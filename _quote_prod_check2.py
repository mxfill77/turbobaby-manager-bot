# read-only проверка прод-Bridge (задача 328): quote_price PCX 160 на ближайшее
# свободное окно + склейка статусов get_pending (CSV). Ничего не пишет.
import json
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

bc = BridgeClient()

r = bc._call("ping")
print("PING:", json.dumps(r, ensure_ascii=False))

# ближайшее свободное 7-дневное окно: старт с завтра, сдвиг при conflicts>0 (макс 14 сдвигов)
start = date.today() + timedelta(days=1)
found = None
for shift in range(15):
    ds = start + timedelta(days=shift)
    de = ds + timedelta(days=7)
    q = bc._call("quote_price", bike="4957",
                 date_start=ds.strftime("%d.%m.%Y"), date_end=de.strftime("%d.%m.%Y"))
    if not q.get("ok"):
        print("QUOTE_FAIL:", json.dumps(q, ensure_ascii=False))
        break
    if q.get("available"):
        found = (ds, de, q)
        break
    print("BUSY %s-%s conflicts=%s" % (ds, de, q.get("conflicts")))

if found:
    ds, de, q = found
    print("QUOTE OK %s → %s:" % (ds.strftime("%d.%m.%Y"), de.strftime("%d.%m.%Y")),
          json.dumps(q, ensure_ascii=False))

p = bc._call("get_pending", status="done,failed")
print("PENDING_CSV: ok=%s statuses=%s items=%s" % (
    p.get("ok"), p.get("statuses"), len(p.get("items", []))))
