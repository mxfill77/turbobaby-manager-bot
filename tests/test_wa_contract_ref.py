#!/usr/bin/env python3
"""CONTRACTREF1510 · сторона wa-agent: сверка версий договора с реестром (проект §4, приёмка §8.2 A1–A14 + служба S*).

Проход подписи `wa_agent_attach.AttachCore` (параметр `ref_of` = `contract_ref.ref_of`) пишет последнее чтение реестра по
номеру в `contract_versions`; блок договора модели (`wa_agent_cstate` → `wa_contract_state`) меняет ТОЛЬКО строку версии:
действует ли версия по реестру и куда смотреть вместо неё. Служба (`wa_agent_svc.contract_ref_of`) засчитывает флаг
WA_AGENT_CONTRACT_REF только при засчитанном WA_AGENT_CONTRACT_STATE.

Стенды — те же, что у CSTATE1510 (`tests/test_wa_attach_cstate.py`: World — поддельная модель с НАСТОЯЩЕЙ дверью аренды,
Real — НАСТОЯЩИЙ адаптер со сверкой Т4а; `tests/test_wa_attach_casestate_accept.py`: svc — служба на подделках), с
синтетическими данными §8: номер 79990001122, байк «Honda PCX 160 1234», срок 2026-10-14…2026-10-20, строки 34/35/36,
doc 1AbCdEfDOC34…, имя «Тест Тестов». Реестр — подделка живой формы (`test_wa_signed_card.Registry`). Сети, моста,
Telegram и WhatsApp нет. Каждый отрицательный случай идёт с близнецом-проходом.

A15–A22 — находки критика после приёмки: снимок старше суток не применяется (1), версия прошлой аренды получает
указатель на текущую / ждущую (2), пустой статус — «неизвестен» (3), сбой записи — строка журнала один раз (8), пробелы
тестов (11: мост со счётчиком подключён к проходу в A13, сбой читателя, аренда не факт, порядок «строки, потом итог»,
REF_PEND_OTHER)."""
import ast
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

PROBE_ARG = "--probe-ref-off-imports"
PROBE_MARK = "CONTRACTREF_OFF_MODULES "
PROBE = PROBE_ARG in sys.argv[1:]

import wa_agent as A  # noqa: E402
import wa_agent_attach as X  # noqa: E402
import wa_agent_cstate as C  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_contract_state as CS  # noqa: E402
import test_wa_signed_card as SC  # noqa: E402  (живые форматы стенда подписи)
import test_wa_attach_cstate as CT  # noqa: E402  (стенды CSTATE1510: World, Real, Script)
import test_wa_attach_casestate_accept as CA  # noqa: E402  (служба на подделках: svc)

if not PROBE:                       # процесс пробы флага выкл (A1в) обязан начаться БЕЗ contract_ref в sys.modules
    import contract_ref as CR  # noqa: E402
    import test_contract_ref as TC  # noqa: E402  (синтетические строки реестра §8)

NUM = "79990001122"
NBH = chr(0x2011)
CONTACTS = "Тест Тестов +7 999 000%s11%s22" % (NBH, NBH)
BIKE = "Honda PCX 160 1234"
BOOKING = "bk-0042"
T_SIGN, T_START = SC.T_SIGN, SC.T_START
S34, S35, S36 = "2026-10-14 17:47", "2026-10-14 18:37", "2026-10-14 19:04"
PDF34 = SC.k3_pdf_fixture.classic(b"signed contract row 34 PCX 1234")
PDF35 = SC.k3_pdf_fixture.classic(b"signed contract row 35 PCX 1234")
PDF36 = SC.k3_pdf_fixture.classic(b"signed contract row 36 PCX 1234")
PDF36B = SC.k3_pdf_fixture.classic(b"signed contract row 36 PCX 1234 resigned")
SHA36 = hashlib.sha256(PDF36).hexdigest()
FILES = {"P34": (34, PDF34), "P35": (35, PDF35), "PDF36": (36, PDF36)}
REF_COLS = ["number", "doc_id", "row", "read_at", "outcome", "role", "status", "signed", "signed_at", "pdf_id",
            "booking_id", "reason"]
CORE_TABLES = ("drafts", "signed_cards", "contract_expect", "pdf_parts", "attach", "signed_asks", "card_out", "outbox")


def book_row():
    return {"booking_id": BOOKING, "bike": BIKE, "date_start": "2026-10-14", "date_end": "2026-10-20",
            "status": "В аренде", "auto_cancel": "", "contacts": CONTACTS, "price": 1500, "currency": "THB"}


def rows(*spec):
    """(строка, статус) → записи реестра живой формы: подписанные — со своим signed_at и PDF."""
    sig = {34: (S34, "P34"), 35: (S35, "P35"), 36: (S36, "PDF36"), 37: ("2026-10-14 21:30", "PDF37")}
    out = []
    for row, status in spec:
        sa, pdf = sig.get(row, ("", ""))
        if status in ("НОВЫЙ", "ОТПРАВЛЕН"):
            sa, pdf = "", ""
        out.append(TC.reg_row(row, status, sa, pdf))
    return out


def live():
    return rows((34, "ОТОЗВАН"), (35, "ОТОЗВАН"), (36, "ПОДПИСАН"))


class World(CT.World):
    """Стенд подписи CSTATE1510 (поддельная модель, НАСТОЯЩАЯ дверь аренды) с синтетикой §8; ref — ядру `ref_of`."""

    def __init__(self, ref=True, regrows=None, cstate=True, **kw):
        self.ref = ref
        CT.World.__init__(self, cstate=cstate, rows=live() if regrows is None else regrows, book=[book_row()], **kw)
        self.pdfs.files.update(FILES)

    def new_core(self):
        kw = dict(log=self.lines.append, clock=self.clock, attach=True, pdf_fetch=self.pdfs,
                  contract_find=self.registry, signed=self.signed, signed_lookback_h=self.lookback_h,
                  ask_of=X.ask_verdict_many if self.ask else None, autosend=self.autosend, cstate=self.cstate,
                  claim_of=CS.signed_claim if self.claim else None)
        if self.ref:
            kw["ref_of"] = CR.ref_of
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)

    def card(self, t=T_SIGN + 600, text="Подписал договор"):
        """Клиент пишет после подписи → такт → карточка подписи. → id черновика."""
        self.put(T_SIGN + 60, text, number=NUM)
        self.tick(t)
        got = self.signed_drafts()
        assert len(got) == 1, (got, self.lines[-8:])
        return got[0][0]

    def snap(self, number=NUM):
        if "contract_versions" not in self.tables():
            return None
        db = sqlite3.connect(self.dbpath)
        db.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in db.execute("SELECT * FROM contract_versions WHERE number=? ORDER BY doc_id, row",
                                                (number,)).fetchall()]
        finally:
            db.close()

    def head(self, number=NUM):
        got = [r for r in self.snap(number) or [] if r["doc_id"] == ""]
        return got[0] if got else None

    def core_state(self):
        out = {}
        have = self.tables()
        for t in CORE_TABLES:
            out[t] = self.q("SELECT * FROM %s ORDER BY rowid" % t) if t in have else None
        return out

    def vline(self, now=None, topic=True, number=NUM):
        """Строка версии блока с фактом «ref» (читатель с ref=True)."""
        now = self.clock.t if now is None else now
        f = C.read_facts(self.dbpath, number, now, ref=True)
        f["topic"] = topic
        b = CS.render(f, now)
        got = [ln for ln in (b or "").split("\n") if ln.startswith("• версия:")]
        return got[0][2:] if got else None, b, f

    def vline_off(self, now=None, topic=True, number=NUM):
        now = self.clock.t if now is None else now
        f = C.read_facts(self.dbpath, number, now)
        f["topic"] = topic
        b = CS.render(f, now)
        got = [ln for ln in (b or "").split("\n") if ln.startswith("• версия:")]
        return got[0][2:] if got else None, b, f


def twins(**kw):
    """Тот же стенд с флагом и без: (без флага, с флагом)."""
    return World(ref=False, **kw), World(ref=True, **kw)


def same_story(a, b):
    """Всё, кроме `contract_versions`, — равно: вызовы двери, черновики, версии, ожидание, части PDF, карточки."""
    sa, sb = a.core_state(), b.core_state()
    assert a.registry.calls == b.registry.calls, (a.registry.calls, b.registry.calls)
    for t in CORE_TABLES:
        assert sa[t] == sb[t], (t, sa[t], sb[t])
    assert a.door.sends == b.door.sends and a.door.media == b.door.media
    assert a.tables() | {"contract_versions"} == b.tables(), (a.tables(), b.tables())


# ═══ A1 · флаг ВЫКЛ — прежнее байт-в-байт ══════════════════════════════════════════════════════════════════════

def test_a01a_pass_without_ref_no_table_twin_only_table_differs():
    a, b = twins()
    assert a.core.ref_of is None and b.core.ref_of is CR.ref_of
    da, db = a.card(), b.card()
    assert "contract_versions" not in a.tables() and "contract_versions" in b.tables()
    for w, did in ((a, da), (b, db)):
        out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
        assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    same_story(a, b)
    assert b.head()["outcome"] == "current", b.snap()


def test_a01b_adapter_ref_off_ignores_filled_table():
    a, b = twins()
    a.card()
    b.card()
    assert b.head() is not None
    outs = []
    for w in (a, b):
        q = CT.Script(CT.final("Хорошо."))
        ad = C.ContractStateAdapter(w.qpath, q, book=w.book, clock=w.clock, agent_db=w.dbpath, log=lambda s: None,
                                    tools={"contract": w.registry, "contract_pdf": w.pdfs})
        assert ad.ref_on is False
        outs.append(ad.build(NUM, 10 ** 6, now=T_SIGN + 900))
    assert outs[0] == outs[1], (outs[0][1][:300], outs[1][1][:300])
    vl, _b, f = b.vline_off(T_SIGN + 900)
    assert "ref" not in f and "реестр" not in vl, vl
    assert C.read_facts(b.dbpath, NUM, T_SIGN + 900) == C.read_facts(a.dbpath, NUM, T_SIGN + 900)


def probe_off_imports():
    """Отдельный процесс: служба со всем CSTATE1510 (карточка подписи, состояние договора), флаг сверки НЕ запрошен."""
    core, lines, model, env = CA.svc(dict(CA.SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1"),
                                     C.ContractStateAdapter)
    tables = CA.tables(env["agent_db"])
    out = {"modules": sorted(m for m in ("contract_ref",) if m in sys.modules),
           "flag_lines": [ln for ln in lines if "WA_AGENT_CONTRACT_REF" in ln],
           "ref_of": getattr(core, "ref_of", "нет атрибута"), "ref_on": getattr(model, "ref_on", None),
           "cstate": bool(core.cstate), "table": "contract_versions" in tables, "expect": "contract_expect" in tables}
    sys.stdout.write(PROBE_MARK + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def test_a01c_service_without_flag_no_module_no_line_no_ref():
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                       timeout=300, env=dict(os.environ))
    text = p.stdout.decode("utf-8", "replace")
    got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
    assert p.returncode == 0 and len(got) == 1, (p.returncode, text[-1500:], p.stderr.decode("utf-8", "replace")[-1500:])
    out = json.loads(got[0][len(PROBE_MARK):])
    assert out == {"modules": [], "flag_lines": [], "ref_of": None, "ref_on": False, "cstate": True, "table": False,
                   "expect": True}, out


PINNED = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",
          "wa_agent_model.py": "868b0c4b3abd75d6f4fca6b1c7021d0f121db3ce",
          "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
          "wa_agent_knowledge.py": "d338a3c23fcfa7f8180a6ed75b38a93e6e4200d3",
          "rental_case.py": "3e3cba2f63461ae6fccf1a7d3f044da0c22cbca0"}


def _blob(path):
    data = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    return {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}, tree


def test_a01d_frozen_blobs_and_locks():
    for name, sha in PINNED.items():
        assert _blob(os.path.join(ROOT, name)) == sha, name
    assert dict(CT.FROZEN, **{"rental_case.py": PINNED["rental_case.py"]}) == PINNED
    assert hashlib.sha256(T.TOOLS_BLOCK.encode("utf-8")).hexdigest() == CA.TOOLS_BLOCK_SHA
    imp, _t = _imports(X.__file__)
    assert imp == {"base64", "hashlib", "re", "zlib", "wa_agent", "wa_agent_tools"}, imp
    imp, tree = _imports(CS.__file__)
    assert imp <= {"re", "datetime"}, imp
    bad = {"open", "exec", "eval", "__import__", "input", "os", "sys", "socket", "sqlite3", "subprocess", "time"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & bad, names & bad
    params = list(X.AttachCore.__init__.__code__.co_varnames[:X.AttachCore.__init__.__code__.co_argcount +
                                                               X.AttachCore.__init__.__code__.co_kwonlyargcount])
    assert "ref_of" in params and not [p for p in params if "rental" in p], params
    assert "build_followup" not in C.ContractStateAdapter.__dict__
    import inspect
    sig = inspect.signature(S.make_model)
    assert sig.parameters["cstate"].default is False, sig
    assert X.AttachCore.__init__.__kwdefaults__["ref_of"] is None and X.AttachCore.__init__.__kwdefaults__["cstate"] is False


# ═══ A2 · служба: флаг засчитан только при засчитанном состоянии договора ═══════════════════════════════════════════

NOT_COUNTED = ("сверка версий договора (WA_AGENT_CONTRACT_REF): не засчитан — флаг 1, но состояние договора для модели "
               "(WA_AGENT_CONTRACT_STATE) не засчитано: сверки версий нет")
ON_WORDS = ("сверка версий договора (WA_AGENT_CONTRACT_REF): вкл — проход подписи пишет последнее чтение реестра по номеру "
            "(contract_versions: doc_id, строка, статус, подписан, PDF — без имён и телефонов); строка версии в блоке "
            "договора модели говорит, действует ли версия по реестру, и называет текущую или ждущую подписи; PDF, "
            "карточки и отправка — как прежде")


def test_a02_service_counted_only_with_contract_state():
    for env in (dict(CA.SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_REF="1"),
                dict(CA.SVC_ON, WA_AGENT_CONTRACT_STATE="1", WA_AGENT_CONTRACT_REF="1")):
        core, lines, m, e = CA.svc(env, C.ContractStateAdapter)
        said = [ln for ln in lines if "WA_AGENT_CONTRACT_REF" in ln]
        assert said == [NOT_COUNTED], said
        assert "contract_versions" not in CA.tables(e["agent_db"]) and m.ref_on is False
        assert getattr(core, "ref_of", None) is None
    core, lines, m, e = CA.svc(dict(CA.SVC_ON, WA_AGENT_SIGNED_CARD="1", WA_AGENT_CONTRACT_STATE="1",
                                    WA_AGENT_CONTRACT_REF="1"), C.ContractStateAdapter)
    said = [ln for ln in lines if "WA_AGENT_CONTRACT_REF" in ln]
    assert said == [ON_WORDS], said
    assert "contract_versions" in CA.tables(e["agent_db"]) and m.ref_on is True and core.ref_of is CR.ref_of


def test_s01_constants_and_flag_rule():
    assert S.F_CONTRACT_REF == X.F_CONTRACT_REF == "WA_AGENT_CONTRACT_REF"
    assert S.F_CONTRACT_REF not in S.FLAGS
    m = types.SimpleNamespace(ref_on=False)
    for env in ({}, {"WA_AGENT_CONTRACT_REF": "0"}, {"WA_AGENT_CONTRACT_REF": ""}, {"WA_AGENT_CONTRACT_REF": "nope"}):
        assert S.contract_ref_of(env, True, m) == (None, None, None) and m.ref_on is False, env
    for v in ("1", "true", "yes", "on", "ON", " True "):
        got = S.contract_ref_of({"WA_AGENT_CONTRACT_REF": v}, True, types.SimpleNamespace(ref_on=False))
        assert got[0] is True and got[1] == {"ref_of": CR.ref_of}, (v, got)
    for ok in (False, None, 1, "1"):
        got = S.contract_ref_of({"WA_AGENT_CONTRACT_REF": "1"}, ok, m)
        assert got[:2] == (False, None) and got[2].startswith("не засчитан — флаг 1, но состояние договора"), got
        assert m.ref_on is False
    saved = sys.modules.get("contract_ref")
    sys.modules["contract_ref"] = None                   # модуль не собран: import падает ImportError
    try:
        got = S.contract_ref_of({"WA_AGENT_CONTRACT_REF": "1"}, True, m)
    finally:
        sys.modules["contract_ref"] = saved
    assert got == (False, None, "не засчитан — модуль сверки версий не собран (ModuleNotFoundError)"), got
    assert m.ref_on is False


def test_s02_core_ref_of_needs_cstate():
    w = World(ref=True, cstate=False)
    assert w.core.ref_of is None and "contract_versions" not in w.tables()
    w2 = World(ref=False)
    assert w2.core.ref_of is None and "contract_versions" not in w2.tables()
    core = X.AttachCore(w2.dbpath, w2.qpath, w2.model, w2.tg, w2.door, log=w2.lines.append, clock=w2.clock,
                        attach=True, pdf_fetch=w2.pdfs, contract_find=w2.registry, signed=True, cstate=True,
                        claim_of=CS.signed_claim, ref_of="не функция")
    assert core.ref_of is None


# ═══ A3 · снимок последнего чтения: колонки, данные, dedup ═════════════════════════════════════════════════════════

T2 = T_SIGN + 600 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5          # проход после паузы «решено» (то же входящее)


def test_a03_snapshot_shape_and_dedup():
    w = World()
    w.card()
    db = sqlite3.connect(w.dbpath)
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(contract_versions)").fetchall()]
    finally:
        db.close()
    assert cols == REF_COLS, cols
    snap = w.snap()
    head = w.head()
    assert head["outcome"] == "current" and head["role"] == X.REF_SUMMARY and head["row"] == 0, head
    assert head["status"] is None and head["signed"] is None and head["booking_id"] == BOOKING, head
    assert head["read_at"] == T_SIGN + 600 and head["reason"] == "текущий — стр. 36", head
    body = {r["row"]: r for r in snap if r["doc_id"]}
    assert set(body) == {34, 35, 36}, snap
    assert body[36]["role"] == "current" and body[36]["signed"] == 1 and body[36]["pdf_id"] == "PDF36", body[36]
    assert body[34]["role"] == body[35]["role"] == "superseded" and body[34]["signed"] == 0, body
    assert all(r["read_at"] == head["read_at"] and r["reason"] is None for r in body.values())
    text = repr([{k: v for k, v in r.items() if k != "number"} for r in snap])
    for bad in ("Тест", "990001122", NUM, "@", "Honda", "PCX", "1234", "2026-10-15"):   # 2026-10-15 — день договора
        assert bad not in text, (bad, text)
    w.tick(T2)                                                   # второе такое же чтение
    snap2 = w.snap()
    assert len(snap2) == len(snap) == 4, snap2
    assert w.head()["read_at"] == T2 and all(r["read_at"] == T2 for r in snap2), snap2
    assert len(w.registry.calls) == 2 and len(w.signed_drafts()) == 1, (w.registry.calls, w.signed_drafts())
    w.registry.rows[:] = rows((36, "ПОДПИСАН"))                   # чтение без 34/35: их строки остаются со старым read_at
    w.tick(T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
    t3 = w.head()["read_at"]
    assert t3 > T2 and len(w.snap()) == 4, w.snap()
    ref = C.read_facts(w.dbpath, NUM, t3 + 1, ref=True)["ref"]
    assert [it["row"] for it in ref["items"]] == [36] and ref["local_row"] == 36, ref


# ═══ A4 · реестр не прочитан — «неизвестно», а не «договора нет» ═══════════════════════════════════════════════════

def _unknown_case(fail):
    a, b = twins()
    for w in (a, b):
        w.card()
        fail(w.registry)
        w.tick(T2)
    return a, b


def test_a04_unread_registry_is_unknown_in_snapshot_and_line():
    for name, fail in (("timeout", lambda r: setattr(r, "fail", T.last9(NUM))),
                       ("card_deadline", lambda r: setattr(r, "deadline", 1))):
        a, b = _unknown_case(fail)
        same_story(a, b)
        head = b.head()
        assert head["outcome"] == "unknown" and head["read_at"] == T2, (name, head)
        assert head["reason"].startswith("реестр не прочитан: "), head
        assert ("door:TimeoutError" if name == "timeout" else "card_deadline") in head["reason"], head
        assert not [r for r in b.snap() if r["doc_id"] and r["read_at"] == T2], b.snap()
        vl, _blk, _f = b.vline(T2 + 60)
        assert vl == "версия: подписан 14.10 19:04 · doc …fDOC36 · реестр 19:26: не прочитан — статус неизвестен", vl
        assert "НЕ текущая" not in vl and "подписанного в сроке аренды нет" not in vl
        assert b.vline_off(T2 + 60)[0] == a.vline_off(T2 + 60)[0] == \
            "версия: подписан 14.10 19:04 · doc …fDOC36 · карточка подписи"
        # близнец: следующее чтение удалось — версия действует
        b.registry.fail, b.registry.deadline = None, 0
        t = T2 + X.SIGNED_RETRY[1] + X.SIGNED_EVERY + 5
        b.tick(t)
        if b.head()["outcome"] != "current":                     # пауза сбоя подряд могла быть длиннее шага
            t = T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
            b.tick(t)
        assert b.head()["outcome"] == "current", (name, b.head(), b.lines[-5:])
        vl, _blk, _f = b.vline(t + 60)
        assert vl.endswith(": действует") and vl.startswith("версия: подписан 14.10 19:04 · doc …fDOC36 · реестр "), vl


# ═══ A5 · отозванная локальная версия и ждущая подписи новая ═══════════════════════════════════════════════════════

def _check_block(b):
    lines = b.split("\n")
    assert len(lines) <= CS.BLOCK_LINES and len(b) <= CS.BLOCK_CHARS, (len(lines), len(b))
    assert all(len(ln) <= CS.LINE_MAX + 2 for ln in lines[1:]), [len(x) for x in lines]
    for d in CT.DATE_ANY.findall(b):
        assert CT.re.fullmatch(r"\d{2}\.\d{2}", d), (d, b)
    assert not CT.re.search(r"\d{9,}", b) and "2026" not in b, b
    assert CT.K.money_claims(b, None) == [] and T.money_claims(b, None, set()) == [], b
    for bad in ("Тест", "Honda", "PCX", "1234", "1AbCdEf", "P34", "PDF36", "стр."):
        assert bad not in b, (bad, b)


def test_a05_revoked_local_version_points_to_pending_new():
    w = World(regrows=rows((34, "ПОДПИСАН")))
    w.card()
    vl, b, _f = w.vline(T_SIGN + 700)
    assert vl == "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:14: действует", vl
    w.registry.revoke(34)
    w.registry.rows.append(TC.reg_row(36, "ОТПРАВЛЕН"))
    w.tick(T2)
    assert w.head()["outcome"] == "pending", w.head()
    vl, b, _f = w.vline(T2 + 60)
    assert vl == ("версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:26: ОТОЗВАН — НЕ текущая; новая doc …fDOC36 "
                  "ждёт подписи (ОТПРАВЛЕН)"), vl
    assert len(vl) <= CS.LINE_MAX, len(vl)
    _check_block(b)
    # тот же снимок — в запросе настоящего адаптера (ref_on), и прежний вызов без него
    for on in (True, False):
        ad = C.ContractStateAdapter(w.qpath, CT.Script(CT.final("Хорошо.")), book=w.book, clock=w.clock,
                                    agent_db=w.dbpath, log=lambda s: None,
                                    tools={"contract": w.registry, "contract_pdf": w.pdfs})
        ad.ref_on = on
        _s, user, _i = ad.build(NUM, 10 ** 6, now=T2 + 60)
        blk = CT.block_of(user)
        assert blk is not None and (("• " + vl) in blk) == on, (on, blk)
        if not on:
            assert "• версия: подписан 14.10 17:47 · doc …fDOC34 · карточка подписи" in blk, blk
    # «НОВЫЙ» — не отправлена на подпись; ждущих две — «и ещё 1»
    w.registry.rows.append(TC.reg_row(37, "НОВЫЙ"))
    t = T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
    w.tick(t)
    vl, b, f = w.vline(t + 60)
    full = CS._version_line(f["version"], t + 60, f["ref"])
    assert full.endswith("ОТОЗВАН — НЕ текущая; новая doc …fDOC37 не отправлена на подпись (НОВЫЙ) и ещё 1"), full
    # длинная строка режется прежним `_cut` с конца: V стоит раньше указателя и остаётся
    assert len(full) > CS.LINE_MAX and vl == CS._cut(full) and len(vl) <= CS.LINE_MAX and vl.endswith("…"), vl
    assert "ОТОЗВАН — НЕ текущая; новая doc …fDOC37" in vl
    _check_block(b)


def test_a05b_typical_lines_fit_and_same_version_twin():
    """Длины типичных строк §4.3 (123 · 115 · 123 знака — все ≤ LINE_MAX) и правило «одна версия» блока = contract_ref."""
    now = SC.phuket(2026, 10, 14, 19, 30)
    v = {"signed_at": S34, "doc": doc_id(34), "file_id": "P34", "src": "card", "draft_id": 1, "decided_at": now - 3000,
         "date_to": "2026-10-20"}
    it34 = {"doc_id": doc_id(34), "row": 34, "role": "superseded", "status": "ОТОЗВАН", "signed": False,
            "signed_at": S34, "pdf_id": "P34"}
    it36p = {"doc_id": doc_id(36), "row": 36, "role": "pending", "status": "ОТПРАВЛЕН", "signed": False,
             "signed_at": "", "pdf_id": ""}
    it36c = dict(it36p, role="current", status="ПОДПИСАН", signed=True, signed_at=S36, pdf_id="PDF36")
    ref_p = {"read_at": now - 60, "outcome": "pending", "reason": "", "local_row": 34, "items": [it36p, it34]}
    ref_c = dict(ref_p, outcome="current", items=[it36c, it34])
    got = [CS._version_line(v, now, ref_p), CS._version_line(v, now, ref_c),
           CS._version_line(dict(v, signed_at="2026-10-13 17:47"), now, ref_c)]
    assert got == [
        "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:29: ОТОЗВАН — НЕ текущая; новая doc …fDOC36 ждёт "
        "подписи (ОТПРАВЛЕН)",
        "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:29: ОТОЗВАН — НЕ текущая; текущая doc …fDOC36 от "
        "14.10 19:04",
        "версия: подписан 13.10 17:47 · doc …fDOC34 · реестр 19:29: ОТОЗВАН — НЕ текущая · вчера; текущая doc …fDOC36 "
        "от 14.10 19:04"], got
    assert [len(x) for x in got] == [123, 115, 123] and all(len(x) <= CS.LINE_MAX for x in got)
    # B: локальной версии нет — каждый исход реестра своими словами
    head = "версия: в базе нет (карточки подписи и сверки ответов) · реестр 19:29: "
    for ref, q in ((ref_c, "подписан doc …fDOC36 от 14.10 19:04"), (ref_p, "doc …fDOC36 ждёт подписи (ОТПРАВЛЕН)"),
                   (dict(ref_p, outcome="ambiguous"), "подписанных несколько — выбор за человеком"),
                   (dict(ref_p, outcome="incomplete"), "прочитан не целиком — выбор за человеком"),
                   (dict(ref_p, outcome="none"), "подписанного в сроке аренды нет"),
                   (dict(ref_p, outcome="unknown", items=[]), "не прочитан — неизвестно, а не «договора нет»")):
        assert CS._version_line(None, now, ref) == head + q, (ref["outcome"], CS._version_line(None, now, ref))
    # A: строка этой версии в чтении — по каждому состоянию (§4.3, таблица V)
    base = "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:29: "
    cases = ((dict(ref_c, items=[it36c]), "этой строки в чтении нет — статус неизвестен"),
             (dict(ref_c, local_row=33), "строка не однозначна — статус неизвестен"),
             (dict(ref_c, local_row=None, items=[it36c, it34, dict(it34, row=33)]),
              "строка не однозначна — статус неизвестен"),
             (dict(ref_c, items=[it36c, dict(it34, role="unchecked")]), "привязка не сверена — статус неизвестен"),
             (dict(ref_c, outcome="ambiguous", items=[dict(it34, role="signed", status="ПОДПИСАН", signed=True)]),
              "подписанных несколько — выбор за человеком"),
             (dict(ref_c, outcome="incomplete", items=[dict(it34, role="signed", status="ПОДПИСАН", signed=True)]),
              "прочитан не целиком — выбор за человеком"),
             (dict(ref_c, items=[dict(it34, role="current", status="ПОДПИСАН", signed=True)]), "действует"),
             (dict(ref_p, outcome="none"), "ОТОЗВАН — НЕ текущая; подписанного в сроке аренды нет"),
             (dict(ref_p, outcome="ambiguous"), "ОТОЗВАН — НЕ текущая; подписанных несколько — выбор за человеком"),
             (dict(ref_p, outcome="incomplete"), "ОТОЗВАН — НЕ текущая; прочитан не целиком — выбор за человеком"))
    for ref, tail_words in cases:
        assert CS._version_line(v, now, ref) == base + tail_words, (tail_words, CS._version_line(v, now, ref))
    # одна версия: блок (свой помощник — замок импортов) и contract_ref судят одинаково
    a = {"doc_id": doc_id(36), "signed_at": S36, "pdf_id": "PDF36"}
    for loc in ({"doc": doc_id(36), "signed_at": S36, "file_id": "PDF36"},
                {"doc": " %s " % doc_id(36), "signed_at": S36, "file_id": "PDF36"},
                {"doc": doc_id(36), "signed_at": "2026-10-15 09:10", "file_id": "PDF36"},
                {"doc": doc_id(36), "signed_at": S36, "file_id": ""}, {"doc": "", "signed_at": S36, "file_id": "PDF36"}):
        twin = {"doc_id": loc["doc"], "signed_at": loc["signed_at"], "file_id": loc["file_id"]}
        assert CS._ref_same(a, loc) == CR.same_version(a, twin), loc


# ═══ A6 · снимок старше решения версии — строка прежняя ═══════════════════════════════════════════════════════════

def test_a06_snapshot_older_than_version_keeps_old_line():
    w = World()
    w.card()
    old = w.vline_off(T_SIGN + 700)[0]
    assert old == "версия: подписан 14.10 19:04 · doc …fDOC36 · карточка подписи", old
    assert w.vline(T_SIGN + 700)[0] == "версия: подписан 14.10 19:04 · doc …fDOC36 · реестр 19:14: действует"
    w.x("UPDATE contract_versions SET read_at=read_at-30 WHERE number=?", (NUM,))   # чтение — раньше решения версии
    assert w.vline(T_SIGN + 700)[0] == old
    now = T_SIGN + 700
    ver = {"signed_at": S36, "doc": doc_id(36), "file_id": "PDF36", "src": "card", "draft_id": 1, "decided_at": now - 100,
           "date_to": "2026-10-20"}
    ref = {"read_at": now - 101, "outcome": "pending", "reason": "", "local_row": 36,
           "items": [{"doc_id": doc_id(36), "row": 36, "role": "superseded", "status": "ОТОЗВАН", "signed": False,
                      "signed_at": S36, "pdf_id": "PDF36"}]}
    base = CS._version_line(ver, now)
    assert CS._version_line(ver, now, ref) == base == "версия: подписан 14.10 19:04 · doc …fDOC36 · карточка подписи"
    for bad in (None, {"unknown": "сбой"}, dict(ref, read_at=None), dict(ref, read_at="x")):
        assert CS._version_line(ver, now, bad) == base, bad
    assert CS._version_line(dict(ver, decided_at=None), now, ref) == base
    assert CS._version_line({"unknown": "нет таблиц"}, now, ref) == "версия: неизвестно (нет таблиц)"
    new = CS._version_line(ver, now, dict(ref, read_at=now - 100))   # равное время — уже применим
    assert new == "версия: подписан 14.10 19:04 · doc …fDOC36 · реестр 19:14: ОТОЗВАН — НЕ текущая", new


def doc_id(row):
    return TC.doc(row)


# ═══ A7 · переподпись того же doc ═════════════════════════════════════════════════════════════════════════════════

def test_a07_resigned_same_doc_named_not_current_no_pointer():
    w = World()
    w.card()
    assert w.vline(T_SIGN + 700)[0].endswith(": действует")
    r36 = [r for r in w.registry.rows if r["row"] == 36][0]
    r36.update(signed_at="2026-10-15 09:10", pdf_id="PDF36B")       # PDF новой версии ещё не читается — карточки нет
    w.tick(T2)
    assert w.head()["outcome"] == "current" and len(w.signed_drafts()) == 1, (w.head(), w.signed_drafts())
    vl = w.vline(T2 + 60)[0]
    assert vl == "версия: подписан 14.10 19:04 · doc …fDOC36 · реестр 19:26: переподписан 15.10 09:10 — эта НЕ текущая", vl
    assert "текущая doc" not in vl and ";" not in vl
    r36.update(signed_at=S36, pdf_id="PDF36")                        # близнец: та же версия — действует
    t = T2 + X.SIGNED_RETRY[1] + X.SIGNED_EVERY + 5
    w.tick(t)
    if w.head()["read_at"] <= T2:
        t = T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
        w.tick(t)
    assert w.vline(t + 60)[0].endswith(": действует"), (w.vline(t + 60)[0], w.lines[-4:])


# ═══ A8 · локальной версии нет ═════════════════════════════════════════════════════════════════════════════════════

def test_a08_no_local_version_unknown_and_pending():
    a, b = twins(regrows=rows((36, "ОТПРАВЛЕН")))
    for w in (a, b):
        w.registry.fail = T.last9(NUM)
        w.put(T_SIGN + 60, "Подписал договор", number=NUM)
        w.tick(T_SIGN + 600)
    same_story(a, b)
    assert b.head()["outcome"] == "unknown"
    vl = b.vline(T_SIGN + 660)[0]
    assert vl == ("версия: в базе нет (карточки подписи и сверки ответов) · реестр 19:14: не прочитан — неизвестно, "
                  "а не «договора нет»"), vl
    for w in (a, b):
        w.registry.fail = None
        w.tick(T_SIGN + 600 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
    same_story(a, b)
    assert b.head()["outcome"] == "pending", b.head()
    t = b.head()["read_at"]
    vl, blk, _f = b.vline(t + 60)
    assert vl == ("версия: в базе нет (карточки подписи и сверки ответов) · реестр %s: doc …fDOC36 ждёт подписи "
                  "(ОТПРАВЛЕН)" % CS.when(t, t + 60)), vl
    _check_block(blk)
    assert a.vline_off(t + 60)[0] == b.vline_off(t + 60)[0] == "версия: в базе нет (карточки подписи и сверки ответов)"
    assert a.vline(t + 60)[0] == "версия: в базе нет (карточки подписи и сверки ответов)", "без флага снимка нет"


# ═══ A9 · PDF не старый при флаге ВКЛ ══════════════════════════════════════════════════════════════════════════════

MEDIA36 = (NUM, "document", X.PDF_MIME, "contract_36.pdf", SHA36)


def test_a09_revoked_basis_stale_then_new_card_and_model_pdf():
    w = World(regrows=rows((34, "ПОДПИСАН")))
    did = w.card()
    w.registry.revoke(34)
    w.registry.rows.append(TC.reg_row(36, "ПОДПИСАН", S36, "PDF36"))
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert w.door.sends == [] and w.door.media == [], (w.door.sends, w.door.media)
    st = w.q("SELECT state, reason FROM drafts WHERE id=?", (did,))[0]
    assert st[0] == A.STALE and st[1].startswith("устарело: основание PDF не подтверждено реестром"), (st, out)
    w.tick(T2)
    cards = w.signed_drafts()
    assert len(cards) == 2, cards
    att = w.attach(cards[-1][0])
    assert att[0] == "PDF36" and att[3] == SHA36 and att[5] == doc_id(36), att
    assert w.head()["outcome"] == "current" and w.door.sends == [], w.head()
    # модель сама сверяет договор: её ответ несёт PDF текущей версии, не старой
    r = Real(regrows=rows((34, "ОТОЗВАН"), (36, "ПОДПИСАН")))
    r.script = CT.Script(CT.tool("contract"), CT.tool("contract_pdf", file_id="PDF36"), CT.final("Вот ваш договор."))
    r.put(T_SIGN + 60, "Пришлите, пожалуйста, мой договор", number=NUM)
    r.tick(T_SIGN + 600)
    got = r.q("SELECT d.kind, a.file_id, a.sha256 FROM drafts d JOIN attach a ON a.draft_id=d.id ORDER BY d.id")
    assert got and got[0][1:] == ("PDF36", SHA36), got
    # близнец: реестр прежний — «Отправить» шлёт текст, затем PDF 34
    w2 = World(regrows=rows((34, "ПОДПИСАН")))
    did2 = w2.card()
    out = w2.core.press(did2, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    assert len(w2.door.sends) == 1 and w2.door.media == [(NUM, "document", X.PDF_MIME, "contract_34.pdf",
                                                          hashlib.sha256(PDF34).hexdigest())], w2.door.media


# ═══ A10 · ответ модели сохраняется ═══════════════════════════════════════════════════════════════════════════════

class Real(CT.Real):
    """НАСТОЯЩИЙ адаптер `ContractStateAdapter` со сверкой Т4а и ядро с `ref_of` — синтетика §8."""

    def __init__(self, regrows=None, ref=True, start=T_START, media="sent"):
        import tempfile
        d = tempfile.mkdtemp(prefix="wa_cref_t_")
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(CT.AT.QSCHEMA)
        q.commit()
        q.close()
        self.ref = ref
        self.clock = SC.Clock(start)
        self.book = SC.Book([book_row()])
        self.registry = SC.Registry(live() if regrows is None else regrows)
        self.registry.clock = self.clock
        self.pdfs = SC.Pdfs(dict(FILES))
        self.tg, self.door = CT.AT.FakeTG(), CT.AT.FakeDoor(media=media)
        self.lines, self.alines = [], []
        self.signed, self.lookback_h, self.cstate, self.ask = True, 6, True, True
        self.script = CT.Script(CT.final("Хорошо."))
        self.adapter = self.new_adapter()
        self.adapter.ref_on = ref
        self.core = self.new_core()
        self.core.tick(start)

    def new_core(self):
        kw = {"ref_of": CR.ref_of} if self.ref else {}
        return X.AttachCore(self.dbpath, self.qpath, self.adapter, self.tg, self.door, log=self.lines.append,
                            clock=self.clock, attach=True, pdf_fetch=self.pdfs, contract_find=self.registry,
                            signed=True, signed_lookback_h=6, ask_of=X.ask_verdict_many, cstate=True,
                            claim_of=CS.signed_claim, **kw)

    def put(self, ts, text, number=NUM):
        return SC.World.put(self, ts, text, number=number)


def _model_draft(regrows, answers):
    w = Real(regrows=regrows)
    w.script = CT.Script(*answers)
    w.put(T_SIGN + 60, "Пришлите, пожалуйста, мой договор")
    w.tick(T_SIGN + 600)
    got = w.q("SELECT id FROM drafts WHERE kind IS NULL OR kind<>? ORDER BY id", (X.KIND_SIGNED,))
    assert got, (w.lines[-8:], w.alines[-4:])
    return w, got[0][0]


def test_a10_model_answer_kept_text_goes_even_without_pdf():
    w, did = _model_draft(rows((35, "ПОДПИСАН"), (36, "ПОДПИСАН")),
                          (CT.tool("contract"), CT.final("Договор уточню и пришлю отдельно.")))
    att = w.q("SELECT file_id, reason FROM attach WHERE draft_id=?", (did,))
    assert att and att[0][0] is None and att[0][1], att
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and len(w.door.sends) == 1 and w.door.media == [], (out, w.door.sends)
    assert w.q("SELECT COUNT(*) FROM pdf_parts WHERE draft_id=?", (did,)) == [(0,)]
    assert w.head_outcome() == "ambiguous"
    # PDF отказан ПОСЛЕ текста: файл подменили между сверкой и нажатием — текст ушёл, PDF нет и названо почему
    w, did = _model_draft(rows((36, "ПОДПИСАН")), (CT.tool("contract"), CT.tool("contract_pdf", file_id="PDF36"),
                                                   CT.final("Вот ваш договор.")))
    assert w.q("SELECT file_id FROM attach WHERE draft_id=?", (did,)) == [("PDF36",)]
    w.pdfs.files["PDF36"] = (36, PDF36B)
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    part = w.q("SELECT state, reason FROM pdf_parts WHERE draft_id=?", (did,))
    assert out["ok"] and len(w.door.sends) == 1 and w.door.media == [], (out, w.door.media)
    assert part[0][0] == A.NOT_SENT and "sha256" in part[0][1], part
    assert w.q("SELECT state FROM drafts WHERE id=?", (did,)) == [(A.SENT,)]
    w, did = _model_draft(rows((36, "ПОДПИСАН")), (CT.tool("contract"), CT.tool("contract_pdf", file_id="PDF36"),
                                                   CT.final("Вот ваш договор.")))
    w.pdfs.files.pop("PDF36")                                        # contract_pdf больше не отдаёт файл
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    part = w.q("SELECT state, reason FROM pdf_parts WHERE draft_id=?", (did,))
    assert out["ok"] and len(w.door.sends) == 1 and part[0][0] == A.NOT_SENT and "contract_pdf" in part[0][1], part
    # близнец: годный PDF — обе части ушли
    w, did = _model_draft(rows((36, "ПОДПИСАН")), (CT.tool("contract"), CT.tool("contract_pdf", file_id="PDF36"),
                                                   CT.final("Вот ваш договор.")))
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл" and w.door.media == [MEDIA36], (out, w.door.media)


def _head_outcome(self):
    db = sqlite3.connect(self.dbpath)
    try:
        got = db.execute("SELECT outcome FROM contract_versions WHERE number=? AND doc_id='' AND row=0",
                         (NUM,)).fetchall()
    finally:
        db.close()
    return got[0][0] if got else None


Real.head_outcome = _head_outcome


# ═══ A11 · единственная подписанная строка — чужая ═════════════════════════════════════════════════════════════════

def test_a11_foreign_only_signed_never_pointed_local_in_it_named_foreign():
    w = World()
    w.card()
    r36 = [r for r in w.registry.rows if r["row"] == 36][0]
    r36["bike"] = "Honda PCX 160 5678"
    w.tick(T2)
    snap = {r["row"]: r for r in w.snap() if r["doc_id"]}
    assert snap[36]["role"] == "foreign" and w.head()["outcome"] == "none", (snap, w.head())
    vl = w.vline(T2 + 60)[0]
    assert vl == ("версия: подписан 14.10 19:04 · doc …fDOC36 · реестр 19:26: другой аренды — НЕ текущая; подписанного "
                  "в сроке аренды нет"), vl
    assert "текущая doc" not in vl
    # локальная версия — в другой строке (35): на чужую подписанную 36 указателя нет
    now = T_SIGN + 700
    ver = {"signed_at": S35, "doc": doc_id(35), "file_id": "P35", "src": "card", "draft_id": 1, "decided_at": now - 100}
    ref = {"read_at": now - 50, "outcome": "none", "reason": "", "local_row": 35, "items": [
        {"doc_id": doc_id(36), "row": 36, "role": "foreign", "status": "ПОДПИСАН", "signed": True, "signed_at": S36,
         "pdf_id": "PDF36"},
        {"doc_id": doc_id(35), "row": 35, "role": "superseded", "status": "ОТОЗВАН", "signed": False, "signed_at": S35,
         "pdf_id": "P35"}]}
    vl = CS._version_line(ver, now, ref)
    assert vl == ("версия: подписан 14.10 18:37 · doc …fDOC35 · реестр 19:14: ОТОЗВАН — НЕ текущая; подписанного в "
                  "сроке аренды нет"), vl
    assert "fDOC36" not in vl
    # близнец: байк тот же — действует
    r36["bike"] = BIKE
    t = T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
    w.tick(t)
    assert w.vline(t + 60)[0].endswith(": действует"), w.vline(t + 60)[0]


# ═══ A12 · дедуп карточек при флаге ВКЛ ════════════════════════════════════════════════════════════════════════════

def test_a12_cards_dedup_and_resign_second_card_same_as_without_flag():
    a, b = twins()
    for w in (a, b):
        w.pdfs.files["PDF36B"] = (36, PDF36B)
        w.card()
        w.tick(T2)
        w.tick(T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
        assert len(w.versions()) == 1 and len(w.signed_drafts()) == 1, (w.versions(), w.signed_drafts())
    same_story(a, b)
    t = T2 + 2 * (X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
    for w in (a, b):
        r36 = [r for r in w.registry.rows if r["row"] == 36][0]
        r36.update(signed_at="2026-10-15 09:10", pdf_id="PDF36B")
        w.tick(t)
        vers = w.versions()
        assert len(vers) == 2 and vers[0][2] == S36 and vers[1][2] == "2026-10-15 09:10", vers
        assert len(w.signed_drafts()) == 2, w.signed_drafts()
        w.tick(t + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
        assert len(w.versions()) == 2 and len(w.signed_drafts()) == 2
    same_story(a, b)
    vl = b.vline(t + X.SIGNED_IDLE + X.SIGNED_EVERY + 65)[0]
    assert vl.startswith("версия: подписан 15.10 09:10 · doc …fDOC36 · реестр ") and vl.endswith(": действует"), vl


# ═══ A13 · make_contract не зовётся никогда ════════════════════════════════════════════════════════════════════════

class CountingBridge:
    """Поддельный мост: считает вызовы ВСЕХ методов; чтение отвечает «нет данных», запись — счётчиком."""

    def __init__(self):
        self.calls = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*a, **k):
            self.calls[name] = self.calls.get(name, 0) + 1
            return {"ok": False, "error": "стенд"}
        return call


class LiveBridge:
    """Мост, через который ИДЁТ проход подписи (находка критика 11: прежний счётчик к проходу подключён не был):
    contract_find / contract_pdf — живые подделки стенда, любой другой метод — счётчик и отказ. Двери ядра — его
    связанные методы, как у службы (`tools["contract"] = bridge.contract_find`)."""

    def __init__(self, world):
        self.world, self.calls = world, {}

    def _n(self, name):
        self.calls[name] = self.calls.get(name, 0) + 1

    def contract_find(self, *a, **k):
        self._n("contract_find")
        return self.world.registry(*a, **k)

    def contract_pdf(self, *a, **k):
        self._n("contract_pdf")
        return self.world.pdfs(*a, **k)

    def __getattr__(self, name):
        if name.startswith("__") or name in ("world", "calls"):
            raise AttributeError(name)

        def call(*a, **k):
            self._n(name)
            return {"ok": False, "error": "стенд"}
        return call


class BridgedWorld(World):
    """Стенд, у которого двери ядра — методы `LiveBridge` (проход подписи и нажатие ходят через «мост»)."""

    def new_core(self):
        if getattr(self, "bridge", None) is None:
            self.bridge = LiveBridge(self)
        kw = dict(log=self.lines.append, clock=self.clock, attach=True, pdf_fetch=self.bridge.contract_pdf,
                  contract_find=self.bridge.contract_find, signed=self.signed, signed_lookback_h=self.lookback_h,
                  ask_of=X.ask_verdict_many if self.ask else None, autosend=self.autosend, cstate=self.cstate,
                  claim_of=CS.signed_claim if self.claim else None)
        if self.ref:
            kw["ref_of"] = CR.ref_of
        return X.AttachCore(self.dbpath, self.qpath, self.model, self.tg, self.door, **kw)


def test_a13_no_make_contract_names_and_zero_calls():
    for mod in (X, C, CS, S, CR):
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & {"make_contract", "save_passport", "ocr_passport"}, (mod.__name__, names)
    import tempfile
    d = tempfile.mkdtemp(prefix="wa_cref_bridge_")
    bridge = CountingBridge()
    model, _why = S.make_model({"queue_db": os.path.join(d, "q.db"), "agent_db": os.path.join(d, "a.db")},
                               bridge=bridge, call=lambda s, u: ("", {}), tools=True, book=True, cstate=True)
    assert type(model).__name__ == "ContractStateAdapter", type(model)
    for doors in (model.tools,):
        for name in ("contract", "contract_pdf"):
            doors[name](**({"file_id": "PDF36"} if name == "contract_pdf" else {"phone": NUM}))
    assert bridge.calls == {"contract_find": 1, "contract_pdf": 1}, bridge.calls
    # проход подписи, нажатие «Отправить», повторное чтение и отзыв — ЧЕРЕЗ мост со счётчиком
    w = BridgedWorld()
    did = w.card()
    out = w.core.press(did, 1, A.ACT_SEND, "Даня", T_SIGN + 700)
    assert out["ok"] and out["words"] == "текст: ушёл · PDF: ушёл", out
    w.tick(T2)
    w.registry.revoke(36)
    w.tick(T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
    got = w.bridge.calls
    assert got.get("contract_find", 0) >= 3 and got.get("contract_pdf", 0) >= 1, ("проход шёл через мост", got)
    assert set(got) <= {"contract_find", "contract_pdf"}, ("ни одного иного метода моста", got)
    assert "make_contract" not in got and not [k for k in got if "passport" in k], got
    assert w.head()["outcome"] == "none", "снимок писался тем же проходом"


# ═══ A14 · сбой записи снимка ══════════════════════════════════════════════════════════════════════════════════════

class FailingDb:
    """База ядра, у которой запись в `contract_versions` падает; всё прочее — настоящая база."""

    def __init__(self, inner):
        self._inner = inner
        self.refused = 0

    def execute(self, sql, *args):
        if "INTO contract_versions" in sql:
            self.refused += 1
            raise sqlite3.OperationalError("database is locked")
        return self._inner.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_a14_snapshot_write_failure_one_line_pass_unchanged():
    a, b = twins()
    b.core.db = FailingDb(b.core.db)
    for w in (a, b):
        w.card()
    same_story(a, b)
    said = [ln for ln in b.lines if ln.startswith("сверка версий договора:")]
    assert said == [X.W_REF_NOT_SAVED % "OperationalError"], said
    assert said[0] == ("сверка версий договора: чтение реестра не записано (OperationalError) — блок модели скажет "
                       "прежнее")
    assert not [ln for ln in a.lines if "сверка версий" in ln]
    assert b.core.db.refused == 1 and b.head() is None
    assert b.vline(T_SIGN + 700)[0] == b.vline_off(T_SIGN + 700)[0], "снимка нет — строка прежняя"
    assert NUM not in said[0] and T.last9(NUM) not in said[0]


# ═══ находки критика CONTRACTREF1510 (правка после приёмки) ══════════════════════════════════════════════════════

NOW = SC.phuket(2026, 10, 14, 19, 30)
if not PROBE:                       # процесс пробы A1в не импортирует синтетику test_contract_ref (TC)
    IT36C = {"doc_id": doc_id(36), "row": 36, "role": "current", "status": "ПОДПИСАН", "signed": True,
             "signed_at": S36, "pdf_id": "PDF36"}
    IT36P = dict(IT36C, role="pending", status="ОТПРАВЛЕН", signed=False, signed_at="", pdf_id="")


def _ver(**over):
    v = {"signed_at": S34, "doc": doc_id(34), "file_id": "P34", "src": "card", "draft_id": 1, "decided_at": NOW - 3000,
         "date_to": "2026-10-20"}
    v.update(over)
    return v


def _ref(outcome, items, read_at=NOW - 60, local_row=None):
    return {"read_at": read_at, "outcome": outcome, "reason": "", "local_row": local_row, "items": items}


# ── 1 (important) · снимок старше суток — строка прежняя ─────────────────────────────────────────────────────────

def test_a15_stale_snapshot_not_applied_fresh_twin_applies():
    assert CS.REF_FRESH == A.FOLLOW_WINDOW == 24 * 3600, "срок снимка = окно 24 ч клиента"
    # форма A на стенде: тот же снимок на границе — применим, секундой позже — строка прежняя (с источником)
    w = World()
    w.card()
    t = w.head()["read_at"]
    edge = w.vline(t + CS.REF_FRESH)[0]
    assert edge.startswith("версия: подписан 14.10 19:04 · doc …fDOC36 · реестр ") and ": действует" in edge, edge
    old = w.vline_off(t + CS.REF_FRESH + 1)[0]
    assert old.startswith("версия: подписан 14.10 19:04 · doc …fDOC36 · карточка подписи"), old
    assert w.vline(t + CS.REF_FRESH + 1)[0] == old, w.vline(t + CS.REF_FRESH + 1)[0]
    # форма B (своей версии нет): снимку 2 суток — «в базе нет», а не чтение прошлой беседы; свежий — по реестру
    b = World(regrows=rows((36, "ОТПРАВЛЕН")))
    b.put(T_SIGN + 60, "Подписал договор", number=NUM)
    b.tick(T_SIGN + 600)
    assert b.head()["outcome"] == "pending", b.head()
    t = b.head()["read_at"]
    assert b.vline(t + 60)[0].endswith(": doc …fDOC36 ждёт подписи (ОТПРАВЛЕН)"), b.vline(t + 60)[0]
    assert b.vline(t + 2 * 86400)[0] == "версия: в базе нет (карточки подписи и сверки ответов)"
    # чистая функция: граница включительно; «сейчас» не число — свежесть неизвестна, строка прежняя
    v = _ver(decided_at=NOW - CS.REF_FRESH - 100)
    ref = _ref("current", [dict(IT36C, doc_id=doc_id(34), row=34, signed_at=S34, pdf_id="P34")],
               read_at=NOW - CS.REF_FRESH, local_row=34)
    assert CS._version_line(v, NOW, ref).endswith(": действует"), CS._version_line(v, NOW, ref)
    assert CS._version_line(v, NOW + 1, ref) == CS._version_line(v, NOW + 1)
    for bad_now in (None, "x", 0):
        assert CS._version_line(v, bad_now, ref) == CS._version_line(v, bad_now), bad_now
    assert CS._version_line(None, NOW + 1, dict(ref, local_row=None)) == \
        "версия: в базе нет (карточки подписи и сверки ответов)"


# ── 2 (important) · версия прошлой аренды: указатель на текущую / ждущую ────────────────────────────────────────

def test_a16_past_rental_version_points_to_current_or_pending():
    past = _ver(signed_at="2026-09-10 17:47", decided_at=NOW - 30 * 86400, date_to="2026-09-20")
    head = "версия: подписан 10.09 17:47 · doc …fDOC34 · реестр 19:29: прошлой аренды — НЕ текущая; "
    got = CS._version_line(past, NOW, _ref("current", [IT36C]))
    assert got == head + "текущая doc …fDOC36 от 14.10 19:04", got
    got = CS._version_line(past, NOW, _ref("pending", [IT36P]))
    assert got == head + "новая doc …fDOC36 ждёт подписи (ОТПРАВЛЕН)", got
    # давность влезает — идёт ПОСЛЕ указателя; не влезает — её нет (указатель цел, «…» не режет его)
    short = _ver(signed_at="2026-10-13 10:00", decided_at=NOW - 2 * 86400, date_to="2026-10-13")
    got = CS._version_line(short, NOW, _ref("current", [IT36C]))
    assert got == ("версия: подписан 13.10 10:00 · doc …fDOC34 · реестр 19:29: прошлой аренды — НЕ текущая; текущая "
                   "doc …fDOC36 от 14.10 19:04 · вчера"), got
    yday = CS._version_line(past, NOW, _ref("current", [IT36C], read_at=NOW - 20 * 3600))
    assert yday.endswith("текущая doc …fDOC36 от 14.10 19:04") and len(yday) <= CS.LINE_MAX, yday
    for full in (got, yday):
        assert CS._cut(full) == full
    # близнецы — строка проекта: срок аренды версии НЕ прошёл / неизвестен — «статус неизвестен» без указателя
    for v in (_ver(), _ver(date_to=None), _ver(date_to="не дата")):
        got = CS._version_line(v, NOW, _ref("current", [IT36C]))
        assert got == "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:29: этой строки в чтении нет — статус " \
                      "неизвестен", got
    # срок прошёл, но текущей / ждущей чтение не называет — указателя нет, «НЕ текущая» не говорится
    for out in ("none", "ambiguous", "incomplete"):
        got = CS._version_line(past, NOW, _ref(out, [dict(IT36C, role="signed")] if out != "none" else []))
        assert got.startswith("версия: подписан 10.09 17:47 · doc …fDOC34 · реестр 19:29: этой строки в чтении нет — "
                              "статус неизвестен · 34 сут назад"), (out, got)
        assert "НЕ текущая" not in got and "fDOC36" not in got, (out, got)
    got = CS._version_line(past, NOW, _ref("unknown", []))
    assert got.endswith("не прочитан — статус неизвестен · 34 сут назад, аренда этой версии закончилась"), got
    # строка версии в чтении ЕСТЬ (другой аренды) — прежнее правило проекта, не «прошлой аренды»
    got = CS._version_line(past, NOW, _ref("current", [IT36C, dict(IT36C, doc_id=doc_id(34), row=34, role="foreign")],
                                           local_row=34))
    assert "другой аренды — НЕ текущая" in got and "прошлой аренды" not in got, got


def test_a16b_past_rental_in_world_pending_then_current():
    """Стенд: версия 34 — аренда 14…20.10; через месяц новая аренда того же клиента, договор формы ждёт подписи, потом
    подписан (его PDF ещё не читается — своей версии нет). Строка версии называет новую, старая — «прошлой аренды»."""
    w = World(regrows=rows((34, "ПОДПИСАН")))
    w.card()
    assert w.vline(T_SIGN + 700)[0].endswith(": действует")
    later = T_SIGN + 31 * 86400                                       # 14.11 19:04
    w.book.rows[:] = [dict(book_row(), booking_id="bk-0043", date_start="2026-11-14", date_end="2026-11-20")]
    w.registry.rows.append(TC.reg_row(36, "ОТПРАВЛЕН", date="2026-11-14"))
    w.put(later - 300, "Подписал договор", number=NUM)
    w.tick(later)
    assert w.head()["outcome"] == "pending" and w.head()["read_at"] == later, (w.head(), w.lines[-6:])
    assert w.registry.calls[-1]["date_from"] == "2026-11-14", w.registry.calls[-1]
    vl, blk, f = w.vline(later + 60)
    assert f["version"]["doc"] == doc_id(34) and f["ref"]["items"][0]["row"] == 36, f
    assert vl == ("версия: подписан 14.10 17:47 · doc …fDOC34 · реестр %s: прошлой аренды — НЕ текущая; новая doc "
                  "…fDOC36 ждёт подписи (ОТПРАВЛЕН)" % CS.when(later, later + 60)), vl
    _check_block(blk)
    assert w.vline_off(later + 60)[0] == ("версия: подписан 14.10 17:47 · doc …fDOC34 · карточка подписи · 31 сут "
                                          "назад, аренда этой версии закончилась"), "без флага — прежняя строка"
    r36 = [r for r in w.registry.rows if r["row"] == 36][0]
    r36.update(status="ПОДПИСАН", signed=True, signed_at="2026-11-14 18:00", pdf_id="PDF36X")   # PDF не читается
    t = later + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
    w.tick(t)
    assert w.head()["outcome"] == "current" and len(w.versions()) == 1, (w.head(), w.versions())
    vl = w.vline(t + 60)[0]
    assert vl.endswith(": прошлой аренды — НЕ текущая; текущая doc …fDOC36 от 14.11 18:00"), vl


# ── 3 (minor) · пустой статус — «неизвестен», а не «НЕ текущая» ──────────────────────────────────────────────────

def test_a17_blank_status_is_unknown_not_dead():
    blank = dict(IT36C, doc_id=doc_id(34), row=34, role="other", status="", signed=False, signed_at=S34, pdf_id="P34")
    for st in ("", "   ", None):
        got = CS._version_line(_ver(), NOW, _ref("current", [IT36C, dict(blank, status=st)], local_row=34))
        assert got == "версия: подписан 14.10 17:47 · doc …fDOC34 · реестр 19:29: строка без статуса — статус неизвестен", got
    twin = CS._version_line(_ver(), NOW, _ref("current", [IT36C, dict(blank, status="ОТОЗВАН", role="superseded")],
                                              local_row=34))
    assert twin.endswith(": ОТОЗВАН — НЕ текущая; текущая doc …fDOC36 от 14.10 19:04"), twin
    # стенд: у строки реестра стёрт статус — снимок «other», строка версии «статус неизвестен»
    w = World(regrows=rows((34, "ПОДПИСАН")))
    w.card()
    r34 = [r for r in w.registry.rows if r["row"] == 34][0]
    r34.update(status="", signed=False)
    w.tick(T2)
    assert {r["row"]: r["role"] for r in w.snap() if r["doc_id"]} == {34: "other"}, w.snap()
    vl = w.vline(T2 + 60)[0]
    assert vl.endswith(": строка без статуса — статус неизвестен") and "НЕ текущая" not in vl, vl


# ── 11 · ждущая подписи с иным статусом (REF_PEND_OTHER) и нормализация статуса ──────────────────────────────────

def test_a18_pending_words_normalized_and_other_status():
    head = "версия: в базе нет (карточки подписи и сверки ответов) · реестр 19:29: doc …fDOC36 "
    for st, words in (("ОТПРАВЛЕН", "ждёт подписи (ОТПРАВЛЕН)"), (" отправлен ", "ждёт подписи (ОТПРАВЛЕН)"),
                      ("Новый", "не отправлена на подпись (НОВЫЙ)"), ("НА ПОДПИСИ", "ждёт подписи (НА ПОДПИСИ)")):
        got = CS._version_line(None, NOW, _ref("pending", [dict(IT36P, status=st)]))
        assert got == head + words, (st, got)
    assert CS.REF_PEND_OTHER % "НА ПОДПИСИ" == "ждёт подписи (НА ПОДПИСИ)"
    got = CS._version_line(_ver(), NOW, _ref("pending", [dict(IT36P, status="на подписи"),
                                                         dict(IT36C, doc_id=doc_id(34), row=34, role="superseded",
                                                              status="ОТОЗВАН", signed=False)], local_row=34))
    assert got.endswith("ОТОЗВАН — НЕ текущая; новая doc …fDOC36 ждёт подписи (на подписи)"), got


# ── 11 · сбой чтения снимка читателем блока — «неизвестно», строка прежняя ──────────────────────────────────────

def test_a19_reader_failure_is_unknown_and_block_unchanged():
    w = World()
    w.card()
    now = T_SIGN + 700
    assert w.vline(now)[0].endswith(": действует")
    off = w.vline_off(now)[0]
    w.x("ALTER TABLE contract_versions RENAME COLUMN outcome TO outcome_was")      # схема снимка сломана
    f_on, f_off = C.read_facts(w.dbpath, NUM, now, ref=True), C.read_facts(w.dbpath, NUM, now)
    assert f_on["ref"] == {"unknown": "сверка с реестром не прочитана: OperationalError"}, f_on["ref"]
    assert f_on["unread"] == f_off["unread"] and f_on["records"] == f_off["records"], (f_on, f_off)
    assert w.vline(now)[0] == off
    outs = []
    for on in (True, False):
        ad = C.ContractStateAdapter(w.qpath, CT.Script(CT.final("Хорошо.")), book=w.book, clock=w.clock,
                                    agent_db=w.dbpath, log=lambda s: None,
                                    tools={"contract": w.registry, "contract_pdf": w.pdfs})
        ad.ref_on = on
        outs.append(ad.build(NUM, 10 ** 6, now=now))
    assert outs[0] == outs[1], "адаптер не падает: блок как без сверки"


# ── 11 · аренда не факт — реестр не читается, снимок не пишется ──────────────────────────────────────────────────

def test_a20_rental_not_fact_nothing_read_nothing_written():
    a, b = twins()
    for w in (a, b):
        w.book.rows[:] = []
        w.put(T_SIGN + 60, "Подписал договор", number=NUM)
        w.tick(T_SIGN + 600)
        assert w.registry.calls == [] and w.signed_drafts() == [], (w.registry.calls, w.lines[-5:])
    same_story(a, b)
    assert "contract_versions" in b.tables() and b.snap() == [], b.snap()
    assert not [ln for ln in b.lines if ln.startswith("сверка версий договора")]
    c = World()                                                      # близнец: аренда есть — чтение и снимок
    c.card()
    assert c.head() is not None and len(c.registry.calls) == 1


# ── 11 · порядок записи: строки, потом итог; обрыв на итоге не объявляет новое чтение ──────────────────────────

class RecordingDb:
    """База ядра, записывающая SQL вставок в `contract_versions`; fail_at — номер вставки, на которой запись падает."""

    def __init__(self, inner, fail_at=None):
        self._inner, self.sql, self.fail_at = inner, [], fail_at

    def execute(self, sql, *args):
        if "INTO contract_versions" in sql:
            self.sql.append(sql)
            if self.fail_at is not None and len(self.sql) == self.fail_at:
                raise sqlite3.OperationalError("disk I/O error")
        return self._inner.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._inner, name)


SUMMARY_SQL = "VALUES(?,'',0,"


def test_a21_rows_first_summary_last_crash_keeps_previous_reading():
    w = World()
    w.core.db = RecordingDb(w.core.db)
    w.card()
    sql = w.core.db.sql
    assert len(sql) == 4 and SUMMARY_SQL in sql[-1] and not [s for s in sql[:-1] if SUMMARY_SQL in s], sql
    head1 = w.head()
    # следующее чтение обрывается на ПОСЛЕДНЕЙ вставке (итог): итог прежний — новое чтение не объявлено
    w.core.db = RecordingDb(w.core.db._inner, fail_at=4)
    w.registry.revoke(36)
    w.tick(T2)
    assert len(w.core.db.sql) == 4, w.core.db.sql
    head2 = w.head()
    assert (head2["read_at"], head2["outcome"]) == (head1["read_at"], "current"), (head1, head2)
    vl = w.vline(T2 + 60)[0]
    assert vl.endswith(": этой строки в чтении нет — статус неизвестен") and "НЕ текущая" not in vl, vl
    said = [ln for ln in w.lines if ln.startswith("сверка версий договора:")]
    assert said == [X.W_REF_NOT_SAVED % "OperationalError"], said
    # близнец: следующее чтение без обрыва — итог новый, строка по нему
    w.core.db = w.core.db._inner
    t = T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5
    w.tick(t)
    assert w.head()["outcome"] == "none" and w.head()["read_at"] == t, w.head()
    assert w.vline(t + 60)[0].endswith(": ОТОЗВАН — НЕ текущая; подписанного в сроке аренды нет"), w.vline(t + 60)[0]


# ── 8 (minor) · сбой записи — строка журнала один раз на процесс и имя ошибки ────────────────────────────────────

class FailingDbAs(FailingDb):
    def __init__(self, inner, exc):
        FailingDb.__init__(self, inner)
        self.exc = exc

    def execute(self, sql, *args):
        if "INTO contract_versions" in sql:
            self.refused += 1
            raise self.exc("стенд")
        return self._inner.execute(sql, *args)


def test_a22_write_failure_logged_once_per_error_name():
    w = World()
    w.core.db = FailingDb(w.core.db)
    w.card()
    w.tick(T2)
    said = [ln for ln in w.lines if ln.startswith("сверка версий договора:")]
    assert said == [X.W_REF_NOT_SAVED % "OperationalError"] and w.core.db.refused == 2, (said, w.core.db.refused)
    inner = w.core.db._inner
    w.core.db = FailingDbAs(inner, sqlite3.IntegrityError)
    w.tick(T2 + X.SIGNED_IDLE + X.SIGNED_EVERY + 5)
    w.tick(T2 + 2 * (X.SIGNED_IDLE + X.SIGNED_EVERY + 5))
    said = [ln for ln in w.lines if ln.startswith("сверка версий договора:")]
    assert said == [X.W_REF_NOT_SAVED % "OperationalError", X.W_REF_NOT_SAVED % "IntegrityError"], said
    assert w.core.db.refused == 2 and len(w.signed_drafts()) == 1, (w.core.db.refused, w.signed_drafts())


def main():
    if PROBE:
        return probe_off_imports()
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
