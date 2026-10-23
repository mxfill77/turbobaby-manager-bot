#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RCFIX2010 п.4 (Codex TB-QA-2010C-ENV-2011): ВХОД ВЫПУСКА Splinter — кортеж ручек выпуска доказывается словом процесса
ДО бизнес-обработчиков, а не только строкой журнала после старта.

Повод: CLOSE_TRUTH, CLOSE_ACCRUAL и HANDOVER_FACTS впервые читает вершина RC2010; скрипт рестарта (srv_splinter_restart5_r7,
библиотека srv_splinter_checks_rc2010.sh 4afe3e88) узнаёт их состояние только из строки «🧩 флаги выпуска» ПОСЛЕ старта и
остановить работу до первого побочного эффекта не может. Теперь bot.main() первым оператором зовёт
`splinter.release_entry(_RELEASE_WORDS, _UNIT_FLAG_KEYS)`: те же слова, что напечатаны строкой флагов, сверяются с КОНЕЧНЫМ
перечнем `RELEASE_ENTRY_STATES` (release — шаг 4 и снятие R0; truth_off — R0, CLOSE_TRUTH=0 из окружения юнита); иное или
неизвестное → одна строка [ERROR] «🚦 вход выпуска: MISMATCH|UNKNOWN — <ИМЯ OK|MISMATCH|UNKNOWN> …», обработчики не
регистрируются, опрос не начинается, процесс ПРОСТАИВАЕТ до остановки (`_park_until_stop`): юнит стоит на Restart=always,
выход дал бы вечный цикл стартов, а простой — устойчивый PID и одну строку; r7 на нём кончится exit 3 («Bot polling started»
0), ложного «чисто» нет.

Разделы:
  A — эквивалентность с библиотекой рестарта: шаблоны SC_FLAGS_RE_* — ДОСЛОВНАЯ копия srv_splinter_checks_rc2010.sh :52–54
      (sha 4afe3e88…; при RCFIX_TUPLE_LIB=<путь> копия сверяется с файлом); на сетке из 2000 сочетаний пяти ручек × источник
      «юнит / не юнит»: release ⇔ шаблон release; truth_off ⇔ шаблон truth_off И CLOSE_TRUTH из юнита; hofacts_on — стоп;
  B — именованные режимы: умолчания, R0 truth_off, R0 undo, R0 restart, всё задано явно — допуск как прежде; каждая ручка
      MISMATCH / UNKNOWN — стоп с именем ровно этой ручки; слова не прочитаны / не тот набор / мусор — UNKNOWN; перечень
      конечен (два состояния, hofacts_on и вкл-слова CLOSE_ACCRUAL / HANDOVER_FACTS не входят, CLOSE_TRUTH=0 входит);
  C — чистота: строка статуса — полный разбор по замкнутой грамматике (имена, OK/MISMATCH/UNKNOWN, фиксированные фразы);
      приманка-значение не печатается; литералов читателей журнала нет; строка флагов байт-в-байт прежняя; проверка только
      читает (ast: нет getenv / записи окружения; окружение после вызова то же);
  D — порядок по исходнику bot.py (ast): имена юнита — до load_dotenv; один снимок слов на строку и на вход; в main() вход —
      body[0], стоп — body[1] (простой и return), всё о регистрации и опросе — ниже стопа; в простое нет выхода;
  E — инструментированный main(): допуск → прежние 22 обработчика + наблюдатель правок CRM (23 всего), 5 ежедневных и 4 повторяющихся задач,
      run_polling последним), строка допуска — первым событием; стоп → события ровно [строка ERROR, простой];
  F — дети: настоящий импорт bot.py с окружением «юнита» и строкой «.env» (заглушка load_dotenv с правилом override=False):
      CLOSE_TRUTH=0 из юнита — truth_off; из .env — стоп при той же строке флагов, которую принял бы шаблон r7 truth_off;
      HANDOVER_FACTS=1 — стоп при строке, которую принял бы шаблон hofacts_on; строка флагов не прочитана — стоп UNKNOWN;
  G — простой не возвращается и не выходит; SIGTERM процессом до main() не перехвачен (systemctl stop действует);
  Z — мутанты правки (по одному на место): каждый роняет хотя бы одну проверку своего места; нулевой мутант зелёный.
Сети, моста, Telegram, мозга и боевых файлов нет: тяжёлые зависимости bot.py — заглушки до импорта (как
tests/test_restart_drain_accept.py), состояние — во временном каталоге, Application — регистратор.
Прогон: venv/Scripts/python.exe tests/test_rcfix2010_tuple.py → «ИТОГ N/M»."""
import ast
import contextlib
import datetime as _dt
import hashlib
import json
import logging
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import types
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.environ.get("RCFIX_TUPLE_SRC", "")          # мутант: каталог с подменённым bot.py / splinter.py
CHILD = os.environ.get("RCFIX_TUPLE_CHILD", "")      # ребёнок раздела F: имя сценария
ONLY = [x for x in os.environ.get("RCFIX_TUPLE_ONLY", "").split(",") if x]
sys.path.insert(0, ROOT)
if SRC:
    sys.path.insert(0, SRC)


def _src(name):
    p = os.path.join(SRC, name) if SRC else ""
    return p if p and os.path.exists(p) else os.path.join(ROOT, name)


STRICT, GEN, TRUTH, ACCR, HOF = "INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN", "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS"
KEYS = (STRICT, GEN, TRUTH, ACCR, HOF)
_SCRUB = KEYS + ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB")
if not CHILD:                                        # ребёнку окружение «юнита» задаёт родитель
    for _f in _SCRUB:
        os.environ.pop(_f, None)

TMP = tempfile.mkdtemp(prefix="rcfix_tuple_")
os.environ["BRIDGE_URL"] = "http://x"
os.environ["BRIDGE_TOKEN"] = "x"
os.environ["BOT_TOKEN"] = "x"
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


class _Mem:
    def all_topic_bikes(self):
        return {}

    def all_info_pins(self):
        return {}


class _Any:
    audit_groups = []

    def __init__(self, *a, **k):
        pass

    def set_audit_config(self, *a, **k):
        pass


def _load_dotenv_stub(*a, **k):
    """Заглушка python-dotenv: строки «.env» ребёнка (RCFIX_TUPLE_DOTENV="К=З,…") по правилу override=False — ключ, уже
    заданный окружением процесса (юнитом), не перекрывается. Настоящий .env не читается никогда."""
    for kv in [x for x in os.environ.get("RCFIX_TUPLE_DOTENV", "").split(",") if x]:
        key, val = kv.split("=", 1)
        os.environ.setdefault(key, val)
    return True


_stub("dotenv", load_dotenv=_load_dotenv_stub)
_stub("bridge_client", BridgeClient=lambda *a, **k: _Any(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=_Any)
_stub("memory", Memory=_Mem)
_stub("auditor", Auditor=_Any)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")


class _Cap(logging.Handler):
    """Журнал процесса: все записи (уровень, текст); во время main() — ещё и в общий список событий `sink`."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []
        self.sink = None

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            msg = str(record.msg)
        self.lines.append((record.levelname, msg))
        if self.sink is not None:
            self.sink.append(("log", record.levelname, msg))


CAP = _Cap()
# Обработчик — ДО импорта bot: строка флагов пишется на импорте. basicConfig bot.py при уже стоящем обработчике ничего не
# делает, поэтому уровень корня — здесь (INFO, как у bot.py), а консоль молчит.
logging.getLogger().addHandler(CAP)
logging.getLogger().setLevel(logging.INFO)

if CHILD == "words_raise":                           # F: строка флагов не прочитана — сбой release_flags_words на импорте
    import splinter as _S0

    def _boom_words():
        raise RuntimeError("стенд: слова ручек не сняты")
    _S0.release_flags_words = _boom_words

import bot  # noqa: E402

S = bot.splinter
SIGTERM_AFTER_IMPORT = signal.getsignal(signal.SIGTERM)

# ======================================================================================================================
# A. Библиотека рестарта: ДОСЛОВНО srv_splinter_checks_rc2010.sh :52–54 (ERE grep -E, LC_ALL=C), sha файла — LIB_SHA.
# ======================================================================================================================
LIB_SHA = "4afe3e88281bff0f5aeda29045b8af9a082c3334d60a3d76f3e5abe16df73f1a"
SC_FLAGS_RE_RELEASE = (r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)"
                       r" · CLOSE_TRUTH=ВКЛ \((не )?задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\)"
                       r" · HANDOVER_FACTS=ВЫКЛ \((не )?задан\)$")
SC_FLAGS_RE_TRUTH_OFF = (r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)"
                         r" · CLOSE_TRUTH=ВЫКЛ \(задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\)"
                         r" · HANDOVER_FACTS=ВЫКЛ \((не )?задан\)$")
SC_FLAGS_RE_HOFACTS_ON = (r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)"
                          r" · CLOSE_TRUTH=ВКЛ \((не )?задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\)"
                          r" · HANDOVER_FACTS=ВКЛ \(задан\)$")
RX_REL, RX_TOFF, RX_HOF = (re.compile(SC_FLAGS_RE_RELEASE), re.compile(SC_FLAGS_RE_TRUTH_OFF),
                           re.compile(SC_FLAGS_RE_HOFACTS_ON))
# R0 (srv_splinter_truthoff_bf85964_r4.sh :143/:145): drop-in «Environment=CLOSE_TRUTH=0», снятие — «Environment=CLOSE_TRUTH=1».
R0_APPLY, R0_UNDO = "0", "1"

HEAD = "🚦 вход выпуска: "
TAIL = "; перечень выпуска release | truth_off; обработчики не зарегистрированы, опрос не начат — процесс ждёт остановки"
WHY_SRC = "CLOSE_TRUTH выключен не окружением юнита (truth_off — только drop-in R0)"
_KEYS_RE = " · ".join("%s (?:OK|MISMATCH|UNKNOWN)" % k for k in KEYS)
_WHY_RE = "|".join(re.escape(w) for w in ("флаги выпуска не прочитаны", "набор ручек не тот", WHY_SRC,
                                           "сочетание не из перечня"))
LINE_GRAMMAR = re.compile(
    "(?:" + re.escape(HEAD) + "OK — состояние (?:release|truth_off) · " + _KEYS_RE + ")"
    "|(?:" + re.escape(HEAD) + "(?:MISMATCH|UNKNOWN) — " + _KEYS_RE + "(?:; (?:" + _WHY_RE + "))*" + re.escape(TAIL) + ")"
    "|(?:" + re.escape(HEAD) + r"UNKNOWN — сбой проверки \([A-Za-z_][A-Za-z0-9_]*\)" + re.escape(TAIL) + ")")
READER_LITERALS = ("🧩 флаги выпуска:", "Bot polling started", "🔁 передача карточек:", "Traceback", "[ERROR]",
                   "Splinter [intake] ", "🆕 INTAKE", "карточка активации во Входящие", "карточка закрытия во Входящие",
                   "Auditor: ", "Топики: ", "Scheduled ")
BAIT = "Zq9-bait-VALUE-7731"


class _Env:
    """Ручки на время проверки; прежнее окружение возвращается всегда."""

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
    """Слова пяти ручек при заданном окружении (не названные — не заданы)."""
    env = {k: None for k in KEYS}
    env.update(kv)
    with _Env(env):
        return S.release_flags_words()


def per_flag(line):
    """{имя: OK|MISMATCH|UNKNOWN} из строки статуса."""
    return {k: m.group(1) for k in KEYS for m in [re.search(re.escape(k) + r" (OK|MISMATCH|UNKNOWN)", line)] if m}


def verdict(line):
    m = re.match(re.escape(HEAD) + r"(OK|MISMATCH|UNKNOWN) — ", line)
    return m.group(1) if m else None


def _old_line():
    """Строка флагов ДО правки — дословно splinter.release_flags_line @4b12f1d (splinter.py:248–255)."""
    _ho_on = S._handover_facts_on()
    _ho_why = "rental_case_rules не загрузился" if (S._rc_on(S.F_HANDOVER_FACTS) and not _ho_on) else None
    return ("🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=%s · %s=%s · CLOSE_TRUTH=%s · CLOSE_ACCRUAL=%s · %s=%s"
            % (S._flag_word("INTAKE_CONFIRM_STRICT", S._intake_confirm_strict_on(), S._FLAG_WORDS_STRICT),
               S.F_CONTRACT_REF_GEN, S._flag_word(S.F_CONTRACT_REF_GEN, S._rc_on(S.F_CONTRACT_REF_GEN), S._FLAG_WORDS_RC),
               S._flag_word("CLOSE_TRUTH", S._close_truth_on(), S._FLAG_WORDS_TRUTH),
               S._flag_word("CLOSE_ACCRUAL", S._close_accrual_on(), S._FLAG_WORDS_TRUTH, S._accrual_off_why()),
               S.F_HANDOVER_FACTS, S._flag_word(S.F_HANDOVER_FACTS, _ho_on, S._FLAG_WORDS_RC, _ho_why)))


GRID = {STRICT: (None, "1", "0", "maybe", " Да "), GEN: (None, "0", "1", "да", "OFF"),
        TRUTH: (None, "1", "0", "maybe", "Off"), ACCR: (None, "0", "1", "maybe"), HOF: (None, "0", "1", "enabled")}


def _grid():
    out = []

    def rec(i, acc):
        if i == len(KEYS):
            out.append(dict(acc))
            return
        for v in GRID[KEYS[i]]:
            acc[KEYS[i]] = v
            rec(i + 1, acc)
    rec(0, {})
    return out


_GRID_CACHE = []


def grid_cases():
    """(окружение, слова, строка флагов) на сетке A — один раз на процесс."""
    if not _GRID_CACHE:
        for env in _grid():
            w = words_of(**env)
            _GRID_CACHE.append((env, w, S.release_flags_line(w)))
    return _GRID_CACHE


def test_a0_library_copy_verbatim():
    """Копия шаблонов — дословно строки :52–54 библиотеки с sha LIB_SHA (если путь дан в RCFIX_TUPLE_LIB)."""
    p = os.environ.get("RCFIX_TUPLE_LIB", "")
    if not p:
        print("    · библиотека не дана (RCFIX_TUPLE_LIB) — сверка копии с файлом пропущена, копия закреплена текстом")
        return
    raw = open(p, "rb").read()
    assert hashlib.sha256(raw).hexdigest() == LIB_SHA, hashlib.sha256(raw).hexdigest()
    lines = raw.decode("utf-8").splitlines()
    assert lines[51] == "SC_FLAGS_RE_RELEASE='%s'" % SC_FLAGS_RE_RELEASE, lines[51]
    assert lines[52] == "SC_FLAGS_RE_TRUTH_OFF='%s'" % SC_FLAGS_RE_TRUTH_OFF, lines[52]
    assert lines[53] == "SC_FLAGS_RE_HOFACTS_ON='%s'" % SC_FLAGS_RE_HOFACTS_ON, lines[53]
    print("    · библиотека %s: sha %s…, строки 52–54 = копия теста" % (os.path.basename(p), LIB_SHA[:8]))


def test_a1_grid_equivalence_with_library():
    """release ⇔ шаблон release; truth_off ⇔ шаблон truth_off И CLOSE_TRUTH из юнита; шаблон hofacts_on — стоп всегда."""
    n = {"release": 0, "truth_off": 0, "truth_off_not_unit": 0, "hofacts": 0, "stop": 0}
    for env, w, line in grid_cases():
        set_keys = frozenset(k for k, v in env.items() if v is not None)
        for unit in (set_keys, frozenset()):
            state, sline = S.release_entry(w, unit)
            rel, toff, hof = bool(RX_REL.search(line)), bool(RX_TOFF.search(line)), bool(RX_HOF.search(line))
            want = "release" if rel else ("truth_off" if (toff and TRUTH in unit) else None)
            assert state == want, (env, sorted(unit), line, sline)
            assert (state is not None) == (verdict(sline) == "OK"), sline
            if hof:
                assert state is None, (env, line)
                n["hofacts"] += 1
            if state == "release":
                n["release"] += 1
            elif state == "truth_off":
                n["truth_off"] += 1
            else:
                n["stop"] += 1
                if toff:
                    n["truth_off_not_unit"] += 1
    assert all(v > 0 for v in n.values()), n
    print("    · сетка %d сочетаний × 2 источника: %s" % (len(grid_cases()), n))


# ======================================================================================================================
# B. Именованные режимы.
# ======================================================================================================================

def test_b1_defaults_release():
    state, line = S.release_entry(words_of(), frozenset())
    assert state == "release", line
    assert line == HEAD + "OK — состояние release · " + " · ".join("%s OK" % k for k in KEYS), line


def test_b2_r0_truth_off_and_restart():
    """R0 apply (drop-in CLOSE_TRUTH=0) и R0 restart по своему файлу — truth_off, допуск."""
    w = words_of(**{TRUTH: R0_APPLY})
    assert dict(w)[TRUTH] == "ВЫКЛ (задан)", w
    for unit in (frozenset({TRUTH}), frozenset(KEYS)):
        state, line = S.release_entry(w, unit)
        assert state == "truth_off", line
        assert line.startswith(HEAD + "OK — состояние truth_off · "), line


def test_b3_r0_undo_and_restart_is_release():
    """R0 undo (второй drop-in CLOSE_TRUTH=1, применяется позже) и restart с обоими файлами — release, как и зовёт r7."""
    w = words_of(**{TRUTH: R0_UNDO})
    assert dict(w)[TRUTH] == "ВКЛ (задан)", w
    for unit in (frozenset({TRUTH}), frozenset()):
        state, line = S.release_entry(w, unit)
        assert state == "release", line


def test_b4_release_with_every_handle_set_explicitly():
    for env in ({STRICT: "1", GEN: "0", TRUTH: "1", ACCR: "0", HOF: "0"},
                {STRICT: "да", GEN: "no", TRUTH: "yes", ACCR: "false", HOF: "off"},
                {STRICT: " TRUE ", GEN: "", TRUTH: "on", ACCR: "нет", HOF: "нет"}):
        for unit in (frozenset(KEYS), frozenset()):
            state, line = S.release_entry(words_of(**env), unit)
            assert state == "release", (env, line)


def test_b5_truth_off_not_from_unit_stops():
    """CLOSE_TRUTH=0 строкой .env (ключа у юнита нет) — не R0: стоп MISMATCH, названа ровно CLOSE_TRUTH и причина."""
    w = words_of(**{TRUTH: "0"})
    state, line = S.release_entry(w, frozenset())
    assert state is None and verdict(line) == "MISMATCH", line
    assert per_flag(line) == {STRICT: "OK", GEN: "OK", TRUTH: "MISMATCH", ACCR: "OK", HOF: "OK"}, line
    assert WHY_SRC in line, line


MISMATCH_CASES = (
    ({STRICT: "0"}, frozenset(), STRICT),
    ({GEN: "1"}, frozenset(), GEN),
    ({ACCR: "1"}, frozenset(), ACCR),
    ({HOF: "1"}, frozenset(), HOF),
    ({TRUTH: "0", ACCR: "1"}, frozenset({TRUTH, ACCR}), ACCR),          # «ВЫКЛ (задан; только поверх CLOSE_TRUTH)»
    ({TRUTH: "0"}, frozenset(), TRUTH),
)
UNKNOWN_CASES = (({STRICT: "maybe"}, STRICT), ({GEN: "да"}, GEN), ({TRUTH: "maybe"}, TRUTH), ({ACCR: "maybe"}, ACCR),
                 ({HOF: "enabled"}, HOF))


def test_b6_each_mismatch_names_only_that_handle():
    for env, unit, key in MISMATCH_CASES:
        state, line = S.release_entry(words_of(**env), unit)
        want = {k: "OK" for k in KEYS}
        want[key] = "MISMATCH"
        assert state is None and verdict(line) == "MISMATCH", (env, line)
        assert per_flag(line) == want, (env, line)


def test_b6b_handover_on_without_rules_is_mismatch():
    """HANDOVER_FACTS=1, а rental_case_rules не грузится: действует ВЫКЛ, но состояние не из перечня — стоп."""
    def _boom():
        raise ImportError("стенд: rental_case_rules не грузится")
    with mock.patch.object(S, "_rc_rules", _boom):
        w = words_of(**{HOF: "1"})
    assert dict(w)[HOF] == "ВЫКЛ (задан; rental_case_rules не загрузился)", w
    state, line = S.release_entry(w, frozenset({HOF}))
    assert state is None and per_flag(line)[HOF] == "MISMATCH" and verdict(line) == "MISMATCH", line


def test_b7_each_unknown_names_only_that_handle():
    for env, key in UNKNOWN_CASES:
        w = words_of(**env)
        assert dict(w)[key].startswith("НЕИЗВЕСТНО"), w
        state, line = S.release_entry(w, frozenset(env))
        want = {k: "OK" for k in KEYS}
        want[key] = "UNKNOWN"
        assert state is None and verdict(line) == "UNKNOWN", (env, line)
        assert per_flag(line) == want, (env, line)


def test_b8_unknown_beats_mismatch():
    state, line = S.release_entry(words_of(**{STRICT: "maybe", ACCR: "1"}), frozenset())
    assert state is None and verdict(line) == "UNKNOWN", line
    assert per_flag(line)[STRICT] == "UNKNOWN" and per_flag(line)[ACCR] == "MISMATCH", line


def test_b9_words_not_read_is_unknown():
    state, line = S.release_entry(None, frozenset(KEYS))
    assert state is None and verdict(line) == "UNKNOWN", line
    assert per_flag(line) == {k: "UNKNOWN" for k in KEYS} and "флаги выпуска не прочитаны" in line, line


def test_b10_wrong_handle_set_is_unknown():
    w = list(words_of())
    for bad in (w[::-1], w[:4], w + [("EXTRA_FLAG", "ВКЛ (задан)")], w[:4] + [w[3]], [(k.lower(), v) for k, v in w]):
        state, line = S.release_entry(tuple(bad), frozenset())
        assert state is None and verdict(line) == "UNKNOWN" and "набор ручек не тот" in line, (bad, line)


class _BadIter:
    def __iter__(self):
        raise RuntimeError("стенд")


def test_b11_garbage_never_raises_and_is_unknown():
    for bad in (42, "строка", [("a",)], [(1, 2, 3)], _BadIter(), [(STRICT, None)] * 5):
        state, line = S.release_entry(bad, None)
        assert state is None and verdict(line) == "UNKNOWN", (bad, line)
    state, line = S.release_entry(words_of(), None)            # нет имён юнита — release не требует их
    assert state == "release", line


def test_b12_finite_list_of_states():
    names = tuple(n for n, _a, _u in S.RELEASE_ENTRY_STATES)
    assert names == ("release", "truth_off"), names
    closed = {"ВКЛ (задан)", "ВКЛ (не задан)", "ВЫКЛ (задан)", "ВЫКЛ (не задан)"}
    for name, allowed, unit_bound in S.RELEASE_ENTRY_STATES:
        assert len(allowed) == len(KEYS) and all(set(a) <= closed and a for a in allowed), name
        assert set(unit_bound) <= {TRUTH}, (name, unit_bound)
    admits = lambda i, w: any(w in a[i] for _n, a, _u in S.RELEASE_ENTRY_STATES)  # noqa: E731
    assert admits(2, "ВЫКЛ (задан)"), "CLOSE_TRUTH=0 (R0) не допускается — это был бы безусловный CLOSE_TRUTH=1"
    assert not admits(2, "ВЫКЛ (не задан)"), "CLOSE_TRUTH ВЫКЛ без ключа невозможен"
    assert not any(admits(i, "ВКЛ (задан)") or admits(i, "ВКЛ (не задан)") for i in (1, 3, 4)), \
        "вкл-слово CONTRACT_REF_GEN / CLOSE_ACCRUAL / HANDOVER_FACTS в перечне"
    assert not admits(0, "ВЫКЛ (задан)") and not admits(0, "ВЫКЛ (не задан)"), "STRICT ВЫКЛ в перечне"
    assert S.RELEASE_FLAG_KEYS == KEYS == (STRICT, S.F_CONTRACT_REF_GEN, TRUTH, ACCR, S.F_HANDOVER_FACTS)
    assert tuple(k for k, _ in S.release_flags_words()) == S.RELEASE_FLAG_KEYS


def test_b13_all_ok_iff_admitted_on_grid():
    for env, w, _line in grid_cases():
        for unit in (frozenset(k for k, v in env.items() if v is not None), frozenset()):
            state, line = S.release_entry(w, unit)
            assert (state is not None) == all(v == "OK" for v in per_flag(line).values()), (env, line)
            assert len(per_flag(line)) == len(KEYS), line


# ======================================================================================================================
# C. Чистота строки статуса и строки флагов.
# ======================================================================================================================

def _all_status_lines():
    out = []
    for env, w, _line in grid_cases()[::7]:
        for unit in (frozenset(k for k, v in env.items() if v is not None), frozenset()):
            out.append(S.release_entry(w, unit)[1])
    for bad in (None, 42, _BadIter(), list(words_of())[::-1]):
        out.append(S.release_entry(bad, frozenset())[1])
    return out


def test_c1_status_line_closed_grammar():
    lines = _all_status_lines()
    for line in lines:
        assert LINE_GRAMMAR.fullmatch(line), line
        assert "=" not in line and "\n" not in line, line
    print("    · строк статуса разобрано полностью: %d" % len(lines))


def test_c2_bait_value_never_printed():
    """Приманка стоит в окружении и ВО ВРЕМЯ проверки (как в процессе: окружение не меняется) — в строке её нет."""
    for key in KEYS:
        env = {k: None for k in KEYS}
        env[key] = BAIT
        with _Env(env):
            w = S.release_flags_words()
            for unit in (frozenset({key}), frozenset()):
                state, line = S.release_entry(w, unit)
                assert state is None, line
                assert BAIT.lower() not in line.lower() and "7731" not in line, line
    environ = {k: BAIT for k in KEYS}
    environ["OTHER"] = BAIT
    names = S.release_unit_keys(environ)
    assert names == frozenset(KEYS) and all(BAIT not in n for n in names), names


def test_c3_no_reader_literals():
    for line in _all_status_lines():
        for lit in READER_LITERALS:
            assert lit not in line, (lit, line)


def test_c4_flags_line_byte_for_byte():
    """Строка «🧩 флаги выпуска» — байт-в-байт прежняя (формула @4b12f1d) на сетке раздела K test_release_flags_line."""
    n = 0
    vals = ("1", "0", "maybe", "да", None, "")
    for sv in vals:
        for tv in vals:
            for av in vals:
                for hv in ("1", "0", "да", None):
                    with _Env({STRICT: sv, GEN: sv, TRUTH: tv, ACCR: av, HOF: hv}):
                        old = _old_line()
                        assert S.release_flags_line() == old, old
                        assert S.release_flags_line(S.release_flags_words()) == old, old
                        n += 1
    assert n == 864, n


def _func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("нет функции %s" % name)


def _names_in(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _env_stores(node):
    """Записи в окружение: os.environ[...] = …, environ.setdefault/update/pop/clear, putenv, unsetenv."""
    bad = []
    for n in ast.walk(node):
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.Delete)):
            tg = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            for t in tg:
                if isinstance(t, ast.Subscript) and "environ" in _names_in(t.value):
                    bad.append(ast.dump(t))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in ("putenv", "unsetenv") or (n.func.attr in ("setdefault", "update", "pop", "clear")
                                                          and "environ" in _names_in(n.func.value)):
                bad.append(ast.dump(n.func))
    return bad


def test_c5_check_only_reads():
    """Вход выпуска окружения не читает (кроме имён в release_unit_keys) и не пишет; подстановки значений нет."""
    tree = ast.parse(open(_src("splinter.py"), encoding="utf-8").read())
    for name in ("release_entry", "_entry_flag_status"):
        used = _names_in(_func(tree, name))
        assert not used & {"os", "environ", "getenv", "_os_env", "putenv", "release_flags_words"}, (name, used)
    ruk = _func(tree, "release_unit_keys")
    assert not _names_in(ruk) & {"getenv", "_os_env", "get", "items", "values"}, _names_in(ruk)
    assert not [n for n in ast.walk(ruk) if isinstance(n, ast.Subscript)], "release_unit_keys читает значения"
    for name in ("release_entry", "_entry_flag_status", "release_unit_keys", "release_flags_words", "release_flags_line"):
        assert not _env_stores(_func(tree, name)), name
    btree = ast.parse(open(_src("bot.py"), encoding="utf-8").read())
    main = _func(btree, "main")
    head = ast.Module(body=main.body[:3], type_ignores=[])
    assert not _names_in(head) & {"getenv", "environ", "_os_env"}, _names_in(head)
    assert not _env_stores(main) and not _env_stores(_func(btree, "_park_until_stop"))
    before = dict(os.environ)
    S.release_unit_keys()
    S.release_entry(words_of(**{TRUTH: "0"}), frozenset({TRUTH}))
    assert dict(os.environ) == before


def test_c6_no_bypass_in_main():
    """Вход в main() — ровно release_entry(_RELEASE_WORDS, _UNIT_FLAG_KEYS) и «entry_state is None»: ни ручки обхода, ни
    второго условия."""
    main = _func(ast.parse(open(_src("bot.py"), encoding="utf-8").read()), "main")
    call = main.body[0].value
    assert isinstance(call, ast.Call) and [a.id for a in call.args if isinstance(a, ast.Name)] == \
        ["_RELEASE_WORDS", "_UNIT_FLAG_KEYS"] and len(call.args) == 2 and not call.keywords, ast.dump(call)
    t = main.body[1].test
    assert (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "entry_state"
            and len(t.ops) == 1 and isinstance(t.ops[0], ast.Is) and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value is None), ast.dump(t)


# ======================================================================================================================
# D. Порядок по исходнику bot.py.
# ======================================================================================================================

def _bot_tree():
    return ast.parse(open(_src("bot.py"), encoding="utf-8").read())


def test_d1_unit_names_before_load_dotenv():
    body = _bot_tree().body
    imp = next(i for i, n in enumerate(body) if isinstance(n, ast.Import) and any(a.name == "splinter" for a in n.names))
    dot = next(i for i, n in enumerate(body) if isinstance(n, ast.Expr) and "load_dotenv" in ast.dump(n))
    uk = [i for i, n in enumerate(body) if isinstance(n, ast.Assign)
          and any(isinstance(t, ast.Name) and t.id == "_UNIT_FLAG_KEYS" for t in n.targets)]
    assert len(uk) == 1, uk
    v = body[uk[0]].value
    assert isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr == "release_unit_keys" \
        and not v.args, ast.dump(v)
    assert imp < uk[0] < dot, (imp, uk, dot)


def test_d2_one_snapshot_for_line_and_entry():
    body = _bot_tree().body
    tr = [n for n in body if isinstance(n, ast.Try) and "release_flags_line" in ast.dump(n)]
    assert len(tr) == 1
    tr = tr[0]
    a0 = tr.body[0]
    assert isinstance(a0, ast.Assign) and a0.targets[0].id == "_RELEASE_WORDS" and \
        a0.value.func.attr == "release_flags_words", ast.dump(a0)
    calls = [n for n in ast.walk(tr.body[1]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "release_flags_line"]
    assert len(calls) == 1 and [a.id for a in calls[0].args] == ["_RELEASE_WORDS"], ast.dump(tr.body[1])
    hb = tr.handlers[0].body
    assert any(isinstance(n, ast.Assign) and n.targets[0].id == "_RELEASE_WORDS" and isinstance(n.value, ast.Constant)
               and n.value.value is None for n in hb), [ast.dump(n) for n in hb]
    assert "НЕ ПРОЧИТАНЫ" in ast.dump(tr.handlers[0])
    assert sum(1 for n in ast.walk(_bot_tree()) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "release_flags_words") == 1, "слова ручек снимаются в bot.py не один раз"


def test_d3_main_entry_first_stop_second():
    main = _func(_bot_tree(), "main")
    a0 = main.body[0]
    assert isinstance(a0, ast.Assign) and isinstance(a0.targets[0], ast.Tuple) and \
        [e.id for e in a0.targets[0].elts] == ["entry_state", "entry_line"], ast.dump(a0)
    assert isinstance(a0.value.func, ast.Attribute) and a0.value.func.attr == "release_entry" and \
        a0.value.func.value.id == "splinter", ast.dump(a0.value)
    stop = main.body[1]
    assert isinstance(stop, ast.If) and not stop.orelse, ast.dump(stop)
    kinds = [type(n).__name__ for n in stop.body]
    assert kinds == ["Expr", "Expr", "Return"], kinds
    assert stop.body[0].value.func.attr == "error" and stop.body[1].value.func.id == "_park_until_stop", \
        [ast.dump(n) for n in stop.body]
    assert stop.body[2].value is None


def test_d4_registration_and_polling_below_stop():
    main = _func(_bot_tree(), "main")
    stop = main.body[1]
    inside = {id(n) for n in ast.walk(stop)}
    want = {"builder", "token", "post_init", "post_stop", "build", "add_handler", "run_daily", "run_repeating",
            "run_polling"}
    seen = set()
    for n in ast.walk(main):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in want:
            assert n.lineno > stop.end_lineno and id(n) not in inside, (n.func.attr, n.lineno)
            seen.add(n.func.attr)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "Bot polling started" in n.value:
            assert n.lineno > stop.end_lineno, n.lineno
            seen.add("polling_line")
        if isinstance(n, ast.Name) and n.id in ("on_startup", "on_stop"):
            assert n.lineno > stop.end_lineno, (n.id, n.lineno)
            seen.add(n.id)
    assert seen == want | {"polling_line", "on_startup", "on_stop"}, seen


def test_d5_park_never_exits():
    park = _func(_bot_tree(), "_park_until_stop")
    names = _names_in(park)
    assert not names & {"exit", "_exit", "quit", "abort", "Application", "send_message", "add_handler", "run_polling",
                        "handoff_restore", "on_startup", "post_init", "kill"}, names
    assert not [n for n in ast.walk(park) if isinstance(n, ast.Raise)], "в простое есть raise"
    assert {"Event", "wait"} <= names, names


# ======================================================================================================================
# E. Инструментированный main().
# ======================================================================================================================
EXPECTED_CALLS = (
    [("builder",), ("token",), ("post_init", "on_startup"), ("post_stop", "on_stop"), ("build",)]
    + [("add_handler", "cmd", c) for c in ("start", "pulse", "audit", "ping", "rules", "chatid", "bike", "board", "o3board",
                                           "pin_info_all", "inbox")]
    + [("add_handler", "cbq", p, f) for p, f in (("^aud:", "on_audit_button"), ("^svc:", "on_service_button"),
                                                 ("^dlv:", "on_decider_button"),
                                                 ("^(approve|reject|check|next):", "on_devbot_button"),
                                                 ("^delivery:", "on_delivery_button"), ("^o3:", "on_o3_button"),
                                                 ("^info:", "on_info_button"))]
    + [("add_handler", "msg", f) for f in ("on_forum_topic", "capture_service_edit", "handle_voice", "handle_photo", "handle_text")]
    + [("run_daily", n, f) for n, f in (("daily_pulse", "scheduled_daily_pulse"),
                                        ("important_reminders", "scheduled_important_reminders"),
                                        ("audit_report", "scheduled_audit_report"),
                                        ("contract_km_daily", "scheduled_contract_km"),
                                        ("devbot_morning", "morning_summary"))]
    + [("run_repeating", n, f) for n, f in (("devbot_report", "report_results"),
                                            ("service_pending_reminder", "scheduled_service_pending_reminder"),
                                            ("staff_ask_tick", "staff_ask_job"), ("rules_snap", "rules_snap_job"))]
    + [("run_polling", "ALL_TYPES")])
_KEEP = object()


def _cb_name(cb):
    return getattr(getattr(cb, "func", cb), "__name__", repr(cb))


def _rec_application(ev):
    def hdesc(h):
        if hasattr(h, "commands"):
            return ("add_handler", "cmd") + tuple(sorted(h.commands))
        if hasattr(h, "pattern"):
            p = getattr(h, "pattern")
            return ("add_handler", "cbq", getattr(p, "pattern", p), _cb_name(h.callback))
        return ("add_handler", "msg", _cb_name(h.callback))

    class JQ:
        def run_daily(self, cb, *a, **k):
            ev.append(("call", "run_daily", k.get("name"), _cb_name(cb)))

        def run_repeating(self, cb, *a, **k):
            ev.append(("call", "run_repeating", k.get("name"), _cb_name(cb)))

    class App:
        job_queue = JQ()

        def add_handler(self, h, *a, **k):
            if _cb_name(h.callback) == "capture_service_edit":
                assert not a and k == {"group": -1}, (a, k)
            ev.append(("call",) + hdesc(h))

        def run_polling(self, *a, **k):
            ev.append(("call", "run_polling", "ALL_TYPES" if k.get("allowed_updates") == bot.Update.ALL_TYPES else
                       repr(k.get("allowed_updates"))))

    class Builder:
        def token(self, t):
            ev.append(("call", "token"))
            return self

        def post_init(self, f):
            ev.append(("call", "post_init", f.__name__))
            return self

        def post_stop(self, f):
            ev.append(("call", "post_stop", f.__name__))
            return self

        def build(self):
            ev.append(("call", "build"))
            return App()

    class Application:
        @staticmethod
        def builder():
            ev.append(("call", "builder"))
            return Builder()
    return Application


def run_main_recorded(words=_KEEP, unit=_KEEP):
    """bot.main() с регистратором вместо Application, записью простоя и часовым поясом без tzdata → (события, вызовов
    handoff_restore). words/unit — подмена снимка bot.py; _KEEP — тот, что bot.py снял на импорте."""
    ev, restore = [], []
    names = ("Application", "_park_until_stop", "ZoneInfo", "GROUP_CHAT_ID", "BOT_TOKEN", "_RELEASE_WORDS",
             "_UNIT_FLAG_KEYS")
    saved = {n: getattr(bot, n) for n in names}
    saved_hr = S.handoff_restore
    try:
        bot.Application = _rec_application(ev)
        bot._park_until_stop = lambda: ev.append(("call", "park"))
        bot.ZoneInfo = lambda name: _dt.timezone(_dt.timedelta(hours=7))
        bot.GROUP_CHAT_ID = -1001
        bot.BOT_TOKEN = "x"
        if words is not _KEEP:
            bot._RELEASE_WORDS = words
        if unit is not _KEEP:
            bot._UNIT_FLAG_KEYS = unit
        S.handoff_restore = lambda *a, **k: (restore.append(1), "передачи нет")[1]
        CAP.sink = ev
        bot.main()
    finally:
        CAP.sink = None
        for n, v in saved.items():
            setattr(bot, n, v)
        S.handoff_restore = saved_hr
    return ev, len(restore)


def _calls(ev):
    return [tuple(e[1:]) for e in ev if e[0] == "call"]


def assert_started_as_before(ev, restore, state):
    assert _calls(ev) == EXPECTED_CALLS, _calls(ev)
    first = ev[0]
    assert first[0] == "log" and first[1] == "INFO" and first[2].startswith("  " + HEAD + "OK — состояние %s · " % state), first
    assert ev[1] == ("call", "builder"), ev[:3]
    i = ev.index(("call", "run_polling", "ALL_TYPES"))
    assert ev[i - 1] == ("log", "INFO", "Bot polling started. Press Ctrl+C to stop."), ev[i - 2:i + 1]
    assert ("call", "park") not in ev and not [e for e in ev if e[0] == "log" and e[1] == "ERROR"], ev
    assert restore == 0                      # post_init регистрируется, но до опроса регистратор его не зовёт


def assert_parked(ev, restore, key=None, word=None):
    assert len(ev) == 2 and ev[1] == ("call", "park"), ev
    lvl, line = ev[0][1], ev[0][2]
    assert ev[0][0] == "log" and lvl == "ERROR" and line.startswith("  " + HEAD), ev[0]
    assert LINE_GRAMMAR.fullmatch(line[2:]), line
    if key:
        assert per_flag(line)[key] == word, (key, word, line)
    assert restore == 0


def test_e1_release_starts_as_before():
    ev, restore = run_main_recorded(words_of(), frozenset())
    assert_started_as_before(ev, restore, "release")
    assert len([c for c in _calls(ev) if c[0] == "add_handler"]) == 23


def test_e2_r0_modes_start_as_before():
    for env, unit, state in (({TRUTH: R0_APPLY}, frozenset({TRUTH}), "truth_off"),
                             ({TRUTH: R0_UNDO}, frozenset({TRUTH}), "release"),
                             ({STRICT: "1", GEN: "0", TRUTH: "1", ACCR: "0", HOF: "0"}, frozenset(KEYS), "release")):
        ev, restore = run_main_recorded(words_of(**env), unit)
        assert_started_as_before(ev, restore, state)


def test_e3_every_mismatch_or_unknown_parks_without_handlers():
    n = 0
    for env, unit, key in MISMATCH_CASES:
        ev, restore = run_main_recorded(words_of(**env), unit)
        assert_parked(ev, restore, key, "MISMATCH")
        n += 1
    for env, key in UNKNOWN_CASES:
        ev, restore = run_main_recorded(words_of(**env), frozenset(env))
        assert_parked(ev, restore, key, "UNKNOWN")
        n += 1
    ev, restore = run_main_recorded(None, frozenset())
    assert_parked(ev, restore, TRUTH, "UNKNOWN")
    ev, restore = run_main_recorded(_BadIter(), frozenset())        # сбой самой проверки — тоже стоп
    assert_parked(ev, restore)
    assert "сбой проверки" in ev[0][2], ev[0]
    assert n == len(MISMATCH_CASES) + len(UNKNOWN_CASES)
    for env, unit in (({}, frozenset()), ({TRUTH: "0"}, frozenset({TRUTH})), ({TRUTH: "0"}, frozenset()),
                      ({HOF: "1"}, frozenset({HOF})), ({ACCR: "maybe"}, frozenset({ACCR}))):
        print("    · образец %s: [%s] %s" % (env or "умолчания", "ERROR" if S.release_entry(words_of(**env), unit)[0] is None
                                         else "INFO", S.release_entry(words_of(**env), unit)[1]))


# ======================================================================================================================
# F. Дети: настоящий импорт bot.py с окружением «юнита» и строкой «.env».
# ======================================================================================================================
CHILD_SCENARIOS = {
    "default_release": ({}, ""),
    "unit_truth_off": ({TRUTH: "0"}, ""),
    "dotenv_truth_off": ({}, "CLOSE_TRUTH=0"),
    "unit_beats_dotenv": ({TRUTH: "0"}, "CLOSE_TRUTH=1"),
    "unit_undo": ({TRUTH: "1"}, ""),
    "unit_hofacts_on": ({HOF: "1"}, ""),
    "dotenv_accrual_on": ({}, "CLOSE_ACCRUAL=1"),
    "words_raise": ({}, ""),
}
CHILD_MARK = "RCFIX_TUPLE_CHILD_RESULT "


def _child_main():
    ev, restore = run_main_recorded()
    out = {"unit": sorted(bot._UNIT_FLAG_KEYS), "words_none": bot._RELEASE_WORDS is None, "restore": restore,
           "flags_lines": [m for _l, m in CAP.lines if "🧩 флаги выпуска" in m], "events": ev}
    sys.stdout.write(CHILD_MARK + json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


def run_children(names):
    procs = {}
    for name in names:
        env = {k: v for k, v in os.environ.items()
               if k not in _SCRUB and k not in ("RCFIX_TUPLE_DOTENV", "RCFIX_TUPLE_CHILD", "RCFIX_TUPLE_ONLY")}
        unit_env, dotenv = CHILD_SCENARIOS[name]
        env.update(unit_env)
        env["RCFIX_TUPLE_CHILD"] = name
        if dotenv:
            env["RCFIX_TUPLE_DOTENV"] = dotenv
        env["PYTHONIOENCODING"] = "utf-8"
        procs[name] = subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    res = {}
    for name, p in procs.items():
        out = p.communicate(timeout=600)[0].decode("utf-8", "replace")
        line = [ln for ln in out.splitlines() if ln.startswith(CHILD_MARK)]
        assert p.returncode == 0 and len(line) == 1, (name, p.returncode, out[-1500:])
        r = json.loads(line[0][len(CHILD_MARK):])
        r["events"] = [tuple(e) for e in r["events"]]
        res[name] = r
    return res


def test_f_real_import_unit_vs_dotenv():
    r = run_children(list(CHILD_SCENARIOS))
    # умолчания — release, как прежде
    d = r["default_release"]
    assert d["unit"] == [] and not d["words_none"] and len(d["flags_lines"]) == 1, d
    assert RX_REL.search(d["flags_lines"][0]), d["flags_lines"]
    assert_started_as_before(d["events"], d["restore"], "release")
    # R0: CLOSE_TRUTH=0 из юнита — truth_off, как прежде
    u = r["unit_truth_off"]
    assert u["unit"] == [TRUTH] and RX_TOFF.search(u["flags_lines"][0]), u
    assert_started_as_before(u["events"], u["restore"], "truth_off")
    # тот же CLOSE_TRUTH=0 строкой .env: шаблон r7 truth_off строку флагов принял бы, вход — стоп
    e = r["dotenv_truth_off"]
    assert e["unit"] == [] and RX_TOFF.search(e["flags_lines"][0]), e
    assert_parked(e["events"], e["restore"], TRUTH, "MISMATCH")
    assert WHY_SRC in e["events"][0][2], e["events"][0]
    # override=False: ключ юнита сильнее строки .env
    b = r["unit_beats_dotenv"]
    assert b["unit"] == [TRUTH] and RX_TOFF.search(b["flags_lines"][0]), b
    assert_started_as_before(b["events"], b["restore"], "truth_off")
    # снятие R0 — release
    n = r["unit_undo"]
    assert n["unit"] == [TRUTH] and RX_REL.search(n["flags_lines"][0]), n
    assert_started_as_before(n["events"], n["restore"], "release")
    # HANDOVER_FACTS=1: шаблон hofacts_on строку принял бы, вход — стоп
    h = r["unit_hofacts_on"]
    assert h["unit"] == [HOF] and RX_HOF.search(h["flags_lines"][0]), h
    assert_parked(h["events"], h["restore"], HOF, "MISMATCH")
    a = r["dotenv_accrual_on"]
    assert a["unit"] == [], a
    assert_parked(a["events"], a["restore"], ACCR, "MISMATCH")
    # строка флагов не прочитана — «НЕ ПРОЧИТАНЫ» и стоп UNKNOWN
    w = r["words_raise"]
    assert w["words_none"] and w["flags_lines"] == ["  🧩 флаги выпуска: НЕ ПРОЧИТАНЫ (RuntimeError)"], w
    assert_parked(w["events"], w["restore"], TRUTH, "UNKNOWN")
    assert "флаги выпуска не прочитаны" in w["events"][0][2]
    print("    · детей %d: настоящий импорт bot.py, имена юнита до load_dotenv" % len(r))


# ======================================================================================================================
# G. Простой.
# ======================================================================================================================

def test_g1_park_blocks_and_does_not_exit():
    t = threading.Thread(target=bot._park_until_stop, daemon=True, name="rcfix_tuple_park")
    t.start()
    t.join(2.0)
    assert t.is_alive(), "простой вернулся или вышел"


def test_g2_sigterm_not_intercepted_before_main():
    """До main() (импорт bot.py со всеми модулями) обработчика SIGTERM нет: в простое systemctl stop / restart действуют
    по умолчанию. Обработчики сигналов ставит только on_startup, до которого простой не доходит."""
    assert SIGTERM_AFTER_IMPORT == signal.SIG_DFL, SIGTERM_AFTER_IMPORT


# ======================================================================================================================
# Z. Мутанты: (файл, было, стало, слова, проверки, которые обязаны упасть).
# ======================================================================================================================
MUTANTS = (
    ("bot.py", '        _park_until_stop()\n        return\n    log.info("  " + entry_line)',
     '        _park_until_stop()\n    log.info("  " + entry_line)', "стоп без return — регистрация после простоя",
     ("test_d3_main_entry_first_stop_second", "test_e3_every_mismatch_or_unknown_parks_without_handlers")),
    ("bot.py", "    if entry_state is None:\n", "    if entry_state is None and False:\n", "вход выключен",
     ("test_c6_no_bypass_in_main", "test_e3_every_mismatch_or_unknown_parks_without_handlers")),
    ("bot.py", "splinter.release_entry(_RELEASE_WORDS, _UNIT_FLAG_KEYS)",
     "splinter.release_entry(splinter.release_flags_words(), _UNIT_FLAG_KEYS)", "main перечитывает ручки",
     ("test_c6_no_bypass_in_main", "test_d2_one_snapshot_for_line_and_entry", "test_f_real_import_unit_vs_dotenv")),
    ("bot.py", "_UNIT_FLAG_KEYS = splinter.release_unit_keys()\n\n# === Загружаем конфиг ===\nload_dotenv()\n",
     "# === Загружаем конфиг ===\nload_dotenv()\n_UNIT_FLAG_KEYS = splinter.release_unit_keys()\n",
     "имена юнита после load_dotenv", ("test_d1_unit_names_before_load_dotenv", "test_f_real_import_unit_vs_dotenv")),
    ("bot.py", 'log.info("  " + splinter.release_flags_line(_RELEASE_WORDS))',
     'log.info("  " + splinter.release_flags_line())', "строка флагов из другого снимка",
     ("test_d2_one_snapshot_for_line_and_entry",)),
    ("bot.py", "    import threading\n    _ev = threading.Event()\n",
     "    import sys as _sys\n    _sys.exit(3)\n    import threading\n    _ev = threading.Event()\n", "выход вместо простоя",
     ("test_d5_park_never_exits", "test_g1_park_blocks_and_does_not_exit")),
    ("splinter.py", '("truth_off", (_RE_ON, _RE_OFF, ("ВЫКЛ (задан)",), _RE_OFF, _RE_OFF), ("CLOSE_TRUTH",)),',
     '("truth_off", (_RE_ON, _RE_OFF, ("ВЫКЛ (задан)",), _RE_OFF, _RE_OFF), ()),', "truth_off без юнита",
     ("test_a1_grid_equivalence_with_library", "test_b5_truth_off_not_from_unit_stops", "test_f_real_import_unit_vs_dotenv")),
    ("splinter.py", '    ("truth_off", (_RE_ON, _RE_OFF, ("ВЫКЛ (задан)",), _RE_OFF, _RE_OFF), ("CLOSE_TRUTH",)),\n', "",
     "truth_off выкинут (безусловный CLOSE_TRUTH=1)",
     ("test_b2_r0_truth_off_and_restart", "test_b12_finite_list_of_states", "test_e2_r0_modes_start_as_before")),
    ("splinter.py", '("release", (_RE_ON, _RE_OFF, _RE_ON, _RE_OFF, _RE_OFF), ()),',
     '("release", (_RE_ON, _RE_OFF, _RE_ON, _RE_OFF, _RE_OFF + ("ВКЛ (задан)",)), ()),', "hofacts_on принят",
     ("test_a1_grid_equivalence_with_library", "test_b6_each_mismatch_names_only_that_handle",
      "test_b12_finite_list_of_states")),
    ("splinter.py", 'body = " · ".join("%s %s" % (k, s) for k, s in zip(RELEASE_FLAG_KEYS, per))',
     'body = " · ".join("%s %s %s" % (k, s, os.getenv(k)) for k, s in zip(RELEASE_FLAG_KEYS, per))', "значение в строке",
     ("test_c2_bait_value_never_printed",)),
    ("splinter.py", 'body = " · ".join("%s %s" % (k, s) for k, s in zip(RELEASE_FLAG_KEYS, per))',
     'body = " · ".join("%s %s" % (k, s) for k, s in zip(RELEASE_FLAG_KEYS, per)) + "".join(" %s" % w for _k, w in words)',
     "слова ручек в строке", ("test_c1_status_line_closed_grammar",)),
    ("splinter.py", 'or word.startswith("НЕИЗВЕСТНО"):', 'or word.startswith("~~"):', "НЕИЗВЕСТНО как решённое",
     ("test_b7_each_unknown_names_only_that_handle", "test_b8_unknown_beats_mismatch")),
    ("splinter.py", 'return "🧩 флаги выпуска: " + " · ".join("%s=%s" % (k, w) for k, w in words)',
     'return "🧩 флаги выпуска: " + " · ".join("%s=%s" % (k, w) for k, w in words) + " "', "строка флагов не байт-в-байт",
     ("test_c4_flags_line_byte_for_byte",)),
)


def _spawn(mut_dir, tests):
    env = {k: v for k, v in os.environ.items() if k not in ("RCFIX_TUPLE_CHILD", "RCFIX_TUPLE_DOTENV")}
    env.update(RCFIX_TUPLE_SRC=mut_dir, RCFIX_TUPLE_ONLY=",".join(tests), PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1")
    return subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def test_zz_mutants():
    if SRC or ONLY:
        return
    if os.environ.get("RCFIX2010_MUTANTS") != "1":
        # Мутации — проверка силы самих голденов, а не продукта; дети идут дольше лимита gate.py (90 с на набор).
        # В обычном прогоне/гейте — явный пропуск; квитанция мутантов снимается отдельным запуском с RCFIX2010_MUTANTS=1.
        print("  SKIP мутанты: RCFIX2010_MUTANTS не 1 (квитанция мутантов — отдельным запуском)")
        return
    union = sorted({t for m in MUTANTS for t in m[4]})
    null_dir = tempfile.mkdtemp(prefix="rcfix_tuple_null_")
    for name in ("bot.py", "splinter.py"):
        with open(os.path.join(null_dir, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(open(os.path.join(ROOT, name), encoding="utf-8").read())
    jobs = [("нулевой мутант (копия без правки)", _spawn(null_dir, union), True)]
    for name, old, new, words, tests in MUTANTS:
        src = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert src.count(old) == 1, (words, src.count(old))
        d = tempfile.mkdtemp(prefix="rcfix_tuple_mut_")
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(src.replace(old, new))
        jobs.append((words, _spawn(d, tests), False))
    missed = []
    for words, p, null in jobs:
        out = p.communicate(timeout=1200)[0].decode("utf-8", "replace")
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
    print("временный каталог: %s%s" % (TMP, (" · мутант: " + SRC) if SRC else ""))
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
    sys.exit(_child_main() if CHILD else main())
