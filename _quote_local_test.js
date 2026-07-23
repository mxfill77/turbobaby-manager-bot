/**
 * Локальный функциональный тест quotePrice (без деплоя): eval QuotePrice.js с моками
 * листов. Эталоны = ЖИВЫЕ значения J-колонки «Календаря бронирования» (экспорт 03.07.2026,
 * F2=08.07.2026, F3=15.07.2026, дней=7) — расчёт обязан совпасть с самим листом.
 */
const fs = require('fs');
const vm = require('vm');

// C-колонка 'цены альт' (живые значения 03.07.2026) и депозиты H
const PRICE_ROWS = {
  3:  ['YAMAHA XSR 155', 590, 502, '', '', '', '', 7000],
  4:  ['HONDA CB 300R', 890, 757, '', '', '', '', 15000],
  5:  ['HONDA REBEL 300', 890, 757, '', '', '', '', 15000],
  6:  ['YAMAHA MT-03 300', 1090, 927, '', '', '', '', 15000],
  7:  ['KAWASAKI NINJA 400', 1185, 1007, '', '', '', '', 20000],
  10: ['KAWA VULCAN 650S', 1798, 1528, '', '', '', '', 20000],
  11: ['HONDA CBR 650R', 1798, 1528, '', '', '', '', 20000],
  12: ['HONDA CB 650R', 1798, 1528, '', '', '', '', 20000],
  13: ['YAMAHA XSR 900', 1798, 1528, '', '', '', '', 20000],
  14: ['YAMAHA R7', 2298, 1953, '', '', '', '', 25000],
  20: ['HONDA CLICK 125', 249, 187, '', '', '', '', 2000],
  21: ['HONDA PCX150', 349, 262, '', '', '', '', 3000],
  22: ['HONDA ADV 150', 449, 337, '', '', '', '', 3000],
  23: ['YAMAHA NMAX 155', 449, 337, '', '', '', '', 3000],
  24: ['HONDA PCX 160', 498, 374, '', '', '', '', 5000],
  25: ['HONDA ADV 160', 498, 374, '', '', '', '', 5000],
  26: ['HONDA FORZA 300', 690, 518, '', '', '', '', 5000],
  27: ['YAMAHA XMAX300 2020-2022', 790, 593, '', '', '', '', 5000],
  28: ['YAMAHA XMAX 300 NEW 2023-', 939, 704, '', '', '', '', 7000],
  29: ['HONDA ADV 350', 998, 749, '', '', '', '', 7000],
  30: ['HONDA XADV 750', 2788, 2091, '', '', '', '', 25000],
};
const DISCOUNTS = { B2: 0.15, B9: 0.15, B19: 0.25 };

// строки 'клиенты' A..F для теста доступности
let CLIENT_ROWS = [];

const priceTab = {
  getRange: (a, b, c, d) => {
    if (typeof a === 'string') return { getValue: () => DISCOUNTS[a] };
    return { getValues: () => [PRICE_ROWS[a]] };
  },
};
const clientsTab = {
  getLastRow: () => CLIENT_ROWS.length + 1,
  getRange: () => ({ getValues: () => CLIENT_ROWS }),
};

const sandbox = {
  CONFIG: { TABS: { PRICES_ALT: 'цены альт', CLIENTS: 'клиенты' } },
  getSheet: (key, tab) => (tab === 'цены альт' ? priceTab : clientsTab),
  resolveBikeName_: (input) => (String(input).startsWith('НЕТ') ? null : String(input)),
  console,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('/root/turbobaby-bridge-gs/QuotePrice.js', 'utf8'), sandbox);
const quote = (bike, ds, de) => sandbox.quotePrice({ bike, date_start: ds, date_end: de });

let fail = 0;
function check(name, cond, extra) {
  if (cond) { console.log('  ok –', name); }
  else { fail++; console.log('  FAIL –', name, '|', JSON.stringify(extra)); }
}

// === 1. Эталоны листа: 7 дней (08.07→15.07), сверка с J-колонкой Календаря ===
const REF = [
  ['XSR 155СС BLACK PHUKET 8949', 3303, 472, 7000],
  ['CB 300CC R 9011', 4716, 674, 15000],
  ['NINJA 400СС PHUKET 6334', 6274, 896, 20000],
  ['VULCAN 650CC S PHUKET 5065', 9519, 1360, 20000],
  ['CBR 650R PHUKET 4505', 9519, 1360, 20000],
  ['NMAX 155CC GREEN-B PHUKET 4957', 2217, 317, 3000],
  ['XMAX 300CC BLUE PHUKET 5773', 3902, 557, 5000],
  ['XMAX 300CC NEW BLACK PHUKET 8969', 4632, 662, 7000],
  ['ADV 350CC BLACK PHUKET 5849', 4928, 704, 7000],
  ['XADV 750CC BLACK BKK 3902', 13759, 1966, 25000],
];
console.log('=== эталоны Календаря, 7 дней ===');
for (const [bike, total, day, dep] of REF) {
  const r = quote(bike, '08.07.2026', '15.07.2026');
  check(bike, r.ok && r.total === total && r.day_price === day && r.deposit === dep && r.days === 7, r);
}

// === 2. Кривые: краевые точки ===
console.log('=== края кривых ===');
let r = quote('NMAX 155CC GREEN-B PHUKET 4957', '08.07.2026', '14.07.2026'); // 6 дней скутер → 5%
check('скутер 6д = 5%', r.ok && r.day_price === Math.round(337 * 0.95) && r.total === Math.round(337 * 6 * 0.95), r);
r = quote('NMAX 155CC GREEN-B PHUKET 4957', '01.07.2026', '01.09.2026');    // 62 дня → 35%
check('скутер >30д = 35%', r.ok && r.day_price === Math.round(337 * 0.65), r);
r = quote('CBR 650R PHUKET 4505', '01.07.2026', '15.08.2026');              // 45 дней мото2 → 50%
check('мото2 >30д = 50%', r.ok && r.day_price === Math.round(1528 * 0.5), r);
r = quote('CB 300CC R 9011', '08.07.2026', '13.07.2026');                   // 5 дней CB300R → 10%
check('CB300R 5д = 10%', r.ok && r.day_price === Math.round(757 * 0.9), r);
r = quote('XSR 155СС BLACK PHUKET 8949', '08.07.2026', '13.07.2026');       // 5 дней XSR155 → 0%
check('XSR155 5д = 0%', r.ok && r.day_price === 502, r);
r = quote('CB 300CC R 9011', '01.07.2026', '21.07.2026');                   // 20 дней → 25+7*1.5=35.5%
check('CB300R 20д = 35.5%', r.ok && r.day_price === Math.round(757 * (1 - 0.355)), r);

// === 3. Доступность (логика F5 Календаря) ===
console.log('=== доступность ===');
CLIENT_ROWS = [
  ['Бронь', 'OFF', 'NMAX 155CC GREEN-B PHUKET 4957', 'Иван', new Date(2026, 6, 10), new Date(2026, 6, 20)],
  ['Завершена', 'OFF', 'XMAX 300CC BLUE PHUKET 5773', 'Пётр', new Date(2026, 6, 1), new Date(2026, 6, 30)],
  ['В аренде', 'ON', 'CBR 650R PHUKET 4505', 'Олег', new Date(2026, 6, 1), new Date(2026, 6, 30)],
  ['В аренде', 'OFF', 'ADV 350CC BLACK PHUKET 5849', 'Ким', '10.07.2026', '12.07.2026 , 13:00'],
];
r = quote('NMAX 155CC GREEN-B PHUKET 4957', '08.07.2026', '15.07.2026');
check('бронь с пересечением → занят', r.ok && r.available === false && r.conflicts === 1, r);
r = quote('NMAX 155CC GREEN-B PHUKET 4957', '21.07.2026', '28.07.2026');
check('после возврата → свободен', r.ok && r.available === true, r);
r = quote('XMAX 300CC BLUE PHUKET 5773', '08.07.2026', '15.07.2026');
check('Завершена не блокирует', r.ok && r.available === true, r);
r = quote('CBR 650R PHUKET 4505', '08.07.2026', '15.07.2026');
check('В аренде + AUTO_CNCL=ON не блокирует', r.ok && r.available === true, r);
r = quote('ADV 350CC BLACK PHUKET 5849', '12.07.2026', '19.07.2026');
check('строковые даты в клиентах + граничное пересечение', r.ok && r.available === false && r.conflicts === 1, r);

// === 4. Форматы дат и ошибки ===
console.log('=== форматы/ошибки ===');
const a1 = quote('NMAX 155CC GREEN-B PHUKET 4957', '08-07-2026', '15-07-2026');
const a2 = quote('NMAX 155CC GREEN-B PHUKET 4957', '2026-07-08', '2026-07-15');
check('dd-mm-yyyy == yyyy-mm-dd', a1.ok && a2.ok && a1.total === a2.total && a1.days === 7, [a1, a2]);
r = quote('NMAX 155CC GREEN-B PHUKET 4957', '15.07.2026', '08.07.2026');
check('end < start → bad_period', !r.ok && r.error === 'bad_period', r);
r = quote('NMAX 155CC GREEN-B PHUKET 4957', 'ерунда', '15.07.2026');
check('кривые даты → bad_dates', !r.ok && r.error === 'bad_dates', r);
r = quote('НЕТ ТАКОГО', '08.07.2026', '15.07.2026');
check('байк не найден → bike_not_resolved', !r.ok && r.error === 'bike_not_resolved', r);
r = sandbox.quotePrice({ date_start: '08.07.2026', date_end: '15.07.2026' });
check('без bike → missing_bike', !r.ok && r.error === 'missing_bike', r);

// сезон
r = quote('NMAX 155CC GREEN-B PHUKET 4957', '08.07.2026', '15.07.2026');
check('season low/0.25 (скутер)', r.ok && r.season.label === 'low' && r.season.global_discount === 0.25, r.season);

console.log(fail === 0 ? '\nALL PASS' : '\nFAILED: ' + fail);
process.exit(fail === 0 ? 0 : 1);
