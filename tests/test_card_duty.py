"""ДЕЖУРНЫЙ ПО КАРТОЧКАМ, ФАЗА 1 (04.08.2026) — регресс на ЖИВОМ формате.

Что доказываем, по порядку важности:
  (0) ГЛАВНЫЙ ТЕСТ — карточка ВЫСШЕГО ВИДА не закрывается сама НИКОГДА. Гоняем ВЕСЬ словарь
      операций гарда (`pretool_guard._ACTIONS`, все до одной) с названной целью — каждая обязана
      дойти до владельца. Тест берёт словарь ИЗ ГАРДА, а не список из головы: появится новый
      красный класс — он попадёт под проверку сам, без правки этого файла.
  (1) четыре условия закрытия, каждое на факте;
  (2) РЕГРЕСС 25 карточек окна разведки 246 — сколько снял бы дежурный, сколько дошло бы;
  (3) откат: CARD_DUTY=0 → поведение БАЙТ-В-БАЙТ прежнее (ноль вызовов дежурного);
  (4) устройство границы: у дежурного нет пути к «одобрить» и нет рук (инвариант чистоты);
  (5) честный предел: подделанный признак пробы НЕ отнимает у владельца ни одной операции.

КАРТОЧКИ КОРПУСА СТРОЯТСЯ ЖИВЫМ КОДОМ, не рукописной строкой: тело даёт `pretool_guard._card`,
обёртку и штамп — `orchestrator_daemon._guard_what` / `_stamp_self_origin`. Идеализированный мок
здесь был бы хуже отсутствующего (правило 8 CLAUDE.md): формат карточки менялся трижды за неделю.

Сети/Telegram/claude/Bridge нет — всё мокнуто, владельцу не уходит ничего."""
import os, sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["PRETOOL_TEST_RUN"] = "1"
# КАНАЛ 2 ИЗОЛЯЦИИ ПРОБ (правило CLAUDE.md): каталог маркеров подставляем ВСЕГДА, даже если тест
# маркеров не пишет — иначе однажды напишет и попадёт в боевой /tmp/cc_guard_block.
os.environ["PRETOOL_BLOCK_DIR"] = "/tmp/cc_guard_block_test"
os.environ["MEM_MIN_MB"] = "0"

import card_duty as CD
import orchestrator_daemon as OD
import pretool_guard as PG

res = []


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    res.append(bool(c))
    return c


# ─────────────────────────── СТРОИТЕЛИ КАРТОЧЕК (живой код) ───────────────────────────
def guard_card(tid, hit, blob="", verified=True):
    """Карточка гарда ровно той формы, что уходит в очередь: тело `_card`, обёртка `_guard_what`."""
    return OD._guard_what(str(tid), {"hit": hit, "card": PG._card(hit, blob)}, verified=verified)


def self_card(text):
    """Заявка исполнителя: демон вычищает чужие штампы и клеит свой, последней строкой."""
    return OD._stamp_self_origin(text)


# ═════════════════ (0) ГЛАВНЫЙ ТЕСТ: ВЫСШИЙ ВИД НЕ ЗАКРЫВАЕТСЯ САМ ═════════════════
print("\n(0) ГЛАВНЫЙ ТЕСТ — карточка высшего вида не закрывается дежурным НИКОГДА")

# Цели, которые гард реально извлекает. ЖИВЫЕ имена полей моста, а не идеализированные.
LIVE_BLOBS = {
    "set_fleet_oil":     "bridge.set_fleet_oil(number='6789', oil_km=27000)",
    "set_fleet_service": "bridge.set_fleet_service(number='6789', kind='редуктор', km=27000)",
    "add_transaction":   "bridge.add_transaction(wallet='Наличка', amount=-500)",
    "void_last":         "bridge.void_last()",
    "create_booking":    "bridge.create_booking(bike='6789', name='Иван', date_start='10.07.2026')",
    "activate_booking":  "bridge.activate_booking(bike='6789', name='Иван')",
    "closing_upsert":    "bridge.closing_upsert(bike='6789', client='Иван', sum_total=5000)",
    "confirmed":         "bridge.set_fleet_oil(number='6789', oil_km=27000, confirmed=True)",
    "delete_event":      "bridge.delete_event(key='ev-42', bike='6789')",
    "edit_event":        "bridge.edit_event(key='ev-42', bike='6789', odo=36982)",
    "DOWRITE":           "DOWRITE=1\nbridge.write_doc(name='park_list', text='x')",
}
# КОМАНДНЫЕ классы: blob им собирает САМ гард (метки del_target=/proc_target= кладёт classify).
# Рукописной меткой их подменять нельзя — это ровно тот «мок ≠ живой формат», на котором
# 08.07 встал прод (класс маятника row705→1268). Берём blob из живого classify().
# ВАЖНО про выбор команд: `systemctl stop splinter` сюда НЕ годится — это ЖЁСТКИЙ блок
# (splinter в списке защищённых процессов), карточки с кнопкой у него нет вовсе, задача
# закрывается failed. Для класса proc_ctl берём НЕзащищённый процесс — иначе тест мерил бы
# другую ветку и молча ничего не проверял.
LIVE_CMDS = {
    "proc_ctl":    "systemctl stop nginx",
    "delete_file": "rm -f /root/turbobaby-manager-bot/bot.py",
    "sqlite":      "/root/turbobaby-manager-bot/venv/bin/python3 -c \""
                   "import sqlite3; sqlite3.connect('/root/other.db')"
                   ".execute('UPDATE rides SET x=1')\"",
}
for _hit, _cmd in LIVE_CMDS.items():
    _kind, _h, _blob = PG.classify(_cmd)
    if _h == _hit:
        LIVE_BLOBS[_hit] = _blob
        ok(True, f"живой blob для [{_hit}] собран самим гардом (classify → {_kind}/{_h})")
    else:
        # Честно: команда классифицировалась иначе — оставляем прежний blob и ГОВОРИМ об этом,
        # а не подменяем молча. Ложный PASS хуже отсутствующей проверки.
        ok(_hit in LIVE_BLOBS,
           f"[{_hit}] живой classify дал {_kind}/{_h or '—'} — blob оставлен ручной, объект ниже "
           f"проверяется всё равно")

# Жёсткий блок проверяем отдельно: у него карточки с кнопкой нет ВООБЩЕ (задача → failed),
# то есть до дежурного такая ветка не доходит по устройству.
_k, _h, _b = PG.classify("systemctl stop splinter")
ok(_k == "block" and _h == "proc_hard_block",
   "снос боевого процесса — ЖЁСТКИЙ блок (кнопки нет вовсе, до дежурного не доходит)")

held_all = True
for hit in sorted(PG._ACTIONS):
    blob = LIVE_BLOBS.get(hit, "")
    card = guard_card(900, hit, blob)
    obj = CD.facts(card, "guard")["obj"]
    if not obj:
        # Цель не извлеклась — карточка такой формы в бою НЕ рождается вовсе (marker_has_object
        # не отдаёт маркер демону). Значит и дежурному её не покажут; отмечаем и идём дальше.
        ok(True, f"[{hit}] цель не извлеклась → в бою карточка не рождается (маркер не пишется)")
        continue
    action, rule, proof = CD.decide(card, "guard")
    held = (action == CD.HOLD)
    held_all &= held
    ok(held, f"[{hit}] цель «{obj[:38]}» → карточка ДОХОДИТ до владельца ({proof[:44]})")

ok(held_all, "ВЕСЬ словарь красных операций гарда с названной целью — удержан, закрытых нет")

# Тот же словарь, но источник СЛАБЫЙ/чужой — цель названа, значит всё равно к владельцу.
for origin in ("guard_weak", "legacy", "self"):
    c = guard_card(901, "add_transaction", LIVE_BLOBS["add_transaction"])
    a, _r, _p = CD.decide(c, origin)
    ok(a == CD.HOLD, f"деньги с названной целью, источник={origin} → к владельцу (цель решает)")

# ═════════════════ (1) ЧЕТЫРЕ УСЛОВИЯ, КАЖДОЕ НА ФАКТЕ ═════════════════
print("\n(1) четыре условия закрытия")

# 1. объект пуст
c = guard_card(117, "add_transaction", "")
a, r, p = CD.decide(c, "guard")
ok(a == CD.CLOSE and r == CD.R_OBJECT, "1. объект пуст (денежная пустышка) → снята по «объект»")
ok("Объект: —" in c, "   … и это ДЕЙСТВИТЕЛЬНО пустая карточка живого формата")

# число пустое, но объект есть → НЕ закрываем (отмена проводки числа не несёт ПО ПРИРОДЕ)
c = guard_card(118, "void_last", LIVE_BLOBS["void_last"])
f = CD.facts(c, "guard")
a, r, p = CD.decide(c, "guard")
ok(f["obj"] and not f["num"], "   отмена проводки: цель есть, числа нет по природе")
ok(a == CD.HOLD, "   → пустое ЧИСЛО карточку НЕ закрывает (класс 29.07 не воскрешаем)")

# 2. источник — слова исполнителя
c = self_card("op=other | Реестр мозга — два ручных шага владельца. 1) Drive: перетащить доки…")
a, r, p = CD.decide(c, OD._card_origin(c))
ok(a == CD.CLOSE and r == CD.R_SOURCE, "2. заявка исполнителя (штамп 🗣) → снята по «источник»")
ok(OD._card_origin(c) == "self", "   штамп источника читается демоном как self")

# guard_weak и legacy НЕ закрываем (fail-closed сужение)
for origin in ("guard_weak", "legacy"):
    c2 = guard_card(119, "add_transaction", "")
    # у безобъектной карточки первым сработает условие 1 — проверяем условие 2 отдельно, на
    # тексте БЕЗ формы карточки (свободный текст, как у заявки, но с чужим штампом)
    a2, r2, _p2 = CD.decide("op=other | какой-то текст без формы карточки", origin)
    ok(a2 == CD.HOLD, f"   источник={origin} → НЕ закрываем (реальный блок терять нельзя)")

# 3. операция уже сделана (владелец уже сказал «да» на тот же вопрос)
a, r, p = CD.decide("op=other | свободный текст", "self", answered_id="")
ok(a == CD.CLOSE and r == CD.R_SOURCE, "3. без answered_id решает более раннее условие")
a, r, p = CD.decide("op=other | свободный текст", "legacy", answered_id="77")
ok(a == CD.CLOSE and r == CD.R_DONE and "77" in p,
   "3. владелец уже ответил «да» на тот же отпечаток → снята по «сделано»")

# 4. проба или дубль
a, r, p = CD.decide("op=other | свободный текст", "legacy", dup_id="55")
ok(a == CD.CLOSE and r == CD.R_PROBE and "55" in p, "4. дубль открытой карточки → снята по «проба-дубль»")
probe_card = PG._card("add_transaction", "", test=True)
a, r, p = CD.decide("op=other | [add_transaction] " + probe_card, "legacy")
ok(a == CD.CLOSE, "4. пометка пробы, поставленная ГАРДОМ → снята")

# fail-closed
for bad, label in ((None, "None"), ("", "пустой текст"), (123, "не строка")):
    a, _r, _p = CD.decide(bad, "guard")
    ok(a == CD.HOLD, f"fail-closed: {label} → к владельцу")
a, _r, _p = CD.verdict("не словарь"), None, None
ok(a[0] == CD.HOLD, "fail-closed: факты не собраны → к владельцу")

# ═════════════════ (2) РЕГРЕСС: 25 КАРТОЧЕК ОКНА РАЗВЕДКИ 246 ═════════════════
print("\n(2) РЕГРЕСС на окне 28.07–04.08 (разведка 246): 25 карточек владельцу")

# ПОТОК ГАРД→ДЕМОН — 13 карточек, ровно те, что дежурный вообще видит. Источник фактов:
# orchestrator_daemon.log (строки рождения) + снимок очереди + артефакты 29.07 и 02.08.
FLOW = [
    # (id, вид, hit, blob, ожидаемое действие, ожидаемое условие, чем обоснован объект)
    ("12",  "guard", "set_fleet_oil",   "", CD.CLOSE, CD.R_OBJECT,
     "ТЗ задачи 27 дословно: «не назвала ни байк, ни пробег»"),
    ("27",  "guard", "set_fleet_oil",   "", CD.CLOSE, CD.R_OBJECT,
     "форма команды — голый токен в однострочнике; живой прогон 04.08 дал «объект=—, число=—»"),
    ("29",  "self",  None,              None, CD.CLOSE, CD.R_SOURCE,
     "журнал: модель процитировала маркер в отчёте о форматах карточек"),
    ("56",  "self",  None,              None, CD.CLOSE, CD.R_SOURCE,
     "журнал: «Реестр мозга — два ручных шага владельца»"),
    ("58",  "self",  None,              None, CD.CLOSE, CD.R_SOURCE,
     "журнал: тот же реестр; «да» владельца дало «headless доказанно не может»"),
    ("117", "guard", "add_transaction", "", CD.CLOSE, CD.R_OBJECT,
     "артефакт 02.08 §1: «проводка ДЕНЕГ в кассу · Объект: — · Число: —»"),
    ("130", "self",  None,              None, CD.CLOSE, CD.R_SOURCE,
     "журнал: модель процитировала маркер в отчёте о замке происхождения"),
    ("135", "guard", "add_transaction", "", CD.CLOSE, CD.R_OBJECT, "артефакт 02.08 §1"),
    ("140", "guard", "add_transaction", "", CD.CLOSE, CD.R_OBJECT, "артефакт 02.08 §1"),
    ("142", "guard", "set_fleet_oil",   LIVE_BLOBS["set_fleet_oil"], CD.HOLD, "",
     "ТЗ задачи 143 дословно: «по байку 6789 с пробегом 27000»"),
    ("143", "guard", "set_fleet_oil",   LIVE_BLOBS["set_fleet_oil"], CD.HOLD, "",
     "тот же вызов пробы, что у 142"),
    ("181", "guard", "add_transaction", "", CD.CLOSE, CD.R_OBJECT, "артефакт 02.08 §1"),
    ("208", "guard", "add_transaction", "", CD.CLOSE, CD.R_OBJECT, "артефакт 02.08 §1"),
]
SELF_TEXTS = {
    "29":  "op=other | (claude не уточнил красное действие — см. вывод задачи)",
    "56":  "op=other | Реестр мозга — два ручных шага владельца. 1) Drive: перетащить доки "
           "KB_booking_flow и KB_collect_booking_spec в папку «TurboBaby Brain».",
    "58":  "op=other | Реестр мозга: обе правки требуют руки владельца · ЧТО: (1) в Drive "
           "перетащить KB_booking_flow и KB_collect_booking_spec в папку «TurboBaby Brain».",
    "130": "op=other | (claude не уточнил красное действие — см. вывод задачи)",
}

closed = held = 0
by_rule = {}
for tid, kind, hit, blob, want_a, want_r, why in FLOW:
    card = self_card(SELF_TEXTS[tid]) if kind == "self" else guard_card(tid, hit, blob)
    origin = OD._card_origin(card)
    a, r, p = CD.decide(card, origin)
    good = (a == want_a) and (not want_r or r == want_r)
    ok(good, f"карточка {tid} [{kind}] → {a}{('/' + r) if r else ''} (ждали "
             f"{want_a}{('/' + want_r) if want_r else ''}) · основание: {why[:52]}")
    if a == CD.CLOSE:
        closed += 1
        by_rule[r] = by_rule.get(r, 0) + 1
    else:
        held += 1

ok(closed == 11 and held == 2,
   f"поток гард→демон: снято {closed}, дошло бы {held} (ждали 11 и 2)")
print("      по условиям: " + ", ".join(f"{k}={v}" for k, v in sorted(by_rule.items())))

# СВОДНЫЕ КАРТОЧКИ КУРАТОРА — 12 штук, ВНЕ области дежурного (другой путь рождения).
# Здесь доказываем главное: даже если такой текст к дежурному попадёт, он его не снимет.
CURATOR_CARDS = [
    "🧑 СВОДНАЯ КАРТОЧКА ВЛАДЕЛЬЦУ (цель 30)\n• Реши, чья реализация минимума красной карточки "
    "живёт: ПК-коммит 17221f2 или непушнутый e4e6e2b\n✅ — ПОСТАВЛЮ ЗАДАЧУ на исполнение пунктов",
    "🧑 СВОДНАЯ КАРТОЧКА ВЛАДЕЛЬЦУ (цель 93)\n• Разреши перезапуск бота-супервайзера, чтобы "
    "фикс метки доехал в прод\n✅ — ПОСТАВЛЮ ЗАДАЧУ на исполнение пунктов",
] * 6
cur_held = 0
for i, txt in enumerate(CURATOR_CARDS):
    a, _r, _p = CD.decide(txt, "legacy")
    if a == CD.HOLD:
        cur_held += 1
ok(cur_held == 12, f"сводные карточки куратора: удержаны {cur_held} из 12 (воля владельца по существу)")

TOTAL_BEFORE = 25
total_after = held + cur_held
ok(total_after == 14, f"ЗАМЕР: было {TOTAL_BEFORE} карточек владельцу → станет {total_after}")

# ═════════════════ (3) ОТКАТ: CARD_DUTY=0 → БАЙТ-В-БАЙТ ПРЕЖНЕЕ ═════════════════
print("\n(3) откат флагом: CARD_DUTY=0 → дежурного нет вовсе")

_calls = {"decide": 0}
_real_decide = CD.decide


def _counting_decide(*a, **kw):
    _calls["decide"] += 1
    return _real_decide(*a, **kw)


CD.decide = _counting_decide
try:
    for val, expect_calls, label in (("0", 0, "CARD_DUTY=0"), ("", 0, "флага нет"),
                                     ("мусор", 0, "мусор в флаге"), ("1", 1, "CARD_DUTY=1")):
        os.environ["CARD_DUTY"] = val
        _calls["decide"] = 0
        card = self_card("op=other | заявка")
        OD.bc = type("B", (), {"get_pending": lambda s, st: {"ok": False},
                               "complete_task": lambda s, *a, **k: {"ok": True}})()
        OD._maybe_card_duty("777", card)
        ok(_calls["decide"] == expect_calls,
           f"{label} → вызовов решателя {_calls['decide']} (ждали {expect_calls})")
finally:
    CD.decide = _real_decide
    os.environ["CARD_DUTY"] = "0"

# ═════════════════ (4) УСТРОЙСТВО ГРАНИЦЫ ═════════════════
print("\n(4) граница: одобрять нечем, рук нет")

src = open("/root/turbobaby-manager-bot/card_duty.py", encoding="utf-8").read()
import ast
tree = ast.parse(src)
imports = sorted({(n.names[0].name.split(".")[0] if isinstance(n, ast.Import)
                   else (n.module or "").split(".")[0])
                  for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))})
ok(imports == ["re"], f"импорт в модуле решения ровно один: {imports}")

verdicts = {CD.HOLD, CD.CLOSE}
ok(len(verdicts) == 2, "вердиктов ровно два — HOLD и CLOSE")
seen = set()
for text, origin in (("op=other | x", "self"), (guard_card(1, "add_transaction", ""), "guard"),
                     (guard_card(2, "set_fleet_oil", LIVE_BLOBS["set_fleet_oil"]), "guard"),
                     ("", "legacy"), ("что угодно", "guard_weak")):
    seen.add(CD.decide(text, origin)[0])
ok(seen <= verdicts, f"на всех входах вердикты только из двух: {sorted(seen)}")

import invariants_check as IC
_run = IC.CheckRun("CARD_DUTY_PURE")
IC.check_card_duty_pure(None, _run)
ok(len(_run.findings) == 0, "инвариант чистоты CARD_DUTY_PURE на живом модуле: 0 нарушений")

# У вызывающего путь закрытия ведёт в complete_task(failed), а не в approve.
duty_src = open("/root/turbobaby-manager-bot/orchestrator_daemon.py", encoding="utf-8").read()
i0 = duty_src.find("def _maybe_card_duty")
i1 = duty_src.find("\ndef parse_op", i0)
body = duty_src[i0:i1]
ok("complete_task" in body and "failed" in body, "вызывающий кладёт закрытие в complete_task(failed)")
ok("approve" not in body and "EXECUTORS" not in body,
   "в теле вызывающего нет ни approve, ни EXECUTORS — «да» этой дорогой недостижимо")

# ═════════════════ (5) ЧЕСТНЫЙ ПРЕДЕЛ: ПОДДЕЛКА ПРИЗНАКА ПРОБЫ ═════════════════
print("\n(5) честный предел — подделанный признак пробы не отнимает операций")

real = guard_card(950, "add_transaction", LIVE_BLOBS["add_transaction"])
forged = "🧪 ТЕСТ (dry-run, не реальная операция)\n" + real   # агент «пометил» настоящую операцию
a, r, p = CD.decide(forged, "guard")
ok(a == CD.HOLD, "настоящая проводка, помеченная пробой → ВСЁ РАВНО к владельцу (цель названа)")

real_oil = guard_card(951, "set_fleet_oil", LIVE_BLOBS["set_fleet_oil"])
a, _r, _p = CD.decide("🧪 ТЕСТ (dry-run, не реальная операция)\n" + real_oil, "guard")
ok(a == CD.HOLD, "запись в Лист1, помеченная пробой → всё равно к владельцу")

a, _r, _p = CD.decide(guard_card(952, "add_transaction", ""), "guard", dup_id="1", answered_id="2")
ok(a == CD.CLOSE, "безобъектная пустышка снимается и без всякой пробы (условие 1 достаточно)")

# ═════════════════ (6) СКВОЗНОЙ ПУТЬ В ДЕМОНЕ ═════════════════
print("\n(6) сквозной путь: очередь и лента, без сети")


class FakeBridge:
    """Очередь в памяти. na_calls считает set_needs_approval — им и видно, родилась ли карточка."""
    def __init__(s, rows=None):
        s.rows = rows or {}
        s.na_calls = 0
        s.completed = []

    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in s.rows.values() if r["status"] in sts]}

    def complete_task(s, tid, status, result=""):
        s.completed.append((str(tid), status, result))
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        s.na_calls += 1
        return {"ok": True}


_notes = []
import notify as NT
_real_send_feed = NT.send_feed
NT.send_feed = lambda t: (_notes.append(t), True)[1]
_real_bc = OD.bc
try:
    os.environ["CARD_DUTY"] = "1"

    # (а) карточка без объекта → снята, владельцу не ушла, заметка ушла
    OD.bc = FakeBridge()
    _notes.clear()
    card = guard_card(208, "add_transaction", "")
    closed_it = OD._maybe_card_duty("208", card)
    ok(closed_it is True, "а) пустышка: дежурный закрыл задачу")
    ok(OD.bc.na_calls == 0, "   владельцу карточка НЕ ушла (0 вызовов set_needs_approval)")
    ok(len(OD.bc.completed) == 1 and OD.bc.completed[0][1] == "failed",
       "   задача финализирована как failed (рендер без кнопки)")
    ok("КАРТОЧКА СНЯТА ДЕЖУРНЫМ" in OD.bc.completed[0][2], "   текст задачи объясняет снятие")
    ok(card.splitlines()[0] in OD.bc.completed[0][2],
       "   исходная карточка сохранена ДОСЛОВНО (молча ничего не исчезает)")
    ok(len(_notes) == 1 and _notes[0].startswith("🧹"), f"   в ленту ушла ровно одна заметка")
    ok("условие: объект" in _notes[0] and "задача 208" in _notes[0],
       "   заметка называет задачу и условие")
    ok("да" not in _notes[0].split("·")[0], "   в заметке нет приглашения отвечать")

    # (б) карточка высшего вида → дежурный НЕ трогает, идёт прежним путём
    OD.bc = FakeBridge()
    _notes.clear()
    card = guard_card(142, "set_fleet_oil", LIVE_BLOBS["set_fleet_oil"])
    ok(OD._maybe_card_duty("142", card) is False, "б) запись в Лист1 с байком: дежурный не берётся")
    ok(len(OD.bc.completed) == 0 and len(_notes) == 0, "   ничего не закрыто и не отправлено")

    # (в) дубль: та же карточка уже открыта у владельца → вторая снимается
    twin = guard_card(300, "add_transaction", LIVE_BLOBS["add_transaction"])
    OD.bc = FakeBridge({300: {"id": 300, "status": "needs_approval", "result": twin}})
    _notes.clear()
    same = guard_card(301, "add_transaction", LIVE_BLOBS["add_transaction"])
    # у обеих есть объект → высший вид → дежурный НЕ снимает даже дубль (fail-closed)
    ok(OD._maybe_card_duty("301", same) is False,
       "в) дубль карточки С ОБЪЕКТОМ не снимается — высший вид сильнее дедупа")

    # (г) мост недоступен на сборе фактов → дежурный строже, а не мягче
    class DeadBridge(FakeBridge):
        def get_pending(s, status="new", lane=None):
            raise RuntimeError("мост лёг")

    OD.bc = DeadBridge()
    _notes.clear()
    ok(OD._maybe_card_duty("208", guard_card(208, "add_transaction", "")) is True,
       "г) мост лёг на сборе близнецов → условие 1 всё равно решает по самой карточке")
    OD.bc = FakeBridge()
    ok(OD._maybe_card_duty("500", self_card("op=other | заявка исполнителя")) is True,
       "   заявка исполнителя снимается и без очереди (факт в самой карточке)")
finally:
    NT.send_feed = _real_send_feed
    OD.bc = _real_bc
    os.environ["CARD_DUTY"] = "0"

print("\n" + "=" * 64)
print(f"ИТОГ: {sum(res)}/{len(res)} PASS")
if not all(res):
    sys.exit(1)
