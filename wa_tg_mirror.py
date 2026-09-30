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
   Тема «имя · номер» открывается по первому ЖИВОМУ входящему или эху клиента. В неё сначала вся
   прежняя переписка сводными сообщениями до 4000 знаков, по времени, «клиент»/«мы», время
   Пхукета; заглушка медиа — «файл Meta не отдаёт»; затем строка о провале 08.09–01.10; затем
   файлы; затем новое. Дальше каждое живое сообщение — в свою тему; квитанции не показываются.
   Темп — не больше 20 вызовов в минуту; 429 — ждать retry_after. wamid дважды не показывается:
   ключ ставится ДО вызова, так что обрыв посреди вызова даёт «не повторять», а не дубль.

Живая wa_queue.db открывается ТОЛЬКО на чтение (mode=ro). Своё состояние — wa_tg_mirror.db рядом.
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

import wa_kind

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
PHUKET_OFFSET  = 7 * 3600
WARN_EVERY     = 3600          # WARNING «показ стоит» — не чаще раза в час
RECHECK_EVERY  = 300           # стоящий показ перепроверяется раз в 5 минут
ALARM_AFTER    = 600           # живая строка без показа дольше 10 минут — тревога
SUMMARY_EVERY  = 300           # сводка числами раз в 5 минут
MEDIA_WAIT     = 180           # живое медиа ждёт своего файла не дольше 3 минут
MEDIA_TRIES    = 5
FREE_FLOOR     = 5 * 1024 ** 3     # после записи свободного места не меньше 5 GiB
CAP_SHARE      = 0.20              # потолок каталога — 20% свободного места на старте …
CAP_MAX        = 4 * 1024 ** 3     # … но не больше 4 GiB

GAP_LINE         = "с 08.09 по 01.10 переписки на сервере нет — она в WhatsApp на телефоне"
PLACEHOLDER_TEXT = "файл Meta не отдаёт"
MEDIA_PLACEHOLDER = "media_placeholder"
_KEY_FORM = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

_MEDIA_WORD = {"image": "фото", "video": "видео", "audio": "аудио", "voice": "голосовое",
               "document": "документ", "sticker": "стикер"}
_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4",
        "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac",
        "application/pdf": ".pdf", "video/3gpp": ".3gp"}

# медиа: конечные состояния — повтор не качается
M_OK, M_FAIL, M_RETRY, M_WAIT = "ok", "fail", "retry", "wait"
# показ: ключ ставится ДО вызова (sending), после ответа — shown; обрыв → unsure, повтора нет
S_SENDING, S_SHOWN, S_UNSURE = "sending", "shown", "unsure"
# ступени темы
T_BACKFILL, T_GAP, T_FILES, T_LIVE = "backfill", "gap", "files", "live"

_QCOLS = ("id", "ts_queued", "from_number", "name", "msg_type", "text", "media_id", "mime",
          "caption", "media_note", "ts_msg", "echo", "history", "wamid")


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
        "d360_key":  (os.environ.get("WA_D360_API_KEY") or "").strip(),
        "tg_token":  (os.environ.get("WA_TG_BOT_TOKEN") or "").strip(),
        "tg_chat":   (os.environ.get("WA_TG_CHAT_ID") or "").strip(),
        "show":      _flag_on(os.environ.get(FLAG_NAME)),
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


def who_of(row) -> str:
    kind = wa_kind.kind_of(row["msg_type"], row["echo"], row["history"])
    if kind == wa_kind.KIND_ECHO:
        return "мы"
    if kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_HISTORY):
        return "клиент"
    return "?"


def body_of(row) -> str:
    t = row["msg_type"] or ""
    if t == MEDIA_PLACEHOLDER:
        return "[медиа — " + PLACEHOLDER_TEXT + "]"
    if t in _MEDIA_WORD:
        s = "[" + _MEDIA_WORD[t] + "]"
        return s + (" " + row["caption"] if row["caption"] else "")
    if row["text"]:
        return row["text"]
    return "[" + (t or "?") + "]"


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


def _row_key(row) -> str:
    return row["wamid"] or ("row:%d" % row["id"])


def _is_live(row) -> bool:
    if int(row["history"] or 0):
        return False
    kind = wa_kind.kind_of(row["msg_type"], row["echo"], row["history"])
    return kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_ECHO)


def _is_receipt(row) -> bool:
    return wa_kind.kind_of(row["msg_type"], row["echo"], row["history"]) == wa_kind.KIND_RECEIPT


_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS media (key TEXT PRIMARY KEY, row_id INTEGER, state TEXT, path TEXT,
    size INTEGER, mime TEXT, code TEXT, tries INTEGER NOT NULL DEFAULT 0,
    next_try REAL NOT NULL DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS shown (key TEXT PRIMARY KEY, number TEXT, state TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS topics (number TEXT PRIMARY KEY, thread_id INTEGER, trigger_id INTEGER,
    stage TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS alarmed (row_id INTEGER PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)
"""


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
        self.ready = False
        self.ready_checked = None
        self.block_reason = ""
        self._warned = {}
        self.last_summary = None
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
            return conn.execute("SELECT " + ", ".join(_QCOLS) + " FROM wa_inbox WHERE " + where,
                                args).fetchall()
        finally:
            conn.close()

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
            conn = self._q()
            try:
                mx = conn.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
            finally:
                conn.close()
            self._kv_set("show_start_id", mx)
            log.info("показ: первое включение, живые строки считаются с id > %d", mx)
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

    def _mark(self, keys, number, state):
        now = self.clock()
        for k in keys:
            self.st.execute("INSERT OR REPLACE INTO shown(key, number, state, ts) VALUES (?,?,?,?)",
                            (k, number, state, now))
        self.st.commit()

    def _unmark(self, keys):
        for k in keys:
            self.st.execute("DELETE FROM shown WHERE key=? AND state=?", (k, S_SENDING))
        self.st.commit()

    def _deliver(self, keys, number, method, params, files=None) -> bool:
        """Ключи ставятся ДО вызова: обрыв процесса посреди вызова повтора не даёт."""
        self._mark(keys, number, S_SENDING)
        ok, _ = self.tg(method, params, files)
        if ok:
            self._mark(keys, number, S_SHOWN)
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

    def _send_file(self, keys, number, thread, media, caption) -> bool:
        _state, path, _size, mime, _code = media
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1] or ".bin"
        return self._deliver(keys, number, "sendDocument",
                             {"chat_id": self.env["tg_chat"], "message_thread_id": thread,
                              "caption": caption[:TG_CAPTION_MAX]},
                             {"document": ("file" + ext, data, mime or "application/octet-stream")})

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
        return ((name.strip() or "без имени") + " · +" + number.lstrip("+"))[:128]

    def show_step(self):
        if not self.show:
            return
        if not self._check_ready():
            return
        start = int(self._kv("show_start_id", "0"))
        topics = {n: (t, trig, stage) for n, t, trig, stage in
                  self.st.execute("SELECT number, thread_id, trigger_id, stage FROM topics")}
        for row in self._rows("id > ? ORDER BY id", (start,)):
            num = row["from_number"] or ""
            if num and num not in topics and _is_live(row):
                thread = self._open_topic(num)
                if thread is None:
                    return
                topics[num] = (thread, row["id"], T_BACKFILL)
                self.st.execute("INSERT INTO topics(number, thread_id, trigger_id, stage, ts) "
                                "VALUES (?,?,?,?,?)", (num, thread, row["id"], T_BACKFILL, self.clock()))
                self.st.commit()
                log.info("показ: тема открыта thread=%d по строке=%d", thread, row["id"])
        for num, (thread, trig, stage) in topics.items():
            if not self.ready:
                return
            self._advance(num, thread, trig, stage)

    def _open_topic(self, number):
        ok, res = self.tg("createForumTopic", {"chat_id": self.env["tg_chat"],
                                               "name": self._topic_name(number)})
        if not ok:
            return None
        return int(res.get("message_thread_id"))

    def _stage(self, number, stage):
        self.st.execute("UPDATE topics SET stage=? WHERE number=?", (stage, number))
        self.st.commit()

    def _advance(self, num, thread, trig, stage):
        rows = [r for r in self._rows("from_number=? ORDER BY id", (num,)) if not _is_receipt(r)]
        prior = [r for r in rows if r["id"] < trig]
        if stage == T_BACKFILL:
            if not self._send_backfill(num, thread, prior):  # предыстория
                return
            stage = T_GAP
            self._stage(num, stage)
        if stage == T_GAP:
            if not self._is_shown("gap:" + num):
                if not self._send_text(["gap:" + num], num, thread, GAP_LINE):
                    return
            stage = T_FILES
            self._stage(num, stage)
        if stage == T_FILES:
            for r in sorted(prior, key=lambda r: (r["ts_msg"] or r["ts_queued"], r["id"])):
                key = "file:" + _row_key(r)
                media = self._media_of(_row_key(r))
                if not media or media[0] != M_OK or (media[2] or 0) > TG_FILE_MAX or self._is_shown(key):
                    continue
                cap = "%s %s" % (pk_time(r["ts_msg"] or r["ts_queued"]), who_of(r))
                if not self._send_file([key], num, thread, media, cap):
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
                if not self._show_one(num, thread, r, key):
                    return

    def _send_backfill(self, num, thread, prior) -> bool:
        items = [("msg:" + _row_key(r), line_of(r))
                 for r in sorted(prior, key=lambda r: (r["ts_msg"] or r["ts_queued"], r["id"]))
                 if not self._is_shown("msg:" + _row_key(r))]
        for keys, text in batch_lines(items):
            if not self._send_text(keys, num, thread, text):
                return False
        return True

    def _show_one(self, num, thread, r, key) -> bool:
        head = "%s %s" % (pk_time(r["ts_msg"] or r["ts_queued"]), who_of(r))
        if r["media_id"]:
            media = self._media_of(_row_key(r))
            state = media[0] if media else None
            if state == M_OK and (media[2] or 0) <= TG_FILE_MAX:
                cap = head + (" · " + r["caption"] if r["caption"] else "")
                return self._send_file([key], num, thread, media, cap)
            if state in (None, M_RETRY) and self.clock() - (r["ts_queued"] or 0) < MEDIA_WAIT:
                return False  # файл ещё качается — порядок темы важнее скорости
            word = _MEDIA_WORD.get(r["msg_type"] or "", r["msg_type"] or "файл")
            if state == M_OK:
                note = "файл %d МБ на сервере, больше лимита Telegram" % ((media[2] or 0) // 2 ** 20)
            else:
                note = "файл не скачан" + (", код " + media[4] if media and media[4] else "")
            text = "%s: [%s — %s]%s" % (head, word, note, (" " + r["caption"]) if r["caption"] else "")
            return self._send_text([key], num, thread, text)
        return self._send_text([key], num, thread, "%s: %s" % (head, body_of(r)))

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
        self.show_step()
        self.watch_step()


def start_line(m) -> str:
    return ("wa-tg-mirror: показ %s (флаг %s) · медиа всегда: каталог %s, потолок %d байт, пол "
            "свободного %d · очередь только чтение: %s"
            % ("включён" if m.show else "выключен", FLAG_NAME, m.media_dir, m.cap, FREE_FLOOR,
               m.queue_db))


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
