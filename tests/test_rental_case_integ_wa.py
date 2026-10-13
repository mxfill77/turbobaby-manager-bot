# -*- coding: utf-8 -*-
"""К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910), шаги 3–4 DESIGN_K4 §11: дело аренды в агенте WhatsApp (флаг WA_AGENT_CASE).

Запуск — в ПОЛНОМ дереве кандидата (wa_agent* импортируют wa_kind и wa_history, их нет в подмножестве К4):

    python tests/test_rental_case_integ_wa.py          # код выхода ≠ 0 при провале

Сеть запрещена: tests/rental_case_fakes подменяет socket.socket при импорте; модель, мост, Telegram и WhatsApp —
подделки. Временные базы — tempfile.mkdtemp(dir=K4_TTMP) и не удаляются. Источник истины — CONTRACT_K4 (§5 resolve,
facts_for_agent, on_client_inbound, on_human_intervention, record_delivery; §8.3 форма факта; §11 ключи idem_key).

A. Флаг выкл (`case=None`) = прежнее поведение. Голдены по образцу tests/test_wa_agent_tools.py:447: базовые модули —
   git-объекты кандидата f2f7295 по ЗАКРЕПЛЁННЫМ sha блобов (`git cat-file blob`, sha сверяется по содержимому); git
   или объекта нет — ПРОПУЩЕНО (это НЕ зелёное). Без git действуют закреплённый отпечаток блока инструментов, отказ
   «неизвестный инструмент» на `case`, состав дверей сверки. Модулей rental_case* в процессе с флагом выкл нет
   (отдельный процесс-проба).
B. Миграция drafts: при выкл база агента прежняя (схема байт-в-байт); база, однажды дополненная под флагом, читается и
   пишется прежним кодом по именам колонок (откат флагом — данные остаются); UNIQUE notice_id — частичный.
C. Флаг вкл: инструмент `case` — только чтение (Store readonly, соединение `mode=ro` запись отвергает, журнал rc_event
   не растёт); дверь `rental` — `resolve(client)` с номером от кода; касса аренды через дело — `rules.bind_cash`;
   виды `case_*` в `fact_key`; ядро (роль wa) пишет входящее, вмешательство, сверку привязки, кассу и договор; на
   «Отправить» версия дела сверяется (сменилась или не прочитана — ничего не уходит).
D. Сеть (NF-1): импорт `bridge_client` дверью бюджета сверки делается один раз разогревом при импорте этого файла; из
   окна разогрева засчитывается только проба IPv6 urllib3 (где fcntl есть), любая другая попытка — провал теста и
   код выхода ≠ 0.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import rental_case_fakes as F  # noqa: E402 — сеть запрещена при импорте (подмена socket.socket)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent as A          # noqa: E402
import wa_agent_model as M    # noqa: E402
import wa_agent_tools as T    # noqa: E402

# ── сеть: разогрев импорта двери бюджета (NF-1, регрессия reg1 09.10) ──────────────────────────────────────────────
# Сверка агента входит в `wa_agent_model.door_budget` (f2f7295:wa_agent_model.py:1279-1287, вызов :1723), а та делает
# `import bridge_client` (f2f7295:bridge_client.py:11 fcntl, :17 requests) → urllib3 ПРИ ИМПОРТЕ пробует IPv6: `socket.socket(AF_INET6)` + bind на ::1
# (urllib3/util/connection.py, `HAS_IPV6 = _has_ipv6("::1")`). Где fcntl есть (Linux/VPS — полное дерево кандидата;
# прогон reg1 с заглушкой fcntl), импорт доходит до этой пробы, и подделка сети честно считает её попыткой (бросает до
# дескриптора — сокет не создаётся). На ПК без fcntl импорт падает раньше (bridge_client.py:11), пробы нет. Без
# разогрева проба случалась внутри ПЕРВОГО теста со сверкой, а счётчик подделки общий на процесс — итог зависел от
# порядка тестов, а не от пути дела. Разогрев делает этот импорт ОДИН раз, здесь, тем же кодом кандидата; из окна
# разогрева засчитывается ТОЛЬКО запись вида `_IPV6_PROBE` (один аргумент AF_INET6 — не соединение: у соединения
# urllib3 три аргумента). Всё прочее в окне и любая попытка вне окна — провал (`net_unexplained`, TestNetGuard, main).
_IPV6_PROBE = re.compile(r"^socket\.socket\(<AddressFamily\.AF_INET6: \d+>,\)$")
_NET_WARM_FROM = F.net_attempts()
with M.door_budget(0):
    pass
_NET_WARM_TO = F.net_attempts()
_NET_WARM_BRIDGE = "bridge_client" in sys.modules


def net_warm():
    """Записи подделки сети, сделанные разогревом (импорт bridge_client через door_budget)."""
    return F.net_log()[_NET_WARM_FROM:_NET_WARM_TO]


def net_unexplained(log=None):
    """Попытки сети с импорта подделок, кроме названной пробы IPv6 urllib3 в окне разогрева (NF-1). Обязано быть []."""
    log = F.net_log() if log is None else list(log)
    return (log[:_NET_WARM_FROM] + [x for x in log[_NET_WARM_FROM:_NET_WARM_TO] if not _IPV6_PROBE.match(x)]
            + log[_NET_WARM_TO:])


TTMP = os.environ.get("K4_TTMP") or tempfile.gettempdir()
PROBE_ARG = "--probe-off-imports"
PROBE_MARK = "K4_OFF_MODULES "

# Блобы базы — по ним голден «флаг выкл = как было». Основа слияния — 0a87a51 + USEFUL1310 (7dc20b5 + fix 64e0748 +
# A1 a6321f6): живой сервер 0a87a51 = e357f5f (306350b: M + TGGREET e57313b, TGHEAD 9207720, P1 99e4ce3, TGSEND
# 7323cfa/1ddf5da/9fb6972, MIRROR88 a0258bb, TGFRESH 306350b; + W15 0b74cc6 + К4 0055eee/e357f5f) + ARRIVAL3P1310
# (только tests/test_agent_arrival.py); W15 модулей wa_agent* не трогает, поэтому основа без К4 = дерево useful-1310-a1
# a6321f6: wa_agent — прежний (USEFUL1310 его не меняет; TGGREET и TGSEND), model — блоб 64e0748 (A1 его не меняет),
# tools — блоб a6321f6 (A1 приёмщика: реквизиты/получение денег в ЛЮБОМ предложении снимают опору итога «к оплате»).
# Было (основа e357f5f + 64e0748): wa_agent_tools 050d8b32431f…; ещё раньше (основа 306350b): wa_agent_model
# bb40440a40f3…, wa_agent_tools d99dd55e777c…. Объекты 40033b71…/474450dc… достижимы из ветки useful-1310-a1 (несёт и
# bundle переноса); без них — ПРОПУЩЕНО, а не зелёное.
BASE_BLOBS = {
    "wa_agent": "5b3fa1bebb1bad4203611c28dbcc14e97c26976f",
    "wa_agent_model": "40033b713d232b0c9e399f7d837c950be7964c2b",
    "wa_agent_tools": "474450dca494af24ec6d1b76a01d253f4bd50834",
}
BASE_TOOLS = ("history", "rental", "cash", "contract", "contract_pdf", "delivery", "rules")
BASE_TOOLS_BLOCK_SHA = "175b220824b649ce151ae7f463ac864166265b26e9ccd13d42032a93d850d3d1"
BASE_TOOLS_BLOCK8_SHA = "eb159874fd54433fdac8f637bd7ea24a7fcc32f2db761d117eb97ad0f2e664ad"
SKIP_WORDS = "ПРОПУЩЕНО: блоб основы слияния не прочитан git (%s) — голден не сверен, это НЕ зелёное"

NUMBER = "66812345678"
OWNER = 504608015                                  # OWNER_IDS по умолчанию (rental_case_rules.OWNER_IDS)
BY_TEST = {"kind": "code", "id": None, "name": "k4-integ-wa"}
BY_OWNER = {"kind": "human", "id": OWNER, "name": "owner"}
CLIENTS_SRC = "лист «клиенты» (clients filter=all)"
T_NOW = F.epoch(2026, 10, 5, 12, 0)
T_OBS = T_NOW - 3600.0
T0 = 1790000000

QSCHEMA = """CREATE TABLE wa_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_queued INTEGER NOT NULL,
 channel TEXT NOT NULL DEFAULT 'wa', from_number TEXT, name TEXT, msg_type TEXT, text TEXT, media_id TEXT,
 ts_msg INTEGER, echo INTEGER NOT NULL DEFAULT 0, history INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'new', raw TEXT, wamid TEXT)"""


def _mkdtemp(tag):
    return tempfile.mkdtemp(prefix="k4wa_%s_" % tag, dir=TTMP)


# ═════════════════════════════════════════ базовые модули из git (голден) ═════════════════════════════════════════

def _blob(name):
    """Исходник базового модуля по закреплённому sha блоба → (текст | None, почему)."""
    sha = BASE_BLOBS[name]
    try:
        p = subprocess.run(["git", "-C", ROOT, "cat-file", "blob", sha], capture_output=True, timeout=60)
    except Exception as e:                                          # noqa: BLE001
        return None, "git недоступен: %s" % type(e).__name__
    if p.returncode != 0:
        return None, "объекта %s нет" % sha[:12]
    data = p.stdout
    if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != sha:
        return None, "содержимое не сошлось с sha %s" % sha[:12]
    return data.decode("utf-8"), ""


_BASE = {}


def base_module(name):
    """Базовый модуль как отдельный объект (`<имя>_k4base`); его зависимости — модули этого процесса."""
    if name in _BASE:
        return _BASE[name]
    src, why = _blob(name)
    if src is None:
        _BASE[name] = (None, why)
        return _BASE[name]
    mod = types.ModuleType(name + "_k4base")
    mod.__file__ = os.path.join(ROOT, name + ".py")
    exec(compile(src, "base:%s.py" % name, "exec"), mod.__dict__)
    _BASE[name] = (mod, "")
    return _BASE[name]


class _Swap(object):
    """На время прогона базы `import wa_agent_tools` внутри базового адаптера отдаёт базовый модуль."""

    def __init__(self, name, mod):
        self.name, self.mod, self.was = name, mod, None

    def __enter__(self):
        self.was = sys.modules.get(self.name)
        sys.modules[self.name] = self.mod
        return self

    def __exit__(self, *exc):
        if self.was is not None:
            sys.modules[self.name] = self.was
        return False


# ═════════════════════════════════════════════════ подделки ════════════════════════════════════════════════════

class Clock(object):
    def __init__(self, t=1790000000.0, step=0.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


class Script(object):
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — что ушло в модель."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


class Book(object):
    """Снимок броней (`wa_book_read.Snapshot`): get(now) → (строки, парк, возраст, почему); taken_at — как есть."""

    def __init__(self, rows, taken_at=T_NOW - 60.0):
        self.rows, self.taken_at, self.reads = list(rows), taken_at, 0

    def get(self, now):
        self.reads += 1
        return self.rows, [], max(0.0, float(now) - float(self.taken_at)), ""


def row_ivan(**kw):
    return F.make_row(812, F.ST_RENTED, "NMAX 155 6908", "Иван", "2026-10-01 10:00", "2026-10-12 10:00",
                      contacts="+66 81 234 5678", deposit_raw="3000", moment=T_NOW, **kw)


def row_ivan_future(**kw):
    return F.make_row(845, F.ST_BOOKED, "NMAX 155 6908", "Иван", "2026-10-20 10:00", "2026-10-25 10:00",
                      contacts="+66 81 234 5678", moment=T_NOW, **kw)


def row_oleg():
    return F.make_row(900, F.ST_RENTED, "PCX 160 7001", "Олег", "2026-10-02 10:00", "2026-10-09 10:00",
                      contacts="+66 80 000 0001", moment=T_NOW)


def bridge(clock):
    b = F.FakeBridge(clock)
    b.cash = [F.make_cash(2041, 4900, "2026-10-02", bike="NMAX 6908", category="rental",
                          description="NMAX 6908 аренда 4900")]
    b.registry = [F.make_contract(233, "D-1", "Ivan", "2026-10-01", "NMAX 155 6908", "+66 81 234 5678",
                                  signed=True, signed_at="2026-10-01 10:12", pdf_id="P-1")]
    b.pdfs = {"P-1": {"row": 233, "client": "Ivan", "contract_date": "2026-10-01", "signed_at": "2026-10-01 10:12"}}
    return b


def doors_of(b):
    return {"cash": b.tx_find, "contract": b.contract_find, "contract_pdf": b.contract_pdf}


def adapter(mod, script, doors=None, book=None, case=None, clock=None, log=None, tools=True, history=None):
    kw = {"case": case} if case is not None else {}
    log = log if log is not None else []
    a = mod.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=clock or Clock(), log=log.append,
                         book=book, tools=(doors or {}) if tools else None, **kw)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", dict(info))
    a._history = lambda number, upto_id: (history if history is not None else
                                          [{"who": "клиент", "text": "оплатил 4900 бат за аренду"}], [])
    a.knowledge.snap["business_rules"] = {"name": "business_rules", "read": True,
                                          "text": "… 03.10.2026-1 Решения владельца …", "len": 40}
    return a


class FakeModel(A.Model):
    def __init__(self, text="черновик"):
        self.calls, self.text = 0, text

    def draft(self, number, upto_id):
        self.calls += 1
        return "%s %d" % (self.text, self.calls)


class FakeTG(A.Telegram):
    def __init__(self):
        self.calls = []

    def card(self, draft_id, ver, number, text):
        self.calls.append(("card", draft_id, ver))
        return 1000 + draft_id

    def card_done(self, draft_id, card_id, words):
        self.calls.append(("card_done", draft_id, words))
        return True

    def ask_pause(self, number, pause_no, via=None):
        self.calls.append(("ask_pause", pause_no, via))


class FakeDoor(A.Door):
    def __init__(self):
        self.sends = []

    def send_text(self, to, text):
        self.sends.append((to, text))
        return {"outcome": "sent", "reason": "ok", "wamid": "wamid.OUT%d" % len(self.sends)}


class World(object):
    """Очередь схемой wa_webhook, своя база агента, ядро модуля `mod` (базы или патча), фиксированные часы."""

    def __init__(self, mod=A, model=None, case=None, tag="w", number=NUMBER):
        d = _mkdtemp(tag)
        self.qpath, self.dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(self.qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        self.mod, self.number = mod, number
        self.now = [float(T0)]
        self.model, self.tg, self.door, self.log = model or FakeModel(), FakeTG(), FakeDoor(), []
        kw = {"case": case} if case is not None else {}
        self.core = mod.Core(self.dbpath, self.qpath, self.model, self.tg, self.door,
                             clock=lambda: self.now[0], log=self.log.append, **kw)

    def put(self, ts, kind="in", wamid=None, msg_type="text", text="x"):
        echo = 1 if kind == "echo" else 0
        q = sqlite3.connect(self.qpath)
        cur = q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history, wamid) "
                        "VALUES(?,?,?,?,?,?,?,?)", (int(ts), self.number, msg_type, text, int(ts), echo, 0, wamid))
        q.commit()
        rid = cur.lastrowid
        q.close()
        return rid

    def tick(self, t):
        self.now[0] = float(t)
        return self.core.tick(float(t))

    def drafts(self):
        return self.core.db.execute("SELECT id, state, ver, upto_id, decided_by, wamid FROM drafts ORDER BY id"
                                    ).fetchall()

    def paused(self):
        row = self.core.db.execute("SELECT paused, pause_no FROM clients WHERE number=?", (self.number,)).fetchone()
        return tuple(row) if row else (0, 0)


def dump_db(path):
    """База агента целиком: схема (sqlite_master) и строки каждой таблицы, по порядку."""
    c = sqlite3.connect(path)
    try:
        schema = sorted(tuple(r) for r in c.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"))
        rows = {}
        for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            rows[name] = sorted(repr(r) for r in c.execute("SELECT * FROM %s" % name).fetchall())
        return {"schema": schema, "rows": rows}
    finally:
        c.close()


def drafts_cols(core):
    return [r[1] for r in core.db.execute("PRAGMA table_info(drafts)")]


# ─────────────────────────────────────────── дело: хранилище на тест ───────────────────────────────────────────

def src_rows(row, obs):
    return {"name": CLIENTS_SRC, "ref": "строка %d" % row["row"], "method": "door", "read_at": obs + 1.0,
            "observed_at": obs}


class CaseEnv(object):
    """База дела (Store.create) в K4_TTMP, общий часовой и источник id, «администратор» роли test."""

    def __init__(self, tc, tag, rows):
        import rental_case as RC
        import rental_case_rules as RR
        self.RC, self.RR = RC, RR
        self.dir = _mkdtemp(tag)
        self.path = os.path.join(self.dir, "rental_case.db")
        self.clock = F.FakeClock(T_NOW)
        self.ids = F.SeqIds()
        RC.Store.create(self.path, clock=self.clock, new_id=self.ids)
        self.admin = RC.Store(self.path, role="test", clock=self.clock, new_id=self.ids)
        tc.addCleanup(self.admin.close)
        self.book = Book(rows)
        self.links = []
        tc.addCleanup(self._close_links)

    def _close_links(self):
        for lk in self.links:
            for st in (lk._ro, lk._rw):
                if st is not None:
                    st.close()

    def open_case(self, row):
        o = self.admin.open_case(origin="test", by=BY_TEST, idem_key="open:test:anchor:%s" % self.RR.anchor_of(row),
                                 booking_id=row.get("booking_id") or None, rental_row=row, contacts=(),
                                 source=src_rows(row, T_OBS), model_req=None)
        if o.get("code") != "ok" or not o.get("case_id"):
            raise AssertionError("open_case: %r" % (o,))
        return o["case_id"]

    def link(self, path=None):
        lk = T.CaseLink(path or self.path, book=self.book, clock=self.clock)
        self.links.append(lk)
        return lk

    def events(self, cid):
        return self.admin.events(cid)

    def rc_event_count(self):
        c = sqlite3.connect(self.path)
        try:
            return c.execute("SELECT COUNT(*) FROM rc_event").fetchone()[0]
        finally:
            c.close()


# ═══════════════════════════════════════ A. флаг выкл = прежнее поведение ═══════════════════════════════════════

GOLD_SCRIPTS = (
    ("сверка: аренда, касса, договор, PDF, дело (флаг выкл), доставка",
     ({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"bike": "NMAX 6908"}},
      {"tool": "contract", "args": {"phone": "+66 81 234 5678"}}, {"tool": "contract_pdf", "args": {"file_id": "P-1"}},
      {"tool": "case", "args": {"intent": "current"}}, {"tool": "delivery", "args": {}},
      final("Оплата получена, 4900 бат. Залог вернём в конце.")), True),
    ("предел вызовов — запасной вызов", ({"tool": "history", "args": {}},), True),
    ("ответ не JSON", ("не JSON",), True),
    ("без сверки (WA_AGENT_TOOLS выкл)", (final("Здравствуйте! Байк свободен."),), False),
)


def model_story(mod, tools_mod):
    """Прогон адаптера модуля `mod` по GOLD_SCRIPTS (флаг дела выкл) → расшифровка: ответ, журнал, промпты, итоги."""
    out = []
    with _Swap("wa_agent_tools", tools_mod):
        for title, answers, tools in GOLD_SCRIPTS:
            clock = Clock()
            b = bridge(F.FakeClock(T_NOW))
            log = []
            s = Script(*answers)
            a = adapter(mod, s, doors=doors_of(b), book=Book([row_ivan(), row_oleg()]), clock=clock, log=log,
                        tools=tools)
            got = a.draft(NUMBER, 5)
            last = a.last or {}
            res = (last.get("tools") or {}).get("results")
            out.append({"title": title, "got": got, "log": log, "seen": s.seen,
                        "results": json.dumps(res, ensure_ascii=False, sort_keys=True, default=str),
                        "bridge": b.calls})
    return json.loads(json.dumps(out, ensure_ascii=False, sort_keys=True, default=str))


def core_story(mod, case=None):
    """Ядро модуля `mod`: черновик, _outdated (сообщение, контекст), нажатия, эхо текста (пауза), «Продолжить» дважды,
    эхо фото (без паузы), новое входящее снимает ждущий черновик → расшифровка, дамп базы, журнал, руки."""
    w = World(mod, case=case, tag="gold")
    out = []
    q = mod.QUIET_DEFAULT
    w.tick(T0 - 1000)
    w.put(T0)
    w.tick(T0 + q)
    d1 = w.drafts()[0][0]
    out.append(("outdated_fresh", w.core._outdated(d1)))
    w.core._bump(NUMBER)
    out.append(("outdated_ctx", w.core._outdated(d1)))
    out.append(("press_ctx", w.core.press(d1, 1, mod.ACT_SEND, "tester", now=T0 + q + 5)))
    w.put(T0 + 600)
    w.tick(T0 + 600 + q)
    d2 = w.drafts()[-1][0]
    w.put(T0 + 700)                                  # клиент написал ещё, скан ещё не прошёл
    out.append(("press_fresh", w.core.press(d2, 1, mod.ACT_SEND, "tester", now=T0 + 701)))
    w.tick(T0 + 700 + q)
    d3 = w.drafts()[-1][0]
    out.append(("press_sent", w.core.press(d3, 1, mod.ACT_SEND, "tester", now=T0 + 700 + q + 5)))
    w.put(T0 + 2000, kind="echo", wamid="wamid.PHONE1")
    w.tick(T0 + 2010)
    pn = w.paused()[1]
    out.append(("paused_text", w.paused()))
    out.append(("resume", w.core.resume(NUMBER, pn, "tester", now=T0 + 2100)))
    out.append(("resume_again", w.core.resume(NUMBER, pn, "tester", now=T0 + 2101)))
    w.put(T0 + 2200, kind="echo", wamid="wamid.PHONE2", msg_type="image")
    w.tick(T0 + 2210)
    out.append(("paused_image", w.paused()))
    w.put(T0 + 2300)
    w.tick(T0 + 2300 + q)
    d4 = w.drafts()[-1][0]
    w.core.db.execute("UPDATE clients SET last_in_id=last_in_id+1000 WHERE number=?", (NUMBER,))
    out.append(("outdated_wrote", w.core._outdated(d4)))
    out.append(("drafts", w.drafts()))
    return {"out": json.loads(json.dumps(out, ensure_ascii=False, default=str)), "db": dump_db(w.dbpath),
            "log": w.log, "tg": w.tg.calls, "door": w.door.sends}


class TestFlagOff(unittest.TestCase):
    """Флаг WA_AGENT_CASE выкл: инструменты, промпт, двери, черновик, ядро и база — как на основе слияния."""

    def test_tools_block_and_names_pinned(self):
        self.assertEqual(T.TOOLS, BASE_TOOLS, "состав инструментов сменился без флага")
        self.assertEqual(hashlib.sha256(T.TOOLS_BLOCK.encode("utf-8")).hexdigest(), BASE_TOOLS_BLOCK_SHA)
        self.assertEqual(hashlib.sha256((T.TOOLS_BLOCK % 8).encode("utf-8")).hexdigest(), BASE_TOOLS_BLOCK8_SHA)
        self.assertNotIn(T.CASE_TOOL, T.TOOLS)

    def test_prompt_head_is_old_block_without_case_door(self):
        s = Script(final("ok"))
        T.run(s, "SYSTEM", "USER", {"cash": lambda **kw: {}}, number=NUMBER, clock=Clock())
        self.assertEqual(s.seen[0], (T.TOOLS_BLOCK % T.MAX_CALLS) + "\n\n" + "USER")
        self.assertNotIn(T.CASE_BLOCK, s.seen[0])

    def test_case_tool_refused_as_unknown_without_door(self):
        r = T.call_tool(T.CASE_TOOL, {"intent": "current"}, {"cash": lambda **kw: {}}, clock=Clock())
        self.assertEqual((r["tool"], r["outcome"], r["reason"]), (T.CASE_TOOL, T.REFUSED, "неизвестный инструмент"))
        self.assertEqual(T.render([r]).count("\n"), 1, "отказ без строк фактов, как у прочих")

    def test_doors_and_rental_door_unchanged(self):
        book = Book([row_ivan(), row_ivan_future(), row_oleg()])
        a = adapter(M, Script(final("x")), doors=doors_of(bridge(F.FakeClock(T_NOW))), book=book)
        doors = a._tool_doors(NUMBER, 5)
        self.assertEqual(sorted(doors), ["cash", "contract", "contract_pdf", "history", "rental", "rules"])
        self.assertIsNone(a.case)
        r = T.call_tool("rental", {}, doors, clock=Clock())
        self.assertEqual(r["outcome"], T.FACT, r)
        self.assertEqual(r["source"], "снимок броней (лист «клиенты»)")
        self.assertEqual([f["date_start"] for f in r["facts"]], ["2026-10-01 10:00"], "будущая бронь не видна, как было")
        self.assertNotIn("case_bind", r["facts"][0])

    def test_fact_key_and_amounts_unchanged_for_old_kinds(self):
        cash = {"kind": "cash", "src": "tx_find", "row": 2, "msg_id": "m2", "link": "l", "amount": 4900,
                "currency": "THB", "role": T.R_RENT, "booking_id": "bk-1", "bike": "NMAX 6908", "at": "2026-10-02"}
        rent = {"kind": "rental", "booking_id": "bk-1", "bike": "NMAX 6908", "date_start": "2026-10-01",
                "date_end": "2026-10-12", "price": None, "currency": "THB"}
        self.assertEqual(T.fact_key(cash), ("cash", "tx_find", "2", "m2"))
        self.assertEqual(T.fact_key(rent), ("rental", "bk-1"))
        self.assertEqual(T.fact_key({"kind": "history"}), ("history",))
        self.assertTrue(T.cash_of_rental(dict(cash, at="2026-10-30"), "bk-1", [rent, cash]),
                        "без дела касса с booking_id аренды привязана, как было (wa_agent_tools.py:536-546)")
        self.assertIn(4900, T.known_amounts(None, [rent, cash], T.calc([rent, cash])))

    def test_model_golden_equals_base_blob(self):
        tools0, why_t = base_module("wa_agent_tools")
        model0, why_m = base_module("wa_agent_model")
        if tools0 is None or model0 is None:
            self.skipTest(SKIP_WORDS % (why_t or why_m))
        now = model_story(M, T)
        was = model_story(model0, tools0)
        self.assertEqual(len(now), len(was))
        first = now[0]                                   # сценарий не пустой: голден сверяет работу, а не тишину
        self.assertEqual(len(first["seen"]), 7)
        self.assertIn('"tool": "case"', first["results"])
        self.assertIn("неизвестный инструмент", first["results"])
        self.assertTrue(isinstance(first["got"], dict) and first["got"].get("text"), first["got"])
        self.assertNotIn("case", first["got"], "флаг выкл: ответ черновика без ключа дела")
        for n, w in zip(now, was):
            self.assertEqual(n, w, "флаг выкл: адаптер разошёлся с базой в сценарии «%s»" % n["title"])

    def test_core_golden_equals_base_blob(self):
        core0, why = base_module("wa_agent")
        if core0 is None:
            self.skipTest(SKIP_WORDS % why)
        now, was = core_story(A), core_story(core0)
        self.assertEqual(now["out"], was["out"], "флаг выкл: _outdated/нажатия/пауза/«Продолжить» разошлись с базой")
        self.assertEqual(now["db"]["schema"], was["db"]["schema"], "флаг выкл: схема базы агента сменилась")
        self.assertEqual(now["db"]["rows"], was["db"]["rows"], "флаг выкл: строки базы агента разошлись")
        self.assertEqual((now["log"], now["tg"], now["door"]), (was["log"], was["tg"], was["door"]))

    def test_core_story_off_without_git(self):
        """Без git: прежние исходы ядра словами кандидата (WROTE_WORDS, контекст, пауза, «уже продолжено»)."""
        got = dict((k, v) for k, v in core_story(A)["out"])
        self.assertIsNone(got["outdated_fresh"])
        self.assertTrue(str(got["outdated_ctx"]).startswith("беседа сменилась после черновика"))
        self.assertEqual(got["press_ctx"]["state"], A.STALE)
        self.assertEqual(got["press_sent"]["state"], A.SENT)
        self.assertEqual(got["paused_text"][0], 1)
        self.assertEqual(got["resume"], {"ok": True, "words": "продолжаем"})
        self.assertFalse(got["resume_again"]["ok"])
        self.assertEqual(got["paused_image"][0], 0, "фото с телефона паузы не ставит (WAPAUSEMEDIA0410)")
        self.assertTrue(str(got["outdated_wrote"]).startswith("клиент написал ещё"))

    def test_off_schema_has_no_case_columns(self):
        w = World(A, tag="offschema")
        cols = drafts_cols(w.core)
        for col, _typ in A.CASE_DRAFT_COLS:
            self.assertNotIn(col, cols, "флаг выкл: база агента прежняя (колонок дела нет)")
        idx = w.core.db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='drafts_notice'").fetchall()
        self.assertEqual(idx, [])
        self.assertEqual(w.core.notice_find("RN-1"), {"unknown": "дело выключено (WA_AGENT_CASE)"})
        self.assertIsNone(w.core.case_delivery("wamid.X", "delivered"))

    def test_off_process_has_no_rental_case_modules(self):
        p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                           timeout=300)
        text = p.stdout.decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
        self.assertEqual(p.returncode, 0, text[-2000:] + p.stderr.decode("utf-8", "replace")[-2000:])
        self.assertEqual(len(lines), 1, text[-2000:])
        self.assertEqual(json.loads(lines[0][len(PROBE_MARK):]), [],
                         "флаг выкл: rental_case* попали в sys.modules процесса (импорт обязан быть ленивым)")

    def test_case_link_of_off_and_misconfig(self):
        self.assertEqual(T.case_link_of(False, "/abs/x.db", book=Book([])), (None, None))
        lk, words = T.case_link_of(True, "rel/x.db", book=Book([]))
        self.assertIsNone(lk)
        self.assertIn("не абсолютный", words)
        missing = os.path.join(_mkdtemp("nolink"), "нет.db")
        lk, words = T.case_link_of(True, missing, book=Book([]))
        self.assertIsNone(lk)
        self.assertIn("Store.create не сделан", words)
        self.assertFalse(os.path.exists(missing), "проверка конфигурации базу не создаёт")


def probe_off_imports():
    """Отдельный процесс: пути флага выкл (сверка с дверями, отказ `case`, ядро) → какие rental_case* загружены."""
    a = adapter(M, Script({"tool": "rental", "args": {}}, {"tool": "case", "args": {}}, final("ok")),
                doors=doors_of(bridge(F.FakeClock(T_NOW))), book=Book([row_ivan()]))
    a.draft(NUMBER, 5)
    T.call_tool(T.CASE_TOOL, {}, {"cash": lambda **kw: {}})
    core_story(A)
    T.case_link_of(False, "", book=None)
    mods = sorted(m for m in sys.modules if m.startswith("rental_case") and m != "rental_case_fakes")
    sys.stdout.write(PROBE_MARK + json.dumps(mods) + "\n")
    sys.stdout.flush()
    return 0


# ═════════════════════════════════════════════ B. миграция drafts ═════════════════════════════════════════════

class TestMigration(unittest.TestCase):

    def test_old_db_then_on_then_off(self):
        env = CaseEnv(self, "mig", [row_ivan()])
        w = World(A, tag="mig")                                    # база агента прежней схемы (флаг выкл)
        w.tick(T0 - 1000)
        w.put(T0)
        w.tick(T0 + A.QUIET_DEFAULT)
        d1 = w.drafts()[0][0]
        before = drafts_cols(w.core)
        self.assertFalse(set(c for c, _t in A.CASE_DRAFT_COLS) & set(before))
        w.core.db.close()
        on = A.Core(w.dbpath, w.qpath, FakeModel(), FakeTG(), FakeDoor(), clock=lambda: float(T0 + 400),
                    case=env.link())                                # первый старт с флагом — миграция
        cols = drafts_cols(on)
        self.assertEqual(cols[:len(before)], before, "старые колонки на своих местах")
        self.assertEqual(cols[len(before):], [c for c, _t in A.CASE_DRAFT_COLS])
        self.assertEqual(on.db.execute("SELECT case_id, case_ver, notice_id FROM drafts WHERE id=?", (d1,)).fetchone(),
                         (None, None, None))
        self.assertIsNone(on._outdated(d1), "черновик без дела судится только по сообщению и контексту")
        on.db.close()
        off = A.Core(w.dbpath, w.qpath, FakeModel(), FakeTG(), FakeDoor(), clock=lambda: float(T0 + 500))
        self.assertEqual(off.db.execute("SELECT text, state, upto_id FROM drafts WHERE id=?", (d1,)).fetchone()[1],
                         A.PENDING, "откат флагом: прежний код читает drafts по именам")
        self.assertEqual(off.press(d1, 1, A.ACT_SEND, "tester", now=T0 + 501)["state"], A.SENT)
        off.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,?,?,?)",
                       ("10000000009", A.DECLINED, "t", 1, T0))
        off.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at) VALUES(?,?,1,?,?,?)",
                       ("10000000009", A.DECLINED, "t", 1, T0))
        self.assertEqual(off.db.execute("SELECT COUNT(*) FROM drafts WHERE notice_id IS NULL").fetchone()[0], 3,
                         "частичный UNIQUE: черновики без уведомления не мешают друг другу")

    def test_notice_unique_and_find(self):
        env = CaseEnv(self, "notice", [row_ivan()])
        w = World(A, case=env.link(), tag="notice")
        ins = ("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, notice_id, case_id, case_ver) "
               "VALUES(?,?,1,?,?,?,?,?,?)")
        w.core.db.execute(ins, (NUMBER, A.PENDING, "уведомление", 1, T0, "RN-1", "RC-x", 1))
        with self.assertRaises(sqlite3.IntegrityError):
            w.core.db.execute(ins, ("10000000002", A.PENDING, "второй", 1, T0, "RN-1", "RC-x", 1))
        found = w.core.notice_find("RN-1")
        self.assertEqual((found["state"], found["wamid"]), (A.PENDING, None))
        self.assertEqual(w.core.notice_find("RN-2"), {"absent": True})


# ═══════════════════════════════════════════ C. флаг вкл: шаг 3 (агент) ═══════════════════════════════════════════

class TestCaseTool(unittest.TestCase):

    def test_case_tool_fact_read_only(self):
        env = CaseEnv(self, "tool", [row_ivan(), row_oleg()])
        cid = env.open_case(row_ivan())
        link = env.link()
        a = adapter(M, Script({"tool": "case", "args": {}}, final("ok")), doors={}, book=env.book, case=link,
                    clock=env.clock)
        doors = a._tool_doors(NUMBER, 5)
        self.assertEqual(sorted(doors), ["case", "history", "rental", "rules"])
        n0 = env.rc_event_count()
        r = T.call_tool(T.CASE_TOOL, {}, doors, clock=env.clock)
        self.assertEqual((r["outcome"], r["ref"], r["version"]), (T.FACT, cid, "case_ver:1"), r)
        self.assertEqual(r["at"], env.clock(), "время факта — начало запроса")
        kinds = [f["kind"] for f in r["facts"]]
        self.assertEqual(kinds[:2], ["case", "case_client"])
        self.assertIn("case_rental", kinds)
        self.assertTrue(all(f["case_id"] == cid and f["case_ver"] == 1 for f in r["facts"]))
        money = [f for f in r["facts"] if f["kind"] == "case_money"]
        self.assertTrue(money and all(f["payment_confirmed"] is False for f in money))
        rent = T.call_tool("rental", {}, doors, clock=env.clock)
        self.assertEqual(rent["outcome"], T.FACT, rent)
        self.assertEqual((rent["facts"][0]["case_id"], rent["facts"][0]["case_ver"]), (cid, 1))
        self.assertEqual(env.rc_event_count(), n0, "инструменты дела только читают: журнал rc_event не вырос")
        st = link.reader()
        self.assertTrue(st.readonly)
        self.assertIsNone(link._rw, "читатель не открывал писателя")
        with self.assertRaises(sqlite3.OperationalError):
            st._con().execute("CREATE TABLE k4_probe(x)")          # соединение mode=ro: SQLite запись отвергает
        a.call = Script({"tool": "case", "args": {}}, final("ok"))
        got = a.draft(NUMBER, 5)
        self.assertEqual((got["case"]["case_id"], got["case"]["case_ver"]), (cid, 1))
        self.assertEqual(got["case"]["writes"], [], "без кассы и договора записывать нечего")
        self.assertEqual(env.rc_event_count(), n0)

    def test_prompt_has_case_block_and_masked_render(self):
        env = CaseEnv(self, "prompt", [row_ivan()])
        env.open_case(row_ivan())
        s = Script({"tool": "case", "args": {}}, final("ok"))
        a = adapter(M, s, doors={}, book=env.book, case=env.link(), clock=env.clock)
        a.draft(NUMBER, 5)
        self.assertTrue(s.seen[0].startswith((T.TOOLS_BLOCK % T.MAX_CALLS) + "\n" + T.CASE_BLOCK + "\n\nUSER"))
        block = s.seen[1]
        self.assertIn('"case_ver": 1', block)
        self.assertIn("[имя]", block)
        self.assertNotIn("Иван", block, "имя клиента в блок модели не идёт")
        # К4 круг 2 (V6): имя не идёт ни в каком регистре — в т. ч. в якоре аренды plate|день|имя (нормализован в нижний)
        self.assertNotIn("иван", block.lower(), "имя клиента в блоке модели (якорь аренды не замаскирован)")
        self.assertNotRegex(block, r'"anchor":\s*"(?!\[имя\])', "якорь аренды в блоке модели — только маской")
        self.assertNotIn("+66", block)
        self.assertNotIn('"src"', block)

    def test_rental_door_via_resolve(self):
        env = CaseEnv(self, "resolve", [row_ivan(), row_ivan_future(), row_oleg()])
        cid = env.open_case(row_ivan())
        doors = adapter(M, Script(final("x")), doors={}, book=env.book, case=env.link(), clock=env.clock
                        )._tool_doors(NUMBER, 5)
        amb = T.call_tool("rental", {}, doors, clock=env.clock)
        self.assertEqual(amb["outcome"], T.AMBIGUOUS, amb)
        self.assertIn("rental_ambiguous", amb["reason"])
        cur = T.call_tool("rental", {"intent": "current"}, doors, clock=env.clock)
        self.assertEqual((cur["outcome"], cur["facts"][0]["case_id"]), (T.FACT, cid))
        self.assertEqual(cur["facts"][0]["date_start"], "2026-10-01 10:00")
        fut = T.call_tool("rental", {"intent": "future"}, doors, clock=env.clock)
        self.assertEqual(fut["outcome"], T.FACT, fut)
        self.assertEqual(fut["facts"][0]["date_start"], "2026-10-20 10:00")
        self.assertNotIn("case_id", fut["facts"][0], "у брони дела нет — строка листа без дела")
        stranger = adapter(M, Script(final("x")), doors={}, book=env.book, case=env.link(), clock=env.clock
                           )._tool_doors("66999999999", 5)
        none = T.call_tool("rental", {}, stranger, clock=env.clock)
        self.assertEqual(none["outcome"], T.EMPTY, none)
        case_none = T.call_tool(T.CASE_TOOL, {}, stranger, clock=env.clock)
        self.assertEqual(case_none["outcome"], T.AMBIGUOUS, "CONTRACT_K4 §8.3: resolve → unknown = ambiguous с ask")
        self.assertTrue(case_none["reason"], case_none)
        self.assertEqual(case_none["facts"], [])

    def test_store_missing_is_unknown_not_created(self):
        env = CaseEnv(self, "missing", [row_ivan()])
        missing = os.path.join(env.dir, "нет-базы.db")
        doors = adapter(M, Script(final("x")), doors={}, book=env.book, case=env.link(missing), clock=env.clock
                        )._tool_doors(NUMBER, 5)
        r = T.call_tool(T.CASE_TOOL, {}, doors, clock=env.clock)
        self.assertEqual(r["outcome"], T.UNKNOWN, r)
        self.assertIn("StoreUnavailable", r["reason"])
        rent = T.call_tool("rental", {}, doors, clock=env.clock)
        self.assertEqual(rent["outcome"], T.UNKNOWN, rent)
        self.assertFalse(os.path.exists(missing), "открытие без создания (I33)")

    def test_case_result_rejects_malformed(self):
        self.assertEqual(T.case_result({"tool": "rental", "outcome": "fact"})["outcome"], T.UNKNOWN)
        self.assertEqual(T.case_result({"tool": "case", "outcome": "fact", "ref": "RC-1", "version": "7",
                                        "facts": [{"kind": "case_client"}]})["outcome"], T.UNKNOWN)
        bad = {"tool": "case", "outcome": "fact", "ref": "RC-1", "version": "case_ver:2",
               "facts": [{"kind": "case", "case_id": "RC-2", "case_ver": 2}]}
        self.assertEqual(T.case_result(bad)["outcome"], T.UNKNOWN, "элемент чужого дела — не факт")
        ok = T.case_result({"tool": "case", "outcome": "fact", "ref": "RC-1", "version": "case_ver:2",
                            "facts": [{"kind": "case", "case_id": "RC-1", "case_ver": 2},
                                      {"kind": "case_note", "x": 1}, {"kind": "cash", "row": 1}]}, at=5.0)
        self.assertEqual((ok["outcome"], ok["at"], [f["kind"] for f in ok["facts"]]), (T.FACT, 5.0,
                                                                                     ["case", "case_note"]))

    def test_fact_key_case_items_do_not_collapse(self):
        base = {"tool": "case", "outcome": "fact", "ref": "RC-1", "version": "case_ver:3", "facts": [
            {"kind": "case", "case_id": "RC-1", "case_ver": 3},
            {"kind": "case_money", "obligation_id": 1, "role": "deposit", "amount": 3000, "currency": "THB"},
            {"kind": "case_money", "obligation_id": 2, "role": "deposit_refund", "amount": 3000, "currency": "THB"},
            {"kind": "case_document", "document_id": 7, "doc_kind": "contract_signed"},
            {"kind": "case_stage", "task_id": "RT-1", "stage": "question_sent"},
            {"kind": "case_stage", "task_id": "RT-1", "stage": "answer_received"}]}
        r = T.case_result(base, at=1.0)
        r["req"] = "case []"
        facts, _dropped = T.sift([r])
        self.assertEqual(len(facts), 6, [T.fact_key(f) for f in facts])
        self.assertEqual(T.fact_key(r["facts"][1])[:4], ("case", "RC-1", "3", "case_money"))
        self.assertNotEqual(T.fact_key(r["facts"][1]), T.fact_key(r["facts"][2]))

    def test_case_money_not_in_known_amounts_nor_pay(self):
        money = {"kind": "case_money", "role": "deposit", "amount": 3333, "currency": "THB", "case_id": "RC-1",
                 "case_ver": 1, "payment_confirmed": False}
        self.assertNotIn(3333, T.known_amounts(None, [money], T.calc([money])), "суммы дела — не опора чисел (I45)")
        self.assertFalse(T.pay_confirmed([money]))

    def test_cash_of_rental_delegates_to_bind_cash(self):
        import rental_case_rules as RR
        ivan = dict(row_ivan(), booking_id="bk-1")
        fut = dict(row_ivan_future(), booking_id="bk-2")
        binding = {"rental_id": 1, "booking_id": "bk-1", "plate": "6908", "start_day": "2026-10-01",
                   "end_day": "2026-10-12", "crm_row_seen": 812, "name_seen": "Иван", "status_seen": "В аренде"}
        rent = {"kind": "rental", "booking_id": "bk-1", "bike": "NMAX 155 6908", "date_start": "2026-10-01 10:00",
                "date_end": "2026-10-12 10:00", "price": None, "currency": "THB"}
        rent_case = dict(rent, case_bind={"rental": binding, "rows": [ivan, fut], "params": dict(RR.PARAMS_DEFAULT)})
        late = {"kind": "cash", "src": "tx_find", "row": 9, "msg_id": "m9", "booking_id": "bk-1", "bike": "NMAX 6908",
                "at": "2026-10-14", "amount": 500, "currency": "THB", "role": T.R_RENT}
        inside = dict(late, row=10, msg_id="m10", at="2026-10-03")
        self.assertTrue(T.cash_of_rental(late, "bk-1", [rent, late]), "без дела — прежнее правило: booking_id")
        self.assertFalse(T.cash_of_rental(late, "bk-1", [rent_case, late]),
                         "через дело — bind_cash: касса после конца аренды → unknown, не привязана")
        self.assertEqual(RR.bind_cash(late, binding, [ivan, fut], RR.PARAMS_DEFAULT)["code"], "unknown")
        self.assertTrue(T.cash_of_rental(inside, "bk-1", [rent_case, inside]))
        no_bk = dict(inside, booking_id="", row=11, msg_id="m11", at="2026-10-11")
        self.assertTrue(T.cash_of_rental(no_bk, "bk-1", [rent, no_bk]), "прежнее: байк и день в сроке")
        pre = dict(no_bk, row=12, msg_id="m12", at="2026-10-16")
        self.assertFalse(T.cash_of_rental(pre, "bk-1", [rent_case, pre]),
                         "через дело: предоплата брони с 20.10 и аренда до 12.10 — выбрать нельзя")

    def test_case_plan_one_case_min_version(self):
        def res(tool, facts, at):
            return {"tool": tool, "outcome": T.FACT, "source": "s", "ref": "", "at": at, "version": "", "window": "",
                    "reason": "", "facts": facts, "req": "%s %s" % (tool, at)}
        r1 = res("case", [{"kind": "case", "case_id": "RC-1", "case_ver": 2}], 1.0)
        r2 = res("rental", [{"kind": "rental", "booking_id": "", "bike": "NMAX 6908", "case_id": "RC-1",
                             "case_ver": 3, "case_bind": {"rental": {"rental_id": 5}}}], 2.0)
        cash = {"kind": "cash", "src": "tx_find", "row": 7, "msg_id": "m7", "link": "l7", "amount": 100,
                "currency": "THB", "booking_id": "", "bike": "NMAX 6908", "at": "2026-10-02", "role": T.R_RENT}
        r3 = res("cash", [cash], 3.0)
        p = T.case_plan([r1, r2, r3])
        self.assertEqual((p["case_id"], p["case_ver"], p["rental_id"]), ("RC-1", 2, 5))
        self.assertEqual([w["op"] for w in p["writes"]], ["bind_cash"])
        key = "cash:RC-1:7:m7:%s" % hashlib.sha256(b"100|THB||").hexdigest()[:12]
        self.assertEqual(p["writes"][0]["idem_key"], key, "CONTRACT_K4 §11: cash:<case>:<row>:<msg_id>:<sha12>")
        r4 = res("case", [{"kind": "case", "case_id": "RC-9", "case_ver": 1}], 4.0)
        p2 = T.case_plan([r1, r2, r3, r4])
        self.assertEqual((p2["case_id"], p2["writes"]), (None, []), "два дела в сверке — без привязки и записей")


# ═══════════════════════════════════════════ C. флаг вкл: шаг 4 (ядро) ═══════════════════════════════════════════

class TestCore(unittest.TestCase):

    def world(self, env, script, tag, rows=None):
        link = env.link()
        b = bridge(env.clock)
        model = adapter(M, script, doors=doors_of(b), book=env.book, case=link, clock=env.clock)
        w = World(A, model=model, case=link, tag=tag)
        return w, model, b

    def test_inbound_draft_writes_and_press(self):
        net0 = len(F.net_log())
        env = CaseEnv(self, "e2e", [row_ivan(), row_oleg()])
        cid = env.open_case(row_ivan())
        script = Script({"tool": "case", "args": {}}, {"tool": "cash", "args": {"bike": "NMAX 6908"}},
                        {"tool": "contract", "args": {"phone": "+66 81 234 5678"}},
                        {"tool": "contract_pdf", "args": {"file_id": "P-1"}},
                        final("Здравствуйте! Байк за вами до 12.10."))
        w, model, _b = self.world(env, script, "e2e")
        w.tick(T_NOW - 2000)
        rid = w.put(T_NOW - 400)
        w.tick(T_NOW)
        drafts = w.core.db.execute("SELECT id, state, case_id, case_ver FROM drafts").fetchall()
        self.assertEqual(len(drafts), 1, w.log)
        did, state, d_cid, d_ver = drafts[0]
        self.assertEqual((state, d_cid, d_ver), (A.PENDING, cid, 1), w.log)
        types_ = [e["type"] for e in env.events(cid)]
        self.assertIn("client_inbound", types_)
        self.assertIn("cash_bound", types_, w.log)
        self.assertEqual(types_.count("document_recorded"), 2, w.log)
        view = env.admin.case_view(cid)
        docs = sorted((d["kind"], d["ext_id"], d["status"]) for d in view["documents"]["items"])
        self.assertEqual(docs, [("contract_pdf", "P-1", "verified"), ("contract_signed", "D-1", "verified")])
        cash = [f for f in view["facts"]["valid"] if f["kind"] == "cash"]
        self.assertEqual([(f["value"]["row"], f["value"]["bound_by"]) for f in cash], [(2041, "plate+day")])
        inbound = [e for e in env.events(cid) if e["type"] == "client_inbound"]
        self.assertEqual(inbound[0]["ref"] or inbound[0]["payload"].get("ref"), "wa_inbox:%d" % rid)
        res = w.core.press(did, 1, A.ACT_SEND, "tester", now=T_NOW + 10)
        self.assertEqual(res["state"], A.SENT, res)
        self.assertEqual(len(w.door.sends), 1)
        # повтор того же такта и тех же записей — duplicate, ни одной новой строки
        n = env.rc_event_count()
        plan = T.case_plan(model.last["tools"]["results"])
        self.assertEqual([wr["op"] for wr in plan["writes"]], ["bind_cash", "record_document", "record_document"])
        again = w.core._case_after(plan)
        self.assertEqual(again, 3)
        w.core._case_inbound(NUMBER, rid, T_NOW - 400, T_NOW)
        self.assertEqual(env.rc_event_count(), n, "повтор записей и входящего — duplicate, новых строк нет")
        self.assertEqual(F.net_log()[net0:], [], "путь дела (входящее → сверка → записи → «Отправить»): сети нет")
        self.assertEqual(net_unexplained(), [], "с импорта подделок — только названная проба IPv6 разогрева (NF-1)")

    def test_outdated_by_case_version_and_unchecked(self):
        env = CaseEnv(self, "ver", [row_ivan()])
        cid = env.open_case(row_ivan())
        script = Script({"tool": "case", "args": {}}, final("Ваш байк до 12.10."))
        w, model, _b = self.world(env, script, "ver")
        w.tick(T_NOW - 2000)
        w.put(T_NOW - 400)
        w.tick(T_NOW)
        did = w.drafts()[0][0]
        self.assertIsNone(w.core._outdated(did))
        o = env.admin.bump_version(cid, reason="new_request", ref="wa:test", by=BY_OWNER,
                                   idem_key="bump:%s:1:new_request:wa:test" % cid, expect_ver=1)
        self.assertEqual((o["code"], o["ver"]), ("ok", 2), o)
        words = w.core._outdated(did)
        self.assertEqual(words, "версия дела сменилась после черновика (1 → 2)")
        res = w.core.press(did, 1, A.ACT_SEND, "tester", now=T_NOW + 10)
        self.assertEqual(res["state"], A.STALE, res)
        self.assertIn("версия дела сменилась", res["words"])
        self.assertEqual(w.door.sends, [], "версия дела сменилась — клиенту ничего не ушло")
        # хранилище не прочитано — «не проверено», ничего не уходит
        w.put(T_NOW + 20)
        model.call = Script({"tool": "case", "args": {}}, final("Ещё ответ."))
        w.tick(T_NOW + 20 + A.QUIET_DEFAULT)
        d2 = w.drafts()[-1][0]
        self.assertEqual(w.core.db.execute("SELECT case_ver FROM drafts WHERE id=?", (d2,)).fetchone()[0], 2)
        w.core.case = env.link(os.path.join(env.dir, "нет-базы.db"))
        words = w.core._outdated(d2)
        self.assertEqual(words, A.CASE_UNCHECKED_WORDS % "StoreUnavailable")
        res = w.core.press(d2, 1, A.ACT_SEND, "tester", now=T_NOW + 400)
        self.assertEqual(res["state"], A.STALE, res)
        self.assertEqual(w.door.sends, [])

    def test_draft_without_case_judged_as_before(self):
        env = CaseEnv(self, "nocase", [row_ivan()])
        w, model, _b = self.world(env, Script(final("Без дела.")), "nocase")
        w.tick(T_NOW - 2000)
        w.put(T_NOW - 400)
        w.tick(T_NOW)
        did = w.drafts()[0][0]
        self.assertEqual(w.core.db.execute("SELECT case_id, case_ver FROM drafts WHERE id=?", (did,)).fetchone(),
                         (None, None), "дела в сверке нет — черновик без дела")
        self.assertIsNone(w.core._outdated(did))
        self.assertEqual(w.core.press(did, 1, A.ACT_SEND, "tester", now=T_NOW + 5)["state"], A.SENT)

    def test_echo_intervention_attention_and_resume(self):
        env = CaseEnv(self, "echo", [row_ivan()])
        cid = env.open_case(row_ivan())
        w, _model, _b = self.world(env, Script(final("x")), "echo")
        w.tick(T_NOW - 2000)
        w.put(T_NOW - 100, kind="echo", wamid="wamid.PHONE_IMG", msg_type="image")
        w.tick(T_NOW - 90)
        self.assertEqual(w.paused()[0], 0)
        ev = [e for e in env.events(cid) if e["type"] == "human_intervention"]
        self.assertEqual(len(ev), 1)
        self.assertFalse(ev[0]["payload"]["attention"], "фото с телефона — событие без внимания (WAPAUSEMEDIA0410)")
        self.assertFalse(env.admin.case_view(cid)["case"]["attention"])
        w.put(T_NOW - 50, kind="echo", wamid="wamid.PHONE_TXT", msg_type="text")
        w.tick(T_NOW - 40)
        paused, pn = w.paused()
        self.assertEqual(paused, 1)
        case = env.admin.case_view(cid)["case"]
        self.assertTrue(case["attention"])
        self.assertEqual(case["wa_pause_no"], pn, "внимание дела несёт номер паузы WA")
        res = w.core.resume(NUMBER, pn, "tester", now=T_NOW)
        self.assertEqual(res, {"ok": True, "words": "продолжаем"}, "«Продолжить» — прежнее")
        self.assertTrue(env.admin.case_view(cid)["case"]["attention"],
                        "снятие внимания дела «Продолжить» не делает (PAUSE_RELEASER=UNKNOWN, остаток)")
        w.put(T_NOW + 10, kind="echo", wamid="wamid.PHONE_DOC", msg_type="document")
        w.tick(T_NOW + 20)
        self.assertEqual(w.paused(), (0, pn), "документ после «Продолжить» паузы не ставит")
        last = [e for e in env.events(cid) if e["type"] == "human_intervention"][-1]
        self.assertEqual((last["payload"]["attention"], last["payload"]["kind"]), (False, "document"),
                         "номер прежней паузы не выдаётся за паузу этого эха")

    def test_autogreet_echo_is_not_intervention(self):
        env = CaseEnv(self, "greet", [row_ivan()])
        cid = env.open_case(row_ivan())
        link = env.link()
        w = World(A, case=link, tag="greet")
        text = "Здравствуйте! Мы скоро ответим."
        w.core.greet = (hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],)
        w.tick(T_NOW - 2000)
        w.put(T_NOW - 100)
        w.put(T_NOW - 98, kind="echo", wamid="wamid.GREET", text=text)
        w.tick(T_NOW - 90)
        self.assertEqual(w.paused()[0], 0)
        self.assertEqual([e for e in env.events(cid) if e["type"] == "human_intervention"], [])
        self.assertTrue([e for e in env.events(cid) if e["type"] == "client_inbound"])

    def test_reconcile_before_model(self):
        env = CaseEnv(self, "recon", [row_ivan()])
        cid = env.open_case(row_ivan())
        moved = row_ivan()
        moved["date_end"] = "2026-10-14 10:00"
        env.book.rows = [moved]
        w, _model, _b = self.world(env, Script(final("x")), "recon")
        w.tick(T_NOW - 2000)
        w.put(T_NOW - 400)
        w.tick(T_NOW)
        view = env.admin.case_view(cid)
        self.assertEqual(view["rental"]["current"]["end_day"], "2026-10-14", w.log)
        self.assertEqual(view["case"]["ver"], 2, "срок сменился — версия дела поднята (period_changed)")
        self.assertTrue(any(l.startswith("дело: сверка привязки %s" % cid) for l in w.log), w.log)

    def test_hint_version_rebinds_case_version(self):
        """Версия по пояснению (NIGHT0710-B2) — своя сверка: черновик помнит версию дела НОВОЙ версии текста."""
        env = CaseEnv(self, "hint", [row_ivan()])
        cid = env.open_case(row_ivan())

        class CaseModel(A.Model):
            def draft(self, number, upto_id):
                return {"text": "v1", "handoff": [], "lang": "ru", "why": "",
                        "case": {"case_id": cid, "case_ver": 1, "writes": [], "words": ""}}

            def redraft(self, number, upto_id, prev_text, hint):
                return {"text": "v2", "handoff": [], "lang": "ru", "why": "",
                        "case": {"case_id": cid, "case_ver": 2, "writes": [], "words": ""}}

        d = _mkdtemp("hintw")
        qpath, dbpath = os.path.join(d, "q.db"), os.path.join(d, "agent.db")
        q = sqlite3.connect(qpath)
        q.execute(QSCHEMA)
        q.commit()
        q.close()
        now = [float(T0)]
        core = A.Core(dbpath, qpath, CaseModel(), FakeTG(), FakeDoor(), clock=lambda: now[0], hints=True,
                      case=env.link())
        core.tick(T0 - 1000)
        q = sqlite3.connect(qpath)
        q.execute("INSERT INTO wa_inbox(ts_queued, from_number, msg_type, text, ts_msg, echo, history) "
                  "VALUES(?,?,?,?,?,0,0)", (T0, NUMBER, "text", "x", T0))
        q.commit()
        q.close()
        core.scan(T0 + 100)
        core.make_drafts(T0 + 100)
        did = core.db.execute("SELECT id FROM drafts").fetchone()[0]
        self.assertEqual(core.db.execute("SELECT case_ver FROM drafts WHERE id=?", (did,)).fetchone()[0], 1)
        core.db.execute("INSERT INTO hints(draft_id, ver_from, text, prev_text, author, ts, state) "
                        "VALUES(?,1,?,?,?,?,?)", (did, "пояснение", "v1", "tester (id 1)", T0 + 110, A.HINT_WAIT))
        self.assertEqual(core.make_hint_versions(T0 + 120), [(did, 2)])
        self.assertEqual(core.db.execute("SELECT ver, case_id, case_ver FROM drafts WHERE id=?", (did,)).fetchone(),
                         (2, cid, 2))

    def test_r2_send_binds_door_wamid_of_notice_draft_only(self):
        """К4 круг 2 (C10): «Отправить» черновика уведомления дела — после НАСТОЯЩЕЙ отправки ядро сообщает хранилищу
        notice_id, draft_id и wamid ДВЕРИ (`CaseLink.notice_sent`); черновик без уведомления, неудачная отправка —
        ничего. Статус провайдера сюда не участвует (его сверяет хранилище с этой привязкой)."""

        class SpyLink(object):
            def __init__(self):
                self.calls = []

            def notice_sent(self, notice_id, draft_id, wamid, at):
                self.calls.append((notice_id, draft_id, wamid, at))
                return {"code": "ok"}

        spy = SpyLink()
        w = World(A, case=spy, tag="r2sent")
        ins = ("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, notice_id) VALUES(?,?,1,?,?,?,?)")
        d1 = w.core.db.execute(ins, (NUMBER, A.CLAIMED, "уведомление", 1, T0, "RN-501")).lastrowid
        d2 = w.core.db.execute(ins, ("10000000002", A.CLAIMED, "ответ", 1, T0, None)).lastrowid
        d3 = w.core.db.execute(ins, ("10000000003", A.CLAIMED, "уведомление", 1, T0, "RN-503")).lastrowid
        out = w.core._deliver(d1, NUMBER, 1, "уведомление", "tester", T_NOW, A.CLAIMED)
        self.assertEqual(out["state"], A.SENT, out)
        sent_wamid = w.core.db.execute("SELECT wamid FROM drafts WHERE id=?", (d1,)).fetchone()[0]
        self.assertEqual(spy.calls, [("RN-501", d1, sent_wamid, T_NOW)], "привязка = wamid двери за этим черновиком")
        w.core._deliver(d2, "10000000002", 1, "ответ", "tester", T_NOW, A.CLAIMED)
        self.assertEqual(len(spy.calls), 1, "черновик без уведомления дела хранилищу не сообщается")
        w.door.send_text = lambda to, text: {"outcome": "not_sent", "reason": "синтетика", "wamid": None}
        w.core._deliver(d3, "10000000003", 1, "уведомление", "tester", T_NOW, A.CLAIMED)
        self.assertEqual(len(spy.calls), 1, "неудачная отправка привязки не даёт")

    def test_case_delivery_only_notice_draft_and_delivered(self):
        env = CaseEnv(self, "deliv", [row_ivan()])
        w = World(A, case=env.link(), tag="deliv")
        w.core.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, wamid, notice_id) "
                          "VALUES(?,?,1,?,?,?,?,?)", (NUMBER, A.SENT, "уведомление", 1, T0, "wamid.N1", "RN-404"))
        w.core.db.execute("INSERT INTO drafts(number, state, ver, text, upto_id, created_at, wamid) "
                          "VALUES(?,?,1,?,?,?,?)", ("10000000002", A.SENT, "ответ", 1, T0, "wamid.N2"))
        self.assertIsNone(w.core.case_delivery("wamid.N1", "sent"), "не «доставлено» — не пишется")
        self.assertIsNone(w.core.case_delivery("wamid.N2", "delivered"), "черновик не уведомления дела")
        out = w.core.case_delivery("wamid.N1", "read", at=T_NOW)
        self.assertEqual(out["code"], "rejected", "уведомления нет в хранилище — отказ хранилища, не падение")
        self.assertTrue(any("доставка черновика" in l for l in w.log), w.log)


# ═══════════════════════════════════════════ D. сеть: разогрев и счётчик (NF-1) ═══════════════════════════════════════════

class TestNetGuard(unittest.TestCase):
    """NF-1: из окна разогрева засчитывается только проба IPv6 urllib3 при импорте bridge_client; прочее — провал."""

    def test_warm_window_only_named_probe(self):
        self.assertEqual(F.net_attempts(), len(F.net_log()), "счётчик и журнал подделки — один к одному")
        warm = net_warm()
        self.assertLessEqual(len(warm), 1, warm)
        self.assertEqual([x for x in warm if not _IPV6_PROBE.match(x)], [], warm)
        if not _NET_WARM_BRIDGE:
            self.assertEqual(warm, [], "bridge_client не импортирован (нет fcntl): до requests не дошло — пробы нет")
        if warm:
            self.assertIn("urllib3", sys.modules, "проба — от импорта urllib3, а не от кода кандидата")
        self.assertEqual(net_unexplained(), [], F.net_log())

    def test_door_budget_again_adds_nothing(self):
        n = F.net_attempts()
        for sec in (0, 1.0):
            with M.door_budget(sec):
                pass
        self.assertEqual(F.net_attempts(), n, "проба IPv6 — однократный импорт; повторный вход в бюджет сети не трогает")

    def test_probe_pattern_is_narrow(self):
        for line in ("socket.socket(<AddressFamily.AF_INET6: 23>,)", "socket.socket(<AddressFamily.AF_INET6: 10>,)"):
            self.assertTrue(_IPV6_PROBE.match(line), line)
        for line in ("socket.socket(<AddressFamily.AF_INET6: 10>, <SocketKind.SOCK_STREAM: 1>, 6)",
                     "socket.socket(<AddressFamily.AF_INET: 2>,)", "socket.socket()",
                     "getaddrinfo('example.com', 443)", "create_connection(('example.com', 443),)"):
            self.assertIsNone(_IPV6_PROBE.match(line), line)

    def test_unexplained_window_is_by_position(self):
        probe = "socket.socket(<AddressFamily.AF_INET6: 10>,)"
        head = ["getaddrinfo('h', 1)"] * _NET_WARM_FROM
        window = [probe] * (_NET_WARM_TO - _NET_WARM_FROM)
        self.assertEqual(net_unexplained(head + window), head)
        self.assertEqual(net_unexplained(head + window + [probe]), head + [probe], "та же проба вне окна — провал")
        other = "create_connection(('h', 443),)"
        self.assertEqual(net_unexplained(head + [other] + window[1:]), head + [other], "в окне — только проба")


def main():
    if PROBE_ARG in sys.argv[1:]:
        return probe_off_imports()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    bad = net_unexplained()
    probes = [x for x in net_warm() if _IPV6_PROBE.match(x)]
    print("сеть: попыток %d; из них проба IPv6 urllib3 при импорте bridge_client в разогреве (NF-1): %d; "
          "необъяснённых: %d %s" % (F.net_attempts(), len(probes), len(bad), json.dumps(bad, ensure_ascii=False)))
    ok = res.wasSuccessful() and not bad
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
