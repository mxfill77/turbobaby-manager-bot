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
USEFUL1310 A2 (V1 проверяющего, решение интегратора К3 — сужение): время и дата при слове «карта»/«счёт» номером не
являются («…по карте при выдаче в 10:00.»), а в СОСЕДНЕМ предложении слово получения не денег (передача байка,
подтверждение сообщения или брони, условие — `_DUE_NOPAY`) опору не снимает («…при получении байка.»); денежное
получение в соседнем предложении («Оплата поступила.», «Перевод дошёл.») запирает по-прежнему.
USEFUL1310 A3 (находки F1–F4 проверяющего X2, решение интегратора К3): подтверждение сообщения или брони и «Got it» не
прощаются, если само подтверждение несёт документ или деньги («Получили ваше сообщение с чеком.», «Got it, thanks for
the slip!») или следующее предложение эллиптически продолжает его деньгами («Получили ваше сообщение. Деньги тоже.»,
«Got your message. And the transfer too, thanks!»); время и дата не занимают слот окна реквизитов («Счёт до 18:00 по
номеру 1234567.» запирает); «all paid / paid in full / fully paid» — слова получения. USEFUL закрепляет каждую
альтернативу `_DUE_NOPAY` своей формой и формы дат (ДД.ММ, ДД.ММ.ГГГГ, ДД/ММ, ЧЧ:ММ, Ч.ММ): откат любой из них роняет
набор.
Замки оплаты не тронуты: «получили 7790» без кассы и второго источника — по-прежнему «оплата не подтверждена сверкой».
USEFUL1310 A4 (слепой судья 5 real, E02; решение интегратора К3): колонка J — ИТОГ аренды (стоимость аренды целиком),
а не «к оплате», не долг и не остаток: дверь `rental` видит только «В аренде», такие аренды обычно оплачены при выдаче.
Блок называет J «итог аренды (стоимость аренды целиком)», слов «к оплате» в нём нет, сумму велено не называть
«осталось оплатить», «долг» или «остаток»; оплачено ли — говорит только касса кодом или человек; «оплачено» (K) и «долг»
(I) листа в факт и модели не подаются. Залог строки (`deposit_raw`, колонка S) — отдельной строкой блока: «залог: N THB,
возвратный, в итог не входит» либо «залог: паспорт», с ролью; без залога (или неразобранный) — строки нет, блок прежний,
кроме слов роли. Сумма залога — опора числа ответа только в предложении залога, где её не называют «к оплате», долгом
или остатком (`deposit_supported`); итог — как в A3 (только в предложении итога). Адаптерный случай E02 стенда (R1:
итог 7790, оплачено 7790, залог 3000): «Итого за аренду 7790 бат, залог 3000 бат (возвратный)» — без ложных замков,
«К оплате 7790, вы уже оплатили» — заперт.
USEFUL1310 A5 (находки V1–V4 проверяющего X3 и judge3b; решение интегратора К3, минимально): (а) окно реквизитов,
перешагнувшее время/дату, номером берёт только номер от 5 цифр («в 10:00, 2 шлема», «7 дней в неделю», «за 3 дня» —
не реквизиты; «до 18:00: 1234567» — реквизиты); (б) зачин «и/а/and/plus + деньги» больше не эллипсис денег (остались
«тоже/также/too/as well»); (в) при неподтверждённой кодом оплате черновик о деньгах несёт карточке предложения о
деньгах, их получении или платёжном документе дословно (`money_said`, до двух) — строка сверки человеком, не замок; (г)
штамп карточки — только установленное: какие числа и с какой опорой (`money_backing`: блок «ЦЕНА», итог аренды кода,
залог аренды кода, факты сверки кода); чисел нет — штампа нет. Секция 7; зубы — мутанты в памяти
(useful3/fix5/teeth5.py).
USEFUL1310 A6 (находки V1–V5 проверяющего X4 и F1–F5 проверяющего X5; решение интегратора К3, минимально): опора числа
залога A4 ОТКАЧЕНА — число залога в черновике без опоры («денежное утверждение без опоры», строка «без опоры»), как на
A3; строка залога в блоке модели осталась, но названа дополнением строки «АРЕНДА КЛИЕНТА» (V4), сырьё «3.000» строки
не даёт (V5); аванс/предоплата/наличные/cash/deposit/advance/prepay — в прежний класс денежных существительных (F1);
строка сверки цитирует только предложения с денежным словом или платёжным документом, первыми — получение с деньгами и
эллипсис денег (F2, F4). Тесты A4 об опоре залога перевёрнуты поимённо (секция 2b и адаптер E02); секция 8.
USEFUL1310 A7 (находки W1, W2, W4, W5 проверяющего X6; решение интегратора К3, последний адресный раунд): строка
сверки снова берёт предложение со словом получения, как на A5, кроме голого междометия-подтверждения без объекта
(«Got it!», «Понял!» — готовая форма модуля «ответ целиком из согласия»); порядок — получение с деньгами и эллипсис,
затем получение, затем прочие о деньгах (W1); слова F1 — только строке сверки, эллипсис судьи — как на A5 (W2); сырьё
«3.000,00» строки залога не даёт (W4). Ожидания A6 изменены поимённо (секции 7, 8); секция 9.

Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на 306350b утвердительные падают по существу (у дерева нет
`due_of`/`due_block`, а `known_amounts` итога не знает). КОНТРОЛЬ и ОТРИЦАТЕЛЬНЫЙ — прежнее поведение и замки, которые
ремонт не задел: зелёные и на 306350b.
Всё на подменах: двери — ответы живого формата (строка листа «клиенты» — ключи ReadClients.js:95-115, строки кассы —
форма tx_find), модель — сценарий. Сети, моста, SQLite и подпроцессов нет; файлов набор не пишет."""
import json
import os
import re
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
DUE = "РАСЧЁТ КОДА — итог аренды"                    # голова блока (литералом; до A4 — «РАСЧЁТ КОДА — к оплате»)
CHANGE = "РАСЧЁТ КОДА — сдача"                       # голова блока сдачи — её новый блок не несёт
NO_CASH = "касса не прочитана — об оплате не утверждай ничего"
NO_REQ = "реквизитов для оплаты (номер счёта, карта, QR) в фактах нет — не называй и не выдумывай"
TOTAL = "итог аренды (стоимость аренды целиком) 7790 THB"   # A4: J — итог аренды, а не «к оплате»
DEP_HEAD = "по листу «клиенты»: залог"                      # A6 (V4): дополнение строки «АРЕНДА КЛИЕНТА»
DEP_LINE = DEP_HEAD + " 3000 THB, возвратный, в итог не входит"  # A4: залог деньгами — отдельной строкой
DEP_PASS = DEP_HEAD + " — паспорт"                          # A4: залог паспортом
PAYABLE = "к оплате"                                        # A4: этих слов в блоке нет

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
    """E02-класс: аренда прочитана, касса нет — сумма, роль, залог, источник и время снимка, «касса не прочитана»,
    «реквизитов нет». A4: сумма названа итогом аренды, а не «к оплате»."""
    b = T.due_block([rental(age=300.0)])
    lines = b.split("\n")
    assert lines[0].startswith(DUE) and CHANGE not in b and PAYABLE not in b.lower(), b
    assert "аренда K3-BK-001: %s." % TOTAL in lines, b
    assert any("НЕ подтверждение оплаты" in s and "лист" in s for s in lines), b
    assert any(s.startswith(DEP_LINE) for s in lines), b
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
        assert b.startswith(DUE) and "итог аренды НЕ назван кодом" in b and "назовёт человек" in b, b
        assert "7790" not in b and PAYABLE not in b.lower(), b
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
    assert b.startswith(DUE) and "НЕ посчитан (расчёт упал: RuntimeError)" in b and NO_CASH in b and NO_REQ in b, b
    assert PAYABLE not in b.lower(), b


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
    tests/test_k3_fix3_0910.py (`M_PRINTS_ALL`, единственное место; новые выражения итога `_DUE_SAY`/`_DUE_NOT`/
    `_DUE_NOPAY`/`_DUE_PROOF`/`_DUE_ALSO` и залога `_DEP_AS_DUE` (A4) там названы поимённо); константы блока `DUE_*` —
    обычные строки, не выражения и не строки-шаблоны."""
    pin = _k3_pin()
    rx = [n for n, v in vars(T).items() if hasattr(v, "pattern")]
    strs = [n for n, v in vars(T).items() if isinstance(v, str) and (n.startswith("_P") or n.startswith("_ASK"))]
    assert (len(rx), len(strs)) == (pin["T"][0], pin["T_str"][0]), (len(rx), len(strs), pin)
    due = [n for n in vars(T) if n.startswith("DUE")]
    assert due and all(isinstance(getattr(T, n), (str, tuple)) and not hasattr(getattr(T, n), "pattern")
                       for n in due), due


# ═══ 2a. USEFUL1310 A4: итог — не «к оплате»; залог отдельной строкой; лист «оплачено/долг» модели не подаётся ═══

NO_DEP = {"deposit": 0, "deposit_raw": ""}
PASSPORT = {"deposit": 0, "deposit_raw": "passport"}


def test_a4_block_deposit_money_passport_none():
    """Блок на фактах с залогом деньгами / паспортом / без залога: строка залога ровно одна (деньги — сумма, валюта,
    «возвратный, в итог не входит», роль; паспорт — «залог: паспорт», роль, «суммы залога не называй»), без залога — её
    нет; слов «к оплате» в блоке нет ни в одном случае (касса не прочитана и касса пуста). A6 (V4): обе строки залога —
    дополнение строки «АРЕНДА КЛИЕНТА» (таблица броней залога не знает, лист «клиенты» его называет)."""
    for extra in ([], [cash([])]):
        money = T.due_block([rental()] + extra).split("\n")
        dep = [s for s in money if s.startswith(DEP_HEAD)]
        assert len(dep) == 1 and dep[0].startswith(DEP_LINE) and "роль:" in dep[0], money
        assert "а не плата за аренду" in dep[0] and "касса кодом или человек" in dep[0], dep
        assert T.DUE_DEP_SUPPL in dep[0] and "«АРЕНДА КЛИЕНТА»" in dep[0], dep
        pas = T.due_block([rental(PASSPORT)] + extra).split("\n")
        dep = [s for s in pas if s.startswith(DEP_HEAD)]
        assert len(dep) == 1 and dep[0].startswith(DEP_PASS) and "роль:" in dep[0], pas
        assert "суммы залога не называй" in dep[0] and "3000" not in "\n".join(pas), pas
        assert T.DUE_DEP_SUPPL in dep[0], dep
        none = T.due_block([rental(NO_DEP)] + extra).split("\n")
        assert not [s for s in none if "залог" in s], none
        for b in (money, pas, none):
            assert PAYABLE not in "\n".join(b).lower() and "аренда K3-BK-001: %s." % TOTAL in b, b


def test_a4_role_words():
    """Роль суммы: итог аренды — стоимость аренды целиком; НЕ «осталось оплатить», НЕ долг, НЕ остаток, НЕ подтверждение
    оплаты; оплачено ли — только касса кодом или человек. Прежнее «называй её, когда клиент спрашивает, сколько платить»
    снято."""
    b = T.due_block([rental()])
    role = [s for s in b.split("\n") if s.startswith("роль суммы:")]
    assert len(role) == 1, b
    r = role[0]
    for w in ("стоимость этой аренды целиком", "НЕ сумма, которую клиенту осталось оплатить", "НЕ долг", "НЕ остаток",
              "НЕ подтверждение оплаты", "«осталось оплатить», «долг» или «остаток» её не называй",
              "Оплачено ли — говорит только касса кодом", "или человек"):
        assert w in r, (w, r)
    assert "сколько платить" not in b and PAYABLE not in b.lower(), b


def test_a4_block_without_deposit_same_lines_as_before():
    """Обратная совместимость: строки без залога — блок прежний, кроме слов роли: те же шесть строк в том же порядке
    (голова, итог, роль, источник, оплата, реквизиты); источник, оплата и реквизиты — дословно прежние."""
    for extra, pay in (([], "оплата: " + NO_CASH + "."),
                       ([cash([])], "оплата: кодом НЕ подтверждена — в кассе нет строки оплаты аренды K3-BK-001. "
                                    "Не пиши, что оплата получена, и не утверждай, что её нет.")):
        lines = T.due_block([rental(NO_DEP)] + extra).split("\n")
        assert len(lines) == 6 and lines[0] == T.DUE_HEAD and lines[2] == T.DUE_ROLE + ".", lines
        assert lines[3:] == ["источник: снимок броней (лист «клиенты»), снят 5 мин назад.", pay, NO_REQ + "."], lines


def test_a4_deposit_unparsed_no_line_no_support():
    """Сырьё залога смешанное («7000 passport» — правило: деньги ЛИБО паспорт), ноль, мусор, расходится с числом моста,
    клетки нет — строки залога нет (блок как без залога). Валюта аренды неизвестна или аренда не одна — строки залога
    деньгами нет. A6 (V5 проверяющего X4): «3.000» (одна точка и ровно три цифры за ней; мост читает его как 3) — строки
    нет, а не «залог: 3 THB»; «3000.00» — по-прежнему 3000."""
    plain = T.due_block([rental(NO_DEP)])
    for row in ({"deposit": 7000, "deposit_raw": "7000 passport"}, {"deposit": 0, "deposit_raw": "0"},
                {"deposit": 0, "deposit_raw": "есть"}, {"deposit": 2500, "deposit_raw": "3000"},
                {"deposit": 3000, "deposit_raw": "3000 бат"}, {"deposit_raw": None},
                {"deposit": 3000, "deposit_raw": "1.2.3"}, {"deposit": 3, "deposit_raw": "3.000"},
                {"deposit_raw": "3.000"}, {"deposit": 30, "deposit_raw": "30.000"}):
        facts = T.accepted([rental(row)])
        assert T.deposit_of(facts) is None, row
        assert T.due_block([rental(row)]) == plain, row
    for res in ([rental(), contract(cur="USD")], [rental(), contract(booking="K3-BK-002")]):
        assert T.deposit_of(T.accepted(res)) is None and DEP_HEAD not in T.due_block(res), res
    assert T.deposit_of(T.accepted([rental({"deposit": 3000, "deposit_raw": "3 000"})]))["amount"] == 3000
    assert T.deposit_of(T.accepted([rental({"deposit": 3000, "deposit_raw": "3000.00"})]))["amount"] == 3000
    assert T.deposit_of(T.accepted([rental(PASSPORT)])) == {"kind": "passport", "booking_id": BK}


def test_a4_sheet_paid_debt_not_given_to_model():
    """Лист «оплачено» (K) и «долг» (I) оплату НЕ подтверждают и модели как факт не подаются: в факте аренды ключей
    `paid`/`debt` нет, их числа не стоят ни в блоке, ни в результатах инструментов, ни в запросе модели; блок говорит
    «касса не прочитана» / «кодом НЕ подтверждена», а не «оплачено»."""
    row = {"paid": 6666, "debt": 4444}
    res = [rental(row)]
    fact = T.accepted(res)[0]
    assert "paid" not in fact and "debt" not in fact and fact["deposit_raw"] == "3000", fact
    for text in (T.due_block(res), T.render(res), T.due_block(res + [cash([])])):
        assert "6666" not in text and "4444" not in text and "paid" not in text and "debt" not in text, text
    assert "оплата: " + NO_CASH in T.due_block(res), T.due_block(res)
    assert "оплата: кодом НЕ подтверждена" in T.due_block(res + [cash([])]), T.due_block(res + [cash([])])
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final("ok"))
    T.run(s, "S", "U", _doors(rows=[dict(ROW, **row)]), number=NUMBER, clock=Clock())
    assert DUE in s.seen[1] and DEP_LINE in s.seen[1], s.seen[1]
    assert not [u for u in s.seen if "6666" in u or "4444" in u], s.seen


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
# USEFUL1310 A2: ещё 4 формы — получение ДЕНЕГ в соседнем предложении (инварианты сужения: оно запирает по-прежнему).
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
         "Оплатили вчера. К оплате 7790 бат.", "Total due 7790 THB. Thanks, we got it.",
         # A2: инварианты сужения — получение ДЕНЕГ в соседнем предложении запирает итог по-прежнему
         "К оплате 7790 бат. Оплата поступила.", "К оплате 7790 бат. Деньги получили, спасибо.",
         "Total due 7790 THB. We received your payment.", "К оплате 7790 бат. Перевод дошёл.",
         # A3 (F1): получение денег за «подтверждением сообщения/брони» — эллипсис в следующем предложении и документ в
         # самом подтверждении (дословно verify2/out/cmp_attack.txt, mine_masked_receipt)
         "Got your message. And the transfer too, thanks! Total 7790 THB.",
         "Получили ваше сообщение. Деньги тоже. К оплате 7790 бат.",
         "Вижу вашу бронь. Оплата тоже на месте. К оплате 7790 бат.",
         "Получили ваше сообщение с чеком. К оплате 7790 бат.", "Вижу вашу бронь и чек. К оплате 7790 бат.",
         "Received your message with the slip. Total 7790 THB.", "Got it, thanks for the slip! Total 7790 THB.",
         # A3 (F2): время/дата в окне реквизитов слотом слова не считаются (mine_masked_clock, дословно)
         "К оплате 7790 бат. Переведите на карту до 15.10 по номеру 1234567.",
         "К оплате 7790 бат. Счёт до 18:00 по номеру 1234567.",
         # A3 (F4): «all paid / paid in full / fully paid / оплачено полностью» — слова получения
         "Received your booking, thanks — all paid. Total 7790 THB.",
         "Got your message — paid in full, thanks. Total 7790 THB.",
         "Got it — all paid. Total 7790 THB.", "Got it, paid in full! Total 7790 THB.",
         "Total 7790 THB. Fully paid, thanks.", "К оплате 7790 бат. Оплачено полностью.",
         # A3 (F3): «Got it» ПОСЛЕ итога — получение, прощается только ДО итога (verify2 attack_probe, money_more)
         "Total due 7790 THB. Got it, thanks!")
# свои: итог и получение денег в ОДНОМ предложении; реквизиты короче 8 цифр; итог в двух предложениях
RISKY_MORE = ("Итого 7790 бат получили, спасибо!", "Всего 7790 бат пришло, спасибо.", "Total 7790 THB received, thanks!",
              "К оплате было 7790 бат — оплачено, спасибо.", "Итого 7790 бат — вижу ваш перевод.",
              "К оплате 7790 бат, счёт TEST-ACC-0042.", "Total 7790 THB, account TEST-ACC-0042.",
              "К оплате 7790 бат, PromptPay 081-000-0000.", "К оплате 7790 бат. Переведите 7790 бат на счёт 123-4-56789-0.")
USEFUL = ANSWERS_OK + ("К оплате за аренду 7790 бат.", "За 10 суток выходит 7790 бат.",
                       "The total for your rental is 7790 THB.",
                       "К оплате за аренду 7790 бат. Реквизиты для оплаты пришлёт коллега.",
                       "Итого 7790 бат, оплатить можно картой или наличными.",
                       "Total 7790 THB, you can pay by card or cash at pickup.",
                       # A2/V2: номер, равный самому итогу, в соседнем предложении — не реквизит
                       "К оплате 7790 бат. Счёт к оплате: 7790 бат.",
                       # A2 (а): время при слове «карта» в соседнем предложении — не номер реквизитов
                       "К оплате 7790 бат. Оплатить можно по карте при выдаче в 10:00.",
                       # A2 (б): получение байка в соседнем предложении — не получение денег
                       "К оплате 7790 бат. Оплатить можно при получении байка.",
                       # A3 (F3): по форме на КАЖДУЮ альтернативу `_DUE_NOPAY` — только она прощает слово получения
                       "К оплате 7790 бат. Оплатить можно при получении.",            # «при получении…»
                       "К оплате 7790 бат. Для получения байка нужен паспорт.",       # «получения байка/ключей»
                       "Got it! The total for your rental is 7790 THB.",              # «Got it» ДО итога
                       "Получили ваш вопрос. К оплате 7790 бат.",                     # подтверждение сообщения
                       "Thanks, received your booking. Total 7790 THB.",              # подтверждение брони
                       "К оплате 7790 бат. Если вы уже оплатили, пришлите чек.",      # условие «если… оплатили»
                       "К оплате 7790 бат. После поступления оплаты коллега подтвердит бронь.",  # «после поступления»
                       "К оплате 7790 бат. По зачислении пришлём подтверждение.",     # «по зачислении»
                       # A3 (F3): даты и время при слове реквизитов — не номер (ДД.ММ, ДД.ММ.ГГГГ, ДД/ММ, ЧЧ:ММ, Ч.ММ)
                       "К оплате 7790 бат. Оплатить по карте можно до 25.10.",
                       "К оплате 7790 бат. Счёт пришлём до 25.10.2026.",
                       "К оплате 7790 бат. Счёт пришлём 25/10.",
                       "К оплате 7790 бат. Карту принимаем с 10:30.",
                       "К оплате 7790 бат. По карте с 9.30.",
                       # A3 (F1, решение К3): слово оплаты в ИНОМ предложении прощения подтверждения не снимает
                       "Got it! The total is 7790 THB. You can pay by transfer.",
                       "Получили ваш вопрос. Оплатить можно переводом. К оплате 7790 бат.")


def test_judge_risky_drafts_get_reason_back():
    """Итог — опора ТОЛЬКО в предложении итога: реквизиты (8+ цифр, слово реквизитов с номером), получение денег
    («на месте», «видим», «is with us», «got it», «получили», «пришло», «received») — «денежное утверждение без опоры»,
    как на 306350b; при кассе пустой и без кассы. USEFUL1310 A1: то же, когда реквизиты или получение денег стоят в
    СОСЕДНЕМ предложении, а итог — в своём; A2: сужение (время/дата, получение не денег) этих форм не задевает; A3:
    получение денег за подтверждением сообщения/брони (F1), номер после даты в окне реквизитов (F2), «all paid / paid
    in full» (F4) и «Got it» после итога запирают."""
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
    """Польза части B цела: ответ с итогом в предложении итога — ни одной причины (RU/EN, способ оплаты словом).
    USEFUL1310 A2: и когда в соседнем предложении стоит тот же итог («Счёт к оплате: 7790 бат.» — исключение «номер,
    равный итогу», V2), время при слове «карта» (а) или получение байка (б). USEFUL1310 A3: по форме на каждую
    альтернативу `_DUE_NOPAY` и на каждую форму даты/времени — откат любой из них роняет этот тест; слово оплаты в ином
    предложении, чем подтверждение, прощения не снимает."""
    for text in USEFUL:
        assert _judge(text, [rental(), cash([])]) == [], text


def test_judge_e02_total_and_deposit_with_price():
    """E02-форма «к оплате 7790 + залог 3000»: залог — опора из «ЦЕНА», итог — из факта; причин нет. Без строки цены
    залог 3000 без опоры — как было и до правки; USEFUL1310 A6: залог факта аренды опорой числа не является вовсе
    (опора A4 откачена)."""
    price = {"line": "ЦЕНА: NMAX 155 | дней: 10, стоимость: 7790 (779 в день), депозит: 3000 бат"}
    for text in ("К оплате 7790 бат + залог 3000 бат.", "К оплате 7790 + залог 3000."):
        assert T.judge(text, price, [rental(), cash([])], T.Journal("5678"))[0] == [], text
        assert K.MONEY_CLAIM_WORDS in _judge(text, [rental(), cash([])]), text


# USEFUL1310 A4 (г): залог деньгами — опора числа ответа только в предложении залога, где его не называют «к оплате»,
# остатком или долгом; реквизиты и получение денег в любом предложении снимают опору, как у итога.
# USEFUL1310 A6 (решение К3 по V1–V3 проверяющего X4): опора (г) ОТКАЧЕНА — у числа залога опоры нет нигде, как на A3.
DEP_OK = ("Итого за аренду 7790 бат, залог 3000 бат (возвратный)",
          "Итого за аренду 7790 бат, залог 3000 бат (возвратный).",
          "Стоимость аренды — 7790 бат. Залог — 3000 бат, он возвратный.",
          "Залог 3000 бат, вернём при возврате байка.",
          "Total for your rental is 7790 THB, refundable deposit 3000 THB.",
          "Залог: 3000 бат (возвратный), в итог аренды не входит.")
DEP_RISKY = ("К оплате 7790 бат + залог 3000 бат.", "Залог 3000 бат к оплате при выдаче.",
             "Deposit 3000 THB is due now.", "You owe a deposit of 3000 THB.", "Осталось оплатить залог 3000 бат.",
             "Долг по залогу 3000 бат.", "Залог 3000 бат получили, спасибо.",
             "Залог 3000 бат. Переведите на счёт 1234567890.",
             "Итого 3000 бат.", "Оплата 3000 бат.")
# A6: формы проверяющего X4 (verify4/out/a4_show.txt, дословно), которые на X4 прошли без MC: V1 — залог «внесите /
# с вас / подлежит оплате…» (13), V2 — залог внутри итога (6), V3 — залог «у нас / вернули / удержали» (11)
A6_V1 = ("Внесите залог 3000 бат.", "С вас залог 3000 бат.", "Нужно внести залог 3000 бат.",
         "Осталось внести залог 3000 бат.", "Залог 3000 бат подлежит оплате.",
         "Залог 3000 бат нужно оплатить при выдаче.", "Залог 3000 бат оплатите при получении байка.",
         "Доплатите залог 3000 бат.",
         "Залог 3000 бат переведите, пожалуйста.", "Залог 3000 бат ещё не внесён.", "Please pay the 3000 THB deposit.",
         "Deposit 3000 THB is payable now.", "Deposit: 3000 THB, please transfer it today.")
A6_V2 = ("Итого 7790 бат, из них залог 3000.", "Итого 7790 бат, включая залог 3000 бат.",
         "Total 7790 THB including the 3000 THB deposit.", "В итог 7790 бат входит залог 3000 бат.",
         "Итого 7790 бат: аренда и залог 3000 бат.", "Стоимость аренды 7790 бат, в том числе залог 3000 бат.")
A6_V3 = ("Залог 3000 бат у нас.", "Ваш залог 3000 бат уже у нас.", "Залог 3000 бат вы уже внесли.",
         "Залог 3000 бат на месте.", "We have your 3000 THB deposit.", "Залог 3000 бат мы вам уже вернули.",
         "Залог 3000 бат вернули вам вчера.", "Мы вернули вам залог 3000 бат.", "We refunded your 3000 THB deposit.",
         "Залог 3000 бат зачтём в оплату аренды.", "Из залога 3000 бат удержали за повреждение.")


def test_a6_judge_deposit_number_unbacked_again():
    """A6 (откат опоры A4): с залогом деньгами в факте аренды число залога — «денежное утверждение без опоры» в ЛЮБОМ
    предложении, как на A3: полезный «залог 3000 бат (возвратный)» и формы V1–V3 проверяющего X4 (касса пуста и касса
    не читана); в claims — число 3000 (сумма в батах либо голое число при денежном слове)."""
    for res in ([rental(), cash([])], [rental()]):
        for text in DEP_OK + A6_V1 + A6_V2 + A6_V3:
            assert K.MONEY_CLAIM_WORDS in _judge(text, res), (text, _judge(text, res))
    facts = T.accepted([rental(), cash([])])
    known = T.known_amounts(None, facts, figures(facts))
    for text in DEP_OK + A6_V1 + A6_V2 + A6_V3:
        assert [c for c in T.money_claims(text, None, known) if c[1] == 3000], text


def test_a4_judge_deposit_outside_deposit_sentence_claim():
    """ОТРИЦАТЕЛЬНЫЙ: залог назван «к оплате», долгом или остатком, рядом реквизиты или получение денег, или число
    залога без слова залога — «денежное утверждение без опоры»."""
    for res in ([rental(), cash([])], [rental()]):
        for text in DEP_RISKY:
            assert K.MONEY_CLAIM_WORDS in _judge(text, res), (text, _judge(text, res))


def test_a4_judge_no_money_deposit_no_support():
    """КОНТРОЛЬ: залога деньгами в факте нет (паспорт, нет залога, неразобранное сырьё) — число залога в любом
    предложении без опоры, как до A4."""
    for row in (PASSPORT, NO_DEP, {"deposit": 7000, "deposit_raw": "7000 passport"}):
        for text in DEP_OK:
            if "3000" in text:
                assert K.MONEY_CLAIM_WORDS in _judge(text, [rental(row), cash([])]), (row, text)


def test_a6_deposit_support_reverted_unit():
    """A6: опора залога A4 снята целиком — нет `deposit_supported`, `deposit_amount`, `_DEP_AS_DUE`, у `known_amounts`
    нет `.deposit`, у `money_claims` — аргумента залога; залог 3000 в множество опоры не входит; итог — как был.
    Строка залога в блоке модели (`deposit_of`) — осталась."""
    for name in ("deposit_supported", "deposit_amount", "_DEP_AS_DUE", "SRC_DEP"):
        assert not hasattr(T, name), name
    import inspect
    assert list(inspect.signature(T.money_claims).parameters) == ["text", "price", "known", "due"]
    assert T.money_claims("Залог 3000 бат.", None, set()) == [("сумма", 3000)]
    facts = T.accepted([rental()])
    known = T.known_amounts(None, facts, figures(facts))
    assert getattr(known, "deposit", None) is None and 3000 not in known and known.due == 7790, known
    assert T.deposit_of(facts) == {"kind": "money", "amount": 3000.0, "currency": "THB", "booking_id": BK}


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
    assert DUE in s.seen[1] and TOTAL in s.seen[1] and NO_CASH in s.seen[1], s.seen[1][-900:]
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
    assert DUE in s.seen[1] and "итог аренды НЕ назван кодом" in s.seen[1] and "7790" not in s.seen[1], s.seen[1]


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
        assert any(DUE in u and TOTAL in u for u in s.seen), s.seen[-1][-900:]
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
        assert any(DUE in u and TOTAL in u for u in s.seen), s.seen[-1][-900:]
        assert out and K.MONEY_CLAIM_WORDS in out["handoff"], (text, out)
        assert out["claims"] and ["сумма", 7790] in out["claims"], (text, out)


# USEFUL1310 A4: адаптерный случай E02 стенда (stand_filipp/data/DATA.md: R1 — итог 7790, оплачено 7790, залог 3000,
# K3-BK-001; касса случая пуста), вопрос клиента E02 дословно — «Дайте номер счета куда оплачивать баты и сколько в
# целом»
E02_Q = "Дайте номер счета куда оплачивать баты и сколько в целом"
E02_OK = "Итого за аренду 7790 бат, залог 3000 бат (возвратный)"
E02_PAID = "К оплате 7790, вы уже оплатили"
LOCKS = (K.MONEY_CLAIM_WORDS, T.PAY_WORDS, T.ROLE_WORDS, T.SUMS_WORDS)


def _e02_block(seen):
    """Блок «РАСЧЁТ КОДА — итог аренды» из последнего запроса модели (от головы до конца блока)."""
    u = seen[-1]
    i = u.index(DUE)
    return u[i:].split("\n\n")[0]


def test_a6_adapter_e02_block_kept_deposit_number_unbacked():
    """Живой путь на фактах E02 стенда: модель видит НОВЫЙ блок (итог аренды, залог 3000 отдельной строкой — A6:
    дополнением строки «АРЕНДА КЛИЕНТА», «к оплате» нет, «оплачено» листа нет). A6 (опора залога A4 откачена,
    ожидание перевёрнуто ПОИМЁННО — на X4 было «claims пусты, без опоры нет»): черновик «Итого за аренду 7790 бат, залог
    3000 бат (возвратный)» — «денежное утверждение без опоры» и сумма 3000 в claims, как на A3; итог 7790 — с опорой;
    ни «оплата не подтверждена», ни роли, ни «суммы расходятся»."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(E02_OK))
    out = adapter(s, E02_Q).draft(NUMBER, 5)
    block = _e02_block(s.seen)
    assert ("аренда K3-BK-001: %s." % TOTAL) in block and DEP_LINE in block and PAYABLE not in block.lower(), block
    assert T.DUE_DEP_SUPPL in block, block
    assert "оплата: кодом НЕ подтверждена — в кассе нет строки оплаты аренды K3-BK-001." in block, block
    assert out and out["claims"] == [["сумма", 3000]], out
    assert K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]
    assert not [w for w in LOCKS[1:] if w in out["handoff"]], out["handoff"]


def test_a4_adapter_e02_payable_and_paid_locked():
    """ОТРИЦАТЕЛЬНЫЙ на живом пути E02: «К оплате 7790, вы уже оплатили» — заперт: «денежное утверждение без опоры» и
    число 7790 в claims (низ карточки называет число, а не «сверено»)."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(E02_PAID))
    out = adapter(s, E02_Q).draft(NUMBER, 5)
    assert out and K.MONEY_CLAIM_WORDS in out["handoff"], out
    assert out["claims"] and any(c[1] == 7790 for c in out["claims"]), out


# ═══ 7. USEFUL1310 A5 (находки V1–V4 проверяющего X3, judge3b; решение интегратора К3) ════════════════════════════
# (а) V2: окно реквизитов, перешагнувшее время/дату, номером берёт только номер от 5 цифр. Новые ложные замки X3
# (verify3/out/cmp_a3.txt, группа c_f2, дословно) — без причин; F2 X3 (номер 7 цифр за временем/датой) — по-прежнему
# заперт (RISKY выше); граница — 4 цифры за временем не номер, 5 цифр — номер; окно без времени — прежнее.
A5_F2_FREE = ("К оплате 7790 бат. По карте с 9:00 до 21:00 7 дней в неделю.",
              "Total 7790 THB. Card payment from 9:00 to 21:00, 7 days a week.",
              "К оплате 7790 бат. Счёт пришлём 25.10, оплатить за 3 дня.",
              "К оплате 7790 бат. Счёт до 18:00 сегодня, срок 1 день.",
              "Total 7790 THB. Card at pickup at 10:00, 2 helmets included.",
              "К оплате 7790 бат. По карте при выдаче в 10:00, 2 шлема в комплекте.")
A5_F2_EDGE = (("К оплате 7790 бат. Счёт до 18:00: 1234.", False), ("К оплате 7790 бат. Счёт до 18:00: 12345.", True),
              ("К оплате 7790 бат. Карта до 15.10: 4521.", False), ("К оплате 7790 бат. Карта до 15.10: 45218.", True),
              ("К оплате 7790 бат. Карта 4521, до 15.10.", True))   # последнее — окно без времени: номер любой длины
# (б) V3: зачин «и/а/and/plus + деньги» в следующем предложении больше не эллипсис денег (c_tied, дословно); при
# «тоже/также/too/as well» — эллипсис, как в A3 (цена оставлена решением К3: остаются запертыми).
A5_TIED_FREE = ("Got it! And payment is by card at pickup. Total 7790 THB.",
                "Got your question. And the payment can be made at pickup. Total 7790 THB.",
                "Получили ваш вопрос. А оплата — при выдаче байка. К оплате 7790 бат.",
                "Получили ваш вопрос. И оплату можно внести при выдаче. К оплате 7790 бат.",
                "К оплате 7790 бат. Получили ваш вопрос. А оплата — при выдаче.",
                "Thanks, received your booking. And the transfer details will follow. Total 7790 THB.")
A5_TIED_KEPT = ("Got your question. You can pay by transfer as well. Total 7790 THB.",
                "Got your question. We accept card and transfer too. Total 7790 THB.",
                "Получили ваш вопрос. Оплату тоже можно сделать картой. К оплате 7790 бат.",
                "Вижу вашу бронь. Перевод тоже подходит. К оплате 7790 бат.")
# (в) V1: маскировки получения денег за «подтверждением» (verify3/out/cmp_a3.txt, по форме на механизм, дословно) —
# судья их по-прежнему не запирает, но строка сверки человеком называет эти предложения дословно.
# A6 (F4, решение К3): ожидание изменено ПОИМЁННО — подтверждение без денег («Получили ваше сообщение.», «Got your
# message.») больше не цитируется, ложная часть с деньгами — цитируется; «Got your message and the bank confirmation.» и
# «Got it, paid!» денежного слова классов модуля не несут — их строки нет (названная цена, A6_PRICE ниже)
# A7 (W1 проверяющего X6, решение К3): ожидание изменено ПОИМЁННО обратно, как на A5 — предложение со словом получения
# снова цитируется (не идёт только голое «Got it!» / «Понял!»), порядок — получение с деньгами и эллипсис первыми, затем
# получение, затем прочие о деньгах; показ — в порядке текста
A5_MASKS = (("Получили ваше сообщение. Деньги — тоже. К оплате 7790 бат.",                        # m_link: тире
             ["Получили ваше сообщение.", "Деньги — тоже."]),
            ("Получили ваше сообщение. Спасибо! Деньги тоже. К оплате 7790 бат.",                  # m_skip1
             ["Получили ваше сообщение.", "Деньги тоже."]),
            ("Получили вашу бронь и депозит. К оплате 7790 бат.", ["Получили вашу бронь и депозит."]),   # m_noun
            ("Received your booking and deposit. Total 7790 THB.", ["Received your booking and deposit."]),
            ("Деньги тоже. Получили ваше сообщение. К оплате 7790 бат.",                            # m_reverse
             ["Деньги тоже.", "Получили ваше сообщение."]),
            ("Got your message. And your payment. Total 7790 THB.",                                 # держал зачин (V3)
             ["Got your message.", "And your payment."]))
# полезные без денег — строки сверки нет (cost_probe проверяющего, дословно; итог судит штамп, не строка сверки)
A5_NO_SAID = ("К оплате 7790 бат. Байк будет готов в 10:00.", "К оплате 7790 бат. Наш офис: Раваи, Viset Rd 52/7.",
              "Total 7790 THB. Pickup at 10:00 tomorrow.", "К оплате 7790 бат. Номер брони K3-BK-001.",
              "Total 7790 THB. Call us at 081-234-5678 if needed.", "Здравствуйте! Байк свободен.",
              "Получили ваш вопрос. Байк свободен.")      # подтверждение без денег в тексте — не сверка


def test_a5_v2_short_number_after_clock_not_requisites():
    """(а) Новые ложные замки X3 (c_f2) — без причин и с опорой итога; F2 X3 (номер 7 цифр за временем/датой) — заперт;
    граница: за временем/датой 4 цифры — не номер, 5 — номер; окно без времени — номер любой длины, как было."""
    for res in ([rental(), cash([])], [rental()]):
        for text in A5_F2_FREE:
            assert _judge(text, res) == [] and T.due_supported(text, 7790), (text, _judge(text, res))
        for text in ("К оплате 7790 бат. Переведите на карту до 15.10 по номеру 1234567.",
                     "К оплате 7790 бат. Счёт до 18:00 по номеру 1234567.",
                     "К оплате 7790 бат. Счёт до 18:00: 1234567."):
            assert K.MONEY_CLAIM_WORDS in _judge(text, res), text
    for text, locked in A5_F2_EDGE:
        assert T.due_supported(text, 7790) is not locked, (text, locked)


def test_a5_v3_opening_conjunction_not_money_ellipsis():
    """(б) Зачин «и/а/and/plus + деньги» снят: полезные инструкции после подтверждения — без причин; «тоже/too/as well»
    по-прежнему эллипсис денег — запирает (названная цена); прочие формы A3 (RISKY) — заперты, как были."""
    for res in ([rental(), cash([])], [rental()]):
        for text in A5_TIED_FREE:
            assert _judge(text, res) == [], (text, _judge(text, res))
        for text in A5_TIED_KEPT:
            assert K.MONEY_CLAIM_WORDS in _judge(text, res), text
    assert not T._DUE_ALSO.search("And the payment can be made at pickup") and T._DUE_ALSO.search("Деньги тоже")


def test_a5_v1_money_said_masks_and_no_money():
    """(в) Предложения о деньгах, их получении или платёжном документе — дословно, до двух (A7: предложение со словом
    получения — снова, как на A5; показ — в порядке текста); предложение итога и текст без денег — не идут."""
    for text, want in A5_MASKS:
        assert T.money_said(text, 7790) == (want, len(want)), (text, T.money_said(text, 7790))
    for text in A5_NO_SAID:
        assert T.money_said(text, 7790) == ([], 0), (text, T.money_said(text, 7790))
    said, n = T.money_said("Получили ваш вопрос. Деньги тоже. Перевод тоже. Чек тоже. К оплате 7790 бат.", 7790)
    assert said == ["Деньги тоже.", "Перевод тоже."] and n == 4, (said, n)      # A7: «вопрос» — в счёте, за эллипсисом
    long = "Получили ваш перевод " + "и ещё раз спасибо " * 20 + "."
    assert len(T.money_said(long)[0][0]) == T.SAID_CUT and T.money_said(long)[0][0].endswith("…")


def test_a5_g_backing_names_numbers_and_source():
    """(г) Числа ответа с опорой и ИМЯ опоры: итог аренды кода (только в предложении итога), блок «ЦЕНА», факты сверки
    кода; число без опоры — не здесь (его называет `money_claims`); чисел нет — пусто. A6 (ожидание изменено
    ПОИМЁННО): опоры «залог аренды кода» нет — залог 3000 в штамп не идёт (он в claims)."""
    facts = T.accepted([rental(), cash([])])
    known = T.known_amounts(None, facts, figures(facts))
    assert T.money_backing(E02_OK, None, known) == [[7790, [T.SRC_DUE]]]
    assert T.money_claims(E02_OK, None, known) == [("сумма", 3000)]
    assert T.money_backing("Здравствуйте! Байк свободен.", None, known) == []
    assert T.money_backing("Итого за аренду 7990 бат.", None, known) == []          # без опоры — в claims
    assert T.money_backing("К оплате 7790 бат, счёт Kasikorn 1234567890.", None, known) == []
    price = {"line": "ЦЕНА: PCX 160: 7 суток, итого 2 800 ฿"}
    assert T.money_backing("PCX на неделю — 2 800 бат.", price, None, bare=False) == [[2800, [T.SRC_PRICE]]]
    cash_row = [{"kind": "cash", "role": T.R_RENT, "currency": "THB", "amount": 4900}]
    assert T.money_backing("Вы внесли 4900 бат.", None, T.known_amounts(None, cash_row, figures(cash_row))) == [
        [4900, [T.SRC_FACTS]]]


def test_a5_adapter_unpaid_said_and_stamp_on_card():
    """Живой путь (E02-вопрос, касса пуста): маскировка V1 — причин судьи нет (как на X3), но запись карточки несёт
    итог с опорой «итог аренды кода», «оплата не подтверждена» и предложения дословно; карточка рисует строку сверки
    и штамп без слова об оплате (`wa_agent.draft_checked` → `wa_agent_tg.card_check`)."""
    import wa_agent as A
    import wa_agent_tg as G
    text = A5_MASKS[0][0]
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
    out = adapter(s, E02_Q).draft(NUMBER, 5)
    assert out["claims"] == [] and out["checked"] == {"nums": [[7790, [T.SRC_DUE]]], "pay": False,
                                                       "said": A5_MASKS[0][1], "more": 0}, out
    lines = G.card_check(out["claims"], A.draft_checked(out)).split("\n")
    assert lines == [G.W_PAY_SAID + " «Получили ваше сообщение.» · «Деньги — тоже.»",   # A7: снова, как на A5
                     "🔎 сверено кодом: 7 790 — итог аренды кода"], lines
    # полезный ответ E02 (итог в предложении итога, залог в нём же) — строки сверки нет; A6 (ожидание изменено
    # ПОИМЁННО): штамп называет только итог, залог 3000 — строкой «без опоры» той же формулировки опоры
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(E02_OK))
    out = adapter(s, E02_Q).draft(NUMBER, 5)
    assert out["checked"] == {"nums": [[7790, [T.SRC_DUE]]], "pay": False, "said": [], "more": 0}, out["checked"]
    assert G.card_check(out["claims"], A.draft_checked(out)) == (
        "🔎 сверено кодом: 7 790 — итог аренды кода\n🔎 проверка кодом — без опоры: сумма 3 000")


def test_a5_adapter_paid_by_code_no_said():
    """Оплата подтверждена кодом (строка кассы аренды + та же сумма в переписке) — строки сверки нет, хотя текст о
    получении денег; штамп — только числа."""
    q = "Я перевёл 7790 бат за аренду, дошло?"
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
               {"tool": "history", "args": {}}, final("Получили ваш перевод, спасибо! Итого за аренду 7790 бат."))
    a = adapter(s, q, cash_items=[tx_item()])
    out = a.draft(NUMBER, 5)
    facts = T.accepted(a.last["tools"]["results"])
    assert T.pay_verdict(facts) == (True, ""), T.pay_verdict(facts)
    assert out["checked"]["pay"] is True and out["checked"]["said"] == [], out["checked"]


def test_a5_no_tools_path_price_only_and_unpaid():
    """Черновик без сверки (WA_AGENT_TOOLS выкл): опора — только блок «ЦЕНА»; кассы нет — оплата кодом не подтверждена,
    предложение о получении денег идёт в строку сверки."""
    a = M.ModelAdapter(":memory:-не-открывается", Script(final("Деньги получили. PCX на неделю — 2 800 бат.")),
                       clock=Clock(), log=lambda *_: None)
    info = {"price": {"line": "ЦЕНА: PCX 160: 7 суток, итого 2 800 ฿"}, "code_reasons": [], "price_words": "цена",
            "history_items": 1, "history_chars": 10, "masked": 0}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", info)
    out = a.draft(NUMBER, 5)
    assert a.tools is None and out["claims"] == [], out
    assert out["checked"] == {"nums": [[2800, [T.SRC_PRICE]]], "pay": False, "said": ["Деньги получили."], "more": 0}


# ═══ 8. USEFUL1310 A6 (находки F1–F5 проверяющего X5; решение интегратора К3) ══════════════════════════════════════
# F1 (verify5, дословно): ложная часть «Аванс тоже» / «Наличные тоже» / «Cash too» строкой сверки не цитировалась — слов
# не было в классе денежных существительных. A6 кладёт их туда (не новый список): строка их цитирует, эллипсис
# `_DUE_ALSO` их видит — судья запирает их, как «Деньги тоже».
# A7 (W2 проверяющего X6, решение К3): ожидание изменено ПОИМЁННО — слова F1 только строке сверки (`_SAID_MONEY_N`),
# эллипсис судьи `_DUE_ALSO` — как на A5 (не видит их: судья эти формы не запирает, как на A5); строка цитирует ложную
# часть и (A7, W1) подтверждение перед ней
A6_F1 = (("Получили вашу бронь. Аванс тоже. К оплате 7790 бат.", ["Получили вашу бронь.", "Аванс тоже."]),
         ("Получили вашу бронь. Наличные тоже. К оплате 7790 бат.", ["Получили вашу бронь.", "Наличные тоже."]),
         ("Got your booking. Cash too, thanks! Total 7790 THB.", ["Got your booking.", "Cash too, thanks!"]))
# F2 (verify5, дословно): ложный эллипсис за двумя законными строками об оплате
A6_F2 = ("Payment by transfer or cash. You can pay by transfer at pickup too. Got your message. The money — too. "
         "Total 7790 THB.")
# F4 (c_k3 проверяющего X3, дословно): полезные консультации — подтверждение без денег не цитируется
# A7 (W1, решение К3): ожидание изменено ПОИМЁННО — не цитируется ТОЛЬКО голое междометие-подтверждение без объекта
# («Got it!», «Okay, got it.»; «Понял!», «Принято!», «Ок, понял.» — формы решения К3); подтверждение с объектом
# («Получили ваш вопрос.», «Thanks, received your booking.») — снова, как на A5 (названная цена решения К3)
A6_F4_NONE = ("Got it! The total is 7790 THB.", "Okay, got it. Total 7790 THB.", "Понял! К оплате 7790 бат.",
              "Принято! К оплате 7790 бат.", "Ок, понял. К оплате 7790 бат.")
A6_F4_MONEY = (("Got it! Total 7790 THB. You can pay by transfer.", ["You can pay by transfer."]),
               ("Thanks, received your booking. Total 7790 THB. Payment by transfer.",
                ["Thanks, received your booking.", "Payment by transfer."]),
               ("Получили ваш вопрос. К оплате 7790 бат. Оплатить можно переводом.", ["Получили ваш вопрос."]))
# ЦЕНА решения К3 (5) на A6: маскировка, где деньги или платёжный документ названы словом ВНЕ классов модуля, судьёй не
# запирается и строки сверки не получала. A7 (W1): строку снова ставит подтверждение — ожидание изменено ПОИМЁННО
A6_PRICE = ("Got your message and the bank confirmation. Total 7790 THB.", "Got it, paid! Total 7790 THB.")


def test_a7_f1_money_nouns_quoted_judge_as_a5():
    """F1 → A7 (W2): аванс, наличные, cash — строке сверки: она цитирует ложную часть дословно (и подтверждение перед
    ней); эллипсис судьи `_DUE_ALSO` — как на A5: этих слов не видит, судья формы F1 не запирает (касса пуста и касса не
    читана); `_SAID_ALSO` строки сверки видит и deposit/prepayment/advance."""
    for text, want in A6_F1:
        assert T.money_said(text, 7790) == (want, 2), (text, T.money_said(text, 7790))
        for res in ([rental(), cash([])], [rental()]):
            assert _judge(text, res) == [], (text, _judge(text, res))
    for piece in ("Аванс тоже", "Наличные тоже", "Cash too", "The deposit too", "The prepayment too",
                  "Advance as well"):
        assert re.search(T._SAID_ALSO, piece, re.I) and not T._DUE_ALSO.search(piece), piece
    for piece in ("Деньги тоже", "The money too", "Перевод тоже", "The transfer as well",
                  "Предоплата тоже"):                               # «(пред)оплата» — в классе судьи и на A5
        assert T._DUE_ALSO.search(piece) and re.search(T._SAID_ALSO, piece, re.I), piece
    assert not T._DUE_ALSO.search("Got your booking") and not T._DUE_ALSO.search("Байк тоже свободен")


def test_a6_f2_money_ellipsis_shown_first():
    """F2: первыми — получение с деньгами и эллипсис денег (в т.ч. через тире); A7 (W1): затем получение, затем прочие о
    деньгах — пара ложного эллипсиса («Got your message.» · «The money — too.») видна целиком; число скрытых названо
    (ожидание изменено ПОИМЁННО: на A6 — «Payment by transfer or cash.» · «The money — too.», скрыто 1)."""
    said, n = T.money_said(A6_F2, 7790)
    assert said == ["Got your message.", "The money — too."] and n == 4, (said, n)
    chk = T.money_check(A6_F2, None, None, pay=False)
    assert chk["said"] == said and chk["more"] == 2, chk


def test_a7_f4_bare_ack_not_quoted():
    """F4 → A7 (W1): голое междометие-подтверждение без объекта строку сверки не ставит; подтверждение с объектом и
    инструкция об оплате — цитируются; «Got it!»-консультация живым путём — без строки сверки, только штамп."""
    for text in A6_F4_NONE:
        assert T.money_said(text, 7790) == ([], 0), (text, T.money_said(text, 7790))
    for text, want in A6_F4_MONEY:
        assert T.money_said(text, 7790) == (want, len(want)), (text, T.money_said(text, 7790))
    import wa_agent as A
    import wa_agent_tg as G
    for text in A6_F4_NONE[:2]:
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
        out = adapter(s, E02_Q).draft(NUMBER, 5)
        assert G.card_check(out["claims"], A.draft_checked(out)) == "🔎 сверено кодом: 7 790 — итог аренды кода", out


def test_a7_w1_price_masks_quoted_again():
    """A7 (W1): маскировка словом вне классов модуля («bank confirmation», «paid» после запятой) — судья по-прежнему не
    запирает (asked нет), но строка сверки снова цитирует подтверждение дословно (на A6 — ни замка, ни строки)."""
    for text in A6_PRICE:
        assert T.money_said(text, 7790) == ([text.split(" Total")[0]], 1), (text, T.money_said(text, 7790))
        assert _judge(text, [rental(), cash([])]) == [], text


# ═══ 9. USEFUL1310 A7 (находки W1, W2, W4 проверяющего X6; решение интегратора К3) ══════════════════════════════════
# W1 (verify6/out/alt_said6.txt, группы m_doc и m_thanks формы проверяющего X3, дословно): 11 масок, у которых на A6
# не было ни замка судьи, ни строки сверки — деньги или платёжный документ названы словом вне классов модуля
A7_W1 = ("Получили ваше сообщение и подтверждение из банка. К оплате 7790 бат.",
         "Получили ваше сообщение с квитком. К оплате 7790 бат.",
         "Получили ваше сообщение и выписку. К оплате 7790 бат.",
         "Получили ваше сообщение и чек-подтверждение. К оплате 7790 бат.",
         "Got your message with the proof. Total 7790 THB.",
         "Got your message and the bank confirmation. Total 7790 THB.",
         "Got it, thanks for the proof! Total 7790 THB.",
         "Received your booking and the bank statement. Total 7790 THB.",
         "Got your message and the payslip. Total 7790 THB.",
         "Got it, thanks for paying! Total 7790 THB.",
         "Got it, paid! Total 7790 THB.")
# W2 (verify6/hint_mig6.py, свидетели «… cash too / наличными тоже», дословно): консультация о способах оплаты
A7_W2 = (("Got it! You can pay by card or cash too. Total 7790 THB.", ["You can pay by card or cash too."]),
         ("Получили ваш вопрос. Оплатить можно переводом или наличными тоже. К оплате 7790 бат.",
          ["Получили ваш вопрос."]))
# W4 (verify6/edge6.py, дословно): сырьё с точкой и ровно тремя цифрами перед запятой — мост читает 3 и 1.5005
A7_W4 = ({"deposit": 3, "deposit_raw": "3.000,00"}, {"deposit": 1.5005, "deposit_raw": "1.500,50"})


def test_a7_w1_receipt_masks_quoted():
    """W1: все 11 масок — строка сверки цитирует предложение с подтверждением дословно (на A6 — 0 из 11); судья их, как
    и прежде, не запирает при asked нет (замок «оплата не подтверждена сверкой» при вопросе об оплате — прежний)."""
    for text in A7_W1:
        said, n = T.money_said(text, 7790)
        assert n == 1 and said == [text.split(" К оплате")[0].split(" Total")[0]], (text, said, n)
        assert _judge(text, [rental(), cash([])]) == [], (text, _judge(text, [rental(), cash([])]))


def test_a7_w1_live_path_card_line():
    """W1 живым путём (E02-вопрос, касса пуста): маскировка без замка судьи — на карточке строка сверки с подтверждением
    дословно и штамп итога; кнопка «Отправить» не снята (строка — сверка человеком)."""
    import wa_agent as A
    import wa_agent_tg as G
    for text in (A7_W1[0], A7_W1[-1]):
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
        out = adapter(s, E02_Q).draft(NUMBER, 5)
        first = text.split(" К оплате")[0].split(" Total")[0]
        assert out["checked"]["said"] == [first] and out["checked"]["pay"] is False, out
        assert G.card_check(out["claims"], A.draft_checked(out)).split("\n")[0] == G.W_PAY_SAID + " «%s»" % first


def test_a7_w2_payment_ways_too_no_lock():
    """W2: «… cash too / наличными тоже» в консультации — не эллипсис судьи (как на A5): причин нет в обоих
    контекстах, итог с опорой; строка сверки цитирует предложение о способах оплаты либо подтверждение с объектом."""
    for text, want in A7_W2:
        assert T.due_supported(text, 7790), text
        for res in ([rental(), cash([])], [rental()]):
            assert _judge(text, res) == [], (text, _judge(text, res))
        assert T.money_said(text, 7790) == (want, len(want)), (text, T.money_said(text, 7790))


def test_a7_w4_eu_decimal_raw_no_deposit_line():
    """W4: «3.000,00» и «1.500,50» (точка и ровно три цифры перед запятой; мост читает их как 3 и 1.5005) — строки
    залога нет, блок как без залога; «3,000.00» и «3000.00» — по-прежнему 3000."""
    plain = T.due_block([rental(NO_DEP)])
    for row in A7_W4:
        assert T.deposit_of(T.accepted([rental(row)])) is None, row
        assert T.due_block([rental(row)]) == plain, row
    for raw in ("3,000.00", "3000.00"):
        assert T.deposit_of(T.accepted([rental({"deposit": 3000, "deposit_raw": raw})]))["amount"] == 3000, raw


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
