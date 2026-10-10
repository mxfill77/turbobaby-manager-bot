#!/usr/bin/env python3
"""K3-FIX шаг 3 (09–10.10.2026, TB-K3-REAL-GAPS-0910) — регрессия находок реального прогона К3 (real/judge_cases
VERDICT §4.1, §4.2, §4.5, §7 N4; F2_CONTRACT §§0, 1, 3.4):
п.1 ДОГОВОР — дверь договоров звалась ТОЛЬКО аргументами модели, а нужного фильтра модель не знает → 8 из 9 запросов
     contract отказаны `no_filter`, путь PDF недостижим. Ремонт: поиск ставит КОД в доверенном контексте обращения
     (номер обращения + срок аренды, прочитанной кодом); чужой/противоречивый фильтр модели — CONFLICT без чтения
     реестра; договор другого периода — назван (CONFLICT), а не принят и не «нет договора».
п.2 СДАЧА — С3 (итог 7790, внесено 8000 → сдача 210 в конце аренды) был недостижим: модели запрещено считать, а код
     разность «наличные − итог» не считал. Ремонт: «РАСЧЁТ КОДА» по проверенной кассе той же аренды; слова клиента
     оплатой не становятся; залог, чужие деньги, иная валюта не складываются; нет основания — отказ словами.
п.3 N4 — утвердительные «в кассе вижу оплату…», «оплата отражена, всё в порядке» обходили детектор подтверждения
     оплаты; отрицание и обещание будущей проверки не дают ни ложного подтверждения, ни ложной блокировки.
п.4 F2 — версия источника только от источника (сегодня null + причина), `version` не выводится из signed_at, длины,
     msg_id, номера строки; у rental/rules время данных — время СНИМКА, свежий вызов старый снимок свежим не делает.
Шаг 3b (10.10.2026, приёмка шага 3 fix_review VERDICT, PASS_WITH_REMARKS на cbe186f):
п.3b D1 — 8 близких утвердительных форм приёмки («Аренда оплачена.», «Платёж получен.», «Оплата есть в кассе.», «Your
     payment went through.» …) определение не ловило: ремонт — ФОРМЫ (`_PAY_FORMS`), а не список; отрицание, будущее,
     долженствование, проверка, условие, вопрос, предмет после предлога, роль залога — не утверждение.
D3   — проверки, которые падают под мутантами приёмки m3r (FACT второго поиска договора не снят в НЕИЗВЕСТНО) и m3v
     (недоплата по кассе не отказ); на cbe186f они ПРОХОДЯТ — ловят мутанты, а не дефект кода.
Шаг 3c (10.10.2026, решение координатора после круга 3b; регрессия REG3B на 6f6e754):
п.3c — ПРЕЖНИЕ формы `_PAY_AFFIRM` давали лишнюю причину «оплата не подтверждена сверкой» на НЕ-утверждениях («После
     оплаты договор пришлём», «Оплата должна быть получена до выдачи…», «Ссылку на оплату получили» и др.): те же
     исключения — одним определением на оба прохода; исход каждого совпадения НАЗВАН (`_PayClaim.verdict`/`explain`,
     храповик слепых читателей 74 → 72); ни одно прежде пойманное утверждение не теряется (КОНТРОЛЬ).
Шаг 3d (10.10.2026, независимая проверка 3b+3c — fix_review3c/VERDICT.md, FAIL на f6ed7bd; решение координатора):
п.3d R1 — исключения шага 3c теряли утверждения, которые ловили cbe186f и 6f6e754 (25 из 38 состязательных фраз
     проверяющего): долженствование судится при СВОЁМ сказуемом, предлог цели — только при слове документа перед ним;
R2   — контроль «ничего не потеряно» собран из ОБЪЕДИНЕНИЯ всех известных списков, включая корпуса проверяющего
     (вшиты данными: списки `RV_*` — дословно fix_review3c/rv3c_corpus.py и rv3c_corpus2.py);
R3   — два семейства, которых не ловил ни один коммит: подтверждение получения отглагольным существительным и
     сказуемое получения с денежной суммой или словом суммы; плюс находки своего состязательного поиска (`ADV_*`).
Шаг 3e (10.10.2026, решение координатора после круга 3d; остатки (а)–(в) строителя 3d):
п.3e 1 — краткое утвердительное получение или подтверждение БЕЗ предмета («Да, всё пришло.», «We got it, thanks!») —
     утверждение оплаты, когда входящее клиента об оплате: признак — одно чистое определение `pay_asked`, адаптер
     передаёт его в `T.run` и `T.judge` рядом с `cash_said`; без признака (вопрос о документе, вопроса нет) — нет;
2    — «долга нет» («задолженности по аренде нет», «ничего не должны», «счёт закрыт», «no balance due», «all settled»);
3    — число без валюты при сказуемом получения, в том числе не вплотную («Да, 7790 получили.»), — утверждение, когда
     оно равно известной денежной сумме сверки (`pay_sums`) либо входящее об оплате; номер байка — нет.

Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на f2f7295 и на коммите шага 2 (996ee09) он падает по существу, на
ремонте проходит. Тест с пометкой КОНТРОЛЬ — зелёный на всех трёх (прежнее поведение, которое ремонт не задел).
Тесты п.3b (кроме КОНТРОЛЯ и отрицательных) падают и на cbe186f (шаг 3); тесты D3 на cbe186f проходят.
Тесты п.3c (кроме КОНТРОЛЯ) падают и на 6f6e754 (шаг 3b).
Тесты п.3d (кроме КОНТРОЛЯ `…backed…` и отрицательного `…reviewer_not_claims…`) падают и на f6ed7bd (шаг 3c).
Тесты п.3e (кроме КОНТРОЛЯ `…backed…`) падают и на 44ba8ee (шаг 3d): утвердительные — по существу (причины нет),
отрицательные — оттого, что на 44ba8ee нет самого контекста сверки (признака входящего и сумм фактов у определения).

Всё на подменах: двери — функции ответа живого формата (`bridge_client.contract_find`/`contract_pdf`/`tx_find`,
строка листа «клиенты» — ключи ReadClients.js), модель — сценарий. Сети, моста, Telegram, WhatsApp, SQLite и
подпроцессов здесь нет; файлов набор не пишет."""
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

import wa_agent as A                # noqa: E402
import wa_agent_attach as X         # noqa: E402
import wa_agent_knowledge as K      # noqa: E402
import wa_agent_model as M          # noqa: E402
import wa_agent_tools as T          # noqa: E402

NUMBER = "66812345678"                                  # номер обращения (WhatsApp)
BK = "K3-BK-001"
T0 = 1791500000.0
TERM = ("2026-10-05", "2026-10-15")
SV_WORDS = "источник версии не отдаёт"                  # литералом: на старых деревьях константы нет
CHANGE_WORDS = "сдача посчитана со слов клиента о переданных наличных — сумму подтверждает человек"
CONTRACT_WORDS = "договор не этого клиента или не этой аренды"

# строка листа «клиенты» — ключи двери clients (ReadClients.js:95-115): итог «к оплате» J = to_pay, K = paid
ROW = {"row": 12, "status": "В аренде", "auto_cancel": "", "bike": "NMAX 155 90101", "name": "Тест Клиент",
       "date_start": "2026-10-05 10:00", "date_end": "2026-10-15 10:00", "duration": "10", "pay_per_day": 779,
       "debt": 0, "to_pay": 7790, "paid": 7790, "deposit": 3000, "deposit_raw": "3000", "helmets": "1",
       "contacts": "+66 81 234 5678", "note": "", "type": "мото", "booking_id": BK}

# записи реестра e-Sign в форме `contract_find` (bridge_client.contract_find, ContractDoor.js contractFind)
DOC1 = {"row": 5, "doc_id": "K3-DOC-001", "client": "Тест Клиент", "contract_date": "2026-10-05",
        "contract_date_raw": "05.10.2026", "created_raw": "", "date_src": "contract_date", "status": "ПОДПИСАН",
        "signed": True, "signed_at": "2026-10-05 10:12", "bike": "NMAX 155 90101", "phone": "+66 81 234 5678",
        "pdf_id": "PDF-0001"}
DOC2 = dict(DOC1, row=6, doc_id="K3-DOC-002", contract_date="2026-10-20", contract_date_raw="20.10.2026",
            signed_at="2026-10-20 09:00", pdf_id="PDF-0002")              # будущая аренда того же байка
DOC3 = dict(DOC1, row=7, doc_id="K3-DOC-003", contract_date=None, contract_date_raw="", date_src="none",
            signed_at="2026-10-06 11:00", pdf_id="PDF-0003")              # подписан, день неизвестен


# ------------------------------- подмены -------------------------------

class Clock:
    def __init__(self, t=T0, step=0.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — запросы, которые она получила."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


def _l9(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d[-9:] if len(d) >= 9 else ""


def _plate(v):
    nums = [n for n in re.findall(r"\d{3,}", str(v or "")) if n not in ("125", "150", "155", "160")]
    return nums[-1] if nums else ""


class Registry:
    """Дверь `contract_find` живого формата (логика contractFind — та же, что у подделки стенда
    stand/fakes/bridge.py:344-447): без телефона/имени/байка — `no_filter`; телефон — последние 9 цифр; байк — по
    номеру; срок — по дню договора включительно, подписанный без дня при сроке — в сторону (`incomplete`)."""

    def __init__(self, rows, fail_after=None):
        self.rows, self.calls, self.fail_after = [dict(r) for r in rows], [], fail_after

    def __call__(self, phone="", name="", bike="", date_from="", date_to="", limit=None):
        self.calls.append({k: v for k, v in (("phone", phone), ("name", name), ("bike", bike),
                                             ("date_from", date_from), ("date_to", date_to)) if v})
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise TimeoutError("дверь молчит")
        p9, plate = _l9(phone), _plate(bike) if bike else ""
        words = [w for w in re.split(r"\s+", str(name or "").lower()) if len(w) >= 2]
        if not p9 and not plate and not words:
            return {"ok": False, "error": "no_filter", "message": "нужен телефон, имя или байк — реестр целиком не выгружается"}
        matched, aside = [], []
        for r in self.rows:
            on = []
            if p9:
                if p9 not in [_l9(x) for x in re.split(r"[,;/|\n]+", r["phone"])]:
                    continue
                on.append("phone")
            if words:
                if not all(w in r["client"].lower() for w in words):
                    continue
                on.append("name")
            if plate:
                if _plate(r["bike"]) != plate:
                    continue
                on.append("bike")
            rec = dict(r, matched_on=on)
            if date_from or date_to:
                if not r["contract_date"]:
                    aside.append(rec)
                    continue
                if (date_from and r["contract_date"] < date_from) or (date_to and r["contract_date"] > date_to):
                    continue
            matched.append(rec)
        signed, aside_signed = [x for x in matched if x["signed"]], [x for x in aside if x["signed"]]
        pick, reason = None, None
        if aside_signed and len(signed) <= 1:
            outcome = "incomplete"
            reason = {"code": "undated_signed", "rows": [x["row"] for x in aside_signed],
                      "message": "подписанный договор под фильтр без известного дня — в сроке ли он, неизвестно"}
        elif not matched:
            outcome = "none"
        elif not signed:
            outcome = "none_signed"
        elif len(signed) > 1:
            outcome = "ambiguous"
        else:
            outcome = "one"
            pick = dict(signed[0], pdf_ready=bool(signed[0]["pdf_id"]))
        return {"ok": True, "outcome": outcome, "pick": pick, "reason": reason, "items": matched,
                "undated_items": aside,
                "checked": {"rows_scanned": len(self.rows), "span_from": date_from, "span_to": date_to,
                            "undated": len(aside), "undated_signed": len(aside_signed), "date_unparsed": 0,
                            "unread": [], "complete": not aside, "matched": len(matched), "signed": len(signed),
                            "returned": len(matched), "truncated": False},
                "filter": {"phone_last9": p9, "name": name, "bike": bike, "plate": plate, "date_from": date_from,
                           "date_to": date_to},
                "stand_meta": {"version": "K3-registry-v1"}}


def pdf_door(file_id=""):
    """`contract_pdf` после клиентской сверки длины и sha256 (bridge_client.contract_pdf → verified)."""
    if file_id not in ("PDF-0001", "PDF-0002", "PDF-0003"):
        return {"ok": False, "error": "not_in_registry"}
    return {"ok": True, "id": file_id, "name": "%s_signed.pdf" % file_id, "mime": "application/pdf", "size": 1234,
            "sha256": "ab" * 32, "row": 5, "verified": True}


def tx_item(row=11, amount=7790, currency="THB", category="rental", booking=BK,
            description="Nmax 90101 +7790 аренда 10 дней K3-BK-001"):
    return {"row": row, "date": "2026-10-05", "date_src": "msg_date", "recorded_at": "2026-10-05T03:10:00.000Z",
            "amount": amount, "amount_raw": str(amount), "amount_unparsed": False, "currency": currency,
            "category": category, "bike": "Nmax 90101", "deposit": "", "description": description,
            "raw": description, "msg_id": "-100311:501:m%d" % row, "link": "https://t.me/c/311/501/%d" % row,
            "status": "recorded", "booking_id": booking}


def tx(items):
    return {"ok": True, "checked": {"span_from": "2026-10-01", "span_to": "2026-10-09", "rows_scanned": 40,
                                    "truncated": False, "complete": True}, "total": {"THB": 999999},
            "items": list(items), "stand_meta": {"version": "K3-cash-v1"}}


def rental_door(age=None):
    def rental():
        out = {"ok": True, "rows": [dict(ROW)]}
        if age is not None:
            out["_taken_at"] = T0 - age
        return out
    return rental


def run(script, reg, number=NUMBER, extra=None):
    doors = {"rental": rental_door(), "contract": reg, "contract_pdf": pdf_door}
    doors.update(extra or {})
    return T.run(script, "S", "U", doors, number=number, clock=Clock())


def outcomes(out, tool=None):
    return [(r["tool"], r["outcome"]) for r in out["results"] if tool is None or r["tool"] == tool]


class Book:
    def __init__(self, rows, age=60.0):
        self.rows, self.age = rows, age

    def get(self, now):
        return self.rows, [], self.age, ""


def adapter(script, cash_items=None, question="Добрый день!", book_age=60.0, reg=None):
    """Адаптер модели с путём сверки Т4а (как `tests/test_wa_agent_tools.adapter`): `build` подменён — запрос модели
    прежний, сведения несут вопрос клиента (последний блок запроса — `info["question"]`, WACARDQ0410)."""
    tools = {"cash": (lambda **kw: tx(cash_items or [])), "contract": reg or Registry([DOC1]),
             "contract_pdf": pdf_door}
    a = M.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=Clock(), log=lambda *_: None,
                       book=Book([dict(ROW)], book_age), tools=tools, fresh=None)
    info = {"price": None, "code_reasons": [], "price_words": "о цене не спрашивают", "history_items": 1,
            "history_chars": 10, "masked": 0, "question": question}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": question}], [])
    return a


C3_QUESTION = ("Я отдал вашему водителю 8000 бат наличными за аренду. Сдачу верните, пожалуйста, на мои новые "
               "реквизиты для возврата: Тест Банк, счёт TEST-ACC-0001.")
C3_TEXT = ("Здравствуйте! Итог аренды по договору — 7790 бат. С 8000 сдача 210 бат — её отдаём в конце аренды, вместе "
           "с возвратом залога. Реквизиты для возврата я не меняю — передаю менеджеру.")


def c3_script(text=C3_TEXT):
    return Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))


# ═══ п.1 ДОГОВОР: поиск в доверенном контексте обращения ═════════════════════════════════════════════════════

def test_p1_contract_no_args_bound_by_code_pdf_reached():
    """K09/K17–K20 real: модель зовёт contract БЕЗ аргументов (номера байка и телефона она не знает) — код ищет по
    номеру обращения и сроку аренды; договор принят и привязан, PDF принят, вложение решено."""
    reg = Registry([DOC1])
    out = run(Script({"tool": "rental", "args": {}}, {"tool": "contract", "args": {}},
                     {"tool": "contract_pdf", "args": {"file_id": "PDF-0001"}},
                     final("Отправляю договор следующим сообщением.")), reg)
    assert reg.calls and reg.calls[0] == {"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}, reg.calls
    assert outcomes(out) == [("rental", T.FACT), ("contract", T.FACT), ("contract_pdf", T.FACT)], \
        [(r["outcome"], r["reason"]) for r in out["results"]]
    c = [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert c and c[0]["doc_id"] == "K3-DOC-001" and c[0]["booking_id"] == BK, c
    meta, why = X.attach_of({"state": T.DONE, "results": out["results"]})
    assert meta and meta["file_id"] == "PDF-0001", why


def test_p1_period_choice_two_contracts():
    """K06: два подписанных договора того же номера и байка (текущий и будущий) — выбран договор СРОКА аренды
    обращения; без срока дверь сказала бы «несколько, выбрать нельзя»."""
    reg = Registry([DOC1, DOC2])
    out = run(Script({"tool": "contract", "args": {}}, final("Договор следующим сообщением.")), reg)
    assert outcomes(out, "contract") == [("contract", T.FACT)], [(r["outcome"], r["reason"]) for r in out["results"]]
    docs = [f["doc_id"] for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert docs == ["K3-DOC-001"], docs


def test_p1_other_period_named_conflict_not_fact():
    """K07: у номера есть только договор ДРУГОГО периода — не принят, не «договора нет», а назван конфликтом
    (причина «нужен человек»), PDF не прикладывается."""
    reg = Registry([DOC2])
    out = run(Script({"tool": "contract", "args": {}}, {"tool": "contract_pdf", "args": {"file_id": "PDF-0002"}},
                     final("Уточню у коллег.")), reg)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.CONFLICT and "вне срока аренды" in res["reason"] and "2026-10-20" in res["reason"], res
    assert not [f for f in T.accepted(out["results"]) if f["kind"] in ("contract", "pdf")]
    words, _ = T.judge("Уточню у коллег.", None, out["results"], out["journal"])
    assert CONTRACT_WORDS in words, words
    meta, why = X.attach_of({"state": T.DONE, "results": out["results"]})
    assert meta is None, meta


def test_p1_incomplete_registry_stays_incomplete():
    """K08: в сроке аренды есть подписанный БЕЗ известного дня — «неполно», не факт, вложения нет."""
    reg = Registry([DOC1, DOC3])
    out = run(Script({"tool": "contract", "args": {}}, final("Договор пришлёт коллега.")), reg)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.INCOMPLETE and "без известного дня" in res["reason"], res
    assert reg.calls[0].get("date_from") == TERM[0], reg.calls
    assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]
    assert X.attach_of({"state": T.DONE, "results": out["results"]})[0] is None


def test_p1_foreign_or_conflicting_filter_conflict_no_read():
    """Отрицательный: явный чужой номер (в т.ч. тот же хвост 9 цифр с другим кодом страны), чужой байк, другой срок —
    CONFLICT с причиной; реестр НЕ читается, привязка к обращению не подменяется, чужого документа нет."""
    for args, word in (({"phone": "+66 89 765 4321"}, "договор другого номера"),
                       ({"phone": "+7 981 234 5678"}, "договор другого номера"),
                       ({"bike": "NMAX 155 90202"}, "договор другой аренды"),
                       ({"date_from": "2026-10-20", "date_to": "2026-10-25"}, "договор другой аренды")):
        reg = Registry([DOC1, DOC2])
        out = run(Script({"tool": "contract", "args": args}, final("Ок")), reg)
        res = out["results"][0]
        assert reg.calls == [], (args, reg.calls)
        assert res["outcome"] == T.CONFLICT and res["reason"].startswith(word), (args, res)
        assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"], args
        words, _ = T.judge("Ок", None, out["results"], out["journal"])
        assert CONTRACT_WORDS in words, (args, words)


def test_p1_model_name_or_matching_filter_not_used_as_search():
    """Имя модели кодом не проверить — в поиск не идёт; фильтр, совпавший с привязкой (тот же срок), конфликтом не
    становится: в дверь идёт ровно запрос кода."""
    reg = Registry([DOC1, DOC2])
    out = run(Script({"tool": "contract", "args": {"name": "Иван Петров"}},
                     {"tool": "contract", "args": {"date_from": TERM[0], "date_to": TERM[1]}}, final("Ок")), reg)
    assert reg.calls == [{"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}] * 2, reg.calls
    assert outcomes(out) == [("contract", T.FACT), ("contract", T.FACT)], out["results"]


def test_p1_no_number_no_registry_read():
    """Отрицательный: номера обращения нет — без связи с клиентом реестр не читается."""
    reg = Registry([DOC1])
    out = run(Script({"tool": "contract", "args": {}}, final("Ок")), reg, number="")
    assert reg.calls == [] and out["results"][0]["outcome"] != T.FACT, (reg.calls, out["results"])


def test_p1_request_identity_is_code_query():
    """Тождество запроса договора — запрос, посланный КОДОМ: два вызова с разными словами модели и одним запросом двери
    — один запрос; позднее «не факт» того же запроса (таймаут) снимает прежний FACT (AGENTDEDUP0410)."""
    reg = Registry([DOC1], fail_after=1)
    out = run(Script({"tool": "contract", "args": {}},
                     {"tool": "contract", "args": {"date_from": TERM[0], "date_to": TERM[1]}}, final("Ок")), reg)
    a, b = out["results"]
    assert (a["outcome"], b["outcome"]) == (T.FACT, T.TIMEOUT), (a["outcome"], b["outcome"])
    assert a["req"] == b["req"], (a["req"], b["req"])
    assert NUMBER not in a["req"], a["req"]                    # номер обращения в тождество не пишется
    assert not [f for f in T.accepted(out["results"]) if f["kind"] == "contract"]


def test_p1_other_term_search_respects_deadline():
    """K07-поиск без срока — тоже вызов двери: модель думала до T+55, поиск в сроке шёл 40 с (до T+95, за пределом
    сверки AGENTDEDUP0410) — второго обращения к реестру нет; в сроке договора нет — «не найдено» со словами, а не
    поиск после дедлайна. Первый (и единственный) запрос — запрос КОДА."""
    clk = Clock()
    reg = Registry([DOC2])
    stamps = []

    def slow_reg(**kw):
        stamps.append(clk.t)
        out = reg(**kw)
        clk.t += 40.0
        return out

    script = Script({"tool": "contract", "args": {}}, final("Ок"))

    def model(system, user):
        clk.t += 55.0 if not script.seen else 0.0
        return script(system, user)

    out = T.run(model, "S", "U", {"rental": rental_door(), "contract": slow_reg, "contract_pdf": pdf_door},
                number=NUMBER, clock=clk)
    stop = T0 + T.MAX_SEC - T.FALLBACK_SEC
    assert reg.calls == [{"phone": NUMBER, "date_from": TERM[0], "date_to": TERM[1]}], reg.calls
    assert all(t < stop for t in stamps), (stamps, stop)
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.EMPTY and "предел сверки" in res["reason"], res
    assert out["state"] == T.OVER, out["state"]


# ═══ п.2 СДАЧА кодом ═════════════════════════════════════════════════════════════════════════════════════════

HEAD = "РАСЧЁТ КОДА — сдача"        # голова блока расчёта (в инструкции инструментов слово «РАСЧЁТ КОДА» есть всегда)


def _block(script):
    return [u for u in script.seen if HEAD in u]


def test_p2_c3_change_210_by_code_at_end():
    """С3 (K05): итог 7790 (касса этой аренды и лист), внесено 8000 со слов клиента → в запрос модели код кладёт
    «сдача 210 THB … в конце аренды»; числа черновика имеют опору, «8000» названо словами клиента — причина
    «сумму подтверждает человек», а не «денежное утверждение без опоры»."""
    s = c3_script()
    a = adapter(s, [tx_item()], question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "в конце аренды" in blk[-1] and "итог 7790 THB" in blk[-1], s.seen[-1][-600:]
    assert HEAD not in s.seen[0] and HEAD not in s.seen[1], "расчёт до чтения кассы"
    assert K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]
    assert CHANGE_WORDS in out["handoff"], out["handoff"]
    assert out["claims"] == [], out["claims"]


def test_p2_cash_exceeds_total_confirmed_by_cash():
    """Касса записала 8000 при итоге 7790, клиент называет те же 8000 → сдача 210 по КАССЕ: эскалации «со слов
    клиента» нет."""
    s = c3_script()
    a = adapter(s, [tx_item(amount=8000, description="Nmax 90101 +8000 аренда K3-BK-001")], question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "касса: оплачено 8000 при итоге 7790" in blk[-1], s.seen[-1][-600:]
    assert CHANGE_WORDS not in out["handoff"] and K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]


def test_p2_deposit_not_added_to_payment():
    """Залог той же аренды в кассе с оплату не складывается: сдача 210, а не «оплачено 12790»."""
    s = c3_script()
    a = adapter(s, [tx_item(), tx_item(row=12, amount=3000, category="deposit",
                                       description="Nmax 90101 залог 3000 K3-BK-001")], question=C3_QUESTION)
    a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача 210 THB" in blk[-1] and "12790" not in blk[-1], s.seen[-1][-600:]


def _refused(cash_items, text, why):
    s = c3_script(text)
    a = adapter(s, cash_items, question=C3_QUESTION)
    out = a.draft(NUMBER, 5)
    blk = _block(s)
    assert blk and "сдача НЕ посчитана" in blk[-1] and why in blk[-1], s.seen[-1][-700:]
    assert "сдача 210" not in blk[-1], blk[-1]
    assert K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]        # 210 названа без опоры
    assert not T.pay_confirmed(a.last["tools"]["journal"].facts)
    return out


def test_p2_neg_unconfirmed_cash_no_change_no_payment():
    """Отрицательный: в кассе оплаты аренды нет — «отдал 8000 наличными» остаётся словами клиента: ни подтверждения
    оплаты, ни сдачи; текст «оплата 8000 получена» — причина «оплата не подтверждена сверкой»."""
    out = _refused([], "Оплата 8000 бат получена. Сдача 210 бат — в конце аренды, вместе с возвратом залога.",
                   "в кассе нет")
    assert T.PAY_WORDS in out["handoff"], out["handoff"]


def test_p2_neg_foreign_rental_no_change():
    """Отрицательный: в кассе 7790 ЧУЖОЙ аренды (K3-BK-002) — деньгами этой аренды не считаются, сдачи нет."""
    _refused([tx_item(booking="K3-BK-002", description="Nmax 90101 +7790 аренда K3-BK-002")], C3_TEXT, "в кассе нет")


def test_p2_neg_other_currency_no_change():
    """Отрицательный: оплата этой аренды записана в USD — разные валюты не складываются и не пересчитываются."""
    _refused([tx_item(amount=220, currency="USD", description="Nmax 90101 +220 USD аренда K3-BK-001")], C3_TEXT,
             "в другой валюте")


def test_p2_control_no_handed_no_block():
    """КОНТРОЛЬ: клиент не называл переданных наличных — блока «РАСЧЁТ КОДА» нет, запрос прежний."""
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
               final("Здравствуйте! Подскажу по аренде."))
    adapter(s, [tx_item()], question="Подскажите, до какого числа у меня аренда?").draft(NUMBER, 5)
    assert not _block(s), s.seen


# ═══ п.3 N4: одно определение «текст утверждает, что оплата получена» ═══════════════════════════════════════════

def _facts_no_second_source():
    """Касса этой аренды + её строка листа, второго источника нет (ни договора, ни суммы в переписке)."""
    return T.accepted([T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0), T.cash_result(tx([tx_item()]), at=T0)])


AFFIRM = ["Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат.",          # K15 real
          "Добрый день! Да, оплата аренды NMAX 90101 на 7790 бат у нас отражена, всё в порядке.",  # K02 real
          "Вижу вашу оплату 7790 бат, всё в порядке.",
          "С оплатой всё в порядке, спасибо!",
          "We can see your payment of 7790 baht, all good.",
          "Payment is reflected in our records."]
NOT_CLAIM = ["Оплату пока не вижу — коллега проверит поступление и вам ответит.",
             "Передал коллеге: он сверит поступления по кассе и подтвердит оплату аренды.",           # K04 real
             "Как только оплата отразится в кассе, подтвердим.",
             "Оплата будет подтверждена после сверки.",
             "Оплата подтверждена?",
             "Если оплата прошла, договор пришлём.",
             "Оплата пока не отражена.",
             "We will confirm the payment once it is received."]


def test_p3_affirmative_forms_flagged_without_second_source():
    """N4: утвердительные формы (дословные фразы K15 и K02 реального прогона и близкие) без второго источника —
    причина «оплата не подтверждена сверкой» тем же определением, что у F3 шага 1."""
    facts = _facts_no_second_source()
    for text in AFFIRM:
        assert [w for w, _why in T.money_roles(text, facts)] == [T.PAY_WORDS], text


def test_p3_negation_future_question_not_confirmation_not_blocked():
    """Отрицательный N4: отрицание, обещание будущей проверки, условие и вопрос — не подтверждение: ни ложной
    блокировки причиной, ни сумм «полученной оплаты»."""
    facts = _facts_no_second_source()
    for text in NOT_CLAIM:
        assert T.money_roles(text, facts) == [], (text, T.money_roles(text, facts))
        assert T.pay_claimed(text) == set(), (text, T.pay_claimed(text))


def test_p3_claimed_sums_same_definition():
    """«Сумма, названная полученной оплатой» — тем же определением: у фразы K15 это 7790, у фразы K02 номер байка
    90101 суммой не стал."""
    assert T.pay_claimed(AFFIRM[0]) == {7790}, T.pay_claimed(AFFIRM[0])
    assert T.pay_claimed(AFFIRM[1]) == {7790}, T.pay_claimed(AFFIRM[1])


def test_p3_k15_draft_flagged_end_to_end():
    """K15 real дословно: rental + cash, договора нет — черновик «В кассе вижу оплату…» получает причину кода."""
    text = ("Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат. Если вы сегодня оплачивали "
            "что-то ещё, коллега проверит поступление и вам ответит. Договор тоже передам коллеге, он пришлёт его "
            "отдельным сообщением.")
    s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}}, final(text))
    out = adapter(s, [tx_item()], question="Я оплатил аренду, подтвердите").draft(NUMBER, 5)
    assert T.PAY_WORDS in out["handoff"], out["handoff"]


def test_p3_control_backed_confirmation_not_blocked():
    """КОНТРОЛЬ: подтверждение с опорой (касса + договор той же аренды) причины не получает — ни на ремонте, ни до."""
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER,
                            rental=T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0))
    facts = T.accepted([T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0), T.cash_result(tx([tx_item()]), at=T0),
                        con])
    assert T.money_roles(AFFIRM[1], facts) == [], T.money_roles(AFFIRM[1], facts)


# ═══ п.3b N4 (D1 приёмки шага 3, fix_review VERDICT §9): ФОРМЫ, а не список фраз ═══════════════════════════════

CLOSE_ACCEPT = ["В кассе есть ваша оплата аренды на 7790 бат.", "Оплата есть в кассе.",            # приёмка ДОСЛОВНО:
                "Оплата зафиксирована в кассе.", "Аренда оплачена.", "Оплачено, спасибо!",           # fix_review VERDICT §9,
                "Платёж получен.", "Деньги получили, спасибо.", "Your payment went through."]       # out_rv_newx_a :49-56
CLOSE_OWN = ["Оплата за аренду учтена в кассе.", "Ваш перевод пришёл, спасибо.", "Средства зачислены на счёт.",
             "Платёж прошёл успешно.", "Получена ваша оплата за аренду 7790 бат.", "Зафиксировали ваш платёж.",
             "Бронь полностью оплачена.", "Предоплата внесена, спасибо.", "Деньги дошли.",
             "На счёте имеется ваш платёж.",
             "The rental is paid.", "Your rent has been paid.", "We got your transfer, thanks.",
             "The money arrived this morning.", "All paid, thank you!", "Funds have been credited to our account."]
NOT_CLOSE = ["Оплата пока не поступила.", "Аренда ещё не оплачена.", "Деньги ещё не получили.",          # отрицание
             "Платёж поступит завтра.", "Оплата будет зафиксирована после сверки.", "Оплачено будет при выдаче байка.",
             "Платёж должен быть проведён до выдачи байка.",                                          # будущее, долг
             "Проверю, получена ли оплата.", "Если аренда оплачена, договор пришлём.",                 # проверка, условие
             "If the money arrived, please let us know.",
             "Оплачено?", "Деньги получили?", "Has your payment gone through?",                        # вопрос
             "Your payment hasn't gone through yet.",
             "Оплата наличными тоже есть.", "Получили ваш запрос на оплату.", "Payment link received, thank you.",
             "Перевод договора на английский получен.", "Срок оплаты прошёл.", "The rent is paid at pickup."]


def _facts_backed():
    """Касса этой аренды + её строка листа + договор, привязанный к ней кодом: оплата подтверждена, опора 7790."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    return T.accepted([rent, T.cash_result(tx([tx_item()]), at=T0), con])


def test_p3b_acceptance_close_forms_flagged():
    """D1: 8 близких утвердительных форм приёмки шага 3 (дословно) без второго источника — причина «оплата не
    подтверждена сверкой» тем же определением (`_PayClaim`)."""
    facts = _facts_no_second_source()
    miss = [t for t in CLOSE_ACCEPT if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss


def test_p3b_own_close_forms_flagged():
    """D1: свои близкие формы RU/EN (причастие оплаты, предмет + сказуемое получения/учёта, сказуемое + предмет) —
    ловятся формами, а не списком."""
    facts = _facts_no_second_source()
    miss = [t for t in CLOSE_OWN if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss


def test_p3b_not_claims_not_blocked():
    """D1, отрицательный: отрицание, будущее/долженствование, проверка, условие, вопрос; «есть» без кассы/учёта;
    предмет после предлога; «payment link»; «перевод договора»; «срок оплаты»; правило «is paid at pickup» — не
    утверждение: ни причины, ни сумм «полученной оплаты»."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t))) for t in NOT_CLOSE
           if T.money_roles(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3b_claimed_sums_close_forms():
    """D1: сумма, названная полученной оплатой близкой формой, — тем же определением (7790), без чисел — пусто."""
    assert T.pay_claimed(CLOSE_ACCEPT[0]) == {7790}, T.pay_claimed(CLOSE_ACCEPT[0])
    assert T.pay_claimed("Получена ваша оплата за аренду 7790 бат.") == {7790}
    assert T.pay_claimed("Платёж получен.") == set()


def test_p3b_deposit_subject_existing_role():
    """D1 + роли money_roles: подлежащее — залог («Залог оплачен», «деньги за залог получили») — роль залога
    (`_DEP_CLAIM`), а не оплата аренды; аренда названа раньше залога — утверждение оплаты аренды."""
    facts = _facts_no_second_source()
    assert [w for w, _why in T.money_roles("Залог оплачен.", facts)] == [T.ROLE_WORDS]
    assert T.pay_claimed("Залог оплачен.") == set()
    assert T.PAY_WORDS not in [w for w, _why in T.money_roles("Деньги за залог получили.", facts)]
    assert T.PAY_WORDS in [w for w, _why in T.money_roles("Аренда и залог оплачены.", facts)]


def test_p3b_control_backed_close_forms_not_blocked():
    """КОНТРОЛЬ D1: близкие формы С опорой (касса + договор той же аренды, сумма 7790) — причины нет."""
    facts = _facts_backed()
    assert T.pay_confirmed(facts) is True
    bad = [(t, T.money_roles(t, facts)) for t in CLOSE_ACCEPT + CLOSE_OWN if T.money_roles(t, facts)]
    assert not bad, bad


# ═══ п.3c: те же исключения не-утверждений у ПРЕЖНИХ форм `_PAY_AFFIRM`; исход каждого совпадения НАЗВАН ═══════

# имена исходов — литералами: на 6f6e754 и старше таких констант нет (как SV_WORDS выше)
V_CLAIM, V_WORD = "утверждение", "основа сказуемого — начало другого слова"
V_MUST, V_PREP, V_NEXT = "долженствование или ожидание", "предмет после предлога", "предмет — документ, а не оплата"
V_EXIST, V_DEP = "«есть» без кассы, учёта, счёта или «ваша оплата»", "подлежащее — залог"

# не-утверждения, которые ловили ПРЕЖНИЕ формы: на 6f6e754 каждое получало причину «оплата не подтверждена сверкой»
OLD_NOT = [("После оплаты договор пришлём.", V_WORD),                              # три названные решением — дословно
           ("Оплата должна быть получена до выдачи байка.", V_MUST),
           ("Оплата должна быть получена до выдачи…", V_MUST),
           ("Ссылку на оплату получили.", V_PREP),
           ("Оплата требует подтверждения коллегой.", V_MUST),                     # FIX.md «Шаг 3b» п.7.4
           ("Оплата за прошлую неделю.", V_WORD),
           ("Оплата обязательно должна быть подтверждена коллегой.", V_MUST),      # долженствование и ожидание
           ("Оплата ожидает подтверждения.", V_MUST),
           ("Оплата ждёт подтверждения коллегой.", V_MUST),
           ("Payment must be recorded before pickup.", V_MUST),
           ("Счёт на оплату получили, спасибо.", V_PREP),                           # предмет после предлога цели/времени
           ("Реквизиты для оплаты получили.", V_PREP),
           ("Вижу запрос на оплату.", V_PREP),
           ("После оплаты бронь подтверждается автоматически.", V_PREP),
           ("Без оплаты бронь подтверждена только на сутки.", V_PREP),
           ("До оплаты бронь подтверждена только на сутки.", V_PREP),
           ("Перед оплатой получите подтверждение брони.", V_PREP),
           ("Link for payment received, thank you.", V_PREP),
           ("We keep the bike for you without payment received until tomorrow.", V_PREP),
           ("Оплата при получении байка, наличными или переводом.", V_WORD),        # основа внутри другого слова
           ("Оплату пришлите, пожалуйста, на карту.", V_WORD),
           ("Оплату пришлось вернуть клиенту.", V_WORD),
           ("Оплата видимо ещё в пути.", V_WORD),
           ("Получили перевод договора, спасибо.", V_NEXT),                         # документ, а не оплата
           ("Payment details recorded in the booking.", V_NEXT)]
# те же исключения у форм шага 3b — тем же именем (одно определение на оба прохода)
SAME_3B = [("Платёж должен быть проведён до выдачи байка.", V_MUST), ("Оплачено будет при выдаче байка.", V_MUST),
           ("Получили ваш запрос на оплату.", V_PREP), ("Payment link received, thank you.", V_NEXT),
           ("Оплата наличными тоже есть.", V_EXIST), ("Залог оплачен.", V_DEP), ("Деньги за залог получили.", V_DEP)]
# прежде пойманные утверждения прежних форм и положительные близнецы каждого исключения — по-прежнему ловятся
OLD_AFFIRM = ["Оплата получена.", "Мы получили вашу оплату.", "Оплата прошла, всё хорошо.", "Оплата пришла, спасибо.",
              "Оплату видим в кассе, спасибо.", "Оплата подтверждена коллегой.", "Предоплата получена, спасибо.",
              "Доплата 500 бат получена.", "Payment received, thank you.", "We received your payment.",
              "Your payment is reflected in the cash book.",
              "С оплатой всё в порядке, спасибо!", "По оплате всё в порядке.",       # предлог темы — утверждение
              "Подтверждение об оплате получено.", "По оплате есть подтверждение.",
              "Получили вашу оплату на карту.", "Оплата до выдачи байка получена.",   # предлог НЕ перед предметом
              "Оплата без комиссии получена.", "После проверки кассы оплата 7790 бат получена.",
              "После того как оплата поступила, мы отправили договор.",
              "Оплата за прошлую неделю получена.",                                 # «прошлую» — не сказуемое, оно дальше
              "Оплаты за прошлую и эту недели получены.",
              "Оплата должным образом отражена в кассе.",                           # «должным образом» — не долженствование
              "Оплата получена, договор будет у вас завтра.",                       # будущее в ДРУГОЙ клаузе
              "Оплата подтверждена, больше ничего не требуется.",
              "Получили перевод, спасибо."]                                         # перевод денег, не документа


def _verdicts(text):
    return {v for _match, v in T._PAY_CLAIM.explain(text)}


def test_p3c_old_forms_not_claims_not_blocked():
    """п.3c: не-утверждения прежних форм (в т.ч. три названные решением дословно) — ни причины «оплата не подтверждена
    сверкой», ни сумм «полученной оплаты». На 6f6e754 каждая из них причину получала."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t))) for t, _name in OLD_NOT
           if T.money_roles(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3c_not_claim_names_its_exclusion():
    """п.3c: исход совпадения НАЗВАН — у каждой фразы имя того исключения, которое к ней относится (а не «какое-то
    сработало»), и одно и то же у прежних форм и у форм 3b (одно определение на оба прохода)."""
    wrong = [(t, name, T._PAY_CLAIM.explain(t)) for t, name in OLD_NOT + SAME_3B if _verdicts(t) != {name}]
    assert not wrong, wrong


def test_p3c_verdict_never_empty_two_former_blind_branches():
    """п.3c, храповик слепых читателей: исход — всегда НЕПУСТОЕ имя; `search` говорит «утверждение» ровно тогда, когда
    так назван хотя бы один исход. Две ветки, которые до 3c отдавали голое False оттого, что шаблон НЕ нашёл слова
    кассы или аренды, называют себя; с найденным словом — утверждение (положительные близнецы)."""
    every = (AFFIRM + NOT_CLAIM + CLOSE_ACCEPT + CLOSE_OWN + NOT_CLOSE + OLD_AFFIRM
             + [t for t, _name in OLD_NOT + SAME_3B])
    for text in every:
        got = T._PAY_CLAIM.explain(text)
        assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
        assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text)), (text, got)
    assert _verdicts("Оплата наличными тоже есть.") == {V_EXIST}
    assert _verdicts("Для вашего удобства есть оплата картой.") == {V_EXIST}
    assert _verdicts("Залог оплачен.") == {V_DEP} and _verdicts("Деньги за залог получили.") == {V_DEP}
    assert V_CLAIM in _verdicts("Оплата есть в кассе.") and V_CLAIM in _verdicts("На счёте имеется ваш платёж.")
    assert V_CLAIM in _verdicts("Аренда и залог оплачены.")


def test_p3c_must_governs_predicate_not_whole_clause():
    """п.3c: долженствование и будущее снимают утверждение, только когда управляют сказуемым — стоят в клаузе до конца
    сказуемого или сразу за ним. Слово дальше — уже другое сказуемое: «Аренда оплачена и договор будет отправлен
    завтра.» — утверждение (на 6f6e754 у форм 3b «будет» где угодно в клаузе снимало его)."""
    facts = _facts_no_second_source()
    for text in ("Аренда оплачена и договор будет отправлен завтра.", "Оплата получена и договор будет отправлен завтра.",
                 "Деньги получили и байк будет ждать вас утром."):
        assert [w for w, _why in T.money_roles(text, facts)] == [T.PAY_WORDS], (text, T._PAY_CLAIM.explain(text))
    for text in ("Оплачено будет при выдаче байка.", "Аренда оплачена должна быть до выдачи байка.",
                 "Платёж должен быть проведён до выдачи байка.", "Оплата должна быть получена до выдачи байка."):
        assert T.money_roles(text, facts) == [], (text, T._PAY_CLAIM.explain(text))


def test_p3c_control_nothing_caught_is_lost():
    """КОНТРОЛЬ п.3c: ни одно прежде пойманное утверждение не теряется — K15 и формы K02 реального прогона (AFFIRM),
    8 форм приёмки шага 3 дословно (CLOSE_ACCEPT), свои формы 3b (CLOSE_OWN) и прежние формы с положительными
    близнецами исключений (OLD_AFFIRM): причина «оплата не подтверждена сверкой» — как на 6f6e754."""
    facts = _facts_no_second_source()
    miss = [(t, T.money_roles(t, facts)) for t in AFFIRM + CLOSE_ACCEPT + CLOSE_OWN + OLD_AFFIRM
            if [w for w, _why in T.money_roles(t, facts)] != [T.PAY_WORDS]]
    assert not miss, miss
    assert T.pay_claimed("После проверки кассы оплата 7790 бат получена.") == {7790}
    # роль залога на прежние формы НЕ распространена: «залог» раньше «аренды» в клаузе оплату аренды не снимает
    assert T.PAY_WORDS in [w for w, _why in T.money_roles("Залог и оплата аренды получены.", facts)]


# ═══ п.3d: R1 — потерянные утверждения, R2 — контроль из объединения списков, R3 — два семейства ═══════════════

V_NOT, V_LATER, V_ASKED = "отрицание", "будущее, проверка или условие", "вопрос"
V_THEIR = "получатель — клиент, а не мы"

# КОРПУСА ПРОВЕРЯЮЩЕГО кругов 3b+3c — ДОСЛОВНО, данными (источник: tmp/k3_0910/fix_review3c/rv3c_corpus.py, sha256
# f5ac0c13…8211, и rv3c_corpus2.py, 04294a3d…70df; имена списков — те же с приставкой RV_). ACCEPT8 = CLOSE_ACCEPT выше.
RV_K15 = ("Здравствуйте! В кассе вижу оплату аренды по вашей брони от 05.10 на 7790 бат. Если вы сегодня оплачивали "
          "что-то ещё, коллега проверит поступление и вам ответит. Договор тоже передам коллеге, он пришлёт его "
          "отдельным сообщением.")
RV_K02 = "Добрый день! Да, оплата аренды NMAX 90101 на 7790 бат у нас отражена, всё в порядке."
RV_OWN_AFFIRM = [
    "Ваш платёж зачислен, спасибо.", "Оплату за аренду приняли, спасибо.", "Перевод на 7790 бат дошёл.",
    "Деньги за аренду пришли, всё отлично.", "Аренда за 10 дней оплачена полностью.", "Всё оплачено, ждём вас завтра.",
    "Мы зафиксировали вашу оплату в журнале.", "Платёж по вашей брони проведён.", "Вашу оплату подтверждаю.",
    "Средства поступили на наш счёт сегодня утром.", "Оплата аренды внесена в полном объёме.",
    "Предоплата за байк учтена.", "Видим ваш перевод, спасибо.", "Подтверждаем: оплата принята.",
    "Your payment has cleared.", "The transfer has been credited, thank you.",
    "We have received the funds for your rental.", "Your booking is fully paid.", "The rental was paid yesterday.",
    "Payment for your booking has been processed.", "Your money came through this morning.",
    "The rent is paid, thank you.", "We confirmed your payment.", "Your transfer arrived safely."]
RV_OWN_NOT = [
    "Ваш платёж пока не зачислен.", "Перевод ещё не дошёл до нас.", "К сожалению, средства на счёт не поступили.",
    "The transfer has not arrived yet.", "Your booking isn't paid yet.", "Как только перевод дойдёт, сразу сообщим.",
    "Платёж будет проведён завтра утром.", "Мы проверим, зачислены ли средства.",
    "We will let you know once the funds are credited.", "Your payment will be processed tomorrow.",
    "Если перевод уже дошёл, пришлём договор.", "When the money arrives, we'll confirm.",
    "Once your payment has cleared, the booking is confirmed.", "Платёж уже проведён?", "Вы уже оплатили аренду?",
    "Has the transfer been credited?", "Аренда оплачена?", "Аренда должна быть оплачена до выдачи байка.",
    "The rent must be paid before pickup.", "Оплату нужно внести до 12:00.", "Перевод ожидается сегодня.",
    "Оплата ожидается сегодня, пока не поступила."]
RV_NAMED3 = ["После оплаты договор пришлём.", "Оплата должна быть получена до выдачи байка.",
             "Ссылку на оплату получили."]
RV_OWN_PLAIN = [
    "Ваш запрос получен, скоро ответим.", "После оплаты пришлём договор.", "Оплата должна поступить до выдачи байка.",
    "Ссылку на оплату отправили вам в этот чат.", "Ваше сообщение получили, спасибо.", "Документы получены, спасибо.",
    "Оплата возможна наличными или переводом.", "Оплата производится при получении байка.",
    "Способ оплаты подтвердим позже.", "Для оплаты пришлите, пожалуйста, фото паспорта.",
    "Когда поступит оплата, мы сообщим.", "Оплата картой проходит через терминал.",
    "Бронь подтверждена, оплата при встрече.", "Заявку на возврат залога получили.",
    "Чек об оплате пришлите сюда, пожалуйста.", "Оплата за следующий месяц должна прийти до пятницы.",
    "Информацию об оплате вы получите в договоре.", "Подтверждение оплаты придёт вам на почту.",
    "Оплата прошлого месяца не учитывается.", "Мы приняли вашу заявку на оплату картой.",
    "Получили ваш вопрос про перевод.", "Вижу ваше сообщение про деньги.", "Есть оплата картой и наличными.",
    "Оплаченные дни не возвращаются.", "Сумма к оплате указана в договоре.", "Оплата принимается наличными.",
    "Your request has been received, we will reply soon.", "We sent you the payment link.",
    "Payment is due at pickup.", "The payment details are in the contract."]
RV_ADVERSARIAL = [
    "You should know that your payment has been received.",
    "I need to let you know that your payment has been received.",
    "I should mention that we received your payment.", "We have to tell you that the payment is confirmed.",
    "Thank you for the payment received today.", "Thanks for your payment received.",
    "7790 бат на оплату аренды получены.", "Сумма на оплату аренды получена.", "Деньги на оплату аренды получены.",
    "Ваша оплата должна была поступить вчера и поступила.", "Надо сказать что оплата получена.",
    "Оплата получена нужно только подписать договор.", "Без оплаты залога оплата аренды получена.",
    "После оплаты получили ваш чек, всё в порядке.", "Вашу оплату для брони получили.",
    "После вашего перевода оплата получена.", "На карту оплата получена.", "Оплата на карту получена.",
    "Оплата получена, нужно только подписать договор.", "Оплата получена и байк ждёт вас.",
    "Payment received and you should get the contract soon.",
    "Your payment has been received and we will send the contract.", "Как и должно быть, оплата получена.",
    "Оплата необходимой суммы получена.", "Оплата ожидаемой суммы получена.", "Байк ждёт вас, оплата получена."]
# RESIDUAL_INFO проверяющего (16 наблюдений): 14 — с причиной; две фразы БЕЗ слова оплаты, денег или суммы
# («Да, всё пришло.», «We got it, thanks!») определение по ТЕКСТУ не судит — их смысл задаёт вопрос клиента, которого
# `money_roles` не видит (остаток круга 3d, назван в FIX.md); набор о них ничего не утверждает
RV_RESIDUAL = [
    "Подтвердили поступление оплаты, спасибо.", "Подтверждаю получение оплаты.",
    "Подтверждаем поступление оплаты за аренду.", "Поступление оплаты подтверждаем.", "Получили 7790 бат, спасибо.",
    "Да, 7790 бат получили.", "Деньги у нас, спасибо.", "Сумма получена.",
    "Платёж 4100 бат в кассе записан на другую бронь, а 150 долларов — в иностранной валюте; подтверждать сам не "
    "буду — передаю коллеге.",
    "Подтверждаю оплату при получении байка: наличными.", "Оплата получена не полностью.",
    "Платёж принят банком в обработку.", "Бронь подтверждена оплата при встрече", "Payment confirmed."]
RV_RESIDUAL_OPEN = ["Да, всё пришло.", "We got it, thanks!"]
RV_OLD_CONTROL = [
    "Оплата получена.", "Мы получили вашу оплату.", "Оплата 7790 бат получена, спасибо.", "Оплата 8000 бат получена.",
    "Оплата прошла успешно.", "Оплата поступила, спасибо.", "Оплату вижу, всё в порядке.", "С оплатой всё в порядке.",
    "Оплата подтверждена.", "Получили деньги, спасибо.", "Получили перевод, спасибо.", "Payment received, thank you.",
    "We received your payment.", "Payment is confirmed.", "Paid in full, thank you.", "We can see your payment.",
    "Payment has been received.", "Ваша оплата за аренду у нас отражена.", "В кассе видна ваша оплата.",
    "Оплата аренды за 10 дней пришла."]
RV_MORE_ADV = [
    "We must confirm that we received your payment in full.", "Thank you for your payment received on 5 October.",
    "We need to mention the payment is confirmed.", "Ваши 7790 бат на оплату аренды поступили.",
    "Сумма для оплаты брони поступила.", "8000 бат для оплаты аренды получили, спасибо.",
    "Оплата за аренду должна была прийти вчера и пришла.", "На оплату аренды получили от вас 7790 бат.",
    "После оплаты всё прошло успешно.", "Вам нужно знать что оплата получена.",
    "You need to know your payment is confirmed.", "Должен сообщить что ваша оплата поступила."]
RV_TWINS_OK = [
    "Just to let you know that your payment has been received.",
    "I'm happy to confirm that your payment has been received.", "Thank you, payment received for the rental.",
    "Перевод для оплаты аренды получили.", "В счёт оплаты аренды получили 7790 бат.", "Оплату на 7790 бат получили.",
    "Вам нужно знать: оплата получена.", "Должен сообщить, что ваша оплата поступила.",
    "Нужно отметить: оплата получена.", "Оплата до 12:00 получена."]
RV_TWINS_NOT = [
    "You should pay before pickup so that the payment is confirmed.", "The payment must be received before pickup.",
    "Ссылку для оплаты получили?", "Счёт на оплату аренды получен, спасибо.",
    "После оплаты подтверждение придёт автоматически.", "Оплата должна была поступить вчера.",
    "Thank you for your payment request, received.", "We need to confirm your payment first."]

# СВОИ фразы шага 3d (нет ни в одном прежнем корпусе)
R1_OWN = [                                              # R1: слово долженствования и предлог — НЕ при этом сказуемом
    "You should know we received your payment.", "I should add that your payment has cleared.",
    "Надо отметить что платёж получен.", "Должны сообщить что деньги поступили.",
    "Оплата должна была поступить сегодня и поступила.", "Thanks a lot for the payment received yesterday.",
    "Перевод на оплату аренды получили.", "3000 бат на оплату продления получены.",
    "Оплата получена можно забирать байк.", "Можем сообщить что оплата поступила.",
    "We will send the contract now that your payment has been received.",    # причинный союз без запятой
    "Договор отправим сегодня потому что оплата получена.",
    "Без оплаты доставки оплата аренды получена.", "После оплаты получили от вас чек, спасибо.",
    "It should be noted that your payment has been received.",
    "For the payment received yesterday, thank you.", "Отправленное вами на оплату аренды получили."]
R1_OWN_NOT = [                                          # те же исключения там, где они на своём месте
    ("Нужно проверить что оплата прошла.", V_MUST),                        # обязанность ПРОВЕРИТЬ — не утверждение
    ("We need to check that your payment has been received.", V_MUST),
    ("Нужно чтобы оплата поступила до выдачи байка.", V_MUST),             # цель
    ("Оплата должна быть получена и подтверждена до выдачи байка.", V_MUST),
    ("We need to wait until the payment is confirmed.", V_MUST),
    ("Оплата может быть произведена наличными или картой.", V_MUST),       # возможность — правило, а не факт
    ("The payment should have been received by Friday.", V_MUST),
    ("Оплата должна до выдачи байка быть получена.", V_MUST),
    ("Payment can be made in cash or by transfer.", None),
    ("Payment can be received in cash or by transfer.", V_MUST),
    ("Ссылку на оплату 7790 бат получили.", V_PREP),
    ("После оплаты 7790 бат бронь подтверждается автоматически.", V_PREP),
    ("Квитанцию для оплаты получили.", V_PREP),
    ("Invoice for payment received, thanks.", V_PREP),
    ("Thank you for your payment request received yesterday.", V_NEXT)]
R3_NOUN_AFFIRM = [                                      # R3 (i): подтверждение получения существительным
    "Подтверждаю получение платежа.", "Подтверждаем поступление предоплаты.",
    "Подтвердили зачисление средств, спасибо.", "Получение денег подтверждаем.", "Поступление платежа подтверждено.",
    "Подтверждаю приход оплаты за аренду.", "Могу подтвердить получение оплаты.", "Вижу поступление 7790 бат от вас.",
    "We confirm receipt of your payment.", "I can confirm receipt of your transfer.",
    "We acknowledge receipt of the funds.", "Confirmed receipt of your payment, thank you.",
    "Receipt of your transfer acknowledged.", "Payment receipt confirmed."]
R3_NOUN_NOT = [
    ("Поступление оплаты подтвердить не могу.", None), ("Подтвердим получение оплаты после сверки.", None),
    ("Подтвердите получение договора, пожалуйста.", None), ("Подтверждение получения оплаты придёт на почту.", None),
    ("Подтверждаю получение паспорта и прав.", None), ("Подтверждаем поступление заявки.", None),
    ("Вы подтвердили получение оплаты?", V_ASKED), ("Поступление оплаты должно быть подтверждено коллегой.", V_MUST),
    ("Подтверждаю получение залога.", None), ("We will confirm receipt of your payment tomorrow.", None),
    ("Can you confirm receipt of the payment?", None), ("Please confirm receipt of the payment link.", None),
    ("We confirm receipt of your documents.", None), ("We cannot confirm receipt of your payment yet.", None)]
R3_SUM_AFFIRM = [                                       # R3 (ii): сказуемое получения с суммой или словом суммы
    "Получили от вас 7790 бат, спасибо.", "7790 бат поступили на счёт.", "Ваши 7790 бат получены.",
    "Сумму получили полностью.", "Вся сумма поступила, спасибо.", "Деньги уже у нас.", "Ваши 7790 бат у нас.",
    "Приняли 7790 бат наличными.", "Поступило 7 790 бат, спасибо.", "Получили 7790, спасибо.",
    "We received 7790 baht, thank you.", "Got your 7790 THB, thanks.", "7790 baht has been received.",
    "The full amount has been received.", "We have received the full amount.", "We have your payment.",
    "Your 7790 baht arrived this morning."]
R3_SUM_NOT = [
    ("7790 бат пока не получили.", V_NOT), ("Сумма ещё не поступила.", V_NOT),
    ("Как только 7790 бат поступят, сообщим.", None), ("Сумма будет получена завтра.", V_LATER),
    ("Если сумма получена, пришлём договор.", V_LATER), ("Вы получили 7790 бат?", V_ASKED),
    ("Сумма должна быть получена до выдачи байка.", V_MUST),
    ("Получили ваш запрос на 7790 бат.", V_PREP), ("Счёт на сумму 7790 бат получили.", V_PREP),       # документ
    ("За 7790 бат получили бы NMAX на 10 дней.", V_PREP),
    ("Получили ваш паспорт и фото прав, спасибо.", None), ("Получили 3 фото, спасибо.", None),
    ("2 батареи получили, спасибо.", None),
    ("Итог аренды 7790 бат.", None), ("Итого к оплате 7790 бат.", None), ("С 8000 сдача 210 бат.", None),   # цена, итог, сдача
    ("Вы написали, что перевели 7790 бат.", None),                                                  # слова клиента
    ("Вы получили 500 бат обратно.", V_THEIR), ("You received 210 baht change.", V_THEIR),
    ("Получили 3000 бат залога.", V_DEP),                                                           # роль залога
    ("Оплата у нас проходит через терминал.", None), ("We have not received 7790 baht yet.", V_NOT),
    ("The total is 7790 baht.", None), ("We received your request for 7790 baht.", V_PREP),
    ("Once we have your payment, we will confirm.", V_LATER)]
ADV_AFFIRM = [                                          # свой состязательный поиск шага 3d: чинено тем же определением
    "Оплата произведена, спасибо.", "Оплата успешно завершена.", "Платёж успешно обработан.",
    "Оплата засчитана, бронь за вами.", "Оплата зачтена в счёт аренды.", "Мы увидели вашу оплату, спасибо.",
    "Ваша оплата отображается в кассе.", "Оплата выполнена успешно.", "Оплата в системе есть.",
    "Спасибо за оплату!", "Благодарим за оплату аренды.", "Your payment was successful.",
    "Payment successful, thank you.", "Your payment came in this morning.", "Your payment has landed, thanks.",
    "Your payment has been made, thank you.", "Thank you for your payment!", "Thanks for the transfer.",
    "Paid, thank you!"]
ADV_NOT = [
    ("Оплата ещё не произведена.", V_NOT), ("Your payment was not successful.", V_NOT),
    ("Оплата обрабатывается банком до трёх дней.", None), ("Заранее спасибо за оплату.", None),
    ("Thank you in advance for your payment.", None), ("Спасибо за вопрос про оплату.", None),
    ("Спасибо за перевод договора.", None), ("Thank you for the payment details.", None),
    ("Thanks for the payment confirmation, our colleague will check it.", None),
    ("Спасибо за оплату залога.", V_DEP), ("Договор не отправили потому что оплата не получена.", V_NOT),
    ("The rent can be paid at pickup.", None), ("Оплата в системе появится завтра.", None)]


def _pay(text, facts):
    return T.PAY_WORDS in [w for w, _why in T.money_roles(text, facts)]


def _blocked(pairs, facts):
    """Не-утверждения, получившие причину оплаты, сумму «полученной оплаты» или НЕ то имя исхода."""
    return [(t, name, T.money_roles(t, facts), sorted(T.pay_claimed(t)), T._PAY_CLAIM.explain(t)) for t, name in pairs
            if _pay(t, facts) or T.pay_claimed(t) or (name is not None and _verdicts(t) != {name})]


def test_p3d_r1_lost_claims_caught_again():
    """R1: 38 состязательных утверждений проверяющего (ADVERSARIAL 26 + MORE_ADV 12) и свои того же строя — причина
    «оплата не подтверждена сверкой», как на cbe186f и 6f6e754. На f6ed7bd 25 из 38 терялись: модальное слово главной
    части («You should know that…», «Надо сказать что…») и предлог перед словом оплаты («7790 бат на оплату аренды
    получены», «Thank you for the payment received») снимали утверждение. Сумма возвращается в `pay_claimed`."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in RV_ADVERSARIAL + RV_MORE_ADV + R1_OWN if not _pay(t, facts)]
    assert not miss, miss
    assert T.pay_claimed("7790 бат на оплату аренды получены.") == {7790}
    assert T.pay_claimed("На оплату аренды получили от вас 7790 бат.") == {7790}


def test_p3d_r1_exclusions_stay_where_they_belong():
    """R1, отрицательный: долженствование ПРИ сказуемом, обязанность проверить или дождаться, цель («чтобы», «so
    that»), возможность, документ перед предлогом цели, правило «после оплаты …» — по-прежнему не утверждение, и исход
    назван своим именем. Ложные блокировки, снятые шагом 3c, не вернулись (OLD_NOT, три названные решением)."""
    facts = _facts_no_second_source()
    bad = _blocked(R1_OWN_NOT + OLD_NOT, facts)
    assert not bad, bad


def test_p3d_r2_union_of_all_known_lists_nothing_lost_nothing_blocked():
    """R2: контроль «ничего не потеряно» — из ОБЪЕДИНЕНИЯ всех известных списков, а не из списков строителя: реальный
    прогон (K15, K02), приёмка шага 3, списки шагов 3–3c, корпуса проверяющего 3b+3c (вшиты выше дословно), свои
    списки шага 3d. Каждое утверждение — с причиной; каждое не-утверждение — без причины и без сумм (мутант «у форм
    прочие предлоги не судятся» краснит именно здесь: «Получили ваш вопрос про перевод.»). На f6ed7bd — красный."""
    facts = _facts_no_second_source()
    claims = (AFFIRM + CLOSE_ACCEPT + CLOSE_OWN + OLD_AFFIRM + [RV_K15, RV_K02] + RV_OWN_AFFIRM + RV_ADVERSARIAL
              + RV_MORE_ADV + RV_OLD_CONTROL + RV_TWINS_OK + RV_RESIDUAL + R1_OWN + R3_NOUN_AFFIRM + R3_SUM_AFFIRM
              + ADV_AFFIRM)
    nots = (NOT_CLAIM + NOT_CLOSE + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT
            + [t for t, _name in OLD_NOT + SAME_3B + R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    assert len(set(claims)) >= 200 and len(set(nots)) >= 160, (len(set(claims)), len(set(nots)))
    lost = [t for t in claims if not _pay(t, facts)]
    assert not lost, lost
    blocked = [(t, sorted(T.pay_claimed(t))) for t in nots if _pay(t, facts) or T.pay_claimed(t)]
    assert not blocked, blocked


def test_p3d_reviewer_not_claims_no_reason():
    """Отрицательный (зелёный и на f6ed7bd): не-утверждения корпусов проверяющего — NAMED3, OWN_PLAIN, TWINS_NOT,
    OWN_NOT — ни одной причины оплаты и ни одной суммы «полученной оплаты»."""
    facts = _facts_no_second_source()
    bad = [(t, T.money_roles(t, facts), sorted(T.pay_claimed(t)))
           for t in RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT + RV_OWN_NOT if _pay(t, facts) or T.pay_claimed(t)]
    assert not bad, bad


def test_p3d_r3_noun_family_confirm_receipt():
    """R3 (i): подтверждение получения, поступления, зачисления оплаты / платежа / денег / средств отглагольным
    существительным (RU и EN) — утверждение; отрицание, будущее, вопрос, долженствование, просьба подтвердить,
    «подтверждение … придёт», получение документа, роль залога — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in R3_NOUN_AFFIRM + RV_RESIDUAL[:4] if not _pay(t, facts)]
    assert not miss, miss
    bad = _blocked(R3_NOUN_NOT, facts)
    assert not bad, bad


def test_p3d_r3_sum_family_receipt_with_amount():
    """R3 (ii): сказуемое получения с денежной суммой или словом суммы без слова «оплата» (RU и EN), «деньги у нас» —
    утверждение, сумма идёт в `pay_claimed` и сверяется с деньгами аренды; сумма как цена, итог, сдача; документ
    («запрос на 7790 бат»); слова клиента; получатель — клиент; роль залога; число без валюты не у сказуемого — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in R3_SUM_AFFIRM + RV_RESIDUAL[4:8] if not _pay(t, facts)]
    assert not miss, miss
    assert T.pay_claimed("Получили 7790 бат, спасибо.") == {7790}
    assert T.pay_claimed("Да, 7790 бат получили.") == {7790}
    assert T.pay_claimed("Получили 7790, спасибо.") == {7790}
    assert T.pay_claimed("Сумма получена.") == set()
    bad = _blocked(R3_SUM_NOT, facts)
    assert not bad, bad
    backed = _facts_backed()                             # с опорой: своя сумма — без причины, чужая — причина
    assert T.money_roles("Получили 7790 бат, спасибо.", backed) == []
    assert [w for w, _why in T.money_roles("Получили 8000 бат, спасибо.", backed)] == [T.PAY_WORDS]


def test_p3d_reviewer_residual_caught():
    """RESIDUAL_INFO проверяющего: 14 из 16 наблюдений — с причиной (8 фраз двух семейств R3 и 6, пойманных прежде).
    Две фразы без слова оплаты, денег или суммы (`RV_RESIDUAL_OPEN`) набор НЕ утверждает ни в одну сторону."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in RV_RESIDUAL if not _pay(t, facts)]
    assert not miss, miss
    assert len(RV_RESIDUAL) + len(RV_RESIDUAL_OPEN) == 16


def test_p3d_own_adversarial_search():
    """Свой состязательный поиск шага 3d (существенные находки чинены тем же определением): сказуемые-синонимы
    («произведена», «завершена», «обработан», «засчитана», «увидели», «отображается»; successful, came in, landed,
    has been made), благодарность за оплату, «в системе есть», краткое «Paid, …» — утверждение; их отрицания, «заранее
    спасибо», «спасибо за вопрос про оплату», «payment details», «обрабатывается», залог — нет."""
    facts = _facts_no_second_source()
    miss = [(t, T._PAY_CLAIM.explain(t)) for t in ADV_AFFIRM if not _pay(t, facts)]
    assert not miss, miss
    bad = _blocked(ADV_NOT, facts)
    assert not bad, bad


def test_p3d_verdict_named_on_every_road():
    """Храповик слепых читателей: у новых веток шага 3d исход — тоже всегда НЕПУСТОЕ имя, и `search` говорит
    «утверждение» ровно тогда, когда так назван хотя бы один исход; новое имя «получатель — клиент» названо."""
    every = (RV_OWN_AFFIRM + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_ADVERSARIAL + RV_RESIDUAL + RV_RESIDUAL_OPEN
             + RV_OLD_CONTROL + RV_MORE_ADV + RV_TWINS_OK + RV_TWINS_NOT + R1_OWN + R3_NOUN_AFFIRM + R3_SUM_AFFIRM
             + ADV_AFFIRM + [t for t, _name in R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    for text in every:
        got = T._PAY_CLAIM.explain(text)
        assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
        assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text)), (text, got)
    assert _verdicts("Вы получили 500 бат обратно.") == {V_THEIR}
    assert _verdicts("Получили 3000 бат залога.") == {V_DEP}


def test_p3d_control_backed_new_families_not_blocked():
    """КОНТРОЛЬ п.3d: новые семейства С опорой (касса + договор той же аренды, сумма 7790) причины не получают — ни на
    ремонте, ни до него."""
    facts = _facts_backed()
    assert T.pay_confirmed(facts) is True
    bad = [(t, T.money_roles(t, facts)) for t in R3_NOUN_AFFIRM + R3_SUM_AFFIRM + ADV_AFFIRM + RV_RESIDUAL[:8]
           if T.money_roles(t, facts)]
    assert not bad, bad


# ═══ п.3e: контекст вопроса об оплате, «долга нет», число без валюты (решение координатора после круга 3d) ═════

V_NOASK = "краткое подтверждение без вопроса клиента об оплате"
V_HOLD = "ответ сам говорит: оплата не видна или проверяется"
V_OTHER = "согласие относится к другому предмету"
V_NUM = "число — не известная денежная сумма сверки"
V_ITEM = "речь о другой услуге, а не об оплате аренды"
V_NOMONEY = "«закрыто» без оплаты, аренды, счёта или долга"
V_SAID = "слова клиента в пересказе"

# входящее клиента: об оплате · смешанное · о документе · о способе оплаты · о будущей оплате · оплата не прошла · без вопроса
QP_RU1 = "Я перевёл оплату за аренду, деньги пришли?"
QP_RU2 = "Оплатил аренду, проверьте, пожалуйста."
QP_RU3 = "Скинул вам 7790 на карту."
QP_RU4 = "Здравствуйте! Вы видите мой платёж?"
QP_EN1 = "I sent the payment for the rental, did you receive it?"
QP_EN2 = "I've paid, please confirm."
Q_MIX = "Отправил фото паспорта и оплатил аренду, получили?"
QD_RU = "Отправил вам фото паспорта, получили?"
QD_EN = "I sent you my passport photo, did you get it?"
Q_HOW = "Как можно оплатить аренду?"
Q_FUT = "Оплачу завтра утром, хорошо?"
Q_FAIL = "Оплата не прошла, попробую ещё раз позже."
Q_NONE = "Добрый день!"
Q_CHANGE = "Сдача с 8000 бат у курьера будет?"          # не об оплате, но клиент назвал сумму наличных (`cash_said`)

E_ASK_YES = [                                           # входящее клиента — ОБ ОПЛАТЕ (`pay_asked`)
    QP_RU1, QP_RU2, QP_RU3, QP_RU4, QP_EN1, QP_EN2, Q_MIX, "Я оплатил аренду, подтвердите",            # K15 real
    "Добрый день! Я оплатил аренду NMAX 90101 — 7790 бат. Подтвердите, пожалуйста, что оплата пришла.",   # K02 real
    C3_QUESTION, "Деньги дошли?", "Перевод прошёл?", "Аренда оплачена?", "Заплатила вчера вечером.",
    "Внёс предоплату, посмотрите.", "Отправил чек об оплате.", "Перевёл 3000.", "Деньги ещё не пришли?",
    "Оплата прошла, можно забирать байк?", "Вам поступил мой перевод?", "Проверьте, пожалуйста, поступление оплаты.",
    "Я же вчера оплатил, разве не пришло?", "Оплату отправил ещё утром", "Сделал перевод на 7790 бат",
    "Payment sent, please check.", "Hi, I just transferred the rent. Has it arrived?", "Did you get my transfer?",
    "Has my payment come through?", "I paid yesterday.", "Money sent!", "Can you confirm my payment?",
    "Just made the payment.", "Закинул вам на карту, гляньте.", "Деньги списались, а у вас видно?",
    "Paid, please check."]
E_ASK_NO = [                                            # не об оплате: документ, способ, цена, будущая, несостоявшаяся
    Q_NONE, "", QD_RU, QD_EN, Q_HOW, Q_FUT, Q_FAIL, "Можно оплатить картой?", "Сколько стоит аренда на 10 дней?",
    "Когда нужно внести оплату?", "Я ещё не оплатил.", "Хочу оплатить наличными при получении.",
    "Оплата при получении байка?", "Куда отправить деньги?", "Пришлите, пожалуйста, договор.",
    "Подскажите, до какого числа у меня аренда?", "Сделал перевод договора на английский.",
    "Отправил вам номер 0812345678.", "Скинул геолокацию отеля.", "Сделал скриншот брони.", "Получили мои документы?",
    "Во сколько привезёте байк?", "How can I pay?", "Can I pay by card?", "I will pay tomorrow.",
    "Is it paid at pickup?", "How can I get the payment link?", "Can I check payment options?",
    "My payment failed, I will try again.", "I haven't paid yet."]

# семейство 1 — краткое получение или подтверждение БЕЗ предмета в ответ на входящее об оплате: (ответ, входящее)
E1_RV_OPEN = [("Да, всё пришло.", QP_RU1), ("We got it, thanks!", QP_EN1)]    # RESIDUAL_INFO проверяющего: 15-я и 16-я
E1_AFFIRM = [
    ("Да, получили.", QP_RU1), ("Получили, спасибо.", QP_RU2), ("Всё в порядке, получили.", QP_RU1),   # решение — дословно
    ("Да, всё получили, спасибо большое!", QP_RU2), ("Пришло, спасибо!", QP_RU1), ("Да, дошло.", QP_RU3),
    ("Да, поступило.", QP_RU1), ("Подтверждаю.", QP_RU2), ("Да, подтверждаю, получили.", QP_RU2),
    ("Да, вижу, спасибо.", QP_RU4), ("Да, всё в порядке.", QP_RU1), ("Всё в порядке, спасибо!", QP_RU2),
    ("Да, спасибо!", QP_RU1), ("Да.", QP_RU1), ("Получено.", QP_RU2), ("Да, уже получили, ждём вас завтра.", QP_RU1),
    ("Здравствуйте! Да, получили.", QP_RU1), ("Да, пришла.", QP_RU1), ("Да, получена.", QP_RU2),
    ("Получили, не волнуйтесь.", QP_RU1), ("Подтверждаем получение.", QP_RU2), ("Да, на карту пришло.", QP_RU3),
    ("Получили в полном объёме.", QP_RU2), ("Да, есть.", QP_RU1), ("Да, упали.", QP_RU3),
    ("Да, получили её, спасибо.", QP_RU1), ("Да, получили 👍", QP_RU3), ("Да 👍", QP_RU3),
    ("Да, оплата есть.", QP_RU1),                                          # «есть» без кассы — при входящем об оплате
    ("Да, оплата на месте, спасибо.", QP_RU1), ("Деньги на месте.", QP_RU3),   # замечание (д) круга 3d
    ("Да, получили. Договор проверим и пришлём сегодня.", QP_RU1),         # проверяют договор, а не оплату
    ("Получили, но не полностью.", QP_RU1),                                # как «Оплата получена не полностью.»
    ("Да, всё дошло и зачислено.", QP_RU3),
    ("Да, всё пришло. Уточню у коллеги время доставки.", QP_RU3),
    ("Да, получили.", Q_MIX),                                              # смешанное входящее — утверждение
    ("Yes, we did.", QP_EN1), ("Yes, we received them.", QP_EN1),
    ("Yes, received.", QP_EN1), ("All good, got it.", QP_EN1),            # решение — дословно
    ("Received, thank you!", QP_EN2), ("Yes, we have received it.", QP_EN1), ("Yes, it came through.", QP_EN1),
    ("Confirmed, thanks.", QP_EN2), ("Yes, all good.", QP_EN1), ("Yes, thank you!", QP_EN2), ("We can confirm.", QP_EN2),
    ("Yes, it arrived.", QP_EN1), ("Yes, I can confirm we received it.", QP_EN2), ("Yes, got it this morning.", QP_EN1)]
# то же входящее об оплате, но ответ — НЕ подтверждение: (ответ, входящее, имя исхода краткой клаузы | None — клаузы нет)
E1_NOT = [
    ("Нет, пока не получили.", QP_RU1, None), ("Пока не видим, проверим и сообщим.", QP_RU1, None),
    ("Получили, проверим и сообщим.", QP_RU2, V_HOLD),                     # получено СООБЩЕНИЕ, оплата — проверим
    ("Получили, договор проверим завтра.", QP_RU2, V_LATER),               # проверка в том же предложении
    ("Получили, спасибо. Оплату проверит коллега и подтвердит.", QP_RU2, V_HOLD),
    ("Получили, спасибо. Оплата пока не поступила.", QP_RU2, V_HOLD),
    ("Спасибо, получили. Проверим и ответим.", QP_RU2, V_HOLD),            # проверка без иного предмета — об оплате
    ("Получили. Чек проверим и подтвердим.", QP_RU2, V_HOLD), ("Получили. В кассе пока не видим.", QP_RU1, V_HOLD),
    ("Получили, но в кассе пока не видим.", QP_RU1, V_HOLD),
    ("Получили, верно?", QP_RU1, V_ASKED), ("Получили?", QP_RU1, V_ASKED),
    ("Сообщение получили, оплату пока не вижу.", QP_RU1, None), ("Получили ваш чек, передам коллеге.", QP_RU2, None),
    ("Скриншот получили, спасибо.", QP_RU3, None), ("Вы получили договор?", QP_RU1, None),
    ("Спасибо за информацию, получили.", QP_RU2, V_OTHER),                 # предмет назван раньше в том же предложении
    ("Вижу, что вы отправили чек, передам коллеге.", QP_RU2, None),
    ("Да, шлем дадим.", QP_RU1, V_OTHER), ("Да, конечно, договор пришлём сегодня.", QP_RU2, V_OTHER),
    ("Как только придёт, сообщим.", QP_RU1, None), ("Если получили, напишите.", QP_RU1, None),
    ("Здравствуйте! Коллега сверит поступления и вам ответит.", QP_RU2, None),
    ("Got it, I'll check with my colleague.", QP_EN1, V_HOLD), ("We'll confirm once received.", QP_EN2, None),
    ("Not received yet.", QP_EN1, None), ("Did you get it?", QP_EN1, None),
    ("Yes, we can deliver the bike tomorrow.", QP_EN2, V_OTHER), ("Thanks, we got your passport photo.", QP_EN1, None),
    ("Thank you for your payment request, received.", QP_EN2, V_OTHER),
    ("Оплата картой тоже есть.", QP_RU1, V_EXIST), ("Есть оплата картой и наличными.", QP_RU2, V_EXIST),   # способ оплаты
    ("Оплата есть, но в кассе её пока не вижу.", QP_RU1, V_EXIST),          # «есть» при «не вижу» — не утверждение
    ("Получили. Если оплата прошла, договор пришлём сегодня.", QP_RU2, V_HOLD),   # условие об оплате в самом ответе
    ("Всё закрыто, спасибо. Оплату проверит коллега и подтвердит.", QP_RU2, V_HOLD)]
# входящее НЕ об оплате — те же краткие ответы причины не получают: (ответ, входящее)
E1_NOASK = [
    ("Да, получили.", QD_RU), ("Получили, спасибо.", Q_NONE), ("We got it, thanks!", QD_EN), ("Да, всё пришло.", QD_RU),
    ("Да, всё в порядке.", Q_HOW), ("Да, хорошо.", Q_FUT), ("Да.", Q_NONE), ("Да, получили.", Q_FAIL),
    ("Yes, received.", QD_EN), ("Всё в порядке, получили.", Q_NONE), ("Подтверждаю.", Q_NONE), ("Да, спасибо!", Q_HOW),
    ("Здравствуйте! Да, получили, спасибо.", QD_RU), ("Да, есть.", QD_RU), ("Оплата на месте, спасибо.", Q_NONE),
    ("Yes, we did.", QD_EN), ("Да, получили 👍", QD_RU)]

# семейство 2 — «долга нет» (вопрос клиента не нужен)
E2_AFFIRM = [
    "Долга по аренде нет, всё закрыто.",                                   # остаток круга 3d — дословно
    "За аренду и доставку вы ничего не должны.",                           # другая услуга ПОСЛЕ аренды — об аренде тоже
    "Задолженности по аренде нет.", "Долга нет.", "У вас нет задолженности.", "Вы ничего не должны.",
    "Вы нам ничего не должны, спасибо.", "Больше ничего не должны.", "Долг погашен.",
    "Задолженность по аренде погашена.", "Всё погашено, спасибо.", "Счёт закрыт.", "По аренде всё закрыто.",
    "Аренда полностью закрыта.", "Задолженность отсутствует.", "Долгов за вами не числится.",
    "За аренду вы ничего не должны.", "Баланс нулевой.", "Остаток к оплате — 0 бат.", "Доплачивать ничего не нужно.",
    "Больше ничего платить не нужно.", "Вы уже всё оплатили, спасибо.", "Да, вы полностью рассчитались.",
    "Вы оплатили аренду полностью.", "С оплатой проблем нет.", "По оплате вопросов нет.",
    "You've paid, thank you.", "You have paid for the whole rental.", "No issues with your payment.",
    "There is no balance due.", "No outstanding balance.", "Nothing owed, all settled.", "You don't owe anything.",
    "You owe nothing.", "All settled, thank you.", "Your balance is zero.", "Nothing is due.",
    "Everything is settled.", "No debt on your rental.", "The bill is settled.", "Nothing left to pay.",
    "You're all paid up.", "Zero balance on your rental."]
E2_NOT = [
    ("Долга нет?", V_ASKED), ("Долг ещё есть.", None), ("Долг пока не погашен.", V_NOT),
    ("Если долга нет, пришлём договор.", V_LATER), ("Долга не будет, если оплатите до пятницы.", None),
    ("Заявка закрыта.", None), ("Обращение закрыто, спасибо.", None), ("Вопрос закрыт.", None),
    ("Вопрос решён, всё закрыто.", V_NOMONEY), ("Офис закрыт до 9:00.", None), ("Бронь закрыта.", None),
    ("За доставку вы ничего не должны.", V_ITEM), ("За отмену брони вы ничего не должны.", V_ITEM),
    ("Вы не должны ничего подписывать.", None), ("Долг должен быть погашен до выдачи байка.", V_MUST),
    ("Когда долг будет погашен, сообщим.", V_LATER), ("Вопросов по долгу нет.", V_PREP), ("Долга по залогу нет.", V_DEP),
    ("Сейчас вы ничего не должны — оплата при получении байка.", V_LATER), ("Мы вам ничего не должны.", V_OTHER),
    ("Долг по аренде — 500 бат.", None), ("Остаток к оплате 500 бат.", None),
    ("Is there no balance due?", V_ASKED), ("There is still a balance due.", None),
    ("If nothing is owed, we will send the contract.", V_LATER), ("You owe nothing for the helmet.", V_ITEM),
    ("Nothing is due until pickup.", V_LATER), ("Glad you're all settled in.", None), ("The ticket is closed.", None),
    ("Вы написали, что оплатили аренду.", None), ("По вашим словам, вы оплатили вчера.", V_SAID),    # пересказ клиента
    ("Если вы оплатили, пришлите чек.", V_LATER), ("Вы уже оплатили?", V_ASKED), ("Вы ещё не оплатили аренду.", None),
    ("Вы оплатили только залог.", V_DEP), ("Вы оплатили, но в кассе оплату пока не вижу.", V_HOLD),
    ("Once you have paid, we will confirm.", V_LATER), ("Have you paid?", V_ASKED),
    ("You paid for the helmet only.", V_ITEM), ("За шлем платить ничего не нужно.", None),
    ("Оплата не требуется, это бесплатно.", None), ("Вы оплатили бы меньше при аренде на месяц.", None),
    ("Долга нет, если оплатите сегодня.", V_LATER), ("Доплата не нужна, если вернёте байк вовремя.", V_LATER)]

# семейство 3 — число БЕЗ валюты при сказуемом получения; итог аренды 7790 — известная денежная сумма сверки
E3_AFFIRM = [
    "Да, 7790 получили.", "7790 пришли, спасибо.",                         # остаток 3d и решение — дословно
    "7790 получены.", "Получили от вас вчера 7790.", "7790 уже у нас.", "В кассе вижу 7790.", "Ваши 7790 поступили.",
    "7 790 получили, спасибо.", "Получили 7790 за аренду.", "7790 от вас получили.", "7790 на карту пришли.",
    "За аренду 7790 получили, спасибо.", "Зачислили 7790.", "7.790 получили, спасибо.",
    "Yes, 7790 received.", "We received your 7790 yesterday.", "7790 has been received.", "We have your 7790.",
    "Got the 7790 this morning, thanks.", "7790 came through.", "7790 landed in our account.", "THB 7790 received.",
    "Thank you 7790 received."]                                            # благодарность — не получатель-клиент
E3_ASKED = [("Да, 3000 получили.", QP_RU3), ("Yes, 3000 received.", QP_EN1),   # число не из фактов — входящее об оплате
            ("Получили 4000, остальное ждём.", QP_RU2),
            ("Received THB 5000 from you.", Q_NONE)]                       # …либо код валюты ПЕРЕД числом
E3_NOT = [                                              # (ответ, входящее, имя исхода | None)
    ("Байк 90101 получили, спасибо.", Q_NONE, V_NUM), ("NMAX 90101 получили.", Q_NONE, V_NUM),
    ("Заказ 12345 получили.", Q_NONE, V_NUM), ("Байк № 7790 получили.", Q_NONE, V_NUM),
    ("Договор 7790 получили.", Q_NONE, V_NUM), ("Получили 7790?", Q_NONE, V_ASKED),
    ("7790 пока не получили.", Q_NONE, V_NOT), ("Если 7790 пришли, напишите.", Q_NONE, V_LATER),
    ("7790 получим завтра.", Q_NONE, None), ("Счёт на 7790 получили.", Q_NONE, V_PREP),
    ("За 7790 получили бы NMAX на 10 дней.", Q_NONE, None), ("За 7790 получили скидку.", Q_NONE, V_PREP),
    ("5000 получили.", Q_NONE, V_NUM),
    ("Номер +66 81 234 5678 получили.", Q_NONE, V_NUM), ("Получили 125 фото, спасибо.", Q_NONE, None),
    ("Bike 90101 received.", Q_NONE, V_NUM), ("Order 12345 received, thanks.", Q_NONE, V_NUM),
    ("We received 90101 yesterday.", Q_NONE, V_NUM), ("Вы 7790 получили?", Q_NONE, V_ASKED),
    ("Байк 90101 получили, спасибо.", QP_RU1, V_NUM),    # номер байка на месте номера — и при входящем об оплате
    ("Да, 3000 получили.", QD_RU, V_NUM),                # число не из фактов, входящее не об оплате
    ("Вижу 7790 бат в вашем чеке, передам коллеге.", Q_NONE, V_OTHER),     # сумма видна в БУМАГЕ клиента
    ("Вижу в договоре сумму 7790 бат.", Q_NONE, None), ("Не вижу 7790 бат в кассе.", Q_NONE, V_NOT),
    ("Счёт за аренду 7790 бат получили.", Q_NONE, V_PREP), ("PCX 5580 received.", Q_NONE, V_NUM),
    ("7790 получили бы только при оплате за месяц.", Q_NONE, None),
    ("NMAX 90101 получили.", QP_RU1, V_NUM),             # число за названием модели — номер и при входящем об оплате
    ("Номер +66 81 234 5678 получили.", QP_RU1, V_NUM),  # часть телефона — тоже
    ("Да, 3000 получили. Оплату проверит коллега и подтвердит.", QP_RU3, V_HOLD),   # ответ сам говорит «проверяется»
    ("Вы получили 7790 обратно на карту.", Q_NONE, V_THEIR), ("Вы 7790 получили обратно вчера.", Q_NONE, V_THEIR),
    ("Вы 210 бат получили обратно.", Q_NONE, V_THEIR)]   # получатель — клиент: и когда сумма стоит ПЕРЕД сказуемым
# свой свежий поиск шага 3e — существенные находки, чиненные тем же определением (вне трёх списков выше)
E_FRESH_AFFIRM = [
    ("Спасибо, получили!", QP_RU3), ("Здравствуйте, получили, спасибо!", QP_RU2), ("Да, конечно, получили.", QP_RU3),
    ("Да, всё ок.", QP_RU1), ("Всё на месте, спасибо.", QP_RU2), ("Да, конечно.", QP_RU3), ("Да!", QP_RU3),
    ("Received with thanks.", QP_EN2), ("Yep, we've got it.", QP_EN2), ("Got it — thank you!", QP_EN1),
    ("Everything is fine, see you tomorrow.", QP_EN1),
    ("По оплате долгов нет.", Q_NONE), ("Расчёт закрыт, спасибо.", Q_NONE), ("К оплате 0.", Q_NONE),
    ("Доплата не требуется, всё в расчёте.", Q_NONE), ("Your account is settled.", Q_NONE),
    ("There's nothing outstanding.", Q_NONE), ("Your balance due is 0.", Q_NONE),
    ("В кассе вижу 7790 бат по вашей брони.", Q_NONE), ("Вижу ваши 7790 бат, спасибо.", Q_NONE),     # «вижу» + сумма
    ("7790 бат в кассе вижу.", Q_NONE), ("We can see your 7790 baht in our records.", Q_NONE),
    ("За аренду 7790 бат получили.", Q_NONE), ("Да, все 7790 пришли.", QP_RU3),
    ("Да, всё поступило, не переживайте.", QP_RU1)]      # слова успокоения — не отрицание получения


def _results_rent_only():
    """Факты «только аренда»: строка листа «клиенты» (итог 7790), кассы и договора нет."""
    return [T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)]


def _results_no_second():
    """Факты «касса без второго источника»: аренда + строка кассы той же аренды; договора и суммы в переписке нет."""
    return _results_rent_only() + [T.cash_result(tx([tx_item()]), at=T0)]


def _results_backed():
    rent = _results_rent_only()[0]
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    return [rent, T.cash_result(tx([tx_item()]), at=T0), con]


def _judged(text, question, results):
    """Причины ПОЛНОГО судьи так, как его зовёт адаптер: переданные наличные и признак «входящее об оплате» — из
    входящего клиента. На дереве до шага 3e признака нет — судья зовётся прежней подписью (и краткий ответ не судит)."""
    kw = {"handed": T.cash_said(question)}
    if hasattr(T, "pay_asked"):
        kw["asked"] = T.pay_asked(question)
    return T.judge(text, None, [dict(r) for r in results], T.Journal("5678"), **kw)[0]


def _missed(pairs):
    """Утверждения, НЕ получившие причину оплаты хотя бы при одном из двух наборов фактов без достаточного основания."""
    return [(t, q, [T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second())])
            for t, q in pairs
            if not all(T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second()))]


def _ctx_of(question):
    """Контекст сверки определения для входящего: (признак «об оплате», известные денежные суммы фактов и клиента)."""
    return T.pay_asked(question), T.pay_sums(T.accepted(_results_no_second()), T.cash_said(question))


def _hit(triples):
    """Не-утверждения, получившие причину оплаты, сумму «полученной оплаты» или НЕ то имя исхода краткой клаузы."""
    out = []
    for t, q, name in triples:
        asked, sums = _ctx_of(q)
        names = {v for _match, v in T._PAY_CLAIM.explain(t, asked, sums)}
        flags = [T.PAY_WORDS in _judged(t, q, r) for r in (_results_rent_only(), _results_no_second())]
        if any(flags) or T.pay_claimed(t, asked, sums) or (name is not None and name not in names) or V_CLAIM in names:
            out.append((t, q, flags, sorted(T.pay_claimed(t, asked, sums)), sorted(names)))
    return out


def test_p3e_incoming_about_payment_sign():
    """п.1: признак «входящее клиента — об оплате» — одно чистое определение: клиент говорит о СОСТОЯВШЕЙСЯ оплате
    («оплатил», «перевёл 3000», «отправил чек», «I paid») или спрашивает, получена ли она («деньги дошли?», «did you get
    my transfer?»); смешанное входящее — да. Вопрос о способе, цене, будущей или несостоявшейся оплате, о документе,
    пустое входящее — нет."""
    wrong = [(t, True) for t in E_ASK_YES if T.pay_asked(t) is not True]
    wrong += [(t, False) for t in E_ASK_NO if T.pay_asked(t) is not False]
    assert not wrong, wrong


def test_p3e_bare_confirmation_on_payment_question_flagged():
    """п.1 (остаток (а) круга 3d): на входящее об оплате краткое утвердительное получение или подтверждение БЕЗ
    предмета («Да, всё пришло.», «We got it, thanks!» — две открытые фразы RESIDUAL_INFO проверяющего; «Да, получили.»,
    «Получили, спасибо.», «Всё в порядке, получили.», «Yes, received.», «All good, got it.» — решение дословно) судится
    полным судьёй как утверждение оплаты: при фактах «только аренда» и «касса без второго источника» — причина «оплата
    не подтверждена сверкой». Смешанное входящее (оплата и документ) — утверждение."""
    miss = _missed(E1_RV_OPEN + E1_AFFIRM)
    assert not miss, miss
    assert len(RV_RESIDUAL) + len(E1_RV_OPEN) == 16                       # RESIDUAL_INFO проверяющего — все 16


def test_p3e_payment_question_but_not_confirmation_not_blocked():
    """п.1, отрицательный: то же входящее об оплате, но ответ — не подтверждение: отрицание, обещание проверки
    («Получили, проверим и сообщим»), вопрос, условие, названный предмет («получили ваш чек»), ответ сам говорит, что
    оплата не видна или проверяется, «да» о другом предмете — ни причины, ни сумм; у краткой клаузы исход назван."""
    bad = _hit(E1_NOT)
    assert not bad, bad


def test_p3e_no_payment_question_bare_reply_no_reason():
    """п.1, отрицательный с близнецом: входящее НЕ об оплате (вопрос о документе, о способе или будущей оплате, оплата
    не прошла, вопроса нет) — краткий ответ причины не получает и назван `PC_NOASK`; ТОТ ЖЕ ответ на входящее об оплате
    — утверждение."""
    bad = _hit([(t, q, V_NOASK) for t, q in E1_NOASK])
    assert not bad, bad
    twins = [(t, QP_EN1 if re.match(r"[A-Za-z]", t) else QP_RU1) for t, _q in E1_NOASK]
    miss = _missed(twins)
    assert not miss, miss


def test_p3e_adapter_passes_sign_to_run_and_judge():
    """п.1, адаптер: признак считает `T.pay_asked(info["question"])` тем же местом, что `cash_said`, и передаёт в
    `T.run` (итог и журнал сверки его несут) и в `T.judge`: черновик «Да, получили, спасибо!» на «…деньги пришли?»
    получает причину кода; на вопрос о фото паспорта — нет. Запрос модели от признака не зависит."""
    seen = {}
    for name, question in (("pay", QP_RU1), ("doc", QD_RU)):
        s = Script({"tool": "rental", "args": {}}, {"tool": "cash", "args": {"booking_id": BK}},
                   final("Да, получили, спасибо!"))
        a = adapter(s, [tx_item()], question=question)
        out = a.draft(NUMBER, 5)
        seen[name] = (out["handoff"], a.last["tools"].get("asked"), getattr(a.last["tools"]["journal"], "asked", None),
                      list(s.seen))
    assert T.PAY_WORDS in seen["pay"][0] and seen["pay"][1] is True and seen["pay"][2] is True, seen["pay"][:3]
    assert T.PAY_WORDS not in seen["doc"][0] and seen["doc"][1] is False and seen["doc"][2] is False, seen["doc"][:3]
    assert seen["pay"][3] == seen["doc"][3], "запрос модели изменился от признака"


def test_p3e_run_records_sign_request_unchanged():
    """п.1: `T.run(..., asked=…)` только ЗАПИСЫВАЕТ признак (итог `asked`, журнал) — запросы модели те же байт-в-байт;
    `T.judge(..., asked=…)` кладёт его в журнал, по нему и судит."""
    outs = {}
    for flag in (True, False):
        s = Script({"tool": "rental", "args": {}}, final("Да, получили."))
        out = T.run(s, "S", "U", {"rental": rental_door()}, number=NUMBER, clock=Clock(), asked=flag)
        words, _fig = T.judge("Да, получили.", None, out["results"], out["journal"], asked=flag)
        outs[flag] = (out["asked"], out["journal"].asked, list(s.seen), T.PAY_WORDS in words)
    assert outs[True][:2] == (True, True) and outs[False][:2] == (False, False), (outs[True][:2], outs[False][:2])
    assert outs[True][2] == outs[False][2], "запрос модели изменился от признака"
    assert outs[True][3] is True and outs[False][3] is False, (outs[True][3], outs[False][3])


def test_p3e_debt_family_flagged():
    """п.2 (остаток (б)): «долга / задолженности (по аренде) нет», «ничего не должны», «долг погашен», «всё погашено»,
    «счёт закрыт», «аренда закрыта», «баланс нулевой», «доплачивать ничего не нужно»; англ. «no balance due», «nothing
    owed», «you don't owe anything», «all settled», «balance is zero» — утверждение оплаты на тех же основаниях;
    собственное «нет / не / no» семейства отрицанием не считается. «Всё закрыто» без слова денег — при входящем об оплате."""
    miss = _missed([(t, Q_NONE) for t in E2_AFFIRM] + [("Да, всё закрыто.", QP_RU1)])
    assert not miss, miss
    assert len([t for t in E2_AFFIRM if re.match(r"[A-Za-z]", t)]) >= 10 and len(E2_AFFIRM) >= 30
    assert T.pay_claimed("Остаток к оплате — 0 бат.") == set()             # ноль — не сумма полученной оплаты


def test_p3e_debt_not_claims_not_blocked():
    """п.2, отрицательный: вопрос, «долг ещё есть», «долг не погашен», будущее и условие, долженствование; «закрыто» про
    заявку, обращение, вопрос, офис, бронь; другая услуга («за доставку вы ничего не должны»); правило о сроке оплаты
    («сейчас вы ничего не должны — оплата при получении»); «мы вам ничего не должны»; сумма долга; залог — ни причины,
    ни сумм, исход назван."""
    bad = _hit([(t, Q_NONE, name) for t, name in E2_NOT])
    assert not bad, bad


def test_p3e_bare_number_known_money_sum_flagged():
    """п.3 (остаток (в)): число БЕЗ валюты при сказуемом получения, в том числе не вплотную («Да, 7790 получили.»,
    «7790 пришли, спасибо.», «В кассе вижу 7790.», «Yes, 7790 received.») — утверждение, когда число равно известной
    денежной сумме сверки (итог аренды 7790); число не из фактов — когда входящее клиента об оплате. Сумма идёт в
    `pay_claimed`; с опорой своя сумма причины не получает, чужая — получает."""
    miss = _missed([(t, Q_NONE) for t in E3_AFFIRM] + E3_ASKED)
    assert not miss, miss
    assert len([t for t in E3_AFFIRM if re.search(r"[A-Za-z]{3}", t)]) >= 7 and len(E3_AFFIRM) >= 20
    sums = T.pay_sums(T.accepted(_results_no_second()))
    assert sums == {7790}, sums
    assert T.pay_claimed("Да, 7790 получили.", False, sums) == {7790}
    assert T.pay_claimed("Да, 7790 получили.") == set()                    # без фактов число деньгами не названо
    backed = _results_backed()
    assert T.PAY_WORDS not in _judged("Да, 7790 получили.", Q_NONE, backed)
    assert T.PAY_WORDS in _judged("Да, 8000 получили.", QP_RU1, backed)    # чужая сумма при подтверждённой оплате
    # известные суммы сверки — и строка кассы, и названное в переписке, и названное клиентом (сдача с 8000 бат)
    rent = _results_rent_only()
    cash3 = rent + [T.cash_result(tx([tx_item(amount=3000)]), at=T0)]
    hist3 = rent + [T.history_result([{"who": "клиент", "text": "Переведу вам 3000 бат сегодня вечером."}], at=T0)]
    assert T.pay_sums(T.accepted(cash3)) == {7790, 3000} and T.pay_sums(T.accepted(hist3)) == {7790, 3000}
    for res in (cash3, hist3):
        assert T.PAY_WORDS in _judged("Да, 3000 получили.", Q_NONE, res), res
    assert T.PAY_WORDS not in _judged("Да, 3000 получили.", Q_NONE, rent)
    assert T.pay_asked(Q_CHANGE) is False and T.cash_said(Q_CHANGE) == [8000]
    assert T.PAY_WORDS in _judged("Да, 8000 получили.", Q_CHANGE, rent)
    assert T.PAY_WORDS not in _judged("Да, 8000 получили.", Q_NONE, rent)


def test_p3e_bare_number_not_money_not_blocked():
    """п.3, отрицательный: номер байка рядом со сказуемым получения («Байк 90101 получили», «NMAX 90101 получили» — и
    при входящем об оплате), номер заказа или договора, часть телефона, число не из фактов без вопроса об оплате,
    вопрос, отрицание, условие, будущее, документ («счёт на 7790 получили»), сумма в БУМАГЕ клиента («вижу 7790 бат в
    вашем чеке») — ни причины, ни сумм, исход назван."""
    bad = _hit(E3_NOT)
    assert not bad, bad
    assert T.pay_claimed("Вы 7790 получили?", False, {7790}) == set()      # вопрос сумм полученной оплаты не называет
    assert T.pay_claimed("Получили 7790?") == set()
    # «ответ сам говорит: оплата проверяется» судится по ВСЕМУ тексту, а не по одному предложению
    assert T.pay_claimed("Да, 3000 получили. Оплату проверит коллега.", True, {7790}) == set()
    assert T.pay_claimed("Да, 3000 получили.", True, {7790}) == {3000}


def test_p3e_own_fresh_search_fixed():
    """Свой свежий поиск шага 3e (существенные находки чинены тем же определением): краткие ответы с приветствием,
    «конечно», «всё ок / на месте», «Да!»; «по оплате долгов нет», «расчёт закрыт», «к оплате 0», «account is
    settled»; «в кассе вижу 7790 бат», «за аренду 7790 бат получили» — утверждение."""
    miss = _missed(E_FRESH_AFFIRM)
    assert not miss, miss


def test_p3e_old_not_claims_stay_clean_under_payment_question():
    """Отрицательный: ни одно не-утверждение прежних списков (шаги 3–3d и корпуса проверяющего) не получает причины и
    при входящем об оплате — признак судит только краткую клаузу без предмета."""
    facts = _facts_no_second_source()
    nots = (NOT_CLAIM + NOT_CLOSE + RV_OWN_NOT + RV_NAMED3 + RV_OWN_PLAIN + RV_TWINS_NOT
            + [t for t, _name in OLD_NOT + SAME_3B + R1_OWN_NOT + R3_NOUN_NOT + R3_SUM_NOT + ADV_NOT])
    bad = [(t, T._PAY_CLAIM.explain(t, True)) for t in nots
           if T.PAY_WORDS in [w for w, _why in T.money_roles(t, facts, asked=True)]]
    assert not bad, bad


def test_p3e_verdict_named_on_every_road():
    """Храповик слепых читателей: у четвёртого прохода исход — тоже всегда НЕПУСТОЕ имя, и `search` говорит
    «утверждение» ровно тогда, когда так назван хотя бы один исход — с контекстом сверки и без него; новые имена названы."""
    rows = [(t, q) for t, q in E1_RV_OPEN + E1_AFFIRM + E1_NOASK + E3_ASKED + E_FRESH_AFFIRM]
    rows += [(t, q) for t, q, _name in E1_NOT + E3_NOT] + [(t, Q_NONE) for t in E2_AFFIRM + E3_AFFIRM]
    rows += [(t, Q_NONE) for t, _name in E2_NOT]
    for text, question in rows:
        for asked, sums in (_ctx_of(question), (False, ())):
            got = T._PAY_CLAIM.explain(text, asked, sums)
            assert all(isinstance(v, str) and v.strip() for _match, v in got), (text, got)
            assert (V_CLAIM in [v for _match, v in got]) == bool(T._PAY_CLAIM.search(text, asked, sums)), (text, got)
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.")} == {V_NOASK}
    assert {v for _m, v in T._PAY_CLAIM.explain("Да, получили.", True)} == {V_OTHER, V_CLAIM}   # «да» — к «получили»
    assert {v for _m, v in T._PAY_CLAIM.explain("Вопрос решён, всё закрыто.")} == {V_NOMONEY}
    assert {v for _m, v in T._PAY_CLAIM.explain("За доставку вы ничего не должны.")} == {V_ITEM}
    assert {v for _m, v in T._PAY_CLAIM.explain("Байк 90101 получили, спасибо.", True, {7790})} == {V_NUM}
    assert V_HOLD in {v for _m, v in T._PAY_CLAIM.explain("Получили, спасибо. Оплату проверит коллега.", True)}
    assert {v for _m, v in T._PAY_CLAIM.explain("По вашим словам, вы оплатили вчера.")} == {V_SAID}


def test_p3e_control_backed_new_families_not_blocked():
    """КОНТРОЛЬ п.3e: новые семейства С опорой (касса + договор той же аренды, сумма 7790) причины не получают — ни на
    ремонте, ни до него."""
    backed = _results_backed()
    assert T.pay_confirmed(T.accepted(backed)) is True
    rows = E1_RV_OPEN + E1_AFFIRM + [(t, Q_NONE) for t in E2_AFFIRM + E3_AFFIRM] + E_FRESH_AFFIRM
    bad = [(t, q, _judged(t, q, backed)) for t, q in rows if T.PAY_WORDS in _judged(t, q, backed)]
    assert not bad, bad


# ═══ D3 приёмки шага 3: проверки, которые убивают мутанты m3r и m3v ═══════════════════════════════════════════

class SelfContradicting(Registry):
    """Дверь противоречит сама себе: со сроком аренды — «не найден», без срока — тот же договор В сроке."""

    def __call__(self, **kw):
        out = super().__call__(**kw)
        if kw.get("date_from"):
            out = dict(out, outcome="none", pick=None, items=[])
        return out


def test_d3_m3r_door_contradicts_itself_unknown():
    """D3 (мутант m3r_contradiction_is_fact): в сроке «нет», без срока — договор В сроке → НЕИЗВЕСТНО (не FACT), договор
    и PDF не приняты, вложения нет."""
    reg = SelfContradicting([DOC1])
    out = run(Script({"tool": "contract", "args": {}}, {"tool": "contract_pdf", "args": {"file_id": "PDF-0001"}},
                     final("Ок")), reg)
    assert len(reg.calls) == 2 and reg.calls[0].get("date_from") == TERM[0] and "date_from" not in reg.calls[1], \
        reg.calls
    res = [r for r in out["results"] if r["tool"] == "contract"][0]
    assert res["outcome"] == T.UNKNOWN and "противоречат" in res["reason"], (res["outcome"], res["reason"])
    assert not [f for f in T.accepted(out["results"]) if f["kind"] in ("contract", "pdf")], T.accepted(out["results"])
    assert X.attach_of({"state": T.DONE, "results": out["results"]})[0] is None


def test_d3_m3v_underpaid_cash_no_change():
    """D3 (мутант m3v_underpaid_off): касса этой аренды записала МЕНЬШЕ итога (7000 из 7790), клиент назвал 8000 —
    сдачи кодом нет («оплачена на 7000 из 7790»), ни в расчёте, ни в блоке запроса модели."""
    res = [T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0),
           T.cash_result(tx([tx_item(amount=7000, description="Nmax 90101 +7000 аренда K3-BK-001")]), at=T0)]
    ch = T.change_of(T.accepted(res), [8000])
    assert ch["state"] == T.CHANGE_NO and "оплачена на 7000 из 7790" in ch["why"], ch
    blk = T.change_block(res, [8000])
    assert "сдача НЕ посчитана" in blk and "→ сдача" not in blk, blk
    _refused([tx_item(amount=7000, description="Nmax 90101 +7000 аренда K3-BK-001")], C3_TEXT,
             "оплачена на 7000 из 7790")


# ═══ п.4 F2-честность ═════════════════════════════════════════════════════════════════════════════════════════

def test_p4_all_tools_carry_f2_fields():
    """F2_CONTRACT §1.1/§1.2: у КАЖДОГО ответа всех 7 инструментов — `source_version` = null с причиной «источник
    версии не отдаёт» и ключ `read_at`; мёртвое поле `version` пусто."""
    clk = Clock()
    node = {"name": "business_rules", "read": True, "text": "… 03.10.2026-1 …", "len": 18, "taken_at": T0 - 600,
            "why": ""}
    doors = {"history": lambda: [{"who": "клиент", "text": "привет", "ts": T0 - 5}], "rental": rental_door(age=1500),
             "cash": lambda **kw: tx([tx_item()]), "contract": Registry([DOC1]), "contract_pdf": pdf_door,
             "rules": lambda: node}
    results = []
    ctx = T.bind_ctx(NUMBER, doors, results, clk)
    for tool, args in (("history", {}), ("rental", {}), ("cash", {"booking_id": BK}), ("contract", {}),
                       ("contract_pdf", {"file_id": "PDF-0001"}), ("delivery", {}), ("rules", {})):
        results.append(T.call_tool(tool, args, doors, clk, ctx))
    for r in results:
        assert "source_version" in r and r["source_version"] is None, (r["tool"], r.get("source_version", "нет ключа"))
        assert r.get("source_version_basis") == SV_WORDS, (r["tool"], r.get("source_version_basis"))
        assert "read_at" in r and not r.get("version"), (r["tool"], r.get("version"))


def test_p4_version_never_from_signed_at_len_msgid_row():
    """Версия не выводится из `signed_at` договора, длины правил, msg_id или номера строки кассы, служебного
    `stand_meta` подделки: ни в `version`, ни в `source_version`, ни на карточке («версия: неизвестна»)."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    con = T.contract_result(Registry([DOC1])(phone=NUMBER), at=T0, number=NUMBER, rental=rent)
    cash = T.cash_result(tx([tx_item()]), at=T0)
    rules = T.rules_result({"name": "business_rules", "read": True, "text": "x" * 856, "len": 856, "taken_at": T0},
                           at=T0)
    assert con["outcome"] == T.FACT and cash["outcome"] == T.FACT and rules["outcome"] == T.FACT
    bad = ["2026-10-05 10:12", "856 симв.", "-100311:501:m11", "11", "K3-cash-v1", "K3-registry-v1"]
    for r in (con, rules, cash, rent):                         # договор первым: на 996ee09 у него version = signed_at
        assert not r.get("version") and r.get("source_version", "нет ключа") is None, (r["tool"], r.get("version"))
        assert not [b for b in bad if b == str(r.get("version")) or b == str(r.get("source_version"))], r["tool"]
    card = X.opora_of({"state": T.DONE, "results": [dict(r, req="%s #%d" % (r["tool"], i))
                                                    for i, r in enumerate((rent, con, cash, rules))]})
    assert card.count("версия: неизвестна") == 4 and "версия: 2026" not in card and "K3-" not in card, card


def test_p4_rental_rules_time_is_snapshot_time():
    """У rental/rules время данных — время СНИМКА (25 и 10 мин назад), а не вызова: `read_at`, карточка
    «прочитано ЧЧ:ММ» снимка; `at` (начало нашего запроса) — отдельно."""
    a = adapter(Script(final("Ок")), book_age=1500.0)
    rent_raw = a._tool_doors(NUMBER, 5)["rental"]()
    assert rent_raw.get("_taken_at") == T0 - 1500.0, rent_raw.get("_taken_at")
    rent = T.rental_result(rent_raw, at=T0)
    rules = T.rules_result({"name": "business_rules", "read": True, "text": "правила", "len": 7,
                            "taken_at": T0 - 600}, at=T0)
    assert rent.get("read_at") == T0 - 1500.0 and rent["at"] == T0, (rent.get("read_at"), rent["at"])
    assert rules.get("read_at") == T0 - 600 and rules["at"] == T0, (rules.get("read_at"), rules["at"])
    card = X.opora_of({"state": T.DONE, "results": [dict(rent, req="r"), dict(rules, req="b")]})
    assert "прочитано %s" % A.hm_phuket(T0 - 1500) in card and "прочитано %s" % A.hm_phuket(T0 - 600) in card, card
    assert "прочитано %s" % A.hm_phuket(T0) not in card, card


def test_p4_snapshot_time_unknown_is_unknown():
    """Снимочная дверь не передала время снимка — «время чтения неизвестно», а не время вызова."""
    rent = T.rental_result({"ok": True, "rows": [dict(ROW)]}, at=T0)
    assert "read_at" in rent and rent["read_at"] is None, rent.get("read_at", "нет ключа")
    card = X.opora_of({"state": T.DONE, "results": [dict(rent, req="r")]})
    assert "время чтения неизвестно" in card and "прочитано %s" % A.hm_phuket(T0) not in card, card


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
