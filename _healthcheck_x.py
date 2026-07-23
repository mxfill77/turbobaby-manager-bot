"""Read-only проверка: Bridge ping + чтение пульса (name=pulse)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
try:
    print("PING:", bc.ping())
except Exception as e:
    print("PING FAIL:", e)

try:
    doc = bc._call("read_doc", name="pulse")
    content = doc.get("content") or doc.get("text") or str(doc)
    print("PULSE:", str(content)[:600])
except Exception as e:
    print("PULSE FAIL:", e)
