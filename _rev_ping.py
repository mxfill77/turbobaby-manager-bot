#!/usr/bin/env python3
"""Диагностика Bridge: ping + write_doc тест."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)

print("=== ping ===")
r = c._call("ping")
print(r)

print("=== read_doc pulse ===")
r2 = c._call("read_doc", name="pulse")
print("ok:", r2.get("ok"), "len:", len(r2.get("text") or ""))

print("=== write_doc pulse test ===")
r3 = c._call("write_doc", name="pulse", text="2026-07-16 07:00 | 🟡 | ревизия — сессия 2 | write_doc тест")
print("write result:", r3)
