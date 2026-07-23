"""Read-only: сырой ответ list_brain."""
from dotenv import load_dotenv
load_dotenv()
import json
from bridge_client import BridgeClient

c = BridgeClient()
m = c._call("list_brain")
print(json.dumps(m, ensure_ascii=False)[:4000])
