"""Read-only разведка 2: полный текст NOTE #287 (фикс 1403fa2) и все тик-строки ревизора."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

b = BridgeClient()
r = b._call("read_doc", name="cowork_log")
text = r.get("text") or ""
lines = text.splitlines()
for ln in lines:
    if "#287" in ln or "16:05" in ln:
        print("FULL:", ln)
        print("=" * 40)
print("--- тики (строки с 'ревизор:'):")
for ln in lines:
    if "ревизор:" in ln.lower():
        print(repr(ln))
