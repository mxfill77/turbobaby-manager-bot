# -*- coding: utf-8 -*-
"""rental_case_rules.py — чистые правила дела аренды К4 (TB-FILIPP-K4-CASE-FOUNDATION-0910).

Источник истины — out/CONTRACT_K4.md §6 (и §3, §4.7, §4.8, §8, §10, §12); устройство — out/DESIGN_K4.md §2–§3, §6–§7.
Адреса `файл:строка` — в кандидате f2f7295 (копия wt/), выводы по коду, не по живому состоянию.

ЧИСТОТА (I20, К4-C18): без БД, сети, часов, окружения и конфигов. «Сейчас» приходит аргументом `moment`
(секунды эпохи), день считается в зоне TZ_H сдвигом часов, без таблиц зон (CONTRACT §1.1). Ничего не пишет и не исполняет: каждая
функция отдаёт вердикт, решение о записи — у rental_case.Store (единственный писатель, I23).

ПРЕДИКАТЫ КАНДИДАТА — импортом «как есть» (DESIGN §1.1 «бронь: предикаты»): `day_of`, `is_active`, `is_manual`,
`status_of`, `phone_keys` (wa_book_read.py:113-160, 356-366) и `plate_of`, `phone_country_clash`, `last9`
(wa_agent_tools.py:169-201). Оба модуля импортируют только stdlib и wa_agent_knowledge (wa_book_read.py:38-40,
wa_agent_tools.py:60-65; wa_agent_knowledge.py:27-29 — datetime, re, time) — сети, окружения и конфигов при импорте
нет. Обращение — через атрибут модуля в момент вызова (`_B.day_of`, `_T.plate_of`): при обратном импорте
(шаг 3 DESIGN §11 — `cash_of_rental` делегирует `bind_cash`) частично загруженный модуль не ломает импорт.

ЗАПРЕЩЕНО (I17, К4-C4/C25, мутанты M1/M1b/M21): выбор аренды по максимуму даты, по последнему элементу, по порядку
строк, через функцию «аренды момента» модуля позиции байка, по окну вокруг «сегодня» (кроме точного дня выдачи). В модуле нет
ни максимума, ни сортировки, ни индекса с конца; больше одного кандидата — всегда unknown с missing и ask (C5).

UNKNOWN (I16, C17): параметр, равный строке "UNKNOWN", правило не продвигает — исход unknown/справка, а не догадка.
"""

import datetime
import hashlib
import json
import re
from typing import Any, Collection, Dict, List, Mapping, Optional, Sequence, Tuple

import intake_confirm as _IC    # APPROVEFIX1610: знаки вопроса, слова правки, спокойный остаток, пробег (только `re`)
import wa_agent_tools as _T
import wa_book_read as _B

UNKNOWN = "UNKNOWN"

# ----------------------------------------------------------------------------------------------------------------
# Параметры (CONTRACT §10). Значения — только принятые нормы и литералы кода с адресом; остальное UNKNOWN.
# Модуль их не меняет; подмена — словарём вызывающего (Store(params=…)), недостающий ключ берётся отсюда.
# ----------------------------------------------------------------------------------------------------------------

OWNER_IDS = frozenset((504608015, 6879003264, 5466425480))          # splinter.py:284, wa_agent.py:175

PARAMS_DEFAULT = {
    "TZ_H": 7,                                                        # bike_position.py:66, wa_book_read.py:44
    "APPROVAL_TTL_S": {"activate": 1800, "close": 1800, "booking": UNKNOWN},   # splinter.py:510, 518; :11682-11683
    "MAX_POST_ATTEMPTS": 1,
    "STAFF_PLACES": {"байк": ["topic", "delivery"], "цена": ["agents"], "бронь": ["agents"],
                     "сложность": ["agents"]},                       # staff_ask.py:29-31
    "OWNER_IDS": OWNER_IDS,
    "APPROVER_IDS": OWNER_IDS,                                        # менеджеры — UNKNOWN (В10)
    "STAFF_ADDRESSEES": {"topic": UNKNOWN, "delivery": UNKNOWN, "agents": UNKNOWN},   # В5а
    "APPROVAL_REPLY_REQUIRED": UNKNOWN,
    "APPROVAL_YES_WORDS": ("да", "ок"),                              # splinter.py:11686
    "APPROVAL_YES_STEMS": ("подтвержд", "заверш", "закрывай", "активируй", "ставь"),   # splinter.py:11686, 11756, 11802
    "APPROVAL_NO_STEMS": ("нет", "отмена", "отклон"),                 # splinter.py:11739
    "APPROVAL_NO_AFTER_NE": ("актив", "заверш", "закрыв", "став"),    # splinter.py:11739, 11781, 11797
    "ACCEPTANCE_SIGNAL": UNKNOWN,
    "ACCEPT_WORDS": UNKNOWN,
    "ACCEPT_NO_STEMS": UNKNOWN,
    "KEY_DIGITS": 9,                                                  # wa_book_read.py:45
    "BUSINESS_HOURS": UNKNOWN,
    "STAFF_REMIND_AFTER": UNKNOWN,
    "WAIT_BEFORE_AGENTS": UNKNOWN,                                    # 3 ч кандидата — значение строителя (В5)
    "ESCALATION_STEP2": UNKNOWN,
    "ANSWER_TTL": UNKNOWN,
    "LATE_ANSWER_ROUTE": UNKNOWN,
    "PHYSICAL_DONE_SOURCES": {"readiness": UNKNOWN, "delivery": UNKNOWN, "handover": UNKNOWN, "return": UNKNOWN,
                              "pickup": UNKNOWN, "other": UNKNOWN},
    "RESULT_RECORD_PLACE": {"handover": "crm:в аренде", "return": "crm:завершена", "readiness": UNKNOWN,
                            "delivery": UNKNOWN, "pickup": UNKNOWN, "other": UNKNOWN},   # Booking.js:348, 463
    "CASE_ON_INTERVENTION": UNKNOWN,
    "PAUSE_DURATION": UNKNOWN,
    "PAUSE_RELEASER": UNKNOWN,
    "NON_WA_MEDIA_EXEMPT": UNKNOWN,                                   # WAPAUSEMEDIA0410 — только эхо WA
    "FINAL_NOTICE_REQUIRED": UNKNOWN,
    "FEEDS_CONNECTED": frozenset(),
    "NEW_REQUEST_RULE": UNKNOWN,
    "AUTO_ASK": UNKNOWN,
    "STALE_ACTIVE_DAYS": UNKNOWN,
    "CONTINUATION_GAP_DAYS": UNKNOWN,
    "MONEY_CLOSE_RULE": UNKNOWN,                                      # известное значение — "cash_and_second_source"
    "HANDOVER_DAY_TOLERANCE": UNKNOWN,
    "CASH_PRE_START_DAYS": UNKNOWN,
    "CASH_POST_END_DAYS": UNKNOWN,
    "CONTRACT_PRE_START_DAYS": UNKNOWN,
    "PAST_LOOKBACK": UNKNOWN,
    "AUTO_CANCEL_B_MEANING": UNKNOWN,
    "TG_CONTACT_MATCH": UNKNOWN,
    "CASH_ROLE_MULTI_MOVE": UNKNOWN,
    "RENTAL_CONFLICT_RULE": UNKNOWN,
    "BOOKING_ID_ORIGIN": UNKNOWN,
    "PAYMENT_RECORD_PLACE": UNKNOWN,
    "CANCEL_RECORD_PLACE": UNKNOWN,
    "CANCEL_PREPAY": UNKNOWN,
    "EXTENSION_NEXT_BOOKING": UNKNOWN,
    "EXTENSION_PAY_WHEN": UNKNOWN,
    "CURRENCY_RATE": UNKNOWN,
    "SMALL_CHANGE_MAX": UNKNOWN,
    "PASSPORT_DEPOSIT_RETURN_RECORD": UNKNOWN,
    "CLOSING_K_SEMANTICS": UNKNOWN,
    "DAMAGE_RULE": UNKNOWN,
    "DELIVERY_ASSIGNEE": UNKNOWN,
}

# Имена, которые CONTRACT §10 называет, но параметрами НЕ являются (поведение зашито или К4 их не использует).
NOT_PARAMS = ("DAYS_RULE", "STAFF_LANG", "CLIENT_SEND", "PAY_CONFIRM", "DRAFT_WAIT_NO_PRESS", "RENTAL_END_REMIND_DAYS")

# Параметры, которые в PARAMS_DEFAULT целиком или частью равны UNKNOWN (перечень для HANDOFF «требует решения»).
UNKNOWN_PARAMS = tuple(
    name for name, value in PARAMS_DEFAULT.items()
    if value == UNKNOWN or (isinstance(value, dict) and UNKNOWN in value.values()))

# ----------------------------------------------------------------------------------------------------------------
# Перечисления (CONTRACT §3, §4.7, §12)
# ----------------------------------------------------------------------------------------------------------------

CLASSES = ("current", "current_unactivated", "future", "past", "stale_booking", "unknown")
FLAGS = ("overdue", "auto_cancel_on", "manual_status", "no_dates", "phone_clash", "stub_name")
PURPOSES = ("client", "handover", "return", "debt", "cash", "contract", "position")
INTENTS = ("current", "future", "past", "specific", None)
BUMP_REASONS = ("new_request", "cancel", "rental_rebind", "period_changed", "bike_changed", "status_drift")
STAGES = ("question_sent", "answer_received", "task_accepted", "physically_done", "result_recorded",
          "client_notified")
STAGE_NO = dict((name, i + 1) for i, name in enumerate(STAGES))
VERDICTS = ("accepted", "reference_author_unverified", "reference_foreign_author", "reference_foreign_place",
            "reference_drift", "reference_stale_version", "reference_expired", "reference_late",
            "reference_superseded", "reference_cancelled", "reference_answered", "reference_unclear",
            "reference_no_reply", "reference_restart")
COVER_BASES = ("document", "addendum", "human_confirmed")

REASONS = (
    "case_not_found", "case_closed", "case_cancelled", "booking_taken", "anchor_taken", "no_plate", "no_start",
    "rental_not_found", "rental_ambiguous", "two_active", "stale_active", "possible_continuation", "link_drift",
    "link_missing", "stale_read", "drift_bike", "drift_start", "drift_name", "phone_clash", "contact",
    "contact_superseded", "contact_source", "attention", "pause_mismatch", "bad_transition", "expect_state",
    "not_reply", "not_linked", "evidence_forbidden", "evidence_foreign", "evidence_missing", "order",
    "readback_mismatch", "not_delivered", "blockers", "obligation_missing", "closing_fact_invalid", "notice_inflight",
    "approver_unknown", "approver_foreign", "param_unknown", "feed_unknown", "no_thai", "cash_other_booking",
    "cash_pre_start", "cash_post_end", "cash_no_rental", "which_rental", "role_unknown", "contract_pre_start",
    "doc_conflict", "doc_unknown", "doc_foreign_rental", "sha_missing", "pdf_not_of_contract", "deduped",
    "store_busy", "idem_payload_mismatch", "task_cancelled", "internal", "doc_period_not_covered",
    "doc_period_unknown", "doc_ambiguous", "second_source_missing", "doc_cover_invalid", "doc_cover_set",
    "period_not_given")
MISSING = ("intent", "booking_id", "dates", "bike", "contact", "which_rental", "link_confirmation", "continuation",
           "addressee", "acceptance_signal", "done_source", "record_place", "approver", "ttl", "business_hours",
           "payment_place", "feed", "retry", "document_period", "second_source", "period")

ST_BOOKED, ST_RENTED, ST_DONE = _B.ST_BOOKED, _B.ST_RENTED, _B.ST_DONE     # «бронь», «в аренде», «завершена»
R_RENT = _T.R_RENT                                                        # «оплата аренды» (wa_agent_tools.py:87)
STUB_NAMES = ("", "—", "-", "?")                                          # intake пишет «—» (splinter.py:11702)

# ----------------------------------------------------------------------------------------------------------------
# Общие помощники
# ----------------------------------------------------------------------------------------------------------------


def _p(params, name):
    """Параметр из словаря вызывающего; недостающий ключ — значение PARAMS_DEFAULT."""
    if params is not None and name in params:
        return params[name]
    return PARAMS_DEFAULT[name]


def is_unknown(value):
    return isinstance(value, str) and value == UNKNOWN


def _known_int(value):
    """Известное целое (не bool и не UNKNOWN) → int, иначе None."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _known_num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _sub(mapping, key):
    """Значение словаря-параметра по ключу; сам параметр UNKNOWN или ключа нет — UNKNOWN."""
    if isinstance(mapping, Mapping):
        return mapping.get(key, UNKNOWN)
    return UNKNOWN


def _as_id_set(value):
    """Набор числовых id (frozenset/set/list/json-строка) → frozenset[int] без меток; UNKNOWN/мусор → None."""
    if is_unknown(value) or value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(v for v in value if isinstance(v, int) and not isinstance(v, bool))
    return None


def _is_int_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def approver_ok(author_id, params):
    """id ∈ APPROVER_IDS (числом; метка UNKNOWN внутри набора никого не пропускает)."""
    ids = _as_id_set(_p(params, "APPROVER_IDS"))
    return _is_int_id(author_id) and ids is not None and author_id in ids


def day_of_moment(moment, tz_h=7):
    """Секунды эпохи → date в зоне +tz_h сдвигом часов, без таблиц зон (CONTRACT §1.1)."""
    return (datetime.datetime.fromtimestamp(float(moment), datetime.timezone.utc)
            + datetime.timedelta(hours=tz_h)).date()


def _date(value):
    """'YYYY-MM-DD' | 'yyyy-MM-dd HH:mm' | date → date | None (wa_book_read.day_of)."""
    if isinstance(value, datetime.date):
        return value
    if value is None:
        return None
    return _B.day_of(value)


def _iso(value):
    d = _date(value)
    return d.isoformat() if d is not None else None


def _dm(value):
    """Дата → «ДД.ММ» для текста вопроса; нет даты — «?»."""
    d = _date(value)
    return "%02d.%02d" % (d.day, d.month) if d is not None else "?"


def _s(value):
    return "" if value is None else str(value).strip()


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _canon_list(items):
    """Канонический порядок строк для отпечатка множества (не выбор: результат только хешируется)."""
    out = [json.dumps(i, ensure_ascii=False, sort_keys=True) for i in items]
    out.sort()
    return out


def _unknown_out(reason, missing, ask, **extra):
    out = {"code": "unknown", "reason": reason, "missing": list(missing), "ask": ask}
    out.update(extra)
    return out


# ----------------------------------------------------------------------------------------------------------------
# Строка, имя, якорь, контакт
# ----------------------------------------------------------------------------------------------------------------


def name_norm(name: Any) -> Optional[str]:
    """str(name).strip().lower() — как мост опознаёт строку (Booking.js:207, 337, 392); заглушка → None (I-18)."""
    if name is None:
        return None
    s = str(name).strip().lower()
    return None if s in STUB_NAMES else s


def plate_of_row(row):
    return _T.plate_of((row or {}).get("bike")) or None


def anchor_of(row: Mapping[str, Any]) -> Optional[str]:
    """"plate|YYYY-MM-DD|name_norm"; нет номера, дня начала или имени (заглушка) → None. Телефон не входит."""
    plate = plate_of_row(row)
    start = _iso((row or {}).get("date_start"))
    nm = name_norm((row or {}).get("name"))
    if not plate or not start or not nm:
        return None
    return "%s|%s|%s" % (plate, start, nm)


_RX_PHONE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")      # = wa_book_read._RX_PHONE (wa_book_read.py:353)
_RX_DIGITS = re.compile(r"\d{9,15}")                    # = wa_book_read._RX_DIGITS (wa_book_read.py:354)


def phones_full(contacts_cell):
    """Номера клетки U целиком (цифры) — тем же разбором, что phone_keys (wa_book_read.py:356-366)."""
    s = str(contacts_cell or "")
    out = []
    for m in _RX_PHONE.finditer(s):
        d = re.sub(r"\D", "", m.group(0))
        if 9 <= len(d) <= 15 and d not in out:
            out.append(d)
    for m in _RX_DIGITS.finditer(s):
        d = m.group(0)
        if not any(x.endswith(d) or d.endswith(x) for x in out):
            out.append(d)
    return out


def _keys(contacts_cell, key_digits):
    if key_digits == _B.KEY_DIGITS:
        return _B.phone_keys(contacts_cell)
    return set(d[-key_digits:] for d in phones_full(contacts_cell) if len(d) >= key_digits)


def contact_match(contacts_cell: str, number: str, key_digits: int = 9) -> str:
    """Номер обращения против клетки U: "match" — хвост key_digits цифр совпал; "clash" — совпал только хвост, а
    записан с явным другим кодом страны (phone_country_clash, wa_agent_tools.py:185-201); "none" — не совпал."""
    digits = re.sub(r"\D", "", str(number or ""))
    if len(digits) < key_digits:
        return "none"
    key = digits[-key_digits:]
    if key not in _keys(contacts_cell, key_digits):
        return "none"
    if _T.phone_country_clash(contacts_cell, number):
        return "clash"
    return "match"


# ----------------------------------------------------------------------------------------------------------------
# Класс строки (CONTRACT §3.1, DESIGN §3.2)
# ----------------------------------------------------------------------------------------------------------------


def _auto_cancel_on(row):
    return _s(row.get("auto_cancel")).upper() == "ON"


def classify(row: Mapping[str, Any], moment: float, params: Mapping[str, Any]) -> Dict[str, Any]:
    """{"cls","flags","plate","start_day","end_day","days","anchor","name_norm"}.

    current — «в аренде» при B≠ON (is_active, wa_book_read.py:152-154), флаг overdue при end_day < дня момента;
    current_unactivated — «бронь», start ≤ день ≤ end; future — «бронь», start > день; stale_booking — «бронь»,
    end < день; past — «завершена»; unknown — рукописный/пустой статус (is_manual), «в аренде» при B=ON
    (AUTO_CANCEL_B_MEANING), нет даты начала, а также нет даты конца у «бронь»/«в аренде» (класс по сроку не
    решается — толкование, см. contract_deviations).
    """
    row = row or {}
    flags = []
    plate = plate_of_row(row)
    sd, ed = _date(row.get("date_start")), _date(row.get("date_end"))
    nm = name_norm(row.get("name"))
    days = (ed - sd).days if sd is not None and ed is not None else None      # 05.10-1 п.3: возврат − выдача
    if nm is None:
        flags.append("stub_name")
    if _auto_cancel_on(row):
        flags.append("auto_cancel_on")
    if sd is None or ed is None:
        flags.append("no_dates")
    st = _B.status_of(row)
    today = day_of_moment(moment, _known_int(_p(params, "TZ_H")) or 0)
    cls = "unknown"
    if not st or _B.is_manual(row):
        flags.append("manual_status")
    elif st == ST_DONE:
        cls = "past"
    elif sd is None or ed is None:
        cls = "unknown"
    elif st == ST_RENTED:
        if _B.is_active(row):
            cls = "current"
            if ed < today:
                flags.append("overdue")
        else:
            cls = "unknown"                                       # «в аренде» при B=ON: AUTO_CANCEL_B_MEANING
    elif st == ST_BOOKED:
        if sd > today:
            cls = "future"
        elif ed < today:
            cls = "stale_booking"
        else:
            cls = "current_unactivated"
    return {"cls": cls, "flags": flags, "plate": plate, "start_day": sd.isoformat() if sd else None,
            "end_day": ed.isoformat() if ed else None, "days": days, "anchor": anchor_of(row), "name_norm": nm}


# ----------------------------------------------------------------------------------------------------------------
# Выбор аренды (CONTRACT §6 pick, DESIGN §3.3–§3.4)
# ----------------------------------------------------------------------------------------------------------------

_CLS_WORDS = {"current": "текущую аренду", "current_unactivated": "бронь (срок уже идёт)", "future": "бронь",
              "past": "прошлую аренду", "stale_booking": "просроченную бронь", "unknown": "строку"}
_NAMED_PURPOSES = ("cash", "return", "debt", "handover")     # вопрос сотруднику/человеку — имя различает аренды


def _cand(row, c):
    """Краткая запись кандидата для вопроса и журнала (без контактов)."""
    return {"row": row.get("row"), "cls": c["cls"], "flags": list(c["flags"]), "plate": c["plate"],
            "bike": _s(row.get("bike")), "name": _s(row.get("name")), "status": _s(row.get("status")),
            "start_day": c["start_day"], "end_day": c["end_day"],
            "booking_id": _s(row.get("booking_id")) or None}


def _describe(cand, purpose):
    what = _CLS_WORDS.get(cand.get("cls") or "", "аренду")
    bike = _s(cand.get("bike")) or _s(cand.get("plate")) or "байк ?"
    parts = ["%s–%s" % (_dm(cand.get("start_day")), _dm(cand.get("end_day")))]
    if cand.get("row") is not None:
        parts.append("строка %s" % cand.get("row"))
    if purpose in _NAMED_PURPOSES and _s(cand.get("name")):
        parts.append(_s(cand.get("name")))
    return "%s %s (%s)" % (what, bike, ", ".join(parts))


def ask_for(candidates: Sequence[Mapping[str, Any]], purpose: str, intent: Optional[str]) -> str:
    """Конкретный вопрос из различающих полей кандидатов (DESIGN §3.4); всегда непустой (C5)."""
    cands = list(candidates or [])
    if not cands:
        if purpose == "client":
            if intent == "future":
                return "Брони по вашему номеру не нашёл. На какой номер или имя оформлена бронь и на какие даты?"
            return "По вашему номеру аренды не нашёл. На какой номер или имя оформлена аренда?"
        if purpose == "handover":
            return "Брони этого байка на этот день не нашёл — какая бронь выдаётся (дата и имя)?"
        if purpose in ("return", "debt"):
            return "Аренды этого байка в статусе «в аренде» не нашёл — какая аренда возвращается (строка, имя)?"
        if purpose == "cash":
            return "Строку кассы не к чему привязать — к какой аренде она относится (строка, имя, даты)?"
        if purpose == "contract":
            return "Аренды для этого договора не нашёл — к какой аренде он относится (байк и даты)?"
        return "Какая аренда имеется в виду (байк, даты, имя)?"
    listed = " или ".join(_describe(c, purpose) for c in cands)
    if purpose == "client":
        return "Уточните, пожалуйста: вы про %s?" % listed
    if purpose in ("return", "debt"):
        return "По байку несколько аренд в статусе «в аренде»: %s — какая возвращается?" % listed
    if purpose == "handover":
        return "Какая бронь выдаётся: %s?" % listed
    if purpose == "cash":
        return "К какой аренде относится строка кассы: %s?" % listed
    if purpose == "contract":
        return "Какой договор нужен: за %s?" % listed
    return "Уточните, какая аренда: %s?" % listed


def _found(row, c):
    return {"code": "found", "row": row, "cls": c["cls"], "candidates": [_cand(row, c)], "missing": [], "ask": "",
            "reason": ""}


def _pick_unknown(reason, missing, cands, purpose, intent, ask=None):
    return {"code": "unknown", "row": None, "cls": None, "candidates": list(cands), "missing": list(missing),
            "ask": ask or ask_for(cands, purpose, intent), "reason": reason}


def _overlaps(sd, ed, q_from, q_to):
    """Пересечение сроков по дням включительно (все аргументы — date)."""
    return sd <= q_to and q_from <= ed


def _stale(c, today, params):
    """«в аренде» с просрочкой — висяк? STALE_ACTIVE_DAYS=UNKNOWN → любая просрочка (I-5)."""
    if "overdue" not in c["flags"]:
        return False
    n = _known_int(_p(params, "STALE_ACTIVE_DAYS"))
    if n is None:
        return True
    return (today - _date(c["end_day"])).days >= n


def _contact_filter(contact, params, classified):
    """client: строки контакта по клетке U (контакт задаёт код, не модель).
    → (пары (row, c) | None, (reason, missing, ask) | None)."""
    if isinstance(contact, Mapping):
        channel, value = _s(contact.get("channel")) or "wa", contact.get("value")
    else:
        channel, value = "wa", contact
    if not _s(value):
        return None, ("contact", ["contact"], "С какого номера или под каким именем оформлена аренда?")
    if channel in ("tg_id", "tg_username"):
        # клиент из TG по нику в U — TG_CONTACT_MATCH (UNKNOWN; смысла известного значения контракт не задаёт)
        return None, ("contact", ["contact"], "Клиент из Telegram: на какой номер телефона оформлена аренда?")
    kd = _known_int(_p(params, "KEY_DIGITS")) or 9
    out, clash = [], []
    for row, c in classified:
        verdict = contact_match(row.get("contacts"), value, kd)
        if verdict == "match":
            out.append((row, c))
        elif verdict == "clash":
            clash.append(_cand(row, c))
    if clash:
        return None, ("phone_clash", ["contact"],
                      "Номер обращения совпал со строкой только последними цифрами, а код страны другой — "
                      "это ваша аренда или другого человека? Назовите имя и даты аренды.")
    return out, None


def pick(rows: Sequence[Mapping[str, Any]], query: Mapping[str, Any], moment: float,
         params: Mapping[str, Any]) -> Dict[str, Any]:
    """{"code": "found"|"unknown", "row","cls","candidates","missing","ask","reason"} — DESIGN §3.3.

    found только при ровно одном кандидате (I17); порядок строк, максимум даты, «аренда момента» и окно вокруг
    «сегодня» не участвуют (кроме точного дня выдачи для handover). unknown — всегда с missing и ask (C5)."""
    query = query or {}
    purpose = query.get("purpose")
    intent = query.get("intent")
    if purpose not in PURPOSES:
        raise ValueError("pick: purpose %r вне %r" % (purpose, PURPOSES))
    tz_h = _known_int(_p(params, "TZ_H")) or 0
    on_day = _date(query.get("on_day"))
    today = on_day if on_day is not None else day_of_moment(moment, tz_h)
    all_rows = [r for r in (rows or []) if isinstance(r, Mapping)]
    classified = [(r, classify(r, moment, params)) for r in all_rows]

    if purpose == "position":
        # «аренда момента» — модуль позиции байка (bike_position.py:259-276); pick его не зовёт (I-6, I17)
        return _pick_unknown("rental_ambiguous", ["which_rental"], [], purpose, intent,
                             ask="Цель position решает модуль позиции байка (аренда момента), а не выбор дела — "
                                 "какая аренда имеется в виду?")
    if purpose == "client":
        return _pick_client(all_rows, classified, query, intent, today, params)

    plate = _s(query.get("plate")) or None
    if purpose in ("handover", "return", "debt", "cash") and not plate:
        return _pick_unknown("no_plate", ["bike"], [], purpose, intent, ask="О каком байке речь (номер)?")
    if purpose == "handover":
        return _pick_handover(classified, plate, today, params, intent)
    if purpose in ("return", "debt"):
        # ВСЕ «в аренде» номера (B≠ON) со стартом ≤ дня момента; будущие брони и «завершена» не кандидаты
        cands = [(r, c) for r, c in classified
                 if c["plate"] == plate and _B.is_active(r)
                 and (c["start_day"] is None or _date(c["start_day"]) <= today)]
        if len(cands) > 1:
            return _pick_unknown("two_active", ["which_rental"], [_cand(r, c) for r, c in cands], purpose, intent)
        if len(cands) == 1:
            r, c = cands[0]
            if c["start_day"] is None:
                return _pick_unknown("rental_not_found", ["dates"], [_cand(r, c)], purpose, intent)
            return _found(r, c)
        return _pick_unknown("rental_not_found", ["dates"], [], purpose, intent)
    if purpose == "cash":
        return _pick_cash(classified, query, plate, params, intent)
    return _pick_contract(classified, query, plate, params, intent)


def _pick_client(all_rows, classified, query, intent, today, params):
    purpose = "client"
    pairs, err = _contact_filter(query.get("contact"), params, classified)
    if err is not None:
        return _pick_unknown(err[0], err[1], [], purpose, intent, ask=err[2])
    futures = [(r, c) for r, c in pairs if c["cls"] == "future"]
    if intent == "current":
        cands = [(r, c) for r, c in pairs if c["cls"] in ("current", "current_unactivated")]
        stale = [(r, c) for r, c in cands if c["cls"] == "current" and _stale(c, today, params)]
        if stale:
            shown = [_cand(r, c) for r, c in stale] + [_cand(r, c) for r, c in futures]
            head = "; ".join("аренда %s с %s числится незакрытой" % (c["plate"] or "?", _dm(c["start_day"]))
                             for r, c in stale)
            tail = "".join(" или о брони с %s" % _dm(c["start_day"]) for r, c in futures)
            return _pick_unknown("stale_active", ["which_rental", "intent"], shown, purpose, intent,
                                 ask="%s — вы о ней%s?" % (head, tail))
        if len(cands) == 1:
            return _found(*cands[0])
        if len(cands) > 1:
            return _pick_unknown("rental_ambiguous", ["which_rental"], [_cand(r, c) for r, c in cands], purpose,
                                 intent)
        if futures:
            ask = "Текущей аренды не нашёл; у вас бронь с %s — вы о ней?" % " / ".join(
                _dm(c["start_day"]) for r, c in futures)
            return _pick_unknown("rental_not_found", ["dates", "intent"], [_cand(r, c) for r, c in futures],
                                 purpose, intent, ask=ask)
        return _pick_unknown("rental_not_found", ["contact", "dates"], [], purpose, intent)
    if intent in ("future", "past"):
        cands = [(r, c) for r, c in pairs if c["cls"] == intent]
        if intent == "past":
            n = _known_int(_p(params, "PAST_LOOKBACK"))           # UNKNOWN → всё, что отдала дверь
            if n is not None:
                cands = [(r, c) for r, c in cands
                         if c["end_day"] is not None and (today - _date(c["end_day"])).days <= n]
        if len(cands) == 1:
            return _found(*cands[0])
        if len(cands) > 1:
            return _pick_unknown("rental_ambiguous", ["which_rental"], [_cand(r, c) for r, c in cands], purpose,
                                 intent)
        return _pick_unknown("rental_not_found", ["contact", "dates"], [], purpose, intent)
    if intent == "specific":
        return _pick_specific(all_rows, pairs, query, intent, params)
    if intent is None:
        cands = [(r, c) for r, c in pairs if c["cls"] not in ("stale_booking", "unknown")]
        if len(cands) == 1:
            r, c = cands[0]
            if c["cls"] == "current" and _stale(c, today, params):
                return _pick_unknown("stale_active", ["which_rental", "intent"], [_cand(r, c)], purpose, intent)
            return _found(r, c)
        if len(cands) > 1:
            return _pick_unknown("rental_ambiguous", ["which_rental", "intent"], [_cand(r, c) for r, c in cands],
                                 purpose, intent)
        return _pick_unknown("rental_not_found", ["contact", "dates"], [], purpose, intent)
    raise ValueError("pick: intent %r вне %r" % (intent, INTENTS))


def _pick_specific(all_rows, pairs, query, intent, params):
    """client/specific: признаки модели — только ФИЛЬТР внутри строк контакта (I-7, I36)."""
    purpose = "client"
    bk = _s(query.get("booking_id")) or None
    cdate = _date(query.get("contract_date"))
    period = query.get("period")
    q_from = q_to = None
    if period:
        q_from, q_to = _date(period[0]), _date(period[1])
    if bk is None and cdate is None and (q_from is None or q_to is None):
        return _pick_unknown("rental_ambiguous", ["which_rental", "intent"], [], purpose, intent,
                             ask="Уточните, пожалуйста, какая аренда: номер брони, даты или дата договора?")
    cands = list(pairs)
    if bk is not None:
        cands = [(r, c) for r, c in cands if _s(r.get("booking_id")) == bk]
        if not cands and any(_s(r.get("booking_id")) == bk for r in all_rows):
            # booking_id чужой строки — признак модели круг строк контакта не расширяет
            return _pick_unknown("contact", ["contact"], [], purpose, intent,
                                 ask="Эта бронь оформлена не на ваш номер — на чьё имя и какой номер она оформлена?")
    else:
        cands = [(r, c) for r, c in cands if c["cls"] != "unknown"]   # класс unknown — только по точному booking_id
    if cdate is not None:
        inside = [(r, c) for r, c in cands if c["start_day"] and c["end_day"]
                  and _date(c["start_day"]) <= cdate <= _date(c["end_day"])]
        if not inside:
            pre = _contract_pre_start(cands, cdate, params)
            if pre is not None:
                if pre.get("code") == "found":
                    return pre
                return _pick_unknown("contract_pre_start", ["which_rental"], pre["candidates"], purpose, intent,
                                     ask=pre["ask"])
        cands = inside
    if q_from is not None and q_to is not None:
        cands = [(r, c) for r, c in cands if c["start_day"] and c["end_day"]
                 and _overlaps(_date(c["start_day"]), _date(c["end_day"]), q_from, q_to)]
    if len(cands) == 1:
        return _found(*cands[0])
    if len(cands) > 1:
        return _pick_unknown("rental_ambiguous", ["which_rental"], [_cand(r, c) for r, c in cands], purpose, intent)
    return _pick_unknown("rental_not_found", ["contact", "dates"], [], purpose, intent)


def _contract_pre_start(pairs, cdate, params):
    """Договор подписан до начала аренды. CONTRACT_PRE_START_DAYS=UNKNOWN → вопрос «к брони с …?»; известен N →
    аренда, начинающаяся не позже N суток после даты договора, — кандидат. Нет таких аренд → None."""
    later = [(r, c) for r, c in pairs if c["start_day"] and _date(c["start_day"]) > cdate]
    if not later:
        return None
    n = _known_int(_p(params, "CONTRACT_PRE_START_DAYS"))
    if n is not None:
        later = [(r, c) for r, c in later if (_date(c["start_day"]) - cdate).days <= n]
        if len(later) == 1:
            return _found(*later[0])
        if not later:
            return None
    shown = [_cand(r, c) for r, c in later]
    ask = "Договор подписан до начала аренды — он к брони %s?" % " или ".join(
        "с %s (%s)" % (_dm(c["start_day"]), c["bike"] or c["plate"] or "?") for c in shown)
    return {"code": "unknown", "candidates": shown, "ask": ask}


def _pick_handover(classified, plate, today, params, intent):
    """«бронь» номера со start_day = дню момента (R2: выдача физически сейчас); HANDOVER_DAY_TOLERANCE=UNKNOWN →
    только точный день; известен N — ранняя выдача брони, начинающейся не позже N суток после дня момента."""
    purpose = "handover"
    tol = _known_int(_p(params, "HANDOVER_DAY_TOLERANCE"))
    booked = [(r, c) for r, c in classified
              if c["plate"] == plate and _B.status_of(r) == ST_BOOKED and c["start_day"] is not None]
    if tol is None:
        cands = [(r, c) for r, c in booked if _date(c["start_day"]) == today]
    else:
        cands = [(r, c) for r, c in booked if 0 <= (_date(c["start_day"]) - today).days <= tol]
    if len(cands) == 1:
        return _found(*cands[0])
    if len(cands) > 1:
        return _pick_unknown("rental_ambiguous", ["which_rental"], [_cand(r, c) for r, c in cands], purpose, intent)
    if booked:
        shown = [_cand(r, c) for r, c in booked]
        ask = "Брони этого байка на этот день нет — это ранняя выдача брони %s?" % " или ".join(
            "с %s (%s)" % (_dm(c["start_day"]), c["name"] or "?") for c in shown)
        return _pick_unknown("rental_not_found", ["dates"], shown, purpose, intent, ask=ask)
    return _pick_unknown("rental_not_found", ["dates"], [], purpose, intent)


def _pick_cash(classified, query, plate, params, intent):
    """cash — правило bind_cash (DESIGN §3.5): found только при единственном претенденте в его сроке."""
    purpose = "cash"
    cash_day = _date(query.get("cash_day"))
    fact = {"bike": plate, "at": cash_day.isoformat() if cash_day else None}
    same = [(r, c) for r, c in classified if c["plate"] == plate]
    claim = cash_claimants(fact, [r for r, c in same], params)
    pairs = [(r, c) for r, c in same if any(cl.get("row") == r.get("row") for cl in claim)]
    if len(claim) == 1 and len(pairs) == 1 and claim[0].get("branch") == "in_term":
        return _found(*pairs[0])
    if not claim:
        return _pick_unknown("cash_no_rental", ["which_rental"], [], purpose, intent)
    shown = [_cand(r, c) for r, c in pairs] or list(claim)
    reason = "which_rental"
    if len(claim) == 1 and claim[0].get("branch") in ("pre_start", "post_end"):
        reason = "cash_" + claim[0]["branch"]
    return _pick_unknown(reason, ["which_rental"], shown, purpose, intent)


def _pick_contract(classified, query, plate, params, intent):
    """Аренда договора с датой c — ПРИНАДЛЕЖНОСТЬ документа; подходит ли он к запрошенному периоду, решает
    отдельно покрытие (document_coverage / Store.documents_for, I46): дата c период не доказывает."""
    purpose = "contract"
    cdate = _date(query.get("contract_date"))
    if cdate is None:
        return _pick_unknown("rental_not_found", ["dates"], [], purpose, intent, ask="Какого числа подписан договор?")
    pairs = classified
    if query.get("contact") is not None:
        pairs, err = _contact_filter(query.get("contact"), params, classified)
        if err is not None:
            return _pick_unknown(err[0], err[1], [], purpose, intent, ask=err[2])
    if plate:
        pairs = [(r, c) for r, c in pairs if c["plate"] == plate]
    pairs = [(r, c) for r, c in pairs if c["cls"] != "unknown"]
    inside = [(r, c) for r, c in pairs if c["start_day"] and c["end_day"]
              and _date(c["start_day"]) <= cdate <= _date(c["end_day"])]
    if len(inside) == 1:
        return _found(*inside[0])
    if len(inside) > 1:
        return _pick_unknown("rental_ambiguous", ["which_rental"], [_cand(r, c) for r, c in inside], purpose, intent)
    pre = _contract_pre_start(pairs, cdate, params)
    if pre is not None:
        if pre.get("code") == "found":
            return pre
        return _pick_unknown("contract_pre_start", ["which_rental"], pre["candidates"], purpose, intent,
                             ask=pre["ask"])
    return _pick_unknown("rental_not_found", ["dates"], [], purpose, intent)


# ----------------------------------------------------------------------------------------------------------------
# Сверка привязки с новым чтением (CONTRACT §6 reconcile, DESIGN §2.3)
# ----------------------------------------------------------------------------------------------------------------


def _contact_values(binding, only_crm=False):
    """Активные контакты канала wa привязки/дела: [{"value","source_kind"}]. Строка — значение без источника."""
    out = []
    for item in (binding or {}).get("contacts") or []:
        if isinstance(item, Mapping):
            if _s(item.get("status") or "active") != "active":
                continue
            if _s(item.get("channel") or "wa") not in ("wa", "phone_crm"):
                continue
            if only_crm and _s(item.get("source_kind")) != "crm":
                continue
            value = re.sub(r"\D", "", _s(item.get("value")))
            sk = _s(item.get("source_kind"))
        else:
            if only_crm:
                continue
            value, sk = re.sub(r"\D", "", _s(item)), ""
        if value:
            out.append({"value": value, "source_kind": sk})
    return out


def _cand_identity(row):
    c = classify(row, 0.0, None)
    return {"row": row.get("row"), "booking_id": _s(row.get("booking_id")) or None, "anchor": c["anchor"],
            "plate": c["plate"], "start_day": c["start_day"], "end_day": c["end_day"], "name_norm": c["name_norm"],
            "status": _B.status_of(row)}


def cand_sha_of(rows):
    """Отпечаток НАБОРА кандидатов (не их порядка): ключ ожидания confirm_link (CONTRACT §11, ux_confirm_open)."""
    return _sha(_canon_list([_cand_identity(r) for r in rows]))


def _recon_base():
    return {"code": None, "row": None, "changes": {}, "bump_reason": None, "link_state": "ok", "link_add": [],
            "link_retire": [], "contacts_add": [], "contacts_supersede": [], "conflict_cases": [],
            "attention": False, "candidates": [], "cand_sha": None, "missing": [], "ask": "", "reason": ""}


def _binding_desc(binding):
    return "%s %s–%s" % (_s(binding.get("plate")) or "?", _dm(binding.get("start_day")), _dm(binding.get("end_day")))


def _row_desc(row):
    c = classify(row, 0.0, None)
    return "строка %s: %s %s–%s, %s, «%s»" % (row.get("row"), _s(row.get("bike")) or c["plate"] or "?",
                                              _dm(c["start_day"]), _dm(c["end_day"]), _s(row.get("name")) or "—",
                                              _s(row.get("status")))


def _recon_unknown(out, code, link_state, reason, missing, rows, ask):
    out.update(code=code, link_state=link_state, reason=reason, missing=list(missing),
               candidates=[_cand_identity(r) for r in rows], cand_sha=cand_sha_of(rows), ask=ask)
    return out


def _status_drift(old, row, binding):
    """Смена статуса: штатная (бронь → в аренде → завершена при ступени 5 возврата) или status_drift."""
    new = _B.status_of(row)
    if new == old:
        return False
    if not new or _B.is_manual(row) or (new == ST_RENTED and _auto_cancel_on(row)):
        return True                                               # рукописный / неизвестный: смысл не придумывается
    if new == ST_DONE:
        return not bool(binding.get("return_stage5"))            # «Завершена» без ступени 5 задачи возврата
    if old == ST_BOOKED and new == ST_RENTED:
        return False
    return True                                                   # прочие (в т. ч. обратные) смены


def _period_conflicts(binding, row, new_s, new_e, others, rows):
    """Пересечение нового срока с другой незавершённой строкой/привязкой того же номера (I-21). Строгое по дням:
    возврат и выдача в один день пересечением не считаются (толкование, см. contract_deviations)."""
    plate = plate_of_row(row)
    cases, hit = [], False
    if new_s is None or new_e is None:
        return hit, cases
    for o in others or []:
        if _s(o.get("case_id")) and _s(o.get("case_id")) == _s(binding.get("case_id")):
            continue
        if _s(o.get("plate")) != _s(plate):
            continue
        os_, oe = _date(o.get("start_day")), _date(o.get("end_day"))
        if _s(o.get("status_seen")).lower() == ST_DONE or os_ is None or oe is None:
            continue
        if os_ < new_e and new_s < oe:
            hit = True
            if _s(o.get("case_id")) and o.get("case_id") not in cases:
                cases.append(o.get("case_id"))
    for r in rows or []:
        if r is row or plate_of_row(r) != plate or _B.status_of(r) == ST_DONE:
            continue
        if _s(r.get("booking_id")) and _s(r.get("booking_id")) == _s(row.get("booking_id")):
            continue
        rs, re_ = _date(r.get("date_start")), _date(r.get("date_end"))
        if rs is not None and re_ is not None and rs < new_e and new_s < re_:
            hit = True
    return hit, cases


def _contacts_diff(binding, row, params):
    kd = _known_int(_p(params, "KEY_DIGITS")) or 9
    row_nums = phones_full(row.get("contacts"))
    row_keys = set(n[-kd:] for n in row_nums if len(n) >= kd)
    have = _contact_values(binding)
    have_keys = set(c["value"][-kd:] for c in have if len(c["value"]) >= kd)
    crm = _contact_values(binding, only_crm=True)
    add = [n for n in row_nums if len(n) >= kd and n[-kd:] not in have_keys]
    sup = [c["value"] for c in crm if c["value"][-kd:] not in row_keys]
    replaced = bool(crm) and bool(row_keys) and len(sup) == len(crm)       # номера U заменены целиком
    return add, sup, replaced


def _apply_same_row(out, binding, row, rows, others, params, check_names):
    """Одна строка совпала (по booking_id или якорю): поля → same/changed/drift/ambiguous."""
    c = classify(row, 0.0, None)
    changes = {}
    old = {"plate": _s(binding.get("plate")) or None, "start_day": _iso(binding.get("start_day")),
           "end_day": _iso(binding.get("end_day")), "name_norm": binding.get("name_norm")}
    if old["name_norm"] is None and binding.get("name_seen") is not None:
        old["name_norm"] = name_norm(binding.get("name_seen"))
    new = {"plate": c["plate"], "start_day": c["start_day"], "end_day": c["end_day"], "name_norm": c["name_norm"]}
    hard = 0                                                      # смена значения (не заполнение пустого)
    for key in ("plate", "start_day", "end_day", "name_norm"):
        if old[key] != new[key]:
            changes[key] = {"old": old[key], "new": new[key]}
            if key != "end_day" and old[key] is not None and new[key] is not None:
                hard += 1
    name_changed = (check_names and old["name_norm"] is not None and new["name_norm"] != old["name_norm"])
    add, sup, replaced = _contacts_diff(binding, row, params)
    if name_changed or hard >= 2 or replaced:
        why = "drift_name" if name_changed else ("drift_contacts" if replaced and hard < 2 else "drift_fields")
        out["changes"] = changes
        return _recon_unknown(out, "drift", "drift", why, ["link_confirmation"], [row],
                              "Строка изменилась сильнее одной правки (%s) — это та же аренда, что у дела (%s)?"
                              % (_row_desc(row), _binding_desc(binding)))
    for key, col in (("start_at", "date_start"), ("end_at", "date_end")):
        if _s(binding.get(key)) and _s(binding.get(key)) != _s(row.get(col)):
            changes[key] = {"old": binding.get(key), "new": row.get(col)}
    old_status = _s(binding.get("status_seen")).lower()
    new_status = _B.status_of(row)
    drift_status = False
    if old_status != new_status:
        changes["status_seen"] = {"old": binding.get("status_seen"), "new": row.get("status")}
        drift_status = _status_drift(old_status, row, binding)
    if row.get("row") is not None and binding.get("crm_row_seen") != row.get("row"):
        changes["crm_row_seen"] = {"old": binding.get("crm_row_seen"), "new": row.get("row")}
    period = any(k in changes for k in ("start_day", "end_day"))
    if period:
        hit, cases = _period_conflicts(binding, row, _date(new["start_day"]), _date(new["end_day"]), others, rows)
        if hit:
            out.update(changes=changes, attention=True, conflict_cases=cases)
            return _recon_unknown(out, "ambiguous", "ambiguous", "which_rental", ["which_rental"], [row],
                                  "Новый срок аренды (%s) пересекает другую незавершённую аренду того же байка — "
                                  "какая аренда действует (RENTAL_CONFLICT_RULE не принят)?" % _row_desc(row))
    if "plate" in changes:
        out["bump_reason"] = "bike_changed"
    elif period:
        out["bump_reason"] = "period_changed"
    elif drift_status:
        out["bump_reason"] = "status_drift"
    out["attention"] = bool(drift_status)
    old_anchor = binding.get("anchor")
    if old_anchor is None and old["plate"] and old["start_day"] and old["name_norm"]:
        old_anchor = "%s|%s|%s" % (old["plate"], old["start_day"], old["name_norm"])
    new_anchor = c["anchor"]
    if old_anchor != new_anchor:
        if old_anchor:
            out["link_retire"].append({"kind": "anchor", "value": old_anchor})
        if new_anchor:
            out["link_add"].append({"kind": "anchor", "value": new_anchor})
    out["contacts_add"] = add
    out["contacts_supersede"] = sup
    out["changes"] = changes
    out["row"] = row
    any_change = bool(changes or out["link_add"] or out["link_retire"] or add or sup)
    out["code"] = "changed" if any_change else "same"
    return out


def reconcile(binding: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], observed_at: float,
              others: Sequence[Mapping[str, Any]], params: Mapping[str, Any]) -> Dict[str, Any]:
    """Сверка привязки с новым чтением по таблице DESIGN §2.3. Ничего не пишет.

    binding — текущая привязка дела (колонки rc_rental) + "case_id", "anchor", "contacts" (активные контакты дела:
    [{"channel","value","status","source_kind"}]) и "return_stage5" (записана ли ступень 5 задачи возврата);
    others — привязки других открытых дел того же номера и дела, у которых подтверждён booking_id строки
    ({"case_id","booking_id","plate","start_day","end_day","status_seen"})."""
    out = _recon_base()
    binding = binding or {}
    rows = [r for r in (rows or []) if isinstance(r, Mapping)]
    prev = _known_num(binding.get("observed_at"))
    if prev is not None and (observed_at is None or float(observed_at) <= float(prev)):
        out.update(code="stale", reason="stale_read")             # I30: не новее применённого — ничего не меняет
        return out
    bk = _s(binding.get("booking_id")) or None
    if bk is not None:
        hits = [r for r in rows if _s(r.get("booking_id")) == bk]
        if not hits:
            return _recon_unknown(out, "not_found", "missing", "rental_not_found", ["contact", "dates"], [],
                                  "Брони дела (%s) в листе больше нет — она удалена, перенесена или это другая "
                                  "строка?" % _binding_desc(binding))
        if len(hits) > 1:
            return _recon_unknown(out, "ambiguous", "ambiguous", "rental_ambiguous", ["which_rental"], hits,
                                  "Номер брони дела найден в нескольких строках (%s) — какая из них настоящая?"
                                  % "; ".join(_row_desc(r) for r in hits))
        return _apply_same_row(out, binding, hits[0], rows, others, params, check_names=True)
    anchor = binding.get("anchor")
    if not anchor:
        plate, start = _s(binding.get("plate")), _iso(binding.get("start_day"))
        nm = binding.get("name_norm")
        anchor = "%s|%s|%s" % (plate, start, nm) if plate and start and nm else None
    hits = [r for r in rows if anchor and anchor_of(r) == anchor]
    if len(hits) > 1:
        return _recon_unknown(out, "ambiguous", "ambiguous", "rental_ambiguous", ["which_rental"], hits,
                              "Байк, день и имя дела совпали с несколькими строками (%s) — какая из них?"
                              % "; ".join(_row_desc(r) for r in hits))
    if len(hits) == 1:
        row = hits[0]
        y = _s(row.get("booking_id")) or None
        if y is not None:
            taken = [o for o in (others or []) if _s(o.get("booking_id")) == y
                     and _s(o.get("case_id")) != _s(binding.get("case_id"))]
            if taken:
                out["conflict_cases"] = [x for x in [binding.get("case_id")] + [o.get("case_id") for o in taken] if x]
                return _recon_unknown(out, "drift", "drift", "link_drift", ["link_confirmation"], [row],
                                      "В строке дела появился номер брони, уже подтверждённый за другим делом (%s) "
                                      "— это одна аренда или разные?" % _row_desc(row))
        res = _apply_same_row(out, dict(binding, anchor=anchor), row, rows, others, params, check_names=True)
        if res["code"] in ("same", "changed") and y is not None:
            res["link_add"].append({"kind": "booking_id", "value": y})
            res["code"] = "changed"
        return res
    # якорь не совпал: строки, совпавшие 2 из 3 (другой байк / другой день / другое имя) → drift
    plate, start, nm = _s(binding.get("plate")) or None, _iso(binding.get("start_day")), binding.get("name_norm")
    near = []
    for r in rows:
        c = classify(r, 0.0, None)
        same = sum(1 for a, b in ((plate, c["plate"]), (start, c["start_day"]), (nm, c["name_norm"]))
                   if a is not None and a == b)
        if same == 2:
            near.append(r)
    if near:
        return _recon_unknown(out, "drift", "drift", "link_drift", ["link_confirmation"], near,
                              "Строка дела (%s) не найдена как была; похожие: %s — это та же аренда?"
                              % (_binding_desc(binding), "; ".join(_row_desc(r) for r in near)))
    return _recon_unknown(out, "not_found", "missing", "rental_not_found", ["contact", "dates"], [],
                          "Строки дела (%s) в листе не нашёл — где теперь эта аренда?" % _binding_desc(binding))


# ----------------------------------------------------------------------------------------------------------------
# Продолжение аренды новой строкой (CONTRACT §6 continuation, DESIGN §2.4)
# ----------------------------------------------------------------------------------------------------------------


def continuation(new_row: Mapping[str, Any], open_bindings: Sequence[Mapping[str, Any]],
                 params: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """[{case_id, why, gap_days}] — открытые дела, продолжением которых может быть новая строка.

    Совпадение: активный контакт дела match с U новой строки ИЛИ равный name_norm (не заглушка). Разрыв = start_day
    новой − end_day прежней в сутках (< 0 — пересечение, 0 — касание днём возврата). Кандидат ⇔ разрыв ≤ N, где N =
    CONTINUATION_GAP_DAYS, а при UNKNOWN N = 0: касание — сомнение при неизвестном параметре (why =
    "param_unknown:CONTINUATION_GAP_DAYS"), пересечение — why="overlap"; дата не известна — why="dates_unknown"."""
    new_row = new_row or {}
    kd = _known_int(_p(params, "KEY_DIGITS")) or 9
    gap_param = _known_int(_p(params, "CONTINUATION_GAP_DAYS"))
    limit = gap_param if gap_param is not None else 0
    nm = name_norm(new_row.get("name"))
    ns = _date(new_row.get("date_start"))
    nbk = _s(new_row.get("booking_id")) or None
    nanchor = anchor_of(new_row)
    out = []
    for b in open_bindings or []:
        if nbk is not None and _s(b.get("booking_id")) == nbk:
            continue                                              # та же бронь — не продолжение, а сверка
        if nanchor is not None and b.get("anchor") == nanchor:
            continue
        contact_hit = any(contact_match(new_row.get("contacts"), c["value"], kd) == "match"
                          for c in _contact_values(b))
        b_nm = b.get("name_norm") if b.get("name_norm") is not None else name_norm(b.get("name_seen"))
        if not (contact_hit or (nm is not None and nm == b_nm)):
            continue
        be = _date(b.get("end_day"))
        if ns is None or be is None:
            out.append({"case_id": b.get("case_id"), "why": "dates_unknown", "gap_days": None})
            continue
        gap = (ns - be).days
        if gap > limit:
            continue                                              # разрыв ≥ 1 при UNKNOWN — near_cases, не кандидат
        if gap < 0:
            why = "overlap"
        elif gap_param is None:
            why = "param_unknown:CONTINUATION_GAP_DAYS"
        else:
            why = "gap_within_param"
        out.append({"case_id": b.get("case_id"), "why": why, "gap_days": gap})
    return out


# ----------------------------------------------------------------------------------------------------------------
# Касса: претенденты и единственная привязка (CONTRACT §6 cash_claimants/bind_cash, DESIGN §3.5)
# ----------------------------------------------------------------------------------------------------------------


def _cash_day(cash_fact, params):
    at = (cash_fact or {}).get("at")
    if _known_num(at) is not None:
        return day_of_moment(at, _known_int(_p(params, "TZ_H")) or 0)
    return _date(str(at or "")[:10]) if at else None     # как cash_of_rental (wa_agent_tools.py:543)


def cash_claimants(cash_fact: Mapping[str, Any], same_plate_rows: Sequence[Mapping[str, Any]],
                   params: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Строки номера, притязающие на строку кассы по любой ветке: в сроке («in_term»); до начала незавершённой
    строки («pre_start»: CASH_PRE_START_DAYS=UNKNOWN — любая, известен N — не дальше N суток); после конца
    незавершённой строки («post_end», CASH_POST_END_DAYS так же). «Завершена» — только в сроке. День кассы или
    даты строки не известны — притязает («day_unknown»/«dates_unknown», fail-closed)."""
    d = _cash_day(cash_fact, params)
    cplate = _T.plate_of((cash_fact or {}).get("bike")) or None
    pre_n = _known_int(_p(params, "CASH_PRE_START_DAYS"))
    post_n = _known_int(_p(params, "CASH_POST_END_DAYS"))
    out = []
    for row in same_plate_rows or []:
        if not isinstance(row, Mapping):
            continue
        rp = plate_of_row(row)
        if cplate is not None and rp != cplate:
            continue
        done = _B.status_of(row) == ST_DONE
        sd, ed = _date(row.get("date_start")), _date(row.get("date_end"))
        if d is None:
            branch = "day_unknown"
        elif sd is None or ed is None:
            branch = "dates_unknown"
        elif sd <= d <= ed:
            branch = "in_term"
        elif done:
            continue
        elif d < sd:
            if pre_n is not None and (sd - d).days > pre_n:
                continue
            branch = "pre_start"
        else:
            if post_n is not None and (d - ed).days > post_n:
                continue
            branch = "post_end"
        out.append({"row": row.get("row"), "booking_id": _s(row.get("booking_id")) or None, "plate": rp,
                    "bike": _s(row.get("bike")), "name": _s(row.get("name")), "status": _s(row.get("status")),
                    "start_day": sd.isoformat() if sd else None, "end_day": ed.isoformat() if ed else None,
                    "branch": branch})
    return out


def _multi_move(cash_fact):
    """Многодвижительное сообщение: одна запись кассы из сообщения с несколькими движениями (роль решается текстом
    всего сообщения, VERIFY_cash_contract У1). Признак кладёт вызывающий: multi_move=True или moves>1."""
    if (cash_fact or {}).get("multi_move") is True:
        return True
    moves = _known_int((cash_fact or {}).get("moves"))
    if moves is not None and moves > 1:
        return True
    role = (cash_fact or {}).get("role")
    return isinstance(role, (list, tuple, set, frozenset)) and len(role) != 1


def _is_rental_claim(cl, rental):
    rbk = _s(rental.get("booking_id")) or None
    if rbk is not None and cl.get("booking_id") is not None:
        return cl["booking_id"] == rbk
    if rental.get("crm_row_seen") is not None and cl.get("row") is not None:
        return cl["row"] == rental.get("crm_row_seen")
    return (cl.get("plate") == (_s(rental.get("plate")) or None) and cl.get("start_day") == _iso(rental.get("start_day"))
            and cl.get("end_day") == _iso(rental.get("end_day")))


def _bind_out(code, bound_by=None, reason="", claimants=(), missing=(), ask=""):
    return {"code": code, "bound_by": bound_by, "reason": reason, "claimants": list(claimants),
            "missing": list(missing), "ask": ask}


def bind_cash(cash_fact: Mapping[str, Any], rental: Mapping[str, Any], same_plate_rows: Sequence[Mapping[str, Any]],
              params: Mapping[str, Any], human: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """{"code": "bound"|"unbound"|"unknown", "bound_by", "reason", "claimants", "missing", "ask"} — DESIGN §3.5.

    rental — привязка дела (booking_id, plate, start_day, end_day, crm_row_seen); same_plate_rows — ВСЕ строки
    номера из полного чтения (с будущими бронями). Касса не привязывается по одному полю (I18, I35)."""
    cash_fact = cash_fact or {}
    rental = rental or {}
    if human and human.get("bind") is True:
        return _bind_out("bound", "human")                        # одобряющего по id проверяет Store (S-m3)
    if _multi_move(cash_fact) and is_unknown(_p(params, "CASH_ROLE_MULTI_MOVE")):
        return _bind_out("unknown", None, "role_unknown", (), ["CASH_ROLE_MULTI_MOVE"],
                         "В одном сообщении кассы несколько движений — к какой роли (аренда, залог, возврат) "
                         "относится эта строка?")
    d = _cash_day(cash_fact, params)
    cplate = _T.plate_of(cash_fact.get("bike")) or None
    rplate = _s(rental.get("plate")) or None
    rs, re_ = _date(rental.get("start_day")), _date(rental.get("end_day"))
    in_term = d is not None and rs is not None and re_ is not None and rs <= d <= re_
    same_plate = cplate is not None and cplate == rplate
    cb = _s(cash_fact.get("booking_id")) or None
    if cb is not None:
        if cb == (_s(rental.get("booking_id")) or None):
            if same_plate and in_term:
                return _bind_out("bound", "booking_id")
            if same_plate and d is not None and rs is not None and d < rs:
                return _bind_out("unknown", None, "cash_pre_start", (), ["which_rental"],
                                 "Касса с номером брони дела пришла до начала аренды (%s) — это предоплата этой "
                                 "брони?" % _dm(rs))
            if same_plate and d is not None and re_ is not None and d > re_:
                return _bind_out("unknown", None, "cash_post_end", (), ["which_rental"],
                                 "Касса с номером брони дела пришла после конца аренды (%s) — она к этой аренде?"
                                 % _dm(re_))
            return _bind_out("unknown", None, "link_confirmation", (), ["link_confirmation"],
                             "Номер брони в кассе — дела, но байк или день не сходятся (касса: %s, %s; аренда: %s "
                             "%s–%s) — к какой аренде строка?" % (cplate or "?", _dm(d), rplate or "?", _dm(rs),
                                                                 _dm(re_)))
        if same_plate and in_term:
            return _bind_out("unknown", None, "link_confirmation", (), ["link_confirmation"],
                             "Касса несёт номер другой брони, но байк и день — внутри аренды дела (%s–%s) — к какой "
                             "аренде строка?" % (_dm(rs), _dm(re_)))
        return _bind_out("unbound", None, "cash_other_booking")
    if cplate is None:
        return _bind_out("unknown", None, "which_rental", (), ["which_rental"],
                         "В строке кассы не разобран номер байка — к какой аренде она относится?")
    if not same_plate:
        return _bind_out("unbound", None, "cash_other_booking")
    claim = cash_claimants(cash_fact, same_plate_rows, params)
    mine = [cl for cl in claim if _is_rental_claim(cl, rental)]
    if not mine and in_term:
        mine = [{"row": rental.get("crm_row_seen"), "booking_id": _s(rental.get("booking_id")) or None,
                 "plate": rplate, "bike": "", "name": _s(rental.get("name_seen")), "status": _s(rental.get("status_seen")),
                 "start_day": _iso(rs), "end_day": _iso(re_), "branch": "in_term"}]
        claim = mine + claim
    others = [cl for cl in claim if not any(cl is m for m in mine)]
    if len(mine) == 1 and not others:
        branch = mine[0]["branch"]
        if branch == "in_term":
            return _bind_out("bound", "plate+day", "", claim)
        if branch in ("pre_start", "post_end"):
            return _bind_out("unknown", None, "cash_" + branch, claim, ["which_rental"],
                             ask_for([dict(c, cls=None) for c in claim], "cash", None))
    if not claim:
        return _bind_out("unknown", None, "cash_no_rental", (), ["which_rental"], ask_for([], "cash", None))
    return _bind_out("unknown", None, "which_rental", claim, ["which_rental"],
                     ask_for([dict(c, cls=None) for c in claim], "cash", None))


# ----------------------------------------------------------------------------------------------------------------
# Слова «да/нет» (CONTRACT §4.8, DESIGN §6.6)
# ----------------------------------------------------------------------------------------------------------------


def _words(text):
    return re.findall(r"[a-zа-я0-9]+", str(text or "").lower().replace("ё", "е"))


def _seq(value):
    if is_unknown(value) or value is None:
        return None
    if isinstance(value, str):
        return (value,)
    return tuple(str(v).lower().replace("ё", "е") for v in value)


# APPROVEFIX1610: основа согласия засчитывается согласием только с окончанием повелительного наклонения или «я/мы»
# настоящего времени («подтверждаю», «завершай», «заверши», «завершаем», «ставьте»). «подтверждено», «завершена»,
# «завершу» — не согласие (сообщение о состоянии, вопрос, обещание сделать руками), а неясный ответ.
APPROVAL_YES_ENDINGS = ("", "те", "ай", "айте", "и", "ите", "аю", "аем")
# Глагол ЧУЖОГО действия согласием этой карточки не является: «активируй» реплаем на карточку закрытия, «завершай» — на
# карточку выдачи или брони — вероятный промах адреса, а не «да» (тот же словарь у строгой ветки 4/5 Splinter:
# intake_confirm.ACTIVATE_CONSENT / CLOSE_CONSENT). Без действия (action=None) — прежний набор основ.
APPROVAL_FOREIGN_STEMS = {"booking": ("заверш", "закрывай", "активируй"), "activate": ("заверш", "закрывай"),
                          "close": ("активируй",)}
# APPROVEFIX1610 (остаток 2 приёмки 8bfcfa3): отказ словами К4 не уже, чем у строгой ветки Splinter — тот же словарь
# `intake_confirm` (одно определение на обе ветки): слова отказа ЦЕЛИКОМ («нет», «неа», «no», «nope», «нельзя», «стоп»,
# «stop», «cancel») и основы («отмен», «отклон») сверх параметра APPROVAL_NO_STEMS. Только в сторону отказа: «стоп»
# реплаем на карточку прежде был «неясным», и карточка оставалась ждать «да».
APPROVAL_NO_WORDS = _IC.REFUSE_WORDS
APPROVAL_NO_FLOOR_STEMS = _IC.REFUSE_STEMS

# APPROVEFIX-K4COMPAT1810 (Codex TB-OWNER-CHECK-1710-2356 п.4, К4 «г»): окно выкладки. Старый процесс splinter держит в
# памяти intake_confirm a24a2904 (13b4188 = 5685e53), где нет km_arg, calm_rest и is_edit_word, а этот модуль берёт с
# диска лениво — первым сообщением ветки К4. Без запаса «да» с хранилищем падало AttributeError, а без хранилища вместо
# подсказки было молчание (находка 4). Есть имя у intake_confirm — зовётся оно (новый процесс: тот же вызов, поведение то
# же); нет имени — локальный двойник с тем же телом. km_arg перенесён дословно, константы — те же значения, что в
# intake_confirm 3b78174. calm_rest и is_edit_word — те же строки над `_residue_ok`, `_TOKEN` и `_is_edit`: в a24a2904 и
# 3b78174 они совпадают дословно вместе со словарями.
_KM_DIGITS_MIN, _KM_DIGITS_MAX = 2, 7                       # = intake_confirm.KM_DIGITS_MIN, KM_DIGITS_MAX
_KM_SEP = "    "                             # = intake_confirm._KM_SEP (пробел, неразрывный, узкий, тонкий)
_KM_NUMBER = r"(?<![0-9])(?:[0-9]{1,3}(?:[" + _KM_SEP + r"][0-9]{3})+|[0-9]+)(?![0-9])"   # = intake_confirm._NUMBER


def _km_arg_local(text):
    """Двойник intake_confirm.km_arg (3b78174) — для старого модуля в памяти процесса."""
    s = str(text or "")
    found = list(re.finditer(_KM_NUMBER, s))
    if len(found) != 1:
        return None, s
    m = found[0]
    digits = "".join(ch for ch in m.group(0) if ch.isdigit())
    if not (_KM_DIGITS_MIN <= len(digits) <= _KM_DIGITS_MAX):
        return None, s
    return digits, s[:m.start()] + " " + s[m.end():]


def _calm_rest_local(text):
    """Двойник intake_confirm.calm_rest (3b78174)."""
    s = str(text or "").lower().replace("ё", "е")
    return _IC._residue_ok(s, list(re.finditer(_IC._TOKEN, s)))


def _is_edit_word_local(w):
    """Двойник intake_confirm.is_edit_word (3b78174)."""
    return _IC._is_edit(str(w or "").lower().replace("ё", "е"))


def _ic(name, local):
    """Функция intake_confirm, если она у модуля есть; иначе — локальный двойник (старый модуль в памяти процесса)."""
    f = getattr(_IC, name, None)
    return local if f is None else f


def approval_decision(text: str, params: Mapping[str, Any], action: Optional[str] = None) -> str:
    """"yes" | "no" | "unclear". Отказ первым: слово с основы APPROVAL_NO_STEMS, слово отказа APPROVAL_NO_WORDS целиком
    или с основы APPROVAL_NO_FLOOR_STEMS (словарь intake_confirm, остаток 2 APPROVEFIX1610); «не» + слово с основы
    APPROVAL_NO_AFTER_NE; «не» + слово согласия (литералы splinter.py:11686, 11739, 11756, 11781, 11797, 11802; У1).

    Согласие — строго (APPROVEFIX1610, Codex TB-OWNER-EFFICIENCY-1610-2054, карта М4/М5): нет знака вопроса, нет слова
    правки, КАЖДОЕ слово — слово APPROVAL_YES_WORDS или основа APPROVAL_YES_STEMS с окончанием APPROVAL_YES_ENDINGS
    (основа чужого действия — APPROVAL_FOREIGN_STEMS — не в счёт), а всё прочее — спокойные знаки (тот же белый
    список, что у строгой брони intake_confirm). Число на карточке брони и выдачи согласием не является; у закрытия
    ровно одно число целиком — аргумент пробега сдачи (`intake_confirm.km_arg`). Без действия (action=None — его не
    знает вызывающий: Store._judge_answer, ответ без реплая) один целый аргумент тоже допускается — прежний голден
    §4.8 «да 35200»; исполнение при этом решает answer_verdict, который действие карточки знает и передаёт.
    «завершена?», «заверши руками», «да, но поправь пробег», «да?», «да, я позвоню клиенту», «ок, позже»,
    «да 35200» на бронь/выдачу — unclear. Иначе unclear."""
    words = _words(text)
    yes_words = _seq(_p(params, "APPROVAL_YES_WORDS")) or ()
    yes_stems = _seq(_p(params, "APPROVAL_YES_STEMS")) or ()
    no_stems = _seq(_p(params, "APPROVAL_NO_STEMS")) or ()
    no_after_ne = _seq(_p(params, "APPROVAL_NO_AFTER_NE")) or ()

    def is_yes(w):
        return w in yes_words or any(w.startswith(s) for s in yes_stems)

    foreign = APPROVAL_FOREIGN_STEMS.get(action or "", ())

    def is_yes_form(w):
        return w in yes_words or any(w.startswith(s) and w[len(s):] in APPROVAL_YES_ENDINGS and s not in foreign
                                     for s in yes_stems)

    for i, w in enumerate(words):
        if (w in APPROVAL_NO_WORDS or any(w.startswith(s) for s in no_stems)
                or w.startswith(APPROVAL_NO_FLOOR_STEMS)):
            return "no"
        if w == "не" and i + 1 < len(words):
            nxt = words[i + 1]
            if any(nxt.startswith(s) for s in no_after_ne) or is_yes(nxt):
                return "no"
    if not any(is_yes(w) for w in words):
        return "unclear"
    low = str(text or "").lower().replace("ё", "е")
    if any(q in low for q in _IC.QUESTION_MARKS) or any(_ic("is_edit_word", _is_edit_word_local)(w) for w in words):
        return "unclear"
    rest = low
    if action in (None, "close"):
        _km, rest = _ic("km_arg", _km_arg_local)(low)
    rest_words = _words(rest)
    if not rest_words or not all(is_yes_form(w) for w in rest_words) or not _ic("calm_rest", _calm_rest_local)(rest):
        return "unclear"
    return "yes"


def approval_km(text: str, params: Mapping[str, Any]) -> Optional[str]:
    """Пробег сдачи из ответа на карточку закрытия (APPROVEFIX1610, М6): только если весь ответ — согласие
    (approval_decision(…, action="close") == "yes") и в нём ровно одно число целиком. Иначе None — пробег берётся из
    карточки (проверенное поле), а не «первое число в тексте»."""
    if approval_decision(text, params, action="close") != "yes":
        return None
    km, _rest = _ic("km_arg", _km_arg_local)(str(text or "").lower().replace("ё", "е"))
    return km


def accept_decision(text: str, params: Mapping[str, Any]) -> str:
    """«Принял» сотрудника (ступень 3, DESIGN §6.4): ACCEPT_WORDS=UNKNOWN → всегда unclear; ACCEPT_NO_STEMS=UNKNOWN
    при известных словах → unclear (отказ первым проверить нечем); иначе отказ первым (основа ACCEPT_NO_STEMS или «не»
    + слово либо фраза согласия), затем слово согласия (равно слову ACCEPT_WORDS; фраза из нескольких слов — подряд)."""
    accept = _seq(_p(params, "ACCEPT_WORDS"))
    no_stems = _seq(_p(params, "ACCEPT_NO_STEMS"))
    if accept is None or no_stems is None:
        return "unclear"
    words = _words(text)
    joined = " " + " ".join(words) + " "
    singles = tuple(a for a in accept if " " not in a.strip())
    phrases = tuple(" ".join(_words(a)) for a in accept if " " in a.strip())
    for i, w in enumerate(words):
        if any(w.startswith(s) for s in no_stems):
            return "no"
        if w == "не" and i + 1 < len(words) and words[i + 1] in singles:
            return "no"
        if w == "не" and any(p and (" ".join(words[i + 1:]) + " ").startswith(p + " ") for p in phrases):
            return "no"                                   # К4 круг 4: «не» перед фразой согласия — тоже отказ
    if any(w in singles for w in words) or any(p and (" " + p + " ") in joined for p in phrases):
        return "yes"
    return "unclear"


# ----------------------------------------------------------------------------------------------------------------
# Вердикт ответа (CONTRACT §4.7)
# ----------------------------------------------------------------------------------------------------------------

_LIVE_EXPECT = ("waiting", "escalating", "escalated", "escalation_unknown")


def _addressees(post):
    raw = (post or {}).get("addressee_ids")
    if is_unknown(raw) or raw is None:
        return None
    return _as_id_set(raw)


def answer_verdict(exp: Mapping[str, Any], case: Optional[Mapping[str, Any]], post: Optional[Mapping[str, Any]],
                   answer: Mapping[str, Any], params: Mapping[str, Any]) -> str:
    """Вердикт по CONTRACT §4.7 (порядок проверок; первая неудача — исход).

    exp — строка rc_expect (kind, action, state, case_ver, claim_boot); case — {"ver","link_state","plate"
    (номер текущей привязки), "confirm_open" (открыт ли confirm_link дела)} или None у approval/booking без дела;
    post — строка rc_post поста reply_to (None — пост не найден); answer — {"chat","msg_id","reply_to","thread_id",
    "author_id","text","at","is_bot", "boot_id" (boot_id принимающего Store — граница запуска п.9)}.
    Отказы шагов 1–2 отдаются строками "not_reply"/"not_linked" (без записи); шаг 3 (повтор) и сироту решает Store.
    "reference_no_reply" — «да» без реплая при APPROVAL_REPLY_REQUIRED=UNKNOWN (адресацию к ждущей карточке делает
    Store, exp — эта карточка)."""
    exp = exp or {}
    answer = answer or {}
    kind = _s(exp.get("kind"))
    text = answer.get("text")
    act = _s(exp.get("action")) or None          # APPROVEFIX1610: слова судятся по действию карточки
    # 1. бот, пустой текст, нет reply_to
    if answer.get("is_bot") or not _s(text):
        return "not_reply"
    reply_to = _s(answer.get("reply_to"))
    if not reply_to:
        if kind != "approval":
            return "not_reply"
        rule = _p(params, "APPROVAL_REPLY_REQUIRED")
        if rule is True:
            return "not_reply"
        if is_unknown(rule) or rule is not False:
            return "reference_no_reply" if approval_decision(text, params, action=act) != "unclear" else "not_reply"
        # False: адресация кандидата к карточке — дальше шаги 3–11 (поста реплая нет — проверки места пропускаются)
    elif post is None:
        return "not_linked"                       # 2. сироту при flight_unknown/escalation_unknown решает Store
    # 4. состояние ожидания
    state = _s(exp.get("state"))
    if state == "superseded":
        return "reference_superseded"
    if state == "cancelled":
        return "reference_cancelled"
    if state == "answered":
        return "reference_answered"
    if state not in _LIVE_EXPECT:
        return "not_linked"                       # planned/in_flight/flight_unknown: поста у ожидания ещё нет
    place = _s((post or {}).get("place"))
    case = case or {}
    # 5. место поста вопроса: тема и номер байка темы
    if kind == "staff_question" and place in ("topic", "delivery"):
        if _s(answer.get("thread_id")) != _s(post.get("thread_id")):
            return "reference_foreign_place"
        if post.get("topic_bike") is None or _s(post.get("topic_bike")) != _s(case.get("plate")):
            return "reference_foreign_place"
    # 6. дрейф привязки
    if place in ("topic", "delivery") and (_s(case.get("link_state")) != "ok" or bool(case.get("confirm_open"))):
        return "reference_drift"
    # 7. автор — по числовому id адресатов поста; у approval/confirm_link адресаты — APPROVER_IDS (I9)
    author = answer.get("author_id")
    if kind in ("approval", "confirm_link"):
        ids = _as_id_set(_p(params, "APPROVER_IDS"))
        if ids is None:
            return "reference_author_unverified"
    else:
        if post is not None and is_unknown(post.get("addressee_ids")):
            return "reference_author_unverified"
        ids = _addressees(post)
        if ids is None:
            return "reference_author_unverified"
    if not _is_int_id(author) or author not in ids:
        return "reference_foreign_author"
    # 8. версия дела
    if exp.get("case_ver") is not None and case.get("ver") is not None and exp.get("case_ver") != case.get("ver"):
        return "reference_stale_version"
    # 9. срок — время Telegram
    at, post_at = _known_num(answer.get("at")), _known_num((post or {}).get("at"))
    age = (at - post_at) if at is not None and post_at is not None else None
    approval_late = False
    if kind == "approval":
        ttl = _sub(_p(params, "APPROVAL_TTL_S"), _s(exp.get("action")))
        if _known_num(ttl) is not None:
            approval_late = age is not None and age > ttl
        elif _s(exp.get("action")) == "booking":
            # срока у карточки брони нет (splinter.py:11682-11683): годна только в запуске, опубликовавшем её
            if _s(exp.get("claim_boot")) == "" or _s(exp.get("claim_boot")) != _s(answer.get("boot_id")):
                return "reference_restart"
    if approval_late:
        return "reference_late"
    answer_ttl = _known_num(_p(params, "ANSWER_TTL"))
    if answer_ttl is not None and age is not None and age > answer_ttl:
        return "reference_expired"
    # 10. слова решения
    if kind in ("approval", "confirm_link") and approval_decision(text, params, action=act) == "unclear":
        return "reference_unclear"
    return "accepted"


# ----------------------------------------------------------------------------------------------------------------
# Свидетельство ступени (CONTRACT §3.6, DESIGN §7.1)
# ----------------------------------------------------------------------------------------------------------------

_KIND_STAGES = {"post": (1,), "answer": (2,), "staff_accept_reply": (3,), "human_mark": (3, 4), "topic_event": (4,),
                "crm_status_read": (5,), "readback": (5,), "wa_delivery": (6,)}
_FORBIDDEN_4_5 = ("staff_answer", "approval_yes", "agent_text", "bike_state")      # I10, I44


def evidence_kind(evidence: Any) -> str:
    """Вид свидетельства — ТОЧНОЕ слово перечня §3.6: строка как есть, без обрезки пробелов и смены регистра. Значение
    не строкой (и подклассом строки) — "": свидетельством никакого вида оно не является. Одно определение на правило
    и на Store (К4 круг 4, §16.10 д): прежде правило обрезало пробелы, а Store сравнивал вид как есть — вид
    «human_mark » проходил мимо ворот одобряющего Store и принимался правилом."""
    k = evidence.get("kind") if isinstance(evidence, Mapping) else None
    return k if type(k) is str else ""


def _answer_ok(ev, task, answers):
    a = (answers or {}).get(ev.get("answer_id"))
    if a is None:
        return "evidence_missing"
    if _s(a.get("task_id")) != _s(task.get("task_id")) or _s(a.get("case_id")) != _s(task.get("case_id")):
        return "evidence_foreign"
    if not (a.get("verdict") == "accepted" or _s(a.get("promoted_by"))):
        return "evidence_foreign"
    if a.get("case_ver_at") != task.get("case_ver"):
        return "evidence_foreign"
    return ""


def _in_term(day, start, end):
    return day is not None and start is not None and end is not None and start <= day <= end


def _expected_in(expected, got):
    """Прочитанное назад содержит записанное: словарь — каждый ключ ожидаемого равен прочитанному (место результата
    может добавить свои поля, например case_id); иное — равенство."""
    if isinstance(expected, Mapping) and isinstance(got, Mapping):
        return all(k in got and got[k] == v for k, v in expected.items())
    return expected == got


def stage_allowed(task: Mapping[str, Any], binding: Mapping[str, Any], stage: str, evidence: Mapping[str, Any],
                  prior: Collection[str], used_refs: Collection[str], answers: Mapping[int, Mapping[str, Any]],
                  other_rows: Sequence[Mapping[str, Any]], params: Mapping[str, Any]) -> Tuple[bool, str]:
    """(допустимо, код). Код при True — "" или "without_acceptance" (ступень 4 без 3, флаг ступени).

    task — rc_task (+ "case_id"); binding — привязка задачи (plate, booking_id, anchor, start_day, end_day,
    crm_row_seen); prior — уже записанные ступени задачи; used_refs — evidence_ref, уже занятые любой ступенью;
    answers — строки rc_answer дела по id с "task_id" их ожидания (для human_mark — ВСЕ ответы дела); evidence —
    Evidence §3.6 (+ "task_id" ожидания у post/readback; у wa_delivery — "expected_wamid", "notice_case_ver",
    "case_ver"; у human_mark — "by" автора вызова, если известен)."""
    task = task or {}
    binding = binding or {}
    ev = evidence or {}
    prior = set(prior or ())
    n = STAGE_NO.get(stage)
    kind = evidence_kind(ev)
    ref = _s(ev.get("ref"))
    if n is None:
        return False, "evidence_forbidden"
    if n in (4, 5) and kind in _FORBIDDEN_4_5:
        return False, "evidence_forbidden"
    if n == 4 and kind == "crm_status_read":
        return False, "evidence_forbidden"
    if n not in _KIND_STAGES.get(kind, ()):
        return False, "evidence_forbidden"
    if not ref:
        return False, "evidence_missing"
    if ref in set(used_refs or ()):
        return False, "evidence_foreign"
    # порядок: 2–3 после 1; 4 без 3 — флаг; 5 только после 4; 6 после 5; ступень не пишется дважды
    if stage in prior:
        return False, "order"
    if n in (2, 3) and "question_sent" not in prior:
        return False, "order"
    if n == 5 and "physically_done" not in prior:
        return False, "order"
    if n == 6 and "result_recorded" not in prior:
        return False, "order"
    tkind = _s(task.get("kind"))
    if kind == "post":
        if not (_s(ev.get("exp_id")) and _s(ev.get("chat")) and _s(ev.get("msg_id"))):
            return False, "evidence_missing"
        if "task_id" in ev and _s(ev.get("task_id")) != _s(task.get("task_id")):
            return False, "evidence_foreign"                  # ожидание чужой задачи (поле кладёт Store)
    elif kind == "answer":
        code = _answer_ok(ev, task, answers)
        if code:
            return False, code
    elif kind == "staff_accept_reply":
        signal = _p(params, "ACCEPTANCE_SIGNAL")
        if is_unknown(signal):
            return False, "param_unknown"
        names = _seq(signal) or ()
        if tkind not in names and "staff_accept_reply" not in names:
            return False, "param_unknown"
        code = _answer_ok(ev, task, answers)
        if code:
            return False, code
        if _s((answers or {}).get(ev.get("answer_id"), {}).get("decision")) != "yes":
            return False, "evidence_forbidden"
    elif kind == "human_mark":
        author = ev.get("author_id")
        by = ev.get("by")
        # не одобряющий по id — свидетельство не принимается (код из перечня §6; Store сам отдаёт approver_unknown
        # по by вызова, §5.3)
        if isinstance(by, Mapping) and (_s(by.get("kind")) != "human" or by.get("id") != author):
            return False, "evidence_forbidden"
        if not approver_ok(author, params):
            return False, "evidence_forbidden"
        # К4 круг 3 (C10/C26, D§7.1, §3.6, §16.3): со строками rc_answer сверяются ОБА поля — act_ref и ref; ответ в ref
        # при act_ref-кнопке такое же «да», как ответ в act_ref
        acts = set(x for x in (_s(ev.get("act_ref")), ref) if x)
        for a in (answers or {}).values():
            if "%s:%s" % (_s(a.get("chat")), _s(a.get("msg_id"))) in acts:
                return False, "evidence_forbidden"            # «да»/ответ не превращается в ступень 3–4 (B3-3)
    elif kind == "topic_event":
        sources = _sub(_p(params, "PHYSICAL_DONE_SOURCES"), tkind)
        if is_unknown(sources) or "topic_event" not in (_seq(sources) or ()):
            return False, "param_unknown"
        if _s(ev.get("bike")) != _s(binding.get("plate")):
            return False, "evidence_foreign"
        at = _known_num(ev.get("at"))
        created = _known_num(task.get("created_at"))
        if at is None or (created is not None and at < created):
            return False, "evidence_foreign"
        day = day_of_moment(at, _known_int(_p(params, "TZ_H")) or 0)
        if not _in_term(day, _date(binding.get("start_day")), _date(binding.get("end_day"))):
            return False, "evidence_foreign"
        for r in other_rows or []:
            if _B.status_of(r) == ST_DONE or plate_of_row(r) != _s(binding.get("plate")):
                continue
            if _s(r.get("booking_id")) and _s(r.get("booking_id")) == _s(binding.get("booking_id")):
                continue
            if r.get("row") is not None and r.get("row") == binding.get("crm_row_seen"):
                continue
            if _in_term(day, _date(r.get("date_start")), _date(r.get("date_end"))):
                return False, "evidence_foreign"
    elif kind == "crm_status_read":
        if tkind not in ("handover", "return"):
            return False, "evidence_forbidden"
        place = _sub(_p(params, "RESULT_RECORD_PLACE"), tkind)
        if is_unknown(place):
            return False, "param_unknown"
        key = _s(ev.get("booking_id")) or _s(ev.get("anchor"))
        if not key or key not in (_s(binding.get("booking_id")), _s(binding.get("anchor"))):
            return False, "evidence_foreign"
        read_at, created = _known_num(ev.get("read_at")), _known_num(task.get("created_at"))
        if read_at is None or created is None or not read_at > created:
            return False, "readback_mismatch"
        if ev.get("row") is None or ev.get("row") != binding.get("crm_row_seen"):
            return False, "readback_mismatch"
        want = _s(place).split(":", 1)[1] if ":" in _s(place) else ""
        if want and _s(ev.get("status")).lower() != want:
            return False, "readback_mismatch"
    elif kind == "readback":
        place = _sub(_p(params, "RESULT_RECORD_PLACE"), tkind)
        if is_unknown(place):
            return False, "param_unknown"
        if _s(ev.get("task_id")) and _s(ev.get("task_id")) != _s(task.get("task_id")):
            return False, "evidence_foreign"
        if _s(ev.get("outcome")) != "landed":
            return False, "readback_mismatch"
        read_at, written_at = _known_num(ev.get("read_at")), _known_num(ev.get("written_at"))
        if read_at is None or written_at is None or not read_at > written_at:
            return False, "readback_mismatch"
        if "expected" in ev and "got" in ev and not _expected_in(ev.get("expected"), ev.get("got")):
            return False, "readback_mismatch"
    elif kind == "wa_delivery":
        if _s(ev.get("status")) not in ("delivered", "read"):
            return False, "not_delivered"
        if not _s(ev.get("wamid")) or not _s(ev.get("notice_id")):
            return False, "evidence_missing"
        if "expected_wamid" in ev and _s(ev.get("expected_wamid")) != _s(ev.get("wamid")):
            return False, "not_delivered"
        if "notice_case_ver" in ev and ev.get("notice_case_ver") != ev.get("case_ver"):
            return False, "not_delivered"
    if n == 4 and "task_accepted" not in prior:
        return True, "without_acceptance"
    return True, ""


# ----------------------------------------------------------------------------------------------------------------
# Обязательный набор обязательств (CONTRACT §3.4 REQUIRED_OBLIGATIONS, DESIGN §7.3)
# ----------------------------------------------------------------------------------------------------------------

_RX_AMOUNT = re.compile(r"^\d+(?:[.,]\d+)?$")
PASSPORT_WORDS = ("passport", "паспорт")                       # deposit_raw сырьём: число | 'passport' | ''
CELL_CURRENCY = "THB"                                          # валюта клеток листа — как в примере CONTRACT §8.3


def _cell_amount(value):
    """Клетка суммы → число > 0 | None (пусто/0/текст — None: клетка пустая приходит нулём, ReadFleet.js:494)."""
    if _known_num(value) is not None:
        return value if value > 0 else None
    s = _s(value).replace(" ", "").replace(" ", "")
    if _RX_AMOUNT.match(s):
        v = float(s.replace(",", "."))
        return (int(v) if v == int(v) else v) if v > 0 else None
    return None


def _obl(kind, role, direction, state, outcome=None, amount=None, currency=None, why="", **extra):
    out = {"kind": kind, "role": role, "direction": direction, "state": state, "outcome": outcome,
           "amount": amount, "currency": currency, "why": why, "required": 1}
    out.update(extra)
    return out


def required_obligations(row: Mapping[str, Any], params: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Обязательный набор при open_case (I25): bike/handover при «Бронь»; bike/return при «Бронь»/«В аренде»;
    money/rent всегда (число в to_pay/debt → open/incomplete, иначе unknown); money/deposit всегда (число → open/
    incomplete + money/deposit_refund; passport → unknown, why=deposit_passport, + document/passport_return с
    документом passport_deposit; пусто/непонятно → unknown); client/notify_final по FINAL_NOTICE_REQUIRED.
    Сумма клетки известной не считается (outcome=incomplete, I26); closed здесь не рождается никогда."""
    row = row or {}
    st = _B.status_of(row)
    out = []
    if st == ST_BOOKED:
        out.append(_obl("bike", "handover", "internal", "open"))
    if st in (ST_BOOKED, ST_RENTED):
        out.append(_obl("bike", "return", "internal", "open"))
    rent = _cell_amount(row.get("to_pay")) or _cell_amount(row.get("debt"))
    if rent is not None:
        out.append(_obl("money", "rent", "from_client", "open", "incomplete", rent, CELL_CURRENCY, "cell"))
    else:
        out.append(_obl("money", "rent", "from_client", "unknown", "unknown", why="cell_empty"))
    dep_raw = _s(row.get("deposit_raw"))
    dep = _cell_amount(dep_raw) if dep_raw else None
    if dep_raw.lower() in PASSPORT_WORDS:
        out.append(_obl("money", "deposit", "from_client", "unknown", "unknown", why="deposit_passport"))
        out.append(_obl("document", "passport_return", "to_client", "open", why="deposit_passport",
                        document={"kind": "passport_deposit", "ext_id": "deposit:%s" % row.get("row"),
                                  "status": "unverified"}))
    elif dep is not None:
        out.append(_obl("money", "deposit", "from_client", "open", "incomplete", dep, CELL_CURRENCY, "cell"))
        out.append(_obl("money", "deposit_refund", "to_client", "open", "incomplete", dep, CELL_CURRENCY, "cell"))
    else:
        out.append(_obl("money", "deposit", "from_client", "unknown", "unknown", why="cell_empty"))
    fin = _p(params, "FINAL_NOTICE_REQUIRED")
    if is_unknown(fin):
        out.append(_obl("client", "notify_final", "to_client", "unknown", why="param_unknown:FINAL_NOTICE_REQUIRED"))
    elif fin is True:
        out.append(_obl("client", "notify_final", "to_client", "open"))
    return out


# ----------------------------------------------------------------------------------------------------------------
# Справка о байке (CONTRACT §6 bike_state_fact, I44)
# ----------------------------------------------------------------------------------------------------------------


def _local_epoch(value, tz_h=7):
    """'yyyy-MM-dd HH:mm' в зоне +tz_h → секунды эпохи | None (wa_book_read.moment_of)."""
    m = _B.moment_of(value)
    if m is None:
        return None
    return m.replace(tzinfo=datetime.timezone.utc).timestamp() - tz_h * 3600


def bike_state_fact(item: Mapping[str, Any], binding: Mapping[str, Any]) -> Dict[str, Any]:
    """Строка листа «состояние_байка» (StatePort) → справка. Решений не принимает: не свидетельство ступеней, не
    закрыватель, booking_id и клиент листа не привязка (I44, I18). Байк листа ≠ bike_name привязки →
    {"code": "foreign_bike"}, факт не пишется. observed_at — `updated` листа в зоне +7 (TZ_H по умолчанию; None —
    время не разобрано)."""
    item = item or {}
    binding = binding or {}
    if _s(item.get("bike")) != _s(binding.get("bike_name")):
        return {"code": "foreign_bike"}
    flags = []
    seen_bk = _s(item.get("booking_id"))
    if seen_bk and seen_bk != _s(binding.get("booking_id")):
        flags.append("foreign_booking")
    if _s(item.get("status")).lower() == ST_RENTED and _s(binding.get("status_seen")).lower() != ST_RENTED:
        flags.append("status_mismatch")
    value = {"status": item.get("status"), "location": item.get("location"), "updated": item.get("updated"),
             "date_due": item.get("date_due"), "booking_id_seen": item.get("booking_id"),
             "client_seen": item.get("client")}
    return {"value": value, "observed_at": _local_epoch(item.get("updated"), PARAMS_DEFAULT["TZ_H"]),
            "flags": flags}


# ----------------------------------------------------------------------------------------------------------------
# Вердикт обязательства (CONTRACT §6 obligation_verdict, I14, I26, I45)
# ----------------------------------------------------------------------------------------------------------------


def _stage_no(value):
    if _known_int(value) is not None:
        return value
    return STAGE_NO.get(_s(value))


def obligation_verdict(kind: str, role: str, want: Mapping[str, Any], write: Optional[Mapping[str, Any]] = None,
                       cell: Optional[Mapping[str, Any]] = None, human: Optional[Mapping[str, Any]] = None,
                       params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """{"state": open|closed|unknown|waived, "by": write|stage|human|"", "why"}. Возраста среди входов нет (I14).

    want — {"amount","currency","direction","state","outcome"} обязательства; human — {"decided"|"waive"|"want",
    "detail"} одобряющего (по id проверяет Store); cell — {"state": value|empty|text|unread, "num"}.
    write у money — {"cash": факт кассы {"state","rental_id","role","amount","currency"}, "second": документ
    {"kind","status","booking_id"} | None, "binding": {"rental_id","booking_id"}}; write у bike/client/document —
    закрыватель-ступень {"stage", "task_kind", "intent", "pdf"} (CONTRACT §3.4)."""
    want = want or {}
    cur = _s(want.get("state")) or "unknown"
    if human:
        if human.get("waive") is True:
            return {"state": "waived", "by": "human", "why": "waived"}
        if human.get("decided"):
            return {"state": "closed", "by": "human", "why": "decided"}
        if isinstance(human.get("want"), Mapping):
            if kind != "money":
                return {"state": cur, "by": "", "why": "want_not_money"}
            return {"state": "open" if cur in ("open", "unknown") else cur, "by": "", "why": "want_set"}
        return {"state": cur, "by": "", "why": "human_no_decision"}
    if write:
        if "stage" in write:
            return _stage_verdict(kind, role, cur, write)
        if kind != "money":
            return {"state": cur, "by": "", "why": "write_not_closer"}
        return _money_write_verdict(role, want, cur, write, params)
    if cell is not None:
        if kind != "money":
            return {"state": cur, "by": "", "why": "cell_not_closer"}
        num = _known_num(cell.get("num"))
        if _s(cell.get("state")) == "value" and num is not None and num > 0:
            return {"state": "open", "by": "", "why": "cell_value"}
        return {"state": "unknown", "by": "", "why": "cell_" + (_s(cell.get("state")) or "unread")}
    return {"state": cur, "by": "", "why": ""}


def _stage_verdict(kind, role, cur, write):
    n = _stage_no(write.get("stage"))
    tkind = _s(write.get("task_kind"))
    if kind == "bike" and role in ("handover", "return") and n is not None and n >= 5 and tkind == role:
        return {"state": "closed", "by": "stage", "why": "result_recorded"}
    if kind == "client" and role == "notify_final" and n == 6 and _s(write.get("intent")) == "final":
        return {"state": "closed", "by": "stage", "why": "client_notified"}
    if kind == "document" and role == "contract_send" and n == 6 and write.get("pdf"):
        return {"state": "closed", "by": "stage", "why": "client_notified"}
    return {"state": cur, "by": "", "why": "stage_not_closer"}


def _money_write_verdict(role, want, cur, write, params):
    rule = _p(params, "MONEY_CLOSE_RULE")
    if is_unknown(rule) or rule != "cash_and_second_source":
        return {"state": cur, "by": "", "why": "param_unknown:MONEY_CLOSE_RULE"}
    # Порядок проверок — CONTRACT §5.2 settle_obligation(write): роль → второй источник → сумма want → booking_id.
    if role != "rent":
        return {"state": cur, "by": "", "why": "role_not_rent"}            # pay_confirmed знает только R_RENT
    binding = write.get("binding") or {}
    second = write.get("second")
    if (not isinstance(second, Mapping) or _s(second.get("kind")) != "contract_signed"
            or _s(second.get("status")) != "verified"
            or _s(second.get("booking_id")) != _s(binding.get("booking_id"))):
        return {"state": cur, "by": "", "why": "second_source_missing"}
    if _s(want.get("outcome")) != "valid":
        return {"state": cur, "by": "", "why": "want_not_valid"}           # сумма клетки известной не считается
    if not _s(binding.get("booking_id")):
        return {"state": cur, "by": "", "why": "booking_id_missing"}
    cash = write.get("cash") or {}
    bound_to = cash.get("rental_id", cash.get("bound_rental_id"))
    if (_s(cash.get("state") or "valid") != "valid" or bound_to is None or bound_to != binding.get("rental_id")
            or _s(cash.get("role")) != R_RENT):
        return {"state": cur, "by": "", "why": "cash_invalid"}
    if _s(cash.get("currency")).upper() != _s(want.get("currency")).upper():
        return {"state": "open", "by": "", "why": "currency_mismatch"}     # валюты не сравниваются (CURRENCY_RATE)
    amount, wanted = _known_num(cash.get("amount")), _known_num(want.get("amount"))
    if amount is None or wanted is None or amount != wanted:
        return {"state": "open", "by": "", "why": "amount_mismatch"}
    return {"state": "closed", "by": "write", "why": "cash_and_second_source"}


# ----------------------------------------------------------------------------------------------------------------
# Покрытие запрошенного периода документом (CONTRACT §6 document_coverage, I46, К4-C39)
# ----------------------------------------------------------------------------------------------------------------

_RX_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _iso_strict(value):
    """'YYYY-MM-DD' (настоящая дата) → date | None; иные формы не принимаются."""
    if not isinstance(value, str) or not _RX_ISO_DAY.match(value):
        return None
    try:
        return datetime.date(int(value[0:4]), int(value[5:7]), int(value[8:10]))
    except ValueError:
        return None


def document_coverage(doc: Mapping[str, Any], period: Tuple[Optional[str], Optional[str]]) -> Dict[str, Any]:
    """ПОКРЫТИЕ запрошенного периода — отдельно от принадлежности (I46): {"code": "covers"|"not_covers"|"unknown",
    "why", "missing"}. Входы — только статус, вид и cover_* документа и запрошенный период; срок привязки, дата
    подписи и дата документа сюда не передаются и не читаются: verified (принадлежность) покрытия не доказывает,
    продление его не расширяет. Покрытие доказано только cover_from/cover_to с cover_basis ∈ COVER_BASES."""
    doc = doc or {}
    if _s(doc.get("status")) != "verified":
        return {"code": "unknown", "why": "binding_not_verified", "missing": ["document_period"]}
    if not period or len(period) != 2:
        return {"code": "unknown", "why": "period_not_given", "missing": ["period"]}
    p_from, p_to = _iso_strict(period[0]), _iso_strict(period[1])
    if p_from is None or p_to is None or p_from > p_to:
        return {"code": "unknown", "why": "period_not_given", "missing": ["period"]}
    if _s(doc.get("kind")) not in ("contract_signed", "contract_pdf"):
        return {"code": "unknown", "why": "doc_period_unknown", "missing": ["document_period"]}
    c_from, c_to = _iso_strict(doc.get("cover_from")), _iso_strict(doc.get("cover_to"))
    basis = doc.get("cover_basis")
    if c_from is None or c_to is None or c_from > c_to or basis not in COVER_BASES:
        return {"code": "unknown", "why": "doc_period_unknown", "missing": ["document_period"]}
    if c_from <= p_from and p_to <= c_to:
        return {"code": "covers", "why": "", "missing": []}
    why = "partial" if (p_from <= c_to and c_from <= p_to) else "outside"
    return {"code": "not_covers", "why": why, "missing": ["document_period"]}


# ----------------------------------------------------------------------------------------------------------------
# Блокеры закрытия и разрешённые намерения (CONTRACT §6 close_blockers/allowed, DESIGN §6.7, §7.6)
# ----------------------------------------------------------------------------------------------------------------

_TERMINAL_EXPECT = ("answered", "superseded", "cancelled")


def _pair(item):
    if isinstance(item, Mapping):
        return (_s(item.get("kind")), _s(item.get("role")))
    return (_s(item[0]), _s(item[1]))


def close_blockers(view: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """[{"what","id","why"}] — пусто ⇔ дело можно закрыть (I13). Возраст не участвует (I14).

    view — части case_view (CONTRACT §8.4): "case" {case_id, link_state, attention}; "rental" {"current": привязка}
    (или сама привязка) со status_seen и, если известно, status_read_back; обязательства — "obligations" или
    "money" + "obligations_other" (id, kind, role, state, closed_by; у closed_by=write — "close_fact_state"/
    close_fact.state = valid и "close_second_status"/close_second.status = verified, иначе closing_fact_invalid);
    "expectations", "notices", "tasks". Набор REQUIRED (I25): "required" [{kind, role}] от Store (из события
    case_opened), иначе required_obligations(view["row"]), иначе минимальный набор, выводимый без строки:
    money/rent, money/deposit (+ deposit_refund при числовом залоге, + document/passport_return при паспорте),
    client/notify_final, пока FINAL_NOTICE_REQUIRED ≠ False (параметры — view["params"])."""
    view = view or {}
    case = view.get("case") or {}
    out = []
    obls = _view_obligations(view)
    for o in obls:
        st = _s(o.get("state"))
        if st in ("open", "unknown"):
            out.append({"what": "obligation", "id": o.get("id", o.get("obligation_id")), "why": "obligation_" + st})
        elif st == "closed" and _s(o.get("closed_by")) == "write":
            fact = o.get("close_fact") if isinstance(o.get("close_fact"), Mapping) else {}
            second = o.get("close_second") if isinstance(o.get("close_second"), Mapping) else {}
            fact_ok = _s(o.get("close_fact_state") or fact.get("state")) == "valid"
            second_ok = _s(o.get("close_second_status") or second.get("status")) == "verified"
            if not (fact_ok and second_ok):
                out.append({"what": "obligation", "id": o.get("id", o.get("obligation_id")),
                            "why": "closing_fact_invalid"})
    required = view.get("required")
    if required is None and view.get("row") is not None:
        required = [(o["kind"], o["role"]) for o in required_obligations(view.get("row"), view.get("params"))]
    if required is None:
        required = _minimal_required(obls, view.get("params"))
    have = set((_s(o.get("kind")), _s(o.get("role"))) for o in obls)
    for item in required:
        pair = _pair(item)
        if pair not in have:
            out.append({"what": "obligation", "id": "%s/%s" % pair, "why": "obligation_missing"})
    for e in view.get("expectations") or []:
        if _s(e.get("state")) not in _TERMINAL_EXPECT:
            out.append({"what": "expectation", "id": e.get("exp_id"), "why": "expect_state"})
    for nt in view.get("notices") or []:
        if _s(nt.get("state")) in ("drafting", "draft_unknown"):
            out.append({"what": "notice", "id": nt.get("notice_id"), "why": "notice_inflight"})
    for t in view.get("tasks") or []:
        if _s(t.get("state")) == "open" and (_known_int(t.get("top_stage")) or 0) < 5:
            out.append({"what": "task", "id": t.get("task_id"), "why": "task_open"})
    if case.get("attention"):
        out.append({"what": "case", "id": case.get("case_id"), "why": "attention"})
    if _s(case.get("link_state") or "ok") != "ok":
        out.append({"what": "case", "id": case.get("case_id"), "why": "link_drift"})
    rental = view.get("rental") or {}
    if isinstance(rental, Mapping) and "current" in rental:
        rental = rental.get("current") or {}
    if not _status_read_back(rental, obls, view.get("tasks") or []):
        out.append({"what": "rental", "id": rental.get("rental_id", rental.get("id")), "why": "status_not_read_back"})
    return out


def _view_obligations(view):
    """Обязательства дела из view: "obligations" или части money + obligations_other (§8.4), без повторов по id."""
    seen, out = set(), []
    parts = [view.get("obligations")] if view.get("obligations") is not None else [view.get("money"),
                                                                                   view.get("obligations_other")]
    for part in parts:
        for o in part or []:
            key = o.get("id", o.get("obligation_id"))
            if key is not None and key in seen:
                continue
            seen.add(key)
            out.append(o)
    return out


def _minimal_required(obls, params):
    """Набор REQUIRED, выводимый без строки листа (§3.4): то, что рождается «всегда», и то, что следует из вида
    залога; bike/handover и bike/return зависят от статуса строки при открытии — их называет Store ("required")."""
    req = [("money", "rent"), ("money", "deposit")]
    for o in obls:
        if _s(o.get("kind")) == "money" and _s(o.get("role")) == "deposit":
            if _known_num(o.get("amount")) is not None:
                req.append(("money", "deposit_refund"))
            if _s(o.get("why")) == "deposit_passport":
                req.append(("document", "passport_return"))
    if _p(params, "FINAL_NOTICE_REQUIRED") is not False:
        req.append(("client", "notify_final"))
    return req


def _status_read_back(rental, obls, tasks):
    """«Завершена» прочитана назад: статус привязки «завершена» и (Store назвал status_read_back, или ступень 5
    задачи возврата записана — её свидетельство readback/crm_status_read, или возврата у дела не было вовсе —
    строка была «завершена» уже при открытии, обязательства bike/return нет)."""
    if _s(rental.get("status_seen")).lower() != ST_DONE:
        return False
    if rental.get("status_read_back") is True:
        return True
    if any(_s(t.get("kind")) == "return" and (_known_int(t.get("top_stage")) or 0) >= 5 for t in tasks):
        return True
    return not any(_s(o.get("kind")) == "bike" and _s(o.get("role")) == "return" for o in obls)


def allowed(view: Mapping[str, Any], params: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Разрешённые НАМЕРЕНИЯ (ничего не исполняет, DESIGN §6.7): propose_client_notice (задача на ступени 5 при
    текущей версии, attention=0, link_state=ok, нет открытого confirm_link, FEEDS_CONNECTED ⊇ {intervention,
    inbound}); request_approval activate/close (задача handover/return на ступени 4, link_state=ok, нет ждущей
    карточки того же действия); close_case (close_blockers пуст). view — как у close_blockers + case.ver/state,
    tasks[].kind/case_ver, expectations[].kind/action, notices[].task_id."""
    view = view or {}
    case = view.get("case") or {}
    if _s(case.get("state") or "open") != "open":
        return []
    out = []
    link_ok = _s(case.get("link_state") or "ok") == "ok"
    exps = list(view.get("expectations") or [])
    confirm_open = any(_s(e.get("kind")) == "confirm_link" and _s(e.get("state")) not in _TERMINAL_EXPECT
                       for e in exps)
    feeds = _p(params, "FEEDS_CONNECTED")
    feeds = set(feeds) if isinstance(feeds, (set, frozenset, list, tuple)) else set()
    client_ok = (not case.get("attention")) and link_ok and not confirm_open and {"intervention", "inbound"} <= feeds
    live_notice = set(_s(nt.get("task_id")) for nt in view.get("notices") or []
                      if _s(nt.get("state")) in ("intent", "drafting", "draft_unknown", "drafted"))
    for t in view.get("tasks") or []:
        top = _known_int(t.get("top_stage")) or 0
        tid = t.get("task_id")
        if (client_ok and top == 5 and _s(t.get("state")) == "done" and t.get("case_ver") == case.get("ver")
                and _s(tid) not in live_notice):
            out.append({"action": "propose_client_notice", "task_id": tid, "why": "result_recorded"})
        action = {"handover": "activate", "return": "close"}.get(_s(t.get("kind")))
        if action and link_ok and top == 4 and _s(t.get("state")) == "open":
            waiting = any(_s(e.get("kind")) == "approval" and _s(e.get("action")) == action
                          and _s(e.get("state")) not in _TERMINAL_EXPECT for e in exps)
            if not waiting:
                out.append({"action": "request_approval", "approval_action": action, "task_id": tid,
                            "why": "physically_done"})
    if not close_blockers(view):
        out.append({"action": "close_case", "task_id": None, "why": "no_blockers"})
    return out
