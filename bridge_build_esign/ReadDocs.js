/**
 * ReadDocs.gs — «общий мозг» TurboBaby на Google Drive.
 *
 * Зона ответственности этого файла (правило проекта: 1 файл Bridge = своя зона):
 *   - setupBrain()        — одноразовая настройка: папка Brain + 4 Google Docs из .md +
 *                           манифест в Script Properties + KB_index. Запускать ИЗ РЕДАКТОРА.
 *   - handleReadDoc_(e)   — endpoint read_doc  (по id или name через манифест).
 *   - handleListBrain_(e) — endpoint list_brain (отдаёт весь манифест).
 *   - handleListBrainFolder_(e) — endpoint list_brain_folder (дети папки Brain: имена и id).
 *
 * Регистрация в роутере: добавить ТОЛЬКО два case в switch(action) внутри doGet (Bridge.gs).
 * Больше в Bridge.gs ничего не трогать.
 */

// === Константы ===
var BRAIN_PARENT_ID = '19UHmWP1dsb1ADk8nwpZThOP0pCu_uhea'; // главная папка компании
var BRAIN_FOLDER_NAME = 'TurboBaby Brain';
var BRAIN_PROP_KEY = 'BRAIN_MANIFEST';

// Маппинг: исходный .md в папке Brain → имя Google Doc → логическое имя в манифесте.
var BRAIN_MAP = [
  { md: 'knowledge_base.md',   doc: 'KB_knowledge_base', key: 'knowledge_base' },
  { md: 'project_state.md',    doc: 'KB_project_state',  key: 'project_state' },
  { md: 'turbobaby_faq_v1.md', doc: 'KB_faq',            key: 'faq' },
  { md: 'park_list.md',        doc: 'KB_park_list',      key: 'park_list' }
];


// ============================================================
//  ОДНОРАЗОВАЯ НАСТРОЙКА — запускать из редактора Apps Script
// ============================================================
function setupBrain() {
  var parent = DriveApp.getFolderById(BRAIN_PARENT_ID);
  var brain = getOrCreateFolder_(parent, BRAIN_FOLDER_NAME);
  Logger.log('Папка Brain: ' + brain.getId());

  var manifest = getBrainManifest_();
  manifest.folder_id = brain.getId();
  var indexLines = [
    'TurboBaby Brain — оглавление базы знаний',
    '',
    'Папка Brain: ' + brain.getId(),
    ''
  ];
  var missing = [];

  BRAIN_MAP.forEach(function (item) {
    var mdFile = findChildFileByName_(brain, item.md);
    if (!mdFile) {
      missing.push(item.md);
      Logger.log('ПРОПУСК: исходник "' + item.md + '" не найден в папке Brain — загрузите его и запустите снова.');
      return;
    }
    var text = mdFile.getBlob().getDataAsString('UTF-8');
    var doc = getOrCreateDoc_(brain, item.doc);
    var body = doc.getBody();
    body.clear();
    body.setText(text);
    doc.saveAndClose();

    var id = doc.getId();
    manifest[item.key] = id;
    indexLines.push(item.key + '  →  ' + item.doc + '  →  ' + id);
    Logger.log(item.doc + ' (' + item.key + '): ' + id);
  });

  // KB_index — человекочитаемое оглавление (дублирует манифест)
  var indexDoc = getOrCreateDoc_(brain, 'KB_index');
  var ib = indexDoc.getBody();
  ib.clear();
  ib.setText(indexLines.join('\n'));
  indexDoc.saveAndClose();
  manifest.index = indexDoc.getId();

  // Манифест → Script Properties (источник правды для read_doc/list_brain)
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  // === Итоговый лог для Филиппа ===
  Logger.log('================ setupBrain завершён ================');
  Logger.log('folder_id      : ' + manifest.folder_id);
  Logger.log('knowledge_base : ' + (manifest.knowledge_base || '—'));
  Logger.log('project_state  : ' + (manifest.project_state || '—'));
  Logger.log('faq            : ' + (manifest.faq || '—'));
  Logger.log('park_list      : ' + (manifest.park_list || '—'));
  Logger.log('index          : ' + manifest.index);
  if (missing.length) {
    Logger.log('ВНИМАНИЕ: не сконвертированы (нет исходника): ' + missing.join(', '));
  }
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return manifest;
}


// ============================================================
//  TYPE-AWARE ДОСТУП К ТЕКСТУ BRAIN-УЗЛА (plain-text файл / Google-Doc)
//  Журналы cc_log/review мигрированы на plain-text (DriveApp) — read без внутр. ошибки Docs,
//  write без износа структуры. Base-доки пока Google-Doc (DocumentApp). Хелперы ветвят по MIME.
// ============================================================
function brainTextRead_(id) {
  var file = DriveApp.getFileById(id);
  if (file.getMimeType() === 'text/plain') {
    return file.getBlob().getDataAsString('UTF-8');   // быстро, без DocumentApp
  }
  return DocumentApp.openById(id).getBody().getText();
}

function brainTextWrite_(id, text) {
  var file = DriveApp.getFileById(id);
  if (file.getMimeType() === 'text/plain') {
    file.setContent(text);                            // plain → без структуры, нечему изнашиваться
    return;
  }
  var doc = DocumentApp.openById(id);
  doc.getBody().clear();
  doc.getBody().setText(text);
  doc.saveAndClose();
}

// ============================================================
//  ЗАМОК ЗАПИСИ В ДОКИ — тот же LockService, что держит очередь задач (BotData.gs).
//  Зачем: любая запись в Brain-док — это read-modify-write ВНУТРИ одного вызова
//  (прочитали текст → порезали → записали обратно). Без замка два таких вызова
//  переплетаются, и тот, кто записал вторым, затирает работу первого.
//  Закрывает две гонки: писатель↔писатель (два write_doc) и писатель↔ротация
//  (write_doc, приехавший в середину прореживания). Вторая появится сама, как
//  только владелец включит time-trigger ротации, — замок ставим ЗАРАНЕЕ.
//
//  Замок ОБЩИЙ с очередью задач (LockService.getScriptLock() — на проект один).
//  Следствие честно: длинная ротация задерживает enqueue/claim_task. Поэтому
//  ротация и живёт по ночному расписанию (~13:xx UTC), а не в рабочем цикле.
//  tryLock (а не waitLock): занято → аккуратный ok:false, а не исключение-500.
// ============================================================
var BRAIN_LOCK_WAIT_MS = 30000;

function withBrainLock_(label, fn) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(BRAIN_LOCK_WAIT_MS)) {
    return { ok: false, error: 'locked', op: label,
             message: 'Доки заняты другой записью (' + label + '): ждали ' +
                      BRAIN_LOCK_WAIT_MS + ' мс. Ничего не изменено, повторите запрос.' };
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

/**
 * Миграция журнала (cc_log/review) с Google-Doc на PLAIN-TEXT файл (фикс износа DocumentApp).
 * Создаёт text/plain файл с тем же именем, переливает ВЕСЬ текст, СТАРЫЙ Doc переименовывает
 * в <имя>_OLD (бэкап, НЕ удаляет), переключает BRAIN_MANIFEST[key] на новый id.
 * Идемпотентно: если узел уже plain — no-op. body: { key }.
 */
function migrateJournalToPlain_(body) {
  var b = body || {};
  var key = b.key;
  if (!key) return { ok: false, error: 'no_key', message: 'Нужен key (cc_log/review)' };
  var manifest = getBrainManifest_();
  var oldId = manifest[key];
  if (!oldId) return { ok: false, error: 'unknown_key', key: key };
  if (!manifest.folder_id) return { ok: false, error: 'no_folder' };

  var oldFile = DriveApp.getFileById(oldId);
  if (oldFile.getMimeType() === 'text/plain') {
    return { ok: true, already_plain: true, key: key, id: oldId };
  }

  var text = brainTextRead_(oldId);                 // весь текущий текст (старый ещё Doc)
  var origName = oldFile.getName();
  var folder = DriveApp.getFolderById(manifest.folder_id);
  var newFile = folder.createFile(origName, text, 'text/plain');  // свежий plain с тем же именем
  var newId = newFile.getId();

  oldFile.setName(origName + '_OLD');               // бэкап старого Doc — НЕ удаляем
  manifest[key] = newId;                            // своп манифеста (read_doc/write_doc/prune пойдут на новый)
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  return { ok: true, key: key, old_id: oldId, old_renamed: origName + '_OLD',
           new_id: newId, new_name: origName, chars: text.length };
}

/**
 * Создать НОВЫЙ plain-text файл в папке Brain + (опц.) зарегистрировать в BRAIN_MANIFEST[key].
 * Для бэкапов и новых журналов (sessions_log/archive). body: { name, key (опц.), text }.
 */
function createBrainPlain_(body) {
  var b = body || {};
  var name = b.name;
  var key = b.key || '';
  var text = (b.text != null) ? String(b.text) : '';
  if (!name) return { ok: false, error: 'no_name' };
  var manifest = getBrainManifest_();
  if (!manifest.folder_id) return { ok: false, error: 'no_folder' };
  var folder = DriveApp.getFolderById(manifest.folder_id);
  var file = folder.createFile(name, text, 'text/plain');
  var id = file.getId();
  if (key) {
    manifest[key] = id;
    PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));
  }
  return { ok: true, name: name, key: key || null, id: id, chars: text.length };
}


/**
 * Зарегистрировать СУЩЕСТВУЮЩИЙ Brain-файл в BRAIN_MANIFEST: ключ name → doc id.
 * МЕРЖ: не перезатирает другие ключи; существующий ключ с ДРУГИМ id НЕ меняет без overwrite:true.
 * Защита: файл должен существовать и лежать в Brain-папке (folder_id из манифеста), имя — [a-z0-9_].
 * body: { name, id, overwrite? }. Для регистрации живых план-листов (roadmap_master и т.п.).
 */
function registerBrainDoc_(body) {
  var p = body || {};
  var name = String(p.name == null ? '' : p.name).trim();
  var id = String(p.id == null ? '' : p.id).trim();
  if (!name || !id) return { ok: false, error: 'need_name_id' };
  if (!/^[a-z0-9_]+$/.test(name)) return { ok: false, error: 'bad_name', message: 'имя только [a-z0-9_]' };

  var man = getBrainManifest_();
  if (man[name] && man[name] !== id && p.overwrite !== true) {
    return { ok: false, error: 'exists', name: name, current_id: man[name],
             message: 'ключ уже занят другим id; overwrite:true чтобы сменить' };
  }
  // Файл должен существовать и быть В Brain-папке (не регистрируем мусор/чужое).
  try {
    var f = DriveApp.getFileById(id);
    var title = f.getName();
    var inBrain = false, ps = f.getParents();
    var folderId = man.folder_id || '';
    while (ps.hasNext()) { if (ps.next().getId() === folderId) { inBrain = true; break; } }
    if (folderId && !inBrain) return { ok: false, error: 'not_in_brain', id: id, title: title };
  } catch (err) {
    return { ok: false, error: 'file_not_found', id: id, message: String(err) };
  }
  if (man[name] === id) {
    return { ok: true, name: name, id: id, already: true, total: Object.keys(man).length };
  }
  man[name] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(man));
  return { ok: true, name: name, id: id, registered: true, total: Object.keys(man).length };
}


// ============================================================
//  ENDPOINTS (вызываются из роутера doGet в Bridge.gs)
// ============================================================
function handleReadDoc_(e) {
  if (!brainTokenOk_(e)) return jsonOut_({ ok: false, error: 'unauthorized', message: 'Неверный токен' });
  try {
    var p = (e && e.parameter) ? e.parameter : {};
    var id = p.id;
    var name = p.name;

    if (!id && name) {
      var man = getBrainManifest_();
      id = man[name];
      if (!id) {
        return jsonOut_({ ok: false, error: 'unknown_name',
          message: 'Нет имени "' + name + '" в манифесте. Запустите setupBrain или см. list_brain.' });
      }
    }
    if (!id) {
      return jsonOut_({ ok: false, error: 'missing_param', message: 'Нужен ?id=... или ?name=...' });
    }

    var text = brainTextRead_(id);
    return jsonOut_({ ok: true, name: name || null, id: id, text: text });
  } catch (err) {
    return jsonOut_({ ok: false, error: 'read_failed', message: String(err) });
  }
}

function handleListBrain_(e) {
  if (!brainTokenOk_(e)) return jsonOut_({ ok: false, error: 'unauthorized', message: 'Неверный токен' });
  try {
    return jsonOut_({ ok: true, manifest: getBrainManifest_() });
  } catch (err) {
    return jsonOut_({ ok: false, error: 'manifest_failed', message: String(err) });
  }
}

/**
 * handleListBrainFolder_(e) — endpoint list_brain_folder: ДЕТИ папки Brain, имена и id.
 *
 * Зачем: list_brain отдаёт МАНИФЕСТ (зарегистрированные ключи), а не содержимое папки —
 * документ, положенный в Brain со стороны, в манифесте не появляется, и его id взять
 * было неоткуда. Этот экшен закрывает ровно эту дыру: перечисление детей папки.
 *
 * Адрес папки берётся ОТТУДА ЖЕ, ОТКУДА ЕГО БЕРЁТ МАНИФЕСТ — manifest.folder_id
 * (та же дорога, что у read_doc / createBrainPlain_ / архиватора), а не числом в коде.
 *
 * ТОЛЬКО ЧТЕНИЕ: ничего не создаёт, не переименовывает, не перемещает, не удаляет и
 * манифеста не касается.
 *
 * Параметры (все необязательные):
 *   prefix   — вернуть только детей, чьё имя НАЧИНАЕТСЯ с этой строки;
 *   limit    — потолок отдаваемых файлов (по умолчанию 500, максимум 1000).
 *
 * Ответ: { ok, folder_id, count, files:[{name,id,mime}], folders_count, folders:[{name,id}],
 *          prefix, scanned, truncated }.
 * truncated:true значит «упёрлись в limit» — список НЕ полон, и судить по нему нельзя.
 */
function handleListBrainFolder_(e) {
  if (!brainTokenOk_(e)) return jsonOut_({ ok: false, error: 'unauthorized', message: 'Неверный токен' });
  try {
    var p = (e && e.parameter) ? e.parameter : {};
    var manifest = getBrainManifest_();
    var folderId = manifest.folder_id;
    if (!folderId) {
      return jsonOut_({ ok: false, error: 'no_folder',
        message: 'В манифесте нет folder_id — сначала setupBrain' });
    }

    var prefix = String(p.prefix == null ? '' : p.prefix);
    var limit = parseInt(p.limit, 10);
    if (!(limit > 0)) limit = 500;
    if (limit > 1000) limit = 1000;

    var folder = DriveApp.getFolderById(folderId);

    var files = [];
    var scanned = 0;
    var truncated = false;
    var it = folder.getFiles();
    while (it.hasNext()) {
      var f = it.next();
      scanned++;
      var nm = f.getName();
      if (prefix && nm.indexOf(prefix) !== 0) continue;
      if (files.length >= limit) { truncated = true; break; }
      files.push({ name: nm, id: f.getId(), mime: f.getMimeType() });
    }

    var folders = [];
    var itf = folder.getFolders();
    while (itf.hasNext()) {
      var sub = itf.next();
      var sname = sub.getName();
      if (prefix && sname.indexOf(prefix) !== 0) continue;
      folders.push({ name: sname, id: sub.getId() });
    }

    files.sort(function (a, b) { return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0); });
    folders.sort(function (a, b) { return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0); });

    return jsonOut_({ ok: true, folder_id: folderId, count: files.length, files: files,
                      folders_count: folders.length, folders: folders,
                      prefix: prefix || null, scanned: scanned, truncated: truncated });
  } catch (err) {
    return jsonOut_({ ok: false, error: 'folder_list_failed', message: String(err) });
  }
}


// ============================================================
//  ХЕЛПЕРЫ (namespace с _ — не конфликтуют с Bridge.gs)
// ============================================================
function getBrainManifest_() {
  var raw = PropertiesService.getScriptProperties().getProperty(BRAIN_PROP_KEY);
  if (!raw) return {};
  try { return JSON.parse(raw); } catch (e) { return {}; }
}

/** Защитный токен-чек: если в Script Properties есть BRIDGE_TOKEN — сверяем;
 *  если ключ называется иначе/отсутствует — полагаемся на проверку токена в doGet. */
function brainTokenOk_(e) {
  var expected = PropertiesService.getScriptProperties().getProperty('BRIDGE_TOKEN');
  if (!expected) return true;
  var got = (e && e.parameter) ? e.parameter.token : '';
  return got === expected;
}

function jsonOut_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function getOrCreateFolder_(parent, name) {
  var it = parent.getFoldersByName(name);
  if (it.hasNext()) {
    var f = it.next();
    if (it.hasNext()) Logger.log('ВНИМАНИЕ: в главной папке несколько папок "' + name + '" — беру первую (' + f.getId() + ').');
    return f;
  }
  return parent.createFolder(name);
}

function findChildFileByName_(folder, name) {
  var it = folder.getFilesByName(name);
  return it.hasNext() ? it.next() : null;
}

/** Находит Google Doc по имени в папке или создаёт новый (создаётся в My Drive, затем перемещается). */
function getOrCreateDoc_(folder, name) {
  var it = folder.getFilesByName(name);
  while (it.hasNext()) {
    var file = it.next();
    if (file.getMimeType() === 'application/vnd.google-apps.document') {
      if (it.hasNext()) Logger.log('ВНИМАНИЕ: несколько документов "' + name + '" в Brain — беру первый (' + file.getId() + ').');
      return DocumentApp.openById(file.getId());
    }
  }
  var doc = DocumentApp.create(name);
  moveFileToFolder_(DriveApp.getFileById(doc.getId()), folder);
  return doc;
}

/** Перемещает файл в папку (add + remove из прочих родителей — работает на всех версиях DriveApp). */
function moveFileToFolder_(file, folder) {
  folder.addFile(file);
  var parents = file.getParents();
  while (parents.hasNext()) {
    var p = parents.next();
    if (p.getId() !== folder.getId()) p.removeFile(file);
  }
}


/**
 * write_doc — синк git→Drive: перезаписать ТЕЛО существующего KB_-дока новым текстом.
 * Вызывается из doPost (Bridge.gs), поэтому ВОЗВРАЩАЕТ ОБЪЕКТ (не ContentService) —
 * doPost оборачивает через jsonResponse(Object.assign({action}, ...)). Токен уже проверен
 * verifyToken в doPost до switch.
 *
 * body: { name | id, text }. Только перезапись по существующему id из манифеста:
 * не создаёт документы, не меняет манифест/doc_id. Пустой text запрещён (защита от затирки).
 *
 * Под замком withBrainLock_ (см. выше): пока идёт эта запись, ни другой write_doc, ни
 * ротация в док не войдут. ОГОВОРКА: замок закрывает гонку ВНУТРИ Bridge. Связку
 * «read_doc с ПК → правка на ПК → write_doc» он НЕ закрывает — это два разных HTTP-вызова,
 * между ними замка нет; там от потери правок защищает обратная сверка в brain_writer.
 */
function writeDoc_(body) {
  return withBrainLock_('write_doc', function () { return writeDocUnlocked_(body); });
}

function writeDocUnlocked_(body) {
  try {
    var b = body || {};
    var id = b.id;
    var name = b.name;

    if (!id && name) {
      var man = getBrainManifest_();
      id = man[name];
      if (!id) {
        return { ok: false, error: 'unknown_name',
          message: 'Нет имени "' + name + '" в манифесте. См. list_brain.' };
      }
    }
    if (!id) {
      return { ok: false, error: 'missing_param', message: 'Нужен name или id' };
    }

    var text = b.text;
    if (text === undefined || text === null) {
      return { ok: false, error: 'missing_text', message: 'Нужен параметр text' };
    }
    if (text === '') {
      return { ok: false, error: 'empty_text', message: 'Пустой text запрещён — это затёрло бы документ' };
    }

    brainTextWrite_(id, text);  // plain→setContent / Doc→clear+setText (type-aware)

    return { ok: true, name: name || null, id: id, chars: text.length };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
}

function setupCcLog() {
  var DOC_NAME = 'KB_claude_code_log';
  var KEY = 'cc_log';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('================ setupCcLog завершён ================');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
}

// =================================================================
//  ОДНОРАЗОВАЯ НАСТРОЙКА KB_claude_userbot_log — журнал задач userbot/агента.
//  Создаёт Doc «KB_claude_userbot_log» и добавляет ключ cc_userbot_log в манифест.
//  НЕ трогает другие KB_* — только cc_userbot_log. Идемпотентна (getOrCreateDoc_).
// =================================================================
function setupCcUserbotLog() {
  var DOC_NAME = 'KB_claude_userbot_log';
  var KEY = 'cc_userbot_log';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('============= setupCcUserbotLog завершён =============');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
}

  // =================================================================
//  ОДНОРАЗОВАЯ НАСТРОЙКА KB_review — запускать ИЗ РЕДАКТОРА Apps Script
//  Создаёт Doc «KB_claude_review» и добавляет ключ review в манифест.
//  НЕ трогает другие KB_* — только review. Идемпотентна.
// =================================================================

function setupReview() {
  var DOC_NAME = 'KB_claude_review';
  var KEY = 'review';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('================= setupReview завершён =================');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
}
