#!/usr/bin/env python3
"""Read-only: статусы всех строк аудит-листа (как закрывали раньше)."""
from bridge_client import BridgeClient

b = BridgeClient()
r = b.audit_list()
if not r.get("ok"):
    print("ERR:", r.get("error"))
    raise SystemExit(1)
for it in r.get("items") or []:
    print(it.get("_row"), "|", it.get("verdict"), "|", repr(it.get("status")), "|", (it.get("detail") or "")[:60])
