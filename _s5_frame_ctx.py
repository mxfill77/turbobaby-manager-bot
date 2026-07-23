"""Read-only: контекст блока правок приложения в cc_log_archive."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log_archive")
lines = r.get("text", "").split("\n")
for i in range(1000, 1170):
    print(f"{i:4} | {lines[i][:175]}")
