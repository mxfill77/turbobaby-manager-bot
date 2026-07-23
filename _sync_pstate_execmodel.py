"""Синк docs/project_state.md → Brain KB_project_state (write_doc name=project_state).
Зелёная зона: зеркало git, откат = ре-синк из git."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

SRC = "/root/turbobaby-manager-bot/docs/project_state.md"
with open(SRC, encoding="utf-8") as f:
    text = f.read()

bc = BridgeClient(timeout=90)
r = bc.write_doc(text, name="project_state")
print("write_doc ok:", (r or {}).get("ok"), "| chars:", (r or {}).get("chars"))

chk = bc._call("read_doc", name="project_state")
got = len((chk or {}).get("text") or "")
exp = len(text)
print(f"сверка code points: git={exp} drive={got} delta={got - exp}")
sys.exit(0 if got == exp else 1)
