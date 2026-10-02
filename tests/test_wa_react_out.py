#!/usr/bin/env python3
"""Реакции из тем форума показа клиенту в WhatsApp (WAREACTOUT0110): реакция человека → одна отправка
с нужным wamid, снятие → пустой эмодзи, без wamid — ничего, окно закрыто — not_sent без повтора,
выключатель, повтор обновления, чужая группа; дверь `wa_send.send_reaction` и одно правило ключа для
двери и показа. Всё на подделках: поддельный http Telegram, временная очередь схемой wa_webhook,
временная база показа, поддельный транспорт 360dialog. Сети нет.

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
import wa_agent_tg as G  # noqa: E402
import wa_send as S  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
HUMAN2 = {"id": 502, "is_bot": False, "first_name": "mike"}
BOT = {"id": 777, "is_bot": True, "first_name": "Splinter"}
THUMB, FIRE, HEART = "\U0001F44D", "\U0001F525", "❤"
KEY360, KEYD360 = "k360_real_AbCdEf0123456789", "kd360_real_ZyXwVu9876543210"


class FakeHttp:
    def __init__(self):
        self.calls, self.updates, self.mid = [], [], 100

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class FakeModel(A.Model):
    def draft(self, number, upto_id):
        return "черновик"


class FakeDoor(A.Door):
    def send_text(self, to, text):
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.T"}


class World:
    """Темы показа: 301 — входящее клиента (wamid.IN1), 302 — наше эхо (wamid.EC1), 303 — пачка
    (solo=0: один wamid и строка без wamid), 304 — показанная строкой реакция (вид reaction), 305 —
    строка без wamid, 306 — испорченное состояние: два разных wamid у одного сообщения."""

    def __init__(self, react=True, cards=False, door=None):
        d = tempfile.mkdtemp(prefix="wa_react_out_t_")
        self.qpath, self.dbpath, self.mpath = (os.path.join(d, n) for n in ("q.db", "agent.db", "m.db"))
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        for wamid, mtype, echo, ts in (("wamid.IN1", "text", 0, T0), ("wamid.EC1", "text", 1, T0 + 5),
                                       ("wamid.H1", "text", 0, T0 - 50), ("wamid.H2", "text", 0, T0 - 40),
                                       ("wamid.RE1", "reaction", 0, T0 + 9)):
            q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                      "VALUES(?,?,?,?,?,?,0,?)", (ts, NUM, mtype, "x", ts, echo, wamid))
        q.commit()
        q.close()
        m = sqlite3.connect(self.mpath)
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("CREATE TABLE shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL, msg_id INTEGER, "
                  "solo INTEGER)")
        for key, mid, solo in (("msg:wamid.IN1", 301, 1), ("msg:wamid.EC1", 302, 1), ("msg:wamid.H1", 303, 0),
                               ("msg:row:78", 303, 0), ("msg:wamid.RE1", 304, 1), ("msg:row:77", 305, 1),
                               ("msg:wamid.H2", 306, 1), ("file:wamid.EC1", 306, 1)):
            m.execute("INSERT INTO shown VALUES(?,?,?,?,?,?)", (key, NUM, "shown", T0, mid, solo))
        m.commit()
        m.close()
        self.http, self.lines, self.sends = FakeHttp(), [], []
        self.door = door or self.fake_send
        self.uid = 5000
        self.tg = G.Tg("123:SECRET", enabled=cards, react=react, show_chat=SHOW, mirror_db=self.mpath,
                       http=self.http, clock=lambda: T0 + 500, log=self.lines.append, react_send=self.door)
        self.core = A.Core(self.dbpath, self.qpath, FakeModel(), self.tg, FakeDoor(),
                           clock=lambda: T0 + 500, log=self.lines.append)
        self.tg.bind(self.core)

    def fake_send(self, to, wamid, emoji):
        self.sends.append((to, wamid, emoji))
        return {"outcome": "sent", "reason": "принято", "wamid": "wamid.R%d" % len(self.sends)}

    def react(self, mid, emoji, user=HUMAN, chat=SHOW, kind="emoji"):
        self.uid += 1
        new = []
        if emoji and kind == "emoji":
            new = [{"type": "emoji", "emoji": emoji}]
        elif kind == "custom_emoji":
            new = [{"type": "custom_emoji", "custom_emoji_id": "5368324170671202286"}]
        body = {"chat": {"id": int(chat), "type": "supergroup"}, "message_id": mid, "date": T0,
                "old_reaction": [], "new_reaction": new}
        if user is not None:
            body["user"] = user
        return {"update_id": self.uid, "message_reaction": body}

    def feed(self, *updates):
        self.http.updates.append(list(updates))
        return self.tg.poll()

    def reset_offset(self):
        self.core.db.execute("DELETE FROM meta WHERE key='tg_offset'")


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_reaction_one_send_right_wamid():
    w = World()
    w.feed(w.react(301, THUMB))
    assert w.sends == [(NUM, "wamid.IN1", THUMB)], w.sends


def test_reaction_on_our_echo_goes_too():
    w = World()
    w.feed(w.react(302, FIRE))
    assert w.sends == [(NUM, "wamid.EC1", FIRE)], w.sends


def test_removal_sends_empty_emoji():
    w = World()
    w.feed(w.react(301, THUMB))
    w.feed(w.react(301, ""))
    assert w.sends == [(NUM, "wamid.IN1", THUMB), (NUM, "wamid.IN1", "")], w.sends


def test_heart_full_form_to_whatsapp():
    w = World()
    w.feed(w.react(301, HEART))
    assert w.sends == [(NUM, "wamid.IN1", "❤️")], w.sends
    assert G.wa_emoji(THUMB) == THUMB and G.wa_emoji("") == ""


def test_two_humans_latest_wins():
    w = World()
    w.feed(w.react(301, THUMB, HUMAN))
    w.feed(w.react(301, FIRE, HUMAN2))
    w.feed(w.react(301, "", HUMAN2))
    w.feed(w.react(301, "", HUMAN))
    assert [s[2] for s in w.sends] == [THUMB, FIRE, THUMB, ""], w.sends


def test_allowed_updates_has_reaction():
    w = World(react=True, cards=False)
    w.feed()
    assert w.http.of("getUpdates")[0]["allowed_updates"] == ["message_reaction"], w.http.calls
    w2 = World(react=True, cards=True)
    w2.feed()
    assert w2.http.of("getUpdates")[0]["allowed_updates"] == ["callback_query", "message", "message_reaction"]


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_no_wamid_nothing_sent():
    w = World()
    w.feed(w.react(999, THUMB), w.react(305, THUMB))
    assert w.sends == [], w.sends
    assert sum("wamid нет" in ln for ln in w.lines) == 2, w.lines


def test_batch_message_nothing_sent():
    w = World()
    w.feed(w.react(303, THUMB), w.react(306, THUMB))
    assert w.sends == [] and sum("wamid нет" in ln for ln in w.lines) == 2, (w.sends, w.lines)
    assert any("больше одного wamid" in ln for ln in w.lines), w.lines


def test_reaction_line_target_nothing_sent():
    w = World()
    w.feed(w.react(304, THUMB))
    assert w.sends == [] and any("вид reaction" in ln for ln in w.lines), (w.sends, w.lines)


def test_window_closed_not_sent_no_repeat():
    trap, calls = [], []

    def transport(url, payload, key, timeout):
        trap.append(payload)
        return 200, json.dumps({"messages": [{"id": "wamid.X"}]}), None

    holder = {}

    def door(to, wamid, emoji):
        calls.append((to, wamid, emoji))
        return S.send_reaction(to, wamid, emoji, now=T0 + 200000, db_path=holder["q"],
                               env={"WA_SEND": "1", "WA_360_API_KEY": KEY360}, transport=transport)

    w = World(door=door)
    holder["q"] = w.qpath
    w.feed(w.react(301, THUMB))
    w.reset_offset()
    w.feed(w.react(301, THUMB))
    w.core.tick(T0 + 200000)
    assert len(calls) == 1 and trap == [], (calls, trap)
    assert any("301" in ln and "not_sent" in ln for ln in w.lines), w.lines


def test_switch_off_nothing():
    assert G.Tg("123:SECRET").react is False, "реакции включены по умолчанию"
    assert G.Tg("", react=True).react is False, "без ключа включено"
    w = World(react=False, cards=True)
    w.feed(w.react(301, THUMB))
    assert w.http.of("getUpdates")[0]["allowed_updates"] == ["callback_query", "message"]
    assert w.sends == [], w.sends
    w.tg.handle(w.react(301, FIRE))
    assert w.sends == [] and any("выключен" in ln for ln in w.lines), (w.sends, w.lines)
    w3 = World(react=False, cards=False)
    assert w3.tg.poll() == 0 and w3.http.calls == []


def test_repeat_update_one_send():
    w = World()
    u = w.react(301, THUMB)
    w.feed(u)
    w.feed(u)
    assert len(w.sends) == 1 and any("уже разобрано" in ln for ln in w.lines), (w.sends, w.lines)
    w.reset_offset()
    w.feed(u)
    assert len(w.sends) == 1, w.sends


def test_door_crash_no_repeat():
    def door(to, wamid, emoji):
        raise RuntimeError("обрыв")

    w = World(door=door)
    u = w.react(301, THUMB)
    w.feed(u)
    w.reset_offset()
    w.tg.react_send = w.fake_send
    w.feed(u)
    assert w.sends == [], w.sends


def test_foreign_group_nothing():
    w = World()
    w.feed(w.react(301, THUMB, chat=G.AGENTS_CHAT), w.react(301, THUMB, chat=-1001234567890))
    assert w.sends == [] and sum("чужой чат" in ln for ln in w.lines) == 2, (w.sends, w.lines)


def test_bot_reaction_ignored():
    w = World()
    w.feed(w.react(301, THUMB, user=BOT))
    assert w.sends == [], w.sends


def test_custom_emoji_not_sent():
    w = World()
    w.feed(w.react(301, None, kind="custom_emoji"))
    assert w.sends == [] and any("custom_emoji" in ln for ln in w.lines), (w.sends, w.lines)
    w.feed(w.react(301, THUMB))
    w.feed(w.react(301, None, kind="custom_emoji"))
    assert [s[2] for s in w.sends] == [THUMB, ""], w.sends


def test_react_only_no_card_actions():
    w = World(react=True, cards=False)
    w.feed({"update_id": 9001, "callback_query": {"id": "cq1", "from": HUMAN, "data": "wa:send:1:1",
                                                  "message": {"message_id": 101,
                                                              "chat": {"id": G.AGENTS_CHAT}}}})
    assert w.http.of("answerCallbackQuery") == [], w.http.calls


def test_log_has_ids_no_emoji_no_number():
    w = World()
    w.feed(w.react(301, THUMB), w.react(999, FIRE))
    log = "\n".join(w.lines)
    assert "301" in log and "sent" in log, log
    assert THUMB not in log and FIRE not in log and NUM not in log and "SECRET" not in log, log


# ═══ дверь wa_send.send_reaction и правило ключа ═════════════════════════════════════════

def _queue(ts):
    d = tempfile.mkdtemp(prefix="wa_react_out_q_")
    p = os.path.join(d, "q.db")
    q = sqlite3.connect(p)
    q.execute(QSCHEMA)
    q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
              "VALUES(?,?,?,?,?,0,0,?)", (ts, NUM, "text", "x", ts, "wamid.IN1"))
    q.commit()
    q.close()
    return p


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, key, timeout):
        self.calls.append((payload, key))
        return 200, json.dumps({"messages": [{"id": "wamid.OUT"}]}), None


def test_send_reaction_payload():
    rec = Rec()
    r = S.send_reaction(NUM, "wamid.IN1", THUMB, now=T0 + 60, db_path=_queue(T0),
                        env={"WA_SEND": "1", "WA_360_API_KEY": KEY360}, transport=rec)
    assert r["outcome"] == S.SENT and r["wamid"] == "wamid.OUT", r
    p = rec.calls[0][0]
    assert p["type"] == "reaction" and p["to"] == NUM, p
    assert p["reaction"] == {"message_id": "wamid.IN1", "emoji": THUMB}, p


def test_send_reaction_removal_empty():
    rec = Rec()
    r = S.send_reaction(NUM, "wamid.IN1", "", now=T0 + 60, db_path=_queue(T0),
                        env={"WA_SEND": "1", "WA_360_API_KEY": KEY360}, transport=rec)
    assert r["outcome"] == S.SENT and rec.calls[0][0]["reaction"]["emoji"] == "", (r, rec.calls)


def test_send_reaction_window_closed_no_net():
    rec = Rec()
    r = S.send_reaction(NUM, "wamid.IN1", THUMB, now=T0 + 200000, db_path=_queue(T0),
                        env={"WA_SEND": "1", "WA_360_API_KEY": KEY360}, transport=rec)
    assert r["outcome"] == S.NOT_SENT and r["window"] == S.WINDOW_CLOSED and rec.calls == [], r


def test_send_reaction_switch_off_no_net():
    rec = Rec()
    r = S.send_reaction(NUM, "wamid.IN1", THUMB, now=T0 + 60, db_path=_queue(T0),
                        env={"WA_SEND": "0", "WA_360_API_KEY": KEY360}, transport=rec)
    assert r["outcome"] == S.NOT_SENT and "выключена" in r["reason"] and rec.calls == [], r
    r = S.send_reaction(NUM, "", THUMB, now=T0 + 60, db_path=_queue(T0),
                        env={"WA_SEND": "1", "WA_360_API_KEY": KEY360}, transport=rec)
    assert r["outcome"] == S.NOT_SENT and rec.calls == [], r


def test_key_rule_one_for_both():
    q = _queue(T0)
    for env, want in (({"WA_360_API_KEY": KEY360, "WA_D360_API_KEY": KEYD360}, KEY360),
                      ({"WA_D360_API_KEY": KEYD360}, KEYD360),
                      ({"WA_360_API_KEY": "PLACEHOLDER", "WA_D360_API_KEY": KEYD360}, KEYD360)):
        rec = Rec()
        r = S.send_reaction(NUM, "wamid.IN1", THUMB, now=T0 + 60, db_path=q,
                            env=dict(env, WA_SEND="1"), transport=rec)
        assert r["outcome"] == S.SENT and rec.calls[0][1] == want, (env.keys(), r)
    rec = Rec()
    r = S.send_reaction(NUM, "wamid.IN1", THUMB, now=T0 + 60, db_path=q,
                        env={"WA_SEND": "1", "WA_360_API_KEY": "PLACEHOLDER" + KEY360}, transport=rec)
    assert r["outcome"] == S.NOT_SENT and rec.calls == [] and KEY360 not in r["reason"], r
    assert "WA_360_API_KEY" in r["reason"] and "WA_D360_API_KEY" in r["reason"], r


def test_mirror_reads_same_key_rule():
    import wa_tg_mirror as M
    saved = {k: os.environ.get(k) for k in S.KEY_NAMES}
    try:
        os.environ.pop("WA_360_API_KEY", None)
        os.environ["WA_D360_API_KEY"] = KEYD360
        assert M._env()["d360_key"] == KEYD360
        os.environ["WA_360_API_KEY"] = KEY360
        assert M._env()["d360_key"] == KEY360, "показ не держит общее правило ключа"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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
