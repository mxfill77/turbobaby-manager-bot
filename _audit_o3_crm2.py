import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

# Check NMAX 155 GREY 5960 booking status specifically
result = bc.closing_get(bike='NMAX 155CC GREY PHUKET 5960')
print('NMAX 155 GREY 5960 closing_get:', result)
print()

result2 = bc.closing_get(bike='NINJA 400')
print('NINJA 400 closing_get:', result2)
print()

# Try history or completed clients
result3 = bc.clients(filter='all')
print('All clients count:', result3.get('ok'), len(result3.get('data', {}).get('clients', result3.get('data', [])) if isinstance(result3.get('data'), dict) else result3.get('data', [])))
data3 = result3.get('data', {})
if isinstance(data3, list):
    rows3 = data3
elif isinstance(data3, dict):
    rows3 = data3.get('clients', data3.get('rows', data3.get('data', [])))
else:
    rows3 = []
print('All rows:', len(rows3))
# Filter for bikes we care about
bikes_of_interest = ['5960', '4724', '6334']
for r in rows3:
    if isinstance(r, dict):
        name = str(r.get('bike',''))
        for plate in bikes_of_interest:
            if plate in name:
                print(f'  {name} | {r.get("name","?")} | status={r.get("status","?")} | start={r.get("date_start","?")} | end={r.get("date_end","?")} | row={r.get("row",r.get("id","?"))}')
