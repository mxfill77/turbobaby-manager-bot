#!/usr/bin/env python3
"""WA → TG MIRROR — медиа клиентов WhatsApp на сервер сразу, показ переписки в Telegram по флагу (01.10.2026).

Две работы разного веса, и вторая без первой не нужна:

1. МЕДИА — ВСЕГДА, при любом флаге. У строки wa_inbox с `media_id` файл забирается у 360dialog
   сразу по приходу, пока ссылка жива: GET <шлюз>/<media_id> → {url}, затем GET той же ссылки с
   хостом шлюза и ключом канала (360dialog, «Media»: хост lookaside.fbsbx.com заменяется на
   waba-v2.360dialog.io). Ключ уходит ТОЛЬКО на хост шлюза; ссылка на чужой хост — отказ.
   Файл — каталог `wa_media` рядом с базой, права 600, имя — хеш wamid (номеров и имён в именах
   файлов нет). Повтор не качается: состояние в своей базе. Отказ — строка WARNING с кодом.
   Потолок каталога — доля свободного места на старте; пол свободного места — FREE_FLOOR.

2. ПОКАЗ — ТОЛЬКО ФЛАГОМ `WA_TG_MIRROR_SHOW` (по умолчанию выключен). Выключен → ни одного
   вызова Telegram, строка старта «показ выключен». Включён, но нет ключа, группы, тем или прав —
   показ стоит, раз в час WARNING с причиной.
   Тема «имя · номер» открывается по первому ЖИВОМУ входящему или эху клиента. Порядок в теме:
   шапка («писал раньше: с …, N сообщений, серий обращений K, последнее …» или «раньше не писал»,
   плюс чего нет); вся предыстория файлом .txt; последние TAIL_N сообщений текстом; их медиа
   файлами; затем новое. Предыстория = архив копии телефона (WAARCHIVE0110) + строки очереди без
   пары в архиве (пара — номер и key_id из wamid), по времени, без дублей. Архива или описи медиа
   нет — тема открывается с тем, что есть, шапка это называет, журнал — раз в час. Первое
   включение открывает темы и по живым строкам за 24 ч до него; тревога — только для новых.
   Дальше каждое живое сообщение — в свою тему; квитанции не показываются.
   Реакция (клиента или наша с телефона, WAREACTNAME0110) — не строкой, а реакцией бота на
   сообщение темы, показанное из строки с wamid цели (id сообщения темы хранится у ключа показа);
   вне набора Telegram или цель не показана отдельным сообщением — короткая строка; снятие — снять.
   Цель — НАШЕ сообщение через API (WAMIRROR0410): эха у него нет, в очереди по его wamid лежит только
   квитанция, и текстом цели квитанция не бывает никогда. Реакция ставится на строку показа ушедшего
   агентом (`agent_show` базы агента, mode=ro); строки нет — короткая строка с текстом ушедшей версии по
   wamid (`outbox`/`drafts` базы агента); не найдено — «на наше сообщение».
   Имя темы догоняет имя клиента: появилось или сменилось — editForumTopic один раз на смену.
   Все виды — по-русски (WAMIRRRU0210): вид без текста — словом (wa_history.kind_word), вид вне
   словаря — «[сообщение неизвестного вида]» и строка журнала с именем вида. Удаление с телефона
   (revoke) — пометка «🗑 удалено с телефона ЧЧ:ММ» на сообщении темы, где цель показана одна
   (прежний текст остаётся зачёркнутым); иначе одна строка «🗑 удалено сообщение от ЧЧ:ММ».
   Темп — не больше 20 вызовов в минуту; 429 — ждать retry_after. wamid дважды не показывается:
   ключ ставится ДО вызова, так что обрыв посреди вызова даёт «не повторять», а не дубль.

Живая wa_queue.db и архив открываются ТОЛЬКО на чтение (mode=ro). Своё состояние — wa_tg_mirror.db рядом.
В журнал не пишутся тексты, номера, имена и пути файлов клиентов — только id строк и числа.

Usage (standalone service): venv/bin/python3 wa_tg_mirror.py
"""

import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque

import wa_history
import wa_kind
import wa_send
# склейка истории и её строки живут в wa_history (WAHISTMOD0110) — её же зовёт агент
from wa_history import (PHUKET_OFFSET, SERIES_GAP, MEDIA_PLACEHOLDER, head_text, item_line,
                        parse_wamid, pk_date, pk_full, who_of)

ROOT = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger("wa_tg_mirror")

D360_BASE       = "https://waba-v2.360dialog.io"
D360_KEY_HEADER = "D360-API-KEY"
META_MEDIA_HOST = "https://lookaside.fbsbx.com"
TG_BASE         = "https://api.telegram.org"

FLAG_NAME      = "WA_TG_MIRROR_SHOW"
TICK_SECS      = 5
TG_PER_MIN     = 20            # потолок вызовов Telegram в скользящую минуту
TG_TEXT_MAX    = 4000
TG_CAPTION_MAX = 1000
TG_FILE_MAX    = 50 * 1024 * 1024
WARN_EVERY    = 3600          # WARNING «показ стоит» — не чаще раза в час
RECHECK_EVERY  = 300           # стоящий показ перепроверяется раз в 5 минут
ALARM_AFTER    = 600           # живая строка без показа дольше 10 минут — тревога
SUMMARY_EVERY  = 300           # сводка числами раз в 5 минут
MEDIA_WAIT     = 180           # живое медиа ждёт своего файла не дольше 3 минут
MEDIA_TRIES    = 5
FREE_FLOOR     = 5 * 1024 ** 3     # после записи свободного места не меньше 5 GiB
CAP_SHARE      = 0.20              # потолок каталога — 20% свободного места на старте …
CAP_MAX        = 4 * 1024 ** 3     # … но не больше 4 GiB

ARCHIVE_DIR    = "/root/wa_archive"   # архив копии телефона: wa_archive.db, media/, media_manifest.jsonl
TAIL_N         = 15            # последних сообщений предыстории — текстом в тему
FIRST_WINDOW   = 86400         # первое включение: темы и по живым строкам за 24 ч до него

PLACEHOLDER_TEXT = "файл Meta не отдаёт"
_KEY_FORM = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

_MEDIA_WORD = wa_history.MEDIA_WORD
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4",
        "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
        "application/pdf": ".pdf", "video/3gpp": ".3gp"}

# медиа: конечные состояния — повтор не качается
M_OK, M_FAIL, M_RETRY, M_WAIT = "ok", "fail", "retry", "wait"
# показ: ключ ставится ДО вызова (sending), после ответа — shown; обрыв → unsure, повтора нет
S_SENDING, S_SHOWN, S_UNSURE = "sending", "shown", "unsure"
# ступени темы
T_HEAD, T_HIST, T_TAIL, T_FILES, T_LIVE = "head", "hist", "tail", "files", "live"

_QCOLS = wa_history.QCOLS

# Реакции (WAREACTNAME0110). Бот ставит ОДНУ реакцию на сообщение и только из набора Telegram
# (ReactionTypeEmoji); вне набора, цель не показана отдельным сообщением или чат реакцию не
# принял (400) — короткая строка в теме. Сравнение — без U+FE0F и без оттенка кожи: «❤️» и «👍🏽»
# WhatsApp ставятся как «❤» и «👍» (оттенок теряется — Telegram его не держит).
TG_REACTIONS = frozenset(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 "
    "🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 "
    "😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡".split())
SIDE_TG = "tg"                 # строка reacts с тем, что бот СЕЙЧАС держит на сообщении темы
NO_NAME = "без имени"
RENAME_EVERY = 60              # имена тем сверяются не чаще раза в минуту

# Удаление с телефона (WAMIRRRU0210): msg_type, поле тела с wamid удалённого и ключ «цель уже
# помечена» — второй revoke той же цели (другой wamid, повтор досинхрона) правки не повторяет.
REVOKE_TYPE = "revoke"
REVOKE_KEY = "rev:"
# Правка с телефона (WAPHONEEDIT0210): цель и новый текст — колонки очереди edit_to/edit_text.
# Таблица edits — какая строка правки последней легла на цель и как (правкой или строкой): повтор
# того же текста (досинхрон под другим wamid) второй правки не даёт, удаление зачёркивает НОВЫЙ текст.
EDIT_TYPE = wa_history.EDIT_TYPE
_UNKNOWN_LOGGED = set()        # имена неизвестных видов, по которым строка журнала уже была
_KIND_FORM = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,39}$")


def _kind_name(kind) -> str:
    """Имя вида для журнала — только формы имени (буква, затем [A-Za-z0-9_.-], до 40); иное — длиной:
    тексты, номера и имена клиентов в журнал не идут."""
    s = str(kind or "")
    if not s:
        return "<пусто>"
    return s if _KIND_FORM.match(s) else "<не имя вида, %d симв.>" % len(s)


def note_unknown(kinds):
    """Вид вне словаря показан словом «сообщение неизвестного вида» — строка журнала с именем вида,
    одна на вид за жизнь процесса."""
    for k in sorted(kinds):
        if k not in _UNKNOWN_LOGGED:
            _UNKNOWN_LOGGED.add(k)
            log.warning("показ: вид сообщения %s неизвестен — показан словом «%s»",
                        _kind_name(k), wa_history.UNKNOWN_WORD)


def pk_hm(ts) -> str:
    return time.strftime("%H:%M", time.gmtime(int(ts or 0) + PHUKET_OFFSET))


def utf16_len(s) -> int:
    """Длина в единицах UTF-16 — так Telegram меряет смещения разметки (entities)."""
    return len(s.encode("utf-16-le")) // 2


def tg_emoji(e) -> str:
    """Эмодзи WhatsApp → эмодзи реакции Telegram или '' (вне набора / пусто)."""
    s = "".join(ch for ch in (e or "") if ch != "️" and not 0x1F3FB <= ord(ch) <= 0x1F3FF)
    return s if s in TG_REACTIONS else ""


def _flag_on(raw) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _env():
    """Ключи — тем же путём, что у wa_webhook: load_dotenv корня дерева. Значения не печатаются."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    qdb = os.environ.get("WA_QUEUE_DB", os.path.join(ROOT, "wa_queue.db"))
    base = os.path.dirname(os.path.abspath(qdb))
    return {
        "queue_db":  qdb,
        "state_db":  os.environ.get("WA_TG_MIRROR_DB", os.path.join(base, "wa_tg_mirror.db")),
        "media_dir": os.environ.get("WA_MEDIA_DIR", os.path.join(base, "wa_media")),
        # одно правило с дверью (WAREACTOUT0110): WA_360_API_KEY, иначе WA_D360_API_KEY
        "d360_key":  wa_send.api_key(os.environ)[0],
        "tg_token":  (os.environ.get("WA_TG_BOT_TOKEN") or "").strip(),
        "tg_chat":   (os.environ.get("WA_TG_CHAT_ID") or "").strip(),
        "show":      _flag_on(os.environ.get(FLAG_NAME)),
        # база агента (WAMIRROR0410): тот же путь, что у службы wa-agent; только mode=ro — строка показа и текст
        # ушедшего через API для реакции клиента на наше сообщение
        "agent_db":  os.environ.get("WA_AGENT_DB", os.path.join(base, "wa_agent.db")),
        "archive_db":       os.environ.get("WA_ARCHIVE_DB", os.path.join(ARCHIVE_DIR, "wa_archive.db")),
        "archive_media":    os.environ.get("WA_ARCHIVE_MEDIA_DIR", os.path.join(ARCHIVE_DIR, "media")),
        "archive_manifest": os.environ.get("WA_ARCHIVE_MANIFEST",
                                           os.path.join(ARCHIVE_DIR, "media_manifest.jsonl")),
    }


def show_enabled(env) -> bool:
    return bool(env.get("show"))


def http_request(method, url, headers=None, data=None, timeout=30):
    """Единственный выход в сеть. → (код HTTP или None, тело bytes). Исключения наружу не идут."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:
            body = b""
        return e.code, body
    except Exception as e:
        return None, type(e).__name__.encode()


def pk_time(ts) -> str:
    return time.strftime("%d.%m %H:%M", time.gmtime(int(ts or 0) + PHUKET_OFFSET))


def history_txt(items) -> bytes:
    return ("\n".join(item_line(it) for it in items) + "\n").encode("utf-8")


def body_of(row) -> str:
    t = row["msg_type"] or ""
    if t == MEDIA_PLACEHOLDER:
        return "[медиа — " + PLACEHOLDER_TEXT + "]"
    if t in _MEDIA_WORD:
        s = "[" + _MEDIA_WORD[t] + "]"
        return s + (" " + row["caption"] if row["caption"] else "")
    if row["text"]:
        return row["text"]
    unknown = set()
    word = wa_history.kind_word(t, unknown)
    note_unknown(unknown)
    return "[" + word + "]"


def line_of(row) -> str:
    return "%s %s: %s" % (pk_time(row["ts_msg"] or row["ts_queued"]), who_of(row), body_of(row))


def batch_lines(items, limit=TG_TEXT_MAX):
    """[(ключ, строка)] → [(ключи, текст ≤ limit)]. Порядок сохраняется; длинная строка режется."""
    out, keys, cur = [], [], ""
    for key, line in items:
        pieces = [line[i:i + limit] for i in range(0, len(line), limit)] or [""]
        for n, piece in enumerate(pieces):
            add = piece if not cur else "\n" + piece
            if cur and len(cur) + len(add) > limit:
                out.append((keys, cur))
                keys, cur, add = [], "", piece
            cur += add
            if n == 0:
                keys.append(key)
    if cur or keys:
        out.append((keys, cur))
    return out


_row_key = wa_history.row_key


def _is_live(row) -> bool:
    if int(row["history"] or 0):
        return False
    kind = wa_kind.kind_of(row["msg_type"], row["echo"], row["history"])
    return kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_ECHO)


def _is_receipt(row) -> bool:
    return wa_kind.kind_of(row["msg_type"], row["echo"], row["history"]) == wa_kind.KIND_RECEIPT


def _is_reaction(row) -> bool:
    return wa_kind.kind_of(row["msg_type"], row["echo"], row["history"]) == wa_kind.KIND_REACTION


_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (key TEXT PRIMARY KEY, row_id INTEGER, state TEXT, path TEXT,
    size INTEGER, mime TEXT, code TEXT, tries INTEGER NOT NULL DEFAULT 0,
    next_try REAL NOT NULL DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER,
    stage TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS alarmed (row_id INTEGER PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS reacts (target TEXT, side TEXT, emoji TEXT, row_id INTEGER,
    PRIMARY KEY (target, side));
CREATE TABLE IF NOT EXISTS edits (target TEXT PRIMARY KEY, row_id INTEGER, how TEXT, ts REAL)
"""
# 01.10.2026 (WAREACTNAME0110): id сообщения темы у показанного ключа (solo — ключ один в
# сообщении, на него можно ставить реакцию) и имя, под которым тема сейчас названа. Только ADD.
_STATE_ADDED = (("shown", "msg_id", "INTEGER"), ("shown", "solo", "INTEGER"), ("topics", "name", "TEXT"))


class Mirror:
    def __init__(self, env, http=None, clock=None, sleep=None, disk_free=None):
        self.env = env
        self.http = http or http_request
        self.clock = clock or time.time
        self.sleep = sleep or time.sleep
        self.disk_free = disk_free or (lambda p: shutil.disk_usage(p).free)
        self.show = show_enabled(env)
        self.queue_db = env["queue_db"]
        self.media_dir = env["media_dir"]
        os.makedirs(self.media_dir, mode=0o700, exist_ok=True)
        os.chmod(self.media_dir, 0o700)
        self.media_used = sum(os.path.getsize(os.path.join(self.media_dir, f))
                              for f in os.listdir(self.media_dir))
        self.cap = int(min(CAP_MAX, CAP_SHARE * self.disk_free(self.media_dir)))
        self._init_state(env["state_db"])
        self.sent = deque()
        self.names_checked = None
        self.ready = False
        self.ready_checked = None
        self.block_reason = ""
        self._warned = {}
        self.last_summary = None
        self._man, self._man_sig = None, None
        self.counts = {"media_ok": 0, "media_fail": 0, "shown": 0, "tg_calls": 0}

    # ── своё состояние ──────────────────────────────────────────────────────────────────
    def _init_state(self, path):
        if not os.path.exists(path):
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
        os.chmod(path, 0o600)
        self.st = sqlite3.connect(path, timeout=10)
        for stmt in _STATE_SCHEMA.strip().split(";"):
            if stmt.strip():
                self.st.execute(stmt)
        for table, col, decl in _STATE_ADDED:
            if col not in {r[1] for r in self.st.execute("PRAGMA table_info(%s)" % table)}:
                self.st.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))
        # обрыв посреди вызова: показано ли — неизвестно; повтор дал бы дубль → не повторяем
        n = self.st.execute("UPDATE shown SET state=? WHERE state=?", (S_UNSURE, S_SENDING)).rowcount
        self.st.commit()
        if n:
            log.warning("показ: %d ключей остались «в отправке» после обрыва — считаются показанными, "
                        "повтора нет", n)

    def _kv(self, k, default=None):
        r = self.st.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def _kv_set(self, k, v):
        self.st.execute("INSERT OR REPLACE INTO kv(k, v) VALUES (?, ?)", (k, str(v)))
        self.st.commit()

    def _warn_hourly(self, what, msg, *args):
        now = self.clock()
        last = self._warned.get(what)
        if last is None or now - last >= WARN_EVERY:
            self._warned[what] = now
            log.warning(msg, *args)

    # ── живая очередь: только чтение ──────────────────────────────────────────────────────
    def _q(self):
        path = os.path.abspath(self.queue_db).replace("\\", "/")
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _rows(self, where, args=()):
        conn = self._q()
        try:
            # колонки, которых в очереди ещё нет (вход не перезапущен после правки), читаются NULL
            have = {r[1] for r in conn.execute("PRAGMA table_info(wa_inbox)")}
            cols = [c if c in have else "NULL AS " + c for c in _QCOLS]
            return conn.execute("SELECT " + ", ".join(cols) + " FROM wa_inbox WHERE " + where,
                                args).fetchall()
        finally:
            conn.close()

    def _react_fields(self, row):
        """Строка реакции → (эмодзи, wamid цели). Строка легла до правки входа (react_to нет) —
        оба берутся из тела сообщения в той же строке (raw). Не раскрылось → ('', None)."""
        if row["react_to"]:
            return row["text"] or "", row["react_to"]
        conn = self._q()
        try:
            raw = conn.execute("SELECT raw FROM wa_inbox WHERE id=?", (row["id"],)).fetchone()
        finally:
            conn.close()
        try:
            r = (json.loads(raw[0] or "null") or {}).get("reaction") or {}
            return r.get("emoji") or "", r.get("message_id") or None
        except (TypeError, ValueError, AttributeError):
            return "", None

    # ── архив копии телефона: только чтение; нет или не читается — причина, а не падение ────
    def _archive(self):
        """→ (соединение mode=ro | None, причина)."""
        path = self.env.get("archive_db") or ""
        if not os.path.exists(path):
            return None, "архива копии телефона нет"
        conn = None
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"),
                                   uri=True, timeout=10)
            conn.execute("SELECT number, ts, from_me, kind, text, caption, transcript, media_file, "
                         "key_id FROM messages LIMIT 0")
            return conn, ""
        except sqlite3.Error as e:
            if conn is not None:
                conn.close()
            return None, "архив не читается (%s)" % type(e).__name__

    def _manifest(self):
        """Опись медиа архива → ({«key_id|from_me»: (путь, размер, mime)}, "") · (None, причина).
        Перечитывается только при смене файла (mtime, размер)."""
        path = self.env.get("archive_manifest") or ""
        try:
            fst = os.stat(path)
        except OSError:
            return None, "описи медиа архива нет"
        sig = (fst.st_mtime, fst.st_size)
        if self._man_sig == sig:
            return self._man, ""
        out, why = wa_history.read_manifest(path, self.env.get("archive_media") or "")
        if out is None:
            return None, why
        self._man, self._man_sig = out, sig
        return out, ""

    def archive_step(self):
        """Каждый такт, при любом флаге: чего нет — WARNING раз в час (без путей файлов клиентов)."""
        conn, why = self._archive()
        if conn is not None:
            conn.close()
        else:
            self._warn_hourly("archive", "предыстория: %s — темы откроются с тем, что есть, шапка назовёт",
                              why)
        man, why_m = self._manifest()
        if man is None:
            self._warn_hourly("manifest", "предыстория: %s — файлы архива в темы не пойдут", why_m)

    def prehistory(self, num, rows, trig):
        """Предыстория номера → (items по времени, чего нет). items = архив + строки очереди ДО
        темы (id < trig) без пары в архиве. Пара — номер и key_id из wamid (номер — from_number:
        у эха номер внутри wamid другой). Архивная запись, чья пара — строка темы (id ≥ trig),
        сюда не идёт: её покажет «новое». Дублей нет ни одной дорогой. Склейка — wa_history.merge
        (её же зовёт агент); здесь — архив своим соединением, опись с кешем и «чего нет»."""
        missing, arch = [], []
        conn, why = self._archive()
        if conn is None:
            missing.append(why)
            self._warn_hourly("archive", "предыстория: %s — темы откроются с тем, что есть, шапка назовёт",
                              why)
        else:
            try:
                arch = wa_history.archive_select(conn, num)
            except sqlite3.Error as e:
                missing.append("архив не читается (%s)" % type(e).__name__)
            finally:
                conn.close()
        man, why_m = self._manifest()
        if man is None:
            missing.append(why_m)
            man = {}
        unknown = set()
        items = wa_history.merge(arch, rows, trig, man, self._media_of, unknown)
        note_unknown(unknown)
        return items, missing

    # ── 1. медиа ─────────────────────────────────────────────────────────────────────────
    def media_step(self):
        rows = self._rows("media_id IS NOT NULL AND media_id <> '' ORDER BY id")
        known = {k: (s, t, nt) for k, s, t, nt in
                 self.st.execute("SELECT key, state, tries, next_try FROM media")}
        now = self.clock()
        for row in rows:
            key = _row_key(row)
            st = known.get(key)
            if st and (st[0] in (M_OK, M_FAIL) or now < st[2]):
                continue
            key_ok = bool(_KEY_FORM.match(self.env.get("d360_key") or ""))
            if not key_ok:
                self._warn_hourly("d360_key", "медиа: ключ канала WA_D360_API_KEY пуст или не той формы — "
                                  "скачивание стоит")
                return
            self._fetch_media(row, key, st[1] if st else 0)

    def _room_for(self, n) -> bool:
        return (self.media_used + n <= self.cap
                and self.disk_free(self.media_dir) - n >= FREE_FLOOR)

    def _media_set(self, key, row_id, state, tries, code="", path=None, size=None, mime=None,
                   next_try=0.0):
        self.st.execute("INSERT OR REPLACE INTO media(key, row_id, state, path, size, mime, code, "
                        "tries, next_try, ts) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (key, row_id, state, path, size, mime, code, tries, next_try, self.clock()))
        self.st.commit()

    def _media_fail(self, row, key, tries, code, status):
        tries += 1
        retry = status is None or status == 429 or (isinstance(status, int) and status >= 500)
        if code == "CEILING":
            state, nxt = M_WAIT, self.clock() + WARN_EVERY
        elif retry and tries < MEDIA_TRIES:
            state, nxt = M_RETRY, self.clock() + 60 * tries
        else:
            state, nxt = M_FAIL, 0.0
        self._media_set(key, row["id"], state, tries, code=code, next_try=nxt)
        if state == M_FAIL:
            self.counts["media_fail"] += 1
        log.warning("медиа: ОТКАЗ строка=%d код=%s попытка=%d/%d → %s",
                    row["id"], code, tries, MEDIA_TRIES, state)

    def _fetch_media(self, row, key, tries):
        hdr = {D360_KEY_HEADER: self.env["d360_key"]}
        mid = urllib.parse.quote(str(row["media_id"]), safe="")
        status, body = self.http("GET", D360_BASE + "/" + mid, hdr, None, 30)
        if status != 200:
            return self._media_fail(row, key, tries, "meta:%s" % status, status)
        try:
            meta = json.loads(body.decode("utf-8"))
        except Exception:
            return self._media_fail(row, key, tries, "meta:not_json", 0)
        url = meta.get("url") or ""
        size = int(meta.get("file_size") or 0)
        mime = meta.get("mime_type") or row["mime"] or ""
        if url.startswith(META_MEDIA_HOST):
            url = D360_BASE + url[len(META_MEDIA_HOST):]
        if not url.startswith(D360_BASE + "/"):
            # ключ канала уходит только на хост шлюза — на чужой хост его не шлём вовсе
            return self._media_fail(row, key, tries, "url:foreign_host", 0)
        if size and not self._room_for(size):
            return self._media_fail(row, key, tries, "CEILING", 0)
        status, data = self.http("GET", url, hdr, None, 120)
        if status != 200:
            return self._media_fail(row, key, tries, "file:%s" % status, status)
        if not self._room_for(len(data)):
            return self._media_fail(row, key, tries, "CEILING", 0)
        ext = _EXT.get(mime.split(";")[0].strip(), ".bin")
        path = os.path.join(self.media_dir, hashlib.sha256(key.encode()).hexdigest()[:32] + ext)
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600) if hasattr(os, "fchmod") else None
            os.write(fd, data)
        finally:
            os.close(fd)
        self.media_used += len(data)
        self._media_set(key, row["id"], M_OK, tries + 1, path=path, size=len(data), mime=mime)
        self.counts["media_ok"] += 1
        log.info("медиа: OK строка=%d размер=%d", row["id"], len(data))

    def _media_of(self, key):
        r = self.st.execute("SELECT state, path, size, mime, code FROM media WHERE key=?",
                            (key,)).fetchone()
        return r

    # ── 2. показ ─────────────────────────────────────────────────────────────────────────
    def _rate_wait(self):
        while True:
            now = self.clock()
            while self.sent and now - self.sent[0] >= 60:
                self.sent.popleft()
            if len(self.sent) < TG_PER_MIN:
                return
            self.sleep(60 - (now - self.sent[0]) + 0.01)

    def _tg_raw(self, method, params, files=None):
        url = TG_BASE + "/bot" + self.env["tg_token"] + "/" + method
        if files:
            bnd = uuid.uuid4().hex
            parts = []
            for k, v in params.items():
                parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                              % (bnd, k, v)).encode("utf-8"))
            for k, (fname, data, ctype) in files.items():
                parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                              'Content-Type: %s\r\n\r\n' % (bnd, k, fname, ctype)).encode("utf-8"))
                parts.append(data + b"\r\n")
            parts.append(("--%s--\r\n" % bnd).encode())
            return self.http("POST", url, {"Content-Type": "multipart/form-data; boundary=" + bnd},
                             b"".join(parts), 120)
        return self.http("POST", url, {"Content-Type": "application/json"},
                         json.dumps(params, ensure_ascii=False).encode("utf-8"), 30)

    def tg(self, method, params, files=None):
        """→ (True, result) · (False, код) · (None, 'net') — ответа нет, исход неизвестен."""
        for _ in range(5):
            self._rate_wait()
            self.sent.append(self.clock())
            self.counts["tg_calls"] += 1
            status, body = self._tg_raw(method, params, files)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            if status == 200 and data.get("ok"):
                return True, data.get("result")
            if status == 429:
                ra = int((data.get("parameters") or {}).get("retry_after") or 5)
                log.warning("telegram: 429 на %s, жду retry_after=%d с", method, ra)
                self.sleep(ra)
                continue
            if status is None:
                log.warning("telegram: %s без ответа (%s)", method, body.decode("ascii", "replace"))
                return None, "net"
            log.warning("telegram: %s HTTP %s %s", method, status,
                        str(data.get("description") or "")[:120])
            if status in (401, 403):
                self.ready = False
            return False, status
        return False, 429

    def _check_ready(self) -> bool:
        now = self.clock()
        if self.ready:
            return True
        if self.ready_checked is not None and now - self.ready_checked < RECHECK_EVERY:
            return False
        self.ready_checked = now
        reason = self._probe()
        if reason:
            self.block_reason = reason
            self._warn_hourly("blocked", "показ: СТОИТ — %s", reason)
            return False
        self.ready, self.block_reason = True, ""
        log.info("показ: готов — группа-форум, у бота право тем")
        if self._kv("show_start_id") is None:
            # темы — и по живым строкам за 24 ч до включения; тревога — только для строк после него
            conn = self._q()
            try:
                mx = conn.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
                lo = conn.execute("SELECT MIN(id) FROM wa_inbox WHERE ts_queued >= ?",
                                  (int(now - FIRST_WINDOW),)).fetchone()[0]
            finally:
                conn.close()
            self._kv_set("open_from_id", lo if lo is not None else mx + 1)
            self._kv_set("show_start_id", mx)
            log.info("показ: первое включение — темы по живым строкам с id >= %s (24 ч до включения), "
                     "тревога «старше 10 минут» — для id > %d", self._kv("open_from_id"), mx)
        return True

    def _probe(self) -> str:
        if not self.env.get("tg_token"):
            return "нет ключа бота WA_TG_BOT_TOKEN"
        if not self.env.get("tg_chat"):
            return "нет группы WA_TG_CHAT_ID"
        ok, me = self.tg("getMe", {})
        if not ok:
            return "ключ бота не принят (%s)" % me
        ok, chat = self.tg("getChat", {"chat_id": self.env["tg_chat"]})
        if not ok:
            return "группа недоступна (%s)" % chat
        if not chat.get("is_forum"):
            return "в группе выключены темы"
        ok, mem = self.tg("getChatMember", {"chat_id": self.env["tg_chat"], "user_id": me.get("id")})
        if not ok:
            return "права бота не прочитаны (%s)" % mem
        if mem.get("status") not in ("administrator", "creator"):
            return "бот не админ группы"
        if mem.get("status") == "administrator" and not mem.get("can_manage_topics"):
            return "у бота нет права управлять темами"
        return ""

    def _is_shown(self, key) -> bool:
        return self.st.execute("SELECT 1 FROM shown WHERE key=?", (key,)).fetchone() is not None

    def _mark(self, keys, number, state, result=None):
        """result — ответ Telegram: его message_id запоминается у ключа (на него ставится реакция)."""
        now = self.clock()
        mid = result.get("message_id") if isinstance(result, dict) else None
        for k in keys:
            self.st.execute("INSERT OR REPLACE INTO shown(key, number, state, ts, msg_id, solo) "
                            "VALUES (?,?,?,?,?,?)", (k, number, state, now, mid, int(len(keys) == 1)))
        self.st.commit()

    def _unmark(self, keys):
        for k in keys:
            self.st.execute("DELETE FROM shown WHERE key=? AND state=?", (k, S_SENDING))
        self.st.commit()

    def _deliver(self, keys, number, method, params, files=None) -> bool:
        """Ключи ставятся ДО вызова: обрыв процесса посреди вызова повтора не даёт."""
        self._mark(keys, number, S_SENDING)
        ok, res = self.tg(method, params, files)
        if ok:
            self._mark(keys, number, S_SHOWN, res)
            self.counts["shown"] += 1
            return True
        if ok is None:
            self._mark(keys, number, S_UNSURE)
            return False
        self._unmark(keys)
        return False

    def _send_text(self, keys, number, thread, text) -> bool:
        return self._deliver(keys, number, "sendMessage",
                             {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                              "text": text})

    def _send_bytes(self, keys, number, thread, fname, data, mime, caption) -> bool:
        return self._deliver(keys, number, "sendDocument",
                             {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                              "caption": caption[:TG_CAPTION_MAX]},
                             {"document": (fname, data, mime or "application/octet-stream")})

    def _send_file(self, keys, number, thread, media, caption) -> bool:
        _state, path, _size, mime, _code = media
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1] or ".bin"
        return self._send_bytes(keys, number, thread, "file" + ext, data, mime, caption)

    def _topic_name(self, number) -> str:
        name = ""
        conn = self._q()
        try:
            try:
                r = conn.execute("SELECT name FROM wa_contacts WHERE number=?", (number,)).fetchone()
                name = (r[0] if r else "") or ""
            except sqlite3.OperationalError:
                name = ""
            if not name:
                r = conn.execute("SELECT name FROM wa_inbox WHERE from_number=? AND name <> '' "
                                 "ORDER BY id DESC LIMIT 1", (number,)).fetchone()
                name = (r[0] if r else "") or ""
        finally:
            conn.close()
        return ((name.strip() or NO_NAME) + " · +" + number.lstrip("+"))[:128]

    def show_step(self):
        if not self.show:
            return
        if not self._check_ready():
            return
        start = int(self._kv("show_start_id", "0"))
        open_from = int(self._kv("open_from_id", str(start + 1)))
        topics = {n: (t, trig, stage) for n, t, trig, stage in
                  self.st.execute("SELECT number, thread_id, trigger_id, stage FROM topics")}
        for row in self._rows("id >= ? ORDER BY id", (open_from,)):
            num = row["from_number"] or ""
            if num and num not in topics and _is_live(row):
                name = self._topic_name(num)
                thread = self._open_topic(name)
                if thread is None:
                    return
                topics[num] = (thread, row["id"], T_HEAD)
                self.st.execute("INSERT INTO topics(number, thread_id, trigger_id, stage, ts, name) "
                                "VALUES (?,?,?,?,?,?)", (num, thread, row["id"], T_HEAD, self.clock(), name))
                self.st.commit()
                log.info("показ: тема открыта thread=%d по строке=%d", thread, row["id"])
        for num, (thread, trig, stage) in topics.items():
            if not self.ready:
                return
            self._advance(num, thread, trig, stage)
        self.rename_step()

    def _open_topic(self, name):
        ok, res = self.tg("createForumTopic", {"chat_id": self.env["tg_chat"], "name": name})
        if not ok:
            return None
        return int(res.get("message_thread_id"))

    def rename_step(self):
        """Имя темы догоняет имя клиента: появилось или сменилось — editForumTopic ОДИН раз на смену.
        Имени нет — тему не трогаем (прежнее имя «без имени» не затирает). Тема, открытая до
        правки (имя не записано), сверяется один раз: 400 «не изменено» — тоже «записано»."""
        now = self.clock()
        if self.names_checked is not None and now - self.names_checked < RENAME_EVERY:
            return
        self.names_checked = now
        for num, thread, stored in self.st.execute("SELECT number, thread_id, name FROM topics").fetchall():
            if not self.ready:
                return
            name = self._topic_name(num)
            if name == stored:
                continue
            if name.startswith(NO_NAME + " · "):
                if stored is None:
                    self._topic_named(num, name)
                continue
            ok, res = self.tg("editForumTopic", {"chat_id": self.env["tg_chat"],
                                                 "message_thread_id": thread, "name": name})
            if ok or (ok is False and res == 400):
                self._topic_named(num, name)
                log.info("показ: имя темы thread=%d %s", thread, "переименована" if ok else "уже то (400)")

    def _topic_named(self, number, name):
        self.st.execute("UPDATE topics SET name=? WHERE number=?", (name, number))
        self.st.commit()

    def _stage(self, number, stage):
        self.st.execute("UPDATE topics SET stage=? WHERE number=?", (stage, number))
        self.st.commit()

    def _advance(self, num, thread, trig, stage):
        rows = [r for r in self._rows("from_number=? ORDER BY id", (num,)) if not _is_receipt(r)]
        if stage != T_LIVE:
            # реакции — не реплики: в предысторию не идут, живые ставятся на своё сообщение ниже
            items, missing = self.prehistory(num, [r for r in rows if not _is_reaction(r)], trig)
            tail = items[-TAIL_N:]
        if stage == T_HEAD:                                   # шапка: писал ли раньше, чего нет
            if not self._is_shown("head:" + num):
                if not self._send_text(["head:" + num], num, thread, head_text(items, missing)):
                    return
            stage = T_HIST
            self._stage(num, stage)
        if stage == T_HIST:                                   # вся предыстория — файлом .txt
            if items and not self._is_shown("hist:" + num):
                cap = "вся прежняя переписка: %d сообщений, %s — %s" % (
                    len(items), pk_date(items[0]["ts"]), pk_date(items[-1]["ts"]))
                if not self._send_bytes(["hist:" + num], num, thread, "history.txt",
                                        history_txt(items), "text/plain", cap):
                    return
            stage = T_TAIL
            self._stage(num, stage)
        if stage == T_TAIL:                                   # последние TAIL_N — текстом
            lines = [("msg:" + it["key"], item_line(it)) for it in tail
                     if not self._is_shown("msg:" + it["key"])]
            for keys, text in batch_lines(lines):
                if not self._send_text(keys, num, thread, text):
                    return
            stage = T_FILES
            self._stage(num, stage)
        if stage == T_FILES:                                  # их медиа — файлами
            for it in tail:
                key = "file:" + it["key"]
                if not it["file"] or self._is_shown(key):
                    continue
                path, _size, mime = it["file"]
                size = os.path.getsize(path)
                cap = "%s %s" % (pk_full(it["ts"]), it["who"])
                if size > TG_FILE_MAX:
                    sent = self._send_text([key], num, thread, "%s: [%s — файл %d МБ на сервере, больше "
                                           "лимита Telegram]" % (cap, it["word"], size // 2 ** 20))
                else:
                    with open(path, "rb") as f:
                        data = f.read()
                    sent = self._send_bytes([key], num, thread, "file" + (os.path.splitext(path)[1] or ".bin"),
                                            data, mime, cap)
                if not sent:
                    return
            stage = T_LIVE
            self._stage(num, stage)
        if stage == T_LIVE:
            for r in rows:
                if r["id"] < trig:
                    continue
                key = "msg:" + _row_key(r)
                if self._is_shown(key):
                    continue
                if _is_reaction(r):
                    if int(r["history"] or 0):
                        continue                              # досинхрон: не живое
                    if not self._react_one(num, thread, r, key):
                        return
                elif (r["msg_type"] or "") == REVOKE_TYPE:
                    if not self._revoke_one(num, thread, r, key, trig):
                        return
                elif (r["msg_type"] or "") == EDIT_TYPE and wa_history.edit_of(r)[1]:
                    if not self._edit_one(num, thread, r, key, trig):
                        return
                elif not self._show_one(num, thread, r, key):
                    return

    def _target_where(self, target):
        """wamid цели → («msg»|«file», id сообщения темы), где она показана ОДНА · (None, None)."""
        for p in ("msg", "file"):
            r = self.st.execute("SELECT msg_id FROM shown WHERE key=? AND state=? AND solo=1 "
                                "AND msg_id IS NOT NULL", (p + ":" + target, S_SHOWN)).fetchone()
            if r:
                return p, int(r[0])
        return None, None

    def _target_msg(self, target):
        """wamid цели → id сообщения темы, где она показана ОДНА (текстом или файлом) · None."""
        return self._target_where(target)[1]

    def _revoke_target(self, row):
        """Строка удаления → wamid удалённого (revoke.original_message_id тела в raw) · None."""
        conn = self._q()
        try:
            raw = conn.execute("SELECT raw FROM wa_inbox WHERE id=?", (row["id"],)).fetchone()
        finally:
            conn.close()
        try:
            rv = (json.loads(raw[0] or "null") or {}).get("revoke") or {}
            return rv.get("original_message_id") or None
        except (TypeError, ValueError, AttributeError):
            return None

    def _target_ts(self, num, target, trows):
        """Время удалённого: строка очереди, иначе запись архива номера по key_id · None."""
        if trows:
            return int(trows[0]["ts_msg"] or trows[0]["ts_queued"] or 0)
        key_id = parse_wamid(target)[1] if target else None
        if not key_id:
            return None
        conn, _why = self._archive()
        if conn is None:
            return None
        try:
            a = conn.execute("SELECT ts FROM messages WHERE number=? AND key_id=? ORDER BY ts LIMIT 1",
                             (num, key_id)).fetchone()
            return int(a[0]) if a else None
        except sqlite3.Error:
            return None
        finally:
            conn.close()

    def _shown_body(self, prefix, trow, trig, new=None):
        """Что показано в теме по строке цели → («text»|«caption», текст) — теми же функциями, что
        показывали: живая лента (id ≥ trig) — _live_view; хвост предыстории — item_line текстом,
        файл хвоста — подпись «дата кто». new — текст правки: та же строка с новым текстом."""
        if new is not None:
            trow = wa_history.edited(trow, new)
        if prefix == "file":
            return "caption", "%s %s" % (pk_full(trow["ts_msg"] or trow["ts_queued"]), who_of(trow)) \
                + (" · " + new if new is not None else "")
        if trow["id"] >= trig:
            how, _media, text = self._live_view(trow)
            return ("caption" if how == "file" else "text"), text
        return "text", item_line(wa_history.queue_item(trow, self._media_of))

    def _revoke_one(self, num, thread, r, key, trig) -> bool:
        """Удаление с телефона (revoke). Цель показана ОДНА и её id есть — правка этого сообщения:
        прежний текст остаётся зачёркнутым, ниже «🗑 удалено с телефона ЧЧ:ММ» (сотрудник видит, ЧТО
        удалено, — в переписке и файле истории оно всё равно лежит). Иначе (цель в пачке, показана
        до хранения id, не показана, не из этой темы, правку чат не принял) — одна строка
        «🗑 удалено сообщение от ЧЧ:ММ». Ключ строки — как у всех; цель — ещё и «rev:<wamid>»:
        повтор тела, рестарт и второй revoke той же цели правку не повторяют."""
        target = self._revoke_target(r)
        when = pk_hm(r["ts_msg"] or r["ts_queued"])
        if target and self._is_shown(REVOKE_KEY + target):
            self._mark([key], num, S_SHOWN)               # цель уже помечена — второй правки нет
            return True
        trows = self._rows("wamid=?", (target,)) if target else []
        prefix, mid = self._target_where(target) if (target and trows) else (None, None)
        if mid is not None:
            how, old = self._shown_now(prefix, trows[0], trig)
            mark = "🗑 удалено с телефона " + when
            cap = TG_CAPTION_MAX if how == "caption" else TG_TEXT_MAX
            old = old[:cap - len(mark) - 1]
            ent = [{"type": "strikethrough", "offset": 0, "length": utf16_len(old)}]
            params = {"chat_id": self.env["tg_chat"], "message_id": mid}
            if how == "caption":
                method = "editMessageCaption"
                params.update(caption=old + "\n" + mark, caption_entities=ent)
            else:
                method = "editMessageText"
                params.update(text=old + "\n" + mark, entities=ent)
            self._mark([key], num, S_SENDING)
            ok, res = self.tg(method, params)
            if ok:
                self._mark([key, REVOKE_KEY + target], num, S_SHOWN)
                self.counts["shown"] += 1
                return True
            if ok is None:
                self._mark([key, REVOKE_KEY + target], num, S_UNSURE)
                return False
            self._unmark([key])
            if res != 400:
                return False                                  # повторим следующим тактом
            # 400 — чат правку не принял: строкой, ответом на цель
        ts = self._target_ts(num, target, trows)
        if ts is None:
            what = "🗑 удалено сообщение — какое, неизвестно"
        else:
            same_day = pk_date(ts) == pk_date(r["ts_msg"] or r["ts_queued"])
            what = "🗑 удалено сообщение от " + (pk_hm(ts) if same_day else pk_time(ts))
        params = {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                  "text": "%s %s: %s" % (pk_time(r["ts_msg"] or r["ts_queued"]), who_of(r), what)}
        reply = mid if mid is not None else self._any_msg(target)
        if reply is not None:
            params["reply_parameters"] = {"message_id": reply, "allow_sending_without_reply": True}
        keys = [key, REVOKE_KEY + target] if target else [key]
        return self._deliver(keys, num, "sendMessage", params)

    # ── правка с телефона (WAPHONEEDIT0210) ────────────────────────────────────────────────
    def _edit_last(self, target):
        """Последняя правка, легшая на цель → (id строки правки, «edit»|«line») · None."""
        return self.st.execute("SELECT row_id, how FROM edits WHERE target=?", (target,)).fetchone()

    def _edit_set(self, target, row_id, how):
        self.st.execute("INSERT OR REPLACE INTO edits(target, row_id, how, ts) VALUES (?,?,?,?)",
                        (target, row_id, how, self.clock()))
        self.st.commit()

    def _edit_view(self, prefix, trow, trig, erow):
        """Цель после правки erow → («text»|«caption», текст) — ровно то, что уходит в правку сообщения:
        вид строки цели с новым текстом, ниже «✏️ изменено с телефона ЧЧ:ММ» (время правки, Пхукет)."""
        how, body = self._shown_body(prefix, trow, trig, wa_history.edit_of(erow)[1])
        mark = "✏️ изменено с телефона " + pk_hm(erow["ts_msg"] or erow["ts_queued"])
        cap = TG_CAPTION_MAX if how == "caption" else TG_TEXT_MAX
        return how, body[:cap - len(mark) - 1] + "\n" + mark

    def _shown_now(self, prefix, trow, trig):
        """Что сообщение цели показывает СЕЙЧАС: последняя правка легла правкой — её вид, иначе прежний."""
        last = self._edit_last(trow["wamid"]) if trow["wamid"] else None
        if last is not None and last[1] == "edit":
            erow = self._rows("id=?", (last[0],))
            if erow and wa_history.edit_of(erow[0])[1]:
                return self._edit_view(prefix, trow, trig, erow[0])
        return self._shown_body(prefix, trow, trig)

    def _edit_one(self, num, thread, r, key, trig) -> bool:
        """Правка с телефона с новым текстом. Цель показана ОДНА и её id есть — правка этого сообщения
        темы: тот же вид строки с новым текстом, ниже «✏️ изменено с телефона ЧЧ:ММ» (текст —
        editMessageText, файл — editMessageCaption). Иначе (цель в пачке, показана до хранения id, не
        показана, не из этой темы, правку чат не принял) — одна строка «✏️ изменено сообщение от ЧЧ:ММ,
        теперь: …» ответом на цель, если она показана хоть в пачке. Ключ строки — как у всех; тот же
        текст на ту же цель ещё раз (досинхрон под другим wamid) второй правки и строки не даёт."""
        target, new = wa_history.edit_of(r)
        last = self._edit_last(target) if target else None
        if last is not None:
            prev = self._rows("id=?", (last[0],))
            if prev and wa_history.edit_of(prev[0])[1] == new:
                self._mark([key], num, S_SHOWN)               # этот текст уже лёг — второй правки нет
                return True
        trows = self._rows("wamid=?", (target,)) if target else []
        prefix, mid = self._target_where(target) if (target and trows) else (None, None)
        if mid is not None:
            how, text = self._edit_view(prefix, trows[0], trig, r)
            params = {"chat_id": self.env["tg_chat"], "message_id": mid}
            if how == "caption":
                method = "editMessageCaption"
                params["caption"] = text
            else:
                method = "editMessageText"
                params["text"] = text
            self._mark([key], num, S_SENDING)
            ok, res = self.tg(method, params)
            if ok:
                self._edit_set(target, r["id"], "edit")
                self._mark([key], num, S_SHOWN)
                self.counts["shown"] += 1
                return True
            if ok is None:
                self._edit_set(target, r["id"], "edit")      # исход неизвестен — повтора нет
                self._mark([key], num, S_UNSURE)
                return False
            self._unmark([key])
            if res != 400:
                return False                                  # повторим следующим тактом
            # 400 — чат правку не принял: строкой, ответом на цель
        at = r["ts_msg"] or r["ts_queued"]
        ts = self._target_ts(num, target, trows)
        what = "✏️ изменено сообщение" + ("" if ts is None else
                                          " от " + (pk_hm(ts) if pk_date(ts) == pk_date(at) else pk_time(ts)))
        params = {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                  "text": ("%s %s: %s, теперь: %s" % (pk_time(at), who_of(r), what, new))[:TG_TEXT_MAX]}
        reply = mid if mid is not None else self._any_msg(target)
        if reply is not None:
            params["reply_parameters"] = {"message_id": reply, "allow_sending_without_reply": True}
        if not self._deliver([key], num, "sendMessage", params):
            return False
        if target:
            self._edit_set(target, r["id"], "line")
        return True

    def _any_msg(self, target):
        """id сообщения темы, где цель показана хоть в пачке (для ответа строкой) · None."""
        if not target:
            return None
        r = self.st.execute("SELECT msg_id FROM shown WHERE key IN (?, ?) AND state=? AND msg_id IS NOT NULL",
                            ("msg:" + target, "file:" + target, S_SHOWN)).fetchone()
        return int(r[0]) if r else None

    def _agent_target(self, target):
        """wamid цели в базе агента (WAMIRROR0410, только mode=ro) → (id строки показа в теме | None, текст ушедшей
        версии | None, наше ли это сообщение). Базы, таблицы или строки нет — (None, None, False)."""
        path = self.env.get("agent_db")
        if not target or not path or not os.path.exists(path):
            return None, None, False
        mid, text, ours = None, None, False
        try:
            conn = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"), uri=True, timeout=5)
            try:
                have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "agent_show" in have:
                    row = conn.execute("SELECT msg_id, chat_id FROM agent_show WHERE wamid=? AND state='shown' "
                                       "AND msg_id IS NOT NULL ORDER BY shown_at LIMIT 1", (target,)).fetchone()
                    if row and (row[1] is None or str(row[1]) == str(self.env.get("tg_chat"))):
                        mid, ours = int(row[0]), True
                if "outbox" in have:
                    cols = {c[1] for c in conn.execute("PRAGMA table_info(outbox)")}
                    row = conn.execute("SELECT text, %s FROM outbox WHERE wamid=?" % (
                        "kind" if "kind" in cols else "NULL"), (target,)).fetchone()
                    if row:
                        ours = True
                        word = _MEDIA_WORD.get(row[1] or "") or ("документ" if row[1] == "document" else None)
                        text = row[0] or ("[%s]" % word if word else None)
                if not text and "drafts" in have:
                    row = conn.execute("SELECT text FROM drafts WHERE wamid=?", (target,)).fetchone()
                    if row:
                        ours, text = True, row[0] or None
            finally:
                conn.close()
        except sqlite3.Error as e:
            self._warn_hourly("agent_db", "база агента не прочитана (%s) — реакция на наше сообщение без текста",
                              type(e).__name__)
        return mid, text, ours

    def _react_one(self, num, thread, r, key) -> bool:
        """Реакция → реакция бота на сообщение темы с её целью; иначе — короткая строка.
        Одна реакция бота на сообщение: держится последняя непустая из сторон «клиент»/«мы»;
        снятие одной стороны возвращает реакцию другой. Ключ строки — как у всех ("msg:"+wamid),
        поэтому повтор тела и рестарт второй раз её не ставят."""
        emoji, target = self._react_fields(r)
        who = who_of(r)
        mid = prev = None
        if target:
            prev = self.st.execute("SELECT emoji FROM reacts WHERE target=? AND side=?",
                                   (target, who)).fetchone()
            self.st.execute("INSERT OR REPLACE INTO reacts(target, side, emoji, row_id) VALUES (?,?,?,?)",
                            (target, who, emoji, r["id"]))
            self.st.commit()
            mid = self._target_msg(target)
        a_mid = a_text = None
        ours = False
        if target and mid is None:
            # цель не показана зеркалом — возможно, наше сообщение через API (WAMIRROR0410): строка показа агента
            a_mid, a_text, ours = self._agent_target(target)
            mid = a_mid
        line = None
        self._mark([key], num, S_SENDING)
        if mid is not None:
            cur = self.st.execute("SELECT emoji FROM reacts WHERE target=? AND side<>? AND emoji<>'' "
                                  "ORDER BY row_id DESC LIMIT 1", (target, SIDE_TG)).fetchone()
            want = tg_emoji(cur[0]) if cur else ""
            held = self.st.execute("SELECT emoji FROM reacts WHERE target=? AND side=?",
                                   (target, SIDE_TG)).fetchone()
            if want != (held[0] if held else ""):
                ok, res = self.tg("setMessageReaction", {
                    "chat_id": self.env["tg_chat"], "message_id": mid,
                    "reaction": [{"type": "emoji", "emoji": want}] if want else []})
                if ok is None:
                    self._mark([key], num, S_UNSURE)
                    return False
                if ok:
                    self.st.execute("INSERT OR REPLACE INTO reacts(target, side, emoji, row_id) "
                                    "VALUES (?,?,?,?)", (target, SIDE_TG, want, r["id"]))
                    self.st.commit()
                elif res == 400:
                    line = True                               # чат не принял — строкой
                else:
                    self._unmark([key])
                    return False
            if emoji and not tg_emoji(emoji):
                line = True                                   # вне набора Telegram — строкой
            elif not emoji and prev and prev[0] and not tg_emoji(prev[0]):
                line = True                                   # снята реакция, показанная строкой
        else:
            line = True                                       # цель не показана отдельным сообщением
        if not line:
            self._mark([key], num, S_SHOWN)
            self.counts["shown"] += 1
            return True
        self._unmark([key])
        rows = self._rows("wamid=?", (target,)) if target else []
        # квитанция текстом цели не бывает (WAMIRROR0410): по wamid нашего API-сообщения в очереди лежит только она
        tgt = [x for x in rows if not _is_receipt(x)]
        ours = ours or len(tgt) < len(rows)
        what, pre = (("реакция " + emoji, "на") if emoji else ("снял реакцию", "с"))
        if tgt:
            to = "%s «%s»" % (pre, body_of(tgt[0])[:40])
        elif a_text:
            to = "%s «%s»" % (pre, a_text[:40])
        elif ours:
            to = "на наше сообщение" if emoji else "с нашего сообщения"
        else:
            to = ("на сообщение" if emoji else "с сообщения") + " не из этой темы"
        params = {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                  "text": "%s %s: %s %s" % (pk_time(r["ts_msg"] or r["ts_queued"]), who, what, to)}
        if mid is not None:
            params["reply_parameters"] = {"message_id": mid, "allow_sending_without_reply": True}
        return self._deliver([key], num, "sendMessage", params)

    def _live_view(self, r):
        """Живая строка → («file», опись файла, подпись) — показ файлом · («text», None, текст).
        Ею же _revoke_one восстанавливает показанное, когда ставит пометку удаления."""
        head = "%s %s" % (pk_time(r["ts_msg"] or r["ts_queued"]), who_of(r))
        if not r["media_id"]:
            return "text", None, "%s: %s" % (head, body_of(r))
        media = self._media_of(_row_key(r))
        state = media[0] if media else None
        if state == M_OK and (media[2] or 0) <= TG_FILE_MAX:
            return "file", media, head + (" · " + r["caption"] if r["caption"] else "")
        word = _MEDIA_WORD.get(r["msg_type"] or "") or wa_history.FILE_WORD
        if state == M_OK:
            note = "файл %d МБ на сервере, больше лимита Telegram" % ((media[2] or 0) // 2 ** 20)
        else:
            note = "файл не скачан" + (", код " + media[4] if media and media[4] else "")
        return "text", None, "%s: [%s — %s]%s" % (head, word, note,
                                                  (" " + r["caption"]) if r["caption"] else "")

    def _show_one(self, num, thread, r, key) -> bool:
        if r["media_id"]:
            media = self._media_of(_row_key(r))
            state = media[0] if media else None
            if state in (None, M_RETRY) and self.clock() - (r["ts_queued"] or 0) < MEDIA_WAIT:
                return False  # файл ещё качается — порядок темы важнее скорости
        how, media, text = self._live_view(r)
        if how == "file":
            return self._send_file([key], num, thread, media, text)
        return self._send_text([key], num, thread, text)

    # ── 3. ожидание и сводка ─────────────────────────────────────────────────────────────
    def _overdue(self):
        start = int(self._kv("show_start_id", "0"))
        now = self.clock()
        out = []
        for r in self._rows("id > ? ORDER BY id", (start,)):
            if _is_live(r) and now - (r["ts_queued"] or 0) > ALARM_AFTER \
                    and not self._is_shown("msg:" + _row_key(r)):
                out.append(r["id"])
        return out

    def watch_step(self):
        now = self.clock()
        overdue = self._overdue() if (self.show and self.ready) else []
        fresh = [i for i in overdue
                 if not self.st.execute("SELECT 1 FROM alarmed WHERE row_id=?", (i,)).fetchone()]
        if fresh:
            text = ("⚠️ показ WhatsApp отстал: %d живых сообщений старше 10 минут не показаны "
                    "(всего просрочено %d)" % (len(fresh), len(overdue)))
            ok, _ = self.tg("sendMessage", {"chat_id": self.env["tg_chat"], "text": text})
            if ok:
                for i in fresh:
                    self.st.execute("INSERT OR IGNORE INTO alarmed(row_id, ts) VALUES (?,?)", (i, now))
                self.st.commit()
            log.warning("ожидание: %d живых строк старше 10 минут без показа, тревога %s",
                        len(overdue), "отправлена" if ok else "НЕ отправлена")
        if self.last_summary is None or now - self.last_summary >= SUMMARY_EVERY:
            self.last_summary = now
            line = self.summary(len(overdue))
            log.info("%s", line)
            if overdue and self.ready:
                self.tg("sendMessage", {"chat_id": self.env["tg_chat"], "text": line})

    def summary(self, overdue=0) -> str:
        m = dict(self.st.execute("SELECT state, COUNT(*) FROM media GROUP BY state").fetchall())
        s = dict(self.st.execute("SELECT state, COUNT(*) FROM shown GROUP BY state").fetchall())
        topics = self.st.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
        show = "выключен" if not self.show else ("идёт" if self.ready else "СТОИТ")
        return ("сводка: показ=%s тем=%d показано=%d без_ответа=%d просрочено=%d · медиа ok=%d "
                "отказ=%d повтор=%d потолок=%d занято=%d потолок_байт=%d"
                % (show, topics, s.get(S_SHOWN, 0), s.get(S_UNSURE, 0), overdue, m.get(M_OK, 0),
                   m.get(M_FAIL, 0), m.get(M_RETRY, 0), m.get(M_WAIT, 0), self.media_used, self.cap))

    def tick(self):
        if not os.path.exists(self.queue_db):
            self._warn_hourly("no_queue", "очередь не найдена — жду")
            return
        self.media_step()
        self.archive_step()
        self.show_step()
        self.watch_step()


def start_line(m) -> str:
    return ("wa-tg-mirror: показ %s (флаг %s) · медиа всегда: каталог %s, потолок %d байт, пол "
            "свободного %d · очередь только чтение: %s · архив: %s, опись медиа: %s"
            % ("включён" if m.show else "выключен", FLAG_NAME, m.media_dir, m.cap, FREE_FLOOR,
               m.queue_db, "есть" if os.path.exists(m.env.get("archive_db") or "") else "нет",
               "есть" if os.path.exists(m.env.get("archive_manifest") or "") else "нет"))


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    env = _env()
    m = Mirror(env)
    log.info("%s", start_line(m))
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    while not stop:
        try:
            m.tick()
        except Exception as e:
            log.error("такт упал: %s", type(e).__name__, exc_info=True)
        for _ in range(TICK_SECS * 2):
            if stop:
                break
            time.sleep(0.5)
    log.info("wa-tg-mirror: остановлен")


if __name__ == "__main__":
    main()
