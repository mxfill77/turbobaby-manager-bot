#!/usr/bin/env python3
"""Read cc_log and find the 11.07 09:40 row12 entry (read-only)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("read_doc failed:", r)
    sys.exit(1)
text = r.get("text") or r.get("content") or ""
print(f"len={len(text)}")
# find entries mentioning row12 or 09:40
idx = 0
low = text.lower()
for marker in ["row12", "09:40"]:
    pos = 0
    while True:
        i = low.find(marker, pos)
        if i < 0:
            break
        print(f"\n===== match '{marker}' at {i} =====")
        print(text[max(0, i-200):i+3000])
        pos = i + len(marker)
        break  # first occurrence of each marker enough for now
