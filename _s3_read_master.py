"""Read-only: KB_MASTER (name=index) для сверки (шаг 3/7 родитель 33)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="index")
print("ok:", r.get("ok"), "| len:", len(r.get("text", "")))
print(r.get("text", ""))
