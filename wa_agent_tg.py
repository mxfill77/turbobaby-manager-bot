#!/usr/bin/env python3
"""РУКИ TELEGRAM СЛУЖБЫ wa-agent — карточки черновиков и вопрос паузы в группе «TurboBaby · Агенты»,
приём нажатий и правок (WAAGENTTG0110, шаг 3 плана WAAGENTLIVE0110 §7).

ЧТО ЭТО. Реализация интерфейса `wa_agent.Telegram` плюс ЕДИНСТВЕННЫЙ читатель `getUpdates` бота
показа (`WA_TG_BOT_TOKEN`, тот же бот, что у wa-tg-mirror: служба показа шлёт им только исходящие,
`getUpdates` не зовёт; второй читатель получил бы 409). Решений здесь нет — кто нажал первым,
снят ли черновик, ушло ли сообщение, решает ядро; адаптер переводит нажатие в вызов ядра и
отвечает на нажатие СЛОВАМИ ЯДРА.

КАРТОЧКА. `sendMessage` в -1003999596406: «имя · +номер», ссылка на тему клиента в форуме показа,
текст черновика, кнопки `wa:send|fix|no:<черновик>:<версия>`. `card_done` — `editMessageText`
без клавиатуры (кнопки сняты). Вопрос паузы — кнопка `wa:go:<id клиента>:<пауза>`: в
`callback_data` номера телефона нет, id клиента — короткий номер строки своей таблицы.

«ИСПРАВИТЬ». Кнопка только подсказывает; правка — РЕПЛАЙ человека на карточку: `Core.revise` с
версией карточки, новая карточка версии +1, «Отправить» на ней шлёт текст человека дословно.
Реплай на прежнюю версию — «устарело».

ДОПУСК. Нажимают и правят люди группы: чат не тот — отказ словами; бот — отказ словами. Id и
имя нажавшего — в журнал; текстов и номеров клиентов в журнале нет.

ЦИКЛ. `run`: `getUpdates` (длинный опрос не дольше остатка до такта) и `Core.tick` раз в 5 с в
ОДНОМ потоке. Offset — в `meta` своей базы, обновление ниже offset не разбирается повторно.

ВЫКЛЮЧАТЕЛЬ. `WA_AGENT_CARDS` по умолчанию выключен: адаптер не делает ни одного вызова Telegram
(ни карточек, ни `getUpdates`), ядро тактует как без рук.
"""

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

import wa_agent

AGENTS_CHAT = -1003999596406       # «TurboBaby · Агенты»
FLAG_NAME = "WA_AGENT_CARDS"
TG_BASE = "https://api.telegram.org"
TICK_SECS = 5
TG_TEXT_MAX = 4000
ANSWER_MAX = 190                   # answerCallbackQuery: до 200 символов
ALLOWED_UPDATES = ["callback_query", "message"]

ACTIONS = {"send": wa_agent.ACT_SEND, "no": wa_agent.ACT_DECLINE}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_clients (
    cid     INTEGER PRIMARY KEY AUTOINCREMENT,      -- короткий id клиента для callback_data
    number  TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_cards (
    card_id   INTEGER PRIMARY KEY,                   -- message_id карточки в группе
    draft_id  INTEGER NOT NULL,
    ver       INTEGER NOT NULL,
    body      TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS tg_pauses (
    cid       INTEGER NOT NULL,
    pause_no  INTEGER NOT NULL,
    msg_id    INTEGER,
    body      TEXT,
    PRIMARY KEY (cid, pause_no)
);
"""


def flag_on(raw) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def http_request(method, url, headers=None, data=None, timeout=30):
    """Единственный выход в сеть. → (код HTTP или None, тело bytes). Исключения наружу не идут."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:                                            # noqa: BLE001
            body = b""
        return e.code, body
    except Exception as e:                                           # noqa: BLE001
        return None, type(e).__name__.encode()


def topic_link(show_chat, thread_id):
    """Ссылка на тему форума показа: https://t.me/c/<id без -100>/<тема>."""
    s = str(show_chat or "").strip()
    if not s.startswith("-100") or not thread_id:
        return ""
    return "https://t.me/c/%s/%d" % (s[4:], int(thread_id))


def who_of(user):
    name = " ".join(x for x in ((user or {}).get("first_name"), (user or {}).get("last_name")) if x)
    return "%s (id %s)" % (name or "без имени", (user or {}).get("id"))


class Tg(wa_agent.Telegram):
    def __init__(self, token, enabled=False, chat_id=AGENTS_CHAT, show_chat=None, mirror_db=None,
                 http=None, clock=time.time, log=None):
        self.token = token or ""
        self.enabled = bool(enabled) and bool(self.token)
        self.chat = int(chat_id)
        self.show_chat = show_chat
        self.mirror_db = mirror_db
        self.http = http or http_request
        self.clock = clock
        self.log = log or (lambda line: None)
        self.core = None
        self.db = None

    def bind(self, core):
        """Своя база — база ядра (offset в её meta, свои таблицы tg_*)."""
        self.core, self.db = core, core.db
        self.db.executescript(_SCHEMA)
        return self

    # ── вызов Bot API ─────────────────────────────────────────────────────────────────────

    def api(self, method, params, timeout=30):
        """→ (True, result) · (False, код|описание) · (None, 'net'). Выключено — сети нет вовсе."""
        if not self.enabled:
            return False, "выключено"
        status, body = self.http("POST", TG_BASE + "/bot" + self.token + "/" + method,
                                 {"Content-Type": "application/json"},
                                 json.dumps(params, ensure_ascii=False).encode("utf-8"), timeout)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:                                            # noqa: BLE001
            data = {}
        if status == 200 and data.get("ok"):
            return True, data.get("result")
        if status is None:
            self.log("telegram: %s без ответа" % method)
            return None, "net"
        self.log("telegram: %s HTTP %s %s" % (method, status, str(data.get("description") or "")[:120]))
        return False, status

    # ── клиент: короткий id, имя, тема ────────────────────────────────────────────────────

    def cid(self, number):
        self.db.execute("INSERT OR IGNORE INTO tg_clients(number) VALUES(?)", (number,))
        return self.db.execute("SELECT cid FROM tg_clients WHERE number=?", (number,)).fetchone()[0]

    def number_of(self, cid):
        row = self.db.execute("SELECT number FROM tg_clients WHERE cid=?", (int(cid),)).fetchone()
        return row[0] if row else None

    def _topic(self, number):
        """(имя темы показа, ссылка) — база показа только mode=ro; нет базы или темы — без ссылки."""
        if self.mirror_db and os.path.exists(self.mirror_db):
            try:
                conn = sqlite3.connect("file:%s?mode=ro" % self.mirror_db, uri=True, timeout=5)
                try:
                    row = conn.execute("SELECT thread_id, name FROM topics WHERE number=?",
                                       (number,)).fetchone()
                finally:
                    conn.close()
                if row:
                    return (row[1] or "без имени · +" + number.lstrip("+")), topic_link(self.show_chat, row[0])
            except Exception as e:                                   # noqa: BLE001
                self.log("база показа не прочитана: %s" % type(e).__name__)
        return "без имени · +" + number.lstrip("+"), ""

    def _head(self, number):
        name, link = self._topic(number)
        return name + "\n" + ("тема: " + link if link else "темы в показе нет")

    # ── интерфейс ядра ────────────────────────────────────────────────────────────────────

    def card(self, draft_id, ver, number, text):
        if not self.enabled:
            return None
        body = "📝 Черновик №%d · версия %d\n%s\n\n%s" % (draft_id, ver, self._head(number), text)
        if len(body) > TG_TEXT_MAX:
            body = body[:TG_TEXT_MAX - 60] + "\n… (показ обрезан; «Отправить» шлёт текст целиком)"
        kb = {"inline_keyboard": [[
            {"text": "✅ Отправить", "callback_data": "wa:send:%d:%d" % (draft_id, ver)},
            {"text": "✏️ Исправить", "callback_data": "wa:fix:%d:%d" % (draft_id, ver)},
            {"text": "✖️ Не нужно", "callback_data": "wa:no:%d:%d" % (draft_id, ver)}]]}
        ok, res = self.api("sendMessage", {"chat_id": self.chat, "text": body, "reply_markup": kb})
        if not ok:
            return None
        mid = int(res.get("message_id"))
        self.db.execute("INSERT OR REPLACE INTO tg_cards(card_id, draft_id, ver, body) VALUES(?,?,?,?)",
                        (mid, draft_id, ver, body))
        self.log("карточка: черновик %d версия %d → сообщение %d" % (draft_id, ver, mid))
        return mid

    def card_done(self, draft_id, card_id, words):
        """Карточка получает исход, кнопки снимаются (editMessageText без reply_markup)."""
        if not self.enabled or not card_id:
            return
        row = self.db.execute("SELECT body FROM tg_cards WHERE card_id=?", (int(card_id),)).fetchone()
        body = (row[0] if row else "📝 Черновик №%d" % draft_id)[:TG_TEXT_MAX - 200]
        self.api("editMessageText", {"chat_id": self.chat, "message_id": int(card_id),
                                     "text": body + "\n\n— " + words})

    def ask_pause(self, number, pause_no):
        if not self.enabled:
            return
        cid = self.cid(number)
        body = ("⏸ %s\nОтветили с телефона — агент на паузе с этим клиентом (пауза %d). "
                "Черновиков не будет до «Продолжить». Когда продолжать?" % (self._head(number), pause_no))
        kb = {"inline_keyboard": [[{"text": "▶️ Продолжить",
                                    "callback_data": "wa:go:%d:%d" % (cid, pause_no)}]]}
        ok, res = self.api("sendMessage", {"chat_id": self.chat, "text": body, "reply_markup": kb})
        mid = int(res.get("message_id")) if ok else None
        self.db.execute("INSERT OR REPLACE INTO tg_pauses(cid, pause_no, msg_id, body) VALUES(?,?,?,?)",
                        (cid, int(pause_no), mid, body))
        self.log("вопрос паузы: клиент %d пауза %d → сообщение %s" % (cid, pause_no, mid))

    # ── приём обновлений ──────────────────────────────────────────────────────────────────

    def offset(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='tg_offset'").fetchone()
        return int(row[0]) if row else 0

    def _set_offset(self, value):
        self.db.execute("INSERT INTO meta(key, value) VALUES('tg_offset', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(value)),))

    def poll(self, timeout=0):
        """Один getUpdates. → число разобранных обновлений или None (вызов не удался)."""
        if not self.enabled:
            return 0
        ok, res = self.api("getUpdates", {"offset": self.offset(), "timeout": int(max(0, timeout)),
                                          "allowed_updates": ALLOWED_UPDATES}, timeout=int(timeout) + 15)
        if not ok:
            if res == 409:
                self.log("getUpdates: 409 — у бота второй читатель, разбор стоит")
            return None
        n = 0
        for u in res or []:
            n += self.handle(u)
        return n

    def handle(self, u):
        """Одно обновление. Ниже offset — уже разобрано, пропуск. → 1 разобрано, 0 пропущено."""
        uid = int(u.get("update_id", -1))
        if uid < self.offset():
            self.log("обновление %d уже разобрано — пропуск" % uid)
            return 0
        try:
            if "callback_query" in u:
                self.on_press(u["callback_query"])
            elif "message" in u:
                self.on_message(u["message"])
        except Exception as e:                                       # noqa: BLE001
            self.log("обновление %d упало: %s" % (uid, type(e).__name__))
        self._set_offset(uid + 1)
        return 1

    def answer(self, cq_id, words):
        self.api("answerCallbackQuery", {"callback_query_id": cq_id, "text": str(words)[:ANSWER_MAX]})

    def on_press(self, cq):
        frm = cq.get("from") or {}
        chat = ((cq.get("message") or {}).get("chat") or {}).get("id")
        data = str(cq.get("data") or "")
        who = who_of(frm)
        self.log("нажатие: от %s · %s" % (who, data))
        if chat != self.chat:
            self.log("отказ: чужой чат %s" % chat)
            return self.answer(cq.get("id"), "отказ: эта кнопка решается только в группе «Агенты»")
        if frm.get("is_bot"):
            self.log("отказ: нажал бот %s" % who)
            return self.answer(cq.get("id"), "отказ: боты не нажимают — решает человек группы")
        parts = data.split(":")
        if len(parts) != 4 or parts[0] != "wa" or not (parts[2].isdigit() and parts[3].isdigit()):
            return self.answer(cq.get("id"), "неизвестная кнопка")
        act, a, b = parts[1], int(parts[2]), int(parts[3])
        if act == "go":
            return self._on_resume(cq, a, b, who)
        if act == "fix":
            row = self.db.execute("SELECT state, ver FROM drafts WHERE id=?", (a,)).fetchone()
            if row and row[0] == wa_agent.PENDING and row[1] == b:
                words = "ответьте реплаем на эту карточку своим текстом — будет версия %d, " \
                        "«Отправить» на ней шлёт ваш текст дословно" % (b + 1)
            else:
                words = self.core._decided(a, b)
            return self.answer(cq.get("id"), words)
        if act not in ACTIONS:
            return self.answer(cq.get("id"), "неизвестная кнопка")
        res = self.core.press(a, b, ACTIONS[act], who)
        self.log("нажатие: черновик %d версия %d %s → %s" % (a, b, act, res.get("state")))
        return self.answer(cq.get("id"), res.get("words"))

    def _on_resume(self, cq, cid, pause_no, who):
        number = self.number_of(cid)
        if not number:
            return self.answer(cq.get("id"), "клиент не найден")
        res = self.core.resume(number, pause_no, who)
        self.log("продолжить: клиент %d пауза %d → %s" % (cid, pause_no, "снята" if res["ok"] else "нет"))
        if res["ok"]:
            row = self.db.execute("SELECT msg_id, body FROM tg_pauses WHERE cid=? AND pause_no=?",
                                  (cid, pause_no)).fetchone()
            if row and row[0]:
                self.api("editMessageText", {"chat_id": self.chat, "message_id": int(row[0]),
                                             "text": (row[1] or "")[:TG_TEXT_MAX - 200] + "\n\n— продолжено: %s, %s"
                                             % (who, wa_agent._hm(self.clock()))})
        return self.answer(cq.get("id"), res["words"])

    def on_message(self, msg):
        """Правка — реплай человека на карточку. Остальные сообщения группы не трогаем."""
        chat = (msg.get("chat") or {}).get("id")
        if chat != self.chat:
            self.log("сообщение из чужого чата %s — пропуск" % chat)
            return
        reply = (msg.get("reply_to_message") or {}).get("message_id")
        card = self.db.execute("SELECT draft_id, ver FROM tg_cards WHERE card_id=?",
                               (reply,)).fetchone() if reply else None
        if not card:
            return
        frm = msg.get("from") or {}
        who = who_of(frm)
        if frm.get("is_bot"):
            self.log("отказ: правку прислал бот %s (черновик %d)" % (who, card[0]))
            return
        did, ver = card
        text = msg.get("text") or ""
        self.log("правка: от %s · черновик %d версия %d" % (who, did, ver))
        if self.core.revise(did, text, who, ver=ver):
            return
        words = "не принято: " + (self.core._decided(did, ver) if text.strip() else "нужен текст сообщения")
        self.api("sendMessage", {"chat_id": self.chat, "text": words,
                                 "reply_parameters": {"message_id": int(msg.get("message_id") or 0),
                                                      "allow_sending_without_reply": True}})


def run(core, tg, should_stop, clock=time.time, sleep=time.sleep, tick_secs=TICK_SECS, log=None):
    """Главный цикл: getUpdates и такт ядра в ОДНОМ потоке. Длинный опрос не дольше остатка до
    такта, поэтому такт идёт раз в tick_secs. Падение такта — строка журнала, не смерть цикла."""
    log = log or (lambda line: None)
    next_tick = clock()
    while not should_stop():
        now = clock()
        if tg.enabled:
            if tg.poll(timeout=max(0, int(next_tick - now))) is None:
                sleep(1)
        now = clock()
        if now >= next_tick:
            try:
                core.tick(now)
            except Exception as e:                                   # noqa: BLE001
                log("такт упал: %s" % type(e).__name__)
            next_tick = now + tick_secs
        elif not tg.enabled:
            sleep(max(0.0, next_tick - now))


if __name__ == "__main__":
    raise SystemExit("wa_agent_tg: руки Telegram (WAAGENTTG0110) — модели и юнита ещё нет; "
                     "запуск службы — шаги 4–5 плана WAAGENTLIVE0110 §7")
