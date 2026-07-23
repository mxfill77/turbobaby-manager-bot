#!/usr/bin/env python3
"""Мини-ревизия 08.07: read-only снимок KB_MASTER в /tmp перед правкой (зона зелёная)."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"

c = BridgeClient()
r = c._call("read_doc", id=KB_MASTER_ID)
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text", "")
snap = "/tmp/KB_MASTER_snapshot_20260708.md"
with open(snap, "w", encoding="utf-8") as f:
    f.write(text)
print(f"OK len={len(text)} code points, snapshot={snap}")
