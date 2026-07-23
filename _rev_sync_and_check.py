#!/usr/bin/env python3
"""Ревизия 16.07: синк project_state в Brain + запуск registry_check."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=90)

# 1. Синк project_state (docs/*.md изменён → синкаем в Brain)
with open(os.path.join(os.path.dirname(__file__), "docs/project_state.md")) as f:
    ps_txt = f.read()

print(f"project_state.md: {len(ps_txt)} chars")
w = c.write_doc(name="project_state", text=ps_txt)
if w.get("ok"):
    print("project_state synced to Brain OK")
else:
    print(f"project_state sync FAILED: {w}")
