"""Хвост cc_log (записи шагов 1-2 родителя 33). Read-only, зона 🟢."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
t = r.get("text", "")
print(t[9000:])
