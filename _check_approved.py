"""Check approved/in_progress tasks + try to get task by id."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Try direct task lookup if Bridge supports it
try:
    r = bc._call("get_task", id=342)
    print("get_task result:", r)
except Exception as e:
    print(f"get_task not available: {e}")

# Check all lanes combined
print("\nChecking all statuses combined (no lane filter):")
for status in ["needs_approval", "approved", "in_progress", "done", "failed", "new"]:
    try:
        r = bc._call("get_pending", status=status)
        tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
        if tasks:
            print(f"\n{status}: {len(tasks)} tasks")
            for t in tasks[:20]:
                print(f"  id={t.get('id')} from={t.get('from','')} status={t.get('status','')} text={str(t.get('task',''))[:60]}")
    except Exception as e:
        print(f"{status} error: {e}")
