"""BRIDGEFIX0710 (07.10.2026): Bot Data больше не создаётся сама. `bridge_build_botdata/` = зеркало
`bridge_prod/` @86 + правка двух файлов (BotData.js, Bridge.js).

До 07.10 любой сбой openById молча заводил новую пустую таблицу «TurboBaby Bot Data» и перезаписывал
BOT_DATA_SHEET_ID (BotData.js:121-163 @86): касса, очередь и журналы уходили на пустую копию. Теперь —
названный отказ ok:false (no_botdata_config / botdata_unavailable / botdata_tab_missing), а новую таблицу
заводит только ручная setupBotData() (прежний id → BOT_DATA_SHEET_ID_PREV).

Покрытие:
  * синтаксис всех .js сборки (node --check);
  * паспорт BUILD.json: состав 19 файлов, база @86 из git-истории зеркала (MIRROR_86) по блобам,
    правлены ровно BotData.js и Bridge.js; три состояния (не выложена / выложена и зеркало о ней /
    прод ушёл дальше) — как у соседних сборок;
  * статические замки: SpreadsheetApp.create — только в createBotDataSpreadsheet_; его зовёт только
    setupBotData; setupBotData не зовёт никто; setProperty('BOT_DATA_SHEET_ID…') — только в setupBotData;
    открытие getBotDataSpreadsheet_ не создаёт и не пишет ничего;
  * харнесс tests/botdata_store_harness.js на сборке — все случаи зелёные (H1–H6);
  * тот же харнесс на базе @86 (блобы git) — красный именно в H1/H2/H3/H5: тест кусает;
  * дифференциал обычного пути H4: ответы базы и сборки побайтно равны;
  * МУТАНТЫ — каждый обязан покраснить харнесс, число упавших случаев называется.
Внешних API нет: харнесс исполняет код моста в node на заглушках."""
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "bridge_build_botdata")
MIRROR = os.path.join(ROOT, "bridge_prod")
HARNESS = os.path.join(ROOT, "tests", "botdata_store_harness.js")
MIRROR_86 = "3c9466fecb0acb98732d5595903560ada76ad738"   # этим коммитом зеркало @86 введено в git
CHANGED = ("BotData.js", "Bridge.js")
LOADED = ("Config.js", "BotData.js", "Bridge.js")          # что исполняет харнесс
_cache = {}


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _text(name):
    return _bytes(os.path.join(BUILD, name)).decode("utf-8")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _passport():
    return json.loads(_bytes(os.path.join(BUILD, "BUILD.json")).decode("utf-8"))


def _base_blob(name):
    if ("blob", name) not in _cache:
        p = subprocess.run(["git", "-C", ROOT, "show", f"{MIRROR_86}:bridge_prod/{name}"], capture_output=True,
                           timeout=30)
        assert p.returncode == 0, f"нет блоба {MIRROR_86}:{name} — базу не сверить: {p.stderr[-300:]}"
        _cache[("blob", name)] = p.stdout
    return _cache[("blob", name)]


def base_sources():
    return {n: _base_blob(n).decode("utf-8") for n in LOADED}


def run(override=None, record=False):
    args = ["node", HARNESS, BUILD] + (["--stdin"] if override is not None else []) + (["--record"] if record else [])
    p = subprocess.run(args, input=json.dumps(override or {}), capture_output=True, text=True, timeout=120,
                       encoding="utf-8")
    try:
        res = json.loads(p.stdout)
    except ValueError:
        res = {"cases": [], "failed": None, "stderr": p.stderr[-800:]}
    return p.returncode, res


def failed_names(res):
    return [c["name"] for c in res.get("cases", []) if not c["pass"]]


def test_build_js_syntax():
    for n in sorted(os.listdir(BUILD)):
        if n.endswith(".js"):
            p = subprocess.run(["node", "--check", os.path.join(BUILD, n)], capture_output=True, text=True, timeout=30)
            assert p.returncode == 0, f"{n}: {p.stderr}"


def test_build_passport():
    """(а) не выложена — база = живое зеркало @86 пофайлово; (б) выложена и зеркало описывает ТУ версию —
    каждый файл сборки побайтно в зеркале; (в) прод ушёл дальше — сборка не тронута по байтам. База сверяется
    всегда — с зеркалом @86 из git-истории (MIRROR_86)."""
    pp = _passport()
    mirror = json.loads(_bytes(os.path.join(MIRROR, "MIRROR.json")).decode("utf-8"))
    names = sorted(n for n in os.listdir(BUILD) if n != "BUILD.json")
    assert len(names) == 19 and pp["выкладке_подлежат"] == names, names
    assert pp["base_prod_version"] == 86 and pp["changed"] == list(CHANGED) and pp["added"] == []
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))
    base = json.loads(_base_blob("MIRROR.json").decode("utf-8"))
    assert base["prod_version"] == 86 and base["script_id"] == pp["script_id"] == mirror["script_id"]
    for n in names:
        b = _bytes(os.path.join(BUILD, n))
        assert pp["build_sha256"][n] == _sha(b), f"{n}: файл сборки разошёлся со своим паспортом"
        same = _sha(b) == base["files_sha256"][n] == _sha(_base_blob(n))
        if n in CHANGED:
            assert not same and pp["base_sha256"][n] == base["files_sha256"][n], f"{n}: не правлен или база не та"
        else:
            assert same, f"{n}: правлен сверх задания"
    delivered = pp.get("delivered_as_version")
    if delivered is None:                                                  # (а)
        assert mirror["prod_version"] == 86, f"зеркало @{mirror['prod_version']}, сборка от @86 — пересобрать"
        for n in names:
            assert mirror["files_sha256"][n] == _sha(_base_blob(n)), f"{n}: живое зеркало ≠ база @86"
        return
    assert isinstance(mirror["prod_version"], int) and mirror["prod_version"] >= delivered > 86, \
        f"сборка выложена как @{delivered}, зеркало @{mirror['prod_version']} — зеркало отстало от прода"
    if mirror["prod_version"] == delivered:                                # (б)
        for n in names:
            assert pp["build_sha256"][n] == mirror["files_sha256"][n] == _sha(_bytes(os.path.join(MIRROR, n))), \
                f"{n}: в проде не то, что построено"


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _fn_body(src, name):
    body = src[src.index("function " + name):]
    return body[:body.index("\nfunction ", 1)]


def test_static_locks():
    code = {n: _strip_comments(_text(n)) for n in os.listdir(BUILD) if n.endswith(".js")}
    allc = "\n".join(code.values())
    bd = code["BotData.js"]
    assert allc.count("SpreadsheetApp.create(") == 1, allc.count("SpreadsheetApp.create(")
    cr = _fn_body(bd, "createBotDataSpreadsheet_")
    assert "SpreadsheetApp.create(" in cr and "setProperty" not in cr
    assert len(re.findall(r"createBotDataSpreadsheet_\(", allc)) == 2      # определение + один вызов
    sb = _fn_body(bd, "setupBotData")
    assert "createBotDataSpreadsheet_(" in sb
    no_str = re.sub(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`[^`]*`", "''", allc)   # слово в тексте — не вызов
    assert len(re.findall(r"\bsetupBotData\s*\(", no_str)) == 1, "setupBotData зовётся кодом моста"
    setp = re.findall(r"setProperty\(\s*'BOT_DATA_SHEET_ID[A-Z_]*'", allc)
    assert len(setp) == 2 and all(s in sb for s in setp), setp
    op = _fn_body(bd, "getBotDataSpreadsheet_")
    for bad in ("create", "setProperty", "initTab_", "insertSheet", "deleteProperty"):
        assert bad not in op, bad


def test_harness_green_on_build():
    code, res = run()
    assert code == 0 and res.get("failed") == 0, failed_names(res) or res
    assert len(res["cases"]) >= 60, len(res["cases"])


def test_harness_bites_base():
    code, res = run(override=base_sources())
    bad = failed_names(res)
    assert code == 1 and bad, "на @86 харнесс зелёный — тест не кусает"
    for grp in ("H1.", "H2.", "H3.", "H5."):
        assert any(n.startswith(grp) for n in bad), f"на @86 нет красных в {grp}"
    assert not [n for n in bad if n.startswith(("H4.", "H6.", "load."))], bad
    _cache["base_red"] = len(bad)


def test_normal_path_byte_equal_to_base():
    _, a = run(override=base_sources(), record=True)
    _, b = run(record=True)
    assert a.get("load") == [] and b.get("load") == []
    h4a, h4b = a["record"]["H4"], b["record"]["H4"]
    assert sorted(h4a) == sorted(h4b) and len(h4a) == 9
    diff = [k for k in h4a if json.dumps(h4a[k], ensure_ascii=False) != json.dumps(h4b[k], ensure_ascii=False)]
    assert not diff, diff


def mutants():
    bd, br = _text("BotData.js"), _text("Bridge.js")
    thr = "throw botDataStoreError_('botdata_unavailable', 'таблица Bot Data не открылась: ' + botDataReason_(e, id));"
    noc = ("throw botDataStoreError_('no_botdata_config',\n"
           "      'свойство BOT_DATA_SHEET_ID не задано — таблицу Bot Data заводит только ручная setupBotData()');")
    txg = "if (!tab && tabName === BOTDATA.TABS.TX) {"
    strip = "if (id) s = s.split(String(id)).join('…');"
    prev = "if (prev) props.setProperty('BOT_DATA_SHEET_ID_PREV', prev);"
    gmap = "if (err && err.botdata_code) {\n      console.error('Bridge BotData:', err.message);"
    pmap = "if (err && err.botdata_code) {   // хранилище Bot Data"
    for frag, src in ((thr, bd), (noc, bd), (txg, bd), (strip, bd), (prev, bd), (gmap, br), (pmap, br)):
        assert src.count(frag) == 1, frag
    return [
        ("M1-create-back-in-catch", {"BotData.js": bd.replace(thr, "const ss2 = createBotDataSpreadsheet_(); "
                                     "props.setProperty('BOT_DATA_SHEET_ID', ss2.getId()); return ss2;")}),
        ("M2-create-in-catch-no-prop", {"BotData.js": bd.replace(thr, "return createBotDataSpreadsheet_();")}),
        ("M3-autocreate-no-config", {"BotData.js": bd.replace(noc, "const ss3 = createBotDataSpreadsheet_(); "
                                     "props.setProperty('BOT_DATA_SHEET_ID', ss3.getId()); return ss3;")}),
        ("M4-tx-tab-created-again", {"BotData.js": bd.replace(txg, "if (!tab && false) {")}),
        ("M5-reason-leaks-id", {"BotData.js": bd.replace(strip, "")}),
        ("M6-setup-no-prev", {"BotData.js": bd.replace(prev, "")}),
        ("M7-get-mapping-dropped", {"Bridge.js": br.replace(gmap, "if (false) {\n      console.error('Bridge BotData:', err.message);")}),
        ("M8-post-mapping-dropped", {"Bridge.js": br.replace(pmap, "if (false) {   // хранилище Bot Data")}),
    ]


def mutant_report():
    if "mut" not in _cache:
        out = {}
        for name, sub in mutants():
            code, res = run(override=sub)
            out[name] = len(failed_names(res)) if res.get("cases") else ("harness_died" if code else 0)
        _cache["mut"] = out
    return _cache["mut"]


def test_mutants_killed():
    rep = mutant_report()
    alive = [m for m, n in rep.items() if n == 0]
    assert not alive, f"мутанты выжили: {alive} · {json.dumps(rep, ensure_ascii=False)}"


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for k, fn in tests:
        try:
            fn()
            print(f"OK   {k}")
        except Exception as e:   # noqa: BLE001 — печатаем и считаем
            bad += 1
            print(f"FAIL {k}: {e}")
    print("на базе @86 красных случаев:", _cache.get("base_red"))
    print("мутанты (упавших случаев харнесса):", json.dumps(mutant_report(), ensure_ascii=False))
    print(f"botdata_store: {len(tests) - bad}/{len(tests)} зелёных, мутантов {len(mutants())}")
    sys.exit(1 if bad else 0)
