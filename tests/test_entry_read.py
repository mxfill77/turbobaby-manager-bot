#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RCFIX2010c · ENTRY_READ r1 (READER_SPEC r2, Codex TB-REVIEW-2110-RECOVERY-V): читатель текущего входа splinter.

Все чтения модуля идут через подменённый фасад FakeWorld (systemctl show по чтениям S0/S1/S2, /proc, boot_id, adjtimex,
часы, пояс, git, drop-in, журнал — настоящий файл во временном каталоге). Строки журнала пишет настоящий
logging.Formatter формата bot.py:73 (UTC), строки флагов и входа — настоящие splinter.release_flags_line/release_entry
(импорт с заглушкой fcntl на Windows). Сети, systemctl, git сервера, моста и боевых файлов нет; health импортируется
ТОЛЬКО здесь (оракул _run_verdict, раздел B).

Разделы:
  A — литералы против bot.py / splinter.py вершины, сетка release_entry (≥ 2000 сочетаний × 2 набора ключей юнита),
      шаблоны флагов против закреплённых копий, слова передачи, синтаксис 3.8;
  B — оракул «не зеленее health._run_verdict» на общей сетке синтетических журналов вершины (обычный прогон — ядро ≥ 300,
      ENTRY_READ_FULL=1 — вся сетка 2100, вставки pend_win / pend_seg — build3), его контракт, второй писатель (счёт по
      окну health r6, gen_contra, пределы) и правило pend health r7 (b4: K3/K4 verify8). Оракул — health дерева (r5);
      ENTRY_READ_HEALTH=<путь к health.py> подставляет другой (r7 рабочей копии rcfix2010, 1a8ba76f…) тем же тестом;
  C — личность (три чтения, boot_id, --expect-run, --expect-wa, --prev-run, рождение, cgroup, AE/EMS, DOWN, переходные
      состояния, каждое неполное чтение wa-agent);
  D — часы и пояс (adjtimex, not-before, шаг, метки и старт впереди, пояс процесса и /etc/localtime; Environment не читается);
  E — журнал (не прочитан/короче/ротация/потолок, посылка, нижняя граница окна, вставка, порядок, возраст, PARKED, NOPOLL,
      база, Traceback, разбиение на куски, грамматика записи r6, коды грамматики цепочки);
  F — код и git; G — drop-in; H — квитанция, коды, положительная таблица CLEAN по фактам (h7) и мутанты «строка → pass» по
      каждой строке добавления кода и факта ворот — ни одного CLEAN (h8b, build3); I — только чтение (AST-замок, ПОЛНЫЙ
      набор опций ssh ls-remote, argv, форма запуска);
  J — охрана --guard unpark и повторная сверка --recheck (тест на КАЖДОЕ поле дрейфа → отказ 63);
  H6/H9/H10 — помощник ПК (ENTRY_READ_HELPER=<путь к lifecycle_er_r1.sh>; в репозитории его нет — иначе явный пропуск):
      шаблоны, стадии er ENTRY / vr / er --vr / ux на подменённом ssh — таблица исходов пути V (RECOVERY_PATH r5 §0.3) и
      вход V0 (§1) живут в помощнике МАШИНОЙ, здесь проверяются; h10 — удалённый шаблон ux ИСПОЛНЯЕТСЯ в bash с
      подменёнными python3/systemctl (build3, MJ1 линзы безопасности круга 2);
  H11 — фикстуры журнала отката h9 против байтов пакета (ENTRY_READ_PKG=<каталог с srv_reld_rollback_bf85964_r10.sh и
      srv_splinter_restart5_r3d.sh>, сверка по sha256 67ab7f7b… / c792804b…; иначе явный пропуск);
  Z — мутанты (ENTRY_READ_MUTANTS=1; в обычном прогоне и в гейте — явный пропуск, квитанция мутантов — отдельным запуском).
Решения К3 21.10 (факт): tests/test_health_wa_reaction.py в раннер r5 НЕ включается — его REPO — боевой путь, он проверяет
живое дерево, а не кандидата; правку kit делает К3 при сборке пакета (описание — build1/REBIND_CAPABILITY.md).
Прогон: venv/Scripts/python.exe tests/test_entry_read.py → «ИТОГ N/M»."""
import ast
import datetime as _dt
import hashlib
import inspect
import io
import itertools
import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import types

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)                        # корень вершины — от каталога самого теста
SRC = os.environ.get("ENTRY_READ_SRC", "")           # мутант: каталог с подменённым entry_read.py
ONLY = [x for x in os.environ.get("ENTRY_READ_ONLY", "").split(",") if x]
FULL = os.environ.get("ENTRY_READ_FULL", "") == "1"  # тяжёлые сетки целиком (обычный прогон — их ядро)
HEALTH_SRC = os.environ.get("ENTRY_READ_HEALTH", "")  # оракул B из другого файла health.py (пусто — health дерева)
sys.path.insert(0, TREE)
if SRC:
    sys.path.insert(0, SRC)

KEYS = ("INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN", "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS")
STRICT, GEN, TRUTH, ACCR, HOF = KEYS
for _f in KEYS + ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB"):
    os.environ.pop(_f, None)
TMP = tempfile.mkdtemp(prefix="entry_read_")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["NOTIFY_COUNT_FILE"] = os.path.join(TMP, "notify_count.txt")
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),
                  ("SPEND_LEDGER_FILE", "spend_ledger.json")):
    os.environ[_k] = os.path.join(TMP, _name)
os.makedirs(os.path.join(TMP, "_default"), exist_ok=True)
os.environ["RESTART_HANDOFF_STATE"] = os.path.join(TMP, "_default", "restart_handoff.json")

try:
    import fcntl  # noqa: F401  (Linux; на ПК — заглушка только для импорта splinter)
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    _fc.lockf = lambda *a, **k: None
    sys.modules["fcntl"] = _fc

import entry_read as ER  # noqa: E402

_SPL, _HEALTH = [], []


def S():
    """splinter — лениво (импорт тяжёлый; детям-мутантам без разделов A/B он не нужен)."""
    if not _SPL:
        import splinter
        _SPL.append(splinter)
    return _SPL[0]


def HL():
    """health — ТОЛЬКО оракул теста (в модуле импорта health нет — замок I). ENTRY_READ_HEALTH — другой файл (r6)."""
    if not _HEALTH:
        if HEALTH_SRC:
            import importlib.util
            spec = importlib.util.spec_from_file_location("health_oracle", HEALTH_SRC)
            health = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(health)
        else:
            import health
        health.LOG = os.path.join(TMP, "health_view.log")      # чтение health — только во временном каталоге
        _HEALTH.append(health)
    return _HEALTH[0]


class _Env:
    def __init__(self, kv):
        self.kv, self.old = dict(kv), {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def words_of(**kv):
    env = {k: None for k in KEYS}
    env.update(kv)
    with _Env(env):
        return S().release_flags_words()


# =============================================================================================================================
# Журнал: настоящий Formatter формата bot.py:73 (UTC — 69k:190–194)
# =============================================================================================================================
INFO, WARNING, ERROR = logging.INFO, logging.WARNING, logging.ERROR
UTC = _dt.timezone.utc
BOT_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
FMT = logging.Formatter(BOT_FMT)
FMT.converter = time.gmtime
NOW = _dt.datetime(2026, 10, 21, 8, 0, 0, tzinfo=UTC).timestamp() + 0.4
NB = int(NOW) - 86400                                   # --not-before: время коммита вершины
FRAC = 0.3                                              # дробная часть настоящего старта юнита
MONO0 = 600000.0
SHA_V = "4f3a" * 10
SHA_RB = "7c1e" * 10
DB_PIN = "cc0b22a486d4222215b6efcb536f04244dd2592ac5b75881ceea7cf70e573f31"
DU_PIN = "60449a3164ebea342ebae8c0ea0e675772316f1a11f0d38d762e0350a3a26f64"
INV_SP = "0123456789abcdef0123456789abcdef"
INV_WA = "fedcba9876543210fedcba9876543210"
BOOT = "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
PID_SP, PID_WA, NR_SP, NR_WA = 1249876, 1187731, 3, 1
PID_WA2 = PID_WA + 7                                    # wa-agent после R1 (PID из WA_DONE)
TCK = 100
BLOB_V = {"bot.py": "b0" * 20, "splinter.py": "51" * 20, "health.py": "4e" * 20, "entry_read.py": "e7" * 20,
          "wa_agent.py": "a9" * 20}
LABEL = "run_bf85964_2110_0830/0e"
POLL = "Bot polling started. Press Ctrl+C to stop."
BASE_B = "🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · CONTRACT_REF_GEN=ВЫКЛ (не задан)"   # 947953e
RECEIPTS = []                                           # все квитанции прогона (H: префикс ПК принимает каждую)


def L(t, level, msg, name="turbobaby", exc_info=None):
    ms = int(round(t * 1000))
    r = logging.LogRecord(name, level, "bot.py", 1, msg, None, exc_info)
    r.created = ms / 1000.0
    r.msecs = float(ms % 1000)
    return [s + "\n" for s in FMT.format(r).split("\n")]


def _exc():
    try:
        raise ValueError("стенд: лист не прочитан")
    except ValueError:
        return sys.exc_info()


def boot_part(t, bmsg, blevel=INFO):
    out = []
    out += L(t + 0.912, INFO, ER.A_MSG)
    out += L(t + 0.931, INFO, "  Топики: ✅ привязок тема→байк из memory.db загружено: 14")
    out += L(t + 0.944, INFO, "  Инфо-кнопки: ✅ закрепов из memory.db загружено: 9")
    out += L(t + 0.951, blevel, "  " + bmsg)
    out += L(t + 0.968, INFO, "  Auditor LLM: ✅ надзор логики для групп [-1001234567890]; канал правок «Аудит»=off")
    return out


def tail_part(t, d=True, e=True, f=True, ho="передачи нет", tb=False, jobs=True):
    out = []
    out += L(t + 1.021, INFO, "Scheduled daily pulse at 09:00 Asia/Bangkok")
    out += L(t + 1.027, INFO, "Scheduled devbot orchestrator result reporting every 45s")
    if d:
        out += L(t + 1.247, INFO, POLL)
    if e:
        out += L(t + 1.402, INFO, "=" * 60)
        out += L(t + 1.403, INFO, "TurboBaby Manager Bot — STARTING")
        out += L(t + 1.404, INFO, "  Timezone: Asia/Bangkok")
    if tb:
        out += L(t + 1.405, ERROR, "  ⚠️ передача карточек: сбой восстановления", exc_info=_exc())
    if f:
        out += L(t + 1.406, INFO, "  🔁 передача карточек: " + ho)
    if jobs:
        out += L(t + 1.611, INFO, "  Bridge: ✅ alive (v1.0.0)")
        out += L(t + 1.702, INFO, "Scheduler started", name="apscheduler.scheduler")
        out += L(t + 46.0, INFO, 'Running job "devbot_report (trigger: interval[0:00:45])"',
                 name="apscheduler.executors.default")
    return out


_CAND_MEMO = {}


def cand_lines(env, unit):
    """(строка флагов, состояние, строка входа) настоящим splinter — один раз на сочетание (сетка B не ждёт splinter)."""
    key = (tuple(sorted((env or {}).items())), tuple(sorted(unit)))
    if key not in _CAND_MEMO:
        words = words_of(**(env or {}))
        st, el = S().release_entry(words, frozenset(unit))
        _CAND_MEMO[key] = (S().release_flags_line(words), st, el)
    return _CAND_MEMO[key]


def cand_proc(t, env=None, unit=(), d=True, e=True, f=True, ho="передачи нет", tb=False, jobs=True):
    """Процесс вершины: строки импорта, флаги и вход настоящим splinter; при допуске — опрос и post_init."""
    bl, st, el = cand_lines(env, unit)
    out = boot_part(t, bl)
    if st is None:
        out += L(t + 0.990, ERROR, "  " + el)
        return out
    out += L(t + 0.990, INFO, "  " + el)
    return out + tail_part(t, d, e, f, ho, tb, jobs)


def notread_proc(t):
    out = boot_part(t, "🧩 флаги выпуска: НЕ ПРОЧИТАНЫ (KeyError)", WARNING)
    out += L(t + 0.990, ERROR, "  " + S().release_entry(None, frozenset())[1])
    return out


def crash_proc(t):
    words = words_of()
    out = boot_part(t, S().release_flags_line(words))
    out += L(t + 0.990, ERROR, "  " + S()._ENTRY_HEAD + "UNKNOWN — сбой проверки (TypeError); " + S()._ENTRY_LIST
             + "; обработчики не зарегистрированы, опрос не начат — процесс ждёт остановки")
    return out


def base_proc(t, d=True, e=True, f=True, ho="передачи нет", tb=False, bmsg=BASE_B, jobs=True):
    """Процесс базы 947953e: строки входа нет, флаги — две ручки."""
    return boot_part(t, bmsg) + tail_part(t, d, e, f, ho, tb, jobs)


def stop_part(t):
    return (L(t, INFO, "  🛑 дренаж остановки: от сигнала 0.1 с из 25; альбомы: 0; передача карточек: записана 0 (sha 0f1e2d3c)")
            + L(t + 0.2, INFO, "Scheduler has been shut down", name="apscheduler.scheduler"))


def history(t_ems, kind="normal"):
    """Прошлый процесс (база), трое суток назад; normal — штатная остановка за 5 с до старта; killed — без остановки."""
    if kind == "none":
        return []
    t = t_ems - 3 * 86400
    out = base_proc(t)
    if kind == "normal":
        out += stop_part(t_ems - 5)
    return out


def to_bytes(lines):
    return b"".join(x if isinstance(x, bytes) else x.encode("utf-8") for x in lines)


# =============================================================================================================================
# Мир: FakeWorld — все чтения модуля
# =============================================================================================================================
_WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def sd_text(t):
    d = _dt.datetime.fromtimestamp(int(t), UTC)
    return "%s %s UTC" % (_WD[d.weekday()], d.strftime("%Y-%m-%d %H:%M:%S"))


def props(pid, ems, emsm, nr, act="active", sub="running", inv=INV_SP, ae_off_us=1500, ae=None):
    return {"InvocationID": inv, "MainPID": str(pid), "NRestarts": str(nr), "ActiveState": act, "SubState": sub,
            "ExecMainStartTimestamp": sd_text(ems) if ems is not None else "",
            "ExecMainStartTimestampMonotonic": str(emsm),
            "ActiveEnterTimestamp": sd_text(ae if ae is not None else ems) if ems is not None else "",
            "ActiveEnterTimestampMonotonic": str(emsm + ae_off_us)}


def proc_stat(pid, ticks, comm="python3"):
    toks = ["S"] + ["0"] * 18 + [str(ticks)] + ["0"] * 5
    return ("%d (%s) " % (pid, comm) + " ".join(toks) + "\n").encode()


class Sc:
    """Сценарий: по умолчанию — CLEAN для state (release / truth_off / base) на вершине SHA_V (или RB для base)."""

    def __init__(self, state="release", age=7200, log=None, sha=None):
        self.state = state
        self.sha = sha or (SHA_RB if state == "base" else SHA_V)
        self.t0 = NOW
        self.ems = int(self.t0) - age
        self.emsm = int(round((MONO0 - (self.t0 - (self.ems + FRAC))) * 1e6))
        self.t2 = self.t0 + 1.2
        self.mono2 = MONO0 + 1.2
        self.ems_wa = self.ems - 3600
        self.emsm_wa = self.emsm - 3600 * 1000000
        self.sp = [props(PID_SP, self.ems, self.emsm, NR_SP)]
        self.wa = [props(PID_WA, self.ems_wa, self.emsm_wa, NR_WA, inv=INV_WA)]
        self.boot = [BOOT.encode() + b"\n"]
        tk = int(round(self.emsm / 1e6 * TCK)) + 2
        tkw = int(round(self.emsm_wa / 1e6 * TCK)) + 3
        self.proc = {PID_SP: [(proc_stat(PID_SP, tk), b"0::/system.slice/splinter.service\n")],
                     PID_WA: [(proc_stat(PID_WA, tkw), b"0::/system.slice/wa-agent.service\n")]}
        tree = dict(BLOB_V)
        if state == "base":
            tree["bot.py"], tree["splinter.py"] = ER.BASE_BOT_BLOB, ER.BASE_SPL_BLOB
        self.tree = tree
        self.work = dict(tree)
        self.mtime = {n: self.ems_wa - 600 for n in tree}
        self.head = self.sha
        self.status = b""
        self.origin = self.sha
        self.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "no",
                        "DropInPaths": (ER.DB if state == "truth_off" else "")}]
        self.cfg_wa = [{"LoadState": "loaded", "NeedDaemonReload": "no"}]
        self.dropin = {ER.DB: ("file", DB_PIN) if state == "truth_off" else ("absent", None), ER.DU: ("absent", None)}
        self.adj = [{"rc": 0, "maxerror": 250000, "status": 0}]
        self.zone = (0, 0, 0)
        self.link = "/usr/share/zoneinfo/Etc/UTC"
        self.fail = {}                  # имя чтения → исключение / («rc», n)
        self.raw = {}                   # имя чтения → сырой ответ (bytes)
        self.fstat_after = None
        self.pstat = None
        self.maxread = None
        if log is None:
            if state == "base":
                log = history(self.ems, "normal") + base_proc(self.ems + FRAC)
            elif state == "truth_off":
                log = history(self.ems, "normal") + cand_proc(self.ems + FRAC, {TRUTH: "0"}, ("CLOSE_TRUTH",))
            else:
                log = history(self.ems, "normal") + cand_proc(self.ems + FRAC)
        self.set_log(log)

    def set_log(self, lines):
        self.log_path = os.path.join(TMP, "splinter_%d.log" % id(self))
        with open(self.log_path, "wb") as fh:
            fh.write(to_bytes(lines))

    def args(self, *extra, **kw):
        a = ["--sha", kw.get("sha", self.sha), "--state", kw.get("state", self.state), "--label", kw.get("label", LABEL),
             "--not-before", str(kw.get("nb", NB)), "--db-sha", DB_PIN, "--du-sha", DU_PIN]
        return a + list(extra)

    def key(self):
        return "%s.%s.%d.%d.%d" % (BOOT[:8], INV_SP, PID_SP, self.emsm, NR_SP)

    def wa_key(self):
        return "%s.%s.%d.%d.%d" % (BOOT[:8], INV_WA, PID_WA, self.emsm_wa, NR_WA)

    def park_for_guard(self):
        """Простой кандидата K0 над кодом отката RB на диске (вход V2a/V2 пути V): процесс старше файлов, wa моложе."""
        self.state, self.sha = "base", SHA_RB
        self.head = self.origin = SHA_RB
        self.tree = dict(BLOB_V, **{"bot.py": ER.BASE_BOT_BLOB, "splinter.py": ER.BASE_SPL_BLOB})
        self.work = dict(self.tree)
        self.ems_wa = self.ems + 1800
        self.emsm_wa = self.emsm + 1800 * 1000000
        self.wa = [props(PID_WA, self.ems_wa, self.emsm_wa, NR_WA, inv=INV_WA)]
        tkw = int(round(self.emsm_wa / 1e6 * TCK)) + 3
        self.proc[PID_WA] = [(proc_stat(PID_WA, tkw), b"0::/system.slice/wa-agent.service\n")]
        self.mtime = {n: self.ems + 1200 for n in self.tree}
        self.set_log(history(self.ems, "normal") + cand_proc(self.ems + FRAC, {ACCR: "1"}))
        return self


def render_props(p):
    if isinstance(p, dict):
        items = list(p.items())
        items.reverse()                  # порядок systemd иной, чем в запросе: разбор по имени ключа
        return (0, "".join("%s=%s\n" % kv for kv in items).encode())
    return p


class _FakeFile:
    def __init__(self, path, maxread):
        self.fh = open(path, "rb")
        self.maxread = maxread

    def read(self, n):
        return self.fh.read(n if not self.maxread else min(n, self.maxread))

    def fileno(self):
        return self.fh.fileno()

    def close(self):
        self.fh.close()


class FakeWorld:
    def __init__(self, sc):
        self.sc = sc
        self.calls, self.reads = [], []
        self.n = {}
        self.walls = 0
        self.monos = 0

    def _seq(self, name, lst):
        i = self.n.get(name, 0)
        self.n[name] = i + 1
        return lst[min(i, len(lst) - 1)]

    def _fail(self, name):
        x = self.sc.fail.get(name)
        if callable(x):
            x = x(self.n.get(name, 0))
        if isinstance(x, BaseException):
            raise x
        return x

    def run(self, argv, timeout):
        argv = tuple(argv)
        self.calls.append(argv)
        if not ER.argv_ok(argv):
            raise PermissionError("вне белого списка")
        sc = self.sc
        names = {ER.ARGV_SHOW_SP: "sp", ER.ARGV_SHOW_WA: "wa", ER.ARGV_CFG_SP: "cfg_sp", ER.ARGV_CFG_WA: "cfg_wa",
                 ER.ARGV_HEAD: "head", ER.ARGV_STATUS: "status", ER.ARGV_LSTREE: "lstree", ER.ARGV_ORIGIN: "origin"}
        name = names.get(argv, "hash")
        x = self._fail(name)
        if x is not None and name not in ("sp", "wa", "cfg_sp", "cfg_wa"):
            return x
        if name in ("sp", "wa", "cfg_sp", "cfg_wa"):
            item = self._seq(name, getattr(sc, name))
            if x is not None:
                return x
            if name in sc.raw:
                return (0, sc.raw[name])
            return render_props(item)
        if name in sc.raw:
            return (0, sc.raw[name])
        if name == "head":
            return (0, (sc.head + "\n").encode())
        if name == "status":
            return (0, sc.status)
        if name == "lstree":
            return (0, "".join("100644 blob %s\t%s\n" % (sc.tree[n], n) for n in sorted(sc.tree)).encode()
                    + b"040000 tree " + b"0" * 40 + b"\ttests\n")
        if name == "origin":
            return (0, ("%s\trefs/heads/main\n" % sc.origin).encode())
        return (0, "".join(sc.work[n] + "\n" for n in argv[len(ER.ARGV_HASH):]).encode())

    def read_small(self, path):
        self.reads.append(path)
        x = self._fail("read:" + path)
        if x is not None:
            return x
        if path == ER.BOOT_ID:
            return self._seq("boot", self.sc.boot)
        m = re.match(r"^/proc/([0-9]+)/(stat|cgroup)$", path)
        if m and int(m.group(1)) in self.sc.proc:
            st, cg = self._seq("proc%s_%s" % (m.group(1), m.group(2)), self.sc.proc[int(m.group(1))])
            return st if m.group(2) == "stat" else cg
        raise FileNotFoundError(2, "нет", path)

    def lstat(self, path):
        self.reads.append("lstat:" + path)
        kind, _sha = self.sc.dropin[path]
        if isinstance(kind, BaseException):
            raise kind
        if kind == "absent":
            raise FileNotFoundError(2, "нет", path)
        mode = {"file": stat.S_IFREG, "link": stat.S_IFLNK, "dir": stat.S_IFDIR}[kind] | 0o644
        return types.SimpleNamespace(st_mode=mode)

    def hash_file(self, path):
        self.reads.append("hash:" + path)
        x = self._fail("hash:" + path)
        if x is not None:
            return x
        return self.sc.dropin[path][1]

    def mtime(self, name):
        x = self._fail("mtime")
        if x is not None:
            return x
        return self.sc.mtime[name]

    def log_open(self):
        x = self._fail("log_open")
        if x is not None:
            return x
        return _FakeFile(self.sc.log_path, self.sc.maxread)

    def log_fstat(self, fh):
        i = self.n.get("fstat", 0)
        self.n["fstat"] = i + 1
        s = os.fstat(fh.fileno())
        if i >= 1 and self.sc.fstat_after is not None:
            return self.sc.fstat_after
        return (1, 77, s.st_size, 1000)

    def log_pstat(self):
        return self.sc.pstat if self.sc.pstat is not None else (1, 77)

    def wall(self):
        self.walls += 1
        x = self._fail("wall")
        if x is not None:
            return x
        return self.sc.t0 if self.walls <= 2 else self.sc.t2

    def mono(self):
        self.monos += 1
        return MONO0 if self.monos <= 1 else self.sc.mono2

    def clk_tck(self):
        return TCK

    def adjtimex(self):
        x = self._fail("adj")
        if x is not None:
            return x
        return self._seq("adj", self.sc.adj)

    def zone(self):
        x = self._fail("zone")
        if x is not None:
            return x
        return self.sc.zone

    def readlink(self, path):
        assert path == ER.LOCALTIME, path
        if isinstance(self.sc.link, BaseException):
            raise self.sc.link
        return self.sc.link


def run_er(sc, argv=None, world=None):
    """→ (rc, строка, разбор квитанции | None, мир)."""
    w = world or FakeWorld(sc)
    out = io.StringIO()
    rc = ER.main(sc.args() if argv is None else argv, world=w, out=out)
    text = out.getvalue()
    if text.startswith("ENTRY_READ r1 "):
        RECEIPTS.append(text.rstrip("\n"))
    return rc, text, ER.parse_receipt(text.rstrip("\n")), w


def why(r):
    return r["why"].split(",")


def expect(sc, cls, code=None, argv=None, absent=None):
    rc, text, r, w = run_er(sc, argv)
    assert r is not None, text
    assert r["class"] == cls, (cls, text)
    if code is not None:
        assert code in why(r), (code, text)
    if absent is not None:
        assert absent not in why(r), (absent, text)
    return r, rc, w


def key_with(k, **kw):
    """Ключ K с заменой полей: boot, inv, pid, emsm, nr."""
    b, inv, pid, emsm, nr = k.split(".")
    f = {"boot": b, "inv": inv, "pid": pid, "emsm": emsm, "nr": nr}
    f.update({x: str(v) for x, v in kw.items()})
    return ".".join(f[x] for x in ("boot", "inv", "pid", "emsm", "nr"))


# =============================================================================================================================
# A. Литералы и сетка release_entry
# =============================================================================================================================
def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_a1_literals_vs_bot():
    """Литералы цепочки — дословно в bot.py вершины, по одному вхождению; формат записи и логгер — те же."""
    src = _read(os.path.join(TREE, "bot.py"))
    for lit in ('log.info("' + ER.A_MSG + '")', 'log.info("' + ER.D_MSG + '")', 'log.info("' + ER.E_MSG + '")',
                'log.info(f"' + ER.F_HEAD + '{splinter.handoff_restore()}")',
                'log.info("  " + splinter.release_flags_line(_RELEASE_WORDS))',
                'log.warning(f"' + ER.B_HEAD + 'НЕ ПРОЧИТАНЫ ({type(e).__name__})")',
                'log.error("  " + entry_line)', 'log.info("  " + entry_line)', 'log.info(f"' + ER.STOP_HEAD,
                'format="' + BOT_FMT + '"', 'log = logging.getLogger("' + ER.LOGGER + '")'):
        assert src.count(lit) == 1, (lit, src.count(lit))
    assert ER.C_HEAD == "  " + S()._ENTRY_HEAD and ER.B_HEAD == "  " + "🧩 флаги выпуска: "
    i94, i106, i1662, i1778 = (src.index(x) for x in (ER.A_MSG, "splinter.release_flags_line(_RELEASE_WORDS)",
                                                    'log.error("  " + entry_line)', ER.D_MSG))
    assert i94 < i106 < i1662 < i1778, "порядок a < b < c < d в коде bot.py"


def test_a1b_literals_vs_base():
    """База 947953e (если объект есть в этом дереве git): a :90, b-WARNING :103, d :1749, e :1340, f :1347 — по одному;
    блобы bot.py / splinter.py = константам модуля. Нет объекта — явный пропуск (байтовую сверку делает адресная
    проверка §15 на ПК)."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    p = subprocess.run(["git", "-C", TREE, "cat-file", "-e", "947953e78df108f276b8ac4b6bd48ffcf327c673^{commit}"],
                       capture_output=True, env=env)
    if p.returncode != 0:
        print("  SKIP a1b: объекта 947953e в дереве нет")
        return
    src = subprocess.run(["git", "-C", TREE, "show", "947953e78df108f276b8ac4b6bd48ffcf327c673:bot.py"],
                         capture_output=True, env=env).stdout.decode("utf-8")
    for lit in ('log.info("' + ER.A_MSG + '")', 'log.info("' + ER.D_MSG + '")', 'log.info("' + ER.E_MSG + '")',
                'log.info(f"' + ER.F_HEAD + '{splinter.handoff_restore()}")',
                'log.warning(f"' + ER.B_HEAD + 'НЕ ПРОЧИТАНЫ ({type(e).__name__})")'):
        assert src.count(lit) == 1, lit
    assert ER.C_HEAD.strip() not in src, "у базы строки входа нет"
    blobs = subprocess.run(["git", "-C", TREE, "rev-parse", "947953e78df108f276b8ac4b6bd48ffcf327c673:bot.py",
                            "947953e78df108f276b8ac4b6bd48ffcf327c673:splinter.py"], capture_output=True,
                           env=env).stdout.decode().split()
    assert blobs == [ER.BASE_BOT_BLOB, ER.BASE_SPL_BLOB], blobs


def test_a2_literals_vs_splinter():
    sp = S()
    assert ER.FLAG_KEYS == sp.RELEASE_FLAG_KEYS
    assert ER.ENTRY_LIST == sp._ENTRY_LIST and ER.C_HEAD[2:] == sp._ENTRY_HEAD
    assert tuple((n, allowed) for n, allowed, _u in sp.RELEASE_ENTRY_STATES) == ER.ENTRY_STATES
    park = sp.release_entry(None, frozenset())[1]
    assert park.endswith("; " + ER.ENTRY_LIST + "; " + ER.PARK_TAIL), park
    ok = sp.release_entry(words_of(), frozenset())[1]
    assert ER._ENTRY_OK.match(ok[len(sp._ENTRY_HEAD):]), ok
    seen = set()
    for env in _grid():
        for _k, w in words_of(**env):
            seen.add(ER._token(w))
    assert "xx" not in seen and {"1z", "1n", "0z", "0n", "0d", "?u"} <= seen, seen


GRID = {STRICT: (None, "1", "0", "maybe", " Да "), GEN: (None, "0", "1", "да", "OFF"),
        TRUTH: (None, "1", "0", "maybe", "Off"), ACCR: (None, "0", "1", "maybe"), HOF: (None, "0", "1", "enabled")}
_GRID_CACHE = []


def _grid():
    if not _GRID_CACHE:
        for vals in itertools.product(*(GRID[k] for k in KEYS)):
            _GRID_CACHE.append({k: v for k, v in zip(KEYS, vals) if v is not None})
    return _GRID_CACHE


def _scan(lines, t_ems=None, age=7200.0, state="release"):
    t_ems = int(NOW) - 7200 if t_ems is None else t_ems
    bl = to_bytes(lines).splitlines()
    sc = ER.scan_lines(bl, t_ems, t_ems, t_ems + 300)
    return ER.derive_chain(sc, state, age)


def test_a3_release_entry_grid():
    """≥ 2000 сочетаний слов × 2 набора ключей юнита: читатель = вердикт release_entry (OK s → POLLING, None → PARKED)."""
    n = {"park": 0, "release": 0, "truth_off": 0}
    t = int(NOW) - 7200
    for env in _grid():
        words = words_of(**env)
        bl = S().release_flags_line(words)
        for unit in (frozenset(), frozenset(["CLOSE_TRUTH"])):
            st, el = S().release_entry(words, unit)
            if st is None:
                d = _scan(boot_part(t + FRAC, bl) + L(t + FRAC + 0.99, ERROR, "  " + el), t)
                assert d["proc"] == "PARKED" and not d["codes"], (env, unit, d)
                verdict = el[len(S()._ENTRY_HEAD):].split(" — ", 1)[0]
                assert d["entry"] == verdict, (d["entry"], verdict)
                n["park"] += 1
            else:
                lines = boot_part(t + FRAC, bl) + L(t + FRAC + 0.99, INFO, "  " + el) + tail_part(t + FRAC)
                d = _scan(lines, t, state=st)
                lib = SC_FLAGS_RE[st]
                assert d["proc"] == "POLLING" and d["entry"] == st and not d["codes"], (env, unit, d)
                assert d["fv"] == (re.search(lib, bl) is None), (env, bl)
                n[st] += 1
    assert sum(n.values()) >= 4000 and all(n.values()), n
    print("  · сетка A3: %s" % n)


# Копии шаблонов библиотек — из закреплённых тестов вершины (AST, без импорта): test_rcfix2010_tuple.py (сверяет библиотеку
# rc2010 по LIB_SHA 4afe3e88) и test_release_flags_line.py (RESTART_OK_RE_947 = SC_FLAGS_RE 5db211d1 :23).
def _const_of(path, name):
    tree = ast.parse(_read(path))
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError(name)


SC_FLAGS_RE = {"release": _const_of(os.path.join(HERE, "test_rcfix2010_tuple.py"), "SC_FLAGS_RE_RELEASE"),
               "truth_off": _const_of(os.path.join(HERE, "test_rcfix2010_tuple.py"), "SC_FLAGS_RE_TRUTH_OFF")}
SC_FLAGS_RE_BASE = _const_of(os.path.join(HERE, "test_release_flags_line.py"), "RESTART_OK_RE_947")


def test_a4_flags_regex_text():
    assert ER.FLAGS_RE == SC_FLAGS_RE, "FLAGS_RE ≠ копиям test_rcfix2010_tuple.py"
    assert ER.BASE_FLAGS_RE == SC_FLAGS_RE_BASE, "BASE_FLAGS_RE ≠ RESTART_OK_RE_947"
    lib = os.environ.get("ENTRY_READ_LIB", "")       # по желанию: путь к srv_splinter_checks_rc2010.sh — байтовая сверка
    if lib:
        text = _read(lib)
        for st, var in (("release", "SC_FLAGS_RE_RELEASE"), ("truth_off", "SC_FLAGS_RE_TRUTH_OFF")):
            assert ("%s='%s'" % (var, ER.FLAGS_RE[st])) in text.split("\n"), var


def test_a5_handoff_words():
    """Каждая ветка возврата splinter.handoff_restore (вершины) → свой ho; ни одна не «other»."""
    src = _read(os.path.join(TREE, "splinter.py"))
    fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "handoff_restore"][0]
    got = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Return) and n.value is not None:
            parts = []
            for v in (n.value.values if isinstance(n.value, ast.JoinedStr) else [n.value]):
                if isinstance(v, ast.Constant):
                    parts.append(v.value)
                else:
                    seg = ast.dump(v)
                    parts.append("deadbeef" if "sha256" in seg else ("2" if "counts" in seg else "X"))
            got.append(ER._ho("".join(parts)))
    assert len(got) == 8 and "other" not in got, got
    assert sorted(set(got)) == ["applied:8", "none", "notapplied", "repeat"], got


def test_a6_syntax_floor():
    src = _read(ER.__file__)
    ast.parse(src, feature_version=(3, 8))
    assert src.endswith("\n") and not src.endswith("\n\n"), "файл кончается ровно одним переводом строки (sha потока)"


# =============================================================================================================================
# B. Оракул: читатель не зеленее health._run_verdict
# =============================================================================================================================
def _health(sc):
    H = HL()
    H.LOG = sc.log_path
    lines, err = H._read_log()
    run = {"pid": PID_SP, "start": _dt.datetime.fromtimestamp(sc.ems, UTC), "start_raw": sd_text(sc.ems),
           "nrestarts": NR_SP, "active": "active", "sub": "running"}
    return H._run_verdict(lines, run, dict(run), _dt.datetime.fromtimestamp(sc.t0, UTC), err)[0]


B_CHAINS = ("poll_release", "poll_truth_off", "park_mismatch", "park_notread", "park_crash", "nopoll_no_d",
            "nopoll_d_only", "partial_e_no_f", "no_a", "poll_dup_d", "park_with_d", "poll_tb")
B_HIST = ("none", "normal", "killed", "cand_prev", "writer_in_window")
B_TIME = ("normal", "young", "shift_east", "late", "early")
B_INJ = ("none", "stamp_below_f", "bad_utf8_below_f", "stop_in_seg", "stamp_pend", "pend_win", "pend_seg")


def _b_log(chain, hist, tshift, inj, ems):
    t = ems + FRAC
    if tshift == "shift_east":
        t += 3600
    elif tshift == "late":
        t += 400
    elif tshift == "early":
        t -= 1.5
    out = history(ems, "killed" if hist == "killed" else ("none" if hist in ("none", "writer_in_window") else "normal"))
    if hist == "cand_prev":                  # прошлый — процесс вершины, проживший сутки и штатно остановленный
        out += cand_proc(ems - 86400) + stop_part(ems - 2)
    if hist == "writer_in_window":
        out += base_proc(ems + 0.1, jobs=False)
    if inj in ("stamp_pend", "pend_win", "pend_seg"):
        out += L(ems - 30, INFO, "клиент написал:\n" + _dt.datetime.fromtimestamp(ems + 10, UTC).strftime(
            "%Y-%m-%d %H:%M:%S") + " текст клиента", name="turbobaby")
    if inj == "pend_win":                    # r7: запись в окне [старт − 2 с, старт) — не история, pend не снимает
        out += L(ems - 1, INFO, "запись в окне двух секунд до старта")
    env_t = {TRUTH: "0"} if chain == "poll_truth_off" else None
    unit = ("CLOSE_TRUTH",) if chain == "poll_truth_off" else ()
    if chain in ("poll_release", "poll_truth_off"):
        out += cand_proc(t, env_t, unit)
    elif chain == "park_mismatch":
        out += cand_proc(t, {ACCR: "1"})
    elif chain == "park_notread":
        out += notread_proc(t)
    elif chain == "park_crash":
        out += crash_proc(t)
    elif chain == "nopoll_no_d":
        out += cand_proc(t, d=False, e=False, f=False, jobs=False)
    elif chain == "nopoll_d_only":
        out += cand_proc(t, e=False, f=False, jobs=False)
    elif chain == "partial_e_no_f":
        out += cand_proc(t, f=False, jobs=False)
    elif chain == "no_a":
        pass
    elif chain == "poll_dup_d":
        out += cand_proc(t) + L(t + 50, INFO, POLL)
    elif chain == "park_with_d":
        out += cand_proc(t, {ACCR: "1"}) + L(t + 2, INFO, POLL)
    elif chain == "poll_tb":
        out += cand_proc(t, tb=True)
    if inj == "stamp_below_f":               # дата в прошлом: ловит только правило «метка неизвестной формы в запуске»
        out += L(t + 60, INFO, "клиент:\n2025-03-01 10:00:00 приеду завтра")
    elif inj == "bad_utf8_below_f":
        out += [b"\xff\xfe" + b" broken bytes\n"]
    elif inj == "stop_in_seg":
        out += L(t + 70, INFO, "Scheduler has been shut down", name="apscheduler.scheduler")
    elif inj == "pend_seg":                  # r7: запись с меткой < старта НИЖЕ начала запуска — не история
        out += L(ems - 20, INFO, "запоздалая запись ниже начала запуска")
    return out


def _b_cases():
    """Сетка B: вся (ENTRY_READ_FULL=1) — 12 × 5 × 5 × 7 = 2100; обычный прогон — ядро: каждое отклонение по одному
    измерению от нормы (12 × 15 = 180) и второй писатель / убитый прошлый вместе с каждым сдвигом времени и каждой
    вставкой (12 × 2 × 10 = 240) — всего 420 ≥ 300."""
    for chain, hist, tshift, inj in itertools.product(B_CHAINS, B_HIST, B_TIME, B_INJ):
        dev = (hist != "normal") + (tshift != "normal") + (inj != "none")
        if FULL or dev <= 1 or (dev == 2 and hist in ("writer_in_window", "killed")):
            yield chain, hist, tshift, inj


def test_b1_never_greener_than_health():
    """Общая сетка журналов вершины: CLEAN ⇒ OK; известный класс с POLLING ⇒ OK; PARKED ⇒ PARKED; health PARKED ⇒
    PARKED | UNKNOWN (и ⇔ на правильной части сетки); health UNKNOWN ⇒ читатель UNKNOWN при ЛЮБОМ gen (ни одного известного
    класса: вход пути V — только из известного; спец. M3 круга 1 — чужой писатель базы в окне больше не MIXED, а UNKNOWN
    gen_contra / win_many); health NO_POLL ⇒ NOPOLL | UNKNOWN. Сетка не пустая; оракул — health дерева или
    ENTRY_READ_HEALTH."""
    stats = {}
    bad = []
    n = 0
    for chain, hist, tshift, inj in _b_cases():
        state = "truth_off" if chain == "poll_truth_off" else "release"
        age = 120 if tshift == "young" else 7200
        sc = Sc(state=state, age=age, log=_b_log(chain, hist, tshift, inj, int(NOW) - age))
        hv = _health(sc)
        rc, text, r, _w = run_er(sc)
        n += 1
        assert r is not None, text
        cls, proc = r["class"], r["proc"]
        stats[(hv, cls)] = stats.get((hv, cls), 0) + 1
        regular = hist in ("none", "normal", "killed", "cand_prev") and tshift == "normal" and inj == "none"
        known = cls != "UNKNOWN"                 # proc под классом UNKNOWN — неподтверждённый разбор, не вывод
        ok = True
        if cls == "CLEAN" and hv != "OK":
            ok = False
        if known and proc == "POLLING" and r["gen"] == "cand" and hv != "OK":
            ok = False
        if cls == "PARKED" and hv != "PARKED":
            ok = False
        if hv == "PARKED" and cls not in ("PARKED", "UNKNOWN"):
            ok = False
        if regular and (hv == "PARKED") != (cls == "PARKED"):
            ok = False
        if hv == "UNKNOWN" and known:
            ok = False
        if hv == "NO_POLL" and cls not in ("NOPOLL", "UNKNOWN"):
            ok = False
        if not ok:
            bad.append("%s/%s/%s/%s health=%s reader=%s/%s why=%s" % (chain, hist, tshift, inj, hv, cls, proc, r["why"]))
    print("  · сетка B (%s, оракул %s): %d журналов; (health, читатель): %s"
          % ("вся" if FULL else "ядро", HEALTH_SRC or "health дерева", n, sorted(stats.items(), key=str)))
    assert n >= 300
    assert not bad, "\n".join(bad[:40])
    assert stats.get(("OK", "CLEAN"), 0) >= 8 and stats.get(("PARKED", "PARKED"), 0) >= (20 if FULL else 12), stats
    assert stats.get(("NO_POLL", "NOPOLL"), 0) >= 3, stats


def test_b2_oracle_signature():
    """Контракт оракула. Грамматика записи читателя — ТОЧНЫЙ формат health r6; у health r6+ она обязана совпасть дословно
    (уровни, имя, окно счёта 2 с), у health r5 (дерево f64ee79) грамматика health шире — читатель строже."""
    H = HL()
    assert list(inspect.signature(H._run_verdict).parameters) == ["lines", "run0", "run1", "now", "log_err"]
    run = {"pid": 1, "start": _dt.datetime.fromtimestamp(0, UTC), "start_raw": "x", "nrestarts": 0, "active": "active",
           "sub": "running"}
    assert H._run_key(run) == (1, "x", 0, "active", "running")
    assert H._START_SKEW_S == ER.START_SKEW_S == 300 and H._BACK_SKEW_S == ER.BACK_S
    assert H._BOOT_MSG == ER.A_MSG and H._ENTRY_PARK_TAIL == ER.PARK_TAIL and H._ENTRY_KEYS == ER.FLAG_KEYS
    log_ts = rb"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}"
    lv = "|".join(ER.LEVELS).encode()
    assert ER.LEVELS == ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    assert ER._REC_B.pattern == (rb"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}),(\d{3}) \[(" + lv + rb")\] ("
                                 + ER._NAME_B + rb"): ")
    hp = H._REC_RE.pattern.encode()
    if hasattr(H, "_LEVELS"):
        assert hp == b"^" + log_ts + rb" \[(?:" + lv + rb")\] " + ER._NAME_B + rb": ", hp
        assert tuple(H._LEVELS) == ER.LEVELS and H._NAME.encode() == ER._NAME_B and H._WIN_BACK_S == ER.WIN_BACK_S
        print("  · b2: оракул — health r6+ (грамматика записи и окно счёта совпали дословно)")
    else:
        assert hp == b"^" + log_ts + rb" \[[A-Z]+\] \S+: ", hp
        print("  · b2: оракул — health r5 (грамматика записи шире r6) — читатель держит r6, строже")
    assert H._STAMPISH_RE.pattern.encode() == b"^" + ER._STAMPISH_B.pattern
    src = HEALTH_SRC or H.__file__
    with open(src, "rb") as fh:
        hsha = hashlib.sha256(fh.read()).hexdigest()
    print("  · b2: оракул %s sha256 %s; правило pend — %s" % (src, hsha, "r7 (только запись истории до начала запуска)"
                                                          if _oracle_pend_r7() else "до r7 (любая запись < старта)"))


def _oracle_pend_r7():
    """Оракул держит правило pend r7: снятие pend в _run_verdict стоит под «ts < start - win and not seg»."""
    return "ts < start - win and not seg" in inspect.getsource(HL()._run_verdict)


def _pend_logs(sc):
    """Журналы правила pend (health r7 · verify8 K3/K4; build3) → (плохие, контроли): [(имя, строки)]."""
    ems, t = sc.ems, sc.ems + FRAC
    own = _dt.datetime.fromtimestamp(ems + 10, UTC).strftime("%Y-%m-%d %H:%M:%S")
    pend = L(ems - 30, INFO, "клиент:\n" + own + " текст")
    hist = history(ems)
    bad = [("PA: запись на старт − 1 с до запуска", hist + pend + L(ems - 1, INFO, "запись") + cand_proc(t)),
           ("PA: запись ровно на старт − 2 с до запуска", hist + pend + L(ems - 2, INFO, "запись") + cand_proc(t)),
           ("PB: запись на старт − 20 с ниже начала запуска", hist + pend + cand_proc(t) + L(ems - 20, INFO, "запись"))]
    good = [("история на старт − 3 с до запуска", hist + pend + L(ems - 3, INFO, "история") + cand_proc(t))]
    # K3/K4: текущий (MainPID) вошёл OK без polling и пишет раскладкой «[I]» / «имя:номер» — строки с меткой неизвестной
    # формы и датой ≥ старта; второй экземпляр (bot.py:73, жив) — полная цепочка через 5 с
    words = words_of()
    cur = boot_part(t, S().release_flags_line(words)) + L(t + 0.99, INFO, "  " + S().release_entry(words, frozenset())[1])
    for form, rep in (("[I]", (" [INFO] ", " [I] ")), ("имя:номер", (" turbobaby: ", " bot.py:73: "))):
        lay = [x.replace(*rep) for x in cur]
        assert all(ER._REC_B.match(x.encode()) is None and ER._STAMPISH_B.match(x.encode()) for x in lay), form
        sec = cand_proc(t + 5)
        bad += [("K3 %s: вставка на старт − 1 с до записей второго" % form, hist + lay + L(ems - 1, INFO, "x") + sec),
                ("K3 %s: вставка на старт − 1 с ниже начала второго" % form, hist + lay + sec + L(ems - 1, INFO, "x")),
                ("K3 %s: вставка на старт − 30 с ниже начала второго" % form, hist + lay + sec + L(ems - 30, INFO, "x")),
                ("K4 %s: шаг часов назад, запись второго на старт − 3 с" % form, hist + lay + sec + L(ems - 3, INFO, "x")),
                ("K3 %s: без вставки" % form, hist + lay + sec)]
        good += [("предел r7 (общий с health): K3 %s, вставка на старт − 3 с до записей второго" % form,
                  hist + lay + L(ems - 3, INFO, "x") + sec)]
    return bad, good


def test_b4_pend_rule_r7():
    """Правило pend = health r7 (build3, MAJOR линз code / атаки / спецификации круга 2; health рабочей копии rcfix2010
    1a8ba76f… :663, :692–696, :728): метку неизвестной формы с датой ≥ старта до начала запуска снимает ТОЛЬКО запись
    истории — метка < старт − 2 с и по месту ДО первой записи с меткой ≥ старта. Журналы PA / PB и K3 / K4 verify8 (две
    раскладки текущего) → читатель UNKNOWN stamp (build2 давал CLEAN); при оракуле с правилом r7 — health тоже UNKNOWN.
    Контроли — запись истории до начала запуска, в том числе ПРЕДЕЛ r7, общий с health (вставка на старт − 3 с до первой
    записи второго): читатель CLEAN, health OK — зеленее health читатель не становится и там."""
    sc = Sc()
    bad, good = _pend_logs(sc)
    r7 = _oracle_pend_r7()
    hv_bad = {}
    for name, lines in bad:
        sc.set_log(lines)
        r, _rc, _w = expect(sc, "UNKNOWN", "stamp")
        hv = _health(sc)
        hv_bad[hv] = hv_bad.get(hv, 0) + 1
        assert hv == "UNKNOWN" or not r7, (name, hv)
    for name, lines in good:
        sc.set_log(lines)
        expect(sc, "CLEAN")
        assert _health(sc) == "OK", name
    print("  · b4: журналов pend %d — читатель UNKNOWN stamp во всех, health %s; контролей %d — CLEAN / OK; оракул — %s"
          % (len(bad), sorted(hv_bad.items()), len(good), "r7" if r7 else "до r7 (там читатель строже)"))


def test_b3_second_writer_window():
    """Второй писатель (M2 круга 1, линза атаки): неоднозначность окна — как health r6 — по ВСЕМУ журналу, мимо выбора
    сегмента (записей загрузки или входа с меткой ≥ EMS − 2 с больше одной → UNKNOWN win_many); чужая цепочка базы над
    кодом V при code=OK → UNKNOWN gen_contra (не вход E-MIX), зеркально — цепочка кандидата при base; законное M-CODE
    (файлы новее процесса) — MIXED gen. Пределы (названы в шапке модуля): одна чужая цепочка в окне при молчащем текущем —
    для release health r6 тоже OK, для base у health вердикта OK нет."""
    sc = Sc()
    t = sc.ems + FRAC
    for off, cls in ((-1.5, "UNKNOWN"), (-0.4, "UNKNOWN"), (-2.6, "CLEAN")):
        sc.set_log(history(sc.ems) + L(sc.ems + off, INFO, ER.A_MSG) + cand_proc(t))
        r, _rc, _w = expect(sc, cls)
        assert (cls == "CLEAN") or "win_many" in why(r), (off, r["why"])
        assert _health(sc) == ("OK" if cls == "CLEAN" else "UNKNOWN") or not hasattr(HL(), "_WIN_BACK_S"), off
    sc.set_log(history(sc.ems) + cand_proc(t) + L(sc.ems + 200, WARNING, ER.A_MSG))       # загрузка любого уровня
    expect(sc, "UNKNOWN", "win_many")
    el_park = cand_lines({ACCR: "1"}, ())[2]
    sc.set_log(history(sc.ems) + L(sc.ems - 1.0, ERROR, "  " + el_park) + cand_proc(t))   # вход простоя в окне выше
    expect(sc, "UNKNOWN", "win_many")
    sc = Sc(state="release")
    sc.set_log(history(sc.ems) + base_proc(sc.ems + 40.0))
    r, _rc, _w = expect(sc, "UNKNOWN", "gen_contra")
    assert r["code"] == "OK" and r["head"] == SHA_V[:12], r
    sc = Sc(state="release")
    sc.set_log(history(sc.ems) + base_proc(sc.ems + FRAC))
    sc.mtime = {n: sc.ems + 600 for n in sc.tree}
    r, _rc, _w = expect(sc, "MIXED", "gen", absent="gen_contra")
    assert "code_newer" in why(r), r["why"]
    sc = Sc(state="base")
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC))
    expect(sc, "UNKNOWN", "gen_contra")
    sc = Sc(state="release")                                   # предел (1) health r6: одна чужая цепочка — и там OK
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + 40.0))
    expect(sc, "CLEAN")
    assert _health(sc) == "OK"
    sc = Sc(state="base")                                      # предел для базы: health — UNKNOWN по построению
    sc.set_log(history(sc.ems) + base_proc(sc.ems + 40.0))
    expect(sc, "CLEAN")
    assert _health(sc) == "UNKNOWN"


# =============================================================================================================================
# C. Личность
# =============================================================================================================================
def test_c1_each_key_changes_between_reads():
    for k, v in (("MainPID", "1249877"), ("ExecMainStartTimestampMonotonic", "1"), ("NRestarts", "4"),
                 ("InvocationID", "f" * 32), ("ActiveEnterTimestampMonotonic", "2"), ("SubState", "stop-sigterm")):
        for pos in (1, 2):
            sc = Sc()
            p = dict(sc.sp[0])
            p[k] = v
            sc.sp = [sc.sp[0]] * pos + [p]
            expect(sc, "UNKNOWN", "ident_changed")


def test_c2_boot_id_changes():
    sc = Sc()
    sc.boot = [BOOT.encode() + b"\n", b"9a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d\n"]
    expect(sc, "UNKNOWN", "boot_changed")
    sc = Sc()
    sc.boot = [b"not-a-boot-id\n"]
    expect(sc, "UNKNOWN", "rd_boot")


def test_c3_expect_run_foreign_park_is_unknown():
    sc = Sc().park_for_guard()
    r, rc, _w = expect(sc, "PARKED", argv=sc.args("--expect-run", sc.key()))
    assert rc == 51 and r["run"] == sc.key()
    foreign = key_with(sc.key(), pid=PID_SP + 1)
    r, rc, _w = expect(sc, "UNKNOWN", "expect_run", argv=sc.args("--expect-run", foreign))
    assert why(r)[0] == "expect_run" and rc == 59


def test_c4_prev_run():
    """--prev-run K0 (V3): boot тот же, pid ≠ K0, EMSmono > K0 и NRestarts = 0 — ручной рестарт счётчик обнуляет (шапка
    модуля; находка линзы code), при любом K0.nr. NRestarts > 0 — автоперезапуск после ручного → UNKNOWN prev_run, в том
    числе при NRestarts = K0.nr (семантика «не растит» тоже не проходит: отказ, а не CLEAN)."""
    sc = Sc(state="base")
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, 0)]
    for k0nr in (0, 3):
        good = "%s.%s.%d.%d.%d" % (BOOT[:8], INV_SP, 999, sc.emsm - 10 ** 7, k0nr)
        expect(sc, "CLEAN", argv=sc.args("--prev-run", good))
    for bad in ("%s.-.%d.%d.%d" % (BOOT[:8], PID_SP, sc.emsm - 10 ** 7, 3),         # тот же PID
                "%s.-.%d.%d.%d" % (BOOT[:8], 999, sc.emsm, 3),                       # EMSmono не больше
                "%s.-.%d.%d.%d" % ("9a2b3c4d", 999, sc.emsm - 10 ** 7, 3)):          # другая загрузка
        expect(sc, "UNKNOWN", "prev_run", argv=sc.args("--prev-run", bad))
    for nr in (1, 3):
        sc2 = Sc(state="base")
        sc2.sp = [props(PID_SP, sc2.ems, sc2.emsm, nr)]
        k0 = "%s.-.%d.%d.%d" % (BOOT[:8], 999, sc2.emsm - 10 ** 7, nr)
        expect(sc2, "UNKNOWN", "prev_run", argv=sc2.args("--prev-run", k0))


def test_c5_birth_delta():
    sc = Sc()
    tk = int(round(sc.emsm / 1e6 * TCK)) + 210
    sc.proc[PID_SP] = [(proc_stat(PID_SP, tk), b"0::/system.slice/splinter.service\n")]
    expect(sc, "UNKNOWN", "birth")
    sc = Sc()
    tk = int(round(sc.emsm / 1e6 * TCK)) + 190
    sc.proc[PID_SP] = [(proc_stat(PID_SP, tk), b"0::/system.slice/splinter.service\n")]
    expect(sc, "CLEAN")


def test_c6_cgroup_foreign():
    sc = Sc()
    st = sc.proc[PID_SP][0][0]
    sc.proc[PID_SP] = [(st, b"0::/system.slice/other.service\n1:name=systemd:/user.slice\n")]
    expect(sc, "UNKNOWN", "cgroup")


def test_c7_ae_ems():
    sc = Sc()
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP, ae_off_us=2100000)]
    expect(sc, "UNKNOWN", "ae_ems")
    sc = Sc()
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP, ae_off_us=1900000)]
    expect(sc, "CLEAN")


def test_c8_empty_invocation_when_active():
    sc = Sc()
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP, inv="")]
    expect(sc, "UNKNOWN", "rd_unit")


def test_c9_down():
    sc = Sc()
    sc.sp = [props(0, sc.ems, sc.emsm, NR_SP, act="inactive", sub="dead", inv="")]
    r, rc, w = expect(sc, "DOWN", "down")
    assert rc == 53 and r["proc"] == "DOWN" and r["run"].split(".")[1] == "-"
    assert not [x for x in w.reads if x.startswith("/proc/%d/" % PID_SP) or x.startswith("/proc/0/")], w.reads


def test_c10_transient_states():
    for act, sub in (("activating", "auto-restart"), ("activating", "start"), ("active", "exited"),
                     ("deactivating", "stop-sigterm"), ("reloading", "reload")):
        sc = Sc()
        sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP, act=act, sub=sub)]
        expect(sc, "UNKNOWN", "unit_transient")
    sc = Sc()
    sc.sp = [props(0, sc.ems, sc.emsm, NR_SP, act="failed", sub="failed", inv=""),
             props(PID_SP, sc.ems, sc.emsm, NR_SP)]
    expect(sc, "UNKNOWN", "ident_changed")


def test_c11_paren_in_comm():
    sc = Sc()
    tk = int(round(sc.emsm / 1e6 * TCK)) + 2
    sc.proc[PID_SP] = [(proc_stat(PID_SP, tk, comm="py) 9 9 9 (x"), b"0::/system.slice/splinter.service\n")]
    expect(sc, "CLEAN")


def test_c12_wa_changed():
    sc = Sc()
    sc.wa = [sc.wa[0], props(PID_WA + 1, sc.ems_wa, sc.emsm_wa, NR_WA, inv=INV_WA)]
    expect(sc, "UNKNOWN", "wa_ident")


def test_c13_show_read_failures():
    for name, fail in (("sp", ("rc", 1)), ("sp", subprocess.TimeoutExpired("systemctl", 15)),
                       ("wa", OSError("нет systemctl"))):
        sc = Sc()
        sc.fail[name] = (lambda i, f=fail: (f[1], b"") if isinstance(f, tuple) else f)
        expect(sc, "UNKNOWN", "rd_unit" if name == "sp" else "rd_wa")
    for raw in (b"MainPID=1\n", b"MainPID=1\nMainPID=2\n", b"Foo=bar\n"):
        sc = Sc()
        sc.raw["sp"] = raw
        expect(sc, "UNKNOWN", "rd_unit")


def test_c14_expect_wa_any_mode():
    """--expect-wa годен и без --guard (V2a/V3: Codex :12 «сверять KWA1»): ключ wa-agent S2 ≠ K в любом поле → UNKNOWN
    expect_wa; равен — класс прежний."""
    sc = Sc(state="base")
    expect(sc, "CLEAN", argv=sc.args("--expect-wa", sc.wa_key()))
    for kw in (key_with(sc.wa_key(), pid=PID_WA + 1), key_with(sc.wa_key(), inv="0" * 32),
               key_with(sc.wa_key(), emsm=1), key_with(sc.wa_key(), nr=NR_WA + 1), key_with(sc.wa_key(), boot="9a2b3c4d")):
        r, rc, _w = expect(sc, "UNKNOWN", "expect_wa", argv=sc.args("--expect-wa", kw))
        assert rc == 59


def test_c15_rd_proc():
    """/proc/<pid>/stat или /cgroup splinter не прочитан → UNKNOWN rd_proc (линза code m11)."""
    for part in ("stat", "cgroup"):
        sc = Sc()
        sc.fail["read:/proc/%d/%s" % (PID_SP, part)] = (lambda i: PermissionError(13, "нет прав"))
        expect(sc, "UNKNOWN", "rd_proc")


def test_c16_wa_every_unread_is_code():
    """wa-agent: не active → MIXED wa_down; метка старта не прочитана (пусто / n/a — M1 линзы атаки), рождение не то,
    cgroup чужая, пустой InvocationID, /proc не прочитан → UNKNOWN wa_ident; ни одна ветка не даёт wa=? без кода."""
    sc = Sc()
    sc.wa = [props(0, sc.ems_wa, sc.emsm_wa, NR_WA, act="inactive", sub="dead", inv="")]
    r, _rc, _w = expect(sc, "MIXED", "wa_down")
    assert r["wa"] == "down", r
    for txt in ("", "n/a"):
        for state in ("release", "base"):
            sc = Sc(state=state)
            sc.mtime["bot.py"] = sc.ems_wa + 10 if state == "base" else sc.mtime["bot.py"]
            p = props(PID_WA, sc.ems_wa, sc.emsm_wa, NR_WA, inv=INV_WA)
            p["ExecMainStartTimestamp"] = txt
            sc.wa = [p]
            r, _rc, _w = expect(sc, "UNKNOWN", "wa_ident")
            assert r["wa"] == "?", r
    sc = Sc()
    sc.proc[PID_WA] = [(sc.proc[PID_WA][0][0], b"0::/system.slice/other.service\n")]
    expect(sc, "UNKNOWN", "wa_ident")
    sc = Sc()
    sc.proc[PID_WA] = [(proc_stat(PID_WA, int(round(sc.emsm_wa / 1e6 * TCK)) + 250), b"0::/system.slice/wa-agent.service\n")]
    expect(sc, "UNKNOWN", "wa_ident")
    sc = Sc()
    sc.wa = [props(PID_WA, sc.ems_wa, sc.emsm_wa, NR_WA, inv="")]
    expect(sc, "UNKNOWN", "wa_ident")
    sc = Sc()
    sc.fail["read:/proc/%d/stat" % PID_WA] = (lambda i: OSError(5, "EIO"))
    expect(sc, "UNKNOWN", "wa_ident")


# =============================================================================================================================
# D. Часы и пояс
# =============================================================================================================================
def test_d1_adjtimex_unreadable():
    for x in (None, {"rc": -1, "maxerror": 0, "status": 0}, OSError("нет ctypes")):
        sc = Sc()
        sc.fail["adj"] = (lambda i, v=x: v) if isinstance(x, BaseException) else None
        if not isinstance(x, BaseException):
            sc.adj = [x]
        r, _rc, _w = expect(sc, "UNKNOWN", "clock_rd")
        assert r["clock"] == "?"


def test_d1b_adjtimex_layout_guard():
    """Настоящий World.adjtimex: машина вне x86_64/aarch64 или sizeof(long) ≠ 8 → None (clock_rd)."""
    if not hasattr(os, "uname"):
        print("  SKIP d1b: нет os.uname (не POSIX)")
        return
    orig = os.uname

    class _U:
        machine = "armv7l"
    try:
        os.uname = lambda: _U()
        assert ER.World().adjtimex() is None
    finally:
        os.uname = orig


def test_d2_maxerror_threshold():
    sc = Sc()
    sc.adj = [{"rc": 5, "maxerror": 16000000, "status": 64}]
    expect(sc, "UNKNOWN", "clock_unsync")
    sc = Sc()
    sc.adj = [{"rc": 5, "maxerror": 15999999, "status": 64}]
    r, _rc, _w = expect(sc, "CLEAN")
    assert r["clock"] == "SYNC" and r["maxerr"] == "15999"


def test_d3_not_before():
    sc = Sc()
    expect(sc, "UNKNOWN", "clock_past", argv=sc.args(nb=int(NOW) + 5))


def test_d4_ems_precise_vs_text():
    for off in (-0.1, 1.6):
        sc = Sc()
        sc.emsm = int(round((MONO0 - (sc.t0 - (sc.ems + off))) * 1e6))
        sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP)]
        tk = int(round(sc.emsm / 1e6 * TCK)) + 2
        sc.proc[PID_SP] = [(proc_stat(PID_SP, tk), b"0::/system.slice/splinter.service\n")]
        expect(sc, "UNKNOWN", "clock_step")
    sc = Sc()
    sc.t2 = sc.t0 + 5.0                    # стенные ушли на 5 с, монотонные — на 1,2: шаг во время прогона
    expect(sc, "UNKNOWN", "clock_step")


def test_d5_chain_mark_ahead():
    sc = Sc(age=7200)
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC) + L(sc.t2 + 3.5, INFO, "Running job x",
                                                             name="apscheduler.executors.default"))
    expect(sc, "UNKNOWN", "clock_ahead")


def test_d6_zone():
    for z in ((3600, 3600, 0), (0, -3600, 1), (-25200, -25200, 0)):
        sc = Sc()
        sc.zone = z
        r, _rc, _w = expect(sc, "UNKNOWN", "zone")
        assert r["tz"] == "NOTUTC"
    sc = Sc()
    sc.fail["zone"] = (lambda i: AttributeError("нет tzset"))
    r, _rc, _w = expect(sc, "UNKNOWN", "zone")
    assert r["tz"] == "?"


def test_d7_localtime_no_environment():
    """r2 п.1: свойство Environment не читается вовсе; пояс системы — readlink /etc/localtime."""
    for link, want_cls, tz in (("/usr/share/zoneinfo/Etc/UTC", "CLEAN", "UTC:link"), ("../usr/share/zoneinfo/UTC",
                               "CLEAN", "UTC:link"), ("/usr/share/zoneinfo/Asia/Bangkok", "UNKNOWN", "NOTUTC:link"),
                               (OSError(22, "Invalid argument"), "CLEAN", "UTC:file"),
                               (FileNotFoundError(2, "нет"), "CLEAN", "UTC:none"),
                               (PermissionError(13, "нет прав"), "UNKNOWN", "?:?")):
        sc = Sc()
        sc.link = link
        r, _rc, w = expect(sc, want_cls)
        assert "%s:%s" % (r["tz"], r["tzsrc"]) == tz, (link, r["tz"], r["tzsrc"])
    for argv in w.calls:
        assert not any("Environment" in x for x in argv), argv


def test_d8_unit_start_ahead():
    """Старт юнита по метке systemd позже t2 + 2 с → UNKNOWN clock_ahead (линза code m6)."""
    sc = Sc()
    sc.sp = [props(PID_SP, int(sc.t2) + 30, sc.emsm, NR_SP)]
    expect(sc, "UNKNOWN", "clock_ahead")


# =============================================================================================================================
# E. Журнал
# =============================================================================================================================
def test_e1_log_unread_short_rot_cap():
    sc = Sc()
    sc.fail["log_open"] = (lambda i: FileNotFoundError(2, "нет", "splinter.log"))
    expect(sc, "UNKNOWN", "rd_log")
    sc = Sc()
    size = os.path.getsize(sc.log_path)
    sc.fstat_after = (1, 77, size - 10, 2000)
    expect(sc, "UNKNOWN", "log_rot")                          # стал короче
    sc = Sc()
    sc.pstat = (1, 78)
    expect(sc, "UNKNOWN", "log_rot")                          # подменён по пути
    sc = Sc()
    sc.fstat_after = (1, 77, size, 2000)
    expect(sc, "UNKNOWN", "log_rot")                          # тот же размер, другой mtime
    sc = Sc()
    sc.fstat_after = (1, 77, size + 400, 2000)
    expect(sc, "CLEAN")                                       # рост за проход — не ротация (читается префикс; принято К3)
    old = ER.LOG_CAP_BYTES
    try:
        ER.LOG_CAP_BYTES = size - 1
        expect(Sc(), "UNKNOWN", "log_cap")
    finally:
        ER.LOG_CAP_BYTES = old
    old = ER.RUN_LINES_CAP
    try:
        ER.RUN_LINES_CAP = 5
        expect(Sc(), "UNKNOWN", "log_cap")
    finally:
        ER.RUN_LINES_CAP = old


def test_e1b_log_short_read():
    class _Short(FakeWorld):
        def log_fstat(self, fh):
            t = FakeWorld.log_fstat(self, fh)
            return (t[0], t[1], t[2] + 100, t[3]) if self.n["fstat"] == 1 else (t[0], t[1], t[2] + 100, t[3])
    sc = Sc()
    rc, text, r, _w = run_er(sc, world=_Short(sc))
    assert r["class"] == "UNKNOWN" and "log_short" in why(r), text


def test_e2_premise():
    sc = Sc()
    sc.set_log(history(sc.ems, "killed") + base_proc(sc.ems - 3000)[:6] + cand_proc(sc.ems - 2000))
    expect(sc, "UNKNOWN", "premise")                          # текущий не дошёл до bot.py:94: последняя a старше EMS
    sc = Sc()
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC + 3600))
    expect(sc, "UNKNOWN", "premise")                          # пояс журнала +1 ч
    sc = Sc()
    sc.set_log([])
    expect(sc, "UNKNOWN", "premise")


def test_e3_chain_above_segment():
    """Вставка цепочки текстом клиента выше последней a с меткой ≥ EMS → chain_dup."""
    sc = Sc()
    t = sc.ems + FRAC
    fake = "клиент:\n" + "".join(L(t + 0.5, INFO, POLL)).rstrip("\n")
    sc.set_log(history(sc.ems) + L(t + 0.2, INFO, fake) + cand_proc(t + 1))
    expect(sc, "UNKNOWN", "chain_dup")


def test_e4_dups():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 80, INFO, POLL))
    expect(sc, "UNKNOWN", "chain_dup")
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 80, INFO, "  🔁 передача карточек: передачи нет"))
    expect(sc, "UNKNOWN", "chain_dup")
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 80, WARNING, ER.A_MSG))
    expect(sc, "UNKNOWN", "chain_dup")


def test_e5_order():
    sc = Sc()
    t = sc.ems + FRAC
    words = words_of()
    el = S().release_entry(words, frozenset())[1]
    lines = boot_part(t, S().release_flags_line(words)) + L(t + 1.247, INFO, POLL) + L(t + 1.3, INFO, "  " + el) \
        + L(t + 1.403, INFO, ER.E_MSG) + L(t + 1.406, INFO, ER.F_HEAD + "передачи нет")
    sc.set_log(history(sc.ems) + lines)
    expect(sc, "UNKNOWN", "chain_order")
    sc.set_log(history(sc.ems) + boot_part(t, S().release_flags_line(words)) + L(t + 0.5, INFO, "  " + el)
               + tail_part(t))
    expect(sc, "UNKNOWN", "chain_order")                       # c раньше b по метке


def test_e6_age_300():
    r, _rc, _w = expect(Sc(age=299), "UNKNOWN", "young")
    assert r["proc"] == "?"
    expect(Sc(age=300), "CLEAN")


def test_e7_partial():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t, f=False, jobs=False))
    expect(sc, "UNKNOWN", "chain_partial")
    words = words_of()
    sc.set_log(history(sc.ems) + boot_part(t, S().release_flags_line(words)) + tail_part(t))
    expect(sc, "UNKNOWN", "chain_partial")                    # d без c у вершины


def test_e8_stamp_and_utf8():
    sc = Sc()
    t = sc.ems + FRAC
    stampish = _dt.datetime.fromtimestamp(t + 1.0, UTC).strftime("%Y-%m-%d %H:%M:%S") + " Bot polling started"
    words = words_of()
    el = S().release_entry(words, frozenset())[1]
    chain = boot_part(t, S().release_flags_line(words)) + [stampish + "\n"] + L(t + 0.99, INFO, "  " + el) + tail_part(t)
    sc.set_log(history(sc.ems) + chain)
    expect(sc, "UNKNOWN", "stamp")
    sc.set_log(history(sc.ems) + boot_part(t, S().release_flags_line(words)) + [b"\xc3\x28 bad\n"]
               + L(t + 0.99, INFO, "  " + el) + tail_part(t))
    expect(sc, "UNKNOWN", "utf8")
    # ниже f: те же байты — как health (весь текущий запуск; принято К3 21.10), а не «без влияния» r1 e8
    sc.set_log(history(sc.ems) + cand_proc(t) + [stampish.replace(" Bot", "x") + "\n"])
    expect(sc, "UNKNOWN", "stamp")
    sc.set_log(history(sc.ems) + cand_proc(t) + ["2001-01-01 00:00:00 старая дата в тексте\n"])
    expect(sc, "UNKNOWN", "stamp")                            # дата прошлого: правило «в запуске», а не pend
    sc.set_log(history(sc.ems) + cand_proc(t) + ["2026-13-45 00:00:00,123 [INFO] turbobaby: невозможная дата\n"])
    expect(sc, "UNKNOWN", "stamp")                            # запись с неразобранной меткой в запуске
    sc.set_log(history(sc.ems) + cand_proc(t) + [b"\xff tail\n"])
    expect(sc, "UNKNOWN", "utf8")
    # в истории (до запуска, и за ними запись истории) — без влияния
    sc.set_log(history(sc.ems, "none") + [b"\xff old\n", (stampish[:4] + "-01-01 00:00:00 old\n").encode()]
               + history(sc.ems) + cand_proc(t))
    expect(sc, "CLEAN")


def test_e18_back_step_120():
    """Запись текущего запуска раньше уже прочитанной больше чем на 120 с → clock_step (= health _BACK_SKEW_S)."""
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 500, INFO, "x") + L(t + 379, INFO, "y"))
    expect(sc, "UNKNOWN", "clock_step")
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 500, INFO, "x") + L(t + 381, INFO, "y"))
    expect(sc, "CLEAN")


def test_e19_pend_stamp_before_run():
    """Метка неизвестной формы с датой ≥ старта ДО записей запуска и без записи истории после неё → stamp (= health
    pend); с записью истории после неё — текст прошлого, без влияния. build3 (= health r7): запись в окне [старт − 2 с,
    старт) (PA) и запись с меткой < старта НИЖЕ начала запуска (PB) историей не бывают — stamp; граница — старт − 2 с."""
    sc = Sc()
    t = sc.ems + FRAC
    own = _dt.datetime.fromtimestamp(sc.ems + 10, UTC).strftime("%Y-%m-%d %H:%M:%S")
    hist = history(sc.ems)
    sc.set_log(hist + L(sc.ems - 30, INFO, "клиент:\n" + own + " текст") + cand_proc(t))
    expect(sc, "UNKNOWN", "stamp")
    sc.set_log(hist + L(sc.ems - 30, INFO, "клиент:\n" + own + " текст") + L(sc.ems - 20, INFO, "история")
               + cand_proc(t))
    expect(sc, "CLEAN")
    pend = L(sc.ems - 30, INFO, "клиент:\n" + own + " текст")
    for at, below in ((sc.ems - 1, False), (sc.ems - 2, False), (sc.ems - 1.999, False), (sc.ems - 20, True),
                      (sc.ems - 1, True)):
        rec = L(at, INFO, "запись")
        sc.set_log(hist + pend + (cand_proc(t) + rec if below else rec + cand_proc(t)))
        r, _rc, _w = expect(sc, "UNKNOWN", "stamp")
        assert why(r) == ["stamp"], (at, below, r["why"])
    sc.set_log(hist + pend + L(sc.ems - 2.001, INFO, "история") + cand_proc(t))
    expect(sc, "CLEAN")                                       # метка ⌊…⌋ = старт − 3 с < старт − 2 с — запись истории


def test_e9_stop_in_segment():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t) + stop_part(t + 100))
    expect(sc, "UNKNOWN", "stop_line")


def test_e10_parked_every_form():
    for build in (lambda t: cand_proc(t, {ACCR: "1"}), lambda t: cand_proc(t, {STRICT: "maybe"}), notread_proc,
                  crash_proc):
        sc = Sc()
        sc.set_log(history(sc.ems) + build(sc.ems + FRAC))
        r, rc, _w = expect(sc, "PARKED", "park")
        assert rc == 51 and r["proc"] == "PARKED" and r["gen"] == "cand" and r["entry"] in ("MISMATCH", "UNKNOWN")
        assert why(r) == ["park"], r["why"]


def test_e11_park_with_intake():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t, {ACCR: "1"}) + L(t + 30, INFO, "Splinter [intake] Иван +66 81 234 5678"))
    expect(sc, "UNKNOWN", "park_contra")
    sc.set_log(history(sc.ems) + cand_proc(t, {ACCR: "1"}) + L(t + 30, INFO, ER.E_MSG))
    expect(sc, "UNKNOWN", "park_contra")


def test_e12_old_polling_above_park():
    """Над простоем — прежний работавший процесс с d и f: PARKED; «active + PID + старая строка старта» CLEAN не даёт."""
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(cand_proc(sc.ems - 86400) + cand_proc(t, {ACCR: "1"}))
    expect(sc, "PARKED", "park")
    sc.set_log(cand_proc(sc.ems - 86400))
    r, _rc, _w = expect(sc, "UNKNOWN", "premise")
    assert r["proc"] != "POLLING"


def test_e13_nopoll():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t, d=False, e=False, f=False, jobs=False))
    expect(sc, "NOPOLL", "nopoll")
    sc.set_log(history(sc.ems) + cand_proc(t, e=False, f=False, jobs=False))
    r, rc, _w = expect(sc, "NOPOLL", "nopoll")
    assert rc == 52


def test_e14_base():
    """База: CLEAN. Цепочка кандидата при --state base: файлы не новее процесса — противоречие gen_contra (UNKNOWN), а
    при файлах новее процесса (законное M-CODE) — MIXED gen."""
    r, rc, _w = expect(Sc(state="base"), "CLEAN")
    assert r["gen"] == "base" and r["entry"] == "NONE" and r["flags"] == "1n.0n" and rc == 0
    sc = Sc(state="base")
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC))
    expect(sc, "UNKNOWN", "gen_contra")
    sc.mtime = {n: sc.ems + 600 for n in sc.tree}
    expect(sc, "MIXED", "gen", absent="gen_contra")


def test_e15_traceback_in_chain():
    sc = Sc()
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, tb=True))
    r, rc, _w = expect(sc, "MIXED", "tb_start")
    assert r["tb"] == "1" and rc == 54
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC) + L(sc.ems + 200, ERROR, "сбой", exc_info=_exc()))
    r, _rc, _w = expect(sc, "CLEAN")                           # Traceback ниже f — вне окна цепочки
    assert r["tb"] == "0"


def test_e16_chunks_same_verdict():
    for build in (lambda sc: history(sc.ems) + cand_proc(sc.ems + FRAC),
                  lambda sc: history(sc.ems) + cand_proc(sc.ems + FRAC, {ACCR: "1"}),
                  lambda sc: [b"line\r\nanother\rthird\n"] + history(sc.ems) + cand_proc(sc.ems + FRAC)):
        base = None
        for mx in (None, 1, 2, 3, 7, 64, 4095, 8192):
            sc = Sc()
            sc.set_log(build(sc))
            sc.maxread = mx
            rc, text, r, _w = run_er(sc)
            if base is None:
                base = text
            assert text == base, (mx, text, base)


def test_e17_handoff_words():
    for ho, word, cls in (("передачи нет", "none", "CLEAN"),
                          ("применена (sha 0a1b2c3d): брони 1 · выдачи 2 · закрытия 0 · занятых мест 1", "applied:4",
                           "CLEAN"), ("повторно не применяю: метка той же передачи (sha 0a1b2c3d)", "repeat", "CLEAN"),
                          ("НЕ применена: файл не прочитан — сохранён как есть", "notapplied", "MIXED"),
                          ("нечего передавать", "other", "MIXED")):
        sc = Sc()
        sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, ho=ho))
        r, _rc, _w = expect(sc, cls)
        assert r["ho"] == word, (ho, r["ho"])


def test_e20_grammar_codes():
    """Каждый код грамматики цепочки — свой исход (линза code m8–m10): flags_grammar, entry_grammar (иной текст INFO и
    уровень WARNING), flags_entry (2 ключа при строке входа, в т.ч. у простоя; слова вне RELEASE_ENTRY_STATES)."""
    t0 = Sc()
    t = t0.ems + FRAC
    words = words_of()
    bl = S().release_flags_line(words)
    el = S().release_entry(words, frozenset())[1]
    el_park = cand_lines({ACCR: "1"}, ())[2]
    assert cand_lines({ACCR: "1"}, ())[1] is None, el_park                 # строка простоя (MISMATCH)
    cases = (
        ("flags_grammar", boot_part(t, "🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · CLOSE_TRUTH=ВКЛ (не задан)")
         + L(t + 0.99, INFO, "  " + el) + tail_part(t)),
        ("entry_grammar", boot_part(t, bl) + L(t + 0.99, INFO, ER.C_HEAD + "OK — иной текст") + tail_part(t)),
        ("entry_grammar", boot_part(t, bl) + L(t + 0.99, WARNING, "  " + el) + tail_part(t)),
        ("flags_entry", boot_part(t, BASE_B) + L(t + 0.99, ERROR, "  " + el_park)),
        ("flags_entry", boot_part(t, cand_lines({ACCR: "1"}, ())[0]) + L(t + 0.99, INFO, "  " + el)
         + tail_part(t)),
    )
    for code, lines in cases:
        sc = Sc()
        sc.set_log(history(sc.ems) + lines)
        expect(sc, "UNKNOWN", code)


def test_e21_park_without_b():
    """Строка простоя без строки флагов в сегменте → UNKNOWN chain_partial, а не PARKED (линза code m7)."""
    sc = Sc()
    t = sc.ems + FRAC
    el_park = cand_lines({ACCR: "1"}, ())[2]
    sc.set_log(history(sc.ems) + L(t + 0.912, INFO, ER.A_MSG) + L(t + 0.99, ERROR, "  " + el_park))
    expect(sc, "UNKNOWN", "chain_partial")


def test_e22_state_and_fv():
    """state: процесс truth_off при --state release → MIXED со «state»; fv: строка флагов базы не по шаблону → MIXED fv
    (линза code m1)."""
    sc = Sc(state="release")
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, {TRUTH: "0"}, ("CLOSE_TRUTH",)))
    expect(sc, "MIXED", "state")
    sc = Sc(state="base")
    sc.set_log(history(sc.ems) + base_proc(sc.ems + FRAC, bmsg="🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВЫКЛ (задан) · "
                                                               "CONTRACT_REF_GEN=ВЫКЛ (не задан)"))
    expect(sc, "MIXED", "fv")


def test_e23_record_grammar_r6():
    """Запись — только ТОЧНЫЙ формат bot.py:73 (health r6): уровень не из пяти имён logging («[I]», «[info]») или имя не
    точечный идентификатор («bot.py:73», префикс потока) — строка с меткой неизвестной формы → в текущем запуске UNKNOWN
    stamp; в истории (за ней запись истории) — без влияния."""
    sc = Sc()
    t = sc.ems + FRAC
    stamp = _dt.datetime.fromtimestamp(t + 60, UTC).strftime("%Y-%m-%d %H:%M:%S") + ",123"
    for ln in (stamp + " [I] turbobaby: строка\n", stamp + " [info] turbobaby: строка\n",
               stamp + " [INFO] bot.py:73: строка\n", stamp + " [INFO] Thread-1 turbobaby: строка\n"):
        sc.set_log(history(sc.ems) + cand_proc(t) + [ln])
        expect(sc, "UNKNOWN", "stamp")
    old = _dt.datetime.fromtimestamp(sc.ems - 7200, UTC).strftime("%Y-%m-%d %H:%M:%S") + ",123 [I] turbobaby: старое\n"
    sc.set_log(history(sc.ems, "none") + [old] + history(sc.ems) + cand_proc(t))
    expect(sc, "CLEAN")


def test_e24_window_lower_bound():
    """Нижняя граница окна записей начала — max(⌊EMS точный⌋, EMS): при дрожании пары часов −3 мс (в допуске EMS_EPS_S)
    запись загрузки на EMS − 0,5 с — вне окна (premise), как у health «старт ≤ метка», а не на секунду шире."""
    sc = Sc()
    sc.emsm = int(round((MONO0 - (sc.t0 - (sc.ems - 0.003))) * 1e6))
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP)]
    tk = int(round(sc.emsm / 1e6 * TCK)) + 2
    sc.proc[PID_SP] = [(proc_stat(PID_SP, tk), b"0::/system.slice/splinter.service\n")]
    sc.set_log(history(sc.ems) + cand_proc(sc.ems - 1.412))
    r, _rc, _w = expect(sc, "UNKNOWN", "premise")
    assert "clock_step" not in why(r), r["why"]


# =============================================================================================================================
# F. Код и git
# =============================================================================================================================
def test_f1_code():
    sc = Sc()
    sc.head = "9" * 40
    expect(sc, "MIXED", "head")
    sc = Sc()
    sc.origin = "9" * 40
    expect(sc, "MIXED", "origin")
    sc = Sc()
    sc.fail["origin"] = (lambda i: (128, b""))
    r, rc, _w = expect(sc, "UNKNOWN", "rd_origin")
    assert why(r) == ["rd_origin"] and r["origin"] == "?" and rc == 59
    sc = Sc()
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, {ACCR: "1"}))
    sc.fail["origin"] = (lambda i: subprocess.TimeoutExpired("git", 60))
    expect(sc, "PARKED", absent="rd_origin")
    sc = Sc()
    sc.status = b" M splinter.py\n"
    expect(sc, "MIXED", "dirty")
    sc = Sc()
    sc.work["health.py"] = "5" * 40
    r, _rc, _w = expect(sc, "MIXED", "blob")
    assert r["code"] == "BLOB" and r["code_k"] == "1"
    sc = Sc()
    sc.mtime["wa_agent.py"] = sc.ems + 5
    r, _rc, _w = expect(sc, "MIXED", "code_newer")
    assert "wa_newer" in why(r) and r["code"] == "NEWER"
    sc = Sc()
    sc.mtime["wa_agent.py"] = sc.ems_wa + 5
    r, _rc, _w = expect(sc, "MIXED", "wa_newer", absent="code_newer")
    assert r["wa"].startswith("newer")
    sc = Sc(state="base")
    sc.tree["bot.py"] = sc.work["bot.py"] = "6" * 40
    expect(sc, "MIXED", "base_blob")


def test_f2_each_git_call_failure():
    for name in ("head", "status", "lstree", "hash"):
        for fail in ((lambda i: (128, b"")), (lambda i: subprocess.TimeoutExpired("git", 15))):
            sc = Sc()
            sc.fail[name] = fail
            r, _rc, _w = expect(sc, "UNKNOWN", "rd_git")
            assert r["head"] == "?" and r["dirty"] == "?", r
    sc = Sc()
    sc.fail["mtime"] = (lambda i: PermissionError(13, "нет прав"))
    expect(sc, "UNKNOWN", "rd_git")
    for raw in (b"zzz\n", b"100644 blob " + b"1" * 40 + b"\tsp ace.py\n"):
        sc = Sc()
        sc.raw["lstree"] = raw
        expect(sc, "UNKNOWN", "rd_git")


# =============================================================================================================================
# G. drop-in
# =============================================================================================================================
def _dropin_sc(state, L_, D_, body_ok=True, link=False, ndr="no", entry_state=None, gen="cand"):
    sc = Sc(state=state)
    if gen == "base":
        sc = Sc(state="base")
    ep = entry_state or state
    if gen == "cand":
        env = {TRUTH: "0"} if ep == "truth_off" else None
        unit = ("CLOSE_TRUTH",) if ep == "truth_off" else ()
        sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, env, unit))
    paths = [p for x, p in (("b", ER.DB), ("u", ER.DU)) if x in L_]
    sc.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": ndr, "DropInPaths": " ".join(["/etc/x.conf"] + paths)}]
    sc.dropin = {}
    for x, p, pin in (("b", ER.DB, DB_PIN), ("u", ER.DU, DU_PIN)):
        if x in D_:
            sc.dropin[p] = ("link" if link else "file", pin if body_ok else "0" * 64)
        else:
            sc.dropin[p] = ("absent", None)
    return sc


def test_g1_dropin_grid():
    cases = 0
    for L_, D_, body_ok, link, ndr, ep in itertools.product(("", "b", "u", "bu"), ("", "b", "u", "bu"), (True, False),
                                                           (False, True), ("no", "yes"), ("release", "truth_off")):
        sc = _dropin_sc(ep, L_, D_, body_ok, link, ndr, ep)
        r = run_er(sc)[2]
        cases += 1
        bad = (D_ and (not body_ok or link)) or L_ == "u" or D_ == "u"
        armed = L_ != D_ or ndr == "yes" or (ep == "release" and L_ == "b")
        if bad:
            want = "BAD"
        elif armed:
            want = "ARMED"
        else:
            want = "OK"
        assert r["dropin"] == want, (L_, D_, body_ok, link, ndr, ep, r["dropin"], r["why"])
        if want == "BAD":
            assert "dropin_bad" in why(r) and r["class"] != "CLEAN", (L_, D_, r["why"])
        src = ep == "truth_off" and L_ != "b"
        if want == "OK" and not src and ndr == "no":
            assert r["class"] == "CLEAN", (L_, D_, ep, r["why"])
        if src:
            assert "state_src" in why(r), (L_, D_, ep, r["why"])
    assert cases == 256
    r = run_er(_dropin_sc("release", "b", "b"))[2]                     # A-39
    assert r["class"] == "ARMED" and why(r) == ["dropin_armed"], r["why"]
    r = run_er(_dropin_sc("truth_off", "", "", entry_state="truth_off"))[2]
    assert r["class"] == "MIXED" and "state_src" in why(r)
    r = run_er(_dropin_sc("base", "b", "b", gen="base"))[2]          # для базы свои файлы инертны
    assert r["class"] == "CLEAN", r["why"]
    sc = _dropin_sc("release", "bb", "b")
    sc.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "no", "DropInPaths": ER.DB + " " + ER.DB}]
    assert run_er(sc)[2]["dropin"] == "BAD"


def test_g2_dropin_read_failures():
    sc = Sc()
    sc.dropin[ER.DB] = (PermissionError(13, "нет прав"), None)
    expect(sc, "UNKNOWN", "rd_dropin")
    sc = _dropin_sc("truth_off", "b", "b")
    sc.fail["hash:" + ER.DB] = (lambda i: OSError(5, "EIO"))
    expect(sc, "UNKNOWN", "rd_dropin")
    sc = Sc()
    sc.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "maybe", "DropInPaths": ""}]
    expect(sc, "UNKNOWN", "rd_cfg")
    sc = Sc()
    sc.cfg_wa = [{"LoadState": "not-found", "NeedDaemonReload": "no"}]
    r, rc, _w = expect(sc, "ARMED", "ndr")
    assert r["ndr_wa"] == "yes" and rc == 55


# =============================================================================================================================
# H. Квитанция
# =============================================================================================================================
def test_h1_receipt_grammar_and_codes():
    table = {"CLEAN": 0, "PARKED": 51, "NOPOLL": 52, "DOWN": 53, "MIXED": 54, "ARMED": 55, "UNKNOWN": 59}
    seen = set()
    for txt in list(RECEIPTS) + [run_er(Sc())[1].rstrip("\n")]:
        assert "\n" not in txt and len(txt) <= ER.RECEIPT_MAX and txt.isascii(), txt
        assert ER.RECEIPT_RE.fullmatch(txt), txt
    for sc, cls in ((Sc(), "CLEAN"), (Sc().park_for_guard(), "PARKED"), (_dropin_sc("release", "b", "b"), "ARMED")):
        rc, text, r, _w = run_er(sc)
        assert r["class"] == cls and rc == table[cls], (cls, rc, text)
        seen.add(cls)
        assert text.count("\n") == 1
        fields = [p.split("=", 1)[0] for p in text.split()[2:]]
        assert fields == ["class", "want", "label", "run", "unit", "ems", "ae", "birth", "age", "clock", "tz", "git", "code",
                          "gen", "proc", "entry", "ebad", "flags", "ho", "tb", "intake", "dropin", "dpaths", "ndr", "wa",
                          "guard", "why"], fields
    assert ER.CODE == table
    assert set(ER.WHY_UNKNOWN) & set(ER.WHY_MIXED) == set() and len(set(ER.ORDER)) == len(ER.ORDER)
    for c in ("expect_wa", "win_many", "gen_contra", "clean_gate"):
        assert ER.CLASS_OF[c] == "UNKNOWN", c


def test_h2_usage():
    sc = Sc()
    base = sc.args()
    sb = Sc(state="base")
    bad = [([], "no_args"), (["--bogus", "1"], "unknown"), (base + ["--sha", SHA_V], "repeat"),
           (base[:-2], "missing_du_sha"), (["--sha", "XYZ"] + base[2:], "form_sha"),
           (base[:4] + ["--label", "has space"] + base[6:], "form_label"),
           (base[:4] + ["--label", LABEL + "\n"] + base[6:], "form_label"),
           (["--sha", SHA_V + "\n"] + base[2:], "form_sha"),
           (base + ["--guard", "unpark"], "guard_needs_expect_run"),
           (sb.args("--expect-run", sb.key(), "--guard", "unpark"), "guard_needs_expect_wa"),
           (sc.args("--expect-run", sc.key(), "--expect-wa", sc.wa_key(), "--guard", "unpark"), "guard_needs_base"),
           (sc.args("--expect-run", "zzz"), "form_expect_run"), (sc.args("--expect-wa", "zzz"), "form_expect_wa"),
           (base + ["--against", "ENTRY_READ r1 x"], "against_without_recheck"),
           (["--recheck"] + base, "missing_expect_run"), (base + ["--state"], "repeat"),
           (base + ["--not-before", "-5"], "repeat")]
    for argv, cls in bad:
        out = io.StringIO()
        rc = ER.main(argv, world=FakeWorld(sc), out=out)
        assert rc == 50 and out.getvalue() == "ENTRY_READ_USAGE %s\n" % cls, (argv, rc, out.getvalue())


def test_h3_internal_exception():
    sc = Sc()
    sc.fail["wall"] = (lambda i: RuntimeError("стенд"))
    rc, text, r, _w = run_er(sc)
    assert rc == 59 and r["class"] == "UNKNOWN" and why(r) == ["internal"], text
    sc = Sc().park_for_guard()
    sc.fail["wall"] = (lambda i: RuntimeError("стенд"))
    rc, text, r, _w = run_er(sc, sc.args("--expect-run", sc.key(), "--expect-wa", sc.wa_key(), "--guard", "unpark"))
    assert rc == 58 and r["guard"] == "REFUSED" and why(r)[0] == "internal", text


def test_h4_prefix_ere():
    rx = re.compile(ER.RECEIPT_PREFIX_ERE)
    good = list(RECEIPTS) + [run_er(Sc())[1].rstrip("\n")]
    assert all(rx.match(x) for x in good)
    g = good[-1]
    spoiled = [g.replace("class=CLEAN", "class=FINE"), g.replace("want=release@" + SHA_V, "want=release@" + SHA_V[:39]),
               g.replace("label=" + LABEL, "label=a b"), g[:-10], g + "\nENTRY_READ r1 x", g.replace("ENTRY_READ r1", "ENTRY_READ r2"),
               g.replace("want=release", "want=prod"), g.replace("guard=-", "guard=OK"), g.replace("why=ok", "why=OK"),
               g.replace("run=" + Sc().key(), "run=zz"), " " + g, g.replace("why=ok", "why=")]
    assert len(spoiled) == 12
    for x in spoiled:
        assert not rx.fullmatch(x), x


def test_h5_no_pii_in_receipt():
    sc = Sc()
    t = sc.ems + FRAC
    sc.set_log(history(sc.ems) + cand_proc(t) + L(t + 30, INFO, "Splinter [intake] Иван Петров +66 81 234 5678 bait-QZ9"))
    rc, text, r, _w = run_er(sc)
    for bait in ("Иван", "Петров", "234 5678", "bait", "QZ9", "+66"):
        assert bait not in text, text
    assert r["intake"] == "1"


def _h7_spoils(P, st):
    """Порчи фактов P → [(условие, {поле: значение})]: каждая ломает одно условие ворот (build3: и «личность перечитана»,
    и условия §5/§6/§8, которые прежде держали только коды)."""
    sp, wa, bi, boot = P["sp"], P["wa_id"], P["birth"], P["boot"]
    u, scan = sp[2], P["scan"]
    seg = scan["seg"]
    rec = seg["rec"]

    def sg(**kw):
        return {"scan": dict(scan, seg=dict(seg, **kw))}

    def sc_(**kw):
        return {"scan": dict(scan, **kw)}
    out = [("ident", {"sp": (sp[0], sp[1], dict(u, nr=u["nr"] + 1))}), ("ident", {"sp": (sp[0], dict(u, pid=7), u)}),
           ("ident", {"sp": (None, sp[1], sp[2])}), ("ident", {"boot": (boot[0], "9a2b3c4d")}),
           ("ident", {"boot": (None, boot[1])}), ("ident", {"wa_id": (wa[0], dict(wa[1], pid=wa[1]["pid"] + 1))}),
           ("ident", {"wa_id": (wa[0], None)}), ("ident", {"birth": (bi[0], (bi[0][0] + 5, bi[0][1]))}),
           ("ident", {"birth": (bi[0], None)}),
           ("run", {"sp": tuple(dict(x, act="activating") for x in sp)}), ("run", {"sp": tuple(dict(x, inv="") for x in sp)}),
           ("run", {"key": None}),
           ("birth", {"birth": ((bi[0][0] + 300, True), (bi[0][0] + 300, True))}),
           ("birth", {"birth": ((bi[0][0], False), (bi[0][0], False))}), ("birth", {"tck": None}),
           ("birth", {"sp": tuple(dict(x, aem=x["emsm"] + 2100000) for x in sp)}),
           ("expect", {"expect_run": key_with(P["key"], pid=PID_SP + 1)}),
           ("expect", {"expect_wa": key_with(P["wa_key"], nr=NR_WA + 1)}), ("expect", {"prev_run": P["key"]}),
           ("expect", {"prev_run": key_with(P["key"], pid=PID_SP + 1, boot="9a2b3c4d")}),
           ("expect", {"prev_run": key_with(P["key"], pid=PID_SP + 1, emsm=u["emsm"] + 1)}),
           ("expect", {"prev_run": key_with(P["key"], pid=PID_SP + 1, emsm=u["emsm"] - 1),
                       "sp": tuple(dict(x, nr=1) for x in sp)}),
           ("clock", {"clock": "UNSYNC"}), ("clock", {"tz": "NOTUTC"}),
           ("time", {"nb": int(P["t0"][0]) + 5}), ("time", {"t2": (P["t0"][0] - 1.0, P["t2"][1])}),
           ("time", {"t2": (P["t2"][0] + 0.6, P["t2"][1])}), ("time", {"ems_dd": 1.5}), ("time", {"ems_dd": -0.006}),
           ("time", {"ems_dd": None}), ("time", {"sp": tuple(dict(x, ems=int(P["t2"][0]) + 3) for x in sp)}),
           ("time", sc_(max_cur=P["t2"][0] + 2.5)),
           ("log", {"log_err": "log_rot"}), ("log", {"scan": None}), ("log", sc_(ahead_at=scan["hist_at"] + 1)),
           ("log", sc_(lines_max=ER.RUN_LINES_CAP + 1)), ("log", sc_(win={"a": 2, "c": 1})),
           ("log", sc_(win={"a": 1, "c": 2}))]
    out += [("log", sc_(cnt=dict(scan["cnt"], **{k: 1}))) for k in sorted(scan["cnt"])]
    out += [("chain", {"chain": False}), ("chain", sc_(seg=None)), ("chain", sc_(above=1)), ("chain", sg(win_a=False)),
            ("chain", sg(dup=True)), ("chain", sg(order=True)), ("chain", sg(win_bf=True)), ("chain", sg(stop=True))]
    for k in ("b", "d", "e", "f"):
        out.append(("chain", sg(rec=dict((x, y) for x, y in rec.items() if x != k))))
    for k in ("d", "e", "f"):
        out.append(("chain", sg(rec=dict(rec, **{k: (rec[k][0], "WARNING", rec[k][2])}))))
    for k, bad in (("proc", "NOPOLL"), ("gen", "cand" if st == "base" else "base"), ("entry", "MISMATCH"), ("fv", True),
                   ("ho", "notapplied"), ("tb", 1), ("age", 299.0), ("head", "9" * 40), ("origin", "9" * 40),
                   ("dirty", 1), ("nblob", 1), ("nnew", 1), ("wa", "newer"), ("wa_key", "?"), ("ndr", ("no", "yes")),
                   ("dropin", "ARMED"), ("lset", frozenset("bu") if st != "release" else frozenset("b")),
                   ("dset", frozenset("u"))):
        out.append(({"fv": "flags", "nblob": "code", "nnew": "code", "head": "git", "origin": "git", "dirty": "git",
                     "wa_key": "wa", "lset": "dropin", "dset": "dropin"}.get(k, k), {k: bad}))
    if st == "base":
        out.append(("base_blob", {"base_blob": False}))
    return out


def test_h7_clean_positive_table():
    """CLEAN — положительная таблица по ФАКТАМ (линза code круга 1 и MAJOR-1 круга 2: не «отсутствие кодов»): на годных
    фактах каждого --state _clean_proven пуст, а порча КАЖДОГО условия по отдельности — в том числе «личность
    перечитана» (S0 = S1 = S2, boot0 = boot2, birth0 = birth1, wa S0 = S2) и условий §5/§6/§8 — роняет именно его."""
    names = set()
    for st in ("release", "truth_off", "base"):
        sc = Sc(state=st)
        a = ER.parse_args(sc.args())
        v = ER.judge(ER.read_current(FakeWorld(sc), a), a)
        P = v["proof"]
        assert v["class"] == "CLEAN" and ER._clean_proven(P) == [], (st, v["why"], ER._clean_proven(P))
        for cond, kw in _h7_spoils(P, st):
            Q = dict(P, **kw)
            got = ER._clean_proven(Q)
            assert cond in got, (st, cond, sorted(kw), got)
            names.add(cond)
        for ho, good in (("applied:4", True), ("repeat", True), ("applied:", False), ("other", False)):
            Q = dict(P)
            Q["ho"] = ho
            assert (ER._clean_proven(Q) == []) == good, (st, ho)
    sc = Sc()
    a = ER.parse_args(sc.args())
    P = ER.judge(ER.read_current(FakeWorld(sc), a), a)["proof"]
    Q = dict(P, lset=frozenset("b"), dset=frozenset("b"))
    assert ER._clean_proven(Q) == ["dropin"]                       # release: L = D = {DB} (A-39) — не CLEAN
    want = {"ident", "run", "birth", "expect", "clock", "time", "log", "chain", "proc", "gen", "entry", "flags", "ho", "tb",
            "age", "git", "code", "base_blob", "wa", "ndr", "dropin"}
    assert names == want, (sorted(want - names), sorted(names - want))
    print("  · h7: условий ворот %d, порча каждого по отдельности роняет его (три --state)" % len(want))


def test_h8_lost_code_is_unknown():
    """Потеря кода → UNKNOWN clean_gate, а не CLEAN: цепочка без e и f, у которой разбор «потерял» код chain_partial
    (подмена derive_chain), — положительные ворота держат (линза code, корень MAJOR-1)."""
    sc = Sc()
    sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, f=False, jobs=False))
    orig = ER.derive_chain

    def lost(scan, state, age):
        d = orig(scan, state, age)
        d["codes"] = set()
        return d
    try:
        ER.derive_chain = lost
        r, rc, _w = expect(sc, "UNKNOWN", "clean_gate")
        assert rc == 59 and why(r) == ["clean_gate"], r["why"]
    finally:
        ER.derive_chain = orig


def _dts(t):
    return _dt.datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d %H:%M:%S")


def _gate_scenarios():
    """Сценарии h8b: (имя, Sc, argv | None, правка констант модуля) — у каждого исходный модуль даёт НЕ CLEAN. Копии
    сценариев тестов C–J (и пробы probe_gate линзы code круга 2), плюс случаи, которых у тестов не было: d уровня WARNING
    (:983), смена рождения между двумя чтениями /proc (:1145)."""
    out = []

    def add(name, sc, argv=None, patch=None):
        out.append((name, sc, argv, patch or {}))

    def logged(lines, **kw):
        sc = Sc(**kw)
        sc.set_log(lines(sc) if callable(lines) else lines)
        return sc
    H = history
    words = words_of()
    bl, el = S().release_flags_line(words), S().release_entry(words, frozenset())[1]
    el_park = cand_lines({ACCR: "1"}, ())[2]
    own = lambda sc: L(sc.ems - 30, INFO, "клиент:\n" + _dts(sc.ems + 10) + " текст")   # noqa: E731
    # --- журнал и цепочка
    add("stamp_in_run", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + [_dts(s.ems + 1.3) + "x polling\n"]))
    add("stamp_old_date", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + ["2001-01-01 00:00:00 старое\n"]))
    add("pend", logged(lambda s: H(s.ems) + own(s) + cand_proc(s.ems + FRAC)))
    add("pend_win", logged(lambda s: H(s.ems) + own(s) + L(s.ems - 1, INFO, "x") + cand_proc(s.ems + FRAC)))
    add("pend_seg", logged(lambda s: H(s.ems) + own(s) + cand_proc(s.ems + FRAC) + L(s.ems - 20, INFO, "x")))
    add("rec_unparsed", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC)
                               + ["2026-13-45 00:00:00,123 [INFO] turbobaby: невозможная дата\n"]))
    add("back_120", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + L(s.ems + 500, INFO, "x")
                           + L(s.ems + 379, INFO, "y")))
    add("utf8", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + [b"\xff tail\n"]))
    add("lines_cap", Sc(), patch={"RUN_LINES_CAP": 5})
    add("size_cap", Sc(), patch={"LOG_CAP_BYTES": 10})
    add("win_many", logged(lambda s: H(s.ems) + L(s.ems - 1.5, INFO, ER.A_MSG) + cand_proc(s.ems + FRAC)))
    add("win_many_c", logged(lambda s: H(s.ems) + L(s.ems - 1.0, ERROR, "  " + el_park) + cand_proc(s.ems + FRAC)))
    add("premise_empty", logged([]))
    add("premise_old_a", logged(lambda s: H(s.ems, "killed") + base_proc(s.ems - 3000)[:6] + cand_proc(s.ems - 2000)))
    add("premise_shift", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC + 3600)))
    add("above", logged(lambda s: H(s.ems) + L(s.ems + FRAC + 0.2, INFO, "клиент:\n" + "".join(
        L(s.ems + FRAC + 0.5, INFO, POLL)).rstrip("\n")) + cand_proc(s.ems + FRAC + 1)))
    add("dup_d", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + L(s.ems + 80, INFO, POLL)))
    add("order", logged(lambda s: H(s.ems) + boot_part(s.ems + FRAC, bl) + L(s.ems + FRAC + 1.247, INFO, POLL)
                        + L(s.ems + FRAC + 1.3, INFO, "  " + el) + L(s.ems + FRAC + 1.403, INFO, ER.E_MSG)
                        + L(s.ems + FRAC + 1.406, INFO, ER.F_HEAD + "передачи нет")))
    add("order_win_bf", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC)[:-6] + L(s.ems + 400, INFO, ER.E_MSG)
                               + L(s.ems + 400.1, INFO, ER.F_HEAD + "передачи нет")))
    add("stop", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC) + stop_part(s.ems + 100)))
    for lv_at, nm in ((1.247, "d"), (1.403, "e"), (1.406, "f")):
        def warn(s, lv_at=lv_at):
            t = s.ems + FRAC
            lines = boot_part(t, bl) + L(t + 0.99, INFO, "  " + el)
            for at, msg in ((1.247, POLL), (1.403, ER.E_MSG), (1.406, ER.F_HEAD + "передачи нет")):
                lines += L(t + at, WARNING if at == lv_at else INFO, msg)
            return H(s.ems) + lines
        add("level_" + nm, logged(warn))
    add("flags_grammar", logged(lambda s: H(s.ems) + boot_part(s.ems + FRAC, "🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ "
                                                                         "(не задан) · CLOSE_TRUTH=ВКЛ (не задан)")
                                + L(s.ems + FRAC + 0.99, INFO, "  " + el) + tail_part(s.ems + FRAC)))
    add("entry_grammar", logged(lambda s: H(s.ems) + boot_part(s.ems + FRAC, bl)
                                + L(s.ems + FRAC + 0.99, INFO, ER.C_HEAD + "OK — иной текст") + tail_part(s.ems + FRAC)))
    add("flags_entry_keys", logged(lambda s: H(s.ems) + boot_part(s.ems + FRAC, BASE_B)
                                   + L(s.ems + FRAC + 0.99, ERROR, "  " + el_park)))
    add("flags_entry_words", logged(lambda s: H(s.ems) + boot_part(s.ems + FRAC, cand_lines({ACCR: "1"}, ())[0])
                                    + L(s.ems + FRAC + 0.99, INFO, "  " + el) + tail_part(s.ems + FRAC)))
    add("park_contra", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, {ACCR: "1"})
                              + L(s.ems + FRAC + 30, INFO, ER.E_MSG)))
    add("park_no_b", logged(lambda s: H(s.ems) + L(s.ems + FRAC + 0.912, INFO, ER.A_MSG)
                            + L(s.ems + FRAC + 0.99, ERROR, "  " + el_park)))
    add("gen_unknown", logged(lambda s: H(s.ems) + L(s.ems + FRAC + 0.912, INFO, ER.A_MSG) + tail_part(s.ems + FRAC)))
    add("young", Sc(age=299))
    add("young_nopoll", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, d=False, e=False, f=False, jobs=False),
                               age=299))
    add("partial", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, f=False, jobs=False)))
    add("park", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, {ACCR: "1"})))
    add("nopoll", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, d=False, e=False, f=False, jobs=False)))
    add("handoff", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, ho="НЕ применена: файл не прочитан")))
    add("tb", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, tb=True)))
    add("chain_ahead", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC)
                              + L(s.t2 + 3.5, INFO, "Running job x", name="apscheduler.executors.default")))
    add("gen_newer", logged(lambda s: H(s.ems) + base_proc(s.ems + FRAC)))
    out[-1][1].mtime = {n: out[-1][1].ems + 600 for n in out[-1][1].tree}
    add("gen_contra", logged(lambda s: H(s.ems) + base_proc(s.ems + 40.0)))
    add("state", logged(lambda s: H(s.ems) + cand_proc(s.ems + FRAC, {TRUTH: "0"}, ("CLOSE_TRUTH",))))
    add("fv_base", logged(lambda s: H(s.ems) + base_proc(s.ems + FRAC, bmsg="🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВЫКЛ "
                                                                           "(задан) · CONTRACT_REF_GEN=ВЫКЛ (не задан)"),
                          state="base"))
    # --- журнал не прочитан
    sc = Sc()
    sc.fail["log_open"] = (lambda i: FileNotFoundError(2, "нет", "splinter.log"))
    add("rd_log", sc)
    sc = Sc()
    sc.fstat_after = (1, 77, os.path.getsize(sc.log_path) - 10, 2000)
    add("log_rot", sc)
    # --- личность
    for name, fld, fn in (("rd_unit", "sp", lambda i: (1, b"")), ("rd_unit_s2", "sp", lambda i: (1, b"") if i >= 2 else None),
                          ("rd_wa", "wa", lambda i: (1, b"")), ("rd_wa_s0", "wa", lambda i: (1, b"") if i == 0 else None),
                          ("rd_cfg", "cfg_wa", lambda i: (1, b"")), ("rd_git", "head", lambda i: (128, b""))):
        sc = Sc()
        sc.fail[fld] = fn
        add(name, sc)
    for name, boots in (("rd_boot", [b"x\n"]), ("rd_boot0", [b"x\n", BOOT.encode() + b"\n"]),
                        ("boot_changed", [BOOT.encode() + b"\n", b"9a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d\n"])):
        sc = Sc()
        sc.boot = boots
        add(name, sc)
    for name, kw in (("wa_pid", {"pid": PID_WA + 1}), ("wa_nr", {"nr": NR_WA + 1}), ("wa_inv", {"inv": "0" * 32})):
        sc = Sc()
        sc.wa = [sc.wa[0], props(kw.get("pid", PID_WA), sc.ems_wa, sc.emsm_wa, kw.get("nr", NR_WA),
                                 inv=kw.get("inv", INV_WA))]
        add(name, sc)
    for name, k, v in (("sp_nr_s2", "NRestarts", "4"), ("sp_inv_s2", "InvocationID", "f" * 32), ("sp_pid_s1", "MainPID", "7")):
        sc = Sc()
        p = dict(sc.sp[0])
        p[k] = v
        sc.sp = [sc.sp[0]] * (1 if k == "MainPID" else 2) + [p] + ([sc.sp[0]] if k == "MainPID" else [])
        add(name, sc)
    for name, kw in (("transient", {"act": "activating", "sub": "start"}), ("inv_empty", {"inv": ""}),
                     ("ae_ems", {"ae_off_us": 2100000}), ("down", {"act": "inactive", "sub": "dead", "inv": ""})):
        sc = Sc()
        sc.sp = [props(0 if name == "down" else PID_SP, sc.ems, sc.emsm, NR_SP, **kw)]
        add(name, sc)
    sc = Sc()
    sc.fail["read:/proc/%d/stat" % PID_SP] = (lambda i: PermissionError(13, "нет прав"))
    add("rd_proc", sc)
    sc = Sc()                                          # active/running, а метка старта пуста: журнал не судится — rd_log
    sc.sp = [props(PID_SP, None, sc.emsm, NR_SP)]
    add("sp_ems_empty", sc)
    tk = int(round(Sc().emsm / 1e6 * TCK)) + 2
    cg = b"0::/system.slice/splinter.service\n"
    for name, seq in (("birth_changes", [(proc_stat(PID_SP, tk), cg), (proc_stat(PID_SP, tk + 5), cg)]),
                      ("birth", [(proc_stat(PID_SP, tk + 208), cg)]),
                      ("cgroup", [(proc_stat(PID_SP, tk), b"0::/system.slice/other.service\n")])):
        sc = Sc()
        sc.proc[PID_SP] = seq
        add(name, sc)
    sc = Sc()
    add("expect_run", sc, sc.args("--expect-run", key_with(sc.key(), pid=PID_SP + 1)))
    sc = Sc()
    add("expect_wa", sc, sc.args("--expect-wa", key_with(sc.wa_key(), nr=NR_WA + 1)))
    sc = Sc(state="base")
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, 1)]
    add("prev_run_nr", sc, sc.args("--prev-run", "%s.-.%d.%d.%d" % (BOOT[:8], 999, sc.emsm - 10 ** 7, 1)))
    sc = Sc(state="base")
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, 0)]
    add("prev_run_pid", sc, sc.args("--prev-run", "%s.-.%d.%d.%d" % (BOOT[:8], PID_SP, sc.emsm - 10 ** 7, 3)))
    # --- часы и пояс
    for name, attr, val in (("clock_rd", "adj", [None]), ("clock_unsync", "adj", [{"rc": 5, "maxerror": 16000000,
                                                                                   "status": 64}]),
                            ("zone", "zone", (3600, 3600, 0))):
        sc = Sc()
        setattr(sc, attr, val)
        add(name, sc)
    sc = Sc()
    add("clock_past", sc, sc.args(nb=int(NOW) + 5))
    sc = Sc()
    sc.t2 = sc.t0 + 5.0
    add("clock_step_pair", sc)
    sc = Sc()
    sc.emsm = int(round((MONO0 - (sc.t0 - (sc.ems + 1.6))) * 1e6))
    sc.sp = [props(PID_SP, sc.ems, sc.emsm, NR_SP)]
    sc.proc[PID_SP] = [(proc_stat(PID_SP, int(round(sc.emsm / 1e6 * TCK)) + 2), cg)]
    add("clock_step_ems", sc)
    sc = Sc()
    sc.sp = [props(PID_SP, int(sc.t2) + 30, sc.emsm, NR_SP)]
    add("start_ahead", sc)
    # --- код, git, wa-agent, конфигурация, drop-in
    for name, fn in (("head", lambda s: setattr(s, "head", "9" * 40)), ("origin", lambda s: setattr(s, "origin", "9" * 40)),
                     ("dirty", lambda s: setattr(s, "status", b" M splinter.py\n")),
                     ("blob", lambda s: s.work.__setitem__("health.py", "5" * 40)),
                     ("code_newer", lambda s: s.mtime.__setitem__("wa_agent.py", s.ems + 5)),
                     ("wa_newer", lambda s: s.mtime.__setitem__("wa_agent.py", s.ems_wa + 5)),
                     ("ndr", lambda s: setattr(s, "cfg_wa", [{"LoadState": "loaded", "NeedDaemonReload": "yes"}])),
                     ("rd_dropin", lambda s: s.dropin.__setitem__(ER.DB, (PermissionError(13, "нет"), None))),
                     ("dropin_bad", lambda s: s.dropin.__setitem__(ER.DB, ("link", DB_PIN))),
                     ("dropin_armed", lambda s: s.dropin.__setitem__(ER.DB, ("file", DB_PIN)))):
        sc = Sc()
        fn(sc)
        add(name, sc)
    sc = Sc(state="base")
    sc.tree["bot.py"] = sc.work["bot.py"] = "6" * 40
    add("base_blob", sc)
    sc = Sc()
    sc.wa = [props(0, sc.ems_wa, sc.emsm_wa, NR_WA, act="inactive", sub="dead", inv="")]
    add("wa_down", sc)
    sc = Sc()
    sc.proc[PID_WA] = [(sc.proc[PID_WA][0][0], b"0::/system.slice/other.service\n")]
    add("wa_cgroup", sc)
    sc = Sc()
    p = props(PID_WA, sc.ems_wa, sc.emsm_wa, NR_WA, inv=INV_WA)
    p["ExecMainStartTimestamp"] = "n/a"
    sc.wa = [p]
    add("wa_ems_empty", sc)
    sc = Sc(state="truth_off")
    sc.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "no", "DropInPaths": ""}]
    sc.dropin[ER.DB] = ("absent", None)
    add("state_src", sc)
    return out


_GATE_LINE = re.compile(r"^\s*(?:(?:self\.generic|codes)\.add\(|codes \|= |self\.(?:pend|cap) = True$"
                        r"|self\.cnt\[\"[a-z0-9]+\"\] \+= 1$|self\.ahead_at = self\.nl$|self\.lines_max = seg\[\"lines\"\]$)")


def _variant(src, name):
    """Модуль из текста (мутант / меченая копия) — в памяти, без файла."""
    mod = types.ModuleType(name)
    mod.__file__ = ER.__file__
    exec(compile(src, ER.__file__ + "#" + name, "exec"), mod.__dict__)  # noqa: S102 — исходник модуля, правка теста
    return mod


def _verdict_of(mod, sc, argv, patch):
    old = {k: getattr(mod, k) for k in patch}
    try:
        for k, v in patch.items():
            setattr(mod, k, v)
        out = io.StringIO()
        mod.main(sc.args() if argv is None else argv, world=FakeWorld(sc), out=out)
    finally:
        for k, v in old.items():
            setattr(mod, k, v)
    r = mod.parse_receipt(out.getvalue().rstrip("\n"))
    return (r["class"], r["why"]) if r is not None else ("NORECEIPT", out.getvalue()[:80])


def test_h8b_each_code_line_lost_never_clean():
    """MAJOR-1 линзы code круга 2 (build3): мутант «строка → pass» по КАЖДОЙ строке добавления кода (codes.add,
    generic.add, codes |=, self.pend = True, self.cap = True) и строке факта ворот (self.cnt[…] += 1, self.ahead_at,
    self.lines_max) — ни на одном сценарии, где эта строка исполняется, класс не CLEAN. Строка без такого сценария — отказ
    теста. Отбор сценариев точный: меченая копия модуля записывает исполненные строки, мутант строки L гоняется на всех
    сценариях, где L исполнилась (на прочих мутант исполняется так же, как исходный модуль)."""
    lines = _read(ER.__file__).split("\n")
    targets = [i for i, ln in enumerate(lines) if _GATE_LINE.match(ln)]
    facts = [i for i in targets if re.search(r"self\.(cnt\[|ahead_at|lines_max)", lines[i])]
    tagged = list(lines)
    for i in targets:
        ind = len(lines[i]) - len(lines[i].lstrip())
        tagged[i] = lines[i][:ind] + "_HIT.add(%d); " % (i + 1) + lines[i][ind:]
    probe = types.ModuleType("entry_read_tagged")
    probe._HIT = set()
    exec(compile("\n".join(tagged), ER.__file__ + "#tagged", "exec"), probe.__dict__)  # noqa: S102
    scen = _gate_scenarios()
    hits = {}
    for name, sc, argv, patch in scen:
        probe._HIT.clear()
        cls, w = _verdict_of(probe, sc, argv, patch)
        assert cls not in ("CLEAN", "NORECEIPT") and (cls, w) == _verdict_of(ER, sc, argv, patch), (name, cls, w)
        for n in probe._HIT:
            hits.setdefault(n, []).append(name)
    by_name = dict((x[0], x) for x in scen)
    assert len(by_name) == len(scen), "имена сценариев не уникальны"
    bare = [n + 1 for n in targets if n + 1 not in hits]
    runs, clean = 0, []
    for i in targets:
        mut = list(lines)
        mut[i] = lines[i][:len(lines[i]) - len(lines[i].lstrip())] + "pass"
        mod = _variant("\n".join(mut), "entry_read_m%d" % (i + 1))
        for name in hits.get(i + 1, ()):
            _n, sc, argv, patch = by_name[name]
            cls, w = _verdict_of(mod, sc, argv, patch)
            runs += 1
            if cls == "CLEAN":
                clean.append("%d %s: %s" % (i + 1, lines[i].strip()[:40], name))
    print("  · h8b: строк %d (добавления кода %d, фактов ворот %d), сценариев %d, прогонов мутантов %d; CLEAN у мутанта: %d"
          "%s" % (len(targets), len(targets) - len(facts), len(facts), len(scen), runs, len(clean),
                  (" — строки " + ", ".join(sorted(set(x.split()[0] for x in clean), key=int))) if clean else ""))
    assert not clean, clean
    assert not bare, "строки без сценария, где они исполняются: %s" % bare
    assert len(targets) >= 85 and len(facts) == 6, (len(targets), [lines[i].strip() for i in facts])

# =============================================================================================================================
# H6/H9. Помощник ПК (ENTRY_READ_HELPER)
# =============================================================================================================================
def test_h6_helper_contract():
    """Помощник ПК (путь в ENTRY_READ_HELPER; в репозитории его нет — иначе явный пропуск): PFX_ERE = RECEIPT_PREFIX_ERE
    дословно; рестарт юнита — ровно одна строка; настоящий grep -E -x (LC_ALL=C) принимает каждую квитанцию прогона и
    строку повторной сверки и отвергает порчи — шаблоны совместимы с POSIX ERE."""
    path = os.environ.get("ENTRY_READ_HELPER", "")
    if not path:
        print("  SKIP h6: ENTRY_READ_HELPER не задан")
        return
    text = _read(path)
    pfx = re.findall(r"(?m)^PFX_ERE='([^']*)'$", text)
    rck = re.findall(r"(?m)^RECHECK_ERE='([^']*)'$", text)
    assert pfx == [ER.RECEIPT_PREFIX_ERE], pfx
    assert len(rck) == 1 and text.count("systemctl restart") == 1, (rck, text.count("systemctl restart"))
    sc = Sc().park_for_guard()
    g = run_er(sc, _guard_argv(sc))[1].rstrip("\n")
    out = io.StringIO()
    assert ER.main(_recheck_argv(sc, g), world=FakeWorld(sc), out=out) == 0
    rline = out.getvalue().rstrip("\n")
    assert re.match(rck[0], rline), rline
    good = sorted(set(RECEIPTS + [g]))
    env = dict(os.environ, LC_ALL="C")
    for pattern, lines, want in ((pfx[0], good, len(good)), (pfx[0], [x.replace("class=", "klass=") for x in good], 0),
                                 (rck[0], [rline], 1), (rck[0], [rline.replace("ndr=no/no", "ndr=yes/no")], 0)):
        f = os.path.join(TMP, "grep_%d.txt" % len(lines))
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        p = subprocess.run(["grep", "-E", "-x", "-c", "--", pattern, f], capture_output=True, env=env)
        assert p.stdout.decode().strip() == str(want), (pattern[:40], p.stdout, p.stderr[-200:])


_KIT = []
RB7_LOG = "/root/k3_probe_20261012/rel_%s_rollback.log" % SHA_RB[:7]


def _kit():
    """Собранная копия помощника во временном каталоге (ER / ER_SHA / NB проставлены, как у сборщика) и подмена ssh на PATH:
    печатает out.txt, выходит кодом rc.txt, каждый вызов пишет строкой в calls.txt. Сервера и сети нет."""
    path = os.environ.get("ENTRY_READ_HELPER", "")
    if not path:
        return None
    if not _KIT:
        import shutil
        d = tempfile.mkdtemp(prefix="helper_", dir=TMP).replace("\\", "/")
        src = open(ER.__file__, "rb").read()
        er = d + "/entry_read_test.py"
        with open(er, "wb") as fh:
            fh.write(src)
        lines = []
        for ln in _read(path).split("\n"):
            if ln.startswith("ER="):
                ln = "ER=" + er
            elif ln.startswith("ER_SHA="):
                ln = "ER_SHA=" + hashlib.sha256(src).hexdigest()
            elif ln.startswith("NB="):
                ln = "NB=" + str(NB)
            elif ln.startswith("DB_SHA="):
                ln = "DB_SHA=" + DB_PIN
            elif ln.startswith("DU_SHA="):
                ln = "DU_SHA=" + DU_PIN
            lines.append(ln)
        hp = d + "/lifecycle_er_built.sh"
        with open(hp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        os.makedirs(d + "/bin")
        with open(d + "/bin/ssh", "w", encoding="utf-8", newline="\n") as fh:
            fh.write('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_DIR/calls.txt"\ncat > /dev/null\n'
                     'cat "$FAKE_DIR/out.txt"\nexit "$(cat "$FAKE_DIR/rc.txt")"\n')
        os.chmod(d + "/bin/ssh", 0o755)
        _KIT.append({"hp": hp, "d": d, "bin": (d + "/bin").replace("/", os.sep), "n": 0,
                     "bash": shutil.which("bash", path=os.environ.get("PATH", "")) or "bash"})
    return _KIT[0]


def _rd(kit):
    """Новый каталог квитанций с именем rd_test (как $RD сессии) — на каждый случай свой родитель."""
    kit["n"] += 1
    rd = "%s/c%d/rd_test" % (kit["d"], kit["n"])
    os.makedirs(rd)
    return rd


def _put(rd, name, text):
    p = rd + "/" + name
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return p


def _helper(kit, args, out="", rc=0):
    """→ (rc, stdout, число вызовов ssh). out/rc — ответ подменённого ssh."""
    _put(kit["d"], "out.txt", out)
    _put(kit["d"], "rc.txt", str(rc))
    calls = kit["d"] + "/calls.txt"
    n0 = len(_read(calls).splitlines()) if os.path.exists(calls) else 0
    env = dict(os.environ, RD_NAME="rd_test", FAKE_DIR=kit["d"], LC_ALL="C",
               PATH=kit["bin"] + os.pathsep + os.environ.get("PATH", ""))
    p = subprocess.run([kit["bash"], kit["hp"]] + list(args), capture_output=True, env=env, timeout=120)
    n1 = len(_read(calls).splitlines()) if os.path.exists(calls) else 0
    return p.returncode, p.stdout.decode("utf-8", "replace"), n1 - n0


def _receipt(sc, argv):
    rc, text, r, _w = run_er(sc, argv)
    assert r is not None, text
    return rc, text


def _v0_scenarios():
    """V0 по RECOVERY_PATH r4 §1: E-PARK / E-MIX / E-ARM (state release, sha V) и не-входы."""
    park = Sc()
    park.set_log(history(park.ems) + cand_proc(park.ems + FRAC, {ACCR: "1"}))
    mix = Sc()
    mix.set_log(history(mix.ems) + base_proc(mix.ems + FRAC))
    mix.mtime = {n: mix.ems + 600 for n in mix.tree}
    arm = _dropin_sc("release", "b", "b")
    dirty = Sc()
    dirty.set_log(history(dirty.ems) + cand_proc(dirty.ems + FRAC, {ACCR: "1"}))
    dirty.status = b" M bot.py\n"
    head = Sc()
    head.set_log(history(head.ems) + base_proc(head.ems + FRAC))
    head.mtime = {n: head.ems + 600 for n in head.tree}
    head.head = "9" * 40
    bad = Sc()
    bad.set_log(history(bad.ems) + base_proc(bad.ems + FRAC))
    bad.mtime = {n: bad.ems + 600 for n in bad.tree}
    bad.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "no", "DropInPaths": ER.DB}]
    bad.dropin[ER.DB] = ("file", "0" * 64)
    wadown = Sc()
    wadown.set_log(history(wadown.ems) + base_proc(wadown.ems + FRAC))
    wadown.mtime = {n: wadown.ems + 600 for n in wadown.tree}
    wadown.wa = [props(0, wadown.ems_wa, wadown.emsm_wa, NR_WA, act="inactive", sub="dead", inv="")]
    blob = Sc()                                    # общие условия годны, но why ∋ blob — вне закрытого списка E-MIX
    blob.set_log(history(blob.ems) + base_proc(blob.ems + FRAC))
    blob.mtime = {n: blob.ems + 600 for n in blob.tree}
    blob.work["health.py"] = "5" * 40
    pnew = Sc()                                    # простой, но why ∋ code_newer — вне закрытого списка E-PARK
    pnew.set_log(history(pnew.ems) + cand_proc(pnew.ems + FRAC, {ACCR: "1"}))
    pnew.mtime = {n: pnew.ems + 600 for n in pnew.tree}
    orig = Sc()                                    # origin не прочитан: git=V/?/0, why без кода — не вход (§10 п.3)
    orig.set_log(history(orig.ems) + base_proc(orig.ems + FRAC))
    orig.mtime = {n: orig.ems + 600 for n in orig.tree}
    orig.fail["origin"] = (lambda i: (128, b""))
    return {"E-PARK": park, "E-MIX": mix, "E-ARM": arm}, {"dirty": dirty, "head": head, "dropin_bad": bad,
                                                         "wa_down": wadown, "blob": blob, "park_newer": pnew,
                                                         "origin_unread": orig, "young": Sc(age=100), "clean": Sc()}


def _wa_done(pid):
    return ("wa-agent ЧИСТЫЙ (код %s, PID %s устоял 35 с, CASESTATE вкл, M4 выкл, CONTRACT_REF выкл, 8 файлов = блобы HEAD, "
            "wa_offer_tool.py handover_facts.py нет; строк [ERROR] wa-agent в снимке и после решения 0)" % (SHA_RB, pid))


def _stp(code=10, rb=SHA_RB):
    """Строка r3d :416 (шаг 4 отката, предпроверка не «0»)."""
    return ("STOP: СТОП ДО РЕСТАРТА: незавершённые карточки не исключены (код %s) — этим заходом выполнен только git fetch -q "
            "origin main (FETCH_HEAD; origin/main = %s прочитан), рестарта не было; не прочитано — UNKNOWN: есть ли в памяти "
            "идущего процесса splinter незавершённые карточки и в каком он состоянии (не здоровье и не чистота); повтор и "
            "следующий шаг по общему слову владельца не вызываются — сначала разбор только чтением" % (code, rb))


def _journal(form, pid=PID_WA2, **kw):
    """Хвост журнала отката r10 (:136/:660/:718/:721/:722, sha256 67ab7f7b…) с частью шага 4 r3d (:380/:416/:462/:573,
    c792804b…) и 5db211d1 (:45/:50) — строки шаблонов этих байтов, подставленные значениями теста (сверяет h11 при
    ENTRY_READ_PKG; build3, M1 линзы спецификации круга 2: до build3 фикстура держала формы r8/r3c)."""
    s4 = ("splinter: шаг 4 отката — bash /root/k3_probe_20261012/%s %s (пин %s…); его строки ниже, итог — строкой "
          "ROLLBACK_END" % (kw.get("r3d", "srv_splinter_restart5_r3d.sh"), SHA_RB, kw.get("pin", "c792804b90d5")))
    env = ("splinter: Environment юнита (systemd 255; белый список — присваиваний/слово значения, прочие имена и значения "
           "не печатаются): INTAKE_CONFIRM_STRICT 0/- · CONTRACT_REF_GEN 0/- · drop-in: путей 0, свой R0 0, снятия R0 0")
    head = ["ROLLBACK предусловия: live HEAD = origin main = FROM, правок 0", "РЕСТАРТ wa-agent ЧИСТЫЙ: код отката %s" % SHA_RB]
    if form == "i":
        part = [env, "ПРЕДПРОВЕРКА: жизнь процесса в журнале — байты 1..2 (старт 2026-10-21 06:00:00 UTC); сообщений 0"]
        part += [] if kw.get("no_win") else ["окно рестарта: замер журнала и предпроверка → systemctl restart в 08:01:02 UTC"]
        part += [] if kw.get("no_rst") else [
            "РЕСТАРТ SPLINTER ЧИСТЫЙ: код %s в процессе; процесс сам сказал INTAKE_CONFIRM_STRICT=ВКЛ, CONTRACT_REF_GEN=ВЫКЛ; "
            "незавершённых карточек до рестарта не было (журнал с байта 1), окно рестарта чистое (оба — и контролем одним "
            "проходом); передача без карточек, восстановление прошло; здоровье доказано чтениями со статусом и одним "
            "проходом по новой части журнала; решение и показ — по одному снимку (байты 2..3), после решения дописано 0 байт "
            "без признаков ошибки и второго старта" % SHA_RB]
        end = ("ROLLBACK_END 0 ОТКАТ ЧИСТЫЙ: %s; splinter ЧИСТЫЙ: шаг 4 (%s) вернул 0 на коде отката %s (дерево 947953e) — "
               "его итоговая строка выше" % (_wa_done(pid), kw.get("tail", "srv_splinter_restart5_r3d.sh"), SHA_RB))
    else:
        part = [env, kw.get("pre", "ПРЕДПРОВЕРКА: строки старта в журнале до замера нет — память процесса не доказана"),
                kw.get("stp", _stp())]
        end = ("ROLLBACK_END 39 STOP: %s; РЕСТАРТ splinter НЕ СДЕЛАН: шаг 4 отката остановился до рестарта (код 6, его строка "
               "выше; при кодах 6 и 8 он уже выполнил git fetch -q origin main — FETCH_HEAD и ссылка origin/main); известно "
               "этим заходом: код отката %s выложен (live HEAD = origin main = %s), wa-agent — как в начале строки, splinter не "
               "рестартован; не прочитано — UNKNOWN: код и состояние процесса splinter (смешанное состояние MIXED не "
               "исключено; не здоровье и не чистота); режим splinter, повтор и следующий шаг по общему слову владельца не "
               "вызываются — сначала разбор только чтением" % (_wa_done(pid), SHA_RB, SHA_RB))
    lines = head + ([s4] if kw.get("s4", True) else []) + part + kw.get("extra", []) + [kw.get("end", end)]
    return "\n".join(lines) + "\n"


def _v2a_sc():
    """Простой K0 после R1 формы (ii): код RB на диске, wa-agent рестартован R1 (новый PID из WA_DONE)."""
    sc = Sc().park_for_guard()
    sc.wa = [props(PID_WA2, sc.ems_wa, sc.emsm_wa, NR_WA, inv=INV_WA)]
    sc.proc[PID_WA2] = [(proc_stat(PID_WA2, int(round(sc.emsm_wa / 1e6 * TCK)) + 3), b"0::/system.slice/wa-agent.service\n")]
    return sc


def _kwa1(sc):
    return "%s.%s.%d.%d.%d" % (BOOT[:8], INV_WA, PID_WA2, sc.emsm_wa, NR_WA)


def _v3_sc(sc2):
    """Новый процесс на RB после ux / формы (i): pid ≠ K0, NRestarts 0, wa-agent — тот же, что в V2a."""
    sc = Sc(state="base", age=400)
    pid = PID_SP + 11
    sc.sp = [props(pid, sc.ems, sc.emsm, 0)]
    sc.proc = {pid: [(proc_stat(pid, int(round(sc.emsm / 1e6 * TCK)) + 2), b"0::/system.slice/splinter.service\n")],
               PID_WA2: [(proc_stat(PID_WA2, int(round(sc2.emsm_wa / 1e6 * TCK)) + 3),
                          b"0::/system.slice/wa-agent.service\n")]}
    sc.wa = [props(PID_WA2, sc2.ems_wa, sc2.emsm_wa, NR_WA, inv=INV_WA)]
    sc.mtime = {n: sc2.ems + 1200 for n in sc.tree}
    return sc


def test_h9_helper_v_path_table():
    """Помощник ПК, путь V машиной (M3 линзы атаки, M1/M2 линзы спецификации): er ENTRY — закрытые списки §1; vr — точные
    формы (i)/(ii) RECOVERY_PATH r5 §3 на байтах отката r10 / шага 4 r3d (build3; формы r8/r3c — STOP) и допустимость по
    входу §0.3 (иное — STOP, нет итога — PENDING rc 2); er --vr (V2a/V3) — KWA1 ≠ KWA0 и pid KWA1 = PID из WA_DONE, а
    V2a/V3 без --vr — отказ до ssh (build3); ux — только после vr (ii) при E-PARK, один на каталог RD; отказ 61/62/63 — rc
    тем же кодом и STAGE_END ux rc=<код>. ssh подменён (печатает заданный ответ, шаблон ux не исполняет — это h10), сервера
    и сети нет."""
    kit = _kit()
    if kit is None:
        print("  SKIP h9: ENTRY_READ_HELPER не задан")
        return
    ok_v0, bad_v0 = _v0_scenarios()
    v0_files = {}
    rd = _rd(kit)
    for name, sc in sorted(ok_v0.items()):
        rc, text = _receipt(sc, sc.args(label="rd_test/V0"))
        hrc, out, nc = _helper(kit, ["er", "V0", "ENTRY", "release", SHA_V], text, rc)
        assert hrc == 0 and nc == 1 and ("ER_ENTRY %s k0=%s kwa0=" % (name, sc.key())) in out, (name, out)
        v0_files[name] = _put(rd, "er_V0_20261021-08000%d.out.txt" % len(v0_files), out)
    for name, sc in sorted(bad_v0.items()):
        rc, text = _receipt(sc, sc.args(label="rd_test/V0"))
        hrc, out, _nc = _helper(kit, ["er", "V0", "ENTRY", "release", SHA_V], text, rc)
        assert hrc == 1 and ("STOP er: не вход пути V" in out or "STOP er: класс" in out
                             or "не из ожидаемых" in out), (name, out)
        assert "ER_ENTRY" not in out and out.rstrip().endswith("STAGE_END er rc=1"), (name, out)
    rc, text = _receipt(ok_v0["E-PARK"], ok_v0["E-PARK"].args(label="rd_test/V0"))
    hrc, out, _nc = _helper(kit, ["er", "V0", "PARKED,MIXED,ARMED", "release", SHA_V], text, rc)
    plain_v0 = _put(rd, "er_V0_20261021-080009.out.txt", out)            # снят не стадией ENTRY — для vr не годен
    # --- vr: таблица исходов §0.3
    def vr(v0, journal, rc=0, path=RB7_LOG):
        return _helper(kit, ["vr", "V1", SHA_RB, v0, path], journal, rc)
    hrc, out, _nc = vr(v0_files["E-PARK"], _journal("ii"))
    assert hrc == 0 and ("VR_RESULT ii entry=E-PARK k0=%s kwa0=%s wa_pid=%d rb=%s\n" % (
        ok_v0["E-PARK"].key(), ok_v0["E-PARK"].wa_key(), PID_WA2, SHA_RB)) in out, out
    vr_ii = _put(rd, "vr_V1_20261021-081000.out.txt", out)
    for v0 in ("E-MIX", "E-ARM"):
        hrc, out, _nc = vr(v0_files[v0], _journal("i"))
        assert hrc == 0 and ("VR_RESULT i entry=%s " % v0) in out and " tr0=08:01:02\n" in out, out
    vr_i = _put(rd, "vr_V1_20261021-081001.out.txt", out)
    stops = (
        (v0_files["E-MIX"], _journal("ii"), "противоречие"),
        (v0_files["E-ARM"], _journal("ii"), "противоречие"),
        (v0_files["E-PARK"], _journal("i"), "противоречие"),
        (v0_files["E-PARK"], _journal("ii", pre="ПРЕДПРОВЕРКА: жизнь процесса в журнале — байты 1..2", stp=_stp(11)), "(б)"),
        (v0_files["E-PARK"], _journal("ii", stp="STOP: СТОП ДО РЕСТАРТА: чтение Environment юнита не удалось или "
                                                "представление не доказуемо (x) — ключи юнита не доказаны; этим заходом "
                                                "выполнен только git fetch -q origin main"), "(в)"),
        (v0_files["E-PARK"], _journal("ii", stp=_stp(11)), "(в)"),
        (v0_files["E-PARK"], _journal("ii", stp=_stp(10, "1" * 40)), "(в)"),
        (v0_files["E-PARK"], _journal("ii", stp="СТОП ДО РЕСТАРТА: незавершённые карточки не исключены (код 10) — рестарт "
                                                "не делаю, решение владельца"), "(в)"),          # форма r3c — не r3d
        (v0_files["E-PARK"], _journal("ii", extra=["шаг 4: повтор — STOP: СТОП ДО РЕСТАРТА: незавершённые карточки не "
                                                   "исключены (код 10) — дубль"]), "(в)"),        # вторая такая строка
        (v0_files["E-PARK"], _journal("ii", extra=["окно рестарта: замер журнала и предпроверка → systemctl restart в "
                                                   "08:01:02 UTC"]), "(г)"),
        (v0_files["E-PARK"], _journal("ii", extra=["ПРЕДПРОВЕРКА: строки старта в журнале до замера нет — память процесса "
                                                   "не доказана"]), "(б)"),
        (v0_files["E-PARK"], _journal("ii", pid="?"), "WA_DONE"),
        (v0_files["E-PARK"], _journal("ii", s4=False), "шага 4"),
        (v0_files["E-PARK"], _journal("ii", end="ROLLBACK_END 40 STOP: ТРЕВОГА splinter: процесс не устоял"), "не форма"),
        (v0_files["E-PARK"], _journal("ii", end="ROLLBACK_END 39 STOP: %s; РЕСТАРТ splinter НЕ СДЕЛАН: чтение sha256 x не "
                                                "удалось (rc 1); известно этим заходом" % _wa_done(PID_WA2)), "не формы (ii)"),
        (v0_files["E-PARK"], _journal("ii", end="ROLLBACK_END 39 STOP: %s; РЕСТАРТ splinter НЕ СДЕЛАН: шаг 4 отката "
                                                "остановился до рестарта (код 8, его строка выше; при кодах 6 и 8"
                                                % _wa_done(PID_WA2)), "не формы (ii)"),
        (v0_files["E-PARK"], _journal("ii", end="ROLLBACK_END 39 %s; РЕСТАРТ splinter НЕ СДЕЛАН: шаг 4 остановился до "
                                                "рестарта (код 6, его строка выше) — STOP: режим splinter и любой повтор по "
                                                "общему слову владельца не вызываются" % _wa_done(PID_WA2)), "не форма"),
        (v0_files["E-PARK"], _journal("ii").replace("(код " + SHA_RB, "(код " + "1" * 40), "не форма"),
        (v0_files["E-PARK"], _journal("ii", r3d="srv_splinter_restart5_r7.sh"), "не r3d"),
        (v0_files["E-PARK"], _journal("ii", r3d="srv_splinter_restart5_r3c.sh"), "не r3d"),        # шаг 4 r3c — не r3d
        (v0_files["E-PARK"], _journal("ii", pin="25b724bff140"), "не r3d"),                          # пин r3c
        (v0_files["E-MIX"], _journal("i", end="ROLLBACK_END 0 ОТКАТ ЧИСТЫЙ: %s; splinter ЧИСТЫЙ: шаг 4 "
                                              "(srv_splinter_restart5_r3d.sh) вернул 0 на коде отката %s (дерево 947953e)"
                                              % (_wa_done(PID_WA2), SHA_RB)), "хвост"),
        (v0_files["E-MIX"], _journal("i", tail="srv_splinter_restart5_r3c.sh"), "хвост"),          # хвост формы r8
        (v0_files["E-MIX"], _journal("i", no_win=True), "окно рестарта"),
        (v0_files["E-MIX"], _journal("i", no_rst=True), "РЕСТАРТ SPLINTER ЧИСТЫЙ"),
        (plain_v0, _journal("ii"), "ER_ENTRY"),
        (_put(rd, "er_V0_20261021-080010.out.txt", _read(v0_files["E-PARK"]).replace("ER_ENTRY E-PARK", "ER_ENTRY E-MIX")),
         _journal("ii"), "ER_ENTRY не совпала"),
    )
    for v0, journal, word in stops:
        hrc, out, _nc = vr(v0, journal)
        assert hrc == 1 and "STOP vr:" in out and word in out and "VR_RESULT" not in out, (word, out)
    hrc, out, _nc = vr(v0_files["E-PARK"], "ROLLBACK предусловия: …\nsplinter: шаг 4 отката — bash x\n")
    assert hrc == 2 and "VR_RESULT PENDING" in out and out.rstrip().endswith("STAGE_END vr rc=2"), out
    hrc, out, _nc = vr(v0_files["E-PARK"], "", rc=255)
    assert hrc == 1 and "НЕИЗВЕСТЕН" in out, out
    hrc, out, nc = vr(v0_files["E-PARK"], _journal("ii"), path="/root/../etc/rel_%s_rollback.log" % SHA_RB[:7])
    assert hrc == 1 and nc == 0, out
    od = "%s/c_other/rd_other" % kit["d"]                              # файл V0 не из каталога этой сессии
    os.makedirs(od)
    hrc, out, nc = vr(_put(od, "er_V0_20261021-080000.out.txt", _read(v0_files["E-PARK"])), _journal("ii"))
    assert hrc == 1 and nc == 0 and "этой сессии" in out, out
    # --- er --vr: V2a и V3
    sc2 = _v2a_sc()
    k0, kwa1 = sc2.key(), _kwa1(sc2)
    assert k0 == ok_v0["E-PARK"].key()
    rc, v2a = _receipt(sc2, sc2.args("--expect-run", k0, label="rd_test/V2a"))
    hrc, out, _nc = _helper(kit, ["er", "V2a", "PARKED", "base", SHA_RB, "--expect-run", k0, "--vr", vr_ii], v2a, rc)
    assert hrc == 0 and ("ER_VR ii kwa1=%s\n" % kwa1) in out, out
    for args, word in ((["--expect-run", k0, "--vr", vr_i], "V2a только после формы (ii)"),
                       (["--expect-run", key_with(k0, pid=PID_SP + 1), "--vr", vr_ii], "V2a только"),):
        hrc, out, nc = _helper(kit, ["er", "V2a", "PARKED", "base", SHA_RB] + args, v2a, rc)
        assert hrc == 1 and nc == 0 and word in out, out
    sc_old = Sc().park_for_guard()                                     # wa-agent сменился, но не тем PID, что в WA_DONE
    rc_o, v2a_old = _receipt(sc_old, sc_old.args("--expect-run", k0, label="rd_test/V2a"))
    hrc, out, _nc = _helper(kit, ["er", "V2a", "PARKED", "base", SHA_RB, "--expect-run", k0, "--vr", vr_ii], v2a_old, rc_o)
    assert hrc == 1 and "KWA1" in out and "ER_VR" not in out, out
    rd2 = _rd(kit)
    vr_pid = _put(rd2, "vr_V1_20261021-081000.out.txt", _read(vr_ii).replace("wa_pid=%d" % PID_WA2, "wa_pid=%d" % (PID_WA2 + 1)))
    hrc, out, _nc = _helper(kit, ["er", "V2a", "PARKED", "base", SHA_RB, "--expect-run", k0, "--vr", vr_pid], v2a, rc)
    assert hrc == 1 and "WA_DONE" in out, out
    sc3 = _v3_sc(sc2)
    rc3, v3 = _receipt(sc3, sc3.args("--prev-run", k0, "--expect-wa", kwa1, label="rd_test/V3"))
    assert rc3 == 0, v3
    hrc, out, nc = _helper(kit, ["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0, "--expect-wa", kwa1, "--vr", vr_ii],
                           v3, rc3)
    assert hrc == 0 and ("ER_VR ii kwa1=%s\n" % kwa1) in out, out
    assert ("--expect-wa " + kwa1) in _read(kit["d"] + "/calls.txt").splitlines()[-1]
    hrc, out, nc = _helper(kit, ["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0, "--vr", vr_ii], v3, rc3)
    assert hrc == 1 and nc == 0 and "--expect-wa" in out, out
    hrc, out, _nc = _helper(kit, ["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0, "--vr", vr_i], v3, rc3)
    assert hrc == 0 and ("ER_VR i kwa1=%s\n" % kwa1) in out, out
    # build3 (M2 линзы атаки круга 2): ключи пути V без --vr — отказ до ssh; KWA1 ↔ WA_DONE сверяется всегда
    for args, txt, trc in ((["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0], v3, rc3),
                           (["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0, "--expect-wa", kwa1], v3, rc3),
                           (["er", "V2a", "PARKED", "base", SHA_RB, "--expect-run", k0], v2a, rc),
                           (["er", "S1", "ANY", "base", SHA_RB, "--expect-wa", kwa1], v3, rc3)):
        hrc, out, nc = _helper(kit, args, txt, trc)
        assert hrc == 1 and nc == 0 and "только V2a/V3 с --vr" in out and "ER_RESULT" not in out, (args, out)
    sc3w = _v3_sc(sc2)                                 # после R1 wa-agent МОЛЧА сменился ещё раз: PID ≠ PID из WA_DONE
    ew, emw = sc2.ems_wa + 60, sc2.emsm_wa + 60 * 1000000
    sc3w.wa = [props(PID_WA2 + 40, ew, emw, NR_WA, inv=INV_WA)]
    sc3w.proc[PID_WA2 + 40] = [(proc_stat(PID_WA2 + 40, int(round(emw / 1e6 * TCK)) + 3),
                                b"0::/system.slice/wa-agent.service\n")]
    rcw, v3w = _receipt(sc3w, sc3w.args("--prev-run", k0, label="rd_test/V3"))
    assert rcw == 0, v3w                               # читатель без --expect-wa: CLEAN — ловит только сверка помощника
    hrc, out, nc = _helper(kit, ["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0, "--vr", vr_i], v3w, rcw)
    assert hrc == 1 and nc == 1 and "KWA1 из квитанции" in out and "ER_VR" not in out, out
    hrc, out, nc = _helper(kit, ["er", "V3", "CLEAN", "base", SHA_RB, "--prev-run", k0], v3w, rcw)
    assert hrc == 1 and nc == 0 and "--vr" in out and "STAGE_END er rc=0" not in out, out   # build2: rc=0
    # --- ux: только после vr (ii) при E-PARK, один на каталог
    g = run_er(sc2, sc2.args("--expect-run", k0, "--expect-wa", kwa1, "--guard", "unpark", label="rd_test/V2"))[1]
    rck = "ENTRY_RECHECK r1 PASS label=rd_test/V2 run=%s wa=%s head=%s dropin=--/-- ndr=no/no\n" % (k0, kwa1, SHA_RB)
    good = g + rck + "UNPARK_END restart_rc=0 pid_before=%d at=1792500000\n" % PID_SP

    def ux(vr_text, kw=kwa1, k=k0, n_ux=1, out=good, rc=0):
        rdx = _rd(kit)
        vf = _put(rdx, "vr_V1_20261021-081000.out.txt", vr_text)
        for i in range(n_ux):
            _put(rdx, "ux_V2_20261021-08200%d.out.txt" % i, "")
        return _helper(kit, ["ux", "V2", SHA_RB, k, kw, vf], out, rc)
    hrc, out, nc = ux(_read(vr_ii))
    assert hrc == 0 and nc == 1 and "UX_RESULT OK at=1792500000" in out and out.rstrip().endswith("STAGE_END ux rc=0"), out
    for args, word in (({"vr_text": _read(vr_i)}, "формы (ii)"), ({"vr_text": _read(vr_ii), "kw": key_with(kwa1, pid=7)},
                       "WA_DONE"), ({"vr_text": _read(vr_ii), "kw": ok_v0["E-PARK"].wa_key()}, "KWA1 = KWA0"),
                       ({"vr_text": _read(vr_ii), "k": key_with(k0, pid=PID_SP + 1)}, "K0 или RB"),
                       ({"vr_text": _read(vr_ii), "n_ux": 2}, "второго ux нет"),
                       ({"vr_text": _read(vr_ii), "n_ux": 0}, "второго ux нет")):
        hrc, out, nc = ux(**args)
        assert hrc == 1 and nc == 0 and word in out and "STOP ux:" in out and "UX_RESULT" not in out, (word, out)
    hrc, out, nc = ux(_read(vr_ii), out=g + "UNPARK_END refused recheck=dropin\n", rc=63)
    assert hrc == 63 and nc == 1 and "UX_RESULT REFUSED rc=63" in out and out.rstrip().endswith("STAGE_END ux rc=63"), out
    print("  · h9: стадии er ENTRY / vr / er --vr / ux на подменённом ssh — %d каталогов квитанций" % kit["n"])


# --- H10. Удалённый шаблон ux ИСПОЛНЯЕТСЯ (build3, MJ1 линзы безопасности круга 2: h9 подменяет ssh заготовкой и шаблон
# не исполняет). Заглушки: python3 (режим по аргументам --guard / --recheck; пишет поток stdin и аргументы, печатает
# заданный ответ, выходит заданным кодом) и systemctl (show → заданный MainPID, restart → журнал вызовов).
_UX_PY = ('#!/bin/sh\nmode=normal\nfor a in "$@"; do case "$a" in --guard) mode=guard ;; --recheck) mode=recheck ;; esac; '
          'done\nn=$(cat "$FAKE/n_$mode" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$FAKE/n_$mode"\n'
          'cat > "$FAKE/stdin_$mode.$n"\nprintf \'%s\\n\' "$*" > "$FAKE/args_$mode.$n"\ncat "$FAKE/out_$mode"\n'
          'exit "$(cat "$FAKE/rc_$mode")"\n')
_UX_SYSTEMCTL = ('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$FAKE/systemctl_calls"\ncase "$1" in\n'
                 '  show) cat "$FAKE/mainpid"; exit "$(cat "$FAKE/rc_show")" ;;\n'
                 '  restart) exit "$(cat "$FAKE/rc_restart")" ;;\nesac\nexit 99\n')
# четыре проверки шаблона перед единственным рестартом — мутант снимает одну (их же гоняет test_zz_helper_mutants)
UX_TMPL_MUTANTS = (
    ('[ "$gr" = 0 ] || { echo "UNPARK_END refused guard_rc=$gr"; exit 61; }',
     'true || { echo "UNPARK_END refused guard_rc=$gr"; exit 61; }', "шаблон ux: снят отказ по rc охраны"),
    ('[ "$cr" = 0 ] || { [ "$cr" = 63 ]', 'true || { [ "$cr" = 63 ]', "шаблон ux: снят отказ по rc --recheck"),
    ('{ [ "$pr" = 0 ] && [ "$p" = "@PID@" ]; } ||', 'true ||', "шаблон ux: снята сверка MainPID"),
    ('[ "$(printf "%s\\n" "$P" | sha256sum | cut -c1-64)" = "@ER_SHA@" ] ||', 'true ||', "шаблон ux: снята сверка sha потока"),
)


def _ux_grid(helper_text, tag):
    """Шаблон ux из текста помощника → исполнение в bash (stdin — поток программы) с заглушками python3/systemctl по
    сетке исходов → список расхождений с ожидаемым (пусто — шаблон держит все проверки)."""
    import shutil
    m = re.findall(r"(?m)^  tmpl='(.*)'$", helper_text)
    assert len(m) == 1, m
    src = open(ER.__file__, "rb").read()
    er_sha = hashlib.sha256(src).hexdigest()
    sc2 = _v2a_sc()
    k0, kwa1, label, pid = sc2.key(), _kwa1(sc2), "rd_test/V2", str(PID_SP)
    g = run_er(sc2, sc2.args("--expect-run", k0, "--expect-wa", kwa1, "--guard", "unpark", label=label))[1]
    rck = "ENTRY_RECHECK r1 PASS label=%s run=%s wa=%s head=%s dropin=--/-- ndr=no/no\n" % (label, k0, kwa1, SHA_RB)

    def build(sha=er_sha):
        c = m[0]
        for a, b in (("@ER_SHA@", sha), ("@RB@", SHA_RB), ("@LABEL@", label), ("@NB@", str(NB)), ("@DB@", DB_PIN),
                     ("@DU@", DU_PIN), ("@K0@", k0), ("@KWA@", kwa1), ("@PID@", pid)):
            c = c.replace(a, b)
        assert not re.search(r"@[A-Z]+@", c), c
        return c
    d = tempfile.mkdtemp(prefix="ux_%s_" % tag, dir=TMP).replace("\\", "/")
    os.makedirs(d + "/bin")
    for fn, body in (("python3", _UX_PY), ("systemctl", _UX_SYSTEMCTL)):
        with open(d + "/bin/" + fn, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        os.chmod(d + "/bin/" + fn, 0o755)
    bash = shutil.which("bash", path=os.environ.get("PATH", "")) or "bash"
    bad = []

    def rd(s, name, default=""):
        p = s + "/" + name
        return _read(p) if os.path.exists(p) else default

    def go(cmd, **kw):
        s = tempfile.mkdtemp(prefix="st_", dir=d).replace("\\", "/")
        vals = dict(guard_out=g, guard_rc=0, re_out=rck, re_rc=0, mainpid=pid, show_rc=0, restart_rc=0)
        vals.update(kw)
        for k, v in (("out_guard", vals["guard_out"]), ("rc_guard", vals["guard_rc"]), ("out_recheck", vals["re_out"]),
                     ("rc_recheck", vals["re_rc"]), ("mainpid", vals["mainpid"] + "\n"), ("rc_show", vals["show_rc"]),
                     ("rc_restart", vals["restart_rc"]), ("out_normal", ""), ("rc_normal", 1)):
            with open(s + "/" + k, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(str(v))
        env = dict(os.environ, FAKE=s, LC_ALL="C", PATH=(d + "/bin").replace("/", os.sep) + os.pathsep + os.environ["PATH"])
        p = subprocess.run([bash, "-c", cmd], input=src, capture_output=True, env=env, timeout=60)
        calls = rd(s, "systemctl_calls").splitlines()
        return (p.returncode, p.stdout.decode("utf-8", "replace").replace("\r\n", "\n"), calls,
                int(rd(s, "n_guard", "0").strip()), int(rd(s, "n_recheck", "0").strip()), s)
    rc, out, calls, ng, nr, s = go(build())
    lines = out.rstrip("\n").split("\n")
    if not (rc == 0 and len(lines) == 3 and calls == ["show splinter --property=MainPID --value", "restart splinter"]
            and re.match(r"^UNPARK_END restart_rc=0 pid_before=%s at=[0-9]+$" % pid, lines[-1]) and ng == 1 and nr == 1):
        bad.append("успех: rc %s, строк %d, вызовы %s" % (rc, len(lines), calls))
    else:
        sg, sr = open(s + "/stdin_guard.1", "rb").read(), open(s + "/stdin_recheck.1", "rb").read()
        if not (sg == sr == src):
            bad.append("поток программы двум python не равен файлу (%d/%d/%d байт)" % (len(sg), len(sr), len(src)))
        ar, ag = rd(s, "args_recheck.1").rstrip("\n"), rd(s, "args_guard.1")
        if not (ar.endswith("--against " + g.rstrip("\n")) and "--guard unpark" in ag and ("--expect-run " + k0) in ag
                and ("--expect-wa " + kwa1) in ag and ("--expect-wa " + kwa1) in ar):
            bad.append("аргументы guard/recheck не те")
    cases = (       # (имя, команда, ответы заглушек, код, слово, вызовов guard, вызовов recheck, рестартов)
        ("sha потока", build("0" * 64), {}, 61, "er_sha", 0, 0, 0),
        ("guard 58", None, {"guard_rc": 58}, 61, "guard_rc=58", 1, 0, 0),
        ("guard 59", None, {"guard_rc": 59}, 61, "guard_rc=59", 1, 0, 0),
        ("recheck 63", None, {"re_out": "UNPARK_END refused recheck=dropin\n", "re_rc": 63}, 63, "recheck=dropin", 1, 1, 0),
        ("recheck 1", None, {"re_out": "", "re_rc": 1}, 63, "recheck=rc1", 1, 1, 0),
        ("MainPID ≠", None, {"mainpid": "77"}, 62, "mainpid=77", 1, 1, 0),
        ("show rc 1", None, {"show_rc": 1}, 62, "mainpid=", 1, 1, 0),
        ("restart rc 1", None, {"restart_rc": 1}, 1, "restart_rc=1", 1, 1, 1),
        # факт (NOTE линзы безопасности круга 2): пустой вывод --recheck при rc 0 шаблон не отличает — рестарт идёт,
        # помощник после него даёт STOP ux (строк 2), второго ux нет
        ("recheck rc 0 без строки", None, {"re_out": "", "re_rc": 0}, 0, "restart_rc=0", 1, 1, 1),
    )
    for name, cmd, kw, want_rc, word, n_g, n_r, n_rst in cases:
        rc, out, calls, ng, nr, _s = go(cmd or build(), **kw)
        rst = len([c for c in calls if c.startswith("restart")])
        if not (rc == want_rc and word in out and ng == n_g and nr == n_r and rst == n_rst):
            bad.append("%s: rc %s, слово %s, guard %d, recheck %d, рестартов %d" % (name, rc, word in out, ng, nr, rst))
            if tag != "real":
                break                                    # мутант уже пойман — остальное не нужно
    return bad


def test_h10_ux_template_exec():
    """Удалённый шаблон ux (дословно из помощника ENTRY_READ_HELPER) исполняется в bash под подменённым окружением
    (python3/systemctl — заглушки на PATH, stdin — поток программы): рестарт ровно один и только после sha потока, --guard
    rc 0, --recheck rc 0 и MainPID = pid K0; во всех прочих исходах рестарта нет и код 61/62/63. Четыре мутанта шаблона
    (rc охраны, rc --recheck, MainPID, sha потока) этим тестом пойманы (build3, MJ1 линзы безопасности круга 2)."""
    path = os.environ.get("ENTRY_READ_HELPER", "")
    if not path:
        print("  SKIP h10: ENTRY_READ_HELPER не задан")
        return
    text = _read(path)
    bad = _ux_grid(text, "real")
    assert not bad, bad
    caught = []
    for i, (old, new, words) in enumerate(UX_TMPL_MUTANTS):
        assert text.count(old) == 1, (words, text.count(old))
        mb = _ux_grid(text.replace(old, new), "m%d" % i)
        assert mb, "мутант не пойман: " + words
        caught.append("%s → %s" % (words, mb[0].split(":")[0]))
    print("  · h10: шаблон ux исполнен (успех + 9 исходов); мутанты шаблона пойманы %d из %d: %s"
          % (len(caught), len(UX_TMPL_MUTANTS), "; ".join(caught)))


# --- H11. Фикстуры журнала отката h9 против байтов пакета (build3, M1 линзы спецификации круга 2)
PKG_R10_SHA = "67ab7f7bffc14cf9b33a91cc46f1b74e5cff93a1692e45ee79d654ca9487d3a6"
PKG_R3D_SHA = "c792804b90d5a7dda2209e72c09e037ad1d0903d53162e14bdf3b197bc8825c9"


def _sh_render(tmpl, vals):
    """Строка bash в двойных кавычках → текст: $ИМЯ и ${ИМЯ:0:12} из vals (имя не из vals — KeyError, тест падает)."""
    def rep(m):
        return vals[m.group(1)][:12] if m.group(1) else vals[m.group(2)]
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*):0:12\}|\$([A-Za-z_][A-Za-z0-9_]*)", rep, tmpl)


def test_h11_journal_fixtures_vs_package_bytes():
    """Фикстуры _journal h9 = строки, которые напечатают байты пакета (ENTRY_READ_PKG — каталог с откатом r10 и шагом 4
    r3d, сверка по sha256): шаблоны echo/fin откатa :136, :660, :718, :721, :722 и r3d :380, :416, :462, :573 подставлены
    значениями теста и дословно равны строкам фикстуры. Смена байтов пакета (иной sha) — отказ теста: формы помощника
    сверяются заново."""
    pkg = os.environ.get("ENTRY_READ_PKG", "")
    if not pkg:
        print("  SKIP h11: ENTRY_READ_PKG не задан")
        return
    raw = {}
    for name, pin in (("srv_reld_rollback_bf85964_r10.sh", PKG_R10_SHA), ("srv_splinter_restart5_r3d.sh", PKG_R3D_SHA)):
        with open(os.path.join(pkg, name), "rb") as fh:
            b = fh.read()
        assert hashlib.sha256(b).hexdigest() == pin, (name, hashlib.sha256(b).hexdigest())
        raw[name] = b.decode("utf-8")
    t10, t3 = raw["srv_reld_rollback_bf85964_r10.sh"], raw["srv_splinter_restart5_r3d.sh"]

    def one(text, rx):
        got = re.findall(rx, text, re.M)
        assert len(got) == 1, (rx[:60], len(got))
        return got[0]
    one(t10, r'^(fin\(\) \{ echo "ROLLBACK_END \$1 \$2"; exit "\$1"; \})$')
    vals = {"SHA": SHA_RB, "pid0": str(PID_WA2), "src": "6", "prc": "10", "tr0": "08:01:02", "SDV": "255",
            "EW": "INTAKE_CONFIRM_STRICT 0/- · CONTRACT_REF_GEN 0/-", "DPC_N": "0", "DPC_OWN": "0", "DPC_UND": "0",
            "SC_OFF": "1", "sz": "2", "sz2": "3", "an": "0",
            "WA_GONE": one(t10, r"^WA_GONE='([^']*)'"),
            "erw": one(t10, r'then erw="(строк \[ERROR\] wa-agent в снимке и после решения 0)"$'),
            "SP_R": one(t10, r"^P=(/\S+)$") + "/" + one(t10, r"^SP_R=\$P/(srv_splinter_restart5_r3d\.sh)\s"),
            "SP_R_SHA": one(t10, r"^SP_R_SHA=([0-9a-f]{64})$")}
    assert vals["SP_R_SHA"] == PKG_R3D_SHA                   # откат r10 пинит именно этот r3d
    vals["WA_DONE"] = _sh_render(one(t10, r'^  WA_DONE="(wa-agent ЧИСТЫЙ [^"]*)"$'), vals)
    assert vals["WA_DONE"] == _wa_done(PID_WA2), vals["WA_DONE"]
    want = (("s4 (r10 :718)", "both", _sh_render(one(t10, r'^  echo "(splinter: шаг 4 отката — bash [^"]*)"$'), vals)),
            ("форма (i) (r10 :721)", "i", "ROLLBACK_END 0 " + _sh_render(one(t10, r'^    0\) fin 0 "([^"]*)" ;;$'), vals)),
            ("форма (ii) (r10 :722)", "ii", "ROLLBACK_END 39 " + _sh_render(
                one(t10, r'^    2\|6\|8\|9\) fin 39 "([^"]*)" ;;$'), vals)),
            ("Environment (r3d :380)", "both", _sh_render(one(t3, r'^  echo "(splinter: Environment юнита \(systemd [^"]*)"$'),
                                                           vals)),
            ("СТОП «код 10» (r3d :416)", "ii", _sh_render(one(t3, r'echo "(STOP: СТОП ДО РЕСТАРТА: незавершённые карточки не '
                                                                   r'исключены \(код \$prc\) [^"]*)"; exit 6; \}$'), vals)),
            ("окно рестарта (r3d :462)", "i", _sh_render(one(t3, r'^echo "(окно рестарта: [^"]*)"$'), vals)),
            ("РЕСТАРТ SPLINTER ЧИСТЫЙ (r3d :573)", "i", _sh_render(one(t3, r'^echo "(РЕСТАРТ SPLINTER ЧИСТЫЙ: [^"]*)"$'), vals)))
    ji, jii = _journal("i").split("\n"), _journal("ii").split("\n")
    assert _stp() in jii
    for name, where, line in want:
        for form, j in (("i", ji), ("ii", jii)):
            if where in (form, "both"):
                assert line in j, (name, form, line[:120])
    print("  · h11: байты пакета r10 %s… / r3d %s… — %d строк фикстуры h9 дословно равны их шаблонам"
          % (PKG_R10_SHA[:8], PKG_R3D_SHA[:8], len(want)))


# =============================================================================================================================
# I. Только чтение
# =============================================================================================================================
FORBIDDEN_VERBS = {"restart", "start", "stop", "daemon-reload", "fetch", "reset", "merge", "push", "-w", "checkout",
                   "pull", "commit", "kill", "reload", "enable", "disable", "set-property", "edit", "gc", "prune"}


def _docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                out.add(id(b.value))
    return out


def test_i1_ast_lock():
    src = _read(ER.__file__)
    tree = ast.parse(src)
    imports = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imports.add((n.module or "").split(".")[0])
    assert imports <= {"os", "sys", "re", "time", "hashlib", "subprocess", "ctypes", "errno", "stat"}, imports
    for banned in ("health", "dotenv", "bridge_client", "anthropic", "notify", "splinter", "bot", "shutil", "socket",
                   "urllib", "importlib", "sqlite3", "requests"):
        assert banned not in imports, banned
    docs = _docstrings(tree)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}

    def of(mod):
        return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
                and n.value.id == mod}
    assert not ({"__file__", "__import__", "exec", "eval", "compile", "open_text"} & names), names
    assert not ({"environ", "environb", "getenv", "putenv"} & attrs), attrs & {"environ", "getenv"}
    os_bad = {"remove", "unlink", "rename", "replace", "mkdir", "makedirs", "rmdir", "chmod", "chown", "symlink", "link",
              "truncate", "utime", "kill", "system", "popen", "fork", "execv", "execve", "spawnv", "write", "ftruncate",
              "removedirs", "renames", "mkfifo", "mknod"}
    assert not (of("os") & os_bad), of("os") & os_bad
    assert "fdopen" not in of("os") and of("subprocess") <= {"run", "DEVNULL", "PIPE"}, (of("os"), of("subprocess"))
    assert of("ctypes") <= {"sizeof", "c_long", "c_uint", "c_int", "c_byte", "Structure", "byref", "CDLL"}, of("ctypes")
    for n in ast.walk(tree):                         # m5 линзы безопасности: os.open — только на чтение
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                and n.func.value.id == "os" and n.func.attr == "open":
            fl = {x.attr for x in ast.walk(n.args[1]) if isinstance(x, ast.Attribute)} \
                | {x.value for x in ast.walk(n.args[1]) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
            assert fl <= {"O_RDONLY", "O_NOFOLLOW", "O_CLOEXEC"}, fl
    cdll = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Call) and isinstance(n.func.value.func, ast.Attribute)
            and n.func.value.func.attr == "CDLL"}
    assert cdll == {"adjtimex"}, cdll                # из libc — только adjtimex(modes=0)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            for bad in ("Environment", "environ", "cmdline", ".env", "known_hosts", "PassEnvironment"):
                assert bad not in n.value, (bad, n.value[:80])
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            mode = n.args[1].value if len(n.args) > 1 and isinstance(n.args[1], ast.Constant) else "r"
            for kw in n.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            assert not set(str(mode)) & set("wax+"), mode
    runs = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
    assert len(runs) == 1 and runs[0].func.attr == "run", [r.func.attr for r in runs]
    world = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "World"][0]
    run_fn = [n for n in world.body if isinstance(n, ast.FunctionDef) and n.name == "run"][0]
    assert runs[0] in list(ast.walk(run_fn))
    called = [n.func.id for n in ast.walk(run_fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "argv_ok" in called
    # замок на ПОЛНЫЙ набор опций ssh ls-remote и окружение детей целиком (M1 линзы безопасности)
    assert ER.SSH_OPTS == ("BatchMode=yes", "StrictHostKeyChecking=yes", "UpdateHostKeys=no", "CheckHostIP=no",
                           "ControlMaster=no", "ControlPath=none", "PermitLocalCommand=no", "ClearAllForwardings=yes",
                           "ForwardAgent=no", "ForwardX11=no", "Tunnel=no"), ER.SSH_OPTS
    assert ER._CHILD_ENV == {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "TZ": "UTC", "HOME": "/root",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "ssh",
        "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o CheckHostIP=no "
                           "-o ControlMaster=no -o ControlPath=none -o PermitLocalCommand=no -o ClearAllForwardings=yes "
                           "-o ForwardAgent=no -o ForwardX11=no -o Tunnel=no"}, ER._CHILD_ENV
    for argv in ER._ARGV_OK + (ER.ARGV_HASH,):
        assert not (set(argv) & FORBIDDEN_VERBS), argv
        assert not any("Environment" in x for x in argv), argv
    assert not ER.argv_ok(("systemctl", "restart", "splinter"))
    assert not ER.argv_ok(ER.ARGV_HASH + ("-w", "x.py"))
    assert not ER.argv_ok(ER.ARGV_HASH)
    assert ER.argv_ok(ER.ARGV_HASH + ("bot.py",))


def test_i2_runtime_argv():
    for sc, extra in ((Sc(), ()), (Sc(state="base"), ()), (Sc().park_for_guard(), None)):
        argv = sc.args() if extra is not None else sc.args("--expect-run", sc.key(), "--expect-wa", sc.wa_key(),
                                                            "--guard", "unpark")
        _rc, _t, _r, w = run_er(sc, argv)
        for a in w.calls:
            assert ER.argv_ok(a) and not (set(a) & FORBIDDEN_VERBS), a
        for p in w.reads:
            assert re.match(r"^(/proc/sys/kernel/random/boot_id|/proc/[0-9]+/(stat|cgroup)|(lstat|hash):/etc/systemd/"
                            r"system/splinter\.service\.d/zz-k3-closetruth(\.undo)?\.conf)$", p), p
        shows = [a for a in w.calls if a[:2] == ("systemctl", "show")]
        assert len([a for a in shows if a == ER.ARGV_SHOW_SP]) == 3 and len([a for a in shows if a == ER.ARGV_SHOW_WA]) == 2


def test_i3_launch_form():
    src = open(ER.__file__, "rb").read()
    for extra, cls in ((["--bogus"], "unknown"), (["--guard"], "missing_value"), ([], "no_args"),
                       (["--guard", "unpark"], "missing_sha")):
        p = subprocess.run([sys.executable, "-I", "-S", "-B", "-"] + extra, input=src, capture_output=True, timeout=60)
        assert p.returncode == 50, (extra, p.returncode, p.stderr[-300:])
        got = p.stdout.replace(b"\r\n", b"\n").decode()      # на Windows текстовый stdout пишет \r\n; на сервере — \n
        assert got == "ENTRY_READ_USAGE %s\n" % cls and p.stderr == b"", (p.stdout, p.stderr[-300:])


def test_i4_no_blind_readers():
    """Храповик слепых читателей (blind_readers.find_blind): у модуля ноль «пустое наверх из ветки промаха» — «не прочитано»
    всюду None или код причины, а не пустое значение."""
    import blind_readers as BR
    assert BR.find_blind(_read(ER.__file__), "entry_read.py") == []


# =============================================================================================================================
# J. Охрана --guard unpark и повторная сверка --recheck
# =============================================================================================================================
def _guard_argv(sc, **kw):
    return sc.args("--expect-run", kw.get("k", sc.key()), "--expect-wa", kw.get("kwa", sc.wa_key()), "--guard", "unpark")


def test_j1_guard_pass_on_park():
    sc = Sc().park_for_guard()
    rc, text, r, _w = run_er(sc, _guard_argv(sc))
    assert rc == 0 and r["class"] == "PARKED" and r["guard"] == "PASS", text
    assert r["code"] == "NEWER" and r["wa"] == "ok" and r["want_state"] == "base" and r["want_sha"] == SHA_RB
    assert why(r)[0] == "park" and not [x for x in why(r) if x.startswith("guard_")], text


def test_j2_each_guard_condition():
    def mod_run(sc):
        return {"k": key_with(sc.key(), nr=NR_SP + 1)}

    cases = (
        ("guard_run", mod_run, None),
        ("guard_code", None, lambda sc: setattr(sc, "head", "9" * 40)),
        ("guard_code", None, lambda sc: setattr(sc, "status", b" M bot.py\n")),
        ("guard_code", None, lambda sc: sc.work.__setitem__("bot.py", "5" * 40)),
        ("guard_code", None, lambda sc: (sc.tree.__setitem__("bot.py", "6" * 40), sc.work.__setitem__("bot.py", "6" * 40))),
        ("guard_ndr", None, lambda sc: setattr(sc, "cfg_wa", [{"LoadState": "loaded", "NeedDaemonReload": "yes"}])),
        ("guard_ndr", None, lambda sc: setattr(sc, "cfg_sp", [{"LoadState": "masked", "NeedDaemonReload": "no",
                                                               "DropInPaths": ""}])),
        ("guard_dropin", None, lambda sc: sc.dropin.__setitem__(ER.DB, ("file", DB_PIN))),
        ("guard_wa", None, lambda sc: sc.mtime.__setitem__("bot.py", sc.ems_wa + 10)),
        ("guard_wa", lambda sc: {"kwa": key_with(sc.wa_key(), pid=PID_WA + 5)}, None),
        ("guard_clock", None, lambda sc: setattr(sc, "adj", [{"rc": 5, "maxerror": 16000000, "status": 64}])),
    )
    for code, argmod, scmod in cases:
        sc = Sc().park_for_guard()
        if scmod:
            scmod(sc)
        kw = argmod(sc) if argmod else {}
        rc, text, r, _w = run_er(sc, _guard_argv(sc, **kw))
        assert rc == 58 and r["guard"] == "REFUSED" and code in why(r), (code, text)


def test_j3_guard_refuses_non_park():
    sc = Sc(state="base")
    rc, text, r, _w = run_er(sc, sc.args("--expect-run", sc.key(), "--expect-wa", sc.wa_key(), "--guard", "unpark"))
    assert rc == 58 and "guard_park" in why(r), text                             # CLEAN
    for mod in (lambda sc: sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC, d=False, e=False, f=False, jobs=False)),
                lambda sc: setattr(sc, "sp", [props(0, sc.ems, sc.emsm, NR_SP, act="inactive", sub="dead", inv="")]),
                lambda sc: sc.set_log(history(sc.ems) + cand_proc(sc.ems + FRAC)),
                lambda sc: setattr(sc, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "yes", "DropInPaths": ""}])):
        sc = Sc().park_for_guard()
        mod(sc)
        rc, text, r, _w = run_er(sc, _guard_argv(sc))
        assert rc == 58 and r["guard"] == "REFUSED", text


def _recheck_argv(sc, against, **kw):
    return ["--recheck", "--sha", kw.get("sha", SHA_RB), "--label", kw.get("label", LABEL), "--db-sha", DB_PIN,
            "--du-sha", DU_PIN, "--expect-run", kw.get("k", sc.key()), "--expect-wa", kw.get("kwa", sc.wa_key()),
            "--against", against]


def _recheck(sc, against, **kw):
    out = io.StringIO()
    w = FakeWorld(sc)
    rc = ER.main(_recheck_argv(sc, against, **kw), world=w, out=out)
    return rc, out.getvalue(), w


def _park_db():
    """Простой K0 со СВОИМ drop-in, загруженным и на диске (L = D = {DB}): база его не читает, охрана PASS."""
    sc = Sc().park_for_guard()
    sc.cfg_sp = [{"LoadState": "loaded", "NeedDaemonReload": "no", "DropInPaths": ER.DB}]
    sc.dropin[ER.DB] = ("file", DB_PIN)
    return sc


def test_j4_recheck_pass_and_each_drift():
    """--recheck: тест на КАЖДОЕ поле дрейфа (r2 п.5): полная K0 — boot_id, InvocationID, MainPID, EMSmono, NRestarts,
    состояние; полный KWA1 — каждое поле и состояние, и повторное чтение в конце; HEAD; index и worktree; NDR и LoadState
    обеих служб; набор и тела своих drop-in и отпечаток DropInPaths (чужой drop-in); каждое неполное чтение; квитанция
    не та (в том числе dropin ≠ OK). Каждый — отказ 63 с точным полем, рестарта нет."""
    sc = Sc().park_for_guard()
    rc, text, r, _w = run_er(sc, _guard_argv(sc))
    assert rc == 0, text
    g = text.rstrip("\n")
    rc, out, w = _recheck(Sc().park_for_guard(), g)
    assert rc == 0 and ER.RECHECK_RE.match(out.rstrip("\n")), out
    assert not any(a in (ER.ARGV_ORIGIN, ER.ARGV_LSTREE) or a[:len(ER.ARGV_HASH)] == ER.ARGV_HASH for a in w.calls)
    assert len([a for a in w.calls if a == ER.ARGV_SHOW_WA]) == 2 and len([a for a in w.calls if a == ER.ARGV_SHOW_SP]) == 2
    wa_mod = (lambda s, **kw: setattr(s, "wa", [props(kw.get("pid", PID_WA), s.ems_wa, kw.get("emsm", s.emsm_wa),
                                                      kw.get("nr", NR_WA), act=kw.get("act", "active"),
                                                      sub=kw.get("sub", "running"), inv=kw.get("inv", INV_WA))]))
    drifts = (
        ("run", lambda s: setattr(s, "sp", [props(PID_SP + 1, s.ems, s.emsm, NR_SP)])),                       # MainPID
        ("run", lambda s: setattr(s, "sp", [props(PID_SP, s.ems, s.emsm, NR_SP + 1)])),                       # NRestarts
        ("run", lambda s: setattr(s, "sp", [props(PID_SP, s.ems, s.emsm, NR_SP, inv="f" * 32)])),             # InvocationID
        ("run", lambda s: setattr(s, "sp", [props(PID_SP, s.ems, s.emsm + 1, NR_SP)])),                       # EMSmono
        ("run", lambda s: setattr(s, "sp", [props(PID_SP, s.ems, s.emsm, NR_SP, act="deactivating", sub="stop-sigterm")])),
        ("run", lambda s: setattr(s, "sp", [props(PID_SP, s.ems, s.emsm, NR_SP), props(PID_SP + 1, s.ems, s.emsm, NR_SP)])),
        ("run", lambda s: setattr(s, "boot", [b"9a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d\n"])),                  # boot_id
        ("run", lambda s: setattr(s, "boot", [BOOT.encode() + b"\n", b"9a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d\n"])),
        ("wa", lambda s: wa_mod(s, pid=PID_WA + 1)), ("wa", lambda s: wa_mod(s, inv="0" * 32)),
        ("wa", lambda s: wa_mod(s, emsm=s.emsm_wa + 1)), ("wa", lambda s: wa_mod(s, nr=NR_WA + 1)),
        ("wa", lambda s: wa_mod(s, act="activating", sub="auto-restart")),
        ("wa", lambda s: setattr(s, "wa", [props(PID_WA, s.ems_wa, s.emsm_wa, NR_WA, inv=INV_WA),
                                           props(PID_WA + 1, s.ems_wa, s.emsm_wa, NR_WA, inv=INV_WA)])),         # в конце
        ("head", lambda s: setattr(s, "head", "9" * 40)),
        ("dirty", lambda s: setattr(s, "status", b"M  bot.py\n")),                                              # index
        ("dirty", lambda s: setattr(s, "status", b" M bot.py\n")),                                              # worktree
        ("ndr", lambda s: setattr(s, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "yes", "DropInPaths": ""}])),
        ("ndr", lambda s: setattr(s, "cfg_wa", [{"LoadState": "loaded", "NeedDaemonReload": "yes"}])),
        ("ndr", lambda s: setattr(s, "cfg_sp", [{"LoadState": "masked", "NeedDaemonReload": "no", "DropInPaths": ""}])),
        ("ndr", lambda s: setattr(s, "cfg_wa", [{"LoadState": "not-found", "NeedDaemonReload": "no"}])),
        ("dropin", lambda s: s.dropin.__setitem__(ER.DU, ("file", DU_PIN))),                                   # набор: D
        ("dropin", lambda s: s.dropin.__setitem__(ER.DB, ("file", "0" * 64))),                                 # тело
        ("dropin", lambda s: setattr(s, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "no",
                                                    "DropInPaths": ER.DB}])),                                   # набор: L
        ("dropin", lambda s: setattr(s, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "no",
                                                    "DropInPaths": ER.DD + "/override.conf"}])),                # чужой
        ("rd_unit", lambda s: s.fail.__setitem__("sp", lambda i: (1, b""))),
        ("rd_unit", lambda s: s.fail.__setitem__("sp", lambda i: (1, b"") if i >= 1 else None)),               # в конце
        ("rd_boot", lambda s: s.fail.__setitem__("read:" + ER.BOOT_ID, lambda i: OSError(5, "EIO"))),
        ("rd_boot", lambda s: setattr(s, "boot", [BOOT.encode() + b"\n", b"zz\n"])),                           # в конце
        ("rd_wa", lambda s: s.fail.__setitem__("wa", lambda i: subprocess.TimeoutExpired("systemctl", 15))),
        ("rd_wa", lambda s: s.fail.__setitem__("wa", lambda i: (1, b"") if i >= 1 else None)),                 # в конце
        ("rd_git", lambda s: s.fail.__setitem__("status", lambda i: (128, b""))),
        ("rd_git", lambda s: s.fail.__setitem__("head", lambda i: subprocess.TimeoutExpired("git", 15))),
        ("rd_cfg", lambda s: s.fail.__setitem__("cfg_wa", lambda i: (1, b""))),
        ("rd_dropin", lambda s: s.dropin.__setitem__(ER.DB, (PermissionError(13, "нет"), None))),
    )
    for field, mod in drifts:
        s = Sc().park_for_guard()
        mod(s)
        rc, out, _w = _recheck(s, g)
        assert rc == 63 and out == "UNPARK_END refused recheck=%s\n" % field, (field, rc, out)
    sd = _park_db()                                                  # охрана со своим drop-in (L = D = {DB})
    gd = run_er(sd, _guard_argv(sd))[1].rstrip("\n")
    assert ER.parse_receipt(gd)["guard"] == "PASS" and ER.parse_receipt(gd)["dl"] == "b-", gd
    assert _recheck(_park_db(), gd)[0] == 0
    for mod in (lambda s: s.dropin.__setitem__(ER.DB, ("file", "0" * 64)), lambda s: s.dropin.__setitem__(ER.DB, ("absent", None)),
                lambda s: s.dropin.__setitem__(ER.DB, ("link", DB_PIN)),
                lambda s: setattr(s, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "no", "DropInPaths": ""}]),
                lambda s: setattr(s, "cfg_sp", [{"LoadState": "loaded", "NeedDaemonReload": "no",
                                                 "DropInPaths": "/etc/x.conf " + ER.DB}])):
        s = _park_db()
        mod(s)
        rc, out, _w = _recheck(s, gd)
        assert rc == 63 and out == "UNPARK_END refused recheck=dropin\n", out
    for kw in ({"k": key_with(sc.key(), pid=PID_SP + 1)}, {"label": "other/V2"}, {"sha": SHA_V},
               {"kwa": key_with(sc.wa_key(), nr=NR_WA + 1)}):
        rc, out, _w = _recheck(Sc().park_for_guard(), g, **kw)
        assert rc == 63 and out == "UNPARK_END refused recheck=against\n", (kw, out)
    for spoil in (g.replace("guard=PASS", "guard=REFUSED"), g.replace("class=PARKED", "class=MIXED"),
                  g.replace("ndr=no/no", "ndr=yes/no"), g.replace("dropin=OK", "dropin=ARMED"),
                  re.sub(r"dpaths=[0-9a-f]{12}", "dpaths=?", g)):
        rc, out, _w = _recheck(Sc().park_for_guard(), spoil)
        assert rc == 63 and out == "UNPARK_END refused recheck=against\n", out


def test_j5_recheck_usage():
    sc = Sc().park_for_guard()
    g = run_er(sc, _guard_argv(sc))[1].rstrip("\n")
    for argv in (_recheck_argv(sc, g)[:-2], _recheck_argv(sc, g) + ["--state", "base"],
                 _recheck_argv(sc, g) + ["--guard", "unpark"], _recheck_argv(sc, "not a receipt"),
                 _recheck_argv(sc, g + "\n")):
        out = io.StringIO()
        assert ER.main(argv, world=FakeWorld(sc), out=out) == 50, (argv, out.getvalue())


# =============================================================================================================================
# Z. Мутанты: (было, стало, слова, проверки, которые обязаны упасть). Пары — несколько замен одного мутанта.
# =============================================================================================================================
MUTANTS = (
    ((("START_SKEW_S = 300          #", "START_SKEW_S = 301          #"),), "окно 300 → 301", ("test_e6_age_300",)),
    ((("START_SKEW_S = 300          #", "START_SKEW_S = 299          #"),), "окно 300 → 299", ("test_e6_age_300",)),
    ((("BIRTH_TOL_S = 2.0 ", "BIRTH_TOL_S = 20.0 "),), "рождение 2 → 20 с", ("test_c5_birth_delta",)),
    ((('if abs(u["aem"] - u["emsm"]) / 1e6 > AE_TOL_S:', "if False:"),), "AE/EMS снята", ("test_c7_ae_ems",)),
    ((('if sc["above"] > 0 or seg["dup"]:', 'if seg["dup"]:'),), "снято «выше сегмента»",
     ("test_e3_chain_above_segment", "test_b1_never_greener_than_health")),
    ((('seg["dup"] = True', 'seg["dup"] = False'),), "снят «≤ 1 раза»", ("test_e4_dups",)),
    ((('if _RANK[kind] <= seg["last_rank"] or tms < seg["last_ts"]:', "if False:"),), "снят порядок",
     ("test_e5_order",)),
    ((('if "d" in rec or "e" in rec or "f" in rec or seg["intake"] > 0:', 'if seg["intake"] > 0:'),),
     "у PARKED снят запрет d/e/f", ("test_e11_park_with_intake", "test_b1_never_greener_than_health")),
    ((('if "d" in rec or "e" in rec or "f" in rec or seg["intake"] > 0:', 'if "d" in rec or "e" in rec or "f" in rec:'),),
     "снят запрет intake", ("test_e11_park_with_intake",)),
    ((('ORDER = WHY_UNKNOWN + ("down", "park", "nopoll") + WHY_MIXED + WHY_ARMED',
       'ORDER = WHY_UNKNOWN + ("down",) + WHY_MIXED + ("park", "nopoll") + WHY_ARMED'),), "PARKED ниже MIXED",
     ("test_j1_guard_pass_on_park", "test_c3_expect_run_foreign_park_is_unknown")),
    ((("if not (sp[0] == sp[1] == sp[2]):", "if not (sp[0] == sp[1]):"),), "снята сверка S2",
     ("test_c1_each_key_changes_between_reads",)),
    ((('if a.get("--expect-run") is not None and key != a["--expect-run"]:', "if False:"),), "снят --expect-run",
     ("test_c3_expect_run_foreign_park_is_unknown",)),
    ((('and u["nr"] == 0):', "and True):"),), "у --prev-run снято NRestarts = 0", ("test_c4_prev_run",)),
    ((("MAXERR_US = 16000000 ", "MAXERR_US = 60000000 "),), "maxerror 16 → 60 с", ("test_d2_maxerror_threshold",)),
    ((('if t0[0] < int(a["--not-before"]):', "if False:"),), "снят not-before", ("test_d3_not_before",)),
    ((('if g["mtime"][x] > u["ems"]])', 'if g["mtime"][x] > u["ems"] + 10 ** 9])'),), "снята сверка mtime",
     ("test_f1_code",)),
    ((('if g["dirty"] > 0:\n            codes.add("dirty")', 'if False:\n            codes.add("dirty")'),), "снят dirty",
     ("test_f1_code",)),
    ((('why = ["rd_origin"]', "why = []"),), "снят origin при CLEAN", ("test_f1_code",)),
    ((('return "ok" if h == pin else "bad"', 'return "ok"'),), "снят пин тела drop-in", ("test_g1_dropin_grid",)),
    ((('if "yes" in (F["ndr_sp"], F["ndr_wa"]):', "if False:"),), "снят NDR", ("test_g2_dropin_read_failures",)),
    ((('codes.add("wa_down")', "pass"), ('codes.add("wa_newer")', "pass")), "снят wa", ("test_f1_code",)),
    ((('gw.append("guard_park")', "pass"),), "охрана: снят класс", ("test_j3_guard_refuses_non_park",)),
    ((('gw.append("guard_run")', "pass"),), "охрана: снят ключ", ("test_j2_each_guard_condition",)),
    ((('gw.append("guard_code")', "pass"),), "охрана: снят код", ("test_j2_each_guard_condition",)),
    ((('gw.append("guard_ndr")', "pass"),), "охрана: снят NDR", ("test_j2_each_guard_condition",)),
    ((('gw.append("guard_dropin")', "pass"),), "охрана: снят drop-in", ("test_j2_each_guard_condition",)),
    ((('gw.append("guard_wa")', "pass"),), "охрана: снят wa", ("test_j2_each_guard_condition",)),
    ((('gw.append("guard_clock")', "pass"),), "охрана: сняты часы", ("test_j2_each_guard_condition",)),
    ((("status = _git(w, ARGV_STATUS)\n", 'status = _git(w, ARGV_STATUS) or ""\n'),), "сбой git → правок 0",
     ("test_f2_each_git_call_failure",)),
    ((('CODE = {"CLEAN": 0, "PARKED": 51, "NOPOLL": 52, "DOWN": 53, "MIXED": 54,',
       'CODE = {"CLEAN": 54, "PARKED": 51, "NOPOLL": 52, "DOWN": 53, "MIXED": 0,'),), "rc CLEAN/MIXED переставлены",
     ("test_h1_receipt_grammar_and_codes",)),
    ((('if self.cur is not None and self.cur >= self.lo:\n                    self.generic.add("stamp")',
       'if False:\n                    self.generic.add("stamp")'),), "снята метка неизвестной формы",
     ("test_e8_stamp_and_utf8", "test_b1_never_greener_than_health")),
    ((('if ts is None and self.cur is not None and self.cur >= self.lo:\n                self.generic.add("stamp")',
       'if False:\n                self.generic.add("stamp")'),), "снята неразобранная метка записи", ("test_e8_stamp_and_utf8",)),
    ((('if ts is not None and self.hi is not None and ts < self.hi - BACK_S:', "if False:"),), "снят шаг назад 120 с",
     ("test_e18_back_step_120",)),
    ((('if not _utf8_ok(ln):\n                self.generic.add("utf8")', 'if False:\n                self.generic.add("utf8")'),),
     "снят байт не UTF-8", ("test_e8_stamp_and_utf8", "test_b1_never_greener_than_health")),
    ((('if not self.pend and own is not None and own >= self.lo:', "if False:"),), "снято правило pend",
     ("test_e19_pend_stamp_before_run", "test_b1_never_greener_than_health")),
    ((('or size1 < size0 or (size1 == size0 and mt1 != mt0):', 'or False:'),), "снята ротация",
     ("test_e1_log_unread_short_rot_cap",)),
    ((('if size0 > LOG_CAP_BYTES:', "if False:"),), "снят потолок размера", ("test_e1_log_unread_short_rot_cap",)),
    ((('seg["win_a"] = self.w_lo <= tms <= self.w_hi', 'seg["win_a"] = True'),), "снята посылка окна a",
     ("test_e2_premise",)),
    ((('or run_key(boot, sp) != a["--expect-run"]:', ":"),), "recheck: снят ключ K0",
     ("test_j4_recheck_pass_and_each_drift",)),
    ((('or run_key(boot, wa) != a["--expect-wa"]:', ":"),), "recheck: снят KWA1", ("test_j4_recheck_pass_and_each_drift",)),
    ((('if head.strip() != a["--sha"]:', "if False:"),), "recheck: снят HEAD", ("test_j4_recheck_pass_and_each_drift",)),
    ((('if [x for x in status.split("\\n") if x != ""]:', "if False:"),), "recheck: снят dirty",
     ("test_j4_recheck_pass_and_each_drift",)),
    ((('!= ("no", "no", "loaded", "loaded"):', '!= (cfg["ndr_sp"], cfg["ndr_wa"], cfg["load_sp"], cfg["load_wa"]):'),),
     "recheck: снят NDR", ("test_j4_recheck_pass_and_each_drift",)),
    ((('if live_l != r["dl"] or live_d != r["dd"] or cfg["dp"] != r["dpaths"]:', "if False:"),), "recheck: снят drop-in",
     ("test_j4_recheck_pass_and_each_drift",)),
    ((('or r["wa"] != "ok" or r["wa_key"] != a["--expect-wa"]', 'or r["wa"] != "ok"'),), "recheck: квитанция без KWA1",
     ("test_j4_recheck_pass_and_each_drift",)),
    # --- build2: линза code (m1–m14), атака (M1, M2), безопасность (M1), спец (M2, M3)
    ((('codes.add("state")', "pass"),), "снят state", ("test_e22_state_and_fv",)),
    ((('codes.add("fv")', "pass"),), "снят fv", ("test_e22_state_and_fv",)),
    ((('codes.add("wa_down")', "pass"),), "снят только wa_down", ("test_c16_wa_every_unread_is_code",)),
    ((('if wb0 is None or wb1 is None or wb0 != wb1 or not tck or not (wb0[1] and wb1[1]) \\\n'
       '                    or w2["inv"] == "" or abs(wb0[0] / float(tck) - w2["emsm"] / 1e6) > BIRTH_TOL_S:',
       'if wb0 is None or wb1 is None or not tck:'),), "wa: снято рождение/cgroup/InvocationID",
     ("test_c16_wa_every_unread_is_code",)),
    ((('elif w2["ems"] < 0:\n                codes.add("wa_ident")', 'elif False:\n                codes.add("wa_ident")'),),
     "wa: метка старта не прочитана → без кода", ("test_c16_wa_every_unread_is_code",)),
    ((('elif b is None:\n            codes.add("chain_partial")', 'elif False:\n            codes.add("chain_partial")'),),
     "PARKED без строки флагов", ("test_e21_park_without_b",)),
    ((('codes.add("entry_grammar")', "pass"),), "снят entry_grammar", ("test_e20_grammar_codes",)),
    ((('codes.add("flags_grammar")', "pass"),), "снят flags_grammar", ("test_e20_grammar_codes",)),
    ((('if c is not None and c["form"] != "bad" and words and len(b["keys"]) != 5:\n        codes.add("flags_entry")',
       'if False:\n        codes.add("flags_entry")'),), "снят flags_entry (ключи)", ("test_e20_grammar_codes",)),
    ((('if not words or len(b["words"]) != 5 or any(x not in allowed[i] for i, x in enumerate(b["words"])):\n'
       '            codes.add("flags_entry")', 'if False:\n            codes.add("flags_entry")'),),
     "снят flags_entry (слова)", ("test_e20_grammar_codes",)),
    ((('codes.add("rd_proc")', "pass"),), "снят rd_proc", ("test_c15_rd_proc",)),
    ((('codes.add("dropin_bad")', "pass"),), "снят dropin_bad", ("test_g1_dropin_grid",)),
    ((('if u["ems"] > t2[0] + AHEAD_S:', "if False:"),), "снят старт юнита впереди", ("test_d8_unit_start_ahead",)),
    ((('live_d = ("b" if db == "ok" else ("?" if db == "bad" else "-")) + ("u" if du == "ok" else ("?" if du == "bad" else "-"))',
       'live_d = ("b" if db in ("ok", "bad") else "-") + ("u" if du in ("ok", "bad") else "-")'),),
     "recheck: тело не по пину считается присутствием", ("test_j4_recheck_pass_and_each_drift",)),
    ((('if (cfg["ndr_sp"], cfg["ndr_wa"], cfg["load_sp"], cfg["load_wa"]) != ("no", "no", "loaded", "loaded"):',
       'if (cfg["ndr_sp"], cfg["ndr_wa"]) != ("no", "no"):'),), "recheck: снят LoadState",
     ("test_j4_recheck_pass_and_each_drift",)),
    ((('or cfg["dp"] != r["dpaths"]:', ":"),), "recheck: снят отпечаток DropInPaths", ("test_j4_recheck_pass_and_each_drift",)),
    ((('if wa2 != wa:', "if False:"),), "recheck: снято повторное чтение wa в конце", ("test_j4_recheck_pass_and_each_drift",)),
    ((('or r["dropin"] != "OK"', 'or r["dropin"] not in ("OK", "ARMED")'),), "recheck: квитанция с ARMED",
     ("test_j4_recheck_pass_and_each_drift",)),
    ((('if sc["win"]["a"] > 1 or sc["win"]["c"] > 1:', "if False:"),), "снят счёт по окну", ("test_b3_second_writer_window",)),
    ((('if kind in self.win and ts >= self.lo - WIN_BACK_S:', 'if kind in self.win and ts >= self.lo:'),),
     "окно счёта без 2 с назад", ("test_b3_second_writer_window",)),
    ((('codes.add("gen_contra")', "pass"),), "снят gen_contra", ("test_b3_second_writer_window", "test_e14_base")),
    ((('if g is not None and "code_newer" not in codes:', 'if g is not None:'),), "gen_contra и при code_newer",
     ("test_b3_second_writer_window",)),
    ((('if not why and _clean_proven(P):', "if False:"),), "сняты положительные ворота CLEAN",
     ("test_h8_lost_code_is_unknown", "test_h8b_each_code_line_lost_never_clean")),
    ((('if a.get("--expect-wa") is not None and wkey != a["--expect-wa"]:', "if False:"),), "снят --expect-wa",
     ("test_c14_expect_wa_any_mode",)),
    ((('if "--expect-wa" not in a:\n            raise Usage("guard_needs_expect_wa")',
       'if False:\n            raise Usage("guard_needs_expect_wa")'),), "охрана без --expect-wa", ("test_h2_usage",)),
    ((('not _ARG_FORM[k].fullmatch(val)', 'not _ARG_FORM[k].match(val)'),), "аргументы match вместо fullmatch",
     ("test_h2_usage",)),
    ((('"|".join(LEVELS).encode("ascii")', 'b"[A-Z]+"'),), "грамматика записи: уровень [A-Z]+ (r5)",
     ("test_e23_record_grammar_r6",)),
    ((('+ rb")\\] (" + _NAME_B + rb"): ")', '+ rb")\\] (\\S+): ")'),), "грамматика записи: имя \\S+ (r5)",
     ("test_e23_record_grammar_r6",)),
    ((('max(int(ems_precise // 1), u["ems"])', 'int(ems_precise // 1)'),), "нижняя граница окна ⌊EMS точный⌋",
     ("test_e24_window_lower_bound",)),
    ((('"CheckHostIP=no", ', ''),), "ssh ls-remote без CheckHostIP=no", ("test_i1_ast_lock",)),
    ((('"GIT_ALLOW_PROTOCOL": "ssh",', ''),), "ls-remote без GIT_ALLOW_PROTOCOL=ssh", ("test_i1_ast_lock",)),
    # --- build3: правило pend r7 (линзы code / атаки / спецификации круга 2) и положительные ворота по фактам
    ((('if ts is not None and ts < self.lo - WIN_BACK_S and not self.in_run:',
       'if ts is not None and ts < self.lo and not self.in_run:'),), "pend: снимает запись окна [старт − 2 с, старт) (r6)",
     ("test_e19_pend_stamp_before_run", "test_b4_pend_rule_r7")),
    ((('if ts is not None and ts < self.lo - WIN_BACK_S and not self.in_run:',
       'if ts is not None and ts < self.lo - WIN_BACK_S:'),), "pend: снимает и запись ниже начала запуска",
     ("test_e19_pend_stamp_before_run", "test_b4_pend_rule_r7")),
    ((('("ident", ident),', '("ident", True),'),), "ворота: снята «личность перечитана»", ("test_h7_clean_positive_table",)),
    ((('and sc["ahead_at"] <= sc["hist_at"] and sc["lines_max"] <= RUN_LINES_CAP', 'and sc["lines_max"] <= RUN_LINES_CAP'),),
     "ворота: снят факт открытой pend-метки", ("test_h7_clean_positive_table", "test_h8b_each_code_line_lost_never_clean")),
)


def _spawn(mut_dir, tests):
    env = dict(os.environ, ENTRY_READ_SRC=mut_dir, ENTRY_READ_ONLY=",".join(tests), PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("ENTRY_READ_MUTANTS", None)
    return subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=TREE, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)


def test_zz_mutants():
    if SRC or ONLY:
        return
    if os.environ.get("ENTRY_READ_MUTANTS") != "1":
        print("  SKIP мутанты: ENTRY_READ_MUTANTS не 1 (квитанция мутантов — отдельным запуском)")
        return
    src = _read(ER.__file__)
    union = sorted({t for m in MUTANTS for t in m[2]})
    null_dir = tempfile.mkdtemp(prefix="entry_read_null_", dir=TMP)
    with open(os.path.join(null_dir, "entry_read.py"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(src)
    jobs = [("нулевой мутант (копия без правки)", _spawn(null_dir, union), True)]
    for pairs, words, tests in MUTANTS:
        text = src
        for old, new in pairs:
            assert text.count(old) == 1, (words, old, text.count(old))
            text = text.replace(old, new)
        d = tempfile.mkdtemp(prefix="entry_read_mut_", dir=TMP)
        with open(os.path.join(d, "entry_read.py"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        jobs.append((words, _spawn(d, tests), False))
        if len([j for j in jobs if j[1].poll() is None]) >= 6:
            jobs[-6][1].wait()
    missed = []
    for words, p, null in jobs:
        out = p.communicate(timeout=1800)[0].decode("utf-8", "replace")
        fell = [ln.split()[1] for ln in out.splitlines() if ln.startswith("FAIL ")]
        print("    · мутант «%s»: упало %d — %s" % (words, len(fell), ", ".join(fell[:4])))
        if null:
            if p.returncode != 0 or fell:
                missed.append((words, out[-800:]))
        elif p.returncode == 0 or not fell:
            missed.append((words, out[-800:]))
    print("  · мутантов %d + нулевой; не пойманы: %d" % (len(MUTANTS), len(missed)))
    assert not missed, missed


# Мутанты помощника ПК (ENTRY_READ_MUTANTS=1 и ENTRY_READ_HELPER): каждая замена снимает одну проверку пути V — h9 обязан упасть.
HELPER_MUTANTS = (
    ('[ "$VR_FORM" = ii ] && [ "$VR_ENTRY" = E-PARK ] || stop ux', 'true || stop ux', "ux без формы (ii) / E-PARK"),
    ('[ "$nux" = 1 ] || stop ux', 'true || stop ux', "ux без замка «один ux на каталог»"),
    ('[ "$pid" = "$VR_PID" ] || { KW_WHY=', 'true || { KW_WHY=', "KWA1 без привязки к PID из WA_DONE"),
    ('[ "$k" != "$VR_KWA0" ] || { KW_WHY=', 'true || { KW_WHY=', "KWA1 = KWA0 допущен"),
    ('[ "$nstp" = 1 ] && case "$stp" in "$VR_STP10$rb$VR_STP10_RB"*) true ;; *) false ;; esac', 'true',
     "vr: (в) «код 10» не сверяется"),
    ('[ "$V0_KIND" = E-PARK ] || stop vr', 'true || stop vr', "vr: 39 при E-MIX/E-ARM допущен"),
    ('case "$V0_KIND" in E-MIX|E-ARM) ;;', 'case "$V0_KIND" in *) ;;', "vr: END 0 при E-PARK допущен"),
    ('case "$EMIX_WHY" in *",$w,"*) ;;', 'case "$EMIX_WHY" in *) ;;', "ENTRY: why E-MIX не сверяется"),
    ('{ [ "$why" = park ] || {', '{ true || {', "ENTRY: why E-PARK не сверяется"),
    ('[ "$git" = "${sha:0:12}/${sha:0:12}/0" ] || { EK_WHY=', 'true || { EK_WHY=', "ENTRY: git=V/V/0 не сверяется"),
    ('[ "$nwin" = 0 ] && [ "$nrst" = 0 ] ||', 'true ||', "vr: (г) окно рестарта не сверяется"),
    ('[ "$npre" = 1 ] && {', 'true && {', "vr: (б) ПРЕДПРОВЕРКА не одна"),
    ('[ "$VR_FORM" = i ] || [ -n "$xw" ] || stop er', 'true || stop er', "V3 после (ii) без --expect-wa"),
    ('[ "$classes" = PARKED ] && [ "$VR_FORM" = ii ] && [ "$VR_ENTRY" = E-PARK ] && [ "$xr" = "$VR_K0" ]',
     '[ "$classes" = PARKED ] && [ "$xr" = "$VR_K0" ]', "V2a без формы (ii)"),
    ('[[ "$s4" =~ $re ]] || stop vr', 'true || stop vr', "vr: строка шага 4 не сверяется"),
    ('echo "STAGE_END ux rc=$rc"', 'echo "STAGE_END ux rc=1"', "ux: STAGE_END расходится с кодом выхода"),
    ('[ "$d" = "${RD_NAME:-}" ] ||', 'true ||', "файл квитанции не из каталога сессии"),
    ('*"; splinter ЧИСТЫЙ: шаг 4 (srv_splinter_restart5_r3d.sh) вернул 0 на коде отката $rb (дерево 947953e) — его '
     'итоговая строка выше") ;;', '*) ;;', "vr: хвост формы (i) не сверяется"),
    ('[ "$nwin" = 1 ] && [[ "$win" =~ $re ]] || stop vr', 'true || stop vr', "vr: (i) без строки окна рестарта"),
    ('[ "$EK" = "$V0_KIND" ] && ', '', "V0: ER_ENTRY не сверяется с квитанцией"),
    # --- build3: формы r10/r3d (M1 линзы спецификации), V2a/V3 только с --vr (M2 линзы атаки), шаблон ux (MJ1 линзы
    # безопасности: четыре мутанта ловит h10, h9 их не видит)
    ('[ -n "$vr" ] || [ -z "$xr$pr$xw" ] || stop er', 'true || stop er', "V2a/V3 без --vr допущены"),
    ('case "$last" in *"$VR_II_MID"*) ;;', 'case "$last" in *) ;;', "vr: середина формы (ii) (код 6, r10 :722) не сверяется"),
    ('\\(пин \'"$VR_S4_PIN"\'…\\)', '\\(пин [0-9a-f]{12}…\\)', "vr: пин шага 4 r3d не сверяется"),
    ('if (index(L[i], stp) > 0)', 'if (index(L[i], stp) == 1)', "vr: (в) «СТОП ДО РЕСТАРТА» — только с начала строки"),
) + UX_TMPL_MUTANTS


def test_zz_helper_mutants():
    if SRC or ONLY:
        return
    path = os.environ.get("ENTRY_READ_HELPER", "")
    if os.environ.get("ENTRY_READ_MUTANTS") != "1" or not path:
        print("  SKIP мутанты помощника: нужны ENTRY_READ_MUTANTS=1 и ENTRY_READ_HELPER")
        return
    text = _read(path)
    jobs = []
    for old, new, words in HELPER_MUTANTS:
        assert text.count(old) == 1, (words, text.count(old))
        d = tempfile.mkdtemp(prefix="helper_mut_", dir=TMP)
        p = os.path.join(d, "lifecycle_er_r1.sh")
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace(old, new))
        env = dict(os.environ, ENTRY_READ_HELPER=p, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
                   ENTRY_READ_ONLY="test_h6_helper_contract,test_h9_helper_v_path_table,test_h10_ux_template_exec")
        env.pop("ENTRY_READ_MUTANTS", None)
        jobs.append((words, subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=TREE, env=env,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)))
        if len([j for j in jobs if j[1].poll() is None]) >= 4:
            jobs[-4][1].wait()
    missed = []
    for words, p in jobs:
        out = p.communicate(timeout=1800)[0].decode("utf-8", "replace")
        fell = [ln for ln in out.splitlines() if ln.startswith("FAIL ")]
        print("    · мутант помощника «%s»: %s" % (words, (fell[0][:160] if fell else "НЕ ПОЙМАН")))
        if p.returncode == 0 or not fell:
            missed.append((words, out[-600:]))
    print("  · мутантов помощника %d; не пойманы: %d" % (len(HELPER_MUTANTS), len(missed)))
    assert not missed, missed


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)
             and (not ONLY or n in ONLY)]
    bad = 0
    t0 = time.time()
    print("временный каталог: %s%s" % (TMP, (" · мутант: " + SRC) if SRC else ""))
    for name, fn in tests:
        t1 = time.time()
        try:
            fn()
            print("PASS", name, "(%.1f с)" % (time.time() - t1))
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:600])
    print("ИТОГ %d/%d (%.1f с)" % (len(tests) - bad, len(tests), time.time() - t0))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
