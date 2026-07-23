"""Синк docs/knowledge_base.md → Brain KB_knowledge_base (write_doc name=knowledge_base).
Истина = git; сверка длины code points. Зелёная зона (авто-синк по факту изменения base-дока)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

with open("/root/turbobaby-manager-bot/docs/knowledge_base.md", encoding="utf-8") as f:
    text = f.read()

c = BridgeClient()
w = c.write_doc(text=text, name="knowledge_base")
print("write_doc knowledge_base:", w.get("ok"), "| git len:", len(text))
if not w.get("ok"):
    print("FAIL:", w)
    raise SystemExit(1)

r = c._call("read_doc", name="knowledge_base")
drive_len = len(r.get("text", "")) if r.get("ok") else -1
print("drive len:", drive_len, "| delta:", drive_len - len(text))
