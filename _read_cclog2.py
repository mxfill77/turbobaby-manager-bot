"""Read more of cc_log to find task #342."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="cc_log")
content = r.get("data", {}).get("content", "") if isinstance(r.get("data"), dict) else r.get("data", "")
if not content:
    content = str(r)

# Search for 342
idx = content.find("342")
if idx >= 0:
    print(f"Found '342' at position {idx}")
    print(content[max(0,idx-200):idx+800])
else:
    print("'342' not found in cc_log top portion")
    print(f"Total length: {len(content)}")
    # Print chars 4000-8000
    print("\n--- chars 4000-8000 ---")
    print(content[4000:8000])
