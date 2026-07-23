"""Read-only: искать записи 17.07 в cc_log."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
t = r.get("text", "")
print("len=", len(t))
for i, line in enumerate(t.splitlines()):
    if "2026-07-17" in line or "17.07" in line:
        print(f"[{i}] {line[:300]}")
