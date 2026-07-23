from bridge_client import BridgeClient
import os, dotenv
dotenv.load_dotenv()
bc = BridgeClient(os.environ['BRIDGE_URL'], os.environ['BRIDGE_TOKEN'])
targets = {'224','225','226','227'}
for st in ('needs_approval', 'failed', 'done', 'new', 'approved', 'in_progress'):
    r = bc.get_pending(st, lane='all')
    items = r if isinstance(r, list) else (r.get('items', []) if isinstance(r, dict) else [])
    for it in items:
        if str(it.get('id')) in targets:
            task = str(it.get('task_text',''))[:200]
            res = str(it.get('result',''))[:200]
            upd = str(it.get('updated',''))
            cre = str(it.get('created',''))
            print(f"--- id={it.get('id')} status={st} from={it.get('from','')} lane={it.get('lane','?')}")
            print(f"    created={cre} updated={upd}")
            print(f"    task_text={task}")
            print(f"    result={res}")
print('Complete')
