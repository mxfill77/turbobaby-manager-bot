#!/usr/bin/env python3
"""Ревизия 07.07: снимок cc_log в /tmp/revision0707."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

c = BridgeClient(timeout=120)
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("FAIL:", r); sys.exit(1)
text = r.get("text") or r.get("content") or ""
with open("/tmp/revision0707/cc_log.snap.md", "w") as f:
    f.write(text)
print("cc_log ok,", len(text), "chars")
