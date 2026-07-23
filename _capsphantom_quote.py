#!/usr/bin/env python3
# READ-ONLY: live Bridge quote_price for NMAX (SpreadsheetApp read = uncached) + ping version.
import json
from bridge_client import BridgeClient
b = BridgeClient()
print('=== ping (version marker) ===')
print(json.dumps(b.ping(), ensure_ascii=False))
print('\n=== quote_price NMAX 30d ===')
r = b._call('quote_price', bike='NMAX', date_start='06.07.2026', date_end='05.08.2026')
print(json.dumps(r, ensure_ascii=False, indent=1))
