# -*- coding: utf-8 -*-
"""Наличие по переписке — примесь к адаптеру модели (BOOKCTX1610, отрезок К2; флаг службы WA_AGENT_BOOK_CTX).

ЗАЧЕМ. Цене адаптер передаёт переписку (`price_pairs(ask, ctx, …)`), а наличию — только хвост: `ModelAdapter._book` берёт
модель и две даты из последнего сообщения клиента. «PCX 160 с 10 по 15 октября сколько?» → цена есть; затем «а свободен?»
→ наличия нет (двух дат в хвосте нет), черновик «коллега проверит», на карточке «наличие и брони — агент их не видит».
Названное клиентом переспрашивалось.

ЧТО ДЕЛАЕТ. `BookCtxMixin` переопределяет РОВНО `_history` (запоминает историю вызова) и `_book`. Сначала ответ родителя;
он остаётся как есть (без строки журнала), если брони выключены, родитель дал ответ (FREE/BUSY) или сам проверил пару
«модель + даты» хвоста, или в хвосте нет вопроса о наличии БАЙКА (`asks_bike`: слово наличия в клаузе без чужого
предмета — шлем, доставка, депозит…; бронь словами — к человеку). Иначе пары «модель + срок» из прежних слов КЛИЕНТА —
той же функцией, что у цены (`wa_agent_model.price_pairs`, только вызов), не больше `PAIRS_MAX`, по каждой —
`wa_book_read.free_bikes` (дверь цены — не больше раза на пару). Срок пары — даты клиента, а не минимум класса.
Отсевы в «неизвестно» (двери нет): в хвосте новый срок, который цена не разберёт в полные даты (G1, ДО снимка: прежний
срок НЕ подставляется) · в хвосте модель не из парка (G2) · сокращение модели неоднозначно · начала или срока нет · срок
прошёл или начался (в том числе унесённый ценой на год вперёд от дня, когда клиент его назвал) · время сообщений
неизвестно · срок пары не назван целиком ни в одном сообщении клиента · ПОСЛЕ слов пары клиент назвал другую модель
или другой срок. Проверенная пара — «неизвестно», если на её даты в таблице бронь по номеру этого клиента, или если
она «занята», а в переписке шла речь о брони (это может быть его же бронь). Пары разошлись (одна свободна, другая
занята) — исход «неизвестно», решает человек. История чужого номера или чужого хвоста — ответ родителя. Любое
исключение — ответ родителя и строка журнала.

ГРАНИЦЫ. Брони не пишутся, альтернатив при занятом нет, новых инструментов и правки промпта нет: «свободен» ставит только
`free_bikes` по ответу двери цены `available is True`, клиенту — только по «Отправить» человека. Импорты — ровно
`datetime`, `re`, `wa_agent_model`, `wa_book_read`, `wa_agent_knowledge`; файлов, сети и базы модуль не касается. Чужие
функции зовутся через атрибут модуля (`M.price_pairs`, `B.free_bikes`). В журнал — только числа и слова: ни номера, ни
моделей, ни дат, ни текста клиента; контакты строк броней читаются только для сверки ключа номера и наружу не идут.

ПОДКЛЮЧЕНИЕ. `with_book_ctx(cls)` → класс «примесь + cls» (один на cls); служба (`wa_agent_svc.book_ctx_of`) меняет класс
уже собранного адаптера (`ModelAdapter` или `ContractStateAdapter`). Флаг выключен — модуль не импортируется вовсе."""
import datetime
import re

import wa_agent_knowledge as K
import wa_agent_model as M
import wa_book_read as B

PAIRS_MAX = M.PAIRS_MAX                          # пар «модель + срок» на вопрос — как у цены (3)
LOG_HEAD = "наличие по переписке: "

# ── формы блока НАЛИЧИЕ (DESIGN_BOOKCTX1610 §5, дословно) ────────────────────────────────────────────────────────
CTX_HEAD = ("НАЛИЧИЕ ПО ПЕРЕПИСКЕ (чего нет в последнем сообщении клиента — модели или дат, — код взял из его прежних "
            "слов теми же парами «модель + срок», что у цены): о наличии говори только по строке своей пары и называй её "
            "модель и даты; спрашивает клиент сейчас о другой модели или других датах — эти строки не о том, уточни у него.")
PAIR_LINE = "— %s: %s"                       # (метка пары, строка исхода)
SIEVE_LINE = "НАЛИЧИЕ: НЕИЗВЕСТНО — %s. Не говори ни «есть», ни «нет», ни «свободен»; %s"   # (why, advice)
G_TERM_LINE = ("НАЛИЧИЕ: НЕИЗВЕСТНО — в последнем сообщении клиент назвал срок без полной даты (без месяца, без конца "
               "или числом суток); прежний срок из переписки НЕ подставлен. Не говори ни «есть», ни «нет», ни «свободен»; "
               "спроси у клиента даты с месяцем (с какого по какое число).")
G_MODEL_LINE = ("НАЛИЧИЕ: НЕИЗВЕСТНО — в последнем сообщении клиент назвал модель, которой код не нашёл в парке; прежняя "
                "модель из переписки НЕ подставлена. Не говори ни «есть», ни «нет», ни «свободен»; скажи, что коллега "
                "проверит, и уточни у клиента модель.")
W_G_TERM = "в последнем сообщении срок без полной даты — прежний срок не подставлен"
W_G_MODEL = "в последнем сообщении модель не из парка — прежняя модель не подставлена"

# ── отсевы пары (§4, дословно) ──────────────────────────────────────────────────────────────────────────────────
W_ALIAS = "модель не определена: «%s» подходит к моделям парка %s"
W_NO_START = "дата начала аренды в переписке не названа"
W_NO_TERM = "срок для этой модели клиент не называл"
W_PAST = "срок из переписки уже прошёл или начался"
W_NO_TIME = "время сообщений клиента неизвестно — срок не привязан к дате"
ADV_MODEL = "спроси у клиента, какая модель."
ADV_DATES = "спроси у клиента даты (с какого по какое число)."
ADV_PAST = "спроси у клиента новые даты."

# ── отсевы сверх проекта (находки критиков BOOKCTX1610; в «неизвестно», двери нет) ─────────────────────────────────
W_SPLIT = "срок собран из разных сообщений клиента — целиком он его не называл"
W_LATER_MODEL = "после этих слов клиент называл другую модель"
W_LATER_TERM = "после этих слов клиент называл другой срок"
ADV_WHICH = "спроси у клиента, о какой модели речь."
# ── проверенная пара → «неизвестно» (свою бронь клиента занятостью не называем; дверь уже спрошена) ────────────────
W_OWN = "на эти даты в таблице есть бронь по номеру этого клиента — занятость может быть его же бронью"
W_BOOK_TALK = "в переписке шла речь о брони — «занято» может быть бронью самого клиента"
# ── исход блока: пары разошлись (одна свободна, другая занята) ────────────────────────────────────────────────────
W_MIXED = "пары переписки разошлись: одна свободна, другая занята — о какой модели или сроке речь, решает человек"

# ── строки журнала (§7): только числа и слова ──────────────────────────────────────────────────────────────────
L_HIST = "история не та — ответ родителя"
L_SNAP = "снимок не служит (%s) — ответ родителя"
L_NO_PAIRS = "пар нет — ответ родителя"
L_TERM = "срок в последнем сообщении без полной даты — НЕИЗВЕСТНО, прежний срок не подставлен"
L_MODEL = "модель в последнем сообщении не из парка — НЕИЗВЕСТНО, прежняя модель не подставлена"
L_PAIRS = "пар %d%s: свободно %d, занято %d, неизвестно %d (отсев %d); дверь %d; снимок %d мин"
L_FAIL = "сбой %s — ответ родителя"

# срок в хвосте без полной даты: «на 20–25», «с 20-го», «20th», «20 числа» (§4, дословно)
_RX_LOOSE_TERM = re.compile(
    r"(?i)(?<![\d.:/])\d{1,2}\s*(?:-|–|—|/)\s*\d{1,2}(?![\d.:/])"
    r"|(?<!\w)(?:с|со|до|from|till|until)\s+\d{1,2}(?![\d.:/])"
    r"|(?<!\d)\d{1,2}\s*-?\s*(?:го|ое|е|st|nd|rd|th)(?!\w)"
    r"|(?<!\d)\d{1,2}\s+числа")
# день словом («завтра», «сегодня-завтра», «на завтрашний день», «today») — срок, даже когда день вопроса неизвестен
# (ask_day None: `find_dates` его не видит). Сверх проекта §4: без этого «а завтра?» ушло бы в `price_pairs`, и та
# подставила бы прежний срок — ровно ловушка G1. Дефис — граница слова («сегодня-завтра»).
_RX_REL_TERM = re.compile(r"(?i)(?<!\w)(?:послезавтра|завтра|сегодня)(?:шн\w*)?(?!\w)"
                          r"|\b(?:day\s+after\s+tomorrow|tomorrow|today|tonight)\b")
# срок словами без чисел (находка I1 критика A): неделя, месяц, выходные, будни, месяц и день недели по имени, «на
# сутки», «через 2 дня», «next week», «for a month», «in 3 days». «may» — только «in/for/during may» («May I…» не срок).
_RX_PERIOD = re.compile(
    r"(?i)(?<!\w)(?:недел\w*|месяц\w*|выходн\w*|будн\w*|январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]|июн\w*|июл\w*|"
    r"август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*|понедельник\w*|вторник\w*|сред[ауы]|четверг\w*|пятниц\w*|"
    r"суббот\w*|воскресень\w*|на\s+(?:сутки|день|ночь)|через\s+(?:день|неделю|месяц|\S+\s+(?:дн|день|сут|ноч|недел|"
    r"месяц)\w*))(?!\w)"
    r"|\b(?:weeks?|weekends?|weekdays?|months?|fortnight|january|february|march|april|june|july|august|september|"
    r"october|november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
    r"|\b(?:in|for|during)\s+may\b|\bfor\s+(?:a|one|the)\s+(?:day|night)\b"
    r"|\b(?:in|within|after)\s+(?:\d{1,3}|an?|one|two|three|four|five|six|seven|few|a\s+few|couple(?:\s+of)?)\s+"
    r"(?:days?|nights?|weeks?|months?)\b")
# «сейчас», «now» — срок только в ХВОСТЕ вопроса о наличии («а сейчас свободен?»); в прежних репликах это частое
# слово-заполнитель («сейчас посмотрю») и признаком другого срока не служит
_RX_NOW = re.compile(r"(?i)(?<!\w)(?:сейчас|прямо\s+сейчас)(?!\w)|\b(?:right\s+)?now\b")
# похоже на модель: латиница и трёхзначная кубатура (§4, дословно)
_RX_MODEL_LIKE = re.compile(r"(?i)(?<![a-z0-9])[a-z][a-z-]*[a-z]\s*-?\s*\d{3}(?!\d)")

# ── вопрос о наличии БАЙКА (находки I3 критика A и I4 критика правды) ─────────────────────────────────────────────
# Слова наличия — подмножество `wa_book_read._RX_AVAIL` БЕЗ слов брони («бронь в силе?», «is my booking confirmed?» —
# вопрос о брони, его решает человек: родитель так и отвечает). Клауза с чужим предметом («а шлем есть?», «Is delivery
# free?», «any discount…», «Есть ли депозит?») вопросом о байке не считается; хватает ОДНОЙ клаузы без чужого предмета
# («а свободен? и сколько депозит?»).
_RX_AVAIL_BIKE = re.compile(
    r"(?i)свобод|налич(?:ие|ии|ия)|занят|есть\s+ли|есть\s*\?|будет\s+ли|available|availab|"
    r"do\s+you\s+have|have\s+you\s+got|is\s+there|are\s+there|\bany\b|\bfree\b")
_RX_FOREIGN = re.compile(
    r"(?i)шлем|(?<!\w)каск|доставк|скидк|депозит|залог|страхов|паспорт|водительск|лиценз|держател|багажник|кофр|"
    r"ящик|перчат|дождевик|экипировк|кресл|бензин|топлив|заправ|оплат|наличн|наличк|(?<!\w)карт(?:а|у|ы|ой|е)(?!\w)|"
    r"(?<!\w)кэш|зарядк|кабел|сим-?карт|симк|вай-?фай|трансфер|такси|экскурс|мойк|чех[оа]л|"
    r"helmet|deliver|discount|deposit|insurance|passport|licen[cs]e|holder|\bbox\b|\bgloves?\b|rain\s*coat|"
    r"\bseat\b|\bfuel\b|petrol|gasoline|\bgas\b|payment|\bpay\b|\bcards?\b|\bcash\b|transfer|taxi|\btours?\b|"
    r"wi-?fi|\bsim\b|charger|\bcable\b|\block\b|\bchain\b")
_RX_CLAUSE = re.compile(r"(?<=[?!.;,\n])|\s+(?:и|а\s+также|а\s+ещё|а\s+еще|and|also|plus)\s+", re.I)

_CLASSES = {}                                    # with_book_ctx: класс «примесь + cls», один на cls


# ── чистые функции ──────────────────────────────────────────────────────────────────────────────────────────────

def asks_bike(ask):
    """Хвост спрашивает о наличии байка → True: есть клауза со словом наличия (без слов брони) и без чужого предмета."""
    return any(_RX_AVAIL_BIKE.search(c) and not _RX_FOREIGN.search(c)
               for c in _RX_CLAUSE.split(str(ask or "")) if c)


def term_parsed(ask, today, ask_day=None):
    """Срок, который `price_pairs` возьмёт из ЭТИХ слов как полные даты (её же правилами): полный диапазон
    (`find_ranges` с днём слов); иначе — если диапазонов и чисел суток нет — две даты по возрастанию (`find_dates` без
    дня, как у неё). Число суток без дат полным сроком НЕ считается: его начало `price_pairs` ищет в других словах."""
    s = str(ask or "")
    ranges = M.find_ranges(s, today, ask_day)
    if [r for r in ranges if r["ds"] is not None]:
        return True
    if not ranges and [n for _a, n in M.count_list(s) if 0 < n <= M.TERM_MAX_DAYS]:
        return False
    dates = M.find_dates(s, today)
    return len(dates) >= 2 and dates[1] > dates[0]


def _loose(s, today, day):
    """Признак срока в словах (любой, разобранный или нет)."""
    return bool([r for r in M.find_ranges(s, today, day) if r["ds"] is None] or M.find_dates(s, today, day)
                or _RX_LOOSE_TERM.search(s) or M.count_list(s) or _RX_REL_TERM.search(s) or _RX_PERIOD.search(s))


def term_in_tail(ask, today, ask_day=None):
    """Хвост называет НОВЫЙ срок, которого `price_pairs` не разберёт в полные даты → True (G1): полного срока её правилами
    нет (`term_parsed`), и есть хотя бы один признак срока — диапазон без месяца («с 20 по 25»), дата (в том числе
    словом от дня вопроса: «сегодня или завтра»), вольная запись (`_RX_LOOSE_TERM`), число суток без дат
    (`M.count_list`), день словом (`_RX_REL_TERM`), срок словами («на неделю», «в ноябре», «next week» — `_RX_PERIOD`),
    «сейчас»/«now»."""
    s = str(ask or "")
    if term_parsed(s, today, ask_day):
        return False
    return _loose(s, today, ask_day) or bool(_RX_NOW.search(s))


def term_sign(text, today, day=None):
    """В прежних словах клиента есть хоть какой-то срок (разобранный или нет) → True. «сейчас»/«now» — не срок."""
    s = str(text or "")
    return term_parsed(s, today, day) or _loose(s, today, day)


def model_in_tail(ask, bikes):
    """Хвост называет модель (латиница + трёхзначная кубатура), которой нет среди упоминаний парка `M.model_hits` →
    True: прежняя модель переписки за неё не идёт («Vespa 150», «PCX 150», «CB 500»)."""
    s = str(ask or "")
    hits = M.model_hits(s, bikes)
    for m in _RX_MODEL_LIKE.finditer(s):
        if not any(h[0] < m.end() and m.start() < h[1] for h in hits):
            return True
    return False


def said_day(ctx, ask_day=None):
    """Самый ранний день сообщений клиента: день вопроса и дни его реплик переписки ((кто, текст, день)) → date | None."""
    days = {ask_day} if ask_day is not None else set()
    for c in ctx or ():
        if isinstance(c, (tuple, list)) and len(c) == 3 and c[0] == M.WHO_CLIENT and c[2] is not None:
            days.add(c[2])
    return min(days) if days else None


def first(said, ds):
    """Ближайшая к дню said (не раньше него) дата с числом и месяцем ds. Нет такого дня в году (29.02) — ValueError."""
    f = datetime.date(said.year, ds.month, ds.day)
    if f < said:
        f = datetime.date(said.year + 1, ds.month, ds.day)
    return f


def sieve(model, t, today, said):
    """Пара «модель + срок» (`price_pairs`) → (code, why, advice, ds, de). code None — пара проверяется на [ds, de]
    (даты КЛИЕНТА: срок, растянутый ценой до минимума класса, сжат обратно до названного клиентом); иначе отсев."""
    ds, de = t.get("ds"), t.get("de")
    if isinstance(model, dict):
        return "alias", W_ALIAS % (model["alias"], " / ".join(model["cands"])), ADV_MODEL, ds, de
    if ds is None:
        return "no_start", W_NO_START, ADV_DATES, None, None
    if t.get("min") and not t.get("client"):
        return "no_term", W_NO_TERM, ADV_DATES, None, None
    if t.get("min") and t.get("client"):
        de = ds + datetime.timedelta(days=t["client"])
    past = ds < today
    if not past and said is not None:
        try:
            past = first(said, ds) < ds
        except ValueError:
            past = True
    if past:
        return "past", W_PAST, ADV_PAST, ds, de
    if said is None:
        return "no_time", W_NO_TIME, ADV_DATES, ds, de
    return None, None, None, ds, de


def hit_ident(hit):
    """Упоминание модели (`M.model_hits`) → ключ тождества, как у `price_pairs`: модель парка; сокращение — «?» + слово."""
    return hit[2] if hit[2] is not None else "?" + str(hit[3]).lower()


def pair_ident(model):
    """Модель пары → тот же ключ тождества."""
    return model if isinstance(model, str) else "?" + str(model.get("alias") or "").lower()


def names_term(text, today, day, ds, de):
    """Слова ОДНОГО сообщения называют срок [ds, de] целиком: диапазоном, двумя датами или датой начала и числом суток
    (с днём сообщения и без него — как разные пути `price_pairs`)."""
    s = str(text or "")
    for d in (day, None):
        if [r for r in M.find_ranges(s, today, d) if r["ds"] == ds and r["de"] == de]:
            return True
        dates = M.find_dates(s, today, d)
        if ds in dates and (de in dates or (de - ds).days in [n for _a, n in M.count_list(s)]):
            return True
    return False


def drift(model, ds, de, msgs, today, bikes, idents):
    """Пара (даты клиента) против его сообщений `msgs` = [(текст, день)], новые первыми, [0] — хвост → (code, why,
    advice) | (None, None, None). Срок пары не назван целиком ни в одном сообщении — «split_term»; новее сообщения, где
    названа модель пары, клиент называл модель не из пар или не из парка — «later_model»; новее сообщения, где назван
    срок пары, клиент называл любой срок — «later_term»."""
    t_src = next((i for i, (s, d) in enumerate(msgs) if names_term(s, today, d, ds, de)), None)
    if t_src is None:
        return "split_term", W_SPLIT, ADV_DATES
    mine = pair_ident(model)
    m_src = next((i for i, (s, _d) in enumerate(msgs) if [h for h in M.model_hits(s, bikes) if hit_ident(h) == mine]),
                 len(msgs))
    for s, _d in msgs[1:m_src]:
        if model_in_tail(s, bikes) or [h for h in M.model_hits(s, bikes) if hit_ident(h) not in idents]:
            return "later_model", W_LATER_MODEL, ADV_WHICH
    for s, d in msgs[1:t_src]:
        if term_sign(s, today, d):
            return "later_term", W_LATER_TERM, ADV_DATES
    return None, None, None


def own_booking(number, rows, units, ds, de):
    """На юнитах пары в [ds, de] занимающая строка с номером этого клиента в «контактах» (последние 9 цифр, как
    `rental_end`) → True. Контакты наружу не идут: ответ — только да/нет."""
    digits = re.sub(r"\D", "", str(number or ""))
    if len(digits) < B.KEY_DIGITS:
        return False
    key, names = digits[-B.KEY_DIGITS:], {B.qnorm(u) for u in units or ()}
    for r in rows or ():
        if B.qnorm(r.get("bike")) not in names or not B.is_busy(r):
            continue
        rs, re_ = B.day_of(r.get("date_start")), B.day_of(r.get("date_end"))
        if rs is not None and re_ is not None and rs <= de and re_ >= ds and key in B.phone_keys(r.get("contacts")):
            return True
    return False


def pair_name(model):
    """Имя пары: модель парка как есть, сокращение — в ёлочках."""
    return model if isinstance(model, str) else "«%s»" % model["alias"]


def pair_label(model, code, ds, de):
    """Метка пары: имя и даты клиента «(с ДД.ММ по ДД.ММ)» без года; дат нет или срок не назван — только имя."""
    name = pair_name(model)
    if ds is not None and de is not None and code != "no_term":
        return "%s (с %s по %s)" % (name, ds.strftime("%d.%m"), de.strftime("%d.%m"))
    return name


def _iso(d):
    return d.isoformat() if d is not None else None


def _g_avail(line, why, kind, age):
    """Блок G1 / G2 → словарь наличия: одна строка, исход «неизвестно», двери нет."""
    return {"outcome": B.UNKNOWN, "model": None, "date_start": None, "date_end": None, "units": 0, "free": 0,
            "busy": 0, "unchecked": 0, "age": age, "door_calls": 0, "why": why, "line": line, "source": "ctx",
            "sieve": kind, "dropped": 0, "pairs": []}


def ctx_avail(got, dropped, age):
    """Исходы пар [(модель, code, why, ds, de, r | None, line)] → словарь наличия (§6) и строка журнала (§7, L6).
    Исход блока: «неизвестно», если неизвестна хоть одна пара; FREE / BUSY — только если такова КАЖДАЯ пара; пары
    разошлись (свободна и занята) — «неизвестно» (W_MIXED), решает человек. «Отсев» в журнале — пары без двери."""
    pairs, checked, whys = [], [], []
    for model, code, why, ds, de, r, line in got:
        outcome = r["outcome"] if r is not None else B.UNKNOWN
        w = r["why"] if r is not None else why
        pairs.append({"model": model if isinstance(model, str) else model["alias"], "date_start": _iso(ds),
                      "date_end": _iso(de), "outcome": outcome, "sieve": code, "why": w,
                      "door_calls": r["door_calls"] if r is not None else 0,
                      "line": PAIR_LINE % (pair_label(model, code, ds, de), line)})
        if r is not None:
            checked.append(r)
        if outcome == B.UNKNOWN and w not in whys:
            whys.append(w)
    outs = [p["outcome"] for p in pairs]
    if B.UNKNOWN in outs:
        outcome = B.UNKNOWN
    elif all(o == B.FREE for o in outs):
        outcome = B.FREE
    elif all(o == B.BUSY for o in outs):
        outcome = B.BUSY
    else:
        outcome = B.UNKNOWN
    if B.FREE in outs and B.BUSY in outs:
        whys.append(W_MIXED)
    avail = {"outcome": outcome, "model": pairs[0]["model"],
             "date_start": checked[0]["date_start"] if checked else None,
             "date_end": checked[0]["date_end"] if checked else None,
             "units": sum(r["units"] for r in checked), "free": sum(r["free"] for r in checked),
             "busy": sum(r["busy"] for r in checked), "unchecked": sum(r["unchecked"] for r in checked),
             "age": age, "door_calls": sum(r["door_calls"] for r in checked),
             "why": "" if outcome in (B.FREE, B.BUSY) else "; ".join(whys),
             "line": CTX_HEAD + "\n" + "\n".join(p["line"] for p in pairs),
             "source": "ctx", "sieve": None, "dropped": dropped, "pairs": pairs}
    words = L_PAIRS % (len(pairs), " (сверх предела %d)" % dropped if dropped else "", outs.count(B.FREE),
                       outs.count(B.BUSY), outs.count(B.UNKNOWN), sum(1 for g in got if g[5] is None),
                       avail["door_calls"], int((age or 0) // 60))
    return avail, words


# ── примесь ─────────────────────────────────────────────────────────────────────────────────────────────────────

class BookCtxMixin:
    """Примесь к адаптеру модели: наличие по переписке, когда в последнем сообщении клиента нет модели или дат."""

    def _history(self, number, upto_id):
        items, missing = super()._history(number, upto_id)
        self._bctx_hist = (str(number), items)
        return items, missing

    def _book(self, number, ask, today, now, ask_day=None):
        res = super()._book(number, ask, today, now, ask_day)
        avail, rental, words = res
        seen = self.__dict__.pop("_bctx_hist", None)
        if self.book is None or not B.avail_ask(ask) or not asks_bike(ask):
            return res
        if avail is not None and (avail["outcome"] in (B.FREE, B.BUSY)
                                  or (avail.get("model") and avail.get("date_start"))):
            return res                                   # родитель сам проверил пару хвоста — вторая дверь не нужна
        try:
            got = self._bctx_ctx(seen, number, ask, today, now, ask_day)
        except Exception as e:                                       # noqa: BLE001 — сбой примеси: ответ родителя
            self.log(LOG_HEAD + L_FAIL % type(e).__name__)
            return res
        if got is None:
            return res
        avail_new, line = got
        return avail_new, rental, words + " · " + LOG_HEAD + line

    def _bctx_ctx(self, seen, number, ask, today, now, ask_day):
        """Шаги 5–13 проекта → (наличие, строка журнала) | None (ответ родителя; строка журнала уже записана)."""
        if seen is None or seen[0] != str(number):
            self.log(LOG_HEAD + L_HIST)
            return None
        items = seen[1]
        tail = self._tail(items)
        tail_text = K.mask("\n".join(it["text"] or ("[%s]" % it["word"] if it["word"] else "")
                                     for it in tail)[-M.TAIL_MAX:])[0]
        if tail_text != ask:
            self.log(LOG_HEAD + L_HIST)
            return None
        ctx = self._context(items, tail)
        if term_in_tail(ask, today, ask_day):                        # G1 — до снимка: мост не зовётся
            self.log(LOG_HEAD + L_TERM)
            return _g_avail(G_TERM_LINE, W_G_TERM, "term_in_tail", None), L_TERM
        rows, bikes, age, why = self.book.get(now)
        if rows is None:
            self.log(LOG_HEAD + L_SNAP % (why or "причина не названа"))
            return None
        if model_in_tail(ask, bikes):                                # G2
            self.log(LOG_HEAD + L_MODEL)
            return _g_avail(G_MODEL_LINE, W_G_MODEL, "model_in_tail", age), L_MODEL
        pairs, dropped = M.price_pairs(ask, ctx, today, bikes, ask_day)
        if not pairs:
            self.log(LOG_HEAD + L_NO_PAIRS)
            return None
        said = said_day(ctx, ask_day)
        now_local = B.local_now(now)
        mine = [(ask, ask_day)] + [(c[1], c[2]) for c in ctx
                                   if isinstance(c, (tuple, list)) and len(c) == 3 and c[0] == M.WHO_CLIENT]
        talk = B.book_intent(ask) or any(B.book_intent(c[1]) for c in ctx if isinstance(c, (tuple, list)) and len(c) > 1)
        idents = {pair_ident(m) for m, _t in pairs}
        got, keys = [], set()
        for model, t in pairs:
            code, w, adv, ds, de = sieve(model, t, today, said)
            if code is None:
                code, w, adv = drift(model, ds, de, mine, today, bikes, idents)
            key = (pair_name(model), ds, de, code)
            if key in keys:
                continue
            keys.add(key)
            if code is not None:
                got.append((model, code, w, ds, de, None, SIEVE_LINE % (w, adv)))
                continue
            units = M.units_of(model, bikes)
            r = B.free_bikes(model, units, ds, de, rows, age, why, now_local, self.door)
            if r["outcome"] in (B.FREE, B.BUSY) and own_booking(number, rows, units, ds, de):
                r, code = B._avail_unknown(dict(r), W_OWN), "own_booking"
            elif r["outcome"] == B.BUSY and talk:
                r, code = B._avail_unknown(dict(r), W_BOOK_TALK), "booking_talk"
            got.append((model, code, r["why"], ds, de, r, r["line"]))
        avail, line = ctx_avail(got, dropped, age)
        self.log(LOG_HEAD + line)
        return avail, line


def with_book_ctx(cls):
    """Класс адаптера → он же с примесью (один на cls). Уже с примесью — как есть: повторное надевание ничего не меняет."""
    if issubclass(cls, BookCtxMixin):
        return cls
    got = _CLASSES.get(cls)
    if got is None:
        got = _CLASSES[cls] = type("BookCtx" + cls.__name__, (BookCtxMixin, cls), {"__module__": __name__})
    return got
