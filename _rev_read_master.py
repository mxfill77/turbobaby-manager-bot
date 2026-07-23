#!/usr/bin/env python3
"""Читаем KB_MASTER для планирования правки."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)
r = c._call("read_doc", name="index")
txt = r.get("text", "") or ""
lines = txt.split("\n")
print(f"Total chars: {len(txt)}, Total lines: {len(lines)}")
print("=== FULL TEXT ===")
for i, line in enumerate(lines):
    print(f"{i:4d}: {line}")
