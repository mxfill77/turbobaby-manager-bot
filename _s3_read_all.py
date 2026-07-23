"""Read-only: KB_RULES + KB_INFRA + list_brain для сверки с KB_MASTER (шаг 3/7 родитель 33)."""
import json
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

for key in ("rules", "infra"):
    r = c._call("read_doc", name=key)
    print(f"===== {key} ok={r.get('ok')} len={len(r.get('text',''))} =====")
    print(r.get("text", ""))
    print()

lb = c._call("list_brain")
print("===== list_brain ok=", lb.get("ok"), "=====")
print(json.dumps(lb, ensure_ascii=False, indent=1))
