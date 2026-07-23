#!/usr/bin/env python3
"""Проверка: долетел ли write в review_archive."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)
r = c._call("read_doc", name="review_archive")
txt = r.get("text", "") or ""
print(f"review_archive len={len(txt)}")
print(f"Starts with: {txt[:300]}")
print(f"Contains 'ПЕРЕНЕСЕНО 2026-07-16': {'ПЕРЕНЕСЕНО 2026-07-16' in txt}")
