"""Read-only health recon: Bridge ping + KB_PULSE + orchestrator queue new/in_progress."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

c = BridgeClient()
print("PING:", c.ping())

p = c._call("read_doc", name="pulse")
content = p.get("content") or p.get("text") or ""
print("PULSE ok:", p.get("ok"), "|", str(content)[:400])

for st in ("new", "in_progress"):
    q = c.get_pending(status=st, lane="all")
    tasks = q.get("tasks") or []
    print(f"QUEUE {st}: ok={q.get('ok')} count={len(tasks)}")
    for t in tasks[:5]:
        print("  -", str(t)[:200])
