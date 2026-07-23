import json
from bridge_client import BridgeClient

bc = BridgeClient()
p = bc.ping()
print("ping:", json.dumps(p, ensure_ascii=False)[:200])
q_new = bc.get_pending(status="new")
q_ip = bc.get_pending(status="in_progress")
print("queue new:", len(q_new.get("tasks", [])), "in_progress:", len(q_ip.get("tasks", [])))
