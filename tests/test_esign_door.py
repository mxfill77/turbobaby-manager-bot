"""Дверь договоров отдаёт PDF из «Подписанные/ГГГГ/ММ» и сама находит адреса (ESIGNDOOR0410, 04.10.2026).

Сборка `bridge_build_esign/` — полный каталог выкладки поверх зеркала `bridge_prod/` @85: 18 файлов
побайтно как в зеркале + правленый ContractDoor.js (прошлая выкладка @85 шла clasp push одним каталогом
в 19 файлов — состав тот же). Что изменено в двери:
  а) contract_pdf отдаёт PDF, если папка подписанных среди предков файла не дальше
     ESIGN.SIGNED_FOLDER_LEVELS = 3 (ММ → ГГГГ → «Подписанные»); глубже или вне — not_in_signed_folder с
     числом уровней; родителей не прочитать — parents_unreadable, PDF не отдаётся;
  б) свойство ESIGN_REGISTRY_ID / ESIGN_SIGNED_FOLDER_ID задано — только оно; не задано — ЕДИНСТВЕННАЯ
     таблица «Договоры — реестр подписей (TB e-Sign)» вне корзины и ЕДИНСТВЕННАЯ папка «Подписанные» в
     папке реестра; 0 или больше 1 — отказ с числом, первый не берётся; источник адреса — в ответе
     (config); в свойства не пишет.

Покрытие: синтаксис; паспорт против зеркала @85 (18 файлов побайтно, ContractDoor.js — база @85 и свой
sha256; база сверяется и с git-историей зеркала, поэтому замок переживает выкладку); выложенная сборка
сверяется с зеркалом ПО БАЙТАМ его файлов, а не только паспортами (подмену байтов при нетронутых
MIRROR.json и BUILD.json паспорта не видят — отрицательный тест портит по байту каждый .js копии
зеркала @86); службы Apps Script те же, что у двери @85; в двери нет пишущих вызовов; новый харнесс
tests/esign_door_gs_harness.js зелёный; ПЕРЕКРЁСТНО — старый харнесс дверей
tests/contract_door_gs_harness.js (102 случая) зелёный на новой сборке и на двери @85 из git-истории
зеркала (коммит MIRROR_85, с проверкой, что это правда @85: рабочий каталог зеркала с 04.10 описывает
@86), а новый харнесс на двери @85 красный ровно на новых ветках (32 из 36); МУТАНТЫ — пять, у двух по
два варианта (реестр и папка), каждый ловится СВОИМ случаем, число упавших печатается."""
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "bridge_build_esign")
MIRROR = os.path.join(ROOT, "bridge_prod")
H_NEW = os.path.join(ROOT, "tests", "esign_door_gs_harness.js")
H_OLD = os.path.join(ROOT, "tests", "contract_door_gs_harness.js")
DOOR = "ContractDoor.js"
LOADED = ("Config.js", "BotData.js", "Bridge.js", DOOR)   # что харнессы грузят в node
MIRROR_85 = "c72f57ea71872665765a86291cdbe293c7093a2d"     # коммит, которым зеркало сведено к проду @85
MIRROR_86 = "3c9466fecb0acb98732d5595903560ada76ad738"     # коммит, которым зеркало сведено к выкладке @86

_cache = {}


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _read(path):
    return _bytes(path).decode("utf-8")


def _sha(path):
    return hashlib.sha256(_bytes(path)).hexdigest()


def _git_blob(path, commit=MIRROR_85):
    """Файл зеркала из git-истории (по умолчанию @85 — база сборки), не с диска: зеркало сдвигается выкладками."""
    proc = subprocess.run(["git", "-C", ROOT, "show", f"{commit}:bridge_prod/{path}"], capture_output=True, timeout=30)
    assert proc.returncode == 0, f"нет блоба {commit}:{path} — базу не сверить: {proc.stderr[-300:]}"
    return proc.stdout


def _base_meta():
    if "base" not in _cache:
        _cache["base"] = json.loads(_git_blob("MIRROR.json").decode("utf-8"))
    return _cache["base"]


def run(harness, override=None):
    args = ["node", harness] + (["--stdin"] if override is not None else [])
    proc = subprocess.run(args, input=json.dumps(override) if override is not None else None,
                          capture_output=True, text=True, timeout=120, encoding="utf-8")
    try:
        res = json.loads(proc.stdout)
    except ValueError:
        res = {"cases": [], "failed": None}
    return proc.returncode, res, proc.stderr


def failed_names(res):
    return [c["name"] for c in res.get("cases", []) if not c["pass"]]


def files_of(where):
    return {n: _read(os.path.join(where, n)) for n in LOADED}


def files_85():
    """То, что грузят харнессы, — с двери @85 из git-истории зеркала (коммит MIRROR_85), не с диска:
    рабочий каталог зеркала с выкладки 04.10 описывает @86, и проверка «на @85» тихо гоняла бы новую сборку."""
    return {n: _git_blob(n).decode("utf-8") for n in LOADED}


def mirror_bytes(where, names):
    """Фактические байты файлов зеркала {имя: bytes, None — файла нет}: сверку выложенного судят они."""
    return {n: _bytes(os.path.join(where, n)) if os.path.isfile(os.path.join(where, n)) else None for n in names}


def delivered_mismatch(p, mirror, files):
    """(б) зеркало описывает ТУ выкладку → [имя, …], где прод разошёлся с построенным. Цепочка: паспорт
    сборки == паспорт зеркала == sha256 фактических байт файла зеркала; одних паспортов мало — подмену
    байтов при нетронутых MIRROR.json и BUILD.json они не видят."""
    bad = []
    for name in sorted(p["build_sha256"]):
        want = mirror["files_sha256"].get(name)
        if p["build_sha256"][name] != want:                  # паспорт сборки против паспорта зеркала
            bad.append(name)
        elif files.get(name) is None or hashlib.sha256(files[name]).hexdigest() != want:   # байты против паспорта
            bad.append(name)
    return bad


def test_build_js_syntax():
    for name in sorted(n for n in os.listdir(BUILD) if n.endswith(".js")):
        proc = subprocess.run(["node", "--check", os.path.join(BUILD, name)], capture_output=True, text=True,
                              timeout=30)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_build_passport():
    """18 файлов побайтно как в зеркале @85, ContractDoor.js — правка поверх базы @85, настроек нет."""
    p = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    mirror = json.loads(_read(os.path.join(MIRROR, "MIRROR.json")))
    base = _base_meta()
    assert base["prod_version"] == p["base_prod_version"] == 85, (base["prod_version"], p["base_prod_version"])
    assert p["script_id"] == base["script_id"] == mirror["script_id"]
    assert p["changed"] == [DOOR] and p["added"] == [], (p["changed"], p["added"])
    names = sorted(base["files_sha256"])
    assert sorted(p["build_sha256"]) == names and p["выкладке_подлежат"] == names, sorted(p["build_sha256"])
    assert sorted(os.listdir(BUILD)) == sorted(names + ["BUILD.json"]), os.listdir(BUILD)
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))
    for name in names:                                       # сборка = свой паспорт, по байтам
        assert p["build_sha256"][name] == _sha(os.path.join(BUILD, name)), f"{name}: файл разошёлся с паспортом"
    same = [n for n in names if n != DOOR]
    assert len(same) == 18 and p["unchanged"] == same, p.get("unchanged")
    for name in same:                                        # 18 файлов — ровно база @85
        assert p["build_sha256"][name] == base["files_sha256"][name] \
            == hashlib.sha256(_git_blob(name)).hexdigest(), f"{name}: не побайтно как в зеркале @85"
    assert p["base_sha256"] == {DOOR: base["files_sha256"][DOOR]}
    assert hashlib.sha256(_git_blob(DOOR)).hexdigest() == base["files_sha256"][DOOR]
    assert p["build_sha256"][DOOR] != base["files_sha256"][DOOR], "ContractDoor.js не изменён"

    delivered = p.get("delivered_as_version")
    if delivered is None:                                    # (а) не выложена: база = живое зеркало
        assert mirror["prod_version"] == 85, f"зеркало ушло на @{mirror['prod_version']} — пересобрать"
        for name in same:
            assert _bytes(os.path.join(BUILD, name)) == _bytes(os.path.join(MIRROR, name)), name
        return
    assert isinstance(delivered, int) and mirror["prod_version"] >= delivered, (delivered, mirror["prod_version"])
    if mirror["prod_version"] == delivered:                  # (б) зеркало описывает ТУ выкладку — по байтам
        bad = delivered_mismatch(p, mirror, mirror_bytes(MIRROR, names))
        assert not bad, f"{bad}: в проде не то, что построено (байты файлов зеркала против паспортов)"


def test_delivered_bytes_catch_js_corruption():
    """Отрицательный: копия зеркала @86 (коммит MIRROR_86, им выкладка сведена) с ОДНИМ испорченным байтом
    .js при нетронутых MIRROR.json и BUILD.json краснеет ровно на этом файле — по каждому .js; паспорта при
    этом сходятся, их одних подмена не видна. Близнец без порчи сходится. Порча — в памяти, диск не трогается."""
    p = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    mirror = json.loads(_git_blob("MIRROR.json", MIRROR_86).decode("utf-8"))
    assert mirror["prod_version"] == p["delivered_as_version"] == 86, (mirror["prod_version"], p["delivered_as_version"])
    names = sorted(p["build_sha256"])
    clean = {n: _git_blob(n, MIRROR_86) for n in names}
    assert delivered_mismatch(p, mirror, clean) == [], "копия зеркала без порчи разошлась с паспортами"
    js = [n for n in names if n.endswith(".js")]
    assert len(js) == 18, js
    for name in js:
        spoiled = bytearray(clean[name])
        spoiled[len(spoiled) // 2] ^= 0x01
        files = dict(clean, **{name: bytes(spoiled)})
        assert all(p["build_sha256"][n] == mirror["files_sha256"][n] for n in names)   # паспорта сходятся
        assert delivered_mismatch(p, mirror, files) == [name], f"{name}: порча байта не замечена"


_SERVICES = re.compile(r"\b(DriveApp|SpreadsheetApp|PropertiesService|Utilities|Session|UrlFetchApp|MailApp|"
                       r"GmailApp|CacheService|LockService|ScriptApp|DocumentApp|CalendarApp|HtmlService|"
                       r"ContentService|FormApp|SlidesApp)\b")


def test_services_same_as_85():
    """Службы Apps Script двери — те же, что у @85; манифест (права) побайтно как в зеркале."""
    new = set(_SERVICES.findall(_read(os.path.join(BUILD, DOOR))))
    old = set(_SERVICES.findall(_git_blob(DOOR).decode("utf-8")))
    assert new == old == {"DriveApp", "SpreadsheetApp", "PropertiesService", "Utilities", "Session"}, (new, old)
    assert _bytes(os.path.join(BUILD, "appsscript.json")) == _git_blob("appsscript.json")


def test_door_has_no_writes():
    src = _read(os.path.join(BUILD, DOOR))
    for bad in ("setValue", "setValues", "appendRow", "insertSheet", "deleteRow", "setProperty", "setProperties",
                "deleteProperty", "setTrashed", "moveTo", "createFile", "createFolder", "makeCopy", "setContent",
                "addEditor", "setName", "UrlFetchApp", "MailApp", "GmailApp"):
        assert bad not in src, f"в двери чтения есть {bad}"


def new_harness():
    if "new" not in _cache:
        _cache["new"] = run(H_NEW)
    return _cache["new"]


def test_new_harness_green():
    code, res, err = new_harness()
    assert code == 0 and res["failed"] == 0, f"{failed_names(res)} {err[-1500:]}"
    names = {c["name"] for c in res["cases"]}
    assert len(names) == 36, len(names)
    for need in ("anc.level1-ok", "anc.level2-ok", "anc.level3-month-ok", "anc.level4-refused",
                 "anc.outside-refused", "anc.file-parents-error", "anc.ancestor-error", "anc.cycle-terminates",
                 "reg.property-only", "reg.search-one", "reg.search-zero", "reg.search-two-refused",
                 "reg.trash-ignored", "reg.search-failed", "reg.pdf-two-refused", "dir.property-only",
                 "dir.no-props-month-pdf-ok", "dir.search-zero", "dir.search-two-refused", "dir.search-failed",
                 "route.pdf-no-props", "route.find-config", "reg.search-no-write", "readonly.no-writes"):
        assert need in names, f"нет кейса {need}"


def test_old_harness_on_new_build_and_on_85():
    """Старый харнесс дверей (102 случая, проверки не тронуты, моки дополнены) — зелёный и на новой
    сборке, и на двери @85: дополненные моки дверь @85 не замечает. @85 — из git (MIRROR_85), и перед
    прогоном сверено, что это правда @85, а не та же новая сборка."""
    runs = (("новая сборка", files_of(BUILD)), ("зеркало @85", files_85()))
    old, base = dict(runs)["зеркало @85"], _base_meta()
    for name in LOADED:                                      # прогон «@85» гоняет ровно файлы паспорта @85
        assert hashlib.sha256(old[name].encode("utf-8")).hexdigest() == base["files_sha256"][name], \
            f"{name}: прогон «@85» не на файлах зеркала @85"
    assert old[DOOR] != dict(runs)["новая сборка"][DOOR], "дверь «@85» равна новой — перекрёстная проверка выродилась"
    for label, files in runs:
        code, res, err = run(H_OLD, files)
        assert code == 0 and res["failed"] == 0, f"{label}: {failed_names(res)} {err[-1500:]}"
        assert len(res["cases"]) == 102, (label, len(res["cases"]))


# @85 проходит РОВНО то, что было верно и до правки: цикл отказан, без поиска при свойствах, записей нет
OLD_DOOR_GREEN = {"anc.cycle-terminates", "anc.no-search-with-props", "reg.search-no-write", "readonly.no-writes"}


def test_new_harness_on_door85_red():
    override = files_of(BUILD)
    override[DOOR] = _git_blob(DOOR).decode("utf-8")
    code, res, err = run(H_NEW, override)
    names = {c["name"] for c in res["cases"]}
    bad = set(failed_names(res))
    assert code == 1 and len(names) == 36, (code, len(names), err[-800:])
    assert names - bad == OLD_DOOR_GREEN and len(bad) == 32, sorted(names - bad)


def _door():
    return _read(os.path.join(BUILD, DOOR))


# мутант = (имя, [(было, стало), …], случаи, которые ОБЯЗАНЫ упасть)
MUTANTS = [
    ("only-immediate-parent", [("  SIGNED_FOLDER_LEVELS: 3,", "  SIGNED_FOLDER_LEVELS: 1,")],
     {"anc.level2-ok", "anc.level3-month-ok", "dir.no-props-month-pdf-ok"}),
    ("no-level-limit", [("while (front.length && level < max) {", "while (front.length) {")],
     {"anc.level4-refused", "dir.no-props-deep-refused"}),
    ("two-registries-first-taken",
     [("if (found.length !== 1) return { ok: false, error: found.length ? 'registry_ambiguous'",
       "if (found.length === 0) return { ok: false, error: found.length ? 'registry_ambiguous'")],
     {"reg.search-two-refused", "reg.pdf-two-refused"}),
    ("search-over-property:registry",
     [("  if (id) return { ok: true, id: id, source: 'property' };\n  var found;",
       "  if (id && !DriveApp.getFilesByName(ESIGN.REGISTRY_NAME).hasNext()) "
       "return { ok: true, id: id, source: 'property' };\n  var found;")],
     {"reg.property-only"}),
    ("search-over-property:folder",
     [("  if (id) return { ok: true, id: id, source: 'property' };\n  if (!regAddr.ok) return regAddr;",
       "  if (id && !regAddr.ok) return { ok: true, id: id, source: 'property' };\n  if (!regAddr.ok) return regAddr;")],
     {"dir.property-only"}),
    ("search-writes-property:registry",
     [("реестр не открывался' };\n  return { ok: true, id: found[0].getId(), source: 'search' };",
       "реестр не открывался' };\n  PropertiesService.getScriptProperties().setProperty(ESIGN.REGISTRY_PROP, "
       "found[0].getId());\n  return { ok: true, id: found[0].getId(), source: 'search' };")],
     {"reg.search-no-write", "readonly.no-writes"}),
    ("search-writes-property:folder",
     [("нужна ровно одна' };\n  return { ok: true, id: found[0].getId(), source: 'search' };",
       "нужна ровно одна' };\n  PropertiesService.getScriptProperties().setProperty(ESIGN.SIGNED_FOLDER_PROP, "
       "found[0].getId());\n  return { ok: true, id: found[0].getId(), source: 'search' };")],
     {"readonly.no-writes"}),
]


def mutant_report():
    """{мутант: (число упавших случаев, их имена)} на новом харнессе."""
    if "mut" not in _cache:
        out = {}
        for name, subs, _ in MUTANTS:
            src = _door()
            for old, new in subs:
                assert src.count(old) == 1, f"мутант {name}: «было» встречается {src.count(old)} раз"
                src = src.replace(old, new)
            override = files_of(BUILD)
            override[DOOR] = src
            code, res, err = run(H_NEW, override)
            out[name] = (len(failed_names(res)) if res.get("cases") else "harness_died", failed_names(res))
        _cache["mut"] = out
    return _cache["mut"]


def test_mutants_killed():
    rep = mutant_report()
    for name, _, must in MUTANTS:
        n, bad = rep[name]
        assert isinstance(n, int) and n > 0, f"мутант {name} выжил: {rep[name]}"
        assert must <= set(bad), f"мутант {name}: не упали {sorted(must - set(bad))}"


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
    print("мутанты (упавших случаев из 36):", json.dumps({k: v[0] for k, v in mutant_report().items()},
                                                          ensure_ascii=False))
    print(f"esign_door: {len(tests) - bad}/{len(tests)} зелёных, мутантов {len(MUTANTS)}")
    sys.exit(1 if bad else 0)
