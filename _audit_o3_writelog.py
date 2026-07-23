import sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from bridge_client import BridgeClient
from dotenv import load_dotenv
load_dotenv()

bc = BridgeClient()

# Read write log - last 50 entries
result = bc.read_write_log(limit=50)
print('Write log ok:', result.get('ok'))
data = result.get('data', {})
rows = data.get('rows', data.get('log', data.get('entries', [])))
print(f'Log rows: {len(rows)}')
for r in rows:
    print(r)
