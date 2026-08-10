/**
 * TurboBaby Bridge — Delivery Zones
 * Зоны доставки мотобайков по Пхукету.
 * Лист «Доставка» в книге «Календарь бронирования» (CONFIG.SHEETS.MANAGER).
 *
 * delivery_zones_init  — одноразовый засев (идемпотентен: лист уже есть → отказ без перезаписи).
 * delivery_zones_get   — read-only, сырьё: зоны + конфиг-блок.
 * delivery_zones_set   — POST-запись: upsert/delete зон по name (строки #CONFIG не трогает).
 */

var DELIVERY_SHEET_NAME = 'Доставка';
var DELIVERY_HEADER = ['зона', 'lat', 'lon', 'цена', 'радиус_км'];
var DELIVERY_ZONES_SEED = [
  ['Раваи',         7.7710, 98.3270, 590, 4],
  ['Чалонг',        7.8465, 98.3390, 590, 4],
  ['Пхукет-таун',   7.8804, 98.3923, 490, 4],
  ['Кейп Панва',    7.8050, 98.4120, 590, 4],
  ['Паклок',        7.9645, 98.4085, 490, 5],
  ['Таланг восток', 7.9256, 98.3672, 490, 5],
  ['Таланг север',  7.9931, 98.3655, 390, 5],
  ['Майкхао',       8.1430, 98.3020, 990, 6],
  ['Аэропорт',      8.1132, 98.3169, 690, 3],
  ['Найтон',        8.0550, 98.2760, 590, 4],
  ['Банг Тао',      7.9910, 98.2930, 290, 4],
  ['Сурин',         7.9788, 98.2770, 290, 3],
  ['Камала',        7.9505, 98.2830, 290, 4],
  ['Патонг',        7.8965, 98.2965, 290, 4],
  ['Карон',         7.8475, 98.2945, 390, 3],
  ['Ката',          7.8200, 98.2985, 490, 3],
];
// Служебный блок ниже зон: пояс 5 км = 1490 ฿; дальше — согласование менеджером.
var DELIVERY_CONFIG_MARKER = '#CONFIG';
var DELIVERY_CONFIG_SEED = [
  ['OUT_BELT_KM',    '5'],
  ['OUT_BELT_PRICE', '1490'],
  ['OUT_BEYOND',     'согласование'],
];

/**
 * Одноразовый init листа «Доставка» (идемпотентен).
 * Лист уже существует → {ok:true, created:false} без перезаписи.
 * Цены/радиусы правит владелец руками после создания.
 */
function deliveryZonesInit_() {
  var ss = SpreadsheetApp.openById(CONFIG.SHEETS.MANAGER);
  if (ss.getSheetByName(DELIVERY_SHEET_NAME)) {
    return { ok: true, created: false, message: 'лист уже существует — не перезаписан' };
  }
  var sheet = ss.insertSheet(DELIVERY_SHEET_NAME);
  sheet.appendRow(DELIVERY_HEADER);
  for (var i = 0; i < DELIVERY_ZONES_SEED.length; i++) {
    sheet.appendRow(DELIVERY_ZONES_SEED[i]);
  }
  // Служебный блок конфигурации: маркер-разделитель + 3 строки key/value
  sheet.appendRow([DELIVERY_CONFIG_MARKER]);
  for (var j = 0; j < DELIVERY_CONFIG_SEED.length; j++) {
    sheet.appendRow(DELIVERY_CONFIG_SEED[j]);
  }
  return {
    ok: true,
    created: true,
    rows: DELIVERY_ZONES_SEED.length,
    sheet: DELIVERY_SHEET_NAME,
  };
}

/**
 * Read-only: все строки листа «Доставка» разделённые на zones (без шапки) и config-блок.
 * Сырьё — без интерпретации; интерпретацию (геодистанция, выбор цены) делает вызывающий код.
 */
function deliveryZonesGet_() {
  var ss = SpreadsheetApp.openById(CONFIG.SHEETS.MANAGER);
  var sheet = ss.getSheetByName(DELIVERY_SHEET_NAME);
  if (!sheet) {
    return {
      ok: false,
      error: 'not_found',
      message: 'лист «Доставка» не найден — сначала delivery_zones_init',
    };
  }
  var lastRow = sheet.getLastRow();
  if (lastRow < 1) return { ok: true, zones: [], config: [] };

  var all = sheet.getRange(1, 1, lastRow, DELIVERY_HEADER.length).getValues();
  var zones = [];
  var config = [];
  var inConfig = false;
  for (var i = 0; i < all.length; i++) {
    var first = String(all[i][0] || '');
    if (first === DELIVERY_CONFIG_MARKER) { inConfig = true; continue; }
    if (first === DELIVERY_HEADER[0]) continue; // пропускаем шапку
    if (inConfig) {
      config.push(all[i]);
    } else {
      zones.push(all[i]);
    }
  }
  return { ok: true, zones: zones, config: config };
}

/**
 * Запись зон (upsert/delete по name) — конверт 5 строк владельца и последующие правки зон.
 * POST {action:'delivery_zones_set', token, zones:[{name,lat,lon,price,radius}|{name,delete:true}]}.
 * Семантика:
 *   • name есть в листе → строка ОБНОВЛЯЕТСЯ на месте (lat/lon/price/radius целиком);
 *   • name нет → строка ДОБАВЛЯЕТСЯ в конец блока зон (ПЕРЕД маркером #CONFIG — иначе
 *     deliveryZonesGet_ отнёс бы её к config-блоку);
 *   • delete:true → строка зоны удаляется (нет такой → имя попадает в missing, не ошибка);
 *   • radius не задан → 0 (колонка legacy: резолвер ПК её игнорирует, лист хранит).
 * Служебные строки НЕ трогаем: шапка «зона» и весь #CONFIG-блок вне досягаемости (скан зон
 * останавливается на маркере; служебные имена в конверте отклоняются валидацией).
 * Валидация ДО записи: битый элемент → отказ ЦЕЛИКОМ, лист не изменён (не полу-применяем).
 * Ответ: {ok, updated, added, deleted[, missing]}.
 */
function deliveryZonesSet_(body) {
  var p = body || {};
  var items = p.zones;
  if (Object.prototype.toString.call(items) !== '[object Array]' || !items.length) {
    return { ok: false, error: 'no_zones',
             message: 'нужен непустой массив zones: [{name, lat, lon, price, radius}|{name, delete:true}]' };
  }
  var ss = SpreadsheetApp.openById(CONFIG.SHEETS.MANAGER);
  var sheet = ss.getSheetByName(DELIVERY_SHEET_NAME);
  if (!sheet) {
    return { ok: false, error: 'not_found',
             message: 'лист «Доставка» не найден — сначала delivery_zones_init' };
  }

  // --- валидация ВСЕГО конверта до первой записи (всё или ничего) ---
  for (var v = 0; v < items.length; v++) {
    var it = items[v] || {};
    var nm = String(it.name == null ? '' : it.name).trim();
    if (!nm) return { ok: false, error: 'bad_item', message: 'элемент #' + v + ': пустое name' };
    if (nm === DELIVERY_HEADER[0] || nm.charAt(0) === '#') {
      return { ok: false, error: 'bad_item',
               message: 'элемент #' + v + ': служебное имя запрещено (' + nm + ')' };
    }
    if (!it['delete']) {
      if (!isFinite(Number(it.lat)) || !isFinite(Number(it.lon)) || !isFinite(Number(it.price))) {
        return { ok: false, error: 'bad_item',
                 message: 'элемент #' + v + ' (' + nm + '): lat/lon/price должны быть числами' };
      }
      if (it.radius != null && it.radius !== '' && !isFinite(Number(it.radius))) {
        return { ok: false, error: 'bad_item',
                 message: 'элемент #' + v + ' (' + nm + '): radius должен быть числом' };
      }
    }
  }

  var updated = 0, added = 0, deleted = 0, missing = [];
  for (var i = 0; i < items.length; i++) {
    var z = items[i];
    var name = String(z.name).trim();
    // Перечитываем колонку имён на КАЖДОЙ итерации: delete/insert сдвигают номера строк.
    // Скан зон останавливается на #CONFIG — совпадение имени в config-блоке невозможно.
    var lastRow = sheet.getLastRow();
    var col = lastRow > 0 ? sheet.getRange(1, 1, lastRow, 1).getValues() : [];
    var rowIdx = -1, markerIdx = -1;
    for (var r = 0; r < col.length; r++) {
      var val = String(col[r][0] == null ? '' : col[r][0]).trim();
      if (val === DELIVERY_CONFIG_MARKER) { markerIdx = r + 1; break; }
      if (val === name) rowIdx = r + 1;
    }
    if (z['delete']) {
      if (rowIdx > 0) { sheet.deleteRow(rowIdx); deleted++; }
      else missing.push(name);
      continue;
    }
    var rowData = [name, Number(z.lat), Number(z.lon), Number(z.price),
                   Number(z.radius == null || z.radius === '' ? 0 : z.radius)];
    if (rowIdx > 0) {
      sheet.getRange(rowIdx, 1, 1, DELIVERY_HEADER.length).setValues([rowData]);
      updated++;
    } else if (markerIdx > 0) {
      sheet.insertRowBefore(markerIdx);
      sheet.getRange(markerIdx, 1, 1, DELIVERY_HEADER.length).setValues([rowData]);
      added++;
    } else {
      sheet.appendRow(rowData);   // листа без #CONFIG-маркера — просто в конец
      added++;
    }
  }
  var res = { ok: true, updated: updated, added: added, deleted: deleted };
  if (missing.length) res.missing = missing;
  return res;
}
