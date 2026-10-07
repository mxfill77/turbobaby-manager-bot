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
 * Upsert строки закрытия (merge: переданные поля поверх существующих, total_due пересчитывается).
 * body: booking_id?, bike, name?, date_return?, fuel_level?, surcharge_days?, surcharge_fuel?,
 *       damage?, other?, deposit_action?, status?, note?.
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
    var rowData = [rec.booking_id, rec.bike, rec.name, rec.date_return, rec.fuel_level,
      rec.surcharge_days, rec.surcharge_fuel, rec.damage, rec.other, total, rec.deposit_action,
      rec.status, rec.note, new Date()];

    if (found) { tab.getRange(found.row, 1, 1, H.length).setValues([rowData]); return { ok: true, row: found.row, updated: true, total_due: total }; }
    tab.appendRow(rowData);
    return { ok: true, row: tab.getLastRow(), saved: true, total_due: total };
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
