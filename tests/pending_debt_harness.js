'use strict';
/**
 * Харнесс «ПОЗИЦИОННЫЙ ДОЛГ»: исполняет РЕАЛЬНЫЙ код моста (`bridge_prod/ServicePending.js`,
 * задеплоенная версия — паспорт MIRROR.json) в node с мок-SpreadsheetApp; схема
 * undo_door_harness.js. МОСТ НЕ ПРАВИТСЯ И НЕ ВЫКЛАДЫВАЕТСЯ — харнесс не проверяет наше
 * лечение, он проверяет СВОЙСТВА МИРА, на которых лечение стоит. Лечится всё на стороне
 * `splinter`, и вот почему это ЕДИНСТВЕННЫЙ доступный путь:
 *
 *   1. НОСИТЕЛЬ. Визит того же байка (`_sp_advance_to_confirm`) передаёт declared/done/odometer/
 *      status и НЕ передаёт `note` → `pick` берёт ноту из `cur`, и она ПЕРЕЖИВАЕТ визит. Ровно
 *      поэтому позиции долга переехали в ноту, а не остались на полях.
 *   2. ПОЧЕМУ НЕ ПОЛЯ. Тот же визит поля ЗАТИРАЕТ: `abs,pads@41357` становится `gear@41641` в ТОЙ
 *      ЖЕ строке. Это дословная судьба живого 5960 (01.08 → 22.08).
 *   3. ДЫРА ЭХА. `servicePendingClose_` — это upsert: НЕ НАЙДЯ открытой строки, мост ДОПИСЫВАЕТ
 *      новую (`saved`, declared и done пусты). Значит «не закрывать, когда закрывать нечего»
 *      может решить только вызывающий — забор обязан стоять в питоне.
 *   4. ДЫРА ЧУЖОЙ СТРОКИ. Закрытие гасит ЛЮБУЮ открытую строку пары чат×тема×байк — мост не
 *      спрашивает, чья работа в ней записана. Значит «своё/чужое» тоже решает вызывающий.
 *   5. ПУСТАЯ НОТА НЕ СТИРАЕТ. `p.note === ''` мост читает как «поле не передали» → сказать
 *      листу «позиций больше нет» можно только НЕПУСТЫМ словом. Отсюда `DEBT:{}`.
 *
 * У каждой отрицательной проверки есть близнец «то же без порчи — проходит».
 * БАЙКИ ВЫДУМАНЫ (`TESTBIKE FAKE …` — таких в парке нет), в Google не ходим, живых данных нет.
 * Печатает JSON {cases:[{name, pass, detail}], negatives}; exit 1, если есть провалы.
 * Запускается из tests/test_service_debt.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// Источник — ЗЕРКАЛО ПРОДА. Обезвреженная папка выкладки отстаёт от прода и источником не является.
const GS_DIR = path.join(__dirname, '..', 'bridge_prod');

const HDR = ['created_at', 'updated_at', 'chat_id', 'topic_id', 'bike', 'declared', 'done',
  'status', 'odometer', 'last_reminded_at', 'note'];
const WIDTH = 20;

function makeSheet(name, rows) {
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  return {
    grid,
    getName() { return name; },
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    getLastColumn() { return WIDTH; },
    appendRow(arr) { const a = arr.slice(); while (a.length < WIDTH) a.push(''); grid.push(a); },
    getRange(a, b, c, d) {
      if (c === undefined) {
        return {
          setValue(v) { ensureRow(a); grid[a - 1][b - 1] = v; },
          getValue() { ensureRow(a); return grid[a - 1][b - 1]; },
          setValues(vv) { ensureRow(a); for (let j = 0; j < vv[0].length; j++) grid[a - 1][b - 1 + j] = vv[0][j]; },
        };
      }
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) { ensureRow(r); out.push(grid[r - 1].slice(b - 1, b - 1 + d)); }
          return out;
        },
        setValues(vv) {
          for (let r = 0; r < vv.length; r++) {
            ensureRow(a + r);
            for (let j = 0; j < vv[r].length; j++) grid[a + r - 1][b - 1 + j] = vv[r][j];
          }
        },
        setFontWeight() { return this; },
        setBackground() { return this; },
      };
    },
    setFrozenRows() {},
  };
}

let spSheet = makeSheet('то_заявки', [HDR.slice()]);

global.SpreadsheetApp = {
  openById: (id) => ({
    getSheetByName: (n) => (n === 'то_заявки' ? spSheet : null),
    insertSheet: (n) => { spSheet = makeSheet(n, [HDR.slice()]); return spSheet; },
    getSheets: () => [spSheet],
    getId: () => String(id),
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
global.Utilities = { getUuid: () => 'ТЕСТ-uuid', formatDate: (d) => String(d) };
global.Session = { getScriptTimeZone: () => 'UTC' };
global.CacheService = {
  getScriptCache: () => ({ get: () => null, put: () => {}, remove: () => {} }),
};

for (const f of ['Config.js', 'BotData.js', 'ReadFleet.js', 'ServicePending.js'])
  vm.runInThisContext(fs.readFileSync(path.join(GS_DIR, f), 'utf8'),
    { filename: path.join(GS_DIR, f) });

const cases = [];
let negatives = 0;
function check(name, cond, detail) {
  cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) });
}
/** Отрицательная: мир ОБЯЗАН вести себя так, как утверждает лечение. Считается отдельно. */
function checkNeg(name, cond, detail) { negatives += 1; check(name, cond, detail); }

const CHAT = '-100777000111';
const TOPIC = '90901';
const BIKE = 'TESTBIKE FAKE 0001';
const OTHER = 'TESTBIKE FAKE 0002';
const DEBT = 'DEBT:{abs@41357; pads@41357}';

function reset() { spSheet = makeSheet('то_заявки', [HDR.slice()]); }
function rows() { return spSheet.grid.slice(1).filter(r => String(r[4] || '').trim() !== ''); }
function row1() { const r = rows()[0] || []; const o = {}; HDR.forEach((h, i) => { o[h] = r[i]; }); return o; }

// ── 1. НОСИТЕЛЬ: визит соседа НЕ передаёт ноту → мост сохраняет её из cur ───────────────────
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, declared: 'abs,pads',
  done: 'abs,pads', odometer: '41357', status: 'ждёт_подтверждения', note: DEBT });
check('carrier.seeded', row1().note === DEBT, row1().note);
// дословный набор полей `_sp_advance_to_confirm`: ноты среди них нет
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, done: 'gear',
  odometer: '41641', status: 'ждёт_подтверждения' });
check('carrier.survives_visit', row1().note === DEBT, row1().note);
check('carrier.one_row', rows().length === 1, rows().length);

// ── 2. ПОЧЕМУ НЕ ПОЛЯ: тот же визит их затирает (дословная судьба 5960) ─────────────────────
checkNeg('fields.done_overwritten', row1().done === 'gear', row1().done);
checkNeg('fields.odometer_overwritten', String(row1().odometer) === '41641', row1().odometer);
checkNeg('fields.declared_kept_only_because_not_passed', row1().declared === 'abs,pads',
  row1().declared);

// ── 3. ДЫРА ЭХА: закрытие без открытой строки ДОПИСЫВАЕТ строку ────────────────────────────
reset();
const echo = servicePendingClose_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'долг закрыт' });
checkNeg('echo.close_without_row_appends', echo.ok === true && echo.saved === true && rows().length === 1,
  JSON.stringify(echo) + ' rows=' + rows().length);
checkNeg('echo.row_is_empty_nonsense', row1().declared === '' && row1().done === '',
  JSON.stringify([row1().declared, row1().done]));
// близнец: строка ЕСТЬ → та же дверь её ОБНОВЛЯЕТ, а не дописывает (забор не отнимает законного)
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, declared: 'oil', done: 'oil',
  odometer: '12212', status: 'ждёт_подтверждения', note: 'DEBT:{oil@12212}' });
const legit = servicePendingClose_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'WORKS:{}' });
check('echo.twin_existing_row_is_updated', legit.updated === true && rows().length === 1,
  JSON.stringify(legit) + ' rows=' + rows().length);
check('echo.twin_status_closed', row1().status === 'закрыто', row1().status);

// ── 4. ДЫРА ЧУЖОЙ СТРОКИ: закрытие гасит любую открытую строку пары чат×тема×байк ───────────
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, declared: 'chain', done: '',
  status: 'ждёт_факт' });
servicePendingClose_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'долг по маслу закрыт' });
checkNeg('alien.chain_claim_is_extinguished', row1().status === 'закрыто', row1().status);
checkNeg('alien.bridge_never_asked_whose_work', row1().declared === 'chain', row1().declared);
// близнец: строка ДРУГОГО байка не задета — забор моста по ключу работает, по работе не работает
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: OTHER, declared: 'chain', done: '',
  status: 'ждёт_факт' });
servicePendingClose_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'x' });
const byBike = rows().filter(r => String(r[4]) === OTHER)[0];
check('alien.twin_other_bike_untouched', String(byBike[7]) === 'ждёт_факт', byBike[7]);

// ── 5. ПУСТАЯ НОТА НЕ СТИРАЕТ → «долг снят» говорится непустым словом ───────────────────────
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, declared: 'abs', done: 'abs',
  status: 'ждёт_подтверждения', note: DEBT });
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: '' });
checkNeg('empty.note_cannot_erase', row1().note === DEBT, row1().note);
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'DEBT:{}' });
check('empty.twin_word_can', row1().note === 'DEBT:{}', row1().note);

// ── 6. СПИСОК ВИСЯКОВ ОТДАЁТ НОТУ — иначе сторож не увидел бы позиций ──────────────────────
reset();
servicePendingUpsert_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, declared: 'abs,pads',
  done: 'abs,pads', odometer: '41357', status: 'ждёт_подтверждения', note: DEBT });
const lst = servicePendingList_({ open: true });
check('list.carries_note', lst.ok && lst.items.length === 1 && lst.items[0].note === DEBT,
  JSON.stringify((lst.items || []).map(i => i.note)));
const got = servicePendingGet_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE });
check('get.carries_note', got.ok && got.item.note === DEBT, JSON.stringify(got));
// близнец: закрытая строка из открытых уходит — снятый долг сторожу не показывается
servicePendingClose_({ chat_id: CHAT, topic_id: TOPIC, bike: BIKE, note: 'DEBT:{}' });
check('list.twin_closed_row_is_gone', (servicePendingList_({ open: true }).items || []).length === 0,
  JSON.stringify(servicePendingList_({ open: true }).items));

const failed = cases.filter(c => !c.pass);
process.stdout.write(JSON.stringify({ cases, negatives, failed: failed.length }, null, 1) + '\n');
process.exit(failed.length ? 1 : 0);
