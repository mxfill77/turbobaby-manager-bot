# -*- coding: utf-8 -*-
"""AGENTLOOPA0310 (Т4а): агент WhatsApp с инструментами чтения и журналом — флаг WA_AGENT_TOOLS.

Всё на подменах: модели, моста, Telegram, WhatsApp, сети и SQLite здесь нет. Двери — функции с ответами живого формата
(`bridge_client.tx_find` @83ee219, `contract_find`/`contract_pdf` @bb0aa86; ответ договора с AGENTFIX0410 снимается
харнессом двери f8276398 — `contract_door_snaps`). Голден флага выкл — дерево 9c4aac6 через
`git show` (нет git — проверка названа пропущенной, а не зелёной)."""

import json
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены,
    import fcntl  # noqa: F401              # на сервере — настоящий модуль (cost_of зовёт только cost_usd)
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent_knowledge as K   # noqa: E402
import wa_agent_model as M       # noqa: E402
import wa_agent_tools as T       # noqa: E402

NUMBER = "66812345678"
BIKE = "Nmax 6908"


# ------------------------------- подмены -------------------------------

class Clock:
    def __init__(self, t=1790000000.0, step=0.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


class Script:
    """Модель по сценарию: список ответов по порядку; последний повторяется."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


def tx_item(row=2, amount=4900, category="rental", description="Nmax 6908 +4900 аренда", status="recorded",
            booking_id="bk-1"):
    return {"row": row, "date": "2026-09-30", "date_src": "msg_date", "recorded_at": "2026-09-30T05:00:00.000Z",
            "amount": amount, "currency": "THB", "category": category, "bike": BIKE, "deposit": "passport",
            "description": description, "raw": description, "msg_id": "-100311:501:m%d" % row,
            "link": "https://t.me/c/311/501", "status": status, "booking_id": booking_id}


def tx(items, complete=True, truncated=False, ok=True):
    checked = {"span_from": "2026-09-01", "span_to": "2026-10-03", "rows_scanned": 120, "truncated": truncated}
    if complete is not None:
        checked["complete"] = complete
    return {"ok": ok, "checked": checked, "total": {"THB": 999999}, "items": list(items)}


import contract_door_snaps as S   # noqa: E402

# ответ двери договоров — снят харнессом f8276398 (AGENTFIX0410), а не написан руками: Ivan Petrov, D-002, ADV 8004,
# 2026-09-20, телефон 66812345678 (последние 9 = NUMBER)
CONTRACT_ONE = S.snap("one_other_client")
# аренда, к которой этот договор привязывается кодом: тот же номер, тот же байк, дата договора в сроке
RENTAL_IVAN = {"status": "В аренде", "contacts": "+66 81 234 5678", "bike": "ADV 750 8004", "booking_id": "bk-2",
               "date_start": "2026-09-20 10:00", "date_end": "2026-10-05 10:00"}


class Book:
    def __init__(self, rows):
        self.rows, self.reads = rows, 0

    def get(self, now):
        self.reads += 1
        return self.rows, [], 60, ""


RENTAL_ROW = {"status": "В аренде", "contacts": "+66 81 234 5678", "bike": BIKE, "booking_id": "bk-1",
              "date_start": "2026-09-30", "date_end": "2026-10-07"}


def adapter(script, doors=None, book=None, history=None, price=None, fresh=None, clock=None, tools=True):
    a = M.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=clock or Clock(), log=LOG.append,
                       book=book, tools=(doors or {}) if tools else None, fresh=fresh)
    info = {"price": price, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0}
    a.build = lambda number, upto_id, now=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: (history if history is not None else
                                          [{"who": "клиент", "text": "оплатил 4900 бат за аренду"}], [])
    a.knowledge.snap["business_rules"] = {"name": "business_rules", "read": True,
                                          "text": "… 03.10.2026-1 Решения владельца …", "len": 40}
    return a


LOG = []


def reasons(out):
    return out["handoff"] if isinstance(out, dict) else None


# ------------------------------- 1. оплата подтверждена кассой и договором -------------------------------

def test_paid_confirmed_by_cash_and_contract():
    s = Script({"tool": "cash", "args": {"bike": BIKE}}, {"tool": "contract", "args": {"phone": NUMBER}},
               final("Оплата 4900 бат получена, спасибо!"))
    # строка кассы — ТОЙ ЖЕ аренды, к которой код привязал договор (bk-2, ADV 8004): до AGENTDEDUP0410 фикстура
    # смешивала кассу аренды bk-1 с договором аренды bk-2 и считалась подтверждением — ровно дефект П2
    ivan = dict(tx_item(booking_id="bk-2"), bike="ADV 750 8004")
    a = adapter(s, {"cash": lambda **kw: tx([ivan]), "contract": lambda **kw: CONTRACT_ONE},
                book=Book([RENTAL_IVAN]))
    out = a.draft(NUMBER, 5)
    assert T.PAY_WORDS not in reasons(out), reasons(out)
    assert K.MONEY_CLAIM_WORDS not in reasons(out), reasons(out)        # 4900 — опора из факта кассы
    facts = a.last["tools"]["journal"].facts
    assert any(f["kind"] == "cash" and f["role"] == T.R_RENT and f["row"] == 2 for f in facts)
    assert a.last["figures"]["sums"] == {"оплата аренды THB": 4900}


def test_paid_confirmed_by_rental_plus_chat_amount():
    s = Script({"tool": "cash", "args": {}}, {"tool": "rental", "args": {}}, {"tool": "history", "args": {}},
               final("Оплата получена: 4900 бат."))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()])}, book=Book([RENTAL_ROW]))
    assert T.PAY_WORDS not in reasons(a.draft(NUMBER, 5))


def test_clients_sheet_alone_is_not_contract():
    s = Script({"tool": "cash", "args": {}}, {"tool": "rental", "args": {}}, final("Оплата получена: 4900 бат."))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()])}, book=Book([RENTAL_ROW]),
                history=[{"who": "клиент", "text": "привет"}])
    assert T.PAY_WORDS in reasons(a.draft(NUMBER, 5))                  # лист без договорённости в переписке


# ------------------------------- 2. записи нет -------------------------------

def test_no_cash_record_payment_not_confirmed():
    s = Script({"tool": "cash", "args": {"bike": BIKE}}, final("Оплата получена, всё в порядке."))
    a = adapter(s, {"cash": lambda **kw: tx([])})
    out = a.draft(NUMBER, 5)
    assert reasons(out)[0] == T.PAY_WORDS, reasons(out)
    res = a.last["tools"]["results"][0]
    assert res["outcome"] == T.EMPTY and "проводок нет" in res["reason"]


def test_no_tools_called_payment_not_confirmed():
    a = adapter(Script(final("Payment received, thank you!")), {})
    assert T.PAY_WORDS in reasons(a.draft(NUMBER, 5))


# ------------------------------- 3. возврат записан -------------------------------

def test_refund_recorded_forbids_will_return():
    items = [tx_item(), tx_item(row=3, amount=-1000, category="rental", description="возврат залога Nmax 6908")]
    s = Script({"tool": "cash", "args": {}}, final("Залог вернём при сдаче байка."))
    a = adapter(s, {"cash": lambda **kw: tx(items)})
    out = a.draft(NUMBER, 5)
    assert T.ROLE_WORDS in reasons(out), reasons(out)
    assert any("возврат уже записан" in c for c in a.last["tools"]["journal"].conflicts)


# ------------------------------- 4. суммы расходятся -------------------------------

def test_sums_disagree():
    row = dict(RENTAL_ROW, price=5000)
    s = Script({"tool": "cash", "args": {}}, {"tool": "rental", "args": {}}, final("Спасибо, ждём вас!"))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()])}, book=Book([row]))
    out = a.draft(NUMBER, 5)
    assert T.SUMS_WORDS in reasons(out), reasons(out)
    assert a.last["figures"]["diffs"] == [{"what": "цена аренды минус оплата", "currency": "THB", "value": 100}]


# ------------------------------- 5. источник молчит -------------------------------

def test_source_silent_timeout_is_not_fact():
    def dead(**kw):
        raise TimeoutError("молчит")
    s = Script({"tool": "cash", "args": {}}, final("Оплата получена."))
    a = adapter(s, {"cash": dead})
    out = a.draft(NUMBER, 5)
    res = a.last["tools"]["results"][0]
    assert res["outcome"] == T.TIMEOUT and res["facts"] == []
    assert T.PAY_WORDS in reasons(out)
    assert any("cash: timeout" in r for r in a.last["tools"]["journal"].refusals)


def test_door_not_deployed_is_unknown():
    s = Script({"tool": "contract", "args": {"phone": NUMBER}}, final("Ок"))
    a = adapter(s, {"contract": lambda **kw: {"ok": False, "error": "unknown_action"}})
    a.draft(NUMBER, 5)
    assert a.last["tools"]["results"][0]["outcome"] == T.UNKNOWN


# ------------------------------- 6. выборка неполная -------------------------------

def test_incomplete_selection_83ee219_shape():
    s = Script({"tool": "cash", "args": {}}, {"tool": "contract", "args": {}}, final("Оплата 4900 бат получена."))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()], complete=None), "contract": lambda **kw: CONTRACT_ONE})
    out = a.draft(NUMBER, 5)
    res = a.last["tools"]["results"][0]
    assert res["outcome"] == T.INCOMPLETE and "до TXFINDFIX" in res["reason"], res
    assert T.PAY_WORDS in reasons(out)                                # неполная выборка оплату не подтверждает


def test_incomplete_truncated():
    r = T.cash_result(tx([tx_item()], complete=True, truncated=True))
    assert r["outcome"] == T.INCOMPLETE


def test_total_never_confirms():
    r = T.cash_result(tx([], complete=True))
    assert r["outcome"] == T.EMPTY and T.accepted([r]) == []          # total 999999 не факт


def test_cash_row_without_source_rejected():
    it = tx_item()
    it["msg_id"] = it["link"] = None
    r = T.cash_result(tx([it]))
    assert r["outcome"] == T.EMPTY and "без источника" in r["reason"]


def test_cancelled_rows():
    r = T.cash_result(tx([tx_item(status="void")]))
    assert r["outcome"] == T.CANCELLED


# ------------------------------- 7. денежные роли -------------------------------

def test_rent_payment_is_not_deposit():
    s = Script({"tool": "cash", "args": {}}, {"tool": "contract", "args": {}}, final("Залог получен, спасибо."))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()]), "contract": lambda **kw: CONTRACT_ONE})
    assert T.ROLE_WORDS in reasons(a.draft(NUMBER, 5))


def test_deposit_role_from_words():
    it = tx_item(row=4, amount=3000, description="залог наличными Nmax 6908")
    assert T.role_of(it) == T.R_DEPOSIT
    assert T.role_of(tx_item()) == T.R_RENT
    assert T.role_of(tx_item(amount=-500, category="other", description="возврат сдачи")) == T.R_REFUND


def test_change_only_at_end_with_deposit():
    bad = T.money_roles("Сдачу переведём завтра.", [])
    ok = T.money_roles("Сдачу отдадим в конце аренды, с возвратом залога.", [])
    assert any("сдача" in why for _w, why in bad) and ok == []
    assert T.money_roles("Байк ждём при сдаче байка в 18:00.", []) == []    # сдача байка — не деньги


# ------------------------------- 8. новое входящее посреди сверки -------------------------------

def test_new_inbound_mid_verification_aborts():
    seen = []

    def fresh(number, upto):
        seen.append(upto)
        return len(seen) >= 2                     # пришло после первого вызова инструмента
    s = Script({"tool": "cash", "args": {}}, {"tool": "contract", "args": {}}, final("Ок"))
    a = adapter(s, {"cash": lambda **kw: tx([tx_item()]), "contract": lambda **kw: CONTRACT_ONE}, fresh=fresh)
    assert a.draft(NUMBER, 5) is None
    assert a.last["tools"]["state"] == T.ABORTED and len(s.seen) == 1


# ------------------------------- 9. неизвестный документ -------------------------------

def test_unknown_document_refused():
    s = Script({"tool": "contract_pdf", "args": {"file_id": "чужой"}}, final("Договор во вложении."))
    a = adapter(s, {"contract_pdf": lambda **kw: {"ok": False, "error": "not_in_registry"}})
    a.draft(NUMBER, 5)
    r = a.last["tools"]["results"][0]
    assert r["outcome"] == T.REFUSED and r["reason"] == "not_in_registry" and r["facts"] == []


def test_unknown_tool_refused():
    r = T.call_tool("sheets_write", {}, {"sheets_write": lambda **kw: {"ok": True}})
    assert r["outcome"] == T.REFUSED and r["reason"] == "неизвестный инструмент"


def test_pdf_content_never_kept():
    r = T.pdf_result({"ok": True, "verified": True, "id": "pdf-7", "name": "TB-0007.pdf", "size": 3,
                      "sha256": "ab", "content_b64": "QUJD", "row": 7}, allowed={"pdf-7"})
    assert r["outcome"] == T.FACT and "content_b64" not in json.dumps(r)


def test_ambiguous_contract_and_rental():
    amb = T.contract_result({"ok": True, "outcome": "ambiguous", "checked": {}})
    rent = T.rental_result({"ok": True, "rows": [RENTAL_ROW, dict(RENTAL_ROW, booking_id="bk-2")]})
    assert amb["outcome"] == T.AMBIGUOUS and rent["outcome"] == T.AMBIGUOUS


def test_delivery_unknown():
    r = T.call_tool("delivery", {}, {"delivery": lambda **kw: {"ok": True}})
    assert r["outcome"] == T.UNKNOWN


def test_rules_fact_sees_rule_0310():
    s = Script({"tool": "rules", "args": {}}, final("Ок"))
    a = adapter(s, {})
    a.draft(NUMBER, 5)
    r = a.last["tools"]["results"][0]
    assert r["outcome"] == T.FACT and r["facts"][0]["rule_0310"] is True


# ------------------------------- пределы -------------------------------

def test_call_limit_falls_back_to_plain_draft():
    s = Script({"tool": "history", "args": {}})          # модель не останавливается
    plain = final("Здравствуйте! Уточню и вернусь.")

    def call(system, user):
        if user == "USER":                                # обычный вызов без блока инструментов
            return json.dumps(plain, ensure_ascii=False), {"in": 1, "out": 1}
        return s(system, user)
    a = adapter(call, {})
    out = a.draft(NUMBER, 5)
    assert T.MAX_CALLS == 8 and T.MAX_SEC == 90.0                      # пределы задания, не «что в модуле»
    assert a.last["tools"]["state"] == T.OVER and a.last["tools"]["calls"] == 8
    assert reasons(out)[0] == T.INCOMPLETE_WORDS and out["text"] == plain["text"]


def test_time_limit_90s():
    s = Script({"tool": "history", "args": {}}, final("Ок"))
    clk = Clock(step=50.0)                                # каждый взгляд на часы — +50 с
    plain = []

    def call(system, user):
        if user == "USER":
            plain.append(1)
            return json.dumps(final("Без сверки."), ensure_ascii=False), {"in": 1, "out": 1}
        return s(system, user)
    a = adapter(call, {}, clock=clk)
    out = a.draft(NUMBER, 5)
    assert a.last["tools"]["state"] == T.OVER
    assert a.last["tools"]["calls"] < T.MAX_CALLS
    # AGENTDEDUP0410: предел 90 с — на ВСЮ сверку с запасным вызовом; часы ушли за дедлайн — запасной не начат
    assert out is None and plain == [] and a.last["fallback"] is False


def test_time_limit_leaves_room_for_fallback():
    """Сверка встаёт за FALLBACK_SEC до дедлайна — запасной обычный вызов успевает начаться в пределе."""
    s = Script({"tool": "history", "args": {}}, final("Ок"))
    clk = Clock()

    def call(system, user):
        if user == "USER":
            assert clk.t < 1790000000.0 + T.MAX_SEC
            return json.dumps(final("Без сверки."), ensure_ascii=False), {"in": 1, "out": 1}
        clk.t += T.MAX_SEC - T.FALLBACK_SEC                   # модель думала до остатка запасному
        return s(system, user)
    a = adapter(call, {}, clock=clk)
    out = a.draft(NUMBER, 5)
    assert a.last["tools"]["state"] == T.OVER and reasons(out)[0] == T.INCOMPLETE_WORDS


# ------------------------------- опора money_claims -------------------------------

def test_bare_number_near_money_word_judged():
    assert ("число", 3500) in T.money_claims("Залог 3500, оплата на месте.", None, set())
    assert T.money_claims("Залог 3500, оплата на месте.", None, {3500}) == []
    assert T.money_claims("Цена PCX 160 на 7 дней уточню.", None, set()) == []
    assert T.money_claims("Байк PCX 160 свободен.", None, set()) == []


def test_support_is_price_facts_calc():
    price = {"line": "ЦЕНА: 2 800 ฿ за сутки"}
    facts = [{"kind": "cash", "role": T.R_RENT, "currency": "THB", "amount": 4900}]
    fig = T.calc(facts)
    known = T.known_amounts(price, facts, fig)
    assert {2800, 4900} <= known
    assert T.money_claims("Итого 2800 бат в сутки, оплачено 4900 бат.", price, known) == []
    assert ("сумма", 7000) in T.money_claims("Итого 7000 бат.", price, known)


# ------------------------------- журнал -------------------------------

def test_journal_no_pii_no_model_text():
    LOG.clear()
    s = Script({"tool": "contract", "args": {"phone": "+66 81 234 5678", "name": "Иван Петров"}},
               final("СЕКРЕТНЫЙ-ТЕКСТ-МОДЕЛИ"))
    a = adapter(s, {"contract": lambda **kw: CONTRACT_ONE}, book=Book([RENTAL_IVAN]))
    a.draft(NUMBER, 5)
    blob = "\n".join(LOG)
    assert "вызов 1 contract" in blob and "→ fact" in blob and "реестр подписей" in blob
    assert "5678" in blob and "234 5678" not in blob and "Иван" not in blob and "Петров" not in blob
    assert "Ivan" not in blob and "Petrov" not in blob and "66812345678" not in blob
    assert "СЕКРЕТНЫЙ-ТЕКСТ-МОДЕЛИ" not in blob
    assert "факт {" in blob and "+66" not in blob


def test_journal_lists_conflicts_and_refusals():
    LOG.clear()
    s = Script({"tool": "cash", "args": {}}, {"tool": "delivery", "args": {}}, final("Оплата получена."))
    a = adapter(s, {"cash": lambda **kw: tx([])})
    a.draft(NUMBER, 5)
    blob = "\n".join(LOG)
    assert "отказ cash: empty" in blob and "отказ delivery: unknown" in blob and "конфликт" in blob


# ------------------------------- 6. флаг выкл = 9c4aac6 -------------------------------

def _base_module():
    try:
        src = subprocess.run(["git", "-C", ROOT, "show", "9c4aac6:wa_agent_model.py"], capture_output=True,
                             check=True, timeout=30).stdout.decode("utf-8")
    except Exception:                                                # noqa: BLE001
        return None
    mod = types.ModuleType("wa_agent_model_base")
    mod.__file__ = os.path.join(ROOT, "wa_agent_model.py")
    exec(compile(src, "9c4aac6:wa_agent_model.py", "exec"), mod.__dict__)
    return mod


GOLDEN_REPLIES = [
    final("Здравствуйте! Байк свободен, цена 2800 бат в сутки."),
    final("Оплата получена, залог вернём."),
    {"text": "Hello", "handoff": ["нужна скидка"], "lang": "th", "why": "x"},
    "не JSON",
]


def _run_off(mod):
    out = []
    for reply in GOLDEN_REPLIES:
        log = []
        a = mod.ModelAdapter(":memory:-не-открывается", Script(reply), log=log.append, clock=Clock())
        info = {"price": {"line": "ЦЕНА: 2 800 ฿"}, "code_reasons": [{"words": "наличие"}],
                "price_words": "цена: number", "history_items": 1, "history_chars": 10, "masked": 0}
        a.build = lambda number, upto_id, now=None: ("SYSTEM", "USER", info)
        out.append((a.draft(NUMBER, 5), log))
    return out


def test_flag_off_golden_equals_9c4aac6():
    base = _base_module()
    if base is None:
        print("  ПРОПУЩЕНО: git show 9c4aac6 недоступен — голден не сверен (это НЕ зелёное)")
        return
    assert _run_off(M) == _run_off(base)


def test_flag_off_no_tools_module_import():
    a = M.ModelAdapter(":memory:", Script(final("x")), clock=Clock())
    assert a.tools is None and a.fresh is None


def test_svc_flag_wires_doors_only_when_on():
    import wa_agent_svc as S
    br = types.SimpleNamespace(tx_find=lambda **k: 1, contract_find=lambda **k: 2, contract_pdf=lambda **k: 3,
                               fleet=lambda: {}, quote_price=lambda **k: {}, _call=lambda *a, **k: {},
                               clients=lambda **k: {})
    env = {"queue_db": ":memory:"}
    off, _ = S.make_model(env, bridge=br, call=Script(final("x")))
    on, _ = S.make_model(env, bridge=br, call=Script(final("x")), tools=True)
    assert off.tools is None and sorted(on.tools) == ["cash", "contract", "contract_pdf"]
    assert S.F_TOOLS == "WA_AGENT_TOOLS" and S.F_TOOLS not in S.FLAGS


def main():
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    bad = 0
    for n in names:
        try:
            globals()[n]()
            print("PASS", n)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", n, type(e).__name__, str(e)[:300])
    print("%d/%d" % (len(names) - bad, len(names)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
