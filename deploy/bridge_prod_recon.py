"""ОТПЕЧАТОК МОСТА: три состояния Apps Script — папка / HEAD проекта / задеплоенная версия.

Зачем: перед `clasp push` нельзя гадать по mtime и `.bak`, кто впереди. Отпечаток по BRIDGE_URL
показывает только ЗАДЕПЛОЕННЫЙ код, а push перезаписывает HEAD — третье состояние, которого
по URL не видно вовсе (04.08.2026 в HEAD лежала чужая незадеплоенная работа; push снёс бы её
молча). Этот скрипт снимает ОБА состояния прямо у Apps Script API теми же учётками, что у clasp.

Read-only: только GET'ы, ничего не пишет в Google. Секреты не печатаются.
Запуск:  venv/bin/python3 deploy/bridge_prod_recon.py [каталог-для-снимков]
По умолчанию снимки кладутся в /root/_bridge_prod_snapshot.

На выходе: какая версия обслуживает прод-URL, хвост списка версий, исходники HEAD и прод-версии
по папкам `head/` и `prod_v<N>/`, плюс `meta.json`. База слияния для деплоя — HEAD.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

SCRIPT_ID = "12iXPDU_wxcyslItPW6X41ODuoVxx2smmlQBfhSwI6Lt42MTrYbv9HhOJ"
PROD_DEPLOYMENT = "AKfycbxNC9gCM7-a635gDMk_jtPKsBNeCcBA23uuyrWXcMWHNREANzFSnpE1kXISAYZ_hXNOqw"
CREDS = "/root/.clasprc.json"
DEFAULT_BASE = "/root/_bridge_prod_snapshot"


def access_token():
    t = json.load(open(CREDS))["tokens"]["default"]
    body = urllib.parse.urlencode({
        "client_id": t["client_id"],
        "client_secret": t["client_secret"],
        "refresh_token": t["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["access_token"]


def api(tok, path, params=None):
    url = "https://script.googleapis.com/v1/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def dump(files, folder):
    os.makedirs(folder, exist_ok=True)
    names = []
    for f in files:
        ext = {"SERVER_JS": ".js", "HTML": ".html", "JSON": ".json"}.get(f["type"], ".txt")
        name = f["name"] + ext
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(f.get("source", ""))
        names.append(name)
    return sorted(names)


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    tok = access_token()

    deps = api(tok, "projects/%s/deployments" % SCRIPT_ID).get("deployments", [])
    prod_ver = None
    print("=== ДЕПЛОИ ===")
    for d in deps:
        cfg = d.get("deploymentConfig", {})
        mark = "  <-- ПРОД (обслуживает BRIDGE_URL)" if d.get("deploymentId") == PROD_DEPLOYMENT else ""
        print("  id=%s... version=%s desc=%r%s" % (
            str(d.get("deploymentId"))[:16], cfg.get("versionNumber", "HEAD"),
            cfg.get("description", ""), mark))
        if d.get("deploymentId") == PROD_DEPLOYMENT:
            prod_ver = cfg.get("versionNumber")
    print("прод обслуживает версию:", prod_ver)

    vers = sorted(api(tok, "projects/%s/versions" % SCRIPT_ID, {"pageSize": 50}).get("versions", []),
                  key=lambda v: v.get("versionNumber", 0))
    print("=== ВЕРСИИ (последние 6 из %d) ===" % len(vers))
    for v in vers[-6:]:
        print("  @%s  %s  %s" % (v.get("versionNumber"), v.get("createTime"),
                                 (v.get("description") or "")[:80]))

    head = api(tok, "projects/%s/content" % SCRIPT_ID)
    names_head = dump(head.get("files", []), os.path.join(base, "head"))
    print("HEAD файлов: %d -> %s/head   (ИМЕННО ЕГО перезапишет clasp push)"
          % (len(names_head), base))

    prod_files = None
    if prod_ver:
        pv = api(tok, "projects/%s/content" % SCRIPT_ID, {"versionNumber": prod_ver})
        prod_files = dump(pv.get("files", []), os.path.join(base, "prod_v%s" % prod_ver))
        print("@%s файлов: %d -> %s/prod_v%s" % (prod_ver, len(prod_files), base, prod_ver))
        hmap = {f["name"]: f.get("source", "") for f in head.get("files", [])}
        pmap = {f["name"]: f.get("source", "") for f in pv.get("files", [])}
        diff = [n for n in sorted(set(hmap) | set(pmap)) if hmap.get(n) != pmap.get(n)]
        print("HEAD vs @%s расходятся файлы: %s" % (prod_ver, diff or "— (HEAD == прод)"))
        if diff:
            print("  ВНИМАНИЕ: HEAD впереди прода. redeploy опубликует ЭТО ТОЖЕ — назови владельцу.")

    with open(os.path.join(base, "meta.json"), "w", encoding="utf-8") as fh:
        # script_id пишется в снимок с 23.08.2026: по нему машина сведения зеркала
        # (`mirror_sync.plan`) отвечает «чей это мост» — иначе отпечаток чужого проекта
        # молча переписал бы наше зеркало, и паспорт заявил бы о нём как о нашем проде.
        fh.write(json.dumps({"prod_version": prod_ver, "script_id": SCRIPT_ID,
                             "versions_tail": vers[-6:],
                             "head_files": names_head, "prod_files": prod_files},
                            ensure_ascii=False, indent=1))
    print("мета:", os.path.join(base, "meta.json"))


main()
