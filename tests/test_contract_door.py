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
одинаково на сервере и на ПК.

CONTRACTFIX0410 (04.10.2026): неизвестный день строки не даёт уверенного единственного ответа —
секция 18 харнесса (контрпример Codex TB-CHECK-0410-0025 п.1 → incomplete; 31.02.2026 → unparsed;
created только при пустой дате договора; pick — полная запись), мутант на каждое правило, docstring
клиента называет incomplete и полноту.

MIRROR88 (13.10.2026): дверь в проде с @85, переделана @86 (ESIGNDOOR0410: адреса поиском по имени,
PDF в «Подписанные/ГГГГ/ММ»), дата договора ДД-ММ-ГГГГ — @88 (P5). Зеркало сведено к @88, каталог сборки
переведён в состояние «выложено» (delivered_as_version 88, файлы == зеркалу) и судится ОБЩИМ правилом трёх
состояний `tests/build_states.py`; харнесс — секции 19 (живые даты) и 20 (поиск и уровни папки), мутанты
на правила @86 и P5.

ESIGNLINK2510 (25.10.2026): новая стройка двери — в СВОЁМ каталоге сборки `bridge_build_esign_link/` (состояние «а»
поверх зеркала @88), `bridge_build_contract/` остаётся следом выложенной сборки и судится прежними тестами паспорта.
Код двери (харнесс, мутанты, страж записей) берётся по правилу srcOf: каталог сборки захода → зеркало. Поля записи
sign_url («Ссылка клиенту на подпись») и doc_url («Ссылка на документ») — необязательные колонки; фильтр doc_id;
харнесс — секция 21, мутант на каждое правило; Bridge.js сборки отличается от зеркала РОВНО строкой маршрута
contract_find (довозит doc_id)."""
import ast
import base64
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_states                                                    # noqa: E402  (правило трёх состояний)

BUILD = os.path.join(ROOT, "bridge_build_contract")          # след выложенной сборки @88 (паспорт)
LINK_BUILD = os.path.join(ROOT, "bridge_build_esign_link")   # каталог сборки захода ESIGNLINK2510
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


def src_path(name):
    """Правило srcOf харнесса: файл есть в каталоге сборки захода — он, иначе зеркало прода."""
    p = os.path.join(LINK_BUILD, name)
    return p if os.path.exists(p) else os.path.join(MIRROR, name)


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
    for path in [os.path.join(BUILD, n) for n in ("ContractDoor.js", "Bridge.js")] + \
            [src_path(n) for n in ("ContractDoor.js", "Bridge.js")]:
        proc = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{path}: {proc.stderr}"


def test_harness_all_green():
    code, out, err = harness()
    assert code == 0, f"харнесс красный:\nstdout={out[-3000:]}\nstderr={err[-2000:]}"
    res = json.loads(out)
    failed = [c for c in res["cases"] if not c["pass"]]
    assert not failed, json.dumps(failed, ensure_ascii=False, indent=1)
    assert len(res["cases"]) >= 169, len(res["cases"])   # MIRROR88: 149; ESIGNLINK2510: + секция 21 (18 + 2 r2)


def test_harness_covers_key_cases():
    code, out, err = harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    for need in ("phone.rows", "phone.via-nick", "name.any-order", "bike.by-plate",
                 "two.ambiguous", "two.by-term", "two.by-bike", "unsigned.none-signed",
                 "unsigned.partial-not-signed", "revoked.found-not-signed", "revoked.pdf-refused",
                 "pdf.sha256", "foreign.not-in-registry", "foreign.drive-not-touched",
                 "foreign.wrong-folder", "empty.rows-scanned", "empty.named-span",
                 "headers.by-name", "config.no-registry", "readonly.no-writes",
                 "route.find", "route.pdf", "route.token",
                 # CONTRACTFIX0410 — отрицательные случаи неизвестного дня
                 "fix.counterexample-incomplete", "fix.counterexample-not-one", "fix.feb31-unparsed",
                 "fix.unparsed-no-created", "fix.empty-uses-created", "fix.pick-full-record",
                 "fix.unsigned-undated-keeps-one", "fix.no-term-keeps-undated", "fix.unread-rich",
                 "fix.ambiguous-over-incomplete", "fix.route-incomplete", "fix.readonly-no-writes",
                 # LIVEDATE1210 (P5 @88): живой формат «Дата договора» ДД-ММ-ГГГГ и отрицательные близнецы
                 "live.day 22-09-2026", "live.term-one 25-09-2026", "live.day 22-09-2026 17:26",
                 "live.neg-unparsed 31-02-2026", "live.neg-unparsed 22-09-2026x",
                 "live.neg-term-incomplete 2026-13-01", "live.term-outside-none", "live.pdf-contract-date",
                 "live.readonly-no-writes",
                 # ESIGNDOOR0410 (@86): адреса поиском и уровни папки подписанных (MIRROR88)
                 "search.property-no-drive-search", "search.registry-one", "search.folder-one",
                 "search.folder-ambiguous", "search.folder-trashed-ignored", "search.registry-ambiguous",
                 "search.ambiguous-pdf-refused", "search.lookup-failed-named",
                 "search.folder-lookup-failed-named", "levels.three-ok", "levels.four-refused",
                 "levels.unreadable-refused", "levels.restored-twin", "search.readonly-no-writes",
                 # ESIGNLINK2510: ссылка клиенту на подпись и ссылка на документ — необязательные колонки, фильтр doc_id
                 "link.by-doc-id", "link.columns-present", "link.by-doc-url", "link.doc-id-exact",
                 "link.doc-id-prefix-none", "link.doc-and-name", "link.sent-new-column", "link.signed-no-sign-url",
                 "link.old-column-not-taken", "link.phone-carries-fields", "link.headers-by-name",
                 "link.route-doc-id", "link.bad-doc-id", "link.old-registry-works", "link.no-optional-columns",
                 "link.no-doc-column-refused", "link.base-registry-empty", "link.readonly-no-writes",
                 # ESIGNLINK2510 r2: аннулированный договор — ссылки на подпись нет
                 "link.canceled-no-sign-url", "link.canceled-case-space"):
        assert need in names, f"нет кейса {need}: {sorted(names)}"


def test_build_passport():
    """Паспорт сборки против зеркала — по правилу ТРЁХ состояний (`tests/build_states.py`).

    До MIRROR88 здесь жило одно состояние («не выложено, база == зеркалу») и `delivered_as_version`
    был запрещён — 13.10.2026 на сведении зеркала @84 → @88 тест покраснел «зеркало ушло на @88, сборка
    на @84 — пересобрать», хотя дверь в проде с @85. Теперь сборка в состоянии «б» (выложена как @88,
    каждый файл побайтно == зеркалу); прод уедет дальше — состояние «в», начнут строить новое — «а»."""
    passport = json.loads(_read(os.path.join(BUILD, "BUILD.json")))
    assert passport["changed"] == ["Bridge.js"]
    assert passport["added"] == ["ContractDoor.js"]
    res = build_states.judge(BUILD, MIRROR)
    assert not res["problems"], res
    assert res["state"] in ("a", "b", "c"), res
    if res["state"] == "a":
        assert not os.path.exists(os.path.join(MIRROR, "ContractDoor.js")), "новый файл уже в зеркале?"
    else:
        assert os.path.exists(os.path.join(MIRROR, "ContractDoor.js")), \
            "сборка объявлена выложенной, а двери в зеркале нет — зеркало отстало от прода"
    assert not os.path.exists(os.path.join(BUILD, ".clasp.json"))


def test_build_only_adds_to_mirror():
    """Bridge.js сборки: только вставки и одна правка строки help, где прежний список сохранён.

    Это правило НЕ ВЫЛОЖЕННОЙ сборки (её дельта к базе-зеркалу). У выложенной база ушла в историю git
    (зеркало @84 — коммит c89c7f4), а сверяется сильнее: в состоянии «б» файлы сборки побайтно равны
    зеркалу, и маршруты двери живут в зеркале, то есть в проде."""
    res = build_states.judge(BUILD, MIRROR)
    if res["state"] in ("b", "c"):
        mbr = _read(os.path.join(MIRROR, "Bridge.js"))
        for need in ("case 'contract_find':", "case 'contract_pdf':", "contractPdf({ id: params.id })",
                     "'contract_find', 'contract_pdf'"):
            assert need in mbr, f"в зеркале прода нет {need!r} — дверь выложенной не выглядит"
        if res["state"] == "b":
            for name in ("Bridge.js", "ContractDoor.js"):
                assert _sha(os.path.join(BUILD, name)) == _sha(os.path.join(MIRROR, name)), name
        return
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


def test_link_build_passport():
    """ESIGNLINK2510: каталог сборки захода — по правилу трёх состояний; до выкладки «а» (база == зеркало @88)."""
    passport = json.loads(_read(os.path.join(LINK_BUILD, "BUILD.json")))
    assert passport["changed"] == ["Bridge.js", "ContractDoor.js"], passport["changed"]
    assert passport["added"] == [], passport["added"]
    res = build_states.judge(LINK_BUILD, MIRROR)
    assert not res["problems"], res
    assert res["state"] in ("a", "b", "c"), res
    assert not os.path.exists(os.path.join(LINK_BUILD, ".clasp.json"))


def test_link_build_bridge_delta():
    """Bridge.js сборки ESIGNLINK2510 против базы-зеркала: РОВНО одна строка — маршрут contract_find довозит doc_id,
    прежние параметры на месте (правило невыложенной сборки; после выкладки файлы == зеркалу и сверять нечего)."""
    res = build_states.judge(LINK_BUILD, MIRROR)
    if res["state"] != "a":
        return
    old = _read(os.path.join(MIRROR, "Bridge.js")).splitlines()
    new = _read(os.path.join(LINK_BUILD, "Bridge.js")).splitlines()
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    diffs = [op for op in sm.get_opcodes() if op[0] != "equal"]
    assert len(diffs) == 1, diffs
    tag, i1, i2, j1, j2 = diffs[0]
    assert tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1, diffs
    assert new[j1] == old[i1].replace("bike: params.bike,", "bike: params.bike, doc_id: params.doc_id,"), (old[i1], new[j1])
    assert "contractFind({" in old[i1]


def _js_functions(text):
    """Верхнеуровневые функции файла моста: имя → текст от `function имя(` до закрывающей `}` в начале строки
    (комментарии между функциями не в счёт — их правка не правка функции)."""
    out, cur, name = {}, [], None
    for line in text.splitlines():
        m = re.match(r"^function (\w+)\(", line)
        if m:
            name, cur = m.group(1), []
        if name:
            cur.append(line)
            if line == "}":
                out[name] = "\n".join(cur)
                name = None
    return out


def test_link_door_only_contract_find_changed():
    """ContractDoor.js сборки: contractPdf и все помощники, кроме contractFind, побайтно прежние (ссылки нужны поиску,
    PDF-дверь ими не пользуется); добавлен ровно один помощник — esignIsCanceled_ (r2: статус «АННУЛИРОВАН»)."""
    res = build_states.judge(LINK_BUILD, MIRROR)
    if res["state"] != "a":
        return
    old = _js_functions(_read(os.path.join(MIRROR, "ContractDoor.js")))
    new = _js_functions(_read(os.path.join(LINK_BUILD, "ContractDoor.js")))
    assert set(new) - set(old) == {"esignIsCanceled_"} and set(old) <= set(new), set(old) ^ set(new)
    changed = sorted(n for n in old if old[n] != new[n])
    assert changed == ["contractFind"], changed


def test_door_has_no_writes():
    """В новом файле нет ни одного пишущего вызова Apps Script (харнесс считает живые записи,
    здесь — страховка по тексту)."""
    src = _read(src_path("ContractDoor.js"))
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
    f = _Fake()                                           # ESIGNLINK2510: id документа доезжает до моста как есть
    ns["contract_find"](f, doc_id=" 1LinkNew0000000000000000000000000000000000001 ", limit=5)
    assert f.calls == [("contract_find", {"doc_id": "1LinkNew0000000000000000000000000000000000001",
                                          "limit": 5})], f.calls
    f = _Fake({"ok": False, "error": "not_in_registry"})
    out = ns["contract_pdf"](f, " pdfA0000000000000000000000001 ")
    assert f.calls == [("contract_pdf", {"id": "pdfA0000000000000000000000001"})], f.calls
    assert out == {"ok": False, "error": "not_in_registry"}, out   # отказ моста — как есть


def test_client_find_doc_names_incomplete():
    """CONTRACTFIX0410: docstring contract_find называет исход incomplete, его причину, полноту
    ответа и полную запись pick — агент читает контракт отсюда, а не из кода моста."""
    meths, _, ns = _client_methods()
    doc = ast.get_docstring(meths["contract_find"]) or ""
    for need in ("`incomplete`", "undated_signed", "`reason`", "checked.complete", "`unread`",
                 "`undated`", "undated_items", "date_unparsed", "contract_date_raw", "unparsed",
                 "pdf_ready", "полная запись", "ПУСТОЙ ячейке", "31.02.2026"):
        assert need in doc, f"docstring contract_find не называет {need!r}"
    for old in ("one", "ambiguous", "none_signed", "none"):
        assert f"`{old}`" in doc, f"прежний исход {old} пропал из docstring"
    # исход incomplete клиент не прячет и не переписывает: ответ моста — как есть
    reply = {"ok": True, "outcome": "incomplete", "pick": None,
             "reason": {"code": "undated_signed", "rows": [3], "message": "m"},
             "checked": {"complete": False, "undated": 1, "undated_signed": 1}}
    f = _Fake(reply)
    out = ns["contract_find"](f, phone="0815550001", date_from="2026-09-01", date_to="2026-09-30")
    assert out is reply and out["outcome"] == "incomplete" and out["pick"] is None, out
    assert f.calls == [("contract_find", {"phone": "0815550001", "date_from": "2026-09-01",
                                          "date_to": "2026-09-30"})], f.calls


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
    # MIRROR88: «было» сдвинуто вслед за кодом @86 (проверка папки переехала в esignInSignedFolder_), суть та же
    ("pdf-folder-skipped", "ContractDoor.js",
     "if (!inDir.ok) return inDir;", "if (false) return inDir;"),
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
    # ESIGNLINK2510: «было» сдвинуто вслед за кодом (в условие добавлен фильтр doc_id), суть та же
    ("no-filter-allowed", "ContractDoor.js",
     "if (!phone && !qWords.length && !plate && !docId) return", "if (false) return"),
    # CONTRACTFIX0410: «было» двух прежних мутантов сдвинуто вслед за кодом (подстановка created
    # переехала в esignRowDate_, запись строки — в rec), суть мутации та же
    ("created-fallback-dropped", "ContractDoor.js",
     "} else if (createdRaw) {", "} else if (false) {"),
    ("row-off-by-one", "ContractDoor.js",
     "var rec = {\n      row: i + 2,", "var rec = {\n      row: i + 1,"),
    ("route-find-missing", "Bridge.js", "case 'contract_find':", "case 'contract_find_x':"),
    ("route-pdf-drops-id", "Bridge.js", "contractPdf({ id: params.id })", "contractPdf({ id: '' })"),
    # ── CONTRACTFIX0410: по мутанту на каждое правило ──
    # П1: день только при верной календарной дате
    ("fix-calendar-dropped", "ContractDoor.js",
     "return esignCalendar_(+y, +mo, +d) ? y + '-' + mo + '-' + d : '';", "return y + '-' + mo + '-' + d;"),
    # П2: created только при ПУСТОЙ дате договора (мутант = прежнее поведение: при неразобранной — тоже)
    ("fix-created-on-unparsed", "ContractDoor.js",
     "  if (raw) {\n    var d = esignDay_(r[c.contract_date], tz);",
     "  if (raw && esignDay_(r[c.contract_date], tz)) {\n    var d = esignDay_(r[c.contract_date], tz);"),
    ("fix-unparsed-called-none", "ContractDoor.js",
     "out.src = d ? 'contract_date' : 'unparsed';", "out.src = d ? 'contract_date' : 'none';"),
    ("fix-raw-dropped", "ContractDoor.js",
     "contract_date_raw: dt.raw,", "contract_date_raw: day || '',"),
    # П3: при сроке неизвестный день не выпадает молча; подписанный среди них → incomplete
    ("fix-undated-dropped", "ContractDoor.js",
     "if (!day) { aside.push(rec); continue; }", "if (!day) { continue; }"),
    ("fix-undated-signed-ignored", "ContractDoor.js",
     "if (asideSigned.length && signed.length <= 1) {", "if (false) {"),
    ("fix-incomplete-over-ambiguous", "ContractDoor.js",
     "if (asideSigned.length && signed.length <= 1) {", "if (asideSigned.length) {"),
    ("fix-unsigned-undated-blocks", "ContractDoor.js",
     "var asideSigned = aside.filter(function (x) { return x.signed; });", "var asideSigned = aside.slice();"),
    ("fix-no-term-drops-undated", "ContractDoor.js",
     "    if (from || to) {\n      // день неизвестен", "    if (true) {\n      // день неизвестен"),
    ("fix-unparsed-not-counted", "ContractDoor.js",
     "if (dt.src === 'unparsed') unparsed++;", "if (false) unparsed++;"),
    # полнота: строки без дня и непрочитанный реестр
    ("fix-complete-ignores-undated", "ContractDoor.js",
     "complete: !aside.length && !unread.length,", "complete: !unread.length,"),
    ("fix-unread-rich-hidden", "ContractDoor.js",
     "catch (e) { rich = null; unread.push('pdf_rich_text'); }", "catch (e) { rich = null; }"),
    ("fix-unread-formulas-hidden", "ContractDoor.js",
     "catch (e) { frm = null; unread.push('pdf_formulas'); }", "catch (e) { frm = null; }"),
    ("fix-rows-short-hidden", "ContractDoor.js",
     "if (data.length < n) unread.push('rows_short');", ""),
    # П4: pick — полная запись плюс pdf_ready (мутант = прежний тонкий pick)
    ("fix-pick-thin", "ContractDoor.js",
     "pick = Object.assign({}, signed[0], { pdf_ready: !!signed[0].pdf_id });",
     "pick = { row: signed[0].row, doc_id: signed[0].doc_id, pdf_id: signed[0].pdf_id, pdf_ready: !!signed[0].pdf_id };"),
    # ── MIRROR88: правила двери @86 (ESIGNDOOR0410) — адреса поиском и уровни папки подписанных ──
    ("search-registry-takes-first", "ContractDoor.js",
     "if (found.length !== 1) return { ok: false, error: found.length ? 'registry_ambiguous'",
     "if (found.length < 1) return { ok: false, error: found.length ? 'registry_ambiguous'"),
    ("search-folder-takes-first", "ContractDoor.js",
     "if (found.length !== 1) return { ok: false, error: found.length ? 'signed_folder_ambiguous'",
     "if (found.length < 1) return { ok: false, error: found.length ? 'signed_folder_ambiguous'"),
    ("search-registry-trashed-counted", "ContractDoor.js",
     "return !f.isTrashed() && String(f.getMimeType()) === ESIGN.REGISTRY_MIME;",
     "return String(f.getMimeType()) === ESIGN.REGISTRY_MIME;"),
    ("search-registry-mime-ignored", "ContractDoor.js",
     "return !f.isTrashed() && String(f.getMimeType()) === ESIGN.REGISTRY_MIME;", "return !f.isTrashed();"),
    ("search-folder-trashed-counted", "ContractDoor.js",
     "if (!f.isTrashed() && !seen[f.getId()])", "if (!seen[f.getId()])"),
    ("search-property-ignored", "ContractDoor.js",
     "getProperty(ESIGN.REGISTRY_PROP);\n  if (id) return", "getProperty(ESIGN.REGISTRY_PROP);\n  if (false) return"),
    ("search-folder-without-registry", "ContractDoor.js",
     "if (!regAddr.ok) return regAddr;", "if (false) return regAddr;"),
    ("levels-too-short", "ContractDoor.js", "SIGNED_FOLDER_LEVELS: 3,", "SIGNED_FOLDER_LEVELS: 2,"),
    ("levels-too-deep", "ContractDoor.js", "SIGNED_FOLDER_LEVELS: 3,", "SIGNED_FOLDER_LEVELS: 4,"),
    ("levels-unreadable-passes", "ContractDoor.js",
     "return { ok: false, error: 'parents_unreadable', level: level,",
     "return { ok: true, error: 'parents_unreadable', level: level,"),
    # ── MIRROR88: ремонт даты P5 @88 (LIVEDATE1210) ──
    ("p5-dash-dropped", "ContractDoor.js",
     r"else if ((m = s.match(/^(\d{2})([-\/])(\d{2})\2(\d{4})(?:$|[ ,T])/))) { y = m[4]; mo = m[3]; d = m[1]; }",
     "else if (false) { }"),
    ("p5-tail-garbage-accepted", "ContractDoor.js", r"(\d{4})(?:$|[ ,T])/)))", r"(\d{4})/)))"),
    ("p5-day-month-swapped", "ContractDoor.js",
     "{ y = m[4]; mo = m[3]; d = m[1]; }", "{ y = m[4]; mo = m[1]; d = m[3]; }"),
    # ── ESIGNLINK2510: по мутанту на каждое правило ──
    ("link-column-required", "ContractDoor.js",
     "NEED: ['client', 'contract_date', 'status', 'signed_at', 'pdf', 'phone', 'bike'],",
     "NEED: ['client', 'contract_date', 'status', 'signed_at', 'pdf', 'phone', 'bike', 'sign_url'],"),
    ("link-old-column-taken", "ContractDoor.js",
     "sign_url: 'Ссылка клиенту на подпись',", "sign_url: 'Ссылка «на подпись»',"),
    # r2: «было» сдвинуто вслед за кодом (ссылку гасит linkDead — подписан ИЛИ аннулирован), суть та же
    ("link-signed-shows-url", "ContractDoor.js",
     "var linkDead = isSigned || esignIsCanceled_(r[c.status]);", "var linkDead = esignIsCanceled_(r[c.status]);"),
    ("link-canceled-shows-url", "ContractDoor.js",
     "var linkDead = isSigned || esignIsCanceled_(r[c.status]);", "var linkDead = isSigned;"),
    ("link-canceled-exact-case", "ContractDoor.js",
     "return esignNorm_(status).toUpperCase() === ESIGN.CANCELED_STATUS;",
     "return String(status) === ESIGN.CANCELED_STATUS;"),
    ("link-not-trimmed", "ContractDoor.js",
     "String(r[c.sign_url] || '').trim() : ''", "String(r[c.sign_url] || '') : ''"),
    ("link-doc-url-dropped", "ContractDoor.js",
     "doc_url: c.doc_url !== undefined ?", "doc_url: false ?"),
    ("link-doc-filter-ignored", "ContractDoor.js",
     "if (String(r[c.doc_id] || '').trim() !== docId) continue;", "if (false) continue;"),
    ("link-doc-filter-prefix", "ContractDoor.js",
     "if (String(r[c.doc_id] || '').trim() !== docId) continue;",
     "if (String(r[c.doc_id] || '').trim().indexOf(docId) !== 0) continue;"),
    ("link-doc-url-not-parsed", "ContractDoor.js",
     "docId = esignFileId_(docIn);", r"docId = /^[-\w]{25,}$/.test(docIn) ? docIn : '';"),
    ("link-bad-doc-silent", "ContractDoor.js",
     "if (!docId) return { ok: false, error: 'bad_doc_id',", "if (false) return { ok: false, error: 'bad_doc_id',"),
    ("link-no-doc-column-silent", "ContractDoor.js",
     "if (docId && c.doc_id === undefined) return", "if (false) return"),
    ("link-columns-flag-lies", "ContractDoor.js",
     "o[k] = c[k] !== undefined; return o;", "o[k] = true; return o;"),
    ("link-route-drops-doc-id", "Bridge.js", "doc_id: params.doc_id,", "doc_id: '',"),
]


def test_mutants_killed():
    assert len(MUTANTS) >= 6
    alive = []
    for name, fname, old, new in MUTANTS:
        src = _read(src_path(fname))
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
