/**
 * ContractDoor.gs — дверь договоров TB e-Sign (CONTRACTDOOR0310, 03.10.2026). ТОЛЬКО ЧТЕНИЕ.
 *
 * contract_find — подписанные договоры аренды из реестра подписей «Договоры — реестр подписей
 *   (TB e-Sign)», лист «Реестр», по телефону (последние 9 цифр), имени, байку и сроку.
 * contract_pdf  — подписанный PDF по id файла: только если id стоит в колонке «PDF (подписанный)»
 *   реестра, строка подписана и файл лежит в папке подписанных.
 *
 * Адреса реестра и папки в коде НЕ лежат: их берёт Script Properties проекта
 * (ESIGN_REGISTRY_ID, ESIGN_SIGNED_FOLDER_ID — тот же приём, что BOT_DATA_SHEET_ID в BotData.js).
 * Свойство не задано → названный отказ, а не пустой ответ.
 *
 * Колонки ищутся ПО ИМЕНИ заголовка (строка 1), а не по позиции: код TB e-Sign живёт вне проекта,
 * порядок колонок отсюда не проверить. Нужной колонки нет → отказ no_column с перечнем.
 *
 * Подписанным считается РОВНО статус «ПОДПИСАН» (без учёта регистра и пробелов). Всё прочее
 * («ОТПРАВЛЕН», «ОТОЗВАН», «ПОДПИСАН ЧАСТИЧНО» …) отдаётся как есть и подписанным не считается.
 * Несколько подписанных под фильтр — исход «ambiguous» (неизвестно), а не первый попавшийся.
 * Подписанный под фильтр без известного дня при заданном сроке — исход «incomplete»: ответ НЕ полон,
 * договора не выбираем (CONTRACTFIX0410, контрпример Codex TB-CHECK-0410-0025 п.1).
 *
 * Ни одной записи: ни в лист, ни в Drive, ни в свойства (проверяет харнесс счётчиком записей).
 */

var ESIGN = {
  REGISTRY_PROP: 'ESIGN_REGISTRY_ID',
  SIGNED_FOLDER_PROP: 'ESIGN_SIGNED_FOLDER_ID',
  SHEET: 'Реестр',
  SIGNED_STATUS: 'ПОДПИСАН',
  FIND_LIMIT_DEFAULT: 20,
  FIND_LIMIT_MAX: 100,
  PDF_MAX_BYTES: 15 * 1024 * 1024,
  PHONE_DIGITS: 9,
  // ключ → имя заголовка в реестре (П1 Штаба 03.10.2026)
  COLS: {
    doc_id: 'ID документа',
    client: 'Клиент',
    contract_date: 'Дата договора',
    status: 'Статус',
    created: 'Документ создан',
    signed_at: 'Подписан',
    pdf: 'PDF (подписанный)',
    nick: 'Ник (Social contact)',
    phone: 'Телефон',
    bike: 'Байк',
  },
  // без этих колонок дверь не судит
  NEED: ['client', 'contract_date', 'status', 'signed_at', 'pdf', 'phone', 'bike'],
};


function esignNorm_(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/[«»"'“”]/g, '').replace(/ё/g, 'е').replace(/Ё/g, 'Е')
    .replace(/\s+/g, ' ').trim().toLowerCase();
}

function esignTz_() {
  try { return Session.getScriptTimeZone() || 'Asia/Bangkok'; } catch (e) { return 'Asia/Bangkok'; }
}

/** Такой день есть в календаре (31.02 — нет, 29.02 — только в високосный год). */
function esignCalendar_(y, mo, d) {
  var dt = new Date(Date.UTC(y, mo - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d;
}

/**
 * День ячейки → 'YYYY-MM-DD' или ''. Date, 'YYYY-MM-DD[ …]', 'DD.MM.YYYY[ …]'. День отдаётся ТОЛЬКО
 * для верной календарной даты: «31.02.2026» → '', а не «2026-02-31» (CONTRACTFIX0410).
 */
function esignDay_(v, tz) {
  if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, tz, 'yyyy-MM-dd');
  var s = String(v === null || v === undefined ? '' : v).trim();
  var y, mo, d;
  var m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|[ T])/);
  if (m) { y = m[1]; mo = m[2]; d = m[3]; }
  else {
    m = s.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})(?:$|[ ,])/);
    if (!m) return '';
    y = m[3]; mo = ('0' + m[2]).slice(-2); d = ('0' + m[1]).slice(-2);
  }
  return esignCalendar_(+y, +mo, +d) ? y + '-' + mo + '-' + d : '';
}

/** Фильтр срока: '' → null (не задан), иначе 'YYYY-MM-DD' или false (не разобран / нет в календаре). */
function esignQueryDay_(v) {
  var s = String(v === null || v === undefined ? '' : v).trim();
  if (!s) return null;
  return esignDay_(s, 'UTC') || false;
}

/**
 * Дата строки реестра (CONTRACTFIX0410). Исходные значения хранятся как есть: raw — «Дата договора»,
 * created_raw — «Документ создан» (Date → 'yyyy-MM-dd HH:mm', строка — как лежит). День — только
 * при верной календарной дате. «Документ создан» подставляется ТОЛЬКО при ПУСТОЙ ячейке даты
 * договора: непустая, но не разобранная дата договора → day null, src 'unparsed', created не берётся.
 * → { day: 'YYYY-MM-DD'|null, src: 'contract_date'|'created'|'unparsed'|'none', raw, created_raw }
 *   unparsed — правящая ячейка (дата договора, а при пустой — «Документ создан») непуста, но не дата;
 *   none — обе пусты (или колонки «Документ создан» нет).
 */
function esignRowDate_(r, c, tz) {
  var raw = esignStamp_(r[c.contract_date], tz);
  var createdRaw = c.created !== undefined ? esignStamp_(r[c.created], tz) : '';
  var out = { day: null, src: 'none', raw: raw, created_raw: createdRaw };
  if (raw) {
    var d = esignDay_(r[c.contract_date], tz);
    out.day = d || null;
    out.src = d ? 'contract_date' : 'unparsed';
  } else if (createdRaw) {
    var dc = esignDay_(r[c.created], tz);
    out.day = dc || null;
    out.src = dc ? 'created' : 'unparsed';
  }
  return out;
}

/** Момент подписи → 'YYYY-MM-DD HH:mm' (Date) или строка как есть. */
function esignStamp_(v, tz) {
  if (v instanceof Date && !isNaN(v.getTime())) return Utilities.formatDate(v, tz, 'yyyy-MM-dd HH:mm');
  return String(v === null || v === undefined ? '' : v).trim();
}

/** id файла Drive из ссылки, формулы HYPERLINK или голого id; иначе ''. */
function esignFileId_(text) {
  var s = String(text === null || text === undefined ? '' : text).trim();
  if (!s) return '';
  var m = s.match(/\/d\/([-\w]{25,})/) || s.match(/[?&]id=([-\w]{25,})/);
  if (m) return m[1];
  return /^[-\w]{25,}$/.test(s) ? s : '';
}

/** Последние 9 цифр каждого номера в ячейке (номера делятся , ; / | и переводом строки). */
function esignPhones_(cell) {
  var out = [];
  String(cell === null || cell === undefined ? '' : cell).split(/[,;\/|\n]+/).forEach(function (piece) {
    var d = piece.replace(/\D/g, '');
    if (d.length >= ESIGN.PHONE_DIGITS) out.push(d.slice(-ESIGN.PHONE_DIGITS));
  });
  return out;
}

function esignWords_(s) {
  return esignNorm_(s).replace(/[^0-9a-zа-я]+/g, ' ').trim().split(' ').filter(Boolean);
}

/** Каждое слово запроса — слово имени либо (от 3 букв) его начало. Порядок слов не важен. */
function esignNameMatch_(qWords, client) {
  var words = esignWords_(client);
  return qWords.every(function (q) {
    return words.some(function (w) { return w === q || (q.length >= 3 && w.indexOf(q) === 0); });
  });
}

function esignIsSigned_(status) {
  return esignNorm_(status).toUpperCase() === ESIGN.SIGNED_STATUS;
}

/**
 * Открыть реестр. → { ok, data, pdfIds, col, headers, unread } или { ok:false, error, … }.
 * pdfIds[i] — id файла из колонки PDF строки i: значение, ссылка богатого текста, формула.
 * unread — что прочитать НЕ удалось (реестр прочитан не целиком): 'rows_short' — строк меньше,
 * чем в листе; 'pdf_rich_text' / 'pdf_formulas' — ссылки PDF богатым текстом / формулой не читались.
 */
function esignRegistry_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty(ESIGN.REGISTRY_PROP);
  if (!id) return { ok: false, error: 'no_registry_config',
    message: 'Script Property ' + ESIGN.REGISTRY_PROP + ' не задан — реестр не открывался' };
  var ss;
  try { ss = SpreadsheetApp.openById(id); }
  catch (e) { return { ok: false, error: 'registry_unreadable', message: String(e && e.message || e) }; }
  var sh = ss.getSheetByName(ESIGN.SHEET);
  if (!sh) return { ok: false, error: 'no_registry_sheet', message: 'нет листа «' + ESIGN.SHEET + '»' };
  var lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  if (lastRow < 1 || lastCol < 1) return { ok: false, error: 'no_column', missing: ESIGN.NEED.slice(), headers: [] };
  var headers = sh.getRange(1, 1, 1, lastCol).getValues()[0].map(function (h) { return String(h); });
  var byName = {};
  headers.forEach(function (h, i) { var k = esignNorm_(h); if (k && !(k in byName)) byName[k] = i; });
  var col = {};
  Object.keys(ESIGN.COLS).forEach(function (k) {
    var i = byName[esignNorm_(ESIGN.COLS[k])];
    if (i !== undefined) col[k] = i;
  });
  var missing = ESIGN.NEED.filter(function (k) { return !(k in col); });
  if (missing.length) return { ok: false, error: 'no_column',
    missing: missing.map(function (k) { return ESIGN.COLS[k]; }), headers: headers };
  var n = lastRow - 1, unread = [];
  var data = n > 0 ? sh.getRange(2, 1, n, lastCol).getValues() : [];
  if (data.length < n) unread.push('rows_short');
  var pdfIds = data.map(function (r) { return esignFileId_(r[col.pdf]); });
  if (n > 0) {
    var rng = sh.getRange(2, col.pdf + 1, n, 1);
    var rich = null, frm = null;
    try { rich = rng.getRichTextValues(); } catch (e) { rich = null; unread.push('pdf_rich_text'); }
    try { frm = rng.getFormulas(); } catch (e) { frm = null; unread.push('pdf_formulas'); }
    for (var i = 0; i < data.length; i++) {
      if (pdfIds[i]) continue;
      var link = rich && rich[i] && rich[i][0] && rich[i][0].getLinkUrl ? rich[i][0].getLinkUrl() : '';
      pdfIds[i] = esignFileId_(link) || esignFileId_(frm && frm[i] ? frm[i][0] : '');
    }
  }
  return { ok: true, data: data, pdfIds: pdfIds, col: col, headers: headers, unread: unread };
}


/**
 * READ-ONLY: договоры клиента в реестре подписей.
 * payload: { phone, name, bike, date_from, date_to, limit }
 *   phone — последние 9 цифр (меньше 9 цифр → bad_phone); ищется в «Телефон» и «Ник (Social contact)»;
 *   name  — слова имени в любом порядке (ни одного слова от 2 букв → bad_name);
 *   bike  — по НОМЕРУ (plateOf_, тот же резолв, что read_events/tx_find); без номера → bad_bike;
 *   date_from/date_to — включительно, по «Дата договора»; «Документ создан» — ТОЛЬКО при пустой ячейке
 *   даты договора (источник дня — date_src, исходные значения — contract_date_raw / created_raw).
 * Нужен хотя бы один из phone/name/bike, иначе no_filter: реестр целиком дверь не выгружает.
 * → { ok, outcome: one|ambiguous|incomplete|none_signed|none, pick, reason, items[], undated_items[],
 *     checked{…, undated, undated_signed, date_unparsed, unread[], complete}, filter, limit, limit_max }
 *
 * Запись договора (items, undated_items, pick): row, doc_id, client, contract_date ('YYYY-MM-DD' или
 * null — день неизвестен), contract_date_raw, created_raw, date_src (contract_date|created|unparsed|
 * none), status, signed, signed_at, bike, phone, pdf_id, matched_on; у pick сверху pdf_ready.
 *
 * Срок задан, а день строки неизвестен (date_src unparsed/none) → строка НЕ выпадает молча: она в
 * undated_items и в счёте checked.undated. Среди таких есть подходящий ПОДПИСАННЫЙ → outcome
 * incomplete, pick null, reason {code:'undated_signed', rows, message}: был ли он в сроке, не знает
 * никто, а значит «ровно один» / «нет» утверждать нельзя. Порядок исходов: ambiguous (в сроке
 * подписанных больше одного — это верно при любом неизвестном) > incomplete > none / none_signed / one.
 * Без срока неизвестный день строку не исключает. checked.complete = false, если есть строки с
 * неизвестным днём при сроке или реестр прочитан не целиком (checked.unread).
 */
function contractFind(payload) {
  var p = payload || {};
  var phoneIn = String(p.phone || '').trim(), nameIn = String(p.name || '').trim(), bikeIn = String(p.bike || '').trim();
  var phone = '', qWords = [], plate = '';
  if (phoneIn) {
    var d = phoneIn.replace(/\D/g, '');
    if (d.length < ESIGN.PHONE_DIGITS) return { ok: false, error: 'bad_phone',
      message: 'в телефоне меньше ' + ESIGN.PHONE_DIGITS + ' цифр' };
    phone = d.slice(-ESIGN.PHONE_DIGITS);
  }
  if (nameIn) {
    qWords = esignWords_(nameIn).filter(function (w) { return w.length >= 2; });
    if (!qWords.length) return { ok: false, error: 'bad_name', message: 'в имени нет слова от 2 букв' };
  }
  if (bikeIn) {
    plate = plateOf_(bikeIn);
    if (!plate) return { ok: false, error: 'bad_bike', message: 'в названии байка нет номера' };
  }
  if (!phone && !qWords.length && !plate) return { ok: false, error: 'no_filter',
    message: 'нужен телефон, имя или байк — реестр целиком не выгружается' };
  var from = esignQueryDay_(p.date_from), to = esignQueryDay_(p.date_to);
  if (from === false || to === false) return { ok: false, error: 'bad_date', message: 'срок: YYYY-MM-DD или DD.MM.YYYY' };
  if (from && to && from > to) return { ok: false, error: 'bad_span', message: 'date_from позже date_to' };
  var limit = parseInt(p.limit, 10);
  if (!(limit > 0)) limit = ESIGN.FIND_LIMIT_DEFAULT;
  if (limit > ESIGN.FIND_LIMIT_MAX) limit = ESIGN.FIND_LIMIT_MAX;

  var reg = esignRegistry_();
  if (!reg.ok) return reg;
  var tz = esignTz_(), c = reg.col, data = reg.data;
  var matched = [], aside = [], unparsed = 0, minDay = '', maxDay = '';
  for (var i = 0; i < data.length; i++) {
    var r = data[i];
    var dt = esignRowDate_(r, c, tz), day = dt.day;
    if (day) { if (!minDay || day < minDay) minDay = day; if (!maxDay || day > maxDay) maxDay = day; }
    var on = [];
    if (phone) {
      if (esignPhones_(r[c.phone]).indexOf(phone) >= 0) on.push('phone');
      else if (c.nick !== undefined && esignPhones_(r[c.nick]).indexOf(phone) >= 0) on.push('nick');
      else continue;
    }
    if (qWords.length) { if (!esignNameMatch_(qWords, r[c.client])) continue; on.push('name'); }
    if (plate) { if (plateOf_(String(r[c.bike] || '')) !== plate) continue; on.push('bike'); }
    if (dt.src === 'unparsed') unparsed++;
    var rec = {
      row: i + 2,
      doc_id: c.doc_id !== undefined ? String(r[c.doc_id] || '') : '',
      client: String(r[c.client] || ''),
      contract_date: day,
      contract_date_raw: dt.raw,
      created_raw: dt.created_raw,
      date_src: dt.src,
      status: String(r[c.status] || ''),
      signed: esignIsSigned_(r[c.status]),
      signed_at: esignStamp_(r[c.signed_at], tz),
      bike: String(r[c.bike] || ''),
      phone: String(r[c.phone] || ''),
      pdf_id: reg.pdfIds[i],
      matched_on: on,
    };
    if (from || to) {
      // день неизвестен — в срок строку не судим, но и не выбрасываем молча (CONTRACTFIX0410)
      if (!day) { aside.push(rec); continue; }
      if (from && day < from) continue;
      if (to && day > to) continue;
    }
    matched.push(rec);
  }
  var desc = function (a, b) { return b.row - a.row; };
  matched.sort(desc);
  aside.sort(desc);
  var signed = matched.filter(function (x) { return x.signed; });
  var asideSigned = aside.filter(function (x) { return x.signed; });
  var unread = reg.unread || [];
  var outcome, pick = null, reason = null;
  if (asideSigned.length && signed.length <= 1) {
    outcome = 'incomplete';
    reason = { code: 'undated_signed', rows: asideSigned.map(function (x) { return x.row; }),
      message: 'подписанный договор под фильтр без известного дня — в сроке ли он, неизвестно; ' +
        'выбрать один договор нельзя, нужен человек' };
  }
  else if (!matched.length) outcome = 'none';
  else if (!signed.length) outcome = 'none_signed';
  else if (signed.length > 1) outcome = 'ambiguous';
  else {
    outcome = 'one';
    pick = Object.assign({}, signed[0], { pdf_ready: !!signed[0].pdf_id });
  }
  var items = matched.slice(0, limit);
  var undatedItems = aside.slice(0, limit);
  return {
    ok: true,
    outcome: outcome,
    pick: pick,
    reason: reason,
    items: items,
    undated_items: undatedItems,
    checked: {
      sheet: ESIGN.SHEET,
      rows_scanned: data.length,
      span_from: from || minDay,
      span_to: to || maxDay,
      undated: aside.length,
      undated_signed: asideSigned.length,
      date_unparsed: unparsed,
      unread: unread,
      complete: !aside.length && !unread.length,
      matched: matched.length,
      signed: signed.length,
      returned: items.length,
      truncated: matched.length > items.length,
    },
    filter: { phone_last9: phone, name: nameIn, bike: bikeIn, plate: plate, date_from: from || '', date_to: to || '' },
    limit: limit,
    limit_max: ESIGN.FIND_LIMIT_MAX,
  };
}


function esignHex_(bytes) {
  return bytes.map(function (b) { return ('0' + ((b < 0 ? b + 256 : b) & 0xff).toString(16)).slice(-2); }).join('');
}

/**
 * READ-ONLY: подписанный PDF по id файла Drive.
 * Отдаёт файл, только если: id стоит в колонке «PDF (подписанный)» реестра · строка «ПОДПИСАН» ·
 * файл не в корзине · лежит в папке подписанных (ESIGN_SIGNED_FOLDER_ID) · это PDF · не больше потолка.
 * Иначе — отказ с причиной. payload: { id } → { ok, id, name, mime, size, sha256, content_b64, row, … }
 */
function contractPdf(payload) {
  var id = String((payload || {}).id || '').trim();
  if (!/^[-\w]{25,}$/.test(id)) return { ok: false, error: 'bad_id', message: 'id файла Drive — от 25 знаков [A-Za-z0-9_-]' };
  var folderId = PropertiesService.getScriptProperties().getProperty(ESIGN.SIGNED_FOLDER_PROP);
  if (!folderId) return { ok: false, error: 'no_signed_folder_config',
    message: 'Script Property ' + ESIGN.SIGNED_FOLDER_PROP + ' не задан — папка подписанных не известна' };
  var reg = esignRegistry_();
  if (!reg.ok) return reg;
  var rows = [];
  for (var i = 0; i < reg.pdfIds.length; i++) if (reg.pdfIds[i] === id) rows.push(i);
  if (!rows.length) return { ok: false, error: 'not_in_registry',
    message: 'id нет в колонке «' + ESIGN.COLS.pdf + '» реестра', checked: { rows_scanned: reg.data.length } };
  var c = reg.col;
  var signedRows = rows.filter(function (i) { return esignIsSigned_(reg.data[i][c.status]); });
  if (!signedRows.length) return { ok: false, error: 'not_signed',
    message: 'строка реестра не «' + ESIGN.SIGNED_STATUS + '»',
    rows: rows.map(function (i) { return { row: i + 2, status: String(reg.data[i][c.status] || '') }; }) };
  var ri = signedRows[0], tz = esignTz_();
  var file;
  try { file = DriveApp.getFileById(id); }
  catch (e) { return { ok: false, error: 'file_unreadable', message: String(e && e.message || e) }; }
  if (file.isTrashed()) return { ok: false, error: 'trashed', message: 'файл в корзине' };
  var inFolder = false, parents = file.getParents();
  while (parents.hasNext()) { if (parents.next().getId() === folderId) { inFolder = true; break; } }
  if (!inFolder) return { ok: false, error: 'not_in_signed_folder', message: 'файл лежит не в папке подписанных' };
  var mime = String(file.getMimeType() || '');
  if (mime !== 'application/pdf') return { ok: false, error: 'not_pdf', mime: mime };
  var size = file.getSize();
  if (size > ESIGN.PDF_MAX_BYTES) return { ok: false, error: 'too_large', size: size, max: ESIGN.PDF_MAX_BYTES };
  var bytes = file.getBlob().getBytes();
  return {
    ok: true,
    id: id,
    name: file.getName(),
    mime: mime,
    size: bytes.length,
    sha256: esignHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)),
    content_b64: Utilities.base64Encode(bytes),
    row: ri + 2,
    client: String(reg.data[ri][c.client] || ''),
    contract_date: esignDay_(reg.data[ri][c.contract_date], tz),
    signed_at: esignStamp_(reg.data[ri][c.signed_at], tz),
  };
}
