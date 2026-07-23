import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "len:", len(text))
print(text[:6000])
