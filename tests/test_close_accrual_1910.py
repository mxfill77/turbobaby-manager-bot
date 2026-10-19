# -*- coding: utf-8 -*-
"""CLOSEACCRUAL1910 (19.10.2026): начисление доплат листа закрытия в K формулой «основа+доплаты» и расшифровка
примечанием к A — сторона SPLINTER (ручка CLOSE_ACCRUAL, умолчание ВЫКЛ, только поверх CLOSE_TRUTH).

Решение владельца 19.10 23:3x: «доплаты … ставить перед основной суммой = и доплаты через + например 10000+500+1000
И писать в примечание в столбец A этой строки». Это НАЧИСЛЕНИЕ к оплате, а не квитанция о деньгах. Условия Codex
TB-REVIEW-1910-2400 (1)–(5); сторона моста — tests/test_close_accrual_gs.py (сборка bridge_build_close_accrual/).

Разделы:
  (P)  чистые части: слова ручки; литерал части и день — те же, что у моста (сверка node-харнессом); close_op_id —
       тот же вывод, что closeAccrualOpId_; привязка ответа листа закрытия (`_acc_from_closing`) — стоп на старом
       мосте, фоллбэке по байку, чужой брони/строке/дне, нечисловой части, сумме ≠ итогу; квитанция → слова;
  (F)  ручка ВЫКЛ (не задана) — карточка и вызов моста ровно CLOSETRUTH1910, даже когда ответ листа несёт части;
       CLOSE_TRUTH=0 — начисления нет; карточка с начислением, а ручку сняли — начисление не шлётся;
  (S)  ручка ВКЛ, строгий путь: карточка «начисление к оплате (это не оплата)»; «да» — ровно один вызов с полем
       accrual без paid_total; квитанция done / нет квитанции (старый мост) / чужой op_id / partial / unknown /
       stopped / already_done / пустой K / текст в K; исключение после отправки и write_failed — «неизвестно»;
       lock_busy — «не записано»; стоп на карточке — закрытие идёт без начисления и говорит почему; два «да» двух
       операторов — один вызов; фото-пробег — прежние правила;
  (R)  рестарт: карточка с операцией через handoff_write/handoff_restore исполняет ТУ ЖЕ операцию; правленая запись
       передачи — начисление не шлётся;
  (L)  прежний путь ответа (INTAKE_CONFIRM_STRICT=0); (K) дело К4 (хранилище);
  (E)  сквозной: `_handle_servicing` → НАСТОЯЩИЙ Closing.js (closing_upsert) → карточка → «да» → НАСТОЯЩИЙ
       closeBooking сборки (node-харнесс, листы в памяти) — K, примечание к A, квитанция; пустой K; фоллбэк по байку;
  (C)  настоящий BridgeClient._post: тело запроса — accrual, origin agent + билет, paid_total нет.
Сеть запрещена подменой socket (rental_case_fakes), память Splinter и база дела — только во временном каталоге
прогона (K4_TTMP). Данные синтетические.
"""
import asyncio
import datetime
import json
import os
import subprocess
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
         "INTAKE_CONFIRM_STRICT", "CLOSE_TRUTH", "CLOSE_ACCRUAL")
for _f in FLAGS:
    os.environ.pop(_f, None)

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
STATE_DIR = tempfile.mkdtemp(prefix="closeaccrual_state_", dir=TTMP)
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
import restart_handoff as RH  # noqa: E402
import bridge_client  # noqa: E402

HARNESS = os.path.join(HERE, "close_accrual_gs_harness.js")
INTAKE = S.INTAKE_CHAT
SERV = S.SERVICING_CHAT
TOPIC = 4244
BIKE = "CB 300CC R 9011"
NAME = "Иван Тест"                   # синтетика (как в соседних наборах)
BID = "bk-r"
APPROVER = "deramor"                 # INTAKE_APPROVERS (по нику) — путь флага 0
APPROVER2 = "turbophuket"
OWNER = "turbophuket"
OWNER_ID = 504608015                 # APPROVER_IDS по умолчанию — путь флага 1 (дело К4)
TZ = datetime.timedelta(hours=7)
P = "🐀 Splinter\n"
DUE_LINE = " К доплате по листу закрытия: 1 500 ฿ — в CRM не пишу."
ACC_LINE = (" Начисление к оплате (это не оплата): доплаты дни 500 · ущерб 1000 = 1 500 ฿ — допишу в K формулой к "
            "основной сумме (+500+1000), расшифровку — в примечание к A.")
ACC_TAIL = "Завершаю (Завершена + пробег 35200 + начисление доплат)? да / нет"


def local_now():
    return datetime.datetime.now(datetime.timezone.utc) + TZ


def dt(days, hm="10:00"):
    return "%s %s" % ((local_now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d"), hm)


DAY0 = dt(-3)[:10]


def rent_row(row=21, bike=BIKE, name=NAME, booking_id=BID):
    """Текущая аренда «В аренде» с −3 по +2 сут (живой формат двери clients)."""
    return F.make_row(row=row, status="В аренде", bike=bike, name=name, date_start=dt(-3), date_end=dt(2),
                      contacts="+66 80 000 0001", booking_id=booking_id, deposit_raw="5000", debt=0)


def closing_reply(parts=None, match="booking_id", bid=BID, crow=5, booking="default", total=None, bike=BIKE):
    """Ответ closing_upsert нового моста (bridge_build_close_accrual/Closing.js): части и привязка."""
    pp = {"surcharge_days": "500", "surcharge_fuel": "", "damage": 1000, "other": ""}
    pp.update(parts or {})
    lits = [S._acc_lit(pp[k]) for k in S._ACC_PARTS]
    tot = total if total is not None else sum(int(x) for x in lits if x)
    bk = ({"row": 21, "status": "В аренде", "bike": BIKE, "date_start": DAY0, "date_end": dt(2)[:10]}
          if booking == "default" else booking)
    return {"ok": True, "row": crow, "updated": True, "total_due": tot, "components": pp,
            "binding": {"v": 1, "row": crow, "match": match, "booking_id": bid, "bike": bike, "date_return": "",
                        "updated_at": "2026-10-19T10:00:00.000Z", "booking": bk,
                        "booking_why": "" if bk else "booking_not_found"}}


def receipt(op, status="done", k="=10000+500+1000", base="number", k_written=True, reason="", note="DONE"):
    return {"v": 1, "op_id": op, "status": status, "reason": reason, "base": base, "k_written": k_written,
            "note": note, "addends": "+500+1000", "k_readback": k}


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
    _next = [870000]

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
    """Мост-подделка: дверь clients (живой формат), лист закрытия — заданный ответ, красные шаги с журналом.
    close_booking (метод клиента — путь без начисления) и _post (путь начисления, `_close_booking_accrual`)
    записываются раздельно: какой из двух путей пошёл, видно по журналу."""

    def __init__(self, rows, closing=None, post_reply=None):
        self.rows = [dict(r) for r in rows]
        self.calls = []
        self.tickets = 0
        self.closing = closing if closing is not None else closing_reply()
        self.post_reply = post_reply

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
        return dict(self.closing) if isinstance(self.closing, dict) else self.closing

    def issue_write_ticket(self):
        self.tickets += 1
        return {"ok": True, "ticket": "t-closeaccrual"}

    def _close(self, bike, name, km_end):
        if km_end in (None, ""):
            return {"ok": False, "error": "km_required", "message": "km_end обязателен"}
        for r in self.rows:
            if r["bike"] == bike and r["name"] == name and r["status"] == "В аренде":
                r["status"] = "Завершена"
                return {"ok": True, "closed": True, "row": r["row"], "bike": bike, "name": name}
        return {"ok": False, "error": "not_active", "message": "нет активной"}

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        return self._close(bike, name, km_end)

    def _post(self, action, **fields):
        assert action == "close_booking", action
        self.calls.append(("post_close_booking", dict(fields)))
        if self.post_reply is not None:
            return self.post_reply(fields)
        res = self._close(fields["bike"], fields["name"], fields.get("km_end"))
        if res.get("ok"):
            res["accrual"] = receipt(fields["accrual"]["close_op_id"])
        return res


SENDS = []
_MID = [960000]


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
    for name in ("_CR_NOTES", "_CR_FORGOT", "_IC_DEAD_ASKS"):
        getattr(S, name, {}).clear()
    S._RC_STORE = None
    for f in FLAGS:
        os.environ.pop(f, None)


def texts():
    return [s.text for s in SENDS if s.chat_id == INTAKE]


def cards():
    return [s for s in SENDS if s.chat_id == INTAKE and "Завершаю" in s.text]


def ret_card(b, km="35200", total_due=1500, km_photo="", closing="bridge"):
    cu = b.closing if closing == "bridge" else closing
    run(S._return_close_card(Ctx(), b, BIKE, km=km, total_due=total_due, km_photo=km_photo, closing=cu))
    cs = cards()
    assert cs, texts()
    return cs[-1]


def say(b, text, reply=None, uname=APPROVER, uid=None):
    m = Msg(text, uname=uname, uid=uid, reply_to=reply)
    run(S._handle_intake(m, Ctx(), b, None))
    return m


def exp_op(parts=("500", "", "1000", ""), brow=21, crow=5, bid=BID, day=None):
    return S._acc_op_id(bid, brow, BIKE, day or DAY0, crow, list(parts))


def exp_payload(km="35200", parts=("500", "", "1000", "")):
    return {"bike": BIKE, "name": NAME, "date_start": dt(-3), "km_end": km,
            "accrual": {"v": 1, "close_op_id": exp_op(parts), "booking_id": BID, "booking_row": 21,
                        "date_start_day": DAY0, "closing_row": 5, "parts": dict(zip(S._ACC_PARTS, parts))}}


def node(payload):
    p = subprocess.run(["node", HARNESS, "--stdin"], input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


class Case(unittest.TestCase):
    truth = "1"                      # CLOSE_TRUTH
    accrual = "1"                    # CLOSE_ACCRUAL; None — ручка не задана

    def setUp(self):
        reset()
        if self.truth is not None:
            os.environ["CLOSE_TRUTH"] = self.truth
        if self.accrual is not None:
            os.environ["CLOSE_ACCRUAL"] = self.accrual

    def tearDown(self):
        reset()


# ========================================================================================================== (P) чистое
class P_Pure(Case):
    accrual = None

    def test_p1_knob_default_off_and_needs_truth(self):
        self.assertEqual(S._CLOSE_ACCRUAL_DEFAULT, "0")
        self.assertFalse(S._close_accrual_on(), "ручка не задана → ВЫКЛ")
        for v in ("1", "on", "yes", "true", "да"):
            os.environ["CLOSE_ACCRUAL"] = v
            self.assertTrue(S._close_accrual_on(), v)
        for v in ("0", "", "off", "no", "нет", "false"):
            os.environ["CLOSE_ACCRUAL"] = v
            self.assertFalse(S._close_accrual_on(), repr(v))
        os.environ["CLOSE_ACCRUAL"] = "1"
        os.environ["CLOSE_TRUTH"] = "0"
        self.assertFalse(S._close_accrual_on(), "откат CLOSE_TRUTH=0 — начисления нет никогда")

    def test_p2_lit_same_as_bridge(self):
        vals = ["500", 500, 500.0, "0500", 0, "0", "", None, "=1+1", "half", -5, "1e3", "12.5", 12.5, True,
                " 500", "500 ฿", "1,5", 10 ** 9, "999999999", float("nan"), float("inf")]
        py = [S._acc_lit(v) for v in vals]
        self.assertEqual(py, ["500", "500", "500", "500", "", "", "", "", None, None, None, None, None, None, None,
                              None, None, None, None, "999999999", None, None])
        js_vals = [v for v in vals if not (isinstance(v, float) and v != v) and v not in (float("inf"),)]
        js = node({"mode": "opid", "vectors": [], "lits": js_vals})["lits"]
        self.assertEqual(js, [S._acc_lit(v) for v in js_vals], "литерал части у моста и у Splinter разошёлся")

    def test_p3_day(self):
        self.assertEqual(S._acc_day("2026-07-10 10:00"), "2026-07-10")
        self.assertEqual(S._acc_day("2026-07-10"), "2026-07-10")
        self.assertEqual(S._acc_day("10.07.2026"), "2026-07-10")
        self.assertEqual(S._acc_day("10.07.2026 , 13:00"), "2026-07-10")
        for bad in ("", None, "скоро", "2026-02-30 10:00", "32.13.2026"):
            self.assertIsNone(S._acc_day(bad), repr(bad))

    def test_p4_op_id_same_derivation_as_bridge(self):
        vecs = [[BID, 21, BIKE, "2026-07-10", 5, ["500", "", "1000", ""]],
                ["bk-acc-1", 2, " 9011 ", "2026-07-10", 7, ["500", "", "1000", ""]],
                ["u-ё", 1268, "Мото ТЕСТ 1111", "2026-12-31", 99, ["", "", "", "7"]]]
        js = node({"mode": "opid", "vectors": vecs})["ids"]
        self.assertEqual(js, [S._acc_op_id(*v) for v in vecs], "close_op_id у моста и у Splinter разошёлся")
        self.assertRegex(js[0], r"^co1-[0-9a-f]{16}$")
        self.assertNotEqual(S._acc_op_id(BID, 21, BIKE, DAY0, 5, ["500", "", "1000", ""]),
                            S._acc_op_id(BID, 21, BIKE, DAY0, 5, ["500", "", "1500", ""]), "части — в id")

    def test_p5_binding_valid(self):
        cand = {"row": 21, "date_start": dt(-3), "booking_id": BID, "name": NAME}
        acc, why = S._acc_from_closing(closing_reply(), cand, BIKE)
        self.assertIsNone(why)
        self.assertEqual(acc, {"acc_op": exp_op(), "acc_bid": BID, "acc_brow": 21, "acc_ds": DAY0, "acc_crow": 5,
                               "acc_parts": ["500", "", "1000", ""]})
        acc_new, why_new = S._acc_from_closing(closing_reply(match="new"), cand, BIKE)
        self.assertIsNone(why_new)
        self.assertEqual(acc_new["acc_op"], exp_op(), "строка дописана этим вызовом с booking_id — годится")

    def test_p6_binding_stops(self):
        cand = {"row": 21, "date_start": dt(-3), "booking_id": BID, "name": NAME}
        old = {"ok": True, "row": 5, "total_due": 1500}
        cases = [
            ("old-bridge", old, cand, "старая версия"),
            ("bike-fallback", closing_reply(match="bike"), cand, "по байку"),
            ("new-no-id", closing_reply(match="new_no_id"), cand, "по байку"),
            ("other-booking", closing_reply(bid="bk-old"), cand, "другой брони"),
            ("no-cand-id", closing_reply(), dict(cand, booking_id=""), "нет booking_id"),
            ("booking-unknown", closing_reply(booking=None), cand, "не найдена"),
            ("other-row", closing_reply(booking={"row": 22, "date_start": DAY0}), cand, "другая строка"),
            ("other-day", closing_reply(booking={"row": 21, "date_start": dt(-4)[:10]}), cand, "день начала"),
            ("formula-part", closing_reply(parts={"damage": "=1+1"}, total=1502), cand, "не целое"),
            ("text-part", closing_reply(parts={"surcharge_fuel": "half"}, total=1500), cand, "не целое"),
            ("fraction-part", closing_reply(parts={"other": "12.5"}, total=1512.5), cand, "не целое"),
            ("negative-part", closing_reply(parts={"other": -5}, total=1495), cand, "не целое"),
            ("sum-mismatch", closing_reply(total=2000), cand, "сумма частей"),
            ("crow-mismatch", dict(closing_reply(), row=6), cand, "не названа"),
            ("bike-mismatch", closing_reply(bike="NMAX 4957"), cand, "байк"),
            ("no-binding", dict(closing_reply(), binding=None), cand, "нет привязки"),
            ("part-missing", dict(closing_reply(), components={"surcharge_days": "500"}), cand, "нет части"),
            ("not-ok", {"ok": False, "error": "closing_failed"}, cand, "не ответил"),
        ]
        for name, cu, cd, word in cases:
            with self.subTest(case=name):
                acc, why = S._acc_from_closing(cu, cd, BIKE, 1500.0)
                self.assertIsNone(acc)
                self.assertIn(word, why or "", why)
        self.assertEqual(S._acc_from_closing(dict(old, total_due=0), cand, BIKE), (None, None), "доплат нет")
        self.assertEqual(S._acc_from_closing(closing_reply(parts={"surcharge_days": "", "damage": 0}, total=0),
                                             cand, BIKE), (None, None))
        self.assertEqual(S._acc_from_closing(None, cand, BIKE, None), (None, None), "ни ответа, ни итога")

    def test_p7_payload_and_off(self):
        rec = {"bike": BIKE, "acc_op": exp_op(), "acc_bid": BID, "acc_brow": 21, "acc_ds": DAY0, "acc_crow": 5,
               "acc_parts": ["500", "", "1000", ""]}
        self.assertEqual(S._acc_payload(rec), (None, None), "ручка ВЫКЛ — поле не шлём")
        os.environ["CLOSE_ACCRUAL"] = "1"
        pl, why = S._acc_payload(rec)
        self.assertIsNone(why)
        self.assertEqual(pl, exp_payload()["accrual"])
        self.assertEqual(S._acc_payload(dict(rec, acc_parts=["700", "", "1000", ""])),
                         (None, "поля начисления карточки не сошлись с её операцией"))
        self.assertEqual(S._acc_payload(dict(rec, acc_parts=["=1", "", "1000", ""]))[0], None)
        self.assertEqual(S._acc_payload({"bike": BIKE, "acc_stop": "почему"}), (None, "почему"))
        self.assertEqual(S._acc_payload({"bike": BIKE}), (None, None), "карточка до ручки — путь CLOSETRUTH1910")

    def test_p8_receipt_words(self):
        pl = exp_payload()["accrual"]
        op = pl["close_op_id"]
        W = lambda rc: S._acc_receipt_words({"ok": True, "accrual": rc} if rc is not None else {"ok": True}, pl, None)
        done = W(receipt(op))
        self.assertIn("Начислено к оплате (это не оплата): K = =10000+500+1000", done)
        self.assertIn("в примечании к A", done)
        self.assertEqual(W(None), S._ACC_NO_RECEIPT)
        self.assertEqual(S._ACC_NO_RECEIPT, " Доплаты не записаны: Bridge их не подтвердил.")
        self.assertEqual(W(receipt("co1-0000000000000000")), S._ACC_NO_RECEIPT, "чужая операция — не квитанция")
        self.assertEqual(W(dict(receipt(op), status="ok")), S._ACC_NO_RECEIPT, "незнакомый статус")
        no_k = receipt(op)
        del no_k["k_readback"]
        self.assertEqual(W(no_k), S._ACC_NO_RECEIPT, "без чтения K назад — не квитанция")
        self.assertIn("основная сумма в K не подтверждена (K пуст)",
                      W(receipt(op, base="empty", k_written=False, k="", note="NOTE_ONLY")))
        self.assertIn("В K не целое число — K не трогал",
                      W(receipt(op, base="text", k_written=False, k="оплатил", note="NOTE_ONLY")))
        self.assertIn("В K формула без числового значения — K не трогал",
                      W(receipt(op, base="error", k_written=False, k="=X99", note="NOTE_ONLY")))
        self.assertIn("уже начислены раньше — второй раз не добавлял", W(receipt(op, status="already_done")))
        self.assertIn("Доплаты не записаны: строка CRM — не та аренда",
                      W(receipt(op, status="stopped", reason="binding_mismatch", k_written=False, k="10000")))
        self.assertIn("записано частично (метка DONE не подтвердилась)",
                      W(receipt(op, status="partial", reason="note_done_unconfirmed")))
        self.assertIn("исход неизвестен (K прочитан назад не тем)",
                      W(receipt(op, status="unknown", reason="k_readback_mismatch", k_written=False)))
        for rc in (receipt(op), receipt(op, status="partial"), receipt(op, status="unknown"), None):
            self.assertNotIn("оплачено", W(rc).lower())
            self.assertNotIn("получено", W(rc).lower())
        for st in ("partial", "unknown"):
            self.assertIn("повтор не делаю", W(receipt(op, status=st)))
            self.assertNotIn("Начислено к оплате", W(receipt(op, status=st)), "частичное — не «записаны»")


# ======================================================== (F) ручка ВЫКЛ / CLOSE_TRUTH=0: ровно путь CLOSETRUTH1910
class F_Off(Case):
    accrual = None

    def test_f1_unset_knob_card_and_call_are_closetruth(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn(DUE_LINE, card.text)
        self.assertNotIn("Начисление", card.text)
        self.assertTrue(card.text.endswith("Завершаю (Завершена + пробег 35200)? да / нет"), card.text)
        self.assertFalse([k for k in S._RETURN_CLOSES[INTAKE] if k.startswith("acc_")], S._RETURN_CLOSES[INTAKE])
        say(b, "да", reply=card)
        self.assertEqual(b.red("close_booking"), [{"bike": BIKE, "name": NAME, "date_start": dt(-3), "km_end": "35200",
                                                    "paid_total": None}])
        self.assertEqual(b.red("post_close_booking"), [], "поле accrual при ручке ВЫКЛ не шлётся")
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21.")

    def test_f2_truth_off_no_accrual(self):
        os.environ["CLOSE_TRUTH"] = "0"
        os.environ["CLOSE_ACCRUAL"] = "1"
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn("Итог закрытия: 1 500 ฿.", card.text)
        say(b, "да", reply=card)
        self.assertEqual([c["paid_total"] for c in b.red("close_booking")], [1500.0], "откат — прежний путь")
        self.assertEqual(b.red("post_close_booking"), [])

    def test_f3_card_with_op_knob_removed_before_yes(self):
        os.environ["CLOSE_ACCRUAL"] = "1"
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["acc_op"], exp_op())
        os.environ["CLOSE_ACCRUAL"] = "0"
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("close_booking")), 1)
        self.assertEqual(b.red("post_close_booking"), [], "ручку сняли — начисление не шлётся")
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21.")


# ============================================================================== (S) ручка ВКЛ, строгий путь (по умолч.)
class S_OnStrict(Case):
    def test_s1_card_says_accrual_not_payment(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn(ACC_LINE, card.text)
        self.assertTrue(card.text.endswith(ACC_TAIL), card.text)
        self.assertNotIn("оплачено", card.text.lower())
        self.assertNotIn(DUE_LINE, card.text)
        rec = S._RETURN_CLOSES[INTAKE]
        self.assertEqual((rec["acc_op"], rec["acc_parts"], rec["acc_crow"], rec["acc_brow"], rec["acc_ds"]),
                         (exp_op(), ["500", "", "1000", ""], 5, 21, DAY0))
        self.assertIsNone(rec["paid_total"])

    def test_s2_yes_one_call_with_accrual_no_paid(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(b.red("post_close_booking"), [exp_payload()])
        self.assertNotIn("paid_total", b.red("post_close_booking")[0])
        self.assertEqual(b.red("close_booking"), [], "путь начисления — одним вызовом, второго закрытия нет")
        self.assertEqual(b.tickets, 1, "красный шаг — под одним билетом 4.2")
        last = texts()[-1]
        self.assertTrue(last.startswith(P + "✅ Завершена, строка 21. Начислено к оплате (это не оплата): "
                                            "K = =10000+500+1000"), last)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "closed")

    def test_s3_old_bridge_no_receipt(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": True, "closed": True, "row": 21, "paid_total": None})
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21." + S._ACC_NO_RECEIPT)

    def test_s4_receipt_other_op_is_not_receipt(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": True, "row": 21,
                                                        "accrual": receipt("co1-ffffffffffffffff")})
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21." + S._ACC_NO_RECEIPT)

    def test_s5_partial_named_no_retry(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": True, "row": 21, "accrual": receipt(
            f["accrual"]["close_op_id"], status="partial", reason="exception_at_note_done: mock", note="IN_PROGRESS")})
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertIn("записано частично", texts()[-1])
        self.assertIn("повтор не делаю", texts()[-1])
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("post_close_booking")), 1, "частичный исход не повторяется")

    def test_s6_exception_after_send_unknown_both(self):
        def boom(f):
            raise TimeoutError("read timeout")
        b = Bridge([rent_row()], post_reply=boom)
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(texts()[-1], P + S._CR_UNKNOWN["close"].format(err="TimeoutError") + S._ACC_UNKNOWN)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["status"], "write_unknown")
        say(b, "да", reply=card)
        self.assertEqual(len(b.red("post_close_booking")), 1, "неизвестный исход не повторяется")

    def test_s7_write_failed_is_unknown(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": False, "error": "write_failed", "message": "x",
                                                        "accrual": receipt(f["accrual"]["close_op_id"],
                                                                           status="stopped", k_written=False)})
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertEqual(texts()[-1], P + S._CR_UNKNOWN["close"].format(err="write_failed") + S._ACC_UNKNOWN)

    def test_s8_lock_busy_not_written(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": False, "error": "lock_busy", "message": "замок занят"})
        card = ret_card(b)
        say(b, "да", reply=card)
        self.assertTrue(texts()[-1].startswith(P + "❌ Закрытие не прошло: lock_busy."), texts()[-1])
        self.assertNotIn("неизвестен", texts()[-1])

    def test_s9_stop_at_card_close_runs_without_accrual(self):
        b = Bridge([rent_row()], closing=closing_reply(match="bike"))
        card = ret_card(b)
        why = "строка листа закрытия найдена по байку, а не по брони — может быть чужой аренды"
        self.assertIn(" К доплате по листу закрытия: 1 500 ฿ — в CRM не пишу (доплаты не начисляю: %s)." % why,
                      card.text)
        self.assertTrue(card.text.endswith("Завершаю (Завершена + пробег 35200)? да / нет"), card.text)
        say(b, "да", reply=card)
        self.assertEqual(b.red("post_close_booking"), [])
        self.assertEqual([c["paid_total"] for c in b.red("close_booking")], [None])
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21. Доплаты не записаны: %s." % why)

    def test_s10_wrong_rental_same_bike(self):
        """Строка листа закрытия от прежней аренды того же байка (другая бронь) — начисление стоп."""
        for name, cu in (("other-booking-id", closing_reply(bid="bk-prev")),
                         ("other-crm-row", closing_reply(booking={"row": 7, "date_start": DAY0}))):
            with self.subTest(case=name):
                reset()
                os.environ["CLOSE_TRUTH"] = os.environ["CLOSE_ACCRUAL"] = "1"
                b = Bridge([rent_row()], closing=cu)
                card = ret_card(b)
                self.assertIn("доплаты не начисляю", card.text)
                self.assertNotIn("acc_op", S._RETURN_CLOSES[INTAKE])
                say(b, "да", reply=card)
                self.assertEqual(b.red("post_close_booking"), [])

    def test_s11_empty_and_text_k_words(self):
        for base, k, word in (("empty", "", "основная сумма в K не подтверждена (K пуст) — K не трогал"),
                              ("text", "оплатил", "В K не целое число — K не трогал")):
            with self.subTest(base=base):
                reset()
                os.environ["CLOSE_TRUTH"] = os.environ["CLOSE_ACCRUAL"] = "1"
                b = Bridge([rent_row()], post_reply=lambda f, base=base, k=k: {
                    "ok": True, "row": 21, "accrual": receipt(f["accrual"]["close_op_id"], base=base, k=k,
                                                              k_written=False, note="NOTE_ONLY")})
                card = ret_card(b)
                say(b, "да", reply=card)
                self.assertIn(word, texts()[-1])
                self.assertNotIn("Начислено к оплате (это не оплата): K =", texts()[-1])

    def test_s12_photo_only_rules_hold(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        self.assertIn(ACC_LINE, card.text)
        self.assertTrue(card.text.endswith("Завершаю (Завершена + пробег из ответа + начисление доплат)? "
                                           "да <пробег> / нет"), card.text)
        say(b, "да", reply=card)
        self.assertEqual(b.red("post_close_booking"), [], "фото-пробег без числа — моста не зовём")
        self.assertEqual(b.tickets, 0)
        say(b, "да 35210", reply=card)
        self.assertEqual(b.red("post_close_booking"), [exp_payload(km="35210")])

    def test_s13_two_operators_one_call(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        say(b, "да", reply=card, uname=APPROVER)
        say(b, "да", reply=card, uname=APPROVER2)
        self.assertEqual(len(b.red("post_close_booking")), 1, "второй оператор той же карточки — без вызова")
        self.assertEqual(len(b.red("close_booking")), 0)

    def test_s14_repeat_return_keeps_operation(self):
        """Повтор возврата, пока карточка ждёт: карточка не дублируется и операция прежняя (не чеканим новую)."""
        b = Bridge([rent_row()])
        ret_card(b)
        op = S._RETURN_CLOSES[INTAKE]["acc_op"]
        b.closing = closing_reply(parts={"other": "300"})
        run(S._return_close_card(Ctx(), b, BIKE, km="35200", total_due=1800, closing=b.closing))
        self.assertEqual(len(cards()), 1)
        self.assertEqual(S._RETURN_CLOSES[INTAKE]["acc_op"], op)


# ============================================================================================ (R) рестарт: та же операция
def restart_process():
    S.handoff_write()
    for d in (S._INTAKE_DRAFTS, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES):
        d.clear()
    for name in ("_CR_NOTES", "_CR_FORGOT", "_IC_DEAD_ASKS"):
        getattr(S, name, {}).clear()
    S._HANDOFF_SEEN.update(applied_sha=None, unapplied=False, carry=[])
    time.sleep(0.05)
    S._CR_LIFE_T0 = time.time()
    out = S.handoff_restore()
    assert out.startswith("применена"), out


class R_Restart(Case):
    def test_r1_restored_card_executes_same_operation(self):
        b = Bridge([rent_row()])
        ret_card(b, km="", km_photo="35200")
        before = {k: v for k, v in S._RETURN_CLOSES[INTAKE].items() if k.startswith("acc_") or k in ("km_photo",
                                                                                                     "due_total")}
        restart_process()
        rec = S._RETURN_CLOSES[INTAKE]
        self.assertEqual({k: rec.get(k) for k in before}, before, "операция и подсказки пережили рестарт")
        say(b, "да")                                         # без реплая: адресное уточнение по ждущей карточке
        self.assertEqual(b.red("post_close_booking"), [])
        asks = [s for s in SENDS if "засчитываю только реплаем" in s.text]
        self.assertTrue(asks, texts())
        say(b, "да 35210", reply=asks[-1])
        self.assertEqual(b.red("post_close_booking"), [exp_payload(km="35210")], "та же операция, не новая")

    def test_r2_handoff_whitelist_roundtrip(self):
        b = Bridge([rent_row()])
        ret_card(b)
        e = RH.select({}, {}, {INTAKE: S._RETURN_CLOSES[INTAKE]})
        obj = RH.pack(e, written_at=1.0, pid=7)
        got, why = RH.verify(obj)
        self.assertEqual(why, "ok")
        d = got[0]["data"]
        for k in ("acc_op", "acc_bid", "acc_brow", "acc_ds", "acc_crow", "acc_parts", "km_photo", "due_total"):
            self.assertIn(k, d)
        self.assertEqual(d["acc_parts"], ["500", "", "1000", ""])

    def test_r3_tampered_restored_card_not_sent(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        S._RETURN_CLOSES[INTAKE]["acc_parts"] = ["900", "", "1000", ""]   # запись разошлась со своей операцией
        say(b, "да", reply=card)
        self.assertEqual(b.red("post_close_booking"), [])
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21. Доплаты не записаны: поля начисления карточки "
                                          "не сошлись с её операцией.")


# ============================================================== (L) ручка ВКЛ, прежний путь ответа (STRICT=0)
class L_OnLegacyReply(Case):
    def setUp(self):
        super(L_OnLegacyReply, self).setUp()
        os.environ["INTAKE_CONFIRM_STRICT"] = "0"

    def test_l1_payload_and_receipt(self):
        b = Bridge([rent_row()])
        ret_card(b)
        say(b, "да")
        self.assertEqual(b.red("post_close_booking"), [exp_payload()])
        self.assertIn("Начислено к оплате (это не оплата): K = =10000+500+1000", texts()[-1])

    def test_l2_write_failed_unknown_accrual(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": False, "error": "write_failed", "message": "x"})
        ret_card(b)
        say(b, "да")
        self.assertTrue(texts()[-1].endswith(S._ACC_UNKNOWN), texts()[-1])

    def test_l3_old_bridge_no_receipt(self):
        b = Bridge([rent_row()], post_reply=lambda f: {"ok": True, "closed": True, "row": 21})
        ret_card(b)
        say(b, "да")
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21." + S._ACC_NO_RECEIPT)


# ============================================================================== (K) ручка ВКЛ, дело К4 (хранилище)
class K_OnCaseStore(Case):
    def setUp(self):
        super(K_OnCaseStore, self).setUp()
        os.environ["RENTAL_CASE_APPROVALS"] = "1"
        import rental_case
        d = tempfile.mkdtemp(prefix="closeaccrual_k4_%s_" % self._testMethodName[5:20], dir=TTMP)
        p = os.path.join(d, "rental_case.sqlite")
        rental_case.Store.create(p)
        os.environ["RENTAL_CASE_DB"] = p

    def k4(self, b, text, reply):
        return say(b, text, reply=reply, uname=OWNER, uid=OWNER_ID)

    def test_k1_card_and_payload(self):
        b = Bridge([rent_row()])
        card = ret_card(b)
        self.assertIn(ACC_LINE, card.text)
        self.assertIn("РЕПЛАЕМ", card.text)
        self.k4(b, "да", card)
        self.assertEqual(b.red("post_close_booking"), [exp_payload()])
        self.assertTrue(any(t.startswith(P + "✅ Завершена, строка 21. Начислено к оплате (это не оплата)")
                            for t in texts()), texts())

    def test_k2_new_card_carries_same_operation(self):
        b = Bridge([rent_row()])
        card = ret_card(b, km="", km_photo="35200")
        self.k4(b, "да", card)
        self.assertEqual(b.red("post_close_booking"), [])
        again = cards()[-1]
        self.assertIn(ACC_LINE, again.text)
        self.k4(b, "да 35300", again)
        self.assertEqual(b.red("post_close_booking"), [exp_payload(km="35300")])

    def test_k3_unknown(self):
        def boom(f):
            raise ConnectionError("reset")
        b = Bridge([rent_row()], post_reply=boom)
        card = ret_card(b)
        self.k4(b, "да", card)
        self.assertTrue(any(t.endswith(S._ACC_UNKNOWN) and "Исход закрытия неизвестен" in t for t in texts()), texts())


# ============================================ (E) сквозной: Splinter → НАСТОЯЩИЕ Closing.js / closeBooking сборки (node)
def _grid(k=10000, note="выдал, шлем 1", closing_bid=BID, q="35000 Km, 05.07.2026"):
    row = ["В аренде", "OFF", BIKE, NAME, dt(-3), dt(2)] + [""] * 19
    row[10], row[16], row[24] = k, q, BID
    grid = [["СТАТУС", "AUTO CNCL", "Название мото", "Имя", "Дата начала", "Дата завершения"]]
    grid += [[""] * 6 for _ in range(19)]            # строки 2..20 пусты: аренда — строка 21, как у двери clients
    grid.append(row)
    crm = {"grid": grid, "formulas": {}, "fvals": {}, "notes": {"21,1": note} if note else {}}
    closing = {"grid": [["booking_id", "bike", "name", "date_return", "fuel_level", "surcharge_days", "surcharge_fuel",
                         "damage", "other", "total_due", "deposit_action", "status", "note", "updated_at"],
                        [closing_bid, BIKE, NAME, "", "", "500", "", "1000", "", 1500, "", "open", "", ""]]}
    return crm, closing


class JSBridge(Bridge):
    """Мост, чьи closing_upsert и close_booking исполняет НАСТОЯЩИЙ код сборки (node --stdin), листы — в памяти."""

    def __init__(self, rows, crm, closing):
        super(JSBridge, self).__init__(rows)
        self.crm, self.closing_sheet = crm, closing

    def _js(self, call, body):
        out = node({"mode": "call", "call": call, "body": body, "crm": self.crm, "closing": self.closing_sheet})
        self.crm, self.closing_sheet = out["crm"], out["closing"]
        return out["res"]

    def closing_upsert(self, **k):
        self.calls.append(("closing_upsert", dict(k)))
        return self._js("closing_upsert", k)

    def close_booking(self, bike, name, date_start=None, km_end=None, paid_total=None):
        self.calls.append(("close_booking", {"bike": bike, "name": name, "date_start": date_start, "km_end": km_end,
                                             "paid_total": paid_total}))
        body = {"bike": bike, "name": name}                 # как bridge_client: опциональные — только при наличии
        if date_start:
            body["date_start"] = date_start
        if km_end is not None:
            body["km_end"] = km_end
        if paid_total is not None:
            body["paid_total"] = paid_total
        return self._js("close_booking", body)

    def _post(self, action, **fields):
        assert action == "close_booking", action
        self.calls.append(("post_close_booking", dict(fields)))
        return self._js("close_booking", fields)


RET_PARSE = {"type": "event", "event_type": "return", "bike": BIKE, "fuel": "полный", "mileage": "35 300", "works": []}


def do_return(b):
    S.set_topic_bike(SERV, TOPIC, BIKE)
    m = Msg("вернул байк, принял", uname="mechanic_test", chat_id=SERV, topic=TOPIC, photo=False)
    run(S._handle_servicing(m, Ctx(), b, FakeClaude(RET_PARSE, {})))


class E_EndToEnd(Case):
    def test_e1_number_base_formula_and_note(self):
        crm, closing = _grid()
        b = JSBridge([rent_row()], crm, closing)
        do_return(b)
        cs = cards()
        self.assertEqual(len(cs), 1, texts())
        self.assertIn(ACC_LINE, cs[0].text)
        say(b, "да", reply=cs[0])
        self.assertEqual(len(b.red("post_close_booking")), 1)
        row = b.crm["grid"][20]
        self.assertEqual(row[0], "Завершена")
        self.assertEqual(row[13], 35300)
        self.assertEqual(b.crm["formulas"].get("21,11"), "=10000+500+1000", "K — основа + доплаты формулой")
        note = b.crm["notes"]["21,1"]
        op = S._RETURN_CLOSES[INTAKE]["acc_op"]
        self.assertTrue(note.startswith("выдал, шлем 1\n[TB %s DONE +500+1000] доплаты (начислено к оплате, "
                                        "не оплата): дни 500 · ущерб 1000; K было: 10000 → =10000+500+1000" % op), note)
        self.assertEqual(texts()[-1], P + "✅ Завершена, строка 21. Начислено к оплате (это не оплата): "
                                          "K = =10000+500+1000 — основная сумма + доплаты дни 500 · ущерб 1000; "
                                          "расшифровка — в примечании к A.")
        say(b, "да", reply=cs[0])
        self.assertEqual(len(b.red("post_close_booking")), 1, "второе «да» — без вызова")

    def test_e2_empty_k_note_only(self):
        crm, closing = _grid(k="", note="")
        b = JSBridge([rent_row()], crm, closing)
        do_return(b)
        say(b, "да", reply=cards()[-1])
        self.assertEqual(b.crm["grid"][20][10], "", "пустой K — не доказанный ноль: K не трогаем")
        self.assertNotIn("21,11", b.crm["formulas"])
        self.assertIn("основная сумма не подтверждена (K пуст)", b.crm["notes"]["21,1"])
        self.assertIn("основная сумма в K не подтверждена (K пуст) — K не трогал", texts()[-1])

    def test_e3_bike_fallback_row_stops_before_any_write(self):
        crm, closing = _grid(closing_bid="")           # строка листа без booking_id — найдётся только по байку
        b = JSBridge([rent_row(booking_id="")], crm, closing)
        b.crm["grid"][20][24] = ""
        do_return(b)
        card = cards()[-1]
        self.assertIn("доплаты не начисляю", card.text)
        say(b, "да", reply=card)
        self.assertEqual(b.red("post_close_booking"), [])
        self.assertEqual(b.crm["grid"][20][0], "Завершена", "само закрытие идёт")
        self.assertEqual(b.crm["grid"][20][10], 10000, "K не тронут")
        self.assertEqual(b.crm["notes"].get("21,1"), "выдал, шлем 1", "примечание не тронуто")
        self.assertIn("Доплаты не записаны:", texts()[-1])

    def test_e4_formula_base_grouped(self):
        crm, closing = _grid(k="")
        crm["formulas"]["21,11"] = "=H21*G21-500"
        crm["fvals"]["21,11"] = 9500
        b = JSBridge([rent_row()], crm, closing)
        do_return(b)
        say(b, "да", reply=cards()[-1])
        self.assertEqual(b.crm["formulas"]["21,11"], "=(H21*G21-500)+500+1000")


# ================================================================== (C) настоящий BridgeClient._post: тело запроса
class C_RealClient(Case):
    def test_c1_body_has_accrual_agent_ticket_no_paid(self):
        c = object.__new__(bridge_client.BridgeClient)
        c.token = "test-token-not-secret"
        sent = []
        c._durable_request = lambda method, action, body=None, retry_full=False: (
            sent.append((method, action, dict(body), retry_full)) or {"ok": True, "row": 21})
        c._blackbox_log = lambda *a, **k: None
        pl = exp_payload()
        with bridge_client.agent_write("t-real"):
            res = S._close_booking_accrual(c, bike=BIKE, name=NAME, date_start=dt(-3), km_end="35200",
                                           accrual=pl["accrual"])
        self.assertEqual(res, {"ok": True, "row": 21})
        self.assertEqual(len(sent), 1)
        method, action, body, retry = sent[0]
        self.assertEqual((method, action, retry), ("POST", "close_booking", False), "запись — без полного повтора")
        self.assertEqual(body["origin"], "agent")
        self.assertEqual(body["ticket"], "t-real")
        self.assertEqual(body["accrual"], pl["accrual"])
        self.assertNotIn("paid_total", body)
        self.assertNotIn("paid_total_opt_in", body)
        self.assertEqual({k: body[k] for k in ("bike", "name", "date_start", "km_end")},
                         {"bike": BIKE, "name": NAME, "date_start": dt(-3), "km_end": "35200"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
