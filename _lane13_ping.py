# Повторный ping Bridge (3 попытки с паузой) — диагностика 404 из селфтеста заявки 13.
import time
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

b = BridgeClient()
for i in range(3):
    r = b.ping()
    print("attempt", i + 1, "->", str(r)[:300])
    if r.get("ok"):
        print("PING OK, version:", r.get("version"))
        sys.exit(0)
    time.sleep(5)
print("PING STILL FAILING")
sys.exit(1)
