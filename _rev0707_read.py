#!/usr/bin/env python3
"""Ревизия 07.07: снимки KB_MASTER (index), pulse, roadmap_master в /tmp/revision0707."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

OUT = "/tmp/revision0707"
os.makedirs(OUT, exist_ok=True)
c = BridgeClient(timeout=120)
for key in ("index", "pulse", "roadmap_master"):
    r = c._call("read_doc", name=key)
    if not r.get("ok"):
        print(f"{key}: FAIL {r}")
        continue
    text = r.get("text") or r.get("content") or ""
    with open(f"{OUT}/{key}.snap.md", "w") as f:
        f.write(text)
    print(f"{key}: ok, {len(text)} chars -> {OUT}/{key}.snap.md")
