"""Read-only: голова cc_log + пульс — ищу статус redeploy Bridge (полоса lane)."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
print("cc_log ok:", r.get("ok"), "len:", len(r.get("text") or ""))
print((r.get("text") or "")[:4000])
print("=" * 40, "PULSE", "=" * 40)
p = c._call("read_doc", name="pulse")
print((p.get("text") or "")[:600])
