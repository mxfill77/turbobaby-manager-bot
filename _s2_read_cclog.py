"""Read-only: найти NOTE-список расхождений KB_MASTER в cc_log (шаг 2/7 родитель 33)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
lines = text.split("\n")
# показать всё с NOTE и контекст вокруг
for i, ln in enumerate(lines):
    if "NOTE" in ln:
        print(f"--- NOTE at line {i} ---")
        for j in range(i, min(i + 60, len(lines))):
            print(f"{j:4} | {lines[j]}")
        print()
