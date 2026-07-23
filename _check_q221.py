from bridge_client import BridgeClient
import os, dotenv
dotenv.load_dotenv()
bc = BridgeClient(os.environ['BRIDGE_URL'], os.environ['BRIDGE_TOKEN'])
targets = {str(i) for i in range(210, 230)}
found = {}
for st in ('needs_approval', 'failed', 'done', 'new', 'approved', 'in_progress'):
    r = bc.get_pending(st, lane='all')
    items = r if isinstance(r, list) else (r.get('items', []) if isinstance(r, dict) else [])
    for it in items:
        tid = str(it.get('id'))
        if tid in targets and tid not in found:
            found[tid] = (st, it)

for tid in sorted(found.keys(), key=lambda x: int(x)):
    st, it = found[tid]
    task = str(it.get('task_text',''))[:120]
    res = str(it.get('result',''))[:80]
    upd = str(it.get('updated',''))
    cre = str(it.get('created',''))
    print(f"id={tid} status={st} from={it.get('from','')} created={cre} updated={upd}")
    print(f"  task={task}")
    print(f"  result={res}")
print('Complete')
