#!/usr/bin/env python3
"""Read-only проба очереди: полные result задач 137 и 141 (разбор красных гейтов 17:56/20:05)."""
import os, sys
REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
from bridge_client import BridgeClient

bc = BridgeClient(timeout=90)
r = bc.get_pending_multi(["done", "failed"], lane="all")
if not r.get("ok"):
    print("ERR:", r.get("error"))
    sys.exit(1)
for it in r.get("items", []):
    tid = int(it.get("id") or 0)
    if tid in (137, 141):
        print(f"===== id={tid} status={it.get('status')} updated={it.get('updated')}")
        print("TEXT:", str(it.get("task_text"))[:400])
        print("RESULT:", str(it.get("result"))[:2500])
        print()
