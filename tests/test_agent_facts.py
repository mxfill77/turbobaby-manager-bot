# -*- coding: utf-8 -*-
"""T4BFACTS0410 (Т4б, шаг 2): деньги ответа и подтверждения оплаты — только аренды обращения; версия факта — по НАЧАЛУ
запроса, а не по приходу ответа.

(а) У клиента две аренды, у каждой своя оплата; обращение — про вторую. Сумма кода, опора чисел ответа и сумма, которую
текст называет полученной оплатой, — только её строки кассы; прочая наличность «не привязано» и в сумму не входит.
(б) R1 начат раньше со старыми данными, R2 позже с новыми; R2 пришёл первым, R1 вторым — действует R2. Поздний отказ или
неизвестность по ключу — факт не подтверждён, старая версия не возвращается.

Ответы дверей — живого формата: касса — `tx_find` (поля как в test_wa_agent_tools), договор — снимок харнесса двери
(contract_door_snaps), аренда — строка листа «клиенты» (дверь аренды адаптера отдаёт только «В аренде»). Часы подменные.
Мутанты: на каждое правило — правка исходника в памяти; мутант обязан уронить хотя бы один случай (число печатается).
Модели, моста, Telegram, WhatsApp, сети и SQLite здесь нет."""

import json
import os
import subprocess
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

import contract_door_snaps as S     # noqa: E402
import wa_agent_knowledge as K      # noqa: E402
import wa_agent_model as M_REAL     # noqa: E402
import wa_agent_tools as T_REAL     # noqa: E402

TOOLS_SRC = os.path.join(ROOT, "wa_agent_tools.py")
BASE = "59883518"                   # дерево до правки: те же случаи на нём обязаны падать (печатается, в итог не идёт)

NUMBER = "66812345678"
BIKE1, BIKE2 = "Nmax 6908", "Click 160 5555"
NUM_NINA = "66815550004"
NINA_BIKE = "Click 160 5555"
AT = 1790000000.0


# ------------------------------- подмены живого формата -------------------------------

def tx_item(row, amount, booking_id, bike, date, description, category="rental"):
    return {"row": row, "date": date, "date_src": "msg_date", "recorded_at": date + "T05:00:00.000Z",
            "amount": amount, "currency": "THB", "category": category, "bike": bike, "deposit": "passport",
            "description": description, "raw": description, "msg_id": "-100311:501:m%d" % row,
            "link": "https://t.me/c/311/501", "status": "recorded", "booking_id": booking_id}


def tx(items):
    return {"ok": True, "checked": {"span_from": "2026-08-25", "span_to": "2026-10-03", "rows_scanned": 140,
                                    "truncated": False, "complete": True},
            "total": {"THB": 999999}, "items": list(items)}


def row(status, bike, ds, de, booking, price=None):
    r = {"status": status, "contacts": "+66 81 234 5678", "bike": bike, "booking_id": booking,
         "date_start": ds, "date_end": de}
    if price is not None:
        r["price"] = price
    return r


# первая аренда клиента завершена и оплачена (с залогом), вторая идёт — обращение про неё
FIRST = row("Завершена", BIKE1, "2026-09-01", "2026-09-07", "bk-1")
SECOND = row("В аренде", BIKE2, "2026-09-28", "2026-10-08", "bk-2")
PAY1 = tx_item(2, 4900, "bk-1", BIKE1, "2026-09-02", "Nmax 6908 +4900 аренда")
DEP1 = tx_item(3, 3000, "bk-1", BIKE1, "2026-09-02", "Nmax 6908 +3000 залог")
PAY2 = tx_item(7, 3500, "bk-2", BIKE2, "2026-09-29", "Click 5555 +3500 аренда")
DEP2 = tx_item(8, 3000, "bk-2", BIKE2, "2026-09-29", "Click 5555 +3000 залог")
CHAT = "Здравствуйте! По второй аренде, Click: оплатил 3500 бат. В прошлый раз было 4900 бат."


def cash_res(T, items, args, at=AT, resp=None):
    r = T.cash_result(resp if resp is not None else tx(items), at=at)
    r["req"] = T.request_key("cash", args)
    return r


def rental_res(T, rows, at=AT):
    r = T.rental_result({"ok": True, "rows": rows}, at=at)
    r["req"] = T.request_key("rental", {})
    return r


def history_res(T, text, at=AT):
    r = T.history_result([{"who": "клиент", "text": text}], at=at)
    r["req"] = T.request_key("history", {})
    return r


def contract_res(T, booking, at=AT):
    """Договор Нины (снимок двери one_complete), привязанный кодом к её аренде с номером брони `booking`."""
    rent = T.rental_result({"ok": True, "rows": [{"status": "В аренде", "contacts": "+66 81 555 0004",
                                                  "bike": NINA_BIKE, "booking_id": booking,
                                                  "date_start": "2026-09-15 10:00", "date_end": "2026-09-20 10:00"}]})
    r = T.contract_result(S.snap("one_complete"), at=at, number=NUM_NINA, rental=rent)
    assert r["outcome"] == T.FACT, r
    r["req"] = T.request_key("contract", {"phone": NUM_NINA})
    return r


def kassa(row_no, amount, at, args):
    """Строка кассы bk-1 (row 2) в версии `amount`, прочитанная запросом `args` с началом `at`."""
    return cash_res(T_REAL_SLOT[0], [tx_item(row_no, amount, "bk-1", BIKE1, "2026-09-02",
                                             "Nmax 6908 +%d аренда" % amount)], args, at=at)


T_REAL_SLOT = [T_REAL]              # модуль под случаем (настоящий или мутант) — для фабрики `kassa`


class Clock:
    def __init__(self, t=AT):
        self.t = t

    def __call__(self):
        return self.t


def final(text):
    return {"text": text, "handoff": [], "lang": "ru", "why": "тест"}


class Model:
    def __init__(self, answers):
        self.answers, self.n = list(answers), 0

    def __call__(self, system, user):
        a = self.answers[min(self.n, len(self.answers) - 1)]
        self.n += 1
        return json.dumps(a, ensure_ascii=False), {"in": 1, "out": 1}


class Book:
    def __init__(self, rows):
        self.rows = rows

    def get(self, now):
        return list(self.rows), [], 60, ""


def adapter(M, answers, doors, rows, chat=CHAT, log=None):
    a = M.ModelAdapter(":memory:-не-открывается", Model(answers), read_doc=None, clock=Clock(),
                       log=(log.append if log is not None else (lambda *_: None)), book=Book(rows), tools=doors,
                       fresh=None)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0, "last_in": None}
    a.build = lambda number, upto_id, now=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": chat}], [])
    return a


TOOLS_ASKED = [{"tool": "cash", "args": {}}, {"tool": "rental", "args": {}}, {"tool": "history", "args": {}}]


def judge_words(T, text, results):
    words, figures = T.judge(text, None, results, T.Journal("5678"))
    return words, figures


# ------------------------------- (а) деньги одной аренды -------------------------------

def c_two_rentals_foreign_payment_run(T, M):
    """Сквозь сверку адаптера: две аренды клиента, касса отдала строки обеих, обращение про вторую (bk-2, 3500).
    Текст «Оплата 4900 получена» берёт чужую оплату — причина «оплата не подтверждена» и «денежное утверждение без
    опоры»; сумма кода — только 3500, строки первой аренды — «не привязано» в журнале."""
    log = []
    a = adapter(M, TOOLS_ASKED + [final("Оплата 4900 бат получена, спасибо!")],
                {"cash": lambda **kw: tx([PAY1, DEP1, PAY2])}, [FIRST, SECOND], log=log)
    out = a.draft(NUMBER, 5)
    assert T.PAY_WORDS in out["handoff"], out["handoff"]
    assert K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]
    assert a.last["figures"]["sums"] == {"оплата аренды THB": 3500}, a.last["figures"]
    assert sorted(u["row"] for u in a.last["figures"]["unbound"]) == [2, 3], a.last["figures"]["unbound"]
    assert any(T.UNBOUND_WORDS in line and '"row": 2' in line for line in log), log


def c_two_rentals_own_payment_run(T, M):
    """Близнец: тот же мир, текст называет оплату ЭТОЙ аренды (3500) — подтверждение принято, опора есть."""
    a = adapter(M, TOOLS_ASKED + [final("Оплата 3500 бат получена, спасибо!")],
                {"cash": lambda **kw: tx([PAY1, DEP1, PAY2])}, [FIRST, SECOND])
    out = a.draft(NUMBER, 5)
    assert T.PAY_WORDS not in out["handoff"], out["handoff"]
    assert K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]
    assert a.last["figures"]["sums"] == {"оплата аренды THB": 3500}, a.last["figures"]


def c_mixed_total_not_support(T, M):
    """Итог двух аренд (8400) — не сумма ответа: «вы оплатили 8400» без опоры; только своя 3500 — опора."""
    res = [cash_res(T, [PAY1, PAY2], {}), rental_res(T, [SECOND]), history_res(T, CHAT)]
    words, figures = judge_words(T, "Итого вы оплатили 8400 бат.", res)
    assert K.MONEY_CLAIM_WORDS in words and figures["sums"] == {"оплата аренды THB": 3500}, (words, figures)
    words, _ = judge_words(T, "Итого вы оплатили 3500 бат.", res)
    assert K.MONEY_CLAIM_WORDS not in words, words


def c_deposit_of_other_rental(T, M):
    """Залог есть только у первой аренды — «залог получен» по второй не подтверждён; близнец с залогом bk-2 — да."""
    base = [rental_res(T, [SECOND]), history_res(T, CHAT)]
    words, _ = judge_words(T, "Залог получен, спасибо.", base + [cash_res(T, [PAY1, DEP1, PAY2], {})])
    assert T.ROLE_WORDS in words, words
    words, _ = judge_words(T, "Залог получен, спасибо.", base + [cash_res(T, [PAY1, PAY2, DEP2], {})])
    assert T.ROLE_WORDS not in words, words


def c_diff_with_own_price(T, M):
    """Разность цены аренды обращения — с ЕЁ оплатой: цена 3500, своя оплата 3500 → 0 (смесь дала бы −4900)."""
    facts = T.accepted([cash_res(T, [PAY1, PAY2], {}),
                        rental_res(T, [row("В аренде", BIKE2, "2026-09-28", "2026-10-08", "bk-2", price=3500)])])
    fig = T.calc(facts)
    assert fig["diffs"] == [{"what": "цена аренды минус оплата", "currency": "THB", "value": 0}], fig


def c_no_appeal_rental_two_in_sight(T, M):
    """Аренда обращения не установлена (по номеру две «В аренде»), касса — обеих: в сумму не входит ничего, обе строки
    «не привязано», «оплачено 4900» — без опоры. Близнец: касса одной аренды — она единственная в поле зрения, сумма есть."""
    amb = T.rental_result({"ok": True, "rows": [dict(FIRST, status="В аренде"), SECOND]}, at=AT)
    amb["req"] = T.request_key("rental", {})
    res = [cash_res(T, [PAY1, PAY2], {}), amb]
    words, figures = judge_words(T, "Оплачено 4900 бат.", res)
    assert figures["sums"] == {} and len(figures["unbound"]) == 2, figures
    assert K.MONEY_CLAIM_WORDS in words, words
    _w, figures = judge_words(T, "Ок.", [cash_res(T, [PAY2], {}), amb])
    assert figures["sums"] == {"оплата аренды THB": 3500} and figures["unbound"] == [], figures


def c_contract_path_foreign_amount(T, M):
    """Второй источник — договор, привязанный к аренде bk-N; в кассе ещё строка чужой аренды bk-1. «Оплата 3500»
    (чужая) не подтверждена, «оплата 4900» (своя) — подтверждена."""
    nina = tx_item(5, 4900, "bk-N", NINA_BIKE, "2026-09-16", "Click 5555 +4900 аренда")
    other = tx_item(6, 3500, "bk-1", BIKE1, "2026-09-02", "Nmax 6908 +3500 аренда")
    facts = T.accepted([contract_res(T, "bk-N"), cash_res(T, [nina, other], {"bike": NINA_BIKE})])
    assert T.pay_confirmed(facts) is True
    assert [w for w, _why in T.money_roles("Оплата 3500 бат получена.", facts)] == [T.PAY_WORDS]
    assert T.money_roles("Оплата 4900 бат получена.", facts) == []


# ------------------------------- (б) версия — по началу запроса -------------------------------

def c_start_order_other_request(T, M):
    """R1 (касса по байку) начат в T со старой суммой 4900, R2 (по брони) — в T+5 с новой 5000; R2 пришёл первым.
    Опора и сумма — 5000; «оплачено 4900» без опоры. Порядок прихода не меняет ничего."""
    r1, r2 = kassa(2, 4900, AT, {"bike": BIKE1}), kassa(2, 5000, AT + 5, {"booking_id": "bk-1"})
    for res in ([r2, r1], [r1, r2]):
        assert T.calc(T.accepted(res))["sums"] == {"оплата аренды THB": 5000}, res
        words, _ = judge_words(T, "Оплачено 4900 бат.", res)
        assert K.MONEY_CLAIM_WORDS in words, words
        words, _ = judge_words(T, "Оплачено 5000 бат.", res)
        assert K.MONEY_CLAIM_WORDS not in words, words


def c_start_order_same_request(T, M):
    """Тот же запрос: ответ, начатый позже (5000), пришёл первым — он и действует; прежний снят."""
    r1, r2 = kassa(2, 4900, AT, {"bike": BIKE1}), kassa(2, 5000, AT + 5, {"bike": BIKE1})
    facts, dropped = T.sift([r2, r1])
    assert [f["amount"] for f in facts if f["kind"] == "cash"] == [5000], facts
    assert any("тот же запрос прочитан позже" in d for d in dropped), dropped


def c_late_refusal_by_key(T, M):
    """R1 (по байку, T, 4900) и R2 (по брони, T+5, 5000) — одна строка; R3 — тот же запрос, что R2, начат в T+9 и
    отказал (таймаут). При любом порядке прихода строка не подтверждена: ни 5000, ни старая 4900; оплаты нет.
    Близнец: отказ начат ДО R2 (T+3) — R2 действует, 5000."""
    base = [rental_res(T, [row("В аренде", BIKE1, "2026-09-01", "2026-09-07", "bk-1")]),
            history_res(T, "оплатил 4900 бат, потом 5000 бат")]
    r1, r2 = kassa(2, 4900, AT, {"bike": BIKE1}), kassa(2, 5000, AT + 5, {"booking_id": "bk-1"})
    late = cash_res(T, [], {"booking_id": "bk-1"}, at=AT + 9, resp={"ok": False, "error": "timeout"})
    for res in ([late, r2, r1], [r1, late, r2], [r2, r1, late]):
        facts = T.accepted(base + res)
        assert not [f for f in facts if f["kind"] == "cash"], (res, facts)
        assert T.pay_confirmed(facts) is False
    early = dict(late, at=AT + 3)
    assert T.calc(T.accepted(base + [r1, early, r2]))["sums"] == {"оплата аренды THB": 5000}


def c_late_unknown_same_request(T, M):
    """Тот же запрос: FACT начат в T, «неизвестно» (дверь не выложена) — в T+5 и пришло первым: факта нет."""
    r1 = kassa(2, 4900, AT, {"bike": BIKE1})
    unk = cash_res(T, [], {"bike": BIKE1}, at=AT + 5, resp={"ok": False, "error": "unknown_action"})
    assert unk["outcome"] == T.UNKNOWN, unk
    assert not [f for f in T.accepted([unk, r1]) if f["kind"] == "cash"]


def c_reread_without_row(T, M):
    """Новейший ответ того же запроса строку уже не несёт — она не подтверждена, и старая версия из другого запроса
    (начатого раньше) не возвращается; соседняя строка нового ответа — опора."""
    r0 = kassa(2, 4900, AT, {"booking_id": "bk-1"})
    r1 = kassa(2, 4900, AT + 1, {"bike": BIKE1})
    r2 = cash_res(T, [tx_item(9, 1000, "bk-1", BIKE1, "2026-09-03", "Nmax 6908 +1000 аренда продление")],
                  {"bike": BIKE1}, at=AT + 2)
    rows = sorted(f["row"] for f in T.accepted([r2, r1, r0]) if f["kind"] == "cash")
    assert rows == [9], rows


def c_run_at_is_request_start(T, M):
    """Живой путь: `at` ответа — время НАЧАЛА запроса (до вызова двери), а не его прихода (дверь шла 10 с)."""
    clk = Clock()

    def door(**kw):
        clk.t += 10.0
        return tx([PAY1])
    out = T.run(Model([{"tool": "cash", "args": {}}, final("Ок")]), "S", "U", {"cash": door}, number=NUMBER,
                clock=clk)
    assert out["results"][0]["at"] == AT and clk.t == AT + 10.0, (out["results"][0]["at"], clk.t)


CASES = [c_two_rentals_foreign_payment_run, c_two_rentals_own_payment_run, c_mixed_total_not_support,
         c_deposit_of_other_rental, c_diff_with_own_price, c_no_appeal_rental_two_in_sight,
         c_contract_path_foreign_amount, c_start_order_other_request, c_start_order_same_request,
         c_late_refusal_by_key, c_late_unknown_same_request, c_reread_without_row, c_run_at_is_request_start]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("фильтр аренды в calc снят", "    bound, unbound = cash_split(facts)\n",
     '    bound, unbound = [f for f in facts if f["kind"] == "cash"], []\n'),
    ("сумма подтверждения без привязки", "    rows = cash_split(facts)[0]\n",
     '    rows = [f for f in facts if f["kind"] == "cash"]\n'),
    ("порядок по приходу", "        return sorted(range(len(results)), key=lambda i: (ats[i], i))\n",
     "        return list(range(len(results)))\n"),
    ("сумма подтверждения не сверяется", "    elif _PAY_CLAIM.search(s):\n", "    elif False:\n"),
    ("«не привязано» — опора ответа", "        if id(f) in loose:\n", "        if False:\n"),
    ("залог — любой аренды", 'f["role"] == R_DEPOSIT for f in bound):', 'f["role"] == R_DEPOSIT for f in facts):'),
    ("без аренды обращения — привязано всё", "        bound = cash if len(named) == 1 else []\n",
     "        bound = cash\n"),
    ("поздний отказ по ключу не снимает старую версию",
     "    for k in [k for k in facts if gone.get(k, -1) > born.get(k, -1)]:\n", "    for k in []:\n"),
    ("новый ответ без строки её не снимает",
     '            kept = {fact_key(g) for g in results[j]["facts"]} if results[j]["outcome"] == FACT else set()\n',
     '            kept = {fact_key(g) for g in r["facts"]} if results[j]["outcome"] == FACT else set()\n'),
]


def module(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = TOOLS_SRC
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(T, M=M_REAL):
    fails = []
    keep = sys.modules.get("wa_agent_tools")
    sys.modules["wa_agent_tools"] = T                 # адаптер импортирует сверку по имени — подставляем мутанта
    T_REAL_SLOT[0] = T
    try:
        for c in CASES:
            try:
                c(T, M)
            except Exception as e:                                   # noqa: BLE001 — падение мутанта = поимка
                fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    finally:
        sys.modules["wa_agent_tools"] = keep
        T_REAL_SLOT[0] = T_REAL
    return fails


def mutant_kills():
    with open(TOOLS_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        out.append((i, rule, run_cases(module(src.replace(old, new), "wa_agent_tools_mut%d" % i))))
    return out


def base_fails():
    """Те же случаи на дереве до правки (`git show BASE:wa_agent_tools.py`). Нет git — None (названо, не зелёное)."""
    try:
        src = subprocess.run(["git", "-C", ROOT, "show", BASE + ":wa_agent_tools.py"], capture_output=True,
                             check=True, timeout=30).stdout.decode("utf-8")
    except Exception:                                                # noqa: BLE001
        return None
    return run_cases(module(src, "wa_agent_tools_base"))


# ------------------------------- тесты -------------------------------

def test_cases_green_on_real_code():
    fails = run_cases(T_REAL)
    assert fails == [], fails


def test_every_rule_has_a_killing_mutant():
    survivors = [(i, rule) for i, rule, fails in mutant_kills() if not fails]
    assert survivors == [], survivors


def test_mutation_harness_restores_module():
    run_cases(T_REAL)
    assert sys.modules["wa_agent_tools"] is T_REAL and T_REAL_SLOT[0] is T_REAL


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
        print("мутант %2d «%s»: упало %d из %d%s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ"))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    bad += len(MUTANTS) - killed
    base = base_fails()
    if base is None:
        print("дерево %s: git недоступен — прогон «до правки» не сделан (это НЕ зелёное)" % BASE)
    else:
        print("дерево %s (до правки): упало %d из %d — %s" % (BASE, len(base), len(CASES),
                                                            ", ".join(n for n, _ in base)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
