/**
 * Closing.gs — «Лист закрытия»: расчёт доплат перед закрытием брони (Bot Data «закрытие»).
 * НЕ меняет статус CRM «Завершена» (отдельный approve-заход). Только данные расчёта.
 * total_due = surcharge_days + surcharge_fuel + damage + other (числа). Деньги-доплаты — ручной ввод v1.
 * Зона: Bot Data (своя таблица, НЕ CRM) — зелёная; аудит через чёрный ящик 4.1 (client-side), НЕ 4.2.
 */

function closingNum_(v) {
  var n = Number(String(v == null ? '' : v).replace(',', '.').replace(/[^\d.\-]/g, ''));
  return isFinite(n) ? n : 0;
}

/** Найти строку «закрытие»: по booking_id (если задан), иначе по bike+date_return. → {row, cur}|null. */
// Статусы «закрыта» — такие строки фоллбэк по байку НЕ воскрешает (повторная аренда → новая строка).
var CLOSING_CLOSED = { closed: 1, settled: 1, done: 1, 'завершено': 1, 'закрыто': 1, 'завершена': 1 };

function closingFind_(tab, H, bid, bike, dret) {
  var last = tab.getLastRow();
  if (last < 2) return null;
  var data = tab.getRange(2, 1, last - 1, H.length).getValues();
  var SI = H.indexOf('status');
  var hit = -1;
  for (var i = 0; i < data.length; i++) {
    var rbid = String(data[i][0] || '').trim();
    if (bid) {
      if (rbid === bid) { hit = i; break; }   // booking_id — ТОЧНЫЙ приоритетный матч
      continue;
    }
    // ФОЛЛБЭК (booking_id пуст): по BIKE среди НЕ-закрытых (open), дата ИГНОР; берём ПОСЛЕДНЮЮ open.
    var rbike = String(data[i][1] || '').trim();
    var rst = String(data[i][SI] || '').trim().toLowerCase();
    if (bike && rbike.toLowerCase() === bike.toLowerCase() && !CLOSING_CLOSED[rst]) hit = i;
  }
  if (hit < 0) return null;
  var cur = {}; H.forEach(function (h, idx) { cur[h] = data[hit][idx]; });
  return { row: hit + 2, cur: cur };
}

/**
 * CLOSEACCRUAL1910 (условие (1) Codex TB-REVIEW-1910-2400): бронь CRM, которой принадлежит booking_id строки
 * закрытия. Ровно одна строка «клиенты» с этим Y → {row, status, bike, date_start (день ГГГГ-ММ-ДД), date_end};
 * ноль/несколько/лист не прочитан → booking null + why. Только чтение. Нужна вызывающему, чтобы доплаты этой
 * строки начислялись ТОЙ аренде, которую он закрывает, а не «последней open по байку».
 */
function closingBookingOf_(bid) {
  if (!bid) return { booking: null, why: 'no_booking_id' };
  try {
    var sh = SpreadsheetApp.openById(BOOKING.MANAGER_ID).getSheetByName(BOOKING.SHEET);
    if (!sh) return { booking: null, why: 'crm_sheet_not_found' };
    var last = sh.getLastRow();
    if (last < 2) return { booking: null, why: 'booking_not_found' };
    var data = sh.getRange(2, 1, last - 1, BOOKING.COL.BOOKING_ID).getValues(); // A..Y
    var hits = [];
    for (var i = 0; i < data.length; i++)
      if (String(data[i][BOOKING.COL.BOOKING_ID - 1] || '').trim() === bid) hits.push(i);
    if (hits.length !== 1) return { booking: null, why: hits.length ? 'booking_ambiguous' : 'booking_not_found' };
    var r = data[hits[0]];
    var de = bookingParseDate_(r[BOOKING.COL.DATE_END - 1]);
    return { booking: { row: hits[0] + 2, status: String(r[BOOKING.COL.STATUS - 1] || '').trim(),
                        bike: String(r[BOOKING.COL.BIKE - 1] || '').trim(),
                        date_start: closeAccrualDay_(r[BOOKING.COL.DATE_START - 1]),
                        date_end: de ? bookingFmtDate_(de) : String(r[BOOKING.COL.DATE_END - 1] || '') },
             why: '' };
  } catch (err) {
    return { booking: null, why: 'crm_unread: ' + String(err) };
  }
}

/**
 * CLOSEACCRUAL1910 (замечание приёмки 20.10 — ВЕРСИЯ записи листа): строка листа закрытия по ТОЧНОМУ booking_id —
 * тем же closingFind_, что closing_upsert (при непустом booking_id фоллбэка по байку нет) — и БЕЗ записи. → {row, cur}
 * | null. Зовёт closeBooking под замком начисления: части операции карточки сверяются с листом СЕЙЧАС, а не с ответом
 * closing_upsert, по которому карточка родилась (лист мог смениться повтором возврата или командой «закрытие»).
 */
function closingRowById_(bid) {
  bid = String(bid || '').trim();
  if (!bid) return null;
  return closingFind_(getBotTab_(BOTDATA.TABS.CLOSING), BOTDATA.CLOSING_HEADERS, bid, '', '');
}

/**
 * CLOSEACCRUAL1910: найденная строка (closingRowById_) → ответ ТОГО ЖЕ вида, что closing_upsert (components +
 * binding с match 'booking_id' и бронью CRM), но без записи; null → {ok:false, error:'not_found'}. Отдаётся
 * вызывающему при отказе closing_changed: новую карточку он строит из листа, прочитанного под замком, и судит её
 * привязку тем же кодом, что на возврате. total_due — как лежит в строке (не пересчёт): части, правленые мимо
 * closing_upsert, вызывающий поймает сверкой суммы.
 */
function closingReplyOf_(found) {
  if (!found) return { ok: false, error: 'not_found' };
  var c = found.cur;
  var bid = String(c.booking_id || '').trim();
  var bk = closingBookingOf_(bid);
  var st = c.updated_at;
  return { ok: true, row: found.row, total_due: c.total_due,
           components: { surcharge_days: c.surcharge_days, surcharge_fuel: c.surcharge_fuel, damage: c.damage,
                         other: c.other },
           binding: { v: 1, row: found.row, match: 'booking_id', booking_id: bid, bike: c.bike,
                      date_return: c.date_return,
                      updated_at: Object.prototype.toString.call(st) === '[object Date]' ? st.toISOString() : String(st || ''),
                      booking: bk.booking, booking_why: bk.why } };
}

/**
 * Upsert строки закрытия (merge: переданные поля поверх существующих, total_due пересчитывается).
 * body: booking_id?, bike, name?, date_return?, fuel_level?, surcharge_days?, surcharge_fuel?,
 *       damage?, other?, deposit_action?, status?, note?.
 * CLOSEACCRUAL1910: ответ несёт сверх прежнего {ok,row,total_due} ещё РОВНО записанные четыре доплаты
 * (components — значения как легли в строку, без пересчёта и без раскладки total_due на части) и привязку
 * (binding): строка листа, КАК она найдена (match: 'booking_id' — по точному booking_id; 'new' — дописана этим
 * вызовом с booking_id; 'bike' — фоллбэк по байку, дата игнорируется, строка может быть ЧУЖОЙ прежней аренды;
 * 'new_no_id' — дописана без booking_id), booking_id, байк, updated_at и бронь CRM этого booking_id
 * (closingBookingOf_). Поиск строки (closingFind_) и запись не менялись: привязку судит вызывающий.
 * Версией записи для начисления служит СОДЕРЖИМОЕ (booking_id, строка, четыре части — closeBooking сверяет их под
 * замком), а не штамп updated_at: штамп меняет любой upsert, в том числе правка одного топлива.
 */
function closingUpsert_(body) {
  var p = body || {};
  try {
    var tab = getBotTab_(BOTDATA.TABS.CLOSING);
    var H = BOTDATA.CLOSING_HEADERS;
    var bid = String(p.booking_id || '').trim();
    var bike = String(p.bike || '').trim();
    var dret = String(p.date_return || '').trim();
    if (!bid && !bike) return { ok: false, error: 'no_key', message: 'нужен booking_id или bike' };

    var found = closingFind_(tab, H, bid, bike, dret);
    var cur = found ? found.cur : {};
    function pick(k, def) { return (p[k] !== undefined && p[k] !== null && p[k] !== '') ? p[k]
                                   : (cur[k] !== undefined && cur[k] !== '' ? cur[k] : def); }

    var rec = {
      booking_id: bid || cur.booking_id || '',
      bike: bike || cur.bike || '',
      name: pick('name', ''),
      date_return: dret || cur.date_return || '',
      fuel_level: pick('fuel_level', ''),
      surcharge_days: pick('surcharge_days', ''),
      surcharge_fuel: pick('surcharge_fuel', ''),
      damage: pick('damage', ''),
      other: pick('other', ''),
      deposit_action: pick('deposit_action', ''),
      status: pick('status', 'open'),
      note: pick('note', ''),
    };
    var total = closingNum_(rec.surcharge_days) + closingNum_(rec.surcharge_fuel) +
                closingNum_(rec.damage) + closingNum_(rec.other);
    var stamp = new Date();
    var rowData = [rec.booking_id, rec.bike, rec.name, rec.date_return, rec.fuel_level,
      rec.surcharge_days, rec.surcharge_fuel, rec.damage, rec.other, total, rec.deposit_action,
      rec.status, rec.note, stamp];
    // CLOSEACCRUAL1910: части — как легли в строку (rec), а не производные от total_due
    var components = { surcharge_days: rec.surcharge_days, surcharge_fuel: rec.surcharge_fuel,
                       damage: rec.damage, other: rec.other };
    function binding(row, match) {
      var bk = closingBookingOf_(String(rec.booking_id || '').trim());
      return { v: 1, row: row, match: match, booking_id: String(rec.booking_id || '').trim(), bike: rec.bike,
               date_return: rec.date_return, updated_at: stamp.toISOString(), booking: bk.booking, booking_why: bk.why };
    }

    if (found) {
      tab.getRange(found.row, 1, 1, H.length).setValues([rowData]);
      return { ok: true, row: found.row, updated: true, total_due: total, components: components,
               binding: binding(found.row, bid ? 'booking_id' : 'bike') };
    }
    tab.appendRow(rowData);
    var newRow = tab.getLastRow();
    return { ok: true, row: newRow, saved: true, total_due: total, components: components,
             binding: binding(newRow, bid ? 'new' : 'new_no_id') };
  } catch (err) {
    return { ok: false, error: 'closing_failed', message: String(err) };
  }
}

/** Прочитать строку закрытия по booking_id или bike. → {ok, item} | {ok:false, error:'not_found'}. */
function closingGet_(body) {
  var p = body || {};
  var tab = getBotTab_(BOTDATA.TABS.CLOSING);
  var H = BOTDATA.CLOSING_HEADERS;
  var bid = String(p.booking_id || '').trim();
  var bike = String(p.bike || '').trim();
  var f = closingFind_(tab, H, bid, bike, String(p.date_return || '').trim());
  if (!f) return { ok: false, error: 'not_found' };
  var o = f.cur; o._row = f.row;
  return { ok: true, item: o };
}

/** Список закрытий (фильтр по status, опц.). → {ok, items}. */
function closingList_(body) {
  var p = body || {};
  var tab = getBotTab_(BOTDATA.TABS.CLOSING);
  var H = BOTDATA.CLOSING_HEADERS;
  var st = p.status ? String(p.status) : null;
  var last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [] };
  var data = tab.getRange(2, 1, last - 1, H.length).getValues();
  var out = [];
  for (var i = 0; i < data.length; i++) {
    var o = {}; H.forEach(function (h, idx) { o[h] = data[i][idx]; });
    if (st && String(o.status) !== st) continue;
    out.push(o);
  }
  return { ok: true, items: out };
}
