"""Read-only: живость манифестных ключей roadmap_master/payments_plan через Bridge read_doc."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
for key in ("roadmap_master", "payments_plan"):
    try:
        r = c._call("read_doc", name=key)
        t = r.get("text", "")
        print(f"{key}: ok={r.get('ok')} len={len(t)} head={t[:120]!r}")
    except Exception as e:
        print(f"{key}: EXC {e}")
