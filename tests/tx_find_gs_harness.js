'use strict';
/**
 * Харнесс двери tx_find (К1 проекта AGENTASKSPL0310, 03.10.2026): исполняет РЕАЛЬНЫЙ код моста в
 * node с мок-листом транзакций — тот же способ, что у botdata_gs_harness.js / undo_door_harness.js
 * (сервисы Apps Script зовутся только внутри функций → vm-загрузка + мок работает).
 *
 * Источники кода — правило srcOf: файл есть в КАТАЛОГЕ СБОРКИ ЗАХОДА `bridge_build_tx_find/` —
 * берём сборку, иначе ЗЕРКАЛО ПРОДА `bridge_prod/`. Судимые файлы — BotData.js (txFind) и Bridge.js
 * (маршрут GET `tx_find`), Config.js (verifyToken) — из зеркала. После выкладки и сведения зеркала
 * харнесс сам начнёт судить зеркало.
 *
 * `--stdin`: подмена исходников JSON-объектом {имя файла: текст} со stdin — так тест гоняет
 * МУТАНТОВ, не создавая файлов на диске.
 *
 * Данные синтетические, в ЖИВОМ формате листа: msg_date лежит и строкой 'YYYY-MM-DD', и Date
 * (Sheets сам парсит дату), recorded_at — ISO-строка UTC (toISOString), msg_id — форма splinter
 * `<chat>:<message>:m<i>` и `<chat>:<message>:topup`.
 *
 * Печатает JSON {cases:[{name, pass, detail}], failed}; exit 1, если есть провалы.
 * Запускается из tests/test_tx_find.py.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build_tx_find');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');

function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}

const OVERRIDE = process.argv.includes('--stdin') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}

// ── мок листа поверх 2D-массива (1-indexed строки/колонки как в Apps Script) + счётчик записей ──
const WRITES = { n: 0, what: [] };
function makeSheet(rows) {
  const WIDTH = 20;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function wrote(what) { WRITES.n++; WRITES.what.push(what); }
  return {
    grid,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow() { wrote('appendRow'); },
    deleteRows() { wrote('deleteRows'); },
    getRange(a, b, c, d) {
      return {
        getValues() {
          const out = [];
          const nr = c === undefined ? 1 : c, nc = d === undefined ? 1 : d;
          for (let r = a; r < a + nr; r++) out.push((grid[r - 1] || new Array(WIDTH).fill('')).slice(b - 1, b - 1 + nc));
          return out;
        },
        getValue() { return (grid[a - 1] || [])[b - 1]; },
        setValue() { wrote('setValue'); },
        setValues() { wrote('setValues'); },
      };
    },
  };
}

const HEADERS = [
  'recorded_at', 'msg_date', 'group', 'sender', 'amount', 'currency',
  'category', 'bike', 'deposit', 'description', 'raw', 'status', 'msg_id', 'booking_id',
];
const CHAT = '-1003111222333';
// строки листа: индекс массива + 1 = номер строки (шапка — строка 1)
const ROWS = [
  HEADERS.slice(),
  /* 2 */ ['2026-09-30T05:00:00.000Z', '2026-09-30', 'Money Cashflow', '@pym', 4900, 'THB', 'rental',
           'Nmax 6908', 'passport', 'Nmax 6908 +4900 аренда', 'Nmax 6908 +4900 1 passport', 'recorded',
           CHAT + ':501:m0', 'bk-uuid-1'],
  /* 3 */ ['2026-10-02T03:00:00.000Z', new Date('2026-10-01T00:00:00+07:00'), 'Money Cashflow', '@pym', 3000,
           'THB', 'rental', 'ADV 8004', 'cash', 'ADV 8004 +3000', 'ADV 8004 +3000 deposit cash', 'recorded',
           CHAT + ':510:m0', ''],
  /* 4 */ ['2026-10-01T03:00:00.000Z', '2026-10-01', 'Money Cashflow', '@pym', 4900, 'THB', 'rental',
           'Nmax 6908', 'passport', 'Nmax 6908 +4900 (ошибка)', 'Nmax 6908 +4900 повтор', 'void',
           CHAT + ':511:m0', 'bk-uuid-1'],
  /* 5 */ ['2026-10-02T04:00:00.000Z', '2026-10-02', 'Money Cashflow', '@pym', 1000, 'THB', 'deposit',
           'Nmax 6908', 'cash', 'Nmax 6908 +1000 депозит', 'Nmax 6908 +1000 депозит, сдача 210 клиенту',
           'recorded', CHAT + ':520:m1', 'bk-uuid-1'],
  /* 6 */ ['2026-10-03T02:00:00.000Z', '2026-10-03', 'Money Cashflow', '@pym', -300, 'THB', 'other',
           'NMAX 155 GREY 6908', '', 'бензин', '-300 бензин Nmax', 'recorded', CHAT + ':530:topup', ''],
  /* 7 */ ['2026-10-03T20:30:00.000Z', '', 'Money Cashflow', '@pym', 500, 'THB', 'rental',
           'Click 160 5580', '', 'Click 5580 +500', 'Click 5580 +500', 'recorded', 'old:1:m0', ''],
  /* 8 */ ['2026-09-15T06:00:00.000Z', '2026-09-15', 'USD Wallet', '@dan', 2000, 'usd', 'rental',
           'Vario 1234', '', 'Vario 1234 +2000$', 'Vario 1234 +2000 usd', 'recorded', '12345:77:m0', 'bk-uuid-2'],
  /* 9 */ ['', '', 'Money Cashflow', '@pym', 50, 'THB', 'other', 'Nmax 6908', '', 'мелочь', 'мелочь 50',
           'recorded', CHAT + ':540:m0', ''],
];

const txSheet = makeSheet(ROWS);
let SHEETS = { 'транзакции': txSheet };
const CREATED = { n: 0 };
const PROPS = { BRIDGE_TOKEN: 'tok-test', BOT_DATA_SHEET_ID: 'fake-botdata-id' };

global.SpreadsheetApp = { openById: () => ({
  getSheetByName: n => SHEETS[n] || null,
  insertSheet: () => { CREATED.n++; return makeSheet([]); },
}) };
global.PropertiesService = { getScriptProperties: () => ({ getProperty: k => (k in PROPS ? PROPS[k] : null), setProperty: () => { WRITES.n++; } }) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = {
  formatDate(d, tz, fmt) {
    if (fmt !== 'yyyy-MM-dd') throw new Error('формат мока не поддержан: ' + fmt);
    return new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
  },
  getUuid: () => 'uuid',
};
global.ContentService = {
  MimeType: { JSON: 'application/json' },
  createTextOutput(s) { return { content: s, setMimeType() { return this; }, getContent() { return this.content; } }; },
};
global.Logger = { log: () => {} };
global.console = console;

for (const f of ['Config.js', 'BotData.js', 'Bridge.js'])
  vm.runInThisContext(srcText(f), { filename: srcOf(f) });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function safe(fn) { try { return fn(); } catch (e) { return { ok: false, error: 'THROWN', message: String(e && e.message) }; } }
const rowsOf = r => (r && r.items ? r.items.map(x => x.row) : null);
const J = x => JSON.stringify(x);

// ── 1. байк: как пишется в кассе и голым номером; сравнение ПО НОМЕРУ ──
{
  const r = safe(() => txFind({ bike: 'Nmax 6908' }));
  check('bike.ok', r.ok === true, J(r).slice(0, 300));
  check('bike.rows', J(rowsOf(r)) === J([9, 6, 5, 2]), J(rowsOf(r)));
  check('bike.plate-not-string', (r.items || []).some(x => x.bike === 'NMAX 155 GREY 6908'),
        'строка «NMAX 155 GREY 6908» найдена по номеру 6908');
  check('bike.voided-counted', r.checked && r.checked.voided === 1, J(r.checked));
  const r2 = safe(() => txFind({ bike: '6908' }));
  check('bike.bare-number', J(rowsOf(r2)) === J([9, 6, 5, 2]), J(rowsOf(r2)));
  check('bike.filter-echo', r.filter && r.filter.plate === '6908' && r.filter.bike === 'Nmax 6908', J(r.filter));
}

// ── 2. бронь: точное совпадение col N; отменённая не отдаётся ──
{
  const r = safe(() => txFind({ booking_id: 'bk-uuid-1' }));
  check('booking.rows', J(rowsOf(r)) === J([5, 2]), J(rowsOf(r)));
  check('booking.total', r.total && r.total.THB === 5900, J(r.total));
  check('booking.field', (r.items || []).every(x => x.booking_id === 'bk-uuid-1'), J((r.items || []).map(x => x.booking_id)));
  const r2 = safe(() => txFind({ booking_id: 'bk-uuid-2' }));
  check('booking.currency-upper', r2.items && r2.items[0] && r2.items[0].currency === 'USD' && r2.total.USD === 2000, J(r2.total));
}

// ── 3. отменённая (status void) не отдаётся ни по какому фильтру ──
{
  const all = [
    safe(() => txFind({ bike: 'Nmax 6908' })),
    safe(() => txFind({ booking_id: 'bk-uuid-1' })),
    safe(() => txFind({ date_from: '2026-10-01', date_to: '2026-10-01' })),
  ];
  const leaked = all.some(r => (r.items || []).some(x => x.row === 4 || String(x.status).toLowerCase() === 'void'));
  check('void.not-returned', !leaked, J(all.map(rowsOf)));
  check('void.counted-in-span', all[2].checked && all[2].checked.voided === 1 && J(rowsOf(all[2])) === J([3]), J(all[2].checked));
}

// ── 4. срок с–по: включительно, день = msg_date (Date и строка), без дня → recorded_at в поясе скрипта ──
{
  const r = safe(() => txFind({ date_from: '2026-10-01', date_to: '2026-10-03' }));
  check('span.rows', J(rowsOf(r)) === J([6, 5, 3]), J(rowsOf(r)));
  check('span.inclusive-ends', (r.items || []).some(x => x.row === 3) && (r.items || []).some(x => x.row === 6), J(rowsOf(r)));
  check('span.date-object', (r.items || []).some(x => x.row === 3 && x.date === '2026-10-01' && x.date_src === 'msg_date'),
        J((r.items || []).filter(x => x.row === 3)));
  check('span.undated', r.checked && r.checked.undated === 1, J(r.checked));
  check('span.checked-echo', r.checked && r.checked.span_from === '2026-10-01' && r.checked.span_to === '2026-10-03', J(r.checked));
  const r2 = safe(() => txFind({ date_from: '01.10.2026', date_to: '03.10.2026' }));
  check('span.ddmmyyyy', J(rowsOf(r2)) === J([6, 5, 3]), J(rowsOf(r2)));
  const r3 = safe(() => txFind({ date_from: '2026-10-04', date_to: '2026-10-04' }));
  check('span.recorded-at-tz', J(rowsOf(r3)) === J([7]) && r3.items[0].date_src === 'recorded_at' && r3.items[0].date === '2026-10-04',
        J(r3.items));
  const r4 = safe(() => txFind({ bike: '6908', date_from: '2026-10-02' }));
  check('span.with-bike', J(rowsOf(r4)) === J([6, 5]), J(rowsOf(r4)));
}

// ── 5. пометка в raw доходит дословно; описание — своё поле ──
{
  const r = safe(() => txFind({ booking_id: 'bk-uuid-1' }));
  const it = (r.items || []).find(x => x.row === 5) || {};
  check('raw.note-arrives', it.raw === 'Nmax 6908 +1000 депозит, сдача 210 клиенту', J(it.raw));
  check('raw.description-separate', it.description === 'Nmax 6908 +1000 депозит', J(it.description));
}

// ── 6. ссылка t.me/c/… из msg_id: только супергруппа -100…; topup тоже; прочее — пусто ──
{
  const byRow = {};
  for (const q of [{ bike: '6908' }, { booking_id: 'bk-uuid-2' }, { bike: '5580' }])
    for (const x of (safe(() => txFind(q)).items || [])) byRow[x.row] = x;
  check('link.m-form', byRow[2] && byRow[2].link === 'https://t.me/c/3111222333/501' && byRow[2].msg_id === CHAT + ':501:m0', J(byRow[2] && byRow[2].link));
  check('link.topup-form', byRow[6] && byRow[6].link === 'https://t.me/c/3111222333/530', J(byRow[6] && byRow[6].link));
  check('link.non-supergroup-empty', byRow[7] && byRow[7].link === '' && byRow[8] && byRow[8].link === '',
        J([byRow[7] && byRow[7].link, byRow[8] && byRow[8].link]));
}

// ── 7. пусто — с числом просмотренных и просмотренным сроком («не найдено» ≠ «не смотрели») ──
{
  const r = safe(() => txFind({ bike: '9999' }));
  check('empty.ok', r.ok === true && J(r.items) === '[]', J(r).slice(0, 200));
  check('empty.rows-scanned', r.checked && r.checked.rows_scanned === 8 && r.checked.matched === 0, J(r.checked));
  check('empty.span-is-sheet', r.checked && r.checked.span_from === '2026-09-15' && r.checked.span_to === '2026-10-04', J(r.checked));
  const r2 = safe(() => txFind({ booking_id: 'nope', date_from: '2026-01-01', date_to: '2026-01-31' }));
  check('empty.named-span', r2.ok === true && r2.items.length === 0 && r2.checked.rows_scanned === 8
        && r2.checked.rows_in_span === 0 && r2.checked.span_from === '2026-01-01' && r2.checked.span_to === '2026-01-31', J(r2.checked));
}

// ── 8. отказы фильтра — названы, не «все строки» ──
{
  check('guard.no-filter', safe(() => txFind({})).error === 'no_filter', J(safe(() => txFind({}))));
  check('guard.bad-bike', safe(() => txFind({ bike: 'Nmax' })).error === 'bad_bike', J(safe(() => txFind({ bike: 'Nmax' }))));
  check('guard.bad-date', safe(() => txFind({ date_from: '2026-13-01' })).error === 'bad_date', '');
  check('guard.bad-span', safe(() => txFind({ date_from: '2026-10-03', date_to: '2026-10-01' })).error === 'bad_span', '');
}

// ── 9. потолок числа строк: назван, считает дальше, но не отдаёт ──
{
  const r = safe(() => txFind({ bike: '6908', limit: 2 }));
  check('limit.cut', J(rowsOf(r)) === J([9, 6]) && r.checked.matched === 4 && r.checked.returned === 2 && r.checked.truncated === true, J(r.checked));
  check('limit.total-full', r.total && r.total.THB === 5650, J(r.total));
  const r2 = safe(() => txFind({ bike: '6908', limit: 100000 }));
  check('limit.max', r2.limit === 200 && r2.limit_max === 200, J([r2.limit, r2.limit_max]));
  const r3 = safe(() => txFind({ bike: '6908' }));
  check('limit.default', r3.limit === 50, J(r3.limit));
}

// ── 10. поля ответа ──
{
  const r = safe(() => txFind({ booking_id: 'bk-uuid-1' }));
  const need = ['row', 'date', 'amount', 'currency', 'category', 'bike', 'description', 'raw', 'msg_id', 'status', 'booking_id', 'link'];
  const miss = need.filter(k => !(r.items && r.items[0] && k in r.items[0]));
  check('fields.all', miss.length === 0, 'нет: ' + J(miss));
  check('fields.row-number', r.items && r.items[0] && r.items[0].row === 5 && r.items[0].amount === 1000, J(r.items && r.items[0]));
}

// ── 11. листа нет → ok:false no_tx_sheet, а не пустой список; лист НЕ создаётся ──
{
  const keep = SHEETS; SHEETS = {};
  const r = safe(() => txFind({ bike: '6908' }));
  SHEETS = keep;
  check('nosheet.error', r.ok === false && r.error === 'no_tx_sheet' && !('items' in r), J(r));
  check('nosheet.not-created', CREATED.n === 0, CREATED.n);
}

// ── 12. только чтение: ни одной записи в лист за весь прогон ──
check('readonly.no-writes', WRITES.n === 0, J(WRITES.what));

// ── 13. маршрут GET doGet → txFind: параметры доезжают, токен проверяется ──
{
  const out = safe(() => doGet({ parameter: { token: 'tok-test', action: 'tx_find', bike: 'Nmax 6908' } }));
  const body = safe(() => JSON.parse(out.getContent()));
  check('route.get-ok', body.action === 'tx_find' && body.ok === true && J(rowsOf(body)) === J([9, 6, 5, 2]), J(body).slice(0, 300));
  const out2 = safe(() => doGet({ parameter: { token: 'tok-test', action: 'tx_find', booking_id: 'bk-uuid-1',
    date_from: '2026-10-01', date_to: '2026-10-03', limit: '1' } }));
  const b2 = safe(() => JSON.parse(out2.getContent()));
  check('route.params-pass', J(rowsOf(b2)) === J([5]) && b2.limit === 1 && b2.checked && b2.checked.span_from === '2026-10-01', J(b2).slice(0, 300));
  const out3 = safe(() => doGet({ parameter: { token: 'wrong', action: 'tx_find', bike: '6908' } }));
  const b3 = safe(() => JSON.parse(out3.getContent()));
  check('route.token', b3.ok === false && b3.error === 'unauthorized', J(b3));
  const out4 = safe(() => doGet({ parameter: { token: 'tok-test', action: 'help' } }));
  const b4 = safe(() => JSON.parse(out4.getContent()));
  check('route.help-lists', Array.isArray(b4.actions) && b4.actions.indexOf('tx_find') >= 0, J(b4.actions));
}

// ══ НЕРАЗОБРАННОЕ НЕ СТАНОВИТСЯ ФАКТОМ (TXFINDFIX0310) — свой лист, прежние случаи выше не тронуты ══
// Сумма строкой и день в иной форме — рука человека или старые строки (писатель кладёт сумму
// числом, msg_date — как пришло). recorded_at 02.10 03:00Z = 10:00 по Бангкоку, тоже 02.10.
const REC2 = '2026-10-02T03:00:00.000Z';
const fx = (rec, md, amt, bike, extra) => {
  const e = extra || {};
  return [rec, md, 'Money Cashflow', '@pym', amt, e.cur || 'THB', 'rental', bike, '', bike + ' ' + amt,
          bike + ' ' + amt, e.st || 'recorded', CHAT + ':' + (e.mid || 900) + ':m0', e.bk || ''];
};
const ROWS2 = [
  HEADERS.slice(),
  /*  2 */ fx(REC2, '2026-10-01', '8,000', 'Nmax 7001', { bk: 'bk-fix', mid: 901 }),
  /*  3 */ fx(REC2, '2026-10-01', '8 000', 'Nmax 7002', { mid: 902 }),
  /*  4 */ fx(REC2, '2026-10-01', 0, 'Nmax 7003', { mid: 903 }),
  /*  5 */ fx(REC2, '2026-10-01', '', 'Nmax 7004', { mid: 904 }),
  /*  6 */ fx(REC2, '01.10.2026', 3000, 'ADV 7005', { mid: 905 }),
  /*  7 */ fx(REC2, 'вчера вечером', 1500, 'ADV 7006', { mid: 906 }),
  /*  8 */ fx(REC2, '2026-10-01', '8,5', 'Nmax 7007', { bk: 'bk-fix', mid: 907 }),
  /*  9 */ fx(REC2, '31.09.2026', 700, 'ADV 7008', { mid: 908 }),
  /* 10 */ fx(REC2, 'вчера вечером', 900, 'ADV 7009', { st: 'void', mid: 910 }),
  /* 11 */ fx(REC2, '2026-10-01', 1000, 'Nmax 7010', { bk: 'bk-fix', mid: 911 }),
  /* 12 */ fx(REC2, '2026-10-03', 500, 'Nmax 7001', { mid: 912 }),
  /* 13 */ fx(REC2, '2026-10-01', '8.000', 'Nmax 7011', { mid: 913 }),
  /* 14 */ fx(REC2, '2026-10-01', '-300', 'Nmax 7012', { mid: 914 }),
  /* 15 */ fx(REC2, '2026-10-01', '1,234,567.50', 'Nmax 7013', { mid: 915 }),
  /* 16 */ fx(REC2, '2026-10-01', '80,00', 'Nmax 7014', { mid: 916 }),
  /* 17 */ fx(REC2, '2026-10-01', '8000 THB', 'Nmax 7015', { mid: 917 }),
  /* 18 */ fx(REC2, '2026-10-01', '8\u00A0000', 'Nmax 7016', { mid: 918 }),
  /* 19 */ fx(REC2, '2026-10-01', '8000', 'Nmax 7017', { mid: 919 }),
];
const txSheet2 = makeSheet(ROWS2);
const onSheet2 = fn => { const keep = SHEETS; SHEETS = { 'транзакции': txSheet2 }; try { return safe(fn); } finally { SHEETS = keep; } };
const one = r => (r && r.items && r.items.length === 1 ? r.items[0] : {});

// ── 14. сумма: строка однозначной формы разбирается; прочее — null + исходник + флаг, не 0 ──
{
  const a = onSheet2(() => txFind({ bike: '7001', date_to: '2026-10-01' }));
  check('amount.comma-string', one(a).amount === 8000 && one(a).amount_raw === '8,000' && one(a).amount_unparsed === false
        && a.total.THB === 8000 && a.total_complete === true && a.checked.amount_unparsed === 0, J([one(a), a.total, a.total_complete]));
  const b = onSheet2(() => txFind({ bike: '7002' }));
  check('amount.space-string', one(b).amount === 8000 && one(b).amount_raw === '8 000' && b.total.THB === 8000, J([one(b), b.total]));
  const nb = onSheet2(() => txFind({ bike: '7016' }));
  check('amount.nbsp-string', one(nb).amount === 8000 && nb.total_complete === true, J(one(nb)));
  const pl = onSheet2(() => txFind({ bike: '7017' }));
  check('amount.plain-string', one(pl).amount === 8000 && one(pl).amount_unparsed === false, J(one(pl)));
  const z = onSheet2(() => txFind({ bike: '7003' }));
  check('amount.real-zero', one(z).amount === 0 && one(z).amount_unparsed === false && one(z).amount_raw === '0'
        && z.total.THB === 0 && z.total_complete === true && z.checked.amount_unparsed === 0, J([one(z), z.total]));
  const e = onSheet2(() => txFind({ bike: '7004' }));
  check('amount.empty-unparsed', one(e).amount === null && one(e).amount_raw === '' && one(e).amount_unparsed === true
        && !('THB' in e.total) && e.total_complete === false && e.checked.amount_unparsed === 1 && e.checked.complete === false,
        J([one(e), e.total, e.total_complete, e.checked]));
  const neg = onSheet2(() => txFind({ bike: '7012' }));
  check('amount.sign', one(neg).amount === -300 && neg.total.THB === -300, J(one(neg)));
  const big = onSheet2(() => txFind({ bike: '7013' }));
  check('amount.groups-fraction', one(big).amount === 1234567.5 && big.total.THB === 1234567.5, J(one(big)));
  const bad = {};
  for (const [pl2, raw] of [['7007', '8,5'], ['7011', '8.000'], ['7014', '80,00'], ['7015', '8000 THB']]) {
    const r = onSheet2(() => txFind({ bike: pl2 }));
    bad[raw] = [one(r).amount, one(r).amount_raw, one(r).amount_unparsed, r.total_complete, J(r.total)];
  }
  check('amount.ambiguous-unparsed', Object.keys(bad).every(k => bad[k][0] === null && bad[k][1] === k && bad[k][2] === true
        && bad[k][3] === false && bad[k][4] === '{}'), J(bad));
  const mix = onSheet2(() => txFind({ booking_id: 'bk-fix' }));
  check('amount.mix-total', J(rowsOf(mix)) === J([11, 8, 2]) && mix.total.THB === 9000 && mix.total_complete === false
        && mix.checked.amount_unparsed === 1 && mix.checked.matched === 3 && mix.checked.complete === false,
        J([rowsOf(mix), mix.total, mix.total_complete, mix.checked]));
  check('amount.unparsed-still-returned', (mix.items || []).some(x => x.row === 8 && x.amount === null && x.amount_raw === '8,5'),
        J(mix.items && mix.items.map(x => [x.row, x.amount, x.amount_raw])));
}

// ── 15. день: DD.MM.YYYY понимается; непустая неразобранная msg_date НЕ подменяется днём записи ──
{
  const d1 = onSheet2(() => txFind({ date_from: '2026-10-01', date_to: '2026-10-01', bike: '7005' }));
  check('date.ddmmyyyy-cell', J(rowsOf(d1)) === J([6]) && one(d1).date === '2026-10-01' && one(d1).date_src === 'msg_date'
        && one(d1).msg_date_raw === '01.10.2026' && d1.checked.complete === true, J([one(d1), d1.checked]));
  const d2 = onSheet2(() => txFind({ date_from: '2026-10-02', date_to: '2026-10-02', bike: '7005' }));
  check('date.ddmmyyyy-not-recorded-day', d2.ok === true && J(d2.items) === '[]', J(rowsOf(d2)));
  const g = onSheet2(() => txFind({ date_from: '2026-10-02', date_to: '2026-10-02' }));
  check('date.garbage-not-in-record-day', g.ok === true && !(g.items || []).some(x => x.row === 7 || x.row === 9),
        J(rowsOf(g)));
  check('date.garbage-counted', g.checked && g.checked.undated === 2 && g.checked.date_unparsed === 2 && g.checked.complete === false
        && g.total_complete === false, J([g.checked, g.total_complete]));
  const gb = onSheet2(() => txFind({ bike: '7006' }));
  check('date.garbage-no-span', one(gb).row === 7 && one(gb).date === null && one(gb).date_src === 'unparsed'
        && one(gb).msg_date_raw === 'вчера вечером' && one(gb).recorded_at === REC2
        && gb.checked.date_unparsed === 1 && gb.checked.complete === false && gb.total_complete === true && gb.total.THB === 1500,
        J([one(gb), gb.checked]));
  const cal = onSheet2(() => txFind({ bike: '7008' }));
  check('date.calendar-check', one(cal).date === null && one(cal).date_src === 'unparsed' && one(cal).msg_date_raw === '31.09.2026',
        J(one(cal)));
  const s1 = onSheet2(() => txFind({ date_from: '2026-10-01', date_to: '2026-10-01' }));
  check('date.span-day1', !(s1.items || []).some(x => x.row === 7 || x.row === 9) && (s1.items || []).some(x => x.row === 6)
        && s1.checked.undated === 2, J([rowsOf(s1), s1.checked]));
}

// ── 16. полнота: обрезка, строки без дня в сроке, только СВОИ (байк/бронь, не отменённые) ──
{
  const c = onSheet2(() => txFind({ bike: '7001' }));
  check('complete.clean', J(rowsOf(c)) === J([12, 2]) && c.checked.complete === true && c.total_complete === true
        && c.total.THB === 8500, J([c.checked, c.total]));
  const t = onSheet2(() => txFind({ bike: '7001', limit: 1 }));
  check('complete.truncated', t.checked.truncated === true && t.checked.complete === false && t.total_complete === true
        && t.total.THB === 8500, J([t.checked, t.total_complete]));
  const own = onSheet2(() => txFind({ bike: '7001', date_from: '2026-10-01', date_to: '2026-10-03' }));
  check('complete.foreign-undated-ignored', own.checked.undated === 0 && own.checked.complete === true && own.total_complete === true,
        J(own.checked));
  const v = onSheet2(() => txFind({ bike: '7009', date_from: '2026-10-02', date_to: '2026-10-02' }));
  check('complete.void-undated-ignored', v.checked.undated === 0 && v.checked.date_unparsed === 0 && v.checked.complete === true
        && J(v.items) === '[]', J(v.checked));
  const v2 = onSheet2(() => txFind({ bike: '7009' }));
  check('complete.void-still-void', J(v2.items) === '[]' && v2.checked.voided === 1 && v2.checked.date_unparsed === 0, J(v2.checked));
  const fields = onSheet2(() => txFind({ bike: '7001' }));
  const need = ['amount_raw', 'amount_unparsed', 'msg_date_raw'];
  check('complete.fields', (fields.items || []).every(x => need.every(k => k in x)) && 'total_complete' in fields
        && ['amount_unparsed', 'date_unparsed', 'complete'].every(k => k in fields.checked), J(fields.items && fields.items[0]));
}

// ── 17. маршрут GET доносит новые поля; лист по-прежнему не тронут ──
{
  const keep = SHEETS; SHEETS = { 'транзакции': txSheet2 };
  const out = safe(() => doGet({ parameter: { token: 'tok-test', action: 'tx_find', booking_id: 'bk-fix' } }));
  SHEETS = keep;
  const body = safe(() => JSON.parse(out.getContent()));
  const it8 = (body.items || []).find(x => x.row === 8) || {};
  check('fix.route-fields', body.ok === true && body.total_complete === false && body.checked && body.checked.complete === false
        && body.checked.amount_unparsed === 1 && it8.amount === null && it8.amount_raw === '8,5' && it8.amount_unparsed === true,
        J(body).slice(0, 400));
  check('fix.readonly', WRITES.n === 0, J(WRITES.what));
}

const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ cases, failed: failed.length }, null, 1));
process.exit(failed.length ? 1 : 0);
