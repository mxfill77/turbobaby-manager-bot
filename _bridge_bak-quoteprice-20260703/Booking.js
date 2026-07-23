/**
 * Booking.gs — постановка ПРЕДВАРИТЕЛЬНОЙ брони ботом.
 *
 * Пишет новую строку в "менеджеру Байки" → лист "клиенты" со статусом "Бронь".
 * Поведение совпадает с формой Rental Agreement, НО:
 *   - статус A = "Бронь" (НЕ "В аренде") → формулы I/J (долг) НЕ начисляют ничего,
 *     пока бронь не активирована. Долг стартует только когда A станет "В аренде".
 *   - активация (Бронь → В аренде) делается отдельно, после фото выдачи тайцем (этап 6),
 *     функцией activateBooking().
 *
 * Карта колонок взята 1-в-1 из formToSheetColumns скрипта формы.
 */

// Лист и колонки (1-indexed) листа "клиенты" таблицы MANAGER
var BOOKING = {
  MANAGER_ID: '1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0',
  SHEET: 'клиенты',
  BIKES_TAB: 'список мото',  // источник точных названий (для проверки данных колонки C)
  COL: {
    STATUS: 1,    // A — "Бронь" / "В аренде" / "Завершена"
    AUTO_CNCL: 2, // B — OFF
    BIKE: 3,      // C — Название мото
    NAME: 4,      // D — Имя
    DATE_START: 5,// E — Дата начала (pick up)
    DATE_END: 6,  // F — Дата завершения (return + time)
    PAY_MONTH: 12,// L — платёж в месяц
    PAY_DAY: 13,  // M — платёж в день
    KM: 14,       // N — пробег на момент сдачи
    DEPOSIT: 19,  // S — залог (число ИЛИ "passport")
    HELMETS: 20,  // T — шлемы
    CONTACTS: 21, // U — контакты
    NOTE: 22,     // V — примечание
    INITIAL_PAY: 11, // K — оплачено (initial payment)
    BOOKING_ID: 25,  // Y — стабильный uuid брони (Галка v1; вне формы A..X и FORMULA_COLS)
  }
};

// Кубатуры (НЕ номера) — чтобы вытащить именно номерной знак байка
var BOOKING_CC = {'125':1,'150':1,'155':1,'160':1,'300':1,'350':1,'400':1,
                  '500':1,'650':1,'700':1,'750':1,'900':1};

function bookingPlate_(text) {
  var nums = String(text).toLowerCase().match(/\d{3,}/g) || [];
  nums = nums.filter(function(n){ return !BOOKING_CC[n]; });
  return nums.length ? nums[nums.length - 1] : null;
}

/**
 * Резолвит вход (номер "4957" или часть названия) в ТОЧНОЕ полное название байка
 * из листа "список мото" — то, что принимает проверка данных колонки C.
 * Возвращает строку (точное имя) или null, если не нашли однозначно.
 */
function resolveBikeName_(input) {
  if (!input) return null;
  var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
  var tab = ss.getSheetByName(BOOKING.BIKES_TAB);
  if (!tab) return null;
  var last = tab.getLastRow();
  if (last < 1) return null;
  var names = tab.getRange(1, 1, last, 1).getValues().map(function(r){ return String(r[0] || '').trim(); })
                 .filter(function(s){ return s; });

  var inExact = String(input).trim();
  // 1) точное совпадение
  for (var i = 0; i < names.length; i++) if (names[i].toLowerCase() === inExact.toLowerCase()) return names[i];
  // 2) по номерному знаку
  var qp = bookingPlate_(inExact);
  if (qp) {
    var hit = names.filter(function(n){ return bookingPlate_(n) === qp; });
    if (hit.length === 1) return hit[0];
  }
  // 3) вхождение (если ровно одно)
  var sub = names.filter(function(n){ return n.toLowerCase().indexOf(inExact.toLowerCase()) >= 0; });
  if (sub.length === 1) return sub[0];
  return null; // неоднозначно или не найдено
}


/**
 * Создать предварительную бронь.
 * Ожидаемые поля body:
 *   bike (обяз.), name (обяз.), date_start, date_end,
 *   pay_day, pay_month, deposit (число или "passport"), helmets,
 *   contacts, note, initial_pay, km
 */
function createBooking(body) {
  var p = body || {};

  // --- валидация минимума ---
  if (!p.bike)  return { ok: false, error: 'missing_bike',  message: 'bike обязателен' };
  if (!p.name)  return { ok: false, error: 'missing_name',  message: 'name обязателен' };

  try {
  // --- резолв байка в ТОЧНОЕ полное название (иначе проверка данных в C отклонит) ---
  var bikeFull = resolveBikeName_(p.bike);
  if (!bikeFull) {
    return { ok: false, error: 'bike_not_resolved',
             message: 'Байк "' + p.bike + '" не найден однозначно в "список мото". ' +
                      'Передай номер (напр. 4957) или точное название.' };
  }

  var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
  var sheet = ss.getSheetByName(BOOKING.SHEET);
  if (!sheet) return { ok: false, error: 'sheet_not_found', message: BOOKING.SHEET };

  // --- защита от дубля: тот же байк (C) + имя (D) + дата начала (E) уже в статусе
  //     "Бронь" ИЛИ "В аренде" → не пишем второй раз ---
  var lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    var scan = sheet.getRange(2, 1, lastRow - 1, BOOKING.COL.DATE_START).getValues(); // A..E
    var wantBike = bikeFull.trim().toLowerCase();
    var wantName = String(p.name).trim().toLowerCase();
    var wantStart = String(p.date_start || '').trim().toLowerCase();
    for (var i = 0; i < scan.length; i++) {
      var st = String(scan[i][BOOKING.COL.STATUS - 1]     || '').trim().toLowerCase();
      var bk = String(scan[i][BOOKING.COL.BIKE - 1]       || '').trim().toLowerCase();
      var nm = String(scan[i][BOOKING.COL.NAME - 1]       || '').trim().toLowerCase();
      var ds = String(scan[i][BOOKING.COL.DATE_START - 1] || '').trim().toLowerCase();
      if ((st === 'бронь' || st === 'в аренде') &&
          bk === wantBike && nm === wantName && ds === wantStart) {
        return { ok: false, error: 'duplicate', row: i + 2, status: st,
                 message: 'Такая бронь (байк+клиент+дата) уже есть в статусе "' + scan[i][BOOKING.COL.STATUS - 1] + '"' };
      }
    }
  }

  // --- первая пустая строка в колонке A (как делает форма) ---
  var colA = sheet.getRange('A:A').getValues();
  var nextRow = 0;
  for (var r = 0; r < colA.length; r++) {
    if (!colA[r][0]) { nextRow = r + 1; break; }
  }
  if (nextRow === 0) nextRow = sheet.getLastRow() + 1;

  // --- запись полей (пустые не трогаем, чтобы не затирать формулы) ---
  function put(col, val) {
    if (val !== undefined && val !== null && val !== '') {
      sheet.getRange(nextRow, col).setValue(val);
    }
  }
  // фиксированные
  sheet.getRange(nextRow, BOOKING.COL.STATUS).setValue('Бронь'); // ← ключевое: НЕ "В аренде"
  sheet.getRange(nextRow, BOOKING.COL.AUTO_CNCL).setValue('OFF');
  sheet.getRange(nextRow, BOOKING.COL.NAME).setValue(p.name);
  // данные брони
  put(BOOKING.COL.BIKE,        bikeFull);    // ← точное название из списка мото
  put(BOOKING.COL.DATE_START,  p.date_start);
  put(BOOKING.COL.DATE_END,    p.date_end);
  put(BOOKING.COL.PAY_DAY,     p.pay_day);
  put(BOOKING.COL.PAY_MONTH,   p.pay_month);
  put(BOOKING.COL.KM,          p.km);
  put(BOOKING.COL.DEPOSIT,     p.deposit);   // число или "passport"
  put(BOOKING.COL.HELMETS,     p.helmets);
  put(BOOKING.COL.CONTACTS,    p.contacts);
  put(BOOKING.COL.NOTE,        p.note);
  put(BOOKING.COL.INITIAL_PAY, p.initial_pay);

  // --- booking_id (Галка v1): стабильный uuid в кол. Y — чтобы договор находить по неизменному id ---
  var bookingId = Utilities.getUuid();
  sheet.getRange(nextRow, BOOKING.COL.BOOKING_ID).setValue(bookingId);

  // --- copyFormulas: протянуть формульные колонки G/H/I/J/O/P/Q/W/X из строки ВЫШЕ ---
  // (техника формы Rental Agreement: fill-down, относительные ссылки сдвигаются на новую строку).
  // КРИТИЧНО: без этого долг (I/J) и расчёты (G/H/O/P/Q/W/X) в новой строке будут пустыми.
  // contentsOnly:false → копируем формулу+формат. Источник = строка выше (лист заполняется подряд).
  var FORMULA_COLS = [7, 8, 9, 10, 15, 16, 17, 23, 24]; // G H I J O P Q W X
  var copied = [];
  if (nextRow > 2) {
    var srcRow = nextRow - 1;
    for (var fc = 0; fc < FORMULA_COLS.length; fc++) {
      var c = FORMULA_COLS[fc];
      sheet.getRange(srcRow, c).copyTo(sheet.getRange(nextRow, c), { contentsOnly: false });
      copied.push(c);
    }
  }

  return { ok: true, saved: true, row: nextRow, status: 'Бронь', bike: bikeFull, name: p.name,
           booking_id: bookingId,
           formulas_copied: copied.length, formula_src_row: nextRow > 2 ? nextRow - 1 : null };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
}

/**
 * Активировать бронь: "Бронь" → "В аренде". Вызывается после фото выдачи (этап 6).
 * С этого момента формулы I/J начинают считать долг.
 */
function activateBooking(body) {
  var p = body || {};
  if (!p.bike || !p.name)
    return { ok: false, error: 'missing_args', message: 'нужны bike и name' };

  var bikeFull = resolveBikeName_(p.bike);
  if (!bikeFull) return { ok: false, error: 'bike_not_resolved', message: 'Байк не найден: ' + p.bike };

  var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
  var sheet = ss.getSheetByName(BOOKING.SHEET);
  if (!sheet) return { ok: false, error: 'sheet_not_found' };

  var lastRow = sheet.getLastRow();
  var data = sheet.getRange(2, 1, lastRow - 1, BOOKING.COL.NAME).getValues();
  for (var i = 0; i < data.length; i++) {
    var st = String(data[i][0] || '').trim().toLowerCase();
    var bk = String(data[i][BOOKING.COL.BIKE - 1] || '').trim().toLowerCase();
    var nm = String(data[i][BOOKING.COL.NAME - 1] || '').trim().toLowerCase();
    if (st === 'бронь' &&
        bk === bikeFull.trim().toLowerCase() &&
        nm === String(p.name).trim().toLowerCase()) {
      sheet.getRange(i + 2, BOOKING.COL.STATUS).setValue('В аренде');
      return { ok: true, activated: true, row: i + 2, bike: bikeFull, name: p.name };
    }
  }
  return { ok: false, error: 'booking_not_found',
           message: 'Активная бронь по этому байку и клиенту не найдена' };
}

/**
 * ТЕСТ — запусти эту функцию кнопкой ▶ Run прямо в редакторе Apps Script.
 * Создаст тестовую бронь. Потом проверь лист "клиенты": должна появиться строка
 * со статусом "Бронь", долг (I) пустой. Тестовую строку после проверки удали руками.
 */
function testBooking() {
  var res = createBooking({
    bike: '4957',
    name: 'ТЕСТ Бронь',
    deposit: 7000,
    pay_day: 500,
    contacts: '@test_client',
    note: 'тестовая бронь — удалить',
    date_start: '02-06-2026',
    date_end: '09-06-2026, 13:00',
  });
  Logger.log('=== РЕЗУЛЬТАТ createBooking ===');
  Logger.log(JSON.stringify(res, null, 2));
  // ожидаем: bike = "NMAX 155CC GREEN-B PHUKET 4957", status "Бронь"
  return res;
}

/**
 * ТЕСТ активации — запусти ПОСЛЕ testBooking, чтобы проверить переход Бронь→В аренде.
 * (Только если хочешь проверить этап 6. Для проверки самой брони не нужен.)
 */
function testActivate() {
  var res = activateBooking({ bike: 'NMAX 4957', name: 'ТЕСТ Бронь' });
  Logger.log('=== РЕЗУЛЬТАТ activateBooking ===');
  Logger.log(JSON.stringify(res, null, 2));
  return res;
}