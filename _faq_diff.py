"""Read-only: снять KB_faq в /tmp и сравнить заголовки секций с docs/turbobaby_faq_v1.md."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
d = c._call("read_doc", name="turbobaby_faq")
kb = d.get("content") or d.get("text") or ""
with open("/tmp/kb_faq_snapshot.md", "w") as f:
    f.write(kb)
vps = open("/root/turbobaby-manager-bot/docs/turbobaby_faq_v1.md").read()

def heads(t):
    return [l for l in t.splitlines() if l.startswith("#")]

kb_h, vps_h = heads(kb), heads(vps)
print("KB len:", len(kb), "| VPS len:", len(vps))
print("--- KB headings ---")
for h in kb_h: print(h)
print("--- VPS headings ---")
for h in vps_h: print(h)
print("--- VPS headings NOT in KB ---")
for h in vps_h:
    if h not in kb_h: print(h)
print("--- KB headings NOT in VPS ---")
for h in kb_h:
    if h not in vps_h: print(h)
