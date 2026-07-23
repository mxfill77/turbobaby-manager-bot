import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
lines = text.splitlines()
for ln in lines:
    if ln.startswith("DONE 2026-07-08 13:09"):
        print(ln)
        break
