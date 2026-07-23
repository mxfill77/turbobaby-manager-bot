"""Read-only: показать очередь Bridge по всем статусам, выделить set_caps/K3-задачи."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
STATUSES = ["new", "in_progress", "needs_approval", "approved", "done", "failed"]
for lane in ("all", None):
    r = c.get_pending_multi(STATUSES, lane=lane)
    print(f"=== lane={lane} ok={r.get('ok')} err={r.get('error')} n={len(r.get('items',[]))}")
    if not r.get("ok"):
        continue
    for it in r.get("items", []):
        if not isinstance(it, dict):
            continue
        tid = it.get("id")
        st = it.get("status")
        frm = it.get("from")
        txt = (it.get("task_text") or "")[:80]
        res = (it.get("result") or "")[:80]
        blob = (str(it.get("task_text","")) + " " + str(it.get("result",""))).lower()
        flag = ""
        if "set_caps" in blob or "toggle_cap" in blob or "k3" in blob or "кап" in blob:
            flag = "  <<< CAPS"
        print(f"  id={tid} st={st} from={frm} | task={txt!r} | res={res!r}{flag}")
    if lane == "all":
        break
