# read-only: структура ответа fleet + поиск PCX
import json, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

b = BridgeClient(timeout=60)
fl = b.fleet()
print("keys:", list(fl.keys()))
raw = json.dumps(fl, ensure_ascii=False, default=str)
print("len:", len(raw))
print(raw[:1500])
idx = raw.upper().find("PCX")
print("PCX at:", idx)
if idx > 0:
    print(raw[max(0, idx-300):idx+600])
