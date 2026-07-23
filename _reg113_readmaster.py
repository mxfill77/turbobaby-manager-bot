"""Read-only: вытащить из KB_MASTER (name=index) строки вокруг f926733."""
import os
from dotenv import load_dotenv

load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

r = BridgeClient(timeout=45)._call("read_doc", name="index")
txt = (r.get("text", "") or "") if r.get("ok") else ""
lines = txt.split("\n")
for i, ln in enumerate(lines):
    if "f926733" in ln:
        for j in range(max(0, i - 2), min(len(lines), i + 3)):
            mark = ">>" if j == i else "  "
            print(f"{mark} {j}: {lines[j]}")
        print("---")
