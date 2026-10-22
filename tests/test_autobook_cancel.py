"""A1AUTOCANCEL2210 (22.10.2026, интеграция К3): синтетика пакета A1 на НАСТОЯЩИХ autobook_cancel.py и bridge_client.py (в пакете — вырезка).

Ответы моста — снятые в пакете A1 ответы cancelBooking/createBooking на подставном листе
(в пакете — ответы `src/bridge_prod/Booking.js` под `tests/test_booking_cancel.js`; копия — tests/fixtures/a1_bridge_responses.json). Identities are synthetic.
No network, no real sheet, no Telegram. Run: python3 -B -m unittest tests/test_autobook_cancel.py -v
"""
import asyncio
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import autobook_cancel as A  # noqa: E402
import bridge_client as BC  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "a1_bridge_responses.json"), encoding="utf-8") as _f:
    FIX = json.load(_f)

CHAT, TOPIC, BOT = -100500, 77, 9000
APPROVERS = {"synth_owner", "synth_manager"}


class U:
    def __init__(self, uid, username, is_bot=False):
        self.id, self.username, self.is_bot = uid, username, is_bot


class M:
    def __init__(self, mid, text="", user=None, reply=None, chat=CHAT, tid=TOPIC):
        self.message_id, self.text, self.from_user, self.reply_to_message = mid, text, user, reply
        self.chat_id, self.message_thread_id = chat, tid


OWNER, MANAGER, STRANGER = U(1001, "synth_owner"), U(1002, "synth_manager"), U(1003, "synth_random")
BOTU = U(BOT, "splinter_bot", is_bot=True)


def can_approve(msg):  # same rule shape as splinter._intake_can_approve, synthetic list
    u = msg.from_user
    return bool(u and u.username and u.username.lower() in APPROVERS)


class FakeBridge:
    """Records every mutating call with the origin/ticket visible inside agent_write (real BC.agent_write)."""

    def __init__(self, replies=(), readbacks=(), ticket="t-synth", has_readback=True):
        self.replies, self.readbacks, self.ticket = list(replies), list(readbacks), ticket
        self.cancels, self.reads, self.tickets, self.hook = [], [], 0, None
        if not has_readback:
            self.booking_by_id = None

    def issue_write_ticket(self):
        self.tickets += 1
        return {"ok": True, "ticket": self.ticket} if self.ticket else {"ok": False, "error": "ticket_failed"}

    def cancel_booking(self, booking_id, by, row_hint=None, expect=None):
        self.cancels.append(dict(booking_id=booking_id, by=by, row_hint=row_hint, expect=expect,
                                 origin=BC.WRITE_ORIGIN.get(), ticket=BC.WRITE_TICKET.get()))
        if self.hook:
            self.hook()
        r = self.replies.pop(0)
        if isinstance(r, BaseException):
            raise r
        return copy.deepcopy(r)

    def booking_by_id(self, booking_id):
        self.reads.append(booking_id)
        r = self.readbacks.pop(0) if self.readbacks else {"ok": False, "error": "unknown_action"}
        if isinstance(r, BaseException):
            raise r
        return copy.deepcopy(r)


class Base(unittest.TestCase):
    def setUp(self):
        self.store, self.said = A.MemoryStore(), []
        self.ok_msg = M(5555, "✅ Бронь записана автоматически, строка 2 …", BOTU)

    async def _say(self, body):
        self.said.append(body)

    def reg(self, res=None, store=None):
        res = res or FIX["booking_a"]
        self.assertTrue(A.register_booked(store or self.store, chat_id=CHAT, thread_id=TOPIC, message=self.ok_msg,
                                          res=res, bot_id=BOT, now=1.0))
        return res

    def reply(self, br, text="отмена", user=OWNER, mid=7001, target=None, store=None, **kw):
        msg = M(mid, text, user, target or self.ok_msg, **kw)
        return asyncio.run(A.handle_reply(msg, text, store=store or self.store, bridge=br, say=self._say,
                                          can_approve=can_approve, chat_is_intake=lambda c: c == CHAT,
                                          agent_write=BC.agent_write, bot_id=BOT,
                                          forwarded=lambda m: getattr(m, "forward_origin", None) is not None))

    def rec(self, store=None):
        return (store or self.store).get("%s:%s" % (CHAT, self.ok_msg.message_id))


class T1_Authorized(Base):
    def test_owner_reply_cancels_exactly_once_bound_to_uuid(self):
        res = self.reg()
        br = FakeBridge([FIX["cancelled"]])
        r = self.reply(br)
        self.assertEqual(r["outcome"], A.CANCELLED)
        self.assertEqual(len(br.cancels), 1)
        c = br.cancels[0]
        self.assertEqual(c["booking_id"], res["booking_id"])
        self.assertEqual(c["by"], "tg:1001 @synth_owner")          # from the Telegram update, not from text
        self.assertEqual((c["origin"], c["ticket"]), ("agent", "t-synth"))
        self.assertEqual(c["row_hint"], res["row"])
        self.assertEqual(c["expect"], {"bike": res["bike"]})
        self.assertEqual(br.reads, [])                               # verified in-response; no extra read needed
        self.assertEqual((r["requested"], r["received"], r["applied"], r["readback"]), (True, True, True, "bridge_reread"))
        self.assertEqual(self.rec()["state"], "cancelled")
        self.assertEqual(self.rec()["last"]["status_before"], "Бронь")
        self.assertEqual(self.rec()["last"]["status_after"], "Отмена")
        self.assertIn("Автобронь отменена", self.said[-1])
        self.assertNotIn("name", self.rec())                        # store keeps no client name

    def test_manager_allowed(self):
        self.reg()
        br = FakeBridge([FIX["cancelled"]])
        self.assertEqual(self.reply(br, user=MANAGER)["outcome"], A.CANCELLED)

    def test_repeated_event_and_second_reply_do_not_call_again(self):
        self.reg()
        br = FakeBridge([FIX["cancelled"]])
        self.reply(br, mid=7001)
        r2 = self.reply(br, mid=7001)                                # same update redelivered
        self.assertEqual(r2["outcome"], "duplicate_event")
        r3 = self.reply(br, mid=7002)                                # new human reply after success
        self.assertEqual(r3["outcome"], A.ALREADY)
        self.assertEqual(len(br.cancels), 1)
        self.assertEqual(br.tickets, 1)

    def test_bridge_already_requires_same_uuid_and_marker(self):
        self.reg()
        self.assertEqual(self.reply(FakeBridge([FIX["already"]]))["outcome"], A.ALREADY)
        bad = copy.deepcopy(FIX["already"])
        bad["readback"]["cancel_marked"] = False
        self.assertEqual(A.cancel_outcome(bad, True, FIX["booking_a"]["booking_id"]), A.UNKNOWN)


class T2_Unauthorized(Base):
    def assertNoCall(self, br, r, handled):
        self.assertEqual(br.cancels, [])
        self.assertEqual(br.tickets, 0)
        self.assertEqual(r["handled"], handled)
        self.assertEqual(self.rec()["state"], "booked")

    def test_refusals(self):
        self.reg()
        fwd = M(7010, "отмена", OWNER, self.ok_msg)
        fwd.forward_origin = object()
        cases = [dict(user=STRANGER), dict(user=U(1001, None)), dict(user=U(1004, "synth_owner", is_bot=True)),
                 dict(user=None), dict(tid=78), dict(chat=-100999)]
        for kw in cases:
            br = FakeBridge([FIX["cancelled"]])
            r = self.reply(br, **kw)
            self.assertNoCall(br, r, kw.get("chat") is None)
        br = FakeBridge([FIX["cancelled"]])
        r = asyncio.run(A.handle_reply(fwd, "отмена", store=self.store, bridge=br, say=self._say,
                                       can_approve=can_approve, chat_is_intake=lambda c: c == CHAT,
                                       agent_write=BC.agent_write, bot_id=BOT,
                                       forwarded=lambda m: getattr(m, "forward_origin", None) is not None))
        self.assertNoCall(br, r, True)
        self.assertEqual(self.said, [])

    def test_forged_lookalike_message_and_row_number_grant_nothing(self):
        self.reg()
        forged = M(6666, "✅ Бронь записана автоматически, строка 2, статус «Бронь».", STRANGER)
        fake_bot = M(5555, "✅ Бронь записана автоматически, строка 2", U(4242, "evil_bot", is_bot=True))
        for target in (forged, M(6667, "строка 2", BOTU)):
            br = FakeBridge([FIX["cancelled"]])
            r = self.reply(br, target=target)
            self.assertEqual((r["handled"], br.cancels), (False, []))
        br = FakeBridge([FIX["cancelled"]])
        r = self.reply(br, target=fake_bot)                          # same id, but author is not our bot
        self.assertEqual((r["outcome"], br.cancels), ("refused", []))
        for txt in ("отмена by @synth_owner", "отмена строки 2", "отмена?", "отмена не нужна", "нет"):
            br = FakeBridge([FIX["cancelled"]])
            r = self.reply(br, text=txt)
            self.assertEqual((r["handled"], br.cancels), (False, []), txt)
        self.assertEqual(self.rec()["state"], "booked")


class T3_NonAutoRaceIdentity(Base):
    def test_manual_booking_message_not_registered(self):
        br = FakeBridge([FIX["cancelled"]])                          # nothing registered (manual «да» booking)
        r = self.reply(br)
        self.assertEqual((r["handled"], br.cancels), (False, []))

    def test_bridge_not_auto_and_status_race_and_changed(self):
        for key in ("not_auto", "not_eligible", "booking_changed", "cancelled_elsewhere", "booking_not_found",
                    "ambiguous"):
            self.setUp()
            f = FIX[key]
            self.reg({"booking_id": f["booking_id"], "row": f.get("row", 2), "bike": "NMAX 155CC TEST 0001"})
            br = FakeBridge([f])
            r = self.reply(br)
            self.assertEqual(r["outcome"], A.NOT_CANCELLED, key)
            self.assertEqual(len(br.cancels), 1, key)
            self.assertEqual(br.reads, [], key)
            self.assertEqual(self.rec()["state"], "not_cancelled", key)
            self.assertIn("НЕ отменена (%s)" % key, self.said[-1])

    def test_row_moved_cancel_follows_uuid(self):
        self.reg()
        br = FakeBridge([FIX["cancelled_moved"]])
        r = self.reply(br)
        self.assertEqual(r["outcome"], A.CANCELLED)
        self.assertEqual(br.cancels[0]["row_hint"], FIX["booking_a"]["row"])
        self.assertEqual(self.rec()["last"]["row"], FIX["booking_a"]["row"] + 1)
        self.assertIn("строка %d" % (FIX["booking_a"]["row"] + 1), self.said[-1])

    def test_ok_alone_or_other_uuid_is_not_cancellation(self):
        bid = FIX["booking_a"]["booking_id"]
        other = copy.deepcopy(FIX["cancelled"])
        other["booking_id"] = other["readback"]["booking_id"] = "00000000-0000-4000-8000-0000000000aa"
        for res in ({"ok": True}, {"ok": True, "saved": True, "row": 2}, other,
                    dict(FIX["cancelled"], status_before="В аренде"), dict(FIX["cancelled"], applied=None),
                    dict(FIX["not_auto"], booking_id="00000000-0000-4000-8000-0000000000aa")):
            self.assertEqual(A.cancel_outcome(res, True, bid), A.UNKNOWN, res)
        self.assertEqual(A.cancel_outcome(FIX["cancelled"], True, bid), A.CANCELLED)


class T4_DoorRefusal(Base):
    def test_door_off_lock_busy_no_ticket(self):
        for key in ("door_off", "lock_busy", "no_ticket"):
            self.setUp()
            self.reg()
            br = FakeBridge([FIX[key]])
            self.assertEqual(self.reply(br)["outcome"], A.NOT_CANCELLED, key)
            self.assertEqual(len(br.cancels), 1)
            self.assertEqual(self.rec()["state"], "not_cancelled")

    def test_ticket_not_issued_sends_nothing(self):
        self.reg()
        br = FakeBridge([FIX["cancelled"]], ticket=None)
        r = self.reply(br)
        self.assertEqual((r["outcome"], r["requested"], br.cancels), (A.NOT_CANCELLED, False, []))
        self.assertIn("no_ticket", self.said[-1])


class T5_UnknownNoRetry(Base):
    def test_timeout_then_readback_then_reconcile_without_second_cancel(self):
        self.reg()
        br = FakeBridge([TimeoutError("synthetic")], readbacks=[FIX["readback_booked"], FIX["readback_cancelled"]])
        r = self.reply(br, mid=7001)
        self.assertEqual(r["outcome"], A.UNKNOWN)
        self.assertEqual((r["requested"], r["received"], r["readback"]), (True, False, "not_seen"))
        self.assertEqual(self.rec()["state"], "unknown")
        self.assertIn("Исход отмены неизвестен", self.said[-1])
        self.assertIn("Повторно не отправляю", self.said[-1])
        r2 = self.reply(br, mid=7002)                                # human asks again → read only
        self.assertEqual(r2["outcome"], A.CANCELLED)
        self.assertEqual(r2["readback"], "verified")
        self.assertEqual(len(br.cancels), 1)                         # never a second mutating call
        self.assertEqual(br.tickets, 1)
        self.assertEqual(br.reads, [FIX["booking_a"]["booking_id"]] * 2)
        self.assertEqual(self.rec()["state"], "cancelled")

    def test_write_failed_and_readback_mismatch_stay_unknown(self):
        for res, rbs in ((FIX["write_failed"], [FIX["readback_booked"]]),
                         (FIX["write_failed"], [ConnectionError("x")]),
                         ({"ok": False, "outcome": "unknown", "error": "timeout"}, []),
                         (None, [])):
            self.setUp()
            self.reg()
            br = FakeBridge([res], readbacks=rbs)
            r = self.reply(br)
            self.assertEqual(r["outcome"], A.UNKNOWN, res)
            self.assertEqual(len(br.cancels), 1)
            for mid in (7101, 7102):
                self.reply(br, mid=mid)
            self.assertEqual(len(br.cancels), 1, "no blind retry")
            self.assertEqual(self.rec()["state"], "unknown")

    def test_no_readback_api_is_explicitly_unknown(self):
        self.reg()
        br = FakeBridge([TimeoutError("synthetic")], has_readback=False)
        r = self.reply(br)
        self.assertEqual((r["outcome"], r["readback"]), (A.UNKNOWN, "unavailable"))


class T6_DurableStore(Base):
    def test_write_ahead_and_restart_reconciles_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "ab_cancel.json")
            st = A.JsonFileStore(path)
            self.reg(store=st)
            seen = []
            br = FakeBridge([TimeoutError("synthetic")])
            br.hook = lambda: seen.append(A.JsonFileStore(path).get("%s:5555" % CHAT)["state"])
            self.reply(br, store=st)
            self.assertEqual(seen, ["cancel_requested"])            # persisted BEFORE the request was sent
            # simulate crash right after send: state left as cancel_requested, new process loads the file
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            raw["%s:5555" % CHAT]["state"] = "cancel_requested"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f)
            st2 = A.JsonFileStore(path)
            br2 = FakeBridge([FIX["cancelled"]], readbacks=[FIX["readback_booked"]])
            r = self.reply(br2, mid=7200, store=st2)
            self.assertEqual((r["outcome"], br2.cancels, br2.tickets), (A.UNKNOWN, [], 0))
            self.assertEqual(sorted(os.listdir(td)), ["ab_cancel.json"])  # no temp leftovers

    def test_register_rejects_row_only_or_bad_uuid(self):
        for res in ({"row": 2}, {"booking_id": "2", "row": 2}, {"booking_id": None}, None):
            self.assertFalse(A.register_booked(self.store, chat_id=CHAT, thread_id=TOPIC, message=self.ok_msg,
                                               res=res))
        self.assertFalse(A.register_booked(self.store, chat_id=CHAT, thread_id=TOPIC, message=None,
                                           res=FIX["booking_a"]))


class T7_KnobTextClient(unittest.TestCase):
    def test_knob_default_off(self):
        for v in (None, "", "0", "off", "нет", "false", "2"):
            self.assertFalse(A.cancel_on(v), v)
        for v in ("1", "on", "ДА", " true "):
            self.assertTrue(A.cancel_on(v), v)

    def test_cancel_words(self):
        for t in ("отмена", "Отмена!", "ОТМЕНИТЬ.", "cancel", " отмена "):
            self.assertTrue(A.is_cancel_text(t), t)
        for t in ("", None, "отмена?", "отмена не нужна", "не отмена", "отмена брони 2", "да", "нет"):
            self.assertFalse(A.is_cancel_text(t), t)

    def test_off_text_unchanged_in_patched_splinter(self):
        """Чтение исходника (не исполнение) НАСТОЯЩЕГО splinter.py: ветка без хранилища держит прежний текст успеха, хранилище
        создаётся только при ручке, ручка — только поверх INTAKE_AUTOBOOK."""
        with open(os.path.join(ROOT, "splinter.py"), encoding="utf-8") as f:
            new = f.read()
        line = ('f"Согласовано {price_w} ฿{door_w}. Отменить: пока вручную в CRM (строка {_row}); «отмена» реплаем — "\n'
                '                      "со следующим выпуском моста.")')
        self.assertIn(line, new)
        self.assertIn("if _abc is None:", new)
        self.assertIn("if _AB_CANCEL_STORE is None and _intake_autobook_cancel_on():", new)
        self.assertIn('return _intake_autobook_on() and autobook_cancel.cancel_on(_os_env("INTAKE_AUTOBOOK_CANCEL", "0"))',
                      new)

    def test_client_cancel_is_non_retry_post_under_token_lock(self):
        calls = []

        class C(BC.BridgeClient):
            token = "synthetic-token"

            def _durable_request(self, method, action, params=None, body=None, retry_full=False):
                calls.append((method, action, params, body, retry_full))
                return {"ok": True}

            def _blackbox_log(self, action, fields, data):                # чёрный ящик 4.1 — мимо сети в тесте
                pass

        c = C.__new__(C)                                                  # без __init__: ни окружения, ни сети
        self.assertIn("cancel_booking", BC.BridgeClient._REDZONE_ACTIONS)
        self.assertNotIn("cancel_booking", C._IDEMPOTENT_POST_ACTIONS)
        with BC.agent_write("t-1"):
            c.cancel_booking("00000000-0000-4000-8000-000000000001", by="tg:1 @x", row_hint=2, expect={"bike": "B"})
        c.booking_by_id("00000000-0000-4000-8000-000000000001")
        m, a, _, body, retry = calls[0]
        self.assertEqual((m, a, retry), ("POST", "cancel_booking", False))
        self.assertEqual((body["origin"], body["ticket"], body["booking_id"], body["row_hint"], body["expect"]),
                         ("agent", "t-1", "00000000-0000-4000-8000-000000000001", 2, {"bike": "B"}))
        self.assertEqual(calls[1][:2], ("GET", "booking_by_id"))
        self.assertTrue(calls[1][4])                                 # GET read-only; full retry is safe
        c.cancel_booking("00000000-0000-4000-8000-000000000001", by="h")
        self.assertEqual(calls[2][3]["origin"], "human")              # outside agent_write: no ticket attached
        self.assertNotIn("ticket", calls[2][3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
