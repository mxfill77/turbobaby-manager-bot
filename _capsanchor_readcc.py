#!/usr/bin/env python3
# READ-ONLY: read top of cc_log to locate врезка (═-only line) for safe insert.
from bridge_client import BridgeClient
import os
b = BridgeClient()
r = b._call('read_doc', name='cc_log')
txt = r.get('text') or r.get('content') or ''
print('OK read, len=', len(txt))
lines = txt.splitlines()
for i, ln in enumerate(lines[:40]):
    mark = ''
    s = ln.strip()
    if s and set(s) == {'═'}:
        mark = '   <<< ═-ONLY LINE'
    print('%3d|%s%s' % (i, ln[:90], mark))
