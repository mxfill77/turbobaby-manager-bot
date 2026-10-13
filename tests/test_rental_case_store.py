#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910) — проверки хранилища дела аренды `rental_case.Store` ЧЁРНЫМ ЯЩИКОМ.

Источник истины — `out/CONTRACT_K4.md` (§1 исходы, §2 схема, §4 переходы, §5 Store, §7 инварианты I1–I46, §8 форматы,
§11 ключи, §12 причины); приёмка и мутанты — `out/DESIGN_K4.md` §13/§15 (К4-C…, M…). Код `rental_case*.py` при
написании проверок не читался и под него не подгонялся: каждая проверка ссылается на пункт контракта в имени или
docstring. Проверяется и исход, и отсутствие лишних записей (снимок всех таблиц `rc_*` до/после) — так ловится порча
(M5, M7, M8, M15–M17, M20, M24, M27, M31b, M31c …), а не только «зелёное».

Покрытие инвариантов (каждый — хотя бы одной проверкой):
  I1  test_I1_I4_case_id_born_once_ver_only_by_version_bumped, test_I20_K4C18_...clock_and_ids
  I2  test_I2_K4C2_booking_id_one_case_api, TestSchema.test_I2_partial_unique_links
  I3  test_I3_I4_reconcile_period_changed_new_current_row, TestSchema.test_I3_one_current_rental
  I4  test_I1_I4_..., test_I3_I4_...
  I5  TestSchema.test_I5_K4C15_event_append_only_triggers, test_I5_each_mutation_has_main_event
  I6  test_I6_failure_inside_transaction_rolls_back_store_usable
  I7  test_I7_I32_K4C13_duplicate_and_payload_mismatch
  I8  test_I8_K4C14_two_stores_cas_one_ok_one_conflict, test_section44_obligation_transitions_I26
  I9  test_I9_I18_K4C9_answer_bound_by_post_addressee_place_not_nick, test_I16_K4C17_params_default_fail_closed
  I10 test_I10_I44_forbidden_evidence_for_stages_4_and_5
  I11 test_I11_stage5_only_after_stage4
  I12 test_I12_I42_I24_K4C10_ladder_stages_1_to_6_notice_restart
  I13 test_I13_I31_K4C31_close_case_hook_inside_transaction, test_I13_close_case_recomputes_blockers
  I14 test_I14_I43_no_transition_by_age_escalation_only_by_approver
  I15 test_I15_flight_unknown_not_reclaimed_and_listed_for_human
  I16 test_I16_K4C17_params_default_fail_closed
  I17 test_I17_resolve_return_two_active_unknown
  I18 test_I9_I18_..., test_I35_K4C7_cash_without_booking_only_single_claimant
  I19 TestOpen.test_I19_I33_K4C16_unavailable_never_empty
  I20 TestOpen.test_I20_K4C18_modules_static_and_injected_clock_ids
  I21 test_I21_bump_revokes_per_design_4_2
  I22 test_I22_K4C36_case_view_and_facts_for_agent_src
  I23 TestOpen.test_I23_K4C14_sql_writes_only_in_rental_case
  I24 test_I24_K4C21_attention_wa_pause_tg_any_kind_release_by_approver, ladder
  I25 test_I25_K4C27_required_obligations_born_with_case
  I26 test_section44_obligation_transitions_I26, TestSchema.test_I26_I45_obligation_checks
  I27 test_I27_one_evidence_ref_one_stage
  I28 test_I28_I39_K4C28_approval_execute_ttl_no_reply_restart, TestSchema.test_I28_answer_execute_check
  I29 test_I29_K4C29_recover_only_own_role_old_boot
  I30 test_I30_K4C30_older_read_changes_nothing
  I31 test_I13_I31_K4C31_close_case_hook_inside_transaction
  I32 test_I7_I32_K4C13_duplicate_and_payload_mismatch
  I33 TestOpen.test_I33_writer_opens_existing_file_uri_without_create, test_I33_I43_store_busy_unknown_retry_safe
  I34 test_I34_K4C23_continuation_needs_approver
  I35 test_I35_K4C7_cash_without_booking_only_single_claimant
  I36 test_I36_I38_superseded_contact_and_resolve
  I37 test_I37_link_drift_hides_rental_money_documents
  I38 test_I36_I38_..., TestOpen.test_I38_patch_finds_case_only_through_resolve (пропуск, пока патча нет)
  I39 test_I28_I39_...
  I40 test_I40_post_of_superseded_recorded_and_orphan_linked, test_section45_cancelled_task_physical_event_fact
  I41 test_I41_agents_question_born_escalated_not_due
  I42 test_I12_I42_I24_...
  I43 test_I14_I43_..., test_I33_I43_store_busy_unknown_retry_safe
  I44 test_I10_I44_...
  I45 test_I16_K4C17_params_default_fail_closed (write при UNKNOWN), test_I45_write_closes_rent_only_with_second_source,
      TestSchema.test_I26_I45_obligation_checks
  I46 test_I46_K4C39_coverage_only_confirmed_first_late_read, TestSchema.test_I46_document_cover_checks
Переходы §4: test_section41_*, test_section42_*, test_section44_*, test_section45_* + переходы внутри сценариев.
Хранилище/рестарт/потоки: test_restart_between_steps_new_store_no_loss_no_repeat,
test_K4C14_one_store_two_threads_no_programming_error, test_I29_*.
F2 К3 (основания версии): TestSchema.test_F2_no_source_version_column, test_I22_K4C36_* (version «case_ver:<n>»).

Запуск: `python tests/test_rental_case_store.py` (код выхода ≠ 0 при провале) или через
`tests/run_rental_case_suites.py`. Временные базы — в tempfile.mkdtemp(dir=K4_TTMP), не удаляются. Сеть запрещена
подменой socket.socket (tests/rental_case_fakes.py; при его отсутствии — своя такая же подмена ниже).
"""
import ast
import contextlib
import copy
import datetime
import hashlib
import json
import os
import re
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, ROOT):                      # ROOT окажется первым: модули дела — из родителя каталога tests
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import rental_case_fakes  # noqa: F401  — подделки §9.1; подменяют socket.socket на бросающий
except ImportError:
    rental_case_fakes = None

import _socket


class _NoNet(object):
    def __init__(self, *a, **kw):
        raise RuntimeError("К4: сеть в тестах запрещена (socket.socket подменён)")


def _no_net(*a, **kw):
    raise RuntimeError("К4: сеть в тестах запрещена (socket.create_connection подменён)")


def _guard_network():
    cur = socket.socket
    if isinstance(cur, type) and issubclass(cur, _socket.socket):      # ещё настоящий — подделки не подменили
        socket.socket = _NoNet
        socket.create_connection = _no_net


_guard_network()

_ORIG_CONNECT = sqlite3.connect          # до любых подмен шпиона: сырые чтения проверок идут мимо него

import rental_case as RC                 # noqa: E402
from rental_case import Store, StoreUnavailable   # noqa: E402

try:
    import rental_case_rules as RR       # noqa: E402
except ImportError:                      # pragma: no cover
    RR = None

UNKNOWN = getattr(RC, "UNKNOWN", None) or getattr(RR, "UNKNOWN", None) or "UNKNOWN"
PARAMS_DEFAULT = getattr(RC, "PARAMS_DEFAULT", None)
if PARAMS_DEFAULT is None and RR is not None:
    PARAMS_DEFAULT = getattr(RR, "PARAMS_DEFAULT", None)

TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
if not os.path.isdir(TTMP):
    os.makedirs(TTMP)

# ------------------------------------------------------------------------------------------------ синтетика
T0 = datetime.datetime(2026, 10, 9, 5, 0, tzinfo=datetime.timezone.utc).timestamp()   # 09.10.2026 12:00 (+7)
T_OBS = T0 - 120.0

APPROVER = 1001                      # синтетический одобряющий (CONTRACT §14 вариант А)
OWNER = 504608015                    # OWNER_IDS по умолчанию (CONTRACT §10)
STRANGER = 2002
STAFF_TOPIC = 9001
STAFF_DELIV = 9002

TOPIC_CHAT = "-1001000000001"
DELIV_CHAT = "-1001000000002"
AGENTS_CHAT = "-1001000000003"
INBOX_CHAT = "-1001000000004"
THREAD = "55"

BIKE = "NMAX 155 6908"
PLATE = "6908"
CLIENTS_SRC = "лист «клиенты» (clients filter=all)"
BK_IVAN = "0b1f3c2a-7d41-4c55-9a10-000000000812"
BK_BORIS = "0b1f3c2a-7d41-4c55-9a10-000000000845"
IVAN_WA = "66812345678"
BORIS_WA = "66897654321"
ANNA_WA = "66861112233"
Q_RU = "Будет ли NMAX 6908 готов к выдаче 15.10?"
Q_TH = "NMAX 6908 จะพร้อมส่งมอบวันที่ 15.10 ไหมครับ?"
WAMID = "wamid.HBgLNjY4OTc2NTQzMjEVAgARGBI0"

BY_APPROVER = {"kind": "human", "id": APPROVER, "name": "owner"}
BY_OWNER = {"kind": "human", "id": OWNER, "name": "owner-default"}
BY_STRANGER = {"kind": "human", "id": STRANGER, "name": "stranger"}
BY_CODE = {"kind": "code", "id": None, "name": "k4-test"}
BY_SPL = {"kind": "code", "id": None, "name": "splinter"}
BY_WA = {"kind": "code", "id": None, "name": "wa_core"}
BY_AGENT = {"kind": "agent", "id": None, "name": "wa_agent"}

SRC_KEYS = ("source", "ref", "method", "read_at", "observed_at", "case_ver")
METHODS = ("door", "reply", "readback", "human", "event")
VIEW_PARTS = ("case", "client", "rental", "bike", "documents", "money", "obligations_other", "facts", "tasks",
              "expectations", "answers", "orphans", "notices", "blockers", "allowed_actions", "read_at")
SRC_PARTS = ("case", "client", "rental", "bike", "documents", "money", "obligations_other", "facts", "tasks",
             "expectations", "answers", "orphans", "notices")
NO_DESCEND = frozenset(("src", "value", "flags", "missing", "payload", "subject", "target", "evidence", "card",
                        "data", "fkey", "addressee_ids", "blockers", "allowed_actions", "ask", "reason", "why",
                        "detail", "posts", "facts", "fact_ids", "candidates", "claimants", "window"))
ELEMENT_KEYS = frozenset(("current", "state", "close_fact", "close_second"))
CONTENT_KEYS = frozenset(("plate", "booking_id", "role", "name_seen", "channel", "case_id", "task_id", "exp_id",
                          "notice_id", "answer_id", "orphan_id", "stage", "ext_id", "doc_kind", "obl_kind",
                          "plate_old", "plate_new"))
SOURCE_VER_KEY = re.compile(r"^(source|src|ext|external|origin|registry|sheet)_?ver(sion)?$", re.I)
_CC = frozenset(("125", "150", "155", "300", "350", "400", "500", "650", "700", "750", "900"))


class FakeClock(object):
    """Инжектированные часы (I20): время меняется только явно."""

    def __init__(self, t):
        self.t = float(t)
        self._lock = threading.Lock()

    def __call__(self):
        return self.t

    def advance(self, dt):
        with self._lock:
            self.t += float(dt)
        return self.t


class IdGen(object):
    """Инжектированный источник id (I1, I20): помнит каждый выданный id."""

    def __init__(self, seed=0xC4000000):
        self.n = seed
        self.issued = []
        self._lock = threading.Lock()

    def __call__(self):
        with self._lock:
            self.n += 1
            v = "%032x" % self.n
            self.issued.append(v)
            return v


def plate_of(text):
    nums = [n for n in re.findall(r"\d{3,}", str(text or "").lower()) if n not in _CC]
    return nums[-1] if nums else ""


def anchor_of(row):
    """Якорь по CONTRACT §6 `anchor_of`: plate|YYYY-MM-DD|name_norm."""
    return "%s|%s|%s" % (plate_of(row.get("bike")), str(row.get("date_start") or "")[:10],
                         str(row.get("name") or "").strip().lower())


def make_row(row, status, bike, name, start, end, contacts, booking_id="", deposit_raw="3000", to_pay=0, debt=0,
             paid=0, auto_cancel=""):
    """Строка двери clients в живом формате (f2f7295:bridge_prod/ReadClients.js:95-121; без price, пусто = 0)."""
    try:
        dep = float(deposit_raw)
    except (TypeError, ValueError):
        dep = 0
    days = None
    try:
        days = (datetime.date(*map(int, end[:10].split("-"))) - datetime.date(*map(int, start[:10].split("-")))).days
    except Exception:
        days = None
    return {"row": row, "status": status, "auto_cancel": auto_cancel, "bike": bike, "name": name,
            "date_start": start, "date_end": end, "duration": days, "pay_per_day": 350, "debt": debt,
            "to_pay": to_pay, "paid": paid, "deposit": dep, "deposit_raw": deposit_raw, "helmets": 1,
            "contacts": contacts, "note": "", "type": "скутер", "booking_id": booking_id,
            "is_active": status == "В аренде" and auto_cancel != "ON", "is_overdue": False, "days_overdue": 0,
            "is_fresh": True}


def row_ivan(**kw):
    r = make_row(812, "В аренде", BIKE, "Иван", "2026-10-01 10:00", "2026-10-12 10:00", "+66 81 234 5678",
                 booking_id=BK_IVAN, deposit_raw="3000")
    r.update(kw)
    return r


def row_boris(**kw):
    r = make_row(845, "Бронь", BIKE, "Борис", "2026-10-15 10:00", "2026-10-20 10:00", "+66 89 765 4321",
                 booking_id=BK_BORIS, deposit_raw="passport")
    r.update(kw)
    return r


def row_anna(**kw):
    r = make_row(900, "Бронь", "PCX 160 4410", "Анна", "2026-10-20 10:00", "2026-10-25 10:00", "+66 86 111 2233",
                 booking_id="", deposit_raw="2000")
    r.update(kw)
    return r


def src_clients(row, observed_at, read_at=None):
    return {"name": CLIENTS_SRC, "ref": "строка %s" % row["row"], "method": "door",
            "read_at": float(observed_at + 3.0 if read_at is None else read_at), "observed_at": float(observed_at)}


def src_of(name, ref, method, observed_at, read_at=None):
    return {"name": name, "ref": ref, "method": method,
            "read_at": float(observed_at + 1.0 if read_at is None else read_at), "observed_at": float(observed_at)}


def k_open(origin, row):
    bk = row.get("booking_id")
    return ("open:%s:bk:%s" % (origin, bk)) if bk else ("open:%s:anchor:%s" % (origin, anchor_of(row)))


def k_fact(case_id, fkey, observed_at):
    return "fact:%s:%s:%s" % (case_id, json.dumps(list(fkey), ensure_ascii=False), observed_at)


def k_ask(case_id, ver, task_id, staff_kind, q_ru, attempt=1):
    return "ask:%s:%s:%s:%s:%d" % (case_id, ver, task_id or "-",
                                   hashlib.sha1(("%s|%s" % (staff_kind, q_ru)).encode("utf-8")).hexdigest()[:12],
                                   attempt)


def bike_posts(t, topic_msg, deliv_msg):
    return [{"place": "topic", "chat": TOPIC_CHAT, "msg_id": str(topic_msg), "thread_id": THREAD,
             "role": "question", "at": float(t)},
            {"place": "delivery", "chat": DELIV_CHAT, "msg_id": str(deliv_msg), "thread_id": None,
             "role": "delivery", "at": float(t)}]


def human_mark(act_ref, author_id=APPROVER, note="отметка одобряющего"):
    return {"kind": "human_mark", "ref": act_ref, "author_id": author_id, "act_ref": act_ref, "note": note}


def dget(o, key, default=None):
    if not isinstance(o, dict):
        return default
    d = o.get("data")
    if isinstance(d, dict) and key in d:
        return d[key]
    return default


def reason_code(o):
    """`reason` — код REASONS (§12) [+ «: слова»] (CONTRACT §1.2)."""
    return str((o or {}).get("reason") or "").split(":")[0].strip()


def verdict_of(o):
    v = dget(o, "verdict")
    return v if v is not None else (o or {}).get("verdict")


def case_id_of(o):
    return (o or {}).get("case_id") or dget(o, "case_id")


def short(obj, n=600):
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        s = repr(obj)
    return s if len(s) <= n else s[:n] + "…"


def walk_elements(obj, path, out, is_item=False):
    """Элементы частей §8.4: каждый элемент списка и каждый словарь с ключами содержания несут src (I22)."""
    if isinstance(obj, dict):
        if is_item or (CONTENT_KEYS & set(obj.keys())):
            out.append((path, obj))
        for k, v in obj.items():
            if k in NO_DESCEND:
                continue
            if k in ELEMENT_KEYS and isinstance(v, dict):
                walk_elements(v, "%s.%s" % (path, k), out, True)
            else:
                walk_elements(v, "%s.%s" % (path, k), out, False)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            walk_elements(v, "%s[%d]" % (path, i), out, True)


def find_keys(obj, pred, path="$", out=None):
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if pred(k, v):
                out.append(("%s.%s" % (path, k), v))
            find_keys(v, pred, "%s.%s" % (path, k), out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            find_keys(v, pred, "%s[%d]" % (path, i), out)
    return out


class DB(object):
    """Сырые чтения/фикстуры проверок мимо Store (схема — часть контракта, §2)."""

    def __init__(self, path):
        self.path = path

    def _con(self, fk=True):
        con = _ORIG_CONNECT(self.path, timeout=10.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        if fk:
            con.execute("PRAGMA foreign_keys=ON")
        return con

    def q(self, sql, args=()):
        con = self._con()
        try:
            return [dict(r) for r in con.execute(sql, tuple(args)).fetchall()]
        finally:
            con.close()

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql, args=()):
        """Фикстура: одна запись в обход Store (только в проверках схемы и подлогах, названных в docstring)."""
        con = self._con()
        try:
            con.execute(sql, tuple(args))
        finally:
            con.close()

    def insert(self, table, cols):
        names = sorted(cols)
        self.x("INSERT INTO %s(%s) VALUES (%s)" % (table, ",".join(names), ",".join("?" * len(names))),
               [cols[n] for n in names])

    def dump(self):
        con = self._con(fk=False)
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rc!_%' ESCAPE '!' ORDER BY name")]
            return dict((n, [tuple(r) for r in con.execute('SELECT * FROM "%s" ORDER BY rowid' % n)]) for n in names)
        finally:
            con.close()

    def case(self, cid):
        return self.one("SELECT * FROM rc_case WHERE case_id=?", (cid,))

    def exp(self, eid):
        return self.one("SELECT * FROM rc_expect WHERE exp_id=?", (eid,))

    def task(self, tid):
        return self.one("SELECT * FROM rc_task WHERE task_id=?", (tid,))

    def notice(self, nid):
        return self.one("SELECT * FROM rc_notice WHERE notice_id=?", (nid,))

    def obligations(self, cid):
        return self.q("SELECT * FROM rc_obligation WHERE case_id=? ORDER BY id", (cid,))

    def obl(self, cid, kind, role):
        rows = self.q("SELECT * FROM rc_obligation WHERE case_id=? AND kind=? AND role=? ORDER BY id",
                      (cid, kind, role))
        return rows[0] if rows else None

    def current_rental(self, cid):
        return self.one("SELECT * FROM rc_rental WHERE case_id=? AND current=1", (cid,))

    def facts(self, cid, kind=None):
        if kind:
            return self.q("SELECT * FROM rc_fact WHERE case_id=? AND kind=? ORDER BY id", (cid, kind))
        return self.q("SELECT * FROM rc_fact WHERE case_id=? ORDER BY id", (cid,))

    def events(self, case_id=None, etype=None):
        sql, args = "SELECT * FROM rc_event WHERE 1=1", []
        if case_id is not None:
            sql += " AND case_id=?"
            args.append(case_id)
        if etype is not None:
            sql += " AND type=?"
            args.append(etype)
        return self.q(sql + " ORDER BY seq", args)

    def stages(self, tid):
        return dict((r["stage"], r) for r in self.q("SELECT * FROM rc_stage WHERE task_id=?", (tid,)))

    def count(self, table, where="1=1", args=()):
        return self.one("SELECT COUNT(*) AS n FROM %s WHERE %s" % (table, where), args)["n"]


class Env(object):
    """Одна база в tempfile.mkdtemp(dir=K4_TTMP) (не удаляется), общие часы и источник id."""

    def __init__(self, tc, params, t0=T0, tag="k4store"):
        self.dir = tempfile.mkdtemp(prefix=tag + "_", dir=TTMP)
        self.path = os.path.join(self.dir, "rental_case.db").replace("\\", "/")
        self.clock = FakeClock(t0)
        self.ids = IdGen()
        self.params = params
        self.store_id = Store.create(self.path, clock=self.clock, new_id=self.ids)
        self.db = DB(self.path)
        self.roles = {}
        self._stores = []
        tc.addCleanup(self._close)

    def store(self, role, **kw):
        kw.setdefault("params", self.params)
        s = Store(self.path, role=role, clock=self.clock, new_id=self.ids, **kw)
        self._stores.append(s)
        self.roles[id(s)] = role
        return s

    def _close(self):
        for s in self._stores:
            try:
                s.close()
            except Exception:
                pass


def synth_params(**over):
    """Синтетические значения UNKNOWN-параметров (CONTRACT §14 вариант А); прочее — PARAMS_DEFAULT."""
    p = copy.deepcopy(dict(PARAMS_DEFAULT))
    p["AUTO_ASK"] = True
    sa = p.get("STAFF_ADDRESSEES")
    sa = dict(sa) if isinstance(sa, dict) else {}
    sa["topic"] = {STAFF_TOPIC}
    sa["delivery"] = {STAFF_DELIV}
    p["STAFF_ADDRESSEES"] = sa
    rrp = p.get("RESULT_RECORD_PLACE")
    rrp = dict(rrp) if isinstance(rrp, dict) else {}
    rrp["readiness"] = "sink:fake"
    p["RESULT_RECORD_PLACE"] = rrp
    p["FEEDS_CONNECTED"] = frozenset({"intervention", "inbound"})
    p["APPROVER_IDS"] = frozenset({APPROVER})
    p.update(over)
    return p


class ConnSpy(object):
    """Шпион sqlite3.connect (CONTRACT §2 «Открытие»): помнит аргументы и через trace-колбэк ловит границу записи.

    Крючок (P-M2, I31) срабатывает один раз — на первом `BEGIN IMMEDIATE/EXCLUSIVE` либо на первой записи вне такой
    транзакции на соединениях проверяемого Store. Исполнение верное (все предусловия внутри BEGIN IMMEDIATE) видит
    вставку крючка; чтение предусловий до захвата замка её не видит.
    """

    def __init__(self):
        self.calls = []
        self.fired = []
        self.trace = []
        self._hook = None
        self._busy = False

    def connect(self, *a, **kw):
        con = _ORIG_CONNECT(*a, **kw)
        self.calls.append((a, dict(kw)))
        state = {"lock": False}

        def cb(sql, _state=state):
            if self._busy:
                return
            s = " ".join(str(sql).split()).upper()
            self.trace.append(s[:100])
            if s.startswith("BEGIN"):
                lock = ("IMMEDIATE" in s) or ("EXCLUSIVE" in s)
                if lock:
                    self._fire("BEGIN IMMEDIATE")
                _state["lock"] = lock
            elif s.startswith("COMMIT") or s.startswith("END") or (
                    s.startswith("ROLLBACK") and not s.startswith("ROLLBACK TO")):
                _state["lock"] = False
            elif re.match(r"(INSERT|UPDATE|DELETE|REPLACE)\b", s) and not _state["lock"]:
                self._fire("запись вне BEGIN IMMEDIATE: " + s[:80])

        try:
            con.set_trace_callback(cb)
        except Exception:
            pass
        return con

    def arm(self, fn):
        self._hook = fn

    def disarm(self):
        self._hook = None

    def _fire(self, why):
        fn, self._hook = self._hook, None
        if fn is None:
            return
        self._busy = True
        try:
            res = fn()
        except Exception as exc:          # крючок обязан сработать чисто — иначе проверка падает ниже
            res = exc
        finally:
            self._busy = False
        self.fired.append((why, res))

    @contextlib.contextmanager
    def patched(self):
        patches = [mock.patch.object(sqlite3, "connect", self.connect)]
        dbapi2 = getattr(sqlite3, "dbapi2", None)
        if dbapi2 is not None and getattr(dbapi2, "connect", None) is _ORIG_CONNECT:
            patches.append(mock.patch.object(dbapi2, "connect", self.connect))
        with contextlib.ExitStack() as st:
            for p in patches:
                st.enter_context(p)
            yield self


# ================================================================================================ база проверок
class K4StoreBase(unittest.TestCase):
    maxDiff = 6000
    e = None

    # ---------- окружение
    def env(self, synth=True, **over):
        self.assertIsNotNone(PARAMS_DEFAULT, "PARAMS_DEFAULT не найден в rental_case/rental_case_rules (CONTRACT §10)")
        if synth:
            params = synth_params(**over)
        else:
            params = None
            if over:
                params = copy.deepcopy(dict(PARAMS_DEFAULT))
                params.update(over)
        self.e = Env(self, params)
        return self.e

    # ---------- утверждения
    def assertCode(self, o, code, reason=None, msg=""):
        self.assertIsInstance(o, dict, "%s: исход не словарь (§1.2): %r" % (msg, o))
        self.assertEqual(o.get("code"), code, "%s: ожидался %s%s, получено %s" % (
            msg, code, "(%s)" % reason if reason else "", short(o)))
        if reason is not None:
            self.assertEqual(reason_code(o), reason, "%s: причина %r вместо %r: %s" % (
                msg, o.get("reason"), reason, short(o)))
        if code == "unknown":                                         # §1.2, §12, К4-C5
            self.assertTrue(o.get("missing"), "%s: unknown без missing (К4-C5): %s" % (msg, short(o)))
            self.assertTrue(o.get("ask"), "%s: unknown без ask (К4-C5): %s" % (msg, short(o)))

    def assertNoWrites(self, before, msg=""):
        after = self.e.db.dump()
        if before != after:
            changed = sorted(t for t in set(before) | set(after) if before.get(t) != after.get(t))
            detail = ", ".join("%s %d→%d" % (t, len(before.get(t) or []), len(after.get(t) or [])) for t in changed)
            self.fail("%s: записи там, где контракт их запрещает (§1.3/§8.1): изменены %s" % (msg, detail))

    def assertNotOk(self, o, msg=""):
        self.assertIsInstance(o, dict, msg)
        self.assertNotEqual(o.get("code"), "ok", "%s: переход прошёл: %s" % (msg, short(o)))

    def check_src(self, path, el):
        src = el.get("src")
        self.assertIsInstance(src, dict, "%s: элемент без src (I22, К4-C36): %s" % (path, short(el)))
        for k in SRC_KEYS:
            self.assertIn(k, src, "%s: в src нет %s (I22): %s" % (path, k, short(src)))
        self.assertIn(src["method"], METHODS, "%s: src.method вне словаря §2: %s" % (path, short(src)))
        for k in ("source", "ref"):
            self.assertTrue(isinstance(src[k], str) and src[k] != "", "%s: src.%s пуст: %s" % (path, k, short(src)))
        for k in ("read_at", "observed_at"):
            self.assertTrue(isinstance(src[k], (int, float)) and not isinstance(src[k], bool),
                            "%s: src.%s не число: %s" % (path, k, short(src)))
        cv = src["case_ver"]
        self.assertTrue(isinstance(cv, int) and not isinstance(cv, bool) and cv >= 1,
                        "%s: src.case_ver не версия дела: %s" % (path, short(src)))

    def assertSrcFromRow(self, label, el, row, keys=SRC_KEYS):
        self.assertIsNotNone(el, "%s: элемент не найден" % label)
        self.assertIsNotNone(row, "%s: строка базы не найдена" % label)
        src = el.get("src") or {}
        for k in keys:
            self.assertEqual(src.get(k), row[k], "%s: src.%s=%r, колонка строки=%r — подстановка (I22, К4-C36)" % (
                label, k, src.get(k), row[k]))

    def assertSrcEquals(self, label, el, expected):
        """src по таблице вывода §8.4 (собственные строки хранилища, ответы) — сверка шести полей."""
        self.assertIsNotNone(el, "%s: элемент не найден" % label)
        src = el.get("src") or {}
        got = dict((k, src.get(k)) for k in SRC_KEYS)
        self.assertEqual(got, dict((k, expected[k]) for k in SRC_KEYS),
                         "%s: src не по таблице вывода §8.4 (I22, К4-C36)" % label)

    def assertNoSourceVersion(self, obj, label):
        hits = find_keys(obj, lambda k, v: bool(SOURCE_VER_KEY.match(str(k))) and v is not None)
        self.assertEqual(hits, [], "%s: заполнена «версия внешнего источника» (CONTRACT §8.4, F2 К3): %r" % (
            label, hits))

    # ---------- шаги (только публичные функции §5)
    def open_case(self, S, row, origin="test", by=BY_CODE, key=None, force_new=False, observed_at=None):
        obs = T_OBS if observed_at is None else observed_at
        return S.open_case(origin=origin, by=by, idem_key=key or k_open(origin, row),
                           booking_id=row.get("booking_id") or None, rental_row=row, contacts=(),
                           source=src_clients(row, obs), model_req=None, force_new=force_new)

    def new_case(self, S, row, **kw):
        o = self.open_case(S, row, **kw)
        self.assertCode(o, "ok", msg="open_case строки %s" % row.get("row"))
        cid = case_id_of(o)
        self.assertTrue(cid, "open_case ok без case_id: %s" % short(o))
        self.assertEqual(o.get("ver"), 1, "open_case → ver=1 (§4.1): %s" % short(o))
        return cid

    def new_task(self, S, cid, kind="readiness", ref="wa:in:501", by=BY_APPROVER, ver=1):
        o = S.open_task(cid, kind=kind, ref=ref, by=by, idem_key="task:%s:%d:%s:%s" % (cid, ver, kind, ref),
                        expect_ver=ver)
        self.assertCode(o, "ok", msg="open_task %s" % kind)
        tid = dget(o, "task_id")
        if not tid:
            row = self.e.db.one("SELECT task_id FROM rc_task WHERE case_id=? AND kind=? ORDER BY created_at DESC",
                                (cid, kind))
            tid = row and row["task_id"]
        self.assertTrue(tid, "open_task без task_id: %s" % short(o))
        self.assertEqual(self.e.db.task(tid)["state"], "open")
        return tid

    def ask(self, S, cid, task_id=None, staff_kind="байк", q_ru=Q_RU, q_th=Q_TH, by=BY_APPROVER, ver=1, attempt=1):
        o = S.request_staff_question(cid, task_id=task_id, staff_kind=staff_kind, q_ru=q_ru, q_th=q_th,
                                     urgency="клиент интересуется", by=by,
                                     idem_key=k_ask(cid, ver, task_id, staff_kind, q_ru, attempt), expect_ver=ver)
        self.assertCode(o, "ok", msg="request_staff_question")
        eid = dget(o, "exp_id")
        self.assertTrue(eid, "request_staff_question ok без data.exp_id (§5.4): %s" % short(o))
        row = self.e.db.exp(eid)
        self.assertEqual(row["state"], "planned", "новое ожидание — planned (§4.2): %r" % row)
        return eid

    def claim(self, S, eid, kinds=("staff_question",), by=BY_SPL, limit=10):
        items = S.claim_for_posting(by=by, kinds=kinds, limit=limit)
        self.assertIsInstance(items, list, "claim_for_posting → список (§5.4)")
        row = self.e.db.exp(eid)
        self.assertEqual(row["state"], "in_flight", "claim_for_posting: planned → in_flight (§4.2): %r" % row)
        self.assertEqual(row["claimed_by"], self.e.roles[id(S)], "claimed_by = роль Store (§4.2, P-B1)")
        self.assertEqual(row["claim_boot"], S.boot_id, "claim_boot = boot_id Store (§4.2, P-B1)")
        self.assertEqual(row["next_check"], "await_post_result")
        return items

    def post_result(self, S, eid, result, by=BY_SPL, rv=None):
        rv = self.e.db.exp(eid)["row_ver"] if rv is None else rv
        return S.mark_post_result(eid, result=result, by=by, idem_key="post:%s:%d" % (eid, rv), expect_row_ver=rv)

    def post(self, S, eid, posts, by=BY_SPL, qid="q-1"):
        return self.post_result(S, eid, {"posted": posts, "qid": qid}, by=by)

    def asked_and_posted(self, S, cid, task_id=None, topic_msg=7001, deliv_msg=7002, q_ru=Q_RU, by=BY_APPROVER,
                         ver=1):
        eid = self.ask(S, cid, task_id=task_id, q_ru=q_ru, by=by, ver=ver)
        self.claim(S, eid)
        o = self.post(S, eid, bike_posts(self.e.clock(), topic_msg, deliv_msg))
        self.assertCode(o, "ok", msg="mark_post_result(posted)")
        row = self.e.db.exp(eid)
        self.assertEqual(row["state"], "waiting", "posted → waiting (§4.2): %r" % row)
        self.assertEqual(row["next_check"], "await_answer")
        return eid

    def staff_reply(self, S, msg_id, reply_to, author_id=STAFF_TOPIC, chat=TOPIC_CHAT, thread_id=THREAD,
                    text="พร้อมครับ / готов", at=None, username="staff", reply_to_is_bot=True, is_bot=False):
        return S.on_staff_answer(chat=chat, msg_id=str(msg_id), reply_to=None if reply_to is None else str(reply_to),
                                 reply_to_is_bot=reply_to_is_bot, thread_id=thread_id, author_id=author_id,
                                 author_username=username, is_bot=is_bot, text=text,
                                 at=self.e.clock() if at is None else at,
                                 by={"kind": "staff", "id": author_id, "name": username})

    def approval(self, S, cid, action, card_ref, msg_id, ver=1, chat=INBOX_CHAT):
        o = S.request_approval(cid, task_id=None, action=action, chat=chat,
                               card={"ref": card_ref, "text": "карточка %s" % card_ref}, by=BY_SPL,
                               idem_key="appr:%s:%s:%s:%s:%s" % (cid or "-", ver if cid else "-", action, chat,
                                                                 card_ref),
                               expect_ver=ver if cid else None)
        self.assertCode(o, "ok", msg="request_approval %s" % action)
        eid = dget(o, "exp_id")
        self.assertTrue(eid, "request_approval ok без exp_id: %s" % short(o))
        self.claim(S, eid, kinds=("approval",))
        p = self.post(S, eid, [{"place": "intake", "chat": chat, "msg_id": str(msg_id), "thread_id": None,
                                "role": "card", "at": self.e.clock()}], qid=None)
        self.assertCode(p, "ok", msg="mark_post_result(card)")
        self.assertEqual(self.e.db.exp(eid)["state"], "waiting")
        return eid

    def appr_reply(self, S, msg_id, reply_to, text="да", author_id=APPROVER, at=None, chat=INBOX_CHAT,
                   reply_to_is_bot=True):
        return S.on_approval_reply(chat=chat, msg_id=str(msg_id),
                                   reply_to=None if reply_to is None else str(reply_to),
                                   reply_to_is_bot=reply_to_is_bot, thread_id=None, author_id=author_id,
                                   author_username="owner", is_bot=False, text=text,
                                   at=self.e.clock() if at is None else at,
                                   by={"kind": "human", "id": author_id, "name": "owner"})

    def stage(self, S, cid, tid, stage, evidence, by=BY_APPROVER):
        return S.record_stage(cid, task_id=tid, stage=stage, evidence=evidence, by=by,
                              idem_key="stage:%s:%s" % (tid, stage))

    def settle(self, S, cid, oid, by=BY_APPROVER, rv=None, **kw):
        if rv is None:
            rv = self.e.db.one("SELECT row_ver FROM rc_obligation WHERE id=?", (oid,))["row_ver"]
        return S.settle_obligation(cid, obligation_id=oid, by=by, idem_key="settle:%s:%d" % (oid, rv),
                                   expect_row_ver=rv, **kw)

    def readback_result(self, S, cid, tid, ver=1, outcome="landed"):
        """Ступень 5 по CONTRACT §14 Д12: expect_readback → claim_execution → mark_written → on_readback."""
        target = {"sink": "fake", "task_id": tid}
        o = S.expect_readback(cid, task_id=tid, action="result", target=target, by=BY_SPL,
                              idem_key="rb:%s:%d:%s:result" % (cid, ver, tid), expect_ver=ver)
        self.assertCode(o, "ok", msg="expect_readback")
        rb = dget(o, "exp_id")
        self.assertTrue(rb, "expect_readback ok без exp_id: %s" % short(o))
        rv = self.e.db.exp(rb)["row_ver"]
        o = S.claim_execution(rb, by=BY_SPL, idem_key="exec:%s:%d" % (rb, rv), expect_row_ver=rv, expect_ver=ver)
        self.assertCode(o, "ok", msg="claim_execution")
        self.assertEqual(self.e.db.exp(rb)["state"], "in_flight")
        rv = self.e.db.exp(rb)["row_ver"]
        tw = self.e.clock()
        o = S.mark_written(rb, result={"ok": True, "row": None, "written_at": tw}, by=BY_SPL,
                           idem_key="written:%s:%d" % (rb, rv), expect_row_ver=rv)
        self.assertCode(o, "ok", msg="mark_written(ok)")
        self.assertEqual(self.e.db.exp(rb)["state"], "waiting", "mark_written(ok) → waiting (§4.2)")
        self.e.clock.advance(5)
        ev = {"kind": "readback", "ref": "sink:fake:%s" % tid, "source": "sink:fake", "written_at": tw,
              "read_at": tw + 5.0, "outcome": outcome, "expected": target, "got": target, "target": target}
        o = S.on_readback(rb, evidence=ev, by=BY_SPL, idem_key="readback:%s:%s" % (rb, ev["read_at"]))
        return rb, o

    def task_fact_ids(self, cid, kinds=("staff_answer", "readback")):
        return [r["id"] for r in self.e.db.facts(cid) if r["kind"] in kinds and r["state"] == "valid"]


# ================================================================================================ открытие, изоляция
class TestOpen(K4StoreBase):

    def test_I19_I33_K4C16_unavailable_never_empty(self):
        """I19/I33, К4-C16: нет файла, порча, чужая/иная схема, не тот schema_version, относительный путь →
        StoreUnavailable (ValueError); открытие ничего не создаёт; create на непустой схеме → StoreUnavailable."""
        d = tempfile.mkdtemp(prefix="k4store_unav_", dir=TTMP)
        clock, ids = FakeClock(T0), IdGen()

        def opener(p):
            return Store(p, role="test", clock=clock, new_id=ids)

        missing = os.path.join(d, "missing.db").replace("\\", "/")
        with self.assertRaises(StoreUnavailable):
            opener(missing)
        for suffix in ("", "-wal", "-shm", "-journal"):
            self.assertFalse(os.path.exists(missing + suffix), "открытие создало %s (I33)" % (missing + suffix))

        corrupt = os.path.join(d, "corrupt.db").replace("\\", "/")
        with open(corrupt, "wb") as f:
            f.write(b"\x00k4-not-a-sqlite-file\xff" * 512)
        with self.assertRaises(StoreUnavailable):
            opener(corrupt)

        empty = os.path.join(d, "empty.db").replace("\\", "/")
        open(empty, "wb").close()
        with self.assertRaises(StoreUnavailable):
            opener(empty)

        foreign = os.path.join(d, "foreign.db").replace("\\", "/")
        con = _ORIG_CONNECT(foreign)
        con.execute("CREATE TABLE clients(row INTEGER, name TEXT)")
        con.commit()
        con.close()
        with self.assertRaises(StoreUnavailable):
            opener(foreign)

        partial = os.path.join(d, "partial.db").replace("\\", "/")
        con = _ORIG_CONNECT(partial)
        con.execute("CREATE TABLE rc_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.executemany("INSERT INTO rc_meta(key, value) VALUES (?, ?)",
                        [("schema_version", "1"), ("store_id", "x"), ("created_at", "0")])
        con.commit()
        con.close()
        with self.assertRaises(StoreUnavailable):
            opener(partial)

        e = Env(self, None, tag="k4store_ver")
        e.db.x("UPDATE rc_meta SET value='2' WHERE key='schema_version'")
        with self.assertRaises(StoreUnavailable):
            opener(e.path)

        e2 = Env(self, None, tag="k4store_exists")
        with self.assertRaises(StoreUnavailable):
            Store.create(e2.path, clock=clock, new_id=ids)

        old = os.getcwd()
        os.chdir(d)                            # относительный путь не должен ничего создать даже здесь
        try:
            rel = "k4_relative_%s.db" % ids()[-8:]
            with self.assertRaises((StoreUnavailable, ValueError)):
                opener(rel)
            with self.assertRaises((StoreUnavailable, ValueError)):
                Store.create(rel, clock=clock, new_id=ids)
            self.assertFalse(os.path.exists(os.path.join(d, rel)), "относительный путь создал файл (I33)")
        finally:
            os.chdir(old)

    def test_I33_writer_opens_existing_file_uri_without_create_store_id_shared(self):
        """I33, CONTRACT §2 «Открытие»: писатель открывает `file:<abs>?mode=rw` (uri=True), без создания; store_id из
        rc_meta один для двух Store разных ролей (CONTRACT §14 Д1)."""
        e = self.env()
        spy = ConnSpy()
        with spy.patched():
            S = e.store("splinter")
            W = e.store("wa")
            cid = self.new_case(S, row_ivan())
            S.case_view(cid)
            W.blockers(cid)
        self.assertTrue(spy.calls, "Store не открыл ни одного соединения через sqlite3.connect")
        for a, kw in spy.calls:
            dbarg = str(a[0] if a else kw.get("database"))
            uri = kw.get("uri") if "uri" in kw else (a[7] if len(a) > 7 else None)
            self.assertIs(uri, True, "соединение без uri=True (I33): %r %r" % (a, kw))
            self.assertTrue(dbarg.startswith("file:"), "соединение не URI-путём: %r" % dbarg)
            m = re.search(r"[?&]mode=(\w+)", dbarg)
            self.assertTrue(m and m.group(1) in ("rw", "ro"), "режим открытия не rw/ro (создание запрещено): %r" % dbarg)
        meta = dict((r["key"], r["value"]) for r in e.db.q("SELECT key, value FROM rc_meta"))
        self.assertEqual(meta.get("schema_version"), "1")
        self.assertEqual(meta.get("store_id"), e.store_id, "Store.create отдаёт store_id из rc_meta")
        self.assertEqual(S.store_id, e.store_id)
        self.assertEqual(W.store_id, e.store_id)
        self.assertNotEqual(S.boot_id, W.boot_id, "boot_id = new_id() каждого объекта (§5)")

    def _module_sources(self):
        out = {}
        for name in ("rental_case.py", "rental_case_rules.py", "rental_case_adapters.py"):
            p = os.path.join(ROOT, name)
            self.assertTrue(os.path.isfile(p), "нет модуля %s (CONTRACT шапка «модули»)" % name)
            with open(p, encoding="utf-8") as f:
                out[name] = f.read()
        return out

    @staticmethod
    def _dotted(node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
        return ""

    @staticmethod
    def _code_strings(tree):
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None) or []
                if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docs.add(id(body[0].value))
        return [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]

    def test_I20_K4C18_K4C19_modules_static_and_injected_clock_ids(self):
        """I20, К4-C18/C19: модули не импортируют сеть/конфиги, не читают окружение, разбираются под 3.8; правила
        без БД и часов; utcfromtimestamp нигде; адаптеры без bridge_client/splinter/wa_agent*/telegram (§9.1);
        часы и id инжектированы — события и строки несут ровно значения подложных часов и источника id (I1)."""
        net = {"socket", "urllib", "urllib3", "http", "requests", "ssl", "ftplib", "smtplib", "httpx", "aiohttp",
               "websocket", "websockets", "telethon", "telegram", "dotenv", "configparser"}
        for name, src in self._module_sources().items():
            tree = ast.parse(src, feature_version=(3, 8))             # К4-C19
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                    if node.module == "os":
                        bad = [a.name for a in node.names if a.name in ("environ", "getenv", "environb")]
                        self.assertEqual(bad, [], "%s: from os import %s (I20)" % (name, bad))
                for m in mods:
                    top = m.split(".")[0]
                    self.assertNotIn(top, net, "%s: импорт %s — сеть/конфиг в модуле (I20)" % (name, m))
                    if name == "rental_case_rules.py":
                        self.assertNotEqual(top, "sqlite3", "правила чистые: без БД (§6)")
                    if name == "rental_case_adapters.py":
                        bad = top in ("bridge_client", "splinter", "telegram") or (
                            top.startswith("wa_agent") and top != "wa_agent_tools")
                        self.assertFalse(bad, "адаптер импортирует %s (§9.1)" % m)
                if isinstance(node, ast.Attribute):
                    dotted = self._dotted(node)
                    self.assertNotIn(dotted, ("os.environ", "os.environb", "os.getenv", "os.putenv"),
                                     "%s: %s — чтение окружения (I20)" % (name, dotted))
                    self.assertFalse(dotted.endswith("utcfromtimestamp"),
                                     "%s: utcfromtimestamp запрещён (CONTRACT §1.1, шапка)" % name)
                if isinstance(node, ast.Call) and name == "rental_case_rules.py":
                    dotted = self._dotted(node.func)
                    self.assertNotIn(dotted, ("time.time", "time.monotonic", "datetime.now", "datetime.datetime.now",
                                              "datetime.utcnow", "datetime.datetime.utcnow", "date.today",
                                              "datetime.date.today", "uuid.uuid4", "random.random"),
                                     "правила зовут часы/случайность (%s) — не чистые (§6, I20)" % dotted)
                if isinstance(node, ast.Attribute) and name == "rental_case.py" and node.attr == "executescript":
                    self.fail("rental_case.py: executescript делает COMMIT — схема создаётся по одному execute (§2)")
        # поведение: часы и id — инжектированные
        self.assertIsNotNone(PARAMS_DEFAULT)
        e = Env(self, synth_params(), t0=T0 + 0.123456, tag="k4store_clock")
        self.e = e
        S = e.store("splinter")
        self.assertIn(S.boot_id, e.ids.issued, "boot_id не из new_id() (§5)")
        self.assertIn(e.store_id, e.ids.issued, "store_id не из new_id() (§2)")
        cid = self.new_case(S, row_ivan())
        self.assertTrue(cid.startswith("RC-") and cid[3:] in e.ids.issued, "case_id = 'RC-' + new_id() (I1): %s" % cid)
        case = e.db.case(cid)
        self.assertEqual(case["created_at"], e.clock(), "created_at не из инжектированных часов (I20)")
        evs = e.db.events(cid, "case_opened")
        self.assertEqual(len(evs), 1, "главное событие case_opened (§8.1)")
        self.assertEqual(evs[0]["at"], e.clock(), "время события не из инжектированных часов (I20)")

    def test_I23_K4C14_sql_writes_only_in_rental_case(self):
        """I23, К4-C14: SQL записи в rc_* есть только в rental_case.py (строки кода правил и адаптеров без
        INSERT/UPDATE/DELETE/REPLACE над rc_*)."""
        rx = re.compile(r"(?is)\b(insert\s+(or\s+\w+\s+)?into|update\s+\S+\s+set|delete\s+from|replace\s+into)\b")
        srcs = self._module_sources()
        for name in ("rental_case_rules.py", "rental_case_adapters.py"):
            tree = ast.parse(srcs[name], feature_version=(3, 8))
            for s in self._code_strings(tree):
                self.assertIsNone(rx.search(s), "%s: SQL записи вне rental_case.py (I23): %r" % (name, s[:120]))
        tree = ast.parse(srcs["rental_case.py"], feature_version=(3, 8))
        self.assertTrue(any(re.search(r"(?is)\binsert\s+(or\s+\w+\s+)?into\b", s) for s in self._code_strings(tree)),
                        "в rental_case.py не найдено SQL записи — писатель не там, где назначен контрактом (I23)")

    def test_I38_patch_finds_case_only_through_resolve(self):
        """I38, К4-C22: добавленные строки интеграционного патча не ищут дело мимо Store.resolve (find_cases и SQL к
        rc_* запрещены). Патч — серия от k4-base (DESIGN §11), шаг 1 в нём — сами модули: строки единственного
        писателя rental_case.py (SQL к rc_* там по контракту, I23) и тестов (сырые вставки фикстур) не судятся;
        судятся все прочие файлы патча — места §11 (wa_agent*.py, splinter.py) и rental_case_rules/adapters.
        Положительный контроль: четыре файла мест §11 обязаны найтись среди судимых, иначе проверка пуста.
        Патч пишется отдельным шагом — пока его нет, проверка пропускается с причиной."""
        cands = [os.environ.get("K4_PATCH") or "", os.path.join(ROOT, "..", "out", "k4_integration.patch"),
                 os.path.join(ROOT, "out", "k4_integration.patch")]
        path = next((p for p in cands if p and os.path.isfile(p)), None)
        if not path:
            self.skipTest("out/k4_integration.patch ещё не собран — I38 проверит набор интеграции и проверяющий")
        added, judged, cur = [], set(), None
        with open(path, encoding="utf-8") as f:
            for ln in f.read().splitlines():
                if ln.startswith("diff --git "):
                    cur = ln.split(" b/", 1)[1] if " b/" in ln else None
                    continue
                if (ln.startswith("+") and not ln.startswith("+++") and cur and cur != "rental_case.py"
                        and not cur.startswith("tests/")):
                    added.append((cur, ln[1:]))
                    judged.add(cur)
        for must in ("splinter.py", "wa_agent.py", "wa_agent_model.py", "wa_agent_tools.py"):
            self.assertIn(must, judged, "место §11 %s не найдено среди судимых строк патча — проверка пуста (I38)"
                          % must)
        sql = re.compile(r"(?i)\b(from|into|update|join)\s+\"?rc_\w+")
        for name, ln in added:
            self.assertNotIn("find_cases(", ln, "%s: патч ищет дело через find_cases (I38): %r" % (name, ln))
            self.assertIsNone(sql.search(ln), "%s: патч ходит SQL к rc_* мимо Store (I38): %r" % (name, ln))


# ================================================================================================ схема §2
# ---------------------------------------------- фикстуры схемы: сырые вставки по колонкам CONTRACT §2 (только TestSchema)
def fx_rental(cid, **over):
    cols = {"case_id": cid, "current": 1, "booking_id": None, "plate": PLATE, "bike_name": BIKE, "model_req": None,
            "name_seen": "Иван", "name_norm": "иван", "start_at": "2026-10-01 10:00", "end_at": "2026-10-12 10:00",
            "start_day": "2026-10-01", "end_day": "2026-10-12", "days": 11, "status_seen": "В аренде",
            "crm_row_seen": 812, "bound_by": "anchor", "source": CLIENTS_SRC, "read_at": T0, "observed_at": T0,
            "ref": "строка 812", "method": "door", "author": "test", "case_ver": 1}
    cols.update(over)
    return cols


def fx_doc(cid, rid, ext, kind="contract_signed", status="verified", **over):
    cols = {"case_id": cid, "kind": kind, "ext_id": ext, "reg_row": 233,
            "sha256": ("ab" * 32) if kind == "contract_pdf" else None, "signed_at": "2026-10-01 10:12",
            "status": status, "bound_by": "human", "rental_id": rid, "source": "test", "read_at": T0,
            "author": "test", "case_ver": 1, "reason": None, "ref": "строка 233", "method": "door",
            "observed_at": T0}
    cols.update(over)
    return cols


def fx_obl(cid, idem, **over):
    cols = {"case_id": cid, "kind": "money", "role": "rent", "direction": "from_client", "amount": 100.0,
            "currency": "THB", "outcome": "valid", "required": 0, "state": "open", "closed_by": None,
            "close_ref": None, "close_fact_id": None, "close_author": None, "close_second_id": None,
            "source": "test", "ref": "raw", "method": "human", "read_at": T0, "observed_at": T0, "created_at": T0,
            "updated_at": T0, "case_ver": 1, "row_ver": 1, "idem_key": idem}
    cols.update(over)
    return cols


def fx_event(idem, **over):
    cols = {"case_id": None, "exp_id": None, "at": T0, "type": "version_bumped", "ver_before": None,
            "ver_after": None, "author": "test", "source": None, "ref": None, "payload": "{}",
            "payload_sha": "0" * 64, "idem_key": idem}
    cols.update(over)
    return cols


def fx_link(cid, **over):
    cols = {"case_id": cid, "kind": "booking_id", "value": BK_IVAN, "status": "candidate", "source": "test",
            "ref": None, "author": "test", "at": T0, "case_ver": 1}
    cols.update(over)
    return cols


def fx_answer(eid, cid, msg_id, **over):
    cols = {"exp_id": eid, "case_id": cid, "chat": INBOX_CHAT, "msg_id": msg_id, "reply_to": "1",
            "thread_id": None, "post_role": "card", "author_id": APPROVER, "author_username": "owner", "at": T0,
            "received_at": T0, "text": "да", "verdict": "accepted", "decision": "yes", "execute": 0,
            "case_ver_at": 1, "promoted_by": None}
    cols.update(over)
    return cols


def fx_stage(cid, tid, stage, ref, idem, **over):
    cols = {"task_id": tid, "case_id": cid, "stage": stage, "evidence_kind": "human_mark", "evidence_ref": ref,
            "evidence": "{}", "flags": "[]", "author": "test", "at": T0, "case_ver": 1, "idem_key": idem}
    cols.update(over)
    return cols


COVER_HUMAN = {"cover_from": "2026-10-01", "cover_to": "2026-10-12", "cover_basis": "human_confirmed",
               "cover_ref": "PDF договора: срок аренды 01.10–12.10", "cover_by": APPROVER, "cover_act": "btn:cover:1",
               "cover_at": T0}
COVER_DOC = {"cover_from": "2026-10-01", "cover_to": "2026-10-12", "cover_basis": "document",
             "cover_ref": "договор п.2", "cover_at": T0}
COVER_OK = [("ok-null", {}), ("ok-human", COVER_HUMAN), ("ok-doc", COVER_DOC),
            ("ok-add", dict(COVER_DOC, cover_basis="addendum"))]
COVER_BAD = [
    ("h-no-by", dict(COVER_HUMAN, cover_by=None)),
    ("h-no-act", dict(COVER_HUMAN, cover_act=None)),
    ("h-empty-act", dict(COVER_HUMAN, cover_act="")),
    ("d-with-by", dict(COVER_DOC, cover_by=APPROVER)),
    ("d-with-act", dict(COVER_DOC, cover_act="btn:x")),
    ("from-gt-to", dict(COVER_HUMAN, cover_from="2026-10-13")),
    ("no-ref", dict(COVER_HUMAN, cover_ref=None)),
    ("empty-ref", dict(COVER_HUMAN, cover_ref="")),
    ("no-at", dict(COVER_HUMAN, cover_at=None)),
    ("basis-binding", dict(COVER_HUMAN, cover_basis="binding_at_verify")),
    ("partial-from", {"cover_from": "2026-10-01"}),
    ("partial-basis", {"cover_basis": "human_confirmed"}),
    ("pdf-cover", dict(COVER_HUMAN, kind="contract_pdf")),            # покрытие PDF наследуется при чтении
    ("pdf-nosha", {"kind": "contract_pdf", "sha256": None}),          # verified PDF без sha256
    ("signed-norental", {"rental_id": None}),                         # verified договор без привязки
]


def obl_bad(fid, did):
    """CHECK rc_obligation (I26, I45): каждая — IntegrityError."""
    return [
        dict(state="closed", closed_by="stage"),                                     # деньги: только write|human
        dict(state="closed", closed_by=None),
        dict(outcome=None),
        dict(state="closed", closed_by="write", close_fact_id=None, close_second_id=did),
        dict(state="closed", closed_by="write", close_fact_id=fid, close_second_id=None),   # I45: нет второго
        dict(role="deposit", state="closed", closed_by="write", close_fact_id=fid, close_second_id=did),
        dict(state="waived", closed_by="write", close_fact_id=fid, close_second_id=did),
        dict(kind="bike", role="return", direction="internal", outcome=None, state="waived", closed_by="stage"),
    ]


def obl_ok(fid, did):
    return [
        dict(state="closed", closed_by="human", close_ref="решение 1001"),
        dict(state="closed", closed_by="write", close_fact_id=fid, close_second_id=did),
        dict(kind="bike", role="return", direction="internal", outcome=None, state="closed", closed_by="stage"),
    ]


class TestSchema(K4StoreBase):

    def test_I5_K4C15_event_append_only_triggers(self):
        """I5, К4-C15: UPDATE/DELETE rc_event → ошибка триггера, журнал не меняется."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        ev = e.db.events(cid)[0]
        before = e.db.dump()
        with self.assertRaises(sqlite3.DatabaseError) as cm:
            e.db.x("UPDATE rc_event SET type='tampered' WHERE seq=?", (ev["seq"],))
        self.assertIn("append-only", str(cm.exception))
        with self.assertRaises(sqlite3.DatabaseError):
            e.db.x("DELETE FROM rc_event WHERE seq=?", (ev["seq"],))
        with self.assertRaises(sqlite3.DatabaseError):
            e.db.x("DELETE FROM rc_event")
        self.assertNoWrites(before, "UPDATE/DELETE rc_event")

    def test_K4C12_event_check_case_or_exp_or_named_type(self):
        """CONTRACT §2 CHECK rc_event / §8.1: событие без дела и ожидания — только recovered, client_inbound,
        human_intervention, answer_orphaned (К4-C12)."""
        e = self.env()
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_event", fx_event("raw:ev:1", type="version_bumped"))
        for i, t in enumerate(("recovered", "client_inbound", "human_intervention", "answer_orphaned")):
            e.db.insert("rc_event", fx_event("raw:ev:ok:%d" % i, type=t))

    def test_I2_partial_unique_links(self):
        """I2: подтверждённый booking_id и подтверждённый якорь — не более чем у одного дела (частичные UNIQUE);
        crm_row подтверждённым не бывает (CHECK)."""
        e = self.env()
        S = e.store("splinter")
        c1 = self.new_case(S, row_ivan())
        c2 = self.new_case(S, row_boris())
        links = e.db.q("SELECT * FROM rc_link WHERE case_id=?", (c1,))
        self.assertTrue(any(l["kind"] == "booking_id" and l["value"] == BK_IVAN and l["status"] == "confirmed"
                            for l in links), "open_case с booking_id → ссылка confirmed (§4.6): %r" % links)
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_link", fx_link(c2, kind="booking_id", value=BK_IVAN, status="confirmed"))
        e.db.insert("rc_link", fx_link(c2, kind="booking_id", value=BK_IVAN, status="candidate"))
        e.db.insert("rc_link", fx_link(c2, kind="anchor", value="9999|2026-11-01|тест", status="confirmed"))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_link", fx_link(c1, kind="anchor", value="9999|2026-11-01|тест", status="confirmed"))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_link", fx_link(c2, kind="crm_row", value="812", status="confirmed"))

    def test_I3_one_current_rental(self):
        """I3: не более одной текущей привязки аренды (ux_rental_current); CHECK: дата начала или booking_id,
        непустой номер."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        self.assertEqual(e.db.count("rc_rental", "case_id=? AND current=1", (cid,)), 1)
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_rental", fx_rental(cid))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_rental", fx_rental(cid, current=0, start_day=None, booking_id=None))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_rental", fx_rental(cid, current=0, plate=""))
        e.db.insert("rc_rental", fx_rental(cid, current=0))

    def test_I26_I45_obligation_checks(self):
        """I26/I45, CONTRACT §2 CHECK rc_obligation: деньги закрывают только write|human; write — только rent с фактом
        и вторым источником; closed без закрывателя и waived не human запрещены; у денег outcome обязателен."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        fk = ["bike_event", BIKE, "handover", "ev-raw"]
        o = S.record_fact(cid, kind="bike_event", value={"type": "handover"},
                          source=src_of("события байка", "ev-raw", "door", T_OBS), scope="case", by=BY_CODE,
                          idem_key=k_fact(cid, fk, T_OBS), fkey=fk)
        self.assertCode(o, "ok", msg="record_fact")
        fid = e.db.facts(cid, "bike_event")[0]["id"]
        rid = e.db.current_rental(cid)["id"]
        e.db.insert("rc_document", fx_doc(cid, rid, "doc-second"))
        did = e.db.one("SELECT id FROM rc_document WHERE ext_id='doc-second'")["id"]
        for i, over in enumerate(obl_bad(fid, did)):
            with self.assertRaises(sqlite3.IntegrityError, msg="CHECK rc_obligation пропустил %r" % over):
                e.db.insert("rc_obligation", fx_obl(cid, "raw:obl:bad:%d" % i, **over))
        for i, over in enumerate(obl_ok(fid, did)):
            e.db.insert("rc_obligation", fx_obl(cid, "raw:obl:ok:%d" % i, **over))

    def test_I28_answer_execute_check(self):
        """I28: execute=1 только при verdict=accepted и decision=yes (CHECK rc_answer); UNIQUE(chat, msg_id)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.ask(S, cid)
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_answer", fx_answer(eid, cid, "a1", verdict="reference_late", execute=1))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_answer", fx_answer(eid, cid, "a2", decision="no", execute=1))
        e.db.insert("rc_answer", fx_answer(eid, cid, "a3", execute=1))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_answer", fx_answer(eid, cid, "a3", verdict="reference_answered"))

    def test_I46_document_cover_checks(self):
        """I46, К4-C39 (DDL): verified с cover_* NULL проходит (CHECK «verified ⇒ покрытие» нет); покрытие либо всё
        NULL, либо целиком с источником дат и только у contract_signed; human_confirmed — с cover_by и cover_act;
        document/addendum — без них; cover_from ≤ cover_to; cover_basis ∈ {document, addendum, human_confirmed}."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        rid = e.db.current_rental(cid)["id"]
        e.db.insert("rc_document", fx_doc(cid, rid, "ok-unverified", status="unverified", rental_id=None))
        for ext, over in COVER_OK:                                   # в т. ч. verified без покрытия (ok-null)
            e.db.insert("rc_document", fx_doc(cid, rid, ext, **over))
        for ext, over in COVER_BAD:
            with self.assertRaises(sqlite3.IntegrityError, msg="CHECK rc_document пропустил %s" % ext):
                e.db.insert("rc_document", fx_doc(cid, rid, ext, **over))

    def test_I27_stage_evidence_ref_unique(self):
        """I27: один ref — одна ступень одной задачи (UNIQUE(evidence_ref), UNIQUE(task_id, stage))."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        t1 = self.new_task(S, cid, kind="readiness", ref="r1")
        t2 = self.new_task(S, cid, kind="delivery", ref="r2")
        e.db.insert("rc_stage", fx_stage(cid, t1, "physically_done", "btn:raw:1", "raw:st:1"))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_stage", fx_stage(cid, t2, "physically_done", "btn:raw:1", "raw:st:2"))
        with self.assertRaises(sqlite3.IntegrityError):
            e.db.insert("rc_stage", fx_stage(cid, t1, "physically_done", "btn:raw:2", "raw:st:3"))

    def test_F2_no_source_version_column(self):
        """CONTRACT §8.4 «Основания версии» (F2 К3): версии внешнего источника в схеме нет ни колонкой; версия дела —
        rc_case.ver; observed_at/read_at — время наших чтений."""
        e = self.env()
        tables = [r["name"] for r in e.db.q(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'rc!_%' ESCAPE '!'")]
        expected = {"rc_meta", "rc_case", "rc_link", "rc_contact", "rc_rental", "rc_fact", "rc_document",
                    "rc_obligation", "rc_task", "rc_stage", "rc_expect", "rc_post", "rc_answer", "rc_reply_unlinked",
                    "rc_notice", "rc_event"}
        self.assertEqual(set(tables), expected, "состав таблиц схемы 1 (§2)")
        for t in tables:
            cols = [r["name"] for r in e.db.q('PRAGMA table_info("%s")' % t)]
            bad = [c for c in cols if SOURCE_VER_KEY.match(c)]
            self.assertEqual(bad, [], "%s: колонка версии внешнего источника %r (F2 К3)" % (t, bad))
        self.assertIn("ver", [r["name"] for r in e.db.q('PRAGMA table_info("rc_case")')])


# ================================================================================================ дело, идентичность
class TestCaseIdentity(K4StoreBase):

    def test_I1_I4_case_id_born_once_ver_only_by_version_bumped(self):
        """I1/I4, К4-C1: case_id = 'RC-'+new_id() один раз; не-подъёмные мутации ver не меняют; ver растёт ровно на 1
        только с version_bumped (ver_before/ver_after); устаревший expect_ver → conflict без записей (I8)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        self.assertTrue(cid.startswith("RC-") and cid[3:] in e.ids.issued)
        o = S.add_contact(cid, channel="tg_username", value="ivan_tg", by=BY_APPROVER,
                          source=src_of("решение одобряющего", "btn:contact:1", "human", T0),
                          idem_key="contact:%s:tg_username:ivan_tg:btn:contact:1" % cid)
        self.assertCode(o, "ok", msg="add_contact одобряющим")
        fk = ["bike_event", BIKE, "handover", "ev-1"]
        o = S.record_fact(cid, kind="bike_event", value={"type": "handover"},
                          source=src_of("события байка", "ev-1", "door", T_OBS), scope="case", by=BY_CODE,
                          idem_key=k_fact(cid, fk, T_OBS), fkey=fk)
        self.assertCode(o, "ok", msg="record_fact")
        self.new_task(S, cid)
        self.ask(S, cid)
        self.assertEqual(e.db.case(cid)["ver"], 1, "контакты/факты/задачи/ожидания версию не поднимают (DESIGN §4.1)")
        self.assertEqual(e.db.events(cid, "version_bumped"), [])
        for ver in (1, 2):
            o = S.bump_version(cid, reason="period_changed", ref="test:bump:%d" % ver, by=BY_APPROVER,
                               idem_key="bump:%s:%d:period_changed:test:bump:%d" % (cid, ver, ver), expect_ver=ver)
            self.assertCode(o, "ok", msg="bump_version %d" % ver)
            self.assertEqual(o.get("ver"), ver + 1)
            self.assertEqual(case_id_of(o) or cid, cid)
        bumps = e.db.events(cid, "version_bumped")
        self.assertEqual([(b["ver_before"], b["ver_after"]) for b in bumps], [(1, 2), (2, 3)])
        self.assertEqual(e.db.case(cid)["ver"], 3)
        self.assertEqual(e.db.count("rc_case"), 1, "второе дело не рождено (I1)")
        before = e.db.dump()
        o = S.bump_version(cid, reason="period_changed", ref="test:stale", by=BY_APPROVER,
                           idem_key="bump:%s:1:period_changed:test:stale" % cid, expect_ver=1)
        self.assertCode(o, "conflict", msg="устаревший expect_ver")
        self.assertEqual((o.get("expected_ver"), o.get("current_ver")), (1, 3), "conflict несёт версии (§1.2)")
        self.assertNoWrites(before, "conflict по версии (I8)")

    def test_I5_each_mutation_has_main_event(self):
        """I5/§8.1: каждая мутация пишет главное событие с её idem_key и payload_sha; подсобытия — '<ключ>#<n>'."""
        e = self.env()
        S = e.store("splinter")
        key = k_open("test", row_ivan())
        cid = self.new_case(S, row_ivan())
        main = e.db.q("SELECT * FROM rc_event WHERE idem_key=?", (key,))
        self.assertEqual(len(main), 1, "главное событие open_case с idem_key вызова (§5)")
        self.assertEqual(main[0]["type"], "case_opened")
        self.assertRegex(main[0]["payload_sha"], r"^[0-9a-f]{64}$")
        pl = json.loads(main[0]["payload"])
        for k in ("origin", "booking_id", "anchor", "rental_id", "obligations", "near_cases"):
            self.assertIn(k, pl, "payload case_opened без %s (§8.1)" % k)
        for ev in e.db.events(cid):
            if ev["idem_key"] != key:
                self.assertTrue(ev["idem_key"].startswith(key + "#"),
                                "событие той же транзакции не подсобытие главного: %r" % ev["idem_key"])
        kb = "bump:%s:1:cancel:test:ev" % cid
        o = S.bump_version(cid, reason="cancel", ref="test:ev", by=BY_APPROVER, idem_key=kb, expect_ver=1)
        self.assertCode(o, "ok")
        ev = e.db.one("SELECT * FROM rc_event WHERE idem_key=?", (kb,))
        self.assertIsNotNone(ev, "главное событие bump_version")
        self.assertEqual(ev["type"], "version_bumped")
        self.assertEqual(o.get("event_seq"), ev["seq"], "event_seq исхода = seq главного события (§1.2)")

    def test_I2_K4C2_booking_id_one_case_api(self):
        """I2, К4-C2, §4.1: open_case с booking_id, подтверждённым у другого дела → rejected(booking_taken,
        data.case_id), без записей."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        other = make_row(902, "Бронь", "PCX 160 4410", "Анна", "2026-10-20 10:00", "2026-10-25 10:00",
                         "+66 86 111 2233", booking_id=BK_IVAN)
        before = e.db.dump()
        o = self.open_case(S, other, origin="splinter")
        self.assertCode(o, "rejected", "booking_taken", msg="второе дело на тот же booking_id")
        self.assertEqual(dget(o, "case_id"), cid)
        self.assertNoWrites(before, "booking_taken")

    def test_section41_open_case_rejections(self):
        """§5.1 open_case: нет номера → rejected(no_plate); нет даты И нет booking_id → rejected(no_start); без записей."""
        e = self.env()
        S = e.store("splinter")
        before = e.db.dump()
        o = self.open_case(S, make_row(950, "Бронь", "NMAX 155", "Олег", "2026-10-20 10:00", "2026-10-22 10:00",
                                       "+66 80 000 0001"))
        self.assertCode(o, "rejected", "no_plate")
        o = self.open_case(S, make_row(951, "Бронь", "NMAX 155 7001", "Олег", None, None, "+66 80 000 0001"),
                           key="open:test:row:строка 951:%s" % T_OBS)
        self.assertCode(o, "rejected", "no_start")
        self.assertNoWrites(before, "open_case отказы")

    def test_I25_K4C27_required_obligations_born_with_case(self):
        """I25, §3.4, DESIGN §7.3, К4-C27: обязательный набор рождается open_case той же транзакцией; паспорт-залог —
        документ passport_deposit (unverified) + document/passport_return; notify_final при UNKNOWN — unknown;
        у денег outcome задан; блокеры закрытия есть."""
        e = self.env()
        S = e.store("splinter")
        o = self.open_case(S, row_ivan())
        self.assertCode(o, "ok")
        cid = case_id_of(o)
        rows = e.db.obligations(cid)
        ids = dget(o, "obligations")
        if ids is not None:
            self.assertEqual(sorted(int(x) for x in ids), sorted(r["id"] for r in rows),
                             "data.obligations = обязательства дела (§5.1)")
        by = dict(((r["kind"], r["role"]), r) for r in rows)
        want = {("bike", "return"): "open", ("money", "rent"): "unknown", ("money", "deposit"): "open",
                ("money", "deposit_refund"): "open", ("client", "notify_final"): "unknown"}
        for k, st in want.items():
            self.assertIn(k, by, "нет обязательного %s/%s (I25): %s" % (k[0], k[1], short(rows)))
            self.assertEqual(by[k]["state"], st, "%s/%s: состояние при рождении (§3.4)" % k)
            self.assertEqual(by[k]["required"], 1, "%s/%s: required=1 (§2)" % k)
            self.assertIsNone(by[k]["closed_by"])
        self.assertNotIn(("bike", "handover"), by, "handover рождается только при «Бронь» (§3.4)")
        self.assertEqual(by[("money", "rent")]["outcome"], "unknown", "клетка 0 → unknown (I26)")
        self.assertEqual(by[("money", "deposit")]["outcome"], "incomplete")
        self.assertEqual(float(by[("money", "deposit")]["amount"]), 3000.0)
        for r in rows:
            if r["kind"] == "money":
                self.assertIn(r["outcome"], ("valid", "unknown", "incomplete"))
            self.assertEqual(r["method"], "door", "src обязательства из чтения строки (§8.4)")
        payloads = " ".join(ev["payload"] for ev in e.db.events(cid))
        self.assertIn("FINAL_NOTICE_REQUIRED", payloads, "why=param_unknown:FINAL_NOTICE_REQUIRED (§3.4)")
        self.assertTrue(S.blockers(cid), "дело с открытыми обязательствами имеет блокеры (I13)")

        o2 = self.open_case(S, row_boris())
        self.assertCode(o2, "ok")
        c2 = case_id_of(o2)
        by2 = dict(((r["kind"], r["role"]), r) for r in e.db.obligations(c2))
        for k in (("bike", "handover"), ("bike", "return"), ("money", "rent"), ("money", "deposit"),
                  ("document", "passport_return"), ("client", "notify_final")):
            self.assertIn(k, by2, "дело Бориса без %s/%s (CONTRACT §14 Д2)" % k)
            self.assertNotEqual(by2[k]["state"], "closed")
        self.assertEqual((by2[("money", "deposit")]["state"], by2[("money", "deposit")]["outcome"]),
                         ("unknown", "unknown"), "залог passport: unknown/unknown (§3.4)")
        self.assertNotIn(("money", "deposit_refund"), by2)
        docs = e.db.q("SELECT * FROM rc_document WHERE case_id=?", (c2,))
        self.assertEqual([(d["kind"], d["status"], d["ext_id"], d["method"]) for d in docs],
                         [("passport_deposit", "unverified", "deposit:845", "door")], "паспорт-залог (§3.4)")
        dl = dget(o2, "documents")
        if dl is not None:
            self.assertEqual([int(x) for x in dl], [docs[0]["id"]])
        self.assertIn("deposit_passport", " ".join(ev["payload"] for ev in e.db.events(c2, "obligation_opened")))

    def test_I34_K4C23_continuation_needs_approver(self):
        """I34, К4-C23, M25: новая строка того же клиента с пересечением при открытом деле →
        unknown(possible_continuation, data.case_id, data.exp_id) + confirm_link у прежнего дела, второго дела нет;
        force_new от кода → rejected(approver_unknown) без записей; от одобряющего — новое дело."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        swap = make_row(901, "В аренде", "PCX 160 4410", "Иван", "2026-10-05 10:00", "2026-10-12 10:00",
                        "+66 81 234 5678", booking_id="0b1f3c2a-7d41-4c55-9a10-000000000901")
        n0 = e.db.count("rc_case")
        o = self.open_case(S, swap)
        self.assertCode(o, "unknown", "possible_continuation")
        self.assertEqual(dget(o, "case_id"), cid)
        ex = e.db.exp(dget(o, "exp_id"))
        self.assertIsNotNone(ex, "confirm_link ожидание не записано")
        self.assertEqual((ex["kind"], ex["case_id"], ex["action"]), ("confirm_link", cid, "confirm"))
        self.assertIsNotNone(ex["cand_sha"])
        self.assertEqual(e.db.count("rc_case"), n0, "второе дело не открыто (I34)")
        before = e.db.dump()
        o = self.open_case(S, swap, force_new=True, key=k_open("test", swap) + ":force-code")
        self.assertCode(o, "rejected", "approver_unknown", msg="force_new не одобряющим")
        self.assertNoWrites(before, "force_new от кода")
        o = self.open_case(S, swap, force_new=True, by=BY_APPROVER, key=k_open("test", swap) + ":force-approver")
        self.assertCode(o, "ok", msg="force_new одобряющим")
        self.assertNotEqual(case_id_of(o), cid)

    def test_I36_I38_superseded_contact_and_resolve(self):
        """I36/I38, §5.1: дело ищется только resolve; контакт добавляет crm/одобряющий (агент → rejected(contact_source));
        superseded-номер клиента дела не находит (none, contact_superseded); активный — находит то же дело."""
        e = self.env()
        S = e.store("wa")
        cid = self.new_case(S, row_ivan())
        acid = self.new_case(S, row_anna())
        r = S.resolve(purpose="client", intent="current", rows=[row_ivan()], moment=T0, observed_at=T_OBS,
                      contact={"channel": "wa", "value": IVAN_WA})
        self.assertEqual((r.get("code"), r.get("case_id")), ("found", cid), "resolve по контакту и booking_id: %s" % short(r))
        r = S.resolve(purpose="client", intent="future", rows=[row_anna()], moment=T0, observed_at=T_OBS,
                      contact={"channel": "wa", "value": ANNA_WA})
        self.assertEqual((r.get("code"), r.get("case_id")), ("found", acid), "resolve по якорю: %s" % short(r))
        before = e.db.dump()
        o = S.add_contact(cid, channel="wa", value="66812349999", by=BY_AGENT,
                          source=src_of("обращение WA", "wa:in:77", "event", T0),
                          idem_key="contact:%s:wa:66812349999:wa:in:77" % cid, supersede_value=IVAN_WA)
        self.assertCode(o, "rejected", "contact_source", msg="агент добавляет контакт")
        self.assertNoWrites(before, "contact_source")
        o = S.add_contact(cid, channel="wa", value="66812349999", by=BY_APPROVER,
                          source=src_of("решение одобряющего", "btn:contact:2", "human", T0),
                          idem_key="contact:%s:wa:66812349999:btn:contact:2" % cid, supersede_value=IVAN_WA)
        self.assertCode(o, "ok", msg="add_contact одобряющим с supersede_value")
        st = dict((r2["value"], r2["status"]) for r2 in e.db.q(
            "SELECT value, status FROM rc_contact WHERE case_id=? AND channel='wa'", (cid,)))
        self.assertEqual(st.get(IVAN_WA), "superseded")
        self.assertEqual(st.get("66812349999"), "active")
        self.assertEqual(e.db.case(cid)["ver"], 1, "контакт версию не поднимает")
        rows_new = [row_ivan(contacts="+66 81 234 9999")]
        r = S.resolve(purpose="client", intent="current", rows=rows_new, moment=T0, observed_at=T0,
                      contact={"channel": "wa", "value": IVAN_WA})
        self.assertEqual(r.get("code"), "none", "superseded-номер нашёл дело (I36): %s" % short(r))
        self.assertEqual(reason_code(r), "contact_superseded")
        r = S.resolve(purpose="client", intent="current", rows=rows_new, moment=T0, observed_at=T0,
                      contact={"channel": "wa", "value": "66812349999"})
        self.assertEqual((r.get("code"), r.get("case_id")), ("found", cid))
        fc = S.find_cases(booking_id=BK_IVAN)
        self.assertTrue(any(isinstance(x, dict) and x.get("case_id") == cid for x in fc), "find_cases для человека")

    def test_I17_resolve_return_two_active_unknown(self):
        """I17, К4-C25, DESIGN §3.3: две «в аренде» одного номера для return → unknown(two_active) с missing и ask,
        без выбора по дате/порядку; resolve — только чтение (без записей)."""
        e = self.env()
        S = e.store("splinter")
        self.new_case(S, row_ivan())
        before = e.db.dump()
        a = row_ivan()
        b = make_row(813, "В аренде", BIKE, "Пётр", "2026-10-03 10:00", "2026-10-15 10:00", "+66 82 000 1111",
                     booking_id="0b1f3c2a-7d41-4c55-9a10-000000000813")
        for rows in ([a, b], [b, a]):
            r = S.resolve(purpose="return", rows=rows, moment=T0, observed_at=T_OBS, plate=PLATE)
            self.assertEqual(r.get("code"), "unknown", "две активные аренды → не found (I17): %s" % short(r))
            self.assertEqual(reason_code(r), "two_active")
            self.assertTrue(r.get("missing") and r.get("ask"), "unknown без missing/ask (К4-C5)")
        self.assertNoWrites(before, "resolve")

    def test_I35_K4C7_cash_without_booking_only_single_claimant(self):
        """I35/I18, К4-C7/C24, M19: касса без booking_id при будущей брони того же номера → unknown(which_rental) с
        претендентами, без записей; при единственном претенденте — bound(plate+day) и факт кассы; повтор — duplicate;
        human-привязка не одобряющим → rejected."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        self.new_case(S, row_boris())
        cash = {"kind": "cash", "src": "tx_find", "row": 2041, "msg_id": "m2041", "link": None,
                "at": "2026-10-05 12:00", "booking_id": None, "bike": BIKE, "amount": 3850, "currency": "THB",
                "role": "оплата аренды", "category": "rental"}
        key = "cash:%s:2041:m2041:%s" % (cid, hashlib.sha256(b"3850|THB||").hexdigest()[:12])
        src = src_of("касса Bot Data «транзакции» (tx_find)", "строка 2041", "door", T_OBS)
        before = e.db.dump()
        o = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan(), row_boris()], source=src, by=BY_CODE, idem_key=key)
        self.assertCode(o, "unknown", "which_rental", msg="касса при будущей брони того же номера")
        self.assertGreaterEqual(len(dget(o, "claimants") or []), 2, "претенденты в исходе: %s" % short(o))
        self.assertNoWrites(before, "bind_cash unknown ожиданий и фактов не рождает")
        o = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan(), row_boris()], source=src, by=BY_AGENT,
                        idem_key=key + ":h", human={"bind": True})
        self.assertCode(o, "rejected", msg="human-привязка не одобряющим")
        self.assertNoWrites(before, "bind_cash human от агента")
        o = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan()], source=src, by=BY_CODE, idem_key=key + ":one")
        self.assertCode(o, "ok", msg="единственный претендент")
        self.assertEqual(dget(o, "bound_by"), "plate+day")
        fid = dget(o, "fact_id")
        f = e.db.one("SELECT * FROM rc_fact WHERE id=?", (fid,))
        self.assertIsNotNone(f, "data.fact_id указывает на факт кассы")
        self.assertEqual((f["kind"], f["case_id"], f["state"]), ("cash", cid, "valid"))
        snap = e.db.dump()
        o2 = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan()], source=src, by=BY_CODE, idem_key=key + ":one")
        self.assertCode(o2, "duplicate")
        self.assertNoWrites(snap, "повтор bind_cash")

    def test_section41_case_cancel_terminal_and_closed_only_additions(self):
        """§4.1/§4.6: cancel_case — одобряющий и только при закрытых/снятых деньгах и документах; якорь → retired;
        после отмены прочие мутации → rejected(case_cancelled) без записей; перебронь с тем же якорем — своё дело.
        Закрытое дело (фикстура: состояние записано в обход Store — положительный путь close_case требует чтения
        «Завершена» назад, которого этот набор не моделирует) принимает только добавления (record_fact contract_ref)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_anna())
        links = e.db.q("SELECT * FROM rc_link WHERE case_id=?", (cid,))
        self.assertTrue(any(l["kind"] == "anchor" and l["status"] == "confirmed" for l in links),
                        "дело без booking_id держит подтверждённый якорь: %r" % links)
        before = e.db.dump()
        o = S.cancel_case(cid, reason="client_cancel", by=BY_CODE, idem_key="cancel:%s:1" % cid, expect_ver=1)
        self.assertCode(o, "rejected", msg="cancel_case кодом")
        o = S.cancel_case(cid, reason="client_cancel", by=BY_APPROVER, idem_key="cancel:%s:1" % cid, expect_ver=1)
        self.assertCode(o, "rejected", msg="cancel_case при открытых деньгах")
        self.assertNoWrites(before, "cancel_case отказы")
        for r in e.db.obligations(cid):
            if r["kind"] in ("money", "document") and r["state"] in ("open", "unknown"):
                self.assertCode(self.settle(S, cid, r["id"], human={"waive": True, "detail": "отмена брони"}), "ok",
                                msg="waive %s" % r["role"])
        o = S.cancel_case(cid, reason="client_cancel", by=BY_APPROVER, idem_key="cancel:%s:1" % cid, expect_ver=1)
        self.assertCode(o, "ok", msg="cancel_case одобряющим")
        self.assertEqual(e.db.case(cid)["state"], "cancelled")
        for l in e.db.q("SELECT * FROM rc_link WHERE case_id=?", (cid,)):
            if l["kind"] in ("anchor", "crm_row"):
                self.assertEqual(l["status"], "retired", "якорь/кандидат отменённого дела → retired: %r" % l)
        self.assertTrue(e.db.events(cid, "case_cancelled"))
        before = e.db.dump()
        ver = e.db.case(cid)["ver"]                    # текущая версия: отказ обязан быть case_cancelled, не conflict
        fk = ["bike_event", "PCX 160 4410", "handover", "ev-c"]
        calls = [
            lambda: S.add_contact(cid, channel="tg_username", value="anna", by=BY_APPROVER,
                                  source=src_of("решение", "btn:c", "human", T0),
                                  idem_key="contact:%s:tg_username:anna:btn:c" % cid),
            lambda: S.bump_version(cid, reason="period_changed", ref="x", by=BY_APPROVER,
                                   idem_key="bump:%s:%d:period_changed:x" % (cid, ver), expect_ver=ver),
            lambda: S.open_task(cid, kind="handover", ref="x", by=BY_APPROVER,
                                idem_key="task:%s:%d:handover:x" % (cid, ver), expect_ver=ver),
            lambda: S.record_fact(cid, kind="bike_event", value={"type": "handover"},
                                  source=src_of("события", "ev-c", "door", T0), scope="case", by=BY_CODE,
                                  idem_key=k_fact(cid, fk, T0), fkey=fk),
        ]
        for i, call in enumerate(calls):
            self.assertCode(call(), "rejected", "case_cancelled", msg="мутация отменённого дела #%d" % i)
        self.assertNoWrites(before, "мутации отменённого дела")
        o = self.open_case(S, row_anna(row=903), origin="splinter")
        self.assertCode(o, "ok", msg="перебронь с тем же якорем после отмены (DESIGN §2.2)")
        self.assertNotEqual(case_id_of(o), cid)

        c2 = self.new_case(S, row_boris())
        e.db.x("UPDATE rc_case SET state='closed' WHERE case_id=?", (c2,))
        before = e.db.dump()
        o = S.add_contact(c2, channel="tg_username", value="boris", by=BY_APPROVER,
                          source=src_of("решение", "btn:b", "human", T0),
                          idem_key="contact:%s:tg_username:boris:btn:b" % c2)
        self.assertCode(o, "rejected", "case_closed")
        fk2 = ["bike_event", BIKE, "return", "ev-b"]
        o = S.record_fact(c2, kind="bike_event", value={"type": "return"}, source=src_of("события", "ev-b", "door", T0),
                          scope="case", by=BY_CODE, idem_key=k_fact(c2, fk2, T0), fkey=fk2)
        self.assertCode(o, "rejected", "case_closed")
        self.assertNoWrites(before, "мутации закрытого дела")
        fk3 = ["contract_ref", BK_BORIS, "doc-old"]
        o = S.record_fact(c2, kind="contract_ref", value={"ref_booking": BK_BORIS, "doc_id": "doc-old"},
                          source=src_of("реестр подписей TB e-Sign (contract_find)", "строка 120", "door", T0),
                          scope="case", by=BY_CODE, idem_key=k_fact(c2, fk3, T0), fkey=fk3)
        self.assertCode(o, "ok", msg="closed → closed: добавление справки договора (§4.1)")
        self.assertEqual((e.db.case(c2)["state"], e.db.case(c2)["ver"]), ("closed", 1))


# ================================================================================================ версия, сверка, чтения
class TestVersionAndRead(K4StoreBase):

    def _facts_three(self, S, cid, tag):
        out = {}
        for kind, scope in (("human_mark", "version"), ("crm_status", "rental"), ("bike_event", "case")):
            fk = [kind, tag, scope]
            o = S.record_fact(cid, kind=kind, value={"tag": tag}, source=src_of("тест", "%s:%s" % (tag, scope), "human",
                                                                               T_OBS),
                              scope=scope, by=BY_CODE, idem_key=k_fact(cid, fk, T_OBS), fkey=fk)
            self.assertCode(o, "ok", msg="record_fact %s/%s" % (kind, scope))
            out[scope] = dget(o, "fact_id") or self.e.db.one(
                "SELECT id FROM rc_fact WHERE case_id=? AND kind=? AND scope=? ORDER BY id DESC", (cid, kind, scope))["id"]
        return out

    def test_I21_bump_revokes_per_design_4_2(self):
        """I21, DESIGN §4.2: подъём (не new_request) в той же транзакции — ожидания без принятого ответа → superseded,
        задачи top_stage<4 → cancelled, факты version и rental → stale (case — нет); new_request задачи не отменяет и
        rental-факты не трогает; new_request от кода при NEW_REQUEST_RULE=UNKNOWN → rejected(param_unknown)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        tid = self.new_task(S, cid)
        eid = self.ask(S, cid, task_id=tid)
        f = self._facts_three(S, cid, "a")
        n_stale = e.db.count("rc_fact", "case_id=? AND state='valid' AND scope IN ('version','rental')", (cid,))
        seq0 = e.db.one("SELECT MAX(seq) AS m FROM rc_event")["m"]
        key = "bump:%s:1:period_changed:test:ext:1" % cid
        o = S.bump_version(cid, reason="period_changed", ref="test:ext:1", by=BY_APPROVER, idem_key=key, expect_ver=1)
        self.assertCode(o, "ok")
        self.assertEqual(o.get("ver"), 2)
        self.assertIn(eid, dget(o, "superseded") or [])
        self.assertIn(tid, dget(o, "cancelled_tasks") or [])
        self.assertEqual(dget(o, "stale_facts"), n_stale)
        self.assertIsInstance(dget(o, "staff_qids_to_close"), list)
        self.assertEqual(e.db.exp(eid)["state"], "superseded")
        self.assertEqual(e.db.task(tid)["state"], "cancelled")
        st = dict((r["id"], r["state"]) for r in e.db.facts(cid))
        self.assertEqual((st[f["version"]], st[f["rental"]], st[f["case"]]), ("stale", "stale", "valid"))
        for ev in e.db.q("SELECT * FROM rc_event WHERE seq > ?", (seq0,)):
            self.assertTrue(ev["idem_key"] == key or ev["idem_key"].startswith(key + "#"),
                            "событие подъёма не главное и не подсобытие его ключа (I5/I21): %r" % ev["idem_key"])
        subs = e.db.q("SELECT * FROM rc_event WHERE idem_key LIKE ?", (key + "#%",))
        self.assertTrue(subs, "отзыв пишется подсобытиями той же транзакции (§8.1)")

        tid2 = self.new_task(S, cid, ver=2, ref="wa:in:502")
        eid2 = self.ask(S, cid, task_id=tid2, ver=2, q_ru="Готов ли шлем к 15.10?")
        f2 = self._facts_three(S, cid, "b")
        before = e.db.dump()
        o = S.bump_version(cid, reason="new_request", ref="wa:in:600", by=BY_CODE,
                           idem_key="bump:%s:2:new_request:wa:in:600" % cid, expect_ver=2)
        self.assertCode(o, "rejected", "param_unknown", msg="new_request от кода (NEW_REQUEST_RULE=UNKNOWN)")
        self.assertNoWrites(before, "new_request от кода")
        o = S.bump_version(cid, reason="new_request", ref="wa:in:600", by=BY_APPROVER,
                           idem_key="bump:%s:2:new_request:wa:in:600" % cid, expect_ver=2)
        self.assertCode(o, "ok")
        self.assertEqual(e.db.exp(eid2)["state"], "superseded")
        self.assertEqual(e.db.task(tid2)["state"], "open", "new_request задачи не отменяет (S-M6)")
        st = dict((r["id"], r["state"]) for r in e.db.facts(cid))
        self.assertEqual((st[f2["version"]], st[f2["rental"]], st[f2["case"]]), ("stale", "valid", "valid"))

    def test_I3_I4_reconcile_period_changed_new_current_row(self):
        """I3/I4, §4.6, DESIGN §2.3: срок сменился при том же booking_id → period_changed + подъём; прежняя привязка
        current=0, новая current=1; повтор того же чтения — duplicate; старое чтение → ok(stale_read) без записей (I30)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        r0 = e.db.current_rental(cid)
        ext = row_ivan(date_end="2026-10-20 10:00")
        src = src_clients(ext, T0)
        key = "recon:%s:%s:%s" % (cid, CLIENTS_SRC, src["observed_at"])
        o = S.reconcile_rental(cid, rows=[ext], source=src, by=BY_CODE, idem_key=key)
        self.assertCode(o, "ok", msg="reconcile_rental period_changed")
        self.assertTrue(dget(o, "bumped"), "period_changed поднимает версию: %s" % short(o))
        self.assertEqual(e.db.case(cid)["ver"], 2)
        rows = e.db.q("SELECT * FROM rc_rental WHERE case_id=? ORDER BY id", (cid,))
        self.assertEqual([r["current"] for r in rows], [0, 1], "смена привязки = новая строка (§4.6)")
        self.assertEqual((rows[0]["id"], rows[0]["end_day"]), (r0["id"], "2026-10-12"))
        self.assertEqual(rows[1]["end_day"], "2026-10-20")
        self.assertEqual(rows[1]["observed_at"], src["observed_at"])
        self.assertTrue(e.db.events(cid, "period_changed"))
        self.assertEqual([(b["ver_before"], b["ver_after"]) for b in e.db.events(cid, "version_bumped")], [(1, 2)])
        snap = e.db.dump()
        self.assertCode(S.reconcile_rental(cid, rows=[ext], source=src, by=BY_CODE, idem_key=key), "duplicate")
        self.assertNoWrites(snap, "повтор того же чтения")
        old = src_clients(row_ivan(), T0 - 600)
        o = S.reconcile_rental(cid, rows=[row_ivan()], source=old, by=BY_CODE,
                               idem_key="recon:%s:%s:%s" % (cid, CLIENTS_SRC, old["observed_at"]))
        self.assertCode(o, "ok", msg="старое чтение")
        self.assertIs(dget(o, "stale_read"), True, "старое чтение → data.stale_read (I30): %s" % short(o))
        self.assertNoWrites(snap, "старое чтение не меняет привязку (I30)")

    def test_I30_K4C30_older_read_changes_nothing(self):
        """I30, M18: факт с observed_at не новее последнего valid того же fkey → ok(stale_read), изменений 0."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        fk = ["crm_status", "812"]
        o = S.record_fact(cid, kind="crm_status", value={"status": "В аренде"},
                          source=src_of(CLIENTS_SRC, "строка 812", "door", T0), scope="rental", by=BY_CODE,
                          idem_key=k_fact(cid, fk, T0), fkey=fk)
        self.assertCode(o, "ok")
        snap = e.db.dump()
        for obs in (T0, T0 - 900):
            o = S.record_fact(cid, kind="crm_status", value={"status": "Бронь"},
                              source=src_of(CLIENTS_SRC, "строка 812", "door", obs), scope="rental", by=BY_CODE,
                              idem_key=k_fact(cid, fk, obs) + ":old", fkey=fk)
            self.assertCode(o, "ok", msg="старое чтение факта")
            self.assertTrue(dget(o, "stale_read") is True or reason_code(o) == "stale_read",
                            "исход старого чтения не назван stale_read: %s" % short(o))
        self.assertNoWrites(snap, "старое чтение факта (I30)")
        o = S.record_fact(cid, kind="crm_status", value={"status": "Завершена"},
                          source=src_of(CLIENTS_SRC, "строка 812", "door", T0 + 60), scope="rental", by=BY_CODE,
                          idem_key=k_fact(cid, fk, T0 + 60), fkey=fk)
        self.assertCode(o, "ok")
        self.assertEqual(len(e.db.facts(cid, "crm_status")), 2, "новое чтение = новая строка (§4.6)")

    def test_I37_link_drift_hides_rental_money_documents(self):
        """I37/I9, DESIGN §2.3, К4-C33: смена имени при том же booking_id → unknown(link_confirmation) + одно
        confirm_link, link_state=drift, без подъёма; повторное чтение того же смещения второго confirm_link не родит;
        facts_for_agent прячет аренду/байк/деньги/документы; ответ места topic → reference_drift."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.asked_and_posted(S, cid, topic_msg=7401, deliv_msg=7402)
        for i, obs in enumerate((T0, T0 + 300)):
            drift = row_ivan(name="Пётр")
            src = src_clients(drift, obs)
            o = S.reconcile_rental(cid, rows=[drift], source=src, by=BY_CODE,
                                   idem_key="recon:%s:%s:%s" % (cid, CLIENTS_SRC, src["observed_at"]))
            self.assertCode(o, "unknown", "link_confirmation", msg="дрейф имени #%d" % i)
        case = e.db.case(cid)
        self.assertEqual((case["link_state"], case["ver"]), ("drift", 1), "дрейф без автоподъёма (I-12)")
        self.assertEqual(e.db.count("rc_expect", "case_id=? AND kind='confirm_link'", (cid,)), 1,
                         "confirm_link не плодится (ux_confirm_open)")
        fa = S.facts_for_agent(cid)
        kinds = set(f.get("kind") for f in fa.get("facts") or [])
        for k in ("case_rental", "case_bike", "case_money", "case_document"):
            self.assertNotIn(k, kinds, "при link_state≠ok отдан %s (I37)" % k)
        self.assertTrue(fa.get("reason"), "reason несёт вопрос confirm_link (§8.3)")
        self.assertNotIn("propose_client_notice", short(S.allowed_actions(cid), 100000))
        a = self.staff_reply(S, 7410, 7401)
        self.assertCode(a, "ok")
        self.assertEqual(verdict_of(a), "reference_drift")
        self.assertEqual(e.db.exp(eid)["state"], "waiting")


# ================================================================================================ ключи, CAS, транзакции
class TestIdempotencyCas(K4StoreBase):

    def test_I7_I32_K4C13_duplicate_and_payload_mismatch(self):
        """I7/I32, M7/M20: тот же ключ и содержимое → duplicate с event_seq первого раза и без записей (в т. ч. из
        второго Store, с иным by.name и в иное время); тот же ключ с иным содержимым → conflict(idem_payload_mismatch)."""
        e = self.env()
        S = e.store("splinter")
        W = e.store("wa")
        cid = self.new_case(S, row_ivan())
        fk = ["bike_event", BIKE, "handover", "ev-1"]
        args = dict(kind="bike_event", value={"type": "handover", "at": "2026-10-01 10:05"},
                    source=src_of("события байка", "ev-1", "door", T_OBS), scope="case", by=BY_CODE,
                    idem_key=k_fact(cid, fk, T_OBS), fkey=fk)
        o1 = S.record_fact(cid, **args)
        self.assertCode(o1, "ok")
        seq1 = e.db.one("SELECT seq FROM rc_event WHERE idem_key=?", (args["idem_key"],))["seq"]
        self.assertEqual(o1.get("event_seq"), seq1)
        snap = e.db.dump()
        e.clock.advance(30)
        for st, a in ((S, args), (W, args), (S, dict(args, by=dict(BY_CODE, name="другое-имя")))):
            o = st.record_fact(cid, **a)
            self.assertCode(o, "duplicate", msg="повтор ключа")
            self.assertEqual(o.get("event_seq"), seq1, "duplicate несёт event_seq первого раза (§1.3)")
        o = S.record_fact(cid, **dict(args, value={"type": "handover", "at": "2026-10-01 10:06"}))
        self.assertCode(o, "conflict", "idem_payload_mismatch")
        o = S.record_fact(cid, **dict(args, scope="version"))
        self.assertCode(o, "conflict", "idem_payload_mismatch")
        self.assertNoWrites(snap, "duplicate/conflict ключа")
        kb = "bump:%s:1:cancel:dup" % cid
        self.assertCode(S.bump_version(cid, reason="cancel", ref="dup", by=BY_APPROVER, idem_key=kb, expect_ver=1), "ok")
        snap = e.db.dump()
        o = S.bump_version(cid, reason="cancel", ref="dup", by=BY_APPROVER, idem_key=kb, expect_ver=1)
        self.assertCode(o, "duplicate", msg="повтор подъёма тем же ключом не конфликт версии")
        o = S.bump_version(cid, reason="cancel", ref="other", by=BY_APPROVER, idem_key=kb, expect_ver=1)
        self.assertCode(o, "conflict", "idem_payload_mismatch")
        self.assertNoWrites(snap, "повтор подъёма")
        self.assertEqual(e.db.case(cid)["ver"], 2)

    def test_I8_K4C14_two_stores_cas_one_ok_one_conflict(self):
        """I8, К4-C14, M8: два Store (роли wa/splinter) одновременно поднимают версию с одним expect_ver → ровно один
        ok и один conflict(expected_ver=1, current_ver=2); один version_bumped."""
        e = self.env()
        A = e.store("wa")
        B = e.store("splinter")
        cid = self.new_case(A, row_ivan())
        barrier = threading.Barrier(2)
        res = {}

        def run(name, st):
            try:
                barrier.wait(10)
                res[name] = st.bump_version(cid, reason="period_changed", ref="race:%s" % name, by=BY_APPROVER,
                                            idem_key="bump:%s:1:period_changed:race:%s" % (cid, name), expect_ver=1)
            except Exception as exc:
                res[name] = exc
        ths = [threading.Thread(target=run, args=(n, s)) for n, s in (("a", A), ("b", B))]
        for t in ths:
            t.start()
        for t in ths:
            t.join(60)
        for v in res.values():
            self.assertIsInstance(v, dict, "исключение в гонке: %r" % (v,))
        self.assertEqual(sorted(v.get("code") for v in res.values()), ["conflict", "ok"], short(res))
        lost = [v for v in res.values() if v.get("code") == "conflict"][0]
        self.assertEqual((lost.get("expected_ver"), lost.get("current_ver")), (1, 2))
        self.assertEqual(e.db.case(cid)["ver"], 2)
        self.assertEqual(len(e.db.events(cid, "version_bumped")), 1)

    def test_K4C14_one_store_two_threads_no_programming_error(self):
        """CONTRACT §2 «соединение одно на поток», DESIGN §5.6, M8: один объект Store из двух потоков — без
        ProgrammingError, все записи ok, ни одна не потеряна."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        errors, codes = [], []
        lock = threading.Lock()

        def worker(tag):
            try:
                for i in range(10):
                    fk = ["bike_event", BIKE, "move", "%s-%d" % (tag, i)]
                    obs = T_OBS + i
                    o = S.record_fact(cid, kind="bike_event", value={"tag": tag, "i": i},
                                      source=src_of("события байка", "%s-%d" % (tag, i), "door", obs), scope="case",
                                      by=BY_CODE, idem_key=k_fact(cid, fk, obs), fkey=fk)
                    S.case_view(cid)
                    with lock:
                        codes.append(o.get("code"))
            except Exception as exc:
                with lock:
                    errors.append(repr(exc))
        ths = [threading.Thread(target=worker, args=(t,)) for t in ("x", "y")]
        for t in ths:
            t.start()
        for t in ths:
            t.join(120)
        self.assertEqual(errors, [], "исключения из потоков (ProgrammingError — соединение не на поток)")
        self.assertEqual(codes, ["ok"] * 20)
        self.assertEqual(len(e.db.facts(cid, "bike_event")), 20)

    def test_I33_I43_store_busy_unknown_retry_safe(self):
        """I33/I43, К4-C31: замок базы дольше busy_timeout_s → unknown(store_busy, missing=[retry]), изменений 0, без
        перехода; повтор тем же idem_key после снятия замка → ok, затем duplicate."""
        e = self.env()
        S = e.store("splinter", busy_timeout_s=0.3)
        cid = self.new_case(S, row_ivan())
        before = e.db.dump()
        lock = _ORIG_CONNECT(e.path, timeout=0.1, isolation_level=None)
        try:
            lock.execute("BEGIN IMMEDIATE")
            t = time.monotonic()
            key = "bump:%s:1:period_changed:busy" % cid
            o = S.bump_version(cid, reason="period_changed", ref="busy", by=BY_APPROVER, idem_key=key, expect_ver=1)
            took = time.monotonic() - t
        finally:
            lock.execute("ROLLBACK")
            lock.close()
        self.assertCode(o, "unknown", "store_busy", msg="занятость базы")
        self.assertIn("retry", o.get("missing") or [])
        self.assertLess(took, 4.0, "busy_timeout_s Store не применён (ждал %.1f с)" % took)
        self.assertNoWrites(before, "store_busy")
        o = S.bump_version(cid, reason="period_changed", ref="busy", by=BY_APPROVER, idem_key=key, expect_ver=1)
        self.assertCode(o, "ok", msg="повтор после занятости")
        self.assertCode(S.bump_version(cid, reason="period_changed", ref="busy", by=BY_APPROVER, idem_key=key,
                                       expect_ver=1), "duplicate")

    def test_I6_failure_inside_transaction_rolls_back_store_usable(self):
        """I6, CONTRACT §1.2: сбой внутри транзакции (подложный триггер бросает на вставке обязательства посреди
        open_case) → ROLLBACK и rejected(internal); ни одной строки rc_*; Store пригоден дальше (транзакция не висит)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        S.blockers(cid)
        e.db.x("CREATE TRIGGER k4test_boom BEFORE INSERT ON rc_obligation WHEN NEW.role = 'deposit' "
               "BEGIN SELECT RAISE(ABORT, 'k4 test boom'); END")
        before = e.db.dump()
        o = self.open_case(S, row_anna())
        self.assertCode(o, "rejected", "internal", msg="сбой посреди open_case")
        self.assertNoWrites(before, "сбой внутри транзакции (I6)")
        o = S.add_contact(cid, channel="tg_username", value="ivan_tg", by=BY_APPROVER,
                          source=src_of("решение", "btn:after", "human", T0),
                          idem_key="contact:%s:tg_username:ivan_tg:btn:after" % cid)
        self.assertCode(o, "ok", msg="Store после сбоя (ROLLBACK сделан)")


class TestTransactionHook(K4StoreBase):

    def _hook_obligation(self, H, cid, n):
        key = "obl:%s:money:delivery:hook-%d" % (cid, n)

        def hook():
            return H.open_obligation(cid, kind="money", role="delivery", direction="from_client",
                                     source=src_of("решение одобряющего", "hook-%d" % n, "human", self.e.clock()),
                                     by=BY_APPROVER, idem_key=key, amount=500.0, currency="THB", outcome="valid")
        return key, hook

    def _oid_by_key(self, cid, key):
        row = self.e.db.one("SELECT id FROM rc_obligation WHERE idem_key=?", (key,))
        if row is None:
            row = self.e.db.one("SELECT id FROM rc_obligation WHERE case_id=? AND role='delivery' ORDER BY id DESC",
                                (cid,))
        self.assertIsNotNone(row, "обязательство крючка не записано")
        return row["id"]

    def test_I13_I31_K4C31_close_case_hook_inside_transaction(self):
        """I31/I13, К4-C31, P-M2, M5: второй Store вставляет обязательство в момент, когда close_case берёт замок записи
        (или пишет без него); блокеры, посчитанные ВНУТРИ BEGIN IMMEDIATE, обязаны его увидеть → rejected(blockers)
        с ним в списке; дело открыто."""
        e = self.env()
        H = e.store("human")
        cid = self.new_case(H, row_ivan())
        H.blockers(cid)                                  # соединение крючка создано до шпиона
        key, hook = self._hook_obligation(H, cid, 1)
        spy = ConnSpy()
        with spy.patched():
            S = e.store("splinter")
            pre = S.blockers(cid)
            self.assertIsInstance(pre, list)
            spy.arm(hook)
            out = S.close_case(cid, by=BY_APPROVER, idem_key="close:%s:1" % cid, expect_ver=1)
            spy.disarm()
        self.assertEqual(len(spy.fired), 1, "крючок не сработал: close_case не взял BEGIN IMMEDIATE и не писал "
                                             "(или открыл соединение мимо sqlite3.connect); след: %r" % spy.trace[-12:])
        why, hook_out = spy.fired[0]
        self.assertNotIsInstance(hook_out, Exception, "крючок упал (%s): %r" % (why, hook_out))
        self.assertCode(hook_out, "ok", msg="крючок open_obligation (%s)" % why)
        oid = self._oid_by_key(cid, key)
        self.assertCode(out, "rejected", "blockers", msg="close_case при вставленном обязательстве")
        bl = dget(out, "blockers") or []
        self.assertTrue(any(isinstance(b, dict) and str(b.get("id")) == str(oid) for b in bl),
                        "блокеры посчитаны вне транзакции записи — вставка крючка (%s) не видна: %s" % (why, short(bl)))
        self.assertEqual(e.db.case(cid)["state"], "open")
        self.assertEqual(e.db.events(cid, "case_closed"), [])

    def test_r2_V3_K4C31_close_case_cas_inside_transaction(self):
        """К4 круг 2, V3 / К4-C31, I8, I31 (judge_C31-C39 c31cas): крючок в момент BEGIN IMMEDIATE close_case поднимает
        версию дела вторым Store — CAS внутри транзакции даёт conflict, дело открыто, case_closed нет. Исходник верен;
        тест закрепляет предусловие CAS против выжившего мутанта V3."""
        e = self.env()
        A = e.store("splinter")
        cid = self.new_case(A, make_row(790, "Завершена", "PCX 160 4410", "Иван", "2026-09-01 10:00",
                                        "2026-09-15 10:00", "+66 81 234 5678", booking_id="", deposit_raw=""))
        for o in e.db.obligations(cid):
            if o["state"] in ("open", "unknown"):
                self.assertCode(self.settle(A, cid, o["id"], human={"waive": True, "detail": "r2: снято одобряющим"}),
                                "ok", msg="снятие %s/%s" % (o["kind"], o["role"]))
        self.assertEqual(A.blockers(cid), [], "фикстура: блокеры после снятия")
        B = e.store("human")
        B.blockers(cid)                                              # соединение крючка — до шпиона
        v0 = e.db.case(cid)["ver"]
        spy = ConnSpy()
        with spy.patched():
            S = e.store("splinter")
            S.blockers(cid)
            spy.arm(lambda: B.bump_version(cid, reason="new_request", ref="r2:c31", by=BY_APPROVER,
                                           idem_key="bump:%s:%s:r2c31" % (cid, v0), expect_ver=v0))
            out = S.close_case(cid, by=BY_APPROVER, idem_key="close:%s:%s:r2c31" % (cid, v0), expect_ver=v0)
            spy.disarm()
        self.assertEqual(len(spy.fired), 1, "крючок не сработал: close_case не взял BEGIN IMMEDIATE; след: %r"
                         % spy.trace[-12:])
        why, hook_out = spy.fired[0]
        self.assertNotIsInstance(hook_out, Exception, "крючок упал (%s): %r" % (why, hook_out))
        self.assertCode(hook_out, "ok", msg="крючок bump_version (%s)" % why)
        self.assertCode(out, "conflict", msg="close_case при версии, поднятой в окне транзакции")
        self.assertEqual(e.db.case(cid)["state"], "open")
        self.assertEqual(e.db.events(cid, "case_closed"), [])

    def test_I13_close_case_recomputes_blockers_not_caller_view(self):
        """I13/I31: чтение blockers() вызывающим — справка; обязательство, родившееся между чтением и close_case без
        подъёма версии, обязано попасть в блокеры той же expect_ver."""
        e = self.env()
        S = e.store("splinter")
        W = e.store("human")
        cid = self.new_case(S, row_ivan())
        pre = S.blockers(cid)
        key, hook = self._hook_obligation(W, cid, 2)
        self.assertCode(hook(), "ok")
        oid = self._oid_by_key(cid, key)
        self.assertFalse(any(isinstance(b, dict) and str(b.get("id")) == str(oid) for b in pre))
        before = e.db.dump()
        out = S.close_case(cid, by=BY_APPROVER, idem_key="close:%s:1" % cid, expect_ver=1)
        self.assertCode(out, "rejected", "blockers")
        self.assertTrue(any(isinstance(b, dict) and str(b.get("id")) == str(oid) for b in dget(out, "blockers") or []))
        self.assertNoWrites(before, "close_case отказ")


# ================================================================================================ ожидания §4.2
class TestExpectations(K4StoreBase):

    def test_section42_expectation_forbidden_transitions_bad_transition(self):
        """§4.2: переходы вне таблицы → rejected(bad_transition) без записей (mark_post_result/mark_escalated/
        claim_escalation/claim_execution/mark_written на planned; mark_written на in_flight вопроса); неверный
        expect_row_ver → conflict; адресаты и тема у поста (M3, M9); отмена — только одобряющим, терминал не меняется."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.ask(S, cid)
        rv = e.db.exp(eid)["row_ver"]
        t = e.clock()
        agents = [{"place": "agents", "chat": AGENTS_CHAT, "msg_id": "7190", "thread_id": None, "role": "escalation",
                   "at": t}]
        before = e.db.dump()
        bad = [
            ("mark_post_result", lambda: S.mark_post_result(eid, result={"posted": bike_posts(t, 7101, 7102),
                                                                        "qid": "q"}, by=BY_SPL,
                                                            idem_key="post:%s:%d" % (eid, rv), expect_row_ver=rv)),
            ("mark_escalated", lambda: S.mark_escalated(eid, result={"posted": agents}, by=BY_SPL,
                                                        idem_key="escd:%s:%d" % (eid, rv), expect_row_ver=rv)),
            ("claim_escalation", lambda: S.claim_escalation(eid, by=BY_APPROVER, idem_key="esc:%s:%d" % (eid, rv),
                                                            expect_row_ver=rv)),
            ("claim_execution", lambda: S.claim_execution(eid, by=BY_SPL, idem_key="exec:%s:%d" % (eid, rv),
                                                          expect_row_ver=rv, expect_ver=1)),
            ("mark_written", lambda: S.mark_written(eid, result={"ok": True, "row": None, "written_at": t}, by=BY_SPL,
                                                    idem_key="written:%s:%d" % (eid, rv), expect_row_ver=rv)),
        ]
        for name, call in bad:
            self.assertCode(call(), "rejected", "bad_transition", msg="%s на planned" % name)
        self.assertNoWrites(before, "переходы вне таблицы")
        self.claim(S, eid)
        rv = e.db.exp(eid)["row_ver"]
        before = e.db.dump()
        o = S.mark_written(eid, result={"ok": True, "row": None, "written_at": t}, by=BY_SPL,
                           idem_key="written:%s:%d" % (eid, rv), expect_row_ver=rv)
        self.assertCode(o, "rejected", "bad_transition", msg="mark_written на вопросе")
        o = self.post_result(S, eid, {"posted": bike_posts(t, 7101, 7102), "qid": "q"}, rv=rv - 1)
        self.assertCode(o, "conflict", msg="mark_post_result с устаревшим row_ver (I8)")
        self.assertNoWrites(before, "отказы на in_flight")
        o = self.post(S, eid, bike_posts(t, 7101, 7102))
        self.assertCode(o, "ok")
        posts = dict((p["msg_id"], p) for p in e.db.q("SELECT * FROM rc_post WHERE exp_id=?", (eid,)))
        self.assertEqual(set(posts), {"7101", "7102"})
        self.assertEqual((posts["7101"]["place"], posts["7101"]["thread_id"], posts["7101"]["topic_bike"]),
                         ("topic", THREAD, PLATE), "тема и байк темы поста (§4.7 п.5, К4-C9)")
        self.assertEqual(posts["7102"]["topic_bike"], PLATE)
        self.assertEqual(json.loads(posts["7101"]["addressee_ids"]), [STAFF_TOPIC], "адресаты у поста (M3)")
        self.assertEqual(json.loads(posts["7102"]["addressee_ids"]), [STAFF_DELIV])
        row = e.db.exp(eid)
        self.assertEqual((row["place"], row["due_basis"], row["business_due_at"]), ("topic", "none", None),
                         "главное место байк → topic; срока нет при UNKNOWN (I43)")
        before = e.db.dump()
        o = S.cancel_expectation(eid, reason="test", by=BY_CODE, idem_key="cancelexp:%s" % eid)
        self.assertCode(o, "rejected", "approver_unknown", msg="отмена ожидания кодом")
        self.assertNoWrites(before, "cancel_expectation кодом")
        self.assertCode(S.cancel_expectation(eid, reason="test", by=BY_APPROVER, idem_key="cancelexp:%s" % eid), "ok")
        self.assertEqual((e.db.exp(eid)["state"], e.db.exp(eid)["next_check"]), ("cancelled", "none"))
        before = e.db.dump()
        o = S.cancel_expectation(eid, reason="again", by=BY_APPROVER, idem_key="cancelexp:%s:again" % eid)
        self.assertCode(o, "rejected", msg="терминальное ожидание")
        rv = e.db.exp(eid)["row_ver"]
        o = S.claim_escalation(eid, by=BY_APPROVER, idem_key="esc:%s:%d" % (eid, rv), expect_row_ver=rv)
        self.assertCode(o, "rejected", msg="эскалация отменённого")
        self.assertNoWrites(before, "переходы терминального ожидания")
        self.assertEqual(S.claim_for_posting(by=BY_SPL), [], "отменённое не отдаётся на публикацию")

    def test_I15_flight_unknown_not_reclaimed_and_listed_for_human(self):
        """I15, M4: unknown → flight_unknown(reconcile); refused/deduped → flight_unknown(human_decision);
        claim_for_posting их не берёт (повтора нет); stuck() показывает человеку; posted из flight_unknown той же
        ролью → waiting."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eids = [self.ask(S, cid, q_ru=q) for q in ("Вопрос А про NMAX 6908?", "Вопрос Б про NMAX 6908?",
                                                    "Вопрос В про NMAX 6908?")]
        S.claim_for_posting(by=BY_SPL, kinds=("staff_question",), limit=10)
        for eid in eids:
            self.assertEqual(e.db.exp(eid)["state"], "in_flight")
        results = [{"unknown": "send вернул None после попытки"}, {"refused": "no_topic"}, {"deduped": "q-old"}]
        nexts = ["reconcile", "human_decision", "human_decision"]
        for eid, res, nc in zip(eids, results, nexts):
            self.assertCode(self.post_result(S, eid, res), "ok", msg="mark_post_result %s" % list(res)[0])
            row = e.db.exp(eid)
            self.assertEqual((row["state"], row["next_check"]), ("flight_unknown", nc), "%s → %r" % (res, row))
        before = e.db.dump()
        self.assertEqual(S.claim_for_posting(by=BY_SPL), [], "flight_unknown отдан на повторную публикацию (I15)")
        self.assertNoWrites(before, "claim_for_posting без кандидатов")
        stuck = short(S.stuck(), 100000)
        for eid in eids:
            self.assertIn(eid, stuck, "stuck() не показывает ожидание с неизвестным исходом")
        o = self.post(S, eids[0], bike_posts(e.clock(), 7201, 7202))
        self.assertCode(o, "ok", msg="posted из flight_unknown той же ролью")
        self.assertEqual(e.db.exp(eids[0])["state"], "waiting")

    def test_I14_I43_no_transition_by_age_escalation_only_by_approver(self):
        """I14/I43, К4-C38, M27: при WAIT_BEFORE_AGENTS=UNKNOWN срок не рождается; через 48 ч due_expectations пуст,
        состояние не меняется; claim_escalation кодом/агентом → rejected(param_unknown), одобряющим → escalating;
        mark_escalated(posted) → escalated; ответ адресата на пост вопроса после эскалации → accepted."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.asked_and_posted(S, cid, topic_msg=7301, deliv_msg=7302)
        e.clock.advance(48 * 3600)
        before = e.db.dump()
        self.assertEqual(S.due_expectations(now=e.clock()), [])
        self.assertEqual(S.due_expectations(), [])
        rv = e.db.exp(eid)["row_ver"]
        for by in (BY_CODE, BY_AGENT, BY_SPL):
            o = S.claim_escalation(eid, by=by, idem_key="esc:%s:%d" % (eid, rv), expect_row_ver=rv)
            self.assertCode(o, "rejected", "param_unknown", msg="эскалация по возрасту (%s)" % by["kind"])
        self.assertNoWrites(before, "48 ч без срока: ни перехода, ни записи (I14)")
        o = S.claim_escalation(eid, by=BY_APPROVER, idem_key="esc:%s:%d" % (eid, rv), expect_row_ver=rv)
        self.assertCode(o, "ok", msg="эскалация одобряющим")
        self.assertEqual((e.db.exp(eid)["state"], e.db.exp(eid)["next_check"]), ("escalating", "await_escalation"))
        rv = e.db.exp(eid)["row_ver"]
        o = S.mark_escalated(eid, result={"posted": [{"place": "agents", "chat": AGENTS_CHAT, "msg_id": "7350",
                                                      "thread_id": None, "role": "escalation", "at": e.clock()}]},
                             by=BY_SPL, idem_key="escd:%s:%d" % (eid, rv), expect_row_ver=rv)
        self.assertCode(o, "ok", msg="mark_escalated(posted)")
        self.assertEqual((e.db.exp(eid)["state"], e.db.exp(eid)["next_check"]), ("escalated", "await_agents"))
        self.assertEqual(e.db.one("SELECT role FROM rc_post WHERE chat=? AND msg_id='7350'", (AGENTS_CHAT,))["role"],
                         "escalation")
        a = self.staff_reply(S, 7310, 7301)
        self.assertCode(a, "ok")
        self.assertEqual(verdict_of(a), "accepted", "эскалация не обесценивает ответ на пост вопроса (§4.7 п.9)")
        self.assertEqual(e.db.exp(eid)["state"], "answered")

    def test_I41_agents_question_born_escalated_not_due(self):
        """I41, M26: вопрос места agents после поста сразу escalated(await_agents), в due_expectations не входит,
        вторая эскалация невозможна."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.ask(S, cid, staff_kind="цена", q_ru="Сколько стоит продление NMAX 6908 до 20.10?",
                       q_th="ต่ออายุ NMAX 6908 ถึง 20.10 ราคาเท่าไหร่?")
        self.assertEqual(e.db.exp(eid)["place"], "agents")
        self.claim(S, eid)
        o = self.post(S, eid, [{"place": "agents", "chat": AGENTS_CHAT, "msg_id": "7501", "thread_id": None,
                                "role": "agents", "at": e.clock()}])
        self.assertCode(o, "ok")
        self.assertEqual((e.db.exp(eid)["state"], e.db.exp(eid)["next_check"]), ("escalated", "await_agents"))
        e.clock.advance(48 * 3600)
        self.assertNotIn(eid, short(S.due_expectations(now=e.clock()), 100000))
        rv = e.db.exp(eid)["row_ver"]
        before = e.db.dump()
        o = S.claim_escalation(eid, by=BY_APPROVER, idem_key="esc:%s:%d" % (eid, rv), expect_row_ver=rv)
        self.assertCode(o, "rejected", msg="вторая эскалация вопроса «Агентов»")
        self.assertNoWrites(before, "эскалация escalated")

    def test_I9_I18_K4C9_answer_bound_by_post_addressee_place_not_nick(self):
        """I9/I18, M9, §4.7: ник без id и не адресат поста → reference_foreign_author; чужая тема →
        reference_foreign_place; не реплай/бот/пустой → rejected(not_reply); реплай не на пост → rejected(not_linked);
        справки не двигают ожидание; адресат Delivery на посту Delivery → accepted; повтор → duplicate; позже →
        reference_answered."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        tid = self.new_task(S, cid)
        eid = self.asked_and_posted(S, cid, task_id=tid, topic_msg=7601, deliv_msg=7602)
        refs = [
            (dict(msg_id=7620, reply_to=7601, author_id=None, username="staff9001"), "reference_foreign_author"),
            (dict(msg_id=7621, reply_to=7601, author_id=STAFF_DELIV), "reference_foreign_author"),
            (dict(msg_id=7622, reply_to=7601, thread_id="77"), "reference_foreign_place"),
        ]
        for kw, verdict in refs:
            a = self.staff_reply(S, **kw)
            self.assertCode(a, "ok", msg="справка %s" % verdict)
            self.assertEqual(verdict_of(a), verdict, short(a))
            self.assertIsNone(dget(a, "stage"), "справка дала ступень")
            row = e.db.one("SELECT verdict FROM rc_answer WHERE chat=? AND msg_id=?", (TOPIC_CHAT, str(kw["msg_id"])))
            self.assertEqual(row and row["verdict"], verdict, "строка rc_answer справки (§4.7)")
        self.assertEqual(e.db.exp(eid)["state"], "waiting", "справки не двигают ожидание (I9)")
        before = e.db.dump()
        self.assertCode(self.staff_reply(S, 7623, None, reply_to_is_bot=False), "rejected", "not_reply")
        self.assertCode(self.staff_reply(S, 7624, 7601, is_bot=True), "rejected", "not_reply")
        self.assertCode(self.staff_reply(S, 7625, 7601, text=""), "rejected", "not_reply")
        self.assertCode(self.staff_reply(S, 7626, 9999, reply_to_is_bot=False), "rejected", "not_linked")
        self.assertNoWrites(before, "отказы ответа")
        a = self.staff_reply(S, 7630, 7602, author_id=STAFF_DELIV, chat=DELIV_CHAT, thread_id=None)
        self.assertCode(a, "ok")
        self.assertEqual(verdict_of(a), "accepted", "адресат Delivery на посту Delivery: %s" % short(a))
        self.assertEqual(e.db.exp(eid)["state"], "answered")
        self.assertIn("answer_received", e.db.stages(tid), "ступень 2 в той же транзакции (§4.2)")
        self.assertTrue([f for f in e.db.facts(cid, "staff_answer") if f["state"] == "valid"], "факт staff_answer")
        snap = e.db.dump()
        self.assertCode(self.staff_reply(S, 7630, 7602, author_id=STAFF_DELIV, chat=DELIV_CHAT, thread_id=None),
                        "duplicate")
        self.assertNoWrites(snap, "повтор ответа")
        a = self.staff_reply(S, 7631, 7601)
        self.assertEqual(verdict_of(a), "reference_answered")

    def test_I16_K4C17_params_default_fail_closed(self):
        """I16, К4-C17 (CONTRACT §14 вариант Б), I9, I43, I45: с PARAMS_DEFAULT шаги агента → rejected(param_unknown);
        одобряющий по умолчанию (OWNER_IDS) проходит, но адресаты UNKNOWN → reference_author_unverified, ступени 2
        нет; due пуст; эскалация кодом → param_unknown; new_request кодом → param_unknown; write денег →
        unknown(param_unknown, MONEY_CLOSE_RULE); намерения клиенту нет."""
        P = PARAMS_DEFAULT
        self.assertIsNotNone(P)
        for name in ("AUTO_ASK", "WAIT_BEFORE_AGENTS", "ANSWER_TTL", "MONEY_CLOSE_RULE", "NEW_REQUEST_RULE",
                     "APPROVAL_REPLY_REQUIRED", "FINAL_NOTICE_REQUIRED", "BUSINESS_HOURS", "CONTINUATION_GAP_DAYS"):
            self.assertEqual(P.get(name), UNKNOWN, "%s по умолчанию UNKNOWN (§10)" % name)
        self.assertEqual(set(P.get("FEEDS_CONNECTED") or ()), set(), "FEEDS_CONNECTED по умолчанию ∅")
        ttl = P.get("APPROVAL_TTL_S") or {}
        self.assertEqual((ttl.get("activate"), ttl.get("close"), ttl.get("booking")), (1800, 1800, UNKNOWN))
        self.assertIn(OWNER, set(P.get("APPROVER_IDS") or ()))
        e = self.env(synth=False)
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        before = e.db.dump()
        o = S.open_task(cid, kind="readiness", ref="wa:in:501", by=BY_AGENT,
                        idem_key="task:%s:1:readiness:wa:in:501" % cid, expect_ver=1)
        self.assertCode(o, "rejected", "param_unknown", msg="open_task агентом (AUTO_ASK)")
        o = S.request_staff_question(cid, task_id=None, staff_kind="байк", q_ru=Q_RU, q_th=Q_TH, urgency="u",
                                     by=BY_AGENT, idem_key=k_ask(cid, 1, None, "байк", Q_RU), expect_ver=1)
        self.assertCode(o, "rejected", "param_unknown", msg="вопрос агентом (AUTO_ASK)")
        o = S.bump_version(cid, reason="new_request", ref="wa:in:9", by=BY_CODE,
                           idem_key="bump:%s:1:new_request:wa:in:9" % cid, expect_ver=1)
        self.assertCode(o, "rejected", "param_unknown", msg="new_request кодом")
        self.assertNoWrites(before, "шаги при UNKNOWN")
        tid = self.new_task(S, cid, by=BY_OWNER)
        eid = self.asked_and_posted(S, cid, task_id=tid, by=BY_OWNER, topic_msg=7701, deliv_msg=7702)
        for p in e.db.q("SELECT * FROM rc_post WHERE exp_id=?", (eid,)):
            self.assertEqual(str(p["addressee_ids"]).strip('"'), "UNKNOWN", "адресаты при UNKNOWN (§2 rc_post)")
        e.clock.advance(48 * 3600)
        self.assertEqual(S.due_expectations(now=e.clock()), [])
        rv = e.db.exp(eid)["row_ver"]
        self.assertCode(S.claim_escalation(eid, by=BY_CODE, idem_key="esc:%s:%d" % (eid, rv), expect_row_ver=rv),
                        "rejected", "param_unknown")
        a = self.staff_reply(S, 7710, 7701)
        self.assertCode(a, "ok")
        self.assertEqual(verdict_of(a), "reference_author_unverified")
        self.assertEqual(e.db.exp(eid)["state"], "waiting")
        self.assertNotIn("answer_received", e.db.stages(tid))
        self.assertNotIn("propose_client_notice", short(S.allowed_actions(cid), 100000))
        cash = {"kind": "cash", "src": "tx_find", "row": 2050, "msg_id": "m2050", "link": None,
                "at": "2026-10-05 12:00", "booking_id": BK_IVAN, "bike": BIKE, "amount": 3850, "currency": "THB",
                "role": "оплата аренды", "category": "rental"}
        o = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan()], source=src_of("касса", "строка 2050", "door", T_OBS),
                        by=BY_CODE, idem_key="cash:%s:2050:m2050:x" % cid)
        self.assertCode(o, "ok", msg="касса этого дела по booking_id")
        rent = e.db.obl(cid, "money", "rent")
        before = e.db.dump()
        o = self.settle(S, cid, rent["id"], by=BY_CODE, write={"cash_fact_id": dget(o, "fact_id"),
                                                               "second_document_id": None})
        self.assertCode(o, "unknown", "param_unknown", msg="write при MONEY_CLOSE_RULE=UNKNOWN (I45)")
        self.assertIn("MONEY_CLOSE_RULE", o.get("missing") or [])
        self.assertNoWrites(before, "write денег при UNKNOWN")

    def test_I40_post_of_superseded_recorded_and_orphan_linked(self):
        """I40, P-M7: пост ожидания, отозванного подъёмом во время публикации, записан в rc_post без смены состояния
        (post_recorded_late), ответ на него → reference_superseded; реплай на неизвестный пост бота при flight_unknown
        в чате → сирота (answer_orphaned без дела), при mark_post_result(posted) связывается с вердиктом; реплай не
        боту → rejected(not_linked)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        eid = self.ask(S, cid)
        self.claim(S, eid)
        o = S.bump_version(cid, reason="period_changed", ref="test:late", by=BY_APPROVER,
                           idem_key="bump:%s:1:period_changed:test:late" % cid, expect_ver=1)
        self.assertCode(o, "ok")
        self.assertEqual(e.db.exp(eid)["state"], "superseded")
        o = self.post(S, eid, bike_posts(e.clock(), 7801, 7802))
        self.assertCode(o, "ok", msg="posted для superseded")
        self.assertEqual(e.db.exp(eid)["state"], "superseded", "состояние не меняется (I40)")
        self.assertEqual(e.db.count("rc_post", "exp_id=?", (eid,)), 2)
        self.assertTrue(e.db.q("SELECT * FROM rc_event WHERE type='post_recorded_late' AND exp_id=?", (eid,)))
        a = self.staff_reply(S, 7810, 7801)
        self.assertEqual(verdict_of(a), "reference_superseded")

        ea = S.request_approval(cid, task_id=None, action="activate", chat=INBOX_CHAT, card={"ref": "card-orph"},
                                by=BY_SPL, idem_key="appr:%s:2:activate:%s:card-orph" % (cid, INBOX_CHAT),
                                expect_ver=2)
        self.assertCode(ea, "ok")
        ea = dget(ea, "exp_id")
        self.claim(S, ea, kinds=("approval",))
        self.assertCode(self.post_result(S, ea, {"unknown": "таймаут отправки карточки"}), "ok")
        self.assertEqual(e.db.exp(ea)["state"], "flight_unknown")
        before = e.db.dump()
        self.assertCode(self.appr_reply(S, 5602, 5601, reply_to_is_bot=False), "rejected", "not_linked")
        self.assertNoWrites(before, "реплай не боту на неизвестный пост")
        o = self.appr_reply(S, 5603, 5601)
        self.assertCode(o, "ok", msg="сирота")
        self.assertEqual(verdict_of(o), "orphan")
        orph = e.db.one("SELECT * FROM rc_reply_unlinked WHERE chat=? AND msg_id='5603'", (INBOX_CHAT,))
        self.assertEqual(orph and orph["state"], "orphan")
        self.assertTrue(e.db.q("SELECT * FROM rc_event WHERE type='answer_orphaned' AND case_id IS NULL"),
                        "answer_orphaned без дела пишется (CHECK rc_event, §8.1)")
        o = self.post(S, ea, [{"place": "intake", "chat": INBOX_CHAT, "msg_id": "5601", "thread_id": None,
                               "role": "card", "at": e.clock()}], qid=None)
        self.assertCode(o, "ok", msg="пост найден")
        orph = e.db.one("SELECT * FROM rc_reply_unlinked WHERE chat=? AND msg_id='5603'", (INBOX_CHAT,))
        self.assertEqual(orph["state"], "linked")
        self.assertIsNotNone(orph["answer_id"])
        ans = e.db.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id='5603'", (INBOX_CHAT,))
        self.assertIsNotNone(ans, "связанная сирота получила вердикт в той же транзакции (I40)")

    def test_I28_I39_K4C28_approval_execute_ttl_no_reply_restart(self):
        """I28/I39, К4-C28, M23/M30: «да» реплаем одобряющего → accepted, execute=True, readback(planned) с parent_exp;
        повтор → duplicate (execute False, decision None); второе «да» → reference_answered (колонка decision=yes);
        claim_execution → обрыв → recover → pending_checks отдаёт readback, повторного claim нет (I15);
        активация через 31 мин → reference_late; «да» без реплая → reference_no_reply (execute False, ожидание то же);
        «когда?» → reference_unclear; карточка брони через сутки в том же запуске → accepted, после рестарта →
        reference_restart."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        ea = self.approval(S, cid, "activate", "card-act-1", 5001)
        e.clock.advance(60)
        o = self.appr_reply(S, 5002, 5001)
        self.assertCode(o, "ok")
        self.assertEqual((verdict_of(o), dget(o, "decision"), dget(o, "execute")), ("accepted", "yes", True))
        self.assertAlmostEqual(float(dget(o, "card_age_s")), 60.0, delta=1.0)
        self.assertEqual(e.db.exp(ea)["state"], "answered")
        rb = dget(o, "readback_exp_id")
        rbrow = e.db.exp(rb)
        self.assertEqual((rbrow["kind"], rbrow["state"], rbrow["parent_exp"]), ("readback", "planned", ea))
        ans = e.db.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id='5002'", (INBOX_CHAT,))
        self.assertEqual((ans["verdict"], ans["decision"], ans["execute"]), ("accepted", "yes", 1))
        snap = e.db.dump()
        o = self.appr_reply(S, 5002, 5001)
        self.assertCode(o, "duplicate")
        self.assertFalse(dget(o, "execute"))
        self.assertIsNone(dget(o, "decision"))
        self.assertNoWrites(snap, "повтор «да»")
        o = self.appr_reply(S, 5003, 5001)
        self.assertEqual((verdict_of(o), dget(o, "execute"), dget(o, "decision")), ("reference_answered", False, None))
        ans = e.db.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id='5003'", (INBOX_CHAT,))
        self.assertEqual((ans["decision"], ans["execute"]), ("yes", 0), "колонка decision пишется всегда (§4.7)")

        rv = e.db.exp(rb)["row_ver"]
        self.assertCode(S.claim_execution(rb, by=BY_SPL, idem_key="exec:%s:%d" % (rb, rv), expect_row_ver=rv,
                                          expect_ver=1), "ok")
        self.assertEqual(e.db.exp(rb)["state"], "in_flight")
        S2 = e.store("splinter")                                   # рестарт Splinter
        r = S2.recover(by=BY_SPL)
        self.assertCode(r, "ok")
        self.assertEqual(dget(r, "expect"), 1)
        row = e.db.exp(rb)
        self.assertEqual((row["state"], row["next_check"]), ("flight_unknown", "readback"))
        pcs = S2.pending_checks(role="splinter")
        self.assertTrue(any(isinstance(p, dict) and p.get("what") == "readback" and p.get("exp_id") == rb
                            for p in pcs), "pending_checks не отдаёт readback после recover: %s" % short(pcs))
        rv = e.db.exp(rb)["row_ver"]
        before = e.db.dump()
        self.assertNotOk(S2.claim_execution(rb, by=BY_SPL, idem_key="exec:%s:%d" % (rb, rv), expect_row_ver=rv,
                                            expect_ver=1), "повторный захват исполнения после обрыва (I15)")
        self.assertNoWrites(before, "повторный claim_execution")

        ec = self.approval(S2, cid, "close", "card-close-1", 5101)
        e.clock.advance(31 * 60)
        o = self.appr_reply(S2, 5102, 5101)
        self.assertEqual((verdict_of(o), dget(o, "execute")), ("reference_late", False), short(o))
        self.assertEqual(e.db.exp(ec)["state"], "waiting")
        o = self.appr_reply(S2, 5103, None, reply_to_is_bot=False)
        self.assertCode(o, "ok", msg="«да» без реплая")
        self.assertEqual((verdict_of(o), dget(o, "execute"), dget(o, "decision")), ("reference_no_reply", False, "yes"))
        ans = e.db.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id='5103'", (INBOX_CHAT,))
        self.assertEqual((ans["exp_id"], ans["reply_to"], ans["post_role"], ans["execute"]), (ec, "", "card", 0))
        self.assertEqual(e.db.exp(ec)["state"], "waiting")
        ea2 = self.approval(S2, cid, "activate", "card-act-2", 5201)
        o = self.appr_reply(S2, 5202, 5201, text="когда?")
        self.assertEqual((verdict_of(o), dget(o, "execute")), ("reference_unclear", False))
        self.assertEqual(e.db.exp(ea2)["state"], "waiting")

        eb = self.approval(S2, None, "booking", "card-bk-1", 5301)
        self.assertIsNone(e.db.exp(eb)["case_id"])
        e.clock.advance(86400)
        o = self.appr_reply(S2, 5302, 5301)
        self.assertEqual((verdict_of(o), dget(o, "execute")), ("accepted", True), "карточка брони в том же запуске")
        self.assertGreater(float(dget(o, "card_age_s")), 1800.0, "1800 к карточке брони не применён (M30)")
        eb2 = self.approval(S2, None, "booking", "card-bk-2", 5401)
        S3 = e.store("splinter")                                   # ещё рестарт
        e.clock.advance(120)
        o = self.appr_reply(S3, 5402, 5401)
        self.assertEqual((verdict_of(o), dget(o, "execute")), ("reference_restart", False), short(o))
        self.assertEqual(e.db.exp(eb2)["state"], "waiting")


# ================================================================================================ рестарт и роли
class TestRecoverRestart(K4StoreBase):

    def test_I29_K4C29_recover_only_own_role_old_boot(self):
        """I29, К4-C29, M17: recover трогает только захваты своей роли с прежним boot_id; захват другой роли и
        собственного запуска не трогается; главное событие recovered без дела; повтор → duplicate; захват другой роли
        после рестарта доводится до waiting."""
        e = self.env()
        S1 = e.store("splinter")
        W1 = e.store("wa")
        cid = self.new_case(S1, row_ivan())
        e1 = self.ask(S1, cid, q_ru="Вопрос 1 про NMAX 6908?")
        e2 = self.ask(S1, cid, q_ru="Вопрос 2 про NMAX 6908?")
        S1.claim_for_posting(by=BY_SPL, kinds=("staff_question",), limit=1)
        W1.claim_for_posting(by=BY_WA, kinds=("staff_question",), limit=1)
        rows = dict((x, e.db.exp(x)) for x in (e1, e2))
        self.assertEqual(sorted(r["state"] for r in rows.values()), ["in_flight", "in_flight"])
        by_role = dict((r["claimed_by"], r["exp_id"]) for r in rows.values())
        self.assertEqual(set(by_role), {"splinter", "wa"})
        self.assertEqual(rows[by_role["splinter"]]["claim_boot"], S1.boot_id)
        self.assertEqual(rows[by_role["wa"]]["claim_boot"], W1.boot_id)
        r = W1.recover(by=BY_WA)
        self.assertCode(r, "ok")
        self.assertEqual(dget(r, "expect"), 0, "recover своего же запуска ничего не трогает")
        self.assertEqual([e.db.exp(x)["state"] for x in (e1, e2)], ["in_flight", "in_flight"])
        S2 = e.store("splinter")
        r = S2.recover(by=BY_SPL)
        self.assertCode(r, "ok")
        self.assertEqual((dget(r, "expect"), dget(r, "escalation"), dget(r, "notice")), (1, 0, 0))
        self.assertEqual(e.db.exp(by_role["splinter"])["state"], "flight_unknown")
        self.assertEqual(e.db.exp(by_role["wa"])["state"], "in_flight", "захват другой роли тронут (M17)")
        key = "recover:splinter:%s" % S2.boot_id
        main = e.db.one("SELECT * FROM rc_event WHERE idem_key=?", (key,))
        self.assertIsNotNone(main, "главное событие recovered с ключом recover:<role>:<boot_id>")
        self.assertEqual((main["type"], main["case_id"], main["exp_id"]), ("recovered", None, None))
        self.assertTrue(e.db.q("SELECT * FROM rc_event WHERE idem_key LIKE ? AND exp_id=?",
                               (key + "#%", by_role["splinter"])), "подсобытие переведённой строки")
        snap = e.db.dump()
        self.assertCode(S2.recover(by=BY_SPL), "duplicate")
        self.assertNoWrites(snap, "повтор recover")
        self.assertEqual(S2.claim_for_posting(by=BY_SPL), [], "ни flight_unknown, ни чужой in_flight не берутся")
        o = self.post(W1, by_role["wa"], bike_posts(e.clock(), 7901, 7902), by=BY_WA)
        self.assertCode(o, "ok", msg="захват другой роли после рестарта Splinter")
        self.assertEqual(e.db.exp(by_role["wa"])["state"], "waiting")

    def test_restart_between_steps_new_store_no_loss_no_repeat(self):
        """DESIGN §5.4, К4-C12, §13 «рестарт»: новый Store на том же файле видит всё; после posted повтора поста нет и
        ответ принимается; обрыв между claim и posted → recover → flight_unknown, повтора нет, найденный пост
        доводит до waiting той же ролью."""
        e = self.env()
        S1 = e.store("splinter")
        cid = self.new_case(S1, row_ivan())
        eid = self.asked_and_posted(S1, cid, topic_msg=8001, deliv_msg=8002)
        S1.close()
        S2 = e.store("splinter")
        r = S2.recover(by=BY_SPL)
        self.assertCode(r, "ok")
        self.assertEqual(dget(r, "expect"), 0)
        self.assertEqual(e.db.exp(eid)["state"], "waiting")
        self.assertEqual(S2.claim_for_posting(by=BY_SPL), [])
        self.assertEqual(e.db.count("rc_post", "exp_id=?", (eid,)), 2, "постов не прибавилось")
        a = self.staff_reply(S2, 8010, 8001)
        self.assertEqual(verdict_of(a), "accepted")
        self.assertEqual(e.db.exp(eid)["state"], "answered")
        e2 = self.ask(S2, cid, q_ru="Есть ли второй шлем к NMAX 6908?")
        self.claim(S2, e2)
        S2.close()
        S3 = e.store("splinter")
        r = S3.recover(by=BY_SPL)
        self.assertEqual(dget(r, "expect"), 1)
        self.assertEqual((e.db.exp(e2)["state"], e.db.exp(e2)["next_check"]), ("flight_unknown", "reconcile"))
        self.assertEqual(S3.claim_for_posting(by=BY_SPL), [], "после обрыва пост не повторяется (I15)")
        o = self.post(S3, e2, bike_posts(e.clock(), 8101, 8102))
        self.assertCode(o, "ok")
        self.assertEqual(e.db.exp(e2)["state"], "waiting")
        self.assertEqual(e.db.case(cid)["ver"], 1)


# ================================================================================================ ступени, уведомление
class TestStagesNotices(K4StoreBase):

    def test_I10_I44_forbidden_evidence_for_stages_4_and_5(self):
        """I10/I44, M6/M29, §3.6: ступени 4 и 5 не принимают staff_answer, approval_yes, agent_text, bike_state;
        ступень 4 handover — и crm_status_read; отказы evidence_forbidden без записей; bike/* не закрыты."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_boris())
        tid = self.new_task(S, cid, kind="handover", ref="spl:card:1")
        fk = ["bike_state", BIKE, "2026-10-01 10:05"]
        o = S.record_fact(cid, kind="bike_state", value={"status": "в аренде", "location": "", "updated":
                                                         "2026-10-01 10:05"},
                          source=src_of("лист «состояние_байка» (state_get)", BIKE, "door", T0 - 3600), scope="case",
                          by=BY_SPL, idem_key=k_fact(cid, fk, T0 - 3600), fkey=fk)
        self.assertCode(o, "ok", msg="справка bike_state пишется фактом (I44)")
        before = e.db.dump()
        for stage in ("physically_done", "result_recorded"):
            for kind in ("staff_answer", "approval_yes", "agent_text", "bike_state"):
                o = self.stage(S, cid, tid, stage, {"kind": kind, "ref": "ev:%s:%s" % (stage, kind)})
                self.assertCode(o, "rejected", "evidence_forbidden", msg="%s свидетельством %s" % (stage, kind))
        o = self.stage(S, cid, tid, "physically_done", {"kind": "crm_status_read", "ref": "crm:845",
                                                        "booking_id": BK_BORIS, "status": "В аренде", "row": 845,
                                                        "read_at": e.clock()})
        self.assertCode(o, "rejected", "evidence_forbidden", msg="crm_status_read на ступени 4 выдачи")
        self.assertNoWrites(before, "запрещённые свидетельства")
        for role in ("handover", "return"):
            self.assertEqual(e.db.obl(cid, "bike", role)["state"], "open")

    def test_I11_stage5_only_after_stage4(self):
        """I11, M16, §4.2: on_readback(landed) без ступени 4 → ожидание answered, факт readback, data.stage=None,
        reason=order, ступени 5 нет, задача open; record_stage(result_recorded) без 4 → отказ."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        tid = self.new_task(S, cid)
        rb, o = self.readback_result(S, cid, tid)
        self.assertCode(o, "ok", msg="on_readback(landed) без ступени 4")
        self.assertIsNone(dget(o, "stage"), "ступень 5 без 4 (M16): %s" % short(o))
        self.assertIn("order", str(o.get("reason") or ""))
        self.assertEqual(e.db.exp(rb)["state"], "answered")
        self.assertNotIn("result_recorded", e.db.stages(tid))
        self.assertEqual(e.db.task(tid)["state"], "open")
        self.assertTrue(e.db.facts(cid, "readback"), "факт readback записан")
        before = e.db.dump()
        o = self.stage(S, cid, tid, "result_recorded", {"kind": "readback", "ref": "sink:fake:%s" % tid,
                                                        "source": "sink:fake", "written_at": T0, "read_at": T0 + 1,
                                                        "outcome": "landed", "expected": {}, "got": {}})
        self.assertCode(o, "rejected", msg="record_stage(result_recorded) без ступени 4")
        self.assertNoWrites(before, "ступень 5 без 4")

    def test_I27_one_evidence_ref_one_stage(self):
        """I27, M24: ступень 4 без 3 — с флагом without_acceptance; тот же ref свидетельства для другой задачи →
        отказ без записей; human_mark не одобряющего → rejected(approver_unknown)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        t1 = self.new_task(S, cid, kind="readiness", ref="r1")
        t2 = self.new_task(S, cid, kind="delivery", ref="r2")
        o = self.stage(S, cid, t1, "physically_done", human_mark("btn:done:1"))
        self.assertCode(o, "ok", msg="ступень 4 human_mark")
        st = e.db.stages(t1)["physically_done"]
        self.assertIn("without_acceptance", st["flags"], "4 без 3 — флаг without_acceptance (§6 stage_allowed)")
        before = e.db.dump()
        o = self.stage(S, cid, t2, "physically_done", human_mark("btn:done:1"))
        self.assertCode(o, "rejected", msg="тот же ref для другой задачи")
        self.assertIn(reason_code(o), ("evidence_foreign", "evidence_forbidden"))
        o = self.stage(S, cid, t2, "physically_done", human_mark("btn:done:2", author_id=STRANGER), by=BY_STRANGER)
        self.assertCode(o, "rejected", "approver_unknown", msg="human_mark не одобряющего")
        o = self.stage(S, cid, t2, "physically_done", human_mark("btn:done:3", author_id=APPROVER), by=BY_CODE)
        self.assertCode(o, "rejected", msg="human_mark не от человека")
        self.assertNoWrites(before, "отказы ступени")

    def test_section45_cancelled_task_physical_event_fact(self):
        """§4.5, P-M7 в, I40: ступень 4 отменённой задачи не пишется — факт physical_event (scope=case) + внимание,
        исход ok с data.stage=None и data.fact_id; ступень 1–3 отменённой задачи → отказ."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        tid = self.new_task(S, cid)
        o = S.cancel_task(cid, task_id=tid, reason="client_cancel", by=BY_APPROVER, idem_key="tcancel:%s" % tid)
        self.assertCode(o, "ok")
        self.assertEqual(e.db.task(tid)["state"], "cancelled")
        o = self.stage(S, cid, tid, "physically_done", human_mark("btn:done:9"))
        self.assertCode(o, "ok", msg="физическое событие отменённой задачи")
        self.assertIsNone(dget(o, "stage"))
        f = e.db.one("SELECT * FROM rc_fact WHERE id=?", (dget(o, "fact_id"),))
        self.assertEqual((f and f["kind"], f and f["scope"]), ("physical_event", "case"))
        self.assertEqual(e.db.stages(tid), {}, "ступень отменённой задачи записана")
        self.assertEqual(e.db.case(cid)["attention"], 1, "физическое событие отменённой задачи → внимание (§4.1)")
        before = e.db.dump()
        self.assertCode(self.stage(S, cid, tid, "task_accepted", human_mark("btn:acc:9")), "rejected")
        self.assertNoWrites(before, "ступень 3 отменённой задачи")

    def test_I24_K4C21_attention_wa_pause_tg_any_kind_release_by_approver(self):
        """I24, К4-C21, M13/M28: эхо WA без паузы — событие без внимания; TG текстом — внимание; второе — без смены
        номера; снять может только одобряющий (кодом/агентом — отказ без записей); пауза WA снимается только её
        номером (иначе pause_mismatch); входящее клиента — событие client_inbound без дела (§8.1)."""
        e = self.env()
        S = e.store("wa")
        cid = self.new_case(S, row_ivan())
        contact = {"channel": "wa", "value": IVAN_WA}
        o = S.on_human_intervention(contact=contact, kind="photo", channel="wa", ref="wa:echo:1", at=e.clock(),
                                    wa_pause_no=None, by=BY_WA, idem_key="human:wa:wa:echo:1")
        self.assertCode(o, "ok")
        self.assertIn(cid, dget(o, "cases") or [])
        self.assertEqual(e.db.case(cid)["attention"], 0, "эхо фото WA без паузы внимания не ставит")
        o = S.on_human_intervention(contact=contact, kind="text", channel="tg", ref="tg:msg:1", at=e.clock(),
                                    wa_pause_no=None, by=BY_WA, idem_key="human:tg:tg:msg:1")
        self.assertCode(o, "ok")
        c = e.db.case(cid)
        self.assertEqual((c["attention"], c["pause_no"]), (1, 1), "текст в TG → внимание (M28)")
        self.assertTrue(e.db.q("SELECT * FROM rc_event WHERE type='human_intervention' AND case_id IS NULL"),
                        "многоделовое human_intervention пишется без дела (CHECK rc_event)")
        o = S.on_human_intervention(contact=contact, kind="sticker", channel="tg", ref="tg:msg:2", at=e.clock(),
                                    wa_pause_no=None, by=BY_WA, idem_key="human:tg:tg:msg:2")
        self.assertCode(o, "ok")
        self.assertEqual((e.db.case(cid)["attention"], e.db.case(cid)["pause_no"]), (1, 1))
        before = e.db.dump()
        for by in (BY_CODE, BY_AGENT, BY_STRANGER):
            self.assertCode(S.clear_attention(cid, by=by, idem_key="clear:%s:1" % cid), "rejected",
                            msg="снятие внимания %s" % by["kind"])
        self.assertNoWrites(before, "снятие внимания не одобряющим")
        self.assertCode(S.clear_attention(cid, by=BY_APPROVER, idem_key="clear:%s:1" % cid), "ok")
        self.assertEqual(e.db.case(cid)["attention"], 0)
        o = S.on_human_intervention(contact=contact, kind="voice", channel="wa", ref="wa:echo:2", at=e.clock(),
                                    wa_pause_no=7, by=BY_WA, idem_key="human:wa:wa:echo:2")
        self.assertCode(o, "ok")
        c = e.db.case(cid)
        self.assertEqual((c["attention"], c["wa_pause_no"]), (1, 7))
        pn = c["pause_no"]
        before = e.db.dump()
        o = S.clear_attention(cid, by=BY_APPROVER, idem_key="clear:%s:%d" % (cid, pn), wa_pause_no=6)
        self.assertCode(o, "rejected", "pause_mismatch")
        self.assertNoWrites(before, "чужой номер паузы")
        self.assertCode(S.clear_attention(cid, by=BY_APPROVER, idem_key="clear:%s:%d" % (cid, pn), wa_pause_no=7),
                        "ok")
        self.assertEqual(e.db.case(cid)["attention"], 0)
        o = S.on_client_inbound(contact=contact, ref="wa:in:9", at=e.clock(), by=BY_WA, idem_key="in:wa:wa:in:9")
        self.assertCode(o, "ok")
        self.assertTrue(e.db.q("SELECT * FROM rc_event WHERE type='client_inbound' AND case_id IS NULL"))
        self.assertEqual(e.db.case(cid)["ver"], 1, "входящее версию не поднимает")

    def test_I12_I42_I24_K4C10_ladder_stages_1_to_6_notice_restart(self):
        """I12/I42/I24/I15, К4-C10/C12, M24, §4.3/§4.5: полная лестница 1–6 на деле Бориса (CONTRACT §14 Д5–Д14):
        вопрос → пост (1) → ответ адресата (2) → human_mark (3; ссылка ответа → evidence_forbidden) → human_mark (4) →
        readback landed (5, задача done); record_stage(client_notified) → bad_transition; внимание блокирует намерение
        до снятия одобряющим; claim_notice второй раз → conflict; рестарт WA → recover → draft_unknown, pending_checks,
        повторного захвата нет; record_delivery(sent) → отказ; delivered → ступень 6, top_stage 6, задача done."""
        e = self.env()
        S = e.store("splinter")
        W = e.store("wa")
        cid = self.new_case(S, row_boris())
        tid = self.new_task(S, cid)
        eid = self.asked_and_posted(S, cid, task_id=tid, topic_msg=7001, deliv_msg=7002)
        self.assertIn("question_sent", e.db.stages(tid), "ступень 1 в транзакции posted (§4.2)")
        e.clock.advance(120)
        a = self.staff_reply(S, 7010, 7001)
        self.assertCode(a, "ok")
        self.assertEqual((verdict_of(a), dget(a, "stage")), ("accepted", "answer_received"))
        self.assertEqual(e.db.exp(eid)["state"], "answered")
        before = e.db.dump()
        o = self.stage(S, cid, tid, "task_accepted", human_mark("%s:7010" % TOPIC_CHAT))
        self.assertCode(o, "rejected", "evidence_forbidden", msg="human_mark со ссылкой ответа (M24)")
        self.assertNoWrites(before, "M24")
        self.assertCode(self.stage(S, cid, tid, "task_accepted", human_mark("btn:accept:1")), "ok")
        self.assertCode(self.stage(S, cid, tid, "physically_done", human_mark("btn:done:1")), "ok")
        rb, o = self.readback_result(S, cid, tid)
        self.assertCode(o, "ok", msg="on_readback(landed)")
        self.assertEqual(dget(o, "stage"), "result_recorded")
        self.assertEqual(e.db.exp(rb)["state"], "answered")
        t = e.db.task(tid)
        self.assertEqual((t["state"], t["top_stage"]), ("done", 5))
        before = e.db.dump()
        o = S.record_stage(cid, task_id=tid, stage="client_notified",
                           evidence={"kind": "wa_delivery", "ref": WAMID, "notice_id": "RN-x", "wamid": WAMID,
                                     "status": "delivered", "at": e.clock()},
                           by=BY_WA, idem_key="stage:%s:client_notified" % tid)
        self.assertCode(o, "rejected", "bad_transition", msg="ступень 6 через record_stage")
        self.assertNoWrites(before, "record_stage(client_notified)")
        self.assertIn("propose_client_notice", short(S.allowed_actions(cid), 100000), "Д13: намерение разрешено")

        o = W.on_human_intervention(contact={"channel": "wa", "value": BORIS_WA}, kind="text", channel="tg",
                                    ref="tg:msg:1", at=e.clock(), wa_pause_no=None, by=BY_WA,
                                    idem_key="human:tg:tg:msg:1")
        self.assertCode(o, "ok")
        self.assertEqual(e.db.case(cid)["attention"], 1)
        self.assertNotIn("propose_client_notice", short(S.allowed_actions(cid), 100000))
        fids = self.task_fact_ids(cid)
        nkey = "notice:%s:1:%s:readiness_confirmed" % (cid, tid)
        before = e.db.dump()
        o = S.propose_client_notice(cid, task_id=tid, intent="readiness_confirmed", fact_ids=fids, by=BY_SPL,
                                    idem_key=nkey, expect_ver=1)
        self.assertCode(o, "rejected", "attention", msg="намерение при внимании (I24)")
        pn = e.db.case(cid)["pause_no"]
        self.assertCode(S.clear_attention(cid, by=BY_CODE, idem_key="clear:%s:%d" % (cid, pn)), "rejected")
        self.assertNoWrites(before, "намерение/снятие при внимании")
        self.assertCode(S.clear_attention(cid, by=BY_APPROVER, idem_key="clear:%s:%d" % (cid, pn)), "ok")
        o = S.propose_client_notice(cid, task_id=tid, intent="readiness_confirmed", fact_ids=fids, by=BY_SPL,
                                    idem_key=nkey, expect_ver=1)
        self.assertCode(o, "ok", msg="propose_client_notice (Д14)")
        nid = dget(o, "notice_id")
        self.assertTrue(nid, "propose_client_notice без notice_id: %s" % short(o))
        self.assertEqual(e.db.notice(nid)["state"], "intent")

        rv = e.db.notice(nid)["row_ver"]
        self.assertCode(W.claim_notice(nid, by=BY_WA, idem_key="nclaim:%s:%d" % (nid, rv), expect_row_ver=rv), "ok")
        n = e.db.notice(nid)
        self.assertEqual((n["state"], n["claimed_by"], n["claim_boot"]), ("drafting", "wa", W.boot_id))
        before = e.db.dump()
        o = W.claim_notice(nid, by=BY_WA, idem_key="nclaim:%s:%d:second" % (nid, rv), expect_row_ver=rv)
        self.assertCode(o, "conflict", msg="второй захват намерения (I42)")
        self.assertNoWrites(before, "второй claim_notice")
        W2 = e.store("wa")                                          # рестарт WA посреди черновика
        r = W2.recover(by=BY_WA)
        self.assertCode(r, "ok")
        self.assertEqual(dget(r, "notice"), 1)
        self.assertEqual(e.db.notice(nid)["state"], "draft_unknown")
        pcs = W2.pending_checks(role="wa")
        self.assertTrue(any(isinstance(p, dict) and p.get("what") == "notice" and p.get("notice_id") == nid
                            for p in pcs), "pending_checks не отдаёт draft_unknown: %s" % short(pcs))
        rv = e.db.notice(nid)["row_ver"]
        before = e.db.dump()
        self.assertNotOk(W2.claim_notice(nid, by=BY_WA, idem_key="nclaim:%s:%d" % (nid, rv), expect_row_ver=rv),
                         "захват draft_unknown (I15)")
        self.assertNoWrites(before, "claim_notice из draft_unknown")
        o = W2.mark_notice(nid, state="drafted", by=BY_WA, idem_key="nst:%s:drafted:77" % nid, expect_row_ver=rv,
                           draft_id=77)
        self.assertCode(o, "ok", msg="draft_unknown → drafted по NoticePort.find")
        self.assertEqual((e.db.notice(nid)["state"], e.db.notice(nid)["draft_id"]), ("drafted", 77))
        src = src_of("wa_agent drafts", "draft:77", "event", e.clock())
        before = e.db.dump()
        o = W2.record_delivery(nid, wamid=WAMID, status="sent", at=e.clock(), source=src, by=BY_WA,
                               idem_key="ndel:%s:%s:sent" % (nid, WAMID))
        self.assertCode(o, "rejected", msg="sent без delivered (I12)")
        self.assertNoWrites(before, "record_delivery(sent)")
        # К4 круг 2 (C10): delivered до привязки отправки — статус сам себя не удостоверяет
        o = W2.record_delivery(nid, wamid=WAMID, status="delivered", at=e.clock(), source=src, by=BY_WA,
                               idem_key="ndel:%s:%s:delivered:unbound" % (nid, WAMID))
        self.assertCode(o, "rejected", msg="delivered без привязки отправки (C10)")
        self.assertNoWrites(before, "record_delivery без привязки отправки")
        o = W2.record_notice_sent(nid, draft_id=77, wamid=WAMID, at=e.clock(),
                                  source=src_of("wa_agent send_text", "draft:77", "door", e.clock()), by=BY_WA,
                                  idem_key="nsent:%s:77:%s" % (nid, WAMID))
        self.assertCode(o, "ok", msg="привязка отправки черновика 77 (C10)")
        self.assertEqual((e.db.notice(nid)["state"], e.db.notice(nid)["wamid"]), ("drafted", WAMID),
                         "привязка отправки не доставка: состояние drafted")
        o = W2.record_delivery(nid, wamid=WAMID, status="delivered", at=e.clock(), source=src, by=BY_WA,
                               idem_key="ndel:%s:%s:delivered" % (nid, WAMID))
        self.assertCode(o, "ok", msg="record_delivery(delivered)")
        n = e.db.notice(nid)
        self.assertEqual((n["state"], n["wamid"]), ("delivered", WAMID))
        t = e.db.task(tid)
        self.assertEqual((t["state"], t["top_stage"]), ("done", 6), "done → done с ступенью 6 (§4.5)")
        st = e.db.stages(tid)
        self.assertEqual(set(st), {"question_sent", "answer_received", "task_accepted", "physically_done",
                                   "result_recorded", "client_notified"})
        self.assertEqual(len(set(r["evidence_ref"] for r in st.values())), 6, "один ref — одна ступень (I27)")
        snap = e.db.dump()
        self.assertCode(W2.record_delivery(nid, wamid=WAMID, status="delivered", at=e.clock(), source=src, by=BY_WA,
                                           idem_key="ndel:%s:%s:delivered" % (nid, WAMID)), "duplicate")
        self.assertNoWrites(snap, "повтор record_delivery")
        self.assertEqual(e.db.case(cid)["ver"], 1, "case_ver дела неизменна на всех шагах (§14)")


# ================================================================================================ обязательства
class TestObligations(K4StoreBase):

    def test_section44_obligation_transitions_I26(self):
        """§4.4, I26/I8, M14: клетка денег не закрывает (value → open, пусто → unknown); сумму want называет только
        одобряющий (агент → approver_unknown); waive — одобряющий; терминальное не меняется; decided → closed(human);
        устаревший expect_row_ver → conflict; обязательства вне REQUIRED рождает только одобряющий."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan())
        rent = e.db.obl(cid, "money", "rent")
        self.assertEqual(rent["state"], "unknown")
        steps = [({"state": "value", "num": 3850}, "open"), ({"state": "empty", "num": 0}, "unknown"),
                 ({"state": "value", "num": 3850}, "open")]
        for cell, st in steps:
            o = self.settle(S, cid, rent["id"], by=BY_CODE, cell=cell)
            self.assertCode(o, "ok", msg="settle cell=%r" % cell)
            r = e.db.obl(cid, "money", "rent")
            self.assertEqual((r["state"], r["closed_by"]), (st, None), "клетка закрыла деньги (I26): %r" % r)
        before = e.db.dump()
        want = {"want": {"amount": 3850, "currency": "THB", "detail": "названо владельцем"}}
        self.assertCode(self.settle(S, cid, rent["id"], by=BY_AGENT, human=want), "rejected", "approver_unknown")
        self.assertCode(self.settle(S, cid, rent["id"], by=BY_CODE, human={"decided": True}), "rejected",
                        "approver_unknown")
        self.assertCode(self.settle(S, cid, rent["id"], rv=e.db.obl(cid, "money", "rent")["row_ver"] - 1,
                                    human=want), "conflict", msg="устаревший expect_row_ver (I8)")
        self.assertNoWrites(before, "отказы settle")
        self.assertCode(self.settle(S, cid, rent["id"], human=want), "ok")
        r = e.db.obl(cid, "money", "rent")
        self.assertEqual((r["state"], r["outcome"], float(r["amount"]), r["currency"]), ("open", "valid", 3850.0, "THB"))
        self.assertTrue(e.db.events(cid, "obligation_want_set"))
        dep = e.db.obl(cid, "money", "deposit")
        self.assertCode(self.settle(S, cid, dep["id"], human={"waive": True, "detail": "залога не было"}), "ok")
        d = e.db.obl(cid, "money", "deposit")
        self.assertEqual((d["state"], d["closed_by"]), ("waived", "human"))
        before = e.db.dump()
        self.assertCode(self.settle(S, cid, dep["id"], human={"decided": True}), "rejected", msg="waived терминально")
        self.assertNoWrites(before, "переход терминального обязательства")
        self.assertCode(self.settle(S, cid, rent["id"], human={"decided": True, "detail": "наличные 3850"}), "ok")
        r = e.db.obl(cid, "money", "rent")
        self.assertEqual((r["state"], r["closed_by"]), ("closed", "human"))
        before = e.db.dump()
        src = src_of("решение одобряющего", "btn:obl:1", "human", T0)
        o = S.open_obligation(cid, kind="money", role="delivery", direction="from_client", source=src, by=BY_AGENT,
                              idem_key="obl:%s:money:delivery:btn:obl:1" % cid, amount=300.0, currency="THB",
                              outcome="valid")
        self.assertCode(o, "rejected", "approver_unknown", msg="агент рождает обязательство")
        self.assertNoWrites(before, "open_obligation агентом")
        o = S.open_obligation(cid, kind="money", role="delivery", direction="from_client", source=src,
                              by=BY_APPROVER, idem_key="obl:%s:money:delivery:btn:obl:1" % cid, amount=300.0,
                              currency="THB", outcome="valid")
        self.assertCode(o, "ok")
        self.assertEqual(e.db.obl(cid, "money", "delivery")["required"], 0)

    def test_I45_write_closes_rent_only_with_second_source(self):
        """I45, M14b, §5.2 settle_obligation(write) при MONEY_CLOSE_RULE="cash_and_second_source": роль ≠ rent →
        rejected(bad_transition); без второго источника → unknown(second_source_missing); сумма не valid →
        unknown(param_unknown, PAYMENT_RECORD_PLACE); всё есть → closed(write) с фактом и вторым источником;
        отзыв второго источника → unknown (obligation_reopened). Каждый отказ — без записей."""
        e = self.env(MONEY_CLOSE_RULE="cash_and_second_source")
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan(to_pay=3850))
        rent = e.db.obl(cid, "money", "rent")
        self.assertEqual((rent["state"], rent["outcome"]), ("open", "incomplete"), "клетка с числом → open/incomplete")
        cash = {"kind": "cash", "src": "tx_find", "row": 2060, "msg_id": "m2060", "link": None,
                "at": "2026-10-05 12:00", "booking_id": BK_IVAN, "bike": BIKE, "amount": 3850, "currency": "THB",
                "role": "оплата аренды", "category": "rental"}
        o = S.bind_cash(cid, cash_fact=cash, rows=[row_ivan(to_pay=3850)],
                        source=src_of("касса", "строка 2060", "door", T_OBS), by=BY_CODE,
                        idem_key="cash:%s:2060:m2060:x" % cid)
        self.assertCode(o, "ok", msg="bind_cash")
        fid = dget(o, "fact_id")
        dep = e.db.obl(cid, "money", "deposit")
        before = e.db.dump()
        o = self.settle(S, cid, dep["id"], by=BY_CODE, write={"cash_fact_id": fid, "second_document_id": None})
        self.assertCode(o, "rejected", "bad_transition", msg="write не у rent")
        o = self.settle(S, cid, rent["id"], by=BY_CODE, write={"cash_fact_id": fid, "second_document_id": None})
        self.assertCode(o, "unknown", "second_source_missing", msg="одна строка кассы")
        self.assertIn("second_source", o.get("missing") or [])
        self.assertNoWrites(before, "write без второго источника")
        rid = e.db.current_rental(cid)["id"]
        o = S.record_document(cid, kind="contract_signed", ext_id="doc-233", status="verified",
                              source=src_of("реестр подписей TB e-Sign (contract_find)", "строка 233", "door", T_OBS),
                              by=BY_APPROVER, idem_key="doc:%s:contract_signed:doc-233:2026-10-01 10:12" % cid,
                              signed_at="2026-10-01 10:12", reg_row=233, rental_id=rid,
                              human_binding={"rental_id": rid})
        self.assertCode(o, "ok", msg="договор по решению одобряющего")
        did = dget(o, "document_id") or e.db.one("SELECT id FROM rc_document WHERE ext_id='doc-233'")["id"]
        before = e.db.dump()
        o = self.settle(S, cid, rent["id"], by=BY_CODE, write={"cash_fact_id": fid, "second_document_id": did})
        self.assertCode(o, "unknown", "param_unknown", msg="сумма want из клетки (incomplete)")
        self.assertIn("PAYMENT_RECORD_PLACE", o.get("missing") or [])
        self.assertNoWrites(before, "write при want не valid")
        self.assertCode(self.settle(S, cid, rent["id"], human={"want": {"amount": 3850, "currency": "THB",
                                                                         "detail": "названо"}}), "ok")
        o = self.settle(S, cid, rent["id"], by=BY_CODE, write={"cash_fact_id": fid, "second_document_id": did})
        self.assertCode(o, "ok", msg="write: касса этого дела + второй источник")
        r = e.db.obl(cid, "money", "rent")
        self.assertEqual((r["state"], r["closed_by"], r["close_fact_id"], r["close_second_id"]),
                         ("closed", "write", fid, did))
        fa = S.facts_for_agent(cid)
        for f in fa.get("facts") or []:
            if f.get("kind") == "case_money":
                self.assertIs(f.get("payment_confirmed"), False, "агенту деньги — не подтверждение оплаты (I45)")
        o = S.revoke_document(cid, document_id=did, reason="sha_changed", by=BY_CODE,
                              source=src_of("реестр подписей TB e-Sign (contract_find)", "строка 233", "door", T0),
                              idem_key="docrev:%s:sha_changed" % did)
        self.assertCode(o, "ok", msg="revoke_document")
        r = e.db.obl(cid, "money", "rent")
        self.assertEqual(r["state"], "unknown", "отзыв второго источника переоткрывает (§4.4, P-B3)")
        self.assertTrue(e.db.events(cid, "obligation_reopened"))


# ================================================================================================ документы I46
class TestDocuments(K4StoreBase):

    def test_I46_K4C39_coverage_only_confirmed_first_late_read(self):
        """I46, К4-C39, M31/M31b/M31c (TB-K4-DOCUMENT-COVERAGE-0910): дело открыто уже по продлённой строке
        (01.10–20.10), договор от 01.10 впервые записан после продления (human_binding без дат) → verified, cover_* NULL;
        human_binding с ключами покрытия → ValueError; documents_for: без периода — только принадлежность
        (unknown(period_not_given), coverage None, pick None); 12.10–20.10 и 01.10–12.10 → unknown(doc_period_unknown);
        confirm_document_coverage: не одобряющий / unverified / без дат, источника, действия, обратные даты — отказы без
        записей; одобряющий 01.10–12.10 → ok, версия та же; 01.10–12.10 → found; 12.10–20.10 →
        unknown(doc_period_not_covered); те же даты → duplicate; иные → rejected(doc_cover_set)."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_ivan(date_end="2026-10-20 10:00"))
        rid = e.db.current_rental(cid)["id"]
        src = src_of("реестр подписей TB e-Sign (contract_find)", "строка 233", "door", T_OBS)
        dkey = "doc:%s:contract_signed:doc-233:2026-10-01 10:12" % cid
        before = e.db.dump()
        with self.assertRaises(ValueError):
            S.record_document(cid, kind="contract_signed", ext_id="doc-233", status="verified", source=src,
                              by=BY_APPROVER, idem_key=dkey, signed_at="2026-10-01 10:12", reg_row=233, rental_id=rid,
                              human_binding={"rental_id": rid, "cover_from": "2026-10-01", "cover_to": "2026-10-12"})
        self.assertNoWrites(before, "human_binding с ключами покрытия")
        o = S.record_document(cid, kind="contract_signed", ext_id="doc-233", status="verified", source=src,
                              by=BY_APPROVER, idem_key=dkey, signed_at="2026-10-01 10:12", reg_row=233, rental_id=rid,
                              human_binding={"rental_id": rid})
        self.assertCode(o, "ok", msg="record_document human_binding")
        did = dget(o, "document_id") or e.db.one("SELECT id FROM rc_document WHERE ext_id='doc-233'")["id"]
        d = e.db.one("SELECT * FROM rc_document WHERE id=?", (did,))
        self.assertEqual((d["status"], d["rental_id"]), ("verified", rid))
        for c in ("cover_from", "cover_to", "cover_basis", "cover_ref", "cover_by", "cover_act", "cover_at"):
            self.assertIsNone(d[c], "record_document записал %s (M31b: срок привязки — не покрытие)" % c)
        r = S.documents_for(cid, period=None)
        self.assertEqual(r.get("code"), "unknown")
        self.assertEqual(reason_code(r), "period_not_given")
        self.assertEqual(r.get("missing"), ["period"])
        self.assertIsNone(r.get("pick"))
        doc = [x for x in r.get("documents") or [] if x.get("document_id") == did]
        self.assertEqual(len(doc), 1, "без периода документ отдаётся с принадлежностью: %s" % short(r))
        self.assertEqual((doc[0].get("binding"), doc[0].get("coverage")), ("bound", None), "M31c: срок не подставлен")
        for period in (("2026-10-12", "2026-10-20"), ("2026-10-01", "2026-10-12")):
            r = S.documents_for(cid, period=period)
            self.assertEqual((r.get("code"), reason_code(r)), ("unknown", "doc_period_unknown"),
                             "принадлежность выдана за покрытие %s (M31/M31b): %s" % (period, short(r)))
            self.assertEqual(r.get("missing"), ["document_period"])
            self.assertTrue(r.get("ask"))
            self.assertIsNone(r.get("pick"))
            doc = [x for x in r.get("documents") or [] if x.get("document_id") == did][0]
            self.assertEqual((doc.get("binding"), doc.get("coverage")), ("bound", "unknown"))
        fa = S.facts_for_agent(cid, period=("2026-10-12", "2026-10-20"))
        self.assertNotIn("covers", [f.get("coverage") for f in fa.get("facts") or []])

        def cover(by=BY_APPROVER, document_id=did, cf="2026-10-01", ct="2026-10-12",
                  sref="PDF договора: срок аренды 01.10–12.10", act="btn:cover:1"):
            return S.confirm_document_coverage(cid, document_id=document_id, cover_from=cf, cover_to=ct,
                                               source_ref=sref, act_ref=act, by=by,
                                               idem_key="cover:%s:%s:%s" % (document_id, cf, ct))
        o = S.record_document(cid, kind="contract_signed", ext_id="doc-240", status="unverified", source=src,
                              by=BY_CODE, idem_key="doc:%s:contract_signed:doc-240:2026-10-02 11:00" % cid,
                              signed_at="2026-10-02 11:00", reg_row=240)
        self.assertCode(o, "ok", msg="record_document unverified")
        uv = dget(o, "document_id") or e.db.one("SELECT id FROM rc_document WHERE ext_id='doc-240'")["id"]
        self.assertEqual(e.db.one("SELECT status FROM rc_document WHERE id=?", (uv,))["status"], "unverified")
        before = e.db.dump()
        self.assertCode(cover(by=BY_STRANGER), "rejected", "approver_unknown")
        self.assertCode(cover(by=BY_CODE), "rejected", "approver_unknown")
        self.assertCode(cover(cf="2026-10-13", ct="2026-10-12"), "rejected", "doc_cover_invalid")
        self.assertCode(cover(cf="01.10.2026"), "rejected", "doc_cover_invalid")
        self.assertCode(cover(sref=""), "rejected", "doc_cover_invalid")
        self.assertCode(cover(act=""), "rejected", "doc_cover_invalid")
        self.assertCode(cover(document_id=uv), "rejected", "doc_unknown")            # покрытие у unverified
        self.assertCode(cover(document_id=did + 100000), "rejected", "doc_unknown")  # не документ дела
        self.assertNoWrites(before, "отказы подтверждения покрытия")
        o = cover()
        self.assertCode(o, "ok", msg="подтверждение одобряющим с явными датами и источником")
        d = e.db.one("SELECT * FROM rc_document WHERE id=?", (did,))
        self.assertEqual((d["cover_from"], d["cover_to"], d["cover_basis"], d["cover_ref"], d["cover_by"],
                          d["cover_act"]),
                         ("2026-10-01", "2026-10-12", "human_confirmed", "PDF договора: срок аренды 01.10–12.10",
                          APPROVER, "btn:cover:1"))
        self.assertEqual((d["status"], d["rental_id"]), ("verified", rid))
        self.assertEqual(e.db.case(cid)["ver"], 1, "подтверждение покрытия версию не поднимает")
        self.assertTrue(e.db.events(cid, "document_coverage_confirmed"))
        r = S.documents_for(cid, period=("2026-10-01", "2026-10-12"))
        self.assertEqual((r.get("code"), r.get("pick")), ("found", did), short(r))
        r = S.documents_for(cid, period=("2026-10-12", "2026-10-20"))
        self.assertEqual((r.get("code"), reason_code(r)), ("unknown", "doc_period_not_covered"),
                         "продление не расширяет покрытие: %s" % short(r))
        self.assertTrue(r.get("ask"))
        snap = e.db.dump()
        self.assertCode(cover(), "duplicate", msg="те же даты")
        self.assertCode(cover(cf="2026-10-01", ct="2026-10-20", sref="допсоглашение п.1", act="btn:cover:2"),
                        "rejected", "doc_cover_set")
        self.assertNoWrites(snap, "покрытие не переписывается")


# ================================================================================================ представление дела
class TestViews(K4StoreBase):

    def test_I22_K4C36_case_view_and_facts_for_agent_src(self):
        """I22, К4-C36, Д2, F2 К3: case_view отдаёт все части §8.4; у каждого элемента 6 полей src, значения — из
        колонок строки или по таблице вывода §8.4 (без подстановки); passport_deposit в документах; facts_for_agent —
        инструмент case, version «case_ver:<n>», виды case_*, doc_kind, payment_confirmed=false, coverage None без
        периода; версии внешнего источника нет нигде."""
        e = self.env()
        S = e.store("splinter")
        cid = self.new_case(S, row_boris())
        tid = self.new_task(S, cid)
        eid = self.asked_and_posted(S, cid, task_id=tid, topic_msg=7001, deliv_msg=7002)
        e.clock.advance(60)
        a = self.staff_reply(S, 7010, 7001)
        self.assertEqual(verdict_of(a), "accepted")
        aid = dget(a, "answer_id")
        fk = ["bike_state", BIKE, "2026-10-01 10:05"]
        st_obs = T0 - 3600
        o = S.record_fact(cid, kind="bike_state", value={"status": "в аренде", "location": "", "updated":
                                                         "2026-10-01 10:05", "date_due": "", "booking_id_seen": "",
                                                         "client_seen": "", "flags": []},
                          source=src_of("лист «состояние_байка» (state_get)", BIKE, "door", st_obs), scope="case",
                          by=BY_SPL, idem_key=k_fact(cid, fk, st_obs), fkey=fk)
        self.assertCode(o, "ok")
        rid = e.db.current_rental(cid)["id"]
        o = S.record_document(cid, kind="contract_signed", ext_id="doc-233", status="verified",
                              source=src_of("реестр подписей TB e-Sign (contract_find)", "строка 233", "door", T_OBS),
                              by=BY_APPROVER, idem_key="doc:%s:contract_signed:doc-233:2026-10-15 09:50" % cid,
                              signed_at="2026-10-15 09:50", reg_row=233, rental_id=rid,
                              human_binding={"rental_id": rid})
        self.assertCode(o, "ok")
        e.clock.advance(5)
        now = e.clock()
        cv = S.case_view(cid)
        for part in VIEW_PARTS:
            self.assertIn(part, cv, "case_view без части %s (§8.4, Д2)" % part)
        els = []
        for part in SRC_PARTS:
            walk_elements(cv[part], part, els, part in ("case", "client"))
        self.assertTrue(els)
        for path, el in els:
            self.check_src(path, el)

        def find(pred):
            for path, el in els:
                if pred(path, el):
                    return el
            return None
        rental = e.db.current_rental(cid)
        self.assertSrcFromRow("аренда", find(lambda p, x: p.startswith("rental") and x.get("start_day") == "2026-10-15"),
                              rental)
        self.assertSrcFromRow("клиент", cv["client"], rental)
        contact = e.db.one("SELECT * FROM rc_contact WHERE case_id=? AND channel='wa'", (cid,))
        self.assertSrcFromRow("контакт", find(lambda p, x: p.startswith("client") and x.get("channel") == "wa"),
                              contact)
        for ext in ("doc-233", "deposit:845"):
            row = e.db.one("SELECT * FROM rc_document WHERE case_id=? AND ext_id=?", (cid, ext))
            self.assertSrcFromRow("документ %s" % ext,
                                  find(lambda p, x, ext=ext: p.startswith("documents") and x.get("ext_id") == ext), row)
        for part, kind, role in (("money", "money", "rent"), ("money", "money", "deposit"),
                                 ("obligations_other", "bike", "handover"),
                                 ("obligations_other", "document", "passport_return")):
            row = e.db.obl(cid, kind, role)
            self.assertSrcFromRow("обязательство %s/%s" % (kind, role),
                                  find(lambda p, x, part=part, role=role: p.startswith(part) and x.get("role") == role
                                       and "src" in x), row)
        frow = e.db.facts(cid, "bike_state")[0]
        self.assertSrcFromRow("факт bike_state", find(lambda p, x: p.startswith("facts") and x.get("kind") ==
                                                      "bike_state"), frow)
        case = e.db.case(cid)
        self.assertSrcEquals("дело", cv["case"], {"source": "rental_case", "ref": cid, "method": "event",
                                                  "read_at": now, "observed_at": case["updated_at"],
                                                  "case_ver": case["ver"]})
        erow = e.db.exp(eid)
        self.assertSrcEquals("ожидание", find(lambda p, x: p.startswith("expectations") and x.get("exp_id") == eid),
                             {"source": "rental_case", "ref": eid, "method": "event", "read_at": now,
                              "observed_at": erow["updated_at"], "case_ver": erow["case_ver"]})
        trow = e.db.task(tid)
        self.assertSrcEquals("задача", find(lambda p, x: p.startswith("tasks") and x.get("task_id") == tid
                                            and "stage" not in x),
                             {"source": "rental_case", "ref": tid, "method": "event", "read_at": now,
                              "observed_at": trow["updated_at"], "case_ver": trow["case_ver"]})
        arow = e.db.one("SELECT * FROM rc_answer WHERE chat=? AND msg_id='7010'", (TOPIC_CHAT,))
        ans_el = find(lambda p, x: p.startswith("answers") and (x.get("answer_id") == (aid or arow["id"]) or
                                                               (x.get("src") or {}).get("ref") == "%s:7010" % TOPIC_CHAT))
        self.assertSrcEquals("ответ", ans_el, {"source": "staff_ask:topic", "ref": "%s:7010" % TOPIC_CHAT,
                                               "method": "reply", "read_at": arow["received_at"],
                                               "observed_at": arow["at"], "case_ver": arow["case_ver_at"]})
        bike = cv["bike"]
        self.assertIsInstance(bike, dict)
        self.assertEqual((bike.get("plate"), bike.get("bike_name")), (PLATE, BIKE))
        self.assertIsInstance(bike.get("state"), dict, "часть «байк» без state при факте bike_state (§8.4)")
        self.assertSrcFromRow("байк.state", bike["state"], frow)
        self.assertIn("passport_deposit", short(cv["documents"], 100000))
        self.assertNoSourceVersion(cv, "case_view")

        fa = S.facts_for_agent(cid)
        self.assertEqual((fa.get("tool"), fa.get("outcome")), ("case", "fact"))
        self.assertEqual(fa.get("version"), "case_ver:%d" % case["ver"], "version — версия ДЕЛА с меткой (§8.3)")
        facts = fa.get("facts") or []
        kinds = set(f.get("kind") for f in facts)
        for k in ("case", "case_client", "case_rental", "case_bike", "case_money", "case_document", "case_answer"):
            self.assertIn(k, kinds, "facts_for_agent без %s (§8.3/§8.4)" % k)
        fels = []
        walk_elements(facts, "facts", fels)
        for path, el in fels:
            self.check_src(path, el)
        for f in facts:
            if f.get("kind") == "case_document":
                self.assertIn("doc_kind", f, "вид документа — doc_kind (§8.3)")
                self.assertIsNone(f.get("coverage"), "coverage без периода — None («не спрашивалось», I46)")
            if f.get("kind") == "case_money":
                self.assertIs(f.get("payment_confirmed"), False, "I45")
        self.assertIn("passport_deposit", [f.get("doc_kind") for f in facts if f.get("kind") == "case_document"])
        self.assertNoSourceVersion(fa, "facts_for_agent")
        self.assertNotEqual(fa.get("version"), "2026-10-15 09:50", "signed_at не версия (F2 К3)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
