"""Read-only: cowork_log — ищем факты родителя 221 и powercfg."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cowork_log")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text") or r.get("content") or ""
with open("/tmp/cowork_snapshot_20260712.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("LEN:", len(text))
