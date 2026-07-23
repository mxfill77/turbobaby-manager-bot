#!/usr/bin/env python3
"""Фикс по сигналу registry_check: c674b8b — коммит ПК-репо (pc_orchestrator), помечаем маркером
«ПК-репо» на КАЖДОЙ строке с хешем (FOREIGN_REPO_MARK глушит резолв в manager-bot, фикс класса 9a695fb).
Затем write_doc + post-write verify."""
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient

KB_MASTER_ID = "1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc"

with open("/tmp/KB_MASTER_new_20260707_evening.md", encoding="utf-8") as f:
    text = f.read()

edits = [
    ("(1) pc-самопочинка (c674b8b) — думатель",
     "(1) pc-самопочинка (c674b8b, ПК-репо) — думатель"),
    ("(3 куска c674b8b+fa3680d+a2b8945 — оба театра под одним",
     "(3 куска: c674b8b ПК-репо + fa3680d + a2b8945 — оба театра под одним"),
    ("ПК-ТЕАТР ЗАВЕРШЁН (c674b8b pc-самопочинка + fa3680d",
     "ПК-ТЕАТР ЗАВЕРШЁН (c674b8b ПК-репо pc-самопочинка + fa3680d"),
]
for old, new in edits:
    n = text.count(old)
    if n != 1:
        print(f"ABORT: якорь встречается {n} раз (нужно 1): {old[:70]!r}")
        raise SystemExit(1)
    text = text.replace(old, new)

with open("/tmp/KB_MASTER_new_20260707_evening.md", "w", encoding="utf-8") as f:
    f.write(text)
print(f"marker edits OK: 3/3, new len={len(text)}")

c = BridgeClient()
w = c.write_doc(text=text, name=None, id=KB_MASTER_ID)
if not w.get("ok"):
    print("WRITE FAIL:", w)
    raise SystemExit(1)
r = c._call("read_doc", id=KB_MASTER_ID)
if not r.get("ok"):
    print("VERIFY READ FAIL:", r)
    raise SystemExit(1)
back = r.get("text", "")
ok = len(back) == len(text) and "c674b8b, ПК-репо" in back and "c674b8b ПК-репо" in back
print(f"verify: prod len={len(back)} vs local={len(text)} | markers ok={ok}")
if not ok:
    print("POST-WRITE VERIFY FAILED")
    raise SystemExit(1)
print("POST-WRITE VERIFY OK")
