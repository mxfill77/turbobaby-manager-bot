# -*- coding: utf-8 -*-
"""INTAKECONFIRM1610 (16.10.2026): голдены ПРЕЖНЕГО поведения ветки «3) approve / нет / правки» и привязки фото.

Ручка `INTAKE_CONFIRM_STRICT=0`. Модуль `intake_confirm` этот тест НЕ импортирует и к именам выпуска не
обращается (кроме необязательной сверки ручки через getattr) — поэтому он обязан быть зелёным на ДВУХ деревьях:
  1) копия `cbe1322` (до выпуска), куда добавлен только этот файл — там ручки нет, работает прежний код;
  2) дерево выпуска с ручкой 0.
Это и есть доказательство «байт-в-байт»: каждая отправка (текст дословно), список вызовов моста (имена и kwargs),
статус черновика, исключение там, где прежний код падал.

Дефекты записаны КАК ПРЕЖНЕЕ поведение ручки 0 и помечены «ДЕФЕКТ Д1/Д2»: Д1 — согласие подстрокой и раньше
отказа («не ставь», «не надо», «погода», «около того», «нет, когда оплатит» записывают бронь); Д2 — исход
«неизвестно» назван «❌ Не записалось», статус остаётся approved. Данные синтетические, сеть не трогается.
"""
import asyncio
import os
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)                 # корень СВОЕГО дерева — первым

for _f in ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", "CONTRACT_REF_GEN"):
    os.environ.pop(_f, None)
os.environ["INTAKE_CONFIRM_STRICT"] = "0"           # откат: прежнее поведение (на cbe1322 ручки нет — не влияет)

_TMP = tempfile.mkdtemp(prefix="intake_confirm_legacy_t_")
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json")):
    os.environ[_k] = os.path.join(_TMP, _name)

try:
    import fcntl  # noqa: F401
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    _fc.lockf = lambda *a, **k: None
    sys.modules["fcntl"] = _fc

import splinter as S  # noqa: E402

INTAKE = S.INTAKE_CHAT
BIKE = "CB 300CC R 9011"
P = "🐀 Splinter\n"
OLD_BOOKED = P + "✅ Бронь записана, строка 33, статус «Бронь»."
OLD_REJECT = P + "❌ Бронь отклонена."
OLD_EDIT = P + "✏️ Принял, жду исправленную карточку."
OLD_DUP12 = P + "⚠️ Уже есть такая бронь (строка 12)."


def old_fail(err, msg):
    return P + "❌ Не записалось: %s. %s" % (err, msg)


FIELDS = {"bike": BIKE, "name": "Мария Тест", "date_start": "15-11-2026", "date_end": "20-11-2026",
          "deposit": "passport", "helmets": 2, "contacts": "+66 80 000 0000", "note": None}
TICKET = ("issue_write_ticket", {})
BOOK = ("create_booking", FIELDS)

SUMMARY = ("🐀 Splinter · Карточка принята.\n"
           "Клиент: Мария Тест · контакты: +66 80 000 0000\n"
           "Модель: CB 300CC R 9011 · даты 15-11-2026 — 20-11-2026\n"
           "Опыт: —\n"
           "Депозит: паспорт\n"
           "Доставка: — (https://maps.app.goo.gl/test) ⚠️ район не определён — проверить вручную\n"
           "Шлемы: 2 · паспорт-фото: да\n"
           "Паспорт распознал (проверьте): MARIA TEST, TST, до 2030-01-01\n"
           "Наличие: даты не распознаны — проверить наличие вручную\n"
           "\nСтавлю бронь? да / нет / правки")


class U:
    def __init__(self, uname, is_bot=False):
        self.username = uname
        self.is_bot = is_bot
        self.id = None


class Reply:
    def __init__(self):
        self.from_user = U("turbobaby_manager_bot", is_bot=True)
        self.forum_topic_created = None


class Msg:
    def __init__(self, text, uname="deramor", photo=False, reply_to_bot=False):
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.message_id = 4242
        self.media_group_id = None
        self.from_user = U(uname)
        self.reply_to_message = Reply() if reply_to_bot else None


class Ctx:
    class _B:
        username = "turbobaby_manager_bot"
    bot = _B()


class Boom(Exception):
    pass


class FakeBridge:
    def __init__(self, reply="ok", ticket_raises=None):
        self.calls = []
        self.reply = reply
        self.ticket_raises = ticket_raises

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        if self.ticket_raises is not None:
            raise self.ticket_raises
        return {"ok": True, "ticket": "t-test"}

    def create_booking(self, **k):
        self.calls.append(("create_booking", dict(k)))
        r = self.reply
        if r == "ok":
            return {"ok": True, "row": 33, "booking_id": "b-1", "bike": k.get("bike")}
        if isinstance(r, BaseException):
            raise r
        return r


SENDS = []


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    SENDS.append((chat_id, text))


S._send = rec_send
FINALIZE_CALLS = []
_REAL_FINALIZE = S._intake_finalize


async def spy_finalize(draft, msg, context, bridge):
    FINALIZE_CALLS.append(draft.get("status"))
    return await _REAL_FINALIZE(draft, msg, context, bridge)


async def fake_ocr(photo_msg, chat_id, context, bridge):
    S._INTAKE_PASSPORT[chat_id] = {"file_id": "f-test", "ocr_status": "ok", "ts": time.time(),
                                   "fields": {"full_name": "MARIA TEST", "country": "TST", "expire_date": "2030-01-01"}}
    return (True, S._INTAKE_PASSPORT[chat_id]["fields"])


PASSPORT_SAVES = []


def fake_passport_save(chat_id, draft, bridge):
    PASSPORT_SAVES.append(draft.get("status"))


S._intake_finalize = spy_finalize
S._intake_passport_ocr = fake_ocr
S._intake_passport_save = fake_passport_save


def reset(**kw):
    del SENDS[:]
    del FINALIZE_CALLS[:]
    del PASSPORT_SAVES[:]
    for dct in (S._INTAKE_DRAFTS, S._INTAKE_PASSPORT, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES, S._RECENT_BOOKINGS):
        dct.clear()
    d = {"model": BIKE, "client": "Мария Тест", "date_start": "15-11-2026", "date_end": "20-11-2026",
         "date_start_iso": None, "date_end_iso": None, "contacts": "+66 80 000 0000",
         "delivery_url": "https://maps.app.goo.gl/test", "helmets": 2, "deposit_type": "паспорт",
         "passport_photo": True, "ts": time.time(), "status": "awaiting_approval"}
    d.update(kw)
    S._INTAKE_DRAFTS[INTAKE] = d


def say(bridge, text, **kw):
    asyncio.run(S._handle_intake(Msg(text, **kw), Ctx(), bridge, None))


def status():
    return S._INTAKE_DRAFTS[INTAKE]["status"]


def texts():
    return [t for c, t in SENDS if c == INTAKE]


B1 = (1, "booked", [OLD_BOOKED])          # записано
Q0 = (0, "awaiting_approval", [])         # молчание, карточка ждёт

# Входы раздела 3 проекта (P/N) + сверх таблицы. (ввод, опции) → (вызовов create_booking, статус, отправки)
LEGACY = [
    ("да", {}, B1), ("Да.", {}, B1), ("ок", {}, B1),
    ("ok", {}, Q0), ("OK", {}, Q0),                                  # латиница не знакома прежней ветке — молчание
    ("ставь", {}, B1), ("подтверждаю", {}, B1), ("да 👍", {}, B1), ("ДА!!!", {}, B1), ("да, ставь", {}, B1),
    ("👍", {}, Q0), ("✅", {}, Q0), ("👍🏻", {}, Q0),
    ("не ставь", {}, B1),                    # ДЕФЕКТ Д1: «ставь» подстрокой и раньше отказа
    ("не надо", {}, Q0),                     # ДЕФЕКТ Д1 (иной вид): «на-д-о» НЕ содержит «да» (проект §1/§4 ошибся),
                                             # прежняя ветка отказ не узнаёт и МОЛЧИТ — 0 вызовов, карточка ждёт
    ("нет", {}, (0, "rejected", [OLD_REJECT])),
    ("отмена", {}, (0, "rejected", [OLD_REJECT])),
    ("не подтверждаю", {}, B1),              # ДЕФЕКТ Д1
    ("нет, когда оплатит", {}, B1),          # ДЕФЕКТ Д1: «ког-да»
    ("всегда так", {}, B1),                  # ДЕФЕКТ Д1
    ("погода", {}, B1),                      # ДЕФЕКТ Д1
    ("около того", {}, B1),                  # ДЕФЕКТ Д1: «ок-оло»
    ("да, но поправь дату", {}, B1),         # ДЕФЕКТ Д1: правка не судится — согласие раньше
    ("ок, исправь имя", {}, B1),             # ДЕФЕКТ Д1
    (None, {}, Q0), ("😂", {}, Q0),
    ("да", {"uname": "pym_thai"}, Q0),       # не аппрувер — ветка 3 не входит
    ("да?", {}, B1),                         # ДЕФЕКТ Д1: вопрос читается согласием
    ("ставим?", {}, Q0),
    ("да, я позвоню клиенту", {}, B1),       # ДЕФЕКТ Д1
    ("да нет", {}, B1),                      # ДЕФЕКТ Д1: согласие раньше отказа
    ("погода", {"reply_to_bot": True}, B1),  # ДЕФЕКТ Д1
    ("нет правок", {}, B1),                  # ДЕФЕКТ Д1: «прав-ок»
    ("нет, исправь дату", {}, B1),           # ДЕФЕКТ Д1: «да-ту»
    ("@turbobaby_manager_bot погода", {}, B1),   # ДЕФЕКТ Д1
    ("оставь", {}, B1),                      # ДЕФЕКТ Д1: «о-ставь»
    ("не ок", {}, B1),                       # ДЕФЕКТ Д1
    ("правки", {}, (0, "awaiting_approval", [OLD_EDIT])),
]


class Legacy(unittest.TestCase):
    def setUp(self):
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"

    def test_knob_is_off_where_it_exists(self):
        f = getattr(S, "_intake_confirm_strict_on", None)       # на cbe1322 ручки нет — сверять нечего
        if f is not None:
            self.assertFalse(f())

    def test_inputs_section3(self):
        self.assertGreaterEqual(len(LEGACY), 38)
        for text, opt, (n, st, sends) in LEGACY:
            with self.subTest(text=text, opt=opt):
                reset()
                b = FakeBridge()
                say(b, text, **opt)
                self.assertEqual(b.calls, [TICKET, BOOK] * n)
                self.assertEqual(status(), st)
                self.assertEqual(texts(), sends)

    def _w(self, reply="ok", ticket_raises=None):
        reset()
        b = FakeBridge(reply=reply, ticket_raises=ticket_raises)
        say(b, "да")
        return b

    def _again(self, b):
        before = list(b.calls)
        say(b, "да")
        self.assertEqual(b.calls, before, "повторное «да» при статусе %s ничего не зовёт" % status())

    def test_w1_booked(self):
        b = self._w()
        self.assertEqual((b.calls, status(), texts()), ([TICKET, BOOK], "booked", [OLD_BOOKED]))
        self._again(b)

    def test_w2_duplicate(self):
        b = self._w(reply={"ok": False, "error": "duplicate", "row": 12})
        self.assertEqual((b.calls, status(), texts()), ([TICKET, BOOK], "approved", [OLD_DUP12]))
        self._again(b)

    def test_w3_w6_named_not_written(self):
        """ДЕФЕКТ Д2: неизвестный исход назван «❌ Не записалось», статус approved."""
        cases = [({"ok": False, "error": "timeout", "message": "Timeout >60s"}, old_fail("timeout", "Timeout >60s")),
                 ({"ok": False, "error": "request_failed", "message": "HTTP 502"},
                  old_fail("request_failed", "HTTP 502")),
                 ({"ok": False, "error": "card_deadline", "message": "бюджет"}, old_fail("card_deadline", "бюджет")),
                 ({"ok": False, "error": "receipt_unknown", "outcome": "unknown", "message": "расписка"},
                  old_fail("receipt_unknown", "расписка")),
                 ({"ok": False, "error": "write_failed", "message": "setValue"}, old_fail("write_failed", "setValue")),
                 ({"ok": False, "error": "internal_error"}, old_fail("internal_error", "")),
                 ({"ok": False, "error": "json_parse_error"}, old_fail("json_parse_error", "")),
                 ({"ok": False, "error": "weird_code"}, old_fail("weird_code", "")),
                 ({"ok": False, "error": ""}, old_fail("?", "")),
                 ({"ok": False}, old_fail("?", ""))]
        for reply, want in cases:
            with self.subTest(reply=reply):
                b = self._w(reply=reply)
                self.assertEqual((b.calls, status(), texts()), ([TICKET, BOOK], "approved", [want]))
                self._again(b)
        self.assertEqual(old_fail("timeout", "Timeout >60s"), P + "❌ Не записалось: timeout. Timeout >60s")

    def test_w7_exception(self):
        """ДЕФЕКТ Д2: исключение после отправки — «❌ Не записалось: exception. обрыв»."""
        b = self._w(reply=RuntimeError("обрыв"))
        self.assertEqual((b.calls, status(), texts()),
                         ([TICKET, BOOK], "approved", [P + "❌ Не записалось: exception. обрыв"]))

    def test_w8_none_reply_raises(self):
        """Прежний код на ответ None падает AttributeError (res.get) — без отправки, статус approved."""
        reset()
        b = FakeBridge(reply=None)
        with self.assertRaises(AttributeError):
            say(b, "да")
        self.assertEqual((b.calls, status(), texts()), ([TICKET, BOOK], "approved", []))

    def test_w9_not_written_codes(self):
        for code in ("bad_json", "no_ticket", "unknown_action", "missing_bike", "missing_name", "bike_not_resolved",
                     "bad_dates", "sheet_not_found", "booking_conflict"):
            with self.subTest(code=code):
                b = self._w(reply={"ok": False, "error": code, "message": "отказ моста"})
                self.assertEqual((b.calls, status(), texts()),
                                 ([TICKET, BOOK], "approved", [old_fail(code, "отказ моста")]))

    def test_w10_ticket_raises(self):
        b = self._w(ticket_raises=Boom("нет билета"))
        self.assertEqual((b.calls, status(), texts()),
                         ([TICKET], "approved", [P + "❌ Не записалось: exception. нет билета"]))

    def test_w11_photo_rearms_card(self):
        """ДЕФЕКТ Д2 (следствие): фото после неясного исхода взводит карточку, «да» — второй create_booking."""
        b = self._w(reply={"ok": False, "error": "timeout", "message": "Timeout >60s"})
        self.assertEqual(status(), "approved")
        say(b, None, photo=True)
        self.assertEqual(FINALIZE_CALLS, ["approved"], "_intake_finalize вызван")
        self.assertEqual(PASSPORT_SAVES, ["approved"])
        self.assertEqual(status(), "awaiting_approval")
        self.assertEqual(texts(), [old_fail("timeout", "Timeout >60s"), SUMMARY])
        b.reply = "ok"
        say(b, "да")
        self.assertEqual(b.calls, [TICKET, BOOK, TICKET, BOOK], "второй вызов create_booking")
        self.assertEqual(status(), "booked")
        self.assertEqual(texts()[-1], OLD_BOOKED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
