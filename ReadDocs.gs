/**
 * ReadDocs.gs — «общий мозг» TurboBaby на Google Drive.
 *
 * Зона ответственности этого файла (правило проекта: 1 файл Bridge = своя зона):
 *   - setupBrain()        — одноразовая настройка: папка Brain + 4 Google Docs из .md +
 *                           манифест в Script Properties + KB_index. Запускать ИЗ РЕДАКТОРА.
 *   - setupCcLog()        — одноразово: создать Doc KB_claude_code_log + ключ cc_log
 *                           в манифесте (лог задач Claude Code). Запускать ИЗ РЕДАКТОРА.
 *   - setupReview()       — одноразово: создать Doc KB_claude_review + ключ review
 *                           (канал ревью Claude-на-сайте). Запускать ИЗ РЕДАКТОРА.
 *   - handleReadDoc_(e)   — endpoint read_doc  (по id или name через манифест).
 *   - handleListBrain_(e) — endpoint list_brain (отдаёт весь манифест).
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

  // Сохраняем уже существующие ключи манифеста (например cc_log), чтобы повторный
  // запуск setupBrain их не затёр — ниже пересобираются только KB_* из BRAIN_MAP.
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
//  ОДНОРАЗОВАЯ НАСТРОЙКА cc_log — запускать ИЗ РЕДАКТОРА Apps Script
//  Создаёт Doc «KB_claude_code_log» и добавляет ключ cc_log в манифест.
//  НЕ трогает другие KB_* — только cc_log. Идемпотентна: повторный запуск
//  не пересоздаёт документ (getOrCreateDoc_ вернёт существующий).
// ============================================================
function setupCcLog() {
  var DOC_NAME = 'KB_claude_code_log';
  var KEY = 'cc_log';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);  // вернёт существующий, если уже создан
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('================ setupCcLog завершён ================');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
}


// ============================================================
//  ОДНОРАЗОВАЯ НАСТРОЙКА KB_claude_userbot_log — журнал задач userbot/агента.
//  Создаёт Doc «KB_claude_userbot_log» и ключ cc_userbot_log в манифесте.
//  НЕ трогает другие KB_* — только cc_userbot_log. Идемпотентна (getOrCreateDoc_).
// ============================================================
function setupCcUserbotLog() {
  var DOC_NAME = 'KB_claude_userbot_log';
  var KEY = 'cc_userbot_log';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);  // вернёт существующий, если уже создан
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('============= setupCcUserbotLog завершён =============');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
}


// ============================================================
//  ОДНОРАЗОВАЯ НАСТРОЙКА KB_review — запускать ИЗ РЕДАКТОРА Apps Script
//  Создаёт Doc «KB_claude_review» и добавляет ключ review в манифест.
//  Канал прямого ревью Claude-на-сайте <-> Claude Code. НЕ трогает другие KB_* —
//  только review. Идемпотентна: повторный запуск не пересоздаёт документ.
// ============================================================
function setupReview() {
  var DOC_NAME = 'KB_claude_review';
  var KEY = 'review';

  var manifest = getBrainManifest_();
  if (!manifest.folder_id) {
    Logger.log('ОШИБКА: в манифесте нет folder_id — сначала запустите setupBrain().');
    return { ok: false, error: 'no_folder' };
  }

  var brain = DriveApp.getFolderById(manifest.folder_id);
  var doc = getOrCreateDoc_(brain, DOC_NAME);  // вернёт существующий, если уже создан
  doc.saveAndClose();
  var id = doc.getId();

  manifest[KEY] = id;
  PropertiesService.getScriptProperties().setProperty(BRAIN_PROP_KEY, JSON.stringify(manifest));

  Logger.log('================ setupReview завершён ================');
  Logger.log(DOC_NAME + ' (' + KEY + '): ' + id);
  Logger.log('BRAIN_MANIFEST: ' + JSON.stringify(manifest));
  return { ok: true, key: KEY, doc: DOC_NAME, id: id };
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

    var text = DocumentApp.openById(id).getBody().getText();
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
 * write_doc — синк git→Drive: перезаписать ТЕЛО существующего KB_-дока новым текстом.
 * Вызывается из doPost (Bridge.gs), поэтому ВОЗВРАЩАЕТ ОБЪЕКТ (не ContentService) —
 * doPost оборачивает через jsonResponse(Object.assign({action}, ...)). Токен уже проверен
 * verifyToken в doPost до switch.
 *
 * body: { name | id, text }. Только перезапись по существующему id из манифеста:
 * не создаёт документы, не меняет манифест/doc_id. Пустой text запрещён (защита от затирки).
 */
function writeDoc_(body) {
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

    var doc = DocumentApp.openById(id);
    var docBody = doc.getBody();
    docBody.clear();            // полная замена тела (как setupBrain), иначе текст допишется
    docBody.setText(text);
    doc.saveAndClose();

    return { ok: true, name: name || null, id: id, chars: text.length };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
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
