"""read-only: cc_log верх — найти запись про set_caps 19:28 / Z3."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient
b = BridgeClient()
r = b._call("read_doc", name="cc_log")
txt = r.get("text") or r.get("content") or ""
print("LEN:", len(txt))
print(txt[:6000])
