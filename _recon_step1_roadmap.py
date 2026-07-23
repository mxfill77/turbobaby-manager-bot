"""Read-only: прочитать roadmap_master."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="roadmap_master")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
open("/tmp/_kb_roadmap.txt", "w").write(r.get("text", ""))
print(r.get("text", "")[:6000])
