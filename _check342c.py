"""Check task #342 - fixed to use 'items' not 'data'."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

# Check raw response format
r = bc._call("get_pending", status="done")
print(f"Raw done response keys: {list(r.keys())}")
print(f"Raw done response: {str(r)[:500]}")

# Try with 'items' key
items = r.get("items", r.get("data", []))
print(f"\nItems type: {type(items)}, count: {len(items) if isinstance(items, list) else 'N/A'}")

# Search across all statuses using correct key
print("\n\nSearching all statuses for task #342:")
for status in ["done", "failed", "in_progress", "needs_approval", "approved", "new"]:
    r = bc._call("get_pending", status=status)
    tasks = r.get("items", r.get("data", []))
    if not isinstance(tasks, list):
        tasks = []
    for t in tasks:
        if str(t.get("id")) == "342":
            print(f"FOUND! status={status}")
            print(f"Result: {t.get('result', '')[:300]}")
            print(f"Full: {t}")

    if tasks:
        print(f"  {status}: {len(tasks)} tasks, ids={[t.get('id') for t in tasks[:5]]}")
    else:
        print(f"  {status}: 0 tasks")
