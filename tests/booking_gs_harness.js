'use strict';
/**
 * Харнесс O3-2a: исполняет РЕАЛЬНЫЙ /root/turbobaby-bridge-gs/Booking.js в node
 * с мок-SpreadsheetApp/Utilities (Apps Script локально не исполнить — но Booking.js
 * зовёт сервисы только внутри функций, поэтому vm-загрузка + мок листа работает).
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_booking_gs.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');

const BOOKING_JS = '/root/turbobaby-bridge-gs/Booking.js';
const NMAX = 'NMAX 155CC GREEN-B PHUKET 4957';
const CB = 'CB 300CC R 9011';

// ── мок листа поверх 2D-массива (1-indexed строки/колонки как в Apps Script) ──
function makeSheet(rows) {
  const WIDTH = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  function cellRange(row, col) {
    return {
      setValue(v) { ensureRow(row); grid[row - 1][col - 1] = v; },
      getValue() { ensureRow(row); return grid[row - 1][col - 1]; },
      copyTo(dst) { dst.setValue('=FORMULA'); }, // fill-down формулы — маркер
    };
  }
  return {
    grid,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    getRange(a, b, c, d) {
      if (typeof a === 'string') return { getValues: () => grid.map(r => [r[0]]) }; // 'A:A'
      if (c === undefined) return cellRange(a, b);
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) { ensureRow(r); out.push(grid[r - 1].slice(b - 1, b - 1 + d)); }
          return out;
        },
      };
    },
  };
}

function makeEnv(clientRows) {
  const clients = makeSheet(clientRows);
  const bikes = makeSheet([[NMAX], [CB], ['HONDA CLICK 125CC 1111']]);
  const sheets = { 'клиенты': clients, 'список мото': bikes };
  global.SpreadsheetApp = { openById: () => ({ getSheetByName: n => sheets[n] || null }) };
  global.Utilities = { getUuid: () => 'uuid-test' };
  global.Logger = { log: () => {} };
  return clients;
}

vm.runInThisContext(fs.readFileSync(BOOKING_JS, 'utf8'), { filename: BOOKING_JS });

// строка листа: [A статус, B, C байк, D имя, E начало, F конец]
const HEADER = ['СТАТУС', 'AUTO CNCL', 'Название мото', 'Имя', 'Дата начала', 'Дата завершения'];
function row(st, bike, name, ds, de) { return [st, 'OFF', bike, name, ds, de]; }

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }

// ── 1. bookingParseDate_: форматы листа/входа ──
{
  const p1 = bookingParseDate_('02.06.2026');
  check('parse.dd.mm.yyyy', p1 && p1.d.getDate() === 2 && p1.d.getMonth() === 5 && p1.d.getFullYear() === 2026 && !p1.hasTime, JSON.stringify(p1));
  const p2 = bookingParseDate_('09.06.2026 , 13:00');
  check('parse.sheet-comma-time', p2 && p2.hasTime && p2.d.getHours() === 13 && p2.d.getMinutes() === 0, JSON.stringify(p2));
  const p3 = bookingParseDate_('09.06.2026, 13:05');
  check('parse.comma-time', p3 && p3.hasTime && p3.d.getHours() === 13 && p3.d.getMinutes() === 5);
  const p4 = bookingParseDate_('03.07.2026 14:00'); // как в живых строках CRM (row698)
  check('parse.space-time', p4 && p4.hasTime && p4.d.getHours() === 14);
  const p5 = bookingParseDate_('02-06-2026'); // формат testBooking
  check('parse.dashes', p5 && p5.d.getDate() === 2 && p5.d.getMonth() === 5);
  const p6 = bookingParseDate_('2026-06-02');
  check('parse.iso', p6 && p6.d.getDate() === 2 && p6.d.getMonth() === 5 && !p6.hasTime);
  const p7 = bookingParseDate_('2026-06-02T13:30');
  check('parse.iso-time', p7 && p7.hasTime && p7.d.getHours() === 13 && p7.d.getMinutes() === 30);
  const p8 = bookingParseDate_(new Date(2026, 5, 2, 13, 0)); // Date-ячейка листа
  check('parse.date-object', p8 && p8.hasTime && p8.t === new Date(2026, 5, 2, 13, 0).getTime());
  check('parse.rollover-rejected', bookingParseDate_('32.13.2026') === null);
  check('parse.garbage-null', bookingParseDate_('скоро') === null && bookingParseDate_('') === null && bookingParseDate_(null) === null);
  check('parse.bad-time-rejected', bookingParseDate_('02.06.2026 , 25:00') === null);
  check('fmt.date', bookingFmtDate_(bookingParseDate_('2026-06-02')) === '02.06.2026');
  check('fmt.date-time', bookingFmtDate_(bookingParseDate_('2026-06-09T13:05')) === '09.06.2026 , 13:05');
  check('fmt.roundtrip-sheet', bookingFmtDate_(bookingParseDate_('09.06.2026 , 13:00')) === '09.06.2026 , 13:00');
}

// ── 2. bookingOverlap_: касание границ НЕ конфликт, открытая аренда блокирует ──
{
  const D = (s) => bookingParseDate_(s).t;
  check('overlap.inside', bookingOverlap_(D('12.07.2026'), D('14.07.2026'), D('10.07.2026'), D('15.07.2026')) === true);
  check('overlap.touch-start', bookingOverlap_(D('15.07.2026'), D('20.07.2026'), D('10.07.2026'), D('15.07.2026')) === false);
  check('overlap.touch-end', bookingOverlap_(D('05.07.2026'), D('10.07.2026'), D('10.07.2026'), D('15.07.2026')) === false);
  check('overlap.disjoint', bookingOverlap_(D('01.07.2026'), D('05.07.2026'), D('10.07.2026'), D('15.07.2026')) === false);
  check('overlap.open-ended-after', bookingOverlap_(D('10.08.2026'), D('12.08.2026'), D('01.07.2026'), null) === true);
  check('overlap.open-ended-before', bookingOverlap_(D('10.06.2026'), D('01.07.2026'), D('01.07.2026'), null) === false);
}

// ── 3. createBooking: конфликт пересечения ──
{
  makeEnv([HEADER, row('Бронь', NMAX, 'Иван', '10.07.2026', '15.07.2026 , 13:00')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '12.07.2026', date_end: '14.07.2026' });
  check('create.conflict-overlap', !r.ok && r.error === 'booking_conflict' && r.row === 2 &&
        r.conflict_name === 'Иван' && r.conflict_start === '10.07.2026' && r.conflict_end === '15.07.2026 , 13:00',
        JSON.stringify(r));
  check('create.conflict-message-detail', /4957/.test(r.message) && /Иван/.test(r.message) && /10\.07\.2026/.test(r.message), r.message);
}
{
  // ячейки как Date-объекты (реальный getValues листа отдаёт Date)
  makeEnv([HEADER, row('В аренде', NMAX, 'Гость', new Date(2026, 6, 10), new Date(2026, 6, 15, 13, 0))]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '2026-07-12', date_end: '2026-07-14' });
  check('create.conflict-date-cells', !r.ok && r.error === 'booking_conflict', JSON.stringify(r));
}
{
  // касание границ: возврат 15.07 (без времени) → выдача с 15.07 допустима
  const sh = makeEnv([HEADER, row('Бронь', NMAX, 'Иван', '10.07.2026', '15.07.2026')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '15.07.2026', date_end: '20.07.2026' });
  check('create.touch-ok', r.ok === true && sh.grid[2][0] === 'Бронь', JSON.stringify(r));
  check('create.touch-written-dates', sh.grid[2][4] === '15.07.2026' && sh.grid[2][5] === '20.07.2026');
}
{
  // другой байк — те же даты свободны
  makeEnv([HEADER, row('Бронь', NMAX, 'Иван', '10.07.2026', '15.07.2026')]);
  const r = createBooking({ bike: '9011', name: 'Пётр', date_start: '12.07.2026', date_end: '14.07.2026' });
  check('create.other-bike-ok', r.ok === true, JSON.stringify(r));
}
{
  // статус "Завершена" НЕ блокирует
  makeEnv([HEADER, row('Завершена', NMAX, 'Иван', '10.07.2026', '15.07.2026')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '12.07.2026', date_end: '14.07.2026' });
  check('create.completed-not-blocking', r.ok === true, JSON.stringify(r));
}
{
  // открытая аренда (F пуст) блокирует всё после старта
  makeEnv([HEADER, row('В аренде', NMAX, 'Иван', '01.07.2026', '')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '10.08.2026', date_end: '12.08.2026' });
  check('create.open-ended-conflict', !r.ok && r.error === 'booking_conflict' && r.conflict_end === '', JSON.stringify(r));
}

// ── 4. bad_dates ──
{
  makeEnv([HEADER]);
  const r1 = createBooking({ bike: '4957', name: 'Пётр', date_start: '14.07.2026', date_end: '12.07.2026' });
  check('create.bad-dates-reversed', !r1.ok && r1.error === 'bad_dates', JSON.stringify(r1));
  const r2 = createBooking({ bike: '4957', name: 'Пётр', date_start: '14.07.2026', date_end: '14.07.2026' });
  check('create.bad-dates-equal', !r2.ok && r2.error === 'bad_dates', JSON.stringify(r2));
  const r3 = createBooking({ bike: '4957', name: 'Пётр', date_start: '14.07.2026', date_end: '14.07.2026 , 13:00' });
  check('create.same-day-with-time-ok', r3.ok === true, JSON.stringify(r3));
}

// ── 5. нормализация: ISO на входе → формат листа в ячейках ──
{
  const sh = makeEnv([HEADER]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '2026-07-21', date_end: '2026-07-25T13:00' });
  check('create.normalize-iso', r.ok === true && sh.grid[1][4] === '21.07.2026' && sh.grid[1][5] === '25.07.2026 , 13:00',
        JSON.stringify({ r, E: sh.grid[1][4], F: sh.grid[1][5] }));
}
{
  // совместимость: нераспознанные даты пишутся как пришли, брони не рушатся
  const sh = makeEnv([HEADER, row('Бронь', NMAX, 'Иван', 'когда-то', '')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: 'скоро', date_end: 'потом' });
  check('create.unparseable-passthrough', r.ok === true && sh.grid[2][4] === 'скоро' && sh.grid[2][5] === 'потом',
        JSON.stringify(r));
}

// ── 6. дубль-чек прежний + через нормализацию ──
{
  makeEnv([HEADER, row('Бронь', NMAX, 'Пётр', '12.07.2026', '14.07.2026')]);
  const r = createBooking({ bike: '4957', name: 'Пётр', date_start: '12.07.2026', date_end: '14.07.2026' });
  check('create.duplicate-exact', !r.ok && r.error === 'duplicate' && r.row === 2, JSON.stringify(r));
  const r2 = createBooking({ bike: '4957', name: 'Пётр', date_start: '2026-07-12', date_end: '2026-07-14' });
  check('create.duplicate-iso-normalized', !r2.ok && r2.error === 'duplicate', JSON.stringify(r2));
}

// ── 7. activateBooking: уточнение по date_start ──
{
  const sh = makeEnv([
    HEADER,
    row('Бронь', NMAX, 'Пётр', '10.07.2026', '12.07.2026'),
    row('Бронь', NMAX, 'Пётр', '20.07.2026', '25.07.2026'),
  ]);
  const r = activateBooking({ bike: '4957', name: 'Пётр', date_start: '2026-07-20' }); // ISO против дд.мм в листе
  check('activate.by-date', r.ok === true && r.row === 3 && sh.grid[2][0] === 'В аренде' && sh.grid[1][0] === 'Бронь',
        JSON.stringify(r));
}
{
  const sh = makeEnv([
    HEADER,
    row('Бронь', NMAX, 'Пётр', '10.07.2026', '12.07.2026'),
    row('Бронь', NMAX, 'Пётр', '20.07.2026', '25.07.2026'),
  ]);
  const r = activateBooking({ bike: '4957', name: 'Пётр' }); // без даты — прежнее поведение: первая
  check('activate.no-date-legacy', r.ok === true && r.row === 2 && sh.grid[1][0] === 'В аренде', JSON.stringify(r));
}
{
  makeEnv([HEADER, row('Бронь', NMAX, 'Пётр', '10.07.2026', '12.07.2026')]);
  const r = activateBooking({ bike: '4957', name: 'Пётр', date_start: '11.07.2026' });
  check('activate.date-mismatch-not-found', !r.ok && r.error === 'booking_not_found', JSON.stringify(r));
}

// ── 8. closeBooking (O3-3b): закрытие аренды В аренде → Завершена ──
// индексы grid (0-based): A=0 статус, F=5 дата возврата, G=6, I=8, J=9, K=10, N=13, Q=16, W=22
{
  // штатное закрытие: A→Завершена, N=km_end, K=paid_total; F и формулы G/I/J/W целы
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][6] = '=G'; sh.grid[1][8] = '=I'; sh.grid[1][9] = '=J'; sh.grid[1][22] = '=W';
  sh.grid[1][16] = '12000 Km, 05.07.2026'; // Q текущий пробег — ЖИВОЙ формат листа (разведка CRM 23:04)
  sh.grid[1][10] = 3000;  // K было оплачено
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 12500, paid_total: 9000 });
  check('close.ok', r.ok === true && r.closed === true && r.row === 2 && sh.grid[1][0] === 'Завершена',
        JSON.stringify(r));
  check('close.km-written', sh.grid[1][13] === 12500, JSON.stringify(sh.grid[1][13]));
  check('close.paid-written', sh.grid[1][10] === 9000, JSON.stringify(sh.grid[1][10]));
  check('close.f-intact', sh.grid[1][5] === '20.07.2026', JSON.stringify(sh.grid[1][5]));
  check('close.formulas-intact', sh.grid[1][6] === '=G' && sh.grid[1][8] === '=I' &&
        sh.grid[1][9] === '=J' && sh.grid[1][22] === '=W');
}
{
  // K опционален: без paid_total ячейка K НЕ трогается (km_end с фикса row705 обязателен)
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][10] = 3000; sh.grid[1][16] = 11111;
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 12000 });
  check('close.k-optional', r.ok === true && sh.grid[1][0] === 'Завершена' &&
        sh.grid[1][10] === 3000 && sh.grid[1][13] === 12000, JSON.stringify(r));
}
{
  // фикс row705 fail-closed: km_end НЕ передан / пустой → km_required, лист не тронут
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = 12000;
  const r1 = closeBooking({ bike: '4957', name: 'Пётр' });
  const r2 = closeBooking({ bike: '4957', name: 'Пётр', km_end: '' });
  check('close.km-required', !r1.ok && r1.error === 'km_required' &&
        !r2.ok && r2.error === 'km_required' &&
        sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '', JSON.stringify({ r1, r2 }));
}
{
  // Бронь (не активирована) → not_active, лист не тронут
  const sh = makeEnv([HEADER, row('Бронь', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  const r = closeBooking({ bike: '4957', name: 'Пётр' });
  check('close.not-active', !r.ok && r.error === 'not_active' && r.row === 2 && sh.grid[1][0] === 'Бронь',
        JSON.stringify(r));
}
{
  // подходящей строки нет ("Завершена" не считается) → not_found
  makeEnv([HEADER, row('Завершена', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  const r = closeBooking({ bike: '4957', name: 'Пётр' });
  check('close.not-found', !r.ok && r.error === 'not_found', JSON.stringify(r));
}
{
  // две "В аренде" одного bike+name: без date_start → ambiguous; с date_start — закрывается верная
  const sh = makeEnv([
    HEADER,
    row('В аренде', NMAX, 'Пётр', '10.06.2026', '10.07.2026'),
    row('В аренде', NMAX, 'Пётр', '20.07.2026', '25.07.2026'),
  ]);
  sh.grid[2][16] = 30000; // Q второй аренды (km_end с фикса row705 обязателен)
  const r1 = closeBooking({ bike: '4957', name: 'Пётр' });
  check('close.ambiguous', !r1.ok && r1.error === 'ambiguous' && r1.rows.length === 2 &&
        sh.grid[1][0] === 'В аренде' && sh.grid[2][0] === 'В аренде', JSON.stringify(r1));
  const r2 = closeBooking({ bike: '4957', name: 'Пётр', date_start: '2026-07-20', km_end: 30100 }); // ISO против дд.мм листа
  check('close.by-date', r2.ok === true && r2.row === 3 && sh.grid[2][0] === 'Завершена' &&
        sh.grid[1][0] === 'В аренде', JSON.stringify(r2));
}
{
  // одометр не уменьшается: km_end < Q → odometer_back (лист не тронут); km_end == Q → ок
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = 12000;
  const r1 = closeBooking({ bike: '4957', name: 'Пётр', km_end: 11000 });
  check('close.odometer-back', !r1.ok && r1.error === 'odometer_back' && r1.odo === 12000 &&
        sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '', JSON.stringify(r1));
  const r2 = closeBooking({ bike: '4957', name: 'Пётр', km_end: 12000 });
  check('close.odometer-equal-ok', r2.ok === true && sh.grid[1][13] === 12000, JSON.stringify(r2));
}
{
  // фикс row705 fail-closed: Q нечисловой (формула упала) → odo_unverifiable, лист НЕ тронут
  // (раньше чек молчаливо пропускался и запись шла — та самая дыра)
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = '#N/A';
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 500 });
  check('close.odo-nonnumeric-unverifiable', !r.ok && r.error === 'odo_unverifiable' &&
        sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '', JSON.stringify(r));
}
{
  // фикс row705 fail-closed: Q ПУСТ → odo_unverifiable «сверь и закрой руками», лист НЕ тронут
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 35200 });
  check('close.odo-empty-unverifiable', !r.ok && r.error === 'odo_unverifiable' && r.row === 2 &&
        /руками/.test(r.message) && sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '',
        JSON.stringify(r));
}
{
  // km_end мусор → bad_km_end, лист не тронут
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 'много' });
  check('close.bad-km-end', !r.ok && r.error === 'bad_km_end' && sh.grid[1][0] === 'В аренде',
        JSON.stringify(r));
}

// ── 9. bookingParseOdo_ (фикс №2 маятника row705→1268): Q живёт строкой «<число> Km, <дата>» ──
{
  check('parseOdo.live-format', bookingParseOdo_('35200 Km, 05.07.2026') === 35200);
  check('parseOdo.lower-km', bookingParseOdo_('12345 km') === 12345);
  check('parseOdo.no-space-km', bookingParseOdo_('12345Km') === 12345);
  check('parseOdo.plain-string', bookingParseOdo_('12345') === 12345);
  check('parseOdo.number-cell', bookingParseOdo_(12345) === 12345);
  check('parseOdo.empty-null', bookingParseOdo_('') === null && bookingParseOdo_(null) === null &&
        bookingParseOdo_(undefined) === null);
  check('parseOdo.garbage-null', bookingParseOdo_('#N/A') === null && bookingParseOdo_('мусор') === null);
  check('parseOdo.bare-date-null', bookingParseOdo_('05.07.2026') === null); // голая дата ≠ пробег
  check('parseOdo.split-number-null', bookingParseOdo_('12 345 Km') === null); // недопарс «12» запрещён
  check('parseOdo.nan-null', bookingParseOdo_(NaN) === null && bookingParseOdo_(Infinity) === null);
}
{
  // живой формат Q → парс → back-гейт ЛОВИТ занижение (до фикса Q-строка давала odo_unverifiable)
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = '35200 Km, 05.07.2026';
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 35100 });
  check('close.odo-live-format-back', !r.ok && r.error === 'odometer_back' && r.odo === 35200 &&
        sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '', JSON.stringify(r));
}
{
  // живой формат Q, km_end ≥ распарсенного → закрытие ok (маятник 1268 закрыт)
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = '35200 Km, 05.07.2026';
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 35450 });
  check('close.odo-live-format-ok', r.ok === true && sh.grid[1][0] === 'Завершена' &&
        sh.grid[1][13] === 35450, JSON.stringify(r));
}
{
  // Q = голая дата без числа → odo_unverifiable (fail-closed цел), лист НЕ тронут
  const sh = makeEnv([HEADER, row('В аренде', NMAX, 'Пётр', '10.07.2026', '20.07.2026')]);
  sh.grid[1][16] = '05.07.2026';
  const r = closeBooking({ bike: '4957', name: 'Пётр', km_end: 35200 });
  check('close.odo-date-only-unverifiable', !r.ok && r.error === 'odo_unverifiable' &&
        /руками/.test(r.message) && sh.grid[1][0] === 'В аренде' && sh.grid[1][13] === '',
        JSON.stringify(r));
}

// ── итог ──
const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ total: cases.length, failed: failed.length, cases }, null, 1));
process.exit(failed.length ? 1 : 0);
