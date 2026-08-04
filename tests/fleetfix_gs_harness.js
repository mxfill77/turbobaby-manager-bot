'use strict';
/**
 * Харнесс «понижение пробега по подтверждённому числу»: исполняет РЕАЛЬНЫЕ
 * /root/turbobaby-bridge-gs/{Config,BotData,ReadFleet}.js в node с мок-SpreadsheetApp
 * (схема botdata_gs_harness.js). BotData.js грузится ради НАСТОЯЩЕГО logWrite_ — аудит-след
 * проверяется на живом коде журнала, а не на заглушке.
 *
 * Фокус — ветка «исправление ошибки» у записи ТО масла (кол.I Лист1 Байки):
 *   1. ОБЫЧНЫЙ путь не ослаблен: понижение без причины и автора по-прежнему oil_decreasing;
 *   2. с ЯВНОЙ причиной и автором понижение проходит и оставляет след;
 *   3. правило владельца «понижение больше 500 км — Пым или владелец» сохранено;
 *   4. АУДИТ-СЛЕД обязателен: журнал упал → запись ОТКАЧЕНА (в живой таблице не остаётся
 *      исправления без следа);
 *   5. рост пробега, not_found, ambiguous, not_confirmed, verify — как были.
 *
 * ЖИВОЙ ФОРМАТ кол.I снят с setFleetOil_ (Number(raw), пусто → 0) и с разведки парка:
 * ячейка держит ЧИСЛО (37000), пустая ячейка = «ТО не заводили».
 *
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_record_fix.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');

const GS = '/root/turbobaby-bridge-gs/';

function makeSheet(rows) {
  const WIDTH = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  return {
    grid,
    getName() { return 'Лист1'; },
    getParent() { return { getId() { return 'fake-fleet-id'; } }; },
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(arr) { const a = arr.slice(); while (a.length < WIDTH) a.push(''); grid.push(a); },
    getRange(a, b, c, d) {
      if (c === undefined) {
        return {
          setValue(v) { ensureRow(a); grid[a - 1][b - 1] = v; },
          getValue() { ensureRow(a); return grid[a - 1][b - 1]; },
          getA1Notation() { return String.fromCharCode(64 + b) + a; },
        };
      }
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) { ensureRow(r); out.push(grid[r - 1].slice(b - 1, b - 1 + d)); }
          return out;
        },
        setValues(vals) {
          for (let r = 0; r < c; r++) { ensureRow(a + r); for (let k = 0; k < d; k++) grid[a + r - 1][b + k - 1] = vals[r][k]; }
        },
        setFontWeight() { return this; },
        getA1Notation() { return String.fromCharCode(64 + b) + a + ':' + String.fromCharCode(64 + b + d - 1) + (a + c - 1); },
      };
    },
    deleteRow(n) { grid.splice(n - 1, 1); },
    deleteRows(start, n) { grid.splice(start - 1, n); },
    setFrozenRows() {},
  };
}

// Лист1 «Байки»: строка 1 дашборд, строка 2 шапка, данные с 3-й.
// Живой случай: NMAX 4957 держит в кол.I 37000, а подтверждено 36982.
const I = 8;   // 0-based индекс колонки I внутри строки
function freshFleet() {
  const head = new Array(30).fill('');
  const hdr = new Array(30).fill('');
  hdr[2] = 'Название';
  hdr[8] = 'ТО Oil';
  function bike(name, oil) {
    const r = new Array(30).fill('');
    r[2] = name; r[8] = oil;
    return r;
  }
  return makeSheet([
    head, hdr,
    bike('NMAX 155CC GREEN-B PHUKET 4957', 37000),
    bike('ADV 160 8004', 12000),
    bike('CLICK 125 5580', ''),           // ТО не заводили — пусто
    bike('NINJA 400 6334', 20000),
    bike('DUPLICATE 7777', 100),
    bike('DUPLICATE 7777', 200),          // два байка с одним номером → ambiguous
  ]);
}

let fleetSheet = freshFleet();
let logSheet = makeSheet([['ts', 'initiator', 'action', 'args', 'result', 'critical']]);
let logBroken = false;

global.SpreadsheetApp = {
  openById: (id) => ({
    getSheetByName: (n) => {
      if (n === 'Лист1') return fleetSheet;
      if (n === 'боевой_лог') { if (logBroken) throw new Error('журнал недоступен'); return logSheet; }
      return null;
    },
    getSheets: () => [], getId: () => String(id),
  }),
  flush: () => {},
};
global.PropertiesService = { getScriptProperties: () => ({ getProperty: () => 'fake-botdata-id', setProperty: () => {} }) };
global.Logger = { log: () => {} };
global.DriveApp = { getFileById: () => ({}), getFolderById: () => ({ addFile: () => {} }), getRootFolder: () => ({ removeFile: () => {} }) };

for (const f of ['Config.js', 'BotData.js', 'ReadFleet.js'])
  vm.runInThisContext(fs.readFileSync(GS + f, 'utf8'), { filename: GS + f });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function reset() {
  fleetSheet = freshFleet();
  logSheet = makeSheet([['ts', 'initiator', 'action', 'args', 'result', 'critical']]);
  logBroken = false;
}
function oilOf(plate) {
  for (let i = 2; i < fleetSheet.grid.length; i++)
    if (plateFromName_(String(fleetSheet.grid[i][2])) === plate) return fleetSheet.grid[i][I];
  return null;
}
function auditRows() { return logSheet.grid.slice(1).filter(r => String(r[2]).indexOf('set_fleet_oil') >= 0); }

// ── 1. ОБЫЧНЫЙ ПУТЬ НЕ ОСЛАБЛЕН: понижение без причины/автора — прежний отказ ──
{
  reset();
  const r = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true });
  check('normal.blocked', r.ok === false && r.error === 'oil_decreasing', JSON.stringify(r));
  check('normal.old_oil-echo', String(r.old_oil) === '37000', JSON.stringify(r));
  check('normal.cell-intact', String(oilOf('4957')) === '37000', oilOf('4957'));
  check('normal.no-audit', auditRows().length === 0, JSON.stringify(auditRows()));

  // причина БЕЗ автора и автор БЕЗ причины — тоже обычный путь (полумера не открывает ветку)
  const r2 = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true, fix_reason: 'ошибка OCR' });
  check('normal.reason-only-blocked', r2.ok === false && r2.error === 'oil_decreasing', JSON.stringify(r2));
  const r3 = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true, fixed_by: '@filipp' });
  check('normal.author-only-blocked', r3.ok === false && r3.error === 'oil_decreasing', JSON.stringify(r3));
  check('normal.half-cell-intact', String(oilOf('4957')) === '37000', oilOf('4957'));
}

// ── 2. ЖИВОЙ СЛУЧАЙ: понижение 37000 → 36982 с названной причиной и автором ──
{
  reset();
  const r = setFleetOil_({
    number: '4957', oil_km: 36982, confirmed: true,
    fix_reason: 'ошибка распознавания одометра 29.07, механик отклонил',
    fixed_by: '@filipp',
  });
  check('fix.ok', r.ok === true, JSON.stringify(r));
  check('fix.cell', String(oilOf('4957')) === '36982', oilOf('4957'));
  check('fix.old_oil-echo', String(r.old_oil) === '37000', JSON.stringify(r));
  check('fix.drop-echo', String(r.correction && r.correction.drop) === '18', JSON.stringify(r.correction));
  check('fix.by-echo', r.correction && r.correction.by === '@filipp', JSON.stringify(r.correction));
  check('fix.rollback-given', String(r.rollback_oil) === '37000', JSON.stringify(r.rollback_oil));
  check('fix.verified', r.verified === true, JSON.stringify(r));
  // соседи целы
  check('fix.neighbours', String(oilOf('8004')) === '12000' && String(oilOf('6334')) === '20000',
        oilOf('8004') + '/' + oilOf('6334'));
}

// ── 3. АУДИТ-СЛЕД: кто, что было, что стало, причина ──
{
  reset();
  const r = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true,
                           fix_reason: 'ошибка OCR', fixed_by: '@filipp' });
  const rows = auditRows();
  check('audit.one-row', rows.length === 1, JSON.stringify(rows));
  const args = rows.length ? String(rows[0][3]) : '';
  check('audit.from-to', args.indexOf('37000') >= 0 && args.indexOf('36982') >= 0, args);
  check('audit.reason', args.indexOf('ошибка OCR') >= 0, args);
  check('audit.initiator', rows.length && String(rows[0][1]) === '@filipp', rows.length ? rows[0][1] : '');
  check('audit.critical-mark', rows.length && String(rows[0][5]).length > 0, rows.length ? rows[0][5] : '');
  check('audit.flag-echo', r.audit_logged === true, JSON.stringify(r.audit_logged));
}

// ── 4. АУДИТ ОБЯЗАТЕЛЕН: журнал недоступен → запись ОТКАЧЕНА, исправления без следа нет ──
{
  reset();
  logBroken = true;
  const r = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true,
                           fix_reason: 'ошибка OCR', fixed_by: '@filipp' });
  check('auditfail.refused', r.ok === false && r.error === 'audit_failed', JSON.stringify(r));
  check('auditfail.rolled-back', String(oilOf('4957')) === '37000', oilOf('4957'));
  check('auditfail.rollback-flag', r.rolled_back === true, JSON.stringify(r));
}

// ── 5. ПРАВИЛО ВЛАДЕЛЬЦА: понижение больше 500 км требует Пыма/владельца ──
{
  reset();
  const big = setFleetOil_({ number: '4957', oil_km: 30000, confirmed: true,
                             fix_reason: 'вписали чужой пробег', fixed_by: '@earth' });
  check('drop500.blocked', big.ok === false && big.error === 'oil_drop_needs_trusted', JSON.stringify(big));
  check('drop500.drop-echo', String(big.drop) === '7000', JSON.stringify(big));
  check('drop500.threshold-echo', String(big.threshold) === '500', JSON.stringify(big));
  check('drop500.cell-intact', String(oilOf('4957')) === '37000', oilOf('4957'));
  check('drop500.no-audit', auditRows().length === 0, JSON.stringify(auditRows()));

  const ok = setFleetOil_({ number: '4957', oil_km: 30000, confirmed: true,
                            fix_reason: 'вписали чужой пробег', fixed_by: '@Pleummmm', trusted: true });
  check('drop500.trusted-passes', ok.ok === true, JSON.stringify(ok));
  check('drop500.trusted-cell', String(oilOf('4957')) === '30000', oilOf('4957'));
  check('drop500.trusted-in-audit', auditRows().length === 1
        && String(auditRows()[0][3]).indexOf('trusted') >= 0, JSON.stringify(auditRows()));

  // ровно на границе 500 — мягкий путь, доверенный не нужен
  reset();
  const edge = setFleetOil_({ number: '4957', oil_km: 36500, confirmed: true,
                              fix_reason: 'поправка', fixed_by: '@earth' });
  check('drop500.edge-passes', edge.ok === true && String(edge.correction.drop) === '500', JSON.stringify(edge));
  reset();
  const over = setFleetOil_({ number: '4957', oil_km: 36499, confirmed: true,
                              fix_reason: 'поправка', fixed_by: '@earth' });
  check('drop500.edge+1-blocked', over.ok === false && over.error === 'oil_drop_needs_trusted', JSON.stringify(over));
}

// ── 6. ОТКАТ ТОЙ ЖЕ ВЕТКОЙ: вернуть прежнее число можно, руками в таблицу лезть не нужно ──
{
  reset();
  const fix = setFleetOil_({ number: '4957', oil_km: 36982, confirmed: true,
                             fix_reason: 'ошибка OCR', fixed_by: '@filipp' });
  const back = setFleetOil_({ number: '4957', oil_km: fix.rollback_oil, confirmed: true,
                              fix_reason: 'откат правки', fixed_by: '@filipp' });
  check('rollback.ok', back.ok === true, JSON.stringify(back));
  check('rollback.cell', String(oilOf('4957')) === '37000', oilOf('4957'));
  check('rollback.audit', auditRows().length === 2, JSON.stringify(auditRows().length));
}

// ── 7. РЕГРЕСС прежнего поведения (ветку исправления не задевает) ──
{
  reset();
  const up = setFleetOil_({ number: '4957', oil_km: 40000, confirmed: true });
  check('regress.grow-ok', up.ok === true && String(oilOf('4957')) === '40000', JSON.stringify(up));
  check('regress.grow-no-audit', auditRows().length === 0, 'рост — обычная запись, отдельного следа не заводим');

  reset();
  const nc = setFleetOil_({ number: '4957', oil_km: 40000 });
  check('regress.not_confirmed', nc.ok === false && nc.error === 'not_confirmed', JSON.stringify(nc));
  const nf = setFleetOil_({ number: '9999', oil_km: 40000, confirmed: true });
  check('regress.not_found', nf.ok === false && nf.error === 'not_found', JSON.stringify(nf));
  const amb = setFleetOil_({ number: '7777', oil_km: 40000, confirmed: true });
  check('regress.ambiguous', amb.ok === false && amb.error === 'ambiguous', JSON.stringify(amb));
  const bad = setFleetOil_({ number: '4957', oil_km: 0, confirmed: true });
  check('regress.bad_oil_km', bad.ok === false && bad.error === 'bad_oil_km', JSON.stringify(bad));
  const nn = setFleetOil_({ oil_km: 100, confirmed: true });
  check('regress.missing_number', nn.ok === false && nn.error === 'missing_number', JSON.stringify(nn));
  // пустая кол.I (ТО не заводили) — старое значение 0, понижения нет
  reset();
  const empty = setFleetOil_({ number: '5580', oil_km: 15000, confirmed: true });
  check('regress.empty-cell', empty.ok === true && String(oilOf('5580')) === '15000', JSON.stringify(empty));
  // ветка исправления НЕ отменяет confirmed
  const ncFix = setFleetOil_({ number: '4957', oil_km: 100, fix_reason: 'r', fixed_by: 'b' });
  check('regress.fix-needs-confirmed', ncFix.ok === false && ncFix.error === 'not_confirmed', JSON.stringify(ncFix));
}

console.log(JSON.stringify({ cases }));
process.exit(cases.some(c => !c.pass) ? 1 : 0);
