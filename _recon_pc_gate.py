import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
from bridge_client import BridgeClient
c = BridgeClient(timeout=60)
for lane in ("pc", None):
    for st in ("done", "failed", "in_progress", "new"):
        r = c.get_pending(status=st, lane=lane)
        tasks = r.get("tasks") or r.get("data") or []
        for t in tasks:
            txt = str(t.get("task") or t.get("task_text") or "")[:100]
            res = str(t.get("result") or "")
            mark = ""
            if "test_settings_allowlist" in res or "1/77" in res or "красн" in res.lower():
                mark = "  <== GATE-RED"
            upd = t.get("updated") or t.get("created") or ""
            if "2026-07-11" in str(upd) or mark:
                print(f"lane={lane} st={st} id={t.get('id')} upd={upd} from={t.get('from')}")
                print(f"   task: {txt}")
                print(f"   result: {res[:400]}{mark}")
                print()
