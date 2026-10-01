#!/usr/bin/env python3
"""ЯДРО СЛУЖБЫ wa-agent — черновик ответа клиенту WhatsApp, согласование в группе, одно нажатие —
одно сообщение (WAAGENTCORE0110, шаг 2 плана WAAGENTLIVE0110 §7).

ЧТО ЭТО. Решение «когда писать черновик, когда его снять, кто нажал первым и ушло ли сообщение»
живёт ЗДЕСЬ и только здесь. Рук у ядра нет: модель, Telegram и дверь отправки приходят снаружи
интерфейсами (`Model`, `Telegram`, `Door` ниже), и ядро не импортирует ни сети, ни `wa_send`,
ни клиента модели. Службы и юнита ещё нет — это шаги 3–4 плана; запуск файла отказывает словами.

ЧТО ЧИТАЕТСЯ И ЧТО ПИШЕТСЯ.
  очередь `wa_queue.db` (`wa_inbox`)  — ТОЛЬКО `mode=ro`; вид строки решает `wa_kind.kind_of`.
  своя база `wa_agent.db`             — курсор, клиенты (пауза), черновики. Чужих баз не пишем.

ТАКТ (`Core.tick`):
  1. СКАН. Строки очереди `id > курсор`. Живое входящее (inbound, history=0) двигает «последнее
     сообщение клиента» и делает его ждущий черновик `stale`. Живое эхо (echo=1, history=0,
     msg_type не status, wamid не наш) — ответ человека с телефона: ждущий черновик `superseded`,
     клиент на ПАУЗЕ, в группу ОДИН вопрос «когда продолжать» на одну паузу (правило владельца
     30.09.2026-7 п.4). Пауза снимается только нажатием «Продолжить» (`Core.resume`).
     На первом старте курсор встаёт на MAX(id): переписка до службы черновиков не даёт.
  2. ЧЕРНОВИК. Клиент не на паузе, ждущих сообщений больше, чем закрыто прежним решением, живого
     черновика нет, со времени последнего сообщения прошло `quiet` (60–90 с — клиенты пишут
     очередями). Перед записью — перепроверка очереди: пришло новое за время модели — не пишем.
     Живой черновик у клиента один: проверка кодом И частичный уникальный индекс базы.

НАЖАТИЕ (`Core.press`). Захват — условный UPDATE `state='pending' AND ver=?`, решает rowcount;
проигравший получает «уже решено: кто, когда, исход». Победитель перепроверяет очередь (эхо →
superseded и пауза; новое входящее → stale), пишет `sending` и ТОЛЬКО ПОТОМ зовёт дверь, затем
исход: sent (с wamid) · not_sent · unsure. Повтора нет нигде: `unknown` двери = `unsure`, а на
старте службы `sending` → `unsure` (сообщение могло уйти) — тот же замок, что `_init_state`
службы показа. `claimed` на старте → `pending`: дверь ещё не звали, отправки не было.

ЧЕГО ЯДРО НЕ ДЕЛАЕТ. Не шлёт без нажатия; не повторяет отправку; не судит окно 24 часа (это
дверь, `wa_send.window_state`); не держит текстов клиентов в журнале — только id, состояния, числа.
"""

import json
import sqlite3
import time

import wa_kind

# ── состояния черновика ─────────────────────────────────────────────────────────────────
PENDING, CLAIMED, SENDING = "pending", "claimed", "sending"
SENT, NOT_SENT, UNSURE = "sent", "not_sent", "unsure"
SUPERSEDED, STALE, DECLINED = "superseded", "stale", "declined"
STATES = (PENDING, CLAIMED, SENDING, SENT, NOT_SENT, UNSURE, SUPERSEDED, STALE, DECLINED)
LIVE = (PENDING, CLAIMED, SENDING)            # «живой» черновик: у клиента не больше одного

# ── действия кнопок ─────────────────────────────────────────────────────────────────────
ACT_SEND, ACT_DECLINE = "send", "decline"

# ── пауза между последним сообщением клиента и черновиком ───────────────────────────────
QUIET_MIN, QUIET_MAX, QUIET_DEFAULT = 60, 90, 75
SCAN_LIMIT = 500                              # строк очереди за один скан
MODEL_RETRY_SEC = 300                         # модель не дала текста — следующая попытка не раньше

# исход двери → состояние черновика; всё незнакомое — unsure (могло уйти, не повторяем)
_DOOR_STATE = {"sent": SENT, "not_sent": NOT_SENT, "unknown": UNSURE}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS clients (
    number      TEXT PRIMARY KEY,
    last_in_id  INTEGER NOT NULL DEFAULT 0,   -- последнее живое входящее (id строки очереди)
    last_in_ts  REAL    NOT NULL DEFAULT 0,   -- его ts_queued (часы сервера)
    done_upto   INTEGER NOT NULL DEFAULT 0,   -- входящие до этого id закрыты решением/человеком
    paused      INTEGER NOT NULL DEFAULT 0,
    pause_no    INTEGER NOT NULL DEFAULT 0,   -- номер паузы: «Продолжить» снимает ровно свою
    paused_at   REAL,
    pause_row   INTEGER,                      -- id строки эха, поставившей паузу
    resumed_by  TEXT,
    resumed_at  REAL,
    next_try    REAL    NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      TEXT    NOT NULL,
    state       TEXT    NOT NULL,
    ver         INTEGER NOT NULL DEFAULT 1,
    text        TEXT    NOT NULL,
    upto_id     INTEGER NOT NULL,             -- последнее входящее, на которое отвечает черновик
    created_at  REAL    NOT NULL,
    decided_by  TEXT,
    decided_at  REAL,
    reason      TEXT,
    wamid       TEXT,
    card_id     INTEGER,
    closed_at   REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_live_draft ON drafts(number)
    WHERE state IN ('pending', 'claimed', 'sending');
CREATE INDEX IF NOT EXISTS drafts_wamid ON drafts(wamid);
"""

# «Нужен человек» (WAAGENTMODEL0210): причины кода и модели — JSON-список слов в drafts.handoff.
# Черновик с причинами «Отправить» не шлёт, пока человек не нажал «Исправить» (версия > 1).
HANDOFF_LOCK_WORDS = "нужен человек — сначала «Исправить»: «Отправить» откроется на исправленной версии"


def handoff_of(raw):
    """drafts.handoff → [слова]; NULL — [] (причин нет). Битая запись — None («не прочитано», не «причин
    нет»): замок `send_locked` и карточка считают такой черновик черновиком с причинами."""
    try:
        val = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return None
    if isinstance(val, list):
        return [str(x) for x in val if str(x).strip()]
    return None


UNREAD_REASON = "причины не прочитаны — решает человек"


def draft_out(out):
    """Ответ Model.draft → (текст | None, [причины]). Строка — прежний контракт без причин."""
    if isinstance(out, dict):
        hand = out.get("handoff") or []
        hand = [str(h).strip() for h in hand if str(h).strip()] if isinstance(hand, list) else []
        return out.get("text"), hand
    return out, []


# ═══ интерфейсы рук (подделки — в тестах; настоящие — шаги 3–4 плана) ═══════════════════

class Model:
    """draft(number, upto_id) → текст черновика или None (модель не дала текста), либо словарь
    {text, handoff[слова причин «нужен человек»], …} (адаптер модели, WAAGENTMODEL0210)."""

    def draft(self, number, upto_id):
        raise NotImplementedError


class Telegram:
    """Группа согласования. Ничего не возвращает, кроме card → id сообщения карточки (или None)."""

    def card(self, draft_id, ver, number, text):
        raise NotImplementedError

    def card_done(self, draft_id, card_id, words):
        raise NotImplementedError

    def ask_pause(self, number, pause_no):
        raise NotImplementedError


class Door:
    """send_text(to, text) → {"outcome": sent|not_sent|unknown, "reason": str, "wamid": str|None}.
    Контракт совпадает с `wa_send.send_text` (тот НИКОГДА не бросает и сам судит окно 24 ч)."""

    def send_text(self, to, text):
        raise NotImplementedError


# ═══ ядро ════════════════════════════════════════════════════════════════════════════════

def _hm(ts):
    return time.strftime("%H:%M", time.gmtime(float(ts))) + " UTC" if ts else "—"


class Core:
    def __init__(self, db_path, queue_path, model, tg, door, quiet=QUIET_DEFAULT,
                 clock=time.time, log=None, drafts=True):
        quiet = int(quiet)
        if not QUIET_MIN <= quiet <= QUIET_MAX:
            raise ValueError("пауза черновика %d с вне %d–%d с" % (quiet, QUIET_MIN, QUIET_MAX))
        self.quiet = quiet
        # WA_AGENT_DRAFTS (WAAGENTSVC0210): выключен — модель не зовётся, черновиков и пауз нет,
        # курсор идёт за очередью (`follow`). Решает служба; ядро по умолчанию прежнее.
        self.drafts = bool(drafts)
        self.queue_path = queue_path
        self.model, self.tg, self.door = model, tg, door
        self.clock = clock
        self.log = log or (lambda line: None)
        self.db = sqlite3.connect(db_path, timeout=10, isolation_level=None)
        self.db.executescript(_SCHEMA)
        if "handoff" not in {r[1] for r in self.db.execute("PRAGMA table_info(drafts)")}:
            self.db.execute("ALTER TABLE drafts ADD COLUMN handoff TEXT")
        self._startup()

    # ── база ──────────────────────────────────────────────────────────────────────────────

    def _startup(self):
        """sending → unsure (могло уйти — не повторяем); claimed → pending (двери не звали).
        Входящие под unsure закрыты: новый черновик на них звал бы ко второй отправке."""
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, (SELECT MAX(upto_id) FROM drafts "
                        "WHERE drafts.number=clients.number AND state=?)) WHERE number IN "
                        "(SELECT number FROM drafts WHERE state=?)", (SENDING, SENDING))
        n1 = self.db.execute("UPDATE drafts SET state=?, reason=? WHERE state=?",
                             (UNSURE, "рестарт посреди отправки — могло уйти, не повторяем",
                              SENDING)).rowcount
        n2 = self.db.execute("UPDATE drafts SET state=?, decided_by=NULL, decided_at=NULL "
                             "WHERE state=?", (PENDING, CLAIMED)).rowcount
        if n1 or n2:
            self.log("старт: sending→unsure %d, claimed→pending %d" % (n1, n2))

    def _queue(self):
        return sqlite3.connect("file:%s?mode=ro" % self.queue_path, uri=True, timeout=5)

    def _cursor(self):
        row = self.db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
        return int(row[0]) if row else None

    def _set_cursor(self, value):
        self.db.execute("INSERT INTO meta(key, value) VALUES('cursor', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(value)),))

    def _client(self, number):
        self.db.execute("INSERT OR IGNORE INTO clients(number) VALUES(?)", (number,))
        return self.db.execute("SELECT last_in_id, last_in_ts, done_upto, paused, pause_no, next_try "
                               "FROM clients WHERE number=?", (number,)).fetchone()

    def _live_draft(self, number):
        return self.db.execute("SELECT id, state FROM drafts WHERE number=? AND state IN (?,?,?)",
                               (number,) + LIVE).fetchone()

    def _our_wamid(self, wamid):
        return bool(wamid) and self.db.execute(
            "SELECT 1 FROM drafts WHERE wamid=?", (wamid,)).fetchone() is not None

    def _close(self, draft_id, state, words, now, from_states=(PENDING,)):
        """Снять черновик условно: только из названных состояний. True — снят этим вызовом."""
        q = "UPDATE drafts SET state=?, reason=?, closed_at=? WHERE id=? AND state IN (%s)" % \
            ",".join("?" * len(from_states))
        n = self.db.execute(q, (state, words, now, draft_id) + tuple(from_states)).rowcount
        if n == 1:
            card = self.db.execute("SELECT card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
            self.log("черновик %d → %s" % (draft_id, state))
            self._tg("card_done", draft_id, card[0] if card else None, words)
        return n == 1

    def _tg(self, method, *args):
        try:
            return getattr(self.tg, method)(*args)
        except Exception as e:                                       # noqa: BLE001
            self.log("telegram %s упал: %s" % (method, type(e).__name__))
            return None

    # ── вид строки очереди ────────────────────────────────────────────────────────────────

    @staticmethod
    def _live_kind(msg_type, echo, history):
        """inbound | echo | None. Живое — только history=0; квитанции и прочее — None."""
        kind = wa_kind.kind_of(msg_type, echo, history)
        if wa_kind._flag(history) is not False:
            return None
        if kind in (wa_kind.KIND_INBOUND, wa_kind.KIND_ECHO):
            return kind
        return None

    # ── пауза ─────────────────────────────────────────────────────────────────────────────

    def _pause(self, number, row_id, now):
        """Человек ответил с телефона: клиент на паузе. Вопрос в группу — один на паузу."""
        n = self.db.execute("UPDATE clients SET paused=1, pause_no=pause_no+1, paused_at=?, "
                            "pause_row=? WHERE number=? AND paused=0", (now, row_id, number)).rowcount
        if n == 1:
            no = self.db.execute("SELECT pause_no FROM clients WHERE number=?", (number,)).fetchone()[0]
            self.log("клиент на паузе (строка эха %d, пауза %d)" % (row_id, no))
            self._tg("ask_pause", number, no)

    def resume(self, number, pause_no, who, now=None):
        """«Продолжить». Снимает ровно свою паузу; второй нажавший получает «уже продолжено»."""
        now = self.clock() if now is None else now
        n = self.db.execute("UPDATE clients SET paused=0, resumed_by=?, resumed_at=? "
                            "WHERE number=? AND paused=1 AND pause_no=?",
                            (who, now, number, int(pause_no))).rowcount
        if n == 1:
            self.log("пауза %s снята нажатием" % pause_no)
            return {"ok": True, "words": "продолжаем"}
        row = self.db.execute("SELECT resumed_by, resumed_at FROM clients WHERE number=?",
                              (number,)).fetchone()
        by, at = (row or (None, None))
        return {"ok": False, "words": "уже продолжено: %s, %s" % (by or "—", _hm(at))}

    # ── такт ──────────────────────────────────────────────────────────────────────────────

    def tick(self, now=None):
        now = self.clock() if now is None else now
        if not self.drafts:
            self.follow()
            return []
        self.scan(now)
        return self.make_drafts(now)

    def follow(self):
        """Черновики выключены: курсор встаёт на MAX(id) без разбора строк, ждущие входящие закрыты
        без черновика. Включение не поднимет черновиков на переписку выключенного времени — то же
        правило, что у первого старта. Живой черновик не трогается: его «Отправить» перепроверит
        очередь (`press` → `_fresh`)."""
        with self._queue() as q:
            top = q.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
        if self._cursor() != top:
            self._set_cursor(top)
        self.db.execute("UPDATE clients SET done_upto=last_in_id WHERE done_upto < last_in_id")
        return top

    def scan(self, now):
        """Новые строки очереди после курсора. Первый старт — курсор на MAX(id), без разбора."""
        cur = self._cursor()
        with self._queue() as q:
            if cur is None:
                top = q.execute("SELECT COALESCE(MAX(id), 0) FROM wa_inbox").fetchone()[0]
                self._set_cursor(top)
                self.log("курсор встал на %d (первый старт)" % top)
                return 0
            rows = q.execute("SELECT id, from_number, msg_type, echo, history, wamid, ts_queued "
                             "FROM wa_inbox WHERE id > ? ORDER BY id LIMIT ?",
                             (cur, SCAN_LIMIT)).fetchall()
        for rid, number, msg_type, echo, history, wamid, ts_q in rows:
            kind = self._live_kind(msg_type, echo, history)
            if kind and number:
                if kind == wa_kind.KIND_INBOUND:
                    self._on_inbound(number, rid, ts_q, now)
                elif not self._our_wamid(wamid):
                    self._on_echo(number, rid, now)
            cur = rid
        self._set_cursor(cur)
        return len(rows)

    def _on_inbound(self, number, rid, ts_q, now):
        self._client(number)
        self.db.execute("UPDATE clients SET last_in_id=MAX(last_in_id, ?), last_in_ts=MAX(last_in_ts, ?) "
                        "WHERE number=?", (rid, float(ts_q or now), number))
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], STALE, "снят: клиент написал ещё (строка %d)" % rid, now)

    def _on_echo(self, number, rid, now):
        self._client(number)
        # человек ответил на всё, что было до его эха: эти входящие закрыты
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?", (number,))
        live = self._live_draft(number)
        if live and live[1] == PENDING:
            self._close(live[0], SUPERSEDED, "снят: ответили с телефона %s" % _hm(now), now)
        self._pause(number, rid, now)

    def make_drafts(self, now):
        made = []
        due = self.db.execute("SELECT number, last_in_id FROM clients WHERE paused=0 "
                              "AND last_in_id > done_upto AND last_in_ts <= ? AND next_try <= ?",
                              (now - self.quiet, now)).fetchall()
        for number, upto in due:
            if self._live_draft(number):
                continue
            try:
                text, hand = draft_out(self.model.draft(number, upto))
            except Exception as e:                                   # noqa: BLE001
                self.log("модель упала: %s" % type(e).__name__)
                text, hand = None, []
            if not isinstance(text, str) or not text.strip():
                self.db.execute("UPDATE clients SET next_try=? WHERE number=?",
                                (now + MODEL_RETRY_SEC, number))
                continue
            # пока думала модель, клиент мог написать ещё или человек ответить — не пишем
            if self._fresh(number, upto):
                continue
            cur = self.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, handoff) "
                                  "VALUES(?,?,1,?,?,?,?)", (number, PENDING, text, upto, now,
                                                            json.dumps(hand, ensure_ascii=False) if hand else None))
            did = cur.lastrowid
            self.log("черновик %d (до строки %d, %d симв.%s)" % (
                did, upto, len(text), ", нужен человек: причин %d" % len(hand) if hand else ""))
            card = self._tg("card", did, 1, number, text)
            if card is not None:
                self.db.execute("UPDATE drafts SET card_id=? WHERE id=?", (card, did))
            made.append(did)
        return made

    def _fresh(self, number, after_id):
        """Что пришло в очередь по клиенту после after_id: (kind, id) первой живой строки или None."""
        with self._queue() as q:
            rows = q.execute("SELECT id, msg_type, echo, history, wamid FROM wa_inbox "
                             "WHERE from_number=? AND id > ? ORDER BY id", (number, after_id)).fetchall()
        for rid, msg_type, echo, history, wamid in rows:
            kind = self._live_kind(msg_type, echo, history)
            if kind == wa_kind.KIND_INBOUND:
                return kind, rid
            if kind == wa_kind.KIND_ECHO and not self._our_wamid(wamid):
                return kind, rid
        return None

    # ── нажатие ───────────────────────────────────────────────────────────────────────────

    def _decided(self, draft_id, ver=None):
        """Слова проигравшему. ver — версия нажатой кнопки: прежняя версия отвечает «устарело»."""
        row = self.db.execute("SELECT state, decided_by, decided_at, closed_at, ver FROM drafts "
                              "WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return "черновика нет"
        state, by, at, closed, ver_now = row
        if ver is not None and int(ver) != ver_now:
            return "устарело: версия %d, действует версия %d — %s" % (
                int(ver), ver_now, "жмите кнопки новой карточки" if state == PENDING
                else self._decided(draft_id))
        ver = ver_now
        if by:
            return "уже решено: %s, %s — %s" % (by, _hm(at), state)
        return "уже решено: снят, %s — %s (версия %d)" % (_hm(closed), state, ver)

    def press(self, draft_id, ver, action, who, now=None):
        """Нажатие кнопки карточки. → {"ok": bool, "state": …, "words": …}."""
        now = self.clock() if now is None else now
        target = CLAIMED if action == ACT_SEND else DECLINED
        if action not in (ACT_SEND, ACT_DECLINE):
            return {"ok": False, "state": None, "words": "неизвестное действие"}
        if action == ACT_SEND and self.send_locked(draft_id, ver):
            # «нужен человек»: ДО захвата и до двери — черновик ждёт правки, кнопки живы
            self.log("черновик %d: «Отправить» заперто — нужен человек, ждём «Исправить»" % draft_id)
            return {"ok": False, "state": PENDING, "words": HANDOFF_LOCK_WORDS}
        if action == ACT_SEND and not self._door_open():
            # дверь выключена (WA_SEND): ДО захвата — черновик остаётся pending, кнопки живы
            row = self.db.execute("SELECT state, ver FROM drafts WHERE id=?", (draft_id,)).fetchone()
            if row and row[0] == PENDING and row[1] == int(ver):
                self.log("черновик %d: «Отправить» — отправка выключена, черновик ждёт" % draft_id)
                return {"ok": False, "state": PENDING,
                        "words": "отправка выключена — черновик ждёт, кнопки живы"}
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        n = self.db.execute("UPDATE drafts SET state=?, decided_by=?, decided_at=? "
                            "WHERE id=? AND state='pending' AND ver=?",
                            (target, who, now, draft_id, int(ver))).rowcount
        if n != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id, ver)}
        number, upto, text = self.db.execute("SELECT number, upto_id, text FROM drafts WHERE id=?",
                                             (draft_id,)).fetchone()
        if action == ACT_DECLINE:
            self.db.execute("UPDATE drafts SET closed_at=? WHERE id=?", (now, draft_id))
            self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, ?) WHERE number=?", (upto, number))
            self._tg("card_done", draft_id, self._card(draft_id), "не нужно: %s, %s" % (who, _hm(now)))
            return {"ok": True, "state": DECLINED, "words": "не отправляем"}

        # ── победитель: перепроверка очереди ДО двери ──
        fresh = self._fresh(number, upto)
        paused = self.db.execute("SELECT paused FROM clients WHERE number=?", (number,)).fetchone()
        if fresh or (paused and paused[0]):
            kind, rid = fresh or (wa_kind.KIND_ECHO, None)
            state = SUPERSEDED if kind == wa_kind.KIND_ECHO else STALE
            self._close(draft_id, state, "снят при нажатии: %s после черновика" %
                        ("ответ с телефона" if state == SUPERSEDED else "новое сообщение клиента"),
                        now, from_states=(CLAIMED,))
            if state == SUPERSEDED and rid is not None:
                self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, last_in_id) WHERE number=?",
                                (number,))
                self._pause(number, rid, now)
            return {"ok": False, "state": state, "words": "не отправлено: " + (
                "ответили с телефона" if state == SUPERSEDED else "клиент написал ещё")}

        # ── sending ДО двери: рестарт после этой строки повтора не даст ──
        if self.db.execute("UPDATE drafts SET state=? WHERE id=? AND state=?",
                           (SENDING, draft_id, CLAIMED)).rowcount != 1:
            return {"ok": False, "state": None, "words": self._decided(draft_id)}
        try:
            res = self.door.send_text(number, text) or {}
        except Exception as e:                                       # noqa: BLE001
            res = {"outcome": "unknown", "reason": "дверь упала: %s" % type(e).__name__}
        state = _DOOR_STATE.get(res.get("outcome"), UNSURE)
        wamid = res.get("wamid") if state == SENT else None
        self.db.execute("UPDATE drafts SET state=?, reason=?, wamid=?, closed_at=? WHERE id=? AND state=?",
                        (state, str(res.get("reason") or "")[:300], wamid, now, draft_id, SENDING))
        self.db.execute("UPDATE clients SET done_upto=MAX(done_upto, ?) WHERE number=?", (upto, number))
        self.log("черновик %d: дверь → %s" % (draft_id, state))
        self._tg("card_done", draft_id, self._card(draft_id), "%s: %s, %s" % (state, who, _hm(now)))
        return {"ok": state == SENT, "state": state, "words": state}

    def revise(self, draft_id, text, who, now=None, ver=None):
        """«Исправить»: текст человека, версия +1; кнопки прежней версии отвечают «устарело».
        ver — версия карточки, на которую ответили реплаем: правка прежней версии не принимается
        (тот же замок, что у нажатия). Принята — прежняя карточка «устарело», новая карточка с
        версией +1; «Отправить» на ней шлёт текст человека дословно."""
        now = self.clock() if now is None else now
        if not (text or "").strip():
            return False
        q, args = "UPDATE drafts SET text=?, ver=ver+1 WHERE id=? AND state='pending'", (text, draft_id)
        if ver is not None:
            q, args = q + " AND ver=?", args + (int(ver),)
        n = self.db.execute(q, args).rowcount
        if n == 1:
            number, ver_now, old_card = self.db.execute(
                "SELECT number, ver, card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
            self.log("черновик %d исправлен → версия %d (%s)" % (draft_id, ver_now, who))
            self._tg("card_done", draft_id, old_card,
                     "устарело: исправлено — %s, %s, действует версия %d" % (who, _hm(now), ver_now))
            card = self._tg("card", draft_id, ver_now, number, text)
            self.db.execute("UPDATE drafts SET card_id=? WHERE id=?", (card, draft_id))
        return n == 1

    def _card(self, draft_id):
        row = self.db.execute("SELECT card_id FROM drafts WHERE id=?", (draft_id,)).fetchone()
        return row[0] if row else None

    def handoff(self, draft_id):
        row = self.db.execute("SELECT handoff FROM drafts WHERE id=?", (draft_id,)).fetchone()
        hand = handoff_of(row[0]) if row else []
        return [UNREAD_REASON] if hand is None else hand

    def send_locked(self, draft_id, ver):
        """«Отправить» заперто: черновик ждёт с этой версией, у него есть причины «нужен человек»,
        и человек его ещё не исправлял (версия 1 — текст модели; «Исправить» даёт версию +1)."""
        row = self.db.execute("SELECT state, ver, handoff FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row or row[0] != PENDING or row[1] != int(ver):
            return False
        hand = handoff_of(row[2])
        return (hand is None or bool(hand)) and row[1] == 1

    def _door_open(self):
        """Дверь без `is_open` — открыта (прежний контракт); `is_open` упал — закрыта."""
        probe = getattr(self.door, "is_open", None)
        if probe is None:
            return True
        try:
            return bool(probe())
        except Exception as e:                                       # noqa: BLE001
            self.log("дверь: is_open упал: %s — считаем выключенной" % type(e).__name__)
            return False

    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM drafts GROUP BY state").fetchall())


if __name__ == "__main__":
    raise SystemExit("wa_agent: ядро без рук (WAAGENTCORE0110) — служба собирается в wa_agent_svc.py "
                     "(WAAGENTSVC0210), Telegram в wa_agent_tg.py (WAAGENTTG0110)")
