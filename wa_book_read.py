# -*- coding: utf-8 -*-
"""wa_book_read.py — брони агента WhatsApp ТОЛЬКО НА ЧТЕНИЕ: «свободен ли байк на даты» и «когда кончается
аренда клиента» (WABOOKTOOLS0210, задание 0121a-78d.0210; предложение BOOKSRC0210 §6).

Повод — запись владельца 02.10.2026-1 п.6: брони открыты агенту только на чтение. Источник — лист «клиенты»
книги «менеджеру Байки» через GET-дверь моста `clients` (filter=all) и парк — дверь `fleet`. BOOKSRC0210: счёт
по одному ответу `clients` правилом двери цены совпал с самой дверью на 38 из 38 юнитов.

СЕТИ ЗДЕСЬ НЕТ. Двери дают вызывающие:
  clients() → ответ моста `clients` со всеми строками  — `BridgeClient().clients(filter="all")`
  fleet()   → ответ моста `fleet`                      — `BridgeClient().fleet`
  door(unit, ds, de) → dict | None                     — `BridgeClient().quote_price` (сверка «свободен»)
Импорты — только stdlib без сети и `wa_agent_knowledge` (тест по ast).

СНИМОК — `Snapshot`: строки `clients` и парк ВМЕСТЕ, в памяти, перечитываются не чаще TTL (10 мин) и только когда
о бронях спросили. Неудачное чтение снимок не затирает и не освежает: возраст честно растёт. Старше MAX_AGE
(30 мин) снимок фактом не служит — «не знаю». Пустой ответ двери прочитанным не считается: пустой лист броней
сказал бы «всё свободно».

ЗАНЯТОСТЬ — копия правила двери цены (`QuotePrice.js:227–246`): строка занимает байк, если статус «Бронь» либо
«В аренде» при B≠ON; байк — то же имя после `quoteNorm_`; пересечение по дням включительно (даты усечены до
дня, как `quoteParseDate_`). Строже двери в одну сторону — юнит «не проверено», а не «свободен», если у него
просроченная активная аренда, рукописный статус (не «Бронь», не «В аренде», не «Завершена») или занимающая
строка без читаемых дат (дверь такую строку пропускает).

free_bikes — исходы: free (по снимку есть свободный юнит, и ОДНА дверь цены на него сказала available) · busy
(прочитаны ВСЕ юниты модели, и все заняты) · unknown (снимка нет или он старше 30 мин, модели нет в парке, дверь
цены не подтвердила, свободных нет, но есть «не проверено»). Наружу — число свободных и всего, без строк броней.

rental_end — последние 9 цифр номера WhatsApp против телефонов в столбце U «контакты» активных аренд («В аренде»,
B≠ON). Исходы: found (каждая аренда — модель и конец; конец прошёл — «по таблице срок истёк», без даты фактом) ·
unknown (снимка нет, номер не найден, дата конца не прочитана). «Не найден» — это «не знаю», а не «аренды нет»:
по BOOKSRC0210 по номеру WhatsApp находится 5 из 14 активных аренд. Имя, залог, долг и контакты наружу не идут:
у факта нет таких полей.
"""

import datetime
import re

import wa_agent_knowledge as K

TTL = 600                    # снимок перечитывается не чаще раза в 10 мин
MAX_AGE = 1800               # старше 30 мин — фактом не служит
PHUKET_OFFSET = 7 * 3600     # зона скрипта моста; тест сверяет с wa_history.PHUKET_OFFSET
KEY_DIGITS = 9               # последние цифры номера (BOOKSRC0210 §4: местный формат в таблице)

FREE, BUSY, FOUND, UNKNOWN = "free", "busy", "found", "unknown"
UNIT_FREE, UNIT_BUSY, UNIT_UNCHECKED = "free", "busy", "unchecked"

ST_BOOKED, ST_RENTED, ST_DONE = "бронь", "в аренде", "завершена"
KNOWN_STATUSES = frozenset((ST_BOOKED, ST_RENTED, ST_DONE))

R_BOOKING = "booking"
R_AVAIL_UNKNOWN = "availability_unknown"
R_RENTAL_EXPIRED = "rental_expired"
R_RENTAL_UNKNOWN = "rental_unknown"
W_BOOKING = "бронь оформляет человек — агент брони только читает"
W_AVAIL_UNKNOWN = "наличие не проверено — решает человек"
W_RENTAL_EXPIRED = "по таблице срок аренды истёк — уточнит менеджер"
W_RENTAL_UNKNOWN = "конец аренды не найден — уточнит человек"
EXPIRED_WORDS = "по таблице срок истёк — уточню у менеджера"


# ------------------------------- вопросы клиента -------------------------------

_RX_AVAIL = re.compile(
    r"(?i)свобод|налич(ие|ии|ия)|брон|занят|есть\s+ли|есть\s*\?|будет\s+ли|available|availab|\bbook|reserv|"
    r"do\s+you\s+have|have\s+you\s+got|is\s+there|are\s+there|\bany\b|\bfree\b")
_RX_BOOK = re.compile(r"(?i)заброн|бронир|\bброн[ьюи]\b|оформ\w*|\bbook\b|\bbooking|reserv")
_RX_TERM = re.compile(
    r"(?i)(конец|окончани\w*|срок\w*)\s+(мо(ей|его)\s+|наш(ей|его)\s+)?аренд|"
    r"(rental|rent|lease)\s+(end|ends|ending|expir\w*|period)")
_RX_WHEN = re.compile(r"(?i)\b(когда|во\s+сколько|к\s+как(ому|ой)|when)\b")
_RX_UNTIL = re.compile(
    r"(?i)до\s+как(ого|ой)\s+(числа|даты|дня|времени|часа)|\b(until|till)\s+(when|what\s+(date|day|time))")
_RX_RETURN = re.compile(
    r"(?i)\b(сда(ть|вать|ю|ём|ем)|верну(ть)?|возвра(щать|тить|щаю|щу))\b|\breturn\b|"
    r"\b(give|bring)\s+(it\s+|the\s+\w+\s+)?back\b|\bdrop\s+(it\s+)?off\b")
_RX_END = re.compile(r"(?i)конча\w*|законч\w*|заканчива\w*|истека\w*|ист[её]к\w*|\bend(s|ing)?\b|expir\w*|\bdue\b")
_RX_RENTAL = re.compile(r"(?i)аренд|прокат|байк|скутер|мотоцикл|\bbike|scooter|motorbike|rental|\brent\b|lease")


def avail_ask(text):
    """Спрашивает ли клиент о свободном байке (слово наличия). Модель и даты проверяет вызывающий."""
    return _RX_AVAIL.search(str(text or "")) is not None


def book_intent(text):
    """Просит ли клиент бронь — её делает человек, агент брони только читает."""
    return _RX_BOOK.search(str(text or "")) is not None


def rental_end_ask(text):
    """Спрашивает ли клиент, когда кончается его аренда (когда сдавать байк)."""
    s = str(text or "")
    return bool(_RX_TERM.search(s)
                or (_RX_UNTIL.search(s) and _RX_RENTAL.search(s))
                or (_RX_WHEN.search(s) and (_RX_RETURN.search(s) or (_RX_END.search(s) and _RX_RENTAL.search(s)))))


# ------------------------------- строки таблицы -------------------------------

def qnorm(s):
    """quoteNorm_ моста: нижний регистр, кириллические «сс» → cc и «с» → c, обрезка."""
    return str(s or "").lower().replace("сс", "cc").replace("с", "c").strip()


_RX_YMD = re.compile(r"^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_RX_DMY = re.compile(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})")
_RX_HM = re.compile(r"(\d{1,2}):(\d{2})")


def day_of(value):
    """Дата строки → date | None — как quoteParseDate_ моста: yyyy-mm-dd или dd.mm.yyyy, до дня."""
    s = str(value or "").strip()
    try:
        m = _RX_YMD.match(s)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = _RX_DMY.match(s)
        if m:
            y = int(m.group(3))
            return datetime.date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return None


def moment_of(value):
    """Конец аренды «yyyy-MM-dd HH:mm» (формат двери clients, зона Пхукета) → datetime | None.
    Без времени — None: «дата и время конца» без времени фактом не служат."""
    d = day_of(value)
    m = _RX_HM.search(str(value or "")[10:])
    if d is None or m is None:
        return None
    try:
        return datetime.datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def status_of(row):
    return str(row.get("status") or "").strip().lower()


def is_busy(row):
    """Правило двери цены: «Бронь», либо «В аренде» при B≠ON."""
    st = status_of(row)
    return st == ST_BOOKED or (st == ST_RENTED and str(row.get("auto_cancel") or "").strip().upper() != "ON")


def is_active(row):
    """Активная аренда: «В аренде» при B≠ON (та же половина правила)."""
    return status_of(row) == ST_RENTED and str(row.get("auto_cancel") or "").strip().upper() != "ON"


def is_manual(row):
    """Рукописный статус: непустой и не из трёх известных («долг» и прочее)."""
    st = status_of(row)
    return bool(st) and st not in KNOWN_STATUSES


def rows_of(reply):
    """Ответ двери clients → [строка, …] | None. Пустой список — не прочитан: пустой лист броней сказал бы
    «всё свободно»."""
    if not isinstance(reply, dict) or not reply.get("ok"):
        return None
    src = reply.get("data") if isinstance(reply.get("data"), dict) else reply
    rows = src.get("clients") if isinstance(src, dict) else None
    if not isinstance(rows, list):
        return None
    rows = [r for r in rows if isinstance(r, dict)]
    return rows or None


def bikes_of(reply):
    """Ответ двери fleet → [байк, …] | None. Пустой парк — не прочитан."""
    if not isinstance(reply, dict) or not reply.get("ok"):
        return None
    src = reply.get("data") if isinstance(reply.get("data"), dict) else reply
    bikes = src.get("bikes") if isinstance(src, dict) else None
    if not isinstance(bikes, list):
        return None
    bikes = [b for b in bikes if isinstance(b, dict) and str(b.get("name") or "").strip()]
    return bikes or None


def local_now(now):
    """Эпоха → «сейчас» Пхукета без зоны (в той же зоне, что даты двери)."""
    return datetime.datetime.fromtimestamp(now + PHUKET_OFFSET, datetime.timezone.utc).replace(tzinfo=None)


# ------------------------------- снимок -------------------------------

class Snapshot:
    """Строки clients и парк вместе. `get(now)` → (строки, парк, возраст, почему); строки None — фактом не служит."""

    def __init__(self, clients, fleet, ttl=TTL, max_age=MAX_AGE):
        self.clients, self.fleet = clients, fleet
        self.ttl, self.max_age = ttl, max_age
        self.rows = self.bikes = self.taken_at = None
        self.why = "ещё не читался"
        self.reads = 0

    def age(self, now):
        return None if self.taken_at is None else max(0.0, now - self.taken_at)

    def refresh(self, now):
        age = self.age(now)
        if age is not None and age < self.ttl:
            return
        self.reads += 1
        try:
            rows = rows_of(self.clients())
            bikes = bikes_of(self.fleet()) if rows is not None else None
        except Exception as e:                     # noqa: BLE001 — отказ моста ≠ «броней нет»
            self.why = "мост не отвечает (%s)" % type(e).__name__
            return
        if rows is None:
            self.why = "дверь clients не дала строк"
            return
        if bikes is None:
            self.why = "дверь fleet не дала парка"
            return
        self.rows, self.bikes, self.taken_at, self.why = rows, bikes, now, ""

    def get(self, now):
        self.refresh(now)
        age = self.age(now)
        if age is None:
            return None, None, None, self.why
        if age > self.max_age:
            return None, None, age, "снимок старше %d мин (%s)" % (self.max_age // 60, self.why or "не освежён")
        return self.rows, self.bikes, age, ""


def _mins(age):
    return int((age or 0) // 60)


# ------------------------------- свободен ли байк -------------------------------

def unit_state(unit, rows, ds, de, now_local):
    """Юнит на дни [ds, de] → (free | busy | unchecked, почему). Пересечения — правилом двери цены."""
    want = qnorm(unit)
    conflicts = 0
    for r in rows:
        if qnorm(r.get("bike")) != want:
            continue
        if is_manual(r):
            return UNIT_UNCHECKED, "рукописный статус"
        if not is_busy(r):
            continue
        rs, re_ = day_of(r.get("date_start")), day_of(r.get("date_end"))
        if rs is None or re_ is None:
            return UNIT_UNCHECKED, "занимающая строка без дат"
        if is_active(r):
            end = moment_of(r.get("date_end"))
            if (end < now_local) if end is not None else (re_ < now_local.date()):
                return UNIT_UNCHECKED, "просроченная активная аренда"
        if rs <= de and re_ >= ds:
            conflicts += 1
    return (UNIT_BUSY if conflicts else UNIT_FREE), "пересечений %d" % conflicts


def _avail_base(model, ds, de, units, age):
    return {"outcome": UNKNOWN, "model": model, "date_start": ds.isoformat() if ds else None,
            "date_end": de.isoformat() if de else None, "units": len(units or ()), "free": 0, "busy": 0,
            "unchecked": 0, "age": age, "door_calls": 0, "why": "", "line": ""}


def _avail_unknown(res, why):
    res.update(outcome=UNKNOWN, why=why,
               line="НАЛИЧИЕ: НЕИЗВЕСТНО — %s. Не говори ни «есть», ни «нет», ни «свободен»; скажи, что коллега "
                    "проверит наличие на эти даты и вернётся." % why)
    return res


def free_bikes(model, units, ds, de, rows, age, why, now_local, door):
    """Модель на даты → словарь исхода (см. шапку). Дверь цены — НЕ БОЛЕЕ ОДНОГО раза и только перед «свободен»."""
    res = _avail_base(model, ds, de, units, age)
    if rows is None:
        return _avail_unknown(res, "таблица броней не прочитана (%s)" % (why or "причина не названа"))
    if not model or not units:
        return _avail_unknown(res, "модели нет в парке")
    if ds is None or de is None or de <= ds:
        return _avail_unknown(res, "срок не разобран")
    free = []
    for u in units:
        st, _ = unit_state(u, rows, ds, de, now_local)
        res[st] += 1
        if st == UNIT_FREE:
            free.append(u)
    if free:
        if door is None:
            return _avail_unknown(res, "двери цены нет — «свободен» не сверен")
        res["door_calls"] = 1
        try:
            q = door(free[0], ds.isoformat(), de.isoformat())
        except Exception as e:                     # noqa: BLE001
            return _avail_unknown(res, "дверь цены упала (%s) — «свободен» не сверен" % type(e).__name__)
        if not isinstance(q, dict) or q.get("ok") is False:
            return _avail_unknown(res, "дверь цены не ответила — «свободен» не сверен")
        if q.get("available") is not True:
            return _avail_unknown(res, "дверь цены не подтвердила свободный юнит — таблица и дверь разошлись"
                                  if q.get("available") is False else "дверь цены не сказала о наличии")
        res.update(outcome=FREE, why="",
                   line="НАЛИЧИЕ (таблица броней, снимок %d мин назад; свободный юнит сверен дверью цены): %s, "
                        "%s — %s: свободно %d из %d. Можно сказать, что на эти даты байк есть. Бронь не обещай и "
                        "не оформляй — её делает человек; «забронировано» не говори."
                        % (_mins(age), model, res["date_start"], res["date_end"], res["free"], res["units"]))
        return res
    if res["unchecked"]:
        return _avail_unknown(res, "свободных по таблице нет, но не проверено юнитов: %d" % res["unchecked"])
    res.update(outcome=BUSY, why="",
               line="НАЛИЧИЕ (таблица броней, снимок %d мин назад; прочитаны все юниты модели): %s, %s — %s: "
                    "заняты все %d. Можно сказать, что на эти даты этой модели нет; другие модели и даты не "
                    "обещай — предложи, что коллега подберёт." % (_mins(age), model, res["date_start"],
                                                                  res["date_end"], res["units"]))
    return res


# ------------------------------- когда кончается аренда -------------------------------

_RX_PHONE = re.compile(r"\+?\d[\d\s\-().]{7,}\d")
_RX_DIGITS = re.compile(r"\d{9,15}")


def phone_keys(contacts):
    """Столбец «контакты» → множество последних 9 цифр телефонов в нём (телефоны с разделителями и сплошные)."""
    s = str(contacts or "")
    keys = set()
    for m in _RX_PHONE.finditer(s):
        d = re.sub(r"\D", "", m.group(0))
        if KEY_DIGITS <= len(d) <= 15:
            keys.add(d[-KEY_DIGITS:])
    for m in _RX_DIGITS.finditer(s):
        keys.add(m.group(0)[-KEY_DIGITS:])
    return keys


def _rental_unknown(res, why):
    res.update(outcome=UNKNOWN, why=why,
               line="АРЕНДА КЛИЕНТА: НЕИЗВЕСТНО — %s. НЕ говори «у вас нет аренды» и не называй дату; скажи, что "
                    "уточнишь у менеджера." % why)
    return res


def rental_end(number, rows, age, why, now_local, model_of):
    """Номер WhatsApp → словарь исхода (см. шапку): rentals = [{model, end | None, expired}] по датам."""
    res = {"outcome": UNKNOWN, "rentals": [], "expired": 0, "age": age, "why": "", "line": ""}
    if rows is None:
        return _rental_unknown(res, "таблица броней не прочитана (%s)" % (why or "причина не названа"))
    digits = re.sub(r"\D", "", str(number or ""))
    if len(digits) < KEY_DIGITS:
        return _rental_unknown(res, "номер короче %d цифр" % KEY_DIGITS)
    key = digits[-KEY_DIGITS:]
    hits = []
    for r in rows:
        if is_active(r) and key in phone_keys(r.get("contacts")):
            hits.append({"model": model_of(r.get("bike")), "end": moment_of(r.get("date_end"))})
    if not hits:
        return _rental_unknown(res, "по номеру WhatsApp активная аренда в таблице не найдена (номер там часто "
                                    "записан иначе) — это «не знаю», а не «аренды нет»")
    if any(h["end"] is None for h in hits):
        return _rental_unknown(res, "дата и время конца аренды в таблице не прочитаны")
    hits.sort(key=lambda h: h["end"])
    for h in hits:
        h["expired"] = h["end"] < now_local
    res["rentals"], res["expired"] = hits, sum(1 for h in hits if h["expired"])
    items = ["%s — %s" % (h["model"], ("по таблице срок истёк" if h["expired"]
                                       else "конец %s (Пхукет)" % h["end"].strftime("%d.%m.%Y %H:%M")))
             for h in hits]
    res.update(outcome=FOUND, why="",
               line="АРЕНДА КЛИЕНТА (таблица броней по номеру WhatsApp, снимок %d мин назад; аренд: %d): %s. "
                    "Называй только модель и время конца; где срок истёк — дату фактом не называй, скажи: «%s». "
                    "Имени, залога и долга ты не знаешь." % (_mins(age), len(hits), "; ".join(items), EXPIRED_WORDS))
    return res


# ------------------------------- «нужен человек» -------------------------------

def adjust_reasons(reasons, avail, rental, ask):
    """Причины кода (`K.handoff`) + факты броней → причины. Факт наличия есть — «агент их не видит» снимается
    (бронь словами клиента — «бронь оформляет человек»); факта нет — «наличие не проверено». Аренда: срок
    истёк или не найдена — причина. Порядок прежний, новые — в конце."""
    out = [dict(r) for r in reasons]
    if avail is not None:
        out = [r for r in out if r.get("reason") != K.R_AVAILABILITY]
        if avail["outcome"] in (FREE, BUSY):
            if book_intent(ask):
                out.append({"reason": R_BOOKING, "words": W_BOOKING, "why": "просьба о брони"})
        else:
            out.append({"reason": R_AVAIL_UNKNOWN, "words": W_AVAIL_UNKNOWN, "why": avail["why"]})
    if rental is not None:
        if rental["outcome"] == UNKNOWN:
            out.append({"reason": R_RENTAL_UNKNOWN, "words": W_RENTAL_UNKNOWN, "why": rental["why"]})
        elif rental["expired"]:
            out.append({"reason": R_RENTAL_EXPIRED, "words": W_RENTAL_EXPIRED, "why": "срок прошёл"})
    return out
