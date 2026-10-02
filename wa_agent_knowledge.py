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


# R_MONEY — один ключ «нужен человек», и поднимает его то же выражение выше (не меняется). На карточку и в
# промпт идёт СРАБОТАВШИЙ ярлык (WACARDCOMPACT0310): вопрос о депозите — «депозит», а не весь перечень денег.
# Альтернативы пяти групп слов вместе РАВНЫ альтернативам выражения R_MONEY (тест сверяет множества).
# WACARDMONEY0310: ярлык не утверждает факта, которого в сообщении нет.
# - «верните»/refund — свой ярлык «возврат денег»: что возвращать (депозит, предоплату, аренду), решает человек.
#   К депозиту — только когда депозит назван (депозит, залог, deposit) и других денег рядом нет.
# - Оплата — по смыслу сообщения: клиент заявил совершённую оплату (оплатил, перевёл, чек, скрин) — MONEY_PAYMENT;
#   признака факта нет (вопрос, упоминание) — «вопрос об оплате»; признак есть, но неясен (отрицание, «ли»,
#   чек в вопросе) — нейтральное «оплата». Причина МОДЕЛИ факта не заявляет никогда: её слова — пересказ, а не
#   сообщение клиента, поэтому её «оплатил» даёт нейтральное «оплата».
MONEY_DAMAGE, MONEY_DEPOSIT, MONEY_DISPUTE, MONEY_PAYMENT = "damage_fines", "deposit", "dispute", "payment"
MONEY_REFUND, MONEY_PAYMENT_ASK, MONEY_PAYMENT_UNCLEAR = "refund", "payment_ask", "payment_unclear"
MONEY_LABELS = (                                # группы слов; группа оплаты уточняется `payment_mode`
    (MONEY_DAMAGE, "повреждения и штрафы", re.compile(
        r"поврежд|царап|вмятин|разбил|сломал|авари|\bдтп|\bупал|штраф|"
        r"damage|scratch|\bdent|crash|accident|\bbroke|\bfined\b|penalt", re.I)),
    (MONEY_DEPOSIT, "депозит", re.compile(r"депозит|залог|deposit", re.I)),
    (MONEY_REFUND, "возврат денег", re.compile(r"верн[иуё]те|refund", re.I)),
    (MONEY_DISPUTE, "спор", re.compile(r"\bспор(?!т)|оспор|претенз|жалоб|dispute|complain", re.I)),
    (MONEY_PAYMENT, "оплата со слов клиента — поступление не проверено", re.compile(
        r"оплат|оплач|переве[лд]|перевёл|перевод(?!чик)|\bчек\b|\bpaid\b|payment|\bpay\b|transfer|receipt|"
        r"invoice", re.I)),
)
MONEY_WORDS = dict([(key, words) for key, words, _rx in MONEY_LABELS]
                   + [(MONEY_PAYMENT_ASK, "вопрос об оплате"), (MONEY_PAYMENT_UNCLEAR, "оплата")])

_PAY_DONE = re.compile(
    r"оплатил[аи]?\b|оплачен[аоы]?\b|заплатил[аи]?\b|перев[её]л[аи]?\b|скинул[аи]?\b|закинул[аи]?\b|"
    r"внес(?:ла|ли)?\b|внёс\b|отправил[аи]?\s+(?:вам\s+)?(?:деньги|оплату|перевод|сумму|предоплату)|"
    r"оплата\s+прошла|прошла\s+оплата|деньги\s+(?:ушли|отправлен)|"
    r"\b(?:i|we|i've|we've|i\s+have|we\s+have|already|just)\s+(?:already\s+|just\s+)?"
    r"(?:paid|sent|transferred|made\s+(?:the\s+)?payment)\b|"
    r"payment\s+(?:is\s+|was\s+|has\s+been\s+)?(?:done|sent|made|completed)\b", re.I)
_PAY_PROOF = re.compile(r"\bчек(?:а|и|ом|у)?\b|\bскрин\w*|квитанц\w*|\breceipt\b|\bscreenshot\b|\bproof\b", re.I)
_PAY_QUESTION = re.compile(r"\?|\bли\b|\bможно\b|\bнужн\w*|\bнадо\b|\bкак\b|\bкуда\b|\bcan\b|\bhow\b|\bdo\s+you\b",
                           re.I)
_NEG_BEFORE = re.compile(r"(?:\bне|\bnot|n't|\bnever)\s+(?:\S+\s+)?$", re.I)
_LI_AFTER = re.compile(r"\s*ли\b", re.I)
# WADRAFTFIX0310: документ под отрицанием фактом не считается — «нет чека», «без чека», no receipt; «чека нет».
# «не» — только вплотную («не чек»): в «не оплатил, чек…» оно относится к оплате, а не к документу
_PROOF_NEG_BEFORE = re.compile(r"(?:\bнет|\bбез|\bno|\bnot|n't|\bnever|\bwithout)\s+(?:\S+\s+)?$|\bне\s+$", re.I)
_PROOF_NEG_AFTER = re.compile(r"\s*(?:(?:пока|ещё|еще|тоже|у\s+меня)\s+)?(?:нет|не)\b", re.I)


def _claimed(s, m):
    """Признак оплаты заявлен как факт: перед ним нет отрицания, после него нет «ли»."""
    return _NEG_BEFORE.search(s[max(0, m.start() - 24):m.start()]) is None and _LI_AFTER.match(s, m.end()) is None


def _proof_claimed(s, m):
    """Документ оплаты (чек, скрин) назван как есть: перед ним нет отрицания («нет», «без», no), после него нет
    «нет» (WADRAFTFIX0310)."""
    return (_PROOF_NEG_BEFORE.search(s[max(0, m.start() - 24):m.start()]) is None
            and _PROOF_NEG_AFTER.match(s, m.end()) is None)


def payment_mode(text, trusted=True):
    """Текст с денежным словом оплаты → MONEY_PAYMENT (заявлена совершённой) | MONEY_PAYMENT_ASK (признака факта
    нет: вопрос или упоминание) | MONEY_PAYMENT_UNCLEAR (признак есть, но неясен). trusted=False — пересказ модели:
    факт из него не берётся, совершённая оплата становится неясной."""
    s = str(text or "")
    done = list(_PAY_DONE.finditer(s))
    proofs = list(_PAY_PROOF.finditer(s))
    fact = (any(_claimed(s, m) for m in done)
            or (any(_proof_claimed(s, m) for m in proofs) and _PAY_QUESTION.search(s) is None))
    if fact:
        return MONEY_PAYMENT if trusted else MONEY_PAYMENT_UNCLEAR
    return MONEY_PAYMENT_UNCLEAR if (done or proofs) else MONEY_PAYMENT_ASK


# WADRAFTFIX0310: другие деньги рядом с депозитом — «верните» уже не только о депозите
_OTHER_MONEY = re.compile(r"аренд|предоплат|аванс|\bден(?:ьг\w*|ег)\s+за\b|\brent\b|\bpre-?pa(?:y|id)\w*|"
                          r"\bmoney\s+for\b", re.I)


def money_labels(text, trusted=True):
    """Текст → [(ярлык, слова)] сработавших денежных ярлыков, в порядке MONEY_LABELS. Не пусто ровно тогда, когда
    сработало выражение R_MONEY. Депозит назван и других денег нет (оплаты, аренды, предоплаты, «денег за», rent —
    WADRAFTFIX0310) — «верните» относится к депозиту; возврат с оплатой без заявленного факта («верните
    предоплату») — это возврат, а не вопрос об оплате."""
    s = str(text or "")
    hit = {key for key, _words, rx in MONEY_LABELS if rx.search(s)}
    if MONEY_DEPOSIT in hit and MONEY_PAYMENT not in hit and not _OTHER_MONEY.search(s):
        hit.discard(MONEY_REFUND)
    out = []
    for key, _words, _rx in MONEY_LABELS:
        if key not in hit:
            continue
        if key == MONEY_PAYMENT:
            key = payment_mode(s, trusted)
            if MONEY_REFUND in hit and key != MONEY_PAYMENT:
                continue
        out.append((key, MONEY_WORDS[key]))
    return out


def handoff(text, price=None):
    """Текст клиента (+ исход цены) → [{reason, words, why}] в порядке REASONS, ключи без повторов, кроме
    R_MONEY: у него строка на каждый сработавший ярлык (`label`, WACARDCOMPACT0310)."""
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
    out = []
    for r, w in REASONS:
        if r not in found:
            continue
        labels = money_labels(s) if r == R_MONEY else []
        if labels:
            out += [{"reason": r, "label": key, "words": words, "why": found[r]} for key, words in labels]
        else:
            out.append({"reason": r, "words": w, "why": found[r]})
    return out


# ------------------------------- категории причин (карточка, дедуп) -------------------------------

# WACARDCOMPACT0310: слова причины → категории → действия сотрудника на карточке. Причины кода узнаются
# по своим словам, причины модели — теми же выражениями, что поднимают «нужен человек». Не узнана —
# категорий нет: карточка показывает слова как есть, дедуп — по тексту. Цена человеком — одна категория.
CAT_PRICE = "price"
# WAMONEYCHECK0310: причина по ТЕКСТУ ЧЕРНОВИКА модели, а не по сообщению клиента — см. `money_claims` ниже
R_MONEY_CLAIM = "money_claim"
MONEY_CLAIM_WORDS = "денежное утверждение без опоры"
# WAKNOWFRESH0310: причина по СНИМКУ ЗНАНИЙ — узел старше предела, его текста в промпте нет (см. `node_stale`)
R_STALE = "stale_knowledge"
STALE_WORDS = "знания устарели"
_WORD_CATS = dict(
    [(REASON_WORDS[R_AVAILABILITY], R_AVAILABILITY), (REASON_WORDS[R_SEASON_CROSS], CAT_PRICE),
     (REASON_WORDS[R_NO_PRICE_MODEL], CAT_PRICE), (REASON_WORDS[R_LONG_TERM], CAT_PRICE),
     (REASON_WORDS[R_DISCOUNT], R_DISCOUNT), (REASON_WORDS[R_DOOR_NO_PRICE], CAT_PRICE),
     (REASON_WORDS[R_MONEY], R_MONEY), (REASON_WORDS[R_LANGUAGE], R_LANGUAGE),
     (MONEY_CLAIM_WORDS, R_MONEY_CLAIM), (STALE_WORDS, R_STALE)]
    + [(words, key) for key, words in MONEY_WORDS.items()])
_RULES = dict(_TEXT_RULES)
_KEYWORD_CATS = ((R_AVAILABILITY, _RULES[R_AVAILABILITY]), (R_DISCOUNT, _RULES[R_DISCOUNT]))
# три смысла оплаты — одна семья для дедупа: оплату по сообщению клиента уже назвал код — пересказ модели лишний
_FAMILY = {MONEY_PAYMENT_ASK: MONEY_PAYMENT, MONEY_PAYMENT_UNCLEAR: MONEY_PAYMENT}


def word_categories(word):
    """Слова причины → [категории] (слова кода — ровно одна; причина модели — все сработавшие) | [].
    Причина модели — пересказ: деньги в ней узнаются без доверия к факту оплаты (WACARDMONEY0310)."""
    w = str(word or "").strip()
    if w in _WORD_CATS:
        return [_WORD_CATS[w]]
    return [cat for cat, rx in _KEYWORD_CATS if rx.search(w)] + [key for key, _ in money_labels(w, trusted=False)]


def _families(cats):
    return {_FAMILY.get(c, c) for c in cats}


def merge_reasons(words, extra):
    """Причины кода + причины модели → список без повторов ПО КАТЕГОРИИ (WACARDCOMPACT0310): причина модели
    отпадает, только если все её категории уже названы (смыслы оплаты — одна семья, WACARDMONEY0310); без
    категории — по тексту (регистр и знаки не различаются). Непустое пустым не становится: при пустом списке
    первая причина модели остаётся всегда."""
    out = [str(w) for w in words or ()]
    cats, texts = set(), set()
    for w in out:
        cats.update(word_categories(w))
        texts.add(_norm(w))
    for h in extra or ():
        got = word_categories(h)
        if (got and _families(got) <= _families(cats)) or _norm(h) in texts:
            continue
        out.append(h)
        cats.update(got)
        texts.add(_norm(h))
    return out


def reason_first(words, word):
    """Причина `word` — первой строкой всегда (WADRAFTFIX0310): уже стоящая (тот же текст без учёта регистра и
    знаков) переносится вперёд, а не остаётся на своём месте; повторов нет."""
    return [word] + [w for w in words or () if _norm(w) != _norm(word)]


# ------------------------------- деньги в черновике модели (WAMONEYCHECK0310) -------------------------------

# Черновик проверяется ПОСЛЕ модели: правило 4 промпта просит цену только из блока «ЦЕНА», но исполнение его не
# проверял никто. Утверждение без опоры — (а) процент в одном предложении со словом предоплаты, депозита или скидки:
# опоры у процента нет ни в одном блоке вызова, его решает человек; (б) сумма в батах, которой нет среди сумм блока
# «ЦЕНА» этого вызова (ставка, итог, депозит двери). Нашлось — причина MONEY_CLAIM_WORDS; текст ответа не правится.
# Число без валюты («PCX 160», «7 суток») суммой не считается.
_CLAIM_PCT = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d+)?\s*(?:%|процент\w*|percent\b|per\s+cent\b)", re.I)
_CLAIM_PCT_WORDS = re.compile(
    r"предоплат|предоплач|аванс|депозит|залог|скидк|скидоч|"
    r"pre-?pay|prepaid|advance|down\s*payment|upfront|up-front|deposit|discount|(?<![-\w])off\b", re.I)
_SENTENCE = re.compile(r"\n+|[.!?;…]+(?=\s|$)")
_SP = " " + chr(0xA0) + chr(0x202F)            # пробел, неразрывный и узкий неразрывный — разделители тысяч
_THB_GROUPED = r"\d{1,3}(?:[" + _SP + r",.]\d{3})+"
_THB_NUM = _THB_GROUPED + r"(?!\d)|\d+(?:[.,]\d+)?"
_CLAIM_THB = re.compile(
    # «฿ 2 800», «THB 2,800», «฿3k»
    r"(?:฿|\bthb\b|\bbaht\b)\s*(?P<pn>" + _THB_NUM + r")(?P<pm>[kк](?![a-zа-яё]))?"
    # «2 800 ฿», «2800 бат», «2.8k baht», «1 500–2 800 ฿», «от 1 500 до 2 800 бат»
    r"|(?<![\d.,])(?:(?P<rn>" + _THB_NUM + r")(?:[-–]|\s+(?:до|to)\s+))?(?P<sn>" + _THB_NUM + r")"
    r"(?:\s*(?P<sm>k|к|тыс(?:\.|яч\w*)?)(?![a-zа-яё]))?\s*(?:฿|бат(?:а|ов|ы)?\b|thb\b|baht\w*)", re.I)


def _thb_value(num, mult):
    """Число суммы и множитель → int | None. Разделители тысяч (пробел, запятая, точка по три цифры) снимаются;
    дробь — только с множителем («2,8k» = 2800)."""
    num = str(num or "").strip()
    if not num:
        return None
    if mult:
        try:
            return int(round(float(re.sub("[" + _SP + "]", "", num).replace(",", ".")) * 1000))
        except ValueError:
            return None
    if re.fullmatch(_THB_GROUPED, num):
        return int(re.sub(r"\D", "", num))
    if re.fullmatch(r"\d+", num):
        return int(num)
    return None                                    # «2.5 бат» без множителя — не сумма аренды, судить нечем


def thb_amounts(text):
    """Текст → [сумма в батах, …] по порядку появления: «2 800 ฿», «2800 бат», «THB 2,800», «2.8k baht»;
    у диапазона — обе границы. Число без валюты суммой не считается."""
    out = []
    for m in _CLAIM_THB.finditer(str(text or "")):
        if m.group("pn") is not None:
            pairs = [(m.group("pn"), m.group("pm"))]
        else:
            pairs = [(m.group("rn"), m.group("sm")), (m.group("sn"), m.group("sm"))]
        for num, mult in pairs:
            v = _thb_value(num, mult)
            if v is not None:
                out.append(v)
    return out


def money_claims(text, price=None):
    """Текст черновика модели (+ исход цены этого вызова) → [(вид, что)] денежных утверждений без опоры:
    ('процент', «30%») — процент в одном предложении со словом предоплаты, депозита или скидки;
    ('сумма', 3500) — сумма в батах, которой нет среди сумм блока «ЦЕНА» (`price["line"]`). Пусто — опора есть
    или денег в тексте нет."""
    s = str(text or "")
    out = []
    for sent in _SENTENCE.split(s):
        if _CLAIM_PCT_WORDS.search(sent):
            out += [("процент", m.group(0).strip()) for m in _CLAIM_PCT.finditer(sent)]
    line = price.get("line") if isinstance(price, dict) else None
    known = set(thb_amounts(line))
    out += [("сумма", v) for v in thb_amounts(s) if v not in known]
    return out


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


def node_stale(node, now=None):
    """Снимок старше своего предела `max_stale` (WAKNOWFRESH0310): его текст модели не подаётся. Предела в узле
    нет (узел не из `Knowledge`) — не устарел, как раньше."""
    age, limit = node_age(node, now), (node or {}).get("max_stale")
    return age is not None and limit is not None and age > limit


def node_failed_unread(node, now=None):
    """Снимка нет, а чтение пробовали в этом вызове и оно не удалось (WADRAFTFIX0310): знаний узла в промпте нет
    по сбою — та же причина, что у устаревшего. Чтение не настроено (`Knowledge` без read_doc) — не сбой, как
    раньше: причины нет."""
    return (node_age(node, now) is None and (node or {}).get("call") == CALL_FAILED
            and bool((node or {}).get("configured")))


# что было с узлом в ЭТОМ вызове `refresh` — для строки журнала (WAKNOWFRESH0310)
CALL_READ, CALL_KEPT, CALL_FAILED = "прочитан", "не перечитывался", "не прочитан"


class Knowledge:
    """Снимки узлов с возрастом. Перечитывает не чаще `max_age` секунд. Неудачное чтение НЕ
    затирает прежний снимок и НЕ освежает его: возраст честно растёт, причина пишется рядом.
    Предел — `max_stale` (по умолчанию 3 × `max_age`, WAKNOWFRESH0310): снимок старше — НЕИЗВЕСТНО вместо
    текста и причина «знания устарели»; до предела модель видит прежний текст с его возрастом."""

    def __init__(self, read_doc, names=NODES, max_age=600, max_stale=None):
        # read_doc None — чтение не настроено (WADRAFTFIX0310): отказ «моста нет», как раньше, но сбоем не считается
        self.configured = read_doc is not None
        self.read_doc = read_doc if read_doc is not None else (lambda n: {"ok": False, "error": "моста нет"})
        self.names, self.max_age = tuple(names), max_age
        self.max_stale = 3 * max_age if max_stale is None else max_stale
        self.snap = {n: {"name": n, "read": False, "text": None, "len": 0, "taken_at": None,
                         "why": "ещё не читался", "max_stale": self.max_stale, "call": None,
                         "configured": self.configured} for n in self.names}

    def refresh(self, now=None):
        t = time.time() if now is None else now
        for n in self.names:
            age = node_age(self.snap[n], t)
            if age is not None and age < self.max_age:
                self.snap[n] = dict(self.snap[n], call=CALL_KEPT)
                continue
            got = read_node(n, self.read_doc, t)
            if got["read"]:
                self.snap[n] = dict(got, max_stale=self.max_stale, call=CALL_READ, configured=self.configured)
            else:
                self.snap[n] = dict(self.snap[n], why=got["why"], call=CALL_FAILED)
        return self.snap


def stale_reasons(nodes, now=None):
    """Узлы этого вызова → [причина «знания устарели»] | []: одна на все узлы, чьих знаний в промпте нет по сбою —
    снимок старше предела или снимка нет, а чтение не удалось (WADRAFTFIX0310)."""
    old = [n for n in nodes or () if node_stale(n, now)]
    none = [n for n in nodes or () if node_failed_unread(n, now)]
    if not old and not none:
        return []
    why = []
    if old:
        why.append("снимок старше %d мин: %s" % (old[0]["max_stale"] // 60, ", ".join(n["name"] for n in old)))
    if none:
        why.append("снимка нет, чтение не удалось: %s" % ", ".join(n["name"] for n in none))
    return [{"reason": R_STALE, "words": STALE_WORDS, "why": "; ".join(why)}]


def node_block(node, now=None):
    """Узел → текст для промпта. Не прочитан или снимок старше предела — НЕИЗВЕСТНО словами, без текста."""
    age = node_age(node, now)
    if age is None:
        return ("УЗЕЛ %s: НЕИЗВЕСТНО — не прочитан (%s). Не отвечай по памяти о том, что в нём; "
                "где нужен он — «уточню у коллег»." % (node.get("name"), node.get("why") or "причина не названа"))
    if node_stale(node, now):
        return ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше %d мин, %s. Не отвечай по памяти о том, что в нём; "
                "где нужен он — «уточню у коллег»." % (node["name"], node["max_stale"] // 60,
                                                       node.get("why") or "не освежён"))
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
