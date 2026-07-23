"""Read-only: свежий cc_log целиком в /tmp для grep."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text") or r.get("content") or ""
with open("/tmp/cclog_snapshot_20260712.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("LEN:", len(text))
