# read-only: все имена байков из fleet, ищем PCX глазами
import json
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

bc = BridgeClient()
f = bc.fleet()
bikes = f.get("data", {}).get("bikes", [])
print("TOTAL:", len(bikes))
for b in bikes:
    print(b.get("name", ""))
