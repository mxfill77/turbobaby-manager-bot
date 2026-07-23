"""Read-only: найти в cc_log DONE «шаг 7/7 родитель 33» (список орфанов, заявка 40)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
lines = text.split("\n")
hits = [i for i, ln in enumerate(lines) if "7/7" in ln and "33" in ln]
print("hits:", hits)
for i in hits:
    lo, hi = max(0, i - 2), min(len(lines), i + 80)
    print(f"=== контекст строки {i} ===")
    for j in range(lo, hi):
        print(f"{j:4} | {lines[j]}")
    print()
