# read-only проверка деплоя Bridge: ping + fleet(PCX 160) + clients(брони PCX) + get_pending CSV
import json, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

b = BridgeClient(timeout=60)

print("=== ping ===")
print(json.dumps(b.ping(), ensure_ascii=False))

print("=== fleet: PCX 160 bikes ===")
fl = b.fleet()
pcx = [x for x in fl.get("bikes", fl.get("items", [])) if "PCX" in str(x).upper()]
print(json.dumps(pcx, ensure_ascii=False, indent=1, default=str)[:3000])

print("=== clients active (busy periods for PCX) ===")
cl = b.clients("active")
items = cl.get("clients", cl.get("items", []))
pcx_busy = [x for x in items if "PCX" in str(x).upper()]
print(json.dumps(pcx_busy, ensure_ascii=False, indent=1, default=str)[:4000])

print("=== get_pending CSV (склейка статусов) ===")
gp = b._call("get_pending", status="done,failed")
print(json.dumps({k: gp.get(k) for k in ("ok", "error", "statuses")}, ensure_ascii=False),
      "| items:", len(gp.get("items", []) or []))
