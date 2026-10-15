# -*- coding: utf-8 -*-
"""Сверка версий договора по реестру подписей — чистые функции (CONTRACTREF1510).

ЗАЧЕМ. Агент должен найти ИМЕННО договор клиента и его актуальную версию, а сотрудник — увидеть, что договор, сделанный
ФОРМОЙ (TB e-Sign, не мостом), уже лежит в реестре, когда `make_contract` отвечает `no_passport`. Ответ двери
`contract_find` уже прочитан вызывающим (проход подписи агента, отчёт splinter); здесь он только РАЗБИРАЕТСЯ: каждая
строка привязывается к брони (телефон, байк, день), получает роль, и называется исход — какая версия текущая.

ТОЖДЕСТВО ВЕРСИИ — (doc_id, signed_at, pdf_id): переподпись того же doc_id (новый signed_at или pdf_id) — НОВАЯ версия;
номер строки реестра (`row`) указывает только место. «Новейший по row или signed_at» не выбирается никогда: двух
привязанных подписанных — исход ambiguous, выбирает человек. Чужая (foreign) и непроверенная (unchecked) строки не
выбираются никогда. Отказ, таймаут, `card_deadline`, неразобранный ответ — исход unknown («неизвестно»), а не «договора
нет»; ответ, прочитанный не целиком, — incomplete.

ГРАНИЦА УСТРОЙСТВОМ: импорты ровно `re` и `wa_agent_tools`; сети, файлов, базы и окружения нет, двери не зовутся (страж —
ast в тесте). В исходе нет клиента, телефона, ника и байка: строка реестра несёт только row, doc_id, статус, подписан ли,
signed_at, pdf_id, день договора и роль."""
import re

import wa_agent_tools as T

# ── исходы, роли, статусы (§6.1) ─────────────────────────────────────────────────────────────────────────────
OUTCOMES = ("current", "pending", "ambiguous", "none", "incomplete", "unknown")
ROLES = ("current", "signed", "pending", "superseded", "other", "foreign", "unchecked")
PENDING_STATUSES = ("НОВЫЙ", "ОТПРАВЛЕН")                    # ждёт подписи
DEAD_STATUSES = ("ОТОЗВАН", "ОТКЛОНЕН", "ИСТЕК")             # не текущий (после нормализации Ё→Е)
DOOR_OUTCOMES = ("one", "ambiguous", "incomplete", "none", "none_signed")   # исходы двери contract_find
ITEM_KEYS = ("row", "doc_id", "status", "signed", "signed_at", "pdf_id", "contract_date", "role")
RES_KEYS = ("outcome", "reason", "current", "pending", "superseded", "foreign", "unchecked", "rows", "booking_id")
YES, NO, UNSURE = "да", "нет", "неизвестно"                  # исход одной проверки привязки строки к брони
DOC_TAIL = 6                                                 # = wa_contract_state.DOC_TAIL (тест сверяет)

# ── слова splinter до чтения реестра (§6.2) ──────────────────────────────────────────────────────────────────
GEN_NO_CRM = "бронь в CRM не найдена — реестр не читал"
GEN_MANY_CRM = "броней в CRM с этим ключом несколько (строки %s) — реестр не читал"
GEN_CRM_UNREAD = "CRM не прочитан (%s) — реестр не читал, неизвестно"
GEN_NO_TERM = "в строке брони нет номера байка или срока — реестр не читал"

# ── слова сотруднику по исходу (§6.3) ────────────────────────────────────────────────────────────────────────
GW_NOT_BRIDGE = " — мост его не пересоберёт: строки паспорта в Bot Data нет (договор сделан не мостом)"
GW_CURRENT = "в реестре есть подписанный договор этой брони: стр. %s · %s %s · doc %s" + GW_NOT_BRIDGE
GW_PENDING = "в реестре договор этой брони ждёт подписи: стр. %s · %s · doc %s" + GW_NOT_BRIDGE
GW_AMBIGUOUS = "в реестре подписанных по этой брони несколько: %s — какой текущий, решает человек"
# неоднозначность ДВЕРИ (R2), а привязанных к брони подписанных меньше двух: строки — под фильтром, а не «этой брони»
GW_AMBIGUOUS_DOOR = ("в реестре под фильтром байка и срока подписанных несколько: %s (привязанных к брони — %d) — какой "
                     "текущий, решает человек")
GW_NONE = "в реестре по байку и сроку брони подписанного и ждущего подписи нет (строк в сроке: %d%s)"
GW_NONE_DEAD = "; не текущие: %s"
GW_INCOMPLETE = "реестр прочитан не полностью или привязка не сверена (%s) — версия не названа%s"
GW_ROWS = "; строки: %s"
GW_UNKNOWN = "реестр не прочитан (%s) — неизвестно, а не «договора нет»"
ROWS_SHOWN = 3                                               # строк реестра словами — не больше, дальше «и ещё N»

# ── причины исхода (без клиента, телефона и байка) ───────────────────────────────────────────────────────────
W_UNREAD = "реестр не прочитан: %s"
W_UNPARSED = "ответ не разобран"
W_NOT_WHOLE = "реестр прочитан не целиком (не прочитано: %s)"
W_UNDATED_SIGNED = "подписанных без известного дня %s"
W_TRUNCATED = "выдача реестра усечена пределом — прочитано не всё"
W_DOOR_INCOMPLETE = "дверь: ответ неполон (%s)"
W_DOOR_AMBIGUOUS = "дверь: подписанных под фильтром несколько"
W_BINDING = "привязка не полна: нет %s"
W_BINDING_SPAN = "привязка не полна: начало срока позже конца"
W_MANY_SIGNED = "подписанных этой брони несколько (стр. %s)"
W_SIGNED_UNCHECKED = "подписанный договор без сверенной привязки (стр. %s)"
W_NO_KEY = "у подписанного нет doc_id, signed_at или pdf_id (стр. %s)"
W_CURRENT = "текущий — стр. %s"
W_PENDING = "ждёт подписи — стр. %s"
W_UNDATED = "строк без известного дня %s — подписанного и ждущего в сроке нет, но смотрели не всё"
W_NONE = "подписанного и ждущего подписи в сроке нет"

_DOC_SAFE = re.compile(r"[^A-Za-z0-9_\-]")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTACT_SPLIT = re.compile(r"[,;/|\n]+")                     # = делители `T.contract_phones` (esignPhones_ двери)
_DIGITS = re.compile(r"\D")
_INTL_PLUS = re.compile(r"\+[\s(]*\d")                       # «+» перед цифрами где угодно в куске («Имя +7 …»)


def tail(doc):
    """doc_id — хвостом не длиннее DOC_TAIL знаков (= `wa_contract_state.doc_tail`, тест сверяет)."""
    return "…" + _DOC_SAFE.sub("", str(doc or ""))[-DOC_TAIL:]


def _s(v):
    return str(v if v is not None else "").strip()


def _norm_status(status):
    """Статус для сравнения: верхний регистр, Ё→Е."""
    return _s(status).upper().replace("Ё", "Е")


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _empty_binding():
    return {"phones": [], "plate": "", "date_from": "", "date_to": "", "booking_id": ""}


def _iso(value):
    d = T.B.day_of(value)
    return d.isoformat() if d is not None else ""


def _rental_fact(rental):
    """Ответ инструмента аренды (FACT, ровно один факт) или сам факт аренды → факт | None."""
    if isinstance(rental, dict) and rental.get("kind") == "rental":
        return rental
    facts = rental.get("facts") if isinstance(rental, dict) and rental.get("outcome") == T.FACT else None
    if isinstance(facts, list) and len(facts) == 1 and isinstance(facts[0], dict):
        return facts[0]
    return None


def binding_of_rental(number, rental):
    """Номер обращения WhatsApp + аренда-факт → привязка. Номер WhatsApp — всегда международный (intl). Факта нет — все
    поля пусты (versions скажет incomplete, а не «договора нет»)."""
    b = _empty_binding()
    fact = _rental_fact(rental)
    if fact is not None:
        if T.last9(number):
            b["phones"] = [{"digits": _DIGITS.sub("", str(number or "")), "intl": True}]
        b["plate"] = T.plate_of(fact.get("bike"))
        b["date_from"], b["date_to"] = _iso(fact.get("date_start")), _iso(fact.get("date_end"))
        b["booking_id"] = str(fact.get("booking_id") or "")
    return b


def binding_of_crm(row):
    """Строка CRM `clients` → привязка. Телефон — кусок `contacts` (делители , ; / | и перевод строки) с 9+ цифрами;
    intl — в куске «+» перед цифрами (в начале или после имени: «Имя +7 …») или его цифры начинаются с «00» (их
    снимаем). Ник и прочее без цифр телефоном не становятся."""
    b = _empty_binding()
    if isinstance(row, dict):
        for piece in _CONTACT_SPLIT.split(str(row.get("contacts") or "")):
            raw = piece.strip()
            digits = _DIGITS.sub("", raw)
            if len(digits) < 9:
                continue
            intl = bool(_INTL_PLUS.search(raw)) or digits.startswith("00")
            b["phones"].append({"digits": digits[2:] if digits.startswith("00") else digits, "intl": intl})
        b["plate"] = T.plate_of(row.get("bike"))
        b["date_from"], b["date_to"] = _iso(row.get("date_start")), _iso(row.get("date_end"))
        b["booking_id"] = _s(row.get("booking_id"))
    return b


# ── привязка строки реестра к брони: три проверки, у каждой да / нет / неизвестно ─────────────────────────────

def _phone_check(raw, b, flt):
    cell = raw.get("phone")
    pl = T.contract_phones(cell)
    on = raw.get("matched_on") if isinstance(raw.get("matched_on"), list) else []
    nick = "nick" in on
    fl9 = _s(flt.get("phone_last9"))
    keys, clash = [], False
    for p in b.get("phones") or []:
        if not isinstance(p, dict):
            continue
        digits = _s(p.get("digits"))
        key = T.last9(digits)
        if not key:
            continue
        keys.append(key)
        if key in pl and (not p.get("intl") or not T.phone_country_clash(cell, digits)):
            return YES
        if nick and fl9 == key:
            return YES                                     # ник, который дверь сверила с ЭТИМ номером
        if key in pl:
            clash = True                                   # совпали только 9 цифр, код страны другой
    verdict = UNSURE
    if clash or (pl and keys) or (nick and fl9 and keys and fl9 not in keys):
        verdict = NO
    return verdict


def _bike_check(raw, b):
    pc, pb = T.plate_of(raw.get("bike")), _s(b.get("plate"))
    verdict = UNSURE
    if pc and pb:
        verdict = YES if pc == pb else NO
    return verdict


def _day_check(raw, b):
    cd, df, dt = _s(raw.get("contract_date")), _s(b.get("date_from")), _s(b.get("date_to"))
    verdict = UNSURE
    if _ISO_DAY.match(cd) and df and dt:
        verdict = YES if df <= cd <= dt else NO
    return verdict


def _role(raw, b, flt):
    checks = (_phone_check(raw, b, flt), _bike_check(raw, b), _day_check(raw, b))
    if NO in checks:
        return "foreign"
    if UNSURE in checks:
        return "unchecked"
    if raw.get("signed") is True:
        return "signed"
    st = _norm_status(raw.get("status"))
    return "pending" if st in PENDING_STATUSES else "superseded" if st in DEAD_STATUSES else "other"


def _item(raw, b, flt):
    row = raw.get("row")
    return {"row": row if _int(row) else None, "doc_id": _s(raw.get("doc_id")), "status": _s(raw.get("status")),
            "signed": raw.get("signed") is True, "signed_at": _s(raw.get("signed_at")), "pdf_id": _s(raw.get("pdf_id")),
            "contract_date": _s(raw.get("contract_date")), "role": _role(raw, b, flt)}


def _unread_why(resp):
    """Ответ двери не прочитан или не разобран → слова | None (прочитан)."""
    if not isinstance(resp, dict):
        return W_UNPARSED
    if resp.get("ok") is not True:
        return _s(resp.get("error")) or W_UNPARSED
    items, checked = resp.get("items"), resp.get("checked")
    if (resp.get("outcome") not in DOOR_OUTCOMES or not isinstance(items, list) or not isinstance(checked, dict)
            or any(not isinstance(x, dict) for x in items)):
        return W_UNPARSED
    return None


def _not_whole_why(resp, checked):
    """R1: ответ прочитан не целиком → слова | None."""
    unread, und = checked.get("unread"), checked.get("undated_signed")
    if not isinstance(unread, list) or unread:
        return W_NOT_WHOLE % (", ".join(_s(u) for u in unread) if isinstance(unread, list) else W_UNPARSED)
    if not _int(und) or und > 0:
        return W_UNDATED_SIGNED % (und if _int(und) else "?")
    if checked.get("truncated") is True or resp.get("truncated") is True:
        return W_TRUNCATED
    if resp.get("outcome") == "incomplete":
        why = resp.get("reason")
        return W_DOOR_INCOMPLETE % (_s(why.get("code")) if isinstance(why, dict) and why.get("code") else "без причины")
    return None


def _binding_why(b):
    """R3: привязка не полна → слова | None."""
    miss = [w for k, w in (("phones", "телефона"), ("plate", "номера байка"), ("date_from", "начала срока"),
                           ("date_to", "конца срока")) if not b.get(k)]
    if miss:
        return W_BINDING % ", ".join(miss)
    if _s(b.get("date_from")) > _s(b.get("date_to")):
        return W_BINDING_SPAN
    return None


def _rows_of(lst):
    return ", ".join(_row_word(it.get("row")) for it in lst)


def _row_word(row):
    return str(row) if row is not None else "?"


def versions(find_resp, binding):
    """Ответ двери `contract_find` + привязка брони → исход (§3.2). Вход не мутируется; тот же вход — равный исход."""
    b = binding if isinstance(binding, dict) else {}
    res = {"outcome": "unknown", "reason": "", "current": None, "pending": [], "superseded": [], "foreign": [],
           "unchecked": [], "rows": [], "booking_id": _s(b.get("booking_id"))}
    why = _unread_why(find_resp)
    if why is not None:                                          # U: «неизвестно», а не «договора нет»
        res["reason"] = W_UNREAD % why
        return res
    flt = find_resp.get("filter") if isinstance(find_resp.get("filter"), dict) else {}
    rows = [_item(raw, b, flt) for raw in find_resp["items"]]
    rows.sort(key=lambda it: (it["row"] is None, -(it["row"] or 0)))
    res["rows"] = rows
    checked = find_resp["checked"]
    signed = [it for it in rows if it["role"] == "signed"]                     # привязанные подписанные
    blind = [it for it in rows if it["signed"] and it["role"] == "unchecked"]  # подписанные с непроверенной привязкой
    pending = [it for it in rows if it["role"] == "pending"]
    undated = checked.get("undated")
    whole_why, binding_why = _not_whole_why(find_resp, checked), _binding_why(b)
    # порядок проверок — §3.2, первая сработавшая решает
    if whole_why is not None:                                                         # R1
        outcome, reason = "incomplete", whole_why
    elif find_resp.get("outcome") == "ambiguous":                                     # R2
        outcome, reason = "ambiguous", W_DOOR_AMBIGUOUS
    elif binding_why is not None:                                                     # R3
        outcome, reason = "incomplete", binding_why
    elif len(signed) >= 2:                                                            # R4: «новейший» не выбирается
        outcome, reason = "ambiguous", W_MANY_SIGNED % _rows_of(signed)
    elif blind:                                                                       # R5
        outcome, reason = "incomplete", W_SIGNED_UNCHECKED % _rows_of(blind)
    elif len(signed) == 1 and not (signed[0]["doc_id"] and signed[0]["signed_at"] and signed[0]["pdf_id"]):
        outcome, reason = "incomplete", W_NO_KEY % _row_word(signed[0]["row"])     # R6: тождество версии не полно
    elif len(signed) == 1:                                                            # R6
        c = signed[0]
        c["role"] = "current"
        outcome, reason, res["current"] = "current", W_CURRENT % _row_word(c["row"]), c
    elif pending:                                                                     # R7
        outcome, reason = "pending", W_PENDING % _rows_of(pending)
    elif _int(undated) and undated > 0:                                               # R8
        outcome, reason = "incomplete", W_UNDATED % undated
    else:                                                                             # R9
        outcome, reason = "none", W_NONE
    res["outcome"], res["reason"] = outcome, reason
    for role in ("pending", "superseded", "foreign", "unchecked"):
        res[role] = [it for it in rows if it["role"] == role]
    return res


def ref_of(find_resp, number, rental):
    """Проход подписи агента: ответ двери + номер обращения + аренда-факт → исход versions()."""
    return versions(find_resp, binding_of_rental(number, rental))


def _pdf_of(x):
    return _s(x.get("pdf_id")) or _s(x.get("file_id"))


def same_version(a, b):
    """Одна версия договора: doc_id, signed_at и PDF (pdf_id, иначе file_id) у обоих непусты и равны после strip."""
    if not (isinstance(a, dict) and isinstance(b, dict)):
        return False
    pairs = ((_s(a.get("doc_id")), _s(b.get("doc_id"))), (_s(a.get("signed_at")), _s(b.get("signed_at"))),
             (_pdf_of(a), _pdf_of(b)))
    return all(x and y and x == y for x, y in pairs)


def crm_pick(rows, booking_id=None, booking_key=None, name=None, date_start=None):
    """Строки CRM `clients` → (строка брони | None, слова | ""). По booking_id — точное равенство; иначе имя и день
    начала (из booking_key «модель|имя|дата» или из name/date_start): имя без регистра и пробелов по краям, день — тем
    же разбором, что у броней. Одна строка — она; ноль — GEN_NO_CRM; больше одной — GEN_MANY_CRM с номерами строк."""
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, (list, tuple)) else []
    bid = _s(booking_id)
    if bid:
        hit = [r for r in rows if _s(r.get("booking_id")) == bid]
    else:
        nm, ds = name, date_start
        if booking_key:
            nm, ds = (str(booking_key).split("|")[1:3] + [None, None])[:2]
        key, day = _s(nm).lower(), T.B.day_of(ds)
        hit = [r for r in rows if key and day is not None and _s(r.get("name")).lower() == key
               and T.B.day_of(r.get("date_start")) == day]
    if len(hit) == 1:
        return hit[0], ""
    if not hit:
        return None, GEN_NO_CRM
    return None, GEN_MANY_CRM % ", ".join(_row_word(r.get("row")) for r in hit)


def _rows_words(lst, status=False):
    """«стр. 35, стр. 36» (status — «стр. 34 ОТОЗВАН, …»): не больше ROWS_SHOWN, дальше «и ещё N»."""
    words = ["стр. %s%s" % (_row_word(it.get("row")), (" " + it.get("status")) if status and it.get("status") else "")
             for it in lst]
    more = len(words) - ROWS_SHOWN
    return ", ".join(words[:ROWS_SHOWN]) + (" и ещё %d" % more if more > 0 else "")


def gen_words(res):
    """Исход versions() → слова сотруднику (§6.3). Имени, телефона и ника в них нет."""
    res = res if isinstance(res, dict) else {}
    out, rows = res.get("outcome"), [it for it in res.get("rows") or [] if isinstance(it, dict)]
    reason = _s(res.get("reason")) or W_UNPARSED
    cur, pend = res.get("current"), [it for it in res.get("pending") or [] if isinstance(it, dict)]
    if out == "current" and isinstance(cur, dict):
        return GW_CURRENT % (_row_word(cur.get("row")), cur.get("status"), cur.get("signed_at"), tail(cur.get("doc_id")))
    if out == "pending" and pend:
        r = pend[0]
        return GW_PENDING % (_row_word(r.get("row")), r.get("status"), tail(r.get("doc_id")))
    if out == "ambiguous":
        bound = [it for it in rows if it.get("role") == "signed"]
        if len(bound) >= 2:                                  # R4: подписанных ЭТОЙ брони (привязанных) несколько
            return GW_AMBIGUOUS % _rows_words(bound)
        signed = [it for it in rows if it.get("signed")]     # R2: несколько — под фильтром двери, не обязательно эта бронь
        return GW_AMBIGUOUS_DOOR % (_rows_words(signed) or "строки не названы", len(bound))
    if out == "none":
        dead = [it for it in res.get("superseded") or [] if isinstance(it, dict)]
        return GW_NONE % (len(rows), GW_NONE_DEAD % _rows_words(dead, status=True) if dead else "")
    if out == "incomplete":
        return GW_INCOMPLETE % (reason, GW_ROWS % _rows_words(rows, status=True) if rows else "")
    return GW_UNKNOWN % reason
