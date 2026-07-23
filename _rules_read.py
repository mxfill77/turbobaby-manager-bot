"""Read-only: показать структуру KB_RULES перед точечной вставкой доктрины подтверждений."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="rules")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
lines = r.get("text", "").split("\n")
print("total lines:", len(lines))
for i, ln in enumerate(lines[:80]):
    print(f"{i:3} | {ln[:110]}")
