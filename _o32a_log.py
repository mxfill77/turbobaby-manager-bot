#!/usr/bin/env python3
"""Журнальная запись O3-2a в cc_log (+пульс той же операцией), тег (o4-headless).
Та же дисциплина, что cclog.py: под врезкой, пишем только если read ok."""
import sys
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
from cclog import _insert_under_vrezka, TYPES


def main(argv) -> int:
    pulse = None
    if "--pulse" in argv:
        p = argv.index("--pulse")
        pulse = argv[p + 1] if p + 1 < len(argv) else ""
        argv = argv[:p] + argv[p + 2:]
    kind = "DONE"
    if argv and argv[0].upper() in TYPES:
        kind = argv[0].upper()
        argv = argv[1:]
    text = " ".join(argv).strip()
    if not text:
        return 2
    c = BridgeClient()
    r = c._call("read_doc", name="cc_log")
    if not r.get("ok"):
        print("READ FAIL — не пишу:", r, file=sys.stderr)
        return 1
    old = r.get("text", "")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    line = f"{kind} {ts} UTC (o4-headless): {text}"
    new = _insert_under_vrezka(old, line)
    w = c.write_doc(text=new, name="cc_log")
    if not w.get("ok"):
        print("WRITE FAIL:", w, file=sys.stderr)
        return 1
    print(f"OK cc_log ← {kind} {ts} (old={len(old)} → new={len(new)})")
    if pulse is not None:
        wp = c.write_doc(text=pulse, name="pulse")
        print("pulse:", "OK" if wp.get("ok") else f"FAIL {wp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
