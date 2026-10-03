'use strict';
/**
 * Харнесс двери договоров TB e-Sign (CONTRACTDOOR0310, 03.10.2026): исполняет РЕАЛЬНЫЙ код моста в
 * node на мок-реестре и мок-Drive — тот же способ, что tx_find_gs_harness.js / botdata_gs_harness.js
 * (сервисы Apps Script зовутся только внутри функций → vm-загрузка + мок работает).
 *
 * Источники кода — правило srcOf: файл есть в КАТАЛОГЕ СБОРКИ ЗАХОДА `bridge_build_contract/` —
 * берём сборку, иначе ЗЕРКАЛО ПРОДА `bridge_prod/`. Судимые файлы — ContractDoor.js (новый) и
 * Bridge.js (маршруты GET `contract_find`/`contract_pdf`); Config.js (verifyToken) и BotData.js
 * (plateOf_) — из зеркала.
 *
 * `--stdin`: подмена исходников JSON-объектом {имя файла: текст} со stdin — так тест гоняет
 * МУТАНТОВ, не создавая файлов на диске.
 *
 * Данные СИНТЕТИЧЕСКИЕ (выдуманные имена и номера, паспортных данных нет). Ячейки — в формах, какие
 * отдаёт Sheets: дата строкой и Date, ссылка на PDF текстом /d/…, голым id, богатым текстом
 * (значение «PDF», ссылка в link) и формулой HYPERLINK (значение «PDF», ссылка в формуле).
 *
 * Печатает JSON {cases:[{name, pass, detail}], failed}; exit 1, если есть провалы.
 * Запускается из tests/test_contract_door.py.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const crypto = require('crypto');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build_contract');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');

function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}

const OVERRIDE = process.argv.includes('--stdin') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}

// ── счётчик записей: любая пишущая операция мока сюда ──
const WRITES = { n: 0, what: [] };
function wrote(what) { WRITES.n++; WRITES.what.push(what); }

// ── мок листа: значения + параллельные сетки богатого текста и формул ──
function makeSheet(rows, rich, formulas) {
  const width = Math.max(...rows.map(r => r.length));
  const grid = rows.map(r => { const a = r.slice(); while (a.length < width) a.push(''); return a; });
  const cell = (g, r, c) => (g && g[r - 1] && g[r - 1][c - 1] !== undefined ? g[r - 1][c - 1] : null);
  return {
    getLastRow() { return grid.length; },
    getLastColumn() { return width; },
    appendRow() { wrote('appendRow'); },
    deleteRows() { wrote('deleteRows'); },
    getRange(a, b, c, d) {
      const nr = c === undefined ? 1 : c, nc = d === undefined ? 1 : d;
      const block = fn => { const out = []; for (let r = a; r < a + nr; r++) { const row = []; for (let k = b; k < b + nc; k++) row.push(fn(r, k)); out.push(row); } return out; };
      return {
        getValues() { return block((r, k) => { const v = cell(grid, r, k); return v === null ? '' : v; }); },
        getRichTextValues() { return block((r, k) => { const u = cell(rich, r, k); return { getLinkUrl: () => u || null, getText: () => String(cell(grid, r, k) || '') }; }); },
        getFormulas() { return block((r, k) => { const f = cell(formulas, r, k); return f || ''; }); },
        setValue() { wrote('setValue'); }, setValues() { wrote('setValues'); }, clear() { wrote('clear'); },
      };
    },
  };
}

// ── синтетика: id файлов Drive (≥25 знаков) ──
const PDF_A = 'pdfA0000000000000000000000001', PDF_B = 'pdfB0000000000000000000000002';
const PDF_C = 'pdfC0000000000000000000000003', PDF_R = 'pdfR0000000000000000000000004';
const PDF_X = 'pdfX0000000000000000000000005', PDF_N = 'pdfN0000000000000000000000006';
const PDF_T = 'pdfT0000000000000000000000007', PDF_L = 'pdfL0000000000000000000000008';
const FOREIGN = 'pdfF0000000000000000000000009';
const SIGNED_DIR = 'dirSigned00000000000000000001', OTHER_DIR = 'dirOther000000000000000000002';
const REG_ID = 'regEsign000000000000000000000001';
const VIEW = id => 'https://drive.google.com/file/d/' + id + '/view?usp=drivesdk';

const HEADERS = ['ID документа', 'Название', 'Клиент', 'Дата договора', 'Статус', 'Документ создан',
  'Email клиента', 'Агент', 'BoldSign ID', 'Отправлен', 'Статусы подписантов', 'Подписан',
  'PDF (подписанный)', 'Аудит-след', 'Заметка', 'Ссылка на документ', 'Ссылка «на подпись»',
  'Обновлено', 'Ник (Social contact)', 'Телефон', 'Байк'];
const H = Object.fromEntries(HEADERS.map((h, i) => [h, i]));
function rowOf(o) { const r = new Array(HEADERS.length).fill(''); for (const k in o) r[H[k]] = o[k]; return r; }
const BKK = s => new Date(s + '+07:00');

// строки реестра: индекс + 1 = номер строки листа (шапка — строка 1)
const ROWS = [
  HEADERS.slice(),
  /* 2 */ rowOf({ 'ID документа': 'D-001', 'Клиент': 'Ivan Petrov', 'Дата договора': '2026-09-01', 'Статус': 'ПОДПИСАН',
    'Подписан': BKK('2026-09-01T10:00:00'), 'PDF (подписанный)': VIEW(PDF_A), 'Ник (Social contact)': '@ivan_test',
    'Телефон': '+66 81 234 5678', 'Байк': 'Nmax 6908', 'Email клиента': 'ivan@example.test' }),
  /* 3 */ rowOf({ 'ID документа': 'D-002', 'Клиент': 'Ivan Petrov', 'Дата договора': BKK('2026-09-20T00:00:00'),
    'Статус': ' Подписан ', 'Подписан': '20.09.2026 14:05', 'PDF (подписанный)': 'PDF',
    'Телефон': '66812345678', 'Байк': 'ADV 8004' }),
  /* 4 */ rowOf({ 'ID документа': 'D-003', 'Клиент': 'Olga Smirnova', 'Дата договора': '2026-09-25', 'Статус': 'ОТПРАВЛЕН',
    'Телефон': '+7 999 111-22-33', 'Байк': 'Click 160 5580' }),
  /* 5 */ rowOf({ 'ID документа': 'D-004', 'Клиент': 'Olga Smirnova', 'Дата договора': '2026-09-10', 'Статус': 'ОТОЗВАН',
    'PDF (подписанный)': 'PDF', 'Телефон': '+79991112233', 'Байк': 'Click 160 5580' }),
  /* 6 */ rowOf({ 'ID документа': 'D-005', 'Клиент': 'Анна Кузнецова', 'Дата договора': '15.09.2026', 'Статус': 'ПОДПИСАН',
    'Подписан': BKK('2026-09-15T18:30:00'), 'PDF (подписанный)': PDF_C,
    'Ник (Social contact)': 'WhatsApp +66 89 765 4321', 'Байк': 'NMAX 155 GREY 6908' }),
  /* 7 */ rowOf({ 'ID документа': 'D-006', 'Клиент': 'John Smith', 'Документ создан': '2026-09-28 09:00', 'Статус': 'ПОДПИСАН',
    'Подписан': '2026-09-28 12:00', 'PDF (подписанный)': VIEW(PDF_X), 'Телефон': '+44 7700 900123', 'Байк': 'Vario 1234' }),
  /* 8 */ rowOf({ 'ID документа': 'D-007', 'Клиент': 'John Smith', 'Дата договора': '2026-09-29', 'Статус': 'ПОДПИСАН ЧАСТИЧНО',
    'Телефон': '+447700900123', 'Байк': 'Vario 1234' }),
  /* 9 */ rowOf({ 'ID документа': 'D-008', 'Клиент': 'Mike Brown', 'Дата договора': '2026-09-30', 'Статус': 'ПОДПИСАН',
    'PDF (подписанный)': VIEW(PDF_N), 'Телефон': '+66 80 000 0001', 'Байк': 'PCX 7777' }),
  /* 10 */ rowOf({ 'ID документа': 'D-009', 'Клиент': 'Lena Test', 'Дата договора': '2026-09-30', 'Статус': 'ПОДПИСАН',
    'PDF (подписанный)': VIEW(PDF_T), 'Телефон': '+66 80 000 0002', 'Байк': 'PCX 7778' }),
  /* 11 */ rowOf({ 'ID документа': 'D-010', 'Клиент': 'Big File', 'Дата договора': '2026-09-30', 'Статус': 'ПОДПИСАН',
    'PDF (подписанный)': VIEW(PDF_L), 'Телефон': '+66 80 000 0003', 'Байк': 'PCX 7779' }),
];
const RICH = ROWS.map(() => []), FORMULAS = ROWS.map(() => []);
RICH[2][H['PDF (подписанный)']] = 'https://drive.google.com/open?id=' + PDF_B + '&usp=sharing';   // строка 3
FORMULAS[4][H['PDF (подписанный)']] = '=HYPERLINK("https://drive.google.com/file/d/' + PDF_R + '/view","PDF")'; // строка 5

let SHEETS = { 'Реестр': makeSheet(ROWS, RICH, FORMULAS) };
const PROPS = { BRIDGE_TOKEN: 'tok-test', ESIGN_REGISTRY_ID: REG_ID, ESIGN_SIGNED_FOLDER_ID: SIGNED_DIR };
const OPENED = { reg: 0 };

// ── мок Drive: байты PDF несут значения ≥128 (в Apps Script это отрицательные Byte) ──
function bytesOf(text) { return Array.from(Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from([0xE2, 0xE3, 0xCF, 0xD3]), Buffer.from(text)])); }
const signedArr = u => u.map(b => (b > 127 ? b - 256 : b));
const DRIVE_GETS = { n: 0, ids: [] };
function makeFile(id, o) {
  const u = bytesOf(o.text || id);
  return {
    getId: () => id, getName: () => o.name || (id + '.pdf'), getMimeType: () => o.mime || 'application/pdf',
    getSize: () => (o.size !== undefined ? o.size : u.length), isTrashed: () => !!o.trashed,
    getParents() { const ps = (o.parents || [SIGNED_DIR]).map(p => ({ getId: () => p })); let i = 0;
      return { hasNext: () => i < ps.length, next: () => ps[i++] }; },
    getBlob() { if (o.size && o.size > 1e6) throw new Error('getBlob на файле сверх потолка'); return { getBytes: () => signedArr(u.slice()) }; },
    setTrashed() { wrote('setTrashed'); }, moveTo() { wrote('moveTo'); }, setName() { wrote('setName'); },
    setContent() { wrote('setContent'); }, addEditor() { wrote('addEditor'); },
    _unsigned: u,
  };
}
const FILES = {
  [PDF_A]: makeFile(PDF_A, { name: 'Договор D-001 подписан.pdf', text: 'contract A' }),
  [PDF_B]: makeFile(PDF_B, { text: 'contract B' }),
  [PDF_C]: makeFile(PDF_C, { text: 'contract C', parents: [OTHER_DIR, SIGNED_DIR] }),
  [PDF_R]: makeFile(PDF_R, { text: 'revoked' }),
  [PDF_X]: makeFile(PDF_X, { text: 'wrong folder', parents: [OTHER_DIR] }),
  [PDF_N]: makeFile(PDF_N, { text: 'doc', mime: 'application/vnd.google-apps.document' }),
  [PDF_T]: makeFile(PDF_T, { text: 'trashed', trashed: true }),
  [PDF_L]: makeFile(PDF_L, { text: 'big', size: 20 * 1024 * 1024 }),
  [FOREIGN]: makeFile(FOREIGN, { text: 'foreign but in signed folder' }),
};

global.SpreadsheetApp = { openById(id) {
  if (id !== REG_ID) throw new Error('no access: ' + id);
  OPENED.reg++;
  return { getSheetByName: n => SHEETS[n] || null, insertSheet() { wrote('insertSheet'); } };
} };
global.DriveApp = { getFileById(id) { DRIVE_GETS.n++; DRIVE_GETS.ids.push(id); if (!FILES[id]) throw new Error('File not found: ' + id); return FILES[id]; },
  createFile() { wrote('createFile'); } };
global.PropertiesService = { getScriptProperties: () => ({ getProperty: k => (k in PROPS ? PROPS[k] : null), setProperty: () => wrote('setProperty') }) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = {
  formatDate(d, tz, fmt) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d).map(p => [p.type, p.value]));
    const day = parts.year + '-' + parts.month + '-' + parts.day;
    if (fmt === 'yyyy-MM-dd') return day;
    if (fmt === 'yyyy-MM-dd HH:mm') return day + ' ' + parts.hour + ':' + parts.minute;
    throw new Error('формат мока не поддержан: ' + fmt);
  },
  DigestAlgorithm: { SHA_256: 'SHA_256' },
  computeDigest(alg, bytes) {
    if (alg !== 'SHA_256') throw new Error('алгоритм мока: ' + alg);
    return signedArr(Array.from(crypto.createHash('sha256').update(Buffer.from(bytes.map(b => b & 0xff))).digest()));
  },
  base64Encode: bytes => Buffer.from(bytes.map(b => b & 0xff)).toString('base64'),
  getUuid: () => 'uuid',
};
global.ContentService = {
  MimeType: { JSON: 'application/json' },
  createTextOutput(s) { return { content: s, setMimeType() { return this; }, getContent() { return this.content; } }; },
};
global.Logger = { log: () => {} };
global.console = console;

for (const f of ['Config.js', 'BotData.js', 'Bridge.js', 'ContractDoor.js'])
  vm.runInThisContext(srcText(f), { filename: srcOf(f) });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function safe(fn) { try { return fn(); } catch (e) { return { ok: false, error: 'THROWN', message: String(e && e.message) }; } }
const rowsOf = r => (r && r.items ? r.items.map(x => x.row) : null);
const J = x => JSON.stringify(x);
const byRow = (r, n) => (r && r.items || []).find(x => x.row === n) || {};

// ── 1. телефон: последние 9 цифр; пробелы, плюс и код страны не мешают; «Ник» тоже ──
{
  const r = safe(() => contractFind({ phone: '0812345678' }));
  check('phone.ok', r.ok === true, J(r).slice(0, 300));
  check('phone.rows', J(rowsOf(r)) === J([3, 2]), J(rowsOf(r)));
  check('phone.matched-on', (r.items || []).every(x => J(x.matched_on) === J(['phone'])), J((r.items || []).map(x => x.matched_on)));
  const r2 = safe(() => contractFind({ phone: '+66 81 234 5678' }));
  check('phone.formatted', J(rowsOf(r2)) === J([3, 2]), J(rowsOf(r2)));
  const r3 = safe(() => contractFind({ phone: '089-765-4321' }));
  check('phone.via-nick', J(rowsOf(r3)) === J([6]) && J(r3.items[0].matched_on) === J(['nick']), J(r3.items));
  check('phone.filter-echo', r.filter && r.filter.phone_last9 === '812345678', J(r.filter));
  check('phone.bad', safe(() => contractFind({ phone: '12345' })).error === 'bad_phone', '');
}

// ── 2. имя: слова в любом порядке, начало слова от 3 букв, ё/регистр не мешают ──
{
  const r = safe(() => contractFind({ name: 'petrov IVAN' }));
  check('name.any-order', J(rowsOf(r)) === J([3, 2]), J(rowsOf(r)));
  const r2 = safe(() => contractFind({ name: 'Ivan Petr' }));
  check('name.prefix', J(rowsOf(r2)) === J([3, 2]), J(rowsOf(r2)));
  const r3 = safe(() => contractFind({ name: 'анна' }));
  check('name.cyrillic', J(rowsOf(r3)) === J([6]) && r3.outcome === 'one', J(r3).slice(0, 200));
  const r4 = safe(() => contractFind({ name: 'iv' }));
  check('name.short-word-no-prefix', r4.ok === true && r4.outcome === 'none', J(rowsOf(r4)));
  check('name.bad', safe(() => contractFind({ name: '!' })).error === 'bad_name', '');
}

// ── 3. байк: по НОМЕРУ (plateOf_), «NMAX 155 GREY 6908» находится по 6908 ──
{
  const r = safe(() => contractFind({ bike: '6908' }));
  check('bike.by-plate', J(rowsOf(r)) === J([6, 2]), J(rowsOf(r)));
  check('bike.two-clients-ambiguous', r.outcome === 'ambiguous' && r.pick === null, J([r.outcome, r.pick]));
  const r2 = safe(() => contractFind({ bike: 'ADV 750 8004' }));
  check('bike.one', J(rowsOf(r2)) === J([3]) && r2.outcome === 'one' && r2.pick.pdf_id === PDF_B, J(r2.pick));
  check('bike.bad', safe(() => contractFind({ bike: 'Nmax' })).error === 'bad_bike', '');
}

// ── 4. два договора одного клиента: без уточнения — неизвестно; срок или байк выбирают ──
{
  const r = safe(() => contractFind({ phone: '0812345678' }));
  check('two.ambiguous', r.outcome === 'ambiguous' && r.pick === null && r.checked.signed === 2, J([r.outcome, r.checked]));
  const r2 = safe(() => contractFind({ phone: '0812345678', date_from: '2026-09-15', date_to: '2026-09-30' }));
  check('two.by-term', J(rowsOf(r2)) === J([3]) && r2.outcome === 'one' && r2.pick.pdf_id === PDF_B && r2.pick.row === 3, J(r2.pick));
  check('two.term-date-object', byRow(r2, 3).contract_date === '2026-09-20' && byRow(r2, 3).date_src === 'contract_date', J(byRow(r2, 3)));
  const r3 = safe(() => contractFind({ name: 'Ivan Petrov', bike: 'Nmax 6908' }));
  check('two.by-bike', J(rowsOf(r3)) === J([2]) && r3.outcome === 'one' && r3.pick.pdf_id === PDF_A && r3.pick.pdf_ready === true, J(r3.pick));
  const r4 = safe(() => contractFind({ phone: '0812345678', date_from: '01.09.2026', date_to: '01.09.2026' }));
  check('two.term-inclusive-ddmmyyyy', J(rowsOf(r4)) === J([2]), J(rowsOf(r4)));
}

// ── 5. неподписанный: отдаётся как есть, подписанным не считается ──
{
  const r = safe(() => contractFind({ name: 'Olga Smirnova' }));
  check('unsigned.none-signed', r.outcome === 'none_signed' && r.pick === null && J(rowsOf(r)) === J([5, 4]), J([r.outcome, rowsOf(r)]));
  check('unsigned.status-raw', byRow(r, 4).status === 'ОТПРАВЛЕН' && byRow(r, 4).signed === false, J(byRow(r, 4)));
  const r2 = safe(() => contractFind({ name: 'John Smith' }));
  check('unsigned.partial-not-signed', r2.outcome === 'one' && r2.pick.row === 7 && byRow(r2, 8).signed === false
        && byRow(r2, 8).status === 'ПОДПИСАН ЧАСТИЧНО', J(r2.items));
  check('unsigned.status-case-space', byRow(safe(() => contractFind({ bike: '8004' })), 3).signed === true, '« Подписан » = подписан');
}

// ── 6. отозванный: в поиске — signed:false; PDF не отдаётся даже при ссылке в реестре ──
{
  const r = safe(() => contractFind({ phone: '79991112233' }));
  check('revoked.found-not-signed', byRow(r, 5).status === 'ОТОЗВАН' && byRow(r, 5).signed === false && r.outcome === 'none_signed', J(byRow(r, 5)));
  check('revoked.pdf-id-from-formula', byRow(r, 5).pdf_id === PDF_R, J(byRow(r, 5).pdf_id));
  const p = safe(() => contractPdf({ id: PDF_R }));
  check('revoked.pdf-refused', p.ok === false && p.error === 'not_signed' && p.rows && p.rows[0].status === 'ОТОЗВАН' && !('content_b64' in p), J(p));
}

// ── 7. PDF: подписанный отдаётся целиком, sha256 и размер верны ──
{
  const p = safe(() => contractPdf({ id: PDF_A }));
  const want = FILES[PDF_A]._unsigned;
  check('pdf.ok', p.ok === true && p.name === 'Договор D-001 подписан.pdf' && p.mime === 'application/pdf', J(p).slice(0, 300));
  check('pdf.size', p.size === want.length, J([p.size, want.length]));
  check('pdf.sha256', p.sha256 === crypto.createHash('sha256').update(Buffer.from(want)).digest('hex'), p.sha256);
  check('pdf.content', p.content_b64 === Buffer.from(want).toString('base64'), (p.content_b64 || '').slice(0, 40));
  check('pdf.registry-row', p.row === 2 && p.client === 'Ivan Petrov' && p.contract_date === '2026-09-01' && p.signed_at === '2026-09-01 10:00', J([p.row, p.client, p.contract_date, p.signed_at]));
  const p2 = safe(() => contractPdf({ id: PDF_C }));
  check('pdf.second-parent-ok', p2.ok === true, J(p2).slice(0, 200));
  const p3 = safe(() => contractPdf({ id: PDF_B }));
  check('pdf.rich-link-row', p3.ok === true && p3.row === 3 && p3.signed_at === '20.09.2026 14:05', J([p3.row, p3.signed_at]));
}

// ── 8. чужой id: не из реестра → отказ ДО Drive; из реестра, но вне папки / не PDF / в корзине / большой ──
{
  const before = DRIVE_GETS.n;
  const p = safe(() => contractPdf({ id: FOREIGN }));
  check('foreign.not-in-registry', p.ok === false && p.error === 'not_in_registry' && p.checked && p.checked.rows_scanned === 10, J(p));
  check('foreign.drive-not-touched', DRIVE_GETS.n === before, J(DRIVE_GETS.ids.slice(before)));
  check('foreign.wrong-folder', safe(() => contractPdf({ id: PDF_X })).error === 'not_in_signed_folder', '');
  check('foreign.not-pdf', safe(() => contractPdf({ id: PDF_N })).error === 'not_pdf', '');
  check('foreign.trashed', safe(() => contractPdf({ id: PDF_T })).error === 'trashed', '');
  const big = safe(() => contractPdf({ id: PDF_L }));
  check('foreign.too-large', big.error === 'too_large' && big.size === 20 * 1024 * 1024, J(big));
  check('foreign.bad-id', safe(() => contractPdf({ id: '../etc' })).error === 'bad_id' && safe(() => contractPdf({})).error === 'bad_id', '');
}

// ── 9. пусто — с числом просмотренных и просмотренным сроком («не найдено» ≠ «не смотрели») ──
{
  const r = safe(() => contractFind({ phone: '0899999999' }));
  check('empty.none', r.ok === true && r.outcome === 'none' && J(r.items) === '[]' && r.pick === null, J(r).slice(0, 200));
  check('empty.rows-scanned', r.checked && r.checked.rows_scanned === 10 && r.checked.matched === 0, J(r.checked));
  check('empty.span-is-registry', r.checked && r.checked.span_from === '2026-09-01' && r.checked.span_to === '2026-09-30', J(r.checked));
  const r2 = safe(() => contractFind({ name: 'Ivan', date_from: '2026-01-01', date_to: '2026-01-31' }));
  check('empty.named-span', r2.ok === true && r2.outcome === 'none' && r2.checked.rows_scanned === 10
        && r2.checked.span_from === '2026-01-01' && r2.checked.span_to === '2026-01-31', J(r2.checked));
}

// ── 10. срок: «Дата договора» пуста → день «Документ создан», источник назван ──
{
  const r = safe(() => contractFind({ bike: '1234', date_from: '2026-09-28', date_to: '2026-09-28' }));
  check('term.created-fallback', J(rowsOf(r)) === J([7]) && byRow(r, 7).date_src === 'created' && byRow(r, 7).contract_date === '2026-09-28', J(r.items));
  const r2 = safe(() => contractFind({ bike: '6908', date_to: '2026-09-15' }));
  check('term.end-inclusive', J(rowsOf(r2)) === J([6, 2]), J(rowsOf(r2)));
}

// ── 11. отказы фильтра — названы, реестр целиком не выгружается ──
{
  check('guard.no-filter', safe(() => contractFind({})).error === 'no_filter', '');
  check('guard.term-alone', safe(() => contractFind({ date_from: '2026-09-01' })).error === 'no_filter', '');
  check('guard.bad-date', safe(() => contractFind({ name: 'Ivan', date_from: '2026-02-30' })).error === 'bad_date', '');
  check('guard.bad-span', safe(() => contractFind({ name: 'Ivan', date_from: '2026-09-30', date_to: '2026-09-01' })).error === 'bad_span', '');
}

// ── 12. потолок: исход считается по ВСЕМ найденным, отдаётся не больше limit ──
{
  const r = safe(() => contractFind({ phone: '0812345678', limit: 1 }));
  check('limit.cut', J(rowsOf(r)) === J([3]) && r.checked.matched === 2 && r.checked.truncated === true && r.outcome === 'ambiguous', J(r.checked));
  const r2 = safe(() => contractFind({ phone: '0812345678', limit: 100000 }));
  check('limit.max', r2.limit === 100 && r2.limit_max === 100, J([r2.limit, r2.limit_max]));
  check('limit.default', safe(() => contractFind({ name: 'Ivan' })).limit === 20, '');
}

// ── 13. поля ответа ──
{
  const r = safe(() => contractFind({ name: 'Ivan Petrov', bike: '6908' }));
  const need = ['row', 'doc_id', 'client', 'contract_date', 'status', 'signed', 'signed_at', 'bike', 'phone', 'pdf_id'];
  const miss = need.filter(k => !(r.items && r.items[0] && k in r.items[0]));
  check('fields.all', miss.length === 0, 'нет: ' + J(miss));
  const it = (r.items || [])[0] || {};
  check('fields.values', it.row === 2 && it.doc_id === 'D-001' && it.contract_date === '2026-09-01' && it.signed_at === '2026-09-01 10:00'
        && it.phone === '+66 81 234 5678' && it.pdf_id === PDF_A, J(it));
  check('fields.no-email', !J(r).includes('ivan@example.test'), 'email клиента в ответ не идёт');
}

// ── 14. заголовки ищутся по ИМЕНИ: другой порядок колонок — тот же ответ; нужной колонки нет — отказ ──
{
  const keep = SHEETS;
  const perm = HEADERS.map((_, i) => i).reverse();
  const shuf = g => g.map(r => perm.map(i => (r || [])[i]));
  SHEETS = { 'Реестр': makeSheet(shuf(ROWS), shuf(RICH), shuf(FORMULAS)) };
  const r = safe(() => contractFind({ phone: '0812345678', date_from: '2026-09-15' }));
  check('headers.by-name', r.ok === true && r.outcome === 'one' && r.pick && r.pick.pdf_id === PDF_B, J(r).slice(0, 300));
  const broken = ROWS.map(x => x.slice()); broken[0][H['Телефон']] = 'Тел.';
  SHEETS = { 'Реестр': makeSheet(broken, RICH, FORMULAS) };
  const r2 = safe(() => contractFind({ name: 'Ivan' }));
  check('headers.missing-named', r2.ok === false && r2.error === 'no_column' && J(r2.missing) === J(['Телефон']), J(r2).slice(0, 200));
  SHEETS = {};
  check('headers.no-sheet', safe(() => contractFind({ name: 'Ivan' })).error === 'no_registry_sheet', '');
  SHEETS = keep;
}

// ── 15. адреса не заданы → названный отказ, а не пустой ответ ──
{
  const reg = PROPS.ESIGN_REGISTRY_ID, dir = PROPS.ESIGN_SIGNED_FOLDER_ID;
  delete PROPS.ESIGN_REGISTRY_ID;
  const r = safe(() => contractFind({ name: 'Ivan' }));
  check('config.no-registry', r.ok === false && r.error === 'no_registry_config' && !('items' in r), J(r));
  PROPS.ESIGN_REGISTRY_ID = reg; delete PROPS.ESIGN_SIGNED_FOLDER_ID;
  check('config.no-folder', safe(() => contractPdf({ id: PDF_A })).error === 'no_signed_folder_config', '');
  PROPS.ESIGN_SIGNED_FOLDER_ID = dir; PROPS.ESIGN_REGISTRY_ID = 'someOtherSheet0000000000000000';
  check('config.unreadable', safe(() => contractFind({ name: 'Ivan' })).error === 'registry_unreadable', '');
  PROPS.ESIGN_REGISTRY_ID = reg;
}

// ── 16. только чтение: ни одной записи в лист, Drive и свойства за весь прогон ──
check('readonly.no-writes', WRITES.n === 0, J(WRITES.what));

// ── 17. маршруты GET doGet: параметры доезжают, токен проверяется, help знает имена ──
{
  const body = x => safe(() => JSON.parse(x.getContent()));
  const b1 = body(safe(() => doGet({ parameter: { token: 'tok-test', action: 'contract_find', phone: '0812345678',
    date_from: '2026-09-15', date_to: '2026-09-30', limit: '5' } })));
  check('route.find', b1.action === 'contract_find' && b1.ok === true && b1.outcome === 'one' && b1.pick.pdf_id === PDF_B && b1.limit === 5, J(b1).slice(0, 300));
  const b1b = body(safe(() => doGet({ parameter: { token: 'tok-test', action: 'contract_find', name: 'Ivan', bike: 'Nmax 6908' } })));
  check('route.find-name-bike', b1b.ok === true && J(rowsOf(b1b)) === J([2]), J(b1b).slice(0, 200));
  const b2 = body(safe(() => doGet({ parameter: { token: 'tok-test', action: 'contract_pdf', id: PDF_A } })));
  check('route.pdf', b2.action === 'contract_pdf' && b2.ok === true && b2.id === PDF_A && typeof b2.content_b64 === 'string', J(b2).slice(0, 200));
  const b3 = body(safe(() => doGet({ parameter: { token: 'wrong', action: 'contract_pdf', id: PDF_A } })));
  check('route.token', b3.ok === false && b3.error === 'unauthorized' && !('content_b64' in b3), J(b3));
  const b4 = body(safe(() => doGet({ parameter: { token: 'tok-test', action: 'help' } })));
  check('route.help-lists', Array.isArray(b4.actions) && b4.actions.indexOf('contract_find') >= 0 && b4.actions.indexOf('contract_pdf') >= 0, J(b4.actions));
}

const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ cases, failed: failed.length }, null, 1));
process.exit(failed.length ? 1 : 0);
