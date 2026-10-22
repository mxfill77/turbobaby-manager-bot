"""A1 (TB-NIGHT-2210-A1, PROPOSAL, default OFF): отмена АВТОброни реплаем «отмена» на сообщение
«✅ Бронь записана автоматически…». Чистая логика + контракт хранилища; руки — в splinter (тонкая обвязка).

Полномочие = сохранённая связь (chat_id, message_id успешного сообщения бота) → booking_id (UUID колонки Y) + тема +
роль автора (_intake_can_approve) + автор не бот/не пересылка. Текст, похожий на «успех», строка N, строка `by`,
реплай на чужое сообщение полномочий не дают. Ровно один мутирующий cancel_booking на запись; после НЕИЗВЕСТНО —
только чтение (readback), без повторной отмены. Импорт только stdlib; сети, окружения, файлов (кроме явно
переданного пути JsonFileStore) модуль не трогает.
"""
import json
import os
import re
import tempfile
import threading

CANCELLED, ALREADY, NOT_CANCELLED, UNKNOWN = "cancelled", "already", "not_cancelled", "unknown"
STATUS_FROM, STATUS_TO = "Бронь", "Отмена"
# Bridge refused BEFORE any write (doPost gates + cancelBooking pre-write checks). Anything else → UNKNOWN.
CANCEL_NOT_WRITTEN = frozenset({"bad_json", "unauthorized", "no_ticket", "unknown_action", "door_off", "missing_args",
                                "sheet_not_found", "booking_not_found", "ambiguous", "booking_changed", "not_auto",
                                "cancelled_elsewhere", "not_eligible", "lock_busy", "read_failed"})
CANCEL_WORDS = frozenset({"отмена", "отмени", "отменить", "отменяй", "отменяем", "cancel"})
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
ON_TAIL = "Отменить: ответьте «отмена» реплаем на это сообщение (владелец/менеджер)."
REGISTER_FAILED = ("⚠️ Связь сообщения с бронью не сохранена — «отмена» реплаем для строки {row} не сработает; "
                   "отмена — вручную в CRM.")


def cancel_on(raw):
    """Ручка INTAKE_AUTOBOOK_CANCEL: по умолчанию ВЫКЛ; splinter дополнительно требует _intake_autobook_on()."""
    return str(raw if raw is not None else "0").strip().lower() in ("1", "true", "yes", "on", "да")


def valid_booking_id(v):
    return isinstance(v, str) and bool(_UUID.match(v.strip()))


def is_cancel_text(text):
    """Только ясная команда целиком: «отмена», «Отмена!», «отменить.». «отмена не нужна», «отмена?» — нет."""
    s = str(text or "").lower().replace("ё", "е").strip().rstrip(".!").strip()
    return s in CANCEL_WORDS


# ── storage contract ──────────────────────────────────────────────────────────────────────────────────────────
class MemoryStore:
    """Контракт: get(key)→dict|None; put(key, rec); update(key, fn)→rec (fn(rec)→rec атомарно под замком).
    MemoryStore НЕ переживает рестарт."""

    def __init__(self):
        self._d, self._lk = {}, threading.Lock()

    def _load(self):
        return self._d

    def _save(self, d):
        self._d = d

    def get(self, key):
        with self._lk:
            r = (self._load() or {}).get(key)
            return dict(r) if r else None

    def put(self, key, rec):
        with self._lk:
            d = dict(self._load() or {})
            d[key] = dict(rec)
            self._save(d)

    def update(self, key, fn):
        with self._lk:
            d = dict(self._load() or {})
            new = fn(dict(d[key]) if key in d else None)
            if new is not None:
                d[key] = dict(new)
                self._save(d)
            return dict(new) if new is not None else None


class JsonFileStore(MemoryStore):
    """Предложение: один JSON-файл, запись через temp + os.replace (атомарная замена). Путь задаёт интегратор.
    Однопроцессный: межпроцессной блокировки нет. Хранит только id/строку/байк/состояние — без ФИО/контактов."""

    def __init__(self, path):
        super().__init__()
        self.path = path

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None                        # файла ещё нет — записей нет (первый старт); битый JSON — исключение

    def _save(self, d):
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.path)), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)


def _key(chat_id, message_id):
    return "%s:%s" % (chat_id, message_id)


def register_booked(store, *, chat_id, thread_id, message, res, bot_id=None, now=0.0):
    """После BOOKED автоброни: связать отправленное сообщение успеха с booking_id. False — не связано (нет id
    сообщения, UUID невалиден, сбой хранилища) → обвязка говорит «вручную в CRM»."""
    try:
        mid = getattr(message, "message_id", None)
        bid = res.get("booking_id") if isinstance(res, dict) else None
        if mid is None or not valid_booking_id(bid):
            return False
        store.put(_key(chat_id, mid), {
            "booking_id": bid.strip(), "row": res.get("row"), "bike": res.get("bike"), "chat_id": chat_id,
            "thread_id": thread_id, "message_id": mid, "bot_id": bot_id, "ts": now, "state": "booked",
            "events": [], "attempts": 0, "last": None})
        return True
    except Exception:
        return False


def lookup(store, msg):
    """Запись для реплая — только по (chat_id, message_id того сообщения, на которое реплай). Иначе None."""
    r = getattr(msg, "reply_to_message", None)
    if r is None or getattr(r, "message_id", None) is None:
        return None
    try:
        return store.get(_key(getattr(msg, "chat_id", None), r.message_id))
    except Exception:
        return None


# ── outcome ───────────────────────────────────────────────────────────────────────────────────────────────────
def _rb_ok(rb, bid):
    return isinstance(rb, dict) and rb.get("booking_id") == bid and rb.get("status") == STATUS_TO and rb.get("cancel_marked") is True


def cancel_outcome(res, sent, booking_id):
    """→ CANCELLED | ALREADY | NOT_CANCELLED | UNKNOWN. ok одно, rowcount, «запрос отправлен» — не отмена: нужен тот же
    UUID, Бронь→Отмена и readback моста с маркером отмены этого UUID."""
    if not sent:
        return NOT_CANCELLED
    if not isinstance(res, dict):
        return UNKNOWN
    rid = res.get("booking_id")
    if res.get("ok") is True and rid == booking_id:
        rb = res.get("readback")
        if (res.get("outcome") == "cancelled" and res.get("applied") is True and res.get("status_before") == STATUS_FROM
                and res.get("status_after") == STATUS_TO and _rb_ok(rb, booking_id)):
            return CANCELLED
        if res.get("outcome") == "already" and res.get("status_after") == STATUS_TO and _rb_ok(rb, booking_id):
            return ALREADY
        return UNKNOWN
    if res.get("ok") is False and res.get("outcome") != "unknown" and rid in (None, "", booking_id) \
            and str(res.get("error") or "") in CANCEL_NOT_WRITTEN:
        return NOT_CANCELLED
    return UNKNOWN


def readback(bridge, booking_id):
    """Только чтение. → ("verified"|"not_seen"|"unavailable"|"mismatch", snapshot). "not_seen" ≠ «не отменено»:
    запрос мог ещё исполниться — исход остаётся НЕИЗВЕСТНО."""
    fn = getattr(bridge, "booking_by_id", None)
    if fn is None:
        return "unavailable", None
    try:
        r = fn(booking_id)
    except Exception:
        return "unavailable", None
    if not isinstance(r, dict) or r.get("ok") is not True or r.get("booking_id") != booking_id:
        return "unavailable", None
    rb = r.get("readback")
    if r.get("found") is not True or not isinstance(rb, dict) or rb.get("booking_id") != booking_id:
        return "mismatch", rb
    if _rb_ok(rb, booking_id):
        return "verified", rb
    if rb.get("status") == STATUS_FROM and not rb.get("cancel_marked"):
        return "not_seen", rb
    return "mismatch", rb


# ── reply handler ─────────────────────────────────────────────────────────────────────────────────────────────
def _actor(msg):
    u = getattr(msg, "from_user", None)
    if u is None or getattr(u, "id", None) is None or getattr(u, "is_bot", False):
        return None
    return "tg:%s @%s" % (u.id, getattr(u, "username", None) or "-")


def _msg(out, rec, res, rb_state, err):
    row = (res.get("row") if isinstance(res, dict) and res.get("row") else None) or rec.get("row")
    bid = rec["booking_id"][:8]
    if out == CANCELLED:
        how = "подтверждено ответом моста и чтением строки" if rb_state is None else "подтверждено отдельным чтением строки"
        return f"✅ Автобронь отменена: строка {row}, «{STATUS_FROM}» → «{STATUS_TO}» (id {bid}…), {how}."
    if out == ALREADY:
        return f"ℹ️ Эта автобронь уже отменена ранее (строка {row}, id {bid}…) — повторно не отменяю."
    if out == NOT_CANCELLED:
        return f"⚠️ Автобронь НЕ отменена ({err}): мост отказал до записи. Строка {row} (id {bid}…)."
    return (f"❓ Исход отмены неизвестен ({err}; чтение: {rb_state or 'нет'}). Повторно не отправляю — проверьте строку "
            f"{row} (id {bid}…) в CRM. Повторный реплай «отмена» — только проверка, без второй отмены.")


async def handle_reply(msg, text, *, store, bridge, say, can_approve, chat_is_intake, agent_write,
                       bot_id=None, forwarded=None):
    """→ dict(handled, outcome, requested, received, applied, readback, calls). handled=False — реплай не на
    связанное сообщение или не «отмена»: прежний маршрут. Состояние «cancel_requested» пишется ДО отправки."""
    res_d = {"handled": False, "outcome": None, "requested": False, "received": False, "applied": None,
             "readback": None, "calls": 0}
    rec = lookup(store, msg)
    if rec is None or not is_cancel_text(text):
        return res_d
    chat_id = getattr(msg, "chat_id", None)
    r = msg.reply_to_message
    rfrom = getattr(r, "from_user", None)
    tid = getattr(msg, "message_thread_id", None)
    bad = (not chat_is_intake(chat_id) or rec.get("chat_id") != chat_id
           or (rec.get("thread_id") is not None and tid != rec.get("thread_id"))
           or (bot_id is not None and (rfrom is None or getattr(rfrom, "id", None) != bot_id))
           or (rec.get("bot_id") is not None and getattr(rfrom, "id", None) != rec.get("bot_id")))
    actor = _actor(msg)
    if bad or actor is None or not can_approve(msg) or (forwarded is not None and forwarded(msg)):
        res_d.update(handled=True, outcome="refused")            # silent like _intake_route_reply for non-approvers
        return res_d
    res_d["handled"] = True
    key, ev, bid = _key(chat_id, r.message_id), "%s:%s" % (chat_id, getattr(msg, "message_id", None)), rec["booking_id"]
    claim = {}

    def _claim(cur):                                              # atomic: dedupe event + state transition
        if cur is None or ev in cur.get("events", []):
            claim["mode"] = "duplicate"
            return None
        cur["events"] = cur.get("events", []) + [ev]
        st = cur.get("state")
        if st in ("booked", "not_cancelled"):
            claim["mode"] = "send"
            cur.update(state="cancel_requested", attempts=cur.get("attempts", 0) + 1, actor=actor)
        elif st == "cancelled":
            claim["mode"] = "done"
        else:                                                     # cancel_requested (crash/restart) or unknown
            claim["mode"] = "reconcile"
        return cur

    rec = store.update(key, _claim) or rec
    mode = claim.get("mode")
    if mode == "duplicate":
        res_d["outcome"] = "duplicate_event"
        return res_d
    if mode == "done":
        res_d["outcome"] = ALREADY
        await say(_msg(ALREADY, rec, None, None, ""))
        return res_d
    res, sent, err, rb_state = None, False, "", None
    if mode == "send":
        try:
            tk = bridge.issue_write_ticket()
            ticket = tk.get("ticket") if isinstance(tk, dict) else None
            if not ticket:
                err = "no_ticket"
            else:
                with agent_write(ticket):
                    sent = True
                    res_d["calls"] += 1
                    res = bridge.cancel_booking(bid, by=actor, row_hint=rec.get("row"),
                                                expect={"bike": rec.get("bike")} if rec.get("bike") else None)
        except Exception as e:
            err = type(e).__name__
        out = cancel_outcome(res, sent, bid)
        if isinstance(res, dict):
            err = err or str(res.get("error") or "")
            res_d["applied"] = res.get("applied")
    else:
        out, err = UNKNOWN, "reconcile"
    res_d["requested"], res_d["received"] = sent or mode == "reconcile", isinstance(res, dict)
    if out == UNKNOWN:
        rb_state, _snap = readback(bridge, bid)
        res_d["readback"] = rb_state
        if rb_state == "verified":
            out = CANCELLED
    elif out in (CANCELLED, ALREADY):
        res_d["readback"] = "bridge_reread"
    new_state = {CANCELLED: "cancelled", ALREADY: "cancelled", NOT_CANCELLED: "not_cancelled"}.get(out, "unknown")
    last = {"outcome": out, "error": err or None, "requested": res_d["requested"], "received": res_d["received"],
            "applied": res_d["applied"], "readback": res_d["readback"],
            "status_before": res.get("status_before") if isinstance(res, dict) else None,
            "status_after": res.get("status_after") if isinstance(res, dict) else None,
            "row": res.get("row") if isinstance(res, dict) else None}

    def _fin(cur):
        if cur is None:
            return None
        cur.update(state=new_state, last=last)
        return cur

    try:
        store.update(key, _fin)
    except Exception:
        pass                                                      # stays "cancel_requested" → next reply reconciles only
    res_d["outcome"] = out
    await say(_msg(out, rec, res, None if out != UNKNOWN and res_d["readback"] != "verified" else rb_state,
                   err or "нет ответа"))
    return res_d
