"""Get full result of task #342."""
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient

bc = BridgeClient()

r = bc._call("get_pending", status="failed", lane="pc")
tasks = r.get("items", [])
for t in tasks:
    if str(t.get("id")) == "342":
        print(f"ID: {t.get('id')}")
        print(f"Status: {t.get('status','')}")
        print(f"Lane: {t.get('lane','')}")
        print(f"From: {t.get('from','')}")
        print(f"Created: {t.get('created','')}")
        print(f"Updated: {t.get('updated','')}")
        print(f"\nTask text: {t.get('task_text','')}")
        print(f"\nResult: {t.get('result','')}")
        break
