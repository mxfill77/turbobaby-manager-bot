"""Read-only: найти в cc_log вердикт разведки O3-2a (около 04:02) по Booking.js."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
text = r.get("text", "")
lines = text.split("\n")
# ищем записи с 04:0 или Booking/O3-2
hits = []
for i, ln in enumerate(lines):
    low = ln.lower()
    if "booking" in low or "o3-2" in low or "o3.2" in low or "04:02" in ln:
        hits.append(i)
print("hit lines:", hits[:30])
# печатаем окно вокруг первого блока хитов
if hits:
    start = max(0, hits[0] - 2)
    end = min(len(lines), hits[0] + 120)
    for i in range(start, end):
        print(f"{i:4} | {lines[i]}")
