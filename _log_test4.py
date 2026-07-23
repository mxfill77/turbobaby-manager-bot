#!/usr/bin/env python3
"""Write DONE entry to cc_log and update pulse for test 4."""
import os
import sys

os.environ["BRIDGE_ALLOW_NETWORK"] = "1"

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.chdir("/root/turbobaby-manager-bot")

from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")

from bridge_client import BridgeClient
from cclog import _make_entry, _insert_under_vrezka, _ensure_pulse_hhmm

DONE_TEXT = "тест 4 — задача выполнена, система работает штатно"
PULSE_TEXT = "2026-07-17 | \U0001f7e2 | тест 4 выполнен | ничего не жду | детали→cc_log"

c = BridgeClient()

# 1. Read cc_log
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r, file=sys.stderr)
    sys.exit(1)

old = r.get("text", "")
print(f"Read cc_log OK, length={len(old)}")

# 2. Build entry (relay path: "DONE …" prefix triggers headless-via-Termux label)
line = _make_entry("DONE", "DONE 2026-07-17 UTC (headless): " + DONE_TEXT)
print(f"Entry: {line}")

# 3. Insert under header vrezka
new = _insert_under_vrezka(old, line)

# 4. Write cc_log back
w = c.write_doc(text=new, name="cc_log")
if not w.get("ok"):
    print("WRITE FAIL cc_log:", w, file=sys.stderr)
    sys.exit(1)
print(f"cc_log written OK (old={len(old)} -> new={len(new)})")

# 5. Write pulse
pulse = _ensure_pulse_hhmm(PULSE_TEXT)
wp = c.write_doc(text=pulse, name="pulse")
if not wp.get("ok"):
    print("WRITE FAIL pulse:", wp, file=sys.stderr)
    sys.exit(1)
print(f"pulse written OK: {pulse}")
