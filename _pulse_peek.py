import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient()
r = c._call("read_doc", name="pulse")
print("ok:", r.get("ok"))
print("----PULSE----")
print(r.get("text",""))
print("----END----")
