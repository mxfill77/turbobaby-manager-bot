"""Read-only: dump raw read_doc response keys for pulse."""
import json
from bridge_client import BridgeClient

c = BridgeClient()
p = c._call("read_doc", name="pulse")
print(json.dumps(p, ensure_ascii=False)[:1500])
