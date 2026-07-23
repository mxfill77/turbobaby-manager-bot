"""Read-only: показать первые 40 строк cc_log (структура врезки перед записью DONE)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

r = BridgeClient()._call("read_doc", name="cc_log")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
for i, ln in enumerate(r.get("text", "").splitlines()[:40]):
    print(f"{i:3}| {ln[:120]}")
