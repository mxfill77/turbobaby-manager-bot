"""Read-only: первые строки cc_log — где врезка/шапка."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
lines = r.get("text", "").split("\n")
for i, ln in enumerate(lines[:12]):
    print(f"{i:3} | {ln[:120]}")
