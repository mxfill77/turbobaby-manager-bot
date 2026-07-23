import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "len:", len(r.get("text","")))
lines = r.get("text","").splitlines()
for i, ln in enumerate(lines[:40]):
    mark = "  <== ═-ONLY" if ln and set(ln.strip()) == {"═"} else ""
    print(f"{i:>3}| {ln[:90]}{mark}")
