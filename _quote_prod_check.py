# read-only проверка прод-Bridge: quote_price + склейка статусов get_pending (CSV)
import json
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

bc = BridgeClient()

r = bc._call("ping")
print("PING:", json.dumps(r, ensure_ascii=False))

q = bc._call("quote_price", bike="4957", date_start="08.07.2026", date_end="15.07.2026")
print("QUOTE:", json.dumps(q, ensure_ascii=False))

p = bc._call("get_pending", status="done,failed")
print("PENDING_CSV: ok=%s statuses=%s items=%s" % (
    p.get("ok"), p.get("statuses"), len(p.get("items", []))))
