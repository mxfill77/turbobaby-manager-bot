#!/usr/bin/env python3
# READ-ONLY: read RAW live cells from MANAGER 'Календарь бронирования' via Sheets API (bypasses Bridge).
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
            d = json.load(resp)
            return d.get('values', [])
    except urllib.error.HTTPError as e:
        return 'HTTPError %s: %s' % (e.code, e.read().decode('utf-8','replace')[:300])
    except Exception as e:
        return 'ERR ' + repr(e)

for a1 in ['Z3:AB3', 'Z3:AB15', 'K3:M3', 'K3:M15', 'H3:J3']:
    print('=== %s ===' % a1)
    print(rng(a1))
