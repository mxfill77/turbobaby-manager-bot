import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if r.get("ok"):
    text = r.get("text", "")
    # Print first 3000 chars (recent entries)
    print(text[:3000])
else:
    print("ERROR:", r)
