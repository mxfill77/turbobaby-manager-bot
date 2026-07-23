import os, json
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient(timeout=60)
r = c.get_pending(status="done", lane="all")
print("keys:", list(r.keys()))
tasks = r.get("tasks") or []
print("count:", len(tasks))
for t in tasks[-12:]:
    print(json.dumps({k: str(v)[:120] for k, v in t.items()}, ensure_ascii=False))
