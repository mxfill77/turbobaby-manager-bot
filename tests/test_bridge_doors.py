"""Общая сборка моста с ОБЕИМИ дверями (BRIDGEBOTH0410, 04.10.2026): `bridge_build_doors/` =
зеркало `bridge_prod/` @84 + дверь кассы tx_find (TXFINDFIX0310) + двери договоров contract_find /
contract_pdf (CONTRACTFIX0410). Выкладывается ОДНИМ clasp вместо двух сборок по очереди: обе
правят Bridge.js, и вторая выкладка стёрла бы маршрут первой.

Покрытие: синтаксис; паспорт против зеркала и файлов; BotData.js и ContractDoor.js побайтно равны
сборкам своих дверей; разница Bridge.js с каждой сборкой — только блок другой двери и строка help;
харнесс tx_find и харнесс договоров на ЭТОЙ сборке (исходники подаются через stdin, сами харнессы
не тронуты) — все случаи зелёные; харнесс маршрутизатора — обе двери и help; МУТАНТЫ — каждый
ловится, и число упавших случаев называется."""
import difflib
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "bridge_build_doors")
TX = os.path.join(ROOT, "bridge_build_tx_find")
CT = os.path.join(ROOT, "bridge_build_contract")
MIRROR = os.path.join(ROOT, "bridge_prod")
H_TX = os.path.join(ROOT, "tests", "tx_find_gs_harness.js")
H_CT = os.path.join(ROOT, "tests", "contract_door_gs_harness.js")
H_RT = os.path.join(ROOT, "tests", "bridge_doors_router_harness.js")
FILES = ("BotData.js", "Bridge.js", "ContractDoor.js")
CONTRACT_DOOR_BEFORE_FIX = "bb0aa862e7da7ca413c463bc04e0992d663ed398"   # дверь договоров до CONTRACTFIX0410

_cache = {}


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _read(path):
    return _bytes(path).decode("utf-8")


def _sha(path):
    return hashlib.sha256(_bytes(path)).hexdigest()


def doors():
    """Исходники сборки для подачи в харнессы через stdin."""
    return {n: _read(os.path.join(BUILD, n)) for n in FILES}


def run(harness, override):
    proc = subprocess.run(["node", harness, "--stdin"], input=json.dumps(override), capture_output=True,
                          text=True, timeout=120, encoding="utf-8")
    try:
        res = json.loads(proc.stdout)
    except ValueError:
        res = {"cases": [], "failed": None}
    return proc.returncode, res, proc.stderr


def failed_names(res):
    return [c["name"] for c in res.get("cases", []) if not c["pass"]]


def test_build_js_syntax():
    for name in FILES:
        proc = subprocess.run(["node", "--check", os.path.join(BUILD, name)], capture_output=True, text=True,
                              timeout=30)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_build_passport():
    """База = зеркало @N пофайлово, содержимое = паспорт, к выкладке ровно три файла, настроек нет."""
    passport = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    mirror = json.loads(_read(os.path.join(MIRROR, "MIRROR.json")))
    assert passport["base_prod_version"] == mirror["prod_version"] == 84, \
        f"зеркало @{mirror['prod_version']}, сборка @{passport['base_prod_version']} — пересобрать"
    assert "delivered_as_version" not in passport
    assert passport["changed"] == ["BotData.js", "Bridge.js"]
    assert passport["added"] == ["ContractDoor.js"]
    assert passport["выкладке_подлежат"] == sorted(FILES)
    assert not os.path.exists(os.path.join(MIRROR, "ContractDoor.js")), "новый файл уже в зеркале?"
    for name in passport["changed"]:
        assert passport["base_sha256"][name] == mirror["files_sha256"][name] == _sha(os.path.join(MIRROR, name)), \
            f"{name}: база сборки разошлась с зеркалом"
    for name in FILES:
        assert passport["build_sha256"][name] == _sha(os.path.join(BUILD, name)), \
            f"{name}: файл сборки разошёлся со своим паспортом"
    assert sorted(os.listdir(BUILD)) == sorted(list(FILES) + ["BUILD.json"]), os.listdir(BUILD)
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))
    assert passport["script_id"] == mirror["script_id"]


def test_door_files_equal_their_builds():
    """BotData.js — из сборки кассы, ContractDoor.js — из сборки договоров, побайтно."""
    assert _bytes(os.path.join(BUILD, "BotData.js")) == _bytes(os.path.join(TX, "BotData.js"))
    assert _bytes(os.path.join(BUILD, "ContractDoor.js")) == _bytes(os.path.join(CT, "ContractDoor.js"))


def _diff(old_path, new_path):
    old = _read(old_path).splitlines()
    new = _read(new_path).splitlines()
    inserted, replaced = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        assert tag in ("insert", "replace"), f"{tag} {old[i1:i2]}"
        if tag == "insert":
            inserted += new[j1:j2]
        else:
            assert i2 - i1 == 1 and j2 - j1 == 1, f"{old[i1:i2]} → {new[j1:j2]}"
            replaced.append((old[i1], new[j1]))
    return inserted, replaced


def test_bridge_only_other_door_and_help():
    """Разница Bridge.js сборки с каждой сборкой двери — блок другой двери и строка help, больше ничего."""
    doors_js = os.path.join(BUILD, "Bridge.js")
    full = "'get_pending', 'tx_find', 'contract_find', 'contract_pdf'"
    ins, rep = _diff(os.path.join(TX, "Bridge.js"), doors_js)        # к кассе добавлены договоры
    assert [x for x in ins if x.strip().startswith("case ")] == ["      case 'contract_find':", "      case 'contract_pdf':"], ins
    assert len(ins) == 10 and "tx_find" not in "\n".join(ins), ins
    assert len(rep) == 1 and rep[0][0].replace("'get_pending', 'tx_find'", full) == rep[0][1], rep
    ins, rep = _diff(os.path.join(CT, "Bridge.js"), doors_js)        # к договорам добавлена касса
    assert [x for x in ins if x.strip().startswith("case ")] == ["      case 'tx_find':"], ins
    assert len(ins) == 6 and "contract" not in "\n".join(ins), ins
    assert len(rep) == 1 and rep[0][0].replace("'get_pending', 'contract_find', 'contract_pdf'", full) == rep[0][1], rep
    ins, rep = _diff(os.path.join(MIRROR, "Bridge.js"), doors_js)    # от зеркала — только вставки и help
    assert len(ins) == 16 and len(rep) == 1 and rep[0][0].replace("'get_pending'", full) == rep[0][1], (ins, rep)


def test_tx_find_harness_on_doors():
    code, res, err = run(H_TX, doors())
    assert code == 0 and res["failed"] == 0, f"{failed_names(res)} {err[-1500:]}"
    assert len(res["cases"]) == 72, len(res["cases"])


def test_contract_harness_on_doors():
    code, res, err = run(H_CT, doors())
    assert code == 0 and res["failed"] == 0, f"{failed_names(res)} {err[-1500:]}"
    assert len(res["cases"]) == 102, len(res["cases"])


def test_router_both_doors_and_help():
    code, res, err = run(H_RT, doors())
    assert code == 0 and res["failed"] == 0, f"{failed_names(res)} {err[-1500:]}"
    names = {c["name"] for c in res["cases"]}
    for need in ("route.tx_find", "route.contract_find", "route.contract_pdf", "help.names-all-three",
                 "door.contract_find-defined", "door.tx_find-defined"):
        assert need in names, need


def _contract_door_before_fix():
    proc = subprocess.run(["git", "-C", ROOT, "show", f"{CONTRACT_DOOR_BEFORE_FIX}:bridge_build_contract/ContractDoor.js"],
                          capture_output=True, timeout=30)
    assert proc.returncode == 0, f"нет блоба {CONTRACT_DOOR_BEFORE_FIX} — мутант не судим: {proc.stderr[-300:]}"
    return proc.stdout.decode("utf-8")


def mutants():
    """(имя, подмена файлов поверх сборки) — каждый обязан покраснить свой харнесс."""
    src = doors()
    bridge = src["Bridge.js"]
    assert bridge.count("case 'tx_find':") == 1 and bridge.count("case 'contract_find':") == 1 \
        and bridge.count("case 'contract_pdf':") == 1
    return [
        ("no-route-tx_find", {"Bridge.js": bridge.replace("case 'tx_find':", "case 'tx_find_x':")}),
        ("no-route-contracts", {"Bridge.js": bridge.replace("case 'contract_find':", "case 'contract_find_x':")
                                .replace("case 'contract_pdf':", "case 'contract_pdf_x':")}),
        ("botdata-of-base", {"BotData.js": _read(os.path.join(MIRROR, "BotData.js"))}),
        ("contractdoor-bb0aa862", {"ContractDoor.js": _contract_door_before_fix()}),
        ("no-contractdoor", {"ContractDoor.js": ""}),
    ]


def mutant_report():
    """{мутант: {харнесс: число упавших случаев}} — по всем трём харнессам."""
    if "mut" not in _cache:
        out = {}
        for name, sub in mutants():
            override = dict(doors(), **sub)
            row = {}
            for label, h in (("tx_find", H_TX), ("contract", H_CT), ("router", H_RT)):
                code, res, _ = run(h, override)
                row[label] = len(failed_names(res)) if res.get("cases") else ("harness_died" if code else 0)
            out[name] = row
        _cache["mut"] = out
    return _cache["mut"]


def test_mutants_killed():
    rep = mutant_report()
    must = {"no-route-tx_find": ("tx_find", "router"), "no-route-contracts": ("contract", "router"),
            "botdata-of-base": ("tx_find",), "contractdoor-bb0aa862": ("contract",),
            "no-contractdoor": ("contract", "router")}
    alive = [f"{m}/{h}" for m, hs in must.items() for h in hs if rep[m][h] == 0]
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
    print("мутанты (упавших случаев по харнессам):", json.dumps(mutant_report(), ensure_ascii=False))
    print(f"bridge_doors: {len(tests) - bad}/{len(tests)} зелёных, мутантов {len(mutants())}")
    sys.exit(1 if bad else 0)
