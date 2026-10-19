# -*- coding: utf-8 -*-
"""Факты карточки выдачи — договор по реестру подписей и залог по брони (HOFACTS1910). Чистые функции.

ЗАЧЕМ. Карточка активации выдачи (`splinter._handover_activation_card`) несла только байк, клиента, строку и даты:
подписан ли договор и указан ли залог, не видел никто, и «да» человека было штампом на КАЖДОЙ выдаче, а не решением
исключения. Здесь — разбор и слова: строка брони уже выбрана вызывающим (`rental_case_rules.pick`, точный день
выдачи), ответ двери `contract_find` уже прочитан им же (в потоке, под потолком времени) — модуль только называет, что
в них лежит, и какое из этого ИСКЛЮЧЕНИЕ. Исключения идут первой строкой карточки (после подписи «🐀 Splinter»).

ДОГОВОР. Привязка брони — `contract_ref.binding_of_crm(row)` (телефон из U, номер байка, срок), исход —
`contract_ref.versions(ответ двери, привязка)`; доверия к «новейшему» нет и здесь (это правило `contract_ref`). Слова
свои: подписан · ждёт подписи · подписанного нет · несколько — решает человек · не сверен · неизвестно. Хвост
`contract_ref.GW_NOT_BRIDGE` («мост его не пересоберёт») — слово генератора договора, к выдаче не относится и не
берётся. Таймаут, отказ двери, неразобранный ответ — «неизвестно, а не «договора нет»»: молчание реестра договором
не считается ни в одну сторону.

ЗАЛОГ. CRM S выбранной строки (`deposit_raw`, мост пишет туда число или «passport», Booking.js:276), как у карточки
приёма: число → «N ฿», «passport» → «паспорт», пусто → «не указан ⚠️». Прочий рукописный текст НЕ повторяется
(в клетке может оказаться что угодно) — «не разобран ⚠️». Это залог ПО БРОНИ, а не приход по кассе: получен ли он,
модуль не знает и не говорит.

ГРАНИЦА УСТРОЙСТВОМ: импорты ровно `re` и `contract_ref`; сети, файлов, базы, часов и окружения нет, двери не зовутся
(страж — ast в tests/test_handover_facts.py). В словах нет телефона, полного doc_id и pdf_id: doc — хвостом
`contract_ref.tail`; имя клиента карточка несёт и без этого модуля.
"""
import re

import contract_ref as CR

FIND_LIMIT = 100                          # = splinter._contract_ref_report (потолок двери, bridge_client.contract_find)
REASON_MAX = 80                           # причина из ответа двери — не длиннее (слово моста, не текст клиента)

# ── исходы строки договора: исходы contract_ref.versions + два своих (до разбора) ─────────────────────────────────
NO_TERM = "no_term"                       # у строки брони нет номера байка или срока — реестр не читали
TIMEOUT = "timeout"                       # реестр не ответил за потолок времени карточки
OUTCOMES = CR.OUTCOMES + (NO_TERM, TIMEOUT)

# ── слова строк карточки ─────────────────────────────────────────────────────────────────────────────────────
DOC = "📄 Договор: "
W_DOC_CURRENT = DOC + "подписан · стр. %s · doc %s"
W_DOC_PENDING = DOC + "ждёт подписи · стр. %s %s · doc %s ⚠️"
W_DOC_NONE = DOC + "подписанного и ждущего подписи в реестре нет (строк в сроке: %d) ⚠️"
W_DOC_MANY = DOC + "подписанных несколько (%s) — какой текущий, решает человек ⚠️"
W_DOC_INCOMPLETE = DOC + "реестр прочитан не полностью или привязка не сверена (%s) — версия не названа ⚠️"
W_DOC_UNKNOWN = DOC + "реестр не прочитан (%s) — неизвестно, а не «договора нет» ⚠️"
W_DOC_TIMEOUT = DOC + "реестр не ответил за %s с — неизвестно, а не «договора нет» ⚠️"
W_DOC_NO_TERM = DOC + "в строке брони нет номера байка или срока — реестр не читал ⚠️"

DEP = "💰 Залог по брони: "
W_DEP_MONEY = DEP + "%s ฿"
W_DEP_ZERO = DEP + "0 ฿ ⚠️"
W_DEP_PASSPORT = DEP + "паспорт"
W_DEP_NONE = DEP + "не указан ⚠️"
W_DEP_UNPARSED = DEP + "в CRM записан не числом и не «паспорт» — не разобран ⚠️"

# ── исключения (первая строка карточки) ───────────────────────────────────────────────────────────────────────
HEAD = "⚠️ Исключение: %s"
HEAD_SEP = " · "
X_DOC_PENDING = "договор не подписан"
X_DOC_NONE = "подписанного договора нет"
X_DOC_MANY = "договоров несколько"
X_DOC_UNCHECKED = "договор не сверен"
X_DOC_UNKNOWN = "договор неизвестен"
X_DEP_NONE = "залог не указан"
X_DEP_ZERO = "залог 0 ฿"
X_DEP_UNPARSED = "залог не разобран"

PASSPORT_WORDS = ("passport", "паспорт")
_NUM = re.compile(r"^\d+(?:[.,]\d+)?$")
_SPACES = re.compile(r"\s+")


def _s(v):
    return str(v if v is not None else "").strip()


def _short(why):
    """Причина из ответа двери → не длиннее REASON_MAX, без переводов строки; пусто → «ответ не разобран»."""
    w = _SPACES.sub(" ", _s(why)) or CR.W_UNPARSED
    return w if len(w) <= REASON_MAX else w[:REASON_MAX - 1] + "…"


def _money(n):
    """Сумма как у карточки приёма (splinter._fmt): «7 000»."""
    return format(float(n), ",.0f").replace(",", " ")


# ── договор ───────────────────────────────────────────────────────────────────────────────────────────────────

def find_args(row):
    """Строка CRM → аргументы `contract_find` (байк и срок брони, дни ISO) | None — нет номера байка или срока (тогда
    реестр не читается вовсе, исход NO_TERM). Тем же разбором, что `splinter._contract_ref_report`."""
    b = CR.binding_of_crm(row)
    if not (b["plate"] and b["date_from"] and b["date_to"]):
        return None
    return {"bike": _s((row or {}).get("bike")), "date_from": b["date_from"], "date_to": b["date_to"],
            "limit": FIND_LIMIT}


def versions_of(row, found):
    """Ответ двери `contract_find` + строка брони → исход `contract_ref.versions` (вход не мутируется)."""
    return CR.versions(found, CR.binding_of_crm(row))


def no_term():
    return {"outcome": NO_TERM, "reason": ""}


def unread(why):
    """Дверь не прочитана (исключение вызова) — тот же исход, что у contract_ref на отказ двери."""
    return {"outcome": "unknown", "reason": CR.W_UNREAD % _short(why)}


def timeout(budget_s):
    return {"outcome": TIMEOUT, "reason": "", "budget": budget_s}


def _unread_words(reason):
    pre = CR.W_UNREAD % ""
    r = _s(reason)
    return _short(r[len(pre):] if r.startswith(pre) else r)


def _row(it):
    return it.get("row") if it.get("row") is not None else "?"


def _rows_words(items):
    """«стр. 38, стр. 36»: не больше contract_ref.ROWS_SHOWN, дальше «и ещё N»."""
    words = ", ".join("стр. %s" % _row(it) for it in items[:CR.ROWS_SHOWN])
    more = len(items) - CR.ROWS_SHOWN
    return words + (" и ещё %d" % more if more > 0 else "")


def _budget_words(budget_s):
    try:
        b = float(budget_s)
    except (TypeError, ValueError):
        return "?"
    return ("%d" % b) if b == int(b) else ("%.1f" % b)


def contract_fact(res):
    """Исход versions() (или no_term / unread / timeout) → (строка карточки, слово исключения | None).
    Подписан один привязанный — исключения нет; всё прочее, включая «неизвестно», — исключение: факт не подтверждён."""
    res = res if isinstance(res, dict) else {}
    out = res.get("outcome")
    rows = [it for it in res.get("rows") or [] if isinstance(it, dict)]
    cur = res.get("current")
    pend = [it for it in res.get("pending") or [] if isinstance(it, dict)]
    if out == "current" and isinstance(cur, dict):
        return W_DOC_CURRENT % (_row(cur), CR.tail(cur.get("doc_id"))), None
    if out == "pending" and pend:
        p = pend[0]
        return W_DOC_PENDING % (_row(p), _s(p.get("status")) or "?", CR.tail(p.get("doc_id"))), X_DOC_PENDING
    if out == "ambiguous":
        bound = [it for it in rows if it.get("role") == "signed"]
        signed = bound if len(bound) >= 2 else [it for it in rows if it.get("signed")]
        return W_DOC_MANY % (_rows_words(signed) or "строки не названы"), X_DOC_MANY
    if out == "none":
        return W_DOC_NONE % len(rows), X_DOC_NONE
    if out == "incomplete":
        return W_DOC_INCOMPLETE % _short(res.get("reason")), X_DOC_UNCHECKED
    if out == NO_TERM:
        return W_DOC_NO_TERM, X_DOC_UNCHECKED
    if out == TIMEOUT:
        return W_DOC_TIMEOUT % _budget_words(res.get("budget")), X_DOC_UNKNOWN
    return W_DOC_UNKNOWN % _unread_words(res.get("reason")), X_DOC_UNKNOWN


# ── залог ─────────────────────────────────────────────────────────────────────────────────────────────────────

def deposit_fact(raw, parsed=None):
    """CRM S строки брони → (строка карточки, слово исключения | None). `raw` — `deposit_raw` двери clients (число |
    «passport» | ''); None — старый мост без ключа: тогда только `deposit` (parseNumber S), и паспорт там неотличим от
    пустого — честное «не указан ⚠️», как у карточки приёма (`splinter._return_deposit_disp`)."""
    if raw is None:
        try:
            p = float(parsed)
        except (TypeError, ValueError):
            p = 0.0
        if p > 0:
            return W_DEP_MONEY % _money(p), None
        return W_DEP_NONE, X_DEP_NONE
    s = _SPACES.sub("", _s(raw))
    if not s:
        return W_DEP_NONE, X_DEP_NONE
    if _NUM.match(s):
        v = float(s.replace(",", "."))
        if v > 0:
            return W_DEP_MONEY % _money(v), None
        return W_DEP_ZERO, X_DEP_ZERO
    if s.lower() in PASSPORT_WORDS:
        return W_DEP_PASSPORT, None
    return W_DEP_UNPARSED, X_DEP_UNPARSED


# ── карточка ──────────────────────────────────────────────────────────────────────────────────────────────────

def facts(row, contract_res):
    """Строка брони + исход договора → {"head": строка исключений | None, "lines": [договор, залог],
    "exceptions": [...], "contract": исход, "deposit": исключение залога | None}. head — первая строка карточки."""
    row = row if isinstance(row, dict) else {}
    c_line, c_x = contract_fact(contract_res)
    d_line, d_x = deposit_fact(row.get("deposit_raw"), row.get("deposit"))
    xs = [x for x in (c_x, d_x) if x]
    return {"head": (HEAD % HEAD_SEP.join(xs)) if xs else None, "lines": [c_line, d_line], "exceptions": xs,
            "contract": (contract_res or {}).get("outcome") if isinstance(contract_res, dict) else None,
            "deposit": d_x}
