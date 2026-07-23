"""Read-only: полный result задачи #274 (родитель pcloc-dec)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient
bc = BridgeClient(timeout=60)

r = bc.get_pending("done", lane="all")
if not r.get("ok"):
    print("Ошибка:", r.get("error"))
    sys.exit(1)

for it in r.get("items", []):
    if str(it.get("id")) == "274":
        print("=== TASK #274 ===")
        print("from:", it.get("from"))
        print("task_text:", it.get("task_text"))
        print("\n=== FULL RESULT ===")
        print(it.get("result") or "(пусто)")
        break
else:
    print("Задача #274 не найдена в done")
