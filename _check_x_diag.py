import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

c = BridgeClient(os.environ['BRIDGE_URL'])

# 1. Pulse
print("=== KB_PULSE ===")
r = c._call("read_doc", name="pulse")
if r.get("ok"):
    print(r.get("text", "")[:500])
else:
    print("ERR:", r)

# 2. Ping Bridge
print("\n=== BRIDGE PING ===")
p = c.ping()
print(p)
