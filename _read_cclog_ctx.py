from bridge_client import BridgeClient
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
async def main():
    bc = BridgeClient(os.environ['BRIDGE_URL'])
    result = await bc.read_doc('cc_log')
    text = result if result else 'empty'
    print(text[:4000])
asyncio.run(main())
