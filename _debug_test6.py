"""Debug test (6) from test_planned_restart.py."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"
os.environ["ORCH_TEST_MODE"] = "1"

import orchestrator_daemon as OD

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 100
    def enqueue_task(s, frm, txt, **kw):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new", **kw):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}
    def claim_task(s, tid, **kw):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed"}
        r["status"] = "in_progress"; r["updated"] = now_iso()
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        print(f"  [FakeBridge.complete_task] id={tid} status={status} result={result[:80]!r}")
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}

class FakePopen:
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

UNIT_RESTART = ("run-r4242.service loaded active running "
                "/usr/bin/systemctl restart orchestrator-daemon")
SELFMOD_TEXT = ("тз: фикс класса — правка orchestrator_daemon.py, в конце отложенный "
                "systemd-run restart демона")

_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0

def fake_popen(args, **kw):
    print(f"  [fake_popen] called rc={fake_popen.claude_rc}")
    return FakePopen(fake_popen.claude_out, fake_popen.claude_rc)
fake_popen.claude_out = ""
fake_popen.claude_rc = 143

def fake_run(args, **kw):
    if args and args[0] == "systemctl":
        fake_run.probe_calls += 1
        print(f"  [fake_run] systemctl call #{fake_run.probe_calls}")
        if fake_run.probe_exc:
            raise fake_run.probe_exc
        return FakeProc(fake_run.probe_out)
    return FakeProc("ok")
fake_run.probe_calls = 0
fake_run.probe_out = UNIT_RESTART
fake_run.probe_exc = None

OD.subprocess.run = fake_run
OD._POPEN = fake_popen
_prev_running = OD._running

# Setup
fb = FakeBridge()
OD.bc = fb
OD._running = False
fake_popen.claude_out, fake_popen.claude_rc = "", 143
fake_run.probe_out, fake_run.probe_exc = UNIT_RESTART, None
fake_run.probe_calls = 0

tid = fb.enqueue_task("Filipp-328-dev", SELFMOD_TEXT)["id"]
print(f"Enqueued task id={tid}, status={fb.rows[tid]['status']}")

print("Calling process_new()...")
OD.process_new()

r = fb.rows[tid]
print(f"After process_new: id={tid} status={r['status']!r} result={r['result'][:80]!r}")
check = r["status"] == "done" and "плановым рестартом" in r["result"]
print(f"Test (6): {'PASS' if check else 'FAIL'}")

# Restore
OD._running = _prev_running
OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS
