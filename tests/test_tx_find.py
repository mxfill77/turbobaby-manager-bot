"""Дверь моста tx_find (К1 проекта AGENTASKSPL0310, 03.10.2026) — read-only поиск проводок кассы
по байку, брони и сроку. Реальный код моста гоняется node-харнессом tests/tx_find_gs_harness.js
(способ botdata_gs_harness.js / undo_door_harness.js): сборка `bridge_build_tx_find/` поверх
зеркала `bridge_prod/` (правило srcOf).

Покрытие: синтаксис двух файлов сборки; харнесс зелёный и несёт ключевые случаи (байк, бронь,
срок, отменённая не отдаётся, пометка в raw, ссылка t.me/c/…, пусто с числом просмотренных);
паспорт сборки против зеркала; сборка только ДОБАВЛЯЕТ к зеркалу; клиентский метод
`BridgeClient.tx_find` — GET (`_call`), в мост уходят только названные фильтры; МУТАНТЫ —
каждый ловится харнессом (исходник подменяется через stdin, файлов не создаётся).

Клиентский метод проверяется разбором исходника (ast) и исполнением ЕГО ЖЕ текста на подставном
`self`: импорт bridge_client тянет `fcntl` и сеть, а у метода зависимостей нет — так тест идёт
одинаково на сервере и на ПК."""
import ast
import difflib
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "bridge_build_tx_find")
MIRROR = os.path.join(ROOT, "bridge_prod")
HARNESS = os.path.join(ROOT, "tests", "tx_find_gs_harness.js")
CLIENT = os.path.join(ROOT, "bridge_client.py")

_cache = {}


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_harness(override=None):
    args = ["node", HARNESS] + (["--stdin"] if override is not None else [])
    proc = subprocess.run(args, input=json.dumps(override) if override is not None else None,
                          capture_output=True, text=True, timeout=60, encoding="utf-8")
    return proc.returncode, proc.stdout, proc.stderr


def harness():
    if "res" not in _cache:
        _cache["res"] = run_harness()
    return _cache["res"]


def test_build_js_syntax():
    for name in ("BotData.js", "Bridge.js"):
        proc = subprocess.run(["node", "--check", os.path.join(BUILD, name)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_harness_all_green():
    code, out, err = harness()
    assert code == 0, f"харнесс красный:\nstdout={out[-3000:]}\nstderr={err[-2000:]}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 40, len(res["cases"])


def test_harness_covers_key_cases():
    code, out, err = harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    for need in ("bike.rows", "bike.plate-not-string", "booking.rows", "span.rows",
                 "span.inclusive-ends", "void.not-returned", "raw.note-arrives", "link.m-form",
                 "link.topup-form", "empty.rows-scanned", "empty.named-span", "limit.cut",
                 "nosheet.error", "readonly.no-writes", "route.get-ok", "route.params-pass"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


def test_build_passport():
    """База сборки = зеркало пофайлово, содержимое = паспорт, настроек проекта нет."""
    passport = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    mirror = json.loads(_read(os.path.join(MIRROR, "MIRROR.json")))
    assert passport["base_prod_version"] == mirror["prod_version"], \
        f"зеркало ушло на @{mirror['prod_version']}, сборка на @{passport['base_prod_version']} — пересобрать"
    assert "delivered_as_version" not in passport
    assert sorted(passport["changed"]) == ["BotData.js", "Bridge.js"]
    assert passport["added"] == []
    for name in passport["changed"]:
        base = passport["base_sha256"][name]
        assert base == mirror["files_sha256"][name] == _sha(os.path.join(MIRROR, name)), \
            f"{name}: база сборки разошлась с зеркалом"
        assert passport["build_sha256"][name] == _sha(os.path.join(BUILD, name)), \
            f"{name}: файл сборки разошёлся со своим паспортом"
    on_disk = sorted(os.listdir(BUILD))
    assert on_disk == sorted(passport["changed"] + passport["added"] + ["BUILD.json"]), on_disk
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))


def test_build_only_adds_to_mirror():
    """Сборка ничего не стирает у прода: BotData — только вставки; Bridge — вставки и одна
    правка строки help, где прежний список сохранён целиком."""
    for name in ("BotData.js", "Bridge.js"):
        old = _read(os.path.join(MIRROR, name)).splitlines()
        new = _read(os.path.join(BUILD, name)).splitlines()
        sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("equal", "insert"):
                continue
            assert name == "Bridge.js" and tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1, \
                f"{name}: {tag} {old[i1:i2]} → {new[j1:j2]}"
            assert "'get_pending'" in old[i1] and new[j1] == old[i1].replace(
                "'get_pending'", "'get_pending', 'tx_find'"), (old[i1], new[j1])


def _client_method():
    tree = ast.parse(_read(CLIENT))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BridgeClient")
    meth = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "tx_find"), None)
    assert meth is not None, "у BridgeClient нет метода tx_find"
    red = None
    for n in cls.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_REDZONE_ACTIONS" for t in n.targets):
            red = {e.value for e in n.value.elts if isinstance(e, ast.Constant)}
    return cls, meth, red


def test_client_method_is_get():
    cls, meth, red = _client_method()
    called = {n.func.attr for n in ast.walk(meth)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}
    assert called == {"_call"}, f"tx_find обязан ходить GET через _call, зовёт: {called}"
    assert red is not None and "tx_find" not in red, "чтение не место в чёрном ящике боевых записей"

    # исполнить ТЕКСТ метода на подставном self: что уходит в мост
    mod = ast.Module(body=[meth], type_ignores=[])
    ns = {"Optional": __import__("typing").Optional}
    exec(compile(mod, CLIENT, "exec"), ns)
    tx_find = ns["tx_find"]

    class Fake:
        def __init__(self):
            self.calls = []

        def _call(self, action, **params):
            self.calls.append((action, params))
            return {"ok": True}

        def _post(self, *a, **k):
            raise AssertionError("POST из read-only метода")

    f = Fake()
    tx_find(f, bike=" Nmax 6908 ", date_from="2026-10-01")
    assert f.calls == [("tx_find", {"bike": "Nmax 6908", "date_from": "2026-10-01"})], f.calls
    f = Fake()
    tx_find(f, booking_id="bk-1", date_to="03.10.2026", limit=5)
    assert f.calls == [("tx_find", {"booking_id": "bk-1", "date_to": "03.10.2026", "limit": 5})], f.calls
    f = Fake()
    tx_find(f)
    assert f.calls == [("tx_find", {})], f.calls   # отказ no_filter выносит мост, клиент не гадает


# мутант = (имя, файл, было, стало); каждый обязан покраснить харнесс
MUTANTS = [
    ("void-returned", "BotData.js",
     "if (String(r[ST]).toLowerCase() === 'void') { voided++; continue; }",
     "if (false) { voided++; continue; }"),
    ("bike-by-string", "BotData.js",
     "if (plate && plateOf_(String(r[BIKE] || '')) !== plate) continue;",
     "if (plate && String(r[BIKE] || '') !== bikeIn) continue;"),
    ("booking-ignored", "BotData.js",
     "if (booking && String(r[BKG]", "if (false && String(r[BKG]"),
    ("span-end-exclusive", "BotData.js",
     "if (to && day > to) continue;", "if (to && day >= to) continue;"),
    ("raw-dropped", "BotData.js",
     "raw: String(r[RAW] === null || r[RAW] === undefined ? '' : r[RAW]),",
     "raw: String(r[DESC] || ''),"),
    ("link-swapped", "BotData.js",
     "return m ? 'https://t.me/c/' + m[1] + '/' + m[2] : '';",
     "return m ? 'https://t.me/c/' + m[2] + '/' + m[1] : '';"),
    ("scanned-is-returned", "BotData.js",
     "rows_scanned: data.length,", "rows_scanned: items.length,"),
    ("row-off-by-one", "BotData.js",
     "items.push({\n      row: i + 2,", "items.push({\n      row: i + 1,"),
    ("day-from-recorded", "BotData.js",
     "var day = txFindDay_(r[MD], tz), src = 'msg_date';",
     "var day = txFindDay_(r[REC], tz), src = 'msg_date';"),
    ("limit-ignored", "BotData.js",
     "if (items.length >= limit) continue;", "if (false) continue;"),
    ("no-filter-allowed", "BotData.js",
     "if (!plate && !booking && !from && !to) return", "if (false) return"),
    ("tz-utc", "BotData.js",
     "try { return Session.getScriptTimeZone() || 'Asia/Bangkok'; }", "try { return 'UTC'; }"),
    ("route-drops-booking", "Bridge.js",
     "txFind({ bike: params.bike, booking_id: params.booking_id,",
     "txFind({ bike: params.bike, booking_id: '',"),
    ("route-missing", "Bridge.js", "case 'tx_find':", "case 'tx_find_x':"),
]


def test_mutants_killed():
    assert len(MUTANTS) >= 6
    alive = []
    for name, fname, old, new in MUTANTS:
        src = _read(os.path.join(BUILD, fname))
        assert src.count(old) == 1, f"мутант {name}: «было» встречается {src.count(old)} раз — мутант не о том"
        code, out, err = run_harness({fname: src.replace(old, new)})
        if code == 0:
            alive.append(name)
    assert not alive, f"мутанты выжили (харнесс их не видит): {alive}"


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
    print(f"tx_find: {len(tests) - bad}/{len(tests)} зелёных, мутантов {len(MUTANTS)}")
    sys.exit(1 if bad else 0)
