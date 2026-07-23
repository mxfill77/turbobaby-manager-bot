"""Read-only: найти записи 30.06 про инструкции приложения / рамку в cc_log_archive."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log_archive")
text = r.get("text", "")
lines = text.split("\n")
print("total lines:", len(lines))

# 1) все строки с датой 2026-06-30 (заголовки записей)
for i, ln in enumerate(lines):
    if "2026-06-30" in ln and any(k in ln for k in ("PLAN", "DONE", "NOTE", "WAITING", "BLOCKED", "SKIPPED")):
        print(f"{i:5} | {ln[:170]}")
