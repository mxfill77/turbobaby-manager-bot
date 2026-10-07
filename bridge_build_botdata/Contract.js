/**
 * Contract.gs — этап B3: генерация договора аренды из шаблона.
 *
 * makeContract_: джойн «паспорта» (OCR, B2) + строка CRM «клиенты» (бронь, B1) по name+date_start →
 * расчёт сборов (DF по району, TH/Cost of hire из computed CRM, CT) → makeCopy шаблона → replaceText 26
 * плейсхолдеров → сохранить в папку договоров → вернуть URL.
 *
 * ТОЛЬКО ЧИТАЕТ CRM (не пишет). Пишет ТОЛЬКО Drive-файл. Поля выдачи/адреса/нет-данных → прочерк «—».
 * Страны/паспорт как в листе «паспорта» (EdenAI, без countryMappings). Депозит-паспорт деньгами НЕ плюсуем.
 */

var CONTRACT_TEMPLATE_ID = '1Hh2GlpxJsa4DplbKYaM1X0Nt6DLCWYQb6znWcG61tOE';
var CONTRACT_FOLDER_ID = '1GX7SIqoskzSuThS4e4EbjeX-B0N_CKxK';
var DASH = '—';

// Галка v1: дефолты + пороги авто-KM (именованные константы).
var PBT_DEFAULT = '12:00';     // время выдачи/возврата по умолчанию (одно поле %Pbt%)
var KM_TOLERANCE = 5;          // |mileage возврата − current_km| ≤ 5 км → «не ездил»
var KM_MAX_AGE_DAYS = 14;      // одометр снят ≤ 14 дней назад → свежий

// Тариф доставки по району (KB, подтверждён штабом). Севернее аэропорта/не распознан → null (прочерк).
var DF_TARIFF = [
  [['patong', 'bangtao', 'bang tao', 'surin', 'kamala'], 290],
  [['karon', 'paklok', 'pa klok'], 390],
  [['kata', 'katu'], 490],
  [['rawai', 'naiharn', 'nai harn', 'chalong'], 590],
  [['airport', 'аэропорт'], 690],
];

/** DF из note(V): район после «доставка:». Самовывоз → 0; не распознан/севернее → null (прочерк). */
function contractDeliveryFee_(note) {
  var m = String(note || '').toLowerCase();
  var dm = m.match(/доставка:\s*([^|]+)/);
  var area = (dm ? dm[1] : m).trim();
  if (/самовывоз|self|pickup|забер/.test(area)) return 0;
  for (var i = 0; i < DF_TARIFF.length; i++) {
    for (var j = 0; j < DF_TARIFF[i][0].length; j++) {
      if (area.indexOf(DF_TARIFF[i][0][j]) >= 0) return DF_TARIFF[i][1];
    }
  }
  return null;
}

/** Телефоны (+/цифры, ≥7) из U. → [tel1, tel2]. */
function contractPhones_(u) {
  var hits = String(u || '').match(/\+?\d[\d\s\-]{6,}\d/g) || [];
  hits = hits.map(function (s) { return s.trim(); });
  return [hits[0] || DASH, hits[1] || DASH];
}

/** @-хэндл из U (или вся строка U, если хэндла нет). */
function contractSocial_(u) {
  var m = String(u || '').match(/@[\w.]+/);
  return m ? m[0] : (String(u || '').trim() || DASH);
}

/** Экранировать спецсимволы regex для replaceText (плейсхолдеры с . и ' ). */
function contractEsc_(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Матчер модели байка → каноничный ключ вкладки стоимость_моделей. ПОРЯДОК ВАЖЕН
// (XADV до ADV; CBR до CB; CB650 и CB300 различать). Кириллич. «СС» → «CC» нормализуется.
var COST_MODEL_RULES = [
  [/\bCBR\s*650/, 'CBR 650R'],
  [/\bCB\s*650/, 'CB 650R'],
  [/\bCB\s*300/, 'CB 300R'],
  [/\bXADV\s*750/, 'XADV 750'],
  [/\bADV\s*350/, 'ADV 350'],
  [/\bNMAX\s*155/, 'NMAX 155'],
  [/\bXSR\s*155/, 'XSR 155'],
  [/\bFORZA\s*300/, 'FORZA 300'],
  [/\bMT[-\s]*03\s*300/, 'MT-03 300'],
  [/\bXMAX\s*300/, 'XMAX 300'],
  [/\bNINJA\s*400/, 'NINJA 400'],
  [/\bVULCAN\s*650/, 'VULCAN 650'],
];

/** Имя байка (C/resolved) → каноничный ключ модели; null если ни одна из 12 моделей не подошла. */
function costModelKey_(bikeName) {
  var s = String(bikeName || '').toUpperCase().replace(/С/g, 'C').replace(/\s+/g, ' ');  // кириллич. С→C
  for (var i = 0; i < COST_MODEL_RULES.length; i++) {
    if (COST_MODEL_RULES[i][0].test(s)) return COST_MODEL_RULES[i][1];
  }
  return null;
}

/** %Cost of vehicle% из вкладки стоимость_моделей по ключу модели; DASH если модель/значение не найдены. */
function costModelLookup_(bikeName) {
  var key = costModelKey_(bikeName);
  if (!key) return DASH;
  var tab = getBotTab_(BOTDATA.TABS.COST_MODELS);
  var last = tab.getLastRow();
  if (last < 2) return DASH;
  var data = tab.getRange(2, 1, last - 1, 2).getValues();
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][0]).trim().toUpperCase() === key.toUpperCase()) {
      var v = data[i][1];
      return (v === '' || v == null) ? DASH : String(v);
    }
  }
  return DASH;
}

/** Нормализовать дату к dd-MM-yyyy (Sheets хранит E как Date, паспорт — строкой). */
function normalizeDate_(v) {
  if (v === null || v === undefined || v === '') return '';
  if (Object.prototype.toString.call(v) === '[object Date]' && !isNaN(v)) {
    return ('0' + v.getDate()).slice(-2) + '-' + ('0' + (v.getMonth() + 1)).slice(-2) + '-' + v.getFullYear();
  }
  var s = String(v).trim();
  var m = s.match(/^(\d{1,2})[-.\/](\d{1,2})[-.\/](\d{4})/);          // dd-MM-yyyy / dd.MM.yyyy
  if (m) return ('0' + m[1]).slice(-2) + '-' + ('0' + m[2]).slice(-2) + '-' + m[3];
  m = s.match(/^(\d{4})[-.\/](\d{1,2})[-.\/](\d{1,2})/);              // yyyy-MM-dd
  if (m) return ('0' + m[3]).slice(-2) + '-' + ('0' + m[2]).slice(-2) + '-' + m[1];
  return s;
}

/** Значение (Date/строка) → объект Date (через normalizeDate_); null если не распарсилось. */
function toDateObj_(v) {
  if (Object.prototype.toString.call(v) === '[object Date]' && !isNaN(v)) return v;
  var s = normalizeDate_(v);
  var m = String(s).match(/^(\d{2})-(\d{2})-(\d{4})$/);   // dd-MM-yyyy
  return m ? new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1])) : null;
}

/** Календарных дней между E и F (>0) или 0, если не распарсилось. */
function daysBetween_(startRaw, endRaw) {
  var a = toDateObj_(startRaw), b = toDateObj_(endRaw);
  if (!a || !b) return 0;
  var d = Math.round((b - a) / 86400000);
  return d > 0 ? d : 0;
}

/** Дни аренды: из срока G «N Д» (int), иначе F−E. 0 если не вышло. */
function durationDays_(g, startRaw, endRaw) {
  var m = String(g || '').match(/(\d+)\s*[ДD]/i);   // «N Д» (кириллич. Д / лат. D)
  if (m) return parseInt(m[1], 10);
  return daysBetween_(startRaw, endRaw);
}

/** Месяцы аренды: из срока G «N М» (int), иначе round((F−E)/30). 0 если не вышло. */
function durationMonths_(g, startRaw, endRaw) {
  var m = String(g || '').match(/(\d+)\s*[МM]/i);   // «N М» (кириллич. М / лат. M)
  if (m) return parseInt(m[1], 10);
  var d = daysBetween_(startRaw, endRaw);
  return d > 0 ? Math.round(d / 30) : 0;
}

/** Район доставки из note («доставка: <район>»); самовывоз/нет → DASH. Для %Pickup/Return address%. */
function contractDeliveryArea_(note) {
  var m = String(note || '').match(/доставка:\s*([^|]+)/i);
  if (!m) return DASH;
  var a = m[1].trim();
  if (!a || /самовывоз|self|pickup|забер/i.test(a)) return DASH;
  return a;
}

/** Авто-KM (Галка v1): {value, status}. «ok» (ставим current_km) ТОЛЬКО если ВСЁ:
 *  ДОМА + последнее событие с пробегом = возврат + |mileage−current_km|≤5 + одометр снят ≤14 дн.
 *  Иначе «request» (под запрос — человек подтверждает; свежий OCR на лету НЕ делаем). */
function autoKm_(bike) {
  try {
    var plate = plateFromName_(bike);
    if (!plate) return { value: null, status: 'request' };
    // 1) подтверждённый одометр из «обслуживание» (свежайший по updated_at)
    var items = (serviceList({}) || {}).items || [];
    var curKm = null, odoAt = null;
    for (var i = 0; i < items.length; i++) {
      if (plateFromName_(String(items[i].bike || '')) !== plate) continue;
      var ck = Number(items[i].current_km);
      var ua = new Date(items[i].updated_at);
      if (isFinite(ck) && ck > 0 && !isNaN(ua) && (odoAt === null || ua > odoAt)) { curKm = ck; odoAt = ua; }
    }
    if (curKm === null || odoAt === null) return { value: null, status: 'request' };
    if ((new Date() - odoAt) / 86400000 > KM_MAX_AGE_DAYS) return { value: null, status: 'request' };
    // 2) байк ДОМА
    var bikes = (getFleetStatus().bikes) || [];
    var fb = null;
    for (var k = 0; k < bikes.length; k++) { if (plateFromName_(bikes[k].name) === plate) { fb = bikes[k]; break; } }
    if (!fb || String(fb.status).toUpperCase().indexOf('ДОМА') < 0) return { value: null, status: 'request' };
    // 3) последнее событие с пробегом = возврат, mileage ≈ curKm
    var evs = (readEvents({ bike: bike, limit: 5 }) || {}).items || [];
    for (var e = 0; e < evs.length; e++) {
      if (String(evs[e].mileage || '') === '') continue;
      if (String(evs[e].event_type || '').toLowerCase() !== 'return') return { value: null, status: 'request' };
      var lm = Number(String(evs[e].mileage).replace(/[^\d.]/g, ''));
      if (isFinite(lm) && Math.abs(lm - curKm) > KM_TOLERANCE) return { value: null, status: 'request' };
      break;
    }
    return { value: curKm, status: 'ok' };
  } catch (e) { return { value: null, status: 'request' }; }
}

/** Маппинг договоров: запись по ключу (booking_id или фоллбэк nd:name|date). null если нет. */
function contractMapGet_(key) {
  var tab = getBotTab_(BOTDATA.TABS.CONTRACTS);
  var last = tab.getLastRow();
  if (last < 2) return null;
  var data = tab.getRange(2, 1, last - 1, BOTDATA.CONTRACTS_HEADERS.length).getValues();
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][0]) === String(key)) return { row: i + 2, file_id: String(data[i][1] || '') };
  }
  return null;
}

/** Upsert маппинга «договоры» (booking_id|file_id|name|bike|created_at|updated_at). */
function contractMapSet_(key, fileId, name, bike) {
  var tab = getBotTab_(BOTDATA.TABS.CONTRACTS);
  var ex = contractMapGet_(key);
  var now = new Date();
  if (ex) {
    tab.getRange(ex.row, 2).setValue(fileId);
    tab.getRange(ex.row, 6).setValue(now);
  } else {
    tab.appendRow([key, fileId, name || '', bike || '', now, now]);
  }
}

/** Regen вар.A: открыть СУЩЕСТВУЮЩИЙ Doc → очистить тело → скопировать тело ШАБЛОНА → replaceText.
 *  Сохраняет file_id/URL. Бросает, если файл недоступен (caller создаст новый). */
function fillContractDoc_(docId, R) {
  var doc = DocumentApp.openById(docId);
  var body = doc.getBody();
  body.clear();
  var tmpl = DocumentApp.openById(CONTRACT_TEMPLATE_ID).getBody();
  var n = tmpl.getNumChildren();
  for (var i = 0; i < n; i++) {
    var el = tmpl.getChild(i).copy();
    var t = el.getType();
    if (t === DocumentApp.ElementType.PARAGRAPH) body.appendParagraph(el.asParagraph());
    else if (t === DocumentApp.ElementType.TABLE) body.appendTable(el.asTable());
    else if (t === DocumentApp.ElementType.LIST_ITEM) body.appendListItem(el.asListItem());
  }
  // убрать ведущий пустой параграф, оставшийся от clear()
  if (body.getNumChildren() > n) {
    var first = body.getChild(0);
    if (first.getType() === DocumentApp.ElementType.PARAGRAPH && first.asParagraph().getText() === '') first.removeFromParent();
  }
  Object.keys(R).forEach(function (key) { body.replaceText('%' + contractEsc_(key) + '%', String(R[key])); });
  doc.saveAndClose();
}

function makeContract_(body) {
  var p = body || {};
  try {
    // --- ключ: booking_id (кол.Y, предпочтительно) ЛИБО name+date_start (booking_key/явные поля) ---
    var name = p.name, dateStart = p.date_start;
    if (p.booking_key) {
      var parts = String(p.booking_key).split('|');
      if (!name) name = (parts[1] || '');
      if (!dateStart) dateStart = (parts[2] || '');
    }
    var wantId = String(p.booking_id || '').trim();
    name = String(name || '').trim();
    dateStart = String(dateStart || '').trim();
    var nameL = name.toLowerCase();
    var dsN = normalizeDate_(dateStart);
    if (!wantId && (!name || !dateStart)) {
      return { ok: false, error: 'no_key', message: 'нужны booking_id ЛИБО booking_key/name+date_start' };
    }

    // --- 1) строка CRM «клиенты»: по booking_id (Y) или name+date. Читаем 25 кол (A..Y). ---
    var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
    var sheet = ss.getSheetByName(BOOKING.SHEET);
    if (!sheet) return { ok: false, error: 'sheet_not_found', message: BOOKING.SHEET };
    var crow = null;
    var clast = sheet.getLastRow();
    if (clast >= 2) {
      var cdata = sheet.getRange(2, 1, clast - 1, 25).getValues();   // A..Y (вкл. booking_id)
      for (var j = 0; j < cdata.length; j++) {
        if (wantId) {
          if (String(cdata[j][24] || '').trim() === wantId) { crow = cdata[j]; break; }
        } else {
          var dnm = String(cdata[j][3] || '').trim();
          if (dnm.toLowerCase() === nameL && normalizeDate_(cdata[j][4]) === dsN) { crow = cdata[j]; break; }
        }
      }
    }
    if (!crow) return { ok: false, error: 'no_booking',
                        message: wantId ? 'бронь по booking_id не найдена' : 'строка брони CRM по name+date не найдена' };

    // имя/дата/байк берём из найденной строки (booking_id-путь их и задаёт)
    name = String(crow[3] || '').trim(); nameL = name.toLowerCase();
    dsN = normalizeDate_(crow[4]);
    var bookingId = String(crow[24] || '').trim();    // Y — может быть пусто у старых броней (фоллбэк-ключ ниже)

    // --- 2) строка «паспорта» по name + date ---
    var ptab = getBotTab_(BOTDATA.TABS.PASSPORT);
    var pH = BOTDATA.PASSPORT_HEADERS;
    var pass = null;
    var plast = ptab.getLastRow();
    if (plast >= 2) {
      var pdata = ptab.getRange(2, 1, plast - 1, pH.length).getValues();
      for (var i = 0; i < pdata.length; i++) {
        var bk = String(pdata[i][0] || '');                 // booking_key
        var pname = String(pdata[i][2] || '').trim();       // name (col3)
        var bkDate = (bk.split('|')[2] || '').trim();
        if (pname.toLowerCase() === nameL && normalizeDate_(bkDate) === dsN) {
          pass = {}; pH.forEach(function (h, idx) { pass[h] = pdata[i][idx]; });
          break;
        }
      }
    }
    if (!pass) return { ok: false, error: 'no_passport', message: 'строка паспорта по name+date не найдена' };

    var bike      = String(crow[2] || '').trim();   // C
    var startRaw  = crow[4];                          // E (Date/строка) — для длительности
    var endRaw    = crow[5];                          // F (Date/строка)
    var endD      = normalizeDate_(crow[5]);        // F → dd-MM-yyyy (для %Rud%)
    var dur       = String(crow[6] || '').trim();   // G — срок («N Д» / «N М»)
    var costMonth = crow[11];                        // L — цена/месяц (СЫРОЙ ввод)
    var costDay   = crow[12];                        // M — цена/день (СЫРОЙ ввод)
    // J (to_pay, crow[9]) НЕ используем для TH: на «Бронь» формула CRM даёт 0 (формулу J/I НЕ трогаем).
    var depRaw    = crow[18];                        // S — число ИЛИ 'passport'
    var helmets   = String(crow[19] || '').trim();  // T
    var contacts  = String(crow[20] || '').trim();  // U
    var note      = String(crow[21] || '').trim();  // V

    // --- 3) %Cost of vehicle% из РЕДАКТИРУЕМОЙ вкладки стоимость_моделей по модели (НЕ Лист1 F) ---
    var vehCost = costModelLookup_(bike);   // строка-число ИЛИ DASH

    // --- 4) расчёты ---
    var now = new Date();
    var today = ('0' + now.getDate()).slice(-2) + '-' + ('0' + (now.getMonth() + 1)).slice(-2) + '-' + now.getFullYear();

    // Cost of hire со ставкой и единицей: M → «<M> per day»; иначе L → «<L> per month»; оба пусты → прочерк.
    // СЫРОЙ ввод L/M, НЕ H. Суффикс следует ЗАПОЛНЕННОМУ полю, не длительности.
    var mNum = Number(costDay), lNum = Number(costMonth);
    var hireStr;
    if (costDay !== '' && costDay != null && isFinite(mNum) && mNum > 0) hireStr = mNum + ' per day';
    else if (costMonth !== '' && costMonth != null && isFinite(lNum) && lNum > 0) hireStr = lNum + ' per month';
    else hireStr = DASH;

    // %TH% (Total Hire) = ВЫЧИСЛЯЕМЫЙ ставка×длительность (НЕ J — на «Бронь» J=0). Сырьё L/M/G/E/F.
    //   M заполнен → TH = M × дни (дни из G «N Д», иначе F−E); иначе L → TH = L × месяцы
    //   (месяцы из G «N М», иначе round((F−E)/30)); ни L ни M → TH = прочерк.
    var th = null;
    if (costDay !== '' && costDay != null && isFinite(mNum) && mNum > 0) {
      var days = durationDays_(dur, startRaw, endRaw);
      if (days > 0) th = mNum * days;
    } else if (costMonth !== '' && costMonth != null && isFinite(lNum) && lNum > 0) {
      var months = durationMonths_(dur, startRaw, endRaw);
      if (months > 0) th = lNum * months;
    }
    var df = contractDeliveryFee_(note);            // число | 0 | null(прочерк)

    var depMoney = (typeof depRaw === 'number' && isFinite(depRaw)) ? depRaw
                   : (String(depRaw).replace(',', '.').match(/^\d+(\.\d+)?$/) ? Number(depRaw) : null);
    var isPassportDep = (depMoney === null) && /passport/i.test(String(depRaw));
    var depositStr = (depMoney !== null) ? String(depMoney) : (isPassportDep ? 'Passport' : DASH);

    // CT (Current Total): TH прочерк → CT прочерк. Иначе base=TH+DF.
    //   депозит деньги → base+Deposit (число); депозит passport → «<base> + Passport»; пусто → base.
    var ct = DASH;
    if (th !== null) {
      var base = th + (df || 0);
      if (depMoney !== null) ct = String(base + depMoney);
      else if (isPassportDep) ct = base + ' + Passport';
      else ct = String(base);
    }

    var phones = contractPhones_(contacts);

    // авто-KM по правилу (Галка v1): сходится → current_km; иначе прочерк («под запрос»)
    var kmAuto = autoKm_(bike);                       // {value:Number|null, status:'ok'|'request'}
    var kmStr = (kmAuto.status === 'ok' && kmAuto.value != null) ? String(kmAuto.value) : DASH;
    // адреса доставки из note (Pickup=Return=район); Address in Phuket (проживание) — прочерк (из диалога позже)
    var area = contractDeliveryArea_(note);

    // --- 5) карта 26 плейсхолдеров (внутренний текст без %) ---
    var R = {
      "Country": pass.country || DASH,
      "Nationality": pass.nationality || DASH,
      "Hirer's full name": pass.full_name || name,
      "Passport No.": pass.document_id || DASH,
      "Date of birth": normalizeDate_(pass.birth_date) || DASH,
      "Expiry date": normalizeDate_(pass.expire_date) || DASH,
      "Social contact": contractSocial_(contacts),
      "Tel.1": phones[0],
      "Tel.2": phones[1],
      "Deposit": depositStr,
      "H": helmets || DASH,
      "Pud": dsN || DASH,
      "Rud": endD || DASH,
      "Model CC Registration": bike || DASH,
      "DF": (df === null ? DASH : String(df)),
      "Cost of hire": hireStr,
      "TH": (th === null ? DASH : String(th)),
      "CT": ct,
      "Cost of vehicle": vehCost,
      "Date": today,
      "KM reading": kmStr,
      "FUEL LEVEL": "FULL",
      "Pbt": PBT_DEFAULT,
      "Address in Phuket": DASH,
      "Pickup address": area,
      "Return address": area,
    };

    // --- 6) один живой договор на бронь: regen в ТОТ ЖЕ Doc по маппингу booking_id→file_id ---
    var fname = (pass.full_name || name) + ' ' + today;
    var mapKey = bookingId || ('nd:' + nameL + '|' + dsN);   // фоллбэк-ключ для старых броней без booking_id
    var prev = contractMapGet_(mapKey);                       // {file_id} | null
    var fileId = null, regenerated = false;
    if (prev && prev.file_id) {
      try {
        fillContractDoc_(prev.file_id, R);                    // вар.A: открыть тот Doc, перестроить из шаблона
        fileId = prev.file_id; regenerated = true;
      } catch (e) { fileId = null; }                          // файл удалён/недоступен → создадим заново ниже
    }
    if (!fileId) {
      var copy = DriveApp.getFileById(CONTRACT_TEMPLATE_ID).makeCopy(fname, DriveApp.getFolderById(CONTRACT_FOLDER_ID));
      var doc = DocumentApp.openById(copy.getId());
      var b = doc.getBody();
      Object.keys(R).forEach(function (key) { b.replaceText('%' + contractEsc_(key) + '%', String(R[key])); });
      doc.saveAndClose();
      fileId = copy.getId();
    }
    contractMapSet_(mapKey, fileId, (pass.full_name || name), bike);   // upsert маппинга «договоры»
    var url = DriveApp.getFileById(fileId).getUrl();

    return { ok: true, file_id: fileId, url: url, name: fname, regenerated: regenerated,
             flags: { hire_blank: hireStr === DASH, df_blank: df === null, vehicle_blank: vehCost === DASH,
                      km_request: kmStr === DASH, booking_id: !!bookingId } };
  } catch (err) {
    return { ok: false, error: 'contract_failed', message: String(err) };
  }
}
