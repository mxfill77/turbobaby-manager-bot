#!/usr/bin/env python3
"""CONTRACTREF1510 · чистый модуль `contract_ref` (проект §3, §6, приёмка §8.1 V1–V20; V21–V22 — находки критика 5, 7).

Сверка версий договора по ответу двери `contract_find`: привязка строки реестра к брони (телефон, байк, день), роль
строки и исход — какая версия текущая. Данные ТОЛЬКО синтетические: номер 79990001122, байк «Honda PCX 160 1234», срок
2026-10-14…2026-10-20, строки 34/35/36, doc вида 1AbCdEfDOC34, имя «Тест Тестов». Ответы двери — живой формы
`bridge_client.contract_find` (как подделка `tests/test_wa_signed_card.py`: reg_row / live_rows). Каждый отрицательный
случай — вместе с близнецом-проходом. Сети, моста, базы и файлов нет."""
import ast
import copy
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import contract_ref as CR  # noqa: E402
import wa_contract_state as CS  # noqa: E402

NUM = "79990001122"
PHONE = "+7 999 000-11-22"
NAME = "Тест Тестов"
NICK = "@test_nick"
BIKE = "Honda PCX 160 1234"
DF, DT = "2026-10-14", "2026-10-20"
BOOKING = "bk-0042"
S34, S35, S36 = "2026-10-14 17:47", "2026-10-14 18:37", "2026-10-14 19:04"


def doc(row):
    return "1AbCdEfDOC%d" % row


def reg_row(row, status, signed_at="", pdf_id="", bike=BIKE, date="2026-10-15", phone=PHONE, on=("phone",), doc_id=None):
    """Запись реестра в форме `bridge_client.contract_find` (как `test_wa_signed_card.reg_row`)."""
    return {"row": row, "doc_id": doc_id or doc(row), "client": NAME, "contract_date": date, "contract_date_raw": date,
            "created_raw": date, "date_src": "contract_date", "status": status, "signed": status == "ПОДПИСАН",
            "signed_at": signed_at, "bike": bike, "phone": phone, "pdf_id": pdf_id, "matched_on": list(on)}


def live_rows():
    return [reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(35, "ОТОЗВАН", S35, "P35"), reg_row(36, "ПОДПИСАН", S36, "PDF36")]


def find(rows, outcome=None, last9="990001122", **checked):
    """Ответ двери живой формы; outcome — как у моста, если не назван."""
    signed = [r for r in rows if r["signed"]]
    out = outcome or ("none" if not rows else "none_signed" if not signed else "one" if len(signed) == 1 else "ambiguous")
    ch = {"rows_scanned": 50, "matched": len(rows), "signed": len(signed), "returned": len(rows), "truncated": False,
          "undated": 0, "undated_signed": 0, "date_unparsed": 0, "unread": [], "complete": True}
    ch.update(checked)
    return {"ok": True, "outcome": out, "pick": dict(signed[0], pdf_ready=True) if out == "one" else None,
            "reason": None, "items": [dict(r) for r in rows], "undated_items": [], "checked": ch,
            "filter": {"phone_last9": last9, "name": "", "bike": "", "plate": "", "date_from": DF, "date_to": DT},
            "limit": 20, "limit_max": 100}


def rental(bike=BIKE, ds=DF, de=DT, booking=BOOKING):
    """Ответ инструмента аренды (FACT, один факт) — форма `wa_agent_tools.rental_result`."""
    return {"tool": "rental", "outcome": "fact", "source": "снимок броней", "ref": booking, "at": 0, "version": "",
            "window": "%s…%s" % (ds, de), "reason": "", "facts": [{
                "kind": "rental", "booking_id": booking, "bike": bike, "date_start": ds, "date_end": de,
                "status": "В аренде", "price": 1500, "currency": "THB"}]}


def binding(**over):
    b = CR.binding_of_rental(NUM, rental())
    b.update(over)
    return b


def V(rows, **kw):
    return CR.versions(find(rows, **kw), binding())


def rows_of(lst):
    return [it["row"] for it in lst]


# ═══ V1 · последовательность версий одной брони ═══════════════════════════════════════════════════════════════

def test_v01_revoked_then_new_is_pending_not_current():
    r = V([reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(36, "НОВЫЙ")])
    assert r["outcome"] == "pending" and r["current"] is None, r
    assert rows_of(r["pending"]) == [36] and rows_of(r["superseded"]) == [34], r
    r = V([reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(36, "ОТПРАВЛЕН")])
    assert r["outcome"] == "pending" and rows_of(r["pending"]) == [36] and r["current"] is None, r
    # близнецы: 34 подписан — текущая 34; живая последовательность 34/35 ОТОЗВАН + 36 ПОДПИСАН — текущая 36
    r = V([reg_row(34, "ПОДПИСАН", S34, "P34")])
    assert r["outcome"] == "current" and r["current"]["row"] == 34 and r["current"]["role"] == "current", r
    r = V(live_rows())
    assert r["outcome"] == "current" and r["current"]["row"] == 36, r
    assert rows_of(r["superseded"]) == [35, 34] and rows_of(r["rows"]) == [36, 35, 34], r


# ═══ V2 · двух привязанных подписанных — выбор за человеком ══════════════════════════════════════════════════

def test_v02_two_signed_bound_is_ambiguous_any_order_any_signed_at():
    a, b = reg_row(35, "ПОДПИСАН", S35, "P35"), reg_row(36, "ПОДПИСАН", S36, "PDF36")
    for rows in ([a, b], [b, a]):
        for sa35 in (S35, "2026-10-14 23:59", "2026-10-13 08:00"):
            rr = [dict(x, signed_at=sa35) if x["row"] == 35 else x for x in rows]
            for door in ("ambiguous", "one"):              # мост сказал «несколько» или ошибся — всё равно не выбираем
                r = CR.versions(find(rr, outcome=door), binding())
                assert r["outcome"] == "ambiguous" and r["current"] is None, (door, sa35, r)
                assert all(it["role"] != "current" for it in r["rows"]), r
    r = V([reg_row(35, "ОТОЗВАН", S35, "P35"), reg_row(36, "ПОДПИСАН", S36, "PDF36")])
    assert r["outcome"] == "current" and r["current"]["row"] == 36, r


# ═══ V3 · телефон: 9 цифр те же, код страны другой ═══════════════════════════════════════════════════════════

def test_v03_same_last9_other_country_code_is_foreign():
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone="+66 990001122")])
    assert r["outcome"] == "none" and r["current"] is None and rows_of(r["foreign"]) == [36], r
    for phone in ("+7 999 000 11 22", "79990001122", "999 000 11 22", "8 999 000-11-22"):
        r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone=phone)])
        assert r["outcome"] == "current" and r["current"]["row"] == 36, (phone, r)


# ═══ V4 · байк ═════════════════════════════════════════════════════════════════════════════════════════════════

def test_v04_other_bike_is_foreign_homoglyph_cc_same():
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", bike="Honda PCX 160 5678")])
    assert r["outcome"] == "none" and rows_of(r["foreign"]) == [36], r
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", bike="HONDA PCX160 1234")])
    assert r["outcome"] == "current", r
    b = CR.binding_of_rental(NUM, rental(bike="NINJA 400CC PHUKET 1234"))           # латиница в аренде
    r = CR.versions(find([reg_row(36, "ПОДПИСАН", S36, "PDF36", bike="NINJA 400СС PHUKET 1234")]), b)   # кириллица
    assert r["outcome"] == "current", r


# ═══ V5 · день договора в сроке брони (границы включительно) ═════════════════════════════════════════════════

def test_v05_contract_day_out_of_term_is_foreign_bounds_inclusive():
    for day in ("2026-10-21", "2026-10-13"):
        r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", date=day)])
        assert r["outcome"] == "none" and rows_of(r["foreign"]) == [36], (day, r)
    for day in (DF, DT):
        r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", date=day)])
        assert r["outcome"] == "current", (day, r)


# ═══ V6 · строка без телефона и ника — привязка не сверена ═══════════════════════════════════════════════════

def test_v06_no_phone_no_nick_unchecked_incomplete_nick_rules():
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone="", on=("bike",))])
    assert r["outcome"] == "incomplete" and r["current"] is None and rows_of(r["unchecked"]) == [36], r
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36")])
    assert r["outcome"] == "current", r
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone="", on=("nick",))], last9="990001122")
    assert r["outcome"] == "current", "ник, который дверь сверила с ЭТИМ номером"
    r = V([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone="", on=("nick",))], last9="111222333")
    assert r["outcome"] == "none" and rows_of(r["foreign"]) == [36], ("ник сверен с другим номером", r)


# ═══ V7 · исход двери ambiguous ═══════════════════════════════════════════════════════════════════════════════

def test_v07_door_ambiguous_is_ambiguous_door_one_is_current():
    rows = [reg_row(36, "ПОДПИСАН", S36, "PDF36"), reg_row(40, "ПОДПИСАН", S36, "PDF40", bike="Honda PCX 160 5678")]
    r = CR.versions(find(rows, outcome="ambiguous"), binding())
    assert r["outcome"] == "ambiguous" and r["current"] is None, r
    r = CR.versions(find([reg_row(36, "ПОДПИСАН", S36, "PDF36")], outcome="one"), binding())
    assert r["outcome"] == "current", r


# ═══ V8 · отказ, таймаут, неразобранный ответ — «неизвестно», НИКОГДА «договора нет» ═════════════════════════

def test_v08_unread_is_unknown_never_none():
    bad = ({"ok": False, "error": "card_deadline"}, {"ok": False, "error": "timeout"}, None, "x", {"ok": True},
           {"ok": True, "outcome": "one", "checked": {}}, {"ok": True, "items": [], "checked": {}},
           {"ok": True, "outcome": "weird", "items": [], "checked": {}}, {"ok": True, "outcome": "none", "items": [],
                                                                         "checked": None},
           {"ok": False}, {"ok": "true", "outcome": "none", "items": [], "checked": {}},
           {"ok": True, "outcome": "one", "items": ["строка"], "checked": {}})
    for resp in bad:
        r = CR.versions(resp, binding())
        assert r["outcome"] == "unknown", (resp, r)
        assert r["rows"] == [] and r["pending"] == [] and r["superseded"] == [] and r["current"] is None, r
        assert r["reason"].startswith("реестр не прочитан: "), r
    assert "card_deadline" in CR.versions(bad[0], binding())["reason"]
    assert CR.versions(find(live_rows()), binding())["outcome"] == "current"
    assert CR.versions(find([]), binding())["outcome"] == "none"


# ═══ V9 · ответ прочитан не целиком ══════════════════════════════════════════════════════════════════════════

def test_v09_not_whole_is_incomplete():
    rows = live_rows()
    for kw in ({"unread": ["лист"]}, {"unread": None}, {"undated_signed": 1}, {"undated_signed": True},
               {"undated_signed": None}, {"truncated": True}):
        r = V(rows, **kw)
        assert r["outcome"] == "incomplete" and r["current"] is None, (kw, r)
    r = CR.versions(find(rows, outcome="incomplete"), binding())
    assert r["outcome"] == "incomplete" and r["current"] is None, r
    r = V(rows, unread=[], undated_signed=0, truncated=False)
    assert r["outcome"] == "current", r


# ═══ V10 · привязка не полна ═════════════════════════════════════════════════════════════════════════════════

def test_v10_binding_incomplete():
    rows = live_rows()
    for over in ({"phones": []}, {"plate": ""}, {"date_from": ""}, {"date_to": ""},
                 {"date_from": "2026-10-21", "date_to": "2026-10-14"}):
        r = CR.versions(find(rows), binding(**over))
        assert r["outcome"] == "incomplete" and r["current"] is None, (over, r)
        assert r["reason"].startswith("привязка не полна"), r
    assert CR.versions(find(rows), binding())["outcome"] == "current"


# ═══ V11 · тождество версии: переподпись того же doc_id — НОВАЯ версия ═══════════════════════════════════════

def test_v11_resign_same_doc_new_version():
    old = reg_row(36, "ПОДПИСАН", S36, "PDF36")
    new = dict(old, signed_at="2026-10-15 09:10", pdf_id="PDF36B")
    assert not CR.same_version(old, new)
    r = V([new])
    assert r["current"]["signed_at"] == "2026-10-15 09:10" and r["current"]["pdf_id"] == "PDF36B", r
    assert CR.same_version(old, copy.deepcopy(old))
    assert not CR.same_version(dict(old, pdf_id=""), dict(old, pdf_id=""))
    assert not CR.same_version(dict(old, doc_id=""), dict(old, doc_id=""))
    loc = {"doc_id": doc(36), "signed_at": S36, "file_id": "PDF36"}             # локальная версия: file_id вместо pdf_id
    assert CR.same_version(old, loc) and CR.same_version(loc, old)
    assert CR.same_version(dict(old, doc_id=" %s " % doc(36)), old), "сравнение после strip"
    assert not CR.same_version(old, dict(loc, file_id="PDF36B"))
    assert not CR.same_version(None, old) and not CR.same_version(old, "x")


# ═══ V12 · у единственного подписанного нет PDF ══════════════════════════════════════════════════════════════

def test_v12_single_signed_without_pdf_incomplete():
    for over in ({"pdf_id": ""}, {"signed_at": ""}, {"doc_id": ""}):
        r = V([dict(reg_row(36, "ПОДПИСАН", S36, "PDF36"), **over)])
        assert r["outcome"] == "incomplete" and r["current"] is None, (over, r)
    assert V([reg_row(36, "ПОДПИСАН", S36, "PDF36")])["outcome"] == "current"


# ═══ V13 · только не текущие ══════════════════════════════════════════════════════════════════════════════════

def test_v13_only_dead_none_undated_incomplete():
    rows = [reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(35, "ОТКЛОНЁН", S35, "P35"), reg_row(33, "истёк")]
    r = V(rows)
    assert r["outcome"] == "none" and rows_of(r["superseded"]) == [35, 34, 33], r
    r = V(rows, undated=1)
    assert r["outcome"] == "incomplete", r
    assert V(rows, undated=0)["outcome"] == "none"
    r = V([reg_row(34, "ОШИБКА")])
    assert r["outcome"] == "none" and r["rows"][0]["role"] == "other", r


# ═══ V14 · несколько ждущих подписи ═══════════════════════════════════════════════════════════════════════════

def test_v14_two_pending_ordered_by_row_desc():
    r = V([reg_row(36, "ОТПРАВЛЕН"), reg_row(37, "НОВЫЙ")])
    assert r["outcome"] == "pending" and rows_of(r["pending"]) == [37, 36] and r["current"] is None, r


# ═══ V15 · граница устройством ════════════════════════════════════════════════════════════════════════════════

FORBIDDEN = {"make_contract", "save_passport", "ocr_passport", "_post", "issue_write_ticket", "agent_write",
             "create_booking", "open", "os", "sys", "socket", "sqlite3", "subprocess", "urllib", "requests"}


def test_v15_imports_names_purity_determinism():
    tree = ast.parse(open(CR.__file__, encoding="utf-8").read())
    imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
               for a in (n.names if isinstance(n, ast.Import) else [ast.alias(n.module or "")])}
    assert imports == {"re", "wa_agent_tools"}, imports
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
        {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & FORBIDDEN, names & FORBIDDEN
    resp, b = find(live_rows()), binding()
    r0, b0 = copy.deepcopy(resp), copy.deepcopy(b)
    one, two = CR.versions(resp, b), CR.versions(resp, b)
    assert resp == r0 and b == b0, "вход не мутируется"
    assert one == two
    rr = rental()
    rr0 = copy.deepcopy(rr)
    assert CR.ref_of(resp, NUM, rr) == one and rr == rr0


# ═══ V16 · в исходе нет клиента, телефона, ника и байка ═══════════════════════════════════════════════════════

def test_v16_no_personal_data_in_result_keys_exact():
    rows = [dict(r, nick=NICK, contacts="%s %s" % (NAME, PHONE)) for r in live_rows()]
    rows.append(reg_row(37, "ПОДПИСАН", S36, "PDF37", phone="+66 990001122"))
    rows.append(reg_row(38, "ОТПРАВЛЕН", bike="Honda PCX 160 5678"))
    for resp in (find(rows), find(rows, outcome="ambiguous"), find(rows, unread=["лист"])):
        r = CR.versions(resp, binding())
        text = repr(r)
        for bad in (NAME, "Тест", PHONE, "990001122", NUM, NICK, "test_nick", BIKE, "Honda", "PCX", "1234", "5678",
                    "+66"):
            assert bad not in text, (bad, text)
        assert set(r) == set(CR.RES_KEYS), sorted(r)
        for it in r["rows"]:
            assert tuple(it) == CR.ITEM_KEYS, it
            assert it["role"] in CR.ROLES
        assert r["booking_id"] == BOOKING


# ═══ V17 · привязка из аренды и из CRM ════════════════════════════════════════════════════════════════════════

def test_v17_bindings():
    for bad in (None, {"tool": "rental", "outcome": "empty", "facts": []}, {"outcome": "fact", "facts": [{}, {}]}, "x"):
        b = CR.binding_of_rental(NUM, bad)
        assert b == {"phones": [], "plate": "", "date_from": "", "date_to": "", "booking_id": ""}, (bad, b)
        assert CR.versions(find(live_rows()), b)["outcome"] == "incomplete"
    b = CR.binding_of_rental(NUM, rental())
    assert b == {"phones": [{"digits": NUM, "intl": True}], "plate": "1234", "date_from": DF, "date_to": DT,
                 "booking_id": BOOKING}, b
    b = CR.binding_of_rental(NUM, rental(ds="14.10.2026", de="2026-10-20 12:00")["facts"][0])   # сам факт; даты — ISO
    assert b["date_from"] == DF and b["date_to"] == DT and b["plate"] == "1234", b
    assert CR.binding_of_rental("12345", rental())["phones"] == []
    c = CR.binding_of_crm({"contacts": "081 234 5678; @nick", "bike": BIKE, "date_start": "2026-10-14 10:00",
                           "date_end": "2026-10-20 18:00", "booking_id": " %s " % BOOKING})
    assert c["phones"] == [{"digits": "0812345678", "intl": False}], c
    assert (c["plate"], c["date_from"], c["date_to"], c["booking_id"]) == ("1234", DF, DT, BOOKING), c
    c = CR.binding_of_crm({"contacts": "+66 81 234 5678 / 0066812345679 | 12-34", "bike": BIKE})
    assert c["phones"] == [{"digits": "66812345678", "intl": True}, {"digits": "66812345679", "intl": True}], c
    assert CR.binding_of_crm(None)["phones"] == [] and CR.binding_of_crm({})["plate"] == ""


# ═══ V18 · выбор строки CRM ═══════════════════════════════════════════════════════════════════════════════════

def test_v18_crm_pick():
    rows = [{"row": 12, "name": NAME, "date_start": "2026-10-14 10:00", "booking_id": "bk-1", "bike": BIKE},
            {"row": 13, "name": " тест тестов ", "date_start": "14.10.2026", "booking_id": "bk-2", "bike": BIKE},
            {"row": 14, "name": "Другой Клиент", "date_start": "2026-10-14", "booking_id": "bk-3", "bike": BIKE}]
    assert CR.crm_pick(rows, name=NAME, date_start=DF) == (None, CR.GEN_MANY_CRM % "12, 13")
    assert CR.crm_pick(rows, booking_key="Honda PCX 160 1234|%s|%s" % (NAME, DF)) == (None, CR.GEN_MANY_CRM % "12, 13")
    assert CR.crm_pick(rows, name="Нет Такого", date_start=DF) == (None, CR.GEN_NO_CRM)
    assert CR.crm_pick(rows, name=NAME, date_start="2026-10-15") == (None, CR.GEN_NO_CRM)
    assert CR.crm_pick(rows, booking_id="bk-404") == (None, CR.GEN_NO_CRM)
    assert CR.crm_pick([], name=NAME, date_start=DF) == (None, CR.GEN_NO_CRM)
    assert CR.crm_pick(rows, name="Другой Клиент", date_start="14.10.2026") == (rows[2], "")
    assert CR.crm_pick(rows, booking_id=" bk-2 ") == (rows[1], "")
    assert CR.crm_pick(rows, booking_key="x|Другой Клиент|2026-10-14 09:00") == (rows[2], "")


# ═══ V19 · слова сотруднику ═══════════════════════════════════════════════════════════════════════════════════

def test_v19_gen_words_each_outcome():
    nb = " — мост его не пересоберёт: строки паспорта в Bot Data нет (договор сделан не мостом)"
    assert CR.gen_words(V(live_rows())) == (
        "в реестре есть подписанный договор этой брони: стр. 36 · ПОДПИСАН 2026-10-14 19:04 · doc …fDOC36" + nb)
    assert CR.gen_words(V([reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(36, "ОТПРАВЛЕН")])) == (
        "в реестре договор этой брони ждёт подписи: стр. 36 · ОТПРАВЛЕН · doc …fDOC36" + nb)
    assert CR.gen_words(V([reg_row(35, "ПОДПИСАН", S35, "P35"), reg_row(36, "ПОДПИСАН", S36, "PDF36")])) == (
        "в реестре подписанных по этой брони несколько: стр. 36, стр. 35 — какой текущий, решает человек")
    many = [reg_row(n, "ПОДПИСАН", S36, "P%d" % n) for n in (31, 32, 33, 34, 35)]
    assert CR.gen_words(V(many)) == ("в реестре подписанных по этой брони несколько: стр. 35, стр. 34, стр. 33 и ещё 2 "
                                     "— какой текущий, решает человек")
    assert CR.gen_words(V([reg_row(34, "ОТОЗВАН", S34, "P34"), reg_row(35, "ОТКЛОНЁН", S35, "P35")])) == (
        "в реестре по байку и сроку брони подписанного и ждущего подписи нет (строк в сроке: 2; не текущие: "
        "стр. 35 ОТКЛОНЁН, стр. 34 ОТОЗВАН)")
    assert CR.gen_words(V([])) == "в реестре по байку и сроку брони подписанного и ждущего подписи нет (строк в сроке: 0)"
    r = V(live_rows(), unread=["лист"])
    assert CR.gen_words(r) == ("реестр прочитан не полностью или привязка не сверена (%s) — версия не названа; строки: "
                               "стр. 36 ПОДПИСАН, стр. 35 ОТОЗВАН, стр. 34 ОТОЗВАН" % r["reason"]), CR.gen_words(r)
    r = CR.versions(find([]), binding(plate=""))
    assert CR.gen_words(r) == "реестр прочитан не полностью или привязка не сверена (%s) — версия не названа" % (
        r["reason"])
    for resp in ({"ok": False, "error": "card_deadline"}, None):
        r = CR.versions(resp, binding())
        w = CR.gen_words(r)
        assert w == "реестр не прочитан (%s) — неизвестно, а не «договора нет»" % r["reason"], w
        assert "нет договора" not in w and "договора нет»" in w
    assert CR.gen_words(None).endswith("— неизвестно, а не «договора нет»")
    for res in (V(live_rows()), V([]), V(live_rows(), unread=["x"])):
        w = CR.gen_words(res)
        assert NAME not in w and "990001122" not in w and "Honda" not in w, w


# ═══ V20 · хвост doc_id тот же, что у блока модели ════════════════════════════════════════════════════════════

def test_v20_tail_equals_block_doc_tail():
    for x in ("1AbCdEfDOC34", "D36", "", None, "1Ab Cd/Ef-DOC_36ёж", "x" * 80):
        assert CR.tail(x) == CS.doc_tail(x), x
    assert CR.DOC_TAIL == CS.DOC_TAIL


# ═══ V21 · неоднозначность ДВЕРИ: строки названы «под фильтром», а не «по этой брони» (находка критика 5) ═════

def test_v21_door_ambiguous_words_name_filter_not_booking():
    own = reg_row(36, "ПОДПИСАН", S36, "PDF36")
    other = reg_row(40, "ПОДПИСАН", S36, "PDF40", bike="Honda PCX 160 5678")       # чужой байк — foreign
    r = CR.versions(find([own, other], outcome="ambiguous"), binding())
    assert r["outcome"] == "ambiguous" and [(it["row"], it["role"]) for it in r["rows"]] == [(40, "foreign"),
                                                                                           (36, "signed")], r
    w = CR.gen_words(r)
    assert w == ("в реестре под фильтром байка и срока подписанных несколько: стр. 40, стр. 36 (привязанных к брони — "
                 "1) — какой текущий, решает человек"), w
    assert "по этой брони" not in w, "чужая строка не названа строкой ЭТОЙ брони"
    r0 = CR.versions(find([dict(own, bike="Honda PCX 160 4321"), other], outcome="ambiguous"), binding())
    assert CR.gen_words(r0).endswith("(привязанных к брони — 0) — какой текущий, решает человек"), CR.gen_words(r0)
    # близнец: обе подписанные привязаны (R4) — прежние слова «по этой брони»
    two = CR.versions(find([own, reg_row(35, "ПОДПИСАН", S35, "P35")], outcome="ambiguous"), binding())
    assert CR.gen_words(two) == ("в реестре подписанных по этой брони несколько: стр. 36, стр. 35 — какой текущий, "
                                 "решает человек"), CR.gen_words(two)


# ═══ V22 · «+» кода страны не в начале куска CRM (находка критика 7) ════════════════════════════════════════════

def test_v22_intl_plus_after_name_checks_country_code():
    for contacts in ("Тест Тестов +7 999 000-11-22", "Тест +(7) 999 000 11 22", "тел. +7 999 000 11 22"):
        b = CR.binding_of_crm({"contacts": contacts, "bike": BIKE, "date_start": DF, "date_end": DT})
        assert b["phones"] == [{"digits": NUM, "intl": True}], (contacts, b)
        r = CR.versions(find([reg_row(36, "ПОДПИСАН", S36, "PDF36", phone="+66 990001122")]), b)
        assert r["outcome"] == "none" and rows_of(r["foreign"]) == [36], ("9 цифр те же, код другой", contacts, r)
        r = CR.versions(find([reg_row(36, "ПОДПИСАН", S36, "PDF36")]), b)          # близнец: тот же номер
        assert r["outcome"] == "current", (contacts, r)
    loc = CR.binding_of_crm({"contacts": "Тест Тестов 8 999 000-11-22; @nick", "bike": BIKE})
    assert loc["phones"] == [{"digits": "89990001122", "intl": False}], loc       # местная запись — без «+»


def test_constants_named_in_design():
    assert CR.OUTCOMES == ("current", "pending", "ambiguous", "none", "incomplete", "unknown")
    assert CR.ROLES == ("current", "signed", "pending", "superseded", "other", "foreign", "unchecked")
    assert CR.PENDING_STATUSES == ("НОВЫЙ", "ОТПРАВЛЕН") and CR.DEAD_STATUSES == ("ОТОЗВАН", "ОТКЛОНЕН", "ИСТЕК")
    assert CR.GEN_NO_CRM == "бронь в CRM не найдена — реестр не читал"
    assert CR.GEN_MANY_CRM == "броней в CRM с этим ключом несколько (строки %s) — реестр не читал"
    assert CR.GEN_CRM_UNREAD == "CRM не прочитан (%s) — реестр не читал, неизвестно"
    assert CR.GEN_NO_TERM == "в строке брони нет номера байка или срока — реестр не читал"
    for out in CR.OUTCOMES:
        assert isinstance(CR.gen_words({"outcome": out, "rows": [], "reason": "x"}), str)


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
