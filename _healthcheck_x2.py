"""Read-only: верх cc_log — есть ли уже DONE по «проверь X» 17.07."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
doc = bc._call("read_doc", name="cc_log")
content = doc.get("content") or doc.get("text") or str(doc)
print(str(content)[:2500])
