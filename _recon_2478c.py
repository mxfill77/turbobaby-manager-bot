import asyncio
import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')

from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

async def main():
    client = BridgeClient(os.environ['BRIDGE_URL'])

    result = await client.call('read_fleet', {})
    if result.get('ok'):
        bikes = result.get('bikes', [])
        for b in bikes:
            name = b.get('name', '')
            if '2478' in name or 'XADV' in name.upper():
                print(f"Bike: {name}")
                print(f"  Full data: {b}")
                break
        else:
            print(f"Bike 2478 NOT found in {len(bikes)} bikes")
            for b in bikes[:3]:
                print(f"  Sample bike keys: {list(b.keys())}")
    else:
        print(f"read_fleet failed: {result}")

    await client.close()

asyncio.run(main())
