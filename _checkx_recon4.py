"""Read-only: bridge ping + queue new/in_progress."""
from bridge_client import BridgeClient

c = BridgeClient()
print("ping:", c.ping().get("ok"))
for st in ("new", "in_progress", "needs_approval"):
    r = c.get_pending(status=st)
    tasks = (r.get("tasks") or r.get("data") or [])
    print(st, "ok=", r.get("ok"), "count=", len(tasks) if isinstance(tasks, list) else tasks)
