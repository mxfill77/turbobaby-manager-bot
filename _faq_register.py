"""Регистрация ключа turbobaby_faq -> KB_faq id в BRAIN_MANIFEST + проверка read_doc."""
from dotenv import load_dotenv
load_dotenv()
import json
from bridge_client import BridgeClient

TARGET_ID = "1tv8Y-K3gLyT9Y0mXyYXZLf2c2rEzPMLHPzvg4lGqs98"

c = BridgeClient()
r = c.register_brain_doc(name="turbobaby_faq", id=TARGET_ID)
print("REGISTER:", json.dumps(r, ensure_ascii=False)[:500])
if not r.get("ok"):
    raise SystemExit(1)

d = c._call("read_doc", name="turbobaby_faq")
print("READ ok:", d.get("ok"), "| id:", d.get("id"), "| name:", d.get("name"))
content = d.get("content") or d.get("text") or ""
print("LEN:", len(content))
print("HEAD:", content[:300].replace("\n", " | "))
