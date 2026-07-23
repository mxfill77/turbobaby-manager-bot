#!/usr/bin/env python3
# READ-ONLY: fetch the EXACT source of deployed version 64 (prod) — caps read/write address.
import json, urllib.parse, urllib.request, re

SCRIPT_ID = '12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ'
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
url = 'https://script.googleapis.com/v1/projects/%s/content?versionNumber=64' % SCRIPT_ID
req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + at})
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)

for f in data.get('files', []):
    if f.get('name') == 'QuotePrice':
        src = f.get('source', '')
        print('QuotePrice source length:', len(src))
        # caps read address markers
        for pat in ['CAPS_ANCHOR', 'QUOTE_CAP_SCAN_FROM', 'QUOTE_CAP_HEADER_ROW',
                    "col: 26", "col:26", "col = 26", 'headerRow', 'quoteFindCapCol_',
                    'setValues', 'nmax']:
            idxs = [m.start() for m in re.finditer(re.escape(pat), src)]
            if idxs:
                print('  MARK %-22s x%d' % (pat, len(idxs)))
        print('\n--- lines mentioning cap read/write address ---')
        for ln in src.splitlines():
            low = ln.lower()
            if any(k in low for k in ['caps_anchor', 'quote_cap_scan', 'quote_cap_header',
                                      'col: 26', 'col:26', "'модель'", 'getrange(caps',
                                      'quotefindcapcol', 'scan_from', 'headerrow']):
                print('   ', ln.strip()[:120])
