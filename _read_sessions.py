"""Search sessions_log for task #342 and #334."""
import sys, re
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="sessions_log")
content = r.get("data", {}).get("content", "") if isinstance(r.get("data"), dict) else r.get("data", "")
if not content:
    content = str(r)

print(f"sessions_log length: {len(content)}")
# Search for 342
positions = [m.start() for m in re.finditer(r'#?342', content)]
print(f"Occurrences of '342': {len(positions)}")
for pos in positions[:5]:
    print(f"\n--- at {pos} ---")
    print(content[max(0,pos-150):pos+400])
