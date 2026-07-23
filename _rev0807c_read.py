#!/usr/bin/env python3
"""Ревизия 08.07 вечер (O3-3c + UX-сага): read-only снимок KB_MASTER в /tmp + верх cc_log для сверки фактов (зелёная зона)."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"

c = BridgeClient()
r = c._call("read_doc", id=KB_MASTER_ID)
if not r.get("ok"):
    print("READ MASTER FAIL:", r)
    raise SystemExit(1)
text = r.get("text", "")
snap = "/tmp/KB_MASTER_snapshot_20260708c.md"
with open(snap, "w", encoding="utf-8") as f:
    f.write(text)
print(f"MASTER OK len={len(text)} code points, snapshot={snap}")

r2 = c._call("read_doc", name="cc_log")
if not r2.get("ok"):
    print("READ CCLOG FAIL:", r2)
    raise SystemExit(1)
cclog = r2.get("text", "")
with open("/tmp/cclog_snapshot_20260708c.md", "w", encoding="utf-8") as f:
    f.write(cclog)
print(f"CCLOG OK len={len(cclog)}; верх 6000 симв ниже:")
print(cclog[:6000])
