"""Read-only: найти вердикт разведки 14:06 (O3-3c А+Б) в cc_log."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
lines = text.split("\n")
# печатаем первые 200 строк — вердикт свежий, должен быть сверху
for i, ln in enumerate(lines[:220]):
    print(f"{i:3} | {ln}")
