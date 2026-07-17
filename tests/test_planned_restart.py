"""ФИКС КЛАССА «самомодификация демона → ложный failed» (урок задачи 105, 07.07.2026).
Самомод-задача ставит отложенный systemd-run restart последним действием; рестарт гасит её же
claude -p (SIGTERM/143) → старый код метил failed при полностью сделанной работе. Фикс: run_task
распознаёт ПЛАНОВЫЙ рестарт по 4 обязательным признакам (SIGTERM-код + _running=False +
самомод-признак в ТЗ + видимая systemd-run-единица) → done с пометкой «завершено плановым
рестартом». НАСТОЯЩИЕ падения (точечный kill / oom / ручной stop без systemd-run / сомнение)
остаются честным failed (fail-safe). Сети/Telegram/claude нет — всё мокнуто."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
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
        if r["status"] != "new": return {"ok": False, "error": "already_claimed"}
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
    def task_heartbeat(s, tid): return {"ok": True}


class FakePopen:
    """Мок _POPEN для claude -p: communicate() возвращает (out, ""), rc задаётся заранее."""
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


# transient-единицы systemd-run, как их отдаёт systemctl list-units --plain --no-legend
UNIT_RESTART = ("run-r4242.service loaded active running "
                "/usr/bin/systemctl restart orchestrator-daemon")
UNIT_OTHER = "run-r9999.service loaded active running /usr/bin/sleep 600"

SELFMOD_TEXT = ("тз: фикс класса — правка orchestrator_daemon.py, в конце отложенный "
                "systemd-run restart демона")
PLAIN_TEXT = "тз: поправь опечатку в prompts.py и прогони тесты"

_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0  # отключить proc-gate в тестах (нет живых claude)

def fake_popen(args, **kw):
    """Мок claude -p через _POPEN."""
    return FakePopen(fake_popen.claude_out, fake_popen.claude_rc)
fake_popen.claude_out = ""
fake_popen.claude_rc = 143

def fake_run(args, **kw):
    """Мок systemctl и прочих subprocess — НЕ claude (он через _POPEN)."""
    if args and args[0] == "systemctl":
        fake_run.probe_calls += 1
        if fake_run.probe_exc:
            raise fake_run.probe_exc
        return FakeProc(fake_run.probe_out)
    return FakeProc("ok")
OD.subprocess.run = fake_run
OD._POPEN = fake_popen

_prev_running = OD._running


def fresh(claude_out="", claude_rc=143, probe_out=UNIT_RESTART, running=False):
    fb = FakeBridge()
    OD.bc = fb
    OD._running = running
    fake_popen.claude_out, fake_popen.claude_rc = claude_out, claude_rc
    fake_run.probe_out, fake_run.probe_exc = probe_out, None
    fake_run.probe_calls = 0
    return fb


# (1) ПЛАНОВЫЙ РЕСТАРТ: все 4 признака → done с пометкой (ядро фикса)
print("(1) плановый рестарт → done с пометкой:")
fresh()
st, out = OD.run_task(1, SELFMOD_TEXT)
res.append(ok(st == "done" and "плановым рестартом" in out and "НЕ сбой" in out,
              "exit=143 + демон в остановке + самомод-ТЗ + systemd-run-единица → done"))
res.append(ok(fake_run.probe_calls == 1, "проба systemctl позвана"))
fresh(claude_rc=-15)
st, out = OD.run_task(1, SELFMOD_TEXT)
res.append(ok(st == "done" and "плановым рестартом" in out,
              "rc=-15 (SIGTERM от subprocess) — тоже плановый"))

# (2) ОБЫЧНЫЙ KILL: демон жив (_running=True) → честный failed
print("(2) точечный kill claude при живом демоне → failed:")
fresh(running=True)
st, out = OD.run_task(2, SELFMOD_TEXT)
res.append(ok(st == "failed" and "плановым рестартом" not in out and "упал" in out,
              "rc=143, но демон НЕ в остановке → failed (точечный kill)"))
res.append(ok(fake_run.probe_calls == 0, "до пробы systemctl не дошло (ранний отказ)"))

# (3) СОМНЕНИЕ → failed (fail-safe, каждый признак обязателен)
print("(3) fail-safe: сомнение → failed:")
fresh()
st, out = OD.run_task(3, PLAIN_TEXT)
res.append(ok(st == "failed", "нет самомод-признака в ТЗ → failed"))
fresh(probe_out=UNIT_OTHER)
st, out = OD.run_task(3, SELFMOD_TEXT)
res.append(ok(st == "failed", "transient-единиц с рестартом демона нет → failed (ручной stop)"))
fresh(probe_out="")
st, out = OD.run_task(3, SELFMOD_TEXT)
res.append(ok(st == "failed", "пустой вывод пробы → failed"))
fresh()
fake_run.probe_exc = OSError("systemctl недоступен")
st, out = OD.run_task(3, SELFMOD_TEXT)
res.append(ok(st == "failed", "проба systemctl упала → failed (fail-safe)"))

# (4) OOM/SIGKILL и обычные провалы — НЕ маскируются
print("(4) настоящие падения остаются failed:")
for rc, label in ((137, "exit=137 (SIGKILL/oom)"), (-9, "rc=-9 (SIGKILL)"), (1, "exit=1 (обычный провал)")):
    fresh(claude_rc=rc)
    st, out = OD.run_task(4, SELFMOD_TEXT)
    res.append(ok(st == "failed" and "плановым рестартом" not in out, label + " → failed"))

# (5) РЕГРЕСС: штатные пути run_task не тронуты
print("(5) регресс штатных путей:")
fresh(claude_out='{"result":"сводка: всё сделано","modelUsage":{"m":{}}}', claude_rc=0)
st, out = OD.run_task(5, SELFMOD_TEXT)
res.append(ok(st == "done" and out == "сводка: всё сделано", "exit=0 → обычный done без пометки"))
fresh(claude_out="NEEDS_APPROVAL: op=git_push | нужен push", claude_rc=0)
st, out = OD.run_task(5, SELFMOD_TEXT)
res.append(ok(st == "needs_approval", "красный маркер → needs_approval как раньше"))

# (6) КОНЦЕВОЙ: через process_new — карточка в очереди done с пометкой
print("(6) end-to-end через process_new:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", SELFMOD_TEXT)["id"]
OD.process_new()
r = fb.rows[tid]
res.append(ok(r["status"] == "done" and "плановым рестартом" in r["result"],
              "задача в очереди финализирована done с пометкой (devbot принесёт её в 328)"))

OD._running = _prev_running
OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
