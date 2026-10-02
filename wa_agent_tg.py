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
без клавиатуры (кнопки сняты). `card_wait` — «уйдёт в ЧЧ:ММ» и кнопка `wa:cancel:…` (ритм, WAHUMANPACE0210). Вопрос паузы — кнопка `wa:go:<id клиента>:<пауза>`: в
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

РЕАКЦИИ НАРУЖУ (WAREACTOUT0110). Человек ставит или снимает реакцию на сообщении темы форума показа —
та же реакция уходит клиенту в WhatsApp на то же сообщение. Читатель тот же (второй читатель бота
получил бы 409): `allowed_updates` + `message_reaction`, бот — админ форума показа. Сообщение темы
сводится к wamid по базе показа (`shown.msg_id`, ключ один в сообщении, только mode=ro) и виду строки
очереди (только сообщение клиента или наше, только mode=ro); wamid нет — наружу ничего, строка журнала.
Реакция уходит дверью `wa_send.send_reaction` (WA_SEND, ключ, окно 24 ч). У бизнеса в WhatsApp ОДНА
реакция на сообщение: держится последняя из реакций людей группы; снял последний — снятие. Одно
изменение — одна отправка: то, что уже уходило на это сообщение (любым исходом), второй раз не шлётся.
Выключатель `WA_AGENT_REACT` по умолчанию выключен — реакции не читаются и не отправляются.

ТЕМА КЛИЕНТА → WHATSAPP (WARELAYTEXT0210). Текст человека в теме клиента форума показа уходит клиенту
(`Core.relay`, дверь `wa_send.send_text`: WA_SEND, ключ, окно 24 ч). Читатель тот же: `allowed_updates`
+ message, edited_message. Тема → номер — `topics` базы показа (mode=ro); общая тема и тема без номера
наружу не идут; бот (и «от имени группы») — тоже. Исход в теме: отправлено — реакция бота 👌 на
сообщение человека; не отправлено — ответ с причиной словами; неизвестно — «не знаю, дошло ли», без
повтора. Правка — не уходит, одна строка в ответ. Удаление сообщения Bot API боту не присылает.
«Отправить» по черновику — строкой «мы · агент, отправил <имя>: текст» в теме клиента.
Выключатель `WA_AGENT_RELAY` по умолчанию выключен — сообщения тем не читаются и не отправляются.

УРОКИ ЛЮДЕЙ (WAAGENTLESSON0210). Принятое «Исправить» при включённых уроках — на новой карточке строка
«📚 урок №N записан кандидатом», ниже отдельным сообщением урок: было/стало, автор, источник и кнопка
«📚 Сделать правилом» `wa:rule:<урок>:0`. Реплай на сообщение кандидата — причина урока. Право перевода и
отката — у ядра (`Core.lesson_admin`, id Telegram нажавшего); остальным — отказ словами ядра. Действующий
урок получает кнопку «↩️ Откатить №N» `wa:unrule:<урок>:0`; откат по номеру — и текстом «откатить №N» в
группе. В журнал — номер урока, кто и исход; было/стало и причины в журнале нет.

МЕДИА ИЗ ТЕМЫ → WHATSAPP (WARELAYMEDIA0210). Фото, видео (и гиф, и кружок), документ, голосовое, аудио,
статичный стикер и место из темы клиента уходят клиенту своим видом (`media_of` → `Core.relay(media=…)` →
`wa_send.send_media`): файл берётся `getFile` и скачивается В ПАМЯТЬ (`Tg.download`, на диск не ложится),
дверь грузит его в 360dialog и шлёт. Голосовое Telegram (OGG/Opus) — аудио WhatsApp. Предел — меньший из
Bot API (20 МБ) и WhatsApp по виду; больше — ответ в теме с размером и пределом, наружу ничего. Альбом —
это отдельные сообщения Telegram: каждый файл — своим сообщением со своим ключом, подпись — та, что у
файла (у альбома Telegram держит её на первом). Вид без пары (контакт, опрос, живая геоточка,
анимированный стикер, …) — ответ в теме, что он в WhatsApp не отправляется. Исход — как у текста.
"""

import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request

import wa_agent
import wa_kind
import wa_send

AGENTS_CHAT = -1003999596406       # «TurboBaby · Агенты»
FLAG_NAME = "WA_AGENT_CARDS"
TG_BASE = "https://api.telegram.org"
TICK_SECS = 5
TG_TEXT_MAX = 4000
ANSWER_MAX = 190                   # answerCallbackQuery: до 200 символов
ALLOWED_UPDATES = ["callback_query", "message"]
REACT_FLAG = "WA_AGENT_REACT"
REACT_UPDATE = "message_reaction"
REACT_KINDS = (wa_kind.KIND_INBOUND, wa_kind.KIND_ECHO)   # на что реакция уходит клиенту
RELAY_FLAG = "WA_AGENT_RELAY"     # тема клиента → WhatsApp (WARELAYTEXT0210), по умолчанию выключен
RELAY_UPDATES = ["message", "edited_message"]
RELAY_SENT_EMOJI = "👌"           # отправлено — реакция бота из набора Telegram на сообщение человека
RELAY_EDIT_WORDS = ("правка в WhatsApp не передаётся — клиент видит первый текст; "
                    "поправку напишите новым сообщением")
# Медиа из темы (WARELAYMEDIA0210)
TG_GET_MAX = 20 * 1024 * 1024      # Bot API getFile: боту отдаётся файл до 20 МБ
TG_FILE_TIMEOUT = 120
RELAY_NO_PAIR = "не отправлено: %s в WhatsApp из темы не отправляется — наружу ничего"
RELAY_NO_CAPTION = "ушло без подписи: у %s в WhatsApp подписи нет — напишите её отдельным сообщением"
NO_CAPTION_GEN = {"voice": "голосового", "audio": "аудио", "sticker": "стикера"}
NO_PAIR = (("contact", "контакт"), ("poll", "опрос"), ("dice", "кубик"), ("game", "игра"),
           ("story", "история"), ("paid_media", "платное медиа"), ("invoice", "счёт"),
           ("giveaway", "розыгрыш"), ("checklist", "список задач"))
AGENT_LINE = "мы · агент, отправил %s: %s"
POLL_RETRY_SEC = 1                 # getUpdates не удался — следующий опрос не раньше
CONFLICT_PAUSE = 30                # 409 (второй читатель) — следующий опрос не раньше; такт идёт

# Сведение Telegram → WhatsApp. Набор реакций Telegram — обычные эмодзи Unicode, WhatsApp принимает
# любое эмодзи, поэтому каждое из набора уходит как есть; семь записаны в Telegram без U+FE0F
# (текстовое начертание по умолчанию) — клиенту уходит полная форма, иначе он увидит значок шрифта.
# Вне набора у Telegram только custom_emoji (премиум) и paid (звёзды): в WhatsApp их нет — не шлём,
# строка журнала; для итога сообщения такая реакция человека — «нет реакции».
WA_FULL_FORM = {
    "❤": "❤️",                                   # ❤
    "❤‍\U0001F525": "❤️‍\U0001F525",   # ❤‍🔥
    "\U0001F54A": "\U0001F54A️",                           # 🕊
    "✍": "✍️",                                   # ✍
    "☃": "☃️",                                   # ☃
    "\U0001F937‍♂": "\U0001F937‍♂️",   # 🤷‍♂
    "\U0001F937‍♀": "\U0001F937‍♀️",   # 🤷‍♀
}

ACTIONS = {"send": wa_agent.ACT_SEND, "no": wa_agent.ACT_DECLINE,
           "cancel": wa_agent.ACT_CANCEL}         # «Отменить» отложенного по ритму (WAHUMANPACE0210)

# уроки людей (WAAGENTLESSON0210)
LESSON_TEXT_MAX = 1500                            # было/стало в сообщении урока, символов
RX_ROLLBACK = re.compile(r"(?i)^\s*откатить\s+(?:урок\s+)?№?\s*(\d+)\s*$")

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
CREATE TABLE IF NOT EXISTS tg_reacts (
    msg_id    INTEGER NOT NULL,                      -- сообщение темы форума показа
    who       TEXT    NOT NULL,                      -- человек группы (u<id> / chat<id> анонимно)
    emoji     TEXT    NOT NULL,                      -- его реакция из набора Telegram
    seq       INTEGER NOT NULL,                      -- update_id: последняя побеждает
    PRIMARY KEY (msg_id, who)
);
CREATE TABLE IF NOT EXISTS tg_lessons (
    lesson_id INTEGER PRIMARY KEY,                   -- номер урока (lessons.id ядра)
    msg_id    INTEGER,                               -- сообщение урока в группе
    body      TEXT
);
CREATE TABLE IF NOT EXISTS tg_react_out (
    msg_id    INTEGER PRIMARY KEY,                   -- что уже уходило клиенту на это сообщение
    wamid     TEXT,
    emoji     TEXT,                                  -- '' — снятие
    outcome   TEXT,                                  -- sending до двери, потом исход двери
    ts        REAL
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


def tg_standard(reactions):
    """new_reaction → (эмодзи из набора Telegram или '', [виды вне набора]). У человека-премиума
    реакций до трёх — берётся последняя обычная: у бизнеса в WhatsApp реакция одна."""
    emoji, other = "", []
    for r in reactions or []:
        if (r or {}).get("type") == "emoji" and r.get("emoji"):
            emoji = r["emoji"]
        else:
            other.append(str((r or {}).get("type") or "?"))
    return emoji, other


def media_of(msg):
    """Сообщение темы → (медиа для `wa_send.send_media` | None, вид без пары словами | None).
    Медиа: kind — вид WhatsApp, label — что прислал человек (голосовое уходит аудио), file_id, size
    (по описанию Telegram), mime, filename, caption, fetch_max; у места — координаты, название, адрес.
    (None, None) — служебное сообщение без вложения: молча."""
    cap = msg.get("caption") or ""

    def f(kind, obj, mime, label=None, filename=""):
        return {"kind": kind, "label": label or kind, "file_id": obj.get("file_id"),
                "size": int(obj.get("file_size") or 0), "mime": str(mime or "").lower(),
                "filename": filename, "caption": cap, "fetch_max": TG_GET_MAX}, None

    if msg.get("photo"):
        sizes = [x for x in msg["photo"] if isinstance(x, dict) and x.get("file_id")]
        lim = min(TG_GET_MAX, wa_send.MEDIA_MAX["image"])
        fit = [x for x in sizes if int(x.get("file_size") or 0) <= lim]
        if not sizes:
            return None, "фото без файла"
        return f("image", (fit or sizes)[-1], "image/jpeg")          # Bot API: размеры по возрастанию
    if msg.get("animation"):
        a = msg["animation"]
        return f("video", a, a.get("mime_type") or "video/mp4")
    if msg.get("video"):
        v = msg["video"]
        return f("video", v, v.get("mime_type") or "video/mp4")
    if msg.get("video_note"):
        return f("video", msg["video_note"], "video/mp4")
    if msg.get("voice"):
        v = msg["voice"]
        return f("audio", v, v.get("mime_type") or "audio/ogg", label="voice")
    if msg.get("audio"):
        a = msg["audio"]
        return f("audio", a, a.get("mime_type") or "", filename=a.get("file_name") or "")
    if msg.get("document"):
        d = msg["document"]
        mime = str(d.get("mime_type") or "").lower()
        kind = next((k for k in ("document", "image", "video", "audio") if mime in wa_send.MEDIA_MIMES[k]),
                    "document")
        return f(kind, d, mime, filename=d.get("file_name") or "")
    if msg.get("sticker"):
        st = msg["sticker"]
        if st.get("is_animated") or st.get("is_video"):
            return None, "анимированный стикер"
        return f("sticker", st, "image/webp")
    if msg.get("location"):
        loc, venue = msg["location"], msg.get("venue") or {}
        if loc.get("live_period") and not venue:
            return None, "живая геоточка"
        return {"kind": "location", "label": "location", "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"), "name": venue.get("title") or "",
                "address": venue.get("address") or ""}, None
    for key, word in NO_PAIR:
        if msg.get(key):
            return None, word
    return None, None


def wa_emoji(tg) -> str:
    """Эмодзи реакции Telegram → эмодзи для WhatsApp (полная форма); '' остаётся '' — снятие."""
    return WA_FULL_FORM.get(tg, tg or "")


class Tg(wa_agent.Telegram):
    def __init__(self, token, enabled=False, chat_id=AGENTS_CHAT, show_chat=None, mirror_db=None,
                 http=None, clock=time.time, log=None, react=False, react_send=None, relay=False, watch=False):
        self.token = token or ""
        self.enabled = bool(enabled) and bool(self.token)
        self.react = bool(react) and bool(self.token)
        self.relay = bool(relay) and bool(self.token)
        # ожидание «клиент без ответа» (WAUNANSWERED0210): только пишет в «Агенты», читателя не заводит
        self.watch = bool(watch) and bool(token)
        self.react_send = react_send
        self.chat = int(chat_id)
        self.show_chat = show_chat
        self.mirror_db = mirror_db
        self.http = http or http_request
        self.clock = clock
        self.log = log or (lambda line: None)
        self.core = None
        self.db = None
        self.polls = {"ok": 0, "fail": 0, "conflict": 0}   # числа для сводки службы
        self.conflict = False                               # идёт серия 409

    def bind(self, core):
        """Своя база — база ядра (offset в её meta, свои таблицы tg_*)."""
        self.core, self.db = core, core.db
        self.db.executescript(_SCHEMA)
        return self

    @property
    def reading(self):
        """Читатель обновлений нужен, если включены карточки, реакции или тема → WhatsApp."""
        return self.enabled or self.react or self.relay

    # ── вызов Bot API ─────────────────────────────────────────────────────────────────────

    def api(self, method, params, timeout=30, quiet=()):
        """→ (True, result) · (False, код|описание) · (None, 'net'). Выключено — сети нет вовсе.
        quiet — коды, которые вызывающий пишет в журнал сам (409 опроса — одной строкой на серию)."""
        if not (self.reading or self.watch):
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
        if status not in quiet:
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
        # «нужен человек» (WAAGENTMODEL0210): пометка с причинами; на версии модели «Отправить» нет —
        # оно появляется на исправленной версии (замок в ядре тот же: Core.send_locked)
        probe = getattr(self.core, "handoff", None)
        hand = probe(draft_id) if probe else []
        mark = ""
        if hand:
            mark = "🙋 НУЖЕН ЧЕЛОВЕК: " + "; ".join(hand) + "\n" + (
                "«Отправить» — после «Исправить» (ответьте реплаем своим текстом)\n" if ver == 1
                else "исправлено человеком — «Отправить» открыто\n")
        # урок людей (WAAGENTLESSON0210): эта версия — правка, записанная кандидатом урока
        lesson = getattr(self.core, "lesson_of", None)
        lesson = lesson(draft_id, ver) if lesson and ver > 1 else None
        if lesson:
            mark += "📚 урок №%d записан кандидатом — «Сделать правилом» под ним\n" % lesson
        # напоминание притихшему (WAFOLLOWUP0210): помечено — это не ответ на сообщение клиента
        kind = getattr(self.core, "draft_kind", None)
        follow = bool(kind) and kind(draft_id) == wa_agent.KIND_FOLLOW
        if follow:
            mark = ("🔔 НАПОМИНАНИЕ — клиент молчит после нашего ответа; написал сам до нажатия — карточка "
                    "«устарело»\n") + mark
        body = "%s №%d · версия %d\n%s\n%s\n%s" % ("🔔 Напоминание" if follow else "📝 Черновик", draft_id, ver,
                                                   self._head(number), mark, text)
        if len(body) > TG_TEXT_MAX:
            body = body[:TG_TEXT_MAX - 60] + "\n… (показ обрезан; «Отправить» шлёт текст целиком)"
        row = [{"text": "✏️ Исправить", "callback_data": "wa:fix:%d:%d" % (draft_id, ver)},
               {"text": "✖️ Не нужно", "callback_data": "wa:no:%d:%d" % (draft_id, ver)}]
        if not (hand and ver == 1):
            row.insert(0, {"text": "✅ Отправить", "callback_data": "wa:send:%d:%d" % (draft_id, ver)})
        kb = {"inline_keyboard": [row]}
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

    def card_wait(self, draft_id, card_id, words, ver):
        """«Отправить» до срока ритма (WAHUMANPACE0210): «уйдёт в ЧЧ:ММ» и одна кнопка «Отменить»
        `wa:cancel:<черновик>:<версия>`. В срок `card_done` снимет её вместе с исходом."""
        if not self.enabled or not card_id:
            return
        row = self.db.execute("SELECT body FROM tg_cards WHERE card_id=?", (int(card_id),)).fetchone()
        body = (row[0] if row else "📝 Черновик №%d" % draft_id)[:TG_TEXT_MAX - 200]
        kb = {"inline_keyboard": [[{"text": "↩️ Отменить", "callback_data": "wa:cancel:%d:%d" % (draft_id, ver)}]]}
        self.api("editMessageText", {"chat_id": self.chat, "message_id": int(card_id),
                                     "text": body + "\n\n— ⏳ " + words, "reply_markup": kb})

    # ── уроки людей (WAAGENTLESSON0210) ───────────────────────────────────────────────────

    def _lesson_body(self, lesson_id):
        row = self.db.execute("SELECT state, author, ts, draft_id, ver_from, ver_to, was_text, now_text, reason "
                              "FROM lessons WHERE id=?", (int(lesson_id),)).fetchone()
        if not row:
            return None, None
        state, author, ts, did, v1, v2, was, now, reason = row

        def cut(s):
            s = str(s or "")
            return s if len(s) <= LESSON_TEXT_MAX else s[:LESSON_TEXT_MAX] + " … (обрезано в показе)"
        return state, ("📚 Урок №%d · %s\nисправил: %s, %s · черновик №%d, версия %d → %d\nбыло: %s\nстало: %s\n"
                       "причина: %s\nВ промпт агента идёт только действующее правило; перевод — «Сделать "
                       "правилом» (владелец или список WA_AGENT_LESSON_ADMINS)."
                       % (int(lesson_id), {"candidate": "кандидат", "active": "действующее правило",
                                           "rolled_back": "откатан"}.get(state, state),
                          author, wa_agent._hm(ts), did, v1, v2, cut(was), cut(now),
                          cut(reason) if reason else "— (ответьте реплаем на это сообщение — запишу причиной)"))

    @staticmethod
    def _lesson_kb(lesson_id, state):
        if state == wa_agent.LESSON_CANDIDATE:
            return {"inline_keyboard": [[{"text": "📚 Сделать правилом",
                                          "callback_data": "wa:rule:%d:0" % int(lesson_id)}]]}
        if state == wa_agent.LESSON_ACTIVE:
            return {"inline_keyboard": [[{"text": "↩️ Откатить №%d" % int(lesson_id),
                                          "callback_data": "wa:unrule:%d:0" % int(lesson_id)}]]}
        return None

    def lesson_card(self, lesson_id):
        """Кандидат урока — отдельное сообщение в «Агенты» с кнопкой «Сделать правилом»."""
        if not self.enabled:
            return None
        state, body = self._lesson_body(lesson_id)
        if body is None:
            return None
        ok, res = self.api("sendMessage", {"chat_id": self.chat, "text": body[:TG_TEXT_MAX],
                                           "reply_markup": self._lesson_kb(lesson_id, state)})
        mid = int(res.get("message_id")) if ok else None
        self.db.execute("INSERT OR REPLACE INTO tg_lessons(lesson_id, msg_id, body) VALUES(?,?,?)",
                        (int(lesson_id), mid, body))
        self.log("урок %d: сообщение кандидата → %s" % (int(lesson_id), mid))
        return mid

    def lesson_done(self, lesson_id, words, state):
        """Перевод или откат: сообщение урока получает исход; у действующего — кнопка «Откатить №N»."""
        if not self.enabled:
            return
        row = self.db.execute("SELECT msg_id FROM tg_lessons WHERE lesson_id=?", (int(lesson_id),)).fetchone()
        if not row or not row[0]:
            return
        _state, body = self._lesson_body(lesson_id)
        params = {"chat_id": self.chat, "message_id": int(row[0]),
                  "text": (body or "📚 Урок №%d" % int(lesson_id))[:TG_TEXT_MAX - 200] + "\n\n— " + words}
        kb = self._lesson_kb(lesson_id, state)
        if kb:
            params["reply_markup"] = kb
        self.api("editMessageText", params)

    def _lesson_show(self, lesson_id):
        """Сообщение кандидата заново (причина записана): тело из базы, кнопка по состоянию."""
        row = self.db.execute("SELECT msg_id FROM tg_lessons WHERE lesson_id=?", (int(lesson_id),)).fetchone()
        state, body = self._lesson_body(lesson_id)
        if not row or not row[0] or body is None:
            return
        params = {"chat_id": self.chat, "message_id": int(row[0]), "text": body[:TG_TEXT_MAX]}
        kb = self._lesson_kb(lesson_id, state)
        if kb:
            params["reply_markup"] = kb
        self.api("editMessageText", params)

    def _say(self, msg, words):
        self.api("sendMessage", {"chat_id": self.chat, "text": words,
                                 "reply_parameters": {"message_id": int(msg.get("message_id") or 0),
                                                      "allow_sending_without_reply": True}})

    def ask_pause(self, number, pause_no, via=None):
        if not self.enabled:
            return
        cid = self.cid(number)
        body = ("⏸ %s\n%s — агент на паузе с этим клиентом (пауза %d). "
                "Черновиков не будет до «Продолжить». Когда продолжать?"
                % (self._head(number), "Человек написал клиенту в теме" if via else "Ответили с телефона",
                   pause_no))
        kb = {"inline_keyboard": [[{"text": "▶️ Продолжить",
                                    "callback_data": "wa:go:%d:%d" % (cid, pause_no)}]]}
        ok, res = self.api("sendMessage", {"chat_id": self.chat, "text": body, "reply_markup": kb})
        mid = int(res.get("message_id")) if ok else None
        self.db.execute("INSERT OR REPLACE INTO tg_pauses(cid, pause_no, msg_id, body) VALUES(?,?,?,?)",
                        (cid, int(pause_no), mid, body))
        self.log("вопрос паузы: клиент %d пауза %d → сообщение %s" % (cid, pause_no, mid))

    def watch_alarm(self, number, text):
        """Тревога ожидания «клиент без ответа» (WAUNANSWERED0210) — одно сообщение в «Агенты», без кнопок.
        → (True, message_id) · (False, код | 'выключено') · (None, 'net')."""
        if not self.watch:
            return False, "выключено"
        ok, res = self.api("sendMessage", {"chat_id": self.chat, "text": str(text)[:TG_TEXT_MAX]})
        return (True, int(res.get("message_id"))) if ok else (ok, res)

    # ── приём обновлений ──────────────────────────────────────────────────────────────────

    def offset(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='tg_offset'").fetchone()
        return int(row[0]) if row else 0

    def _set_offset(self, value):
        self.db.execute("INSERT INTO meta(key, value) VALUES('tg_offset', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(value)),))

    def poll(self, timeout=0):
        """Один getUpdates. → число разобранных обновлений или None (вызов не удался)."""
        if not self.reading:
            return 0
        allowed = []
        for name in ((ALLOWED_UPDATES if self.enabled else []) + (RELAY_UPDATES if self.relay else [])
                     + ([REACT_UPDATE] if self.react else [])):
            if name not in allowed:
                allowed.append(name)
        ok, res = self.api("getUpdates", {"offset": self.offset(), "timeout": int(max(0, timeout)),
                                          "allowed_updates": allowed}, timeout=int(timeout) + 15, quiet=(409,))
        if not ok:
            if res == 409:
                self.polls["conflict"] += 1
                if not self.conflict:
                    self.log("getUpdates: 409 — у бота второй читатель, разбор стоит; опрос раз в %d с, "
                             "такт ядра идёт, число 409 — в сводке" % CONFLICT_PAUSE)
                self.conflict = True
            else:
                self.polls["fail"] += 1
            return None
        if self.conflict:
            self.log("getUpdates: 409 прошёл — читатель снова один (409 за серию: %d)" % self.polls["conflict"])
            self.conflict = False
        self.polls["ok"] += 1
        n = 0
        for u in res or []:
            n += self.handle(u)
        return n

    def poll_pause(self):
        """Сколько ждать до следующего опроса после неудачного: серия 409 — CONFLICT_PAUSE."""
        return CONFLICT_PAUSE if self.conflict else POLL_RETRY_SEC

    def handle(self, u):
        """Одно обновление. Ниже offset — уже разобрано, пропуск. → 1 разобрано, 0 пропущено."""
        uid = int(u.get("update_id", -1))
        if uid < self.offset():
            self.log("обновление %d уже разобрано — пропуск" % uid)
            return 0
        try:
            if "callback_query" in u:
                if self.enabled:
                    self.on_press(u["callback_query"])
            elif "message" in u:
                if self._is_show(u["message"]):
                    self.on_topic(u["message"])
                elif self.enabled:
                    self.on_message(u["message"])
            elif "edited_message" in u:
                if self._is_show(u["edited_message"]):
                    self.on_topic_edit(u["edited_message"])
            elif REACT_UPDATE in u:
                self.on_reaction(u[REACT_UPDATE], uid)
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
        if act in ("rule", "unrule"):
            # уроки (WAAGENTLESSON0210): право решает ядро по id нажавшего
            fn = self.core.lesson_promote if act == "rule" else self.core.lesson_rollback
            res = fn(a, who, frm.get("id"))
            self.log("урок %d: %s → %s" % (a, act, res.get("state") or "нет"))
            return self.answer(cq.get("id"), res.get("words"))
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
        frm = msg.get("from") or {}
        who = who_of(frm)
        if not frm.get("is_bot") and self._on_lesson_text(msg, reply, who, frm):
            return
        card = self.db.execute("SELECT draft_id, ver FROM tg_cards WHERE card_id=?",
                               (reply,)).fetchone() if reply else None
        if not card:
            return
        if frm.get("is_bot"):
            self.log("отказ: правку прислал бот %s (черновик %d)" % (who, card[0]))
            return
        did, ver = card
        text = msg.get("text") or ""
        self.log("правка: от %s · черновик %d версия %d" % (who, did, ver))
        if self.core.revise(did, text, who, ver=ver, who_id=frm.get("id")):
            return
        words = "не принято: " + (self.core._decided(did, ver) if text.strip() else "нужен текст сообщения")
        self._say(msg, words)

    def _on_lesson_text(self, msg, reply, who, frm):
        """Уроки (WAAGENTLESSON0210): «откатить №N» текстом и реплай-причина на сообщение кандидата.
        → True — сообщение разобрано здесь."""
        text = msg.get("text") or ""
        m = RX_ROLLBACK.match(text)
        row = None if m or not reply else self.db.execute(
            "SELECT lesson_id FROM tg_lessons WHERE msg_id=?", (reply,)).fetchone()
        if m:
            res = self.core.lesson_rollback(int(m.group(1)), who, frm.get("id"))
            self.log("урок %s: «откатить» текстом от %s → %s" % (m.group(1), who, res.get("state") or "нет"))
            self._say(msg, res.get("words"))
        elif row and self.core.lesson_reason(row[0], text, who):
            self._lesson_show(row[0])
            self._say(msg, "причина урока №%d записана" % row[0])
        elif row:
            self._say(msg, "не принято: причину пишут только кандидату, текстом — %s"
                      % self.core._lesson_decided(row[0]))
        # разобрано здесь — «откатить №N» или реплай на сообщение урока; прочее — карточкам
        return bool(m or row)

    # ── тема клиента → WhatsApp (WARELAYTEXT0210) ─────────────────────────────────────────

    def _is_show(self, msg):
        return bool(self.show_chat) and str(((msg or {}).get("chat") or {}).get("id")) == str(self.show_chat)

    def _topics(self, where, arg):
        """Строки topics базы показа (только mode=ro) → (строки | None, почему)."""
        if not (self.mirror_db and os.path.exists(self.mirror_db)):
            return None, "базы показа нет"
        try:
            conn = self._ro(self.mirror_db)
            try:
                return conn.execute("SELECT number, thread_id FROM topics WHERE " + where, (arg,)).fetchall(), ""
            finally:
                conn.close()
        except Exception as e:                                       # noqa: BLE001
            return None, "база показа не прочитана: %s" % type(e).__name__

    def _topic_number(self, msg):
        """Сообщение форума показа → (номер клиента, тема) · (None, почему). Общая тема и тема без
        номера наружу не идут."""
        thread = msg.get("message_thread_id") if msg.get("is_topic_message") else None
        if not thread:
            return None, "общая тема форума"
        rows, why = self._topics("thread_id=?", int(thread))
        if rows is None:
            return None, why
        nums = {r[0] for r in rows if r[0]}
        if len(nums) != 1:
            return None, "у темы %s %s" % (thread, "нет номера клиента" if not nums else "больше одного номера")
        return nums.pop(), int(thread)

    def _human(self, msg):
        frm = msg.get("from") or {}
        return bool(frm) and not frm.get("is_bot")

    def download(self, file_id, cap):
        """Файл Telegram → (bytes | None, почему): `getFile`, затем скачивание В ПАМЯТЬ — на диск не
        пишется ни байта. Ключ бота живёт только в адресе запроса и в журнал не идёт."""
        ok, res = self.api("getFile", {"file_id": file_id})
        if not ok:
            return None, "getFile не удался (%s)" % res
        path = (res or {}).get("file_path")
        if not path:
            return None, "getFile без пути файла"
        size = int((res or {}).get("file_size") or 0)
        if cap and size > cap:
            return None, "файл %s больше предела %s" % (wa_send.fmt_size(size), wa_send.fmt_size(cap))
        status, body = self.http("GET", TG_BASE + "/file/bot" + self.token + "/" + path, {}, None,
                                 TG_FILE_TIMEOUT)
        if status != 200:
            return None, "скачивание: HTTP %s" % status
        return bytes(body or b""), ""

    def _topic_reply(self, thread, mid, words):
        return self.api("sendMessage", {"chat_id": self.show_chat, "message_thread_id": int(thread),
                                        "text": str(words)[:TG_TEXT_MAX],
                                        "reply_parameters": {"message_id": int(mid),
                                                             "allow_sending_without_reply": True}})

    def on_topic(self, msg):
        """Сообщение в форуме показа. Текст человека в теме клиента → `Core.relay` → клиенту в WhatsApp;
        исход — в теме: отправлено — реакция бота, иначе — ответ словами. → исход или None (наружу ничего)."""
        mid = int(msg.get("message_id") or 0)
        if not self.relay:
            self.log("тема: сообщение %d — %s выключен, наружу ничего" % (mid, RELAY_FLAG))
            return None
        if not self._human(msg):
            self.log("тема: сообщение %d — написал не человек (бот или от имени группы), наружу ничего" % mid)
            return None
        number, thread = self._topic_number(msg)
        if not number:
            self.log("тема: сообщение %d — %s, наружу ничего" % (mid, thread))
            return None
        text = msg.get("text")
        media = None
        if not isinstance(text, str) or not text.strip():
            media, no_pair = media_of(msg)
            if media is None:
                if no_pair:
                    self.log("тема: сообщение %d — %s в WhatsApp не отправляется, ответ словами" % (mid, no_pair))
                    self._topic_reply(thread, mid, RELAY_NO_PAIR % no_pair)
                return None
            if media.get("file_id"):
                media["fetch"] = lambda cap, fid=media["file_id"]: self.download(fid, cap)
            res = self.core.relay(mid, number, None, who_of(msg.get("from")), media=media)
        else:
            res = self.core.relay(mid, number, text, who_of(msg.get("from")))
        out = res.get("outcome")
        if out == wa_agent.RELAY_DUP:
            return None
        if out == "sent":
            self.api("setMessageReaction", {"chat_id": self.show_chat, "message_id": mid,
                                            "reaction": [{"type": "emoji", "emoji": RELAY_SENT_EMOJI}]})
            if res.get("dropped_caption"):
                self._topic_reply(thread, mid, RELAY_NO_CAPTION % NO_CAPTION_GEN.get(
                    (media or {}).get("label"), "этого вида"))
        else:
            self._topic_reply(thread, mid, res.get("words"))
        return out

    def on_topic_edit(self, msg):
        """Правка сообщения в теме клиента: клиенту не уходит; одна строка в ответ на сообщение."""
        mid = int(msg.get("message_id") or 0)
        if not self.relay or not self._human(msg):
            return None
        number, thread = self._topic_number(msg)
        if not number:
            return None
        if msg.get("location"):
            self.log("тема: сообщение %d — геоточка обновилась, в WhatsApp не передаётся" % mid)
            return None
        if not self.core.edit_once(mid):
            self.log("тема: правка сообщения %d — ответ уже дан" % mid)
            return None
        self.log("тема: правка сообщения %d — в WhatsApp не передаётся, ответ словами" % mid)
        self._topic_reply(thread, mid, RELAY_EDIT_WORDS)
        return True

    def agent_sent(self, number, text, who):
        """Ушедшее агентом по «Отправить» — одной строкой в тему клиента. → id сообщения или None."""
        if not self.relay:
            return None
        rows, why = self._topics("number=?", number)
        thread = rows[0][1] if rows else None
        if not thread:
            self.log("тема: строки «отправил агент» нет — %s" % (why or "у клиента нет темы"))
            return None
        line = AGENT_LINE % (str(who or "").split(" (id ")[0] or "—", text)
        if len(line) > TG_TEXT_MAX:
            line = line[:TG_TEXT_MAX - 1] + "…"
        ok, res = self.api("sendMessage", {"chat_id": self.show_chat, "message_thread_id": int(thread),
                                           "text": line})
        return int(res.get("message_id")) if ok else None

    # ── реакции наружу (WAREACTOUT0110) ───────────────────────────────────────────────────

    def _ro(self, path):
        return sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=5)

    def _react_target(self, mid):
        """Сообщение темы → (wamid, номер, '') либо (None, None, почему). Только mode=ro."""
        if not mid:
            return None, None, "нет id сообщения"
        if not (self.mirror_db and os.path.exists(self.mirror_db)):
            return None, None, "базы показа нет"
        try:
            conn = self._ro(self.mirror_db)
            try:
                rows = conn.execute("SELECT key, number FROM shown WHERE msg_id=? AND state='shown' "
                                    "AND solo=1", (int(mid),)).fetchall()
            finally:
                conn.close()
        except Exception as e:                                       # noqa: BLE001
            return None, None, "база показа не прочитана: %s" % type(e).__name__
        pairs = set()
        for key, number in rows:
            pre, _, wamid = str(key).partition(":")
            if pre in ("msg", "file") and wamid and not wamid.startswith("row:"):
                pairs.add((wamid, number))
        if not pairs:
            return None, None, "в показе у сообщения нет ключа с wamid (не из показа или показано до 40b158b)"
        if len(pairs) > 1:
            return None, None, "у сообщения больше одного wamid"
        wamid, number = pairs.pop()
        qpath = getattr(self.core, "queue_path", None)
        try:
            conn = self._ro(qpath)
            try:
                row = conn.execute("SELECT msg_type, echo, history FROM wa_inbox WHERE wamid=? "
                                   "ORDER BY id LIMIT 1", (wamid,)).fetchone()
            finally:
                conn.close()
        except Exception as e:                                       # noqa: BLE001
            return None, None, "очередь не прочитана: %s" % type(e).__name__
        if not row:
            return None, None, "строки цели в очереди нет"
        kind = wa_kind.kind_of(row[0], row[1], row[2])
        if kind not in REACT_KINDS:
            return None, None, "цель — не сообщение клиента и не наше (вид %s)" % kind
        return wamid, number, ""

    def _send_reaction(self, number, wamid, emoji):
        if self.react_send:
            return self.react_send(number, wamid, emoji)
        return wa_send.send_reaction(number, wamid, emoji, db_path=getattr(self.core, "queue_path", None))

    def on_reaction(self, mr, seq=0):
        """Реакция человека в группе показа → та же реакция клиенту. → исход двери или None."""
        chat = (mr.get("chat") or {}).get("id")
        mid = mr.get("message_id")
        if str(chat) != str(self.show_chat or ""):
            self.log("реакция: чужой чат %s — пропуск" % chat)
            return None
        if not self.react:
            self.log("реакция: сообщение темы %s — %s выключен, наружу ничего" % (mid, REACT_FLAG))
            return None
        user = mr.get("user") or {}
        actor = (mr.get("actor_chat") or {}).get("id")
        if user.get("is_bot") or (not user and str(actor) != str(chat)):
            self.log("реакция: сообщение темы %s — поставил не человек группы, пропуск" % mid)
            return None
        who = ("u%s" % user.get("id")) if user else ("chat%s" % actor)
        emoji, other = tg_standard(mr.get("new_reaction"))
        if other:
            self.log("реакция: сообщение темы %s — вид %s в WhatsApp не существует, не отправляется"
                     % (mid, ",".join(other)))
        wamid, number, why = self._react_target(mid)
        if not wamid:
            self.log("реакция: сообщение темы %s — wamid нет (%s), наружу ничего" % (mid, why))
            return None
        if emoji:
            self.db.execute("INSERT OR REPLACE INTO tg_reacts(msg_id, who, emoji, seq) VALUES(?,?,?,?)",
                            (int(mid), who, emoji, int(seq)))
        else:
            self.db.execute("DELETE FROM tg_reacts WHERE msg_id=? AND who=?", (int(mid), who))
        row = self.db.execute("SELECT emoji FROM tg_reacts WHERE msg_id=? ORDER BY seq DESC LIMIT 1",
                              (int(mid),)).fetchone()
        want = row[0] if row else ""
        last = self.db.execute("SELECT emoji, outcome FROM tg_react_out WHERE msg_id=?",
                               (int(mid),)).fetchone()
        if (last[0] if last else "") == want:
            self.log("реакция: сообщение темы %s — это уже уходило клиенту (%s), второй раз не шлём"
                     % (mid, last[1] if last else "снимать нечего"))
            return None
        # sending ДО двери: обрыв посреди вызова повтора не даёт
        self.db.execute("INSERT OR REPLACE INTO tg_react_out(msg_id, wamid, emoji, outcome, ts) "
                        "VALUES(?,?,?,?,?)", (int(mid), wamid, want, "sending", self.clock()))
        try:
            res = self._send_reaction(number, wamid, wa_emoji(want)) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": wa_send.UNKNOWN, "reason": "дверь упала: %s" % type(e).__name__}
        outcome = str(res.get("outcome") or wa_send.UNKNOWN)
        self.db.execute("UPDATE tg_react_out SET outcome=? WHERE msg_id=?", (outcome, int(mid)))
        self.log("реакция: сообщение темы %s · %s → %s · %s" % (mid, "реакция" if want else "снятие",
                                                               outcome, str(res.get("reason") or "")[:120]))
        return outcome


def run(core, tg, should_stop, clock=time.time, sleep=time.sleep, tick_secs=TICK_SECS, log=None,
        on_turn=None, stats=None):
    """Главный цикл: getUpdates и такт ядра в ОДНОМ потоке. Длинный опрос не дольше остатка до
    такта, поэтому такт идёт раз в tick_secs. Падение такта — строка журнала, не смерть цикла.
    Неудачный опрос откладывает СЛЕДУЮЩИЙ опрос (`tg.poll_pause`: 409 — 30 с), а не такт.
    on_turn(now) — раз за оборот (сводка службы); stats — счётчики тактов для неё."""
    log = log or (lambda line: None)
    stats = stats if stats is not None else {}
    next_tick = clock()
    poll_after = 0.0
    while not should_stop():
        now = clock()
        if tg.reading and now >= poll_after:
            if tg.poll(timeout=max(0, int(next_tick - now))) is None:
                poll_after = clock() + getattr(tg, "poll_pause", lambda: POLL_RETRY_SEC)()
        now = clock()
        if now >= next_tick:
            stats["ticks"] = stats.get("ticks", 0) + 1
            try:
                core.tick(now)
            except Exception as e:                                   # noqa: BLE001
                stats["tick_fail"] = stats.get("tick_fail", 0) + 1
                log("такт упал: %s" % type(e).__name__)
            next_tick = now + tick_secs
        elif not tg.reading or now < poll_after:
            sleep(max(0.0, (next_tick if not tg.reading else min(next_tick, poll_after)) - now))
        if on_turn is not None:
            on_turn(clock())


if __name__ == "__main__":
    raise SystemExit("wa_agent_tg: руки Telegram (WAAGENTTG0110) — служба запускается wa_agent_svc.py "
                     "(WAAGENTSVC0210)")
