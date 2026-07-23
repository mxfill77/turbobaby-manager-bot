# Селфтест полосы pc живьём (read-only для прода: пишет ТОЛЬКО в Bridge-очередь Bot Data,
# метка from=selftest-lane-pc НЕ в QUEUE_FROMS devbot'а -> карточек в Telegram не будет).
import os
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.chdir("/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

b = BridgeClient()
res = {"ok": True, "steps": []}

def step(name, ok, detail=""):
    res["steps"].append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), name, "|", detail)
    if not ok:
        res["ok"] = False

# 1. ping
r = b.ping()
step("ping", bool(r.get("ok")), str(r)[:200])
if not r.get("ok"):
    sys.exit(1)

# 2. enqueue lane=pc
r = b.enqueue_task("selftest-lane-pc", "[SELFTEST 04.07] проверка полосы pc — НЕ исполнять", lane="pc")
step("enqueue lane=pc", bool(r.get("ok")) and r.get("lane") == "pc", str(r)[:200])
tid = r.get("id")
if not r.get("ok") or tid is None:
    sys.exit(1)

def ids(rr):
    return [str(it.get("id")) for it in rr.get("items", [])]

# 3. get_pending БЕЗ lane (=vps) — тестовую задачу видеть НЕ должен
r = b.get_pending("new")
step("get_pending без lane НЕ видит pc-задачу", bool(r.get("ok")) and str(tid) not in ids(r),
     "lane=%s ids=%s" % (r.get("lane"), ids(r)))

# 4. get_pending lane=pc — должен видеть
r = b.get_pending("new", lane="pc")
step("get_pending lane=pc ВИДИТ задачу", bool(r.get("ok")) and str(tid) in ids(r),
     "lane=%s ids=%s" % (r.get("lane"), ids(r)))

# 5. guard чужой полосы: claim с lane=vps должен дать wrong_lane
r = b.claim_task(tid, lane="vps")
step("claim lane=vps -> wrong_lane (guard)", (not r.get("ok")) and r.get("error") == "wrong_lane", str(r)[:200])

# 6. claim своей полосой
r = b.claim_task(tid, lane="pc")
step("claim lane=pc -> ok", bool(r.get("ok")), str(r)[:200])

# 7. complete тестовой задачи (done, чтобы не висела в очереди)
r = b.complete_task(tid, "done", "selftest lane=pc пройден, задача тестовая, не исполнялась")
step("complete done", bool(r.get("ok")), str(r)[:200])

# 8. контроль: в new её больше нет ни в одной полосе
r = b.get_pending("new", lane="all")
step("после complete нет в new (lane=all)", bool(r.get("ok")) and str(tid) not in ids(r),
     "ids=%s" % ids(r))

print("RESULT:", "ALL PASS" if res["ok"] else "HAS FAIL", "| test task id =", tid)
sys.exit(0 if res["ok"] else 1)
