/**
 * QuotePrice.gs — read-only расчёт цены аренды: quote_price(bike, date_start, date_end).
 *
 * СТРОГО БЕЗ ЗАПИСИ: ничего не пишет ни в один лист (в т.ч. НЕ трогает
 * F2/F3 «Календаря бронирования») — только читает и считает.
 *
 * Источники (живые, из CRM «менеджеру Байки»):
 *   - 'цены альт'  — базовые цены (B), цена с глобальной скидкой (C), депозит (H),
 *                    глобальные скидки категорий B2/B9/B19 (= 'Календарь бронирования'!H3/I3/J3);
 *   - 'клиенты'    — занятость: строка со статусом "Бронь", или "В аренде" с B<>"ON",
 *                    пересекающая запрошенный период (E<=date_end И F>=date_start) —
 *                    та же логика, что формула FILTER в F5 «Календаря бронирования».
 *
 * Кривые «скидка за срок» перенесены 1-в-1 из формул колонки G листа 'цены альт'
 * (сверено по XLSX-экспорту 03.07.2026, значения совпадают с колонкой J Календаря):
 *   moto1_xsr (XSR 155):      d<=5 → 0; d<=13 → 5%+(d-6)*1%; d<=30 → min(45%, 25%+(d-13)*1.5%); >30 → 45%
 *   moto1     (CB300R/REBEL/MT-03/NINJA400): d<=3 → 0; d<=6 → 10%; d<=13 → 10%+(d-6)*1%;
 *                             d<=30 → min(45%, 25%+(d-13)*1.5%); >30 → 45%
 *   moto2     (VULCAN/CBR650/CB650/XSR900/R7): d<=5 → 0; d=6 → 10%; d<=13 → 11%+(d-7)*1%;
 *                             d<=30 → 18%+(d-14)*2%; >30 → 50%
 *   scooter   (остальные):    d<=5 → 0; d=6 → 5%; d<=13 → 6%+(d-7)*1%;
 *                             d<=30 → 18%+(d-14)*1.0625%; >30 → 35%
 *
 * СЕЗОННОСТЬ: отдельной таблицы сезонов в CRM нет — сезон кодируется глобальными
 * скидками категорий H3/I3/J3 «Календаря бронирования» (их крутит владелец при смене
 * сезона; сейчас low season → 15%/15%/25%). Возвращаем label low/high + сырую скидку.
 *
 * КАПЫ-АКЦИИ low season (05.07.2026, адрес перенесён 05.07.2026): блок
 * «Модель | Кап ฿/мес | Активен» на листе «Календарь бронирования» по ЕДИНОМУ адресу
 * CAPS_ANCHOR — сейчас шапка Z3, данные Z4:AB15 (12 моделей). Убран ПОДАЛЬШЕ вправо от
 * рабочего вида (был K3:M15, вставал впритык к живой J-квоте строк байков 4–36 и мешал
 * менеджеру). В ответ добавляются поля cap_price/cap_active (резолв модели байка → строка
 * капа). ЛОГИКИ ПОДМЕНЫ ЦЕНЫ ЗДЕСЬ НЕТ — подмена/оффер на стороне userbot. Блока по
 * адресу нет / не читается → cap_price: null, cap_active: false, quote_price работает как раньше.
 */

// Строки 'цены альт': [модель, строка листа (1-indexed), кривая скидок, regex распознавания,
// cap — ключ строки в блоке капов Календаря (normalized-имя из колонки «Модель» CAPS_ANCHOR), null = капа нет]
var QUOTE_MODELS = [
  { model: 'YAMAHA XSR 155',            row: 3,  curve: 'moto1_xsr', re: /xsr\s*155/,        cap: 'xsr155' },
  { model: 'HONDA CB 300R',             row: 4,  curve: 'moto1',     re: /cb\s*300/,         cap: 'cb300r' },
  { model: 'HONDA REBEL 300',           row: 5,  curve: 'moto1',     re: /rebel/,            cap: null },
  { model: 'YAMAHA MT-03 300',          row: 6,  curve: 'moto1',     re: /mt[\s-]*03/,       cap: 'mt-03' },
  { model: 'KAWASAKI NINJA 400',        row: 7,  curve: 'moto1',     re: /ninja/,            cap: 'ninja400' },
  { model: 'KAWA VULCAN 650S',          row: 10, curve: 'moto2',     re: /vulcan/,           cap: 'vulcan' },
  { model: 'HONDA CBR 650R',            row: 11, curve: 'moto2',     re: /cbr\s*650/,        cap: 'cb650r/cbr650r' },
  { model: 'HONDA CB 650R',             row: 12, curve: 'moto2',     re: /cb\s*650/,         cap: 'cb650r/cbr650r' },
  { model: 'YAMAHA XSR 900',            row: 13, curve: 'moto2',     re: /xsr\s*900/,        cap: null },
  { model: 'YAMAHA R7',                 row: 14, curve: 'moto2',     re: /(^|[^a-z0-9])r7([^0-9]|$)/, cap: null },
  { model: 'HONDA CLICK 125',           row: 20, curve: 'scooter',   re: /click/,            cap: null },
  { model: 'HONDA PCX150',              row: 21, curve: 'scooter',   re: /pcx\s*150/,        cap: null },
  { model: 'HONDA ADV 150',             row: 22, curve: 'scooter',   re: /(^|[^x])adv\s*150/, cap: null },
  { model: 'YAMAHA NMAX 155',           row: 23, curve: 'scooter',   re: /nmax/,             cap: 'nmax' },
  { model: 'HONDA PCX 160',             row: 24, curve: 'scooter',   re: /pcx\s*160/,        cap: null },
  { model: 'HONDA ADV 160',             row: 25, curve: 'scooter',   re: /(^|[^x])adv\s*160/, cap: null },
  { model: 'HONDA FORZA 300',           row: 26, curve: 'scooter',   re: /forza/,            cap: 'forza300' },
  // NEW проверяется ПЕРЕД старым XMAX (как колонки D/E Календаря: regexmatch "xmax 300" + "new")
  { model: 'YAMAHA XMAX 300 NEW 2023-', row: 28, curve: 'scooter',   re: /xmax\s*300(?=.*new)/, cap: 'xmax new' },
  { model: 'YAMAHA XMAX300 2020-2022',  row: 27, curve: 'scooter',   re: /xmax\s*300/,       cap: 'xmax old' },
  { model: 'HONDA ADV 350',             row: 29, curve: 'scooter',   re: /(^|[^x])adv\s*350/, cap: 'adv350' },
  { model: 'HONDA XADV 750',            row: 30, curve: 'scooter',   re: /xadv\s*750/,       cap: 'xadv750' },
];

// ЕДИНЫЙ адрес блока капов low season в «Календаре бронирования» — ОДНА точка правды.
// Чтение (quoteReadCaps_) и запись (setCaps/toggleCap) берут адрес ОТСЮДА → всегда синхронны;
// будущий перенос блока = правка ТОЛЬКО этих трёх полей.
// Сейчас: шапка Z3 «Модель | Кап ฿/мес | Активен», данные Z4:AB15 (до 12 моделей).
// Перенесён вправо от рабочего вида (был K3:M15 — впритык к живой J-квоте строк 4–36, мешал менеджеру).
var CAPS_ANCHOR = {
  col: 26,        // Z — колонка «Модель» (AA = «Кап ฿/мес», AB = «Активен»)
  headerRow: 3,   // Z3 — шапка (та же строка, что глобальные скидки H3/I3/J3)
  dataRows: 12    // Z4:AB15 — максимум строк данных; чтение до первой пустой «Модели»
};

// Глобальные скидки категорий в 'цены альт' (зеркала 'Календарь бронирования'!H3/I3/J3)
var QUOTE_DISCOUNT_CELLS = { moto1: 'B2', moto2: 'B9', scooter: 'B19' };

/** Нормализация имени байка: как в формулах Календаря — LOWER + кириллическое "сс" → "cc". */
function quoteNorm_(s) {
  return String(s || '').toLowerCase()
    .replace(/сс/g, 'cc')   // кириллица в "155СС"
    .replace(/с/g, 'c')     // одиночная кириллическая с (на всякий)
    .trim();
}

/** Скидка за срок (доля 0..1) — 1-в-1 формулы колонки G 'цены альт'. */
function quoteDurationDiscount_(curve, d) {
  if (curve === 'moto1_xsr') {
    if (d <= 5) return 0;
    if (d <= 13) return 0.05 + (d - 6) * 0.01;
    if (d <= 30) return Math.min(0.45, 0.25 + (d - 13) * 0.015);
    return 0.45;
  }
  if (curve === 'moto1') {
    if (d <= 3) return 0;
    if (d <= 6) return 0.10;
    if (d <= 13) return 0.10 + (d - 6) * 0.01;
    if (d <= 30) return Math.min(0.45, 0.25 + (d - 13) * 0.015);
    return 0.45;
  }
  if (curve === 'moto2') {
    if (d <= 5) return 0;
    if (d === 6) return 0.10;
    if (d <= 13) return 0.11 + (d - 7) * 0.01;
    if (d <= 30) return 0.18 + (d - 14) * 0.02;
    return 0.50;
  }
  // scooter
  if (d <= 5) return 0;
  if (d === 6) return 0.05;
  if (d <= 13) return 0.06 + (d - 7) * 0.01;
  if (d <= 30) return 0.18 + (d - 14) * 0.010625;
  return 0.35;
}

/** Парс даты: Date как есть; строки "dd.mm.yyyy" / "dd-mm-yyyy" / "yyyy-mm-dd". null если не вышло. */
function quoteParseDate_(v) {
  if (v && typeof v.getTime === 'function' && !isNaN(v.getTime())) {
    return new Date(v.getFullYear(), v.getMonth(), v.getDate());
  }
  var s = String(v || '').trim();
  if (!s) return null;
  var m = s.match(/^(\d{4})[.\-\/](\d{1,2})[.\-\/](\d{1,2})/);          // yyyy-mm-dd
  if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
  m = s.match(/^(\d{1,2})[.\-\/](\d{1,2})[.\-\/](\d{2,4})/);            // dd.mm.yyyy
  if (m) {
    var y = +m[3]; if (y < 100) y += 2000;
    return new Date(y, +m[2] - 1, +m[1]);
  }
  return null;
}

/** Нормализация имени модели в блоке капов: lower + схлопнуть пробелы. */
function quoteNormCap_(s) {
  return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim();
}

/** Номер колонки (1-indexed) → буква(ы) A1-нотации: 26 → 'Z', 27 → 'AA', 28 → 'AB'. */
function quoteColLetter_(col) {
  var s = '';
  while (col > 0) {
    var m = (col - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    col = Math.floor((col - 1) / 26);
  }
  return s;
}

/**
 * Чтение блока капов из «Календаря бронирования» ОТ CAPS_ANCHOR (Z3): {normName: {cap, active}}.
 * Шапка по адресу не «Модель» → null (блока по адресу нет — не ошибка). Данные читаются
 * от Z4 вниз (CAPS_ANCHOR.dataRows) до первой пустой «Модели».
 */
function quoteReadCaps_() {
  var cal = getSheet('MANAGER', CONFIG.TABS.CALENDAR);
  var head = cal.getRange(CAPS_ANCHOR.headerRow, CAPS_ANCHOR.col, 1, 3).getValues()[0];
  if (quoteNormCap_(head[0]) !== 'модель') return null;   // блока по адресу нет
  var rows = cal.getRange(CAPS_ANCHOR.headerRow + 1, CAPS_ANCHOR.col, CAPS_ANCHOR.dataRows, 3).getValues();
  var map = {};
  for (var j = 0; j < rows.length; j++) {
    var name = quoteNormCap_(rows[j][0]);
    if (!name) break;   // первая пустая «Модель» = конец блока
    var capNum = Number(String(rows[j][1]).replace(/[^\d.]/g, ''));
    var act = quoteNormCap_(rows[j][2]);
    map[name] = {
      cap: (capNum && !isNaN(capNum)) ? capNum : null,
      active: (act === 'да' || act === 'yes' || act === 'true' || act === '1')
    };
  }
  return map;
}

/** Модель по точному имени байка из "список мото". null если не распознали. */
function quoteMatchModel_(bikeFull) {
  var norm = quoteNorm_(bikeFull);
  for (var i = 0; i < QUOTE_MODELS.length; i++) {
    if (QUOTE_MODELS[i].re.test(norm)) return QUOTE_MODELS[i];
  }
  return null;
}

/**
 * quote_price — read-only. body/params: bike, date_start, date_end.
 * → { ok, bike, model, days, day_price, total, deposit, available, conflicts, season,
 *     cap_price, cap_active, text }
 */
function quotePrice(body) {
  var p = body || {};
  if (!p.bike) return { ok: false, error: 'missing_bike', message: 'bike обязателен' };

  var dStart = quoteParseDate_(p.date_start);
  var dEnd = quoteParseDate_(p.date_end);
  if (!dStart || !dEnd)
    return { ok: false, error: 'bad_dates',
             message: 'date_start/date_end: жду dd.mm.yyyy | dd-mm-yyyy | yyyy-mm-dd' };
  var days = Math.round((dEnd.getTime() - dStart.getTime()) / 86400000); // как G3 = ABS(F3-F2)
  if (days < 1)
    return { ok: false, error: 'bad_period', message: 'date_end должен быть позже date_start (мин. 1 день)' };

  try {
    // --- байк → точное имя из "список мото" (та же функция, что у create_booking) ---
    var bikeFull = resolveBikeName_(p.bike);
    if (!bikeFull)
      return { ok: false, error: 'bike_not_resolved',
               message: 'Байк "' + p.bike + '" не найден однозначно в "список мото"' };

    var mdl = quoteMatchModel_(bikeFull);
    if (!mdl)
      return { ok: false, error: 'model_not_priced', bike: bikeFull,
               message: 'Модель байка не найдена в прайсе "цены альт": ' + bikeFull };

    // --- живые цены из 'цены альт': C (день с глобальной скидкой), B (базовая), H (депозит) ---
    var priceTab = getSheet('MANAGER', CONFIG.TABS.PRICES_ALT);
    var rowVals = priceTab.getRange(mdl.row, 1, 1, 8).getValues()[0];   // A..H
    var baseDaily = Number(rowVals[2]);                                  // C — уже с глобальной скидкой
    var deposit = Number(rowVals[7]);                                    // H
    var groupKey = (mdl.curve === 'moto2') ? 'moto2' : (mdl.curve === 'scooter' ? 'scooter' : 'moto1');
    var globalDiscount = Number(priceTab.getRange(QUOTE_DISCOUNT_CELLS[groupKey]).getValue());
    if (!baseDaily || isNaN(baseDaily))
      return { ok: false, error: 'price_read_failed', message: 'Пустая цена в "цены альт" строка ' + mdl.row };

    // --- расчёт (как колонка G 'цены альт' / J Календаря) ---
    var disc = quoteDurationDiscount_(mdl.curve, days);
    var dayPrice = Math.round(baseDaily * (1 - disc));
    var total = Math.round(baseDaily * days * (1 - disc));

    // --- доступность: как FILTER в F5 Календаря (пересечение периода в 'клиенты') ---
    var clients = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
    var lastRow = clients.getLastRow();
    var conflicts = 0;
    if (lastRow >= 2) {
      var rows = clients.getRange(2, 1, lastRow - 1, 6).getValues();     // A..F
      var wantBike = quoteNorm_(bikeFull);
      for (var i = 0; i < rows.length; i++) {
        var st = String(rows[i][0] || '').trim().toLowerCase();
        var isBusyStatus = (st === 'бронь') ||
          (st === 'в аренде' && String(rows[i][1] || '').trim().toUpperCase() !== 'ON');
        if (!isBusyStatus) continue;
        if (quoteNorm_(rows[i][2]) !== wantBike) continue;
        var rs = quoteParseDate_(rows[i][4]);                            // E — начало
        var re = quoteParseDate_(rows[i][5]);                            // F — конец
        if (!rs || !re) continue;
        if (rs.getTime() <= dEnd.getTime() && re.getTime() >= dStart.getTime()) conflicts++;
      }
    }
    var available = (conflicts === 0);

    // --- сезон: кодируется глобальной скидкой категории (H3/I3/J3 Календаря) ---
    var season = {
      label: globalDiscount > 0 ? 'low' : 'high',
      global_discount: globalDiscount,
      source: "Календарь бронирования H3/I3/J3 (через 'цены альт' B2/B9/B19)"
    };

    // --- кап-акция low season: блок капов справа от H3/I3/J3 (подмену цены делает userbot) ---
    var capPrice = null, capActive = false;
    try {
      var caps = (mdl.cap) ? quoteReadCaps_() : null;
      var capEntry = (caps && caps[mdl.cap]) ? caps[mdl.cap] : null;
      if (capEntry) {
        capPrice = capEntry.cap;
        capActive = !!(capEntry.active && capEntry.cap);
      }
    } catch (capErr) {
      // блок не читается → cap-полей нет (null/false), сам quote_price НЕ падает
    }

    return {
      ok: true,
      bike: bikeFull,
      model: mdl.model,
      days: days,
      day_price: dayPrice,
      total: total,
      deposit: deposit,
      available: available,
      conflicts: conflicts,
      season: season,
      cap_price: capPrice,
      cap_active: capActive,
      text: mdl.model + ' | дней: ' + days + ', стоимость: ' + total +
            ' (скидка за срок ' + Math.round(disc * 100) + '%, ' + dayPrice + ' в день), депозит: ' +
            deposit + ' бат' + (available ? '' : ' | ⚠️ ЗАНЯТ на эти даты (пересечений: ' + conflicts + ')')
    };
  } catch (err) {
    return { ok: false, error: 'quote_failed', message: String(err) };
  }
}

// ═══ ЗАПИСЬ БЛОКА КАПОВ (05.07.2026) — set_caps / toggle_cap ═══
// ЕДИНСТВЕННОЕ место записи QuotePrice: блок капов по адресу CAPS_ANCHOR (сейчас Z3:AB15)
// «Календаря бронирования». Запись идёт ТУДА ЖЕ, откуда читает quoteReadCaps_ — один адрес.
// «Календарь бронирования» — ЖИВАЯ рабочая таблица → оба экшена требуют confirmed=true
// (тот же гейт, что set_fleet_oil) + они в REDZONE_LOCK (Bridge.js). Сам quote_price
// остаётся строго read-only.

/** Парс флага вкл/выкл: true/false, 'on'/'off', 'да'/'нет', 'yes'/'no', '1'/'0'. null = не понял. */
function quoteParseOnOff_(v) {
  if (v === true) return true;
  if (v === false) return false;
  var s = quoteNormCap_(v);
  if (s === 'on' || s === 'да' || s === 'yes' || s === 'true' || s === '1') return true;
  if (s === 'off' || s === 'нет' || s === 'no' || s === 'false' || s === '0') return false;
  return null;
}

/**
 * set_caps — создаёт/перезаписывает блок капов ЦЕЛИКОМ по адресу CAPS_ANCHOR (Z3:AB15).
 * body: { confirmed: true, caps: [{model:String, cap:Number, active:Bool|String}, ...] }
 *   (1..CAPS_ANCHOR.dataRows строк). Пишет шапку + строки от адреса, лишний хвост старого
 *   блока (до dataRows) дочищается.
 * → { ok, header_cell, rows, models } | { ok:false, error }
 */
function setCaps(body) {
  var p = body || {};
  if (p.confirmed !== true)
    return { ok: false, error: 'not_confirmed',
             message: 'Запись блока капов в «Календарь бронирования» требует confirmed=true' };
  var caps = p.caps;
  if (!caps || !caps.length)
    return { ok: false, error: 'missing_caps', message: 'caps: жду непустой список {model, cap, active}' };
  if (caps.length > CAPS_ANCHOR.dataRows)
    return { ok: false, error: 'too_many_caps',
             message: 'Максимум ' + CAPS_ANCHOR.dataRows + ' строк капов, пришло ' + caps.length };

  var rows = [];
  for (var i = 0; i < caps.length; i++) {
    var name = String(caps[i].model || '').trim();
    var capNum = Number(caps[i].cap);
    var act = quoteParseOnOff_(caps[i].active === undefined ? true : caps[i].active);
    if (!name)
      return { ok: false, error: 'bad_cap_row', message: 'Строка ' + (i + 1) + ': пустая model' };
    if (!capNum || isNaN(capNum) || capNum <= 0)
      return { ok: false, error: 'bad_cap_row',
               message: 'Строка ' + (i + 1) + ' (' + name + '): cap должен быть числом > 0, пришло ' + caps[i].cap };
    if (act === null)
      return { ok: false, error: 'bad_cap_row',
               message: 'Строка ' + (i + 1) + ' (' + name + '): active непонятен: ' + caps[i].active };
    rows.push([name, capNum, act ? 'да' : 'нет']);
  }

  try {
    var cal = getSheet('MANAGER', CONFIG.TABS.CALENDAR);
    var col = CAPS_ANCHOR.col;
    var hr = CAPS_ANCHOR.headerRow;
    cal.getRange(hr, col, 1, 3).setValues([['Модель', 'Кап ฿/мес', 'Активен']]);
    cal.getRange(hr + 1, col, rows.length, 3).setValues(rows);
    var tailRows = CAPS_ANCHOR.dataRows - rows.length;
    if (tailRows > 0)   // старый блок мог быть длиннее — дочищаем хвост до конца региона
      cal.getRange(hr + 1 + rows.length, col, tailRows, 3).clearContent();
    return { ok: true, header_cell: quoteColLetter_(col) + hr, rows: rows.length,
             models: rows.map(function (r) { return r[0]; }) };
  } catch (err) {
    return { ok: false, error: 'set_caps_failed', message: String(err) };
  }
}

/**
 * toggle_cap — переключает «Активен» одной модели в существующем блоке капов.
 * body: { confirmed: true, model: String, on: Bool|'on'|'off'|'да'|'нет' }.
 * → { ok, model, cap_price, cap_active } | { ok:false, error }
 */
function toggleCap(body) {
  var p = body || {};
  if (p.confirmed !== true)
    return { ok: false, error: 'not_confirmed',
             message: 'Переключение капа в «Календаре бронирования» требует confirmed=true' };
  var want = quoteNormCap_(p.model);
  if (!want) return { ok: false, error: 'missing_model', message: 'model обязателен' };
  var on = quoteParseOnOff_(p.on);
  if (on === null)
    return { ok: false, error: 'bad_on', message: 'on: жду on/off | да/нет | true/false, пришло ' + p.on };

  try {
    var cal = getSheet('MANAGER', CONFIG.TABS.CALENDAR);
    var col = CAPS_ANCHOR.col;
    var hr = CAPS_ANCHOR.headerRow;
    var head = cal.getRange(hr, col, 1, 1).getValues()[0];
    if (quoteNormCap_(head[0]) !== 'модель')
      return { ok: false, error: 'no_cap_block',
               message: 'Блока капов нет по адресу в «Календаре бронирования» — сначала set_caps' };
    var vals = cal.getRange(hr + 1, col, CAPS_ANCHOR.dataRows, 2).getValues();
    for (var j = 0; j < vals.length; j++) {
      var name = quoteNormCap_(vals[j][0]);
      if (!name) break;   // первая пустая «Модель» = конец блока
      if (name === want) {
        cal.getRange(hr + 1 + j, col + 2).setValue(on ? 'да' : 'нет');
        var capNum = Number(String(vals[j][1]).replace(/[^\d.]/g, ''));
        return { ok: true, model: String(vals[j][0]), cap_price: (capNum && !isNaN(capNum)) ? capNum : null,
                 cap_active: on };
      }
    }
    return { ok: false, error: 'model_not_found',
             message: 'Модель "' + p.model + '" не найдена в блоке капов' };
  } catch (err) {
    return { ok: false, error: 'toggle_cap_failed', message: String(err) };
  }
}
