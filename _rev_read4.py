#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)
r = c._call("read_doc", name="index")
txt = r.get("text", "") or ""
lines = txt.split("\n")

print("--- Lines 320-565 (11.07+, §4, §5) ---")
for i, line in enumerate(lines[320:565], start=320):
    print(f"{i}: {line}")
