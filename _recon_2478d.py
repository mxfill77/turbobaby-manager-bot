import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')

from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

client = BridgeClient(os.environ['BRIDGE_URL'])

result = client.fleet()
if result.get('ok'):
    bikes = result.get('bikes', [])
    for b in bikes:
        name = b.get('name', '') or b.get('bike', '')
        plate = str(b.get('plate', ''))
        if '2478' in name or '2478' in plate or 'XADV' in name.upper():
            print(f"Bike: {name}")
            print(f"Keys: {list(b.keys())}")
            print(f"Full: {b}")
    print(f"Total bikes: {len(bikes)}")
else:
    print(f"fleet failed: {result}")

result2 = client.service_list()
if result2.get('ok'):
    services = result2.get('services', [])
    for s in services:
        name = s.get('bike', '')
        if '2478' in name or 'XADV' in name.upper():
            print(f"\nService record: {s}")
    print(f"Total services: {len(services)}")
else:
    print(f"service_list failed: {result2}")
