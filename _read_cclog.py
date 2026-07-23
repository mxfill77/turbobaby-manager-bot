"""Read cc_log top portion to find task #342 result."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="cc_log")
content = r.get("data", {}).get("content", "") if isinstance(r.get("data"), dict) else r.get("data", "")
if not content:
    content = str(r)

# Print first 4000 chars
print(content[:4000])
