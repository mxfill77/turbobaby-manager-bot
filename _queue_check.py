import os, sys
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv('/root/turbobaby-manager-bot/.env')
from bridge_client import BridgeClient
bc = BridgeClient()
r = bc.get_pending_multi(['new','in_progress','needs_approval','done','failed'], lane='all')
if r.get('ok'):
    items = r.get('items', [])
    ids = sorted([int(it.get('id',0)) for it in items if it.get('id')])
    print('Total items:', len(items))
    if ids:
        print('ID range:', min(ids), 'to', max(ids))
    by_status = {}
    for it in items:
        st = it.get('status','?')
        by_status[st] = by_status.get(st, 0) + 1
    print('By status:', by_status)
    if ids:
        gaps = [i for i in range(min(ids), max(ids)+1) if i not in ids]
        print('Missing IDs (gaps):', gaps[:30])
    froms = {}
    for it in items:
        f = it.get('from','?')
        froms[f] = froms.get(f, 0) + 1
    print('By from:', froms)
else:
    print('Error:', r)
