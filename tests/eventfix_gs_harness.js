'use strict';
/**
 * Харнесс «правка строки события НА МЕСТЕ»: исполняет РЕАЛЬНЫЙ
 * bridge_prod/BotData.js в node с мок-SpreadsheetApp/PropertiesService
 * (схема botdata_gs_harness.js / booking_gs_harness.js).
 *
 * Фокус — то, чего до 04.08.2026 в мосте НЕ БЫЛО ВОВСЕ: действие правки строки листа
 * «события» без удаления и пересоздания. Проверяем ровно те инварианты, которые делают
 * правку пригодной для починки данных с телефона:
 *   1. МЕТКА ВРЕМЕНИ ЗАПИСИ (recorded_at, кол.A) сохраняется — правка не переписывает историю;
 *   2. КЛЮЧ приводится в соответствие содержимому (синтетический контентный ключ вида
 *      info:<номер>:<работа>:<км> обязан меняться вместе с числом, иначе дедуп моста будет
 *      сверять строку по неверному отпечатку);
 *   3. точный ключ обязателен, ровно одно совпадение, конфликт нового ключа — отказ;
 *   4. АУДИТ-СЛЕД: что было, что стало, кто исправил — В САМОЙ СТРОКЕ (кол. notes/status),
 *      плюс строка в боевой_лог; ответ несёт before/after и готовый ОТКАТ.
 *
 * Живой формат листа снят с BOTDATA.EVENT_HEADERS (12 колонок, sender последней) и с
 * addEvent(): recorded_at = new Date().toISOString(), mileage хранится как ЧИСЛО либо
 * пустая строка, msg_id — строка (телеграм-ключ либо синтетический контентный).
 *
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_record_fix.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// Источник .js — ЗЕРКАЛО ПРОДА `bridge_prod/` в этом репо (задеплоенная версия, паспорт
// MIRROR.json). Рабочая папка /root/turbobaby-bridge-gs обезврежена 10.08.2026 и ОТСТАЁТ от
// прода — харнесс, читающий её, проверял бы не тот код, что живёт в мосте.
const GS_DIR = path.join(__dirname, '..', 'bridge_prod');
const BOTDATA_JS = path.join(GS_DIR, 'BotData.js');

// ── мок листа поверх 2D-массива (1-indexed строки/колонки как в Apps Script) ──
function makeSheet(rows) {
  const WIDTH = 30;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  const sheet = {
    grid,
    getName() { return 'мок'; },
    getParent() { return { getId() { return 'fake-botdata-id'; } }; },
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
          getA1Notation() { return 'R' + a + 'C' + b; },
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
        getA1Notation() { return 'R' + a + 'C' + b + ':R' + (a + c - 1) + 'C' + (b + d - 1); },
      };
    },
    deleteRow(n) { grid.splice(n - 1, 1); },
    deleteRows(start, n) { grid.splice(start - 1, n); },
    setFrozenRows() {},
  };
  return sheet;
}

const EVENT_HEADERS = [
  'recorded_at', 'msg_date', 'group', 'bike', 'event_type',
  'fuel', 'mileage', 'photos', 'notes', 'status', 'msg_id', 'sender',
];

// ЖИВОЙ СЛУЧАЙ: NMAX 155 GREEN-B 4957, строка 29.07 09:32:15 несёт 38982 вместо 36982.
// Ключ синтетический контентный (форма splinter: info:<номер>:<работа>:<км>).
const REC_AT = '2026-07-29T09:32:15.000Z';
function freshEvents() {
  return makeSheet([
    EVENT_HEADERS.slice(),
    ['2026-07-28T10:00:00.000Z', '2026-07-28', 'Обслуживание', 'NMAX 155 GREEN-B PHUKET 4957',
     'repair', '', 30800, 0, 'замена масла', 'recorded', 'info:4957:oil:30800', '@earth'],
    [REC_AT, '2026-07-29', 'Обслуживание', 'NMAX 155 GREEN-B PHUKET 4957',
     'repair', '', 38982, 0, 'моторное масло — 38982 км', 'recorded', 'info:4957:oil:38982', '@earth'],
    ['2026-07-30T11:00:00.000Z', '2026-07-30', 'Обслуживание', 'ADV 160 8004',
     'repair', '', 12000, 0, 'колодки перед', 'recorded', 'info:8004:pads:12000', '@earth'],
  ]);
}

let evSheet = freshEvents();
let logSheet = makeSheet([['ts', 'initiator', 'action', 'args', 'result', 'critical']]);
const sheets = {};
function wire() {
  sheets['события'] = evSheet;
  sheets['боевой_лог'] = logSheet;
}
wire();

global.SpreadsheetApp = {
  openById: () => ({ getSheetByName: n => sheets[n] || null, getSheets: () => [], getId: () => 'fake-botdata-id' }),
  flush: () => {},
};
global.PropertiesService = { getScriptProperties: () => ({ getProperty: () => 'fake-botdata-id', setProperty: () => {} }) };
global.Logger = { log: () => {} };

vm.runInThisContext(fs.readFileSync(BOTDATA_JS, 'utf8'), { filename: BOTDATA_JS });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function reset() { evSheet = freshEvents(); logSheet = makeSheet([['ts', 'initiator', 'action', 'args', 'result', 'critical']]); wire(); }
function rowOf(key) {
  for (let i = 1; i < evSheet.grid.length; i++) if (String(evSheet.grid[i][10]) === key) return evSheet.grid[i];
  return null;
}

// ── 0. действие вообще существует ──
check('exists.editEvent', typeof editEvent === 'function', typeof editEvent);
if (typeof editEvent !== 'function') {
  console.log(JSON.stringify({ cases }));
  process.exit(1);
}

// ── 1. ЖИВОЙ СЛУЧАЙ: правка на месте, метка времени записи сохраняется ──
{
  reset();
  const before = rowOf('info:4957:oil:38982').slice();
  const r = editEvent({
    msg_id: 'info:4957:oil:38982',
    fields: { mileage: 36982, notes: 'моторное масло — 36982 км' },
    new_msg_id: 'info:4957:oil:36982',
    reason: 'ошибка распознавания одометра, механик отклонил 29.07',
    fixed_by: '@filipp', confirmed: true,
  });
  check('fix.ok', r.ok === true, JSON.stringify(r));
  const after = rowOf('info:4957:oil:36982');
  check('fix.row-alive', after !== null, 'строка найдена по НОВОМУ ключу');
  check('fix.recorded_at-kept', after && String(after[0]) === REC_AT,
        after ? String(after[0]) + ' (было ' + REC_AT + ')' : 'нет строки');
  check('fix.mileage-new', after && String(after[6]) === '36982', after ? after[6] : '');
  check('fix.old-key-gone', rowOf('info:4957:oil:38982') === null, 'старого ключа больше нет');
  check('fix.no-new-row', evSheet.getLastRow() === 4, evSheet.getLastRow());   // шапка + 3 строки, как было
  check('fix.before-echo', r.before && String(r.before.mileage) === '38982', JSON.stringify(r.before));
  check('fix.after-echo', r.after && String(r.after.mileage) === '36982', JSON.stringify(r.after));
  check('fix.key-echo', r.key && r.key.old === 'info:4957:oil:38982' && r.key.new === 'info:4957:oil:36982',
        JSON.stringify(r.key));
  check('fix.rollback-given', !!(r.rollback && String(r.rollback.fields.mileage) === '38982'),
        JSON.stringify(r.rollback));
  // соседние строки не тронуты
  check('fix.neighbour-intact', String(evSheet.grid[1][6]) === '30800' && String(evSheet.grid[3][6]) === '12000',
        evSheet.grid[1][6] + '/' + evSheet.grid[3][6]);
  void before;
}

// ── 2. АУДИТ-СЛЕД: что было, что стало, кто исправил ──
{
  reset();
  const r = editEvent({
    msg_id: 'info:4957:oil:38982', fields: { mileage: 36982 },
    new_msg_id: 'info:4957:oil:36982',
    reason: 'ошибка OCR', fixed_by: '@filipp', confirmed: true,
  });
  const after = rowOf('info:4957:oil:36982');
  const notes = after ? String(after[8]) : '';
  check('audit.in-row', notes.indexOf('36982') >= 0 && notes.indexOf('38982') >= 0,
        notes);
  check('audit.who-in-row', notes.indexOf('@filipp') >= 0, notes);
  check('audit.reason-in-row', notes.indexOf('ошибка OCR') >= 0, notes);
  check('audit.status', after && String(after[9]) === 'corrected', after ? after[9] : '');
  check('audit.changes-echo', Array.isArray(r.audit && r.audit.changes) && r.audit.changes.length >= 1,
        JSON.stringify(r.audit));
  check('audit.by-echo', r.audit && r.audit.by === '@filipp', JSON.stringify(r.audit));
  // строка в боевой_лог
  const logged = logSheet.grid.slice(1).filter(x => String(x[2]).indexOf('edit_event') >= 0);
  check('audit.writelog', logged.length === 1, JSON.stringify(logged));
  check('audit.writelog-args', logged.length === 1 && String(logged[0][3]).indexOf('38982') >= 0
        && String(logged[0][3]).indexOf('36982') >= 0, logged.length ? logged[0][3] : '');
}

// ── 3. ОТКАТ той же правкой: before возвращает строку к исходному ──
{
  reset();
  const fix = editEvent({
    msg_id: 'info:4957:oil:38982', fields: { mileage: 36982, notes: 'моторное масло — 36982 км' },
    new_msg_id: 'info:4957:oil:36982', reason: 'ошибка OCR', fixed_by: '@filipp', confirmed: true,
  });
  const back = editEvent({
    msg_id: fix.rollback.msg_id, fields: fix.rollback.fields,
    new_msg_id: fix.rollback.new_msg_id, reason: 'откат правки', fixed_by: '@filipp', confirmed: true,
  });
  check('rollback.ok', back.ok === true, JSON.stringify(back));
  const row = rowOf('info:4957:oil:38982');
  check('rollback.mileage', row && String(row[6]) === '38982', row ? row[6] : 'нет строки');
  check('rollback.recorded_at-kept', row && String(row[0]) === REC_AT, row ? row[0] : '');
}

// ── 4. ГРАНИЦЫ: без ключа / без причины / без автора / без подтверждения — отказ и НИЧЕГО не тронуто ──
{
  const guards = [
    ['no_key', { fields: { mileage: 1 }, reason: 'r', fixed_by: 'b', confirmed: true }],
    ['no_reason', { msg_id: 'info:4957:oil:38982', fields: { mileage: 1 }, fixed_by: 'b', confirmed: true }],
    ['no_author', { msg_id: 'info:4957:oil:38982', fields: { mileage: 1 }, reason: 'r', confirmed: true }],
    ['not_confirmed', { msg_id: 'info:4957:oil:38982', fields: { mileage: 1 }, reason: 'r', fixed_by: 'b' }],
  ];
  for (const [want, payload] of guards) {
    reset();
    const r = editEvent(payload);
    check('guard.' + want, r.ok === false && r.error === want, JSON.stringify(r));
    check('guard.' + want + '.untouched', String(rowOf('info:4957:oil:38982')[6]) === '38982',
          'строка не тронута');
  }
}

// ── 5. МЕТКУ ВРЕМЕНИ ЗАПИСИ ПРАВИТЬ НЕЛЬЗЯ ВООБЩЕ (белый список полей) ──
{
  reset();
  const r = editEvent({
    msg_id: 'info:4957:oil:38982', fields: { recorded_at: '2020-01-01T00:00:00.000Z' },
    reason: 'r', fixed_by: 'b', confirmed: true,
  });
  check('whitelist.recorded_at-refused', r.ok === false && r.error === 'bad_field', JSON.stringify(r));
  check('whitelist.recorded_at-intact', String(rowOf('info:4957:oil:38982')[0]) === REC_AT,
        rowOf('info:4957:oil:38982')[0]);
  const r2 = editEvent({
    msg_id: 'info:4957:oil:38982', fields: { msg_id: 'подмена' },
    reason: 'r', fixed_by: 'b', confirmed: true,
  });
  check('whitelist.msg_id-refused', r2.ok === false && r2.error === 'bad_field', JSON.stringify(r2));
  const r3 = editEvent({
    msg_id: 'info:4957:oil:38982', fields: { чужое: 1 }, reason: 'r', fixed_by: 'b', confirmed: true,
  });
  check('whitelist.unknown-refused', r3.ok === false && r3.error === 'bad_field', JSON.stringify(r3));
}

// ── 6. НЕ НАШЁЛ / НЕОДНОЗНАЧНО / КОНФЛИКТ КЛЮЧА ──
{
  reset();
  const r = editEvent({ msg_id: 'нет-такого', fields: { mileage: 1 }, reason: 'r', fixed_by: 'b', confirmed: true });
  check('miss.not_found', r.ok === false && r.error === 'not_found', JSON.stringify(r));

  reset();
  // два ряда с ОДНИМ ключом (так бывает у строк без свидетеля — до правила обязательного ключа)
  evSheet.appendRow([REC_AT, '2026-07-29', 'Обслуживание', 'NMAX 155 GREEN-B PHUKET 4957',
                     'repair', '', 38982, 0, 'дубль', 'recorded', 'info:4957:oil:38982', '@earth']);
  const r2 = editEvent({ msg_id: 'info:4957:oil:38982', fields: { mileage: 36982 },
                         reason: 'r', fixed_by: 'b', confirmed: true });
  check('miss.ambiguous', r2.ok === false && r2.error === 'ambiguous' && r2.matched === 2, JSON.stringify(r2));
  check('miss.ambiguous.untouched', String(evSheet.grid[2][6]) === '38982' && String(evSheet.grid[4][6]) === '38982',
        'обе строки целы');
  // group сужает до одной — но здесь group у обеих одинаковая, значит по-прежнему отказ (не угадываем)
  const r3 = editEvent({ msg_id: 'info:4957:oil:38982', group: 'Обслуживание', fields: { mileage: 36982 },
                         reason: 'r', fixed_by: 'b', confirmed: true });
  check('miss.ambiguous-with-group', r3.ok === false && r3.error === 'ambiguous', JSON.stringify(r3));

  reset();
  const r4 = editEvent({ msg_id: 'info:4957:oil:38982', fields: { mileage: 30800 },
                         new_msg_id: 'info:4957:oil:30800',   // такой ключ УЖЕ занят соседней строкой
                         reason: 'r', fixed_by: 'b', confirmed: true });
  check('miss.key_conflict', r4.ok === false && r4.error === 'key_conflict', JSON.stringify(r4));
  check('miss.key_conflict.untouched', String(rowOf('info:4957:oil:38982')[6]) === '38982', 'строка цела');

  reset();
  const r5 = editEvent({ msg_id: 'info:4957:oil:38982', fields: {}, reason: 'r', fixed_by: 'b', confirmed: true });
  check('miss.nothing_to_change', r5.ok === false && r5.error === 'nothing_to_change', JSON.stringify(r5));
}

// ── 7. group как ДОП. сужение (та же дисциплина точного ключа, что у удаления) ──
{
  reset();
  const r = editEvent({ msg_id: 'info:4957:oil:38982', group: 'Money Cashflow', fields: { mileage: 36982 },
                        reason: 'r', fixed_by: 'b', confirmed: true });
  check('group.narrow-miss', r.ok === false && r.error === 'not_found', JSON.stringify(r));
  const r2 = editEvent({ msg_id: 'info:4957:oil:38982', group: 'Обслуживание', fields: { mileage: 36982 },
                         new_msg_id: 'info:4957:oil:36982', reason: 'r', fixed_by: 'b', confirmed: true });
  check('group.narrow-hit', r2.ok === true, JSON.stringify(r2));
}

// ── 8. РЕГРЕСС соседей: добавление/удаление/чтение событий работают как прежде ──
{
  reset();
  const add = addEvent({ msg_date: '2026-08-04', group: 'Обслуживание', bike: 'NMAX 4957',
                         event_type: 'repair', mileage: 37100, notes: 'проверка', msg_id: 'tg:1:2' });
  check('regress.addEvent', add.ok === true && add.saved === true, JSON.stringify(add));
  const dup = addEvent({ msg_date: '2026-08-04', group: 'Обслуживание', bike: 'NMAX 4957',
                         event_type: 'repair', mileage: 37100, notes: 'проверка', msg_id: 'tg:1:2' });
  check('regress.addEvent-dedup', dup.duplicate === true, JSON.stringify(dup));
  const del = deleteEvent({ msg_id: 'tg:1:2' });
  check('regress.deleteEvent', del.ok === true && del.deleted === 1, JSON.stringify(del));
  const noKey = deleteEvent({});
  check('regress.deleteEvent-nokey', noKey.ok === false && noKey.error === 'no_key', JSON.stringify(noKey));
}

// ── 9. ЧТЕНИЕ ИСТОРИИ ОТДАЁТ КЛЮЧ — иначе адресовать правку нечем ──
{
  reset();
  const ev = readEvents({ bike: 'NMAX 155 GREEN-B PHUKET 4957', limit: 8 });
  check('read.ok', ev.ok === true && ev.items.length === 2, JSON.stringify(ev.items.length));
  const it = ev.items[0];   // newest-first → строка 29.07
  check('read.msg_id', it && it.msg_id === 'info:4957:oil:38982', JSON.stringify(it));
  check('read.status', it && it.status === 'recorded', JSON.stringify(it));
  check('read.group', it && it.group === 'Обслуживание', JSON.stringify(it));
  // прежние поля на месте (карточка байка их читает)
  check('read.legacy-fields', it && it.recorded_at === REC_AT && it.mileage === '38982'
        && it.event_type === 'repair' && typeof it.notes === 'string', JSON.stringify(it));
}

console.log(JSON.stringify({ cases }));
process.exit(cases.some(c => !c.pass) ? 1 : 0);
