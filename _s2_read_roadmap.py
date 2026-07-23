"""Read-only: дамп roadmap_master для актуализации статусов."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="roadmap_master")
text = r.get("text", "")
print("ok:", r.get("ok"), "| len:", len(text))
with open("/tmp/roadmap_master_snapshot.txt", "w", encoding="utf-8") as f:
    f.write(text)
print("saved /tmp/roadmap_master_snapshot.txt")
