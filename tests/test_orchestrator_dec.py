"""Моки C-декомпозера (ступень 2 часть C, KB_review PLAN 21:40): «декомпозируй:» → планировщик
(read-only claude -p) → шаги «[шаг i/N родитель id]» отдельными задачами → исполнение по одному
(guard последовательности + halt-on-fail) → сводка synthetic-задачей. Сети/Telegram/claude нет —
всё мокнуто (FakeBridge = очередь в памяти, subprocess.run подменён)."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
os.environ["THEATER_ROUTER"] = "0"  # изоляция от роутера театра (кусок 3): легаси-поведение 328

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD
import devbot as DB


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь оркестратора в памяти — контракт как у Bridge (BotData.js): enqueue/claim/complete/
    needs_approval без валидации from, complete из любого статуса."""
    def __init__(s):
        s.rows, s.nid = {}, 100
    def enqueue_task(s, frm, txt):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new"):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}
    def claim_task(s, tid):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"; r["updated"] = now_iso()
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}
    def approve(s, tid):                       # тестовый шорткат «да N»
        r = s.rows.get(int(tid)); r["status"] = "approved"; r["updated"] = now_iso()
    def task_heartbeat(s, tid): return {"ok": True}
    def issue_write_ticket(s): return {"ok": True, "ticket": "t-test"}
    def consume_write_ticket(s, tk): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}
    def by_status(s, status):
        return [r for r in s.rows.values() if r["status"] == status]
    def summaries(s, pid):
        return [r for r in s.rows.values() if r["task_text"].startswith(f"[сводка родитель {pid}]")]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode


_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0  # отключить proc-gate в тестах (real /proc видит claude)
def fake_run(args, **kw):
    return FakeProc("ok")   # git / systemctl (claude идёт через _POPEN)
def fake_popen(args, **kw):
    prompt = args[-1] if args else ""
    if prompt.startswith(OD.PLANNER_PREAMBLE):
        return FakePopen(fake_run.plan_out)
    return FakePopen(fake_run.step_out)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen
fake_run.plan_out = "1. шаг один\n2. шаг два"
fake_run.step_out = "сводка: шаг сделан"


def fresh():
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    return fb


# (1) devbot: префикс «декомпозируй:» → метка dec
print("(1) devbot «декомпозируй:»:")
ENQ = []
class EB:
    def enqueue_task(s, frm, txt): ENQ.append((frm, txt)); return {"ok": True, "id": 5}
m1 = DB._try_enqueue("декомпозируй: перепиши модуль X", EB())
res.append(ok(ENQ[-1] == ("Filipp-328-dec", "перепиши модуль X") and "декомпозиц" in m1.lower(),
              "«декомпозируй:» → from=Filipp-328-dec + ответ про план шагов"))
m2 = DB._try_enqueue("разбей: большое ТЗ", EB())
res.append(ok(ENQ[-1] == ("Filipp-328-dec", "большое ТЗ"), "«разбей:» — синоним"))
res.append(ok(DB._try_enqueue("декомпозируй:", EB()).startswith("🤖 Пустое ТЗ"), "пустое → отклонено"))
res.append(ok("Filipp-328-dec" in DB.QUEUE_FROMS, "QUEUE_FROMS включает dec (отчёты шагов дойдут)"))
res.append(ok("декомпозируй" in DB._g_help(), "help описывает «декомпозируй:»"))

# (2) константы/таймаут/парсер
print("(2) константы и парсер плана:")
res.append(ok(OD._task_timeout({"from": "Filipp-328-dec"}) == 2700, "from=*-dec → 2700с (45 мин)"))
res.append(ok(OD.MAX_STEPS == 8, "потолок шагов = 8"))
res.append(ok(OD._parse_steps("1. a\n2) b\nмусор без номера\n3. c") == ["a", "b", "c"],
              "парсер: «N.»/«N)» берёт, мусор игнорирует"))
res.append(ok(OD._parse_steps("никаких шагов") == [], "нет списка → пусто"))
res.append(ok("НЕЛЬЗЯ править" in OD.PLANNER_PREAMBLE and "нумерованный список" in OD.PLANNER_PREAMBLE,
              "преамбула планировщика: read-only + строгий формат"))
res.append(ok(OD._STEP_RE.match("[шаг 2/5 родитель 44] текст").groups() == ("2", "5", "44"),
              "_STEP_RE парсит i/N/родителя"))

# (3) родитель → план → fan-out шагов
print("(3) родитель → план → шаги в очереди:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "перепиши модуль X")["id"]
OD.process_new()
parent = fb.rows[pid]
res.append(ok(parent["status"] == "done" and "🧩 Декомпозиция: 2 шагов" in parent["result"],
              "родитель done, план в результате (devbot принесёт в 328)"))
news = sorted(fb.by_status("new"), key=lambda r: r["id"])
res.append(ok(len(news) == 2 and news[0]["task_text"] == f"[шаг 1/2 родитель {pid}] шаг один"
              and news[1]["task_text"] == f"[шаг 2/2 родитель {pid}] шаг два"
              and all(r["from"] == "Filipp-328-dec" for r in news),
              "2 шага в очереди с паттерном [шаг i/N родитель id], from=dec"))

# (4) исполнение по одному + сводка после последнего
print("(4) шаги по одному → сводка:")
OD.process_new()   # шаг 1
step1 = news[0]["id"]
res.append(ok(fb.rows[step1]["status"] == "done" and not fb.summaries(pid),
              "шаг 1 done, сводки ещё нет (шаг 2 в очереди)"))
OD.process_new()   # шаг 2 → последний → сводка
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and sums[0]["status"] == "done"
              and "2/2 шагов done" in sums[0]["result"],
              "после последнего шага — одна done-сводка «2/2 шагов done»"))
OD._dec_post_summary(pid)
res.append(ok(len(fb.summaries(pid)) == 1, "повторный вызов сводки — дубля нет (идемпотентно)"))

# (5) красный шаг: needs_approval блокирует следующий шаг, approve доводит цепочку
print("(5) красный шаг → guard → approve → цепочка доехала:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "задача с красным шагом")["id"]
OD.process_new()                                   # план → 2 шага
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_out = "NEEDS_APPROVAL: op=git_push | нужен push"
OD.process_new()                                   # шаг 1 → needs_approval
res.append(ok(fb.rows[s1]["status"] == "needs_approval", "красный шаг 1 → needs_approval (кнопка)"))
fake_run.step_out = "сводка: шаг сделан"
OD.process_new()                                   # guard: шаг 2 НЕ берём, пока сиблинг ждёт
res.append(ok(fb.rows[s2]["status"] == "new", "guard: шаг 2 не тронут, пока шаг 1 ждёт «да»"))
fb.approve(s1)
OD.process_approved()                              # хардкод-op git_push (мок) → done
res.append(ok(fb.rows[s1]["status"] == "done", "approve → op исполнен → шаг 1 done"))
OD.process_new()                                   # шаг 2 → последний → сводка
res.append(ok(fb.rows[s2]["status"] == "done" and len(fb.summaries(pid)) == 1
              and "2/2" in fb.summaries(pid)[0]["result"],
              "цепочка доехала после approve, сводка 2/2"))

# (6) halt-on-fail: упавший шаг глушит остальные, сводка с ❌
print("(6) halt-on-fail:")
fb = fresh()
fake_run.plan_out = "1. первый\n2. второй\n3. третий"
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ из 3 шагов, шаг 1 упадёт")["id"]
OD.process_new()
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
_real_run_task = OD.run_task
OD.run_task = lambda tid, txt, task_timeout=600, preamble=None: ("failed", "всё сломалось")
OD.process_new()                                   # шаг 1 → failed → halt
OD.run_task = _real_run_task
res.append(ok(fb.rows[s1]["status"] == "failed", "шаг 1 failed"))
res.append(ok(fb.rows[s2]["status"] == "failed" and "пропущен" in fb.rows[s2]["result"]
              and fb.rows[s3]["status"] == "failed",
              "шаги 2-3 пропущены (цепочка остановлена)"))
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "0/3 шагов done" in sums[0]["result"]
              and "❌" in sums[0]["result"], "сводка: 0/3 done, ❌ по шагам"))

# (7) «нет N» мимо демона (devbot ставит failed) → хвостовой скан/пропуск даёт сводку
print("(7) reject мимо демона:")
fb = fresh()
fake_run.plan_out = "1. первый\n2. второй"
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ, шаг 1 отклонят")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fb.complete_task(s1, "failed", "отклонено Филиппом")   # как devbot._cb_reject / «нет N»
OD.process_new()                                   # кандидат шаг 2 → в цепочке failed → пропуск+сводка
res.append(ok(fb.rows[s2]["status"] == "failed" and "пропущен" in fb.rows[s2]["result"],
              "шаг 2 пропущен после отклонения шага 1"))
res.append(ok(len(fb.summaries(pid)) == 1, "сводка пришла (не потерялась при reject)"))
# отклонён ПОСЛЕДНИЙ живой шаг → некому дёрнуть хук → добирает process_dec_tails
fb2 = fresh()
fake_run.plan_out = "1. единственный"
pid2 = fb2.enqueue_task("Filipp-328-dec", "ТЗ из 1 шага")["id"]
OD.process_new()
(s1,) = [r["id"] for r in fb2.by_status("new")]
fb2.complete_task(s1, "failed", "отклонено Филиппом")
OD.process_dec_tails()
res.append(ok(len(fb2.summaries(pid2)) == 1, "tails: сводка после reject последнего шага"))

# (8) осиротевшая сводка (демон упал между enqueue и complete) → доводится
print("(8) осиротевшая сводка:")
fb = fresh()
fake_run.plan_out = "1. первый\n2. второй"
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new(); OD.process_new(); OD.process_new()   # план + 2 шага (+сводка)
orphan = fb.enqueue_task("Filipp-328-dec", f"[сводка родитель {pid}] сводный отчёт по шагам")["id"]
OD.process_new()
res.append(ok(fb.rows[orphan]["status"] == "done" and "Сводка декомпозиции" in fb.rows[orphan]["result"],
              "orphan-сводка доведена (регенерация, planner не зовётся)"))

# (9) планировщик сломался / слишком много шагов → родитель failed
print("(9) деградации планировщика:")
fb = fresh()
fake_run.plan_out = "не могу, нет списка"
pid = fb.enqueue_task("Filipp-328-dec", "мутное ТЗ")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "failed" and "не вернул нумерованный список" in fb.rows[pid]["result"],
              "нет списка → родитель failed с объяснением"))
fb = fresh()
fake_run.plan_out = "\n".join(f"{i}. шаг {i}" for i in range(1, 10))
pid = fb.enqueue_task("Filipp-328-dec", "гигантское ТЗ")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "failed" and "потолка 8" in fb.rows[pid]["result"]
              and not fb.by_status("new"), "9 шагов > потолка → failed, шаги НЕ ставились"))
fake_run.plan_out = "1. шаг один\n2. шаг два"

# (10) обычные задачи не задеты: «задача:»/«тз:» идут мимо веток dec
print("(10) обычные задачи мимо декомпозера:")
fake_run.step_out = "сводка: шаг сделан"
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "почини рендер")["id"]
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "done" and fb.rows[tid]["result"].startswith("сводка:"),
              "«тз:» (from=dev) исполнена как раньше (без планировщика)"))

OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
