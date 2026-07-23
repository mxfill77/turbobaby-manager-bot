"""FACT-CHECK капов — read-only live probes через прод Bridge. Ничего не пишет."""
import json
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

b = BridgeClient()

print("=== 1. PING (версия/deployment) ===")
print(json.dumps(b.ping(), ensure_ascii=False))

print("\n=== 2. quote_price NMAX 30д (живое чтение quoteReadCaps_ от CAPS_ANCHOR) ===")
q = b.quote_price(bike="4255", date_start="08.07.2026", date_end="07.08.2026")
print(json.dumps(q, ensure_ascii=False))

print("\n=== 3. set_caps БЕЗ confirmed — проба, есть ли action на проде (НЕ пишет) ===")
r = b._call("set_caps")  # без confirmed → not_confirmed если новый код; unknown_action если старый прод
print(json.dumps(r, ensure_ascii=False))

print("\n=== 4. toggle_cap БЕЗ confirmed — та же проба ===")
r2 = b._call("toggle_cap")
print(json.dumps(r2, ensure_ascii=False))

print("\n=== 5. help — список action прода ===")
try:
    h = b._call("help")
    txt = json.dumps(h, ensure_ascii=False)
    print("set_caps in help:", "set_caps" in txt, "| toggle_cap in help:", "toggle_cap" in txt)
except Exception as e:
    print("help err:", e)
