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
import sys
import time
import signal
import logging
import subprocess

REPO = "/root/turbobaby-manager-bot"

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, REPO)
from bridge_client import BridgeClient

POLL_SEC = 60            # пауза между опросами очереди
TASK_TIMEOUT = 600       # таймаут одной задачи (10 мин) — claude -p не должен висеть вечно
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
# Преамбула к задаче: red-zone → claude выводит маркер и останавливается, НЕ обходит гейт.
APPROVAL_PREAMBLE = (
    "Ты выполняешь задачу автономно в headless-режиме (без интерактивного подтверждения).\n"
    "ПРАВИЛО БЕЗОПАСНОСТИ: если для выполнения нужно КРАСНОЕ действие — запись в рабочие таблицы "
    "(CRM/Лист1/Байки/Зарплаты), деньги/транзакции, clasp deploy/redeploy/push, sqlite3 на memory.db, "
    "git push, systemctl restart/stop, set_fleet_oil/set_fleet_service, confirmed=true, delete_event, "
    "любое удаление — НЕ пытайся его выполнить и НЕ ищи обходных путей. Вместо этого выведи РОВНО одну "
    "строку вида:\n"
    "NEEDS_APPROVAL: <кратко: какое именно красное действие/команда нужны>\n"
    "и заверши работу. Зелёные read-only шаги (чтение, диагностика) выполняй как обычно.\n"
    "Если задача целиком read-only — просто выполни её и верни результат, без маркера.\n\n"
    "ЗАДАЧА:\n"
)
# Фоллбэк-фразы (если claude описал блокировку гейта без маркера) — тоже эскалируем (эскалация
# безопасна: лишь спрашивает Филиппа, красное НЕ исполняется).
_NA_FALLBACK = ("требует подтверждения", "нужно подтверждение", "нужно «да»", "нужно \"да\"",
                "requires approval", "needs approval", "permission to use", "не разрешено гейтом")


def _detect_needs_approval(text):
    """Вернуть текст красного действия (what), если claude самодекларировал маркер или явно описал
    блок гейта. Иначе None. Эскалация предпочтительнее тихого failed (так требует задача)."""
    t = text or ""
    for line in t.splitlines():
        i = line.find(NA_MARKER)
        if i >= 0:
            what = line[i + len(NA_MARKER):].strip()
            return what or "(claude не уточнил красное действие — см. полный вывод задачи)"
    low = t.lower()
    if any(p in low for p in _NA_FALLBACK):
        return "(гейт заблокировал красное действие; claude не дал маркер — вывод:)\n" + t[:1500]
    return None


def run_task(task_id, task_text):
    """Исполнить задачу через claude -p (headless). Возврат: (status, result_text).
    status ∈ done|failed|needs_approval (красная зона — самодекларация claude через маркер)."""
    log.info("ИСПОЛНЕНИЕ id=%s через claude -p (timeout=%ss)", task_id, TASK_TIMEOUT)
    child_env = dict(os.environ)
    child_env.setdefault("HOME", "/root")
    child_env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    prompt = APPROVAL_PREAMBLE + task_text
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt],      # список аргументов, БЕЗ shell → нет инъекции через task_text
            cwd=REPO,
            capture_output=True, text=True,
            timeout=TASK_TIMEOUT,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        log.warning("id=%s ТАЙМАУТ %ss — задача прервана", task_id, TASK_TIMEOUT)
        return "failed", f"таймаут {TASK_TIMEOUT}s — claude -p прерван, задача не завершилась"
    except Exception as e:
        log.error("id=%s ошибка запуска claude -p: %s", task_id, e)
        return "failed", f"ошибка запуска claude -p: {e}"

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


def cycle():
    """Один проход: опросить очередь, взять старейшую new-задачу, исполнить, записать результат."""
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

    status, result = run_task(tid, text)
    if status == "needs_approval":
        # Красная зона: НЕ исполняем. Ставим needs_approval — дев-бот спросит «да» Филиппа.
        rr = bc.set_needs_approval(tid, result)
        log.info("NEEDS_APPROVAL id=%s bridge_ok=%s", tid, rr.get("ok"))
    else:
        cm = bc.complete_task(tid, status, result)
        log.info("COMPLETE id=%s status=%s bridge_ok=%s", tid, status, cm.get("ok"))


def main():
    log.info("=== ДЕМОН СТАРТ (poll=%ss, task_timeout=%ss, claude=%s) ===",
             POLL_SEC, TASK_TIMEOUT, CLAUDE_BIN)
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
