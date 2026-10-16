# -*- coding: utf-8 -*-
"""APPROVEFIX1610 (16.10.2026): ответ на карточки выдачи/приёма/брони во «Входящих» — адрес, смысл, пробег, исход.

Повод: Codex TB-OWNER-EFFICIENCY-1610-2054 (runtime-approval-review.json, minimum_acceptance) и карта
QUEUE4_INTAKE_SUBSTR_MAP М1–М6 (дерево 13b4188). Проверяется через НАСТОЯЩИЕ обработчики Splinter
(`_handover_activation_card` / `_return_close_card` → `_handle_intake`) с изолированным мостом-подделкой, в ОБОИХ
положениях RENTAL_CASE_APPROVALS: 0 — ветки 4/5 в памяти процесса (строгий путь, ручка INTAKE_CONFIRM_STRICT по
умолчанию ВКЛ); 1 — ожидания хранилища дела (временная база), `approval_decision` / `_rc_execute`.

Разделы:
  (A) выдача, флаг 0: дословные негативы карты — 0 вызовов activate_booking; позитивы реплаем на СВОЮ карточку — ровно
      1 вызов с точной целью; без реплая / пересланное / чужой автор / срок / повтор — 0 или не больше 1;
  (B) приём, флаг 0: негативы — 0 вызовов close_booking; ложный отказ «через интернет-банк» карточку не гасит; пробег —
      точный km_end (из ответа целиком или поле карточки), деньги / срок / два числа / длинное число — 0 вызовов;
  (C) адрес, флаг 0: две карточки разных байков (замена старой новой), одновременно бронь/выдача/приём — реплай
      попадает ровно в свою ветку, чужая карточка не гаснет и не исполняется;
  (D) исход, флаг 0: отказ до отправки (нет билета) / «неизвестно» после отправки (timeout, обрыв) / записано — три
      разных исхода, повтора «неизвестно» нет;
  (E) флаг 1 (хранилище дела): те же негативы для activate/close/booking (М4/М5), пробег закрытия, исход «неизвестно»;
  (F) ручка INTAKE_CONFIRM_STRICT=0: ветки 4/5 прежние байт-в-байт — дефекты М1/М2/М6 записаны КАК ПРЕЖНЕЕ
      поведение отката (этот раздел обязан быть зелёным и на 13b4188, и на ветке);
  (P) чистые части: intake_confirm.km_arg / red_outcome / decide_action, rental_case_rules.approval_decision(action).

Каждый негатив (A)–(E) обязан падать на 13b4188 (там согласие — подстрокой и без привязки к карточке); стражи, уже
зелёные на 13b4188, названы в отчёте отдельно. Сеть запрещена подменой socket (rental_case_fakes), память Splinter и
база дела — только во временном каталоге прогона (TMP/K4_TTMP). Данные синтетические.
"""
import asyncio
import datetime
import json
import os
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, ROOT):                  # итог: ROOT — первым, tests/ — вторым (ловушка метода: чужой корень не берём)
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

FLAGS = ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", "CONTRACT_REF_GEN")
for _f in FLAGS:
    os.environ.pop(_f, None)
os.environ.pop("INTAKE_CONFIRM_STRICT", None)       # ручка не задана → строгий режим по умолчанию

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
STATE_DIR = tempfile.mkdtemp(prefix="approvefix_state_", dir=TTMP)
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),
                  ("RESTART_HANDOFF_STATE", "restart_handoff.json")):
    os.environ[_k] = os.path.join(STATE_DIR, _name)

import rental_case_fakes as F  # noqa: E402 — сеть запрещена при импорте

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
BIKE_A = "CB 300CC R 9011"
BIKE_B = "PCX 160 4410"
APPROVER = "deramor"                 # INTAKE_APPROVERS (по нику) — путь флага 0
OWNER = "turbophuket"
OWNER_ID = 504608015                 # APPROVER_IDS по умолчанию — путь флага 1
TZ = datetime.timedelta(hours=7)
P = "🐀 Splinter\n"


def local_now():
    return datetime.datetime.now(datetime.timezone.utc) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


def bk_row(row=17, bike=BIKE_A, name="Анна Тест", booking_id="bk-a", contacts="+66 82 555 1111"):
    """Бронь, выдаваемая сегодня (живой формат двери clients)."""
    return F.make_row(row=row, status="Бронь", bike=bike, name=name, date_start=dt(0, "09:00"), date_end=dt(5),
                      contacts=contacts, booking_id=booking_id, deposit_raw="3000", debt=0)


def bk_row_b():
    """Бронь второго байка, другой клиент и контакт (иначе дело К4 спросит «продолжение?» вместо карточки)."""
    return bk_row(row=18, bike=BIKE_B, name="Борис Тест", booking_id="bk-b", contacts="+66 89 333 4444")


def rent_row(row=21, bike=BIKE_A, name="Иван Тест", booking_id="bk-r"):
    """Текущая аренда «В аренде» с −3 по +2 сут."""
    return F.make_row(row=row, status="В аренде", bike=bike, name=name, date_start=dt(-3), date_end=dt(2),
                      contacts="+66 81 234 5678", booking_id=booking_id, deposit_raw="5000", debt=500)


# --------------------------------------------------------------------------------------------- подделки Telegram/моста
class BotUser(object):
    id = 1
    username = "turbobaby_manager_bot"
    is_bot = True


class U(object):
    def __init__(self, uname=APPROVER, uid=None):
        self.username = uname
        self.id = uid
        self.is_bot = False


class Sent(object):
    def __init__(self, mid, chat_id, text):
        self.message_id = mid
        self.chat_id = chat_id
        self.text = text
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = BotUser()


class Msg(object):
    _next = [810000]

    def __init__(self, text, uname=APPROVER, uid=None, reply_to=None, at=None, mid=None):
        if mid is None:
            Msg._next[0] += 1
            mid = Msg._next[0]
        self.message_id = mid
        self.text = text
        self.caption = None
        self.photo = None
        self.sticker = None
        self.chat_id = INTAKE
        self.message_thread_id = None
        self.media_group_id = None
        self.date = datetime.datetime.fromtimestamp(time.time() if at is None else at, datetime.timezone.utc)
        self.from_user = U(uname, uid)
        self.reply_to_message = reply_to


class Ctx(object):
    class B(object):
        username = "turbobaby_manager_bot"
    bot = B()


class Bridge(object):
    """Мост: дверь clients (живой формат) + красные шаги с журналом вызовов. Режимы: ticket "ok"|"none";
    activate/close "ok"|"timeout" (ответ потерян, строка НЕ тронута)|"raise_after_send" (обрыв ПОСЛЕ записи)."""

    def __init__(self, rows):
        self.rows = [dict(r) for r in rows]
        self.calls = []
        self.tickets = 0
        self.ticket_mode = "ok"
        self.activate_mode = "ok"
        self.close_mode = "ok"

    def red(self, name):
        return [k for n, k in self.calls if n == name]

    def _call(self, action, **k):
        assert action == "clients", action
        return F.clients_reply(self.rows, filter=k.get("filter", "all"))

    def clients(self, filter="active"):
        return F.clients_reply(self.rows, filter=filter)

    def find_bike(self, q):
        return {"name": q, "status": "ДОМА", "oil_last_km": 30500}

    def read_events(self, bike, limit=30):
        return {"ok": False, "error": "нет в подделке"}

    def state_set(self, **k):
        return {"ok": True}

    def add_event(self, **k):
        return {"ok": True, "saved": True}

    def service_pending_get(self, *a, **k):
        return {"ok": False, "error": "not_found"}

    def service_list(self, *a, **k):
        return {"items": []}

    def closing_upsert(self, **k):
        return {"ok": True, "row": 5, "total_due": 1500}

    def issue_write_ticket(self):
        self.tickets += 1
        if self.ticket_mode == "none":
            return {"ok": False, "error": "ticket_failed"}
        return {"ok": True, "ticket": "t-approvefix"}

    def _find(self, bike, name, status):
        for r in self.rows:
            if r["bike"] == bike and r["name"] == name and r["status"] == status:
                return r
        return None

    def activate_booking(self, bike, name, date_start=None):
        self.calls.append(("activate_booking", {"bike": bike, "name": name, "date_start": date_start}))
        if self.activate_mode == "timeout":
            return {"ok": False, "error": "timeout", "message": "Timeout >60s"}
        r = self._find(bike, name, "Бронь")
        if r is None:
            return {"ok": False, "error": "booking_not_found", "message": "не найдена"}
        r["status"] = "В аренде"
        if self.activate_mode == "raise_after_send":
            raise RuntimeError("обрыв после записи")
        return {"ok": True, "activated": True, "row": r["row"], "bike": bike, "name": name}

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        if self.close_mode == "timeout":
            return {"ok": False, "error": "timeout", "message": "Timeout >60s"}
        if km_end in (None, ""):
            return {"ok": False, "error": "km_required", "message": "km_end обязателен"}
        r = self._find(bike, name, "В аренде")
        if r is None:
            return {"ok": False, "error": "not_active", "message": "нет активной"}
        r["status"] = "Завершена"
        if self.close_mode == "raise_after_send":
            raise RuntimeError("обрыв после записи")
        return {"ok": True, "closed": True, "row": r["row"], "bike": bike, "name": name}

    def create_booking(self, **k):
        self.calls.append(("create_booking", dict(k)))
        n = 30 + len(self.red("create_booking"))
        bk = "bk-new-%d" % n
        self.rows.append(F.make_row(row=n, status="Бронь", bike=k.get("bike") or "", name=k.get("name") or "—",
                                    date_start=dt(4), date_end=dt(9), contacts=k.get("contacts") or "",
                                    booking_id=bk))
        return {"ok": True, "row": n, "booking_id": bk, "bike": k.get("bike")}


SENDS = []
_MID = [920000]


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    _MID[0] += 1
    s = Sent(_MID[0], chat_id, text)
    SENDS.append(s)
    return s


async def rec_pass(*a, **k):
    return None


S._send = rec_send
S._send_bike_card = rec_pass
S._after_mileage = rec_pass
S._ask_mileage_confirm = rec_pass
S._ask_service_col = rec_pass


def run(coro):
    return asyncio.run(coro)


def reset():
    del SENDS[:]
    for d in (S._RETURN_CLOSES, S._RET_CLOSE_WARN_TS, S._HANDOVER_ACTIVATIONS, S._HO_ACT_WARN_TS, S._INTAKE_DRAFTS,
              S._RECENT_BOOKINGS, S._INTAKE_PASSPORT):
        d.clear()
    S._RC_STORE = None
    for f in FLAGS:
        os.environ.pop(f, None)
    os.environ.pop("INTAKE_CONFIRM_STRICT", None)


def texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards(word):
    return [s for s in SENDS if s.chat_id == INTAKE and word in s.text]


def ho_card(b, bike=BIKE_A):
    run(S._handover_activation_card(Ctx(), b, bike))
    cs = cards("Активирую")
    assert cs, texts()
    return cs[-1]


def ret_card(b, bike=BIKE_A, km="35200", total_due=1500):
    run(S._return_close_card(Ctx(), b, bike, km=km, total_due=total_due))
    cs = cards("Завершаю")
    assert cs, texts()
    return cs[-1]


def say(b, text, reply=None, uname=APPROVER, uid=None, forward=False, at=None, mid=None):
    m = Msg(text, uname=uname, uid=uid, reply_to=reply, at=at, mid=mid)
    if forward:
        m.forward_origin = object()
    run(S._handle_intake(m, Ctx(), b, None))
    return m


def booking_draft(card_mid):
    return {"model": BIKE_A, "client": "Мария Новая", "date_start": "15-11-2026", "date_end": "20-11-2026",
            "date_start_iso": None, "date_end_iso": None, "contacts": "+66 83 777 2222",
            "delivery_url": "https://maps.app.goo.gl/x", "helmets": 2, "deposit_type": "паспорт",
            "passport_photo": True, "ts": time.time(), "status": "awaiting_approval", "ic_msg_ids": [card_mid]}


class Case(unittest.TestCase):
    def setUp(self):
        reset()

    def tearDown(self):
        reset()


# ======================================================================================================== (A) выдача
ACT_NEGATIVE = ("не активируй", "не активировать пока", "не подтверждаю", "да нет", "нет, когда оплатит", "погода",
                "около того", "сейчас уточню срок", "дам знать", "да?", "да, но сначала оплата", "👍", "да 35200")
ACT_POSITIVE = ("да", "Да.", "ок", "ok", "yes", "активируй", "подтверждаю", "да, активируй 👍")


class A_Activation(Case):
    def test_a1_negatives_reply_on_own_card_zero_calls(self):
        for text in ACT_NEGATIVE:
            with self.subTest(text=text):
                reset()
                b = Bridge([bk_row()])
                card = ho_card(b)
                say(b, text, reply=card)
                self.assertEqual(b.red("activate_booking"), [], "негатив карты М1 исполнил активацию: %r" % text)
                self.assertEqual(b.tickets, 0, "на негатив билет 4.2 не выписывается")

    def test_a2_positives_reply_on_own_card_exactly_one_call(self):
        for text in ACT_POSITIVE:
            with self.subTest(text=text):
                reset()
                b = Bridge([bk_row()])
                card = ho_card(b)
                say(b, text, reply=card)
                self.assertEqual(b.red("activate_booking"), [{"bike": BIKE_A, "name": "Анна Тест",
                                                              "date_start": dt(0, "09:00")}])
                self.assertIn(P + "✅ В аренде, строка 17.", texts())

    def test_a3_refusal_reply_cancels_without_call(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        say(b, "не активируй", reply=card)
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "rejected")
        self.assertIn(P + "❌ Активацию отменил — статус в CRM не менял.", texts())

    def test_a4_yes_without_reply_asks_names_card_then_reply_on_ask_counts(self):
        b = Bridge([bk_row()])
        ho_card(b)
        say(b, "да")
        self.assertEqual(b.red("activate_booking"), [], "«да» без реплая не адресовано карточке")
        asks = [s for s in SENDS if "засчитываю только реплаем" in s.text]
        self.assertEqual(len(asks), 1, texts())
        self.assertIn("строка 17", asks[0].text)
        self.assertNotIn("Анна", asks[0].text, "в уточнении нет имени клиента (ПДн)")
        say(b, "да", reply=asks[0])
        self.assertEqual(len(b.red("activate_booking")), 1, "реплай на адресное уточнение — ответ этой карточке")

    def test_a5_forwarded_yes_silent(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        n = len(SENDS)
        say(b, "да", reply=card, forward=True)
        self.assertEqual(b.red("activate_booking"), [])
        self.assertEqual(len(SENDS), n, "пересланное — не ответ подтверждающего: молчание")

    def test_a6_foreign_author_zero_calls(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        say(b, "да", reply=card, uname="pym_thai")
        self.assertEqual(b.red("activate_booking"), [])
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting")

    def test_a7_ttl_expired_reply_zero_calls(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        S._HANDOVER_ACTIVATIONS[INTAKE]["ts"] -= (S._HO_ACT_TTL + 60)
        say(b, "да", reply=card)
        self.assertEqual(b.red("activate_booking"), [])

    def test_a8_duplicate_answer_one_call(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        m = say(b, "да", reply=card)
        run(S._handle_intake(m, Ctx(), b, None))            # тот же апдейт повторно
        say(b, "да", reply=card)                             # второй ответ на ту же карточку
        self.assertEqual(len(b.red("activate_booking")), 1, "повтор ответа второго вызова не даёт")
        self.assertEqual(b.tickets, 1)


# ========================================================================================================= (B) приём
CLOSE_NEGATIVE = ("не подтверждаю", "завершена?", "заверши руками", "завершу сам", "когда оплатит — закроем",
                  "сейчас уточню срок", "да, доплатил 40000", "да, через 10 минут", "да, но поправь пробег", "стоп",
                  "погода", "дам знать", "да нет", "нет, когда оплатит", "да 12345678", "да 35300 35400",
                  "около часа", "да, я позвоню клиенту")


class B_Close(Case):
    def test_b1_negatives_reply_on_own_card_zero_calls(self):
        for text in CLOSE_NEGATIVE:
            with self.subTest(text=text):
                reset()
                b = Bridge([rent_row()])
                card = ret_card(b)
                say(b, text, reply=card)
                self.assertEqual(b.red("close_booking"), [], "негатив карты М2/М6 закрыл аренду: %r" % text)

    def test_b2_false_refusal_internet_bank_keeps_card(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        say(b, "через интернет-банк", reply=card)
        self.assertEqual(b.red("close_booking"), [])
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting", "«интер-нет» — не отказ: карточка жива")
        self.assertNotIn(P + "❌ Закрытие отменил — статус в CRM не менял.", texts())

    def test_b3_km_exact_target(self):
        cases = (("да", "35200"),                  # проверенное поле карточки (пробег из контекста возврата)
                 ("да 35300", "35300"),
                 ("да 35 300", "35300"),
                 ("да, закрывай 35300", "35300"),
                 ("завершай", "35200"),
                 ("закрывай", "35200"))
        for text, km in cases:
            with self.subTest(text=text):
                reset()
                b = Bridge([rent_row()])
                card = ret_card(b)
                say(b, text, reply=card)
                self.assertEqual(b.red("close_booking"), [{"bike": BIKE_A, "name": "Иван Тест",
                                                           "date_start": dt(-3), "km_end": km,
                                                           "paid_total": 1500.0}])

    def test_b4_km_missing_on_card_reply_number_closes(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="")
        say(b, "да", reply=card)
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], [None], "без пробега — мост отказал до записи")
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting", "km_required — карточка жива")
        say(b, "да 35 300", reply=card)
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], [None, "35300"])
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "closed")

    def test_b6_forwarded_foreign_late_duplicate_close(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        say(b, "да", reply=card, forward=True)
        say(b, "да", reply=card, uname="pym_thai")
        say(b, "да")                                                     # без реплая — уточнение
        self.assertEqual(b.red("close_booking"), [], "пересланное / не одобряющий / без реплая — 0 вызовов")
        m = say(b, "да", reply=card)
        run(S._handle_intake(m, Ctx(), b, None))                        # тот же апдейт повторно
        self.assertEqual(len(b.red("close_booking")), 1, "повтор ответа второго вызова не даёт")
        reset()
        b = Bridge([rent_row()])
        card = ret_card(b)
        S._RETURN_CLOSES[INTAKE]["ts"] -= (S._RET_CLOSE_TTL + 60)
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), [], "просроченная карточка приёма не исполняется")

    def test_b5_money_time_many_long_numbers_zero_calls(self):
        for text in ("да, доплатил 40000", "да, через 10 минут", "да 35300 35400", "да 12345678", "да 5"):
            with self.subTest(text=text):
                reset()
                b = Bridge([rent_row()])
                card = ret_card(b, km="")
                say(b, text, reply=card)
                self.assertEqual(b.red("close_booking"), [], "число не пробег сдачи: %r" % text)


# ========================================================================================================= (C) адрес
class C_Routing(Case):
    def test_c1_reply_on_replaced_card_A_does_not_activate_B(self):
        b = Bridge([bk_row(), bk_row_b()])
        card_a = ho_card(b, BIKE_A)
        card_b = ho_card(b, BIKE_B)
        self.assertNotEqual(card_a.message_id, card_b.message_id)
        say(b, "да", reply=card_a)
        self.assertEqual(b.red("activate_booking"), [], "«да» реплаем на карточку A активировал байк B")
        self.assertTrue(any("заменена новой" in t for t in texts()), texts())
        say(b, "да", reply=card_b)
        self.assertEqual(b.red("activate_booking"), [{"bike": BIKE_B, "name": "Борис Тест",
                                                      "date_start": dt(0, "09:00")}])

    def test_c2_booking_activation_close_reply_goes_to_its_card_only(self):
        b = Bridge([rent_row(), bk_row_b()])
        close_card = ret_card(b, BIKE_A)
        act_card = ho_card(b, BIKE_B)
        bk_card = types.SimpleNamespace(message_id=4100, from_user=U("dasha_mgr"), forum_topic_created=None)
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(bk_card.message_id)
        say(b, "да", reply=close_card)
        self.assertEqual(len(b.red("close_booking")), 1, "реплай на карточку приёма — закрытие")
        self.assertEqual(b.red("activate_booking"), [])
        self.assertEqual(b.red("create_booking"), [])
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting")
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval")
        say(b, "да", reply=act_card)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval")
        say(b, "да", reply=bk_card)
        self.assertEqual(len(b.red("create_booking")), 1, "реплай на карточку брони — бронь (строгий путь)")

    def test_c3_refusal_on_activation_card_does_not_reject_booking(self):
        b = Bridge([bk_row_b()])
        act_card = ho_card(b, BIKE_B)
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(4100)
        say(b, "нет", reply=act_card)
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "rejected")
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval",
                         "отказ карточке выдачи погасил карточку брони")

    def test_c4_unbound_refusal_with_two_cards_extinguishes_nothing(self):
        b = Bridge([bk_row_b()])
        ho_card(b, BIKE_B)
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(4100)
        say(b, "нет")
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting")
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval",
                         "«нет» без реплая погасило карточку брони при ждущей выдаче")
        self.assertTrue(any("несколько карточек" in t for t in texts()), texts())

    def test_c5_edit_on_close_card_does_not_mark_booking_edit(self):
        b = Bridge([rent_row()])
        close_card = ret_card(b)
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(4100)
        say(b, "да, но поправь пробег", reply=close_card)
        self.assertEqual(b.red("close_booking"), [])
        self.assertFalse(S._INTAKE_DRAFTS[INTAKE].get("ic_edit_asked"), "правка к приёму записалась брони")


# ========================================================================================================== (D) исход
class D_Outcome(Case):
    def test_d1_no_ticket_activation_not_sent(self):
        b = Bridge([bk_row()])
        b.ticket_mode = "none"
        card = ho_card(b)
        say(b, "да", reply=card)
        self.assertEqual(b.red("activate_booking"), [], "без билета вызов не уходит")
        self.assertTrue(any("❌ Активация не прошла: no_ticket" in t for t in texts()), texts())

    def test_d2_timeout_after_send_activation_unknown_no_repeat(self):
        b = Bridge([bk_row()])
        b.activate_mode = "timeout"
        card = ho_card(b)
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertIn(P + "⚠️ Исход активации неизвестен (timeout) — проверь CRM; повтор не делаю.", texts())
        self.assertFalse(any("не менял" in t for t in texts()), "«неизвестно» назвали «CRM не менял»")
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("activate_booking")), 1, "«неизвестно» повторно не исполняется")

    def test_d3_exception_after_send_close_unknown_no_repeat(self):
        b = Bridge([rent_row()])
        b.close_mode = "raise_after_send"
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("close_booking")), 1)
        self.assertIn(P + "⚠️ Исход закрытия неизвестен (RuntimeError) — проверь CRM; повтор не делаю.", texts())
        self.assertFalse(any("не менял" in t for t in texts()), texts())
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("close_booking")), 1)

    def test_d4_timeout_close_unknown_and_no_ticket_close_not_sent(self):
        b = Bridge([rent_row()])
        b.close_mode = "timeout"
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertIn(P + "⚠️ Исход закрытия неизвестен (timeout) — проверь CRM; повтор не делаю.", texts())
        reset()
        b = Bridge([rent_row()])
        b.ticket_mode = "none"
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), [])

    def test_d5_confirmed_write_and_named_refusal(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertIn(P + "✅ Завершена, строка 21.", texts())
        reset()
        b = Bridge([bk_row(name="Другой Клиент")])
        card = ho_card(b)
        b.rows[0]["name"] = "Сменили Имя"                      # мост отказывает ДО записи: booking_not_found
        say(b, "да", reply=card)
        self.assertTrue(any("❌ Активация не прошла: booking_not_found" in t and "не менял" in t for t in texts()),
                        texts())


# ================================================================================================ (E) флаг 1 (дело)
class E_CaseStore(Case):
    def setUp(self):
        super(E_CaseStore, self).setUp()
        os.environ["RENTAL_CASE_APPROVALS"] = "1"
        import rental_case
        d = tempfile.mkdtemp(prefix="approvefix_k4_%s_" % self._testMethodName[5:20], dir=TTMP)
        p = os.path.join(d, "rental_case.sqlite")
        rental_case.Store.create(p)
        os.environ["RENTAL_CASE_DB"] = p

    def k4(self, b, text, reply):
        return say(b, text, reply=reply, uname=OWNER, uid=OWNER_ID)

    def bk_card(self, b):
        d = booking_draft(None)
        d.pop("ic_msg_ids")
        S._INTAKE_DRAFTS[INTAKE] = d
        run(S._intake_finalize(d, Msg("🆕 БРОНЬ …"), Ctx(), b))
        cs = [s for s in SENDS if s.chat_id == INTAKE and "РЕПЛАЕМ" in s.text and "Активирую" not in s.text
              and "Завершаю" not in s.text]
        self.assertTrue(cs, texts())
        return cs[-1]

    def test_e1_activation_negatives_zero_calls(self):
        for text in ("да?", "да 35200", "да, я позвоню клиенту", "ок, позже", "да, но сначала оплата",
                     "подтверждено", "ёлки, да", "закрывай", "да, но поправь дату"):
            with self.subTest(text=text):
                self.setUp()
                b = Bridge([bk_row()])
                card = ho_card(b)
                self.assertIn("РЕПЛАЕМ", card.text)
                self.k4(b, text, card)
                self.assertEqual(b.red("activate_booking"), [], "К4 (М4): %r исполнил активацию" % text)

    def test_e2_close_negatives_zero_calls(self):
        for text in ("завершена?", "заверши руками", "завершу сам", "да, но поправь пробег", "да, доплатил 40000",
                     "да, через 10 минут", "активируй", "да 12345678", "да 35300 35400"):
            with self.subTest(text=text):
                self.setUp()
                b = Bridge([rent_row()])
                card = ret_card(b)
                self.k4(b, text, card)
                self.assertEqual(b.red("close_booking"), [], "К4 (М4/М6): %r закрыл аренду" % text)

    def test_e3_booking_negatives_zero_create(self):
        for text in ("да, но поправь дату", "да?", "да 15", "ставь бронь"):
            with self.subTest(text=text):
                self.setUp()
                b = Bridge([rent_row()])
                card = self.bk_card(b)
                self.k4(b, text, card)
                self.assertEqual(b.red("create_booking"), [], "К4 (М5): %r поставил бронь мимо строгого пути" % text)

    def test_e4_positives_exact_target_and_km(self):
        b = Bridge([bk_row()])
        card = ho_card(b)
        self.k4(b, "активируй", card)
        self.assertEqual(b.red("activate_booking"), [{"bike": BIKE_A, "name": "Анна Тест",
                                                      "date_start": dt(0, "09:00")}])
        for text, km in (("да", "35200"), ("да 35 300", "35300"), ("да 35300", "35300")):
            with self.subTest(text=text):
                self.setUp()
                b = Bridge([rent_row()])
                card = ret_card(b)
                self.k4(b, text, card)
                self.assertEqual([c["km_end"] for c in b.red("close_booking")], [km])
        self.setUp()
        b = Bridge([rent_row()])
        card = self.bk_card(b)
        self.k4(b, "да", card)
        self.assertEqual(len(b.red("create_booking")), 1)

    def test_e5_unknown_after_send_and_no_ticket(self):
        b = Bridge([bk_row()])
        b.activate_mode = "timeout"
        card = ho_card(b)
        self.k4(b, "да", card)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertTrue(any("Исход активации неизвестен (timeout)" in t for t in texts()), texts())
        self.assertFalse(any("не менял" in t for t in texts()), "«неизвестно» названо «CRM не менял»")
        self.k4(b, "да", card)
        self.assertEqual(len(b.red("activate_booking")), 1, "повтора нет")
        self.setUp()
        b = Bridge([bk_row()])
        b.ticket_mode = "none"
        card = ho_card(b)
        self.k4(b, "да", card)
        self.assertEqual(b.red("activate_booking"), [], "без билета вызов не уходит")

    def test_e6_guards_refusals_and_replaced_card(self):
        for text in ("не активируй", "не подтверждаю", "да нет", "нет, когда оплатит", "погода", "дам знать"):
            with self.subTest(text=text):
                self.setUp()
                b = Bridge([bk_row()])
                card = ho_card(b)
                self.k4(b, text, card)
                self.assertEqual(b.red("activate_booking"), [])
        self.setUp()
        b = Bridge([bk_row(), bk_row_b()])
        card_a = ho_card(b, BIKE_A)
        card_b = ho_card(b, BIKE_B)
        self.assertNotEqual(card_a.message_id, card_b.message_id, "вторая карточка не родилась: %r" % texts())
        self.k4(b, "да", card_a)
        self.assertEqual(b.red("activate_booking"), [])
        self.k4(b, "да", card_b)
        self.assertEqual([c["bike"] for c in b.red("activate_booking")], [BIKE_B])


# =============================================================================== (F) ручка 0: прежнее байт-в-байт
class F_KnobOffLegacy(Case):
    """INTAKE_CONFIRM_STRICT=0 → ветки 4/5 прежние (13b4188). Дефекты М1/М2/М6 записаны КАК ПРЕЖНЕЕ поведение отката:
    этот раздел зелёный и на 13b4188, и на ветке — доказательство «байт-в-байт» (тексты дословно, вызовы моста)."""

    def setUp(self):
        super(F_KnobOffLegacy, self).setUp()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"

    def test_f1_m1_defect_ne_aktiviruy_activates(self):
        b = Bridge([bk_row()])
        ho_card(b)
        say(b, "не активируй")                                         # ДЕФЕКТ М1 (без реплая, подстрокой)
        self.assertEqual(len(b.red("activate_booking")), 1)
        self.assertEqual(texts()[-1], P + "✅ В аренде, строка 17.")

    def test_f2_m2_m6_defects_close(self):
        b = Bridge([rent_row()])
        ret_card(b)
        say(b, "да, доплатил 40000")                                   # ДЕФЕКТ М6: деньги — пробегом
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], ["40000"])
        reset()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        b = Bridge([rent_row()])
        ret_card(b)
        say(b, "завершена?")                                           # ДЕФЕКТ М2: вопрос — закрытие
        self.assertEqual(len(b.red("close_booking")), 1)
        reset()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"
        b = Bridge([rent_row()])
        ret_card(b)
        say(b, "через интернет-банк")                                  # ДЕФЕКТ: «интер-нет» — ложный отказ
        self.assertEqual(texts()[-1], P + "❌ Закрытие отменил — статус в CRM не менял.")
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "rejected")

    def test_f3_unknown_named_not_changed_legacy(self):
        b = Bridge([bk_row()])
        b.activate_mode = "timeout"
        ho_card(b)
        say(b, "да")
        self.assertEqual(texts()[-1], P + "❌ Активация не прошла: timeout. Timeout >60s\n"
                                          "Статус в CRM не менял — переведи руками.")
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "error")


# =================================================================================================== (P) чистые части
class P_Pure(unittest.TestCase):
    def test_p1_km_arg(self):
        import intake_confirm as IC
        for text, km in (("да 35300", "35300"), ("да 35 300", "35300"), ("да 35 300", "35300"),
                         ("да", None), ("да 5", None), ("да 12345678", None), ("да 35300 35400", None),
                         ("да 2 35300", None), ("да 10 000 5", None), ("10", "10")):
            with self.subTest(text=text):
                self.assertEqual(IC.km_arg(text)[0], km)

    def test_p2_red_outcome_three_words(self):
        import intake_confirm as IC
        self.assertEqual(IC.red_outcome(None, False, "activate"), IC.NOT_WRITTEN)
        self.assertEqual(IC.red_outcome({"ok": True}, True, "close"), IC.WRITTEN)
        self.assertEqual(IC.red_outcome(None, True, "close"), IC.UNKNOWN)
        for code in ("timeout", "request_failed", "receipt_unknown", "write_failed", "internal_error", "", "duplicate"):
            with self.subTest(code=code):
                self.assertEqual(IC.red_outcome({"ok": False, "error": code}, True, "close"), IC.UNKNOWN)
                self.assertEqual(IC.red_outcome({"ok": False, "error": code}, True, "activate"), IC.UNKNOWN)
        self.assertEqual(IC.red_outcome({"ok": False, "error": "booking_not_found"}, True, "activate"), IC.NOT_WRITTEN)
        self.assertEqual(IC.red_outcome({"ok": False, "error": "booking_not_found"}, True, "close"), IC.UNKNOWN,
                         "списки «не записано» у действий свои, не общие")
        self.assertEqual(IC.red_outcome({"ok": False, "error": "odometer_back"}, True, "close"), IC.NOT_WRITTEN)

    def test_p3_booking_words_unchanged_by_extras(self):
        import intake_confirm as IC
        for text in ("да", "не ставь", "да, но поправь дату", "погода", "да?", "активируй", "завершай"):
            with self.subTest(text=text):
                self.assertEqual(IC.decide_action(text, "booking"), IC.decide(text))
        self.assertEqual(IC.decide("активируй"), IC.SILENT, "слова выдачи бронь не ставят")

    def test_p4_k4_action_aware(self):
        import rental_case_rules as R
        pd = R.PARAMS_DEFAULT
        self.assertEqual(R.approval_decision("да 35200", pd, action="close"), "yes")
        self.assertEqual(R.approval_decision("да 35200", pd, action="activate"), "unclear")
        self.assertEqual(R.approval_decision("да 35200", pd, action="booking"), "unclear")
        self.assertEqual(R.approval_decision("активируй", pd, action="close"), "unclear", "глагол чужого действия")
        self.assertEqual(R.approval_decision("завершай", pd, action="activate"), "unclear")
        self.assertEqual(R.approval_km("да 35 300", pd), "35300")
        self.assertIsNone(R.approval_km("да, доплатил 40000", pd))
        self.assertIsNone(R.approval_km("да", pd))


if __name__ == "__main__":
    unittest.main(verbosity=2)
