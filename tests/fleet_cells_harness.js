'use strict';
/**
 * Харнесс контракта клетки ТО: исполняет РЕАЛЬНЫЙ /root/turbobaby-bridge-gs/ReadFleet.js в node
 * с мок-SpreadsheetApp (схема botdata_gs_harness.js: сервисы зовутся только внутри функций →
 * vm-загрузка + мок листа работает).
 *
 * Фокус — ТРАНСПОРТ клетки, а не толкование значений:
 *   (1) без cells ответ БАЙТ-В-БАЙТ прежний (доказывается сравнением с ответом с cells,
 *       из которого разметка удалена: если бы правка что-то ЗАМЕНИЛА, объекты разошлись бы);
 *   (2) три состояния различены — ЗНАЧЕНИЕ / ПУСТО / НЕ-ЧИСЛО;
 *   (3) невозможные значения (−5000, настоящий 0) доезжают как ЗНАЧЕНИЕ, а не как «пусто»;
 *   (4) cellState_ не разошёлся с parseNumber: state==='value' ⇔ parseNumber добыт из содержимого;
 *   (5) сам parseNumber не изменён (регресс на дословных живых формах).
 *
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1, если есть провалы.
 * Запускается из tests/test_fleet_cell.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');

const READFLEET_JS = '/root/turbobaby-bridge-gs/ReadFleet.js';
const WIDTH = 34;

function pad(arr) { const a = arr.slice(); while (a.length < WIDTH) a.push(''); return a; }

function makeSheet(rows) {
  const grid = rows.map(pad);
  return {
    grid,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    getRange(a, b, c, d) {
      if (typeof a === 'string') {           // 'A1:AH1' — дашборд
        return { getValues: () => [grid[0].slice(0, WIDTH)] };
      }
      return {
        getValues() {
          const out = [];
          for (let r = a; r < a + c; r++) out.push(grid[r - 1].slice(b - 1, b - 1 + d));
          return out;
        },
      };
    },
  };
}

// ── живой лист: строка 1 дашборд, строка 2 шапка, строки 3+ байки ──────────────────────────
// Колонки байка: 0=A #, 1=B статус, 2=C имя, 3=D дата, 4=E год, 5=F цена, 6=G принёс,
//                7=H пробег, 8=I масло, 9=J редуктор, 10=K ABS, 11=L фильтр
function bikeRow(n, name, H, I, J, K, L) {
  const r = new Array(24).fill('');
  r[0] = n; r[1] = 'ДОМА'; r[2] = name; r[3] = '01.01.2025'; r[4] = 2024;
  r[5] = 100000; r[6] = 50000;
  r[7] = H; r[8] = I; r[9] = J; r[10] = K; r[11] = L;
  return r;
}

const DASH = pad([0, 1000, 0, 0, 500000, 0, 900000, 0, 30500, 0, 366000, 0, 12, 0,
                  1200000, 0, 14, 0, 0, 38, 0, 20, 0, 15, 0, 2, 0, 1, 0, 0, 0, 3]);
const HEADERS = pad(['#', 'Статус', 'Название', 'Дата', 'Год', 'Цена', 'Принёс',
                     'Пробег', 'ТО Oil', 'ТО Gear', 'ABS', 'Возд. фильтр']);

const sheet = makeSheet([
  DASH,
  HEADERS,
  // A: три состояния в одной строке — число, пусто, прочерк, слово
  bikeRow(1, 'ТЕСТ 1111 NMAX 155CC PHUKET 1111', 12600, 37000, '', '-', 'нет данных'),
  // B: невозможные значения и живой текстовый формат одометра
  bikeRow(2, 'ТЕСТ 8969 XMAX 300CC PHUKET 8969', '35200 Km, 05.07.2026', 0, -5000,
          '   ', new Date(2026, 6, 5)),
  // C: валюта/разделители и null/undefined из пустых клеток листа
  bikeRow(3, 'ТЕСТ 4957 NMAX 155CC PHUKET 4957', '฿ 12 345', '24 094', null, undefined, '0'),
]);

global.CONFIG = { SHEETS: { FLEET: 'fake-fleet-id' }, TABS: {}, VERSION: 'harness' };
global.SpreadsheetApp = { openById: () => ({ getSheetByName: n => (n === 'Лист1' ? sheet : null) }) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = { formatDate: (d) => '2026-07-05 00:00' };
global.Logger = { log: () => {} };

vm.runInThisContext(fs.readFileSync(READFLEET_JS, 'utf8'), { filename: READFLEET_JS });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: String(detail) }); }

// ── (1) БЕЗ разметки ответ прежний ─────────────────────────────────────────────────────────
const plain = getFleetStatus();
const marked = getFleetStatus('1');

check('plain.no-cells-key',
      plain.bikes.every(b => !('cells' in b)),
      'байков без ключа cells: ' + plain.bikes.filter(b => !('cells' in b)).length +
      ' из ' + plain.bikes.length);

const strippedMarked = JSON.parse(JSON.stringify(marked));
strippedMarked.bikes.forEach(b => { delete b.cells; });
check('plain.identical-to-marked-minus-cells',
      JSON.stringify(plain) === JSON.stringify(strippedMarked),
      'разметка ДОБАВЛЯЕТ и ничего не заменяет: ' +
      (JSON.stringify(plain) === JSON.stringify(strippedMarked) ? 'совпало' :
       'РАЗОШЛОСЬ\n' + JSON.stringify(plain) + '\n' + JSON.stringify(strippedMarked)));

check('marked.has-cells-key',
      marked.bikes.every(b => b.cells && typeof b.cells === 'object'),
      'байков с разметкой: ' + marked.bikes.filter(b => b.cells).length);

// формы параметра: что включает разметку, а что нет
const forms = [[true, true], [1, true], ['1', true], ['true', true],
               [undefined, false], ['', false], ['0', false], [false, false]];
forms.forEach(([arg, want]) => {
  const got = ('cells' in getFleetStatus(arg).bikes[0]);
  // имя кейса — через JSON.stringify: String(1) и String('1') совпадают, и два РАЗНЫХ кейса
  // получали одно имя (число и строка — разные формы параметра, их и надо различать).
  check('param.' + JSON.stringify(arg), got === want, 'аргумент ' + JSON.stringify(arg) +
        ' → разметка ' + (got ? 'есть' : 'нет') + ', ожидали ' + (want ? 'есть' : 'нет'));
});

// ── (2) ТРИ СОСТОЯНИЯ различены ────────────────────────────────────────────────────────────
const A = marked.bikes[0], B = marked.bikes[1], C = marked.bikes[2];

check('state.value', A.cells.oil_last_km.state === 'value' && A.cells.oil_last_km.num === 37000,
      'кол.I=37000 → ' + JSON.stringify(A.cells.oil_last_km));
check('state.empty', A.cells.gear_last_km.state === 'empty',
      'кол.J пусто → ' + JSON.stringify(A.cells.gear_last_km));
check('state.text.dash', A.cells.abs_last_km.state === 'text' && A.cells.abs_last_km.raw === '-',
      'кол.K прочерк → ' + JSON.stringify(A.cells.abs_last_km));
check('state.text.word', A.cells.airfilter_last_km.state === 'text',
      'кол.L слово → ' + JSON.stringify(A.cells.airfilter_last_km));
check('state.empty.spaces', B.cells.abs_last_km.state === 'empty',
      'кол.K одни пробелы → ' + JSON.stringify(B.cells.abs_last_km));
check('state.empty.null', C.cells.gear_last_km.state === 'empty',
      'кол.J null → ' + JSON.stringify(C.cells.gear_last_km));
check('state.empty.undefined', C.cells.abs_last_km.state === 'empty',
      'кол.K undefined → ' + JSON.stringify(C.cells.abs_last_km));
check('state.text.date', B.cells.airfilter_last_km.state === 'text',
      'кол.L дата → ' + JSON.stringify(B.cells.airfilter_last_km));

// три состояния по ОДНОМУ байку сразу — то, чего сегодня нет вовсе
check('three-states.side-by-side',
      A.cells.oil_last_km.state === 'value' && A.cells.gear_last_km.state === 'empty' &&
      A.cells.abs_last_km.state === 'text',
      'I=value, J=empty, K=text у одного байка');

// ── (3) НЕВОЗМОЖНЫЕ значения — транспорт их НЕ чинит и НЕ прячет ───────────────────────────
check('impossible.negative',
      B.cells.gear_last_km.state === 'value' && B.cells.gear_last_km.num === -5000,
      'кол.J=−5000 (живой случай 8969) → ' + JSON.stringify(B.cells.gear_last_km));
check('impossible.true-zero',
      B.cells.oil_last_km.state === 'value' && B.cells.oil_last_km.num === 0,
      'кол.I=настоящий 0 → value, НЕ empty: ' + JSON.stringify(B.cells.oil_last_km));
check('impossible.zero-as-text',
      C.cells.airfilter_last_km.state === 'value' && C.cells.airfilter_last_km.num === 0,
      'кол.L="0" строкой → value 0: ' + JSON.stringify(C.cells.airfilter_last_km));
check('impossible.zero-vs-empty-differ',
      B.cells.oil_last_km.state !== A.cells.gear_last_km.state,
      'настоящий ноль и пустая клетка теперь РАЗНЫЕ состояния');

// ── (4) живой текстовый формат: число добыто, сырое сохранено ──────────────────────────────
check('live-text.odometer',
      B.cells.mileage.state === 'value' && B.cells.mileage.num === 35200 &&
      B.cells.mileage.raw === '35200 Km, 05.07.2026',
      'кол.H живой формат → ' + JSON.stringify(B.cells.mileage));
check('live-text.currency',
      C.cells.mileage.state === 'value' && C.cells.mileage.num === 12345,
      'кол.H «฿ 12 345» → ' + JSON.stringify(C.cells.mileage));
check('live-text.thin-space',
      C.cells.oil_last_km.state === 'value' && C.cells.oil_last_km.num === 24094,
      'кол.I «24 094» → ' + JSON.stringify(C.cells.oil_last_km));

// ── (5) cellState_ НЕ разошёлся с parseNumber ──────────────────────────────────────────────
const TABLE = ['', '   ', null, undefined, '-', '—', 'нет', 'нет данных', 'н/д', 0, 1, -5000,
               37000, '0', '24 094', '฿ 12 345', '35200 Km, 05.07.2026', '12.5', '12,5',
               new Date(2026, 6, 5), 'abc', '  42  ', ' 100'];
const drift = [];
TABLE.forEach(v => {
  const st = cellState_(v);
  const pn = parseNumber(v);
  if (st.state === 'value') {
    if (st.num !== pn) drift.push({ v: String(v), why: 'value: num=' + st.num + ' ≠ parseNumber=' + pn });
  } else if (pn !== 0) {
    drift.push({ v: String(v), why: 'не-value, а parseNumber дал ' + pn });
  }
});
check('mirror.cellstate-vs-parsenumber', drift.length === 0,
      'значений сверено ' + TABLE.length + ', расхождений ' + drift.length +
      (drift.length ? ': ' + JSON.stringify(drift) : ''));

// ── (6) сам parseNumber не изменён (регресс на дословных формах) ───────────────────────────
const PN = [['', 0], ['-', 0], ['abc', 0], [null, 0], [undefined, 0], [0, 0], [37000, 37000],
            ['24 094', 24094], ['฿ 12 345', 12345], ['35200 Km, 05.07.2026', 35200], [-5000, -5000]];
const pnBad = PN.filter(([v, want]) => parseNumber(v) !== want);
check('regress.parsenumber-unchanged', pnBad.length === 0,
      'форм сверено ' + PN.length + ', разошлось ' + pnBad.length +
      (pnBad.length ? ': ' + JSON.stringify(pnBad) : ''));

// ── (7) прочие поля строки парка не тронуты ────────────────────────────────────────────────
check('other-fields.intact',
      A.name === 'ТЕСТ 1111 NMAX 155CC PHUKET 1111' && A.status === 'ДОМА' &&
      A.cost === 100000 && A.total_revenue === 50000 && A.oil_last_km === 37000 &&
      A.gear_last_km === 0 && A.abs_last_km === 0,
      'числовые поля прежние, в т.ч. НУЛИ на месте: gear=' + A.gear_last_km +
      ', abs=' + A.abs_last_km);
check('summary.intact', plain.summary.total === 3 && plain.summary.home === 3,
      'сводка: ' + JSON.stringify(plain.summary));
check('dashboard.intact', plain.dashboard.count_total === 38 && plain.dashboard.income_per_day === 1000,
      'дашборд: total=' + plain.dashboard.count_total);

// Рядом с кейсами печатаем САМ ответ моста с разметкой: питон-часть (tests/test_fleet_cell.py)
// кормит им fleet_cell.read, и тогда фикстура питона — не пересказ формата, а РОВНО то, что
// вернул живой ReadFleet.js. Формат разметки описан в одном месте — здесь; расходиться нечему.
process.stdout.write(JSON.stringify({ cases, fleet: marked }, null, 1));
process.exit(cases.some(c => !c.pass) ? 1 : 0);
