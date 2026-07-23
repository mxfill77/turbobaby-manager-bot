"""Read-only: читаем KB_MASTER целиком, сохраняем снимок в /tmp для бэкапа."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text") or r.get("content") or ""
print("LEN:", len(text))
with open("/tmp/kb_master_backup_20260712.txt", "w", encoding="utf-8") as f:
    f.write(text)
print(text)
