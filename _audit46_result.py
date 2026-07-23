"""Read-only: результат задачи 46 из Bridge-очереди (сводка headless-CC)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c.get_pending_multi(["done", "reported"])
print("ok:", r.get("ok"), "| items:", len(r.get("items", [])))
for it in r.get("items", []):
    if str(it.get("id")) == "46":
        for k, v in it.items():
            print(f"{k}: {str(v)[:2500]}")
        break
else:
    print("id=46 не найден среди done/reported; статусы items:",
          [(it.get("id"), it.get("status")) for it in r.get("items", [])][:30])
