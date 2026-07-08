'use strict';
/**
 * Харнесс O3-3c часть А: исполняет РЕАЛЬНЫЙ /root/turbobaby-bridge-gs/BotData.js в node
 * с мок-SpreadsheetApp/PropertiesService (схема booking_gs_harness.js: сервисы зовутся
 * только внутри функций → vm-загрузка + мок листа работает).
 * Фокус: col N booking_id в листе транзакций — TX_HEADERS, appendRow, дострой заголовка N1
 * на живом 13-колоночном листе, обратная совместимость старых вызовов (пишут пусто),
 * регресс dedup по msg_id / computeBalance_ / voidLastTransaction.
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_botdata_gs.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');

const BOTDATA_JS = '/root/turbobaby-bridge-gs/BotData.js';

// ── мок листа поверх 2D-массива (1-indexed строки/колонки как в Apps Script) ──
function makeSheet(rows) {
  const WIDTH = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  function cellRange(row, col) {
    return {
      setValue(v) { ensureRow(row); grid[row - 1][col - 1] = v; },
      getValue() { ensureRow(row); return grid[row - 1][col - 1]; },
    };
  }
  return {
    grid,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(arr) {
      const a = arr.slice(); while (a.length < WIDTH) a.push('');
      grid.push(a);
    },
    getRange(a, b, c, d) {
      if (c === undefined) return cellRange(a, b);
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) { ensureRow(r); out.push(grid[r - 1].slice(b - 1, b - 1 + d)); }
          return out;
        },
      };
    },
    deleteRows(start, n) { grid.splice(start - 1, n); },
  };
}

// живой лист транзакций СЕГОДНЯ: шапка из 13 колонок (booking_id ещё нет) + одна старая строка
const OLD_HEADERS = [
  'recorded_at', 'msg_date', 'group', 'sender', 'amount', 'currency',
  'category', 'bike', 'deposit', 'description', 'raw', 'status', 'msg_id',
];
const txSheet = makeSheet([
  OLD_HEADERS.slice(),
  ['2026-07-01T00:00:00Z', '2026-07-01', 'Money Cashflow', '@pym', 500, 'THB',
   'rental', 'NMAX 4957', '', 'старая строка', 'старая строка', 'recorded', 'old:1:m0'],
]);
const sheets = { 'транзакции': txSheet };
global.SpreadsheetApp = { openById: () => ({ getSheetByName: n => sheets[n] || null }) };
global.PropertiesService = { getScriptProperties: () => ({ getProperty: () => 'fake-botdata-id', setProperty: () => {} }) };
global.Logger = { log: () => {} };

vm.runInThisContext(fs.readFileSync(BOTDATA_JS, 'utf8'), { filename: BOTDATA_JS });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }

// ── 1. TX_HEADERS: booking_id достроен col N (14-я, последняя) ──
check('headers.len14', BOTDATA.TX_HEADERS.length === 14, BOTDATA.TX_HEADERS.length);
check('headers.colN', BOTDATA.TX_HEADERS[13] === 'booking_id', BOTDATA.TX_HEADERS[13]);
check('headers.msgid-place', BOTDATA.TX_HEADERS[12] === 'msg_id', 'msg_id остался col M — dedup botMsgExists_(…,13,…) цел');

// ── 2. addTransaction С booking_id → col N заполнен ──
{
  const r = addTransaction({
    msg_date: '2026-07-08', group: 'Money Cashflow', sender: '@pym', amount: 4900,
    currency: 'THB', category: 'rental', bike: 'ADV 8004', deposit: 'passport',
    description: 'ADV 8004 +4900 1 passport', raw: 'ADV 8004 +4900 1 passport',
    msg_id: 'c:100:m0', booking_id: 'uuid-dep-1',
  });
  const row = txSheet.grid[txSheet.getLastRow() - 1];
  check('with-id.saved', r.ok && r.saved, JSON.stringify(r));
  check('with-id.colN', row[13] === 'uuid-dep-1', JSON.stringify(row.slice(12, 14)));
  check('with-id.msgid', row[12] === 'c:100:m0', row[12]);
}

// ── 3. дострой заголовка N1 на живом 13-колоночном листе (идемпотентно) ──
check('header-n1.built', txSheet.grid[0][13] === 'booking_id', JSON.stringify(txSheet.grid[0].slice(12, 14)));

// ── 4. addTransaction БЕЗ booking_id (старый вызов) → col N пуст, ничего не падает ──
{
  const r = addTransaction({
    msg_date: '2026-07-08', group: 'Money Cashflow', sender: '@pym', amount: -300,
    currency: 'THB', category: 'other', description: 'бензин', raw: '-300 бензин',
    msg_id: 'c:101:m0',
  });
  const row = txSheet.grid[txSheet.getLastRow() - 1];
  check('no-id.saved', r.ok && r.saved, JSON.stringify(r));
  check('no-id.colN-empty', row[13] === '', JSON.stringify(row[13]));
}

// ── 5. регресс: dedup по msg_id жив (та же col M=13) ──
{
  const before = txSheet.getLastRow();
  const r = addTransaction({ amount: 999, msg_id: 'c:100:m0', booking_id: 'uuid-XXX' });
  check('dedup.duplicate', r.ok && r.duplicate === true, JSON.stringify(r));
  check('dedup.no-new-row', txSheet.getLastRow() === before, txSheet.getLastRow() + ' vs ' + before);
}

// ── 6. регресс: computeBalance_ считает как раньше (500 + 4900 - 300) ──
{
  const bal = computeBalance_('Money Cashflow');
  check('balance.thb', bal.THB === 5100, JSON.stringify(bal));
}

// ── 7. регресс: voidLastTransaction (читает TX_HEADERS.length=14 колонок; статус col 12 на месте) ──
{
  const r = voidLastTransaction({ group: 'Money Cashflow' });
  check('void.ok', r.ok && r.voided && r.amount === -300, JSON.stringify(r));
  const bal = computeBalance_('Money Cashflow');
  check('void.balance', bal.THB === 5400, JSON.stringify(bal));
}

const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ cases, failed: failed.length }, null, 1));
process.exit(failed.length ? 1 : 0);
