# -*- coding: utf-8 -*-
"""wa_agent_knowledge.py — знания агента WhatsApp: цена, «нужен человек», узлы мозга, маска.

Шаг 4 плана WAAGENTLIVE0110 §7 (задание 0103-76t.0110). Решение владельца 01.10.2026 20:14
«Все ответы да»: цена — из той же двери, что у Telegram-бота (`bridge_client.quote_price`,
только чтение), модель — платный ключ. Модуль модель НЕ зовёт и ничего не отправляет: он
готовит то, что адаптер модели подаст в промпт, и список «нужен человек» для карточки.

СЕТИ ЗДЕСЬ НЕТ. Дверь цены, парк и чтение узла дают вызывающие:
  door(unit, date_start, date_end) → dict | None   — `BridgeClient().quote_price`
  units(model) → [имя юнита, …] | None             — резолв модели в юниты парка (`fleet`)
  read_doc(name) → ответ моста (dict)               — `lambda n: client._call("read_doc", name=n)`
Импорты — только stdlib без сети (тест по ast).

ТРИ ИСХОДА ЦЕНЫ, и ни один не подменяет другой:
  number  — число двери с разбивкой (сутки, ставка, итог, депозит) на срок внутри ОДНОГО сезона;
  human   — «эту цену считает человек» с причиной из списка ниже;
  unknown — проверить нечем (дверь молчит, парк не прочитан, дат нет). Не ноль и не «от».
Формы «от … ฿» нет ни на одной дороге: смешанный период уходит человеку ДО двери.

Причины «нужен человек» — кодом, список закрыт: наличие и брони; срок через границу сезонов;
модель без цены; срок от 30 суток; скидка или уступка; дверь не дала числа; повреждения,
штрафы, депозит, споры, оплаты; язык не русский и не английский.
"""

import datetime
import re
import time

PRICE_NUMBER = "number"
PRICE_HUMAN = "human"
PRICE_UNKNOWN = "unknown"

R_AVAILABILITY = "availability"
R_SEASON_CROSS = "season_cross"
R_NO_PRICE_MODEL = "no_price_model"
R_LONG_TERM = "long_term"
R_DISCOUNT = "discount"
R_DOOR_NO_PRICE = "door_no_price"
R_MONEY = "money_dispute"
R_LANGUAGE = "language"

# Порядок — порядок строк в карточке. Слова без цифр: они уходят и в промпт.
REASONS = (
    (R_AVAILABILITY, "наличие и брони — агент их не видит"),
    (R_SEASON_CROSS, "срок через границу сезонов"),
    (R_NO_PRICE_MODEL, "модель без цены"),
    (R_LONG_TERM, "срок от месяца и дольше"),
    (R_DISCOUNT, "скидка или уступка — решение человека"),
    (R_DOOR_NO_PRICE, "дверь цены не дала числа"),
    (R_MONEY, "повреждения, штрафы, депозит, споры или оплаты"),
    (R_LANGUAGE, "язык не русский и не английский"),
)
REASON_WORDS = dict(REASONS)

LONG_TERM_DAYS = 30

# Границы сезонов — копия `season.periods` файла цен ПК (`price_source.json`, sha256 fad920dd9e4cb3e8…,
# версия 1 от 02.09.2026; снята 01.10.2026). На сервере файла цен нет. Копия — данные владельца:
# перепишет он календарь — правится эта таблица, а не логика.
SEASON_PERIODS = (
    ("P1", "06-01", "09-30", False),
    ("P2", "10-01", "10-31", False),
    ("P3", "11-01", "11-30", False),
    ("P4", "12-01", "12-14", False),
    ("P5", "12-15", "02-05", True),
    ("P6", "02-06", "03-31", False),
    ("P7", "04-01", "04-30", False),
    ("P8", "05-01", "05-15", False),
    ("P9", "05-16", "05-31", False),
)

NODES = ("faq", "business_rules")


# ------------------------------- даты и сезоны -------------------------------

def _date(value):
    """Дата | 'ГГГГ-ММ-ДД' | 'ДД.ММ.ГГГГ' → date | None. Не дата — «не знаю», а не сегодня."""
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    s = "" if value is None else str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _md(s):
    m, d = s.split("-")
    return int(m), int(d)


def period_of(day, periods=SEASON_PERIODS):
    """Дата → ключ периода | None. Период через новый год сравнивается двумя половинами."""
    md = (day.month, day.day)
    for key, f, t, crosses_year in periods:
        lo, hi = _md(f), _md(t)
        if crosses_year:
            if md >= lo or md <= hi:
                return key
        elif lo <= md <= hi:
            return key
    return None


def season_span(ds, de, periods=SEASON_PERIODS):
    """Срок → ('one'|'crosses'|'unknown', [ключи периодов по порядку]). Обе даты входят в срок,
    проверяется КАЖДЫЙ день: перекос в сторону «спроси человека» — лишний вопрос дешевле неверной цены."""
    seen = []
    day = ds
    while day <= de:
        key = period_of(day, periods)
        if key is None:
            return "unknown", seen
        if not seen or seen[-1] != key:
            seen.append(key)
        day += datetime.timedelta(days=1)
    if not seen:
        return "unknown", seen
    return ("one" if len(seen) == 1 else "crosses"), seen


# ------------------------------- цена -------------------------------

def _num(value):
    """Число двери → int | None. «Нет числа» никогда не становится нулём."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def has_price(q):
    """Несёт ли ответ двери цену — по тем же полям, что клиентская фраза ПК (`door_price.has_price`)."""
    if not isinstance(q, dict):
        return False
    text = q.get("text")
    if isinstance(text, str) and text.strip():
        return True
    return any(_num(q.get(k)) is not None for k in ("day_price", "total", "cap_price"))


def _norm(s):
    return re.sub(r"[^0-9a-zа-яё]+", "", str(s or "").lower())


def _money(n):
    return "{:,}".format(int(n)).replace(",", " ")


def _base(model, ds, de):
    return {"outcome": PRICE_UNKNOWN, "reason": None, "why": "", "model": model, "unit": None,
            "date_start": ds.isoformat() if ds else None, "date_end": de.isoformat() if de else None,
            "days": None, "day_price": None, "total": None, "deposit": None, "season": None,
            "door_calls": 0, "line": ""}


def _human(res, reason, why):
    res.update(outcome=PRICE_HUMAN, reason=reason, why=why,
               line="Эту цену считает человек: %s. Числа цены не называть — ни точного, ни «от», "
                    "ни диапазона, ни среднего; скажи, что коллега вернётся с точной суммой."
                    % REASON_WORDS[reason])
    return res


def _unknown(res, why):
    res.update(outcome=PRICE_UNKNOWN, reason=None, why=why,
               line="Цена НЕИЗВЕСТНА: проверить было нечем. Числа цены не называть — ни точного, "
                    "ни «от», ни диапазона, ни по памяти; скажи, что уточнишь у коллег.")
    return res


def quote(model, date_start, date_end, door, units, no_price_models=()):
    """Цена модели на даты → словарь исхода (см. шапку). Дверь зовётся НЕ БОЛЕЕ ОДНОГО раза и
    только когда все ворота пропустили: срок до месяца, один сезон, модель не в списке без цены."""
    ds, de = _date(date_start), _date(date_end)
    res = _base(model, ds, de)
    if not str(model or "").strip() or ds is None or de is None:
        return _unknown(res, "модели или дат нет")
    if de <= ds:
        return _unknown(res, "конец срока не позже начала")
    days = (de - ds).days                      # как у двери: разность дат (QuotePrice.js, CBQUOTE3009 §2)
    res["days"] = days
    if days >= LONG_TERM_DAYS:
        return _human(res, R_LONG_TERM, "%d сут." % days)
    verdict, keys = season_span(ds, de)
    if verdict == "unknown":
        return _unknown(res, "сезон не определён")
    if verdict == "crosses":
        return _human(res, R_SEASON_CROSS, " → ".join(keys))
    if _norm(model) in {_norm(m) for m in no_price_models}:
        return _human(res, R_NO_PRICE_MODEL, "модель в списке без цены")
    try:
        names = units(model)
    except Exception as e:                     # noqa: BLE001 — отказ парка ≠ «модели нет»
        return _unknown(res, "парк не прочитан (%s)" % type(e).__name__)
    if names is None:
        return _unknown(res, "парк не прочитан")
    names = [n for n in names if str(n or "").strip()]
    if not names:
        return _human(res, R_NO_PRICE_MODEL, "модели нет в парке — цену назвать нечем")
    res["unit"] = names[0]
    res["door_calls"] = 1
    try:
        q = door(names[0], ds.isoformat(), de.isoformat())
    except Exception as e:                     # noqa: BLE001
        return _unknown(res, "дверь цены упала (%s)" % type(e).__name__)
    if not isinstance(q, dict):
        return _unknown(res, "дверь цены не ответила")
    if q.get("ok") is False:
        return _unknown(res, "дверь цены ответила отказом")
    if not has_price(q):
        return _human(res, R_DOOR_NO_PRICE, "ответ двери без числа")
    total, day = _num(q.get("total")), _num(q.get("day_price"))
    if (total is not None and total <= 0) or (day is not None and day <= 0):
        return _human(res, R_NO_PRICE_MODEL, "дверь дала ноль")
    if total is None or day is None:
        return _human(res, R_DOOR_NO_PRICE, "нет итога или ставки за сутки")
    if _num(q.get("days")) != days:
        return _unknown(res, "дверь посчитала другой срок (%s сут.)" % q.get("days"))
    season = q.get("season")
    deposit = _num(q.get("deposit"))
    res.update(outcome=PRICE_NUMBER, reason=None, why="", day_price=day, total=total,
               deposit=deposit if deposit is not None and deposit >= 0 else None,
               season=season.get("label") if isinstance(season, dict) else None,
               model=q.get("model") or model)
    dep = ("депозит %s ฿" % _money(res["deposit"])) if res["deposit"] is not None \
        else "депозит — уточнит человек"
    res["line"] = "%s, %s — %s: %d сут., %s ฿ в сутки, итого %s ฿ за срок; %s." % (
        res["date_start"], res["date_end"], res["model"], days, _money(day), _money(total), dep)
    return res


# ------------------------------- «нужен человек» по тексту клиента -------------------------------

_TEXT_RULES = (
    (R_AVAILABILITY, re.compile(
        r"свобод|налич(ие|ии|ия)|брон|заброн|занят|available|availab|\bbook|reserv", re.I)),
    (R_DISCOUNT, re.compile(
        r"скидк|скидоч|дешевл|подешев|уступ|\bторг|сбав|discount|cheaper|lower\s+price|"
        r"better\s+price|best\s+price|promo", re.I)),
    (R_MONEY, re.compile(
        r"поврежд|царап|вмятин|разбил|сломал|авари|\bдтп|\bупал|штраф|депозит|залог|верн[иуё]те|"
        r"\bспор(?!т)|оспор|претенз|жалоб|оплат|оплач|переве[лд]|перевёл|перевод(?!чик)|\bчек\b|"
        r"refund|damage|scratch|\bdent|crash|accident|\bbroke|\bfined\b|penalt|deposit|dispute|"
        r"complain|\bpaid\b|payment|\bpay\b|transfer|receipt|invoice", re.I)),
)

_EN_WORDS = frozenset(
    "a an the i you we he she it they my your is are was be do does can could would will please "
    "hi hello hey thanks thank ok okay yes no not how what when where which much many price prices "
    "rent rental bike bikes scooter motorbike day days week weeks month for to from of in on at "
    "with and or but if this that there here have has need want like cost costs available".split())
_NOT_RU_CYR = re.compile(r"[іїєґўІЇЄҐЎқңөүұһәғҚҢӨҮҰҺӘҒ]")


def lang_of(text):
    """Текст клиента → 'ru' | 'en' | 'other' | None (букв нет — судить нечем)."""
    letters = [c for c in str(text or "") if c.isalpha()]
    if not letters:
        return None
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    lat = sum(1 for c in letters if "a" <= c.lower() <= "z")
    if (len(letters) - cyr - lat) > 0.2 * len(letters):
        return "other"
    if cyr >= lat:
        return "other" if _NOT_RU_CYR.search(text) else "ru"
    words = re.findall(r"[a-z]+", str(text).lower())
    if len(words) >= 3 and not any(w in _EN_WORDS for w in words):
        return "other"
    return "en"


def handoff(text, price=None):
    """Текст клиента (+ исход цены) → [{reason, words, why}] без повторов, в порядке REASONS."""
    found = {}
    s = str(text or "")
    for reason, rx in _TEXT_RULES:
        m = rx.search(s)
        if m:
            found[reason] = "слово в сообщении клиента"
    if lang_of(s) == "other":
        found[R_LANGUAGE] = "язык сообщения"
    if isinstance(price, dict) and price.get("outcome") == PRICE_HUMAN and price.get("reason"):
        found.setdefault(price["reason"], price.get("why") or "")
    return [{"reason": r, "words": w, "why": found[r]} for r, w in REASONS if r in found]


# ------------------------------- узлы мозга -------------------------------

def read_node(name, read_doc, now=None):
    """Узел → {name, read, text, len, taken_at, why}. Не прочитан → read=False и text=None:
    «неизвестно», а не пустая строка, которую модель приняла бы за «правил нет»."""
    t = time.time() if now is None else now
    out = {"name": name, "read": False, "text": None, "len": 0, "taken_at": None, "why": ""}
    try:
        reply = read_doc(name)
    except Exception as e:                     # noqa: BLE001
        out["why"] = "мост не отвечает (%s)" % type(e).__name__
        return out
    if not isinstance(reply, dict):
        out["why"] = "ответ моста не разобран"
        return out
    if not reply.get("ok"):
        out["why"] = "мост ответил отказом (%s)" % (reply.get("error") or "без причины")
        return out
    text = reply.get("text") or reply.get("content")
    if not isinstance(text, str) or not text.strip():
        out["why"] = "узел пуст — прочитанным не считаю"
        return out
    out.update(read=True, text=text, len=len(text), taken_at=t)
    return out


def node_age(node, now=None):
    """Возраст снимка в секундах | None (снимка нет)."""
    if not node or not node.get("read") or node.get("taken_at") is None:
        return None
    return max(0.0, (time.time() if now is None else now) - node["taken_at"])


class Knowledge:
    """Снимки узлов с возрастом. Перечитывает не чаще `max_age` секунд. Неудачное чтение НЕ
    затирает прежний снимок и НЕ освежает его: возраст честно растёт, причина пишется рядом."""

    def __init__(self, read_doc, names=NODES, max_age=600):
        self.read_doc, self.names, self.max_age = read_doc, tuple(names), max_age
        self.snap = {n: {"name": n, "read": False, "text": None, "len": 0, "taken_at": None,
                         "why": "ещё не читался"} for n in self.names}

    def refresh(self, now=None):
        t = time.time() if now is None else now
        for n in self.names:
            age = node_age(self.snap[n], t)
            if age is not None and age < self.max_age:
                continue
            got = read_node(n, self.read_doc, t)
            if got["read"]:
                self.snap[n] = got
            else:
                self.snap[n] = dict(self.snap[n], why=got["why"])
        return self.snap


def node_block(node, now=None):
    """Узел → текст для промпта. Не прочитан — НЕИЗВЕСТНО словами, а не пусто."""
    age = node_age(node, now)
    if age is None:
        return ("УЗЕЛ %s: НЕИЗВЕСТНО — не прочитан (%s). Не отвечай по памяти о том, что в нём; "
                "где нужен он — «уточню у коллег»." % (node.get("name"), node.get("why") or "причина не названа"))
    return "УЗЕЛ %s (снят %d мин назад, %d симв.):\n%s" % (
        node["name"], int(age // 60), node["len"], node["text"])


# ------------------------------- маска до модели -------------------------------

_STRONG = re.compile(
    r"(?i)(?<![\w])(парол\w*|password\w*|passwd|passcode|pwd|пин-?код\w*|\bпин\b|\bpin\b|pin-?code|"
    r"otp|cvv|cvc|secret|секрет\w*|token|токен\w*|api[\s_-]?key)(?![\w])")
_WEAK = re.compile(r"(?i)(?<![\w])(код\w*|code|ключ\w*|key)(?![\w])")
_FILLER = frozenset(
    "от для к на у мой моя мои мне не это is for from of to my the your wifi wi-fi вайфай вай-фай "
    "аккаунта аккаунт account и and : = - — –".split())
_FORMATS = (
    ("ключ", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("ключ", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{16,}")),
    ("ключ", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("ключ", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("ключ", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("ключ", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("ключ", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{30,}")),
    ("ключ", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
)
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_URL_SECRET = re.compile(r"(?i)([?&](?:token|key|api_key|apikey|secret|password|pass|sig|signature|auth)=)([^&\s#]+)")
_CARD = re.compile(r"(?<![\d+])(\d{4})[ \-]?(\d{4})[ \-]?(\d{4})[ \-]?(\d{4})(?!\d)")
_TOKEN = re.compile(r"\S+")
_EDGE = ".,;:!?()[]{}«»\"'"


def _luhn(digits):
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        s += d
        alt = not alt
    return s % 10 == 0


def _label(kind):
    return "[скрыто: %s]" % kind


def _weak_value(tok):
    """Значение после «код/ключ»: буквы-цифры от 4 знаков, есть цифра, не дата и не телефон.
    Предикат, а не читатель: одно выражение без «пустого из ветки промаха» (храповик blind_readers)."""
    return (re.fullmatch(r"[A-Za-z0-9\-]{4,}", tok) is not None and re.search(r"\d", tok) is not None
            and re.fullmatch(r"\d{9,}", tok) is None)


def _generic(tok):
    """Паролеподобное слово: от 12 знаков подряд, есть и буква, и цифра; не ссылка и не почта."""
    return (len(tok) >= 12 and "://" not in tok and not tok.lower().startswith("www.")
            and re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", tok) is None
            and re.fullmatch(r"[A-Za-z0-9_\-+/=!#$%^&*@.]+", tok) is not None
            and re.search(r"[A-Za-z]", tok) is not None and re.search(r"\d", tok) is not None)


def mask(text):
    """Текст → (текст с метками, число замен). Пароли, ключи, коды — меткой «[скрыто: …]»;
    телефоны, цены и даты не трогаются (у них нет букв и нет слова-ключа перед ними)."""
    s = str(text or "")
    n = 0
    spans = []                                  # (start, end, kind) — замены, без пересечений

    def take(a, b, kind):
        nonlocal n
        for x, y, _ in spans:
            if a < y and x < b:
                return
        spans.append((a, b, kind))
        n += 1

    for kind, rx in _FORMATS:
        for m in rx.finditer(s):
            take(m.start(), m.end(), kind)
    for m in _URL.finditer(s):
        for q in _URL_SECRET.finditer(m.group(0)):
            take(m.start() + q.start(2), m.start() + q.end(2), "ключ")
    for m in _CARD.finditer(s):
        if _luhn("".join(m.groups())):
            take(m.start(), m.end(), "карта")
    toks = []
    for m in _TOKEN.finditer(s):
        a, b = m.start(), m.end()
        while a < b and s[a] in _EDGE:
            a += 1
        while b > a and s[b - 1] in _EDGE:
            b -= 1
        if a < b:
            toks.append((a, b, s[a:b]))
    for i, (a, b, tok) in enumerate(toks):
        strong, weak = _STRONG.fullmatch(tok), _WEAK.fullmatch(tok)
        if strong or weak:
            for a2, b2, t2 in toks[i + 1:i + 5]:
                if t2.lower() in _FILLER:
                    continue
                if strong and len(t2) >= 3:
                    take(a2, b2, "пароль" if re.match(r"(?i)парол|pass|pwd", tok) else "код")
                elif weak and _weak_value(t2):
                    take(a2, b2, "код")
                break
    for a, b, tok in toks:
        if _generic(tok):                       # ссылку целиком отсекает сам `_generic` («://», «www.»)
            take(a, b, "ключ")
    for a, b, kind in sorted(spans, reverse=True):
        s = s[:a] + _label(kind) + s[b:]
    return s, n


# ------------------------------- сборка для промпта -------------------------------

def prompt_parts(price, reasons, nodes, now=None):
    """Блоки знаний для промпта → {имя: текст}; вместе с размером каждого (для замера объёма)."""
    parts = {}
    if price is not None:
        parts["price"] = "ЦЕНА: " + (price.get("line") or "")
    if reasons:
        parts["handoff"] = "НУЖЕН ЧЕЛОВЕК: " + "; ".join(r["words"] for r in reasons) + \
            ". Черновик пишется, но отправляет его только человек после правки."
    for node in nodes or ():
        parts["node:" + str(node.get("name"))] = node_block(node, now)
    return parts
