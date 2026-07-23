#!/usr/bin/env python3
"""Ревизия 08.07: read-only снимок KB_ROADMAP_MASTER (name=roadmap_master) в /tmp (зелёная зона)."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="roadmap_master")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text", "")
with open("/tmp/KB_ROADMAP_snapshot_20260708b.md", "w", encoding="utf-8") as f:
    f.write(text)
print(f"OK len={len(text)}, snapshot=/tmp/KB_ROADMAP_snapshot_20260708b.md")
