"""Read-only: pulse + cc_log top for 'проверь X' health check."""
from bridge_client import BridgeClient

c = BridgeClient()
p = c._call("read_doc", name="pulse")
print("PULSE ok=", p.get("ok"))
print((p.get("data") or {}).get("content", "")[:600])
print("=" * 40)
log = c._call("read_doc", name="cc_log")
d = log.get("data") or {}
content = d.get("content", "")
print("CCLOG ok=", log.get("ok"), "len=", len(content))
print(content[:2500])
