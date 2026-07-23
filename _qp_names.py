# read-only: все имена байков парка
import json, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

b = BridgeClient(timeout=60)
fl = b.fleet()
for bike in fl["data"]["bikes"]:
    print(bike["number"], "|", bike["name"], "|", bike["status"],
          "|", (bike.get("current_rental") or {}).get("end_date", ""))
