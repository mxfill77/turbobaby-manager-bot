/**
 * ReadFinance.gs — финансовая аналитика
 * 
 * Считаем доход из таблицы "клиенты" (колонка K = "Оплачено")
 * и сравниваем с историческими данными из дашборда "Байки".
 */


/**
 * Финансы за период.
 * period: 'today' | 'week' | 'month' | 'year' | 'all'
 */
function getFinance(period) {
  period = period || 'month';
  
  const now = new Date();
  let cutoff;
  
  switch (period) {
    case 'today':
      cutoff = new Date(now);
      cutoff.setHours(0, 0, 0, 0);
      break;
    case 'week':
      cutoff = new Date(now);
      cutoff.setDate(cutoff.getDate() - 7);
      break;
    case 'month':
      cutoff = new Date(now);
      cutoff.setMonth(cutoff.getMonth() - 1);
      break;
    case 'year':
      cutoff = new Date(now);
      cutoff.setFullYear(cutoff.getFullYear() - 1);
      break;
    case 'all':
      cutoff = new Date(2022, 0, 1);
      break;
    default:
      cutoff = new Date(now);
      cutoff.setMonth(cutoff.getMonth() - 1);
  }
  
  const sheet = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return { revenue: 0, count: 0 };
  
  // Читаем нужные колонки: C (bike), D (name), E (start), F (end), K (paid), X (type)
  const data = sheet.getRange(2, 1, lastRow - 1, 24).getValues();
  
  let totalRevenue = 0;
  let rentalsCount = 0;
  const byBike = {};
  const byType = { 'мото': 0, 'скутер': 0, 'unknown': 0 };
  
  for (const row of data) {
    const bike = String(row[2] || '').trim();        // C
    const dateStart = row[4];                         // E
    const paid = parseNumber(row[10]);                // K
    const type = String(row[23] || '').trim().toLowerCase();  // X
    
    if (!bike || paid <= 0) continue;
    if (!(dateStart instanceof Date)) continue;
    if (dateStart < cutoff) continue;
    
    totalRevenue += paid;
    rentalsCount++;
    
    byBike[bike] = (byBike[bike] || 0) + paid;
    
    if (type === 'мото') byType['мото'] += paid;
    else if (type === 'скутер') byType['скутер'] += paid;
    else byType['unknown'] += paid;
  }
  
  // Топ-10 байков по доходу
  const topBikes = Object.entries(byBike)
    .map(([name, revenue]) => ({ bike: name, revenue }))
    .sort((a, b) => b.revenue - a.revenue)
    .slice(0, 10);
  
  // Средний чек
  const avgRental = rentalsCount > 0 ? Math.round(totalRevenue / rentalsCount) : 0;
  
  // Дни в периоде
  const days = Math.max(1, Math.floor((now - cutoff) / (1000 * 60 * 60 * 24)));
  const avgPerDay = Math.round(totalRevenue / days);
  
  return {
    period: period,
    from: formatDate(cutoff),
    to: formatDate(now),
    days_in_period: days,
    total_revenue: totalRevenue,
    rentals_count: rentalsCount,
    avg_rental: avgRental,
    avg_per_day: avgPerDay,
    by_type: byType,
    top_bikes: topBikes,
  };
}


/**
 * Зарплаты — выплаты за период.
 * Читает из таблицы "Зарплаты" → лист "Выплаты (Рус)" (Даня/Даша)
 * и "Выплаты" (тайцы).
 */
function getSalaries(period) {
  period = period || 'month';
  
  const now = new Date();
  let cutoff;
  
  if (period === 'month') {
    cutoff = new Date(now);
    cutoff.setMonth(cutoff.getMonth() - 1);
  } else if (period === 'year') {
    cutoff = new Date(now);
    cutoff.setFullYear(cutoff.getFullYear() - 1);
  } else {
    cutoff = new Date(2025, 0, 1);
  }
  
  const totals = {};  // { 'Даня': 50000, 'Даша': 30000, ... }
  let totalAmount = 0;
  
  // Лист тайцев
  try {
    const sheetTH = SpreadsheetApp.openById(CONFIG.SHEETS.SALARY).getSheetByName('Выплаты');
    if (sheetTH) {
      const lastRow = sheetTH.getLastRow();
      if (lastRow > 1) {
        const data = sheetTH.getRange(2, 1, lastRow - 1, 4).getValues();
        for (const row of data) {
          const date = row[0];
          const name = String(row[1] || '').trim();
          const amount = parseNumber(row[2]);
          if (!name || amount === 0) continue;
          if (!(date instanceof Date) || date < cutoff) continue;
          totals[name] = (totals[name] || 0) + amount;
          totalAmount += amount;
        }
      }
    }
  } catch(e) {
    console.error('Salaries TH error:', e.message);
  }
  
  // Лист менеджеров (Даня/Даша)
  try {
    const sheetRU = SpreadsheetApp.openById(CONFIG.SHEETS.SALARY).getSheetByName('Выплаты (Рус)');
    if (sheetRU) {
      const lastRow = sheetRU.getLastRow();
      if (lastRow > 1) {
        const data = sheetRU.getRange(2, 1, lastRow - 1, 4).getValues();
        for (const row of data) {
          const date = row[0];
          const name = String(row[1] || '').trim();
          const amount = parseNumber(row[2]);
          if (!name || amount === 0) continue;
          if (!(date instanceof Date) || date < cutoff) continue;
          totals[name] = (totals[name] || 0) + amount;
          totalAmount += amount;
        }
      }
    }
  } catch(e) {
    console.error('Salaries RU error:', e.message);
  }
  
  return {
    period: period,
    from: formatDate(cutoff),
    to: formatDate(now),
    total: totalAmount,
    by_person: totals,
  };
}