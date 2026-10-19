'use strict';
/**
 * Харнесс CLOSEACCRUAL1910 (19.10.2026): исполняет РЕАЛЬНЫЕ Booking.js и Closing.js моста в node с мок-листами —
 * тот же способ, что booking_gs_harness.js / tx_find_gs_harness.js (сервисы Apps Script зовутся только внутри
 * функций → vm-загрузка + мок работает).
 *
 * Источники кода — правило srcOf: файл есть в КАТАЛОГЕ СБОРКИ `bridge_build_close_accrual/` — берём сборку, иначе
 * ЗЕРКАЛО ПРОДА `bridge_prod/`. После выкладки и сведения зеркала харнесс сам начнёт судить зеркало.
 *
 * Мок ячейки держит ЗНАЧЕНИЕ, ФОРМУЛУ и ПРИМЕЧАНИЕ раздельно (как Sheets: setValue A не трогает примечание A) и
 * умеет сбой по номеру вызова (setNote / setFormula / setValue) и крюк после записи примечания (правка листа
 * «человеком» между записями). Замок — мок LockService: занятость задаётся, взятия и снятия считаются.
 *
 * `--mutant`: исходники подменяются JSON-объектом {имя файла: текст} со stdin, затем идёт весь набор (мутанты).
 * `--stdin`: один заход по JSON со stdin — {mode:'opid', vectors:[…]} → id операции; {mode:'call', crm, closing,
 * call:'closing_upsert'|'closing_get'|'close_booking', body} → {res, crm, closing} (состояние листов туда и обратно). Так
 * tests/test_close_accrual_1910.py гоняет НАСТОЯЩИЙ мост на НАСТОЯЩИХ полях Splinter, не создавая файлов.
 *
 * Печатает JSON {total, failed, cases:[{name, pass, detail}]}; exit 1, если есть провалы. Данные синтетические.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const crypto = require('crypto');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build_close_accrual');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');
function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}

const CB = 'CB 300CC R 9011';
const NMAX = 'NMAX 155CC GREEN-B PHUKET 4957';
// заголовки листа «закрытие» — дословно BOTDATA.CLOSING_HEADERS зеркала (сверка — кейс closing.headers-mirror)
const CLOSING_HEADERS = ['booking_id', 'bike', 'name', 'date_return', 'fuel_level', 'surcharge_days',
  'surcharge_fuel', 'damage', 'other', 'total_due', 'deposit_action', 'status', 'note', 'updated_at'];

// ── мок листа: значения / формулы / примечания раздельно, сбои по номеру вызова ──
function makeSheet(rows, opt) {
  opt = opt || {};
  const WIDTH = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  const formulas = Object.assign({}, opt.formulas || {});   // 'r,c' → '=…'
  const fvals = Object.assign({}, opt.fvals || {});         // 'r,c' → вычисленное значение формулы
  const notes = Object.assign({}, opt.notes || {});         // 'r,c' → текст примечания
  const fault = opt.fault || {};
  const n = { setNote: 0, setFormula: 0, setValue: 0, setValues: 0, appendRow: 0 };
  const writes = [];
  function ensureRow(r) { while (grid.length < r) grid.push(new Array(WIDTH).fill('')); }
  function bump(op) {
    n[op]++;
    if ((fault[op] || []).indexOf(n[op]) >= 0) throw new Error('mock ' + op + ' #' + n[op] + ' fail');
  }
  const api = {
    grid, formulas, fvals, notes, n, writes,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(row) { bump('appendRow'); const a = row.slice(); while (a.length < WIDTH) a.push(''); grid.push(a); writes.push(['appendRow']); },
    getRange(a, b, c, d) {
      if (typeof a === 'string') return { getValues: () => grid.map(r => [r[0]]) };
      if (c === undefined) return cell(a, b);
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) {
            ensureRow(r);
            const line = [];
            for (let k = b; k < b + d; k++) {
              const key = r + ',' + k;
              line.push(formulas[key] !== undefined ? (fvals[key] !== undefined ? fvals[key] : 0) : grid[r - 1][k - 1]);
            }
            out.push(line);
          }
          return out;
        },
        setValues(vals) {
          bump('setValues');
          for (let i = 0; i < vals.length; i++) { ensureRow(a + i); for (let j = 0; j < vals[i].length; j++) grid[a + i - 1][b + j - 1] = vals[i][j]; }
          writes.push(['setValues', a]);
        },
      };
    },
  };
  function cell(r, c) {
    const key = r + ',' + c;
    return {
      setValue(v) { bump('setValue'); ensureRow(r); grid[r - 1][c - 1] = v; delete formulas[key]; writes.push(['setValue', r, c, v]); },
      getValue() { ensureRow(r); return formulas[key] !== undefined ? (fvals[key] !== undefined ? fvals[key] : 0) : grid[r - 1][c - 1]; },
      getFormula() { return formulas[key] || ''; },
      setFormula(f) {
        bump('setFormula'); ensureRow(r);
        formulas[key] = opt.normalizeFormula ? opt.normalizeFormula(f) : f;
        fvals[key] = '#mock-eval'; grid[r - 1][c - 1] = ''; writes.push(['setFormula', r, c, f]);
      },
      getNote() { return notes[key] || ''; },
      setNote(t) {
        bump('setNote'); notes[key] = t; writes.push(['setNote', r, c]);
        if (opt.afterSetNote) opt.afterSetNote(n.setNote, api);
      },
      copyTo(dst) { dst.setValue('=FORMULA'); },
    };
  }
  return api;
}

const LOCK = { busy: false, tries: 0, released: 0, lastMs: null };
const CUR = { closing: null, closingFail: false };   // лист закрытия текущего окружения (body() кладёт туда строку)
function makeEnv(crmRows, crmOpt, closingRows) {
  LOCK.busy = false; LOCK.tries = 0; LOCK.released = 0; LOCK.lastMs = null;
  const clients = makeSheet(crmRows, crmOpt);
  const bikes = makeSheet([[NMAX], [CB], ['HONDA CLICK 125CC 1111']]);
  const closing = makeSheet(closingRows || [CLOSING_HEADERS.slice()]);
  CUR.closing = closing; CUR.closingFail = false;
  const sheets = { 'клиенты': clients, 'список мото': bikes };
  global.SpreadsheetApp = { openById: () => ({ getSheetByName: nm => sheets[nm] || null }) };
  global.getBotTab_ = () => { if (CUR.closingFail) throw new Error('mock Bot Data unavailable'); return closing; };
  global.BOTDATA = { TABS: { CLOSING: 'закрытие' }, CLOSING_HEADERS: CLOSING_HEADERS };
  global.Logger = { log: () => {} };
  global.LockService = {
    getScriptLock: () => ({
      tryLock(ms) { LOCK.tries++; LOCK.lastMs = ms; return !LOCK.busy; },
      releaseLock() { LOCK.released++; },
    }),
  };
  return { clients, closing };
}

global.Utilities = {
  getUuid: () => 'uuid-test',
  DigestAlgorithm: { SHA_256: 'SHA_256' },
  Charset: { UTF_8: 'UTF_8' },
  computeDigest(alg, s, cs) {             // как Apps Script: массив ЗНАКОВЫХ байт
    if (alg !== 'SHA_256' || cs !== 'UTF_8') throw new Error('mock computeDigest: ' + alg + '/' + cs);
    return Array.from(crypto.createHash('sha256').update(String(s), 'utf8').digest()).map(b => (b > 127 ? b - 256 : b));
  },
};

// `--mutant`: подмена исходников JSON-объектом {имя файла: текст} со stdin — так тест гоняет МУТАНТОВ без файлов
const OVERRIDE = process.argv.includes('--mutant') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}
vm.runInThisContext(srcText('Booking.js'), { filename: srcOf('Booking.js') });
vm.runInThisContext(srcText('Closing.js'), { filename: srcOf('Closing.js') });

// ── строки CRM: A статус, C байк, D имя, E начало, F конец, K оплачено(10), N пробег(13), Q одометр(16), Y id(24) ──
const HEADER = ['СТАТУС', 'AUTO CNCL', 'Название мото', 'Имя', 'Дата начала', 'Дата завершения'];
function crm(o) {
  const r = [o.st || 'В аренде', 'OFF', o.bike || CB, o.name || 'Пётр', o.ds || '10.07.2026', o.de || '20.07.2026'];
  while (r.length < 25) r.push('');
  r[10] = o.k === undefined ? 10000 : o.k;
  r[16] = o.q === undefined ? '12000 Km, 05.07.2026' : o.q;
  r[24] = o.bid === undefined ? 'bk-acc-1' : o.bid;
  return r;
}
const DAY = '2026-07-10';
const BID = 'bk-acc-1';
const CROW = 7;
const PREV_NOTE = 'выдал Пётр, шлем 1';

function acc(parts, over) {
  const pp = Object.assign({ surcharge_days: '', surcharge_fuel: '', damage: '', other: '' }, parts || {});
  const o = Object.assign({ bid: BID, brow: 2, bike: '9011', day: DAY, crow: CROW }, over || {});
  const lits = CLOSE_ACCRUAL.PARTS.map(k => closeAccrualLit_(pp[k]));
  const id = o.op || closeAccrualOpId_(o.bid, o.brow, o.bike, o.day, o.crow, lits.map(x => (x === null ? '' : x)));
  return { v: 2, close_op_id: id, booking_id: o.bid, booking_row: o.brow, date_start_day: o.day, closing_row: o.crow,
           parts: pp };
}
// Строка листа закрытия операции: booking_id и те же части в строке closing_row — лист «как при рождении карточки».
// body() кладёт её в лист текущего окружения; кейсы ВЕРСИИ правят лист ПОСЛЕ body() (раздел 9).
function closingLine(bid, pp, total) {
  const r = [bid, CB, 'Пётр', '20.07.2026', '', pp.surcharge_days, pp.surcharge_fuel, pp.damage, pp.other,
             total === undefined ? 0 : total, '', 'open', '', new Date(Date.UTC(2026, 6, 20, 10, 0, 0))];
  while (r.length < 30) r.push('');
  return r;
}
function seedClosing(a) {
  if (!a || typeof a !== 'object' || !a.parts || typeof a.parts !== 'object' || !CUR.closing) return;
  const crow = Number(a.closing_row);
  if (!(crow >= 2 && crow < 100)) return;
  const g = CUR.closing.grid;
  while (g.length < crow) g.push(new Array(30).fill(''));
  g[crow - 1] = closingLine(a.booking_id, a.parts);
}
function body(a, extra) {
  seedClosing(a);
  return Object.assign({ bike: '9011', name: 'Пётр', date_start: '2026-07-10', km_end: 12500, accrual: a }, extra || {});
}
const A1 = '2,1', K = '2,11';

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function J(x) { return JSON.stringify(x); }

if (process.argv.includes('--stdin')) {
  const inp = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
  if (inp.mode === 'opid') {
    console.log(JSON.stringify({ ids: (inp.vectors || []).map(v => closeAccrualOpId_(v[0], v[1], v[2], v[3], v[4], v[5])),
                                 lits: (inp.lits || []).map(closeAccrualLit_) }));
    process.exit(0);
  }
  // mode 'call': состояние листов → вызов → состояние листов
  const st = inp.crm || {};
  const env = makeEnv(st.grid || [HEADER], { formulas: st.formulas, fvals: st.fvals, notes: st.notes },
                      (inp.closing || {}).grid);
  // closing_get — для команды «закрытие» сквозного теста (правка доплаты, пока карточка ждёт)
  const CALLS = { closing_upsert: closingUpsert_, closing_get: closingGet_, close_booking: closeBooking };
  if (!CALLS[inp.call]) throw new Error('harness --stdin: неизвестный вызов ' + inp.call);
  const res = CALLS[inp.call](inp.body);
  console.log(JSON.stringify({ res,
    crm: { grid: env.clients.grid, formulas: env.clients.formulas, fvals: env.clients.fvals, notes: env.clients.notes },
    closing: { grid: env.closing.grid }, lock: { tries: LOCK.tries, released: LOCK.released } }));
  process.exit(0);
}

// ═══ 1. closing_upsert: части как легли + привязка (условие (1)) ═══
{
  const env = makeEnv([HEADER, crm({})], {}, [CLOSING_HEADERS.slice(),
    [BID, CB, 'Пётр', '20.07.2026', 'half', '500', '', '1000', '', 1500, '', 'open', '', '']]);
  const r = closingUpsert_({ booking_id: BID, bike: CB, name: 'Пётр', fuel_level: 'full' });
  check('closing.old-fields-kept', r.ok === true && r.row === 2 && r.updated === true && r.total_due === 1500, J(r));
  check('closing.components-raw', J(r.components) === J({ surcharge_days: '500', surcharge_fuel: '', damage: '1000', other: '' }), J(r.components));
  const b = r.binding || {};
  check('closing.match-booking-id', b.v === 1 && b.match === 'booking_id' && b.row === 2 && b.booking_id === BID && b.bike === CB, J(b));
  check('closing.booking-of-id', b.booking && b.booking.row === 2 && b.booking.date_start === DAY &&
        b.booking.date_end === '20.07.2026' && b.booking.status === 'В аренде' && b.booking_why === '', J(b.booking));
  check('closing.updated-at', typeof b.updated_at === 'string' && /^\d{4}-\d\d-\d\dT/.test(b.updated_at), b.updated_at);
  check('closing.crm-read-only', env.clients.writes.length === 0, J(env.clients.writes));
}
{
  const env = makeEnv([HEADER, crm({})], {}, [CLOSING_HEADERS.slice()]);
  const r = closingUpsert_({ booking_id: BID, bike: CB, name: 'Пётр', surcharge_days: '700' });
  check('closing.match-new', r.ok && r.saved && r.binding.match === 'new' && r.binding.row === 2 && r.row === 2 &&
        r.components.surcharge_days === '700' && r.binding.booking && r.binding.booking.row === 2, J(r));
  check('closing.append-one-row', env.closing.n.appendRow === 1, J(env.closing.n));
}
{
  // фоллбэк по байку (booking_id пуст) — строка ЧУЖОЙ прежней аренды возможна: match 'bike', бронь не названа
  makeEnv([HEADER, crm({})], {}, [CLOSING_HEADERS.slice(),
    ['bk-old', CB, 'Прежний', '01.06.2026', '', '900', '', '', '', 900, '', 'open', '', '']]);
  const r = closingUpsert_({ bike: CB, name: 'Пётр' });
  check('closing.match-bike-fallback', r.ok && r.binding.match === 'bike' && r.binding.booking_id === 'bk-old' &&
        r.components.surcharge_days === '900', J(r.binding));
}
{
  makeEnv([HEADER, crm({})], {}, [CLOSING_HEADERS.slice()]);
  const r = closingUpsert_({ bike: CB, name: 'Пётр' });
  check('closing.match-new-no-id', r.ok && r.binding.match === 'new_no_id' && r.binding.booking === null &&
        r.binding.booking_why === 'no_booking_id', J(r.binding));
}
{
  makeEnv([HEADER, crm({}), crm({ ds: '01.08.2026' })], {}, [CLOSING_HEADERS.slice()]);
  const r = closingUpsert_({ booking_id: BID, bike: CB });
  check('closing.booking-ambiguous', r.binding.booking === null && r.binding.booking_why === 'booking_ambiguous', J(r.binding));
  makeEnv([HEADER, crm({ bid: 'bk-other' })], {}, [CLOSING_HEADERS.slice()]);
  const r2 = closingUpsert_({ booking_id: BID, bike: CB });
  check('closing.booking-not-found', r2.binding.booking === null && r2.binding.booking_why === 'booking_not_found', J(r2.binding));
}
{
  const mirrorBotData = fs.readFileSync(path.join(GS_MIRROR, 'BotData.js'), 'utf8');
  const m = /CLOSING_HEADERS:\s*\[([\s\S]*?)\]/.exec(mirrorBotData);
  const got = m ? m[1].split(',').map(x => x.trim().replace(/^'|'$/g, '')).filter(Boolean) : null;
  check('closing.headers-mirror', got && J(got) === J(CLOSING_HEADERS), J(got));
}

// ═══ 2. начисление: число / формула / пусто / текст (условия (3)(4)) ═══
{
  const env = makeEnv([HEADER, crm({})], { notes: { [A1]: PREV_NOTE } });
  const a = acc({ surcharge_days: '500', damage: 1000 });
  const r = closeBooking(body(a));
  const c = env.clients;
  check('acc.number.closed', r.ok === true && r.closed === true && r.row === 2 && c.grid[1][0] === 'Завершена' &&
        c.grid[1][13] === 12500, J(r));
  check('acc.number.k-formula', c.formulas[K] === '=10000+500+1000', c.formulas[K]);
  const rc = r.accrual || {};
  check('acc.number.receipt', rc.v === 2 && rc.status === 'done' && rc.op_id === a.close_op_id && rc.k_written === true &&
        rc.k_readback === '=10000+500+1000' && rc.note === 'DONE' && rc.base === 'number' && rc.addends === '+500+1000', J(rc));
  const note = c.notes[A1] || '';
  check('acc.number.note-prev-kept', note.indexOf(PREV_NOTE + '\n') === 0, J(note));
  check('acc.number.note-done-line', note === PREV_NOTE + '\n[TB ' + a.close_op_id + ' DONE +500+1000] доплаты ' +
        '(начислено к оплате, не оплата): дни 500 · ущерб 1000; K было: 10000 → =10000+500+1000', J(note));
  check('acc.number.no-in-progress-left', note.indexOf('IN_PROGRESS') < 0, J(note));
  check('acc.number.a-value-is-status', c.grid[1][0] === 'Завершена', c.grid[1][0]);
  check('acc.number.order', J(c.writes.map(w => w[0])) === J(['setValue', 'setValue', 'setNote', 'setFormula', 'setNote']),
        J(c.writes));
  check('acc.lock.taken-released', LOCK.tries === 1 && LOCK.released === 1 && LOCK.lastMs === 10000, J(LOCK));
  check('acc.paid-not-in-reply', r.paid_total === null && r.paid_total_ignored === undefined, J(r));
}
{
  const env = makeEnv([HEADER, crm({ k: '' })], { formulas: { [K]: '=H2*G2-500' }, fvals: { [K]: 9500 } });
  const r = closeBooking(body(acc({ damage: '1000', other: '200' })));
  check('acc.formula.grouped', env.clients.formulas[K] === '=(H2*G2-500)+1000+200', env.clients.formulas[K]);
  check('acc.formula.receipt', r.accrual.status === 'done' && r.accrual.base === 'formula' &&
        r.accrual.k_readback === '=(H2*G2-500)+1000+200', J(r.accrual));
}
{
  const env = makeEnv([HEADER, crm({ k: '' })], { notes: { [A1]: PREV_NOTE } });
  const a = acc({ surcharge_days: '500' });
  const r = closeBooking(body(a));
  const note = env.clients.notes[A1] || '';
  check('acc.empty.k-untouched', env.clients.grid[1][10] === '' && env.clients.formulas[K] === undefined &&
        env.clients.n.setFormula === 0, J(env.clients.writes));
  check('acc.empty.note-only', note === PREV_NOTE + '\n[TB ' + a.close_op_id + ' NOTE_ONLY +500] основная сумма не ' +
        'подтверждена (K пуст) — K не трогал; доплаты (начислено к оплате, не оплата): дни 500', J(note));
  check('acc.empty.receipt', r.accrual.status === 'done' && r.accrual.base === 'empty' && r.accrual.k_written === false &&
        r.accrual.k_readback === '' && r.accrual.note === 'NOTE_ONLY', J(r.accrual));
}
{
  const env = makeEnv([HEADER, crm({ k: 'оплатил наличными' })]);
  const r = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.text.k-untouched', env.clients.grid[1][10] === 'оплатил наличными' && env.clients.n.setFormula === 0, J(r));
  check('acc.text.receipt', r.accrual.status === 'done' && r.accrual.base === 'text' && r.accrual.k_written === false &&
        /не целое число/.test(env.clients.notes[A1]), J(r.accrual));
  const env2 = makeEnv([HEADER, crm({ k: 10000.5 })]);
  const r2 = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.fraction.k-untouched', env2.clients.grid[1][10] === 10000.5 && r2.accrual.base === 'text', J(r2.accrual));
  const env3 = makeEnv([HEADER, crm({ k: '' })], { formulas: { [K]: '=X99' }, fvals: { [K]: '#REF!' } });
  const r3 = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.error.k-untouched', env3.clients.formulas[K] === '=X99' && r3.accrual.base === 'error' &&
        r3.accrual.status === 'done' && env3.clients.n.setFormula === 0, J(r3.accrual));
}

// ═══ 3. стоп ДО записей K/примечания: части, привязка, id (условия (1)(2)) ═══
{
  const bad = [['=1+1'], ['half'], [-5], [NaN], [Infinity], ['1e3'], ['12.5'], [12.5], [true], [{}], [' 500'],
               ['500 ฿'], ['1,5'], [1e9]];
  bad.forEach(([v]) => {
    const env = makeEnv([HEADER, crm({})], { notes: { [A1]: PREV_NOTE } });
    const a = acc({ surcharge_days: '500' });
    a.parts.damage = v;
    const r = closeBooking(body(a));
    check('acc.bad-component.' + J(String(v)), r.ok === true && r.accrual.status === 'stopped' &&
          r.accrual.reason === 'bad_component' && env.clients.grid[1][10] === 10000 && env.clients.n.setFormula === 0 &&
          env.clients.notes[A1] === PREV_NOTE && env.clients.grid[1][0] === 'Завершена', J(r.accrual));
  });
}
{
  const runs = [
    ['wrong-booking-id', acc({ surcharge_days: '500' }, { bid: 'bk-other' })],
    ['wrong-row', acc({ surcharge_days: '500' }, { brow: 3 })],
    ['wrong-day', acc({ surcharge_days: '500' }, { day: '2026-07-11' })],
  ];
  runs.forEach(([nm, a]) => {
    const env = makeEnv([HEADER, crm({})]);
    const r = closeBooking(body(a));
    check('acc.binding.' + nm, r.ok && r.accrual.status === 'stopped' && r.accrual.reason === 'binding_mismatch' &&
          env.clients.n.setNote === 0 && env.clients.n.setFormula === 0, J(r.accrual));
  });
  const env = makeEnv([HEADER, crm({ bid: '' })]);
  const r = closeBooking(body(acc({ surcharge_days: '500' }, { bid: '' })));
  check('acc.binding.no-booking-id', r.accrual.status === 'stopped' && r.accrual.reason === 'binding_mismatch', J(r.accrual));
}
{
  // тот же id, другие части — не наша операция
  const env = makeEnv([HEADER, crm({})]);
  const a = acc({ surcharge_days: '500' });
  a.parts.surcharge_days = '700';
  const r = closeBooking(body(a));
  check('acc.payload-mismatch.id', r.accrual.status === 'stopped' && r.accrual.reason === 'payload_mismatch' &&
        env.clients.n.setNote === 0 && env.clients.n.setFormula === 0 && env.clients.grid[1][10] === 10000, J(r.accrual));
  makeEnv([HEADER, crm({})]);
  const a2 = acc({ surcharge_days: '500' }, { crow: 8 });
  a2.closing_row = 7;
  const r2 = closeBooking(body(a2));
  check('acc.payload-mismatch.closing-row', r2.accrual.reason === 'payload_mismatch', J(r2.accrual));
}
{
  // { v: 1 } — поле прежней версии (без сверки листа закрытия) не принимается: стоп до записей
  const shapes = [{ v: 1 }, 'строка', { v: 2, close_op_id: 'co1-xyz' }];
  shapes.forEach((s, i) => {
    makeEnv([HEADER, crm({})]);
    const r = closeBooking(body(Object.assign({}, acc({ surcharge_days: '500' }), typeof s === 'object' ? s : {}),
                                typeof s === 'string' ? { accrual: s } : {}));
    check('acc.bad-shape.' + i, r.ok && r.accrual.status === 'stopped' && r.accrual.reason === 'bad_accrual', J(r.accrual));
  });
  makeEnv([HEADER, crm({})]);
  const a = acc({});
  const r = closeBooking(body(a));
  check('acc.no-addends', r.ok && r.accrual.status === 'stopped' && r.accrual.reason === 'no_addends', J(r.accrual));
}

// ═══ 4. та же операция дважды / повтор / частичный исход (условия (2)(3)) ═══
{
  const env = makeEnv([HEADER, crm({})]);
  const a = acc({ surcharge_days: '500', damage: '1000' });
  closeBooking(body(a));
  const r2 = closeBooking(body(a));             // строка уже «Завершена» — второй заход её не находит
  check('acc.twice.second-not-found', r2.ok === false && r2.error === 'not_found' &&
        env.clients.formulas[K] === '=10000+500+1000' && env.clients.n.setFormula === 1, J(r2));
  check('acc.twice.lock-released', LOCK.tries === 2 && LOCK.released === 2, J(LOCK));
  // строку вернули в «В аренде» руками — метка DONE: второй раз слагаемые не добавляются
  env.clients.grid[1][0] = 'В аренде';
  const r3 = closeBooking(body(a));
  check('acc.reopened-done.no-double-add', r3.ok && r3.accrual.status === 'already_done' &&
        env.clients.formulas[K] === '=10000+500+1000' && env.clients.n.setFormula === 1 &&
        r3.accrual.k_readback === '=10000+500+1000', J(r3.accrual));
}
{
  // сбой между K и примечанием DONE: K проверен, метка — IN_PROGRESS
  const env = makeEnv([HEADER, crm({})], { fault: { setNote: [2] } });
  const a = acc({ surcharge_days: '500', damage: '1000' });
  const r = closeBooking(body(a));
  check('acc.partial.k-then-note-fail', r.ok && r.accrual.status === 'partial' && r.accrual.k_written === true &&
        env.clients.formulas[K] === '=10000+500+1000' && /IN_PROGRESS/.test(env.clients.notes[A1]) &&
        r.accrual.note === 'IN_PROGRESS' && /^exception_at_note_done/.test(r.accrual.reason), J(r.accrual));
  check('acc.partial.lock-released', LOCK.released === 1, J(LOCK));
  // повтор той же операции на вновь открытой строке: K уже РОВНО ожидаемый → только метка DONE, без слагаемых
  env.clients.grid[1][0] = 'В аренде';
  const r2 = closeBooking(body(a));
  check('acc.partial.recover-done', r2.ok && r2.accrual.status === 'already_done' && r2.accrual.recovered === true &&
        env.clients.formulas[K] === '=10000+500+1000' && env.clients.n.setFormula === 1 &&
        /DONE/.test(env.clients.notes[A1]) && !/IN_PROGRESS/.test(env.clients.notes[A1]), J(r2.accrual));
}
{
  // сбой записи K: метка IN_PROGRESS легла, K — нет; исход «неизвестно», без повтора
  const env = makeEnv([HEADER, crm({})], { fault: { setFormula: [1] } });
  const a = acc({ surcharge_days: '500' });
  const r = closeBooking(body(a));
  check('acc.k-write-fail.unknown', r.ok && r.accrual.status === 'unknown' && env.clients.grid[1][10] === 10000 &&
        env.clients.formulas[K] === undefined && /IN_PROGRESS/.test(env.clients.notes[A1]) &&
        /^exception_at_k_write/.test(r.accrual.reason), J(r.accrual));
  env.clients.grid[1][0] = 'В аренде';
  const r2 = closeBooking(body(a));             // повтор той же операции: K не ожидаемый → ни одной записи
  check('acc.k-write-fail.retry-partial-no-write', r2.accrual.status === 'partial' &&
        r2.accrual.reason === 'in_progress_found' && env.clients.n.setFormula === 1 && env.clients.grid[1][10] === 10000,
        J(r2.accrual));
}
{
  // сбой первой записи примечания: K не пишем, исход «неизвестно»
  const env = makeEnv([HEADER, crm({})], { fault: { setNote: [1] } });
  const r = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.note-fail.unknown-no-k', r.ok && r.accrual.status === 'unknown' && env.clients.n.setFormula === 0 &&
        env.clients.grid[1][10] === 10000, J(r.accrual));
}
{
  // «человек» правит K между меткой IN_PROGRESS и записью K — K не перезаписываем
  const env = makeEnv([HEADER, crm({})], { afterSetNote: (n, sh) => { if (n === 1) sh.grid[1][10] = 12000; } });
  const r = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.prestate-changed', r.ok && r.accrual.status === 'partial' && r.accrual.reason === 'prestate_changed' &&
        env.clients.grid[1][10] === 12000 && env.clients.n.setFormula === 0, J(r.accrual));
  const env2 = makeEnv([HEADER, crm({})], { afterSetNote: (n, sh) => { if (n === 1) sh.grid[1][24] = 'bk-swapped'; } });
  const r2 = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.prestate-row-identity', r2.accrual.status === 'partial' && r2.accrual.reason === 'prestate_changed' &&
        env2.clients.n.setFormula === 0, J(r2.accrual));
}
{
  // лист вернул другую формулу, чем записали — «неизвестно», не «готово»
  const env = makeEnv([HEADER, crm({})], { normalizeFormula: f => f + '+0' });
  const r = closeBooking(body(acc({ surcharge_days: '500' })));
  check('acc.k-readback-mismatch', r.accrual.status === 'unknown' && r.accrual.reason === 'k_readback_mismatch' &&
        r.accrual.k_written === false && /IN_PROGRESS/.test(env.clients.notes[A1]), J(r.accrual));
}
{
  // метка ТОЙ ЖЕ операции с другими слагаемыми (правленое примечание) — payload_mismatch
  const a = acc({ surcharge_days: '500' });
  const env = makeEnv([HEADER, crm({})], { notes: { [A1]: '[TB ' + a.close_op_id + ' DONE +700] ручная правка' } });
  const r = closeBooking(body(a));
  check('acc.marker-other-addends', r.accrual.status === 'stopped' && r.accrual.reason === 'payload_mismatch' &&
        env.clients.n.setFormula === 0, J(r.accrual));
  // у строки уже есть начисление ДРУГОЙ операции — второе не кладём
  const env2 = makeEnv([HEADER, crm({})], { notes: { [A1]: '[TB co1-0123456789abcdef DONE +900] прежняя' } });
  const r2 = closeBooking(body(a));
  check('acc.other-op-recorded', r2.accrual.status === 'stopped' && r2.accrual.reason === 'other_accrual_recorded' &&
        env2.clients.n.setFormula === 0, J(r2.accrual));
}

// ═══ 5. замок: два оператора, занятость, без начисления замка нет ═══
{
  const env = makeEnv([HEADER, crm({})]);
  LOCK.busy = true;
  const a = acc({ surcharge_days: '500' });
  const r = closeBooking(body(a));
  check('lock.busy-no-writes', r.ok === false && r.error === 'lock_busy' && env.clients.writes.length === 0 &&
        r.accrual && r.accrual.status === 'stopped' && r.accrual.reason === 'lock_busy' && r.accrual.op_id === a.close_op_id,
        J(r));
  check('lock.busy-not-released', LOCK.released === 0, J(LOCK));
}
{
  const env = makeEnv([HEADER, crm({})]);
  const r = closeBooking({ bike: '9011', name: 'Пётр', km_end: 12500 });
  check('lock.not-taken-without-accrual', r.ok && LOCK.tries === 0 && env.clients.grid[1][10] === 10000, J(LOCK));
}
{
  // исключение записи закрытия (A) под замком — write_failed, замок снят, начисление не начиналось
  const env = makeEnv([HEADER, crm({})], { fault: { setValue: [1] } });
  const r = closeBooking(body(acc({ surcharge_days: '500' })));
  check('lock.released-on-write-failed', r.ok === false && r.error === 'write_failed' && LOCK.released === 1 &&
        r.accrual && r.accrual.status === 'stopped' && r.accrual.reason === 'close_write_failed' &&
        env.clients.n.setNote === 0 && env.clients.n.setFormula === 0, J(r));
}

// ═══ 6. paid_total (условие (5)): без явного opt-in не пишется ═══
{
  const env = makeEnv([HEADER, crm({})]);
  const r = closeBooking({ bike: '9011', name: 'Пётр', km_end: 12500, paid_total: 1500 });
  check('paid.ignored-without-opt-in', r.ok && env.clients.grid[1][10] === 10000 && r.paid_total === null &&
        r.paid_total_ignored === true, J(r));
  const env2 = makeEnv([HEADER, crm({})]);
  const r2 = closeBooking({ bike: '9011', name: 'Пётр', km_end: 12500, paid_total: 1500, paid_total_opt_in: true });
  check('paid.written-with-opt-in', r2.ok && env2.clients.grid[1][10] === 1500 && r2.paid_total === 1500 &&
        r2.paid_total_ignored === undefined, J(r2));
  const env3 = makeEnv([HEADER, crm({})]);
  const r3 = closeBooking({ bike: '9011', name: 'Пётр', km_end: 12500, paid_total: 1500, paid_total_opt_in: 'true' });
  check('paid.opt-in-only-boolean', env3.clients.grid[1][10] === 10000 && r3.paid_total_ignored === true, J(r3));
  const env4 = makeEnv([HEADER, crm({})]);
  const r4 = closeBooking(body(acc({ surcharge_days: '500' }), { paid_total: 1500, paid_total_opt_in: true }));
  check('paid.ignored-with-accrual', r4.ok && r4.paid_total_ignored === true && env4.clients.formulas[K] === '=10000+500',
        J(r4));
}

// ═══ 7. прежние отказы закрытия с начислением — до записей, под замком ═══
{
  const env = makeEnv([HEADER, crm({})]);
  const r = closeBooking(body(acc({ surcharge_days: '500' }), { km_end: 11000 }));
  check('acc.odometer-back-no-writes', r.ok === false && r.error === 'odometer_back' && env.clients.writes.length === 0 &&
        LOCK.released === 1, J(r));
  const env2 = makeEnv([HEADER, crm({})]);
  const r2 = closeBooking(body(acc({ surcharge_days: '500' }), { km_end: undefined }));
  check('acc.km-required-no-writes', r2.error === 'km_required' && env2.clients.writes.length === 0, J(r2));
}

// ═══ 8. id операции: независимый пересчёт канона ═══
{
  const lits = ['500', '', '1000', ''];
  const canon = ['co1', BID, '2', '9011', DAY, '7'].concat(lits).join('|');
  const ref = 'co1-' + crypto.createHash('sha256').update(canon, 'utf8').digest('hex').slice(0, 16);
  check('opid.independent', closeAccrualOpId_(BID, 2, ' 9011 ', DAY, 7, lits) === ref, ref);
  check('opid.lits', J(['500', 500, '0500', 0, '', null, undefined].map(closeAccrualLit_)) ===
        J(['500', '500', '500', '', '', '', '']), J(['500', 500, '0500', 0, '', null].map(closeAccrualLit_)));
}

// ═══ 9. ВЕРСИЯ записи листа закрытия (замечание приёмки 20.10): части операции — с листом СЕЙЧАС, под замком ═══
// Карточка рождается на одном ответе closing_upsert, а «да» приходит позже: лист мог смениться повтором возврата или
// командой «закрытие». Строка перечитывается по ТОЧНОМУ booking_id; разошлась — отказ ЦЕЛИКОМ до записей.
function setPart(k, v, row) {                     // правка строки листа «после карточки» (мимо записи моста)
  CUR.closing.grid[(row || CROW) - 1][CLOSING_HEADERS.indexOf(k)] = v;
}
{
  // часть ДОБАВЛЕНА (прочее +300), пока карточка ждала: старые части не пишутся, лист — в ответе
  const env = makeEnv([HEADER, crm({})], { notes: { [A1]: PREV_NOTE } });
  const a = acc({ surcharge_days: '500', damage: '1000' });
  const req = body(a);
  setPart('other', '300');
  const r = closeBooking(req);
  const c = env.clients;
  check('ver.added.refused-no-writes', r.ok === false && r.error === 'closing_changed' && r.row === 2 &&
        c.writes.length === 0 && c.grid[1][0] === 'В аренде' && c.grid[1][13] === '' && c.grid[1][10] === 10000 &&
        c.notes[A1] === PREV_NOTE && env.closing.writes.length === 0, J(r) + J(c.writes));
  check('ver.added.receipt-stopped', r.accrual && r.accrual.v === 2 && r.accrual.op_id === a.close_op_id &&
        r.accrual.status === 'stopped' && r.accrual.reason === 'closing_changed' && r.accrual.k_written === false, J(r.accrual));
  const now = r.closing_now || {};
  const nb = now.binding || {};
  check('ver.added.closing-now', now.ok === true && now.row === CROW && J(now.components) ===
        J({ surcharge_days: '500', surcharge_fuel: '', damage: '1000', other: '300' }) && nb.match === 'booking_id' &&
        nb.booking_id === BID && nb.row === CROW && nb.booking && nb.booking.row === 2 && nb.booking.date_start === DAY,
        J(now));
  check('ver.added.lock-released', LOCK.tries === 1 && LOCK.released === 1, J(LOCK));
  // новая карточка — НОВАЯ операция из листа сейчас: та же бронь, новые части → закрывает и начисляет новое
  const a2 = acc({ surcharge_days: '500', damage: '1000', other: '300' });
  check('ver.added.new-op-differs', a2.close_op_id !== a.close_op_id, a2.close_op_id);
  const r2 = closeBooking(body(a2));
  check('ver.added.new-op-done', r2.ok && r2.accrual.status === 'done' && c.formulas[K] === '=10000+500+1000+300' &&
        c.grid[1][0] === 'Завершена', J(r2.accrual));
}
{
  // часть УМЕНЬШЕНА (ущерб 1000 → 400): K не получает лишнего
  const env = makeEnv([HEADER, crm({})]);
  const req = body(acc({ surcharge_days: '500', damage: '1000' }));
  setPart('damage', 400);
  const r = closeBooking(req);
  check('ver.reduced.refused-no-writes', r.ok === false && r.error === 'closing_changed' &&
        env.clients.writes.length === 0 && env.clients.formulas[K] === undefined && r.closing_now.components.damage === 400,
        J(r));
  const r2 = closeBooking(body(acc({ surcharge_days: '500', damage: 400 })));
  check('ver.reduced.new-op-done', r2.ok && r2.accrual.status === 'done' && env.clients.formulas[K] === '=10000+500+400',
        env.clients.formulas[K]);
}
{
  // доплату сняли совсем: отказ; в листе — ни одной части (новая карточка — уже без начисления)
  const env = makeEnv([HEADER, crm({})]);
  const req = body(acc({ damage: '1000' }));
  setPart('damage', '');
  const r = closeBooking(req);
  check('ver.waived.refused', r.error === 'closing_changed' && env.clients.writes.length === 0 &&
        J(r.closing_now.components) === J({ surcharge_days: '', surcharge_fuel: '', damage: '', other: '' }), J(r));
}
{
  // у строки листа стёрли booking_id: строки этой брони нет — отказ; ПО БАЙКУ та же строка не подбирается
  const env = makeEnv([HEADER, crm({})]);
  const req = body(acc({ damage: '1000' }));
  setPart('booking_id', '');
  const r = closeBooking(req);
  check('ver.row-gone.refused', r.error === 'closing_changed' && env.clients.writes.length === 0 &&
        J(r.closing_now) === J({ ok: false, error: 'not_found' }), J(r));
  check('ver.row-gone.no-bike-fallback', CUR.closing.grid[CROW - 1][1] === CB &&
        CUR.closing.grid[CROW - 1][CLOSING_HEADERS.indexOf('status')] === 'open' && r.error === 'closing_changed',
        J(r.closing_now));
}
{
  // строка той же брони теперь в другом месте листа: номер строки — часть операции → отказ
  const env = makeEnv([HEADER, crm({})]);
  const req = body(acc({ damage: '1000' }));
  const g = CUR.closing.grid;
  while (g.length < CROW + 2) g.push(new Array(30).fill(''));
  g[CROW + 1] = g[CROW - 1].slice();
  g[CROW - 1] = new Array(30).fill('');
  const r = closeBooking(req);
  check('ver.row-moved.refused', r.error === 'closing_changed' && env.clients.writes.length === 0 &&
        r.closing_now.row === CROW + 2, J(r.closing_now));
}
{
  // повтор возврата БЕЗ правки доплат (настоящий upsert: топливо и штамп сменились) — версия = содержимое, начисляем
  const env = makeEnv([HEADER, crm({})]);
  const req = body(acc({ surcharge_days: '500', damage: '1000' }));
  closingUpsert_({ booking_id: BID, bike: CB, fuel_level: 'full' });
  const r = closeBooking(req);
  check('ver.same-parts.reupsert-done', r.ok && r.accrual.status === 'done' && env.closing.n.setValues === 1 &&
        env.clients.formulas[K] === '=10000+500+1000', J(r.accrual));
  // в ячейке листа — число вместо строки цифр (так хранит Sheets): тот же литерал
  const env2 = makeEnv([HEADER, crm({})]);
  const req2 = body(acc({ surcharge_days: '500', damage: '1000' }));
  setPart('surcharge_days', 500);
  setPart('damage', 1000);
  const r2 = closeBooking(req2);
  check('ver.number-cell-same-lit', r2.ok && r2.accrual.status === 'done' && env2.clients.formulas[K] === '=10000+500+1000',
        J(r2.accrual));
}
{
  // лист закрытия не прочитан (Bot Data недоступна): закрытие идёт, начисление — стоп без единой записи K/примечания
  const env = makeEnv([HEADER, crm({})], { notes: { [A1]: PREV_NOTE } });
  const req = body(acc({ damage: '1000' }));
  CUR.closingFail = true;
  const r = closeBooking(req);
  check('ver.closing-unread.stop', r.ok && r.closed && r.accrual.status === 'stopped' &&
        /^closing_unread: /.test(r.accrual.reason) && env.clients.grid[1][0] === 'Завершена' &&
        env.clients.n.setFormula === 0 && env.clients.notes[A1] === PREV_NOTE, J(r.accrual));
}
{
  // лист правят ПОСЛЕ плана — между меткой IN_PROGRESS и записью K: K не пишем, исход partial
  const env = makeEnv([HEADER, crm({})], { afterSetNote: (n) => { if (n === 1) setPart('damage', 400); } });
  const r = closeBooking(body(acc({ surcharge_days: '500', damage: '1000' })));
  check('ver.changed-at-prestate.partial', r.ok && r.accrual.status === 'partial' && r.accrual.reason === 'closing_changed' &&
        r.accrual.k_written === false && env.clients.n.setFormula === 0 && env.clients.grid[1][10] === 10000 &&
        /IN_PROGRESS/.test(env.clients.notes[A1]), J(r.accrual));
}
{
  // closing_now — того же вида, что ответ closing_upsert: вызывающий судит новую карточку тем же кодом
  makeEnv([HEADER, crm({})], {}, [CLOSING_HEADERS.slice(),
    [BID, CB, 'Пётр', '20.07.2026', '', '500', '', '1000', '', 1500, '', 'open', '', '']]);
  const up = closingUpsert_({ booking_id: BID, bike: CB, fuel_level: 'half' });
  const now = closingReplyOf_(closingRowById_(BID));
  const norm = o => { const b = Object.assign({}, o.binding); delete b.updated_at;
    return J({ row: o.row, total_due: o.total_due, parts: CLOSE_ACCRUAL.PARTS.map(k => closeAccrualLit_(o.components[k])),
               binding: b, keys: Object.keys(o.binding).sort() }); };
  check('ver.reply-of-same-shape', now.ok === true && up.ok === true && norm(now) === norm(up) &&
        typeof now.binding.updated_at === 'string' && now.binding.updated_at.length > 0, norm(now) + ' vs ' + norm(up));
  check('ver.reply-of-not-found', J(closingReplyOf_(closingRowById_('bk-nope'))) === J({ ok: false, error: 'not_found' }) &&
        closingRowById_('') === null, '');
}

const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ total: cases.length, failed: failed.length, cases }, null, 1));
process.exit(failed.length ? 1 : 0);
