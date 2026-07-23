/**
 * ServicePending.gs — двухфазный сервисный поток ТО (Bot Data «то_заявки»).
 * ФАЗА 1 (заявка): механик привёз байк на работы → строка status='заявлено', declared=перечень.
 * ФАЗА 2 (факт): механик отписался «готово» → done=перечень + odometer → status='ждёт_подтверждения'.
 * ЗАПИСЬ в Лист1 (кол.I/J) делает Splinter ТОЛЬКО по «да» доверенного (trust не ослаблен) — НЕ здесь.
 * Зона: Bot Data (своя таблица, НЕ CRM/Лист1) — зелёная; в REDZONE_LOCK НЕ входит.
 * declared/done — строки-перечни kind через запятую: oil,gear,abs,airfilter,filter,pads,chain,other.
 * status ∈ заявлено | ждёт_факт | ждёт_подтверждения | закрыто.
 */

// Закрытые заявки фоллбэк по байку/теме НЕ воскрешает (новый визит → новая строка).
var SP_CLOSED = { 'закрыто': 1, closed: 1, done: 1, 'завершено': 1 };

/** Найти ОТКРЫТУЮ заявку: по chat_id+topic_id+bike среди НЕ-закрытых; берём последнюю open. → {row,cur}|null. */
function servicePendingFind_(tab, H, chat_id, topic_id, bike) {
  var last = tab.getLastRow();
  if (last < 2) return null;
  var data = tab.getRange(2, 1, last - 1, H.length).getValues();
  var SI = H.indexOf('status');
  var plate = plateFromName_(bike);
  var hit = -1;
  for (var i = 0; i < data.length; i++) {
    var rst = String(data[i][SI] || '').trim().toLowerCase();
    if (SP_CLOSED[rst]) continue;
    var rchat = String(data[i][2] || '').trim();
    var rtopic = String(data[i][3] || '').trim();
    var rbike = String(data[i][4] || '').trim();
    var sameChat = String(chat_id || '').trim() === rchat;
    var sameTopic = String(topic_id || '').trim() === rtopic;
    var sameBike = plate ? (plateFromName_(rbike) === plate)
                         : (rbike.toLowerCase() === String(bike || '').trim().toLowerCase());
    if (sameChat && sameTopic && (sameBike || !bike)) hit = i;
  }
  if (hit < 0) return null;
  var cur = {}; H.forEach(function (h, idx) { cur[h] = data[hit][idx]; });
  return { row: hit + 2, cur: cur };
}

/**
 * Upsert заявки (merge переданных полей поверх существующей открытой).
 * body: chat_id, topic_id, bike, declared?, done?, status?, odometer?, note?.
 */
function servicePendingUpsert_(body) {
  var p = body || {};
  try {
    var tab = getBotTab_(BOTDATA.TABS.SERVICE_PENDING);
    var H = BOTDATA.SERVICE_PENDING_HEADERS;
    var chat_id = String(p.chat_id == null ? '' : p.chat_id).trim();
    var topic_id = String(p.topic_id == null ? '' : p.topic_id).trim();
    var bike = String(p.bike || '').trim();
    if (!chat_id || !bike) return { ok: false, error: 'no_key', message: 'нужны chat_id и bike' };

    var found = servicePendingFind_(tab, H, chat_id, topic_id, bike);
    var cur = found ? found.cur : {};
    function pick(k, def) { return (p[k] !== undefined && p[k] !== null && p[k] !== '') ? p[k]
                                   : (cur[k] !== undefined && cur[k] !== '' ? cur[k] : def); }
    var nowIso = new Date().toISOString();
    var rec = {
      created_at: cur.created_at || nowIso,
      updated_at: nowIso,
      chat_id: chat_id,
      topic_id: topic_id,
      bike: bike,
      declared: pick('declared', ''),
      done: pick('done', ''),
      status: pick('status', 'заявлено'),
      odometer: pick('odometer', ''),
      last_reminded_at: pick('last_reminded_at', ''),
      note: pick('note', ''),
    };
    var rowData = [rec.created_at, rec.updated_at, rec.chat_id, rec.topic_id, rec.bike,
      rec.declared, rec.done, rec.status, rec.odometer, rec.last_reminded_at, rec.note];
    if (found) {
      tab.getRange(found.row, 1, 1, H.length).setValues([rowData]);
      return { ok: true, row: found.row, updated: true, status: rec.status };
    }
    tab.appendRow(rowData);
    return { ok: true, row: tab.getLastRow(), saved: true, status: rec.status };
  } catch (err) {
    return { ok: false, error: 'service_pending_failed', message: String(err) };
  }
}

/** Прочитать открытую заявку по chat_id+topic_id+bike. → {ok,item}|{ok:false,error:'not_found'}. */
function servicePendingGet_(body) {
  var p = body || {};
  var tab = getBotTab_(BOTDATA.TABS.SERVICE_PENDING);
  var H = BOTDATA.SERVICE_PENDING_HEADERS;
  var f = servicePendingFind_(tab, H, p.chat_id, p.topic_id, String(p.bike || '').trim());
  if (!f) return { ok: false, error: 'not_found' };
  var o = f.cur; o._row = f.row;
  return { ok: true, item: o };
}

/**
 * Список заявок. Фильтры (опц.): status (точное), open=true (все НЕ закрытые),
 * older_than_min (для висяка: updated_at старше N минут). → {ok, items}.
 */
function servicePendingList_(body) {
  var p = body || {};
  var tab = getBotTab_(BOTDATA.TABS.SERVICE_PENDING);
  var H = BOTDATA.SERVICE_PENDING_HEADERS;
  var last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [] };
  var data = tab.getRange(2, 1, last - 1, H.length).getValues();
  var st = p.status ? String(p.status) : null;
  var openOnly = (p.open === true || p.open === 'true');
  var olderMin = p.older_than_min != null ? Number(p.older_than_min) : null;
  var now = new Date().getTime();
  var out = [];
  for (var i = 0; i < data.length; i++) {
    var o = {}; H.forEach(function (h, idx) { o[h] = data[i][idx]; });
    var rst = String(o.status || '').trim().toLowerCase();
    if (st && String(o.status) !== st) continue;
    if (openOnly && SP_CLOSED[rst]) continue;
    if (olderMin != null) {
      var ts = o.updated_at ? new Date(o.updated_at).getTime() : 0;
      if (!ts || (now - ts) / 60000 < olderMin) continue;
    }
    o._row = i + 2;
    out.push(o);
  }
  return { ok: true, items: out };
}

/** Закрыть заявку (status='закрыто'). body: chat_id, topic_id, bike, note?. */
function servicePendingClose_(body) {
  var p = body || {};
  var merged = Object.assign({}, p, { status: 'закрыто' });
  return servicePendingUpsert_(merged);
}
