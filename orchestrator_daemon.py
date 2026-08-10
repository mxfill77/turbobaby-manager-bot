#!/usr/bin/env python3
"""
ОРКЕСТРАТОР ступень 1, заход 2а — ДЕМОН исполнения очереди (ИЗОЛИРОВАННО, без дев-бота).

Цикл (каждые POLL_SEC):
  get_pending(new)  — плоский HTTP к Bridge, БЕЗ claude -p (токены LLM на опрос НЕ тратим)
    → есть new → claim_task(id) (атомарно new→in_progress)
      → claim успешен → исполнить через `claude -p "<task_text>"` (headless, cwd=репо, видит CLAUDE.md)
        → complete_task(id, done|failed, <вывод/ошибка/таймаут>)

ЗАЩИТА (доктрина KB_ORCHESTRATOR_SAFETY):
  - НЕ используем --dangerously-skip-permissions. claude -p читает .claude/settings.json:
    green-команды (allow) исполняет, красные (ask: clasp/sqlite3/systemctl stop/git push) в headless
    НЕ может подтвердить → отказ. Демон сам красную зону НЕ проходит.
  - Таймаут задачи (TASK_TIMEOUT) → задача не висит вечно: превышен → complete failed("таймаут").
  - Рубильник: `systemctl stop orchestrator-daemon` — гасит ТОЛЬКО этот демон, splinter живёт.
  - Демон спит между опросами; idle = только HTTP get_pending (бесплатно по токенам).

НЕ интегрирован в дев-бот (это заход 2б). Задачи кладутся в очередь извне (в 2а — вручную).
"""
import os
import re
import sys
import time
import json
import signal
import logging
import datetime
import fcntl
import subprocess
import threading

REPO = "/root/turbobaby-manager-bot"
BRIDGE_GS = "/root/turbobaby-bridge-gs"

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, REPO)
from bridge_client import BridgeClient, FIXTURE_TASK_RE, _fixture_norm
import card_duty          # ДЕЖУРНЫЙ ПО КАРТОЧКАМ: чистое решение без ввода-вывода (см. _maybe_card_duty)
import curator_claim      # ПОЗИЦИЯ ЗАЯВКИ: имя под отрицанием — не просьба (см. _curator_human_place)
import curator_ops        # РАЗБОР ПУНКТА СВОДКИ НА ОПЕРАЦИИ: чистая функция (см. _curator_human_place)
import curator_event      # ТОЖДЕСТВО СОБЫТИЯ МЕЖДУ ЦЕЛЯМИ: чистая функция (см. _curator_event_seen)
import prod_drift         # ДЕТЕКТОР ДРЕЙФА ПРОДА: read-only, только говорит (см. _maybe_prod_drift)
import chain_series       # СЧЁТ СЕРИИ ЦЕПОЧЕК: чистая функция без рук (см. _series_note_terminal)


def _is_fixture(text: str) -> bool:
    """True → текст — каноническая тест-фикстура класса 193.
    Проверяет ОБА: оригинал (чистые кирилл. паттерны «проверь X»/«тест» …) И нормализованный
    (mixed-script: «тask» Кирилл.т+ASCII → «task»). ORCH_TEST_MODE НЕ проверяет — место вызова."""
    s = str(text or "")
    return bool(FIXTURE_TASK_RE.search(s) or FIXTURE_TASK_RE.search(_fixture_norm(s)))


def _env_int(name, default):
    """Целое из .env с дефолтом; мусор/пусто → дефолт (fail-safe: кривой .env не роняет демона)."""
    try:
        v = int(str(os.environ.get(name) or "").strip() or default)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


POLL_SEC = 60            # пауза между опросами очереди
HEARTBEAT_SEC = 45       # как часто фон-поток бьёт updated, пока claude -p исполняется (детект зависания)
# Таймауты claude-подпроцесса задач — из .env (инцидент 07.07 задача 138, по образцу PC_STEP_TIMEOUT);
# по истечении subprocess.run сам убивает claude → честный failed «⏱ таймаут», думатель такое НЕ чинит
# (гейт по ⏱-маркеру в _maybe_selfheal). Heartbeat задачи тикает НЕЗАВИСИМЫМ фон-потоком (_heartbeat_loop)
# и исполнением не блокируется. Дефолты = прежние боевые значения (не ослабляем «задача:» до часа).
TASK_TIMEOUT = _env_int("TASK_TIMEOUT", 600)        # быстрая «задача:» (10 мин)
TASK_TIMEOUT_DEV = _env_int("TASK_TIMEOUT_DEV", 2700)  # дев-ТЗ «тз:» (45 мин) — правка+тесты+гейт+отчёт
TIMEOUT_MARK = "⏱"       # маркер таймаут/сирота-диагнозов: думатель самопочинки их НЕ чинит
# Сирота in_progress (инцидент 07.07, задача 138): claim долетел сервер-сайд при потерянном ответе
# (404/timeout Bridge) → демон задачу «пропустил», а подобрать некому — висела бы вечно. Реапер:
# in_progress полосы vps с updated старше ORPHAN_TTL → честный failed (см. process_orphans).
ORPHAN_TTL = _env_int("ORPHAN_TTL", 600)
# ГЕЙТ ПАМЯТИ (16.07.2026, OOM-инцидент 05:27 UTC): перед стартом claude -p (шаг/одиночка)
# проверяем MemAvailable; дефицит → задача ждёт в new, не started и не failed.
# MEM_MIN_MB=0 → гейт выключен полностью (off в баннере).
# Fail-safe: /proc/meminfo нечитаем → гейт пропускается, прежнее поведение.
try:
    _raw_mem = str(os.environ.get("MEM_MIN_MB") or "").strip()
    MEM_MIN_MB = max(0, int(_raw_mem)) if _raw_mem else 2560
except (ValueError, TypeError):
    MEM_MIN_MB = 2560
MEM_RETRY_SEC = _env_int("MEM_RETRY_SEC", 120)   # cooldown после детекта дефицита, сек
_mem_wait_until = 0.0                              # monotonic: до этого момента не берём задачи
_mem_deny_count = 0        # число последовательных «настоящих» отказов (cooldown-пропуски не в счёт)
MEM_DENY_ALERT = 3         # порог для карточки в 328 (сбрасывается после алерта)
# ГЕЙТ RSS CLAUDE (17.07.2026, OOM №2): суммарный RSS живых claude-процессов в mem-gate.
# Если суммарный RSS >= CLAUDE_RSS_TOTAL_MB → тот же cooldown/карточка, что у MemAvail-гейта.
# CLAUDE_RSS_TOTAL_MB=0 → RSS-гейт выключен. Fail-safe: /proc нечитаем → пропускается.
CLAUDE_RSS_TOTAL_MB = _env_int("CLAUDE_RSS_TOTAL_MB", 4096)
# ГЕЙТ ПАРАЛЛЕЛИЗМА (17.07.2026, OOM №2): считать живые claude-процессы перед spawn.
# Если живых claude >= MAX_CLAUDE_PROCS → задача ждёт в new (не failed, не потеряна).
# MAX_CLAUDE_PROCS=0 → гейт выключен. Fail-safe: /proc нечитаем → гейт пропускается.
MAX_CLAUDE_PROCS = _env_int("MAX_CLAUDE_PROCS", 4)
PROC_RETRY_SEC = _env_int("PROC_RETRY_SEC", 120)   # cooldown после детекта превышения
_proc_wait_until = 0.0
_proc_deny_count = 0
PROC_DENY_ALERT = 3       # порог алерта в 328 (механика идентична MEM_DENY_ALERT)
# ВЫГРУЗКА ЗАВЕРШЁННЫХ ЦЕПЕЙ (17.07.2026): _summarized/_adapt_finish растут без очистки.
# MAX_CHAIN_CACHE — потолок: старые (наименьшие pid) вытесняются при превышении.
MAX_CHAIN_CACHE = _env_int("MAX_CHAIN_CACHE", 200)
DEV_FROM_SUFFIX = "-dev" # метка dev-режима в поле from очереди (devbot кладёт Filipp-328-dev)
DEC_FROM_SUFFIX = "-dec" # метка декомпозиции (ступень 2 часть C; devbot кладёт Filipp-328-dec):
                         # родитель «декомпозируй:» + его шаги + synthetic-сводка — всё под этой меткой
MAX_STEPS = 8            # потолок шагов декомпозиции (планировщику велено 2–7; больше → failed родителя)
# === ПК-ТЕАТР (кусок 2 «один дирижёр, два театра», 07.07.2026) ===
# «декомпозируй:» из темы PC-дев (829): родитель кладётся devbot'ом с меткой PC_DEC_FROM на полосе
# vps (планировщик/думатели ТОЛЬКО здесь, на ПК мозг не дублируется), а ШАГИ демон выдаёт на полосу
# lane=pc — их claim'ит и исполняет pc_orchestrator. Детали — секция «ПК-ТЕАТР: функции» ниже.
PC_LANE = "pc"
PC_DEC_FROM = "Filipp-pc-dec"   # метка семейства pc-декомпозиции (родитель vps + шаги lane=pc + карточки/сводка)
PC_STEP_TIMEOUT = int(os.environ.get("PC_STEP_TIMEOUT") or 3600)  # сек: ПК молчит (шаг не взят /
                         # heartbeat умер / approved завис) → честный failed цепи, думатель НЕ зовётся
PC_SILENT_MARK = "⏱ ПК-театр не отвечает"   # маркер таймаут-диагноза (по нему же гасится самопочинка)
_REJECT_PREFIX = "отклонено Филиппом"        # результат devbot-отказа («нет N»/кнопка ❌) — halt без думателя
OP_TIMEOUT = 180         # таймаут хардкод-операции красной зоны (git push / restart)
APPROVED_TTL = 1800      # approved-задача живёт 30 мин; не довёл → авто-failed «approve истёк»

# УЧЁТ ОПРОСОВ ОЧЕРЕДИ (класс 25.07.2026). Подтверждение НЕЛЬЗЯ гасить по APPROVED_TTL, если
# демон в это окно мост не опрашивал: иначе «да» владельца сгорает из-за НАШЕЙ слепоты, а он
# видит failed после нажатия. Отметки живут только в памяти — после рестарта окно считается
# НЕпокрытым, то есть ошибка идёт в сторону сохранения задачи.
_POLL_OK_TS: list = []      # отметки успешных get_pending
_POLL_FAIL_N: dict = {}     # подряд-неудачи по виду опроса


def _poll_ok(kind: str = "") -> None:
    """Отметить УСПЕШНЫЙ опрос очереди."""
    _POLL_OK_TS.append(time.time())
    del _POLL_OK_TS[:-500]
    if kind:
        _POLL_FAIL_N[kind] = 0


def _poll_fail(kind: str) -> int:
    """Отметить НЕУДАЧНЫЙ опрос. -> сколько подряд."""
    _POLL_FAIL_N[kind] = _POLL_FAIL_N.get(kind, 0) + 1
    return _POLL_FAIL_N[kind]


def _poll_covered(window: int) -> bool:
    """True <=> последние `window` секунд мост опрашивался РЕГУЛЯРНО и УСПЕШНО: отметки есть,
    самая старая покрывает начало окна, дыр больше 3*POLL_SEC нет, последняя свежая.
    Истории нет (только стартовали) -> False: жечь чужое «да» по своим часам нельзя."""
    now = time.time()
    ts = [t for t in _POLL_OK_TS if t >= now - window]
    if not ts or ts[0] > now - window + 3 * POLL_SEC:
        return False
    prev = ts[0]
    for t in ts[1:]:
        if t - prev > 3 * POLL_SEC:
            return False
        prev = t
    return (now - ts[-1]) <= 3 * POLL_SEC
# needs_approval lifetime (класс 23.07.2026): висит до решения владельца (hard-cap 24ч), напоминание 3ч
NA_LIFETIME = int(os.environ.get("NA_LIFETIME", "86400") or "86400")      # 24ч hard-cap needs_approval
NA_REMINDER_SEC = int(os.environ.get("NA_REMINDER_SEC", "10800") or "10800")  # 3ч: напоминание
_na_reminded: set = set()   # id задач, по которым >3ч-напоминание отправлено (in-memory)
CLAUDE_BIN = "/usr/bin/claude"
# РОЛЬ-РАЗВОД PERMISSIONS (08.07.2026): headless-задачи получают СТРОГИЙ доп-слой настроек через
# `--settings` — ask на clasp push/redeploy/deploy/run/version/create-version/deployments.
# Precedence движка deny>ask>allow действует ПОВЕРХ всех источников → этот ask бьёт allow из
# .claude/settings.local.json владельца (интерактивные сессии владельца clasp'ают без промптов,
# headless — нет). В -p режиме ask = авто-отказ → claude выводит NEEDS_APPROVAL, как раньше.
# Файл в корне репо (git-истина): в .claude/ headless писать не может (гейт движка).
# Fail-closed: файла нет → CLI падает с ошибкой → честный failed, а не тихая потеря забора.
HEADLESS_SETTINGS = os.path.join(REPO, "headless_settings.json")
# КОНДУКТОР МОДЕЛИ (06.07.2026; голова сменена 30.07.2026): headless-исполнитель по умолчанию —
# claude-opus-5, фолбэк — claude-opus-4-8. Вынесено в env, НЕ хардкод:
# смена модели в будущем = правка .env (ORCH_MODEL / ORCH_MODEL_FALLBACK), без правки кода.
# Фолбэк исполняет САМ CLI флагом --fallback-model В РАМКАХ ОДНОГО вызова при
# overload/недоступности/лимите/неверном имени primary → задача НЕ исполняется дважды
# (проверено 06.07: невалидная primary + --fallback-model=opus → CLI сам берёт opus, exit 0,
# modelUsage=opus). Хардкода без фолбэка нет: упёршись в лимит основной, автоматика не встаёт.
ORCH_MODEL = (os.environ.get("ORCH_MODEL") or "claude-opus-5").strip() or "claude-opus-5"
ORCH_MODEL_FALLBACK = (os.environ.get("ORCH_MODEL_FALLBACK") or "claude-opus-4-8").strip() or "claude-opus-4-8"
# УСКОРЕНИЕ ЦЕПЕЙ ч.1 (13.07.2026): модель ИСПОЛНИТЕЛЯ headless-задач — отдельный флаг
# EXECUTOR_MODEL (.env). Шаги цепей в основном механические по готовой спеке — быстрый
# исполнитель ускоряет цепь; ДУМАНЬЕ (планировщик декомпозиции, самопочинка, адаптация
# плана, куратор) остаётся на кондукторе ORCH_MODEL и этим флагом НЕ трогается.
# Дефолт (переменной нет / пустая) = ORCH_MODEL байт-в-байт — поведение как до правки;
# откат = убрать EXECUTOR_MODEL из .env + рестарт демона, без деплоя.
# КЛАСС 404 (урок ПК b18ad08, KB 12.07): claude -p принимает только ПОЛНЫЕ model id,
# короткий алиас в конфиге → 404 от API. Известные алиасы нормализуем на импорте;
# незнакомое значение не трогаем (на невалидной primary CLI сам уйдёт на --fallback-model).
_MODEL_ALIASES = {
    "fable": "claude-fable-5",
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}
# СНЯТИЕ ГОЛОВЫ (30.07.2026, решение владельца «Opus 5 — единственная голова обеих полос»):
# слой ПОВЕРХ алиасов. Любое имя снятой модели — короткое, «семейство-версия» или полное — после
# нормализации уводится на claude-opus-5, поэтому застрявшее в чьём-то окружении старое значение
# не вернёт её мимо .env. Ключи слева убрать НЕЛЬЗЯ: тогда старое значение уйдёт в claude -p как
# есть и даст 404 (класс b18ad08).
_MODEL_RETIRED = {"claude-fable-5": "claude-opus-5"}


def _normalize_model(name):
    """Короткий алиас → полный model id (класс 404 b18ad08); имя снятой головы → claude-opus-5.
    Полные id и незнакомые значения — как есть; суффиксы вида [1m] сохраняются
    («opus-4-8[1m]» → «claude-opus-4-8[1m]»)."""
    n = (name or "").strip()
    low = n.lower()
    if low in _MODEL_ALIASES:
        out = _MODEL_ALIASES[low]
    elif re.match(r"^(fable|opus|sonnet|haiku)-\d", low):  # семейство-версия без префикса claude-
        out = "claude-" + n
    else:
        out = n
    return _MODEL_RETIRED.get(out.lower(), out)


_EXECUTOR_MODEL_RAW = (os.environ.get("EXECUTOR_MODEL") or "").strip()
EXECUTOR_MODEL = _normalize_model(_EXECUTOR_MODEL_RAW) if _EXECUTOR_MODEL_RAW else ORCH_MODEL

import task_metrics  # единый формат строки METRICS (обе полосы) + norm_effort/extract_tokens
import status_truth  # ПРАВДА СТАТУСА (зеркало ПК-фикса 5f2be1c/1597cbe, 30.07.2026): код причины
                     # провала + следы работы в окне задачи. Подробности класса — в самом модуле.
# УРОВЕНЬ УСИЛИЙ ИСПОЛНИТЕЛЯ (24.07.2026): claude -p принимает --effort (low/medium/high/xhigh/max);
# на VPS раньше НЕ передавался -> CLI брал дефолт. Выносим в env EXECUTOR_EFFORT (дефолт xhigh —
# доктрина «каждая задача ultrathink»); незнакомое значение -> xhigh (task_metrics.norm_effort).
EXECUTOR_EFFORT = task_metrics.norm_effort(os.environ.get("EXECUTOR_EFFORT"))
RESULT_MAX = 4500        # Bridge режет result на 5000 — оставляем запас
LOG_PATH = os.path.join(REPO, "orchestrator_daemon.log")

# === ХВОСТ 2 (28.07.2026): ДЛИНА ДО ОБРЕЗКИ НЕ ТЕРЯЕТСЯ ===
# result режется под RESULT_MAX ДО записи в очередь, поэтому devbot видел уже обрубок и мог
# сказать лишь «обрезано», не зная СКОЛЬКО срезано (остаток коммита 8ed16b0 дословно: «полной
# длины ИСХОДНОГО отчёта в карточке нет и быть не может»). Теперь длину несёт сам текст:
# машиночитаемая пометка в хвосте (её парсит devbot._TRUNC_FULL_RE), итог по-прежнему ≤ RESULT_MAX.
TRUNC_HEAD = "✂️ РЕЗУЛЬТАТ ОБРЕЗАН ДЕМОНОМ"


def _trunc_note(full_len, kept):
    """Хвостовая пометка обрезки: полная длина ДО обрезки + сколько реально попало в очередь."""
    return (f"\n\n{TRUNC_HEAD}: полная длина {full_len} симв., в очередь попало {kept} — "
            f"срезано {full_len - kept} симв. (потолок RESULT_MAX={RESULT_MAX}). "
            f"Полный вывод ищи в orchestrator_daemon.log / cc_log задачи.")


def cap_result(text, limit=None):
    """Обрезать result под потолок очереди, СОХРАНИВ полную длину прямо в тексте.
    Короче потолка → возвращаем байт-в-байт (пометки нет, поведение прежнее).
    Длиннее → голова + _trunc_note; итоговая длина гарантированно ≤ limit (цикл ужимает
    голову, пока пометка со своими числами не поместится — числа сами меняют её длину)."""
    limit = RESULT_MAX if limit is None else limit
    s = "" if text is None else str(text)
    n = len(s)
    if n <= limit:
        return s
    keep = max(0, limit - len(_trunc_note(n, limit)))
    while keep > 0 and keep + len(_trunc_note(n, keep)) > limit:
        keep -= 1
    return s[:keep] + _trunc_note(n, keep)


# === ХВОСТ 1 (28.07.2026): ЖУРНАЛ ВЗЯТИЙ В РАБОТУ ===
# «🔄 в работе» рождалось ТОЛЬКО из 45-секундного снимка in_progress, который делает devbot.
# Задача, прожившая 5–9 секунд, между двумя опросами в снимок не попадала ВООБЩЕ — анонс
# взятия не приходил ни разу (живой пример: задачи 14/15 28.07). Состояние опрашивать поздно —
# записываем СОБЫТИЕ: строка JSONL на каждое реальное взятие из process_new. Событие лежит в
# файле и доезжает независимо от того, сколько задача прожила; devbot читает журнал с оффсетом.
# Пишем ТОЛЬКО из process_new (взятие задачи владельца). Synthetic-карточки демона (сводки,
# коррекции плана, самопочинка) claim'ятся своими вызовами bc.claim_task и события НЕ порождают —
# иначе каждая служебная карточка получала бы лишний анонс «в работе».
CLAIM_LOG_PATH = os.path.join(REPO, "orchestrator_claims.jsonl")
CLAIM_LOG_MAX_BYTES = 200_000    # ~800 событий; при превышении оставляем хвост
CLAIM_LOG_KEEP_LINES = 200


def write_claim_event(task, path=None):
    """Записать факт взятия задачи в работу строкой JSONL. Поля повторяют строку очереди
    (id/created/from/lane/task_text) — devbot гоняет по ним ТЕ ЖЕ helpers дедупа и маршрутизации;
    updated = момент взятия (по нему seed-on-start гасит историю до старта бота).
    FAIL-SAFE: любой сбой записи логируется и НЕ трогает исполнение задачи — видимость не
    важнее работы. Под тестом в БОЕВОЙ журнал не пишем (класс METRICS-мусора 25.07): тест
    обязан передать свой path, иначе событие не пишется вовсе."""
    path = path or CLAIM_LOG_PATH
    if _UNDER_TEST and os.path.abspath(path) == os.path.abspath(CLAIM_LOG_PATH):
        return False
    try:
        rec = {
            "id": task.get("id"),
            "created": str(task.get("created") or ""),
            "from": str(task.get("from") or ""),
            "lane": str(task.get("lane") or ""),
            "task_text": str(task.get("task_text") or "")[:400],
            "updated": datetime.datetime.now(datetime.timezone.utc)
                       .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        try:                                   # ротация: журнал не растёт бесконечно
            if os.path.getsize(path) > CLAIM_LOG_MAX_BYTES:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    tail = f.readlines()[-CLAIM_LOG_KEEP_LINES:]
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(tail)
        except OSError:
            pass                               # журнала ещё нет / не прочли — просто дописываем
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        log.warning("журнал взятий: событие id=%s не записано (%s) — анонс «в работе» "
                    "останется на снимке in_progress", task.get("id"), e)
        return False

# §12 корень 1 (06.07.2026): под тест-прогоном НЕ трогаем боевой orchestrator_daemon.log —
# сам ИМПОРТ модуля (test_orchestrator_*/test_convert_loop_break делают `import orchestrator_daemon`)
# конфигурировал FileHandler на ЖИВОЙ лог, и любой log.info фикстуры лил строки в него. Тест-прогон
# определяем по: активный pytest / entry-point tests/test_*.py / явный флаг ORCH_DAEMON_TEST=1 →
# логгер в NullHandler (ни файла, ни консоли). Боевой демон (systemd, argv=orchestrator_daemon.py) —
# как раньше, пишет в LOG_PATH.
# 25.07.2026: признак вынесен в task_metrics.under_test и ДОПОЛНЕН ORCH_TEST_MODE=1. Прежний набор
# опознавал тест по имени входного файла test_*, и КОПИЯ теста под другим именем (живой случай:
# `git show <хеш>:tests/test_x.py > /tmp/old.py`) снова писала в боевой журнал — 5 строк METRICS,
# неотличимых от живых задач. ORCH_TEST_MODE=1 ставит gate.py всем тест-процессам; в бою его нет
# ни в .env, ни в юните, и демон сам вычищает его из дочерних окружений (child_env.pop).
_UNDER_TEST = task_metrics.under_test(
    (sys.argv[0] if sys.argv else ""), os.environ, sys.modules)
if _UNDER_TEST:
    logging.basicConfig(level=logging.INFO, handlers=[logging.NullHandler()])
else:
    logging.basicConfig(
        filename=LOG_PATH, level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
log = logging.getLogger("orchestrator_daemon")

bc = BridgeClient(timeout=90)
_running = True


def _stop(signum, _frame):
    """SIGTERM/SIGINT (в т.ч. от systemctl stop) — мягкая остановка после текущей итерации."""
    global _running
    _running = False
    log.info("получен сигнал %s — останавливаюсь после текущей итерации", signum)


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


# Маркер самодекларации красной зоны (заход 2б-2). Демон НЕ угадывает формулировки отказа —
# инструктирует claude -p вывести этот маркер вместо попытки обойти гейт.
NA_MARKER = "NEEDS_APPROVAL:"

# Guard-маркер (шаг 2/6 родитель 185): pretool_guard пишет /tmp/cc_guard_block/{tid}.json
# при красном блоке внутри headless-задачи → монитор-поток видит файл → гасит claude-подпроцесс
# → run_task возвращает needs_approval с честной карточкой. Никакого «продолжаю другими путями».
GUARD_BLOCK_DIR = "/tmp/cc_guard_block"
_POPEN = subprocess.Popen   # module-level для замены в тестах (тест мокает OD._POPEN)

# ТЕЧЬ МАРКЕРОВ (цель 36 шаг 3, 29.07.2026). Маркер удаляется РОВНО в одном месте —
# _guard_marker_clear перед запуском задачи ТОГО ЖЕ id. После обработки (needs_approval /
# жёсткий блок) файл остаётся в боевом каталоге НАВСЕГДА: ни одной ветки удаления «за собой»
# в коде нет. Разведка цели 36 нашла инертные 12, 27, 399 (12/27 — наследие тест-протечки
# CC_TASK_ID, её источник закрыт 28.07 через TEST_BLOCK_DIR/префикс; 399 — из СТАРОЙ нумерации
# очереди, т.е. номера уже один раз сбрасывались и могут повториться).
# Детонации «повтор номера» сегодня НЕТ (clear стоит перед КАЖДЫМ запуском — доказано тестом),
# но копящийся мусор вреден иначе: (1) врёт при разборе инцидента — свежий блок живой задачи
# неотличим от трёхнедельного трупа; (2) держит весь барьер на ОДНОМ вызове clear — любая
# будущая ветка запуска claude с CC_TASK_ID без clear делает старый файл боевым (пост-проверка
# в _run_task_impl сработает даже без монитора и выдаст ЧУЖУЮ карточку).
# Лечение — уборка по возрасту: маркер старше GUARD_MARKER_TTL удаляется в начале cycle().
# ГОНКИ С ЖИВЫМ МАРКЕРОМ НЕТ: демон одно-воркерный, run_task блокирующий → пока исполняется
# задача, cycle() (а с ним уборка) не крутится; дефолт TTL(6ч) с запасом больше TASK_TIMEOUT_DEV.
GUARD_MARKER_TTL = _env_int("GUARD_MARKER_TTL", 21600)   # 6ч; 0 = уборка выключена (откат)


def _guard_marker_path(tid):
    return os.path.join(GUARD_BLOCK_DIR, f"{tid}.json")


def _guard_marker_clear(tid):
    try:
        os.remove(_guard_marker_path(tid))
    except OSError:
        pass


def _guard_marker_read(tid):
    try:
        with open(_guard_marker_path(tid), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _guard_is_hard(data):
    """True если маркер гарда несёт blocktype=hard (порт из stash@{1}): запись по ЖИВОЙ сущности.
    Такая задача закрывается failed БЕЗ кнопки approve — «да» тут не предусмотрено доктриной."""
    return bool(data) and (data or {}).get("blocktype") == "hard"


# === ЗАМОК ПРОИСХОЖДЕНИЯ КРАСНОЙ КАРТОЧКИ (класс «подделка карточек», 31.07.2026) ===
# Зеркало класса, закрытого на ПК-полосе (9e518b7/3124e25/8bcf1ec). Дыра была одна на два театра:
# строку «op=… | …» печатала САМА МОДЕЛЬ, демон делал из неё красную карточку с кнопками МИМО
# гарда, а после «да» КЛАСС ОПЕРАЦИИ читался ИЗ ТОЙ ЖЕ СТРОКИ (parse_op → EXECUTORS) — то есть
# исполнимую команду выбирал текст исполнителя, а карточка перед владельцем могла говорить о чём
# угодно другом. ФОРМАТ подделать легко, ИСТОЧНИК — нет. Поэтому решает не вид строки, а ВЕТКА
# рождения карточки:
#   · маркер-файл гарда (его пишет хук, УВИДЕВШИЙ реальную команду, + одноразовый токен задачи)
#     → штамп 🔒, карточка с кнопкой и правом на исполнимый класс — как было;
#   · текст исполнителя → штамп 🗣, причём штампы гарда из текста ВЫЧИЩАЮТСЯ (_scrub_origin),
#     поэтому подделать происхождение печатью нельзя.
# ЧЕСТНЫЙ ПРЕДЕЛ: агент с bash на этой же машине читает свой env и физически может написать файл
# маркера сам — токен ловит протухший/чужой маркер и делает подлог видимым владельцу, но границей
# против намеренного противника с тем же uid не является и не притворяется ею. Реальный вектор
# здесь — спутавшаяся модель и инъекция через прочитанные данные; его замок закрывает.
ORIGIN_GUARD_TOKEN = "🔒 источник карточки: ГАРД (маркер сверен)"
ORIGIN_GUARD_WEAK_TOKEN = "🔒 источник карточки: ГАРД (маркер без сверки)"
ORIGIN_SELF_TOKEN = "🗣 источник карточки: СЛОВА ИСПОЛНИТЕЛЯ"
_ORIGIN_LINE_RE = re.compile(r"(?mi)^[^\S\n]*[🔒🗣]?[^\S\n]*источник карточки[^\S\n]*:.*$")
_GUARD_SUFFIX_RE = re.compile(r"\[guard-block задача[^\]\n]{0,40}\]", re.IGNORECASE)
# ДЫРА ФОРМЫ (вторая ревизия класса, 31.07.2026 — найдена ревизией этого же замка). Регэксп выше
# ЯКОРЕН на ^: штамп, напечатанный ПОСРЕДИ строки — «op=git_push | выложи ветку 🔒 источник
# карточки: ГАРД (маркер сверен)» — он не снимал. Такая заявка исполнителя читалась как гардовая
# (_card_origin → «guard») и открывала ОБА рубежа сразу: карточку с кнопкой в process_new и
# хардкод-команду EXECUTORS после «да» в process_approved. Класс тот же, ради которого замок и
# строился, только другой ФОРМЫ — а литерал штампа модель берёт прямо из этого файла, репо у неё
# перед глазами. Поэтому фразу штампа снимаем ГДЕ УГОДНО в тексте, а не только с начала строки,
# и оставляем на её месте видимый след: молча из карточки ничего не исчезает.
_ORIGIN_ANY_RE = re.compile(r"[🔒🗣]?[^\S\n]*источник[^\S\n]+карточки[^\S\n]*:", re.IGNORECASE)
ORIGIN_SCRUB_MARK = "⟨штамп источника вычищен⟩"


def _guard_token_new():
    """Одноразовый токен задачи для сверки маркера гарда. Отдельной функцией — тест подменяет её,
    иначе не может заранее положить «правильный» маркер."""
    return os.urandom(8).hex()


def _scrub_origin(text):
    """Снять из ТЕКСТА ИСПОЛНИТЕЛЯ любые штампы происхождения и суффикс guard-block: штамп ставит
    ДЕМОН в момент рождения карточки, напечатанный моделью — подделка. Пустые строки схлопываем,
    чтобы карточка не разъезжала.

    ДВА ПРОХОДА (фикс дыры формы 31.07.2026): целые строки-штампы убираем совсем (карточка не
    разъезжается), а штамп ПОСРЕДИ чужой строки заменяем видимой пометкой — вырезать полстроки
    нельзя (потеряется смысл заявки), оставить как есть тем более (это и была дыра)."""
    t = _ORIGIN_LINE_RE.sub("", str(text or ""))
    t = _ORIGIN_ANY_RE.sub(ORIGIN_SCRUB_MARK, t)
    t = _GUARD_SUFFIX_RE.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _self_origin_stamp():
    return (f"{ORIGIN_SELF_TOKEN} — гард ни одной команды не перехватывал; «да» здесь = поручить "
            f"работу обычной задачей, а не исполнить операцию, названную в строке")


def _stamp_self_origin(what):
    """Дескриптор ЗАЯВКИ ИСПОЛНИТЕЛЯ: чужие штампы вычищены, свой честный приклеен в КОНЕЦ —
    в начале стоит «op=… | », и этот формат держат тесты и дедуп карточек в devbot.

    Тело режем ПОД штамп (фикс 31.07.2026): происхождение читается по ПОСЛЕДНЕЙ строке, поэтому
    штамп обязан пережить обрезку под потолок очереди. Иначе длинная заявка теряла бы штамп на
    cap'е — владелец не увидел бы источник, а карточка стала бы «legacy» без причины."""
    stamp = _self_origin_stamp()
    return f"{cap_result(_scrub_origin(what), max(200, RESULT_MAX - len(stamp) - 1))}\n{stamp}"


def _card_origin(what):
    """Происхождение карточки — по штампу, который поставил ДЕМОН при рождении. «legacy» =
    карточка, лежавшая в очереди ДО этой правки (штампа нет): прав на исполнимый класс не даём
    (fail-closed) — доказать происхождение нечем, а конверт op=other владельцу доступен и так.

    ЧИТАЕМ ТОЛЬКО ПОСЛЕДНЮЮ непустую строку и только с её НАЧАЛА (фикс дыры формы 31.07.2026).
    Демон приклеивает свой штамп ПОСЛЕДНИМ и делает это ПОСЛЕ скраба чужого текста — значит это
    место модель занять не может. Совпадение штампа где-то в теле происхождением больше не
    считается: раньше хватало вписать литерал в середину своей же строки. Штамп не на своём месте
    (обрезка, чужая правка result, подделка) → «legacy» = карточка живёт, прав на исполнимый класс
    нет. Порядок проверок — от слабейшего права к сильнейшему; пересечений у литералов нет."""
    lines = [ln.strip() for ln in str(what or "").splitlines() if ln.strip()]
    last = lines[-1] if lines else ""
    if last.startswith(ORIGIN_SELF_TOKEN):
        return "self"
    if last.startswith(ORIGIN_GUARD_WEAK_TOKEN):
        return "guard_weak"
    if last.startswith(ORIGIN_GUARD_TOKEN):
        return "guard"
    return "legacy"


def _guard_what(tid, data, verified=True):
    """Строка needs_approval из данных маркера: op=other + hit + card + ШТАМП происхождения.
    Тело карточки тоже скрабим: в нём лежит текст ПЕРЕХВАЧЕННОЙ КОМАНДЫ, то есть буквы модели."""
    hit = str((data or {}).get("hit") or "guard_block")
    card = str((data or {}).get("card") or "")
    body = card if card else f"guard заблокировал операцию «{hit}» в headless-задаче"
    # Штамп — КОНСТАНТА (номер задачи уже стоит строкой выше): отпечаток карточки в devbot
    # считается по тексту, и переменная часть в штампе разбила бы дедуп «×N одинаковых».
    stamp = (f"{ORIGIN_GUARD_TOKEN} — перехвачена реальная команда этой задачи" if verified else
             f"{ORIGIN_GUARD_WEAK_TOKEN} — токен задачи не сошёлся: маркер мог остаться от "
             f"прошлого прогона или написан не хуком. Карточку показываю (реальный блок терять "
             f"нельзя), но прав на исполнимый класс у неё нет")
    head = f"op=other | [{hit}] {_scrub_origin(body)}\n[guard-block задача {tid}]"
    # тело режем ПОД штамп — он последняя строка и несёт происхождение (см. _card_origin)
    return f"{cap_result(head, max(200, RESULT_MAX - len(stamp) - 1))}\n{stamp}"


def _guard_monitor_loop(tid, proc, stop_event, kill_event, card_holder):
    """Фон-поток: каждые 2с проверяем маркер. Нашли → terminate claude → kill_event."""
    path = _guard_marker_path(tid)
    while not stop_event.wait(2.0):
        if os.path.exists(path):
            data = _guard_marker_read(tid)
            card_holder.append(data or {})
            try:
                proc.terminate()
            except Exception:
                pass
            kill_event.set()
            return


def _guard_markers_sweep(directory=None, now=None):
    """Убрать осиротевшие guard-маркеры: файлы «*.json» старше GUARD_MARKER_TTL по mtime.
    Возврат — число убранных (для лога/теста).

    ТЕСТ БОЕВОЕ НЕ ТРОГАЕТ (симметрия фикса 28.07, где тест перестал ПИСАТЬ в боевой каталог):
    при ORCH_TEST_MODE=1 (его гейт ставит всем тест-процессам) уборка дефолтного каталога —
    no-op; явно переданный `directory` = осознанный вызов, работает всегда.

    FAIL-SAFE: TTL<=0 (рубильник) / каталога нет / listdir или stat падает / remove падает →
    тихо пропускаем. Уборка не критична — барьер держит _guard_marker_clear перед запуском,
    её отказ не должен ронять цикл демона."""
    if GUARD_MARKER_TTL <= 0:
        return 0
    explicit = directory is not None
    d = directory or GUARD_BLOCK_DIR
    if not explicit and (os.environ.get("ORCH_TEST_MODE") or "").strip():
        return 0
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    now = time.time() if now is None else now
    killed = 0
    for name in names:
        if not name.endswith(".json"):
            continue                       # чужое в каталоге не наше дело
        path = os.path.join(d, name)
        try:
            age = now - os.path.getmtime(path)
        except OSError:
            continue
        if age < GUARD_MARKER_TTL:
            continue                       # свежий — может принадлежать живой задаче
        try:
            os.remove(path)
        except OSError:
            continue
        killed += 1
        log.info("guard-маркер %s осиротел (возраст %sс > TTL %sс) → убран",
                 name, int(age), GUARD_MARKER_TTL)
    return killed


def _fail_card(out, err, rc):
    """§12 корень 3 (06.07.2026): ЧИСТАЯ карточка провала claude -p — НЕ сырой дамп всего
    stdout+stderr (шум, усиленный громким-провалом d946f92). Отдаём осмысленную суть: первую
    строку stdout (по контракту преамбулы = сводка ≤400) + хвост stderr (реальная ошибка),
    капнуто коротко. Полный поток claude -p как карточку НЕ релеим — детали задача пишет в cc_log.
    Границу «громкий провал ДЕНЕГ» (splinter._note_llm_loss, force-пуш) это НЕ трогает —
    там отдельный механизм, он остаётся."""
    o = (out or "").strip()
    e = (err or "").strip()
    summary = o.splitlines()[0].strip() if o else ""
    etail = " / ".join([x for x in e.splitlines() if x.strip()][-2:]) if e else ""
    body = " | ".join([b for b in (summary, etail) if b]) or f"exit={rc}"
    return f"claude -p упал (exit={rc}): {body}"[:600]


def _truthful_fail(tid, base, code, task=None, started=None, max_len=RESULT_MAX):
    """ПРАВДА СТАТУСА (зеркало ПК-фикса 5f2be1c/1597cbe, 30.07.2026) — единая точка обрамления
    провала: к прежнему честному диагнозу добавляются КОД ПРИЧИНЫ и СЛЕДЫ РАБОТЫ В ОКНЕ задачи.

    Зачем: по статусу планируется следующий шаг. Голое «провалена» у задачи, которая успела
    закоммитить и записать журнал, дважды за сутки увело план в неверную сторону (инцидент ПК,
    задачи 54 и 61) — и владелец видел «упало» там, где работа лежит в git.
    ВАЖНО: текст говорит «в окне задачи ЕСТЬ работа», а НЕ «работа выполнена» — окно ловит и
    параллельные сессии, авторства оно не доказывает (живая проверка на ПК: 8 коммитов в окне,
    свой — один). Смысл base и его ведущий маркер (⏱/✋) сохраняются: на маркер смотрят гейт
    самопочинки и пропуск куратора.
    FAIL-SAFE: любой сбой сборки (git недоступен, реестр битый, что угодно) → прежний голый
    текст, байт-в-байт как до фикса. Правда статуса не смеет ломать закрытие задачи."""
    try:
        txt = status_truth.fail_result(base, code, task=task, task_id=tid, started=started,
                                       repo=REPO, max_len=max_len)
        log.warning(status_truth.log_line(tid, code))
        return txt
    except Exception as e:
        log.warning("правда статуса: сборка итога id=%s упала (%s) — прежний голый текст", tid, e)
        return str(base or "")[:max_len]


def _truthful_fail_last(tid, base, task=None):
    """То же обрамление, но код причины берётся из канала ПОСЛЕДНЕГО run_task (см. _LAST_RUN).
    Нужен там, где терминальный текст собирает слой самопочинки: код туда не дотянуть аргументом,
    не сломав моки его собственных сьютов.
    Канал пуст либо принадлежит другой задаче (run_task подменён моком / путь без исполнения) →
    прежний голый текст, байт-в-байт как до фикса."""
    if _LAST_RUN.get("task") != tid or not _LAST_RUN.get("fail_code"):
        return str(base or "")[:RESULT_MAX]
    return _truthful_fail(tid, base, _LAST_RUN["fail_code"], task=task,
                          started=_LAST_RUN.get("started"))

# === ФИКС КЛАССА «самомодификация → ложный failed» (урок задачи 105, 07.07.2026) ===
# Самомод-задача правит orchestrator_daemon.py и по доктрине ставит отложенный
# `systemd-run --on-active=Ns systemctl restart orchestrator-daemon` ПОСЛЕДНИМ действием. Рестарт
# гасит ВЕСЬ cgroup сервиса, включая claude -p самой задачи (SIGTERM → exit=143) — работа к этому
# моменту СДЕЛАНА (RESULT в cc_log, commit в git), но демон метил задачу failed «claude -p упал».
# Отличаем «убит запланированным рестартом» от настоящего падения по обязательным признакам
# (любое сомнение → прежний честный failed, fail-safe):
#   1) exit-код SIGTERM (143 у CLI / -15 от subprocess) — SIGKILL/oom (137/-9) сюда НЕ попадают;
#   2) демон САМ получил SIGTERM тем же моментом (_running=False): systemd гасит cgroup целиком;
#      точечный kill claude-процесса или oom демона не трогают (_running останется True);
#   3) в тексте задачи признак самомодификации (orchestrator_daemon / «самомодификация»);
#   4) в systemd ВИДНА transient-единица systemd-run с рестартом демона: run-*.timer ещё не
#      сработал ИЛИ run-*.service прямо сейчас гонит restart (он блокируется, пока демон не
#      погашен — мы ещё живы и успеваем её увидеть). Ручной systemctl stop/restart владельцем
#      такой единицы НЕ создаёт → останется честный failed.
#
# ФИКС ДЫРЫ класса 48d9c64 (урок задачи 122, 07.07.2026): признаки выше НЕ отличали СВОЙ рестарт
# от ЧУЖОГО — задача, взятая в окно ЧУЖОГО отложенного рестарта (единица уже тикала, когда её
# claude стартовал), гибла на СТАРТЕ и ложно закрывалась done+🔁 («фантомный done», работа
# терялась). Два слоя:
#   СЛОЙ 1 (профилактика, process_new): пока systemd-run-единица рестарта демона ЖИВА
#     (ActiveState active/activating — таймер тикает или restart уже идёт) — новые задачи НЕ
#     берём («пауза приёма»); они спокойно ждут в new, свежий демон возьмёт их после рестарта.
#     Мёртвые/failed-остовы единиц паузу НЕ дают (иначе залипший остов заморозил бы приём).
#   СЛОЙ 2 (детект, run_task): 5-й признак — ВРЕМЯ. Единица создана ДО старта claude задачи
#     (min monotonic-меток единицы < time.monotonic() старта — одна шкала CLOCK_MONOTONIC)
#     = ЧУЖОЙ рестарт → задача возвращается в new (клон дословно; НЕ failed — думателя зря не
#     дёргаем) и переисполняется после рестарта. Создана ПОСЛЕ старта (или времени не видно —
#     сомнение) = прежний путь 48d9c64: признак 3 (самомод-ТЗ) → done+🔁, иначе честный failed.
_SIGTERM_RCS = (143, -15)
_SELFMOD_RE = re.compile(r"orchestrator[-_ ]?daemon|самомодифика", re.IGNORECASE)
_RESTART_NEEDLE = "restart orchestrator-daemon"


def _restart_probe():
    """ОДИН systemctl-вызов → свойства transient-единиц systemd-run (run-*.timer/service),
    чей блок содержит команду рестарта демона. Возврат (visible, pending, earliest_mono_sec):
      visible  — единица видна (признак 4, как в 48d9c64);
      pending  — единица ЖИВА (ActiveState active/activating): окно, в котором новые задачи
                 брать нельзя (слой 1); мёртвый/failed остов паузы НЕ даёт;
      earliest — самая ранняя monotonic-метка (сек с boot; шкала = time.monotonic()) среди
                 таких единиц ≈ момент создания systemd-run; None = времени не видно (сомнение).
    Любой сбой пробы = (False, False, None) — fail-safe: детект молчит, приём не встаёт."""
    try:
        p = subprocess.run(
            ["systemctl", "show", "run-*.service", "run-*.timer",
             "--property=Id,Description,ActiveState,"
             "ActiveEnterTimestampMonotonic,InactiveExitTimestampMonotonic"],
            capture_output=True, text=True, timeout=10)
        out = p.stdout or ""
    except Exception as e:
        log.warning("planned-restart: проба systemctl не отработала (%s) — считаю НЕплановым", e)
        return False, False, None
    visible, pending, earliest = False, False, None
    for block in out.split("\n\n"):
        if _RESTART_NEEDLE not in block:
            continue
        visible = True
        state = ""
        for line in block.splitlines():
            k, _sep, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k == "ActiveState":
                state = v
            elif k in ("ActiveEnterTimestampMonotonic", "InactiveExitTimestampMonotonic"):
                try:
                    usec = int(v)
                except ValueError:
                    continue
                if usec > 0 and (earliest is None or usec / 1e6 < earliest):
                    earliest = usec / 1e6
        if state in ("active", "activating"):
            pending = True
    return visible, pending, earliest


def _restart_pending():
    """True → отложенный плановый рестарт демона ЖИВ в systemd (слой 1: пауза приёма new)."""
    return _restart_probe()[1]


def _mem_available_mb():
    """MemAvailable из /proc/meminfo в МБ. None при любой ошибке чтения (fail-safe)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return None


def _live_claude_count():
    """Число живых claude-процессов по /proc/*/cmdline (первый элемент = исполняемый).
    None при ошибке сканирования (fail-safe: гейт пропускается)."""
    try:
        n = 0
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                with open(f"/proc/{entry.name}/cmdline", "rb") as f:
                    cmd = f.read(512)
                first = cmd.split(b"\x00")[0]
                if b"claude" in first:
                    n += 1
            except OSError:
                pass
        return n
    except Exception:
        return None


def _live_claude_rss_mb():
    """Суммарный RSS всех живых claude-процессов в МБ. None при ошибке (fail-safe)."""
    try:
        total_kb = 0
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            pid = entry.name
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read(512)
                if b"claude" not in cmd.split(b"\x00")[0]:
                    continue
                with open(f"/proc/{pid}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            total_kb += int(line.split()[1])
                            break
            except OSError:
                pass
        return total_kb // 1024
    except Exception:
        return None


def _mem_gate_check():
    """Гейт памяти перед стартом claude -p.
    True  = дефицит (не берём задачу, она остаётся в new).
    False = памяти достаточно / /proc нечитаем (fail-safe) / MEM_MIN_MB=0 (выключен).
    Два критерия: (1) MemAvailable < MEM_MIN_MB; (2) суммарный RSS claude >= CLAUDE_RSS_TOTAL_MB.
    После MEM_DENY_ALERT последовательных «настоящих» отказов отправляет synthetic-карточку в 328."""
    global _mem_wait_until, _mem_deny_count
    if MEM_MIN_MB <= 0:
        return False
    now = time.monotonic()
    if now < _mem_wait_until:
        log.info("⏳ ждёт памяти: cooldown %ds — задачи ждут в new (порог=%dМБ)",
                 int(_mem_wait_until - now), MEM_MIN_MB)
        return True
    mb = _mem_available_mb()
    if mb is None:
        return False  # fail-safe: /proc/meminfo нечитаем → гейт пропускается
    # (2) RSS живых claude
    crss = _live_claude_rss_mb() if CLAUDE_RSS_TOTAL_MB > 0 else None
    low_mem = mb < MEM_MIN_MB
    high_rss = (crss is not None and crss >= CLAUDE_RSS_TOTAL_MB)
    if not low_mem and not high_rss:
        _mem_deny_count = 0   # память в норме — сброс счётчика
        return False
    _mem_wait_until = now + MEM_RETRY_SEC
    _mem_deny_count += 1
    if low_mem:
        log.warning("⏳ mem-gate: MemAvail %dМБ < %dМБ — задача ждёт new, ретрай %ds (подряд=%d)",
                    mb, MEM_MIN_MB, MEM_RETRY_SEC, _mem_deny_count)
    if high_rss:
        log.warning("⏳ mem-gate: claude RSS %dМБ >= %dМБ — задача ждёт new, ретрай %ds (подряд=%d)",
                    crss, CLAUDE_RSS_TOTAL_MB, MEM_RETRY_SEC, _mem_deny_count)
    if _mem_deny_count >= MEM_DENY_ALERT:
        _mem_deny_count = 0   # сброс: следующие MEM_DENY_ALERT отказов дадут ещё один алерт
        _mem_alert_328(mb)
    return True


def _mem_alert_328(mb):
    """Synthetic-карточка в 328 при MEM_DENY_ALERT последовательных OOM-отказах. Fail-safe тишина."""
    try:
        wait_min = round(MEM_DENY_ALERT * MEM_RETRY_SEC / 60)
        msg = (f"⚠️ OOM-ГЕЙТ: памяти {mb}МБ < {MEM_MIN_MB}МБ · "
               f"{MEM_DENY_ALERT} отказа(ов) подряд (~{wait_min} мин) · "
               f"задачи ждут в new · при восстановлении подберутся автоматически")
        r = bc.enqueue_task("Filipp-328", "[⚠️ oom-гейт] памяти мало — задачи ждут")
        if not r.get("ok"):
            return
        sid = r.get("id")
        bc.claim_task(sid)
        bc.complete_task(sid, "done", msg)
        log.warning("mem-gate: карточка в 328 (id=%s): %s", sid, msg)
    except Exception as e:
        log.warning("mem-gate: карточка в 328 упала (%s) — тишина", e)


def _proc_gate_check():
    """Гейт параллелизма: живых claude >= MAX_CLAUDE_PROCS → задача ждёт в new.
    True = превышение. False = ОК / MAX_CLAUDE_PROCS=0 (выключен) / /proc нечитаем (fail-safe).
    Механика cooldown/алерт идентична _mem_gate_check."""
    global _proc_wait_until, _proc_deny_count
    if MAX_CLAUDE_PROCS <= 0:
        return False
    now = time.monotonic()
    if now < _proc_wait_until:
        log.info("⏳ proc-gate: cooldown %ds — ждём слота claude (лимит=%d)",
                 int(_proc_wait_until - now), MAX_CLAUDE_PROCS)
        return True
    n = _live_claude_count()
    if n is None:
        return False  # fail-safe: /proc нечитаем → гейт пропускается
    if n < MAX_CLAUDE_PROCS:
        _proc_deny_count = 0
        return False
    _proc_wait_until = now + PROC_RETRY_SEC
    _proc_deny_count += 1
    log.warning("⏳ proc-gate: живых claude %d >= %d — задача ждёт new, ретрай %ds (подряд=%d)",
                n, MAX_CLAUDE_PROCS, PROC_RETRY_SEC, _proc_deny_count)
    if _proc_deny_count >= PROC_DENY_ALERT:
        _proc_deny_count = 0
        _proc_alert_328(n)
    return True


def _proc_alert_328(n):
    """Synthetic-карточка в 328 при PROC_DENY_ALERT последовательных proc-gate отказах. Fail-safe тишина."""
    try:
        wait_min = round(PROC_DENY_ALERT * PROC_RETRY_SEC / 60)
        msg = (f"⚠️ PROC-ГЕЙТ: живых claude {n} >= {MAX_CLAUDE_PROCS} · "
               f"{PROC_DENY_ALERT} отказа(ов) подряд (~{wait_min} мин) · "
               f"задачи ждут в new · при освобождении слота подберутся автоматически")
        r = bc.enqueue_task("Filipp-328", "[⚠️ proc-гейт] claude занят — задачи ждут")
        if not r.get("ok"):
            return
        sid = r.get("id")
        bc.claim_task(sid)
        bc.complete_task(sid, "done", msg)
        log.warning("proc-gate: карточка в 328 (id=%s): %s", sid, msg)
    except Exception as e:
        log.warning("proc-gate: карточка в 328 упала (%s) — тишина", e)


def _prune_chain_cache():
    """Выгрузка завершённых цепей: _summarized/_adapt_finish растут без ограничения.
    Если _summarized > MAX_CHAIN_CACHE — отсекаем старые (наименьшие pid) до MAX_CHAIN_CACHE,
    синхронно чистим осиротевшие записи _adapt_finish."""
    if len(_summarized) <= MAX_CHAIN_CACHE:
        return
    excess = sorted(_summarized)[:len(_summarized) - MAX_CHAIN_CACHE]
    for pid in excess:
        _summarized.discard(pid)
        _adapt_finish.pop(pid, None)
    log.info("chain-cache: pruned %d old pids (_summarized=%d)", len(excess), len(_summarized))


def _planned_restart_verdict(rc, task_text, t0_mono):
    """Классификация гибели claude -p задачи (см. блок-комментарий выше):
      None      — НЕ плановый рестарт → прежний честный failed;
      "own"     — СВОЙ рестарт (самомод-задача поставила единицу ПОСЛЕ своего старта,
                  работа сделана) → done+🔁 (фикс 48d9c64, байт-в-байт);
      "foreign" — ЧУЖОЙ рестарт (единица создана ДО старта claude этой задачи — гибель на
                  старте, работа НЕ делалась) → возврат задачи в new (фикс дыры, урок 122).
    Fail-safe: времени не видно / сомнение → ветка own только при самомод-признаке в ТЗ
    (прежние 4 признака), иначе None — не хуже 48d9c64."""
    if rc not in _SIGTERM_RCS:
        return None
    if _running:
        return None
    visible, _pending, earliest = _restart_probe()
    if not visible:
        return None
    if earliest is not None and t0_mono is not None and earliest < t0_mono:
        return "foreign"
    if _SELFMOD_RE.search(str(task_text or "")):
        return "own"
    return None


# === АВТО-ПЕРЕЧЕНЬ красных op (п.4 узкий, штаб 19.06) — РОВНО два, оба обратимы ===
# clasp_redeploy / CRM / Лист1 / деньги / set_fleet_* / delete_event — НЕ здесь (позже, особое «да»).
AUTO_OPS = ("git_push", "restart_splinter")

# Преамбула v3 (Q2 разблокирован 03.07: критерий обкатки ступени 2 выполнен — 3 «тз:» подряд done
# без ручных сессий, вкл. прод-фикс 3978a91). restart splinter теперь CC делает САМ оранжевым циклом
# (гейт→restart→проверка чистого старта→отчёт); кнопка op=restart_splinter остаётся фоллбэком.
# Red-zone (Лист1/CRM/деньги/clasp/sqlite3/delete) — БЕЗ изменений: маркер op=other, НЕ обходить гейт.
# v3.1 (03.07, урок задачи 43): правило самомодификации — рестарт orchestrator-daemon из задачи
# только ОТЛОЖЕННО (systemd-run --on-active=10s) и ПОСЛЕ отчёта, иначе рестарт убивает свой claude.
APPROVAL_PREAMBLE = (
    "Ты выполняешь задачу автономно в headless-режиме (без интерактивного подтверждения) в репо "
    "/root/turbobaby-manager-bot — CLAUDE.md и вся его дисциплина действуют.\n"
    "ДИСЦИПЛИНА (обязательно): перед правкой кода — бэкап (коммит/копия .bak); после правки — "
    "py_compile + тесты; перед git push — гейт (venv/bin/python3 gate.py; pre-push зовёт его сам); "
    "для промежуточных шагов цепи гейт автоматически работает в селективном режиме (только тесты "
    "затронутых модулей + smoke) — команда gate.py та же, режим прозрачный; вывод несёт пометку "
    "«гейт полный» / «гейт селективный (N тестов)» — упомяни в первой строке отчёта шага; "
    "каждый значимый шаг — строка в cc_log через cclog.py (UTC-время берёт само, "
    "НЕ вычислять вручную — Bangkok UTC+7 даёт «09:xx» вместо «02:xx UTC», класс 17.07): "
    "venv/bin/python3 cclog.py PLAN/DONE/BLOCKED «текст» [--pulse «строка»] ; "
    "статус честно: «технически готово» отдельно от «функционально подтверждено». "
    "ПОРЯДОК: cc_log DONE пишется ТОЛЬКО ПОСЛЕ успешного завершения операции (exit 0 финальной "
    "команды, включая git push). НЕ пиши DONE до git push — если push провалится или заблокируется, "
    "штаб будет видеть «готово» при несделанном состоянии (класс 23.07.2026).\n"
    "КАРТА ДЕЙСТВИЙ:\n"
    "- Зелёное/оранжевое (чтение, диагностика, правки кода, тесты, git commit, git push) — делай САМ; "
    "git push по циклу гейт→push→отчёт, БЕЗ маркера.\n"
    "- рестарт/старт своих сервисов (splinter/orchestrator-daemon/wa-webhook) — делай САМ, "
    "оранжевым циклом: гейт (venv/bin/python3 gate.py, только exit 0) → systemctl restart/start <сервис> "
    "→ systemctl is-active <сервис> active → в сводке «сделал, старт чистый». "
    "При failed — откат на прошлый рабочий коммит + restart + честный отчёт. "
    "Маркер op=restart_splinter НЕ выводи (он только аварийный фоллбэк). "
    "systemctl daemon-reload — зелёное (просто перечитать юниты, без рестарта). "
    "NEEDS_APPROVAL НЕ объявлять на рестарт/старт своих сервисов (splinter/orchestrator-daemon/wa-webhook).\n"
    "- САМОМОДИФИКАЦИЯ (правишь orchestrator_daemon.py — код демона, который исполняет ТЕБЯ): "
    "рестарт демона убьёт твой же claude-процесс (SIGTERM, отчёт пропадёт). Поэтому отчёт в "
    "cc_log+пульс и сводку пиши ДО рестарта, а рестарт — САМОЕ ПОСЛЕДНЕЕ действие и ТОЛЬКО "
    "ОТЛОЖЕННО: systemd-run --on-active=10s systemctl restart orchestrator-daemon. НИКОГДА не зови "
    "systemctl restart orchestrator-daemon напрямую из задачи. Если рестарт всё же погасит твой "
    "процесс раньше выхода (exit=143) — демон распознает плановый рестарт (фикс 07.07) и пометит "
    "задачу done с пометкой, НЕ failed; настоящие падения остаются failed.\n"
    "- ТЕСТЫ/ФИКСТУРЫ БЕЗ ПУШЕЙ В ЛИЧКУ: гейт (gate.py) сам ставит PRETOOL_NOPUSH=1 подпроцессам "
    "тестов. Если запускаешь тест/фикстуру/dry-run ВНЕ гейта (ручной прогон tests/*.py, скрипт со "
    "scratchpad/_test/_dryrun, проверка pretool_guard) — ставь env-префикс сам: "
    "PRETOOL_NOPUSH=1 venv/bin/python3 <скрипт>. Ноль тестовых карточек/пушей Филиппу в личку.\n"
    "- НАСТОЯЩЕЕ КРАСНОЕ — запись в рабочие таблицы (CRM/Лист1/Байки/Зарплаты), деньги/транзакции, "
    "clasp deploy/redeploy/push, sqlite3 CLI на memory.db, боевые записи ТО парка (масло/сервис в Лист1), "
    "подтверждённая запись в Лист1/CRM, удаление событий, любое удаление данных и файлов ВНЕ "
    "временных каталогов — НЕ выполняй и НЕ ищи обходных путей: выведи РОВНО "
    "одну строку «NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия · на что смотреть>» "
    "и заверши работу (исполнит человек).\n"
    "- УБОРКА СВОЕГО ЧЕРНОВИКА — ЗЕЛЁНОЕ, карточку НЕ объявлять: файл, который ты сам создал во "
    "временном каталоге (/tmp, /var/tmp, /dev/shm), убирай сам из python-кода, назвав путь "
    "ЛИТЕРАЛОМ (os.remove(\"/tmp/…\") / shutil.rmtree(\"/tmp/…\")) — владельцу тут решать нечего, "
    "файл твой и живёт до перезагрузки. Маска (/tmp/*), сам корень /tmp и любая цель ВНЕ "
    "временного каталога (файлы репо, БД, таблицы, события) — прежнее красное с карточкой.\n"
    "ВЕРИФИКАЦИЯ ЖИВЫМ ФАКТОМ (класс R11–R15, 19.07.2026): в выводе ОБЯЗАТЕЛЬНО включи блок «FACT:» "
    "с живым доказательством эффекта — для кода: «FACT: commit <хеш> в git log origin/main»; "
    "для рестарта сервиса: «FACT: PID=<новый PID>, is-active=active, баннер=<первая строка лога после старта>»; "
    "для записи в мозг (write_doc): «FACT: read back: <первые 200 символов перечитанного текста>»; "
    "read-only задача без изменений: «FACT: read-only». Задача без FACT: → карточка в 328 получит ⚠️ unverified.\n"
    "ФОРМАТ ОТВЕТА: первая строка — сводка результата (≤400 символов, уйдёт в Telegram-тему 328); "
    "подробности — в cc_log, НЕ в вывод. Задача целиком read-only → просто выполни и верни сводку.\n\n"
    "ЗАДАЧА:\n"
)

# === ДЕКОМПОЗЕР (ступень 2 часть C, KB_review PLAN 21:40) ===
# «декомпозируй: <крупное ТЗ>» → родитель (from=*-dec, без паттернов ниже) → планировщик claude -p
# (read-only) возвращает нумерованный список → шаги отдельными задачами «[шаг i/N родитель id] …»
# → исполнение по одному (FIFO + guard последовательности) → synthetic-сводка «[сводка родитель id]».
# Bridge-очередь НЕ меняется: родство — ТОЛЬКО по паттерну в task_text (решение плана C).
PLANNER_PREAMBLE = (
    "Ты — планировщик декомпозиции в headless-режиме в репо /root/turbobaby-manager-bot "
    "(CLAUDE.md действует). Твоя задача — РАЗБИТЬ крупное ТЗ на шаги, НЕ выполняя его: можно "
    "читать код/логи/доки (read-only разведка), НЕЛЬЗЯ править файлы, коммитить, деплоить, "
    "писать в таблицы.\n"
    "ФОРМАТ ОТВЕТА — СТРОГО и ТОЛЬКО нумерованный список шагов, каждый с новой строки "
    "«N. <шаг>», без заголовков, без кода, без текста до/после списка. Шагов 2–7. Каждый шаг — "
    "САМОДОСТАТОЧНОЕ дев-ТЗ (до 45 мин, ≤400 символов): исполнитель увидит ТОЛЬКО текст шага, "
    "поэтому впиши в каждый нужный контекст (файлы, функции, что сделать, как проверить). Шаги "
    "строго в порядке исполнения; правки кода раньше, деплой/рестарт/проверка — последними.\n"
    "КРАСНАЯ ЗОНА В ТЗ — НЕ ПОВОД ОТКАЗЫВАТЬСЯ ОТ ПЛАНА (урок задачи 166): ты ТОЛЬКО планируешь "
    "и сам ничего не исполняешь, поэтому упоминание clasp/деплоя/рабочих таблиц/денег/удаления "
    "в ТЗ НЕ требует подтверждения на этапе плана — НЕ выводи NEEDS_APPROVAL из-за содержимого "
    "ТЗ. Красное действие оформи ОТДЕЛЬНЫМ шагом (обычно последним): исполнитель ЭТОГО шага сам "
    "спросит «да» Филиппа кнопкой по штатной механике. Если ТЗ явно говорит, что прод-применение "
    "(деплой/рестарт) делается отдельно/хвостом — тем более просто строй план. ЕДИНСТВЕННОЕ "
    "исключение: ВСЁ ТЗ целиком = одно красное действие и разбивать не на что (например "
    "«задеплой прод») — тогда вместо списка выведи РОВНО одну строку "
    "«NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия>».\n"
    "ОРАНЖЕВОЕ ≠ красное: рестарт/старт своих сервисов (splinter/orchestrator-daemon/wa-webhook), "
    "git push, systemctl daemon-reload — исполнитель делает САМОСТОЯТЕЛЬНО (оранжевый цикл); "
    "в план выносить ОБЫЧНЫМ шагом, НЕ как NEEDS_APPROVAL-шаг.\n"
    "ВЕРИФИКАЦИЯ В ШАГАХ (класс R11–R15): для каждого шага, меняющего состояние системы "
    "(код/рестарт/запись в мозг), добавь в текст шага напоминание «в выводе включи FACT: с живым "
    "подтверждением (commit <хеш>/PID+is-active/read back)» — исполнитель обязан верифицировать эффект.\n\n"
    "КРУПНОЕ ТЗ:\n"
)
# Дописка планировщику для родителя ПК-театра (ДОБАВЛЯЕТСЯ ПОСЛЕ PLANNER_PREAMBLE — startswith
# в тест-моках/роутинге не ломается): шаги исполнит агент на ДРУГОЙ машине, не этот VPS.
PLANNER_PC_NOTE = (
    "ОСОБЕННОСТЬ ТЕАТРА ИСПОЛНЕНИЯ: шаги будет исполнять headless-агент на ДРУГОЙ машине "
    "(ПК, pc_orchestrator) — НЕ этот VPS. Пиши каждый шаг самодостаточно для ТОЙ машины: не "
    "ссылайся на пути/сервисы/файлы этого VPS, если само ТЗ явно не про них; весь контекст, "
    "нужный шагу, впиши в его текст.\n\n"
)
_STEP_RE = re.compile(r"^\[шаг (\d+)/(\d+) родитель (\d+)\]")
_SUM_RE = re.compile(r"^\[сводка родитель (\d+)\]")
_PLAN_LINE_RE = re.compile(r"^\s*(\d{1,2})[.)]\s+(\S.*)")
# guard последовательности: пока сиблинг висит в этих статусах — новые шаги родителя НЕ берём
# (needs_approval/approved = ждём Филиппа/доводку; in_progress = stale после падения демона —
# порядок шагов важнее живости, Филиппу и так уйдёт «⚠️ зависла» от devbot).
_DEC_WAIT_STATUSES = ("in_progress", "needs_approval", "approved")
# Фоллбэк-фразы (если claude описал блокировку гейта без маркера) — тоже эскалируем (эскалация
# безопасна: лишь спрашивает Филиппа, красное НЕ исполняется; op=other → решение владельца).
_NA_FALLBACK = ("требует подтверждения", "нужно подтверждение", "нужно «да»", "нужно \"да\"",
                "requires approval", "needs approval", "permission to use", "не разрешено гейтом")
_OP_RE = re.compile(r"op\s*=\s*([a-z_]+)", re.IGNORECASE)
# префикс дескриптора «op=xxx | » — срезается при конверте op=other в headless-ТЗ (остаётся карточка)
_OP_PREFIX_RE = re.compile(r"^\s*op\s*=\s*[a-z_]+\s*\|\s*", re.IGNORECASE)

# === КОРНЕВОЙ РАЗРЫВ ПЕТЕЛЬ КОНВЕРТОВ op=other (ст3, KB_MASTER §7/§12 — чинить навсегда) ===
# Петля: op=other → «да» Филиппа → конверт (headless-задача) → та упирается в то же красное →
# NEEDS_APPROVAL → «да» → новый конверт → … (56→57→58…). Рвём тремя слоями (план 06.07, RESULT 10:07):
#  СЛОЙ 1 (ядро): конверт-задача (текст с маркером ниже), снова эскалировавшая NEEDS_APPROVAL, =
#    доказательство, что headless красное НЕ пройдёт → НЕ ставим approvable needs_approval (это был бы
#    ре-конверт), а финализируем ТЕРМИНАЛЬНЫМ failed с ручной картой → рендер без approve-кнопки → петля
#    рвётся после РОВНО 1 перерождения.
#  СЛОЙ 2 (экономия перерождения): известное headless-НЕВОЗМОЖНОЕ красное (по ключевым словам) НЕ
#    конвертируем вовсе → сразу та же терминальная карта = ноль перерождений на известных петлях.
#  СЛОЙ 3 (страховка): fingerprint-дедуп в /inbox (devbot) — не трогаем.
_CONVERT_MARK = "[конверт одобренной заявки"
_CONVERT_RE = re.compile(r"^\s*\[конверт одобренной заявки\b")
# Слой 2: маркеры заведомо headless-невозможного красного (clasp/живая таблица/деньги/CLI-БД/удаление/
# календарь). Ловим в дескрипторе (what) И в тексте исходной задачи — до первого конверта.
# СУЖЕНО 25.07.2026: ловим ИМЕНА ОПЕРАЦИЙ и команды, а не ТЕМЫ. Прежний список бил по словам
# «деньг|касс|удал|байки|crm|календар|лист 1» — под них попадало и безобидное ЧТЕНИЕ («покажи
# отчёт по деньгам», «удалённый доступ»), и одобренная владельцем задача закрывалась терминально
# без единой попытки. Защита не ослаблена: несработавший слой 2 стоит РОВНО одно перерождение —
# конверт уйдёт в обычный контур, там его встретит pretool_guard, а слой 1 закроет петлю.
_HEADLESS_IMPOSSIBLE_RE = re.compile(
    r"\bclasp\b|\bredeploy\b|\bsqlite3\b|"
    r"\bset_fleet_(?:oil|service)\b|\bdelete_event\b|\bcreate_booking\b|"
    r"\bactivate_booking\b|\badd_transaction\b|\bvoid_last\b|\bclosing_upsert\b|"
    r"confirmed\s*=\s*true|\bDOWRITE\b|"
    r"\bgspread\b|sheets\.googleapis\.com|script\.google\.com",
    re.IGNORECASE,
)
# УДАЛЕНИЕ ВЫНЕСЕНО ИЗ СПИСКА ВЫШЕ И СУДИТСЯ ПО ЦЕЛИ (30.07.2026) — тот же класс, что сужение
# 25.07 («имена операций, а не темы») и «данные ≠ команда» в гарде: краснеть должно ДЕЙСТВИЕ, а не
# наличие глагола в тексте. Было: os.remove|os.unlink|shutil.rmtree|rm -rf где угодно в тексте =
# заведомо headless-невозможное красное. Под это попадала УБОРКА СВОЕГО ЧЕРНОВИКА во временном
# каталоге — файла, который задача сама и создала: владельцу решать нечего, а стоило это карточки,
# «да» и терминальной карты «сделай руками» (в 328 — предложение владельцу пойти удалить файл в /tmp).
# Теперь красным НЕ считается ровно один случай: цель названа ЛИТЕРАЛОМ, лежит внутри временного
# каталога (/tmp, /var/tmp, /dev/shm) и является КОНКРЕТНЫМ путём под его корнем.
# FAIL-SAFE во все стороны (сомнение → прежнее красное): цель не извлеклась (переменная,
# os.path.join), маска (/tmp/*), сам корень /tmp, «..», путь вне временных каталогов.
_DELETE_VERB_RE = re.compile(r"os\.remove|os\.unlink|shutil\.rmtree|\brm\s+-rf\b", re.IGNORECASE)
# Цель обязана идти СРАЗУ за глаголом (пробелы/открывающая скобка допустимы): иначе «os.remove(p)
# # см. /tmp/x» подцепил бы путь из комментария и позеленел бы на пустом месте.
_DELETE_TARGET_RE = re.compile(r"^[\s(]*(?:[\"']([^\"']{1,200})[\"']|(/[^\s,)\]\"']{1,200}))")
_TMP_ROOTS = ("/tmp/", "/var/tmp/", "/dev/shm/")


def _is_tmp_path(p):
    """Цель — КОНКРЕТНЫЙ файл/каталог внутри временного каталога? (маски и сам корень — нет)."""
    p = (p or "").strip().strip("'\"").strip()
    if not p or "*" in p or "?" in p:
        return False
    for root in _TMP_ROOTS:
        if p.startswith(root):
            tail = p[len(root):].strip("/")
            return bool(tail) and ".." not in tail.split("/")
    return False


def _delete_targets(blob):
    """Цели, названные РЯДОМ с глаголом удаления → список (пустая строка = не извлеклась)."""
    out = []
    for m in _DELETE_VERB_RE.finditer(blob or ""):
        t = _DELETE_TARGET_RE.match(blob[m.end():m.end() + 240])
        out.append(((t.group(1) or t.group(2)) if t else "") or "")
    return out


def _delete_is_red(blob):
    """True → в тексте есть удаление, которое НЕ является уборкой своего временного файла.
    Глагола нет → False. Хоть одна цель вне временного каталога (или не извлечённая) → True."""
    targets = _delete_targets(blob)
    if not targets:
        return False
    return any(not _is_tmp_path(t) for t in targets)


# === САМОПОЧИНКА ШАГА (мета-дирижёр кусок 1, KB_MASTER §4, заведено 06.07.2026) ===
# Провал шага декомпозера (исполнительский fail, НЕ красный NEEDS_APPROVAL) при STEP_SELFHEAL=1
# в .env → вместо мгновенного halt-on-fail зовём ДУМАТЕЛЯ: claude -p через тот же кондуктор
# ORCH_MODEL/ORCH_MODEL_FALLBACK (0bc9187), чистый генератор (--max-turns 1, без исполнения),
# строгий JSON {"verdict","fixed_step","reason"}. verdict=retry → шаг перерождается НОВОЙ задачей
# с детерминированным маркером «[самопочинка шага N, попытка 1]» (паттерн конвертов fa90193);
# перерождённый шаг, упавший ПОВТОРНО, → ТЕРМИНАЛЬНЫЙ halt (ровно 1 попытка, петля невозможна).
# FAIL-SAFE: думатель упал / таймаут / JSON не распарсился / enqueue не встал → прежний
# halt-on-fail байт-в-байт (не хуже текущего). Красное НЕ ослабляется: думатель ничего не
# исполняет, перерождённый шаг идёт обычным путём (NEEDS_APPROVAL → кнопка как раньше).
# STEP_SELFHEAL=0/нет → ветка не зовётся вовсе (мгновенный откат конфигом + рестарт демона).
# РАСШИРЕНИЕ ст4 (07.07.2026, последний кусок): ТОТ ЖЕ механизм и ТОТ ЖЕ флаг на одиночные
# «тз:»/«задача:» — провал → думатель (контекст: текст задачи дословно + суть провала, JSON с
# fixed_task) → 1 перерождение «[самопочинка задачи N, попытка 1]» → повторный провал =
# терминальный failed с диагнозом. Конверты и плановый рестарт самомода (done) — НЕ трогаются.
STEP_SELFHEAL_TIMEOUT = 180   # думатель — чистый генератор без tools, ответ короткий
_HEAL_RE = re.compile(r"\[самопочинка шага (\d+), попытка (\d+)\]")
# РАСШИРЕНИЕ ст4 (07.07.2026, последний кусок мета-дирижёра): ТОТ ЖЕ механизм на одиночные
# «тз:»/«задача:» под ТЕМ ЖЕ флагом STEP_SELFHEAL. Маркер перерождения одиночной задачи стоит
# ПЕРВЫМ в тексте → якорь ^ (у шага маркер идёт после [шаг i/N], там search). N = id исходной
# задачи. Анкер ещё и страхует от ложного срабатывания на ТЗ, где маркер лишь упомянут в тексте.
_HEAL_TASK_RE = re.compile(r"^\s*\[самопочинка задачи (\d+), попытка (\d+)\]")
THINKER_PREAMBLE = (
    "Ты — думательный слой самопочинки оркестратора TurboBaby (мета-дирижёр). Шаг декомпозиции "
    "упал при исполнении. Твоя задача — ТОЛЬКО диагноз и вердикт; ты НИЧЕГО не исполняешь, "
    "инструментов у тебя нет, файлы не читаешь — решай строго по данным ниже.\n"
    "Ответь СТРОГО ОДНИМ JSON-объектом, без текста до/после, без markdown-обёртки:\n"
    '{"verdict":"retry"|"halt","fixed_step":"<новая формулировка шага>","reason":"<1 строка диагноза>"}\n'
    "verdict=retry — ТОЛЬКО если провал починим переформулировкой шага (неверный путь/имя файла, "
    "недостающий контекст, кривая команда) и правка очевидна; fixed_step тогда — САМОДОСТАТОЧНОЕ "
    "дев-ТЗ ≤400 символов (исполнитель увидит ТОЛЬКО его, впиши нужный контекст). Во всех прочих "
    "случаях (причина неясна, нужен человек, красная зона, объём не влезает в таймаут) — "
    "verdict=halt и fixed_step пустой. Система даёт РОВНО ОДНУ попытку починки — не предлагай "
    "многошаговых планов.\n"
    "(Контекст системы R11–R15: исполнительские задачи обязаны включать блок FACT: в финальный вывод. "
    "В твоём JSON-ответе FACT: не нужен — ты думаешь, не исполняешь.)\n\n"
)
# Преамбула думателя ОДИНОЧНОЙ задачи (расширение ст4): та же схема/строгость, но контекст без
# родителя/плана (их у одиночной нет) и ключ fixed_task вместо fixed_step.
TASK_THINKER_PREAMBLE = (
    "Ты — думательный слой самопочинки оркестратора TurboBaby (мета-дирижёр). Одиночная "
    "headless-задача упала при исполнении. Твоя задача — ТОЛЬКО диагноз и вердикт; ты НИЧЕГО "
    "не исполняешь, инструментов у тебя нет, файлы не читаешь — решай строго по данным ниже.\n"
    "Ответь СТРОГО ОДНИМ JSON-объектом, без текста до/после, без markdown-обёртки:\n"
    '{"verdict":"retry"|"halt","fixed_task":"<новая формулировка задачи>","reason":"<1 строка диагноза>"}\n'
    "verdict=retry — ТОЛЬКО если провал починим переформулировкой задачи (неверный путь/имя файла, "
    "недостающий контекст, кривая команда) и правка очевидна; fixed_task тогда — САМОДОСТАТОЧНОЕ "
    "дев-ТЗ ≤400 символов (исполнитель увидит ТОЛЬКО его, впиши нужный контекст). Во всех прочих "
    "случаях (причина неясна, нужен человек, красная зона, объём не влезает в таймаут) — "
    "verdict=halt и fixed_task пустой. Система даёт РОВНО ОДНУ попытку починки — не предлагай "
    "многошаговых планов.\n"
    "(Контекст системы R11–R15: исполнительские задачи обязаны включать блок FACT: в финальный вывод. "
    "В твоём JSON-ответе FACT: не нужен — ты думаешь, не исполняешь.)\n\n"
)


def _selfheal_on():
    """Флаг STEP_SELFHEAL=1 в .env (демон load_dotenv'ит на старте). 0/нет → прежнее поведение."""
    return (os.environ.get("STEP_SELFHEAL") or "").strip() == "1"


def _is_convert(text):
    """True → задача является конвертом одобренной op=other (родилась из «да» Филиппа). Слой 1."""
    return bool(_CONVERT_RE.match(str(text or "")))


def _is_headless_impossible(*texts):
    """True → в тексте(ах) есть маркер заведомо headless-невозможного красного действия. Слой 2.
    Удаление проверяется отдельно и ПО ЦЕЛИ (_delete_is_red): уборка своего черновика в /tmp
    красным не считается, всё прочее удаление — как было."""
    blob = " ".join(str(t or "") for t in texts)
    if _HEADLESS_IMPOSSIBLE_RE.search(blob):
        return True
    return _delete_is_red(blob)


def _manual_card(what, orig_text=""):
    """Терминальная карточка «сделай РУКАМИ» (это НЕ сбой, а нормальный ручной исход). Кладётся в
    complete_task(failed) → рендерится БЕЗ approve-кнопки → ре-approve/ре-конверт невозможен, петля
    рвётся. Тело: явно «требуется ручное действие», что именно сделать (из карточки) и что проверить."""
    card = _OP_PREFIX_RE.sub("", what or "").strip() or "(карточка пустая — см. вывод задачи)"
    lines = [
        "✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ (это не сбой, а нормальный ручной исход)",
        "Headless-контур доказано не может выполнить это красное действие (рабочие таблицы/деньги/"
        "clasp/sqlite3/удаление). Кнопки «да» здесь НЕТ намеренно — повторный approve лишь плодит "
        "петлю конвертов. Требуется решение владельца — переставь задачу в 328 после его ответа. "
        "Действие из карточки:",
        card,
        "После — проверь результат в целевой таблице/логах; при необходимости повтори исходную "
        "задачу в 328 обычным префиксом.",
    ]
    if orig_text:
        lines.append(f"Исходная задача (контекст): {str(orig_text).strip()[:300]}")
    return cap_result("\n".join(lines))


def _forged_op_card(what):
    """Терминальная карта на ЗАЯВКУ исполнителя с ИСПОЛНИМЫМ классом операции (кнопки нет
    намеренно). Это не «сбой»: работа встала на красном — но карточку по одним словам мы не
    рождаем, потому что подтверждать в ней нечего. Объекта нет: гард команды не видел, а класс,
    который демон исполнил бы после «да», брался бы из этой же строки. Ровно этот класс ошибок
    (ПК: «коротким да открывались 11 видов из 19») закрыт замком происхождения 31.07.2026."""
    op = parse_op(what)
    card = _OP_PREFIX_RE.sub("", _scrub_origin(what)).strip() or "(текст заявки пуст — см. вывод задачи)"
    return cap_result("\n".join([
        "✋ ЗАЯВКА ИСПОЛНИТЕЛЯ, А НЕ КАРТОЧКА ГАРДА (кнопки «да» здесь нет намеренно)",
        f"Задача сама напечатала строку с исполнимым классом операции (op={op}), но гард НИ ОДНОЙ "
        f"команды не перехватывал. Подтверждать нечего: объекта операции никто не видел, а после "
        f"«да» демон брал бы класс исполняемой команды из этой же строки.",
        f"Что было заявлено: {card}",
        "Что делать: git push и рестарт своих сервисов исполнитель делает САМ оранжевым циклом "
        "(гейт → действие → отчёт) — маркер для них не нужен и преамбулой запрещён. Если действие "
        "всё же требуется — поставь его отдельной задачей: когда команду РЕАЛЬНО попробуют, её "
        "перехватит гард и пришлёт карточку с кнопкой и объектом.",
    ]))


# ═══════════════ ДЕЖУРНЫЙ ПО КАРТОЧКАМ, ФАЗА 1 (04.08.2026) ═══════════════
# Решение живёт в card_duty.py — ЧИСТОЙ функции без ввода-вывода (там же вся доктрина, граница и
# честный предел). Здесь — только руки: собрать факты из очереди, положить вердикт в терминальный
# путь без кнопки и сказать владельцу заметкой. Разделение не косметическое: у модуля решения нет
# инструментов ни выдать себе прав, ни отправить что-либо от своего имени, и это стережёт
# инвариант CARD_DUTY_PURE в гейте, а не докстринг.
#
# ОТКАТ: CARD_DUTY=0 в .env (или убрать строку) + рестарт демона → ветка мертва целиком, карточки
# уходят владельцу байт-в-байт как раньше. Дефолт — ВЫКЛЮЧЕНО (как у CURATOR): ошибка дежурного
# гасила бы владельцу видимость красного, а это ровно то направление, где цена ошибки высшая.


def _card_duty_on():
    """Флаг CARD_DUTY=1 в .env (парсер как у CURATOR/STEP_SELFHEAL). 0/нет/мусор → выключено."""
    return (os.environ.get("CARD_DUTY") or "").strip() == "1"


def _duty_fingerprint(what):
    """Отпечаток карточки = (op-код, текст без префикса «op=… |» и без штампа происхождения).
    Зеркало devbot._inbox_fingerprint, плюс снятие штампа: он несёт КОНСТАНТУ, но у guard_weak
    текст штампа другой — без снятия одинаковые по сути карточки не схлопнулись бы."""
    body = _ORIGIN_LINE_RE.sub("", _OP_PREFIX_RE.sub("", str(what or "")))
    return parse_op(what), " ".join(body.split())


def _duty_queue_twins(tid, what):
    """(dup_id, answered_id) — карточка с ТЕМ ЖЕ отпечатком, уже открытая у владельца либо уже
    одобренная им. Читаем очередь read-only; свою задачу пропускаем.
    FAIL-SAFE: мост не ответил / любое исключение → пустые id, то есть эти два условия просто не
    сработают (дежурный станет строже, не мягче)."""
    fp = _duty_fingerprint(what)
    dup_id = answered_id = ""
    for status, slot in (("needs_approval", "dup"), ("approved", "ans")):
        try:
            r = bc.get_pending(status)
        except Exception:
            continue
        if not r.get("ok"):
            continue
        for it in r.get("items", []):
            if str(it.get("id")) == str(tid):
                continue
            if _duty_fingerprint(it.get("result")) != fp:
                continue
            if slot == "dup" and not dup_id:
                dup_id = str(it.get("id"))
            elif slot == "ans" and not answered_id:
                answered_id = str(it.get("id"))
    return dup_id, answered_id


def _duty_note(tid, rule, proof):
    """Заметка в ленту 829: владелец видит закрытие ПОСТФАКТУМ и ничего не отвечает.
    FAIL-SAFE: адреса нет / сеть / любой сбой → False. Отсутствие заметки НЕ отменяет закрытия,
    но факт молчания попадает в журнал демона — след не теряется ни при каком исходе."""
    try:
        import notify
        return bool(notify.send_feed(card_duty.note("VPS", tid, rule, proof)))
    except Exception as e:
        log.warning("дежурный: заметка в ленту не ушла (%s)", e)
        return False


def _maybe_card_duty(tid, what):
    """CARD_DUTY=1 → вердикт дежурного по карточке. True = карточка снята и задача финализирована
    (владельцу не пойдёт), False = прежний путь (set_needs_approval), байт-в-байт.

    FAIL-SAFE НА КАЖДОМ ШАГЕ: флаг выключен, сбой сбора фактов, сбой самого решения, вердикт
    HOLD → False. Закрытие требует положительного доказательства; всё остальное — к владельцу."""
    if not _card_duty_on():
        return False
    try:
        dup_id, answered_id = _duty_queue_twins(tid, what)
        action, rule, proof = card_duty.decide(
            what, _card_origin(what), op=parse_op(what),
            dup_id=dup_id, answered_id=answered_id)
    except Exception as e:
        log.warning("дежурный: решение не собралось id=%s (%s) → карточка идёт владельцу", tid, e)
        return False
    if action != card_duty.CLOSE:
        log.info("дежурный: карточка id=%s остаётся владельцу (%s)", tid, proof)
        return False
    # СЛЕД РАНЬШЕ ЗАКРЫТИЯ: заметка уходит ДО complete_task — если мост упадёт на закрытии,
    # владелец уже знает о снятии, а карточка останется висеть (видимый, а не молчаливый сбой).
    sent = _duty_note(tid, rule, proof)
    cm = bc.complete_task(tid, "failed", cap_result(card_duty.close_result(what, rule, proof)))
    log.info("DUTY-CLOSE id=%s условие=%s (%s) заметка=%s bridge_ok=%s",
             tid, rule, proof, sent, cm.get("ok"))
    return True


def parse_op(what):
    """Извлечь op-код из сохранённого what (дескриптор needs_approval). 'other' если не распознан/не из перечня."""
    m = _OP_RE.search(what or "")
    if not m:
        return "other"
    op = m.group(1).lower()
    return op if op in AUTO_OPS else "other"


# Заметка слоя ФРАЗЫ (замок происхождения, 31.07.2026). Слова о красной зоне в отчёте — это не
# перехваченная команда и не самодекларация: объекта нет, подтверждать нечего. Прежняя ветка
# делала из таких слов approvable-карточку И ПОДМЕНЯЛА настоящий результат задачи телом карточки —
# успешный read-only разбор про подтверждения превращался в «жду да» ни на чём. Теперь исход
# задачи остаётся честным, а сигнал владельцу идёт заметкой. Формулировка НАМЕРЕННО не содержит
# фраз из _NA_FALLBACK: заметка не должна сама себя детектить на следующем круге.
NA_PHRASE_NOTE = (
    "\n\n⚠️ В отчёте есть слова про красную зону и одобрение владельца, но гард ни одной команды "
    "не перехватывал, а маркера красной зоны задача не выводила — по одним словам карточку "
    "владельцу не рождаю (объекта операции нет, подтверждать нечего). Если действие всё же нужно "
    "— поставь его отдельной задачей: когда команду РЕАЛЬНО попробуют, её перехватит гард и "
    "пришлёт карточку с кнопкой и объектом.")


# Заметка о ЦИТАТЕ маркера (класс 05.08.2026, см. _na_declaration). Отчёт остаётся целым, а
# владелец всё равно видит, что в тексте была фраза про красное. Формулировка НАМЕРЕННО не
# содержит ни литерала маркера, ни фраз из _NA_FALLBACK: заметка не должна детектить сама себя
# на следующем круге (тот же приём, что у NA_PHRASE_NOTE).
NA_QUOTE_NOTE = (
    "\n\n⚠️ В отчёте маркер красной зоны ПРОЦИТИРОВАН (ячейка таблицы, обратные кавычки, ограда "
    "кода), а не заявлен: заявлением считается только маркер в начале строки — её хвост демон и "
    "делает карточкой. Отчёт оставлен целиком, карточка владельцу не рождена. Если красное "
    "действие правда нужно — поставь его отдельной задачей: когда команду РЕАЛЬНО попробуют, её "
    "перехватит гард и пришлёт карточку с объектом; а заявление печатай отдельной строкой, с её "
    "начала.")


def _with_phrase_note(body, note):
    """Приклеить заметку слоя фразы так, чтобы она НЕ была срезана капом: сначала режем тело под
    длину заметки, потом клеим. Заметки нет → прежний cap_result(body) байт-в-байт."""
    if not note:
        return cap_result(body)
    return cap_result(cap_result(body, max(200, RESULT_MAX - len(note))) + note)


# === ПОЗИЦИЯ ЗАЯВЛЕНИЯ (класс «цитата маркера убивает отчёт», 05.08.2026) ===
# Зеркало ПРАВИЛА ИСПОЛНЯЮЩЕЙ ПОЗИЦИИ (5ca761d, pretool_guard): решает не СОВПАДЕНИЕ СЛОВА в
# свободном тексте, а МЕСТО, в котором слово стоит. Здесь разборщик — сам _detect_na: он берёт
# ХВОСТ СТРОКИ после маркера и делает из него дескриптор карточки, ПОДМЕНЯЯ им весь отчёт.
# Значит заявляющая позиция ровно одна — НАЧАЛО СТРОКИ: только там хвост строки И ЕСТЬ заявление.
# ЧТО ЛОМАЛОСЬ (боевые случаи из orchestrator_daemon.log, 14 суток): id=246 напечатала таблицу
# правил с ячейкой «маркер `NEEDS_APPROVAL:`» — весь 25-минутный отчёт заменили ТРИ символа хвоста
# ячейки («` |»); id=130 писала отчёт О САМОМ ДЕТЕКТЕ и была съедена собственным описанием;
# id=29 упомянула шаблон карточки в прозе. У 29 хвост начинался с «op=» — то есть проверкой ФОРМЫ
# ХВОСТА класс не закрывается вовсе, решает именно позиция.
# ГРАНИЦА НАЗВАНА: перед маркером допускается лишь ДЕКОРАЦИЯ форматирования (пробелы, маркер
# списка, звёздочки/подчёрки выделения, решётки заголовка) — она ничего не цитирует. Обратная
# кавычка, кавычки, «|» ячейки, «>» цитаты, любая буква/цифра означают, что маркер стоит ВНУТРИ
# текста. Строки внутри ограды ``` — тоже цитата: это показанный текст, а не строка отчёта.
# НАПРАВЛЕНИЕ СОМНЕНИЯ (обратное гарду — и намеренно): гард решает, ИСПОЛНИТСЯ ли команда, и
# сомневается в сторону запрета; здесь не исполняется НИЧЕГО ни при каком исходе — решается лишь
# судьба ОТЧЁТА. Поэтому непризнанное заявление не пропадает молча: отчёт остаётся целым и несёт
# видимую ⚠️-заметку (NA_QUOTE_NOTE), то есть худший исход ошибки — «карточки нет, но всё видно»,
# а не «отчёта нет». Настоящее заявление в контрактной позиции — байт-в-байт как было.
_NA_DECOR = " \t -–—•*+_#"          # декорация форматирования: цитирующим символом не является
_NA_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")


def _na_declaration(line):
    """Хвост маркера, если маркер стоит в ЗАЯВЛЯЮЩЕЙ позиции (начало строки); иначе None."""
    i = line.find(NA_MARKER)
    if i < 0:
        return None
    if line[:i].strip(_NA_DECOR):        # перед маркером есть ТЕКСТ → это цитата, а не заявление
        return None
    return line[i + len(NA_MARKER):].strip()


def _detect_na(text):
    """(what, kind): kind = 'marker' — модель вывела NA_MARKER В ЗАЯВЛЯЮЩЕЙ ПОЗИЦИИ (самодекларация
    по контракту преамбулы); 'quote' — маркер лишь процитирован в тексте отчёта (таблица, кавычки,
    ограда кода) — заявлением НЕ является; 'phrase' — только слова о блокировке, маркера нет;
    None — чисто. Заявление сильнее цитаты: в отчёте с обоими побеждает заявление."""
    t = text or ""
    quoted, fenced = False, False
    for line in t.splitlines():
        if _NA_FENCE_RE.match(line):
            fenced = not fenced
        if NA_MARKER not in line:
            continue
        what = None if fenced else _na_declaration(line)
        if what is not None:
            return (what or "op=other | (claude не уточнил красное действие — см. вывод задачи)"), "marker"
        quoted = True
    if quoted:
        return None, "quote"
    low = t.lower()
    if any(p in low for p in _NA_FALLBACK):
        return None, "phrase"
    return None, None


def _detect_needs_approval(text):
    """Вернуть дескриптор красного действия (строка с op=…), если claude самодекларировал маркер или
    явно описал блок гейта. Иначе None. Эскалация предпочтительнее тихого failed (так требует задача).
    Дескриптор сохраняется в очередь как what — по нему демон при approved исполняет хардкод-команду op.

    ПУТЬ ИСПОЛНИТЕЛЯ сюда больше НЕ ходит (см. _run_task_impl: там _detect_na + замок
    происхождения). Функция осталась ради ПЛАНИРОВЩИКА декомпозиции (чисто-красный родитель —
    фейл-сейф урока 166) и юнит-тестов, стерегущих формат детекта: их семантика прежняя."""
    what, kind = _detect_na(text)
    if kind == "marker":
        return what
    if kind in ("phrase", "quote"):
        # 'quote' сюда попадает ТОЛЬКО из фейл-сейфа планировщика (плана нет вовсе) — там отказ
        # был и остаётся честным failed, и вывод целиком уходит в тело отказа, а не режется в
        # хвост процитированной строки. Слабее прежнего этот путь не стал.
        return "op=other | (гейт заблокировал красное; claude не дал маркер — вывод:)\n" + (text or "")[:1400]
    return None


def _heartbeat_loop(task_id, stop_event):
    """Фон-поток: пока задача исполняется, каждые HEARTBEAT_SEC бьёт updated в Bridge
    (доказывает, что демон жив → report_results на стороне Splinter не поднимет «завис»).
    Ошибки heartbeat ГЛУШИМ — heartbeat не должен валить исполнение задачи."""
    while not stop_event.wait(HEARTBEAT_SEC):
        try:
            bc.task_heartbeat(task_id)
        except Exception as e:
            log.warning("id=%s heartbeat упал (глушу): %s", task_id, e)


def _task_timeout(task):
    """Таймаут по метке from очереди: дев-ТЗ («тз:», from=*-dev), декомпозиция (from=*-dec,
    планирование-разведка и шаги — те же дев-ТЗ) и followup-задачи куратора (from=Filipp-curator —
    по промпту куратора это дев-ТЗ: код/тесты/доки) → 45 мин, остальное → 10 мин."""
    frm = str(task.get("from") or "")
    if frm == CURATOR_FROM:
        return TASK_TIMEOUT_DEV
    return TASK_TIMEOUT_DEV if frm.endswith((DEV_FROM_SUFFIX, DEC_FROM_SUFFIX)) else TASK_TIMEOUT


def _run_task_impl(task_id, task_text, task_timeout=TASK_TIMEOUT, preamble=None, _mctx=None):
    """Исполнить задачу через claude -p (headless). Возврат: (status, result_text).
    status ∈ done|failed|needs_approval|requeue (needs_approval — красная зона, самодекларация
    claude через маркер; requeue — гибель от ЧУЖОГО планового рестарта, вернуть задачу в new).
    preamble: None → боевая APPROVAL_PREAMBLE; планировщик декомпозиции передаёт PLANNER_PREAMBLE."""
    log.info("ИСПОЛНЕНИЕ id=%s через claude -p (timeout=%ss)", task_id, task_timeout)
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    # Фикс утечки баланса: демон load_dotenv'ит .env (ради BRIDGE) → ANTHROPIC_API_KEY коллатерально
    # попадает в os.environ. Снимаем его (и OPENAI) из child_env, чтобы claude -p шёл по ~/.claude (Max),
    # а НЕ по платному API. Splinter не затронут (он ключ берёт из своего процесса, не через claude -p).
    child_env.pop("ANTHROPIC_API_KEY", None)
    child_env.pop("OPENAI_API_KEY", None)
    # Фикс утечки тест-флагов (17.07.2026): ORCH_TEST_MODE=1/PRETOOL_NOPUSH=1 могут попасть в
    # os.environ демона если он был запущен из тест-окружения (gate.py не изолирует parent env).
    # В боевом child_env тест-флаги НИКОГДА не нужны: ban-сеть и mute-пуши ломают нормальные задачи.
    # 01.08.2026 — СНИМАЕМ ВСЕ ЧЕТЫРЕ ИМЕНИ, а не два. Гард считает тест-прогоном любое из
    # pretool_guard._TEST_RUN_ENVS, и с 01.08 это же множество глушит ОБА канала владельца
    # (прямой пуш + маркер демону). Пока чистились только два имени, протёкший в окружение демона
    # PRETOOL_TEST_RUN или PYTEST_CURRENT_TEST молча увёл бы маркер ЖИВОЙ задачи в тест-каталог, и
    # владелец не увидел бы красной карточки вовсе — тихая потеря вместо лишнего вопроса.
    # Список держать РАВНЫМ pretool_guard._TEST_RUN_ENVS: разъедутся — вернётся ровно этот класс.
    for _test_flag in ("ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PRETOOL_TEST_RUN", "PYTEST_CURRENT_TEST"):
        child_env.pop(_test_flag, None)
    # Гейт-алерты только на финальном прогоне (хвост §7, 12.07.2026): внутри headless-задачи
    # промежуточные красные прогоны gate.py — штатный red-fix-green цикл, НЕ шум владельцу.
    # Флаг велит gate.py молчать в Telegram на НЕ-финальных прогонах; финальный pre-push зовёт
    # gate.py --final и алертит как раньше. Без этого env (интерактив/cron/девбот) — всё как было.
    child_env["GATE_ALERT_FINAL_ONLY"] = "1"
    # Ускорение цепей ч.2 (13.07.2026): промежуточный шаг декомпозиции (i < N) →
    # gate.py запускает только тесты затронутых модулей (селективный гейт).
    # Расширение (15.07.2026, GATE_SINGLE_SELECTIVE=1): одиночные «тз:»/«задача:» — тоже.
    # Последний шаг (i == N), планировщик — всегда полный. --final (pre-push) всегда полный.
    # Fail-safe gate.py: не смог определить затронутые → полный сьют автоматически.
    # Сброс унаследованного значения: parent-процесс (gate.py при селективном прогоне) может
    # передавать GATE_STEP_SELECTIVE=1 через env → child-задача наследует его в child_env.
    # Сбрасываем до нашего решения — флаг управляем ТОЛЬКО отсюда, не наследованием.
    child_env.pop("GATE_STEP_SELECTIVE", None)
    if preamble is None:
        _sm = _STEP_RE.match(str(task_text or ""))
        if _sm and int(_sm.group(1)) < int(_sm.group(2)):
            child_env["GATE_STEP_SELECTIVE"] = "1"
        elif not _sm and (os.environ.get("GATE_SINGLE_SELECTIVE") or "").strip() == "1":
            # Одиночные «тз:»/«задача:» + GATE_SINGLE_SELECTIVE=1 → тоже селективный гейт.
            child_env["GATE_STEP_SELECTIVE"] = "1"
    prompt = (preamble if preamble is not None else APPROVAL_PREAMBLE) + task_text
    # Heartbeat: фон-поток бьёт updated, пока claude -p блокирующе исполняется. Останавливаем в finally.
    _hb_stop = threading.Event()
    _hb = threading.Thread(target=_heartbeat_loop, args=(task_id, _hb_stop), daemon=True)
    _hb.start()
    # Кондуктор: --model основная + --fallback-model прежняя (Opus 4.8 1M). При
    # overload/недоступности/лимите/неверном имени primary CLI сам переключается на fallback внутри
    # ОДНОГО вызова (без двойного исполнения). --output-format json → из ответа достаём и текст
    # (result), и КАКАЯ модель реально отработала (ключи modelUsage) для явной строки в лог.
    # prompt — ПОСЛЕДНИМ аргументом (позиционный; тест-моки читают args[-1]).
    # УСКОРЕНИЕ ЦЕПЕЙ ч.1: планировщик декомпозиции = ДУМАНЬЕ → ORCH_MODEL (предикат тот же,
    # что у NA-гейта ниже); исполнитель задач/шагов → EXECUTOR_MODEL (дефолт = ORCH_MODEL).
    is_planner = preamble is not None and preamble.startswith(PLANNER_PREAMBLE)
    model = ORCH_MODEL if is_planner else EXECUTOR_MODEL
    cmd = [CLAUDE_BIN, "-p",
           "--model", model,
           "--fallback-model", ORCH_MODEL_FALLBACK,
           "--effort", EXECUTOR_EFFORT,
           "--output-format", "json",
           "--settings", HEADLESS_SETTINGS,  # строгий headless-слой (роль-развод: clasp → ask)
           prompt]                          # список аргументов, БЕЗ shell → нет инъекции через task_text
    # Guard-маркер: очистить старый маркер, задать CC_TASK_ID для pretool_guard.
    # CC_GUARD_TOKEN (замок происхождения 31.07.2026) — одноразовый токен ЭТОГО прогона: хук
    # кладёт его в маркер, демон сверяет. Маркер без токена/с чужим — карточку всё равно даёт
    # (реальный блок терять нельзя), но помечается как несверенный и прав на класс не несёт.
    task_id_str = str(task_id)
    child_env["CC_TASK_ID"] = task_id_str
    _guard_token = _guard_token_new()
    child_env["CC_GUARD_TOKEN"] = _guard_token
    _guard_marker_clear(task_id_str)
    _guard_kill = threading.Event()
    _guard_data = []

    # старт claude задачи по CLOCK_MONOTONIC — опора 5-го признака (свой/чужой плановый рестарт)
    t0_mono = time.monotonic()
    try:
        proc = _POPEN(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True, env=child_env)
    except Exception as e:
        log.error("id=%s ошибка запуска claude -p: %s", task_id, e)
        _hb_stop.set()
        _hb.join(timeout=5)
        _set_fail_code(_mctx, "exec_error")
        return "failed", f"ошибка запуска claude -p: {e}"

    # Guard-монитор: фон-поток проверяет маркер каждые 2с, при обнаружении — terminate
    _gm = threading.Thread(target=_guard_monitor_loop,
                            args=(task_id_str, proc, _hb_stop, _guard_kill, _guard_data),
                            daemon=True)
    _gm.start()

    _timed_out = False
    try:
        _stdout, _stderr = proc.communicate(timeout=task_timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            _stdout, _stderr = proc.communicate()
        except Exception:
            _stdout, _stderr = "", ""
        _timed_out = True
    finally:
        _hb_stop.set()
        _hb.join(timeout=5)
        _gm.join(timeout=3)

    if _timed_out:
        log.warning("id=%s ТАЙМАУТ %ss — claude -p убит, честный failed", task_id, task_timeout)
        _set_fail_code(_mctx, "run_timeout")
        return "failed", (f"{TIMEOUT_MARK} таймаут задачи {task_timeout}s — claude -p убит, задача "
                          f"не завершилась (лимит TASK_TIMEOUT из .env); думатель таймауты не чинит — "
                          f"упрости/раздели задачу и поставь заново")

    # Пост-проверка маркера (монитор мог не успеть до выхода claude)
    if not _guard_kill.is_set():
        _d = _guard_marker_read(task_id_str)
        if _d is not None:
            _guard_data.append(_d)
            _guard_kill.set()

    if _guard_kill.is_set():
        _gd = _guard_data[0] if _guard_data else None
        _gd_ok = bool(_gd) and str((_gd or {}).get("token") or "") == _guard_token
        what = _guard_what(task_id_str, _gd, verified=_gd_ok)
        if not _gd_ok:
            log.warning("id=%s маркер гарда БЕЗ сверки токена (протухший/не от хука) — карточку "
                        "показываю, класс операции по ней не признаётся", task_id)
        if _guard_is_hard(_gd):                        # живая сущность → кнопки «да» не предлагаем
            log.warning("id=%s guard-block ЖЁСТКИЙ (живая сущность) → failed без approve: %.100s",
                        task_id, what)
            return "failed", cap_result("✋ ЖЁСТКИЙ БЛОК: запись в живые таблицы по ЖИВОЙ сущности. "
                                        "Кнопки «да» здесь нет намеренно — по доктрине такое "
                                        "одобряется только для ТЕСТ-сущностей write-смока, а живую "
                                        "правит владелец сам.\n" + what)
        log.info("id=%s guard-block → needs_approval: %.100s", task_id, what)
        return "needs_approval", what[:RESULT_MAX]

    raw = (_stdout or "").strip()
    err = (_stderr or "").strip()

    # --output-format json: {result:<текст>, modelUsage:{<модель>:{…}}, is_error, api_error_status}.
    # Достаём текст ответа (result) и КАКАЯ модель реально отработала (ключи modelUsage). Парс-фейл
    # (пустой/не-json вывод, тест-моки с plain text) → деградация на сырой stdout, как в текст-режиме.
    out, models_ran, _parsed = raw, [], None
    try:
        j = json.loads(raw)
        _parsed = j
        out = (j.get("result") or "").strip()
        models_ran = list((j.get("modelUsage") or {}).keys())
    except Exception:
        pass
    if _mctx is not None:
        _mctx["model"] = ",".join(models_ran) if models_ran else model
        _ti, _to = task_metrics.extract_tokens(_parsed)
        _mctx["tokens_in"], _mctx["tokens_out"] = _ti, _to
    if models_ran:
        ran = ",".join(models_ran)
        picked = "фолбэк" if model not in ran and ORCH_MODEL_FALLBACK in ran else "основная"
        log.info("id=%s модель отработала: %s (запрошена=%s, фолбэк=%s, взята=%s)",
                 task_id, ran, model, ORCH_MODEL_FALLBACK, picked)
    else:
        log.info("id=%s модель: запрошена=%s фолбэк=%s (modelUsage пуст — ошибка резолва / текст-режим)",
                 task_id, model, ORCH_MODEL_FALLBACK)

    # Красная зона: claude самодекларировал, что нужно «да» Филиппа → needs_approval (НЕ failed).
    # ИСКЛЮЧЕНИЕ — планировщик декомпозиции (урок 166): он read-only и ничего не исполняет,
    # NEEDS_APPROVAL/фоллбэк-фразы в ЕГО выводе (red-маркеры в тексте родителя, «требует
    # подтверждения» в тексте шага) не должны глушить план на этапе планирования. Полный вывод
    # уходит в _dec_plan_and_fanout как done: план распарсился → строим (красный ШАГ спросит
    # кнопкой при исполнении); плана нет + NA-маркер → фейл-сейф чисто-красного родителя там же.
    _phrase_note = ""
    if not (preamble is not None and preamble.startswith(PLANNER_PREAMBLE)):
        _na_what, _na_kind = _detect_na(out)
        if _na_kind == "marker":
            # ЗАМОК ПРОИСХОЖДЕНИЯ: это ЗАЯВКА ИСПОЛНИТЕЛЯ, а не карточка гарда. Штампы гарда из
            # его текста вычищаем и ставим свой, честный — владелец видит источник ДО нажатия,
            # а process_new по штампу решает, рождать ли кнопку (исполнимый класс — не рождать).
            what = _stamp_self_origin(_na_what)
            log.info("id=%s заявка исполнителя (NA_MARKER): %.140s", task_id, what)
            return "needs_approval", what[:RESULT_MAX]
        if _na_kind == "quote":
            # ПОЗИЦИЯ ЗАЯВЛЕНИЯ: маркер стоит ВНУТРИ строки отчёта — это цитата. Отчёт не трогаем
            # (раньше он целиком заменялся хвостом процитированной строки), карточки нет.
            _phrase_note = NA_QUOTE_NOTE
            log.info("id=%s маркер красной зоны ПРОЦИТИРОВАН в отчёте (не в позиции заявления) — "
                     "отчёт остаётся целым, карточка НЕ рождена", task_id)
        elif _na_kind == "phrase":
            _phrase_note = NA_PHRASE_NOTE
            log.info("id=%s слова о красной зоне без маркера — карточка НЕ рождена (замок "
                     "происхождения), исход задачи остаётся честным", task_id)

    if proc.returncode != 0:
        # фикс класса (урок 105): убит ПЛАНОВЫМ рестартом демона (самомодификация) → это НЕ сбой;
        # фикс дыры 48d9c64 (урок 122): ЧУЖОЙ рестарт (единица старше старта claude) → гибель на
        # старте, работа не делалась → возврат задачи в new (requeue), НЕ done+🔁 и НЕ failed.
        planned = _planned_restart_verdict(proc.returncode, task_text, t0_mono)
        if planned == "foreign":
            log.info("id=%s claude -p погашен ЧУЖИМ плановым рестартом демона (exit=%s) → возврат в new",
                     task_id, proc.returncode)
            return "requeue", (
                "🔄 Задача взята в окно ЧУЖОГО планового рестарта демона и погашена на старте — "
                "работа НЕ выполнялась. Возвращаю в очередь: исполнится заново после рестарта.")
        if planned == "own":
            log.info("id=%s claude -p погашен ПЛАНОВЫМ рестартом демона (exit=%s) → done с пометкой",
                     task_id, proc.returncode)
            return "done", (
                "🔁 Завершено плановым рестартом демона (самомодификация): claude-процесс задачи "
                "штатно погашен отложенным systemd-run restart — по доктрине рестарт ставится "
                "ПОСЛЕДНИМ действием, работа к этому моменту сделана. Итоги — в cc_log (RESULT "
                "задачи) и git log. Это НЕ сбой.")
        log.warning("id=%s claude -p exit=%s", task_id, proc.returncode)
        # КОД ПРИЧИНЫ ставим ЗДЕСЬ, где известны сырые out/err/rc, — а не разбором готовой
        # карточки потом: причину знает тот, кто её видел (класс «судим по действию»).
        _set_fail_code(_mctx, status_truth.classify_exec(out, err, proc.returncode))
        # §12 корень 3: чистая карточка провала, НЕ сырой дамп stdout+stderr (шум).
        return "failed", _with_phrase_note(_fail_card(out, err, proc.returncode), _phrase_note)
    log.info("id=%s claude -p exit=0 (вывод %d симв)", task_id, len(out))
    return "done", _with_phrase_note(out or "(claude -p вернул пустой вывод)", _phrase_note)


def _set_fail_code(mctx, code):
    """Записать КОД причины провала в контекст исполнения. Строкой-диагнозом причину потом не
    «угадываем»: её кладёт тот участок, который её ВИДЕЛ (сырые out/err/rc, факт таймаута).
    mctx=None (планировщик/думатель зовут импл напрямую) → тихо ничего, поведение прежнее."""
    if isinstance(mctx, dict):
        mctx["fail_code"] = code


# ПРАВДА СТАТУСА: код причины и точный старт последнего run_task. Отдельный канал, а НЕ новый
# аргумент/возврат run_task — её сигнатуру мокают шесть тест-сьютов лямбдами фиксированной формы,
# и расширение сигнатуры сломало бы ровно те моки, что стерегут соседние классы.
# Детерминизм обеспечивает вызывающий: чистит словарь ПЕРЕД вызовом и сверяет id — мок run_task
# словарь не заполнит, значит обрамления не будет, и поведение под моком прежнее.
_LAST_RUN: dict = {}


def run_task(task_id, task_text, task_timeout=TASK_TIMEOUT, preamble=None):
    # Обёртка-наблюдаемость над _run_task_impl: та же сигнатура/возврат, но по завершении пишет
    # ОДНУ структурную строку METRICS в orchestrator_daemon.log (модель/усилие/тайминги/исход/
    # токены/самопочинки/канал). Замер в try/except — его сбой НИКОГДА не меняет исход задачи.
    _mctx = {"model": None, "tokens_in": None, "tokens_out": None}
    _t0 = time.monotonic()
    _start = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    _expect_busy(task_id, task_timeout)   # ярус 2: заход идёт — это продукт, а не остановка
    status, result = _run_task_impl(task_id, task_text, task_timeout, preamble, _mctx)
    try:
        _is_planner = preamble is not None and preamble.startswith(PLANNER_PREAMBLE)
        _model = _mctx.get("model") or (ORCH_MODEL if _is_planner else EXECUTOR_MODEL)
        log.info(task_metrics.metrics_line(
            task=task_id, lane="vps", model=_model, effort=EXECUTOR_EFFORT, start_iso=_start,
            end_iso=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            dur_s=time.monotonic() - _t0, outcome=status, attempts=1,
            selfheals=task_metrics.selfheal_count(task_text),
            tokens_in=_mctx.get("tokens_in"), tokens_out=_mctx.get("tokens_out"),
            task_text=task_text,
            mode=("test" if _UNDER_TEST else "prod"),
            src=(os.path.basename((sys.argv[0] if sys.argv else "") or "") or None)))
    except Exception as _e:
        log.warning("METRICS не записан (vps id=%s): %s", task_id, _e)
    _LAST_RUN.clear()
    _LAST_RUN.update({"task": task_id, "fail_code": _mctx.get("fail_code"), "started": _start})
    return status, result


# === ИСПОЛНИТЕЛИ красных op (хардкод-команды; claude НЕ участвует, op-код детерминирует команду) ===
def _exec_git_push(task_id):
    """op=git_push: git push текущей ветки. БЕЗ --no-verify → pre-push hook 4.3 (gate.py) остаётся."""
    try:
        p = subprocess.run(["git", "push"], cwd=REPO, capture_output=True, text=True, timeout=OP_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "failed", f"git push: таймаут {OP_TIMEOUT}s"
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    if p.returncode != 0:
        return "failed", cap_result(f"git push exit={p.returncode}: {out}")
    return "done", cap_result(f"git push выполнен:\n{out}")


def _exec_restart_splinter(task_id):
    """op=restart_splinter: systemctl restart splinter + проверка is-active после."""
    try:
        p = subprocess.run(["systemctl", "restart", "splinter"], capture_output=True, text=True, timeout=OP_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "failed", f"restart splinter: таймаут {OP_TIMEOUT}s"
    if p.returncode != 0:
        return "failed", f"restart splinter exit={p.returncode}: {(p.stderr or '').strip()}"[:RESULT_MAX]
    chk = subprocess.run(["systemctl", "is-active", "splinter"], capture_output=True, text=True)
    state = (chk.stdout or "").strip()
    if state != "active":
        return "failed", f"restart splinter: после рестарта is-active={state} (НЕ active!)"
    return "done", "splinter перезапущен, is-active=active"


EXECUTORS = {"git_push": _exec_git_push, "restart_splinter": _exec_restart_splinter}


# === ДЕКОМПОЗЕР: функции (родитель → план → шаги → guard → сводка) ===
def _is_dec(task):
    """Задача семейства декомпозиции (from=*-dec: родитель / шаг / synthetic-сводка)."""
    return str(task.get("from") or "").endswith(DEC_FROM_SUFFIX)


def _parse_steps(text):
    """Нумерованные строки плана «N. <шаг>» / «N) <шаг>» → список текстов шагов (по порядку).
    Прочие строки (пустые, преамбулы, маркдаун) молча игнорируются — планировщику велено их не давать."""
    steps = []
    for line in (text or "").splitlines():
        m = _PLAN_LINE_RE.match(line)
        if m:
            steps.append(m.group(2).strip())
    return steps


def _dec_red_note(steps):
    """Строка-пометка красных шагов плана для карточки родителя (урок 166): шаги с маркером
    красного (_HEADLESS_IMPOSSIBLE_RE) → «🔴 красные шаги: i, j …». Только ДИСПЛЕЙ в result —
    текст шагов в очереди НЕ трогается (и строка с 🔴 не матчит _PLAN_LINE_RE → restart-proof
    парс плана из result родителя в ПК-театре/адаптации не задевается). Нет красных → ''."""
    red = [str(i) for i, s in enumerate(steps, 1) if _is_headless_impossible(s)]
    if not red:
        return ""
    return (f"🔴 красные шаги: {', '.join(red)} — исполнитель шага спросит «да» кнопкой, "
            f"сам не исполнит.\n")


def _dec_siblings(pid, statuses):
    """Шаги родителя pid в указанных статусах очереди → [(step_i, step_n, item), …]. read-only."""
    out = []
    for st in statuses:
        try:
            r = bc.get_pending(st)
        except Exception as e:
            log.warning("dec: get_pending(%s) упал (%s)", st, e)
            continue
        if not r.get("ok"):
            continue
        for it in r.get("items", []):
            m = _STEP_RE.match(str(it.get("task_text") or ""))
            if m and int(m.group(3)) == pid:
                out.append((int(m.group(1)), int(m.group(2)), it))
    return out


def _dec_step_blocked(pid):
    """True → шаг родителя pid брать НЕЛЬЗЯ: сиблинг висит в needs_approval/approved/in_progress
    (порядок исполнения важнее скорости). Блокируется ТОЛЬКО эта цепочка — process_new возьмёт
    следующую по FIFO чужую задачу."""
    return bool(_dec_siblings(pid, _DEC_WAIT_STATUSES))


def _dec_summary_text(pid):
    """Сводный отчёт по родителю pid: все done/failed-шаги, отсортированные по номеру.
    Строка на шаг = ✅/❌ + первая строка результата (сводка ≤400 от исполнителя)."""
    rows = sorted(_dec_siblings(pid, ("done", "failed")),
                  key=lambda x: (x[0], int(x[2].get("id") or 0)))
    # адаптация плана (кусок 2): заменённые/досрочно закрытые шаги (done+♻️/⏭-карта) — не
    # результаты работы, из сводки исключаются (их закрытие уже отрапортовано отдельно)
    rows = [(i, n, it) for i, n, it in rows
            if not str(it.get("result") or "").lstrip().startswith(
                (ADAPT_REPLACED_MARK, ADAPT_FINISH_MARK))]
    # самопочинка может дать ДВЕ записи на один номер шага (исходный 🩹-done + перерождённый);
    # в сводке оставляем ПОСЛЕДНЮЮ по id (реальный финал шага). Без дублей — поведение прежнее.
    last = {}
    for i, n, it in rows:
        last[i] = (i, n, it)
    rows = [last[k] for k in sorted(last)]
    if not rows:
        return f"🧩 Сводка декомпозиции (родитель {pid}): шагов не найдено (очередь пуста?)"
    n_done = sum(1 for _i, _n, it in rows if str(it.get("status")) == "done")
    total = rows[-1][1]     # хвостовой шаг несёт АКТУАЛЬНЫЙ итог плана (adjust мог сменить N);
                            # в обычной цепи все N равны — поведение прежнее
    head = f"🧩 Сводка декомпозиции (родитель {pid}): {n_done}/{total} шагов done"
    fin = _adapt_finish.get(pid)
    if fin:
        head += f", 🏁 завершено досрочно: {fin}"
    elif n_done < len(rows):
        head += ", есть упавшие/пропущенные"
    lines = [head]
    for i, n, it in rows:
        emoji = "✅" if str(it.get("status")) == "done" else "❌"
        first = (str(it.get("result") or "").strip().splitlines() or ["(пусто)"])[0]
        lines.append(f"{emoji} шаг {i}/{n}: {first[:400]}")
    return "\n".join(lines)[:RESULT_MAX]


_summarized = set()      # родители, по которым сводка уже отправлена (память процесса; после
                         # рестарта демона от дублей защищает скан существующих сводок ниже)


def _dec_summary_exists(pid):
    """Сводка по родителю pid уже есть в очереди (в любом живом статусе)? Защита от дубля."""
    mark = f"[сводка родитель {pid}]"
    for st in ("done", "new", "in_progress"):
        try:
            r = bc.get_pending(st)
        except Exception:
            continue
        if r.get("ok") and any(str(it.get("task_text") or "").startswith(mark)
                               for it in r.get("items", [])):
            return True
    return False


def _dec_post_summary(pid):
    """Все шаги родителя pid финальны → отдать сводку в 328 synthetic-задачей (enqueue→claim→done).
    Очередь — единственный канал демона в 328; devbot принесёт её как обычный done-рапорт.
    Идемпотентно: повторный вызов (рестарт демона, хвостовой скан) дубля не даёт."""
    if pid in _summarized:
        return
    if _dec_summary_exists(pid):
        _summarized.add(pid)
        return
    text = _dec_summary_text(pid)
    r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", f"[сводка родитель {pid}] сводный отчёт по шагам")
    if not r.get("ok"):
        log.warning("dec: сводка родителя %s не встала в очередь (%s)", pid, r.get("error"))
        return
    sid = r.get("id")
    bc.claim_task(sid)                    # даже если claim не прошёл — complete финализирует
    cm = bc.complete_task(sid, "done", text)
    _summarized.add(pid)
    _adapt_finish.pop(pid, None)          # выгрузка: adapt_reason больше не нужен после сводки
    log.info("dec: сводка родителя %s → задача %s (bridge_ok=%s)", pid, sid, cm.get("ok"))
    _maybe_curator_chain(pid, text)     # куратор цели (CURATOR=1, шаг 2/7 родитель 231):
                                        # ПОСЛЕ сводки; идемпотентность выше = один вызов на цепь


def process_dec_tails():
    """Хвост декомпозиции, финализированный МИМО демона (напр. «нет N» по шагу → devbot ставит
    failed без хука цепочки): если у родителя есть failed-шаг, живых шагов не осталось, а сводки
    нет — отправить сводку. Дёшево: 1 get_pending(failed) на цикл, детали — только по новым pid."""
    try:
        r = bc.get_pending("failed")
    except Exception as e:
        log.warning("dec tails: get_pending(failed) упал (%s)", e)
        return
    if not r.get("ok"):
        return
    pids = set()
    for it in r.get("items", []):
        m = _STEP_RE.match(str(it.get("task_text") or ""))
        if m:
            pids.add(int(m.group(3)))
    for pid in pids - _summarized:
        if _dec_siblings(pid, ("new",) + _DEC_WAIT_STATUSES):
            continue        # цепочка ещё живёт — сводка придёт штатным хуком/пропуском шагов
        _dec_post_summary(pid)


def _dec_after_step(pid, step_i, step_n, status):
    """Хук после финала шага: done → адаптация плана (PLAN_ADAPT, кусок 2 мета-дирижёра);
    failed → пропустить оставшиеся new-сиблинги (цепочка зависимая, дальше идти опасно);
    все финальны → сводка по родителю."""
    if status == "done":
        try:
            _maybe_plan_adapt(pid, step_i, step_n)
        except Exception as e:      # адаптация — слой-надстройка: её сбой НЕ валит хук цепи
            log.warning("plan-adapt: сбой адаптации родителя %s (%s) — fail-safe keep", pid, e)
    if status == "failed":
        for i, n, it in sorted(_dec_siblings(pid, ("new",)), key=lambda x: x[0]):
            bc.complete_task(it.get("id"), "failed",
                             f"⏭ пропущен: шаг {step_i}/{step_n} родителя {pid} упал — цепочка остановлена")
            log.info("dec: шаг %s/%s родителя %s пропущен (цепочка остановлена)", i, n, pid)
    if not _dec_siblings(pid, ("new",) + _DEC_WAIT_STATUSES):
        _dec_post_summary(pid)


def _maybe_dec_after(task_text, status):
    """Если финализированная задача — шаг декомпозиции, дёрнуть хук цепочки (halt/сводка)."""
    m = _STEP_RE.match(str(task_text or ""))
    if m and status in ("done", "failed"):
        _dec_after_step(int(m.group(3)), int(m.group(1)), int(m.group(2)), status)


# === САМОПОЧИНКА ШАГА: функции (диагноз думателя → 1 перерождение / терминальный halt) ===
def _dec_parent_context(pid):
    """Контекст родителя pid для думателя: (исходная цель дословно, план шагов). Родитель после
    fan-out лежит в done (task_text = цель, result = план). Не нашли → заглушки (не валимся)."""
    try:
        r = bc.get_pending("done")
        if r.get("ok"):
            for it in r.get("items", []):
                if int(it.get("id") or 0) == int(pid):
                    return (str(it.get("task_text") or "").strip()[:1500],
                            str(it.get("result") or "").strip()[:2000])
    except Exception as e:
        log.warning("selfheal: контекст родителя %s не прочитан (%s)", pid, e)
    return (f"(родитель {pid} не найден в очереди)", "(план недоступен)")


def _parse_thinker_json(text, fix_key="fixed_step"):
    """Строгий парс ответа думателя → {"verdict",<fix_key>,"reason"} или None (fail-safe).
    fix_key: "fixed_step" (шаг декомпозера) / "fixed_task" (одиночная задача, расширение ст4).
    Терпим обёртку-мусор вокруг JSON (берём от первой { до последней }), но verdict обязан быть
    retry|halt — иначе None."""
    t = (text or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    v = str(d.get("verdict") or "").strip().lower()
    if v not in ("retry", "halt"):
        return None
    return {"verdict": v,
            fix_key: str(d.get(fix_key) or "").strip(),
            "reason": str(d.get("reason") or "").strip()}


def _thinker_exec(prompt, timeout, tag):
    """Общий запуск думателя (самопочинка кусок 1 / адаптация плана кусок 2): claude -p через
    кондуктор ORCH_MODEL/ORCH_MODEL_FALLBACK, чистый генератор (--max-turns 1 — один ответ, без
    инструментального цикла). Возврат: текст ответа (распакован из CLI-конверта
    --output-format json) или None при ЛЮБОМ сбое (запуск/таймаут/exit!=0) — fail-safe."""
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    child_env.pop("ANTHROPIC_API_KEY", None)   # как в run_task: идём по ~/.claude, не по платному API
    child_env.pop("OPENAI_API_KEY", None)
    # фикс 17.07: тест-флаги не утекают в дочерние; 01.08 — все четыре имени, см. run_task
    for _test_flag in ("ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PRETOOL_TEST_RUN", "PYTEST_CURRENT_TEST"):
        child_env.pop(_test_flag, None)
    cmd = [CLAUDE_BIN, "-p",
           "--model", ORCH_MODEL,
           "--fallback-model", ORCH_MODEL_FALLBACK,
           "--output-format", "json",
           "--max-turns", "1",
           "--settings", HEADLESS_SETTINGS,    # тот же строгий headless-слой (единообразие забора)
           prompt]                             # prompt последним (тест-моки читают args[-1])
    # Ярус 2: думатель тоже крутится СИНХРОННО внутри cycle() — перештамповываем окно доверия
    # своим таймаутом, иначе «задача 45 мин, следом думатель 3 мин» снова читалось бы остановкой.
    _expect_busy(tag, timeout)
    try:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                              timeout=timeout, env=child_env)
    except Exception as e:
        log.warning("%s: думатель не отработал (%s) — fail-safe", tag, e)
        return None
    raw = (proc.stdout or "").strip()
    out = raw
    try:
        env_j = json.loads(raw)
        if isinstance(env_j, dict) and "result" in env_j:   # CLI-конверт --output-format json
            out = (env_j.get("result") or "").strip()
    except Exception:
        pass
    if proc.returncode != 0:
        log.warning("%s: думатель exit=%s — fail-safe", tag, proc.returncode)
        return None
    return out


def _selfheal_consult(pid, step_i, step_n, step_text, fail_text):
    """Думатель самопочинки: промпт = цель родителя ДОСЛОВНО + план шагов + упавший шаг + суть
    провала (как _fail_card). Возврат: dict вердикта или None (любой сбой думателя = None =
    fail-safe прежний halt-on-fail)."""
    goal, plan = _dec_parent_context(pid)
    prompt = (THINKER_PREAMBLE +
              f"ИСХОДНАЯ ЦЕЛЬ РОДИТЕЛЯ (дословно):\n{goal}\n\n"
              f"ПЛАН ШАГОВ РОДИТЕЛЯ:\n{plan}\n\n"
              f"УПАВШИЙ ШАГ {step_i}/{step_n} (текст дословно):\n{step_text}\n\n"
              f"СУТЬ ПРОВАЛА:\n{str(fail_text or '')[:1200]}\n")
    out = _thinker_exec(prompt, STEP_SELFHEAL_TIMEOUT, "selfheal")
    if out is None:
        return None
    verdict = _parse_thinker_json(out)
    if verdict is None:
        log.warning("selfheal: ответ думателя не распарсился (fail-safe halt): %.200s", out)
    return verdict


def _task_selfheal_consult(task_text, fail_text):
    """Думатель самопочинки ОДИНОЧНОЙ задачи (расширение ст4): контекст — текст задачи ДОСЛОВНО +
    суть провала (родителя/плана у одиночной нет). Возврат: dict {"verdict","fixed_task","reason"}
    или None (любой сбой думателя = None = fail-safe прежний голый failed)."""
    prompt = (TASK_THINKER_PREAMBLE +
              f"УПАВШАЯ ЗАДАЧА (текст дословно):\n{str(task_text or '')[:2000]}\n\n"
              f"СУТЬ ПРОВАЛА:\n{str(fail_text or '')[:1200]}\n")
    out = _thinker_exec(prompt, STEP_SELFHEAL_TIMEOUT, "task-selfheal")
    if out is None:
        return None
    verdict = _parse_thinker_json(out, fix_key="fixed_task")
    if verdict is None:
        log.warning("task-selfheal: ответ думателя не распарсился (fail-safe failed): %.200s", out)
    return verdict


def _maybe_task_selfheal(tid, text, fail_text, frm):
    """Провал ОДИНОЧНОЙ задачи («тз:»/«задача:», НЕ шаг декомпозера) → тот же думательный слой,
    РОВНО 1 попытка (расширение ст4, 07.07.2026, тот же флаг STEP_SELFHEAL). Возврат True =
    финализация сделана здесь (перерождение / терминальный failed с диагнозом); False = прежний
    голый failed в вызывающем коде (fail-safe). Красное НЕ ослаблено: сюда доходит только
    исполнительский failed — needs_approval отсечён раньше в process_new, а плановый рестарт
    самомод-задачи (фикс 48d9c64) уже стал done внутри run_task и думателя не видит.
    Конверты одобренных заявок ([конверт…]) НЕ трогаем: их маркер обязан стоять ПЕРВЫМ —
    по нему работает разрыв петли ре-конвертов (_is_convert), перерождение сдвинуло бы его.
    PLAN_ADAPT на одиночные НЕ распространяется — плана у одиночной задачи нет."""
    if _is_convert(text):
        return False
    if str(frm or "").endswith(DEC_FROM_SUFFIX):
        return False                          # артефакт декомпозиции без [шаг i/N] — не одиночная задача
    hm = _HEAL_TASK_RE.match(str(text or ""))
    if hm:
        # перерождённая задача упала ПОВТОРНО → терминальный failed (без retry) — петля невозможна
        oid = hm.group(1)
        bc.complete_task(tid, "failed", _truthful_fail_last(tid,
                         (f"🛑 самопочинка не помогла (попытка 1 исчерпана): перерождение задачи "
                          f"{oid} упало повторно — нужен человек.\n{str(fail_text or '')}")[:RESULT_MAX]))
        log.info("task-selfheal: id=%s (перерождение задачи %s) упал ПОВТОРНО → терминальный failed",
                 tid, oid)
        return True
    verdict = _task_selfheal_consult(text, fail_text)
    if verdict is None:
        return False                          # fail-safe: сбой думателя = прежний голый failed
    reason = verdict["reason"] or "(без причины)"
    fixed = verdict["fixed_task"]
    if verdict["verdict"] != "retry" or not fixed:
        bc.complete_task(tid, "failed", _truthful_fail_last(tid,
                         (f"задача упала → думатель: halt, причина: {reason}\n"
                          f"Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX]))
        log.info("task-selfheal: id=%s → думатель halt (%s)", tid, reason[:120])
        return True
    reborn = f"[самопочинка задачи {tid}, попытка 1] {fixed}"[:RESULT_MAX]
    r = bc.enqueue_task(frm or f"Filipp-328{DEV_FROM_SUFFIX}", reborn)
    if not r.get("ok"):
        log.warning("task-selfheal: перерождение задачи id=%s не встало в очередь (%s) — fail-safe failed",
                    tid, r.get("error"))
        return False                          # fail-safe: очередь не приняла → прежний голый failed
    nid = r.get("id")
    card = (f"🩹 задача упала → думатель: retry, правка: {fixed[:200]}, причина: {reason[:200]}\n"
            f"Перерождена задачей id {nid} (попытка 1 из 1; повторный провал = терминальный failed).\n"
            f"Исходный провал: {str(fail_text or '')[:400]}")
    bc.complete_task(tid, "done", card[:RESULT_MAX])
    log.info("task-selfheal: id=%s перерождён задачей %s (retry)", tid, nid)
    return True


def _maybe_selfheal(tid, text, fail_text, frm=""):
    """Провал задачи (исполнительский failed) → думательный слой, РОВНО 1 попытка самопочинки:
    шаг декомпозера — с контекстом родителя (кусок 1); одиночная «тз:»/«задача:» — по тексту
    задачи (расширение ст4). Возврат True = финализация сделана здесь (перерождение / терминальный
    halt с диагнозом); False = ничего не делал → прежний путь в вызывающем коде (fail-safe)."""
    if not _selfheal_on():
        return False
    if str(fail_text or "").lstrip().startswith(TIMEOUT_MARK):
        # ⏱-диагнозы (таймаут задачи / сирота in_progress / молчание ПК) думатель НЕ чинит:
        # переформулировка не ускорит зависший claude и не оживит Bridge — честный failed
        return False
    m = _STEP_RE.match(str(text or ""))
    if not m:
        return _maybe_task_selfheal(tid, text, fail_text, frm)
    step_i, step_n, pid = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if _HEAL_RE.search(text):
        # перерождённый шаг упал ПОВТОРНО → терминальный halt (без retry) — петля невозможна
        bc.complete_task(tid, "failed", _truthful_fail_last(tid,
                         (f"🛑 самопочинка не помогла (попытка 1 исчерпана): шаг {step_i}/{step_n} "
                          f"родителя {pid} упал повторно — цепочка остановлена, нужен человек.\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX]))
        log.info("selfheal: id=%s шаг %s/%s родителя %s упал ПОВТОРНО → терминальный halt",
                 tid, step_i, step_n, pid)
        _maybe_dec_after(text, "failed")
        return True
    verdict = _selfheal_consult(pid, step_i, step_n, text, fail_text)
    if verdict is None:
        return False                          # fail-safe: сбой думателя = прежнее поведение
    reason = verdict["reason"] or "(без причины)"
    fixed = verdict["fixed_step"]
    if verdict["verdict"] != "retry" or not fixed:
        bc.complete_task(tid, "failed", _truthful_fail_last(tid,
                         (f"шаг {step_i}/{step_n} упал → думатель: halt, причина: {reason}\n"
                          f"Цепочка остановлена (диагноз думателя выше).\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX]))
        log.info("selfheal: id=%s шаг %s/%s родителя %s → думатель halt (%s)",
                 tid, step_i, step_n, pid, reason[:120])
        _maybe_dec_after(text, "failed")
        return True
    reborn = (f"[шаг {step_i}/{step_n} родитель {pid}] "
              f"[самопочинка шага {step_i}, попытка 1] {fixed}")[:RESULT_MAX]
    r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", reborn)
    if not r.get("ok"):
        log.warning("selfheal: перерождение шага id=%s не встало в очередь (%s) — fail-safe halt",
                    tid, r.get("error"))
        return False                          # fail-safe: очередь не приняла → прежний halt
    nid = r.get("id")
    card = (f"🩹 шаг {step_i}/{step_n} упал → думатель: retry, правка: {fixed[:200]}, "
            f"причина: {reason[:200]}\n"
            f"Перерождён задачей id {nid} (попытка 1 из 1; повторный провал = терминальный halt).\n"
            f"Исходный провал: {str(fail_text or '')[:400]}")
    bc.complete_task(tid, "done", card[:RESULT_MAX])
    log.info("selfheal: id=%s шаг %s/%s родителя %s перерождён задачей %s (retry)",
             tid, step_i, step_n, pid, nid)
    _maybe_dec_after(text, "done")
    return True


# === АДАПТАЦИЯ ПЛАНА (мета-дирижёр кусок 2, KB_MASTER §4, заведено 07.07.2026) ===
# После КАЖДОГО done-шага декомпозера (при PLAN_ADAPT=1 в .env, отдельный флаг) думатель — та же
# схема, что самопочинка: claude -p через кондуктор ORCH_MODEL/FALLBACK, чистый генератор
# (--max-turns 1) — сверяет результаты с целью родителя и решает дальнейший план. Строгий JSON
# {"verdict":"keep"|"adjust"|"finish","adjusted_steps":[…],"reason":"1 строка"}:
#   keep   → оставшиеся шаги исполняются как были (ноль изменений в очереди);
#   adjust → оставшиеся new-шаги заменяются adjusted_steps (СДЕЛАННЫЕ не трогаются); новые шаги
#            несут маркер «[коррекция плана K]», в 328 идёт карточка «после шага i думатель
#            скорректировал план: <reason>». МАКСИМУМ 2 коррекции на цепь (счётчик K —
#            restart-proof, выводится из маркеров в очереди): третий adjust → терминальный halt
#            «план дрейфует, нужен владелец» с диагнозом;
#   finish → цель достигнута досрочно: оставшиеся шаги закрываются пропуском, сводка родителя —
#            с пометкой «завершено досрочно: <reason>».
# «skipped» РЕАЛИЗОВАН КАК done+маркер-карта (⏭ досрочно / ♻️ заменён): Bridge completeTask_
# принимает ТОЛЬКО done|failed (bad_status), а редеплой Bridge = красная зона; failed нельзя —
# failed-сиблинг глушит цепь (guard в process_new). Сводка эти карты ИСКЛЮЧАЕТ (не результаты).
# ЭКОНОМИЯ ЛИМИТОВ: оставшихся шагов 0 (последний шаг) → думатель НЕ зовётся (сводка и так
# финалит); план из 2 шагов ⇒ зовётся только после шага 1 (то же правило).
# FAIL-SAFE везде: думатель упал / таймаут / мусор-JSON / verdict вне словаря / adjust с пустым
# adjusted_steps / переполнение потолка MAX_STEPS / enqueue коррекции не встал → keep (план как
# есть, не хуже текущего). Красное НЕ ослаблено: скорректированный шаг идёт обычным путём
# (NEEDS_APPROVAL → кнопка). Совместимость с самопочинкой (STEP_SELFHEAL): провал шага →
# самопочинка; done шага → адаптация; после 🩹-done исходного упавшего шага адаптация НЕ зовётся
# (перерождение того же номера ещё в очереди — guard по номеру шага).
# PLAN_ADAPT=0/нет → ветка не зовётся вовсе (байт-в-байт прежнее поведение, независимый откат).
PLAN_ADAPT_TIMEOUT = 180      # думатель — чистый генератор без tools, ответ короткий
PLAN_ADAPT_MAX = 2            # потолок коррекций на цепь; третий adjust = дрейф плана → halt
_ADAPT_MARK_RE = re.compile(r"\[коррекция плана (\d+)\]")
_ADAPT_CARD_RE = re.compile(r"^\[коррекция плана родитель (\d+)\]")
ADAPT_REPLACED_MARK = "♻️ заменён коррекцией плана"
ADAPT_FINISH_MARK = "⏭ закрыт досрочно"
_adapt_finish = {}            # pid → reason досрочного финиша (память процесса; сводка идёт
                              # в ТОМ ЖЕ вызове _dec_after_step, рестарт между ними не страшен)
ADAPT_PREAMBLE = (
    "Ты — думательный слой адаптации плана оркестратора TurboBaby (мета-дирижёр). Очередной шаг "
    "декомпозиции успешно завершён. Твоя задача — сверить результаты сделанного с целью родителя "
    "и решить, верен ли ЕЩЁ оставшийся план; ты НИЧЕГО не исполняешь, инструментов у тебя нет, "
    "файлы не читаешь — решай строго по данным ниже.\n"
    "Ответь СТРОГО ОДНИМ JSON-объектом, без текста до/после, без markdown-обёртки:\n"
    '{"verdict":"keep"|"adjust"|"finish","adjusted_steps":["<шаг>",...],"reason":"<1 строка>"}\n'
    "verdict=keep — оставшийся план верен, исполнять как есть (adjusted_steps пустой). Это "
    "ДЕФОЛТ: при малейшем сомнении — keep.\n"
    "verdict=adjust — ТОЛЬКО если результаты сделанных шагов сделали оставшиеся лишними/"
    "неверными и правка очевидна; adjusted_steps = НОВЫЙ полный список ОСТАВШИХСЯ шагов "
    "(сделанные не трогай), каждый — САМОДОСТАТОЧНОЕ дев-ТЗ ≤400 символов (исполнитель увидит "
    "ТОЛЬКО его текст, впиши нужный контекст).\n"
    "verdict=finish — цель родителя УЖЕ достигнута, оставшиеся шаги не нужны вовсе "
    "(adjusted_steps пустой).\n\n"
)


def _plan_adapt_on():
    """Флаг PLAN_ADAPT=1 в .env (отдельно от STEP_SELFHEAL). 0/нет → прежнее поведение."""
    return (os.environ.get("PLAN_ADAPT") or "").strip() == "1"


def _parse_adapt_json(text):
    """Строгий парс ответа думателя адаптации → {"verdict","adjusted_steps","reason"} или None
    (None = fail-safe keep у вызывающего). Терпим обёртку-мусор вокруг JSON; verdict обязан быть
    keep|adjust|finish; adjust без непустых adjusted_steps → None (пустой adjusted = keep)."""
    t = (text or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    v = str(d.get("verdict") or "").strip().lower()
    if v not in ("keep", "adjust", "finish"):
        return None
    raw_steps = d.get("adjusted_steps")
    steps = ([str(s).strip() for s in raw_steps if str(s).strip()]
             if isinstance(raw_steps, list) else [])
    if v == "adjust" and not steps:
        return None
    return {"verdict": v, "adjusted_steps": steps, "reason": str(d.get("reason") or "").strip()}


def _adapt_count(pid):
    """Сколько коррекций уже было у цепи родителя pid = max K из маркеров «[коррекция плана K]»
    среди шагов очереди. Restart-proof: счётчик выводится из очереди, не из памяти процесса."""
    k = 0
    for _i, _n, it in _dec_siblings(pid, ("new", "done", "failed")):
        m = _ADAPT_MARK_RE.search(str(it.get("task_text") or ""))
        if m:
            k = max(k, int(m.group(1)))
    return k


def _adapt_post_card(pid, card):
    """Карточка адаптации в 328 synthetic-задачей (enqueue→claim→done) — как сводка декомпозера:
    очередь = единственный канал демона в 328, devbot принесёт done-рапортом."""
    r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}",
                        f"[коррекция плана родитель {pid}] карточка адаптации плана")
    if not r.get("ok"):
        log.warning("plan-adapt: карточка родителя %s не встала в очередь (%s)", pid, r.get("error"))
        return
    sid = r.get("id")
    bc.claim_task(sid)                    # даже если claim не прошёл — complete финализирует
    bc.complete_task(sid, "done", card[:RESULT_MAX])


def _adapt_consult(pid, step_i, remaining):
    """Думатель адаптации: цель родителя ДОСЛОВНО + исходный план + результаты сделанных шагов
    (сжато: первая строка = сводка ≤400 исполнителя) + оставшиеся шаги → вердикт keep/adjust/
    finish. Возврат: dict вердикта или None (любой сбой = None = fail-safe keep)."""
    goal, plan = _dec_parent_context(pid)
    done_last = {}                        # номер шага → финальный результат (последний по id:
    for i, _n, it in sorted(_dec_siblings(pid, ("done",)),   # 🩹-дубли самопочинки затираются)
                            key=lambda x: (x[0], int(x[2].get("id") or 0))):
        res = str(it.get("result") or "").strip()
        if res.startswith((ADAPT_REPLACED_MARK, ADAPT_FINISH_MARK)):
            continue                      # закрытые адаптацией — не результаты работы
        done_last[i] = res
    done_lines = [f"шаг {i}: {(done_last[i].splitlines() or ['(пусто)'])[0][:300]}"
                  for i in sorted(done_last)] or ["(результатов пока нет)"]
    rem_lines = [f"шаг {i}: {_STEP_RE.sub('', str(it.get('task_text') or ''), 1).strip()[:400]}"
                 for i, _n, it in remaining]
    prompt = (ADAPT_PREAMBLE +
              f"ИСХОДНАЯ ЦЕЛЬ РОДИТЕЛЯ (дословно):\n{goal}\n\n"
              f"ИСХОДНЫЙ ПЛАН ШАГОВ:\n{plan}\n\n"
              f"РЕЗУЛЬТАТЫ СДЕЛАННЫХ ШАГОВ (сжато; только что завершён шаг {step_i}):\n"
              + "\n".join(done_lines) + "\n\n"
              "ОСТАВШИЕСЯ ШАГИ ПЛАНА:\n" + "\n".join(rem_lines) + "\n")
    out = _thinker_exec(prompt, PLAN_ADAPT_TIMEOUT, "plan-adapt")
    if out is None:
        return None
    v = _parse_adapt_json(out)
    if v is None:
        log.warning("plan-adapt: ответ думателя не распарсился/пуст (fail-safe keep): %.200s", out)
    return v


def _maybe_plan_adapt(pid, step_i, step_n):
    """Адаптация плана после done-шага декомпозера (PLAN_ADAPT=1): keep → ничего; adjust →
    заменить оставшиеся new-шаги (≤2 коррекций на цепь, третья = halt «план дрейфует»); finish →
    закрыть оставшиеся досрочно. ЛЮБОЙ сбой = keep (план как есть). Вызывается из _dec_after_step
    ДО проверки сводки — статусы, выставленные здесь, сводка увидит тем же вызовом."""
    if not _plan_adapt_on():
        return
    remaining = sorted(_dec_siblings(pid, ("new",)), key=lambda x: x[0])
    if not remaining:
        return                            # последний шаг: думателя не звать (экономия лимитов)
    if any(i <= step_i for i, _n, _it in remaining):
        return                            # перерождение самопочинки этого номера ждёт в new —
                                          # шаг реально НЕ закрыт (🩹-done лишь карточка)
    verdict = _adapt_consult(pid, step_i, remaining)
    if verdict is None or verdict["verdict"] == "keep":
        return                            # keep / fail-safe: ноль изменений в очереди
    reason = (verdict["reason"] or "(без причины)")[:300]
    if verdict["verdict"] == "finish":
        _adapt_finish[pid] = reason
        for i, n, it in remaining:
            bc.complete_task(it.get("id"), "done",
                             f"{ADAPT_FINISH_MARK}: шаг {i}/{n} не нужен — цель родителя {pid} "
                             f"достигнута после шага {step_i} (решение думателя): {reason}")
        log.info("plan-adapt: родитель %s finish после шага %s → %s шагов закрыто досрочно (%s)",
                 pid, step_i, len(remaining), reason[:120])
        return
    # adjust
    steps = verdict["adjusted_steps"]
    if step_i + len(steps) > MAX_STEPS:
        log.warning("plan-adapt: родитель %s adjust дал %s шагов (итог > потолка %s) — fail-safe keep",
                    pid, len(steps), MAX_STEPS)
        return
    k = _adapt_count(pid) + 1
    if k > PLAN_ADAPT_MAX:
        for i, n, it in remaining:
            bc.complete_task(it.get("id"), "failed",
                             f"🛑 план дрейфует: думатель запросил коррекцию №{k} (лимит "
                             f"{PLAN_ADAPT_MAX} на цепь) — цепочка остановлена, нужен владелец. "
                             f"Диагноз думателя: {reason}")
        log.info("plan-adapt: родитель %s — adjust №%s (> лимита %s) → терминальный halt (дрейф)",
                 pid, k, PLAN_ADAPT_MAX)
        return
    # порядок fail-safe: СНАЧАЛА полностью ставим новый план, ТОЛЬКО потом закрываем старый;
    # не встал целиком → откатываем вставшие новые и живём по прежнему плану (keep)
    new_total = step_i + len(steps)
    ids = []
    for j, s in enumerate(steps, start=step_i + 1):
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}",
                            (f"[шаг {j}/{new_total} родитель {pid}] [коррекция плана {k}] {s}")[:RESULT_MAX])
        if r.get("ok"):
            ids.append(r.get("id"))
        else:
            log.warning("plan-adapt: родитель %s шаг коррекции %s не встал (%s) — fail-safe keep",
                        pid, j, r.get("error"))
            for nid in ids:
                bc.complete_task(nid, "done",
                                 f"{ADAPT_REPLACED_MARK} — отменён: коррекция {k} не встала "
                                 f"целиком, действует прежний план")
            return
    for i, n, it in remaining:
        bc.complete_task(it.get("id"), "done",
                         f"{ADAPT_REPLACED_MARK} {k}: шаг {i}/{n} заменён (решение думателя "
                         f"после шага {step_i}): {reason}")
    _adapt_post_card(pid, (
        f"🧭 после шага {step_i} думатель скорректировал план (коррекция {k}/{PLAN_ADAPT_MAX}): {reason}\n"
        f"Новых шагов {len(steps)} (id {', '.join(str(x) for x in ids)}), итог плана {new_total} "
        f"шагов; сделанные шаги 1–{step_i} не тронуты. Третья коррекция = halt «план дрейфует»."))
    log.info("plan-adapt: родитель %s adjust K=%s после шага %s → %s новых шагов (id %s)",
             pid, k, step_i, len(steps), ids)


# === КУРАТОР ЦЕЛИ (мета-дирижёр, шаг 1/7 родитель 231, 12.07.2026) ===
# При CURATOR=1 в .env (отдельный флаг, парсер как STEP_SELFHEAL, дефолт 0 = ветки нет вовсе)
# думатель-«куратор» сверяет ИСХОДНУЮ ЦЕЛЬ задачи с итогом исполнителя: closed → цель закрыта;
# followup → остались ЗЕЛЁНЫЕ хвосты, tasks = самодостаточные дев-ТЗ ≤400 на дожим; human →
# дожим требует владельца. Шаг 1 внёс флаг + консультацию + парсер; шаг 2/7 подключил ТОЧКИ
# ВЫЗОВА (_maybe_curator_*: сводка родителя vps-цепи + финал done/failed одиночки vps-полосы,
# closed → тишина, followup/human → карточка-сигнал в 328); постановка followup-задач в
# очередь — следующие шаги родителя 231.
# Та же схема, что самопочинка/адаптация: _thinker_exec (кондуктор ORCH_MODEL/FALLBACK,
# --max-turns 1, чистый генератор без инструментов), строгий JSON. FAIL-SAFE: мусор / сбой /
# таймаут думателя → None — вызывающий код обязан вести себя как при CURATOR=0 (не хуже).
CURATOR_TIMEOUT = 180         # куратор — чистый генератор без tools, ответ короткий
CURATOR_TASK_MAX = 400        # потолок одного followup-ТЗ (лимит сводки в 328)
# Постановка followup-задач (шаг 3/7 родитель 231): from-метка и бюджеты. Бюджеты считаются
# restart-proof ИЗ МАРКЕРОВ очереди ([куратор цели G, шаг m] в начале task_text) — память
# процесса не нужна, рестарт демона счётчики не обнуляет.
CURATOR_FROM = "Filipp-curator"  # метка followup-задач куратора в очереди (та же полоса vps)
CURATOR_MAX_PER_ROOT = 3      # ≤3 продолжений (куратор-задач) на корень G суммарно, обе глубины
CURATOR_MAX_DEPTH = 2         # корень → продолжения (глубина 1) → дожим дожима (глубина 2) → стоп
CURATOR_MAX_PER_DAY = 10      # ≤10 куратор-задач/сутки (UTC) по ВСЕМ корням — общий предохранитель
# === РЕЕСТР ПРОВЕРЕННЫХ ФАКТОВ (15.07.2026, петля повторных диагностик) ===
# Куратор независим на каждый терминал: без памяти ставил DNS-разведку ×3 за 10 мин
# (07:38/07:42/07:47; 10:57/11:01/11:05; 15:07/15:10 — инциденты 15.07). Реестр (JSON+flock)
# хранит «факт подтверждён задачей N»: ключ = нормализованный предмет, значение = вердикт+время+id.
# Пишется при постановке (pending) и при done-финале (вердикт = первая строка result).
# Перед postановкой: свежая запись (< FACT_TTL) → refused вместо enqueue.
# Противоречие (старый ≠ новый, оба не pending) → карточка-сигнал в 328. FAIL-SAFE везде.
VERIFIED_FACTS_FILE = os.path.join(REPO, "verified_facts.json")
VERIFIED_FACTS_LOCK = os.path.join(REPO, "verified_facts.lock")
FACT_TTL = _env_int("FACT_TTL", 21600)   # 6ч по умолчанию (.env); 0 = всё устаревшее (тест)
DEDUP_WINDOW = _env_int("DEDUP_WINDOW", 1800)  # 30 мин — окно дедупа followup-проверок куратора
# === СОБЫТИЕ СОСЕДА (05.08.2026, класс «куратор не видит закрытую цель соседа») ===
# Окно соседства для тождества СОБЫТИЯ (curator_event): сосед старше окна событием уже не
# считается — факт мог протухнуть (рестарт, новые коммиты). 6ч = FACT_TTL по духу; замер на
# живом корпусе показал одинаковый результат и при 6ч, и при 24ч (оба совпадения ~1ч).
EVENT_WINDOW = _env_int("EVENT_WINDOW", 21600)
# Под тест-прогоном (ORCH_DAEMON_TEST/pytest/test_*.py) реестр заглушается: _vf_write — no-op,
# _vf_check — None. Иначе test_curator_budget/test_curator загрязняли бы production-файл
# между тест-кейсами. test_verified_facts.py явно снимает флаг + перенаправляет пути в tmpdir.
_VF_DISABLED = _UNDER_TEST
# Секции хвостов в result исполнителя: «ХВОСТ:/ХВОСТЫ:», «технически готово…; функционально…»
_CURATOR_TAIL_RE = re.compile(r"(?i)(хвост|технически готово|функциональн)")
_VF_MARKER_RE = re.compile(r"^\[куратор цели \d+, шаг \d+\](\[глубина 2\])?\s*")


def _vf_normalize(task_text):
    """Ключ реестра проверенных фактов: стрипает куратор-маркер → lowercase →
    спецсимволы в пробелы → collapse → первые 120 символов.
    None если пусто (fail-safe: None = кэш не используется)."""
    try:
        t = _VF_MARKER_RE.sub("", str(task_text or "")).lower()
        t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
        t = re.sub(r"\s+", " ", t).strip()
        return t[:120] or None
    except Exception:
        return None


def _vf_load():
    """Читает реестр с диска БЕЗ lock (вызывать только под flock). {} при ошибке."""
    try:
        with open(VERIFIED_FACTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {}
    except Exception as e:
        log.warning("vf_load: ошибка (%s) → {}", e)
        return {}


def _vf_save(data):
    """Пишет реестр на диск БЕЗ lock (вызывать только под flock)."""
    with open(VERIFIED_FACTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _vf_ts_hhmm(ts_str):
    """UTC ISO → «HH:MM UTC». «?» при ошибке."""
    try:
        t = datetime.datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return t.astimezone(datetime.timezone.utc).strftime("%H:%M")
    except Exception:
        return "?"


def _vf_entry_fresh(entry):
    """True если entry не устарел (< FACT_TTL секунд). False при ошибке разбора."""
    try:
        ts = datetime.datetime.fromisoformat(str(entry["ts"]).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - ts).total_seconds() < FACT_TTL
    except Exception:
        return False


def _vf_check(key):
    """Ищет ключ в реестре. dict entry если запись СВЕЖАЯ (< FACT_TTL), None если нет/ошибка/устарела.
    Fail-safe: любая ошибка → None (spawn ведёт себя как без кэша). _VF_DISABLED → None (под тестом)."""
    if _VF_DISABLED or not key:
        return None
    try:
        with open(VERIFIED_FACTS_LOCK, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                data = _vf_load()
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
        entry = data.get(key)
        if not entry:
            return None
        return entry if _vf_entry_fresh(entry) else None
    except Exception as e:
        log.warning("vf_check(%.60s): ошибка (%s) — fail-safe None", key, e)
        return None


def _vf_contradiction_card(key, old_entry, new_verdict, new_task_id):
    """Карточка «вердикты расходятся» в 328 (read-only synthetic, без конверта). Fail-safe тишина."""
    try:
        old_hm = _vf_ts_hhmm(old_entry.get("ts", ""))
        old_v = str(old_entry.get("verdict", "") or "")[:150]
        new_v = str(new_verdict or "")[:150]
        body = (f"⚠️ вердикты расходятся по факту «{key[:80]}»:\n"
                f"  старый: задача {old_entry.get('task_id')} в {old_hm} UTC — «{old_v}»\n"
                f"  новый: задача {new_task_id} — «{new_v}»\n"
                "(реестр обновлён новым вердиктом; если расхождение важно — проверьте вручную)")
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}",
                            f"[вердикты расходятся] {key[:60]}")
        if r.get("ok"):
            sid = r["id"]
            bc.claim_task(sid)
            bc.complete_task(sid, "done", body[:RESULT_MAX])
            log.info("vf_contradiction: карточка id=%s, ключ=%.60s", sid, key)
    except Exception as e:
        log.warning("vf_contradiction: ошибка карточки (%s) — fail-safe тишина", e)


def _vf_write(key, verdict, task_id):
    """Записывает key → {verdict, ts, task_id} в реестр с exclusive flock.
    После сброса lock: если старый и новый вердикты НЕ pending и различаются → карточка противоречия.
    Fail-safe: любая ошибка логируется, не роняет вызывающий код. _VF_DISABLED → no-op (под тестом)."""
    if _VF_DISABLED or not key:
        return
    contradiction = None
    try:
        with open(VERIFIED_FACTS_LOCK, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = _vf_load()
                old = data.get(key)
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                old_v = str(old.get("verdict") or "").strip() if old else ""
                new_v = str(verdict or "").strip()
                if (old and old_v not in ("pending", "") and new_v not in ("pending", "")
                        and old_v.lower() != new_v.lower()):
                    contradiction = (old, verdict)   # эмитируем ПОСЛЕ сброса lock
                data[key] = {"verdict": str(verdict or "")[:200],
                             "ts": now_iso, "task_id": task_id}
                _vf_save(data)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception as e:
        log.warning("vf_write(%.60s): ошибка (%s) — fail-safe", key, e)
        return
    if contradiction:
        _vf_contradiction_card(key, contradiction[0], contradiction[1], task_id)


# === ДЕДУП FOLLOWUP-ПРОВЕРОК (15.07.2026, наблюдение: цели 82/83 — wa-webhook ×2, цель 73 — DNS ×2)
# Куратор видит только текущий терминал и не знает, что аналогичная read-only проверка уже
# выполнена другой задачей за последние 30 мин. Два слоя: (1) промпт-инъекция — куратор получает
# список недавних done-задач и решает семантически; (2) программный фильтр — нормализованный ключ
# предложенной задачи совпадает с ключом done-задачи → refused+note. Deploy-контекст (терминал сам
# был изменением) → дедуп пропускается (проверки после деплоя обязаны быть свежими). FAIL-SAFE везде.


def _recent_done_tasks_map(window_sec=None):
    """Done-задачи из bridge в окне window_sec сек → {normalized_key: task_id}.
    Fail-safe: {} при ошибке / _VF_DISABLED (под тестом, как и весь VF-блок)."""
    if _VF_DISABLED:
        return {}
    ws = window_sec if window_sec is not None else DEDUP_WINDOW
    try:
        r = bc.get_pending("done")
        if not r.get("ok"):
            return {}
        out = {}
        for it in r.get("items", []):
            age = _age_sec(it.get("updated"))  # _age_sec определена ниже по файлу — OK, Python резолвит при вызове
            if age is None or age >= ws:
                continue
            k = _vf_normalize(it.get("task_text", ""))
            if k:
                out[k] = it.get("id")
        return out
    except Exception as e:
        log.warning("recent_done_map: ошибка (%s) — fail-safe {}", e)
        return {}


_DEPLOY_CTX_RE = re.compile(
    r"(?i)(деплой|deploy|clasp\s+redeploy|git\s+push|рестарт\s+splinter|рестарт\s+демон"
    r"|restart\s+splinter|перезапустил|задеплоил|новая\s+версия|коммит|commit\b)")


def _is_deploy_context(goal, result):
    """True если терминал — деплой/код-изменение/рестарт. В таком контексте
    followup-проверки обязаны быть свежими, дедуп не применяется."""
    return bool(_DEPLOY_CTX_RE.search(str(goal or "") + " " + str(result or "")))


def _followup_dedup(tasks, goal="", result=""):
    """Фильтрует предложенные followup-задачи против недавних done-задач (DEDUP_WINDOW).
    Deploy-контекст → пропуск дедупа (проверки после изменений должны быть свежими).
    Возврат (remaining, refused): refused = [(task_text, reason), ...].
    Fail-safe: (tasks, []) при любой ошибке или _VF_DISABLED."""
    if _VF_DISABLED or _is_deploy_context(goal, result):
        return tasks, []
    try:
        done_map = _recent_done_tasks_map(DEDUP_WINDOW)
        if not done_map:
            return tasks, []
        remaining, refused = [], []
        for t in tasks:
            k = _vf_normalize(t)
            if k and k in done_map:
                did = done_map[k]
                refused.append((t, f"проверка уже выполнена задачей {did}"))
            else:
                remaining.append(t)
        return remaining, refused
    except Exception as e:
        log.warning("followup_dedup: ошибка (%s) — fail-safe (все задачи без фильтра)", e)
        return tasks, []


CURATOR_PREAMBLE = (
    "Ты — куратор целей оркестратора TurboBaby (мета-дирижёр). Headless-задача завершилась — "
    "сверь ИСХОДНУЮ ЦЕЛЬ с итогом исполнителя и реши, закрыта ли цель. Ты НИЧЕГО не исполняешь, "
    "инструментов у тебя нет, файлы не читаешь — решай строго по данным ниже.\n"
    "Ответь СТРОГО ОДНИМ JSON-объектом, без текста до/после, без markdown-обёртки:\n"
    '{"verdict":"closed"|"followup"|"human","tasks":["<зелёное ТЗ ≤400>"],'
    '"human":"<что нужно от владельца>","reason":"<1 строка>"}\n'
    "closed — цель достигнута, хвостов нет (или они чисто косметические; tasks/human пустые). "
    "followup — остались ЗЕЛЁНЫЕ хвосты (код/тесты/доки/диагностика БЕЗ красной зоны: без записи "
    "в рабочие таблицы, денег, clasp, sqlite3, удалений; рестарт/старт своих сервисов "
    "splinter/orchestrator-daemon/wa-webhook и daemon-reload — оранжевые, tasks допустимы); "
    "tasks тогда — 1–3 САМОДОСТАТОЧНЫХ "
    "дев-ТЗ ≤400 символов каждое (исполнитель увидит ТОЛЬКО текст ТЗ, впиши нужный контекст). "
    "human — дожим требует владельца (красная зона, бизнес-решение, доступы, ручной тест); human "
    "тогда — 1 строка, что именно нужно. ЖЕЛЕЗНО: красные и смок-шаги (запись в рабочие таблицы "
    "Лист1/CRM/Зарплаты, деньги, clasp, sqlite3, удаления, деплой, смок-прогон на живых данных) — "
    "ТОЛЬКО в human, НИКОГДА в tasks. При сомнении между followup и human выбирай human — "
    "куратор не плодит самодеятельность.\n"
    "ВЕРИФИКАЦИЯ (класс R11–R15): наличие блока «FACT:» в итоге исполнителя — признак верификации "
    "живым фактом. Его ОТСУТСТВИЕ у dev-задачи — сигнал неопределённости: при сомнении выбирай "
    "followup/human, а не closed (эффект не доказан — цель нельзя считать закрытой уверенно).\n\n"
)


def _curator_on():
    """Флаг CURATOR=1 в .env (демон load_dotenv'ит на старте; парсер как STEP_SELFHEAL).
    0/нет/мусор → куратор выключен, поведение прежнее."""
    return (os.environ.get("CURATOR") or "").strip() == "1"


def _curator_scope_on():
    """Флаг CURATOR_SCOPE=1 в .env: done-одиночки без коммита в result → мимо куратора
    (read-only разведки/диагностики не плодят followup). 0/нет → текущее поведение
    (консультация на каждом done/failed одиночки). Откат: CURATOR_SCOPE=0 + рестарт демона."""
    return (os.environ.get("CURATOR_SCOPE") or "").strip() == "1"


def _gate_single_selective_on():
    """Флаг GATE_SINGLE_SELECTIVE=1 в .env: одиночные «тз:»/«задача:» → селективный гейт
    (smoke + затронутые модули вместо полного сьюта). Fail-safe: gate.py не смог определить
    затронутые → полный сьют. 0/нет → полный гейт на одиночных (прежнее поведение)."""
    return (os.environ.get("GATE_SINGLE_SELECTIVE") or "").strip() == "1"


_COMMIT_IN_RESULT_RE = re.compile(r"(?i)(коммит\b|commit\b|git\s+push)")
_RESULT_FACT_RE = re.compile(r"\bFACT\s*:", re.IGNORECASE)


def _result_has_commit(result):
    """True если result содержит признак коммита / push — задача делала изменения кода."""
    return bool(_COMMIT_IN_RESULT_RE.search(str(result or "")))


def _result_has_fact(result):
    """True если result содержит блок FACT: — живое доказательство эффекта (класс R11–R15)."""
    return bool(_RESULT_FACT_RE.search(str(result or "")))


def _curator_tails(result):
    """Секции «ХВОСТ/ХВОСТЫ/технически готово…; функционально…» из result исполнителя:
    строка-триггер + её блок вниз до пустой строки. Секций нет → явная заглушка (куратор видит,
    что исполнитель хвостов не заявил). Общий потолок 1500 символов."""
    lines = str(result or "").splitlines()
    blocks, i = [], 0
    while i < len(lines):
        if _CURATOR_TAIL_RE.search(lines[i]):
            j = i
            while j < len(lines) and lines[j].strip():
                j += 1
            blocks.append("\n".join(lines[i:j]))
            i = j
        else:
            i += 1
    return "\n\n".join(blocks)[:1500] if blocks else "(секций про хвосты в итоге нет)"


def _parse_curator_json(text):
    """Строгий парс ответа куратора → {"verdict","tasks","human","reason"} или None (fail-safe).
    Терпим обёртку-мусор вокруг JSON (от первой { до последней }); verdict обязан быть
    closed|followup|human; followup без непустых tasks → None (пустой followup бессмыслен);
    каждое ТЗ режется до CURATOR_TASK_MAX (лимит сводки 328)."""
    t = (text or "").strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        d = json.loads(t[i:j + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    v = str(d.get("verdict") or "").strip().lower()
    if v not in ("closed", "followup", "human"):
        return None
    raw = d.get("tasks")
    tasks = ([str(s).strip()[:CURATOR_TASK_MAX] for s in raw if str(s).strip()]
             if isinstance(raw, list) else [])
    if v == "followup" and not tasks:
        return None
    return {"verdict": v, "tasks": tasks,
            "human": str(d.get("human") or "").strip(),
            "reason": str(d.get("reason") or "").strip()}


def _curator_consult(goal, result):
    """Куратор цели (CURATOR=1): вход — цель ДОСЛОВНО + итог/сводка (первая строка result — по
    протоколу это сводка ≤400 для 328) + секции хвостов из result → вердикт closed/followup/human.
    Возврат: dict вердикта или None при ЛЮБОМ сбое (запуск/таймаут/мусор) — fail-safe, вызывающий
    код ведёт себя как при CURATOR=0."""
    res = str(result or "").strip()
    summary = (res.splitlines() or ["(итог пуст)"])[0][:400] or "(итог пуст)"
    # Промпт-инъекция: недавние done-задачи (DEDUP_WINDOW) — куратор решает семантически,
    # не ставить ли дублирующую проверку. Пуст при _VF_DISABLED (тесты) или нет свежих задач.
    recent_map = _recent_done_tasks_map(DEDUP_WINDOW)
    if recent_map:
        lines = [f"  - задача {tid}: {key[:80]}" for key, tid in list(recent_map.items())[:12]]
        recent_ctx = ("\n\nНЕДАВНО ВЫПОЛНЕННЫЕ ЗАДАЧИ (окно 30 мин):\n" + "\n".join(lines) +
                      "\nЕсли предлагаемый followup по смыслу дублирует задачу выше — "
                      "не включай его в tasks (верни closed или исключи из tasks).\n")
    else:
        recent_ctx = ""
    prompt = (CURATOR_PREAMBLE +
              f"ИСХОДНАЯ ЦЕЛЬ (дословно):\n{str(goal or '').strip()[:1500]}\n\n"
              f"ИТОГ/СВОДКА ИСПОЛНИТЕЛЯ:\n{summary}\n\n"
              f"СЕКЦИИ ХВОСТОВ ИЗ ИТОГА:\n{_curator_tails(res)}\n"
              + recent_ctx)
    out = _thinker_exec(prompt, CURATOR_TIMEOUT, "curator")
    if out is None:
        return None
    v = _parse_curator_json(out)
    if v is None:
        log.warning("curator: ответ куратора не распарсился (fail-safe None): %.200s", out)
    return v


# --- Точки вызова куратора (шаг 2/7 родитель 231): терминалы vps-полосы ---
# Куратор зовётся РОВНО один раз на терминал (дедуп: память процесса _curated + restart-proof
# скан маркеров [куратор …] в очереди). verdict=closed / сбой думателя → тишина (поведение как
# при CURATOR=0); followup/human → карточка-сигнал [куратор …] в 328 synthetic-задачей (тот же
# канал, что сводки/коррекции) — она же и маркер дедупа. МИМО куратора: ⏱-диагнозы
# (таймаут/сирота/ПК — инфраструктура, не цель), «отклонено Филиппом» (владелец уже решил),
# конверты одобренных заявок, pc-полоса (_pc_post_summary хук не зовёт; одиночки pc в process_new
# не попадают), плановый рестарт-🔁 (работа отчитана в cc_log, итога для сверки нет).
_CURATOR_CARD_RE = re.compile(r"^\[куратор (задача|родитель) (\d+)\]")
# Маркер followup-задачи куратора (шаг 3/7): G = id КОРНЕВОЙ задачи (или родителя цепи), m —
# сквозной номер продолжения по корню. Для бюджетов regex матчится ОТ НАЧАЛА task_text
# (.match — перерождения самопочинки с их префиксом не задваивают счёт), для трассировки корня
# на терминале — поиском по тексту (.search — маркер жив и под префиксом перерождения).
_CURATOR_GOAL_RE = re.compile(r"\[куратор цели (\d+), шаг (\d+)\]")
_CURATOR_DEPTH2_MARK = "[глубина 2]"  # тег сразу ЗА маркером у продолжений второй глубины
# Ветка human (шаг 4/7 родитель 231): пункты «нужно от владельца» НЕ ставятся задачами, а копятся
# в ОДНУ сводную карточку на цель G — synthetic-задачу [куратор владельцу цель G] в статусе
# needs_approval (devbot несёт needs_approval в инбокс INBOX_TOPIC_ID, прод 1160). Новые пункты
# той же цели дописываются ПРАВКОЙ result существующей открытой карточки (set_needs_approval
# по любому статусу перезаписывает result); тот же текст пункта повторно → счётчик ×N на той же
# строке, НЕ дубль (дедуп-образец bd5d516). Маркер НЕ матчится ни _CURATOR_CARD_RE (задача|
# родитель), ни _CURATOR_GOAL_RE (куратор цели) — бюджеты followup и дедуп терминалов не путает.
# ОПЕРАЦИОННАЯ КАРТОЧКА (класс 251/254/257, 05.08.2026): пункт, назвавший ДВЕ И БОЛЕЕ операции,
# разводится по карточкам — по одной на операцию, маркер несёт КЛЮЧ семьи операции
# ([куратор владельцу цель 247, операция bridge_deploy]). Ключ, а не порядковый номер: он и есть
# restart-proof дедуп (та же операция той же цели повторно → ×N на своей карточке, а не второй
# дубль). Общая карточка «к сведению» остаётся с прежним маркером БЕЗ хвоста, поэтому
# startswith-поиск `_curator_human_upsert` операционные карточки не подхватывает (после числа
# цели у них запятая, а не `]`).
_CURATOR_HUMAN_RE = re.compile(r"^\[куратор владельцу цель (\d+)(?:, операция ([^\]]+))?\]")
_CURATOR_HUMAN_ITEM_RE = re.compile(r"^(\d+)\. (.+?)(?: \(×(\d+)\))?$")
_HUMAN_CONT = "    "          # префикс строки-ПРОДОЛЖЕНИЯ пункта (разбор склеивает их обратно)
_HUMAN_OVERFLOW = "…пунктов не поместилось:"   # видимый след урезки тела под подпись
# Служебные строки операционной карточки. Начинаются с «· » намеренно: разбор пунктов читает
# только строки «N. …» и продолжения с отступом _HUMAN_CONT, поэтому служебное в ТЗ конверта
# пунктом не притворится. Контекст кладётся ОДНОЙ строкой (переводы строк схлопнуты) — иначе
# строка «1. …» внутри дословного текста куратора уехала бы в конверт как отдельный пункт.
_HUMAN_SCOPE = ("· это «да» покрывает ТОЛЬКО операцию из заголовка карточки — соседние операции "
                "того же пункта ждут своих «да» на своих карточках.")
_HUMAN_SIBL = "· рядом по этому же пункту ждут: "
_HUMAN_CTX = "· контекст пункта куратора (дословно): "
_HUMAN_CTX_MIN = 200          # ниже этого контекст не режем — резать дальше нечего, режем пункты
# ЧАСТИЧНЫЙ РАЗВОД НАЗЫВАЕТ СЕБЯ В САМОЙ КАРТОЧКЕ (класс 05.08.2026). Карточки развода встают ПО
# ОДНОЙ, и каждая постановка может не встать сама по себе (мост/очередь — живой класс 138/146).
# До правки недостающие операции назывались ТОЛЬКО в отчётной карточке 328, а карточка ИНБОКСА
# вдобавок утверждала обратное: строка соседей перечисляла ВСЕ операции пункта, включая те, у
# которых карточки нет и не будет. Владелец решал по неполному списку, считая его полным, — это
# хуже лишней карточки: молчание о том, что требует его воли. FAIL-CLOSED «до факта» здесь
# невозможен по устройству: отказ обнаруживается только попыткой, а поставленную карточку не
# отозвать честно (мост знает лишь done|failed — закрытая строка оставила бы владельцу в инбоксе
# кнопку без задачи, ту же ложь с другой стороны). Значит честная форма одна — назвать нехватку.
# Токенов объекта в строке нет намеренно (см. _curator_human_render): её читает devbot._card_objects.
_HUMAN_MISSING = ("· ⚠️ РАЗВОД НЕ ПОЛНЫЙ: эти операции того же пункта карточки НЕ получили — "
                  "своего «да» они здесь не ждут и отдельной карточкой не придут, "
                  "дожимать отдельным «тз:»: ")
_HUMAN_WHY_MAX = 70           # диагноз в карточке — хвостом; целиком он живёт в отчёте 328
# ИМЯ ПОД ОТРИЦАНИЕМ ЗАЯВКОЙ НЕ ЯВЛЯЕТСЯ (класс карточек 349/357/358, 06.08.2026). Развод пункта
# вытаскивал имя сервиса из фразы «splinter НЕ трогаем» и из описания вариантов выбора и выписывал
# на него карточку — владелец отклонял. Демотировка (см. `curator_claim`) НЕ снимает карточку, она
# снимает РАЗВОД: пункт едет владельцу целиком, одним «да», ровно как до 05.08. Но молчать об этом
# нельзя — если машина ошиблась и имя всё-таки было просьбой, заметит это только владелец, поэтому
# карточка НАЗЫВАЕТ демотированные имена. Токенов объекта в строке нет намеренно (её читает
# devbot._card_objects): называем ЯРЛЫК операции, а не команду — литерал куратора и так стоит
# дословно в самом пункте строкой выше.
_HUMAN_NOTCLAIM = ("⚠️ НАЗВАНО, НО ЗАЯВКОЙ НЕ СОЧТЕНО (отдельной карточки на это нет; пункт "
                   "по операциям НЕ разведён — он перед тобой ЦЕЛИКОМ, одним «да»): ")
_HUMAN_NOTCLAIM_TAIL = " · если это была просьба — дожми её отдельным «тз:»."
_NOTE_TOLD = "в карточки владельца это вписано"
_NOTE_SILENT = "молчат о недостающих операциях"
# ПОДПИСЬ КАРТОЧКИ ВЛАДЕЛЬЦУ — единственное место, где сказано, что случится ПОСЛЕ ✅.
# Названы ОБА исхода, а не выбран один: тип пункта по-прежнему НЕ угадываем (признака
# «разрешение vs к сведению» в свободной строке куратора нет), но и не обещаем исполнения там,
# где контур исполнять не вправе. Живое основание правки (04.08.2026): карточка 257 → конверт
# 258 вернулся ручной картой (деплой моста — красное), карточка 264 → конверт 265 закрылся
# done, не сделав ничего (единственное действие пункта — строка в файле секретов, агенту
# закрыта жёстким блоком гарда). Оба раза подпись ДО нажатия обещала «пункт будет выполнен».
# ТОКЕНОВ ОБЪЕКТА В ПОДПИСИ НЕТ (см. докстринг _curator_human_render): красная зона названа
# словами, без имён команд и обратных кавычек — иначе devbot._card_objects подсунул бы
# владельцу объект сверки, которого тот не просил.
_HUMAN_SIGN = (
    "✅ — ПОСТАВЛЮ ЗАДАЧУ на исполнение этих пунктов (её номер придёт отдельным рапортом "
    "в 328): пункт, просящий разрешение на операцию, будет выполнен; пункт «просто принял "
    "к сведению» закроется без действий. Если пункт упирается в настоящее красное (рабочие "
    "таблицы, деньги, деплой моста, база памяти, файл секретов, удаление вне временного "
    "каталога) — задача вернёт его тебе ручной картой: «да» на ЭТОЙ карточке гейт красной "
    "зоны НЕ открывает. ❌ — отклонить, ничего не делаю. Новые пункты этой цели куратор "
    "дописывает в ЭТУ карточку (актуальный список — /inbox).")
_CURATOR_SKIP_MARKS = (TIMEOUT_MARK, "🔁", _REJECT_PREFIX)
_curated = set()              # (kind, id) — терминалы, по которым консультация уже потрачена


def _curator_card_exists(kind, key):
    """Карточка куратора по этому терминалу уже в очереди (любой живой статус)? Restart-proof
    слой дедупа: после рестарта демона память _curated пуста, маркер в очереди — нет."""
    mark = f"[куратор {kind} {key}]"
    for st in ("done", "new", "in_progress"):
        try:
            r = bc.get_pending(st)
        except Exception:
            continue
        if r.get("ok") and any(str(it.get("task_text") or "").startswith(mark)
                               for it in r.get("items", [])):
            return True
    return False


def _curator_root_depth(kind, key, goal):
    """Корень G и ГЛУБИНА новых продолжений по тексту терминала (restart-proof: только маркеры).
    Терминал без маркера куратора → корень = сам терминал, новые задачи = глубина 1;
    терминал-продолжение ([куратор цели G, шаг m]) → тот же корень G, новые = глубина 2;
    терминал с тегом [глубина 2] → новые были бы глубиной 3 (запрещено, вернём 3).
    Терминал-родитель цепи — всегда корень (шаги цепи кураторских маркеров не несут)."""
    if kind != "задача":
        return int(key), 1
    t = str(goal or "")
    m = _CURATOR_GOAL_RE.search(t)
    if not m:
        return int(key), 1
    if t[m.end():m.end() + len(_CURATOR_DEPTH2_MARK)] == _CURATOR_DEPTH2_MARK:
        return int(m.group(1)), 3
    return int(m.group(1)), 2


def _queue_items():
    """Очередь ЦЕЛИКОМ одним CSV-опросом → list[dict] (у каждого item есть status), None при
    сбое. Один опрос обслуживает и бюджеты (_curator_used), и тождество события
    (_curator_event_seen) — второго похода к мосту за тот же снимок не делаем."""
    try:
        r = bc.get_pending("new,in_progress,done,failed,needs_approval,approved")
    except Exception:
        return None
    if not r.get("ok"):
        return None
    return list(r.get("items", []))


def _curator_used(root, items=None):
    """Срез бюджетов из маркеров очереди ОДНИМ CSV-опросом (restart-proof):
    (продолжений по корню root, куратор-задач за сегодня UTC по всем корням, max шаг корня).
    None при сбое опроса — вызывающий код задачи НЕ ставит (fail-safe: без доказанного бюджета
    не плодим, карточка объяснит владельцу). created нечитаем → считаем сегодняшней (в сторону
    лимита, не в сторону спама). items — готовый снимок очереди (см. _queue_items); None →
    опрашиваем сами (прежнее поведение)."""
    if items is None:
        items = _queue_items()
    if items is None:
        return None
    per_root, today, max_step = 0, 0, 0
    now = datetime.datetime.now(datetime.timezone.utc)
    for it in items:
        m = _CURATOR_GOAL_RE.match(str(it.get("task_text") or ""))
        if not m:
            continue
        if int(m.group(1)) == int(root):
            per_root += 1
            max_step = max(max_step, int(m.group(2)))
        try:
            s = str(it.get("created")).replace("Z", "+00:00")
            t = datetime.datetime.fromisoformat(s)
            if t.tzinfo is None:
                t = t.replace(tzinfo=datetime.timezone.utc)
            if t.astimezone(datetime.timezone.utc).date() == now.date():
                today += 1
        except Exception:
            today += 1
    return per_root, today, max_step


# === СОБЫТИЕ СОСЕДА: тот же факт уже проверяет/проверила ДРУГАЯ цель (05.08.2026) ===
# Куратор независим на каждом терминале и НЕ ВИДИТ соседних целей. Живой класс: ТЗ владельца
# пришло дважды (цели 320/324 и 319/323 — дословно один заголовок), каждая цель родила свою
# журнальную проверку одного события, все холостые («запись была с самого начала»). Реестр
# фактов (_vf_*) и дедуп окна (_followup_dedup) их не ловят: ключ там — ТЕКСТ задачи, а
# формулировки соседей разные. Тождество здесь считается ПО СОБЫТИЮ (curator_event: вид факта
# × предмет-имя), ОБЛАСТЬ (файл/модуль) предметом не считается — две цели вправе править один
# файл разными правками. FAIL-SAFE везде: снимка нет / событие не образовано / любое
# исключение → задача ставится КАК ПРЕЖДЕ (правило умеет только НЕ ставить, а не разрешать).
_EVENT_DEAD_STATUS = ("failed", "rejected")   # сосед умер — факт не закрыт, проверять законно


def _curator_event_seen(root, task_text, goal, items):
    """Сосед по СОБЫТИЮ: кураторская задача ДРУГОГО корня в окне EVENT_WINDOW, чьё событие
    совпало с событием предлагаемого ТЗ. Возврат (id, root2, status2, «HH:MM», предмет) или
    None. Свой корень пропускается намеренно — это шаги одной цели, их держат бюджеты.
    Свежайший сосед выигрывает (о нём и говорим владельцу)."""
    try:
        if not items:
            return None
        by_id = {}
        for it in items:
            try:
                by_id[int(it.get("id"))] = it
            except (TypeError, ValueError):
                continue
        goal_text = str((by_id.get(int(root)) or {}).get("task_text") or goal or "")
        mine = curator_event.event_of(task_text, goal_text)
        if mine is None:
            return None
        best = None
        for it in items:
            m = _CURATOR_GOAL_RE.match(str(it.get("task_text") or ""))
            if not m:
                continue
            root2 = int(m.group(1))
            if root2 == int(root):
                continue
            if str(it.get("status") or "").strip().lower() in _EVENT_DEAD_STATUS:
                continue
            age = _age_sec(it.get("created"))
            if age is None or age > EVENT_WINDOW:
                continue
            goal2 = str((by_id.get(root2) or {}).get("task_text") or "")
            ev2 = curator_event.event_of(it.get("task_text"), goal2)
            if not curator_event.same_event(mine, ev2):
                continue
            if best is None or age < best[0]:
                best = (age, it.get("id"), root2, str(it.get("status") or ""),
                        _vf_ts_hhmm(it.get("created")), curator_event.shared_subject(mine, ev2))
        return best[1:] if best else None
    except Exception as e:
        log.warning("curator-event: сбой сверки события (%s) — fail-safe (ставим как прежде)", e)
        return None


def _curator_spawn(kind, key, goal, tasks):
    """Ветка followup (шаг 3/7 родитель 231): каждое ТЗ куратора → задача from=Filipp-curator
    ТОЙ ЖЕ полосы (куратор живёт только на vps-терминалах → полоса vps, дефолт enqueue) с
    маркером [куратор цели G, шаг m]; вторая глубина несёт тег [глубина 2]. Бюджеты — из
    маркеров очереди (см. _curator_used): превышение / сбой опроса / enqueue-fail → ТЗ уходит
    в refused (владелец увидит его в карточке и может дожать «тз:» руками), постановка не
    падает и не зацикливается. Возврат {"placed":[(id, ТЗ)...], "refused":[(ТЗ, почему)...],
    "root": G}."""
    root, depth = _curator_root_depth(kind, key, goal)
    if depth > CURATOR_MAX_DEPTH:
        return {"root": root, "placed": [],
                "refused": [(t, f"глубина цепочки продолжений > {CURATOR_MAX_DEPTH}") for t in tasks]}
    items = _queue_items()        # ОДИН снимок очереди на бюджеты И на тождество события
    used = _curator_used(root, items)
    if used is None:
        return {"root": root, "placed": [],
                "refused": [(t, "очередь не опросить — бюджет не доказать") for t in tasks]}
    per_root, today, max_step = used
    depth_tag = _CURATOR_DEPTH2_MARK if depth == 2 else ""
    placed, refused = [], []
    for t in tasks:
        if per_root >= CURATOR_MAX_PER_ROOT:
            refused.append((t, f"исчерпан лимит корня ({CURATOR_MAX_PER_ROOT} продолжений на цель)"))
            continue
        if today >= CURATOR_MAX_PER_DAY:
            refused.append((t, f"исчерпан суточный лимит ({CURATOR_MAX_PER_DAY} куратор-задач/сутки)"))
            continue
        # Сверка с реестром проверенных фактов: свежий факт → не ставим дубль диагностики
        vf_key = _vf_normalize(t)
        cached = _vf_check(vf_key) if vf_key else None
        if cached is not None:
            cv = str(cached.get("verdict") or "").strip()
            hm = _vf_ts_hhmm(cached.get("ts", ""))
            cid = cached.get("task_id")
            if cv == "pending":
                refused.append((t, f"кэш: задача {cid} уже поставлена в {hm} UTC (ожидает результат)"))
            else:
                refused.append((t, f"кэш: уже подтверждено задачей {cid} в {hm} UTC — «{cv[:80]}»"))
            continue
        # СОБЫТИЕ СОСЕДА: тот же факт уже закрыт/проверяется ДРУГОЙ целью (тождество по
        # событию, не по номеру цели и не по области). Отказ виден владельцу в карточке —
        # не согласен, дожимает «тз:» руками.
        seen = _curator_event_seen(root, t, goal, items)
        if seen is not None:
            sid_, sroot, sstat, shm, subj = seen
            closed = str(sstat).strip().lower() == "done"
            refused.append((t, ("событие уже закрыто целью" if closed else
                                "то же событие уже проверяет цель") +
                            f" {sroot} (задача {sid_}, {shm} UTC" +
                            (")" if closed else f", статус {sstat})") +
                            (f"; общий предмет — {subj}" if subj else "")))
            log.info("curator-event: ТЗ по цели %s не поставлено — сосед %s (цель %s, %s), предмет %s",
                     root, sid_, sroot, sstat, subj)
            continue
        max_step += 1
        try:
            r = bc.enqueue_task(CURATOR_FROM, f"[куратор цели {root}, шаг {max_step}]{depth_tag} {t}")
        except Exception as e:
            r = {"ok": False, "error": str(e)}
        if r.get("ok"):
            placed.append((r.get("id"), t))
            _vf_write(vf_key, "pending", r.get("id"))   # отметить: поставлено, ожидает результат
            per_root += 1
            today += 1
        else:
            max_step -= 1
            refused.append((t, f"enqueue не прошёл ({r.get('error')})"))
    return {"root": root, "placed": placed, "refused": refused}


def _curator_human_items(body):
    """Пункты из тела сводной карточки владельцу → [(текст, счётчик)]. Строки-ненумерованные
    (заголовок, подсказка, пустые) молча пропускаются — рендер их пересоберёт.

    ПРОДОЛЖЕНИЕ ПУНКТА (04.08.2026, вторая ревизия класса «кнопка не порождает работу»):
    разбор шёл ПОСТРОЧНО, и у многострочного пункта в ТЗ конверта уезжала ТОЛЬКО ПЕРВАЯ
    строка — владелец видел на карточке весь пункт, жал ✅, а исполнитель получал огрызок
    («нужно два решения:» без самих решений). Замер до правки: пункт из трёх строк доезжал
    одной. Теперь рендер отбивает продолжения префиксом _HUMAN_CONT, а разбор склеивает их
    обратно — пункт доезжает ДОСЛОВНО. Строки без префикса (подпись, заголовок) пунктом и
    его продолжением НЕ становятся."""
    items = []
    for ln in str(body or "").splitlines():
        if items and ln.startswith(_HUMAN_CONT):
            t, n = items[-1]
            items[-1] = (t + "\n" + ln[len(_HUMAN_CONT):], n)
            continue
        m = _CURATOR_HUMAN_ITEM_RE.match(ln.strip())
        if m:
            items.append((m.group(2).strip(), int(m.group(3) or 1)))
    return items


def _human_item_block(i, t, n):
    """Пункт → блок строк карточки: номер на ПЕРВОЙ строке (её читает _CURATOR_HUMAN_ITEM_RE),
    остальные строки пункта — с префиксом продолжения. ×N остаётся на первой строке: счётчик
    живёт там же, где номер, иначе разбор его не увидит."""
    ls = str(t or "").split("\n")
    first = f"{i}. {ls[0]}" + (f" (×{n})" if n > 1 else "")
    return "\n".join([first] + [_HUMAN_CONT + x for x in ls[1:]])


def _curator_human_render(root, items, op=None):
    """Тело сводной карточки «нужно от владельца» по цели root. Пункт с счётчиком >1 несёт ×N.

    op (класс 251/254/257, 05.08.2026) — карточка ОДНОЙ операции из нескольких:
    {"idx","total","label","siblings":[…],"ctx":<пункт куратора дословно>,"missing":[(имя,почему)]}.
    Заголовок называет операцию и её номер из N, служебные строки — область «да», соседей,
    нехватку (частичный развод, см. `_curator_human_name_missing`) и контекст. ПОДПИСЬ
    `_HUMAN_SIGN` НЕ ТРОГАЕМ (фикс 3a95df7 обещает исход — это остаётся): область «да» сужена
    ОТДЕЛЬНОЙ строкой, а не переписыванием обещания.
    `missing` РЕЖЕТСЯ ПОСЛЕДНИМ (а точнее — не режется вовсе): в порядке урезки первым идёт
    справка-контекст, затем пункты; строка о нехватке — не справка, а единственное место, где
    владелец узнаёт, что список перед ним неполон.

    ПОДПИСЬ ОБЯЗАНА СКАЗАТЬ, ЧТО БУДЕТ ПОСЛЕ «ДА» (класс карточек 95/100, 31.07.2026): ✅ не
    «гасит строку», а СТАВИТ задачу на исполнение пунктов (_convert_curator_human_approved).
    Раньше подпись обещала «карточка закроется» — и владелец, разрешая операцию, получал ровно
    закрытие: одна кнопка означала то «принял к сведению», то «разрешаю действие», различить их
    было нельзя. Теперь исход назван ДО нажатия.
    В подписи НЕ употребляем токенов объекта (обратные кавычки, systemctl/clasp/git push/
    sqlite3): devbot._card_objects берёт объект сверки «да <объект>» из ТЕЛА карточки —
    служебный текст не должен подсовывать ему объект, которого владелец не просил.

    ТЕЛО РЕЖЕТСЯ ПОД ПОДПИСЬ, А НЕ ПОДПИСЬ ПОД ПОТОЛОК (04.08.2026, вторая ревизия класса —
    зеркало приёма `_stamp_self_origin` из замка происхождения). Подпись клеилась ПОСЛЕДНЕЙ, а
    итог резался `[:RESULT_MAX]` — и на длинной карточке владелец не видел ВООБЩЕ НИЧЕГО о том,
    что будет после ✅. Замер на живом пункте карточки 264: 8 пунктов — подпись есть, 12 —
    подписи нет (тело ровно 4500, хвост обрывается на полуслове). Куратор дописывает пункты в
    ОДНУ карточку `_curator_human_upsert`, так что двузначное число пунктов — не гипотеза.
    Теперь каркас (заголовок + подпись) кладётся ВСЕГДА, а не поместившиеся пункты честно
    названы числом: молча из карточки не исчезает ничего. Один пункт заведомо влезает — upsert
    режет его под CURATOR_TASK_MAX (400)."""
    items = list(items or [])
    if op:
        head = (f"🧑 нужно от владельца (цель {root}) — ОПЕРАЦИЯ {op['idx']} из {op['total']}, "
                f"каждая отдельной карточкой: {op['label']}")
    else:
        head = f"🧑 нужно от владельца (цель {root}) — сам куратор задач по этим пунктам НЕ ставит:"
    ctx = " ⏎ ".join(str((op or {}).get("ctx") or "").splitlines()).strip()
    keep, ctx_keep = len(items), len(ctx)
    while True:
        blocks = [_human_item_block(i, t, n) for i, (t, n) in enumerate(items[:keep], 1)]
        note = ("" if keep == len(items) else
                f"{_HUMAN_OVERFLOW} {len(items) - keep} — в карточку не поместились; полный "
                f"список /inbox, их дожимать отдельным «тз:».")
        tail = []
        if op:
            tail.append(_HUMAN_SCOPE)
            if op.get("siblings"):
                tail.append(_HUMAN_SIBL + "; ".join(op["siblings"]))
            if op.get("missing"):
                tail.append(_HUMAN_MISSING + "; ".join(
                    f"{lbl} — {str(why)[:_HUMAN_WHY_MAX]}" for lbl, why in op["missing"]))
            if ctx:
                tail.append(_HUMAN_CTX + ctx[:ctx_keep] + ("…" if ctx_keep < len(ctx) else ""))
        body = "\n".join([head] + blocks + ([note] if note else []) + tail + ["", _HUMAN_SIGN])
        if len(body) <= RESULT_MAX:
            return body
        # Режем СНАЧАЛА контекст (он справочный), и только потом пункты: пункт — то, за что
        # владелец жмёт «да», справка дешевле его.
        if ctx_keep > _HUMAN_CTX_MIN:
            ctx_keep = max(_HUMAN_CTX_MIN, ctx_keep - 500)
            continue
        if keep == 0:
            return body[:RESULT_MAX]
        keep -= 1


def _human_notclaim_line(demoted):
    """Строка-пометка «названо, но заявкой не сочтено» → приклеивается к пункту ПРОДОЛЖЕНИЕМ.

    Почему продолжением пункта, а не отдельной строкой карточки: карточка копит пункты разных
    консультаций (`_curator_human_upsert` перечитывает их из тела и рендерит заново), и пометка
    обязана держаться СВОЕГО пункта — иначе следующий пункт стёр бы её вместе с чужим контекстом.
    Продолжения разбор склеивает обратно (`_curator_human_items`), поэтому пометка доезжает и до
    ТЗ конверта: исполнитель прочитает, что это имя работой не является."""
    names = "; ".join(f"{d.get('label') or d.get('key')} — {d.get('why')}" for d in demoted)
    return _HUMAN_NOTCLAIM + names + _HUMAN_NOTCLAIM_TAIL


def _curator_human_upsert(root, item, demoted=None):
    """Ветка human (шаг 4/7 родитель 231): пункт → ЕДИНАЯ сводная карточка владельцу по цели root.
    Открытая (needs_approval) карточка [куратор владельцу цель root] уже есть → дописать пункт
    правкой её result (тот же текст → ×N, не дубль); нет → создать synthetic-задачу (образец
    _dec_post_summary: enqueue → claim → финализация, здесь финал = set_needs_approval, чтобы
    devbot унёс карточку в инбокс INBOX_TOPIC_ID). Пункт кладётся и в task_text новой карточки —
    упади демон между enqueue и set_needs_approval, сирота доводится в process_new БЕЗ потери
    пункта. Возврат (id, "created"|"edited"|"dedup") или None при ЛЮБОМ сбое — вызывающий код
    откатывается на прежнюю карточку-полотно в 328 (fail-safe, не хуже шага 2/7)."""
    try:
        item = str(item or "").strip()[:CURATOR_TASK_MAX] or "(куратор не уточнил)"
        if demoted:
            # Пометка клеится ПОСЛЕ урезки пункта (приём `_stamp_self_origin`): иначе потолок
            # съел бы саму пометку — то есть ровно то место, где сказано, что список неполон.
            item += "\n" + _human_notclaim_line(demoted)
        mark = f"[куратор владельцу цель {root}]"
        r = bc.get_pending("needs_approval")
        if not r.get("ok"):
            return None
        for it in r.get("items", []):
            if not str(it.get("task_text") or "").startswith(mark):
                continue
            tid, mode = it.get("id"), "edited"
            items = _curator_human_items(it.get("result"))
            for i, (t, n) in enumerate(items):
                if t == item:
                    items[i], mode = (t, n + 1), "dedup"
                    break
            else:
                items.append((item, 1))
            rr = bc.set_needs_approval(tid, _curator_human_render(root, items))
            return (tid, mode) if rr.get("ok") else None
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", f"{mark} {item}")
        if not r.get("ok"):
            return None
        sid = r.get("id")
        bc.claim_task(sid)    # даже если claim не прошёл — set_needs_approval финализирует
        rr = bc.set_needs_approval(sid, _curator_human_render(root, [(item, 1)]))
        return (sid, "created") if rr.get("ok") else None
    except Exception as e:
        log.warning("curator-human: upsert карточки владельцу (цель %s) упал (%s) — fail-safe",
                    root, e)
        return None


def _human_op_line(op):
    """Пункт операционной карточки: что именно разрешается. Литерал куратора приведён рядом —
    им же devbot._card_objects берёт объект для ответа «да <объект>», поэтому имя операции в
    карточке стоит В ТЕЛЕ (а не в подписи, где токенов объекта нет намеренно)."""
    lit = str(op.get("literal") or "").strip()
    line = op["label"] + (f" — в пункте куратора названо так: «{lit}»" if lit else "")
    return line[:CURATOR_TASK_MAX]


def _curator_human_name_missing(root, drawn, placed, refused):
    """ВТОРОЙ ПРОХОД частичного развода: вписать в КАЖДУЮ вставшую карточку, каких операций пункта
    карточки не досталось, и убрать эти операции из строки соседей.

    ЗАЧЕМ ВТОРОЙ ПРОХОД, А НЕ ПРАВИЛЬНЫЙ ПЕРВЫЙ. Отказ постановки виден ТОЛЬКО по факту попытки:
    первая карточка рендерится, когда о судьбе третьей ещё ничего не известно. Отозвать её потом
    нельзя (мост знает done|failed; закрытая строка оставит владельцу кнопку без задачи), значит
    единственная честная правка — досказать. Зовётся ТОЛЬКО при частичном разводе: полный развод
    идёт БАЙТ-В-БАЙТ прежним путём и ни одного лишнего запроса к мосту не делает.

    СОСЕДИ ПЕРЕСЧИТЫВАЮТСЯ ПО ФАКТУ: строка «рядом ждут» перечисляет только операции, у которых
    карточка действительно стоит. Иначе одна и та же операция значилась бы в карточке и
    «ожидающей рядом», и «оставшейся без карточки» — противоречие внутри одного тела хуже
    умолчания.

    Возврат — id карточек, вписать в которые НЕ удалось: они по-прежнему молчат о нехватке, и это
    называется в отчёте 328 громко (fail-safe: сбой дописи не отменяет уже вставших карточек)."""
    got = [lbl for _tid, lbl in placed]
    silent = []
    for tid, meta, items in drawn:
        m = dict(meta, missing=list(refused),
                 siblings=[x for x in got if x != meta["label"]])
        try:
            rr = bc.set_needs_approval(tid, _curator_human_render(root, items, m))
        except Exception as e:
            log.warning("curator-human: допись нехватки в карточку %s упала (%s)", tid, e)
            rr = {"ok": False}
        if not rr.get("ok"):
            silent.append(tid)
    return silent


def _curator_human_split(root, item, ops):
    """Пункт назвал НЕСКОЛЬКО операций → по карточке НА КАЖДУЮ (класс 251/254/257, 05.08.2026).

    КЛАСС. Карточки 251 и 254 просили под одним «да» деплой моста И две правки живых данных, 257 —
    деплой И пробу правки. Владелец отказал 251 и 254 целиком, и правильно: правило «одна карточка
    = одна операция» у карточек гарда закрыто, а здесь операции разного веса стояли одним списком.
    Цена отказа — вся готовая работа пункта (по 251 и 254 её собирали заново). Теперь каждая
    операция ждёт своего «да» отдельно: отказ по деплою больше не убивает разрешение на правку.

    ЧТО ИМЕННО РАЗВОДИТСЯ. Единица — СЕМЬЯ операции (`curator_ops.operations`): `clasp push` и
    `clasp redeploy` одного пункта = ОДИН выкат моста (штатный цикл), а рестарт splinter и рестарт
    orchestrator-daemon = ДВЕ карточки (разные объекты, разный вес). Текст пункта едет с каждой
    карточкой ДОСЛОВНО контекстом — режется список операций, а не смысл.

    ДЕДУП RESTART-PROOF: маркер несёт КЛЮЧ семьи, поэтому повтор той же операции той же цели даёт
    ×N на своей карточке, а не второй дубль (тот же образец, что у `_curator_human_upsert`).

    FAIL-SAFE: очередь не опросить, либо НИ ОДНОЙ карточки поставить не удалось → None, и
    вызывающий код откатывается на прежний путь (общая карточка) — не хуже сегодняшнего.

    ЧАСТИЧНЫЙ РАЗВОД ВИДЕН ВЛАДЕЛЬЦУ (класс 05.08.2026). Часть карточек встала, часть нет →
    возвращаем что встало, НЕвставшие операции названы в отчёте в 328 (образец
    `_curator_spawn.refused`) И — главное — В САМИХ КАРТОЧКАХ ИНБОКСА
    (`_curator_human_name_missing`): владелец решает по карточкам, а не по отчёту в 328, и до
    правки карточка вдобавок выдавала операции без карточки за ожидающие рядом. Молча не теряется
    ни одна операция, а если и допись не прошла — отчёт называет карточки, которые молчат.
    Возврат (ids_str, "split", note) | None."""
    try:
        ctx = str(item or "").strip()
        try:
            r = bc.get_pending("needs_approval")
            open_items = r.get("items", []) if r.get("ok") else None
        except Exception:
            open_items = None
        if open_items is None:
            return None              # дедуп не доказать — вторых карточек не плодим
        labels = [o["label"] for o in ops]
        placed, refused, drawn = [], [], []
        for i, o in enumerate(ops, 1):
            line = _human_op_line(o)
            mark = f"[куратор владельцу цель {root}, операция {o['key']}]"
            meta = {"idx": i, "total": len(ops), "label": o["label"], "ctx": ctx,
                    "siblings": [x for j, x in enumerate(labels, 1) if j != i]}
            found = next((it for it in open_items
                          if str(it.get("task_text") or "").startswith(mark)), None)
            if found is not None:
                tid = found.get("id")
                items = _curator_human_items(found.get("result")) or [(line, 1)]
                for k, (t, n) in enumerate(items):
                    if t == line:
                        items[k] = (t, n + 1)
                        break
                else:
                    items.append((line, 1))
                rr = bc.set_needs_approval(tid, _curator_human_render(root, items, meta))
                if rr.get("ok"):
                    placed.append((tid, o["label"]))
                    drawn.append((tid, meta, items))   # чем отрендерена — для дописи нехватки
                else:
                    refused.append((o["label"], "правка карточки не прошла"))
                continue
            rq = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", f"{mark} {line}")
            if not rq.get("ok"):
                refused.append((o["label"], f"enqueue не прошёл ({rq.get('error')})"))
                continue
            sid = rq.get("id")
            bc.claim_task(sid)     # даже если claim не прошёл — set_needs_approval финализирует
            rr = bc.set_needs_approval(sid, _curator_human_render(root, [(line, 1)], meta))
            if rr.get("ok"):
                placed.append((sid, o["label"]))
                drawn.append((sid, meta, [(line, 1)]))
            else:
                refused.append((o["label"], "карточка не встала в needs_approval"))
        if not placed:
            return None              # ни одной карточки — откат на прежний путь, «да» не теряем
        note = ""
        if refused:
            silent = _curator_human_name_missing(root, drawn, placed, refused)
            note = ("операции БЕЗ карточки (дожать «тз:» руками): "
                    + "; ".join(f"{lbl} — {why}" for lbl, why in refused))
            note += ("; " + _NOTE_TOLD) if not silent else (
                "; ВПИСАТЬ это в карточки " + ", ".join(str(t) for t in silent)
                + " НЕ удалось — они " + _NOTE_SILENT)
        return (", ".join(str(i) for i, _l in placed), "split", note)
    except Exception as e:
        log.warning("curator-human: развод пункта по операциям (цель %s) упал (%s) — fail-safe",
                    root, e)
        return None


def _curator_human_place(root, item):
    """Точка входа ветки human: пункт с ДВУМЯ и более названными операциями разводится по
    карточкам, всё прочее идёт прежним путём БАЙТ-В-БАЙТ.

    ПОЧЕМУ ПОРОГ ДВА, А НЕ ОДИН. Замер живого корпуса (19 сводных карточек за 14 суток, 28.07–
    05.08): больше одной операции несли 4 (251, 254, 257, 264), ровно одну — 10, ни одной — 5.
    На одной операции карточка и сегодня одна, так что порог 1 не изменил бы НИЧЕГО, кроме
    заголовка — и заодно переименовал бы в «операционные» те карточки, где операция лишь упомянута
    (карточка 226 перечисляет рестарт splinter как пункт ПРОЕКТА, а не как просьбу). Порог два
    берёт ровно тот класс, ради которого правка и делается, и не трогает остальное.
    ТИП ПУНКТА НЕ УГАДЫВАЕМ по-прежнему: считается не «просьба это или сводка», а сколько РАЗНЫХ
    операций названо — факт, а не намерение.

    ИМЯ ПОД ОТРИЦАНИЕМ ЗАЯВКОЙ НЕ ЯВЛЯЕТСЯ (класс карточек 349/357/358, 06.08.2026). Развод считал
    операцию по СОВПАДЕНИЮ ИМЕНИ и вытащил splinter из фразы «splinter НЕ трогаем» (цель 344), а
    следом оба имени — из описания вариантов выбора (цель 355): три фантомные карточки из четырёх,
    что развод выписал за всю свою жизнь, все три отклонены кнопкой. Теперь позицию вхождения судит
    `curator_claim`, и ЛЮБАЯ демотировка отменяет РАЗВОД целиком: пункт едет владельцу одной
    карточкой, ровно как до 05.08, а карточка НАЗЫВАЕТ демотированное имя.
    ПОЧЕМУ РАЗВОД ОТМЕНЯЕТСЯ ЦЕЛИКОМ, а не «делим оставшееся». Разведённая карточка утверждает
    «соседи ждут своих «да» отдельными карточками» — если демотировка ошиблась, это утверждение
    станет ложью, и владелец подтвердит неполный список, считая его полным (тот самый класс, ради
    которого заведён `_HUMAN_MISSING`). Отмена развода такой лжи родить не может физически: под
    одной кнопкой лежит весь пункт. Цена — гранулярность; замер живого корпуса: случаев
    «демотировано И осталось ≥2 заявок» за 7 суток НОЛЬ.
    FAIL-SAFE: любое исключение в разборе или в позиции — прежний путь БАЙТ-В-БАЙТ."""
    try:
        occs = curator_ops.occurrences(item)
        kept_occs, demoted = curator_claim.filter_claims(item, occs)
        ops = curator_ops.dedup(kept_occs)
    except Exception as e:
        log.warning("curator-human: разбор пункта на операции упал (%s) — прежний путь", e)
        ops, demoted = [], []
    if demoted:
        log.info("curator-human: в пункте цели %s имена %s заявкой не сочтены (%s) — развода нет, "
                 "пункт владельцу целиком", root,
                 ", ".join(d["key"] for d in demoted),
                 "; ".join(sorted({d["why"] for d in demoted})))
        res = _curator_human_upsert(root, item, demoted)
        if res is None:
            return None
        return (res[0], res[1],
                "имена, названные в пункте, но заявкой НЕ сочтённые (карточек на них нет): "
                + "; ".join(f"{d['label']} — {d['why']}" for d in demoted)
                + " — развод пункта по операциям поэтому не выполнялся")
    if len(ops) >= 2:
        res = _curator_human_split(root, item, ops)
        if res is not None:
            log.info("curator-human: пункт цели %s разведён по %d операциям (%s) → карточки %s",
                     root, len(ops), ", ".join(o["key"] for o in ops), res[0])
            return res
        log.warning("curator-human: развести пункт цели %s по %d операциям не вышло — "
                    "прежний путь (общая карточка)", root, len(ops))
    return _curator_human_upsert(root, item)


def _curator_card_text(kind, key, v, spawn=None, hum=None):
    """Тело карточки-сигнала куратора для 328 (result synthetic-задачи). followup — отчёт о
    поставленных продолжениях и/или почему не поставлены (бюджет/сбой); human — отчёт, куда
    ушёл пункт (сводная карточка владельцу, шаг 4/7) либо сам пункт при сбое upsert."""
    reason = v.get("reason") or "(без причины)"
    if v["verdict"] == "human":
        lines = [f"🧭 куратор: цель ({kind} {key}) требует владельца — задачи НЕ ставятся.",
                 f"что нужно: {v.get('human') or '(куратор не уточнил)'}",
                 f"причина: {reason}"]
        if hum:
            word = {"split": "пункт РАЗВЕДЁН по отдельным карточкам — по одной на операцию",
                    "created": "создана сводная карточка владельцу",
                    "edited": "пункт добавлен в сводную карточку владельцу",
                    "dedup": "пункт уже был в сводной карточке владельцу (счётчик ×N)"}[hum[1]]
            noun = "задачи" if hum[1] == "split" else "задача"
            lines.append(f"🧑 {word} ({noun} {hum[0]}, инбокс).")
            if len(hum) > 2 and hum[2]:
                lines.append(f"⚠️ {hum[2]}")
        else:
            lines.append("🧑 сводная карточка владельцу НЕ встала (сбой очереди) — "
                         "пункт только в этой карточке.")
        return "\n".join(lines)[:RESULT_MAX]
    sp = spawn or {"root": key, "placed": [],
                   "refused": [(t, "постановка не выполнялась") for t in v["tasks"]]}
    lines = [f"🧭 куратор: цель ({kind} {key}) НЕ закрыта — остались зелёные хвосты.",
             f"причина: {reason}"]
    if sp["placed"]:
        lines.append(f"поставлены продолжения (from={CURATOR_FROM}, корень {sp['root']}):")
        lines += [f"{i}. задача id {pid}: {t}" for i, (pid, t) in enumerate(sp["placed"], 1)]
    if sp["refused"]:
        lines.append("НЕ поставлено (дожать можно «тз:» из списка):")
        lines += [f"- {t} — {why}" for t, why in sp["refused"]]
    return "\n".join(lines)[:RESULT_MAX]


def _maybe_curator(kind, key, goal, result):
    """Консультация куратора на терминале (kind=задача|родитель, key=id очереди). CURATOR=0 →
    ноль вызовов; дедуп — ровно одна консультация на терминал; closed/сбой → тишина;
    followup → постановка продолжений (_curator_spawn, бюджеты из маркеров) + карточка-отчёт;
    human → карточка «требует владельца». Куратор — слой-надстройка: ЛЮБОЕ исключение ловится,
    боевой финал задачи он не валит и не меняет."""
    try:
        if not _curator_on():
            return
        k = (kind, int(key))
        if k in _curated:
            return
        if _curator_card_exists(kind, key):
            _curated.add(k)
            return
        _curated.add(k)           # попытка потрачена независимо от исхода — одна на терминал
        v = _curator_consult(goal, result)
        if v is None or v["verdict"] == "closed":
            log.info("curator: %s %s → %s (тишина)", kind, key,
                     v["verdict"] if v else "сбой думателя")
            return
        # Дедуп followup-проверок (программный фильтр поверх промпт-инъекции):
        # предложенные задачи, дублирующие недавние done (DEDUP_WINDOW) → refused+note.
        # Deploy-контекст → пропуск дедупа (_followup_dedup проверяет сам).
        pre_refused = []
        if v["verdict"] == "followup":
            remaining, pre_refused = _followup_dedup(v["tasks"], goal, result)
            if not remaining:
                log.info("curator: %s %s followup→closed (все %d задач дедуплицированы окном %ss)",
                         kind, key, len(pre_refused), DEDUP_WINDOW)
                return
            if pre_refused:
                v = dict(v, tasks=remaining)
                log.info("curator: %s %s %d/%d followup-задач дедуплицированы (окно %ss)",
                         kind, key, len(pre_refused), len(pre_refused) + len(remaining), DEDUP_WINDOW)
        # Карточка-маркер дедупа встаёт ПЕРВОЙ, продолжения ставятся МЕЖДУ её enqueue и
        # complete: упади демон посреди — сирота доводится (process_new), консультация не
        # повторяется, продолжения не задваиваются.
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}",
                            f"[куратор {kind} {key}] вердикт куратора")
        if not r.get("ok"):
            log.warning("curator: карточка по %s %s не встала в очередь (%s)",
                        kind, key, r.get("error"))
            return
        sid = r.get("id")
        bc.claim_task(sid)        # даже если claim не прошёл — complete финализирует
        spawn = _curator_spawn(kind, key, goal, v["tasks"]) if v["verdict"] == "followup" else None
        if spawn and pre_refused:
            spawn = dict(spawn, refused=spawn["refused"] + pre_refused)
        hum = None
        if v["verdict"] == "human":
            # ветка human (шаг 4/7): задач НЕ ставим — пункт в сводную карточку владельцу
            # по КОРНЮ цели (продолжения того же корня копятся в ту же карточку)
            hum = _curator_human_place(_curator_root_depth(kind, key, goal)[0],
                                       v.get("human") or v.get("reason"))
        cm = bc.complete_task(sid, "done", _curator_card_text(kind, key, v, spawn, hum))
        log.info("curator: %s %s → %s, карточка задачей %s (bridge_ok=%s, продолжений=%s, hum=%s)",
                 kind, key, v["verdict"], sid, cm.get("ok"),
                 len(spawn["placed"]) if spawn else 0, hum and hum[1])
    except Exception as e:
        log.warning("curator: сбой консультации по %s %s (%s) — fail-safe тишина", kind, key, e)


def _maybe_curator_single(frm, tid, text, result, status="done", force_consult=False):
    """Куратор на финале done/failed ОДИНОЧКИ «тз:»/«задача:» vps-полосы (from=Filipp-328[-dev]
    строго — артефакты декомпозиции/операций/pc сюда не проходят) и followup-задачи куратора
    (from=Filipp-curator — её терминал даёт вторую глубину дожима; третью глушит бюджет глубины
    в _curator_spawn). Зовётся из process_new ПОСЛЕ complete_task — финал уже записан, куратор
    его не трогает. force_consult=True — bypass CURATOR_SCOPE-фильтра (для ⚠️ unverified задач)."""
    if str(frm or "") not in ("Filipp-328", "Filipp-328" + DEV_FROM_SUFFIX, CURATOR_FROM):
        return                    # dec-семейство (куратор цепи зовётся на сводке), pc, op и прочее
    if _is_convert(text):
        return                    # конверт одобренной заявки — вне кураторского контура
    if str(result or "").lstrip().startswith(_CURATOR_SKIP_MARKS):
        return                    # ⏱-диагноз / плановый рестарт-🔁 / отклонено Филиппом
    # CURATOR_SCOPE=1: done-одиночки без коммита в result → мимо куратора (read-only разведки).
    # force_consult=True (⚠️ unverified dev-задача) обходит этот фильтр — куратор всегда нужен.
    if not force_consult and _curator_scope_on() and status == "done" and not _result_has_commit(result):
        return
    _maybe_curator("задача", tid, text, result)


def _maybe_curator_chain(pid, summary):
    """Куратор после сводки родителя vps-цепи декомпозера (зовётся из _dec_post_summary — сводка
    уже в очереди). Цель = task_text родителя (дословно из done), итог = текст сводки. МИМО:
    цепь с ⏱-диагнозом или «отклонено Филиппом» в шагах (первые строки шагов видны в сводке)."""
    if not _curator_on():
        return
    s = str(summary or "")
    if TIMEOUT_MARK in s or _REJECT_PREFIX in s:
        return
    goal, _plan = _dec_parent_context(pid)
    _maybe_curator("родитель", pid, goal, summary)


# === ПК-ТЕАТР: функции (кусок 2 «один дирижёр, два театра», 07.07.2026) ===
# Мозг (планировщик, думатели самопочинки/адаптации) живёт ТОЛЬКО здесь, на VPS; ПК-агент
# (pc_orchestrator) — второй театр ИСПОЛНЕНИЯ шагов (claim lane=pc + headless CC, без мозга).
# КЛЮЧЕВОЕ ОТЛИЧИЕ от vps-цепи: guard последовательности vps-цепи живёт в НАШЕМ process_new —
# у ПК-агента такого guard'а нет (он claim'ит FIFO всё подряд). Веерный fan-out дал бы гонку:
# после провала шага i ПК взял бы шаг i+1 раньше, чем мы его пропустим (halt-on-fail дырявый),
# а перерождение самопочинки (id выше) исполнилось бы ПОСЛЕ следующих шагов. Поэтому шаги
# релизятся ПО ОДНОМУ: в очереди lane=pc живёт максимум один шаг цепи, следующий встаёт только
# после done предыдущего (+ адаптация). Состояние цепи restart-proof — целиком из очереди:
# план = нумерованный список в result родителя, коррекции = карточки «[коррекция плана родитель N]»
# с нумерованным остатком плана в result, прогресс = сами pc-шаги. Память процесса — только
# дедуп-кэши (_summarized, _pc_adapted); после рестарта демона цепь продолжается с того же места.
# ИЗОЛЯЦИЯ ПОЛОС НЕ ОСЛАБЛЕНА: читаем ТОЛЬКО шаги СВОИХ родителей (from=PC_DEC_FROM + [шаг i/N]);
# одиночные pc-задачи (Filipp-pc / Filipp-pc-dev) не трогаем; claim чужой полосы НЕ делаем
# (complete_task на своих шагах = финализация собственной цепи, как в vps-потоке).
# ТАЙМАУТ: ПК может быть выключен → шаг висит (new не взят / in_progress без heartbeat /
# approved не доведён) дольше PC_STEP_TIMEOUT → честный failed с диагнозом «ПК-театр не
# отвечает» + halt цепи; думатель такое НЕ чинит (переформулировка не включит ПК).
_PC_CARD_RE = re.compile(r"^\[карточка родитель (\d+)\]")
_PC_ADAPT_BASE_RE = re.compile(r"после шага (\d+)")
_PC_STATUSES = ("new", "in_progress", "needs_approval", "approved", "done", "failed")
_pc_adapted = set()           # (pid, step_i), по которым думатель адаптации уже спрошен (память
                              # процесса — рестарт даст максимум один лишний keep-вопрос)


def _age_sec(updated_iso):
    """Возраст updated задачи в секундах. None при ошибке разбора → таймаут НЕ объявляем
    (лучше подождать цикл, чем убить живой шаг из-за парсинга; зеркало devbot._task_age_sec)."""
    try:
        s = str(updated_iso).replace("Z", "+00:00")
        t = datetime.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None


def _pc_enqueue(text):
    """Шаг цепи в очередь полосы pc (from=PC_DEC_FROM, lane=pc). Мок без lane-kwarg (легаси-тесты
    сюда не заходят, страховка) → обычный enqueue."""
    try:
        return bc.enqueue_task(PC_DEC_FROM, text, lane=PC_LANE)
    except TypeError:
        return bc.enqueue_task(PC_DEC_FROM, text)


def _pc_fetch_items():
    """Все задачи полосы pc по статусам _PC_STATUSES → список items (у каждого есть status)
    | None (ошибка чтения → пропустить цикл целиком: частичная картина опаснее ожидания).
    Один CSV-вызов get_pending_multi, фоллбэк — по-статусно; мок без lane-kwarg → без lane
    (фильтр по from=PC_DEC_FROM ниже отсеивает чужое)."""
    fn = getattr(bc, "get_pending_multi", None)
    if fn is not None:
        try:
            r = fn(_PC_STATUSES, lane=PC_LANE)
        except TypeError:
            r = fn(_PC_STATUSES)
        if not r.get("ok"):
            return None
        return [it for it in r.get("items", []) if isinstance(it, dict)]
    items = []
    for st in _PC_STATUSES:
        try:
            rr = bc.get_pending(st, lane=PC_LANE)
        except TypeError:
            rr = bc.get_pending(st)
        if not rr.get("ok"):
            return None
        for it in rr.get("items", []):
            if isinstance(it, dict):
                it.setdefault("status", st)
                items.append(it)
    return items


def _pc_group_chains(items):
    """items полосы pc → {pid: [(step_i, step_n, item), …]} ТОЛЬКО своих цепей
    (from=PC_DEC_FROM + паттерн шага). Одиночные pc-задачи (Filipp-pc[-dev]) не попадают."""
    chains = {}
    for it in items:
        if str(it.get("from") or "") != PC_DEC_FROM:
            continue
        m = _STEP_RE.match(str(it.get("task_text") or ""))
        if m:
            chains.setdefault(int(m.group(3)), []).append(
                (int(m.group(1)), int(m.group(2)), it))
    return chains


def _pc_chain_steps(pid):
    """Шаги цепи родителя pid с полосы pc (для осиротевшей сводки). Ошибка чтения → []."""
    items = _pc_fetch_items()
    return (_pc_group_chains(items).get(int(pid)) or []) if items is not None else []


def _pc_post_card(pid, text):
    """Событийная карточка цепи ПК-театра (🩹 retry / 🛑 terminal / halt-диагноз) в тему PC-дев
    synthetic-задачей (enqueue vps → claim → done): очередь — единственный канал демона наружу,
    devbot принесёт done-рапортом (from=PC_DEC_FROM → тема 829)."""
    r = bc.enqueue_task(PC_DEC_FROM, f"[карточка родитель {pid}] событие цепи ПК-театра")
    if not r.get("ok"):
        log.warning("pc-dec: карточка родителя %s не встала в очередь (%s)", pid, r.get("error"))
        return
    sid = r.get("id")
    bc.claim_task(sid)                    # даже если claim не прошёл — complete финализирует
    bc.complete_task(sid, "done", str(text)[:RESULT_MAX])


def _pc_summary_text(pid, steps):
    """Сводка цепи ПК-театра из переданных шагов (зеркало _dec_summary_text, но по снапшоту
    pc-шагов — vps-читалка _dec_siblings их не видит). Дубли номера (провал+перерождение) —
    последняя запись по id."""
    rows = sorted([s for s in steps if str(s[2].get("status")) in ("done", "failed")],
                  key=lambda x: (x[0], int(x[2].get("id") or 0)))
    last = {}
    for i, n, it in rows:
        last[i] = (i, n, it)
    rows = [last[k] for k in sorted(last)]
    if not rows:
        return f"🧩 Сводка декомпозиции (родитель {pid}, театр PC): шагов не найдено (очередь пуста?)"
    n_done = sum(1 for _i, _n, it in rows if str(it.get("status")) == "done")
    total = rows[-1][1]   # маркер последнего релизнутого шага несёт актуальный итог плана
    head = f"🧩 Сводка декомпозиции (родитель {pid}, театр PC): {n_done}/{total} шагов done"
    fin = _adapt_finish.get(pid)
    if fin:
        head += f", 🏁 завершено досрочно: {fin}"
    elif n_done < len(rows):
        head += ", есть упавшие/пропущенные"
    lines = [head]
    for i, n, it in rows:
        emoji = "✅" if str(it.get("status")) == "done" else "❌"
        first = (str(it.get("result") or "").strip().splitlines() or ["(пусто)"])[0]
        lines.append(f"{emoji} шаг {i}/{n}: {first[:400]}")
    return "\n".join(lines)[:RESULT_MAX]


def _pc_post_summary(pid, steps):
    """Финал цепи ПК-театра → сводка в тему PC-дев (synthetic done, как _dec_post_summary).
    Идемпотентно: _summarized + скан существующих сводок (_dec_summary_exists — сводка лежит
    на полосе vps, читалка её видит)."""
    if pid in _summarized:
        return
    if _dec_summary_exists(pid):
        _summarized.add(pid)
        return
    text = _pc_summary_text(pid, steps)
    r = bc.enqueue_task(PC_DEC_FROM, f"[сводка родитель {pid}] сводный отчёт по шагам")
    if not r.get("ok"):
        log.warning("pc-dec: сводка родителя %s не встала в очередь (%s)", pid, r.get("error"))
        return
    sid = r.get("id")
    bc.claim_task(sid)
    cm = bc.complete_task(sid, "done", text)
    _summarized.add(pid)
    _adapt_finish.pop(pid, None)          # выгрузка: adapt_reason больше не нужен после сводки
    log.info("pc-dec: сводка родителя %s → задача %s (bridge_ok=%s)", pid, sid, cm.get("ok"))


def _parse_numbered(text):
    """Нумерованные строки «N. <текст>» → {N: <текст>} (для восстановления плана из result
    родителя / карточки коррекции). Прочие строки игнорируются."""
    out = {}
    for line in (text or "").splitlines():
        m = _PLAN_LINE_RE.match(line)
        if m:
            out[int(m.group(1))] = m.group(2).strip()
    return out


def _pc_current_plan(pid):
    """ТЕКУЩИЙ план цепи ПК-театра, restart-proof из очереди (полоса vps, где лежат родитель и
    карточки): план родителя (нумерованный список в result) + коррекции «[коррекция плана
    родитель pid] после шага B…» (нумерованный остаток в result) поверх, в порядке id.
    → (plan: {номер: (текст, K-происхождение; 0=исходный)}, K всего коррекций, база последней
    коррекции | None). Ошибка чтения / родитель не найден → ({}, 0, None) — вызывающий даст
    честный halt-диагноз, не гадаем."""
    try:
        r = bc.get_pending("done")
    except Exception as e:
        log.warning("pc-dec: план родителя %s не прочитан (%s)", pid, e)
        return {}, 0, None
    if not r.get("ok"):
        return {}, 0, None
    parent_result, cards = "", []
    for it in r.get("items", []):
        if int(it.get("id") or 0) == int(pid):
            parent_result = str(it.get("result") or "")
        m = _ADAPT_CARD_RE.match(str(it.get("task_text") or ""))
        if m and int(m.group(1)) == int(pid):
            cards.append(it)
    plan = {num: (txt, 0) for num, txt in _parse_numbered(parent_result).items()}
    last_base = None
    cards.sort(key=lambda x: int(x.get("id") or 0))
    for k, card in enumerate(cards, 1):
        bm = _PC_ADAPT_BASE_RE.search(str(card.get("task_text") or ""))
        nums = _parse_numbered(str(card.get("result") or ""))
        if not bm or not nums:
            continue          # осиротевшая/пустая коррекция — план не меняла (fail-safe keep)
        base = int(bm.group(1))
        plan = {num: v for num, v in plan.items() if num <= base}
        plan.update({num: (txt, k) for num, txt in nums.items()})
        last_base = base
    return plan, len(cards), last_base


def _pc_release(pid, j, total, text, k=0):
    """Релиз шага j/total цепи pid на полосу pc (следующий шаг встаёт ТОЛЬКО после done
    предыдущего). k>0 → шаг из коррекции плана (маркер для restart-proof счётчика/глаз).
    Возврат: ok-флаг."""
    mark = f"[коррекция плана {k}] " if k else ""
    r = _pc_enqueue(f"[шаг {j}/{total} родитель {pid}] {mark}{text}"[:RESULT_MAX])
    if not r.get("ok"):
        log.warning("pc-dec: релиз шага %s/%s родителя %s не встал (%s) — повтор следующим циклом",
                    j, total, pid, r.get("error"))
        return False
    log.info("pc-dec: шаг %s/%s родителя %s релизнут (id %s, lane=pc)", j, total, pid, r.get("id"))
    return True


def _pc_adapt_consult(pid, step_i, steps, remaining):
    """Думатель адаптации для цепи ПК-театра — ТА ЖЕ схема, что _adapt_consult (ADAPT_PREAMBLE,
    кондуктор, --max-turns 1, строгий JSON), но сделанное берём из pc-шагов снапшота, а
    оставшееся — из восстановленного плана (в очереди lane=pc его нет — шаги релизятся по одному).
    None = fail-safe keep."""
    goal, plan_txt = _dec_parent_context(pid)
    done_last = {}
    for i, _n, it in sorted([s for s in steps if str(s[2].get("status")) == "done"],
                            key=lambda x: (x[0], int(x[2].get("id") or 0))):
        done_last[i] = str(it.get("result") or "").strip()
    done_lines = [f"шаг {i}: {(done_last[i].splitlines() or ['(пусто)'])[0][:300]}"
                  for i in sorted(done_last)] or ["(результатов пока нет)"]
    rem_lines = [f"шаг {j}: {t[:400]}" for j, t in remaining]
    prompt = (ADAPT_PREAMBLE +
              f"ИСХОДНАЯ ЦЕЛЬ РОДИТЕЛЯ (дословно):\n{goal}\n\n"
              f"ИСХОДНЫЙ ПЛАН ШАГОВ:\n{plan_txt}\n\n"
              f"РЕЗУЛЬТАТЫ СДЕЛАННЫХ ШАГОВ (сжато; только что завершён шаг {step_i}):\n"
              + "\n".join(done_lines) + "\n\n"
              "ОСТАВШИЕСЯ ШАГИ ПЛАНА:\n" + "\n".join(rem_lines) + "\n")
    out = _thinker_exec(prompt, PLAN_ADAPT_TIMEOUT, "pc-plan-adapt")
    if out is None:
        return None
    v = _parse_adapt_json(out)
    if v is None:
        log.warning("pc-plan-adapt: ответ думателя не распарсился/пуст (fail-safe keep): %.200s", out)
    return v


def _pc_after_fail(pid, i, n, it, steps):
    """Провал pc-шага (финализирован ПК-агентом/devbot'ом/таймаутом — уже failed в очереди).
    Отказ Филиппа / молчание ПК → halt без думателя; перерождение упало повторно → терминальный
    halt; иначе при STEP_SELFHEAL=1 → ТОТ ЖЕ думатель самопочинки, РОВНО 1 перерождение lane=pc.
    Halt в sequential-модели = просто НЕ релизить дальше + сводка (пропускать нечего)."""
    text = str(it.get("task_text") or "")
    fail_text = str(it.get("result") or "")
    if fail_text.lstrip().startswith(_REJECT_PREFIX) or PC_SILENT_MARK in fail_text:
        _pc_post_summary(pid, steps)          # человек сказал «нет» / ПК молчал — чинить нечего
        return
    if _HEAL_RE.search(text):
        _pc_post_card(pid, f"🛑 самопочинка не помогла (попытка 1 исчерпана): шаг {i}/{n} "
                           f"родителя {pid} упал повторно — цепочка остановлена, нужен человек.\n"
                           f"{fail_text[:400]}")
        _pc_post_summary(pid, steps)
        return
    if not _selfheal_on():
        _pc_post_summary(pid, steps)          # прежний halt-on-fail (провал уже отрапортован ❌)
        return
    verdict = _selfheal_consult(pid, i, n, text, fail_text)
    if verdict is None or verdict["verdict"] != "retry" or not verdict["fixed_step"]:
        reason = (verdict or {}).get("reason") or "(сбой думателя — fail-safe halt)"
        _pc_post_card(pid, f"шаг {i}/{n} упал → думатель: halt, причина: {reason}\n"
                           f"Цепочка остановлена (диагноз думателя выше).")
        _pc_post_summary(pid, steps)
        return
    fixed, reason = verdict["fixed_step"], verdict["reason"] or "(без причины)"
    r = _pc_enqueue((f"[шаг {i}/{n} родитель {pid}] "
                     f"[самопочинка шага {i}, попытка 1] {fixed}")[:RESULT_MAX])
    if not r.get("ok"):
        log.warning("pc-dec: перерождение шага %s родителя %s не встало (%s) — fail-safe halt",
                    i, pid, r.get("error"))
        _pc_post_summary(pid, steps)          # как vps: очередь не приняла → halt
        return
    _pc_post_card(pid, f"🩹 шаг {i}/{n} упал → думатель: retry, правка: {fixed[:200]}, "
                       f"причина: {reason[:200]}\n"
                       f"Перерождён задачей id {r.get('id')} (lane=pc; попытка 1 из 1; повторный "
                       f"провал = терминальный halt).\nИсходный провал: {fail_text[:400]}")
    log.info("pc-dec: шаг %s/%s родителя %s перерождён задачей %s (retry)", i, n, pid, r.get("id"))


def _pc_after_done(pid, i, n, it, steps):
    """Done pc-шага: последний по плану → сводка; иначе ТА ЖЕ адаптация плана (PLAN_ADAPT):
    keep → релиз следующего шага; adjust → карточка коррекции (restart-proof план в result)
    + релиз первого скорректированного (≤PLAN_ADAPT_MAX коррекций, дальше halt «план дрейфует»);
    finish → сводка «завершено досрочно». Любой сбой думателя = keep."""
    plan, k_cnt, last_base = _pc_current_plan(pid)
    total = max(plan) if plan else n
    if i >= total:
        _pc_post_summary(pid, steps)
        return
    if plan.get(i + 1) is None:
        _pc_post_card(pid, f"⚠️ план родителя {pid} не восстановился из очереди (шаг {i + 1} "
                           f"не найден в result родителя/коррекций) — цепочка остановлена, "
                           f"поставь «декомпозируй:» заново.")
        _pc_post_summary(pid, steps)
        return
    consult = (_plan_adapt_on() and last_base != i and (pid, i) not in _pc_adapted)
    if consult:
        _pc_adapted.add((pid, i))
        remaining = [(j, plan[j][0]) for j in sorted(plan) if j > i]
        verdict = _pc_adapt_consult(pid, i, steps, remaining)
        if verdict is not None and verdict["verdict"] == "finish":
            reason = (verdict["reason"] or "(без причины)")[:300]
            _adapt_finish[pid] = reason
            _pc_post_card(pid, f"🏁 после шага {i} думатель решил: цель родителя {pid} достигнута "
                               f"досрочно ({reason}) — оставшиеся шаги {i + 1}–{total} не релизятся.")
            _pc_post_summary(pid, steps)
            log.info("pc-plan-adapt: родитель %s finish после шага %s (%s)", pid, i, reason[:120])
            return
        if verdict is not None and verdict["verdict"] == "adjust":
            new_steps = verdict["adjusted_steps"]
            reason = (verdict["reason"] or "(без причины)")[:300]
            k = k_cnt + 1
            if k > PLAN_ADAPT_MAX:
                _pc_post_card(pid, f"🛑 план дрейфует: думатель запросил коррекцию №{k} (лимит "
                                   f"{PLAN_ADAPT_MAX} на цепь) — цепочка остановлена, нужен "
                                   f"владелец. Диагноз думателя: {reason}")
                _pc_post_summary(pid, steps)
                log.info("pc-plan-adapt: родитель %s — adjust №%s (> лимита %s) → halt (дрейф)",
                         pid, k, PLAN_ADAPT_MAX)
                return
            if i + len(new_steps) > MAX_STEPS:
                log.warning("pc-plan-adapt: родитель %s adjust дал %s шагов (итог > потолка %s) "
                            "— fail-safe keep", pid, len(new_steps), MAX_STEPS)
            else:
                new_total = i + len(new_steps)
                numbered = "\n".join(f"{j}. {s}" for j, s in enumerate(new_steps, start=i + 1))
                card = (f"🧭 после шага {i} думатель скорректировал план (коррекция "
                        f"{k}/{PLAN_ADAPT_MAX}): {reason}\n"
                        f"НОВЫЙ ОСТАВШИЙСЯ ПЛАН (шаги {i + 1}–{new_total}, релизятся по одному):\n"
                        f"{numbered}\n"
                        f"Итог плана {new_total} шагов; сделанные шаги 1–{i} не тронуты. "
                        f"Третья коррекция = halt «план дрейфует».")
                cr = bc.enqueue_task(PC_DEC_FROM,
                                     f"[коррекция плана родитель {pid}] после шага {i} (K={k})")
                if cr.get("ok"):
                    bc.claim_task(cr.get("id"))
                    bc.complete_task(cr.get("id"), "done", card[:RESULT_MAX])
                    _pc_release(pid, i + 1, new_total, new_steps[0], k=k)
                    log.info("pc-plan-adapt: родитель %s adjust K=%s после шага %s → релиз "
                             "скорректированного шага %s/%s", pid, k, i, i + 1, new_total)
                    return
                log.warning("pc-plan-adapt: карточка коррекции родителя %s не встала (%s) — "
                            "fail-safe keep", pid, cr.get("error"))
    # keep / fail-safe / адаптация выключена / уже адаптировано → следующий шаг прежнего плана
    txt, k_origin = plan[i + 1]
    _pc_release(pid, i + 1, total, txt, k=k_origin)


def _pc_chain_tick(pid, steps):
    """Один тик надзора цепи ПК-театра: смотрим ПОСЛЕДНИЙ шаг (максимальный номер, при дублях —
    старший id: перерождение самопочинки). Ожидание (new/in_progress/approved) → проверка
    таймаута ПК; needs_approval → ждём Филиппа (карточка уже в инбоксе от devbot); done/failed →
    хуки цепи (адаптация/самопочинка/сводка)."""
    i, n, it = max(steps, key=lambda s: (s[0], int(s[2].get("id") or 0)))
    st = str(it.get("status") or "")
    if st == "needs_approval":
        return
    if st in ("new", "in_progress", "approved"):
        age = _age_sec(it.get("updated"))
        if age is not None and age > PC_STEP_TIMEOUT:
            diag = (f"{PC_SILENT_MARK}: шаг {i}/{n} родителя {pid} висит в статусе {st} "
                    f"{int(age // 60)} мин (лимит {PC_STEP_TIMEOUT // 60} мин) — ПК выключен или "
                    f"агент не работает. Цепочка остановлена (самопочинка такое не чинит). "
                    f"Проверь ПК-агента и повтори «декомпозируй:» в теме PC-дев.")
            bc.complete_task(it.get("id"), "failed", diag)
            log.info("pc-dec: шаг %s/%s родителя %s таймаут ПК (%s, %sс) → failed + halt",
                     i, n, pid, st, int(age))
            it["status"], it["result"] = "failed", diag   # снапшот в актуальное — для сводки
            _pc_post_summary(pid, steps)
        return
    # терминальный статус: закрытая ранее цепь (рестарт демона) → в кэш и не трогать
    if _dec_summary_exists(pid):
        _summarized.add(pid)
        return
    if st == "failed":
        _pc_after_fail(pid, i, n, it, steps)
    elif st == "done":
        _pc_after_done(pid, i, n, it, steps)


def process_pc_chains():
    """Надзор ПК-театра (каждый цикл демона): read-only снимок полосы pc → тик по каждой СВОЕЙ
    цепи (from=PC_DEC_FROM). Чужое на полосе pc (одиночные Filipp-pc[-dev]) не трогаем, claim
    не делаем. Сбой тика одной цепи не валит остальные (доберём следующим циклом)."""
    items = _pc_fetch_items()
    if items is None:
        return
    chains = _pc_group_chains(items)
    for pid in sorted(set(chains) - _summarized):
        try:
            _pc_chain_tick(pid, chains[pid])
        except Exception as e:
            log.warning("pc-dec: тик цепи родителя %s упал (%s) — следующим циклом", pid, e)


def _earlier_new_sibling(items, pid, step_i):
    """True → среди new-задач снапшота есть шаг ТОГО ЖЕ родителя с МЕНЬШИМ номером. Перерождение
    самопочинки получает id ВЫШЕ следующих шагов — порядок цепочки держим по НОМЕРУ шага, не по id.
    В обычной цепочке (id растут вместе с номерами) всегда False — поведение прежнее."""
    for it in items:
        mm = _STEP_RE.match(str(it.get("task_text") or ""))
        if mm and int(mm.group(3)) == int(pid) and int(mm.group(1)) < int(step_i):
            return True
    return False


def _dec_plan_and_fanout(tid, task_text, frm=""):
    """Родитель декомпозиции: планировщик claude -p (read-only) → парс шагов → шаги в очередь
    «[шаг i/N родитель tid] …» → родитель done с планом (devbot принесёт план в 328).
    ПК-ТЕАТР (frm=PC_DEC_FROM): план строится ТАК ЖЕ здесь (единственный планировщик), но шаги
    уходят на полосу lane=pc ПО ОДНОМУ (sequential release, см. секцию «ПК-ТЕАТР») — в очередь
    сразу встаёт ТОЛЬКО шаг 1, остальные релизит process_pc_chains после done предыдущего.
    Полоса vps (любой другой frm) — байт-в-байт прежнее поведение (веерный fan-out)."""
    pc = (frm == PC_DEC_FROM)
    preamble = PLANNER_PREAMBLE + (PLANNER_PC_NOTE if pc else "")
    status, out = run_task(tid, task_text, task_timeout=TASK_TIMEOUT_DEV, preamble=preamble)
    if status == "requeue":
        # чужой плановый рестарт погасил планировщик на старте → родитель возвращается в new
        _requeue_foreign_restart(tid, frm, task_text, out)
        return
    if status != "done":
        # планировщик read-only: needs_approval от него = аномалия → честный failed, не кнопка
        bc.complete_task(tid, "failed", f"декомпозиция не удалась (планировщик {status}): {out}"[:RESULT_MAX])
        return
    steps = _parse_steps(out)
    if not steps:
        # фейл-сейф урока 166: плана нет, но есть NA-маркер/фоллбэк → ВЕСЬ смысл родителя = одно
        # красное действие («декомпозируй: задеплой прод») → прежний честный отказ (та же карта,
        # что давал маршрут needs_approval планировщика до фикса; НЕ кнопка — конверт жил бы вне цепочки)
        what = _detect_needs_approval(out)
        if what is not None:
            bc.complete_task(tid, "failed",
                             f"декомпозиция не удалась (планировщик needs_approval): {what}"[:RESULT_MAX])
            return
        bc.complete_task(tid, "failed",
                         f"декомпозиция не удалась: планировщик не вернул нумерованный список шагов:\n{out}"[:RESULT_MAX])
        return
    if len(steps) > MAX_STEPS:
        bc.complete_task(tid, "failed",
                         f"декомпозиция не удалась: {len(steps)} шагов > потолка {MAX_STEPS} — "
                         f"упрости ТЗ или разбей вручную:\n{out}"[:RESULT_MAX])
        return
    n = len(steps)
    if pc:
        # ПК-театр: релизим ТОЛЬКО шаг 1 (lane=pc) ДО complete родителя (crash-окно без шагов —
        # родитель останется in_progress, devbot поднимет «зависла»); план целиком — в result
        # родителя нумерованным списком (restart-proof источник для release/адаптации).
        r = _pc_enqueue(f"[шаг 1/{n} родитель {tid}] {steps[0]}")
        if not r.get("ok"):
            bc.complete_task(tid, "failed",
                             f"декомпозиция (театр PC) не удалась: шаг 1 не встал в очередь "
                             f"lane=pc ({r.get('error')})"[:RESULT_MAX])
            return
        plan = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
        res = (f"🧩 Декомпозиция (театр PC): {n} шагов — исполняет ПК-агент ПО ОДНОМУ (lane=pc), "
               f"план и надзор на VPS.\n{plan}\n{_dec_red_note(steps)}"
               f"Шаг 1 в очереди lane=pc (id {r.get('id')}). Каждый шаг отчитается сюда отдельно; "
               f"красный шаг спрошу кнопкой; после последнего пришлю сводку. ПК молчит "
               f">{PC_STEP_TIMEOUT // 60} мин → честный failed цепи (без самопочинки).")
        bc.complete_task(tid, "done", res[:RESULT_MAX])
        log.info("pc-dec: родитель %s → план %s шагов, шаг 1 релизнут (id %s, lane=pc)",
                 tid, n, r.get("id"))
        return
    ids, errs = [], []
    for i, step in enumerate(steps, 1):
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", f"[шаг {i}/{n} родитель {tid}] {step}")
        if r.get("ok"):
            ids.append(str(r.get("id")))
        else:
            errs.append(f"шаг {i} не встал: {r.get('error')}")
            log.warning("dec: родитель %s шаг %s не встал в очередь (%s)", tid, i, r.get("error"))
    plan = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    res = (f"🧩 Декомпозиция: {n} шагов, в очереди id {', '.join(ids) or '—'}.\n{plan}\n{_dec_red_note(steps)}"
           f"Исполняю по одному (каждый шаг отчитается сюда отдельно), после последнего пришлю сводку. "
           f"Красный шаг спрошу кнопкой.")
    if errs:
        res += "\n⚠️ " + "; ".join(errs)
    bc.complete_task(tid, "done" if ids else "failed", res[:RESULT_MAX])
    log.info("dec: родитель %s → %s шагов (id %s)", tid, n, ",".join(ids))


def _approved_expired(updated_iso):
    """True, если approved-задача висит дольше APPROVED_TTL (по полю updated очереди). При ошибке
    разбора времени → False (одобренное Филиппом лучше выполнить, чем потерять из-за парсинга)."""
    try:
        s = str(updated_iso).replace("Z", "+00:00")
        t = datetime.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
        return age > APPROVED_TTL
    except Exception:
        return False


def _convert_other_approved(tid, task, what):
    """op=other после «да» Филиппа (заведено 03.07): хардкод-команды нет — заявку НЕ валим
    failed-отпиской «требуется решение владельца», а конвертируем в ОБЫЧНУЮ headless-задачу (текст заявки = ТЗ,
    from=Filipp-328-dev → дев-таймаут 45 мин); devbot принесёт её результат в 328 отдельным
    рапортом. Красная классификация ВНУТРИ новой задачи как была (преамбула/hook): настоящее
    красное снова даст NEEDS_APPROVAL-кнопку — approve заявки обхода гейта НЕ создаёт.
    Исключение: шаг декомпозиции НЕ конвертируем — конверт жил бы ВНЕ цепочки (без паттерна
    [шаг i/N]), guard последовательности его не видит → следующий шаг стартовал бы до
    исполнения одобренного. Для шага — прежний честный failed (halt-on-fail цепочки)."""
    if _STEP_RE.match(str(task.get("task_text") or "")):
        log.info("APPROVED id=%s op=other у шага декомпозиции → failed (конверт сломал бы guard)", tid)
        bc.complete_task(tid, "failed",
                         f"не могу выполнить автоматически: {what[:400]} — требуется решение "
                         f"владельца: переставь задачу в 328 после его ответа")
        _maybe_dec_after(task.get("task_text"), "failed")
        return
    orig = str(task.get("task_text") or "").strip()
    # СЛОЙ 2: заведомо headless-НЕВОЗМОЖНОЕ красное (clasp/живая таблица/деньги/sqlite3/удаление) —
    # НЕ конвертируем (конверт лишь родил бы то же NEEDS_APPROVAL) → сразу терминальная ручная карта =
    # ноль перерождений на известной петле. Слой 1 добьёт неизвестное красное при ре-эскалации конверта.
    #
    # СУДИМ ТОЛЬКО ПО ЗАЯВКЕ (02.08.2026, класс «корень А»). Раньше в тот же скан уходил `orig` —
    # ПРОЗА ТЗ ВЛАДЕЛЬЦА, текст, который слою никто не обещал. Любое из 15 слов в ней — «разберись,
    # почему add_transaction не логируется», «посмотри лог clasp» — и УЖЕ ОДОБРЕННАЯ владельцем
    # заявка закрывалась терминальной картой «сделай руками», не попробовав ни разу: его «да»
    # съедало совпадение слова в его же формулировке. Решать про операцию должна ОПЕРАЦИЯ — то
    # есть заявка (`what`), которую владелец и подтверждал, а не контекст вокруг неё.
    # ЗАЩИТА НЕ ОСЛАБЛЕНА, и это свойство слоя, а не надежда: слой 2 экономит перерождение, а не
    # запрещает — несработавший стоит РОВНО одно (конверт уйдёт обычным путём, там его встретит
    # pretool_guard, а слой 1 закроет петлю терминально). Ровно так это и записано выше.
    if _is_headless_impossible(what):
        log.info("APPROVED id=%s op=other headless-невозможно (keyword) → терминальная карта, без конверта", tid)
        bc.complete_task(tid, "failed", _manual_card(what, orig))
        return
    card = _OP_PREFIX_RE.sub("", what or "").strip() or "(карточка пустая — см. исходную задачу)"
    tz = (f"[конверт одобренной заявки {tid}] Филипп нажал «да» на заявку: {card}\n"
          f"Исходная задача (контекст): {orig}\n"
          f"Выполни одобренное в рамках исходной задачи. Дисциплина CLAUDE.md действует полностью; "
          f"настоящее красное (рабочие таблицы/деньги/clasp/sqlite3/удаление) — по-прежнему ТОЛЬКО "
          f"маркером NEEDS_APPROVAL: одобрение заявки обход гейта НЕ даёт.")[:RESULT_MAX]
    r = bc.enqueue_task(f"Filipp-328{DEV_FROM_SUFFIX}", tz)
    if not r.get("ok"):
        log.warning("APPROVED id=%s конверт op=other не встал в очередь (%s) → failed", tid, r.get("error"))
        bc.complete_task(tid, "failed",
                         f"одобрено, но конверт в headless-задачу не встал в очередь "
                         f"({r.get('error')}) — требуется решение владельца: переставь задачу "
                         f"в 328 после его ответа. Заявка: {what[:400]}")
        _maybe_dec_after(task.get("task_text"), "failed")
        return
    nid = r.get("id")
    bc.complete_task(tid, "done",
                     f"✅ Одобрено → конвертировано в headless-задачу id {nid} (from=Filipp-328-dev, "
                     f"таймаут 45 мин). Результат придёт отдельным рапортом по задаче {nid}.")
    log.info("APPROVED id=%s op=other → конверт в headless-задачу %s", tid, nid)


def _enqueue_convert_verified(tid, tz):
    """Поставить конверт одобренной карточки НАДЁЖНО → id задачи | None.

    Образец — `_claim_task_verified` и devbot `_enqueue_reliable` (класс 138/146: ответ моста
    теряется, а действие сервер-сайд ДОЛЕТАЕТ). Порядок: enqueue → сбой → verify «конверт этой
    карточки уже лежит в new?» (ответ потерялся, задача встала — берём ЕЁ id, дубля не плодим)
    → иначе РОВНО один повтор → иначе None (вызывающий закрывает карточку честным failed).
    Маркер конверта несёт номер КАРТОЧКИ, поэтому verify точен: чужой конверт под него не
    подойдёт. FAIL-SAFE: verify сам не читается → сразу к повтору, хуже прежнего не будет."""
    frm = f"Filipp-328{DEV_FROM_SUFFIX}"
    r = bc.enqueue_task(frm, tz)
    if r.get("ok"):
        return r.get("id")
    log.warning("curator-human: enqueue конверта карточки %s не прошёл (%s) — проверяю, не "
                "долетел ли он всё-таки", tid, r.get("error"))
    mark = f"[конверт одобренной заявки {tid}]"
    try:
        rr = bc.get_pending("new")
        if rr.get("ok"):
            for it in rr.get("items", []):
                if isinstance(it, dict) and str(it.get("task_text") or "").startswith(mark):
                    log.warning("curator-human: конверт карточки %s ДОЛЕТЕЛ (id=%s) — повтор не "
                                "нужен, дубля нет", tid, it.get("id"))
                    return it.get("id")
    except Exception as e:
        log.warning("curator-human: verify конверта карточки %s не прочитался (%s) — к повтору",
                    tid, e)
    r2 = bc.enqueue_task(frm, tz)
    if r2.get("ok"):
        log.info("curator-human: конверт карточки %s встал со второй попытки (id=%s)",
                 tid, r2.get("id"))
        return r2.get("id")
    log.warning("curator-human: повтор enqueue конверта карточки %s тоже не прошёл (%s)",
                tid, r2.get("error"))
    return None


def _convert_curator_human_approved(tid, task, what):
    """✅ на сводной карточке владельцу (куратор, шаг 4/7) → ЗАДАЧА на исполнение её пунктов.

    КЛАСС (инцидент карточек 95 и 100, 31.07.2026). Обе карточки просили РАЗРЕШЕНИЕ на одну и ту
    же операцию — рестарт splinter; владелец подтвердил обе, и обе закрылись в done «пункты
    приняты/сделаны владельцем». Работы не родилось ни разу: ветка гасила approved сразу, без
    конверта и без исполнения. Два зелёных коммита простояли в проде полдня, вскрылось ручной
    перекличкой. Корень: ОДНА кнопка означала то «принял к сведению», то «разрешаю действие», и
    владелец их различить не мог. Карточка, просящая разрешение на операцию, обязана рождать работу.

    ТИП ПУНКТА НЕ УГАДЫВАЕМ. Надёжного признака «разрешение» vs «к сведению» в тексте пункта нет
    (куратор пишет свободной строкой), а угадывание вернуло бы тот же класс с другой стороны —
    молча съеденное «да». Поэтому: ✅ ВСЕГДА ставит задачу, карточка говорит об этом ДО нажатия
    (_curator_human_render), а разбор «исполнять / нечего исполнять» уходит исполнителю, который
    видит пункт целиком. Пункт «к сведению» работы по-прежнему не рождает — ТЗ прямо запрещает
    её выдумывать, так что для владельца исход такого пункта тот же, что и был.

    ПЕТЛИ. Текст задачи несёт маркер [конверт одобренной заявки N] ПЕРВЫМ → работает весь готовый
    контур разрыва: слой 1 (повторный NEEDS_APPROVAL конверта = терминальная ручная карта БЕЗ
    approve-кнопки, process_new), пропуск самопочинки (_maybe_selfheal) и пропуск куратора
    (_maybe_curator_single) — ре-карточка на ту же цель невозможна.
    СЛОЙ 2 (_is_headless_impossible) здесь НЕ применяем НАМЕРЕННО: карточка — СПИСОК, и одно
    красное слово в чужом пункте похоронило бы исполнимые пункты рядом; слой 1 закрывает петлю
    после ровно одного перерождения, этого достаточно.

    ИСХОД ПОСТАНОВКИ ЧЕСТЕН (04.08.2026, вторая ревизия класса): постановка идёт надёжно
    (_enqueue_convert_verified: verify → один повтор), а если задача всё же не встала —
    карточка закрывается FAILED, а не done. Прежний done читался в 328 как успех: владелец
    нажал ✅, увидел зелёный рапорт, а работы за ним не было — тот же класс с другой стороны.
    Пункты в result по-прежнему ДОСЛОВНО: «да» владельца не теряется ни в одном исходе."""
    m = _CURATOR_HUMAN_RE.match(str(task.get("task_text") or ""))
    root = m.group(1) if m else "?"
    items = _curator_human_items(what)
    if not items:
        # тело карточки не разобралось (обрезка/старый формат) — «да» не теряем: берём пункт
        # из task_text (он кладётся туда при создании карточки именно на такой случай)
        tail = _CURATOR_HUMAN_RE.sub("", str(task.get("task_text") or "")).strip()
        items = [(tail or str(what).strip() or "(тело карточки пустое — см. задачу-цель)", 1)]
    body = "\n".join(f"{i}. {t}" for i, (t, _n) in enumerate(items, 1))
    # хвост урезки тела (см. _curator_human_render): пунктов на карточке было больше, чем
    # поместилось — исполнитель обязан знать, что список НЕ полон, иначе «одобрено всё» солжёт
    over = next((ln.strip() for ln in str(what or "").splitlines()
                 if ln.strip().startswith(_HUMAN_OVERFLOW)), "")
    # ОПЕРАЦИОННАЯ КАРТОЧКА (класс 251/254/257): пункт здесь — ОДНА операция, а дословный текст
    # куратора приехал справкой. Контекст в ТЗ нужен (без него исполнитель не знает, какая строка
    # и какое число), но область «да» им НЕ расширяется — сказано прямо, иначе конверт сделал бы
    # соседние операции, которых владелец на ЭТОЙ карточке не разрешал.
    ctx = next((ln.strip()[len(_HUMAN_CTX):] for ln in str(what or "").splitlines()
                if ln.strip().startswith(_HUMAN_CTX)), "")
    is_op = bool(ctx or (m and m.group(2)))

    def _tz(ctx_part):
        scope = ""
        if is_op:
            scope = ("ЭТА КАРТОЧКА — ОДНА ОПЕРАЦИЯ, разведённая из пункта, где их было несколько. "
                     "Соседние операции того же пункта сюда НЕ входят и ждут своих «да» отдельными "
                     "карточками: НЕ делай их, даже если они названы в справке ниже.\n"
                     + (f"Справка — пункт куратора дословно: {ctx_part}\n" if ctx_part else ""))
        return (
            f"[конверт одобренной заявки {tid}] Филипп нажал «да» на сводную карточку владельцу "
            f"(цель {root}). ОДОБРЕННЫЕ ПУНКТЫ:\n{body}\n" + (f"({over})\n" if over else "") + "\n"
            + scope +
            f"Пункт, просивший РАЗРЕШЕНИЕ на операцию, этим «да» РАЗРЕШЁН — выполни его и докажи "
            f"эффект блоком FACT:. Пункт чисто информационный («принял к сведению», решение уже "
            f"принято, делать нечего) — работу НЕ выдумывай: скажи в отчёте, что исполнять нечего. "
            f"Если пункт уже исполнен кем-то раньше — проверь живым фактом и доложи, не повторяя. "
            f"ЧАСТЬ ПУНКТА, ЗАКРЫТУЮ ТЕБЕ ПРАВИЛАМИ, НЕ ОТМЕНЯЕТ ОСТАЛЬНОГО: выполни ту часть, что "
            f"открыта (оранжевый цикл — свои сервисы, гейт, коммит, push), а закрытую назови "
            f"ОТДЕЛЬНОЙ строкой «нужно от владельца: …» — молча не бросай пункт целиком. "
            f"Дисциплина CLAUDE.md действует полностью; настоящее красное (рабочие таблицы/деньги/"
            f"clasp/sqlite3/удаление) — по-прежнему ТОЛЬКО маркером NEEDS_APPROVAL: одобрение "
            f"карточки обход гейта НЕ даёт.")

    # СПРАВКА РЕЖЕТСЯ ПОД ДИСЦИПЛИНУ, А НЕ ДИСЦИПЛИНА ПОД ПОТОЛОК (тот же приём, что у
    # _curator_human_render). Хвост ТЗ несёт самое важное — «красное только маркером
    # NEEDS_APPROVAL»; уедь он под cap_result, конверт получил бы контекст без запрета.
    raw = _tz(ctx)
    if len(raw) > RESULT_MAX and ctx:
        room = max(0, len(ctx) - (len(raw) - RESULT_MAX) - 1)
        raw = _tz(ctx[:room] + "…")
    tz = cap_result(raw)
    nid = _enqueue_convert_verified(tid, tz)
    if nid is None:
        # «ДА» НЕ МОЖЕТ ПОГАСНУТЬ В ЗЕЛЁНОМ ИСХОДЕ (04.08.2026, вторая ревизия класса).
        # Раньше здесь стоял done — и в 328 это читалось РОВНО как успех: владелец нажал ✅,
        # получил зелёный рапорт, а задачи не существовало. Это тот же класс, ради которого
        # ветку и переписывали 31.07, просто с другой стороны. Теперь исход честный (failed):
        # карточка видна как НЕзакрытое дело, пункты в result ДОСЛОВНО — «да» не теряется.
        bc.complete_task(tid, "failed", cap_result(
            f"🧑 сводная карточка владельцу (✅): «да» ПРИНЯТО, но задача на исполнение НЕ "
            f"встала в очередь даже с повтором — работы за этим «да» СЕЙЧАС НЕТ. Дожми пункты "
            f"вручную («тз:» в 328), они здесь дословно:\n{body}"))
        log.warning("curator-human: карточка %s одобрена, но задача-исполнитель не встала "
                    "(даже с повтором) → failed, «да» видно как незакрытое", tid)
        return
    bc.complete_task(tid, "done", cap_result(
        f"🧑 сводная карточка владельцу (✅) → задача id {nid} на исполнение пунктов "
        f"(from=Filipp-328{DEV_FROM_SUFFIX}, таймаут 45 мин). Пункт-разрешение будет выполнен, "
        f"пункт «к сведению» закроется без действий. Результат придёт отдельным рапортом "
        f"по задаче {nid}."))
    log.info("curator-human: карточка %s одобрена (✅) → задача %s на исполнение пунктов", tid, nid)


def process_approved():
    """Довести одобренные Филиппом красные шаги (status=approved). claude ПОВТОРНО НЕ зовётся —
    op∈AUTO_OPS исполняется хардкод-командой (билет 4.2 + чёрный ящик); op=other (заведено 03.07)
    конвертируется в обычную headless-задачу (см. _convert_other_approved) — демон красное сам
    НЕ исполняет, конверт лишь возвращает заявку в обычный контур с той же классификацией.
    Инвариант: хардкод — ТОЛЬКО если op∈AUTO_OPS И билет 4.2 consume ok И не истёк таймаут approved."""
    r = bc.get_pending("approved")
    if not r.get("ok"):
        # Раньше выходили МОЛЧА: подтверждения не обрабатывались, задача сгорала по APPROVED_TTL,
        # и владелец видел failed после «да», а в журнале не было ни строки.
        n = _poll_fail("approved")
        log.warning("approved: мост не ответил (%s) — цикл пропущен, подряд неудач: %d",
                    r.get("error") or "без поля error", n)
        return
    _poll_ok("approved")
    for task in sorted(r.get("items", []), key=lambda x: int(x.get("id") or 0)):
        tid = task.get("id")
        # FIXTURE-GUARD (класс 193, рубеж approved): заглушка одобрена — НЕ исполнять,
        # не конвертировать в конверт. ORCH_TEST_MODE=1 выключает, как в process_new.
        _ftxt_ap = str(task.get("task_text") or "")
        if _is_fixture(_ftxt_ap) and os.environ.get("ORCH_TEST_MODE") != "1":
            bc.complete_task(tid, "failed",
                             "⛔ фикстура-заглушка в живой очереди (approved) — НЕ исполняю "
                             "(класс 193). Чинить источник: тестам — мок-очередь либо TEST-.")
            log.warning("fixture-guard/approved: id=%s заглушка (%.40s…) → failed", tid, _ftxt_ap)
            continue
        what = str(task.get("result") or "")        # сохранённый дескриптор (op=… | текст) — одобренный

        # Сводная карточка владельцу (куратор, шаг 4/7): ✅ = РАЗРЕШЕНИЕ на пункты, а не «принял
        # к сведению» (класс карточек 95/100, 31.07.2026 — раньше здесь стоял голый done, и «да»
        # на операцию молча не рождало работы) → задача на исполнение пунктов, карточка
        # закрывается ссылкой на неё. ДО проверки таймаута approved намеренно: «approve истёк»
        # сжёг бы «да» владельца (класс 25.07 — не жечь «да» из-за своей слепоты). Новые
        # human-пункты той же цели после закрытия пойдут НОВОЙ карточкой (upsert ищет открытые).
        if _CURATOR_HUMAN_RE.match(str(task.get("task_text") or "")):
            _convert_curator_human_approved(tid, task, what)
            continue

        # таймаут approved: одобрено давно, не довели → авто-failed
        if _approved_expired(task.get("updated")):
            if not _poll_covered(APPROVED_TTL):
                log.warning("APPROVED id=%s истёк по часам, но мост в это окно опрашивался с "
                            "перебоями — НЕ гашу (класс 25.07: не жечь «да» из-за своей слепоты)",
                            tid)
                continue
            log.info("APPROVED id=%s ИСТЁК (>%ss) → failed [слой ttl]", tid, APPROVED_TTL)
            bc.complete_task(tid, "failed", _truthful_fail(
                tid, "approve истёк (>30 мин), повтори задачу [закрыто: слой ttl]",
                "approval_timeout", task=task))
            _maybe_dec_after(task.get("task_text"), "failed")
            continue

        op = parse_op(what)
        # ЗАМОК ПРОИСХОЖДЕНИЯ, второй рубеж (класс «подделка карточек», 31.07.2026): класс
        # операции после «да» признаётся ТОЛЬКО у карточки, рождённой сверенным маркером гарда.
        # Карточка из очереди до правки (origin=legacy) и любая заявка исполнителя прав на
        # хардкод-команду не имеют — «да» уходит в обычный конверт, где действует та же
        # классификация. Первый рубеж (process_new) такую карточку вообще не рождает; этот
        # рубеж стережёт то, что уже лежало в очереди, и любую будущую ветку рождения.
        if op in EXECUTORS and _card_origin(what) != "guard":
            log.warning("APPROVED id=%s: исполнимый класс op=%s заявлен НЕ гардом (origin=%s) → "
                        "класс не признан, «да» уходит в обычный конверт",
                        tid, op, _card_origin(what))
            op = "other"
        if op not in EXECUTORS:
            # вне авто-перечня / free-text / op=other → демон сам НЕ исполняет:
            # конверт в обычную headless-задачу (или failed для шага декомпозиции)
            _convert_other_approved(tid, task, what)
            continue

        # билет 4.2: одноразовый серверный жетон авторизации + аудит (issue → consume перед командой)
        tk = (bc.issue_write_ticket() or {}).get("ticket")
        if not tk or not bc.consume_write_ticket(tk).get("ok"):
            log.warning("APPROVED id=%s билет 4.2 не подтверждён → failed", tid)
            bc.complete_task(tid, "failed", "билет токен-замка 4.2 не подтверждён — операция не выполнена [закрыто: слой 1]")
            continue

        log.info("APPROVED id=%s ИСПОЛНЯЮ op=%s (билет погашен)", tid, op)
        status, out = EXECUTORS[op](tid)
        # чёрный ящик 4.1: факт approved-красной операции
        try:
            bc.log_write(initiator="orchestrator-daemon", act=op, args=f"task {tid}",
                         result=("ok" if status == "done" else "fail"), critical="approved-redzone")
        except Exception as e:
            log.warning("APPROVED id=%s чёрный ящик не записан (%s)", tid, e)
        bc.complete_task(tid, status, out)
        log.info("APPROVED id=%s op=%s → %s", tid, op, status)
        _maybe_dec_after(task.get("task_text"), status)   # шаг декомпозиции → halt/сводка


# Маркер клона (микрофикс §7 12.07.2026, инцидент 156: владелец видел «задвоение карточки» —
# клон возврата 7ff92fb неотличим от новой задачи). Ставится строго В КОНЕЦ текста клона:
# стартовые маркеры не сдвигаются ([шаг i/N родитель id] — _STEP_RE.match с начала,
# [конверт…] — _CONVERT_RE обязан стоять ПЕРВЫМ). Парный детект — devbot._is_repeat_item
# (константа продублирована там: devbot живёт в процессе bot.py, демон не импортирует).
REPEAT_MARK = "[повтор задачи"


def _requeue_foreign_restart(tid, frm, text, note):
    """СЛОЙ 2 фикса дыры 48d9c64 (урок 122): задача погашена ЧУЖИМ плановым рестартом на старте —
    работа НЕ делалась. Bridge completeTask_ принимает только done|failed → «возврат в new» =
    клон задачи ДОСЛОВНО (тот же текст — шаг декомпозера сохраняет маркер [шаг i/N], одиночная —
    полосу from и таймаут) + маркер REPEAT_MARK в КОНЦЕ (карточка клона в 328 получает «(повтор)»
    в заголовке — инцидент 156; повторный клон клона маркер не дублирует) + исходная закрывается
    done с маркер-картой 🔄. НЕ failed: думатель самопочинки зря не дёргается, цепочка декомпозера
    не глушится (сводка возьмёт финал клона — последняя запись номера шага по id). Хуки цепи НЕ
    зовём: клон в new держит цепь живой (guard'ы process_new/_maybe_plan_adapt его видят).
    Клон не встал → честный failed (не потерять задачу молча)."""
    frm = str(frm or "") or f"Filipp-328{DEV_FROM_SUFFIX}"
    text = str(text or "")
    clone = text if REPEAT_MARK in text else f"{text}\n{REPEAT_MARK} {tid}]"
    r = bc.enqueue_task(frm, clone)
    if not r.get("ok"):
        log.warning("FOREIGN-RESTART id=%s клон не встал в очередь (%s) → честный failed",
                    tid, r.get("error"))
        bc.complete_task(tid, "failed",
                         (f"погашена чужим плановым рестартом демона на старте (работа не "
                          f"делалась), возврат в очередь не встал ({r.get('error')}) — повтори "
                          f"задачу")[:RESULT_MAX])
        _maybe_dec_after(text, "failed")
        return
    nid = r.get("id")
    bc.complete_task(tid, "done",
                     (f"{note}\nВозвращена в очередь задачей id {nid} (текст дословно, полоса "
                      f"from та же) — исполнится после рестарта демона.")[:RESULT_MAX])
    log.info("FOREIGN-RESTART id=%s → возвращена в new задачей %s", tid, nid)


def _fixture_reap_open():
    """Реапер фикстур (класс 193, рубеж 4): закрыть тест-заглушки, застрявшие в
    needs_approval или approved (туда guard process_new не достаёт). Каждый cycle().
    ORCH_TEST_MODE=1 → тесты гоняют фикстуры через мок, не трогаем."""
    if os.environ.get("ORCH_TEST_MODE") == "1":
        return
    r = bc.get_pending("needs_approval,approved")
    if not r.get("ok"):
        return
    for item in r.get("items", []):
        tid = item.get("id")
        txt = str(item.get("task_text") or "")
        if not _is_fixture(txt):
            continue
        st = item.get("status", "?")
        bc.complete_task(tid, "failed",
                         f"⛔ фикстура-заглушка в живой очереди (статус={st}, "
                         "класс 193 реапер). Чинить источник: тестам — мок-очередь либо TEST-.")
        log.warning("fixture-reap: id=%s статус=%s заглушка (%.40s…) → failed", tid, st, txt)


def process_orphans():
    """Фикс класса «claim долетел — исполнение не стартовало» (инцидент 07.07.2026, задача 138):
    Bridge в сбое (404 на redirect-echo / timeout) может ИСПОЛНИТЬ claim_task сервер-сайд, потеряв
    ответ → клиент видит request_failed и «пропускает», а задача уже in_progress — исполнять её
    некому, heartbeat мёртв, висит вечно (138 провисела 70+ мин до ручного рестарта и осталась бы
    висеть). Демон однопоточный: в момент cycle() НАША задача in_progress быть не может (run_task
    блокирующий) — любая vps-in_progress здесь = сирота; ORPHAN_TTL — страховка (свежий claim из
    гонки/чужого процесса не трогаем, ждём порог). Полосу pc НЕ трогаем — там надзор
    process_pc_chains (PC_STEP_TIMEOUT). Сирота → честный failed с ⏱-маркером (думатель НЕ
    зовётся — гейт ⏱ в _maybe_selfheal, да и путь реапера думателя не знает) + хук цепи
    декомпозера (halt-on-fail/сводка), чтобы цепь тоже не висела. Сбой чтения/парсинга → ничего
    не делаем (fail-safe: лучше подождать цикл, чем убить живое)."""
    r = bc.get_pending("in_progress")
    if not r.get("ok"):
        return
    for it in r.get("items", []):
        if not isinstance(it, dict):
            continue
        if str(it.get("lane") or "").strip().lower() == PC_LANE:
            continue                     # ПК-театр — чужой исполнитель, надзор PC_STEP_TIMEOUT
        age = _age_sec(it.get("updated"))
        if age is None or age < ORPHAN_TTL:
            continue
        tid = it.get("id")
        text = str(it.get("task_text") or "")
        card = (f"{TIMEOUT_MARK} задача-сирота: взята в исполнение (in_progress), но исполнитель "
                f"молчит {int(age)}с (heartbeat мёртв, порог {ORPHAN_TTL}с). Вероятно claim долетел "
                f"до Bridge без ответа в окно его сбоя (урок задачи 138, 07.07) или демон был "
                f"прерван до/во время исполнения. Работа не выполнялась либо оборвана — повтори "
                f"задачу; думатель сирот не чинит.")
        # правда статуса: код причины + следы работы в окне (сирота часто УСПЕЛА поработать —
        # именно этот случай на ПК дважды увёл план в неверную сторону)
        card = _truthful_fail(tid, card, "heartbeat_timeout", task=it)
        cm = bc.complete_task(tid, "failed", card[:RESULT_MAX])
        log.warning("ORPHAN id=%s: in_progress без heartbeat %sс → честный failed (bridge_ok=%s)",
                    tid, int(age), cm.get("ok"))
        _maybe_dec_after(text, "failed")


def _claim_task_verified(tid):
    """ФИКС КОРНЯ повторных сирот (138 вчера, 146 сегодня — 08.07.2026): claim-verify по образцу
    _enqueue_reliable. Инцидент 146 (лог 03:44 UTC): 1-й POST claim ИСПОЛНИЛСЯ сервер-сайд, но
    глючный echo-слой Google вернул unauthorized → auth-resend клиента получил already_claimed
    ОТ СВОЕГО ЖЕ долетевшего claim'а → демон счёл claim чужим и пропустил цикл → задача сирота
    in_progress до реапера (~10 мин простоя). Claim НЕ идемпотентен (в _IDEMPOTENT_POST_ACTIONS
    не вносить — слепой re-POST брал бы уже чужое), поэтому именно verify: после клиентского
    сбоя claim — немедленный read-only GET in_progress СВОЕЙ полосы (vps). Worker-колонки в
    очереди нет; доказательство владения = одно-воркерность полосы: claim vps-задач делает
    ТОЛЬКО этот демон (pc claim'ит pc_orchestrator, synthetic-задачи имеют свои id), а кандидат
    секунды назад был new в ЭТОМ ЖЕ цикле — значит in_progress сейчас может быть только НАШ
    долетевший claim → считаем claim успешным, исполняем штатно, сироты нет.
    Задачи нет в in_progress (claim реально не долетел) / статус иной / verify сам сбоит →
    как раньше: пропуск цикла (fail-safe, не хуже прежнего; настоящее застревание добьёт реапер
    process_orphans по ORPHAN_TTL). Семантические отказы not_found/wrong_lane/no_id verify не
    дёргают — там claim заведомо не наш. Тесты tests/test_claim_verify.py (в гейте)."""
    cl = bc.claim_task(tid)
    if cl.get("ok"):
        return cl
    err = str(cl.get("error") or "")
    if err in ("not_found", "wrong_lane", "no_id"):
        return cl
    try:
        vr = bc.get_pending("in_progress")
        if vr.get("ok") and any(str(it.get("id")) == str(tid) for it in (vr.get("items") or [])):
            log.warning("CLAIM-VERIFY id=%s: клиентский сбой claim (%s), но задача in_progress "
                        "на моей полосе — claim долетел, исполняю штатно (сироты нет)", tid, err)
            return {"ok": True, "verified": True}
    except Exception as e:
        log.warning("CLAIM-VERIFY id=%s: verify не удался (%s) — прежний пропуск цикла", tid, e)
    return cl


def process_new():
    """Взять старейшую new-задачу, исполнить через claude -p, записать результат/needs_approval."""
    r = bc.get_pending("new")
    if not r.get("ok"):
        log.warning("get_pending ошибка: %s", r.get("error"))
        return
    items = r.get("items", [])
    if not items:
        return
    # СЛОЙ 1 фикса дыры 48d9c64 (урок 122) — ПРОФИЛАКТИКА: в systemd жив отложенный плановый
    # рестарт демона (таймер тикает / restart уже идёт) → новые задачи НЕ берём — взятая сейчас
    # погибнет на старте вместе с нами. Задачи спокойно ждут в new; после рестарта свежий демон
    # возьмёт их как обычно. Сбой пробы → паузы нет (fail-safe, поведение как было).
    if _restart_pending():
        log.info("пауза приёма: жду планового рестарта демона (systemd-run-единица жива) — "
                 "%d задач(и) ждут в new", len(items))
        return
    # ГЕЙТ ПАМЯТИ: свободно < MEM_MIN_MB или claude RSS >= CLAUDE_RSS_TOTAL_MB → ждём в new
    if _mem_gate_check():
        return
    # ГЕЙТ ПАРАЛЛЕЛИЗМА: живых claude >= MAX_CLAUDE_PROCS → ждём в new
    if _proc_gate_check():
        return
    # FIFO: get_pending отдаёт newest-first → берём наименьший id (старейшую задачу) первым.
    # Шаг декомпозиции, чей сиблинг ждёт (needs_approval/approved/in_progress), пропускаем —
    # НЕ блокируя чужие задачи дальше по очереди (guard последовательности цепочки).
    task = None
    for cand in sorted(items, key=lambda x: int(x.get("id") or 0)):
        # FIXTURE-GUARD (класс 193): заглушка из тестов дошла до живой очереди (гард клиента
        # обойдён/чужой клиент) → НЕ исполняем: мгновенный failed без claude -p. ORCH_TEST_MODE=1
        # (ставит gate.py тестам) фильтр выключает — голдены гоняют фикстуры через мок свободно.
        _ftxt = str(cand.get("task_text") or "")
        if _is_fixture(_ftxt) and os.environ.get("ORCH_TEST_MODE") != "1":
            bc.complete_task(cand.get("id"), "failed",
                             "⛔ фикстура-заглушка в живой очереди — НЕ исполняю (класс 193: тесты "
                             "пишут мимо мока). Чинить источник: тестам — мок-очередь либо TEST-.")
            log.warning("fixture-guard: id=%s заглушка (%.40s…) → failed без исполнения",
                        cand.get("id"), _ftxt)
            return
        if _is_dec(cand):
            m = _STEP_RE.match(str(cand.get("task_text") or ""))
            if m:
                pid = int(m.group(3))
                if _dec_siblings(pid, ("failed",)):
                    # сиблинг упал/отклонён («нет N» finalизирует мимо демона) → цепочку глушим:
                    # этот шаг failed, хук доведёт остальных + сводку. return (не continue):
                    # снапшот items уже неактуален, доработаем следующим циклом.
                    bc.complete_task(cand.get("id"), "failed",
                                     f"⏭ пропущен: другой шаг родителя {pid} упал/отклонён — цепочка остановлена")
                    log.info("dec: шаг id=%s родителя %s пропущен (в цепочке есть failed)",
                             cand.get("id"), pid)
                    _maybe_dec_after(str(cand.get("task_text") or ""), "failed")
                    return
                if _dec_step_blocked(pid):
                    log.info("dec: шаг id=%s родителя %s ждёт сиблинга — пропускаю в этом цикле",
                             cand.get("id"), pid)
                    continue
                if _earlier_new_sibling(items, pid, int(m.group(1))):
                    # перерождение самопочинки: шаг с МЕНЬШИМ номером ждёт в new (id у него выше) —
                    # порядок цепочки по номеру шага, этого кандидата пропускаем в этом проходе
                    log.info("dec: шаг id=%s родителя %s ждёт шага с меньшим номером — пропускаю",
                             cand.get("id"), pid)
                    continue
        task = cand
        break
    if task is None:
        return
    tid = task.get("id")
    text = str(task.get("task_text") or "")
    log.info("NEW id=%s from=%s text=%.120s", tid, task.get("from"), text)

    cl = _claim_task_verified(tid)
    if not cl.get("ok"):
        log.info("claim id=%s не удался (%s) — пропускаю в этом цикле", tid, cl.get("error"))
        return

    # ХВОСТ 1: событие «взял в работу» — ЕДИНСТВЕННАЯ точка записи журнала взятий. Отсюда его
    # заберёт devbot и вынесет карточку в 328, даже если задача прожила 5 секунд и ни в один
    # 45с-снимок in_progress не попала. Сбой записи задачу не трогает (fail-safe внутри).
    write_claim_event(task)

    if _is_dec(task):
        sm = _SUM_RE.match(text)
        if sm:
            # осиротевшая synthetic-сводка (демон упал между enqueue и complete) → доводим;
            # у ПК-семейства сводку собираем из pc-шагов (vps-читалка их не видит)
            if str(task.get("from") or "") == PC_DEC_FROM:
                pid = int(sm.group(1))
                bc.complete_task(tid, "done", _pc_summary_text(pid, _pc_chain_steps(pid)))
            else:
                bc.complete_task(tid, "done", _dec_summary_text(int(sm.group(1))))
            log.info("dec: осиротевшая сводка id=%s доведена", tid)
            return
        if _ADAPT_CARD_RE.match(text):
            # осиротевшая карточка адаптации (демон упал между enqueue и complete) → доводим,
            # НЕ отдавая её планировщику как «родителя» (сами шаги коррекции уже в цепочке)
            bc.complete_task(tid, "done", "🧭 карточка коррекции плана (осиротела при рестарте "
                                          "демона; шаги коррекции уже в цепочке родителя)")
            log.info("dec: осиротевшая карточка адаптации id=%s доведена", tid)
            return
        if _PC_CARD_RE.match(text):
            # осиротевшая событийная карточка ПК-театра (🩹/🛑/⚠️ — тело живёт в result при
            # complete; сирота = тело потеряно при рестарте, сама цепь идёт своим ходом)
            bc.complete_task(tid, "done", "🃏 карточка события цепи ПК-театра (осиротела при "
                                          "рестарте демона; цепь родителя идёт своим ходом)")
            log.info("pc-dec: осиротевшая карточка id=%s доведена", tid)
            return
        hm = _CURATOR_HUMAN_RE.match(text)
        if hm:
            # осиротевшая сводная карточка владельцу (демон упал между enqueue и set_needs_approval):
            # пункт живёт в task_text → доводим В needs_approval с отрендеренным телом, пункт не
            # теряется, devbot унесёт карточку в инбокс как обычно
            item = text[hm.end():].strip() or "(пункт потерян при рестарте демона)"
            bc.set_needs_approval(tid, _curator_human_render(int(hm.group(1)), [(item, 1)]))
            log.info("curator-human: осиротевшая сводная карточка id=%s доведена в needs_approval", tid)
            return
        if _CURATOR_CARD_RE.match(text):
            # осиротевшая карточка куратора (демон упал между enqueue и complete: вердикт потерян,
            # повторно куратора НЕ зовём — карточка остаётся restart-proof маркером дедупа)
            bc.complete_task(tid, "done", "🧭 карточка куратора (осиротела при рестарте демона; "
                                          "вердикт потерян, консультация не повторяется)")
            log.info("curator: осиротевшая карточка id=%s доведена", tid)
            return
        if not _STEP_RE.match(text):
            # родитель «декомпозируй:» → план → fan-out шагов (ПК-театр: релиз шага 1 lane=pc)
            _dec_plan_and_fanout(tid, text, frm=str(task.get("from") or ""))
            return

    _LAST_RUN.clear()          # правда статуса: канал кода причины чист ДО вызова (см. _LAST_RUN)
    status, result = run_task(tid, text, task_timeout=_task_timeout(task))
    if status == "requeue":
        # чужой плановый рестарт погасил задачу на старте → вернуть в new (слой 2 фикса 122)
        _requeue_foreign_restart(tid, task.get("from"), text, result)
        return
    if status == "needs_approval":
        if _is_convert(text):
            # СЛОЙ 1 (ядро): конверт снова упёрся в красное → headless ДОКАЗАННО не может. НЕ ставим
            # approvable needs_approval (это был бы ре-конверт = петля). Терминальный failed с ручной
            # картой → рендер БЕЗ approve-кнопки → петля рвётся после РОВНО 1 перерождения.
            _mcard = _manual_card(result)
            cm = bc.complete_task(tid, "failed", _mcard)
            log.info("CONVERT-LOOP-BREAK id=%s → failed (терминальная ручная карта), bridge_ok=%s",
                     tid, cm.get("ok"))
            _series_note_terminal(task, "failed", _mcard)
            _maybe_dec_after(text, "failed")
        elif parse_op(result) in EXECUTORS and _card_origin(result) != "guard":
            # ЗАМОК ПРОИСХОЖДЕНИЯ (класс «подделка карточек», 31.07.2026): строка заявляет
            # ИСПОЛНИМЫЙ класс (демон выполнил бы его сам хардкод-командой), но гард такой команды
            # НЕ перехватывал — значит объекта у заявки нет и «да» подтверждало бы не операцию, а
            # текст, который задача про себя написала. Карточку не рождаем вовсе: терминальная
            # карта без кнопки. Настоящее красное придёт карточкой тогда, когда команду РЕАЛЬНО
            # попробуют — её перехватит гард (деньги и живые таблицы спрашивают как спрашивали).
            _fcard = _forged_op_card(result)
            cm = bc.complete_task(tid, "failed", _fcard)
            log.warning("FORGED-OP id=%s: заявлен op=%s без гарда (origin=%s) → карточки нет, "
                        "терминальная карта, bridge_ok=%s",
                        tid, parse_op(result), _card_origin(result), cm.get("ok"))
            _series_note_terminal(task, "failed", _fcard)
            _maybe_dec_after(text, "failed")
        elif _maybe_card_duty(tid, result):
            # ДЕЖУРНЫЙ ПО КАРТОЧКАМ (CARD_DUTY=1): за карточкой доказанно нет операции, которую
            # «да» владельца могло бы разрешить → вопрос снят, задача финализирована внутри,
            # владельцу ушла заметка в ленту. Решение гарда НЕ менялось: команда так и не прошла.
            # В СЧЁТ СЕРИИ ВМЕШАТЕЛЬСТВОМ НЕ ИДЁТ: карточка до владельца не дошла вовсе (рамка
            # прямо: «ask без объекта владельцу не отправляется»), — только терминал записи.
            _series_note_terminal(task, "failed", result)
            _maybe_dec_after(text, "failed")     # как у forged-op: шаг цепи считается упавшим
        else:
            # Красная зона: НЕ исполняем. Ставим needs_approval — дев-бот спросит «да» Филиппа.
            rr = bc.set_needs_approval(tid, result)
            log.info("NEEDS_APPROVAL id=%s origin=%s bridge_ok=%s",
                     tid, _card_origin(result), rr.get("ok"))
            # ЖИВОЙ СЧЁТ СЕРИИ: тело карточки записываем СЕЙЧАС — после ответа очередь его
            # затрёт вердиктом, и вопрос «какая операция за ней стояла» станет неотвечаемым.
            _series_note_card(tid, task, result)
    else:
        # САМОПОЧИНКА (STEP_SELFHEAL=1): провал шага декомпозиции ИЛИ одиночной «тз:»/«задача:»
        # (расширение ст4) → думатель, 1 попытка. True = финализировано внутри (перерождение/
        # терминальный failed с диагнозом); False = прежний путь.
        if status == "failed" and _maybe_selfheal(tid, text, result, frm=str(task.get("from") or "")):
            return
        # ПРАВДА СТАТУСА: думатель за задачу не взялся → это ТЕРМИНАЛЬНЫЙ провал, по нему будут
        # планировать. Обрамляем кодом причины и следами работы в окне. Порядок важен: думатель
        # видит ИСХОДНЫЙ текст (его ⏱-гейт и формулировки не тронуты), обрамление — только в
        # том, что уходит в очередь и на глаза владельцу. Терминалы САМОГО думателя (halt /
        # повторный провал перерождения) обрамляются у себя, тем же _truthful_fail_last.
        if status == "failed":
            result = _truthful_fail_last(tid, result, task=task)
        # FACT-верификация (R11–R15, смягчено 20.07.2026): dev-done без блока FACT: НЕ мутирует
        # сохранённый result (инвариант «финал байт-в-байт») и НЕ форсирует куратора (CURATOR_SCOPE
        # цел). Видимость ⚠️ unverified даёт devbot в ТЕКСТЕ карточки 328 недеструктивно (по
        # _result_has_fact). _result_has_fact()/force_consult оставлены для devbot и юнит-теста §9.
        cm = bc.complete_task(tid, status, result)
        log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))
        _series_note_terminal(task, status, result)   # ЖИВОЙ СЧЁТ СЕРИИ: исход известен здесь
        _maybe_dec_after(text, status)          # шаг декомпозиции → halt-on-fail / сводка
        # Реестр фактов: done-финал followup-задачи куратора → зафиксировать вердикт (перезапишет pending)
        if status == "done" and _curator_on() and str(task.get("from") or "") == CURATOR_FROM:
            vf_key = _vf_normalize(text)
            if vf_key:
                _vf_write(vf_key, (result.splitlines()[0] if result else "")[:200], tid)
        _maybe_curator_single(task.get("from"), tid, text, result, status=status)   # куратор цели (CURATOR=1)


def process_na_reminders():
    """Напоминание Филиппу о needs_approval >3ч (пуш в личку) + hard-cap 24ч → failed.
    «нет» Филиппа devbot ставит failed сам — такие задачи сюда не попадают. (класс 23.07.2026)"""
    global _na_reminded
    r = bc.get_pending("needs_approval")
    if not r.get("ok"):
        n = _poll_fail("needs_approval")
        log.warning("na_reminders: мост не ответил (%s) — напоминания пропущены, подряд неудач: %d",
                    r.get("error") or "без поля error", n)
        return
    _poll_ok("needs_approval")
    active_ids: set = set()
    for task in r.get("items", []):
        tid = task.get("id")
        active_ids.add(tid)
        age = (_age_sec(task.get("updated")) or 0)
        if age > NA_LIFETIME:
            log.info("NEEDS_APPROVAL VPS id=%s hard-cap >%ss=24ч → failed", tid, NA_LIFETIME)
            # ТОТ ЖЕ класс, что задача 54 на ПК: работа сделана, сгорело подтверждение —
            # статус обязан назвать причину кодом и показать следы, а не молчать «провалена»
            bc.complete_task(tid, "failed", _truthful_fail(
                tid, "подтверждение не получено за 24ч — задача провалена (hard cap)",
                "approval_timeout", task=task))
            _na_reminded.discard(tid)
            _maybe_dec_after(task.get("task_text"), "failed")
        elif age > NA_REMINDER_SEC and tid not in _na_reminded:
            _na_reminded.add(tid)
            card = str(task.get("result") or "")[:300]
            msg = (f"⏰ задача #{tid} ждёт одобрения уже >3ч "
                   f"(✅/❌ в теме 1160 или «да {tid}»/«нет {tid}»):\n{card}")
            log.info("NEEDS_APPROVAL VPS id=%s >3ч — напоминание push личка", tid)
            try:
                import subprocess as _sp
                _sp.run([sys.executable, os.path.join(REPO, "notify.py"), "--need", msg],
                        timeout=15, check=False, capture_output=True)
            except Exception as e:
                log.warning("NA reminder push failed id=%s: %s", tid, e)
    _na_reminded &= active_ids   # очистить id задач, которые больше не needs_approval
    _series_cards_tick(active_ids)   # ЖИВОЙ СЧЁТ СЕРИИ: карточки, ушедшие из needs_approval


# ═══════════════ ЖИВОЙ СЧЁТ СЕРИИ ЦЕПОЧЕК (10.08.2026, рамка §8г) ═══════════════════════════
# Решение живёт в chain_series.py — чистой функции без рук (страж CHAIN_SERIES_PURE в гейте).
# Здесь только руки: собрать факты, положить состояние в СВОЙ файл и записать строку в журнал.
#
# ПОЧЕМУ СОСТОЯНИЕ ЖИВЁТ ЗДЕСЬ, А НЕ ПЕРЕСЧИТЫВАЕТСЯ ПО ОЧЕРЕДИ. Очередь ЗАТИРАЕТ тело карточки
# её же вердиктом: у задачи, дошедшей до владельца, `result` на момент needs_approval держал
# карточку, а после ответа там лежит «отклонено Филиппом» либо рапорт конверта. Замер 10.08
# померил этот пробел числом: из 106 вмешательств окна тело карточки ВОССТАНОВИМО у 46, у 60 —
# нет. Значит вопрос «какая операция стояла за карточкой» после ответа из очереди уже не задать,
# а демон в момент рождения карточки держит её тело в руках. Отсюда и правило рамки «где
# считать»: исход известен демону в момент терминала — там и писать.
#
# СЧЁТ НИЧЕГО НЕ РЕШАЕТ. Он не ставит задач, не трогает очередь и не меняет ни одного вердикта —
# только пишет свой файл и строку в журнал. Ошибка счёта поэтому стоит неверного числа.
# ОТКАТ: CHAIN_SERIES=0 в .env + рестарт демона → ветка мертва ДО сбора фактов.
CHAIN_SERIES_FILE = os.path.join(REPO, "chain_series.json")
CHAIN_SERIES_TEST_FILE = "/tmp/cc_chain_series_test.json"   # тест-прогон в боевое НЕ пишет
SERIES_KEEP = _env_int("SERIES_KEEP", 400)        # сколько цепочек помним (файл не растёт вечно)
SERIES_WINDOWS = 40                               # окон исполнения для приписки рестартов
SERIES_UNITS = (("splinter", "bot.py"),
                ("orchestrator-daemon", "orchestrator_daemon.py"),
                ("wa-webhook", "wa_webhook.py"))
# Хвост после конца задачи, в который её ОТЛОЖЕННЫЙ рестарт (`systemd-run --on-active=10s`,
# правило самомодификации) ещё считается своим. Без хвоста система штрафовала бы себя за
# собственное правило, объявляя плановый самрестарт ремонтом руками.
SERIES_OWN_GRACE = 180


def _series_on():
    """CHAIN_SERIES в .env: по умолчанию ВКЛЮЧЕНО, «0» выключает ветку целиком (ДО чтения
    фактов). Дефолт-«включено» здесь законен ровно потому, что счёт ничего не решает."""
    return (os.environ.get("CHAIN_SERIES") or "1").strip() != "0"


_IS_DAEMON = False   # ставится в main(): БОЕВОЕ состояние серии пишет только боевой процесс


def _series_file():
    """Куда писать состояние. ORCH_TEST_MODE → ВРЕМЕННЫЙ файл: зеркало дисциплины `_drift_dir` —
    тест не пишет в боевое состояние никогда, иначе счёт серии врал бы прогонами гейта.
    CC_SERIES_FILE — явная подмена (осознанный вызов из своего сьюта).

    ТРЕТИЙ РУБЕЖ — ЛИЧНОСТЬ ПИШУЩЕГО, и он заведён по ЖИВОМУ ФАКТУ, а не про запас. Признак
    тест-прогона живёт в окружении, а харнесс, запущенный руками (`venv/bin/python3 своя_проба.py`),
    НЕ НЕСЁТ НИ ОДНОГО из четырёх имён изоляции — импортировал демона, позвал руки счёта и написал
    в боевой файл. Ровно это и случилось 10.08.2026: боевой `chain_series.json` к 18:25 держал
    синтетическую цепочку 101 (`created` пуст, окна исполнения нулевой длины), тогда как боевой
    демон поднят в 08:08:56 и кода счёта в памяти не имел вовсе — в его журнале НИ ОДНОЙ строки
    «СЕРИЯ». То есть боевое состояние метрики целиком было следом пробы. Поэтому боевой путь
    отдаётся ТОЛЬКО процессу, который и есть демон (флаг ставит `main()`), а всякий импорт со
    стороны — в тест-файл. Направление ошибки названо: промах этого рубежа стоит СЧЁТА (демон
    считал бы во временный файл), а не подлога в боевом, — и виден он сразу, первой же сверкой."""
    explicit = (os.environ.get("CC_SERIES_FILE") or "").strip()
    if explicit:
        return explicit
    if (os.environ.get("ORCH_TEST_MODE") or "").strip() or not _IS_DAEMON:
        return CHAIN_SERIES_TEST_FILE
    return CHAIN_SERIES_FILE


def _series_load():
    """Состояние с диска или None — «НЕ ПРОЧИТАНО». Пустой словарь здесь был бы слепым: он
    неотличим от честного «серия только началась», и счёт молча обнулялся бы на каждом сбое
    диска (класс «нуль по неразбору»). Различение отдаёт `_series_state`."""
    try:
        with open(_series_file(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("серия: состояние битое (%s) — счёт начнётся заново, и это будет видно "
                    "в поле started_counting", e)
        return None
    except Exception as e:
        log.warning("серия: состояние не прочитано (%s) — счёт начнётся заново", e)
        return None


def _series_state():
    """Состояние для правки. Не прочитано → чистое, и МОМЕНТ НАЧАЛА СЧЁТА записывается в него:
    обнулённая серия обязана сама говорить, с какого времени она считается."""
    st = _series_load()
    if st is None:
        st = {}
    st.setdefault("started_counting", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return st


def _series_save(state):
    """Атомарная запись (tmp + replace): оборванная запись не оставит битого файла."""
    path = _series_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def _series_units_now():
    """{юнит: метка старта} живых процессов. Юнита нет / проба сбоит → его в словаре нет вовсе
    (о мёртвом сервисе говорит health, а не счётчик серии)."""
    out = {}
    for unit, entry in SERIES_UNITS:
        try:
            p = prod_drift.live(unit, entry)
        except Exception:
            p = None
        if p and p.get("started"):
            out[unit] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(p["started"]))
    return out


def _series_commits(result, since):
    """Хеши из отчёта, ДОКАЗАННО доехавшие в origin/main. Доказательство внешнее (git), а не
    слово отчёта: «закоммитил» в тексте весом не является. git недоступен → пусто, то есть вес
    по коммитам не доказан — молчим, а не додумываем."""
    toks = set(re.findall(r"\b([0-9a-f]{7,40})\b", str(result or "").lower()))
    out = (prod_drift._git(["log", "origin/main", "--format=%H", "--since=" + str(since or ""),
                            "-n", "200"]) or "") if toks else ""
    have = [s.strip() for s in out.splitlines() if len(s.strip()) == 40]
    return sorted({s[:7] for s in have for t in toks if s.startswith(t)})


def _series_chain(state, root, task):
    """Запись цепочки в состоянии (создать при первом касании)."""
    ch = state.setdefault("chains", {}).get(str(root))
    if ch is None:
        lane = str((task or {}).get("lane") or "vps")
        ch = state["chains"][str(root)] = {
            "root": int(root), "lane": lane,
            "created": chain_series.stamp((task or {}).get("created")),
            "closed_at": "", "statuses": {}, "cards": [], "refusals": [],
            # ВЕС ПОЛОСЫ pc ОТСЮДА НЕ НАБЛЮДАЕМ (чужой репозиторий) — это «неизвестно», а не
            # «нуль веса»: иначе слепота стала бы обвинением (класс «нуль по неразбору»).
            "weight": {"commits": [], "restarts": 0, "known": lane != "pc"},
        }
    return ch


def _series_root(tid, text, state):
    """Корень цепочки записи. Родитель ищется по маркеру и разрешается ТРАНЗИТИВНО через уже
    известные цепочки состояния (конверт → карточка владельцу → цель → корень)."""
    kind, par = chain_series.parent_of(text)
    seen = {int(tid)}
    while par is not None and par not in seen:
        seen.add(par)
        # Родителя ищем и среди КАРТОЧЕК цепочки, а не только среди её записей: сводная карточка
        # владельцу терминала в process_new не имеет (её закрывает ветка одобрения), и без этой
        # строки конверт «[конверт одобренной заявки N]» заводил бы СВОЮ цепочку — плоский счёт,
        # который рамка запрещает прямо.
        owner = None
        for r, ch in (state.get("chains") or {}).items():
            if int(r) == par or str(par) in (ch.get("statuses") or {}) \
                    or par in {c.get("id") for c in (ch.get("cards") or [])}:
                owner = int(r)
                break
        if owner is None or owner == par:
            return par, kind
        par = owner
    return int(tid), kind


def _series_note_card(tid, task, what):
    """КАРТОЧКА РОДИЛАСЬ. Тело записываем СЕЙЧАС — после ответа очередь его затрёт. Операции
    называет curator_ops: ТОТ ЖЕ словарь, которым машина зовёт операции сама."""
    if not _series_on():
        return
    try:
        state = _series_state()
        root, _kind = _series_root(tid, str((task or {}).get("task_text") or ""), state)
        ch = _series_chain(state, root, task)
        ops = [o["key"] for o in curator_ops.operations(str(what or ""))]
        ch["cards"] = [c for c in ch["cards"] if c.get("id") != tid]
        ch["cards"].append({"id": tid, "open": True, "born": chain_series.stamp(
            time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())), "ops": ops})
        _series_save(state)
        log.info("серия: карточка id=%s цепочки %s записана (операции: %s)",
                 tid, root, ",".join(ops) or "нет")
    except Exception as e:
        log.warning("серия: карточку id=%s записать не удалось (%s) — счёт не тронут", tid, e)


def _series_note_terminal(task, status, result):
    """ТЕРМИНАЛ ЗАПИСИ. Здесь исход известен — здесь и пишем: статус, необъяснённый отказ,
    окно исполнения (для приписки рестартов) и доказанные коммиты (вес)."""
    if not _series_on():
        return
    try:
        tid = int((task or {}).get("id"))
        text = str((task or {}).get("task_text") or "")
        state = _series_state()
        root, kind = _series_root(tid, text, state)
        ch = _series_chain(state, root, task)
        ch["statuses"][str(tid)] = str(status or "")
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        ch["closed_at"] = max(ch.get("closed_at") or "", now)
        why = chain_series.refusal(status, result)
        if why:
            ch["refusals"].append({"id": tid, "reason": why, "at": now})
        if chain_series.is_manual_card(result):
            # Работа ушла в руки владельца. Операция ВЫСШЕГО ВИДА §7 — это воля по конструкции
            # (система не вправе делать её сама), своя оранжевая операция — ремонт руками.
            v = chain_series.sort_manual_card(
                [o["key"] for o in curator_ops.operations(str(result or ""))])
            ch["cards"].append({"id": tid, "open": False, "sort": v["sort"], "why": v["why"],
                                "at": now})
        if ch["weight"].get("known"):
            for sha in _series_commits(result, ch.get("created") or ""):
                if sha not in ch["weight"]["commits"]:
                    ch["weight"]["commits"].append(sha)
        # _LAST_RUN["started"] — ISO-строка начала ИСПОЛНЕНИЯ (не постановки). Окно берётся
        # именно по ней: `created` очереди — момент, когда задачу положили, а простоять в new
        # она может часами, и по такому окну «своей» оказалась бы любая перезагрузка мира.
        lo = chain_series.stamp(_LAST_RUN.get("started")) if _LAST_RUN.get("task") == tid else ""
        if lo:
            wins = state.setdefault("windows", [])
            wins.append({"root": int(root), "lo": lo, "hi": now})
            state["windows"] = wins[-SERIES_WINDOWS:]
        _series_derive(state)
        _series_save(state)
    except Exception as e:
        log.warning("серия: терминал id=%s не записан (%s) — счёт не тронут",
                    (task or {}).get("id"), e)


def _series_cards_tick(active_na):
    """РАЗ В ЦИКЛ: заметить смену операционного состояния и закрыть карточки, ушедшие из
    needs_approval. Сорт карточки ставится ЗДЕСЬ — когда известно и что она просила (тело
    записано при рождении), и успела ли операция случиться сама (старты юнитов).

    ОТВЕТ ВЛАДЕЛЬЦА В РЕШЕНИЕ НЕ ВХОДИТ ВОВСЕ: «да» и «нет» отсюда неразличимы по построению —
    карточка просто перестала висеть. Ровно этого и требует рамка: сорт по ОПЕРАЦИИ."""
    if not _series_on():
        return
    try:
        state = _series_state()
        now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        units, prev = _series_units_now(), (state.get("units") or {})
        changes = state.setdefault("changes", [])
        first = not prev
        for unit, at in units.items():
            if prev.get(unit) == at:
                continue
            if not first:               # первое наблюдение НЕ обвиняет: истории у нас ещё нет
                changes.append({"family": "service:" + unit, "at": at, "unit": unit})
                _series_attribute(state, unit, at)
        state["units"] = units
        state["changes"] = changes[-200:]

        closed = 0
        for ch in (state.get("chains") or {}).values():
            for c in ch.get("cards") or []:
                if not c.get("open") or c.get("id") in (active_na or set()):
                    continue
                v = chain_series.sort_card(c.get("ops"), state.get("changes"), c.get("born"), now)
                c.update({"open": False, "sort": v["sort"], "why": v["why"], "at": now})
                closed += 1
                log.info("серия: карточка id=%s закрыта, сорт=%s — %s",
                         c.get("id"), v["sort"], v["why"][:120])
        d = _series_derive(state)
        _series_save(state)
        if closed:
            log.info("СЕРИЯ: %s", chain_series.render(d))
    except Exception as e:
        log.warning("серия: тик не отработал (%s) — счёт не тронут", e)


def _series_attribute(state, unit, at):
    """Старт юнита: чей он. Попал в окно исполнения задачи (+хвост на отложенный рестарт) → это
    СВОЯ работа цепочки, она идёт ей в вес. Не попал ни в одно окно → РЕМОНТ РУКАМИ: за систему
    сделали то, что она обязана была сделать сама. Приписываем последней цепочке — у события
    мира своего номера в очереди нет, и приписка тут условна, о чём сказано прямо."""
    for w in reversed(state.get("windows") or []):
        if str(w.get("lo") or "") <= at <= _series_plus(str(w.get("hi") or ""), SERIES_OWN_GRACE):
            ch = (state.get("chains") or {}).get(str(w.get("root")))
            if ch:
                ch["weight"]["restarts"] = int(ch["weight"].get("restarts") or 0) + 1
                return
    # Полоса важна: перезапускают юниты VPS, и повесить это на ПК-цепочку значило бы назвать
    # чужого виновника. Приписываем последней СВОЕЙ цепочке — приписка условна и названа прямо.
    roots = sorted((int(r) for r, ch in (state.get("chains") or {}).items()
                    if str(ch.get("lane") or "vps") != "pc"), reverse=True)
    if roots:
        (state["chains"][str(roots[0])]["cards"]).append(
            {"id": None, "open": False, "sort": chain_series.MANUAL, "at": at,
             "why": "перезапуск %s в %s не попадает ни в одно окно исполнения — сделано руками"
                    % (unit, at)})
        log.info("серия: перезапуск %s в %s не приписан ни одной задаче → ремонт руками", unit, at)


def _series_plus(ts, sec):
    """Метка + секунды (в её же строковом виде; через полночь — граница суток)."""
    try:
        h, m, s = (int(x) for x in ts[11:].split(":"))
    except (ValueError, IndexError):
        return ts
    t = h * 3600 + m * 60 + s + int(sec)
    return ts[:11] + ("23:59:59" if t >= 86400
                      else "%02d:%02d:%02d" % (t // 3600, (t % 3600) // 60, t % 60))


def _series_derive(state):
    """Пересчитать вердикты и серию чистой функцией; лишние цепочки выгрузить."""
    chains = state.get("chains") or {}
    for r in sorted(chains, key=lambda x: int(x))[:-SERIES_KEEP] if len(chains) > SERIES_KEEP \
            else []:
        chains.pop(r, None)
    verdicts = []
    for r in sorted(chains, key=lambda x: int(x)):
        ch = dict(chains[r])
        ch["statuses"] = list((chains[r].get("statuses") or {}).values())
        ch["cards"] = [c for c in (chains[r].get("cards") or []) if not c.get("open")]
        verdicts.append(chain_series.chain_verdict(ch))
    d = chain_series.series(verdicts)
    # ПАМЯТЬ ПРОТИВ УРЕЗКИ. `best` и `breaks` считаются по цепочкам, которые состояние ЕЩЁ помнит
    # (потолок SERIES_KEEP), поэтому забывание старых цепочек молча УКОРАЧИВАЛО бы рекорд и
    # стирало дату последнего обрыва — то есть файл переставал бы отвечать на два из четырёх
    # вопросов рамки §8г, ничего об этом не сказав. Оба поля переносятся вперёд: рекорд не
    # уменьшается никогда, последний обрыв держится, пока его не сменит новый.
    prev = state.get("derived") or {}
    d["best_ever"] = max(int(prev.get("best_ever") or 0), int(d.get("best") or 0))
    if not d.get("last_break"):
        d["last_break"] = prev.get("last_break")
    d["line"] = chain_series.render(d)
    d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["derived"] = d
    return d


# ═══════════════ ДЕТЕКТОР ДРЕЙФА ПРОДА (06.08.2026, решение владельца «без рестарта») ═══════
# Разбор и решение живут в prod_drift.py — модуле, который НЕ УМЕЕТ ни перезапускать, ни писать,
# ни отправлять (инвариант PROD_DRIFT_READONLY в гейте: словарь внешних команд = читающий git,
# open только на чтение, импорты по списку). Здесь — только руки: спросить факты, отдать заметку
# в ленту 829 и запомнить эпизод, чтобы не повторяться.
#
# АВТОМАТИКИ РЕСТАРТА НЕТ НИ В КАКОМ ВИДЕ. Заметка информационная: кнопок нет, номера нет, слова
# «да» нет — отвечать не на что и нечем. Когда перезапускать прод, решает владелец; система лишь
# перестаёт молчать о разрыве (разбор цели 355: демон 49 % недели позади git, splinter 39 %,
# самый долгий разрыв 34,4 ч закрыт ПОСТОРОННИМ апгрейдом пакетов — разрыв не видел никто).
#
# ПОЧЕМУ ПОСЛЕДНИМ В ЦИКЛЕ: детектор ходит в /proc и зовёт git, а очередь ждать не должна.
# ПОЧЕМУ ТРОТТЛИНГ: цикл демона — минута, а разрыв меряется часами; лишние 60 запусков git в час
# не купили бы ни одной заметки раньше.
# ОТКАТ: DRIFT_HOURS=0 в .env + рестарт демона → ветка мертва целиком (вердикт пуст ДО сбора
# фактов, git не зовётся ни разу).
DRIFT_STATE_DIR = "/tmp/cc_drift_seen"                # эпизоды, о которых уже сказали
DRIFT_EVERY_SEC = _env_int("DRIFT_EVERY_SEC", 900)    # как часто вообще собирать факты
DRIFT_KEEP = 16                                       # сколько ключей эпизодов помним
_drift_next = 0.0                                     # ближайший разрешённый замер (троттлинг)


def _drift_dir():
    """Каталог состояния. ORCH_TEST_MODE → тест-каталог: зеркало дисциплины _guard_markers_sweep,
    тест НЕ пишет в боевой каталог никогда. CC_DRIFT_DIR — явная подмена (осознанный вызов)."""
    explicit = (os.environ.get("CC_DRIFT_DIR") or "").strip()
    if explicit:
        return explicit
    if (os.environ.get("ORCH_TEST_MODE") or "").strip():
        return DRIFT_STATE_DIR + "_test"
    return DRIFT_STATE_DIR


def _drift_seen(key):
    """Об этом эпизоде уже говорили? FAIL-SAFE: файла нет / мусор → False, то есть скажем ещё раз.
    Направление выбрано в сторону лишней заметки: молчание — ровно то, что мы чиним."""
    try:
        with open(os.path.join(_drift_dir(), "seen.json"), encoding="utf-8") as f:
            return str(key) in (json.load(f) or {}).get("keys", [])
    except Exception:
        return False


def _drift_mark(key):
    """Запомнить эпизод (ключ = юнит · старт процесса · первый неподхваченный коммит).
    Best-effort: диск недоступен → худшее, что случится, — повтор заметки на следующем замере."""
    d = _drift_dir()
    keys = []
    try:
        with open(os.path.join(d, "seen.json"), encoding="utf-8") as f:
            keys = list((json.load(f) or {}).get("keys", []))
    except Exception:
        keys = []
    keys = ([str(key)] + [k for k in keys if k != str(key)])[:DRIFT_KEEP]
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "seen.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"keys": keys}, f)
        os.replace(tmp, os.path.join(d, "seen.json"))
    except Exception as e:
        log.warning("дрейф прода: состояние не сохранено (%s) — возможен повтор заметки", e)


def _maybe_prod_drift(now=None):
    """DRIFT_HOURS > 0 → сказать в ленту 829 о живом процессе, который отстал от origin/main.
    → список ключей эпизодов, о которых сказали В ЭТОТ раз (для лога и теста).

    НИ ОДИН ПРОЦЕСС ЗДЕСЬ НЕ ПЕРЕЗАПУСКАЕТСЯ: ветка умеет ровно два действия — прочитать факты и
    отправить строку. FAIL-SAFE на каждом шаге (флаг, сбор фактов, вердикт, канал, состояние) →
    молчание, то есть поведение байт-в-байт как без детектора."""
    global _drift_next
    try:
        hours = prod_drift.hours_env()
        if hours <= 0:
            return []
        now = time.time() if now is None else float(now)
        if now < _drift_next:
            return []
        _drift_next = now + DRIFT_EVERY_SEC
        notes = prod_drift.verdict(prod_drift.snapshot(now=now), hours)
    except Exception as e:
        log.warning("дрейф прода: замер пропущен (%s)", e)
        return []
    said = []
    for n in notes:
        try:
            if _drift_seen(n.get("key")):
                continue
            import notify
            if not notify.send_feed(prod_drift.render(n, "VPS")):
                log.warning("ДРЕЙФ ПРОДА: %s позади на %s — заметка НЕ ушла (адрес/сеть); "
                            "скажем на следующем замере", n.get("unit"),
                            prod_drift.human_age(n.get("age")))
                continue
            _drift_mark(n.get("key"))
            said.append(n.get("key"))
            log.info("ДРЕЙФ ПРОДА: %s (PID %s) позади origin/main на %s — файлы: %s; первый "
                     "неподхваченный коммит %s. Рестарт НЕ делается: решение владельца",
                     n.get("unit"), n.get("pid"), prod_drift.human_age(n.get("age")),
                     ", ".join(n.get("files") or []), n.get("sha"))
        except Exception as e:
            log.warning("дрейф прода: заметка не ушла (%s)", e)
    return said


# ════════════════════ ПУЛЬС ОБОРОТА — О2 СЛОЯ ОЖИДАНИЙ (07.08.2026) ════════════════════════
# ЕДИНСТВЕННАЯ НОВАЯ ЗАПИСЬ ВО ВСЁМ СЛОЕ. Ожидание О2 («главный процесс произвёл свой результат,
# а не просто существует») требует продукта, который процесс выдаёт И БЕЗ СПРОСА: успешный опрос
# очереди не логируется вовсе, поэтому «работает вхолостую» и «умер» снаружи выглядят одинаково
# (06.08 в журнале есть окно 10 ч 07 м без единой строки — и это было здоровьем).
#
# HEARTBEAT ДЛЯ ЭТОГО НЕ ГОДИТСЯ и намеренно не используется: _heartbeat_loop — отдельный поток,
# он стучит независимо от того, делает ли claude -p хоть что-нибудь. Он доказывает жизнь потока,
# который его шлёт, и ничего больше.
#
# ПОЧЕМУ В КОНЦЕ cycle(), А НЕ В НАЧАЛЕ: продукт — состоявшийся ОБОРОТ, а не вход в него. Ложного
# молчания на сбоях моста это не даёт: get_pending-ошибки гасятся внутри процедур (process_new
# просто выходит), а строк «ошибка цикла» в журнале демона за всю его историю — 0.
#
# СУДИТ ЭТОТ ФАКТ НЕ ДЕМОН: пульс читает expectations_run.py из таймера яруса 2 — наблюдатель не
# может жить на том, за чем следит. Здесь только запись, никаких решений и никакого канала.
EXPECT_PULSE_DIR = "/tmp/cc_expect_pulse"
_EXPECT_STARTED = time.time()      # старт ЭТОГО экземпляра демона (эпизод О2 ключуется им)
_expect_turns = 0                  # сколько оборотов сделал экземпляр
_expect_last_ts = 0.0              # когда состоялся ПОСЛЕДНИЙ оборот (штамп занятости его не двигает)


def _expect_pulse_dir():
    """Каталог пульса. ORCH_TEST_MODE → тест-каталог (тест не пишет в боевой), CC_EXPECT_DIR —
    явная подмена. Зеркало дисциплины _drift_dir."""
    explicit = (os.environ.get("CC_EXPECT_DIR") or "").strip()
    if explicit:
        return os.path.join(explicit, "cc_expect_pulse")
    if (os.environ.get("ORCH_TEST_MODE") or "").strip():
        return EXPECT_PULSE_DIR + "_test"
    return EXPECT_PULSE_DIR


def _expect_write(busy=None):
    """Записать пульс атомарно. busy=None — чистый оборот (ключа busy в файле НЕТ вовсе, то есть
    штамп занятости снимается САМИМ фактом состоявшегося оборота, отдельной уборки не требуется).
    Best-effort и МОЛЧА: сбой записи не смеет уронить цикл — худшее, что случится, — ярус 2
    скажет «оборота нет», то есть ошибётся в сторону заметки, а не молчания."""
    try:
        d = _expect_pulse_dir()
        os.makedirs(d, exist_ok=True)
        rec = {"ts": _expect_last_ts, "n": _expect_turns,
               "pid": os.getpid(), "started": _EXPECT_STARTED}
        if busy:
            rec["busy"] = busy
        tmp = os.path.join(d, "pulse.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(d, "pulse.json"))
    except Exception:                                                # noqa: BLE001
        pass


def _expect_pulse():
    """Отметить состоявшийся оборот — и ТЕМ ЖЕ действием снять штамп занятости."""
    global _expect_turns, _expect_last_ts
    _expect_turns += 1
    _expect_last_ts = time.time()
    _expect_write()


def _expect_busy(task_id, limit_sec):
    """Штамп «занят объявленной синхронной работой» ПЕРЕД claude -p (исполнитель, планировщик,
    думатель). Ярус 2 иначе читает длинный заход как остановку демона: claude -p крутится ВНУТРИ
    cycle(), а пульс пишется последней строкой — замер 10.08.2026 дал 10 ложных заметок из 10.

    Штамп НЕ подменяет продукт: поле ts (последний СОСТОЯВШИЙСЯ оборот) не двигается, меняется
    только объявление «я занят с T и обещал себе уложиться в L». Каждый следующий claude -p
    перештамповывает окно своим таймаутом, поэтому доверие всегда привязано к ИДУЩЕМУ вызову,
    а не к самому длинному за оборот. Снимается штамп состоявшимся оборотом (_expect_pulse)."""
    try:
        _expect_write({"since": time.time(), "limit": float(limit_sec or 0),
                       "task": task_id, "pid": os.getpid()})
    except Exception:                                                # noqa: BLE001
        pass


def cycle():
    """Один проход: подобрать сирот in_progress (урок 138) → довести одобренное красное
    (approved) → добрать хвосты декомпозиций, финализированные мимо демона (сводка) → надзор
    цепей ПК-театра (полоса pc, read-only + релиз/хуки своих цепей) → взять новое (new).
    Выгрузка завершённых цепей (_prune_chain_cache): cheap check, только при превышении потолка.
    Уборка осиротевших guard-маркеров (_guard_markers_sweep, цель 36): локальная ФС, до сети.
    ПОСЛЕДНИМ — детектор дрейфа прода (_maybe_prod_drift, read-only + троттлинг): очередь важнее,
    а разрыв меряется часами. Он только ГОВОРИТ (заметка в ленту), ничего не перезапуская.
    САМОЙ ПОСЛЕДНЕЙ строкой — пульс оборота (_expect_pulse): факт «оборот СОСТОЯЛСЯ» для яруса 2
    слоя ожиданий. Пишется молча и best-effort; судит этот факт таймер, а не демон."""
    _prune_chain_cache()
    _guard_markers_sweep()      # осиротевшие /tmp/cc_guard_block/*.json старше GUARD_MARKER_TTL
    _fixture_reap_open()        # закрыть фикстуры в needs_approval/approved (класс 193 рубеж 4)
    process_orphans()
    process_na_reminders()      # напоминание >3ч + hard-cap 24ч для needs_approval (класс 23.07)
    process_approved()
    process_dec_tails()
    process_pc_chains()
    process_new()
    _maybe_prod_drift()         # ДЕТЕКТОР ДРЕЙФА: read-only, только говорит (заметка в ленту 829)
    _expect_pulse()             # ПУЛЬС ОБОРОТА (О2): факт «оборот состоялся» для яруса 2


def main():
    global _IS_DAEMON
    _IS_DAEMON = True          # с этой строки боевой файл состояния серии пишет этот процесс
    _banner_avail = _mem_available_mb() or 0
    _banner_crss = _live_claude_rss_mb() or 0
    _banner_cprocs = _live_claude_count() or 0
    log.info("=== ДЕМОН СТАРТ (poll=%ss, task_timeout=%ss/dev=%ss, approved_ttl=%ss, na_lifetime=%ss, auto_ops=%s, claude=%s, "
             "selfheal=%s, plan_adapt=%s, curator=%s, curator_scope=%s, gate_single_sel=%s, "
             "drift=%sч/%sс, "
             "fact_ttl=%ss, model=%s, fallback=%s, executor_model=%s, effort=%s, "
             "mem_gate=%s(min=%dMB avail=%dMB), "
             "rss_gate=%s(max=%dMB cur=%dMB), proc_gate=%s(max=%d cur=%d), chain_cache=%d) ===",
             POLL_SEC, TASK_TIMEOUT, TASK_TIMEOUT_DEV, APPROVED_TTL, NA_LIFETIME, ",".join(AUTO_OPS), CLAUDE_BIN,
             int(_selfheal_on()), int(_plan_adapt_on()), int(_curator_on()), int(_curator_scope_on()),
             int(_gate_single_selective_on()),
             prod_drift.hours_env(), DRIFT_EVERY_SEC,
             FACT_TTL, ORCH_MODEL, ORCH_MODEL_FALLBACK, EXECUTOR_MODEL,
             EXECUTOR_EFFORT,
             "on" if MEM_MIN_MB > 0 else "off", MEM_MIN_MB, _banner_avail,
             "on" if CLAUDE_RSS_TOTAL_MB > 0 else "off", CLAUDE_RSS_TOTAL_MB, _banner_crss,
             "on" if MAX_CLAUDE_PROCS > 0 else "off", MAX_CLAUDE_PROCS, _banner_cprocs,
             MAX_CHAIN_CACHE)
    while _running:
        try:
            cycle()
        except Exception as e:
            log.exception("ошибка цикла: %s", e)
        # дробный сон, чтобы остановка по сигналу была быстрой (не ждать весь POLL_SEC)
        for _ in range(POLL_SEC):
            if not _running:
                break
            time.sleep(1)
    log.info("=== ДЕМОН ОСТАНОВЛЕН (рубильник/сигнал) ===")


if __name__ == "__main__":
    main()
