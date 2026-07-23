from bridge_client import BridgeClient
import os, dotenv
dotenv.load_dotenv()
bc = BridgeClient(os.environ['BRIDGE_URL'], os.environ['BRIDGE_TOKEN'])
targets = {'220','221','222','223','224','225','226','227','228','229','230'}
for st in ('needs_approval', 'failed', 'done', 'new', 'approved', 'in_progress'):
    r = bc.get_pending(st, lane='all')
    items = r if isinstance(r, list) else (r.get('items', []) if isinstance(r, dict) else [])
    for it in items:
        if str(it.get('id')) in targets:
            res = str(it.get('result',''))[:100]
            print(f"id={it.get('id')} status={st} lane={it.get('lane','?')} from={it.get('from','')} result={res}")
print('Queue scan complete')
