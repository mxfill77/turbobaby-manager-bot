#!/usr/bin/env python3
# READ-ONLY: fetch source of deployed version 64, inspect QuotePrice cap-read address.
import json, urllib.parse, urllib.request

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
with urllib.request.urlopen(req, timeout=60) as r:
    content = json.load(r)

for f in content.get('files', []):
    if f.get('name') == 'QuotePrice':
        src = f.get('source', '')
        print('QuotePrice length:', len(src))
        for i, line in enumerate(src.splitlines(), 1):
            L = line.lower()
            if any(k in line for k in ['CAPS_ANCHOR', 'QUOTE_CAP_SCAN', 'QUOTE_CAP_HEADER', 'col: 26', 'col: 11', 'headerRow', 'quoteReadCaps_']) \
               or 'getrange' in L and 'cap' in L:
                print('%4d: %s' % (i, line.strip()[:110]))
        # dump the quoteReadCaps_ body
        print('--- quoteReadCaps_ body ---')
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if 'function quoteReadCaps_' in line:
                for j in range(i, min(i+22, len(lines))):
                    print(lines[j][:120])
                break
