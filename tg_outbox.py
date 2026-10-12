#!/usr/bin/env python3
"""ИСХОДЯЩАЯ ОЧЕРЕДЬ TELEGRAM (TGSEND1310) — «✅ Отправить» на карточке канала TG уходит клиенту с
бизнес-аккаунта @turbophuket через userbot на ПК. Сервер писать клиенту Telegram сам не умеет и
не учится: он кладёт ответ в СВОЮ очередь, ПК забирает, шлёт и подтверждает.

ЧТО ЗДЕСЬ. Одна таблица `tg_out` в своём файле (путь — `TG_OUTBOX_DB`, по умолчанию `tg_outbox.db`
рядом с `tg_queue.db`; ни одного файла WA и ни одного файла канала TG — сверка в `wa_agent_svc` и
`wa_webhook`). Модуль ЧИСТЫЙ: sqlite3 и время, ни сети, ни Telegram, ни .env. Его зовут два
процесса — служба агента (дверь `TgDoor`: положить, ждать, отменить) и вход `wa_webhook`
(GET /tg-queue/outbox — забрать, POST /tg-queue/ack — подтвердить).

ЖИЗНЬ РЯДА (каждый переход — условный UPDATE, решает rowcount; SQLite сериализует пишущих):
    queued ──claim──▶ claimed ──ack──▶ sent | failed | unknown        (исход назвал ПК)
       └──cancel (дверь в срок, ТОЛЬКО из queued)──▶ cancelled           (ПК ряда не видел)
  • ЗАБРАТЬ (`claim`) можно только queued и только до `expires_at` — ряд, переживший дверь (служба
    упала посреди ожидания), не уйдёт клиенту никогда: его срок вышел, и следующий `put`/`claim`
    называет его cancelled.
  • ПОВТОРНАЯ ВЫДАЧА: claimed без подтверждения выдаётся СНОВА, пока не вышел срок и дверь ждёт
    (`door_gave_up` пуст). Это ответ на потерянный ответ GET: ПК, не видевший ряда, получает его со
    следующим опросом. Двойной отправки нет на стороне ПК — его журнал по `token`: ряд, который уже
    шёл, повторно не шлётся, а подтверждается из журнала.
  • ОТМЕНА (`cancel_queued`) — только queued → cancelled. Отменённый ряд не выдаётся ни одной дорогой:
    `claim` берёт только queued, повторная выдача — только claimed. Ни одной поздней отправки.
  • ДВЕРЬ ПЕРЕСТАЛА ЖДАТЬ (`give_up`) — claimed остаётся claimed (ПК мог отправить), но больше не
    выдаётся; позднее подтверждение ПК записывается (сверка эха по id сообщения его увидит).
  • ПОДТВЕРЖДЕНИЕ (`ack`) идемпотентно: первый исход окончателен, повтор того же — «уже записано»,
    иной — «уже записано: <первый>» без перезаписи; чужой токен, неизвестный id, отменённый ряд и
    ряд, который ПК не забирал, — отказ словами. Исход «sent» без целого msg_id > 0 не принимается.

КЛЮЧ ЭХА. Ушедшее сообщение вернётся лентой ПК рядом dir=out, и вход `wa_webhook.tg_row_event`
положит его в tg_queue.db с ключом `tg:<chat_id>:<msg_id>:out` (`wa_webhook.tg_wamid`). Дверь отдаёт
ядру РОВНО этот ключ полем `wamid` (`echo_wamid`): тогда ядро узнаёт эхо своей отправки прежним
`Core._our_wamid` (drafts.wamid), а история агента не задваивает реплику (`wa_history.with_sent`
сверяет по тому же ключу). Совпадение двух формул стережёт тест.
"""

import os
import re
import sqlite3
import time
import uuid

FLAG = "WA_AGENT_TG_SEND"                 # выключатель: только 1/true/yes/on (правило `wa_agent_tg.flag_on`)
# ОДИН выключатель — у службы агента (её drop-in). Вход wa_webhook его не читает: он судит по ПУЛЬСУ двери в
# самой очереди (`meta.door_beat`). Ядро канала TG с открытой дверью пишет пульс каждым тактом (раз в 5 с) и
# каждой постановкой; пульс старше DOOR_FRESH, нет файла или нет пульса — «отправка выключена»: выдача пуста,
# ПК опрашивает реже. Служба выключена флагом, упала или стоит — дверь закрывается сама через DOOR_FRESH.
DOOR_FRESH = 90                           # с: ожидание двери до 60 с + такт 5 с + запас
PATH_ENV = "TG_OUTBOX_DB"                 # путь файла очереди; нет — рядом с tg_queue.db
FILE_NAME = "tg_outbox.db"
WAIT_ENV = "WA_AGENT_TG_SEND_SEC"         # сколько дверь ждёт подтверждения ПК, с
WAIT_DEFAULT, WAIT_MIN, WAIT_MAX = 20, 5, 60   # потолок = бюджет отправки WhatsApp (wa_send.SEND_BUDGET_SEC)

QUEUED, CLAIMED = "queued", "claimed"
SENT, FAILED, UNKNOWN, CANCELLED = "sent", "failed", "unknown", "cancelled"
STATES = (QUEUED, CLAIMED, SENT, FAILED, UNKNOWN, CANCELLED)
FINAL = (SENT, FAILED, UNKNOWN, CANCELLED)
ACK_OUTCOMES = (SENT, FAILED, UNKNOWN)    # что вправе назвать ПК

TEXT_MAX = 4096                           # Telegram: текст сообщения ≤ 4096 знаков (единиц UTF-16)
ERROR_MAX = 300
CLAIM_LIMIT = 10
ECHO_BEFORE, ECHO_AFTER = 120, 900        # запасной путь сверки эха по тексту: окно вокруг постановки, с

_ECHO_RE = re.compile(r"^tg:(\d{1,20}):(\d{1,20}):out$")
_KEY_RE = re.compile(r"^tg:(-?\d{1,20})$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_out (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    token        TEXT    NOT NULL UNIQUE,
    chat_id      INTEGER NOT NULL,
    text         TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    created_at   REAL    NOT NULL,
    expires_at   REAL    NOT NULL,
    claimed_at   REAL,
    handed       INTEGER NOT NULL DEFAULT 0,
    door_gave_up REAL,
    acked_at     REAL,
    msg_id       INTEGER,
    error        TEXT,
    cancel_why   TEXT
);
CREATE INDEX IF NOT EXISTS idx_tg_out_state ON tg_out(state, expires_at);
CREATE INDEX IF NOT EXISTS idx_tg_out_msg ON tg_out(chat_id, msg_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_BEAT_SQL = ("INSERT INTO meta(key, value) VALUES('door_beat', ?) "
             "ON CONFLICT(key) DO UPDATE SET value=excluded.value")


def flag_on(raw) -> bool:
    """То же правило, что `wa_agent_tg.flag_on`: включает только явное 1/true/yes/on."""
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def path_of(environ, tg_queue_db) -> str:
    """Путь очереди: `TG_OUTBOX_DB` или `tg_outbox.db` рядом с файлом очереди канала TG."""
    raw = str((environ or {}).get(PATH_ENV) or "").strip()
    if raw:
        return raw
    return os.path.join(os.path.dirname(os.path.abspath(str(tg_queue_db))), FILE_NAME)


def wait_of(raw):
    """`WA_AGENT_TG_SEND_SEC` → (секунды, слова). Пусто — умолчание; не целое или вне 5–60 — умолчание и
    слово «битая»: дверь не ждёт дольше, чем цикл службы уже допускает отправке WhatsApp."""
    s = str(raw or "").strip()
    if not s:
        return WAIT_DEFAULT, "%d с" % WAIT_DEFAULT
    if re.fullmatch(r"\d{1,3}", s) and WAIT_MIN <= int(s) <= WAIT_MAX:
        return int(s), "%d с" % int(s)
    return WAIT_DEFAULT, "%d с (настройка %s битая — вне %d–%d)" % (WAIT_DEFAULT, WAIT_ENV, WAIT_MIN, WAIT_MAX)


def echo_wamid(chat_id, msg_id) -> str:
    """Ключ эха ушедшего сообщения в tg_queue.db — та же формула, что `wa_webhook.tg_wamid(…, "out")`."""
    return "tg:%d:%d:out" % (int(chat_id), int(msg_id))


def parse_echo(wamid):
    """`tg:<chat>:<msg>:out` → (chat_id, msg_id); иное → None."""
    m = _ECHO_RE.match(str(wamid or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def chat_of(key):
    """Ключ клиента очереди `tg:<chat_id>` → chat_id (int) или None."""
    m = _KEY_RE.match(str(key or ""))
    return int(m.group(1)) if m else None


def tg_len(text) -> int:
    """Длина текста так, как её меряет Telegram — единицами UTF-16."""
    return len(str(text or "").encode("utf-16-le", "surrogatepass")) // 2


def norm_text(text) -> str:
    """Текст для сверки эха: переводы строк к \\n, края без пробелов (Telegram их срезает)."""
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _row(r):
    if r is None:
        return None
    keys = ("id", "token", "chat_id", "text", "state", "created_at", "expires_at", "claimed_at", "handed",
            "door_gave_up", "acked_at", "msg_id", "error", "cancel_why")
    return dict(zip(keys, r))


_COLS = ("id, token, chat_id, text, state, created_at, expires_at, claimed_at, handed, door_gave_up, acked_at, "
         "msg_id, error, cancel_why")


class Outbox:
    """Очередь в файле `path`. Соединение — на операцию (два процесса, один файл); запись — BEGIN IMMEDIATE."""

    def __init__(self, path, clock=time.time, create=True):
        """create=False — только существующий файл (вход wa_webhook): нет файла — FileNotFoundError, файла не
        заводим — заводит его служба агента, когда выключатель включён."""
        self.path = str(path)
        self.clock = clock
        if not create and not os.path.exists(self.path):
            raise FileNotFoundError(self.path)
        if not os.path.exists(self.path):
            # тексты клиентам — файл только владельцу (как сырой архив входа); ОС без прав — как есть
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            os.close(fd)
        conn = self._conn()
        try:
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    def _conn(self):
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def _write(self, fn):
        """Одна пишущая транзакция: BEGIN IMMEDIATE … COMMIT; исключение — ROLLBACK и наружу."""
        conn = self._conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                out = fn(conn)
                conn.execute("COMMIT")
                return out
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        finally:
            conn.close()

    @staticmethod
    def _sweep(conn, now):
        """Просроченные queued → cancelled («срок вышел, ПК не забрал»): их дверь уже не ждёт."""
        return conn.execute("UPDATE tg_out SET state=?, cancel_why=? WHERE state=? AND expires_at<=?",
                            (CANCELLED, "срок вышел — ПК не забрал", QUEUED, now)).rowcount

    # ── сторона двери ──────────────────────────────────────────────────────────────────────

    def put(self, chat_id, text, wait, token=None, now=None):
        """Ряд queued со сроком now+wait. → (id, token). token — свой (дверь заводит его ДО записи, чтобы
        отменить ряд и тогда, когда ответ на запись потерян)."""
        now = self.clock() if now is None else float(now)
        token = token or uuid.uuid4().hex

        def fn(conn):
            self._sweep(conn, now)
            conn.execute(_BEAT_SQL, (repr(now),))          # постановка — тоже пульс: пока дверь ждёт, такта нет
            cur = conn.execute("INSERT INTO tg_out(token, chat_id, text, state, created_at, expires_at) "
                               "VALUES(?,?,?,?,?,?)", (token, int(chat_id), str(text), QUEUED, now, now + float(wait)))
            return cur.lastrowid
        return self._write(fn), token

    # ── пульс двери: единственный выключатель живёт у службы агента ──────────────────────────

    def beat(self, now=None):
        """Дверь открыта прямо сейчас (зовёт ядро канала TG каждым тактом)."""
        now = self.clock() if now is None else float(now)
        self._write(lambda conn: conn.execute(_BEAT_SQL, (repr(now),)))

    def door(self, now=None, fresh=DOOR_FRESH):
        """→ (открыта?, возраст пульса с | None). Пульса нет, он битый или старше fresh — закрыта; пульс «из
        будущего» дальше fresh (часы поехали) — тоже закрыта: незнание не открывает дверь."""
        now = self.clock() if now is None else float(now)
        conn = self._conn()
        try:
            row = conn.execute("SELECT value FROM meta WHERE key='door_beat'").fetchone()
        finally:
            conn.close()
        try:
            age = now - float(row[0]) if row else None
        except (TypeError, ValueError):
            age = None
        return (age is not None and -fresh <= age <= fresh), age

    def get(self, token):
        conn = self._conn()
        try:
            return _row(conn.execute("SELECT %s FROM tg_out WHERE token=?" % _COLS, (str(token),)).fetchone())
        finally:
            conn.close()

    def cancel_queued(self, token, why):
        """queued → cancelled. True — отменено ЭТИМ вызовом (ПК ряда не видел и не увидит)."""
        return self._write(lambda conn: conn.execute(
            "UPDATE tg_out SET state=?, cancel_why=? WHERE token=? AND state=?",
            (CANCELLED, str(why)[:ERROR_MAX], str(token), QUEUED)).rowcount) == 1

    def give_up(self, token, now=None):
        """Дверь перестала ждать claimed-ряд: больше не выдаётся; исход ПК, если придёт, запишется."""
        now = self.clock() if now is None else float(now)
        return self._write(lambda conn: conn.execute(
            "UPDATE tg_out SET door_gave_up=? WHERE token=? AND state=? AND door_gave_up IS NULL",
            (now, str(token), CLAIMED)).rowcount) == 1

    # ── сторона входа (ПК) ─────────────────────────────────────────────────────────────────

    def claim(self, limit=CLAIM_LIMIT, now=None):
        """Выдача ПК: queued → claimed и повторная выдача claimed без подтверждения — только до срока и пока
        дверь ждёт. Одной транзакцией. → [ряды] (id, token, chat_id, text, created_at, expires_at, handed)."""
        now = self.clock() if now is None else float(now)

        def fn(conn):
            self._sweep(conn, now)
            rows = conn.execute("SELECT %s FROM tg_out WHERE ((state=? AND expires_at>?) OR (state=? AND "
                                "expires_at>? AND door_gave_up IS NULL)) ORDER BY id LIMIT ?" % _COLS,
                                (QUEUED, now, CLAIMED, now, int(limit))).fetchall()
            out = []
            for r in rows:
                rec = _row(r)
                if rec["state"] == QUEUED:
                    if conn.execute("UPDATE tg_out SET state=?, claimed_at=?, handed=handed+1 WHERE id=? AND "
                                    "state=?", (CLAIMED, now, rec["id"], QUEUED)).rowcount != 1:
                        continue
                else:
                    conn.execute("UPDATE tg_out SET handed=handed+1 WHERE id=?", (rec["id"],))
                rec["handed"] = int(rec["handed"] or 0) + 1
                out.append({k: rec[k] for k in ("id", "token", "chat_id", "text", "created_at", "expires_at",
                                                "handed")})
            return out
        return self._write(fn)

    def ack(self, row_id, token, outcome, msg_id=None, error=None, now=None):
        """Исход от ПК. → {"ok": bool, "state": …, "dup": bool, "error": слова отказа}. Идемпотентно."""
        now = self.clock() if now is None else float(now)
        if outcome not in ACK_OUTCOMES:
            return {"ok": False, "error": "bad_outcome"}
        if outcome == SENT and not (isinstance(msg_id, int) and not isinstance(msg_id, bool) and msg_id > 0):
            return {"ok": False, "error": "bad_msg_id"}
        err = None if error is None else str(error)[:ERROR_MAX]

        def fn(conn):
            rec = _row(conn.execute("SELECT %s FROM tg_out WHERE id=?" % _COLS, (int(row_id),)).fetchone())
            if rec is None:
                return {"ok": False, "error": "not_found"}
            if rec["token"] != str(token):
                return {"ok": False, "error": "token_mismatch"}
            if rec["state"] == CANCELLED:
                return {"ok": False, "error": "cancelled", "state": CANCELLED}
            if rec["state"] == QUEUED:
                return {"ok": False, "error": "not_claimed", "state": QUEUED}
            if rec["state"] in FINAL:
                same = rec["state"] == outcome and (outcome != SENT or rec["msg_id"] == msg_id)
                return {"ok": True, "state": rec["state"], "dup": True, "same": same, "msg_id": rec["msg_id"]}
            n = conn.execute("UPDATE tg_out SET state=?, acked_at=?, msg_id=?, error=? WHERE id=? AND state=?",
                             (outcome, now, msg_id if outcome == SENT else None, err, rec["id"], CLAIMED)).rowcount
            return {"ok": n == 1, "state": outcome if n == 1 else rec["state"], "dup": False,
                    "msg_id": msg_id if outcome == SENT else None}
        return self._write(fn)

    # ── сверка эха (ядро канала TG) ────────────────────────────────────────────────────────

    def sent_token(self, chat_id, msg_id):
        """Токен ряда, который ПК подтвердил как ушедший сообщением msg_id в чат chat_id, или None."""
        conn = self._conn()
        try:
            r = conn.execute("SELECT token FROM tg_out WHERE chat_id=? AND msg_id=? AND state=? ORDER BY id DESC "
                             "LIMIT 1", (int(chat_id), int(msg_id), SENT)).fetchone()
            return r[0] if r else None
        finally:
            conn.close()

    def maybe_sent(self, chat_id, ts, before=ECHO_BEFORE, after=ECHO_AFTER):
        """Ряды чата, которые МОГЛИ уйти, а id сообщения нам не известен (claimed без исхода, исход unknown),
        поставленные в окне вокруг времени эха ts. → [(token, text)], новые первыми."""
        conn = self._conn()
        try:
            return conn.execute("SELECT token, text FROM tg_out WHERE chat_id=? AND state IN (?,?) AND msg_id IS NULL "
                                "AND created_at>=? AND created_at<=? ORDER BY id DESC",
                                (int(chat_id), CLAIMED, UNKNOWN, float(ts) - after, float(ts) + before)).fetchall()
        finally:
            conn.close()

    def counts(self):
        conn = self._conn()
        try:
            return dict(conn.execute("SELECT state, COUNT(*) FROM tg_out GROUP BY state").fetchall())
        finally:
            conn.close()


if __name__ == "__main__":
    raise SystemExit("tg_outbox: очередь без рук (TGSEND1310) — дверь в wa_agent_svc.TgDoor, выдача и "
                     "подтверждение — wa_webhook /tg-queue/outbox и /tg-queue/ack")
