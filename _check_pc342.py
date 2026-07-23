"""Check PC lane for tasks around #342."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Check PC lane for all statuses
print("=== PC LANE ===")
for status in ["done", "failed", "in_progress", "needs_approval", "approved", "new"]:
    r = bc._call("get_pending", status=status, lane="pc")
    tasks = r.get("items", [])
    nearby = [t for t in tasks if 335 <= int(t.get('id',0)) <= 350]
    if nearby:
        print(f"\n{status} (pc lane) nearby:")
        for t in nearby:
            print(f"  id={t.get('id')} task={str(t.get('task_text',''))[:80]} result={str(t.get('result',''))[:100]}")
    if tasks:
        ids = [t.get('id',0) for t in tasks]
        nearby_ids = [i for i in ids if 335 <= int(i) <= 350]
        if nearby_ids:
            print(f"  {status} pc: nearby={nearby_ids}")

# Also check 'all' lane
print("\n=== ALL LANES ===")
for status in ["done", "in_progress"]:
    r = bc._call("get_pending", status=status, lane="all")
    tasks = r.get("items", [])
    nearby = [t for t in tasks if 335 <= int(t.get('id',0)) <= 350]
    if nearby:
        print(f"\n{status} (all lanes) nearby:")
        for t in nearby:
            print(f"  id={t.get('id')} lane={t.get('lane','')} task={str(t.get('task_text',''))[:80]} result={str(t.get('result',''))[:100]}")
    print(f"  {status} all: total={len(tasks)}")
