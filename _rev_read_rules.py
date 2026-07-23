#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)
r = c._call("read_doc", name="rules")
print("ok:", r.get("ok"))
txt = r.get("text", "")
print(f"len={len(txt)}")
# Print last 50 lines
lines = txt.split("\n")
print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines[-60:], start=len(lines)-60):
    print(f"{i}: {line}")
