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

# Преамбула v2 (ступень 2 O4, 03.07): красная карта СИНХРОННА .claude/settings.json от 02.07
# (git push теперь allow → CC делает сам; restart splinter на обкатке — кнопкой через op-маркер).
# Red-zone → claude выводит маркер с op-кодом и останавливается, НЕ обходит гейт.
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
    "- systemctl restart splinter САМ НЕ делай (режим обкатки ступени 2): если рестарт нужен — выведи "
    "строку «NEEDS_APPROVAL: op=restart_splinter | <зачем>» и заверши работу (исполнят кнопкой в 328).\n"
    "- НАСТОЯЩЕЕ КРАСНОЕ — запись в рабочие таблицы (CRM/Лист1/Байки/Зарплаты), деньги/транзакции, "
    "clasp deploy/redeploy/push, sqlite3 CLI на memory.db, set_fleet_oil/set_fleet_service, "
    "confirmed=true, delete_event, любое удаление — НЕ выполняй и НЕ ищи обходных путей: выведи РОВНО "
    "одну строку «NEEDS_APPROVAL: op=other | <карточка: что · куда · последствия · на что смотреть>» "
    "и заверши работу (исполнит человек).\n"
    "ФОРМАТ ОТВЕТА: первая строка — сводка результата (≤400 символов, уйдёт в Telegram-тему 328); "
    "подробности — в cc_log, НЕ в вывод. Задача целиком read-only → просто выполни и верни сводку.\n\n"
    "ЗАДАЧА:\n"
)
# Фоллбэк-фразы (если claude описал блокировку гейта без маркера) — тоже эскалируем (эскалация
# безопасна: лишь спрашивает Филиппа, красное НЕ исполняется; op=other → человек в Termux).
_NA_FALLBACK = ("требует подтверждения", "нужно подтверждение", "нужно «да»", "нужно \"да\"",
                "requires approval", "needs approval", "permission to use", "не разрешено гейтом")
_OP_RE = re.compile(r"op\s*=\s*([a-z_]+)", re.IGNORECASE)


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
    """Таймаут по метке from очереди: дев-ТЗ («тз:», from=*-dev) → 45 мин, остальное → 10 мин."""
    return TASK_TIMEOUT_DEV if str(task.get("from") or "").endswith(DEV_FROM_SUFFIX) else TASK_TIMEOUT


def run_task(task_id, task_text, task_timeout=TASK_TIMEOUT):
    """Исполнить задачу через claude -p (headless). Возврат: (status, result_text).
    status ∈ done|failed|needs_approval (красная зона — самодекларация claude через маркер)."""
    log.info("ИСПОЛНЕНИЕ id=%s через claude -p (timeout=%ss)", task_id, task_timeout)
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    # Фикс утечки баланса: демон load_dotenv'ит .env (ради BRIDGE) → ANTHROPIC_API_KEY коллатерально
    # попадает в os.environ. Снимаем его (и OPENAI) из child_env, чтобы claude -p шёл по ~/.claude (Max),
    # а НЕ по платному API. Splinter не затронут (он ключ берёт из своего процесса, не через claude -p).
    child_env.pop("ANTHROPIC_API_KEY", None)
    child_env.pop("OPENAI_API_KEY", None)
    prompt = APPROVAL_PREAMBLE + task_text
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


def process_approved():
    """Довести одобренные Филиппом красные шаги (status=approved). claude ПОВТОРНО НЕ зовётся —
    op-код берётся из сохранённого в needs_approval дескриптора (то, что одобрил Филипп).
    Инвариант: исполняю ТОЛЬКО если op∈AUTO_OPS И билет 4.2 consume ok И не истёк таймаут approved."""
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
            continue

        op = parse_op(what)
        if op not in EXECUTORS:
            # вне авто-перечня / free-text / op=other → не исполняем, человек в Termux
            log.info("APPROVED id=%s op вне перечня (%s) → failed (Termux)", tid, op)
            bc.complete_task(tid, "failed",
                             f"не могу выполнить автоматически: {what[:400]} — сделай в Termux")
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
    items = sorted(items, key=lambda x: int(x.get("id") or 0))
    task = items[0]
    tid = task.get("id")
    text = str(task.get("task_text") or "")
    log.info("NEW id=%s from=%s text=%.120s", tid, task.get("from"), text)

    cl = bc.claim_task(tid)
    if not cl.get("ok"):
        log.info("claim id=%s не удался (%s) — пропускаю в этом цикле", tid, cl.get("error"))
        return

    status, result = run_task(tid, text, task_timeout=_task_timeout(task))
    if status == "needs_approval":
        # Красная зона: НЕ исполняем. Ставим needs_approval — дев-бот спросит «да» Филиппа.
        rr = bc.set_needs_approval(tid, result)
        log.info("NEEDS_APPROVAL id=%s bridge_ok=%s", tid, rr.get("ok"))
    else:
        cm = bc.complete_task(tid, status, result)
        log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))


def cycle():
    """Один проход: сначала довести одобренное красное (approved), потом взять новое (new)."""
    process_approved()
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
