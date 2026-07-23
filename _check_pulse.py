import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

c = BridgeClient()
r = c._call("read_doc", name="pulse")
if r.get("ok"):
    print("PULSE:", r.get("text", "").strip())
else:
    print("PULSE ERROR:", r)
