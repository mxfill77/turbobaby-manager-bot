#!/usr/bin/env python3
"""Адаптер модели wa-agent (WAAGENTMODEL0210): история и знания доходят до модели, маска, «нужен
человек» → пометка и «Отправить» заперто до «Исправить», не JSON — черновика нет, WA_AGENT_DRAFTS
выключен — модель не звана, цена без дат — двери нет. Всё на подделках: временные очередь и архив,
поддельные модель, мост (узлы, парк, дверь цены), Bot API и дверь отправки. Сети нет, модели нет.

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
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_svc as SV  # noqa: E402
import wa_agent_tg as G  # noqa: E402

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""
ASCHEMA = """CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT, ts INTEGER, from_me INTEGER,
 kind TEXT, text TEXT, caption TEXT, transcript TEXT, media_file TEXT, key_id TEXT)"""

NUM = "10000000009"                      # выдуманный номер
CHAT = G.AGENTS_CHAT
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
T0 = 1_790_000_000                       # 2026-09-21 UTC
FAQ = "FAQ-УЗЕЛ: доставка по Пхукету бесплатно от 3 суток; депозит наличными."
RULES = "ПРАВИЛА-УЗЕЛ: шлем обязателен; права категории A."
FLEET = {"ok": True, "bikes": [{"name": "PCX 160 1234"}, {"name": "PCX 160 5678"}, {"name": "XMAX 300 4321"}]}
OK_JSON = json.dumps({"text": "Добрый день! Подскажу.", "lang": "ru", "handoff": [], "why": "вопрос"},
                     ensure_ascii=False)


class FakeCall:
    """Поддельная модель: пишет (system, user), отдаёт заданный ответ."""

    def __init__(self, reply=OK_JSON):
        self.calls, self.reply = [], reply

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.reply, {"model": "fake", "in": len(system + user) // 4, "out": 20}


class FakeBridge:
    def __init__(self):
        self.reads, self.fleets, self.doors = [], 0, []

    def read_doc(self, name):
        self.reads.append(name)
        return {"ok": True, "text": FAQ if name == "faq" else RULES}

    def fleet(self):
        self.fleets += 1
        return FLEET

    def door(self, unit, ds, de):
        self.doors.append((unit, ds, de))
        # живой формат двери (QuotePrice.js): скидка за срок — только словами в text (WAPRICECTX0410)
        return {"ok": True, "days": 7, "day_price": 400, "total": 2800, "deposit": 3000,
                "season": {"label": "P3"}, "model": "PCX 160",
                "text": "PCX 160 | дней: 7, стоимость: 2800 (скидка за срок 0%, 400 в день), депозит: 3000 бат"}


class FakeHttp:
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


class FakeDoor(A.Door):
    def __init__(self):
        self.sends = []

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}


class World:
    def __init__(self, reply=OK_JSON, archive=0):
        d = tempfile.mkdtemp(prefix="wa_agent_model_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        self.apath = os.path.join(d, "arch.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        a = sqlite3.connect(self.apath)
        a.execute(ASCHEMA)
        for i in range(archive):                  # выдуманный архив: старые реплики обеих сторон
            a.execute("INSERT INTO messages(number, ts, from_me, kind, text, key_id) VALUES(?,?,?,?,?,?)",
                      (NUM, T0 - 86400 * 40 + i * 60, i % 2, "text", "АРХИВ-%03d" % i, "K%03d" % i))
        a.commit()
        a.close()
        self.call, self.bridge, self.lines = FakeCall(reply), FakeBridge(), []
        self.adapter = WM.ModelAdapter(self.qpath, self.call, read_doc=self.bridge.read_doc,
                                       fleet=self.bridge.fleet, door=self.bridge.door, archive_db=self.apath,
                                       clock=lambda: T0, log=self.lines.append)
        self.http, self.door = FakeHttp(), FakeDoor()
        self.uid = 1000
        self.tg = G.Tg("123:SECRET", enabled=True, http=self.http, clock=lambda: T0 + 500,
                       log=self.lines.append)
        self.core = A.Core(self.dbpath, self.qpath, self.adapter, self.tg, self.door,
                           clock=lambda: T0 + 500, log=self.lines.append)
        self.tg.bind(self.core)
        self.core.tick(T0 - 1000)

    def put(self, ts, text, kind="in", history=0):
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                        "VALUES(?,?,?,?,?,?,?)", (ts, NUM, "text", text, ts, 1 if kind == "echo" else 0, history))
        q.commit()
        q.close()
        return cur.lastrowid

    def ask(self, text, ts=T0):
        self.put(ts, text)
        self.core.tick(ts + A.QUIET_DEFAULT)

    def press(self, data, card_id):
        self.uid += 1
        self.http.updates.append([{"update_id": self.uid, "callback_query": {
            "id": "cq%d" % self.uid, "from": HUMAN, "data": data,
            "message": {"message_id": card_id, "chat": {"id": CHAT}}}}])
        self.tg.poll()

    def reply(self, card_id, text):
        self.uid += 1
        self.http.updates.append([{"update_id": self.uid, "message": {
            "message_id": 900 + self.uid, "from": HUMAN, "chat": {"id": CHAT}, "text": text,
            "reply_to_message": {"message_id": card_id}}}])
        self.tg.poll()

    def drafts(self):
        return self.core.db.execute("SELECT id, state, ver, text, handoff FROM drafts ORDER BY id").fetchall()

    def answers(self):
        return [p["text"] for p in self.http.of("answerCallbackQuery")]


def buttons(params):
    return [b["callback_data"] for row in params["reply_markup"]["inline_keyboard"] for b in row]


# ═══ позитивы ════════════════════════════════════════════════════════════════════════════

def test_history_and_knowledge_reach_model():
    w = World(archive=40)
    for i in range(10):                          # живая переписка до вопроса: клиент и мы по очереди
        w.put(T0 - 3000 + i * 60, "ОЧЕРЕДЬ-%02d" % i, kind="echo" if i % 2 else "in")
    w.core.tick(T0 - 100)                        # эхо ставит паузу — снимаем её «Продолжить»
    w.core.resume(NUM, 1, "тест")
    w.put(T0 - 10, "СЕЙЧАС-1 а доставка есть?")
    w.ask("СЕЙЧАС-2 и шлем дадите?")
    assert len(w.call.calls) == 1, len(w.call.calls)
    system, user = w.call.calls[0]
    for i in range(40):
        assert "АРХИВ-%03d" % i in user, i
    for i in range(10):
        assert "ОЧЕРЕДЬ-%02d" % i in user, i
    assert FAQ in user and RULES in user and "снят 0 мин назад" in user, user[:400]
    now = user.split("КЛИЕНТ СЕЙЧАС")[1]
    assert "СЕЙЧАС-1" in now and "СЕЙЧАС-2" in now and "ОЧЕРЕДЬ" not in now, now
    info = w.adapter.last["info"]
    assert info["history_items"] == 52 and info["history_chars"] > 52 * 20, info
    assert info["user_chars"] == len(user) and len(user) > info["history_chars"] + len(FAQ) + len(RULES)
    assert "Пересказывать" not in system and "НЕ пересказывай" in system
    assert len(w.drafts()) == 1 and w.drafts()[0][3] == "Добрый день! Подскажу."


def test_rows_after_upto_not_in_history():
    w = World()
    rid = w.put(T0, "ДО-ЧЕРНОВИКА")
    w.put(T0 + 5, "ПОСЛЕ-ЧЕРНОВИКА")
    _s, user, _i = w.adapter.build(NUM, rid, now=T0 + 100)
    assert "ДО-ЧЕРНОВИКА" in user and "ПОСЛЕ-ЧЕРНОВИКА" not in user, user[-300:]


def test_mask_applied_before_model():
    w = World()
    w.ask("пароль от wifi: Qwerty12345zz, карта 4111 1111 1111 1111, сколько стоит PCX?")
    user = w.call.calls[0][1]
    assert "Qwerty12345zz" not in user and "4111 1111 1111 1111" not in user, user[-300:]
    assert "[скрыто: пароль]" in user and "[скрыто: карта]" in user, user[-300:]
    assert w.adapter.last["info"]["masked"] >= 2


def test_price_with_model_and_dates_one_door():
    w = World()
    w.ask("Сколько стоит PCX 160 с 5 по 12 ноября?")
    assert w.bridge.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], w.bridge.doors
    user = w.call.calls[0][1]
    assert "ЦЕНА: 2026-11-05, 2026-11-12 — PCX 160: 7 сут., 400 ฿ в сутки, итого 2 800 ฿" in user, user[-500:]


def test_handoff_mark_send_locked_until_fix():
    rep = json.dumps({"text": "Сожалеем, передам коллеге.", "lang": "ru", "handoff": ["жалоба"],
                      "why": "жалоба"}, ensure_ascii=False)
    w = World(reply=rep)
    w.ask("Байк сломался на второй день, очень недоволен")
    d = w.drafts()
    assert len(d) == 1 and json.loads(d[0][4]) and "жалоба" in json.loads(d[0][4]), d
    card = w.http.of("sendMessage")[0]
    assert "🙋 НУЖЕН ЧЕЛОВЕК" in card["text"] and "жалоба" in card["text"], card["text"]
    # причина кода — сработавший ярлык денег, а не весь перечень (WACARDCOMPACT0310)
    assert "повреждения и штрафы" in card["text"] and K.REASON_WORDS[K.R_MONEY] not in card["text"], card["text"]
    assert buttons(card) == ["wa:fix:1:1", "wa:no:1:1"], buttons(card)
    w.press("wa:send:1:1", 101)                                              # старая/подделанная кнопка
    assert w.door.sends == [] and w.answers()[-1] == A.HANDOFF_LOCK_WORDS[:G.ANSWER_MAX], w.answers()
    assert w.drafts()[0][1] == A.PENDING
    w.reply(101, "Очень жаль! Коллега Дарья уже звонит вам.")
    card2 = w.http.of("sendMessage")[1]
    assert buttons(card2) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], buttons(card2)
    assert "исправлено человеком" in card2["text"], card2["text"]
    w.press("wa:send:1:2", 102)
    assert w.door.sends == [(NUM, "Очень жаль! Коллега Дарья уже звонит вам.")], w.door.sends


def test_code_reason_alone_locks():
    w = World()                                   # модель причин не дала, код нашёл «скидка»
    w.ask("А скидку сделаете?")
    hand = json.loads(w.drafts()[0][4])
    assert K.REASON_WORDS[K.R_DISCOUNT] in hand, hand
    w.press("wa:send:1:1", 101)
    assert w.door.sends == [], w.door.sends


def test_broken_handoff_record_locks():
    w = World()
    w.ask("Спасибо!")
    w.core.db.execute("UPDATE drafts SET handoff='{битое' WHERE id=1")
    assert A.handoff_of("{битое") is None and A.handoff_of(None) == []
    w.press("wa:send:1:1", 101)
    assert w.door.sends == [] and w.answers()[-1] == A.HANDOFF_LOCK_WORDS[:G.ANSWER_MAX], w.answers()
    assert w.core.handoff(1) == [A.UNREAD_REASON]


def test_other_language_by_model_lang():
    rep = json.dumps({"text": "Hello!", "lang": "de", "handoff": [], "why": "x"})
    w = World(reply=rep)
    w.ask("Hallo")
    assert K.REASON_WORDS[K.R_LANGUAGE] in json.loads(w.drafts()[0][4]), w.drafts()


def test_thai_by_code():
    w = World()
    w.ask("สวัสดีครับ ราคาเท่าไหร่")
    assert K.REASON_WORDS[K.R_LANGUAGE] in json.loads(w.drafts()[0][4]), w.drafts()


def test_no_handoff_as_before():
    w = World()
    w.ask("Спасибо!")
    d = w.drafts()
    assert len(d) == 1 and d[0][4] is None, d
    card = w.http.of("sendMessage")[0]
    assert buttons(card) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"] and "НУЖЕН" not in card["text"]
    w.press("wa:send:1:1", 101)
    assert w.door.sends == [(NUM, "Добрый день! Подскажу.")], w.door.sends


def test_fenced_json_accepted():
    w = World(reply="```json\n" + OK_JSON + "\n```")
    w.ask("Привет")
    assert len(w.drafts()) == 1


# ═══ негативы ════════════════════════════════════════════════════════════════════════════

def test_not_json_no_draft_log_line():
    w = World(reply="Добрый день! Подскажу.")
    w.ask("Привет")
    assert len(w.call.calls) == 1 and w.drafts() == [], w.drafts()
    assert any("не JSON" in ln for ln in w.lines), w.lines
    assert w.http.of("sendMessage") == []
    nt = w.core.db.execute("SELECT next_try FROM clients WHERE number=?", (NUM,)).fetchone()[0]
    assert nt > T0, nt


def test_json_without_text_no_draft():
    w = World(reply=json.dumps({"text": " ", "lang": "ru", "handoff": [], "why": ""}))
    w.ask("Привет")
    assert w.drafts() == []


def test_drafts_off_model_not_called():
    for flag, calls in (("0", 0), ("1", 1)):
        w = World()
        env = {"queue_db": w.qpath, "agent_db": w.dbpath + flag, "mirror_db": "", "tg_token": "",
               "show_chat": ""}
        core, _tg, _f, words = SV.build(env, environ={"WA_AGENT_DRAFTS": flag}, model=w.adapter,
                                        clock=lambda: T0 + 500)
        core.tick(T0 - 1000)
        w.put(T0, "Привет")
        for k in range(30):
            core.tick(T0 + k * 10)
        assert len(w.call.calls) == calls, (flag, len(w.call.calls))
        assert words["WA_AGENT_DRAFTS"] == ("вкл" if calls else "выкл"), words


def test_price_without_dates_no_door():
    w = World()
    w.ask("Сколько стоит PCX 160 в сутки?")
    assert w.bridge.doors == [] and w.bridge.fleets == 0, (w.bridge.doors, w.bridge.fleets)
    assert "ЦЕНА:" not in w.call.calls[0][1]
    assert "без дат" in w.adapter.last["info"]["price_words"]
    assert len(w.drafts()) == 1


def test_price_season_cross_no_door_handoff():
    w = World()
    w.ask("price for PCX 160 from 25 Nov to 5 Dec?")
    assert w.bridge.doors == [], w.bridge.doors
    assert K.REASON_WORDS[K.R_SEASON_CROSS] in json.loads(w.drafts()[0][4])


def test_dates_without_price_question_no_door():
    w = World()
    w.ask("Нужен PCX 160 с 5 по 12 ноября, доставка в Патонг есть?")
    assert w.bridge.doors == [] and w.bridge.fleets == 0, (w.bridge.doors, w.bridge.fleets)
    assert w.adapter.last["info"]["price_words"] == "о цене не спрашивают"


def test_parse_reply_unit():
    assert WM.parse_reply('{"text": " ", "lang": "ru"}') is None
    assert WM.parse_reply('["text"]') is None
    assert WM.parse_reply("просто текст") is None
    got = WM.parse_reply('{"text": "Ок", "lang": "EN", "handoff": ["a", " ", "b"], "why": "w"}')
    assert got == {"text": "Ок", "lang": "en", "handoff": ["a", "b"], "why": "w"}, got


def test_model_crash_no_draft():
    w = World()

    def boom(system, user):
        raise RuntimeError("overloaded")
    w.adapter.call = boom
    w.ask("Привет")
    assert w.drafts() == [] and any("модель упала" in ln for ln in w.lines)


def test_node_unread_is_unknown_words():
    w = World()
    w.adapter.knowledge = K.Knowledge(lambda n: {"ok": False, "error": "x"})
    w.ask("Привет")
    assert "УЗЕЛ faq: НЕИЗВЕСТНО" in w.call.calls[0][1]


def test_find_dates_forms():
    import datetime
    t = datetime.date(2026, 10, 2)
    D = datetime.date
    assert WM.find_dates("с 5 по 12 ноября", t) == [D(2026, 11, 5), D(2026, 11, 12)]
    assert WM.find_dates("10.12 - 20.12", t) == [D(2026, 12, 10), D(2026, 12, 20)]
    assert WM.find_dates("from Nov 5 to Nov 12", t) == [D(2026, 11, 5), D(2026, 11, 12)]
    assert WM.find_dates("1 марта", t) == [D(2027, 3, 1)]
    assert WM.find_dates("сколько стоит pcx 160", t) == []


def test_journal_no_client_text():
    w = World()
    w.ask("СЕКРЕТНАЯ-ФРАЗА-КЛИЕНТА")
    assert not any("СЕКРЕТНАЯ" in ln or NUM in ln for ln in w.lines), w.lines


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
