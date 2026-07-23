#!/usr/bin/env python3
from bridge_client import BridgeClient
b = BridgeClient()
r = b._call('read_doc', name='cc_log')
txt = r.get('text') or r.get('content') or ''
lines = txt.splitlines()
# print full lines 3..11 (recent caps entries) untruncated
for i in range(3, 12):
    if i < len(lines):
        print('--- line %d ---' % i)
        print(lines[i])
