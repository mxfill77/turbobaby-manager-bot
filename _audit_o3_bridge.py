import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

# Read current active clients (В аренде)
result = bc.clients(filter='active')
print('CRM active clients ok:', result.get('ok'))
clients = result.get('data', {})
if isinstance(clients, list):
    rows = clients
elif isinstance(clients, dict):
    rows = clients.get('clients', clients.get('rows', clients.get('data', [])))
else:
    rows = []
print(f'Active rentals count: {len(rows)}')
for r in rows[:10]:
    if isinstance(r, dict):
        print(f"  {r.get('bike','?')} | {r.get('name','?')} | status={r.get('status','?')} | date_start={r.get('date_start','?')} | date_due={r.get('date_due','?')}")

print()
# Check fleet status
fleet_r = bc.fleet()
print('Fleet ok:', fleet_r.get('ok'))
bikes = fleet_r.get('data', {}).get('bikes', [])
print(f'Fleet bikes: {len(bikes)}')
renting = [b for b in bikes if 'аренде' in str(b.get('status',''))]
print(f'В аренде: {len(renting)}')
for b in renting:
    print(f"  {b.get('name','')} | client={b.get('client','')} | due={b.get('date_due','')}")

# Check anomalies
anom = bc.anomalies()
print('Anomalies ok:', anom.get('ok'))
anom_data = anom.get('data', {})
print('Anomalies:', str(anom_data)[:500])
