#!/usr/bin/env python3
# READ-ONLY: refresh clasp OAuth token, list Apps Script deployments/versions. No writes.
import json, urllib.parse, urllib.request

SCRIPT_ID = '12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ'
PROD_DEPLOY = 'AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw'

tok = json.load(open('/root/.clasprc.json'))['tokens']['default']

def refresh():
    data = urllib.parse.urlencode({
        'client_id': tok['client_id'], 'client_secret': tok['client_secret'],
        'refresh_token': tok['refresh_token'], 'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)['access_token']

def get(url, at):
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + at})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

at = refresh()
print('token refreshed ok')
deps = get('https://script.googleapis.com/v1/projects/%s/deployments' % SCRIPT_ID, at)
print('=== DEPLOYMENTS ===')
for d in deps.get('deployments', []):
    dc = d.get('deploymentConfig', {})
    dep_id = d.get('deploymentId')
    ver = dc.get('versionNumber')
    is_prod = ' <<< PROD (URL)' if dep_id == PROD_DEPLOY else ''
    print('deploymentId=%s ver=%s desc=%r%s' % (dep_id, ver, dc.get('description'), is_prod))
print('=== VERSIONS ===')
vers = get('https://script.googleapis.com/v1/projects/%s/versions' % SCRIPT_ID, at)
for v in vers.get('versions', []):
    print('v%s  %s  %r' % (v.get('versionNumber'), v.get('createTime'), v.get('description')))
