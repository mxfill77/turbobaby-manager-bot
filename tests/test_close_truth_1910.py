# -*- coding: utf-8 -*-
"""CLOSETRUTH1910 (19.10.2026): правда карточки приёма — ручка CLOSE_TRUTH (отрезок RETURN/CLOSE TRUTH карты цикла).

Дефект подтверждён по коду 947953e до правки: итог листа закрытия (total_due = сумма ДОПЛАТ, bridge_prod/Closing.js:4)
уходил в close_booking.paid_total и перезаписывал K «оплачено» (bridge_prod/Booking.js:466-467); пробег карточки —
слияние `parsed.mileage or vis.mileage`, и «да» без числа клал сырой OCR фото в N. Проверяется через НАСТОЯЩИЕ
обработчики Splinter (`_return_close_card` / `_handle_servicing` → `_handle_intake`) с мостом-подделкой во всех трёх
путях ответа: строгий (INTAKE_CONFIRM_STRICT по умолчанию), прежний (INTAKE_CONFIRM_STRICT=0), дело К4
(RENTAL_CASE_APPROVALS=1, временная база).

Разделы:
  (P)  чистые части: слова ручки, `_close_paid_arg`, `_close_km_photo_only`, `_close_card_parts`;
  (T)  ручка ВКЛ, строгий путь: доплата — только текстом «к доплате … — в CRM не пишу», paid_total=None во всех
       вызовах; пробег с фото — подсказка, «да» без числа — ни билета, ни вызова, карточка жива; «да <пробег>» —
       один вызов с этим числом; Р2 сверяет число ответа с фото-подсказкой; пробег текста — только `km_arg`;
       запись, рождённая до ручки (paid_total в памяти), K не пишет и говорит об этом;
  (E)  ручка ВКЛ, сквозной путь `_handle_servicing`: фото-пробег в km карточки не попадает, текстовый — попадает;
  (L)  ручка ВКЛ, прежний путь ответа (INTAKE_CONFIRM_STRICT=0) — те же два правила;
  (K)  ручка ВКЛ, дело К4: то же, плюс цель ожидания, рождённая до ручки с paid_total;
  (O)  ручка ВЫКЛ («0», «off» — откат): текст карточки и вызов моста — дословно прежние (947953e), включая записанные
       КАК ПРЕЖНЕЕ поведение отката дефекты (paid_total=1500.0; фото-пробег идёт в km_end по «да»).

Умолчание ручки — ВКЛ (`splinter._CLOSE_TRUTH_DEFAULT`): ручка не задана → путь правды (P1, D1); закреплённые наборы
tests/test_return_close.py и tests/test_rental_case_integ_spl.py по слову владельца ждут paid_total=None, их блобы
перезакреплены в tests/test_contractref_accept.py. Сеть запрещена подменой socket (rental_case_fakes), память Splinter
и база дела — только во временном каталоге прогона. Данные синтетические.
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
for _p in (HERE, ROOT):                  # итог: ROOT — первым, tests/ — вторым (чужой корень не берём)
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

FLAGS = ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", "CONTRACT_REF_GEN",
         "INTAKE_CONFIRM_STRICT", "CLOSE_TRUTH")
for _f in FLAGS:
    os.environ.pop(_f, None)

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
STATE_DIR = tempfile.mkdtemp(prefix="closetruth_state_", dir=TTMP)
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
SERV = S.SERVICING_CHAT
TOPIC = 4243
BIKE = "CB 300CC R 9011"
NAME = "Иван Тест"                   # синтетика (как в соседних наборах)
APPROVER = "deramor"                 # INTAKE_APPROVERS (по нику) — путь флага 0
OWNER = "turbophuket"
OWNER_ID = 504608015                 # APPROVER_IDS по умолчанию — путь флага 1 (дело К4)
TZ = datetime.timedelta(hours=7)
P = "🐀 Splinter\n"
DUE_LINE = " К доплате по листу закрытия: 1 500 ฿ — в CRM не пишу."
PHOTO_LINE = ("Пробег на сдаче: с фото прочитано 35200 — не подтверждено; закрыть: «да 35200» "
              "(или «да <верный пробег>»).")
PHOTO_TAIL = "Завершаю (Завершена + пробег из ответа)? да <пробег> / нет"


def local_now():
    return datetime.datetime.now(datetime.timezone.utc) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


def rent_row(row=21, bike=BIKE, name=NAME, booking_id="bk-r"):
    """Текущая аренда «В аренде» с −3 по +2 сут (живой формат двери clients)."""
    return F.make_row(row=row, status="В аренде", bike=bike, name=name, date_start=dt(-3), date_end=dt(2),
                      contacts="+66 80 000 0001", booking_id=booking_id, deposit_raw="5000", debt=0)


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
    _next = [830000]

    def __init__(self, text, uname=APPROVER, uid=None, reply_to=None, chat_id=INTAKE, topic=None, photo=False):
        Msg._next[0] += 1
        self.message_id = Msg._next[0]
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else None
        self.sticker = None
        self.chat_id = chat_id
        self.message_thread_id = topic
        self.media_group_id = None
        self.date = datetime.datetime.now(datetime.timezone.utc)
        self.from_user = U(uname, uid)
        self.reply_to_message = reply_to


class Ctx(object):
    class B(object):
        username = "turbobaby_manager_bot"
    bot = B()


class FakeClaude(object):
    """Разборщик текста и зрение — заданными ответами (без сети)."""

    def __init__(self, parsed, vision=None):
        self._p = parsed
        self._v = vision or {}

    def quick(self, system, text, max_tokens=300, **kw):
        if system == S.TRANSLATE_RU_TH:
            return "ครับ"
        return json.dumps(self._p)

    def vision(self, *a, **k):
        return json.dumps(self._v)


class Bridge(object):
    """Мост: дверь clients (живой формат) + красные шаги с журналом вызовов. close_booking — как closeBooking
    по смыслу проверок: без km_end — km_required (до записи)."""

    def __init__(self, rows, total_due=1500):
        self.rows = [dict(r) for r in rows]
        self.calls = []
        self.tickets = 0
        self.total_due = total_due

    def red(self, name):
        return [k for n, k in self.calls if n == name]

    def _call(self, action, **k):
        assert action == "clients", action
        return F.clients_reply(self.rows, filter=k.get("filter", "all"))

    def clients(self, filter="active"):
        return F.clients_reply(self.rows, filter=filter)

    def find_bike(self, q):
        return {"name": q, "status": "в аренде", "oil_last_km": 30500}

    def read_events(self, bike, limit=30):
        return {"ok": False, "error": "нет в подделке"}

    def state_set(self, **k):
        return {"ok": True}

    def add_event(self, **k):
        self.calls.append(("add_event", dict(k)))
        return {"ok": True, "saved": True}

    def service_pending_get(self, *a, **k):
        return {"ok": False, "error": "not_found"}

    def service_list(self, *a, **k):
        return {"items": []}

    def closing_upsert(self, **k):
        self.calls.append(("closing_upsert", dict(k)))
        return {"ok": True, "row": 5, "total_due": self.total_due}

    def issue_write_ticket(self):
        self.tickets += 1
        return {"ok": True, "ticket": "t-closetruth"}

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        if km_end in (None, ""):
            return {"ok": False, "error": "km_required", "message": "km_end обязателен"}
        for r in self.rows:
            if r["bike"] == bike and r["name"] == name and r["status"] == "В аренде":
                r["status"] = "Завершена"
                return {"ok": True, "closed": True, "row": r["row"], "bike": bike, "name": name}
        return {"ok": False, "error": "not_active", "message": "нет активной"}


SENDS = []
_MID = [940000]


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    _MID[0] += 1
    s = Sent(_MID[0], chat_id, text)
    SENDS.append(s)
    return s


async def rec_pass(*a, **k):
    return None


async def rec_dl(pm):
    return b"x"


S._send = rec_send
S._send_bike_card = rec_pass
S._after_mileage = rec_pass
S._ask_mileage_confirm = rec_pass
S._ask_service_col = rec_pass
S._download_photo = rec_dl


def run(coro):
    return asyncio.run(coro)


def reset():
    del SENDS[:]
    for d in (S._RETURN_CLOSES, S._RET_CLOSE_WARN_TS, S._HANDOVER_ACTIVATIONS, S._HO_ACT_WARN_TS, S._INTAKE_DRAFTS,
              S._RECENT_BOOKINGS, S._INTAKE_PASSPORT, S._CARD_LAST, S._PENDING_WORKS):
        d.clear()
    S._RC_STORE = None
    for f in FLAGS:
        os.environ.pop(f, None)


def texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards():
    return [s for s in SENDS if s.chat_id == INTAKE and "Завершаю" in s.text]


def ret_card(b, km="35200", total_due=1500, km_photo=""):
    run(S._return_close_card(Ctx(), b, BIKE, km=km, total_due=total_due, km_photo=km_photo))
    cs = cards()
    assert cs, texts()
    return cs[-1]


def say(b, text, reply=None, uname=APPROVER, uid=None):
    m = Msg(text, uname=uname, uid=uid, reply_to=reply)
    run(S._handle_intake(m, Ctx(), b, None))
    return m


def exp_close(km, paid=None):
    return [{"bike": BIKE, "name": NAME, "date_start": dt(-3), "km_end": km, "paid_total": paid}]


def photo_note(where):
    return P + S._CR_KM_PHOTO.format(km="35200", where=where)


class Case(unittest.TestCase):
    truth = "1"                      # значение CLOSE_TRUTH для класса; None — ручка не задана

    def setUp(self):
        reset()
        if self.truth is not None:
            os.environ["CLOSE_TRUTH"] = self.truth

    def tearDown(self):
        reset()


# ========================================================================================================== (P) чистое
class P_Pure(Case):
    truth = None

    def test_p1_knob_words_and_default(self):
        self.assertEqual(S._CLOSE_TRUTH_DEFAULT, "1", "умолчание ВКЛ (слово владельца о закреплённых наборах)")
        self.assertTrue(S._close_truth_on(), "ручка не задана → ВКЛ")
        for v in ("1", "on", "yes", "true", "да", "ON"):
            os.environ["CLOSE_TRUTH"] = v
            self.assertTrue(S._close_truth_on(), v)
        for v in ("0", "", " 0 ", "off", "no", "нет", "false", "FALSE", "Off"):
            os.environ["CLOSE_TRUTH"] = v
            self.assertFalse(S._close_truth_on(), repr(v))

    def test_p3_paid_arg_on_off(self):
        self.assertEqual(S._close_paid_arg(1500.0), (None, True), "умолчание ВКЛ — не шлём")
        os.environ["CLOSE_TRUTH"] = "0"
        self.assertEqual(S._close_paid_arg(1500.0), (1500.0, False), "ВЫКЛ — значение как есть")
        self.assertEqual(S._close_paid_arg(None), (None, False))
        os.environ["CLOSE_TRUTH"] = "1"
        self.assertEqual(S._close_paid_arg(1500.0), (None, True), "ВКЛ — не шлём и говорим, что сняли")
        self.assertEqual(S._close_paid_arg(None), (None, False), "снимать нечего — не говорим")

    def test_p4_photo_only_judges_record(self):
        self.assertTrue(S._close_km_photo_only({"km": "", "km_photo": "35200"}))
        self.assertFalse(S._close_km_photo_only({"km": "35200", "km_photo": "35999"}))
        self.assertFalse(S._close_km_photo_only({"km": "", "km_photo": ""}))
        self.assertFalse(S._close_km_photo_only({"km": "35200"}), "прежняя запись без km_photo")
        self.assertFalse(S._close_km_photo_only(None))
        os.environ["CLOSE_TRUTH"] = "0"
        self.assertTrue(S._close_km_photo_only({"km": "", "km_photo": "35200"}),
                        "обещание карточки держится и при снятой ручке")

    def test_p5_card_parts(self):
        self.assertEqual(S._close_card_parts("35200", "", 1500.0),
                         ("Пробег на сдаче: 35200.", DUE_LINE, "Завершаю (Завершена + пробег 35200)? да / нет"))
        self.assertEqual(S._close_card_parts("", "35200", None), (PHOTO_LINE, "", PHOTO_TAIL))
        self.assertEqual(S._close_card_parts("", "", None),
                         ("Пробег на сдаче: не увидел — ответь «да <цифра пробега>».", "",
                          "Завершаю (Завершена)? да / нет"))
        for parts in (S._close_card_parts("35200", "", 1500.0), S._close_card_parts("", "35200", 99.0)):
            self.assertNotIn("оплачено", "".join(parts).lower())


# ============================================================================== (T) ручка ВКЛ, строгий путь (по умолч.)
class T_OnStrict(Case):
    def test_t1_due_only_text_paid_none(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn(DUE_LINE, card.text)
        self.assertNotIn("оплачено", card.text.lower(), card.text)
        self.assertNotIn("Итог закрытия", card.text)
        self.assertTrue(card.text.endswith("Завершаю (Завершена + пробег 35200)? да / нет"), card.text)
        rec = S._RETURN_CLOSES[INTAKE]
        self.assertIsNone(rec["paid_total"])
        self.assertEqual(rec["due_total"], 1500.0)
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertIn(P + "✅ Завершена, строка 21.", texts(), "без пометки: снимать было нечего")

    def test_t2_zero_due_no_line(self):
        b = Bridge([rent_row()])
        card = ret_card(b, total_due=0)
        self.assertNotIn("К доплате", card.text)
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))

    def test_t3_photo_only_yes_without_number_zero_calls(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        self.assertIn(PHOTO_LINE, card.text)
        self.assertTrue(card.text.endswith(PHOTO_TAIL), card.text)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["km"], "", "фото-пробег — не проверенное поле карточки")
        for text in ("да", "закрывай", "да, закрывай"):
            with self.subTest(text=text):
                say(b, text, reply=card)
                self.assertEqual(b.red("close_booking"), [], "фото-пробег ушёл в мост без числа: %r" % text)
                self.assertEqual(b.tickets, 0, "билет 4.2 не выписывается")
                self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting", "карточка жива")
                self.assertEqual(texts()[-1], photo_note(" реплаем на карточку"))
        say(b, "да 35200", reply=card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "closed")

    def test_t4_photo_only_yes_on_note_does_not_write(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        say(b, "да", reply=card)
        note = [s for s in SENDS if s.text == photo_note(" реплаем на карточку")][-1]
        say(b, "да", reply=note)
        say(b, "да 35200", reply=note)
        self.assertEqual(b.red("close_booking"), [], "пояснение «немое»: реплай на него ничего не подтверждает")

    def test_t5_photo_hint_is_reference_for_order_check(self):
        """Р2: число ответа против фото-подсказки — разный порядок → переспрос без моста; повтор того же — вызов."""
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        say(b, "да 3520", reply=card)
        self.assertEqual(b.red("close_booking"), [])
        self.assertTrue(any("«3520»" in t and "35200" in t for t in texts()), texts())
        say(b, "да 3520", reply=card)
        self.assertEqual([c["km_end"] for c in b.red("close_booking")], ["3520"])

    def test_t6_text_km_only_digits_one_number(self):
        for km_in, want in (("35 200", "35200"), ("35200 km", "35200"), ("35200", "35200")):
            with self.subTest(km=km_in):
                reset()
                os.environ["CLOSE_TRUTH"] = "1"
                b = Bridge([rent_row()])
                card = ret_card(b, km=km_in)
                self.assertEqual(S._RETURN_CLOSES[INTAKE]["km"], want)
                say(b, "да", reply=card)
                self.assertEqual(b.red("close_booking"), exp_close(want))
        for km_in in ("35200/35300", "1", "123456789", "пробег"):
            with self.subTest(km=km_in):
                reset()
                os.environ["CLOSE_TRUTH"] = "1"
                b = Bridge([rent_row()])
                card = ret_card(b, km=km_in)
                self.assertEqual(S._RETURN_CLOSES[INTAKE]["km"], "", "не одно число 2–7 цифр — пробега нет")
                self.assertIn("не увидел", card.text)
                say(b, "да", reply=card)
                self.assertEqual([c["km_end"] for c in b.red("close_booking")], [None],
                                 "без числа — прежняя ветка km_required моста")

    def test_t7_text_km_wins_over_photo(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="35200", km_photo="35999")
        self.assertNotIn("35999", card.text)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["km_photo"], "")
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))

    def test_t8_record_born_before_knob_does_not_write_k(self):
        """Запись с paid_total из прежнего процесса (передача restart_handoff несёт paid_total) — K не пишем и говорим."""
        b = Bridge([rent_row()])
        card = ret_card(b)
        S._RETURN_CLOSES[INTAKE]["paid_total"] = 1500.0
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertIn(P + "✅ Завершена, строка 21." + S._CLOSE_PAID_NOTE, texts())

    def test_t9_noreply_path_bound_ask_photo_only(self):
        """«да» без реплая → адресное уточнение → «да» на него: фото-пробег по-прежнему моста не зовёт."""
        b = Bridge([rent_row()])
        ret_card(b, km="", km_photo="35200")
        say(b, "да")
        asks = [s for s in SENDS if "засчитываю только реплаем" in s.text]
        self.assertEqual(len(asks), 1, texts())
        say(b, "да", reply=asks[0])
        self.assertEqual(b.red("close_booking"), [])
        self.assertEqual(texts()[-1], photo_note(" реплаем на карточку"))


# ====================================================================== (E) ручка ВКЛ, сквозной путь `_handle_servicing`
RET_PARSE = {"type": "event", "event_type": "return", "bike": BIKE, "fuel": "полный", "mileage": "", "works": []}
VIS_KM = {"fuel": "полный", "mileage": "35200", "mileage_confidence": "low", "kind": "dashboard", "damage": None}


def do_return(b, parse, vis=None, photo=True):
    S.set_topic_bike(SERV, TOPIC, BIKE)
    m = Msg("вернул байк, принял", uname="mechanic_test", chat_id=SERV, topic=TOPIC, photo=photo)
    run(S._handle_servicing(m, Ctx(), b, FakeClaude(parse, vis)))


class E_OnServicing(Case):
    def test_e1_photo_km_not_in_card_km(self):
        b = Bridge([rent_row()])
        do_return(b, RET_PARSE, VIS_KM)
        cs = cards()
        self.assertEqual(len(cs), 1, texts())
        self.assertIn(PHOTO_LINE, cs[0].text)
        self.assertIn(DUE_LINE, cs[0].text)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["km"], "")
        say(b, "да", reply=cs[0])
        self.assertEqual(b.red("close_booking"), [], "сырой OCR фото ушёл в N по «да»")
        say(b, "да 35210", reply=cs[0])
        self.assertEqual(b.red("close_booking"), exp_close("35210"))

    def test_e2_text_km_in_card(self):
        b = Bridge([rent_row()])
        do_return(b, dict(RET_PARSE, mileage="35 300"), VIS_KM)
        cs = cards()
        self.assertEqual(len(cs), 1, texts())
        self.assertIn("Пробег на сдаче: 35300.", cs[0].text)
        self.assertNotIn("с фото", cs[0].text)
        say(b, "да", reply=cs[0])
        self.assertEqual(b.red("close_booking"), exp_close("35300"))


# ============================================================== (L) ручка ВКЛ, прежний путь ответа (STRICT=0)
class L_OnLegacyReply(Case):
    def setUp(self):
        super(L_OnLegacyReply, self).setUp()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"

    def test_l1_paid_none(self):
        b = Bridge([rent_row()])
        ret_card(b)
        say(b, "да")
        self.assertEqual(b.red("close_booking"), exp_close("35200"))

    def test_l2_photo_only_yes_zero_calls_then_number(self):
        b = Bridge([rent_row()])
        ret_card(b, km="", km_photo="35200")
        say(b, "да")
        self.assertEqual(b.red("close_booking"), [])
        self.assertEqual(b.tickets, 0)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "awaiting")
        self.assertEqual(texts()[-1], photo_note(""))
        say(b, "да 35300")
        self.assertEqual(b.red("close_booking"), exp_close("35300"))

    def test_l3_record_born_before_knob(self):
        b = Bridge([rent_row()])
        ret_card(b)
        S._RETURN_CLOSES[INTAKE]["paid_total"] = 1500.0
        say(b, "да")
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertIn(P + "✅ Завершена, строка 21." + S._CLOSE_PAID_NOTE, texts())


# ============================================================================== (K) ручка ВКЛ, дело К4 (хранилище)
class K_OnCaseStore(Case):
    def setUp(self):
        super(K_OnCaseStore, self).setUp()
        os.environ["RENTAL_CASE_APPROVALS"] = "1"
        import rental_case
        d = tempfile.mkdtemp(prefix="closetruth_k4_%s_" % self._testMethodName[5:20], dir=TTMP)
        p = os.path.join(d, "rental_case.sqlite")
        rental_case.Store.create(p)
        os.environ["RENTAL_CASE_DB"] = p

    def k4(self, b, text, reply):
        return say(b, text, reply=reply, uname=OWNER, uid=OWNER_ID)

    def test_k1_due_text_paid_none(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn(DUE_LINE, card.text)
        self.assertIn("РЕПЛАЕМ", card.text)
        self.assertNotIn("оплачено", card.text.lower())
        self.k4(b, "да", card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertTrue(any(t == P + "✅ Завершена, строка 21." for t in texts()), texts())

    def test_k2_photo_only_new_card_then_number(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        self.assertIn(PHOTO_LINE, card.text)
        n = len(cards())
        self.k4(b, "да", card)
        self.assertEqual(b.red("close_booking"), [], "К4: фото-пробег ушёл в мост без числа")
        self.assertEqual(b.tickets, 0)
        self.assertIn(photo_note(" реплаем на новую карточку ниже"), texts())
        again = cards()
        self.assertEqual(len(again), n + 1, "новая карточка того же закрытия: %r" % texts())
        self.assertIn(PHOTO_LINE, again[-1].text)
        self.k4(b, "да 35300", again[-1])
        self.assertEqual(b.red("close_booking"), exp_close("35300"))

    def test_k3_target_born_before_knob_does_not_write_k(self):
        """Цель ожидания, рождённая прежним кодом с paid_total (живёт в хранилище через рестарт): K не пишем."""
        b = Bridge([rent_row()])
        cand = S._return_resolve_close(b, BIKE)
        run(S._rc_close_card(Ctx(), b, BIKE, cand, "35200", 1500.0))
        card = cards()[-1]
        self.assertNotIn("оплачено", card.text.lower(), "при ручке «оплачено» не обещается и старой цели")
        self.k4(b, "да", card)
        self.assertEqual(b.red("close_booking"), exp_close("35200"))
        self.assertIn(P + "✅ Завершена, строка 21." + S._CLOSE_PAID_NOTE, texts())


# ================================================== (D) ручка НЕ задана: умолчание ВКЛ — путь правды, а не откат
class D_DefaultOn(Case):
    truth = None

    def test_d1_unset_knob_is_truth_path(self):
        self.assertNotIn("CLOSE_TRUTH", os.environ)
        b = Bridge([rent_row()])
        do_return(b, RET_PARSE, VIS_KM)
        cs = cards()
        self.assertEqual(len(cs), 1, texts())
        self.assertIn(PHOTO_LINE, cs[0].text)
        self.assertIn(DUE_LINE, cs[0].text)
        self.assertNotIn("оплачено", cs[0].text.lower(), cs[0].text)
        say(b, "да", reply=cs[0])
        self.assertEqual(b.red("close_booking"), [], "умолчание: фото-пробег без числа в мост не идёт")
        say(b, "да 35210", reply=cs[0])
        self.assertEqual(b.red("close_booking"), exp_close("35210"), "умолчание: paid_total=None, K не пишем")


# ============================================================== (O) ручка ВЫКЛ: дословно прежнее (947953e), откат
OLD_CARD = (P + "📥 ПРИЁМ: CB 300CC R 9011 вернулся от Иван Тест, строка 21. Пробег на сдаче: 35200. "
            "Итог закрытия: 1 500 ฿.\n💰 Верни депозит: 5 000 ฿\n"
            "Завершаю (Завершена + пробег 35200 + оплачено 1 500)? да / нет")
OLD_CARD_NOKM = (P + "📥 ПРИЁМ: CB 300CC R 9011 вернулся от Иван Тест, строка 21. Пробег на сдаче: не увидел — "
                 "ответь «да <цифра пробега>». Итог закрытия: 1 500 ฿.\n💰 Верни депозит: 5 000 ฿\n"
                 "Завершаю (Завершена + оплачено 1 500)? да / нет")


class O_OffLegacy(Case):
    truth = None

    def _both(self):
        for v in ("0", "off"):          # умолчание ВКЛ: откат — только явным словом
            reset()
            os.environ["CLOSE_TRUTH"] = v
            yield v

    def test_o1_card_text_verbatim_and_paid_written(self):
        for v in self._both():
            with self.subTest(knob=v):
                b = Bridge([rent_row()])
                card = ret_card(b, km_photo="35999")
                self.assertEqual(card.text, OLD_CARD)
                self.assertEqual(S._RETURN_CLOSES[INTAKE]["paid_total"], 1500.0)
                self.assertNotIn("km_photo", S._RETURN_CLOSES[INTAKE], "ручка ВЫКЛ: km_photo не читается")
                self.assertNotIn("due_total", S._RETURN_CLOSES[INTAKE])
                say(b, "да", reply=card)
                self.assertEqual(b.red("close_booking"), exp_close("35200", 1500.0),
                                 "откат: прежняя запись итога листа в K (дефект записан как прежнее)")
                self.assertIn(P + "✅ Завершена, строка 21.", texts())

    def test_o2_no_km_card_verbatim(self):
        for v in self._both():
            with self.subTest(knob=v):
                b = Bridge([rent_row()])
                card = ret_card(b, km="", km_photo="35200")
                self.assertEqual(card.text, OLD_CARD_NOKM)
                say(b, "да", reply=card)
                self.assertEqual(b.red("close_booking"), exp_close(None, 1500.0), "прежняя ветка km_required")

    def test_o3_servicing_photo_km_goes_to_card_as_before(self):
        """Откат: фото-пробег сливается в km карточки и по «да» уходит в km_end (дефект записан как прежнее)."""
        for v in self._both():
            with self.subTest(knob=v):
                b = Bridge([rent_row()])
                do_return(b, RET_PARSE, VIS_KM)
                cs = cards()
                self.assertEqual(len(cs), 1, texts())
                self.assertIn("Пробег на сдаче: 35200.", cs[0].text)
                self.assertIn("Итог закрытия: 1 500 ฿.", cs[0].text)
                say(b, "да", reply=cs[0])
                self.assertEqual(b.red("close_booking"), exp_close("35200", 1500.0))

    def test_o4_k4_card_text_verbatim(self):
        import rental_case
        for v in self._both():
            with self.subTest(knob=v):
                os.environ["RENTAL_CASE_APPROVALS"] = "1"
                d = tempfile.mkdtemp(prefix="closetruth_k4off_", dir=TTMP)
                p = os.path.join(d, "rental_case.sqlite")
                rental_case.Store.create(p)
                os.environ["RENTAL_CASE_DB"] = p
                b = Bridge([rent_row()])
                card = ret_card(b, km_photo="35999")
                self.assertEqual(card.text, OLD_CARD + S._RC_REPLY_HINT)
                say(b, "да", reply=card, uname=OWNER, uid=OWNER_ID)
                self.assertEqual(b.red("close_booking"), exp_close("35200", 1500.0))

    def test_o5_legacy_reply_verbatim(self):
        for v in self._both():
            with self.subTest(knob=v):
                os.environ["INTAKE_CONFIRM_STRICT"] = "0"
                b = Bridge([rent_row()])
                ret_card(b)
                say(b, "да")
                self.assertEqual(b.red("close_booking"), exp_close("35200", 1500.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
