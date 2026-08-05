"""КУРАТОР НЕ ВИДИТ ЗАКРЫТУЮ ЦЕЛЬ СОСЕДА — тождество ПО СОБЫТИЮ (05.08.2026).

Живой класс (cc_log 05.08 10:48): ТЗ владельца пришло дважды (цели 320 и 324 — дословно
один заголовок, 319 и 323 — тоже), и каждая цель родила СВОЮ журнальную проверку одного
события: задачи 330/336 и 327/334. Все четыре — холостые заходы «премиса не подтвердилась,
запись была с самого начала». Реестр фактов и дедуп окна их не ловят: ключ там — ТЕКСТ
задачи, а формулировки соседей разные.

Тождество считается ПО СОБЫТИЮ (вид факта × предмет-имя), НЕ по номеру цели и НЕ по
ОБЛАСТИ: две цели вправе править ОДИН файл РАЗНЫМИ правками — это разные события.

Секции:
(1) чистота модуля + событие не образуется (не проверка / нет вида / нет предмета)
(2) заголовок цели: директива режима пропускается, повтор ТЗ → один заголовок
(3) предмет: коммит-хеш да, дата нет, имя в «кавычках» да, ИМЯ ФАЙЛА — НЕТ (область)
(4) вид: журнал/прод/пуш; ГЕЙТ видом не является; разные виды на одном предмете ≠ событие
(5) ЖИВЫЕ ГОЛДЕНЫ на ДОСЛОВНЫХ текстах: 334↔327 и 336↔330 — одно событие;
    332↔327 (единственный ложный запрет реплея) — НЕ одно событие
(6) _curator_event_seen: сосед другой цели в окне; свой корень / failed / вне окна / нет снимка
(7) _curator_spawn: дословная 336 при живом соседе 330 → НЕ поставлена, причина названа;
    другое событие в том же файле → поставлена КАК ПРЕЖДЕ (не запрещаем лишнего)
(8) FAIL-SAFE: сбой сверки события → задача ставится как прежде
(9) ГРАНИЦЫ: CURATOR=0 → куратор не зовётся вовсе (регресс существующего поведения)
"""
import ast
import datetime
import os
import sys

# Путь берётся ОТ ФАЙЛА ТЕСТА, а не константой: тот же файл гоняется по дереву ДО правки
# (git worktree) — с хардкодом он импортировал бы новый код и «красный до» был бы ложью.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

try:
    import curator_event as CE
except Exception as e:                                   # noqa: BLE001
    CE = None
    print("  (модуля curator_event нет: %s)" % e)

import orchestrator_daemon as OD


# ── ДОСЛОВНЫЕ тексты живого корпуса (снимок очереди 05.08.2026) ──────────────
T327 = ("[куратор цели 319, шаг 1] Хвост задачи 319 (фикс «имя секрета в аргументе», "
        "pretool_guard.py, коммиты 05c110b и e6fb0b5). Проверь два факта: 1) "
        "venv/bin/python3 gate.py — зелёный; 2) в журнале cc_log (read_doc name=cc_log) "
        "есть строка DONE про этот фикс. Гейт красный — почини. Строки нет — допиши через "
        "venv/bin/python3 cclog.py \"итог\". Отчёт с блоком FACT: числа тестов гейта и "
        "наличие строки в журнале.")
T334 = ("[куратор цели 323, шаг 1] Проверь, есть ли в cc_log строка DONE о фиксе «имя "
        "секрета в аргументе» (коммит c8cec4f). Читай read_doc(name=cc_log). Если строки "
        "НЕТ — добавь ровно одну: venv/bin/python3 cclog.py \"фикс имя секрета в аргументе: "
        "блоков 30→24, регресс 57/57, гейт 171 зелёных, c8cec4f\". Если строка уже есть — "
        "не писать, дубль не создавать. Пульс обновить той же операцией (--pulse).")
T330 = ("[куратор цели 320, шаг 1] Зелёная диагностика, кода не править. Фикс «одна "
        "операция не спрашивается дважды» (repeat_ask + posttool_feed._remember_permission, "
        "коммит 9906598) требовал финалом строку в cc_log, а в отчёте она не названа. "
        "Проверь: read_doc(name=cc_log) — есть ли запись об этом фиксе; git log/status — "
        "коммит запушен, хуки на диске = запушенная версия. Строки нет → допиши через "
        "`venv/bin/python3 cclog.py \"<итог ")
T336 = ("[куратор цели 324, шаг 1] Проверь cc_log: read_doc(name=cc_log) — есть ли DONE о "
        "ревизии фикса 3 (коммит eb33187, память захода гарда: разъезд каталогов гард/лента "
        "+ подпись тела вместо текста команды)? Если записи нет — допиши: "
        "venv/bin/python3 cclog.py \"ревизия фикса 3: два дефекта закрыты, тест 48/52 -> "
        "52/52, гейт 171 зелёный, eb33187 в origin/main\" --pulse \"статус\". Только "
        "журнал: не деплоить, не рестартовать.")
T332 = ("[куратор цели 318, шаг 2][глубина 2] CLAUDE.md, секция фикса 40c8425 («КЛАСС "
        "БОЛЬШЕ НЕ ВСТАЁТ НА ЛИТЕРАЛ»): в ОСТАТКАХ строка «до рестарта демона живой процесс "
        "держит старый код» ложна — pretool_guard.py подключён хуком PreToolUse отдельным "
        "подпроцессом, демон его не импортирует. Проверь фактом (grep pretool_guard в "
        "orchestrator_daemon.py), поправь строку по образцу e6fb0b5, gate.py, коммит. "
        "Рестарт не делать.")

G319 = ("ultrathink\n\nГРАНИЦА ГЕЙТА, фикс 2 из 3: ИМЯ СЕКРЕТА В АРГУМЕНТЕ.\n"
        "Только этот фикс.\n")
G323 = ("ultrathink\n\nГРАНИЦА ГЕЙТА, фикс 2 из 3: ИМЯ СЕКРЕТА В АРГУМЕНТЕ.\n"
        "Только этот фикс, объём не расширять.\n")
G320 = ("ultrathink\n\nГРАНИЦА ГЕЙТА, фикс 3 из 3: ОДНА ОПЕРАЦИЯ СПРАШИВАЕТСЯ ДВАЖДЫ.\n"
        "Только этот фикс.\n")
G324 = ("ultrathink\n\nГРАНИЦА ГЕЙТА, фикс 3 из 3: ОДНА ОПЕРАЦИЯ СПРАШИВАЕТСЯ ДВАЖДЫ.\n"
        "Только этот фикс.\n")
G318 = ("ultrathink\n\nГРАНИЦА ГЕЙТА, фикс 1 из 3: КЛАСС ВСТАЁТ НА ЛИТЕРАЛ.\n"
        "Только этот фикс. Ничего сверх — прошлый заход умер от объёма.\n")


def ev(text, goal=""):
    return CE.event_of(text, goal) if CE else None


# ── (1) чистота модуля и «события нет» ───────────────────────────────────────
print("(1) чистота модуля + событие не образуется:")

if CE:
    src = open(os.path.join(REPO, "curator_event.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
    res.append(ok(imports == {"re"},
                  "(1) модуль чистый: единственный импорт — re (факт ast, не докстринг), а не %s"
                  % sorted(imports)))
    res.append(ok("def enqueue" not in src and "bc." not in src,
                  "(1) модуль ничего не ставит в очередь — только отвечает «одно ли событие»"))
else:
    res.append(ok(False, "(1) модуль чистый: единственный импорт — re"))
    res.append(ok(False, "(1) модуль ничего не ставит в очередь"))

res.append(ok(ev("") is None, "(1) пустой текст → события нет"))
res.append(ok(ev("Почини гард и запушь: pretool_guard.py, коммит abc1234") is None,
              "(1) задача-ДЕЙСТВИЕ без проверки → события нет (правило её не касается)"))
res.append(ok(ev("Проверь, что клиенту ответили вежливо") is None,
              "(1) проверка без вида факта → события нет"))
res.append(ok(ev("Проверь cc_log: есть ли записи вообще") is None,
              "(1) проверка без НАЗВАННОГО предмета → события нет (сравнить можно только названное)"))


# ── (2) заголовок цели ───────────────────────────────────────────────────────
print("(2) заголовок цели:")
if CE:
    h320, h324, h318 = CE.goal_head(G320), CE.goal_head(G324), CE.goal_head(G318)
    res.append(ok(h320 and "ultrathink" not in h320,
                  "(2) директива режима «ultrathink» заголовком не считается"))
    res.append(ok(h320 == h324 and h320 != "",
                  "(2) ТЗ владельца пришло дважды (320/324) → ОДИН заголовок"))
    res.append(ok(CE.goal_head(G319) == CE.goal_head(G323),
                  "(2) 319/323 — тот же заголовок (второй экземпляр того же ТЗ)"))
    res.append(ok(h318 != h320, "(2) другая работа (318 «класс встаёт на литерал») → другой заголовок"))
    res.append(ok(CE.goal_head("") == "" and CE.goal_head(None) == "",
                  "(2) пустая цель → заголовка нет"))
    res.append(ok(CE.goal_head("тз:\nкоротко\nПОЧИНИ ЛЕНТУ АДРЕСА 829") ==
                  CE.goal_head("ПОЧИНИ ЛЕНТУ АДРЕСА 829"),
                  "(2) служебные и слишком короткие строки пропускаются"))
else:
    for lbl in ("директива режима", "ТЗ дважды → один заголовок", "319/323 тот же заголовок",
                "другая работа → другой заголовок", "пустая цель", "короткие строки"):
        res.append(ok(False, "(2) " + lbl))


# ── (3) предмет: имена события, но НЕ область ────────────────────────────────
print("(3) предмет — имя события, область предметом не является:")
if CE:
    s = CE.subjects("Проверь, есть ли в cc_log строка о коммите 9906598")
    res.append(ok(any(x == "коммит:9906598" for x in s),
                  "(3) короткий хеш из одних цифр (9906598) — предмет"))
    s = CE.subjects("Проверь cc_log: строка о eb33187")
    res.append(ok(any(x == "коммит:eb33187" for x in s), "(3) хеш с буквами — предмет"))
    s = CE.subjects("Проверь журнал: снимок .bak-napos-20260805 на месте")
    res.append(ok(not any(x.startswith("коммит:") for x in s),
                  "(3) восьмизначная ДАТА (20260805) коммитом не считается"))
    s = CE.subjects("Проверь cc_log: есть ли строка о фиксе «имя секрета в аргументе»")
    res.append(ok(any(x == "имя:имя секрета в аргументе" for x in s),
                  "(3) имя в «кавычках» — предмет"))
    s = CE.subjects("Проверь, что pretool_guard.py и orchestrator_daemon.py в origin/main")
    res.append(ok(not s, "(3) ИМЯ ФАЙЛА предметом НЕ является — это область, а не событие"))
    a = ev("Проверь cc_log: строка о правке в pretool_guard.py есть?",
           "ФИКС ГАРДА: денежная ветвь\n")
    b = ev("Проверь cc_log: строка о правке в pretool_guard.py есть?",
           "ФИКС ГАРДА: удаление вне tmp\n")
    res.append(ok(not CE.same_event(a, b),
                  "(3) ДВЕ ЦЕЛИ, ОДИН ФАЙЛ, разные правки → РАЗНЫЕ события (лишнего не запрещаем)"))
else:
    for lbl in ("цифровой хеш", "хеш с буквами", "дата не хеш", "имя в кавычках",
                "файл не предмет", "один файл разные правки"):
        res.append(ok(False, "(3) " + lbl))


# ── (4) вид факта ────────────────────────────────────────────────────────────
print("(4) вид факта:")
if CE:
    res.append(ok("journal" in CE.kinds("read_doc(name=cc_log): есть ли строка"),
                  "(4) журнал — вид"))
    res.append(ok("prod" in CE.kinds("доехал ли коммит в живой демон, MainPID"),
                  "(4) прод (живой процесс) — вид"))
    res.append(ok("push" in CE.kinds("коммит в origin/main?"), "(4) выложен ли — вид"))
    res.append(ok(CE.kinds("venv/bin/python3 gate.py — гейт зелёный?") == frozenset(),
                  "(4) ГЕЙТ видом НЕ является: это состояние дерева на момент, а не факт о предмете"))
    a = ev("Проверь, доехал ли коммит 3a95df7 в живой демон (PID, старт)", "ВЫКАТКА ФИКСА\n")
    b = ev("Проверь cc_log: есть ли строка DONE о коммите 3a95df7", "ЖУРНАЛ ФИКСА\n")
    res.append(ok(a is not None and b is not None and not CE.same_event(a, b),
                  "(4) один предмет, РАЗНЫЕ виды («доехал в прод» vs «есть в журнале») → не одно событие"))
else:
    for lbl in ("журнал", "прод", "push", "гейт не вид", "разные виды"):
        res.append(ok(False, "(4) " + lbl))


# ── (5) ЖИВЫЕ ГОЛДЕНЫ ────────────────────────────────────────────────────────
print("(5) живые голдены (дословные тексты очереди):")
if CE:
    e327, e334 = ev(T327, G319), ev(T334, G323)
    e330, e336 = ev(T330, G320), ev(T336, G324)
    e332 = ev(T332, G318)
    res.append(ok(CE.same_event(e334, e327),
                  "(5) 334 (цель 323) и 327 (цель 319) — ОДНО событие (журнальная строка о том же фиксе)"))
    res.append(ok(CE.shared_subject(e334, e327) == "имя:имя секрета в аргументе",
                  "(5) общий предмет 334/327 назван: имя фикса"))
    res.append(ok(CE.same_event(e336, e330),
                  "(5) 336 (цель 324) и 330 (цель 320) — ОДНО событие (тот же заголовок ТЗ владельца)"))
    res.append(ok(CE.shared_subject(e336, e330).startswith("цель:"),
                  "(5) общий предмет 336/330 — заголовок повторённой цели"))
    res.append(ok(not CE.same_event(e332, e327),
                  "(5) 332 (правка CLAUDE.md) и 327 — РАЗНЫЕ события: ложный запрет не воскрешаем"))
    res.append(ok(not CE.same_event(e336, e327),
                  "(5) 336 и 327 — разные события (разные фиксы)"))
    res.append(ok(not CE.same_event(e334, e330),
                  "(5) 334 и 330 — разные события (разные фиксы)"))
else:
    for lbl in ("334/327 одно", "предмет 334/327", "336/330 одно", "предмет 336/330",
                "332/327 разные", "336/327 разные", "334/330 разные"):
        res.append(ok(False, "(5) " + lbl))


# ── Мост-фикстура ────────────────────────────────────────────────────────────
def iso(minutes_ago):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 900
        s.enq_calls = []

    def add(s, status, text, frm="Filipp-curator", created_min_ago=60, tid=None):
        s.nid = tid if tid is not None else s.nid + 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": "", "created": iso(created_min_ago),
                         "updated": iso(created_min_ago)}
        return s.nid

    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in s.rows.values() if r["status"] in sts]}

    def claim_task(s, tid, lane=None):
        return {"ok": True}

    def complete_task(s, tid, status, result=""):
        return {"ok": True}

    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text))
        return {"ok": True, "id": s.add("new", text, frm=frm, created_min_ago=0)}

    def set_needs_approval(s, tid, what):
        return {"ok": True}


def fresh_bridge():
    """Очередь-фикстура: цели 319/320/323/324 и живые кураторские соседи 327/330."""
    fb = FakeBridge()
    fb.add("done", G319, frm="Filipp-328-dev", created_min_ago=180, tid=319)
    fb.add("done", G320, frm="Filipp-328-dev", created_min_ago=170, tid=320)
    fb.add("done", G323, frm="Filipp-328-dev", created_min_ago=160, tid=323)
    fb.add("done", G324, frm="Filipp-328-dev", created_min_ago=150, tid=324)
    fb.add("in_progress", T327, created_min_ago=58, tid=327)
    fb.add("done", T330, created_min_ago=69, tid=330)
    fb.nid = 900
    return fb


# ── (6) _curator_event_seen ──────────────────────────────────────────────────
print("(6) _curator_event_seen: сосед по событию:")
seen_fn = getattr(OD, "_curator_event_seen", None)
if seen_fn and CE:
    fb = fresh_bridge()
    items = fb.get_pending("new,in_progress,done,failed,needs_approval,approved")["items"]

    body336 = CE.strip_marker(T336)
    r = seen_fn(324, body336, G324, items)
    res.append(ok(r is not None and r[0] == 330 and r[1] == 320,
                  "(6) 324 предлагает проверку 336 → найден сосед 330 (цель 320)"))
    res.append(ok(r is not None and str(r[2]) == "done",
                  "(6) статус соседа назван (done = событие уже закрыто)"))

    body334 = CE.strip_marker(T334)
    r2 = seen_fn(323, body334, G323, items)
    res.append(ok(r2 is not None and r2[0] == 327 and r2[1] == 319,
                  "(6) 323 предлагает проверку 334 → найден сосед 327 (цель 319), он ещё в работе"))

    res.append(ok(seen_fn(320, body336, G320, items) is None,
                  "(6) СВОЙ корень соседом не считается (шаги одной цели держат бюджеты)"))

    fb2 = fresh_bridge()
    fb2.rows[330]["status"] = "failed"
    items2 = fb2.get_pending("new,in_progress,done,failed,needs_approval,approved")["items"]
    res.append(ok(seen_fn(324, body336, G324, items2) is None,
                  "(6) сосед FAILED → факт не закрыт, проверка законна"))

    fb3 = fresh_bridge()
    fb3.rows[330]["created"] = iso(60 * 24 * 3)
    items3 = fb3.get_pending("new,in_progress,done,failed,needs_approval,approved")["items"]
    res.append(ok(seen_fn(324, body336, G324, items3) is None,
                  "(6) сосед старше окна EVENT_WINDOW → не сосед (факт мог протухнуть)"))

    res.append(ok(seen_fn(324, body336, G324, None) is None,
                  "(6) снимка очереди нет → None (fail-safe: ставим как прежде)"))
    res.append(ok(seen_fn(324, "почини ленту, ничего не проверяя", G324, items) is None,
                  "(6) предложение-ДЕЙСТВИЕ события не образует → соседа не ищем"))
else:
    for lbl in ("сосед найден", "статус соседа", "334 → 327", "свой корень", "failed сосед",
                "вне окна", "нет снимка", "действие не событие"):
        res.append(ok(False, "(6) " + lbl))


# ── (7) _curator_spawn: живой путь постановки ────────────────────────────────
print("(7) _curator_spawn — постановка:")
old_bc = OD.bc
fb = fresh_bridge()
OD.bc = fb
body336 = CE.strip_marker(T336) if CE else T336
sp = OD._curator_spawn("задача", 324, G324, [body336])
followup = [c for c in fb.enq_calls if "куратор цели" in c[1]]
res.append(ok(len(followup) == 0 and len(sp["placed"]) == 0,
              "(7) дословная 336 при живом соседе 330 → задача НЕ поставлена"))
why = sp["refused"][0][1] if sp["refused"] else ""
res.append(ok("событие" in why and "320" in why,
              "(7) причина названа владельцу: событие закрыто целью 320 — «%s»" % why[:80]))
res.append(ok("330" in why, "(7) причина называет задачу-соседа номером"))

fb = fresh_bridge()
OD.bc = fb
sp2 = OD._curator_spawn("задача", 323, G323, [CE.strip_marker(T334) if CE else T334])
res.append(ok(len(sp2["placed"]) == 0 and sp2["refused"],
              "(7) дословная 334 при живом соседе 327 → тоже не поставлена"))

fb = fresh_bridge()
OD.bc = fb
other = ("Проверь, доехал ли коммит 8698b45 в живой orchestrator-daemon: "
         "systemctl show -p ExecMainStartTimestamp против даты коммита.")
sp3 = OD._curator_spawn("задача", 338, "ДЫРА В FAIL-SAFE РАЗВОДА КУРАТОРСКОГО ПУНКТА.\n", [other])
res.append(ok(len(sp3["placed"]) == 1 and not sp3["refused"],
              "(7) ДРУГОЕ событие (прод, другой коммит, другая цель) → поставлена КАК ПРЕЖДЕ"))

fb = fresh_bridge()
OD.bc = fb
same_file = ("Проверь фактом, что в pretool_guard.py денежная ветвь судит вызов, "
             "и поправь строку; коммит.")
sp4 = OD._curator_spawn("задача", 400, "ДЕНЕЖНАЯ ВЕТВЬ ГАРДА: судим действие.\n", [same_file])
res.append(ok(len(sp4["placed"]) == 1,
              "(7) тот же ФАЙЛ, другое событие → поставлена (область запрета не даёт)"))


# ── (8) FAIL-SAFE ────────────────────────────────────────────────────────────
print("(8) fail-safe:")
if CE and seen_fn:
    _orig = CE.event_of

    def _boom(*a, **kw):
        raise RuntimeError("сверка события упала")

    CE.event_of = _boom
    fb = fresh_bridge()
    OD.bc = fb
    sp5 = OD._curator_spawn("задача", 324, G324, [body336])
    CE.event_of = _orig
    res.append(ok(len(sp5["placed"]) == 1,
                  "(8) сверка события упала → задача ставится КАК ПРЕЖДЕ (не хуже прежнего)"))
else:
    res.append(ok(False, "(8) сбой сверки → ставим как прежде"))

fb = fresh_bridge()
OD.bc = fb


def _no_queue():
    return None


_orig_qi = getattr(OD, "_queue_items", None)
if _orig_qi:
    OD._queue_items = _no_queue
    sp6 = OD._curator_spawn("задача", 324, G324, [body336])
    OD._queue_items = _orig_qi
    res.append(ok(len(sp6["placed"]) == 0 and "бюджет" in (sp6["refused"][0][1] if sp6["refused"] else ""),
                  "(8) очередь не опросить → прежний отказ про бюджет (поведение не изменилось)"))
else:
    res.append(ok(False, "(8) очередь не опросить → прежний отказ про бюджет"))


# ── (9) ГРАНИЦЫ: CURATOR=0 ───────────────────────────────────────────────────
print("(9) границы:")
calls = []
_orig_spawn = OD._curator_spawn


def _spy(*a, **kw):
    calls.append(a)
    return _orig_spawn(*a, **kw)


OD._curator_spawn = _spy
os.environ["CURATOR"] = "0"
OD._maybe_curator("задача", 1, "тз: проверь журнал", "готово")
res.append(ok(len(calls) == 0, "(9) CURATOR=0 → куратор не зовётся вовсе (регресс)"))
os.environ["CURATOR"] = "1"
OD._curator_spawn = _orig_spawn
OD.bc = old_bc

res.append(ok(getattr(OD, "EVENT_WINDOW", 0) >= 3600,
              "(9) окно соседства задаётся .env-ручкой EVENT_WINDOW (откат — сузить/обнулить)"))

# ОТКАТ ДОКАЗАН, А НЕ ОБЪЯВЛЕН: EVENT_WINDOW=0 → соседей нет вовсе, поведение прежнее.
_old_win = getattr(OD, "EVENT_WINDOW", None)
if _old_win is not None:
    fb = fresh_bridge()
    OD.bc = fb
    OD.EVENT_WINDOW = 0
    sp7 = OD._curator_spawn("задача", 324, G324, [body336])
    OD.EVENT_WINDOW = _old_win
    OD.bc = old_bc
    res.append(ok(len(sp7["placed"]) == 1 and not sp7["refused"],
                  "(9) EVENT_WINDOW=0 → правило инертно, дословная 336 ставится как до правки"))
else:
    res.append(ok(False, "(9) EVENT_WINDOW=0 → правило инертно"))


print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
