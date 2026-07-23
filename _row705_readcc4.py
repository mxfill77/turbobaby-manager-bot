"""Read-only: полные тексты двух верхних DONE-записей cc_log (08:43 и 08:41)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
i1 = text.find("DONE 2026-07-08 08:43")
i2 = text.find("PLAN 2026-07-08 08:33")
print(text[i1:i2])
