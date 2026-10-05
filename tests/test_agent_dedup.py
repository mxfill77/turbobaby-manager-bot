# -*- coding: utf-8 -*-
"""AGENTDEDUP0410 (Т4а, часть 2): каждый факт сверки — один раз и в последней версии; позднее «не факт» того же запроса
снимает прежний факт; оплата — строкой кассы этой аренды и вторым источником той же аренды; факт старше последнего
входящего не опора; общий дедлайн сверки, включая запасной вызов.

Ответы дверей — живого формата: касса — `tx_find` (поля как в test_wa_agent_tools), договор — снимок харнесса двери
(contract_door_snaps), аренда — строка листа «клиенты». Часы подменные, дверь медленная — она двигает часы.
Мутанты: на каждое правило — правка исходника в памяти; мутант обязан уронить хотя бы один случай (число печатается).
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

import contract_door_snaps as S     # noqa: E402
import wa_agent_model as M_REAL     # noqa: E402
import wa_agent_tools as T_REAL     # noqa: E402

TOOLS_SRC = os.path.join(ROOT, "wa_agent_tools.py")
MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")

NUMBER = "66812345678"
BIKE = "Nmax 6908"
NUM_NINA = "66815550004"
NINA_BIKE = "Click 160 5555"
AT = 1790000000.0


# ------------------------------- подмены живого формата -------------------------------

def tx_item(row=2, amount=4900, category="rental", description="Nmax 6908 +4900 аренда", booking_id="bk-1",
            bike=BIKE, date="2026-09-30"):
    item = {"row": row, "date": date, "date_src": "msg_date", "recorded_at": date + "T05:00:00.000Z",
            "amount": amount, "currency": "THB", "category": category, "bike": bike, "deposit": "passport",
            "description": description, "raw": description, "msg_id": "-100311:501:m%d" % row,
            "link": "https://t.me/c/311/501", "status": "recorded", "booking_id": booking_id}
    if booking_id is None:
        item.pop("booking_id")
    return item


def tx(items, complete=True):
    return {"ok": True, "checked": {"span_from": "2026-09-01", "span_to": "2026-10-03", "rows_scanned": 120,
                                    "truncated": False, "complete": complete},
            "total": {"THB": 999999}, "items": list(items)}


def row(contacts, bike, ds, de, booking="bk-1"):
    return {"status": "В аренде", "contacts": contacts, "bike": bike, "booking_id": booking,
            "date_start": ds, "date_end": de}


RENTAL_ROW = row("+66 81 234 5678", BIKE, "2026-09-30", "2026-10-07", "bk-1")


def cash_res(T, items, args, at=AT, ok=True):
    r = T.cash_result(tx(items) if ok else {"ok": False, "error": "timeout"}, at=at)
    r["req"] = T.request_key("cash", args)
    return r


def rental_res(T, r, at=AT):
    res = T.rental_result({"ok": True, "rows": [r]}, at=at)
    res["req"] = T.request_key("rental", {})
    return res


def contract_res(T, booking, at=AT):
    """Договор Нины (снимок двери one_complete), привязанный кодом к её аренде с номером брони `booking`."""
    rent = T.rental_result({"ok": True, "rows": [row("+66 81 555 0004", NINA_BIKE, "2026-09-15 10:00",
                                                       "2026-09-20 10:00", booking)]})
    r = T.contract_result(S.snap("one_complete"), at=at, number=NUM_NINA, rental=rent)
    assert r["outcome"] == T.FACT, r
    r["req"] = T.request_key("contract", {"phone": NUM_NINA})
    return r


def history_res(T, text, at=AT):
    r = T.history_result([{"who": "клиент", "text": text}], at=at)
    r["req"] = T.request_key("history", {})
    return r


def nina_cash(booking="bk-N", **kw):
    return tx_item(bike=NINA_BIKE, date="2026-09-16", booking_id=booking, description="Click 5555 +4900 аренда", **kw)


class Clock:
    def __init__(self, t=AT):
        self.t = t

    def __call__(self):
        return self.t


def final(text):
    return {"text": text, "handoff": [], "lang": "ru", "why": "тест"}


class Model:
    """Модель по сценарию; каждый вызов — в журнал событий со временем начала; `slow` — сколько секунд он идёт."""

    def __init__(self, clk, events, answers, slow=(), plain=final("Уточню и вернусь.")):
        self.clk, self.events, self.answers, self.slow, self.plain, self.n = clk, events, list(answers), slow, plain, 0

    def __call__(self, system, user):
        if user == "USER":                                    # запасной обычный вызов без блока инструментов
            self.events.append(("запасной", self.clk.t))
            return json.dumps(self.plain, ensure_ascii=False), {"in": 1, "out": 1}
        self.events.append(("модель", self.clk.t))
        self.clk.t += self.slow[self.n] if self.n < len(self.slow) else 0.0
        a = self.answers[min(self.n, len(self.answers) - 1)]
        self.n += 1
        return json.dumps(a, ensure_ascii=False), {"in": 1, "out": 1}


def slow_door(clk, events, name, sec, answer):
    def door(**kw):
        events.append((name, clk.t))
        clk.t += sec
        return json.loads(json.dumps(answer))
    return door


def adapter(M, model, clk, doors, book_rows=None, history_text="оплатил 4900 бат за аренду", last_in=None):
    class Book:
        def get(self, now):
            return list(book_rows or []), [], 60, ""
    a = M.ModelAdapter(":memory:-не-открывается", model, read_doc=None, clock=clk, log=lambda *_: None,
                       book=Book() if book_rows is not None else None, tools=doors, fresh=None)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0, "last_in": last_in}
    a.build = lambda number, upto_id, now=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": history_text}], [])
    return a


def after(events, deadline):
    return [e for e in events if e[1] >= deadline]


# ------------------------------- случаи -------------------------------

def c_cash_row_twice_one_sum(T, M):
    """Одна строка кассы прочитана двумя запросами — в опоре и в сумме один раз."""
    res = [cash_res(T, [tx_item()], {"bike": BIKE}), cash_res(T, [tx_item()], {"booking_id": "bk-1"})]
    cash = [f for f in T.accepted(res) if f["kind"] == "cash"]
    assert len(cash) == 1, cash
    assert T.calc(T.accepted(res))["sums"] == {"оплата аренды THB": 4900}


def c_cash_row_twice_run(T, M):
    """То же сквозь сверку адаптера: сумма кода 4900, а не 9800."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, {"tool": "cash", "args": {"booking_id": "bk-1"}},
                            final("Спасибо!")])
    a = adapter(M, model, clk, {"cash": lambda **kw: tx([tx_item()])})
    a.draft(NUMBER, 5)
    assert a.last["figures"]["sums"] == {"оплата аренды THB": 4900}, a.last["figures"]
    assert len([f for f in a.last["tools"]["journal"].facts if f["kind"] == "cash"]) == 1


def c_calc_dedup_direct(T, M):
    f = T.accepted([cash_res(T, [tx_item()], {"bike": BIKE})])[0]
    assert T.calc([f, dict(f)])["sums"] == {"оплата аренды THB": 4900}


def c_latest_version_wins(T, M):
    """Строка исправлена между прочтениями (два разных запроса) — опора и сумма из последней версии."""
    res = [cash_res(T, [tx_item(amount=4900)], {"bike": BIKE}),
           cash_res(T, [tx_item(amount=5000)], {"booking_id": "bk-1"})]
    assert T.calc(T.accepted(res))["sums"] == {"оплата аренды THB": 5000}


def c_one_msg_two_rows_two_facts(T, M):
    """Близнец дедупа: одно сообщение записано двумя строками кассы (тот же msg_id и link) — это ДВА факта, сумма обеих."""
    a = tx_item(row=2, amount=4900)
    b = dict(tx_item(row=3, amount=1000, description="Nmax 6908 +1000 аренда продление"),
             msg_id=a["msg_id"], link=a["link"])
    facts = T.accepted([cash_res(T, [a, b], {"bike": BIKE})])
    assert len([f for f in facts if f["kind"] == "cash"]) == 2, facts
    assert T.calc(facts)["sums"] == {"оплата аренды THB": 5900}


def c_same_row_other_msg_two_facts(T, M):
    """Тождество кассы — row ВМЕСТЕ с msg_id|link: тот же номер строки под другим сообщением — другой факт, а не новая
    версия прежнего (молча слить их значило бы потерять проводку)."""
    a = tx_item(row=2, amount=4900)
    b = dict(tx_item(row=2, amount=1000, description="Nmax 6908 +1000 аренда"), msg_id="-100311:777:m2",
             link="https://t.me/c/311/777")
    facts = T.accepted([cash_res(T, [a], {"bike": BIKE}), cash_res(T, [b], {"booking_id": "bk-1"})])
    assert len([f for f in facts if f["kind"] == "cash"]) == 2, facts


def c_contract_twice_one(T, M):
    """Договор (row + doc_id) прочитан двумя запросами — в опоре один, версия последнего прочтения; близнец с другим
    doc_id — два факта."""
    first = contract_res(T, "bk-N")
    second = json.loads(json.dumps(first))
    second["facts"][0]["signed_at"] = "2026-09-15T11:00:00.000Z"
    second["req"] = T.request_key("contract", {"name": "Nina"})
    got = [f for f in T.accepted([first, second]) if f["kind"] == "contract"]
    assert len(got) == 1 and got[0]["signed_at"] == "2026-09-15T11:00:00.000Z", got
    other = json.loads(json.dumps(second))
    other["facts"][0]["doc_id"] = "doc-другой"
    assert len([f for f in T.accepted([first, other]) if f["kind"] == "contract"]) == 2


def c_rental_twice_one(T, M):
    """Аренда (booking_id) из двух прочтений — одна, версия последнего; аренда обращения остаётся одной."""
    first = rental_res(T, RENTAL_ROW)
    second = rental_res(T, dict(RENTAL_ROW, date_end="2026-10-09"))
    second["req"] = T.request_key("rental", {"phone": NUMBER})
    got = [f for f in T.accepted([first, second]) if f["kind"] == "rental"]
    assert len(got) == 1 and got[0]["date_end"] == "2026-10-09", got
    assert T.rental_of(got) == "bk-1"


def c_pay_latest_version(T, M):
    """pay_confirmed — по последней версии строки: строку исправили «аренда» → «залог» — оплата аренды не подтверждена;
    близнец (исправили «залог» → «аренда») — подтверждена."""
    rent = tx_item(amount=4900)
    dep = tx_item(amount=4900, description="Nmax 6908 +4900 залог")
    base = [rental_res(T, RENTAL_ROW), history_res(T, "оплатил 4900 бат")]
    to_dep = base + [cash_res(T, [rent], {"bike": BIKE}), cash_res(T, [dep], {"booking_id": "bk-1"})]
    assert T.pay_confirmed(T.accepted(to_dep)) is False
    to_rent = base + [cash_res(T, [dep], {"bike": BIKE}), cash_res(T, [rent], {"booking_id": "bk-1"})]
    assert T.pay_confirmed(T.accepted(to_rent)) is True


def c_fact_then_refusal_same_request(T, M):
    """FACT, затем отказ того же запроса → опоры нет: ни суммы, ни подтверждения оплаты."""
    res = [cash_res(T, [tx_item()], {"bike": BIKE}), rental_res(T, RENTAL_ROW),
           history_res(T, "оплатил 4900 бат"), cash_res(T, [], {"bike": " nmax  6908 "}, ok=False)]
    facts = T.accepted(res)
    assert not [f for f in facts if f["kind"] == "cash"], facts
    assert T.pay_confirmed(facts) is False
    _facts, dropped = T.sift(res)
    assert any("тот же запрос прочитан позже" in d for d in dropped), dropped


def c_refusal_other_request_keeps(T, M):
    """Близнец: отказ ДРУГОГО запроса прежний факт не снимает — оплата подтверждена."""
    res = [cash_res(T, [tx_item()], {"bike": BIKE}), rental_res(T, RENTAL_ROW),
           history_res(T, "оплатил 4900 бат"), cash_res(T, [], {"booking_id": "bk-9"}, ok=False)]
    assert T.pay_confirmed(T.accepted(res)) is True


def c_fact_then_refusal_run(T, M):
    """Сквозь сверку: касса ответила, потом тот же запрос — таймаут; текст «оплата получена» → причина человеку."""
    clk, ev = Clock(), []
    seen = []

    def cash(**kw):
        seen.append(1)
        if len(seen) > 1:
            raise TimeoutError("молчит")
        return tx([tx_item()])
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, {"tool": "rental", "args": {}},
                            {"tool": "history", "args": {}}, {"tool": "cash", "args": {"bike": BIKE}},
                            final("Оплата 4900 бат получена.")])
    a = adapter(M, model, clk, {"cash": cash}, book_rows=[RENTAL_ROW])
    out = a.draft(NUMBER, 5)
    assert T.PAY_WORDS in out["handoff"], out["handoff"]
    assert a.last["figures"]["sums"] == {}, a.last["figures"]


def c_cash_contract_other_rental(T, M):
    """Касса аренды bk-1, договор привязан к аренде bk-N → оплата не подтверждена; близнец той же аренды — да."""
    bad = T.accepted([cash_res(T, [nina_cash("bk-1")], {"bike": NINA_BIKE}), contract_res(T, "bk-N")])
    assert T.pay_confirmed(bad) is False
    ok = T.accepted([cash_res(T, [nina_cash("bk-N")], {"bike": NINA_BIKE}), contract_res(T, "bk-N")])
    assert T.pay_confirmed(ok) is True


def c_two_rentals_no_pay(T, M):
    """Лист говорит bk-1, договор — bk-N: аренда обращения не одна → не подтверждено при любой строке кассы."""
    facts = T.accepted([rental_res(T, row("+66 81 555 0004", NINA_BIKE, "2026-09-15", "2026-09-20", "bk-1")),
                        contract_res(T, "bk-N"), cash_res(T, [nina_cash("bk-N")], {"bike": NINA_BIKE})])
    assert T.rental_of(facts) is None and T.pay_confirmed(facts) is False


def c_contract_without_booking_not_second(T, M):
    """Договор без номера брони (аренда в листе без booking_id) — не второй источник аренды bk-1."""
    unbound = contract_res(T, None)
    assert unbound["facts"][0]["booking_id"] is None
    facts = T.accepted([rental_res(T, RENTAL_ROW), cash_res(T, [tx_item()], {"bike": BIKE}), unbound])
    assert T.pay_confirmed(facts) is False


def c_cash_without_booking_by_bike_window(T, M):
    """Строка кассы без booking_id — этой аренды, только если байк тот же и день внутри срока."""
    base = [rental_res(T, RENTAL_ROW), history_res(T, "оплатил 4900 бат")]
    inside = T.accepted(base + [cash_res(T, [tx_item(booking_id=None, date="2026-10-02")], {"bike": BIKE})])
    assert T.pay_confirmed(inside) is True
    outside = T.accepted(base + [cash_res(T, [tx_item(booking_id=None, date="2026-09-20")], {"bike": BIKE})])
    assert T.pay_confirmed(outside) is False


def c_stale_fact(T, M):
    """Касса прочитана раньше последнего входящего — устарела; близнец прочитан после — опора."""
    since = AT + 10
    old = [cash_res(T, [tx_item()], {"bike": BIKE}, at=AT), rental_res(T, RENTAL_ROW, at=AT + 20),
           history_res(T, "оплатил 4900 бат", at=AT + 20)]
    assert T.pay_confirmed(T.accepted(old, since=since)) is False
    assert T.calc(T.accepted(old, since=since))["sums"] == {}
    new = [cash_res(T, [tx_item()], {"bike": BIKE}, at=AT + 30)] + old[1:]
    assert T.pay_confirmed(T.accepted(new, since=since)) is True


def c_stale_run(T, M):
    """Сквозь сверку: последнее входящее клиента новее прочтения кассы — сумма кода пуста, оплата не подтверждена."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, {"tool": "rental", "args": {}},
                            {"tool": "history", "args": {}}, final("Оплата 4900 бат получена.")])
    a = adapter(M, model, clk, {"cash": lambda **kw: tx([tx_item()])}, book_rows=[RENTAL_ROW], last_in=AT + 5)
    out = a.draft(NUMBER, 5)
    assert a.last["figures"]["sums"] == {}, a.last["figures"]
    assert T.PAY_WORDS in out["handoff"], out["handoff"]
    twin = adapter(M, Model(Clock(AT + 10), [], model.answers), Clock(AT + 10),
                   {"cash": lambda **kw: tx([tx_item()])}, book_rows=[RENTAL_ROW], last_in=AT + 5)
    assert T.PAY_WORDS not in twin.draft(NUMBER, 5)["handoff"]


def c_slow_door_no_calls_after_deadline(T, M):
    """Медленная дверь кассы (100 с) — после дедлайна вызовов 0: ни модели, ни дверей, ни запасного; черновика нет."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, {"tool": "history", "args": {}}, final("Ок")])
    a = adapter(M, model, clk, {"cash": slow_door(clk, ev, "касса", 100.0, tx([tx_item()]))})
    out = a.draft(NUMBER, 5)
    deadline = a.last["tools"]["deadline"]
    assert deadline == AT + T.MAX_SEC, deadline
    assert after(ev, deadline) == [], ev
    assert out is None and a.last["tools"]["state"] == T.OVER and a.last.get("fallback") is False
    assert [e[0] for e in ev] == ["модель", "касса"], ev


def c_slow_model_door_after_deadline(T, M):
    """Модель думала до T+95 и попросила дверь — дверь не зовётся: после дедлайна вызовов 0."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, final("Ок")], slow=(95.0,))
    a = adapter(M, model, clk, {"cash": slow_door(clk, ev, "касса", 1.0, tx([tx_item()]))})
    out = a.draft(NUMBER, 5)
    assert after(ev, a.last["tools"]["deadline"]) == [], ev
    assert out is None and a.last["tools"]["doors"] == 0


def c_slow_final_after_deadline(T, M):
    """Итог модели пришёл после дедлайна — не черновик сверки и не повод для запасного вызова."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [final("Оплата получена.")], slow=(95.0,))
    a = adapter(M, model, clk, {})
    out = a.draft(NUMBER, 5)
    assert out is None and a.last["tools"]["state"] == T.OVER, out
    assert after(ev, a.last["tools"]["deadline"]) == [], ev


def c_contract_slow_rental_not_read(T, M):
    """Дверь договоров шла 40 с с T+55 — аренду код сам уже не читает (T+95 после дедлайна)."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "contract", "args": {"phone": NUM_NINA}}, final("Ок")], slow=(55.0,))
    a = adapter(M, model, clk, {"contract": slow_door(clk, ev, "договор", 40.0, S.snap("one_complete"))},
                book_rows=[row("+66 81 555 0004", NINA_BIKE, "2026-09-15 10:00", "2026-09-20 10:00", "bk-N")])
    orig = a._tool_doors

    def doors(number, upto):
        d = orig(number, upto)
        rent = d["rental"]

        def rental(**kw):
            ev.append(("аренда", clk.t))
            return rent(**kw)
        d["rental"] = rental
        return d
    a._tool_doors = doors
    a.draft(NUM_NINA, 5)
    assert after(ev, a.last["tools"]["deadline"]) == [], ev
    r = a.last["tools"]["results"][0]
    assert r["outcome"] != T.FACT, r


def c_fallback_within_deadline(T, M):
    """Дверь шла 70 с: сверка встаёт (остаток — запасному), запасной вызов начат ДО дедлайна, причина первой."""
    clk, ev = Clock(), []
    model = Model(clk, ev, [{"tool": "cash", "args": {"bike": BIKE}}, final("Оплата получена.")])
    a = adapter(M, model, clk, {"cash": slow_door(clk, ev, "касса", 70.0, tx([tx_item()]))})
    out = a.draft(NUMBER, 5)
    assert [e[0] for e in ev] == ["модель", "касса", "запасной"], ev
    assert ev[-1][1] < a.last["tools"]["deadline"]
    assert out["handoff"][0] == T.INCOMPLETE_WORDS, out


CASES = [c_cash_row_twice_one_sum, c_cash_row_twice_run, c_calc_dedup_direct, c_latest_version_wins,
         c_one_msg_two_rows_two_facts, c_same_row_other_msg_two_facts, c_contract_twice_one, c_rental_twice_one,
         c_pay_latest_version, c_fact_then_refusal_same_request, c_refusal_other_request_keeps, c_fact_then_refusal_run,
         c_cash_contract_other_rental, c_two_rentals_no_pay, c_contract_without_booking_not_second,
         c_cash_without_booking_by_bike_window, c_stale_fact, c_stale_run, c_slow_door_no_calls_after_deadline,
         c_slow_model_door_after_deadline, c_slow_final_after_deadline, c_contract_slow_rental_not_read,
         c_fallback_within_deadline]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    (TOOLS_SRC, "идентичность факта: строка кассы один раз",
     "            k = fact_key(f)\n            if k in facts:", "            k = (i, id(f))\n            if k in facts:"),
    (TOOLS_SRC, "calc — по дедупу", "        uniq[fact_key(f)] = f\n", "        uniq[(id(f), len(uniq))] = f\n"),
    (TOOLS_SRC, "версия — последнего прочтения", "            facts[k] = f\n", "            facts.setdefault(k, f)\n"),
    (TOOLS_SRC, "позднее не-FACT того же запроса снимает FACT", "        if j != i:\n", "        if False:\n"),
    (TOOLS_SRC, "тождество запроса — инструмент и аргументы",
     '    return "%s %s" % (tool, json.dumps(norm, ensure_ascii=False))\n', "    return tool\n"),
    (TOOLS_SRC, "касса — этой аренды",
     'f["role"] == R_RENT and cash_of_rental(f, bk, facts)]', 'f["role"] == R_RENT]'),
    (TOOLS_SRC, "второй источник — той же аренды",
     'if any(f["kind"] == "contract" and str(f.get("booking_id") or "") == bk for f in facts):',
     'if any(f["kind"] == "contract" for f in facts):'),
    (TOOLS_SRC, "аренда обращения одна", "    return ids.pop() if len(ids) == 1 else None\n",
     "    return sorted(ids)[-1] if ids else None\n"),
    (TOOLS_SRC, "строка без booking_id — байк и срок",
     "    return bool(pc) and pc == pr and None not in (d, ds, de) and ds <= d <= de\n",
     "    return bool(pc) and pc == pr\n"),
    (TOOLS_SRC, "свежесть: факт старше входящего не опора", "        if stale(r, since):\n", "        if False:\n"),
    (TOOLS_SRC, "дверь не зовётся без времени",
     "        if not may_call():                                # модель просит дверь", "        if False:  #"),
    (TOOLS_SRC, "аренду код не читает без времени",
     "            if may_call is not None and not may_call():\n", "            if False:\n"),
    (TOOLS_SRC, "сверка оставляет остаток запасному", "    stop = deadline - max(0.0, min(reserve, max_sec))\n",
     "    stop = deadline\n"),
    (TOOLS_SRC, "итог после дедлайна — не черновик сверки", "            if clock() > deadline:\n",
     "            if False:\n"),
    (MODEL_SRC, "запасной вызов — только до дедлайна", '            if self.clock() >= out["deadline"]:',
     "            if False:"),
    (MODEL_SRC, "свежесть передаётся судье", '                                   since=info.get("last_in"))',
     "                                   since=None)"),
    (TOOLS_SRC, "тождество кассы: row в ключе",
     '        return ("cash", str(f.get("src") or "tx_find"), str(f.get("row")), str(f.get("msg_id") or f.get("link") or ""))',
     '        return ("cash", str(f.get("src") or "tx_find"), str(f.get("msg_id") or f.get("link") or ""))'),
    (TOOLS_SRC, "тождество кассы: msg_id|link в ключе",
     '        return ("cash", str(f.get("src") or "tx_find"), str(f.get("row")), str(f.get("msg_id") or f.get("link") or ""))',
     '        return ("cash", str(f.get("src") or "tx_find"), str(f.get("row")))'),
    (TOOLS_SRC, "тождество договора: row и doc_id",
     '        return ("contract", str(f.get("row")), str(f.get("doc_id") or ""))',
     '        return ("contract", str(f.get("row")), str(f.get("doc_id") or ""), id(f))'),
    (TOOLS_SRC, "тождество аренды: booking_id",
     '            return ("rental", str(f["booking_id"]))', '            return ("rental", str(f["booking_id"]), id(f))'),
    (TOOLS_SRC, "денежные роли судятся по отсеянному", "    for w, why in money_roles(text, facts):",
     '    for w, why in money_roles(text, [g for r in results if r["outcome"] == FACT for g in r["facts"]]):'),
]


def load(path, name):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def module(src, name, path):
    mod = types.ModuleType(name)
    mod.__file__ = path
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(T, M):
    fails = []
    keep = sys.modules.get("wa_agent_tools")
    sys.modules["wa_agent_tools"] = T                 # адаптер импортирует сверку по имени — подставляем мутанта
    try:
        for c in CASES:
            try:
                c(T, M)
            except Exception as e:                                   # noqa: BLE001 — падение мутанта = поимка
                fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    finally:
        sys.modules["wa_agent_tools"] = keep
    return fails


def mutant_kills():
    out = []
    srcs = {TOOLS_SRC: load(TOOLS_SRC, ""), MODEL_SRC: load(MODEL_SRC, "")}
    for i, (path, rule, old, new) in enumerate(MUTANTS, 1):
        src = srcs[path]
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        mutated = src.replace(old, new)
        if path == TOOLS_SRC:
            T, M = module(mutated, "wa_agent_tools_mut%d" % i, path), M_REAL
        else:
            T, M = T_REAL, module(mutated, "wa_agent_model_mut%d" % i, path)
        out.append((i, rule, run_cases(T, M)))
    return out


# ------------------------------- тесты -------------------------------

def test_cases_green_on_real_code():
    fails = run_cases(T_REAL, M_REAL)
    assert fails == [], fails


def test_every_rule_has_a_killing_mutant():
    survivors = [(i, rule) for i, rule, fails in mutant_kills() if not fails]
    assert survivors == [], survivors


def test_mutation_harness_restores_module():
    run_cases(T_REAL, M_REAL)
    assert sys.modules["wa_agent_tools"] is T_REAL


def main():
    bad = 0
    fails = run_cases(T_REAL, M_REAL)
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
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
