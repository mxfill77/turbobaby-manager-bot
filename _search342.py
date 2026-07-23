"""Search all of cc_log for task #342 mentions."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="cc_log")
content = r.get("data", {}).get("content", "") if isinstance(r.get("data"), dict) else r.get("data", "")
if not content:
    content = str(r)

# Search for all occurrences of 342
import re
positions = [m.start() for m in re.finditer(r'34[12]', content)]
print(f"Total cc_log length: {len(content)}")
print(f"Found mentions near '342': {positions}")
for pos in positions[:5]:
    print(f"\n--- pos {pos} ---")
    print(content[max(0,pos-100):pos+300])
