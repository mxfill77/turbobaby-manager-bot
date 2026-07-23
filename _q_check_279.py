"""Read-only: проверить состояние задач #279, #274 и все needs_approval в очереди."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient
bc = BridgeClient(timeout=60)

print("=== needs_approval ===")
r = bc.get_pending("needs_approval", lane="all")
if r.get("ok"):
    items = r.get("items") or []
    print(f"Кол-во: {len(items)}")
    for it in items:
        print(f"  id={it.get('id')} from={it.get('from')} lane={it.get('lane')} updated={it.get('updated')}")
        print(f"    result={str(it.get('result') or '')[:200]}")
        print(f"    task_text={str(it.get('task_text') or '')[:100]}")
else:
    print(f"Ошибка: {r.get('error')}")

print()
print("=== all statuses search for #279 and #274 ===")
for st in ("new", "in_progress", "done", "failed", "needs_approval", "approved"):
    r2 = bc.get_pending(st, lane="all")
    if not r2.get("ok"):
        continue
    for it in (r2.get("items") or []):
        if str(it.get("id")) in ("279", "274"):
            print(f"  FOUND id={it.get('id')} status={st} from={it.get('from')} updated={it.get('updated')}")
            print(f"    task_text={str(it.get('task_text') or '')[:150]}")
            print(f"    result={str(it.get('result') or '')[:200]}")

print()
print("=== approved ===")
r3 = bc.get_pending("approved", lane="all")
if r3.get("ok"):
    items3 = r3.get("items") or []
    print(f"Approved tasks: {len(items3)}")
    for it in items3:
        print(f"  id={it.get('id')} from={it.get('from')} updated={it.get('updated')}")
        print(f"    result={str(it.get('result') or '')[:200]}")
else:
    print(f"Ошибка approved: {r3.get('error')}")

print()
print("=== open new tasks (top 5) ===")
r4 = bc.get_pending("new")
if r4.get("ok"):
    items4 = (r4.get("items") or [])[:5]
    for it in items4:
        print(f"  id={it.get('id')} from={it.get('from')}: {str(it.get('task_text') or '')[:80]}")
