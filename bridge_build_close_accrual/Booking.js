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

// ═══ CLOSEACCRUAL1910: начисление доплат листа закрытия в K + расшифровка примечанием к A ═══
//
// Решение владельца 19.10.2026 23:3x: доплаты ставить перед основной суммой «=» и через «+»
// (10000+500+1000) и писать в примечание к ячейке A этой строки. Это НАЧИСЛЕНИЕ к оплате, а НЕ квитанция
// о полученных деньгах: после записи K значит «основная сумма + начисленные доплаты», и ни одна строка здесь
// не утверждает, что деньги получены. Минимальный шов ЭТОГО изменения, не общий механизм. Условия Codex
// TB-REVIEW-1910-2400:
//  (1) части доплат вызывающий берёт ТОЛЬКО из свежего ответа closing_upsert той же аренды (Closing.js:
//      components + binding); здесь они сверяются с САМОЙ строкой CRM: booking_id в Y, номер строки, день
//      начала E. Расхождение — начисление стоп до записей K/примечания (само закрытие A/N идёт). Слагаемыми
//      бывают только целые числа ≥ 0 (число или строка цифр): строка, текст формулы, дробь, NaN — стоп,
//      инъекции формулы в K нет;
//      ВЕРСИЯ записи листа (замечание приёмки 20.10): части карточки фиксируются, когда она рождается, а лист
//      закрытия живёт дальше (повтор возврата, команда «закрытие» правит доплату). Поэтому под замком, ДО записей,
//      строка листа перечитывается по ТОЧНОМУ booking_id (closingRowById_, фоллбэка по байку нет): та же строка и
//      те же четыре литерала — иначе отказ closing_changed ЦЕЛИКОМ (ни A/N, ни K, ни примечания), и в ответе лист
//      как он есть (closing_now) — вызывающий рождает новую карточку новой операцией. Перед записью K лист
//      перечитывается ещё раз (разошёлся — partial, K не пишем). closing_upsert замка не берёт: окно между
//      последним чтением листа и setFormula не закрыто — это тоже НЕ атомарность;
//  (2) K и примечание A — ДВЕ записи, атомарности у Apps Script нет. Шов: стабильный close_op_id (выводится
//      из booking_id, строки брони, байка, дня начала, строки листа закрытия и точных частей; присланный id не
//      сошёлся с выводом — payload_mismatch), замок скрипта, повторное чтение ТОЙ ЖЕ строки перед записью K,
//      чтение назад после, метка операции в самом примечании: IN_PROGRESS — ДО записи K, DONE — после
//      проверенного K. Частичный исход не повторяется и не откатывается — он называется (partial/unknown).
//      ЗАМОК — НЕ АТОМАРНОСТЬ: LockService упорядочивает только заходы скрипта, взявшие этот же замок
//      (закрытия с начислением). Правку листа человеком, другой скрипт и закрытие без начисления он не
//      останавливает — от них защищает только повторное чтение строки и K перед записью;
//  (3) примечание — getNote/setNote (не setValue A: там статус), прежний текст сохраняется. Основа K
//      сохраняется со скобками: формула «=X» → «=(X)+500+1000», число v → «=v+500+1000»; метка DONE той же
//      операции — повторно не добавляем (already_done);
//  (4) пустой K — не доказанный ноль: K не трогаем, пишем только примечание «основная сумма не подтверждена»;
//      текст / ошибка / нецелое число в K — K не трогаем, только примечание, квитанция называет основу;
//  (5) квитанция начисления в ответе — accrual {status, op_id, k_readback, …}; без неё вызывающий обязан
//      считать доплаты НЕ записанными. Прежняя запись итога в K (paid_total) без явного paid_total_opt_in
//      === true НЕ исполняется (paid_total_ignored): старый Splinter не воскресит перезапись K производной
//      суммой; ни один нынешний вызывающий opt-in не ставит.
// Версия поля V: 2 — «части сверены с листом закрытия под замком». Поле другой версии — стоп bad_accrual до
// записей: сборка без сверки листа (V 1) и Splinter с V 2 друг друга не примут молча.
var CLOSE_ACCRUAL = {
  V: 2,
  PARTS: ['surcharge_days', 'surcharge_fuel', 'damage', 'other'],     // порядок слагаемых — постоянный
  LABEL: { surcharge_days: 'дни', surcharge_fuel: 'топливо', damage: 'ущерб', other: 'прочее' },
  LOCK_MS: 10000,
  OP_RE: /^co1-[0-9a-f]{16}$/,
};

/** Часть доплаты → литерал слагаемого: '' (нет / ноль), строка цифр, null (не целое число ≥ 0 — стоп). */
function closeAccrualLit_(v) {
  if (v === undefined || v === null || v === '') return '';
  var n;
  if (typeof v === 'number') {
    if (!isFinite(v) || Math.floor(v) !== v) return null;
    n = v;
  } else if (typeof v === 'string' && /^\d{1,9}$/.test(v)) {
    n = Number(v);
  } else {
    return null;
  }
  if (n < 0 || n >= 1e9) return null;
  return n === 0 ? '' : String(n);
}

/** День ячейки/строки даты → 'ГГГГ-ММ-ДД' (тем же bookingParseDate_, что матчит date_start) или null. */
function closeAccrualDay_(v) {
  var p = bookingParseDate_(v);
  if (!p) return null;
  return p.d.getFullYear() + '-' + bookingPad2_(p.d.getMonth() + 1) + '-' + bookingPad2_(p.d.getDate());
}

/** close_op_id: 'co1-' + первые 16 hex sha256 канона. Тот же вывод — у Splinter (`_acc_op_id`). */
function closeAccrualOpId_(bid, brow, bike, day, crow, lits) {
  var canon = ['co1', bid, String(brow), String(bike || '').trim().toLowerCase(), day, String(crow)]
    .concat(lits).join('|');
  var dig = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, canon, Utilities.Charset.UTF_8);
  var hex = '';
  for (var i = 0; i < dig.length; i++) { var b = (dig[i] + 256) % 256; hex += (b < 16 ? '0' : '') + b.toString(16); }
  return 'co1-' + hex.slice(0, 16);
}

/** Метки операций в примечании → [{op, state, adds, tag, tail}]. */
function closeAccrualMarks_(note) {
  var out = [], m;
  var re = /\[TB (co1-[0-9a-f]{16}) (IN_PROGRESS|DONE|NOTE_ONLY) ((?:\+\d+)+)\]([^\n]*)/g;
  while ((m = re.exec(String(note || ''))) !== null)
    out.push({ op: m[1], state: m[2], adds: m[3], tag: m[0].slice(0, m[0].length - m[4].length), tail: m[4] });
  return out;
}

function closeAccrualNorm_(f) { return String(f || '').replace(/\s+/g, '').toLowerCase(); }

function closeAccrualIdent_(sheet, rowN) {
  var r = sheet.getRange(rowN, 1, 1, BOOKING.COL.BOOKING_ID).getValues()[0]; // A..Y
  return { bike: String(r[BOOKING.COL.BIKE - 1] || '').trim(), day: closeAccrualDay_(r[BOOKING.COL.DATE_START - 1]),
           bid: String(r[BOOKING.COL.BOOKING_ID - 1] || '').trim() };
}

function closeAccrualK_(sheet, rowN) {
  var c = sheet.getRange(rowN, BOOKING.COL.INITIAL_PAY);
  return { f: String(c.getFormula() || ''), v: c.getValue() };
}

function closeAccrualKText_(k) {
  if (k.f) return k.f;
  return (k.v === '' || k.v === null || k.v === undefined) ? '' : String(k.v);
}

function closeAccrualJoin_(prev, line) { return prev ? prev + '\n' + line : line; }

/** Лист закрытия СЕЙЧАС (closingRowById_) — та же строка crow и те же четыре литерала, что у операции? */
function closeAccrualSameClosing_(cl, crow, lits) {
  if (!cl || cl.row !== crow) return false;
  for (var i = 0; i < CLOSE_ACCRUAL.PARTS.length; i++)
    if (closeAccrualLit_(cl.cur[CLOSE_ACCRUAL.PARTS[i]]) !== lits[i]) return false;
  return true;
}

/** Строка метки в примечании. Начисление, а не оплата — словами. */
function closeAccrualLine_(pl, state) {
  var parts = [];
  CLOSE_ACCRUAL.PARTS.forEach(function (k, i) { if (pl.lits[i]) parts.push(CLOSE_ACCRUAL.LABEL[k] + ' ' + pl.lits[i]); });
  var tag = '[TB ' + pl.op + ' ' + state + ' ' + pl.adds + ']';
  var what = 'доплаты (начислено к оплате, не оплата): ' + parts.join(' · ');
  if (pl.act === 'write') return tag + ' ' + what + '; K было: ' + closeAccrualKText_(pl.k0) + ' → ' + pl.formula;
  if (pl.base === 'empty') return tag + ' основная сумма не подтверждена (K пуст) — K не трогал; ' + what;
  if (pl.base === 'error') return tag + ' в K формула без числового значения — K не трогал; ' + what;
  return tag + ' в K не целое число («' + closeAccrualKText_(pl.k0).slice(0, 40) + '») — K не трогал; ' + what;
}

/**
 * План начисления — ТОЛЬКО чтение, до любых записей закрытия. → {act, reason, op, …}:
 * act 'stop' (ни одной записи K/примечания) | 'write' (формула в K + метка) | 'note_only' (K не трогаем) |
 * 'already' (метка DONE/NOTE_ONLY этой операции — повторно не добавляем) | 'recover' (метка IN_PROGRESS и K уже
 * РОВНО ожидаемый — дописать DONE, слагаемые не добавлять) | 'partial' (IN_PROGRESS, а K не ожидаемый — ни
 * одной записи, исход называем).
 * Стоп 'closing_changed' (лист закрытия разошёлся с частями операции) — особый: closeBookingRun_ по нему отказывает
 * закрытию ЦЕЛИКОМ до записей; pl.closing — найденная строка листа (или null) для ответа closing_now.
 */
function closeAccrualPlan_(sheet, rowN, p) {
  var a = p.accrual;
  var pl = { act: 'stop', reason: '', op: (a && typeof a === 'object' && typeof a.close_op_id === 'string')
             ? a.close_op_id : null, base: null, adds: '', lits: [] };
  function stop(why) { pl.act = 'stop'; pl.reason = why; return pl; }
  if (!a || typeof a !== 'object' || a.v !== CLOSE_ACCRUAL.V || !CLOSE_ACCRUAL.OP_RE.test(String(a.close_op_id || '')))
    return stop('bad_accrual');
  var parts = a.parts;
  if (!parts || typeof parts !== 'object' || Object.keys(parts).sort().join(',') !== CLOSE_ACCRUAL.PARTS.slice().sort().join(','))
    return stop('bad_accrual');
  var lits = CLOSE_ACCRUAL.PARTS.map(function (k) { return closeAccrualLit_(parts[k]); });
  if (lits.indexOf(null) >= 0) return stop('bad_component');
  pl.lits = lits;
  pl.adds = lits.filter(function (x) { return x; }).map(function (x) { return '+' + x; }).join('');
  if (!pl.adds) return stop('no_addends');
  var crow = Number(a.closing_row);
  if (!(isFinite(crow) && Math.floor(crow) === crow && crow >= 2)) return stop('bad_accrual');
  // (1) привязка — к САМОЙ строке CRM, которую закрываем
  var id0 = closeAccrualIdent_(sheet, rowN);
  if (!id0.bid || id0.bid !== String(a.booking_id || '').trim() || Number(a.booking_row) !== rowN ||
      !id0.day || id0.day !== String(a.date_start_day || ''))
    return stop('binding_mismatch');
  // (2) id выводится из ЗДЕСЬ прочитанного; присланный id с другими частями/строкой — не наша операция
  var op = closeAccrualOpId_(id0.bid, rowN, p.bike, id0.day, crow, lits);
  if (op !== a.close_op_id) return stop('payload_mismatch');
  pl.op = op;
  pl.id0 = id0;
  pl.crow = crow;
  // (1) ВЕРСИЯ: части операции — с листом закрытия СЕЙЧАС, под замком; строка — по ТОЧНОМУ booking_id брони,
  // которую закрываем. Лист не прочитан — стоп начисления (закрытие идёт, как при прочих стопах); прочитан и
  // разошёлся — closing_changed (отказ закрытию целиком, новая карточка у вызывающего)
  var cl;
  try { cl = closingRowById_(id0.bid); } catch (eC) { return stop('closing_unread: ' + String(eC)); }
  if (!closeAccrualSameClosing_(cl, crow, lits)) { pl.closing = cl; return stop('closing_changed'); }
  pl.note0 = String(sheet.getRange(rowN, BOOKING.COL.STATUS).getNote() || '');
  pl.k0 = closeAccrualK_(sheet, rowN);
  var marks = closeAccrualMarks_(pl.note0);
  var mine = marks.filter(function (m) { return m.op === op; });
  if (mine.some(function (m) { return m.adds !== pl.adds; })) return stop('payload_mismatch');
  if (mine.length) {
    if (mine.some(function (m) { return m.state === 'DONE' || m.state === 'NOTE_ONLY'; })) { pl.act = 'already'; return pl; }
    var i = mine[0].tail.lastIndexOf('→ =');
    var expF = i >= 0 ? mine[0].tail.slice(i + 2) : '';
    pl.tag = mine[0].tag;
    if (expF && closeAccrualNorm_(pl.k0.f) === closeAccrualNorm_(expF)) { pl.act = 'recover'; return pl; }
    pl.act = 'partial'; pl.reason = 'in_progress_found'; return pl;
  }
  if (marks.length) return stop('other_accrual_recorded');
  // (3)/(4) основа K
  var k0 = pl.k0;
  if (k0.f) {
    if (typeof k0.v === 'number' && isFinite(k0.v)) {
      pl.base = 'formula'; pl.act = 'write'; pl.formula = '=(' + k0.f.replace(/^=/, '') + ')' + pl.adds;
    } else { pl.base = 'error'; pl.act = 'note_only'; }
  } else if (k0.v === '' || k0.v === null || k0.v === undefined) {
    pl.base = 'empty'; pl.act = 'note_only';
  } else if (typeof k0.v === 'number' && isFinite(k0.v) && Math.floor(k0.v) === k0.v && Math.abs(k0.v) < 1e15) {
    pl.base = 'number'; pl.act = 'write'; pl.formula = '=' + String(k0.v) + pl.adds;
  } else {
    pl.base = 'text'; pl.act = 'note_only';
  }
  return pl;
}

/** Исполнение плана — ПОСЛЕ записи A/N, под тем же замком. → квитанция начисления. Не бросает. */
function closeAccrualApply_(sheet, rowN, pl) {
  var rc = { v: CLOSE_ACCRUAL.V, op_id: pl.op, status: 'stopped', reason: pl.reason || '', base: pl.base,
             k_written: false, note: null, addends: pl.adds || '', k_readback: null };
  var stage = 'plan';
  var cell = null;
  try {
    cell = sheet.getRange(rowN, BOOKING.COL.STATUS);
    if (pl.act === 'already') {
      rc.status = 'already_done';
    } else if (pl.act === 'partial') {
      rc.status = 'partial';
    } else if (pl.act === 'recover') {
      stage = 'note_done';
      var nr = String(cell.getNote() || '');
      var doneTag = pl.tag.replace(' IN_PROGRESS ', ' DONE ');
      cell.setNote(nr.replace(pl.tag, doneTag));
      if (String(cell.getNote() || '').indexOf(doneTag) >= 0) { rc.status = 'already_done'; rc.recovered = true; }
      else { rc.status = 'partial'; rc.reason = 'note_done_unconfirmed'; }
    } else if ((pl.act === 'note_only' || pl.act === 'write') && String(cell.getNote() || '') !== pl.note0) {
      rc.status = 'stopped'; rc.reason = 'note_changed_before_write';   // примечание правили после плана
    } else if (pl.act === 'note_only') {
      var only = closeAccrualLine_(pl, 'NOTE_ONLY');
      stage = 'note_only';
      cell.setNote(closeAccrualJoin_(pl.note0, only));
      if (String(cell.getNote() || '').indexOf(only) >= 0) rc.status = 'done';
      else { rc.status = 'unknown'; rc.reason = 'note_readback_mismatch'; }
    } else if (pl.act === 'write') {
      var line = closeAccrualLine_(pl, 'IN_PROGRESS');
      stage = 'note_in_progress';                         // метка ДО записи K
      cell.setNote(closeAccrualJoin_(pl.note0, line));
      if (String(cell.getNote() || '').indexOf(line) < 0) {
        rc.status = 'unknown'; rc.reason = 'note_readback_mismatch';
      } else {
        stage = 'prestate';                               // та же строка, тот же K — иначе K не пишем
        var id1 = closeAccrualIdent_(sheet, rowN), k1 = closeAccrualK_(sheet, rowN);
        var same = id1.bid === pl.id0.bid && id1.day === pl.id0.day && id1.bike === pl.id0.bike &&
                   (pl.base === 'formula' ? k1.f === pl.k0.f : (k1.f === '' && k1.v === pl.k0.v));
        // лист закрытия — ещё раз, вплотную к записи K (closing_upsert замка не берёт и мог пройти после плана)
        var sameCl = same && closeAccrualSameClosing_(closingRowById_(pl.id0.bid), pl.crow, pl.lits);
        if (!same) {
          rc.status = 'partial'; rc.reason = 'prestate_changed';
        } else if (!sameCl) {
          rc.status = 'partial'; rc.reason = 'closing_changed';
        } else {
          stage = 'k_write';
          sheet.getRange(rowN, BOOKING.COL.INITIAL_PAY).setFormula(pl.formula);
          stage = 'k_readback';
          if (closeAccrualNorm_(closeAccrualK_(sheet, rowN).f) !== closeAccrualNorm_(pl.formula)) {
            rc.status = 'unknown'; rc.reason = 'k_readback_mismatch';
          } else {
            rc.k_written = true;
            stage = 'k_verified';
            var n1 = String(cell.getNote() || '');
            if (n1.indexOf(line) < 0) {
              rc.status = 'partial'; rc.reason = 'note_changed';
            } else {
              var done = closeAccrualLine_(pl, 'DONE');
              stage = 'note_done';                        // DONE — только после проверенного K
              cell.setNote(n1.replace(line, done));
              if (String(cell.getNote() || '').indexOf(done) >= 0) rc.status = 'done';
              else { rc.status = 'partial'; rc.reason = 'note_done_unconfirmed'; }
            }
          }
        }
      }
    }
  } catch (err) {
    // до первой записи — «стоп»; до проверенного K — «неизвестно» (K или метка могли лечь); после метки
    // IN_PROGRESS без записи K или после проверенного K — «частично»
    rc.status = stage === 'plan' ? 'stopped'
      : (stage === 'prestate' || stage === 'k_verified' || stage === 'note_done') ? 'partial' : 'unknown';
    rc.reason = 'exception_at_' + stage + ': ' + String(err);
  }
  try { rc.k_readback = closeAccrualKText_(closeAccrualK_(sheet, rowN)); } catch (e) { rc.k_readback = null; }
  try {
    var ms = closeAccrualMarks_(sheet.getRange(rowN, BOOKING.COL.STATUS).getNote())
      .filter(function (m) { return m.op === pl.op; });
    rc.note = ms.length ? ms[ms.length - 1].state : null;
  } catch (e2) { rc.note = null; }
  return rc;
}

/**
 * Закрыть аренду: "В аренде" → "Завершена" (O3-3b, возврат байка).
 * body: bike, name (обяз.); km_end (ОБЯЗ. — пробег на сдаче → N; без него err km_required);
 *       date_start (опц. — матч строки по ДНЮ, как activateBooking);
 *       paid_total (опц. — итог оплаты → K) — CLOSEACCRUAL1910: пишется ТОЛЬКО при paid_total_opt_in === true
 *         и без accrual; иначе не пишется и ответ говорит paid_total_ignored: true;
 *       accrual (опц., CLOSEACCRUAL1910) — начисление доплат листа закрытия: {v:2, close_op_id, booking_id,
 *         booking_row, date_start_day, closing_row, parts:{surcharge_days, surcharge_fuel, damage, other}};
 *         весь заход — под замком скрипта; квитанция — поле accrual ответа (см. блок CLOSEACCRUAL выше).
 * ДЕЙСТВИЯ над найденной строкой: A='Завершена'; N=km_end (ОБЯЗАТЕЛЕН — fail-closed,
 * инцидент row705); K=paid_total если передан (иначе K не трогаем); формульные G/I/J/W
 * НЕ трогаем; F НЕ меняем (дата возврата уже стоит с брони).
 * Ошибки: missing_args / bike_not_resolved / sheet_not_found;
 *   lock_busy (CLOSEACCRUAL1910) — замок закрытия с начислением не взят за LOCK_MS: ни одной записи;
 *   closing_changed (CLOSEACCRUAL1910) — части начисления разошлись с листом закрытия СЕЙЧАС (строка по точному
 *     booking_id): ни одной записи, closing_now — лист как он есть (вид ответа closing_upsert) для новой карточки;
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

  // CLOSEACCRUAL1910: закрытие с начислением — весь заход (поиск строки, план, записи) под замком скрипта.
  // Замок упорядочивает только такие же заходы и атомарности НЕ даёт (см. блок CLOSEACCRUAL выше).
  // Без accrual — прежний путь без замка.
  var hasAcc = p.accrual !== undefined && p.accrual !== null;
  if (!hasAcc) return closeBookingRun_(p, false);
  var lock = null;
  try { lock = LockService.getScriptLock(); } catch (eL) { lock = null; }
  if (!lock || !lock.tryLock(CLOSE_ACCRUAL.LOCK_MS)) {
    return { ok: false, error: 'lock_busy',
             message: 'замок закрытия с начислением не взят за ' + CLOSE_ACCRUAL.LOCK_MS + ' мс — ничего не писал',
             accrual: { v: CLOSE_ACCRUAL.V, op_id: (p.accrual && typeof p.accrual.close_op_id === 'string')
                        ? p.accrual.close_op_id : null, status: 'stopped', reason: 'lock_busy', base: null,
                        k_written: false, note: null, addends: '', k_readback: null } };
  }
  try {
    return closeBookingRun_(p, true);
  } finally {
    lock.releaseLock();
  }
}

/** Тело closeBooking (прежнее; CLOSEACCRUAL1910 — план начисления до записей, квитанция после). */
function closeBookingRun_(p, hasAcc) {
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

  // CLOSEACCRUAL1910: план начисления — только чтение, ДО записей закрытия. Сбой чтения плана закрытие не
  // останавливает: начисление — стоп, без единой записи K/примечания
  var plan = null;
  if (hasAcc) {
    try { plan = closeAccrualPlan_(sheet, rowN, p); }
    catch (eP) { plan = { act: 'stop', reason: 'plan_unread: ' + String(eP), op: null, base: null, adds: '', lits: [] }; }
  }
  if (plan && plan.act === 'stop' && plan.reason === 'closing_changed') {
    // ВЕРСИЯ (замечание приёмки 20.10): карточку подтверждали на ДРУГИХ доплатах — не пишем НИЧЕГО (ни A/N, ни K,
    // ни примечания), отдаём лист как он есть; вызывающий рождает новую карточку новой операцией. Отказ ДО записей
    // — для вызывающего «не записано», как lock_busy
    var now;
    try { now = closingReplyOf_(plan.closing); } catch (eN) { now = { ok: false, error: 'closing_unread', message: String(eN) }; }
    return { ok: false, error: 'closing_changed', row: rowN, closing_now: now,
             message: 'лист закрытия этой брони изменился после карточки — ничего не писал, нужна новая карточка',
             accrual: { v: CLOSE_ACCRUAL.V, op_id: plan.op, status: 'stopped', reason: 'closing_changed', base: null,
                        k_written: false, note: null, addends: plan.adds || '', k_readback: null } };
  }
  try {
  // --- запись: ТОЛЬКО A+N (+K по переданному); формульные G/I/J/W и дату F не трогаем ---
  sheet.getRange(rowN, BOOKING.COL.STATUS).setValue('Завершена');
  sheet.getRange(rowN, BOOKING.COL.KM).setValue(kmEnd);
  var paidWritten = false, paidIgnored = false;
  if (p.paid_total !== undefined && p.paid_total !== null && p.paid_total !== '') {
    // CLOSEACCRUAL1910 (условие (5)): прежняя запись итога в K — только явным opt-in и не в заходе начисления
    if (p.paid_total_opt_in === true && !hasAcc) {
      sheet.getRange(rowN, BOOKING.COL.INITIAL_PAY).setValue(p.paid_total);
      paidWritten = true;
    } else {
      paidIgnored = true;
    }
  }

  var res = { ok: true, closed: true, row: rowN, bike: bikeFull, name: p.name,
              km_end: kmEnd, paid_total: paidWritten ? p.paid_total : null };
  if (paidIgnored) res.paid_total_ignored = true;
  if (plan) res.accrual = closeAccrualApply_(sheet, rowN, plan);   // не бросает
  return res;
  } catch (errW) {
    var bad = { ok: false, error: 'write_failed', message: String(errW) };
    if (plan) bad.accrual = { v: CLOSE_ACCRUAL.V, op_id: plan.op, status: 'stopped', reason: 'close_write_failed',
                              base: null, k_written: false, note: null, addends: plan.adds || '', k_readback: null };
    return bad;
  }
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