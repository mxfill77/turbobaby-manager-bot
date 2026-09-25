# -*- coding: utf-8 -*-
"""ПОЛОЖЕНИЕ БАЙКА НА МОМЕНТ СООБЩЕНИЯ — ОДНА ФУНКЦИЯ (25.09.2026, задание Штаба 0033-74b.2509).

СЛОВО ВЛАДЕЛЬЦА 25.09: совет «помыть, воск, чехол» (подсказка C) звучит ТОЛЬКО когда байк на базе
ПОСЛЕ ВОЗВРАТА и ещё не помыт. В аренде, в ремонте, перед выдачей и при неизвестном положении — молчит.
До этого C вызывался по КАРТИНКЕ (vision сказал «грязно»), а гасился лишь сервисными словами самого
сообщения: живой случай 21.09, VULCAN 650 S 5065 — в 04:54 бот сам принял три работы по байку, а в
06:16 по снимку разобранного байка посоветовал помыть его и накрыть чехлом.

ЗАМЕР ДО КОДА (живой splinter.log, окно 11.09 13:25 → 25.09 13:25 UTC; артефакт ПК
`2026-09-25-POMYTZAMER2509.md`, срез 11.09 14:40 → 25.09 14:40 UTC — те же 11 советов): советов C 11
(отправлено 7, подавлено замком 4). По журнальным ногам источников: РЕМОНТ 4, НЕИЗВЕСТНО 7, ВОЗВРАТ 0
(сигналов возврата за 14 суток — ни одного); за всё время журнала советов C 18, ВОЗВРАТ ровно 1.

ПОЛОЖЕНИЙ ШЕСТЬ, и ровно одно на сообщение:
    ВОЗВРАТ     байк вернулся из аренды (сообщение говорит «вернул», либо свой след возврата/CRM
                говорит, что аренда кончилась сегодня или вчера) и мойки после этого не было;
    В АРЕНДЕ    CRM/парк говорят «В аренде», а своего следа возврата после начала аренды нет;
    РЕМОНТ      работы или сервис-слова в этом сообщении или в теме за последние N часов,
                разобранный байк на снимке, открытая заявка на ТО, парк «В ремонте»;
    ВЫДАЧА      слова выдачи, бронь начинается сегодня или завтра, свой след выдачи за сутки;
    ПОМЫТ       мойка названа в этом сообщении либо записана ПОСЛЕ начала текущего цикла возврата;
    НЕИЗВЕСТНО  источники молчат или не прочитаны. Это НЕ «можно советовать».

ПОРЯДОК СИЛЫ — и почему именно такой.
  1 мойка в ЭТОМ сообщении — самое свежее знание о байке;
  2 возврат в ЭТОМ сообщении — «возврат выигрывает» (тот же принцип, что у `_ret_ctx`: деньги и
    закрытие важнее косметики), поэтому он сильнее выдачи и сервиса того же сообщения;
  3 выдача в ЭТОМ сообщении;
  4 сервис: сообщение → память темы за N часов → открытая заявка → парк «В ремонте»;
  5 CRM «В аренде» (если СВОЙ след возврата не новее начала аренды — CRM запаздывает за людьми);
  6 бронь сегодня/завтра, свой след выдачи за сутки;
  7 возврат по истории (свой след, CRM) — только сегодня или вчера по местному времени;
  8 иначе НЕИЗВЕСТНО.
Ошибка порядка стоит молчания, а не лишнего совета: C звучит только на ВОЗВРАТЕ.

N ИЗ ЗАМЕРА. Промежутки «сервисный сигнал → следующее сообщение той же темы» по всему журналу
(01.06 → 25.09, 66 промежутков): кластер сессии 0.001…4.70 ч, дальше ПУСТО до 15.23 ч, затем
27…2026 ч. N = 10 ч — середина пустого промежутка (4.70; 15.23); любое N из него делит корпус
одинаково. Ручка `POS_SERVICE_H` (часы), умолчание `SERVICE_H_DEFAULT`.

ЦИКЛ ВОЗВРАТА. Совет C — один раз за цикл по байку. Цикл называется АРЕНДОЙ, которая кончилась
(номер брони CRM, иначе её начало), и только если CRM не прочитан — местной датой возврата. Так два
разных источника одного и того же возврата (слово «вернул» в 10:00 и «Завершена» в CRM в 12:00) дают
ОДИН цикл, а не два совета. Мойка «после возврата» — это мойка ПОСЛЕ НАЧАЛА цикла.

ЧИСТОТА. Импорты ровно два — `re` и `work_intent` (одно определение вопроса на все гейты: «помыл?» —
вопрос, а не отчёт о мойке). Моста, записи, сети и своих часов здесь нет: «сейчас» и факты приносят
руки (`splinter._pos_facts`), решение не бросает никогда.
"""
import re

import work_intent

RETURN = "возврат"
RENT = "в аренде"
REPAIR = "ремонт"
ISSUE = "выдача"
WASHED = "помыт"
UNKNOWN = "неизвестно"
STATES = (RETURN, RENT, REPAIR, ISSUE, WASHED, UNKNOWN)

#: N — окно «сервис в теме недавно», часы (из замера, см. шапку).
SERVICE_H_DEFAULT = 10.0
#: Пхукет: CRM отдаёт даты в часовом поясе таблицы, «сегодня/вчера/завтра» — по местным суткам.
TZ_H = 7
#: Дрожание часов между машинами: запись «из будущего» ближе этого — ещё настоящее.
SKEW_SEC = 300
#: Свой след выдачи считается выдачей не дольше суток — дальше байк уже у клиента или вернулся.
ISSUE_EVENT_H = 24.0

#: Источники — словами (попадают в строку события и в журнал).
SRC_MSG = "сообщение"
SRC_MEM = "память темы"
SRC_EVENTS = "события"
SRC_REQUEST = "заявка"
SRC_FLEET = "парк"
SRC_CRM = "CRM"

#: След возврата, который пишет САМ этот модуль (руки кладут его в notes строки событий). Только
#: возврат, названный СООБЩЕНИЕМ: производный «возврат по истории» следом не является, иначе метка
#: сама себя продлевала бы каждой новой строкой.
RETURN_MARK = "положение: возврат (сообщение)"

# --- мойка: отчёт о сделанном, а не просьба -----------------------------------------------------
#: «помыть»/«надо помыть» — просьба (инфинитив), мойкой не является; формы прошедшего — являются.
_WASH_RU = re.compile(r"(?<![а-яё])(?:по|вы|от)мы(?:л[аио]?|т[аоы]?)(?![а-яё])")
_WASH_RU_NOUN = re.compile(r"(?<![а-яё])мойк[аи]\s+(?:сделан\w*|готов\w*|есть)")
_WASH_EN = re.compile(r"\b(?:washed|wash(?:ing)?\s+(?:done|finished|ok))\b")
_WASH_TH = ("ล้างแล้ว", "ล้างรถแล้ว", "ล้างเสร็จ", "ล้างเรียบร้อย")
_WASH_NOT_RU = re.compile(r"(?<![а-яё])(?:не|ещё\s+не|еще\s+не)\s+(?:по|вы|от)мы(?:л[аио]?|т[аоы]?)(?![а-яё])")
_WASH_NOT_EN = re.compile(r"\b(?:not|never|didnt|didn't|isnt|isn't|wasnt|wasn't)\s+(?:yet\s+)?washed\b")
_WASH_NOT_TH = ("ยังไม่ล้าง", "ไม่ได้ล้าง", "ไม่ล้าง")

# --- сервисная речь: запасной признак поверх разбора (работы, заявка, подпись-указание) ---------
#: Слов топлива здесь НЕТ намеренно: «น้ำมันเต็ม» (бак полный) — речь ВОЗВРАТА, а не ремонта, и тайское
#: «น้ำมัน» одно и то же слово для масла и бензина. Масло ловится глаголом замены и разбором работ.
_SVC_RU = re.compile(
    r"(?<![а-яё])(?:ремонт\w*|почин\w*|замен\w*|поменя\w*|меня(?:ю|ем|ть)|разобр\w*|разбор\w*|"
    r"собрал\w*|снял\w*|сняли|снят\w*|колодк\w*|масл[оау]\w*|цеп[ьи]|тормоз\w*|аккумулятор\w*|"
    r"свеч\w*|фильтр\w*|подшипник\w*|диагност\w*|сломал\w*|сломан\w*|течёт|течет|подтека\w*)"
    r"|не\s+работает")
_SVC_EN = re.compile(r"\b(?:repair\w*|fix\w*|service\w*|replac\w*|chang(?:e|ed|ing)|broken|brake\w*|"
                     r"pads?|oil|chain|battery|spark|filter|bearing\w*|disassembl\w*|leak\w*)\b")
_SVC_TH = ("ซ่อม", "เปลี่ยน", "ถอด", "ประกอบ", "เบรก", "ถ่ายน้ำมัน", "โซ่", "แบต", "ไส้กรอง")
_SVC_TH_BROKEN = re.compile("เสีย(?!ง)")


def _low(text):
    return str(text or "").lower()


def wash_said(text):
    """Слова человека говорят, что байк ПОМЫТ? Вопрос и отрицание — не мойка. Не бросает:
    на вход идёт `str(...)`, а разбор строки шаблоном исключений не порождает."""
    s = _low(text)
    said = bool(_WASH_RU.search(s) or _WASH_RU_NOUN.search(s) or _WASH_EN.search(s)
                or any(w in s for w in _WASH_TH))
    denied = bool(_WASH_NOT_RU.search(s) or _WASH_NOT_EN.search(s) or any(w in s for w in _WASH_NOT_TH))
    return said and not denied and not work_intent.asks(s)


def service_said(text):
    """Сервисная речь в тексте (работы, поломка, разборка). Запасной признак: основной — разбор
    сообщения (работы, `repair`/`intake`, подпись-указание), который руки приносят сами."""
    s = _low(text)
    return bool(_SVC_RU.search(s) or _SVC_EN.search(s) or any(w in s for w in _SVC_TH)
                or _SVC_TH_BROKEN.search(s))


# --- время: только арифметика, своих часов нет ----------------------------------------------------
def _days(y, m, d):
    """Дни от 1970-01-01 для григорианской даты (алгоритм days_from_civil)."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


_MON = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12}
_RX_ISO = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?"
                     r"\s*(Z|[+-]\d{2}:?\d{2})?")
_RX_RU = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s*,?\s*(\d{1,2}):(\d{2}))?")
_RX_JS = re.compile(r"([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s+GMT([+-]\d{4})")


def when(s, tz_h=TZ_H):
    """Строка времени из таблицы → секунды эпохи или None. Без пояса — местное время таблицы.
    Живые формы: ISO с `Z`/поясом (`recorded_at`), 'YYYY-MM-DD HH:MM' и 'DD.MM.YYYY[ , HH:MM]'
    (CRM, см. `splinter._date_start_key`), дата JS 'Fri Sep 25 2026 13:44:12 GMT+0700'."""
    try:
        t = str(s or "").strip()
        if not t:
            return None
        m = _RX_JS.search(t)
        if m and m.group(1).lower() in _MON:
            off = int(m.group(7)[0] + "1") * (int(m.group(7)[1:3]) * 3600 + int(m.group(7)[3:5]) * 60)
            return (_days(int(m.group(3)), _MON[m.group(1).lower()], int(m.group(2))) * 86400
                    + int(m.group(4)) * 3600 + int(m.group(5)) * 60 + int(m.group(6)) - off)
        m = _RX_ISO.search(t)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
            z = m.group(7)
            if z == "Z":
                off = 0
            elif z:
                zz = z.replace(":", "")
                off = int(zz[0] + "1") * (int(zz[1:3]) * 3600 + int(zz[3:5]) * 60)
            else:
                off = int(tz_h) * 3600
            return _days(y, mo, d) * 86400 + hh * 3600 + mm * 60 + ss - off
        m = _RX_RU.search(t)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            hh, mm = int(m.group(4) or 0), int(m.group(5) or 0)
            return _days(y, mo, d) * 86400 + hh * 3600 + mm * 60 - int(tz_h) * 3600
    except Exception:
        return None
    return None


def local_day(epoch, tz_h=TZ_H):
    """Номер местных суток (для «сегодня/вчера/завтра»)."""
    return int((float(epoch) + int(tz_h) * 3600) // 86400)


def day_label(epoch, tz_h=TZ_H):
    """Местная дата словами 'YYYY-MM-DD' (метка цикла без CRM)."""
    z = local_day(epoch, tz_h) + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return "%04d-%02d-%02d" % (y + (m <= 2), m, d)


# --- факты таблиц → нормальная форма (руки отдают сырые строки, разбор — здесь) -------------------
def events_from_items(items):
    """Строки `read_events` → [{type, at}], только то, что судит положение: возврат, выдача,
    мойка, работы. Строка без читаемого времени пропадает: без времени она ничего не доказывает."""
    out = []
    for it in items or []:
        try:
            et = str(it.get("event_type") or "").strip().lower()
            notes = str(it.get("notes") or "")
            at = when(it.get("recorded_at"))
            if at is None:
                at = when(it.get("msg_date"))
            if at is None:
                continue
            if et == "wash":
                typ = "wash"
            elif et == "return" or RETURN_MARK in notes:
                typ = "return"
            elif et == "handover":
                typ = "handover"
            elif et in ("repair", "intake"):
                typ = "service"
            else:
                continue
            out.append({"type": typ, "at": at})
        except Exception:
            continue
    return out


def rentals_from_rows(rows):
    """Строки CRM «клиенты» ОДНОГО байка → [{status, start, end, id}]. Статусы — живые слова
    листа (A): «Бронь», «В аренде», «Завершена»; прочие (отмена, пусто) судом не являются."""
    out = []
    for r in rows or []:
        try:
            st = str(r.get("status") or "").strip().lower()
            if st not in ("бронь", "в аренде", "завершена"):
                continue
            out.append({"status": st, "start": when(r.get("date_start")),
                        "end": when(r.get("date_end")),
                        "id": str(r.get("booking_id") or "").strip()
                        or ("строка %s" % r.get("row") if r.get("row") else "")})
        except Exception:
            continue
    return out


# --- решение ----------------------------------------------------------------------------------
def _out(state, why, src="", cycle="", cycle_start=None, unread=()):
    return {"state": state, "why": why, "src": src, "cycle": cycle,
            "cycle_start": cycle_start, "unread": list(unread)}


def _rental_for(rentals, moment):
    """Аренда, к которой относится момент: самая свежая, начавшаяся не позже него (+дрожание)."""
    best = None
    for r in rentals or []:
        s = r.get("start")
        if s is None or r.get("status") == "бронь":
            continue
        if s <= moment + SKEW_SEC and (best is None or s > best["start"]):
            best = r
    return best


def _cycle(rentals, moment):
    """Имя цикла возврата и его начало. Аренда известна → её номер и начало; иначе — дата."""
    r = _rental_for(rentals, moment)
    if r:
        return ("аренда " + (r.get("id") or day_label(r["start"]))), r["start"]
    return ("день " + day_label(moment)), moment


def _washed_since(events, start, now):
    return any(e.get("type") == "wash" and start is not None and start < e.get("at", 0) <= now + SKEW_SEC
               for e in events or [])


def position(facts=None):
    """Факты → положение байка. Возврат: {state, why, src, cycle, cycle_start, unread}. Не бросает.

    facts:
      now            секунды эпохи (обязательно; нет — НЕИЗВЕСТНО)
      service_h      N, часы (нет — SERVICE_H_DEFAULT)
      msg_wash / msg_return / msg_handover / msg_service / msg_disassembled   признаки сообщения
      svc_marks      [секунды] — сервис в этой теме (память процесса + свои строки работ)
      open_request   True/False/None — открытая заявка на ТО (None = не прочитано)
      fleet_status   строка статуса парка или None (не прочитан)
      rentals        rentals_from_rows(...) или None (CRM не прочитан)
      events         events_from_items(...) или None (свои события не прочитаны)
    """
    try:
        return _position(facts or {})
    except Exception as e:                          # решение не имеет права стать причиной падения
        return _out(UNKNOWN, "решение упало (%s) — молчим" % type(e).__name__)


def _position(f):
    now = f.get("now")
    if now is None:
        return _out(UNKNOWN, "время неизвестно")
    now = float(now)
    try:
        n_h = float(f.get("service_h") if f.get("service_h") is not None else SERVICE_H_DEFAULT)
    except (TypeError, ValueError):
        n_h = SERVICE_H_DEFAULT
    rentals = f.get("rentals")
    events = f.get("events")
    unread = [name for name, v in (("события", events), ("CRM", rentals)) if v is None]
    rentals = rentals or []
    events = events or []

    # 1–3: само сообщение
    if f.get("msg_wash"):
        return _out(WASHED, "мойка названа в этом сообщении", SRC_MSG)
    if f.get("msg_return"):
        cyc, start = _cycle(rentals, now)
        if _washed_since(events, start, now):
            return _out(WASHED, "возврат назван, но мойка после начала цикла уже записана",
                        SRC_EVENTS, cyc, start)
        return _out(RETURN, "возврат назван в этом сообщении", SRC_MSG, cyc, start, unread)
    if f.get("msg_handover"):
        return _out(ISSUE, "выдача названа в этом сообщении", SRC_MSG)

    # 4: сервис
    if f.get("msg_service"):
        return _out(REPAIR, "работы или сервис-слова в этом сообщении", SRC_MSG)
    if f.get("msg_disassembled"):
        return _out(REPAIR, "на снимке разобранный байк", SRC_MSG)
    win = n_h * 3600.0
    marks = [float(t) for t in (f.get("svc_marks") or []) if t is not None]
    marks += [e["at"] for e in events if e.get("type") == "service"]
    recent = [t for t in marks if -SKEW_SEC <= now - t <= win]
    if recent:
        ago = (now - max(recent)) / 3600.0
        return _out(REPAIR, "сервис в теме %.1f ч назад (окно %g ч)" % (max(ago, 0.0), n_h), SRC_MEM)
    if f.get("open_request") is True:
        return _out(REPAIR, "открыта заявка на ТО", SRC_REQUEST)
    fs = str(f.get("fleet_status") or "").strip().lower()
    if "ремонт" in fs:
        return _out(REPAIR, "парк: «%s»" % f.get("fleet_status"), SRC_FLEET)

    # свои следы возврата/выдачи (последние по времени, не из будущего)
    own_ret = [e["at"] for e in events if e.get("type") == "return" and e["at"] <= now + SKEW_SEC]
    own_ho = [e["at"] for e in events if e.get("type") == "handover" and e["at"] <= now + SKEW_SEC]
    last_ret = max(own_ret) if own_ret else None
    last_ho = max(own_ho) if own_ho else None

    # 5: аренда идёт — если свой след возврата не новее её начала
    active = [r for r in rentals if r.get("status") == "в аренде"
              and (r.get("start") is None or r["start"] <= now + SKEW_SEC)]
    in_rent = bool(active) or fs.startswith("в аренд")
    if in_rent:
        starts = [r["start"] for r in active if r.get("start") is not None]
        a_start = max(starts) if starts else None
        if not (last_ret is not None and (a_start is None or last_ret > a_start)
                and (last_ho is None or last_ret > last_ho)):
            return _out(RENT, "CRM/парк: «В аренде»", SRC_CRM if active else SRC_FLEET)

    today = local_day(now)
    # 6: выдача по брони и по своему следу
    for r in rentals:
        if r.get("status") == "бронь" and r.get("start") is not None:
            if local_day(r["start"]) in (today, today + 1):
                return _out(ISSUE, "бронь начинается %s" % ("сегодня" if local_day(r["start"]) == today
                                                            else "завтра"), SRC_CRM)
    if last_ho is not None and (last_ret is None or last_ho > last_ret) and now - last_ho <= ISSUE_EVENT_H * 3600:
        return _out(ISSUE, "свой след выдачи %.1f ч назад" % ((now - last_ho) / 3600.0), SRC_EVENTS)

    # 7: возврат по истории — только сегодня или вчера
    cands = []
    if last_ret is not None and local_day(last_ret) in (today, today - 1) \
            and (last_ho is None or last_ret > last_ho):
        cands.append((last_ret, SRC_EVENTS))
    ended = [r for r in rentals if r.get("end") is not None and r.get("status") in ("завершена", "в аренде")
             and r["end"] <= now + SKEW_SEC]
    if ended:
        last_end = max(ended, key=lambda r: r["end"])
        newer = [r for r in rentals if r.get("start") is not None and r is not last_end
                 and last_end.get("start") is not None and r["start"] > last_end["start"]
                 and r["start"] <= now + SKEW_SEC and r.get("status") != "бронь"]
        if not newer and local_day(last_end["end"]) in (today, today - 1) and not in_rent:
            cands.append((last_end["end"], SRC_CRM))
    if cands:
        moment, src = max(cands)
        cyc, start = _cycle(rentals, moment)
        if _washed_since(events, start, now):
            return _out(WASHED, "мойка записана после начала цикла возврата", SRC_EVENTS, cyc, start)
        return _out(RETURN, "возврат %s (%s)" % ("сегодня" if local_day(moment) == today else "вчера", src),
                    src, cyc, start, unread)

    why = "источники молчат"
    if unread:
        why += "; не прочитано: " + ", ".join(unread)
    return _out(UNKNOWN, why, "", "", None, unread)


# --- то, что из положения следует ------------------------------------------------------------------
def may_advise_wash(pos):
    """Совет C допустим? Ровно при ВОЗВРАТЕ с названным циклом; ПОМЫТ и всё прочее — молчание."""
    return bool(pos) and pos.get("state") == RETURN and bool(pos.get("cycle"))


def deposit_phrase(pos):
    """Фраза тревоги J «если это возврат — посмотри по депозиту» — только при ВОЗВРАТЕ."""
    return bool(pos) and pos.get("state") == RETURN


def hint_state(pos):
    """Состояние для замка повторов подсказки C: ЦИКЛ, а не «грязно». Тот же цикл — повтор."""
    return ("цикл возврата", (pos or {}).get("cycle") or "")


def note(pos):
    """Сегмент строки событий: положение и его источник. Возврат по сообщению — след RETURN_MARK."""
    st = (pos or {}).get("state") or UNKNOWN
    src = (pos or {}).get("src") or ""
    return "положение: %s%s" % (st, (" (%s)" % src) if src else "")
