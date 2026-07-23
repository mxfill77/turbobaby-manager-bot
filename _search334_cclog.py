"""Search cc_log for #334 and lesson_router mentions."""
import sys, re
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="cc_log")
content = r.get("data", {}).get("content", "") if isinstance(r.get("data"), dict) else r.get("data", "")
if not content:
    content = str(r)

# Look for 334, 342, lesson_router, рестарт бота, смоук
for pattern in ["334", "lesson_router", "LESSON_LLM", "рестарт бота", "смоук", "smoke", "#340", "#341", "#343"]:
    positions = [m.start() for m in re.finditer(re.escape(pattern), content)]
    if positions:
        print(f"\n=== '{pattern}' found at {positions[:3]} ===")
        for pos in positions[:2]:
            print(content[max(0,pos-80):pos+200])
    else:
        print(f"'{pattern}' not found")
