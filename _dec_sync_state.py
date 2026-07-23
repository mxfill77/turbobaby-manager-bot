"""Авто-синк docs/project_state.md → Brain KB_project_state (write_doc name=project_state).
Истина = git; сверка длины в code points. Зона 🟢."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

with open("/root/turbobaby-manager-bot/docs/project_state.md", encoding="utf-8") as f:
    src = f.read()
c = BridgeClient()
w = c.write_doc(text=src, name="project_state")
print("write:", w.get("ok"))
r = c._call("read_doc", name="project_state")
print("git len:", len(src), "| drive len:", len(r.get("text", "")), "| delta:", len(src) - len(r.get("text", "")))
