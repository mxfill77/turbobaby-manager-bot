# -*- coding: utf-8 -*-
"""Наличие и цена по запросу модели — инструмент «offer» сверки Т4а (OFFER1910, отрезок inquiry-to-booking; флаг службы
WA_AGENT_OFFER, по умолчанию выкл).

ЗАЧЕМ. Блоки «ЦЕНА» и «НАЛИЧИЕ» готовит код ДО модели по регуляркам хвоста: цену — только при слове цены, наличие — только
при слове наличия и двух датах в ПОСЛЕДНЕМ сообщении. Названное клиентом раньше теряется, ответ — «коллега уточнит»
(передача человеку за 14 сут: цена 42, наличие 35 из 81 ответа). При «занято» альтернатив нет ни одной дорогой. Модель сама
выбрать источник наличия и цены не может: у сверки Т4а (`wa_agent_tools.TOOLS`) такого инструмента нет.

ЧТО ДЕЛАЕТ. Инструмент `offer {"model", "date_from", "date_to"}` — только чтение, модель зовёт его сама по паре, которую
поняла из переписки. Код, а не модель: даты — строго ГГГГ-ММ-ДД, конец позже начала, начало не раньше сегодняшнего дня по
Пхукету; снимок броней (`wa_book_read.Snapshot`) служит; модель — ОДНА модель живого парка по ключу имён
(`wa_agent_model.model_hits`: сокращение к нескольким моделям — «неоднозначно», модель не из парка — «неизвестно»). Срок
короче минимума класса (`term_minimum`, WAMINPRICE0510) — наличие и цена на минимум (аренда не короче него). Ворота цены —
те же `K.quote` (пробный проход с дверью-заглушкой, без сети): срок от 30 суток, стык сезонов, модель без цены — «считает
человек», сезон не определён — «неизвестно»; дверь в этих случаях не зовётся. Прошли — ТЕ ЖЕ `wa_book_read.free_bikes`
(свободно — только по ответу двери цены `available is True`) и `K.quote` через общую дверь вызова: ответ двери на (юнит,
даты) читается один раз, поэтому на пару — ОДИН вызов quote_price, он даёт и наличие, и цену. Итог — ответ инструмента
формы `wa_agent_tools.result` (источник, at, read_at — время СНИМКА, ref, окно) с фактом «offer»: модель, даты, свободно или
занято, юниты, возраст снимка, подтверждённый юнит (только сотруднику: в запрос модели не идёт), числа цены. Занято — модель
может проверить другую модель или другие даты; offer — не больше OFFER_MAX вызовов на сверку (дальше отказ «предел», двери
нет); повтор той же пары — ответ из кеша сверки, двери нет.

СУД. Факты offer в `results` сверки НЕ кладутся (тождество факта `fact_key` их не знает): аренды, оплаты, итога «к оплате»
и денежных ролей они не дают. Опора денег, суток и дат черновика — исход цены вызова вместе с ценами принятых фактов offer
(`judged_price`: `K.price_set`; процент скидки двери снимается `without_known_discount` тем же путём). Принятый факт
(FACT, прочитан не раньше последнего входящего клиента) снимает причину «наличие и брони — агент их не видит» (и её пересказ
моделью дословно) — только если КАЖДАЯ модель, которую черновик назвал свободной, проверена offer как свободная
(`avail_mismatch`, приёмка OFFER1910): занятое, непроверенное, не из парка или «свободен» без модели при занятом — причина
остаётся, и к ней «наличие в тексте не совпадает с проверкой — решает человек». Просьба о брони — «бронь оформляет
человек» остаётся. Не факт — «наличие не проверено — решает человек»; ворота человека — их причины `K.handoff`. Брони не
пишутся, клиенту — только по «Отправить» человека.

КОПИЯ. Цикл сверки (`wa_agent_tools.run`) и черновик со сверкой (`ModelAdapter._draft_tools`) закреплены блобами в семи
наборах — их не трогаем. Поэтому `run` и `OfferMixin._draft_tools` здесь — копии родителей с помеченными правками
(«OFFER»), сверенные по sha256 исходника (`PARENT_SHA`): разошлись (или класс уже переопределил `_draft_tools`) —
`with_offer` отказывает, служба пишет «не засчитан», адаптер прежний. Модель offer не звала — черновик, журнал и опора
равны родительским (тест-близнец), кроме строки инструмента в блоке «ИНСТРУМЕНТЫ».

ГРАНИЦЫ. Импорты — `datetime`, `hashlib`, `inspect`, `json`, `re`, `time`, `wa_agent_knowledge`, `wa_agent_model`,
`wa_agent_tools`, `wa_book_read`; файлов, сети и базы модуль не касается — двери (снимок, quote_price) у адаптера. В
журнал — только числа, модель, даты и юнит (журнал сверки — сотруднику); номера и текста клиента нет.

ПОДКЛЮЧЕНИЕ. `with_offer(cls)` → класс «примесь + cls» (один на cls); служба (`wa_agent_svc.offer_of`) меняет класс уже
собранного адаптера. Флаг выключен — модуль не импортируется вовсе: system, user, блок инструментов и класс адаптера
байт-в-байт прежние."""
import datetime
import hashlib
import inspect
import json
import re
import time

import wa_agent_knowledge as K
import wa_agent_model as M
import wa_agent_tools as T
import wa_book_read as B

OFFER_TOOL = "offer"
OFFER_MAX = 3                                    # вызовов offer на одну сверку (альтернативы при «занято»)
SOURCE = "снимок броней (лист «клиенты») + дверь цены (quote_price)"
LOG_HEAD = "offer: "
LABEL_MAX = 40                                   # слова модели о модели в строке ответа и журнале, знаков

# строка инструмента в блоке «ИНСТРУМЕНТЫ» сверки — только у адаптера с примесью (флаг выкл — блок прежний)
OFFER_BLOCK = ('offer {"model": "<модель парка>", "date_from": "ГГГГ-ММ-ДД", "date_to": "ГГГГ-ММ-ДД"} — наличие и цена '
               'одной модели на даты одним вызовом (модель код сверит с парком, свободный байк — с дверью цены); занято — '
               'можно проверить другую модель или другие даты; не больше %d вызовов offer за сверку. Наличие и цену по '
               'offer называй только из его строк «НАЛИЧИЕ» и «ЦЕНА».' % OFFER_MAX)

# ── ответ модели (блок результатов) ─────────────────────────────────────────────────────────────────────────────
HEAD = "OFFER — НАЛИЧИЕ И ЦЕНА ПО ТВОЕМУ ЗАПРОСУ (код; «не факт» — не опора; вызовов offer осталось %d):"
BUSY_LINE = ("НАЛИЧИЕ (таблица броней, снимок %d мин назад; прочитаны все юниты модели): %s, %s — %s: заняты все %d. "
             "Можно сказать, что на эти даты этой модели нет. Другую модель или другие даты можно проверить вызовом "
             "offer; свободной называй только проверенную, её цену — только из её строки «ЦЕНА».")
NOT_LINE = "НАЛИЧИЕ: НЕИЗВЕСТНО — %s. Не говори ни «есть», ни «нет», ни «свободен»; %s"
FACT_NOTE = ("Наличие этих пар проверил код: причину «%s» в handoff не переноси; бронь по-прежнему оформляет человек."
             % K.REASON_WORDS[K.R_AVAILABILITY])
ADV_MODEL = "уточни у клиента модель."
ADV_DATES = "уточни у клиента даты (с какого по какое число)."
ADV_HUMAN = "скажи, что наличие и цену на этот срок проверит коллега."
ADV_LATER = "скажи, что коллега проверит наличие и вернётся."
ADV_LIMIT = "больше offer не зови — скажи, что коллега подберёт."

# ── отказы и «неизвестно» (двери нет) ───────────────────────────────────────────────────────────────────────────
W_LIMIT = "предел: не больше %d вызовов offer за сверку — этот не выполнен" % OFFER_MAX
W_DATES = "даты не в виде ГГГГ-ММ-ДД"
W_ORDER = "конец срока не позже начала"
W_PAST = "срок уже начался или прошёл (сегодня по Пхукету %s)"
W_NO_BOOK = "броней нет — наличие не читается"
W_NO_DOOR = "двери цены нет — «свободен» не сверить"
W_NO_SNAP = "таблица броней не прочитана (%s)"
W_NO_MODEL = "модель не названа"
W_FLEET = "модели «%s» нет в парке"
W_ALIAS = "модель не определена: «%s» подходит к моделям парка %s"
W_MANY = "названо несколько моделей (%s) — один вызов offer на одну модель"
W_GATE_HUMAN = "считает человек: %s"
W_GATE_UNKNOWN = "цена и наличие не проверены: %s"
W_CACHED = "повтор той же пары — ответ из кеша сверки, дверь не звана"

# ── журнал (числа и слова; юнит — сотруднику) ───────────────────────────────────────────────────────────────────
L_SUM = "вызовов %d: факт %d (свободно %d, занято %d), не факт %d (предел %d), дверь цены %d, кеш %d"
L_FAIL = "сбой %s — не факт"

# Копии родителей сверены по sha256 исходника (переводы строк сведены к \n): разошлись — `with_offer` отказывает.
PARENT_SHA = {
    "wa_agent_model.ModelAdapter._draft_tools": "03bc50a874743cdcd4a420f87c2bb92afc91006eb969555db12ce753a8859b10",
    "wa_agent_tools.run": "22bce16c666472488185b56a113c607daef73a88f89b3e82b8c6590f3d35740c",
}

# похоже на модель: латиница и трёхзначная кубатура — то же выражение, что у наличия по переписке (`wa_book_ctx`, не
# импортируется: его флаг свой)
_RX_MODEL_LIKE = re.compile(r"(?i)(?<![a-z0-9])[a-z][a-z-]*[a-z]\s*-?\s*\d{3}(?!\d)")
_CLASSES = {}                                    # with_offer: класс «примесь + cls», один на cls


class ParentDrift(RuntimeError):
    """Копия родителя не сверена (исходник изменился или `_draft_tools` уже переопределён) — примесь не надевается."""


# ── чистые функции ──────────────────────────────────────────────────────────────────────────────────────────────

def _sha(fn):
    return hashlib.sha256(inspect.getsource(fn).replace("\r\n", "\n").encode("utf-8")).hexdigest()


def drift():
    """Родители копий → [имя, …] разошедшихся с `PARENT_SHA` (исходника нет — тоже разошёлся). Пусто — сверены."""
    out = []
    for name, fn in (("wa_agent_model.ModelAdapter._draft_tools", M.ModelAdapter._draft_tools),
                     ("wa_agent_tools.run", T.run)):
        try:
            ok = _sha(fn) == PARENT_SHA[name]
        except (OSError, TypeError):                                 # исходник не прочитан — не сверено
            ok = False
        if not ok:
            out.append(name)
    return out


def day_arg(value):
    """Дата аргумента модели → date | None: строго ГГГГ-ММ-ДД (иная запись — день и месяц не угадываем)."""
    s = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def label_of(value):
    """Слова модели о модели → под маской, не длиннее LABEL_MAX (в ответ и журнал)."""
    return K.mask(re.sub(r"\s+", " ", str(value or "")).strip())[0][:LABEL_MAX]


def model_of(value, bikes):
    """Слова модели о модели + парк снимка → (модель парка | None, код отсева | None, почему). Модель — ровно одна
    модель парка по ключу живых имён (`M.model_hits`); сокращение к нескольким моделям — "alias"; несколько моделей —
    "many"; модели нет (в том числе модель с кубатурой не из парка рядом с моделью парка) — "fleet"."""
    s = str(value or "").strip()
    if not s:
        return None, "no_model", W_NO_MODEL
    hits = M.model_hits(s, bikes)
    amb = [h for h in hits if h[2] is None]
    if amb:
        return None, "alias", W_ALIAS % (amb[0][3], " / ".join(amb[0][4]))
    models = sorted({h[2] for h in hits})
    if len(models) > 1:
        return None, "many", W_MANY % " / ".join(models)
    foreign = [m for m in _RX_MODEL_LIKE.finditer(s) if not any(h[0] < m.end() and m.start() < h[1] for h in hits)]
    if not models or foreign:
        return None, "fleet", W_FLEET % label_of(foreign[0].group(0) if foreign else s)
    if not M.units_of(models[0], bikes):
        return None, "fleet", W_FLEET % label_of(s)
    return models[0], None, ""


def term_of(model, ds, de):
    """Срок запроса → {ds, de, days[, min, client]}: короче минимума класса — на минимум (как цена, WAMINPRICE0510)."""
    days = (de - ds).days
    term = {"ds": ds, "de": de, "days": days}
    mn = M.term_minimum([model]).get(model)
    if mn is not None and 0 < days < mn:
        term = dict(term, de=ds + datetime.timedelta(days=mn), days=mn, min=mn, client=days)
    return term


def accepted(offers, since=None):
    """Ответы offer → принятые: FACT, прочитанные не раньше последнего входящего клиента (`T.stale`), каждая пара один
    раз (повтор из кеша — та же пара)."""
    out, seen = [], set()
    for r in offers or ():
        if r.get("outcome") != T.FACT or T.stale(r, since):
            continue
        o = r.get("offer") or {}
        key = (o.get("model"), o.get("date_from"), o.get("date_to"))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def judged_price(price, facts):
    """Исход цены вызова + принятые факты offer → исход цены для суда денег, суток и дат: цены свободных пар offer —
    вариантами `K.price_set`. Цен offer нет — исход вызова как есть (тот же объект)."""
    extra = [r["offer"]["quote"] for r in facts or () if isinstance(r.get("offer", {}).get("quote"), dict)]
    if not extra:
        return price
    return K.price_set(K.quotes_of(price) + extra)


def judged_info(info, price, facts):
    """Сведения вызова для проверок суток и дат (`_days_check`, `_arrival_check`): исход цены — `judged_price`, сроки
    («СРОКИ») — плюс сроки принятых фактов offer. Фактов нет — сведения как есть (тот же объект)."""
    if not facts and price is info.get("price"):
        return info
    terms = list(info.get("terms") or ())
    for r in facts or ():
        o = r["offer"]
        terms.append({"ds": day_arg(o["date_from"]), "de": day_arg(o["date_to"]), "days": o["days"]})
        if o.get("client"):
            terms.append({"ds": None, "de": None, "days": o["client"]})
    return dict(info, price=price, terms=terms)


def offer_reasons(reasons, offers, facts, ask, mismatch=()):
    """Причины кода + ответы offer этой сверки → причины ({reason, words, why}); прежние — в прежнем порядке, новые — в
    конце, ключ причины один раз. Принятый факт и наличие текста с ним совпало (`mismatch` пуст) — «наличие и брони —
    агент их не видит» снята, просьба о брони — «бронь оформляет человек»; не совпало — прежняя остаётся (как без
    флага), и в конце — «наличие в тексте не совпадает с проверкой»; ворота человека и скидка без числа у цен offer —
    причины `K.handoff`; ответ не факт (кроме ворот человека) — «наличие не проверено — решает человек»."""
    out = [dict(r) for r in reasons or ()]
    if not offers:
        return out
    if facts and not mismatch:
        out = [r for r in out if r.get("reason") != K.R_AVAILABILITY]
        if B.book_intent(ask):
            out.append({"reason": B.R_BOOKING, "words": B.W_BOOKING, "why": "просьба о брони"})
    quotes = [r["offer"]["quote"] for r in offers if isinstance((r.get("offer") or {}).get("quote"), dict)]
    out += K.handoff("", K.price_set(quotes))
    unknown = [r for r in offers if r.get("outcome") != T.FACT and not (r.get("offer") or {}).get("gate")]
    if unknown:
        out.append({"reason": B.R_AVAIL_UNKNOWN, "words": B.W_AVAIL_UNKNOWN, "why": "offer: не факт %d" % len(unknown)})
    if mismatch:
        out.append({"reason": R_AVAIL_MISMATCH, "words": W_AVAIL_MISMATCH, "why": "offer: " + "; ".join(mismatch)})
    keep, seen = [], set()
    for r in out:
        if r.get("reason") not in seen or r.get("reason") == K.R_MONEY:
            seen.add(r.get("reason"))
            keep.append(r)
    return keep


def _norm(s):
    return re.sub(r"[^0-9a-zа-яё]+", "", str(s or "").lower())


def without_avail_words(words, facts, mismatch=()):
    """Принятый факт offer и наличие текста с ним совпало → слова «наличие и брони — агент их не видит» сняты и у
    пересказа модели (дословного); иначе (фактов нет или `mismatch` не пуст) как есть."""
    if not facts or mismatch:
        return words
    gone = _norm(K.REASON_WORDS[K.R_AVAILABILITY])
    return [w for w in words if _norm(w) != gone]


# ── «свободен» в тексте черновика против фактов offer (приёмка OFFER1910) ─────────────────────────────────────────
# Принятый факт снимает «агент их не видит» только тогда, когда КАЖДАЯ модель, которую черновик назвал свободной, имеет
# принятый факт «свободно» и ни одного «занято»: иначе снятие спрятало бы от сотрудника черновик, назвавший свободным
# занятое или непроверенное (модель отвечает сама — по сценарию это не держится). Разбор слов грубый и сомнение отдаёт
# человеку: часть предложения, где модель названа занятой («PCX 160 занят»), — не «свободно»; всё прочее в предложении
# со словом «свободно» — названо свободным. Обратного («свободное названо занятым») слой не судит.

# деление на предложения — то же, что у судьи денег (`K.money_claims`); имени нет — модуль не собирается (служба: «не
# засчитан», адаптер прежний), а не падает черновик
_sentences = K._sentences
# части предложения: запятая, скобки, тире между пробелами (не «10–15»), «но», «а», «однако», but, however
_RX_CLAUSE = re.compile(r"(?i)[,()]|\s[—–-]\s|\s(?:но|а|однако|зато|but|however|whereas)\s")
_RX_NEG = re.compile(r"(?i)(?:(?<![а-яёa-z])(?:не|нет|ни|not|no)|n['’]t)\s+$")      # отрицание прямо перед словом
# слово «свободно» — само по себе, и без модели рядом (слово «занято» с отрицанием — тоже: «не занят», not booked)
_RX_FREE = re.compile(
    r"(?i)(?<![а-яё])свобод\w*|(?<![а-яё])в\s+наличии|(?<![а-яё])доступ(?:ен|на|но|ны)(?![а-яё])|"
    r"(?<![a-z])(?:available|in\s+stock|vacant)(?![a-z])")
# слабое слово («есть», free): «свободно» — только с моделью, байком или вариантом рядом или в голой части («Да, есть»)
_RX_WEAK = re.compile(r"(?i)(?<![а-яё])(?:есть|име(?:ется|ются))(?![а-яё])|(?<![a-z])free(?![a-z])")
_RX_BUSY = re.compile(r"(?i)(?<![а-яё])(?:занят\w*|нет|нету|недоступ\w*|забронирован\w*)(?![а-яё])|"
                      r"(?<![a-z])(?:busy|booked|taken|unavailable|sold\s+out)(?![a-z])")
_RX_GEN = re.compile(r"(?i)свободн(?:ых|ого|ой)$")                 # «свободных … нет» — нет
_RX_NET = re.compile(r"(?i)(?<![а-яё])нет(?![а-яё])")
_RX_OBJECT = re.compile(r"(?i)вариант|байк|скутер|мотоцикл|мопед|модел|(?<![а-яё])друг(?:ой|ая|ие|ую|их|ое)(?![а-яё])|"
                        r"(?<![a-z])(?:bikes?|scooters?|motorbikes?|mopeds?|options?|models?|other)(?![a-z])")
_BARE = frozenset(
    "конечно даты дату числа число время срок сроки сейчас пока этих этот эту sure still these those dates date days "
    "period time there января февраля марта апреля июня июля августа сентября октября ноября декабря january february "
    "march april june july august september october november december".split())
_NOT_MODEL = frozenset(("thb", "baht", "usd", "eur", "rub", "km"))     # «THB 400» — сумма, а не модель
M_BUSY = "%s — по проверке занят"
M_BOTH = "%s — по проверке занят на одни из дат"
M_UNCHECKED = "%s — не проверен"
M_FOREIGN = "«%s» — не из парка"
M_ALIAS = "«%s» — модель не определена"
M_BARE = "«свободно» без модели — а по проверке есть занятое"
R_AVAIL_MISMATCH = "offer_avail_mismatch"
W_AVAIL_MISMATCH = "наличие в тексте не совпадает с проверкой — решает человек"
L_MISMATCH = ("наличие в тексте не совпадает с проверкой: %%s — «%s» не снята, причина «%s»"
              % (K.REASON_WORDS[K.R_AVAILABILITY], W_AVAIL_MISMATCH))


def _parts(s, a, b):
    """Предложение s[a:b] → [(начало, конец)] частей (`_RX_CLAUSE`)."""
    out, at = [], a
    for m in _RX_CLAUSE.finditer(s, a, b):
        out.append((at, m.start()))
        at = m.end()
    out.append((at, b))
    return out


def _bare(part):
    """Часть без слов длиннее трёх букв, кроме слабого слова, согласия, дат и сроков («Да, есть», «на эти даты есть»)."""
    return not [w for w in re.findall(r"[a-zа-яё]+", part.lower())
                if len(w) >= 4 and w not in _BARE and not _RX_WEAK.fullmatch(w)]


def _marks(part, named):
    """Часть предложения → (свободно, занято). Слово «свободно» без отрицания — свободно; с отрицанием («не свободен»,
    «нет в наличии», «свободных … нет») — занято; слово «занято» без отрицания — занято, с отрицанием («не занят», «не
    забронирован», not booked) — свободно; слабое слово — свободно, только если в части названа модель, байк или вариант
    или часть голая."""
    free = busy = False
    for m in _RX_FREE.finditer(part):
        if _RX_NEG.search(part[:m.start()]) or (_RX_GEN.search(m.group()) and _RX_NET.search(part, m.end())):
            busy = True
        else:
            free = True
    for m in _RX_BUSY.finditer(part):
        if _RX_NEG.search(part[:m.start()]):
            free = True
        else:
            busy = True
    if not free and any(not _RX_NEG.search(part[:m.start()]) for m in _RX_WEAK.finditer(part)):
        free = bool(named or _RX_OBJECT.search(part) or _bare(part))
    return free, busy


def _mentions(s, bikes):
    """Модели в тексте → [(начало, конец, модель | None | False, слово)]: модель парка (`M.model_hits`; None —
    сокращение к нескольким), False — похожее на модель не из парка (сумма «THB 400» — не модель)."""
    hits = [(h[0], h[1], h[2], h[3]) for h in M.model_hits(s, bikes)]
    foreign = [(m.start(), m.end(), False, m.group()) for m in _RX_MODEL_LIKE.finditer(s)
               if not any(h[0] < m.end() and m.start() < h[1] for h in hits)
               and re.sub(r"[^a-z]", "", m.group().lower()) not in _NOT_MODEL]
    return sorted(hits + foreign)


def avail_mismatch(text, facts, bikes):
    """Текст черновика + принятые факты offer + парк снимка → [почему наличие текста не совпало с проверкой] (пусто —
    совпало или фактов нет). Названа свободной (в предложении со словом «свободно», кроме части, где модель названа
    занятой без «свободно») — модель совпадает только при факте «свободно» и ни одном «занято»; не проверена, не из
    парка, сокращение к нескольким — не совпадает. «Свободно», а свободной не названа ни одна модель предложения, —
    совпадает, только если занятого среди фактов нет."""
    if not facts:
        return []
    got = {}
    for r in facts:
        o = r.get("offer") or {}
        got.setdefault(o.get("model"), set()).add(o.get("avail"))
    busy_any = any(B.BUSY in v for v in got.values())
    s = str(text or "")
    ments, out = _mentions(s, bikes), []
    for a, b in _sentences(s):
        parts = []
        for c0, c1 in _parts(s, a, b):
            named = [x for x in ments if c0 <= x[0] < c1]
            parts.append((named, _marks(s[c0:c1], bool(named))))
        if not any(free for _n, (free, _busy) in parts):
            continue
        claimed = [x for named, (free, busy) in parts if free or not busy for x in named]
        if not claimed and busy_any:
            out.append(M_BARE)
        out += [w for w in (_verdict(model, word, got) for _a, _b, model, word in claimed) if w]
    return list(dict.fromkeys(out))


def _verdict(model, word, got):
    """Модель, названная свободной, + исходы фактов по моделям → почему не совпало | None (совпало)."""
    if model is False:
        return M_FOREIGN % label_of(word)
    if model is None:
        return M_ALIAS % label_of(word)
    av = got.get(model, set())
    if B.BUSY in av:
        return (M_BOTH if B.FREE in av else M_BUSY) % model
    return None if B.FREE in av else M_UNCHECKED % model


def _mins(age):
    return int((age or 0) // 60)


# ── вызовы offer одной сверки ───────────────────────────────────────────────────────────────────────────────────

class Offers(object):
    """Вызовы offer ОДНОЙ сверки: предел, кеш пар, общая дверь цены (ответ на (юнит, даты) читается один раз), ответы по
    порядку. Двери — у адаптера: `book` (снимок), `door` (quote_price), `no_price_models`."""

    def __init__(self, adapter, today=None, limit=OFFER_MAX):
        self.adapter, self.today, self.limit = adapter, today, limit
        self.results, self.cache, self.memo = [], {}, {}
        self.calls = self.door_calls = self.cached = self.over = 0
        self.bikes = None                                            # парк последнего служащего снимка (`avail_mismatch`)

    def door(self, unit, ds, de):
        """Общая дверь цены вызова: (юнит, даты) → ответ двери, прочитанный один раз; исключение — то же, повторно."""
        key = (B.qnorm(unit), str(ds), str(de))
        if key not in self.memo:
            self.door_calls += 1
            try:
                self.memo[key] = (True, self.adapter.door(unit, ds, de))
            except Exception as e:                                   # noqa: BLE001 — исход судят free_bikes/quote
                self.memo[key] = (False, e)
        ok, got = self.memo[key]
        if not ok:
            raise got
        return got

    def call(self, args, clock=time.time):
        """Вход модели → ответ инструмента (форма `T.result` + поле `offer`); записан в `results`."""
        at = clock()
        self.calls += 1
        if self.calls > self.limit:                                  # предел — ни снимка, ни двери
            self.over += 1
            asked = label_of(args.get("model")) if isinstance(args, dict) else ""
            res = self._res(T.REFUSED, at, W_LIMIT, {"code": "limit", "asked": asked})
        else:
            try:
                res = self._read(args if isinstance(args, dict) else {}, at, clock)
            except Exception as e:                                   # noqa: BLE001 — сбой инструмента: не факт
                res = self._res(T.UNKNOWN, at, L_FAIL % type(e).__name__, {"code": "fail"})
        self.results.append(res)
        return res

    @staticmethod
    def _res(outcome, at, reason="", offer=None, facts=None, read_at=None, ref="", window=""):
        o = {"model": None, "asked": "", "date_from": None, "date_to": None, "days": None, "min": None, "client": None,
             "avail": None, "units": 0, "free": 0, "busy": 0, "unchecked": 0, "unit": None, "age": None,
             "door_calls": 0, "quote": None, "gate": None, "code": None, "line": "", "cached": False}
        o.update(offer or {})
        res = T.result(OFFER_TOOL, outcome, SOURCE, ref=ref, at=at, window=window, reason=reason, facts=facts,
                       read_at=at if read_at is None else read_at)
        res["offer"] = o
        return res

    def _read(self, args, at, clock):
        a = self.adapter
        asked = label_of(args.get("model"))
        ds, de = day_arg(args.get("date_from")), day_arg(args.get("date_to"))
        base = {"asked": asked, "date_from": ds.isoformat() if ds else None, "date_to": de.isoformat() if de else None}
        if ds is None or de is None:
            return self._res(T.REFUSED, at, W_DATES, dict(base, code="dates"))
        if de <= ds:
            return self._res(T.REFUSED, at, W_ORDER, dict(base, code="order"))
        today = self.today or B.local_now(at).date()
        if ds < today:
            return self._res(T.REFUSED, at, W_PAST % today.isoformat(), dict(base, code="past"))
        if getattr(a, "book", None) is None:
            return self._res(T.UNKNOWN, at, W_NO_BOOK, dict(base, code="no_book"))
        if getattr(a, "door", None) is None:
            return self._res(T.UNKNOWN, at, W_NO_DOOR, dict(base, code="no_door"))
        now = clock()
        rows, bikes, age, why = a.book.get(now)
        taken = now - age if isinstance(age, (int, float)) and not isinstance(age, bool) else None
        base["age"] = age
        if rows is None or not bikes:
            return self._res(T.UNKNOWN, at, W_NO_SNAP % (why or "парка в снимке нет"), dict(base, code="snapshot"),
                             read_at=taken)
        self.bikes = bikes
        model, code, why_m = model_of(args.get("model"), bikes)
        if model is None:
            return self._res(T.AMBIGUOUS if code in ("alias", "many") else T.UNKNOWN, at, why_m,
                             dict(base, code=code), read_at=taken)
        units = M.units_of(model, bikes)
        term = term_of(model, ds, de)
        base.update(model=model, date_to=term["de"].isoformat(), days=term["days"], min=term.get("min"),
                    client=term.get("client"), units=len(units))
        key = (model, term["ds"], term["de"])
        if key in self.cache:                                        # повтор пары — двери нет
            self.cached += 1
            got = self.cache[key]
            return dict(got, offer=dict(got["offer"], cached=True, door_calls=0),
                        reason=(got["reason"] + "; " if got["reason"] else "") + W_CACHED)
        res = self._pair(model, units, term, rows, age, why, now, at, taken, base)
        self.cache[key] = res
        return res

    def _pair(self, model, units, term, rows, age, why, now, at, taken, base):
        """Пара прошла вход: ворота цены (`K.quote` с заглушкой) → `free_bikes` → `K.quote` той же дверью."""
        a = self.adapter
        before = self.door_calls
        ref, window = model, "%s…%s" % (term["ds"].isoformat(), term["de"].isoformat())
        probe = []
        gate = K.quote(model, term["ds"], term["de"], lambda u, s, e: probe.append(u), lambda m: list(units),
                       a.no_price_models)
        if not probe:                                                # ворота: дверь не зовётся
            human = gate["outcome"] == K.PRICE_HUMAN
            gate = M.mark_minimum(gate, term)
            why_g = (W_GATE_HUMAN % K.REASON_WORDS[gate["reason"]] if human and gate.get("reason") in K.REASON_WORDS
                     else W_GATE_UNKNOWN % (gate.get("why") or "ворота цены"))
            return self._res(T.UNKNOWN, at, why_g, dict(base, code="gate", gate=gate.get("reason") if human else None,
                                                        quote=gate if human else None),
                             read_at=taken, ref=ref, window=window)
        seen = []

        def door(u, s, e):
            seen.append(u)
            return self.door(u, s, e)
        avail = B.free_bikes(model, units, term["ds"], term["de"], rows, age, why, B.local_now(now), door)
        o = dict(base, avail=avail["outcome"], free=avail["free"], busy=avail["busy"], unchecked=avail["unchecked"],
                 line=avail["line"], unit=None)
        if avail["outcome"] == B.UNKNOWN:
            o["door_calls"] = self.door_calls - before
            return self._res(T.UNKNOWN, at, avail["why"], dict(o, code="avail"), read_at=taken, ref=ref,
                             window=window)
        q = None
        if avail["outcome"] == B.FREE:
            unit = seen[0]
            q = M.mark_minimum(K.quote(model, term["ds"], term["de"], door,
                                       lambda m: [unit] + [u for u in units if u != unit], a.no_price_models), term)
            o.update(unit=unit, quote=q)
        else:
            o["line"] = BUSY_LINE % (_mins(age), model, avail["date_start"], avail["date_end"], avail["units"])
        o["door_calls"] = self.door_calls - before
        fact = {"kind": "offer", "model": model, "date_start": o["date_from"], "date_end": o["date_to"],
                "days": o["days"], "min_days": o["min"], "client_days": o["client"], "avail": avail["outcome"],
                "unit": o["unit"], "units": avail["units"], "free": avail["free"], "busy": avail["busy"],
                "age": age, "read_at": taken, "door_at": at,
                "price_outcome": q["outcome"] if q else None, "day_price": q["day_price"] if q else None,
                "total": q["total"] if q else None, "deposit": q["deposit"] if q else None,
                "discount": q["discount"] if q else None, "currency": "THB"}
        return self._res(T.FACT, at, "", o, facts=[fact], read_at=taken, ref=ref, window=window)

    # ── что видит модель и что пишет журнал ─────────────────────────────────────────────────────────────────────

    def render(self):
        """Ответы offer → блок запроса модели ("" — вызовов не было). Юнита в блоке нет: его видит только сотрудник."""
        if not self.results:
            return ""
        out = [HEAD % max(0, self.limit - self.calls)]
        for i, r in enumerate(self.results, 1):
            o = r["offer"]
            name = o["model"] or ("«%s»" % o["asked"] if o["asked"] else "модель не названа")
            dates = ("%s — %s" % (o["date_from"], o["date_to"])) if o["date_from"] and o["date_to"] else "даты не разобраны"
            out.append("%d) offer %s, %s → %s%s" % (i, name, dates, r["outcome"],
                                                    (" · " + r["reason"]) if r["reason"] else ""))
            if r["outcome"] == T.FACT:
                out.append("   " + o["line"])
                if o["quote"]:
                    out.append("   ЦЕНА: " + (o["quote"].get("line") or ""))
                continue
            if o["quote"]:                                           # ворота человека — строка цены как у «ЦЕНА»
                out.append("   ЦЕНА: " + (o["quote"].get("line") or ""))
            code = o["code"]
            adv = (ADV_LIMIT if code == "limit" else ADV_MODEL if code in ("alias", "many", "fleet", "no_model") else
                   ADV_DATES if code in ("dates", "order", "past") else ADV_HUMAN if code == "gate" else ADV_LATER)
            out.append("   " + NOT_LINE % (r["reason"], adv))
        if any(r["outcome"] == T.FACT for r in self.results):
            out.append(FACT_NOTE)
        return "\n".join(out)

    def summary(self):
        """Строка журнала «offer:» — только числа."""
        facts = [r for r in self.results if r["outcome"] == T.FACT]
        return LOG_HEAD + L_SUM % (self.calls, len(facts), sum(1 for r in facts if r["offer"]["avail"] == B.FREE),
                                   sum(1 for r in facts if r["offer"]["avail"] == B.BUSY),
                                   len(self.results) - len(facts), self.over, self.door_calls, self.cached)


class Journal(T.Journal):
    """Журнал сверки `wa_agent_tools.Journal` + строки фактов offer (модель, даты, юнит — сотруднику; без номера)."""

    def __init__(self, number_tail=""):
        super(Journal, self).__init__(number_tail)
        self.offers = []

    def lines(self):
        out = super(Journal, self).lines()
        for r in self.offers:
            if r["outcome"] != T.FACT:
                continue
            o = r["offer"]
            f = {"model": o["model"], "date_start": o["date_from"], "date_end": o["date_to"], "avail": o["avail"],
                 "unit": o["unit"], "units": o["units"], "free": o["free"], "busy": o["busy"],
                 "snapshot_min": _mins(o["age"]), "door_calls": o["door_calls"], "cached": o["cached"]}
            q = o["quote"] or {}
            f.update({k: q[k] for k in ("day_price", "total", "deposit", "discount") if q.get(k) is not None})
            out.append("  offer факт %s" % json.dumps(f, ensure_ascii=False))
        return out


# ── цикл сверки: КОПИЯ `wa_agent_tools.run` (PARENT_SHA) с инструментом offer ────────────────────────────────────

def run(call, system, user, doors, offer, number="", clock=time.time, fresh=None, spend=None,
        max_calls=T.MAX_CALLS, max_sec=T.MAX_SEC, reserve=T.FALLBACK_SEC, handed=None, asked=None):
    """`wa_agent_tools.run` + инструмент offer (`offer` — `Offers` этой сверки). Правки помечены «OFFER»: строка
    инструмента в блоке «ИНСТРУМЕНТЫ»; блок ответов offer после блока результатов; вызов offer идёт в `offer`, а не в
    `results` (их судят `sift`/`judge`); журнал — `Journal` с ответами offer; в итоге — ключ `offers`. Предел вызовов
    модели и секунд — прежние и общие: offer — такой же ход модели и такая же дверь."""
    t0 = clock()
    deadline = t0 + max_sec
    stop = deadline - max(0.0, min(reserve, max_sec))
    jr = Journal(re.sub(r"\D", "", str(number))[-4:])                 # OFFER: журнал с ответами offer
    jr.asked = bool(asked)
    jr.offers = offer.results
    results, n = [], {"calls": 0, "doors": 0}

    def may_call():
        return clock() < stop

    def counted(fn):
        def door(**kw):
            n["doors"] += 1
            return fn(**kw)
        return door
    doors = {k: (counted(v) if callable(v) else v) for k, v in (doors or {}).items()}
    ctx = T.bind_ctx(number, doors, results, clock, may_call)
    tools_block = T.TOOLS_BLOCK % max_calls
    if T.CASE_TOOL in doors:                      # К4 (WA_AGENT_CASE): строка инструмента дела; выкл — блок прежний
        tools_block += "\n" + T.CASE_BLOCK
    tools_block += "\n" + OFFER_BLOCK                                # OFFER: строка инструмента
    head = tools_block + "\n\n" + user

    def out(state, raw=None, usage=None):
        return {"state": state, "raw": raw, "usage": usage, "results": results, "journal": jr, "calls": n["calls"],
                "doors": n["doors"], "sec": clock() - t0, "deadline": deadline, "asked": jr.asked,
                "offers": offer.results}                              # OFFER: ответы offer — отдельно от results
    while True:
        if fresh is not None and fresh():
            return out(T.ABORTED)
        if n["calls"] >= max_calls or not may_call():
            return out(T.OVER)
        block = T.render(results)
        more = offer.render()                                         # OFFER: ответы offer — после результатов
        if more:
            block = (block + "\n\n" + more) if block else more
        due = T.due_block(results)                        # итог «к оплате» — кодом, из факта аренды (часть B)
        if due:
            block = (block + "\n\n" + due) if block else due
        # K3-FIX3 п.2: расчёт сдачи — кодом, когда касса уже прочитана (до неё отказ «оплаты в кассе нет» был бы ложным)
        sums = T.change_block(results, handed) if any(r.get("tool") == "cash" for r in results) else ""
        if sums:
            block = (block + "\n\n" + sums) if block else sums
        raw, usage = call(system, head + ("\n\n" + block if block else ""))
        n["calls"] += 1
        if spend is not None:
            spend(usage)
        turn = T.parse_turn(raw)
        if turn is None or turn[0] == "final":
            if clock() > deadline:
                return out(T.OVER, usage=usage)
            return out(T.DONE, raw, usage)
        _, tool, args = turn
        if not may_call():                                # модель просит дверь, а времени на новый вызов нет
            return out(T.OVER, usage=usage)
        t1 = clock()
        if tool == OFFER_TOOL:                                        # OFFER: вызов offer — в `offer`, не в results
            before = offer.door_calls
            res = offer.call(args, clock)
            n["doors"] += offer.door_calls - before
        else:
            res = T.call_tool(tool, args, doors, clock, ctx)
            results.append(res)
        jr.call(len(results) + len(offer.results), tool, args, res, clock() - t1)


# ── примесь ─────────────────────────────────────────────────────────────────────────────────────────────────────

class OfferMixin:
    """Примесь к адаптеру модели: инструмент offer в сверке Т4а. Переопределяет ровно `_draft_tools`."""

    def _draft_tools(self, number, upto_id, hint=None):
        """КОПИЯ `ModelAdapter._draft_tools` (PARENT_SHA) с правками OFFER1910 (помечены «OFFER»): цикл — `run` этого
        модуля; опора денег, суток и дат — исход цены вместе с ценами принятых фактов offer; причины кода — с поправкой
        фактов offer (`offer_reasons`, `without_avail_words`); журнал — со строкой «offer:». Факты незавершённой сверки
        (предел) — не опора, и факты offer тоже."""
        if hint is None:
            system, user, info = self.build(number, upto_id)
        else:                                               # версия по пояснению со сверкой (Д2): блок пояснения
            system, user, info = self.build(number, upto_id, hint=hint)
        handed = T.cash_said(info.get("question"))         # K3-FIX3 п.2: переданные наличные — СЛОВА клиента
        asked = T.pay_asked(info.get("question"))          # K3-FIX шаг 3e: входящее клиента — об оплате (признак судье)
        # K3-FIX шаг 3g: тема оплаты открыта? — хвост и история перед ним блоками, от нашего последнего ответа назад, до
        # закрывающего события (признак правилу класса; блоков в сведениях нет — один обмен `before`, как в первой части)
        topic = T.pay_topic(info.get("question"), *(info.get("before") or ("", "")), blocks=info.get("blocks"),
                            now=info.get("judged"))
        offer = Offers(self, info.get("today"))           # OFFER: вызовы offer этой сверки
        with M.door_budget(T.MAX_SEC - T.FALLBACK_SEC):        # плечо моста не переживёт срок сверки (AGENTDEDUP0410)
            out = run(self.call, system, user, self._tool_doors(number, upto_id), offer, number=number,
                      clock=self.clock, fresh=(lambda: self.fresh(number, upto_id)) if self.fresh else None,
                      spend=lambda u: self._spend(u, "сверка:"), handed=handed, asked=asked)
        jr = out["journal"]
        if offer.calls:                                    # OFFER: строка журнала числами — на каждую сверку с offer
            self.log(offer.summary())
        if out["state"] == T.ABORTED:
            for line in jr.lines():
                self.log(line)
            self.log("сверка прервана: новое входящее — черновика нет")
            self.last = {"info": info, "tools": out}
            return None
        reasons, raw, usage = [], out["raw"], out["usage"]
        offers = out["offers"]                             # OFFER: ответы offer этой сверки
        if out["state"] == T.OVER:
            if self.clock() >= out["deadline"]:              # общий предел — и для запасного пути (AGENTDEDUP0410)
                for line in jr.lines():
                    self.log(line)
                self.log("сверка: общий предел %d с исчерпан — запасной вызов не начат, черновика нет (повтор позже)"
                         % T.MAX_SEC)
                self.last = {"info": info, "tools": out, "fallback": False}
                return None
            raw, usage = self.call(system, user)                # тот же один вызов, что и без флага
            self._spend(usage, "черновик:")
            reasons = [T.INCOMPLETE_WORDS]
            out["results"] = []                                 # факты незавершённой сверки не опора
            offers = []                                         # OFFER: и ответы offer — тоже
        facts_o = accepted(offers, info.get("last_in"))     # OFFER: принятые факты offer (свежие, по паре один раз)
        price = judged_price(info["price"], facts_o)       # OFFER: «ЦЕНА» ∪ цены фактов offer — опора суда
        info_j = judged_info(info, price, facts_o)         # OFFER: то же — проверкам суток и дат
        if self._cut(usage, "модель:"):                         # обрыв пределом — черновика нет (WAOPUSHIGHC0510)
            for line in jr.lines():
                self.log(line)
            self.last = {"info": info, "usage": usage, "raw": raw, "parsed": None, "tools": out}
            return None
        got = M.parse_reply(raw)
        # процент скидки за срок, названной дверью, — с опорой (WAPRICECTX0410): судья сверки процент судит без
        # исхода цены, поэтому названная дверью скидка снимается из текста до суда; прочее — как было
        said = K.without_known_discount(got["text"], price) if got else ""
        # K3-FIX шаг 3i (вариант В): судье — и сам текст входящего (с шага 3j правилу важен сам факт текста, не слова)
        words_t, figures = T.judge(said, price, out["results"], jr, handed=handed, asked=asked,
                                   incoming=info.get("question"),
                                   since=info.get("last_in"))
        for line in jr.lines():
            self.log(line)
        self.last = {"info": info, "usage": usage, "raw": raw, "parsed": got, "tools": out, "figures": figures}
        if got is None:
            self.log("модель: ответ не JSON или без текста — черновика нет (сверка %s, вызовов %d)"
                     % (out["state"], out["calls"]))
            return None
        # OFFER: причины кода — с поправкой ответов offer (принятый факт снимает «агент их не видит», только если каждая
        # модель, названная в тексте свободной, проверена свободной: иначе причина остаётся и «не совпадает с проверкой»)
        mismatch = avail_mismatch(got["text"], facts_o, offer.bikes)
        if mismatch:
            self.log(LOG_HEAD + L_MISMATCH % "; ".join(mismatch))
        words = [r["words"] for r in offer_reasons(info["code_reasons"], offers, facts_o, info.get("question"),
                                                   mismatch)]
        if got["lang"] not in ("ru", "en") and K.REASON_WORDS[K.R_LANGUAGE] not in words:
            words.append(K.REASON_WORDS[K.R_LANGUAGE])
        # K3-FIX шаг 3g (правило класса): тема оплаты открыта, а оплата кодом не подтверждена (принятые факты ЭТОЙ сверки;
        # у незавершённой их нет) — причина кода при любом тексте ответа. Она встаёт к причинам кода ДО причин модели
        # (пересказ модели об оплате отпадает как повтор); оплату уже назвал код по входящему — второй такой нет
        why_t, rule = T.topic_reason(topic, jr.facts)
        rule = K.merge_reasons(words, rule)[len(words):]
        words = K.merge_reasons(words + rule, got["handoff"])
        words = self._days_check(got["text"], info_j, words)    # сутки у дат (WADAYS0410)
        words = self._arrival_check(got["text"], info_j, words)   # срок и приезд без опоры (WATIMECLAIMB0510)
        words = self._lang_check(got["text"], info, words)      # язык ответа против языка разговора (WALANGCONVB0510)
        for w in reversed(words_t + rule):                      # причины кода о деньгах — вперёд
            words = K.reason_first(words, w)
        if why_t != T.PT_NONE:
            self.log("правило класса: %s; причина кода %s" % (
                why_t, "добавлена" if rule else "не добавлена (оплату уже назвал код по входящему)"
                if why_t in T.PT_OPEN else "не нужна"))
        for w in reversed(reasons):                             # «сверка не завершена» — самой первой
            words = K.reason_first(words, w)
        words = without_avail_words(words, facts_o, mismatch)   # OFFER: пересказ «агент их не видит» при факте снят
        self.log("модель: черновик %d симв. со сверкой (%s, вызовов %d, %.1f с), причин %d"
                 % (len(got["text"]), out["state"], out["calls"], out["sec"], len(words)))
        # проверка чисел кодом для низа карточки (WACARDUI0510): опора та же, что у судьи сверки — «ЦЕНА» ∪ факты
        known = T.known_amounts(price, jr.facts, figures)
        claims = T.money_claims(said, price, known)
        # USEFUL1310 A5: что установлено кодом — числа с опорой, подтверждена ли оплата (`pay_verdict` принятых фактов
        # этой сверки), предложения о деньгах при неподтверждённой оплате; вход модели не меняется
        checked = T.money_check(got["text"], price, known, judged=said, pay=T.pay_verdict(jr.facts)[0])
        res = dict({"text": got["text"], "handoff": words, "lang": got["lang"], "why": got["why"],
                    "claims": [list(c) for c in claims], "checked": checked}, **M.card_fields(info, got))
        if self.case is not None:
            # К4 (WA_AGENT_CASE): дело и версия, на которые написан черновик, и записи в дело по фактам сверки —
            # их делает ядро (`wa_agent.Core`, роль wa); адаптер только читает. Выкл — ответ прежний
            res["case"] = T.case_plan(out["results"], since=info.get("last_in"))
            self.log("дело: %s" % res["case"]["words"])
        return res


def with_offer(cls):
    """Класс адаптера → он же с примесью (один на cls). Уже с примесью — как есть. Копии не сверены (`drift`) или
    `_draft_tools` у cls уже свой — `ParentDrift`: примесь не надевается, адаптер прежний."""
    if issubclass(cls, OfferMixin):
        return cls
    if getattr(cls, "_draft_tools", None) is not M.ModelAdapter._draft_tools:
        raise ParentDrift("у %s свой _draft_tools — копия сверки его обошла бы" % cls.__name__)
    bad = drift()
    if bad:
        raise ParentDrift("исходник родителя изменился: %s" % ", ".join(bad))
    got = _CLASSES.get(cls)
    if got is None:
        got = _CLASSES[cls] = type("Offer" + cls.__name__, (OfferMixin, cls), {"__module__": __name__})
    return got
