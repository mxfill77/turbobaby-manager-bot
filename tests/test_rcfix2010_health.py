#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RCFIX2010 C · PARKSEEN (Codex TB-QA-2110-0006-PARKSEEN, вариант B; вопрос K3-2110-0006-QB): health ВИДИТ простой
Splinter.

Повод: под 410a839 bot.main() при входе выпуска MISMATCH/UNKNOWN печатает ОДНУ строку [ERROR] «🚦 вход выпуска: …» и
простаивает (_park_until_stop): обработчиков, задач и опроса нет, бот молчит. Прежний health искал «Bot polling started»
последним совпадением по ВСЕМУ неротированному splinter.log — строка прошлого запуска проходила, одна строка [ERROR]
давала «⚠️ РАБОТАЕТ, но 1 ошибок», code 0, и пуш (только при code ≠ 0) не уходил. Теперь polling судится в границе
ТЕКУЩЕГО запуска: MainPID + ExecMainStartTimestamp юнита (два чтения вокруг чтения журнала), строка входа выпуска этого
запуска и его polling.

Разделы:
  A — адресные случаи Codex на настоящих build_report()/main(): журнал — настоящий файл во временном каталоге, строки —
      настоящий logging.Formatter формата bot.py:73 (UTC, логгер «turbobaby», сообщение «  » + строка входа), строки
      входа — настоящий splinter.release_entry; systemctl — подмена subprocess.run с выводом в порядке живого образца
      (docs/artifacts/2026-08-16-rule-delivery-check.md:24–31, «Ddd YYYY-MM-DD HH:MM:SS UTC»); сеть (мост, мозг, кредит,
      WA, git) — заглушки:
        a1 старый polling + новый простой MISMATCH → ❌ code 1, слово «ПРОСТОЙ», один пуш; контрфакт — прежний
           check_polling (дословно health.py@410a839:162–164) на том же входе даёт «⚠️ РАБОТАЕТ, но 1 ошибок», code 0;
        a2 то же для UNKNOWN (флаги не прочитаны) и «сбой проверки»;
        a3 нормальный текущий запуск (release, truth_off) → отчёт посимвольно прежний, кроме строки Polling; пуша нет;
        a4 граница недоступна (исключение, код ≠ 0, пусто, MainPID 0, метка ''/n/a/не UTC, нет NRestarts) → НЕИЗВЕСТНО;
        a5 граница сменилась между чтениями (PID / старт / NRestarts / ActiveState) → НЕИЗВЕСТНО;
        a6 нет polling текущего запуска / нет ни входа, ни polling / запуск моложе 300 с / polling без строки входа;
        a7 прежние случаи health (кредит и его дедуп, Brain, ошибки, мост, WA, сервис не active) не изменились;
        a8 цикл падений ПОСЛЕ строки polling (verify3 x1: bot.py:1778 печатает её до app.run_polling :1779), текущему
           запуску 3 с, NRestarts 57 → НЕИЗВЕСТНО, code 1, один пуш; прежний check_polling — «✅ ВСЁ ОК»; порог 300 с;
  B — чистая _run_verdict: неоднозначность, противоречия, уровни, окно 300 с, часы и пояс, строгость якоря, продолжения;
  C — доставка: notify True → «отправлен (Telegram ok)»; False / None / исключение → «доставка не подтверждена (НЕ
      отправлен … неизвестно) … повтора нет»; вызов ровно один; код возврата прежний; настоящего notify нет;
  D — замки: копии health ↔ splinter (_ENTRY_HEAD, имена RELEASE_ENTRY_STATES, RELEASE_FLAG_KEYS); формат и строки
      bot.py; health не импортирует splinter; сетка всех строк release_entry ⇔ вердикт health; храповик слепых;
      _read_run на живом формате (порядок ключей, лишние ключи) и его вызов;
  Z — мутанты (RCFIX2010_MUTANTS=1, как в test_rcfix2010_tuple.py): каждый роняет хотя бы одну проверку своего места,
      нулевой зелёный.
Сети, systemctl, Telegram, мозга и боевых файлов нет: notify — заглушка в sys.modules (плюс NOTIFY_COUNT_FILE во
временном каталоге — проверяется, что он так и не появился), dotenv и bridge_client — заглушки (настоящий файл окружения
не читается), файл эпизода кредита health — во временном каталоге.
Прогон: venv/Scripts/python.exe tests/test_rcfix2010_health.py → «ИТОГ N/M»."""
import ast
import contextlib
import datetime as _dt
import io
import itertools
import logging
import os
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.environ.get("RCFIX_HEALTH_SRC", "")         # мутант / «до правки»: каталог с подменённым health.py
ONLY = [x for x in os.environ.get("RCFIX_HEALTH_ONLY", "").split(",") if x]
sys.path.insert(0, ROOT)
if SRC:
    sys.path.insert(0, SRC)

KEYS = ("INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN", "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS")
STRICT, GEN, TRUTH, ACCR, HOF = KEYS
for _f in KEYS + ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB"):
    os.environ.pop(_f, None)

TMP = tempfile.mkdtemp(prefix="rcfix_health_")
COUNT_FILE = os.path.join(TMP, "notify_count.txt")
os.environ["NOTIFY_COUNT_FILE"] = COUNT_FILE          # страховка: настоящий notify сети не тронет (count-режим)
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["BRIDGE_URL"] = "http://x"
os.environ["BRIDGE_TOKEN"] = "x"
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),
                  ("SPEND_LEDGER_FILE", "spend_ledger.json")):
    os.environ[_k] = os.path.join(TMP, _name)
os.makedirs(os.path.join(TMP, "_default"), exist_ok=True)
os.environ["RESTART_HANDOFF_STATE"] = os.path.join(TMP, "_default", "restart_handoff.json")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


try:
    import fcntl  # noqa: F401
except ImportError:
    _stub("fcntl", flock=lambda *a, **k: None, LOCK_EX=2, LOCK_UN=8, LOCK_SH=1, LOCK_NB=4)


class _Any:
    def __init__(self, *a, **k):
        pass


_stub("dotenv", load_dotenv=lambda *a, **k: True)     # настоящий файл окружения не читается никогда
_stub("bridge_client", BridgeClient=lambda *a, **k: _Any(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())


class _NotifyStub:
    """notify(text, track, clear_first, force) → bool, как notify.py:207. Результат задаёт тест: True / False / None /
    исключение. Каждый вызов записывается — проверяется число вызовов за прогон."""

    def __init__(self):
        self.calls = []
        self.result = True

    def __call__(self, text, track=False, clear_first=False, force=False):
        self.calls.append({"text": text, "force": force, "track": track})
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


NOTIFY = _NotifyStub()
_stub("notify", notify=NOTIFY)

import health as H  # noqa: E402

_SPL = []


def S():
    """splinter — лениво (импорт тяжёлый; детям-мутантам без раздела D он не нужен)."""
    if not _SPL:
        import splinter
        _SPL.append(splinter)
    return _SPL[0]


INFO, WARNING, ERROR = logging.INFO, logging.WARNING, logging.ERROR
UTC = _dt.timezone.utc
BOT_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"          # дословно bot.py:73 (закреплено test_d2)
FMT = logging.Formatter(BOT_FMT)
FMT.converter = time.gmtime                                             # процесс бота и systemd — в UTC (69k:190–194)
POLL = "Bot polling started. Press Ctrl+C to stop."                     # дословно bot.py:1778
NOW = _dt.datetime(2026, 10, 21, 8, 0, 0, tzinfo=UTC).timestamp()
T_A = NOW - 3 * 86400 - 1234                                            # прошлый запуск: трое суток назад
T_B = NOW - 7200                                                        # текущий запуск: два часа назад
PID_A, PID_B = 1187731, 1249876


def dt(t):
    return _dt.datetime.fromtimestamp(t, UTC)


def L(t, level, msg, name="turbobaby", exc_info=None):
    """Строки журнала одной записи — настоящий Formatter формата bot.py (многострочные — с продолжениями без метки)."""
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


class _BadIter:
    def __iter__(self):
        raise RuntimeError("стенд")


# ---------------------------------------------------------------------------------------------------------------------
# Журнал: запуски в порядке bot.py — строки импорта (:94, :99, :101, :106/:109, :115), вход (:1662/:1665), при допуске
# «Scheduled …» (:1720–1769), polling (:1778), post_init (:1345–1365) и тики планировщика. Простой после строки входа
# не пишет НИЧЕГО (bot.py:1642–1655); SIGTERM обработчиков не имеет — строк остановки у простоя нет.
# ---------------------------------------------------------------------------------------------------------------------

def boot(t0, words):
    out = []
    out += L(t0 + 0.912, INFO, "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)")
    out += L(t0 + 0.931, INFO, "  Топики: ✅ привязок тема→байк из memory.db загружено: 14")
    out += L(t0 + 0.944, INFO, "  Инфо-кнопки: ✅ закрепов из memory.db загружено: 9")
    if words is None:
        out += L(t0 + 0.951, WARNING, "  🧩 флаги выпуска: НЕ ПРОЧИТАНЫ (KeyError)")
    else:
        out += L(t0 + 0.951, INFO, "  " + S().release_flags_line(words))
    out += L(t0 + 0.968, INFO, "  Auditor LLM: ✅ надзор логики для групп [-1001234567890]; канал правок «Аудит»=off")
    return out


def tail_ok(t0, poll_at=1.247, post=True):
    out = []
    out += L(t0 + 1.021, INFO, "Scheduled daily pulse at 09:00 Asia/Bangkok")
    out += L(t0 + 1.024, INFO, "Scheduled audit report at 09:30")
    out += L(t0 + 1.027, INFO, "Scheduled devbot orchestrator result reporting every 45s")
    out += L(t0 + 1.031, INFO, "Scheduled service-pending (ТО заявки) reminder every 1h")
    if poll_at is not None:
        out += L(t0 + poll_at, INFO, POLL)
    if post:
        out += L(t0 + 1.402, INFO, "=" * 60)
        out += L(t0 + 1.403, INFO, "TurboBaby Manager Bot — STARTING")
        out += L(t0 + 1.404, INFO, "  Timezone: Asia/Bangkok")
        out += L(t0 + 1.405, INFO, "  🔁 передача карточек: нечего передавать")
        out += L(t0 + 1.611, INFO, "  Bridge: ✅ alive (v1.0.0)")
        out += L(t0 + 1.702, INFO, "Scheduler started", name="apscheduler.scheduler")
        out += L(t0 + 46.0, INFO, 'Running job "devbot_report (trigger: interval[0:00:45], next run at: '
                                  '2026-10-21 06:01:31 UTC)" (scheduled at 2026-10-21 06:00:46.000000+00:00)',
                 name="apscheduler.executors.default")
    return out


def errors_after(t0, n):
    out = []
    for i in range(n):
        if i == 0:
            out += L(t0 + 600 + i, ERROR, "Splinter [intake] сбой разбора листа", name="splinter", exc_info=_exc())
        else:
            out += L(t0 + 600 + 60 * i, ERROR, "Splinter [ops] таймаут моста (read_doc)", name="splinter")
    return out


def run_ok(t0, words=None, unit=frozenset(), poll_at=1.247, post=True, errors=0):
    words = words_of() if words is None else words
    state, line = S().release_entry(words, unit)
    assert state is not None, line
    return boot(t0, words) + L(t0 + 1.003, INFO, "  " + line) + tail_ok(t0, poll_at, post) + errors_after(t0, errors)


def run_park(t0, words, unit=frozenset()):
    state, line = S().release_entry(words, unit)
    assert state is None, line
    return boot(t0, None if words is None or isinstance(words, _BadIter) else words) + L(t0 + 1.003, ERROR, "  " + line)


def run_old(t0, poll=True, stop=True):
    """Запуск ПРЕЖНЕГО кода (947953e): строки входа выпуска нет, polling есть; штатная остановка — строка
    планировщика."""
    out = L(t0 + 0.9, INFO, "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)")
    out += L(t0 + 0.95, INFO, "  🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · "
                              "CONTRACT_REF_GEN=ВЫКЛ (не задан)")
    out += L(t0 + 0.97, INFO, "  Auditor LLM: ✅ надзор логики для групп [-1001234567890]; канал правок «Аудит»=off")
    out += L(t0 + 1.02, INFO, "Scheduled daily pulse at 09:00 Asia/Bangkok")
    if poll:
        out += L(t0 + 1.21, INFO, POLL)
        out += L(t0 + 1.40, INFO, "TurboBaby Manager Bot — STARTING")
    out += errors_after(t0, 3)
    if stop:
        out += L(t0 + 86000.5, INFO, "Scheduler has been shut down", name="apscheduler.scheduler")
    return out


def history():
    """Прошлый запуск НОВОГО кода (вход OK, polling, ошибки) — журнал не ротируется (health.py: «копит все запуски»)."""
    return run_ok(T_A, errors=4) + L(T_A + 86000.5, INFO, "Scheduler has been shut down", name="apscheduler.scheduler")


# ---------------------------------------------------------------------------------------------------------------------
# systemctl: вывод `systemctl show` в порядке живого образца, только запрошенные ключи; `is-active` — слово и код.
# ---------------------------------------------------------------------------------------------------------------------
SYSTEMD_ORDER = ("ActiveState", "SubState", "FragmentPath", "ActiveEnterTimestamp", "MainPID", "NRestarts",
                 "ExecMainStartTimestamp", "ExecMainStartTimestampMonotonic")
_WD = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def stamp(t, tz="UTC", shift_h=0):
    tm = time.gmtime(int(t) + shift_h * 3600)
    return "%s %s %s" % (_WD[tm.tm_wday], time.strftime("%Y-%m-%d %H:%M:%S", tm), tz)


def props_of(pid, t0, nrestarts=0, active="active", sub="running", ts=None):
    st = stamp(t0) if ts is None else ts
    return {"ActiveState": active, "SubState": sub, "FragmentPath": "/etc/systemd/system/splinter.service",
            "ActiveEnterTimestamp": st, "MainPID": str(pid), "NRestarts": str(nrestarts),
            "ExecMainStartTimestamp": st, "ExecMainStartTimestampMonotonic": "2011920081825"}


class FakeSystemd:
    """subprocess.run для systemctl. runs — снимки свойств по очереди ЧТЕНИЙ ГРАНИЦЫ (вызовы с MainPID); check_service
    (SubState,NRestarts,ExecMainStartTimestamp) видит последний выданный. mode: None | 'raise' | 'rc1' | 'empty'."""

    def __init__(self, runs, is_active="active", mode=None):
        self.runs = list(runs)
        self.is_active = is_active
        self.mode = mode
        self.calls = []
        self.bound_reads = 0

    def __call__(self, cmd, capture_output=False, text=False, timeout=None, **kw):
        self.calls.append(list(cmd))
        assert capture_output and text and timeout, cmd
        if cmd[0] != "systemctl":
            raise FileNotFoundError(2, "No such file or directory", cmd[0])
        if self.mode == "raise":
            raise FileNotFoundError(2, "No such file or directory", "systemctl")
        if self.mode == "rc1":
            return subprocess.CompletedProcess(cmd, 1, "", "Failed to connect to bus: No such file or directory\n")
        if cmd[1] == "is-active":
            return subprocess.CompletedProcess(cmd, 0 if self.is_active == "active" else 3, self.is_active + "\n", "")
        assert cmd[1] == "show" and cmd[2] == "splinter" and cmd[3].startswith("--property="), cmd
        req = cmd[3].split("=", 1)[1].split(",")
        if "MainPID" in req:
            props = self.runs[min(self.bound_reads, len(self.runs) - 1)]
            self.bound_reads += 1
        else:
            props = self.runs[min(max(self.bound_reads - 1, 0), len(self.runs) - 1)]
        if self.mode == "empty":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        out = "".join("%s=%s\n" % (k, props[k]) for k in SYSTEMD_ORDER if k in req and k in props)
        return subprocess.CompletedProcess(cmd, 0, out, "")


NET = dict(check_bridge=lambda *a, **k: (True, "alive v1.0.0"),
           check_brain_latency=lambda *a, **k: (False, "cc_log 1.1с; review 1.0с; project_state 20.3с; "
                                                       "knowledge_base 18.0с"),
           check_api_credit=lambda *a, **k: (False, "кредит ок (1-токенная проба прошла)"),
           check_commit=lambda *a, **k: (True, "410a839 2026-10-20 12:00:00 +0000 rc-2010-c"),
           check_wa_webhook=lambda *a, **k: (True, "active, handshake 200/probe42, очередь new=0"))
_EP = itertools.count()


@contextlib.contextmanager
def world(lines, runs, now=NOW, is_active="active", mode=None, episode=None, **over):
    path = os.path.join(TMP, "splinter.log")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)
    fake = FakeSystemd(runs, is_active, mode)
    stubs = dict(NET)
    stubs.update(over)
    with contextlib.ExitStack() as st:
        st.enter_context(mock.patch.object(H, "LOG", path))
        st.enter_context(mock.patch.object(H, "_utcnow", lambda: dt(now)))
        st.enter_context(mock.patch.object(H.subprocess, "run", fake))
        st.enter_context(mock.patch.object(H, "_CREDIT_EPISODE_FILE",
                                           episode or os.path.join(TMP, "credit_episode_%d" % next(_EP))))
        for k, v in stubs.items():
            st.enter_context(mock.patch.object(H, k, v))
        yield fake


class Rep:
    def __init__(self, report, summary, code, fake):
        self.report, self.summary, self.code, self.fake = report, summary, code, fake

    def row(self, name):
        for ln in self.report.split("\n"):
            if ln.startswith(("✅ " + name, "❌ " + name)):
                return ln
        return None


def build(lines, runs, **kw):
    with world(lines, runs, **kw) as fake:
        report, summary, code, _bw, _cw = H.build_report()
    return Rep(report, summary, code, fake)


def run_main(lines, runs, argv=("--push",), result=True, **kw):
    NOTIFY.calls.clear()
    NOTIFY.result = result
    buf = io.StringIO()
    with world(lines, runs, **kw):
        with contextlib.redirect_stdout(buf):
            rc = H.main(list(argv))
    return rc, buf.getvalue(), list(NOTIFY.calls)


def old_check_polling(lines, *a, **k):
    """Прежний check_polling — дословно health.py@410a839:162–164 (последнее совпадение по всему журналу)."""
    p = H._last_match(lines, "Bot polling started")
    return (bool(p), "Bot polling started" if p else "нет «Bot polling started» в логе")


def B(t0=T_B, pid=PID_B, **kw):
    p = props_of(pid, t0, **kw)
    return [p, p]


def run_of(props):
    with mock.patch.object(H.subprocess, "run", FakeSystemd([props])):
        return H._read_run()


def verdict(lines, t0=T_B, now=NOW):
    r = run_of(props_of(PID_B, t0))
    assert r is not None
    return H._run_verdict(lines, r, r, dt(now))


def same_except_polling(new, old):
    a = [ln for ln in new.report.split("\n") if not ln.startswith(("✅ Polling", "❌ Polling"))]
    b = [ln for ln in old.report.split("\n") if not ln.startswith(("✅ Polling", "❌ Polling"))]
    return a == b and new.summary == old.summary and new.code == old.code


# ======================================================================================================================
# A. Адресные случаи Codex на настоящем build_report()/main().
# ======================================================================================================================

def test_a1_old_polling_new_park_mismatch():
    """Старый polling (прошлый запуск нового И прежнего кода) + текущий простой MISMATCH (STRICT=0 строкой)."""
    for hist in (history(), run_old(T_A)):
        lines = hist + run_park(T_B, words_of(**{STRICT: "0"}))
        r = build(lines, B())
        assert r.code == 1, (r.code, r.summary)
        assert r.summary.startswith("❌ ПРОБЛЕМА: ") and "ПРОСТОЙ Splinter" in r.summary, r.summary
        assert "вход выпуска MISMATCH" in r.summary and "INTAKE_CONFIRM_STRICT MISMATCH" in r.summary, r.summary
        assert "PID %d" % PID_B in r.summary and "бот молчит" in r.summary, r.summary
        assert r.row("Polling").startswith("❌ Polling"), r.row("Polling")
        assert r.fake.bound_reads == 2, r.fake.calls          # граница читалась ДВАЖДЫ (до и после журнала)
        # контрфакт: прежний check_polling на ТОМ ЖЕ входе — зелёный polling и «⚠️ РАБОТАЕТ, но 1 ошибок», code 0
        old = build(lines, B(), check_polling=old_check_polling)
        assert old.code == 0 and old.summary == "⚠️ РАБОТАЕТ, но 1 ошибок в логе с старта — стоит глянуть", old.summary
        assert old.row("Polling") == "✅ Polling         Bot polling started", old.row("Polling")
        rc, out, calls = run_main(lines, B())
        assert rc == 1 and len(calls) == 1 and calls[0]["force"] is True, (rc, calls)
        assert "ПРОСТОЙ Splinter" in calls[0]["text"] and "[push] отправлен (Telegram ok)" in out, out[-300:]
        rc0, _out0, calls0 = run_main(lines, B(), check_polling=old_check_polling)
        assert rc0 == 0 and calls0 == [], (rc0, calls0)      # прежде: пуша не было вовсе
    print("    · простой MISMATCH: ❌ code 1 и один пуш; прежний check_polling на том же журнале: ⚠️ code 0, пушей 0")
    print("      стало: %s" % r.summary)
    print("      было:  %s" % old.summary)


def test_a2_old_polling_new_park_unknown():
    """Простой UNKNOWN: флаги не прочитаны (bot.py:109 → _RELEASE_WORDS=None) и «сбой проверки»; ручка UNKNOWN."""
    for words, word in ((None, "UNKNOWN"), (_BadIter(), "UNKNOWN"), (words_of(**{STRICT: "maybe"}), "UNKNOWN")):
        lines = history() + run_park(T_B, words)
        r = build(lines, B())
        assert r.code == 1 and "ПРОСТОЙ Splinter: вход выпуска " + word in r.summary, r.summary
        rc, out, calls = run_main(lines, B())
        assert rc == 1 and len(calls) == 1, (rc, calls)
        old = build(lines, B(), check_polling=old_check_polling)
        assert old.code == 0, old.summary


def test_a3_normal_current_run_as_before():
    """Нормальный текущий запуск — отчёт посимвольно прежний (кроме строки Polling), итог прежний, пуша нет."""
    cases = (("release, ошибки", run_ok(T_B, errors=3), "⚠️ РАБОТАЕТ, но "),
             ("release, без ошибок", run_ok(T_B), "✅ ВСЁ ОК"),
             ("truth_off (CLOSE_TRUTH=0 юнитом)", run_ok(T_B, words_of(**{TRUTH: "0"}), frozenset({TRUTH}), errors=1),
              "⚠️ РАБОТАЕТ, но "))
    for name, cur, want in cases:
        lines = history() + cur
        r = build(lines, B())
        assert r.code == 0 and r.summary.startswith(want), (name, r.summary)
        st = "truth_off" if "truth_off" in name else "release"
        want_row = ("✅ Polling         вход выпуска OK (%s) · Bot polling started · PID %d, старт %s UTC, "
                    "рестартов 0" % (st, PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S")))
        assert r.row("Polling") == want_row, r.row("Polling")
        old = build(lines, B(), check_polling=old_check_polling)
        assert same_except_polling(r, old), (name, r.report, old.report)
        rc, out, calls = run_main(lines, B())
        assert rc == 0 and calls == [] and "[push]" not in out, (name, rc, calls)
    print("    · нормальный запуск: 3 варианта, отчёт = прежний кроме строки Polling, пушей 0")


def test_a4_boundary_unavailable_is_unknown():
    """Граница не прочитана — НЕИЗВЕСТНО, code 1, пуш; валидный старый И текущий журнал не спасают."""
    lines = history() + run_ok(T_B, errors=2)
    p = props_of(PID_B, T_B)
    variants = (("systemctl не запустился", dict(mode="raise")),
                ("код ≠ 0", dict(mode="rc1")),
                ("пустой вывод", dict(mode="empty")),
                ("MainPID=0", dict(runs=[dict(p, MainPID="0")] * 2)),
                ("метка пустая", dict(runs=[dict(p, ExecMainStartTimestamp="")] * 2)),
                ("метка n/a", dict(runs=[dict(p, ExecMainStartTimestamp="n/a")] * 2)),
                ("пояс не UTC", dict(runs=[dict(p, ExecMainStartTimestamp=stamp(T_B, "+07", 7))] * 2)),
                ("нет NRestarts", dict(runs=[{k: v for k, v in p.items() if k != "NRestarts"}] * 2)),
                ("MainPID не число", dict(runs=[dict(p, MainPID="[not set]")] * 2)))
    for name, kw in variants:
        runs = kw.pop("runs", [p, p])
        r = build(lines, runs, **kw)
        assert r.code == 1, (name, r.summary)
        assert "запуск не доказан — НЕИЗВЕСТНО: граница запуска не прочитана" in r.summary, (name, r.summary)
        assert r.row("Polling").startswith("❌ Polling"), (name, r.row("Polling"))
        rc, _out, calls = run_main(lines, runs, **kw)
        assert rc == 1 and len(calls) == 1, (name, rc, calls)
    print("    · граница недоступна: %d вариантов → НЕИЗВЕСТНО, code 1, один пуш" % len(variants))


def test_a5_boundary_changed_between_reads():
    lines = history() + run_ok(T_B)
    p = props_of(PID_B, T_B)
    for name, p1 in (("PID", dict(p, MainPID=str(PID_B + 7))),
                     ("старт", dict(p, ExecMainStartTimestamp=stamp(T_B + 1))),
                     ("NRestarts", dict(p, NRestarts="1")), ("ActiveState", dict(p, ActiveState="deactivating"))):
        r = build(lines, [p, p1])
        assert r.code == 1 and "граница запуска сменилась во время чтения журнала" in r.summary, (name, r.summary)
        assert "НЕИЗВЕСТНО" in r.summary, r.summary


def test_a6_no_current_polling():
    # (а) вход OK, polling нет, запуску 2 ч
    r = build(history() + run_ok(T_B, poll_at=None, post=False), B())
    assert r.code == 1 and "вход выпуска OK (release), но нет polling текущего запуска" in r.summary, r.summary
    # (б) в текущем запуске ни входа, ни polling (завис импорт) — есть только строки прошлого запуска
    hung = L(T_B + 0.4, INFO, "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)")
    r = build(history() + hung, B())
    assert r.code == 1 and "нет строки «вход выпуска» и polling текущего запуска" in r.summary, r.summary
    # (в) запуск моложе 300 с, строки входа ещё нет
    r = build(history(), B(), now=T_B + 120)
    assert r.code == 1 and "НЕИЗВЕСТНО: запуск моложе 300 с" in r.summary, r.summary
    # (г) текущий процесс — прежний код: polling есть, строки входа нет (смешанное состояние диска и процесса)
    r = build(history() + run_old(T_B, stop=False), B())
    assert r.code == 1 and "polling текущего запуска без строки «вход выпуска»" in r.summary, r.summary
    # (д) журнал пуст / не читается
    r = build([], B())
    assert r.code == 1 and "нет строки «вход выпуска» и polling текущего запуска" in r.summary, r.summary
    with mock.patch.object(H, "_read_log_lines", lambda: []):
        r = build(history() + run_ok(T_B), B())
    assert r.code == 1 and "Polling" in r.report and r.row("Polling").startswith("❌"), r.summary


def test_a7_prior_cases_unchanged():
    """Кредит, Brain, ошибки, мост, WA, сервис не active — как прежде (сверка с прежним check_polling на том же
    входе)."""
    lines = history() + run_ok(T_B, errors=2)
    cases = (
        ("кредит", dict(check_api_credit=lambda *a, **k: (True, "❗кредит платного ключа на нуле (BadRequestError)")),
         0, "⚠️ Кредит платного ключа на нуле"),
        ("Brain", dict(check_brain_latency=lambda *a, **k: (True, "cc_log 14с⚠️(>10)")), 0,
         "⚠️ Brain-док читается медленно"),
        ("ошибки", {}, 0, "⚠️ РАБОТАЕТ, но "),
        ("мост", dict(check_bridge=lambda *a, **k: (False, "TimeoutError (после 3 попыток)")), 1,
         "❌ ПРОБЛЕМА: Bridge не отвечает"),
        ("WA отказ", dict(check_wa_webhook=lambda *a, **k: (False, "active, PROBE FAIL: HTTP 502")), 1,
         "❌ ПРОБЛЕМА: WA webhook не отвечает"),
        ("WA не настроен", dict(check_wa_webhook=lambda *a, **k: (None, "не настроен (WA_VERIFY_TOKEN не задан)")), 0,
         "⚠️ РАБОТАЕТ, но "),
    )
    for name, over, code, head in cases:
        r = build(lines, B(), **over)
        old = build(lines, B(), check_polling=old_check_polling, **over)
        assert r.code == code and r.summary.startswith(head), (name, r.summary)
        assert same_except_polling(r, old), (name, r.report, old.report)
    # Brain → один пуш; кредит — один пуш на эпизод (второй прогон молчит), выздоровление закрывает эпизод
    rc, _o, calls = run_main(lines, B(), check_brain_latency=lambda *a, **k: (True, "cc_log 14с⚠️(>10)"))
    assert rc == 0 and len(calls) == 1, calls
    ep = os.path.join(TMP, "credit_episode_dedup")
    cw = dict(check_api_credit=lambda *a, **k: (True, "❗кредит платного ключа на нуле (BadRequestError)"))
    rc1, _o, c1 = run_main(lines, B(), episode=ep, **cw)
    rc2, _o, c2 = run_main(lines, B(), episode=ep, **cw)
    assert (rc1, len(c1), rc2, len(c2)) == (0, 1, 0, 0), (rc1, c1, rc2, c2)
    run_main(lines, B(), episode=ep)
    assert not os.path.exists(ep), "эпизод кредита не закрылся"
    # сервис не active: прежняя проблема «Splinter не active» на месте (+ запуск не доказан)
    r = build(lines, [dict(props_of(PID_B, T_B), ActiveState="inactive", SubState="dead", MainPID="0")] * 2,
              is_active="inactive")
    assert r.code == 1 and "Splinter не active" in r.summary and "НЕИЗВЕСТНО" in r.summary, r.summary
    # --push-always на нормальном запуске — один пуш, как прежде
    rc, out, calls = run_main(history() + run_ok(T_B), B(), argv=("--push-always",))
    assert rc == 0 and len(calls) == 1 and "[push] отправлен (Telegram ok)" in out, (rc, calls, out[-200:])


# Необработанное исключение из app.run_polling (bot.py:1779): Python печатает его в stderr МИМО logging — строки без
# метки, они наследуют метку прошлой строки (форма — out/verify3_health_attack/test_v3_health_attack.py: tb_lines).
CRASH_TB = ["Traceback (most recent call last):\n",
            '  File "/root/turbobaby-manager-bot/bot.py", line 1783, in <module>\n',
            "    main()\n",
            '  File "/root/turbobaby-manager-bot/bot.py", line 1779, in main\n',
            "    app.run_polling(allowed_updates=Update.ALL_TYPES)\n",
            "telegram.error.TimedOut: Timed out\n"]


def test_a8_crash_loop_after_polling_line():
    """verify3 x1: юнит в цикле падений ПОСЛЕ строки «Bot polling started» (initialize/get_me/post_init падают в
    run_polling, Restart=always поднимает новый процесс через 10 с). Три прошлых цикла «вход OK → polling → Traceback»
    и текущий запуск 3 с, NRestarts 57: бот не обслуживает, а прежде было «✅ ВСЁ ОК», code 0, пушей 0 (ошибки прошлых
    циклов отсечены границей старта — Traceback наследует их метку)."""
    s_cur = int(NOW) - 3
    lines = history()
    for k in (3, 2, 1):
        lines += run_ok(s_cur - 17 * k, post=False) + CRASH_TB
    lines += run_ok(s_cur, post=False)                     # вход OK и polling на +1.247 с; падения ещё не видно
    runs = B(t0=s_cur, pid=PID_B + 57, nrestarts=57)
    r = build(lines, runs)
    assert r.code == 1, (r.code, r.summary)
    assert ("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: запуск моложе 300 с — устойчивость запуска не доказана"
            in r.summary and "рестартов 57" in r.summary), r.summary
    assert r.row("Polling").startswith("❌ Polling"), r.row("Polling")
    rc, out, calls = run_main(lines, runs)
    assert rc == 1 and len(calls) == 1 and "моложе 300 с" in calls[0]["text"], (rc, calls)
    # контрфакт: прежний check_polling на том же журнале — зелёный, пуша нет
    old = build(lines, runs, check_polling=old_check_polling)
    assert old.code == 0 and old.summary == "✅ ВСЁ ОК", old.summary
    # порог: тот же запуск без падения — в 299 с ещё НЕИЗВЕСТНО, в 300 с прежний зелёный (отчёт = прежний, кроме Polling)
    calm = history() + run_ok(s_cur, post=False)
    r299 = build(calm, B(t0=s_cur), now=s_cur + 299)
    assert r299.code == 1 and "запуск моложе 300 с — устойчивость" in r299.summary, r299.summary
    r300 = build(calm, B(t0=s_cur), now=s_cur + 300)
    assert r300.code == 0 and r300.summary == "✅ ВСЁ ОК", r300.summary
    assert same_except_polling(r300, build(calm, B(t0=s_cur), now=s_cur + 300, check_polling=old_check_polling))
    print("    · цикл падений после polling (NRestarts 57, запуску 3 с): ❌ code 1, один пуш; прежде: %s" % old.summary)


# ======================================================================================================================
# B. Чистая _run_verdict.
# ======================================================================================================================

def test_b1_ambiguity_and_contradictions():
    ok_line = S().release_entry(words_of(), frozenset())[1]
    park_line = S().release_entry(words_of(**{GEN: "1"}), frozenset())[1]
    t = T_B
    cases = (
        ("два входа", boot(t, words_of()) + L(t + 1.0, INFO, "  " + ok_line) + L(t + 1.1, INFO, "  " + ok_line)
         + L(t + 1.2, INFO, POLL), "граница неоднозначна: строк «вход выпуска»"),
        ("два polling", run_ok(t) + L(t + 2.0, INFO, POLL), "граница неоднозначна: polling"),
        ("polling после простоя", run_park(t, words_of(**{GEN: "1"})) + L(t + 1.3, INFO, POLL),
         "противоречие: вход выпуска MISMATCH, а polling"),
        ("polling до входа", boot(t, words_of()) + L(t + 0.99, INFO, POLL) + L(t + 1.0, INFO, "  " + ok_line),
         "противоречие: polling раньше строки"),
        ("OK под ERROR", L(t + 1.0, ERROR, "  " + ok_line) + L(t + 1.2, INFO, POLL), "уровень ERROR не сходится"),
        ("MISMATCH под INFO", L(t + 1.0, INFO, "  " + park_line), "уровень INFO не сходится"),
        ("OK без пяти ручек", L(t + 1.0, INFO, "  🚦 вход выпуска: OK — состояние release") + L(t + 1.2, INFO, POLL),
         "не по грамматике"),
        ("неизвестное состояние", L(t + 1.0, INFO, "  " + ok_line.replace("состояние release", "состояние hofacts_on"))
         + L(t + 1.2, INFO, POLL), "не по грамматике"),
        ("простой без хвоста", L(t + 1.0, ERROR, "  🚦 вход выпуска: MISMATCH — INTAKE_CONFIRM_STRICT MISMATCH"),
         "не по грамматике"),
    )
    for name, lines, want in cases:
        st, why = verdict(lines)
        assert st == "UNKNOWN" and want in why, (name, st, why)


def test_b2_window_and_clock():
    t = T_B
    ok_line = S().release_entry(words_of(), frozenset())[1]
    # вход позже старта больше чем на 300 с (сдвиг пояса на часы / долгий импорт) → НЕИЗВЕСТНО
    st, why = verdict(L(t + 301, INFO, "  " + ok_line) + L(t + 301.2, INFO, POLL))
    assert st == "UNKNOWN" and "строка «вход выпуска» позже старта больше чем на 300 с" in why, why
    park_line = S().release_entry(words_of(**{STRICT: "0"}), frozenset())[1]
    st, why = verdict(L(t + 301, ERROR, "  " + park_line))           # простой за окном — не «простой», а НЕИЗВЕСТНО
    assert st == "UNKNOWN" and "строка «вход выпуска» позже старта больше чем на 300 с" in why, why
    assert verdict(L(t + 299, ERROR, "  " + park_line))[0] == "PARKED"
    st, _ = verdict(L(t + 299, INFO, "  " + ok_line) + L(t + 299.5, INFO, POLL))
    assert st == "OK", st
    st, why = verdict(L(t + 1, INFO, "  " + ok_line) + L(t + 400, INFO, POLL))
    assert st == "UNKNOWN" and "polling позже старта" in why, why
    # последняя строка впереди часов на 2 ч → НЕИЗВЕСТНО
    st, why = verdict(run_ok(t) + L(NOW + 7200, INFO, "Splinter [ops] тик", name="splinter"))
    assert st == "UNKNOWN" and "впереди часов" in why, why
    # журнал в местном поясе +07 при systemd в UTC: все строки текущего запуска «впереди часов»
    st, why = verdict(run_ok(t + 7 * 3600))
    assert st == "UNKNOWN" and "впереди часов" in why, why
    # журнал позади UTC (−3 ч): текущий запуск выпадает из сегмента целиком → не зелёное
    st, why = verdict(history() + run_ok(t - 3 * 3600))
    assert st == "NO_POLL", (st, why)
    # старт юнита впереди часов
    r = run_of(props_of(PID_B, NOW + 3600))
    assert H._run_verdict(run_ok(NOW + 3600), r, r, dt(NOW))[0] == "UNKNOWN"


def test_b3_same_second_as_start():
    """Строка в ту же секунду, что старт (точность ExecMainStartTimestamp — секунда), — текущему запуску; секундой
    раньше — прошлому; polling прошлого процесса в ту же секунду — «ровно одна» ловит."""
    t = T_B
    ok_line = S().release_entry(words_of(), frozenset())[1]
    cur = L(t + 0.12, INFO, "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)") \
        + L(t + 0.4, INFO, "  " + ok_line) + L(t + 0.62, INFO, POLL)
    assert verdict(L(t - 0.5, INFO, POLL) + cur)[0] == "OK"
    st, why = verdict(L(t + 0.05, INFO, POLL) + cur)
    assert st == "UNKNOWN" and "противоречие: polling раньше" in why, why


def test_b4_strict_anchor_and_continuations():
    t = T_B
    ok_line = S().release_entry(words_of(), frozenset())[1]
    quote_poll = L(t + 5, INFO, "Splinter [ops] ответ dev-боту: ✅ Polling         Bot polling started")
    cont_poll = ["Bot polling started. Press Ctrl+C to stop.\n"]
    other_logger = L(t + 6, INFO, POLL, name="devbot")
    one_space = ["%s [INFO] turbobaby: Bot polling started. Press Ctrl+C to stop.\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(t) + 7)) + ",000 ")]
    base = boot(t, words_of()) + L(t + 1.0, INFO, "  " + ok_line) + tail_ok(t, poll_at=None, post=False)
    for name, extra in (("цитата", quote_poll), ("продолжение без метки", cont_poll), ("чужой логгер", other_logger),
                        ("лишний пробел", one_space)):
        st, why = verdict(base + extra)
        assert st == "NO_POLL", (name, st, why)
    # вход внутри чужого сообщения — не вход
    quote_entry = L(t + 1.0, INFO, "Splinter [ops] текст группы: 🚦 вход выпуска: " + ok_line[len("🚦 вход выпуска: "):])
    st, _ = verdict(quote_entry + L(t + 1.2, INFO, POLL))
    assert st == "UNKNOWN", st                         # polling без строки входа
    # многострочный Traceback между входом и polling: продолжения наследуют метку, polling засчитан
    tb = L(t + 1.1, ERROR, "Splinter [intake] сбой", name="splinter", exc_info=_exc())
    assert len(tb) > 2 and not tb[1][:4].isdigit(), tb
    st, why = verdict(boot(t, words_of()) + L(t + 1.0, INFO, "  " + ok_line) + tb + L(t + 1.2, INFO, POLL))
    assert st == "OK", (st, why)
    # окончания строк CRLF (журнал, переписанный чужим инструментом) — тот же вердикт
    st, _ = verdict([ln.replace("\n", "\r\n") for ln in run_ok(t)])
    assert st == "OK", st


def test_b5_young_run():
    t = T_B
    st, why = verdict(run_ok(t, poll_at=None, post=False), now=t + 60)
    assert st == "UNKNOWN" and "моложе 300 с — polling ещё нет" in why, why
    st, why = verdict(run_park(t, words_of(**{STRICT: "0"})), now=t + 30)
    assert st == "PARKED", (st, why)                   # простой виден сразу: строка входа уже есть
    # вход OK и polling есть, но запуск моложе 300 с — НЕИЗВЕСТНО (строка polling печатается до app.run_polling)
    ok_run = run_ok(t, post=False)
    st, why = verdict(ok_run, now=t + 3)
    assert st == "UNKNOWN" and "моложе 300 с — устойчивость запуска не доказана" in why, (st, why)
    assert verdict(ok_run, now=t + 299)[0] == "UNKNOWN"
    assert verdict(ok_run, now=t + 300)[0] == "OK"
    # verify3 x5: вход и polling ПРЕЖНЕГО процесса в ту же секунду, что старт нового (метки — до секунды), новый ещё
    # импортируется → не OK по чужим строкам
    st, why = verdict(run_ok(t - 1.0, post=False), now=t + 1.2)
    assert st == "UNKNOWN" and "моложе 300 с" in why, (st, why)


# ======================================================================================================================
# C. Доставка уведомления.
# ======================================================================================================================

def test_c1_known_delivery():
    lines = history() + run_park(T_B, words_of(**{STRICT: "0"}))
    rc, out, calls = run_main(lines, B(), result=True)
    assert rc == 1 and len(calls) == 1, (rc, calls)
    assert "[push] отправлен (Telegram ok)" in out and "не подтверждена" not in out, out[-300:]


def test_c2_unknown_delivery_no_retry():
    lines = history() + run_park(T_B, words_of(**{STRICT: "0"}))
    for res in (False, None, 0, TimeoutError("timed out"), urllib.error.URLError("сеть"), OSError("сокет закрыт"),
                ImportError("нет модуля")):
        rc, out, calls = run_main(lines, B(), result=res)
        push = [ln for ln in out.split("\n") if ln.startswith("[push]")]
        assert rc == 1 and len(calls) == 1, (res, rc, calls)          # код прежний, вызов ровно один, повтора нет
        assert len(push) == 1, (res, push)
        p = push[0]
        assert p.startswith("[push] доставка не подтверждена (НЕ отправлен или ответ потерян — неизвестно)"), (res, p)
        assert p.endswith("— повтора нет") and "[push] отправлен (" not in out, (res, p)
        if isinstance(res, BaseException):
            assert type(res).__name__ in p, (res, p)
    print("    · доставка неизвестна: 7 исходов notify → «не подтверждена … повтора нет», вызов ровно один")


def test_c3_no_push_when_green_and_one_call_max():
    rc, out, calls = run_main(history() + run_ok(T_B), B(), argv=("--push",))
    assert rc == 0 and calls == [] and "[push]" not in out, (rc, calls)
    rc, out, calls = run_main(history() + run_ok(T_B), B(), argv=())
    assert rc == 0 and calls == [], calls
    rc, out, calls = run_main(history() + run_park(T_B, words_of(**{STRICT: "0"})), B(), argv=())
    assert rc == 1 and calls == [] and "[push]" not in out, calls     # без --push не пушит, как прежде
    # проблема + Brain + первый кредит сразу — всё равно ОДИН вызов
    rc, out, calls = run_main(history() + run_park(T_B, words_of(**{STRICT: "0"})), B(), result=False,
                              check_brain_latency=lambda *a, **k: (True, "cc_log ✗(timeout>10с)"),
                              check_api_credit=lambda *a, **k: (True, "❗кредит платного ключа на нуле (X)"))
    assert rc == 1 and len(calls) == 1, calls


def test_y_no_real_notify_attempt():
    """Настоящий notify не звался ни разу: файл мок-счётчика NOTIFY_COUNT_FILE так и не появился."""
    assert not os.path.exists(COUNT_FILE), open(COUNT_FILE, encoding="utf-8").read()[:300]
    assert sys.modules["notify"].notify is NOTIFY


# ======================================================================================================================
# D. Замки.
# ======================================================================================================================

def test_d1_copies_match_splinter():
    sp = S()
    assert H._ENTRY_HEAD == sp._ENTRY_HEAD, (H._ENTRY_HEAD, sp._ENTRY_HEAD)
    assert H._ENTRY_STATES == tuple(n for n, _a, _u in sp.RELEASE_ENTRY_STATES), H._ENTRY_STATES
    assert H._ENTRY_KEYS == sp.RELEASE_FLAG_KEYS == KEYS, H._ENTRY_KEYS
    assert sp._ENTRY_LIST == "перечень выпуска " + " | ".join(H._ENTRY_STATES), sp._ENTRY_LIST
    park = sp.release_entry(None, frozenset())[1]
    assert park.endswith("; " + H._ENTRY_PARK_TAIL), park


def test_d2_bot_source_formats():
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "basicConfig"]
    assert len(calls) == 1, len(calls)
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert isinstance(kw.get("format"), ast.Constant) and kw["format"].value == BOT_FMT, ast.dump(calls[0])
    assert "datefmt" not in kw and "filename" not in kw, sorted(kw)            # asctime «%Y-%m-%d %H:%M:%S,mmm», поток
    assert src.count('log = logging.getLogger("turbobaby")') == 1
    assert src.count('log.info("%s")' % POLL) == 1, "литерал polling bot.py:1778 изменился"
    assert src.count('log.error("  " + entry_line)') == 1 and src.count('log.info("  " + entry_line)') == 1
    main = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"][0]
    seg = ast.get_source_segment(src, main)
    assert seg.index('log.error("  " + entry_line)') < seg.index("_park_until_stop()") < seg.index(
        'log.info("  " + entry_line)') < seg.index('log.info("%s")' % POLL), "порядок вход → простой/допуск → polling"


def test_d3_health_does_not_import_splinter():
    tree = ast.parse(open(H.__file__, encoding="utf-8").read())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert "splinter" not in mods and "bot" not in mods, sorted(mods)


def test_d4_grid_release_entry_iff_health_verdict():
    """Все строки статуса splinter.release_entry на сетке слов (5 слов × 5 ручек × 3 набора ключей юнита + сбойные
    входы) на своём уровне: health OK ⇔ release_entry отдал состояние; иначе ПРОСТОЙ. Простой + polling — НЕИЗВЕСТНО;
    допуск без polling — нет polling; строка на чужом уровне — НЕИЗВЕСТНО."""
    sp = S()
    closed = ("ВКЛ (задан)", "ВКЛ (не задан)", "ВЫКЛ (задан)", "ВЫКЛ (не задан)", "НЕИЗВЕСТНО (стенд)")
    r = run_of(props_of(PID_B, T_B))
    now = dt(NOW)
    t = T_B + 1.0
    inputs = [tuple(zip(KEYS, combo)) for combo in itertools.product(closed, repeat=len(KEYS))]
    inputs += [words_of(**{ACCR: "1", TRUTH: "0"}), words_of(**{HOF: "enabled"}), None, 42, _BadIter(),
               tuple(reversed(words_of())), tuple(words_of())[:4]]
    n = {"OK": 0, "PARKED": 0}
    for i, words in enumerate(inputs):
        for unit in (frozenset(), frozenset({TRUTH}), frozenset(KEYS)):
            state, line = sp.release_entry(words, unit)
            entry = L(t, INFO if state else ERROR, "  " + line)
            st, why = H._run_verdict(entry + (L(t + 0.2, INFO, POLL) if state else []), r, r, now)
            assert st == ("OK" if state else "PARKED"), (words, sorted(unit), line, st, why)
            if state:
                assert "вход выпуска OK (%s)" % state in why, why
            n[st] += 1
            if i % 37 == 0:
                if state:
                    assert H._run_verdict(entry, r, r, now)[0] == "NO_POLL"
                    assert H._run_verdict(L(t, ERROR, "  " + line) + L(t + 0.2, INFO, POLL), r, r, now)[0] == "UNKNOWN"
                else:
                    assert H._run_verdict(entry + L(t + 0.2, INFO, POLL), r, r, now)[0] == "UNKNOWN"
                    assert H._run_verdict(L(t, INFO, "  " + line), r, r, now)[0] == "UNKNOWN"
    assert n["OK"] > 0 and n["PARKED"] > n["OK"], n
    print("    · сетка: строк статуса %d (OK %d, простой %d)" % (sum(n.values()), n["OK"], n["PARKED"]))


def test_d5_blind_readers_ratchet():
    import blind_readers as BR
    found = BR.find_blind(open(H.__file__, encoding="utf-8").read(), "health.py")
    base = BR.load_baseline(os.path.join(ROOT, BR.BASELINE_NAME))
    assert len(found) <= base["per_file"]["health.py"] == 4, found
    new_fns = {"_read_run", "_run_key", "_run_word", "_run_verdict", "check_polling", "build_report", "main"}
    assert not [f for f in found if f["func"] in new_fns], found


def test_d6_read_run_live_format():
    # дословный живой образец (docs/artifacts/2026-08-16-rule-delivery-check.md:24–31), ключи в порядке systemd
    live = ("ActiveState=active\nSubState=running\nFragmentPath=/etc/systemd/system/orchestrator-daemon.service\n"
            "ActiveEnterTimestamp=Sun 2026-08-16 18:54:50 UTC\nMainPID=1249876\nNRestarts=0\n"
            "ExecMainStartTimestamp=Sun 2026-08-16 18:54:50 UTC\nExecMainStartTimestampMonotonic=2011920081825\n")
    seen = []

    def _run(cmd, **kw):
        seen.append((list(cmd), kw))
        return subprocess.CompletedProcess(cmd, 0, live, "")
    with mock.patch.object(H.subprocess, "run", _run):
        got = H._read_run()
    assert got == {"pid": 1249876, "start": _dt.datetime(2026, 8, 16, 18, 54, 50, tzinfo=UTC),
                   "start_raw": "Sun 2026-08-16 18:54:50 UTC", "nrestarts": 0, "active": "active",
                   "sub": "running"}, got
    assert seen[0][0] == ["systemctl", "show", "splinter",
                          "--property=MainPID,ExecMainStartTimestamp,NRestarts,ActiveState,SubState"], seen
    assert seen[0][1].get("timeout") == 15 and seen[0][1].get("capture_output") and seen[0][1].get("text"), seen
    # обратный порядок строк — тот же результат (разбор по ключам)
    rev = "".join(reversed(live.splitlines(True)))
    with mock.patch.object(H.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, rev, "")):
        assert H._read_run() == got
    # пояс не UTC и битая метка — None (прежде пояс молча считался UTC)
    for bad in ("Sun 2026-08-16 21:54:50 MSK", "Sun 2026-08-16 18:54:50", "Sun 2026-08-16 25:54:50 UTC", "0"):
        txt = live.replace("ExecMainStartTimestamp=Sun 2026-08-16 18:54:50 UTC", "ExecMainStartTimestamp=" + bad)
        with mock.patch.object(H.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, txt, "")):
            assert H._read_run() is None, bad
    # check_service на том же источнике — прежний текст
    with world([], B()):
        ok, detail, start_dt, nr = H.check_service()
    assert ok and detail == "active/running, uptime 2ч0м, рестартов 0", detail
    assert start_dt == dt(int(T_B)) and nr == "0", (start_dt, nr)


# ======================================================================================================================
# Z. Мутанты: (было, стало, слова, проверки, которые обязаны упасть). Файл — health.py.
# ======================================================================================================================
MUTANTS = (
    ("        if cur is None or cur < start:\n            continue\n",
     "        if cur is None:\n            continue\n",
     "граница запуска снята (весь журнал)", ("test_a3_normal_current_run_as_before", "test_b3_same_second_as_start")),
    ("    if _run_key(run0) != _run_key(run1):\n", "    if False:\n", "сверка двух чтений границы снята",
     ("test_a5_boundary_changed_between_reads",)),
    ('    if run0 is None or run1 is None:\n        return "UNKNOWN",',
     '    if run0 is None or run1 is None:\n        return "OK",',
     "нет границы = зелёное", ("test_a4_boundary_unavailable_is_unknown",)),
    ("    status, why = _run_verdict(lines, run0, run1, now if now is not None else _utcnow())\n",
     '    status, why = (("OK", "Bot polling started") if _last_match(lines, "Bot polling started")\n'
     '                   else ("NO_POLL", "нет"))\n',
     "прежний check_polling (последнее совпадение по всему журналу)",
     ("test_a1_old_polling_new_park_mismatch", "test_a2_old_polling_new_park_unknown",
      "test_a4_boundary_unavailable_is_unknown")),
    ('    if mp and lvl == "ERROR":\n', '    if mp and lvl == "ERROR" and False:\n', "простой не назван простоем",
     ("test_a1_old_polling_new_park_mismatch", "test_d4_grid_release_entry_iff_health_verdict")),
    ("        elif _POLL_RE.match(ln):\n", '        elif "Bot polling started" in ln:\n',
     "якорь polling снят (подстрока)", ("test_b4_strict_anchor_and_continuations",)),
    ("    if ets > start + skew:\n", "    if False:\n", "окно 300 с для входа снято", ("test_b2_window_and_clock",)),
    ("    if young:   # verify3 x1/x1b/x5", "    if False:   # verify3 x1/x1b/x5",
     "молодой запуск с polling — OK (verify3 x1)", ("test_a8_crash_loop_after_polling_line", "test_b5_young_run")),
    ("        if cur > ahead:\n", "        if False:\n", "метки впереди часов не проверяются",
     ("test_b2_window_and_clock",)),
    ('    if not (mo and lvl == "INFO"):\n', "    if not mo:\n", "уровень строки входа не сверяется",
     ("test_b1_ambiguity_and_contradictions", "test_d4_grid_release_entry_iff_health_verdict")),
    ("    if len(polls) > 1:\n", "    if False:\n", "два polling — не неоднозначность",
     ("test_b1_ambiguity_and_contradictions",)),
    ('parts[3] == "UTC"', "True", "пояс метки systemd не проверяется", ("test_d6_read_run_live_format",)),
    ("        problems.append(pl_d)\n", '        problems.append("нет polling")\n', "в сводке прежнее «нет polling»",
     ("test_a1_old_polling_new_park_mismatch", "test_a4_boundary_unavailable_is_unknown")),
    ("    run1 = _read_run()\n", "    run1 = run0\n", "граница из одного чтения",
     ("test_a5_boundary_changed_between_reads",)),
    ("            if ok is True:\n", "            if True:\n", "неизвестная доставка печатается как «отправлен»",
     ("test_c2_unknown_delivery_no_retry",)),
    ("            ok = notify(report, force=True)   # боевой health-алерт — тест-мут не глушит\n",
     "            ok = notify(report, force=True) or notify(report, force=True)\n", "повтор notify при неуспехе",
     ("test_c2_unknown_delivery_no_retry", "test_c3_no_push_when_green_and_one_call_max")),
)


def _spawn(mut_dir, tests):
    env = dict(os.environ)
    env.update(RCFIX_HEALTH_SRC=mut_dir, RCFIX_HEALTH_ONLY=",".join(tests), PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1")
    env.pop("NOTIFY_COUNT_FILE", None)                  # у ребёнка свой временный каталог и свой счётчик
    return subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_zz_mutants():
    if SRC or ONLY:
        return
    if os.environ.get("RCFIX2010_MUTANTS") != "1":
        print("  SKIP мутанты: RCFIX2010_MUTANTS не 1 (квитанция мутантов — отдельным запуском)")
        return
    src = open(os.path.join(ROOT, "health.py"), encoding="utf-8").read()
    union = sorted({t for m in MUTANTS for t in m[3]})
    null_dir = tempfile.mkdtemp(prefix="rcfix_health_null_")
    with open(os.path.join(null_dir, "health.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    jobs = [("нулевой мутант (копия без правки)", _spawn(null_dir, union), True)]
    for old, new, words, tests in MUTANTS:
        assert src.count(old) == 1, (words, src.count(old))
        d = tempfile.mkdtemp(prefix="rcfix_health_mut_")
        with open(os.path.join(d, "health.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace(old, new))
        jobs.append((words, _spawn(d, tests), False))
    missed = []
    for words, p, null in jobs:
        out = p.communicate(timeout=600)[0].decode("utf-8", "replace")
        fell = [ln.split()[1] for ln in out.splitlines() if ln.startswith("FAIL ")]
        print("    · мутант «%s»: упало %d — %s" % (words, len(fell), ", ".join(fell[:4])))
        if null:
            if p.returncode != 0 or fell:
                missed.append((words, out[-800:]))
        elif p.returncode == 0 or not fell:
            missed.append((words, out[-800:]))
    assert not missed, missed


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)
             and (not ONLY or n in ONLY)]
    bad = 0
    print("временный каталог: %s · health: %s" % (TMP, H.__file__))
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
