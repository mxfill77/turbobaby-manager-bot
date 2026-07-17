"""CURATOR_SCOPE — сужение триггера куратора (15.07.2026).
CURATOR_SCOPE=1 в .env: done-одиночки БЕЗ коммита в result → мимо куратора (тишина);
failed-одиночки и сводки цепей — как прежде. CURATOR_SCOPE=0/нет → текущее поведение.
Проверки:
  (0) парсер флага CURATOR_SCOPE;
  (1) _result_has_commit — детектор коммита/push в result;
  (2) _maybe_curator_single: done без коммита + CURATOR_SCOPE=1 → ноль consult;
  (3) _maybe_curator_single: done С коммитом + CURATOR_SCOPE=1 → consult;
  (4) _maybe_curator_single: failed + CURATOR_SCOPE=1 → consult (не заглушается);
  (5) CURATOR_SCOPE=0: done без коммита → consult (прежнее поведение);
  (6) цепь (_maybe_curator_chain): CURATOR_SCOPE не влияет (unchanged);
  (7) интеграция process_new: done read-only → ноль consult, done с коммитом → consult."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# Принудительная изоляция: боевой .env наследуется headless-задачей
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "1"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


# --- spy на _curator_consult ---
_real_consult = OD._curator_consult
consults = []
def spy_consult(goal, result):
    consults.append((goal, result))
    return {"verdict": "closed", "tasks": [], "human": "", "reason": "spy-closed"}
OD._curator_consult = spy_consult


class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 300
    def add(s, status, text, frm="Filipp-328", result=""):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": "2026-07-15T00:00:00+00:00"}
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, text, lane=None):
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}


_real_bc = OD.bc
_real_run_task = OD.run_task
_real_rp = OD._restart_pending
OD._restart_pending = lambda: False
OD.MAX_CLAUDE_PROCS = 0; OD.MEM_MIN_MB = 0; OD.CLAUDE_RSS_TOTAL_MB = 0

# Заменяем bc сразу — orchestrator_daemon load_dotenv'ит реальный .env при import,
# поэтому OD.bc изначально указывает на боевой Bridge. Без замены _curator_card_exists
# будет вызывать реальный Bridge в разделах (2)-(5).
_stub_bc = FakeBridge()
OD.bc = _stub_bc


def setup(run_ret, frm="Filipp-328-dev", text="задача: проверь DNS записи"):
    fb = FakeBridge()
    OD.bc = fb
    OD.run_task = lambda tid, t, task_timeout=600, preamble=None: run_ret
    OD._curated.clear()
    consults.clear()
    return fb, fb.add("new", text, frm=frm)


# (0) парсер флага CURATOR_SCOPE
print("(0) парсер флага CURATOR_SCOPE:")
os.environ.pop("CURATOR_SCOPE", None)
res.append(ok(OD._curator_scope_on() is False, "нет в env → выкл (дефолт = текущее поведение)"))
os.environ["CURATOR_SCOPE"] = "0"
res.append(ok(OD._curator_scope_on() is False, "CURATOR_SCOPE=0 → выкл"))
os.environ["CURATOR_SCOPE"] = " 1 "
res.append(ok(OD._curator_scope_on() is True, "CURATOR_SCOPE=' 1 ' → вкл (strip как STEP_SELFHEAL)"))
os.environ["CURATOR_SCOPE"] = "true"
res.append(ok(OD._curator_scope_on() is False, "CURATOR_SCOPE=true (мусор) → выкл, не падает"))
os.environ["CURATOR_SCOPE"] = "1"
res.append(ok(OD._curator_scope_on() is True, "CURATOR_SCOPE=1 → вкл"))

# (1) _result_has_commit
print("(1) _result_has_commit — детектор коммита/push:")
res.append(ok(OD._result_has_commit("DNS проверен, все записи в норме, хвостов нет") is False,
              "read-only result (нет commit/push) → False"))
res.append(ok(OD._result_has_commit("фикс gate.py — коммит abc1234f, рестарт демона") is True,
              "«коммит» в result → True"))
res.append(ok(OD._result_has_commit("DONE: commit 3cedb92 pushed") is True,
              "«commit» (en) в result → True"))
res.append(ok(OD._result_has_commit("git push origin main успешно") is True,
              "«git push» в result → True"))
res.append(ok(OD._result_has_commit("GIT PUSH завершён") is True,
              "«GIT PUSH» (регистр) → True"))
res.append(ok(OD._result_has_commit("") is False, "пустая строка → False"))
res.append(ok(OD._result_has_commit(None) is False, "None → False, не падает"))
# «committee» не должно срабатывать (word boundary)
res.append(ok(OD._result_has_commit("committee decision approved") is False,
              "committee (не commit\\b) → False"))

# (2) done без коммита + CURATOR_SCOPE=1 → ноль consult
print("(2) done без коммита + CURATOR_SCOPE=1 → ноль consult:")
os.environ["CURATOR_SCOPE"] = "1"
OD._maybe_curator_single("Filipp-328", 101, "задача: проверь DNS", "DNS ОК, хвостов нет", status="done")
res.append(ok(consults == [], "done read-only → ноль consult"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328-dev", 102, "тз: проверь логи", "логи чистые, нет ошибок", status="done")
res.append(ok(consults == [], "done read-only (from=-dev) → ноль consult"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-curator", 103, "задача: дожать хвост", "всё проверено, чисто", status="done")
res.append(ok(consults == [], "done read-only (from=Filipp-curator) → ноль consult"))

# (3) done С коммитом + CURATOR_SCOPE=1 → consult
print("(3) done С коммитом + CURATOR_SCOPE=1 → consult:")
consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 104, "тз: fix gate", "фикс готов — коммит 61b7c44, push", status="done")
res.append(ok(len(consults) == 1 and consults[0][0] == "тз: fix gate",
              "done + коммит в result → consult (код изменялся)"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 105, "тз: deploy", "DONE: commit d73a25d, git push done", status="done")
res.append(ok(len(consults) == 1, "done + commit (en) → consult"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 106, "тз: push", "git push origin main завершён", status="done")
res.append(ok(len(consults) == 1, "done + git push → consult"))

# (4) failed + CURATOR_SCOPE=1 → consult (не заглушается)
print("(4) failed + CURATOR_SCOPE=1 → consult:")
consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 107, "задача: проверь DNS", "DNS ОК", status="failed")
res.append(ok(len(consults) == 1, "failed без коммита → consult (failed не заглушается CURATOR_SCOPE)"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 108, "тз: fix", "гейт красный", status="failed")
res.append(ok(len(consults) == 1, "failed (код-задача) → consult"))

# (5) CURATOR_SCOPE=0: done без коммита → consult (прежнее поведение)
print("(5) CURATOR_SCOPE=0 → прежнее поведение:")
os.environ["CURATOR_SCOPE"] = "0"
consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 109, "задача: проверь логи", "логи чистые", status="done")
res.append(ok(len(consults) == 1, "CURATOR_SCOPE=0: done read-only → consult (прежнее поведение)"))

os.environ.pop("CURATOR_SCOPE", None)
consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328", 110, "задача: проверь логи", "логи чистые", status="done")
res.append(ok(len(consults) == 1, "CURATOR_SCOPE отсутствует: done read-only → consult (прежнее поведение)"))

# (6) цепь (_maybe_curator_chain): CURATOR_SCOPE не влияет
print("(6) цепь → CURATOR_SCOPE не меняет поведение:")
os.environ["CURATOR_SCOPE"] = "1"

class FakeBC6:
    def __init__(s):
        s.rows = {}
        s.nid = 400
        parent_text = "декомпозируй: проверь весь стек"
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": "Filipp-328-dec", "task_text": parent_text,
                         "status": "done", "result": "1. шаг\n2. шаг", "updated": "2026-07-15T00:00:00+00:00"}
        s.pid = s.nid
        for i in (1, 2):
            s.nid += 1
            s.rows[s.nid] = {"id": s.nid, "from": "Filipp-328-dec",
                             "task_text": f"[шаг {i}/2 родитель {s.pid}] шаг {i}",
                             "status": "done", "result": f"шаг {i} прошёл", "updated": "2026-07-15T00:00:00+00:00"}
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def enqueue_task(s, frm, text, lane=None):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": "new",
                         "result": "", "updated": "2026-07-15T00:00:00+00:00"}
        return {"ok": True, "id": s.nid}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def claim_task(s, tid, lane=None): return {"ok": True}

fb6 = FakeBC6()
OD.bc = fb6
consults.clear(); OD._curated.clear(); OD._summarized.clear()
OD._dec_post_summary(fb6.pid)
sums = [r for r in fb6.rows.values() if str(r["task_text"]).startswith("[сводка родитель")]
res.append(ok(len(sums) == 1, "сводка встала как обычно"))
res.append(ok(len(consults) == 1 and "декомпозируй: проверь весь стек" in consults[0][0],
              "CURATOR_SCOPE=1 не блокирует консультацию куратора ЦЕПИ"))

# (7) интеграция: process_new done read-only → ноль consult; done с коммитом → consult
print("(7) интеграция process_new:")
os.environ["CURATOR_SCOPE"] = "1"

fb, t = setup(("done", "DNS проверен, все записи ОК, хвостов нет"))
OD.process_new()
res.append(ok(consults == [] and fb.rows[t]["status"] == "done",
              "process_new: done read-only → ноль consult, финал цел"))

fb, t = setup(("done", "фикс gate.py — коммит 61b7c44, git push done"))
OD.process_new()
res.append(ok(len(consults) == 1 and consults[0][0] == "задача: проверь DNS записи",
              "process_new: done с коммитом → consult"))

fb, t = setup(("failed", "DNS недоступен, хвостов нет"))
OD.process_new()
res.append(ok(len(consults) == 1, "process_new: failed (нет коммита) → consult"))

# cleanup
os.environ.pop("CURATOR_SCOPE", None)
OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_rp
OD._curator_consult = _real_consult
OD._curated.clear(); OD._summarized.clear()

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
