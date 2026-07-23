#!/usr/bin/env python3
# READ-ONLY: raw live cells from MANAGER 'Календарь бронирования' via Sheets API (bypass Bridge/Cache).
import json, urllib.parse, urllib.request

SPREADSHEET = '1sL-rw0klRcJKtWKpgIzLVge6U1GswtBUacJ_jo0JgL0'
TAB = 'Календарь бронирования'
tok = json.load(open('/root/.clasprc.json'))['tokens']['default']

def refresh():
    data = urllib.parse.urlencode({
        'client_id': tok['client_id'], 'client_secret': tok['client_secret'],
        'refresh_token': tok['refresh_token'], 'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)['access_token']

at = refresh()

def rng(a1):
    r = TAB + '!' + a1
    url = ('https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s'
           '?valueRenderOption=UNFORMATTED_VALUE&majorDimension=ROWS'
           % (SPREADSHEET, urllib.parse.quote(r)))
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + at})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.load(resp).get('values', [])
    except urllib.error.HTTPError as e:
        return 'HTTPError %s: %s' % (e.code, e.read().decode('utf-8','replace')[:300])
    except Exception as e:
        return 'ERR ' + repr(e)

# 1) The two addresses owner inspected
for a1 in ['K3:M3', 'K4:M15', 'Z3:AB3', 'Z4:AB15']:
    print('=== %s ===' % a1)
    print(rng(a1))

# 2) Full K-version scan region: header row 3 across K..T (11..20), data rows 4..23
print('\n=== FULL SCAN row3 K3:T3 (K-version header scan) ===')
print(rng('K3:T3'))
print('=== FULL SCAN K3:T23 (K-version data window, 20 rows) ===')
for row in (rng('K3:T23') or []):
    print(row)

# 3) Wide sweep: any "модель"/cap block anywhere right of the live J-quote
print('\n=== WIDE SWEEP A1..AF40 — hunt any cap header/values ===')
grid = rng('A1:AF40')
if isinstance(grid, str):
    print(grid)
else:
    import re
    for ri, row in enumerate(grid, start=1):
        for ci, val in enumerate(row):
            s = str(val).strip().lower()
            if not s:
                continue
            if 'модель' in s or 'кап' in s or 'активен' in s or s == '5000' or val == 5000:
                col = ''
                c = ci
                while True:
                    col = chr(65 + c % 26) + col
                    c = c // 26 - 1
                    if c < 0:
                        break
                print('  hit R%d %s = %r' % (ri, col, val))
