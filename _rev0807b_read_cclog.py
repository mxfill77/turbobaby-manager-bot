#!/usr/bin/env python3
"""Ревизия 08.07: read-only чтение cc_log (name=cc_log) в /tmp для сверки фактов дня (зелёная зона)."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r)
    raise SystemExit(1)
text = r.get("text", "")
with open("/tmp/cc_log_snapshot_20260708b.md", "w", encoding="utf-8") as f:
    f.write(text)
print(f"OK len={len(text)}, snapshot=/tmp/cc_log_snapshot_20260708b.md")
