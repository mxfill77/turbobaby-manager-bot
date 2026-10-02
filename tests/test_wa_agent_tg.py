#!/usr/bin/env python3
"""Руки Telegram службы wa-agent (WAAGENTTG0110): карточка с тремя кнопками, нажатие → одна отправка,
«Исправить» реплаем → версия +1, пауза → «Продолжить», допуск людей группы, единственный читатель
getUpdates с offset в своей базе, цикл в одном потоке, выключатель. Всё на поддельном http:
временная очередь схемой wa_webhook, временная база показа, поддельная дверь. Сети нет.

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

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "66812345678"
CHAT = G.AGENTS_CHAT
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
HUMAN2 = {"id": 502, "is_bot": False, "first_name": "mike"}
BOT = {"id": 777, "is_bot": True, "first_name": "Splinter"}


class FakeHttp:
    """Поддельный Bot API: пишет вызовы, sendMessage даёт растущий message_id, getUpdates — из очереди."""

    def __init__(self):
        self.calls, self.updates, self.mid = [], [], 100

    def __call__(self, method, url, headers=None, data=None, timeout=30):
        name = url.rsplit("/", 1)[-1]
        params = json.loads(data.decode("utf-8")) if data else {}
        self.calls.append((name, params))
        if name == "sendMessage":
            self.mid += 1
            return 200, json.dumps({"ok": True, "result": {"message_id": self.mid}}).encode()
        if name == "getUpdates":
            batch = self.updates.pop(0) if self.updates else []
            return 200, json.dumps({"ok": True, "result": batch}).encode()
        return 200, json.dumps({"ok": True, "result": True}).encode()

    def of(self, name):
        return [p for n, p in self.calls if n == name]


class FakeModel(A.Model):
    def draft(self, number, upto_id):
        return "черновик модели"


class FakeDoor(A.Door):
    def __init__(self):
        self.sends = []

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}


class World:
    def __init__(self, enabled=True):
        d = tempfile.mkdtemp(prefix="wa_agent_tg_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        self.mpath = os.path.join(d, "mirror.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        m = sqlite3.connect(self.mpath)
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Анна · +" + NUM))
        m.commit()
        m.close()
        self.http, self.door, self.lines = FakeHttp(), FakeDoor(), []
        self.uid = 1000
        self.new_core(enabled)
        self.core.tick(T0 - 1000)

    def new_core(self, enabled=True):
        self.tg = G.Tg("123:SECRET", enabled=enabled, show_chat=SHOW, mirror_db=self.mpath, http=self.http,
                       clock=lambda: T0 + 500, log=self.lines.append)
        self.core = A.Core(self.dbpath, self.qpath, FakeModel(), self.tg, self.door,
                           clock=lambda: T0 + 500, log=self.lines.append)
        self.tg.bind(self.core)

    def put(self, ts, kind="in"):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                        "VALUES(?,?,?,?,?,?,0)", (ts, NUM, "text", "x", ts, 1 if kind == "echo" else 0))
        q.commit()
        q.close()
        return cur.lastrowid

    def draft(self):
        self.put(T0)
        self.core.tick(T0 + A.QUIET_DEFAULT)
        cards = self.http.of("sendMessage")
        assert len(cards) == 1, cards
        return cards[0]

    def upd(self, **body):
        self.uid += 1
        body["update_id"] = self.uid
        return body

    def press(self, data, user=HUMAN, chat=CHAT, card_id=101):
        return self.upd(callback_query={"id": "cq%d" % (self.uid + 1), "from": user, "data": data,
                                        "message": {"message_id": card_id, "chat": {"id": chat}}})

    def reply(self, card_id, text, user=HUMAN, chat=CHAT):
        return self.upd(message={"message_id": 900 + self.uid, "from": user, "chat": {"id": chat},
                                 "text": text, "reply_to_message": {"message_id": card_id}})

    def feed(self, *updates):
        self.http.updates.append(list(updates))
        return self.tg.poll()

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]

    def state(self, did=1):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT state, ver, decided_by FROM drafts WHERE id=?", (did,)).fetchone()
        db.close()
        return row


def buttons(params):
    return [b["callback_data"] for row in params["reply_markup"]["inline_keyboard"] for b in row]


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_draft_card_three_buttons():
    w = World()
    p = w.draft()
    assert p["chat_id"] == CHAT, p["chat_id"]
    assert buttons(p) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], buttons(p)
    assert "Анна · +" + NUM in p["text"] and "https://t.me/c/4401325262/42" in p["text"], p["text"]
    assert "черновик модели" in p["text"]


def test_press_one_send_card_done():
    w = World()
    w.draft()
    w.feed(w.press("wa:send:1:1"))
    assert w.door.sends == [(NUM, "черновик модели")], w.door.sends
    ed = w.http.of("editMessageText")
    assert len(ed) == 1 and ed[0]["message_id"] == 101 and "reply_markup" not in ed[0], ed
    assert "sent: Дарья (id 501)" in ed[0]["text"], ed[0]["text"]
    assert w.answers() == ["sent"], w.answers()
    assert w.state()[0] == A.SENT


def test_fix_reply_version_up_human_text():
    w = World()
    w.draft()
    w.feed(w.press("wa:fix:1:1"))
    assert "реплаем" in w.answers()[0] and w.state()[1] == 1, (w.answers(), w.state())
    w.feed(w.reply(101, "Текст человека, дословно."))
    assert w.state()[:2] == (A.PENDING, 2), w.state()
    cards = w.http.of("sendMessage")
    assert len(cards) == 2 and buttons(cards[1]) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], cards
    assert "Текст человека, дословно." in cards[1]["text"]
    ed = w.http.of("editMessageText")
    assert len(ed) == 1 and ed[0]["message_id"] == 101 and "устарело" in ed[0]["text"], ed
    w.feed(w.press("wa:send:1:2", card_id=102))
    assert w.door.sends == [(NUM, "Текст человека, дословно.")], w.door.sends


def test_pause_resume_button():
    w = World()
    w.put(T0, "echo")
    w.core.tick(T0 + 5)
    asks = w.http.of("sendMessage")
    assert len(asks) == 1 and buttons(asks[0]) == ["wa:go:1:1"], asks
    assert w.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()[0] == 1
    w.feed(w.press("wa:go:1:1", card_id=101))
    assert w.answers() == ["продолжаем"], w.answers()
    assert w.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()[0] == 0
    ed = w.http.of("editMessageText")
    assert len(ed) == 1 and "продолжено: Дарья (id 501)" in ed[0]["text"] and "reply_markup" not in ed[0]


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_second_press_already_decided():
    w = World()
    w.draft()
    w.feed(w.press("wa:send:1:1"), w.press("wa:send:1:1", user=HUMAN2))
    assert len(w.door.sends) == 1, w.door.sends
    a = w.answers()
    assert a[0] == "sent" and a[1].startswith("уже решено: Дарья (id 501), ") and a[1].endswith("— sent"), a


def test_bot_press_refused():
    w = World()
    w.draft()
    w.feed(w.press("wa:send:1:1", user=BOT))
    assert w.door.sends == [] and w.state()[0] == A.PENDING
    assert w.answers() == ["отказ: боты не нажимают — решает человек группы"], w.answers()
    w.feed(w.reply(101, "текст бота", user=BOT))
    assert w.state()[1] == 1 and len(w.http.of("sendMessage")) == 1, "бот правит карточку"


def test_foreign_chat_refused():
    w = World()
    w.draft()
    w.feed(w.press("wa:send:1:1", chat=-100555))
    assert w.door.sends == [] and w.state()[0] == A.PENDING
    assert w.answers()[0].startswith("отказ: эта кнопка решается только"), w.answers()
    w.feed(w.reply(101, "чужой текст", chat=-100555))
    assert w.state()[1] == 1, "правка из чужого чата"


def test_old_version_stale():
    w = World()
    w.draft()
    w.feed(w.reply(101, "версия два"))
    w.feed(w.press("wa:send:1:1"))
    assert w.door.sends == [] and w.state()[:2] == (A.PENDING, 2), (w.door.sends, w.state())
    assert w.answers()[0].startswith("устарело: версия 1, действует версия 2"), w.answers()
    w.feed(w.press("wa:fix:1:1"))
    assert w.answers()[1].startswith("устарело: версия 1"), w.answers()
    w.feed(w.reply(101, "правка старой карточки"))
    assert w.state()[1] == 2, w.state()
    last = w.http.of("sendMessage")[-1]["text"]
    assert last.startswith("не принято: устарело"), last


def test_repeat_update_one_send():
    w = World()
    w.draft()
    u = w.press("wa:send:1:1")
    w.feed(u)
    w.feed(u)                                          # Telegram прислал то же обновление снова
    assert len(w.door.sends) == 1 and len(w.answers()) == 1, (w.door.sends, w.answers())
    assert w.tg.offset() == u["update_id"] + 1
    w.new_core()                                       # рестарт: offset из базы
    assert w.tg.offset() == u["update_id"] + 1
    w.core.db.execute("UPDATE meta SET value='0' WHERE key='tg_offset'")   # offset потерян
    w.feed(u)
    assert len(w.door.sends) == 1, "повтор после потери offset дал вторую отправку"
    assert w.answers()[-1].startswith("уже решено"), w.answers()


def test_cards_off_no_send_message():
    w = World(enabled=False)
    w.put(T0)
    w.core.tick(T0 + A.QUIET_DEFAULT)
    w.put(T0 + 200, "echo")
    w.core.tick(T0 + 300)
    assert w.http.calls == [], w.http.calls
    assert w.tg.poll() == 0 and w.http.calls == []
    # прямой разбор обновления при выключенном: ни ответа на нажатие, ни сообщения — сети нет вовсе
    w.tg.handle(w.press("wa:fix:1:1"))
    w.tg.handle(w.press("wa:fix:1:1", user=BOT))
    w.tg.handle(w.reply(101, "текст"))
    assert w.tg.api("sendMessage", {"chat_id": CHAT, "text": "x"}) == (False, "выключено")
    assert w.http.calls == [], w.http.calls
    assert G.flag_on(None) is False and G.flag_on("") is False and G.flag_on("on") is True


def test_switch_default_off():
    assert G.Tg("123:SECRET").enabled is False
    assert G.Tg("", enabled=True).enabled is False, "без ключа включено"


# ═══ устройство ══════════════════════════════════════════════════════════════════════════

def test_no_phone_in_callback_data():
    w = World()
    w.draft()
    w.put(T0 + 300, "echo")
    w.core.tick(T0 + 305)
    datas = [d for p in w.http.of("sendMessage") if "reply_markup" in p for d in buttons(p)]
    assert len(datas) == 4 and all(NUM not in d and NUM[-6:] not in d for d in datas), datas
    assert all(len(d.encode()) <= 64 for d in datas)


def test_get_updates_params_offset():
    w = World()
    w.feed()
    p = w.http.of("getUpdates")[0]
    assert p["allowed_updates"] == ["callback_query", "message"] and p["offset"] == 0, p


def test_press_logged_with_id_name_no_client():
    w = World()
    w.draft()
    w.feed(w.press("wa:send:1:1"))
    log = "\n".join(w.lines)
    assert "Дарья (id 501)" in log, log
    assert NUM not in log and "черновик модели" not in log and "SECRET" not in log, log


def test_loop_one_thread_tick_every_5s():
    w = World()
    clock = [T0 + 2000.0]
    seen = []

    def poll(timeout=0):
        seen.append(("poll", timeout))
        clock[0] += max(timeout, 0.5)
        return 0

    real_tick = w.core.tick

    def tick(now=None):
        seen.append(("tick", now))
        return real_tick(now)

    w.tg.poll, w.core.tick = poll, tick
    G.run(w.core, w.tg, lambda: clock[0] > T0 + 2030, clock=lambda: clock[0], sleep=lambda s: None)
    ticks = [t for k, t in seen if k == "tick"]
    polls = [t for k, t in seen if k == "poll"]
    assert 6 <= len(ticks) <= 8 and polls and max(polls) <= G.TICK_SECS, (ticks, polls)
    assert all(b - a >= G.TICK_SECS for a, b in zip(ticks, ticks[1:])), ticks
    src = open(G.__file__, encoding="utf-8").read()
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
