#!/usr/bin/env python3
"""Ревизия мозга 07.07: разведка — манифест Brain + снимки ключевых доков в /tmp."""
import json, os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

OUT = "/tmp/revision0707"
os.makedirs(OUT, exist_ok=True)
c = BridgeClient()

# 1. манифест
r = c._call("list_brain")
if not r.get("ok"):
    print("LIST_BRAIN FAIL:", r); sys.exit(1)
files = r.get("files") or r.get("data") or r
with open(f"{OUT}/list_brain.json", "w") as f:
    json.dump(r, f, ensure_ascii=False, indent=1)
print("LIST_BRAIN keys:", list(r.keys()))
if isinstance(files, list):
    print("COUNT:", len(files))
    for it in files:
        print(" -", it)
else:
    print(json.dumps(r, ensure_ascii=False)[:3000])
