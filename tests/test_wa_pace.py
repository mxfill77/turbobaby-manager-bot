#!/usr/bin/env python3
"""Человеческий ритм «Отправить» (WAHUMANPACE0210): первый ответ беседы — не раньше случайных 3–5 мин после
сообщения клиента; следующий — по длине текста минус время с сообщения клиента, не меньше нуля; раньше
срока — отложено в базе («уйдёт в ЧЧ:ММ», «Отменить»), позже — сразу; рестарт не теряет и не дублирует;
выключатель WA_AGENT_PACE по умолчанию выключен; текст человека из темы ритм не касается.
Всё на подделках: временная очередь схемой wa_webhook, временная база агента, модель/Telegram/дверь —
подделки из test_wa_agent, test_wa_agent_tg и test_wa_agent_svc. Сети нет.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import hashlib
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import test_wa_agent as TA  # noqa: E402
import test_wa_agent_tg as TG  # noqa: E402
import test_wa_agent_svc as TS  # noqa: E402

NUM, T0 = TA.NUM, TA.T0
LONG = "x" * 349                     # FakeModel допишет « 1»: 351 знак → набор 351 / 1.75 = 200.6 с


class PaceTG(TA.FakeTG):
    def __init__(self):
        super().__init__()
        self.waits = []

    def card_wait(self, draft_id, card_id, words, ver):
        self.waits.append((draft_id, words, ver))


class PaceWorld(TA.World):
    """Мир test_wa_agent с ритмом: pace — выключатель ядра, r — доля окна первого ответа (вместо random)."""

    def __init__(self, pace=True, r=0.5, quiet=A.QUIET_MIN, greet=(), **kw):
        self.pace, self.r, self.quiet, self.greet = pace, r, quiet, greet
        super().__init__(**kw)
        self.tg = PaceTG()
        self.core.tg = self.tg

    def new_core(self):
        return A.Core(self.dbpath, self.qpath, self.model, getattr(self, "tg", None) or PaceTG(), self.door,
                      quiet=self.quiet, pace=self.pace, rand=lambda: self.r, greet=self.greet)

    def restart(self):
        self.core.db.close()
        self.core = self.new_core()

    def due(self, did):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT due_at FROM drafts WHERE id=?", (did,)).fetchone()
        db.close()
        return row[0]


def draft_at(w, ts=T0):
    """Сообщение клиента в ts, черновик через паузу тишины (60 с — QUIET_MIN)."""
    w.put(ts)
    w.core.tick(ts + w.quiet)
    d = w.drafts(A.PENDING)
    assert len(d) == 1, d
    return d[0][0]


def chat_before(gap=900):
    """История переписки до службы: клиент, наш ответ с телефона; беседа идёт (тишина < 4 ч)."""
    return [(T0 - gap - 100, "in"), (T0 - gap, "echo")]


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_first_press_minute1_goes_at_3_5():
    for r, want in ((0.0, 180), (0.5, 240), (0.999, 299)):
        w = PaceWorld(r=r)
        did = draft_at(w)                                     # черновик на 60-й секунде
        res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
        assert res["ok"] and res["state"] == A.SCHEDULED, res
        assert res["words"].startswith("уйдёт в "), res
        assert w.door.sends == [], "ушло на 1-й минуте"
        due = w.due(did)
        assert int(due - T0) == want and 180 <= due - T0 < 300, (r, due - T0)
        assert w.tg.waits and w.tg.waits[0][0] == did and "уйдёт в" in w.tg.waits[0][1], w.tg.waits
        w.core.tick(due - 1)
        assert w.door.sends == [], "ушло раньше срока"
        w.core.tick(due)
        assert w.door.sends == [(NUM, "черновик 1")], w.door.sends
        assert w.drafts()[0][1] == A.SENT and w.drafts()[0][4] == "owner", w.drafts()


def test_press_minute10_immediate():
    w = PaceWorld()
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 600)
    assert res["state"] == A.SENT and len(w.door.sends) == 1, (res, w.door.sends)
    assert w.tg.waits == [], w.tg.waits


def test_long_second_reply_waits_by_length():
    w = PaceWorld(model=TA.FakeModel(text=LONG), pre=chat_before())
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)
    assert res["state"] == A.SCHEDULED, res
    due = w.due(did)
    assert abs(due - (T0 + 351 / A.PACE_CPS)) < 0.01, due - T0      # 200.6 с от сообщения клиента
    w.core.tick(T0 + 200)
    assert w.door.sends == [], "ушло до конца набора"
    w.core.tick(T0 + 201)
    assert len(w.door.sends) == 1, w.door.sends


def test_short_second_reply_no_first_window():
    w = PaceWorld(pre=chat_before())
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)  # 10 знаков = 6 с набора < 61 с
    assert res["state"] == A.SENT and len(w.door.sends) == 1, res


def test_model_thought_longer_no_extra():
    w = PaceWorld(model=TA.FakeModel(text=LONG), pre=chat_before())
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 230)  # прошло 230 с > набора 200.6 с
    assert res["state"] == A.SENT and len(w.door.sends) == 1, res


def test_typing_ceiling():
    w = PaceWorld(model=TA.FakeModel(text="x" * 2000), pre=chat_before())
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)
    assert w.due(did) == T0 + A.PACE_TYPE_MAX, w.due(did) - T0


def test_long_silence_is_new_talk():
    w = PaceWorld(pre=chat_before(gap=5 * 3600))                   # тишина 5 ч > 4 ч — беседа новая
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)
    assert res["state"] == A.SCHEDULED and int(w.due(did) - T0) == 240, (res, w.due(did) - T0)


def test_autogreet_not_our_reply():
    fp = hashlib.sha256("x".encode("utf-8")).hexdigest()[:10]       # World.put пишет текст «x»
    w = PaceWorld(greet=(fp,))
    w.put(T0)
    w.put(T0 + 3, kind="echo")                                    # автоприветствие через 3 с
    w.core.tick(T0 + 10)
    did = draft_at(w, T0 + 20)                                    # клиент дописал через 20 с
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 81)
    assert res["state"] == A.SCHEDULED and int(w.due(did) - T0) == 240, (res, w.due(did) - T0)


def test_api_reply_is_ours():
    w = PaceWorld()
    w.core.relay(800, NUM, "здравствуйте", "owner", now=T0 - 200)  # наш ответ из темы — в outbox
    w.core.resume(NUM, 1, "owner", now=T0 - 100)
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)  # беседа идёт: следующий, 6 с набора
    assert res["state"] == A.SENT and len(w.door.sends) == 2, (res, w.door.sends)


def test_restart_before_due_one_send():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    due = w.due(did)
    w.restart()
    assert w.drafts()[0][1] == A.SCHEDULED, w.drafts()
    w.core.tick(due - 5)
    assert w.door.sends == [], w.door.sends
    w.restart()
    w.core.tick(due + 1)
    w.core.tick(due + 6)
    w.restart()
    w.core.tick(due + 11)
    assert len(w.door.sends) == 1 and w.drafts()[0][1] == A.SENT, (w.door.sends, w.drafts())


def test_restart_in_sending_unsure():
    w = PaceWorld(door=TA.FakeDoor(crash=True))
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    try:
        w.core.tick(w.due(did))
    except TA.Crash:
        pass
    w.door.crash = False
    w.restart()
    w.core.tick(w.due(did) + 60)
    assert len(w.door.sends) == 1 and w.drafts()[0][1] == A.UNSURE, (w.door.sends, w.drafts())


def test_cancel_nothing():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    res = w.core.press(did, 1, A.ACT_CANCEL, "mike", now=T0 + 100)
    assert res["ok"] and res["state"] == A.DECLINED, res
    w.core.tick(T0 + 1000)
    assert w.door.sends == [], w.door.sends
    again = w.core.press(did, 1, A.ACT_CANCEL, "owner", now=T0 + 101)
    assert not again["ok"] and "уже решено" in again["words"], again
    assert w.drafts()[0][4] == "mike", w.drafts()
    w.core.tick(T0 + 2000)
    assert w.drafts(A.PENDING) == [], "отмена родила новый черновик на те же сообщения"


def test_cancel_after_send_nothing_changes():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    w.core.tick(w.due(did))
    res = w.core.press(did, 1, A.ACT_CANCEL, "mike", now=T0 + 400)
    assert not res["ok"] and w.drafts()[0][1] == A.SENT and len(w.door.sends) == 1, (res, w.drafts())


def test_client_wrote_more_approved_goes_new_next():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    due = w.due(did)
    w.put(T0 + 100)                                               # клиент написал ещё до срока
    w.core.tick(T0 + 100 + w.quiet)
    new = w.drafts(A.PENDING)
    assert len(new) == 1 and new[0][0] != did, w.drafts()
    assert w.drafts()[0][1] == A.SCHEDULED, "одобренное снято новым сообщением"
    res = w.core.press(new[0][0], 1, A.ACT_SEND, "owner", now=T0 + 170)
    assert res["state"] == A.SCHEDULED and w.due(new[0][0]) >= due, (res, w.due(new[0][0]), due)
    w.core.tick(due)
    assert w.door.sends == [(NUM, "черновик 1")], w.door.sends
    w.core.tick(w.due(new[0][0]))
    assert w.door.sends == [(NUM, "черновик 1"), (NUM, "черновик 2")], w.door.sends


def test_phone_reply_before_due_not_sent():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    w.put(T0 + 120, kind="echo")                                  # человек ответил с телефона
    w.core.tick(w.due(did))
    assert w.door.sends == [] and w.drafts()[0][1] == A.SUPERSEDED, (w.door.sends, w.drafts())


def test_scheduled_goes_when_drafts_off():
    w = PaceWorld()
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    w.core.drafts = False                                         # WA_AGENT_DRAFTS выключили до срока
    w.core.tick(w.due(did))
    assert len(w.door.sends) == 1, w.door.sends


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_topic_text_immediate():
    w = PaceWorld()
    w.put(T0)
    w.core.tick(T0 + 10)
    res = w.core.relay(800, NUM, "привет", "owner", now=T0 + 20)  # на 20-й секунде — до любого срока
    assert res["outcome"] == "sent" and w.door.sends == [(NUM, "привет")], (res, w.door.sends)


def test_switch_off_immediate():
    w = PaceWorld(pace=False)
    did = draft_at(w)
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 60)
    assert res["state"] == A.SENT and len(w.door.sends) == 1 and w.tg.waits == [], res


def test_core_default_pace_off():
    w = TA.World()
    did = TA.one_draft(w)[0]
    res = w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + A.QUIET_DEFAULT)
    assert res["state"] == A.SENT and len(w.door.sends) == 1, res


# ═══ руки Telegram и служба ══════════════════════════════════════════════════════════════

def test_tg_card_wait_cancel_button():
    w = TG.World()
    w.core.pace, w.core.rand = True, (lambda: 0.5)
    w.draft()                                                     # карточка — сообщение 101
    w.core.clock = lambda: T0 + 80                                # нажатие на 80-й секунде
    w.feed(w.press("wa:send:1:1"))
    assert w.state()[0] == A.SCHEDULED and w.door.sends == [], (w.state(), w.door.sends)
    edits = w.http.of("editMessageText")
    assert edits and "уйдёт в" in edits[-1]["text"], edits
    kb = edits[-1]["reply_markup"]["inline_keyboard"]
    assert [b["callback_data"] for row in kb for b in row] == ["wa:cancel:1:1"], kb
    assert w.answers()[-1].startswith("уйдёт в"), w.answers()
    w.feed(w.press("wa:cancel:1:1", user=TG.HUMAN2))
    assert w.state()[0] == A.DECLINED and w.state()[2].startswith("mike"), w.state()
    assert "отменено" in w.answers()[-1], w.answers()
    w.core.tick(T0 + 3600)
    assert w.door.sends == [], w.door.sends


def test_svc_switch():
    off = TS.World(dict(TS.ALL_ON))
    assert off.core.pace is False, "без WA_AGENT_PACE ритм включён"
    assert any("ритм (WA_AGENT_PACE): выкл" in ln for ln in off.lines), off.lines
    on = TS.World(dict(TS.ALL_ON, WA_AGENT_PACE="1"))
    assert on.core.pace is True and any("ритм (WA_AGENT_PACE): вкл" in ln for ln in on.lines), on.lines
    junk = TS.World(dict(TS.ALL_ON, WA_AGENT_PACE="maybe"))
    assert junk.core.pace is False


def test_journal_no_client_text_or_number():
    lines = []
    w = PaceWorld(model=TA.FakeModel(text=LONG), pre=chat_before())
    w.core.log = lines.append
    did = draft_at(w)
    w.core.press(did, 1, A.ACT_SEND, "owner", now=T0 + 61)
    w.core.tick(T0 + 300)
    assert lines and not any(NUM in ln or "xxxx" in ln for ln in lines), lines


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
