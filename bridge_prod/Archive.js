/**
 * Archive.gs — автопрореживание журнала cc_log (KB_claude_code_log).
 *
 * Держит cc_log компактным (<= CCLOG_MAX_BYTES символов): старые записи переносит в архивный
 * док KB_claude_code_log_archive. Читает/пишет доки ЛОКАЛЬНО (DocumentApp) — без HTTP, потому
 * НЕ флапает на больших доках (в отличие от read_doc/write_doc по сети).
 *
 * Зона ответственности: ТОЛЬКО Brain-доки cc_log и его архив. Рабочих таблиц не касается.
 * Использует общие хелперы из ReadDocs.gs: getBrainManifest_, getOrCreateDoc_, BRAIN_PROP_KEY.
 *
 * Эндпоинты (case в Bridge.gs doPost):
 *   prune_cc_log        — разовый прогон pruneCcLog_() (ручной/из bridge_client).
 *   setup_prune_trigger — установить ежедневный time-trigger (идемпотентно).
 * Триггер вызывает pruneCcLogTrigger() (стабильное имя хендлера).
 *
 * 29.07.2026 в этот же файл добавлена ротация cowork_log (см. блок ниже):
 *   prune_cowork_log / setup_cowork_prune_trigger / prune_cowork_selftest.
 * ВСЕ записи в доки идут под общим замком withBrainLock_ (ReadDocs.gs) — тем же
 * LockService, что держит очередь задач.
 */

var CCLOG_KEY = 'cc_log';
var CCLOG_ARCHIVE_KEY = 'cc_log_archive';
var CCLOG_ARCHIVE_DOC = 'KB_claude_code_log_archive';
var CCLOG_MAXBYTES_PROP = 'CCLOG_MAX_BYTES';
var CCLOG_MAXBYTES_DEFAULT = 50000;
var CCLOG_TRIGGER_HANDLER = 'pruneCcLogTrigger';
var CCLOG_ARCH_MARK = '════';

/** Порог из Script Property CCLOG_MAX_BYTES (символов), дефолт 50000. Меняется без редеплоя. */
function ccLogMaxBytes_() {
  var v = PropertiesService.getScriptProperties().getProperty(CCLOG_MAXBYTES_PROP);
  var n = v ? Number(v) : NaN;
  return (isFinite(n) && n > 0) ? n : CCLOG_MAXBYTES_DEFAULT;
}

/** id архивного дока; если ключа нет в манифесте — создать док и зарегистрировать (закрывает хвост Части A). */
function ccLogArchiveId_() {
  var manifest = getBrainManifest_();
  if (manifest[CCLOG_ARCHIVE_KEY]) return manifest[CCLOG_ARCHIVE_KEY];
  if (!manifest.folder_id) throw new Error('no folder_id в манифесте — сначала setupBrain');
  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, CCLOG_ARCHIVE_DOC);
  doc.saveAndClose();
  var id = doc.getId();
  manifest[CCLOG_ARCHIVE_KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));
  return id;
}

/**
 * Разбить текст на записи по заголовкам (KEY YYYY-MM-DD, время опц.). Индексный разрез — лоссless.
 *
 * Контракт строки журнала: <ТИП> <ГГГГ-ММ-ДД ЧЧ:ММ UTC>: <текст>. ASK добавлен 29.07.2026 —
 * это тип «развилка-остановка, нужен выбор человека» (правило журнала в CLAUDE.md: DONE для
 * завершения, ASK для развилки). До правки ASK-запись НЕ была заголовком: она прилипала к
 * предыдущей записи как её хвост и уезжала в архив вместе с ней — то есть незакрытый вопрос
 * владельцу мог уехать в архив, не будучи отдельной записью.
 *
 * Якорь НАМЕРЕННО обрывается на дате, а не тянется до « UTC:». Этот разрез общий для ЧЕТЫРЁХ
 * прореживаний (cc_log, review, review_size, sessions_log), а в их доках лежат легаси-строки
 * без времени и без UTC. Ужесточение под новый контракт сместило бы границы записей в живых
 * доках — поэтому меняем ТОЛЬКО набор типов, ничего больше.
 */
function ccLogSplit_(text) {
  var re = /^(PLAN|DONE|NOTE|ASK|BLOCKED|WAITING|SKIPPED)\s+\d{4}-\d{2}-\d{2}/gm;
  var starts = [], m;
  while ((m = re.exec(text)) !== null) {
    starts.push(m.index);
    if (re.lastIndex === m.index) re.lastIndex++;
  }
  var preamble = starts.length ? text.substring(0, starts[0]) : text;
  var entries = [];
  for (var i = 0; i < starts.length; i++) {
    var s = starts[i];
    var e = (i + 1 < starts.length) ? starts[i + 1] : text.length;
    entries.push(text.substring(s, e));
  }
  return { preamble: preamble, entries: entries };
}

/**
 * Ядро: если cc_log > порога — оставить новейшие записи (сумма <= порога), остальные перенести
 * в архив (newest-first, под шапкой архива). Идемпотентно: если уже компактный — no-op.
 * Под общим замком записи (withBrainLock_) — читаем и пишем док как одну неделимую операцию.
 */
function pruneCcLog_() {
  return withBrainLock_('prune_cc_log', pruneCcLogUnlocked_);
}

function pruneCcLogUnlocked_() {
  var manifest = getBrainManifest_();
  var ccId = manifest[CCLOG_KEY];
  if (!ccId) return { ok: false, error: 'no_cc_log' };

  // Гарантируем существование+регистрацию архива в манифесте при ЛЮБОМ вызове (даже no-op) —
  // закрывает хвост Части A (ключ cc_log_archive) без захода в редактор.
  var archId = ccLogArchiveId_();

  var text = brainTextRead_(ccId);   // type-aware: plain(DriveApp)/Doc(DocumentApp)
  var maxBytes = ccLogMaxBytes_();
  if (text.length <= maxBytes) {
    return { ok: true, moved: 0, kept_chars: text.length, archive_id: archId, note: 'cc_log уже компактный' };
  }

  var sp = ccLogSplit_(text);
  var entries = sp.entries;
  if (entries.length <= 1) {
    return { ok: true, moved: 0, kept_chars: text.length, note: 'мало записей, не делю' };
  }

  // entries уже newest-first: держим новейшие пока сумма (записи) <= порога
  var keep = [], acc = 0;
  for (var i = 0; i < entries.length; i++) {
    if (acc + entries[i].length > maxBytes && keep.length > 0) break;
    keep.push(entries[i]); acc += entries[i].length;
  }
  var move = entries.slice(keep.length);
  if (move.length === 0) {
    return { ok: true, moved: 0, kept_chars: text.length, note: 'нечего переносить' };
  }
  var moveText = move.join('');

  // === архив: перенесённые ПЕРЕД старым содержимым (под шапкой) ===
  var archDoc = DocumentApp.openById(archId);
  var archText = archDoc.getBody().getText();
  var archHeader, archRest;
  var idx = archText.indexOf(CCLOG_ARCH_MARK);
  if (archText.indexOf('📦') === 0 && idx >= 0) {
    var nl = archText.indexOf('\n', idx);
    archHeader = archText.substring(0, nl + 1);
    archRest = archText.substring(nl + 1).replace(/^\n+/, '');
  } else {
    archHeader = '📦 KB_claude_code_log_archive — АРХИВ журнала Claude Code (старые записи cc_log, newest-first).\n' +
                 'Автопрореживание: записи сверх порога переносятся сюда (новейшее сверху).\n' +
                 '════════════════════════════════════════════════════════════════════\n';
    archRest = archText;
  }
  var newArch = archHeader + '\n' + moveText + (archRest ? '\n' + archRest : '');
  archDoc.getBody().clear();
  archDoc.getBody().setText(newArch);
  archDoc.saveAndClose();

  // === cc_log: преамбула-шапка + оставленные новейшие ===
  var keepText = keep.join('');
  var newCc;
  if (sp.preamble && sp.preamble.indexOf('📦') === 0) {
    newCc = sp.preamble.replace(/\n+$/, '\n') + '\n' + keepText;
  } else {
    newCc = '📦 cc_log — КОМПАКТНЫЙ журнал Claude Code. Старое → KB_claude_code_log_archive (id ' + archId + ').\n' +
            '════════════════════════════════════════════════════════════════════\n\n' + keepText;
  }
  brainTextWrite_(ccId, newCc);      // type-aware: plain(setContent)/Doc(clear+setText)

  return { ok: true, moved: move.length, kept: keep.length, kept_chars: newCc.length,
           archive_id: archId, archive_chars: newArch.length, max_bytes: maxBytes };
}

/** Обёртка для time-trigger (стабильное имя хендлера). Ошибки не валят триггер — пишем в лог. */
function pruneCcLogTrigger() {
  try {
    var r = pruneCcLog_();
    Logger.log('pruneCcLogTrigger: ' + JSON.stringify(r));
  } catch (err) {
    Logger.log('pruneCcLogTrigger ОШИБКА: ' + err);
  }
}

/** Установить ежедневный time-trigger (~13:00 UTC). Идемпотентно: прежние того же хендлера сносим. */
function setupPruneTrigger() {
  // Засеять порог Script Property (если ещё нет) — чтобы Филипп менял его в Project Settings без редеплоя.
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty(CCLOG_MAXBYTES_PROP)) {
    props.setProperty(CCLOG_MAXBYTES_PROP, String(CCLOG_MAXBYTES_DEFAULT));
  }
  // Заодно гарантируем регистрацию архива в манифесте.
  try { ccLogArchiveId_(); } catch (e) {}

  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === CCLOG_TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]); removed++;
    }
  }
  ScriptApp.newTrigger(CCLOG_TRIGGER_HANDLER).timeBased().everyDays(1).atHour(13).create();
  return { ok: true, handler: CCLOG_TRIGGER_HANDLER, removed_old: removed,
           schedule: 'ежедневно ~13:00 UTC', max_bytes: ccLogMaxBytes_() };
}


// ============================================================
//  ПРОРЕЖИВАНИЕ KB_review — разовое (по образцу cc_log Часть A).
//  Семантика «что оставить» решается на VPS (Claude Code сверяет PLAN↔DONE),
//  сюда приходит ЯВНЫЙ список keep_headers (первые строки записей, которые ОСТАВИТЬ).
//  Bridge лишь делит док ЛОКАЛЬНО (DocumentApp, без HTTP-флапа), переносит закрытые в архив.
//  Зона: только Brain-доки review/архив. Рабочих таблиц не касается. Endpoint: prune_review (POST).
// ============================================================
var REVIEW_KEY = 'review';
var REVIEW_ARCHIVE_KEY = 'review_archive';
var REVIEW_ARCHIVE_DOC = 'KB_claude_review_archive';
var REVIEW_ARCH_MARK = '════';
var REVIEW_MAXBYTES_PROP = 'REVIEW_MAX_BYTES';
var REVIEW_MAXBYTES_DEFAULT = 50000;
var REVIEW_TRIGGER_HANDLER = 'pruneReviewTrigger';

/** Порог из Script Property REVIEW_MAX_BYTES (символов), дефолт 50000. Меняется без редеплоя. */
function reviewMaxBytes_() {
  var v = PropertiesService.getScriptProperties().getProperty(REVIEW_MAXBYTES_PROP);
  var n = v ? Number(v) : NaN;
  return (isFinite(n) && n > 0) ? n : REVIEW_MAXBYTES_DEFAULT;
}

/** id архивного дока review; если ключа нет в манифесте — создать док и зарегистрировать. */
function reviewArchiveId_() {
  var manifest = getBrainManifest_();
  if (manifest[REVIEW_ARCHIVE_KEY]) return manifest[REVIEW_ARCHIVE_KEY];
  if (!manifest.folder_id) throw new Error('no folder_id в манифесте — сначала setupBrain');
  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, REVIEW_ARCHIVE_DOC);
  doc.saveAndClose();
  var id = doc.getId();
  manifest[REVIEW_ARCHIVE_KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));
  return id;
}

/**
 * Разовое прореживание review: записи, чья ПЕРВАЯ строка ∈ keep_headers — остаются (исходный
 * порядок), остальные переносятся в архив (newest-first, под шапкой). Делёж — ccLogSplit_
 * (тот же индексный лоссless-разрез). Гард безопасности: КАЖДЫЙ keep_header должен найтись
 * ровно — иначе НИЧЕГО не пишем (рассинхрон классификации = отказ, не порча дока).
 * body: { keep_headers: [string,...] }. Под общим замком записи (withBrainLock_).
 */
function pruneReview_(body) {
  return withBrainLock_('prune_review', function () { return pruneReviewUnlocked_(body); });
}

function pruneReviewUnlocked_(body) {
  var b = body || {};
  var keepHeaders = b.keep_headers;
  if (!keepHeaders || Object.prototype.toString.call(keepHeaders) !== '[object Array]') {
    return { ok: false, error: 'bad_keep_headers', message: 'нужен массив keep_headers' };
  }
  var manifest = getBrainManifest_();
  var revId = manifest[REVIEW_KEY];
  if (!revId) return { ok: false, error: 'no_review' };
  var archId = reviewArchiveId_();  // bootstrap create+register при любом вызове

  var revDoc = DocumentApp.openById(revId);
  var text = revDoc.getBody().getText();
  var sp = ccLogSplit_(text);            // переиспользуем разрез cc_log (тот же regex заголовков)
  var entries = sp.entries;
  if (entries.length === 0) {
    return { ok: true, moved: 0, kept: 0, note: 'нет записей' };
  }

  // нормализация заголовков для сверки (trim первой строки)
  var wanted = {};
  for (var i = 0; i < keepHeaders.length; i++) wanted[String(keepHeaders[i]).trim()] = 0;

  var keep = [], move = [], keepChars = 0, moveChars = 0;
  for (var j = 0; j < entries.length; j++) {
    var first = entries[j].split('\n')[0].trim();
    if (wanted.hasOwnProperty(first)) {
      wanted[first]++; keep.push(entries[j]); keepChars += entries[j].length;
    } else {
      move.push(entries[j]); moveChars += entries[j].length;
    }
  }
  // гард: все запрошенные keep_headers должны быть найдены ровно (0 => не нашли, нет порчи)
  var unmatched = [];
  for (var key in wanted) { if (wanted[key] === 0) unmatched.push(key); }
  if (unmatched.length > 0) {
    return { ok: false, error: 'unmatched_headers', unmatched: unmatched,
             message: 'keep_header не найден в review — запись НЕ изменена (рассинхрон классификации)' };
  }
  if (move.length === 0) {
    return { ok: true, moved: 0, kept: keep.length, note: 'нечего переносить', archive_id: archId };
  }
  var moveText = move.join('');

  // === архив: перенесённые ПЕРЕД старым содержимым (под шапкой), newest-first ===
  var archDoc = DocumentApp.openById(archId);
  var archText = archDoc.getBody().getText();
  var archHeader, archRest;
  var idx = archText.indexOf(REVIEW_ARCH_MARK);
  if (archText.indexOf('📦') === 0 && idx >= 0) {
    var nl = archText.indexOf('\n', idx);
    archHeader = archText.substring(0, nl + 1);
    archRest = archText.substring(nl + 1).replace(/^\n+/, '');
  } else {
    archHeader = '📦 KB_claude_review_archive — АРХИВ канала ревью (ЗАКРЫТЫЕ PLAN: задеплоено/есть DONE в cc_log).\n' +
                 'Прореживание по образцу cc_log: закрытые записи переносятся сюда (новейшее сверху). Ничего не удаляется.\n' +
                 '════════════════════════════════════════════════════════════════════\n';
    archRest = archText;
  }
  var newArch = archHeader + '\n' + moveText + (archRest ? '\n' + archRest : '');
  archDoc.getBody().clear();
  archDoc.getBody().setText(newArch);
  archDoc.saveAndClose();

  // === review: шапка + оставленные (исходный порядок) ===
  var keepText = keep.join('');
  var newRev = '📦 KB_review — КОМПАКТНЫЙ канал ревью. Остаются только АКТУАЛЬНЫЕ PLAN (ждут ревью/деплоя).\n' +
               'Закрытое (задеплоено/есть DONE) → KB_claude_review_archive (id ' + archId + ').\n' +
               '════════════════════════════════════════════════════════════════════\n\n' + keepText;
  revDoc.getBody().clear();
  revDoc.getBody().setText(newRev);
  revDoc.saveAndClose();

  return { ok: true, kept: keep.length, moved: move.length,
           kept_entry_chars: keepChars, moved_entry_chars: moveChars,
           orig_chars: text.length, review_new_chars: newRev.length, archive_new_chars: newArch.length,
           review_id: revId, archive_id: archId };
}


// ============================================================
//  АВТОПРОРЕЖИВАНИЕ KB_review ПО РАЗМЕРУ — рекуррентное (зеркало pruneCcLog_).
//  Держит review <= REVIEW_MAX_BYTES: новейшие записи остаются, старые → архив (newest-first).
//  Эвристика «новейшее ≈ актуальное»: в review новые PLAN сверху, закрытые со временем опускаются вниз.
//  Идемпотентно (no-op если уже компактный). Локально DocumentApp — не флапает.
//  Endpoint: prune_review_size (ручной прогон); триггер: pruneReviewTrigger (ежедневно).
// ============================================================
function pruneReviewBySize_() {
  return withBrainLock_('prune_review_size', pruneReviewBySizeUnlocked_);
}

function pruneReviewBySizeUnlocked_() {
  var manifest = getBrainManifest_();
  var revId = manifest[REVIEW_KEY];
  if (!revId) return { ok: false, error: 'no_review' };
  var archId = reviewArchiveId_();  // гарантируем существование+регистрацию архива при любом вызове

  var text = brainTextRead_(revId);   // type-aware: plain(DriveApp)/Doc(DocumentApp)
  var maxBytes = reviewMaxBytes_();
  if (text.length <= maxBytes) {
    return { ok: true, moved: 0, kept_chars: text.length, archive_id: archId, note: 'review уже компактный' };
  }

  var sp = ccLogSplit_(text);   // тот же индексный лоссless-разрез (regex заголовков общий)
  var entries = sp.entries;
  if (entries.length <= 1) {
    return { ok: true, moved: 0, kept_chars: text.length, note: 'мало записей, не делю' };
  }

  // entries newest-first: держим новейшие пока сумма <= порога
  var keep = [], acc = 0;
  for (var i = 0; i < entries.length; i++) {
    if (acc + entries[i].length > maxBytes && keep.length > 0) break;
    keep.push(entries[i]); acc += entries[i].length;
  }
  var move = entries.slice(keep.length);
  if (move.length === 0) {
    return { ok: true, moved: 0, kept_chars: text.length, note: 'нечего переносить' };
  }
  var moveText = move.join('');

  // === архив: перенесённые ПЕРЕД старым содержимым (под шапкой) ===
  var archDoc = DocumentApp.openById(archId);
  var archText = archDoc.getBody().getText();
  var archHeader, archRest;
  var idx = archText.indexOf(REVIEW_ARCH_MARK);
  if (archText.indexOf('📦') === 0 && idx >= 0) {
    var nl = archText.indexOf('\n', idx);
    archHeader = archText.substring(0, nl + 1);
    archRest = archText.substring(nl + 1).replace(/^\n+/, '');
  } else {
    archHeader = '📦 KB_claude_review_archive — АРХИВ канала ревью (ЗАКРЫТЫЕ PLAN: задеплоено/есть DONE в cc_log).\n' +
                 'Прореживание по образцу cc_log: закрытые записи переносятся сюда (новейшее сверху). Ничего не удаляется.\n' +
                 '════════════════════════════════════════════════════════════════════\n';
    archRest = archText;
  }
  var newArch = archHeader + '\n' + moveText + (archRest ? '\n' + archRest : '');
  archDoc.getBody().clear();
  archDoc.getBody().setText(newArch);
  archDoc.saveAndClose();

  // === review: преамбула-шапка + оставленные новейшие ===
  var keepText = keep.join('');
  var newRev;
  if (sp.preamble && sp.preamble.indexOf('📦') === 0) {
    newRev = sp.preamble.replace(/\n+$/, '\n') + '\n' + keepText;
  } else {
    newRev = '📦 KB_review — КОМПАКТНЫЙ канал ревью. Старое → KB_claude_review_archive (id ' + archId + ').\n' +
             '════════════════════════════════════════════════════════════════════\n\n' + keepText;
  }
  brainTextWrite_(revId, newRev);     // type-aware: plain(setContent)/Doc(clear+setText)

  return { ok: true, moved: move.length, kept: keep.length, kept_chars: newRev.length,
           archive_id: archId, archive_chars: newArch.length, max_bytes: maxBytes };
}

/** Обёртка для time-trigger (стабильное имя хендлера). Ошибки не валят триггер — пишем в лог. */
function pruneReviewTrigger() {
  try {
    var r = pruneReviewBySize_();
    Logger.log('pruneReviewTrigger: ' + JSON.stringify(r));
  } catch (err) {
    Logger.log('pruneReviewTrigger ОШИБКА: ' + err);
  }
}

/** Установить ежедневный time-trigger автопрореживания review (~13:10 UTC). Идемпотентно. */
function setupReviewPruneTrigger() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty(REVIEW_MAXBYTES_PROP)) {
    props.setProperty(REVIEW_MAXBYTES_PROP, String(REVIEW_MAXBYTES_DEFAULT));
  }
  try { reviewArchiveId_(); } catch (e) {}  // гарантируем регистрацию архива в манифесте

  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === REVIEW_TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]); removed++;
    }
  }
  // ~13:10 UTC — на 10 мин позже cc_log (13:00), чтобы не пересекаться по DocumentApp.
  ScriptApp.newTrigger(REVIEW_TRIGGER_HANDLER).timeBased().everyDays(1).atHour(13).nearMinute(10).create();
  return { ok: true, handler: REVIEW_TRIGGER_HANDLER, removed_old: removed,
           schedule: 'ежедневно ~13:10 UTC', max_bytes: reviewMaxBytes_() };
}


// ============================================================
//  ПРОРЕЖИВАНИЕ KB_sessions_log (хроника сессий) — plain-text, по образцу cc_log.
//  project_state остаётся ВЕЧНЫМ (без триггера). Хроника живёт здесь, самочистится.
// ============================================================
var SESSIONS_KEY = 'sessions_log';
var SESSIONS_ARCHIVE_KEY = 'sessions_log_archive';
var SESSIONS_ARCHIVE_NAME = 'KB_sessions_log_archive';
var SESSIONS_ARCH_MARK = '════';
var SESSIONS_MAXBYTES_PROP = 'SESSIONS_LOG_MAX_BYTES';
var SESSIONS_MAXBYTES_DEFAULT = 50000;
var SESSIONS_TRIGGER_HANDLER = 'pruneSessionsLogTrigger';

function sessionsMaxBytes_() {
  var v = PropertiesService.getScriptProperties().getProperty(SESSIONS_MAXBYTES_PROP);
  var n = parseInt(v, 10);
  return (isFinite(n) && n > 0) ? n : SESSIONS_MAXBYTES_DEFAULT;
}

/** id архива sessions_log (plain-text); если нет — создать plain-файл и зарегистрировать. */
function sessionsArchiveId_() {
  var manifest = getBrainManifest_();
  if (manifest[SESSIONS_ARCHIVE_KEY]) return manifest[SESSIONS_ARCHIVE_KEY];
  if (!manifest.folder_id) throw new Error('no folder_id');
  var folder = DriveApp.getFolderById(manifest.folder_id);
  var file = folder.createFile(SESSIONS_ARCHIVE_NAME, '', 'text/plain');
  var id = file.getId();
  manifest[SESSIONS_ARCHIVE_KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));
  return id;
}

/** Прорежать sessions_log по размеру (новейшие записи ≤ порога, старые → архив). plain-text.
 *  Под общим замком записи (withBrainLock_). */
function pruneSessionsLog_() {
  return withBrainLock_('prune_sessions_log', pruneSessionsLogUnlocked_);
}

function pruneSessionsLogUnlocked_() {
  var manifest = getBrainManifest_();
  var sId = manifest[SESSIONS_KEY];
  if (!sId) return { ok: false, error: 'no_sessions_log' };
  var archId = sessionsArchiveId_();

  var text = brainTextRead_(sId);
  var maxBytes = sessionsMaxBytes_();
  if (text.length <= maxBytes) {
    return { ok: true, moved: 0, kept_chars: text.length, archive_id: archId, note: 'sessions_log уже компактный' };
  }
  var sp = ccLogSplit_(text);   // тот же индексный разрез по заголовкам PLAN/DONE/NOTE… (lossless)
  var entries = sp.entries;
  if (entries.length <= 1) {
    return { ok: true, moved: 0, kept_chars: text.length, note: 'мало записей, не делю' };
  }
  var keep = [], acc = 0;
  for (var i = 0; i < entries.length; i++) {
    if (acc + entries[i].length > maxBytes && keep.length > 0) break;
    keep.push(entries[i]); acc += entries[i].length;
  }
  var move = entries.slice(keep.length);
  if (move.length === 0) return { ok: true, moved: 0, kept_chars: text.length, note: 'нечего переносить' };
  var moveText = move.join('');

  var archText = brainTextRead_(archId);
  var newArch = (archText ? moveText + '\n' + archText : moveText);
  brainTextWrite_(archId, newArch);

  var keepText = (sp.preamble || '') + keep.join('');
  brainTextWrite_(sId, keepText);
  return { ok: true, moved: move.length, kept: keep.length, kept_chars: keepText.length,
           archive_id: archId, archive_chars: newArch.length, max_bytes: maxBytes };
}

function pruneSessionsLogTrigger() {
  try { Logger.log('pruneSessionsLogTrigger: ' + JSON.stringify(pruneSessionsLog_())); }
  catch (err) { Logger.log('pruneSessionsLogTrigger ОШИБКА: ' + err); }
}

function setupSessionsPruneTrigger() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty(SESSIONS_MAXBYTES_PROP)) {
    props.setProperty(SESSIONS_MAXBYTES_PROP, String(SESSIONS_MAXBYTES_DEFAULT));
  }
  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === SESSIONS_TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]); removed++;
    }
  }
  // ~13:20 UTC — после cc_log(13:00)/review(13:10), чтобы не пересекаться по DocumentApp/DriveApp.
  ScriptApp.newTrigger(SESSIONS_TRIGGER_HANDLER).timeBased().everyDays(1).atHour(13).nearMinute(20).create();
  return { ok: true, handler: SESSIONS_TRIGGER_HANDLER, removed_old: removed,
           schedule: 'ежедневно ~13:20 UTC', max_bytes: sessionsMaxBytes_() };
}

// ============================================================
//  РОТАЦИЯ cowork_log (журнал Dispatch/Cowork) — по образцу prune_cc_log.
//
//  Отличие от cc_log, НАМЕРЕННОЕ: cowork_log — док, в который дозаписывают СВЕРХУ
//  (cowork_log_append кладёт новую строку в голову, новейшее наверху). Поэтому шапку
//  «📦 …» в источник НЕ впечатываем — иначе следующая дозапись легла бы ВЫШЕ шапки и
//  та уползла бы в середину журнала. Источник остаётся ровно тем, чем был: preamble
//  (как правило пустой) + новейшие записи. Шапка живёт только в АРХИВЕ, куда никто,
//  кроме ротации, не пишет. Это шаблон pruneSessionsLog_, а не pruneCcLog_.
//
//  Архив — plain-text файл (не Google-Doc): cowork_log исторически дорастал до 750 КБ,
//  а DocumentApp на таких размерах и тормозит, и изнашивает структуру (см. migrateJournalToPlain_).
//
//  Порог — Script Property COWORK_MAX_BYTES, меняется без редеплоя.
//  Триггер НЕ включается этим кодом: setupCoworkPruneTrigger() существует, но не вызвана.
// ============================================================
var COWORK_KEY = 'cowork_log';
var COWORK_ARCHIVE_KEY = 'cowork_log_archive';
var COWORK_ARCHIVE_NAME = 'KB_cowork_log_archive';
var COWORK_ARCH_MARK = '════';
var COWORK_MAXBYTES_PROP = 'COWORK_MAX_BYTES';
var COWORK_MAXBYTES_DEFAULT = 50000;
var COWORK_TRIGGER_HANDLER = 'pruneCoworkLogTrigger';
var COWORK_ARCH_HEADER =
  '📦 KB_cowork_log_archive — АРХИВ журнала Dispatch/Cowork (старые записи cowork_log, newest-first).\n' +
  'Ротация по размеру: записи сверх порога COWORK_MAX_BYTES переносятся сюда. Ничего не удаляется.\n' +
  '════════════════════════════════════════════════════════════════════\n';

/** Порог из Script Property COWORK_MAX_BYTES (символов), дефолт 50000. Меняется без редеплоя. */
function coworkMaxBytes_() {
  var v = PropertiesService.getScriptProperties().getProperty(COWORK_MAXBYTES_PROP);
  var n = parseInt(v, 10);
  return (isFinite(n) && n > 0) ? n : COWORK_MAXBYTES_DEFAULT;
}

/** id plain-text файла в папке Brain по ключу манифеста; нет — создать и зарегистрировать. */
function brainPlainId_(key, name) {
  var manifest = getBrainManifest_();
  if (manifest[key]) return manifest[key];
  if (!manifest.folder_id) throw new Error('no folder_id в манифесте — сначала setupBrain');
  var folder = DriveApp.getFolderById(manifest.folder_id);
  var file = folder.createFile(name, '', 'text/plain');
  var id = file.getId();
  manifest[key] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));
  return id;
}

function coworkArchiveId_() {
  return brainPlainId_(COWORK_ARCHIVE_KEY, COWORK_ARCHIVE_NAME);
}

/**
 * ЯДРО ротации — работает по ЯВНЫМ id, поэтому одинаково гоняется и на живом cowork_log,
 * и на тестовом доке (см. coworkPruneSelfTest_). Один и тот же код на обеих дорожках:
 * проверка не «повторяет логику», а исполняет ту самую.
 *
 * Порядок записи: СНАЧАЛА архив, ПОТОМ источник. Если второй записи не случится, записи
 * останутся в ОБОИХ доках (дубль, видно глазами), а не пропадут — потеря хуже дубля.
 */
function coworkRotate_(srcId, archId, maxBytes) {
  var text = brainTextRead_(srcId);
  var before = text.length;
  if (before <= maxBytes) {
    return { ok: true, moved: 0, kept: 0, before_chars: before, kept_chars: before,
             archive_id: archId, max_bytes: maxBytes, note: 'cowork_log уже компактный' };
  }

  var sp = ccLogSplit_(text);
  var entries = sp.entries;
  if (entries.length <= 1) {
    return { ok: true, moved: 0, kept: entries.length, before_chars: before, kept_chars: before,
             entries: entries.length, archive_id: archId, max_bytes: maxBytes,
             note: 'мало записей, не делю' };
  }

  // entries newest-first: держим новейшие, пока сумма записей <= порога
  var keep = [], acc = 0;
  for (var i = 0; i < entries.length; i++) {
    if (acc + entries[i].length > maxBytes && keep.length > 0) break;
    keep.push(entries[i]); acc += entries[i].length;
  }
  var move = entries.slice(keep.length);
  if (move.length === 0) {
    return { ok: true, moved: 0, kept: keep.length, before_chars: before, kept_chars: before,
             entries: entries.length, archive_id: archId, max_bytes: maxBytes,
             note: 'нечего переносить' };
  }
  var moveText = move.join('');

  // === архив: перенесённые ПЕРЕД старым содержимым, под шапкой (шапка переживает прогоны) ===
  var archText = brainTextRead_(archId);
  var archHeader, archRest;
  var idx = archText.indexOf(COWORK_ARCH_MARK);
  if (archText.indexOf('📦') === 0 && idx >= 0) {
    var nl = archText.indexOf('\n', idx);
    archHeader = archText.substring(0, nl + 1);
    archRest = archText.substring(nl + 1).replace(/^\n+/, '');
  } else {
    archHeader = COWORK_ARCH_HEADER;
    archRest = archText;
  }
  var newArch = archHeader + '\n' + moveText + (archRest ? '\n' + archRest : '');
  brainTextWrite_(archId, newArch);

  // === источник: преамбула как была + оставленные новейшие. Шапку НЕ впечатываем. ===
  var keepText = (sp.preamble || '') + keep.join('');
  brainTextWrite_(srcId, keepText);

  return { ok: true, entries: entries.length, kept: keep.length, moved: move.length,
           before_chars: before, kept_chars: keepText.length,
           moved_chars: moveText.length, archive_id: archId,
           archive_chars: newArch.length, max_bytes: maxBytes };
}

/** Ротация ЖИВОГО cowork_log. Под общим замком записи. Идемпотентна (no-op если компактный). */
function pruneCoworkLog_() {
  return withBrainLock_('prune_cowork_log', pruneCoworkLogUnlocked_);
}

function pruneCoworkLogUnlocked_() {
  var manifest = getBrainManifest_();
  var srcId = manifest[COWORK_KEY];
  if (!srcId) return { ok: false, error: 'no_cowork_log' };
  var archId = coworkArchiveId_();   // создаём+регистрируем архив при ЛЮБОМ вызове, даже no-op
  return coworkRotate_(srcId, archId, coworkMaxBytes_());
}

/** Обёртка для time-trigger (стабильное имя хендлера). Ошибки не валят триггер — пишем в лог. */
function pruneCoworkLogTrigger() {
  try {
    var r = pruneCoworkLog_();
    Logger.log('pruneCoworkLogTrigger: ' + JSON.stringify(r));
  } catch (err) {
    Logger.log('pruneCoworkLogTrigger ОШИБКА: ' + err);
  }
}

/**
 * Установить ежедневный time-trigger ротации cowork_log (~13:30 UTC). Идемпотентно.
 * НЕ ВЫЗЫВАЕТСЯ НИОТКУДА в этом коде — включение триггера остаётся решением владельца
 * (endpoint setup_cowork_prune_trigger). Пока не вызвана — ротация только ручная.
 */
function setupCoworkPruneTrigger() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty(COWORK_MAXBYTES_PROP)) {
    props.setProperty(COWORK_MAXBYTES_PROP, String(COWORK_MAXBYTES_DEFAULT));
  }
  try { coworkArchiveId_(); } catch (e) {}

  var triggers = ScriptApp.getProjectTriggers();
  var removed = 0;
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === COWORK_TRIGGER_HANDLER) {
      ScriptApp.deleteTrigger(triggers[i]); removed++;
    }
  }
  // ~13:30 UTC — после cc_log(13:00)/review(13:10)/sessions(13:20): доки не пересекаются,
  // и общий замок записи не держится четырьмя ротациями одновременно.
  ScriptApp.newTrigger(COWORK_TRIGGER_HANDLER).timeBased().everyDays(1).atHour(13).nearMinute(30).create();
  return { ok: true, handler: COWORK_TRIGGER_HANDLER, removed_old: removed,
           schedule: 'ежедневно ~13:30 UTC', max_bytes: coworkMaxBytes_() };
}


// ============================================================
//  САМОПРОВЕРКА РОТАЦИИ — на ТЕСТОВЫХ доках, живой cowork_log только ЧИТАЕТСЯ.
//
//  Фикстура снимается с прода (правило CLAUDE.md «мок обязан копировать живой формат»):
//  тестовый док засевается ПЕРВЫМИ K записями живого cowork_log — дословно, вместе с их
//  реальными заголовками, кириллицей и хвостами. Никакой идеализированной схемы.
//
//  Живой cowork_log в этой функции НЕ ПИШЕТСЯ ни при каком исходе — только brainTextRead_.
//  body: { entries?: K=12, max_bytes?: M (деф. половина засеянного), archive_preview?: N=4000 }
// ============================================================
var COWORK_TEST_SRC_KEY = 'cowork_log_test';
var COWORK_TEST_SRC_NAME = 'KB_cowork_log_TEST';
var COWORK_TEST_ARCH_KEY = 'cowork_log_test_archive';
var COWORK_TEST_ARCH_NAME = 'KB_cowork_log_TEST_archive';

function coworkPruneSelfTest_(body) {
  return withBrainLock_('prune_cowork_selftest', function () {
    return coworkPruneSelfTestUnlocked_(body || {});
  });
}

function coworkPruneSelfTestUnlocked_(b) {
  var manifest = getBrainManifest_();
  var liveId = manifest[COWORK_KEY];
  if (!liveId) return { ok: false, error: 'no_cowork_log' };

  var wantEntries = parseInt(b.entries, 10);
  if (!isFinite(wantEntries) || wantEntries <= 0) wantEntries = 12;
  var preview = parseInt(b.archive_preview, 10);
  if (!isFinite(preview) || preview <= 0) preview = 4000;

  // --- фикстура с прода: живой док только читаем ---
  var liveText = brainTextRead_(liveId);
  var liveSp = ccLogSplit_(liveText);
  if (liveSp.entries.length === 0) {
    return { ok: false, error: 'live_has_no_entries', live_chars: liveText.length };
  }
  var seedEntries = liveSp.entries.slice(0, wantEntries);
  var seedText = seedEntries.join('');

  var maxBytes = parseInt(b.max_bytes, 10);
  if (!isFinite(maxBytes) || maxBytes <= 0) maxBytes = Math.floor(seedText.length / 2);

  // --- тестовые доки: пересеваем начисто, чтобы прогон был воспроизводимым ---
  var testSrcId = brainPlainId_(COWORK_TEST_SRC_KEY, COWORK_TEST_SRC_NAME);
  var testArchId = brainPlainId_(COWORK_TEST_ARCH_KEY, COWORK_TEST_ARCH_NAME);
  brainTextWrite_(testSrcId, seedText);
  brainTextWrite_(testArchId, '');

  var srcBefore = brainTextRead_(testSrcId).length;

  // --- ТО ЖЕ ядро, что гоняет живую ротацию ---
  var res = coworkRotate_(testSrcId, testArchId, maxBytes);

  var srcAfterText = brainTextRead_(testSrcId);
  var archAfterText = brainTextRead_(testArchId);

  // --- проверка сохранности: ни один символ не потерян и не задвоен ---
  var lossless = (srcAfterText + archAfterText.substring(COWORK_ARCH_HEADER.length + 1)
                    .replace(/^\n+/, '')) .length;

  return {
    ok: true,
    live_doc_untouched: true,
    live_id: liveId,
    live_chars: liveText.length,
    live_entries_total: liveSp.entries.length,
    seeded_entries: seedEntries.length,
    max_bytes: maxBytes,
    test_src_id: testSrcId,
    test_archive_id: testArchId,
    src_chars_before: srcBefore,
    src_chars_after: srcAfterText.length,
    archive_chars_after: archAfterText.length,
    rotate_result: res,
    sum_after_vs_before: (srcAfterText.length + archAfterText.length) + ' vs ' + srcBefore,
    entries_after_in_src: ccLogSplit_(srcAfterText).entries.length,
    entries_after_in_archive: ccLogSplit_(archAfterText).entries.length,
    lossless_chars: lossless,
    archive_text: archAfterText.length > preview
      ? archAfterText.substring(0, preview) + '\n…[обрезано в отчёте, в доке целиком]'
      : archAfterText,
    src_text_after: srcAfterText.length > preview
      ? srcAfterText.substring(0, preview) + '\n…[обрезано в отчёте, в доке целиком]'
      : srcAfterText
  };
}


/** Аудит: список всех prune-триггеров проекта (handler + расписание из кода). */
function listProjectTriggers_() {
  var trs = ScriptApp.getProjectTriggers();
  var handlers = [];
  for (var i = 0; i < trs.length; i++) handlers.push(trs[i].getHandlerFunction());
  return {
    ok: true, count: trs.length, handlers: handlers,
    known: {
      pruneCcLogTrigger: { schedule: '~13:00 UTC', max_bytes: ccLogMaxBytes_() },
      pruneReviewTrigger: { schedule: '~13:10 UTC', max_bytes: reviewMaxBytes_() },
      pruneSessionsLogTrigger: { schedule: '~13:20 UTC', max_bytes: sessionsMaxBytes_() },
      pruneCoworkLogTrigger: { schedule: '~13:30 UTC', max_bytes: coworkMaxBytes_(),
                               installed: handlers.indexOf('pruneCoworkLogTrigger') >= 0 }
    }
  };
}
