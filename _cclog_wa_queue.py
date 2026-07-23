#!/usr/bin/env python3
"""One-shot: write wa_queue.db check result to cc_log + pulse."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from cclog import _make_entry, _insert_under_vrezka, _ensure_pulse_hhmm
from bridge_client import BridgeClient

ENTRY_TEXT = (
    "wa_queue.db проверена — таблица wa_inbox, 0 строк (очередь пуста); "
    "wa-webhook active с 15.07 18:40 UTC, работает 1д5ч."
)
PULSE_TEXT = (
    "2026-07-17 UTC | \U0001f7e2 | wa_queue.db: пусто (0 строк), wa-webhook active "
    "| ничего не жду | детали→cc_log запись «wa_queue.db проверена»"
)

c = BridgeClient()

# 1. Read cc_log
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r, file=sys.stderr)
    sys.exit(1)

old = r.get("text", "")
line = _make_entry("DONE", ENTRY_TEXT)
new_text = _insert_under_vrezka(old, line)

# 2. Write cc_log
w = c.write_doc(text=new_text, name="cc_log")
if not w.get("ok"):
    print("WRITE cc_log FAIL:", w, file=sys.stderr)
    sys.exit(1)
print(f"cc_log OK: {line}")

# 3. Write pulse
pulse = _ensure_pulse_hhmm(PULSE_TEXT)
wp = c.write_doc(text=pulse, name="pulse")
if not wp.get("ok"):
    print("WRITE pulse FAIL:", wp, file=sys.stderr)
    sys.exit(1)
print(f"pulse OK: {pulse}")
print("Done.")
