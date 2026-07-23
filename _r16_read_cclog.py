"""Read cc_log to find PLAN entry from 17.07."""
from bridge_client import BridgeClient
import os
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()
result = bc._call("read_doc", name="cc_log")
print(f"Result keys: {list(result.keys())}")
print(f"Status: {result.get('status')}")
print(f"Error: {result.get('error')}")
content = result.get("content", result.get("text", ""))
print(f"Content length: {len(content)}")
print(content[:8000])
