"""O3-3c часть В recon: какие поля отдаёт прод-Bridge clients (есть ли raw депозит)."""
import json
from bridge_client import BridgeClient

b = BridgeClient()
r = b.clients(filter="all")
rows = r.get("data", {}).get("clients", [])
print("rows:", len(rows))
if rows:
    print("keys:", sorted(rows[-1].keys()))
    for c in rows[-6:]:
        print(c.get("row"), repr(c.get("status")), repr(c.get("bike"))[:30],
              "deposit=", repr(c.get("deposit")), "deposit_raw=", repr(c.get("deposit_raw")))
