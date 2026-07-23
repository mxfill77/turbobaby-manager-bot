#!/usr/bin/env python3
"""Read-only разведка для дельта-ревизии 12.07: KB_MASTER + парк (XMAX)."""
import json
from bridge_client import BridgeClient

c = BridgeClient()

r = c._call("read_doc", id="1-bH3b6c_oamqST551iLxn-voSDragdV0rUZkFwgmAqc")
if r.get("ok"):
    text = r.get("text", "")
    with open("/tmp/kb_master_1207.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("KB_MASTER ok, len=", len(text))
else:
    print("KB_MASTER FAIL:", json.dumps(r, ensure_ascii=False)[:300])

f = c.fleet()
if f.get("ok"):
    bikes = f["data"].get("bikes", f["data"])
    with open("/tmp/fleet_1207.json", "w", encoding="utf-8") as fo:
        json.dump(bikes, fo, ensure_ascii=False, indent=1)
    if isinstance(bikes, list):
        xm = [b for b in bikes if "XMAX" in json.dumps(b, ensure_ascii=False).upper()]
        print("fleet ok, bikes=", len(bikes), "; XMAX rows=", len(xm))
        for b in xm:
            print(json.dumps(b, ensure_ascii=False))
    else:
        print("fleet ok, non-list data keys:", list(f["data"].keys()))
else:
    print("fleet FAIL:", json.dumps(f, ensure_ascii=False)[:300])
