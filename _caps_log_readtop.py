import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient
b = BridgeClient()
d = b.read_doc(name="cc_log")
txt = d.get("text") if isinstance(d, dict) else str(d)
print("=== ok:", isinstance(d, dict) and d.get("ok"), "len:", len(txt or ""))
print("---- first 1600 chars ----")
print((txt or "")[:1600])
