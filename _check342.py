"""Read task #342 status from Bridge queue."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Try to find task #342 by checking all statuses
for status in ["done", "failed", "in_progress", "needs_approval", "approved", "new"]:
    r = bc.get_pending(status=status)
    tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
    for t in tasks:
        if str(t.get("id")) == "342":
            print(f"STATUS: {status}")
            print(f"TASK: {t}")
            sys.exit(0)

print("Task #342 not found in any status")
