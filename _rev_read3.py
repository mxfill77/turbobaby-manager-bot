#!/usr/bin/env python3
"""Читаю KB_MASTER после строки 127 (после 07.07 блока)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)
r = c._call("read_doc", name="index")
txt = r.get("text", "") or ""
lines = txt.split("\n")

print(f"Total lines: {len(lines)}")

# Find key section headers
for i, line in enumerate(lines):
    if any(x in line for x in ["РАЗДЕЛ", "⭐", "13.07", "14.07", "15.07", "WA", "WhatsApp", "360dialog", "webhook"]):
        print(f"Line {i}: {line[:120]}")

print("\n--- Lines 120-320 (after 07.07 block) ---")
for i, line in enumerate(lines[120:320], start=120):
    print(f"{i}: {line}")
