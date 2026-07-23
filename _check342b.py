"""Read task #342 - try broader search including done tasks."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Try multi-status including done
for lane in [None, "vps", "pc"]:
    for status in ["done", "failed", "in_progress", "needs_approval", "approved", "new"]:
        kw = {"status": status}
        if lane:
            kw["lane"] = lane
        r = bc._call("get_pending", **kw)
        tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
        for t in tasks:
            if str(t.get("id")) == "342":
                print(f"FOUND lane={lane} STATUS={status}")
                print(f"RESULT: {t.get('result', '')[:500]}")
                print(f"FULL: {t}")
                sys.exit(0)

print("Task #342 not found")
print("Trying read_doc cc_log for recent entries about 342...")
