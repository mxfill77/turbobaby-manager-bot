/**
 * TurboBaby Bridge — Config
 * 
 * Все ID файлов Google Drive и настройки в одном месте.
 * Токен авторизации хранится в Script Properties (НЕ в коде!).
 * 
 * Как добавить токен:
 *   Project Settings → Script Properties → Add property
 *   Property: BRIDGE_TOKEN
 *   Value: (любая случайная строка, например: tb_a8f3kx9p2nz7q1r5)
 */

const CONFIG = {
  // === Google Sheets ===
  SHEETS: {
    MANAGER: '1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0',    // "менеджеру Байки" — CRM
    FLEET:   '1ZBCmVvzoFu7X0td7O5T5xSJplK8m8h9wvdESBc0a1EE',    // "Байки" — парк + доход
    PRICES:  '1tN1XY0CqMDe-S-fs6eFAYkGPBZPt0__H1pLyh5DO2x0',    // "Цены"
    SALARY:  '1hC7aA9oOWwuac2CkKKuTvOV9UVMG2b-3e5s4s8GIeUk',    // "Зарплаты"
  },

  // === Google Drive Folders ===
  FOLDERS: {
    PASSPORTS:  '1OhIwNe98D5zN6jp51GVTghnFrkd0nRPu',
    CONTRACTS:  '1GX7SIqoskzSuThS4e4EbjeX-B0N_CKxK',
    MAIN:       '19UHmWP1dsb1ADk8nwpZThOP0pCu_uhea',
  },

  // === Sheet Names (внутри SHEETS.MANAGER) ===
  TABS: {
    CLIENTS:    'клиенты',                  // главная таблица аренд
    CALENDAR:   'Календарь бронирования',   // фильтр свободных байков
    PRICES_ALT: 'цены альт',                // калькулятор цен
    BIKES_LIST: 'список мото',              // 38 байков
  },

  // === Колонки в листе "клиенты" (1-indexed для удобства) ===
  CLIENT_COLS: {
    STATUS:       1,   // A — "В аренде" / "Завершена"
    AUTO_CNCL:    2,   // B — "ON" / "OFF"
    BIKE:         3,   // C — название мото
    NAME:         4,   // D — имя клиента
    DATE_START:   5,   // E — дата начала
    DATE_END:     6,   // F — дата завершения (с временем)
    DURATION:     7,   // G — срок (формула "X Д" / "X М")
    PAY_PER_DAY:  8,   // H — платёж в день
    DEBT:         9,   // I — долг (формула)
    TO_PAY:       10,  // J — к оплате (формула)
    PAID:         11,  // K — оплачено
    PAY_MONTH:    12,  // L — платёж в месяц (для скрипта)
    PAY_DAY:      13,  // M — платёж в день (для скрипта)
    KM_INITIAL:   14,  // N — пробег на момент сдачи
    DEPOSIT:      19,  // S — залог
    HELMETS:      20,  // T — шлемы
    CONTACTS:     21,  // U — телефон/телеграм
    NOTE:         22,  // V — примечание
    AUTO_STATUS:  23,  // W — формула автостатуса
    TYPE:         24,  // X — "мото"/"скутер"
  },

  // === Авторизация ===
  // Токен для защиты Web App от случайных запросов.
  // Получаем из Script Properties (безопасно).
  get TOKEN() {
    const t = PropertiesService.getScriptProperties().getProperty('BRIDGE_TOKEN');
    if (!t) {
      throw new Error(
        'BRIDGE_TOKEN не настроен. ' +
        'Project Settings → Script Properties → Add: BRIDGE_TOKEN'
      );
    }
    return t;
  },

  // === Версия Bridge ===
  VERSION: '1.0.0',
  STARTED_AT: '2026-05-28',
};

/**
 * Возвращает Sheet объект по логическому имени.
 * Пример: getSheet('MANAGER', 'клиенты')
 */
function getSheet(sheetKey, tabName) {
  const fileId = CONFIG.SHEETS[sheetKey];
  if (!fileId) throw new Error(`Unknown sheet key: ${sheetKey}`);
  
  const ss = SpreadsheetApp.openById(fileId);
  const tab = ss.getSheetByName(tabName);
  if (!tab) throw new Error(`Tab "${tabName}" not found in ${sheetKey}`);
  
  return tab;
}

/**
 * Проверка токена авторизации.
 * Возвращает true если токен валидный.
 */
function verifyToken(providedToken) {
  if (!providedToken) return false;
  return providedToken === CONFIG.TOKEN;
}
