# -*- coding: utf-8 -*-
"""Факты карточки выдачи — договор по реестру подписей и залог по брони (HOFACTS1910, v2 20.10). Чистые функции.

ЗАЧЕМ. Карточка активации выдачи (`splinter._handover_activation_card`) несла только байк, клиента, строку и даты:
подписан ли договор и указан ли залог, не видел никто, и «да» человека было штампом на КАЖДОЙ выдаче, а не решением
исключения. Здесь — разбор и слова: строка брони уже выбрана вызывающим (`rental_case_rules.pick`, точный ЦЕЛЕВОЙ день
выдачи — местный день сообщения), ответ двери `contract_find` уже прочитан им же (в потоке, под потолком времени) —
модуль только называет, что в них лежит, и какое из этого ИСКЛЮЧЕНИЕ. Исключения идут первой строкой карточки (после
подписи «🐀 Splinter»).

ДОГОВОР. Чтение — ТОЙ ЖЕ дорогой, что у `splinter._contract_ref_report` (binding_of_crm → contract_find по точным
байку и сроку → versions): аргументы двери собирает она, здесь — только исход `contract_ref.versions(ответ двери,
привязка)` из того же ответа (`from_report`); доверия к «новейшему» нет и здесь (это правило `contract_ref`). Слова
свои: подписан · ждёт подписи · подписанного нет · несколько (этой брони / под фильтром двери) — решает человек · не
сверен · неизвестно. Хвост `contract_ref.GW_NOT_BRIDGE` («мост его не пересоберёт») — слово генератора договора, к
выдаче не относится и не берётся. Таймаут, отказ двери, неразобранный ответ — «неизвестно, а не «договора нет»»:
молчание реестра договором не считается ни в одну сторону.

ЗАЛОГ. CRM S выбранной строки (`deposit_raw`, мост пишет туда число или «passport», Booking.js:276), как у карточки
приёма: число → «N ฿» (разделители тысяч «7,000» / «7.000» / «7 000» — это 7000), «passport» → «паспорт», пусто → «не
указан ⚠️». Прочий рукописный текст (дробь, смесь разделителей, валюта словом) НЕ повторяется и не угадывается —
«не разобран ⚠️». Это значение, ЗАПИСАННОЕ В CRM по брони, а не приход по кассе: слова карточки называют источник
и прямо говорят «получение не сверено» (сверка получения — только уже разрешённой кассовой сверкой этой аренды).

ДЕНЬ ВЫДАЧИ ПРОТИВ БРОНИ (правило владельца 19.10 23:3x). Брони номера на целевой день нет, а на другой день есть —
бот сам ±N не выбирает и дат не меняет: карточка РУЧНАЯ (без «да / нет»), слова — `mismatch_line`: позже брони →
переоформить договор и бронь, оплата с исходной даты, если перенос не согласован заранее; раньше брони → переоформить
на фактические даты. Броней несколько — адресный вопрос с их перечнем (`many_line`), «последней» не бывает.

ТА ЖЕ СТРОКА. `ident` — тождество строки брони (строка, booking_id, номер байка, срок, имя): им вызывающий сверяет, что
перед записью вкладки состояния и перед «да» перечитана ТА ЖЕ бронь, что показала карточка (`same_as_card`).

ГРАНИЦА УСТРОЙСТВОМ: импорты ровно `re`, `datetime` (только разбор дня ISO — часов нет) и `contract_ref`; сети,
файлов, базы, часов и окружения нет, двери не зовутся (страж — ast в tests/test_handover_facts.py). В строках фактов нет
телефона, полного doc_id и pdf_id: doc — хвостом `contract_ref.tail`; имя клиента карточка несёт и без этого модуля.
"""
import datetime
import re

import contract_ref as CR

REASON_MAX = 80                           # причина из ответа двери — не длиннее (слово моста, не текст клиента)

# ── исходы строки договора: исходы contract_ref.versions + два своих (до разбора) ─────────────────────────────────
NO_TERM = "no_term"                       # у строки брони нет номера байка или срока — реестр не читали
TIMEOUT = "timeout"                       # реестр не ответил за потолок времени карточки
OUTCOMES = CR.OUTCOMES + (NO_TERM, TIMEOUT)
W_REPORT_BROKEN = "сверка не собрана"     # `_contract_ref_report` не дошёл до двери не по сроку (модуль сверки и пр.)

# ── слова строк карточки ─────────────────────────────────────────────────────────────────────────────────────
DOC = "📄 Договор: "
W_DOC_CURRENT = DOC + "подписан · стр. %s · doc %s"
W_DOC_PENDING = DOC + "ждёт подписи · стр. %s %s · doc %s%s ⚠️"
W_DOC_PENDING_MORE = " · ещё ждут подписи: %s"
W_DOC_NONE = DOC + "подписанного и ждущего подписи в реестре нет (строк в сроке: %d) ⚠️"
W_DOC_MANY = DOC + "подписанных несколько (%s) — какой текущий, решает человек ⚠️"
# неоднозначность ДВЕРИ (R2), а привязанных к брони подписанных меньше двух — как contract_ref.GW_AMBIGUOUS_DOOR
W_DOC_MANY_DOOR = (DOC + "под фильтром байка и срока подписанных несколько (%s; привязанных к брони — %d) — какой "
                   "текущий, решает человек ⚠️")
W_DOC_INCOMPLETE = DOC + "реестр прочитан не полностью или привязка не сверена (%s) — версия не названа ⚠️"
W_DOC_UNKNOWN = DOC + "реестр не прочитан (%s) — неизвестно, а не «договора нет» ⚠️"
W_DOC_TIMEOUT = DOC + "реестр не ответил за %s с — неизвестно, а не «договора нет» ⚠️"
W_DOC_NO_TERM = DOC + "в строке брони нет номера байка или срока — реестр не читал ⚠️"

DEP = "💰 Залог по брони"
DEP_CRM = DEP + " (записан в CRM): "      # источник — клетка S строки брони, не касса
NOT_CHECKED = " — получение не сверено"   # получение денег / паспорта ничем не подтверждено
W_DEP_MONEY = DEP_CRM + "%s ฿" + NOT_CHECKED
W_DEP_ZERO = DEP_CRM + "0 ฿ ⚠️"
W_DEP_PASSPORT = DEP_CRM + "паспорт" + NOT_CHECKED
W_DEP_NONE = DEP + ": в CRM не указан ⚠️"
W_DEP_UNPARSED = DEP + ": в CRM записан не числом и не «паспорт» — не разобран ⚠️"

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

# ── день выдачи против брони (ручная карточка, правило владельца 19.10 23:3x) ─────────────────────────────────────
W_LATE = ("Клиент берёт байк позже брони на %d дн. (бронь с %s): переоформить договор и бронь. "
          "Если перенос не согласован заранее — оплата с %s (исходная дата).")
W_EARLY = "Выдача раньше брони на %d дн. (бронь с %s): переоформить договор и бронь на фактические даты."
W_HAND_HEAD = "⚠️ ВЫДАЧА %s → %s: брони на %s нет — бронь строка %s (%s)."
W_HAND_TAIL = "Сам не активирую и даты не меняю — после переоформления активируй руками (Бронь→В аренде)."
W_MANY = ("⚠️ ВЫДАЧА %s: брони на %s нет, а броней этого байка несколько: %s — какая выдаётся? Сам не выбираю, "
          "не активирую и даты не меняю: договор и бронь переоформить руками.")
W_MANY_ITEM = "строка %s с %s (%s)"

PASSPORT_WORDS = ("passport", "паспорт")
_INT = re.compile(r"^\d+$")
# разделитель тысяч — один и тот же знак между группами ровно по три цифры: «7,000», «7.000», «1,000,000»
_GROUPED = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d{1,3}(?:\.\d{3})+$")
# группы и нулевые копейки другим знаком: «20,000.00» / «20.000,00» — однозначно; прочие дроби — нет
_GROUPED_ZERO = re.compile(r"^(\d{1,3}(?:,\d{3})+)\.0{1,2}$|^(\d{1,3}(?:\.\d{3})+),0{1,2}$")
_ZERO_FRAC = re.compile(r"^(\d+)[.,]0{1,2}$")      # «20000.0», «7000,00» — целое; «7.5», «7,50» — не разобрано
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


def _day(iso):
    """'YYYY-MM-DD…' → date | None (только разбор строки: часов модуль не читает)."""
    try:
        return datetime.date.fromisoformat(_s(iso)[:10])
    except (TypeError, ValueError):
        return None


def dm(iso):
    """День ISO → «ДД.ММ» для слов карточки; не разобран — «?»."""
    d = _day(iso)
    return "%02d.%02d" % (d.day, d.month) if d is not None else "?"


# ── договор ───────────────────────────────────────────────────────────────────────────────────────────────────

def versions_of(row, found):
    """Ответ двери `contract_find` + строка брони → исход `contract_ref.versions` (вход не мутируется)."""
    return CR.versions(found, CR.binding_of_crm(row))


def from_report(row, called, found, words):
    """Исход чтения ДОРОГОЙ `splinter._contract_ref_report` (её аргументы двери, её отображение сбоя вызова в
    {"ok": False, "error": класс}): дверь звана → versions() из ТОГО ЖЕ ответа и той же привязки; не звана и слова —
    «нет номера байка или срока» → no_term; не звана иначе (сверка не собрана) → «неизвестно», а не «договора нет»."""
    if called:
        return versions_of(row, found)
    if words == CR.GEN_NO_TERM:
        return no_term()
    return unread(W_REPORT_BROKEN)


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
    Подписан один привязанный — исключения нет; всё прочее, включая «неизвестно», — исключение: факт не подтверждён.
    Несколько подписанных: привязанных к брони ≥2 (R4) и только под фильтром двери (R2) — разные слова, как у
    contract_ref.gen_words; ждущих подписи несколько — первая названа, остальные перечнем."""
    res = res if isinstance(res, dict) else {}
    out = res.get("outcome")
    rows = [it for it in res.get("rows") or [] if isinstance(it, dict)]
    cur = res.get("current")
    pend = [it for it in res.get("pending") or [] if isinstance(it, dict)]
    if out == "current" and isinstance(cur, dict):
        return W_DOC_CURRENT % (_row(cur), CR.tail(cur.get("doc_id"))), None
    if out == "pending" and pend:
        p = pend[0]
        more = W_DOC_PENDING_MORE % _rows_words(pend[1:]) if len(pend) > 1 else ""
        return (W_DOC_PENDING % (_row(p), _s(p.get("status")) or "?", CR.tail(p.get("doc_id")), more),
                X_DOC_PENDING)
    if out == "ambiguous":
        bound = [it for it in rows if it.get("role") == "signed"]
        if len(bound) >= 2:
            return W_DOC_MANY % _rows_words(bound), X_DOC_MANY
        signed = [it for it in rows if it.get("signed")]
        return W_DOC_MANY_DOOR % (_rows_words(signed) or "строки не названы", len(bound)), X_DOC_MANY
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

def deposit_value(raw):
    """Клетка S (`deposit_raw`) → ("money", число > 0) | ("zero", 0) | ("passport", None) | ("none", None) |
    ("unparsed", None). Число двери (int / float без дроби) — как есть; текст — без пробелов (обычных, неразрывных,
    узких): целое; группы тысяч одним знаком («7,000», «7.000»); группы и нулевые копейки другим знаком
    («20,000.00»); целое с нулевыми копейками («20000.0»). Всё прочее (дробь «7.5», смесь знаков, валюта словом,
    минус) — не угадывается: unparsed."""
    if isinstance(raw, bool):
        return "unparsed", None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v != v or v in (float("inf"), float("-inf")) or v < 0 or v != int(v):
            return "unparsed", None
        return ("money", v) if v > 0 else ("zero", 0)
    s = _SPACES.sub("", _s(raw))
    if not s:
        return "none", None
    if s.lower() in PASSPORT_WORDS:
        return "passport", None
    digits = None
    if _INT.match(s):
        digits = s
    elif _GROUPED.match(s):
        digits = re.sub(r"[.,]", "", s)
    else:
        m = _GROUPED_ZERO.match(s) or _ZERO_FRAC.match(s)
        if m:
            digits = re.sub(r"[.,]", "", next(g for g in m.groups() if g is not None))
    if digits is None:
        return "unparsed", None
    v = float(int(digits))
    return ("money", v) if v > 0 else ("zero", 0)


def deposit_fact(raw, parsed=None):
    """CRM S строки брони → (строка карточки, слово исключения | None). `raw` — `deposit_raw` двери clients (число |
    «passport» | ''); None — старый мост без ключа: тогда только `deposit` (parseNumber S), и паспорт там неотличим от
    пустого — честное «не указан ⚠️», как у карточки приёма (`splinter._return_deposit_disp`). Число и паспорт —
    значение, записанное в CRM: слова называют источник и «получение не сверено», исключением это не становится."""
    if raw is None:
        try:
            p = float(parsed)
        except (TypeError, ValueError):
            p = 0.0
        if p > 0:
            return W_DEP_MONEY % _money(p), None
        return W_DEP_NONE, X_DEP_NONE
    kind, v = deposit_value(raw)
    if kind == "money":
        return W_DEP_MONEY % _money(v), None
    if kind == "zero":
        return W_DEP_ZERO, X_DEP_ZERO
    if kind == "passport":
        return W_DEP_PASSPORT, None
    if kind == "none":
        return W_DEP_NONE, X_DEP_NONE
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


# ── та же бронь: тождество строки ────────────────────────────────────────────────────────────────────────────────

def ident(row):
    """Строка брони → тождество для сверки «та же бронь, что на карточке»: [строка, booking_id, номер байка, начало
    и конец срока (дни ISO), имя без регистра]. Статус не входит: бронь, активированная руками между карточкой и
    записью вкладки состояния, — та же бронь (её «уже активна» решает вызывающий)."""
    row = row if isinstance(row, dict) else {}
    b = CR.binding_of_crm(row)
    return [row.get("row"), b["booking_id"], b["plate"], b["date_from"], b["date_to"], _s(row.get("name")).lower()]


def same_as_card(rec, row):
    """Запись ждущей карточки + перечитанная строка → та же ли бронь. Есть тождество карточки (`ident`, флаг ВКЛ) —
    равенство целиком; нет (запись восстановлена рестартом или заведена до флага) — номер строки, имя и начало срока
    ровно как в записи: по ним мост и активирует (bike + name + date_start)."""
    rec = rec if isinstance(rec, dict) else {}
    row = row if isinstance(row, dict) else {}
    want = rec.get("ident")
    if isinstance(want, (list, tuple)):
        return ident(row) == list(want)
    return (rec.get("row") is not None and row.get("row") == rec.get("row")
            and _s(row.get("name")).lower() == _s(rec.get("name")).lower()
            and _s(row.get("date_start")) == _s(rec.get("date_start")))


# ── день выдачи против брони ──────────────────────────────────────────────────────────────────────────────────

def day_mismatch(cands, on_day):
    """Кандидаты pick(handover) с причиной «на этот день брони нет» (все «бронь» номера с известным началом) +
    целевой день ISO → {"kind": "late"|"early", "days": N, "cand": кандидат} — бронь ровно одна; {"kind": "many",
    "cands": [...]} — броней несколько (выбирает человек); None — броней нет или день не разобран (прежний ⚠️ pick).
    Ни один исход не выбирает бронь «±N» и не меняет её дат."""
    day = _day(on_day)
    if day is None:
        return None
    cs = [c for c in cands or [] if isinstance(c, dict) and _day(c.get("start_day")) is not None]
    if not cs:
        return None
    if len(cs) > 1:
        return {"kind": "many", "cands": cs}
    c = cs[0]
    n = (day - _day(c.get("start_day"))).days
    if n == 0:
        return None                       # такую pick нашёл бы сам; здесь не судим
    return {"kind": "late" if n > 0 else "early", "days": abs(n), "cand": c}


def mismatch_line(mm):
    """Исход day_mismatch (late / early) → строка правила владельца: позже брони — оплата с ИСХОДНОЙ даты, если перенос
    не согласован заранее; раньше — переоформить на фактические даты."""
    start = dm((mm.get("cand") or {}).get("start_day"))
    if mm.get("kind") == "late":
        return W_LATE % (mm.get("days"), start, start)
    return W_EARLY % (mm.get("days"), start)


def many_line(bike, on_day, cands):
    """Броней номера на другие дни несколько → адресный вопрос с их перечнем (не больше ROWS_SHOWN, дальше «и ещё»)."""
    cs = [c for c in cands or [] if isinstance(c, dict)]
    items = [W_MANY_ITEM % (c.get("row") if c.get("row") is not None else "?", dm(c.get("start_day")),
                            _s(c.get("name")) or "?") for c in cs[:CR.ROWS_SHOWN]]
    more = len(cs) - CR.ROWS_SHOWN
    listed = ", ".join(items) + (" и ещё %d" % more if more > 0 else "")
    return W_MANY % (bike, dm(on_day), listed)
