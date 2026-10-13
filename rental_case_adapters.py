# -*- coding: utf-8 -*-
"""rental_case_adapters.py — тонкие порты дела аренды К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910), CONTRACT §9.1.

Каждый порт получает ГОТОВЫЙ внешний объект (или функцию) аргументом и только переводит его ответ в форму контракта:
решений не принимает, в rc_* не пишет (единственный писатель — rental_case.Store, I23), сам в сеть не ходит и
ничего из прода не импортирует. Разрешённые импорты (§9.1): stdlib, wa_agent_tools, wa_book_read, bike_position
(только events_from_items, лениво), rental_case_rules. Исключение или таймаут обёрнутого объекта → {"unknown": "<тип>"}
(у портов с полем ok — {"ok": False, "unknown": "<тип>"}), никогда «refused» и без повтора (I43, I15).

Сопоставление с готовыми путями кандидата f2f7295 — CONTRACT §9.0: дверь clients (bridge_client.py:724) и снимок WA
(wa_book_read.py:222-261) → RentalSource; staff_ask.ask/escalate по шву S1/S4 (§13) → StaffAskPort/EscalationPort;
касса tx_find → wa_agent_tools.cash_result (wa_agent_tools.py:126-162) → CashPort; реестр contract_find →
wa_agent_tools.contract_result (:257-291) → ContractPort; contract_pdf → pdf_result (:294-306) → PdfPort; лист
закрытия и лист «состояние_байка» — в К4 ТОЛЬКО подделки (closing_get и state_get — POST, могут создать лист);
события байка → BikeEventsPort (ref живой порт не даёт, bike_position.py:206-232); статусы WA → DeliveryStatusPort.

Основания версии (§8.4, F2 К3): observed_at, отдаваемый портами, — время НАШЕГО чтения (начало чтения двери или
snapshot.taken_at как есть), а не версия листа; поле версии внешнего источника порты не выдумывают.
"""

import datetime
import re
from typing import Any, Callable, Collection, Dict, List, Mapping, Optional, Sequence

import rental_case_rules as R
import wa_agent_tools as WT
import wa_book_read as WB

CLIENTS_SOURCE = "лист «клиенты» (clients filter=all)"
SNAPSHOT_SOURCE = "снимок броней WA (wa_book_read.Snapshot)"
STATE_SOURCE = "состояние_байка"
EVENTS_SOURCE = "события байка (read_events)"


def _unknown(exc, with_ok=True):
    name = type(exc).__name__ if isinstance(exc, BaseException) else str(exc)
    return {"ok": False, "unknown": name} if with_ok else {"unknown": name}


def _s(value):
    return "" if value is None else str(value).strip()


def _local_epoch(value, tz_h=7):
    """'yyyy-MM-dd HH:mm' в зоне +tz_h → секунды эпохи | None (wa_book_read.moment_of)."""
    m = WB.moment_of(value)
    if m is None:
        return None
    return m.replace(tzinfo=datetime.timezone.utc).timestamp() - tz_h * 3600


# ---------------------------------------------------------------------------------------------------------------------
# Чтение броней
# ---------------------------------------------------------------------------------------------------------------------


class RentalSource(object):
    """Строки двери `clients` с временем НАШЕГО чтения: read() → {ok, rows, observed_at, read_at, source, error}."""

    def __init__(self, reader, *, source_name, clock):
        self.reader = reader
        self.source_name = source_name
        self.clock = clock
        self._snapshot = None

    def read(self):
        t0 = self.clock()
        if self._snapshot is not None:
            return self._read_snapshot(t0)
        try:
            resp = self.reader()
        except Exception as e:                                   # noqa: BLE001 — отказ двери ≠ «броней нет»
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": "unknown:%s" % type(e).__name__, "unknown": type(e).__name__}
        rows = resp if isinstance(resp, list) else WB.rows_of(resp)
        if rows is None:
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": "дверь clients не дала строк"}
        return {"ok": True, "rows": [dict(r) for r in rows if isinstance(r, Mapping)], "observed_at": t0,
                "read_at": self.clock(), "source": self.source_name, "error": ""}

    def _read_snapshot(self, t0):
        snap = self._snapshot
        try:
            rows, _bikes, _age, why = snap.get(t0)
        except Exception as e:                                   # noqa: BLE001
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": "unknown:%s" % type(e).__name__, "unknown": type(e).__name__}
        taken = getattr(snap, "taken_at", None)
        if rows is None or taken is None:
            return {"ok": False, "rows": None, "observed_at": None, "read_at": t0, "source": self.source_name,
                    "error": why or "снимок не готов"}
        return {"ok": True, "rows": [dict(r) for r in rows if isinstance(r, Mapping)], "observed_at": taken,
                "read_at": t0, "source": self.source_name, "error": ""}

    @staticmethod
    def from_bridge(bridge, clock):
        """clients(filter="all"); observed_at = время НАЧАЛА нашего чтения (bridge_client.py:724)."""
        return RentalSource(lambda: bridge.clients(filter="all"), source_name=CLIENTS_SOURCE, clock=clock)

    @staticmethod
    def from_snapshot(snapshot, clock):
        """snapshot.get(now); observed_at = snapshot.taken_at КАК ЕСТЬ (wa_book_read.py:222-261), не now − age."""
        src = RentalSource(None, source_name=SNAPSHOT_SOURCE, clock=clock)
        src._snapshot = snapshot
        return src


# ---------------------------------------------------------------------------------------------------------------------
# staff_ask (шов S1/S4), карточки одобряющего
# ---------------------------------------------------------------------------------------------------------------------

_ROLE_OF_PLACE = (("topic", "question"), ("delivery", "delivery"), ("agents", "agents"))


def _role_of(place, escalation=False):
    if escalation:
        return "escalation"
    for p, r in _ROLE_OF_PLACE:
        if p == place:
            return r
    return "question"


def s1_result(resp, at, escalation=False):
    """Ответ staff_ask (S1/S4) → форма порта: posts непуст → {"posted", "qid"}; refusal → {"refused"}; deduped →
    {"deduped": qid}; иначе (пусто без кода, unknown_places) → {"unknown": why}. Повтора нет (CONTRACT §9.1)."""
    r = resp if isinstance(resp, Mapping) else {}
    posts = r.get("posts") or []
    if posts:
        return {"posted": [{"place": p.get("place"), "chat": p.get("chat"), "msg_id": p.get("msg_id"),
                            "thread_id": p.get("thread_id"), "role": _role_of(p.get("place"), escalation), "at": at}
                           for p in posts if isinstance(p, Mapping)], "qid": r.get("qid")}
    if r.get("refusal"):
        return {"refused": r.get("refusal")}
    if r.get("deduped"):
        return {"deduped": r.get("qid")}
    return {"unknown": _s(r.get("why")) or "посты пусты без кода отказа"}


def _subject(exp):
    s = (exp or {}).get("subject")
    return s if isinstance(s, Mapping) else {}


class StaffAskPort(object):
    """staff_ask.ask по шву S1 (async). Чаты и тема байка — от вызывающего (К5)."""

    def __init__(self, ask, send, *, clock, servicing_chat=None, delivery_chat=None, agents_chat=None,
                 topic_of=None):
        self.ask = ask
        self.send = send
        self.clock = clock
        self.servicing_chat = servicing_chat
        self.delivery_chat = delivery_chat
        self.agents_chat = agents_chat
        self.topic_of = topic_of

    async def post(self, exp):
        s = _subject(exp)
        bike = s.get("bike") or (exp or {}).get("bike") or ""
        try:
            topic_id = self.topic_of(bike) if callable(self.topic_of) else None
            r = await self.ask(self.send, kind=s.get("staff_kind"), bike=bike, q_ru=s.get("q_ru"), q_th=s.get("q_th"),
                               urgency=s.get("urgency"), servicing_chat=self.servicing_chat, topic_id=topic_id,
                               delivery_chat=self.delivery_chat, agents_chat=self.agents_chat,
                               case_id=(exp or {}).get("case_id"), case_ver=(exp or {}).get("case_ver"),
                               expect_id=(exp or {}).get("exp_id"))
        except Exception as e:                                   # noqa: BLE001 — таймаут/исключение → unknown, без повтора
            return _unknown(e, with_ok=False)
        return s1_result(r, self.clock())


class EscalationPort(object):
    """staff_ask.escalate по шву S4 (async): та же форма, role=escalation."""

    def __init__(self, escalate, send, *, agents_chat, clock, why="решение одобряющего"):
        self.escalate_fn = escalate
        self.send = send
        self.agents_chat = agents_chat
        self.clock = clock
        self.why = why

    async def escalate(self, exp):
        qid = (exp or {}).get("ext_qid") or (exp or {}).get("qid")
        try:
            r = await self.escalate_fn(qid, self.send, agents_chat=self.agents_chat, why=self.why)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e, with_ok=False)
        return s1_result(dict(r or {}, qid=qid), self.clock(), escalation=True)


class ApprovalPort(object):
    """Карточка/вопрос confirm_link во «Входящие» (async): send(chat, text) → msg_id | None."""

    def __init__(self, send, *, chat, clock, place="intake", render=None):
        self.send = send
        self.chat = chat
        self.clock = clock
        self.place = place
        self.render = render

    async def post_card(self, exp):
        chat = (exp or {}).get("chat") or self.chat
        s = _subject(exp)
        text = self.render(exp) if callable(self.render) else (s.get("text") or s.get("question") or "")
        try:
            mid = await self.send(chat, text)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e, with_ok=False)
        if mid is None:
            return {"unknown": "карточка не принята (исход отправки неизвестен)"}
        return {"posted": [{"place": self.place, "chat": chat, "msg_id": str(mid), "thread_id": None,
                            "role": "card", "at": self.clock()}], "qid": None}


# ---------------------------------------------------------------------------------------------------------------------
# Касса, договоры, PDF
# ---------------------------------------------------------------------------------------------------------------------


# Отмена строки кассы — то же правило, что у cash_result кандидата (wa_agent_tools.py:93 `_CANCEL`), а не своё.
_CASH_CANCEL = getattr(WT, "_CANCEL", None) or re.compile(r"void|отмен|cancel", re.I)


def cash_fkey(fact):
    """Тождество факта кассы (CONTRACT §8.2): ["cash", src, row, msg_id|link]."""
    return ["cash", _s(fact.get("src")) or "tx_find", fact.get("row"), fact.get("msg_id") or fact.get("link") or ""]


class CashPort(object):
    """tx_find → wa_agent_tools.cash_result + {"window", "complete", "keys", "cancelled"} (§9.1)."""

    def __init__(self, bridge, clock):
        self.bridge = bridge
        self.clock = clock

    def find(self, *, booking_id="", bike="", date_from="", date_to=""):
        at = self.clock()
        try:
            resp = self.bridge.tx_find(bike=bike, booking_id=booking_id, date_from=date_from, date_to=date_to)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        res = dict(WT.cash_result(resp, at))
        checked = (resp or {}).get("checked") if isinstance(resp, Mapping) else None
        checked = checked if isinstance(checked, Mapping) else {}
        plate = WT.plate_of(bike) if _s(bike) else ""
        cancelled = []
        for it in (resp or {}).get("items") or [] if isinstance(resp, Mapping) else []:
            if isinstance(it, Mapping) and _CASH_CANCEL.search(_s(it.get("status"))):
                cancelled.append(cash_fkey({"src": "tx_find", "row": it.get("row"), "msg_id": it.get("msg_id"),
                                            "link": it.get("link")}))
        res["window"] = {"booking_id": booking_id or "", "bike": bike or "", "plate": plate, "date_from": date_from,
                         "date_to": date_to, "span_from": checked.get("span_from"), "span_to": checked.get("span_to")}
        res["complete"] = checked.get("complete") is True and not checked.get("truncated")
        res["keys"] = [cash_fkey(f) for f in res.get("facts") or []]
        res["cancelled"] = cancelled
        return res


def as_rental_result(binding):
    """Привязка дела (или строка двери) → результат инструмента `rental` (FACT) для bind_contract."""
    if isinstance(binding, Mapping) and "outcome" in binding:
        return dict(binding)
    b = dict(binding or {})
    fact = {"kind": "rental", "booking_id": _s(b.get("booking_id")) or None,
            "bike": b.get("bike_name") or b.get("bike") or b.get("plate"),
            "date_start": b.get("start_at") or b.get("date_start") or b.get("start_day"),
            "date_end": b.get("end_at") or b.get("date_end") or b.get("end_day"),
            "status": b.get("status_seen") or b.get("status"), "price": None, "currency": "THB"}
    return WT.result("rental", WT.FACT, "дело аренды (rental_case): привязка", ref=_s(fact["booking_id"]),
                     window="%s…%s" % (fact["date_start"], fact["date_end"]), facts=[fact])


class ContractPort(object):
    """contract_find → wa_agent_tools.contract_result(resp, at, number, rental=as_rental_result(rental))."""

    def __init__(self, bridge, clock):
        self.bridge = bridge
        self.clock = clock

    def find(self, *, number, rental, phone="", bike="", date_from="", date_to=""):
        at = self.clock()
        try:
            resp = self.bridge.contract_find(phone=phone, bike=bike, date_from=date_from, date_to=date_to)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        return WT.contract_result(resp, at, number=number, rental=as_rental_result(rental))


class PdfPort(object):
    """contract_pdf → wa_agent_tools.pdf_result(resp, at, allowed) (PDF только принятого договора)."""

    def __init__(self, bridge, clock):
        self.bridge = bridge
        self.clock = clock

    def fetch(self, file_id, *, allowed=()):
        at = self.clock()
        try:
            resp = self.bridge.contract_pdf(file_id)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        return WT.pdf_result(resp, at, allowed=allowed)


# ---------------------------------------------------------------------------------------------------------------------
# Лист закрытия и «состояние_байка» — в К4 только подделки (§9.1); события байка
# ---------------------------------------------------------------------------------------------------------------------


class ClosingPort(object):
    """Лист закрытия ТОЛЬКО по booking_id: get(booking_id) → {"ok": True, "item"} | {"ok": False, "error"} |
    {"ok": False, "unknown"}. В К4 getter — подделка: живой closing_get — POST и создаёт лист."""

    def __init__(self, getter, clock=None):
        self.getter = getter
        self.clock = clock

    def get(self, booking_id):
        if not _s(booking_id):
            return {"ok": False, "error": "no_key"}
        try:
            resp = self.getter(booking_id)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        if isinstance(resp, Mapping) and resp.get("ok") and isinstance(resp.get("item"), Mapping):
            return {"ok": True, "item": dict(resp["item"])}
        if isinstance(resp, Mapping) and resp.get("error"):
            return {"ok": False, "error": _s(resp.get("error"))}
        return {"ok": False, "unknown": "ответ без ok"}


class StatePort(object):
    """Лист «состояние_байка»: get(bike) → {"ok": True, "item", "observed_at": <updated>, "read_at", "source"} |
    {"ok": False, "absent": True} | {"ok": False, "unknown"}. В К4 getter — подделка (state_get — POST, getBotTab_
    создаёт лист). Дальше — rules.bike_state_fact → Store.record_fact(kind="bike_state", scope="case")."""

    def __init__(self, getter, clock, tz_h=7):
        self.getter = getter
        self.clock = clock
        self.tz_h = tz_h

    def get(self, bike):
        try:
            resp = self.getter(bike)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        if not (isinstance(resp, Mapping) and resp.get("ok")):
            if isinstance(resp, Mapping) and resp.get("error") == "not_found":
                return {"ok": False, "absent": True}
            return {"ok": False, "unknown": _s((resp or {}).get("error") if isinstance(resp, Mapping) else "")
                    or "ответ без ok"}
        item = dict(resp.get("item") or {})
        return {"ok": True, "item": item, "observed_at": _local_epoch(item.get("updated"), self.tz_h),
                "read_at": self.clock(), "source": STATE_SOURCE}


class BikeEventsPort(object):
    """События байка: events(bike, limit) → {"ok": True, "items": [{type, at, ref}]}. Сырые строки read_events
    переводит bike_position.events_from_items (ref живой порт не даёт → "", ступень по нему — evidence_missing)."""

    def __init__(self, reader, clock=None):
        self.reader = reader
        self.clock = clock

    def events(self, bike, limit=30):
        try:
            items = self.reader(bike, limit)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e)
        if isinstance(items, Mapping):
            items = items.get("items") or []
        items = [it for it in items or [] if isinstance(it, Mapping)]
        if items and "event_type" in items[0]:
            import bike_position                                 # лениво: только events_from_items (§9.1)
            norm = bike_position.events_from_items(items)
            return {"ok": True, "items": [{"type": e.get("type"), "at": e.get("at"), "ref": ""} for e in norm]}
        return {"ok": True, "items": [{"type": it.get("type"), "at": it.get("at"), "ref": _s(it.get("ref"))}
                                      for it in items][:limit]}


# ---------------------------------------------------------------------------------------------------------------------
# Чтение назад, место результата, WA
# ---------------------------------------------------------------------------------------------------------------------


class CrmReadback(object):
    """Чтение назад строки CRM после красного шага: row_status(target) → {"outcome": landed|absent|unknown, "row",
    "status", "read_at", "observed_at", "siblings": [{row, booking_id, status_old, status_new}]} — все строки того же
    байк+имя (I-19). target = {booking_id | row, status (ожидаемый), siblings_before?: {row: status}}."""

    def __init__(self, source):
        self.source = source

    def row_status(self, *, target):
        t = dict(target or {})
        rd = self.source.read()
        base = {"outcome": "unknown", "row": None, "status": None, "read_at": rd.get("read_at"),
                "observed_at": rd.get("observed_at"), "siblings": []}
        if not rd.get("ok"):
            base["error"] = rd.get("error")
            return base
        rows = rd.get("rows") or []
        bk, rn = _s(t.get("booking_id")), t.get("row")
        hits = [r for r in rows if (bk and _s(r.get("booking_id")) == bk) or (not bk and rn is not None
                                                                              and r.get("row") == rn)]
        if len(hits) != 1:
            base["outcome"] = "absent" if (bk and not hits) else "unknown"
            return base
        r = hits[0]
        want = _s(t.get("status")).lower()
        base.update(row=r.get("row"), status=r.get("status"),
                    outcome="landed" if want and WB.status_of(r) == want else "absent")
        before = t.get("siblings_before") if isinstance(t.get("siblings_before"), Mapping) else {}
        plate, nm = R.plate_of_row(r), R.name_norm(r.get("name"))
        for s in rows:
            if s is r or R.plate_of_row(s) != plate or R.name_norm(s.get("name")) != nm:
                continue
            old = before.get(str(s.get("row")), before.get(s.get("row")))
            base["siblings"].append({"row": s.get("row"), "booking_id": _s(s.get("booking_id")) or None,
                                     "status_old": old, "status_new": s.get("status")})
        return base


class ResultSink(object):
    """Протокол места записи результата (RESULT_RECORD_PLACE): write(task, value) → {"ok"} | {"unknown"};
    read(task) → {"outcome": landed|absent|unknown, "read_at"}. Обёртка над функциями вызывающего."""

    def __init__(self, write_fn=None, read_fn=None, clock=None):
        self.write_fn = write_fn
        self.read_fn = read_fn
        self.clock = clock

    def write(self, task, value):
        if not callable(self.write_fn):
            return {"unknown": "место записи не подключено (RESULT_RECORD_PLACE)"}
        try:
            r = self.write_fn(task, value)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e, with_ok=False)
        return {"ok": True} if (r is True or (isinstance(r, Mapping) and r.get("ok") is True)) else \
            {"unknown": _s((r or {}).get("unknown") if isinstance(r, Mapping) else r) or "запись не подтверждена"}

    def read(self, task):
        t = self.clock() if callable(self.clock) else None
        if not callable(self.read_fn):
            return {"outcome": "unknown", "read_at": t}
        try:
            r = self.read_fn(task)
        except Exception as e:                                   # noqa: BLE001
            return {"outcome": "unknown", "read_at": t, "unknown": type(e).__name__}
        r = dict(r or {}) if isinstance(r, Mapping) else {}
        if r.get("outcome") not in ("landed", "absent", "unknown"):
            r["outcome"] = "unknown"
        r.setdefault("read_at", t)
        return r


class NoticePort(object):
    """Протокол WA-ядра для уведомления клиента (клиенту — только нажатием человека, 01.10-1 п.1):
    propose(notice_id, case_id, case_ver, intent, facts) → {"draft_id"} | {"unknown"} (идемпотентен по notice_id);
    find(notice_id) → {"draft_id", "state", "wamid"} | {"absent": True} | {"unknown"}."""

    def __init__(self, propose_fn, find_fn):
        self.propose_fn = propose_fn
        self.find_fn = find_fn

    def propose(self, *, notice_id, case_id, case_ver, intent, facts):
        try:
            r = self.propose_fn(notice_id=notice_id, case_id=case_id, case_ver=case_ver, intent=intent,
                                facts=list(facts or []))
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e, with_ok=False)
        if isinstance(r, Mapping) and isinstance(r.get("draft_id"), int) and not isinstance(r.get("draft_id"), bool):
            return {"draft_id": r["draft_id"]}
        return {"unknown": _s((r or {}).get("unknown") if isinstance(r, Mapping) else r) or "черновик не подтверждён"}

    def find(self, notice_id):
        try:
            r = self.find_fn(notice_id)
        except Exception as e:                                   # noqa: BLE001
            return _unknown(e, with_ok=False)
        if not isinstance(r, Mapping):
            return {"unknown": "ответ не словарь"}
        if r.get("absent"):
            return {"absent": True}
        if "draft_id" in r:
            return {"draft_id": r.get("draft_id"), "state": r.get("state"), "wamid": r.get("wamid")}
        return {"unknown": _s(r.get("unknown")) or "черновик не найден однозначно"}


class DeliveryStatusPort(object):
    """Статус доставки по ТОЧНОМУ wamid (part_status, wa_agent_attach.py:145-180): {"status", "at"}."""

    STATUSES = ("sent", "delivered", "read", "failed", "unknown")

    def __init__(self, status_fn):
        self.status_fn = status_fn

    def status(self, wamid):
        try:
            r = self.status_fn(wamid)
        except Exception as e:                                   # noqa: BLE001
            return {"status": "unknown", "at": None, "unknown": type(e).__name__}
        r = dict(r or {}) if isinstance(r, Mapping) else {}
        st = _s(r.get("status")).lower()
        return {"status": st if st in self.STATUSES else "unknown", "at": r.get("at")}
