#!/usr/bin/env python3
# READ-ONLY recon: prod Bridge ping + quote_price NMAX. No writes.
import os, json, urllib.parse, urllib.request

url = None; token = None
with open('/root/turbobaby-manager-bot/.env') as f:
    for ln in f:
        if ln.startswith('BRIDGE_URL='): url = ln.split('=',1)[1].strip()
        if ln.startswith('BRIDGE_TOKEN='): token = ln.split('=',1)[1].strip()

def call(params):
    params = dict(params); params['token'] = token
    q = urllib.parse.urlencode(params)
    full = url + '?' + q
    try:
        with urllib.request.urlopen(full, timeout=40) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:
        return 'ERR: ' + repr(e)

print('=== PING ===')
print(call({'action': 'ping'}))
print('=== QUOTE bike=4255 08.07-07.08 (30д) ===')
print(call({'action': 'quote_price', 'bike': '4255',
            'date_start': '08.07.2026', 'date_end': '07.08.2026'}))
print('=== QUOTE bike=4255 08.07-15.07 (7д) ===')
print(call({'action': 'quote_price', 'bike': '4255',
            'date_start': '08.07.2026', 'date_end': '15.07.2026'}))
