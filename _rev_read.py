#!/usr/bin/env python3
"""Чтение Brain-доков для ревизии 16.07."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from bridge_client import BridgeClient

c = BridgeClient(timeout=60)

for name in ["index", "review", "project_state", "rules"]:
    r = c._call("read_doc", name=name)
    ok = r.get("ok")
    txt = r.get("text", "") or ""
    print(f"\n=== {name} (ok={ok}, len={len(txt)}) ===")
    if ok:
        print(txt[:6000])
    else:
        print(r)
