'use strict';
/**
 * Харнесс «ОТМЕНА ЗАПИСИ ТО»: исполняет РЕАЛЬНЫЙ код моста в node с мок-SpreadsheetApp
 * (схема fleetfix_gs_harness.js), но берёт файлы из ДВУХ источников:
 *   · `bridge_build/` — КАТАЛОГ СБОРКИ ЗАХОДА, судимый код (ReadFleet.js, ServiceUndo.js);
 *   · `bridge_prod/`  — ЗЕРКАЛО задеплоенной версии, база для файлов, которых сборка не трогала
 *                       (Config.js — verifyWrite_/адрес, BotData.js — НАСТОЯЩИЕ logWrite_,
 *                       readWriteLog_, serviceUpsert, getBotTab_).
 * Правило выбора одно и записано кодом (srcOf): файл есть в сборке — берём сборку, иначе
 * зеркало. После выкладки и обновления зеркала харнесс сам начнёт судить зеркало.
 *
 * ЧТО ПРОВЕРЯЕТСЯ.
 *   1. ПАМЯТЬ О ВЫТЕСНЕНИИ пишется при КАЖДОЙ записи регистра (I, J, K, L), а прежде её не
 *      было ни у одной, кроме ветки исправления масла.
 *   2. ДВЕРЬ ОТМЕНЫ по ССЫЛКЕ НА АКТ возвращает ОБЕ базы: живой Лист1 и зеркало
 *      «обслуживание». Одна вернулась, вторая нет → отказ ЦЕЛИКОМ с компенсацией первой.
 *   3. ОТРИЦАТЕЛЬНЫЕ (каждый обязан краснеть, то есть дверь обязана ОТКАЗАТЬ):
 *      скрутка под видом отмены · клетку между делом изменил третий · отмена не последней
 *      записи · отмена отмены · вторая база недоступна на середине.
 *
 * ЖИВОЙ ФОРМАТ клеток снят с самих писателей (Number(raw), пусто → 0) и с разведки парка:
 * клетка держит ЧИСЛО (41357), пустая = «регистр не заводили», встречается и не-число.
 * БАЙКИ В ФИКСТУРАХ ВЫДУМАНЫ и помечены ТЕСТ: живых номеров парка здесь нет ни одного.
 *
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_undo_door.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');

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
    appendBroken: false,
    getName() { return name; },
    getParent() { return { getId() { return 'ТЕСТ-таблица'; } }; },
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(arr) {
      if (sheet.appendBroken) throw new Error('лист недоступен для дописывания');
      const a = arr.slice(); while (a.length < WIDTH) a.push('');
      grid.push(a);
    },
    getRange(a, b, c, d) {
      if (typeof a === 'string') {                       // форма 'A1:AH1' — её зовёт getFleetStatus
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

// Лист1 «Байки»: строка 1 дашборд, строка 2 шапка, данные с 3-й.
// Колонки: C название (idx 2), I масло (8), J редуктор (9), K ABS (10), L фильтр (11).
const C_OIL = 9, C_GEAR = 10, C_ABS = 11, C_AIR = 12;   // 1-based

function freshFleet() {
  const head = new Array(WIDTH).fill('');
  const hdr = new Array(WIDTH).fill('');
  hdr[2] = 'Название'; hdr[8] = 'ТО Oil'; hdr[9] = 'ТО Gear'; hdr[10] = 'ABS'; hdr[11] = 'Аир фильтр';
  function bike(name, oil, gear, abs, air) {
    const r = new Array(WIDTH).fill('');
    r[2] = name; r[8] = oil; r[9] = gear; r[10] = abs; r[11] = air;
    return r;
  }
  return makeSheet('Лист1', [
    head, hdr,
    // ВЫДУМАННЫЕ байки: таких номеров в парке нет (парк — четырёхзначные номера).
    bike('ТЕСТ-БАЙК 90101', '', 41357, '', ''),        // редуктор как у живого случая, масла нет
    bike('ТЕСТ-БАЙК 90202', 24500, '', '', ''),         // только масло
    bike('ТЕСТ-БАЙК 90303', 10000, 10000, 10000, 10000),
    bike('ТЕСТ-БАЙК 90404', '', 'прочерк', '', ''),     // не-число в клетке (живой формат)
    bike('ТЕСТ-ДУБЛЬ 90505', '', 100, '', ''),
    bike('ТЕСТ-ДУБЛЬ 90505', '', 200, '', ''),          // два байка с одним номером → ambiguous
  ]);
}

const LOG_HDR = ['logged_at', 'initiator', 'action', 'args', 'result', 'critical'];
const SVC_HDR = ['updated_at', 'bike', 'topic_id', 'service_type', 'current_km',
  'last_service_km', 'interval_km', 'next_km', 'status', 'pinned_msg_id', 'last_reminded_at', 'note'];

let fleetSheet = freshFleet();
let logSheet = makeSheet('боевой_лог', [LOG_HDR.slice()]);
let svcSheet = makeSheet('обслуживание', [SVC_HDR.slice()]);
let svcBroken = false;         // «зеркало недоступно» — вторая база отказывает на середине
let uuidSeq = 0;

global.SpreadsheetApp = {
  openById: (id) => ({
    getSheetByName: (n) => {
      if (n === 'Лист1') return fleetSheet;
      if (n === 'боевой_лог') return logSheet;
      if (n === 'обслуживание') {
        if (svcBroken) throw new Error('зеркало обслуживания недоступно');
        return svcSheet;
      }
      return null;
    },
    getSheets: () => [], getId: () => String(id),
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
// Живой Utilities.getUuid() случаен ЦЕЛИКОМ — мок обязан быть таким же, иначе ключ акта
// проверялся бы на источнике удобнее настоящего (мок, переставший задевать ветку, хуже
// отсутствующего). Здесь меняются все части uuid сразу.
global.Utilities = {
  getUuid: () => {
    uuidSeq += 1;
    const h = (0x1a2b3c4d + uuidSeq * 7919).toString(16);
    return h + '-' + h.slice(0, 4) + '-4' + h.slice(1, 4) + '-a' + h.slice(2, 5) + '-' + h + h.slice(0, 4);
  },
  formatDate: (d) => String(d),
};
global.Session = { getScriptTimeZone: () => 'UTC' };
global.CacheService = {
  getScriptCache: () => ({ get: () => null, put: () => {}, remove: () => {} }),
};

for (const f of ['Config.js', 'BotData.js', 'ReadFleet.js', 'ServiceUndo.js'])
  vm.runInThisContext(fs.readFileSync(srcOf(f), 'utf8'), { filename: srcOf(f) });

// ─────────────────────────── утилиты сценариев ───────────────────────────
const cases = [];
let negatives = 0;
function check(name, cond, detail) {
  cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) });
}
/** Отрицательная проверка: дверь ОБЯЗАНА отказать. Считается отдельно — их число в отчёте. */
function checkNeg(name, cond, detail) {
  negatives += 1;
  check(name, cond, detail);
}

function reset() {
  fleetSheet = freshFleet();
  logSheet = makeSheet('боевой_лог', [LOG_HDR.slice()]);
  svcSheet = makeSheet('обслуживание', [SVC_HDR.slice()]);
  svcBroken = false;
  uuidSeq = 0;
}
function cellOf(plate, col) {
  for (let i = 2; i < fleetSheet.grid.length; i++)
    if (plateFromName_(String(fleetSheet.grid[i][2])) === plate) return fleetSheet.grid[i][col - 1];
  return null;
}
function logRows(actName) {
  return logSheet.grid.slice(1).filter(r => String(r[2]) === actName);
}
function mirrorOf(plate, kind) {
  for (let i = 1; i < svcSheet.grid.length; i++) {
    if (String(svcSheet.grid[i][3]).trim() !== kind) continue;
    if (plateFromName_(String(svcSheet.grid[i][1])) === plate) return svcSheet.grid[i];
  }
  return null;
}
/** Зеркало «как его ведёт splinter после акта»: ЖИВОЙ serviceUpsert, не ручная строка. */
function mirrorAfterAct(bike, kind, current, last, interval) {
  return serviceUpsert({ bike: bike, service_type: kind, current_km: current,
                         last_service_km: last, interval_km: interval });
}

// ══════════════════════════ 1. ПАМЯТЬ О ВЫТЕСНЕНИИ ══════════════════════════
// Прежде боевой журнал знал РОВНО одну запись регистра (ветка исправления масла, ReadFleet:350).
{
  reset();
  const g = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true, by: '@pym' });
  check('mem.gear-write-ok', g.ok === true, JSON.stringify(g));
  check('mem.gear-act-id', typeof g.act === 'string' && g.act.length > 0, JSON.stringify(g.act));
  check('mem.gear-act-logged', g.act_logged === true, JSON.stringify(g.act_logged));
  const rows = logRows('ТО-регистр: вытеснение');
  check('mem.gear-one-line', rows.length === 1, JSON.stringify(rows.length));
  const rec = rows.length ? undoParse_(rows[0][3]) : null;
  check('mem.gear-parsed', !!rec, rows.length ? rows[0][3] : '');
  check('mem.gear-old', rec && rec.o === 41357, JSON.stringify(rec));
  check('mem.gear-new', rec && rec.n === 41641, JSON.stringify(rec));
  check('mem.gear-col', rec && rec.c === C_GEAR, JSON.stringify(rec && rec.c));
  check('mem.gear-kind', rec && rec.k === 'gear', JSON.stringify(rec && rec.k));
  check('mem.gear-plate', rec && rec.p === '90101', JSON.stringify(rec && rec.p));
  check('mem.gear-by', rec && rec.w === '@pym', JSON.stringify(rec && rec.w));
  check('mem.gear-args-fits', String(rows[0][3]).length <= 500, String(rows[0][3]).length);
  check('mem.gear-human-readable', String(rows[0][3]).indexOf('кол.J 41357→41641') >= 0, rows[0][3]);

  // остальные два вида регистра — та же память
  const a = setFleetService_({ number: '90303', kind: 'abs', km: 12000, confirmed: true });
  const f = setFleetService_({ number: '90303', kind: 'airfilter', km: 13000, confirmed: true });
  check('mem.abs-act', a.ok === true && !!a.act, JSON.stringify(a));
  check('mem.air-act', f.ok === true && !!f.act, JSON.stringify(f));
  check('mem.three-lines', logRows('ТО-регистр: вытеснение').length === 3, logRows('ТО-регистр: вытеснение').length);

  // масло: ОБЫЧНЫЙ рост тоже оставляет память (прежде — ни строки)
  reset();
  const o = setFleetOil_({ number: '90202', oil_km: 26000, confirmed: true, by: '@bot' });
  check('mem.oil-grow-act', o.ok === true && !!o.act, JSON.stringify(o));
  const orec = undoParse_(logRows('ТО-регистр: вытеснение')[0][3]);
  check('mem.oil-grow-col', orec && orec.c === C_OIL, JSON.stringify(orec && orec.c));
  check('mem.oil-grow-old', orec && orec.o === 24500, JSON.stringify(orec));

  // пустая клетка: сырое значение запомнено ПУСТЫМ, а не нулём
  reset();
  const e = setFleetService_({ number: '90202', kind: 'gear', km: 5000, confirmed: true });
  const erec = undoParse_(logRows('ТО-регистр: вытеснение')[0][3]);
  check('mem.empty-raw', erec && erec.r === '' && erec.o === 0, JSON.stringify(erec));

  // ветка исправления масла: аудит-след И память — РАЗНЫЕ строки, прежний след не тронут
  reset();
  const fx = setFleetOil_({ number: '90202', oil_km: 24000, confirmed: true,
                            fix_reason: 'ошибка распознавания', fixed_by: '@filipp' });
  check('mem.fix-ok', fx.ok === true, JSON.stringify(fx));
  check('mem.fix-audit-kept', logRows('set_fleet_oil (исправление)').length === 1,
        JSON.stringify(logSheet.grid.slice(1).map(r => r[2])));
  check('mem.fix-memory-added', logRows('ТО-регистр: вытеснение').length === 1,
        JSON.stringify(logSheet.grid.slice(1).map(r => r[2])));
  check('mem.fix-act-id', !!fx.act, JSON.stringify(fx.act));
  check('mem.fix-by', undoParse_(logRows('ТО-регистр: вытеснение')[0][3]).w === '@filipp',
        JSON.stringify(logRows('ТО-регистр: вытеснение')[0][3]));

  // журнал упал → запись состоялась, но об отсутствии памяти СКАЗАНО (best-effort, не молчание)
  reset();
  logSheet.appendBroken = true;
  const nb = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  check('mem.log-down-write-ok', nb.ok === true && String(cellOf('90101', C_GEAR)) === '41641', JSON.stringify(nb));
  check('mem.log-down-said', nb.act === null && nb.act_logged === false, JSON.stringify(nb));
}

// ══════════════════════════ 2. ЗЕРКАЛО НОРМАЛИЗАЦИИ ══════════════════════════
// undoCellNum_ обязан считать клетку ТАК ЖЕ, как её считают сами писатели, иначе сличение
// разойдётся с записью молча. Сверяется на живом коде обеих сторон.
{
  const probes = [['90202', C_GEAR, ''], ['90303', C_GEAR, 10000], ['90404', C_GEAR, 'прочерк']];
  for (const [plate, col, raw] of probes) {
    reset();
    const w = setFleetService_({ number: plate, kind: 'gear', km: 99000, confirmed: true });
    check('norm.' + plate, w.ok === true && w.old_km === undoCellNum_(raw),
          'писатель=' + JSON.stringify(w.old_km) + ' сличение=' + JSON.stringify(undoCellNum_(raw)));
  }
}

// ══════════════════════════ 3. ОТМЕНА ВОЗВРАЩАЕТ ОБЕ БАЗЫ ══════════════════════════
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true, by: '@pym' });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  check('undo.setup-cell', String(cellOf('90101', C_GEAR)) === '41641', cellOf('90101', C_GEAR));
  check('undo.setup-mirror', String(mirrorOf('90101', 'gear')[5]) === '41641',
        JSON.stringify(mirrorOf('90101', 'gear')));

  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.ok', u.ok === true, JSON.stringify(u));
  check('undo.cell-back', String(cellOf('90101', C_GEAR)) === '41357', cellOf('90101', C_GEAR));
  check('undo.mirror-back', String(mirrorOf('90101', 'gear')[5]) === '41357',
        JSON.stringify(mirrorOf('90101', 'gear')));
  check('undo.mirror-state', u.mirror && u.mirror.state === 'restored', JSON.stringify(u.mirror));
  check('undo.current_km-untouched', String(mirrorOf('90101', 'gear')[4]) === '41641',
        'пробег — факт о байке, отмена его не трогает');
  check('undo.next_km-recomputed', String(mirrorOf('90101', 'gear')[7]) === '45357',
        JSON.stringify(mirrorOf('90101', 'gear')));
  check('undo.ledger-full', u.ledger && u.ledger.accepted === 3 && u.ledger.done === 3,
        JSON.stringify(u.ledger));
  check('undo.removed-restored', u.removed === 41641 && u.restored_num === 41357, JSON.stringify(u));
  check('undo.address', String(u.full_address).indexOf('J3') >= 0, u.full_address);
  check('undo.verified', u.verified === true, JSON.stringify(u.verified));
  // соседи целы
  check('undo.neighbours', String(cellOf('90303', C_GEAR)) === '10000', cellOf('90303', C_GEAR));

  // след РАСТЁТ, а не переписывается: строка вытеснения на месте, рядом строка отмены
  check('undo.trace-write-kept', logRows('ТО-регистр: вытеснение').length === 1,
        JSON.stringify(logRows('ТО-регистр: вытеснение').length));
  const un = logRows('ТО-регистр: отмена');
  check('undo.trace-undo-added', un.length === 1, JSON.stringify(un.length));
  const urec = un.length ? undoParse_(un[0][3]) : null;
  check('undo.trace-links-act', urec && urec.u === w.act, JSON.stringify(urec));
  check('undo.trace-initiator', un.length && String(un[0][1]) === '@filipp', un.length ? un[0][1] : '');
  check('undo.trace-human', un.length && String(un[0][3]).indexOf('ОТМЕНА акта') >= 0, un.length ? un[0][3] : '');
  check('undo.act-echo', u.undo_act === (urec && urec.a), JSON.stringify([u.undo_act, urec && urec.a]));
}

// ── отмена по маслу (кол.I) — та же дверь ──
{
  reset();
  const w = setFleetOil_({ number: '90202', oil_km: 26000, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90202', 'oil', 26000, 26000, 3000);
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.oil-ok', u.ok === true, JSON.stringify(u));
  check('undo.oil-cell', String(cellOf('90202', C_OIL)) === '24500', cellOf('90202', C_OIL));
  check('undo.oil-mirror', String(mirrorOf('90202', 'oil')[5]) === '24500',
        JSON.stringify(mirrorOf('90202', 'oil')));
}

// ── ПУСТАЯ КЛЕТКА ВОЗВРАЩАЕТСЯ ПУСТОЙ, а не нулём ──
{
  reset();
  const w = setFleetService_({ number: '90202', kind: 'gear', km: 5000, confirmed: true });
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.empty-ok', u.ok === true, JSON.stringify(u));
  check('undo.empty-stays-empty', cellOf('90202', C_GEAR) === '', JSON.stringify(cellOf('90202', C_GEAR)));
}

// ── НЕ-ЧИСЛО В КЛЕТКЕ возвращается дословно ──
{
  reset();
  const w = setFleetService_({ number: '90404', kind: 'gear', km: 7000, confirmed: true });
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.text-ok', u.ok === true, JSON.stringify(u));
  check('undo.text-restored', String(cellOf('90404', C_GEAR)) === 'прочерк', cellOf('90404', C_GEAR));
}

// ── ЗЕРКАЛА НЕТ ВОВСЕ: отмена идёт, несделанное названо поимённо (живьём 3 строки на 38 байков) ──
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.nomirror-ok', u.ok === true, JSON.stringify(u));
  check('undo.nomirror-cell', String(cellOf('90101', C_GEAR)) === '41357', cellOf('90101', C_GEAR));
  check('undo.nomirror-state', u.mirror && u.mirror.state === 'absent', JSON.stringify(u.mirror));
  check('undo.nomirror-named', u.ledger && u.ledger.missing.length === 1 &&
        String(u.ledger.missing[0]).indexOf('gear') >= 0, JSON.stringify(u.ledger));
  check('undo.nomirror-not-created', mirrorOf('90101', 'gear') === null,
        'строку зеркала ради отмены не заводим');
}

// ── ЗЕРКАЛО УЖЕ НА ПРЕЖНЕМ ЧИСЛЕ (его не успели обновить) — не отказ ──
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41357, 4000);
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.mirror-already-ok', u.ok === true, JSON.stringify(u));
  check('undo.mirror-already-state', u.mirror && u.mirror.state === 'already', JSON.stringify(u.mirror));
  check('undo.mirror-already-value', String(mirrorOf('90101', 'gear')[5]) === '41357',
        JSON.stringify(mirrorOf('90101', 'gear')));
}

// ══════════════════ 4. ОТРИЦАТЕЛЬНЫЕ: дверь ОБЯЗАНА отказать ══════════════════

// ── (Н1) СКРУТКА ПОД ВИДОМ ОТМЕНЫ ──────────────────────────────────────────────
{
  // (а) выдуманная ссылка на акт: такого вытеснения мост не помнит
  reset();
  setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  const bogus = serviceUndo_({ act: 'деадбееф0000', by: '@вор', confirmed: true });
  checkNeg('НЕГ.скрутка.выдуманный-акт', bogus.ok === false && bogus.error === 'act_not_found',
           JSON.stringify(bogus));
  checkNeg('НЕГ.скрутка.клетка-цела', String(cellOf('90101', C_GEAR)) === '41641', cellOf('90101', C_GEAR));
  checkNeg('НЕГ.скрутка.следа-отмены-нет', logRows('ТО-регистр: отмена').length === 0,
           JSON.stringify(logRows('ТО-регистр: отмена')));

  // (б) настоящая ссылка + подсунутые снаружи числа: дверь их не принимает ВООБЩЕ
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  const forced = serviceUndo_({ act: w.act, by: '@вор', confirmed: true,
                                km: 100, old_km: 100, new_km: 100, oil_km: 100,
                                restore_to: 100, to: 100, expected: 100, value: 100 });
  checkNeg('НЕГ.скрутка.число-снаружи-проигнорировано',
           forced.ok === true && String(cellOf('90101', C_GEAR)) === '41357',
           JSON.stringify([forced.ok, cellOf('90101', C_GEAR)]));
  checkNeg('НЕГ.скрутка.число-снаружи-не-в-клетке', String(cellOf('90101', C_GEAR)) !== '100',
           cellOf('90101', C_GEAR));
  checkNeg('НЕГ.скрутка.число-снаружи-не-в-зеркале', String(mirrorOf('90101', 'gear')[5]) !== '100',
           JSON.stringify(mirrorOf('90101', 'gear')));

  // (в) скрутка «в лоб» прежней дверью — сторож на месте, ничего не ослаблено
  reset();
  const down = setFleetService_({ number: '90101', kind: 'gear', km: 100, confirmed: true });
  checkNeg('НЕГ.скрутка.в-лоб-отказ', down.ok === false && down.error === 'km_decreasing', JSON.stringify(down));
  checkNeg('НЕГ.скрутка.в-лоб-клетка-цела', String(cellOf('90101', C_GEAR)) === '41357', cellOf('90101', C_GEAR));
  checkNeg('НЕГ.скрутка.в-лоб-памяти-нет', logRows('ТО-регистр: вытеснение').length === 0,
           'отказанная запись ничего не вытеснила — памяти о ней быть не должно');

  // (г) отмена без confirmed — живая таблица без подтверждения не правится
  reset();
  const w2 = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  const nc = serviceUndo_({ act: w2.act, by: '@filipp' });
  checkNeg('НЕГ.скрутка.без-confirmed', nc.ok === false && nc.error === 'not_confirmed', JSON.stringify(nc));
  checkNeg('НЕГ.скрутка.без-confirmed-клетка-цела', String(cellOf('90101', C_GEAR)) === '41641',
           cellOf('90101', C_GEAR));

  // (д) ссылки нет вовсе
  const na = serviceUndo_({ by: '@filipp', confirmed: true });
  checkNeg('НЕГ.скрутка.без-ссылки', na.ok === false && na.error === 'need_act', JSON.stringify(na));
}

// ── (Н2) КЛЕТКУ МЕЖДУ ДЕЛОМ ИЗМЕНИЛ ТРЕТИЙ ────────────────────────────────────
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  fleetSheet.grid[2][C_GEAR - 1] = 41999;                       // чужая рука в живой таблице
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.третий.отказ', u.ok === false && u.error === 'cell_changed', JSON.stringify(u));
  checkNeg('НЕГ.третий.клетка-не-затёрта', String(cellOf('90101', C_GEAR)) === '41999', cellOf('90101', C_GEAR));
  checkNeg('НЕГ.третий.зеркало-не-тронуто', String(mirrorOf('90101', 'gear')[5]) === '41641',
           JSON.stringify(mirrorOf('90101', 'gear')));
  checkNeg('НЕГ.третий.назван-найденный', u.found === 41999 && u.expected === 41641, JSON.stringify(u));
  checkNeg('НЕГ.третий.следа-отмены-нет', logRows('ТО-регистр: отмена').length === 0,
           JSON.stringify(logRows('ТО-регистр: отмена')));
  // БЛИЗНЕЦ ОТКАЗА: тот же акт, та же дверь, но чужой руки не было — отмена проходит.
  // Без этой пары отрицательный тест мог бы зеленеть по любой другой причине.
  fleetSheet.grid[2][C_GEAR - 1] = 41641;
  const twin = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.третий.близнец-проходит', twin.ok === true && String(cellOf('90101', C_GEAR)) === '41357',
        JSON.stringify([twin.ok, cellOf('90101', C_GEAR)]));

  // подслучай живого 5960: клетку УЖЕ вернули рукой — отменять нечего, зовём владельца
  reset();
  const w2 = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  fleetSheet.grid[2][C_GEAR - 1] = 41357;
  const u2 = serviceUndo_({ act: w2.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.рукой.отказ', u2.ok === false && u2.error === 'cell_already_at_old', JSON.stringify(u2));
  checkNeg('НЕГ.рукой.клетка-цела', String(cellOf('90101', C_GEAR)) === '41357', cellOf('90101', C_GEAR));
}

// ── (Н3) ОТМЕНА НЕ ПОСЛЕДНЕЙ ЗАПИСИ ───────────────────────────────────────────
{
  reset();
  const first = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  const second = setFleetService_({ number: '90101', kind: 'gear', km: 42000, confirmed: true });
  const u = serviceUndo_({ act: first.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.непоследняя.отказ', u.ok === false && u.error === 'not_last', JSON.stringify(u));
  checkNeg('НЕГ.непоследняя.назван-новее', u.newer_act === second.act, JSON.stringify(u));
  checkNeg('НЕГ.непоследняя.клетка-цела', String(cellOf('90101', C_GEAR)) === '42000', cellOf('90101', C_GEAR));

  // последняя — отменяется, и после неё первая по-прежнему НЕ отменяется
  const uOk = serviceUndo_({ act: second.act, by: '@filipp', confirmed: true });
  check('undo.последняя-проходит', uOk.ok === true && String(cellOf('90101', C_GEAR)) === '41641',
        JSON.stringify([uOk.ok, cellOf('90101', C_GEAR)]));
  const again = serviceUndo_({ act: first.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.непоследняя.после-отмены-тоже', again.ok === false && again.error === 'not_last',
           JSON.stringify(again));

  // чужая колонка того же байка отмене не мешает: пара «байк × колонка», а не байк
  reset();
  const gear = setFleetService_({ number: '90303', kind: 'gear', km: 20000, confirmed: true });
  setFleetService_({ number: '90303', kind: 'abs', km: 21000, confirmed: true });
  const uG = serviceUndo_({ act: gear.act, by: '@filipp', confirmed: true });
  check('undo.другая-колонка-не-мешает', uG.ok === true && String(cellOf('90303', C_GEAR)) === '10000',
        JSON.stringify([uG.ok, cellOf('90303', C_GEAR)]));
}

// ── (Н4) ОТМЕНА ОТМЕНЫ ────────────────────────────────────────────────────────
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.первая-отмена-ok', u.ok === true, JSON.stringify(u));

  const undoOfUndo = serviceUndo_({ act: u.undo_act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.отмена-отмены.отказ', undoOfUndo.ok === false && undoOfUndo.error === 'undo_of_undo',
           JSON.stringify(undoOfUndo));
  checkNeg('НЕГ.отмена-отмены.клетка-цела', String(cellOf('90101', C_GEAR)) === '41357',
           cellOf('90101', C_GEAR));

  const twice = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.повторная-отмена.отказ', twice.ok === false && twice.error === 'already_undone',
           JSON.stringify(twice));
  checkNeg('НЕГ.повторная-отмена.назван-откат', twice.undo_act === u.undo_act, JSON.stringify(twice));
  checkNeg('НЕГ.отмена-отмены.зеркало-цело', String(mirrorOf('90101', 'gear')[5]) === '41357',
           JSON.stringify(mirrorOf('90101', 'gear')));
  checkNeg('НЕГ.отмена-отмены.следов-ровно-два',
           logRows('ТО-регистр: отмена').length === 1 && logRows('ТО-регистр: вытеснение').length === 1,
           JSON.stringify(logSheet.grid.slice(1).map(r => r[2])));
}

// ── (Н5) ВТОРАЯ БАЗА НЕДОСТУПНА НА СЕРЕДИНЕ ──────────────────────────────────
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  svcBroken = true;                                    // зеркало отваливается ПОСЛЕ записи Лист1
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  svcBroken = false;
  checkNeg('НЕГ.вторая-база.отказ', u.ok === false && u.error === 'mirror_unavailable', JSON.stringify(u));
  checkNeg('НЕГ.вторая-база.первая-компенсирована', u.compensated === true &&
           String(cellOf('90101', C_GEAR)) === '41641', JSON.stringify([u.compensated, cellOf('90101', C_GEAR)]));
  checkNeg('НЕГ.вторая-база.зеркало-как-было', String(mirrorOf('90101', 'gear')[5]) === '41641',
           JSON.stringify(mirrorOf('90101', 'gear')));
  checkNeg('НЕГ.вторая-база.ledger-ноль', u.ledger && u.ledger.done === 0, JSON.stringify(u.ledger));
  checkNeg('НЕГ.вторая-база.следа-отмены-нет', logRows('ТО-регистр: отмена').length === 0,
           JSON.stringify(logRows('ТО-регистр: отмена')));
  // акт НЕ считается отменённым: после починки зеркала отмена проходит штатно
  const retry = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.после-починки-проходит', retry.ok === true && String(cellOf('90101', C_GEAR)) === '41357',
        JSON.stringify([retry.ok, cellOf('90101', C_GEAR)]));

  // подслучай: зеркало держит ЧУЖОЕ число — тоже отказ целиком
  reset();
  const w2 = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 40000, 4000);
  const u2 = serviceUndo_({ act: w2.act, by: '@filipp', confirmed: true });
  checkNeg('НЕГ.зеркало-чужое.отказ', u2.ok === false && u2.error === 'mirror_changed', JSON.stringify(u2));
  checkNeg('НЕГ.зеркало-чужое.первая-компенсирована', String(cellOf('90101', C_GEAR)) === '41641',
           cellOf('90101', C_GEAR));
  checkNeg('НЕГ.зеркало-чужое.зеркало-не-затёрто', String(mirrorOf('90101', 'gear')[5]) === '40000',
           JSON.stringify(mirrorOf('90101', 'gear')));
}

// ── (Н6) СЛЕД ОТМЕНЫ НЕ ЗАПИСАЛСЯ: обе базы возвращаются в состояние «при входе» ──
{
  reset();
  const w = setFleetService_({ number: '90101', kind: 'gear', km: 41641, confirmed: true });
  mirrorAfterAct('ТЕСТ-БАЙК 90101', 'gear', 41641, 41641, 4000);
  logSheet.appendBroken = true;                        // читать журнал можно, дописывать — нет
  const u = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  logSheet.appendBroken = false;
  checkNeg('НЕГ.след-отмены.отказ', u.ok === false && u.error === 'undo_audit_failed', JSON.stringify(u));
  checkNeg('НЕГ.след-отмены.клетка-как-была', String(cellOf('90101', C_GEAR)) === '41641',
           cellOf('90101', C_GEAR));
  checkNeg('НЕГ.след-отмены.зеркало-как-было', String(mirrorOf('90101', 'gear')[5]) === '41641',
           JSON.stringify(mirrorOf('90101', 'gear')));
  checkNeg('НЕГ.след-отмены.обе-компенсации-названы',
           u.compensated === true && u.mirror_compensated === true, JSON.stringify(u));
  // БЛИЗНЕЦ ОТКАЗА: журнал починился — тот же акт отменяется штатно, обе базы возвращаются.
  const twin = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('undo.след-отмены.близнец-проходит',
        twin.ok === true && String(cellOf('90101', C_GEAR)) === '41357' &&
        String(mirrorOf('90101', 'gear')[5]) === '41357',
        JSON.stringify([twin.ok, cellOf('90101', C_GEAR), mirrorOf('90101', 'gear')[5]]));
}

// ══════════════════════════ 5. РЕГРЕСС: прежние двери не ослаблены ══════════════════════════
{
  reset();
  const up = setFleetService_({ number: '90101', kind: 'gear', km: 45000, confirmed: true });
  check('regress.рост-проходит', up.ok === true && String(cellOf('90101', C_GEAR)) === '45000', JSON.stringify(up));
  const nc = setFleetService_({ number: '90101', kind: 'gear', km: 46000 });
  check('regress.not_confirmed', nc.ok === false && nc.error === 'not_confirmed', JSON.stringify(nc));
  const nf = setFleetService_({ number: '99999', kind: 'gear', km: 46000, confirmed: true });
  check('regress.not_found', nf.ok === false && nf.error === 'not_found', JSON.stringify(nf));
  const amb = setFleetService_({ number: '90505', kind: 'gear', km: 46000, confirmed: true });
  check('regress.ambiguous', amb.ok === false && amb.error === 'ambiguous', JSON.stringify(amb));
  const bk = setFleetService_({ number: '90101', kind: 'gearbox', km: 46000, confirmed: true });
  check('regress.bad_kind', bk.ok === false && bk.error === 'bad_kind', JSON.stringify(bk));
  const oilDown = setFleetOil_({ number: '90202', oil_km: 100, confirmed: true });
  check('regress.масло-понижение-без-причины', oilDown.ok === false && oilDown.error === 'oil_decreasing',
        JSON.stringify(oilDown));
  // отмена не резолвится на неоднозначном байке
  reset();
  const w = setFleetService_({ number: '90303', kind: 'gear', km: 20000, confirmed: true });
  fleetSheet.grid[4][2] = 'ТЕСТ-ДУБЛЬ 90505';          // ломаем однозначность ПОСЛЕ записи
  fleetSheet.grid[4][C_GEAR - 1] = 20000;
  const uAmb = serviceUndo_({ act: w.act, by: '@filipp', confirmed: true });
  check('regress.отмена-не-найдя-байка', uAmb.ok === false && uAmb.error === 'not_found',
        JSON.stringify(uAmb));
}

// ── ВЕТКА ИСПРАВЛЕНИЯ МАСЛА НА СБОРКЕ: свод tests/fleetfix_gs_harness.js ──────────────
// Тот харнесс судит ЗЕРКАЛО (задеплоенную версию) и после выкладки накроет этот код сам.
// Пока сборка не выложена, её копию ветки исправления обязан покрыть этот файл — иначе
// «не ослаблено» держалось бы на глаз.
{
  reset();
  const plain = setFleetOil_({ number: '90202', oil_km: 24000, confirmed: true });
  check('fix.без-причины-отказ', plain.ok === false && plain.error === 'oil_decreasing', JSON.stringify(plain));
  const half = setFleetOil_({ number: '90202', oil_km: 24000, confirmed: true, fix_reason: 'r' });
  check('fix.полумера-отказ', half.ok === false && half.error === 'oil_decreasing', JSON.stringify(half));
  check('fix.клетка-цела', String(cellOf('90202', C_OIL)) === '24500', cellOf('90202', C_OIL));

  reset();
  const ok = setFleetOil_({ number: '90202', oil_km: 24000, confirmed: true,
                            fix_reason: 'ошибка распознавания', fixed_by: '@filipp' });
  check('fix.причина+автор-проходит', ok.ok === true && String(cellOf('90202', C_OIL)) === '24000',
        JSON.stringify(ok));
  check('fix.rollback_oil-назван', ok.rollback_oil === 24500, JSON.stringify(ok.rollback_oil));

  reset();
  const big = setFleetOil_({ number: '90202', oil_km: 20000, confirmed: true,
                             fix_reason: 'чужой пробег', fixed_by: '@earth' });
  check('fix.больше-500-нужен-доверенный', big.ok === false && big.error === 'oil_drop_needs_trusted',
        JSON.stringify(big));
  check('fix.больше-500-клетка-цела', String(cellOf('90202', C_OIL)) === '24500', cellOf('90202', C_OIL));

  reset();
  logSheet.appendBroken = true;
  const noAudit = setFleetOil_({ number: '90202', oil_km: 24000, confirmed: true,
                                 fix_reason: 'ошибка', fixed_by: '@filipp' });
  logSheet.appendBroken = false;
  check('fix.след-обязателен', noAudit.ok === false && noAudit.error === 'audit_failed', JSON.stringify(noAudit));
  check('fix.след-обязателен-откачено', noAudit.rolled_back === true &&
        String(cellOf('90202', C_OIL)) === '24500', JSON.stringify([noAudit.rolled_back, cellOf('90202', C_OIL)]));
}

console.log(JSON.stringify({ cases, negatives }));
process.exit(cases.some(c => !c.pass) ? 1 : 0);
