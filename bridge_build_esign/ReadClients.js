/**
 * ReadClients.gs — чтение данных из листа "клиенты"
 * 
 * ВАЖНО: 
 *   - Аренды старше 12 месяцев игнорируем (KB: "долги старше года списаны")
 *   - Скрытые строки (фильтр "Завершена") учитываем как закрытые
 *   - Активная аренда = A="В аренде" И B="OFF" (как в формуле F5 Календаря)
 */


// Лимит "свежих" записей в месяцах — после этого считаем устаревшим
const FRESH_MONTHS = 12;


/**
 * Главная функция чтения клиентов.
 * filter: 'active' | 'overdue' | 'recent' | 'all'
 */
function getClients(filter) {
  filter = filter || 'active';
  
  const sheet = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { clients: [], summary: emptySummary() };
  
  // Читаем колонки A-Y (1-25): X=тип, Y=booking_id (Галка/Лист закрытия)
  const data = sheet.getRange(2, 1, lastRow - 1, 25).getValues();
  
  const now = new Date();
  const freshCutoff = new Date(now);
  freshCutoff.setMonth(freshCutoff.getMonth() - FRESH_MONTHS);
  
  const clients = [];
  
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const rowNum = i + 2;  // реальный номер строки
    
    const status = String(row[0] || '').trim();        // A
    const autoCncl = String(row[1] || '').trim();      // B
    const bike = String(row[2] || '').trim();          // C
    const name = String(row[3] || '').trim();          // D
    const dateStart = row[4];                          // E
    const dateEnd = row[5];                            // F
    const duration = String(row[6] || '').trim();      // G
    const payPerDay = parseNumber(row[7]);             // H
    const debt = parseNumber(row[8]);                  // I
    const toPay = parseNumber(row[9]);                 // J
    const paid = parseNumber(row[10]);                 // K
    const deposit = parseNumber(row[18]);              // S
    const depositRaw = String(row[18] == null ? '' : row[18]).trim();  // S сырьём: число | 'passport' | '' (O3-3c — parseNumber ест 'passport' в 0)
    const helmets = String(row[19] || '').trim();      // T
    const contacts = String(row[20] || '').trim();     // U
    const note = String(row[21] || '').trim();         // V
    const type = String(row[23] || '').trim();         // X — мото/скутер
    const bookingId = String(row[24] || '').trim();    // Y — booking_id (uuid, Галка v1)

    // Пропускаем пустые строки
    if (!name && !bike) continue;
    
    // Парсим даты
    const dateStartObj = dateStart instanceof Date ? dateStart : null;
    const dateEndObj = parseEndDate(dateEnd);  // F может быть "01.06.2026 , 14:00"
    
    // Свежесть записи
    const isFresh = dateStartObj && dateStartObj >= freshCutoff;
    
    // Реальный статус (учитывая что W-формула делает автостатус по NOW())
    // Активная = "В аренде" И B != "ON" (по логике твоей F5 Календаря)
    const isActive = status === 'В аренде' && autoCncl !== 'ON';
    
    // Просрочка — активная и dateEnd в прошлом
    const isOverdue = isActive && dateEndObj && dateEndObj < now;
    const daysOverdue = isOverdue ? Math.floor((now - dateEndObj) / (1000 * 60 * 60 * 24)) : 0;
    
    // === Фильтрация ===
    let include = false;
    
    if (filter === 'all') {
      include = true;
    } else if (filter === 'active') {
      // Активные — только свежие, чтобы не показывать "висяки" 2022-2024
      include = isActive && isFresh;
    } else if (filter === 'overdue') {
      include = isOverdue && isFresh;
    } else if (filter === 'recent') {
      include = isFresh;
    } else if (filter === 'all_active') {
      // Включая старые — для аналитики
      include = isActive;
    }
    
    if (!include) continue;
    
    clients.push({
      row: rowNum,
      status: status,
      auto_cancel: autoCncl,
      bike: bike,
      name: name,
      date_start: formatDate(dateStartObj),
      date_end: formatDate(dateEndObj),
      duration: duration,
      pay_per_day: payPerDay,
      debt: debt,
      to_pay: toPay,
      paid: paid,
      deposit: deposit,
      deposit_raw: depositRaw,
      helmets: helmets,
      contacts: contacts,
      note: note,
      type: type,
      booking_id: bookingId,

      // Расчётные флаги
      is_active: isActive,
      is_overdue: isOverdue,
      days_overdue: daysOverdue,
      is_fresh: isFresh,
    });
  }
  
  // === Сводка ===
  const summary = {
    count: clients.length,
    active: clients.filter(c => c.is_active).length,
    overdue: clients.filter(c => c.is_overdue).length,
    total_debt: clients.filter(c => c.is_active).reduce((s, c) => s + c.debt, 0),
    total_paid: clients.reduce((s, c) => s + c.paid, 0),
    total_deposits: clients.filter(c => c.is_active).reduce((s, c) => s + c.deposit, 0),
  };
  
  return { clients, summary };
}


/**
 * Аномалии — то что бот должен предложить починить/спросить у менеджера.
 */
function getAnomalies() {
  const sheet = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { anomalies: [] };
  
  const data = sheet.getRange(2, 1, lastRow - 1, 24).getValues();
  
  const now = new Date();
  const freshCutoff = new Date(now);
  freshCutoff.setMonth(freshCutoff.getMonth() - FRESH_MONTHS);
  
  const anomalies = [];
  
  // Счётчики
  let oldActiveCount = 0;
  
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    const rowNum = i + 2;
    
    const status = String(row[0] || '').trim();
    const autoCncl = String(row[1] || '').trim();
    const bike = String(row[2] || '').trim();
    const name = String(row[3] || '').trim();
    const dateStart = row[4];
    const dateEnd = row[5];
    const debt = parseNumber(row[8]);
    const paid = parseNumber(row[10]);
    
    if (!name && !bike) continue;
    
    const dateStartObj = dateStart instanceof Date ? dateStart : null;
    const dateEndObj = parseEndDate(dateEnd);
    const isActive = status === 'В аренде' && autoCncl !== 'ON';
    const isFresh = dateStartObj && dateStartObj >= freshCutoff;
    
    // === Тип 1: Старая "В аренде" (висяк >12 мес) ===
    if (isActive && dateStartObj && !isFresh) {
      oldActiveCount++;
      // Не добавляем в anomalies массово — только счётчик
      // Бот спросит "у тебя N старых аренд, разобраться?"
    }
    
    // === Тип 2: Просрочка возврата >1 день (свежие!) ===
    if (isActive && isFresh && dateEndObj && dateEndObj < now) {
      const daysOverdue = Math.floor((now - dateEndObj) / (1000 * 60 * 60 * 24));
      if (daysOverdue >= 1) {
        anomalies.push({
          type: 'overdue_return',
          severity: daysOverdue >= 3 ? 'high' : 'medium',
          row: rowNum,
          bike: bike,
          client: name,
          days_overdue: daysOverdue,
          end_date: formatDate(dateEndObj),
          debt: debt,
          message: `${name} (${bike}) — просрочил возврат на ${daysOverdue} ${dayWord(daysOverdue)}, долг ${formatMoney(debt)}`
        });
      }
    }
    
    // === Тип 3: Большой долг у активной свежей аренды ===
    if (isActive && isFresh && debt > 5000) {
      anomalies.push({
        type: 'large_debt',
        severity: debt > 20000 ? 'high' : 'medium',
        row: rowNum,
        bike: bike,
        client: name,
        debt: debt,
        paid: paid,
        message: `${name} (${bike}) — долг ${formatMoney(debt)}, оплачено ${formatMoney(paid)}`
      });
    }
    
    // === Тип 4: Возврат завтра — напомнить (свежие активные) ===
    if (isActive && isFresh && dateEndObj) {
      const hoursUntilEnd = (dateEndObj - now) / (1000 * 60 * 60);
      if (hoursUntilEnd > 0 && hoursUntilEnd <= 36) {
        anomalies.push({
          type: 'return_soon',
          severity: 'info',
          row: rowNum,
          bike: bike,
          client: name,
          end_date: formatDate(dateEndObj),
          hours_left: Math.round(hoursUntilEnd),
          message: `${name} (${bike}) возвращает через ${Math.round(hoursUntilEnd)} часов — напомнить?`
        });
      }
    }
  }
  
  // Добавляем сводку о старых записях
  if (oldActiveCount > 0) {
    anomalies.push({
      type: 'old_active_records',
      severity: 'info',
      count: oldActiveCount,
      message: `${oldActiveCount} ${rentalWord(oldActiveCount)} в статусе "В аренде" старше 12 месяцев. Скорее всего уже закрыты — пересмотреть?`
    });
  }
  
  // Сортируем по severity (high → medium → info)
  const severityOrder = { high: 0, medium: 1, info: 2 };
  anomalies.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
  
  return { anomalies, count: anomalies.length };
}


/**
 * История клиента по телефону или имени.
 * Ищет во всех записях (включая старые).
 */
function getClientHistory(search) {
  const sheet = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { history: [] };
  
  const data = sheet.getRange(2, 1, lastRow - 1, 24).getValues();
  
  const searchLower = String(search).toLowerCase().trim();
  // Чистим телефон от пробелов и плюса для нечёткого поиска
  const phoneClean = searchLower.replace(/[\s+\-()]/g, '');
  
  const history = [];
  
  for (let i = 0; i < data.length; i++) {
    const row = data[i];
    
    const name = String(row[3] || '').trim();        // D
    const contacts = String(row[20] || '').trim();   // U
    
    if (!name && !contacts) continue;
    
    // Поиск по имени или телефону
    const nameLower = name.toLowerCase();
    const contactsLower = contacts.toLowerCase();
    const contactsClean = contactsLower.replace(/[\s+\-()]/g, '');
    
    const matches = 
      (searchLower.length >= 3 && nameLower.includes(searchLower)) ||
      contactsLower.includes(searchLower) ||
      (phoneClean.length >= 5 && contactsClean.includes(phoneClean));
    
    if (!matches) continue;
    
    history.push({
      row: i + 2,
      status: String(row[0] || '').trim(),
      bike: String(row[2] || '').trim(),
      name: name,
      date_start: formatDate(row[4] instanceof Date ? row[4] : null),
      date_end: formatDate(parseEndDate(row[5])),
      duration: String(row[6] || '').trim(),
      pay_per_day: parseNumber(row[7]),
      paid: parseNumber(row[10]),
      deposit: parseNumber(row[18]),
      contacts: contacts,
      note: String(row[21] || '').trim(),
    });
  }
  
  // Сортируем по дате (новые сверху)
  history.sort((a, b) => {
    const da = a.date_start || '';
    const db = b.date_start || '';
    return db.localeCompare(da);
  });
  
  return {
    query: search,
    total_rentals: history.length,
    total_paid: history.reduce((s, h) => s + h.paid, 0),
    history: history,
  };
}


/**
 * Возвраты в ближайшие N дней.
 */
function getReturnsSoon(days) {
  days = days || 3;
  
  const { clients } = getClients('active');
  const now = new Date();
  const limit = new Date(now);
  limit.setDate(limit.getDate() + days);
  
  const returns = clients
    .filter(c => {
      if (!c.date_end) return false;
      const endDate = new Date(c.date_end);
      return endDate >= now && endDate <= limit;
    })
    .map(c => ({
      bike: c.bike,
      client: c.name,
      end_date: c.date_end,
      contacts: c.contacts,
      debt: c.debt,
      duration: c.duration,
    }));
  
  // Также добавим уже просроченные
  const overdue = clients
    .filter(c => c.is_overdue)
    .map(c => ({
      bike: c.bike,
      client: c.name,
      end_date: c.date_end,
      contacts: c.contacts,
      debt: c.debt,
      days_overdue: c.days_overdue,
      overdue: true,
    }));
  
  return {
    days_ahead: days,
    overdue_count: overdue.length,
    overdue: overdue,
    upcoming_count: returns.length,
    upcoming: returns,
  };
}


/**
 * Daily Pulse — всё что нужно для утренней сводки.
 */
function getDailyPulse() {
  const clientsResult = getClients('active');
  const anomalies = getAnomalies();
  const returns = getReturnsSoon(2);
  const fleet = getFleetStatus();
  
  return {
    summary: {
      active_rentals: clientsResult.summary.active,
      overdue_returns: clientsResult.summary.overdue,
      total_debt: clientsResult.summary.total_debt,
      bikes_home: fleet.summary.home,
      bikes_rented: fleet.summary.rented,
      income_today: fleet.dashboard.income_per_day,
    },
    fleet_dashboard: fleet.dashboard,
    anomalies_count: anomalies.count,
    anomalies_top: anomalies.anomalies.slice(0, 5),
    returns_soon: returns,
    active_clients: clientsResult.clients,
  };
}


// === Утилиты ===

/**
 * Парсит дату завершения. В таблице она может быть:
 *   - Date объектом (если ячейка отформатирована как дата)
 *   - Строкой типа "01.06.2026 , 14:00"
 *   - Просто датой "01.06.2026"
 */
function parseEndDate(val) {
  if (!val) return null;
  if (val instanceof Date) return val;
  
  const str = String(val).trim();
  if (!str) return null;
  
  // Формат "DD.MM.YYYY , HH:MM" или "DD.MM.YYYY"
  const m = str.match(/(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:,\s*(\d{1,2}):(\d{2}))?/);
  if (m) {
    const day = parseInt(m[1]);
    const month = parseInt(m[2]) - 1;
    const year = parseInt(m[3]);
    const hour = m[4] ? parseInt(m[4]) : 17;  // дефолт 17:00
    const minute = m[5] ? parseInt(m[5]) : 30;  // дефолт 17:30
    return new Date(year, month, day, hour, minute);
  }
  
  // Попробуем как обычную дату
  const parsed = new Date(str);
  return isNaN(parsed.getTime()) ? null : parsed;
}


function emptySummary() {
  return {
    count: 0, active: 0, overdue: 0,
    total_debt: 0, total_paid: 0, total_deposits: 0
  };
}


function formatMoney(n) {
  if (!n || isNaN(n)) return '0 ฿';
  return `${Math.round(n).toLocaleString('ru-RU')} ฿`;
}


function dayWord(n) {
  const last = n % 10;
  const last2 = n % 100;
  if (last2 >= 11 && last2 <= 14) return 'дней';
  if (last === 1) return 'день';
  if (last >= 2 && last <= 4) return 'дня';
  return 'дней';
}


function rentalWord(n) {
  const last = n % 10;
  const last2 = n % 100;
  if (last2 >= 11 && last2 <= 14) return 'аренд';
  if (last === 1) return 'аренда';
  if (last >= 2 && last <= 4) return 'аренды';
  return 'аренд';
}
