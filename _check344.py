"""Check what task #344 is (currently in_progress)."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

r = bc._call("get_pending", status="in_progress")
tasks = r.get("items", [])
for t in tasks:
    print(f"ID: {t.get('id')}")
    print(f"From: {t.get('from','')}")
    print(f"Lane: {t.get('lane','')}")
    print(f"Task: {t.get('task_text','')[:300]}")
    print(f"Result: {t.get('result','')[:100]}")
    print(f"Status: {t.get('status','')}")
    print()

# Also check what IDs 339-343 might have been
print("\nChecking if 339-343 were deleted/archived:")
print("IDs 335-350 in done:", [])
r2 = bc._call("get_pending", status="done")
done = [t.get('id',0) for t in r2.get("items",[])]
print([i for i in done if 335 <= i <= 350])

r3 = bc._call("get_pending", status="failed")
failed = [t.get('id',0) for t in r3.get("items",[])]
print("IDs 335-350 in failed:", [i for i in failed if 335 <= i <= 350])
