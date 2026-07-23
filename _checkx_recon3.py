"""Read-only: top of cc_log."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
t = r.get("text", "")
print("len=", len(t))
print(t[:3000])
