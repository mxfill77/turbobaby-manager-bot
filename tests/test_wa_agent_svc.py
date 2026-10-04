#!/usr/bin/env python3
"""Служба wa-agent (WAAGENTSVC0210): сборка ядра, рук Telegram, двери и реакций; четыре выключателя
по умолчанию выключены; «отправка выключена» до двери; второй читатель (409) — строка и не падает;
сводка раз в 5 минут; юнит. Всё на подделках: поддельный Bot API, поддельная модель, поддельная дверь
текста и реакций, временные очередь, база показа и база агента. Сети нет, модель не зовётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
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
import wa_agent_svc as S  # noqa: E402
import wa_agent_tg as G  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
CHAT = G.AGENTS_CHAT
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
TOKEN = "123:SECRET"
ALL_ON = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_CARDS": "1", "WA_AGENT_REACT": "1", "WA_SEND": "1"}


class Clock:
    def __init__(self, t):
        self.t = float(t)

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += max(float(s), 0.01)


class FakeHttp:
    """Поддельный Bot API: пишет вызовы; getUpdates — из очереди партий (или 409), двигает часы."""

    def __init__(self, clock, conflict=False):
        self.calls, self.updates, self.mid, self.clock, self.conflict = [], [], 100, clock, conflict

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "getUpdates":
            self.clock.t += max(params.get("timeout", 0), 0.5)
            if self.conflict:
                return 409, json.dumps({"ok": False, "error_code": 409, "description":
                                        "Conflict: terminated by other getUpdates request"}).encode()
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        if name == "sendMessage":
            self.mid += 1
            return 200, json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class FakeModel(A.Model):
    def __init__(self):
        self.calls = 0

    def draft(self, number, upto_id):
        self.calls += 1
        return "черновик модели"


class World:
    def __init__(self, environ, model=True, conflict=False, t=T0):
        d = tempfile.mkdtemp(prefix="wa_agent_svc_t_")
        self.env = {"queue_db": os.path.join(d, "q.db"), "mirror_db": os.path.join(d, "mirror.db"),
                    "agent_db": os.path.join(d, "agent.db"), "tg_token": TOKEN, "show_chat": SHOW,
                    "log_path": os.path.join(d, "wa_agent.log")}
        q = sqlite3.connect(self.env["queue_db"])
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        m = sqlite3.connect(self.env["mirror_db"])
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Анна · +" + NUM))
        m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
                  "solo INTEGER)")
        m.execute("INSERT INTO shown VALUES(?,?,?,?,?,?)", ("msg:wamid.IN1", NUM, "shown", T0, 555, 1))
        m.commit()
        m.close()
        self.clock = Clock(t)
        self.http = FakeHttp(self.clock, conflict=conflict)
        self.model = FakeModel() if model else None
        self.sends, self.reacts, self.lines = [], [], []
        self.uid = 1000
        self.build(environ)

    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}

    def react_send(self, number, wamid, emoji):
        self.reacts.append((number, wamid, emoji))
        return {"outcome": "sent", "reason": "ok"}

    def build(self, environ):
        self.environ = dict(environ)
        self.core, self.tg, self.flags, self.words = S.build(
            self.env, environ=self.environ, model=self.model, http=self.http, send=self.send,
            react_send=self.react_send, clock=self.clock, line=self.lines.append)
        return self

    def put(self, ts, kind="in", wamid=None):
        q = sqlite3.connect(self.env["queue_db"])
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,0,?)", (ts, NUM, "text", "x", ts, 1 if kind == "echo" else 0, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        return body

    def press(self, data, card_id=101):
        return self.upd(callback_query={"id": "cq%d" % (self.uid + 1), "from": HUMAN, "data": data,
                                        "message": {"message_id": card_id, "chat": {"id": CHAT}}})

    def reaction(self, emoji, mid=555):
        return self.upd(message_reaction={"chat": {"id": int(SHOW)}, "message_id": mid, "user": HUMAN,
                                          "date": T0, "old_reaction": [],
                                          "new_reaction": [{"type": "emoji", "emoji": emoji}] if emoji else []})

    def serve(self, seconds, every=S.SUMMARY_EVERY):
        end = self.clock.t + seconds
        return S.serve(self.core, self.tg, self.words, lambda: self.clock.t >= end, clock=self.clock,
                       sleep=self.clock.sleep, every=every, line=self.lines.append)

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def draft_state(self, did=1):
        return self.core.db.execute("SELECT state FROM drafts WHERE id=?", (did,)).fetchone()


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_e2e_inbound_draft_card_press_one_send():
    w = World(ALL_ON)
    w.core.tick(T0 - 1000)                                   # первый старт: курсор на MAX(id)
    w.put(T0 - 200)                                          # вход клиента
    w.http.updates = [[], [], [w.press("wa:send:1:1")], [w.press("wa:send:1:1")]]
    w.serve(60)
    # WAMIRROR0410: ушедшее — ещё одной строкой в теме клиента (форум показа), карточка в «Агентах» одна
    cards = [p for p in w.http.of("sendMessage") if p.get("chat_id") == CHAT]
    assert w.model.calls == 1, w.model.calls
    assert len(cards) == 1 and "черновик модели" in cards[0]["text"], cards
    shows = [p for p in w.http.of("sendMessage") if str(p.get("chat_id")) == SHOW]
    assert len(shows) == 1 and shows[0]["text"].endswith("\nчерновик модели"), shows
    assert w.sends == [(NUM, "черновик модели")], w.sends               # одна отправка
    assert w.draft_state() == (A.SENT,), w.draft_state()
    assert w.answers()[0] == "sent" and w.answers()[1].startswith("уже решено"), w.answers()


def test_reaction_one_send():
    w = World({"WA_AGENT_REACT": "1"})
    w.put(T0 - 100, wamid="wamid.IN1")
    w.http.updates = [[w.reaction("👍")], [w.reaction("👍")]]
    w.serve(30)
    assert w.reacts == [(NUM, "wamid.IN1", "👍")], w.reacts
    allowed = w.http.of("getUpdates")[0]["allowed_updates"]
    assert allowed == [G.REACT_UPDATE], allowed                           # карточки выключены
    assert not w.http.of("sendMessage") and not w.sends


def test_summary_every_5_minutes_numbers_only():
    w = World(ALL_ON)
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    w.serve(900)
    sums = [ln for ln in w.lines if ln.startswith("сводка:")]
    assert 3 <= len(sums) <= 4, sums
    assert "sent=1" in sums[-1] and "WA_SEND=вкл" in sums[-1], sums[-1]
    log = "\n".join(w.lines)
    assert NUM not in log and "черновик модели" not in log and "SECRET" not in log, log


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_all_switches_off_zero_telegram_zero_door():
    w = World({})
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.put(T0 - 150, kind="echo")
    w.put(T0 - 100, wamid="wamid.IN1")
    w.http.updates = [[w.press("wa:send:1:1"), w.reaction("👍")]]
    w.serve(600)
    assert w.http.calls == [], w.http.calls                              # ни одного вызова Telegram
    assert w.sends == [] and w.reacts == [], (w.sends, w.reacts)         # ни одного вызова двери
    assert w.model.calls == 0 and w.core.counts() == {}, (w.model.calls, w.core.counts())
    assert all(v == "выкл" for v in w.words.values()), w.words
    for raw in ({}, {k: "0" for k in ALL_ON}, {k: "" for k in ALL_ON}, {k: "no" for k in ALL_ON}):
        assert not any(S.flags_of(raw).values()), raw


def test_send_off_words_before_door():
    env = dict(ALL_ON)
    del env["WA_SEND"]
    w = World(env)
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    w.serve(30)
    assert w.sends == [], w.sends                                         # дверь не звана
    assert w.answers() and "отправка выключена" in w.answers()[0], w.answers()
    assert w.draft_state() == (A.PENDING,), w.draft_state()             # черновик ждёт
    assert w.words["WA_SEND"] == "выкл"
    door = S.SendDoor(w.env["queue_db"], environ={}, send=w.send)        # сама дверь — тоже до сети
    res = door.send_text(NUM, "x")
    assert res["outcome"] == "not_sent" and "отправка выключена" in res["reason"] and w.sends == [], res


def test_door_probe_crash_counts_as_off():
    w = World(ALL_ON)
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.core.tick(T0 + 100)

    def boom():
        raise RuntimeError("x")
    w.core.door.is_open = boom
    res = w.core.press(1, 1, A.ACT_SEND, "Дарья")
    assert "отправка выключена" in res["words"] and w.sends == [], res


def test_second_reader_409_logged_once_no_crash():
    w = World({"WA_AGENT_CARDS": "1"}, conflict=True)
    stats = w.serve(120)
    polls = w.http.of("getUpdates")
    said = [ln for ln in w.lines if "второй читатель" in ln]
    assert len(said) == 1 and "409" in said[0], said
    assert not [ln for ln in w.lines if "HTTP 409" in ln], w.lines
    assert 2 <= len(polls) <= 6, len(polls)                              # опрос раз в 30 с
    assert stats.get("ticks", 0) >= 20 and not stats.get("tick_fail"), stats   # такт идёт
    assert w.tg.polls["conflict"] == len(polls), w.tg.polls
    assert "409=%d" % len(polls) in S.summary(w.core, w.tg, w.words, stats), w.lines


def test_drafts_flag_without_model_stays_off():
    w = World({"WA_AGENT_DRAFTS": "1"}, model=False)
    assert w.core.drafts is False and "адаптера модели нет" in w.words["WA_AGENT_DRAFTS"], w.words


def test_drafts_off_no_backlog_on_enable():
    w = World(ALL_ON)
    w.core.tick(T0 - 1000)
    w.put(T0 - 10)                                    # пришло при включённых, тишина не вышла
    w.core.tick(T0)
    off = dict(ALL_ON, WA_AGENT_DRAFTS="0")
    w.build(off)
    w.put(T0 + 10)                                    # пришло при выключенных
    w.core.tick(T0 + 20)
    w.build(ALL_ON)
    w.core.tick(T0 + 500)
    assert w.core.counts() == {} and w.model.calls == 0, (w.core.counts(), w.model.calls)
    w.put(T0 + 600)                                   # новое после включения — черновик есть
    w.core.tick(T0 + 700)
    assert w.core.counts() == {A.PENDING: 1}, w.core.counts()


def test_env_same_path_as_mirror():
    import wa_tg_mirror
    real = wa_tg_mirror._env
    wa_tg_mirror._env = lambda: {"queue_db": "/x/wa_queue.db", "state_db": "/x/wa_tg_mirror.db",
                                 "tg_token": "T", "tg_chat": SHOW}
    try:
        env = S.env_of()
    finally:
        wa_tg_mirror._env = real
    assert env["queue_db"] == "/x/wa_queue.db" and env["mirror_db"] == "/x/wa_tg_mirror.db", env
    assert env["tg_token"] == "T" and env["show_chat"] == SHOW, env
    assert os.path.basename(env["agent_db"]) == "wa_agent.db" and env["log_path"].endswith("wa_agent.log"), env


def test_unit_text():
    unit = open(os.path.join(ROOT, "deploy", "wa-agent.service"), encoding="utf-8").read()
    mirror = open(os.path.join(ROOT, "deploy", "wa-tg-mirror.service"), encoding="utf-8").read()

    def val(text, key):
        return [ln.split("=", 1)[1] for ln in text.splitlines() if ln.startswith(key + "=")]
    assert val(unit, "User") == val(mirror, "User") == ["root"]
    assert val(unit, "WorkingDirectory") == val(mirror, "WorkingDirectory")
    py = val(mirror, "ExecStart")[0].split()[0]
    assert val(unit, "ExecStart") == [py + " /root/turbobaby-manager-bot/wa_agent_svc.py"], val(unit, "ExecStart")
    assert val(unit, "Restart") == ["always"]
    assert not [ln for ln in unit.splitlines() if ln.startswith(("Environment", "EnvironmentFile"))]
    src = open(S.__file__, encoding="utf-8").read()
    assert "threading" not in src and "Thread(" not in src


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
