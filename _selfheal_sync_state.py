#!/usr/bin/env python3
"""Синк base-дока project_state.md → Brain (KB_project_state) после правки (DoD авто-синк, 🟢).
Сверка по длине code points (drive == git)."""
import os, sys
REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))
from bridge_client import BridgeClient

bc = BridgeClient(timeout=90)
src = open(os.path.join(REPO, "docs", "project_state.md"), encoding="utf-8").read()
if os.environ.get("SKIP_WRITE") != "1":
    r = bc.write_doc(src, name="project_state")
    print("write ok:", r.get("ok"), "| err:", r.get("error"))
    if not r.get("ok"):
        sys.exit(1)
rd = bc._call("read_doc", name="project_state")
body = (rd.get("content") or rd.get("text") or "") if isinstance(rd, dict) else ""
print("read ok:", rd.get("ok") if isinstance(rd, dict) else "?",
      "| git len:", len(src), "| drive len:", len(body), "| delta:", len(body) - len(src))
sys.exit(0)
