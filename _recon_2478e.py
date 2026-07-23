import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')

from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

client = BridgeClient(os.environ['BRIDGE_URL'])

# Try ping first
ping = client.ping()
print(f"ping: {ping}")

# Try fleet with different approach
result = client.fleet()
print(f"fleet ok={result.get('ok')} keys={list(result.keys())}")
print(f"fleet raw: {str(result)[:500]}")

# Try service list
result2 = client.service_list()
print(f"service_list ok={result2.get('ok')} keys={list(result2.keys())}")
print(f"service_list raw: {str(result2)[:500]}")
