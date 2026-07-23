#!/usr/bin/env python3
# READ-ONLY: list Apps Script deployments + versions (which version serves prod URL).
import json, urllib.parse, urllib.request

SCRIPT_ID = '12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ'
PROD_DEP = 'AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw'
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
def get(url):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + at})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        return {'HTTPError': e.code, 'body': e.read().decode('utf-8','replace')[:300]}

print('=== DEPLOYMENTS ===')
d = get('https://script.googleapis.com/v1/projects/%s/deployments' % SCRIPT_ID)
for dep in d.get('deployments', []):
    dc = dep.get('deploymentConfig', {})
    ent = dep.get('entryPoints', [{}])
    url = ''
    for e in ent:
        w = e.get('webApp', {})
        if w.get('url'):
            url = w['url']
    depid = dep.get('deploymentId','')
    is_prod = PROD_DEP in url or depid == PROD_DEP
    print('  dep=%s ver=%s desc=%r %s' % (
        depid[:24], dc.get('versionNumber','HEAD'), dc.get('description',''),
        '<<< PROD (serves BRIDGE_URL)' if is_prod else ''))
    if url:
        print('      url=...%s' % url[-40:])

print('\n=== VERSIONS (latest first) ===')
v = get('https://script.googleapis.com/v1/projects/%s/versions?pageSize=50' % SCRIPT_ID)
vers = sorted(v.get('versions', []), key=lambda x: x.get('versionNumber',0), reverse=True)
for ver in vers[:15]:
    print('  v%s  %s  %r' % (ver.get('versionNumber'), ver.get('createTime',''), ver.get('description','')[:70]))
