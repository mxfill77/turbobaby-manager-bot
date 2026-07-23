"""Read-only: KB_MASTER §1-2 + поиск рамки в sessions_log/review."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

r = c._call("read_doc", name="master") if False else None
# ключ KB_MASTER в манифесте может быть 'master' — сначала посмотреть манифест
m = c._call("list_brain")
items = m.get("files") or m.get("items") or m.get("docs") or []
print("manifest keys:")
for it in items:
    print(" ", it if isinstance(it, str) else (it.get("name") or it.get("key"), it.get("id"), it.get("title")))
