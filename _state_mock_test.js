/**
 * МОК-ТЕСТ слоя «состояние_байка» (Этап 1 трекинга).
 * GAS не исполняется в node — стабим минимальный Sheets API (grid-фейк),
 * грузим BotData.js в общий контекст, переопределяем getBotDataSpreadsheet_ на фейк,
 * прогоняем upsert→get→list + валидацию статуса. Временный хелпер (НЕ в tests/, gate не цепляет).
 */
const fs = require('fs');
const vm = require('vm');

// --- Грид-фейк листа: data[r][c], 1-based эмуляция через 0-based хранение ---
function FakeSheet() { this.data = []; }
FakeSheet.prototype.getLastRow = function () { return this.data.length; };
FakeSheet.prototype.setFrozenRows = function () { return this; };
FakeSheet.prototype.appendRow = function (arr) { this.data.push(arr.slice()); };
FakeSheet.prototype.getRange = function (row, col, numRows, numCols) {
  numRows = (numRows == null) ? 1 : numRows;
  numCols = (numCols == null) ? 1 : numCols;
  const sheet = this;
  return {
    setFontWeight: function () { return this; },
    setValue: function (v) {
      while (sheet.data.length < row) sheet.data.push([]);
      sheet.data[row - 1][col - 1] = v;
      return this;
    },
    setValues: function (vals) {
      for (let i = 0; i < numRows; i++) {
        while (sheet.data.length < row + i) sheet.data.push([]);
        for (let j = 0; j < numCols; j++) sheet.data[row - 1 + i][col - 1 + j] = vals[i][j];
      }
      return this;
    },
    getValues: function () {
      const out = [];
      for (let i = 0; i < numRows; i++) {
        const r = [];
        const src = sheet.data[row - 1 + i] || [];
        for (let j = 0; j < numCols; j++) {
          const v = src[col - 1 + j];
          r.push(v == null ? '' : v);
        }
        out.push(r);
      }
      return out;
    },
  };
};

function FakeSS() { this.sheets = {}; }
FakeSS.prototype.getSheetByName = function (n) { return this.sheets[n] || null; };
FakeSS.prototype.insertSheet = function (n) { return (this.sheets[n] = new FakeSheet()); };

const fakeSS = new FakeSS();

// --- грузим источник + тест в ОДНОМ scope (const/let не утекают на globalThis) ---
const src = fs.readFileSync('/root/turbobaby-bridge-gs/BotData.js', 'utf8');

let failures = 0;
function check(name, cond) {
  if (cond) { console.log('  PASS  ' + name); }
  else { console.log('  FAIL  ' + name); failures++; }
}

const test = `
// override на фейк (минуем SpreadsheetApp/CONFIG/Drive)
getBotDataSpreadsheet_ = function () { return __fakeSS; };

const B = 'NMAX 155CC BLACK GOLD PHUKET 4255';

// 1) insert
var r1 = stateUpsert_({ bike: B, status: 'в аренде', client: 'John',
  booking_id: 'BK1', date_out: '2026-06-01', date_due: '2026-06-10', location: 'Patong' });
__check('1 insert ok', r1.ok === true && r1.upserted === 'inserted');
__check('1 status сохранён', r1.item.status === 'в аренде');
__check('1 client сохранён', r1.item.client === 'John');

// 2) get
var g = stateGet_({ bike: B });
__check('2 get ok', g.ok === true && g.item.booking_id === 'BK1');
__check('2 get client', g.item.client === 'John');

// 3) update-merge: меняем status+date_back, client/booking_id НЕ передаём — должны сохраниться
var r2 = stateUpsert_({ bike: B, status: 'к возврату', date_back: '2026-06-09' });
__check('3 update (не insert)', r2.upserted === 'updated');
__check('3 status обновлён', r2.item.status === 'к возврату');
__check('3 client сохранён при merge', r2.item.client === 'John');
__check('3 booking_id сохранён при merge', r2.item.booking_id === 'BK1');
__check('3 date_back записан', r2.item.date_back === '2026-06-09');

// один байк = одна строка (upsert не плодит дубли)
var l1 = stateList_();
__check('3 list total=1 (нет дублей)', l1.total === 1);

// 4) второй байк
stateUpsert_({ bike: 'CB 650R 7777', status: 'дома' });
var l2 = stateList_();
__check('4 list total=2', l2.total === 2);

// 5) валидация статуса
var bad = stateUpsert_({ bike: 'X 0001', status: 'летит' });
__check('5 bad_status отклонён', bad.ok === false && bad.error === 'bad_status');
var l3 = stateList_();
__check('5 невалидный не записан (total=2)', l3.total === 2);

// 6) пустой bike
var nob = stateUpsert_({ status: 'дома' });
__check('6 no_bike отклонён', nob.ok === false && nob.error === 'no_bike');

// 7) get несуществующего
var gn = stateGet_({ bike: 'NETU 9999' });
__check('7 get not_found', gn.ok === false && gn.error === 'not_found');

// 8) пустой статус допускается (ещё не выставлен)
var emp = stateUpsert_({ bike: 'EMPTY 0002', status: '' });
__check('8 пустой статус ок', emp.ok === true);
`;

const sandbox = { __fakeSS: fakeSS, __check: check, console: console, Date: Date };
vm.createContext(sandbox);
vm.runInContext(src + '\n' + test, sandbox, { filename: 'BotData+test' });

console.log(failures === 0 ? '\nALL PASS' : '\n' + failures + ' FAIL');
process.exitCode = failures === 0 ? 0 : 1;
