"""Read-only: KB_PULSE (protocol 'проверь')."""
import sys, os
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="pulse")
print("PULSE ok=", r.get("ok"))
print(r.get("text", "")[:800])
