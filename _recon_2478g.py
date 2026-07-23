import sys, json
sys.path.insert(0, '/root/turbobaby-manager-bot')

from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

client = BridgeClient(os.environ['BRIDGE_URL'])

# Bot Data: service_pending
r = client.service_pending_list(chat_id=-1002751134848)
print(f"service_pending_list: {json.dumps(r, ensure_ascii=False, indent=2)}")

# events for topic 83 (XADV 2478)
try:
    r2 = client.get_events(topic_id=83, chat_id=-1002751134848)
    print(f"\nevents: {json.dumps(r2, ensure_ascii=False)[:1000]}")
except Exception as e:
    print(f"events error: {e}")

# try list_events or get_info
try:
    r3 = client.list_events(topic_id=83, chat_id=-1002751134848)
    print(f"\nlist_events: {json.dumps(r3, ensure_ascii=False)[:1000]}")
except Exception as e:
    print(f"list_events error: {e}")
