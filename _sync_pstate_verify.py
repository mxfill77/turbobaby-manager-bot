"""Сверка синка project_state: длина code points git-файла vs Drive (read_doc через _call)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

text = open("/root/turbobaby-manager-bot/docs/project_state.md", encoding="utf-8").read()
bc = BridgeClient()
r = bc._call("read_doc", name="project_state")
drive = r.get("text") or r.get("content") or ""
print("read ok:", r.get("ok"), f"| git={len(text)} drive={len(drive)} delta={len(drive) - len(text)}")
