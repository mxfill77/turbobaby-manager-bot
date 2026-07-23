"""Read-only: KB_MASTER (name=index) целиком до §3 + поиск 'рамк' в sessions_log."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="index")
text = r.get("text", "")
print("KB_MASTER ok:", r.get("ok"), "len:", len(text))
lines = text.split("\n")
# печатаем до начала раздела 3
stop = len(lines)
for i, ln in enumerate(lines):
    if i > 5 and ("РАЗДЕЛ 3" in ln or "Раздел 3" in ln or ln.strip().startswith("## 3")):
        stop = i + 1
        break
for i, ln in enumerate(lines[:min(stop, 220)]):
    print(f"{i:4} | {ln[:175]}")

print("\n===== sessions_log: 'рамк' =====")
s = c._call("read_doc", name="sessions_log")
slines = s.get("text", "").split("\n")
for i, ln in enumerate(slines):
    if "рамк" in ln.lower():
        print(f"{i:5} | {ln[:170]}")
