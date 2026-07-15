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
from bridge_client import BridgeClient

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
CLAUDE_BIN = "/usr/bin/claude"
# РОЛЬ-РАЗВОД PERMISSIONS (08.07.2026): headless-задачи получают СТРОГИЙ доп-слой настроек через
# `--settings` — ask на clasp push/redeploy/deploy/run/version/create-version/deployments.
# Precedence движка deny>ask>allow действует ПОВЕРХ всех источников → этот ask бьёт allow из
# .claude/settings.local.json владельца (интерактивные Termux-сессии clasp'ают без промптов,
# headless — нет). В -p режиме ask = авто-отказ → claude выводит NEEDS_APPROVAL, как раньше.
# Файл в корне репо (git-истина): в .claude/ headless писать не может (гейт движка).
# Fail-closed: файла нет → CLI падает с ошибкой → честный failed, а не тихая потеря забора.
HEADLESS_SETTINGS = os.path.join(REPO, "headless_settings.json")
# КОНДУКТОР МОДЕЛИ (06.07.2026): headless-исполнитель по умолчанию — Claude Fable 5, фолбэк —
# прежняя рабочая модель (Opus 4.8 1M = CLI-дефолт до этой правки). Вынесено в env, НЕ хардкод:
# смена модели в будущем = правка .env (ORCH_MODEL / ORCH_MODEL_FALLBACK), без правки кода.
# Фолбэк исполняет САМ CLI флагом --fallback-model В РАМКАХ ОДНОГО вызова при
# overload/недоступности/лимите/неверном имени primary → задача НЕ исполняется дважды
# (проверено 06.07: невалидная primary + --fallback-model=opus → CLI сам берёт opus, exit 0,
# modelUsage=opus). Хардкода без фолбэка нет: упёршись в лимит Fable, автоматика не встаёт.
ORCH_MODEL = (os.environ.get("ORCH_MODEL") or "fable").strip() or "fable"
ORCH_MODEL_FALLBACK = (os.environ.get("ORCH_MODEL_FALLBACK") or "claude-opus-4-8[1m]").strip() or "claude-opus-4-8[1m]"
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


def _normalize_model(name):
    """Короткий алиас → полный model id (класс 404 b18ad08). Полные id и незнакомые
    значения — как есть; суффиксы вида [1m] сохраняются («opus-4-8[1m]» → «claude-opus-4-8[1m]»)."""
    n = (name or "").strip()
    low = n.lower()
    if low in _MODEL_ALIASES:
        return _MODEL_ALIASES[low]
    if re.match(r"^(fable|opus|sonnet|haiku)-\d", low):  # семейство-версия без префикса claude-
        return "claude-" + n
    return n


_EXECUTOR_MODEL_RAW = (os.environ.get("EXECUTOR_MODEL") or "").strip()
EXECUTOR_MODEL = _normalize_model(_EXECUTOR_MODEL_RAW) if _EXECUTOR_MODEL_RAW else ORCH_MODEL
RESULT_MAX = 4500        # Bridge режет result на 5000 — оставляем запас
LOG_PATH = os.path.join(REPO, "orchestrator_daemon.log")

# §12 корень 1 (06.07.2026): под тест-прогоном НЕ трогаем боевой orchestrator_daemon.log —
# сам ИМПОРТ модуля (test_orchestrator_*/test_convert_loop_break делают `import orchestrator_daemon`)
# конфигурировал FileHandler на ЖИВОЙ лог, и любой log.info фикстуры лил строки в него. Тест-прогон
# определяем по: активный pytest / entry-point tests/test_*.py / явный флаг ORCH_DAEMON_TEST=1 →
# логгер в NullHandler (ни файла, ни консоли). Боевой демон (systemd, argv=orchestrator_daemon.py) —
# как раньше, пишет в LOG_PATH.
_UNDER_TEST = (
    "pytest" in sys.modules
    or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    or os.path.basename((sys.argv[0] if sys.argv else "") or "").startswith("test_")
    or os.environ.get("ORCH_DAEMON_TEST") == "1"
)
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
#      погашен — мы ещё живы и успеваем её увидеть). Ручной systemctl stop/restart из Termux
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
# без Termux, вкл. прод-фикс 3978a91). restart splinter теперь CC делает САМ оранжевым циклом
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
    "каждый значимый шаг — строка в cc_log (write_doc name=cc_log, запись ПОД врезкой) + пульс "
    "(write_doc name=pulse) ОДНОЙ операцией; статус честно: «технически готово» отдельно от "
    "«функционально подтверждено».\n"
    "КАРТА ДЕЙСТВИЙ:\n"
    "- Зелёное/оранжевое (чтение, диагностика, правки кода, тесты, git commit, git push) — делай САМ; "
    "git push по циклу гейт→push→отчёт, БЕЗ маркера.\n"
    "- systemctl restart splinter — тоже делай САМ, оранжевым циклом: гейт (venv/bin/python3 gate.py, "
    "только при exit 0) → systemctl restart splinter → проверка чистого старта (systemctl is-active "
    "active + свежий старт-лог в splinter.log без ошибок) → в сводке отчитайся «нужен был restart — "
    "сделал, старт чистый». При failed/грязном старте — откат на прошлый рабочий коммит + restart + "
    "честный отчёт. Маркер op=restart_splinter НЕ выводи (он остаётся только аварийным фоллбэком).\n"
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
    "clasp deploy/redeploy/push, sqlite3 CLI на memory.db, set_fleet_oil/set_fleet_service, "
    "confirmed=true, delete_event, любое удаление — НЕ выполняй и НЕ ищи обходных путей: выведи РОВНО "
    "одну строку «NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия · на что смотреть>» "
    "и заверши работу (исполнит человек).\n"
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
    "«NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия>».\n\n"
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
# безопасна: лишь спрашивает Филиппа, красное НЕ исполняется; op=other → человек в Termux).
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
_HEADLESS_IMPOSSIBLE_RE = re.compile(
    r"clasp|redeploy|\bsqlite3\b|set_fleet_(?:oil|service)|delete_event|confirmed\s*=\s*true|"
    r"лист\s*1|\bcrm\b|зарплат|байки|транзакц|проводк|деньг|касс|удал(?:и|ени|яе|ён)|календар",
    re.IGNORECASE,
)


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
    "многошаговых планов.\n\n"
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
    "многошаговых планов.\n\n"
)


def _selfheal_on():
    """Флаг STEP_SELFHEAL=1 в .env (демон load_dotenv'ит на старте). 0/нет → прежнее поведение."""
    return (os.environ.get("STEP_SELFHEAL") or "").strip() == "1"


def _is_convert(text):
    """True → задача является конвертом одобренной op=other (родилась из «да» Филиппа). Слой 1."""
    return bool(_CONVERT_RE.match(str(text or "")))


def _is_headless_impossible(*texts):
    """True → в тексте(ах) есть маркер заведомо headless-невозможного красного действия. Слой 2."""
    blob = " ".join(str(t or "") for t in texts)
    return bool(_HEADLESS_IMPOSSIBLE_RE.search(blob))


def _manual_card(what, orig_text=""):
    """Терминальная карточка «сделай РУКАМИ» (это НЕ сбой, а нормальный ручной исход). Кладётся в
    complete_task(failed) → рендерится БЕЗ approve-кнопки → ре-approve/ре-конверт невозможен, петля
    рвётся. Тело: явно «требуется ручное действие», что именно сделать (из карточки) и что проверить."""
    card = _OP_PREFIX_RE.sub("", what or "").strip() or "(карточка пустая — см. вывод задачи)"
    lines = [
        "✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ (это не сбой, а нормальный ручной исход)",
        "Headless-контур доказано не может выполнить это красное действие (рабочие таблицы/деньги/"
        "clasp/sqlite3/удаление). Кнопки «да» здесь НЕТ намеренно — повторный approve лишь плодит "
        "петлю конвертов. Выполни РУКАМИ в Termux:",
        card,
        "После — проверь результат в целевой таблице/логах; при необходимости повтори исходную "
        "задачу в 328 обычным префиксом.",
    ]
    if orig_text:
        lines.append(f"Исходная задача (контекст): {str(orig_text).strip()[:300]}")
    return "\n".join(lines)[:RESULT_MAX]


def parse_op(what):
    """Извлечь op-код из сохранённого what (дескриптор needs_approval). 'other' если не распознан/не из перечня."""
    m = _OP_RE.search(what or "")
    if not m:
        return "other"
    op = m.group(1).lower()
    return op if op in AUTO_OPS else "other"


def _detect_needs_approval(text):
    """Вернуть дескриптор красного действия (строка с op=…), если claude самодекларировал маркер или
    явно описал блок гейта. Иначе None. Эскалация предпочтительнее тихого failed (так требует задача).
    Дескриптор сохраняется в очередь как what — по нему демон при approved исполняет хардкод-команду op."""
    t = text or ""
    for line in t.splitlines():
        i = line.find(NA_MARKER)
        if i >= 0:
            what = line[i + len(NA_MARKER):].strip()
            return what or "op=other | (claude не уточнил красное действие — см. вывод задачи)"
    low = t.lower()
    if any(p in low for p in _NA_FALLBACK):
        return "op=other | (гейт заблокировал красное; claude не дал маркер — вывод:)\n" + t[:1400]
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


def run_task(task_id, task_text, task_timeout=TASK_TIMEOUT, preamble=None):
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
    # Гейт-алерты только на финальном прогоне (хвост §7, 12.07.2026): внутри headless-задачи
    # промежуточные красные прогоны gate.py — штатный red-fix-green цикл, НЕ шум владельцу.
    # Флаг велит gate.py молчать в Telegram на НЕ-финальных прогонах; финальный pre-push зовёт
    # gate.py --final и алертит как раньше. Без этого env (Termux/cron/девбот) — всё как было.
    child_env["GATE_ALERT_FINAL_ONLY"] = "1"
    # Ускорение цепей ч.2 (13.07.2026): промежуточный шаг декомпозиции (i < N) →
    # gate.py запускает только тесты затронутых модулей (селективный гейт).
    # Последний шаг (i == N), одиночки, планировщик — полный сьют (preamble is None = executor).
    # --final (pre-push hook) всегда бьёт флаг — деплой-прогон всегда полный.
    if preamble is None:
        _sm = _STEP_RE.match(str(task_text or ""))
        if _sm and int(_sm.group(1)) < int(_sm.group(2)):
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
           "--output-format", "json",
           "--settings", HEADLESS_SETTINGS,  # строгий headless-слой (роль-развод: clasp → ask)
           prompt]                          # список аргументов, БЕЗ shell → нет инъекции через task_text
    # старт claude задачи по CLOCK_MONOTONIC — опора 5-го признака (свой/чужой плановый рестарт)
    t0_mono = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=REPO,
            capture_output=True, text=True,
            timeout=task_timeout,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        log.warning("id=%s ТАЙМАУТ %ss — claude -p убит, честный failed", task_id, task_timeout)
        return "failed", (f"{TIMEOUT_MARK} таймаут задачи {task_timeout}s — claude -p убит, задача "
                          f"не завершилась (лимит TASK_TIMEOUT из .env); думатель таймауты не чинит — "
                          f"упрости/раздели задачу и поставь заново")
    except Exception as e:
        log.error("id=%s ошибка запуска claude -p: %s", task_id, e)
        return "failed", f"ошибка запуска claude -p: {e}"
    finally:
        _hb_stop.set()
        _hb.join(timeout=5)

    raw = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    # --output-format json: {result:<текст>, modelUsage:{<модель>:{…}}, is_error, api_error_status}.
    # Достаём текст ответа (result) и КАКАЯ модель реально отработала (ключи modelUsage). Парс-фейл
    # (пустой/не-json вывод, тест-моки с plain text) → деградация на сырой stdout, как в текст-режиме.
    out, models_ran = raw, []
    try:
        j = json.loads(raw)
        out = (j.get("result") or "").strip()
        models_ran = list((j.get("modelUsage") or {}).keys())
    except Exception:
        pass
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
    if not (preamble is not None and preamble.startswith(PLANNER_PREAMBLE)):
        what = _detect_needs_approval(out)
        if what is not None:
            log.info("id=%s NEEDS_APPROVAL: %.140s", task_id, what)
            return "needs_approval", what[:RESULT_MAX]

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
        # §12 корень 3: чистая карточка провала, НЕ сырой дамп stdout+stderr (шум).
        return "failed", _fail_card(out, err, proc.returncode)
    log.info("id=%s claude -p exit=0 (вывод %d симв)", task_id, len(out))
    return "done", (out[:RESULT_MAX] if out else "(claude -p вернул пустой вывод)")


# === ИСПОЛНИТЕЛИ красных op (хардкод-команды; claude НЕ участвует, op-код детерминирует команду) ===
def _exec_git_push(task_id):
    """op=git_push: git push текущей ветки. БЕЗ --no-verify → pre-push hook 4.3 (gate.py) остаётся."""
    try:
        p = subprocess.run(["git", "push"], cwd=REPO, capture_output=True, text=True, timeout=OP_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "failed", f"git push: таймаут {OP_TIMEOUT}s"
    out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
    if p.returncode != 0:
        return "failed", f"git push exit={p.returncode}: {out}"[:RESULT_MAX]
    return "done", f"git push выполнен:\n{out}"[:RESULT_MAX]


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
    cmd = [CLAUDE_BIN, "-p",
           "--model", ORCH_MODEL,
           "--fallback-model", ORCH_MODEL_FALLBACK,
           "--output-format", "json",
           "--max-turns", "1",
           "--settings", HEADLESS_SETTINGS,    # тот же строгий headless-слой (единообразие забора)
           prompt]                             # prompt последним (тест-моки читают args[-1])
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
        bc.complete_task(tid, "failed",
                         (f"🛑 самопочинка не помогла (попытка 1 исчерпана): перерождение задачи "
                          f"{oid} упало повторно — нужен человек.\n{str(fail_text or '')}")[:RESULT_MAX])
        log.info("task-selfheal: id=%s (перерождение задачи %s) упал ПОВТОРНО → терминальный failed",
                 tid, oid)
        return True
    verdict = _task_selfheal_consult(text, fail_text)
    if verdict is None:
        return False                          # fail-safe: сбой думателя = прежний голый failed
    reason = verdict["reason"] or "(без причины)"
    fixed = verdict["fixed_task"]
    if verdict["verdict"] != "retry" or not fixed:
        bc.complete_task(tid, "failed",
                         (f"задача упала → думатель: halt, причина: {reason}\n"
                          f"Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX])
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
        bc.complete_task(tid, "failed",
                         (f"🛑 самопочинка не помогла (попытка 1 исчерпана): шаг {step_i}/{step_n} "
                          f"родителя {pid} упал повторно — цепочка остановлена, нужен человек.\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX])
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
        bc.complete_task(tid, "failed",
                         (f"шаг {step_i}/{step_n} упал → думатель: halt, причина: {reason}\n"
                          f"Цепочка остановлена (диагноз думателя выше).\n"
                          f"{str(fail_text or '')}")[:RESULT_MAX])
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
CURATOR_PREAMBLE = (
    "Ты — куратор целей оркестратора TurboBaby (мета-дирижёр). Headless-задача завершилась — "
    "сверь ИСХОДНУЮ ЦЕЛЬ с итогом исполнителя и реши, закрыта ли цель. Ты НИЧЕГО не исполняешь, "
    "инструментов у тебя нет, файлы не читаешь — решай строго по данным ниже.\n"
    "Ответь СТРОГО ОДНИМ JSON-объектом, без текста до/после, без markdown-обёртки:\n"
    '{"verdict":"closed"|"followup"|"human","tasks":["<зелёное ТЗ ≤400>"],'
    '"human":"<что нужно от владельца>","reason":"<1 строка>"}\n'
    "closed — цель достигнута, хвостов нет (или они чисто косметические; tasks/human пустые). "
    "followup — остались ЗЕЛЁНЫЕ хвосты (код/тесты/доки/диагностика БЕЗ красной зоны: без записи "
    "в рабочие таблицы, денег, clasp, sqlite3, удалений); tasks тогда — 1–3 САМОДОСТАТОЧНЫХ "
    "дев-ТЗ ≤400 символов каждое (исполнитель увидит ТОЛЬКО текст ТЗ, впиши нужный контекст). "
    "human — дожим требует владельца (красная зона, бизнес-решение, доступы, ручной тест); human "
    "тогда — 1 строка, что именно нужно. ЖЕЛЕЗНО: красные и смок-шаги (запись в рабочие таблицы "
    "Лист1/CRM/Зарплаты, деньги, clasp, sqlite3, удаления, деплой, смок-прогон на живых данных) — "
    "ТОЛЬКО в human, НИКОГДА в tasks. При сомнении между followup и human выбирай human — "
    "куратор не плодит самодеятельность.\n\n"
)


def _curator_on():
    """Флаг CURATOR=1 в .env (демон load_dotenv'ит на старте; парсер как STEP_SELFHEAL).
    0/нет/мусор → куратор выключен, поведение прежнее."""
    return (os.environ.get("CURATOR") or "").strip() == "1"


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
    prompt = (CURATOR_PREAMBLE +
              f"ИСХОДНАЯ ЦЕЛЬ (дословно):\n{str(goal or '').strip()[:1500]}\n\n"
              f"ИТОГ/СВОДКА ИСПОЛНИТЕЛЯ:\n{summary}\n\n"
              f"СЕКЦИИ ХВОСТОВ ИЗ ИТОГА:\n{_curator_tails(res)}\n")
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
_CURATOR_HUMAN_RE = re.compile(r"^\[куратор владельцу цель (\d+)\]")
_CURATOR_HUMAN_ITEM_RE = re.compile(r"^(\d+)\. (.+?)(?: \(×(\d+)\))?$")
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


def _curator_used(root):
    """Срез бюджетов из маркеров очереди ОДНИМ CSV-опросом (restart-proof):
    (продолжений по корню root, куратор-задач за сегодня UTC по всем корням, max шаг корня).
    None при сбое опроса — вызывающий код задачи НЕ ставит (fail-safe: без доказанного бюджета
    не плодим, карточка объяснит владельцу). created нечитаем → считаем сегодняшней (в сторону
    лимита, не в сторону спама)."""
    try:
        r = bc.get_pending("new,in_progress,done,failed,needs_approval,approved")
        if not r.get("ok"):
            return None
    except Exception:
        return None
    per_root, today, max_step = 0, 0, 0
    now = datetime.datetime.now(datetime.timezone.utc)
    for it in r.get("items", []):
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
    used = _curator_used(root)
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
    (заголовок, подсказка, пустые) молча пропускаются — рендер их пересоберёт."""
    items = []
    for ln in str(body or "").splitlines():
        m = _CURATOR_HUMAN_ITEM_RE.match(ln.strip())
        if m:
            items.append((m.group(2).strip(), int(m.group(3) or 1)))
    return items


def _curator_human_render(root, items):
    """Тело сводной карточки «нужно от владельца» по цели root. Пункт с счётчиком >1 несёт ×N."""
    lines = [f"🧑 нужно от владельца (цель {root}) — куратор задач по этим пунктам НЕ ставит:"]
    for i, (t, n) in enumerate(items, 1):
        lines.append(f"{i}. {t}" + (f" (×{n})" if n > 1 else ""))
    lines.append("")
    lines.append("✅ — принял/сделал (карточка закроется), ❌ — отклонить. Новые пункты этой цели "
                 "куратор дописывает в ЭТУ карточку (актуальный список — /inbox).")
    return "\n".join(lines)[:RESULT_MAX]


def _curator_human_upsert(root, item):
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
            word = {"created": "создана сводная карточка владельцу",
                    "edited": "пункт добавлен в сводную карточку владельцу",
                    "dedup": "пункт уже был в сводной карточке владельцу (счётчик ×N)"}[hum[1]]
            lines.append(f"🧑 {word} (задача {hum[0]}, инбокс).")
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
        hum = None
        if v["verdict"] == "human":
            # ветка human (шаг 4/7): задач НЕ ставим — пункт в сводную карточку владельцу
            # по КОРНЮ цели (продолжения того же корня копятся в ту же карточку)
            hum = _curator_human_upsert(_curator_root_depth(kind, key, goal)[0],
                                        v.get("human") or v.get("reason"))
        cm = bc.complete_task(sid, "done", _curator_card_text(kind, key, v, spawn, hum))
        log.info("curator: %s %s → %s, карточка задачей %s (bridge_ok=%s, продолжений=%s, hum=%s)",
                 kind, key, v["verdict"], sid, cm.get("ok"),
                 len(spawn["placed"]) if spawn else 0, hum and hum[1])
    except Exception as e:
        log.warning("curator: сбой консультации по %s %s (%s) — fail-safe тишина", kind, key, e)


def _maybe_curator_single(frm, tid, text, result):
    """Куратор на финале done/failed ОДИНОЧКИ «тз:»/«задача:» vps-полосы (from=Filipp-328[-dev]
    строго — артефакты декомпозиции/операций/pc сюда не проходят) и followup-задачи куратора
    (from=Filipp-curator — её терминал даёт вторую глубину дожима; третью глушит бюджет глубины
    в _curator_spawn). Зовётся из process_new ПОСЛЕ complete_task — финал уже записан, куратор
    его не трогает."""
    if str(frm or "") not in ("Filipp-328", "Filipp-328" + DEV_FROM_SUFFIX, CURATOR_FROM):
        return                    # dec-семейство (куратор цепи зовётся на сводке), pc, op и прочее
    if _is_convert(text):
        return                    # конверт одобренной заявки — вне кураторского контура
    if str(result or "").lstrip().startswith(_CURATOR_SKIP_MARKS):
        return                    # ⏱-диагноз / плановый рестарт-🔁 / отклонено Филиппом
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
    «сделай в Termux», а конвертируем в ОБЫЧНУЮ headless-задачу (текст заявки = ТЗ,
    from=Filipp-328-dev → дев-таймаут 45 мин); devbot принесёт её результат в 328 отдельным
    рапортом. Красная классификация ВНУТРИ новой задачи как была (преамбула/hook): настоящее
    красное снова даст NEEDS_APPROVAL-кнопку — approve заявки обхода гейта НЕ создаёт.
    Исключение: шаг декомпозиции НЕ конвертируем — конверт жил бы ВНЕ цепочки (без паттерна
    [шаг i/N]), guard последовательности его не видит → следующий шаг стартовал бы до
    исполнения одобренного. Для шага — прежний честный failed (halt-on-fail цепочки)."""
    if _STEP_RE.match(str(task.get("task_text") or "")):
        log.info("APPROVED id=%s op=other у шага декомпозиции → failed (конверт сломал бы guard)", tid)
        bc.complete_task(tid, "failed",
                         f"не могу выполнить автоматически: {what[:400]} — сделай в Termux")
        _maybe_dec_after(task.get("task_text"), "failed")
        return
    orig = str(task.get("task_text") or "").strip()
    # СЛОЙ 2: заведомо headless-НЕВОЗМОЖНОЕ красное (clasp/живая таблица/деньги/sqlite3/удаление) —
    # НЕ конвертируем (конверт лишь родил бы то же NEEDS_APPROVAL) → сразу терминальная ручная карта =
    # ноль перерождений на известной петле. Слой 1 добьёт неизвестное красное при ре-эскалации конверта.
    if _is_headless_impossible(what, orig):
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
                         f"({r.get('error')}) — сделай в Termux: {what[:400]}")
        _maybe_dec_after(task.get("task_text"), "failed")
        return
    nid = r.get("id")
    bc.complete_task(tid, "done",
                     f"✅ Одобрено → конвертировано в headless-задачу id {nid} (from=Filipp-328-dev, "
                     f"таймаут 45 мин). Результат придёт отдельным рапортом по задаче {nid}.")
    log.info("APPROVED id=%s op=other → конверт в headless-задачу %s", tid, nid)


def process_approved():
    """Довести одобренные Филиппом красные шаги (status=approved). claude ПОВТОРНО НЕ зовётся —
    op∈AUTO_OPS исполняется хардкод-командой (билет 4.2 + чёрный ящик); op=other (заведено 03.07)
    конвертируется в обычную headless-задачу (см. _convert_other_approved) — демон красное сам
    НЕ исполняет, конверт лишь возвращает заявку в обычный контур с той же классификацией.
    Инвариант: хардкод — ТОЛЬКО если op∈AUTO_OPS И билет 4.2 consume ok И не истёк таймаут approved."""
    r = bc.get_pending("approved")
    if not r.get("ok"):
        return
    for task in sorted(r.get("items", []), key=lambda x: int(x.get("id") or 0)):
        tid = task.get("id")
        what = str(task.get("result") or "")        # сохранённый дескриптор (op=… | текст) — одобренный

        # Сводная карточка владельцу (куратор, шаг 4/7): ✅ = «принял/сделал» — просто закрываем
        # done, НИКАКОГО конверта/исполнения (пункты по определению red/владельческие; конверт
        # op=other погнал бы их в headless — петля NEEDS_APPROVAL). До проверки таймаута:
        # «approve истёк» для карточки-списка бессмыслен. Новые human-пункты той же цели после
        # закрытия пойдут НОВОЙ карточкой (_curator_human_upsert ищет только открытые).
        if _CURATOR_HUMAN_RE.match(str(task.get("task_text") or "")):
            bc.complete_task(tid, "done",
                             "🧑 сводная карточка владельцу закрыта (✅): пункты приняты/сделаны "
                             "владельцем. Новые human-пункты той же цели встанут новой карточкой.")
            log.info("curator-human: сводная карточка %s закрыта владельцем (✅)", tid)
            continue

        # таймаут approved: одобрено давно, не довели → авто-failed
        if _approved_expired(task.get("updated")):
            log.info("APPROVED id=%s ИСТЁК (>%ss) → failed", tid, APPROVED_TTL)
            bc.complete_task(tid, "failed", "approve истёк (>30 мин), повтори задачу")
            _maybe_dec_after(task.get("task_text"), "failed")
            continue

        op = parse_op(what)
        if op not in EXECUTORS:
            # вне авто-перечня / free-text / op=other → демон сам НЕ исполняет:
            # конверт в обычную headless-задачу (или failed для шага декомпозиции)
            _convert_other_approved(tid, task, what)
            continue

        # билет 4.2: одноразовый серверный жетон авторизации + аудит (issue → consume перед командой)
        tk = (bc.issue_write_ticket() or {}).get("ticket")
        if not tk or not bc.consume_write_ticket(tk).get("ok"):
            log.warning("APPROVED id=%s билет 4.2 не подтверждён → failed", tid)
            bc.complete_task(tid, "failed", "билет токен-замка 4.2 не подтверждён — операция не выполнена")
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
    # FIFO: get_pending отдаёт newest-first → берём наименьший id (старейшую задачу) первым.
    # Шаг декомпозиции, чей сиблинг ждёт (needs_approval/approved/in_progress), пропускаем —
    # НЕ блокируя чужие задачи дальше по очереди (guard последовательности цепочки).
    task = None
    for cand in sorted(items, key=lambda x: int(x.get("id") or 0)):
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
            cm = bc.complete_task(tid, "failed", _manual_card(result))
            log.info("CONVERT-LOOP-BREAK id=%s → failed (терминальная ручная карта), bridge_ok=%s",
                     tid, cm.get("ok"))
            _maybe_dec_after(text, "failed")
        else:
            # Красная зона: НЕ исполняем. Ставим needs_approval — дев-бот спросит «да» Филиппа.
            rr = bc.set_needs_approval(tid, result)
            log.info("NEEDS_APPROVAL id=%s bridge_ok=%s", tid, rr.get("ok"))
    else:
        # САМОПОЧИНКА (STEP_SELFHEAL=1): провал шага декомпозиции ИЛИ одиночной «тз:»/«задача:»
        # (расширение ст4) → думатель, 1 попытка. True = финализировано внутри (перерождение/
        # терминальный failed с диагнозом); False = прежний путь.
        if status == "failed" and _maybe_selfheal(tid, text, result, frm=str(task.get("from") or "")):
            return
        cm = bc.complete_task(tid, status, result)
        log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))
        _maybe_dec_after(text, status)          # шаг декомпозиции → halt-on-fail / сводка
        # Реестр фактов: done-финал followup-задачи куратора → зафиксировать вердикт (перезапишет pending)
        if status == "done" and _curator_on() and str(task.get("from") or "") == CURATOR_FROM:
            vf_key = _vf_normalize(text)
            if vf_key:
                _vf_write(vf_key, (result.splitlines()[0] if result else "")[:200], tid)
        _maybe_curator_single(task.get("from"), tid, text, result)   # куратор цели (CURATOR=1)


def cycle():
    """Один проход: подобрать сирот in_progress (урок 138) → довести одобренное красное
    (approved) → добрать хвосты декомпозиций, финализированные мимо демона (сводка) → надзор
    цепей ПК-театра (полоса pc, read-only + релиз/хуки своих цепей) → взять новое (new)."""
    process_orphans()
    process_approved()
    process_dec_tails()
    process_pc_chains()
    process_new()


def main():
    log.info("=== ДЕМОН СТАРТ (poll=%ss, task_timeout=%ss/dev=%ss, approved_ttl=%ss, auto_ops=%s, claude=%s, "
             "selfheal=%s, plan_adapt=%s, curator=%s, fact_ttl=%ss, model=%s, executor_model=%s) ===",
             POLL_SEC, TASK_TIMEOUT, TASK_TIMEOUT_DEV, APPROVED_TTL, ",".join(AUTO_OPS), CLAUDE_BIN,
             int(_selfheal_on()), int(_plan_adapt_on()), int(_curator_on()), FACT_TTL, ORCH_MODEL, EXECUTOR_MODEL)
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
