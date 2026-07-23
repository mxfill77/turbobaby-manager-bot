"""Read-only: показать структуру cc_log (врезка ═-строка) перед вставкой NOTE."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
lines = r.get("text", "").split("\n")
print("total lines:", len(lines))
# индекс первой строки целиком из ═
import re
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
print("first ═-only line index:", sep)
print("=== первые 40 строк ===")
for i, ln in enumerate(lines[:40]):
    print(f"{i:3} | {ln[:100]}")
