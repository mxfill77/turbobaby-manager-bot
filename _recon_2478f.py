import sys, json
sys.path.insert(0, '/root/turbobaby-manager-bot')

from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

client = BridgeClient(os.environ['BRIDGE_URL'])

result = client.fleet()
data = result.get('data', {})
bikes = data.get('bikes', [])
print(f"Fleet bikes count: {len(bikes)}")

for b in bikes:
    name = b.get('name', '') or b.get('bike', '') or str(b)
    if '2478' in str(b):
        print(f"\n=== XADV 750 GREY 2478 ===")
        print(json.dumps(b, ensure_ascii=False, indent=2))
        break
