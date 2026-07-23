from bridge_client import BridgeClient

bc = BridgeClient()
p = bc.ping()
print("ping:", p.get("ok"), p.get("version", ""), p.get("status", ""))
for st in ("new", "in_progress", "needs_approval"):
    r = bc.get_pending(status=st)
    tasks = r.get("tasks") or r.get("items") or []
    print(st, len(tasks), [t.get("id") for t in tasks][:10])
