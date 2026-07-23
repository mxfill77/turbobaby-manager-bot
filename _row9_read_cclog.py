#!/usr/bin/env python3
"""Read-only: верх cc_log — ищу вердикт разбора 11.07 09:40 (row9, тайский блок приёмки)."""
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("ERR:", r)
    raise SystemExit(1)
text = r.get("text", "")
print("LEN:", len(text))
print(text[:14000])
