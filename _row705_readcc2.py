"""Read-only: полный текст DONE-записи про смок @66 (инцидент row705)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
lines = r.get("text", "").split("\n")
print(lines[5])
