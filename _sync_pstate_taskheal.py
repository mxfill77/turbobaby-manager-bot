"""Авто-синк docs/project_state.md → Brain KB_project_state (write_doc name=project_state).
Истина = git-файл; сверка по длине code points. Зона 🟢 (зеркало git)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

path = "/root/turbobaby-manager-bot/docs/project_state.md"
text = open(path, encoding="utf-8").read()
bc = BridgeClient()
r = bc.write_doc(text, name="project_state")
print("write_doc ok:", r.get("ok"), "| err:", r.get("error"))
rd = bc.read_doc(name="project_state") if hasattr(bc, "read_doc") else {}
drive_len = len(rd.get("text") or rd.get("content") or "")
print(f"git codepoints={len(text)} drive codepoints={drive_len} delta={drive_len - len(text)}")
