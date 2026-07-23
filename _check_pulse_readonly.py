import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="pulse")
if r.get("ok"):
    print("PULSE:", r.get("text", "").strip())
else:
    print("PULSE READ FAIL:", r)
p = c.ping()
print("PING:", p)
