'use strict';
/**
 * Харнесс ESIGNDOOR0410 (04.10.2026): дверь договоров пускает PDF из подпапок «Подписанные/ГГГГ/ММ»
 * и сама находит реестр и папку подписанных, когда свойства проекта не заданы. Исполняет РЕАЛЬНЫЙ
 * код моста в node на мок-реестре и мок-Drive (способ contract_door_gs_harness.js).
 *
 * Источники — правило srcOf: файл есть в КАТАЛОГЕ СБОРКИ `bridge_build_esign/` — берём сборку, иначе
 * ЗЕРКАЛО ПРОДА `bridge_prod/`. `--stdin`: подмена исходников JSON-объектом {имя: текст} — мутанты.
 *
 * Ветки и их ± случаи:
 *   A. предки: папка подписанных на уровне 1/2/3 — отдаём; 4 и вне — not_in_signed_folder с числом
 *      уровней; ошибка чтения родителей файла и предка — parents_unreadable, PDF не отдаётся;
 *   B. адрес реестра: свойство задано — только оно, поиска нет; не задано — единственная таблица
 *      вне корзины; 0 / 2 — отказ с числом, первую не берём; сбой поиска — свой код;
 *   C. адрес папки: свойство задано — только оно; не задано — единственная «Подписанные» в папке
 *      реестра; 0 / 2 — отказ с числом; сбой — свой код;
 *   D. только чтение: ни setProperty, ни записи в лист и Drive за весь прогон.
 * Данные синтетические. Печатает JSON {cases:[{name, pass, detail}], failed}; exit 1 при провалах.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const crypto = require('crypto');

const GS_BUILD = path.join(__dirname, '..', 'bridge_build_esign');
const GS_MIRROR = path.join(__dirname, '..', 'bridge_prod');
function srcOf(name) {
  const inBuild = path.join(GS_BUILD, name);
  return fs.existsSync(inBuild) ? inBuild : path.join(GS_MIRROR, name);
}
const OVERRIDE = process.argv.includes('--stdin') ? JSON.parse(fs.readFileSync(0, 'utf8') || '{}') : {};
function srcText(name) {
  return Object.prototype.hasOwnProperty.call(OVERRIDE, name) ? OVERRIDE[name] : fs.readFileSync(srcOf(name), 'utf8');
}

const WRITES = { n: 0, what: [] };
function wrote(what) { WRITES.n++; WRITES.what.push(what); }
const CALLS = { filesByName: 0, foldersByName: 0, openById: [] };

function iter(list) { let i = 0; return { hasNext: () => i < list.length, next: () => list[i++] }; }

// ── мок-папки: дерево «Мой диск / Контракты DOC / Подписанные / 2026 / 10|09 / глубже» ──
const ID = s => (s + '0000000000000000000000000000').slice(0, 28);
const D = {
  MYDRIVE: ID('dirMyDrive'), CONTRACTS: ID('dirContracts'), SIGNED: ID('dirSigned'), Y2026: ID('dirY2026'),
  M10: ID('dirM10'), M09: ID('dirM09'), DEEP: ID('dirDeep'), OTHER: ID('dirOther'), ERRDIR: ID('dirErr'),
  CYC_A: ID('dirCycA'), CYC_B: ID('dirCycB'), SIGNED2: ID('dirSigned2'), SIGNED_T: ID('dirSignedT'),
};
const FOLDER_PARENTS = {
  [D.MYDRIVE]: [], [D.CONTRACTS]: [D.MYDRIVE], [D.SIGNED]: [D.CONTRACTS], [D.Y2026]: [D.SIGNED],
  [D.M10]: [D.Y2026], [D.M09]: [D.Y2026], [D.DEEP]: [D.M10], [D.OTHER]: [D.MYDRIVE],
  [D.ERRDIR]: 'THROW', [D.CYC_A]: [D.CYC_B], [D.CYC_B]: [D.CYC_A],
  [D.SIGNED2]: [D.CONTRACTS], [D.SIGNED_T]: [D.CONTRACTS],
};
// что лежит «Подписанные» в папке (переключается случаями)
let SIGNED_KIDS = { [D.CONTRACTS]: [D.SIGNED] };
const TRASHED_DIRS = { [D.SIGNED_T]: true };
let FOLDERS_THROW = false;
function folder(id) {
  return {
    getId: () => id,
    isTrashed: () => !!TRASHED_DIRS[id],
    getParents() {
      const ps = FOLDER_PARENTS[id];
      if (ps === 'THROW') throw new Error('parents unreadable: ' + id);
      return iter((ps || []).map(folder));
    },
    getFoldersByName(name) {
      CALLS.foldersByName++;
      if (FOLDERS_THROW) throw new Error('getFoldersByName сорван');
      return iter(name === 'Подписанные' ? (SIGNED_KIDS[id] || []).map(folder) : []);
    },
    createFolder() { wrote('createFolder'); }, setTrashed() { wrote('setTrashed'); },
  };
}

// ── мок-файлы ──
const P = {
  ROOT: ID('pdfRoot'), Y: ID('pdfYear'), M10: ID('pdfM10'), M09: ID('pdfM09'), DEEP: ID('pdfDeep'),
  OUT: ID('pdfOut'), ERR: ID('pdfErrSelf'), ERR2: ID('pdfErrUp'), MULTI: ID('pdfMulti'), CYC: ID('pdfCyc'),
};
const REG = ID('regEsignMain'), REG2 = ID('regEsignTwin'), REG_T = ID('regEsignTrash'), REG_PDF = ID('regAsPdf');
function bytesOf(text) { return Array.from(Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from([0xE2, 0xE3]), Buffer.from(text)])); }
const signedArr = u => u.map(b => (b > 127 ? b - 256 : b));
function makeFile(id, o) {
  const u = bytesOf(o.text || id);
  return {
    getId: () => id, getName: () => o.name || (id + '.pdf'),
    getMimeType: () => o.mime || 'application/pdf', getSize: () => u.length,
    isTrashed: () => !!o.trashed,
    getParents() { if (o.parents === 'THROW') throw new Error('file parents unreadable'); return iter((o.parents || []).map(folder)); },
    getBlob() { return { getBytes: () => signedArr(u.slice()) }; },
    setTrashed() { wrote('setTrashed'); }, moveTo() { wrote('moveTo'); }, setContent() { wrote('setContent'); },
    _unsigned: u,
  };
}
const SHEET_MIME = 'application/vnd.google-apps.spreadsheet';
const FILES = {
  [P.ROOT]: makeFile(P.ROOT, { parents: [D.SIGNED], text: 'root' }),
  [P.Y]: makeFile(P.Y, { parents: [D.Y2026], text: 'year' }),
  [P.M10]: makeFile(P.M10, { parents: [D.M10], text: 'october contract', name: 'Договор октябрь.pdf' }),
  [P.M09]: makeFile(P.M09, { parents: [D.M09], text: 'september contract' }),
  [P.DEEP]: makeFile(P.DEEP, { parents: [D.DEEP], text: 'too deep' }),
  [P.OUT]: makeFile(P.OUT, { parents: [D.OTHER], text: 'outside' }),
  [P.ERR]: makeFile(P.ERR, { parents: 'THROW', text: 'err self' }),
  [P.ERR2]: makeFile(P.ERR2, { parents: [D.ERRDIR, D.M10], text: 'err up' }),
  [P.MULTI]: makeFile(P.MULTI, { parents: [D.OTHER, D.M09], text: 'multi' }),
  [P.CYC]: makeFile(P.CYC, { parents: [D.CYC_A], text: 'cycle' }),
  [REG]: makeFile(REG, { parents: [D.CONTRACTS], mime: SHEET_MIME }),
  [REG2]: makeFile(REG2, { parents: [D.OTHER], mime: SHEET_MIME }),
  [REG_T]: makeFile(REG_T, { parents: [D.CONTRACTS], mime: SHEET_MIME, trashed: true }),
  [REG_PDF]: makeFile(REG_PDF, { parents: [D.CONTRACTS], mime: 'application/pdf' }),
};
const REG_NAME = 'Договоры — реестр подписей (TB e-Sign)';
let SEARCH = [REG];          // что вернёт поиск таблицы по имени (переключается случаями)
let SEARCH_THROW = false;

// ── реестр: одна таблица на оба id (REG и REG2), разница видна по CALLS.openById ──
const HEADERS = ['ID документа', 'Клиент', 'Дата договора', 'Статус', 'Подписан', 'PDF (подписанный)', 'Телефон', 'Байк'];
const VIEW = id => 'https://drive.google.com/file/d/' + id + '/view';
const ROWS = [HEADERS].concat(Object.keys(P).map((k, i) => ['E-' + (i + 1), 'Client ' + k, '2026-10-01', 'ПОДПИСАН',
  '2026-10-01 10:00', VIEW(P[k]), '+66 81 000 00' + String(10 + i), 'PCX ' + (1000 + i)]));
function sheet() {
  const grid = ROWS;
  const width = HEADERS.length;
  return {
    getLastRow: () => grid.length, getLastColumn: () => width,
    getRange(a, b, c, d) {
      const nr = c === undefined ? 1 : c, nc = d === undefined ? 1 : d;
      const block = fn => { const out = []; for (let r = a; r < a + nr; r++) { const row = []; for (let k = b; k < b + nc; k++) row.push(fn(r, k)); out.push(row); } return out; };
      return {
        getValues: () => block((r, k) => (grid[r - 1] && grid[r - 1][k - 1] !== undefined ? grid[r - 1][k - 1] : '')),
        getRichTextValues: () => block(() => ({ getLinkUrl: () => null })),
        getFormulas: () => block(() => ''),
        setValue() { wrote('setValue'); }, setValues() { wrote('setValues'); },
      };
    },
    appendRow() { wrote('appendRow'); },
  };
}

const PROPS = {};
function setProps(o) { for (const k of Object.keys(PROPS)) delete PROPS[k]; Object.assign(PROPS, { BRIDGE_TOKEN: 'tok-test' }, o); }
setProps({ ESIGN_REGISTRY_ID: REG, ESIGN_SIGNED_FOLDER_ID: D.SIGNED });

global.SpreadsheetApp = { openById(id) {
  CALLS.openById.push(id);
  if (id !== REG && id !== REG2) throw new Error('no access: ' + id);
  return { getSheetByName: n => (n === 'Реестр' ? sheet() : null), insertSheet() { wrote('insertSheet'); } };
} };
global.DriveApp = {
  getFileById(id) { if (!FILES[id]) throw new Error('File not found: ' + id); return FILES[id]; },
  getFilesByName(name) {
    CALLS.filesByName++;
    if (SEARCH_THROW) throw new Error('поиск Drive сорван');
    return iter(name === REG_NAME ? SEARCH.map(id => FILES[id]) : []);
  },
  getFolderById: id => folder(id),
  createFile() { wrote('createFile'); }, createFolder() { wrote('createFolder'); },
};
global.PropertiesService = { getScriptProperties: () => ({
  getProperty: k => (k in PROPS ? PROPS[k] : null),
  setProperty: () => wrote('setProperty'), setProperties: () => wrote('setProperties'), deleteProperty: () => wrote('deleteProperty'),
}) };
global.Session = { getScriptTimeZone: () => 'Asia/Bangkok' };
global.Utilities = {
  formatDate(d, tz, fmt) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(d).map(p => [p.type, p.value]));
    const day = parts.year + '-' + parts.month + '-' + parts.day;
    return fmt === 'yyyy-MM-dd' ? day : day + ' ' + parts.hour + ':' + parts.minute;
  },
  DigestAlgorithm: { SHA_256: 'SHA_256' },
  computeDigest: (alg, bytes) => signedArr(Array.from(crypto.createHash('sha256').update(Buffer.from(bytes.map(b => b & 0xff))).digest())),
  base64Encode: bytes => Buffer.from(bytes.map(b => b & 0xff)).toString('base64'),
  getUuid: () => 'uuid',
};
global.ContentService = {
  MimeType: { JSON: 'application/json' },
  createTextOutput(s) { return { content: s, setMimeType() { return this; }, getContent() { return this.content; } }; },
};
global.Logger = { log: () => {} };

for (const f of ['Config.js', 'BotData.js', 'Bridge.js', 'ContractDoor.js'])
  vm.runInThisContext(srcText(f), { filename: srcOf(f) });

const cases = [];
function check(name, cond, detail) { cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) }); }
function safe(fn) { try { return fn(); } catch (e) { return { ok: false, error: 'THROWN', message: String(e && e.message) }; } }
const J = x => JSON.stringify(x);
const pdf = id => safe(() => contractPdf({ id }));
const noContent = r => r && !('content_b64' in r);
function reset() { CALLS.filesByName = 0; CALLS.foldersByName = 0; CALLS.openById = []; SEARCH = [REG]; SEARCH_THROW = false;
  FOLDERS_THROW = false; SIGNED_KIDS = { [D.CONTRACTS]: [D.SIGNED] }; setProps({ ESIGN_REGISTRY_ID: REG, ESIGN_SIGNED_FOLDER_ID: D.SIGNED }); }

// ── A. предки: «Подписанные/ГГГГ/ММ» пускается, глубже и вне — нет ──
{
  reset();
  const r1 = pdf(P.ROOT);
  check('anc.level1-ok', r1.ok === true && r1.folder_level === 1, J(r1).slice(0, 200));
  const r2 = pdf(P.Y);
  check('anc.level2-ok', r2.ok === true && r2.folder_level === 2, J(r2).slice(0, 200));
  const r3 = pdf(P.M10);
  const want = FILES[P.M10]._unsigned;
  check('anc.level3-month-ok', r3.ok === true && r3.folder_level === 3 && r3.name === 'Договор октябрь.pdf'
    && r3.sha256 === crypto.createHash('sha256').update(Buffer.from(want)).digest('hex'), J(r3).slice(0, 200));
  check('anc.other-month-ok', pdf(P.M09).folder_level === 3, 'сентябрь пускается так же, как октябрь');
  const r4 = pdf(P.DEEP);
  check('anc.level4-refused', r4.ok === false && r4.error === 'not_in_signed_folder' && r4.levels_checked === 3
    && r4.levels_max === 3 && noContent(r4), J(r4));
  const ro = pdf(P.OUT);
  check('anc.outside-refused', ro.ok === false && ro.error === 'not_in_signed_folder' && typeof ro.levels_checked === 'number'
    && ro.levels_max === 3 && noContent(ro), J(ro));
  const rm = pdf(P.MULTI);
  check('anc.multi-parent-ok', rm.ok === true && rm.folder_level === 3, J(rm).slice(0, 200));
  const rc = pdf(P.CYC);
  check('anc.cycle-terminates', rc.ok === false && rc.error === 'not_in_signed_folder' && noContent(rc), J(rc));
  const re1 = pdf(P.ERR);
  check('anc.file-parents-error', re1.ok === false && re1.error === 'parents_unreadable' && re1.level === 1 && noContent(re1), J(re1));
  const re2 = pdf(P.ERR2);
  check('anc.ancestor-error', re2.ok === false && re2.error === 'parents_unreadable' && re2.level === 2 && noContent(re2), J(re2));
  check('anc.config-property', r3.config && r3.config.registry === 'property' && r3.config.signed_folder === 'property', J(r3.config));
  check('anc.no-search-with-props', CALLS.filesByName === 0 && CALLS.foldersByName === 0, J(CALLS));
}

// ── B. адрес реестра: свойство — только оно; нет — единственная таблица вне корзины ──
{
  reset(); SEARCH = [REG2];
  const f1 = safe(() => contractFind({ name: 'Client' }));
  check('reg.property-only', f1.ok === true && f1.config && f1.config.registry === 'property' && CALLS.filesByName === 0
    && J(CALLS.openById) === J([REG]), J([f1.config, CALLS]));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG];
  const f2 = safe(() => contractFind({ name: 'Client' }));
  check('reg.search-one', f2.ok === true && f2.config && f2.config.registry === 'search' && CALLS.filesByName === 1
    && J(CALLS.openById) === J([REG]), J([f2.config, CALLS]));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [];
  const f3 = safe(() => contractFind({ name: 'Client' }));
  check('reg.search-zero', f3.ok === false && f3.error === 'no_registry_config' && f3.found === 0 && f3.source === 'search'
    && !('items' in f3) && CALLS.openById.length === 0, J(f3));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG, REG2];
  const f4 = safe(() => contractFind({ name: 'Client' }));
  check('reg.search-two-refused', f4.ok === false && f4.error === 'registry_ambiguous' && f4.found === 2 && f4.source === 'search'
    && CALLS.openById.length === 0 && !('items' in f4), J([f4, CALLS]));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG_T, REG];
  const f5 = safe(() => contractFind({ name: 'Client' }));
  check('reg.trash-ignored', f5.ok === true && f5.config.registry === 'search' && J(CALLS.openById) === J([REG]), J([f5.error, CALLS]));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG_PDF, REG];
  const f6 = safe(() => contractFind({ name: 'Client' }));
  check('reg.non-sheet-ignored', f6.ok === true && J(CALLS.openById) === J([REG]), J([f6.error, CALLS]));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG_T];
  const f7 = safe(() => contractFind({ name: 'Client' }));
  check('reg.only-trashed-zero', f7.ok === false && f7.error === 'no_registry_config' && f7.found === 0, J(f7));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH_THROW = true;
  const f8 = safe(() => contractFind({ name: 'Client' }));
  check('reg.search-failed', f8.ok === false && f8.error === 'registry_lookup_failed' && f8.source === 'search' && !('items' in f8), J(f8));

  reset(); delete PROPS.ESIGN_REGISTRY_ID; SEARCH = [REG, REG2];
  const p4 = pdf(P.M10);
  check('reg.pdf-two-refused', p4.ok === false && p4.error === 'registry_ambiguous' && p4.found === 2 && noContent(p4)
    && CALLS.openById.length === 0, J(p4));
  check('reg.search-no-write', WRITES.n === 0, J(WRITES.what));
}

// ── C. адрес папки: свойство — только оно; нет — единственная «Подписанные» в папке реестра ──
{
  reset(); SIGNED_KIDS = { [D.CONTRACTS]: [D.SIGNED2] };
  const c1 = pdf(P.M10);
  check('dir.property-only', c1.ok === true && c1.config.signed_folder === 'property' && CALLS.foldersByName === 0, J([c1.config, CALLS]));

  reset(); setProps({});
  const c2 = pdf(P.M10);
  check('dir.no-props-month-pdf-ok', c2.ok === true && c2.folder_level === 3 && c2.config && c2.config.registry === 'search'
    && c2.config.signed_folder === 'search' && typeof c2.content_b64 === 'string', J(c2).slice(0, 300));
  check('dir.no-props-other-month-ok', pdf(P.M09).ok === true, 'сентябрь без свойств');
  const c2d = pdf(P.DEEP);
  check('dir.no-props-deep-refused', c2d.error === 'not_in_signed_folder' && c2d.levels_checked === 3 && noContent(c2d), J(c2d));

  reset(); delete PROPS.ESIGN_SIGNED_FOLDER_ID; SIGNED_KIDS = {};
  const c3 = pdf(P.M10);
  check('dir.search-zero', c3.ok === false && c3.error === 'no_signed_folder_config' && c3.found === 0 && c3.source === 'search'
    && noContent(c3), J(c3));

  reset(); delete PROPS.ESIGN_SIGNED_FOLDER_ID; SIGNED_KIDS = { [D.CONTRACTS]: [D.SIGNED, D.SIGNED2] };
  const c4 = pdf(P.M10);
  check('dir.search-two-refused', c4.ok === false && c4.error === 'signed_folder_ambiguous' && c4.found === 2 && noContent(c4), J(c4));

  reset(); delete PROPS.ESIGN_SIGNED_FOLDER_ID; SIGNED_KIDS = { [D.CONTRACTS]: [D.SIGNED_T, D.SIGNED] };
  const c5 = pdf(P.M10);
  check('dir.trash-ignored', c5.ok === true && c5.config.signed_folder === 'search', J(c5).slice(0, 200));

  reset(); delete PROPS.ESIGN_SIGNED_FOLDER_ID; FOLDERS_THROW = true;
  const c6 = pdf(P.M10);
  check('dir.search-failed', c6.ok === false && c6.error === 'signed_folder_lookup_failed' && noContent(c6), J(c6));

  reset(); delete PROPS.ESIGN_SIGNED_FOLDER_ID;
  const c7 = pdf(P.M10);
  check('dir.registry-property-folder-search', c7.ok === true && c7.config.registry === 'property' && c7.config.signed_folder === 'search', J(c7.config));

  reset(); setProps({}); SEARCH = [];
  const c8 = pdf(P.M10);
  check('dir.no-registry-no-folder', c8.ok === false && c8.error === 'no_registry_config' && c8.found === 0 && noContent(c8)
    && CALLS.foldersByName === 0, J(c8));

  reset(); setProps({}); SEARCH = [REG2];   // реестр нашёлся вне «Контракты DOC» → «Подписанных» рядом нет
  const c9 = pdf(P.M10);
  check('dir.found-registry-no-folder-near', c9.ok === false && c9.error === 'no_signed_folder_config' && c9.found === 0, J(c9));
}

// ── маршрут GET: без свойств PDF из папки месяца доезжает, ответ называет источник ──
{
  reset(); setProps({});
  const b = safe(() => JSON.parse(doGet({ parameter: { token: 'tok-test', action: 'contract_pdf', id: P.M10 } }).getContent()));
  check('route.pdf-no-props', b.action === 'contract_pdf' && b.ok === true && b.folder_level === 3
    && b.config && b.config.signed_folder === 'search', J(b).slice(0, 300));
  const f = safe(() => JSON.parse(doGet({ parameter: { token: 'tok-test', action: 'contract_find', name: 'Client' } }).getContent()));
  check('route.find-config', f.ok === true && f.config && f.config.registry === 'search', J(f).slice(0, 200));
}

// ── D. только чтение за весь прогон ──
check('readonly.no-writes', WRITES.n === 0, J(WRITES.what));

const failed = cases.filter(c => !c.pass);
console.log(JSON.stringify({ cases, failed: failed.length }, null, 1));
process.exit(failed.length ? 1 : 0);
