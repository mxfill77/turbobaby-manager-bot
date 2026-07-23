# read-only: живой quote_price на проде — PCX 160 (нет в парке) + NMAX 4957 ближайшие даты
import json, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

b = BridgeClient(timeout=60)

print("=== quote_price bike='PCX 160' 04.07-11.07 ===")
r1 = b._call("quote_price", bike="PCX 160", date_start="04.07.2026", date_end="11.07.2026")
print(json.dumps(r1, ensure_ascii=False, indent=1))

print("=== quote_price bike=4957 (NMAX 155 GREEN-B, ДОМА) 04.07-11.07 ===")
r2 = b._call("quote_price", bike="4957", date_start="04.07.2026", date_end="11.07.2026")
print(json.dumps(r2, ensure_ascii=False, indent=1))
