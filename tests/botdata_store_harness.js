'use strict';
/**
 * Харнесс BRIDGEFIX0710 (07.10.2026): Bot Data больше не создаётся сама.
 * Исполняет РЕАЛЬНЫЕ Config.js + BotData.js + Bridge.js моста в node с заглушками
 * SpreadsheetApp / PropertiesService / DriveApp / LockService / ContentService (способ
 * bridge_doors_router_harness.js). Внешних API нет, настроек прода нет: id таблицы и токен — выдуманные.
 *
 *   node botdata_store_harness.js [<каталог-исходников>] [--stdin] [--record]
 *   Каталог не назван — правило srcOf, как у соседних харнессов: файл есть в КАТАЛОГЕ СБОРКИ
 *   `bridge_build_botdata/` — берём сборку, иначе ЗЕРКАЛО ПРОДА `bridge_prod/`.
 *   --stdin: подмена исходников JSON-объектом {имя файла: текст} — так тест гоняет мутантов.
 *
 * Сценарии (каждый на чистом состоянии заглушек):
 *   H1  свойство есть, openById БРОСАЕТ (текст ошибки несёт id) → касса/очередь отвечают ok:false
 *       botdata_unavailable, причина без id; create=0, setProperty=0, insertSheet=0, appendRow=0;
 *   H2  свойства нет → ok:false no_botdata_config; create=0, setProperty=0;
 *   H3  таблица открылась, вкладки «транзакции» нет → чтения и запись кассы ok:false botdata_tab_missing,
 *       вкладка не создана; tx_find — прежний no_tx_sheet;
 *   H4  обычный путь (таблица и вкладки есть) — ответы печатаются целиком для сверки «как на @86»;
 *   H5  setupBotData(): ровно одна новая таблица, прежний id в BOT_DATA_SHEET_ID_PREV;
 *   H6  отсутствующая НЕ кассовая вкладка (боевой_лог) создаётся, как прежде, в той же таблице.
 * Печатает JSON {cases:[{name, pass, detail}], failed, normal:{…}}; exit 1 при провалах.
 * Режим --record печатает только ответы H1–H4 (для дифференциала база ↔ сборка), без проверок.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const ARG_DIR = process.argv[2] && !process.argv[2].startsWith('--') ? process.argv[2] : null;
const GS_BUILD = path.join(__dirname, '..', 'bridge_build_botdata');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');
function srcOf(name) {
  if (ARG_DIR) return path.join(ARG_DIR, name);
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}
const RECORD = process.argv.includes('--record');
const OVERRIDE = process.argv.includes('--stdin') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}

// ── время заморожено: ответы базы и сборки сравниваются побайтно ──
const RealDate = Date;
const FIXED = RealDate.parse('2026-10-07T05:00:00.000Z');
class FixedDate extends RealDate {
  constructor(...a) { if (a.length) super(...a); else super(FIXED); }
  static now() { return FIXED; }
}
global.Date = FixedDate;

const SHEET_ID = 'FAKEbotdataSHEETidXYZ0123456789';   // выдуманный id
const TOKEN = 'tok-test';
const C = {};            // счётчики обращений
let PROPS = {};
let OPEN = null;         // поведение openById: 'throw' | spreadsheet-объект
let CREATED = [];

function reset() {
  for (const k of ['openById', 'create', 'setProperty', 'deleteProperty', 'insertSheet', 'appendRow',
    'deleteSheet', 'addFile', 'removeFile', 'lock']) C[k] = 0;
  C.setPropertyKeys = [];
  PROPS = { BRIDGE_TOKEN: TOKEN };
  OPEN = null;
  CREATED = [];
}

function makeSheet(name, rows) {
  const W = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < W) a.push(''); return a; });
  function ensure(n) { while (grid.length < n) grid.push(new Array(W).fill('')); }
  const sh = {
    grid,
    getName() { return name; },
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--) if (grid[i].some(v => v !== '' && v != null)) return i + 1;
      return 0;
    },
    appendRow(arr) { C.appendRow++; const a = arr.slice(); while (a.length < W) a.push(''); grid.push(a); },
    getRange(r, c, nr, nc) {
      if (nr === undefined) {
        return {
          setValue(v) { ensure(r); grid[r - 1][c - 1] = v; },
          getValue() { ensure(r); return grid[r - 1][c - 1]; },
          setValues(vs) { ensure(r); vs[0].forEach((v, i) => { grid[r - 1][c - 1 + i] = v; }); },
          setFontWeight() { return this; },
        };
      }
      return {
        getValues() { const o = []; for (let i = r; i < r + nr; i++) { ensure(i); o.push(grid[i - 1].slice(c - 1, c - 1 + nc)); } return o; },
        setValues(vs) { vs.forEach((row, i) => { ensure(r + i); row.forEach((v, j) => { grid[r + i - 1][c + j - 1] = v; }); }); },
        setFontWeight() { return this; },
      };
    },
    setFrozenRows() {},
    deleteRows(s, n) { grid.splice(s - 1, n); },
    deleteRow(s) { grid.splice(s - 1, 1); },
  };
  return sh;
}

function makeSpreadsheet(id, tabs) {
  const sheets = Object.assign({}, tabs);
  return {
    sheets,
    getId() { return id; },
    getSheetByName(n) { return sheets[n] || null; },
    insertSheet(n) { C.insertSheet++; sheets[n] = makeSheet(n, []); return sheets[n]; },
    getSheets() { return Object.values(sheets); },
    deleteSheet(s) { C.deleteSheet++; delete sheets[s.getName()]; },
  };
}

global.PropertiesService = {
  getScriptProperties: () => ({
    getProperty: k => (k in PROPS ? PROPS[k] : null),
    setProperty: (k, v) => { C.setProperty++; C.setPropertyKeys.push(k); PROPS[k] = v; },
    deleteProperty: k => { C.deleteProperty++; delete PROPS[k]; },
  }),
};
global.SpreadsheetApp = {
  openById(id) {
    C.openById++;
    if (OPEN === 'throw') throw new Error('Unexpected error while getting the method or property openById on object SpreadsheetApp. id=' + id);
    if (OPEN && OPEN.getId() === id) return OPEN;
    throw new Error('Document ' + id + ' is missing (perhaps it was deleted, or you don\'t have read access?)');
  },
  create(title) {
    C.create++;
    const ss = makeSpreadsheet('NEWsheet' + C.create + 'idABCDEFGHIJKLMNOP', { 'Лист1': makeSheet('Лист1', []) });
    CREATED.push({ title, id: ss.getId() });
    return ss;
  },
};
global.DriveApp = {
  getFileById: () => ({}),
  getFolderById: () => ({ addFile() { C.addFile++; } }),
  getRootFolder: () => ({ removeFile() { C.removeFile++; } }),
};
global.LockService = { getScriptLock: () => ({ waitLock() { C.lock++; }, releaseLock() {} }) };
global.CacheService = { getScriptCache: () => ({ get: () => null, put() {}, remove() {} }) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = { getUuid: () => 'uuid', formatDate: (d, tz, f) => new RealDate(d).toISOString().slice(0, 10) };
global.ContentService = {
  MimeType: { JSON: 'application/json' },
  createTextOutput(s) { return { content: s, setMimeType() { return this; }, getContent() { return this.content; } }; },
};
global.Logger = { log: () => {} };
global.console = { log() {}, error() {}, warn() {} };

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
const J = x => JSON.stringify(x);

const loadErr = [];
for (const f of ['Config.js', 'BotData.js', 'Bridge.js']) {
  try { vm.runInThisContext(srcText(f), { filename: f }); } catch (e) { loadErr.push(f + ': ' + e.message); }
}
check('load.no-errors', !loadErr.length, J(loadErr));

function parse(out) {
  try { return JSON.parse(out.getContent()); } catch (e) { return { unparsed: String(out && out.content) }; }
}
function get(params) {
  try { return parse(doGet({ parameter: Object.assign({ token: TOKEN }, params) })); }
  catch (e) { return { thrown: String(e && e.message) }; }
}
function post(body) {
  try { return parse(doPost({ postData: { contents: JSON.stringify(Object.assign({ token: TOKEN }, body)) } })); }
  catch (e) { return { thrown: String(e && e.message) }; }
}

const TXH = ['recorded_at', 'msg_date', 'group', 'sender', 'amount', 'currency', 'category', 'bike', 'deposit',
  'description', 'raw', 'status', 'msg_id', 'booking_id'];
function liveSpreadsheet(withTx) {
  const tabs = {
    'очередь_оркестратора': makeSheet('очередь_оркестратора', [
      ['id', 'created', 'from', 'task_text', 'status', 'result', 'approved_by', 'updated', 'lane'],
      [7, '2026-10-06T10:00:00.000Z', 'Filipp', 'задача семь', 'new', '', '', '2026-10-06T10:00:00.000Z', 'pc'],
    ]),
    'сверка_баланса': makeSheet('сверка_баланса', [['at', 'currency', 'bot', 'pym', 'diff', 'note']]),
  };
  if (withTx) {
    tabs['транзакции'] = makeSheet('транзакции', [TXH,
      ['2026-10-07T01:00:00.000Z', '2026-10-07', 'Money Cashflow', '@pym', 500, 'THB', 'rental', 'NMAX 6908', '', 'аренда',
        'аренда', 'recorded', 'c:1:m0', ''],
      ['2026-10-07T02:00:00.000Z', '2026-10-07', 'Money Cashflow', '@pym', -120, 'THB', 'other', '', '', 'бензин',
        'бензин', 'recorded', 'c:2:m0', '']]);
  }
  return makeSpreadsheet(SHEET_ID, tabs);
}

// Набор вызовов, через который идут касса Splinter, опрос очереди, журнал (боевые маршруты моста).
function calls() {
  return {
    get_pending: get({ action: 'get_pending', status: 'new', lane: 'pc' }),
    get_balance: post({ action: 'get_balance', group: 'Money Cashflow' }),
    get_balance_all: post({ action: 'get_balance' }),
    tx_summary: post({ action: 'tx_summary', period: 'today' }),
    check_balance: post({ action: 'check_balance', currency: 'THB', pym_balance: 380, group: 'Money Cashflow' }),
    add_transaction: post({ action: 'add_transaction', group: 'Money Cashflow', amount: 50, currency: 'THB',
      category: 'other', msg_id: 'c:3:m0', msg_date: '2026-10-07', sender: '@pym', description: 'вода', raw: 'вода' }),
    void_last: post({ action: 'void_last', group: 'Money Cashflow' }),
    tx_find: get({ action: 'tx_find', bike: '6908', limit: '5' }),
    enqueue_task: post({ action: 'enqueue_task', from: 'Filipp', task_text: 'новая', lane: 'pc' }),
  };
}
const CASH = ['get_pending', 'get_balance', 'get_balance_all', 'tx_summary', 'check_balance', 'add_transaction',
  'void_last', 'enqueue_task'];

const record = {};

// ── H1: openById бросает ──
reset();
PROPS.BOT_DATA_SHEET_ID = SHEET_ID;
OPEN = 'throw';
{
  const r = calls();
  record.H1 = r;
  for (const k of CASH) {
    check('H1.' + k + '.refused-named', r[k].ok === false && r[k].error === 'botdata_unavailable', J(r[k]));
    check('H1.' + k + '.reason-without-id', typeof r[k].message === 'string' && r[k].message.length > 0
      && r[k].message.indexOf(SHEET_ID) < 0, J(r[k].message));
  }
  check('H1.tx_find.still-refused', r.tx_find.ok === false, J(r.tx_find));
  check('H1.no-create', C.create === 0, C.create);
  check('H1.no-setProperty', C.setProperty === 0, J(C.setPropertyKeys));
  check('H1.no-insertSheet', C.insertSheet === 0, C.insertSheet);
  check('H1.no-appendRow', C.appendRow === 0, C.appendRow);
  check('H1.property-untouched', PROPS.BOT_DATA_SHEET_ID === SHEET_ID && !('BOT_DATA_SHEET_ID_PREV' in PROPS), J(PROPS));
  check('H1.openById-was-called', C.openById > 0, C.openById);
}

// ── H2: свойства нет ──
reset();
{
  const r = calls();
  record.H2 = r;
  for (const k of CASH) check('H2.' + k + '.no-config', r[k].ok === false && r[k].error === 'no_botdata_config', J(r[k]));
  check('H2.tx_find.no-sheet', r.tx_find.ok === false && r.tx_find.error === 'no_tx_sheet', J(r.tx_find));
  check('H2.no-create', C.create === 0, C.create);
  check('H2.no-setProperty', C.setProperty === 0, J(C.setPropertyKeys));
  check('H2.no-openById', C.openById === 0, C.openById);
}

// ── H3: таблица открылась, вкладки «транзакции» нет ──
reset();
PROPS.BOT_DATA_SHEET_ID = SHEET_ID;
OPEN = liveSpreadsheet(false);
{
  const before = Object.keys(OPEN.sheets).sort().join(',');
  const r = {
    get_balance: post({ action: 'get_balance', group: 'Money Cashflow' }),
    get_balance_all: post({ action: 'get_balance' }),
    tx_summary: post({ action: 'tx_summary', period: 'today' }),
    check_balance: post({ action: 'check_balance', currency: 'THB', pym_balance: 380, group: 'Money Cashflow' }),
    add_transaction: post({ action: 'add_transaction', group: 'Money Cashflow', amount: 50, currency: 'THB', msg_id: 'c:3:m0' }),
    add_transaction_no_msgid: post({ action: 'add_transaction', group: 'Money Cashflow', amount: 50, currency: 'THB' }),
    void_last: post({ action: 'void_last', group: 'Money Cashflow' }),
    tx_find: get({ action: 'tx_find', bike: '6908', limit: '5' }),
    get_pending: get({ action: 'get_pending', status: 'new', lane: 'pc' }),
  };
  record.H3 = r;
  for (const k of ['get_balance', 'get_balance_all', 'tx_summary', 'check_balance', 'add_transaction',
    'add_transaction_no_msgid', 'void_last']) {
    check('H3.' + k + '.tab-missing', r[k].ok === false && r[k].error === 'botdata_tab_missing', J(r[k]));
  }
  check('H3.tx_find.no-sheet-as-before', r.tx_find.ok === false && r.tx_find.error === 'no_tx_sheet', J(r.tx_find));
  check('H3.get_pending.other-tab-works', r.get_pending.ok === true && (r.get_pending.items || []).length === 1, J(r.get_pending));
  check('H3.tx-tab-not-created', !OPEN.sheets['транзакции'] && C.insertSheet === 0, Object.keys(OPEN.sheets).join(','));
  check('H3.tabs-unchanged', Object.keys(OPEN.sheets).sort().join(',') === before, Object.keys(OPEN.sheets).join(','));
  check('H3.no-create', C.create === 0 && C.setProperty === 0, J({ create: C.create, set: C.setPropertyKeys }));
  check('H3.no-appendRow', C.appendRow === 0, C.appendRow);
}

// ── H4: обычный путь ──
reset();
PROPS.BOT_DATA_SHEET_ID = SHEET_ID;
OPEN = liveSpreadsheet(true);
{
  const r = calls();
  record.H4 = r;
  check('H4.get_balance.ok', r.get_balance.ok === true && r.get_balance.balance && r.get_balance.balance.THB === 380, J(r.get_balance));
  check('H4.add_transaction.saved', r.add_transaction.ok === true && r.add_transaction.saved === true, J(r.add_transaction));
  check('H4.void_last.ok', r.void_last.ok === true && r.void_last.voided === true, J(r.void_last));
  check('H4.get_pending.ok', r.get_pending.ok === true && (r.get_pending.items || []).length === 1, J(r.get_pending));
  check('H4.tx_find.ok', r.tx_find.ok === true, J(r.tx_find));
  check('H4.no-create', C.create === 0 && C.setProperty === 0, J({ create: C.create, set: C.setPropertyKeys }));
}

if (!RECORD) {
  // ── H5: setupBotData ──
  reset();
  PROPS.BOT_DATA_SHEET_ID = SHEET_ID;
  {
    const has = typeof global.setupBotData === 'function';
    check('H5.setupBotData-defined', has, typeof global.setupBotData);
    let res = null;
    if (has) { try { res = setupBotData(); } catch (e) { res = { thrown: String(e.message) }; } }
    check('H5.one-new-table', C.create === 1 && CREATED.length === 1 && CREATED[0].title === 'TurboBaby Bot Data', J(CREATED));
    check('H5.prev-saved', PROPS.BOT_DATA_SHEET_ID_PREV === SHEET_ID, J(PROPS));
    check('H5.id-switched-to-new', CREATED.length === 1 && PROPS.BOT_DATA_SHEET_ID === CREATED[0].id, J(PROPS));
    check('H5.only-two-props', J(C.setPropertyKeys.slice().sort()) === J(['BOT_DATA_SHEET_ID', 'BOT_DATA_SHEET_ID_PREV']), J(C.setPropertyKeys));
    check('H5.under-lock', C.lock === 1, C.lock);
    check('H5.reply-without-full-id', res && res.ok === true && J(res).indexOf(CREATED.length ? CREATED[0].id : '?') < 0, J(res));
    reset();
    if (has) { try { setupBotData(); } catch (e) {} }
    check('H5.no-prev-when-none', !('BOT_DATA_SHEET_ID_PREV' in PROPS) && C.create === 1
      && J(C.setPropertyKeys) === J(['BOT_DATA_SHEET_ID']), J(C.setPropertyKeys));
  }

  // ── H6: не кассовая вкладка досоздаётся, как прежде (та же таблица, свойство не тронуто) ──
  reset();
  PROPS.BOT_DATA_SHEET_ID = SHEET_ID;
  OPEN = liveSpreadsheet(true);
  {
    const r = post({ action: 'log_write', initiator: 'test', act: 'x', args: '', result: 'ok' });
    check('H6.writelog-created-in-same-table', r.ok === true && !!OPEN.sheets['боевой_лог'] && C.insertSheet === 1, J(r));
    check('H6.no-create-no-setProperty', C.create === 0 && C.setProperty === 0, J({ create: C.create, set: C.setPropertyKeys }));
  }
}

const failed = cases.filter(c => !c.pass);
if (RECORD) {
  console.log = (...a) => process.stdout.write(a.join(' ') + '\n');
  process.stdout.write(JSON.stringify({ load: loadErr, record }) + '\n');
  process.exit(0);
}
process.stdout.write(JSON.stringify({ cases, failed: failed.length }, null, 1) + '\n');
process.exit(failed.length ? 1 : 0);
