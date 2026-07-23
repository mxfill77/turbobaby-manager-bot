import os
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient
b = BridgeClient()

for st in ("done", "in_progress", "new", "needs_approval", "approved", "failed"):
    try:
        r = b.get_pending(st, lane="all")
    except TypeError:
        r = b.get_pending(st)
    if not r.get("ok"):
        print(st, "ERR", r.get("error"))
        continue
    for it in r.get("items", []):
        tid = str(it.get("id"))
        txt = str(it.get("task_text") or "")
        if tid == "185" or "родитель 185" in txt:
            print("=" * 60)
            print("id", tid, "| st", st, "| from", it.get("from"), "| lane", it.get("lane"))
            print("TASK:", txt[:600])
            print("RESULT:", str(it.get("result") or "")[:1500])
