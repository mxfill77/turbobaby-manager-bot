/**
 * TurboBaby Bridge — BotData
 *
 * Хранилище для Splinter: транзакции, баланс, события (обслуживание байков).
 * Пишется в ОТДЕЛЬНУЮ таблицу "TurboBaby Bot Data" на Drive владельца —
 * рабочие таблицы (CRM, Зарплаты) НЕ трогаем.
 *
 * Таблица создаётся автоматически при первой записи.
 * Её ID сохраняется в Script Properties → BOT_DATA_SHEET_ID.
 */

const BOTDATA = {
  SHEET_TITLE: 'TurboBaby Bot Data',
  TABS: {
    TX:      'транзакции',
    EVENTS:  'события',
    BALANCE: 'сверка_баланса',
    SERVICE: 'обслуживание',
    IMPORTANT: 'важное',
    AUDIT: 'аудит',
    WRITELOG: 'боевой_лог',
    QUEUE: 'очередь_оркестратора',
    PASSPORT: 'паспорта',
    COST_MODELS: 'стоимость_моделей',
    CONTRACTS: 'договоры',
    CLOSING: 'закрытие',
    SERVICE_PENDING: 'то_заявки',
    STATE: 'состояние_байка',
  },
  TX_HEADERS: [
    'recorded_at', 'msg_date', 'group', 'sender', 'amount', 'currency',
    'category', 'bike', 'deposit', 'description', 'raw', 'status', 'msg_id',
    'booking_id'   // col N (O3-3c): привязка deposit-прихода к брони (uuid из CRM col Y); опционален
  ],
  EVENT_HEADERS: [
    'recorded_at', 'msg_date', 'group', 'bike', 'event_type',
    'fuel', 'mileage', 'photos', 'notes', 'status', 'msg_id', 'sender'
  ],
  BALANCE_HEADERS: [
    'checked_at', 'currency', 'bot_balance', 'pym_balance', 'diff', 'note'
  ],
  // ТО-трекер: одна строка = один вид ТО одного байка
  SERVICE_HEADERS: [
    'updated_at', 'bike', 'topic_id', 'service_type', 'current_km',
    'last_service_km', 'interval_km', 'next_km', 'status',
    'pinned_msg_id', 'last_reminded_at', 'note'
  ],
  // Важное (надзиратель): ДТП, ремонты, просрочки — крепится, напоминается, закрывается
  IMPORTANT_HEADERS: [
    'created_at', 'chat_id', 'topic_id', 'group', 'kind', 'summary',
    'pinned_msg_id', 'last_reminded_at', 'status', 'confirmed_by', 'closed_at', 'note'
  ],
  // Журнал действий бота для аудита: что просили, что сделал, вердикт надзора
  AUDIT_HEADERS: [
    'logged_at', 'group', 'topic_id', 'user_request', 'tool', 'tool_args',
    'claimed_result', 'verdict', 'severity', 'detail', 'suggested_fix', 'status'
  ],
  // ЧЁРНЫЙ ЯЩИК боевых записей (пункт 4.1): каждая запись в живые данные — атомарный appendRow.
  WRITELOG_HEADERS: [
    'logged_at', 'initiator', 'action', 'args', 'result', 'critical'
  ],
  // ОЧЕРЕДЬ ОРКЕСТРАТОРА (ступень 1, заход 1): служебный лист задач. НЕ боевые данные.
  // status ∈ new/in_progress/needs_approval/approved/done/failed.
  // lane (вторая полоса 04.07.2026): 'vps' (демон на VPS) | 'pc' (агент на ПК). Пустая ячейка
  // у старых строк = 'vps'. get_pending БЕЗ lane отдаёт ТОЛЬКО vps — старый VPS-демон без
  // правок не видит и не берёт pc-задачи.
  QUEUE_HEADERS: [
    'id', 'created', 'from', 'task_text', 'status', 'result', 'approved_by', 'updated', 'lane'
  ],
  // ПАСПОРТА (этап B2): OCR-результат паспорта, привязка к брони. НЕ в CRM «клиенты».
  // ocr_status ∈ ok / failed. Поля распознавания — ПРЕДВАРИТЕЛЬНЫЕ (vision ошибается).
  PASSPORT_HEADERS: [
    'booking_key', 'bike', 'name', 'drive_file_id', 'last_name', 'given_names', 'full_name',
    'document_id', 'nationality', 'country', 'birth_date', 'expire_date', 'ocr_status', 'created_at'
  ],
  // СТОИМОСТЬ МОДЕЛЕЙ (B3-fix): РЕДАКТИРУЕМЫЙ источник %Cost of vehicle% по модели (Филипп правит ячейку
  // без передеплоя). НЕ Лист1 F (давал неверные числа). model = каноничный ключ матчера costModelKey_.
  COST_MODELS_HEADERS: ['model', 'value_thb'],
  // ДОГОВОРЫ (Галка v1): маппинг booking_id→file_id, один живой договор на бронь (regen в тот же Doc).
  CONTRACTS_HEADERS: ['booking_id', 'file_id', 'name', 'bike', 'created_at', 'updated_at'],
  // ЗАКРЫТИЕ (Лист закрытия): расчёт доплат перед закрытием брони. НЕ меняет статус CRM «Завершена».
  // total_due = бот суммирует surcharge_days+surcharge_fuel+damage+other (числа).
  CLOSING_HEADERS: ['booking_id', 'bike', 'name', 'date_return', 'fuel_level', 'surcharge_days',
    'surcharge_fuel', 'damage', 'other', 'total_due', 'deposit_action', 'status', 'note', 'updated_at'],
  // ТО-ЗАЯВКИ (двухфазный сервис): одна строка = один открытый визит байка на ТО.
  // declared/done — перечни kind через запятую (oil,gear,filter,pads,chain...). status: заявлено|ждёт_факт|ждёт_подтверждения|закрыто.
  SERVICE_PENDING_HEADERS: ['created_at', 'updated_at', 'chat_id', 'topic_id', 'bike',
    'declared', 'done', 'status', 'odometer', 'last_reminded_at', 'note'],
  // СОСТОЯНИЕ БАЙКА (Этап 1 трекинга): bot-owned слой, ОДНА строка на байк (ключ = bike, точное название).
  // НЕ CRM/Лист1 — их статус производный. Брони живут в CRM «клиенты», тут только текущее состояние.
  // status ∈ STATE_STATUSES (в аренде / к возврату / дома / офис / ремонт).
  STATE_HEADERS: ['bike', 'status', 'location', 'booking_id', 'client', 'date_out',
    'date_due', 'date_back', 'service_name', 'last_event_msg_id', 'updated'],
};

// Допустимые статусы состояния байка (валидируются в stateUpsert_).
var STATE_STATUSES = ['в аренде', 'к возврату', 'дома', 'офис', 'ремонт'];

// Начальный засев вкладки «стоимость_моделей» (одноразово через seedCostModels_; потом правится в ячейках).
var COST_MODELS_SEED = [
  ['NMAX 155', 70000], ['XSR 155', 80000], ['FORZA 300', 120000], ['MT-03 300', 120000],
  ['XMAX 300', 140000], ['CB 300R', 150000], ['ADV 350', 150000], ['NINJA 400', 200000],
  ['CBR 650R', 220000], ['CB 650R', 220000], ['VULCAN 650', 220000], ['XADV 750', 440000],
];

/** Засеять «стоимость_моделей» 12 строками ОДНОРАЗОВО (идемпотентно: если данные уже есть — не трогает). */
function seedCostModels_() {
  var tab = getBotTab_(BOTDATA.TABS.COST_MODELS);
  if (tab.getLastRow() >= 2) return { ok: true, seeded: false, rows: tab.getLastRow() - 1, message: 'уже засеяно' };
  for (var i = 0; i < COST_MODELS_SEED.length; i++) tab.appendRow(COST_MODELS_SEED[i]);
  return { ok: true, seeded: true, rows: COST_MODELS_SEED.length };
}

// Лимит строк боевого лога (трим старейших сверх лимита, чтобы лист не раздувался).
var WRITELOG_MAX_ROWS = 3000;


/**
 * Возвращает (создаёт при необходимости) таблицу Bot Data.
 */
function getBotDataSpreadsheet_() {
  const props = PropertiesService.getScriptProperties();
  let id = props.getProperty('BOT_DATA_SHEET_ID');

  if (id) {
    try {
      return SpreadsheetApp.openById(id);
    } catch (e) {
      // ID протух — пересоздадим
      id = null;
    }
  }

  // Создаём новую таблицу в главной папке компании
  const ss = SpreadsheetApp.create(BOTDATA.SHEET_TITLE);
  // Переносим в папку MAIN если возможно
  try {
    const file = DriveApp.getFileById(ss.getId());
    const folder = DriveApp.getFolderById(CONFIG.FOLDERS.MAIN);
    folder.addFile(file);
    DriveApp.getRootFolder().removeFile(file);
  } catch (e) {
    // если не вышло — останется в корне, не критично
  }

  // Инициализируем вкладки
  initTab_(ss, BOTDATA.TABS.TX, BOTDATA.TX_HEADERS);
  initTab_(ss, BOTDATA.TABS.EVENTS, BOTDATA.EVENT_HEADERS);
  initTab_(ss, BOTDATA.TABS.BALANCE, BOTDATA.BALANCE_HEADERS);
  initTab_(ss, BOTDATA.TABS.SERVICE, BOTDATA.SERVICE_HEADERS);
  initTab_(ss, BOTDATA.TABS.IMPORTANT, BOTDATA.IMPORTANT_HEADERS);
  initTab_(ss, BOTDATA.TABS.AUDIT, BOTDATA.AUDIT_HEADERS);
  initTab_(ss, BOTDATA.TABS.SERVICE_PENDING, BOTDATA.SERVICE_PENDING_HEADERS);

  // Удаляем дефолтный лист "Sheet1"/"Лист1"
  const def = ss.getSheets().find(s =>
    ['Sheet1', 'Лист1'].includes(s.getName())
  );
  if (def && ss.getSheets().length > 1) ss.deleteSheet(def);

  props.setProperty('BOT_DATA_SHEET_ID', ss.getId());
  return ss;
}

function initTab_(ss, name, headers) {
  let tab = ss.getSheetByName(name);
  if (!tab) tab = ss.insertSheet(name);
  if (tab.getLastRow() === 0) {
    tab.getRange(1, 1, 1, headers.length).setValues([headers]);
    tab.setFrozenRows(1);
    tab.getRange(1, 1, 1, headers.length).setFontWeight('bold');
  }
  return tab;
}

function getBotTab_(tabName) {
  const ss = getBotDataSpreadsheet_();
  let tab = ss.getSheetByName(tabName);
  if (!tab) {
    // Лист ещё не создан (например 'обслуживание' в старой таблице) — создаём с заголовками
    const headersMap = {};
    headersMap[BOTDATA.TABS.TX] = BOTDATA.TX_HEADERS;
    headersMap[BOTDATA.TABS.EVENTS] = BOTDATA.EVENT_HEADERS;
    headersMap[BOTDATA.TABS.BALANCE] = BOTDATA.BALANCE_HEADERS;
    headersMap[BOTDATA.TABS.SERVICE] = BOTDATA.SERVICE_HEADERS;
    headersMap[BOTDATA.TABS.IMPORTANT] = BOTDATA.IMPORTANT_HEADERS;
    headersMap[BOTDATA.TABS.AUDIT] = BOTDATA.AUDIT_HEADERS;
    headersMap[BOTDATA.TABS.WRITELOG] = BOTDATA.WRITELOG_HEADERS;
    headersMap[BOTDATA.TABS.QUEUE] = BOTDATA.QUEUE_HEADERS;
    headersMap[BOTDATA.TABS.PASSPORT] = BOTDATA.PASSPORT_HEADERS;
    headersMap[BOTDATA.TABS.COST_MODELS] = BOTDATA.COST_MODELS_HEADERS;
    headersMap[BOTDATA.TABS.CONTRACTS] = BOTDATA.CONTRACTS_HEADERS;
    headersMap[BOTDATA.TABS.CLOSING] = BOTDATA.CLOSING_HEADERS;
    headersMap[BOTDATA.TABS.SERVICE_PENDING] = BOTDATA.SERVICE_PENDING_HEADERS;
    headersMap[BOTDATA.TABS.STATE] = BOTDATA.STATE_HEADERS;
    tab = initTab_(ss, tabName, headersMap[tabName] || ['col1']);
  }
  return tab;
}


/**
 * ЧЁРНЫЙ ЯЩИК боевых записей (4.1): атомарный appendRow одной строки лога.
 * payload: { initiator, action, args, result, critical }. НИЧЕГО не блокирует — только пишет.
 * Трим: если строк сверх WRITELOG_MAX_ROWS — удаляем старейшие (с верха данных).
 */
function logWrite_(payload) {
  try {
    var p = payload || {};
    var tab = getBotTab_(BOTDATA.TABS.WRITELOG);
    tab.appendRow([
      new Date(),
      String(p.initiator || '?').slice(0, 80),
      String(p.act || p.action || '?').slice(0, 60),   // p.act: логируемое действие (action занят роутингом)
      String(p.args || '').slice(0, 500),
      String(p.result || '').slice(0, 200),
      String(p.critical || '')
    ]);
    var last = tab.getLastRow();
    var over = last - 1 - WRITELOG_MAX_ROWS;   // строк данных сверх лимита
    if (over > 0) tab.deleteRows(2, over);     // удалить старейшие (сразу под шапкой)
    return { ok: true, rows: Math.min(last - 1, WRITELOG_MAX_ROWS) };
  } catch (err) {
    return { ok: false, error: 'log_failed', message: String(err) };
  }
}

/**
 * Чтение боевого лога для проверки С САЙТА. payload: { limit }. Возвращает последние limit записей
 * (newest-first). Дефолт 50, максимум 500.
 */
function readWriteLog_(payload) {
  var p = payload || {};
  var limit = Math.min(Math.max(parseInt(p.limit, 10) || 50, 1), 500);
  var tab = getBotTab_(BOTDATA.TABS.WRITELOG);
  var last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [], total: 0 };
  var n = Math.min(limit, last - 1);
  var rows = tab.getRange(last - n + 1, 1, n, BOTDATA.WRITELOG_HEADERS.length).getValues();
  var items = [];
  for (var i = rows.length - 1; i >= 0; i--) {   // newest-first
    var r = rows[i];
    items.push({
      logged_at: r[0], initiator: r[1], action: r[2],
      args: r[3], result: r[4], critical: r[5]
    });
  }
  return { ok: true, items: items, total: last - 1 };
}


/**
 * === ОЧЕРЕДЬ ОРКЕСТРАТОРА (ступень 1, заход 1 — инфраструктура) ===
 * Служебный лист «очередь_оркестратора». НЕ боевые данные (CRM/Лист1/деньги не трогаются).
 * Колонки (1-based): id=1, created=2, from=3, task_text=4, status=5, result=6, approved_by=7, updated=8.
 * Демона нет — это только таблица + CRUD по статусам.
 */
var QUEUE_COL = { id: 1, created: 2, from: 3, task_text: 4, status: 5, result: 6, approved_by: 7, updated: 8, lane: 9 };

/** Нормализация lane: пустое/мусор → 'vps' (все строки до введения колонки — vps-полоса). */
function queueLane_(v) {
  var s = String(v == null ? '' : v).trim().toLowerCase();
  return s === '' ? 'vps' : s;
}

/** Строка листа очереди → объект по QUEUE_HEADERS. */
function queueRowObj_(values) {
  var o = {};
  BOTDATA.QUEUE_HEADERS.forEach(function (h, i) { o[h] = values[i]; });
  return o;
}

/** Найти sheet-строку (1-based) по id; -1 если нет. */
function queueFindRow_(tab, id) {
  var last = tab.getLastRow();
  if (last < 2) return -1;
  var ids = tab.getRange(2, QUEUE_COL.id, last - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

/**
 * enqueue_task: новая задача в очередь. payload: { from, task_text, lane? } → { ok, id, lane }.
 * lane дефолтится в 'vps' (вторая полоса 04.07.2026: 'pc' = агент на ПК).
 * id = max(существующих) + 1 (под LockService — без гонки id и дублей).
 */
function enqueueTask_(payload) {
  var p = payload || {};
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var tab = getBotTab_(BOTDATA.TABS.QUEUE);
    var last = tab.getLastRow();
    var id = 1;
    if (last >= 2) {
      var ids = tab.getRange(2, QUEUE_COL.id, last - 1, 1).getValues();
      for (var i = 0; i < ids.length; i++) {
        var n = parseInt(ids[i][0], 10);
        if (isFinite(n) && n >= id) id = n + 1;
      }
    }
    var now = new Date();
    var lane = queueLane_(p.lane);
    tab.appendRow([
      id, now,
      String(p.from || '').slice(0, 120),
      String(p.task_text || '').slice(0, 5000),
      'new', '', '', now, lane
    ]);
    return { ok: true, id: id, lane: lane };
  } finally {
    lock.releaseLock();
  }
}

/**
 * get_pending: задачи по статусу (деф. new), newest-first. payload: { status?, lane? } → { ok, items }.
 * Дешёвое чтение — демон опрашивает этим (без токенов LLM).
 * lane (04.07.2026): БЕЗ параметра/пустой = 'vps' (старый VPS-демон не видит pc-задачи);
 * 'all' = без фильтра (devbot-опрос обеих полос); иначе — точный матч (пустая ячейка = 'vps').
 */
function getPending_(payload) {
  var p = payload || {};
  var raw = (p.status != null && String(p.status) !== '') ? String(p.status) : 'new';
  // Склейка статусов (02.07.2026): status может быть CSV ('done,failed,…') — клиент опрашивает
  // очередь ОДНИМ вызовом вместо четырёх. Поле statuses в ответе = маркер поддержки CSV для
  // клиентского feature-detect (bridge_client.get_pending_multi; старый клиент поле игнорирует).
  var statuses = raw.split(',').map(function (s) { return s.trim(); })
                    .filter(function (s) { return s !== ''; });
  var lane = queueLane_(p.lane);
  var tab = getBotTab_(BOTDATA.TABS.QUEUE);
  var last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [], statuses: statuses, lane: lane };
  var rows = tab.getRange(2, 1, last - 1, BOTDATA.QUEUE_HEADERS.length).getValues();
  var items = [];
  for (var i = rows.length - 1; i >= 0; i--) {   // newest-first
    if (statuses.indexOf(String(rows[i][QUEUE_COL.status - 1])) === -1) continue;
    if (lane !== 'all' && queueLane_(rows[i][QUEUE_COL.lane - 1]) !== lane) continue;
    items.push(queueRowObj_(rows[i]));
  }
  return { ok: true, items: items, statuses: statuses, lane: lane };
}

/**
 * claim_task: АТОМАРНО new→in_progress (только если ещё new, иначе already_claimed).
 * payload: { id, lane? } → { ok, task } | { ok:false, error }. LockService гарантирует, что два
 * одновременных claim не возьмут одну задачу (второй получит already_claimed).
 * lane (04.07.2026, опциональный guard): передан и НЕ 'all' и не совпал с полосой задачи →
 * wrong_lane (демон чужой полосы не заберёт задачу даже по прямому id).
 */
function claimTask_(payload) {
  var p = payload || {};
  if (p.id == null || String(p.id) === '') return { ok: false, error: 'no_id' };
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var tab = getBotTab_(BOTDATA.TABS.QUEUE);
    var row = queueFindRow_(tab, p.id);
    if (row < 0) return { ok: false, error: 'not_found' };
    if (p.lane != null && String(p.lane) !== '' && queueLane_(p.lane) !== 'all') {
      var taskLane = queueLane_(tab.getRange(row, QUEUE_COL.lane).getValue());
      if (taskLane !== queueLane_(p.lane)) return { ok: false, error: 'wrong_lane', lane: taskLane };
    }
    var cur = String(tab.getRange(row, QUEUE_COL.status).getValue());
    if (cur !== 'new') return { ok: false, error: 'already_claimed', status: cur };
    tab.getRange(row, QUEUE_COL.status).setValue('in_progress');
    tab.getRange(row, QUEUE_COL.updated).setValue(new Date());
    var vals = tab.getRange(row, 1, 1, BOTDATA.QUEUE_HEADERS.length).getValues()[0];
    return { ok: true, task: queueRowObj_(vals) };
  } finally {
    lock.releaseLock();
  }
}

/**
 * complete_task: финал задачи. payload: { id, status('done'|'failed'), result } → { ok }.
 */
function completeTask_(payload) {
  var p = payload || {};
  if (p.id == null || String(p.id) === '') return { ok: false, error: 'no_id' };
  var status = String(p.status || '');
  if (status !== 'done' && status !== 'failed') return { ok: false, error: 'bad_status' };
  var tab = getBotTab_(BOTDATA.TABS.QUEUE);
  var row = queueFindRow_(tab, p.id);
  if (row < 0) return { ok: false, error: 'not_found' };
  tab.getRange(row, QUEUE_COL.status).setValue(status);
  tab.getRange(row, QUEUE_COL.result).setValue(String(p.result || '').slice(0, 5000));
  tab.getRange(row, QUEUE_COL.updated).setValue(new Date());
  return { ok: true };
}

/**
 * set_needs_approval: задача упёрлась в красную зону. payload: { id, what } →
 * status=needs_approval + result=<что собирается сделать>. { ok }.
 */
function setNeedsApproval_(payload) {
  var p = payload || {};
  if (p.id == null || String(p.id) === '') return { ok: false, error: 'no_id' };
  var tab = getBotTab_(BOTDATA.TABS.QUEUE);
  var row = queueFindRow_(tab, p.id);
  if (row < 0) return { ok: false, error: 'not_found' };
  tab.getRange(row, QUEUE_COL.status).setValue('needs_approval');
  tab.getRange(row, QUEUE_COL.result).setValue(String(p.what || '').slice(0, 5000));
  tab.getRange(row, QUEUE_COL.updated).setValue(new Date());
  return { ok: true };
}

/**
 * approve_task: Филипп дал «да» на красный шаг. payload: { id, approved_by } →
 * needs_approval→approved + approved_by + updated. Только из needs_approval, иначе not_awaiting.
 */
function approveTask_(payload) {
  var p = payload || {};
  if (p.id == null || String(p.id) === '') return { ok: false, error: 'no_id' };
  var tab = getBotTab_(BOTDATA.TABS.QUEUE);
  var row = queueFindRow_(tab, p.id);
  if (row < 0) return { ok: false, error: 'not_found' };
  var cur = String(tab.getRange(row, QUEUE_COL.status).getValue());
  if (cur !== 'needs_approval') return { ok: false, error: 'not_awaiting', status: cur };
  tab.getRange(row, QUEUE_COL.status).setValue('approved');
  tab.getRange(row, QUEUE_COL.approved_by).setValue(String(p.approved_by || '').slice(0, 120));
  tab.getRange(row, QUEUE_COL.updated).setValue(new Date());
  return { ok: true };
}

/**
 * task_heartbeat: фон-поток демона бьёт updated, пока задача исполняется (детект зависания).
 * payload: { id } → updated=now ТОЛЬКО если status==in_progress (финальные/ждущие не трогаем).
 * { ok } | { ok:false, error:'no_id'/'not_found'/'not_inprogress' }.
 */
function queueHeartbeat_(payload) {
  var p = payload || {};
  if (p.id == null || String(p.id) === '') return { ok: false, error: 'no_id' };
  var tab = getBotTab_(BOTDATA.TABS.QUEUE);
  var row = queueFindRow_(tab, p.id);
  if (row < 0) return { ok: false, error: 'not_found' };
  var cur = String(tab.getRange(row, QUEUE_COL.status).getValue());
  if (cur !== 'in_progress') return { ok: false, error: 'not_inprogress', status: cur };
  tab.getRange(row, QUEUE_COL.updated).setValue(new Date());
  return { ok: true };
}


/**
 * Уже записана ли транзакция/событие с таким msg_id? (защита от дублей)
 */
function botMsgExists_(tabName, msgIdCol, msgId) {
  if (!msgId) return false;
  const tab = getBotTab_(tabName);
  const last = tab.getLastRow();
  if (last < 2) return false;
  const ids = tab.getRange(2, msgIdCol, last - 1, 1).getValues();
  return ids.some(r => String(r[0]) === String(msgId));
}


/**
 * Добавить транзакцию (приход/расход).
 * payload: { msg_date, group, sender, amount, currency, category,
 *            bike, deposit, description, raw, status, msg_id, booking_id }
 * booking_id (col N, O3-3c) опционален: старые вызовы без него пишут пусто.
 */
function addTransaction(payload) {
  const p = payload || {};
  const msgId = p.msg_id || '';

  if (botMsgExists_(BOTDATA.TABS.TX, 13, msgId)) {
    return { ok: true, duplicate: true, msg_id: msgId };
  }

  const tab = getBotTab_(BOTDATA.TABS.TX);
  // Живой лист создан на 13 колонок — initTab_ существующую шапку не трогает,
  // заголовок N1 достраиваем здесь (идемпотентно, одна ячейка).
  if (String(tab.getRange(1, 14).getValue()) !== 'booking_id') {
    tab.getRange(1, 14).setValue('booking_id');
  }
  tab.appendRow([
    new Date().toISOString(),
    p.msg_date || '',
    p.group || '',
    p.sender || '',
    Number(p.amount) || 0,
    (p.currency || 'THB').toUpperCase(),
    p.category || 'other',
    p.bike || '',
    p.deposit || '',
    p.description || '',
    p.raw || '',
    p.status || 'recorded',
    msgId,
    p.booking_id ? String(p.booking_id) : '',
  ]);

  return { ok: true, saved: true, balance: computeBalance_() };
}


/**
 * Добавить событие по байку (приёмка/сдача/ремонт + топливо/пробег).
 * payload: { msg_date, group, bike, event_type, fuel, mileage,
 *            photos, notes, status, msg_id }
 */
function addEvent(payload) {
  const p = payload || {};
  const msgId = p.msg_id || '';

  if (botMsgExists_(BOTDATA.TABS.EVENTS, 11, msgId)) {
    return { ok: true, duplicate: true, msg_id: msgId };
  }

  const tab = getBotTab_(BOTDATA.TABS.EVENTS);
  tab.appendRow([
    new Date().toISOString(),
    p.msg_date || '',
    p.group || '',
    p.bike || '',
    p.event_type || '',
    p.fuel || '',
    p.mileage || '',
    p.photos || 0,
    p.notes || '',
    p.status || 'recorded',
    msgId,
    p.sender || '',
  ]);

  return { ok: true, saved: true };
}


/**
 * Удалить строки из листа «события» ТОЛЬКО по точному ключу (msg_id и/или group).
 * ЗАЩИТА (иначе отказ):
 *   - без точного ключа (нет ни msg_id, ни group) → отказ no_key (никаких широких удалений);
 *   - group='' / '*' / только пробелы → отказ (не считается точным ключом);
 *   - совпало больше max (по умолч. 50, потолок 200) → отказ too_many (не удаляем ничего).
 * Совпадение по EXACT-равенству строки (===). Удаляет ТОЛЬКО лист EVENTS (своя таблица бота).
 * Возвращает сколько и ЧТО удалил (для сверки по return/логу, без кэш-экспорта).
 * payload: { msg_id?, group?, max? }
 */
function deleteEvent(payload) {
  const p = payload || {};
  const msgId = (p.msg_id != null) ? String(p.msg_id).trim() : '';
  const group = (p.group != null) ? String(p.group).trim() : '';
  const max = Math.min(Number(p.max) || 50, 200);

  if (!msgId && !group) return { ok: false, error: 'no_key', message: 'нужен точный msg_id и/или group' };
  if (p.group != null && !group) return { ok: false, error: 'bad_group', message: 'group пустой — не точный ключ' };
  if (group === '*' || group === '%') return { ok: false, error: 'bad_group', message: 'широкий фильтр запрещён' };

  const tab = getBotTab_(BOTDATA.TABS.EVENTS);
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, deleted: 0, rows: [] };

  const cols = BOTDATA.EVENT_HEADERS.length;
  const data = tab.getRange(2, 1, last - 1, cols).getValues();
  const GRP = 2, BIKE = 3, NOTES = 8, MID = 10;   // 0-based по EVENT_HEADERS

  const hits = [];
  for (let i = 0; i < data.length; i++) {
    const r = data[i];
    const okMid = msgId ? (String(r[MID]) === msgId) : true;
    const okGrp = group ? (String(r[GRP]) === group) : true;
    if (okMid && okGrp) hits.push({ row: i + 2, group: r[GRP], bike: r[BIKE], notes: r[NOTES], msg_id: r[MID] });
  }
  if (hits.length === 0) return { ok: true, deleted: 0, rows: [] };
  if (hits.length > max) return { ok: false, error: 'too_many', matched: hits.length, max: max, message: 'совпало больше лимита — ничего не удалил' };

  // удаляем СНИЗУ ВВЕРХ — чтобы номера строк не сползали по ходу
  for (let j = hits.length - 1; j >= 0; j--) tab.deleteRow(hits[j].row);
  return { ok: true, deleted: hits.length, key: { msg_id: msgId, group: group },
           rows: hits.map(h => ({ msg_id: String(h.msg_id), group: String(h.group), bike: String(h.bike), notes: String(h.notes) })) };
}


/**
 * Поля строки «события», которые ПРАВКА имеет право менять → 1-based колонка листа.
 * recorded_at (кол.A) и msg_id (кол.K) сюда НЕ входят НАМЕРЕННО:
 *   · recorded_at — метка времени ЗАПИСИ; правка меняет содержимое, а не момент, когда оно
 *     легло в лист. Именно её теряло «удалить + добавить заново», и именно поэтому она не в
 *     белом списке ВООБЩЕ: невозможность её переписать доказывается структурой, а не аккуратностью;
 *   · msg_id — ключ строки; он меняется отдельным полем new_msg_id, чтобы правка ключа была
 *     ЯВНОЙ и проверялась на конфликт с чужой строкой.
 */
var EVENT_FIX_FIELDS = {
  msg_date: 2, group: 3, bike: 4, event_type: 5, fuel: 6,
  mileage: 7, photos: 8, notes: 9, status: 10, sender: 12
};


/**
 * ПРАВКА строки листа «события» НА МЕСТЕ (без удаления и пересоздания).
 *
 * ЗАЧЕМ ОТДЕЛЬНОЕ ДЕЙСТВИЕ. Починка через deleteEvent+addEvent теряет recorded_at (новая строка
 * встаёт с новым временем записи) и переставляет строку в конец листа — история перестаёт быть
 * историей. Владелец правит систему с телефона, ручная правка ячейки как способ починки данных
 * доктриной запрещена, значит починка обязана быть ШТАТНОЙ операцией.
 *
 * КЛЮЧ ПРИВОДИТСЯ В СООТВЕТСТВИЕ СОДЕРЖИМОМУ. У автоматики ключ СИНТЕТИЧЕСКИЙ и КОНТЕНТНЫЙ
 * (`info:<номер>:<работа>:<км>`, `odo_audit:…`, `sp:…` — см. bridge_client.add_event): повтор
 * того же факта даёт тот же ключ и схлопывается дедупом. Если поправить число, а ключ оставить
 * прежним, дедуп будет сверять строку по отпечатку, которого в ней уже нет: правильная запись
 * ляжет ВТОРОЙ строкой, а ошибочный отпечаток продолжит гасить повторы. Поэтому new_msg_id —
 * часть той же операции, а не отдельный заход.
 *
 * ДИСЦИПЛИНА ТОЧНОГО КЛЮЧА — та же, что у deleteEvent: без ключа отказ, ровно одно совпадение,
 * никаких широких правок. Плюс своё: причина и автор ОБЯЗАТЕЛЬНЫ (аудит-след), а новый ключ
 * не должен быть занят другой строкой (иначе правка родила бы двойника).
 *
 * payload: { msg_id, group?, fields:{…EVENT_FIX_FIELDS…}, new_msg_id?, reason, fixed_by, confirmed:true }
 * → { ok, row, key:{old,new}, recorded_at, before, after, audit:{at,by,reason,changes,logged},
 *     rollback:{action,msg_id,new_msg_id,fields}, verified }
 */
function editEvent(payload) {
  try {
    var p = payload || {};
    var msgId = (p.msg_id != null) ? String(p.msg_id).trim() : '';
    var group = (p.group != null) ? String(p.group).trim() : '';
    var newId = (p.new_msg_id != null) ? String(p.new_msg_id).trim() : '';
    var reason = String(p.reason == null ? '' : p.reason).trim();
    var by = String(p.fixed_by == null ? '' : p.fixed_by).trim();
    var fields = (p.fields && typeof p.fields === 'object') ? p.fields : {};

    if (!msgId) return { ok: false, error: 'no_key', message: 'нужен точный msg_id правимой строки' };
    if (!reason) return { ok: false, error: 'no_reason',
                          message: 'правка без НАЗВАННОЙ причины не принимается (аудит-след)' };
    if (!by) return { ok: false, error: 'no_author',
                      message: 'правка без автора не принимается (аудит-след)' };
    if (p.confirmed !== true) return { ok: false, error: 'not_confirmed',
                                       message: 'правка строки требует confirmed=true' };

    var names = Object.keys(fields);
    for (var n = 0; n < names.length; n++) {
      if (!EVENT_FIX_FIELDS[names[n]]) {
        return { ok: false, error: 'bad_field', field: names[n],
                 allowed: Object.keys(EVENT_FIX_FIELDS),
                 message: 'править можно только перечисленные поля; метка времени записи не ' +
                          'правится вовсе, ключ — через new_msg_id' };
      }
    }
    if (!names.length && !newId) return { ok: false, error: 'nothing_to_change',
                                          message: 'не названо ни одно поле и не задан новый ключ' };

    var tab = getBotTab_(BOTDATA.TABS.EVENTS);
    var last = tab.getLastRow();
    if (last < 2) return { ok: false, error: 'not_found', msg_id: msgId };

    var cols = BOTDATA.EVENT_HEADERS.length;
    var data = tab.getRange(2, 1, last - 1, cols).getValues();
    var REC = 0, MD = 1, GRP = 2, BIKE = 3, ET = 4, FUEL = 5,
        MIL = 6, PH = 7, NOTES = 8, ST = 9, MID = 10, SND = 11;

    var hits = [], conflict = false;
    for (var i = 0; i < data.length; i++) {
      var r = data[i];
      if (String(r[MID]) === msgId && (group ? String(r[GRP]) === group : true)) hits.push(i + 2);
      else if (newId && String(r[MID]) === newId) conflict = true;
    }
    if (!hits.length) return { ok: false, error: 'not_found', msg_id: msgId, group: group };
    if (hits.length > 1) {
      return { ok: false, error: 'ambiguous', matched: hits.length, rows: hits,
               message: 'ключ совпал с несколькими строками — сузь group; правку наугад не делаем' };
    }
    if (conflict) {
      return { ok: false, error: 'key_conflict', new_msg_id: newId,
               message: 'новый ключ уже занят другой строкой — правка родила бы двойника' };
    }

    var row = hits[0];
    var cur = data[row - 2];
    function cell(idx) { return (cur[idx] === '' || cur[idx] == null) ? '' : String(cur[idx]); }
    var before = {
      recorded_at: cell(REC), msg_date: cell(MD), group: cell(GRP), bike: cell(BIKE),
      event_type: cell(ET), fuel: cell(FUEL), mileage: cell(MIL), photos: cell(PH),
      notes: cell(NOTES), status: cell(ST), msg_id: cell(MID), sender: cell(SND)
    };

    // ЧТО МЕНЯЕМ — считаем ДО записи: это и аудит-след, и готовый откат.
    var changes = [];
    for (var k = 0; k < names.length; k++) {
      var f = names[k];
      var from = String(cur[EVENT_FIX_FIELDS[f] - 1] == null ? '' : cur[EVENT_FIX_FIELDS[f] - 1]);
      var to = String(fields[f] == null ? '' : fields[f]);
      if (from !== to) changes.push({ field: f, from: from, to: to });
    }
    var keyChanged = !!(newId && newId !== msgId);
    if (keyChanged) changes.push({ field: 'msg_id', from: msgId, to: newId });
    if (!changes.length) return { ok: false, error: 'nothing_to_change',
                                  message: 'значения в строке уже такие' };

    // АУДИТ-СЛЕД ЖИВЁТ В САМОЙ СТРОКЕ: что было → что стало, кто и когда, причина. В отличие от
    // Лист1 (живая чужая таблица, свободной колонки нет) здесь место есть — и след неотделим от
    // правки: он пишется той же операцией, поэтому не может «не доехать».
    var at = new Date().toISOString();
    // Значения в ШТАМПЕ подрезаются: штамп кладётся В notes, а notes сам может быть предметом
    // правки — без подрезки каждая следующая правка вкладывала бы прошлый штамп в новый, и
    // ячейка росла бы в разы. Полные значения лежат в changes и в откате, там подрезки нет.
    function brief(v) {
      var s = String(v == null ? '' : v);
      return s.length > 60 ? (s.slice(0, 60) + '…') : s;
    }
    var diff = changes.map(function (c) {
      return c.field + ' ' + (brief(c.from) || '—') + '→' + (brief(c.to) || '—');
    }).join('; ');
    var stamp = '✏️ исправлено ' + at + ' ' + by + ': ' + diff + '; причина: ' + reason;
    var baseNotes = (fields.notes !== undefined) ? String(fields.notes) : String(cur[NOTES] || '');
    var newNotes = (baseNotes ? baseNotes + ' | ' : '') + stamp;
    var newStatus = (fields.status !== undefined) ? String(fields.status) : 'corrected';

    for (var k2 = 0; k2 < names.length; k2++) {
      var f2 = names[k2];
      if (f2 === 'notes' || f2 === 'status') continue;      // пишутся ниже, вместе со штампом
      tab.getRange(row, EVENT_FIX_FIELDS[f2]).setValue(fields[f2]);
    }
    tab.getRange(row, EVENT_FIX_FIELDS.notes).setValue(newNotes);
    tab.getRange(row, EVENT_FIX_FIELDS.status).setValue(newStatus);
    if (keyChanged) tab.getRange(row, MID + 1).setValue(newId);
    // кол.A (recorded_at) не пишется НИ ОДНОЙ веткой выше — это и есть сохранение метки записи.

    // пост-запись-верификация: перечитываем ровно эту строку
    var got = tab.getRange(row, 1, 1, cols).getValues()[0];
    function gcell(idx) { return (got[idx] === '' || got[idx] == null) ? '' : String(got[idx]); }
    var mismatches = [];
    if (gcell(REC) !== before.recorded_at) {
      mismatches.push({ field: 'recorded_at', expected: before.recorded_at, got: gcell(REC) });
    }
    for (var k3 = 0; k3 < changes.length; k3++) {
      var ch = changes[k3];
      var idx = (ch.field === 'msg_id') ? MID : (EVENT_FIX_FIELDS[ch.field] - 1);
      if (ch.field === 'notes' || ch.field === 'status') continue;   // сверяются ниже со штампом
      if (gcell(idx) !== ch.to) mismatches.push({ field: ch.field, expected: ch.to, got: gcell(idx) });
    }
    if (gcell(NOTES) !== newNotes) mismatches.push({ field: 'notes', expected: newNotes, got: gcell(NOTES) });
    if (gcell(ST) !== newStatus) mismatches.push({ field: 'status', expected: newStatus, got: gcell(ST) });
    if (mismatches.length) {
      return { ok: false, error: 'verify_failed', row: row, mismatches: mismatches,
               message: 'правка не подтвердилась перечитыванием строки — проверь лист руками' };
    }

    var after = {
      recorded_at: gcell(REC), msg_date: gcell(MD), group: gcell(GRP), bike: gcell(BIKE),
      event_type: gcell(ET), fuel: gcell(FUEL), mileage: gcell(MIL), photos: gcell(PH),
      notes: gcell(NOTES), status: gcell(ST), msg_id: gcell(MID), sender: gcell(SND)
    };

    // второй след — в боевой_лог (переживает и рестарт, и повторную правку той же строки).
    // Best-effort: след В СТРОКЕ уже лёг вместе с правкой, поэтому падение журнала не отменяет
    // операцию — но факт «не залогировано» виден в ответе, а не проглатывается.
    var logged = false;
    try {
      var lg = logWrite_({
        initiator: by, act: 'edit_event',
        args: 'msg_id=' + msgId + (keyChanged ? ('→' + newId) : '') + '; ' + diff +
              '; причина: ' + reason,
        result: 'ok', critical: 'правка строки события'
      });
      logged = !!(lg && lg.ok);
    } catch (eLog) {
      logged = false;
    }

    // ОТКАТ ОПИСАН ДАННЫМИ, а не словами: готовый обратный вызов той же операции.
    var rbFields = {};
    for (var k4 = 0; k4 < changes.length; k4++) {
      if (changes[k4].field === 'msg_id') continue;
      rbFields[changes[k4].field] = changes[k4].from;
    }
    rbFields.notes = before.notes;
    rbFields.status = before.status;

    return {
      ok: true, row: row, key: { old: msgId, new: (keyChanged ? newId : msgId) },
      recorded_at: before.recorded_at, before: before, after: after,
      audit: { at: at, by: by, reason: reason, changes: changes, logged: logged },
      rollback: { action: 'edit_event', msg_id: (keyChanged ? newId : msgId),
                  new_msg_id: msgId, fields: rbFields },
      verified: true
    };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
}


/** Номер байка из названия (последнее число ≥3 цифр, кроме кубатуры). Зеркало find_bike. */
function plateOf_(text) {
  var CC = { '125':1,'150':1,'155':1,'300':1,'350':1,'400':1,'500':1,'650':1,'700':1,'750':1,'900':1 };
  var nums = (String(text || '').toLowerCase().match(/\d{3,}/g) || []).filter(function (n) { return !CC[n]; });
  return nums.length ? nums[nums.length - 1] : '';
}


/**
 * READ-ONLY: последние обслуживания байка из листа «события» (сервис-на-пробеге для карточки).
 * Резолв байка ПО НОМЕРУ (plate). Newest-first, потолок 30. Рабочих таблиц НЕ касается.
 * payload: { bike, limit=8 } → { ok, bike, items:[{recorded_at,msg_date,event_type,mileage,notes}] }
 */
function readEvents(payload) {
  var p = payload || {};
  var limit = Math.min(Number(p.limit) || 8, 30);
  var want = plateOf_(String(p.bike || ''));
  var tab = getBotTab_(BOTDATA.TABS.EVENTS);
  var last = tab.getLastRow();
  if (last < 2 || !want) return { ok: true, bike: String(p.bike || ''), items: [] };
  var cols = BOTDATA.EVENT_HEADERS.length;
  var data = tab.getRange(2, 1, last - 1, cols).getValues();
  // EVENT_HEADERS: recorded_at,msg_date,group,bike,event_type,fuel,mileage,photos,notes,status,msg_id
  var REC = 0, MD = 1, GRP = 2, BIKE = 3, ET = 4, MIL = 6, NOTES = 8, ST = 9, MID = 10;
  var out = [];
  for (var i = data.length - 1; i >= 0; i--) {          // снизу вверх = newest-first
    var r = data[i];
    if (plateOf_(String(r[BIKE] || '')) !== want) continue;
    var et = String(r[ET] || '');
    var notes = String(r[NOTES] || '');
    var mil = (r[MIL] === '' || r[MIL] == null) ? '' : String(r[MIL]);
    if (et !== 'repair' && !notes && !mil) continue;     // только осмысленные записи
    // КЛЮЧ, ГРУППА И СТАТУС В ВЫДАЧЕ (04.08.2026): правка и удаление строки работают ТОЛЬКО по
    // точному ключу, а узнать его было неоткуда — чтение истории ключ не отдавало вовсе, и
    // ошибочную строку нечем было адресовать. Поля добавлены, прежние на месте (карточка байка
    // читает work/km — её разбор не задет).
    out.push({ recorded_at: String(r[REC] || ''), msg_date: String(r[MD] || ''),
               event_type: et, mileage: mil, notes: notes,
               msg_id: String(r[MID] || ''), group: String(r[GRP] || ''),
               status: String(r[ST] || '') });
    if (out.length >= limit) break;
  }
  return { ok: true, bike: String(p.bike || ''), items: out };
}


/**
 * Отменить последнюю активную запись (status≠void).
 * payload: { group } — если задан, отменяет последнюю запись ИМЕННО этого кошелька.
 * Помечает строку status=void (не удаляет — обратимо), возвращает что отменил.
 */
function voidLastTransaction(payload) {
  const p = payload || {};
  const group = p.group ? String(p.group) : '';
  const tab = getBotTab_(BOTDATA.TABS.TX);
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, voided: false, message: 'нет записей' };

  // col 3=group, 5=amount, 6=currency, 10=description, 12=status
  const rng = tab.getRange(2, 1, last - 1, BOTDATA.TX_HEADERS.length);
  const rows = rng.getValues();
  const statusCol = BOTDATA.TX_HEADERS.indexOf('status'); // 0-based внутри строки

  // идём с конца — ищем последнюю не-void (и нужной группы, если задана)
  for (let i = rows.length - 1; i >= 0; i--) {
    const r = rows[i];
    const grp = String(r[2]);
    const status = String(r[statusCol]).toLowerCase();
    if (status === 'void') continue;
    if (group && grp !== group) continue;
    // нашли — помечаем void
    const sheetRow = i + 2; // +2: шапка + 1-based
    tab.getRange(sheetRow, statusCol + 1).setValue('void');
    const amount = Number(r[4]) || 0;
    const cur = String(r[5] || 'THB').toUpperCase();
    const desc = String(r[9] || '');
    return {
      ok: true, voided: true,
      group: grp, amount: amount, currency: cur, description: desc,
      balance: computeBalance_(group || grp),
    };
  }
  return { ok: true, voided: false, message: 'нет активных записей для отмены' };
}


/**
 * Считает текущий баланс по каждой валюте = сумма всех транзакций (кроме void).
 * Возвращает { THB: ..., EUR: ..., PASSPORT: ... }
 */
function computeBalance_(group) {
  const tab = getBotTab_(BOTDATA.TABS.TX);
  const last = tab.getLastRow();
  const out = {};
  if (last < 2) return out;

  // читаем group(3), amount(5), currency(6), status(12)
  const rows = tab.getRange(2, 3, last - 1, 10).getValues();
  for (const r of rows) {
    const grp = r[0];          // col 3
    const amount = r[2];       // col 5
    const currency = r[3];     // col 6
    const status = r[9];       // col 12 (status)
    if (String(status).toLowerCase() === 'void') continue;  // отменённые не считаем
    if (group && String(grp) !== String(group)) continue;
    const cur = String(currency || 'THB').toUpperCase();
    out[cur] = (out[cur] || 0) + (Number(amount) || 0);
  }
  for (const k of Object.keys(out)) out[k] = Math.round(out[k] * 100) / 100;
  return out;
}


/**
 * Балансы по всем кошелькам (группам) сразу + общий итог.
 */
function computeBalanceAll_() {
  const tab = getBotTab_(BOTDATA.TABS.TX);
  const last = tab.getLastRow();
  const byWallet = {};
  const total = {};
  if (last < 2) return { wallets: {}, total: {} };

  const rows = tab.getRange(2, 3, last - 1, 10).getValues();
  for (const r of rows) {
    const status = r[9];       // col 12 (status)
    if (String(status).toLowerCase() === 'void') continue;  // отменённые не считаем
    const grp = String(r[0] || '—');
    const cur = String(r[3] || 'THB').toUpperCase();
    const amt = Number(r[2]) || 0;
    byWallet[grp] = byWallet[grp] || {};
    byWallet[grp][cur] = (byWallet[grp][cur] || 0) + amt;
    total[cur] = (total[cur] || 0) + amt;
  }
  const round = o => { for (const k in o) o[k] = Math.round(o[k] * 100) / 100; };
  for (const w in byWallet) round(byWallet[w]);
  round(total);
  return { wallets: byWallet, total: total };
}


/**
 * Сверка: бот сравнивает свой баланс с тем что назвал Пым.
 * payload: { currency, pym_balance, note, group }
 * Если задан group — сверяет баланс ИМЕННО этого кошелька.
 */
function checkBalance(payload) {
  const p = payload || {};
  const cur = String(p.currency || 'THB').toUpperCase();
  const bot = computeBalance_(p.group)[cur] || 0;
  const pym = Number(p.pym_balance);
  const diff = Math.round((bot - pym) * 100) / 100;

  const tab = getBotTab_(BOTDATA.TABS.BALANCE);
  tab.appendRow([
    new Date().toISOString(), cur, bot,
    isNaN(pym) ? '' : pym,
    isNaN(pym) ? '' : diff,
    (p.group ? p.group + ' | ' : '') + (p.note || ''),
  ]);

  return {
    ok: true,
    currency: cur,
    group: p.group || null,
    bot_balance: bot,
    pym_balance: isNaN(pym) ? null : pym,
    diff: isNaN(pym) ? null : diff,
    match: isNaN(pym) ? null : Math.abs(diff) < 0.01,
  };
}


/**
 * Текущий баланс. Если задан group — только этот кошелёк.
 * Без group — балансы по всем кошелькам + общий итог.
 */
function getBalance(payload) {
  const group = payload && payload.group;
  if (group) {
    return { ok: true, group: group, balance: computeBalance_(group) };
  }
  const all = computeBalanceAll_();
  return { ok: true, balance: all.total, wallets: all.wallets };
}


/**
 * === ТО-ТРЕКЕР ===
 * Обновить/создать запись ТО байка. Считает next_km и статус (ok/due/overdue).
 * payload: { bike, topic_id, service_type, current_km, last_service_km, interval_km, note }
 * Любое поле опционально — обновляем только переданное, остальное берём из существующей строки.
 */
function serviceUpsert(payload) {
  const p = payload || {};
  const bike = String(p.bike || '').trim();
  const stype = String(p.service_type || 'oil').trim();
  if (!bike) return { ok: false, error: 'no_bike' };

  const tab = getBotTab_(BOTDATA.TABS.SERVICE);
  const H = BOTDATA.SERVICE_HEADERS;
  const last = tab.getLastRow();
  let rowIdx = -1, row = null;

  // Матчинг по НОМЕРУ байка + service_type (а НЕ по полному имени), чтобы
  // 'NMAX 155 BLACK GOLD 4255' (имя темы) и 'NMAX 155CC BLACK GOLD PHUKET 4255'
  // (каноничное из Лист1) считались одной строкой и не плодили дубли.
  // Номер не извлекается (null) → fallback на точное сравнение имени
  // (байки без номера, напр. 'XSR 155 GREEN').
  const inPlate = plateFromName_(bike);
  if (last >= 2) {
    const data = tab.getRange(2, 1, last - 1, H.length).getValues();
    for (let i = 0; i < data.length; i++) {
      const rowBike = String(data[i][1]).trim();
      const rowType = String(data[i][3]).trim();
      if (rowType !== stype) continue;   // разные типы ТО (oil/gear) НЕ схлопываем
      const match = inPlate
        ? (plateFromName_(rowBike) === inPlate)
        : (rowBike === bike);
      if (match) { rowIdx = i + 2; row = data[i]; break; }
    }
  }

  // текущие значения (из строки или из payload)
  const get = (col, fallback) => {
    const idx = H.indexOf(col);
    const fromRow = row ? row[idx] : '';
    return fromRow !== '' && fromRow != null ? fromRow : fallback;
  };

  const current_km     = num_(p.current_km     != null ? p.current_km     : get('current_km', ''));
  const last_service_km= num_(p.last_service_km!= null ? p.last_service_km: get('last_service_km', ''));
  const interval_km    = num_(p.interval_km    != null ? p.interval_km    : get('interval_km', ''));
  const note           = p.note != null ? p.note : get('note', '');
  const topic_id       = p.topic_id != null ? p.topic_id : get('topic_id', '');
  const pinned         = get('pinned_msg_id', '');
  const last_reminded  = get('last_reminded_at', '');

  const next_km = (last_service_km && interval_km) ? (last_service_km + interval_km) : '';
  let status = 'ok';
  if (next_km && current_km) {
    if (current_km >= next_km) status = 'overdue';
    else if (next_km - current_km <= 300) status = 'due';   // подходит (≤300 км)
  }

  // Имя для записи — всегда каноничное из Лист1 (по номеру); иначе как пришло.
  const canonName = canonicalBikeName_(bike) || bike;

  const rowData = [
    new Date(), canonName, topic_id, stype, current_km,
    last_service_km, interval_km, next_km, status,
    pinned, last_reminded, note
  ];

  if (rowIdx > 0) tab.getRange(rowIdx, 1, 1, H.length).setValues([rowData]);
  else tab.appendRow(rowData);

  return { ok: true, bike: canonName, service_type: stype, current_km: current_km,
           next_km: next_km, status: status, km_left: next_km && current_km ? next_km - current_km : null };
}

/**
 * Все записи ТО + те, что требуют внимания (due/overdue).
 */
function serviceList(payload) {
  const tab = getBotTab_(BOTDATA.TABS.SERVICE);
  const H = BOTDATA.SERVICE_HEADERS;
  const last = tab.getLastRow();
  const all = [], attention = [];
  if (last < 2) return { ok: true, items: [], attention: [] };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  for (const r of data) {
    const item = {};
    H.forEach((h, i) => item[h] = r[i]);
    all.push(item);
    if (item.status === 'due' || item.status === 'overdue') attention.push(item);
  }
  return { ok: true, items: all, attention: attention };
}

/**
 * Удалить ОДНУ строку ТО из «обслуживание» по якорю (bike + service_type + updated_at).
 * НАДЁЖНАЯ идентификация: updated_at (мс-точность) — фактически уникален per строка.
 * Защита: 0 матчей → not_found; >1 → ambiguous (НЕ удаляет, вернёт кандидатов); ровно 1 → deleteRow.
 * Все 3 параметра ОБЯЗАТЕЛЬНЫ. Необратимо → аудит client-side 4.1 (_REDZONE_ACTIONS).
 * body: { bike, service_type, updated_at(ISO) }
 */
function serviceDelete_(body) {
  var p = body || {};
  var bike = String(p.bike == null ? '' : p.bike).trim();
  var stype = String(p.service_type == null ? '' : p.service_type).trim();
  var anchor = String(p.updated_at == null ? '' : p.updated_at).trim();
  if (!bike || !stype || !anchor) {
    return { ok: false, error: 'need_params', message: 'нужны bike + service_type + updated_at' };
  }
  try {
    var tab = getBotTab_(BOTDATA.TABS.SERVICE);
    var H = BOTDATA.SERVICE_HEADERS;
    var last = tab.getLastRow();
    if (last < 2) return { ok: false, error: 'not_found' };
    var data = tab.getRange(2, 1, last - 1, H.length).getValues();
    var inPlate = plateFromName_(bike);
    var matches = [];
    for (var i = 0; i < data.length; i++) {
      var rowBike = String(data[i][1]).trim();
      var rowType = String(data[i][3]).trim();
      if (rowType !== stype) continue;
      var sameBike = inPlate ? (plateFromName_(rowBike) === inPlate)
                             : (rowBike.toLowerCase() === bike.toLowerCase());
      if (!sameBike) continue;
      var u = data[i][0];
      var uStr = (u && u.toISOString) ? u.toISOString() : String(u);
      if (uStr === anchor) {
        matches.push({ sheetRow: i + 2,
          snapshot: { updated_at: uStr, bike: rowBike, service_type: rowType,
            current_km: data[i][4], last_service_km: data[i][5], next_km: data[i][7], status: data[i][8] } });
      }
    }
    if (matches.length === 0) return { ok: false, error: 'not_found', bike: bike, service_type: stype, updated_at: anchor };
    if (matches.length > 1) {
      return { ok: false, error: 'ambiguous', count: matches.length,
               candidates: matches.map(function (m) { return m.snapshot; }) };
    }
    var hit = matches[0];
    tab.deleteRow(hit.sheetRow);
    return { ok: true, deleted: true, row: hit.sheetRow, snapshot: hit.snapshot };
  } catch (err) {
    return { ok: false, error: 'delete_failed', message: String(err) };
  }
}

/**
 * Записать id закреплённого сообщения / время напоминания (чтобы потом обновлять/откреплять).
 * payload: { bike, service_type, pinned_msg_id, last_reminded_at }
 */
function serviceSetPin(payload) {
  const p = payload || {};
  const bike = String(p.bike || '').trim();
  const stype = String(p.service_type || 'oil').trim();
  const tab = getBotTab_(BOTDATA.TABS.SERVICE);
  const H = BOTDATA.SERVICE_HEADERS;
  const last = tab.getLastRow();
  if (last < 2) return { ok: false, error: 'not_found' };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][1]).trim() === bike && String(data[i][3]).trim() === stype) {
      if (p.pinned_msg_id != null)    tab.getRange(i + 2, H.indexOf('pinned_msg_id') + 1).setValue(p.pinned_msg_id);
      if (p.last_reminded_at != null) tab.getRange(i + 2, H.indexOf('last_reminded_at') + 1).setValue(p.last_reminded_at);
      return { ok: true };
    }
  }
  return { ok: false, error: 'not_found' };
}

function num_(v) {
  if (v === '' || v == null) return '';
  const n = Number(String(v).replace(/[^\d.-]/g, ''));
  return isNaN(n) ? '' : n;
}


/**
 * === СОСТОЯНИЕ БАЙКА (Этап 1 трекинга) ===
 * Bot-owned слой: одна строка на байк (ключ = bike, ТОЧНОЕ название, как везде в системе).
 * upsert по bike — переданные поля перезаписывают, НЕ переданные (undefined) сохраняются из строки.
 * status (если передан) валидируется по STATE_STATUSES; пустой '' допускается (ещё не выставлен).
 * body: { bike(обяз.), status, location, booking_id, client, date_out, date_due,
 *         date_back, service_name, last_event_msg_id }
 */
function stateUpsert_(body) {
  const p = body || {};
  const bike = String(p.bike == null ? '' : p.bike).trim();
  if (!bike) return { ok: false, error: 'no_bike', message: 'нужно точное название байка (bike)' };

  // Валидация статуса: пустой/не переданный — ок; иначе должен быть из списка.
  if (p.status != null && String(p.status).trim() !== '' &&
      STATE_STATUSES.indexOf(String(p.status).trim()) === -1) {
    return { ok: false, error: 'bad_status', status: String(p.status),
             allowed: STATE_STATUSES, message: 'недопустимый статус состояния' };
  }

  const tab = getBotTab_(BOTDATA.TABS.STATE);
  const H = BOTDATA.STATE_HEADERS;
  const last = tab.getLastRow();
  let rowIdx = -1, row = null;
  if (last >= 2) {
    const keys = tab.getRange(2, 1, last - 1, 1).getValues();   // кол. bike
    for (let i = 0; i < keys.length; i++) {
      if (String(keys[i][0]).trim() === bike) { rowIdx = i + 2; break; }
    }
    if (rowIdx > 0) row = tab.getRange(rowIdx, 1, 1, H.length).getValues()[0];
  }

  // merge: переданное (не undefined) перезаписывает; иначе из строки; иначе ''.
  const merge = (col) => {
    if (p[col] != null) return String(p[col]);
    const idx = H.indexOf(col);
    return row ? row[idx] : '';
  };

  const rowData = [
    bike,
    merge('status'),
    merge('location'),
    merge('booking_id'),
    merge('client'),
    merge('date_out'),
    merge('date_due'),
    merge('date_back'),
    merge('service_name'),
    merge('last_event_msg_id'),
    new Date(),   // updated — всегда сейчас
  ];

  let targetRow;
  if (rowIdx > 0) {
    tab.getRange(rowIdx, 1, 1, H.length).setValues([rowData]);
    targetRow = rowIdx;
  } else {
    tab.appendRow(rowData);
    targetRow = tab.getLastRow();
  }

  // post-write verify: перечитать записанную строку (flush+getValues). Последний столбец
  // updated (new Date() c мс — лист хранит с усечением) из сверки ИСКЛЮЧАЕМ, иначе ложный mismatch.
  const verifyCols = H.length - 1;
  const full_address = sheetFullAddr_(tab.getParent().getId(), tab.getName(),
                                      tab.getRange(targetRow, 1, 1, H.length).getA1Notation());
  const vr = verifyWrite_(tab, targetRow, 1, 1, verifyCols, [rowData.slice(0, verifyCols)]);
  if (!vr.ok)
    return { ok: false, error: 'verify_failed', full_address: full_address, mismatches: vr.mismatches };

  const item = {};
  H.forEach((h, i) => item[h] = rowData[i]);
  return { ok: true, upserted: rowIdx > 0 ? 'updated' : 'inserted', bike: bike, item: item,
           verified: true, full_address: full_address };
}

/**
 * Прочитать состояние одного байка по точному названию.
 * body: { bike } → { ok, item } | { ok:false, error:'not_found' }
 */
function stateGet_(body) {
  const p = body || {};
  const bike = String(p.bike == null ? '' : p.bike).trim();
  if (!bike) return { ok: false, error: 'no_bike' };
  const tab = getBotTab_(BOTDATA.TABS.STATE);
  const H = BOTDATA.STATE_HEADERS;
  const last = tab.getLastRow();
  if (last < 2) return { ok: false, error: 'not_found', bike: bike };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  for (let i = 0; i < data.length; i++) {
    if (String(data[i][0]).trim() === bike) {
      const item = {};
      H.forEach((h, j) => item[h] = data[i][j]);
      return { ok: true, item: item };
    }
  }
  return { ok: false, error: 'not_found', bike: bike };
}

/**
 * Срез состояния всего парка (кто где сейчас).
 * → { ok, items:[{bike,status,location,...}], total }
 */
function stateList_() {
  const tab = getBotTab_(BOTDATA.TABS.STATE);
  const H = BOTDATA.STATE_HEADERS;
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [], total: 0 };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  const items = [];
  for (let i = 0; i < data.length; i++) {
    const item = {};
    H.forEach((h, j) => item[h] = data[i][j]);
    items.push(item);
  }
  return { ok: true, items: items, total: items.length };
}


/**
 * === НАДЗИРАТЕЛЬ ВАЖНОГО ===
 * Добавить важный пункт (ДТП, ремонт, просрочка...). Создаётся со статусом open.
 * payload: { chat_id, topic_id, group, kind, summary, pinned_msg_id, confirmed_by, note }
 */
function importantAdd(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.IMPORTANT);
  const now = new Date();
  tab.appendRow([
    now, String(p.chat_id || ''), String(p.topic_id || ''), p.group || '',
    p.kind || 'other', p.summary || '',
    p.pinned_msg_id || '', now,    // last_reminded_at = время создания
    'open', p.confirmed_by || '', '', p.note || ''
  ]);
  return { ok: true, added: true };
}

/**
 * Список важного. payload: { status } — фильтр (open/done), пусто = все.
 */
function importantList(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.IMPORTANT);
  const H = BOTDATA.IMPORTANT_HEADERS;
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [] };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  const items = [];
  for (let i = 0; i < data.length; i++) {
    const it = { _row: i + 2 };
    H.forEach((h, j) => it[h] = data[i][j]);
    if (p.status && String(it.status) !== p.status) continue;
    items.push(it);
  }
  return { ok: true, items: items };
}

/**
 * Какие важные пункты пора напомнить (open и прошло >= days дней с last_reminded_at).
 * payload: { days } (по умолчанию 3)
 */
function importantDueReminders(payload) {
  const p = payload || {};
  const days = Number(p.days) || 3;
  const now = new Date();
  const res = importantList({ status: 'open' });
  const due = [];
  for (const it of res.items) {
    const last = it.last_reminded_at ? new Date(it.last_reminded_at) : null;
    if (!last || (now - last) / 86400000 >= days) due.push(it);
  }
  return { ok: true, items: due };
}

/**
 * Отметить что напомнили (обновить last_reminded_at и, если надо, новый pinned_msg_id).
 * payload: { row, pinned_msg_id }
 */
function importantTouch(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.IMPORTANT);
  const H = BOTDATA.IMPORTANT_HEADERS;
  if (!p.row) return { ok: false, error: 'no_row' };
  tab.getRange(p.row, H.indexOf('last_reminded_at') + 1).setValue(new Date());
  if (p.pinned_msg_id != null) {
    tab.getRange(p.row, H.indexOf('pinned_msg_id') + 1).setValue(p.pinned_msg_id);
  }
  return { ok: true };
}

/**
 * Закрыть важный пункт (выполнено, открепляем). payload: { row, confirmed_by }
 */
function importantClose(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.IMPORTANT);
  const H = BOTDATA.IMPORTANT_HEADERS;
  if (!p.row) return { ok: false, error: 'no_row' };
  tab.getRange(p.row, H.indexOf('status') + 1).setValue('done');
  tab.getRange(p.row, H.indexOf('closed_at') + 1).setValue(new Date());
  if (p.confirmed_by) tab.getRange(p.row, H.indexOf('confirmed_by') + 1).setValue(p.confirmed_by);
  return { ok: true, closed: true };
}


/**
 * === АУДИТОР (надзор за ботом) ===
 * Записать действие бота в журнал аудита.
 * payload: { group, topic_id, user_request, tool, tool_args, claimed_result,
 *            verdict, severity, detail, suggested_fix, status }
 */
function auditLog(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.AUDIT);
  tab.appendRow([
    new Date(), p.group || '', String(p.topic_id || ''),
    String(p.user_request || '').slice(0, 500),
    p.tool || '', String(p.tool_args || '').slice(0, 1000),
    String(p.claimed_result || '').slice(0, 1000),
    p.verdict || 'ok', p.severity || '', String(p.detail || '').slice(0, 1000),
    String(p.suggested_fix || '').slice(0, 1000), p.status || 'new'
  ]);
  return { ok: true, logged: true };
}

/**
 * Список аудита. payload: { verdict, status, since } — фильтры (опц).
 * since — ISO-строка/дата: вернуть только записи новее.
 */
function auditList(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.AUDIT);
  const H = BOTDATA.AUDIT_HEADERS;
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, items: [] };
  const data = tab.getRange(2, 1, last - 1, H.length).getValues();
  const sinceDate = p.since ? new Date(p.since) : null;
  const items = [];
  for (let i = 0; i < data.length; i++) {
    const it = { _row: i + 2 };
    H.forEach((h, j) => it[h] = data[i][j]);
    if (p.verdict && String(it.verdict) !== p.verdict) continue;
    if (p.status && String(it.status) !== p.status) continue;
    if (sinceDate && it.logged_at && new Date(it.logged_at) < sinceDate) continue;
    items.push(it);
  }
  return { ok: true, items: items };
}

/**
 * Обновить статус записи аудита (напр. 'resolved' после правки/апрува).
 * payload: { row, status }
 */
function auditUpdate(payload) {
  const p = payload || {};
  const tab = getBotTab_(BOTDATA.TABS.AUDIT);
  const H = BOTDATA.AUDIT_HEADERS;
  if (!p.row) return { ok: false, error: 'no_row' };
  if (p.status) tab.getRange(p.row, H.indexOf('status') + 1).setValue(p.status);
  return { ok: true };
}


/**
 * Сводка транзакций за период (today/week/month) — для дневной сводки Splinter.
 * Возвращает суммы по категориям + список.
 */
function getTxSummary(period) {
  const tab = getBotTab_(BOTDATA.TABS.TX);
  const last = tab.getLastRow();
  if (last < 2) return { ok: true, period: period, total: {}, by_category: {}, items: [] };

  const now = new Date();
  let since = new Date(0);
  if (period === 'today') since = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  else if (period === 'week') since = new Date(now.getTime() - 7 * 864e5);
  else if (period === 'month') since = new Date(now.getFullYear(), now.getMonth(), 1);

  const rows = tab.getRange(2, 1, last - 1, BOTDATA.TX_HEADERS.length).getValues();
  const byCat = {};
  const total = {};
  const items = [];

  for (const r of rows) {
    const recorded = new Date(r[0]);
    if (recorded < since) continue;
    const amount = Number(r[4]) || 0;
    const cur = String(r[5] || 'THB').toUpperCase();
    const cat = r[6] || 'other';

    total[cur] = (total[cur] || 0) + amount;
    byCat[cat] = byCat[cat] || {};
    byCat[cat][cur] = (byCat[cat][cur] || 0) + amount;

    items.push({
      date: r[1], sender: r[3], amount: amount, currency: cur,
      category: cat, bike: r[7], description: r[9],
    });
  }
  return { ok: true, period: period, total: total, by_category: byCat, items: items };
}


/**
 * РУЧНОЙ ТЕСТ записи. Run → testBotData.
 */
function testBotData() {
  console.log('1) addTransaction (аренда +4900)');
  console.log(JSON.stringify(addTransaction({
    msg_date: '2026-05-27', group: 'Money Cashflow', sender: '@Pleummmm',
    amount: 4900, currency: 'THB', category: 'rental',
    bike: 'ADV 8004', deposit: 'passport', description: 'ADV 8004 rental',
    raw: 'ADV 8004 +4,900 Bath 1 passport', msg_id: 'test-1'
  })));

  console.log('2) addTransaction (зарплата -5000)');
  console.log(JSON.stringify(addTransaction({
    msg_date: '2026-05-27', group: 'Money Cashflow', sender: '@Pleummmm',
    amount: -5000, currency: 'THB', category: 'salary',
    description: 'Earth salary', raw: 'Earth salary -5000', msg_id: 'test-2'
  })));

  console.log('3) getBalance');
  console.log(JSON.stringify(getBalance()));

  console.log('4) checkBalance (Пым сказал -100)');
  console.log(JSON.stringify(checkBalance({ currency: 'THB', pym_balance: -100 })));

  console.log('5) addEvent (байк сдан)');
  console.log(JSON.stringify(addEvent({
    msg_date: '2026-05-27', group: 'การบำรุงรักษา', bike: 'NMAX 7530',
    event_type: 'return', fuel: 'half', mileage: '12450', photos: 5,
    notes: 'вернулся, фото есть', msg_id: 'test-ev-1'
  })));
}