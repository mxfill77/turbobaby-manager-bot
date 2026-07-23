"""Read-only: найти в cc_log записи про инцидент row705 (контекст для урока-класса)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
lines = text.split("\n")
hits = [i for i, ln in enumerate(lines) if "705" in ln]
print("hit lines:", hits[:20])
for i in hits[:6]:
    for j in range(max(0, i - 2), min(len(lines), i + 6)):
        print(f"{j:4} | {lines[j][:180]}")
    print("---")
