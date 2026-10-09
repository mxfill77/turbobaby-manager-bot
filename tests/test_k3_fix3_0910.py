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

Каждый тест утверждает ПРАВИЛЬНОЕ поведение; на f2f7295 и на коммите шага 2 (996ee09) он падает по существу, на
ремонте проходит. Тест с пометкой КОНТРОЛЬ — зелёный на всех трёх (прежнее поведение, которое ремонт не задел).
Тесты п.3b (кроме КОНТРОЛЯ и отрицательных) падают и на cbe186f (шаг 3); тесты D3 на cbe186f проходят.

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
