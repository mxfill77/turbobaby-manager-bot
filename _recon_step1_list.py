"""Read-only: list_brain — найти roadmap; затем прочитать его."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("list_brain")
print("ok:", r.get("ok"))
import json
files = r.get("files") or r.get("items") or r.get("manifest") or r
if isinstance(files, dict):
    print(json.dumps(files, ensure_ascii=False, indent=1)[:4000])
else:
    for f in files:
        print(f)
