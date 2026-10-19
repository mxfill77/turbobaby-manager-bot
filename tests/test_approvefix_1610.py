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
  (P) чистые части: intake_confirm.km_arg / red_outcome / decide_action, rental_case_rules.approval_decision(action);
  (R) Р1 приёмки 571a117: отказ / вопрос / условие БЕЗ реплая не становится согласием ни одним последующим «да» (пробы
      X-bind приёмки дословно + цепочки, отказ реплаем, снятие прежней привязки, две карточки, флаг 1, бронь);
  (RK) Р1-К повторной приёмки e34e086: согласие ДРУГОГО действия без реплая при одной ждущей карточке («закрывай» при
      ждущей выдаче, «активируй» при ждущем приёме) — пояснение без привязки, ни одного вызова; зеркала: согласие
      СВОЕГО действия по-прежнему привязывает уточнение, две карточки — прежний ответ;
  (RB) остаток 1 приёмки 8bfcfa3 (бронь): «да?» / тег / «нет» реплаем на чужое → «да» на ответ бота → «да» на
      уточнение — create_booking не рождается; зеркала: «да» без реплая и реплай на сообщение бота этой жизни — прежняя
      привязка;
  (RW) остаток 2: словарь отказов К4 (флаг 1) не уже строгой ветки — «стоп», «stop», «cancel», «нельзя», «неа» (и
      весь intake_confirm.REFUSE_WORDS) — отказ, «да» на карточку после него не пишет;
  (R3) Р3 и вытеснение: штатный рестарт (передача restart_handoff как в проде, новая граница жизни процесса) и
      вытеснение памяти пояснений потолком 40 — «да» на старое пояснение адресного вопроса не рождает, второе «да» не
      пишет; путь «да» без реплая → уточнение → «да» работает;
  (R2) Р2: пробег — роль и единицы против показания карточки (переспрос без вызова моста, подтверждение повтором того
      же числа), неуменьшение против Q строки — мостом при записи (подделка моста с живой сверкой Q closeBooking);
      «да 15» само по себе не ошибка.

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
                                                           "paid_total": None}])  # CLOSETRUTH1910: K не пишем

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


# ===================================================== (R) Р1 приёмки: не-согласие без реплая не становится согласием
# Приёмка 571a117 (accept/accept_approvefix.py, пробы X-bind-00…04): отказ / правка без реплая получали уточнение
# «Это ответ на карточку …?», ПРИВЯЗАННОЕ к карточке, и «да» на него исполняло activate/close. Формы проб перенесены
# дословно (r1), дальше — свои варианты: цепочка «да» на ответы бота, отказ реплаем, снятие привязки прежнего уточнения,
# две карточки, тег бота, флаг 1 (хранилище дела), бронь.
ACT_NOREPLY_NOT_CONSENT = ("нет", "не активируй", "стоп", "да, но поправь дату", "да?", "да, но сначала оплата",
                           "@turbobaby_manager_bot")
CLOSE_NOREPLY_NOT_CONSENT = ("нет", "не подтверждаю", "стоп", "да?", "да 35300", "да, но поправь пробег",
                             "@turbobaby_manager_bot")
X_BIND_PROBES = (("act", "нет"), ("act", "не активируй"), ("act", "да, но поправь дату"), ("close", "нет"),
                 ("close", "не подтверждаю"))                   # дословно accept_approvefix.X_CASES
REFUSALS_ACT = ("нет", "не активируй", "стоп")
REFUSALS_CLOSE = ("нет", "не подтверждаю", "стоп")


def _exp_act():
    return [{"bike": BIKE_A, "name": "Анна Тест", "date_start": dt(0, "09:00")}]


def _exp_close(km):
    # CLOSETRUTH1910 (CLOSE_TRUTH ВКЛ по умолчанию): итог листа закрытия в K «оплачено» не пишется
    return [{"bike": BIKE_A, "name": "Иван Тест", "date_start": dt(-3), "km_end": km, "paid_total": None}]


def _writes(b):
    return [n for n, _k in b.calls if n in ("activate_booking", "close_booking", "create_booking")]


class R_NoReplyRefusalNeverConsent(Case):
    def _card(self, kind):
        if kind == "act":
            b = Bridge([bk_row()])
            return b, ho_card(b), S._HANDOVER_ACTIVATIONS
        b = Bridge([rent_row()])
        return b, ret_card(b), S._RETURN_CLOSES

    def test_r1_acceptance_probes_x_bind(self):
        """Пробы X-bind-00…04 приёмки: «<не-согласие>» БЕЗ реплая → ответ бота; «да» реплаем на этот ответ → 0
        изменяющих вызовов, карточка жива (не исполнена и не снята)."""
        for kind, text in X_BIND_PROBES:
            with self.subTest(kind=kind, text=text):
                reset()
                b, _card, store = self._card(kind)
                n0 = len(SENDS)
                say(b, text)
                asks = SENDS[n0:]
                self.assertTrue(asks, "на ответ без реплая бот молчит: %r" % text)
                self.assertFalse(any("Это ответ на карточку" in s.text for s in asks),
                                 "не-согласию задан вопрос, на который «да» = «да, адрес этот»: %r" % texts())
                say(b, "да", reply=asks[-1])
                self.assertEqual(_writes(b), [], "Р1: «%s» без реплая + «да» на уточнение → запись в CRM" % text)
                self.assertEqual(store[INTAKE]["status"], "awaiting")

    def test_r2_chain_of_yes_on_bot_replies_never_writes_then_card_reply_works(self):
        for kind, pool in (("act", ACT_NOREPLY_NOT_CONSENT), ("close", CLOSE_NOREPLY_NOT_CONSENT)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    reset()
                    b, card, store = self._card(kind)
                    n0 = len(SENDS)
                    say(b, text)
                    self.assertTrue(SENDS[n0:], "на ответ без реплая бот молчит: %r" % text)
                    for _ in range(3):                                   # «да» на каждый следующий ответ бота
                        say(b, "да", reply=SENDS[-1])
                    self.assertEqual(_writes(b), [], "«%s» без реплая → цепочка «да» дала запись" % text)
                    self.assertEqual(store[INTAKE]["status"], "awaiting", "карточку погасило не-согласие без реплая")
                    say(b, "да", reply=card)                             # канонический адрес — сама карточка
                    if kind == "act":
                        self.assertEqual(b.red("activate_booking"), _exp_act())
                    else:
                        self.assertEqual(b.red("close_booking"), _exp_close("35200"))

    def test_r3_close_number_without_reply_is_not_written_as_card_km(self):
        """«да 35300» без реплая прежде шло в привязанное уточнение, и «да» на него закрывало с km_end карточки 35200 —
        не тем числом, что назвал человек."""
        b, card, _store = self._card("close")
        n0 = len(SENDS)
        say(b, "да 35300")
        say(b, "да", reply=SENDS[n0:][-1])
        self.assertEqual(b.red("close_booking"), [])
        say(b, "да 35300", reply=card)
        self.assertEqual(b.red("close_booking"), _exp_close("35300"))

    def test_r4_refusal_with_reply_then_yes_never_writes(self):
        for kind, pool in (("act", REFUSALS_ACT), ("close", REFUSALS_CLOSE)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    reset()
                    b, card, store = self._card(kind)
                    say(b, text, reply=card)
                    self.assertEqual(store[INTAKE]["status"], "rejected", "отказ реплаем на карточку снимает её")
                    say(b, "да", reply=SENDS[-1])                        # «да» на «❌ … отменил»
                    say(b, "да", reply=card)                             # «да» на снятую карточку
                    say(b, "да")                                         # «да» без реплая
                    self.assertEqual(_writes(b), [], "отказ реплаем + «да» → запись: %r" % text)

    def test_r5_later_not_consent_unbinds_earlier_ask(self):
        """Уточнение уже привязано (на «да» без реплая — `_CR_BIND`, на «да?» реплаем — `_CR_ASK`); затем отказ без
        реплая — «да» реплаем на СТАРОЕ уточнение больше не исполняет; реплай на саму карточку — исполняет."""
        for kind, first, first_reply in (("act", "да", False), ("act", "да?", True), ("close", "да", False),
                                         ("close", "да?", True)):
            with self.subTest(kind=kind, first=first):
                reset()
                b, card, store = self._card(kind)
                n0 = len(SENDS)
                say(b, first, reply=card if first_reply else None)
                old_ask = SENDS[n0:][-1]
                self.assertIn(old_ask.message_id, store[INTAKE]["msg_ids"], "уточнение не привязано: %r" % texts())
                say(b, "нет")                                            # передумал — без реплая
                self.assertNotIn(old_ask.message_id, store[INTAKE]["msg_ids"], "привязка старого уточнения не снята")
                say(b, "да", reply=old_ask)
                self.assertEqual(_writes(b), [], "«да» реплаем на старое уточнение после «нет» исполнило карточку")
                self.assertEqual(store[INTAKE]["status"], "awaiting")
                say(b, "да", reply=card)
                self.assertEqual(len(_writes(b)), 1, "реплай на саму карточку — ответ ей")

    def test_r6_positive_yes_without_reply_bind_ask_still_counts(self):
        b, _card, _store = self._card("act")
        say(b, "да")
        asks = [s for s in SENDS if "засчитываю только реплаем" in s.text]
        self.assertEqual(len(asks), 1, texts())
        say(b, "да", reply=asks[0])
        self.assertEqual(b.red("activate_booking"), _exp_act())
        reset()
        b, _card, _store = self._card("close")
        say(b, "да")
        asks = [s for s in SENDS if "засчитываю только реплаем" in s.text]
        self.assertEqual(len(asks), 1, texts())
        say(b, "да 35300", reply=asks[0])
        self.assertEqual(b.red("close_booking"), _exp_close("35300"))

    def test_r7_two_cards_refusal_without_reply_then_yes_chain_never_activates(self):
        b = Bridge([rent_row(), bk_row_b()])
        close_card = ret_card(b, BIKE_A)
        act_card = ho_card(b, BIKE_B)
        say(b, "нет")
        multi = [s for s in SENDS if "несколько карточек" in s.text]
        self.assertEqual(len(multi), 1, texts())
        say(b, "да 35300", reply=close_card)                            # приём закрыт реплаем на свою карточку
        self.assertEqual(len(b.red("close_booking")), 1)
        say(b, "да", reply=multi[0])                                     # осталась одна выдача
        say(b, "да", reply=SENDS[-1])
        self.assertEqual(b.red("activate_booking"), [], "«нет» без реплая при двух карточках → цепочка «да» → выдача")
        self.assertEqual(S._HANDOVER_ACTIVATIONS[INTAKE]["status"], "awaiting")
        say(b, "да", reply=act_card)
        self.assertEqual([c["bike"] for c in b.red("activate_booking")], [BIKE_B])

    def test_r8_note_wording_and_reply_guards(self):
        b, _card, store = self._card("act")
        n0 = len(SENDS)
        say(b, "нет")
        note = SENDS[n0:][-1]
        self.assertIn("строка 17", note.text)
        self.assertNotIn("Анна", note.text, "в пояснении нет имени клиента (ПДн)")
        self.assertNotIn("?", note.text, "пояснение — не вопрос: «да» на него нечему подтверждать")
        n1 = len(SENDS)
        say(b, "да", reply=note, uname="pym_thai")                     # не одобряющий
        say(b, "да", reply=note, forward=True)                           # пересланное
        self.assertEqual(len(SENDS), n1, "реплай не одобряющего / пересланный — молчание")
        say(b, "нет", reply=note)                                        # «нет» на пояснение карточку не снимает
        self.assertEqual(store[INTAKE]["status"], "awaiting")
        self.assertEqual(_writes(b), [])

    def test_r9_booking_alone_one_yes_after_not_consent_without_reply_zero_create(self):
        bk_card = types.SimpleNamespace(message_id=4100, from_user=U("dasha_mgr"), forum_topic_created=None)
        for text in ("нет", "да?", "да, но поправь дату", "не ставь"):
            with self.subTest(text=text):
                reset()
                b = Bridge([])
                S._INTAKE_DRAFTS[INTAKE] = booking_draft(bk_card.message_id)
                n0 = len(SENDS)
                say(b, text)
                self.assertTrue(SENDS[n0:], texts())
                say(b, "да", reply=SENDS[-1])
                self.assertEqual(b.red("create_booking"), [], "бронь: «%s» без реплая + «да» → create" % text)


class R_K4_NoReplyRefusalNeverConsent(Case):
    """Флаг RENTAL_CASE_APPROVALS=1: путь хранилища дела (`_rc_intake_reply`) — те же формы, 0 записей. Настройка — как
    у (E) (своя временная база дела на каждый прогон), без наследования: тесты (E) не должны гоняться дважды."""

    def setUp(self):
        super(R_K4_NoReplyRefusalNeverConsent, self).setUp()
        os.environ["RENTAL_CASE_APPROVALS"] = "1"
        import rental_case
        d = tempfile.mkdtemp(prefix="approvefix_k4r_%s_" % self._testMethodName[5:20], dir=TTMP)
        p = os.path.join(d, "rental_case.sqlite")
        rental_case.Store.create(p)
        os.environ["RENTAL_CASE_DB"] = p

    def k4(self, b, text, reply):
        return say(b, text, reply=reply, uname=OWNER, uid=OWNER_ID)

    def _card(self, kind):
        if kind == "act":
            b = Bridge([bk_row()])
            return b, ho_card(b)
        b = Bridge([rent_row()])
        return b, ret_card(b)

    def test_r10_k4_refusal_without_reply_then_yes_on_bot_zero_then_card_reply_works(self):
        for kind, pool in (("act", REFUSALS_ACT + ("да, но поправь дату", "да?")),
                           ("close", REFUSALS_CLOSE + ("да?", "да 35300"))):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    self.setUp()
                    b, card = self._card(kind)
                    n0 = len(SENDS)
                    self.k4(b, text, None)
                    for s in list(SENDS[n0:]):
                        self.k4(b, "да", s)
                    self.k4(b, "да", None)
                    self.assertEqual(_writes(b), [], "К4: «%s» без реплая + «да» → запись" % text)
                    self.k4(b, "да", card)
                    self.assertEqual(len(_writes(b)), 1, "К4: реплай на саму карточку — ответ ей")

    def test_r11_k4_refusal_with_reply_then_yes_on_bot_zero(self):
        """Отказ реплаем на карточку, затем «да» на ответы бота и «да» без реплая — 0 записей. «да» реплаем на САМУ
        карточку после отказа словарём К4 («нет», «не активируй», «не подтверждаю») — тоже 0: ожидание закрыто.
        «стоп» словарь К4 до остатка 2 отказом не знал (APPROVAL_NO_STEMS) — ответ «неоднозначный», карточка жила; здесь
        это не судится (исключение ниже — след той поры), отказ «стоп» судит раздел (RW)."""
        for kind, pool in (("act", REFUSALS_ACT), ("close", REFUSALS_CLOSE)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    self.setUp()
                    b, card = self._card(kind)
                    n0 = len(SENDS)
                    self.k4(b, text, card)
                    for s in list(SENDS[n0:]):
                        self.k4(b, "да", s)
                    self.k4(b, "да", None)
                    self.assertEqual(_writes(b), [], "К4: отказ реплаем + «да» на уточнение → запись: %r" % text)
                    if text != "стоп":
                        self.k4(b, "да", card)
                        self.assertEqual(_writes(b), [], "К4: отказ реплаем + «да» на карточку → запись: %r" % text)

    def test_r12_k4_other_action_consent_without_reply_zero(self):
        """Страж (зелёный и до Р1-К): флаг 1, те же 9 форм X приёмки без реплая → «да» на ответы бота и без реплая →
        0 записей; реплай «да» на саму карточку — ровно одна."""
        for kind, pool in (("act", X_OTHER_ACT), ("close", X_OTHER_CLOSE)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    self.setUp()
                    b, card = self._card(kind)
                    n0 = len(SENDS)
                    self.k4(b, text, None)
                    for s in list(SENDS[n0:]):
                        self.k4(b, "да", s)
                    self.k4(b, "да", None)
                    self.assertEqual(_writes(b), [], "К4: «%s» без реплая + «да» → запись" % text)
                    self.k4(b, "да", card)
                    self.assertEqual(len(_writes(b)), 1, "К4: реплай на саму карточку — ответ ей")


# =========================================== (RK) Р1-К: согласие ДРУГОГО действия без реплая при одной ждущей карточке
# Повторная приёмка e34e086 (accept_r2/accept_r2_new.py, пробы X-f0-act-00…04 и X-f0-close-00…03): согласие решалось
# объединением слов выдачи и приёма, а вопрос «Это ответ на карточку …?» привязывался к единственной ждущей карточке без
# сверки ДЕЙСТВИЯ — «активируй» при ждущем только приёме → вопрос про приём → «да» → close_booking (и наоборот).
X_OTHER_ACT = ("закрывай", "завершай", "заверши", "да, закрывай", "закрываем")      # ждёт ТОЛЬКО выдача (дословно X)
X_OTHER_CLOSE = ("активируй", "активируем", "да, активируй", "активируйте")         # ждёт ТОЛЬКО приём (дословно X)
OWN_ACT = ("активируй", "активируем", "активируйте", "да, активируй")               # зеркало: своё действие — выдача
OWN_CLOSE = ("закрывай", "завершай", "заверши", "да, закрывай", "закрываем")        # зеркало: своё действие — приём


class RK_OtherActionConsentNoReply(Case):
    def _card(self, kind):
        if kind == "act":
            b = Bridge([bk_row()])
            return b, ho_card(b), S._HANDOVER_ACTIVATIONS
        b = Bridge([rent_row()])
        return b, ret_card(b), S._RETURN_CLOSES

    def test_rk1_acceptance_x_nine_forms_note_unbound_zero_calls(self):
        """Пробы X приёмки дословно: «<согласие чужого действия>» без реплая → пояснение (не вопрос, без привязки) →
        «да» реплаем на ответ бота ×2 → 0 изменяющих вызовов, карточка жива; реплай «да» на саму карточку — ровно один
        вызов её действия."""
        for kind, pool in (("act", X_OTHER_ACT), ("close", X_OTHER_CLOSE)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    reset()
                    b, card, store = self._card(kind)
                    ids0 = list(store[INTAKE].get("msg_ids") or [])
                    n0 = len(SENDS)
                    say(b, text)
                    out = SENDS[n0:]
                    self.assertEqual(len(out), 1, "на ответ без реплая — ровно одно сообщение: %r" % texts())
                    self.assertNotIn("Это ответ на карточку", out[0].text, "чужому действию задан адресный вопрос")
                    self.assertIn("Ответ без реплая на карточку %s" % ("выдачи" if kind == "act" else "приёма"),
                                  out[0].text, "пояснение называет ждущую карточку")
                    self.assertEqual(list(store[INTAKE].get("msg_ids") or []), ids0, "пояснение привязано к карточке")
                    self.assertEqual(list(store[INTAKE].get("ask_ids") or []), [])
                    for _ in range(2):
                        say(b, "да", reply=SENDS[-1])
                    self.assertEqual(_writes(b), [], "Р1-К: «%s» без реплая + «да» на ответ бота → запись" % text)
                    self.assertEqual(store[INTAKE]["status"], "awaiting")
                    say(b, "да", reply=card)
                    if kind == "act":
                        self.assertEqual(b.red("activate_booking"), _exp_act())
                        self.assertEqual(b.red("close_booking"), [])
                    else:
                        self.assertEqual(b.red("close_booking"), _exp_close("35200"))
                        self.assertEqual(b.red("activate_booking"), [])

    def test_rk2_mirror_own_action_without_reply_still_binds(self):
        """Зеркало: согласие СВОЕГО действия без реплая — прежний адресный вопрос, привязанный к карточке; «да» на него
        — ровно один вызов её действия (для приёма — пробег поля карточки)."""
        for kind, pool in (("act", OWN_ACT), ("close", OWN_CLOSE)):
            for text in pool:
                with self.subTest(kind=kind, text=text):
                    reset()
                    b, _card, store = self._card(kind)
                    n0 = len(SENDS)
                    say(b, text)
                    asks = [s for s in SENDS[n0:] if "Это ответ на карточку" in s.text]
                    self.assertEqual(len(asks), 1, texts())
                    self.assertIn(asks[0].message_id, store[INTAKE]["msg_ids"], "уточнение не привязано")
                    self.assertEqual(_writes(b), [], "без реплая ничего не исполняется")
                    say(b, "да", reply=asks[0])
                    if kind == "act":
                        self.assertEqual(b.red("activate_booking"), _exp_act())
                    else:
                        self.assertEqual(b.red("close_booking"), _exp_close("35200"))
                    self.assertEqual(len(_writes(b)), 1)

    def test_rk3_other_action_word_unbinds_earlier_ask(self):
        """Как прочие не-согласия (r5): уточнение привязано на «да» без реплая; затем согласие ЧУЖОГО действия без
        реплая — привязка снята, «да» на старое уточнение не исполняет; реплай на саму карточку — исполняет."""
        for kind, other in (("act", "закрывай"), ("act", "да, закрывай"), ("close", "активируй"),
                            ("close", "да, активируй")):
            with self.subTest(kind=kind, other=other):
                reset()
                b, card, store = self._card(kind)
                n0 = len(SENDS)
                say(b, "да")
                old_ask = SENDS[n0:][-1]
                self.assertIn(old_ask.message_id, store[INTAKE]["msg_ids"], texts())
                say(b, other)
                self.assertNotIn(old_ask.message_id, store[INTAKE]["msg_ids"], "привязка старого уточнения не снята")
                say(b, "да", reply=old_ask)
                self.assertEqual(_writes(b), [], "«да» на старое уточнение после чужого глагола исполнило карточку")
                say(b, "да", reply=card)
                self.assertEqual(len(_writes(b)), 1)

    def test_rk4_two_cards_answer_unchanged(self):
        """Ждут две карточки (приём A, выдача B): глагол любого действия без реплая — прежний ответ «ждут несколько»,
        ни одного вызова; «да» на этот ответ — тоже ни одного."""
        for text in ("закрывай", "активируй", "да, закрывай", "да, активируй"):
            with self.subTest(text=text):
                reset()
                b = Bridge([rent_row(), bk_row_b()])
                ret_card(b, BIKE_A)
                ho_card(b, BIKE_B)
                n0 = len(SENDS)
                say(b, text)
                out = SENDS[n0:]
                self.assertEqual(len(out), 1, texts())
                self.assertIn("Ждут ответа несколько карточек", out[0].text)
                say(b, "да", reply=out[0])
                say(b, "да", reply=SENDS[-1])
                self.assertEqual(_writes(b), [])

    def test_rk5_pure_action_words(self):
        """Чистая часть, на которой стоит правка: слово чужого действия согласием этой карточки не является."""
        import intake_confirm as IC
        for text in X_OTHER_ACT:
            with self.subTest(action="activate", text=text):
                self.assertNotEqual(IC.decide_action(text, "activate"), IC.YES)
        for text in X_OTHER_CLOSE:
            with self.subTest(action="close", text=text):
                self.assertNotEqual(IC.decide_action(IC.km_arg(text)[1], "close"), IC.YES)
        for text in OWN_ACT:
            with self.subTest(action="activate", own=text):
                self.assertEqual(IC.decide_action(text, "activate"), IC.YES)
        for text in OWN_CLOSE:
            with self.subTest(action="close", own=text):
                self.assertEqual(IC.decide_action(text, "close"), IC.YES)


# ===================================== остатки приёмки 8bfcfa3: общие подделки (память маршрута, рестарт, мост с Q)
_MEM = ("_CR_NOTES", "_CR_FORGOT", "_IC_DEAD_ASKS")          # память маршрута; на 8bfcfa3 двух последних имён нет


def _mem_clear():
    for name in _MEM:
        getattr(S, name, {}).clear()


def restart_process():
    """Штатный рестарт Splinter, как в проде: post_stop пишет передачу (`handoff_write`), память процесса пропадает
    целиком (карточки, пояснения, привязки, вытеснение), новая жизнь процесса начинается позже всего, что бот уже
    написал (`_CR_LIFE_T0`; на 8bfcfa3 имени нет — присваивание ни на что не влияет), post_init поднимает передачу
    (`handoff_restore`) — переходят только поля белого списка restart_handoff."""
    S.handoff_write()
    for d in (S._INTAKE_DRAFTS, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES):
        d.clear()
    _mem_clear()
    S._HANDOFF_SEEN.update(applied_sha=None, unapplied=False, carry=[])
    time.sleep(0.05)                                         # всё написанное до рестарта — строго раньше границы
    S._CR_LIFE_T0 = time.time()
    out = S.handoff_restore()
    assert out.startswith("применена"), out


def bot_msg(text):
    """Сообщение бота этой жизни процесса, не входящее ни в одну карточку (например, исход другой карточки)."""
    _MID[0] += 1
    s = Sent(_MID[0], INTAKE, text)
    SENDS.append(s)
    return s


def other_human_msg(text="коллега: клиент перезвонит"):
    return types.SimpleNamespace(message_id=4200, from_user=U("dasha_mgr"), forum_topic_created=None, text=text,
                                 date=datetime.datetime.now(datetime.timezone.utc))


BK_CARD_MID = 4100


def bk_card_msg():
    return types.SimpleNamespace(message_id=BK_CARD_MID, from_user=U("dasha_mgr"), forum_topic_created=None)


class MemCase(Case):
    def setUp(self):
        super(MemCase, self).setUp()
        _mem_clear()
        self._t0 = getattr(S, "_CR_LIFE_T0", None)

    def tearDown(self):
        _mem_clear()
        if self._t0 is not None:
            S._CR_LIFE_T0 = self._t0
        super(MemCase, self).tearDown()


# ================================================ (RB) остаток 1: бронь — «да?» без реплая не дорастает до записи
BOOK_NOT_CONSENT_NOREPLY = ("да?", "ок?", "@turbobaby_manager_bot", "🤔", "да 35200")


class RB_BookingNotConsentChain(MemCase):
    def _book(self):
        b = Bridge([])
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(BK_CARD_MID)
        return b

    def test_rb1_not_consent_without_reply_then_yes_chain_zero_create_card_reply_books(self):
        """Остаток 1 дословно: «да?» без реплая → «да» на ответ бота → «да» на уточнение → … — 0 create_booking;
        реплай «да» на саму карточку брони — ровно один."""
        for text in BOOK_NOT_CONSENT_NOREPLY:
            with self.subTest(text=text):
                reset()
                _mem_clear()
                b = self._book()
                n0 = len(SENDS)
                say(b, text)
                self.assertTrue(SENDS[n0:], "на ответ без реплая бот молчит: %r" % text)
                for _ in range(3):
                    say(b, "да", reply=SENDS[-1])
                self.assertEqual(b.red("create_booking"), [], "бронь: «%s» без реплая + «да»×3 на ответы бота → "
                                                             "create_booking" % text)
                self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval")
                say(b, "да", reply=bk_card_msg())
                self.assertEqual(len(b.red("create_booking")), 1, "реплай на карточку брони — ответ ей")

    def test_rb2_refusal_reply_on_other_human_then_yes_chain_zero_create(self):
        """«нет» реплаем на чужое сообщение → переспрос «ответ на другое сообщение» → «да» на него → «да» на
        уточнение — 0 create_booking (тот же класс, другой адрес не-согласия)."""
        for text in ("нет", "правки потом", "да?"):
            with self.subTest(text=text):
                reset()
                _mem_clear()
                b = self._book()
                say(b, text, reply=other_human_msg())
                for _ in range(2):
                    say(b, "да", reply=SENDS[-1])
                self.assertEqual(b.red("create_booking"), [], "«%s» реплаем на чужое + «да»×2 → create" % text)

    def test_rb3_mirror_yes_without_reply_bind_then_reply_books(self):
        """Зеркало (зелёное и на 8bfcfa3): согласие без реплая — уточнение С привязкой, «да» на него — запись."""
        b = self._book()
        say(b, "да")
        ask = SENDS[-1]
        self.assertIn(ask.message_id, S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"], texts())
        say(b, "да", reply=ask)
        self.assertEqual(len(b.red("create_booking")), 1)

    def test_rb4_mirror_reply_on_bot_message_of_this_life_still_binds(self):
        """Зеркало (Codex 0307, «старое сообщение этого бота»): «да» реплаем на сообщение бота ЭТОЙ жизни процесса, не
        бывшее переспросом к не-согласию, — прежнее уточнение с привязкой; «да» на него — запись."""
        b = self._book()
        other = bot_msg(P + "✅ В аренде, строка 7.")
        say(b, "да", reply=other)
        ask = SENDS[-1]
        self.assertIn(ask.message_id, S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"], "уточнение не привязано: %r" % texts())
        say(b, "да", reply=ask)
        self.assertEqual(len(b.red("create_booking")), 1)

    def test_rb5_mute_ask_names_card_but_is_not_bound(self):
        """Ответ на «да» реплаем на переспрос к «да?» — то же адресное уточнение (называет карточку, ПДн нет), но его
        id в сообщения карточки не попадает: реплай на него ничего не ставит."""
        b = self._book()
        say(b, "да?")
        say(b, "да", reply=SENDS[-1])
        mute = SENDS[-1]
        d = S._INTAKE_DRAFTS[INTAKE]
        self.assertEqual(mute.text, P + S._IC_ASK_BIND.format(card=S._ic_card_name(d)))
        self.assertNotIn("Мария", mute.text)
        self.assertNotIn(mute.message_id, d["ic_msg_ids"], "уточнение к «немому» переспросу привязано к карточке")


# ===================================================== (RW) остаток 2: словарь отказов К4 не уже строгой ветки
K4_REFUSALS = ("стоп", "stop", "cancel", "нельзя", "неа", "Стоп!", "STOP", "no", "nope", "отмени")


class RW_K4RefusalWords(Case):
    def setUp(self):
        super(RW_K4RefusalWords, self).setUp()
        os.environ["RENTAL_CASE_APPROVALS"] = "1"
        import rental_case
        d = tempfile.mkdtemp(prefix="approvefix_k4w_%s_" % self._testMethodName[5:20], dir=TTMP)
        p = os.path.join(d, "rental_case.sqlite")
        rental_case.Store.create(p)
        os.environ["RENTAL_CASE_DB"] = p

    def k4(self, b, text, reply):
        return say(b, text, reply=reply, uname=OWNER, uid=OWNER_ID)

    def test_rw1_pure_refusal_words_are_no_for_every_action(self):
        import intake_confirm as IC
        import rental_case_rules as R
        pd = R.PARAMS_DEFAULT
        words = sorted(set(K4_REFUSALS) | set(IC.REFUSE_WORDS))
        for action in (None, "activate", "close", "booking"):
            for w in words:
                with self.subTest(action=action, word=w):
                    self.assertEqual(R.approval_decision(w, pd, action=action), "no",
                                     "К4: «%s» — отказ строгой ветки, а словарь К4 его не знает" % w)

    def test_rw2_guards_not_refusal(self):
        """Границы: слово отказа — ЦЕЛИКОМ; соседние слова отказом не становятся, согласие — прежнее."""
        import rental_case_rules as R
        pd = R.PARAMS_DEFAULT
        for text, want in (("да", "yes"), ("ок", "yes"), ("да 35200", "unclear"), ("стопка", "unclear"),
                           ("неактивна", "unclear"), ("nobody", "unclear"), ("nothing", "unclear")):
            with self.subTest(text=text):
                self.assertEqual(R.approval_decision(text, pd, action="activate"), want)
        self.assertEqual(R.approval_decision("да 35200", pd, action="close"), "yes")

    def test_rw3_k4_refusal_reply_on_card_closes_card_then_yes_zero_writes(self):
        """Флаг 1, реплай «<слово отказа>» на карточку выдачи/приёма → «❌ … отменил»; «да» реплаем на ту же карточку
        и на ответы бота — 0 записей (прежде: «неоднозначный», карточка ждала, «да» на неё писало)."""
        for kind in ("act", "close"):
            for w in ("стоп", "stop", "cancel", "нельзя", "неа"):
                with self.subTest(kind=kind, word=w):
                    self.setUp()
                    if kind == "act":
                        b = Bridge([bk_row()])
                        card = ho_card(b)
                    else:
                        b = Bridge([rent_row()])
                        card = ret_card(b)
                    n0 = len(SENDS)
                    self.k4(b, w, card)
                    said = [s.text for s in SENDS[n0:]]
                    self.assertTrue(any("отменил" in t for t in said), "К4: «%s» не отказ: %r" % (w, said))
                    for s in list(SENDS[n0:]):
                        self.k4(b, "да", s)
                    self.k4(b, "да", card)
                    self.assertEqual(_writes(b), [], "К4: «%s» реплаем на карточку + «да» → запись" % w)


# ============================================================ (R3) Р3: рестарт и вытеснение памяти пояснений
class R3_RestartAndEviction(MemCase):
    def _card(self, kind):
        if kind == "act":
            b = Bridge([bk_row()])
            return b, ho_card(b), S._HANDOVER_ACTIVATIONS
        b = Bridge([rent_row()])
        return b, ret_card(b), S._RETURN_CLOSES

    def _exp(self, kind):
        return _exp_act() if kind == "act" else _exp_close("35200")

    def test_r3a_restart_yes_on_old_note_never_writes_then_noreply_path_works(self):
        """Р3 дословно: «нет» без реплая → пояснение N → штатный рестарт → «да» реплаем на N → «да» на ответ бота →
        0 записей; карточка пережила рестарт и ждёт; «да» без реплая → уточнение этой жизни → «да» на него — запись."""
        for kind in ("act", "close"):
            with self.subTest(kind=kind):
                reset()
                _mem_clear()
                b, _card, store = self._card(kind)
                say(b, "нет")
                note = SENDS[-1]
                restart_process()
                self.assertEqual(store[INTAKE]["status"], "awaiting", "карточка не пережила рестарт")
                n0 = len(SENDS)
                say(b, "да", reply=note)
                out = [s.text for s in SENDS[n0:]]
                self.assertFalse(any("Это ответ на карточку" in t for t in out),
                                 "«да» на старое пояснение родило адресный вопрос: %r" % out)
                for _ in range(2):
                    say(b, "да", reply=SENDS[-1])
                self.assertEqual(_writes(b), [], "Р3: «да» на пояснение до рестарта → запись")
                self.assertEqual(store[INTAKE]["status"], "awaiting")
                say(b, "да")
                ask = SENDS[-1]
                self.assertIn("Это ответ на карточку", ask.text, texts())
                say(b, "да", reply=ask)
                self.assertEqual(b.red("activate_booking" if kind == "act" else "close_booking"), self._exp(kind))

    def test_r3b_restart_reply_on_card_itself_does_not_write_through_chain(self):
        """После рестарта id карточки не переходят (restart_handoff не тронут): реплай «да» на неё — сообщение
        неизвестного происхождения: ни записи, ни адресного вопроса, и «да» на ответ бота тоже не пишет."""
        for kind in ("act", "close"):
            with self.subTest(kind=kind):
                reset()
                _mem_clear()
                b, card, store = self._card(kind)
                restart_process()
                say(b, "да", reply=card)
                say(b, "да", reply=SENDS[-1])
                self.assertEqual(_writes(b), [], "после рестарта «да» на карточку + «да» на ответ бота → запись")
                self.assertEqual(store[INTAKE]["status"], "awaiting")

    def test_r3c_eviction_yes_on_evicted_note_never_writes(self):
        """Вытеснение: «нет» без реплая → пояснение N1 → 41 «да» на «немые» ответы (N1 выпадает из потолка 40) → «да»
        реплаем на N1 → «да» на ответ бота — 0 записей; реплай на саму карточку — запись."""
        for kind in ("act", "close"):
            with self.subTest(kind=kind):
                reset()
                _mem_clear()
                b, card, store = self._card(kind)
                say(b, "нет")
                n1 = SENDS[-1]
                for _ in range(41):
                    say(b, "да", reply=SENDS[-1])
                self.assertNotIn(n1.message_id, S._CR_NOTES.get(INTAKE) or [], "N1 не вытеснен — проба не та")
                self.assertEqual(_writes(b), [])
                n0 = len(SENDS)
                say(b, "да", reply=n1)
                self.assertFalse(any("Это ответ на карточку" in s.text for s in SENDS[n0:]), texts()[-2:])
                say(b, "да", reply=SENDS[-1])
                self.assertEqual(_writes(b), [], "«да» на вытесненное пояснение → запись")
                say(b, "да", reply=card)
                self.assertEqual(len(_writes(b)), 1)

    def test_r3d_booking_restart_chain_zero_create_card_reply_books(self):
        """Бронь: «да?» без реплая → переспрос → штатный рестарт (черновик и id карточки переходят) → «да» на
        переспрос → «да» на ответ бота — 0 create_booking; реплай на карточку брони — запись."""
        b = Bridge([])
        S._INTAKE_DRAFTS[INTAKE] = booking_draft(BK_CARD_MID)
        say(b, "да?")
        ask = SENDS[-1]
        restart_process()
        self.assertEqual(S._INTAKE_DRAFTS[INTAKE]["status"], "awaiting_approval")
        say(b, "да", reply=ask)
        say(b, "да", reply=SENDS[-1])
        self.assertEqual(b.red("create_booking"), [], "бронь: «да» на переспрос до рестарта → create")
        say(b, "да", reply=bk_card_msg())
        self.assertEqual(len(b.red("create_booking")), 1)

    def test_r3e_mirror_bot_message_of_this_life_still_binds(self):
        """Зеркало (зелёное и на 8bfcfa3): реплай «да» на сообщение бота ЭТОЙ жизни, не пояснение и не вытесненное, —
        прежний адресный вопрос с привязкой; «да» на него — ровно одна запись."""
        for kind in ("act", "close"):
            with self.subTest(kind=kind):
                reset()
                _mem_clear()
                b, _card, store = self._card(kind)
                other = bot_msg(P + "✅ В аренде, строка 7.")
                say(b, "да", reply=other)
                ask = SENDS[-1]
                self.assertIn("Это ответ на карточку", ask.text, texts())
                self.assertIn(ask.message_id, store[INTAKE]["msg_ids"])
                say(b, "да", reply=ask)
                self.assertEqual(len(_writes(b)), 1)

    def test_r3f_pure_origin_truth_table(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        old = now - datetime.timedelta(hours=1)

        def m(reply):
            return types.SimpleNamespace(chat_id=INTAKE, reply_to_message=reply)

        S._CR_LIFE_T0 = time.time() - 60
        S._CR_FORGOT[INTAKE] = 920500

        class Boom(object):
            @property
            def message_id(self):
                raise RuntimeError("не читается")

        cases = ((None, False, "реплая нет"),
                 (types.SimpleNamespace(message_id=1, from_user=U("x"), date=old), False, "сообщение человека"),
                 (types.SimpleNamespace(message_id=999999, from_user=BotUser(), date=now), False, "бот, эта жизнь"),
                 (types.SimpleNamespace(message_id=999999, from_user=BotUser(), date=old), True, "бот, до рестарта"),
                 (types.SimpleNamespace(message_id=999999, from_user=BotUser()), True, "бот, даты нет"),
                 (types.SimpleNamespace(message_id=920400, from_user=BotUser(), date=now), True, "не новее вытесн."),
                 (types.SimpleNamespace(message_id=None, from_user=BotUser(), date=now), True, "id нет"),
                 (types.SimpleNamespace(message_id=999999, date=now, forum_topic_created=object()), False, "тема"),
                 (Boom(), True, "разбор упал"))
        for reply, want, ctx in cases:
            with self.subTest(case=ctx):
                self.assertEqual(S._cr_origin_unknown(m(reply)), want, ctx)


# ============================================== (R2) Р2: пробег — роль, единицы, текущий Q, неуменьшение при записи
_Q_RE = __import__("re").compile(r"^(\d+)\s*(?:[KkКк][MmМм][\s\S]*)?$")


class QBridge(Bridge):
    """Мост с ЖИВОЙ сверкой одометра closeBooking — порядок проверок bridge_prod/Booking.js:378-470: строка «В аренде»
    по байку и клиенту (not_active) · km_end обязателен (km_required) · число (bad_km_end) · Q строки живым форматом
    «<число> Km, <дата>» (bookingParseOdo_; не разобран → odo_unverifiable) · km_end < Q → odometer_back · иначе
    A=Завершена, N=km_end. `n` — что записано в N."""

    def __init__(self, rows, q):
        Bridge.__init__(self, rows)
        self.q = dict(q)
        self.n = {}

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        r = self._find(bike, name, "В аренде")
        if r is None:
            return {"ok": False, "error": "not_active", "message": "нет активной"}
        if km_end in (None, ""):
            return {"ok": False, "error": "km_required", "row": r["row"], "message": "km_end обязателен"}
        try:
            km = float(km_end)
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_km_end", "message": "km_end не число: %s" % km_end}
        raw = self.q.get(r["row"], "")
        mm = _Q_RE.match(str(raw).strip()) if raw not in ("", None) else None
        odo = float(mm.group(1)) if mm else None
        if odo is None:
            return {"ok": False, "error": "odo_unverifiable", "row": r["row"], "odo_raw": str(raw), "km_end": km,
                    "message": "одометр строки пуст/нечитаем"}
        if km < odo:
            return {"ok": False, "error": "odometer_back", "row": r["row"], "odo": odo, "km_end": km,
                    "message": "km_end (%s) меньше текущего пробега строки (Q=%s)" % (km_end, odo)}
        r["status"] = "Завершена"
        self.n[r["row"]] = km_end
        return {"ok": True, "closed": True, "row": r["row"], "bike": bike, "name": name, "km_end": km}


Q_LIVE = "35200 Km, 05.10.2026"


class R2_MileageRoleUnitsQ(MemCase):
    def _b(self, q=Q_LIVE):
        return QBridge([rent_row()], {21: q})

    def test_r2a_short_number_against_card_reading_asks_without_call_then_full_number_closes(self):
        """«да 15» реплаем на карточку с показанием 35200 — моста не зовём (ни билета, ни вызова), карточка жива,
        переспрос называет оба числа; «да» на переспрос — ничего; «да 35300» на карточку — запись N=35300."""
        b = self._b()
        card = ret_card(b, km="35200")
        say(b, "да 15", reply=card)
        self.assertEqual(b.red("close_booking"), [], "«да 15» при показании 35200 ушло в мост")
        self.assertEqual(b.tickets, 0)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting")
        self.assertIn("«15»", texts()[-1])
        self.assertIn("35200", texts()[-1])
        say(b, "да", reply=SENDS[-1])
        self.assertEqual(b.red("close_booking"), [])
        say(b, "да 35300", reply=card)
        self.assertEqual(b.n, {21: "35300"})

    def test_r2b_extra_digit_up_is_not_written_silently(self):
        """Единицы вверх: «да 352000» (лишний разряд) при показании 35200 — мост бы ПРИНЯЛ (не меньше Q); теперь
        моста не зовём. Повтор того же «да 352000» — подтверждение человека: вызов уходит, судит мост; другое
        полное число — закрывает им."""
        b = self._b()
        card = ret_card(b, km="35200")
        say(b, "да 352000", reply=card)
        self.assertEqual(b.red("close_booking"), [], "лишний разряд записался бы в N без вопроса")
        say(b, "да 35300", reply=card)
        self.assertEqual(b.n, {21: "35300"})
        reset()
        _mem_clear()
        b = self._b()
        card = ret_card(b, km="35200")
        say(b, "да 352000", reply=card)
        say(b, "да 352000", reply=card)
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], ["352000"], "повтор — подтверждение")

    def test_r2c_short_number_is_not_an_error_by_itself(self):
        """Codex: «да 15» само по себе не ошибка — без показания на карточке или при показании того же порядка число
        уходит в мост, и при Q не больше его закрытие записано."""
        for card_km, q in (("", "10 Km, 05.10.2026"), ("12", "10 Km, 05.10.2026"), ("", "10")):
            with self.subTest(card_km=card_km, q=q):
                reset()
                _mem_clear()
                b = self._b(q)
                card = ret_card(b, km=card_km)
                say(b, "да 15", reply=card)
                self.assertEqual(b.n, {21: "15"})

    def test_r2d_non_decrease_against_q_is_judged_at_write(self):
        """Неуменьшение и текущий Q — при записи (мост): без показания на карточке «да 15» уходит, мост против Q=35200
        отказывает до записи (odometer_back); Q не читается — odo_unverifiable; в N не легло ничего, «✅» нет."""
        for q, err in ((Q_LIVE, "odometer_back"), ("", "odo_unverifiable"), ("05.10.2026", "odo_unverifiable")):
            with self.subTest(q=q):
                reset()
                _mem_clear()
                b = self._b(q)
                card = ret_card(b, km="")
                say(b, "да 15", reply=card)
                self.assertEqual(len(b.red("close_booking")), 1)
                self.assertEqual(b.n, {}, "пробег меньше Q / без сверки записан в N")
                self.assertEqual(b.rows[0]["status"], "В аренде")
                self.assertFalse(any("✅ Завершена" in t for t in texts()), texts())
                self.assertTrue(any(err in t or "Закрыть не могу" in t for t in texts()), texts())

    def test_r2e_same_order_and_power_of_ten_crossing_close_without_question(self):
        for card_km, q, said, want in (("35200", Q_LIVE, "да 35300", "35300"),
                                       ("35200", Q_LIVE, "да 35 300", "35300"),
                                       ("99950", "99950 Km, 05.10.2026", "да 100020", "100020"),
                                       ("35200", Q_LIVE, "да", "35200")):
            with self.subTest(said=said, card_km=card_km):
                reset()
                _mem_clear()
                b = self._b(q)
                card = ret_card(b, km=card_km)
                say(b, said, reply=card)
                self.assertEqual(b.n, {21: want})

    def test_r2f_k4_short_number_asks_with_new_card_then_repeat_goes_to_bridge(self):
        """Флаг 1 (хранилище дела): то же правило. «да 15» на карточку с показанием 35200 → моста не зовём, новая
        карточка того же закрытия; «да 35300» на неё — запись; повтор «да 15» на неё — вызов, мост против Q
        отказывает (odometer_back), N не тронут."""
        import rental_case
        for second, want_n, want_calls in (("да 35300", {21: "35300"}, ["35300"]), ("да 15", {}, ["15"])):
            with self.subTest(second=second):
                reset()
                _mem_clear()
                os.environ["RENTAL_CASE_APPROVALS"] = "1"
                d = tempfile.mkdtemp(prefix="approvefix_k4q_", dir=TTMP)
                p = os.path.join(d, "rental_case.sqlite")
                rental_case.Store.create(p)
                os.environ["RENTAL_CASE_DB"] = p
                b = self._b()
                card = ret_card(b, km="35200")
                n_cards = len(cards("Завершаю"))
                say(b, "да 15", reply=card, uname=OWNER, uid=OWNER_ID)
                self.assertEqual(b.red("close_booking"), [], "К4: «да 15» при показании 35200 ушло в мост")
                self.assertTrue(any("«15»" in t for t in texts()), texts())
                again = cards("Завершаю")
                self.assertEqual(len(again), n_cards + 1, "К4: новой карточки того же закрытия нет: %r" % texts())
                say(b, second, reply=again[-1], uname=OWNER, uid=OWNER_ID)
                self.assertEqual([c["km_end"] for c in b.red("close_booking")], want_calls)
                self.assertEqual(b.n, want_n)

    def test_r2g_pure_km_doubt_three_outcomes(self):
        import intake_confirm as IC
        for km, ref, want in (("15", "35200", True), ("352000", "35200", True), ("3520", "35200", True),
                              ("35", "35200", True), ("35300", "35200", False), ("35100", "35200", False),
                              ("100020", "99950", False), ("15", "12", False), ("15", None, None), (None, "35200", None),
                              ("", "35200", None), ("15", "0", None), ("15", "—", None)):
            with self.subTest(km=km, ref=ref):
                self.assertIs(IC.km_doubt(km, ref), want)


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
