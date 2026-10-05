# -*- coding: utf-8 -*-
"""AGENTFIX0410 (Т4а, часть 1): договор агент берёт фактом только из настоящего ответа двери, только при полноте и только
для клиента и аренды текущего обращения.

Сквозной контракт: ответы двери договоров снимает её же харнесс (tests/contract_door_gs_harness.js --snap, код
f8276398 из bridge_build_contract/), PDF проходит настоящий `bridge_client.BridgeClient.contract_pdf` (сверка длины и
sha256), аренду читает настоящая дверь адаптера (`ModelAdapter._tool_doors` → rental) из снимка броней. Выдуманных
полей в подменах нет: строка брони — те же ключи, что у листа «клиенты» в остальных тестах агента.

Мутанты: на каждое правило — правка исходника `wa_agent_tools.py` в памяти; мутант обязан уронить хотя бы один случай
(число падений печатается). Мутанты двери (вход, а не проверяемый код) — правка ContractDoor.js через --stdin харнесса.
Модели, моста, Telegram, WhatsApp, сети и SQLite здесь нет."""

import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))
    # bridge_client берёт fcntl для замков своих файлов; contract_pdf его не зовёт — на ПК достаточно имени модуля
    sys.modules.setdefault("fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_SH=1, LOCK_UN=8, LOCK_NB=4,
                                                          flock=lambda *a, **k: None))

import bridge_client               # noqa: E402
import contract_door_snaps as S     # noqa: E402
import wa_agent_model as M          # noqa: E402
import wa_agent_tools as T_REAL     # noqa: E402

TOOLS_SRC = os.path.join(ROOT, "wa_agent_tools.py")

NUM_IVAN, NUM_NINA, NUM_OLEG = "66812345678", "66815550004", "66815550005"
NUM_ANNA, NUM_JOHN = "66897654321", "447700900123"
PDF_B, PDF_C = "pdfB0000000000000000000000002", "pdfC0000000000000000000000003"


# ------------------------------- подмены -------------------------------

class Clock:
    def __init__(self, t=1790000000.0):
        self.t = t

    def __call__(self):
        return self.t


class Script:
    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return json.dumps(a, ensure_ascii=False), {"in": 1, "out": 1}


class Book:
    def __init__(self, rows):
        self.rows = rows

    def get(self, now):
        return self.rows, [], 60, ""


def row(contacts, bike, ds, de, booking="bk-1"):
    """Строка листа «клиенты» — ключи, которыми живёт снимок броней (wa_book_read)."""
    return {"status": "В аренде", "contacts": contacts, "bike": bike, "booking_id": booking,
            "date_start": ds, "date_end": de}


def rental(T, r):
    return T.rental_result({"ok": True, "rows": [r] if r else []})


def pdf_client():
    """Настоящий клиентский метод contract_pdf; `_call` отдаёт ответ contractPdf, снятый харнессом."""
    snaps = S.snaps()
    by_id = {PDF_B: snaps["pdf_b"], PDF_C: snaps["pdf_c"]}
    c = object.__new__(bridge_client.BridgeClient)
    c._call = lambda action, **p: json.loads(json.dumps(
        by_id.get(p.get("id"), {"ok": False, "error": "not_in_registry"})))
    return c


def doors_for(number, book_rows, contract_table):
    """Двери сверки: rental и history — настоящие двери адаптера, contract — снимок харнесса по аргументам модели,
    contract_pdf — настоящий клиент. Аргументы модели дверь договоров получает как есть."""
    a = M.ModelAdapter(":memory:-не-открывается", lambda s, u: ("{}", {}), read_doc=None, clock=Clock(),
                       log=lambda *_: None, book=Book(book_rows), tools={}, fresh=None)
    a._history = lambda n, u: ([], [])
    doors = a._tool_doors(number, 5)
    seen = []

    def contract(**kw):
        seen.append(dict(kw))
        key = T_REAL.last9(kw.get("phone")) or kw.get("name") or ""
        return json.loads(json.dumps(contract_table[key]))
    doors["contract"] = contract
    doors["contract_pdf"] = pdf_client().contract_pdf
    return doors, seen


def final(text):
    return {"text": text, "handoff": [], "lang": "ru", "why": "тест"}


# ------------------------------- мутанты двери (вход) -------------------------------

def door_mutant(old, new):
    src = S.source("ContractDoor.js")
    assert src.count(old) == 1, "мутант двери не применился: %r" % old
    return {"ContractDoor.js": src.replace(old, new)}


DOOR_NO_INCOMPLETE = ("  if (asideSigned.length && signed.length <= 1) {", "  if (false) {")
DOOR_NO_FIELDS = ("      undated_signed: asideSigned.length,\n      date_unparsed: unparsed,\n      unread: unread,\n",
                  "      date_unparsed: unparsed,\n")
DOOR_UNSIGNED_PICK = ("pick = Object.assign({}, signed[0], { pdf_ready: !!signed[0].pdf_id });",
                      "pick = Object.assign({}, matched[0], { pdf_ready: !!matched[0].pdf_id });")


# ------------------------------- случаи (T — проверяемый модуль) -------------------------------

def c_rows_short_direct(T):
    r = T.contract_result(S.snap("one_rows_short_ivan"), number=NUM_IVAN,
                          rental=rental(T, row("+66 81 234 5678", "ADV 750 8004", "2026-09-20 10:00", "2026-10-05 10:00")))
    assert r["outcome"] == T.INCOMPLETE and r["facts"] == [], r
    assert T.UNREAD_WORDS in r["reason"] and "rows_short" in r["reason"], r["reason"]


def c_rows_short_run_no_pdf(T):
    doors, _ = doors_for(NUM_IVAN, [row("+66 81 234 5678", "ADV 750 8004", "2026-09-20 10:00", "2026-10-05 10:00")],
                         {"812345678": S.snap("one_rows_short_ivan")})
    out = T.run(Script({"tool": "contract", "args": {"phone": NUM_IVAN}},
                       {"tool": "contract_pdf", "args": {"file_id": PDF_B}}, final("Договор во вложении.")),
                "S", "U", doors, number=NUM_IVAN, clock=Clock())
    res = out["results"]
    assert [r["outcome"] for r in res] == [T.INCOMPLETE, T.REFUSED], [(r["outcome"], r["reason"]) for r in res]
    assert not [f for f in T.accepted(res) if f["kind"] in ("contract", "pdf")]


def c_unsigned_undated_fact(T):
    r = T.contract_result(S.snap("one_unsigned_undated"), number=NUM_OLEG,
                          rental=rental(T, row("+66 81 555 0005", "ADV 6666", "2026-09-18 09:00", "2026-09-25 09:00", "bk-7")))
    assert r["outcome"] == T.FACT, r
    assert r["facts"][0]["bound_by"] == "телефон" and r["facts"][0]["booking_id"] == "bk-7", r["facts"]


def c_ambiguous(T):
    r = T.contract_result(S.snap("ambiguous"), number=NUM_NINA, rental=None)
    assert r["outcome"] == T.AMBIGUOUS and r["facts"] == [], r


def c_incomplete(T):
    r = T.contract_result(S.snap("incomplete"), number="66815550001", rental=None)
    assert r["outcome"] == T.INCOMPLETE and r["facts"] == [] and "дверь: ответ неполон" in r["reason"], r


def c_other_number_direct(T):
    r = T.contract_result(S.snap("one_other_client"), number=NUM_NINA,
                          rental=rental(T, row("+66 81 555 0004", "ADV 750 8004", "2026-09-20 10:00", "2026-10-05 10:00")))
    assert r["outcome"] == T.CONFLICT and "другого номера" in r["reason"], r


NINA_RENT = ("+66 81 555 0004", "Click 160 5555")


def c_other_bike(T):
    r = T.contract_result(S.snap("one_complete"), number=NUM_NINA,
                          rental=rental(T, row(NINA_RENT[0], "Click 160 5556", "2026-09-15 10:00", "2026-09-20 10:00")))
    assert r["outcome"] == T.CONFLICT and "байк договора 5555" in r["reason"], r


def c_before_start(T):
    r = T.contract_result(S.snap("one_complete"), number=NUM_NINA,
                          rental=rental(T, row(*NINA_RENT, "2026-09-17 10:00", "2026-09-25 10:00")))
    assert r["outcome"] == T.CONFLICT and "вне срока" in r["reason"], r


def c_after_end(T):
    r = T.contract_result(S.snap("one_complete"), number=NUM_NINA,
                          rental=rental(T, row(*NINA_RENT, "2026-09-10 10:00", "2026-09-15 10:00")))
    assert r["outcome"] == T.CONFLICT and "вне срока" in r["reason"], r


def c_start_day_inclusive(T):
    r = T.contract_result(S.snap("one_complete"), number=NUM_NINA,
                          rental=rental(T, row(*NINA_RENT, "2026-09-16 15:00", "2026-09-23 15:00")))
    assert r["outcome"] == T.FACT, r


def c_end_day_inclusive(T):
    r = T.contract_result(S.snap("one_complete"), number=NUM_NINA,
                          rental=rental(T, row(*NINA_RENT, "2026-09-09 10:00", "2026-09-16 10:00")))
    assert r["outcome"] == T.FACT, r


def c_no_rental(T):
    for rent in (rental(T, None), None):
        r = T.contract_result(S.snap("one_complete"), number=NUM_NINA, rental=rent)
        assert r["outcome"] == T.UNKNOWN and r["facts"] == [] and "аренда" in r["reason"], r


def c_model_args_foreign_run(T):
    doors, seen = doors_for(NUM_NINA, [row("+66 81 555 0004", "ADV 750 8004", "2026-09-20 10:00", "2026-10-05 10:00")],
                            {"812345678": S.snap("one_other_client")})
    out = T.run(Script({"tool": "contract", "args": {"phone": "0812345678"}},
                       {"tool": "contract_pdf", "args": {"file_id": PDF_B}}, final("Ваш договор во вложении.")),
                "S", "U", doors, number=NUM_NINA, clock=Clock())
    res = out["results"]
    assert seen == [{"phone": "0812345678"}], seen                    # аргументы модели дошли до двери как есть
    assert [r["outcome"] for r in res] == [T.CONFLICT, T.REFUSED], [(r["outcome"], r["reason"]) for r in res]
    words, _ = T.judge("Ваш договор во вложении.", None, res, out["journal"])
    assert T.CONTRACT_WORDS in words, words
    assert any(c.startswith("contract: договор другого номера") for c in out["journal"].conflicts), out["journal"].conflicts


def c_nick_fact_run(T):
    doors, _ = doors_for(NUM_ANNA, [row("+66 89 765 4321", "Nmax 6908", "2026-09-15 09:00", "2026-09-22 09:00", "bk-6")],
                         {"897654321": S.snap("one_nick")})
    out = T.run(Script({"tool": "contract", "args": {"phone": NUM_ANNA}},
                       {"tool": "contract_pdf", "args": {"file_id": PDF_C}}, final("Договор во вложении.")),
                "S", "U", doors, number=NUM_ANNA, clock=Clock())
    res = out["results"]
    assert [r["outcome"] for r in res] == [T.FACT, T.FACT], [(r["outcome"], r["reason"]) for r in res]
    assert res[0]["facts"][0]["bound_by"] == "ник" and res[1]["facts"][0]["id"] == PDF_C
    assert "content_b64" not in json.dumps(res)


def c_nick_foreign(T):
    r = T.contract_result(S.snap("one_nick"), number=NUM_NINA,
                          rental=rental(T, row("+66 81 555 0004", "Nmax 6908", "2026-09-15 09:00", "2026-09-22 09:00")))
    assert r["outcome"] == T.CONFLICT and "другого номера" in r["reason"], r


def c_door_without_incomplete_branch(T):
    resp = S.snap("incomplete", override=door_mutant(*DOOR_NO_INCOMPLETE))
    assert resp["outcome"] == "one" and resp["checked"]["undated_signed"] == 1      # вход: дверь сказала «один»
    r = T.contract_result(resp, number="66815550001", rental=None)
    assert r["outcome"] == T.INCOMPLETE and "без известного дня 1" in r["reason"], r


def c_door_without_fields(T):
    resp = S.snap("one_complete", override=door_mutant(*DOOR_NO_FIELDS))
    assert resp["outcome"] == "one" and "unread" not in resp["checked"]             # вход: дверь до CONTRACTFIX
    r = T.contract_result(resp, number=NUM_NINA,
                          rental=rental(T, row(*NINA_RENT, "2026-09-15 10:00", "2026-09-20 10:00")))
    assert r["outcome"] == T.INCOMPLETE and "CONTRACTFIX0410" in r["reason"], r


def c_signed_pick_required(T):
    rent = rental(T, row("+44 7700 900123", "Vario 1234", "2026-09-28 10:00", "2026-10-02 10:00"))
    ok = T.contract_result(S.snap("one_partial_neighbor"), number=NUM_JOHN, rental=rent)
    assert ok["outcome"] == T.FACT, ok                                               # близнец: настоящая дверь
    resp = S.snap("one_partial_neighbor", override=door_mutant(*DOOR_UNSIGNED_PICK))
    assert resp["outcome"] == "one" and resp["pick"]["signed"] is False             # вход: дверь подсунула неподписанный
    r = T.contract_result(resp, number=NUM_JOHN, rental=rent)
    assert r["outcome"] != T.FACT and r["facts"] == [], r


def c_no_ctx_no_fact(T):
    r = T.call_tool("contract", {"phone": NUM_NINA}, {"contract": lambda **kw: S.snap("one_complete")})
    assert r["outcome"] == T.UNKNOWN and "номер обращения" in r["reason"], r
    p = T.call_tool("contract_pdf", {"file_id": PDF_C}, {"contract_pdf": pdf_client().contract_pdf})
    assert p["outcome"] == T.REFUSED and p["facts"] == [], p


CASES = [c_rows_short_direct, c_rows_short_run_no_pdf, c_unsigned_undated_fact, c_ambiguous, c_incomplete,
         c_other_number_direct, c_other_bike, c_before_start, c_after_end, c_start_day_inclusive,
         c_end_day_inclusive, c_no_rental, c_model_args_foreign_run, c_nick_fact_run, c_nick_foreign,
         c_door_without_incomplete_branch, c_door_without_fields, c_signed_pick_required, c_no_ctx_no_fact]


# ------------------------------- мутанты адаптера: одно правило — одна правка -------------------------------

MUTANTS = [
    ("unread непуст → не факт", '    if unread:\n        return result("contract", INCOMPLETE',
     '    if False:\n        return result("contract", INCOMPLETE'),
    ("undated_signed = 0", "    if undated_signed != 0:\n", "    if False:\n"),
    ("поля полноты обязательны",
     "    if (not isinstance(unread, list) or not isinstance(undated_signed, int) or isinstance(undated_signed, bool)):\n",
     "    if False:\n"),
    ("incomplete двери → INCOMPLETE", '    if out == "incomplete":\n', "    if False:\n"),
    ("pick подписан", 'if out != "one" or not pick or pick.get("signed") is not True:', 'if out != "one" or not pick:'),
    ("телефон договора = номер обращения", "    if key in phones:\n", "    if True:\n"),
    ("ник сверен дверью по номеру обращения",
     '    elif "nick" in on and str(flt.get("phone_last9") or "") == key:\n', '    elif "nick" in on:\n'),
    ("без аренды — не факт",
     '    if not isinstance(rental, dict) or rental.get("outcome") != FACT or len(rental.get("facts") or []) != 1:\n',
     "    if False:\n"),
    ("байк договора = байк аренды", "    if pc != pr:\n", "    if False:\n"),
    ("дата в сроке аренды", "    if not ds.isoformat() <= cd <= de.isoformat():\n", "    if False:\n"),
    ("день начала включительно", "ds.isoformat() <= cd <= de", "ds.isoformat() < cd <= de"),
    ("день конца включительно", "cd <= de.isoformat():", "cd < de.isoformat():"),
    ("PDF только принятого договора",
     '    if not resp.get("id") or resp.get("id") not in set(allowed or ()):\n', "    if False:\n"),
    ("номер — кодом, не аргументом модели", 'number=ctx.get("number") or ""',
     'number=(args or {}).get("phone") or ctx.get("number") or ""'),
    ("сверка передаёт контекст привязки", "        res = call_tool(tool, args, doors, clock, ctx)\n",
     "        res = call_tool(tool, args, doors, clock)\n"),
    ("конфликт договора виден человеку", '        if r["outcome"] == CONFLICT:\n', "        if False:\n"),
]


def load(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = TOOLS_SRC
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(T):
    fails = []
    for c in CASES:
        try:
            c(T)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    return fails


def mutant_kills():
    with open(TOOLS_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        out.append((i, rule, run_cases(load(src.replace(old, new), "wa_agent_tools_mut%d" % i))))
    return out


# ------------------------------- тесты -------------------------------

def test_cases_green_on_real_code():
    fails = run_cases(T_REAL)
    assert fails == [], fails


def test_every_rule_has_a_killing_mutant():
    survivors = [(i, rule) for i, rule, fails in mutant_kills() if not fails]
    assert survivors == [], survivors


def test_snapshots_come_from_door_code():
    snaps = S.snaps()
    assert {"one_rows_short_ivan", "one_unsigned_undated", "ambiguous", "incomplete", "one_other_client",
            "one_complete", "one_nick", "one_partial_neighbor", "pdf_b", "pdf_c"} <= set(snaps)
    keys = {"row", "doc_id", "client", "contract_date", "contract_date_raw", "created_raw", "date_src", "status",
            "signed", "signed_at", "bike", "phone", "pdf_id", "matched_on", "pdf_ready"}
    for name, s in snaps.items():
        if s.get("pick"):
            assert set(s["pick"]) == keys, (name, sorted(s["pick"]))


def main():
    bad = 0
    fails = run_cases(T_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL " + f[0][1]) if f else "PASS", c.__name__)
    bad += len(fails)
    print("случаи: %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule, fs in mutant_kills():
        killed += bool(fs)
        print("мутант %2d «%s»: упало %d из %d%s" % (i, rule, len(fs), len(CASES),
                                                    "" if fs else "  ← ВЫЖИЛ"))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    bad += len(MUTANTS) - killed
    try:
        test_snapshots_come_from_door_code()
        print("PASS test_snapshots_come_from_door_code")
    except AssertionError as e:
        bad += 1
        print("FAIL test_snapshots_come_from_door_code", e)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
