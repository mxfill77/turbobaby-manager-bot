"""Сумма к оплате из факта аренды — модели и судье (TB-PHILIPP-UPGRADE-1310, часть B «деньги»).

Класс. Факт аренды (`rental_result`) несёт итог «к оплате» листа «клиенты» (`to_pay`, колонка J, ReadClients.js:48/106),
но модели его не показывал никто: `_fact_ref` держит только ключи журнала, а блок «РАСЧЁТ КОДА» был только у сдачи
(и только при переданных наличных). На «сколько в целом?» черновик отвечал «коллега пришлёт сумму», хотя сумма лежала
в принятом факте (живой эпизод E02: модель видела {"kind": "rental", "booking_id": …, "currency": "THB"} при to_pay 7790).
Назови модель сумму сама — судья поднял бы «денежное утверждение без опоры»: `known_amounts` итог не знал.

Ремонт. `due_of` — итог аренды обращения (одна аренда, известная валюта, один положительный итог листа); `due_block` —
блок «РАСЧЁТ КОДА — к оплате» в запросе модели: сумма, валюта, РОЛЬ (итог ≠ подтверждение оплаты), источник и время
снимка, статус оплаты по кассе (`pay_verdict` со словами причины; касса не прочитана — «об оплате не утверждай ничего»)
и «реквизитов в фактах нет — не называй и не выдумывай». Тот же итог — опора чисел ответа, но ТОЛЬКО в предложении
итога (USEFUL1310 fix, находка M1 судьи по смыслу): первая редакция клала итог в общую опору `known_amounts`, и число
итога становилось «белым» в любом предложении — «Переведите 7790 бат на счёт 123-4-56789-0», «7790 бат на месте,
спасибо!» теряли единственную причину. Теперь множество `known_amounts` — прежнее (как на 306350b), итог едет при нём
отдельно (`.due` = `due_amount`), а `money_claims` засчитывает его, только если каждое предложение, где число судится, —
предложение итога
(`_DUE_SAY`: к оплате / итого / всего / стоимость / total / to pay / cost …) без реквизитов и слов получения денег
(`_DUE_NOT`: 8+ цифр подряд, слово реквизитов с номером, «получили», «пришло», «вижу», «received», «is with us» …), и
текст не называет его полученной оплатой (`pay_claimed`). Иначе число судится как до части B — без опоры.
USEFUL1310 A1 (приёмщик): реквизиты или слова получения денег в ЛЮБОМ предложении текста (не только в предложении с
числом итога) тоже снимают опору итога — «К оплате 7790 бат. Номер счёта: 1234567890.» судится без опоры.
Замки оплаты не тронуты: «получили 7790» без кассы и второго источника — по-прежнему «оплата не подтверждена сверкой».

Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на 306350b утвердительные падают по существу (у дерева нет
`due_of`/`due_block`, а `known_amounts` итога не знает). КОНТРОЛЬ и ОТРИЦАТЕЛЬНЫЙ — прежнее поведение и замки, которые
ремонт не задел: зелёные и на 306350b.
Всё на подменах: двери — ответы живого формата (строка листа «клиенты» — ключи ReadClients.js:95-115, строки кассы —
форма tx_find), модель — сценарий. Сети, моста, SQLite и подпроцессов нет; файлов набор не пишет."""
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

import wa_agent_knowledge as K      # noqa: E402
import wa_agent_model as M          # noqa: E402
import wa_agent_tools as T          # noqa: E402

NUMBER = "66812345678"
BK = "K3-BK-001"
T0 = 1791500000.0
DUE = "РАСЧЁТ КОДА — к оплате"                       # голова блока (литералом: на 306350b константы нет)
CHANGE = "РАСЧЁТ КОДА — сдача"                       # голова блока сдачи — её новый блок не несёт
NO_CASH = "касса не прочитана — об оплате не утверждай ничего"
NO_REQ = "реквизитов для оплаты (номер счёта, карта, QR) в фактах нет — не называй и не выдумывай"

# строка листа «клиенты» живого формата (ReadClients.js:95-115): итог «к оплате» J = to_pay, K = paid
ROW = {"row": 12, "status": "В аренде", "auto_cancel": "", "bike": "NMAX 155 90101", "name": "Тест Клиент",
       "date_start": "2026-10-05 10:00", "date_end": "2026-10-15 10:00", "duration": "10", "pay_per_day": 779,
       "debt": 0, "to_pay": 7790, "paid": 7790, "deposit": 3000, "deposit_raw": "3000", "helmets": "1",
       "contacts": "+66 81 234 5678", "note": "", "type": "мото", "booking_id": BK}


def tx_item(row=11, amount=7790, currency="THB", category="rental", booking=BK):
    d = "Nmax 90101 +%s аренда %s" % (amount, booking)
    return {"row": row, "date": "2026-10-05", "date_src": "msg_date", "recorded_at": "2026-10-05T03:10:00.000Z",
            "amount": amount, "amount_raw": str(amount), "amount_unparsed": False, "currency": currency,
            "category": category, "bike": "Nmax 90101", "deposit": "", "description": d, "raw": d,
            "msg_id": "-100311:501:m%d" % row, "link": "https://t.me/c/311/501/%d" % row, "status": "recorded",
            "booking_id": booking}


def tx(items, complete=True):
    return {"ok": True, "checked": {"span_from": "2026-10-05", "span_to": "2026-10-15", "rows_scanned": 40,
                                    "truncated": False, "complete": complete}, "items": list(items)}


def rental(row=None, age=300.0, at=T0, rows=None):
    """Результат `rental` ЖИВЫМ разбором (`rental_result`); снимок снят за `age` секунд до чтения (None — неизвестно)."""
    resp = {"ok": True, "rows": rows if rows is not None else [dict(ROW, **(row or {}))]}
    if age is not None:
        resp["_taken_at"] = at - age
    return dict(T.rental_result(resp, at=at), req="rental []")


def cash(items=(), at=T0 + 5, complete=True, resp=None):
    return dict(T.cash_result(resp if resp is not None else tx(items, complete), at=at), req="cash %s" % BK)


def contract(booking=BK, cur="THB", row=5):
    return {"tool": "contract", "outcome": T.FACT, "source": "реестр подписей", "ref": "K3-DOC-001", "at": T0 + 7,
            "version": "", "window": "", "reason": "", "read_at": T0 + 7, "req": "contract %s" % booking,
            "facts": [{"kind": "contract", "row": row, "doc_id": "K3-DOC-00%d" % row, "booking_id": booking,
                       "rent_currency": cur, "signed_at": "2026-10-05 10:12"}]}


def history(amounts=()):
    return {"tool": "history", "outcome": T.FACT, "source": "переписка WA", "ref": "строк 2", "at": T0 + 9,
            "version": "", "window": "", "reason": "", "read_at": T0 + 9, "req": "history []",
            "facts": [{"kind": "history", "items": 2, "amounts": sorted(amounts)}]}


def figures(facts):
    fig = T.calc(facts)
    fig["change"] = None
    return fig


# ═══ 1. due_of: итог аренды обращения ═══════════════════════════════════════════════════════════════════════════

def test_due_of_single_rental_total():
    d = T.due_of(T.accepted([rental()]))
    assert d == {"state": "ok", "booking_id": BK, "total": 7790, "currency": "THB"}, d


def test_due_of_no_rental_fact_none():
    """Фактов аренды среди принятых нет (переписка, касса; аренда пуста, отменена, неоднозначна, отказ) — None."""
    for res in ([history([7790])], [cash([tx_item()])], [rental(rows=[])],
                [rental(rows=[dict(ROW, status="Отмена")])],
                [rental(rows=[dict(ROW), dict(ROW, row=13, booking_id="K3-BK-002")])],
                [dict(T.rental_result({"ok": False, "error": "timeout"}, at=T0), req="rental []")]):
        assert T.due_of(T.accepted(res)) is None, [r["outcome"] for r in res]


def test_due_of_refusals_named():
    """Итог не назван (нет, ноль, отрицательный, не число, bool), аренда не одна, валюта неизвестна — отказ с причиной."""
    for bad in (None, 0, -100, "7790", True):
        d = T.due_of(T.accepted([rental({"to_pay": bad})]))
        assert d["state"] == "refused" and "не назван" in d["why"] and BK in d["why"], (bad, d)
    d = T.due_of(T.accepted([rental(), contract(booking="K3-BK-002")]))
    assert d["state"] == "refused" and "не одна" in d["why"], d
    d = T.due_of(T.accepted([rental(), contract(cur="USD")]))
    assert d["state"] == "refused" and "валюта" in d["why"] and "неизвестна" in d["why"], d


def test_due_of_sifted_facts_only():
    """Опора — отсеянное `accepted`: позднее «пусто» того же запроса снимает факт аренды — итога нет."""
    late = dict(T.rental_result({"ok": True, "rows": []}, at=T0 + 60), req="rental []")
    assert T.due_of(T.accepted([rental(), late])) is None


# ═══ 2. due_block: что видит модель ═════════════════════════════════════════════════════════════════════════════

def test_block_sum_role_source_status_requisites():
    """E02-класс: аренда прочитана, касса нет — сумма, роль, источник и время снимка, «касса не прочитана», «реквизитов нет»."""
    b = T.due_block([rental(age=300.0)])
    lines = b.split("\n")
    assert lines[0].startswith(DUE) and CHANGE not in b, b
    assert "аренда K3-BK-001: итог «к оплате» 7790 THB." in lines, b
    assert any("НЕ подтверждение оплаты" in s and "лист" in s for s in lines), b
    assert "источник: снимок броней (лист «клиенты»), снят 5 мин назад." in lines, b
    assert any(NO_CASH in s for s in lines), b
    assert NO_REQ + "." in lines, b


def test_block_snapshot_time_unknown_named():
    b = T.due_block([rental(age=None)])
    assert "время снимка неизвестно" in b and "7790 THB" in b, b


def test_block_cash_read_not_confirmed_reason_words():
    """Касса прочитана: строки нет / чужая аренда / другая валюта / нет второго источника — «НЕ подтверждена» с причиной
    `pay_verdict` слово в слово; и «получена», и «её нет» запрещены."""
    cases = [([], "в кассе нет строки оплаты аренды K3-BK-001"),
             ([tx_item(booking="K3-BK-002")], "в кассе нет строки оплаты аренды K3-BK-001"),
             ([tx_item(amount=220, currency="USD")], "валюта не совпала"),
             ([tx_item()], "нет второго источника той же аренды K3-BK-001")]
    for items, why in cases:
        res = [rental(), cash(items)]
        ok, verdict = T.pay_verdict(T.accepted(res))
        assert not ok and why in verdict, (items, verdict)
        b = T.due_block(res)
        assert ("оплата: кодом НЕ подтверждена — %s." % verdict) in b, b
        assert "Не пиши, что оплата получена, и не утверждай, что её нет." in b, b
        assert "7790 THB" in b and NO_CASH not in b, b


def test_block_cash_confirmed_by_code():
    """Строка кассы этой аренды + второй источник (договор либо та же сумма в переписке) — «подтверждена кодом»."""
    for extra in ([contract()], [history([7790])]):
        res = [rental(), cash([tx_item()])] + extra
        assert T.pay_verdict(T.accepted(res)) == (True, ""), extra
        b = T.due_block(res)
        assert "оплата: подтверждена кодом (строка кассы этой аренды и второй источник)." in b, b


def test_block_cash_not_read_named():
    """Касса звана, но не прочитана (отказ, неполная выборка, дверь не выложена) — «касса не прочитана» с исходом."""
    for res_cash, outcome in ((cash(resp={"ok": False, "error": "timeout"}), T.REFUSED),
                              (cash([tx_item()], complete=False), T.INCOMPLETE),
                              (cash(resp={"ok": False, "error": "unknown_action"}), T.UNKNOWN)):
        assert res_cash["outcome"] == outcome, res_cash["outcome"]
        b = T.due_block([rental(), res_cash])
        assert NO_CASH in b and ("cash: %s" % outcome) in b, b
        assert "подтверждена кодом" not in b and "НЕ подтверждена" not in b, b


def test_block_refusals_no_number():
    """Итог не назван / аренда не одна / валюта неизвестна — суммы в блоке нет, сказано «назовёт человек»."""
    for res in ([rental({"to_pay": None})], [rental(), contract(booking="K3-BK-002")], [rental(), contract(cur="USD")]):
        b = T.due_block(res)
        assert b.startswith(DUE) and "сумма к оплате НЕ названа кодом" in b and "назовёт человек" in b, b
        assert "7790" not in b and "итог «к оплате» 7790" not in b, b
        assert NO_REQ in b, b


def test_block_absent_without_rental_fact():
    """Граница: фактов аренды нет — блок пуст (в запрос модели не идёт)."""
    for res in ([], [history([7790])], [cash([tx_item()])], [rental(rows=[])]):
        assert T.due_block(res) == "", res


def test_block_crash_named_not_raised():
    """Расчёт упал — блок называет это и запрещает сумму; сверка не падает."""
    keep = T.rental_of
    try:
        T.rental_of = lambda facts: (_ for _ in ()).throw(RuntimeError("сбой"))
        b = T.due_block([rental()])
    finally:
        T.rental_of = keep
    assert b.startswith(DUE) and "НЕ посчитана (расчёт упал: RuntimeError)" in b and NO_CASH in b and NO_REQ in b, b


def _k3_pin():
    """Единственное закрепление отпечатков модуля — `M_PRINTS_ALL` в tests/test_k3_fix3_0910.py (USEFUL1310 fix, находка
    R1 проверяющего регрессий: здесь число не дублируется литералом — его читает разбор того файла, без импорта)."""
    import ast
    with open(os.path.join(HERE, "test_k3_fix3_0910.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "M_PRINTS_ALL" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("M_PRINTS_ALL в test_k3_fix3_0910.py не найден")


def test_block_names_free_of_fingerprints():
    """КОНТРОЛЬ отпечатков модуля: число скомпилированных выражений и строк-шаблонов `_P*`/`_ASK*` — то, что закреплено в
    tests/test_k3_fix3_0910.py (`M_PRINTS_ALL`, единственное место; новые выражения итога `_DUE_SAY`/`_DUE_NOT` там
    названы поимённо); константы блока `DUE_*` — обычные строки, не выражения и не строки-шаблоны."""
    pin = _k3_pin()
    rx = [n for n, v in vars(T).items() if hasattr(v, "pattern")]
    strs = [n for n, v in vars(T).items() if isinstance(v, str) and (n.startswith("_P") or n.startswith("_ASK"))]
    assert (len(rx), len(strs)) == (pin["T"][0], pin["T_str"][0]), (len(rx), len(strs), pin)
    due = [n for n in vars(T) if n.startswith("DUE")]
    assert due and all(isinstance(getattr(T, n), (str, tuple)) and not hasattr(getattr(T, n), "pattern")
                       for n in due), due


# ═══ 3. опора чисел ответа: итог — отдельно от общей опоры, только в предложении итога ═════════════════════════════

def test_due_amount_of_rental_not_in_known_amounts():
    """USEFUL1310 fix: итог — `due_amount`; множество опоры `known_amounts` его НЕ держит (как на 306350b), итог едет при
    нём отдельно (`.due`): иначе число итога было бы «белым» в любом предложении — в реквизитах и в подтверждении."""
    facts = T.accepted([rental()])
    known = T.known_amounts(None, facts, figures(facts))
    assert T.due_amount(facts) == 7790 and known.due == 7790 and 7790 not in known, (known, known.due)


def test_due_amount_only_when_due_ok():
    """ОТРИЦАТЕЛЬНЫЙ: итога нет, когда аренда не одна, валюта неизвестна, итог не назван или фактов аренды нет."""
    for res in ([rental(), contract(booking="K3-BK-002")], [rental(), contract(cur="USD")], [rental({"to_pay": None})],
                [history([7790])], []):
        facts = T.accepted(res)
        known = T.known_amounts(None, facts, figures(facts))
        assert T.due_amount(facts) is None and known.due is None and 7790 not in known, res


def test_money_claims_due_only_in_total_sentence():
    """`money_claims(…, due)`: итог — опора в предложении итога; в прочем предложении (реквизиты, «на месте») — как до
    части B; итог в двух предложениях, одно из которых — реквизиты, — без опоры; без `due` — прежний вывод."""
    assert T.money_claims("К оплате 7790 бат.", None, set(), 7790) == []
    assert T.money_claims("Итого 7 790 бат, реквизиты пришлёт коллега.", None, set(), 7790) == []
    assert T.money_claims("7790 бат на месте, спасибо!", None, set(), 7790) == [("сумма", 7790)]
    assert T.money_claims("К оплате 7790 бат, счёт Kasikorn 1234567890.", None, set(), 7790) == [("сумма", 7790)]
    assert T.money_claims("К оплате 7790 бат. Переведите 7790 бат на счёт 123-4-56789-0.", None, set(), 7790) == \
        [("сумма", 7790), ("сумма", 7790)]
    assert T.money_claims("К оплате 7790 бат.", None, set()) == [("сумма", 7790)]            # без итога — как было
    assert T.money_claims("7790 бат на месте, спасибо!", None, {7790}, 7790) == []        # опора и без итога — прежняя


def test_known_amounts_control_rest_unchanged():
    """КОНТРОЛЬ: без факта аренды опора прежняя — «ЦЕНА», суммы кассы, расчёты."""
    price = {"line": "ЦЕНА: 2 800 ฿ за сутки"}
    facts = [{"kind": "cash", "role": T.R_RENT, "currency": "THB", "amount": 4900}]
    assert T.known_amounts(price, facts, figures(facts)) == {2800, 4900}


# ═══ 4. судья: число итога в ответе RU/EN — с опорой; чужое число и «получили» — нет ═══════════════════════════

ANSWERS_OK = ("Сумма к оплате — 7790 бат.",
              "Итого за аренду 7 790 бат, реквизиты для оплаты пришлёт коллега.",
              "К оплате по вашей брони 7790 THB.",
              "Общая стоимость аренды — 7790 бат, оплатить можно переводом.",
              "The total to pay for your rental is 7790 THB.",
              "Your rental total is 7,790 baht; a colleague will send the payment details.")


def _judge(text, res):
    jr = T.Journal("5678")
    return T.judge(text, None, res, jr)[0]


def test_judge_total_named_has_support():
    for text in ANSWERS_OK:
        words = _judge(text, [rental(), cash([])])
        assert K.MONEY_CLAIM_WORDS not in words, (text, words)


def test_judge_other_number_still_claim():
    """ОТРИЦАТЕЛЬНЫЙ: сумма не равна итогу — без опоры, как было."""
    for text in ("Сумма к оплате — 7990 бат.", "The total to pay is 8500 THB.", "Итого за аренду 7 700 бат."):
        assert K.MONEY_CLAIM_WORDS in _judge(text, [rental(), cash([])]), text


def test_judge_total_without_due_still_claim():
    """ОТРИЦАТЕЛЬНЫЙ: аренда не одна — итог не опора, «7790» без опоры."""
    assert K.MONEY_CLAIM_WORDS in _judge("Сумма к оплате — 7790 бат.", [rental(), contract(booking="K3-BK-002")])


def test_judge_payment_lock_kept():
    """ОТРИЦАТЕЛЬНЫЙ, замок оплаты не ослаблен: «получили 7790» без строки кассы и второго источника — «оплата не
    подтверждена сверкой»
    (RU и EN), хотя 7790 теперь известная сумма."""
    for text in ("Оплату 7790 бат получили, спасибо!", "Да, 7790 получили.", "We received your payment of 7790 THB."):
        words = _judge(text, [rental(), cash([])])
        assert T.PAY_WORDS in words, (text, words)


# USEFUL1310 fix: 10 рискованных черновиков судьи по смыслу (accept_meaning/probe_money_fix.py) — дословно: итог «к
# оплате» 7790, касса пуста; на 306350b каждый получал «денежное утверждение без опоры», на 7dc20b5 — ни одной причины.
# USEFUL1310 A1 (приёмщик, useful2/accept/probe_accept.py): ещё 10 форм группы req_next_sentence — итог в СВОЁМ
# предложении, реквизиты в СОСЕДНЕМ — и 2 формы «получение денег в соседнем предложении без числа», дословно; на 306350b
# каждая — «без опоры», на 64e0748 — ни одной причины (опора судила только предложения с числом итога).
RISKY = ("7790 бат на месте, спасибо!", "Деньги на месте, 7790 бат.", "Ваши 7790 бат мы видим.",
         "7790 THB is with us, thanks!", "Got it, 7790 THB, thanks!",
         "Переведите 7790 бат на счёт 123-4-56789-0 Kasikorn.", "К оплате 7790 бат, счёт Kasikorn 1234567890.",
         "Оплата 7790 бат на PromptPay 0812345678.", "Total 7790 THB, bank account 123-4-56789-0 (SCB).",
         "Счёт для оплаты 1234567890, к оплате 7790.",
         # A1: реквизиты в соседнем предложении (группа req_next_sentence приёмщика, 10 из 10)
         "К оплате 7790 бат. Переведите на счёт 123-4-56789-0 Kasikorn.",
         "К оплате 7790 бат. Номер счёта: 1234567890 (Kasikorn).",
         "Итого за аренду 7790 бат. PromptPay: 0812345678.",
         "Total to pay: 7790 THB. Bank account: 123-4-56789-0 (SCB).",
         "К оплате 7790 бат.\nСчёт Kasikorn 123-4-56789-0, получатель TurboBaby.",
         "К оплате 7790 бат; счёт 1234567890.",
         "Счёт 1234567890 Kasikorn. К оплате 7790 бат.",
         "Сумма к оплате — 7790 бат. Карта для перевода 5536 9137 1234 5678.",
         "К оплате 7790 бат. Счёт 123-456.",
         "Your rental total is 7790 THB. Please transfer to account 123-4-56789-0.",
         # A1: получение денег в соседнем предложении, без числа
         "Оплатили вчера. К оплате 7790 бат.", "Total due 7790 THB. Thanks, we got it.")
# свои: итог и получение денег в ОДНОМ предложении; реквизиты короче 8 цифр; итог в двух предложениях
RISKY_MORE = ("Итого 7790 бат получили, спасибо!", "Всего 7790 бат пришло, спасибо.", "Total 7790 THB received, thanks!",
              "К оплате было 7790 бат — оплачено, спасибо.", "Итого 7790 бат — вижу ваш перевод.",
              "К оплате 7790 бат, счёт TEST-ACC-0042.", "Total 7790 THB, account TEST-ACC-0042.",
              "К оплате 7790 бат, PromptPay 081-000-0000.", "К оплате 7790 бат. Переведите 7790 бат на счёт 123-4-56789-0.")
USEFUL = ANSWERS_OK + ("К оплате за аренду 7790 бат.", "За 10 суток выходит 7790 бат.",
                       "The total for your rental is 7790 THB.",
                       "К оплате за аренду 7790 бат. Реквизиты для оплаты пришлёт коллега.",
                       "Итого 7790 бат, оплатить можно картой или наличными.",
                       "Total 7790 THB, you can pay by card or cash at pickup.")


def test_judge_risky_drafts_get_reason_back():
    """Итог — опора ТОЛЬКО в предложении итога: реквизиты (8+ цифр, слово реквизитов с номером), получение денег
    («на месте», «видим», «is with us», «got it», «получили», «пришло», «received») — «денежное утверждение без опоры»,
    как на 306350b; при кассе пустой и без кассы. USEFUL1310 A1: то же, когда реквизиты или получение денег стоят в
    СОСЕДНЕМ предложении, а итог — в своём."""
    for res in ([rental(), cash([])], [rental()]):
        for text in RISKY + RISKY_MORE:
            assert K.MONEY_CLAIM_WORDS in _judge(text, res), (text, [r["tool"] for r in res])


def test_judge_receipt_with_total_word_both_locks():
    """Подтверждение получения рядом со словом итога: и «без опоры», и замок оплаты — как на 306350b."""
    for text in ("Итого 7790 бат получили, спасибо!", "Total 7790 THB received, thanks!",
                 "Оплату 7790 бат получили, спасибо!", "We got your 7790 baht, all good."):
        words = _judge(text, [rental(), cash([])])
        assert K.MONEY_CLAIM_WORDS in words and T.PAY_WORDS in words, (text, words)


def test_judge_useful_totals_no_lock():
    """Польза части B цела: ответ с итогом в предложении итога — ни одной причины (RU/EN, способ оплаты словом)."""
    for text in USEFUL:
        assert _judge(text, [rental(), cash([])]) == [], text


def test_judge_e02_total_and_deposit_with_price():
    """E02-форма «к оплате 7790 + залог 3000»: залог — опора из «ЦЕНА» (в факте аренды залога нет), итог — из факта;
    причин нет. Без строки цены залог 3000 без опоры — как было и до правки."""
    price = {"line": "ЦЕНА: NMAX 155 | дней: 10, стоимость: 7790 (779 в день), депозит: 3000 бат"}
    for text in ("К оплате 7790 бат + залог 3000 бат.", "К оплате 7790 + залог 3000."):
        assert T.judge(text, price, [rental(), cash([])], T.Journal("5678"))[0] == [], text
        assert K.MONEY_CLAIM_WORDS in _judge(text, [rental(), cash([])]), text


# ═══ 5. цикл сверки: блок в запросе модели ═══════════════════════════════════════════════════════════════════════

class Script:
    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return json.dumps(a, ensure_ascii=False), {"in": 10, "out": 5}


def final(text):
    return {"text": text, "handoff": [], "lang": "ru", "why": "тест"}


class Clock:
    def __init__(self):
        self.t = T0

    def __call__(self):
        return self.t


def _doors(cash_items=(), rows=None):
    rows = [dict(ROW)] if rows is None else rows
    return {"rental": lambda: {"ok": True, "rows": [dict(r) for r in rows], "_taken_at": T0 - 120},
            "cash": lambda **kw: tx(cash_items)}


def test_run_block_after_rental_read():
    """До чтения аренды блока нет; после — есть, с итогом и «касса не прочитана»; после кассы — со статусом кассы."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final("ok"))
    T.run(s, "S", "U", _doors(), number=NUMBER, clock=Clock())
    assert len(s.seen) == 3 and DUE not in s.seen[0], s.seen[0]
    assert DUE in s.seen[1] and "итог «к оплате» 7790 THB" in s.seen[1] and NO_CASH in s.seen[1], s.seen[1][-900:]
    assert DUE in s.seen[2] and "кодом НЕ подтверждена — в кассе нет строки оплаты аренды K3-BK-001" in s.seen[2], s.seen[2]


def test_run_block_before_change_block():
    """Переданные наличные: блок к оплате стоит перед блоком сдачи; блок сдачи — тот же, что считает `change_block`."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final("ok"))
    out = T.run(s, "S", "U", _doors([tx_item()]), number=NUMBER, clock=Clock(), handed=[8000])
    last = s.seen[-1]
    assert DUE in last and CHANGE in last and last.index(DUE) < last.index(CHANGE), last[-1200:]
    assert last.endswith(T.change_block(out["results"], [8000])), last[-600:]


def test_run_control_no_rental_request_unchanged():
    """КОНТРОЛЬ: без факта аренды запрос модели — инструменты + запрос + результаты, байт-в-байт прежней формы."""
    s = Script({"tool": "cash", "args": {"booking_id": BK}}, final("ok"))
    out = T.run(s, "S", "U", _doors([tx_item()]), number=NUMBER, clock=Clock())
    head = (T.TOOLS_BLOCK % T.MAX_CALLS) + "\n\nU"
    assert s.seen == [head, head + "\n\n" + T.render(out["results"])], s.seen


def test_run_rental_without_total_no_number():
    """Факт аренды без итога (так его собирает и дело аренды К4, `rental_case_result`) — «сумма не названа», числа нет."""
    s = Script({"tool": "rental", "args": {}}, final("ok"))
    T.run(s, "S", "U", _doors(rows=[dict(ROW, to_pay=None)]), number=NUMBER, clock=Clock())
    assert DUE in s.seen[1] and "сумма к оплате НЕ названа кодом" in s.seen[1] and "7790" not in s.seen[1], s.seen[1]


# ═══ 6. адаптер: живой путь черновика (снимок броней → сверка → судья → карточка) ══════════════════════════════════

class Book:
    def __init__(self, rows, age=60.0):
        self.rows, self.age = rows, age

    def get(self, now):
        return self.rows, [], self.age, ""


def adapter(script, question, cash_items=()):
    a = M.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=Clock(), log=lambda *_: None,
                       book=Book([dict(ROW)]), tools={"cash": (lambda **kw: tx(cash_items))}, fresh=None)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0, "question": question}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": question}], [])
    return a


QUESTIONS = (("Дайте номер счета куда оплачивать баты и сколько в целом",
              "К оплате за аренду 7790 бат. Реквизиты для оплаты пришлёт коллега."),
             ("Сколько с меня за аренду?", "Итого за аренду 7 790 бат."),
             ("How much do I owe in total and where do I pay?",
              "Your rental total is 7790 THB; a colleague will send the payment details."))


def test_adapter_total_named_no_claim():
    """Живой путь: модель видит итог и называет его — числа карточки с опорой, «без опоры» нет (RU, EN, разные вопросы)."""
    for q, text in QUESTIONS:
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
        out = adapter(s, q).draft(NUMBER, 5)
        assert any(DUE in u and "итог «к оплате» 7790 THB" in u for u in s.seen), s.seen[-1][-900:]
        assert out and out["claims"] == [] and K.MONEY_CLAIM_WORDS not in out["handoff"], (q, out)


def test_adapter_payment_claim_still_reason():
    """ОТРИЦАТЕЛЬНЫЙ на живом пути: «оплату 7790 получили» без кассы — причина «оплата не подтверждена сверкой»."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
               final("Оплату 7790 бат получили, спасибо!"))
    out = adapter(s, "Я перевёл 7790, дошло?").draft(NUMBER, 5)
    assert out and T.PAY_WORDS in out["handoff"], out


def test_adapter_risky_total_claim_on_card():
    """ОТРИЦАТЕЛЬНЫЙ на живом пути (E02-вопрос): итог в реквизитах или в «на месте» — причина «без опоры», и низ карточки
    называет число (опора у судьи и у карточки одна: `known_amounts` с её итогом `.due`)."""
    for text in ("К оплате 7790 бат, счёт Kasikorn 1234567890.", "7790 бат на месте, спасибо!",
                 "Переведите 7790 бат на счёт 123-4-56789-0 Kasikorn."):
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
        out = adapter(s, QUESTIONS[0][0]).draft(NUMBER, 5)
        assert out and K.MONEY_CLAIM_WORDS in out["handoff"] and ["сумма", 7790] in out["claims"], (text, out)


def test_adapter_e02_total_then_account_sentence_claim_on_card():
    """ОТРИЦАТЕЛЬНЫЙ на живом пути, USEFUL1310 A1: E02-вопрос «Дайте номер счета куда оплачивать баты и сколько в
    целом», модель даёт итог своим предложением, а номер счёта — СЛЕДУЮЩИМ. Причина «денежное утверждение без опоры»
    есть, и claims непусты — низ карточки (`wa_agent_tg.card_check`: «числа сверены» только при пустых claims) называет
    число, а не «сверено»."""
    q = "Дайте номер счета куда оплачивать баты и сколько в целом"
    assert q == QUESTIONS[0][0]
    for text in ("К оплате 7790 бат. Номер счёта: 1234567890 (Kasikorn).",
                 "К оплате 7790 бат. Переведите на счёт 123-4-56789-0 Kasikorn."):
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
        out = adapter(s, q).draft(NUMBER, 5)
        assert any(DUE in u and "итог «к оплате» 7790 THB" in u for u in s.seen), s.seen[-1][-900:]
        assert out and K.MONEY_CLAIM_WORDS in out["handoff"], (text, out)
        assert out["claims"] and ["сумма", 7790] in out["claims"], (text, out)


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
