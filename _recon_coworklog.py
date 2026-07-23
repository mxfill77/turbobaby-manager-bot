"""Read-only разведка: свежие строки cowork_log через Bridge (формат NOTE ревизора)."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

b = BridgeClient()
r = b._call("read_doc", name="cowork_log")
print("ok:", r.get("ok"), "| error:", r.get("error"))
text = r.get("text") or ""
print("len:", len(text))
lines = text.splitlines()
# все строки со словом «ревизор» (первые 15) + просто первые 25 строк дока
rev = [ln for ln in lines if "ревизор" in ln.lower()]
print("--- строки с 'ревизор' (top15):")
for ln in rev[:15]:
    print(repr(ln[:200]))
print("--- первые 25 строк дока:")
for ln in lines[:25]:
    print(repr(ln[:160]))
