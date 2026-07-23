"""Read-only: верх cc_log — контекст по гейту/clasp-настройкам и O3-3b."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
lines = text.split("\n")
for ln in lines[:80]:
    print(ln[:200])
