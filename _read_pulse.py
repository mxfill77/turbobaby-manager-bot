import asyncio, sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')

async def main():
    client = BridgeClient(os.environ['BRIDGE_URL'])
    result = client._call("read_doc", name='pulse')
    print(result)

asyncio.run(main())
