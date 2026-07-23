"""Find task #342 in all done tasks."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Get all done tasks
r = bc._call("get_pending", status="done")
tasks = r.get("items", [])
print(f"Total done tasks: {len(tasks)}")

# Search for #342
for t in tasks:
    if str(t.get("id")) == "342":
        print(f"\n=== FOUND #342 ===")
        print(f"Status: done")
        print(f"Created: {t.get('created','')}")
        print(f"From: {t.get('from','')}")
        print(f"Task: {t.get('task_text','')[:200]}")
        print(f"Result: {t.get('result','')}")
        break
else:
    print("\n#342 not in done. Checking failed...")
    r2 = bc._call("get_pending", status="failed")
    tasks2 = r2.get("items", [])
    for t in tasks2:
        if str(t.get("id")) == "342":
            print(f"\n=== FOUND #342 in FAILED ===")
            print(f"Created: {t.get('created','')}")
            print(f"Task: {t.get('task_text','')[:200]}")
            print(f"Result: {t.get('result','')}")
            break
    else:
        # Print all done task IDs around 342
        print("Not found in done/failed. IDs in done:")
        ids = sorted([t.get('id',0) for t in tasks])
        # Show ids around 342
        nearby = [i for i in ids if 335 <= i <= 350]
        print(f"Nearby ids (335-350): {nearby}")
        print(f"All ids: {ids[:30]}...{ids[-10:]}")
