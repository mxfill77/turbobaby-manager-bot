'use strict';
/**
 * Харнесс маршрутизатора общей сборки (BRIDGEBOTH0410, 04.10.2026): ОДИН Bridge.js из
 * `bridge_build_doors/` ведёт и в дверь кассы `tx_find`, и в двери договоров `contract_find` /
 * `contract_pdf`, а `help` называет все три. Исполняется РЕАЛЬНЫЙ код моста в node (способ
 * tx_find_gs_harness.js / contract_door_gs_harness.js).
 *
 * Источники — правило srcOf: файл есть в `bridge_build_doors/` — берём сборку, иначе зеркало
 * `bridge_prod/`. Сначала проверяется, что обе двери ЕСТЬ как функции (без этого шпион ниже
 * спрятал бы потерянный файл), затем двери подменяются шпионами — так маршрут судится сам по
 * себе, без данных листов: какой action в какую дверь привёл и с какими параметрами.
 *
 * `--stdin`: подмена исходников JSON-объектом {имя файла: текст} — так тест гоняет мутантов.
 * Печатает JSON {cases:[{name, pass, detail}], failed}; exit 1, если есть провалы.
 * Запускается из tests/test_bridge_doors.py.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build_doors');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');

function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}
const OVERRIDE = process.argv.includes('--stdin') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}

const PROPS = { BRIDGE_TOKEN: 'tok-test' };
global.PropertiesService = { getScriptProperties: () => ({ getProperty: k => (k in PROPS ? PROPS[k] : null), setProperty: () => {} }) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = { getUuid: () => 'uuid', formatDate: () => '2026-10-04' };
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
for (const f of ['Config.js', 'BotData.js', 'Bridge.js', 'ContractDoor.js']) {
  try { vm.runInThisContext(srcText(f), { filename: srcOf(f) }); } catch (e) { loadErr.push(f + ': ' + e.message); }
}
check('load.no-errors', !loadErr.length, J(loadErr));

// ── 1. обе двери есть как функции (до шпионов) ──
check('door.tx_find-defined', typeof global.txFind === 'function', typeof global.txFind);
check('door.contract_find-defined', typeof global.contractFind === 'function', typeof global.contractFind);
check('door.contract_pdf-defined', typeof global.contractPdf === 'function', typeof global.contractPdf);

// ── 2. шпионы вместо дверей: маршрут судится сам по себе ──
const CALLS = [];
const spy = name => p => { CALLS.push({ name, p }); return { ok: true, spied: name }; };
global.txFind = spy('txFind');
global.contractFind = spy('contractFind');
global.contractPdf = spy('contractPdf');

function get(params) {
  CALLS.length = 0;
  let out;
  try { out = doGet({ parameter: params }); } catch (e) { return { thrown: String(e && e.message) }; }
  try { return JSON.parse(out.getContent()); } catch (e) { return { unparsed: String(out && out.content) }; }
}

{
  const b = get({ token: 'tok-test', action: 'tx_find', bike: 'Nmax 6908', booking_id: 'bk-1',
    date_from: '2026-10-01', date_to: '2026-10-03', limit: '5' });
  check('route.tx_find', b.action === 'tx_find' && b.spied === 'txFind' && CALLS.length === 1, J(b));
  const p = (CALLS[0] || {}).p || {};
  check('route.tx_find-params', p.bike === 'Nmax 6908' && p.booking_id === 'bk-1' && p.date_from === '2026-10-01'
    && p.date_to === '2026-10-03' && p.limit === '5', J(p));
}
{
  const b = get({ token: 'tok-test', action: 'contract_find', phone: '0812345678', name: 'Ivan',
    bike: 'Nmax 6908', date_from: '2026-09-01', date_to: '2026-09-30', limit: '3' });
  check('route.contract_find', b.action === 'contract_find' && b.spied === 'contractFind' && CALLS.length === 1, J(b));
  const p = (CALLS[0] || {}).p || {};
  check('route.contract_find-params', p.phone === '0812345678' && p.name === 'Ivan' && p.bike === 'Nmax 6908'
    && p.date_from === '2026-09-01' && p.date_to === '2026-09-30' && p.limit === '3', J(p));
}
{
  const b = get({ token: 'tok-test', action: 'contract_pdf', id: 'pdfA0000000000000000000000001' });
  check('route.contract_pdf', b.action === 'contract_pdf' && b.spied === 'contractPdf' && CALLS.length === 1, J(b));
  check('route.contract_pdf-id', ((CALLS[0] || {}).p || {}).id === 'pdfA0000000000000000000000001', J(CALLS));
}
{
  const b = get({ token: 'tok-test', action: 'help' });
  const a = Array.isArray(b.actions) ? b.actions : [];
  check('help.names-all-three', ['tx_find', 'contract_find', 'contract_pdf'].every(x => a.indexOf(x) >= 0), J(a));
  check('help.keeps-prior', J(a.slice(0, 9)) === J(['ping', 'fleet', 'clients', 'anomalies', 'client_history',
    'finance', 'returns_soon', 'daily_pulse', 'get_pending']) && a.length === 12, J(a));
  check('help.no-door-called', CALLS.length === 0, J(CALLS));
}
for (const action of ['tx_find', 'contract_find', 'contract_pdf']) {
  const b = get({ token: 'wrong', action, bike: '6908', phone: '0812345678', id: 'x' });
  check('token.' + action, b.ok === false && b.error === 'unauthorized' && CALLS.length === 0, J(b));
}
{
  const b = get({ token: 'tok-test', action: 'no_such_action' });
  check('route.unknown', b.ok === false && b.error === 'unknown_action' && CALLS.length === 0, J(b));
  const g = get({ token: 'tok-test', action: 'get_pending_x' });
  check('route.unknown-near-name', g.error === 'unknown_action', J(g));
}

const failed = cases.filter(c => !c.pass).length;
process.stdout.write(JSON.stringify({ cases, failed }));
process.exit(failed ? 1 : 0);
