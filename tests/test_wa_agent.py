#!/usr/bin/env python3
"""Ядро wa-agent (WAAGENTCORE0110): черновик после паузы, захват нажатия, снятие по эхо и новому
входящему, пауза клиента, рестарт посреди отправки. Всё на подделках: временная очередь схемой
wa_webhook, своя временная база, модель/Telegram/дверь — подделки. Сети нет.

WA_AGENT_SRC=<каталог> подменяет модуль (прогон мутантов)."""
import ast
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402

# схема очереди — та же, что wa_webhook._SCHEMA (поля, которые читает ядро)
QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "10000000001"
T0 = 1_790_000_000


class Crash(BaseException):
    """Смерть процесса посреди вызова двери: except Exception её не ловит."""


class FakeModel(A.Model):
    def __init__(self, text="черновик", during=None):
        self.calls, self.text, self.during = 0, text, during

    def draft(self, number, upto_id):
        self.calls += 1
        if self.during:
            self.during()
        return self.text if self.text is None else "%s %d" % (self.text, self.calls)


class FakeTG(A.Telegram):
    def __init__(self):
        self.cards, self.done, self.asks = [], [], []

    def card(self, draft_id, ver, number, text):
        self.cards.append(draft_id)
        return 1000 + draft_id

    def card_done(self, draft_id, card_id, words):
        self.done.append((draft_id, words))

    def ask_pause(self, number, pause_no):
        self.asks.append((number, pause_no))


class FakeDoor(A.Door):
    def __init__(self, outcome="sent", crash=False):
        self.sends, self.outcome, self.crash = [], outcome, crash

    def send_text(self, to, text):
        self.sends.append((to, text))
        if self.crash:
            raise Crash()
        return {"outcome": self.outcome, "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)
                if self.outcome == "sent" else None}


class World:
    def __init__(self, model=None, door=None, pre=None):
        d = tempfile.mkdtemp(prefix="wa_agent_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        for args in pre or ():
            self.put(*args)
        self.model, self.tg, self.door = model or FakeModel(), FakeTG(), door or FakeDoor()
        self.core = self.new_core()
        self.core.tick(T0 - 1000)          # первый старт: курсор на MAX(id)

    def new_core(self):
        return A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door)

    def put(self, ts, kind="in", number=NUM, history=0, wamid=None, msg_type="text"):
        echo = 1 if kind == "echo" else 0
        if kind == "status":
            msg_type, echo = "status", 1
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, "
                        "wamid) VALUES(?,?,?,?,?,?,?,?)", (ts, number, msg_type, "x", ts, echo, history, wamid))
        q.commit()
        rid = cur.lastrowid
        q.close()
        return rid

    def drafts(self, state=None):
        db = sqlite3.connect(self.dbpath)
        rows = db.execute("SELECT id, state, ver, upto_id, decided_by, wamid FROM drafts ORDER BY id").fetchall()
        db.close()
        return [r for r in rows if state is None or r[1] == state]

    def paused(self, number=NUM):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT paused, pause_no FROM clients WHERE number=?", (number,)).fetchone()
        db.close()
        return row or (0, 0)


def one_draft(w, ts=T0):
    w.put(ts)
    w.core.tick(ts + A.QUIET_DEFAULT)
    d = w.drafts(A.PENDING)
    assert len(d) == 1, d
    return d[0]


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_inbound_pause_one_draft():
    w = World()
    w.put(T0)
    w.core.tick(T0 + 10)
    w.put(T0 + 30)                                     # клиент пишет очередью
    w.core.tick(T0 + 30 + A.QUIET_DEFAULT - 1)
    assert w.drafts() == [] and w.model.calls == 0, "черновик до паузы тишины"
    for k in range(5):
        w.core.tick(T0 + 30 + A.QUIET_DEFAULT + k * 5)
    d = w.drafts()
    assert len(d) == 1 and d[0][1] == A.PENDING, d
    assert w.model.calls == 1 and len(w.tg.cards) == 1, (w.model.calls, w.tg.cards)


def test_press_one_message():
    w = World()
    did = one_draft(w)[0]
    r = w.core.press(did, 1, A.ACT_SEND, "owner")
    assert r["ok"] and r["state"] == A.SENT, r
    assert w.door.sends == [(NUM, "черновик 1")], w.door.sends
    d = w.drafts()[0]
    assert d[1] == A.SENT and d[4] == "owner" and d[5] == "wamid.OUT1", d
    w.core.tick(T0 + 500)
    assert len(w.drafts()) == 1, "после отправки новый черновик на те же сообщения"


def test_echo_supersede_pause_resume():
    w = World()
    did = one_draft(w)[0]
    w.put(T0 + 100, "echo")
    w.core.tick(T0 + 101)
    assert w.drafts()[0][1] == A.SUPERSEDED, w.drafts()
    assert w.paused()[0] == 1 and w.tg.asks == [(NUM, 1)], (w.paused(), w.tg.asks)
    assert w.core.press(did, 1, A.ACT_SEND, "owner")["ok"] is False and w.door.sends == []
    w.put(T0 + 200)                                    # клиент пишет на паузе
    w.core.tick(T0 + 200 + 200)
    assert len(w.drafts()) == 1 and w.model.calls == 1, "черновик на паузе"
    w.put(T0 + 500, "echo")                            # человек отвечает снова — вопрос не повторяется
    w.put(T0 + 600)
    w.core.tick(T0 + 900)
    assert w.tg.asks == [(NUM, 1)] and len(w.drafts()) == 1, (w.tg.asks, w.drafts())
    r = w.core.resume(NUM, 1, "owner", now=T0 + 950)
    assert r["ok"] and w.paused()[0] == 0, r
    assert w.core.resume(NUM, 1, "mike", now=T0 + 951)["ok"] is False
    w.core.tick(T0 + 960)
    d = w.drafts(A.PENDING)
    assert len(d) == 1 and w.model.calls == 2, ("после «Продолжить» нет черновика", w.drafts())


def test_decline():
    w = World()
    did = one_draft(w)[0]
    assert w.core.press(did, 1, A.ACT_DECLINE, "owner")["state"] == A.DECLINED
    r = w.core.press(did, 1, A.ACT_SEND, "mike")
    assert r["ok"] is False and "owner" in r["words"] and A.DECLINED in r["words"], r
    w.core.tick(T0 + 1000)
    assert len(w.drafts()) == 1 and w.door.sends == [], "после «не нужно» новый черновик/отправка"


def test_revise_old_version_dead():
    w = World()
    did = one_draft(w)[0]
    assert w.core.revise(did, "текст человека", "owner")
    assert w.core.press(did, 1, A.ACT_SEND, "mike")["ok"] is False and w.door.sends == []
    assert w.core.press(did, 2, A.ACT_SEND, "mike")["ok"] is True
    assert w.door.sends == [(NUM, "текст человека")], w.door.sends


def test_real_door_closed_contract():
    """Настоящая wa_send.send_text при выключенной ручке: not_sent до сети, ядро пишет not_sent."""
    import wa_send

    class RealDoor(A.Door):
        def send_text(self, to, text):
            return wa_send.send_text(to, text, env={})
    w = World(door=RealDoor())
    did = one_draft(w)[0]
    r = w.core.press(did, 1, A.ACT_SEND, "owner")
    assert r["state"] == A.NOT_SENT, r
    assert w.core.press(did, 1, A.ACT_SEND, "owner")["ok"] is False


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_two_presses_one_send():
    w = World()
    did = one_draft(w)[0]
    other = w.new_core()                               # второй процесс на той же базе
    r1 = w.core.press(did, 1, A.ACT_SEND, "owner")
    r2 = other.press(did, 1, A.ACT_SEND, "mike")
    assert r1["ok"] and r2["ok"] is False, (r1, r2)
    assert len(w.door.sends) == 1, ("двойная отправка", len(w.door.sends))
    assert "owner" in r2["words"] and A.SENT in r2["words"] and "UTC" in r2["words"], r2


def test_repeat_update_one_send():
    w = World()
    did = one_draft(w)[0]
    for _ in range(3):                                 # тот же callback доставлен трижды
        w.core.press(did, 1, A.ACT_SEND, "owner")
    assert len(w.door.sends) == 1, ("повтор обновления — повтор отправки", len(w.door.sends))


def test_restart_in_sending_no_repeat():
    w = World(door=FakeDoor(crash=True))
    did = one_draft(w)[0]
    try:
        w.core.press(did, 1, A.ACT_SEND, "owner")
    except Crash:
        pass
    assert w.drafts()[0][1] == A.SENDING, w.drafts()
    w.door.crash = False
    w.core = w.new_core()                              # рестарт службы
    assert w.drafts()[0][1] == A.UNSURE, w.drafts()
    w.core.press(did, 1, A.ACT_SEND, "owner")
    w.core.tick(T0 + 2000)
    assert len(w.door.sends) == 1, ("повтор после рестарта", len(w.door.sends))
    assert len(w.drafts()) == 1, ("новый черновик на те же сообщения после рестарта", w.drafts())


def test_door_unknown_is_unsure():
    w = World(door=FakeDoor(outcome="unknown"))
    did = one_draft(w)[0]
    assert w.core.press(did, 1, A.ACT_SEND, "owner")["state"] == A.UNSURE
    w.core.press(did, 1, A.ACT_SEND, "owner")
    assert len(w.door.sends) == 1, "unknown двери повторён"


def test_paused_no_draft():
    w = World()
    w.put(T0, "echo")                                  # человек написал первым
    w.put(T0 + 10)
    w.core.tick(T0 + 500)
    assert w.paused()[0] == 1 and w.drafts() == [] and w.model.calls == 0, (w.paused(), w.drafts())


def test_new_inbound_makes_stale():
    w = World()
    old = one_draft(w)[0]
    w.put(T0 + 100)
    w.core.tick(T0 + 101)
    assert w.drafts()[0][1] == A.STALE, w.drafts()
    assert any(d == old for d, _ in w.tg.done), w.tg.done
    w.core.tick(T0 + 100 + A.QUIET_DEFAULT)
    live = w.drafts(A.PENDING)
    assert len(live) == 1 and live[0][0] != old, w.drafts()
    assert w.core.press(old, 1, A.ACT_SEND, "owner")["ok"] is False and w.door.sends == []


def test_press_sees_unscanned_echo():
    w = World()
    did = one_draft(w)[0]
    w.put(T0 + 100, "echo")                            # такт ещё не видел эха
    r = w.core.press(did, 1, A.ACT_SEND, "owner")
    assert r["ok"] is False and r["state"] == A.SUPERSEDED and w.door.sends == [], r
    assert w.paused()[0] == 1, "эхо при нажатии не поставило паузу"


def test_press_sees_unscanned_inbound():
    w = World()
    did = one_draft(w)[0]
    w.put(T0 + 100)
    r = w.core.press(did, 1, A.ACT_SEND, "owner")
    assert r["state"] == A.STALE and w.door.sends == [], r
    w.core.tick(T0 + 100 + A.QUIET_DEFAULT)
    assert len(w.drafts(A.PENDING)) == 1, w.drafts()


def test_first_start_ignores_old():
    w = World(pre=[(T0 - 5000,), (T0 - 4000, "echo"), (T0 - 3000,)])
    w.core.tick(T0 + 1000)
    assert w.drafts() == [] and w.paused()[0] == 0, (w.drafts(), w.paused())


def test_own_wamid_echo_no_pause():
    w = World()
    did = one_draft(w)[0]
    w.core.press(did, 1, A.ACT_SEND, "owner")
    w.put(T0 + 200, "echo", wamid="wamid.OUT1")
    w.core.tick(T0 + 201)
    assert w.paused()[0] == 0 and w.tg.asks == [], "эхо своей отправки поставило паузу"


def test_history_receipt_ignored():
    w = World()
    w.put(T0, "in", history=1)
    w.put(T0, "echo", history=1)
    w.put(T0, "status")
    w.core.tick(T0 + 500)
    assert w.drafts() == [] and w.paused()[0] == 0, (w.drafts(), w.paused())


def test_model_race_no_draft():
    holder = {}
    m = FakeModel(during=lambda: holder["w"].put(T0 + 70) if holder["w"].model.calls == 1 else None)
    w = World(model=m)
    holder["w"] = w
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    assert w.drafts() == [], ("черновик записан, хотя клиент написал во время модели", w.drafts())
    w.core.tick(T0 + 70 + A.QUIET_DEFAULT)
    assert len(w.drafts(A.PENDING)) == 1, w.drafts()


def test_model_none_retry_later():
    w = World(model=FakeModel(text=None))
    w.put(T0)
    for k in range(10):
        w.core.tick(T0 + A.QUIET_DEFAULT + k * 5)
    assert w.drafts() == [] and w.model.calls == 1, w.model.calls


def test_quiet_bounds():
    w = World()
    for bad in (59, 91):
        try:
            A.Core(w.dbpath, w.qpath, w.model, w.tg, w.door, quiet=bad)
        except ValueError:
            continue
        raise AssertionError("пауза %d принята" % bad)


def test_one_live_index():
    w = World()
    did = one_draft(w)[0]
    try:
        w.core.db.execute("INSERT INTO drafts(number, state, text, upto_id, created_at) VALUES(?,?,?,?,?)",
                          (NUM, A.PENDING, "x", 1, T0))
    except sqlite3.IntegrityError:
        return
    raise AssertionError("база приняла второй живой черновик (%d)" % did)


def test_no_network_in_core():
    src = open(A.__file__, encoding="utf-8").read()
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names == {"sqlite3", "time", "wa_kind"}, names


def test_queue_read_only():
    w = World()
    with w.core._queue() as q:
        try:
            q.execute("INSERT INTO wa_inbox(ts_queued) VALUES(1)")
        except sqlite3.OperationalError:
            return
    raise AssertionError("очередь открыта на запись")


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
