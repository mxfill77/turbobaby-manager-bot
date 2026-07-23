import asyncio
import sys
import os
os.environ['BRIDGE_ALLOW_NETWORK'] = '1'
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

async def main():
    client = BridgeClient(os.environ['BRIDGE_URL'])
    result = client._call("read_doc", name="pulse")
    print(result)

asyncio.run(main())
