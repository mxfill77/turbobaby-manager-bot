import json
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="pulse")
print(json.dumps(r, ensure_ascii=False)[:2000])
