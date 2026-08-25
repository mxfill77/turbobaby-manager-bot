'use strict';
/**
 * Харнесс «ОТВЕТУ ВЛАДЕЛЬЦА ЕСТЬ КУДА СЕСТЬ» (ход D, 26.08.2026).
 *
 * ЧТО ПРОВЕРЯЕТСЯ — не форма тела, а СКВОЗНОЙ путь: расписка живой записи регистра →
 * `undo_last.position` (читает ключ акта) → `undo_last.act` → `undo_last.request` (ответ
 * владельца) → `bridge_client.service_undo` (тело POST перехвачено, сеть не трогается) →
 * ЖИВОЙ код двери `serviceUndo_` в node с мок-таблицами. Обе половины пути настоящие: python
 * зовётся отсюда подпроцессом (tests/undo_answer_payload.py), а не пересказывается фикстурой.
 *
 * ОТРИЦАТЕЛЬНЫЕ БЛИЗНЕЦЫ (каждый обязан ОТКАЗАТЬ, и клетка обязана остаться целой):
 *   · поддельный ключ акта → act_not_found;
 *   · ответа владельца не было → not_confirmed;
 *   · та же просьба вторым разом → отказ (отмены отмены не бывает).
 *
 * Источники кода — те же два, что у undo_door_harness.js: `bridge_build/` (сборка захода),
 * иначе `bridge_prod/` (зеркало задеплоенной версии). Правило выбора записано кодом (srcOf).
 * БАЙКИ ВЫДУМАНЫ и помечены ТЕСТ: живых номеров парка здесь нет ни одного (5960 в код не
 * попадает — заход прямо запрещал его трогать).
 *
 * Печатает JSON {cases, negatives}; exit 1 при провале. Зовётся из tests/test_guard_unlock.py.
 */
const fs = require('fs');
const os = require('os');
const vm = require('vm');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const GS_BUILD = path.join(ROOT, 'bridge_build');
const GS_MIRROR = path.join(ROOT, 'bridge_prod');

function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}

// ─────────────────────────── мок листа (живой формат) ───────────────────────────
const WIDTH = 40;
function colToNum(letters) {
  let n = 0;
  for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n;
}
function numToCol(n) {
  let s = '';
  while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); }
  return s;
}
function makeSheet(name, rows) {
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  const sheet = {
    grid,
    getName() { return name; },
    getParent() { return { getId() { return 'ТЕСТ-таблица'; } }; },
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(arr) { const a = arr.slice(); while (a.length < WIDTH) a.push(''); grid.push(a); },
    getRange(a, b, c, d) {
      if (typeof a === 'string') {
        const m = /^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$/.exec(a);
        if (!m) throw new Error('мок не понимает диапазон ' + a);
        const c1 = colToNum(m[1]), r1 = Number(m[2]), c2 = colToNum(m[3]), r2 = Number(m[4]);
        return sheet.getRange(r1, c1, r2 - r1 + 1, c2 - c1 + 1);
      }
      if (c === undefined) {
        return {
          setValue(v) { ensureRow(a); grid[a - 1][b - 1] = v; },
          getValue() { ensureRow(a); return grid[a - 1][b - 1]; },
          getA1Notation() { return numToCol(b) + a; },
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
        getA1Notation() { return numToCol(b) + a + ':' + numToCol(b + d - 1) + (a + c - 1); },
      };
    },
    deleteRow(n) { grid.splice(n - 1, 1); },
    deleteRows(start, n) { grid.splice(start - 1, n); },
    setFrozenRows() {},
  };
  return sheet;
}

const C_OIL = 9, C_GEAR = 10;                       // 1-based колонки Лист1
const LOG_HDR = ['logged_at', 'initiator', 'action', 'args', 'result', 'critical'];
const SVC_HDR = ['updated_at', 'bike', 'topic_id', 'service_type', 'current_km',
  'last_service_km', 'interval_km', 'next_km', 'status', 'pinned_msg_id', 'last_reminded_at', 'note'];

function freshFleet() {
  const head = new Array(WIDTH).fill('');
  const hdr = new Array(WIDTH).fill('');
  hdr[2] = 'Название'; hdr[8] = 'ТО Oil'; hdr[9] = 'ТО Gear'; hdr[10] = 'ABS'; hdr[11] = 'Аир фильтр';
  function bike(name, oil, gear) {
    const r = new Array(WIDTH).fill('');
    r[2] = name; r[8] = oil; r[9] = gear;
    return r;
  }
  // Выдуманный байк: таких номеров в парке нет. Числа взяты формой живого случая (было → стало).
  return makeSheet('Лист1', [head, hdr, bike('ТЕСТ-БАЙК 90808', 41357, 41357)]);
}

let fleetSheet = freshFleet();
let logSheet = makeSheet('боевой_лог', [LOG_HDR.slice()]);
let svcSheet = makeSheet('обслуживание', [SVC_HDR.slice()]);
let uuidSeq = 0;

global.SpreadsheetApp = {
  openById: () => ({
    getSheetByName: (n) => (n === 'Лист1' ? fleetSheet
      : n === 'боевой_лог' ? logSheet
        : n === 'обслуживание' ? svcSheet : null),
    getSheets: () => [], getId: () => 'ТЕСТ-id',
  }),
  flush: () => {},
};
global.PropertiesService = {
  getScriptProperties: () => ({ getProperty: () => 'ТЕСТ-botdata', setProperty: () => {} }),
};
global.Logger = { log: () => {} };
global.DriveApp = {
  getFileById: () => ({}), getFolderById: () => ({ addFile: () => {} }),
  getRootFolder: () => ({ removeFile: () => {} }),
};
global.Utilities = {
  getUuid: () => {
    uuidSeq += 1;
    const h = (0x5a2b3c4d + uuidSeq * 7919).toString(16);
    return h + '-' + h.slice(0, 4) + '-4' + h.slice(1, 4) + '-a' + h.slice(2, 5) + '-' + h + h.slice(0, 4);
  },
  formatDate: (d) => String(d),
};
global.Session = { getScriptTimeZone: () => 'UTC' };
global.CacheService = { getScriptCache: () => ({ get: () => null, put: () => {}, remove: () => {} }) };

for (const f of ['Config.js', 'BotData.js', 'ReadFleet.js', 'ServiceUndo.js'])
  vm.runInThisContext(fs.readFileSync(srcOf(f), 'utf8'), { filename: srcOf(f) });

// ─────────────────────────── утилиты ───────────────────────────
const cases = [];
let negatives = 0;
function check(name, cond, detail) {
  cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) });
}
function checkNeg(name, cond, detail) { negatives += 1; check(name, cond, detail); }
function cellOf(plate, col) {
  for (let i = 2; i < fleetSheet.grid.length; i++)
    if (plateFromName_(String(fleetSheet.grid[i][2])) === plate) return fleetSheet.grid[i][col - 1];
  return null;
}

/** ПУТЬ ОТВЕТА ВЛАДЕЛЬЦА, пройденный ЖИВЫМ python-кодом полосы (модули, а не пересказ). */
function answerPayload(receipt) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'guard_unlock_'));
  const inp = path.join(dir, 'receipt.json');
  const out = path.join(dir, 'payload.json');
  fs.writeFileSync(inp, JSON.stringify(receipt), 'utf8');
  execFileSync(path.join(ROOT, 'venv/bin/python3'),
    [path.join(__dirname, 'undo_answer_payload.py'), inp, out],
    { cwd: ROOT, encoding: 'utf8', timeout: 120000,
      env: Object.assign({}, process.env, { PRETOOL_NOPUSH: '1', ORCH_TEST_MODE: '1' }) });
  const data = JSON.parse(fs.readFileSync(out, 'utf8'));
  fs.rmSync(dir, { recursive: true, force: true });   // свой черновик во временном каталоге
  return data;
}

// ══════════ 1. ЗАПИСЬ РЕГИСТРА → ОТВЕТ ВЛАДЕЛЬЦА → ДВЕРЬ СРАБАТЫВАЕТ ══════════
{
  const w = setFleetService_({ number: '90808', kind: 'gear', km: 41667, confirmed: true, by: '@pym' });
  check('write.ok', w.ok === true, JSON.stringify(w));
  check('write.act-назван', typeof w.act === 'string' && w.act.length > 0, JSON.stringify(w.act));
  check('write.клетка-поднялась', String(cellOf('90808', C_GEAR)) === '41667', cellOf('90808', C_GEAR));

  const p = answerPayload(w);
  check('answer.позиция-построена', p.position && p.position.act === w.act,
        JSON.stringify([p.position_why, p.position && p.position.act, w.act]));
  check('answer.тел-ровно-одно', (p.yes || []).length === 1, JSON.stringify((p.yes || []).length));
  const yes = (p.yes || [])[0] || {};
  check('answer.дверь-названа', yes.action === 'service_' + 'undo', JSON.stringify(yes.action));
  check('answer.ключ-акта-доехал', yes.body && yes.body.act === w.act,
        JSON.stringify([yes.body && yes.body.act, w.act]));
  check('answer.подтверждение-владельца-в-теле', yes.body && yes.body.confirmed === true,
        JSON.stringify(yes.body && yes.body.confirmed));
  check('answer.числа-снаружи-нет', yes.body && !('km' in yes.body) && !('oil_km' in yes.body),
        JSON.stringify(Object.keys(yes.body || {})));

  // ── ОТРИЦАТЕЛЬНЫЙ БЛИЗНЕЦ: поддельный ключ акта ────────────────────────────────
  const forged = Object.assign({}, yes.body, { act: 'деадбееф000000' });
  const bad = serviceUndo_(forged);
  checkNeg('neg.поддельный-акт-отвергнут', bad.ok === false && bad.error === 'act_not_found',
           JSON.stringify(bad));
  check('neg.поддельный-акт-клетка-цела', String(cellOf('90808', C_GEAR)) === '41667',
        cellOf('90808', C_GEAR));

  // ── ОТРИЦАТЕЛЬНЫЙ БЛИЗНЕЦ: ответа владельца не было ────────────────────────────
  const noYes = ((p.no || [])[0] || {}).body || {};
  check('answer.без-да-тело-построено', noYes.act === w.act, JSON.stringify(noYes));
  check('answer.без-да-причина-названа', (p.no_refusals || []).length === 1,
        JSON.stringify(p.no_refusals));
  const nc = serviceUndo_(noYes);
  checkNeg('neg.без-подтверждения-отказ', nc.ok === false && nc.error === 'not_confirmed',
           JSON.stringify(nc));
  check('neg.без-подтверждения-клетка-цела', String(cellOf('90808', C_GEAR)) === '41667',
        cellOf('90808', C_GEAR));

  // ── БЛИЗНЕЦ «то же без порчи»: настоящий ответ владельца → дверь срабатывает ────
  const good = serviceUndo_(yes.body);
  check('door.срабатывает', good.ok === true, JSON.stringify(good));
  check('door.вернула-вытесненное', String(cellOf('90808', C_GEAR)) === '41357',
        cellOf('90808', C_GEAR));
  check('door.назвала-тот-же-акт', good.act === w.act, JSON.stringify([good.act, w.act]));
  check('door.след-отмены-растёт',
        logSheet.grid.slice(1).filter(r => String(r[2]) === 'ТО-регистр: отмена').length === 1,
        JSON.stringify(logSheet.grid.slice(1).map(r => String(r[2]))));

  // ── ОТРИЦАТЕЛЬНЫЙ БЛИЗНЕЦ: та же просьба вторым разом ──────────────────────────
  const again = serviceUndo_(yes.body);
  checkNeg('neg.повтор-отвергнут', again.ok === false, JSON.stringify(again));
  check('neg.повтор-клетка-цела', String(cellOf('90808', C_GEAR)) === '41357',
        cellOf('90808', C_GEAR));
}

console.log(JSON.stringify({ cases, negatives }));
process.exit(cases.some(c => !c.pass) ? 1 : 0);
