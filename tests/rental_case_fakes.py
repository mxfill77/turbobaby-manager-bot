# -*- coding: utf-8 -*-
"""Подделки портов дела аренды К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910) — только для тестов.

Источник истины — out/CONTRACT_K4.md: §9.1 (порты и форма ответов), §13 (шов S1–S7 к staff_ask), §14 (демо-случай),
§8.4 (основания версии: поле версии у подделок версией источника НЕ является и в дело не переносится).

Что здесь есть (по одной подделке на порт §9.1, у каждой журнал вызовов `calls`):
  * сеть запрещена ПРИ ИМПОРТЕ: `socket.socket` подменён бросающим классом (`NetworkBlocked`), `getaddrinfo` и
    `create_connection` — тоже; попытки считаются (`net_attempts()`). Локальная пара `socket.socketpair` (её делает
    цикл asyncio для самопайпа) создаётся настоящим классом — это не сеть;
  * `FakeClock`, `SeqIds` — инжектируемые часы и источник id (CONTRACT §1.1);
  * `Counters` — счётчики постов staff_ask, эскалаций, карточек, вызовов NoticePort, отправок клиенту кодом (обязаны
    остаться 0), «нажатий человека» в подделке WA, вызовов двери и красных шагов моста, попыток сети;
  * фабрика синтетических строк в ЖИВОМ формате кандидата f2f7295:
      - `make_row` — строка двери `clients` (f2f7295:bridge_prod/ReadClients.js:95-121: без `price`, пустые суммы = 0,
        даты 'yyyy-MM-dd HH:mm' | None, booking_id '' при пустой Y);
      - `make_cash` + `FakeBridge.tx_find` — касса (f2f7295:bridge_build_tx_find/BotData.js:1650-1681; void не отдаётся);
      - `make_contract` + `FakeBridge.contract_find` — реестр e-Sign (f2f7295:bridge_build_contract/ContractDoor.js:
        275-340); `FakeBridge.contract_pdf` — как `bridge_client.contract_pdf` (bridge_client.py:1133-1157, `verified`
        ставит клиент по длине и sha256);
      - `FakeBridge.state_get` — лист «состояние_байка» (f2f7295:bridge_prod/BotData.js:92-93, 1229-1250);
      - `FakeBridge.closing_get` — лист закрытия только по booking_id (f2f7295:bridge_prod/BotData.js:83-84, Closing.js:
        88-98; фоллбэк по байку К4 не принимает);
  * порты §9.1: `FakeRentalSource`, `FakeStaffAskPort`, `FakeEscalationPort`, `FakeApprovalPort`, `FakeCashPort`,
    `FakeContractPort`, `FakePdfPort`, `FakeClosingPort`, `FakeStatePort`, `FakeBikeEventsPort`, `FakeCrmReadback`,
    `FakeResultSink`, `FakeNoticePort`, `FakeDeliveryStatusPort`;
  * `FakeStaffAsk` — staff_ask по шву S1–S7 (CONTRACT §13): запись ДО отправки, `unknown_places`, отказ только до первой
    отправки, дедуп с expect_id (S2), `managed_by="rental_case"` и пропуск в `due()/tick()` (S3), `escalate` (S4),
    `close` (S6), без пометки решателю (S7); `FakeReplyHandler` — порядок S5 (сначала дело, потом мозг);
  * `run_coro` — исполняет корутину подделки без цикла событий (подделки не засыпают).

Таймаут или исключение подделки внешнего клиента → `{"unknown": …}`, никогда `refused` и без повтора (I43).
Ничего не пишет на диск и не удаляет; сети нет.
"""
import base64
import datetime
import hashlib
import itertools
import json
import os
import re
import socket
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# =====================================================================================================================
# Сеть запрещена при импорте (CONTRACT §9.1 «тесты подменяют socket.socket на бросающий», §14, К4-C18)
# =====================================================================================================================


class NetworkBlocked(RuntimeError):
    """Попытка сети в тестах К4."""


_NET = getattr(socket, "_k4_net", None)
if _NET is None:
    _NET = {"attempts": 0, "log": []}
_REAL_SOCKET = getattr(socket, "_k4_real_socket", socket.socket)
_REAL_SOCKETPAIR = getattr(socket, "_k4_real_socketpair", socket.socketpair)
_REAL_GETADDRINFO = getattr(socket, "_k4_real_getaddrinfo", socket.getaddrinfo)
_REAL_CREATE_CONNECTION = getattr(socket, "_k4_real_create_connection", socket.create_connection)
_SWAP_LOCK = threading.RLock()


def _net_hit(what):
    _NET["attempts"] += 1
    _NET["log"].append(str(what)[:160])
    return NetworkBlocked("сеть в тестах К4 запрещена (tests/rental_case_fakes.py): %s" % (what,))


class _BlockedSocket(_REAL_SOCKET):
    """socket.socket тестов К4: любое создание сокета — попытка сети, исключение."""

    def __init__(self, *args, **kwargs):  # noqa: D401 — бросает до создания дескриптора
        raise _net_hit("socket.socket%r" % (args,))


def _blocked_getaddrinfo(*args, **kwargs):
    raise _net_hit("getaddrinfo%r" % (args[:2],))


def _blocked_create_connection(*args, **kwargs):
    raise _net_hit("create_connection%r" % (args[:1],))


def _local_socketpair(*args, **kwargs):
    """Локальная пара сокетов (самопайп цикла asyncio) — не сеть: на время вызова — настоящий класс."""
    with _SWAP_LOCK:
        socket.socket = _REAL_SOCKET
        try:
            return _REAL_SOCKETPAIR(*args, **kwargs)
        finally:
            socket.socket = _BlockedSocket


if not getattr(socket, "_k4_guard", False):
    socket._k4_net = _NET
    socket._k4_real_socket = _REAL_SOCKET
    socket._k4_real_socketpair = _REAL_SOCKETPAIR
    socket._k4_real_getaddrinfo = _REAL_GETADDRINFO
    socket._k4_real_create_connection = _REAL_CREATE_CONNECTION
    socket._k4_guard = True
socket.socket = _BlockedSocket
socket.socketpair = _local_socketpair
socket.getaddrinfo = _blocked_getaddrinfo
socket.create_connection = _blocked_create_connection


def net_attempts():
    """Число попыток сети с импорта подделок (обязано быть 0)."""
    return int(_NET["attempts"])


def net_log():
    return list(_NET["log"])


# только после подмены сокета: модули кандидата (без сети при импорте), их разбор — живой формат
import wa_agent_tools as WT  # noqa: E402
import wa_book_read as WB  # noqa: E402

# =====================================================================================================================
# Часы, id, счётчики
# =====================================================================================================================

TZ_H = 7
UNKNOWN = "UNKNOWN"


def epoch(y, mo, d, h=0, mi=0, s=0):
    """Местное время Пхукета (+7) → секунды эпохи (как день CONTRACT §1.1)."""
    dt = datetime.datetime(y, mo, d, h, mi, s, tzinfo=datetime.timezone.utc) - datetime.timedelta(hours=TZ_H)
    return dt.timestamp()


def local_dt(t):
    return (datetime.datetime.fromtimestamp(t, datetime.timezone.utc) + datetime.timedelta(hours=TZ_H)).replace(
        tzinfo=None)


def local_str(t):
    """Секунды эпохи → 'yyyy-MM-dd HH:mm' (формат двери clients)."""
    return local_dt(t).strftime("%Y-%m-%d %H:%M")


def day_str(t):
    return local_dt(t).strftime("%Y-%m-%d")


class FakeClock(object):
    """Инжектируемые часы (CONTRACT §1.1). `tick` — прибавка на каждый вызов (по умолчанию 0: время двигает тест)."""

    def __init__(self, start, tick=0.0):
        self.now = float(start)
        self.tick = float(tick)
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.calls += 1
            t = self.now
            self.now += self.tick
            return t

    def advance(self, seconds):
        with self._lock:
            self.now += float(seconds)
            return self.now

    def set(self, t):
        with self._lock:
            self.now = float(t)
            return self.now


class SeqIds(object):
    """Инжектируемый источник id: 32 hex, по порядку (детерминированный след)."""

    def __init__(self, start=1):
        self._n = itertools.count(start)
        self._lock = threading.Lock()
        self.issued = []

    def __call__(self):
        with self._lock:
            v = "%032x" % next(self._n)
            self.issued.append(v)
            return v


class Counters(object):
    """Счётчики внешних действий подделок. `client_sends` и `net` обязаны остаться 0 (CONTRACT §14)."""

    FIELDS = ("staff_posts", "staff_send_attempts", "escalations", "approval_cards", "notice_calls", "client_sends",
              "human_press_sends", "bridge_calls", "bridge_red_calls", "brain_appends", "result_writes",
              "result_reads", "crm_readbacks", "state_reads", "closing_reads", "cash_reads", "contract_reads",
              "pdf_reads", "event_reads", "delivery_status_reads", "rental_reads")

    def __init__(self):
        self._lock = threading.Lock()
        for f in self.FIELDS:
            setattr(self, f, 0)

    def bump(self, name, n=1):
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    @property
    def net(self):
        return net_attempts()

    def snapshot(self):
        d = dict((f, getattr(self, f)) for f in self.FIELDS)
        d["net"] = net_attempts()
        return d


def run_coro(coro):
    """Исполнить корутину подделки без цикла событий: подделки не засыпают; заснула — ошибка теста."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    coro.close()
    raise RuntimeError("корутина подделки заснула — подделки К4 обязаны завершаться без цикла событий")


# =====================================================================================================================
# Фабрика синтетических строк (живой формат кандидата)
# =====================================================================================================================

ST_BOOKED, ST_RENTED, ST_DONE = "Бронь", "В аренде", "Завершена"
CLIENTS_SOURCE = "лист «клиенты» (clients filter=all)"


def _num(v):
    """parseNumber двери: число или 0 (пустая клетка суммы приходит 0, f2f7295:bridge_prod/ReadFleet.js:494)."""
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return v
    s = re.sub(r"[^\d.\-]", "", str(v or "").replace(",", "."))
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return 0


def make_row(row, status, bike, name, date_start, date_end, contacts="", booking_id="", deposit_raw="", debt=0,
             to_pay=0, paid=0, pay_per_day=0, auto_cancel="OFF", note="", type_="скутер", helmets="", duration="",
             moment=None):
    """Строка двери `clients` в живом формате (f2f7295:bridge_prod/ReadClients.js:95-121). Без `price`.

    `date_start`/`date_end` — 'yyyy-MM-dd HH:mm' или None (нераспознанная дата). Флаги двери (`is_active`,
    `is_overdue`, `days_overdue`, `is_fresh`) считаются как у двери относительно `moment` (секунды эпохи), если он дан.
    """
    st = str(status or "").strip()
    is_active = st == ST_RENTED and str(auto_cancel or "").strip() != "ON"
    end_dt = None
    if date_end:
        try:
            end_dt = datetime.datetime.strptime(str(date_end)[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            end_dt = None
    start_dt = None
    if date_start:
        try:
            start_dt = datetime.datetime.strptime(str(date_start)[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            start_dt = None
    now_dt = local_dt(moment) if moment is not None else None
    is_overdue = bool(is_active and end_dt is not None and now_dt is not None and end_dt < now_dt)
    days_overdue = int((now_dt - end_dt).total_seconds() // 86400) if is_overdue else 0
    is_fresh = bool(start_dt is not None and (now_dt is None or start_dt >= now_dt - datetime.timedelta(days=365)))
    dep_raw = str(deposit_raw if deposit_raw is not None else "").strip()
    return {
        "row": int(row),
        "status": st,
        "auto_cancel": str(auto_cancel or "").strip(),
        "bike": str(bike or "").strip(),
        "name": str(name or "").strip(),
        "date_start": date_start,
        "date_end": date_end,
        "duration": str(duration or "").strip(),
        "pay_per_day": _num(pay_per_day),
        "debt": _num(debt),
        "to_pay": _num(to_pay),
        "paid": _num(paid),
        "deposit": _num(dep_raw),
        "deposit_raw": dep_raw,
        "helmets": str(helmets or "").strip(),
        "contacts": str(contacts or "").strip(),
        "note": str(note or "").strip(),
        "type": str(type_ or "").strip(),
        "booking_id": str(booking_id or "").strip(),
        "is_active": is_active,
        "is_overdue": is_overdue,
        "days_overdue": days_overdue,
        "is_fresh": is_fresh,
    }


def clients_reply(rows, filter="all"):
    """Ответ двери `clients` через мост: {ok, data: {clients, summary}} (wa_book_read.rows_of понимает обе формы)."""
    rows = [dict(r) for r in rows]
    summary = {"count": len(rows), "active": len([r for r in rows if r.get("is_active")]),
               "overdue": len([r for r in rows if r.get("is_overdue")]),
               "total_debt": sum(r.get("debt") or 0 for r in rows if r.get("is_active")),
               "total_paid": sum(r.get("paid") or 0 for r in rows),
               "total_deposits": sum(r.get("deposit") or 0 for r in rows if r.get("is_active"))}
    return {"ok": True, "data": {"clients": rows, "summary": summary}, "filter": filter}


def make_cash(row, amount, msg_date, bike="", booking_id="", currency="THB", category="rental", msg_id=None,
              description="", raw="", status="", deposit="", recorded_at=None, group="Money Cashflow",
              sender="@cashier"):
    """Строка листа «транзакции» Bot Data (TX_HEADERS, f2f7295:bridge_build_tx_find/BotData.js:1608): номер строки
    листа + клетки. `msg_date` — 'YYYY-MM-DD' (день сообщения кассы)."""
    return {"row": int(row), "recorded_at": recorded_at or (str(msg_date) + " 12:00:00"), "msg_date": msg_date,
            "group": group, "sender": sender, "amount": amount, "currency": currency, "category": category,
            "bike": bike, "deposit": deposit, "description": description, "raw": raw, "status": status,
            "msg_id": str(msg_id if msg_id is not None else "m%d" % int(row)), "booking_id": booking_id}


def cash_link(msg_id):
    return "https://t.me/c/1000000001/%s" % msg_id if msg_id else ""


def make_contract(row, doc_id, client, contract_date, bike, phone, signed=True, signed_at=None, pdf_id=None,
                  nick="", status=None):
    """Строка реестра подписей TB e-Sign (поля записи — f2f7295:bridge_build_contract/ContractDoor.js:275-290)."""
    return {"row": int(row), "doc_id": doc_id, "client": client, "contract_date": contract_date,
            "contract_date_raw": (contract_date[8:10] + "." + contract_date[5:7] + "." + contract_date[:4])
            if contract_date else "", "created_raw": "", "date_src": "contract_date" if contract_date else "none",
            "status": status or ("ПОДПИСАН" if signed else "ОТПРАВЛЕН"), "signed": bool(signed),
            "signed_at": signed_at, "bike": bike, "phone": phone, "nick": nick, "pdf_id": pdf_id}


def pdf_bytes(file_id):
    return ("%%PDF-1.4 синтетический договор %s\n" % file_id).encode("utf-8")


def pdf_sha256(file_id):
    return hashlib.sha256(pdf_bytes(file_id)).hexdigest()


def _phones_last9(cell):
    return [p for p in (WT.last9(x) for x in re.split(r"[,;/|\n]+", str(cell or ""))) if p]


# =====================================================================================================================
# Дверь моста (только чтение) — живой формат ответов; красные шаги — счётчик
# =====================================================================================================================


class FakeBridge(object):
    """Подделка `bridge_client.BridgeClient` для чтений К4. Ни одного сетевого вызова; журнал `calls`."""

    def __init__(self, clock, counters=None):
        self.clock = clock
        self.counters = counters or Counters()
        self.rows = []
        self.cash = []
        self.registry = []
        self.unread = []
        self.pdfs = {}
        self.pdf_mismatch = set()
        self.states = {}
        self.closing = {}
        self.events = {}
        self.fail = {}
        self.calls = []
        self.red_calls = []

    def _hit(self, action, **kw):
        self.calls.append((action, dict(kw)))
        self.counters.bump("bridge_calls")
        f = self.fail.get(action)
        if isinstance(f, BaseException):
            raise f
        return f

    # --- чтения ---
    def clients(self, filter="active"):
        f = self._hit("clients", filter=filter)
        if f is not None:
            return f
        rows = self.rows if filter == "all" else [r for r in self.rows if r.get("is_active") and r.get("is_fresh")]
        return clients_reply(rows, filter)

    def tx_find(self, bike="", booking_id="", date_from="", date_to="", limit=None):
        f = self._hit("tx_find", bike=bike, booking_id=booking_id, date_from=date_from, date_to=date_to, limit=limit)
        if f is not None:
            return f
        plate = WT.plate_of(bike) if str(bike or "").strip() else ""
        booking = str(booking_id or "").strip()
        lim = int(limit) if limit else 50
        span = bool(date_from or date_to)
        items, voided, matched, first, last = [], 0, 0, "", ""
        total = {}
        for c in sorted(self.cash, key=lambda x: -x["row"]):            # newest-first, как дверь
            day = str(c.get("msg_date") or "")[:10]
            if day:
                first = day if (not first or day < first) else first
                last = day if (not last or day > last) else last
            if span and day:
                if date_from and day < date_from:
                    continue
                if date_to and day > date_to:
                    continue
            if plate and WT.plate_of(str(c.get("bike") or "")) != plate:
                continue
            if booking and str(c.get("booking_id") or "").strip() != booking:
                continue
            if str(c.get("status") or "").lower() == "void":
                voided += 1
                continue
            matched += 1
            cur = str(c.get("currency") or "THB").upper()
            amt = c.get("amount")
            if isinstance(amt, (int, float)) and not isinstance(amt, bool):
                total[cur] = round(total.get(cur, 0) + amt, 2)
            if len(items) >= lim:
                continue
            items.append({"row": c["row"], "date": day or None, "date_src": "msg_date" if day else "recorded_at",
                          "msg_date_raw": day, "recorded_at": c.get("recorded_at") or "", "amount": amt,
                          "amount_raw": str(amt), "amount_unparsed": False, "currency": cur,
                          "category": str(c.get("category") or ""), "bike": str(c.get("bike") or ""),
                          "deposit": str(c.get("deposit") or ""), "description": str(c.get("description") or ""),
                          "raw": str(c.get("raw") or ""), "msg_id": c.get("msg_id") or "",
                          "link": cash_link(c.get("msg_id")), "status": str(c.get("status") or ""),
                          "booking_id": str(c.get("booking_id") or ""), "group": c.get("group") or "",
                          "sender": c.get("sender") or ""})
        return {"ok": True, "filter": {"bike": bike, "booking_id": booking_id, "date_from": date_from,
                                       "date_to": date_to},
                "limit": lim, "limit_max": 200,
                "checked": {"span_from": date_from or first, "span_to": date_to or last, "sheet_first": first,
                            "sheet_last": last, "rows_scanned": len(self.cash), "undated": 0,
                            "rows_in_span": matched + voided, "voided": voided, "matched": matched,
                            "returned": len(items), "truncated": matched > len(items), "amount_unparsed": 0,
                            "date_unparsed": 0, "complete": matched == len(items)},
                "total": total, "total_complete": True, "items": items}

    def contract_find(self, phone="", name="", bike="", date_from="", date_to="", limit=None):
        f = self._hit("contract_find", phone=phone, name=name, bike=bike, date_from=date_from, date_to=date_to)
        if f is not None:
            return f
        key = WT.last9(phone) if str(phone or "").strip() else ""
        plate = WT.plate_of(bike) if str(bike or "").strip() else ""
        matched = []
        for c in self.registry:
            on = []
            if key:
                if key in _phones_last9(c.get("phone")):
                    on.append("phone")
                elif key in _phones_last9(c.get("nick")):
                    on.append("nick")
                else:
                    continue
            if plate:
                if WT.plate_of(str(c.get("bike") or "")) != plate:
                    continue
                on.append("bike")
            day = c.get("contract_date")
            if (date_from or date_to) and day:
                if date_from and day < date_from:
                    continue
                if date_to and day > date_to:
                    continue
            rec = dict((k, c.get(k)) for k in ("row", "doc_id", "client", "contract_date", "contract_date_raw",
                                                "created_raw", "date_src", "status", "signed", "signed_at", "bike",
                                                "phone", "pdf_id"))
            rec["matched_on"] = on
            matched.append(rec)
        matched.sort(key=lambda x: -x["row"])
        signed = [m for m in matched if m["signed"]]
        pick = None
        if not matched:
            outcome = "none"
        elif not signed:
            outcome = "none_signed"
        elif len(signed) > 1:
            outcome = "ambiguous"
        else:
            outcome = "one"
            pick = dict(signed[0], pdf_ready=bool(signed[0].get("pdf_id")))
        return {"ok": True, "outcome": outcome, "pick": pick, "reason": None, "items": matched, "undated_items": [],
                "filter": {"phone_last9": key, "bike": bike, "date_from": date_from, "date_to": date_to},
                "checked": {"sheet": "Реестр", "rows_scanned": len(self.registry), "span_from": date_from,
                            "span_to": date_to, "undated": 0, "undated_signed": 0, "date_unparsed": 0,
                            "unread": list(self.unread), "complete": not self.unread, "matched": len(matched),
                            "signed": len(signed), "returned": len(matched), "truncated": False}}

    def contract_pdf(self, file_id):
        f = self._hit("contract_pdf", id=file_id)
        if f is not None:
            return f
        meta = self.pdfs.get(file_id)
        if meta is None:
            return {"ok": False, "error": "not_in_registry", "id": file_id}
        raw = pdf_bytes(file_id)
        res = {"ok": True, "id": file_id, "name": meta.get("name") or ("%s.pdf" % file_id), "mime": "application/pdf",
               "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
               "content_b64": base64.b64encode(raw).decode("ascii"), "row": meta.get("row"),
               "client": meta.get("client"), "contract_date": meta.get("contract_date"),
               "signed_at": meta.get("signed_at")}
        if file_id in self.pdf_mismatch:
            return dict(res, ok=False, error="pdf_mismatch", verified=False,
                        message="длина или sha256 содержимого не сошлись с ответом моста")
        return dict(res, verified=True)                                  # как bridge_client.contract_pdf

    def state_get(self, bike):
        f = self._hit("state_get", bike=bike)
        if f is not None:
            return f
        item = self.states.get(str(bike or "").strip())
        if item is None:
            return {"ok": False, "error": "not_found", "bike": bike}
        return {"ok": True, "item": dict(item)}

    def closing_get(self, booking_id=None, bike=None):
        f = self._hit("closing_get", booking_id=booking_id, bike=bike)
        if f is not None:
            return f
        if not booking_id:
            return {"ok": False, "error": "no_key", "message": "К4: лист закрытия только по booking_id"}
        item = self.closing.get(str(booking_id))
        if item is None:
            return {"ok": False, "error": "not_found"}
        return {"ok": True, "item": dict(item)}

    def read_events(self, bike, limit=8):
        f = self._hit("read_events", bike=bike, limit=limit)
        if f is not None:
            return f
        return {"ok": True, "bike": bike, "items": [dict(e) for e in self.events.get(bike, [])][:limit]}

    # --- красные шаги (К4 их не зовёт; Splinter зовёт после claim_execution) ---
    def activate_booking(self, **kw):
        self.red_calls.append(("activate_booking", dict(kw)))
        self.counters.bump("bridge_red_calls")
        return {"ok": True, "row": kw.get("row")}

    def close_booking(self, **kw):
        self.red_calls.append(("close_booking", dict(kw)))
        self.counters.bump("bridge_red_calls")
        return {"ok": True, "row": kw.get("row")}


# =====================================================================================================================
# Порты CONTRACT §9.1
# =====================================================================================================================


class FakeRentalSource(object):
    """RentalSource: read() → {"ok", "rows", "observed_at", "read_at", "source", "error"}.

    observed_at — начало НАШЕГО чтения (дверь) или заданный `observed_at` («старый снимок»: snapshot.taken_at как есть).
    Это не версия листа (CONTRACT §8.4)."""

    def __init__(self, clock, rows=None, bridge=None, source_name=CLIENTS_SOURCE, observed_at=None, fail=None,
                 counters=None):
        self.clock = clock
        self.rows = rows
        self.bridge = bridge
        self.source_name = source_name
        self.observed_at = observed_at
        self.fail = fail
        self.counters = counters or Counters()
        self.calls = []

    def read(self):
        t0 = self.clock()
        self.calls.append(t0)
        self.counters.bump("rental_reads")
        if self.fail:
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": str(self.fail)}
        try:
            if self.bridge is not None:
                rows = WB.rows_of(self.bridge.clients(filter="all"))
            else:
                rows = [dict(r) for r in (self.rows or [])]
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": "unknown:%s" % type(e).__name__}
        if rows is None:
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": "дверь clients не дала строк"}
        obs = self.observed_at if self.observed_at is not None else t0
        return {"ok": True, "rows": rows, "observed_at": obs, "read_at": self.clock(), "source": self.source_name,
                "error": ""}


class FakeTelegram(object):
    """Отправитель Telegram для подделки staff_ask: `send(place, chat_id, text, thread_id, reply_to)` → mid | None.

    Режимы места (`mode[place]`): "ok"; "refuse" (не принято, не доставлено); "deliver_then_raise" (доставлено, затем
    исключение — как `_sask_sender` кандидата, глотающий его в None, splinter.py:1747-1756); "raise_before"
    (исключение до доставки). `sent` — доставленные посты, `attempts` — все попытки."""

    def __init__(self, clock, counters=None, start_mid=7001):
        self.clock = clock
        self.counters = counters or Counters()
        self.mode = {}
        self.mids = {}
        self._next = itertools.count(start_mid)
        self.sent = []
        self.attempts = []

    def next_mid(self, place):
        q = self.mids.get(place)
        if q:
            return str(q.pop(0))
        return str(next(self._next))

    async def send(self, place, chat_id, text, thread_id=None, reply_to=None):
        self.attempts.append({"place": place, "chat": chat_id, "thread_id": thread_id, "at": self.clock()})
        self.counters.bump("staff_send_attempts")
        mode = self.mode.get(place, "ok")
        if mode == "refuse":
            return None
        if mode == "raise_before":
            raise TimeoutError("таймаут до доставки (подделка)")
        mid = self.next_mid(place)
        self.sent.append({"place": place, "chat": chat_id, "msg_id": mid, "thread_id": thread_id,
                          "reply_to": reply_to, "text": text, "at": self.clock()})
        if mode == "deliver_then_raise":
            raise TimeoutError("доставлено, затем таймаут ответа (подделка)")
        return mid


async def _safe_send(send, place, chat, text, thread_id, reply_to):
    """Как `_sask_sender` кандидата: любое исключение → None («не знаю, ушло ли»)."""
    try:
        return await send(place, chat, text, thread_id, reply_to)
    except Exception:                                                   # noqa: BLE001
        return None


class FakeStaffAsk(object):
    """staff_ask по шву S1–S7 (CONTRACT §13; DESIGN §6.5). Состояние в памяти (на диск не пишет).

    Места — коды К4: "topic" (тема байка), "delivery" (Delivery cooperation), "agents" («Агенты»)."""

    WAIT_S = 3 * 3600                                                    # staff_ask.py:22-26 — свой срок подделки, не дела
    KIND_BIKE = "байк"
    KINDS_MANAGERS = ("цена", "бронь", "сложность")

    def __init__(self, clock, counters=None, enabled=True, wait_s=None):
        self.clock = clock
        self.counters = counters or Counters()
        self.enabled = enabled
        self.wait_s = float(wait_s if wait_s is not None else self.WAIT_S)
        self.asks = {}
        self.by_mid = {}
        self.order = []
        self.dlive_marks = []
        self.calls = []
        self._seq = itertools.count(1)

    @staticmethod
    def dedup_key(kind, bike, q_ru, expect_id=None):
        """S2: при expect_id — sha1(вид|байк|вопрос|expect_id); без него — прежний ключ staff_ask.py:154-155."""
        base = "%s|%s|%s" % (kind, bike, str(q_ru).strip().lower())
        if expect_id is not None:
            base = base + "|" + str(expect_id)
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

    def _open_same(self, key):
        for qid in self.order:
            a = self.asks[qid]
            if a["key"] == key and a["status"] in ("open", "escalated"):
                return qid
        return None

    async def ask(self, send, *, kind, bike, q_ru, q_th, urgency="для ясности", handles=(), servicing_chat=None,
                  topic_id=None, delivery_chat=None, agents_chat=None, reply_to=None, now=None, path=None,
                  case_id=None, case_ver=None, expect_id=None):
        """S1 → {"posts": [{place, chat, msg_id, thread_id}], "unknown_places", "refusal", "qid", "deduped", "why"}."""
        self.calls.append(("ask", {"kind": kind, "bike": bike, "expect_id": expect_id, "case_id": case_id,
                                   "case_ver": case_ver}))
        res = {"posts": [], "unknown_places": [], "refusal": None, "qid": None, "deduped": False, "why": ""}
        if not self.enabled:
            res.update(refusal="disabled", why="выключено")
            return res
        now = self.clock() if now is None else now
        kind = kind if kind in (self.KIND_BIKE,) + self.KINDS_MANAGERS else self.KIND_BIKE
        q_ru, q_th = str(q_ru or "").strip(), str(q_th or "").strip()
        if not q_ru:
            res.update(refusal="no_text", why="нет текста вопроса")
            return res
        agents = kind in self.KINDS_MANAGERS
        if not agents and not q_th:
            res.update(refusal="no_thai", why="нет тайского текста")
            return res
        if not agents and not topic_id:
            res.update(refusal="no_topic", why="тема байка не найдена")
            return res
        key = self.dedup_key(kind, bike, q_ru, expect_id)
        same = self._open_same(key)
        if same:
            res.update(deduped=True, qid=same, why="тот же вопрос уже открыт")
            return res
        qid = "%d-%s-%d" % (int(now), key[:6], next(self._seq))
        a = {"key": key, "kind": kind, "bike": bike or "", "q_ru": q_ru, "q_th": q_th, "urgency": urgency,
             "asked_ts": now, "status": "open", "posts": {}, "answers": [], "case_id": case_id,
             "case_ver": case_ver, "expect_id": expect_id}
        if expect_id is not None:
            a["managed_by"] = "rental_case"                               # S3
        self.asks[qid] = a                                               # запись ДО отправки (G12)
        self.order.append(qid)
        res["qid"] = qid
        if agents:
            mid = await _safe_send(send, "agents", agents_chat, "вопрос (%s): %s" % (kind, q_ru), None, None)
            if mid is None:
                res["unknown_places"].append("agents")
                res["why"] = "«Агенты»: исход отправки неизвестен"
                return res
            a["posts"]["agents"] = [agents_chat, mid]
            a["status"] = "escalated"
            self.by_mid["%s:%s" % (agents_chat, mid)] = qid
            res["posts"].append({"place": "agents", "chat": agents_chat, "msg_id": mid, "thread_id": None})
            self.counters.bump("staff_posts")
            return res
        mid = await _safe_send(send, "topic", servicing_chat, "%s / %s" % (q_th, q_ru), topic_id, reply_to)
        if mid is None:
            res["unknown_places"].append("topic")
            res["why"] = "тема байка: исход отправки неизвестен"
            return res
        a["posts"]["question"] = [servicing_chat, mid, topic_id]
        self.by_mid["%s:%s" % (servicing_chat, mid)] = qid
        res["posts"].append({"place": "topic", "chat": servicing_chat, "msg_id": mid, "thread_id": topic_id})
        self.counters.bump("staff_posts")
        if expect_id is None:
            self.dlive_marks.append((servicing_chat, mid, qid))          # S7: метка решателю — только не делу
        dmid = await _safe_send(send, "delivery", delivery_chat, "посмотрите вопрос по %s (%s)" % (bike, urgency),
                                None, None)
        if dmid is None:
            res["unknown_places"].append("delivery")
        else:
            a["posts"]["delivery"] = [delivery_chat, dmid]
            self.by_mid["%s:%s" % (delivery_chat, dmid)] = qid
            res["posts"].append({"place": "delivery", "chat": delivery_chat, "msg_id": dmid, "thread_id": None})
            self.counters.bump("staff_posts")
        return res

    async def escalate(self, qid, send, *, agents_chat, why):
        """S4 → {"posts": [{place, chat, msg_id, thread_id}]} | {"unknown_places": [...]} | {"refusal": код}."""
        self.calls.append(("escalate", {"qid": qid, "why": why}))
        a = self.asks.get(qid)
        if a is None:
            return {"refusal": "no_question", "posts": []}
        if a.get("status") == "closed":
            return {"refusal": "closed", "posts": []}
        mid = await _safe_send(send, "agents", agents_chat, "уточнение: %s (%s)" % (a["q_ru"], why), None, None)
        if mid is None:
            return {"unknown_places": ["agents"], "posts": []}
        a["posts"]["agents"] = [agents_chat, mid]
        a["status"] = "escalated"
        self.by_mid["%s:%s" % (agents_chat, mid)] = qid
        self.counters.bump("escalations")
        return {"posts": [{"place": "agents", "chat": agents_chat, "msg_id": mid, "thread_id": None}]}

    def on_reply(self, brain_append, *, chat, reply_to, mid, user_id, username, is_bot, text, ts=None, path=None):
        """Реплай → строка мозга (как staff_ask.on_reply, staff_ask.py:245-268)."""
        self.calls.append(("on_reply", {"chat": chat, "reply_to": reply_to, "mid": mid}))
        if reply_to is None or is_bot or not str(text or "").strip():
            return {"recorded": False, "qid": None, "why": "не ответ человека"}
        qid = self.by_mid.get("%s:%s" % (chat, reply_to))
        a = self.asks.get(qid) if qid else None
        if a is None:
            return {"recorded": False, "qid": None, "why": "не реплай на вопрос"}
        line = "ОТВЕТ СОТРУДНИКА [staff_ask %s#%s] id %s: %s" % (qid, mid, user_id, str(text).strip()[:200])
        ok, why = brain_append(line)
        self.counters.bump("brain_appends")
        a["answers"].append({"mid": mid, "user_id": user_id, "brain": "ok" if ok else "не принят: %s" % why})
        if a.get("status") != "closed":
            a["status"] = "answered"
        return {"recorded": bool(ok), "qid": qid, "why": "" if ok else why, "line": line}

    def close(self, qid, *, reason, path=None):
        """S6: запись → closed; due/tick/дедуп её не видят."""
        self.calls.append(("close", {"qid": qid, "reason": reason}))
        a = self.asks.get(qid)
        if a is None:
            return False
        a["status"] = "closed"
        a["closed_reason"] = reason
        return True

    def due(self, now, wait=None):
        """Как staff_ask.due, но записи дела (S3, managed_by=rental_case) и закрытые (S6) пропускаются."""
        wait = self.wait_s if wait is None else wait
        out = []
        for qid in self.order:
            a = self.asks[qid]
            if a.get("managed_by") == "rental_case":
                continue
            if a.get("status") == "open" and "question" in a["posts"] and now - float(a["asked_ts"]) >= wait:
                out.append(qid)
        return out

    async def tick(self, send, *, agents_chat, now=None, path=None):
        """Эскалация по СВОЕМУ сроку подделки (3 ч) — только записей не дела; сроком дела это не является (I43)."""
        now = self.clock() if now is None else now
        n = 0
        for qid in self.due(now):
            a = self.asks[qid]
            mid = await _safe_send(send, "agents", agents_chat, "не ответили: %s" % a["q_ru"], None, None)
            if mid is None:
                continue
            a["posts"]["agents"] = [agents_chat, mid]
            a["status"] = "escalated"
            self.by_mid["%s:%s" % (agents_chat, mid)] = qid
            self.counters.bump("escalations")
            n += 1
        return n


def _subject(exp):
    s = (exp or {}).get("subject")
    if isinstance(s, str):
        try:
            s = json.loads(s)
        except ValueError:
            s = {"text": s}
    return s if isinstance(s, dict) else {}


def s1_to_port(r, at, role_of_place=None):
    """Ответ S1 → форма порта StaffAskPort.post (CONTRACT §9.1): posts непуст → posted; refusal → refused;
    deduped → deduped; иначе → unknown (в т. ч. пусто без кода и unknown_places)."""
    roles = role_of_place or {"topic": "question", "delivery": "delivery", "agents": "agents"}
    posts = (r or {}).get("posts") or []
    if posts:
        return {"posted": [{"place": p["place"], "chat": p["chat"], "msg_id": p["msg_id"],
                            "thread_id": p.get("thread_id"), "role": roles.get(p["place"], p["place"]), "at": at}
                           for p in posts], "qid": r.get("qid")}
    if (r or {}).get("refusal"):
        return {"refused": r["refusal"]}
    if (r or {}).get("deduped"):
        return {"deduped": r.get("qid")}
    return {"unknown": (r or {}).get("why") or "посты пусты без кода отказа"}


class FakeStaffAskPort(object):
    """StaffAskPort (async): post(exp) → {"posted", "qid"} | {"refused"} | {"deduped"} | {"unknown"}; повтора нет.

    Поля вопроса берутся из `exp` (exp_id, case_id, case_ver, subject: q_ru/q_th/staff_kind/urgency/bike), а чего
    нет — из значений подделки по умолчанию."""

    def __init__(self, staff_ask, telegram, clock, servicing_chat, topic_id, delivery_chat, agents_chat,
                 bike="NMAX 155 6908", kind="байк", q_ru="Будет ли байк готов?", q_th="รถพร้อมไหมครับ",
                 urgency="клиент интересуется", fail=None):
        self.staff_ask = staff_ask
        self.telegram = telegram
        self.clock = clock
        self.chats = {"servicing_chat": servicing_chat, "topic_id": topic_id, "delivery_chat": delivery_chat,
                      "agents_chat": agents_chat}
        self.defaults = {"bike": bike, "kind": kind, "q_ru": q_ru, "q_th": q_th, "urgency": urgency}
        self.fail = fail
        self.calls = []

    async def post(self, exp):
        exp = dict(exp or {})
        self.calls.append(exp.get("exp_id"))
        if self.fail is not None:
            return {"unknown": type(self.fail).__name__ if isinstance(self.fail, BaseException) else str(self.fail)}
        s = _subject(exp)
        kind = s.get("staff_kind") or s.get("kind") or self.defaults["kind"]
        place = exp.get("place")                                         # главное место ожидания (rc_expect.place)
        if place == "agents" and kind not in FakeStaffAsk.KINDS_MANAGERS:
            kind = "цена"
        elif place in ("topic", "delivery") and kind in FakeStaffAsk.KINDS_MANAGERS:
            kind = FakeStaffAsk.KIND_BIKE
        try:
            r = await self.staff_ask.ask(
                self.telegram.send, kind=kind, bike=s.get("bike") or exp.get("bike") or self.defaults["bike"],
                q_ru=s.get("q_ru") or self.defaults["q_ru"], q_th=s.get("q_th") or self.defaults["q_th"],
                urgency=s.get("urgency") or self.defaults["urgency"],
                servicing_chat=self.chats["servicing_chat"], topic_id=self.chats["topic_id"],
                delivery_chat=self.chats["delivery_chat"], agents_chat=self.chats["agents_chat"],
                case_id=exp.get("case_id"), case_ver=exp.get("case_ver"), expect_id=exp.get("exp_id"))
        except Exception as e:                                           # noqa: BLE001 — таймаут/исключение → unknown
            return {"unknown": type(e).__name__}
        return s1_to_port(r, self.clock())


class FakeEscalationPort(object):
    """EscalationPort (async): escalate(exp) → та же форма, role=escalation (S4)."""

    def __init__(self, staff_ask, telegram, clock, agents_chat, why="решение одобряющего"):
        self.staff_ask = staff_ask
        self.telegram = telegram
        self.clock = clock
        self.agents_chat = agents_chat
        self.why = why
        self.calls = []

    async def escalate(self, exp):
        exp = dict(exp or {})
        qid = exp.get("ext_qid") or exp.get("qid")
        self.calls.append((exp.get("exp_id"), qid))
        try:
            r = await self.staff_ask.escalate(qid, self.telegram.send, agents_chat=self.agents_chat, why=self.why)
        except Exception as e:                                           # noqa: BLE001
            return {"unknown": type(e).__name__}
        r = dict(r, qid=qid)
        return s1_to_port(r, self.clock(), {"agents": "escalation"})


class FakeApprovalPort(object):
    """ApprovalPort (async): post_card(exp) → {"posted": [{place: "intake", chat, msg_id, thread_id, role: "card",
    at}], "qid": None} | {"unknown"}. Карточка/вопрос confirm_link во «Входящие»."""

    def __init__(self, telegram, clock, chat, counters=None, place="intake"):
        self.telegram = telegram
        self.clock = clock
        self.chat = chat
        self.place = place
        self.counters = counters or telegram.counters
        self.calls = []

    async def post_card(self, exp):
        exp = dict(exp or {})
        self.calls.append(exp.get("exp_id"))
        chat = exp.get("chat") or self.chat
        try:
            mid = await self.telegram.send(self.place, chat, "карточка %s" % exp.get("exp_id"), None, None)
        except Exception as e:                                           # noqa: BLE001
            return {"unknown": type(e).__name__}
        if mid is None:
            return {"unknown": "карточка не принята"}
        self.counters.bump("approval_cards")
        return {"posted": [{"place": self.place, "chat": chat, "msg_id": mid, "thread_id": None, "role": "card",
                            "at": self.clock()}], "qid": None}


def cash_fkey(fact):
    """Тождество факта кассы (CONTRACT §8.2): ["cash", src, row, msg_id|link]."""
    return ["cash", str(fact.get("src") or "tx_find"), fact.get("row"), fact.get("msg_id") or fact.get("link") or ""]


class FakeCashPort(object):
    """CashPort: find(...) → wa_agent_tools.cash_result + {"window", "complete", "keys", "cancelled"}."""

    def __init__(self, bridge, clock, counters=None):
        self.bridge = bridge
        self.clock = clock
        self.counters = counters or bridge.counters
        self.calls = []

    def find(self, *, booking_id="", bike="", date_from="", date_to=""):
        at = self.clock()
        self.calls.append({"booking_id": booking_id, "bike": bike, "date_from": date_from, "date_to": date_to})
        self.counters.bump("cash_reads")
        try:
            resp = self.bridge.tx_find(bike=bike, booking_id=booking_id, date_from=date_from, date_to=date_to)
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "unknown": type(e).__name__}
        res = WT.cash_result(resp, at)
        checked = (resp or {}).get("checked") if isinstance(resp, dict) else {}
        checked = checked if isinstance(checked, dict) else {}
        plate = WT.plate_of(bike) if bike else ""
        cancelled = []
        for c in self.bridge.cash:
            if str(c.get("status") or "").lower() != "void":
                continue
            if plate and WT.plate_of(str(c.get("bike") or "")) != plate:
                continue
            if booking_id and str(c.get("booking_id") or "") != str(booking_id):
                continue
            day = str(c.get("msg_date") or "")[:10]
            if (date_from and day < date_from) or (date_to and day > date_to):
                continue
            cancelled.append(["cash", "tx_find", c["row"], c.get("msg_id") or cash_link(c.get("msg_id"))])
        res = dict(res)
        res["window"] = {"booking_id": booking_id or "", "bike": bike or "", "plate": plate, "date_from": date_from,
                         "date_to": date_to, "span_from": checked.get("span_from"), "span_to": checked.get("span_to")}
        res["complete"] = checked.get("complete") is True and not checked.get("truncated")
        res["keys"] = [cash_fkey(f) for f in res.get("facts") or []]
        res["cancelled"] = cancelled
        return res


def rental_fact_result(rental, at=None):
    """Привязка/строка → результат инструмента `rental` (wa_agent_tools.result, FACT) для bind_contract.
    Уже готовый результат (есть `outcome`) отдаётся как есть."""
    if isinstance(rental, dict) and "outcome" in rental:
        return rental
    r = dict(rental or {})
    fact = {"kind": "rental", "booking_id": r.get("booking_id") or None,
            "bike": r.get("bike") or r.get("bike_name") or r.get("plate"),
            "date_start": r.get("date_start") or r.get("start_at") or r.get("start_day"),
            "date_end": r.get("date_end") or r.get("end_at") or r.get("end_day"),
            "status": r.get("status") or r.get("status_seen"), "price": None, "currency": "THB"}
    return WT.result("rental", WT.FACT, "снимок броней (лист «клиенты»)", ref=str(fact["booking_id"] or ""), at=at,
                     window="%s…%s" % (fact["date_start"], fact["date_end"]), facts=[fact])


class FakeContractPort(object):
    """ContractPort: find(number, rental, …) → wa_agent_tools.contract_result(resp, at, number, rental)."""

    def __init__(self, bridge, clock, counters=None):
        self.bridge = bridge
        self.clock = clock
        self.counters = counters or bridge.counters
        self.calls = []

    def find(self, *, number, rental, phone="", bike="", date_from="", date_to=""):
        at = self.clock()
        self.calls.append({"number": number, "phone": phone, "bike": bike})
        self.counters.bump("contract_reads")
        try:
            resp = self.bridge.contract_find(phone=phone, bike=bike, date_from=date_from, date_to=date_to)
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "unknown": type(e).__name__}
        return WT.contract_result(resp, at, number=number, rental=rental_fact_result(rental, at))


class FakePdfPort(object):
    """PdfPort: fetch(file_id, allowed) → wa_agent_tools.pdf_result."""

    def __init__(self, bridge, clock, counters=None):
        self.bridge = bridge
        self.clock = clock
        self.counters = counters or bridge.counters
        self.calls = []

    def fetch(self, file_id, *, allowed=()):
        at = self.clock()
        self.calls.append(file_id)
        self.counters.bump("pdf_reads")
        try:
            resp = self.bridge.contract_pdf(file_id)
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "unknown": type(e).__name__}
        return WT.pdf_result(resp, at, allowed=allowed)


class FakeClosingPort(object):
    """ClosingPort (в К4 только подделка): get(booking_id) → {"ok": True, "item"} | {"ok": False, "error"} |
    {"ok": False, "unknown"}. Без booking_id — отказ (фоллбэк по байку не принимается)."""

    def __init__(self, bridge, clock, counters=None):
        self.bridge = bridge
        self.clock = clock
        self.counters = counters or bridge.counters
        self.calls = []

    def get(self, booking_id):
        self.calls.append(booking_id)
        self.counters.bump("closing_reads")
        if not booking_id:
            return {"ok": False, "error": "no_key"}
        try:
            return self.bridge.closing_get(booking_id=booking_id)
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "unknown": type(e).__name__}


def state_item(bike, status="в аренде", location="", booking_id="", client="", date_out="", date_due="",
               date_back="", service_name="", last_event_msg_id="", updated="2026-10-01 10:05"):
    """Строка листа «состояние_байка» (STATE_HEADERS, f2f7295:bridge_prod/BotData.js:92-93)."""
    return {"bike": bike, "status": status, "location": location, "booking_id": booking_id, "client": client,
            "date_out": date_out, "date_due": date_due, "date_back": date_back, "service_name": service_name,
            "last_event_msg_id": last_event_msg_id, "updated": updated}


def _updated_epoch(updated):
    try:
        d = datetime.datetime.strptime(str(updated)[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return epoch(d.year, d.month, d.day, d.hour, d.minute)


class FakeStatePort(object):
    """StatePort (в К4 только подделка; state_get — POST и может создать лист): get(bike) →
    {"ok": True, "item", "observed_at": <updated>, "read_at", "source": "состояние_байка"} |
    {"ok": False, "absent": True} | {"ok": False, "unknown": "<тип>"}."""

    def __init__(self, bridge, clock, counters=None):
        self.bridge = bridge
        self.clock = clock
        self.counters = counters or bridge.counters
        self.calls = []

    def get(self, bike):
        self.calls.append(bike)
        self.counters.bump("state_reads")
        try:
            resp = self.bridge.state_get(bike)
        except Exception as e:                                           # noqa: BLE001
            return {"ok": False, "unknown": type(e).__name__}
        if not (isinstance(resp, dict) and resp.get("ok")):
            if isinstance(resp, dict) and resp.get("error") == "not_found":
                return {"ok": False, "absent": True}
            return {"ok": False, "unknown": str((resp or {}).get("error") or "ответ без ok")}
        item = resp["item"]
        return {"ok": True, "item": item, "observed_at": _updated_epoch(item.get("updated")),
                "read_at": self.clock(), "source": "состояние_байка"}


class FakeBikeEventsPort(object):
    """BikeEventsPort: events(bike, limit) → {"ok": True, "items": [{type, at, ref}]}. Живой порт ref не даёт
    (bike_position.py:206-232) → `with_ref=False` отдаёт ref=""."""

    def __init__(self, clock, items=None, with_ref=True, counters=None):
        self.clock = clock
        self.items = dict(items or {})
        self.with_ref = with_ref
        self.counters = counters or Counters()
        self.calls = []

    def events(self, bike, limit=30):
        self.calls.append(bike)
        self.counters.bump("event_reads")
        out = []
        for e in self.items.get(bike, [])[:limit]:
            out.append({"type": e.get("type"), "at": e.get("at"), "ref": e.get("ref") if self.with_ref else ""})
        return {"ok": True, "items": out}


class FakeCrmReadback(object):
    """CrmReadback: row_status(target) → {"outcome": landed|absent|unknown, "row", "status", "read_at",
    "observed_at", "siblings": [{row, booking_id, status_old, status_new}]}. Исход задаёт тест (`plan`)."""

    def __init__(self, clock, counters=None):
        self.clock = clock
        self.counters = counters or Counters()
        self.plan = []
        self.default = {"outcome": "unknown", "row": None, "status": None, "siblings": []}
        self.calls = []

    def row_status(self, *, target):
        self.calls.append(dict(target or {}))
        self.counters.bump("crm_readbacks")
        r = dict(self.plan.pop(0) if self.plan else self.default)
        t = self.clock()
        r.setdefault("siblings", [])
        r["read_at"] = r.get("read_at") or t
        r["observed_at"] = r.get("observed_at") or t
        return r


class FakeResultSink(object):
    """ResultSink (место RESULT_RECORD_PLACE, в демо «sink:fake»): write(task, value) → {"ok": True} | {"unknown"};
    read(task) → {"outcome": landed|absent|unknown, "read_at", "value"}."""

    def __init__(self, clock, counters=None, name="sink:fake"):
        self.clock = clock
        self.counters = counters or Counters()
        self.name = name
        self.store = {}
        self.write_mode = "ok"
        self.read_mode = "ok"
        self.calls = []

    @staticmethod
    def _key(task):
        t = dict(task or {})
        return str(t.get("task_id") or t.get("id") or json.dumps(t, sort_keys=True, ensure_ascii=False))

    def write(self, task, value):
        self.calls.append(("write", self._key(task)))
        self.counters.bump("result_writes")
        if self.write_mode == "unknown":
            return {"unknown": "таймаут записи (подделка)"}
        self.store[self._key(task)] = {"value": dict(value or {}), "written_at": self.clock()}
        return {"ok": True}

    def read(self, task):
        self.calls.append(("read", self._key(task)))
        self.counters.bump("result_reads")
        t = self.clock()
        if self.read_mode == "unknown":
            return {"outcome": "unknown", "read_at": t}
        rec = self.store.get(self._key(task))
        if rec is None:
            return {"outcome": "absent", "read_at": t}
        return {"outcome": "landed", "read_at": t, "value": rec["value"], "written_at": rec["written_at"]}


class FakeNoticePort(object):
    """NoticePort (WA-ядро): propose(...) → {"draft_id"} | {"unknown"} — идемпотентен по notice_id (частичный UNIQUE
    `drafts.notice_id`, второго черновика на одно намерение нет); find(notice_id) → {"draft_id", "state", "wamid"} |
    {"absent": True} | {"unknown"}. Клиенту подделка НЕ пишет: `human_press` — нажатие человека в WA (не код К4),
    `send_to_client` — ловушка: любой вызов считается отправкой кодом и падает."""

    def __init__(self, clock, counters=None):
        self.clock = clock
        self.counters = counters or Counters()
        self.drafts = {}
        self.mode = "ok"
        self.calls = []
        self._ids = itertools.count(1)
        self._wamids = itertools.count(1)

    def propose(self, *, notice_id, case_id, case_ver, intent, facts):
        self.calls.append(("propose", notice_id, case_ver, intent))
        self.counters.bump("notice_calls")
        if self.mode == "unknown":
            return {"unknown": "таймаут WA (подделка)"}
        d = self.drafts.get(notice_id)
        if d is None:
            d = {"draft_id": next(self._ids), "state": "pending", "wamid": None, "case_id": case_id,
                 "case_ver": case_ver, "intent": intent, "facts": list(facts or [])}
            self.drafts[notice_id] = d
        return {"draft_id": d["draft_id"]}

    def find(self, notice_id):
        self.calls.append(("find", notice_id))
        self.counters.bump("notice_calls")
        if self.mode == "find_unknown":
            return {"unknown": "таймаут WA (подделка)"}
        d = self.drafts.get(notice_id)
        if d is None:
            return {"absent": True}
        return {"draft_id": d["draft_id"], "state": d["state"], "wamid": d["wamid"]}

    def human_press(self, notice_id):
        """Нажатие человека «отправить» в WA (01.10-1 п.1) — wamid записывается за черновиком."""
        d = self.drafts[notice_id]
        d["wamid"] = "wamid.FAKE%04d" % next(self._wamids)
        d["state"] = "sent"
        self.counters.bump("human_press_sends")
        return d["wamid"]

    def send_to_client(self, *args, **kwargs):
        self.counters.bump("client_sends")
        raise AssertionError("отправка клиенту кодом запрещена (01.10-1 п.1): только нажатием человека")


class FakeDeliveryStatusPort(object):
    """DeliveryStatusPort: status(wamid) → {"status": sent|delivered|read|failed|unknown, "at"} по ТОЧНОМУ wamid."""

    def __init__(self, clock, counters=None):
        self.clock = clock
        self.counters = counters or Counters()
        self.statuses = {}
        self.calls = []

    def status(self, wamid):
        self.calls.append(wamid)
        self.counters.bump("delivery_status_reads")
        st = self.statuses.get(wamid)
        if st is None:
            return {"status": "unknown", "at": None}
        return {"status": st[0], "at": st[1]}


class FakeReplyHandler(object):
    """Шов S5: обработчик реплая зовёт дело ПЕРВЫМ, в своём try, затем staff_ask.on_reply — независимо от исхода.
    `store_call(**поля)` — обёртка над Store.on_staff_answer; `brain_append(line)` → (ok, why) или исключение."""

    def __init__(self, store_call, staff_ask, brain_append):
        self.store_call = store_call
        self.staff_ask = staff_ask
        self.brain_append = brain_append
        self.order = []

    def handle(self, chat, msg_id, reply_to, reply_to_is_bot, thread_id, author_id, author_username, is_bot, text, at):
        case_out, brain_out = None, None
        self.order.append("case")
        try:
            case_out = self.store_call(chat=chat, msg_id=msg_id, reply_to=reply_to, reply_to_is_bot=reply_to_is_bot,
                                       thread_id=thread_id, author_id=author_id, author_username=author_username,
                                       is_bot=is_bot, text=text, at=at,
                                       by={"kind": "staff", "id": author_id, "name": author_username or ""})
        except Exception as e:                                           # noqa: BLE001
            case_out = {"error": type(e).__name__}
        self.order.append("brain")
        try:
            brain_out = self.staff_ask.on_reply(self.brain_append, chat=chat, reply_to=reply_to, mid=msg_id,
                                                user_id=author_id, username=author_username, is_bot=is_bot,
                                                text=text, ts=at)
        except Exception as e:                                           # noqa: BLE001
            brain_out = {"error": type(e).__name__}
        return case_out, brain_out
