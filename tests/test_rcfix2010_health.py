#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RCFIX2010 C · PARKSEEN (Codex TB-QA-2110-0006-PARKSEEN, вариант B; вопрос K3-2110-0006-QB): health ВИДИТ простой
Splinter.

Повод: под 410a839 bot.main() при входе выпуска MISMATCH/UNKNOWN печатает ОДНУ строку [ERROR] «🚦 вход выпуска: …» и
простаивает (_park_until_stop): обработчиков, задач и опроса нет, бот молчит. Прежний health искал «Bot polling started»
последним совпадением по ВСЕМУ неротированному splinter.log — строка прошлого запуска проходила, одна строка [ERROR]
давала «⚠️ РАБОТАЕТ, но 1 ошибок», code 0, и пуш (только при code ≠ 0) не уходил. Теперь polling судится в границе
ТЕКУЩЕГО запуска: MainPID + ExecMainStartTimestamp юнита (чтения до и после журнала и третье — непосредственно перед
вердиктом), строка входа выпуска этого запуска и его polling; метки systemd и журнала — на одной шкале UTC.

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
        a4 граница недоступна (исключение, код ≠ 0, пусто, MainPID 0, метка ''/n/a/буквенный пояс, нет NRestarts) →
           НЕИЗВЕСТНО;
        a5 граница сменилась между чтениями (PID / старт / NRestarts / ActiveState) → НЕИЗВЕСТНО;
        a6 нет polling текущего запуска / нет ни входа, ни polling / запуск моложе 300 с / polling без строки входа;
        a7 прежние случаи health (кредит и его дедуп, Brain, ошибки, мост, WA, сервис не active) не изменились;
        a8 цикл падений ПОСЛЕ строки polling (verify3 x1: bot.py:1778 печатает её до app.run_polling :1779), текущему
           запуску 3 с, NRestarts 57 → НЕИЗВЕСТНО, code 1, один пуш; прежний check_polling — «✅ ВСЁ ОК»; порог 300 с;
        a9 (verify3 x2) рестарт ВО ВРЕМЯ долгих проверок, новый процесс в простое → третье чтение границы перед
           вердиктом → НЕИЗВЕСТНО, code 1, один пуш; пары: без рестарта — прежнее ✅; граница перед вердиктом не
           прочитана; строка сервиса из другого запуска;
        a10 (verify3 x4) прочитанный пустой журнал — «нет строк» (факт); не прочитан (каталог, нет файла) / прочитан
           не целиком / байты не UTF-8 в сегменте — НЕИЗВЕСТНО с причиной; пары: те же байты в истории не мешают,
           CRLF = LF, чтение = прежний readlines;
        a11 (h3 · verify4 r4) строка «Аудитор» при непрочитанном журнале — НЕИЗВЕСТНО «маркеры не проверены», а не
           «нет ✅»; пары: прочитанный пустой — «нет ✅» (факт), нормальный — прежняя строка;
        a12 (r4 · verify5 п.4) _read_log кусками = разбор r3 целиком на любых границах кусков (1…8192 байт; CRLF/CR,
           многобайтовые и битые байты через границу, хвост без перевода строки); пик памяти не выше прежнего
           readlines();
  B — чистая _run_verdict: неоднозначность, противоречия, уровни, окно 300 с, часы и пояс, строгость якоря, продолжения;
      b6 (verify3 x6) все 12 зелёных сочетаний смены пояса между процессами (прошлый +1 ч, текущий −1…−12 ч, прошлый
      жил час) на настоящем build_report() → НЕИЗВЕСТНО «метки журнала идут назад»; пары без сдвига — ПРОСТОЙ и OK;
      порог 120 с; запись с неразобранной меткой в сегменте — НЕИЗВЕСТНО, в истории — нет;
      b7 (h3 · verify4 n6a) все 72 зелёных сочетания атаки (оба процесса в одном поясе восточнее systemd, прошлый
      прожил hp·3600 − 1 / hp·3600 с, текущий завис после строк загрузки) → НЕИЗВЕСТНО «посылка «журнал в UTC» … не
      подтверждена», контрфакт без правила посылки — OK; точный пример на build_report()/main(); пары: тот же
      зависший процесс в UTC — «нет строки» (факт), окно [старт, старт + 300 с] по границам, журнал без записи начала;
      b8 (h3 · verify4 n2a/n2b) метка неизвестной формы (без мс, мс через точку, ISO с T, иная раскладка — настоящий
      logging.Formatter): 4 × 26 зелёных n2a и 8 случаев n2b → НЕИЗВЕСТНО «строка с меткой неизвестной формы»,
      контрфакт без правила — OK / «нет строки»; пары: та же форма в истории не мешает, время без секунд — текст;
      цена (предел x3) записана проверкой;
      r4 (verify5): b3 — polling выше строки загрузки текущего процесса больше не его (было «противоречие», стало OK;
      «ровно одна» проверяется ниже строки загрузки и без неё); b7, b8 — контрфакт «без правила — OK» стал «без правила
      и без границ процесса — OK» (объяснение по месту записей — в докстрингах тестов);
      b9 (verify5 Q1, MAJOR) строка загрузки bot.py:94 по месту начинает новый процесс: точный пример Q1 на
      build_report()/main() → ❌ code 1, один пуш (r3 — ✅); убитый прошлый × сетка — «нет строки», без правила — OK;
      норма после короткого прошлого — ✅ (r3 — «граница неоднозначна»);
      b10 (verify5 п.2, отделимое) остановка планировщика ниже polling — процесс того polling завершён: штатно
      остановленный прошлый + текущий до bot.py:94 → «нет строки» (r3 — OK); убитый прошлый — предел (1), записан;
      живая форма 70a — OK / PARKED / NO_POLL; слова зависания до bot.py:94 (п.5);
      r5 (verify6, решение Codex TB-REVIEW-2110-HEALTH-STEP0): b11 — сужение п.3 r4 (метка только со словом уровня)
      ОТКАЧЕНО к правилу r3: форма без слова уровня у текущего простоя при убитом прошлом в окне — НЕИЗВЕСТНО (repro
      verify6 nolevel), цена x3 вернулась и записана проверкой (только текущий запуск; в истории — ✅), метку даёт
      только запись (замок cost N1/N2), предел (3) при убитом прошлом записан; b12 — СЧЁТ СТРОК ЗАГРУЗКИ: в окне
      текущего запуска (метка ≥ старта) их больше одной → НЕИЗВЕСТНО (второй писатель А/Б, P1); текст bot.py:94 в
      сообщении — не строка загрузки; запись загрузки текстом text[:100] (bot.py:572) не подделать (110 > 99); порядок
      внутри процесса (атака v6 a3: чужие загрузка / вход / polling ниже строк текущего с метками раньше них) —
      НЕИЗВЕСТНО; пределы (1) записаны; нормальные запуски (цикл рестартов, прошлый в UTC, часы, 70a) — без новых
      тревог; b9/b10 — слова и
      ожидания по счёту и по п.2 (сброс остановкой называется остановкой; цена вставленной строки остановки записана);
      b13 — слова посылки: строка загрузки без входа или запись позже окна — первой причиной пояс/часы (cost W6/W7);
      a13 — _read_log линеен: одна строка 16 МБ без \\n и журнал только с \\r — порядок r3;
  C — доставка: notify True → «отправлен (Telegram ok)»; False / None / исключение → «доставка не подтверждена (НЕ
      отправлен … неизвестно) … повтора нет»; вызов ровно один; код возврата прежний; настоящего notify нет;
  D — замки: копии health ↔ splinter (_ENTRY_HEAD, имена RELEASE_ENTRY_STATES, RELEASE_FLAG_KEYS); формат и строки
      bot.py; health не импортирует splinter; сетка всех строк release_entry ⇔ вердикт health; храповик слепых;
      _read_run на живом формате (порядок ключей, лишние ключи) и его вызов; d7 (verify3 x6) пояс метки systemd
      разбирается на шкалу UTC («+07»/«-03»/«+0545»/GMT; буквенный — граница не прочитана), check_service на той же
      шкале; пара: сервер и журнал бота оба в +07 — пояс журнала не UTC → НЕИЗВЕСТНО;
  Z — мутанты (RCFIX2010_MUTANTS=1, как в test_rcfix2010_tuple.py): каждый роняет хотя бы одну проверку своего места,
      нулевой зелёный; у каждого правила r4/r5 — свой мутант (п.1 r4 ×3, п.2 r4 ×4, правило метки r3 и метка только у
      записи, счёт строк загрузки ×3, порядок внутри процесса ×2, слова ×2, чтение ×3); число — в печати
      test_zz_mutants.
Сети, systemctl, Telegram, мозга и боевых файлов нет: notify — заглушка в sys.modules (плюс NOTIFY_COUNT_FILE во
временном каталоге — проверяется, что он так и не появился), dotenv и bridge_client — заглушки (настоящий файл окружения
не читается), файл эпизода кредита health — во временном каталоге. h3: пути модуля health (LOG, .wa_watchdog_fails,
.api_credit_episode) уведены во временный каталог с импорта; open и subprocess.run ВНУТРИ health — сторожа (файл вне
временного каталога и любой процесс мимо FakeSystemd записываются и отказывают), test_y_no_live_reads требует ноль
попыток и держит замок «каждый читатель build_report подменён в world()».
Прогон: venv/Scripts/python.exe tests/test_rcfix2010_health.py → «ИТОГ N/M»."""
import ast
import contextlib
import datetime as _dt
import io
import itertools
import logging
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc
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

# h3 (изоляция): на сервере ROOT health — живое дерево, и неподменённый читатель открыл бы боевой splinter.log,
# .wa_watchdog_fails или .api_credit_episode. Пути модуля — во временный каталог с импорта; open и subprocess.run ВНУТРИ
# health — сторожа (world()/run_of()/test_d6 подменяют subprocess.run на FakeSystemd поверх сторожа и снимают подмену
# на выходе). Каждая попытка мимо записывается в LIVE и отказывает; test_y_no_live_reads требует ноль.
LIVE = {"open": [], "run": []}
_TMPN = os.path.normcase(os.path.abspath(TMP))
_REAL_OPEN = open


def _guard_open(path, *a, **k):
    p = os.path.normcase(os.path.abspath(os.fspath(path)))
    if p != _TMPN and not p.startswith(_TMPN + os.sep):
        LIVE["open"].append(p)
        raise PermissionError(13, "тест: health открывает файл вне временного каталога", p)
    return _REAL_OPEN(path, *a, **k)


def _guard_run(cmd, *a, **k):
    LIVE["run"].append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
    raise FileNotFoundError(2, "тест: живой процесс из health запрещён", str(cmd))


H.LOG = os.path.join(TMP, "splinter.log")
H._WA_PROBE_FAIL_FILE = os.path.join(TMP, "wa_watchdog_fails")
H._CREDIT_EPISODE_FILE = os.path.join(TMP, "credit_episode_default")
H.open = _guard_open                                   # имя модуля health заслоняет builtins.open
H.subprocess = types.SimpleNamespace(run=_guard_run)   # health зовёт только subprocess.run

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


def prev_run(t_start, t_end, step=300):
    """Прошлый запуск НОВОГО кода, живший до рестарта t_end: вход OK, polling, тики планировщика каждые step с, штатная
    остановка (форма — verify3_health_attack prev_run_until)."""
    out = run_ok(t_start)
    t = t_start + 46 + step
    while t < t_end - 10:
        out += L(t, INFO, 'Running job "devbot_report (trigger: interval[0:00:45])"',
                 name="apscheduler.executors.default")
        t += step
    out += L(t_end - 5, INFO, "Scheduler has been shut down", name="apscheduler.scheduler")
    return out


_STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} \[", re.ASCII)


def shift_ts(lines, hours):
    """Журнал процесса, писавшего в поясе UTC+hours: asctime = time.localtime процесса (bot.py:71–74), поэтому метка
    КАЖДОЙ записи сдвинута на hours часов, продолжения без метки — как есть (форма — verify3 x6 shift_ts)."""
    out = []
    for ln in lines:
        m = _STAMP_RE.match(ln)
        if m:
            d = _dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") + _dt.timedelta(hours=hours)
            ln = d.strftime("%Y-%m-%d %H:%M:%S") + ln[19:]
        out.append(ln)
    return out


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
        assert r.fake.bound_reads == 3, r.fake.calls          # граница: до журнала, после него и перед вердиктом
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
                # буквенный пояс неоднозначен (verify3 x6: «+07» теперь разбирается на шкалу UTC — test_d7)
                ("пояс буквенный (MSK)", dict(runs=[dict(p, ExecMainStartTimestamp=stamp(T_B, "MSK", 3))] * 2)),
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
    # (д) журнал прочитан и пуст — «нет строк» (факт); не прочитан — НЕИЗВЕСТНО с причиной (verify3 x4, подробно — a10)
    r = build([], B())
    assert r.code == 1 and "нет строки «вход выпуска» и polling текущего запуска" in r.summary, r.summary
    r = build(history() + run_ok(T_B), B(), _read_log=lambda: (None, "не прочитан (PermissionError)"))
    assert r.code == 1 and r.row("Polling").startswith("❌"), r.summary
    assert "НЕИЗВЕСТНО: журнал splinter.log не прочитан (PermissionError)" in r.summary, r.summary
    assert "нет строки" not in r.summary, r.summary


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


def test_a9_boundary_rechecked_before_verdict():
    """verify3 x2: граница снималась ДО долгих проверок (мост ×3, мозг 4 дока, кредит, WA — до ~9 мин). Юнит
    перезапущен ВО ВРЕМЯ проверки моста, новый процесс встал в простой MISMATCH (его строки дописаны в журнал) — прежде
    отчёт уходил «✅ ВСЁ ОК», code 0 по ушедшему процессу. Третье чтение границы непосредственно перед вердиктом →
    НЕИЗВЕСТНО, code 1, один пуш. Пары: та же долгая проверка без рестарта — вердикт и отчёт прежние; граница перед
    вердиктом не прочитана (systemctl код 1); строка «Splinter сервис» из другого запуска (старт / NRestarts / active)."""
    path = os.path.join(TMP, "splinter.log")
    s2 = int(NOW) - 30
    holder = {}

    def bridge(restart=False, mode=None):
        def _b(*a, **k):
            if restart:
                with open(path, "a", encoding="utf-8", newline="\n") as f:
                    f.writelines(run_park(s2, words_of(**{STRICT: "0"})))
                holder["fake"].runs = [props_of(PID_B + 9, s2, nrestarts=1)]
                holder["fake"].bound_reads = 0
            if mode:
                holder["fake"].mode = mode
            return True, "alive v1.0.0"
        return _b

    def go(br, argv=None, **over):
        NOTIFY.calls.clear()
        NOTIFY.result = True
        buf = io.StringIO()
        with world(history() + run_ok(T_B), B(), check_bridge=br, **over) as fake:
            holder["fake"] = fake
            if argv is None:
                report, summary, code, _bw, _cw = H.build_report()
                return Rep(report, summary, code, fake)
            with contextlib.redirect_stdout(buf):
                rc = H.main(list(argv))
        return rc, buf.getvalue(), list(NOTIFY.calls)

    was = "PID %d, старт %s UTC, рестартов 0" % (PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S"))
    now_ = "PID %d, старт %s UTC, рестартов 1" % (PID_B + 9, dt(s2).strftime("%Y-%m-%d %H:%M:%S"))
    r = go(bridge(restart=True))
    assert r.code == 1 and r.row("Polling").startswith("❌ Polling"), (r.code, r.summary)
    assert r.summary.startswith("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: граница запуска сменилась за время "
                                "отчёта (%s → %s) — вердикт относится к ушедшему запуску; прежний вердикт: вход "
                                "выпуска OK (release)" % (was, now_)), r.summary
    assert r.fake.bound_reads == 1, r.fake.calls             # после рестарта прочитана одна граница — перед вердиктом
    rc, out, calls = go(bridge(restart=True), argv=("--push",))
    assert rc == 1 and len(calls) == 1 and "сменилась за время отчёта" in calls[0]["text"], (rc, calls, out[-300:])
    # пара: та же долгая проверка без рестарта — прежний зелёный, прежняя строка Polling, пуша нет
    r = go(bridge())
    assert r.code == 0 and r.summary == "✅ ВСЁ ОК" and r.fake.bound_reads == 3, (r.summary, r.fake.bound_reads)
    assert r.row("Polling") == "✅ Polling         вход выпуска OK (release) · Bot polling started · " + was, r.row(
        "Polling")
    rc, out, calls = go(bridge(), argv=("--push",))
    assert rc == 0 and calls == [], (rc, calls)
    # граница перед вердиктом не прочитана
    r = go(bridge(mode="rc1"))
    assert r.code == 1 and ("НЕИЗВЕСТНО: граница запуска не перечитана перед вердиктом (systemctl show) — вердикт по "
                            + was + " не подтверждён; прежний вердикт: вход выпуска OK") in r.summary, r.summary
    # строка «Splinter сервис» из другого запуска: старт, NRestarts, is-active
    for name, over in (("старт", dict(check_service=lambda: (True, "active/running", dt(int(T_B) + 60), "0"))),
                       ("NRestarts", dict(check_service=lambda: (True, "active/running", dt(int(T_B)), "1"))),
                       ("is-active", dict(is_active="inactive"))):
        r = go(bridge(), **over)
        assert r.code == 1 and "НЕИЗВЕСТНО: факты отчёта не согласованы: «Splinter сервис»" in r.summary, (name, r.summary)
    print("    · рестарт во время отчёта: ❌ НЕИЗВЕСТНО code 1, один пуш; без рестарта — прежний ✅; ещё 4 пары")


def test_a10_log_unread_truncated_unparsed_vs_empty():
    """verify3 x4: «прочитан, строк нет» (факт) ≠ «не прочитан / прочитан не целиком / не разобран» (НЕИЗВЕСТНО с
    причиной). Прежде _read_log_lines глотал исключение → [], и вердикт утверждал ОТСУТСТВИЕ строк при непрочитанном
    источнике."""
    lines = history() + run_ok(T_B)
    # (1) прочитан и пуст — «нет строки …» (факт), не НЕИЗВЕСТНО
    r = build([], B())
    assert r.code == 1 and "НЕИЗВЕСТНО" not in r.row("Polling"), r.row("Polling")
    assert "нет строки «вход выпуска» и polling текущего запуска" in r.row("Polling"), r.row("Polling")
    # (2) не прочитан: каталог вместо файла (форма атаки x4) и файла нет — НЕИЗВЕСТНО с причиной, не «нет строк»
    for name, target in (("каталог", TMP), ("нет файла", os.path.join(TMP, "нет-такого.log"))):
        with world(lines, B()):
            with mock.patch.object(H, "LOG", target):
                report, summary, code, _bw, _cw = H.build_report()
        pol = [ln for ln in report.split("\n") if "Polling" in ln][0]
        assert code == 1 and "запуск не доказан — НЕИЗВЕСТНО: журнал splinter.log не прочитан (" in pol, (name, pol)
        assert "отсутствие строк не доказано" in pol and "нет строки" not in pol, (name, pol)
        if name == "нет файла":
            assert "не прочитан (FileNotFoundError)" in pol, pol
    # (3) прочитан не целиком: прочитано меньше размера на открытии / файл укоротился за чтение
    path = os.path.join(TMP, "trunc.log")
    data = "".join(lines).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    for name, sizes in (("прочитано меньше размера", (len(data) + 4096, len(data) + 4096)),
                        ("укоротился за чтение", (len(data), len(data) - 100))):
        it = iter(sizes)
        with mock.patch.object(H, "LOG", path), \
                mock.patch.object(H.os, "fstat", lambda fd: types.SimpleNamespace(st_size=next(it))):
            got, why = H._read_log()
        assert got is None and why.startswith("прочитан не целиком (размер на открытии "), (name, got, why)
    with mock.patch.object(H, "LOG", path):
        assert H._read_log() == (lines, None)                   # без подмены — целиком, строки те же
    r = build(lines, B(), _read_log=lambda: (None, "прочитан не целиком (размер на открытии 9 байт, прочитано 5, "
                                                     "после чтения 9)"))
    assert r.code == 1 and "НЕИЗВЕСТНО: журнал splinter.log прочитан не целиком" in r.summary, r.summary
    # (4) не разобран: байты не UTF-8 в сегменте текущего запуска — НЕИЗВЕСТНО; те же байты в истории — не мешают
    def bin_build(blob):
        with world([], B()) as fake:
            with open(H.LOG, "wb") as f:
                f.write(blob)
            report, summary, code, _bw, _cw = H.build_report()
            same = H._read_log() == (H._read_log_lines(), None)
        return Rep(report, summary, code, fake), same

    enc = lambda ls: "".join(ls).encode("utf-8")              # noqa: E731
    bad = b"\xd0\x9f\xff\xfe \x80 \xc3\n"                       # обрывок кириллицы и одиночные байты — не UTF-8
    r, _same = bin_build(enc(lines) + bad)
    assert r.code == 1 and "НЕИЗВЕСТНО: строка журнала текущего запуска не разобрана (байты не UTF-8)" in r.summary, \
        r.summary
    r, _same = bin_build(enc(history()) + bad + enc(run_ok(T_B)))
    assert r.code == 0 and r.summary == "✅ ВСЁ ОК", r.summary
    # (5) концы строк: CRLF — тот же отчёт, что LF; чтение = прежний readlines() текстового режима
    lf = enc(history() + run_ok(T_B, errors=2))
    (a, same_lf), (b, same_crlf) = bin_build(lf), bin_build(lf.replace(b"\n", b"\r\n"))
    assert a.code == b.code == 0 and a.report == b.report and same_lf and same_crlf, (a.report, b.report)
    # build_report судит журнал по _read_log, а не по прежнему _read_log_lines
    tree = ast.parse(open(H.__file__, encoding="utf-8").read())
    br = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_report"][0]
    called = {n.func.id for n in ast.walk(br) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_read_log" in called and "_read_log_lines" not in called and "_recheck_run" in called, sorted(called)
    print("    · журнал: пустой — «нет строк»; не прочитан / не целиком / не UTF-8 — НЕИЗВЕСТНО с причиной (6 пар)")


def test_a11_auditor_row_unread_journal():
    """h3 · verify4 r4: строка «Аудитор» при НЕПРОЧИТАННОМ журнале утверждала «нет ✅ в старт-логе» — отсутствие маркеров
    по источнику, которого не читали (тот же класс, что x4 у Polling). Теперь — НЕИЗВЕСТНО с причиной; ❌ и «аудитор не
    подтверждён» в сводке остаются (он и правда не подтверждён). Пары: прочитанный пустой журнал — «нет ✅» (факт),
    нормальный журнал — прежняя строка."""
    lines = history() + run_ok(T_B)
    for why in ("не прочитан (PermissionError)", "прочитан не целиком (размер на открытии 9 байт, прочитано 5, после "
                                                 "чтения 9)"):
        r = build(lines, B(), _read_log=lambda why=why: (None, why))
        row = r.row("Аудитор")
        assert row == ("❌ Аудитор         НЕИЗВЕСТНО: журнал splinter.log " + why
                       + " — маркеры старт-лога не проверены"), row
        assert r.code == 1 and "аудитор не подтверждён" in r.summary, r.summary
    with world(lines, B()):
        with mock.patch.object(H, "LOG", os.path.join(TMP, "нет-такого.log")):
            report, _summary, code, _bw, _cw = H.build_report()
    row = [ln for ln in report.split("\n") if "Аудитор" in ln][0]
    assert code == 1 and "НЕИЗВЕСТНО: журнал splinter.log не прочитан (FileNotFoundError)" in row, row
    assert "нет ✅" not in row, row
    assert build([], B()).row("Аудитор") == "❌ Аудитор         нет ✅ в старт-логе: Auditor, Auditor LLM"
    assert build(lines, B()).row("Аудитор") == "✅ Аудитор         подключён + LLM-надзор (старт-лог)"


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
    # журнал позади UTC (−3 ч): текущий запуск выпадает из сегмента целиком → не зелёное. h3 (verify4 n6a): и не «нет
    # строки» — последняя по месту запись начала процесса (его вход) стоит на −10799 с от старта, посылка «журнал в UTC»
    # не подтверждена → НЕИЗВЕСТНО (было NO_POLL; оба — ❌ code 1, поменялось слово «нет строк» на «не доказано»)
    st, why = verdict(history() + run_ok(t - 3 * 3600))
    assert st == "UNKNOWN" and "посылка «журнал в UTC» для текущего запуска не подтверждена" in why, (st, why)
    assert "-10799 с от старта юнита, вне окна [старт, старт + 300 с]" in why, why
    # старт юнита впереди часов
    r = run_of(props_of(PID_B, NOW + 3600))
    assert H._run_verdict(run_ok(NOW + 3600), r, r, dt(NOW))[0] == "UNKNOWN"


def test_b3_same_second_as_start():
    """Строка в ту же секунду, что старт (точность ExecMainStartTimestamp — секунда), — текущему запуску; секундой
    раньше — прошлому; polling чужого процесса в ту же секунду НИЖЕ строки загрузки текущего — «ровно одна» ловит.

    r4 (verify5 Q1) — ожидание изменено ПО МЕСТУ записей. Было: polling на +0,05 с ВЫШЕ строки загрузки текущего
    (bot.py:94 на +0,12 с) → UNKNOWN «противоречие: polling раньше строки входа». Стало: строка загрузки по месту
    начинает НОВЫЙ процесс, поэтому polling выше неё — прежнего процесса и в счёт не идёт; у текущего своя цепочка
    загрузка → вход → polling → OK. Верно, потому что bot.py:94 — первая безусловная запись процесса (test_d2), polling
    того же процесса (bot.py:1778) по месту всегда НИЖЕ неё, а файл дописывается: polling выше строки загрузки текущему
    процессу принадлежать не может. Прежняя проверка «ровно одна» не ослабла — она переехала туда, где чужой polling
    возможен в сегменте текущего процесса: ниже его строки загрузки (запись вперемешку) — UNKNOWN, как было; и без
    строки загрузки (журнал без bot.py:94) — UNKNOWN, как было."""
    t = T_B
    ok_line = S().release_entry(words_of(), frozenset())[1]
    boot94 = L(t + 0.12, INFO, BOOT_LINE)
    rest = L(t + 0.4, INFO, "  " + ok_line) + L(t + 0.62, INFO, POLL)
    cur = boot94 + rest
    assert verdict(L(t - 0.5, INFO, POLL) + cur)[0] == "OK"
    st, why = verdict(L(t + 0.05, INFO, POLL) + cur)                 # чужой polling ВЫШЕ строки загрузки текущего
    assert st == "OK", (st, why)
    st, why = verdict(boot94 + L(t + 0.15, INFO, POLL) + rest)        # чужой polling НИЖЕ строки загрузки текущего
    assert st == "UNKNOWN" and "противоречие: polling раньше" in why, why
    st, why = verdict(L(t + 0.05, INFO, POLL) + rest)                 # строки загрузки нет — прежнее правило
    assert st == "UNKNOWN" and "противоречие: polling раньше" in why, why
    assert verdict(L(t - 0.5, INFO, POLL) + rest)[0] == "OK"          # без строки загрузки: секундой раньше — прошлому


def test_b4_strict_anchor_and_continuations():
    t = T_B
    ok_line = S().release_entry(words_of(), frozenset())[1]
    quote_poll = L(t + 5, INFO, "Splinter [ops] ответ dev-боту: ✅ Polling         Bot polling started")
    cont_poll = ["Bot polling started. Press Ctrl+C to stop.\n"]
    other_logger = L(t + 6, INFO, POLL, name="devbot")
    one_space = ["%s [INFO] turbobaby: Bot polling started. Press Ctrl+C to stop.\n"
                 % (time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(t) + 7)) + ",000 ")]
    base = boot(t, words_of()) + L(t + 1.0, INFO, "  " + ok_line) + tail_ok(t, poll_at=None, post=False)
    for name, extra in (("цитата", quote_poll), ("продолжение без метки", cont_poll), ("чужой логгер", other_logger)):
        st, why = verdict(base + extra)
        assert st == "NO_POLL", (name, st, why)
    # лишний пробел перед [INFO]: polling не засчитан, как прежде; h3 (verify4 n2) — и не невидимый текст, а метка
    # неизвестной формы в текущем запуске → НЕИЗВЕСТНО (было NO_POLL; оба — ❌ code 1)
    st, why = verdict(base + one_space)
    assert st == "UNKNOWN" and "строка с меткой неизвестной формы" in why, (st, why)
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


# verify3 x6 (out/verify3_health_reverify/reports/wt/test_v3_health_attack.txt): ровно эти 12 сочетаний (возраст
# прошлого запуска, пояс прошлого процесса, пояс текущего) давали OK при простое.
X6_GREENS = tuple((3600, 1, hc) for hc in range(-12, 0))


def test_b6_zone_switch_between_processes():
    """verify3 x6: пояс процесса бота сменился МЕЖДУ процессами. Прошлый процесс (жил час до рестарта) писал в +1 ч —
    его вход OK и polling «переезжают» за старт текущего; текущий в простое пишет западнее (−1…−12 ч) — его строка
    простоя уходит раньше старта. Прежде — OK при простое (12 сочетаний). Журнал — настоящий Formatter bot.py со сдвигом
    метки на пояс процесса, граница — вывод systemctl show живого порядка с поясом «UTC», отчёт — настоящий
    build_report(). Пары: тот же журнал без сдвига — ПРОСТОЙ; норма с тем же сдвигом — НЕИЗВЕСТНО, без сдвига — OK."""
    s0 = T_B
    park = run_park(s0, words_of(**{STRICT: "0"}))
    norm = run_ok(s0)
    seen = 0
    for age, hp, hc in X6_GREENS:
        prev = shift_ts(prev_run(s0 - age, s0), hp)
        for name, cur in (("простой", park), ("норма", norm)):
            r = build(history() + prev + shift_ts(cur, hc), B(t0=s0))
            assert r.code == 1 and r.row("Polling").startswith("❌ Polling"), (age, hp, hc, name, r.summary)
            assert "запуск не доказан — НЕИЗВЕСТНО: метки журнала идут назад" in r.summary, (age, hp, hc, name,
                                                                                              r.summary)
            seen += 1
    prev = prev_run(s0 - 3600, s0)
    r = build(history() + prev + park, B(t0=s0))
    assert r.code == 1 and "ПРОСТОЙ Splinter: вход выпуска MISMATCH" in r.summary, r.summary
    r = build(history() + prev + norm, B(t0=s0))
    assert r.code == 0 and r.summary == "✅ ВСЁ ОК", r.summary
    # порог «назад» 120 с: перестановка потоков (0,5 с) и шаг часов 120 с — ещё порядок; 121 с — НЕИЗВЕСТНО
    for back_s, want in ((0.5, "OK"), (120, "OK"), (121, "UNKNOWN")):
        extra = L(s0 + 600, INFO, "Splinter [ops] тик", name="splinter") + L(s0 + 600 - back_s, INFO,
                                                                              "Splinter [ops] тик-2", name="splinter")
        st, why = verdict(history() + norm + extra)
        assert st == want, (back_s, st, why)
    # запись логгера bot.py с неразобранной меткой: в сегменте — НЕИЗВЕСТНО, в истории — не мешает
    bad = ["2026-13-45 99:99:99,999 [INFO] turbobaby: " + POLL + "\n"]
    st, why = verdict(history() + norm + bad)
    assert st == "UNKNOWN" and "запись журнала с неразобранной меткой «2026-13-45 99:99:99,999»" in why, (st, why)
    assert verdict(history() + bad + norm)[0] == "OK"
    # цифры метки — только ASCII: полноширинная «запись» — текст, polling она не даёт
    wide = ["２０２６-１０-２１ ０７:００:００,０００ [INFO] turbobaby: " + POLL + "\n"]
    assert verdict(history() + run_ok(s0, poll_at=None, post=False) + wide)[0] == "NO_POLL"
    print("    · смена пояса между процессами: %d сочетаний x6 × (простой, норма) = %d отчётов → НЕИЗВЕСТНО; без сдвига —"
          " ПРОСТОЙ / ✅" % (len(X6_GREENS), seen))


# h3 · verify4 n6a (out/verify4_health_attack/reports/v4b/test_v4_health_attack.txt, FACT n6a_grid: 72 зелёных, из них
# 8 пар с одинаковым поясом): ровно эти сочетания (возраст прошлого запуска, пояс прошлого процесса hp, пояс текущего
# hc) давали OK — прошлый в hp = 0,25…2 ч восточнее systemd прожил hp·3600 − 1 или hp·3600 с (его вход и polling
# встают в [старт, старт + 300 с]), текущий в поясе hc = hp…2 ч завис после строк загрузки (входа нет), записи не идут
# назад.
N6A_GREENS = tuple((900 * k + d, k / 4.0, hc / 4.0) for k in range(1, 9) for d in (-1, 0) for hc in range(k, 9))
BOOT_LINE = "  Auditor: ✅ подключён к splinter._send (надзор за языком исходящих)"   # дословно bot.py:94 (test_d2)


def test_b7_premise_current_run_east_zone():
    """h3 · verify4 n6a: посылка «журнал в UTC» не доказана для ТЕКУЩЕГО запуска — вердикт по строкам НЕИЗВЕСТНО, а не
    «✅ ВСЁ ОК». Правило: последняя по месту запись начала процесса (строка загрузки bot.py:94 / вход) — в окне [старт,
    старт + 300 с] (порог = окно входа; опора — два живых наблюдения, 69k:190–194 Δ ≤ 1,2 с и 70a:156–157,163–169
    Δ ≤ 1,5 с, точность — секунда метки systemd; порог не измерен).

    r4 — КОНТРФАКТ изменён по месту записей (основное утверждение — UNKNOWN «посылка … не подтверждена», +hc·3600 с —
    прежнее). Было: без правила посылки (_premise_gap → None) — OK на всех 72 сочетаниях. Стало: без правила посылки —
    NO_POLL «нет строки «вход выпуска»», потому что по месту НИЖЕ входа и polling прошлого стоят две записи, каждая из
    которых по правилам r4 отрезает их от текущего запуска: остановка планировщика прошлого (prev_run пишет
    «Scheduler has been shut down» за 5 с до рестарта, по его часам — в сегменте, п.2) и строка загрузки bot.py:94
    текущего (п.1, verify5 Q1). Это верно: вход и polling, стоящие в файле выше строки загрузки процесса, этому процессу
    не принадлежат (test_d2: bot.py:94 — первая безусловная запись), а остановка планировщика пишется при
    Application.stop — процесс того polling завершён. Зелёное на тех же 72 журналах воспроизводится только без ВСЕХ
    трёх правил (посылка, граница по строке загрузки, граница по остановке) — это и есть контрфакт атаки n6a теперь;
    без одной посылки — NO_POLL (❌ code 1, слово «нет строк» вместо «не доказано»).

    r5 — второй контрфакт снова изменён: без одной посылки — НЕИЗВЕСТНО по СЧЁТУ строк загрузки (r5 · verify6): строка
    загрузки прошлого (+hp ч, прожил hp·3600 − 1 / hp·3600 с) и строка загрузки текущего (+hc ч ≥ hp) обе стоят по своим
    меткам не раньше старта — в окно текущего запуска писали два процесса. Без всех трёх (строка загрузки снята целиком —
    с ней снят и счёт) — OK, как прежде."""
    hung = boot(T_B, words_of())                           # пять строк загрузки bot.py:94–117, строки входа нет
    same_zone = {(hp, hc) for _a, hp, hc in N6A_GREENS if hp == hc}           # FACT n6a_grid: n_same_zone=8 (пары)
    assert len(N6A_GREENS) == 72 and len(same_zone) == 8, (len(N6A_GREENS), sorted(same_zone))
    never = re.compile(r"(?!)")
    for age, hp, hc in N6A_GREENS:
        lines = history() + shift_ts(prev_run(T_B - age, T_B, step=900), hp) + shift_ts(hung, hc)
        st, why = verdict(lines)
        assert st == "UNKNOWN" and "посылка «журнал в UTC» для текущего запуска не подтверждена" in why, (age, hp, hc,
                                                                                                          st, why)
        assert "%+d с от старта юнита" % int(hc * 3600) in why, (age, hp, hc, why)   # строка загрузки текущего
        with mock.patch.object(H, "_premise_gap", lambda *a, **k: None):           # без посылки — счёт строк загрузки
            st0, why0 = verdict(lines)
            assert st0 == "UNKNOWN" and "в окне текущего запуска 2 строк загрузки — писали несколько процессов" in why0, (
                age, hp, hc, st0, why0)
        with mock.patch.object(H, "_premise_gap", lambda *a, **k: None), mock.patch.object(H, "_BOOT_RE", never), \
                mock.patch.object(H, "_SHUT_RE", never):                           # контрфакт: без всех трёх — OK
            assert verdict(lines)[0] == "OK", (age, hp, hc)
    # точный пример атаки на настоящем build_report() и main(): оба процесса в +01, прошлый прожил час
    lines = history() + shift_ts(prev_run(T_B - 3600, T_B), 1) + shift_ts(hung, 1)
    r = build(lines, B())
    assert r.code == 1 and r.row("Polling").startswith("❌ Polling"), (r.code, r.summary)
    assert ("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: посылка «журнал в UTC» для текущего запуска не подтверждена: "
            "последняя по месту в файле запись начала процесса (строка загрузки bot.py:94 / «вход выпуска») — "
            "2026-10-21 07:00:00 по метке журнала, +3600 с от старта юнита") in r.summary, r.summary
    rc, out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1 and "посылка «журнал в UTC»" in calls[0]["text"], (rc, calls)
    # пара: тот же зависший процесс в UTC — посылка подтверждена его строкой загрузки (+0 с), «нет строки» — факт
    r = build(history() + prev_run(T_B - 3600, T_B) + hung, B())
    assert r.code == 1 and "НЕИЗВЕСТНО" not in r.row("Polling"), r.row("Polling")
    assert "нет строки «вход выпуска» и polling текущего запуска" in r.row("Polling"), r.row("Polling")
    # пара: нормальный текущий запуск в UTC после прошлого — прежний ✅ (a3); тот же пояс +01 у всех — не зелёное
    assert build(history() + prev_run(T_B - 3600, T_B) + run_ok(T_B), B()).summary == "✅ ВСЁ ОК"
    r = build(shift_ts(history() + prev_run(T_B - 3600, T_B) + run_ok(T_B), 1), B())
    assert r.code == 1 and "НЕИЗВЕСТНО" in r.summary, r.summary
    # окно по границам: запись начала на старт + 300 с — подтверждена; + 301 с и − 1 с — нет
    for at, want in ((T_B + 300.5, "NO_POLL"), (T_B + 301.2, "UNKNOWN"), (T_B - 0.5, "UNKNOWN")):
        st, why = verdict(history() + L(at, INFO, BOOT_LINE))
        assert st == want, (at - T_B, st, why)
    # записи начала в журнале нет вовсе (срезан с головы): было «нет строки» → НЕИЗВЕСТНО; журнал без единой метки —
    # факт
    st, why = verdict(run_ok(T_B)[12:] + L(T_B + 3000, INFO, "Splinter [ops] тик", name="splinter"))
    assert st == "UNKNOWN" and "в журнале нет ни строки загрузки (bot.py:94), ни строки «вход выпуска»" in why, \
        (st, why)
    for blank in ([], ["\n", "\n"], ["Traceback (most recent call last):\n", "ValueError: x\n"]):
        st, why = verdict(blank)
        assert st == "NO_POLL" and "нет строки «вход выпуска»" in why, (blank, st, why)
    print("    · посылка текущего запуска: %d зелёных n6a → НЕИЗВЕСТНО (без правила — OK); пары UTC/окно/без записи "
          "начала" % len(N6A_GREENS))


# h3 · verify4 n2: формы метки, которых health не знает, — настоящий logging.Formatter с поясом процесса (а не правка
# строк): datefmt без мс; мс через точку; ISO с T; иная раскладка с той же меткой.
def _alien(datefmt=None, msec=None, iso=False, layout=BOT_FMT):
    f = logging.Formatter(layout, datefmt=datefmt)
    f.converter = time.gmtime
    if msec:
        f.default_msec_format = msec
    if iso:
        f.default_time_format = "%Y-%m-%dT%H:%M:%S"
    return f


ALIEN = {"без мс": _alien(datefmt="%Y-%m-%d %H:%M:%S"), "мс через точку": _alien(msec="%s.%03d"),
         "ISO с T": _alien(iso=True), "иная раскладка": _alien(layout="%(asctime)s - %(name)s - %(levelname)s - "
                                                                      "%(message)s")}
_FULL_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) \[([A-Z]+)\] (\S+): (.*)$", re.ASCII | re.DOTALL)


def relog(lines, fmt, hours=0):
    """Те же записи, написанные другим форматтером процессом в поясе UTC+hours; продолжения без метки — как есть."""
    out = []
    for ln in lines:
        m = _FULL_RE.match(ln.rstrip("\n"))
        if not m:
            out.append(ln)
            continue
        t = (_dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
             + int(m.group(2)) / 1000.0 + hours * 3600)
        r = logging.LogRecord(m.group(4), logging.getLevelName(m.group(3)), "bot.py", 1, m.group(5), None, None)
        ms = int(round(t * 1000))
        r.created, r.msecs = ms / 1000.0, float(ms % 1000)
        out.append(fmt.format(r) + "\n")
    return out


def test_b8_unknown_stamp_form_is_unknown():
    """h3 · verify4 n2a/n2b: строка, начинающаяся с метко-подобного префикса, но не запись формата bot.py:73, — в
    текущем запуске НЕИЗВЕСТНО «строка с меткой неизвестной формы», а не невидимый текст. Прежде: n2a — 26 зелёных на
    форму при ПРОСТОЕ, n2b — «нет строки «вход выпуска»» при строке входа, написанной другой формой.

    r4 — два ожидания изменены по месту записей. (1) Контрфакт n2a: было «без правила метки — OK», стало «без правила
    метки и без границы по остановке планировщика — OK»: прошлый (prev_run, +1 ч) пишет «Scheduler has been shut down»
    за 5 с до рестарта — по его часам это в сегменте и НИЖЕ его polling, и по п.2 r4 его вход и polling текущему не
    засчитаны (без одного правила метки — NO_POLL, не зелёное). (2) Цена x3 r3 (строка сообщения «2026-10-21 09:00:00
    выдача» в текущем запуске и перед ним — UNKNOWN) в r4 снималась п.3 (слово уровня). r5 (verify6 c1) п.3 откатил —
    цена x3 снова та же, что у r3, и записана здесь строками r3 (test_b11 — подробно)."""
    park, norm = run_park(T_B, words_of(**{STRICT: "0"})), run_ok(T_B)
    assert relog(norm, FMT) == norm                       # перерисовка тем же форматтером — тождество
    no_ms = logging.Formatter(BOT_FMT, datefmt="%Y-%m-%d %H:%M:%S")
    no_ms.converter = time.gmtime
    assert relog(park, ALIEN["без мс"])[5] == no_ms.format(logging.makeLogRecord(dict(
        name="turbobaby", levelno=ERROR, levelname="ERROR", msg=park[5].split(": ", 1)[1].rstrip("\n"),
        created=T_B + 1.003, msecs=3.0))) + "\n"
    never = re.compile(r"(?!)")
    # n2b: без посылки пояса, текущий процесс пишет неизвестной формой
    for fname, f in ALIEN.items():
        for kind, cur in (("простой", park), ("норма", norm)):
            lines = history() + relog(cur, f)
            st, why = verdict(lines)
            assert st == "UNKNOWN" and "строка с меткой неизвестной формы" in why, (fname, kind, st, why)
            with mock.patch.object(H, "_STAMPISH_RE", never), \
                    mock.patch.object(H, "_premise_gap", lambda *a, **k: None):
                assert verdict(lines)[0] == "NO_POLL", (fname, kind)         # контрфакт r2: «нет строки»
        # пары: та же форма в ИСТОРИИ (прошлый процесс писал ею) не мешает — текущий в формате bot.py судится как прежде
        assert verdict(relog(history(), f) + norm)[0] == "OK", fname
        assert verdict(relog(history(), f) + park)[0] == "PARKED", fname
    # n2a: найденные зелёные (FACT n2a: 26 на форму) — прошлый +1 ч прожил 3599 / 3600 с, текущий простой в поясе
    # −12…0 ч
    n = 0
    for fname, f in ALIEN.items():
        for age in (3599, 3600):
            prev = shift_ts(prev_run(T_B - age, T_B, step=900), 1)
            for hc in range(-12, 1):
                lines = history() + prev + relog(park, f, hc)
                st, why = verdict(lines)
                assert st == "UNKNOWN" and "строка с меткой неизвестной формы" in why, (fname, age, hc, st, why)
                with mock.patch.object(H, "_STAMPISH_RE", never):
                    assert verdict(lines)[0] == "NO_POLL", (fname, age, hc)   # r4 п.2: остановка прошлого ниже polling
                with mock.patch.object(H, "_STAMPISH_RE", never), mock.patch.object(H, "_SHUT_RE", never):
                    assert verdict(lines)[0] == "OK", (fname, age, hc)    # контрфакт: без обоих — зелёное при простое
                n += 1
    assert n == 4 * 26, n
    # точный пример атаки на build_report()/main(): прежде «⚠️ РАБОТАЕТ, но 1 ошибок», code 0, пушей 0
    lines = history() + shift_ts(prev_run(T_B - 3600, T_B), 1) + relog(park, ALIEN["без мс"], -3)
    r = build(lines, B())
    assert r.code == 1 and "НЕИЗВЕСТНО: строка с меткой неизвестной формы «2026-10-21 03:00:00 [INFO]" in r.summary, \
        r.summary
    rc, out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1, (rc, calls)
    # граница правила: текст сообщения с датой-временем в ИСТОРИИ, за которым идут записи истории, — не метка; время без
    # секунд — текст; цена (предел x3), r5 = r3: то же с секундами в текущем запуске или последним перед ним — ложная
    # тревога
    msg = "[-1001234567890] Филипп (HQ · Общий) → мозг: бронь:\n%s выдача"
    hist = history()
    in_hist = hist[:5] + L(T_A + 0.99, INFO, msg % "2026-10-21 09:00:00") + hist[5:]
    assert verdict(in_hist + norm)[0] == "OK"
    assert verdict(history() + norm + L(T_B + 3600, INFO, msg % "2026-10-21 09:00"))[0] == "OK"
    st, why = verdict(history() + norm + L(T_B + 3600, INFO, msg % "2026-10-21 09:00:00"))
    assert st == "UNKNOWN" and "неизвестной формы «2026-10-21 09:00:00 выдача»" in why, (st, why)
    st, why = verdict(history() + L(T_A + 86001, INFO, msg % "2026-10-21 09:00:00") + norm)
    assert st == "UNKNOWN" and "неизвестной формы" in why, (st, why)
    print("    · метка неизвестной формы: n2b 8 случаев, n2a %d зелёных → НЕИЗВЕСТНО (без правила — «нет строки» / без"
          " правила и остановки — OK); история и время без секунд не мешают" % n)


# r4 · verify5: формы атаки Q1 и живого 70a (out/verify5_health_attack/test_v5_health_attack.py: until, p1_short,
# hung_before_94) — здесь свои, на тех же фикстурах.
SHUT = "Scheduler has been shut down"                              # apscheduler, при Application.stop (JobQueue PTB)
MEM_LINE = "Memory DB initialized: memory.db"                      # живой 70a:164 — запись ДО строки загрузки bot.py:94


def _until(lines, t_end):
    """Строки процесса до момента t_end (продолжения — вместе с родителем)."""
    out, keep = [], True
    for ln in lines:
        m = _STAMP_RE.match(ln)
        if m:
            t = (_dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
                 + int(ln[20:23]) / 1000.0)
            keep = t <= t_end
        if keep:
            out.append(ln)
    return out


def stop_line(t):
    return L(t, INFO, SHUT, name="apscheduler.scheduler")


def short_prev(G, life, clean=True):
    """Прошлый процесс НОВОГО кода: старт за G с до текущего, вход OK, polling, хвост post_init (до +46 с), прожил life
    с; clean — штатная остановка (строка планировщика на +life), иначе убит (SIGKILL / OOM — строки нет)."""
    s = T_B - G
    return _until(run_ok(s), s + life) + (stop_line(s + life) if clean else [])


def hung_before_94(t0=T_B):
    """Текущий процесс завис ДО строки загрузки bot.py:94 (импорт / конструкторы bot.py:83–85): одна запись Memory()."""
    return L(t0 + 0.475, INFO, MEM_LINE, name="memory")


NEVER = re.compile(r"(?!)")
# Сетки атаки Q1 (verify5 q1_grid): пояс прошлого hp ч, разрыв стартов G = hp·3600 + d, жизнь прошлого. В Q1_GRID
# последняя запись убитого прошлого (≤ +46 с) отстаёт от строки загрузки текущего меньше чем на 120 с при любом d; в
# B10_GRID то же для штатной остановки (+life ≤ +60 с) — без правил r4 каждое сочетание зелёное.
Q1_GRID = tuple((k / 4.0, d, life) for k in (1, 4, 8, 22, 56) for d in (-60, -1, 0, 1) for life in (30, 60, 119))
B10_GRID = tuple((k / 4.0, d, life) for k in (1, 4, 8, 22, 56) for d in (-60, -1, 0, 1) for life in (30, 50, 60))


def test_b9_boot_line_starts_new_process():
    """r4 · verify5 Q1 (MAJOR): строка загрузки bot.py:94 ПО МЕСТУ в файле начинает НОВЫЙ процесс — вход выпуска и
    polling выше неё сбрасываются (при любой её метке). Атака: пояс процесса бота сменился МЕЖДУ процессами (x6),
    прошлый в +hp ч прожил ≤ 2 мин и стоял hp ч до текущего, текущий в UTC написал строки загрузки (bot.py:94–117) и
    завис до входа. Вход и polling прошлого стоят в [старт, старт + 300 с], его последняя запись отстаёт от строки
    загрузки текущего меньше чем на 120 с — проверка «назад» молчит; r3 на точном примере — «✅ ВСЁ ОК», code 0, пушей
    0 (out/tmp/verify5_health_attack/repro_q1_x6_short_prev.py). Правило отделимо от п.2: на убитом прошлом (строки
    остановки нет) атаку закрывает только оно.

    r5 (verify6) — ожидания по СЧЁТУ строк загрузки: прошлый стартовал за G = hp·3600 + d до текущего и писал в +hp ч,
    поэтому его строка загрузки стоит по своей метке на старт − d + 0,912 с. При d ≤ 0 она в окне текущего запуска
    вместе со строкой загрузки текущего — две строки, НЕИЗВЕСТНО «писали несколько процессов» (было «нет строки»; оба —
    ❌ code 1). При d = 1 она на 0,088 с раньше старта — счёт 1, исход r4. Цена (предел (5) _run_verdict): НОРМАЛЬНЫЙ
    текущий запуск после такого прошлого при d ≤ 0 — тоже НЕИЗВЕСТНО (r3 — «граница неоднозначна», r4 — ✅)."""
    hung = boot(T_B, words_of())
    who = "PID %d, старт %s UTC, рестартов 0" % (PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S"))
    two = "в окне текущего запуска 2 строк загрузки — писали несколько процессов (второй писатель / смена пояса)"
    # точный пример verify5 Q1 (прошлый +01 прожил 60 с и штатно остановлен) на build_report()/main()
    lines = history() + shift_ts(short_prev(3600, 60), 1) + hung
    r = build(lines, B())
    assert r.code == 1 and r.summary.startswith("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: " + two), r.summary
    rc, _out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1 and two in calls[0]["text"], (rc, calls)
    with mock.patch.object(H, "_BOOT_RE", NEVER), mock.patch.object(H, "_SHUT_RE", NEVER):
        assert build(lines, B()).summary == "✅ ВСЁ ОК"                # контрфакт r3: без границ процесса — зелёное
    # убитый прошлый (строки остановки нет): атаку закрывает строка загрузки текущего (сброс по месту, при d ≤ 0 — и счёт)
    without, by = 0, {"UNKNOWN": 0, "NO_POLL": 0}
    for hp, d, life in Q1_GRID:
        prev = shift_ts(short_prev(int(hp * 3600) + d, life, clean=False), hp)
        in_window = d <= 0                                            # строка загрузки прошлого: старт − d + 0,912 с
        for name, cur in (("завис после строк загрузки", hung), ("завис после bot.py:94", L(T_B + 0.912, INFO,
                                                                                               BOOT_LINE))):
            st, why = verdict(history() + prev + cur)
            if in_window:
                assert st == "UNKNOWN" and two in why, (hp, d, life, name, st, why)
            else:
                assert st == "NO_POLL" and "нет строки «вход выпуска» и polling" in why, (hp, d, life, name, st, why)
            by[st] += 1
            with mock.patch.object(H, "_BOOT_RE", NEVER):
                without += verdict(history() + prev + cur)[0] == "OK"
        # пары: текущий простой — ПРОСТОЙ (d = 1) / НЕИЗВЕСТНО по счёту (d ≤ 0); текущий норма — OK (d = 1) / НЕИЗВЕСТНО
        # по счёту (d ≤ 0, цена (5); r3: «граница неоднозначна: строк «вход выпуска» 2», F5 «смена пояса +1 → UTC»)
        st, why = verdict(history() + prev + run_park(T_B, words_of(**{STRICT: "0"})))
        assert (st, two in why) == (("UNKNOWN", True) if in_window else ("PARKED", False)), (hp, d, life, st, why)
        st, why = verdict(history() + prev + run_ok(T_B))
        assert (st, two in why) == (("UNKNOWN", True) if in_window else ("OK", False)), (hp, d, life, st, why)
        with mock.patch.object(H, "_BOOT_RE", NEVER):
            st, why = verdict(history() + prev + run_ok(T_B))
            assert st == "UNKNOWN" and "граница неоднозначна" in why, (hp, d, life, st, why)
    assert without == 2 * len(Q1_GRID), (without, len(Q1_GRID))       # без правила — каждое сочетание зелёное
    assert by == {"UNKNOWN": 2 * 45, "NO_POLL": 2 * 15}, by          # d ∈ {−60, −1, 0} — 45 сочетаний, d = 1 — 15
    # строка загрузки по МЕСТУ, а не по метке: текущий целиком на 2 с раньше старта (шаг часов) — не зелёное
    prev = shift_ts(short_prev(3600, 60, clean=False), 1)
    st, why = verdict(history() + prev + boot(T_B - 2, words_of()))
    assert st != "OK", (st, why)
    # норма, затем строка загрузки с меткой за 30 с до старта ниже по месту — не зелёное. r5 (verify6 a3): строка загрузки
    # с меткой раньше старта НИЖЕ записей текущего запуска — сразу НЕИЗВЕСТНО (её закрыли бы и сброс по месту, и посылка),
    # поэтому мутанты verify6 m01/m14 («сброс только в сегменте / только при метке ≥ старта») эта пара не различает
    st, why = verdict(history() + run_ok(T_B) + L(T_B - 30, INFO, BOOT_LINE))
    assert st == "UNKNOWN" and ("строка загрузки bot.py:94 с меткой 2026-10-21 05:59:30 раньше старта юнита стоит ниже "
                                "строки загрузки текущего запуска") in why, (st, why)
    print("    · строка загрузки начинает процесс: точный Q1 → ❌ code 1, один пуш (r5 — по счёту строк загрузки); убитый "
          "прошлый %d×2 → %r (без правила — %d зелёных); норма после него — ✅ при d = 1, НЕИЗВЕСТНО при d ≤ 0 (цена"
          " (5))" % (len(Q1_GRID), by, without))


def test_b10_scheduler_stop_ends_process():
    """r4 · verify5 п.2 (ОТДЕЛИМОЕ правило): строка «Scheduler has been shut down» (apscheduler, строгий шаблон
    _SHUT_RE) в сегменте НИЖЕ последнего polling по месту ⇒ процесс того polling завершён (JobQueue PTB — единственный
    планировщик bot.py, останавливается при Application.stop), его вход и polling текущему запуску не засчитаны. Цель —
    доля предела (1) со штатной остановкой прошлого: текущий завис ДО bot.py:94 (ни одной своей записи), прошлый
    восточнее ровно на промежуток между стартами — r3: OK (verify5 q1_limit1: 1232 зелёных со штатной остановкой).
    Убитый прошлый — предел (1) остаётся (записан проверкой). Живая форма 70a (остановка прошлого в сегменте по времени,
    ВЫШЕ строки загрузки текущего по месту) — норма OK, простой PARKED, зависание NO_POLL, как раньше.

    r5 (verify6): СЛОВА сброса по п.2 — правда о том, что видно: «после polling стоит строка остановки планировщика —
    процесс того polling завершён (или строка вставлена сообщением)», а не «нет строки «вход выпуска»» (вход был — его
    отрезала остановка). ЦЕНА п.2 записана проверкой: полная строка остановки — 82 знака, с «лог:\\n» — 87 ≤ text[:100]
    (bot.py:572), вставленная сообщением в НОРМАЛЬНОМ запуске ниже его polling — ❌ до рестарта (fail-closed, ложная
    тревога). Простой со вставленной строкой остановки — по-прежнему ПРОСТОЙ (сброс только ниже polling, verify6 m02);
    строка остановки не уровня INFO — не остановка (verify6 m16)."""
    who = "PID %d, старт %s UTC, рестартов 0" % (PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S"))
    stopped = ("после polling стоит строка остановки планировщика — процесс того polling завершён (или строка вставлена "
               "сообщением)")
    without = killed_ok = 0
    for hp, d, life in B10_GRID:
        G = int(hp * 3600) + d
        lines = history() + shift_ts(short_prev(G, life, clean=True), hp) + hung_before_94()
        st, why = verdict(lines)
        assert st == "NO_POLL" and why.startswith(stopped) and why.endswith("(%s)" % who), (hp, d, life, st, why)
        with mock.patch.object(H, "_SHUT_RE", NEVER):
            without += verdict(lines)[0] == "OK"
        killed_ok += verdict(history() + shift_ts(short_prev(G, life, clean=False), hp) + hung_before_94())[0] == "OK"
    assert without == len(B10_GRID), (without, len(B10_GRID))        # без правила — каждое сочетание зелёное
    assert killed_ok == len(B10_GRID), killed_ok                       # ПРЕДЕЛ (1): убитый прошлый — зелёное (назван)
    # точный пример на build_report()/main(): прошлый +01 прожил 60 с, штатно остановлен, текущий завис до bot.py:94
    lines = history() + shift_ts(short_prev(3600, 60), 1) + hung_before_94()
    r = build(lines, B())
    assert r.code == 1 and r.summary == ("❌ ПРОБЛЕМА: " + stopped + ": остановка 2026-10-21 06:01:00 по метке журнала, "
                                         "нового входа и polling ниже неё нет (%s)" % who), r.summary
    rc, _out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1, (rc, calls)
    with mock.patch.object(H, "_SHUT_RE", NEVER):
        assert build(lines, B()).summary == "✅ ВСЁ ОК"                # контрфакт r3
    # без смены пояса: прошлый (старт за 1 с) успел вход и polling в секунду старта текущего и штатно остановлен
    lines = history() + run_ok(T_B - 1.0, post=False) + stop_line(T_B + 0.577) + hung_before_94(T_B + 0.4)
    assert verdict(lines)[0] == "NO_POLL", verdict(lines)
    with mock.patch.object(H, "_SHUT_RE", NEVER):
        assert verdict(lines)[0] == "OK"
    # живая форма 70a (70a:156–157 граница, 70a:163–169 журнал): остановка прошлого «12:22:09,577» (:163) при старте
    # 12:22:09 (:157) — в сегменте по времени, ВЫШЕ строк текущего по месту; затем «Memory DB initialized» (:164) и строки
    # текущего
    prev70 = _until(prev_run(T_B - 3600, T_B + 10), T_B - 10) + stop_line(T_B + 0.577)
    for name, cur, want in (("норма", run_ok(T_B), "OK"),
                            ("простой", run_park(T_B, words_of(**{STRICT: "0"})), "PARKED"),
                            ("завис после строк загрузки", boot(T_B, words_of()), "NO_POLL")):
        st, why = verdict(history() + prev70 + hung_before_94() + cur)
        assert st == want, (name, st, why)
    assert build(history() + prev70 + hung_before_94() + run_ok(T_B), B()).summary == "✅ ВСЁ ОК"
    # 70a, текущий завис ДО bot.py:94 — слова (r4 · п.5): первой причиной «текущий процесс до строки загрузки не дошёл»
    st, why = verdict(history() + prev70 + hung_before_94())
    assert st == "UNKNOWN" and ("вне окна [старт, старт + 300 с] — текущий процесс до строки загрузки не дошёл "
                                "(импорт/конструкторы bot.py:83–85), пояс журнала не UTC или импорт дольше 300 с") \
        in why, (st, why)
    # граница правила: остановка без polling выше — ничего; не строгая запись (чужой логгер, цитата, продолжение) — не
    # остановка; собственная остановка текущего ниже его polling — процесс завершается: не зелёное
    assert verdict(history() + stop_line(T_B + 0.5) + run_ok(T_B))[0] == "OK"
    for extra in (L(T_B + 600, INFO, "Splinter [ops] " + SHUT, name="splinter"),
                  L(T_B + 600, INFO, SHUT, name="devbot"), L(T_B + 600, INFO, "[-100] Ф (HQ) → мозг: лог:\n" + SHUT),
                  [SHUT + "\n"], L(T_B + 600, WARNING, SHUT, name="apscheduler.scheduler"),
                  L(T_B + 600, INFO, SHUT + ".", name="apscheduler.scheduler")):
        assert verdict(history() + run_ok(T_B) + extra)[0] == "OK", extra
    st, why = verdict(history() + run_ok(T_B) + stop_line(T_B + 3000))
    assert st == "NO_POLL" and why == (stopped + ": остановка 2026-10-21 06:50:00 по метке журнала, нового входа и "
                                       "polling ниже неё нет (%s)" % who), (st, why)
    # ЦЕНА п.2 (fail-closed): полная строка остановки, вставленная сообщением bot.py:572 в нормальном запуске
    stop_rec = stop_line(T_B + 3570)[0].rstrip("\n")
    text = "лог:\n" + stop_rec
    assert (len(stop_rec), len(text)) == (82, 87) and len(text) <= 100, (len(stop_rec), len(text))
    pasted = history() + prev_run(T_B - 3600, T_B) + run_ok(T_B) + _msg(T_B + 3600, text)
    assert pasted[-1] == stop_rec + "\n", pasted[-2:]                 # продолжение сообщения — запись целиком
    st, why = verdict(pasted)
    assert st == "NO_POLL" and why.startswith(stopped + ": остановка 2026-10-21 06:59:30"), (st, why)
    r = build(pasted, B())
    assert r.code == 1 and r.summary.startswith("❌ ПРОБЛЕМА: " + stopped), r.summary
    # простой + та же вставка — ПРОСТОЙ (polling выше остановки нет — сброса нет, verify6 m02)
    st, why = verdict(history() + run_park(T_B, words_of(**{STRICT: "0"})) + _msg(T_B + 3600, text))
    assert st == "PARKED" and "ПРОСТОЙ Splinter" in why, (st, why)
    print("    · остановка планировщика ниже polling: %d сочетаний «штатно остановлен + текущий до bot.py:94» → «%s…» "
          "(без правила — %d зелёных); убитый прошлый — предел (1): %d зелёных; 70a — OK/PARKED/NO_POLL; цена п.2 — "
          "вставка 87 знаков → ❌ до рестарта" % (len(B10_GRID), stopped[:40], without, killed_ok))


F5_TEXTS = ("бронь:\n2026-10-21 09:00:00 выдача", "лог:\n2026-10-21 09:00:00.123456 событие",
            "json:\n2026-10-21T09:00:00Z", "бронь:\n2026/10/21 09:00:00 выдача")


def _msg(t, text):
    return L(t, INFO, "[-1001234567890] Филипп (HQ · Общий) → мозг: " + text[:100])        # bot.py:572, text[:100]


def test_b11_stamp_prefix_rule_r3_restored():
    """r5 · verify6 c1 (решение Codex TB-REVIEW-2110-HEALTH-STEP0): сужение п.3 r4 («метка неизвестной формы — только со
    словом уровня logging в первых 56 символах после префикса») ОТКАЧЕНО к правилу r3. Повод: процесс, пишущий формой
    без слова уровня («%(asctime)s %(name)s: %(message)s»), в ПРОСТОЕ при убитом прошлом в окне давал «✅ ВСЁ ОК» (атака
    v6 c1 — 216 сочетаний r4 OK при r3 НЕИЗВЕСТНО; repro_v6_nolevel), а продолжение «…,ммм» без слова уровня становилось
    действующей меткой (verify6 cost N1/N1b/N2/N2b — тревога на НОРМЕ до часов ПК или навсегда).
    Цена правила r3 (предел x3) — записана здесь: строка сообщения bot.py:572, начинающаяся с даты-времени с секундами
    (F5), в ТЕКУЩЕМ запуске — НЕИЗВЕСТНО до рестарта; в ИСТОРИИ, если за ней идёт запись истории, — ✅; с датой ≥ старта
    последней перед сегментом (прошлый убит сразу после сообщения) — НЕИЗВЕСТНО (pend r3). Замок «метку даёт только
    запись» — проверка с правилом метки, снятым подменой. Предел (3) — метка не в начале строки — при убитом прошлом."""
    who = "PID %d, старт %s UTC, рестартов 0" % (PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S"))
    park = run_park(T_B, words_of(**{STRICT: "0"}))
    killed = shift_ts(_until(prev_run(T_B - 3600, T_B, step=900), T_B - 10), 1)       # +01, прожил час, убит
    clean = shift_ts(prev_run(T_B - 3600, T_B, step=900), 1)                          # +01, прожил час, штатно
    utc = prev_run(T_B - 3600, T_B)                                                    # UTC, штатно
    # (1) repro verify6 nolevel на build_report()/main(): r4 — «✅ ВСЁ ОК», code 0, пушей 0
    nolevel = _alien(layout="%(asctime)s %(name)s: %(message)s")
    lines = history() + killed + relog(park, nolevel)
    r = build(lines, B())
    assert r.code == 1 and ("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: строка с меткой неизвестной формы «2026-10-21 "
                            "06:00:00,912 tu» в текущем запуске") in r.summary, r.summary
    rc, _out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1, (rc, calls)
    with mock.patch.object(H, "_STAMPISH_RE", NEVER):
        assert verdict(lines)[0] == "OK"                     # контрфакт: без правила метки — зелёное при простое
    # (2) формы атаки v6 c1 без слова уровня / со словом дальше 56 символов — НЕИЗВЕСТНО при любом прошлом
    forms = {"«метка,мс имя: сообщение»": nolevel, "«метка,мс сообщение»": _alien(layout="%(asctime)s %(message)s"),
             "«метка - имя - сообщение»": _alien(layout="%(asctime)s - %(name)s - %(message)s"),
             "уровень числом [20]": _alien(layout="%(asctime)s [%(levelno)s] %(name)s: %(message)s"),
             "без мс, без уровня": _alien(datefmt="%Y-%m-%d %H:%M:%S", layout="%(asctime)s %(name)s: %(message)s"),
             "ISO с T, без уровня": _alien(iso=True, layout="%(asctime)s %(name)s: %(message)s"),
             "имя шириной 60, уровень дальше 56": _alien(layout="%(asctime)s %(name)-60s %(levelname)s %(message)s")}
    n = 0
    for fname, f in forms.items():
        for pname, prev in (("убит +01", killed), ("штатно +01", clean), ("UTC", utc)):
            for cname, cur in (("простой", park), ("норма", run_ok(T_B))):
                st, why = verdict(history() + prev + relog(cur, f))
                assert st == "UNKNOWN" and "строка с меткой неизвестной формы" in why, (fname, pname, cname, st, why)
                n += 1
    # (3) ЦЕНА x3 (только ТЕКУЩИЙ запуск): F5 в текущем — НЕИЗВЕСТНО, ❌ и пуш; в истории за ней запись истории — ✅
    norm = history() + utc + run_ok(T_B)
    for text in F5_TEXTS:
        st, why = verdict(norm + _msg(T_B + 3600, text))
        assert st == "UNKNOWN" and "строка с меткой неизвестной формы" in why and who in why, (text, st, why)
        r = build(norm + _msg(T_B + 3600, text), B())
        assert r.code == 1 and "НЕИЗВЕСТНО: строка с меткой неизвестной формы" in r.summary, (text, r.summary)
        i = len(_until(utc, T_B - 1800))
        in_hist = history() + utc[:i] + _msg(T_B - 1800, text) + utc[i:] + run_ok(T_B)
        r = build(in_hist, B())
        assert r.code == 0 and r.summary == "✅ ВСЁ ОК", (text, r.summary)
    # пара: тот же текст с датой раньше старта перед сегментом — ✅; без секунд / без ведущего года — текст
    assert verdict(history() + _until(utc, T_B - 60) + _msg(T_B - 30, "бронь:\n2026-10-20 09:00:00 выдача")
                   + run_ok(T_B))[0] == "OK"
    for text in ("бронь:\n2026-10-21 09:00 выдача", "бронь:\n21.10.2026 09:00:00 выдача"):
        assert verdict(norm + _msg(T_B + 3600, text))[0] == "OK", text
    # перед сегментом с датой ≥ старта и без записи истории после неё (F5 «прошлый убит сразу после сообщения») — r3
    lines = (history() + _until(prev_run(T_B - 3600, T_B + 10), T_B - 60)
             + _msg(T_B - 30, "бронь:\n2026-10-25 09:00:00 выдача") + run_ok(T_B))
    st, why = verdict(lines)
    assert st == "UNKNOWN" and "строка с меткой неизвестной формы «2026-10-25 09:00:00 выдача»" in why, (st, why)
    # (4) ЗАМОК «метку даёт только запись» (verify6 cost N1/N2): даже при СНЯТОМ правиле метки продолжение с «,ммм» в
    # истории — не действующая метка (r4: «впереди часов» на норме до часов ПК / навсегда)
    far = _msg(T_A + 5000, "лог:\n2099-01-01 00:00:00,000 x")                                     # N1: три дня назад
    pc = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(T_B - 1810) + 7 * 3600)) + ",000"
    mb = _msg(T_B - 1800, "смотри:\n" + pc + " | ✅ модерация: сообщение пропущено (чат -1001)")     # N2: ПК +07
    utc_mb = utc[:i] + mb + utc[i:]
    for name, ls in (("N1", run_ok(T_A, errors=4) + far + history()[-1:] + utc + run_ok(T_B)),
                     ("N2", history() + utc_mb + run_ok(T_B))):
        assert verdict(ls)[0] == "OK", name
        with mock.patch.object(H, "_STAMPISH_RE", NEVER):
            st, why = verdict(ls)
            assert st == "OK", (name, st, why)
    # (5) ПРЕДЕЛ (3), записан: метка не в начале строки у текущего простоя, прошлый +01 прожил час и УБИТ — его вход и
    # polling проходят за текущий: OK при простое; штатно остановленный — п.2: NO_POLL. Так же уровень впереди метки.
    for lay in ("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%(levelname)s %(asctime)s %(name)s: %(message)s"):
        f = _alien(layout=lay)
        assert verdict(history() + killed + relog(park, f))[0] == "OK", lay                       # предел (3)
        assert verdict(history() + clean + relog(park, f))[0] == "NO_POLL", lay
    print("    · правило метки r3: repro nolevel → ❌ code 1, один пуш; формы c1 %d → НЕИЗВЕСТНО; цена x3 — только текущий "
          "запуск (в истории ✅); метка только у записи (N1/N2 ✅ и без правила); предел (3) при убитом прошлом записан"
          % n)


def _stray(t0, kind):
    """Второй процесс бота НЕ из юнита (ручной `python bot.py >> splinter.log`, второй экземпляр) пишет тем же форматом в
    тот же файл ПОСЛЕ строк текущего: загрузка, вход OK, polling, post_init; kind — убит / жив (тики) / штатно (остановка
    планировщика). Форма — verify6 test_v6_health_attack: stray."""
    out = run_ok(t0)
    if kind == "жив":
        t = t0 + 300
        while t < NOW - 60:
            out += L(t, INFO, 'Running job "devbot_report (trigger: interval[0:00:45])"',
                     name="apscheduler.executors.default")
            t += 900
    elif kind == "штатно":
        out += stop_line(t0 + 200)
    return out


def test_b12_boot_count_second_writer():
    """r5 · verify6 (repro_v6_second_writer А/Б, regress P1, атака v6 a2/a3): строка загрузки bot.py:94 по месту
    сбрасывает вход и polling выше неё (п.1 r4) — и потому строка загрузки ВТОРОГО процесса, дописанного в тот же файл
    после строк текущего, отдавала его polling MainPID: простой → «✅ ВСЁ ОК» (А), вход без polling → «✅ ВСЁ ОК» (Б).
    Правило r5: строк загрузки (_BOOT_RE: полная запись формата bot.py:73 и дословный текст bot.py:94) с меткой ≥ старта
    юнита больше одной — НЕИЗВЕСТНО «в окне текущего запуска N строк загрузки — писали несколько процессов (второй
    писатель / смена пояса)». Пределы (1) — записаны проверкой: строка загрузки в окне ОДНА и чужая — текущий своей не
    написал (завис до bot.py:94), а вход и polling — второго писателя или одного/нескольких убитых прошлых восточнее (из
    которых строка загрузки в окне только у одного). Строгость шаблона (verify6 m06): текст bot.py:94 в сообщении — не
    строка загрузки. Подделка: запись загрузки — 110 знаков, а строка-продолжение bot.py:572 (text[:100]) — не длиннее 99.
    Нормальные запуски — без новых тревог: цикл рестартов (NRestarts > 0, промежуток ≥ 10 с), прошлый в UTC, прошлый
    стартовал в ту же секунду (x5), шаг часов назад ≤ 120 с, 70a (test_b10)."""
    who = "PID %d, старт %s UTC, рестартов 0" % (PID_B, dt(T_B).strftime("%Y-%m-%d %H:%M:%S"))
    two = "в окне текущего запуска 2 строк загрузки — писали несколько процессов (второй писатель / смена пояса)"
    park = run_park(T_B, words_of(**{STRICT: "0"}))
    second = run_ok(T_B + 30)
    # А: MainPID в простое, через 30 с второй экземпляр (вход OK, polling) убит — build_report()/main(): ❌ code 1, пуш
    lines = history() + park + second
    st, why = verdict(lines)
    assert st == "UNKNOWN" and why.startswith(two) and why.endswith("(%s)" % who), (st, why)
    r = build(lines, B())
    assert r.code == 1 and r.summary.startswith("❌ ПРОБЛЕМА: запуск не доказан — НЕИЗВЕСТНО: " + two), r.summary
    rc, _out, calls = run_main(lines, B())
    assert rc == 1 and len(calls) == 1 and two in calls[0]["text"], (rc, calls)
    with mock.patch.object(H, "_BOOT_RE", NEVER):                     # r3: без строк загрузки — «два входа»
        assert "граница неоднозначна: строк «вход выпуска»" in verdict(lines)[1]
    # Б: MainPID — вход OK без polling, тот же второй экземпляр
    st, why = verdict(history() + run_ok(T_B, poll_at=None, post=False) + second)
    assert st == "UNKNOWN" and why.startswith(two), (st, why)
    # сетка a2: шесть состояний текущего × второй через X с × убит / жив / штатно
    cur = {"завис до bot.py:94": hung_before_94(), "завис после bot.py:94": L(T_B + 0.912, INFO, BOOT_LINE),
           "завис после строк загрузки": boot(T_B, words_of()),
           "завис после входа (до polling)": run_ok(T_B, poll_at=None, post=False), "простой MISMATCH": park,
           "простой UNKNOWN": run_park(T_B, None)}
    seen, limit = {}, {}
    for cname, c in cur.items():
        for X in (2, 30, 120, 250, 298):
            for kind in ("убит", "жив", "штатно"):
                st, why = verdict(history() + c + _stray(T_B + X, kind))
                seen[st] = seen.get(st, 0) + 1
                if cname == "завис до bot.py:94":                    # своей строки загрузки нет — счёт 1
                    want = "NO_POLL" if kind == "штатно" else "OK"
                    assert st == want, (cname, X, kind, st, why)
                    limit[st] = limit.get(st, 0) + 1
                else:
                    assert st == "UNKNOWN" and why.startswith(two), (cname, X, kind, st, why)
    assert limit == {"OK": 10, "NO_POLL": 5} and seen.get("OK") == 10, (limit, seen)   # ПРЕДЕЛ (1): второй писатель
    # P1: два коротких прошлых в +01, оба убиты, строки загрузки обоих в окне (старт + 10,9 и + 50,9 с) — НЕИЗВЕСТНО
    p0 = shift_ts(short_prev(3590, 30, clean=False), 1)
    p1 = shift_ts(short_prev(3550, 30, clean=False), 1)
    pm = shift_ts(short_prev(3620, 25, clean=False), 1)               # третий: все записи раньше старта
    for name, ls in (("два убитых + Memory()", history() + p0 + p1 + hung_before_94()),
                     ("два убитых, текущий — ни строки", history() + p0 + p1),
                     ("три убитых + Memory()", history() + pm + p0 + p1 + hung_before_94())):
        st, why = verdict(ls)
        assert st == "UNKNOWN" and why.startswith(two), (name, st, why)
    r = build(history() + p0 + p1 + hung_before_94(), B())
    assert r.code == 1 and two in r.summary, r.summary
    # ПРЕДЕЛ (1), записан: один убитый прошлый в окне / несколько, из которых строка загрузки в окне у одного — OK
    assert verdict(history() + p1 + hung_before_94())[0] == "OK"
    assert verdict(history() + pm + p1 + hung_before_94())[0] == "OK"
    # атака v6 a3 (r4 — OK): чужие загрузка / вход / polling НИЖЕ строк текущего, с метками в секунду старта
    st, why = verdict(history() + park + run_ok(T_B - 1.0, post=False))
    assert st == "UNKNOWN" and ("строка загрузки bot.py:94 с меткой 2026-10-21 05:59:59 раньше старта юнита стоит ниже "
                                "строки загрузки текущего запуска") in why, (st, why)
    st, why = verdict(history() + L(T_B + 0.912, INFO, BOOT_LINE) + run_ok(T_B - 1.0, post=False)[1:])
    assert st == "UNKNOWN" and ("«вход выпуска» 2026-10-21 06:00:00,003 ниже строки загрузки bot.py:94 по месту, но "
                                "раньше неё по метке (2026-10-21 06:00:00,912)") in why, (st, why)
    st, why = verdict(history() + L(T_B + 0.912, INFO, BOOT_LINE) + run_ok(T_B - 1.0, post=False)[6:])
    assert st == "UNKNOWN" and "polling 2026-10-21 06:00:00,247 ниже строки загрузки" in why, (st, why)
    # пары: тот же порядок по месту, но вход и polling ПОСЛЕ строки загрузки по метке — свой процесс, OK
    assert verdict(history() + L(T_B + 0.912, INFO, BOOT_LINE) + run_ok(T_B, post=False)[1:])[0] == "OK"
    # m06: текст bot.py:94 в сообщении клиента (запись turbobaby, не строка загрузки) — норма остаётся нормой
    norm = history() + prev_run(T_B - 3600, T_B) + run_ok(T_B)
    for text in (BOOT_LINE.strip(), BOOT_LINE, "лог:\n" + BOOT_LINE, "смотри: " + BOOT_LINE.strip()):
        st, why = verdict(norm + _msg(T_B + 3600, text))
        assert st == "OK", (text, st, why)
    # подделка: полную запись загрузки сообщением bot.py:572 не вставить — 23 + 19 + 68 = 110 > 99
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    assert src.count('→ мозг: {text[:100]}")') == 1, "bot.py:572 больше не режет текст до 100 знаков"
    rec94 = L(T_B + 3570, INFO, BOOT_LINE)[0].rstrip("\n")
    parts = (len(rec94.split(" [INFO] ", 1)[0]), len(" [INFO] turbobaby: "), len(BOOT_LINE))
    assert H._BOOT_RE.match(rec94) and parts == (23, 19, 68) and len(rec94) == sum(parts) == 110, (parts, len(rec94))
    for text in ("\n" + rec94, "лог:\n" + rec94):
        ls = norm + _msg(T_B + 3600, text)
        cont = ls[-1].rstrip("\n")
        assert len(cont) <= 99 and not H._BOOT_RE.match(cont), (len(cont), cont)
        assert verdict(ls)[0] == "OK", text
    # нормальные запуски — без новых тревог
    s = T_B
    loop = history()
    for k in (3, 2, 1):
        loop += run_ok(s - 17 * k, post=False) + CRASH_TB            # цикл падений: промежуток 17 с ≥ RestartSec 10 с
    loop += run_ok(s)
    normal = {"цикл рестартов, NRestarts 3": (loop, B(nrestarts=3)),
              "прошлый в UTC прожил сутки": (history() + prev_run(T_B - 86400, T_B) + run_ok(T_B), B()),
              "прошлый стартовал за 1 с (x5)": (history() + run_ok(T_B - 1.0, post=False) + run_ok(T_B), B()),
              "шаг часов назад 119 с в текущем": (history() + run_ok(T_B) + L(T_B + 600, INFO, "тик", name="splinter")
                                                  + L(T_B + 481, INFO, "тик-2", name="splinter"), B()),
              # фазз B build7 (образец ложной тревоги первой редакции правила a3): прошлый в +02 прожил 60 с и убит — его
              # записи по его часам заходят за старт; следующий прошлый в UTC (простой) — строка загрузки раньше старта
              "прошлый +02 за старт, затем прошлый UTC": (history() + shift_ts(short_prev(7245, 60, clean=False), 2)
                                                          + run_park(T_B - 46, words_of(**{STRICT: "0"})) + run_ok(T_B),
                                                          B())}
    for name, (ls, runs) in normal.items():
        r = build(ls, runs)
        assert r.code == 0 and r.row("Polling").startswith("✅ Polling"), (name, r.summary)
    # ПРЕДЕЛ (2б), записан (как r3/r4; фазз B build7 — 1 из 40000): текущий встал между входом и polling, а сообщение
    # bot.py:572 вставило полную строку polling (84 знака ≤ text[:100]) со штампом в окне и после строки загрузки — OK
    poll_rec = L(T_B + 2, INFO, POLL)[0].rstrip("\n")
    assert len(poll_rec) == 84, len(poll_rec)
    ls = history() + run_ok(T_B, poll_at=None, post=False) + _msg(T_B + 60, "лог:\n" + poll_rec)
    assert verdict(ls)[0] == "OK"                                        # предел (2б): ложное зелёное, не тревога
    assert verdict(history() + run_ok(T_B, poll_at=None, post=False))[0] == "NO_POLL"
    print("    · счёт строк загрузки: второй писатель А/Б → ❌ code 1, один пуш; сетка a2 %r (предел (1): %r); P1 два/три "
          "убитых → НЕИЗВЕСТНО; текст bot.py:94 в сообщении — норма; запись загрузки 110 > 99; нормальные запуски %d — ✅"
          % (seen, limit, len(normal)))


def test_b13_premise_words_first_cause():
    """r5 · verify6 cost W6/W7: слова посылки «журнал в UTC» называют первой причиной то, что следует из ПОСЛЕДНЕЙ по месту
    записи начала процесса. Строка загрузки bot.py:94 без строки входа после неё (процесс до неё дошёл и встал) или
    запись позже окна (вышедший до старта процесс по UTC так поздно не пишет) — первой причиной пояс журнала не UTC или
    шаг часов (W6: текущий в +01, W7: в −03). Строка входа прошлого раньше окна — первой «текущий процесс до строки
    загрузки не дошёл» (W1–W3, живой 70a)."""
    prev = history() + prev_run(T_B - 3600, T_B)
    head = "вне окна [старт, старт + 300 с] — "
    zone_boot = (head + "пояс журнала не UTC или шаг часов (последняя запись начала — строка загрузки bot.py:94 без строки"
                 " входа после неё: писавший процесс до неё дошёл)")
    hung = head + "текущий процесс до строки загрузки не дошёл (импорт/конструкторы bot.py:83–85)"
    cases = {"W6 после bot.py:94, текущий в +01": (prev + shift_ts(boot(T_B, words_of()), 1), zone_boot, "+3600 с"),
             "W7 после bot.py:94, текущий в −03": (prev + shift_ts(boot(T_B, words_of()), -3), zone_boot, "-10800 с"),
             "W1 до bot.py:94, ни строки": (prev, hung, "-3599 с"),
             "W3 до bot.py:94, прошлый убит": (history() + _until(prev_run(T_B - 3600, T_B + 10), T_B - 10)
                                               + hung_before_94(), hung, "-3599 с")}
    for name, (ls, want, delta) in cases.items():
        st, why = verdict(ls)
        assert st == "UNKNOWN" and want in why and delta + " от старта юнита" in why, (name, st, why)
    # запись позже окна: прошлый в +02 стартовал за час, штатно остановлен, текущий не написал ничего
    st, why = verdict(history() + shift_ts(short_prev(3600, 60), 2))
    assert st == "UNKNOWN" and (head + "пояс журнала не UTC или шаг часов (запись позже окна: процесс, вышедший до "
                                "старта, по UTC так поздно не пишет)") in why and "+3601 с" in why, (st, why)
    print("    · слова посылки: W6/W7 — первой пояс/часы; W1/W3 — первой «не дошёл»; запись позже окна — пояс/часы")


def _ref_read_log(blob):
    """Разбор журнала r3 дословно (health.py@r3:273–277): весь файл одним куском."""
    parts = blob.decode("utf-8", "surrogateescape").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def test_a12_read_log_chunked_equals_whole():
    """r4 · verify5 п.4: _read_log читает кусками (_READ_CHUNK) и разбирает блоки до последнего «\\n» — результат
    посимвольно равен разбору r3 целиком на любых границах кусков (CRLF и одиночный CR на границе, многобайтовые символы
    и байты не UTF-8 через границу, хвост без перевода строки, пустой файл); пиковая память не выше прежнего
    readlines() (verify4 n7: r3 — 7,0× размера, readlines — 2,25×)."""
    rnd = random.Random(20261021)
    alpha = [b"a", "я".encode(), "🚦".encode(), b"\r", b"\n", b"\r\n", b" ", b"\xff", b"\xd0", b"\xe2\x82",
             b"\x0b", b"\x0c", b"\x1c", b"\x85", " ".encode(), "\x85".encode(),
             "2026-10-21 06:00:01,003 [INFO] turbobaby: x".encode()]
    blobs = [b"", b"\n", b"\r", b"\r\n", b"\r\r\n", b"\n\r", b"a\rb", b"a\r", b"a", "я\r\nя".encode(), b"\xd0\n\x9f"]
    blobs += [b"".join(rnd.choice(alpha) for _ in range(rnd.randint(0, 60))) for _ in range(300)]
    live = "".join(history() + run_ok(T_B, errors=3)).encode("utf-8")
    blobs += [live, live.replace(b"\n", b"\r\n"), live.replace(b"\n", b"\r"), live[:-1], live + b"\xd0\x9f\xff"]
    path = os.path.join(TMP, "chunks.log")
    n = 0
    for chunk in (1, 2, 3, 5, 7, 64, 4096, H._READ_CHUNK):
        with mock.patch.object(H, "LOG", path), mock.patch.object(H, "_READ_CHUNK", chunk):
            for blob in blobs:
                with open(path, "wb") as f:
                    f.write(blob)
                got = H._read_log()
                assert got == (_ref_read_log(blob), None), (chunk, blob[:80], got[0][:5] if got[0] else got)
                n += 1
    # память: журнал живого вида (кириллица + эмодзи) ~4 МБ — пик _read_log не выше прежнего _read_log_lines
    with open(path, "wb") as f:
        for _ in range(max(1, (4 << 20) // len(live))):
            f.write(live)
    peaks = {}
    with mock.patch.object(H, "LOG", path):
        for name, fn in (("_read_log", H._read_log), ("_read_log_lines", H._read_log_lines)):
            tracemalloc.start()
            out = fn()
            peaks[name] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            del out
    size = os.path.getsize(path)
    assert peaks["_read_log"] <= peaks["_read_log_lines"], {k: round(v / size, 3) for k, v in peaks.items()}
    print("    · чтение кусками: %d разборов = r3 посимвольно; пик на %.1f МБ: _read_log %.2f×, readlines %.2f×"
          % (n, size / 2 ** 20, peaks["_read_log"] / size, peaks["_read_log_lines"] / size))


def test_a13_read_log_linear_on_long_lines():
    """r5 · verify6 (regress P4, attack test_v6_read_log_long_line): в r4 каждый кусок склеивался с растущим хвостом
    (buf = tail + chunk) и весь буфер сканировался rfind заново — одна строка 16 МБ без \\n читалась 13,5 с против 0,05 с
    у r3 (квадрат по длине строки). r5 ищет перевод строки только в новом куске, хвост копится списком и склеивается
    один раз. Здесь: одна строка 16 МБ без \\n, журнал 8 МБ только с \\r, та же строка 4 МБ посреди живого журнала —
    разбор посимвольно равен разбору r3 целиком (_ref_read_log), время — порядка r3: потолок 1,5 с с запасом на
    параллельный прогон мутантов (r4 на той же строке — 13,5 с; склейка хвоста на каждом куске — мутант ниже)."""
    path = os.path.join(TMP, "long_line.log")
    live = "".join(history() + run_ok(T_B)).encode("utf-8")
    cases = {"одна строка 16 МБ без \\n": b"x" * (16 << 20),
             "только \\r, 8 МБ": b"2026-10-21 06:00:00,000 [INFO] x: y\r" * ((8 << 20) // 37),
             "строка 4 МБ посреди живого журнала": live + b"2026-10-21 06:30:00,000 [INFO] splinter: dump " + b"y" * (
                 4 << 20) + b"\n" + live}
    times = {}
    for name, blob in cases.items():
        with open(path, "wb") as f:
            f.write(blob)
        with mock.patch.object(H, "LOG", path):
            t0 = time.perf_counter()
            got = H._read_log()
            t_read = time.perf_counter() - t0
        t0 = time.perf_counter()
        ref = _ref_read_log(blob)
        t_ref = time.perf_counter() - t0
        assert got == (ref, None), (name, None if got[0] is None else len(got[0]), len(ref))
        times[name] = (round(t_read, 3), round(t_ref, 3))
        assert t_read <= 1.5, (name, t_read, t_ref)
    with open(path, "wb") as f:                                        # 16 МБ во временном каталоге не держим
        f.write(b"")
    print("    · _read_log на длинных строках (r5, r3-разбор): %r" % times)


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


def test_y_no_live_reads():
    """h3 (изоляция): за весь прогон health не открыл ни одного файла вне временного каталога и не запустил ни одного
    процесса мимо FakeSystemd (сторожа LIVE); пути модуля — во временном каталоге. Замок: каждая функция health, которую
    зовёт build_report, подменена в world() — NET, subprocess.run → FakeSystemd (_read_run, check_service), LOG → TMP
    (_read_log) — или чистая."""
    assert LIVE == {"open": [], "run": []}, LIVE
    for p in (H.LOG, H._WA_PROBE_FAIL_FILE, H._CREDIT_EPISODE_FILE):
        assert os.path.normcase(os.path.abspath(p)).startswith(_TMPN + os.sep), p
    assert H.__dict__.get("open") is _guard_open and H.subprocess.run is _guard_run, (H.__dict__.get("open"),
                                                                                     H.subprocess)
    tree = ast.parse(open(H.__file__, encoding="utf-8").read())
    defs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    br = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_report"][0]
    called = {n.func.id for n in ast.walk(br) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id in defs}
    covered = set(NET) | {"_read_run", "check_service", "_read_log"}
    pure = {"check_auditor", "check_polling", "check_log_health", "_recheck_run", "_utcnow"}
    assert "_read_log" in called and not (called - covered - pure), sorted(called - covered - pure)


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
    # h3 · verify4 n6a: строка загрузки bot.py:94 — запись начала процесса для посылки health (_BOOT_MSG): дословно
    # одна, на верхнем уровне модуля (без условия), после basicConfig и до main(), и ПЕРВЫЙ вызов log.* после
    # basicConfig
    boot_call = 'log.info("%s")' % H._BOOT_MSG
    assert H._BOOT_MSG == BOOT_LINE and src.count(boot_call) == 1, "строка загрузки bot.py:94 изменилась"
    seg_of = lambda n: ast.get_source_segment(src, n) or ""          # noqa: E731
    top = [i for i, n in enumerate(tree.body) if isinstance(n, ast.Expr) and seg_of(n) == boot_call]
    cfg = [i for i, n in enumerate(tree.body) if isinstance(n, ast.Expr) and "logging.basicConfig(" in seg_of(n)]
    i_main = [i for i, n in enumerate(tree.body) if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert len(top) == 1 and len(cfg) == 1 and cfg[0] < top[0] < i_main[0], (top, cfg, i_main)
    between = [n for n in tree.body[cfg[0] + 1:top[0]] for c in ast.walk(n) if isinstance(c, ast.Call)
               and isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
               and c.func.value.id == "log"]
    assert not between, [seg_of(n) for n in between]


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
    new_fns = {"_read_run", "_run_key", "_run_word", "_run_verdict", "check_polling", "build_report", "main",
               "_read_log", "_systemd_utc", "_recheck_run", "check_service"}
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


def test_d7_systemd_zone_one_utc_scale():
    """verify3 x6: метка systemd — с её поясом на шкалу UTC (прежде _read_run отвергал любой пояс ≠ UTC, а
    check_service пояс молча отбрасывал: «13:00:00 +07» читалось как 13:00 UTC). Пары живого формата systemctl show:
    сервер в +07, журнал бота в UTC — граница прочитана, ✅; сервер и журнал бота оба в +07 (asctime = localtime
    процесса) — пояс журнала не UTC → НЕИЗВЕСТНО; буквенный пояс — граница не прочитана."""
    want = dt(int(T_B))                                        # 2026-10-21 06:00:00 UTC, среда
    for raw, exp in (("Wed 2026-10-21 06:00:00 UTC", want), ("Wed 2026-10-21 06:00:00 GMT", want),
                     ("Wed 2026-10-21 13:00:00 +07", want), ("Wed 2026-10-21 03:00:00 -03", want),
                     ("Wed 2026-10-21 11:45:00 +0545", want), ("  Wed 2026-10-21 06:00:00 UTC\n", want),
                     ("Wed 2026-10-21 09:00:00 MSK", None), ("Wed 2026-10-21 11:30:00 IST", None),
                     ("Wed 2026-10-21 21:00:00 +15", None), ("Wed 2026-10-21 06:00:00 +0560", None),
                     ("Wed 2026-10-21 06:00:00", None), ("Wed 2026-10-21 06:00:00.123456 UTC", None),
                     ("Wed 2026-10-21 06:00:00 UTC extra", None), ("Wed 2026-13-21 06:00:00 UTC", None),
                     ("n/a", None), ("", None), (None, None)):
        assert H._systemd_utc(raw) == exp, (raw, H._systemd_utc(raw), exp)
    p7 = dict(props_of(PID_B, T_B), ExecMainStartTimestamp=stamp(T_B, "+07", 7),
              ActiveEnterTimestamp=stamp(T_B, "+07", 7))
    assert p7["ExecMainStartTimestamp"] == "Wed 2026-10-21 13:00:00 +07", p7
    r7 = run_of(p7)
    assert r7 is not None and r7["start"] == want and r7["start_raw"] == "Wed 2026-10-21 13:00:00 +07", r7
    lines = history() + run_ok(T_B)
    r = build(lines, [p7, p7])
    assert r.code == 0 and r.summary == "✅ ВСЁ ОК", r.summary
    assert r.row("Polling").endswith("PID %d, старт 2026-10-21 06:00:00 UTC, рестартов 0" % PID_B), r.row("Polling")
    assert "uptime 2ч0м" in r.report, r.report               # check_service на той же шкале
    with world([], [p7, p7]):
        ok, detail, start_dt, nr = H.check_service()
    assert ok and start_dt == want and detail == "active/running, uptime 2ч0м, рестартов 0", (start_dt, detail)
    # пара: и systemd, и журнал бота в +07 — метки журнала «впереди часов» → НЕИЗВЕСТНО, а не зелёное
    r = build(shift_ts(lines, 7), [p7, p7])
    assert r.code == 1 and "запуск не доказан — НЕИЗВЕСТНО" in r.summary and "впереди часов" in r.summary, r.summary
    # буквенный пояс — граница не прочитана (не молчаливое UTC)
    pm = dict(props_of(PID_B, T_B), ExecMainStartTimestamp=stamp(T_B, "MSK", 3))
    assert run_of(pm) is None
    r = build(lines, [pm, pm])
    assert r.code == 1 and "НЕИЗВЕСТНО: граница запуска не прочитана" in r.summary, r.summary


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
    ("    status, why = _run_verdict(lines, run0, run1, now if now is not None else _utcnow(), log_err)\n",
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
    # verify3 x6 — шкала UTC: пояс systemd разбирается, порядок записей и метки журнала сверяются
    ("    else:\n        return None     # буквенный пояс / сдвиг вне шкалы — граница не доказана\n",
     "    else:\n        minutes = 0     # буквенный пояс / сдвиг вне шкалы — граница не доказана\n",
     "буквенный пояс systemd — молчаливое UTC",
     ("test_d6_read_run_live_format", "test_d7_systemd_zone_one_utc_scale", "test_a4_boundary_unavailable_is_unknown")),
    ("    return (local - datetime.timedelta(minutes=minutes))", "    return (local - datetime.timedelta(minutes=0))",
     "сдвиг пояса systemd не применяется", ("test_d7_systemd_zone_one_utc_scale",)),
    ('    start_dt = _systemd_utc(props.get("ExecMainStartTimestamp", ""))\n',
     '    start_dt = _systemd_utc(props.get("ExecMainStartTimestamp", "").rsplit(" ", 1)[0] + " UTC")\n',
     "check_service отбрасывает пояс (прежнее поведение)", ("test_d7_systemd_zone_one_utc_scale",)),
    ("        if rec and ts is not None and hi is not None and ts < hi - back:\n", "        if False:\n",
     "порядок записей журнала не сверяется (12 зелёных x6)", ("test_b6_zone_switch_between_processes",)),
    ("        if rec and ts is None and cur is not None and cur >= start:\n", "        if False:\n",
     "запись с неразобранной меткой в сегменте не замечается", ("test_b6_zone_switch_between_processes",)),
    # verify3 x2 — третье чтение границы перед вердиктом
    ("_read_run(), (svc_ok, start_dt, svc_nr))", "run1, (svc_ok, start_dt, svc_nr))",
     "граница перед вердиктом не перечитывается", ("test_a9_boundary_rechecked_before_verdict",)),
    ('    return False, "запуск не доказан — НЕИЗВЕСТНО: " + why + "; прежний вердикт: " + pl_d\n',
     "    return pl_ok, pl_d\n", "сверка перед вердиктом без последствий",
     ("test_a9_boundary_rechecked_before_verdict",)),
    ("    elif svc != (", "    elif False and svc != (", "строка сервиса не сверяется с границей",
     ("test_a9_boundary_rechecked_before_verdict",)),
    # verify3 x4 — «не прочитан» ≠ «нет строк»
    ('        return None, "не прочитан (" + type(e).__name__ + ")"\n', "        return [], None\n",
     "непрочитанный журнал = пустой (прежняя форма)", ("test_a10_log_unread_truncated_unparsed_vs_empty",)),
    ("    if got < size0 or size1 < size0:\n", "    if False:\n", "обрезанное чтение не замечается",
     ("test_a10_log_unread_truncated_unparsed_vs_empty",)),
    ("        if _SURR_RE.search(ln):\n", "        if False:\n", "байты не UTF-8 в сегменте не замечаются",
     ("test_a10_log_unread_truncated_unparsed_vs_empty",)),
    ("        problems.append(pl_d)\n", '        problems.append("нет polling")\n', "в сводке прежнее «нет polling»",
     ("test_a1_old_polling_new_park_mismatch", "test_a4_boundary_unavailable_is_unknown")),
    ("    run1 = _read_run()\n", "    run1 = run0\n", "граница из одного чтения",
     ("test_a5_boundary_changed_between_reads",)),
    # h3 · verify4 n6a — посылка «журнал в UTC» для текущего запуска
    ('    if gap is not None:\n        return "UNKNOWN", gap\n', '    if False:\n        return "UNKNOWN", gap\n',
     "вердикт по строкам без посылки (_gate снят)", ("test_b7_premise_current_run_east_zone",)),
    ("    if start <= mark <= start + datetime.timedelta(seconds=_START_SKEW_S):\n", "    if True:\n",
     "окно посылки снято (любая запись начала подтверждает)",
     ("test_b7_premise_current_run_east_zone", "test_b2_window_and_clock")),
    ("        if not stamped:\n            return None\n", "        if True:\n            return None\n",
     "журнал без записи начала — посылка подтверждена", ("test_b7_premise_current_run_east_zone",)),
    ("        if rec and ts is not None and (_BOOT_RE.match(ln) or _ENTRY_RE.match(ln)):\n",
     "        if rec and ts is not None and _ENTRY_RE.match(ln):\n", "строка загрузки bot.py:94 — не запись начала",
     ("test_b7_premise_current_run_east_zone",)),
    ("            mark = ts                      # последняя по месту",
     "            mark = mark or ts              # последняя по месту",
     "первая по месту запись начала вместо последней",
     ("test_b7_premise_current_run_east_zone", "test_a3_normal_current_run_as_before")),
    # h3 · verify4 n2a/n2b — метка неизвестной формы
    ("                if cur is not None and cur >= start:\n"
     '                    return "UNKNOWN", _unparsed_words(ln, who)\n',
     '                if False:\n                    return "UNKNOWN", _unparsed_words(ln, who)\n',
     "метка неизвестной формы в сегменте — невидимый текст (n2a)", ("test_b8_unknown_stamp_form_is_unknown",)),
    ("                if pend is None and own is not None and own >= start:\n", "                if False:\n",
     "метка неизвестной формы до сегмента не замечается (n2b)", ("test_b8_unknown_stamp_form_is_unknown",)),
    ("            pend = None                    # за меткой", "            pass                           # за меткой",
     "запись истории не снимает метку неизвестной формы (ложная тревога)", ("test_b8_unknown_stamp_form_is_unknown",)),
    # h3 · verify4 r4 — строка Аудитор при непрочитанном журнале
    ("    if log_err is not None:     # h3 · verify4 r4", "    if False:     # h3 · verify4 r4",
     "строка Аудитор при непрочитанном журнале — «нет ✅»", ("test_a11_auditor_row_unread_journal",)),
    # r4 · verify5 Q1 — строка загрузки bot.py:94 по месту начинает новый процесс
    ("        if rec and ts is not None and _BOOT_RE.match(ln):\n            entries, polls = [], []",
     "        if False:\n            entries, polls = [], []", "строка загрузки не начинает новый процесс (verify5 Q1)",
     ("test_b9_boot_line_starts_new_process", "test_b3_same_second_as_start")),
    # r4 · verify5 п.2 — остановка планировщика ниже polling завершает процесс того polling (отделимое правило)
    ("        elif polls and _SHUT_RE.match(ln):\n", "        elif False:\n",
     "остановка планировщика не завершает процесс (п.2)", ("test_b10_scheduler_stop_ends_process",)),
    # r5 · verify6 c1 — правило метки r3 (сужение п.3 r4 откачено) и метка только у записи (cost N1/N2)
    ("            if sm is not None:             # h3 · verify4 n2 (r5",
     "            if sm is not None and False:  # h3 · verify4 n2 (r5",
     "метко-подобный префикс — текст (правило метки снято)",
     ("test_b8_unknown_stamp_form_is_unknown", "test_b11_stamp_prefix_rule_r3_restored")),
    ("        ts = _parse_log_ts(ln) if rec else None", "        ts = _parse_log_ts(ln)",
     "метку даёт и продолжение «,ммм» (cost N1/N2)", ("test_b11_stamp_prefix_rule_r3_restored",)),
    # r5 · verify6 — счёт строк загрузки в окне текущего запуска
    ("    if boots > 1:", "    if False:", "счёт строк загрузки снят (второй писатель А/Б, P1)",
     ("test_b12_boot_count_second_writer", "test_b9_boot_line_starts_new_process")),
    ("            if ts >= start:\n                boots += 1", "            if True:\n                boots += 1",
     "строки загрузки считаются по всему журналу, а не в окне", ("test_a3_normal_current_run_as_before",
                                                                 "test_b12_boot_count_second_writer")),
    ('_BOOT_RE = re.compile(r"^" + _LOG_TS + r" \\[INFO\\] turbobaby: " + re.escape(_BOOT_MSG) + r"$", re.ASCII)',
     '_BOOT_RE = re.compile(r".*" + re.escape(_BOOT_MSG.strip()), re.ASCII)',
     "строка загрузки подстрокой (verify6 m06)", ("test_b12_boot_count_second_writer",)),
    # r5 · verify6 a3 — порядок внутри процесса
    ("        if rec and ts is not None and ts < start and boots > 0 and _BOOT_RE.match(ln):\n",
     "        if False:\n", "строка загрузки раньше старта ниже записей текущего — не замечается (a3)",
     ("test_b12_boot_count_second_writer",)),
    ("        if boot_ts is not None and (ts, ln[20:23]) < boot_ts and (m or _POLL_RE.match(ln)):\n",
     "        if False:\n", "вход/polling раньше строки загрузки над ними — не замечается (a3)",
     ("test_b12_boot_count_second_writer",)),
    # r5 · verify6 — п.2: слова сброса, сброс только ниже polling, только [INFO]
    ("        if shut is not None:", "        if False:", "сброс остановкой назван «нет строки» (слова п.2)",
     ("test_b10_scheduler_stop_ends_process",)),
    ("        elif polls and _SHUT_RE.match(ln):\n", "        elif _SHUT_RE.match(ln):\n",
     "остановка сбрасывает и без polling выше (verify6 m02)", ("test_b10_scheduler_stop_ends_process",)),
    ('r" \\[INFO\\] apscheduler\\.scheduler: Scheduler has been shut down$"',
     'r" \\[[A-Z]+\\] apscheduler\\.scheduler: Scheduler has been shut down$"',
     "остановка любого уровня (verify6 m16)", ("test_b10_scheduler_stop_ends_process",)),
    # r5 · verify6 cost W6/W7 — слова посылки
    ("    if mark_boot or mark > start:\n", "    if False:\n", "посылка: первой причиной всегда «не дошёл» (W6/W7)",
     ("test_b13_premise_words_first_cause",)),
    # r4 · verify5 п.4 / r5 · verify6 — чтение журнала кусками, линейно
    ("                chunk = f.read(size)\n", "                chunk = f.read()\n",
     "журнал одним куском (пик памяти r3)", ("test_a12_read_log_chunked_equals_whole",)),
    ("                    tail = [chunk[cut:]]\n", "                    tail = []\n",
     "хвост куска без перевода строки теряется", ("test_a12_read_log_chunked_equals_whole",)),
    ("                    tail.append(chunk)\n                    size = min(size * 2, _READ_GROW_MAX)",
     '                    tail = [b"".join(tail) + chunk]',
     "хвост склеивается на каждом куске 8 КиБ (квадрат r4)", ("test_a13_read_log_linear_on_long_lines",)),
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
