'use strict';
/**
 * Харнесс: delivery_zones_init / delivery_zones_get из bridge_prod/Delivery.js
 * исполняется в Node.js с мок-SpreadsheetApp (Config.js нужен для CONFIG.SHEETS.MANAGER).
 * Печатает JSON {cases:[{name, pass, detail}]}; exit 1 при провалах.
 * Запускается из tests/test_delivery_gs.py (в гейте).
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// Источник .js — ЗЕРКАЛО ПРОДА `bridge_prod/` в этом репо (задеплоенная версия, паспорт
// MIRROR.json). Рабочая папка /root/turbobaby-bridge-gs обезврежена 10.08.2026 и ОТСТАЁТ от
// прода — харнесс, читающий её, проверял бы не тот код, что живёт в мосте.
const GS_DIR      = path.join(__dirname, '..', 'bridge_prod');
const CONFIG_JS   = path.join(GS_DIR, 'Config.js');
const DELIVERY_JS = path.join(GS_DIR, 'Delivery.js');

// ── мок листа поверх 2D-массива (1-indexed, AppScript-стиль) ──
function makeSheet(rows) {
  const WIDTH = 10;
  const grid = rows.map(r => { const a = r.slice(); while (a.length < WIDTH) a.push(''); return a; });
  function ensureRow(n) { while (grid.length < n) grid.push(new Array(WIDTH).fill('')); }
  return {
    grid,
    getLastRow() {
      for (let i = grid.length - 1; i >= 0; i--)
        if (grid[i].some(v => v !== '' && v !== null && v !== undefined)) return i + 1;
      return 0;
    },
    appendRow(arr) {
      const a = arr.slice(); while (a.length < WIDTH) a.push('');
      grid.push(a);
    },
    getRange(r, c, nr, nc) {
      return {
        getValues() {
          const out = [];
          for (let i = r; i < r + nr; i++) { ensureRow(i); out.push(grid[i - 1].slice(c - 1, c - 1 + nc)); }
          return out;
        },
      };
    },
  };
}

// ── мок SpreadsheetApp с одной книгой MANAGER ──
function makeEnv(existingDelivery) {
  const sheets = {};
  if (existingDelivery) sheets['Доставка'] = existingDelivery;

  const ss = {
    getSheetByName(name) { return sheets[name] || null; },
    insertSheet(name) {
      const s = makeSheet([]);
      sheets[name] = s;
      return s;
    },
  };
  global.SpreadsheetApp = {
    openById(_id) { return ss; },
    flush() {},
  };
  global.PropertiesService = {
    getScriptProperties() { return { getProperty() { return 'fake-token'; } }; },
  };
  global.Logger = { log() {} };
  return ss;
}

// Загружаем Config.js (нужен CONFIG.SHEETS.MANAGER) затем Delivery.js
// PropertiesService заглушка уже в global выше
global.PropertiesService = { getScriptProperties() { return { getProperty() { return 'fake-token'; } }; } };
global.SpreadsheetApp = { openById() { return {}; } };
global.Logger = { log() {} };

vm.runInThisContext(fs.readFileSync(CONFIG_JS, 'utf8'),   { filename: CONFIG_JS });
vm.runInThisContext(fs.readFileSync(DELIVERY_JS, 'utf8'), { filename: DELIVERY_JS });

const cases = [];
function check(name, cond, detail) {
  cases.push({ name, pass: !!cond, detail: detail === undefined ? '' : String(detail) });
}

// ═══════════════════════════════════════════════════════════
// 1. Константы модуля
// ═══════════════════════════════════════════════════════════
check('const.sheet_name',  DELIVERY_SHEET_NAME === 'Доставка',   DELIVERY_SHEET_NAME);
check('const.header.len',  DELIVERY_HEADER.length === 5,          DELIVERY_HEADER.length);
check('const.header.cols', DELIVERY_HEADER.join('|') === 'зона|lat|lon|цена|радиус_км',
                           DELIVERY_HEADER.join('|'));
check('const.zones.count', DELIVERY_ZONES_SEED.length === 16,     DELIVERY_ZONES_SEED.length);
check('const.config.rows', DELIVERY_CONFIG_SEED.length === 3,     DELIVERY_CONFIG_SEED.length);

// ═══════════════════════════════════════════════════════════
// 2. deliveryZonesInit_ — свежая книга
// ═══════════════════════════════════════════════════════════
{
  makeEnv(null);
  const r = deliveryZonesInit_();
  check('init.ok',      r.ok === true,                r.message || '');
  check('init.created', r.created === true,           String(r.created));
  check('init.rows',    r.rows === 16,                r.rows);
  check('init.sheet',   r.sheet === 'Доставка',       r.sheet);

  // Проверяем содержимое созданного листа
  const ss = SpreadsheetApp.openById('x');
  const sheet = ss.getSheetByName('Доставка');
  check('init.sheet_exists', !!sheet, 'sheet должен существовать');
  // строк = 1 шапка + 16 зон + 1 маркер + 3 конфига = 21
  check('init.total_rows', sheet.getLastRow() === 21, sheet.getLastRow());

  // Шапка (строка 1)
  const hdr = sheet.getRange(1, 1, 1, 5).getValues()[0];
  check('init.hdr.0', hdr[0] === 'зона',       hdr[0]);
  check('init.hdr.4', hdr[4] === 'радиус_км',  hdr[4]);

  // Первая зона (строка 2)
  const z1 = sheet.getRange(2, 1, 1, 5).getValues()[0];
  check('init.z1.name',  z1[0] === 'Раваи',  z1[0]);
  check('init.z1.lat',   z1[1] === 7.7710,   z1[1]);
  check('init.z1.lon',   z1[2] === 98.3270,  z1[2]);
  check('init.z1.price', z1[3] === 590,      z1[3]);
  check('init.z1.rad',   z1[4] === 4,        z1[4]);

  // Последняя зона (строка 17)
  const z16 = sheet.getRange(17, 1, 1, 5).getValues()[0];
  check('init.z16.name',  z16[0] === 'Ката', z16[0]);
  check('init.z16.price', z16[3] === 490,    z16[3]);
  check('init.z16.rad',   z16[4] === 3,      z16[4]);

  // Маркер конфига (строка 18)
  const mkr = sheet.getRange(18, 1, 1, 5).getValues()[0];
  check('init.marker', mkr[0] === '#CONFIG', mkr[0]);

  // Конфиг-блок (строки 19–21)
  const cfg = sheet.getRange(19, 1, 3, 2).getValues();
  check('init.cfg.belt_km',    cfg[0][0] === 'OUT_BELT_KM'    && cfg[0][1] === '5',           JSON.stringify(cfg[0]));
  check('init.cfg.belt_price', cfg[1][0] === 'OUT_BELT_PRICE' && cfg[1][1] === '1490',        JSON.stringify(cfg[1]));
  check('init.cfg.beyond',     cfg[2][0] === 'OUT_BEYOND'     && cfg[2][1] === 'согласование', JSON.stringify(cfg[2]));
}

// ═══════════════════════════════════════════════════════════
// 3. deliveryZonesInit_ — идемпотентность (лист уже существует)
// ═══════════════════════════════════════════════════════════
{
  const existing = makeSheet([['зона', 'lat', 'lon', 'цена', 'радиус_км']]);
  makeEnv(existing);
  const r = deliveryZonesInit_();
  check('idempotent.ok',          r.ok === true,         '');
  check('idempotent.not_created', r.created === false,   String(r.created));
  check('idempotent.message',     r.message.includes('уже существует'), r.message);
  // убедимся, что лист НЕ был перезаписан (строк по-прежнему 1, а не 21)
  const ss = SpreadsheetApp.openById('x');
  const sheet = ss.getSheetByName('Доставка');
  check('idempotent.rows_untouched', sheet.getLastRow() === 1, sheet.getLastRow());
}

// ═══════════════════════════════════════════════════════════
// 4. deliveryZonesGet_ — нет листа
// ═══════════════════════════════════════════════════════════
{
  makeEnv(null);
  const r = deliveryZonesGet_();
  check('get.not_found.ok',    r.ok === false,         '');
  check('get.not_found.error', r.error === 'not_found', r.error);
}

// ═══════════════════════════════════════════════════════════
// 5. deliveryZonesGet_ — после init (живой формат листа)
// ═══════════════════════════════════════════════════════════
{
  makeEnv(null);
  deliveryZonesInit_(); // заполняем лист
  const r = deliveryZonesGet_();
  check('get.ok',          r.ok === true,  r.error || '');
  check('get.zones.count', r.zones.length === 16, r.zones.length);
  check('get.config.count', r.config.length === 3, r.config.length);

  // Первая зона (col 0..4)
  check('get.z1.name',  r.zones[0][0] === 'Раваи', r.zones[0][0]);
  check('get.z1.price', r.zones[0][3] === 590,      r.zones[0][3]);

  // Последняя зона
  check('get.z16.name',  r.zones[15][0] === 'Ката', r.zones[15][0]);
  check('get.z16.rad',   r.zones[15][4] === 3,       r.zones[15][4]);

  // Конфиг-блок: [[key,val,...], ...]
  check('get.cfg.belt_km',    r.config[0][0] === 'OUT_BELT_KM'    && r.config[0][1] === '5',    '');
  check('get.cfg.belt_price', r.config[1][0] === 'OUT_BELT_PRICE' && r.config[1][1] === '1490', '');
  check('get.cfg.beyond',     r.config[2][0] === 'OUT_BEYOND'     && r.config[2][1] === 'согласование', '');
}

// ═══════════════════════════════════════════════════════════
// 6. deliveryZonesGet_ — пустой лист (без строк)
// ═══════════════════════════════════════════════════════════
{
  makeEnv(makeSheet([]));
  const r = deliveryZonesGet_();
  check('get.empty.ok',     r.ok === true,       '');
  check('get.empty.zones',  r.zones.length === 0, r.zones.length);
  check('get.empty.config', r.config.length === 0, r.config.length);
}

// ─── итог ───
const pass = cases.filter(c => c.pass).length;
const fail = cases.filter(c => !c.pass).length;
process.stdout.write(JSON.stringify({ cases, pass, fail }) + '\n');
if (fail > 0) process.exit(1);
