"""Search Bridge for tasks related to parent #334."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

found = []
for lane in [None, "vps", "pc"]:
    for status in ["done", "failed", "in_progress", "needs_approval", "approved", "new"]:
        kw = {"status": status}
        if lane:
            kw["lane"] = lane
        try:
            r = bc._call("get_pending", **kw)
            tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
            for t in tasks:
                tid = str(t.get("id", ""))
                text = t.get("task", "") or ""
                result = t.get("result", "") or ""
                if "334" in tid or "334" in text or "342" in tid or "шаг 6" in text:
                    found.append((lane, status, tid, text[:100], result[:200]))
        except Exception as e:
            pass

if found:
    for item in found:
        print(f"lane={item[0]} status={item[1]} id={item[2]}")
        print(f"  task: {item[3]}")
        print(f"  result: {item[4]}")
else:
    print("No tasks found related to #334 or #342")
    # Print all done tasks to see what's there
    print("\nAll done tasks (first 10):")
    r = bc._call("get_pending", status="done")
    tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
    for t in tasks[:10]:
        print(f"  id={t.get('id')} from={t.get('from','')} text={str(t.get('task',''))[:80]}")
