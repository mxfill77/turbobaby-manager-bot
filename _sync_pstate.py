"""Авто-синк base-дока project_state в Brain (git = истина, Drive = зеркало) + сверка длины."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
import bridge_client

with open("/root/turbobaby-manager-bot/docs/project_state.md", encoding="utf-8") as f:
    text = f.read()
b = bridge_client.BridgeClient()
r = b.write_doc(text, name="project_state")
print("write:", r.get("ok"), r.get("error"))
rr = b._call("read_doc", name="project_state")
drive = rr.get("text") or ""
print("git codepoints:", len(text), "| drive codepoints:", len(drive), "| delta:", len(drive) - len(text))
