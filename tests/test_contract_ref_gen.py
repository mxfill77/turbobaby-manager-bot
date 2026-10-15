#!/usr/bin/env python3
"""CONTRACTREF1510 · сторона splinter (генератор договора): флаг CONTRACT_REF_GEN (проект §5, приёмка §8.3 G1–G8).

`bot.scheduled_contract_km` и команда «договор» (`splinter._handle_intake`, ветка 1b): при флаге бронь берётся по
booking_id (кол. Y), а отказ моста `no_passport` называет, что лежит в реестре подписей по этой брони
(`splinter._contract_ref_report`: только чтение — `clients` и `contract_find`, второго make_contract нет). Флаг выкл —
вызовы, ответы и строки журнала прежние байт-в-байт.

Мост — подделка со счётчиками ВСЕХ методов; Telegram (`splinter._send`) — запись; тяжёлые зависимости `bot.py`
(Claude, Memory, Auditor, dotenv) застаблены ДО импорта (как `tests/test_audit_button.py`) — живой memory.db, .env и
сеть не трогаются. Данные синтетические: номер 79990001122, байк «Honda PCX 160 1234», имя «Тест Тестов», строки
реестра 34/35/36."""
import ast
import asyncio
import datetime
import json
import logging
import os
import subprocess
import sys
import types
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
FLAG = "CONTRACT_REF_GEN"
os.environ.pop(FLAG, None)

PROBE_ARG = "--probe-gen-off-imports"
PROBE_MARK = "CONTRACTREF_GEN_OFF "
PROBE = PROBE_ARG in sys.argv[1:]

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import splinter as S  # noqa: E402


class _FakeMemory:
    def all_topic_bikes(self):
        return {}

    def all_info_pins(self):
        return {}


class _FakeAuditor:
    audit_groups = []

    def __init__(self, *a, **k):
        pass

    def set_audit_config(self, *a, **k):
        pass


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("claude_client", ClaudeClient=lambda *a, **k: types.SimpleNamespace())
_stub("memory", Memory=_FakeMemory)
_stub("auditor", Auditor=_FakeAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")
import bot as B  # noqa: E402

NUM = "79990001122"
PHONE = "+7 999 000-11-22"
NAME = "Тест Тестов"
BIKE = "Honda PCX 160 1234"
UUID = "3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f"
TODAY = datetime.datetime.now(ZoneInfo(B.TZ_NAME)).strftime("%Y-%m-%d")
END = (datetime.datetime.strptime(TODAY, "%Y-%m-%d") + datetime.timedelta(days=6)).strftime("%Y-%m-%d")
NO_PASSPORT = {"ok": False, "error": "no_passport", "message": "строки паспорта в Bot Data нет"}
OK_MAKE = {"ok": True, "name": "Договор", "url": "https://docs/x", "flags": {"km_request": False}}
OLD_FAIL = "🐀 Splinter\n❌ Договор не сделан: no_passport. строки паспорта в Bot Data нет"
ASK_BOOKING = ("🐀 Splinter\nУкажи бронь: «договор <booking_key>» или «договор <Имя> <дата>», либо отправь после "
               "карточки брони.")
INTAKE = S.INTAKE_CHAT


def crm_row(row=12, booking_id=UUID, name=NAME, date_start=None, status="Бронь", bike=BIKE):
    return {"row": row, "status": status, "auto_cancel": "", "bike": bike, "name": name,
            "date_start": date_start or TODAY + " 10:00", "date_end": END + " 18:00", "contacts": NAME + " " + PHONE,
            "booking_id": booking_id, "deposit_raw": "passport"}


def reg_row(row, status, signed_at="", pdf_id="", bike=BIKE, phone=PHONE, date=None):
    """Запись реестра живой формы (`bridge_client.contract_find`), поиск — по байку и сроку (matched_on bike)."""
    return {"row": row, "doc_id": "1AbCdEfDOC%d" % row, "client": NAME, "contract_date": date or TODAY,
            "contract_date_raw": date or TODAY, "created_raw": date or TODAY, "date_src": "contract_date",
            "status": status, "signed": status == "ПОДПИСАН", "signed_at": signed_at, "bike": bike, "phone": phone,
            "pdf_id": pdf_id, "matched_on": ["bike"]}


def find(rows, outcome=None):
    signed = [r for r in rows if r["signed"]]
    out = outcome or ("none" if not rows else "none_signed" if not signed else "one" if len(signed) == 1 else "ambiguous")
    return {"ok": True, "outcome": out, "pick": dict(signed[0], pdf_ready=True) if out == "one" else None,
            "reason": None, "items": [dict(r) for r in rows], "undated_items": [],
            "checked": {"rows_scanned": 40, "matched": len(rows), "signed": len(signed), "returned": len(rows),
                        "truncated": False, "undated": 0, "undated_signed": 0, "date_unparsed": 0, "unread": [],
                        "complete": True},
            "filter": {"phone_last9": "", "name": "", "bike": BIKE, "plate": "1234", "date_from": TODAY,
                       "date_to": END}}


SIGNED_LIVE = [reg_row(34, "ОТОЗВАН", TODAY + " 09:47", "P34"), reg_row(36, "ПОДПИСАН", TODAY + " 11:04", "PDF36")]
PENDING_LIVE = [reg_row(34, "ОТОЗВАН", TODAY + " 09:47", "P34"), reg_row(36, "ОТПРАВЛЕН")]


class Bridge:
    """Поддельный мост: каждый вызов любого метода — в `calls` (имя, аргументы)."""

    def __init__(self, clients=(), make=None, found=None, find_exc=None, clients_exc=None):
        self.calls, self.clients = [], list(clients)
        self.make = dict(make or NO_PASSPORT)
        self.found = found if found is not None else find(SIGNED_LIVE)
        self.find_exc, self.clients_exc = find_exc, clients_exc

    def _call(self, action, **kw):
        self.calls.append(("_call:" + action, kw))
        if self.clients_exc is not None:
            raise self.clients_exc
        return {"ok": True, "action": action, "data": {"clients": [dict(c) for c in self.clients]}}

    def issue_write_ticket(self):
        self.calls.append(("issue_write_ticket", {}))
        return {"ok": True, "ticket": "t-1"}

    def make_contract(self, **kw):
        self.calls.append(("make_contract", kw))
        return dict(self.make)

    def contract_find(self, **kw):
        self.calls.append(("contract_find", kw))
        if self.find_exc is not None:
            raise self.find_exc
        return self.found

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*a, **k):
            self.calls.append((name, k))
            return {"ok": False, "error": "стенд"}
        return call

    def n(self, name):
        return sum(1 for c, _ in self.calls if c == name)

    def args(self, name):
        return [k for c, k in self.calls if c == name]


class Logs(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


LOGS = Logs()
for _name in ("turbobaby", "splinter"):
    logging.getLogger(_name).addHandler(LOGS)
    logging.getLogger(_name).setLevel(logging.INFO)

SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    SENDS.append(text)


S._send = _rec_send


class _U:
    def __init__(self, uname="deramor"):
        self.username, self.is_bot, self.id = uname, False, 1


class Msg:
    def __init__(self, text, uname="deramor"):
        self.text, self.caption, self.photo = text, None, None
        self.chat_id, self.message_thread_id = INTAKE, None
        self.date = datetime.datetime(2026, 10, 14, 8, 0, tzinfo=datetime.timezone.utc)
        self.message_id, self.from_user, self.reply_to_message = 777, _U(uname), None


def flag(on):
    if on:
        os.environ[FLAG] = "1"
    else:
        os.environ.pop(FLAG, None)


def km(bridge, on):
    """Один запуск задания `scheduled_contract_km` на подделке. → новые строки журнала."""
    flag(on)
    B.bridge = bridge
    start = len(LOGS.lines)
    asyncio.run(B.scheduled_contract_km(None))
    return LOGS.lines[start:]


def intake(text, bridge, on, drafts=None):
    """Одна команда «договор …» во «Входящих бронях». → (ответы, новые строки журнала)."""
    flag(on)
    SENDS.clear()
    S._INTAKE_DRAFTS.clear()
    if drafts:
        S._INTAKE_DRAFTS[INTAKE] = dict(drafts)
    start = len(LOGS.lines)
    asyncio.run(S._handle_intake(Msg(text), None, bridge, None))
    return list(SENDS), LOGS.lines[start:]


def ref_lines(lines):
    return [ln for ln in lines if "реестр:" in ln]


# ═══ G1 · флаг ВЫКЛ — прежнее байт-в-байт ═══════════════════════════════════════════════════════════════════════

def test_g01_flag_off_contract_km_as_before():
    b = Bridge(clients=[crm_row(), crm_row(row=13, booking_id="", name="Другой Клиент", date_start="2026-01-01 10:00"),
                        crm_row(row=14, status="В аренде")])
    lines = km(b, on=False)
    assert b.args("make_contract") == [{"name": NAME, "date_start": TODAY + " 10:00"}], b.calls
    assert b.n("contract_find") == 0 and b.n("_call:clients") == 1 and b.n("issue_write_ticket") == 1, b.calls
    assert [c for c, _ in b.calls] == ["_call:clients", "issue_write_ticket", "make_contract"], b.calls
    assert lines == ["  📄 contract_km: бронь «%s» — no_passport" % NAME], lines


def probe_off():
    """Отдельный процесс: флаг выключен — задание и команда с отказом no_passport; contract_ref не загружается."""
    b = Bridge(clients=[crm_row()])
    km(b, on=False)
    sends, _l = intake("договор %s" % UUID, b, on=False)
    sends2, _l2 = intake("договор Тест Тестов " + TODAY, b, on=False)
    out = {"modules": sorted(m for m in ("contract_ref",) if m in sys.modules), "find": b.n("contract_find"),
           "sends": sends + sends2}
    sys.stdout.write(PROBE_MARK + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def test_g01b_flag_off_process_never_imports_contract_ref():
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and len(got) == 1, (p.returncode, text[-1500:], p.stderr.decode("utf-8", "replace")[-1500:])
    out = json.loads(got[0][len(PROBE_MARK):])
    assert out == {"modules": [], "find": 0, "sends": [ASK_BOOKING, OLD_FAIL]}, out


# ═══ G2 · флаг ВКЛ: бронь по booking_id ═══════════════════════════════════════════════════════════════════════════

def test_g02_flag_on_booking_id_only_kwarg_else_old_call():
    b = Bridge(clients=[crm_row()], make=OK_MAKE)
    km(b, on=True)
    assert b.args("make_contract") == [{"booking_id": UUID}], b.calls
    for empty in ("", "   ", None):
        b = Bridge(clients=[crm_row(booking_id=empty)], make=OK_MAKE)
        km(b, on=True)
        assert b.args("make_contract") == [{"name": NAME, "date_start": TODAY + " 10:00"}], (empty, b.calls)
    b = Bridge(clients=[crm_row(booking_id="  %s " % UUID)], make=OK_MAKE)
    km(b, on=True)
    assert b.args("make_contract") == [{"booking_id": UUID}], b.calls


# ═══ G3 · отчёт о реестре — только при no_passport ═════════════════════════════════════════════════════════════════

def test_g03_registry_read_only_on_no_passport_one_find_name_free_line():
    b = Bridge(clients=[crm_row()], make=OK_MAKE)
    lines = km(b, on=True)
    assert b.n("contract_find") == 0 and not ref_lines(lines), (b.calls, lines)
    for found, head in ((find(SIGNED_LIVE), "в реестре есть подписанный договор этой брони: стр. 36 · ПОДПИСАН "),
                        (find(PENDING_LIVE), "в реестре договор этой брони ждёт подписи: стр. 36 · ОТПРАВЛЕН · doc "
                                             "…fDOC36")):
        b = Bridge(clients=[crm_row()], found=found)
        lines = km(b, on=True)
        assert b.args("contract_find") == [{"bike": BIKE, "date_from": TODAY, "date_to": END, "limit": 100}], b.calls
        assert b.n("make_contract") == 1 and b.n("issue_write_ticket") == 1 and b.n("_call:clients") == 1, b.calls
        new = ref_lines(lines)
        assert len(new) == 1 and new[0].startswith("  📄 contract_km: строка CRM 12 — реестр: " + head), new
        assert "мост его не пересоберёт: строки паспорта в Bot Data нет (договор сделан не мостом)" in new[0], new
        assert NAME not in new[0] and "990001122" not in new[0], new
        assert lines[0] == "  📄 contract_km: бронь «%s» — no_passport" % NAME, "прежняя строка — на месте"
    # иной отказ моста — реестр не читается
    b = Bridge(clients=[crm_row()], make={"ok": False, "error": "no_booking"})
    lines = km(b, on=True)
    assert b.n("contract_find") == 0 and not ref_lines(lines), lines


# ═══ G4 · реестр не прочитан — «неизвестно» ════════════════════════════════════════════════════════════════════════

def test_g04_registry_refused_or_crashed_is_unknown():
    for kw in ({"found": {"ok": False, "error": "card_deadline"}}, {"find_exc": TimeoutError("timed out")},
               {"found": {"ok": True}}):
        b = Bridge(clients=[crm_row()], **kw)
        new = ref_lines(km(b, on=True))
        assert len(new) == 1 and "реестр не прочитан (" in new[0] and new[0].endswith(
            "— неизвестно, а не «договора нет»"), (kw, new)
        assert "нет договора" not in new[0]
    b = Bridge(clients=[crm_row()], find_exc=TimeoutError("timed out"))
    assert "TimeoutError" in ref_lines(km(b, on=True))[0]
    b = Bridge(clients=[crm_row()], found=find(SIGNED_LIVE))
    assert "подписанный договор этой брони: стр. 36" in ref_lines(km(b, on=True))[0]


# ═══ G5 · команда «договор <uuid>» ═════════════════════════════════════════════════════════════════════════════════

def test_g05_uuid_command_only_with_flag():
    b = Bridge(clients=[crm_row()])
    sends, _l = intake("договор %s" % UUID, b, on=False)
    assert sends == [ASK_BOOKING] and b.n("make_contract") == 0 and b.calls == [], (sends, b.calls)
    b = Bridge(clients=[crm_row()], make=OK_MAKE)
    sends, _l = intake("договор %s" % UUID, b, on=True)
    assert b.args("make_contract") == [{"booking_id": UUID}] and b.n("issue_write_ticket") == 1, b.calls
    assert sends and sends[0].startswith("🐀 Splinter\n✅ Договор готов: https://docs/x"), sends
    for text in ("договор %s-x" % UUID, "договор %s лишнее" % UUID, "договор 3f2a9c1e7b4d4e8a9c0f1a2b3c4d5e6f"):
        b = Bridge(clients=[crm_row()], make=OK_MAKE)
        sends, _l = intake(text, b, on=True)
        assert {"booking_id": UUID} not in b.args("make_contract"), (text, b.calls)
    # прочие формы — прежние при любом флаге
    for on in (False, True):
        b = Bridge(make=OK_MAKE)
        intake("договор NINJA|%s|%s" % (NAME, TODAY), b, on=on)
        key = "NINJA|%s|%s" % (NAME, TODAY)
        assert b.args("make_contract") == [{"booking_key": key, "name": None, "date_start": None}], b.calls
        b = Bridge(make=OK_MAKE)
        intake("договор %s %s" % (NAME, TODAY), b, on=on)
        assert b.args("make_contract") == [{"booking_key": None, "name": NAME, "date_start": TODAY}], b.calls
        b = Bridge(make=OK_MAKE)
        intake("договор", b, on=on, drafts={"model": BIKE, "client": NAME, "date_start": TODAY, "ts": 0})
        key = "%s|%s|%s" % (BIKE, NAME, TODAY)
        assert b.args("make_contract") == [{"booking_key": key, "name": None, "date_start": None}], b.calls


# ═══ G6 · отчёт команды: строка CRM по ключу брони ═════════════════════════════════════════════════════════════════

def test_g06_intake_no_passport_report_many_crm_rows_and_one():
    import contract_ref as CR
    two = [crm_row(row=12, booking_id="bk-1"), crm_row(row=13, booking_id="bk-2")]
    b = Bridge(clients=two)
    sends, lines = intake("договор %s|%s|%s" % (BIKE, NAME, TODAY), b, on=True)
    assert sends == [OLD_FAIL + "\n📄 Реестр по этой брони: " + CR.GEN_MANY_CRM % "12, 13"], sends
    assert b.n("contract_find") == 0 and b.n("_call:clients") == 1 and b.n("make_contract") == 1, b.calls
    assert lines[-1] == "  🆕 INTAKE: договор не сделан (no_passport) — реестр: " + CR.GEN_MANY_CRM % "12, 13", lines
    b = Bridge(clients=[crm_row()])
    sends, lines = intake("договор %s|%s|%s" % (BIKE, NAME, TODAY), b, on=True)
    assert b.args("contract_find") == [{"bike": BIKE, "date_from": TODAY, "date_to": END, "limit": 100}], b.calls
    assert sends[0].startswith(OLD_FAIL + "\n📄 Реестр по этой брони: в реестре есть подписанный договор этой брони: "
                               "стр. 36 · ПОДПИСАН"), sends
    assert NAME not in sends[0].split("\n📄", 1)[1], sends
    # «договор <uuid>» при no_passport — строка CRM по booking_id; «Имя дата»; брони нет; CRM не прочитан
    b = Bridge(clients=[crm_row(booking_id="bk-1"), crm_row(row=13)])
    sends, _l = intake("договор %s" % UUID, b, on=True)
    assert b.args("make_contract") == [{"booking_id": UUID}] and b.n("contract_find") == 1, b.calls
    b = Bridge(clients=[crm_row()])
    sends, _l = intake("договор %s %s" % (NAME, TODAY), b, on=True)
    assert b.n("contract_find") == 1 and "стр. 36" in sends[0], (b.calls, sends)
    b = Bridge(clients=[])
    sends, _l = intake("договор %s %s" % (NAME, TODAY), b, on=True)
    assert sends == [OLD_FAIL + "\n📄 Реестр по этой брони: " + CR.GEN_NO_CRM] and b.n("contract_find") == 0, sends
    b = Bridge(clients=[crm_row()], clients_exc=TimeoutError("x"))
    sends, _l = intake("договор %s %s" % (NAME, TODAY), b, on=True)
    assert sends == [OLD_FAIL + "\n📄 Реестр по этой брони: " + CR.GEN_CRM_UNREAD % "TimeoutError"], sends
    b = Bridge(clients=[crm_row(bike="Honda PCX")])                  # в строке брони нет номера байка
    sends, _l = intake("договор %s %s" % (NAME, TODAY), b, on=True)
    assert sends == [OLD_FAIL + "\n📄 Реестр по этой брони: " + CR.GEN_NO_TERM] and b.n("contract_find") == 0, sends
    # флаг выкл — тот же отказ без отчёта и без чтений
    b = Bridge(clients=two)
    sends, lines = intake("договор %s|%s|%s" % (BIKE, NAME, TODAY), b, on=False)
    assert sends == [OLD_FAIL] and b.n("_call:clients") == 0 and not [ln for ln in lines if "реестр" in ln], sends


# ═══ G7 · граница устройством ═════════════════════════════════════════════════════════════════════════════════════

def _fn(path, name):
    tree = ast.parse(open(path, encoding="utf-8").read())
    got = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(got) == 1, name
    return got[0]


def test_g07_report_has_no_write_names_and_reads_at_most_once():
    fn = _fn(S.__file__, "_contract_ref_report")
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | \
        {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute)}
    bad = {"make_contract", "issue_write_ticket", "agent_write", "_post", "save_passport", "create_booking"}
    assert not names & bad, names & bad
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert sum(1 for c in calls if c.func.attr == "contract_find") == 1
    assert sum(1 for c in calls if c.func.attr == "_call") == 1
    b = Bridge(clients=[crm_row()])
    words = S._contract_ref_report(b, booking_key="x|%s|%s" % (NAME, TODAY))
    assert [c for c, _ in b.calls] == ["_call:clients", "contract_find"], b.calls
    assert words.startswith("в реестре есть подписанный договор этой брони"), words
    b = Bridge()
    S._contract_ref_report(b, row=crm_row())
    assert [c for c, _ in b.calls] == ["contract_find"], b.calls
    assert S.F_CONTRACT_REF_GEN == FLAG
    km_fn = _fn(B.__file__, "scheduled_contract_km")
    gens = [n for n in ast.walk(km_fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "_rc_on"]
    loops = [n for n in ast.walk(km_fn) if isinstance(n, ast.For)]
    assert len(gens) == 1 and len(loops) == 1 and gens[0].lineno < loops[0].lineno, "флаг — один раз до цикла"


# ═══ G8 · флаг переключён между запусками — без переимпорта ═══════════════════════════════════════════════════════

def test_g08_flag_toggle_between_runs():
    seen = []
    for on in (False, True, False, True):
        b = Bridge(clients=[crm_row()])
        lines = km(b, on=on)
        seen.append((b.args("make_contract"), b.n("contract_find"), len(ref_lines(lines))))
    off = ([{"name": NAME, "date_start": TODAY + " 10:00"}], 0, 0)
    on_ = ([{"booking_id": UUID}], 1, 1)
    assert seen == [off, on_, off, on_], seen
    for on, want in ((False, [ASK_BOOKING]), (True, None), (False, [ASK_BOOKING])):
        b = Bridge(make=OK_MAKE)
        sends, _l = intake("договор %s" % UUID, b, on=on)
        assert (sends == want) if want else b.args("make_contract") == [{"booking_id": UUID}], (on, sends, b.calls)


# ═══ находки критика CONTRACTREF1510 (правка после приёмки) ═══════════════════════════════════════════════════════

def test_g09_report_broken_module_or_crash_is_unknown_words():
    """11: модуль сверки не собран / разбор упал — слова W_CONTRACT_REF_BROKEN («неизвестно, а не «договора нет»»),
    исключения наружу нет, мост после сбоя не зовётся."""
    saved = sys.modules.get("contract_ref", "нет")
    sys.modules["contract_ref"] = None                         # import падает ModuleNotFoundError
    try:
        b = Bridge(clients=[crm_row()])
        words = S._contract_ref_report(b, row=crm_row())
    finally:
        if saved == "нет":
            sys.modules.pop("contract_ref", None)
        else:
            sys.modules["contract_ref"] = saved
    assert words == S.W_CONTRACT_REF_BROKEN % "ModuleNotFoundError" and b.calls == [], (words, b.calls)
    assert words.endswith("— неизвестно, а не «договора нет»"), words
    import contract_ref as CR
    real = CR.binding_of_crm

    def boom(row):
        raise RuntimeError("стенд")
    CR.binding_of_crm = boom
    try:
        b = Bridge(clients=[crm_row()])
        words = S._contract_ref_report(b, row=crm_row())
    finally:
        CR.binding_of_crm = real
    assert words == S.W_CONTRACT_REF_BROKEN % "RuntimeError" and b.n("contract_find") == 0, (words, b.calls)
    assert S._contract_ref_report(Bridge(), row=crm_row()).startswith("в реестре есть подписанный договор")   # близнец


def test_g10_clients_refused_or_garbage_is_crm_unread():
    """11: ответ clients с ok=False / не словарь — GEN_CRM_UNREAD, contract_find не зовётся; близнец ok — чтение."""
    import contract_ref as CR

    class CrmBridge(Bridge):
        def __init__(self, resp):
            Bridge.__init__(self)
            self.resp = resp

        def _call(self, action, **kw):
            self.calls.append(("_call:" + action, kw))
            return self.resp
    key = "x|%s|%s" % (NAME, TODAY)
    for resp, why in (({"ok": False, "error": "timeout"}, "timeout"), ({"ok": False}, "ответ не разобран"),
                      ("строка", "ответ не разобран"), (None, "ответ не разобран")):
        b = CrmBridge(resp)
        assert S._contract_ref_report(b, booking_key=key) == CR.GEN_CRM_UNREAD % why, (resp, b.calls)
        assert b.n("contract_find") == 0 and b.n("_call:clients") == 1, b.calls
    b = CrmBridge({"ok": True, "data": {"clients": [crm_row()]}})
    assert S._contract_ref_report(b, booking_key=key).startswith("в реестре есть подписанный договор этой брони")
    assert b.n("contract_find") == 1


def test_g11_two_bookings_same_name_and_day_each_by_its_booking_id():
    """10: две строки «Бронь» с одним именем и днём. Флаг ВКЛ — два make_contract(booking_id) с РАЗНЫМИ ключами (мост
    ключует Doc по кол. Y: у второй брони — свой Doc, то есть запись второго Doc в Drive и карту договоров; утверждение
    проекта §5.1 «тождество Doc прежнее» здесь неверно — названо). Флаг ВЫКЛ — прежние два одинаковых вызова имя+дата
    (мост дважды перегенерировал бы Doc первой строки)."""
    two = [crm_row(row=12, booking_id="bk-1"), crm_row(row=13, booking_id="bk-2")]
    b = Bridge(clients=two, make=OK_MAKE)
    km(b, on=True)
    assert b.args("make_contract") == [{"booking_id": "bk-1"}, {"booking_id": "bk-2"}], b.calls
    b = Bridge(clients=two, make=OK_MAKE)
    km(b, on=False)
    assert b.args("make_contract") == [{"name": NAME, "date_start": TODAY + " 10:00"}] * 2, b.calls


def test_g12_report_reads_off_the_event_loop():
    """13: отчёт о реестре (чтения моста) идёт в потоке, а не в цикле событий — и в задании, и в команде; слова те же."""
    import threading
    seen = []
    real = S._contract_ref_report

    def spy(*a, **k):
        seen.append(threading.get_ident())
        return real(*a, **k)
    S._contract_ref_report = spy
    try:
        lines = km(Bridge(clients=[crm_row()]), on=True)
        sends, ilines = intake("договор %s|%s|%s" % (BIKE, NAME, TODAY), Bridge(clients=[crm_row()]), on=True)
    finally:
        S._contract_ref_report = real
    loop_thread = threading.get_ident()                          # asyncio.run крутит цикл в этом же потоке
    assert len(seen) == 2 and loop_thread not in seen, (seen, loop_thread)
    assert len(ref_lines(lines)) == 1 and "подписанный договор этой брони: стр. 36" in ref_lines(lines)[0], lines
    assert "\n📄 Реестр по этой брони: в реестре есть подписанный договор" in sends[0], sends
    assert ilines[-1].startswith("  🆕 INTAKE: договор не сделан (no_passport) — реестр: в реестре есть"), ilines


def main():
    if PROBE:
        return probe_off()
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    try:
        for name, fn in tests:
            try:
                fn()
                print("PASS", name)
            except Exception as e:                                   # noqa: BLE001
                bad += 1
                print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    finally:
        flag(False)
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
