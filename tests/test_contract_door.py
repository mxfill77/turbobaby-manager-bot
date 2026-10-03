"""Дверь моста договоров TB e-Sign (CONTRACTDOOR0310, 03.10.2026) — read-only: contract_find
(договоры из реестра подписей по телефону, имени, байку и сроку) и contract_pdf (подписанный PDF
только из реестра и только из папки подписанных). Реальный код моста гоняется node-харнессом
tests/contract_door_gs_harness.js (способ tx_find_gs_harness.js): сборка `bridge_build_contract/`
поверх зеркала `bridge_prod/` (правило srcOf).

Покрытие: синтаксис файлов сборки; харнесс зелёный и несёт ключевые случаи (телефон, имя, байк,
два договора одного клиента, неподписанный, отозванный, чужой id PDF, пусто с числом
просмотренных); паспорт сборки против зеркала; сборка только ДОБАВЛЯЕТ к зеркалу; методы клиента —
GET (`_call`), в мост уходят только названные фильтры, PDF сверяется по длине и sha256; МУТАНТЫ —
каждый ловится харнессом (исходник подменяется через stdin, файлов не создаётся).

Методы клиента проверяются разбором исходника (ast) и исполнением ИХ ЖЕ текста на подставном
`self`: импорт bridge_client тянет `fcntl` и сеть, а у методов зависимостей нет — так тест идёт
одинаково на сервере и на ПК."""
import ast
import base64
import difflib
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "bridge_build_contract")
MIRROR = os.path.join(ROOT, "bridge_prod")
HARNESS = os.path.join(ROOT, "tests", "contract_door_gs_harness.js")
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
    for name in ("ContractDoor.js", "Bridge.js"):
        proc = subprocess.run(["node", "--check", os.path.join(BUILD, name)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_harness_all_green():
    code, out, err = harness()
    assert code == 0, f"харнесс красный:\nstdout={out[-3000:]}\nstderr={err[-2000:]}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 60, len(res["cases"])


def test_harness_covers_key_cases():
    code, out, err = harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    for need in ("phone.rows", "phone.via-nick", "name.any-order", "bike.by-plate",
                 "two.ambiguous", "two.by-term", "two.by-bike", "unsigned.none-signed",
                 "unsigned.partial-not-signed", "revoked.found-not-signed", "revoked.pdf-refused",
                 "pdf.sha256", "foreign.not-in-registry", "foreign.drive-not-touched",
                 "foreign.wrong-folder", "empty.rows-scanned", "empty.named-span",
                 "headers.by-name", "config.no-registry", "readonly.no-writes",
                 "route.find", "route.pdf", "route.token"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


def test_build_passport():
    """База сборки = зеркало пофайлово, содержимое = паспорт, настроек проекта нет."""
    passport = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    mirror = json.loads(_read(os.path.join(MIRROR, "MIRROR.json")))
    assert passport["base_prod_version"] == mirror["prod_version"], \
        f"зеркало ушло на @{mirror['prod_version']}, сборка на @{passport['base_prod_version']} — пересобрать"
    assert "delivered_as_version" not in passport
    assert passport["changed"] == ["Bridge.js"]
    assert passport["added"] == ["ContractDoor.js"]
    assert not os.path.exists(os.path.join(MIRROR, "ContractDoor.js")), "новый файл уже в зеркале?"
    for name in passport["changed"]:
        base = passport["base_sha256"][name]
        assert base == mirror["files_sha256"][name] == _sha(os.path.join(MIRROR, name)), \
            f"{name}: база сборки разошлась с зеркалом"
    for name in passport["changed"] + passport["added"]:
        assert passport["build_sha256"][name] == _sha(os.path.join(BUILD, name)), \
            f"{name}: файл сборки разошёлся со своим паспортом"
    on_disk = sorted(os.listdir(BUILD))
    assert on_disk == sorted(passport["changed"] + passport["added"] + ["BUILD.json"]), on_disk
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))


def test_build_only_adds_to_mirror():
    """Bridge.js сборки: только вставки и одна правка строки help, где прежний список сохранён."""
    old = _read(os.path.join(MIRROR, "Bridge.js")).splitlines()
    new = _read(os.path.join(BUILD, "Bridge.js")).splitlines()
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    replaced = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("equal", "insert"):
            continue
        assert tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1, f"{tag} {old[i1:i2]} → {new[j1:j2]}"
        assert "'get_pending'" in old[i1] and new[j1] == old[i1].replace(
            "'get_pending'", "'get_pending', 'contract_find', 'contract_pdf'"), (old[i1], new[j1])
        replaced += 1
    assert replaced == 1, replaced


def test_door_has_no_writes():
    """В новом файле нет ни одного пишущего вызова Apps Script (харнесс считает живые записи,
    здесь — страховка по тексту)."""
    src = _read(os.path.join(BUILD, "ContractDoor.js"))
    for bad in ("setValue", "setValues", "appendRow", "insertSheet", "deleteRow", "setProperty",
                "setTrashed", "moveTo", "createFile", "makeCopy", "setContent", "addEditor",
                "UrlFetchApp", "MailApp", "GmailApp"):
        assert bad not in src, f"в двери чтения есть {bad}"


def _client_methods():
    tree = ast.parse(_read(CLIENT))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BridgeClient")
    meths = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)
             and n.name in ("contract_find", "contract_pdf")}
    assert set(meths) == {"contract_find", "contract_pdf"}, f"у BridgeClient нет методов: {set(meths)}"
    red = None
    for n in cls.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_REDZONE_ACTIONS" for t in n.targets):
            red = {e.value for e in n.value.elts if isinstance(e, ast.Constant)}
    ns = {"Optional": __import__("typing").Optional}
    exec(compile(ast.Module(body=list(meths.values()), type_ignores=[]), CLIENT, "exec"), ns)
    return meths, red, ns


class _Fake:
    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply if reply is not None else {"ok": True}

    def _call(self, action, **params):
        self.calls.append((action, params))
        return self.reply

    def _post(self, *a, **k):
        raise AssertionError("POST из read-only метода")


def test_client_methods_are_get():
    meths, red, ns = _client_methods()
    for name, meth in meths.items():
        called = {n.func.attr for n in ast.walk(meth)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}
        assert called == {"_call"}, f"{name} обязан ходить GET через _call, зовёт: {called}"
        assert red is not None and name not in red, "чтение не место в чёрном ящике боевых записей"

    f = _Fake()
    ns["contract_find"](f, phone=" +66 81 234 5678 ", date_from="2026-09-15")
    assert f.calls == [("contract_find", {"phone": "+66 81 234 5678", "date_from": "2026-09-15"})], f.calls
    f = _Fake()
    ns["contract_find"](f, name="Ivan", bike="Nmax 6908", date_to="30.09.2026", limit=5)
    assert f.calls == [("contract_find", {"name": "Ivan", "bike": "Nmax 6908", "date_to": "30.09.2026",
                                          "limit": 5})], f.calls
    f = _Fake()
    ns["contract_find"](f)
    assert f.calls == [("contract_find", {})], f.calls   # отказ no_filter выносит мост, клиент не гадает
    f = _Fake({"ok": False, "error": "not_in_registry"})
    out = ns["contract_pdf"](f, " pdfA0000000000000000000000001 ")
    assert f.calls == [("contract_pdf", {"id": "pdfA0000000000000000000000001"})], f.calls
    assert out == {"ok": False, "error": "not_in_registry"}, out   # отказ моста — как есть


def test_client_pdf_verified():
    """Клиент декодирует содержимое и сверяет длину и sha256 с ответом моста."""
    _, _, ns = _client_methods()
    raw = b"%PDF-1.7\n\xe2\xe3\xcf\xd3contract A"
    good = {"ok": True, "id": "x" * 28, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "content_b64": base64.b64encode(raw).decode()}
    out = ns["contract_pdf"](_Fake(dict(good)), "x" * 28)
    assert out["ok"] is True and out["verified"] is True, out
    bad_sha = dict(good, sha256="0" * 64)
    out = ns["contract_pdf"](_Fake(bad_sha), "x" * 28)
    assert out["ok"] is False and out["error"] == "pdf_mismatch" and out["verified"] is False, out
    bad_len = dict(good, size=len(raw) + 1)
    out = ns["contract_pdf"](_Fake(bad_len), "x" * 28)
    assert out["ok"] is False and out["error"] == "pdf_mismatch", out
    broken = dict(good, content_b64="!!не base64!!")
    out = ns["contract_pdf"](_Fake(broken), "x" * 28)
    assert out["ok"] is False and out["error"] == "pdf_mismatch", out


# мутант = (имя, файл, было, стало); каждый обязан покраснить харнесс
MUTANTS = [
    ("signed-by-prefix", "ContractDoor.js",
     "return esignNorm_(status).toUpperCase() === ESIGN.SIGNED_STATUS;",
     "return esignNorm_(status).toUpperCase().indexOf(ESIGN.SIGNED_STATUS) === 0;"),
    ("ambiguous-picks-first", "ContractDoor.js",
     "else if (signed.length > 1) outcome = 'ambiguous';", "else if (false) outcome = 'ambiguous';"),
    ("phone-all-digits", "ContractDoor.js",
     "phone = d.slice(-ESIGN.PHONE_DIGITS);", "phone = d;"),
    ("nick-ignored", "ContractDoor.js",
     "else if (c.nick !== undefined &&", "else if (false &&"),
    ("pdf-registry-skipped", "ContractDoor.js",
     "if (!rows.length) return { ok: false, error: 'not_in_registry',",
     "if (false) return { ok: false, error: 'not_in_registry',"),
    ("pdf-unsigned-allowed", "ContractDoor.js",
     "if (!signedRows.length) return { ok: false, error: 'not_signed',",
     "if (false) return { ok: false, error: 'not_signed',"),
    ("pdf-folder-skipped", "ContractDoor.js",
     "if (!inFolder) return", "if (false) return"),
    ("pdf-trashed-allowed", "ContractDoor.js",
     "if (file.isTrashed()) return", "if (false) return"),
    ("pdf-size-ignored", "ContractDoor.js",
     "if (size > ESIGN.PDF_MAX_BYTES) return", "if (false) return"),
    ("pdf-sha-wrong", "ContractDoor.js",
     "esignHex_(Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes))",
     "esignHex_(bytes.slice(0, 32))"),
    ("bike-by-string", "ContractDoor.js",
     "if (plateOf_(String(r[c.bike] || '')) !== plate) continue;",
     "if (String(r[c.bike] || '') !== bikeIn) continue;"),
    ("span-end-exclusive", "ContractDoor.js",
     "if (to && day > to) continue;", "if (to && day >= to) continue;"),
    ("scanned-is-matched", "ContractDoor.js",
     "rows_scanned: data.length,", "rows_scanned: matched.length,"),
    ("rich-link-ignored", "ContractDoor.js",
     "pdfIds[i] = esignFileId_(link) || esignFileId_(", "pdfIds[i] = esignFileId_("),
    ("no-filter-allowed", "ContractDoor.js",
     "if (!phone && !qWords.length && !plate) return", "if (false) return"),
    ("created-fallback-dropped", "ContractDoor.js",
     "if (!day && c.created !== undefined) {", "if (false) {"),
    ("row-off-by-one", "ContractDoor.js",
     "matched.push({\n      row: i + 2,", "matched.push({\n      row: i + 1,"),
    ("route-find-missing", "Bridge.js", "case 'contract_find':", "case 'contract_find_x':"),
    ("route-pdf-drops-id", "Bridge.js", "contractPdf({ id: params.id })", "contractPdf({ id: '' })"),
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
    print(f"contract_door: {len(tests) - bad}/{len(tests)} зелёных, мутантов {len(MUTANTS)}")
    sys.exit(1 if bad else 0)
