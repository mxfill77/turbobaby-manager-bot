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
import signal
import logging
import datetime
import subprocess
import threading

REPO = "/root/turbobaby-manager-bot"
BRIDGE_GS = "/root/turbobaby-bridge-gs"

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, REPO)
from bridge_client import BridgeClient

POLL_SEC = 60            # пауза между опросами очереди
HEARTBEAT_SEC = 45       # как часто фон-поток бьёт updated, пока claude -p исполняется (детект зависания)
TASK_TIMEOUT = 600       # таймаут быстрой задачи «задача:» (10 мин) — claude -p не должен висеть вечно
TASK_TIMEOUT_DEV = 2700  # таймаут дев-ТЗ «тз:» (45 мин, ступень 2 O4) — правка+тесты+гейт+отчёт
DEV_FROM_SUFFIX = "-dev" # метка dev-режима в поле from очереди (devbot кладёт Filipp-328-dev)
DEC_FROM_SUFFIX = "-dec" # метка декомпозиции (ступень 2 часть C; devbot кладёт Filipp-328-dec):
                         # родитель «декомпозируй:» + его шаги + synthetic-сводка — всё под этой меткой
MAX_STEPS = 8            # потолок шагов декомпозиции (планировщику велено 2–7; больше → failed родителя)
OP_TIMEOUT = 180         # таймаут хардкод-операции красной зоны (git push / restart)
APPROVED_TTL = 1800      # approved-задача живёт 30 мин; не довёл → авто-failed «approve истёк»
CLAUDE_BIN = "/usr/bin/claude"
RESULT_MAX = 4500        # Bridge режет result на 5000 — оставляем запас
LOG_PATH = os.path.join(REPO, "orchestrator_daemon.log")

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

# === АВТО-ПЕРЕЧЕНЬ красных op (п.4 узкий, штаб 19.06) — РОВНО два, оба обратимы ===
# clasp_redeploy / CRM / Лист1 / деньги / set_fleet_* / delete_event — НЕ здесь (позже, особое «да»).
AUTO_OPS = ("git_push", "restart_splinter")

# Преамбула v3 (Q2 разблокирован 03.07: критерий обкатки ступени 2 выполнен — 3 «тз:» подряд done
# без Termux, вкл. прод-фикс 3978a91). restart splinter теперь CC делает САМ оранжевым циклом
# (гейт→restart→проверка чистого старта→отчёт); кнопка op=restart_splinter остаётся фоллбэком.
# Red-zone (Лист1/CRM/деньги/clasp/sqlite3/delete) — БЕЗ изменений: маркер op=other, НЕ обходить гейт.
APPROVAL_PREAMBLE = (
    "Ты выполняешь задачу автономно в headless-режиме (без интерактивного подтверждения) в репо "
    "/root/turbobaby-manager-bot — CLAUDE.md и вся его дисциплина действуют.\n"
    "ДИСЦИПЛИНА (обязательно): перед правкой кода — бэкап (коммит/копия .bak); после правки — "
    "py_compile + тесты; перед git push — гейт (venv/bin/python3 gate.py; pre-push зовёт его сам); "
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
    "строго в порядке исполнения; правки кода раньше, деплой/рестарт/проверка — последними.\n\n"
    "КРУПНОЕ ТЗ:\n"
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
    """Таймаут по метке from очереди: дев-ТЗ («тз:», from=*-dev) и декомпозиция (from=*-dec,
    планирование-разведка и шаги — те же дев-ТЗ) → 45 мин, остальное → 10 мин."""
    frm = str(task.get("from") or "")
    return TASK_TIMEOUT_DEV if frm.endswith((DEV_FROM_SUFFIX, DEC_FROM_SUFFIX)) else TASK_TIMEOUT


def run_task(task_id, task_text, task_timeout=TASK_TIMEOUT, preamble=None):
    """Исполнить задачу через claude -p (headless). Возврат: (status, result_text).
    status ∈ done|failed|needs_approval (красная зона — самодекларация claude через маркер).
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
    prompt = (preamble if preamble is not None else APPROVAL_PREAMBLE) + task_text
    # Heartbeat: фон-поток бьёт updated, пока claude -p блокирующе исполняется. Останавливаем в finally.
    _hb_stop = threading.Event()
    _hb = threading.Thread(target=_heartbeat_loop, args=(task_id, _hb_stop), daemon=True)
    _hb.start()
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],      # список аргументов, БЕЗ shell → нет инъекции через task_text
            cwd=REPO,
            capture_output=True, text=True,
            timeout=task_timeout,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        log.warning("id=%s ТАЙМАУТ %ss — задача прервана", task_id, task_timeout)
        return "failed", f"таймаут {task_timeout}s — claude -p прерван, задача не завершилась"
    except Exception as e:
        log.error("id=%s ошибка запуска claude -p: %s", task_id, e)
        return "failed", f"ошибка запуска claude -p: {e}"
    finally:
        _hb_stop.set()
        _hb.join(timeout=5)

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    # Красная зона: claude самодекларировал, что нужно «да» Филиппа → needs_approval (НЕ failed).
    what = _detect_needs_approval(out)
    if what is not None:
        log.info("id=%s NEEDS_APPROVAL: %.140s", task_id, what)
        return "needs_approval", what[:RESULT_MAX]

    if proc.returncode != 0:
        log.warning("id=%s claude -p exit=%s", task_id, proc.returncode)
        msg = (out + ("\n" + err if err else "")).strip() or f"exit={proc.returncode}"
        return "failed", f"claude exit={proc.returncode}: {msg}"[:RESULT_MAX]
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
    rows = sorted(_dec_siblings(pid, ("done", "failed")), key=lambda x: x[0])
    if not rows:
        return f"🧩 Сводка декомпозиции (родитель {pid}): шагов не найдено (очередь пуста?)"
    n_done = sum(1 for _i, _n, it in rows if str(it.get("status")) == "done")
    total = rows[0][1]
    head = f"🧩 Сводка декомпозиции (родитель {pid}): {n_done}/{total} шагов done"
    if n_done < len(rows):
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
    """Хук после финала шага: failed → пропустить оставшиеся new-сиблинги (цепочка зависимая,
    дальше идти опасно); все финальны → сводка по родителю."""
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


def _dec_plan_and_fanout(tid, task_text):
    """Родитель декомпозиции: планировщик claude -p (read-only) → парс шагов → шаги в очередь
    «[шаг i/N родитель tid] …» → родитель done с планом (devbot принесёт план в 328)."""
    status, out = run_task(tid, task_text, task_timeout=TASK_TIMEOUT_DEV, preamble=PLANNER_PREAMBLE)
    if status != "done":
        # планировщик read-only: needs_approval от него = аномалия → честный failed, не кнопка
        bc.complete_task(tid, "failed", f"декомпозиция не удалась (планировщик {status}): {out}"[:RESULT_MAX])
        return
    steps = _parse_steps(out)
    if not steps:
        bc.complete_task(tid, "failed",
                         f"декомпозиция не удалась: планировщик не вернул нумерованный список шагов:\n{out}"[:RESULT_MAX])
        return
    if len(steps) > MAX_STEPS:
        bc.complete_task(tid, "failed",
                         f"декомпозиция не удалась: {len(steps)} шагов > потолка {MAX_STEPS} — "
                         f"упрости ТЗ или разбей вручную:\n{out}"[:RESULT_MAX])
        return
    n = len(steps)
    ids, errs = [], []
    for i, step in enumerate(steps, 1):
        r = bc.enqueue_task(f"Filipp-328{DEC_FROM_SUFFIX}", f"[шаг {i}/{n} родитель {tid}] {step}")
        if r.get("ok"):
            ids.append(str(r.get("id")))
        else:
            errs.append(f"шаг {i} не встал: {r.get('error')}")
            log.warning("dec: родитель %s шаг %s не встал в очередь (%s)", tid, i, r.get("error"))
    plan = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    res = (f"🧩 Декомпозиция: {n} шагов, в очереди id {', '.join(ids) or '—'}.\n{plan}\n"
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
    card = _OP_PREFIX_RE.sub("", what or "").strip() or "(карточка пустая — см. исходную задачу)"
    orig = str(task.get("task_text") or "").strip()
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


def process_new():
    """Взять старейшую new-задачу, исполнить через claude -p, записать результат/needs_approval."""
    r = bc.get_pending("new")
    if not r.get("ok"):
        log.warning("get_pending ошибка: %s", r.get("error"))
        return
    items = r.get("items", [])
    if not items:
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
        task = cand
        break
    if task is None:
        return
    tid = task.get("id")
    text = str(task.get("task_text") or "")
    log.info("NEW id=%s from=%s text=%.120s", tid, task.get("from"), text)

    cl = bc.claim_task(tid)
    if not cl.get("ok"):
        log.info("claim id=%s не удался (%s) — пропускаю в этом цикле", tid, cl.get("error"))
        return

    if _is_dec(task):
        sm = _SUM_RE.match(text)
        if sm:
            # осиротевшая synthetic-сводка (демон упал между enqueue и complete) → доводим
            bc.complete_task(tid, "done", _dec_summary_text(int(sm.group(1))))
            log.info("dec: осиротевшая сводка id=%s доведена", tid)
            return
        if not _STEP_RE.match(text):
            _dec_plan_and_fanout(tid, text)     # родитель «декомпозируй:» → план → fan-out шагов
            return

    status, result = run_task(tid, text, task_timeout=_task_timeout(task))
    if status == "needs_approval":
        # Красная зона: НЕ исполняем. Ставим needs_approval — дев-бот спросит «да» Филиппа.
        rr = bc.set_needs_approval(tid, result)
        log.info("NEEDS_APPROVAL id=%s bridge_ok=%s", tid, rr.get("ok"))
    else:
        cm = bc.complete_task(tid, status, result)
        log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))
        _maybe_dec_after(text, status)          # шаг декомпозиции → halt-on-fail / сводка


def cycle():
    """Один проход: довести одобренное красное (approved) → добрать хвосты декомпозиций,
    финализированные мимо демона (сводка) → взять новое (new)."""
    process_approved()
    process_dec_tails()
    process_new()


def main():
    log.info("=== ДЕМОН СТАРТ (poll=%ss, task_timeout=%ss/dev=%ss, approved_ttl=%ss, auto_ops=%s, claude=%s) ===",
             POLL_SEC, TASK_TIMEOUT, TASK_TIMEOUT_DEV, APPROVED_TTL, ",".join(AUTO_OPS), CLAUDE_BIN)
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
