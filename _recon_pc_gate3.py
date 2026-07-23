import os, json
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient(timeout=60)
for st in ("done", "failed"):
    r = c.get_pending(status=st, lane="all")
    items = r.get("items") or []
    print(f"== status={st} count={len(items)}")
    for t in items:
        row = {k: str(v)[:90] for k, v in t.items()}
        s = json.dumps(row, ensure_ascii=False)
        if "2026-07-11" in s or "allowlist" in s or "1/77" in s:
            print(s[:700])
