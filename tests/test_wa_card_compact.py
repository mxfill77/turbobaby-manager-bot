#!/usr/bin/env python3
"""Компактная честная карточка черновика (WACARDCOMPACT0310): сверху полный ответ клиенту, он не режется;
до трёх действий сотрудника по сработавшим категориям; R_MONEY — сработавший ярлык; причины модели — дедуп
по категории; «why» модели не показывается; дверь закрыта — «отправка выключена» на любой версии; подсказка
про реплай. Всё на подделке Bot API и подделке двери: временные очередь и база, сети нет, модели нет.
Фразы клиентов выдуманы, номер выдуман.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import re
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
import wa_agent_tg as G  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — мир адаптера модели на подделках (мост, модель, Bot API)

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""

NUM = "10000000007"                      # выдуманный номер
CHAT = G.AGENTS_CHAT
SHOW = "-1004401325262"
T0 = 1_790_000_000
HUMAN = {"id": 501, "is_bot": False, "first_name": "Дарья"}
ANSWER = "Добрый день! Подскажу."


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


class FakeDoor(A.Door):
    """Дверь с пробой is_open, как у живой службы (WA_SEND)."""

    def __init__(self, open_=True):
        self.sends, self.open = [], open_

    def is_open(self):
        return self.open

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}


class FakeModel(A.Model):
    """Подделка адаптера: причины кода — K.handoff по фразе клиента, причины модели — дедуп по категории."""

    def __init__(self):
        self.ask, self.answer, self.extra, self.why, self.calls = "", ANSWER, [], "", 0

    def draft(self, number, upto_id):
        self.calls += 1
        code = [r["words"] for r in K.handoff(self.ask)]
        return {"text": self.answer, "handoff": K.merge_reasons(code, self.extra), "why": self.why}


class World:
    def __init__(self, door_open=True):
        d = tempfile.mkdtemp(prefix="wa_card_compact_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        self.mpath = os.path.join(d, "mirror.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        m = sqlite3.connect(self.mpath)
        m.execute("CREATE TABLE topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER, "
                  "stage TEXT, ts REAL, name TEXT)")
        m.execute("INSERT INTO topics VALUES(?,?,?,?,?,?)", (NUM, 42, 1, "live", T0, "Тест · +" + NUM))
        m.commit()
        m.close()
        self.http, self.door, self.model, self.lines = FakeHttp(), FakeDoor(door_open), FakeModel(), []
        self.uid = 1000
        self.tg = G.Tg("123:SECRET", enabled=True, show_chat=SHOW, mirror_db=self.mpath, http=self.http,
                       clock=lambda: T0 + 500, log=self.lines.append)
        self.core = A.Core(self.dbpath, self.qpath, self.model, self.tg, self.door,
                           clock=lambda: T0 + 500, log=self.lines.append)
        self.tg.bind(self.core)
        self.core.tick(T0 - 1000)

    def draft(self, ask, answer=ANSWER, extra=(), why=""):
        """Фраза клиента → черновик → сообщения карточки (последнее — с кнопками)."""
        self.model.ask, self.model.answer, self.model.extra, self.model.why = ask, answer, list(extra), why
        q = sqlite3.connect(self.qpath)
        q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                  "VALUES(?,?,?,?,?,0,0)", (T0, NUM, "text", "x", T0))
        q.commit()
        q.close()
        self.core.tick(T0 + A.QUIET_DEFAULT)
        return self.http.of("sendMessage")

    def feed(self, *updates):
        self.http.updates.append(list(updates))
        return self.tg.poll()

    def reply(self, card_id, text):
        self.uid += 1
        return {"update_id": self.uid, "message": {"message_id": 900 + self.uid, "from": HUMAN,
                                                   "chat": {"id": CHAT}, "text": text,
                                                   "reply_to_message": {"message_id": card_id}}}

    def press(self, data, card_id):
        self.uid += 1
        return {"update_id": self.uid, "callback_query": {"id": "cq%d" % self.uid, "from": HUMAN, "data": data,
                                                          "message": {"message_id": card_id, "chat": {"id": CHAT}}}}

    def state(self, did=1):
        db = sqlite3.connect(self.dbpath)
        row = db.execute("SELECT state, ver, text FROM drafts WHERE id=?", (did,)).fetchone()
        db.close()
        return row


def card(msgs):
    """Карточка — сообщение с кнопками (последнее)."""
    with_kb = [p for p in msgs if "reply_markup" in p]
    assert with_kb, msgs
    return with_kb[-1]


def actions(text):
    return [ln[2:] for ln in text.split("\n") if ln.startswith("• ")]


def buttons(p):
    return [b["callback_data"] for row in p["reply_markup"]["inline_keyboard"] for b in row]


# ═══ проверки Штаба (п.5) ════════════════════════════════════════════════════════════════

def test_deposit_question_only_deposit():
    q = "Какой депозит нужен за PCX на неделю?"
    assert [r["words"] for r in K.handoff(q)] == ["депозит"], K.handoff(q)
    w = World()
    t = card(w.draft(q))["text"]
    assert actions(t) == [G.CARD_ACTIONS[K.MONEY_DEPOSIT]], actions(t)
    low = t.lower()
    assert not any(bad in low for bad in ("поврежд", "штраф", "спор", "оплат")), t


def test_thanks_with_payment_word_no_damage():
    q = "Спасибо большое за информацию об оплате!"
    w = World()
    t = card(w.draft(q))["text"]
    low = t.lower()
    assert "поврежд" not in low and "штраф" not in low, t
    assert actions(t) == [G.CARD_ACTIONS[K.MONEY_PAYMENT]], actions(t)


def test_booking_negation_no_confirm_action():
    q = "Нет, бронировать пока не буду, просто хотел узнать цену"
    w = World()
    t = card(w.draft(q))["text"]
    assert "подтверд" not in t.lower(), t
    assert actions(t) == [G.CARD_ACTIONS[K.R_AVAILABILITY]], actions(t)


def test_payment_confirmation_is_payment():
    q = "Оплатил, перевёл 3000 бат, вот чек"
    w = World()
    t = card(w.draft(q))["text"]
    assert actions(t) == [G.CARD_ACTIONS[K.MONEY_PAYMENT]], actions(t)
    assert "депозит" not in t.lower() and "поврежд" not in t.lower(), t


def test_long_answer_two_messages_whole():
    answer = "Ответ клиенту без сокращений. " * 128 + "КОНЕЦ-ОТВЕТА"       # 3852 знака
    w = World()
    msgs = w.draft("Какой депозит?", answer=answer)
    assert len(msgs) == 2, [len(p["text"]) for p in msgs]
    assert "reply_markup" not in msgs[0] and answer in msgs[0]["text"], msgs[0]["text"][-80:]
    c = card(msgs)
    assert ("%d знаков" % len(answer)) in c["text"] and "сообщением выше" in c["text"], c["text"]
    assert G.W_HINT in c["text"] and actions(c["text"]) == [G.CARD_ACTIONS[K.MONEY_DEPOSIT]], c["text"]
    assert all(len(p["text"]) <= G.TG_TEXT_MAX for p in msgs) and len(c["text"]) <= G.CARD_ROOM
    # реплай на сообщение с ответом — та же правка, что реплай на карточку
    w.feed(w.reply(101, "Короткий готовый текст."))
    assert w.state()[:2] == (A.PENDING, 2), w.state()


def test_v2_door_closed_says_send_off():
    w = World(door_open=False)
    c1 = card(w.draft("Какой депозит нужен?"))
    assert G.W_DOOR_CLOSED in c1["text"], c1["text"]
    w.feed(w.reply(101, "Депозит — коллега уточнит."))
    c2 = card(w.http.of("sendMessage")[1:])
    assert "версия 2" in c2["text"] and G.W_DOOR_CLOSED in c2["text"], c2["text"]
    assert "«Отправить» открыто" not in c2["text"], c2["text"]
    # без причин — тоже: дверь закрыта на любой карточке
    w2 = World(door_open=False)
    assert G.W_DOOR_CLOSED in card(w2.draft("Привет"))["text"]
    # контроль: дверь открыта — прежнее «исправлено человеком — «Отправить» открыто»
    w3 = World(door_open=True)
    w3.draft("Какой депозит нужен?")
    w3.feed(w3.reply(101, "Депозит — коллега уточнит."))
    c3 = card(w3.http.of("sendMessage")[1:])
    assert G.W_SEND_OPEN in c3["text"] and G.W_DOOR_CLOSED not in c3["text"], c3["text"]


def test_reply_make_shorter_v2_with_hint():
    w = World()
    c1 = card(w.draft("Сколько стоит PCX на неделю?"))
    assert G.W_HINT in c1["text"], c1["text"]
    w.feed(w.reply(101, "сделай короче"))
    assert w.state() == (A.PENDING, 2, "сделай короче"), w.state()
    c2 = card(w.http.of("sendMessage")[1:])
    assert c2["text"].split("\n\n")[1] == "сделай короче", c2["text"]       # реплай целиком стал ответом
    assert G.W_HINT in c2["text"] and "версия 2" in c2["text"], c2["text"]
    assert w.model.calls == 1, w.model.calls                                 # модель не звалась


# ═══ ветки правки ════════════════════════════════════════════════════════════════════════

def _alts(pattern):
    return set(pattern.split("|"))


def test_money_labels_union_equals_trigger():
    trig = dict(K._TEXT_RULES)[K.R_MONEY]
    subs = set()
    for _key, _words, rx in K.MONEY_LABELS:
        subs |= _alts(rx.pattern)
    assert subs == _alts(trig.pattern), (subs ^ _alts(trig.pattern))
    for t in ("Какой депозит?", "Спасибо за информацию об оплате", "царапина на крыле", "I paid by transfer",
              "хочу спортбайк", "жалоба на сервис", "верните залог", "привет", "a scratch and a fine",
              "переводчик нужен", "чек пришёл", "спорт"):
        hit = bool(trig.search(t))
        assert hit == (K.R_MONEY in [r["reason"] for r in K.handoff(t)]) == bool(K.money_labels(t)), t


def test_model_reasons_dedup_by_category():
    got = K.merge_reasons(["депозит"], ["Клиент спрашивает про депозит", "жалоба", "Жалоба на сервис",
                                       "позвонить клиенту", "Позвонить клиенту."])
    assert got == ["депозит", "жалоба", "позвонить клиенту"], got
    assert K.merge_reasons(["депозит"], ["бронь и депозит"]) == ["депозит", "бронь и депозит"]
    assert K.merge_reasons([], ["депозит?"]) == ["депозит?"]                 # непустое пустым не становится
    assert K.merge_reasons([], []) == []


def test_adapter_dedup_and_label():
    rep = json.dumps({"text": "Депозит уточнит коллега.", "lang": "ru",
                      "handoff": ["вопрос о депозите", "депозит"], "why": "вопрос"}, ensure_ascii=False)
    w = TM.World(reply=rep)
    w.ask("Какой депозит за PCX?")
    assert json.loads(w.drafts()[0][4]) == ["депозит"], w.drafts()
    t = w.http.of("sendMessage")[0]["text"]
    assert actions(t) == [G.CARD_ACTIONS[K.MONEY_DEPOSIT]], t


def test_why_not_on_card():
    w = World()
    msgs = w.draft("Какой депозит?", why="ФАКТ-МОДЕЛИ: клиент уже оплатил")
    assert not any("ФАКТ-МОДЕЛИ" in p["text"] for p in msgs), msgs


def test_actions_max_three_details_full():
    q = "Свободен ли байк? Скидку дадите? Какой депозит? Оплатил переводом. Был штраф."
    w = World()
    t = card(w.draft(q))["text"]
    acts = actions(t)
    assert len(acts) == 4 and acts[-1] == "ещё 2 — в подробностях", acts
    words = [r["words"] for r in K.handoff(q)]
    assert len(words) == 5 and ("основания (5): " + "; ".join(words)) in t, (words, t)


def test_details_cut_hidden_counted():
    top, notes, details = "T", "N" * 100, "D" * 500
    answer = "A" * (G.CARD_ROOM - len(top) - 4 - len(notes) - 300)
    texts = G.card_texts(top, answer, notes, details)
    assert len(texts) == 1 and len(texts[0]) <= G.CARD_ROOM, [len(x) for x in texts]
    assert answer in texts[0]
    m = re.search(r"скрыто знаков подробностей: (\d+)", texts[0])
    assert m and texts[0].count("D") + int(m.group(1)) == len(details), texts[0][-120:]
    # ответ длиннее одного сообщения Telegram — несколькими подряд, без потерь
    big = "Б" * 9000
    many = G.card_texts(top, big, notes, details)
    joined = "".join(many[:-1])
    assert len(many) == 4 and big in joined.replace(top + G.W_ANSWER_LEAD, "", 1), [len(x) for x in many]
    assert all(len(x) <= G.TG_TEXT_MAX for x in many)


def test_lock_and_buttons_unchanged():
    w = World()
    c1 = card(w.draft("Какой депозит?"))
    assert buttons(c1) == ["wa:fix:1:1", "wa:no:1:1"], buttons(c1)
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [] and w.state()[0] == A.PENDING
    w.feed(w.reply(101, "Готовый текст."))
    c2 = card(w.http.of("sendMessage")[1:])
    assert buttons(c2) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], buttons(c2)
    w.feed(w.press("wa:send:1:2", 102))
    assert w.door.sends == [(NUM, "Готовый текст.")], w.door.sends


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
