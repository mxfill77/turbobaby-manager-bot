/**
 * ReadFleet.gs — чтение статуса парка из таблицы "Байки"
 * 
 * Структура "Байки" Лист1:
 *   Строка 1 — дашборд (Доход в день, % в год, ROI)
 *   Строка 2 — заголовки (#, Статус, Название, Год выпуска, ...)
 *   Строка 3+ — данные по каждому байку
 *   
 *   Колонки (1-indexed):
 *     B (2) — Статус (формула: ДОМА / В аренде / В ремонте / У Гоши / Требует ремонта)
 *     C (3) — Название мото
 *     D (4) — Дата покупки
 *     E (5) — Год выпуска
 *     F (6) — Стоимость с доставкой
 *     G (7) — Принёс денег (доход байка за всё время)
 *     S (19) — Статус (текстовый, "В аренде"/"")
 *     T (20) — Кому сдан
 *     U (21) — Срок аренды
 *     V (22) — Дата завершения
 *     W (23) — Платёж в день
 *     X (24) — Долг
 */


/**
 * Возвращает полный статус парка.
 *
 * withCells (необязательный, по умолчанию выключен) — ДОБАВИТЬ к каждому байку поле `cells`
 * с РАЗМЕТКОЙ состояния клеток ТО: value / empty / text (см. cellState_). Параметр опционален
 * НАМЕРЕННО: без него ответ БАЙТ-В-БАЙТ прежний, поэтому ни один сегодняшний потребитель
 * (get_fleet в промпт модели, getDailyPulse, canonicalBikeName_, Contract.js, getIdleBikes)
 * не получает ни одного лишнего байта. Разметку просит только тот, кому нужно РАЗЛИЧИЕ
 * «пусто / прочерк / значение», а не голое число.
 */
function getFleetStatus(withCells) {
  const wantCells = (withCells === true || withCells === 1 ||
                     withCells === '1' || withCells === 'true');
  const sheet = SpreadsheetApp.openById(CONFIG.SHEETS.FLEET).getSheetByName('Лист1');
  if (!sheet) throw new Error('Лист1 не найден в "Байки"');

  // === Дашборд из строки 1 ===
  const dashRange = sheet.getRange('A1:AH1').getValues()[0];
  // По формулам из аудита:
  //   B1 (idx 1) — Доход в день
  //   E1 (idx 4) — Вложено в инвентарь актуально
  //   G1 (idx 6) — Вложено всего
  //   I1 (idx 8) — В месяц (доход × 30.5)
  //   K1 (idx 10) — В год
  //   M1 (idx 12) — % в год -12%
  //   O1 (idx 14) — Оплат всего
  //   Q1 (idx 16) — % в год основной
  //   T1 (idx 19) — Всего мото
  //   V1 (idx 21) — В аренде count
  //   X1 (idx 23) — Дома count
  //   Z1 (idx 25) — В ремонте
  //   AB1 (idx 27) — Требует ремонта
  //   AD1 (idx 29) — У Гоши
  //   AF1 (idx 31) — Всего должников
  
  const dashboard = {
    income_per_day: parseNumber(dashRange[1]),
    invested_actual: parseNumber(dashRange[4]),
    invested_total: parseNumber(dashRange[6]),
    income_per_month: parseNumber(dashRange[8]),
    income_per_year: parseNumber(dashRange[10]),
    payments_total: parseNumber(dashRange[14]),
    percent_per_year: parseNumber(dashRange[16]),
    count_total: parseNumber(dashRange[19]),
    count_rented: parseNumber(dashRange[21]),
    count_home: parseNumber(dashRange[23]),
    count_repair: parseNumber(dashRange[25]),
    count_needs_repair: parseNumber(dashRange[27]),
    count_at_gosha: parseNumber(dashRange[29]),  // устаревший, должно быть 0
    count_debtors: parseNumber(dashRange[31]),
  };

  // === Данные по каждому байку (строки 3-N) ===
  const lastRow = sheet.getLastRow();
  if (lastRow < 3) {
    return { dashboard, bikes: [] };
  }

  // Читаем диапазон A3:X{lastRow}
  const data = sheet.getRange(3, 1, lastRow - 2, 24).getValues();
  
  const bikes = [];
  for (const row of data) {
    const name = row[2];  // C — Название
    if (!name || String(name).trim() === '') continue;  // пропуск пустых
    
    const status = row[1];  // B — Статус (формула)
    
    const bike = {
      number: parseNumber(row[0]),               // A — # (порядковый)
      status: String(status || '').trim(),       // ДОМА / В аренде / ...
      name: String(name).trim(),
      purchase_date: formatDate(row[3]),         // D
      year: parseNumber(row[4]),                 // E
      cost: parseNumber(row[5]),                 // F — стоимость с доставкой
      total_revenue: parseNumber(row[6]),        // G — принёс денег
      mileage: parseNumber(row[7]),              // H — пробег при покупке (стартовый, НЕ текущий)
      oil_last_km: parseNumber(row[8]),          // I — пробег на последней замене масла
      gear_last_km: parseNumber(row[9]),         // J — ТО Gear (редуктор), только скутеры
      abs_last_km: parseNumber(row[10]),         // K — АБС (ABS oil)
      airfilter_last_km: parseNumber(row[11]),   // L — аир фильтр (воздушный)

      // Если в аренде — данные клиента (колонки S-X = индексы 18-23)
      current_rental: status === 'В аренде' ? {
        client: String(row[19] || '').trim(),    // T
        duration: String(row[20] || '').trim(),  // U
        end_date: formatDate(row[21]),           // V
        pay_per_day: parseNumber(row[22]),       // W
        debt: parseNumber(row[23]),              // X
      } : null,
    };

    // Разметка клеток ТО — ТОЛЬКО по явной просьбе (см. шапку функции).
    // Читается СЫРОЕ значение row[i], то самое, которое parseNumber схлопывает в 0.
    if (wantCells) {
      bike.cells = {
        mileage: cellState_(row[7]),             // H
        oil_last_km: cellState_(row[8]),         // I
        gear_last_km: cellState_(row[9]),        // J
        abs_last_km: cellState_(row[10]),        // K
        airfilter_last_km: cellState_(row[11]),  // L
      };
    }

    bikes.push(bike);
  }

  // === Сводка ===
  const summary = {
    total: bikes.length,
    home: bikes.filter(b => b.status === 'ДОМА').length,
    rented: bikes.filter(b => b.status === 'В аренде').length,
    repair: bikes.filter(b => b.status === 'В ремонте' || b.status === 'Требует ремонта').length,
  };

  return { dashboard, summary, bikes };
}


/**
 * Список простаивающих байков (давно не сдавались).
 * Считаем по полю G (Принёс денег) и сравниваем с средним.
 * Альтернатива: ищем в "клиенты" последнюю аренду по каждому байку.
 */
function getIdleBikes(minDaysIdle) {
  minDaysIdle = minDaysIdle || 14;
  
  // Получаем все байки
  const fleet = getFleetStatus();
  const homeBikes = fleet.bikes.filter(b => b.status === 'ДОМА');
  
  // Для каждого ищем последнюю аренду в "клиенты"
  const clientsSheet = getSheet('MANAGER', CONFIG.TABS.CLIENTS);
  const lastRow = clientsSheet.getLastRow();
  if (lastRow < 2) return [];
  
  const clientsData = clientsSheet.getRange(2, 1, lastRow - 1, 6).getValues();
  
  const idle = [];
  const now = new Date();
  
  for (const bike of homeBikes) {
    let lastRentalEnd = null;
    
    // Ищем все аренды этого байка
    for (const row of clientsData) {
      const bikeName = String(row[2] || '').trim();  // C
      if (bikeName !== bike.name) continue;
      
      const endDate = row[5];  // F — дата завершения
      if (endDate instanceof Date) {
        if (!lastRentalEnd || endDate > lastRentalEnd) {
          lastRentalEnd = endDate;
        }
      }
    }
    
    if (lastRentalEnd) {
      const daysIdle = Math.floor((now - lastRentalEnd) / (1000 * 60 * 60 * 24));
      if (daysIdle >= minDaysIdle) {
        idle.push({
          bike: bike.name,
          last_rental_end: formatDate(lastRentalEnd),
          days_idle: daysIdle,
          total_revenue: bike.total_revenue,
        });
      }
    } else {
      // Никогда не сдавался — тоже добавим
      idle.push({
        bike: bike.name,
        last_rental_end: null,
        days_idle: 999,
        total_revenue: bike.total_revenue,
      });
    }
  }
  
  // Сортируем по дням простоя (больше — выше)
  idle.sort((a, b) => b.days_idle - a.days_idle);
  
  return idle;
}


/**
 * Извлекает НОМЕР байка из названия — правило find_bike (зеркало bridge_client.py).
 * Берёт все числа из 3+ цифр, выкидывает кубатуры (cc), возвращает ПОСЛЕДНЕЕ.
 * Кубатура — НЕ номер. Возвращает строку или null.
 */
function plateFromName_(text) {
  var CC = { '125': 1, '150': 1, '155': 1, '300': 1, '350': 1, '400': 1,
             '500': 1, '650': 1, '700': 1, '750': 1, '900': 1 };
  var nums = (String(text == null ? '' : text).toLowerCase().match(/\d{3,}/g) || [])
    .filter(function (n) { return !CC[n]; });
  return nums.length ? nums[nums.length - 1] : null;
}

/**
 * Каноничное имя байка из Лист1 Байки по НОМЕРУ (логика find_bike).
 * Возвращает строку-имя из Лист1 или null (номер не извлекается / байк не найден /
 * Лист1 недоступен). Используется serviceUpsert, чтобы хранить единое имя на байк.
 */
function canonicalBikeName_(query) {
  var plate = plateFromName_(query);
  if (!plate) return null;
  try {
    var bikes = getFleetStatus().bikes || [];
  } catch (e) {
    return null;
  }
  for (var i = 0; i < bikes.length; i++) {
    if (plateFromName_(bikes[i].name) === plate) return bikes[i].name;
  }
  return null;
}

/**
 * Порог правила владельца: понижение пробега БОЛЬШЕ этого числа километров подтверждает
 * Пым или владелец, меньше-или-равно — достаточно названной причины и автора.
 * Зеркало мягкого гейта одометра в splinter (_SOFT_ODO_THRESHOLD = 500).
 */
var OIL_FIX_TRUSTED_DROP = 500;


/**
 * GUARDED-запись «ТО Oil» в Лист1 Байки, колонка I (row[8] 0-based → колонка 9).
 * Резолв байка ТОЛЬКО по номеру (plateFromName_). Пишет ровно одну ячейку (col I).
 * НЕ трогает кол. J «ТО Gear» и любые другие.
 * body: { number:String, oil_km:Number, confirmed:Bool }
 * Возвращает ОБЪЕКТ (не ContentService).
 */
function setFleetOil_(body) {
  try {
    var p = body || {};
    var number = String(p.number == null ? '' : p.number).trim();
    if (!number) return { ok: false, error: 'missing_number' };

    var oil_km = Number(p.oil_km);
    if (!isFinite(oil_km) || oil_km <= 0) return { ok: false, error: 'bad_oil_km' };

    if (p.confirmed !== true) {
      return { ok: false, error: 'not_confirmed',
               message: 'Запись в Лист1 требует confirmed=true' };
    }

    var sheet = SpreadsheetApp.openById(CONFIG.SHEETS.FLEET).getSheetByName('Лист1');
    if (!sheet) return { ok: false, error: 'write_failed', message: 'Лист1 не найден в "Байки"' };

    var lastRow = sheet.getLastRow();
    if (lastRow < 3) return { ok: false, error: 'not_found', number: number };

    // A3:I — нужны C (название, idx 2) и I (ТО Oil, idx 8)
    var data = sheet.getRange(3, 1, lastRow - 2, 9).getValues();
    var matches = [];
    for (var i = 0; i < data.length; i++) {
      var name = String(data[i][2] || '').trim();   // C — Название
      if (!name) continue;
      if (plateFromName_(name) === number) {
        var raw = data[i][8];   // I
        var oldOil = (raw === '' || raw === null || raw === undefined) ? 0 : Number(raw);
        if (!isFinite(oldOil)) oldOil = 0;
        // raw хранится ради ОТКАТА: пустая ячейка («ТО не заводили») обязана вернуться пустой,
        // а не нулём — иначе откат сам испортил бы живую таблицу.
        matches.push({ sheetRow: i + 3, name: name, old_oil: oldOil, raw: raw });
      }
    }

    if (matches.length === 0) return { ok: false, error: 'not_found', number: number };
    if (matches.length > 1) {
      return { ok: false, error: 'ambiguous', number: number,
               matches: matches.map(function (m) { return m.name; }) };
    }

    var hit = matches[0];
    var old_oil = hit.old_oil;

    // ── ВЕТКА «ИСПРАВЛЕНИЕ ОШИБКИ» (04.08.2026) ──────────────────────────────────────────────
    // Сторож убывания на ОБЫЧНОМ пути остаётся ровно таким, каким был: одометр не убывает, и
    // молчаливое понижение — почти всегда ошибка распознавания. Но у ошибки, УЖЕ ЗАПИСАННОЙ в
    // живую таблицу, до сих пор не было штатного лечения: единственным способом оставалась
    // ручная правка ячейки, а владелец рулит с телефона. Ветка открывается ТОЛЬКО парой
    // «названная причина + названный автор» — полумера (одно без другого) ветку НЕ открывает,
    // иначе признак исправления появлялся бы сам собой у любого вызова.
    var fixReason = String(p.fix_reason == null ? '' : p.fix_reason).trim();
    var fixedBy = String(p.fixed_by == null ? '' : p.fixed_by).trim();
    var isFix = !!(fixReason && fixedBy);
    var drop = old_oil - oil_km;

    if (oil_km < old_oil) {
      if (!isFix) {
        // ПРЕЖНЕЕ ПОВЕДЕНИЕ БАЙТ-В-БАЙТ (splinter ветвится именно на этот код ошибки).
        return { ok: false, error: 'oil_decreasing', old_oil: old_oil, new_oil: oil_km,
                 message: 'Новое значение меньше старого — подтверди отдельно' };
      }
      // ПРАВИЛО ВЛАДЕЛЬЦА СОХРАНЕНО: понижение больше OIL_FIX_TRUSTED_DROP км подтверждает
      // Пым или владелец. Доверие приходит СВЕРХУ (бот знает, кто доверенный; мост — нет),
      // поэтому здесь это второй рубеж, а не первый: без признака ветка не идёт.
      if (drop > OIL_FIX_TRUSTED_DROP && p.trusted !== true) {
        return { ok: false, error: 'oil_drop_needs_trusted', old_oil: old_oil, new_oil: oil_km,
                 drop: drop, threshold: OIL_FIX_TRUSTED_DROP,
                 message: 'понижение больше ' + OIL_FIX_TRUSTED_DROP +
                          ' км подтверждает Пым или владелец' };
      }
    }

    // Запись ТОЛЬКО в колонку I (9). Больше ничего не трогаем.
    sheet.getRange(hit.sheetRow, 9).setValue(oil_km);

    // post-write verify: перечитать ровно записанную ячейку кол.I (flush+getValues)
    var full_address = sheetFullAddr_(CONFIG.SHEETS.FLEET, 'Лист1',
                                      sheet.getRange(hit.sheetRow, 9).getA1Notation());
    var vr = verifyWrite_(sheet, hit.sheetRow, 9, 1, 1, [[oil_km]]);
    if (!vr.ok)
      return { ok: false, error: 'verify_failed', full_address: full_address, mismatches: vr.mismatches };

    // ── АУДИТ-СЛЕД ИСПРАВЛЕНИЯ ОБЯЗАТЕЛЕН ────────────────────────────────────────────────────
    // Правило одометра требует след ВСЕГДА. У Лист1 своего места под след нет (живая чужая
    // таблица, свободной колонки нет), поэтому след — строка боевого журнала, и она здесь
    // FAIL-CLOSED: журнал не записался → правку ОТКАТЫВАЕМ. Исправление без следа в живой
    // таблице неотличимо от порчи данных, а «молчаливый пропуск чека» доктрина запрещает прямо.
    var audit_logged = null;
    if (isFix) {
      audit_logged = false;
      try {
        var lg = logWrite_({
          initiator: fixedBy, act: 'set_fleet_oil (исправление)',
          args: 'байк=' + hit.name + '; кол.I ' + old_oil + '→' + oil_km +
                (drop > 0 ? ('; понижение ' + drop + ' км') : '; повышение') +
                (p.trusted === true ? '; trusted=да (Пым/владелец)' : '') +
                '; причина: ' + fixReason,
          result: 'ok', critical: 'исправление пробега в Лист1'
        });
        audit_logged = !!(lg && lg.ok);
      } catch (eLog) {
        audit_logged = false;
      }
      if (!audit_logged) {
        var rolled = false;
        try {
          sheet.getRange(hit.sheetRow, 9).setValue(hit.raw);   // именно raw: пустое вернётся пустым
          rolled = true;
        } catch (eBack) {
          rolled = false;
        }
        return { ok: false, error: 'audit_failed', rolled_back: rolled,
                 old_oil: old_oil, new_oil: oil_km, full_address: full_address,
                 message: 'след исправления не записался — запись ' +
                          (rolled ? 'откачена, повтори позже' : 'НЕ откачена, закрой руками') };
      }
    }

    var out = { ok: true, number: number, bike_name: hit.name, row: hit.sheetRow,
                old_oil: old_oil, new_oil: oil_km, verified: true, full_address: full_address };
    if (isFix) {
      out.correction = { reason: fixReason, by: fixedBy, drop: drop, trusted: p.trusted === true };
      out.rollback_oil = old_oil;      // откат описан ДАННЫМИ: тем же вызовом вернуть это число
      out.audit_logged = audit_logged;
    }
    return out;
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
}


/**
 * GUARDED-запись регламента ТО для НЕмоторных видов: gear→кол.J, abs→кол.K, airfilter→кол.L.
 * Зеркало setFleetOil_; кол.I «ТО Oil» (масло) и H НЕ трогает — для масла отдельный set_fleet_oil.
 * Резолв байка ТОЛЬКО по номеру (plateFromName_). Пишет РОВНО одну ячейку выбранной колонки.
 * body: { number:String, kind:String('gear'|'abs'|'airfilter'), km:Number, confirmed:Bool }
 */
function setFleetService_(body) {
  try {
    var p = body || {};
    var number = String(p.number == null ? '' : p.number).trim();
    if (!number) return { ok: false, error: 'missing_number' };

    // Белый список: вид ТО → 1-based колонка (J=10, K=11, L=12). Кол.I (9, масло) сюда НЕ входит.
    var COLS = { gear: 10, abs: 11, airfilter: 12 };
    var kind = String(p.kind == null ? '' : p.kind).trim().toLowerCase();
    var col = COLS[kind];
    if (!col) return { ok: false, error: 'bad_kind',
                       message: 'kind должен быть gear|abs|airfilter' };

    var km = Number(p.km);
    if (!isFinite(km) || km <= 0) return { ok: false, error: 'bad_km' };

    if (p.confirmed !== true) {
      return { ok: false, error: 'not_confirmed',
               message: 'Запись в Лист1 требует confirmed=true' };
    }

    var sheet = SpreadsheetApp.openById(CONFIG.SHEETS.FLEET).getSheetByName('Лист1');
    if (!sheet) return { ok: false, error: 'write_failed', message: 'Лист1 не найден в "Байки"' };

    var lastRow = sheet.getLastRow();
    if (lastRow < 3) return { ok: false, error: 'not_found', number: number };

    // Читаем C (название, idx 2) и целевую колонку (col-1, 0-based).
    var data = sheet.getRange(3, 1, lastRow - 2, col).getValues();
    var matches = [];
    for (var i = 0; i < data.length; i++) {
      var name = String(data[i][2] || '').trim();   // C — Название
      if (!name) continue;
      if (plateFromName_(name) === number) {
        var raw = data[i][col - 1];
        var oldVal = (raw === '' || raw === null || raw === undefined) ? 0 : Number(raw);
        if (!isFinite(oldVal)) oldVal = 0;
        matches.push({ sheetRow: i + 3, name: name, old_km: oldVal });
      }
    }

    if (matches.length === 0) return { ok: false, error: 'not_found', number: number };
    if (matches.length > 1) {
      return { ok: false, error: 'ambiguous', number: number,
               matches: matches.map(function (m) { return m.name; }) };
    }

    var hit = matches[0];
    // Защита от отката: новое меньше старого — не пишем (как у масла).
    if (km < hit.old_km) {
      return { ok: false, error: 'km_decreasing', old_km: hit.old_km, new_km: km,
               message: 'Новое значение меньше старого — подтверди отдельно' };
    }

    // Запись ТОЛЬКО в выбранную колонку. Больше ничего не трогаем.
    sheet.getRange(hit.sheetRow, col).setValue(km);

    // post-write verify: перечитать ровно записанную ячейку выбранной колонки (flush+getValues)
    var full_address = sheetFullAddr_(CONFIG.SHEETS.FLEET, 'Лист1',
                                      sheet.getRange(hit.sheetRow, col).getA1Notation());
    var vr = verifyWrite_(sheet, hit.sheetRow, col, 1, 1, [[km]]);
    if (!vr.ok)
      return { ok: false, error: 'verify_failed', full_address: full_address, mismatches: vr.mismatches };

    return { ok: true, number: number, bike_name: hit.name, row: hit.sheetRow,
             kind: kind, column: col, old_km: hit.old_km, new_km: km,
             verified: true, full_address: full_address };
  } catch (err) {
    return { ok: false, error: 'write_failed', message: String(err) };
  }
}


// === Утилиты ===

/**
 * Безопасно парсит число из ячейки (может быть string с "฿" и пробелами).
 */
function parseNumber(val) {
  if (val === null || val === undefined || val === '') return 0;
  if (typeof val === 'number') return val;
  // Убираем валюту, пробелы, неразрывные пробелы
  const cleaned = String(val).replace(/[฿$\s\u00A0,]/g, '').replace(',', '.');
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

/**
 * СОСТОЯНИЕ КЛЕТКИ до схлопывания в число — три исхода вместо одного нуля (09.08.2026).
 *
 * parseNumber выше отдаёт 0 в ТРЁХ разных случаях: клетка ПУСТА (строка 476), в клетке
 * НЕ-ЧИСЛО — прочерк, слово, дата (строка 481), и в клетке НАСТОЯЩИЙ НОЛЬ. Наверх все три
 * приезжают неразличимо, поэтому «не измерено» нельзя выразить в принципе: перепись
 * docs/artifacts/2026-08-08-park-overdue-35-of-38-census.md — 12 просрочек из 35 фантомные.
 *
 * cellState_ НЕ ЧИНИТ значения и НЕ судит их: −5000 км, ноль и «35200 Km, 05.07.2026» доезжают
 * такими, какие они есть. Он отвечает ровно на один вопрос — ЧТО в клетке лежало:
 *   value  в клетке число (в т.ч. добытое из живого текста «฿ 12 345») → num = ровно то же
 *          число, которое вернул бы parseNumber;
 *   empty  содержимого нет вовсе (пусто / одни пробелы);
 *   text   содержимое ЕСТЬ, но числом оно не стало (прочерк, слово, дата).
 * Инвариант, ради которого функция написана рядом с parseNumber, а не поодаль:
 *   state === 'value'  ⇔  parseNumber(val) добыт ИЗ СОДЕРЖИМОГО и равен num;
 *   state !== 'value'  ⇔  parseNumber(val) === 0 ФОЛЛБЭКОМ, а не по факту.
 * Инвариант проверяется на ЭТОМ ЖЕ живом файле харнессом tests/fleet_cells_harness.js —
 * поэтому вычистка НЕ должна разойтись с parseNumber. Класс символов здесь на один
 * короче: у parseNumber неразрывный пробел выписан отдельным escape-ом, а в JS его
 * и без того включает `\s` — классы равносильны, и равенство доказано харнессом.
 *
 * raw — сырое содержимое строкой, чтобы про «не-число» можно было СКАЗАТЬ, что именно лежит.
 */
function cellState_(val) {
  if (val === null || val === undefined || val === '') return { state: 'empty', raw: '' };
  if (typeof val === 'number') return { state: 'value', num: val, raw: String(val) };
  const raw = String(val);
  if (raw.trim() === '') return { state: 'empty', raw: raw };
  const cleaned = raw.replace(/[฿$\s,]/g, '').replace(',', '.');
  const n = parseFloat(cleaned);
  if (isNaN(n)) return { state: 'text', raw: raw };
  return { state: 'value', num: n, raw: raw };
}

/**
 * Форматирует дату в ISO string или null.
 */
function formatDate(val) {
  if (!val) return null;
  if (val instanceof Date) {
    return Utilities.formatDate(val, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  }
  return String(val);
}