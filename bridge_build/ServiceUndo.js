/**
 * ServiceUndo.gs — ОТМЕНА ЗАПИСИ ТО: память о вытеснении + дверь возврата.
 *
 * ПОЧЕМУ ЭТОГО НЕ БЫЛО (разбор 22.08.2026, docs/artifacts/2026-08-22-bridge-lower-registers.md).
 * Регистры ТО (Лист1 «Байки»: I масло · J редуктор · K ABS · L воздушный фильтр) мост умеет
 * поднимать и не умеет понижать: сторож `km_decreasing` / `oil_decreasing` называет себя
 * «Защита от отката» и смотрит РОВНО в одну сторону. Понижение за 82 суток понадобилось дважды
 * и оба раза как ОТМЕНА ошибки (15.07 масло 24997 вместо 24500; 22.08 кол.J 41641, которую
 * вернули РУКОЙ). Признака, отличающего отмену от скрутки, у моста не было НИ ОДНОГО: слова
 * `fix_reason`/`fixed_by` заполняет сам вызывающий, `trusted` мост проверить не может и говорит
 * это о себе дословно (ReadFleet: «мост — нет»), билет токен-замка не связан ни с байком, ни с
 * колонкой, ни с числом.
 *
 * ПРИЗНАК, КОТОРЫЙ ЗДЕСЬ ЗАВЕДЁН, — НЕ СЛОВА, А ПАМЯТЬ И СЛИЧЕНИЕ.
 *   1. НАРУЖУ ЧИСЛО ВНИЗ НЕ ПРИНИМАЕТСЯ ВОВСЕ. Дверь принимает ССЫЛКУ НА АКТ (`act`), а прежнее
 *      значение достаёт из СВОЕЙ памяти — строки боевого журнала, которую мост написал сам в
 *      момент вытеснения. Скрутка предъявить такую строку не может ФИЗИЧЕСКИ: произвольное
 *      число мост никогда не вытеснял.
 *   2. СЛИЧЕНИЕ (CAS). Отмена идёт, только если в клетке ДО СИХ ПОР ровно то число, которое
 *      записал акт, И возвращается ровно то, что этот акт вытеснил. Клетку тронула чужая рука —
 *      ОТКАЗ и зов владельца, а не затирание (в т.ч. случай «уже вернули рукой» — 5960).
 *   3. ТОЛЬКО ПОСЛЕДНЯЯ запись по паре «байк × колонка»; отмена отмены запрещена.
 *   4. КАЖДЫЙ ОТКАТ САМ ЛОЖИТСЯ В ЖУРНАЛ событием — след РАСТЁТ, а не переписывается.
 *
 * ОБЕ БАЗЫ ИЛИ НИ ОДНОЙ. Один акт записи ТО меняет мир в двух хранилищах: живой Лист1 (кол.
 * I/J/K/L) и ЗЕРКАЛО «обслуживание» в своей таблице бота (`last_service_km`). Отмена, вернувшая
 * одну базу и не вернувшая вторую, — это НЕ частичный успех, а расхождение, которое само не
 * срастётся: живьём 22.08 по 5960 Лист1 J вернули рукой на 41357, а зеркало осталось на 41641 —
 * 284 км в ОПАСНУЮ сторону (напоминание о ТО придёт позже, чем должно). Поэтому здесь: не
 * удалось вернуть вторую базу → КОМПЕНСИРУЕМ первую и отказываем целиком.
 *
 * ПОЧЕМУ КОМПЕНСАЦИЯ — НЕ ВТОРОЕ КРАСНОЕ. Компенсация возвращает клетку в то состояние, в
 * котором её застала дверь, то есть пишет БОЛЬШЕЕ число — в БЕЗОПАСНОМ направлении, которое
 * сторож не запрещал никогда. Скруткой она не может быть по устройству. Тот же приём уже живёт
 * в мосте: `setFleetOil_` откатывает собственную правку, когда не лёг след исправления.
 *
 * ГРАНИЦЫ. Дверь не трогает `current_km` зеркала (мир правда проехал — это факт о байке, а не
 * наша запись), не трогает строки событий и заявку ТО (их возвращает вызывающий), не создаёт
 * строку зеркала, которой нет (заводить запись о том, чего мы не измеряли, нельзя), и не решает
 * за владельца: запись в Лист1 по-прежнему требует `confirmed=true`, а agent-вызов — билета
 * токен-замка (`service_undo` внесён в REDZONE_LOCK).
 */

// Маркер машинного хвоста в поле args боевого журнала. Один хозяин формата на писателя и
// читателя (undoArgs_ / undoParse_ ниже) — разойтись им негде по построению.
var UNDO_TAG = '#ТО';

// Имена действий в журнале. НЕ содержат имён боевых операций намеренно: строка вытеснения —
// не аудит-след исправления, это РАЗНЫЕ записи, и читатель обязан их различать.
var UNDO_ACT_WRITE = 'ТО-регистр: вытеснение';
var UNDO_ACT_UNDO = 'ТО-регистр: отмена';

// Зеркало `String(p.args).slice(0, 500)` в logWrite_: человеческую часть режем ПОД машинный
// хвост, иначе длинное имя байка молча съело бы память об акте (приём «тело режется под штамп»).
var UNDO_ARGS_MAX = 500;

// Сколько последних строк журнала спрашиваем. Ёмкость журнала 3000 строк с ротацией; акт
// старше окна честно не находится (`act_not_found` + названное окно), а не «отменяется наугад».
var UNDO_SCAN_ROWS = 500;

// Колонка регистра → буква Лист1. ТОЛЬКО для человека в отчёте: решение о колонке принимает
// сам акт (поле `c` записи), второго словаря о том же смысле здесь не заводится.
var UNDO_COL_LETTER = { 9: 'I', 10: 'J', 11: 'K', 12: 'L' };


/**
 * Число из клетки регистра — ЗЕРКАЛО трёх строк, которыми его считают сами писатели
 * (`setFleetOil_`, `setFleetService_`): пусто → 0, не число → 0.
 * Равенство с писателями проверяется харнессом на живом коде, а не обещанием.
 */
function undoCellNum_(raw) {
  var v = (raw === '' || raw === null || raw === undefined) ? 0 : Number(raw);
  if (!isFinite(v)) v = 0;
  return v;
}

// Счётчик актов ВНУТРИ одного исполнения. Apps Script поднимает глобальные заново на каждый
// запрос, поэтому сам по себе он уникальности не даёт — он закрывает единственную дыру, которую
// не закрывает время: два акта в ОДНУ миллисекунду (запись двух видов ТО одним заходом).
var UNDO_SEQ = 0;

/**
 * Идентификатор акта: время + порядковый номер в исполнении + хвост uuid.
 * НЕ «первые N знаков uuid»: на источнике с постоянным префиксом такой ключ схлопнулся бы, а
 * ключ здесь решает, ЧТО именно отменяют, — столкновение отменило бы чужую запись.
 */
function undoActId_() {
  UNDO_SEQ += 1;
  var t = Number(new Date().getTime()).toString(36);
  var r = '';
  try {
    r = String(Utilities.getUuid()).replace(/[^0-9a-f]/gi, '').toLowerCase();
  } catch (e) {
    r = '';
  }
  return t + UNDO_SEQ.toString(36) + (r ? r.slice(-4) : 'zzzz');
}

/** Сырое значение клетки, годное к дословному возврату? Пусто, число и строка — да. */
function undoRawOk_(raw) {
  if (raw === '' || raw === null || raw === undefined) return true;
  var t = typeof raw;
  return t === 'number' || t === 'string';
}

/** Человеку — как показать сырое значение клетки («пусто» вместо пустой строки). */
function undoShow_(raw) {
  if (raw === '' || raw === null || raw === undefined) return 'пусто';
  return String(raw);
}

/**
 * ПИСАТЕЛЬ ФОРМАТА: человеческая часть + машинный хвост, и хвост НЕ РЕЖЕТСЯ никогда.
 */
function undoArgs_(human, rec) {
  var tail = UNDO_TAG + JSON.stringify(rec);
  var room = UNDO_ARGS_MAX - tail.length - 3;
  var head = String(human == null ? '' : human);
  if (room <= 0) return tail;                    // хвост дороже прозы
  if (head.length > room) head = head.slice(0, room);
  return head + ' · ' + tail;
}

/**
 * ЧИТАТЕЛЬ ФОРМАТА: запись акта из строки журнала либо null.
 * Мусор, обрезка, чужая строка → null (никогда не бросает: отмена не должна падать на прозе).
 */
function undoParse_(args) {
  var s = String(args == null ? '' : args);
  var i = s.lastIndexOf(UNDO_TAG);
  if (i < 0) return null;
  var o;
  try {
    o = JSON.parse(s.slice(i + UNDO_TAG.length));
  } catch (e) {
    return null;
  }
  if (!o || !o.a || !o.p || !o.c) return null;
  return o;
}


/**
 * ПАМЯТЬ О ВЫТЕСНЕНИИ — зовётся ПОСЛЕ каждой удавшейся и сверенной записи регистра.
 *
 * Best-effort НАМЕРЕННО: журнал не лёг → запись всё равно состоялась, но отменить её будет
 * НЕЧЕМ, и об этом говорится вслух (`act: null`, `act_logged: false`), а не молчится. Ронять
 * законную запись ТО из-за икоты журнала было бы хуже: она про мир, а память — про нас.
 * (У ветки исправления масла свой, FAIL-CLOSED аудит-след — он не тронут и живёт отдельно.)
 *
 * rec: { p:plate, b:bikeName, c:col, k:kind, o:oldNum, r:oldRaw, n:newNum, w:by }
 * → { act:String|null, logged:Bool }
 */
function undoRemember_(rec) {
  try {
    var id = undoActId_();
    var body = { a: id, p: String(rec.p), b: String(rec.b), c: Number(rec.c),
                 k: String(rec.k), o: Number(rec.o), n: Number(rec.n),
                 r: undoRawOk_(rec.r) ? (rec.r === null || rec.r === undefined ? '' : rec.r) : '',
                 w: String(rec.w || 'bot') };
    if (!undoRawOk_(rec.r)) body.x = 1;           // вернуть дословно нечем — отмена откажет
    var human = 'байк=' + rec.b + '; кол.' + (UNDO_COL_LETTER[rec.c] || rec.c) + ' ' +
                undoShow_(rec.r) + '→' + rec.n + '; вид=' + rec.k + '; кто=' + (rec.w || 'bot');
    var lg = logWrite_({ initiator: String(rec.w || 'bot'), act: UNDO_ACT_WRITE,
                         args: undoArgs_(human, body), result: 'ok',
                         critical: 'память о вытеснении регистра ТО' });
    if (!(lg && lg.ok)) return { act: null, logged: false };
    return { act: id, logged: true };
  } catch (e) {
    return { act: null, logged: false };
  }
}


/** Все записи актов ТО из хвоста журнала, НОВЕЙШИЕ ПЕРВЫМИ. */
function undoActs_() {
  var log = readWriteLog_({ limit: UNDO_SCAN_ROWS });
  var out = [];
  if (!log || !log.ok || !log.items) return out;
  for (var i = 0; i < log.items.length; i++) {          // readWriteLog_ отдаёт newest-first
    var act = String(log.items[i].action || '');
    if (act.indexOf('ТО-регистр') !== 0) continue;
    var rec = undoParse_(log.items[i].args);
    if (rec) out.push(rec);
  }
  return out;
}


/** Строка зеркала «обслуживание» по паре байк × вид. Бросает, если зеркало недоступно. */
function undoMirrorRead_(plate, kind) {
  var tab = getBotTab_(BOTDATA.TABS.SERVICE);
  var H = BOTDATA.SERVICE_HEADERS;
  var last = tab.getLastRow();
  if (last < 2) return { found: false };
  var data = tab.getRange(2, 1, last - 1, H.length).getValues();
  var iBike = H.indexOf('bike'), iType = H.indexOf('service_type'),
      iLast = H.indexOf('last_service_km');
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][iType] || '').trim() !== kind) continue;
    if (plateFromName_(String(data[i][iBike] || '')) !== plate) continue;
    return { found: true, row: i + 2, bike: String(data[i][iBike] || '').trim(),
             last: undoCellNum_(data[i][iLast]) };
  }
  return { found: false };
}


/** Компенсация клетки Лист1 «вернуть как было при входе» (направление ВВЕРХ). → Bool. */
function undoCompensateCell_(sheet, row, col, value) {
  try {
    sheet.getRange(row, col).setValue(value);
    var vr = verifyWrite_(sheet, row, col, 1, 1, [[value]]);
    return !!(vr && vr.ok);
  } catch (e) {
    return false;
  }
}

/** Компенсация зеркала «вернуть как было при входе». → Bool. */
function undoCompensateMirror_(bike, kind, value) {
  try {
    var r = serviceUpsert({ bike: bike, service_type: kind, last_service_km: value });
    return !!(r && r.ok);
  } catch (e) {
    return false;
  }
}


/**
 * ДВЕРЬ ОТМЕНЫ. body: { act:String, by:String, confirmed:Bool }.
 * Числа СНАРУЖИ не принимаются вовсе — любое переданное число игнорируется по устройству.
 * Возвращает ОБЪЕКТ (не ContentService).
 */
function serviceUndo_(body) {
  try {
    var p = body || {};
    var act = String(p.act == null ? '' : p.act).trim();
    var by = String(p.by == null ? '' : p.by).trim() || 'bot';
    if (!act) return { ok: false, error: 'need_act',
                       message: 'отмена идёт по ССЫЛКЕ НА АКТ; числа снаружи дверь не принимает' };
    if (p.confirmed !== true) {
      return { ok: false, error: 'not_confirmed',
               message: 'Возврат значения в Лист1 требует confirmed=true' };
    }

    // ── 1. ПАМЯТЬ: акт, названный ссылкой, обязан быть НАШИМ вытеснением ──────────────────
    var acts;
    try {
      acts = undoActs_();
    } catch (eLog) {
      return { ok: false, error: 'journal_unavailable', message: String(eLog) };
    }
    var ref = null;
    for (var i = 0; i < acts.length; i++) if (acts[i].a === act) { ref = acts[i]; break; }
    if (!ref) {
      return { ok: false, error: 'act_not_found', act: act, scanned: acts.length,
               window_rows: UNDO_SCAN_ROWS,
               message: 'такого вытеснения мост не помнит (просмотрено ' + acts.length +
                        ' актов в последних ' + UNDO_SCAN_ROWS + ' строках журнала) — ' +
                        'отменять нечего' };
    }
    if (ref.u) {
      return { ok: false, error: 'undo_of_undo', act: act, undo_of: ref.u,
               message: 'это сама отмена; отмены отмены не бывает' };
    }
    if (ref.x) {
      return { ok: false, error: 'raw_not_restorable', act: act,
               message: 'прежнее содержимое клетки дословно не восстановимо — закрой руками' };
    }

    // ── 2. ТОЛЬКО ПОСЛЕДНЯЯ по паре «байк × колонка» ─────────────────────────────────────
    // Окно просмотра тут не вредит по построению: всё, что НОВЕЕ найденного акта, лежит ближе
    // к хвосту журнала, то есть внутри того же окна. Пропустить «запись новее» нельзя.
    var newest = null;
    for (var j = 0; j < acts.length; j++) {
      if (acts[j].p === ref.p && Number(acts[j].c) === Number(ref.c)) { newest = acts[j]; break; }
    }
    if (newest && newest.a !== ref.a) {
      if (newest.u === ref.a) {
        return { ok: false, error: 'already_undone', act: act, undo_act: newest.a,
                 message: 'этот акт уже отменён' };
      }
      return { ok: false, error: 'not_last', act: act, newer_act: newest.a,
               message: 'по этому байку и колонке есть запись новее — отменяется только последняя' };
    }

    // ── 3. СЛИЧЕНИЕ: в клетке ДО СИХ ПОР ровно то, что записал акт ───────────────────────
    var sheet = SpreadsheetApp.openById(CONFIG.SHEETS.FLEET).getSheetByName('Лист1');
    if (!sheet) return { ok: false, error: 'write_failed', message: 'Лист1 не найден в "Байки"' };
    var lastRow = sheet.getLastRow();
    if (lastRow < 3) return { ok: false, error: 'not_found', number: ref.p };

    var col = Number(ref.c);
    var data = sheet.getRange(3, 1, lastRow - 2, col).getValues();
    var matches = [];
    for (var k = 0; k < data.length; k++) {
      var name = String(data[k][2] || '').trim();
      if (!name) continue;
      if (plateFromName_(name) === ref.p) matches.push({ sheetRow: k + 3, name: name,
                                                         raw: data[k][col - 1] });
    }
    if (matches.length === 0) return { ok: false, error: 'not_found', number: ref.p };
    if (matches.length > 1) {
      return { ok: false, error: 'ambiguous', number: ref.p,
               matches: matches.map(function (m) { return m.name; }) };
    }
    var hit = matches[0];
    var cur = undoCellNum_(hit.raw);
    var full_address = sheetFullAddr_(CONFIG.SHEETS.FLEET, 'Лист1',
                                      sheet.getRange(hit.sheetRow, col).getA1Notation());
    if (cur !== Number(ref.n)) {
      var back = (cur === Number(ref.o));
      return { ok: false, error: back ? 'cell_already_at_old' : 'cell_changed',
               act: act, expected: Number(ref.n), found: cur, restore_to: Number(ref.o),
               full_address: full_address, bike_name: hit.name,
               message: back
                 ? 'клетку уже вернули к прежнему значению — отменять нечего, зови владельца'
                 : 'клетку тронула чужая рука — возврат не делаю, зови владельца' };
    }

    var ledger = { accepted: 3, done: 0, missing: [] };

    // ── 4. ПЕРВАЯ БАЗА: Лист1 → прежнее СЫРОЕ значение (пустая клетка вернётся пустой) ────
    try {
      sheet.getRange(hit.sheetRow, col).setValue(ref.r);
    } catch (eW) {
      return { ok: false, error: 'write_failed', act: act, full_address: full_address,
               message: String(eW) };
    }
    var vr = verifyWrite_(sheet, hit.sheetRow, col, 1, 1, [[ref.r]]);
    if (!vr.ok) {
      return { ok: false, error: 'verify_failed', act: act, full_address: full_address,
               mismatches: vr.mismatches,
               message: 'перечитывание не подтвердило возврат — перечитай клетку, не повторяй вслепую' };
    }
    ledger.done += 1;

    // ── 5. ВТОРАЯ БАЗА: зеркало «обслуживание» → last_service_km = прежнее ───────────────
    // Строки зеркала может НЕ БЫТЬ вовсе (живьём 22.08: 3 строки на 38 байков) — это не отказ,
    // возвращать там нечего; создавать её ради отмены значило бы завести запись о том, чего мы
    // не измеряли. Отказ — только «не смогли» и «там чужое число».
    var mirror = { state: 'absent' };
    var mirrorTouched = false;
    var failed = null;
    try {
      var m = undoMirrorRead_(ref.p, ref.k);
      if (!m.found) {
        mirror = { state: 'absent' };
        ledger.missing.push('зеркало «обслуживание»: строки по виду «' + ref.k + '» нет — возвращать нечего');
      } else if (m.last === Number(ref.o)) {
        mirror = { state: 'already', row: m.row, last_service_km: m.last };
      } else if (m.last !== Number(ref.n)) {
        mirror = { state: 'changed', row: m.row, last_service_km: m.last };
        failed = { error: 'mirror_changed',
                   message: 'в зеркале «обслуживание» чужое число — возврат отменён целиком, зови владельца' };
      } else {
        var up = serviceUpsert({ bike: m.bike || ref.b, service_type: ref.k,
                                 last_service_km: Number(ref.o) });
        if (up && up.ok) {
          mirrorTouched = true;
          mirror = { state: 'restored', row: m.row, bike: m.bike,
                     from: m.last, to: Number(ref.o) };
        } else {
          mirror = { state: 'failed', row: m.row, detail: up };
          failed = { error: 'mirror_failed',
                     message: 'зеркало «обслуживание» не вернулось — возврат отменён целиком' };
        }
      }
    } catch (eM) {
      mirror = { state: 'unavailable', detail: String(eM) };
      failed = { error: 'mirror_unavailable',
                 message: 'зеркало «обслуживание» недоступно — возврат отменён целиком' };
    }

    if (failed) {
      // ОБЕ БАЗЫ ИЛИ НИ ОДНОЙ: первую возвращаем как было при входе. Направление ВВЕРХ —
      // сторож его не запрещал никогда, скруткой это быть не может по устройству.
      var comp = undoCompensateCell_(sheet, hit.sheetRow, col, Number(ref.n));
      return { ok: false, error: failed.error, act: act, bike_name: hit.name,
               row: hit.sheetRow, column: col, kind: ref.k,
               full_address: full_address, mirror: mirror,
               compensated: comp, ledger: { accepted: 3, done: 0, missing: [failed.message] },
               message: failed.message + '; Лист1 ' +
                        (comp ? 'возвращена в прежнее состояние (' + ref.n + ')'
                              : 'НЕ возвращена — в клетке ' + undoShow_(ref.r) + ', закрой руками') };
    }
    if (mirror.state === 'restored' || mirror.state === 'already') ledger.done += 1;

    // ── 6. СЛЕД РАСТЁТ: сама отмена ложится в журнал отдельным событием ─────────────────
    var undoId = undoActId_();
    var undoRec = { a: undoId, p: ref.p, b: ref.b, c: col, k: ref.k,
                    o: Number(ref.n), n: Number(ref.o), r: Number(ref.n),
                    w: by, u: ref.a };
    var humanU = 'ОТМЕНА акта ' + ref.a + '; байк=' + ref.b + '; кол.' +
                 (UNDO_COL_LETTER[col] || col) + ' ' + ref.n + '→' + undoShow_(ref.r) +
                 '; вид=' + ref.k + '; кто=' + by;
    var lgU = null;
    try {
      lgU = logWrite_({ initiator: by, act: UNDO_ACT_UNDO, args: undoArgs_(humanU, undoRec),
                        result: 'ok', critical: 'отмена записи регистра ТО' });
    } catch (eU) {
      lgU = null;
    }
    if (!(lgU && lgU.ok)) {
      // FAIL-CLOSED, как у аудит-следа исправления: отмена без следа в живой таблице
      // неотличима от порчи данных. Возвращаем обе базы в состояние «при входе».
      var compC = undoCompensateCell_(sheet, hit.sheetRow, col, Number(ref.n));
      var compM = mirrorTouched
        ? undoCompensateMirror_(mirror.bike || ref.b, ref.k, Number(ref.n))
        : true;
      return { ok: false, error: 'undo_audit_failed', act: act,
               full_address: full_address, mirror: mirror,
               compensated: !!compC, mirror_compensated: !!compM,
               ledger: { accepted: 3, done: 0, missing: ['след отмены не записался'] },
               message: 'след отмены не записался — возврат отменён целиком; Лист1 ' +
                        (compC ? 'вернулась' : 'НЕ вернулась, закрой руками') + ', зеркало ' +
                        (compM ? 'вернулось' : 'НЕ вернулось, закрой руками') };
    }
    ledger.done += 1;

    return { ok: true, act: act, undo_act: undoId, number: ref.p, bike_name: hit.name,
             row: hit.sheetRow, column: col, kind: ref.k,
             removed: Number(ref.n), restored: ref.r, restored_num: Number(ref.o),
             verified: true, full_address: full_address, mirror: mirror,
             ledger: ledger, by: by };
  } catch (err) {
    return { ok: false, error: 'undo_failed', message: String(err) };
  }
}
