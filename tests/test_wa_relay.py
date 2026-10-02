#!/usr/bin/env python3
"""Тема клиента → WhatsApp (WARELAYTEXT0210): текст человека в теме форума показа уходит клиенту одной
отправкой; исход виден в теме; «Отправить» агента — строкой в теме; человек написал — агент на паузе;
ушедшее через API — в истории агента видом «мы» один раз. Всё на подделках: Bot API, дверь, модель,
временные очередь, база показа и база агента (World из test_wa_agent_svc). Сети нет.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_wa_agent_svc as SV  # noqa: E402  (кладёт ROOT и WA_AGENT_SRC в путь)

import wa_agent as A  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_history as H  # noqa: E402

NUM, SHOW, T0, HUMAN = SV.NUM, SV.SHOW, SV.T0, SV.HUMAN
ON = {"WA_AGENT_RELAY": "1", "WA_SEND": "1"}
TEXT = "Байк готов, привезём к 10"
CLOSED = {"outcome": "not_sent", "reason": "окно закрыто (последнее сообщение клиента 30 ч назад, "
          "предел 24 ч) — шаблоны не шлём", "wamid": None, "window": "closed"}


class RW(SV.World):
    """World службы + заданный исход двери (по умолчанию sent с wamid.OUT<n>)."""

    def __init__(self, environ, res=None, **kw):
        self.res = res
        super().__init__(environ, **kw)

    def send(self, to, text, db_path=None):
        self.sends.append((to, text))
        if self.res:
            return dict(self.res)
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}

    def topic(self, text=TEXT, mid=700, thread=42, frm=None, edited=False, in_topic=True, **extra):
        m = {"message_id": mid, "chat": {"id": int(SHOW)}, "from": frm or HUMAN, "date": T0}
        if text is not None:
            m["text"] = text
        if in_topic:
            m.update(message_thread_id=thread, is_topic_message=True)
        m.update(extra)
        return self.upd(**{("edited_message" if edited else "message"): m})

    def show_msgs(self):
        return [p for p in self.http.of("sendMessage") if str(p.get("chat_id")) == SHOW]

    def paused(self):
        row = self.core.db.execute("SELECT paused FROM clients WHERE number=?", (NUM,)).fetchone()
        return bool(row and row[0])


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_text_one_send_to_topic_number():
    w = RW(ON)
    w.http.updates = [[w.topic()]]
    w.serve(10)
    assert w.sends == [(NUM, TEXT)], w.sends                            # одна отправка, номер темы 42
    allowed = w.http.of("getUpdates")[0]["allowed_updates"]
    assert allowed == ["message", "edited_message"], allowed


def test_sent_reaction_on_human_message():
    w = RW(ON)
    w.http.updates = [[w.topic()]]
    w.serve(10)
    r = w.http.of("setMessageReaction")
    assert r == [{"chat_id": SHOW, "message_id": 700,
                  "reaction": [{"type": "emoji", "emoji": G.RELAY_SENT_EMOJI}]}], r
    assert w.show_msgs() == [], w.show_msgs()                           # ответа словами нет
    st = w.core.db.execute("SELECT state, wamid FROM relay WHERE msg_id=700").fetchone()
    assert st == (A.SENT, "wamid.OUT1"), st


def test_agent_send_line_in_topic():
    w = RW(dict(SV.ALL_ON, WA_AGENT_RELAY="1"))
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    w.serve(60)
    assert w.sends == [(NUM, "черновик модели")], w.sends
    lines = w.show_msgs()
    assert len(lines) == 1, lines
    assert lines[0]["message_thread_id"] == 42 and lines[0]["text"] == "мы · агент, отправил Дарья: черновик модели", lines


def test_human_wrote_pauses_agent():
    w = RW(dict(SV.ALL_ON, WA_AGENT_RELAY="1"))
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.http.updates = [[], [], [w.topic()]]
    w.serve(60)
    assert w.draft_state() == (A.SUPERSEDED,), w.draft_state()          # черновик снят
    assert w.paused(), "агент не на паузе"
    asks = [p["text"] for p in w.http.of("sendMessage") if "Человек написал клиенту в теме" in p["text"]]
    assert len(asks) == 1, w.http.of("sendMessage")
    w.put(w.clock.t - 100)                                               # клиент пишет ещё
    w.serve(200)
    assert w.model.calls == 1, w.model.calls                             # на паузе модель не зовётся


def test_sent_in_agent_history_once():
    w = RW(dict(SV.ALL_ON, WA_AGENT_RELAY="1"))
    w.core.tick(T0 - 1000)
    w.put(T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")], [w.topic()]]
    w.serve(60)
    assert len(w.sends) == 2, w.sends
    items, _ = H.read_history(NUM, w.env["queue_db"], None, sent_db=w.env["agent_db"])
    ours = [it["text"] for it in items if it["who"] == "мы"]
    assert ours == ["черновик модели", TEXT], ours
    # эхо всё же пришло с тем же wamid — в истории по-прежнему один раз, и паузы оно не ставит
    w.core.resume(NUM, 1, "Дарья")
    w.put(w.clock.t - 1, kind="echo", wamid="wamid.OUT2")
    w.serve(10)
    items, _ = H.read_history(NUM, w.env["queue_db"], None, sent_db=w.env["agent_db"])
    keys = [it["key"] for it in items if it["who"] == "мы"]
    assert keys == ["wamid.OUT1", "wamid.OUT2"], keys                    # эхо OUT2 и outbox — одна реплика
    assert not w.paused(), "эхо нашей отправки поставило паузу"
    import wa_agent_model as M
    got, _ = M.ModelAdapter(w.env["queue_db"], None, agent_db=w.env["agent_db"])._history(NUM, 10 ** 9)
    assert [it["key"] for it in got if it["who"] == "мы"] == ["wamid.OUT1", "wamid.OUT2"], got


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_bot_wrote_nothing():
    w = RW(ON)
    w.http.updates = [[w.topic(frm={"id": 9, "is_bot": True, "first_name": "bot"})]]
    w.serve(10)
    assert w.sends == [] and w.show_msgs() == [] and not w.http.of("setMessageReaction")
    assert not w.paused()


def test_general_topic_and_topic_without_number_nothing():
    w = RW(ON)
    w.http.updates = [[w.topic(in_topic=False), w.topic(mid=701, thread=77)]]
    w.serve(10)
    assert w.sends == [] and w.show_msgs() == [] and not w.http.of("setMessageReaction")
    assert any("общая тема" in ln for ln in w.lines) and any("нет номера" in ln for ln in w.lines), w.lines


def test_window_closed_reason_no_repeat():
    w = RW(ON, res=CLOSED)
    upd = w.topic()
    w.http.updates = [[upd], [upd], [w.topic()]]                         # то же обновление и то же сообщение
    w.serve(30)
    assert len(w.sends) == 1, w.sends
    msgs = w.show_msgs()
    assert len(msgs) == 1 and msgs[0]["text"] == A.W_CLOSED, msgs
    assert msgs[0]["reply_parameters"]["message_id"] == 700 and msgs[0]["message_thread_id"] == 42, msgs
    assert w.paused()                                                     # человек вмешался — пауза всё равно


def test_repeat_update_and_restart_one_send():
    w = RW(ON)
    upd = w.topic()
    w.http.updates = [[upd, upd], [w.topic()]]
    w.serve(30)
    assert w.sends == [(NUM, TEXT)], w.sends
    # обрыв посреди двери: строка sending → после рестарта unsure, второй отправки нет
    w.core.db.execute("INSERT INTO relay(msg_id, number, state, ts) VALUES(800,?,?,?)", (NUM, A.SENDING, T0))
    w.build(ON)
    assert w.core.db.execute("SELECT state FROM relay WHERE msg_id=800").fetchone() == (A.UNSURE,)
    w.http.updates = [[w.topic(mid=800)]]
    w.serve(10)
    assert w.sends == [(NUM, TEXT)], w.sends


def test_switch_off_nothing():
    w = RW({"WA_SEND": "1"})
    w.http.updates = [[w.topic()]]
    w.serve(30)
    assert w.http.calls == [] and w.sends == [], w.http.calls             # читателя нет вовсе
    w2 = RW({"WA_SEND": "1", "WA_AGENT_CARDS": "1"})
    w2.http.updates = [[w2.topic(), w2.topic(mid=701, edited=True)]]
    w2.serve(10)
    assert w2.sends == [] and w2.show_msgs() == [] and not w2.http.of("setMessageReaction"), w2.http.calls
    assert "edited_message" not in w2.http.of("getUpdates")[0]["allowed_updates"]


def test_edit_not_relayed_one_line():
    w = RW(ON)
    w.http.updates = [[w.topic()], [w.topic(text="исправил", edited=True), w.topic(text="ещё", edited=True)]]
    w.serve(20)
    assert w.sends == [(NUM, TEXT)], w.sends                             # правка не ушла
    msgs = w.show_msgs()
    assert [m["text"] for m in msgs] == [G.RELAY_EDIT_WORDS], msgs


def test_unknown_words_no_repeat():
    w = RW(ON, res={"outcome": "unknown", "reason": "транспорт молчит", "wamid": None})
    upd = w.topic()
    w.http.updates = [[upd], [w.topic()]]
    w.serve(20)
    assert len(w.sends) == 1, w.sends
    assert [m["text"] for m in w.show_msgs()] == [A.W_UNSURE], w.show_msgs()


def test_door_off_and_door_error_words():
    w = RW({"WA_AGENT_RELAY": "1"})                                      # WA_SEND выключен
    w.http.updates = [[w.topic()]]
    w.serve(10)
    assert w.sends == [] and [m["text"] for m in w.show_msgs()] == [A.W_DOOR_OFF], w.show_msgs()
    w2 = RW(ON, res={"outcome": "not_sent", "reason": "сервер отказал 400: bad", "wamid": None})
    w2.http.updates = [[w2.topic()]]
    w2.serve(10)
    assert [m["text"] for m in w2.show_msgs()] == [A.W_DOOR_ERR % "сервер отказал 400: bad"], w2.show_msgs()
    w3 = RW(ON, res={"outcome": "not_sent", "reason": "окно неизвестно: входящих нет", "wamid": None,
                     "window": "unknown"})
    w3.http.updates = [[w3.topic()]]
    w3.serve(10)
    assert [m["text"] for m in w3.show_msgs()] == [A.W_WIN_UNKNOWN], w3.show_msgs()


def test_kind_without_pair_words():
    # медиа уходят с WARELAYMEDIA0210 (tests/test_wa_relay_media.py); вид без пары — ответ словами
    w = RW(ON)
    w.http.updates = [[w.topic(text=None, contact={"phone_number": "000", "first_name": "x"})]]
    w.serve(10)
    assert w.sends == [] and [m["text"] for m in w.show_msgs()] == [G.RELAY_NO_PAIR % "контакт"], w.show_msgs()


def test_journal_no_client_text_or_number():
    w = RW(ON)
    w.http.updates = [[w.topic()]]
    w.serve(400)
    log = "\n".join(w.lines)
    assert TEXT not in log and NUM not in log, log
    assert any("из тем sent=1" in ln for ln in w.lines), [ln for ln in w.lines if ln.startswith("сводка")]


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                           # noqa: BLE001
            fails += 1
            print("FAIL", name, type(e).__name__, str(e)[:300])
    print("%d/%d" % (len(tests) - fails, len(tests)))
    sys.exit(1 if fails else 0)
