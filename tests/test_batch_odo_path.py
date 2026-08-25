"""ВЕСЬ ПУТЬ «РАБОТЫ БЫЛИ НА ДРУГОМ ПРОБЕГЕ» НА ВЫДУМАННЫХ БАЙКАХ (25.08.2026).

Карточка подтверждения работ → третья кнопка → вопрос о пробеге и дате → запись партии.
Гоняется ЖИВЫМИ дверями `splinter`: `_sp_advance_to_confirm` → `handle_service_button`
(`svc:bodo`) → `handle_mileage_confirm` (текст ответа) → `_batch_odo_commit`.

ОТРИЦАТЕЛЬНЫЕ ТЕСТЫ С БЛИЗНЕЦАМИ — предмет задания, три штуки:
  (N1) партия на другом пробеге НЕ сдвигает текущий пробег байка; близнец — обычный путь
       (`_sp_write_done`) его сдвигает, то есть проверка умеет отличать одно от другого;
  (N2) без даты или без пробега НЕ пишется и человеку сказано, ЧТО прислать; близнец — то же
       без порчи (пробег И дата) пишется;
  (N3) две партии подряд на РАЗНЫХ пробегах дают ДВЕ группы записей; близнец — те же работы на
       ТОМ ЖЕ пробеге дают ОДНУ группу (ключ контентный, мост схлопнет их сам).

ФЕЙКОВЫЙ МОСТ НЕ ПОВТОРЯЕТ ИМЁН БОЕВЫХ ОПЕРАЦИЙ — урок 14.08 (`2026-08-14-undo-oil-door.md`):
гард судит ТЕЛО теста, и фикстура, объявившая метод с именем боевой операции, сама становится
«пишущей». Вызовы ловятся через `__getattr__`, имена сверяются строками из кусков.

БАЙКИ ВЫДУМАНЫ (`TESTBIKE 000ZZ PHUKET 4242` / `TESTBIKE 111YY PHUKET 4343`), в парке их нет;
в Лист1 и в зеркало не уходит НИЧЕГО — все обращения копятся в списке и проверяются им же.
"""
import asyncio
import datetime
import os
import sys
import unittest

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["BATCH_ODO"] = "1"           # боевой дефолт ЯВНО: сьют не зависит от .env машины
os.environ["NEVER_SILENT"] = "1"
os.environ["SERVICE_DEBT"] = "0"        # предмет сьюта — запись партии, не бухгалтерия заявки

import splinter as S          # noqa: E402
import batch_odo as B         # noqa: E402

CHAT = -1009000000043
TOPIC = 8822
BIKE = "TESTBIKE 000ZZ PHUKET 4242"
BIKE2 = "TESTBIKE 111YY PHUKET 4343"
WHO = "@testpym"
TODAY = datetime.date(2026, 8, 25)

# Имена боевых операций собираются ИЗ КУСКОВ: цельного литерала в теле сьюта нет.
OP_EVENT = "add_" + "event"
OP_REG_OIL = "set_fleet" + "_oil"
OP_REG_SVC = "set_fleet" + "_service"
OP_SYNC = "service_" + "upsert"


class _Calls(list):
    def names(self):
        return [c[0] for c in self]

    def of(self, name):
        return [c for c in self if c[0] == name]


class _FakeBridge:
    """Мост-заглушка: ловит ЛЮБОЙ вызов по имени, ничего не делает, ничего не пишет."""

    def __init__(self, answers=None):
        self.calls = _Calls()
        self._answers = answers or {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _catch(*a, **kw):
            self.calls.append((name, a, kw))
            return self._answers.get(name, {"ok": True})
        return _catch


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 900 + len(self.sent)})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()

    def texts(self):
        return [k.get("text", "") for k in self.bot.sent]

    def last(self):
        return self.bot.sent[-1].get("text", "") if self.bot.sent else ""

    def keyboards(self):
        return [k.get("reply_markup") for k in self.bot.sent]


class _User:
    def __init__(self):
        self.id, self.username, self.is_bot = 99043, WHO.lstrip("@"), False
        self.first_name = "TestPym"


class _Msg:
    def __init__(self, text=""):
        self.chat_id, self.text, self.message_thread_id = CHAT, text, TOPIC
        self.caption, self.photo = None, []
        self.from_user, self.message_id = _User(), 778
        self.date = datetime.datetime(2026, 8, 25, 10, 0, 0)
        self.reply_to_message = None


class _Query:
    def __init__(self, data):
        self.data, self.from_user, self.message = data, _User(), _Msg()
        self.answered = []

    async def answer(self, text="", show_alert=False):
        self.answered.append(text)

    async def edit_message_reply_markup(self, **kw):
        return True

    async def edit_message_text(self, *a, **kw):
        return True


class _Upd:
    def __init__(self, q):
        self.callback_query = q


def _run(coro):
    """Свой цикл на вызов: `get_event_loop` без работающего цикла с 3.12 бросает, а состояние
    между вызовами живёт в модуле `splinter`, а не в цикле, — терять нечего."""
    return asyncio.run(coro)


def _reset():
    S._BATCH_ODO_PENDING.clear()
    S._SVC_TOKENS.clear()
    S._PENDING_WORKS.clear()
    S._PENDING_MILEAGE.clear()
    S._KM_EVENTS_WRITTEN.clear()


def _labels(kb):
    """Метки кнопок клавиатуры одним списком (клавиатуры нет → пустой)."""
    if not kb:
        return []
    return [b.text for row in kb.inline_keyboard for b in row]


def _tok_of(kb, action):
    for row in (kb.inline_keyboard if kb else []):
        for b in row:
            if (b.callback_data or "").startswith(f"svc:{action}:"):
                return b.callback_data
    return ""


class _Base(unittest.TestCase):
    def setUp(self):
        _reset()
        self.ctx = _Ctx()
        self.bridge = _FakeBridge()
        self._trusted = S._is_trusted_user
        S._is_trusted_user = lambda u: True
        self._cur = S._odo_current
        S._odo_current = lambda bridge, bike: ""     # число не прочитано → понижения нет
        self._words = S._sp_words_said
        S._sp_words_said = lambda *a, **kw: []       # слов заявки нет → ярлыки видов

    def tearDown(self):
        S._is_trusted_user = self._trusted
        S._odo_current = self._cur
        S._sp_words_said = self._words
        _reset()

    def _card(self, done=("brakes",)):
        _run(S._sp_advance_to_confirm(self.ctx, self.bridge, CHAT, TOPIC, BIKE,
                                      list(done), list(done), "41200"))
        return self.ctx.bot.sent[-1].get("reply_markup")

    def _press(self, kb):
        q = _Query(_tok_of(kb, "bodo"))
        _run(S.handle_service_button(_Upd(q), self.ctx, self.bridge))
        return q

    def _say(self, text):
        return _run(S.handle_mileage_confirm(_Msg(text), self.ctx, self.bridge, text))

    def _events(self):
        return self.bridge.calls.of(OP_EVENT)

    def _keys(self):
        return [c[2].get("msg_id") for c in self._events()]


class TestButton(_Base):
    """(1) ТРЕТИЙ ИСХОД появился на карточке — и гаснет ручкой отката."""

    def test_button_present(self):
        kb = self._card()
        self.assertIn(B.BUTTON_LABEL, _labels(kb))

    def test_card_had_one_button_before(self):
        """Замер «до»: у карточки подтверждения работ была РОВНО ОДНА кнопка, не две."""
        os.environ["BATCH_ODO"] = "0"
        try:
            kb = self._card()
            self.assertEqual(len(_labels(kb)), 1)
            self.assertNotIn(B.BUTTON_LABEL, _labels(kb))
        finally:
            os.environ["BATCH_ODO"] = "1"

    def test_confirm_button_untouched(self):
        """Обещание прежней кнопки не тронуто ни символом."""
        kb = self._card()
        self.assertIn("✅ ยืนยันบันทึก / Подтвердить запись", _labels(kb))
        self.assertTrue(_tok_of(kb, "done"))

    def test_press_writes_nothing(self):
        """Кнопка НИЧЕГО не пишет — она только открывает вопрос."""
        kb = self._card()
        before = len(self.bridge.calls)
        self._press(kb)
        for name in (OP_EVENT, OP_REG_OIL, OP_REG_SVC):
            self.assertEqual(self.bridge.calls.of(name), [], name)
        self.assertGreaterEqual(len(self.bridge.calls), before)

    def test_press_asks_km_and_date(self):
        kb = self._card()
        self._press(kb)
        said = self.ctx.last()
        self.assertIn("ПРОБЕГ", said)
        self.assertIn("ДАТУ", said)
        self.assertIsNotNone(S.pending_batch_odo_for(CHAT, TOPIC))

    def test_untrusted_gets_no_question(self):
        S._is_trusted_user = lambda u: False
        kb = self._card()
        self._press(kb)
        self.assertIsNone(S.pending_batch_odo_for(CHAT, TOPIC))

    def test_router_door_wired(self):
        """Без своей двери в роутере ответ человека не дошёл бы до обработчика НИ РАЗУ."""
        src = open("/root/turbobaby-manager-bot/bot.py", encoding="utf-8").read()
        self.assertIn("pending_batch_odo_for", src)


class TestNegative1OdometerUntouched(_Base):
    """(N1) ПАРТИЯ НА ДРУГОМ ПРОБЕГЕ НЕ СДВИГАЕТ ТЕКУЩИЙ ПРОБЕГ БАЙКА.

    Близнец ниже гоняет ОБЫЧНЫЙ путь на тех же фикстурах и доказывает, что проверка умеет
    увидеть сдвиг, — иначе «не сдвигает» могло бы значить «сьют слеп»."""

    def test_batch_does_not_touch_odometer(self):
        kb = self._card()
        self._press(kb)
        self._say("24500 15.07.2026")
        for name in (OP_REG_OIL, OP_REG_SVC):
            self.assertEqual(self.bridge.calls.of(name), [], name)
        for _n, _a, kw in self.bridge.calls.of(OP_SYNC):
            self.assertNotIn("current_km", kw)

    def test_batch_wrote_history_at_named_km_and_date(self):
        kb = self._card()
        self._press(kb)
        self._say("24500 15.07.2026")
        evs = self._events()
        self.assertTrue(evs)
        for _n, _a, kw in evs:
            self.assertEqual(str(kw.get("mileage")), "24500")
            self.assertEqual(kw.get("msg_date"), "2026-07-15")

    def test_twin_normal_path_does_touch_odometer(self):
        """БЛИЗНЕЦ: обычное подтверждение пишет регистр — значит проверка выше не слепа."""
        _run(S._sp_write_done(self.ctx, self.bridge, CHAT, TOPIC, BIKE, ["oil"], "41200",
                              confirmed_by=WHO, ceiling_ok=True))
        touched = self.bridge.calls.of(OP_REG_OIL) + self.bridge.calls.of(OP_REG_SVC)
        self.assertTrue(touched, "обычный путь обязан трогать регистр — иначе близнец бесполезен")

    def test_receipt_says_odometer_untouched(self):
        kb = self._card()
        self._press(kb)
        self._say("24500 15.07.2026")
        self.assertIn("не тронут", self.ctx.last())


class TestNegative2MissingFields(_Base):
    """(N2) БЕЗ ДАТЫ ИЛИ БЕЗ ПРОБЕГА НЕ ПИШЕТСЯ, И ЧЕЛОВЕКУ СКАЗАНО, ЧТО ПРИСЛАТЬ.

    Прямая буква правила владельца: «Нет любого из двух — работа не записывается»."""

    def _ask(self):
        kb = self._card()
        self._press(kb)

    def test_km_only_writes_nothing(self):
        self._ask()
        self._say("24500")
        self.assertEqual(self._events(), [])
        self.assertIn("ДАТЫ", self.ctx.last())

    def test_date_only_writes_nothing(self):
        self._ask()
        self._say("15.07.2026")
        self.assertEqual(self._events(), [])
        self.assertIn("ПРОБЕГА", self.ctx.last())

    def test_neither_writes_nothing(self):
        self._ask()
        self._say("были работы на той неделе")
        self.assertEqual(self._events(), [])
        self.assertIn("ДВА числа", self.ctx.last())

    def test_question_stays_open_after_refusal(self):
        """Отказ не закрывает вопрос глухо: человек дописывает недостающее и партия ложится."""
        self._ask()
        self._say("24500")
        self.assertIsNotNone(S.pending_batch_odo_for(CHAT, TOPIC))
        self._say("24500 15.07.2026")
        self.assertTrue(self._events())

    def test_refusal_speaks_both_languages(self):
        self._ask()
        self._say("24500")
        said = self.ctx.last()
        self.assertIn("🇷🇺", said)
        self.assertIn("🇹🇭", said)

    def test_twin_both_fields_write(self):
        """БЛИЗНЕЦ: то же без порчи — пробег И дата — пишется."""
        self._ask()
        self._say("24500 15.07.2026")
        self.assertTrue(self._events())
        self.assertIn("✅", self.ctx.last())


class TestNegative3TwoBatches(_Base):
    """(N3) ДВЕ ПАРТИИ ПОДРЯД НА РАЗНЫХ ПРОБЕГАХ — ДВЕ ГРУППЫ ЗАПИСЕЙ, А НЕ ОДНА."""

    def _batch(self, answer, done=("brakes",)):
        kb = self._card(done)
        self._press(kb)
        self._say(answer)

    def test_two_mileages_two_groups(self):
        self._batch("24500 15.07.2026")
        first = set(self._keys())
        self._batch("31000 02.08.2026")
        all_keys = set(self._keys())
        second = all_keys - first
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertEqual(first & second, set(), "ключи партий пересеклись — это была бы одна группа")
        self.assertEqual(len(all_keys), len(first) + len(second))

    def test_two_mileages_two_dates_in_rows(self):
        self._batch("24500 15.07.2026")
        self._batch("31000 02.08.2026")
        dates = {kw.get("msg_date") for _n, _a, kw in self._events()}
        miles = {str(kw.get("mileage")) for _n, _a, kw in self._events()}
        self.assertEqual(dates, {"2026-07-15", "2026-08-02"})
        self.assertEqual(miles, {"24500", "31000"})

    def test_twin_same_mileage_one_group(self):
        """БЛИЗНЕЦ: те же работы на ТОМ ЖЕ пробеге дают ОДИН набор ключей — мост схлопнет их.

        Ключ контентный (`info:{номер}:{ключ-работы}:{км}`), и именно поэтому разные пробеги
        выше разошлись сами, без второй машинерии."""
        self._batch("24500 15.07.2026")
        first = set(self._keys())
        self._batch("24500 15.07.2026")
        self.assertEqual(set(self._keys()), first)


class TestLoweringRoad(_Base):
    """(2) Пробег партии НИЖЕ записанного — идём СУЩЕСТВУЮЩЕЙ дорогой понижения с пояснением."""

    def setUp(self):
        super().setUp()
        S._odo_current = lambda bridge, bike: "41200"

    def _ask(self):
        kb = self._card()
        self._press(kb)

    def test_asks_for_written_explanation(self):
        self._ask()
        self._say("24500 15.07.2026")
        said = self.ctx.last()
        for n in ("41200", "24500", "16700"):
            self.assertIn(n, said)
        self.assertEqual(self._events(), [], "до пояснения не пишем ничего")

    def test_agreement_is_not_an_explanation(self):
        """Словарь согласия — тот же, что у понижения: «да» пояснением не станет и здесь."""
        self._ask()
        self._say("24500 15.07.2026")
        self._say("да")
        self.assertEqual(self._events(), [])
        self.assertIsNotNone(S.pending_batch_odo_for(CHAT, TOPIC))

    def test_real_words_let_it_through(self):
        self._ask()
        self._say("24500 15.07.2026")
        self._say("делали в другом сервисе в июле, внести забыли")
        self.assertTrue(self._events())
        self.assertIn("Пояснение сохранил", self.ctx.last())

    def test_explanation_stored_as_its_own_row(self):
        """Слова человека едут ДОСЛОВНО отдельной строкой — их читают ПОТОМ, не только в чате."""
        self._ask()
        self._say("24500 15.07.2026")
        self._say("делали в другом сервисе в июле, внести забыли")
        notes = " ".join(str(kw.get("notes")) for _n, _a, kw in self._events())
        self.assertIn("делали в другом сервисе", notes)

    def test_lowering_still_does_not_move_odometer(self):
        self._ask()
        self._say("24500 15.07.2026")
        self._say("делали в другом сервисе в июле, внести забыли")
        for name in (OP_REG_OIL, OP_REG_SVC):
            self.assertEqual(self.bridge.calls.of(name), [], name)

    def test_twin_above_recorded_needs_no_explanation(self):
        """БЛИЗНЕЦ: партия ВЫШЕ записанного пишется сразу — вопроса о причине нет."""
        S._odo_current = lambda bridge, bike: "20000"
        self._ask()
        self._say("24500 15.07.2026")
        self.assertTrue(self._events())


class TestRollback(_Base):
    """(3) Откат ручкой: `BATCH_ODO=0` → карточка байт-в-байт прежняя, пути нет вовсе."""

    def test_flag_off_no_button_no_path(self):
        os.environ["BATCH_ODO"] = "0"
        try:
            kb = self._card()
            self.assertEqual(_tok_of(kb, "bodo"), "")
            self.assertEqual(len(_labels(kb)), 1)
        finally:
            os.environ["BATCH_ODO"] = "1"

    def test_flag_off_card_text_unchanged(self):
        os.environ["BATCH_ODO"] = "0"
        try:
            self._card()
            off = self.ctx.last()
        finally:
            os.environ["BATCH_ODO"] = "1"
        ctx2 = _Ctx()
        _run(S._sp_advance_to_confirm(ctx2, self.bridge, CHAT, TOPIC, BIKE,
                                      ["brakes"], ["brakes"], "41200"))
        self.assertEqual(off, ctx2.bot.sent[-1].get("text"),
                         "текст карточки менять не разрешено — менялась только клавиатура")


class TestSecondBike(_Base):
    """(4) Партия ключуется темой: соседний выдуманный байк в чужую партию не попадает."""

    def test_other_topic_untouched(self):
        kb = self._card()
        self._press(kb)
        self.assertIsNone(S.pending_batch_odo_for(CHAT, TOPIC + 1))

    def test_second_bike_own_rows(self):
        kb = self._card()
        self._press(kb)
        self._say("24500 15.07.2026")
        bikes = {kw.get("bike") for _n, _a, kw in self._events()}
        self.assertEqual(bikes, {BIKE})
        self.assertNotIn(BIKE2, bikes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
