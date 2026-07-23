"""Read-only: найти в cc_log запись «конверт 2 деплоя Bridge» и напечатать её целиком."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
idx = text.find("конверт 2")
print("idx:", idx)
if idx == -1:
    # поиск в архиве
    ra = c._call("read_doc", name="cc_log_archive")
    ta = ra.get("text", "")
    print("archive ok:", ra.get("ok"), "| len:", len(ta))
    ia = ta.find("конверт 2")
    print("archive idx:", ia)
    if ia != -1:
        print(ta[max(0, ia - 500):ia + 4000])
else:
    print(text[max(0, idx - 500):idx + 4000])
