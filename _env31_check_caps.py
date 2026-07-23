"""Конверт заявки 31: read-only проверка живого Bridge — вернулись ли cap_price/cap_active.
Находим конкретный NMAX в парке (find_bike), затем quote_price на месяц. Только чтение."""
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient

bc = BridgeClient()
fb = bc.find_bike("NMAX")
name = fb.get("name")
if not name:
    print("не удалось выбрать конкретный NMAX; сырой ответ ключи:", list(fb.keys()))
    sys.exit(0)
print("байк для проверки:", name)

q = bc.quote_price(name, "2026-07-06", "2026-08-05")
if q is None:
    print("BRIDGE: quote_price вернул None (ошибка/таймаут/старый Bridge)")
else:
    print("cap_price =", q.get("cap_price"))
    print("cap_active =", q.get("cap_active"))
    print("has_cap_keys =", "cap_price" in q)
    print("day_price =", q.get("day_price"), "| total =", q.get("total"))
