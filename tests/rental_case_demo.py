#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Демонстрационный случай К4 — tests/rental_case_demo.py (CONTRACT_K4 §14; приёмка ПОР:35 = К4-C35; вариант Б = К4-C17).

Источник истины — out/CONTRACT_K4.md §14 (фикстура, шаги Д1–Д14, счётчики, след, вариант Б), DESIGN_K4 §13 (строка
«полный демо-случай», мутанты M6, M27) и §15 (К4-C35, К4-C17, К4-C18). Проверка — ЧЁРНЫМ ЯЩИКОМ: код rental_case*.py
не читается и под него не подгоняется. Наблюдается только то, что контракт делает видимым:
  * исходы публичных функций `rental_case.Store` (§5; форма Outcome §1.2; коды §1.3);
  * строки схемы §2 — ТОЛЬКО чтение (SELECT), отдельным соединением `mode=ro` на каждый запрос, без своих транзакций;
  * журналы и счётчики подделок `tests/rental_case_fakes.py` (§9.1, шов §13). Сеть запрещена импортом подделок
    (`socket.socket` подменён бросающим) — первым импортом этого файла.

Запуск (только stdlib; разбор ast.parse(src, feature_version=(3, 8))):
    python tests/rental_case_demo.py [--variant A|B] [--trace <путь>]       # по умолчанию оба: A, затем Б
    python tests/rental_case_demo.py --repeat-check [--variant A|B]         # два прогона → нормализованные следы равны
    python tests/rental_case_demo.py --compare <след1> <след2>              # сверка двух готовых следов без прогона
Код выхода: 0 — все выбранные прогоны прошли; 1 — провал шага/сверки; 2 — реализация не импортируется / ошибка вызова.

Каждый шаг Д1–Д14 проверяет ожидаемый исход §14 И отсутствие лишнего: отказ (`rejected`/`conflict`/`unknown` без записи)
и `duplicate` не пишут ни строки и ни события (§1.3, §8.1); чтения (`resolve`, `facts_for_agent`, `due_expectations`,
`allowed_actions`) не пишут ничего; события мутации — только в деле Бориса или без дела (§8.1); `case_ver` дела Бориса = 1
после КАЖДОГО вызова; дело Ивана после Д2 не меняется ни одной строкой; счётчики подделок в конце — постов staff_ask 2
(тема, Delivery), эскалаций 0, вызовов NoticePort 0, отправок клиенту 0, попыток сети 0.

Контрольные пробы (actor `probe:<инвариант>`): вызов, который ОБЯЗАН быть отвергнут/повторён без записи, — чтобы демо
ловило порчу, а не только «зелёное»: I7 (тот же idem_key → duplicate с event_seq первого раза), I32 (тот же ключ с
другим содержимым → conflict(idem_payload_mismatch)), I43/M27 (claim_escalation кодом при WAIT_BEFORE_AGENTS=UNKNOWN →
rejected(param_unknown)), I10/M6 (ступень 4 по свидетельству staff_answer → rejected). Строки проб в след входят (строка
на вызов), в счёт «каждый шаг ok/found» (К4-C35) не входят. Ключи проб — канонические §11; ключ пробы I10 совпадает с
ключом Д11: отказ ключа не расходует (§1.3), и Д11 тем же ключом обязан дать ok, а не conflict/duplicate.

Д4 сверяет части дела для агента (§8.3/§8.4, К4-C36): все части, шесть полей src у каждого элемента (и вложенных),
src строк, рождённых open_case, = source вызова Д2 (§5.1), src.case_ver = 1, номер клиента — только маской, версии
внешнего источника нет. Ключ версии части `case` в контракте расходится (§8.3 пример — `case_ver`, §8.4 — `ver` «без
переименований»): принимается любой из двух, значение обязано быть 1.

След (§14) — строка JSON на вызов: {"step", "actor", "role", "call", "args_sha", "code", "verdict", "case_id", "ver",
"event_seq": [seq событий, записанных ЭТИМ вызовом], "data": {выбранные ключи исхода}, "fakes": {"staff_posts",
"escalations", "notice_calls", "client_sends", "net"}}. Аргументы в след не пишутся: `args_sha` = sha256 канонического
JSON аргументов, в которых id прогона и время заменены порядковыми метками (`Labeler`), путь базы — меткой "<db>".
Время стенных часов не используется вовсе (часы — FakeClock от 09.10.2026 12:00 +7); в несущих полях следа времени нет.
Пути следа: вариант A — `--trace` (по умолчанию out/trace_demo.jsonl), вариант Б — рядом с суффиксом `_B`
(trace_demo_B.jsonl). Провальный прогон пишет след в `<путь>.partial`, а не в `<путь>`. Существующий файл следа не
затирается: он откладывается переименованием в `<путь>.prev-<n>` (ничего не удаляется). Режим `--repeat-check` пишет
оба прогона во временный каталог (K4_TTMP), не трогая out/; с `--trace` — первый прогон туда, второй — с суффиксом
`_repeat`.

Нормализация следа (`normalize_trace`) — сверка повторяемости К4-C35: id прогона (`RC-`/`RT-`/`RE-`/`RN-` + 32 hex и
голые 32 hex: boot_id, store_id) → `<idN>`, значения временных ключей (at, read_at, observed_at, written_at, now, …) →
`<tN>` по порядку первого появления; `args_sha` сравнивается как есть (уже посчитан по нормализованным аргументам).

Временная база — tempfile.mkdtemp(dir=K4_TTMP или системный temp) и НЕ удаляется. Боевых записей нет: мост, мозг,
Telegram, WhatsApp — только подделки в памяти.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

import rental_case_fakes as F  # noqa: E402 — ПЕРВЫМ: подмена socket.socket до импорта модулей дела

# =====================================================================================================================
# Фикстура §14 (синтетика; формат двери clients — f2f7295:bridge_prod/ReadClients.js:95-121 через F.make_row)
# =====================================================================================================================

DEFAULT_TRACE = "D:/turbobaby-bot/tmp/k4_0910/out/trace_demo.jsonl"
STEPS = ("Д1", "Д2", "Д3", "Д4", "Д5", "Д6", "Д7", "Д8", "Д9", "Д10", "Д11", "Д12", "Д13", "Д14")
T0 = F.epoch(2026, 10, 9, 12, 0)          # §14: момент — 09.10.2026 12:00 (+7)
STEP_S = 60.0                              # шаг k начинается в T0 + (k-1) мин (часы двигает только демо)
H48 = 48 * 3600.0

BIKE = "NMAX 155 6908"
PLATE = "6908"
IVAN_ROW, BORIS_ROW = 812, 845
IVAN_U = "+66 81 234 5678"                 # номера U разные (§14)
BORIS_U = "+7 916 123-45-67"
BORIS_WA = "79161234567"                   # контакт обращения WA — цифры целиком, задаёт КОД (I36)

SERVICING_CHAT = "-1002000000001"          # чат тем байков (тема 55)
TOPIC_THREAD = "55"
DELIVERY_CHAT = "-1002000000002"
AGENTS_CHAT = "-1002000000003"
TOPIC_MID, DELIVERY_MID, ANSWER_MID = "7001", "7002", "7010"

Q_RU = "Будет ли NMAX 6908 готов к выдаче 15.10?"
Q_TH = "NMAX 6908 จะพร้อมส่งมอบวันที่ 15.10 ไหมครับ"
URGENCY = "клиент интересуется"
ANSWER_TEXT = "พร้อมครับ / готов"
WA_REF = "wa:in:501"
INTENT = "readiness_confirmed"

STAFF_ID = 9001
STAFF_NAME = "mech9001"
APPROVER_A = 1001                          # вариант А: APPROVER_IDS={1001}

BY_TEST = {"kind": "code", "id": None, "name": "demo:test"}
BY_WA = {"kind": "code", "id": None, "name": "wa"}
BY_AGENT = {"kind": "agent", "id": None, "name": "wa_agent"}
BY_SPL = {"kind": "code", "id": None, "name": "splinter"}
BY_HUMAN = {"kind": "human", "id": APPROVER_A, "name": "approver1001"}
HUMAN_ACTOR = "human %d" % APPROVER_A
STAFF_ACTOR = "staff %d" % STAFF_ID

UNKNOWN_STAYS = ("WAIT_BEFORE_AGENTS", "ANSWER_TTL", "ACCEPT_WORDS")   # §14: остаются UNKNOWN в обоих вариантах

# §3.4 REQUIRED: «Бронь» + deposit_raw=passport + FINAL_NOTICE_REQUIRED=UNKNOWN (§14 Д2 — дословно этот набор)
BORIS_OBLIGATIONS = sorted([("bike", "handover"), ("bike", "return"), ("money", "rent"), ("money", "deposit"),
                            ("document", "passport_return"), ("client", "notify_final")])
# §3.4 REQUIRED: «В аренде» (handover — только при «Бронь») + залог числом (+ deposit_refund) + notify_final
IVAN_OBLIGATIONS = sorted([("bike", "return"), ("money", "rent"), ("money", "deposit"), ("money", "deposit_refund"),
                           ("client", "notify_final")])
STAGES_A = [("question_sent", "post"), ("answer_received", "answer"), ("task_accepted", "human_mark"),
            ("physically_done", "human_mark"), ("result_recorded", "readback")]
FA_KINDS = ("case", "case_client", "case_rental", "case_bike", "case_money", "case_document", "case_obligation")
SRC_KEYS = ("source", "ref", "method", "read_at", "observed_at", "case_ver")
SRC_METHODS = ("door", "reply", "readback", "human", "event")              # §2: CHECK method у строк с src
FAKE_KEYS = ("staff_posts", "escalations", "notice_calls", "client_sends", "net")
FINAL_COUNTERS = {"staff_posts": 2, "escalations": 0, "notice_calls": 0, "client_sends": 0, "net": 0}
OK_CODES = ("ok", "found", "fact")
NO_WRITE_CODES = ("rejected", "conflict", "unknown", "duplicate")
OUT_KEYS = ("case_id", "rental_id", "obligations", "documents", "near_cases", "task_id", "exp_id", "notice_id",
            "answer_id", "fact_id", "stage", "state", "verdict", "decision", "execute", "expect", "escalation",
            "notice", "orphan_id", "cases", "readback_exp_id", "superseded_notices", "stale_read")

# =====================================================================================================================
# Мелочи: вывод, JSON, нормализация следа
# =====================================================================================================================


def say(msg):
    try:
        sys.stdout.write(msg + "\n")
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        sys.stdout.write(msg.encode(enc, "replace").decode(enc, "replace") + "\n")
    sys.stdout.flush()


def _jsonable(x):
    """Значение → JSON-совместимое; множества — отсортированным списком (порядок не зависит от хеш-соли)."""
    if isinstance(x, dict):
        return dict((str(k), _jsonable(v)) for k, v in x.items())
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((_jsonable(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, bytes):
        return x.decode("utf-8", "replace")
    return repr(x)


def _short(x, n=700):
    try:
        s = json.dumps(_jsonable(x), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        s = repr(x)
    return s if len(s) <= n else s[:n] + "…"


def _payload(ev):
    try:
        p = json.loads(ev.get("payload") or "{}")
    except (TypeError, ValueError):
        return {}
    return p if isinstance(p, dict) else {}


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _addressees(v):
    """rc_post.addressee_ids (§2: json int-список | "UNKNOWN") → отсортированный список int | "UNKNOWN" (строка как
    есть или в JSON-кавычках — §2 и §4.7 п.7 форму литерала не уточняют)."""
    try:
        x = json.loads(v) if isinstance(v, str) else v
    except ValueError:
        x = v
    if isinstance(x, list):
        return sorted(x)
    return x


def _has_value(obj, needle):
    """Есть ли строковое значение `needle` где-либо внутри структуры."""
    if isinstance(obj, dict):
        return any(_has_value(v, needle) for v in obj.values())
    if isinstance(obj, (list, tuple, set, frozenset)):
        return any(_has_value(v, needle) for v in obj)
    return isinstance(obj, str) and obj == needle


def _keys_valued(obj, key):
    """Все значения ключа `key` во вложенной структуре."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out.extend(_keys_valued(v, key))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_keys_valued(v, key))
    return out


_ID_RE = re.compile(r"(?<![0-9A-Za-z])(?:R[CTEN]-)?[0-9a-f]{32}(?![0-9A-Za-z])")
TIME_KEYS = frozenset(("at", "read_at", "observed_at", "written_at", "created_at", "updated_at", "moment", "now",
                       "received_at", "post_at", "waiting_since", "claim_at", "delivered_at", "cover_at",
                       "escalated_at", "taken_at", "business_due_at", "asked_ts", "ts"))


class Labeler(object):
    """Замена id прогона и времени на порядковые метки (по порядку первого появления)."""

    def __init__(self):
        self.ids = {}
        self.times = {}

    def _id(self, s):
        lab = self.ids.get(s)
        if lab is None:
            lab = "<id%d>" % (len(self.ids) + 1)
            self.ids[s] = lab
        return lab

    def _time(self, v):
        k = repr(float(v))
        lab = self.times.get(k)
        if lab is None:
            lab = "<t%d>" % (len(self.times) + 1)
            self.times[k] = lab
        return lab

    def norm(self, obj, key=None):
        if isinstance(obj, dict):
            out = {}
            for k in sorted(obj, key=lambda x: str(x)):
                out[str(k)] = self.norm(obj[k], str(k))
            return out
        if isinstance(obj, (set, frozenset)):
            return [self.norm(v, key) for v in _jsonable(obj)]
        if isinstance(obj, (list, tuple)):
            return [self.norm(v, key) for v in obj]
        if obj is None or isinstance(obj, bool):
            return obj
        if isinstance(obj, (int, float)):
            return self._time(obj) if key in TIME_KEYS else obj
        if isinstance(obj, str):
            return _ID_RE.sub(lambda m: self._id(m.group(0)), obj)
        return self.norm(_jsonable(obj), key)


def normalize_trace(records):
    """След → список с id и временем, заменёнными порядковыми метками (сверка повторяемости К4-C35)."""
    lab = Labeler()
    out = []
    for rec in records:
        r = dict(rec)
        sha = r.pop("args_sha", None)
        n = lab.norm(r)
        n["args_sha"] = sha
        out.append(n)
    return out


def load_trace(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def compare_traces(a, b):
    """→ (равны, объяснение первого расхождения)."""
    na, nb = normalize_trace(a), normalize_trace(b)
    if na == nb:
        return True, ""
    for i in range(max(len(na), len(nb))):
        x = na[i] if i < len(na) else None
        y = nb[i] if i < len(nb) else None
        if x != y:
            return False, "строка %d:\n  1: %s\n  2: %s" % (i + 1, _short(x, 900), _short(y, 900))
    return False, "расхождение без строки"


def set_aside(path):
    """Отложить существующий файл переименованием в <путь>.prev-<n> (ничего не удаляется)."""
    if not os.path.lexists(path):
        return None
    n = 1
    while os.path.lexists("%s.prev-%d" % (path, n)):
        n += 1
    cand = "%s.prev-%d" % (path, n)
    os.rename(path, cand)
    return cand


def trace_path_for(base, variant):
    if variant == "A":
        return base
    stem, ext = os.path.splitext(base)
    return stem + "_B" + (ext or ".jsonl")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def anchor_of_row(row):
    """Якорь строки для idem_key open_case (§11: open:<origin>:anchor:<anchor>; §6 anchor_of: plate|день|имя)."""
    return "%s|%s|%s" % (F.WT.plate_of(row.get("bike")), str(row.get("date_start") or "")[:10],
                         str(row.get("name") or "").strip().lower())


def fixture_rows():
    """§14: строка 812 — Иван «В аренде» 01.10–12.10, залог 3000; строка 845 — Борис «Бронь» 15.10–20.10, залог
    passport; тот же байк; номера U разные; Y пуст у обеих (booking_id §14 не назван)."""
    return [
        F.make_row(IVAN_ROW, F.ST_RENTED, BIKE, "Иван", "2026-10-01 10:00", "2026-10-12 10:00", contacts=IVAN_U,
                   deposit_raw="3000", moment=T0),
        F.make_row(BORIS_ROW, F.ST_BOOKED, BIKE, "Борис", "2026-10-15 10:00", "2026-10-20 10:00", contacts=BORIS_U,
                   deposit_raw="passport", moment=T0),
    ]


def params_for(RC, variant):
    """Вариант А — синтетические значения §14 поверх PARAMS_DEFAULT; вариант Б — PARAMS_DEFAULT (params=None)."""
    if variant == "B":
        return None
    p = dict(RC.PARAMS_DEFAULT)
    rrp = p.get("RESULT_RECORD_PLACE")
    rrp = dict(rrp) if isinstance(rrp, dict) else {}
    rrp["readiness"] = "sink:fake"
    sa = p.get("STAFF_ADDRESSEES")
    sa = dict(sa) if isinstance(sa, dict) else {}
    sa["topic"] = frozenset([STAFF_ID])
    sa["delivery"] = frozenset([9002])
    p["AUTO_ASK"] = True
    p["STAFF_ADDRESSEES"] = sa
    p["RESULT_RECORD_PLACE"] = rrp
    p["FEEDS_CONNECTED"] = frozenset(["intervention", "inbound"])
    p["APPROVER_IDS"] = frozenset([APPROVER_A])
    return p


def approver_for(RC, variant):
    """Одобряющий: вариант А — 1001; вариант Б — из APPROVER_IDS по умолчанию (= OWNER_IDS, CONTRACT §10)."""
    if variant == "A":
        return dict(BY_HUMAN)
    ids = []
    for key in ("APPROVER_IDS", "OWNER_IDS"):
        v = RC.PARAMS_DEFAULT.get(key)
        if isinstance(v, (set, frozenset, list, tuple)):
            ids = sorted(i for i in v if isinstance(i, int) and not isinstance(i, bool))
        if ids:
            break
    return {"kind": "human", "id": ids[0] if ids else 504608015, "name": "approver-default"}


def _list_code(x):
    return "ok" if isinstance(x, list) else type(x).__name__


def _outcome_code(x):
    if isinstance(x, dict):
        return x.get("code")
    if isinstance(x, list):
        return "ok"
    return type(x).__name__


def _outcome_data(x):
    if not isinstance(x, dict):
        return {}
    d = x.get("data") if isinstance(x.get("data"), dict) else {}
    sel = dict((k, d[k]) for k in OUT_KEYS if k in d)
    for k in ("reason", "missing"):
        if x.get(k):
            sel[k] = x[k]
    return sel


def _outcome_verdict(x):
    if isinstance(x, dict) and isinstance(x.get("data"), dict):
        return x["data"].get("verdict")
    return None


def _action_names(acts):
    names = []
    for a in acts if isinstance(acts, list) else []:
        if isinstance(a, dict):
            nm = None
            for k in ("action", "name", "what", "op"):
                if isinstance(a.get(k), str):
                    nm = a[k]
                    break
            names.append(nm if nm is not None else _short(a, 80))
        else:
            names.append(str(a))
    return names


def _port_code(r):
    if not isinstance(r, dict):
        return type(r).__name__
    if r.get("posted"):
        return "ok"
    for k in ("refused", "deduped", "unknown"):
        if k in r:
            return k
    return "empty"


def _post_data(r):
    posts = (r or {}).get("posted") or []
    return {"posted": [{"place": p.get("place"), "chat": p.get("chat"), "msg_id": p.get("msg_id"),
                        "thread_id": p.get("thread_id"), "role": p.get("role")} for p in posts],
            "qid_set": bool((r or {}).get("qid")),
            "other": sorted(k for k in (r or {}) if k not in ("posted", "qid"))}


def _resolve_data(r):
    if not isinstance(r, dict):
        return {}
    row = r.get("row")
    out = dict((k, r.get(k)) for k in ("code", "case_id", "ver", "reason", "missing") if r.get(k) is not None)
    if isinstance(row, dict):
        out["row"] = row.get("row")
    return out


def _fa_data(r):
    if not isinstance(r, dict):
        return {}
    facts = r.get("facts") if isinstance(r.get("facts"), list) else []
    return {"outcome": r.get("outcome"), "tool": r.get("tool"), "version": r.get("version"),
            "kinds": sorted(set(str(f.get("kind")) for f in facts if isinstance(f, dict)))}


# =====================================================================================================================
# Наблюдатель схемы §2 — только чтение
# =====================================================================================================================


class Peek(object):
    """SELECT по схеме §2. Соединение на каждый запрос (mode=ro; если ro не открылось — обычное, только SELECT),
    autocommit, транзакций не держит — писатель-Store не ждёт наблюдателя."""

    TABLES_CASE = ("rc_case", "rc_link", "rc_contact", "rc_rental", "rc_fact", "rc_document", "rc_obligation",
                   "rc_task", "rc_stage", "rc_expect", "rc_answer", "rc_notice", "rc_event")

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.uri = pathlib.Path(self.path).as_uri() + "?mode=ro"
        self._ro_ok = True

    def _connect(self):
        if self._ro_ok:
            c = None
            try:
                c = sqlite3.connect(self.uri, uri=True, timeout=10, isolation_level=None)
                c.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
            except sqlite3.OperationalError:
                if c is not None:
                    c.close()
                self._ro_ok = False
            else:
                c.row_factory = sqlite3.Row
                return c
        if not os.path.isfile(self.path):
            raise RuntimeError("файла базы нет: %s" % self.path)
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        return c

    def query(self, *stmts):
        c = self._connect()
        try:
            return [[dict(r) for r in c.execute(sql, tuple(args)).fetchall()] for sql, args in stmts]
        finally:
            c.close()

    def rows(self, sql, args=()):
        return self.query((sql, args))[0]

    def one(self, sql, args=()):
        r = self.rows(sql, args)
        return r[0] if r else None

    def max_seq(self):
        return int(self.one("SELECT COALESCE(MAX(seq), 0) AS m FROM rc_event")["m"])

    def events_after(self, seq):
        return self.rows("SELECT seq, case_id, exp_id, type, ver_before, ver_after, author, payload, idem_key "
                         "FROM rc_event WHERE seq > ? ORDER BY seq", (seq,))

    def counts(self):
        c = self._connect()
        try:
            names = [r["name"] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'rc!_%' ESCAPE '!' "
                "ORDER BY name").fetchall()]
            return dict((t, int(c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0])) for t in names)
        finally:
            c.close()

    def ver(self, case_id):
        r = self.one("SELECT ver FROM rc_case WHERE case_id = ?", (case_id,))
        return r["ver"] if r else None

    def case_snapshot(self, case_id):
        stmts = [("SELECT * FROM %s WHERE case_id = ? ORDER BY rowid" % t, (case_id,)) for t in self.TABLES_CASE]
        return dict(zip(self.TABLES_CASE, self.query(*stmts)))


class DemoFailure(Exception):
    """Несовпадение ожидаемого исхода шага §14."""


# =====================================================================================================================
# Один прогон варианта
# =====================================================================================================================


class DemoRun(object):
    """Прогон варианта A или B (CONTRACT §14) на своём файле базы (mkdtemp в K4_TTMP; не удаляется)."""

    def __init__(self, RC, variant, trace_path, db_dir):
        self.RC = RC
        self.variant = variant
        self.trace_path = trace_path
        # абсолютный путь (§2, I33) прямыми косыми: безопасен и для URI file:%s?mode=rw, который строит Store
        self.db_path = os.path.join(os.path.abspath(db_dir), "rental_case_demo_%s.sqlite" % variant).replace("\\", "/")
        self.clock = F.FakeClock(T0)
        self.ids = F.SeqIds()
        self.counters = F.Counters()
        self.args_labeler = Labeler()
        self.trace = []
        self.peek = None
        self.stores = {}
        self.store_id = None
        self.step = "Д0"
        self.boris = None
        self.ivan = None
        self.task = None
        self.exp = None
        self.ivan_snap = None
        self.boris_obl0 = None
        self.src_boris = None                  # source open_case дела Бориса (Д2) — для сверки src частей (§8.4)
        self.brain_lines = []
        self.params = params_for(RC, variant)
        self.approver = approver_for(RC, variant)
        self.approver_actor = "human %s" % self.approver["id"]
        self.telegram = F.FakeTelegram(self.clock, self.counters, start_mid=int(TOPIC_MID))
        self.staff_ask = F.FakeStaffAsk(self.clock, self.counters)
        self.staff_port = F.FakeStaffAskPort(self.staff_ask, self.telegram, self.clock, SERVICING_CHAT, TOPIC_THREAD,
                                             DELIVERY_CHAT, AGENTS_CHAT, bike=BIKE, kind="байк", q_ru=Q_RU, q_th=Q_TH,
                                             urgency=URGENCY)
        self.escalation_port = F.FakeEscalationPort(self.staff_ask, self.telegram, self.clock, AGENTS_CHAT)
        self.sink = F.FakeResultSink(self.clock, self.counters, name="sink:fake")
        self.notice_port = F.FakeNoticePort(self.clock, self.counters)
        self.source = F.FakeRentalSource(self.clock, rows=fixture_rows(), counters=self.counters)

    # ------------------------------------------------------------------------------------------------ служебное
    @property
    def is_a(self):
        return self.variant == "A"

    def now(self):
        return self.clock.now

    def check(self, cond, msg, detail=None):
        if not cond:
            raise DemoFailure("%s [%s]: %s%s" % (self.step, self.variant, msg,
                                                 "" if detail is None else " | " + _short(detail)))

    def begin(self, i):
        self.step = STEPS[i - 1]
        self.clock.set(T0 + (i - 1) * STEP_S)

    def _fakes(self):
        snap = self.counters.snapshot()
        return dict((k, snap.get(k)) for k in FAKE_KEYS)

    def _args_sha(self, call, args_view):
        canon = self.args_labeler.norm({"call": call, "args": _jsonable(args_view)})
        s = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def _record(self, actor, role, call, args_view, out, case_id, events, code, verdict, data):
        ver = None
        if isinstance(out, dict) and isinstance(out.get("ver"), int) and not isinstance(out.get("ver"), bool):
            ver = out["ver"]
        elif case_id and self.peek is not None:
            ver = self.peek.ver(case_id)
        self.trace.append({"step": self.step, "actor": actor, "role": role, "call": call,
                           "args_sha": self._args_sha(call, args_view), "code": code, "verdict": verdict,
                           "case_id": case_id, "ver": ver, "event_seq": [e["seq"] for e in events],
                           "data": _jsonable(data), "fakes": self._fakes()})

    def note(self, actor, role, call, args_view, out, code, data):
        """Строка следа для вызова, уже выполненного внутри подделки (шов S5), без своих событий."""
        self._record(actor, role, call, args_view, out, None, [], code, None, data)

    def _invoke(self, actor, role, call, fn, args_view, case_id=None, code_fn=None, data_fn=None, verdict_fn=None):
        seq0 = self.peek.max_seq() if self.peek is not None else None
        c0 = self.peek.counts() if self.peek is not None else None
        try:
            out = fn()
        except Exception as e:  # noqa: BLE001 — строка следа, затем исключение наверх (провал шага)
            self._record(actor, role, call, args_view, None, case_id, [], "exception", None,
                         {"exception": type(e).__name__, "message": str(e)[:300]})
            raise
        events = self.peek.events_after(seq0) if (self.peek is not None and seq0 is not None) else []
        c1 = self.peek.counts() if (self.peek is not None and c0 is not None) else None
        cid = case_id
        if cid is None and isinstance(out, dict) and isinstance(out.get("case_id"), str):
            cid = out.get("case_id")
        self._record(actor, role, call, args_view, out, cid, events,
                     (code_fn or _outcome_code)(out), (verdict_fn or _outcome_verdict)(out),
                     (data_fn or _outcome_data)(out))
        if self.boris is not None and self.peek is not None:
            v = self.peek.ver(self.boris)
            self.check(v == 1, "§14: case_ver дела Бориса = 1 на всех шагах; после %s ver=%r" % (call, v))
        return out, events, c0, c1

    def _no_change(self, call, events, c0, c1):
        self.check(not events, "%s: событий быть не должно (§1.3, §8.1: отказы и чтения событий не порождают)" % call,
                   events)
        if c0 is not None and c1 is not None:
            diff = dict((t, (c0.get(t), c1.get(t))) for t in set(c0).union(c1) if c0.get(t) != c1.get(t))
            self.check(not diff, "%s: хранилище изменилось (§1.3)" % call, diff)

    def mut(self, actor, role, name, pos=(), kw=None, case_id=None, expect="ok", reason=None, allowed_cases=None,
            require_event=True):
        """Мутация Store (§5): исход, события и отсутствие лишних записей."""
        kw = dict(kw or {})
        store = self.stores[role]
        call = "Store." + name
        out, events, c0, c1 = self._invoke(actor, role, call, lambda: getattr(store, name)(*pos, **kw),
                                           {"pos": list(pos), "kw": kw}, case_id)
        self.check(isinstance(out, dict), "%s: исход не Outcome (§1.2)" % call, out)
        code = out.get("code")
        codes = (expect,) if isinstance(expect, str) else tuple(expect)
        self.check(code in codes, "%s: код %r, ожидался %s" % (call, code, "|".join(codes)), out)
        if reason is not None:
            self.check(str(out.get("reason") or "").startswith(reason),
                       "%s: причина %r, ожидалась %s (§12)" % (call, out.get("reason"), reason), out)
        if code == "unknown":
            self.check(out.get("missing") and out.get("ask"), "%s: unknown без missing/ask (§1.2, К4-C5)" % call, out)
        if case_id is not None and isinstance(out.get("case_id"), str):
            self.check(out["case_id"] == case_id, "%s: исход о другом деле" % call, out)
        if code == "ok":
            if require_event:
                self.check(events, "%s: ok без главного события (§1.3, I5)" % call, out)
            es = out.get("event_seq")
            if es is not None and events:
                self.check(es in [e["seq"] for e in events], "%s: event_seq исхода не среди событий вызова" % call,
                           (es, [e["seq"] for e in events]))
            if callable(allowed_cases):
                allowed = allowed_cases(out)
            elif allowed_cases is not None:
                allowed = set(allowed_cases)
            else:
                allowed = set([self.boris, None])
            bad = [e for e in events if e.get("case_id") not in allowed]
            self.check(not bad, "%s: событие в чужом деле (§14: дело Ивана не меняется)" % call, bad)
        else:
            self._no_change(call, events, c0, c1)
        return out, events

    def read_call(self, actor, role, name, pos=(), kw=None, case_id=None, code_fn=None, data_fn=None):
        """Чтение Store: ни события, ни строки."""
        kw = dict(kw or {})
        store = self.stores[role]
        call = "Store." + name
        out, events, c0, c1 = self._invoke(actor, role, call, lambda: getattr(store, name)(*pos, **kw),
                                           {"pos": list(pos), "kw": kw}, case_id, code_fn, data_fn)
        self._no_change(call, events, c0, c1)
        return out

    def port(self, actor, role, call, fn, args_view, code_fn=None, data_fn=None):
        """Вызов порта-подделки или конструктора/закрытия Store: в хранилище дела не пишет."""
        out, events, c0, c1 = self._invoke(actor, role, call, fn, args_view, None,
                                           code_fn or (lambda r: "ok"), data_fn or (lambda r: {}), lambda r: None)
        self._no_change(call, events, c0, c1)
        return out

    def open_store(self, role, actor):
        kw = {"role": role, "clock": self.clock, "new_id": self.ids, "params": self.params}
        st = self.port(actor, role, "Store", lambda: self.RC.Store(self.db_path, **kw),
                       {"path": "<db>", "role": role, "params": "variant:" + self.variant},
                       data_fn=lambda s: {"role": role, "store_id": getattr(s, "store_id", None),
                                          "boot_id": getattr(s, "boot_id", None)})
        self.check(getattr(st, "store_id", None) == self.store_id,
                   "Store(role=%s): store_id не тот (Д1: store_id один)" % role, getattr(st, "store_id", None))
        self.check(getattr(st, "boot_id", None), "Store(role=%s): нет boot_id (§5, §1.1)" % role)
        self.stores[role] = st
        return st

    def ensure_store(self, role, actor):
        if role not in self.stores:
            self.open_store(role, actor)
        return self.stores[role]

    def close_stores(self):
        for role in list(self.stores):
            try:
                self.stores[role].close()
            except Exception:  # noqa: BLE001 — закрытие в конце прогона, исход не влияет
                pass

    def rental_read(self, actor, role):
        r = self.port(actor, role, "RentalSource.read", self.source.read, {"source": F.CLIENTS_SOURCE},
                      code_fn=lambda x: "ok" if x.get("ok") else "unknown",
                      data_fn=lambda x: {"rows": sorted(int(y.get("row")) for y in (x.get("rows") or [])),
                                         "source": x.get("source")})
        self.check(r.get("ok") and isinstance(r.get("rows"), list), "RentalSource.read (подделка) не дал строк", r)
        return r

    # --- чтения схемы
    def exp_row(self, exp_id):
        return self.peek.one("SELECT * FROM rc_expect WHERE exp_id = ?", (exp_id,))

    def task_row(self):
        return self.peek.one("SELECT task_id, case_id, kind, state, top_stage, case_ver FROM rc_task "
                             "WHERE task_id = ?", (self.task,))

    def stages(self):
        return [(r["stage"], r["evidence_kind"]) for r in
                self.peek.rows("SELECT stage, evidence_kind FROM rc_stage WHERE task_id = ? ORDER BY id",
                               (self.task,))]

    def obligations(self, case_id):
        return self.peek.rows("SELECT id, kind, role, direction, state, outcome, required, closed_by, row_ver "
                              "FROM rc_obligation WHERE case_id = ? ORDER BY id", (case_id,))

    def has_event(self, events, etype, case_id=None):
        return any(e.get("type") == etype and (case_id is None or e.get("case_id") == case_id) for e in events)

    # ============================================================================================ шаги §14
    def d1(self):
        """Д1: Store.create(path); Store(role="wa"), Store(role="splinter") на одном файле → store_id один (§2, §5)."""
        base = self.params if self.params is not None else self.RC.PARAMS_DEFAULT
        for name in UNKNOWN_STAYS:
            self.check(base.get(name) == F.UNKNOWN, "§14: параметр %s обязан остаться UNKNOWN" % name, base.get(name))
        sid = self.port("test", "test", "Store.create",
                        lambda: self.RC.Store.create(self.db_path, clock=self.clock, new_id=self.ids),
                        {"path": "<db>"}, code_fn=lambda s: "ok" if isinstance(s, str) and s else "bad",
                        data_fn=lambda s: {"store_id": s})
        self.check(isinstance(sid, str) and sid, "Store.create не вернул store_id (§5)", sid)
        self.store_id = sid
        self.peek = Peek(self.db_path)
        meta = dict((r["key"], r["value"]) for r in self.peek.rows("SELECT key, value FROM rc_meta"))
        self.check(meta.get("store_id") == sid and str(meta.get("schema_version")) == "1",
                   "rc_meta: store_id/schema_version (§2)", meta)
        filled = dict((t, n) for t, n in self.peek.counts().items() if t != "rc_meta" and n)
        self.check(not filled, "новое хранилище не пусто (§2)", filled)
        self.open_store("wa", "test")
        self.open_store("splinter", "test")
        self.check(self.stores["wa"].boot_id != self.stores["splinter"].boot_id, "boot_id ролей совпали (§5)")

    def d2(self):
        """Д2: open_case(845), open_case(812) → ok, ver 1; обязательства и паспорт-залог Бориса (§3.4, I25)."""
        self.open_store("test", "test")
        read = self.rental_read("test", "test")
        rows = dict((int(r.get("row")), r) for r in read["rows"])
        self.check(sorted(rows) == [IVAN_ROW, BORIS_ROW], "фикстура: строки 812 и 845", sorted(rows))
        opened = {}
        for rn in (BORIS_ROW, IVAN_ROW):
            row = rows[rn]
            src = {"name": read["source"], "ref": "строка %d" % rn, "method": "door", "read_at": read["read_at"],
                   "observed_at": read["observed_at"]}
            kw = {"origin": "test", "by": BY_TEST, "idem_key": "open:test:anchor:%s" % anchor_of_row(row),
                  "rental_row": row, "source": src}
            out, events = self.mut("test", "test", "open_case", (), kw,
                                   allowed_cases=lambda o: set([(o.get("data") or {}).get("case_id"), None]))
            data = out.get("data") or {}
            cid = data.get("case_id")
            self.check(isinstance(cid, str) and cid.startswith("RC-"), "open_case: data.case_id 'RC-…' (§1.1, §5.1)",
                       out)
            self.check(out.get("case_id") in (None, cid), "open_case: case_id исхода ≠ data.case_id", out)
            self.check(out.get("ver") == 1 and self.peek.ver(cid) == 1, "open_case: ver 1 (§4.1)", out)
            self.check(self.has_event(events, "case_opened", cid), "нет события case_opened (§8.1)", events)
            opened[rn] = (cid, out, events)
            if rn == BORIS_ROW:
                self.src_boris = dict(src)
        self.boris, self.ivan = opened[BORIS_ROW][0], opened[IVAN_ROW][0]
        self.check(self.boris != self.ivan, "два открытия дали одно дело (I1)")
        # --- Борис: обязательный набор §3.4 и документ passport_deposit (§14 Д2, I25, I46)
        obl = self.obligations(self.boris)
        got = sorted((o["kind"], o["role"]) for o in obl)
        self.check(got == BORIS_OBLIGATIONS, "§14 Д2/§3.4: обязательства Бориса", got)
        by_role = dict(((o["kind"], o["role"]), o) for o in obl)
        dep = by_role[("money", "deposit")]
        self.check(dep["state"] == "unknown" and dep["outcome"] == "unknown",
                   "money/deposit при passport: unknown/unknown (§3.4)", dep)
        self.check(by_role[("client", "notify_final")]["state"] == "unknown",
                   "client/notify_final при FINAL_NOTICE_REQUIRED=UNKNOWN: unknown (§3.4)",
                   by_role[("client", "notify_final")])
        self.check(all(o["required"] == 1 and o["closed_by"] is None for o in obl),
                   "обязательства open_case: required=1, не закрыты (I25)", obl)
        bdata = opened[BORIS_ROW][1].get("data") or {}
        self.check(sorted(bdata.get("obligations") or []) == sorted(o["id"] for o in obl),
                   "open_case data.obligations ≠ рождённым (§5.1)", bdata)
        self.check(any(e.get("type") == "obligation_opened" and _payload(e).get("role") == "deposit"
                       and str(_payload(e).get("why") or "").startswith("deposit_passport")
                       for e in opened[BORIS_ROW][2]),
                   "нет obligation_opened(deposit, why=deposit_passport) (§3.4, §8.1)", opened[BORIS_ROW][2])
        docs = self.peek.rows("SELECT id, kind, ext_id, status, cover_from, cover_to, cover_basis FROM rc_document "
                              "WHERE case_id = ?", (self.boris,))
        self.check(len(docs) == 1 and docs[0]["kind"] == "passport_deposit" and docs[0]["status"] == "unverified"
                   and docs[0]["ext_id"] == "deposit:%d" % BORIS_ROW,
                   "документ passport_deposit (unverified, ext_id deposit:845) (§3.4, §14 Д2)", docs)
        self.check(docs[0]["cover_from"] is None and docs[0]["cover_to"] is None and docs[0]["cover_basis"] is None,
                   "I46: open_case покрытия не пишет", docs)
        self.check(sorted(bdata.get("documents") or []) == [docs[0]["id"]], "open_case data.documents (§5.1)", bdata)
        # --- Иван: свой набор §3.4, документов нет
        iobl = self.obligations(self.ivan)
        igot = sorted((o["kind"], o["role"]) for o in iobl)
        self.check(igot == IVAN_OBLIGATIONS, "§3.4: обязательства Ивана («В аренде», залог 3000)", igot)
        iby = dict(((o["kind"], o["role"]), o) for o in iobl)
        for role in ("deposit", "deposit_refund"):
            o = iby[("money", role)]
            self.check(o["state"] == "open" and o["outcome"] == "incomplete",
                       "money/%s при залоге числом: open/incomplete (§3.4)" % role, o)
        idocs = self.peek.rows("SELECT id FROM rc_document WHERE case_id = ?", (self.ivan,))
        self.check(not idocs and not (opened[IVAN_ROW][1].get("data") or {}).get("documents"),
                   "у Ивана документов нет", idocs)
        self.ivan_snap = self.peek.case_snapshot(self.ivan)
        self.boris_obl0 = obl

    def d3(self):
        """Д3: on_client_inbound(контакт Бориса, wa:in:501) → ok; client_inbound в деле Бориса, Иван не задет (§5.5)."""
        kw = {"contact": {"channel": "wa", "value": BORIS_WA}, "ref": WA_REF, "at": self.now(), "by": BY_WA,
              "idem_key": "in:wa:%s" % WA_REF}
        out, events = self.mut("wa", "wa", "on_client_inbound", (), kw, case_id=self.boris)
        main = [e for e in events if e.get("type") == "client_inbound"]
        self.check(main, "нет события client_inbound (§8.1)", events)
        dump = json.dumps([_payload(e) for e in main], ensure_ascii=False)
        self.check(self.boris in dump, "client_inbound: дела Бориса нет в payload.cases (§8.1)", dump)
        self.check(self.ivan not in dump, "client_inbound задел дело Ивана (контакт Ивана другой)", dump)
        self.check(any(e.get("case_id") == self.boris for e in events),
                   "нет события в деле Бориса (подсобытие #n, §8.1)", events)

    def d4(self):
        """Д4: resolve(client, future, контакт от кода) → found: дело Бориса, а не текущая аренда Ивана того же байка
        (I17, I36, I38); facts_for_agent — fact с частями §8.4 (I22, I45, F2 К3)."""
        read = self.rental_read("wa", "wa")
        kw = {"purpose": "client", "intent": "future", "contact": {"channel": "wa", "value": BORIS_WA},
              "rows": read["rows"], "moment": self.now(), "observed_at": read["observed_at"]}
        res = self.read_call("wa", "wa", "resolve", (), kw,
                             code_fn=lambda r: r.get("code") if isinstance(r, dict) else type(r).__name__,
                             data_fn=_resolve_data)
        self.check(isinstance(res, dict) and res.get("code") == "found", "resolve(client, future): ожидался found", res)
        self.check(res.get("case_id") == self.boris,
                   "resolve: не дело Бориса (текущая аренда Ивана того же байка — не ответ, I17)", res)
        if isinstance(res.get("row"), dict):
            self.check(str(res["row"].get("row")) == str(BORIS_ROW), "resolve: выбрана не строка 845", res.get("row"))
        if res.get("ver") is not None:
            self.check(res.get("ver") == 1, "resolve: ver дела", res)
        fa = self.read_call("wa", "wa", "facts_for_agent", (self.boris,), {}, case_id=self.boris,
                            code_fn=lambda r: r.get("outcome") if isinstance(r, dict) else type(r).__name__,
                            data_fn=_fa_data)
        self.check_facts_for_agent(fa)

    def check_facts_for_agent(self, fa):
        self.check(isinstance(fa, dict) and fa.get("outcome") == "fact", "facts_for_agent: outcome=fact (§8.3)", fa)
        self.check(fa.get("tool") == "case", "facts_for_agent: tool=case (§8.3)", fa.get("tool"))
        self.check(fa.get("version") == "case_ver:1",
                   "§8.3/§8.4: version = \"case_ver:<n>\" — версия ДЕЛА, не источника", fa.get("version"))
        facts = fa.get("facts")
        self.check(isinstance(facts, list) and facts, "facts_for_agent: facts пуст", fa)
        kinds = set(f.get("kind") for f in facts if isinstance(f, dict))
        miss = [k for k in FA_KINDS if k not in kinds]
        self.check(not miss, "§8.4 (Д2): нет частей %s" % ",".join(miss), sorted(str(k) for k in kinds))
        for f in facts:
            where = str(f.get("kind"))
            self._check_src(f, where)
            for sub in ("contacts", "cash", "history"):                 # вложенные элементы частей §8.4
                for c in f.get(sub) or []:
                    self._check_src(c, "%s.%s" % (where, sub))
            for sub in ("state", "close_fact", "close_second"):
                if isinstance(f.get(sub), dict):
                    self._check_src(f[sub], "%s.%s" % (where, sub))
        case = [f for f in facts if f.get("kind") == "case"]
        self.check(len(case) == 1 and case[0].get("case_id") == self.boris, "часть case: ровно одна, дело Бориса", case)
        # версия дела: ключ case_ver (пример §8.3) или ver (ключ части §8.4 «без переименований») — расхождение
        # самого контракта; демо принимает любой из двух, но значение обязано быть 1
        cver = case[0]["case_ver"] if "case_ver" in case[0] else case[0].get("ver")
        self.check(cver == 1, "часть case: версия дела 1 (§8.3/§8.4)", case[0])
        csrc = case[0]["src"]
        self.check(csrc.get("source") == "rental_case" and csrc.get("ref") == self.boris and csrc.get("method") == "event",
                   "§8.4 вывод src дела: rental_case / case_id / event", csrc)
        client = [f for f in facts if f.get("kind") == "case_client"]
        self.check(len(client) == 1 and client[0].get("name_seen") == "Борис", "часть клиент: имя Борис (§8.4)", client)
        contacts = client[0].get("contacts")
        self.check(isinstance(contacts, list) and len(contacts) == 1, "часть клиент: один контакт из U строки (§5.1)",
                   contacts)
        c = contacts[0]
        self.check(c.get("channel") == "wa" and c.get("status") == "active" and c.get("source_kind") == "crm"
                   and str(c.get("value_masked") or "").endswith(BORIS_WA[-4:]),
                   "контакт клиента: wa, active, crm, маска по хвосту (§5.1, §8.3, §1.1)", c)
        rental = [f for f in facts if f.get("kind") == "case_rental"]
        self.check(len(rental) == 1, "часть аренда: ровно одна текущая привязка", rental)
        r = rental[0]
        self.check(r.get("crm_row_seen") == BORIS_ROW and r.get("start_day") == "2026-10-15"
                   and r.get("end_day") == "2026-10-20" and r.get("bound_by") == "anchor",
                   "часть аренда: строка 845, 15.10–20.10, привязка по якорю (Y пуст)", r)
        money = [f for f in facts if f.get("kind") == "case_money"]
        self.check(money and all(m.get("payment_confirmed") is False for m in money),
                   "I45: case_money.payment_confirmed=false у каждого", money)
        self.check(sorted(str(m.get("role")) for m in money) == ["deposit", "rent"],
                   "часть деньги: rent и deposit Бориса (§3.4)", money)
        docs = [f for f in facts if f.get("kind") == "case_document"]
        self.check(any(d.get("doc_kind") == "passport_deposit" and d.get("status") == "unverified" for d in docs),
                   "часть документы: passport_deposit (unverified)", docs)
        others = [f for f in facts if f.get("kind") == "case_obligation"]
        self.check(sorted((str(o.get("obl_kind")), str(o.get("role"))) for o in others)
                   == sorted(x for x in BORIS_OBLIGATIONS if x[0] != "money"),
                   "часть obligations_other: bike/document/client Бориса, kind → obl_kind (§8.3, §8.4)", others)
        # «у всех строк дела — 6 полей src из source» open_case (§5.1, К4-C36: значения = колонкам строки)
        s0 = self.src_boris or {}
        born = [("case_rental", r), ("case_client", client[0]), ("contact", c)] + [("case_money", m) for m in money] \
            + [("case_document", d) for d in docs] + [("case_obligation", o) for o in others]
        for where, item in born:
            s = item["src"]
            self.check(s.get("source") == s0.get("name") and s.get("method") == "door"
                       and s.get("read_at") == s0.get("read_at") and s.get("observed_at") == s0.get("observed_at")
                       and str(BORIS_ROW) in str(s.get("ref")),
                       "К4-C36: src элемента %s не из source open_case" % where, (s, s0))
        for item in (r, client[0]):
            self.check(item["src"].get("ref") == s0.get("ref"), "§2/§8.4: src.ref аренды и клиента = source.ref",
                       (item["src"], s0))
        self.check(not any(v is not None for v in _keys_valued(fa, "source_ver")),
                   "§8.4 F2: версия внешнего источника неизвестна (source_ver заполнен)", fa)
        dump = json.dumps(_jsonable(fa), ensure_ascii=False)
        self.check(self.ivan not in dump and "Иван" not in dump, "facts_for_agent Бориса несёт данные Ивана", dump[:400])
        self.check(BORIS_WA not in dump, "§1.1/§8.3: номер клиента агенту — только маской (value_masked)", dump[:400])

    def _check_src(self, item, where):
        src = item.get("src") if isinstance(item, dict) else None
        self.check(isinstance(src, dict), "I22/§8.4: у элемента %s нет src" % where, item)
        miss = [k for k in SRC_KEYS if k not in src]
        self.check(not miss, "I22/§8.4: src элемента %s неполон (нет %s)" % (where, ",".join(miss)), src)
        self.check(src.get("method") in SRC_METHODS, "§2: src.method элемента %s вне словаря" % where, src)
        self.check(all(_is_num(src.get(k)) for k in ("read_at", "observed_at")),
                   "§1.1/§8.4: src.read_at/observed_at элемента %s — не время числом" % where, src)
        self.check(src.get("case_ver") == 1, "I22/§8.4: src.case_ver элемента %s ≠ 1 (дело Бориса на версии 1)" % where,
                   src)

    def d5(self):
        """Д5: open_task(readiness, ref=wa:in:501, expect_ver=1) → ok, task_id. Б: от агента — rejected(param_unknown)
        (AUTO_ASK, К4-C17), от одобряющего — ok. Пробы: I7 duplicate, I32 conflict."""
        def kw(by, kind="readiness"):
            return {"kind": kind, "ref": WA_REF, "by": by, "expect_ver": 1,
                    "idem_key": "task:%s:1:readiness:%s" % (self.boris, WA_REF)}
        if self.is_a:
            actor, role, by = "agent", "wa", BY_AGENT
        else:
            self.mut("agent", "wa", "open_task", (self.boris,), kw(BY_AGENT), case_id=self.boris,
                     expect="rejected", reason="param_unknown")
            self.ensure_store("human", self.approver_actor)
            actor, role, by = self.approver_actor, "human", self.approver
        out, events = self.mut(actor, role, "open_task", (self.boris,), kw(by), case_id=self.boris)
        tid = (out.get("data") or {}).get("task_id")
        self.check(isinstance(tid, str) and tid.startswith("RT-"), "open_task: data.task_id 'RT-…' (§1.1, §14 Д5)", out)
        self.task = tid
        t = self.task_row()
        self.check(t and t["case_id"] == self.boris and t["kind"] == "readiness" and t["state"] == "open"
                   and t["top_stage"] == 0 and t["case_ver"] == 1, "rc_task после open_task (§4.5)", t)
        self.check(self.has_event(events, "task_opened", self.boris), "нет события task_opened (§8.1)", events)
        dup, _ = self.mut("probe:I7", role, "open_task", (self.boris,), kw(by), case_id=self.boris,
                          expect="duplicate")
        if out.get("event_seq") is not None:
            self.check(dup.get("event_seq") == out.get("event_seq"),
                       "I7/§1.3: duplicate отдаёт event_seq первого раза", (out.get("event_seq"), dup.get("event_seq")))
        self.mut("probe:I32", role, "open_task", (self.boris,), kw(by, kind="delivery"), case_id=self.boris,
                 expect="conflict", reason="idem_payload_mismatch")
        self.check(self.task_row()["kind"] == "readiness", "I32: задача изменилась после conflict")

    def d6(self):
        """Д6: request_staff_question(байк, q_ru, q_th, urgency, expect_ver=1) → ok, ожидание planned (§4.2, §5.4).
        Б: от агента — rejected(param_unknown) (AUTO_ASK), от одобряющего — ok."""
        qsha = hashlib.sha1(("байк|" + Q_RU).encode("utf-8")).hexdigest()[:12]

        def kw(by):
            return {"task_id": self.task, "staff_kind": "байк", "q_ru": Q_RU, "q_th": Q_TH, "urgency": URGENCY,
                    "by": by, "expect_ver": 1, "idem_key": "ask:%s:1:%s:%s:1" % (self.boris, self.task, qsha)}
        if self.is_a:
            actor, role, by = "agent", "wa", BY_AGENT
        else:
            self.mut("agent", "wa", "request_staff_question", (self.boris,), kw(BY_AGENT), case_id=self.boris,
                     expect="rejected", reason="param_unknown")
            actor, role, by = self.approver_actor, "human", self.approver
        out, events = self.mut(actor, role, "request_staff_question", (self.boris,), kw(by), case_id=self.boris)
        exp = (out.get("data") or {}).get("exp_id")
        self.check(isinstance(exp, str) and exp.startswith("RE-"), "request_staff_question: data.exp_id 'RE-…'", out)
        self.exp = exp
        r = self.exp_row(exp)
        self.check(r and r["kind"] == "staff_question" and r["place"] == "topic" and r["state"] == "planned"
                   and r["task_id"] == self.task and r["case_id"] == self.boris and r["case_ver"] == 1,
                   "ожидание planned, главное место topic (§4.2, STAFF_PLACES[байк])", r)
        self.check(r["business_due_at"] is None, "I43: срока у ожидания нет (WAIT_BEFORE_AGENTS=UNKNOWN)", r)
        self.check(self.has_event(events, "expectation_planned"), "нет события expectation_planned (§8.1)", events)

    def d7(self):
        """Д7: claim_for_posting → StaffAskPort.post → mark_post_result(posted=[тема 7001/55, Delivery 7002]) → waiting,
        question_sent, business_due_at NULL; due_expectations(now+48 ч) == [] (I43, M27). Шов S3/S7 на подделке."""
        spl = self.stores["splinter"]
        claimed, events, c0, c1 = self._invoke(
            "splinter", "splinter", "Store.claim_for_posting", lambda: spl.claim_for_posting(by=BY_SPL),
            {"kw": {"by": BY_SPL}}, self.boris, _list_code,
            lambda l: {"exp_ids": [x.get("exp_id") for x in l] if isinstance(l, list) else None})
        self.check(isinstance(claimed, list) and len(claimed) == 1 and claimed[0].get("exp_id") == self.exp,
                   "claim_for_posting: ровно наше ожидание", claimed)
        self.check(events and all(e.get("case_id") in (self.boris, None) for e in events),
                   "claim_for_posting: событие захвата в деле Бориса (§4.2, I5)", events)
        r = self.exp_row(self.exp)
        self.check(r["state"] == "in_flight" and r["claimed_by"] == "splinter" and r["claim_boot"] == spl.boot_id,
                   "захват: in_flight, claimed_by=splinter, claim_boot=boot_id (§4.2)", r)
        post = self.port("splinter", "splinter", "StaffAskPort.post",
                         lambda: F.run_coro(self.staff_port.post(claimed[0])), {"exp_id": self.exp},
                         code_fn=_port_code, data_fn=_post_data)
        self.check(isinstance(post, dict) and post.get("posted"), "StaffAskPort.post: posted (§9.1)", post)
        got = sorted((p.get("place"), p.get("chat"), str(p.get("msg_id")), p.get("thread_id")) for p in post["posted"])
        want = sorted([("topic", SERVICING_CHAT, TOPIC_MID, TOPIC_THREAD), ("delivery", DELIVERY_CHAT, DELIVERY_MID,
                                                                            None)])
        self.check(got == want, "§14 Д7: посты тема 7001 (тема 55) и Delivery 7002", got)
        self.check(self.counters.staff_posts == 2, "постов подделки staff_ask 2", self.counters.snapshot())
        qid = post.get("qid")
        ask = self.staff_ask.asks.get(qid) if qid else None
        self.check(ask is not None and ask.get("managed_by") == "rental_case" and ask.get("expect_id") == self.exp,
                   "шов S3: запись staff_ask с expect_id и managed_by=rental_case (§13)", ask)
        self.check(self.staff_ask.dlive_marks == [], "шов S7: пост вопроса дела не передан решателю (§13)",
                   self.staff_ask.dlive_marks)
        rv = self.exp_row(self.exp)["row_ver"]
        out, events = self.mut("splinter", "splinter", "mark_post_result", (self.exp,),
                               {"result": post, "by": BY_SPL, "expect_row_ver": rv,
                                "idem_key": "mark_post_result:%s:%s" % (self.exp, rv)}, case_id=self.boris)
        r = self.exp_row(self.exp)
        self.check(r["state"] == "waiting" and r["next_check"] == "await_answer", "ожидание waiting/await_answer (§4.2)",
                   r)
        self.check(r["business_due_at"] is None and r["due_basis"] == "none",
                   "§14 Д7: business_due_at=NULL, due_basis=none (I43)", r)
        self.check(r["ext_qid"] == qid, "ext_qid = qid staff_ask (S1, §2)", r)
        posts = self.peek.rows("SELECT chat, msg_id, exp_id, place, role, thread_id, topic_bike, addressee_ids "
                               "FROM rc_post WHERE exp_id = ? ORDER BY msg_id", (self.exp,))
        pk = sorted((p["chat"], str(p["msg_id"]), p["place"], p["role"]) for p in posts)
        self.check(pk == sorted([(SERVICING_CHAT, TOPIC_MID, "topic", "question"),
                                 (DELIVERY_CHAT, DELIVERY_MID, "delivery", "delivery")]), "rc_post (§2, §4.2)", posts)
        by_place = dict((p["place"], p) for p in posts)
        self.check(str(by_place["topic"]["thread_id"]) == TOPIC_THREAD, "rc_post: тема поста вопроса 55", posts)
        self.check(all(str(p["topic_bike"] or "") == PLATE for p in posts),
                   "К4-C9/§4.7 п.5: topic_bike = номер привязки у мест topic/delivery", posts)
        if self.is_a:
            self.check(_addressees(by_place["topic"]["addressee_ids"]) == [STAFF_ID]
                       and _addressees(by_place["delivery"]["addressee_ids"]) == [9002],
                       "адресаты поста из STAFF_ADDRESSEES (M3)", posts)
        else:
            self.check(all(_addressees(p["addressee_ids"]) == F.UNKNOWN for p in posts),
                       "§14 Б Д7: addressee_ids=\"UNKNOWN\"", posts)
        self.check(self.stages() == [("question_sent", "post")], "ступень question_sent в той же транзакции (§4.2)",
                   self.stages())
        self.check(self.task_row()["top_stage"] == 1, "top_stage 1", self.task_row())
        self.check(self.has_event(events, "stage_recorded", self.boris), "нет события stage_recorded (§8.1)", events)
        later = self.now() + H48
        due = self.read_call("splinter", "splinter", "due_expectations", (), {"now": later}, case_id=self.boris,
                             code_fn=_list_code, data_fn=lambda l: {"n": len(l) if isinstance(l, list) else None})
        self.check(due == [], "§14 Д7/I43/M27: due_expectations(now+48 ч) == []", due)
        rv = self.exp_row(self.exp)["row_ver"]
        self.mut("probe:I43", "splinter", "claim_escalation", (self.exp,),
                 {"by": BY_SPL, "expect_row_ver": rv, "idem_key": "claim_escalation:%s:%s" % (self.exp, rv)},
                 case_id=self.boris, expect="rejected", reason="param_unknown")
        self.check(self.exp_row(self.exp)["state"] == "waiting", "I43/M27: claim_escalation кодом сдвинул ожидание",
                   self.exp_row(self.exp))
        n = self.port("splinter", "splinter", "FakeStaffAsk.tick",
                      lambda: F.run_coro(self.staff_ask.tick(self.telegram.send, agents_chat=AGENTS_CHAT, now=later)),
                      {"now": later}, data_fn=lambda k: {"escalated": k})
        self.check(n == 0 and self.counters.escalations == 0, "шов S3: tick подделки дело не эскалирует (§13)", n)
        self.check(qid not in self.staff_ask.due(later), "шов S3: due() подделки пропускает вопрос дела", qid)

    def d8(self):
        """Д8: закрыть и открыть Store(role=splinter) заново; recover() → ok, изменений 0; ожидание waiting на месте
        (I29, К4-C12)."""
        old = self.stores["splinter"]
        old_boot = old.boot_id
        before = self.exp_row(self.exp)
        self.port("splinter", "splinter", "Store.close", old.close, {"role": "splinter"})
        self.stores.pop("splinter")
        new = self.open_store("splinter", "splinter")
        self.check(new.boot_id != old_boot, "новый Store — новый boot_id (§5)", (old_boot, new.boot_id))
        c0 = self.peek.counts()
        out, events = self.mut("splinter", "splinter", "recover", (), {"by": BY_SPL}, allowed_cases=[None],
                               require_event=False)
        data = out.get("data") or {}
        self.check(all(data.get(k) == 0 for k in ("expect", "escalation", "notice")),
                   "recover: изменений 0 (§5: data expect/escalation/notice)", data)
        self.check(self.exp_row(self.exp) == before, "ожидание после рестарта не то же (§14 Д8, I29)",
                   (before, self.exp_row(self.exp)))
        c1 = self.peek.counts()
        diff = dict((t, (c0.get(t), c1.get(t))) for t in set(c0).union(c1)
                    if t != "rc_event" and c0.get(t) != c1.get(t))
        self.check(not diff, "recover изменил строки дела", diff)

    def _brain_append(self, line):
        """Подделка записи мозга для шва S5 — только список в памяти (боевых записей нет)."""
        self.brain_lines.append(line)
        return True, ""

    def d9(self):
        """Д9: ответ сотрудника 9001 реплаем на 7001 в теме 55 через обработчик S5 (дело первым, мозг потом).
        А: ok(accepted), ожидание answered, ступень answer_received, факт staff_answer. Б: ok(reference_author_unverified),
        ожидание waiting, ступени 2 нет, due_expectations(now+48 ч) == []. Проба I10/M6 (А)."""
        box = {}

        def store_call(**kw):
            try:
                out, _ = self.mut(STAFF_ACTOR, "splinter", "on_staff_answer", (), kw, case_id=self.boris)
            except DemoFailure as e:
                box["fail"] = e
                raise
            except Exception as e:  # noqa: BLE001 — обработчик S5 глотает исключение; поднимем после него
                box["exc"] = (e, traceback.format_exc())
                raise
            box["out"] = out
            return out

        handler = F.FakeReplyHandler(store_call, self.staff_ask, self._brain_append)
        case_out, brain_out = handler.handle(SERVICING_CHAT, ANSWER_MID, TOPIC_MID, True, TOPIC_THREAD, STAFF_ID,
                                             STAFF_NAME, False, ANSWER_TEXT, self.now())
        if "fail" in box:
            raise box["fail"]
        if "exc" in box:
            say(box["exc"][1])
            raise box["exc"][0]
        self.check("out" in box, "S5: обработчик реплая не дошёл до дела", case_out)
        self.note(STAFF_ACTOR, "splinter", "FakeStaffAsk.on_reply",
                  {"chat": SERVICING_CHAT, "reply_to": TOPIC_MID, "mid": ANSWER_MID}, brain_out,
                  "ok" if isinstance(brain_out, dict) and brain_out.get("recorded") else "not_recorded",
                  {"recorded": bool(isinstance(brain_out, dict) and brain_out.get("recorded"))})
        self.check(handler.order == ["case", "brain"], "S5: дело — первым, мозг — потом (§13)", handler.order)
        out = box["out"]
        data = out.get("data") or {}
        if data.get("exp_id") is not None:
            self.check(data.get("exp_id") == self.exp, "on_staff_answer: data.exp_id не наше ожидание", data)
        ans = self.peek.rows("SELECT id, exp_id, case_id, post_role, author_id, verdict, decision, execute, case_ver_at "
                             "FROM rc_answer WHERE chat = ? AND msg_id = ?", (SERVICING_CHAT, ANSWER_MID))
        self.check(len(ans) == 1 and ans[0]["exp_id"] == self.exp and ans[0]["author_id"] == STAFF_ID
                   and ans[0]["post_role"] == "question" and ans[0]["execute"] == 0,
                   "rc_answer: строка ответа (§4.7: пишется для шагов 4–11)", ans)
        self.check(ans[0]["decision"] == "unclear",
                   "§4.7/§4.8: колонка decision пишется всегда; accept_decision при ACCEPT_WORDS=UNKNOWN → unclear", ans)
        if data.get("answer_id") is not None:
            self.check(data.get("answer_id") == ans[0]["id"], "on_staff_answer: data.answer_id ≠ rc_answer.id", data)
        r = self.exp_row(self.exp)
        if self.is_a:
            self.check(data.get("verdict") == "accepted", "§14 Д9: verdict=accepted", out)
            self.check(data.get("stage") == "answer_received", "§14 Д9: ступень answer_received в исходе (§5.4)", out)
            self.check(data.get("decision") == "unclear",
                       "§4.7/§4.8: decision=accept_decision при ACCEPT_WORDS=UNKNOWN → unclear", out)
            self.check(ans[0]["verdict"] == "accepted" and ans[0]["case_id"] == self.boris and ans[0]["case_ver_at"] == 1,
                       "rc_answer: accepted, дело Бориса, версия 1", ans)
            self.check(r["state"] == "answered" and r["next_check"] == "none" and r["answer_id"] == ans[0]["id"],
                       "§14 Д9: ожидание answered (§4.2)", r)
            self.check(self.stages() == STAGES_A[:2], "§14 Д9: ступени question_sent, answer_received", self.stages())
            self.check(self.task_row()["top_stage"] == 2 and self.task_row()["state"] == "open", "задача: ступень 2",
                       self.task_row())
            facts = self.peek.rows("SELECT id, fkey, state FROM rc_fact WHERE case_id = ? AND kind = 'staff_answer'",
                                   (self.boris,))
            self.check(len(facts) == 1 and facts[0]["state"] == "valid", "§14 Д9: факт staff_answer", facts)
            try:
                fkey = [str(x) for x in json.loads(facts[0]["fkey"])]
            except (TypeError, ValueError):
                fkey = None
            self.check(fkey == ["staff_answer", SERVICING_CHAT, ANSWER_MID], "§8.2: fkey ответа", facts)
            ev = {"kind": "staff_answer", "ref": "%s:%s" % (SERVICING_CHAT, ANSWER_MID), "answer_id": ans[0]["id"]}
            # ключ — канонический §11 (тот же, что у Д11): отказ ключа не расходует (§1.3), Д11 им же обязан пройти
            self.mut("probe:I10", "splinter", "record_stage", (self.boris,),
                     {"task_id": self.task, "stage": "physically_done", "evidence": ev, "by": BY_HUMAN,
                      "idem_key": "stage:%s:physically_done" % self.task},
                     case_id=self.boris, expect="rejected")
            self.check(self.stages() == STAGES_A[:2], "I10/M6: ступень 4 по staff_answer записана", self.stages())
        else:
            self.check(data.get("verdict") == "reference_author_unverified",
                       "§14 Б Д9: verdict=reference_author_unverified (STAFF_ADDRESSEES=UNKNOWN)", out)
            self.check(data.get("decision") is None, "§4.7: data.decision у справки — None", out)
            self.check(ans[0]["verdict"] == "reference_author_unverified", "rc_answer: справка", ans)
            self.check(r["state"] == "waiting", "§14 Б Д9: ожидание остаётся waiting", r)
            self.check(self.stages() == [("question_sent", "post")], "§14 Б Д9: ступени 2 нет", self.stages())
            due = self.read_call("splinter", "splinter", "due_expectations", (), {"now": self.now() + H48},
                                 case_id=self.boris, code_fn=_list_code,
                                 data_fn=lambda l: {"n": len(l) if isinstance(l, list) else None})
            self.check(due == [], "§14 Б: due_expectations(now+48 ч) == [] (I43)", due)

    def _stage_step(self, stage, ref, note, top_after):
        """Д10/Д11: record_stage(human_mark одобряющего 1001). Б: 1001 ∉ APPROVER_IDS → не ok, ничего не записано."""
        self.ensure_store("human", HUMAN_ACTOR)
        ev = {"kind": "human_mark", "ref": ref, "author_id": APPROVER_A, "act_ref": ref, "note": note}
        kw = {"task_id": self.task, "stage": stage, "evidence": ev, "by": BY_HUMAN,
              "idem_key": "stage:%s:%s" % (self.task, stage)}
        before = self.stages()
        if self.is_a:
            out, events = self.mut(HUMAN_ACTOR, "human", "record_stage", (self.boris,), kw, case_id=self.boris)
            self.check(self.stages() == before + [(stage, "human_mark")], "ступень %s (human_mark)" % stage,
                       self.stages())
            t = self.task_row()
            self.check(t["top_stage"] == top_after and t["state"] == "open", "задача после %s" % stage, t)
            self.check(self.has_event(events, "stage_recorded", self.boris), "нет события stage_recorded", events)
        else:
            self.mut(HUMAN_ACTOR, "human", "record_stage", (self.boris,), kw, case_id=self.boris,
                     expect=("rejected", "unknown"))
            self.check(self.stages() == before, "§14 Б: продвижение ступеней — провал", self.stages())

    def d10(self):
        """Д10: record_stage(task_accepted, human_mark(act_ref=btn:accept:1)) → ok (§3.6)."""
        self._stage_step("task_accepted", "btn:accept:1", "принял к исполнению", 3)

    def d11(self):
        """Д11: record_stage(physically_done, human_mark(act_ref=btn:done:1)) → ok (§3.6)."""
        self._stage_step("physically_done", "btn:done:1", "байк готов", 4)

    def d12(self):
        """Д12: expect_readback(result, {sink:fake, task_id}) → claim_execution → ResultSink.write → mark_written(ok) →
        ResultSink.read → on_readback(landed) → ступень result_recorded, задача done (I11). Б: места записи нет
        (RESULT_RECORD_PLACE[readiness]=UNKNOWN) — синк не зовётся, ступени 5 нет."""
        target = {"sink": "fake", "task_id": self.task}
        kw = {"task_id": self.task, "action": "result", "target": target, "by": BY_SPL, "expect_ver": 1,
              "idem_key": "readback:%s:1:%s:result" % (self.boris, self.task)}
        if not self.is_a:
            before = self.stages()
            self.mut("splinter", "splinter", "expect_readback", (self.boris,), kw, case_id=self.boris,
                     expect=("ok", "rejected", "unknown"))
            self.check(self.stages() == before and self.task_row()["state"] == "open",
                       "§14 Б: продвижение задачи — провал", (self.stages(), self.task_row()))
            self.check(self.counters.result_writes == 0, "§14 Б: запись результата без места", self.counters.snapshot())
            return
        out, events = self.mut("splinter", "splinter", "expect_readback", (self.boris,), kw, case_id=self.boris)
        rexp = (out.get("data") or {}).get("exp_id")
        if not rexp:
            cand = self.peek.rows("SELECT exp_id FROM rc_expect WHERE task_id = ? AND kind = 'readback'", (self.task,))
            self.check(len(cand) == 1, "expect_readback: ожидание readback не найдено", cand)
            rexp = cand[0]["exp_id"]
        r = self.exp_row(rexp)
        self.check(r and r["kind"] == "readback" and r["action"] == "result" and r["state"] == "planned"
                   and r["case_id"] == self.boris and r["case_ver"] == 1, "ожидание readback planned (§4.2)", r)
        try:
            tgt = json.loads(r["target"]) if r["target"] else None
        except (TypeError, ValueError):
            tgt = None
        self.check(isinstance(tgt, dict) and all(tgt.get(k) == v for k, v in target.items()),
                   "rc_expect.target несёт цель чтения назад (§2)", r["target"])
        rv = r["row_ver"]
        self.mut("splinter", "splinter", "claim_execution", (rexp,),
                 {"by": BY_SPL, "expect_row_ver": rv, "expect_ver": 1,
                  "idem_key": "claim_execution:%s:%s" % (rexp, rv)}, case_id=self.boris)
        r = self.exp_row(rexp)
        self.check(r["state"] == "in_flight" and r["next_check"] == "execute" and r["claimed_by"] == "splinter",
                   "claim_execution: in_flight/execute (§4.2)", r)
        self.clock.advance(5)
        w_at = self.now()
        task_view = {"task_id": self.task, "case_id": self.boris, "kind": "readiness"}
        value = {"task_id": self.task, "readiness": "ready", "day": "2026-10-15", "answer": ANSWER_TEXT}
        w = self.port("splinter", "splinter", "ResultSink.write", lambda: self.sink.write(task_view, value),
                      {"task": task_view, "value": value}, code_fn=lambda x: "ok" if x.get("ok") else "unknown",
                      data_fn=lambda x: {"ok": bool(x.get("ok"))})
        self.check(w.get("ok"), "ResultSink.write (подделка)", w)
        rv = self.exp_row(rexp)["row_ver"]
        self.mut("splinter", "splinter", "mark_written", (rexp,),
                 {"result": {"ok": True, "row": None, "written_at": w_at}, "by": BY_SPL, "expect_row_ver": rv,
                  "idem_key": "mark_written:%s:%s" % (rexp, rv)}, case_id=self.boris)
        r = self.exp_row(rexp)
        self.check(r["state"] == "waiting" and r["next_check"] == "readback", "mark_written(ok): waiting/readback", r)
        self.clock.advance(5)
        rd = self.port("splinter", "splinter", "ResultSink.read", lambda: self.sink.read(task_view),
                       {"task": task_view}, code_fn=lambda x: "ok" if x.get("outcome") == "landed" else x.get("outcome"),
                       data_fn=lambda x: {"outcome": x.get("outcome")})
        self.check(rd.get("outcome") == "landed" and rd.get("read_at") > w_at, "ResultSink.read: landed позже записи",
                   rd)
        ev = {"kind": "readback", "ref": "sink:fake:%s" % self.task, "source": "sink:fake", "written_at": w_at,
              "read_at": rd["read_at"], "outcome": "landed", "expected": value, "got": rd.get("value")}
        out, events = self.mut("splinter", "splinter", "on_readback", (rexp,),
                               {"evidence": ev, "by": BY_SPL, "idem_key": "on_readback:%s:landed" % rexp},
                               case_id=self.boris)
        self.check((out.get("data") or {}).get("stage") == "result_recorded",
                   "§14 Д12: ступень result_recorded в исходе (§4.2)", out)
        self.check(self.exp_row(rexp)["state"] == "answered", "readback answered (§4.2)", self.exp_row(rexp))
        t = self.task_row()
        self.check(t["state"] == "done" and t["top_stage"] == 5, "§14 Д12: задача done на ступени 5 (§3.5)", t)
        self.check(self.stages() == STAGES_A, "ступени 1–5 по порядку со своими свидетельствами (§3.6)", self.stages())
        rb = self.peek.rows("SELECT id FROM rc_fact WHERE case_id = ? AND kind = 'readback' AND state = 'valid'",
                            (self.boris,))
        self.check(len(rb) == 1, "факт readback (§4.2)", rb)
        self.check(self.counters.result_writes == 1 and self.counters.result_reads == 1,
                   "синк: одна запись, одно чтение (I15)", self.counters.snapshot())

    def d13(self):
        """Д13: allowed_actions → есть propose_client_notice (А); Б — нет (К4-C17)."""
        acts = self.read_call("splinter", "splinter", "allowed_actions", (self.boris,), {}, case_id=self.boris,
                              code_fn=_list_code, data_fn=lambda l: {"actions": _action_names(l)})
        self.check(isinstance(acts, list), "allowed_actions: список (§5.5)", acts)
        if self.is_a:
            self.check(_has_value(acts, "propose_client_notice"), "§14 Д13: есть propose_client_notice", acts)
        else:
            self.check("propose_client_notice" not in json.dumps(_jsonable(acts), ensure_ascii=False),
                       "§14 Б: allowed_actions без propose_client_notice", acts)

    def d14(self):
        """Д14: propose_client_notice(readiness_confirmed, fact_ids=[staff_answer, readback], expect_ver=1) → ok,
        уведомление intent — конец случая: черновика нет, клиенту ничего не уходит (§4.3, I42)."""
        facts = self.peek.rows("SELECT id, kind FROM rc_fact WHERE case_id = ? AND state = 'valid' "
                               "AND kind IN ('staff_answer', 'readback') ORDER BY id", (self.boris,))
        sa = [f["id"] for f in facts if f["kind"] == "staff_answer"]
        rb = [f["id"] for f in facts if f["kind"] == "readback"]
        kw = {"task_id": self.task, "intent": INTENT, "fact_ids": sa + rb, "by": BY_SPL, "expect_ver": 1,
              "idem_key": "notice:%s:1:%s:%s" % (self.boris, self.task, INTENT)}
        if not self.is_a:
            self.mut("splinter", "splinter", "propose_client_notice", (self.boris,), kw, case_id=self.boris,
                     expect=("rejected", "unknown"))
            self.check(not self.peek.rows("SELECT notice_id FROM rc_notice"), "§14 Б: намерение уведомить — провал")
            return
        self.check(len(sa) == 1 and len(rb) == 1, "факты staff_answer и readback для намерения", facts)
        out, events = self.mut("splinter", "splinter", "propose_client_notice", (self.boris,), kw, case_id=self.boris)
        notices = self.peek.rows("SELECT notice_id, case_id, task_id, intent, state, case_ver, draft_id, wamid "
                                 "FROM rc_notice")
        self.check(len(notices) == 1, "одно уведомление", notices)
        n = notices[0]
        self.check(str(n["notice_id"]).startswith("RN-") and n["case_id"] == self.boris and n["task_id"] == self.task
                   and n["intent"] == INTENT and n["state"] == "intent" and n["case_ver"] == 1,
                   "§14 Д14: уведомление intent текущей версии (§4.3)", n)
        self.check(n["draft_id"] is None and n["wamid"] is None, "§14 Д14: черновик не создаётся", n)
        nid = (out.get("data") or {}).get("notice_id")
        if nid is not None:
            self.check(nid == n["notice_id"], "propose_client_notice: data.notice_id ≠ rc_notice", out)
        self.check(self.has_event(events, "notice_proposed", self.boris), "нет события notice_proposed (§8.1)", events)
        self.check(self.notice_port.calls == [] and self.counters.notice_calls == 0,
                   "§14: вызовов NoticePort 0 (намерение — не черновик)", self.notice_port.calls)

    # ------------------------------------------------------------------------------------------------ итог
    def final_checks(self):
        snap = self.counters.snapshot()
        for k in FAKE_KEYS:
            self.check(snap.get(k) == FINAL_COUNTERS[k], "§14 счётчики: %s = %r, ожидалось %r" % (
                k, snap.get(k), FINAL_COUNTERS[k]), snap)
        self.check(snap.get("human_press_sends") == 0, "нажатий отправки нет", snap)
        self.check(F.net_attempts() == 0, "К4-C18: попытки сети", F.net_log())
        self.check(sorted(s["place"] for s in self.telegram.sent) == ["delivery", "topic"],
                   "§14: по одному посту на место (тема, Delivery); «Агентам» — ничего", self.telegram.sent)
        cases = self.peek.rows("SELECT case_id, ver, state, attention, link_state FROM rc_case")
        self.check(sorted(c["case_id"] for c in cases) == sorted([self.boris, self.ivan]),
                   "К4-C1: лишних дел нет", cases)
        b = [c for c in cases if c["case_id"] == self.boris][0]
        self.check(b["ver"] == 1 and b["state"] == "open" and b["attention"] == 0 and b["link_state"] == "ok",
                   "дело Бориса: ver 1, open, без внимания, привязка ok", b)
        self.check(self.peek.case_snapshot(self.ivan) == self.ivan_snap, "§14: дело Ивана изменилось после Д2")
        self.check(self.obligations(self.boris) == self.boris_obl0,
                   "обязательства Бориса изменились (готовность их не закрывает, §3.4)", self.obligations(self.boris))
        roles = sorted(r["role"] for r in self.peek.rows("SELECT role FROM rc_post"))
        self.check(roles == ["delivery", "question"], "rc_post: вопрос и Delivery, эскалаций нет (I41)", roles)
        t = self.task_row()
        notices = self.peek.rows("SELECT notice_id, state, draft_id, wamid FROM rc_notice")
        if self.is_a:
            self.check(t["state"] == "done" and t["top_stage"] == 5, "задача done на ступени 5", t)
            self.check(len(notices) == 1 and notices[0]["state"] == "intent", "в конце — одно намерение", notices)
        else:
            self.check(t["state"] == "open" and t["top_stage"] == 1, "§14 Б: задача дальше ступени 1 не пошла", t)
            self.check(self.stages() == [("question_sent", "post")], "§14 Б: ступени", self.stages())
            self.check(self.exp_row(self.exp)["state"] == "waiting", "§14 Б: ожидание waiting", self.exp_row(self.exp))
            self.check(not notices, "§14 Б: намерений нет", notices)
        seen = []
        for rec in self.trace:
            if rec["step"] not in seen:
                seen.append(rec["step"])
        self.check(seen == list(STEPS), "К4-C35: шаги Д1–Д14 по порядку", seen)
        foreign = [rec for rec in self.trace if rec["step"] in STEPS[2:] and rec["case_id"] not in (self.boris, None)]
        self.check(not foreign, "К4-C35: один case_id — после Д2 вызовы только о деле Бориса", foreign)
        vers = [rec for rec in self.trace if rec["step"] in STEPS[2:] and rec["case_id"] == self.boris
                and rec["ver"] != 1]
        self.check(not vers, "К4-C35/§14: case_ver дела Бориса = 1 в следе", vers)
        last = self.trace[-1]["fakes"] if self.trace else None
        self.check(last == FINAL_COUNTERS, "§14: счётчики подделок в последней строке следа", last)
        if self.is_a:
            bad = [rec for rec in self.trace
                   if not str(rec["actor"]).startswith("probe:") and rec["code"] not in OK_CODES]
            self.check(not bad, "К4-C35: каждый шаг ok/found", bad)

    # ------------------------------------------------------------------------------------------------ прогон
    def execute(self):
        steps = (self.d1, self.d2, self.d3, self.d4, self.d5, self.d6, self.d7, self.d8, self.d9, self.d10,
                 self.d11, self.d12, self.d13, self.d14)
        ok = False
        say("DEMO %s: база %s" % (self.variant, self.db_path))
        try:
            for i, fn in enumerate(steps, 1):
                self.begin(i)
                fn()
                say("  %s [%s] ok" % (self.step, self.variant))
            self.step = "итог"
            self.final_checks()
            ok = True
        except DemoFailure as e:
            say("DEMO %s: ПРОВАЛ — %s" % (self.variant, e))
        except Exception as e:  # noqa: BLE001 — исключение реализации/подделки = провал шага
            say("DEMO %s: ИСКЛЮЧЕНИЕ на шаге %s — %s: %s" % (self.variant, self.step, type(e).__name__, e))
            say(traceback.format_exc())
        finally:
            self.close_stores()
        path = self.write_trace(ok)
        say("DEMO %s: %s; вызовов %d; след %s (sha256 %s)" % (
            self.variant, "PASS" if ok else "FAIL", len(self.trace), path.replace("\\", "/"), sha256_file(path)))
        return ok

    def write_trace(self, ok):
        path = self.trace_path if ok else self.trace_path + ".partial"
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        moved = set_aside(path)
        if moved:
            say("  прежний след отложен: %s" % moved.replace("\\", "/"))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for rec in self.trace:
                f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        return path


# =====================================================================================================================
# Вход
# =====================================================================================================================


def _variant(s):
    v = str(s or "").strip().upper()
    return {"А": "A", "Б": "B"}.get(v, v)


def parse_args(argv):
    p = argparse.ArgumentParser(description="Демо-случай К4 (CONTRACT_K4 §14): варианты А/Б, след, повторяемость")
    p.add_argument("--variant", type=_variant, choices=("A", "B"), default=None,
                   help="A | B (по умолчанию оба: A, затем B)")
    p.add_argument("--trace", default=None,
                   help="след варианта A (по умолчанию %s); след B — рядом с суффиксом _B" % DEFAULT_TRACE)
    p.add_argument("--repeat-check", action="store_true",
                   help="два прогона каждого варианта → следы равны после нормализации id и времени")
    p.add_argument("--compare", nargs=2, metavar=("TRACE1", "TRACE2"), default=None,
                   help="сверить два готовых следа после нормализации (без прогона)")
    return p.parse_args(argv)


def _ttmp_root():
    root = os.environ.get("K4_TTMP") or tempfile.gettempdir()
    os.makedirs(root, exist_ok=True)
    return root


def run_once(RC, variant, trace_path, ttmp_root, tag=""):
    db_dir = tempfile.mkdtemp(prefix="k4demo_%s%s_" % (variant, tag), dir=ttmp_root)
    try:
        run = DemoRun(RC, variant, trace_path, db_dir)
    except Exception as e:  # noqa: BLE001 — нет PARAMS_DEFAULT и т. п.: провал подготовки, а не падение раннера
        say("DEMO %s: ПРОВАЛ подготовки — %s: %s" % (variant, type(e).__name__, e))
        say(traceback.format_exc())
        return False, None
    return run.execute(), run


def repeat_check(RC, variants, trace_base, ttmp_root):
    rdir = tempfile.mkdtemp(prefix="k4demo_repeat_", dir=ttmp_root)
    rc = 0
    for v in variants:
        paths = []
        oks = []
        for n in (1, 2):
            if trace_base:
                stem, ext = os.path.splitext(trace_base)
                base = trace_base if n == 1 else stem + "_repeat" + (ext or ".jsonl")
            else:
                base = os.path.join(rdir, "run%d" % n, os.path.basename(DEFAULT_TRACE))
            path = trace_path_for(base, v)
            ok, _run = run_once(RC, v, path, ttmp_root, "_r%d" % n)
            oks.append(ok)
            paths.append(path)
        if not all(oks):
            say("REPEAT %s: FAIL — прогон не прошёл (%s)" % (v, ", ".join("run%d=%s" % (i + 1, "ok" if o else "FAIL")
                                                                        for i, o in enumerate(oks))))
            rc = 1
            continue
        same, why = compare_traces(load_trace(paths[0]), load_trace(paths[1]))
        if same:
            say("REPEAT %s: PASS — следы двух прогонов равны после нормализации (%d строк): %s, %s" % (
                v, len(load_trace(paths[0])), paths[0].replace("\\", "/"), paths[1].replace("\\", "/")))
        else:
            say("REPEAT %s: FAIL — следы расходятся после нормализации: %s" % (v, why))
            rc = 1
    return rc


def main(argv=None):
    args = parse_args(argv)
    if args.compare:
        same, why = compare_traces(load_trace(args.compare[0]), load_trace(args.compare[1]))
        say("COMPARE: %s%s" % ("PASS — следы равны после нормализации" if same else "FAIL — ", "" if same else why))
        return 0 if same else 1
    try:
        import rental_case as RC  # noqa: WPS433 — реализация импортируется после подмены сокета
    except ImportError as e:
        say("DEMO: реализация rental_case не импортируется из %s: %s" % (ROOT, e))
        return 2
    variants = [args.variant] if args.variant else ["A", "B"]
    ttmp_root = _ttmp_root()
    if args.repeat_check:
        rc = repeat_check(RC, variants, args.trace, ttmp_root)
    else:
        base = args.trace or DEFAULT_TRACE
        rc = 0
        for v in variants:
            ok, _run = run_once(RC, v, trace_path_for(base, v), ttmp_root)
            if not ok:
                rc = 1
    if F.net_attempts():
        say("DEMO: попытки сети: %d — %s" % (F.net_attempts(), F.net_log()))
        rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
