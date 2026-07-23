"""Read-only: поиск «проверь X» по всему cc_log + длина дока."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
doc = bc._call("read_doc", name="cc_log")
content = str(doc.get("content") or doc.get("text") or doc)
print("LEN:", len(content))
idx = content.find("проверь X")
print("FOUND at:", idx)
if idx >= 0:
    print(content[max(0, idx - 300):idx + 500])
