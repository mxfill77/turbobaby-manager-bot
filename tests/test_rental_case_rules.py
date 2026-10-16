#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""К4 — проверки чистых правил `rental_case_rules` чёрным ящиком строго по out/CONTRACT_K4.md.

Источник истины — CONTRACT_K4 (ревизия 2 + полнота 1 + синхронизация + дозакрытие покрытия; sha256 b37a3695…,
out/DESIGN_FREEZE.txt); приёмка и мутанты — DESIGN_K4 §13, критерии — DESIGN_K4 §15. Код реализации при написании
не читался: проверяются исходы §6, коды причин §12, «unknown всегда с непустыми missing и ask» (К4-C5), классы §3.1,
запреты выбора (I17, К4-C4, К4-C25), слова §4.8 (I39), порядок вердиктов §4.7 (I9), bind_cash с претендентами (I35),
раздельные вердикты документа — принадлежность и покрытие периода (I46, К4-C39), fail-closed при UNKNOWN (I16, §10).

Форма входов. Контракт §6 называет входы правил `Mapping` без перечня ключей (кроме частей case_view §8.4, строк
хранилища §2 и строк двери clients). Здесь входы строятся из колонок схемы §2 (rc_case, rc_rental, rc_expect, rc_post,
rc_answer, rc_task, rc_document, rc_obligation), частей §8.4 и строк двери `clients`
(f2f7295:bridge_prod/ReadClients.js:95-121). Где контракт ключ не называет (номер текущей привязки у дела, boot_id
принимающего Store), даётся надмножество ключей — см. построители «ФОРМА ВХОДОВ» ниже: расхождение формы правится
там, в одном месте, а не в каждой проверке.

Запуск: `python tests/test_rental_case_rules.py` (код выхода ≠ 0 при провале) или раннером
tests/run_rental_case_suites.py. Сеть запрещена (socket.socket подменён в tests/rental_case_fakes.py; если его нет —
запасная подмена здесь же). Базы, файлов на запись, часов и окружения проверки не трогают.
"""

import ast
import copy
import datetime
import inspect
import itertools
import json
import os
import re
import socket
import sys
import textwrap
import time
import unittest
from typing import Any, Dict, List, Mapping, Optional
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_ORIG_SOCKET = socket.socket
try:
    import rental_case_fakes  # noqa: F401  — подмена socket.socket (CONTRACT §9.1 «Подделки»)
except ImportError:  # файл подделок пишет другой шаг; без него — запасная подмена ниже
    rental_case_fakes = None

if socket.socket is _ORIG_SOCKET:
    class _NoNetSocket(_ORIG_SOCKET):
        def __init__(self, *args, **kwargs):  # noqa: D401
            raise RuntimeError("К4: сеть в тестах запрещена (I20, К4-C18)")

    socket.socket = _NoNetSocket

import rental_case_rules as R  # noqa: E402

# ----------------------------------------------------------------------------------------------------------------
# Перечни контракта
# ----------------------------------------------------------------------------------------------------------------

UNKNOWN = "UNKNOWN"   # CONTRACT §10: UNKNOWN = "UNKNOWN"

REASONS = frozenset("""
case_not_found case_closed case_cancelled booking_taken anchor_taken no_plate no_start rental_not_found
rental_ambiguous two_active stale_active possible_continuation link_drift link_missing stale_read drift_bike
drift_start drift_name phone_clash contact contact_superseded contact_source attention pause_mismatch bad_transition
expect_state not_reply not_linked evidence_forbidden evidence_foreign evidence_missing order readback_mismatch
not_delivered blockers obligation_missing closing_fact_invalid notice_inflight approver_unknown approver_foreign
param_unknown feed_unknown no_thai cash_other_booking cash_pre_start cash_post_end cash_no_rental which_rental
role_unknown contract_pre_start doc_conflict doc_unknown doc_foreign_rental sha_missing pdf_not_of_contract deduped
store_busy idem_payload_mismatch task_cancelled internal doc_period_not_covered doc_period_unknown doc_ambiguous
second_source_missing doc_cover_invalid doc_cover_set period_not_given
""".split())
# §4.1, §5.1, §6 (bind_cash, resolve) называют исход unknown(link_confirmation), а перечень REASONS §12 этого кода не
# содержит (он есть только в MISSING). Расхождение контракта названо в отчёте шага; здесь код допускается причиной.
REASONS_OK = REASONS | {"link_confirmation"}

MISSING = frozenset("""
intent booking_id dates bike contact which_rental link_confirmation continuation addressee acceptance_signal
done_source record_place approver ttl business_hours payment_place feed retry document_period second_source period
""".split())

PARAM_NAMES = frozenset("""
TZ_H APPROVAL_TTL_S MAX_POST_ATTEMPTS STAFF_PLACES OWNER_IDS APPROVER_IDS STAFF_ADDRESSEES APPROVAL_REPLY_REQUIRED
APPROVAL_YES_WORDS APPROVAL_YES_STEMS APPROVAL_NO_STEMS APPROVAL_NO_AFTER_NE ACCEPTANCE_SIGNAL ACCEPT_WORDS
ACCEPT_NO_STEMS KEY_DIGITS BUSINESS_HOURS STAFF_REMIND_AFTER WAIT_BEFORE_AGENTS ESCALATION_STEP2 ANSWER_TTL
LATE_ANSWER_ROUTE PHYSICAL_DONE_SOURCES RESULT_RECORD_PLACE CASE_ON_INTERVENTION PAUSE_DURATION PAUSE_RELEASER
NON_WA_MEDIA_EXEMPT FINAL_NOTICE_REQUIRED FEEDS_CONNECTED NEW_REQUEST_RULE AUTO_ASK STALE_ACTIVE_DAYS
CONTINUATION_GAP_DAYS MONEY_CLOSE_RULE HANDOVER_DAY_TOLERANCE CASH_PRE_START_DAYS CASH_POST_END_DAYS
CONTRACT_PRE_START_DAYS PAST_LOOKBACK AUTO_CANCEL_B_MEANING TG_CONTACT_MATCH CASH_ROLE_MULTI_MOVE RENTAL_CONFLICT_RULE
BOOKING_ID_ORIGIN PAYMENT_RECORD_PLACE CANCEL_RECORD_PLACE CANCEL_PREPAY EXTENSION_NEXT_BOOKING EXTENSION_PAY_WHEN
CURRENCY_RATE SMALL_CHANGE_MAX PASSPORT_DEPOSIT_RETURN_RECORD CLOSING_K_SEMANTICS DAMAGE_RULE DELIVERY_ASSIGNEE
""".split())

# имена §10, у которых по умолчанию UNKNOWN целиком
FAIL_CLOSED_NAMES = (
    "APPROVAL_REPLY_REQUIRED", "ACCEPTANCE_SIGNAL", "ACCEPT_WORDS", "ACCEPT_NO_STEMS", "BUSINESS_HOURS",
    "STAFF_REMIND_AFTER", "WAIT_BEFORE_AGENTS", "ESCALATION_STEP2", "ANSWER_TTL", "LATE_ANSWER_ROUTE",
    "CASE_ON_INTERVENTION", "PAUSE_DURATION", "PAUSE_RELEASER", "NON_WA_MEDIA_EXEMPT", "FINAL_NOTICE_REQUIRED",
    "NEW_REQUEST_RULE", "AUTO_ASK", "STALE_ACTIVE_DAYS", "CONTINUATION_GAP_DAYS", "MONEY_CLOSE_RULE",
    "HANDOVER_DAY_TOLERANCE", "CASH_PRE_START_DAYS", "CASH_POST_END_DAYS", "CONTRACT_PRE_START_DAYS", "PAST_LOOKBACK",
    "AUTO_CANCEL_B_MEANING", "TG_CONTACT_MATCH", "CASH_ROLE_MULTI_MOVE", "RENTAL_CONFLICT_RULE", "BOOKING_ID_ORIGIN",
    "PAYMENT_RECORD_PLACE", "CANCEL_RECORD_PLACE", "CANCEL_PREPAY", "EXTENSION_NEXT_BOOKING", "EXTENSION_PAY_WHEN",
    "CURRENCY_RATE", "SMALL_CHANGE_MAX", "PASSPORT_DEPOSIT_RETURN_RECORD", "CLOSING_K_SEMANTICS", "DAMAGE_RULE",
    "DELIVERY_ASSIGNEE",
)

OWNER_IDS = frozenset((504608015, 6879003264, 5466425480))
TASK_KINDS = ("readiness", "delivery", "handover", "return", "pickup", "other")
YES_WORDS = ("да", "ок")
YES_STEMS = ("подтвержд", "заверш", "закрывай", "активируй", "ставь")
NO_STEMS = ("нет", "отмена", "отклон")
NO_AFTER_NE = ("актив", "заверш", "закрыв", "став")

CLASSES = frozenset(("current", "current_unactivated", "future", "past", "stale_booking", "unknown"))
FLAGS = frozenset(("overdue", "auto_cancel_on", "manual_status", "no_dates", "phone_clash", "stub_name"))
STAGES = ("question_sent", "answer_received", "task_accepted", "physically_done", "result_recorded",
          "client_notified")
VERDICTS = frozenset((
    "accepted", "reference_author_unverified", "reference_foreign_author", "reference_foreign_place",
    "reference_drift", "reference_stale_version", "reference_expired", "reference_late", "reference_superseded",
    "reference_cancelled", "reference_answered", "reference_unclear", "reference_no_reply", "reference_restart"))


def _contract_params() -> Dict[str, Any]:
    """PARAMS_DEFAULT ровно по таблице CONTRACT §10 (формы — как названы в столбце «тип»)."""
    p = {name: UNKNOWN for name in FAIL_CLOSED_NAMES}   # type: Dict[str, Any]
    p.update({
        "TZ_H": 7,
        "APPROVAL_TTL_S": {"activate": 1800, "close": 1800, "booking": UNKNOWN},
        "MAX_POST_ATTEMPTS": 1,
        "STAFF_PLACES": {"байк": ["topic", "delivery"], "цена": ["agents"], "бронь": ["agents"],
                         "сложность": ["agents"]},
        "OWNER_IDS": OWNER_IDS,
        "APPROVER_IDS": OWNER_IDS,
        "STAFF_ADDRESSEES": {"topic": UNKNOWN, "delivery": UNKNOWN, "agents": UNKNOWN},
        "APPROVAL_YES_WORDS": YES_WORDS,
        "APPROVAL_YES_STEMS": YES_STEMS,
        "APPROVAL_NO_STEMS": NO_STEMS,
        "APPROVAL_NO_AFTER_NE": NO_AFTER_NE,
        "KEY_DIGITS": 9,
        "PHYSICAL_DONE_SOURCES": {k: UNKNOWN for k in TASK_KINDS},
        "RESULT_RECORD_PLACE": {"handover": "crm:в аренде", "return": "crm:завершена", "readiness": UNKNOWN,
                                "delivery": UNKNOWN, "pickup": UNKNOWN, "other": UNKNOWN},
        "FEEDS_CONNECTED": frozenset(),
    })
    return p


def _impl_params_default():
    """PARAMS_DEFAULT реализации (CONTRACT §10/DESIGN §9: в rental_case.py; допускаем и rental_case_rules)."""
    for modname in ("rental_case_rules", "rental_case"):
        try:
            mod = __import__(modname)
        except Exception:  # noqa: BLE001 — модуль хранилища может отсутствовать на шаге проверки правил
            continue
        pd = getattr(mod, "PARAMS_DEFAULT", None)
        if isinstance(pd, Mapping):
            return modname, pd
    return None, None


IMPL_PD_MOD, IMPL_PD = _impl_params_default()

# Параметры проверок: лишние ключи реализации сохраняются, значения имён §10 — строго по контракту
# (правила судятся контрактом, а не умолчаниями реализации; сами умолчания судит TestParamsDefault).
PD = dict(IMPL_PD or {})
PD.update(_contract_params())


def params(**over) -> Dict[str, Any]:
    p = dict(PD)
    p.update(over)
    return p


# синтетика (вариант А CONTRACT §14) — одобряющий 1001, адресаты тем 9001/9002
PS = params(APPROVER_IDS=frozenset({1001}),
            STAFF_ADDRESSEES={"topic": frozenset({9001}), "delivery": frozenset({9002}), "agents": frozenset({9003})})
PS_FEEDS = dict(PS, FEEDS_CONNECTED=frozenset({"intervention", "inbound"}))

# ----------------------------------------------------------------------------------------------------------------
# Время и строки двери clients (формат f2f7295:bridge_prod/ReadClients.js:95-121; даты 'yyyy-MM-dd HH:mm' | None)
# ----------------------------------------------------------------------------------------------------------------

TZ7 = datetime.timezone(datetime.timedelta(hours=7))


def ts(y, m, d, hh=12, mm=0) -> float:
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ7).timestamp()


MOMENT = ts(2026, 10, 9, 12, 0)          # момент демо-случая §14: 09.10.2026 12:00 (+7)
T_OBS = ts(2026, 10, 9, 11, 0)           # применённое чтение привязки
T_NEW = ts(2026, 10, 9, 12, 0)           # новое чтение

IVAN_PHONE, IVAN_NUM = "+66 81 234 5678", "66812345678"
BORIS_PHONE, BORIS_NUM = "+66 89 765 4321", "66897654321"
ANNA_PHONE, ANNA_NUM = "+66 86 111 2233", "66861112233"
OLEG_PHONE, OLEG_NUM = "+66 83 333 4455", "66833334455"
KIRA_PHONE, KIRA_NUM = "+66 84 444 5566", "66844445566"
PETR_PHONE = "+66 80 555 0000"

C_IVAN = {"channel": "wa", "value": IVAN_NUM}
C_BORIS = {"channel": "wa", "value": BORIS_NUM}
C_ANNA = {"channel": "wa", "value": ANNA_NUM}
C_KIRA = {"channel": "wa", "value": KIRA_NUM}


def _day(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    return datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))


def mk_row(row, status, bike, name, start, end, contacts="", booking_id="", deposit_raw="", debt=0, to_pay=0,
           paid=0, auto_cancel="", pay_per_day=0, note="") -> Dict[str, Any]:
    """Строка двери clients как её отдаёт ReadClients.js:95-121 (флаги двери — на момент чтения MOMENT)."""
    try:
        deposit = float(deposit_raw)
    except (TypeError, ValueError):
        deposit = 0
    is_active = status == "В аренде" and auto_cancel != "ON"
    end_d = _day(end)
    overdue = bool(is_active and end_d is not None and end_d < datetime.date(2026, 10, 9))
    return {"row": row, "status": status, "auto_cancel": auto_cancel, "bike": bike, "name": name,
            "date_start": start, "date_end": end, "duration": "", "pay_per_day": pay_per_day, "debt": debt,
            "to_pay": to_pay, "paid": paid, "deposit": deposit, "deposit_raw": deposit_raw, "helmets": "",
            "contacts": contacts, "note": note, "type": "скутер", "booking_id": booking_id,
            "is_active": is_active, "is_overdue": overdue,
            "days_overdue": (datetime.date(2026, 10, 9) - end_d).days if overdue else 0, "is_fresh": True}


def rv(base: Mapping[str, Any], **kw) -> Dict[str, Any]:
    d = dict(base)
    d.update(kw)
    return d


# фикстура §14: 812 — Иван «В аренде» NMAX 155 6908 01.10–12.10, залог 3000; 845 — Борис «Бронь» тот же байк 15.10–20.10,
# залог passport; номера U разные. Прочие строки — прошлое Ивана, висяки, вторые брони.
R812 = mk_row(812, "В аренде", "NMAX 155 6908", "Иван", "2026-10-01 10:00", "2026-10-12 10:00", IVAN_PHONE,
              "bk-812", "3000")
R845 = mk_row(845, "Бронь", "NMAX 155 6908", "Борис", "2026-10-15 10:00", "2026-10-20 10:00", BORIS_PHONE,
              "bk-845", "passport")
R790 = mk_row(790, "Завершена", "NMAX 155 6908", "Иван", "2026-09-01 10:00", "2026-09-15 10:00", IVAN_PHONE,
              "bk-790", "3000")
R700 = mk_row(700, "В аренде", "PCX 160 4410", "Анна", "2023-05-01 10:00", "2023-05-10 10:00", ANNA_PHONE, "", "")
R860 = mk_row(860, "Бронь", "PCX 160 4410", "Анна", "2026-10-15 10:00", "2026-10-25 10:00", ANNA_PHONE, "bk-860",
              "2000")
R650 = mk_row(650, "В аренде", "NMAX 155 6908", "Пётр", "2023-03-01 10:00", "2023-03-10 10:00", PETR_PHONE, "", "")
R870 = mk_row(870, "В аренде", "ADV 160 5151", "Олег", "2026-10-02 10:00", "2026-10-10 10:00", OLEG_PHONE, "",
              "1000")
ALL_ROWS = [R812, R845, R790, R700, R860, R650]

# ----------------------------------------------------------------------------------------------------------------
# ФОРМА ВХОДОВ (одно место правки, если форма реализации окажется иной)
# ----------------------------------------------------------------------------------------------------------------


class Addr(str):
    """rc_post.addressee_ids: json-строка колонки (§2), при этом `in`/итерация работают как по списку int —
    вход годится и для разбора json.loads, и для прямой проверки членства."""

    def __new__(cls, ids):
        ids = tuple(ids)
        obj = str.__new__(cls, json.dumps(list(ids)))
        obj._ids = ids
        return obj

    def __getnewargs__(self):
        return (self._ids,)

    def __contains__(self, item):
        return item in self._ids

    def __iter__(self):
        return iter(self._ids)


_CC = frozenset(("125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"))   # = plate_of


def _plate_of(text: str) -> str:
    """Копия правила wa_agent_tools.plate_of (последнее число от 3 цифр, не кубатура) — только для фикстур."""
    nums = [n for n in re.findall(r"\d{3,}", str(text or "").lower()) if n not in _CC]
    return nums[-1] if nums else ""


def binding(case_id, rental_id, row, booking_id, contacts, status_seen=None, observed_at=T_OBS):
    """Привязка аренды — колонки rc_rental (§2) + её контакты (rc_contact) для сверки U (§6 reconcile).
    Поля выводятся здесь, а не вызовом правил: фикстура не зависит от проверяемого кода."""
    start_day = row["date_start"][:10] if row.get("date_start") else None
    end_day = row["date_end"][:10] if row.get("date_end") else None
    nn = str(row["name"]).strip().lower()
    nn = None if nn in ("", "—", "-", "?") else nn
    plate = _plate_of(row["bike"])
    anchor = "%s|%s|%s" % (plate, start_day, nn) if (plate and start_day and nn) else None
    days = (_day(end_day) - _day(start_day)).days if (start_day and end_day) else None
    return {"id": rental_id, "rental_id": rental_id, "case_id": case_id, "current": 1,
            "booking_id": booking_id or None, "anchor": anchor, "plate": plate,
            "bike_name": row["bike"], "name_seen": row["name"], "name_norm": nn,
            "start_at": row["date_start"], "end_at": row["date_end"], "start_day": start_day,
            "end_day": end_day, "days": days, "status_seen": status_seen or row["status"],
            "crm_row_seen": row["row"], "row": row["row"], "bound_by": "booking_id" if booking_id else "anchor",
            "observed_at": observed_at, "read_at": observed_at, "source": "лист «клиенты» (clients filter=all)",
            "ref": "строка %s" % row["row"], "method": "door",
            "contacts": [{"channel": "wa", "value": v, "status": "active", "source_kind": "crm"} for v in contacts]}


def mk_case(ver=1, link_state="ok", plate="6908", boot="BOOT-A", state="open") -> Dict[str, Any]:
    """Дело для answer_verdict: колонки rc_case + номер текущей привязки и boot_id принимающего Store
    (контракт их ключей не называет — даём надмножество имён)."""
    rental = {"rental_id": 52, "plate": plate, "bike_name": "NMAX 155 %s" % plate, "booking_id": "bk-845",
              "start_day": "2026-10-15", "end_day": "2026-10-20", "crm_row_seen": 845}
    return {"case_id": "RC-B", "ver": ver, "state": state, "link_state": link_state, "link_exp_id": None,
            "attention": 0, "plate": plate, "current_plate": plate, "rental": dict(rental), "current": dict(rental),
            "binding": dict(rental), "boot_id": boot}


CHAT_TOPIC = "-1001234567890"
CHAT_DELIVERY = "-1009876543210"
CHAT_INBOX = "-1005555555555"
T_POST = ts(2026, 10, 9, 12, 0)


def staff_ctx(exp=None, case=None, post=None, ans=None, boot="BOOT-A"):
    e = {"exp_id": "RE-1", "case_id": "RC-B", "task_id": "RT-1", "kind": "staff_question", "action": None,
         "place": "topic", "chat": CHAT_TOPIC, "state": "waiting", "next_check": "await_answer", "case_ver": 1,
         "claimed_by": "splinter", "claim_boot": "BOOT-A", "parent_exp": None, "post_at": T_POST,
         "waiting_since": T_POST, "business_due_at": None, "due_basis": "none"}
    c = mk_case(boot=boot)
    p = {"chat": CHAT_TOPIC, "msg_id": "7001", "exp_id": "RE-1", "place": "topic", "role": "question",
         "thread_id": "55", "topic_bike": "6908", "addressee_ids": Addr([9001]), "at": T_POST}
    a = {"chat": CHAT_TOPIC, "msg_id": "7010", "reply_to": "7001", "reply_to_is_bot": True, "thread_id": "55",
         "author_id": 9001, "author_username": "staff_9001", "is_bot": False, "text": "พร้อมครับ / готов",
         "at": T_POST + 600, "received_at": T_POST + 601, "boot_id": boot}
    e.update(exp or {})
    c.update(case or {})
    p.update(post or {})
    a.update(ans or {})
    return e, c, p, a


def approval_ctx(action="activate", kind="approval", exp=None, case=None, post=None, ans=None, boot="BOOT-A"):
    e = {"exp_id": "RE-A", "case_id": "RC-B", "task_id": None, "kind": kind,
         "action": action if kind == "approval" else "confirm", "place": "intake", "chat": CHAT_INBOX,
         "state": "waiting", "next_check": "await_answer", "case_ver": 1, "claimed_by": "splinter",
         "claim_boot": "BOOT-A", "parent_exp": None, "post_at": T_POST, "waiting_since": T_POST,
         "cand_sha": "c0ffee" if kind == "confirm_link" else None}
    c = mk_case(boot=boot)
    p = {"chat": CHAT_INBOX, "msg_id": "8001", "exp_id": "RE-A", "place": "intake", "role": "card",
         "thread_id": None, "topic_bike": None, "addressee_ids": Addr([1001]), "at": T_POST}
    a = {"chat": CHAT_INBOX, "msg_id": "8010", "reply_to": "8001", "reply_to_is_bot": True, "thread_id": None,
         "author_id": 1001, "author_username": "owner", "is_bot": False, "text": "да", "at": T_POST + 60,
         "received_at": T_POST + 61, "boot_id": boot}
    e.update(exp or {})
    c.update(case or {})
    p.update(post or {})
    a.update(ans or {})
    return e, c, p, a


def cash_fact(day, booking_id="", bike="NMAX 155 6908", role="оплата аренды", amount=4900, currency="THB"):
    """Факт кассы в форме wa_agent_tools.cash_result (`at` — дата строки), + день и номер байка для правил."""
    return {"kind": "cash", "src": "tx_find", "row": 2041, "msg_id": "m-2041", "link": None,
            "at": (day + " 13:20") if day else None, "day": day, "date": day, "booking_id": booking_id,
            "bike": bike, "plate": _plate_of(bike), "amount": amount, "currency": currency,
            "role": role, "category": "rental"}


SRC = {"source": "test", "ref": "строка 812", "method": "door", "read_at": T_OBS, "observed_at": T_OBS, "case_ver": 1}
DIRECTION = {("money", "rent"): "from_client", ("money", "deposit"): "from_client",
             ("money", "deposit_refund"): "to_client", ("bike", "handover"): "internal",
             ("bike", "return"): "internal", ("client", "notify_final"): "to_client",
             ("document", "passport_return"): "to_client"}


def obl(oid, kind, role, state, closed_by=None, outcome=None, amount=None, currency=None) -> Dict[str, Any]:
    """Элемент частей money / obligations_other case_view (§8.4) + id строки rc_obligation."""
    return {"id": oid, "obligation_id": oid, "kind": kind, "role": role,
            "direction": DIRECTION.get((kind, role), "internal"), "state": state, "closed_by": closed_by,
            "close_ref": "btn:%s" % oid if closed_by == "human" else None,
            "outcome": outcome if outcome is not None else ("valid" if kind == "money" else None),
            "amount": amount, "currency": currency, "required": 1, "why": "", "close_fact": None,
            "close_second": None, "cash": [], "payment_confirmed": False, "src": dict(SRC)}


def mk_view(case_ver=2, status_seen="Завершена", tasks=None, expectations=None, notices=None, money=None,
            other=None, attention=0, link_state="ok") -> Dict[str, Any]:
    """case_view по частям §8.4 (+ общий список obligations тех же элементов)."""
    if money is None:
        money = [obl(90501, "money", "rent", "closed", "human", amount=4900, currency="THB"),
                 obl(90502, "money", "deposit", "closed", "human", amount=3000, currency="THB"),
                 obl(90503, "money", "deposit_refund", "closed", "human", amount=3000, currency="THB")]
    if other is None:
        other = [obl(90504, "bike", "handover", "closed", "stage"),
                 obl(90505, "bike", "return", "closed", "stage"),
                 obl(90506, "client", "notify_final", "waived", "human")]
    if tasks is None:
        tasks = [{"task_id": "RT-R", "case_id": "RC-I", "kind": "return", "state": "done", "top_stage": 5,
                  "rental_id": 41, "case_ver": case_ver, "created_at": T_OBS, "updated_at": T_NEW, "row_ver": 3,
                  "reason": None, "src": dict(SRC)}]
    if expectations is None:
        expectations = [{"exp_id": "RE-1", "case_id": "RC-I", "task_id": "RT-R", "kind": "staff_question",
                         "action": None, "place": "topic", "state": "answered", "next_check": "none",
                         "case_ver": case_ver, "src": dict(SRC)}]
    if notices is None:
        notices = [{"notice_id": "RN-1", "case_id": "RC-I", "task_id": "RT-R", "intent": "final",
                    "state": "delivered", "case_ver": case_ver, "draft_id": 7, "wamid": "wamid.X",
                    "src": dict(SRC)}]
    case = {"case_id": "RC-I", "ver": case_ver, "state": "open", "link_state": link_state, "attention": attention,
            "att_channel": "wa" if attention else None, "origin": "test", "created_at": T_OBS,
            "created_by": "test", "src": dict(SRC)}
    rental_cur = {"booking_id": "bk-812", "anchor": "6908|2026-10-01|иван", "plate": "6908",
                  "start_at": "2026-10-01 10:00", "end_at": "2026-10-12 10:00", "start_day": "2026-10-01",
                  "end_day": "2026-10-12", "days": 11, "status_seen": status_seen, "crm_row_seen": 812,
                  "bound_by": "booking_id", "src": dict(SRC)}
    return {"case": case,
            "client": {"name_seen": "Иван", "src": dict(SRC),
                       "contacts": [{"channel": "wa", "value_masked": "…5678", "status": "active",
                                     "source_kind": "crm", "src": dict(SRC)}]},
            "rental": {"current": rental_cur, "history": []},
            "bike": {"plate": "6908", "bike_name": "NMAX 155 6908", "model_req": "NMAX", "history": [],
                     "state": None, "src": dict(SRC)},
            "documents": [], "refs": [], "money": money, "obligations_other": other,
            "obligations": list(money) + list(other), "facts": [], "facts_inactive": [], "tasks": tasks,
            "expectations": expectations, "answers": [], "orphans": [], "notices": notices, "missing": [],
            "read_at": T_NEW}


# ----------------------------------------------------------------------------------------------------------------
# Общие помощники
# ----------------------------------------------------------------------------------------------------------------


def rcode(value: Any) -> str:
    """Код причины без слов: «код[: слова]» (§1.2)."""
    return str(value or "").split(":")[0].strip()


def row_no(x: Any) -> Optional[int]:
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, Mapping):
        r = x.get("row")
        if isinstance(r, Mapping):
            return row_no(r)
        if isinstance(r, int) and not isinstance(r, bool):
            return r
        for k in ("crm_row_seen", "row_no"):
            v = x.get(k)
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    return None


def rows_of(seq: Any) -> set:
    return {row_no(x) for x in (seq or [])} - {None}


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, sort_keys=True)


def has_token(obj: Any, token: Any) -> bool:
    return str(token) in jdump(obj)


def flags_of(res: Mapping[str, Any]) -> set:
    return set(res.get("flags") or [])


class K4Case(unittest.TestCase):
    maxDiff = None

    def pure(self, fn, *args, **kwargs):
        """Правила §6 чистые: входы после вызова не меняются (побочных записей у правил нет)."""
        before_a, before_k = copy.deepcopy(args), copy.deepcopy(kwargs)
        res = fn(*args, **kwargs)
        self.assertEqual(args, before_a, "%s изменил позиционные входы (§6: чистые правила)" % fn.__name__)
        self.assertEqual(kwargs, before_k, "%s изменил именованные входы (§6: чистые правила)" % fn.__name__)
        return res

    def assertUnknownWellFormed(self, res: Mapping[str, Any], where: str = "") -> None:
        """К4-C5 / §1.2 / §12: unknown всегда с непустыми missing и ask; missing — из перечня §12 или имя параметра."""
        missing, ask = res.get("missing"), res.get("ask")
        self.assertIsInstance(missing, (list, tuple), "missing не список: %s %r" % (where, res))
        self.assertTrue(len(missing) > 0, "unknown без missing (К4-C5, M12): %s %r" % (where, res))
        for m in missing:
            self.assertIsInstance(m, str, where)
            self.assertIn(m, MISSING | PARAM_NAMES, "missing вне §12/§10: %s %r" % (where, m))
        self.assertIsInstance(ask, str, "ask не строка: %s %r" % (where, res))
        self.assertTrue(ask.strip(), "unknown без ask (К4-C5, M12): %s %r" % (where, res))

    def assertReason(self, res: Mapping[str, Any], *codes: str) -> None:
        self.assertIn(rcode(res.get("reason")), codes, "причина %r не из %r: %r" % (res.get("reason"), codes, res))

    def assertMissingHas(self, res: Mapping[str, Any], item: str) -> None:
        self.assertIn(item, list(res.get("missing") or []), "в missing нет %r: %r" % (item, res))


# ================================================================================================================
# Модуль: публичные функции, сигнатуры §6, чистота (I20, К4-C18, К4-C19), параметры (§10, К4-C17)
# ================================================================================================================

SIGNATURES = {
    "classify": ["row", "moment", "params"],
    "name_norm": ["name"],
    "anchor_of": ["row"],
    "contact_match": ["contacts_cell", "number", "key_digits"],
    "pick": ["rows", "query", "moment", "params"],
    "ask_for": ["candidates", "purpose", "intent"],
    "reconcile": ["binding", "rows", "observed_at", "others", "params"],
    "continuation": ["new_row", "open_bindings", "params"],
    "cash_claimants": ["cash_fact", "same_plate_rows", "params"],
    "bind_cash": ["cash_fact", "rental", "same_plate_rows", "params", "human"],
    "answer_verdict": ["exp", "case", "post", "answer", "params"],
    # APPROVEFIX1610 (Codex TB-OWNER-EFFICIENCY-1610-2054: «в К4 передавать action в решение»): необязательное действие
    # карточки; осознанное расширение сигнатуры §6, прежние вызовы (text, params) не меняются
    "approval_decision": ["text", "params", "action"],
    "accept_decision": ["text", "params"],
    "stage_allowed": ["task", "binding", "stage", "evidence", "prior", "used_refs", "answers", "other_rows",
                      "params"],
    "required_obligations": ["row", "params"],
    "bike_state_fact": ["item", "binding"],
    "obligation_verdict": ["kind", "role", "want", "write", "cell", "human", "params"],
    "document_coverage": ["doc", "period"],
    "close_blockers": ["view"],
    "allowed": ["view", "params"],
}


class TestModuleContract(K4Case):

    def test_public_functions_and_signatures_section6(self):
        """CONTRACT §6: каждая функция есть, имена и порядок аргументов — как в контракте."""
        for name, expected in SIGNATURES.items():
            fn = getattr(R, name, None)
            self.assertTrue(callable(fn), "нет rental_case_rules.%s (§6)" % name)
            got = [p.name for p in inspect.signature(fn).parameters.values()
                   if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]
            self.assertEqual(got, expected, "сигнатура %s расходится с §6" % name)
        self.assertEqual(inspect.signature(R.contact_match).parameters["key_digits"].default, 9)
        sig = inspect.signature(R.bind_cash).parameters
        self.assertIsNone(sig["human"].default, "bind_cash(human=None) — §6")

    def test_obligation_verdict_has_no_age_input_I14(self):
        """I14: «возраста среди входов нет» — ни возраста, ни часов, ни «сейчас» во входах obligation_verdict."""
        names = list(inspect.signature(R.obligation_verdict).parameters)
        for n in names:
            for bad in ("age", "now", "clock", "time", "moment", "at"):
                self.assertNotEqual(n, bad)
                self.assertFalse(n.endswith("_age") or n.startswith("age_"), n)

    def test_document_coverage_takes_only_doc_and_period_C39(self):
        """К4-C39 / I46: document_coverage(doc, period) — параметр привязки не принимается; в теле нет имён
        signed_at, contract_date, start_day, end_day (M31, M31b)."""
        params_ = list(inspect.signature(R.document_coverage).parameters)
        self.assertEqual(len(params_), 2, params_)
        for n in params_:
            self.assertNotIn("binding", n)
            self.assertNotIn("rental", n)
        src = textwrap.dedent(inspect.getsource(R.document_coverage))
        tree = ast.parse(src)
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                seen.add(node.id)
            elif isinstance(node, ast.Attribute):
                seen.add(node.attr)
            elif isinstance(node, ast.arg):
                seen.add(node.arg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                seen.add(node.value)
        for bad in ("signed_at", "contract_date", "start_day", "end_day"):
            self.assertNotIn(bad, seen, "document_coverage читает %r (К4-C39: покрытие не из даты/срока)" % bad)

    def test_rules_source_py38_and_pure_I20_C18_C19(self):
        """I20, К4-C18, К4-C19: модуль разбирается как 3.8, без API 3.9+, без сети/БД/окружения/часов/файлов;
        I17, К4-C4, К4-C25: _rental_for в правилах не упоминается вовсе (выбор только своим правилом)."""
        path = inspect.getsourcefile(R)
        with open(path, "rb") as fh:
            raw = fh.read()
        self.assertNotIn(b"\r", raw, "rental_case_rules.py не LF-only")
        src = raw.decode("utf-8")
        tree = ast.parse(src, feature_version=(3, 8))
        bad_modules = {"socket", "sqlite3", "urllib", "http", "requests", "subprocess", "ssl", "ftplib", "smtplib",
                       "telegram", "bridge_client", "splinter", "wa_agent", "wa_agent_model", "wa_agent_svc",
                       "wa_agent_tg", "wa_agent_attach", "staff_ask", "bot", "random", "dotenv", "zoneinfo",
                       "asyncio"}
        bad_attrs = {"removeprefix", "removesuffix", "utcfromtimestamp", "utcnow", "getenv", "putenv", "environ",
                     "uuid4", "monotonic", "perf_counter"}
        problems = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] in bad_modules:
                        problems.append("import %s" % a.name)
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in bad_modules:
                    problems.append("from %s import" % node.module)
                for a in node.names:
                    if a.name == "_rental_for":
                        problems.append("import _rental_for")
            elif isinstance(node, ast.Attribute):
                base = node.value
                base_name = base.id if isinstance(base, ast.Name) else (
                    base.attr if isinstance(base, ast.Attribute) else "")
                if node.attr in bad_attrs:
                    problems.append("атрибут %s" % node.attr)
                if node.attr == "_rental_for":
                    problems.append("_rental_for")
                if node.attr in ("now", "today") and base_name in ("datetime", "date"):
                    problems.append("%s.%s" % (base_name, node.attr))
                if node.attr == "time" and base_name == "time":
                    problems.append("time.time")
                if node.attr == "cache" and base_name == "functools":
                    problems.append("functools.cache")
                if node.attr == "UTC" and base_name == "datetime":
                    problems.append("datetime.UTC")
            elif isinstance(node, ast.Name):
                if node.id == "_rental_for":
                    problems.append("_rental_for")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                problems.append("open(…)")
        self.assertEqual(problems, [], "нарушения чистоты/совместимости в rental_case_rules.py")

    def test_rules_do_not_read_clock(self):
        """§6 «без часов»: правила с заблокированными time.time/time.monotonic работают (момент — аргумент)."""
        boom = mock.Mock(side_effect=AssertionError("правило прочитало часы"))
        with mock.patch.object(time, "time", boom), mock.patch.object(time, "monotonic", boom):
            R.classify(R812, MOMENT, PD)
            R.pick(ALL_ROWS, {"purpose": "return", "plate": "6908"}, MOMENT, PD)
            R.document_coverage({"status": "verified", "kind": "contract_signed", "cover_from": None,
                                 "cover_to": None, "cover_basis": None}, ("2026-10-12", "2026-10-20"))
        self.assertEqual(boom.call_count, 0)

    def test_network_guard_active_C18(self):
        """К4-C18: подмена socket.socket действует в процессе проверок."""
        with self.assertRaises(Exception):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)

    def test_unknown_marker(self):
        """§10: UNKNOWN = "UNKNOWN" (если модуль правил экспортирует метку)."""
        if hasattr(R, "UNKNOWN"):
            self.assertEqual(R.UNKNOWN, "UNKNOWN")


class TestParamsDefault(K4Case):
    """§10, К4-C17, К4-C38: умолчания реализации — ровно таблица §10, непринятые нормы — UNKNOWN."""

    def test_transcribed_table_self_consistent(self):
        """Своя выписка §10 в этом файле полна: имена = 56 строк таблицы."""
        self.assertEqual(set(_contract_params()), set(PARAM_NAMES))
        self.assertEqual(len(PARAM_NAMES), 56)

    def _pd(self):
        if IMPL_PD is None:
            self.fail("PARAMS_DEFAULT не найден ни в rental_case_rules, ни в rental_case (§10, DESIGN §9)")
        return IMPL_PD

    @staticmethod
    def _unknown_at(value, key=None):
        if value == UNKNOWN:
            return True
        if key is not None and isinstance(value, Mapping):
            return value.get(key, UNKNOWN) == UNKNOWN
        return False

    def test_names_equal_contract_table_C17(self):
        pd = self._pd()
        self.assertEqual(set(pd), set(PARAM_NAMES), "имена PARAMS_DEFAULT ≠ CONTRACT §10 (К4-C17)")
        self.assertNotIn("TECH_TIMEOUT_S", pd, "К4-C38: TECH_TIMEOUT_S снят")

    def test_known_values(self):
        pd = self._pd()
        self.assertEqual(pd["TZ_H"], 7)
        self.assertEqual(pd["KEY_DIGITS"], 9)
        self.assertEqual(pd["MAX_POST_ATTEMPTS"], 1)
        self.assertEqual(pd["APPROVAL_TTL_S"]["activate"], 1800)
        self.assertEqual(pd["APPROVAL_TTL_S"]["close"], 1800)
        self.assertEqual(pd["APPROVAL_TTL_S"]["booking"], UNKNOWN, "I39/M30: у брони числа нет")
        self.assertEqual(set(pd["OWNER_IDS"]), set(OWNER_IDS))
        self.assertEqual(set(pd["APPROVER_IDS"]), set(OWNER_IDS), "APPROVER_IDS по умолчанию = OWNER_IDS")
        self.assertEqual(set(pd["FEEDS_CONNECTED"]), set(), "FEEDS_CONNECTED по умолчанию ∅")
        self.assertEqual(tuple(pd["APPROVAL_YES_WORDS"]), YES_WORDS)
        self.assertEqual(tuple(pd["APPROVAL_YES_STEMS"]), YES_STEMS)
        self.assertEqual(tuple(pd["APPROVAL_NO_STEMS"]), NO_STEMS)
        self.assertEqual(tuple(pd["APPROVAL_NO_AFTER_NE"]), NO_AFTER_NE)
        self.assertEqual(list(pd["STAFF_PLACES"]["байк"]), ["topic", "delivery"])
        for k in ("цена", "бронь", "сложность"):
            self.assertEqual(list(pd["STAFF_PLACES"][k]), ["agents"])

    def test_unknown_defaults_fail_closed_I16(self):
        pd = self._pd()
        for name in FAIL_CLOSED_NAMES:
            self.assertEqual(pd[name], UNKNOWN, "%s по умолчанию обязан быть UNKNOWN (§10)" % name)
        for place in ("topic", "delivery", "agents"):
            self.assertTrue(self._unknown_at(pd["STAFF_ADDRESSEES"], place), "STAFF_ADDRESSEES[%s]" % place)
        for kind in TASK_KINDS:
            self.assertTrue(self._unknown_at(pd["PHYSICAL_DONE_SOURCES"], kind), "PHYSICAL_DONE_SOURCES[%s]" % kind)
        rrp = pd["RESULT_RECORD_PLACE"]
        self.assertEqual(rrp["handover"], "crm:в аренде")
        self.assertEqual(rrp["return"], "crm:завершена")
        for kind in ("readiness", "delivery", "pickup", "other"):
            self.assertTrue(self._unknown_at(rrp, kind), "RESULT_RECORD_PLACE[%s]" % kind)


# ================================================================================================================
# name_norm, anchor_of, contact_match (I-18, DESIGN §2.2, §3.2)
# ================================================================================================================


class TestNameAnchorContact(K4Case):

    def test_name_norm_and_stubs_I18(self):
        self.assertEqual(R.name_norm("  Иван "), "иван")
        self.assertEqual(R.name_norm("ИВАН"), "иван")
        for stub in ("", "—", "-", "?", "  —  "):
            self.assertIsNone(R.name_norm(stub), "заглушка %r → None (I-18)" % stub)

    def test_anchor_of(self):
        """Якорь = plate|YYYY-MM-DD|name_norm; нет любой части → None (§6, DESIGN §2.2)."""
        self.assertEqual(self.pure(R.anchor_of, R812), "6908|2026-10-01|иван")
        self.assertEqual(R.anchor_of(R870), "5151|2026-10-02|олег")
        self.assertIsNone(R.anchor_of(rv(R812, bike="NMAX")), "нет номера байка → нет якоря")
        self.assertIsNone(R.anchor_of(rv(R812, date_start=None)), "нет даты → нет якоря")
        self.assertIsNone(R.anchor_of(rv(R812, name="—")), "имя-заглушка → нет якоря (I-18)")
        self.assertIsNone(R.anchor_of(rv(R812, name="")), "пустое имя → нет якоря")
        self.assertEqual(R.anchor_of(rv(R812, booking_id="")), "6908|2026-10-01|иван", "телефон/Y в якорь не входят")

    def test_contact_match(self):
        """§6 contact_match: хвост KEY_DIGITS; явный другой код страны — clash (phone_country_clash)."""
        self.assertEqual(self.pure(R.contact_match, IVAN_PHONE, IVAN_NUM), "match")
        self.assertEqual(R.contact_match("081 234 5678", IVAN_NUM), "match", "местная запись — по хвосту")
        self.assertEqual(R.contact_match("Иван " + IVAN_PHONE + ", жена +66 82 000 1111", IVAN_NUM), "match")
        self.assertEqual(R.contact_match("+7 981 234-56-78", IVAN_NUM), "clash", "тот же хвост, другой код страны")
        self.assertEqual(R.contact_match("+66 99 999 9999", IVAN_NUM), "none")
        self.assertEqual(R.contact_match("", IVAN_NUM), "none")
        self.assertEqual(R.contact_match(IVAN_PHONE, IVAN_NUM, key_digits=9), "match")


# ================================================================================================================
# classify — классы строки §3.1 (DESIGN §3.2), день в зоне +7 (§1.1)
# ================================================================================================================


class TestClassify(K4Case):

    def cls(self, row, moment=MOMENT, prm=None):
        res = self.pure(R.classify, row, moment, prm or PD)
        self.assertIn(res.get("cls"), CLASSES, "класс вне §3.1: %r" % res)
        self.assertTrue(flags_of(res) <= FLAGS, "флаги вне §3.1: %r" % res)
        return res

    def test_current_with_fields(self):
        res = self.cls(R812)
        self.assertEqual(res["cls"], "current")
        self.assertNotIn("overdue", flags_of(res))
        self.assertEqual(res["plate"], "6908", "номер — последнее число от 3 цифр, не кубатура (plate_of)")
        self.assertEqual(res["start_day"], "2026-10-01")
        self.assertEqual(res["end_day"], "2026-10-12")
        self.assertEqual(res["days"], 11, "сутки = дата возврата − дата выдачи (05.10-1 п.3)")
        self.assertEqual(res["anchor"], "6908|2026-10-01|иван")
        self.assertEqual(res["name_norm"], "иван")

    def test_current_overdue_flag(self):
        res = self.cls(R812, ts(2026, 10, 13, 12))
        self.assertEqual(res["cls"], "current")
        self.assertIn("overdue", flags_of(res))
        self.assertIn("overdue", flags_of(self.cls(R650)), "висяк 2023 — current с overdue")

    def test_overdue_day_in_tz_plus7_section1_1(self):
        row = rv(R812, date_end="2026-10-09 10:00")
        self.assertNotIn("overdue", flags_of(self.cls(row, ts(2026, 10, 9, 23, 0))), "тот же день +7")
        self.assertIn("overdue", flags_of(self.cls(row, ts(2026, 10, 10, 0, 30))),
                      "10.10 00:30 (+7) — уже следующий день, хотя по UTC ещё 09.10")

    def test_auto_cancel_on_is_unknown(self):
        res = self.cls(rv(R812, auto_cancel="ON"))
        self.assertEqual(res["cls"], "unknown", "«в аренде» при B=ON — unknown (AUTO_CANCEL_B_MEANING=UNKNOWN)")
        self.assertIn("auto_cancel_on", flags_of(res))

    def test_booking_classes(self):
        self.assertEqual(self.cls(rv(R845, date_start="2026-10-08 10:00", date_end="2026-10-12 10:00"))["cls"],
                         "current_unactivated")
        self.assertEqual(self.cls(rv(R845, date_start="2026-10-09 10:00", date_end="2026-10-09 18:00"))["cls"],
                         "current_unactivated", "граница: start_day = end_day = день")
        self.assertEqual(self.cls(R845)["cls"], "future")
        self.assertEqual(self.cls(rv(R845, date_start="2026-09-01 10:00", date_end="2026-10-05 10:00"))["cls"],
                         "stale_booking")

    def test_booking_day_in_tz_plus7(self):
        row = rv(R845, date_start="2026-10-10 10:00", date_end="2026-10-12 10:00")
        self.assertEqual(self.cls(row, ts(2026, 10, 10, 1, 0))["cls"], "current_unactivated",
                         "10.10 01:00 (+7) = 09.10 18:00 UTC: день — по +7")
        self.assertEqual(self.cls(row, ts(2026, 10, 9, 23, 0))["cls"], "future")

    def test_past(self):
        self.assertEqual(self.cls(R790)["cls"], "past")

    def test_manual_status_unknown(self):
        res = self.cls(rv(R812, status="долг"))
        self.assertEqual(res["cls"], "unknown")
        self.assertIn("manual_status", flags_of(res))

    def test_no_dates_unknown(self):
        res = self.cls(rv(R812, date_start=None))
        self.assertEqual(res["cls"], "unknown")
        self.assertIn("no_dates", flags_of(res))
        self.assertIsNone(res.get("start_day"))
        self.assertIsNone(res.get("anchor"))

    def test_stub_name(self):
        res = self.cls(rv(R812, name="—"))
        self.assertIn("stub_name", flags_of(res))
        self.assertIsNone(res.get("name_norm"))
        self.assertIsNone(res.get("anchor"))

    def test_status_case_insensitive(self):
        self.assertEqual(self.cls(rv(R812, status="в аренде"))["cls"], "current")
        self.assertEqual(self.cls(rv(R845, status="БРОНЬ"))["cls"], "future")
        self.assertEqual(self.cls(rv(R790, status="завершена"))["cls"], "past")

    def test_vocabulary_sweep_section3_1(self):
        for row in ALL_ROWS + [R870, rv(R812, status="долг"), rv(R812, date_start=None)]:
            for m in (MOMENT, ts(2026, 10, 13), ts(2026, 10, 15, 9), ts(2023, 5, 5)):
                self.cls(row, m)


# ================================================================================================================
# pick — выбор аренды (§6, DESIGN §3.3–§3.4; I17, I36; К4-C4, К4-C5, К4-C25; M1, M1b, M11, M12, M21, M22)
# ================================================================================================================


class TestPick(K4Case):

    def pk(self, rows, query, moment=MOMENT, prm=None):
        prm = prm or PD
        res = self.pure(R.pick, rows, query, moment, prm)
        self.assertIn(res.get("code"), ("found", "unknown"), res)
        if res["code"] == "unknown":
            self.assertUnknownWellFormed(res, "pick %r" % (query,))
            self.assertIn(rcode(res.get("reason")), REASONS_OK, "причина вне §12: %r" % res)
            self.assertIsNone(res.get("row"), "unknown не отдаёт строку: %r" % res)
        else:
            self.assertIn(row_no(res.get("row")), {r["row"] for r in rows}, "found: строка не из входа")
            self.assertLessEqual(len(rows_of(res.get("candidates"))), 1, "I17: found при >1 кандидате")
            self.assertEqual(res.get("cls"), R.classify(res["row"], moment, prm)["cls"])
        return res

    def assertFound(self, res, row):
        self.assertEqual(res["code"], "found", res)
        self.assertEqual(row_no(res["row"]), row, res)

    # --- client (контакт от кода, I36) ---

    def test_client_current_and_future_same_bike_section13(self):
        """§13 «текущая и будущая бронь того же байка»; §14 Д4: будущая бронь Бориса, а не текущая аренда Ивана."""
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "current", "contact": C_IVAN}), 812)
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "future", "contact": C_BORIS}), 845)

    def test_client_future_absent_is_unknown(self):
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "future", "contact": C_IVAN})
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "rental_not_found")

    def test_client_rows_of_other_contacts_never_used_I36_M22(self):
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "current", "contact": C_BORIS})
        self.assertEqual(res["code"], "unknown", "у Бориса нет текущей; текущая Ивана того же байка не его")
        self.assertTrue(rows_of(res.get("candidates")) <= {845}, res)

    def test_client_specific_foreign_booking_id_is_unknown_contact_M22(self):
        """I-7: booking_id чужой строки → unknown(contact)."""
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "specific", "contact": C_IVAN,
                                 "booking_id": "bk-845"})
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "contact")
        self.assertMissingHas(res, "contact")

    def test_client_specific_own_booking_id(self):
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "specific", "contact": C_IVAN,
                                            "booking_id": "bk-812"}), 812)

    def test_client_specific_contract_date_selects_past_rental_M11(self):
        """§13 «запрос старого договора»: договор 05.09 → аренда 01.09–15.09, а не активная."""
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "specific", "contact": C_IVAN,
                                            "contract_date": "2026-09-05"}), 790)

    def test_client_specific_period(self):
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "specific", "contact": C_IVAN,
                                            "period": ("2026-10-10", "2026-10-11")}), 812)
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "specific", "contact": C_IVAN,
                                 "period": ("2026-09-10", "2026-10-05")})
        self.assertEqual(res["code"], "unknown", "период пересекает обе аренды Ивана")
        self.assertTrue({790, 812} <= rows_of(res.get("candidates")), res)

    def test_client_intent_none_two_is_always_unknown(self):
        """DESIGN §3.3 client/None: >1 → unknown всегда (все классы контакта, кроме stale_booking/unknown)."""
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": None, "contact": C_IVAN})
        self.assertEqual(res["code"], "unknown")
        self.assertTrue({790, 812} <= rows_of(res.get("candidates")), res)
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": None, "contact": C_ANNA})
        self.assertEqual(res["code"], "unknown", "висяк + бронь Анны")

    def test_client_intent_none_single_found(self):
        self.assertFound(self.pk([R812, R845, R700], {"purpose": "client", "intent": None, "contact": C_IVAN}), 812)

    def test_client_current_stale_active_section13(self):
        """§13 «висяк и две в аренде»: висяк 2023 + бронь → unknown(stale_active) с вопросом (STALE_ACTIVE_DAYS)."""
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "current", "contact": C_ANNA})
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "stale_active")
        self.assertMissingHas(res, "which_rental")
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "future", "contact": C_ANNA}), 860)

    def test_client_current_any_overdue_is_stale_active(self):
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "current", "contact": C_IVAN},
                      moment=ts(2026, 10, 13, 12))
        self.assertEqual(res["code"], "unknown", "просрочка на 1 день при STALE_ACTIVE_DAYS=UNKNOWN")
        self.assertReason(res, "stale_active")

    def test_client_current_includes_unactivated(self):
        kira = mk_row(881, "Бронь", "PCX 160 4410", "Кира", "2026-10-08 10:00", "2026-10-12 10:00", KIRA_PHONE,
                      "bk-881")
        self.assertFound(self.pk(ALL_ROWS + [kira], {"purpose": "client", "intent": "current", "contact": C_KIRA}),
                         881)

    def test_client_current_no_window_around_today(self):
        """DESIGN §3.4: окно «сегодня ± сутки» запрещено — бронь с завтра текущей не становится."""
        kira = mk_row(882, "Бронь", "PCX 160 4410", "Кира", "2026-10-10 10:00", "2026-10-14 10:00", KIRA_PHONE,
                      "bk-882")
        res = self.pk(ALL_ROWS + [kira], {"purpose": "client", "intent": "current", "contact": C_KIRA})
        self.assertEqual(res["code"], "unknown")
        ended = mk_row(883, "В аренде", "PCX 160 4410", "Кира", "2026-10-01 10:00", "2026-10-08 10:00", KIRA_PHONE)
        res = self.pk([ended], {"purpose": "client", "intent": "current", "contact": C_KIRA})
        self.assertEqual(res["code"], "unknown", "аренда, кончившаяся вчера, — висяк, а не «текущая»")
        self.assertReason(res, "stale_active")

    def test_client_past_and_lookback_unknown(self):
        self.assertFound(self.pk(ALL_ROWS, {"purpose": "client", "intent": "past", "contact": C_IVAN}), 790)
        old = mk_row(500, "Завершена", "PCX 160 4410", "Иван", "2023-01-01 10:00", "2023-01-05 10:00", IVAN_PHONE)
        res = self.pk([old, R812], {"purpose": "client", "intent": "past", "contact": C_IVAN})
        self.assertFound(res, 500)   # PAST_LOOKBACK=UNKNOWN → всё, что отдала дверь, без отсечки по давности
        res = self.pk([old, R790, R812], {"purpose": "client", "intent": "past", "contact": C_IVAN})
        self.assertEqual(res["code"], "unknown", "две прошлые → unknown «за какие даты / какой байк»")

    def test_client_without_contact_is_unknown(self):
        res = self.pk(ALL_ROWS, {"purpose": "client", "intent": "current"})
        self.assertEqual(res["code"], "unknown", "client: контакт обязателен (I36)")
        self.assertMissingHas(res, "contact")

    def test_client_phone_clash(self):
        clash = rv(R812, contacts="+7 981 234-56-78")
        res = self.pk([clash, R845], {"purpose": "client", "intent": "current", "contact": C_IVAN})
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "phone_clash")
        self.assertMissingHas(res, "contact")

    def test_client_tg_username_unknown_param(self):
        """DESIGN §3.3: клиент из TG по нику в U — TG_CONTACT_MATCH=UNKNOWN → unknown."""
        row = rv(R812, contacts=IVAN_PHONE + " @ivan_tg")
        res = self.pk([row], {"purpose": "client", "intent": "current",
                              "contact": {"channel": "tg_username", "value": "ivan_tg"}})
        self.assertEqual(res["code"], "unknown")
        self.assertMissingHas(res, "contact")

    # --- handover / return / debt (I-6, R2) ---

    def test_handover_exact_day_only(self):
        rows = [R812, R845, R790]
        self.assertFound(self.pk(rows, {"purpose": "handover", "plate": "6908"}, ts(2026, 10, 15, 9)), 845)
        for m in (ts(2026, 10, 14, 9), ts(2026, 10, 16, 9)):
            res = self.pk(rows, {"purpose": "handover", "plate": "6908"}, m)
            self.assertEqual(res["code"], "unknown", "HANDOVER_DAY_TOLERANCE=UNKNOWN → только точный день")

    def test_handover_two_bookings_same_day(self):
        twin = mk_row(884, "Бронь", "NMAX 155 6908", "Кира", "2026-10-15 12:00", "2026-10-17 10:00", KIRA_PHONE,
                      "bk-884")
        res = self.pk([R812, R845, twin], {"purpose": "handover", "plate": "6908"}, ts(2026, 10, 15, 9))
        self.assertEqual(res["code"], "unknown", "RENTAL_CONFLICT_RULE=UNKNOWN")
        self.assertTrue({845, 884} <= rows_of(res.get("candidates")), res)

    def test_return_only_started_active_I6(self):
        """§13: return → текущая; будущая бронь и «Завершена» не кандидаты."""
        self.assertFound(self.pk([R845, R790, R812], {"purpose": "return", "plate": "6908"}), 812)
        self.assertFound(self.pk([R845, R790, R812], {"purpose": "debt", "plate": "6908"}), 812)

    def test_return_two_active_is_unknown_M1_M21(self):
        """§13 «две в аренде 6908 → unknown»: вместо max(date_start) и _rental_for (К4-C25)."""
        for purpose in ("return", "debt"):
            res = self.pk([R650, R812, R845, R790], {"purpose": purpose, "plate": "6908"})
            self.assertEqual(res["code"], "unknown", purpose)
            self.assertReason(res, "two_active")
            self.assertMissingHas(res, "which_rental")
            self.assertEqual(rows_of(res.get("candidates")) & {650, 812}, {650, 812}, res)
            self.assertNotIn(845, rows_of(res.get("candidates")), "будущая бронь — не кандидат возврата")

    def test_return_auto_cancel_on_not_candidate(self):
        on = mk_row(651, "В аренде", "NMAX 155 6908", "Пётр", "2026-09-20 10:00", "2026-09-30 10:00", PETR_PHONE,
                    auto_cancel="ON")
        self.assertFound(self.pk([on, R812], {"purpose": "return", "plate": "6908"}), 812)

    def test_contract_purpose(self):
        """§3.3 contract: аренда контакта и байка, чей период ∋ дата; до начала → unknown(contract_pre_start)."""
        q = {"purpose": "contract", "contact": C_IVAN, "plate": "6908"}
        self.assertFound(self.pk(ALL_ROWS, dict(q, contract_date="2026-10-01")), 812)
        self.assertFound(self.pk(ALL_ROWS, dict(q, contract_date="2026-09-05")), 790)
        res = self.pk([R812, R845], dict(q, contract_date="2026-09-30"))
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "contract_pre_start")

    # --- свойства ---

    def test_order_independence_M1b(self):
        """I17: порядок строк не решает — те же исходы при любой перестановке (cand[-1], первая подходящая)."""
        rows = [R650, R812, R845, R790, R700]
        cases = [
            ({"purpose": "client", "intent": "current", "contact": C_IVAN}, MOMENT),
            ({"purpose": "client", "intent": None, "contact": C_IVAN}, MOMENT),
            ({"purpose": "return", "plate": "6908"}, MOMENT),
            ({"purpose": "handover", "plate": "6908"}, ts(2026, 10, 15, 9)),
            ({"purpose": "client", "intent": "past", "contact": C_IVAN}, MOMENT),
        ]
        for query, moment in cases:
            outcomes = set()
            for perm in itertools.permutations(rows):
                res = R.pick(list(perm), query, moment, PD)
                outcomes.add((res.get("code"), row_no(res.get("row")), rcode(res.get("reason"))
                              if res.get("code") == "unknown" else ""))
            self.assertEqual(len(outcomes), 1, "исход зависит от порядка строк: %r → %r" % (query, outcomes))

    def test_unknown_well_formed_sweep_C5_M12(self):
        queries = [
            {"purpose": "client", "intent": "current", "contact": C_IVAN},
            {"purpose": "client", "intent": "future", "contact": C_IVAN},
            {"purpose": "client", "intent": "past", "contact": C_IVAN},
            {"purpose": "client", "intent": None, "contact": C_IVAN},
            {"purpose": "client", "intent": "current", "contact": C_ANNA},
            {"purpose": "client", "intent": None, "contact": C_ANNA},
            {"purpose": "client", "intent": "specific", "contact": C_IVAN, "booking_id": "bk-845"},
            {"purpose": "client", "intent": "specific", "contact": C_IVAN, "booking_id": "bk-zzz"},
            {"purpose": "client", "intent": "current", "contact": {"channel": "wa", "value": "66800000000"}},
            {"purpose": "client", "intent": "current"},
            {"purpose": "handover", "plate": "6908"},
            {"purpose": "return", "plate": "6908"},
            {"purpose": "debt", "plate": "6908"},
            {"purpose": "return", "plate": "9999"},
            {"purpose": "contract", "contact": C_IVAN, "plate": "6908", "contract_date": "2026-09-30"},
        ]
        n_unknown = 0
        for q in queries:
            for m in (MOMENT, ts(2026, 10, 13), ts(2026, 10, 15, 9), ts(2026, 10, 14, 9)):
                res = self.pk(ALL_ROWS, q, m)
                n_unknown += res["code"] == "unknown"
        self.assertGreater(n_unknown, 20)


class TestAskFor(K4Case):

    def test_ask_for_candidates_nonempty_M12(self):
        """DESIGN §3.4: ask собирается из различающих полей; пустой ask — порча M12."""
        res = R.pick(ALL_ROWS, {"purpose": "client", "intent": None, "contact": C_IVAN}, MOMENT, PD)
        ask = self.pure(R.ask_for, res["candidates"], "client", None)
        self.assertIsInstance(ask, str)
        self.assertGreater(len(ask.strip()), 10)
        res = R.pick([R650, R812], {"purpose": "return", "plate": "6908"}, MOMENT, PD)
        ask = self.pure(R.ask_for, res["candidates"], "return", None)
        self.assertGreater(len(ask.strip()), 10)


# ================================================================================================================
# reconcile — сверка привязки с новым чтением (§6, DESIGN §2.3; I30, I-12, I-20, I-21; К4-C30, К4-C33; M10, M18)
# ================================================================================================================

B812 = binding("RC-I", 41, R812, "bk-812", [IVAN_NUM])
B870 = binding("RC-O", 61, R870, "", [OLEG_NUM])
OTHERS_B = [{"case_id": "RC-B", "rental_id": 52, "booking_id": "bk-845", "plate": "6908", "bike_name": "NMAX 155 6908",
             "start_day": "2026-10-15", "end_day": "2026-10-20", "status_seen": "Бронь", "name_norm": "борис",
             "anchor": "6908|2026-10-15|борис", "crm_row_seen": 845}]
RECON_CODES = ("stale", "same", "changed", "drift", "ambiguous", "not_found")


class TestReconcile(K4Case):

    def rc(self, bnd, rows, observed_at=T_NEW, others=(), prm=None):
        res = self.pure(R.reconcile, bnd, rows, observed_at, list(others), prm or PD)
        self.assertIn(res.get("code"), RECON_CODES, res)
        if res["code"] in ("drift", "ambiguous", "not_found"):
            self.assertUnknownWellFormed(res, "reconcile %s" % res["code"])
            self.assertFalse(res.get("bump_reason"), "I-12: при дрейфе/неоднозначности автоподъёма нет: %r" % res)
        return res

    def test_stale_read_I30_M18(self):
        """I30: чтение не новее применённого ничего не меняет — даже если строка «изменилась»."""
        changed = [rv(R812, date_end="2026-10-20 10:00"), R845]
        for obs in (T_OBS, T_OBS - 900):
            res = self.rc(B812, changed, obs, OTHERS_B)
            self.assertEqual(res["code"], "stale", "observed_at=%s ≤ применённого" % obs)
            self.assertFalse(res.get("bump_reason"))
            self.assertFalse(res.get("changes"))

    def test_same(self):
        res = self.rc(B812, [R812, R845], others=OTHERS_B)
        self.assertEqual(res["code"], "same")
        self.assertFalse(res.get("bump_reason"))

    def test_period_changed_bumps_M10(self):
        res = self.rc(B812, [rv(R812, date_end="2026-10-14 10:00"), R845], others=OTHERS_B)
        self.assertEqual(res["code"], "changed", "та же аренда, не новое дело (M10)")
        self.assertEqual(res["bump_reason"], "period_changed")
        self.assertIn(res.get("link_state"), ("ok", None))

    def test_period_overlap_with_other_unfinished_row_I21(self):
        """§13 «продление поверх брони Бориса → внимание, без подъёма»; RENTAL_CONFLICT_RULE=UNKNOWN."""
        res = self.rc(B812, [rv(R812, date_end="2026-10-17 10:00"), R845], others=OTHERS_B)
        self.assertEqual(res["code"], "ambiguous")
        self.assertTrue(res.get("attention"))
        self.assertIn("RC-B", list(res.get("conflict_cases") or []))
        self.assertMissingHas(res, "which_rental")

    def test_bike_changed_bumps(self):
        res = self.rc(B812, [rv(R812, bike="NMAX 155 7001")])
        self.assertEqual(res["code"], "changed")
        self.assertEqual(res["bump_reason"], "bike_changed")

    def test_name_changed_is_drift_I12(self):
        res = self.rc(B812, [rv(R812, name="Пётр"), R845], others=OTHERS_B)
        self.assertEqual(res["code"], "drift")
        self.assertEqual(res.get("link_state"), "drift")
        self.assertMissingHas(res, "link_confirmation")
        self.assertTrue(res.get("cand_sha"), "confirm_link требует cand_sha (§2 CHECK)")

    def test_two_fields_changed_is_drift(self):
        res = self.rc(B812, [rv(R812, bike="NMAX 155 7001", date_start="2026-10-02 10:00")])
        self.assertEqual(res["code"], "drift")

    def test_booking_not_found(self):
        res = self.rc(B812, [R845, R790], others=OTHERS_B)
        self.assertEqual(res["code"], "not_found")
        self.assertEqual(res.get("link_state"), "missing")

    def test_booking_in_two_rows_ambiguous_I20(self):
        res = self.rc(B812, [R812, rv(R812, row=813), R845], others=OTHERS_B)
        self.assertEqual(res["code"], "ambiguous")
        self.assertEqual(res.get("link_state"), "ambiguous")

    def test_regular_status_flow_no_bump(self):
        bnd = dict(B812, status_seen="Бронь")
        res = self.rc(bnd, [R812, R845], others=OTHERS_B)
        self.assertIn(res["code"], ("same", "changed"))
        self.assertFalse(res.get("bump_reason"), "«Бронь»→«В аренде» штатно — без подъёма (DESIGN §2.3)")

    def test_manual_status_is_status_drift_with_attention_I15(self):
        res = self.rc(B812, [rv(R812, status="долг"), R845], others=OTHERS_B)
        self.assertEqual(res.get("bump_reason"), "status_drift")
        self.assertTrue(res.get("attention"))

    def test_contacts_added_and_superseded_M10b(self):
        res = self.rc(B812, [rv(R812, contacts=IVAN_PHONE + ", +66 82 000 1111"), R845], others=OTHERS_B)
        self.assertIn(res["code"], ("same", "changed"))
        self.assertTrue(has_token(res.get("contacts_add"), "820001111"), res)
        bnd = binding("RC-I", 41, R812, "bk-812", [IVAN_NUM, "66820001111"])
        res = self.rc(bnd, [R812, R845], others=OTHERS_B)
        self.assertIn(res["code"], ("same", "changed"))
        self.assertTrue(has_token(res.get("contacts_supersede"), "820001111"), res)

    def test_all_contacts_replaced_is_drift(self):
        res = self.rc(B812, [rv(R812, contacts="+66 82 000 1111"), R845], others=OTHERS_B)
        self.assertEqual(res["code"], "drift", "номера U заменены целиком → drift")

    def test_anchor_period_changed(self):
        res = self.rc(B870, [rv(R870, date_end="2026-10-11 10:00")])
        self.assertEqual(res["code"], "changed")
        self.assertEqual(res["bump_reason"], "period_changed")

    def test_anchor_booking_id_appeared_free(self):
        res = self.rc(B870, [rv(R870, booking_id="bk-870")])
        self.assertIn(res["code"], ("same", "changed"))
        self.assertTrue(has_token(res.get("link_add"), "bk-870"), "Y появился и свободен → link_add: %r" % res)

    def test_anchor_booking_id_taken_is_drift_with_both_cases(self):
        others = [{"case_id": "RC-X", "rental_id": 99, "booking_id": "bk-taken", "plate": "5151",
                   "bike_name": "ADV 160 5151", "start_day": "2026-11-01", "end_day": "2026-11-05",
                   "status_seen": "Бронь", "name_norm": "зоя", "anchor": "5151|2026-11-01|зоя", "crm_row_seen": 990}]
        res = self.rc(B870, [rv(R870, booking_id="bk-taken")], others=others)
        self.assertEqual(res["code"], "drift")
        self.assertTrue(has_token(res, "RC-X"), "drift с обоими case_id: %r" % res)

    def test_anchor_two_rows_ambiguous(self):
        res = self.rc(B870, [R870, rv(R870, row=871)])
        self.assertEqual(res["code"], "ambiguous")

    def test_anchor_two_of_three_is_drift_I18(self):
        res = self.rc(B870, [rv(R870, date_start="2026-10-03 10:00")])
        self.assertEqual(res["code"], "drift")


# ================================================================================================================
# continuation — продолжение новой строкой (§6, DESIGN §2.4; I34; К4-C23; M25)
# ================================================================================================================

OB_I = {"case_id": "RC-I", "rental_id": 41, "plate": "6908", "bike_name": "NMAX 155 6908", "name_norm": "иван",
        "booking_id": "bk-812", "start_day": "2026-10-01", "end_day": "2026-10-12",
        "contacts": [{"channel": "wa", "value": IVAN_NUM, "status": "active", "source_kind": "crm"}]}


def new_row(start, end, name="Иван", contacts=IVAN_PHONE):
    return mk_row(901, "Бронь", "PCX 160 4410", name, start, end, contacts, "bk-901", "3000")


class TestContinuation(K4Case):

    def ct(self, row, bindings=(OB_I,), prm=None):
        res = self.pure(R.continuation, row, list(bindings), prm or PD)
        self.assertIsInstance(res, list)
        return res

    def ids(self, res):
        return [c.get("case_id") for c in res]

    def test_touch_by_return_day_is_question_when_gap_unknown(self):
        """§13: касание днём возврата при CONTINUATION_GAP_DAYS=UNKNOWN → кандидат (вопрос), why — param_unknown."""
        res = self.ct(new_row("2026-10-12 10:00", "2026-10-20 10:00"))
        self.assertEqual(self.ids(res), ["RC-I"])
        self.assertEqual(res[0].get("gap_days"), 0)
        self.assertIn("param_unknown:CONTINUATION_GAP_DAYS", str(res[0].get("why")))

    def test_overlap_is_candidate(self):
        res = self.ct(new_row("2026-10-10 10:00", "2026-10-20 10:00"))
        self.assertEqual(self.ids(res), ["RC-I"])
        self.assertEqual(res[0].get("gap_days"), -2)

    def test_gap_one_day_not_candidate(self):
        self.assertEqual(self.ct(new_row("2026-10-13 10:00", "2026-10-20 10:00")), [])

    def test_known_gap_parameter(self):
        self.assertEqual(self.ids(self.ct(new_row("2026-10-14 10:00", "2026-10-20 10:00"),
                                          prm=params(CONTINUATION_GAP_DAYS=2))), ["RC-I"])
        p = params(CONTINUATION_GAP_DAYS=-1)
        self.assertEqual(self.ct(new_row("2026-10-12 10:00", "2026-10-20 10:00"), prm=p), [], "−1: без касания")
        self.assertEqual(self.ids(self.ct(new_row("2026-10-11 10:00", "2026-10-20 10:00"), prm=p)), ["RC-I"])

    def test_contact_match_with_other_name(self):
        self.assertEqual(self.ids(self.ct(new_row("2026-10-12 10:00", "2026-10-20 10:00", name="Ivan P."))),
                         ["RC-I"])

    def test_other_name_other_contact_not_candidate(self):
        self.assertEqual(self.ct(new_row("2026-10-10 10:00", "2026-10-20 10:00", name="Борис",
                                         contacts=BORIS_PHONE)), [])

    def test_stub_names_do_not_match(self):
        ob = dict(OB_I, name_norm=None, contacts=[])
        self.assertEqual(self.ct(new_row("2026-10-10 10:00", "2026-10-20 10:00", name="—", contacts=BORIS_PHONE),
                                 [ob]), [], "имя-заглушка совпадением не считается")

    def test_superseded_contact_does_not_match(self):
        ob = dict(OB_I, contacts=[{"channel": "wa", "value": IVAN_NUM, "status": "superseded",
                                   "source_kind": "crm"}])
        self.assertEqual(self.ct(new_row("2026-10-10 10:00", "2026-10-20 10:00", name="Ivan P."), [ob]), [])

    def test_unknown_dates_candidate(self):
        res = self.ct(new_row(None, None))
        self.assertEqual(self.ids(res), ["RC-I"])
        self.assertIn("dates_unknown", str(res[0].get("why")))


# ================================================================================================================
# cash_claimants, bind_cash — касса (§6, DESIGN §3.5; I18, I35; К4-C7, К4-C24; M2, M19)
# ================================================================================================================

RENT_I = {"rental_id": 41, "id": 41, "case_id": "RC-I", "booking_id": "bk-812", "plate": "6908",
          "bike_name": "NMAX 155 6908", "start_day": "2026-10-01", "end_day": "2026-10-12", "crm_row_seen": 812,
          "row": 812, "status_seen": "В аренде", "name_norm": "иван", "anchor": "6908|2026-10-01|иван"}
RENT_B = {"rental_id": 52, "id": 52, "case_id": "RC-B", "booking_id": "bk-845", "plate": "6908",
          "bike_name": "NMAX 155 6908", "start_day": "2026-10-15", "end_day": "2026-10-20", "crm_row_seen": 845,
          "row": 845, "status_seen": "Бронь", "name_norm": "борис", "anchor": "6908|2026-10-15|борис"}
ROWS_6908 = [R812, R845, R790]


class TestCash(K4Case):

    def cl(self, fact, rows=ROWS_6908, prm=None):
        return rows_of(self.pure(R.cash_claimants, fact, list(rows), prm or PD))

    def bc(self, fact, rental=RENT_I, rows=ROWS_6908, prm=None, human=None):
        res = self.pure(R.bind_cash, fact, rental, list(rows), prm or PD, human)
        self.assertIn(res.get("code"), ("bound", "unbound", "unknown"), res)
        if res["code"] == "unknown":
            self.assertUnknownWellFormed(res, "bind_cash")
            self.assertIn(rcode(res.get("reason")), REASONS_OK, res)
        return res

    def test_claimants_include_future_booking_prestart_M19(self):
        """§13: касса «предоплата 6908» при брони с 15.10 → бронь — претендент (CASH_PRE_START_DAYS=UNKNOWN)."""
        self.assertEqual(self.cl(cash_fact("2026-10-05")), {812, 845})

    def test_claimants_post_end_and_prestart(self):
        self.assertEqual(self.cl(cash_fact("2026-10-14")), {812, 845})

    def test_finished_row_only_inside_its_term(self):
        self.assertEqual(self.cl(cash_fact("2026-09-10")), {790, 812, 845})
        self.assertEqual(self.cl(cash_fact("2026-09-20")), {812, 845}, "«Завершена» — только в сроке")

    def test_known_windows(self):
        """Известное окно сужает претендентов (UNKNOWN — шире, fail-closed); границы окна не испытываются."""
        self.assertEqual(self.cl(cash_fact("2026-10-05"), prm=params(CASH_PRE_START_DAYS=3)), {812})
        self.assertEqual(self.cl(cash_fact("2026-10-13"), prm=params(CASH_PRE_START_DAYS=3)), {812, 845})
        self.assertEqual(self.cl(cash_fact("2026-10-15"), prm=params(CASH_POST_END_DAYS=2)), {845})
        self.assertEqual(self.cl(cash_fact("2026-10-13"), prm=params(CASH_POST_END_DAYS=2)), {812, 845})

    def test_no_booking_two_claimants_unknown_M2_M19(self):
        res = self.bc(cash_fact("2026-10-05"))
        self.assertEqual(res["code"], "unknown", "касса без booking_id при будущей брони — претенденты (I35)")
        self.assertReason(res, "which_rental")
        self.assertMissingHas(res, "which_rental")
        self.assertEqual(rows_of(res.get("claimants")), {812, 845})

    def test_no_booking_single_claimant_bound(self):
        res = self.bc(cash_fact("2026-10-05"), prm=params(CASH_PRE_START_DAYS=3))
        self.assertEqual(res["code"], "bound")
        self.assertEqual(res.get("bound_by"), "plate+day")

    def test_no_booking_for_future_rental_unknown(self):
        res = self.bc(cash_fact("2026-10-14"), rental=RENT_B)
        self.assertEqual(res["code"], "unknown")

    def test_booking_id_agrees_bound(self):
        res = self.bc(cash_fact("2026-10-05", booking_id="bk-812"))
        self.assertEqual(res["code"], "bound")
        self.assertEqual(res.get("bound_by"), "booking_id")

    def test_booking_id_equal_but_before_start(self):
        res = self.bc(cash_fact("2026-09-28", booking_id="bk-812"))
        self.assertEqual(res["code"], "unknown")
        self.assertReason(res, "cash_pre_start")

    def test_booking_id_equal_but_other_plate(self):
        res = self.bc(cash_fact("2026-10-05", booking_id="bk-812", bike="PCX 160 4410"))
        self.assertEqual(res["code"], "unknown", "booking_id — сильный признак только в согласии с номером")
        self.assertMissingHas(res, "link_confirmation")

    def test_foreign_booking_id_inside_our_term_needs_confirmation(self):
        """§13 «чужая оплата»: касса с booking_id брони Бориса в день аренды Ивана → unknown (K4-C24)."""
        res = self.bc(cash_fact("2026-10-05", booking_id="bk-845"))
        self.assertEqual(res["code"], "unknown")
        self.assertMissingHas(res, "link_confirmation")

    def test_foreign_booking_id_outside_term_unbound(self):
        res = self.bc(cash_fact("2026-10-16", booking_id="bk-845"))
        self.assertEqual(res["code"], "unbound")
        self.assertReason(res, "cash_other_booking")
        res = self.bc(cash_fact("2026-10-05", booking_id="bk-845", bike="PCX 160 4410"))
        self.assertEqual(res["code"], "unbound", "другой booking_id и другой номер — не наша")

    def test_human_bind(self):
        res = self.bc(cash_fact("2026-10-05"), human={"bind": True})
        self.assertEqual(res["code"], "bound")
        self.assertEqual(res.get("bound_by"), "human")

    def test_cash_without_day_not_bound(self):
        """DESIGN §9.0: касса байка без дня — не привязка."""
        res = self.bc(cash_fact(None))
        self.assertNotEqual(res["code"], "bound")


# ================================================================================================================
# answer_verdict — порядок проверок §4.7 (I9, I14, I16, I39; К4-C9, К4-C28; M3, M9, M30)
# ================================================================================================================


class TestAnswerVerdict(K4Case):

    def av(self, ctx, prm=None):
        e, c, p, a = ctx
        prm = dict(prm or PS)
        prm.setdefault("boot_id", a.get("boot_id"))   # boot_id принимающего Store (§4.7 п.9) — надмножество
        v = self.pure(R.answer_verdict, e, c, p, a, prm)
        self.assertIsInstance(v, str)
        return v

    def assertVerdict(self, ctx, expected, prm=None, msg=""):
        v = self.av(ctx, prm)
        self.assertEqual(v, expected, msg)
        self.assertIn(v, VERDICTS)

    # baseline
    def test_accepted_staff_question(self):
        self.assertVerdict(staff_ctx(), "accepted")

    def test_ttl_unknown_time_does_not_decide_I14(self):
        """п.9: ANSWER_TTL=UNKNOWN — время ответа не решает; эскалация не обесценивает ответ."""
        self.assertVerdict(staff_ctx(ans={"at": T_POST + 48 * 3600}), "accepted")
        self.assertVerdict(staff_ctx(exp={"state": "escalated"}, ans={"at": T_POST + 48 * 3600}), "accepted")
        for st in ("escalating", "escalation_unknown"):
            self.assertVerdict(staff_ctx(exp={"state": st}), "accepted", msg=st)

    # п.1
    def test_bot_or_empty_is_not_reply(self):
        for ans in ({"is_bot": True}, {"text": ""}):
            v = self.av(staff_ctx(ans=ans))
            self.assertNotEqual(v, "accepted")
            self.assertIn("not_reply", v, ans)

    def test_staff_without_reply_to_is_not_reply(self):
        e, c, p, a = staff_ctx(ans={"reply_to": None, "reply_to_is_bot": False})
        v = self.av((e, c, None, a))
        self.assertIn("not_reply", v)

    def test_approval_without_reply_unknown_param_is_reference_no_reply_I39(self):
        """п.1: APPROVAL_REPLY_REQUIRED=UNKNOWN и слово решения → справка reference_no_reply (fail-closed)."""
        ctx = approval_ctx(ans={"reply_to": None, "reply_to_is_bot": False, "text": "да"})
        self.assertVerdict(ctx, "reference_no_reply")
        v = self.av(approval_ctx(ans={"reply_to": None, "reply_to_is_bot": False, "text": "когда?"}))
        self.assertIn("not_reply", v, "unclear без реплая → not_reply")
        v = self.av(approval_ctx(ans={"reply_to": None, "reply_to_is_bot": False, "text": "да"}),
                    prm=dict(PS, APPROVAL_REPLY_REQUIRED=True))
        self.assertIn("not_reply", v)

    # п.2
    def test_post_not_found_is_not_linked_or_orphan(self):
        e, c, p, a = staff_ctx(ans={"reply_to": "6999"})
        v = self.av((e, c, None, a))
        self.assertNotEqual(v, "accepted")
        self.assertTrue("not_linked" in v or "orphan" in v, v)

    # п.4
    def test_terminal_states_are_references(self):
        for st, verdict in (("superseded", "reference_superseded"), ("cancelled", "reference_cancelled"),
                            ("answered", "reference_answered")):
            self.assertVerdict(staff_ctx(exp={"state": st}), verdict)
            # п.4 раньше п.7: не адресат при отозванном ожидании — всё равно справка о состоянии
            self.assertVerdict(staff_ctx(exp={"state": st}, ans={"author_id": 5555}), verdict)

    # п.5
    def test_foreign_place_thread_and_topic_bike_M9(self):
        self.assertVerdict(staff_ctx(ans={"thread_id": "56"}), "reference_foreign_place")
        self.assertVerdict(staff_ctx(post={"topic_bike": "7001"}), "reference_foreign_place")
        self.assertVerdict(staff_ctx(post={"topic_bike": None}), "reference_foreign_place",
                           msg="topic_bike IS NULL у места topic → чужое место (К4-C9)")
        self.assertVerdict(staff_ctx(case={"plate": "7001", "current_plate": "7001",
                                           "rental": dict(mk_case()["rental"], plate="7001"),
                                           "current": dict(mk_case()["rental"], plate="7001"),
                                           "binding": dict(mk_case()["rental"], plate="7001")}),
                           "reference_foreign_place", msg="байк поменялся после поста")
        # п.5 раньше п.7 и п.8
        self.assertVerdict(staff_ctx(ans={"thread_id": "56", "author_id": 5555}), "reference_foreign_place")
        self.assertVerdict(staff_ctx(ans={"thread_id": "56"}, case={"ver": 2}), "reference_foreign_place")

    def test_delivery_place_checked_too(self):
        ctx = staff_ctx(post={"chat": CHAT_DELIVERY, "msg_id": "7002", "place": "delivery", "thread_id": None,
                              "addressee_ids": Addr([9002])},
                        ans={"chat": CHAT_DELIVERY, "reply_to": "7002", "thread_id": None, "author_id": 9002})
        self.assertVerdict(ctx, "accepted", msg="ответ адресата Delivery по посту Delivery (§13)")
        e, c, p, a = ctx
        p2 = dict(p, topic_bike="7001")
        self.assertVerdict((e, c, p2, a), "reference_foreign_place")

    def test_place_check_only_for_topic_and_delivery(self):
        ctx = staff_ctx(exp={"place": "agents"},
                        post={"place": "agents", "thread_id": "1", "topic_bike": None,
                              "addressee_ids": Addr([9003])},
                        ans={"thread_id": "2", "author_id": 9003})
        self.assertVerdict(ctx, "accepted", msg="у «Агентов» тема и байк темы не сверяются")

    # п.6
    def test_link_drift_is_reference_drift(self):
        for ls in ("drift", "missing", "ambiguous"):
            self.assertVerdict(staff_ctx(case={"link_state": ls}), "reference_drift", msg=ls)
        # п.6 раньше п.7
        self.assertVerdict(staff_ctx(case={"link_state": "drift"}, ans={"author_id": 5555}), "reference_drift")

    def test_drift_not_applied_outside_topic_delivery(self):
        ctx = staff_ctx(exp={"place": "agents"}, case={"link_state": "drift"},
                        post={"place": "agents", "topic_bike": None, "addressee_ids": Addr([9003])},
                        ans={"author_id": 9003})
        self.assertVerdict(ctx, "accepted")

    # п.7
    def test_author_unverified_when_addressees_unknown(self):
        self.assertVerdict(staff_ctx(post={"addressee_ids": "UNKNOWN"}), "reference_author_unverified")
        # п.7 раньше п.8
        self.assertVerdict(staff_ctx(post={"addressee_ids": "UNKNOWN"}, case={"ver": 2}),
                           "reference_author_unverified")

    def test_foreign_author_and_nick_not_used_M9(self):
        self.assertVerdict(staff_ctx(ans={"author_id": 5555}), "reference_foreign_author")
        self.assertVerdict(staff_ctx(ans={"author_id": None, "author_username": "staff_9001"}),
                           "reference_foreign_author", msg="ник без id — не автор (I9)")
        self.assertVerdict(staff_ctx(ans={"author_id": "9001"}), "reference_foreign_author",
                           msg="author_id не int — не автор (§4.7 п.7)")
        self.assertVerdict(staff_ctx(ans={"author_username": "кто-то другой"}), "accepted",
                           msg="ник не участвует и в обратную сторону")

    def test_approval_author_must_be_approver(self):
        self.assertVerdict(approval_ctx(ans={"author_id": 5555}), "reference_foreign_author")

    # п.8
    def test_stale_version_M3(self):
        self.assertVerdict(staff_ctx(case={"ver": 2}), "reference_stale_version")
        # п.8 раньше п.9
        self.assertVerdict(approval_ctx(case={"ver": 2}, ans={"at": T_POST + 1801}), "reference_stale_version")

    # п.9
    def test_approval_ttl_activate_close(self):
        for action in ("activate", "close"):
            self.assertVerdict(approval_ctx(action, ans={"at": T_POST + 1800}), "accepted", msg=action)
            self.assertVerdict(approval_ctx(action, ans={"at": T_POST + 1801}), "reference_late", msg=action)
            self.assertVerdict(approval_ctx(action, ans={"at": T_POST + 31 * 60}), "reference_late",
                               msg="§13: «да» на активацию через 31 мин → late")
        # п.9 раньше п.10
        self.assertVerdict(approval_ctx(ans={"at": T_POST + 1801, "text": "когда?"}), "reference_late")

    def test_booking_card_no_1800_same_boot_M30(self):
        """I39: у карточки брони срока 1800 нет — сутки спустя в том же запуске принято."""
        self.assertVerdict(approval_ctx("booking", ans={"at": T_POST + 86400}), "accepted")

    def test_booking_card_after_restart_I39(self):
        self.assertVerdict(approval_ctx("booking", ans={"at": T_POST + 120}, boot="BOOT-B"), "reference_restart")

    def test_restart_boundary_only_for_booking(self):
        """§4.7 п.9: граница запуска — только у approval/booking при UNKNOWN; у activate решает срок 1800."""
        self.assertVerdict(approval_ctx("activate", ans={"at": T_POST + 120}, boot="BOOT-B"), "accepted")

    def test_answer_ttl_known_expires_staff_answer(self):
        prm = dict(PS, ANSWER_TTL=600)
        self.assertVerdict(staff_ctx(ans={"at": T_POST + 601}), "reference_expired", prm=prm)
        self.assertVerdict(staff_ctx(ans={"at": T_POST + 600}), "accepted", prm=prm)

    # п.10
    def test_unclear_approval_and_confirm_link(self):
        self.assertVerdict(approval_ctx(ans={"text": "когда?"}), "reference_unclear")
        self.assertVerdict(approval_ctx(ans={"text": "посмотрю"}), "reference_unclear")
        self.assertVerdict(approval_ctx(kind="confirm_link", ans={"text": "когда?"}), "reference_unclear")

    def test_unclear_text_irrelevant_for_staff_question(self):
        self.assertVerdict(staff_ctx(ans={"text": "когда?"}), "accepted")

    # п.11
    def test_refusal_is_still_accepted_verdict(self):
        """Вердикт — про ответ, решение — отдельно: «нет» реплаем одобряющего → accepted (decision=no)."""
        self.assertVerdict(approval_ctx(ans={"text": "нет, не закрывай"}), "accepted")
        self.assertVerdict(approval_ctx(kind="confirm_link", ans={"text": "да"}), "accepted")


# ================================================================================================================
# Слова §4.8 — approval_decision, accept_decision (I39; К4-C28; DESIGN §6.4, §6.6)
# ================================================================================================================


class TestWords(K4Case):

    GOLDENS = (("да", "yes"), ("да 35200", "yes"), ("Да.", "yes"), ("подтверждаю", "yes"), ("завершай", "yes"),
               ("ок", "yes"), ("не ставь", "no"), ("нет, не закрывай", "no"), ("да, но не активируй до оплаты", "no"),
               ("не завершай пока", "no"), ("отклоняю", "no"), ("отмена", "no"), ("когда?", "unclear"),
               ("посмотрю", "unclear"))

    def ad(self, text, prm=None):
        return self.pure(R.approval_decision, text, prm or PD)

    def test_goldens_section4_8(self):
        for text, expected in self.GOLDENS:
            self.assertEqual(self.ad(text), expected, "голден §4.8: %r" % text)

    def test_refusal_first(self):
        for text in ("да нет", "ДА, НЕТ", "нетушки", "не да", "не подтверждаю", "ок, отклоняю", "закрывай. отмена",
                     "ставь… хотя нет"):
            self.assertEqual(self.ad(text), "no", text)

    def test_yes_whole_word_only(self):
        for text in ("дай подумать", "дальше", "окно", "окей", "надо", "доклад"):
            self.assertEqual(self.ad(text), "unclear", "«да/ок» — только целым словом: %r" % text)
        for text in ("ДА!", "Ок", "закрывай", "активируй", "заверши"):
            self.assertEqual(self.ad(text), "yes", text)
        # APPROVEFIX1610 (карта М4, Codex TB-OWNER-EFFICIENCY-1610-2054): прежний голден «ёлки, да», «подтверждено»,
        # «ставь бронь» → yes пересмотрен осознанно — постороннее слово рядом с согласием и форма-состояние основы
        # («подтверждено») согласием не являются (как у строгой брони intake_confirm: ASK, test_intake_confirm TRAPS)
        for text in ("ёлки, да", "подтверждено", "ставь бронь"):
            self.assertEqual(self.ad(text), "unclear", text)

    def test_word_lists_come_from_params(self):
        """§4.8/§10: списки слов — параметры; нормализация ё→е применяется к тексту."""
        prm = params(APPROVAL_YES_WORDS=("угу", "еще"), APPROVAL_YES_STEMS=(), APPROVAL_NO_STEMS=("неа",),
                     APPROVAL_NO_AFTER_NE=())
        self.assertEqual(self.ad("угу", prm), "yes")
        self.assertEqual(self.ad("ЕЩЁ", prm), "yes", "ё→е до сравнения слов")
        self.assertEqual(self.ad("неа", prm), "no")
        self.assertEqual(self.ad("не угу", prm), "no", "«не» + слово согласия — отказ")
        self.assertEqual(self.ad("да", prm), "unclear")

    def test_accept_decision_unknown_is_always_unclear_I16(self):
        """§4.8, DESIGN §6.4: ACCEPT_WORDS=UNKNOWN → unclear всегда (ступень 3 — только human_mark)."""
        for text in ("да", "принял", "ок", "готов", "нет"):
            self.assertEqual(self.pure(R.accept_decision, text, PD), "unclear", text)

    def test_accept_decision_known_refusal_first(self):
        prm = params(ACCEPT_WORDS=frozenset({"принял"}), ACCEPT_NO_STEMS=("нет",), ACCEPTANCE_SIGNAL=frozenset({
            "readiness"}))
        self.assertEqual(R.accept_decision("принял", prm), "yes")
        self.assertEqual(R.accept_decision("Принял, едем", prm), "yes")
        self.assertEqual(R.accept_decision("нет, не принял", prm), "no")
        self.assertEqual(R.accept_decision("посмотрю", prm), "unclear")


# ================================================================================================================
# stage_allowed — ступени и свидетельства (§3.6, §6; I10, I11, I27, I44; К4-C10, К4-C26; M6, M16, M24, M29)
# ================================================================================================================

BIND_B = {"rental_id": 52, "id": 52, "case_id": "RC-B", "plate": "6908", "bike_name": "NMAX 155 6908",
          "booking_id": "bk-845", "anchor": "6908|2026-10-15|борис", "name_norm": "борис", "start_day": "2026-10-15",
          "end_day": "2026-10-20", "start_at": "2026-10-15 10:00", "end_at": "2026-10-20 10:00",
          "crm_row_seen": 845, "row": 845, "status_seen": "Бронь", "current": 1}
T_TASK = ts(2026, 10, 15, 9, 0)
ANSWERS = {5: {"id": 5, "answer_id": 5, "exp_id": "RE-1", "task_id": "RT-H", "exp_task_id": "RT-H",
               "case_id": "RC-B", "chat": CHAT_TOPIC, "msg_id": "7010", "reply_to": "7001", "verdict": "accepted",
               "promoted_by": None, "case_ver_at": 1, "decision": "unclear", "author_id": 9001,
               "post_role": "question"}}
P1 = frozenset({"question_sent"})
P2 = P1 | {"answer_received"}
P3 = P2 | {"task_accepted"}
P4 = P3 | {"physically_done"}
P5 = P4 | {"result_recorded"}
PS_TOPIC = dict(PS, PHYSICAL_DONE_SOURCES=dict({k: UNKNOWN for k in TASK_KINDS}, handover=frozenset({"topic_event"})))


def st_task(kind="handover", top=3, case_ver=1, state="open", created=T_TASK):
    return {"task_id": "RT-H", "case_id": "RC-B", "kind": kind, "state": state, "top_stage": top, "rental_id": 52,
            "case_ver": case_ver, "created_at": created, "updated_at": created, "row_ver": 1, "reason": None}


def ev_human(act="btn:done:1", author=1001):
    return {"kind": "human_mark", "author_id": author, "act_ref": act, "note": "сделано", "ref": act}


def ev_topic(bike="6908", at=None, ref="topic:55:9101"):
    return {"kind": "topic_event", "bike": bike, "type": "выдача", "at": at if at is not None else ts(2026, 10, 15,
                                                                                                        10, 30),
            "ref": ref}


def ev_crm(row=845, booking_id="bk-845", read_at=None):
    return {"kind": "crm_status_read", "booking_id": booking_id, "status": "В аренде", "row": row,
            "read_at": read_at if read_at is not None else ts(2026, 10, 15, 10, 40), "ref": "crm:%s:read" % row}


def ev_readback(outcome="landed", written=None, read=None):
    w = written if written is not None else ts(2026, 10, 15, 10, 35)
    return {"kind": "readback", "source": "crm", "ref": "строка 845", "written_at": w,
            "read_at": read if read is not None else w + 30, "outcome": outcome, "expected": "В аренде",
            "got": "В аренде" if outcome == "landed" else None, "target": {"row": 845, "status": "В аренде"}}


class TestStageAllowed(K4Case):

    def sa(self, stage, evidence, prior=P3, used=frozenset(), answers=None, other=(R812, R790), prm=None,
           task=None, bnd=None):
        res = self.pure(R.stage_allowed, task or st_task(), bnd or BIND_B, stage, evidence, prior, used,
                        answers if answers is not None else ANSWERS, list(other), prm or PS_TOPIC)
        self.assertIsInstance(res, tuple)
        self.assertEqual(len(res), 2)
        ok, code = res
        self.assertIsInstance(ok, bool)
        if not ok:
            self.assertIn(rcode(code), ("evidence_forbidden", "evidence_foreign", "evidence_missing", "order",
                                        "param_unknown", "readback_mismatch", "not_delivered"),
                          "код stage_allowed вне §6: %r" % (code,))
        return ok, rcode(code)

    def assertDenied(self, res, *codes):
        ok, code = res
        self.assertFalse(ok, "ступень разрешена, а не должна (%r)" % (codes,))
        if codes:
            self.assertIn(code, codes)

    # ступень 2
    def test_answer_of_this_task(self):
        ok, _ = self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"}, prior=P1,
                        task=st_task(top=1))
        self.assertTrue(ok)

    def test_answer_of_other_task_is_foreign_I27(self):
        answers = {5: dict(ANSWERS[5], task_id="RT-OTHER", exp_task_id="RT-OTHER")}
        self.assertDenied(self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"}, prior=P1,
                                  answers=answers, task=st_task(top=1)), "evidence_foreign")

    def test_answer_reference_not_promoted_denied(self):
        answers = {5: dict(ANSWERS[5], verdict="reference_author_unverified")}
        self.assertDenied(self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"}, prior=P1,
                                  answers=answers, task=st_task(top=1)))
        answers = {5: dict(ANSWERS[5], verdict="reference_author_unverified", promoted_by="1001")}
        ok, _ = self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"}, prior=P1,
                        answers=answers, task=st_task(top=1))
        self.assertTrue(ok, "справка, принятая одобряющим (promoted_by), годится для ступени 2")

    def test_answer_other_version_denied(self):
        answers = {5: dict(ANSWERS[5], case_ver_at=2)}
        self.assertDenied(self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"}, prior=P1,
                                  answers=answers, task=st_task(top=1)))

    def test_answer_before_question_is_order(self):
        self.assertDenied(self.sa("answer_received", {"kind": "answer", "answer_id": 5, "ref": "ans:5"},
                                  prior=frozenset(), task=st_task(top=0)), "order")

    def test_wrong_kind_for_stage(self):
        self.assertDenied(self.sa("answer_received", ev_human("btn:x:1"), prior=P1, task=st_task(top=1)))

    # ступень 3
    def test_task_accepted_by_human_mark(self):
        ok, _ = self.sa("task_accepted", ev_human("btn:accept:1"), prior=P2, task=st_task(top=2))
        self.assertTrue(ok)
        self.assertDenied(self.sa("task_accepted", ev_human("btn:accept:1", author=5555), prior=P2,
                                  task=st_task(top=2)))
        self.assertDenied(self.sa("task_accepted", ev_human("btn:accept:1"), prior=frozenset(),
                                  task=st_task(top=0)), "order")

    def test_staff_accept_reply_needs_known_signal_I16(self):
        ev = {"kind": "staff_accept_reply", "answer_id": 5, "ref": "acc:5"}
        answers = {5: dict(ANSWERS[5], decision="yes")}
        self.assertDenied(self.sa("task_accepted", ev, prior=P2, answers=answers, task=st_task(top=2)),
                          "param_unknown", "evidence_forbidden")

    # ступень 4
    def test_physically_done_forbidden_kinds_I10_M6_M29(self):
        for kind in ("staff_answer", "approval_yes", "agent_text", "bike_state"):
            ev = {"kind": kind, "ref": "x:%s" % kind, "answer_id": 5, "text": "готово", "bike": "6908",
                  "status": "в аренде"}
            self.assertDenied(self.sa("physically_done", ev), "evidence_forbidden")
            self.assertDenied(self.sa("result_recorded", ev, prior=P4), "evidence_forbidden")

    def test_physically_done_crm_status_read_forbidden_for_handover_return_I10(self):
        for kind in ("handover", "return"):
            self.assertDenied(self.sa("physically_done", ev_crm(), task=st_task(kind=kind)), "evidence_forbidden")

    def test_human_mark_with_answer_ref_forbidden_M24(self):
        act = "%s:%s" % (CHAT_TOPIC, "7010")
        self.assertDenied(self.sa("physically_done", ev_human(act)), "evidence_forbidden")
        self.assertDenied(self.sa("task_accepted", ev_human(act), prior=P2, task=st_task(top=2)),
                          "evidence_forbidden")

    def test_human_mark_physically_done(self):
        ok, _ = self.sa("physically_done", ev_human())
        self.assertTrue(ok)
        ok, _ = self.sa("physically_done", ev_human(), prior=P2, task=st_task(top=2))
        self.assertTrue(ok, "4 без 3 — с флагом without_acceptance, но допустимо")
        self.assertDenied(self.sa("physically_done", ev_human(author=5555)))

    def test_topic_event_needs_known_source(self):
        self.assertDenied(self.sa("physically_done", ev_topic(), prm=PS), "param_unknown", "evidence_forbidden")

    def test_topic_event_binding_rules_I27(self):
        ok, _ = self.sa("physically_done", ev_topic())
        self.assertTrue(ok, "событие темы с ref, номером привязки и временем в сроке")
        self.assertDenied(self.sa("physically_done", ev_topic(bike="7001")))
        self.assertDenied(self.sa("physically_done", ev_topic(at=ts(2026, 10, 15, 8, 0))), )   # раньше задачи
        self.assertDenied(self.sa("physically_done", ev_topic(at=ts(2026, 10, 21, 10, 0))))   # вне срока аренды
        self.assertDenied(self.sa("physically_done", ev_topic(ref="")), "evidence_missing")
        self.assertDenied(self.sa("physically_done", ev_topic(), used=frozenset({"topic:55:9101"})))
        kira = mk_row(885, "Бронь", "NMAX 155 6908", "Кира", "2026-10-15 08:00", "2026-10-15 18:00", KIRA_PHONE,
                      "bk-885")
        self.assertDenied(self.sa("physically_done", ev_topic(), other=(R812, kira)),)   # в сроке другой строки

    def test_used_ref_is_foreign(self):
        self.assertDenied(self.sa("physically_done", ev_human(), used=frozenset({"btn:done:1"})))

    # ступень 5
    def test_result_without_physically_done_is_order_I11_M16(self):
        self.assertDenied(self.sa("result_recorded", ev_crm(), prior=P3), "order")
        self.assertDenied(self.sa("result_recorded", ev_readback(), prior=P3), "order", "readback_mismatch")

    def test_result_crm_status_read_handover(self):
        ok, _ = self.sa("result_recorded", ev_crm(), prior=P4, task=st_task(top=4))
        self.assertTrue(ok, "crm_status_read handover: booking_id привязки, read_at > created_at, row = crm_row_seen")
        self.assertDenied(self.sa("result_recorded", ev_crm(row=812), prior=P4, task=st_task(top=4)))
        self.assertDenied(self.sa("result_recorded", ev_crm(booking_id="bk-812"), prior=P4, task=st_task(top=4)))
        self.assertDenied(self.sa("result_recorded", ev_crm(read_at=T_TASK - 60), prior=P4, task=st_task(top=4)))
        self.assertDenied(self.sa("result_recorded", ev_crm(), prior=P4, task=st_task(kind="readiness", top=4)))

    def test_result_readback_must_be_landed_and_read_after_write(self):
        self.assertDenied(self.sa("result_recorded", ev_readback("absent"), prior=P4, task=st_task(top=4)))
        self.assertDenied(self.sa("result_recorded", ev_readback("unknown"), prior=P4, task=st_task(top=4)))
        w = ts(2026, 10, 15, 10, 35)
        self.assertDenied(self.sa("result_recorded", ev_readback(written=w, read=w), prior=P4, task=st_task(top=4)))

    def test_result_place_unknown_for_readiness(self):
        """RESULT_RECORD_PLACE[readiness]=UNKNOWN → ступень 5 невозможна (param_unknown)."""
        self.assertDenied(self.sa("result_recorded", ev_readback(), prior=P4, task=st_task(kind="readiness", top=4),
                                  prm=PD), "param_unknown")

    # ступень 6
    def test_client_notified_only_delivered(self):
        ev = {"kind": "wa_delivery", "notice_id": "RN-1", "wamid": "wamid.X", "status": "sent",
              "at": ts(2026, 10, 15, 11), "ref": "wamid.X"}
        self.assertDenied(self.sa("client_notified", ev, prior=P5, task=st_task(top=5, state="done")))
        self.assertDenied(self.sa("client_notified", ev_human("btn:notify:1"), prior=P5,
                                  task=st_task(top=5, state="done")))


# ================================================================================================================
# required_obligations — обязательный набор (§3.4, DESIGN §7.3; I25, I26; К4-C27; M15)
# ================================================================================================================


def find_obl(lst, kind, role):
    return [o for o in lst if o.get("kind") == kind and o.get("role") == role]


def why_of(o):
    return str(o.get("why") or o.get("reason") or "")


class TestRequiredObligations(K4Case):

    def ro(self, row, prm=None):
        res = self.pure(R.required_obligations, row, prm or PD)
        self.assertIsInstance(res, list)
        self.assertTrue(res, "обязательный набор не пуст (M15)")
        for o in res:
            self.assertNotEqual(o.get("role"), "promise", "роль promise снята")
            if o.get("kind") == "money":
                self.assertNotEqual(o.get("outcome"), "valid", "I26: сумма клетки известной не считается")
                self.assertIn(o.get("outcome"), ("unknown", "incomplete"))
            self.assertIn(o.get("state"), ("open", "unknown"))
            d = DIRECTION.get((o.get("kind"), o.get("role")))
            if d and o.get("direction") is not None:
                self.assertEqual(o.get("direction"), d, o)
        return res

    def one(self, lst, kind, role):
        found = find_obl(lst, kind, role)
        self.assertEqual(len(found), 1, "%s/%s: %r" % (kind, role, lst))
        return found[0]

    def test_booking_with_passport_deposit_section14_D2(self):
        res = self.ro(R845)
        self.assertEqual(self.one(res, "bike", "handover")["state"], "open")
        self.assertEqual(self.one(res, "bike", "return")["state"], "open")
        rent = self.one(res, "money", "rent")
        self.assertEqual((rent["state"], rent["outcome"]), ("unknown", "unknown"), "клетки 0/пусто → unknown")
        dep = self.one(res, "money", "deposit")
        self.assertEqual((dep["state"], dep["outcome"]), ("unknown", "unknown"))
        self.assertIn("deposit_passport", why_of(dep))
        self.one(res, "document", "passport_return")
        self.assertEqual(find_obl(res, "money", "deposit_refund"), [], "денежного залога строка не называет")
        fin = self.one(res, "client", "notify_final")
        self.assertEqual(fin["state"], "unknown")
        self.assertIn("param_unknown:FINAL_NOTICE_REQUIRED", why_of(fin))

    def test_active_with_numeric_deposit_and_rent_cell(self):
        res = self.ro(rv(R812, to_pay=4900))
        self.assertEqual(find_obl(res, "bike", "handover"), [], "handover — только при «Бронь»")
        self.assertEqual(self.one(res, "bike", "return")["state"], "open")
        rent = self.one(res, "money", "rent")
        self.assertEqual((rent["state"], rent["outcome"]), ("open", "incomplete"))
        dep = self.one(res, "money", "deposit")
        self.assertEqual((dep["state"], dep["outcome"]), ("open", "incomplete"))
        ref = self.one(res, "money", "deposit_refund")
        self.assertEqual((ref["state"], ref["outcome"]), ("open", "incomplete"))
        self.assertEqual(find_obl(res, "document", "passport_return"), [])

    def test_debt_cell_counts_as_number(self):
        rent = self.one(self.ro(rv(R812, to_pay=0, debt=4900)), "money", "rent")
        self.assertEqual(rent["state"], "open")

    def test_finished_row_has_no_bike_obligations(self):
        res = self.ro(R790)
        self.assertEqual(find_obl(res, "bike", "handover") + find_obl(res, "bike", "return"), [])
        self.one(res, "money", "rent")
        self.one(res, "money", "deposit")

    def test_empty_or_garbage_deposit_unknown(self):
        for raw in ("", "три тысячи"):
            res = self.ro(rv(R812, deposit_raw=raw, deposit=0))
            dep = self.one(res, "money", "deposit")
            self.assertEqual((dep["state"], dep["outcome"]), ("unknown", "unknown"), raw)
            self.assertEqual(find_obl(res, "money", "deposit_refund"), [], raw)

    def test_final_notice_parameter(self):
        self.assertEqual(self.one(self.ro(R812, params(FINAL_NOTICE_REQUIRED=True)), "client", "notify_final")
                         ["state"], "open")
        self.assertEqual(find_obl(self.ro(R812, params(FINAL_NOTICE_REQUIRED=False)), "client", "notify_final"), [])


# ================================================================================================================
# bike_state_fact — справка о байке (§6; I44; К4-C37; M29)
# ================================================================================================================

BIND_I = {"rental_id": 41, "id": 41, "case_id": "RC-I", "plate": "6908", "bike_name": "NMAX 155 6908",
          "booking_id": "bk-812", "status_seen": "В аренде", "start_day": "2026-10-01", "end_day": "2026-10-12",
          "crm_row_seen": 812}


def state_item(**kw):
    d = {"bike": "NMAX 155 6908", "status": "в аренде", "location": "", "booking_id": "bk-812", "client": "Иван",
         "date_out": "2026-10-01", "date_due": "2026-10-12", "date_back": "", "service_name": "",
         "last_event_msg_id": "", "updated": "2026-10-01 10:05"}
    d.update(kw)
    return d


class TestBikeStateFact(K4Case):

    def bs(self, item, bnd=BIND_I):
        return self.pure(R.bike_state_fact, item, bnd)

    def test_value_and_observed_at(self):
        res = self.bs(state_item())
        val = res.get("value") or {}
        for k in ("status", "location", "updated", "date_due", "booking_id_seen", "client_seen"):
            self.assertIn(k, val, "value.%s (§6 bike_state_fact)" % k)
        self.assertEqual(val["booking_id_seen"], "bk-812")
        self.assertEqual(val["client_seen"], "Иван")
        self.assertEqual(set(res.get("flags") or []), set())
        self.assertIn(res.get("observed_at"), ("2026-10-01 10:05", ts(2026, 10, 1, 10, 5)),
                      "observed_at = updated листа, а не время чтения")

    def test_foreign_booking_flag(self):
        self.assertIn("foreign_booking", self.bs(state_item(booking_id="bk-999")).get("flags") or [])
        self.assertNotIn("foreign_booking", self.bs(state_item(booking_id="")).get("flags") or [])

    def test_status_mismatch_flag(self):
        res = self.bs(state_item(), dict(BIND_I, status_seen="Бронь"))
        self.assertIn("status_mismatch", res.get("flags") or [])

    def test_foreign_bike(self):
        self.assertEqual(self.bs(state_item(bike="PCX 160 4410")).get("code"), "foreign_bike")


# ================================================================================================================
# obligation_verdict — закрытие обязательств (§6, DESIGN §7.4; I14, I26, I45; К4-C27; M14, M14b)
# ================================================================================================================

WANT_RENT = {"state": "open", "amount": 4900, "currency": "THB", "direction": "from_client", "outcome": "valid",
             "kind": "money", "role": "rent"}
CASH_OK = {"fact_id": 77, "id": 77, "kind": "cash", "state": "valid", "case_id": "RC-I", "rental_id": 41,
           "role": "оплата аренды", "amount": 4900, "currency": "THB", "bound_by": "booking_id", "row": 2041,
           "msg_id": "m-2041", "booking_id": "bk-812"}
SECOND_OK = {"document_id": 9, "id": 9, "kind": "contract_signed", "status": "verified", "case_id": "RC-I",
             "rental_id": 41, "booking_id": "bk-812", "rental_booking_id": "bk-812", "ext_id": "doc-233"}
BIND_W = {"rental_id": 41, "booking_id": "bk-812"}
P_CR = params(MONEY_CLOSE_RULE="cash_and_second_source")


def write_(cash=None, second="ok", bnd=None):
    return {"cash": dict(CASH_OK, **(cash or {})),
            "second": dict(SECOND_OK) if second == "ok" else second,
            "binding": dict(bnd if bnd is not None else BIND_W)}


class TestObligationVerdict(K4Case):

    def ov(self, kind, role, want, write=None, cell=None, human=None, prm=None):
        res = self.pure(R.obligation_verdict, kind, role, want, write=write, cell=cell, human=human,
                        params=prm or PD)
        self.assertIn(res.get("state"), ("open", "closed", "unknown", "waived"), res)
        self.assertIn(res.get("by"), ("write", "stage", "human", "", None), res)
        if res["state"] != "closed":
            self.assertNotEqual(res.get("by"), "write")
        return res

    def assertNotClosed(self, res, want_state=None):
        self.assertNotEqual(res["state"], "closed", res)
        if want_state is not None:
            self.assertEqual(res["state"], want_state, res)

    def test_write_does_not_close_when_rule_unknown_I45_M14b(self):
        for st in ("open", "unknown"):
            res = self.ov("money", "rent", dict(WANT_RENT, state=st), write=write_())
            self.assertNotClosed(res, st)
            self.assertEqual(res.get("why"), "param_unknown:MONEY_CLOSE_RULE")
        res = self.ov("money", "deposit", dict(WANT_RENT, role="deposit"), write=write_())
        self.assertNotClosed(res, "open")
        self.assertTrue(str(res.get("why")).startswith("param_unknown"), res)

    def test_write_closes_rent_with_cash_and_second_source(self):
        res = self.ov("money", "rent", WANT_RENT, write=write_(), prm=P_CR)
        self.assertEqual((res["state"], res["by"]), ("closed", "write"))

    def test_write_needs_every_condition_M14b(self):
        cases = [
            (("money", "deposit", dict(WANT_RENT, role="deposit"), write_()), "role_not_rent"),
            (("money", "rent", WANT_RENT, write_(second=None)), "second_source_missing"),
            (("money", "rent", dict(WANT_RENT, outcome="incomplete"), write_()), "want_not_valid"),
            # у привязки нет booking_id (и у договора его нет — «None == None» совпадением не считается)
            (("money", "rent", WANT_RENT,
              write_(second=dict(SECOND_OK, booking_id=None, rental_booking_id=None),
                     bnd={"rental_id": 41, "booking_id": None})), "booking_id_missing"),
        ]
        for (kind, role, want, w), why in cases:
            res = self.ov(kind, role, want, write=w, prm=P_CR)
            self.assertNotClosed(res, want["state"])
            self.assertEqual(res.get("why"), why)

    def test_write_rejects_weak_sources(self):
        bad = [
            write_(second=dict(SECOND_OK, status="unverified")),
            write_(second=dict(SECOND_OK, kind="contract_pdf")),
            write_(second=dict(SECOND_OK, booking_id="bk-999", rental_booking_id="bk-999", rental_id=99)),
            write_(cash={"role": "залог"}),
            write_(cash={"state": "revoked"}),
            write_(cash={"rental_id": 99, "case_id": "RC-X"}),
            write_(cash={"amount": 4000}),
            write_(cash={"currency": "RUB"}),
        ]
        for w in bad:
            self.assertNotClosed(self.ov("money", "rent", WANT_RENT, write=w, prm=P_CR))

    def test_cell_never_closes_money_I26_M14(self):
        for prm in (PD, P_CR):
            res = self.ov("money", "rent", WANT_RENT, cell={"state": "value", "num": 4900}, prm=prm)
            self.assertNotClosed(res, "open")
            res = self.ov("money", "rent", dict(WANT_RENT, state="unknown"), cell={"state": "value", "num": 4900},
                          prm=prm)
            self.assertNotClosed(res, "open")
            for cell in ({"state": "value", "num": 0}, {"state": "empty"}, {"state": "text"}, {"state": "unread"}):
                self.assertNotClosed(self.ov("money", "rent", WANT_RENT, cell=cell, prm=prm), "unknown")

    def test_human_decides_and_waives(self):
        res = self.ov("money", "rent", dict(WANT_RENT, outcome="incomplete"),
                      human={"decided": True, "detail": "касса 2041 + 2042"})
        self.assertEqual((res["state"], res["by"]), ("closed", "human"))
        res = self.ov("money", "deposit", dict(WANT_RENT, role="deposit", state="unknown"),
                      human={"waive": True, "detail": "залога нет"})
        self.assertEqual(res["state"], "waived")
        res = self.ov("bike", "return", {"state": "open"}, human={"decided": True, "detail": "вернул"})
        self.assertEqual((res["state"], res["by"]), ("closed", "human"))

    def test_human_want_sets_amount_but_closes_nothing(self):
        res = self.ov("money", "rent", dict(WANT_RENT, state="unknown", outcome="unknown", amount=None),
                      human={"want": {"amount": 4900, "currency": "THB", "detail": "названо владельцем"}})
        self.assertEqual(res["state"], "open", "§4.4: want → unknown → open, ничего не закрывает")


# ================================================================================================================
# document_coverage — покрытие периода отдельно от принадлежности (§6, I46; К4-C39; M31, M31b, M31c)
# ================================================================================================================

DOC_VERIFIED = {"id": 9, "document_id": 9, "case_id": "RC-I", "kind": "contract_signed", "ext_id": "doc-233",
                "reg_row": 233, "status": "verified", "rental_id": 41, "bound_by": "телефон + 6908 + 2026-10-01",
                "signed_at": "2026-10-01 10:12", "sha256": None, "cover_from": None, "cover_to": None,
                "cover_basis": None, "cover_ref": None, "cover_by": None, "cover_act": None, "cover_at": None}
# «Отравленный» документ контрпримера TB-K4-DOCUMENT-COVERAGE-0910: подписан 01.10 на 01.10–12.10, впервые прочитан
# после продления аренды до 20.10 — рядом лежат дата договора и срок привязки на момент записи (01.10–20.10).
DOC_LATE_READ = dict(DOC_VERIFIED, contract_date="2026-10-01", start_day="2026-10-01", end_day="2026-10-20",
                     window="2026-10-01…2026-10-20",
                     rental={"start_day": "2026-10-01", "end_day": "2026-10-20", "booking_id": "bk-812"})


def covered(frm, to, basis="human_confirmed", base=None):
    d = dict(base or DOC_VERIFIED)
    d.update(cover_from=frm, cover_to=to, cover_basis=basis, cover_ref="PDF договора: срок аренды, стр. 1",
             cover_by=1001 if basis == "human_confirmed" else None,
             cover_act="btn:cover:1" if basis == "human_confirmed" else None, cover_at=T_NEW)
    return d


class TestDocumentCoverage(K4Case):

    def dc(self, doc, period):
        res = self.pure(R.document_coverage, doc, period)
        self.assertIn(res.get("code"), ("covers", "not_covers", "unknown"), res)
        return res

    def assertCov(self, res, code, why=None, missing=None):
        self.assertEqual(res["code"], code, res)
        if why is not None:
            self.assertEqual(res.get("why"), why, res)
        if missing is not None:
            self.assertEqual(list(res.get("missing") or []), missing, res)

    def test_first_late_read_counterexample_M31b(self):
        """TB-K4-DOCUMENT-COVERAGE-0910: verified-документ, впервые прочитанный после продления до 20.10, без
        доказанного покрытия → запрос 12.10–20.10 unknown(doc_period_unknown), а не covers."""
        res = self.dc(DOC_LATE_READ, ("2026-10-12", "2026-10-20"))
        self.assertCov(res, "unknown", "doc_period_unknown", ["document_period"])

    def test_binding_does_not_prove_even_initial_term_M31(self):
        for period in (("2026-10-01", "2026-10-12"), ("2026-10-01", "2026-10-20"), ("2026-10-02", "2026-10-03")):
            self.assertCov(self.dc(DOC_LATE_READ, period), "unknown", "doc_period_unknown", ["document_period"])
            self.assertCov(self.dc(DOC_VERIFIED, period), "unknown", "doc_period_unknown", ["document_period"])

    def test_incomplete_or_foreign_basis_is_unknown_M31b_M31c(self):
        for doc in (covered("2026-10-01", "2026-10-20", basis="binding_at_verify"),
                    covered("2026-10-01", "2026-10-20", basis=None),
                    dict(covered("2026-10-01", "2026-10-20"), cover_to=None),
                    dict(covered("2026-10-01", "2026-10-20"), cover_from=None)):
            self.assertCov(self.dc(doc, ("2026-10-12", "2026-10-20")), "unknown", "doc_period_unknown",
                           ["document_period"])

    def test_confirmed_coverage_covers_and_not_covers(self):
        """§13 (д): подтверждено одобряющим 01.10–12.10 → 01.10–12.10 covers, 12.10–20.10 not_covers."""
        doc = covered("2026-10-01", "2026-10-12")
        self.assertCov(self.dc(doc, ("2026-10-01", "2026-10-12")), "covers")
        self.assertCov(self.dc(doc, ("2026-10-02", "2026-10-05")), "covers")
        self.assertCov(self.dc(doc, ("2026-10-12", "2026-10-20")), "not_covers", "partial")
        self.assertCov(self.dc(doc, ("2026-09-25", "2026-10-05")), "not_covers", "partial")
        self.assertCov(self.dc(doc, ("2026-10-13", "2026-10-20")), "not_covers", "outside")
        late = covered("2026-10-01", "2026-10-12", base=DOC_LATE_READ)
        self.assertCov(self.dc(late, ("2026-10-12", "2026-10-20")), "not_covers", "partial",
                       )   # срок привязки 01.10–20.10 рядом не расширяет доказанное покрытие

    def test_addendum_confirmed_extension_covers(self):
        """§13 (е): одобряющий подтвердил 01.10–20.10 по допсоглашению → 12.10–20.10 covers."""
        self.assertCov(self.dc(covered("2026-10-01", "2026-10-20", base=DOC_LATE_READ), ("2026-10-12", "2026-10-20")),
                       "covers")

    def test_document_and_addendum_bases_accepted(self):
        """§6: cover_basis ∈ {document, addendum, human_confirmed} — правило считает покрытие по любому из трёх
        (писателя document/addendum в К4 нет — это проверка правила, а не пути записи)."""
        for basis in ("document", "addendum"):
            self.assertCov(self.dc(covered("2026-10-01", "2026-10-12", basis=basis), ("2026-10-01", "2026-10-12")),
                           "covers")
            self.assertCov(self.dc(covered("2026-10-01", "2026-10-12", basis=basis), ("2026-10-12", "2026-10-20")),
                           "not_covers", "partial")

    def test_binding_verdict_first_I46(self):
        """Порядок §6: status ≠ verified → unknown(binding_not_verified) раньше периода и покрытия."""
        for status in ("unverified", "revoked"):
            doc = dict(covered("2026-10-01", "2026-10-20"), status=status)
            self.assertCov(self.dc(doc, ("2026-10-12", "2026-10-20")), "unknown", "binding_not_verified")
            self.assertCov(self.dc(doc, None), "unknown", "binding_not_verified")

    def test_period_required_M31c(self):
        """Без периода — period_not_given, даже при доказанном покрытии и сроке привязки рядом."""
        for doc in (DOC_LATE_READ, covered("2026-10-01", "2026-10-20")):
            for period in (None, ("2026-10-12", None), (None, "2026-10-20"), (None, None)):
                self.assertCov(self.dc(doc, period), "unknown", "period_not_given", ["period"])

    def test_never_covers_without_proven_coverage_sweep(self):
        periods = [("2026-10-%02d" % a, "2026-10-%02d" % b) for a in range(1, 21, 3) for b in range(a, 21, 4)]
        for doc in (DOC_VERIFIED, DOC_LATE_READ):
            for period in periods:
                self.assertNotEqual(self.dc(doc, period)["code"], "covers", (doc.get("end_day"), period))


# ================================================================================================================
# close_blockers — правило закрытия (§6, DESIGN §7.6; I13, I25; К4-C11)
# ================================================================================================================


def blk_has(blockers, token):
    for b in blockers:
        if b.get("id") == token or b.get("why") == token or b.get("what") == token:
            return True
        if isinstance(token, str) and token in jdump(b):
            return True
    return False


def set_state(view, oid, state, closed_by=None):
    for part in ("money", "obligations_other", "obligations"):
        for o in view[part]:
            if o.get("id") == oid:
                o["state"] = state
                o["closed_by"] = closed_by
    return view


def drop(view, oid):
    for part in ("money", "obligations_other", "obligations"):
        view[part] = [o for o in view[part] if o.get("id") != oid]
    return view


class TestCloseBlockers(K4Case):

    def cb(self, view):
        res = self.pure(R.close_blockers, view)
        self.assertIsInstance(res, list)
        for b in res:
            for k in ("what", "id", "why"):
                self.assertIn(k, b, "блокер — {what, id, why} (§5.5): %r" % b)
        return res

    def test_settled_case_has_no_blockers(self):
        self.assertEqual(self.cb(mk_view()), [])

    def test_open_or_unknown_obligation_blocks(self):
        self.assertTrue(blk_has(self.cb(set_state(mk_view(), 90501, "open")), 90501))
        self.assertTrue(blk_has(self.cb(set_state(mk_view(), 90502, "unknown")), 90502))
        self.assertTrue(blk_has(self.cb(set_state(mk_view(), 90505, "open")), 90505))
        self.assertTrue(blk_has(self.cb(set_state(mk_view(), 90506, "unknown")), 90506),
                        "client/notify_final при FINAL_NOTICE_REQUIRED=UNKNOWN — блокер до ступени 6 или waived")

    def test_missing_required_obligation_I25(self):
        for oid in (90501, 90502):
            self.assertTrue(blk_has(self.cb(drop(mk_view(), oid)), "obligation_missing"), oid)

    def test_nonterminal_expectation_blocks(self):
        for st in ("planned", "in_flight", "waiting", "escalating", "escalated", "flight_unknown",
                   "escalation_unknown"):
            view = mk_view(expectations=[{"exp_id": "RE-7", "case_id": "RC-I", "task_id": None,
                                          "kind": "staff_question", "state": st, "next_check": "await_answer",
                                          "case_ver": 2, "src": dict(SRC)}])
            self.assertTrue(blk_has(self.cb(view), "RE-7"), st)
        for st in ("answered", "superseded", "cancelled"):
            view = mk_view(expectations=[{"exp_id": "RE-7", "case_id": "RC-I", "task_id": None,
                                          "kind": "staff_question", "state": st, "next_check": "none",
                                          "case_ver": 2, "src": dict(SRC)}])
            self.assertFalse(blk_has(self.cb(view), "RE-7"), st)

    def test_notice_inflight_blocks(self):
        for st in ("drafting", "draft_unknown"):
            view = mk_view(notices=[{"notice_id": "RN-9", "case_id": "RC-I", "task_id": "RT-R", "intent": "final",
                                     "state": st, "case_ver": 2, "draft_id": None, "src": dict(SRC)}])
            bl = self.cb(view)
            self.assertTrue(blk_has(bl, "notice_inflight") or blk_has(bl, "RN-9"), st)

    def test_open_task_below_5_blocks(self):
        for top in (0, 3, 4):
            view = mk_view(tasks=[{"task_id": "RT-9", "case_id": "RC-I", "kind": "readiness", "state": "open",
                                   "top_stage": top, "rental_id": 41, "case_ver": 2, "created_at": T_OBS,
                                   "src": dict(SRC)}] + mk_view()["tasks"])
            self.assertTrue(blk_has(self.cb(view), "RT-9"), top)

    def test_attention_and_drift_block_I24_I37(self):
        self.assertTrue(blk_has(self.cb(mk_view(attention=1)), "attention"))
        self.assertTrue(blk_has(self.cb(mk_view(link_state="drift")), "link_drift"))


# ================================================================================================================
# allowed — разрешённые намерения (§6, DESIGN §6.7; I24, I37; §4.3 условия propose_client_notice)
# ================================================================================================================


def notice_view(**kw):
    tasks = [{"task_id": "RT-1", "case_id": "RC-B", "kind": "readiness", "state": "done", "top_stage": 5,
              "rental_id": 52, "case_ver": kw.pop("task_ver", 1), "created_at": T_OBS, "src": dict(SRC)}]
    money = [obl(90601, "money", "rent", "open", outcome="incomplete", amount=4900, currency="THB"),
             obl(90602, "money", "deposit", "unknown", outcome="unknown")]
    other = [obl(90604, "bike", "handover", "open"), obl(90605, "bike", "return", "open"),
             obl(90606, "client", "notify_final", "unknown")]
    v = mk_view(case_ver=1, status_seen="Бронь", tasks=kw.pop("tasks", tasks), money=money, other=other,
                notices=[], **kw)
    return v


class TestAllowed(K4Case):

    def al(self, view, prm=None):
        res = self.pure(R.allowed, view, prm or PS_FEEDS)
        self.assertIsInstance(res, list)
        return res

    def has(self, res, action):
        return any(action in jdump(item) for item in res)

    def test_notice_intent_allowed_when_all_conditions_hold_section4_3(self):
        self.assertTrue(self.has(self.al(notice_view()), "propose_client_notice"))

    def test_no_client_intent_without_feeds_S_M3(self):
        self.assertFalse(self.has(self.al(notice_view(), PS), "propose_client_notice"), "FEEDS_CONNECTED=∅")

    def test_no_client_intent_under_attention_I24(self):
        self.assertFalse(self.has(self.al(notice_view(attention=1)), "propose_client_notice"))

    def test_no_client_intent_under_drift_I37(self):
        for ls in ("drift", "missing", "ambiguous"):
            self.assertFalse(self.has(self.al(notice_view(link_state=ls)), "propose_client_notice"), ls)

    def test_no_client_intent_with_open_confirm_link(self):
        exps = [{"exp_id": "RE-L", "case_id": "RC-B", "task_id": None, "kind": "confirm_link", "action": "confirm",
                 "state": "waiting", "next_check": "await_answer", "case_ver": 1, "cand_sha": "c0ffee",
                 "src": dict(SRC)}]
        self.assertFalse(self.has(self.al(notice_view(expectations=exps)), "propose_client_notice"))

    def test_no_client_intent_for_old_version_or_unfinished_task(self):
        self.assertFalse(self.has(self.al(notice_view(task_ver=0)), "propose_client_notice"),
                         "задача прежней версии")
        tasks = [{"task_id": "RT-1", "case_id": "RC-B", "kind": "readiness", "state": "open", "top_stage": 4,
                  "rental_id": 52, "case_ver": 1, "created_at": T_OBS, "src": dict(SRC)}]
        self.assertFalse(self.has(self.al(notice_view(tasks=tasks)), "propose_client_notice"), "ступень 4 < 5")

    def test_request_approval_after_physically_done(self):
        t4 = [{"task_id": "RT-H", "case_id": "RC-B", "kind": "handover", "state": "open", "top_stage": 4,
               "rental_id": 52, "case_ver": 1, "created_at": T_OBS, "src": dict(SRC)}]
        self.assertTrue(self.has(self.al(notice_view(tasks=t4)), "request_approval"))
        t3 = [dict(t4[0], top_stage=3)]
        self.assertFalse(self.has(self.al(notice_view(tasks=t3)), "request_approval"))

    def test_close_case_only_without_blockers_I13(self):
        self.assertTrue(self.has(self.al(mk_view()), "close_case"))
        self.assertFalse(self.has(self.al(set_state(mk_view(), 90501, "open")), "close_case"))
        self.assertFalse(self.has(self.al(notice_view()), "close_case"))


if __name__ == "__main__":
    unittest.main()
