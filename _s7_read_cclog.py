"""Чтение cc_log (только name=) — вытащить DONE шагов родителя 33 для сводки. Read-only, зона 🟢."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
t = r.get("text", "")
print("LEN:", len(t))
print(t[:9000])
