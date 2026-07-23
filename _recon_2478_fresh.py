import sys, json, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

client = BridgeClient(os.environ['BRIDGE_URL'])

print("=== 1. FLEET (Лист1) ===")
r = client.fleet()
bikes = r.get('data', {}).get('bikes', [])
for b in bikes:
    if '2478' in str(b):
        print(json.dumps(b, ensure_ascii=False, indent=2))
        break
else:
    print("NOT FOUND in fleet")

print("\n=== 2. SERVICE_PENDING_LIST (Bot Data) ===")
r2 = client.service_pending_list(chat_id=-1002751134848)
print(json.dumps(r2, ensure_ascii=False, indent=2))

print("\n=== 3. MEMORY.DB: topic_bike for 2478 ===")
import sqlite3
conn = sqlite3.connect('/root/turbobaby-manager-bot/memory.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cur.fetchall()]
print(f"Tables: {tables}")
for t in tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = [c[1] for c in cur.fetchall()]
    if any(k in cols for k in ('bike', 'number', 'oil', 'odo', 'km')):
        cur.execute(f"SELECT * FROM {t}")
        rows = cur.fetchall()
        print(f"\nTable {t} cols={cols}:")
        for row in rows:
            if any('2478' in str(v) for v in row):
                print(f"  MATCH: {row}")
conn.close()
