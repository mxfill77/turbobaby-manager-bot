"""Read-only: манифест Brain — под каким ключом KB_faq, есть ли turbobaby_faq."""
from dotenv import load_dotenv
load_dotenv()
import json
from bridge_client import BridgeClient

TARGET_ID = "1tv8Y-K3gLyT9Y0mXyYXZLf2c2rEzPMLHPzvg4lGqs98"

c = BridgeClient()
m = c._call("list_brain")
if not m.get("ok"):
    print("LIST_BRAIN FAIL:", json.dumps(m, ensure_ascii=False)[:500])
    raise SystemExit(1)

docs = m.get("docs") or m.get("data") or m.get("manifest") or m
print("RAW KEYS:", list(m.keys()))
items = None
for k in ("docs", "data", "manifest", "files", "items"):
    if isinstance(m.get(k), (list, dict)):
        items = m[k]
        break
print(json.dumps(items, ensure_ascii=False)[:3000])
print("---")
found_key = None
has_turbobaby_faq = False
if isinstance(items, dict):
    for name, meta in items.items():
        mid = meta if isinstance(meta, str) else (meta.get("id") if isinstance(meta, dict) else None)
        if mid == TARGET_ID:
            found_key = name
        if name == "turbobaby_faq":
            has_turbobaby_faq = True
            print("turbobaby_faq ->", json.dumps(meta, ensure_ascii=False))
elif isinstance(items, list):
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("id") == TARGET_ID:
            found_key = it.get("name") or it.get("key")
        if (it.get("name") or it.get("key")) == "turbobaby_faq":
            has_turbobaby_faq = True
            print("turbobaby_faq ->", json.dumps(it, ensure_ascii=False))
print("KB_faq id registered under key:", found_key)
print("has turbobaby_faq key:", has_turbobaby_faq)
