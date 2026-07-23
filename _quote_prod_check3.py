# read-only: повтор ping + поиск PCX в списке мото через find_bike/fleet
import json
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

bc = BridgeClient()

r = bc._call("ping")
print("PING:", json.dumps(r, ensure_ascii=False))

fb = bc.find_bike("PCX")
print("FIND_PCX:", json.dumps(fb, ensure_ascii=False)[:2000])
