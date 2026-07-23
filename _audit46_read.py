"""Read-only: аудит задачи 46 — записи в cc_log (верх) + текущий пульс."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("cc_log ok:", r.get("ok"), "| len:", len(r.get("text", "")))
lines = r.get("text", "").split("\n")
print("=== первые 80 строк cc_log ===")
for i, ln in enumerate(lines[:80]):
    print(f"{i:3} | {ln[:160]}")

p = c._call("read_doc", name="pulse")
print("\n=== pulse ===")
print("ok:", p.get("ok"))
print(p.get("text", ""))
