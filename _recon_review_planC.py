"""Read-only: найти в KB_review запись PLAN 21:40 (часть C — декомпозер)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="review")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
text = r.get("text", "")
idx = text.find("21:40")
print("idx 21:40:", idx)
if idx >= 0:
    print(text[max(0, idx - 500):idx + 6000])
else:
    print(text[:4000])
