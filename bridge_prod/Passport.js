/**
 * Passport.gs — этап B2: OCR паспорта через EdenAI + хранение в Bot Data «паспорта».
 *
 * Поток: splinter качает фото → base64 → uploadPassportPhoto_ (в папку «Паспорта») → file_id →
 *        ocrPassport_(file_id) (EdenAI identity_parser, provider microsoft) → savePassport_ (лист «паспорта»).
 *
 * ГРАНИЦЫ: страну/национальность берём КАК ОТДАЁТ EdenAI (без countryMappings). Паспорт НЕ пишем в CRM
 *          «клиенты» (по дизайну формы — только лист «паспорта» + договор B3). Ключ EdenAI — ТОЛЬКО из
 *          Script Property EDENAI_API_KEY (не хардкод, не в логи). Поля OCR — ПРЕДВАРИТЕЛЬНЫЕ.
 */

var PASSPORT_FOLDER_ID = '1OhIwNe98D5zN6jp51GVTghnFrkd0nRPu';   // папка Drive «Паспорта»
var EDENAI_URL = 'https://api.edenai.run/v2/ocr/identity_parser';

/** Значение поля EdenAI (объект {value}/{name} или строка). */
function ppVal_(f) {
  if (f === null || f === undefined) return '';
  if (typeof f === 'object') return String(f.value || f.name || '').trim();
  return String(f).trim();
}

/** Латиница после '/': "ИВАНОВ/IVANOV" → "IVANOV". Если '/' нет — как есть. */
function ppLatin_(s) {
  s = String(s || '');
  return (s.indexOf('/') >= 0 ? s.split('/').pop() : s).trim();
}

/** Capitalize слова. */
function ppCap_(s) {
  s = String(s || '').trim().toLowerCase();
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
}

/** EdenAI-дата (YYYY-MM-DD / прочее) → dd-MM-yyyy (как форма). Не распарсилось — как есть. */
function ppDate_(s) {
  s = String(s || '').trim();
  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return m[3] + '-' + m[2] + '-' + m[1];
  return s;
}

/**
 * Разобрать ответ EdenAI identity_parser в поля. null, если нет last_name / extracted_data пуст.
 * Страны/национальность — КАК ОТДАЛ EdenAI (без маппинга).
 */
function passportParse_(arr) {
  if (!arr) return null;
  var list = Array.isArray(arr) ? arr : [arr];
  var ms = null;
  for (var i = 0; i < list.length; i++) {
    if (String(list[i].provider || '').toLowerCase() === 'microsoft') { ms = list[i]; break; }
  }
  if (!ms) ms = list[0];                              // фоллбэк на первый провайдер
  if (!ms) return null;
  var ed = ms.extracted_data || [];
  if (!ed.length) return null;
  var d = ed[0];

  var last = ppLatin_(ppVal_(d.last_name));
  if (!last) return null;                             // нет фамилии → распознавание не удалось

  var givenArr = d.given_names || [];
  var given = (Array.isArray(givenArr) ? givenArr : [givenArr])
                .map(function (g) { return ppLatin_(ppVal_(g)); })
                .filter(function (x) { return x; }).join(' ');

  var fullName = (ppCap_(last) + ' ' + given.split(' ').map(ppCap_).join(' ')).trim().replace(/\s+/g, ' ');

  return {
    last_name: last,
    given_names: given,
    full_name: fullName,
    document_id: ppVal_(d.document_id),
    nationality: ppVal_(d.nationality),               // как EdenAI
    country: ppVal_(d.country),                        // как EdenAI (country.value/name)
    birth_date: ppDate_(ppVal_(d.birth_date)),
    expire_date: ppDate_(ppVal_(d.expire_date)),
  };
}

/**
 * Залить фото (base64) в папку «Паспорта». body: { image_b64, filename, mime? }.
 * → { ok, file_id, url }.
 */
function uploadPassportPhoto_(body) {
  var p = body || {};
  try {
    if (!p.image_b64) return { ok: false, error: 'no_image', message: 'image_b64 обязателен' };
    var mime = p.mime || 'image/jpeg';
    var name = String(p.filename || 'passport').replace(/[^\w.\-]+/g, '_').slice(0, 80) + '.jpg';
    var blob = Utilities.newBlob(Utilities.base64Decode(p.image_b64), mime, name);
    var folder = DriveApp.getFolderById(PASSPORT_FOLDER_ID);
    var file = folder.createFile(blob);
    return { ok: true, file_id: file.getId(), url: file.getUrl() };
  } catch (err) {
    return { ok: false, error: 'upload_failed', message: String(err) };
  }
}

/**
 * OCR паспорта через EdenAI. body: { file_id } ИЛИ { image_b64, mime? }.
 * Ключ — из Script Property EDENAI_API_KEY. Страны как EdenAI. Мягкие возвраты (не throw).
 * → { ok:true, fields:{...} } | { ok:false, error:'no_api_key'|'ocr_failed'|'edenai_error', message }.
 */
function ocrPassport_(body) {
  var p = body || {};
  var key = PropertiesService.getScriptProperties().getProperty('EDENAI_API_KEY');
  if (!key) return { ok: false, error: 'no_api_key', message: 'EDENAI_API_KEY не задан в Script Properties' };
  try {
    var blob;
    if (p.file_id) {
      blob = DriveApp.getFileById(p.file_id).getBlob();        // как форма: blob из Drive
    } else if (p.image_b64) {
      blob = Utilities.newBlob(Utilities.base64Decode(p.image_b64), p.mime || 'image/jpeg', 'passport.jpg');
    } else {
      return { ok: false, error: 'no_input', message: 'нужен file_id или image_b64' };
    }
    var resp = UrlFetchApp.fetch(EDENAI_URL, {
      method: 'post',
      headers: { Authorization: 'Bearer ' + key },
      payload: { providers: 'microsoft', file: blob, response_as_dict: 'false', language: 'en' },
      muteHttpExceptions: true,
    });
    var code = resp.getResponseCode();
    var bodyText = resp.getContentText();
    if (code < 200 || code >= 300) {
      return { ok: false, error: 'edenai_error', message: 'HTTP ' + code,
               raw_provider_status: String(bodyText).slice(0, 300) };
    }
    var data;
    try { data = JSON.parse(bodyText); } catch (e) {
      return { ok: false, error: 'edenai_error', message: 'bad JSON', raw_provider_status: String(bodyText).slice(0, 300) };
    }
    var fields = passportParse_(data);
    if (!fields) {
      var st = '';
      try { st = Array.isArray(data) && data[0] ? String(data[0].status || '') : ''; } catch (e) {}
      return { ok: false, error: 'ocr_failed', message: 'паспорт не распознан (нет last_name/extracted_data)',
               raw_provider_status: st };
    }
    return { ok: true, fields: fields };
  } catch (err) {
    return { ok: false, error: 'edenai_error', message: String(err) };
  }
}

/**
 * Сохранить/обновить строку в листе «паспорта» (upsert по booking_key). body:
 *   { booking_key (или bike+name+date_start), bike, name, drive_file_id,
 *     last_name, given_names, full_name, document_id, nationality, country,
 *     birth_date, expire_date, ocr_status }
 * → { ok, row }.
 */
function savePassport_(body) {
  var p = body || {};
  try {
    var key = String(p.booking_key || ((p.bike || '') + '|' + (p.name || '') + '|' + (p.date_start || ''))).trim();
    if (!key || key === '||') return { ok: false, error: 'no_key', message: 'нужен booking_key или bike+name+date_start' };
    var tab = getBotTab_(BOTDATA.TABS.PASSPORT);
    var H = BOTDATA.PASSPORT_HEADERS;
    var rowData = [
      key, p.bike || '', p.name || '', p.drive_file_id || '',
      p.last_name || '', p.given_names || '', p.full_name || '', p.document_id || '',
      p.nationality || '', p.country || '', p.birth_date || '', p.expire_date || '',
      p.ocr_status || '', new Date()
    ];
    var last = tab.getLastRow();
    var rowIdx = -1;
    if (last >= 2) {
      var keys = tab.getRange(2, 1, last - 1, 1).getValues();
      for (var i = 0; i < keys.length; i++) {
        if (String(keys[i][0]) === key) { rowIdx = i + 2; break; }
      }
    }
    if (rowIdx > 0) { tab.getRange(rowIdx, 1, 1, H.length).setValues([rowData]); return { ok: true, row: rowIdx, updated: true }; }
    tab.appendRow(rowData);
    return { ok: true, row: tab.getLastRow(), saved: true };
  } catch (err) {
    return { ok: false, error: 'save_failed', message: String(err) };
  }
}
