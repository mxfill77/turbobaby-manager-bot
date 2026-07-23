"""Read cc_log head (первые 30 строк) — определить границу врезки. Read-only, зона 🟢."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
for i, ln in enumerate(r.get("text", "").splitlines()[:30]):
    print(i, repr(ln[:100]))
