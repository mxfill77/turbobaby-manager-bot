#!/usr/bin/env python3
"""Read-only проба очереди: статус задачи 138 (+ соседей 137-141) по всем статусам обеих полос."""
import os, sys
REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
from bridge_client import BridgeClient

bc = BridgeClient(timeout=90)
statuses = ["new", "in_progress", "needs_approval", "approved", "done", "failed"]
r = bc.get_pending_multi(statuses, lane="all")
if not r.get("ok"):
    print("ERR:", r.get("error"))
    sys.exit(1)
for it in r.get("items", []):
    tid = int(it.get("id") or 0)
    if 135 <= tid <= 142:
        print(f"id={tid} status={it.get('status')} lane={it.get('lane')} from={it.get('from')} "
              f"updated={it.get('updated')} text={str(it.get('task_text'))[:80]!r} "
              f"result={str(it.get('result'))[:120]!r}")
