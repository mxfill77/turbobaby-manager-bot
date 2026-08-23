"""ДОЛГ ПРИНЯТОЙ РАБОТЫ: строка заводится ДО показа кнопки и гаснет только доказанным (23.08.2026).

ЖИВОЙ СЛУЧАЙ, ради которого писано (`docs/artifacts/2026-08-22-service-5960-fate.md`, `tok=18`):
    01.08  08:06:40  NMAX 155 GREY 5960 — карточка подтверждения ушла в тему;
                     кнопку НЕ НАЖАЛИ; принято 2 позиции, записано 0;
    22.08            самой заявки уже не существует — «не только не была записана, она и не
                     докричалась».
Носителей у принятой работы было два, и оба нестойкие: токен в памяти процесса (`_SVC_TOKENS`,
рестарт стирает) и текст сообщения с кнопкой (его удаляет `_clear_cycle_msgs`). Строки в листе
«то_заявки» не заводилось ВООБЩЕ: `_ask_service_col` и `_ask_oil_or_km` не звали
`service_pending_upsert` ни разу.

ЗАМЕР, решивший ГРАНИЦУ (splinter.log, 01.06→23.08, 83 суток): прогонов ТО-трекера 129, из них
`due/overdue` 55, записей масла 8, записей столбца 1. Заводить долг на КАЖДОМ показе кнопки масла
= до 55 строк, из которых ≥47 висели бы по работе, которую НИКТО не заявлял (байку пришёл срок,
человек прислал фото приборки). Поэтому у двери масла долг требует `oil_hint`
(`_is_oil_done_marker` — человек СКАЗАЛ, что замена сделана), а у двери столбца работа названа
самим вызовом (`works`).

Что доказывается:
    (1) УСТРОЙСТВО   у `verdict()` параметра возраста НЕТ ВОВСЕ, а `voice()` не умеет вернуть ни
                     один из `CLOSERS` — «по таймеру не гаснет» держится кодом, а не докстрингом;
                     импортов у решения ноль (ast);
    (2) ПРИЁМ        что считается принятой работой (замер выше), и что НЕ считается;
    (3) ТРИ ПРИЗНАКА закрытия и РОВНО они; дырка в фактах closed НЕ даёт;
    (4) ТРИ ИСХОДА   висит · закрыт · неизвестно — и «неизвестно» ≠ «записано»;
    (5) СТОРОЖ       статус `ждёт_подтверждения` ПРОХОДИТ проверку возраста (до 23.08 стоял
                     голый `continue` ВЫШЕ неё → ни напоминаний, ни эскалации);
    (6) ОТРИЦАТЕЛЬНЫЙ ТЕСТ: кнопку не нажали → долг ОСТАЛСЯ и СОСТАРИЛСЯ;
    (7) БЛИЗНЕЦ:     кнопку нажали, запись доказана → долг ЗАКРЫЛСЯ. Сторож, который держит
                     всегда, не лучше того, который не держит никогда;
    (8) ДВЕРИ        строка заводится ДО показа кнопки на ОБЕИХ (порядок вызовов, не обещание);
    (9) ОТКАТ        `SERVICE_DEBT=0` → путь байт-в-байт прежний, мосту ни одного обращения;
   (10) ЖИВОЙ ADV 350 372 — завёлся бы долг новой логикой или нет (пункт 5 задания).

БАЙКИ ВЫДУМАННЫЕ (`TESTBIKE FAKE …` — таких в парке нет), в рабочие таблицы и в зеркало не
пишется ничего. Стенд моста НЕ ОБЪЯВЛЯЕТ НИ ОДНОГО МЕТОДА: имена ловит `__getattr__`, поэтому
имён боевых операций в теле файла нет вовсе.
"""
import ast
import asyncio
import inspect
import os
import sys
import unittest

# Корень — ОТ ФАЙЛА (ловушка метода 07.08: чужой боевой корень в sys.path зеленит прогон «до»).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT != "/root/turbobaby-manager-bot":
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"]
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NOTIFY_COUNT_FILE"] = "/tmp/tb_debt_notify_count.txt"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.pop("SERVICE_DEBT", None)          # дефолт ветки — жива

import service_debt                                                        # noqa: E402

FAKE_BIKE = "TESTBIKE FAKE 0001"     # в парке такого нет и быть не может
FAKE_CHAT = -100777000111
FAKE_TOPIC = 90901


# ============================== СТЕНД (харнесс живёт В КАТАЛОГЕ ТЕСТОВ) =======================
class _Clip:
    """Клетка регистра в контракте `fleet_cell`: разобрана/нет + величина."""

    def __init__(self, ok, payload=None, note="клетка стенда"):
        self.ok = ok
        self.payload = payload
        self.outcome = "value" if ok else "empty"
        self._note = note

    def say(self):
        return self._note


class _Bus:
    """Стенд моста БЕЗ ИМЁН БОЕВЫХ ОПЕРАЦИЙ.

    Ни одного метода не объявлено: обращение любым именем ловит `__getattr__`, поэтому в теле
    файла нет ни имени операции живой таблицы, ни его написания. Заодно это делает счётчик
    обращений полным — мимо него у стенда пройти нечем."""

    def __init__(self, replies=None):
        self.seen = []                 # [(имя, kwargs)] — ВСЕ обращения, по порядку
        self.replies = replies or {}

    def __getattr__(self, name):
        def _call(*a, **kw):
            self.seen.append((name, kw))
            r = self.replies.get(name)
            if callable(r):
                return r(*a, **kw)
            return {"ok": True} if r is None else r
        return _call

    def names(self):
        return [n for n, _ in self.seen]

    def count(self, name):
        return self.names().count(name)


def _run(coro):
    return asyncio.run(coro)


# ============================== (1) ГРАНИЦЫ УСТРОЙСТВОМ ======================================
class T1Structure(unittest.TestCase):
    """«По таймеру долг не гаснет» — свойство кода, а не обещание докстринга."""

    def test_verdict_has_no_age_parameter_at_all(self):
        params = set(inspect.signature(service_debt.verdict).parameters)
        for bad in ("age", "age_h", "now", "ts", "created_at", "older_than", "ttl", "timeout"):
            self.assertNotIn(bad, params,
                             f"у verdict() появился параметр «{bad}» — таймер снова может закрыть долг")
        self.assertEqual(params, {"write", "cell", "human", "odometer"})

    def test_verdict_source_does_not_mention_time(self):
        src = inspect.getsource(service_debt.verdict)
        for bad in ("time.", "datetime", "age_h", "now()"):
            self.assertNotIn(bad, src, f"в verdict() пролезло время ({bad})")

    def test_voice_cannot_close_anything(self):
        """voice() знает возраст — и именно поэтому не вправе вернуть признак закрытия."""
        src = inspect.getsource(service_debt.voice)
        for closer in service_debt.CLOSERS:
            self.assertNotIn(f'"{closer}"', src)
        seen = set()
        for st in (service_debt.STATUS, "ждёт_факт", "заявлено", "", None):
            for age in (None, 0, 1, 5.9, 6, 47.9, 48, 1000, 10 ** 9, -5, "мусор"):
                for esc in (True, False):
                    v = service_debt.voice(st, age, escalated=esc)
                    self.assertIn(v["speak"], service_debt.VOICES)
                    self.assertNotIn(v["speak"], service_debt.CLOSERS)
                    seen.add(v["speak"])
        self.assertEqual(seen, set(service_debt.VOICES), "не все исходы громкости достижимы")

    def test_zero_imports(self):
        with open(os.path.join(ROOT, "service_debt.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [], "у решения долга появился импорт — чистота потеряна")

    def test_no_io_calls(self):
        with open(os.path.join(ROOT, "service_debt.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        banned = {"open", "exec", "eval", "compile", "__import__", "input"}
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                self.assertNotIn(n.func.id, banned, f"решение долга зовёт {n.func.id}()")

    def test_exactly_three_closers(self):
        self.assertEqual(len(service_debt.CLOSERS), 3)
        self.assertEqual(set(service_debt.CLOSERS),
                         {service_debt.BY_WRITE, service_debt.BY_CELL, service_debt.BY_HUMAN})


# ============================== (2) ЧТО СЧИТАЕТСЯ ПРИНЯТОЙ РАБОТОЙ ===========================
class T2Accepted(unittest.TestCase):

    def test_col_door_named_work_with_number_is_a_debt(self):
        ok, why = service_debt.accepted(service_debt.DOOR_COL, ["gear"], "12212")
        self.assertTrue(ok, why)

    def test_oil_door_needs_the_claim_not_just_the_due_date(self):
        """ЗАМЕР: 55 due/overdue против 8 записей — безусловный долг дал бы ≥47 фантомов."""
        ok, why = service_debt.accepted(service_debt.DOOR_OIL, ["oil"], "12212", oil_hint=False)
        self.assertFalse(ok)
        self.assertIn("вопрос", why)
        ok2, _ = service_debt.accepted(service_debt.DOOR_OIL, ["oil"], "12212", oil_hint=True)
        self.assertTrue(ok2, "человек СКАЗАЛ, что замена сделана — это принятая работа")

    def test_no_number_is_not_yet_a_debt(self):
        for km in ("", None, "  ", "не число"):
            ok, why = service_debt.accepted(service_debt.DOOR_COL, ["gear"], km)
            self.assertFalse(ok)
            self.assertIn("числ", why)

    def test_no_work_named_is_not_a_debt(self):
        ok, _ = service_debt.accepted(service_debt.DOOR_COL, [], "12212")
        self.assertFalse(ok)

    def test_unknown_door_never_makes_a_debt(self):
        ok, _ = service_debt.accepted("сообщение в теме", ["gear"], "12212")
        self.assertFalse(ok)

    def test_open_fields_merge_and_do_not_clobber(self):
        """Место исчезновения №5: второй вид партии затирал первый."""
        f = service_debt.open_fields(service_debt.DOOR_COL, ["abs"], "41641",
                                     prev_declared=["gear"], prev_done=["gear"])
        self.assertEqual(f["declared"], ["gear", "abs"])
        self.assertEqual(f["done"], ["gear", "abs"])
        self.assertEqual(f["odometer"], "41641")
        self.assertEqual(f["status"], service_debt.STATUS)

    def test_open_fields_none_when_not_accepted(self):
        self.assertIsNone(service_debt.open_fields(service_debt.DOOR_OIL, ["oil"], "1", False))

    def test_live_number_formats(self):
        f = service_debt.open_fields(service_debt.DOOR_COL, ["gear"], "12 212")
        self.assertEqual(f["odometer"], "12212")


# ============================== (3)(4) ТРИ ПРИЗНАКА, ТРИ ИСХОДА ==============================
class T3Verdict(unittest.TestCase):

    def test_closed_by_proven_write(self):
        v = service_debt.verdict(write={"landed": True, "known": True, "detail": "ok"})
        self.assertTrue(v["closed"])
        self.assertEqual(v["by"], service_debt.BY_WRITE)
        self.assertEqual(v["state"], service_debt.CLOSED)

    def test_closed_by_reread_register_cell_equal_and_greater(self):
        for got in (12212, 12500, 99999):
            v = service_debt.verdict(cell={"read": True, "km": got}, odometer=12212)
            self.assertTrue(v["closed"], f"регистр {got} ≥ 12212 — записано мимо нас")
            self.assertEqual(v["by"], service_debt.BY_CELL)

    def test_cell_below_debt_keeps_it_open(self):
        v = service_debt.verdict(cell={"read": True, "km": 12000}, odometer=12212)
        self.assertFalse(v["closed"])
        self.assertEqual(v["state"], service_debt.OPEN)

    def test_closed_by_explicit_human_decision(self):
        v = service_debt.verdict(human={"decided": True, "who": "@owner"})
        self.assertTrue(v["closed"])
        self.assertEqual(v["by"], service_debt.BY_HUMAN)
        self.assertIn("@owner", v["why"])

    def test_no_facts_is_unknown_not_closed(self):
        v = service_debt.verdict()
        self.assertEqual(v["state"], service_debt.UNKNOWN)
        self.assertFalse(v["closed"])

    def test_every_hole_refuses_to_close(self):
        """«Проверить не удалось» ≠ «записано» — замок против ложного зелёного."""
        holes = [
            dict(write={"landed": False, "known": False, "detail": "расписка не пришла"}),
            dict(write={"landed": False, "known": True, "detail": "km_decreasing"}),
            dict(cell={"read": False, "detail": "парк не прочитан"}, odometer=12212),
            dict(cell={"read": True, "km": None}, odometer=12212),
            dict(cell={"read": True, "km": 12212}, odometer=None),
            dict(cell={"read": True, "km": 12212}, odometer=""),
            dict(human={"decided": False}),
            dict(write=None, cell=None, human=None),
        ]
        for kw in holes:
            v = service_debt.verdict(**kw)
            self.assertFalse(v["closed"], f"дырка закрыла долг: {kw}")
            self.assertIn(v["state"], (service_debt.OPEN, service_debt.UNKNOWN))

    def test_unknown_and_open_are_told_apart(self):
        u = service_debt.verdict(cell={"read": False, "detail": "мост молчит"}, odometer=1)
        self.assertEqual(u["state"], service_debt.UNKNOWN, "смотреть не удалось")
        o = service_debt.verdict(cell={"read": True, "km": 5}, odometer=10)
        self.assertEqual(o["state"], service_debt.OPEN, "смотрели — не легло")

    def test_garbage_facts_never_close(self):
        for junk in ("да", 1, [], {"landed": "да"}, {"read": "да"}, {"decided": 1}):
            for slot in ("write", "cell", "human"):
                v = service_debt.verdict(**{slot: junk}, odometer=100)
                self.assertFalse(v["closed"], f"мусор в {slot} закрыл долг: {junk!r}")

    def test_state_always_from_the_vocabulary(self):
        for kw in (dict(), dict(write={"landed": True}), dict(cell={"read": True, "km": 9}, odometer=1)):
            self.assertIn(service_debt.verdict(**kw)["state"], service_debt.STATES)


# ============================== (5) СТОРОЖ: ДОЛГ ПРОХОДИТ ПРОВЕРКУ ВОЗРАСТА ===================
class T5Voice(unittest.TestCase):

    def test_debt_status_is_no_longer_skipped_before_the_age_check(self):
        """До 23.08 голый `continue` стоял ВЫШЕ проверки возраста — ни напоминаний, ни эскалации."""
        self.assertEqual(service_debt.voice(service_debt.STATUS, 7.0)["speak"], service_debt.REMIND)
        self.assertEqual(service_debt.voice(service_debt.STATUS, 60.0)["speak"],
                         service_debt.ESCALATE)

    def test_debt_reminder_goes_to_the_keeper_not_the_mechanic(self):
        """Механик своё сделал: работа названа, кнопка показана. Не нажали её Пым/владелец."""
        self.assertEqual(service_debt.voice(service_debt.STATUS, 7.0)["to"], service_debt.TO_KEEPER)
        self.assertEqual(service_debt.voice("ждёт_факт", 7.0)["to"], service_debt.TO_MECHANIC)

    def test_young_debt_is_quiet(self):
        self.assertEqual(service_debt.voice(service_debt.STATUS, 1.0)["speak"], service_debt.QUIET)

    def test_escalation_is_not_repeated(self):
        v = service_debt.voice(service_debt.STATUS, 60.0, escalated=True)
        self.assertEqual(v["speak"], service_debt.QUIET)

    def test_unknown_age_is_quiet_not_loud(self):
        v = service_debt.voice(service_debt.STATUS, None)
        self.assertEqual(v["speak"], service_debt.QUIET)
        self.assertIn("не прочитан", v["why"])

    def test_thresholds_are_arguments_not_hardcode(self):
        self.assertEqual(service_debt.voice(service_debt.STATUS, 3.0, remind_after_h=2.0)["speak"],
                         service_debt.REMIND)
        self.assertEqual(service_debt.voice(service_debt.STATUS, 3.0, remind_after_h=99.0)["speak"],
                         service_debt.QUIET)


# ============================== (8) ДВЕРИ: СТРОКА ДО ПОКАЗА КНОПКИ ============================
class T8Doors(unittest.TestCase):
    """Порядок вызовов, а не обещание: upsert обязан случиться РАНЬШЕ отправки сообщения."""

    def setUp(self):
        import splinter
        self.sp = splinter
        os.environ.pop("SERVICE_DEBT", None)

    def _door(self, which, **kw):
        order = []
        bus = _Bus({"service_pending_get": {"ok": False, "error": "not_found"}})

        async def _fake_send(*a, **k):
            order.append("СООБЩЕНИЕ")
            return type("M", (), {"message_id": 1})()

        async def _fake_hint(*a, **k):
            order.append("СООБЩЕНИЕ")
            return type("M", (), {"message_id": 1})()

        real_send, real_hint = self.sp._send, self.sp._hint_send
        real_up = self.sp._sp_debt_open
        try:
            self.sp._send = _fake_send
            self.sp._hint_send = _fake_hint

            def _spy(bridge, chat, topic, bike, kinds, km, door, oil_hint=False):
                r = real_up(bridge, chat, topic, bike, kinds, km, door, oil_hint=oil_hint)
                order.append("ДОЛГ" if r else "ДОЛГА НЕТ")
                return r
            self.sp._sp_debt_open = _spy
            self.sp._remember_cycle_msg = lambda *a, **k: None
            if which == "col":
                _run(self.sp._ask_service_col(None, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE,
                                              "gear", "12212", bridge=bus))
            else:
                _run(self.sp._ask_oil_or_km(None, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE, "12212",
                                            "overdue", 10800, -1412, bridge=bus, **kw))
        finally:
            self.sp._send, self.sp._hint_send = real_send, real_hint
            self.sp._sp_debt_open = real_up
        return order, bus

    def test_column_door_writes_the_debt_before_showing_the_button(self):
        order, bus = self._door("col")
        self.assertEqual(order[0], "ДОЛГ", f"кнопку показали раньше долга: {order}")
        self.assertIn("СООБЩЕНИЕ", order)
        ups = [kw for n, kw in bus.seen if n == "service_pending_upsert"]
        self.assertEqual(len(ups), 1)
        self.assertEqual(ups[0]["status"], service_debt.STATUS)
        self.assertEqual(ups[0]["done"], "gear")
        self.assertEqual(ups[0]["odometer"], "12212")
        self.assertEqual(ups[0]["bike"], FAKE_BIKE)

    def test_oil_door_writes_the_debt_before_showing_the_button(self):
        order, bus = self._door("oil", oil_hint=True)
        self.assertEqual(order[0], "ДОЛГ", f"кнопку показали раньше долга: {order}")
        ups = [kw for n, kw in bus.seen if n == "service_pending_upsert"]
        self.assertEqual(len(ups), 1)
        self.assertEqual(ups[0]["done"], "oil")

    def test_oil_door_without_the_claim_writes_nothing(self):
        order, bus = self._door("oil", oil_hint=False)
        self.assertEqual(order[0], "ДОЛГА НЕТ")
        self.assertEqual(bus.count("service_pending_upsert"), 0,
                         "срок ТО завёл фантомный долг — это ≥47 строк за 83 суток")
        self.assertIn("СООБЩЕНИЕ", order, "вопрос человеку задать всё равно обязаны")

    def test_bridge_down_still_shows_the_button(self):
        """FAIL-SAFE в сторону кнопки: долг — добавленная видимость, а не новый забор."""
        def _boom(*a, **k):
            raise RuntimeError("мост лёг")
        bus = _Bus({"service_pending_upsert": _boom,
                    "service_pending_get": {"ok": False, "error": "not_found"}})
        sent = []

        async def _fake_send(*a, **k):
            sent.append(1)
            return type("M", (), {"message_id": 1})()
        real = self.sp._send
        try:
            self.sp._send = _fake_send
            self.sp._remember_cycle_msg = lambda *a, **k: None
            _run(self.sp._ask_service_col(None, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE, "gear",
                                          "12212", bridge=bus))
        finally:
            self.sp._send = real
        self.assertEqual(len(sent), 1, "мост лёг — а кнопку человеку показать обязаны")


# ============ (6)(7) ОТРИЦАТЕЛЬНЫЙ ТЕСТ И ЕГО БЛИЗНЕЦ — БЕЗ НИХ ЗАДАЧА НЕ ЗАКРЫТА ============
class T6NegativeAndTwin(unittest.TestCase):
    """Сторож, который держит ВСЕГДА, не лучше того, который не держит НИКОГДА.

    Оба теста идут по ОДНОЙ дороге и различаются РОВНО одним: нажали кнопку или нет."""

    def setUp(self):
        import splinter
        self.sp = splinter
        os.environ.pop("SERVICE_DEBT", None)
        self.sp._SP_LAST_SENT.clear()

    def _row(self, age_h, odo="12212"):
        import datetime as dt
        born = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=age_h)
        return {"chat_id": FAKE_CHAT, "topic_id": FAKE_TOPIC, "bike": FAKE_BIKE,
                "declared": "gear", "done": "gear", "status": service_debt.STATUS,
                "odometer": odo, "created_at": born.isoformat().replace("+00:00", "Z"),
                "last_reminded_at": "", "note": ""}

    def _tick(self, bus, age_h):
        """Один оборот сторожа висяков по одной строке долга."""
        import time as _t
        said = []

        async def _fake_hint(*a, **k):
            said.append(k.get("text", ""))
            return type("M", (), {"message_id": 1})()
        real = self.sp._hint_send
        try:
            self.sp._hint_send = _fake_hint
            _run(self.sp._sp_debt_voice(None, bus, self._row(age_h), _t.time()))
        finally:
            self.sp._hint_send = real
        return said, bus

    # ---------- ОТРИЦАТЕЛЬНЫЙ: кнопку НЕ нажали ----------
    def test_negative_button_not_pressed_debt_survives_and_ages(self):
        # Регистр пуст → мимо бота никто не писал → долг обязан ОСТАТЬСЯ.
        bus = _Bus({"fleet": {"ok": True, "data": {"bikes": [{"name": FAKE_BIKE}]}},
                    "cell": _Clip(False, None, "клетка пуста")})
        # (а) молод — молчим, но НЕ закрываем
        said, _ = self._tick(bus, age_h=1.0)
        self.assertEqual(said, [], "молодой долг шумит")
        self.assertEqual(bus.count("service_pending_close"), 0, "молодой долг ЗАКРЫЛИ")
        # (б) состарился → ГОВОРИМ и всё ещё НЕ закрываем
        self.sp._SP_LAST_SENT.clear()
        said2, bus2 = self._tick(
            _Bus({"fleet": {"ok": True, "data": {"bikes": [{"name": FAKE_BIKE}]}},
                  "cell": _Clip(False, None, "клетка пуста")}), age_h=25.0)
        self.assertEqual(len(said2), 1, "долг состарился, а сторож промолчал")
        self.assertIn("не нажали", said2[0])
        self.assertEqual(bus2.count("service_pending_close"), 0,
                         "ДОЛГ ЗАКРЫЛСЯ САМ — ровно тот класс, ради которого писан модуль")
        # (в) по таймеру не гаснет НИКОГДА — даже в 10 раз старше эскалации
        v = service_debt.verdict(cell={"read": False, "detail": "клетка пуста"}, odometer=12212)
        self.assertFalse(v["closed"])

    # ---------- БЛИЗНЕЦ: кнопку нажали, запись доказана ----------
    def test_twin_button_pressed_and_write_proven_debt_closes(self):
        bus = _Bus()
        v = self.sp._sp_debt_close(bus, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE, kinds=["gear"],
                                   odometer=12212,
                                   write={"landed": True, "known": True, "detail": "расписка ok"})
        self.assertTrue(v["closed"], "запись доказана, а долг не закрылся")
        self.assertEqual(v["by"], service_debt.BY_WRITE)
        self.assertEqual(bus.count("service_pending_close"), 1)
        self.assertEqual(bus.seen[-1][1]["bike"], FAKE_BIKE)

    def test_twin_written_past_the_bot_closes_by_the_reread_cell(self):
        """Владелец внёс рукой ЧУЖОЕ число (больше нашего) — долг снят ПО ФАКТУ, а не по времени."""
        bus = _Bus({"fleet": {"ok": True, "data": {"bikes": [{"name": FAKE_BIKE}]}},
                    "cell": _Clip(True, 12500)})
        said, _ = self._tick(bus, age_h=25.0)
        self.assertEqual(bus.count("service_pending_close"), 1, "запись мимо бота не закрыла долг")
        self.assertEqual(said, [], "долг уже лежит в регистре — шуметь не о чем")

    def test_twin_human_said_no_work(self):
        bus = _Bus()
        v = self.sp._sp_debt_close(bus, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE, kinds=["oil"],
                                   odometer=12212,
                                   human={"decided": True, "who": "@pym",
                                          "detail": "нажато «Просто пробег»"})
        self.assertTrue(v["closed"])
        self.assertEqual(v["by"], service_debt.BY_HUMAN)
        self.assertEqual(bus.count("service_pending_close"), 1)

    def test_the_pair_differs_by_exactly_one_thing(self):
        """Одна дорога, один различитель — иначе близнец ничего не доказывает."""
        facts_no = dict(cell={"read": True, "km": 12000}, odometer=12212)
        facts_yes = dict(cell={"read": True, "km": 12212}, odometer=12212)
        self.assertFalse(service_debt.verdict(**facts_no)["closed"])
        self.assertTrue(service_debt.verdict(**facts_yes)["closed"])

    def test_escalation_fires_on_a_very_old_debt(self):
        """B4 по долгу до 23.08 не срабатывала НИ РАЗУ — `continue` стоял выше проверки."""
        calls = []

        async def _fake_esc(*a, **k):
            calls.append(a)
        bus = _Bus({"fleet": {"ok": True, "data": {"bikes": [{"name": FAKE_BIKE}]}},
                    "cell": _Clip(False, None, "клетка пуста")})
        real = self.sp._sp_escalate_stuck
        try:
            self.sp._sp_escalate_stuck = _fake_esc
            import time as _t
            _run(self.sp._sp_debt_voice(None, bus, self._row(60.0), _t.time()))
        finally:
            self.sp._sp_escalate_stuck = real
        self.assertEqual(len(calls), 1, "долг старше 48ч не дошёл до владельца")
        self.assertEqual(bus.count("service_pending_close"), 0)


# ============================== (9) ОТКАТ ====================================================
class T9Rollback(unittest.TestCase):

    def setUp(self):
        import splinter
        self.sp = splinter

    def tearDown(self):
        os.environ.pop("SERVICE_DEBT", None)

    def test_flag_off_touches_the_bridge_zero_times(self):
        os.environ["SERVICE_DEBT"] = "0"
        bus = _Bus()
        self.assertIsNone(self.sp._sp_debt_open(bus, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE,
                                                ["gear"], "12212", service_debt.DOOR_COL))
        self.assertIsNone(self.sp._sp_debt_close(bus, FAKE_CHAT, FAKE_TOPIC, FAKE_BIKE,
                                                 write={"landed": True}))
        self.assertEqual(bus.seen, [], "выключенная ветка обратилась к мосту")

    def test_flag_parser_matches_the_project(self):
        self.assertTrue(service_debt.enabled(None))
        self.assertTrue(service_debt.enabled("1"))
        for off in ("0", "false", "no", "off"):
            self.assertFalse(service_debt.enabled(off))


# ============================== (10) ЖИВОЙ СЛУЧАЙ ADV 350 372 ================================
class T10LiveAdv(unittest.TestCase):
    """Живой снимок листа «то_заявки» 23.08.2026 08:35 UTC — строку НЕ трогаем, только судим.

        chat -1002751134848 · тема 2583 · ADV 350 372
        declared=gear · done=gear · odometer='' · status='ждёт_факт'
        created_at 2026-08-22T07:12:13.019Z · last_reminded_at 2026-08-23T03:01:51Z
    """
    LIVE = {"bike": "ADV 350 372", "declared": "gear", "done": "gear", "odometer": "",
            "status": "ждёт_факт", "created_at": "2026-08-22T07:12:13.019Z"}

    def test_new_logic_would_not_have_created_this_row(self):
        """У обеих кнопочных дверей условие — ЧИСЛО. У этой строки его нет: кнопки не было."""
        ok, why = service_debt.accepted(service_debt.DOOR_COL, ["gear"], self.LIVE["odometer"])
        self.assertFalse(ok)
        self.assertIn("числ", why)
        self.assertIsNone(service_debt.open_fields(service_debt.DOOR_COL, ["gear"],
                                                   self.LIVE["odometer"]))

    def test_its_status_is_not_the_debt_status_so_the_old_path_still_owns_it(self):
        self.assertNotEqual(self.LIVE["status"], service_debt.STATUS)
        self.assertEqual(service_debt.voice(self.LIVE["status"], 25.3)["to"],
                         service_debt.TO_MECHANIC)

    def test_when_the_number_arrives_it_becomes_a_debt_and_the_new_branch_owns_it(self):
        """Придёт пробег → `_sp_advance_to_confirm` переведёт в `ждёт_подтверждения`.
        ДО 23.08 это был бы конец следа: `continue` выше проверки возраста. Теперь — нет."""
        v = service_debt.voice(service_debt.STATUS, 25.3)
        self.assertEqual(v["speak"], service_debt.REMIND)
        self.assertEqual(v["to"], service_debt.TO_KEEPER)

    def test_escalation_moment_is_arithmetic_not_a_guess(self):
        """created 22.08 07:12:13Z + 48ч = 24.08 07:12:13Z — момент, когда всплыл бы у владельца."""
        import datetime as dt
        born = dt.datetime.fromisoformat(self.LIVE["created_at"].replace("Z", "+00:00"))
        due = born + dt.timedelta(hours=48)
        self.assertEqual(due.strftime("%Y-%m-%d %H:%M:%S"), "2026-08-24 07:12:13")
        age_at_due = (due - born).total_seconds() / 3600.0
        self.assertEqual(service_debt.voice(self.LIVE["status"], age_at_due)["speak"],
                         service_debt.ESCALATE)

    def test_empty_odometer_can_never_be_closed_by_a_cell(self):
        """Сверять не с чем → «неизвестно», и это НЕ «записано»."""
        v = service_debt.verdict(cell={"read": True, "km": 99999}, odometer=self.LIVE["odometer"])
        self.assertFalse(v["closed"])
        self.assertEqual(v["state"], service_debt.UNKNOWN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
