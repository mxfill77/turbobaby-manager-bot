"""Read-only проба прод-Bridge: quote_price NMAX на месяц — есть ли cap-ключи (заявка 33)."""
import json
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
res = bc.quote_price("NMAX", "10.07.2026", "10.08.2026")
if res is None:
    print("RESULT: None (ошибка/таймаут/не-ok)")
else:
    print("keys:", sorted(res.keys()))
    print("cap_price:", res.get("cap_price", "<КЛЮЧА НЕТ — старый Bridge>"))
    print("cap_active:", res.get("cap_active", "<КЛЮЧА НЕТ — старый Bridge>"))
    print("day_price:", res.get("day_price"), "| total:", res.get("total"),
          "| season:", res.get("season"), "| model:", res.get("model"))
