import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
r = bc._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL:", r.get("error"))
    sys.exit(1)
text = r.get("text") or r.get("content") or ""
print("LEN:", len(text))
# найти упоминания 156
import re
idx = 0
hits = []
for m in re.finditer(r"156", text):
    hits.append(m.start())
print("HITS:", len(hits))
for h in hits[:12]:
    print("=" * 60)
    print(text[max(0, h - 900):h + 900])
