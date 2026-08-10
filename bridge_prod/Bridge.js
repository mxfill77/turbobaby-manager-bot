/**
 * TurboBaby Bridge — главный entry-point
 * 
 * Web App URL: после deploy → доступен по https://script.google.com/macros/s/.../exec
 * 
 * Все запросы идут через GET с параметрами:
 *   ?token=XXX&action=YYY&...
 * 
 * Примеры:
 *   ?token=XXX&action=ping
 *   ?token=XXX&action=fleet
 *   ?token=XXX&action=clients&filter=active
 *   ?token=XXX&action=anomalies
 *   ?token=XXX&action=finance&period=month
 *   ?token=XXX&action=client_history&phone=+7912345
 */


/**
 * Главный обработчик GET запросов от Python бота.
 */
function doGet(e) {
  try {
    const params = e?.parameter || {};
    
    // Авторизация
    if (!verifyToken(params.token)) {
      return jsonResponse({
        ok: false,
        error: 'unauthorized',
        message: 'Invalid or missing token'
      }, 401);
    }

    const action = params.action || 'ping';
    
    // === РОУТИНГ ===
    switch (action) {
      
      // --- Проверка живой ли Bridge ---
      case 'ping':
        return jsonResponse({
          ok: true,
          version: CONFIG.VERSION,
          time: new Date().toISOString(),
          message: 'TurboBaby Bridge alive'
        });

      // --- Парк (38 байков, статусы) ---
      // params.cells=1 — попросить РАЗМЕТКУ клеток ТО (value/empty/text, см. cellState_).
      // Без параметра ответ БАЙТ-В-БАЙТ прежний: разметка добавляется, ничего не заменяет.
      case 'fleet':
        return jsonResponse({
          ok: true,
          action: 'fleet',
          data: getFleetStatus(params.cells)
        });

      // --- Активные аренды + сводка ---
      case 'clients':
        const filter = params.filter || 'active';
        return jsonResponse({
          ok: true,
          action: 'clients',
          filter: filter,
          data: getClients(filter)
        });

      // --- История обслуживаний по байку (read-only лист «события»; сервис-на-пробеге для карточки) ---
      case 'read_events':
        return jsonResponse(Object.assign({ action: 'read_events' },
          readEvents({ bike: params.bike || '', limit: params.limit })));

      // --- Очередь оркестратора: задачи по статусу (деф. new), newest-first (дешёвый опрос демоном) ---
      case 'get_pending':
        return jsonResponse(Object.assign({ action: 'get_pending' },
          getPending_({ status: params.status, lane: params.lane })));

      // --- Расчёт цены аренды (read-only, ничего не пишет) ---
      case 'quote_price':
        return jsonResponse(Object.assign({ action: 'quote_price' },
          quotePrice({ bike: params.bike, date_start: params.date_start, date_end: params.date_end })));

      // --- Аномалии (просрочки, долги, странные записи) ---
      case 'anomalies':
        return jsonResponse({
          ok: true,
          action: 'anomalies',
          data: getAnomalies()
        });

      // --- История клиента по телефону или имени ---
      case 'client_history':
        const search = params.phone || params.name;
        if (!search) {
          return jsonResponse({
            ok: false,
            error: 'missing_param',
            message: 'Provide ?phone=... or ?name=...'
          }, 400);
        }
        return jsonResponse({
          ok: true,
          action: 'client_history',
          query: search,
          data: getClientHistory(search)
        });

      // --- Финансы (доход за период) ---
      case 'finance':
        const period = params.period || 'today';
        return jsonResponse({
          ok: true,
          action: 'finance',
          period: period,
          data: getFinance(period)
        });

      // --- Возвраты в ближайшие N дней ---
      case 'returns_soon':
        const days = parseInt(params.days || '3');
        return jsonResponse({
          ok: true,
          action: 'returns_soon',
          days: days,
          data: getReturnsSoon(days)
        });

      // --- Daily Pulse: вся сводка одним запросом ---
      case 'daily_pulse':
        return jsonResponse({
          ok: true,
          action: 'daily_pulse',
          time: new Date().toISOString(),
          data: getDailyPulse()
        });

      // --- Список доступных action ---
      case 'help':
        return jsonResponse({
          ok: true,
          version: CONFIG.VERSION,
          actions: [
            'ping', 'fleet', 'clients', 'anomalies',
            'client_history', 'finance', 'returns_soon', 'daily_pulse', 'get_pending'
          ],
          examples: {
            ping: '?token=XXX&action=ping',
            fleet: '?token=XXX&action=fleet',
            clients_active: '?token=XXX&action=clients&filter=active',
            clients_overdue: '?token=XXX&action=clients&filter=overdue',
            client_history: '?token=XXX&action=client_history&phone=%2B79123456789',
            finance_month: '?token=XXX&action=finance&period=month',
            returns_soon: '?token=XXX&action=returns_soon&days=7',
            quote_price: '?token=XXX&action=quote_price&bike=4957&date_start=08.07.2026&date_end=15.07.2026',
          }
        });
        
        case 'read_doc':
     return handleReadDoc_(e);
   case 'list_brain':
     return handleListBrain_(e);

      // --- Зоны доставки (read-only) ---
      case 'delivery_zones_get':
        return jsonResponse(Object.assign({ action: 'delivery_zones_get' }, deliveryZonesGet_()));

      default:
        return jsonResponse({
          ok: false,
          error: 'unknown_action',
          message: `Unknown action: ${action}. Try ?action=help`
        }, 400);
    }

  } catch (err) {
    // Логируем ошибку для отладки
    console.error('Bridge error:', err.message, err.stack);
    return jsonResponse({
      ok: false,
      error: 'internal_error',
      message: err.message,
      stack: err.stack
    }, 500);
  }
}


/**
 * POST endpoint — запись данных Splinter (транзакции, события, сверка).
 *
 * Тело запроса — JSON:
 *   { "token": "...", "action": "add_transaction", ...поля }
 *
 * Actions:
 *   add_transaction  — приход/расход в лист "транзакции"
 *   add_event        — событие по байку (приёмка/сдача/ремонт)
 *   check_balance    — сверить баланс бота с названным Пымом
 *   get_balance      — текущий баланс (можно и POST'ом)
 *   tx_summary       — сводка за период (period: today/week/month)
 *
 * ВАЖНО: записываем только в отдельную таблицу "TurboBaby Bot Data".
 * Рабочие таблицы (CRM, Зарплаты) этот endpoint НЕ трогает.
 */
// === ТОКЕН-ЗАМОК (4.2): одноразовые краткоживущие билеты для agent-записей ===
var WRITE_TICKET_TTL = 120;   // сек

/** Выдать одноразовый билет (origin=agent санкционирует боевую запись). Хранится в CacheService, TTL 120с. */
function issueWriteTicket_(body) {
  var token = Utilities.getUuid();
  CacheService.getScriptCache().put('wt_' + token, '1', WRITE_TICKET_TTL);
  return { ok: true, ticket: token, ttl: WRITE_TICKET_TTL };
}

/** Проверить+ПОГАСИТЬ билет. true если валиден (был в кэше и не использован), иначе false. Одноразовый. */
function consumeWriteTicket_(token) {
  if (!token) return false;
  var cache = CacheService.getScriptCache();
  var key = 'wt_' + token;
  if (cache.get(key) === null) return false;   // нет/истёк/уже погашен
  cache.remove(key);                            // гасим — повторное использование невозможно
  return true;
}


function doPost(e) {
  try {
    let body = {};
    try {
      body = JSON.parse(e?.postData?.contents || '{}');
    } catch (parseErr) {
      return jsonResponse({ ok: false, error: 'bad_json', message: parseErr.message }, 400);
    }

    if (!verifyToken(body.token)) {
      return jsonResponse({ ok: false, error: 'unauthorized' }, 401);
    }

    const action = body.action || '';

    // === ТОКЕН-ЗАМОК боевой записи (4.2) — централизованный гейт ===
    // Защищаем ТОЛЬКО agent-записи. origin=human/отсутствует → пропускаем (замок спит, люди как сейчас).
    // origin=agent на КРАСНОМ экшене → нужен валидный одноразовый билет, иначе ЖЁСТКИЙ отказ + лог rejected.
    var REDZONE_LOCK = {
      set_fleet_oil: 1, set_fleet_service: 1, add_transaction: 1, void_last: 1,
      create_booking: 1, activate_booking: 1, close_booking: 1, delete_event: 1,
      edit_event: 1,                                                // правка строки НА МЕСТЕ: затирает прежнее значение
      ocr_passport: 1, save_passport: 1, upload_passport_photo: 1,  // B2: внешний вызов + Drive + Bot Data
      make_contract: 1,                                             // B3: Drive-запись договора + чтение CRM
      set_caps: 1, toggle_cap: 1,                                   // капы: запись в живой «Календарь бронирования»
      delivery_zones_set: 1                                         // зоны доставки: запись в живой «Календарь бронирования»
    };
    if (REDZONE_LOCK[action] && String(body.origin || 'human') === 'agent') {
      var _tok = body.ticket || '';
      if (!consumeWriteTicket_(_tok)) {
        try {
          logWrite_({ initiator: 'agent', act: action,
                      args: 'origin=agent, ticket=' + (_tok ? 'invalid/expired' : 'none'),
                      result: 'rejected', critical: 'токен-замок 4.2' });
        } catch (e) {}
        return jsonResponse({ ok: false, error: 'no_ticket',
          message: 'agent-запись без валидного билета отклонена (токен-замок 4.2)', action: action }, 403);
      }
    }

    switch (action) {
      case 'add_transaction':
        return jsonResponse(Object.assign({ action }, addTransaction(body)));

      case 'add_event':
        return jsonResponse(Object.assign({ action }, addEvent(body)));

      case 'delete_event':
        return jsonResponse(Object.assign({ action }, deleteEvent(body)));

      // правка строки события НА МЕСТЕ: метка времени записи сохраняется, ключ приводится
      // к содержимому (см. editEvent в BotData.js). Замена «удалить + добавить заново».
      case 'edit_event':
        return jsonResponse(Object.assign({ action }, editEvent(body)));

      case 'check_balance':
        return jsonResponse(Object.assign({ action }, checkBalance(body)));

      case 'get_balance':
        return jsonResponse(Object.assign({ action }, getBalance(body)));

      case 'tx_summary':
        return jsonResponse(Object.assign({ action }, getTxSummary(body.period || 'today')));

      case 'void_last':
        return jsonResponse(Object.assign({ action }, voidLastTransaction(body)));

      case 'service_upsert':
        return jsonResponse(Object.assign({ action }, serviceUpsert(body)));

      case 'service_list':
        return jsonResponse(Object.assign({ action }, serviceList(body)));

      case 'service_delete':
        return jsonResponse(Object.assign({ action }, serviceDelete_(body)));
      case 'service_set_pin':
        return jsonResponse(Object.assign({ action }, serviceSetPin(body)));

      case 'important_add':
        return jsonResponse(Object.assign({ action }, importantAdd(body)));

      case 'important_list':
        return jsonResponse(Object.assign({ action }, importantList(body)));

      case 'important_due':
        return jsonResponse(Object.assign({ action }, importantDueReminders(body)));

      case 'important_touch':
        return jsonResponse(Object.assign({ action }, importantTouch(body)));

      case 'important_close':
        return jsonResponse(Object.assign({ action }, importantClose(body)));

      case 'audit_log':
        return jsonResponse(Object.assign({ action }, auditLog(body)));

      case 'audit_list':
        return jsonResponse(Object.assign({ action }, auditList(body)));

      case 'audit_update':
        return jsonResponse(Object.assign({ action }, auditUpdate(body)));

      case 'quote_price':   // read-only расчёт цены (дублирует GET — удобнее ботам, шлющим всё POST'ом)
        return jsonResponse(Object.assign({ action }, quotePrice(body)));

      case 'set_caps':      // блок капов Z3:AB15 «Календаря бронирования» целиком (confirmed-гейт)
        return jsonResponse(Object.assign({ action }, setCaps(body)));

      case 'toggle_cap':    // переключить «Активен» одной модели в блоке капов (confirmed-гейт)
        return jsonResponse(Object.assign({ action }, toggleCap(body)));

      case 'create_booking':
        return jsonResponse(Object.assign({ action }, createBooking(body)));

      case 'activate_booking':
        return jsonResponse(Object.assign({ action }, activateBooking(body)));

      case 'close_booking':
        return jsonResponse(Object.assign({ action }, closeBooking(body)));

      // === B2 паспорт (OCR) ===
      case 'upload_passport_photo':
        return jsonResponse(Object.assign({ action }, uploadPassportPhoto_(body)));

      case 'ocr_passport':
        return jsonResponse(Object.assign({ action }, ocrPassport_(body)));

      case 'save_passport':
        return jsonResponse(Object.assign({ action }, savePassport_(body)));

      // === B3 договор ===
      case 'make_contract':
        return jsonResponse(Object.assign({ action }, makeContract_(body)));

      case 'seed_cost_models':   // одноразовый засев вкладки стоимость_моделей (идемпотентно)
        return jsonResponse(Object.assign({ action }, seedCostModels_()));

      // === Лист закрытия (Bot Data «закрытие», НЕ CRM → НЕ в REDZONE_LOCK; аудит 4.1 client-side) ===
      case 'closing_upsert':
        return jsonResponse(Object.assign({ action }, closingUpsert_(body)));
      case 'closing_get':
        return jsonResponse(Object.assign({ action }, closingGet_(body)));
      case 'closing_list':
        return jsonResponse(Object.assign({ action }, closingList_(body)));

      // === ТО-заявки (двухфазный сервис; Bot Data «то_заявки», НЕ CRM → НЕ в REDZONE_LOCK) ===
      case 'service_pending_upsert':
        return jsonResponse(Object.assign({ action }, servicePendingUpsert_(body)));
      case 'service_pending_get':
        return jsonResponse(Object.assign({ action }, servicePendingGet_(body)));
      case 'service_pending_list':
        return jsonResponse(Object.assign({ action }, servicePendingList_(body)));
      case 'service_pending_close':
        return jsonResponse(Object.assign({ action }, servicePendingClose_(body)));

      // === Состояние байка (Этап 1 трекинга — bot-owned слой, НЕ CRM/Лист1) ===
      case 'state_set':
        return jsonResponse(Object.assign({ action }, stateUpsert_(body)));
      case 'state_get':
        return jsonResponse(Object.assign({ action }, stateGet_(body)));
      case 'state_list':
        return jsonResponse(Object.assign({ action }, stateList_()));

      // === Удаление файла в Brain-папке (housekeeping; защита not_in_brain; аудит 4.1 client-side) ===
      case 'trash_brain_file':
        return jsonResponse(Object.assign({ action }, trashBrainFile_(body)));

      // === Перенос файла Brain → подпапка Brain/_archive (обратимо; защита not_in_brain) ===
      case 'move_brain_file':
        return jsonResponse(Object.assign({ action }, moveBrainFile_(body)));

      // === Перенос KB_*-файла НАРУЖУ→ВНУТРЬ: в КОРЕНЬ папки Brain (защита not_kb_file) ===
      case 'move_into_brain':
        return jsonResponse(Object.assign({ action }, moveIntoBrain_(body)));

      // === Снять ключ из BRAIN_MANIFEST (односторонняя; нужен confirm:true, folder_id защищён) ===
      case 'unregister_brain_doc':
        return jsonResponse(Object.assign({ action }, unregisterBrainDoc_(body)));

        case 'write_doc':
  return jsonResponse(Object.assign({ action }, writeDoc_(body)));

      case 'register_brain_doc':
        return jsonResponse(Object.assign({ action }, registerBrainDoc_(body)));

      case 'migrate_journal':
        return jsonResponse(Object.assign({ action }, migrateJournalToPlain_(body)));

      case 'create_brain_plain':
        return jsonResponse(Object.assign({ action }, createBrainPlain_(body)));

      case 'prune_sessions_log':
        return jsonResponse(Object.assign({ action }, pruneSessionsLog_()));

      case 'setup_sessions_prune_trigger':
        return jsonResponse(Object.assign({ action }, setupSessionsPruneTrigger()));

      case 'list_project_triggers':
        return jsonResponse(Object.assign({ action }, listProjectTriggers_()));

      case 'log_write':
        return jsonResponse(Object.assign({ action }, logWrite_(body)));

      case 'read_write_log':
        return jsonResponse(Object.assign({ action }, readWriteLog_(body)));

      // === Очередь оркестратора (ступень 1, заход 1 — служебный лист, НЕ боевые данные) ===
      case 'enqueue_task':
        return jsonResponse(Object.assign({ action }, enqueueTask_(body)));

      case 'claim_task':
        return jsonResponse(Object.assign({ action }, claimTask_(body)));

      case 'complete_task':
        return jsonResponse(Object.assign({ action }, completeTask_(body)));

      case 'set_needs_approval':
        return jsonResponse(Object.assign({ action }, setNeedsApproval_(body)));

      case 'approve_task':
        return jsonResponse(Object.assign({ action }, approveTask_(body)));

      case 'task_heartbeat':
        return jsonResponse(Object.assign({ action }, queueHeartbeat_(body)));

      case 'issue_write_ticket':
        return jsonResponse(Object.assign({ action }, issueWriteTicket_(body)));

      case 'consume_write_ticket':
        return jsonResponse(Object.assign({ action }, { ok: consumeWriteTicket_(body.ticket || '') }));

      case 'set_fleet_oil':
        return jsonResponse(Object.assign({ action }, setFleetOil_(body)));

      case 'set_fleet_service':
        return jsonResponse(Object.assign({ action }, setFleetService_(body)));

      case 'prune_cc_log':
        return jsonResponse(Object.assign({ action }, pruneCcLog_()));

      case 'setup_prune_trigger':
        return jsonResponse(Object.assign({ action }, setupPruneTrigger()));

      case 'prune_review':
        return jsonResponse(Object.assign({ action }, pruneReview_(body)));

      case 'prune_review_size':
        return jsonResponse(Object.assign({ action }, pruneReviewBySize_()));

      case 'setup_review_prune_trigger':
        return jsonResponse(Object.assign({ action }, setupReviewPruneTrigger()));

      // --- Ротация cowork_log: ручной прогон. Триггер ставится ОТДЕЛЬНЫМ экшеном ниже,
      //     сам по себе этот вызов расписание не включает. ---
      case 'prune_cowork_log':
        return jsonResponse(Object.assign({ action }, pruneCoworkLog_()));

      case 'setup_cowork_prune_trigger':
        return jsonResponse(Object.assign({ action }, setupCoworkPruneTrigger()));

      // Самопроверка ротации на ТЕСТОВЫХ доках (живой cowork_log только читается).
      case 'prune_cowork_selftest':
        return jsonResponse(Object.assign({ action }, coworkPruneSelfTest_(body)));

      // === Зоны доставки (одноразовый init — POST) ===
      case 'delivery_zones_init':
        return jsonResponse(Object.assign({ action }, deliveryZonesInit_()));

      // Запись зон (upsert/delete по name; #CONFIG не трогает) — конверт владельца
      case 'delivery_zones_set':
        return jsonResponse(Object.assign({ action }, deliveryZonesSet_(body)));

      default:
        return jsonResponse({
          ok: false,
          error: 'unknown_action',
          message: `Unknown POST action: ${action}`,
          actions: ['add_transaction', 'add_event', 'delete_event', 'read_events', 'check_balance', 'get_balance', 'tx_summary', 'void_last', 'service_upsert', 'service_list', 'service_set_pin', 'important_add', 'important_list', 'important_due', 'important_touch', 'important_close', 'audit_log', 'audit_list', 'audit_update', 'create_booking', 'activate_booking', 'close_booking', 'write_doc', 'migrate_journal', 'create_brain_plain', 'log_write', 'read_write_log', 'issue_write_ticket', 'consume_write_ticket', 'set_fleet_oil', 'set_fleet_service', 'prune_cc_log', 'setup_prune_trigger', 'prune_review', 'prune_review_size', 'setup_review_prune_trigger', 'prune_sessions_log', 'setup_sessions_prune_trigger', 'prune_cowork_log', 'setup_cowork_prune_trigger', 'prune_cowork_selftest', 'list_project_triggers', 'enqueue_task', 'claim_task', 'complete_task', 'set_needs_approval', 'approve_task', 'task_heartbeat', 'get_pending', 'upload_passport_photo', 'ocr_passport', 'save_passport', 'make_contract', 'seed_cost_models', 'closing_upsert', 'closing_get', 'closing_list', 'state_set', 'state_get', 'state_list', 'trash_brain_file', 'move_brain_file', 'register_brain_doc', 'move_into_brain', 'unregister_brain_doc', 'edit_event']
        }, 400);
    }

  } catch (err) {
    console.error('Bridge POST error:', err.message, err.stack);
    return jsonResponse({ ok: false, error: 'internal_error', message: err.message }, 500);
  }
}


/**
 * Утилита: формирует JSON-ответ.
 * Google Apps Script не позволяет менять HTTP status code в doGet,
 * поэтому "статус" возвращаем в теле ответа.
 */
function jsonResponse(obj, httpStatus) {
  // httpStatus идёт в тело — Python будет на это смотреть
  obj._status = httpStatus || 200;
  
  return ContentService
    .createTextOutput(JSON.stringify(obj, null, 2))
    .setMimeType(ContentService.MimeType.JSON);
}


/**
 * РУЧНОЙ ТЕСТ — запусти из редактора чтобы проверить что Bridge работает.
 * Run → testBridge.
 * Логи в "Executions".
 */
function testBridge() {
  const tests = ['ping', 'fleet', 'clients', 'anomalies', 'daily_pulse'];
  
  for (const action of tests) {
    console.log(`\n=== TEST: ${action} ===`);
    const e = { parameter: { token: CONFIG.TOKEN, action: action } };
    const response = doGet(e);
    const text = response.getContent();
    console.log(text.substring(0, 500) + (text.length > 500 ? '...' : ''));
  }
}