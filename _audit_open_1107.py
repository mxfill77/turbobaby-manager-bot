"""Read-only: открытые аудит-замечания целиком (для разбора утренней сводки)."""
import json
from bridge_client import BridgeClient

b = BridgeClient()
r = b.audit_list()
if not r.get("ok"):
    print("ERR:", r.get("error"))
    raise SystemExit(1)
items = r.get("items") or []
opn = [it for it in items if str(it.get("status", "")).lower() in ("new", "open", "", "pending")]
print(f"всего {len(items)}, открытых {len(opn)}")
for it in opn:
    print("=" * 70)
    print(json.dumps(it, ensure_ascii=False, indent=1))
