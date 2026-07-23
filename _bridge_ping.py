"""Ping Bridge and check all task statuses."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Ping
r = bc.ping()
print(f"Ping: {r}")

# Check with 'all' status to see everything
print("\nAll tasks (status=all):")
try:
    r = bc._call("get_pending", status="all")
    tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
    print(f"Count: {len(tasks)}")
    for t in tasks[:30]:
        print(f"  id={t.get('id')} status={t.get('status','')} from={t.get('from','')} text={str(t.get('task',''))[:70]}")
except Exception as e:
    print(f"Error: {e}")

# Check with from Filipp-328-dec (dec chain tasks)
print("\nDec tasks from Filipp-328-dec:")
try:
    r = bc._call("get_pending", status="done")
    tasks = r.get("data", []) if isinstance(r.get("data"), list) else []
    print(f"Done count: {len(tasks)}")
    for t in tasks[:5]:
        print(f"  id={t.get('id')} text={str(t.get('task',''))[:80]}")
except Exception as e:
    print(f"Error: {e}")
