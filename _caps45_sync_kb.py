"""Синк docs/knowledge_base.md → Brain KB_knowledge_base (write_doc name=knowledge_base).
Истина = git; Drive = зеркало; сверка по длине code points. Зелёная зона."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

src = open("/root/turbobaby-manager-bot/docs/knowledge_base.md", encoding="utf-8").read()
c = BridgeClient()
w = c.write_doc(text=src, name="knowledge_base")
print("write:", w.get("ok"), w.get("error", ""))
if not w.get("ok"):
    raise SystemExit(1)
r = c._call("read_doc", name="knowledge_base")
back = r.get("text", "")
print("git codepoints:", len(src), "| drive codepoints:", len(back), "| delta:", len(back) - len(src))
