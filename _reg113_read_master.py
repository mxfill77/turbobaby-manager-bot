#!/usr/bin/env python3
"""Разведка: прочитать KB_MASTER (name=index), показать строки с f926733 / pc_orchestrator.
Снимок целиком в /tmp/kb_master_snapshot_113.txt (бэкап ДО правки). READ-ONLY."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

c = BridgeClient(timeout=45)
r = c._call("read_doc", name="index")
if not r.get("ok"):
    print("READ FAIL:", r)
    sys.exit(1)
txt = r.get("text", "") or ""
with open("/tmp/kb_master_snapshot_113.txt", "w", encoding="utf-8") as f:
    f.write(txt)
print(f"len={len(txt)} code points, snapshot -> /tmp/kb_master_snapshot_113.txt")
lines = txt.split("\n")
for i, ln in enumerate(lines, 1):
    low = ln.lower()
    if "f926733" in low or "pc_orchestrator" in low or "pc-orchestrator" in low:
        print(f"{i}: {ln}")
