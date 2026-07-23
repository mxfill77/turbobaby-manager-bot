"""Read-only проверка: долетел ли деплой Bridge (quote_price + statuses) до прода."""
import os, sys, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
import requests

URL = os.getenv("BRIDGE_URL")
TOK = os.getenv("BRIDGE_TOKEN")

def call(action, **params):
    q = {"token": TOK, "action": action, **params}
    try:
        r = requests.get(URL, params=q, timeout=45, allow_redirects=True)
        return r.status_code, r.text[:600]
    except Exception as e:
        return "EXC", str(e)[:300]

print("=== ping ===")
print(call("ping"))
print("=== quote_price bike=4957 08.07-15.07 ===")
print(call("quote_price", bike="4957", date_start="08.07.2026", date_end="15.07.2026"))
print("=== get_pending (statuses?) ===")
code, body = call("get_pending")
print(code)
try:
    d = json.loads(body) if body.strip().startswith("{") else None
except Exception:
    d = None
if d is not None:
    print("keys:", list(d.keys()))
    print("has statuses:", "statuses" in d)
else:
    print(body[:400])
