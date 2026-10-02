#!/usr/bin/env python3
"""Ожидание «клиент без ответа» в службе wa-agent (WAUNANSWERED0210): молчание дольше порога — одна
тревога в «Агенты»; ответ с телефона, по «Отправить», из темы или реакцией — тишина; автоответ — не
ответ; повтор такта и рестарт — одна тревога; выключатель WA_AGENT_WATCH выключен — ничего.
Всё на подделках: поддельный Bot API, поддельная дверь, временные очередь, база показа и база агента.
Сети нет, модель не зовётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_watch as W  # noqa: E402
from test_wa_agent_svc import ALL_ON, CHAT, NUM, T0, World as _World, FakeHttp  # noqa: E402

ON = {"WA_AGENT_WATCH": "1"}
TH = W.WATCH_SEC
LINK = "https://t.me/c/4401325262/42"


class World(_World):
    def start(self, t=T0 - 5000):
        """Первый старт ядра и ожидания: курсоры на MAX(id)."""
        self.core.tick(t)
        if self.core.watch is not None:
            self.core.watch.tick(t)
        return self

    def row(self, ts, echo=0, text="x", msg_type="text", wamid=None, history=0, number=NUM):
        q = sqlite3.connect(self.env["queue_db"])
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,?,?)", (ts, number, msg_type, text, ts, echo, history, wamid))
        q.commit()
        q.close()
        return cur.lastrowid

    def alarms(self):
        return [p for p in self.http.of("sendMessage") if p["text"].startswith("⏰")]

    def table(self):
        return self.core.db.execute("SELECT name FROM sqlite_master WHERE name='watch_alarm'").fetchone()


def _w(environ=ON, **kw):
    return World(dict(environ), **kw).start()


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_silence_over_threshold_one_alarm():
    w = _w()
    w.row(T0 - 2200)
    w.serve(600)
    al = w.alarms()
    assert len(al) == 1, al
    assert al[0]["chat_id"] == CHAT and "reply_markup" not in al[0], al[0]
    assert "Анна" in al[0]["text"] and LINK in al[0]["text"] and "36 мин" in al[0]["text"], al[0]["text"]
    assert not w.http.of("getUpdates")                                   # читателя не заводит
    assert w.core.watch.counts() == {W.SENT: 1}, w.core.watch.counts()


def test_paused_agent_nobody_answered_alarm():
    env = dict(ALL_ON, **ON)
    w = _w(env)
    w.row(T0 - 4000)
    w.row(T0 - 3900, echo=1, text="ответ с телефона")                   # человек ответил → пауза
    w.row(T0 - 2200)                                                     # клиент написал ещё, ответа нет
    w.serve(120)
    assert w.core.db.execute("SELECT paused FROM clients").fetchone() == (1,)
    al = w.alarms()
    assert len(al) == 1 and "агент на паузе" in al[0]["text"], al
    assert w.model.calls == 0                                            # на паузе черновика нет


def test_only_autogreet_by_fingerprint_alarm():
    w = _w()
    w.core.watch.greet = (W.fp("ПРИВЕТСТВИЕ"),)
    w.row(T0 - 2300)
    w.row(T0 - 2200, echo=1, text="ПРИВЕТСТВИЕ")                        # 100 с — по времени не автоответ
    w.serve(120)
    assert len(w.alarms()) == 1, w.alarms()


def test_only_autoreply_by_time_after_first_alarm():
    w = _w()
    w.row(T0 - 2300)                                                     # «первое»: 14 суток тишины
    w.row(T0 - 2297, echo=1, text="другой текст")                       # 3 с — автоответ по времени
    w.serve(120)
    assert len(w.alarms()) == 1, w.alarms()


def test_new_client_message_rearms():
    w = _w()
    w.row(T0 - 2200)
    w.serve(300)
    w.row(w.clock.t)                                                     # новое сообщение клиента
    w.serve(TH + 300)
    assert len(w.alarms()) == 2, w.alarms()


def test_client_reaction_is_not_answer():
    w = _w()
    w.row(T0 - 2300)
    w.row(T0 - 2200, echo=0, msg_type="reaction")                       # реакция КЛИЕНТА
    w.serve(120)
    assert len(w.alarms()) == 1, w.alarms()


def test_unparsed_echo_flag_is_not_answer():
    w = _w()
    w.row(T0 - 2300)
    w.row(T0 - 2200, echo="?", text="неизвестно чьё")
    w.serve(120)
    assert len(w.alarms()) == 1, w.alarms()


def test_telegram_fail_with_code_retried_once_sent():
    class Http(FakeHttp):
        fail = 1

        def __call__(self, method, url, headers=None, data=None, timeout=30):
            if url.endswith("/sendMessage") and self.fail:
                self.fail -= 1
                self.calls.append(("sendMessage", json.loads(data.decode("utf-8"))))
                return 500, b'{"ok": false, "description": "x"}'
            return FakeHttp.__call__(self, method, url, headers, data, timeout)

    w = World(dict(ON))
    w.http = Http(w.clock)
    w.build(w.environ).start()
    w.row(T0 - 2200)
    w.serve(600)
    assert len(w.alarms()) == 2, w.alarms()                             # отказ + одна удачная
    assert w.core.watch.counts() == {W.SENT: 1}, w.core.watch.counts()


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_answered_from_phone_silence():
    w = _w()
    w.row(T0 - 2300)
    w.row(T0 - 2200, echo=1, text="ответ человека")
    w.serve(600)
    assert w.alarms() == [], w.alarms()


def test_fast_reply_after_not_first_message_is_answer():
    w = World(dict(ON))
    w.row(T0 - 5 * 86400, history=1)                                     # прежняя переписка за 14 суток
    w.start()
    w.row(T0 - 2300)
    w.row(T0 - 2297, echo=1, text="быстрый ответ")                      # 3 с, но клиент не «первый»
    w.serve(120)
    assert w.alarms() == [], w.alarms()


def test_our_reaction_from_phone_silence():
    w = _w()
    w.row(T0 - 2300)
    w.row(T0 - 2200, echo=1, msg_type="reaction")
    w.serve(120)
    assert w.alarms() == [], w.alarms()


def test_answered_by_press_silence():
    env = dict(ALL_ON, **ON)
    w = _w(env)
    w.row(T0 - 200)
    w.http.updates = [[], [], [w.press("wa:send:1:1")]]
    w.serve(TH + 400)
    assert w.sends == [(NUM, "черновик модели")], w.sends
    assert w.alarms() == [], w.alarms()


def test_answered_from_topic_silence():
    w = _w(dict(ON, WA_SEND="1"))
    w.row(T0 - 2300)
    res = w.core.relay(7, NUM, "ответ из темы", "Дарья", now=T0 - 2200)
    assert res["outcome"] == "sent", res
    w.serve(600)
    assert w.alarms() == [], w.alarms()


def test_our_reaction_from_topic_silence():
    w = _w()
    w.row(T0 - 2300, wamid="wamid.IN1")
    w.core.db.execute("INSERT INTO tg_react_out(msg_id, wamid, emoji, outcome, ts) VALUES(555,?,?,?,?)",
                      ("wamid.IN1", "👍", "sent", T0 - 2200))
    w.serve(600)
    assert w.alarms() == [], w.alarms()


def test_under_threshold_silence():
    w = _w()
    w.row(T0 - TH + 30)
    w.serve(20)
    assert w.alarms() == [], w.alarms()
    w.serve(120)
    assert len(w.alarms()) == 1, w.alarms()


def test_repeat_tick_and_restart_one_alarm():
    w = _w()
    w.row(T0 - 2200)
    w.serve(600)
    for t in range(5):
        w.core.watch.tick(w.clock.t + 61 * (t + 1))
    w.build(w.environ)                                                   # рестарт службы
    w.serve(600)
    assert len(w.alarms()) == 1, w.alarms()


def test_restart_mid_send_no_repeat():
    w = _w()
    w.row(T0 - 2200)
    w.core.db.execute("INSERT INTO watch_alarm(number, in_id, state, ts) VALUES(?,?,?,?)",
                      (NUM, 1, W.SENDING, T0 - 10))                     # оборвались посреди Telegram
    w.build(w.environ)
    w.serve(600)
    assert w.alarms() == [], w.alarms()
    assert w.core.watch.counts() == {W.UNSURE: 1}, w.core.watch.counts()


def test_net_unknown_not_retried():
    class Http(FakeHttp):
        def __call__(self, method, url, headers=None, data=None, timeout=30):
            if url.endswith("/sendMessage"):
                self.calls.append(("sendMessage", json.loads(data.decode("utf-8"))))
                return None, b"TimeoutError"
            return FakeHttp.__call__(self, method, url, headers, data, timeout)

    w = World(dict(ON))
    w.http = Http(w.clock)
    w.build(w.environ).start()
    w.row(T0 - 2200)
    w.serve(600)
    assert len(w.alarms()) == 1 and w.core.watch.counts() == {W.UNSURE: 1}, (w.alarms(), w.core.watch.counts())


def test_switch_off_nothing():
    w = _w(ALL_ON)                                                       # всё прочее включено, ожидание — нет
    w.row(T0 - 2200)
    w.serve(600)
    assert w.alarms() == [] and w.core.watch is None and w.table() is None
    assert w.words["WA_AGENT_WATCH"] == "выкл", w.words
    w2 = _w({})
    w2.row(T0 - 2200)
    w2.serve(600)
    assert w2.http.calls == [], w2.http.calls


def test_flag_without_bot_key_stays_off():
    w = World(dict(ON))
    w.env.update({k: "" for k in w.env if k.startswith("tg_")})        # ключа бота нет
    w.build(w.environ)
    assert w.core.watch is None and "ключа бота нет" in w.words["WA_AGENT_WATCH"], w.words


def test_first_start_backlog_silence():
    w = World(dict(ON))
    w.row(T0 - 2200)                                                     # до включения ожидания
    w.start()
    w.serve(600)
    assert w.alarms() == [], w.alarms()


def test_older_than_day_silence():
    w = _w()
    w.row(T0 - W.WINDOW - 100)
    w.serve(600)
    assert w.alarms() == [], w.alarms()


def test_log_numbers_only():
    w = _w()
    w.row(T0 - 2200, text="секретный текст")
    w.serve(600)
    log = "\n".join(w.lines)
    assert "тревога → sent" in log and NUM not in log and "секретный" not in log, log
    assert any("тревог ожидания sent=1" in ln for ln in w.lines if ln.startswith("сводка:")), w.lines


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
