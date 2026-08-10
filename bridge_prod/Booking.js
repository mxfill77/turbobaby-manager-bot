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
    ODO: 17,      // Q — текущий пробег (формула; для чека «одометр не уменьшается»)
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


// ═══ Даты брони (O3-2a, 08.07.2026): парс/формат/пересечение ═══

/**
 * Парс даты брони: ячейка листа (Date) или строка.
 * Строки: 'дд.мм.гггг' (также дд-мм-гггг / дд/мм/гггг), ISO 'гггг-мм-дд',
 * опциональный хвост времени ' , Ч:мм' / ', Ч:мм' / ' Ч:мм' (у ISO — и 'T13:00').
 * → { t: миллисекунды, d: Date, hasTime: bool } или null (не распарсилось).
 */
function bookingParseDate_(v) {
  if (v === undefined || v === null || v === '') return null;
  if (Object.prototype.toString.call(v) === '[object Date]') {
    if (isNaN(v.getTime())) return null;
    return { t: v.getTime(), d: v,
             hasTime: (v.getHours() !== 0 || v.getMinutes() !== 0) };
  }
  var s = String(v).trim();
  var hh = 0, mi = 0, hasTime = false, ds = s;
  var mt = s.match(/^(.*?)\s*,?\s+(\d{1,2}):(\d{2})$/); // хвост времени через пробел/запятую
  if (mt) { ds = mt[1].trim(); hh = +mt[2]; mi = +mt[3]; hasTime = true; }
  var dd, mm, yy;
  var m1 = ds.match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})$/); // дд.мм.гггг
  if (m1) { dd = +m1[1]; mm = +m1[2]; yy = +m1[3]; }
  else {
    var m2 = ds.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:T(\d{1,2}):(\d{2})(?::\d{2})?)?$/); // ISO
    if (!m2) return null;
    yy = +m2[1]; mm = +m2[2]; dd = +m2[3];
    if (m2[4] !== undefined) { hh = +m2[4]; mi = +m2[5]; hasTime = true; }
  }
  if (hh > 23 || mi > 59) return null;
  var d = new Date(yy, mm - 1, dd, hh, mi, 0, 0);
  // new Date перекатывает 32.13 в соседний месяц — такие даты отсекаем как нечестные
  if (d.getFullYear() !== yy || d.getMonth() !== mm - 1 || d.getDate() !== dd) return null;
  return { t: d.getTime(), d: d, hasTime: hasTime };
}

function bookingPad2_(n) { return (n < 10 ? '0' : '') + n; }

/** Формат листа «клиенты» (E/F): 'дд.мм.гггг' или 'дд.мм.гггг , Ч:мм'. p — от bookingParseDate_. */
function bookingFmtDate_(p) {
  var d = p.d;
  var out = bookingPad2_(d.getDate()) + '.' + bookingPad2_(d.getMonth() + 1) + '.' + d.getFullYear();
  if (p.hasTime) out += ' , ' + d.getHours() + ':' + bookingPad2_(d.getMinutes());
  return out;
}

/**
 * Пересечение интервалов занятости [aStart, aEnd) и [bStart, bEnd), миллисекунды.
 * Касание границ НЕ конфликт (возврат утром + выдача тем же днём — штатный оборот).
 * bEnd == null → открытая аренда (даты возврата нет) — занята с bStart и дальше.
 */
function bookingOverlap_(aStart, aEnd, bStart, bEnd) {
  if (bEnd === null || bEnd === undefined) return aEnd > bStart;
  return aStart < bEnd && bStart < aEnd;
}

/** Равенство дат для дубль-чека: оба парсятся → по метке времени, иначе прежнее строковое сравнение. */
function bookingDateEq_(cellVal, inputParsed, inputRaw) {
  var cp = bookingParseDate_(cellVal);
  if (cp && inputParsed) return cp.t === inputParsed.t;
  return String(cellVal || '').trim().toLowerCase() === String(inputRaw || '').trim().toLowerCase();
}

/**
 * Одометр из ячейки Q (фикс №2 маятника row705→1268): Q в живом листе — СТРОКА
 * «<число> Km, <дата>» («35200 Km, 05.07.2026»), а не чистое число — Number(Q) давал NaN
 * и odo_unverifiable блокировал ВСЕ реальные закрытия. Принимаем РОВНО:
 *   Number-ячейку · '12345' · '12345 Km, 05.07.2026' · '12345 km' / '12345Km' (регистр любой).
 * Всё прочее (пусто / мусор / '#N/A' / голая дата '05.07.2026' / '12 345 Km' с разрывом
 * числа) → null = odo_unverifiable у вызывающего. Fail-closed цел: не уверены в числе →
 * НЕ закрываем; недопарс запрещён (лучше null, чем «12» из «12 345»).
 */
function bookingParseOdo_(qRaw) {
  if (qRaw === '' || qRaw === null || qRaw === undefined) return null;
  if (typeof qRaw === 'number') return (isNaN(qRaw) || !isFinite(qRaw)) ? null : qRaw;
  var m = String(qRaw).trim().match(/^(\d+)\s*(?:[KkКк][MmМм][\s\S]*)?$/);
  return m ? Number(m[1]) : null;
}

/**
 * Создать предварительную бронь.
 * Ожидаемые поля body:
 *   bike (обяз.), name (обяз.), date_start, date_end,
 *   pay_day, pay_month, deposit (число или "passport"), helmets,
 *   contacts, note, initial_pay, km
 * Даты принимаются в 'дд.мм.гггг[ , Ч:мм]' и ISO 'гггг-мм-дд[T Ч:мм]'; в лист пишутся
 * форматом листа. Нераспознанный формат пишется как пришёл (совместимость INTAKE).
 * Ошибки (в существующую err-ветку клиента): bad_dates (date_end не позже date_start),
 * booking_conflict (пересечение дат с Бронь/В аренде того же байка; 'Завершена' не блокирует).
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

  // --- парс/нормализация дат + валидация date_end > date_start (O3-2a) ---
  var newStart = bookingParseDate_(p.date_start);
  var newEnd   = bookingParseDate_(p.date_end);
  if (newStart && newEnd && newEnd.t <= newStart.t) {
    return { ok: false, error: 'bad_dates',
             message: 'date_end (' + bookingFmtDate_(newEnd) + ') должен быть позже date_start (' +
                      bookingFmtDate_(newStart) + ')' };
  }
  // в лист — форматом листа; нераспознанное — как пришло (не ломаем существующий флоу)
  var writeStart = newStart ? bookingFmtDate_(newStart) : p.date_start;
  var writeEnd   = newEnd   ? bookingFmtDate_(newEnd)   : p.date_end;

  var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
  var sheet = ss.getSheetByName(BOOKING.SHEET);
  if (!sheet) return { ok: false, error: 'sheet_not_found', message: BOOKING.SHEET };

  // --- защита от дубля: тот же байк (C) + имя (D) + дата начала (E) уже в статусе
  //     "Бронь" ИЛИ "В аренде" → не пишем второй раз ---
  var lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    var scan = sheet.getRange(2, 1, lastRow - 1, BOOKING.COL.DATE_END).getValues(); // A..F
    var wantBike = bikeFull.trim().toLowerCase();
    var wantName = String(p.name).trim().toLowerCase();
    for (var i = 0; i < scan.length; i++) {
      var st = String(scan[i][BOOKING.COL.STATUS - 1]     || '').trim().toLowerCase();
      var bk = String(scan[i][BOOKING.COL.BIKE - 1]       || '').trim().toLowerCase();
      var nm = String(scan[i][BOOKING.COL.NAME - 1]       || '').trim().toLowerCase();
      if ((st === 'бронь' || st === 'в аренде') &&
          bk === wantBike && nm === wantName &&
          bookingDateEq_(scan[i][BOOKING.COL.DATE_START - 1], newStart, p.date_start || '')) {
        return { ok: false, error: 'duplicate', row: i + 2, status: st,
                 message: 'Такая бронь (байк+клиент+дата) уже есть в статусе "' + scan[i][BOOKING.COL.STATUS - 1] + '"' };
      }
    }

    // --- конфликт занятости (O3-2a): пересечение [date_start, date_end] с датами
    //     ТОГО ЖЕ байка в статусе "Бронь"/"В аренде". "Завершена" НЕ блокирует.
    //     Касание границ (возврат = день новой выдачи) конфликтом НЕ считается. ---
    if (newStart) {
      var aStart = newStart.t;
      // без date_end проверяем точечно момент старта (+1мс, чтобы старт в старте чужой брони ловился)
      var aEnd = newEnd ? newEnd.t : newStart.t + 1;
      for (var j = 0; j < scan.length; j++) {
        var st2 = String(scan[j][BOOKING.COL.STATUS - 1] || '').trim().toLowerCase();
        if (st2 !== 'бронь' && st2 !== 'в аренде') continue;
        var bk2 = String(scan[j][BOOKING.COL.BIKE - 1] || '').trim().toLowerCase();
        if (bk2 !== wantBike) continue;
        var rowStart = bookingParseDate_(scan[j][BOOKING.COL.DATE_START - 1]);
        if (!rowStart) continue; // дату строки не разобрать — судить занятость не можем
        var rowEnd = bookingParseDate_(scan[j][BOOKING.COL.DATE_END - 1]); // null → открытая аренда
        if (bookingOverlap_(aStart, aEnd, rowStart.t, rowEnd ? rowEnd.t : null)) {
          var cName = String(scan[j][BOOKING.COL.NAME - 1] || '');
          var cStat = String(scan[j][BOOKING.COL.STATUS - 1] || '');
          return { ok: false, error: 'booking_conflict', row: j + 2,
                   bike: bikeFull, conflict_name: cName, conflict_status: cStat,
                   conflict_start: bookingFmtDate_(rowStart),
                   conflict_end: rowEnd ? bookingFmtDate_(rowEnd) : '',
                   message: 'Байк "' + bikeFull + '" занят: строка ' + (j + 2) + ', ' + cName +
                            ', ' + bookingFmtDate_(rowStart) + ' → ' +
                            (rowEnd ? bookingFmtDate_(rowEnd) : 'без даты возврата') +
                            ' (статус "' + cStat + '")' };
        }
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
  put(BOOKING.COL.DATE_START,  writeStart);  // нормализовано в формат листа (O3-2a)
  put(BOOKING.COL.DATE_END,    writeEnd);
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
 * date_start (опц., O3-2a): при двух бронях одного клиента на один байк уточняет,
 * КАКУЮ активировать — матч по дню (время не сравнивается); без date_start — как раньше
 * (первая подходящая по bike+name).
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

  var wantStart = bookingParseDate_(p.date_start); // null, если дата не передана/не разобрана
  var lastRow = sheet.getLastRow();
  var data = sheet.getRange(2, 1, lastRow - 1, BOOKING.COL.DATE_START).getValues(); // A..E
  for (var i = 0; i < data.length; i++) {
    var st = String(data[i][0] || '').trim().toLowerCase();
    var bk = String(data[i][BOOKING.COL.BIKE - 1] || '').trim().toLowerCase();
    var nm = String(data[i][BOOKING.COL.NAME - 1] || '').trim().toLowerCase();
    if (st === 'бронь' &&
        bk === bikeFull.trim().toLowerCase() &&
        nm === String(p.name).trim().toLowerCase()) {
      if (p.date_start) {
        var rowVal = data[i][BOOKING.COL.DATE_START - 1];
        var rp = bookingParseDate_(rowVal);
        var match = (wantStart && rp)
          ? (wantStart.d.getFullYear() === rp.d.getFullYear() &&
             wantStart.d.getMonth() === rp.d.getMonth() &&
             wantStart.d.getDate() === rp.d.getDate())
          : String(rowVal || '').trim().toLowerCase() === String(p.date_start).trim().toLowerCase();
        if (!match) continue;
      }
      sheet.getRange(i + 2, BOOKING.COL.STATUS).setValue('В аренде');
      return { ok: true, activated: true, row: i + 2, bike: bikeFull, name: p.name };
    }
  }
  return { ok: false, error: 'booking_not_found',
           message: 'Активная бронь по этому байку и клиенту' +
                    (p.date_start ? ' с датой начала ' + p.date_start : '') + ' не найдена' };
}

/**
 * Закрыть аренду: "В аренде" → "Завершена" (O3-3b, возврат байка).
 * body: bike, name (обяз.); km_end (ОБЯЗ. — пробег на сдаче → N; без него err km_required);
 *       date_start (опц. — матч строки по ДНЮ, как activateBooking);
 *       paid_total (опц. — итог оплаты → K).
 * ДЕЙСТВИЯ над найденной строкой: A='Завершена'; N=km_end (ОБЯЗАТЕЛЕН — fail-closed,
 * инцидент row705); K=paid_total если передан (иначе K не трогаем); формульные G/I/J/W
 * НЕ трогаем; F НЕ меняем (дата возврата уже стоит с брони).
 * Ошибки: missing_args / bike_not_resolved / sheet_not_found;
 *   not_active — по bike+name(+date_start) найдена только "Бронь" (сначала выдача);
 *   not_found — подходящей строки нет вовсе;
 *   ambiguous — две и более "В аренде" по этому bike+name, а date_start не сузил до одной;
 *   km_required — km_end не передан (без пробега на сдаче аренду НЕ закрываем);
 *   bad_km_end — km_end не число;
 *   odo_unverifiable — из Q строки не извлечь число (пусто/мусор; живой формат Q —
 *     «<число> Km, <дата>», парсится bookingParseOdo_, фикс №2): чек «одометр не
 *     уменьшается» провести нельзя → НЕ закрываем (fail-closed, инцидент row705;
 *     force-флага нет намеренно — сверить и закрыть руками);
 *   odometer_back — km_end меньше текущего пробега Q строки (одометр не уменьшается —
 *     правило владельца).
 */
function closeBooking(body) {
  var p = body || {};
  if (!p.bike || !p.name)
    return { ok: false, error: 'missing_args', message: 'нужны bike и name' };

  try {
  var bikeFull = resolveBikeName_(p.bike);
  if (!bikeFull) return { ok: false, error: 'bike_not_resolved', message: 'Байк не найден: ' + p.bike };

  var ss = SpreadsheetApp.openById(BOOKING.MANAGER_ID);
  var sheet = ss.getSheetByName(BOOKING.SHEET);
  if (!sheet) return { ok: false, error: 'sheet_not_found' };

  var wantBike = bikeFull.trim().toLowerCase();
  var wantName = String(p.name).trim().toLowerCase();
  var wantStart = bookingParseDate_(p.date_start); // null, если не передана/не разобрана

  var active = [];      // строки "В аренде" по bike+name(+date_start)
  var sawBooking = 0;   // строка "Бронь" по тем же критериям (для честного not_active)
  var lastRow = sheet.getLastRow();
  if (lastRow >= 2) {
    var data = sheet.getRange(2, 1, lastRow - 1, BOOKING.COL.DATE_START).getValues(); // A..E
    for (var i = 0; i < data.length; i++) {
      var st = String(data[i][0] || '').trim().toLowerCase();
      if (st !== 'в аренде' && st !== 'бронь') continue;
      var bk = String(data[i][BOOKING.COL.BIKE - 1] || '').trim().toLowerCase();
      var nm = String(data[i][BOOKING.COL.NAME - 1] || '').trim().toLowerCase();
      if (bk !== wantBike || nm !== wantName) continue;
      if (p.date_start) { // матч по ДНЮ — та же логика, что activateBooking
        var rowVal = data[i][BOOKING.COL.DATE_START - 1];
        var rp = bookingParseDate_(rowVal);
        var match = (wantStart && rp)
          ? (wantStart.d.getFullYear() === rp.d.getFullYear() &&
             wantStart.d.getMonth() === rp.d.getMonth() &&
             wantStart.d.getDate() === rp.d.getDate())
          : String(rowVal || '').trim().toLowerCase() === String(p.date_start).trim().toLowerCase();
        if (!match) continue;
      }
      if (st === 'в аренде') active.push(i + 2);
      else sawBooking = i + 2;
    }
  }

  if (active.length === 0) {
    if (sawBooking) {
      return { ok: false, error: 'not_active', row: sawBooking,
               message: 'Строка ' + sawBooking + ' по этому байку и клиенту в статусе "Бронь" — ' +
                        'аренда ещё не активирована (сначала выдача), закрывать нечего' };
    }
    return { ok: false, error: 'not_found',
             message: 'Аренда "В аренде" по этому байку и клиенту' +
                      (p.date_start ? ' с датой начала ' + p.date_start : '') + ' не найдена' };
  }
  if (active.length > 1) {
    return { ok: false, error: 'ambiguous', rows: active,
             message: 'Найдено ' + active.length + ' строк "В аренде" по этому байку и клиенту ' +
                      '(строки ' + active.join(', ') + ') — передай date_start, чтобы уточнить' };
  }
  var rowN = active[0];

  // --- km_end ОБЯЗАТЕЛЕН (fail-closed, инцидент row705): без пробега на сдаче не закрываем ---
  if (p.km_end === undefined || p.km_end === null || p.km_end === '')
    return { ok: false, error: 'km_required', row: rowN,
             message: 'km_end обязателен — без пробега на сдаче аренду не закрываем' };
  var kmEnd = Number(p.km_end);
  if (isNaN(kmEnd) || !isFinite(kmEnd))
    return { ok: false, error: 'bad_km_end', message: 'km_end не число: ' + p.km_end };
  // одометр НЕ уменьшается (сверка с формульным Q текущего пробега); Q в живом листе —
  // строка «<число> Km, <дата>» → bookingParseOdo_ (фикс №2); не распарсили число →
  // чек провести НЕЛЬЗЯ → НЕ закрываем (никакого молчаливого пропуска гейта; force-флага нет)
  var odoRaw = sheet.getRange(rowN, BOOKING.COL.ODO).getValue();
  var odo = bookingParseOdo_(odoRaw);
  if (odo === null) {
    return { ok: false, error: 'odo_unverifiable', row: rowN, odo_raw: String(odoRaw),
             km_end: kmEnd,
             message: 'одометр строки ' + rowN + ' пуст/нечитаем («' + String(odoRaw) +
                      '») — сверь и закрой руками' };
  }
  if (kmEnd < odo) {
    return { ok: false, error: 'odometer_back', row: rowN, odo: odo, km_end: kmEnd,
             message: 'km_end (' + kmEnd + ') меньше текущего пробега строки ' + rowN +
                      ' (Q=' + odo + ') — одометр не уменьшается' };
  }

  // --- запись: ТОЛЬКО A+N (+K по переданному); формульные G/I/J/W и дату F не трогаем ---
  sheet.getRange(rowN, BOOKING.COL.STATUS).setValue('Завершена');
  sheet.getRange(rowN, BOOKING.COL.KM).setValue(kmEnd);
  var paidWritten = false;
  if (p.paid_total !== undefined && p.paid_total !== null && p.paid_total !== '') {
    sheet.getRange(rowN, BOOKING.COL.INITIAL_PAY).setValue(p.paid_total);
    paidWritten = true;
  }

  return { ok: true, closed: true, row: rowN, bike: bikeFull, name: p.name,
           km_end: kmEnd, paid_total: paidWritten ? p.paid_total : null };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
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