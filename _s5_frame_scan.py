"""Read-only: показать заголовки и структуру записей архива (строки 300-1080)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log_archive")
lines = r.get("text", "").split("\n")
import re
for i, ln in enumerate(lines[:1080]):
    if re.match(r"^(PLAN|DONE|NOTE|WAITING|BLOCKED|SKIPPED)\b", ln.strip()):
        print(f"{i:5} | {ln[:165]}")
