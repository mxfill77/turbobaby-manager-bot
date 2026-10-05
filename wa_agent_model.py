#!/usr/bin/env python3
"""АДАПТЕР МОДЕЛИ СЛУЖБЫ wa-agent — `Model.draft(number, upto_id)` (WAAGENTMODEL0210, задание 0107-77b).

Повод — слова владельца 01.10: «Пересказывать ничего не надо, он должен быть умным. И отвечать на
запросы, которые сейчас просят клиенты, видеть контекст»; «Все ответы да» (цены из двери, платный ключ).

ЧТО ИДЁТ В МОДЕЛЬ (одним вызовом на черновик):
  • вся история клиента — `wa_history.read_history` (архив копии телефона + очередь), обрезанная по
    upto_id: строки очереди новее черновика не идут (их перепроверит ядро);
  • МАСКА ДО МОДЕЛИ — `wa_agent_knowledge.mask` на всё, что пишет клиент или мы: пароли, ключи, коды,
    карты уходят меткой «[скрыто: …]»;
  • снимки узлов `faq` и `business_rules` с возрастом (`wa_agent_knowledge.Knowledge`); не прочитан —
    НЕИЗВЕСТНО словами, а не пусто. Снимок старше предела (`max_stale`, 3 × `max_age` = 30 мин, WAKNOWFRESH0310)
    — тоже НЕИЗВЕСТНО, без текста, и причина «знания устарели» первой из причин кода;
  • цена — `wa_agent_knowledge.quote` ТОЛЬКО когда клиент сейчас спрашивает о цене. Модель и обе даты в его
    словах — одна дверь. Модели или дат нет — пары «модель + срок» из последних сообщений диалога, наших и клиента
    (WAPRICECTX0410): до трёх, каждая — своя дверь с прежними воротами; срок числом суток — от начала из переписки,
    начала нет — числа нет, агент спрашивает даты. Модель ищется по ключу живых имён парка (`wa_book_read`,
    WADRAFTFIX0210). Скидка за срок — в строке цены всегда, и 0%; дверь её не назвала — «неизвестна» и причина;
  • причины «нужен человек» кодом — `wa_agent_knowledge.handoff` по тому, что клиент спрашивает сейчас;
  • уроки людей (WAAGENTLESSON0210) — ТОЛЬКО действующие (`wa_agent.active_lessons`, своя база агента
    mode=ro), блоком с номерами, под той же маской; кандидат и откатанный не идут. Нет базы уроков
    (`lessons_db` пуст — WA_AGENT_LESSONS выключен) — блока нет, как раньше;
  • брони ТОЛЬКО на чтение (WABOOKTOOLS0210, `wa_book_read`) — тем же путём, что цена: кодом ДО модели и только
    на явный вопрос. «Свободен ли байк» — слово наличия, модель из парка и обе даты → блок «НАЛИЧИЕ»; «когда
    кончается аренда» → блок «АРЕНДА КЛИЕНТА» по номеру WhatsApp; у обоих возраст снимка. Нет факта — причина
    «нужен человек». Снимка нет (`book` пуст — WA_AGENT_BOOK_READ выключен) — промпт байт-в-байт прежний.

НАПОМИНАНИЕ ПРИТИХШЕМУ (WAFOLLOWUP0210) — `followup(number, upto_id)`: своя инструкция, история под маской, узлы
знаний и действующие уроки; цен и «нужен человек» нет. Ответ — JSON {skip, text, lang, why}: skip=true —
«не нужно» (ядро карточки не делает), текст — черновик напоминания, прочее — None (повтор позже).

ОТВЕТ МОДЕЛИ — JSON {text, lang, handoff[], why}. Не JSON, нет текста — черновика нет, строка журнала
(ядро повторит не раньше MODEL_RETRY_SEC). lang не ru/en — причина «язык». Итог `draft` — словарь
{text, handoff[слова], lang, why} (ядро принимает и прежнюю строку); причины — кода и модели вместе.

КАРТОЧКА СОТРУДНИКА (WACARDQ0410) — итог `draft` несёт ещё {question, q_lang, q_ru, text_ru}: вопрос — блок последних
реплик клиента ровно в том виде, что ушёл в модель (под маской); язык вопроса — кодом (`question_lang` → `K.lang_of`);
не русский — тем же вызовом два перевода на русский (блок `TR_BLOCK` в сообщении), русский — переводов нет. Клиенту
уходит только text.

НАШИ ПРЕЖНИЕ СЛОВА (WAOURWORDS0410) — правило 12 инструкции: строки «мы» в истории обязывают, из двух наших сообщений
о том же действует более позднее, расхождение со знаниями — в handoff. «Позднее» модель читает по времени строки:
`wa_history.model_line` даёт каждой «ДД.ММ.ГГГГ ЧЧ:ММ» (Пхукет). Кодом правило не проверяется: проверка денег
(`K.money_claims`) нашу прежнюю сумму опорой по-прежнему не считает — повтор ставит причину «нужен человек».

ПЛАТЕЛЬЩИК — платный ключ API тем же путём, что у Splinter (`claude_client.ClaudeClient`:
ANTHROPIC_API_KEY из .env корня дерева, учёт трат `spend_ledger.meter`). Значение ключа не печатается.

ЖУРНАЛ — только номер черновика у ядра, объёмы, токены, причины словами. Текстов, номеров и имён
клиентов в журнале нет. Знания — строкой «знания: …» на каждый вызов (WAKNOWFRESH0310): имя узла, прочитан ли
сейчас, длина, sha16 и возраст снимка; текста узлов в журнале нет.

КЭШ ПРОМПТА (WAAGENTCACHE0210) — выключатель службы WA_AGENT_CACHE: «1h»/«5m» — срок, 1/true/yes/on — 1h,
прочее и пусто — выключен (запрос байт-в-байт прежний). Включён — неизменная часть идёт ВПЕРЕДИ одним
системным префиксом: инструкция, затем снимки `faq` и `business_rules` БЕЗ возраста (меняются только со
сменой узла) с отметкой `cache_control` на последнем блоке; возраст узлов, уроки, цена, факты, история и
вопрос — после, в сообщении. Цена каждого вызова считается по usage (вход, запись в кэш 5 мин/1 ч, чтение
из кэша, выход) — строкой журнала и итогом в сводку службы (`spend`). Множители — по документации Anthropic
«Prompt caching»: запись 5 мин 1.25× цены входа, запись 1 ч 2×, чтение 0.1×.
"""

import datetime
import hashlib
import json
import os
import re
import sqlite3
import time

import wa_agent
import wa_agent_knowledge as K
import wa_book_read as B
import wa_history

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = "claude-sonnet-4-5"          # как CLAUDE_MODEL Splinter по умолчанию (claude_client)
# WACARDQ0410: при вопросе не по-русски тот же ответ несёт ещё два перевода (вопроса до TR_Q_MAX знаков и ответа);
# при 700 длинный вопрос обрывал бы JSON — черновика не было бы вовсе. Цена — по фактическим токенам, не по пределу
MAX_TOKENS = 1500
HISTORY_MAX = 60000                           # символов истории; старше — обрезается с головы, словами
TAIL_MAX = 4000
LESSON_ITEM_MAX = 600                         # было/стало/причина одного урока в промпте, символов
LESSONS_MAX = 8000                            # блок уроков целиком; не помещается — старшие уходят, словами
LESSONS_HEAD = ("УРОКИ ЛЮДЕЙ — действующие правила (поправки сотрудников к прежним черновикам, утверждены "
                "владельцем), по номерам. В похожем случае пиши так, как «стало», и следуй причине. Имён, "
                "номеров, дат и сумм из примеров не переноси — это переписка другого клиента; правила выше "
                "(цены, наличие, брони, «нужен человек») уроки не отменяют.")


def lessons_block(rows):
    """[(номер, было, стало, причина)] → текст блока или '' (уроков нет). Новые важнее: не помещается
    в LESSONS_MAX — уходят старшие номера, словами."""
    def cut(s):
        s = " ".join(str(s or "").split())
        return s if len(s) <= LESSON_ITEM_MAX else s[:LESSON_ITEM_MAX] + "…"
    items = ["№%d: было «%s» → стало «%s»%s" % (n, cut(was), cut(now), "; причина: %s" % cut(why) if why else "")
             for n, was, now, why in rows]
    keep, size = [], len(LESSONS_HEAD)
    for it in reversed(items):
        if size + len(it) + 1 > LESSONS_MAX:
            break
        keep.insert(0, it)
        size += len(it) + 1
    if not keep:
        return ""
    drop = len(items) - len(keep)
    return "\n".join([LESSONS_HEAD] + (["(старших уроков не поместилось: %d)" % drop] if drop else []) + keep)

SYSTEM_PROMPT = """Ты — менеджер проката мотобайков TurboBaby на Пхукете и пишешь ЧЕРНОВИК ответа клиенту в WhatsApp. Черновик читает сотрудник и сам решает, отправлять ли его.

Как отвечать:
1. Отвечай на то, что клиент спрашивает СЕЙЧАС (блок «КЛИЕНТ СЕЙЧАС»). Вся история — чтобы понимать контекст: кто он, что уже обсуждали, что ему уже ответили. Историю НЕ пересказывай и не повторяй то, что клиенту уже сказали.
2. Коротко: обычно 1–3 предложения, как живой менеджер в мессенджере. Без канцелярита, без списков, если о них не просили.
3. Пиши на языке клиента: русский или английский. Если клиент пишет на другом языке — ответь по-английски коротко и поставь в handoff причину «язык не русский и не английский».
4. Цены, наличие и брони НЕ выдумывай. Цену называй ТОЛЬКО из блока «ЦЕНА» и только так, как он разрешает; блока нет или он говорит «считает человек»/«неизвестна» — чисел цены не называй вовсе (ни точного, ни «от», ни диапазона), скажи, что коллега уточнит и вернётся с точной суммой. Наличие и брони ты не видишь — не обещай «есть» и «забронировано».
5. Факты о компании (доставка, депозит, документы, правила) — только из узлов знаний ниже. Узел НЕИЗВЕСТНО или нужного там нет — «уточню у коллег», а не по памяти.
6. От имени людей не обещай: никаких «коллега позвонит в 15:00», «мы вернём депозит», «сделаем скидку». Можно: «передам коллеге, он ответит».
7. Если вопрос требует решения человека (наличие и брони, скидка, срок через границу сезонов, срок от месяца, повреждения, штрафы, депозит, споры, оплаты, жалоба, иной язык, что-то, чего нет в знаниях и что нельзя сказать уклончиво) — всё равно напиши вежливый короткий черновик, но перечисли причины в handoff. Причины из блока «НУЖЕН ЧЕЛОВЕК» перенеси в handoff обязательно.
8. На «спасибо», «ок» и подобное — короткий вежливый ответ без новых вопросов и предложений.
9. Метки «[скрыто: …]» — это скрытые данные клиента; не проси их повторить и не упоминай.
10. Число суток аренды называй ТОЛЬКО из блоков «СРОКИ» и «ЦЕНА» — там его посчитал код: дата возврата минус дата выдачи («с 5 по 7» — двое суток, не трое). Блоков нет — числа суток не называй. Клиент назвал другое число суток на те же даты — мягко поправь числом из «СРОКИ».
11. В ответе о цене скидку за срок называй ВСЕГДА — числом из блока «ЦЕНА», и когда она 0% («скидка за срок 0%»). В блоке «скидка за срок неизвестна» — скажи, что скидку за срок уточнит коллега, числа скидки не называй. Блок «ЦЕНА» с несколькими вариантами — назови цену каждого варианта (модель и срок), не выбирай за клиента. Другой скидки сверх этой не обещай (правило 6).
12. НАШИ ПРЕЖНИЕ СЛОВА ОБЯЗЫВАЮТ. Строки «мы» в истории — уже сказанное клиенту компанией: с телефона, из темы или через «Отправить». Наше последнее предложение, условие, срок или цена о том же действуют, пока мы сами их не изменили: продолжай их, не спорь с ними и не подменяй прежними нашими словами, знаниями или своим расчётом. Два наших сообщения о том же расходятся — действует более позднее. Наше слово расходится со знаниями — клиенту не противоречь, а перенеси расхождение в handoff: «наше сообщение ЧЧ:ММ расходится с правилом …». Число, которое мы уже назвали, повторяй только к той же модели и тому же сроку; нового числа из него не выводи.

Ответ — РОВНО один JSON-объект без пояснений и без ``` вокруг:
{"text": "текст ответа клиенту", "lang": "ru" или "en" (язык клиента; иной — его код), "handoff": ["причина словами", …] или [], "why": "одна строка для сотрудника: что спросил клиент и почему такой ответ"}"""

# Брони на чтение (WABOOKTOOLS0210): при включённом снимке правила 4 и 7 говорят о блоках «НАЛИЧИЕ» и «АРЕНДА
# КЛИЕНТА»; без снимка — SYSTEM_PROMPT байт-в-байт прежний. Замена — строго по одному вхождению.
_RULE4_OLD = "Наличие и брони ты не видишь — не обещай «есть» и «забронировано»."
_RULE4_BOOK = ("Наличие байка на даты называй ТОЛЬКО из блока «НАЛИЧИЕ» и только так, как он разрешает; блока нет "
               "или там НЕИЗВЕСТНО — наличие ты не видишь: не обещай «есть» и «свободен». Конец аренды клиента — "
               "ТОЛЬКО из блока «АРЕНДА КЛИЕНТА»; блока нет или там НЕИЗВЕСТНО — не говори «у вас нет аренды», скажи, "
               "что уточнишь у менеджера. Бронь ты не делаешь: «забронировано» не обещай — её оформляет человек.")
_RULE7_OLD = "(наличие и брони, скидка,"
_RULE7_BOOK = "(бронь, наличие без факта в блоке «НАЛИЧИЕ», конец аренды без факта, скидка,"
if SYSTEM_PROMPT.count(_RULE4_OLD) != 1 or SYSTEM_PROMPT.count(_RULE7_OLD) != 1:
    raise RuntimeError("SYSTEM_PROMPT: правила 4/7 для броней не найдены ровно по одному разу")
SYSTEM_PROMPT_BOOK = SYSTEM_PROMPT.replace(_RULE4_OLD, _RULE4_BOOK).replace(_RULE7_OLD, _RULE7_BOOK)

# ── вопрос клиента и перевод для сотрудника на карточке (WACARDQ0410) ───────────────────
# Вопрос на карточке — ровно то, что ушло в модель последним блоком (хвост реплик клиента после нашей последней,
# под той же маской), а не пересказ модели. Язык вопроса судит КОД (`K.lang_of`), поле lang модели — нет. Не русский —
# в сообщение (не в инструкцию: префикс кэша прежний) идёт блок с просьбой двух переводов тем же вызовом; русский или
# букв нет — блока нет, промпт байт-в-байт прежний. Переводы видит только сотрудник: клиенту уходит одно поле text.
TR_Q_MAX = 800                                # перевод вопроса — не длиннее, знаков (просьба модели и обрезка кода)
TR_A_MAX = 3000                               # перевод ответа — не длиннее, знаков (обрезка кода)
TR_BLOCK = ("ПЕРЕВОД ДЛЯ СОТРУДНИКА (код определил: клиент пишет не по-русски). В тот же JSON добавь ещё два поля: "
            "\"q_ru\" — перевод на русский того, о чём клиент спрашивает в последнем блоке (не длиннее %d знаков; "
            "длинное сократи, сохранив смысл), и \"text_ru\" — перевод на русский твоего ответа из поля \"text\". "
            "Переводы видит только сотрудник; клиенту уходит одно поле \"text\" на языке клиента." % TR_Q_MAX)
_LABEL = re.compile(r"\[[^\[\]\n]{1,40}\]")   # метки маски «[скрыто: …]» и медиа «[фото]» — не слова клиента


def question_lang(question):
    """Язык вопроса клиента — кодом: `K.lang_of` по словам клиента без наших меток. → 'ru' | 'en' | 'other' | None."""
    return K.lang_of(_LABEL.sub(" ", str(question or "")))


def need_translation(lang):
    """Перевод нужен, если язык вопроса не русский; букв нет (None) — переводить нечего."""
    return lang not in ("ru", None)


# ── даты и модель в словах клиента ─────────────────────────────────────────────────────

_PRICE_ASK = re.compile(
    r"(?i)цен|стоим|стоит|сколько|почём|почем|прайс|тариф|price|cost|how\s+much|rate|quote")
_MONTHS = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "авг": 8,
    "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}
_MON = r"(янв\w*|фев\w*|мар\w*|апр\w*|ма[яй]|июн\w*|июл\w*|авг\w*|сен\w*|окт\w*|ноя\w*|дек\w*|" \
       r"jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
_RX_NUM = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)|(?<![\d.])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?![\d])")
_RX_RANGE_WORD = re.compile(r"(?i)(?<!\d)(\d{1,2})\s*(?:-|–|—|по|до|to|till|until)\s*(\d{1,2})\s+" + _MON)
_RX_DAY_MON = re.compile(r"(?i)(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON)
_RX_MON_DAY = re.compile(r"(?i)" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?!\d)")


def _mon(word):
    return _MONTHS.get(str(word or "").lower()[:3])


def _mk(today, d, m, y=None):
    """День и месяц (год — если назван) → date; без года — ближайшая будущая (сегодня включительно)."""
    try:
        if y is not None:
            y = int(y)
            y = y + 2000 if y < 100 else y
            return datetime.date(y, int(m), int(d))
        cand = datetime.date(today.year, int(m), int(d))
        return cand if cand >= today else datetime.date(today.year + 1, int(m), int(d))
    except (ValueError, TypeError):
        return None


def find_dates(text, today):
    """Даты в словах клиента по порядку появления → [date, …] (без повторов подряд)."""
    s = str(text or "")
    hits = []
    for m in _RX_RANGE_WORD.finditer(s):
        mo = _mon(m.group(3))
        for pos, day in ((m.start(1), m.group(1)), (m.start(2), m.group(2))):
            d = _mk(today, day, mo)
            if d:
                hits.append((pos, d))
    taken = [(m.start(), m.end()) for m in _RX_RANGE_WORD.finditer(s)]

    def free(a):
        return not any(x <= a < y for x, y in taken)

    for m in _RX_DAY_MON.finditer(s):
        if free(m.start()):
            d = _mk(today, m.group(1), _mon(m.group(2)))
            if d:
                hits.append((m.start(), d))
    for m in _RX_MON_DAY.finditer(s):
        if free(m.start()):
            d = _mk(today, m.group(2), _mon(m.group(1)))
            if d:
                hits.append((m.start(), d))
    for m in _RX_NUM.finditer(s):
        if m.group(1):
            d = _mk(today, m.group(3), m.group(2), m.group(1))
        else:
            d = _mk(today, m.group(4), m.group(5), m.group(6))
        if d:
            hits.append((m.start(), d))
    hits.sort(key=lambda h: h[0])
    out = []
    for _, d in hits:
        if not out or out[-1] != d:
            out.append(d)
    return out


# ── сутки по датам (WADAYS0410) ────────────────────────────────────────────────────────
# «С 5 по 7» — двое суток: дата возврата минус дата выдачи, как у двери цены (`K.quote`, QuotePrice.js). Код считает
# сутки каждому диапазону дат клиента (блок «СРОКИ») и сверяет число суток у диапазона в черновике модели.

TERMS_MAX = 6                                  # диапазонов в блоке «СРОКИ»: новые важнее
TERM_MAX_DAYS = 400                            # длиннее — не срок аренды, а неразобранная пара чисел
TERMS_HEAD = "СРОКИ (сутки посчитал код: дата возврата минус дата выдачи; «с 5 по 7» — двое суток): "
_SEP = r"\s*(?:-|–|—|по|до|to|till|until)\s*"
_ORD = r"(?:st|nd|rd|th)?"
_NOT_TIME = r"(?![.:/]\d)(?!\s*(?:час|ч\b|утр|вечер|ноч|мин|am\b|pm\b|h\b|o'?clock))"
_RANGES = (                                    # (вид, выражение); место, занятое первым, следующие не трогают
    ("iso", re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})" + _SEP + r"(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")),
    ("num", re.compile(r"(?<![\d.])(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?" + _SEP
                       + r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)")),
    ("dm_dm", re.compile(r"(?i)(?<!\d)(\d{1,2})" + _ORD + r"\s+(?:of\s+)?" + _MON + _SEP + r"(\d{1,2})" + _ORD
                         + r"\s+(?:of\s+)?" + _MON)),
    ("md_md", re.compile(r"(?i)\b" + _MON + r"\s+(\d{1,2})" + _ORD + _SEP + _MON + r"\s+(\d{1,2})" + _ORD
                         + r"(?!\d)")),
    ("d_dm", _RX_RANGE_WORD),
    ("dm_d", re.compile(r"(?i)(?<!\d)(\d{1,2})" + _ORD + r"\s+(?:of\s+)?" + _MON + _SEP + r"(\d{1,2})" + _ORD
                        + r"(?!\d)" + _NOT_TIME)),
    ("md_d", re.compile(r"(?i)\b" + _MON + r"\s+(\d{1,2})" + _ORD + _SEP + r"(\d{1,2})" + _ORD + r"(?!\d)"
                        + _NOT_TIME)),
    ("bare", re.compile(r"(?i)(?<!\w)с\s+(\d{1,2})\s+по\s+(\d{1,2})(?!\d)" + _NOT_TIME)),
)


def term_days(ds, de):
    """Сутки аренды: дата возврата минус дата выдачи («с 5 по 7» — двое), как `K.quote` и дверь цены."""
    return (de - ds).days


def _span(today, d1, m1, y1, d2, m2, y2):
    """Пара дат диапазона → (выдача, возврат) | None. Год не назван — возврат ближайший будущий (как `_mk`), выдача —
    последняя такая дата не позже возврата: «с 30 сентября по 2 октября» — двое суток при любом «сегодня»."""
    def yr(y):
        y = int(y)
        return y + 2000 if y < 100 else y
    try:
        if y2 is not None:
            de = datetime.date(yr(y2), int(m2), int(d2))
        elif y1 is not None:
            de = datetime.date(yr(y1), int(m2), int(d2))
        else:
            de = _mk(today, d2, m2)
        if de is None:
            return None
        if y1 is not None:
            ds = datetime.date(yr(y1), int(m1), int(d1))
            if y2 is None and de < ds:
                de = datetime.date(de.year + 1, int(m2), int(d2))
        else:
            ds = datetime.date(de.year, int(m1), int(d1))
            if ds > de:
                ds = datetime.date(de.year - 1, int(m1), int(d1))
    except (ValueError, TypeError, AttributeError):      # не дата · «сегодня» не задано — не диапазон
        return None
    return (ds, de) if ds < de else None


def _range_of(kind, g, today):
    """Совпадение выражения диапазона → {ds, de, days, label} | None (не диапазон)."""
    if kind == "bare":                         # «с 5 по 7» без месяца: дат нет, сутки — разность чисел одного месяца
        d1, d2 = int(g[0]), int(g[1])
        if not 1 <= d1 < d2 <= 31:
            return None
        return {"ds": None, "de": None, "days": term_days(datetime.date(2001, 1, d1), datetime.date(2001, 1, d2)),
                "label": "с %d по %d (месяц не назван)" % (d1, d2)}
    y1 = y2 = None
    if kind == "iso":
        y1, m1, d1, y2, m2, d2 = g
    elif kind == "num":
        d1, m1, y1, d2, m2, y2 = g
    elif kind == "dm_dm":
        d1, w1, d2, w2 = g
        m1, m2 = _mon(w1), _mon(w2)
    elif kind == "md_md":
        w1, d1, w2, d2 = g
        m1, m2 = _mon(w1), _mon(w2)
    elif kind == "d_dm":
        d1, d2, w = g
        m1 = m2 = _mon(w)
    elif kind == "dm_d":
        d1, w, d2 = g
        m1 = m2 = _mon(w)
    else:                                      # md_d
        w, d1, d2 = g
        m1 = m2 = _mon(w)
    if m1 is None or m2 is None:
        return None
    span = _span(today, d1, m1, y1, d2, m2, y2)
    if span is None:
        return None
    days = term_days(*span)
    if days > TERM_MAX_DAYS:
        return None
    return {"ds": span[0], "de": span[1], "days": days,
            "label": "с %s по %s" % (span[0].strftime("%d.%m"), span[1].strftime("%d.%m"))}


def find_ranges(text, today):
    """Диапазоны дат в тексте по порядку появления → [{a, b, ds, de, days, label}]. Сутки — `term_days`."""
    s = str(text or "")
    taken, out = [], []
    for kind, rx in _RANGES:
        for m in rx.finditer(s):
            a, b = m.span()
            if any(x < b and a < y for x, y in taken):
                continue
            got = _range_of(kind, m.groups(), today)
            if got is not None:
                taken.append((a, b))
                out.append(dict(got, a=a, b=b))
    return sorted(out, key=lambda r: r["a"])


def client_terms(items, today):
    """История → диапазоны дат из слов КЛИЕНТА, без повторов, не больше TERMS_MAX (новые важнее)."""
    seen, out = set(), []
    for it in items or ():
        if it.get("who") != "клиент" or not it.get("text"):
            continue
        for r in find_ranges(it["text"], today):
            key = (r["label"], r["days"])
            if key not in seen:
                seen.add(key)
                out.append(r)
    return out[-TERMS_MAX:]


def terms_line(ranges):
    """Диапазоны → блок «СРОКИ» | '' (дат нет — блока нет)."""
    if not ranges:
        return ""
    return TERMS_HEAD + "; ".join("%s — %d сут." % (r["label"], r["days"]) for r in ranges)


_CNT_WORDS = {
    "один": 1, "одни": 1, "одних": 1, "одна": 1, "два": 2, "две": 2, "двух": 2, "двое": 2, "три": 3, "трое": 3,
    "трёх": 3, "трех": 3, "четыре": 4, "четверо": 4, "четырёх": 4, "четырех": 4, "пять": 5, "пятеро": 5, "пяти": 5,
    "шесть": 6, "шестеро": 6, "шести": 6, "семь": 7, "семеро": 7, "семи": 7, "восемь": 8, "восьми": 8,
    "девять": 9, "девяти": 9, "десять": 10, "десяти": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_RX_COUNT = re.compile(
    r"(?i)(?<![\w.,])(\d{1,3}|" + "|".join(sorted(_CNT_WORDS, key=len, reverse=True)) + r")"
    r"(?:-?(?:х|ти|ми|ух|ёх|ех))?(?:\s+|\s*-\s*)"
    r"(?:сут(?:ки|ок|ка|кам|ках)|дн(?:я|ей|ям)|день|ноч(?:ь|и|ей)|days?|nights?)\b")
# число суток — не срок аренды: «через 2 дня», «от 3 суток», «минимальный срок 3 дня», «за 1 день до выдачи»
_CNT_SKIP_BEFORE = re.compile(
    r"(?i)(?<!\w)(?:через|спустя|в\s+течение|кажд\w+|минимум|минимальн\w*(?:\s+\w+){0,2}|не\s+(?:менее|меньше|более|больше)|"
    r"более|больше|менее|меньше|от|до|within|in|after|every|at\s+least|minimum|min|from|up\s+to|more\s+than|"
    r"less\s+than)\s*$")
_CNT_SKIP_AFTER = re.compile(r"(?i)\s+(?:до|before|назад|ago|после|after)\b")


def day_counts(text):
    """Текст → [(начало, конец, число суток)] по порядку: «3 суток», «двое суток», «3-х дней», «2 nights», «2-day»."""
    s = str(text or "")
    out = []
    for m in _RX_COUNT.finditer(s):
        w = m.group(1).lower()
        n = int(w) if w.isdigit() else _CNT_WORDS.get(w)
        if n is None or _CNT_SKIP_BEFORE.search(s[max(0, m.start() - 40):m.start()]) \
                or _CNT_SKIP_AFTER.match(s, m.end()):
            continue
        out.append((m.start(), m.end(), n))
    return out


_RX_LEADS = re.compile(r"(?i)\s*(?:\(|с|from|на|for|:)?\s*")


def _owner_of(ranges, a, b, sent):
    """Чей это срок: число сразу вводит диапазон («на 3 дня с 5 по 7», «3 суток (с 5 по 7)») — его; иначе —
    ближайший диапазон ПЕРЕД числом («5–7 октября — 3 суток, 5–8 — …»); перед числом нет — первый после."""
    after = [r for r in ranges if r["a"] >= b]
    if after and _RX_LEADS.fullmatch(sent[b:after[0]["a"]]):
        return after[0]
    before = [r for r in ranges if r["b"] <= a]
    if before:
        return before[-1]
    return after[0] if after else ranges[0]


def days_claims(text, today, known=(), price=None):
    """Текст черновика → [(что, названо, по датам)] — число суток без опоры на даты:
    (а) у диапазона дат в одном предложении названо число суток, и ни одно из них не равно разности дат;
    (б) число суток без диапазона рядом, когда сутки известны (блок «СРОКИ», «ЦЕНА», диапазоны самого черновика),
        и ни одно число суток черновика не совпало ни с одним известным. Пусто — сверять нечего или всё верно.
    Поправка клиента («вы написали 3 дня, но с 5 по 7 — двое суток») причиной не становится: верное число названо."""
    s = str(text or "")
    out, free, every, ref = [], [], [], set(known or ())
    for q in K.quotes_of(price):                          # каждый вариант цены (WAPRICECTX0410)
        if isinstance(q.get("days"), int):
            ref.add(q["days"])
    for sent in K._SENTENCE.split(s):
        ranges, counts = find_ranges(sent, today), day_counts(sent)
        ref.update(r["days"] for r in ranges)
        every += [n for _a, _b, n in counts]
        if not ranges:
            free += [n for _a, _b, n in counts]
            continue
        near = {}
        for a, b, n in counts:                 # число — диапазону своего предложения (`_owner_of`)
            r = _owner_of(ranges, a, b, sent)
            near.setdefault(r["a"], (r, []))[1].append(n)
        for r, ns in near.values():
            if r["days"] not in ns:
                out += [(r["label"], n, r["days"]) for n in ns]
    if ref and free and not any(n in ref for n in every):
        out += [("сутки без дат рядом", n, "/".join(str(x) for x in sorted(ref))) for n in free if n not in ref]
    return out


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _nocc(s):
    return re.sub("cc", "", _alnum(s))


def model_of_name(name):
    """Имя юнита парка «PCX 160 1234» → модель «PCX 160»: последний номер (номерной знак, 4 цифры —
    кубатура трёхзначна и остаётся) снят."""
    toks = str(name or "").split()
    if len(toks) > 1 and re.fullmatch(r"\d{4}", toks[-1]):
        toks.pop()
    return " ".join(toks).strip()


def fleet_bikes(reply):
    """Ответ моста `fleet` → список байков | None (не прочитан)."""
    if not isinstance(reply, dict) or not reply.get("ok"):
        return None
    src = reply.get("data") if isinstance(reply.get("data"), dict) else reply
    bikes = src.get("bikes") if isinstance(src, dict) else None
    return bikes if isinstance(bikes, list) else None


# Модель в словах клиента — `wa_book_read.find_model` (ключ живых имён парка) и для цены, и для наличия
# (WADRAFTFIX0210). Прежний поиск брал имя юнита без номерного знака: на живых именах вида
# «XMAX 300CC NEW BLUE PHUKET 1234» это цвет и город, и модель не находилась никогда (замер 02.10: 0 из 13).


def units_of(model, bikes):
    """Модель → имена юнитов (как `pricing._candidates`: строго, затем без «CC»)."""
    m = _alnum(model)
    if not m:
        return []
    strict = [b.get("name") for b in bikes if m in _alnum(b.get("name"))]
    if strict:
        return strict
    mk = _nocc(model)
    return [b.get("name") for b in bikes if mk and mk in _nocc(b.get("name"))]


# ── вопрос о цене без модели или дат — варианты из переписки (WAPRICECTX0410) ───────────────
# Повод — владелец 05.10, черновик №11: «сколько будет стоить?» относилось и к ADV 350 на 5 дней из НАШЕГО ответа, а
# цена бралась только из слов клиента «сейчас». Вопрос о цене без модели или без двух дат дополняется последними
# сообщениями диалога (наши и клиента, новые первыми): пары «модель + срок», без повторов, не больше PAIRS_MAX, каждая —
# свой `K.quote` с прежними воротами (срок до месяца, один сезон, модель с ценой и в парке). Срок числом суток
# («на 5 дней») — от начала, названного в переписке (самая новая дата); начала нет — числа нет, агент спрашивает даты.

CTX_MSGS = 6                                   # сообщений диалога до вопроса, где ищутся модель и срок
PAIRS_MAX = 3                                  # вариантов «модель + срок» на вопрос; дверь цены — не чаще
NO_START_LINE = ("%s на %d сут.: цена НЕИЗВЕСТНА — дата начала аренды в переписке не названа. Числа цены не "
                 "называть; спроси у клиента даты (с какого по какое число).")


def _norm_map(text):
    """Текст → (строка как у `B._nocc`: строчные латиница и цифры без «cc»; [место каждого её знака в тексте])."""
    keep = [(c, i) for i, c in enumerate(str(text or "").lower()) if "a" <= c <= "z" or "0" <= c <= "9"]
    out, i = [], 0
    while i < len(keep):                       # «cc» снимается слева направо без перекрытий — как re.sub("cc", "")
        if keep[i][0] == "c" and i + 1 < len(keep) and keep[i + 1][0] == "c":
            i += 2
            continue
        out.append(keep[i])
        i += 1
    return "".join(c for c, _ in out), [p for _, p in out]


def find_models(text, bikes):
    """Модели из парка в тексте → [(место в тексте, модель)] по порядку, каждая один раз. Ключ — как у
    `B.find_model` (живые имена парка без «CC»); совпадение внутри более длинного ключа — не своё."""
    t, pos = _norm_map(text)
    keys = {}
    for b in bikes or ():
        m = B.model_key((b or {}).get("name"))
        k = B._nocc(m)
        if len(k) >= 3:
            keys.setdefault(k, m)
    hits = []
    for k, m in keys.items():
        at = t.find(k)
        while at >= 0:
            hits.append((at, at + len(k), m))
            at = t.find(k, at + 1)
    hits = [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and o[1] - o[0] > h[1] - h[0] for o in hits)]
    out, seen = [], set()
    for a, _b, m in sorted(hits):
        if m not in seen:
            seen.add(m)
            out.append((pos[a], m))
    return out


def _terms(text, today):
    """Сроки сообщения → [{a, ds, de, days}]: диапазоны дат; их нет — числа суток («на 5 дней») без дат. Диапазон без
    месяца («с 5 по 7») — срока нет: ни дат, ни уверенности в числе."""
    rs = find_ranges(text, today)
    full = [r for r in rs if r["ds"] is not None]
    if full:
        return [{"a": r["a"], "ds": r["ds"], "de": r["de"], "days": r["days"]} for r in full]
    if rs:
        return []
    return [{"a": a, "ds": None, "de": None, "days": n} for a, _b, n in day_counts(text) if 0 < n <= TERM_MAX_DAYS]


def context_start(msgs, today):
    """Начало срока из переписки (сообщения новые первыми): самый новый диапазон дат — его начало; диапазонов нет —
    первая дата самого нового сообщения с датой; дат нет — None."""
    for text in msgs:
        full = [r for r in find_ranges(text, today) if r["ds"] is not None]
        if full:
            return full[0]["ds"]
    for text in msgs:
        dates = find_dates(text, today)
        if dates:
            return dates[0]
    return None


def _pair_up(models, terms):
    """Модели и сроки одного сообщения → [(модель, срок)]: одна модель — со всеми сроками, один срок — со всеми
    моделями; иначе каждой модели — ближайший срок по месту в тексте (поровну — тот, что после модели)."""
    if not models or not terms:
        return []
    if len(models) == 1:
        return [(models[0][1], t) for t in terms]
    if len(terms) == 1:
        return [(m, terms[0]) for _p, m in models]
    return [(m, min(terms, key=lambda t: (abs(t["a"] - p), t["a"] < p))) for p, m in models]


def price_pairs(ask, ctx, today, bikes):
    """Вопрос о цене + сообщения диалога до него (новые первыми) → ([(модель, {ds, de, days})], отброшено сверх
    PAIRS_MAX). Модели и сроки вопроса — первыми, недостающее — из самого нового сообщения, где оно есть; в вопросе нет
    ни модели, ни срока — пары каждого сообщения (недостающее так же). Срок числом суток — от `context_start`; начала нет —
    ds и de None (цены нет, агент спрашивает даты)."""
    msgs = [str(ask or "")] + [str(c or "") for c in list(ctx or ())[:CTX_MSGS]]
    parsed = [(find_models(t, bikes), _terms(t, today)) for t in msgs]
    a_models, a_terms = parsed[0]
    dates = find_dates(msgs[0], today)
    if not a_terms and len(dates) >= 2 and dates[1] > dates[0]:      # две даты вопроса — срок, как раньше
        a_terms = [{"a": 0, "ds": dates[0], "de": dates[1], "days": term_days(dates[0], dates[1])}]
    fill_m = next((ms for ms, _ts in parsed if ms), [])
    fill_t = a_terms or next((ts for _ms, ts in parsed if ts), [])
    if a_models or a_terms:
        raw = _pair_up(a_models or fill_m, fill_t)
    else:
        raw = []
        for ms, ts in parsed[1:]:
            if ms or ts:
                raw += _pair_up(ms or fill_m, ts or fill_t)
    start = context_start(msgs, today)
    pairs, seen = [], set()
    for m, t in raw:
        if t["ds"] is None and start is not None:
            t = dict(t, ds=start, de=start + datetime.timedelta(days=t["days"]))
        key = (m, t["ds"], t["de"], t["days"])
        if key not in seen:
            seen.add(key)
            pairs.append((m, t))
    return pairs[:PAIRS_MAX], max(0, len(pairs) - PAIRS_MAX)


# ── ответ модели ───────────────────────────────────────────────────────────────────────

def parse_reply(raw):
    """Ответ модели → {text, lang, handoff[], why} | None (не JSON или нет текста — черновика нет)."""
    s = str(raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        data = json.loads(s)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    hand = data.get("handoff")
    hand = [str(h).strip() for h in hand if str(h).strip()] if isinstance(hand, list) else []

    out = {"text": text.strip(), "lang": str(data.get("lang") or "").strip().lower()[:8],
           "handoff": hand[:8], "why": str(data.get("why") or "").strip()[:300]}
    for key, cap in (("q_ru", TR_Q_MAX), ("text_ru", TR_A_MAX)):   # перевод для сотрудника (WACARDQ0410) — если дан
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            out[key] = v.strip()[:cap]
    return out


def card_fields(info, got):
    """Поля карточки сотрудника (WACARDQ0410): вопрос — из блока последних реплик клиента, что ушёл в модель (под
    маской); язык — кодом; переводы — только при не русском вопросе. Клиенту из этого не уходит ничего.
    Вопроса в сведениях нет (сборка без него) — полей нет: карточка прежняя."""
    question = info.get("question")
    if question is None:
        return {}
    lang = info.get("q_lang")
    keep = need_translation(lang)
    return {"question": question, "q_lang": lang or "",
            "q_ru": got.get("q_ru", "") if keep else "", "text_ru": got.get("text_ru", "") if keep else ""}


# ── кэш промпта и цена по usage (WAAGENTCACHE0210) ─────────────────────────────────────

CACHE_TTLS = ("5m", "1h")
# Множители к цене входа модели — документация Anthropic «Prompt caching», раздел цен:
# https://platform.claude.com/docs/en/build-with-claude/prompt-caching
CACHE_WRITE_X = {"5m": 1.25, "1h": 2.0}
CACHE_READ_X = 0.1
KNOW_HEAD = ("ЗНАНИЯ КОМПАНИИ — снимки узлов мозга (на них ссылается правило 5; возраст снимков — в сообщении, "
             "блок «ВОЗРАСТ ЗНАНИЙ»):")


def cache_ttl_of(value):
    """Настройка WA_AGENT_CACHE → срок кэша | None (выключен). «5m»/«1h» — срок; 1/true/yes/on — «1h»
    (выбор WAAGENTCACHE0210 §2: черновики реже раза в 5 минут); пусто и всё прочее — выключен."""
    v = str(value or "").strip().lower()
    if v in CACHE_TTLS:
        return v
    if v in ("1", "true", "yes", "on"):
        return "1h"
    return None


def usage_of(u):
    """usage ответа API → {in, cw, cw5, cw1h, cr, out} — целые; поля нет — 0. `in` — вход ПОСЛЕ кэша
    (так его считает API), `cw` — запись в кэш, `cw5`/`cw1h` — она же по срокам, `cr` — чтение из кэша."""
    def g(o, k):                                       # поля SDK — int | None; None и «нет поля» — 0
        return max(0, int(getattr(o, k, 0) or 0)) if o is not None else 0
    cc = getattr(u, "cache_creation", None)
    return {"in": g(u, "input_tokens"), "cw": g(u, "cache_creation_input_tokens"),
            "cw5": g(cc, "ephemeral_5m_input_tokens"), "cw1h": g(cc, "ephemeral_1h_input_tokens"),
            "cr": g(u, "cache_read_input_tokens"), "out": g(u, "output_tokens")}


def cost_of(model, use):
    """Цена вызова по usage → {usd, usd_nocache, eq_in}. eq_in — вход в токенах по цене входа:
    in + запись 5 мин × 1.25 + запись 1 ч × 2 + чтение × 0.1; запись без разбивки по сроку — по ДОРОГОМУ
    (2×, учёт не занижает). usd_nocache — тот же вход целиком по цене входа (как без кэша). Цены модели —
    `spend_ledger.cost_usd` (одна таблица с Splinter)."""
    import spend_ledger
    u = {k: int((use or {}).get(k) or 0) for k in ("in", "cw", "cw5", "cw1h", "cr", "out")}
    rest = max(0, u["cw"] - u["cw5"] - u["cw1h"])
    eq_in = (u["in"] + u["cw5"] * CACHE_WRITE_X["5m"] + (u["cw1h"] + rest) * CACHE_WRITE_X["1h"]
             + u["cr"] * CACHE_READ_X)
    per_in = spend_ledger.cost_usd(model, 1_000_000, 0) / 1_000_000.0          # $ за токен входа
    return {"usd": per_in * eq_in + spend_ledger.cost_usd(model, 0, u["out"]),
            "usd_nocache": spend_ledger.cost_usd(model, u["in"] + u["cw"] + u["cr"], u["out"]),
            "eq_in": eq_in}


def cost_words(use, cost):
    """Строка журнала о цене вызова: только числа."""
    return ("цена: вход %d · запись в кэш %d (5 мин %d, 1 ч %d) · чтение из кэша %d · выход %d → $%.4f "
            "(без кэша $%.4f)" % (use["in"], use["cw"], use["cw5"], use["cw1h"], use["cr"], use["out"],
                                  cost["usd"], cost["usd_nocache"]))


def _by_name(nodes):
    return sorted(nodes or (), key=lambda n: str(n.get("name")))            # как sorted(parts): business_rules, faq


def node_stable(node, now=None):
    """Узел → текст для префикса кэша: без возраста и без причины непрочтения (они меняются каждый вызов
    и живут в блоке «ВОЗРАСТ ЗНАНИЙ»). Меняется только со сменой узла. Не прочитан — НЕИЗВЕСТНО словами."""
    if K.node_age(node, now) is None:
        return ("УЗЕЛ %s: НЕИЗВЕСТНО — не прочитан (причина — в блоке «ВОЗРАСТ ЗНАНИЙ»). Не отвечай по памяти о "
                "том, что в нём; где нужен он — «уточню у коллег»." % node.get("name"))
    if K.node_stale(node, now):                       # старше предела — без текста (WAKNOWFRESH0310)
        return ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше %d мин (причина — в блоке «ВОЗРАСТ ЗНАНИЙ»). Не отвечай по "
                "памяти о том, что в нём; где нужен он — «уточню у коллег»." % (node["name"], node["max_stale"] // 60))
    return "УЗЕЛ %s (%d симв.):\n%s" % (node["name"], node["len"], node["text"])


def knowledge_stable(nodes, now=None):
    """Неизменная часть знаний — одним блоком: шапка и узлы по имени."""
    return "\n\n".join([KNOW_HEAD] + [node_stable(n, now) for n in _by_name(nodes)])


def ages_block(nodes, now=None):
    """Переменная часть знаний — возраст снимков и причина непрочтения, в сообщение (после префикса)."""
    out = []
    for n in _by_name(nodes):
        age = K.node_age(n, now)
        if K.node_stale(n, now):
            out.append("%s — НЕИЗВЕСТНО: снимок старше %d мин, %s" % (n["name"], n["max_stale"] // 60,
                                                                    n.get("why") or "не освежён"))
            continue
        out.append("%s — %s" % (n.get("name"), "снят %d мин назад" % int(age // 60) if age is not None else
                                "НЕИЗВЕСТНО: не прочитан (%s)" % (n.get("why") or "причина не названа")))
    return "ВОЗРАСТ ЗНАНИЙ: " + "; ".join(out)


def sha16(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


def knowledge_line(nodes, now=None):
    """Узлы этого вызова → строка журнала (WAKNOWFRESH0310): имя, прочитан ли сейчас, длина, sha16 и возраст
    снимка — без текста узла. Снимка нет или он старше предела — НЕИЗВЕСТНО словами."""
    out = []
    for n in _by_name(nodes):
        s = "%s — %s" % (n.get("name"), n.get("call") or "не читался")
        if n.get("call") == K.CALL_FAILED:
            s += " (%s)" % str(n.get("why") or "причина не названа")[:120]
        age = K.node_age(n, now)
        if age is None:
            out.append(s + ", снимка нет — НЕИЗВЕСТНО")
            continue
        s += ", снимок %d симв., sha16 %s, возраст %d с" % (n["len"], sha16(n["text"]), int(age))
        if K.node_stale(n, now):
            s += " > предела %d с — НЕИЗВЕСТНО, текста в промпте нет" % n["max_stale"]
        out.append(s)
    return "знания: " + "; ".join(out)


def system_chars(system):
    return len(system) if isinstance(system, str) else sum(len(b.get("text") or "") for b in system)


class _LedgerUsage:
    """usage для `spend_ledger.meter`: вход — в токенах по цене входа (eq_in), чтобы учёт трат Splinter
    видел запись и чтение кэша по их цене, а не только `input_tokens`. Без кэша eq_in = input_tokens."""

    def __init__(self, eq_in, out):
        self.input_tokens, self.output_tokens = int(round(eq_in)), int(out)


# ── платный вызов (как у Splinter) ─────────────────────────────────────────────────────

def paid_call(model_name=None, env_file=None):
    """→ call(system, user) → (текст, usage-словарь). Ключ — ANTHROPIC_API_KEY из .env дерева тем же
    путём, что у Splinter; учёт трат — `spend_ledger.meter`. Значение ключа нигде не печатается.
    system — строка (кэш выключен) или список блоков с `cache_control` (WAAGENTCACHE0210) — уходит как есть."""
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file or os.path.join(ROOT, ".env"))
    except Exception:                                                # noqa: BLE001
        pass
    from anthropic import Anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY нет — платного ключа нет")
    client = Anthropic(api_key=key)
    name = model_name or os.environ.get("WA_AGENT_MODEL") or os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL

    def call(system, user):
        resp = client.messages.create(model=name, max_tokens=MAX_TOKENS, system=system,
                                      messages=[{"role": "user", "content": user}])
        u = getattr(resp, "usage", None)
        use = usage_of(u)
        model = getattr(resp, "model", name) or name
        try:
            import spend_ledger
            spend_ledger.meter(name, _LedgerUsage(cost_of(model, use)["eq_in"], use["out"]) if u is not None
                               else None)
        except Exception:                                            # noqa: BLE001
            pass
        text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text, dict(use, model=model)
    return call


def door_budget(seconds):
    """Общий бюджет плеч моста на время сверки (AGENTDEDUP0410): двери кассы и договоров — методы `bridge_client`, и их
    лестницы повторов режутся тем же `card_budget`, что у карточки «Инфо». Модуля нет (ПК без fcntl) — без бюджета."""
    try:
        import bridge_client
        return bridge_client.card_budget(seconds, label="сверки агента")
    except Exception:                                                # noqa: BLE001
        import contextlib
        return contextlib.nullcontext()


# ── адаптер ────────────────────────────────────────────────────────────────────────────

class ModelAdapter(wa_agent.Model):
    """draft(number, upto_id) → {text, handoff[слова], lang, why} | None.

    call(system, user) → (текст, usage) — модель; read_doc(name) → ответ моста; fleet() → ответ моста
    `fleet`; door(unit, ds, de) → ответ двери цены. Все — снаружи (в тестах подделки)."""

    def __init__(self, queue_db, call, read_doc=None, fleet=None, door=None, archive_db="",
                 manifest="", media_dir="", no_price_models=(), clock=time.time, log=None, agent_db="",
                 lessons_db="", book=None, cache=None, tools=None, fresh=None):
        self.queue_db, self.call = queue_db, call
        # инструменты чтения (AGENTLOOPA0310, флаг WA_AGENT_TOOLS): None — выкл, черновик одним вызовом, как в 9c4aac6;
        # dict дверей моста (cash/contract/contract_pdf) — модель сама выбирает, что прочитать (`wa_agent_tools`)
        self.tools = tools
        self.fresh = fresh                                # fresh(number, upto_id) → новое входящее посреди сверки
        self.cache = cache if cache in CACHE_TTLS else None   # срок кэша промпта (WAAGENTCACHE0210); None — выкл
        self.spend = {"calls": 0, "in": 0, "cw": 0, "cr": 0, "out": 0, "usd": 0.0, "usd_nocache": 0.0}
        self.book = book                                  # снимок броней `wa_book_read.Snapshot`; None — выкл
        self.agent_db = agent_db                          # outbox: ушедшее через API (WARELAYTEXT0210)
        self.lessons_db = lessons_db                      # уроки людей (WAAGENTLESSON0210); пусто — выкл
        self.fleet, self.door = fleet, door
        self.archive_db, self.manifest, self.media_dir = archive_db, manifest, media_dir
        self.no_price_models = tuple(no_price_models)
        self.knowledge = K.Knowledge(read_doc)              # None — чтение не настроено (WADRAFTFIX0310)
        self.clock = clock
        self.log = log or (lambda line: None)
        self.last = None                                  # разбор последнего вызова (для проб и тестов)

    def _system(self, text, nodes, now):
        """Кэш выключен — строка инструкции, как раньше (узлы — в сообщении). Включён — префикс из двух
        блоков: инструкция и знания без возраста; отметка кэша — на последнем (кэшируется всё до неё)."""
        if not self.cache:
            return text
        return [{"type": "text", "text": text},
                {"type": "text", "text": knowledge_stable(nodes, now),
                 "cache_control": {"type": "ephemeral", "ttl": self.cache}}]

    def _knowledge_blocks(self, parts, nodes, now):
        """Блоки знаний для сообщения: кэш выключен — узлы с возрастом (как раньше); включён — только возраст."""
        if self.cache:
            return [ages_block(nodes, now)]
        return [parts[k] for k in sorted(parts) if k.startswith("node:")]

    def _spend(self, usage, what):
        """usage вызова → строка журнала о цене и итог в `self.spend` (сводка службы). → цена."""
        use = {k: int((usage or {}).get(k) or 0) for k in ("in", "cw", "cw5", "cw1h", "cr", "out")}
        cost = cost_of((usage or {}).get("model") or DEFAULT_MODEL, use)
        s = self.spend
        s["calls"] += 1
        for k in ("in", "cw", "cr", "out"):
            s[k] += use[k]
        s["usd"] += cost["usd"]
        s["usd_nocache"] += cost["usd_nocache"]
        self.log("%s %s" % (what, cost_words(use, cost)))
        return cost

    def _history(self, number, upto_id):
        items, missing = wa_history.read_history(number, self.queue_db, self.archive_db, self.manifest,
                                                 self.media_dir, trig=int(upto_id) + 1,
                                                 sent_db=self.agent_db or None)
        return items, missing

    @staticmethod
    def _tail(items):
        """То, что клиент спрашивает сейчас: его реплики после нашей последней. Автоприветствие
        (`auto`, WAGREETECHO0210) нашим ответом не считается — первый вопрос до него остаётся «сейчас»."""
        tail = []
        for it in reversed(items):
            if it.get("auto"):
                continue
            if it["who"] == "мы":
                break
            if it["who"] == "клиент":
                tail.append(it)
        return list(reversed(tail))

    def _lessons(self):
        """Действующие уроки из базы агента (mode=ro). Выключено — []; не прочитано — [] и строка журнала:
        без уроков агент пишет как раньше, а не выдумывает правила."""
        if not self.lessons_db:
            return []
        try:
            db = sqlite3.connect("file:%s?mode=ro" % self.lessons_db, uri=True, timeout=5)
            try:
                return wa_agent.active_lessons(db)
            finally:
                db.close()
        except Exception as e:                                       # noqa: BLE001
            self.log("уроки не прочитаны: %s — блока уроков нет" % type(e).__name__)
            return []

    def _price(self, ask, today, ctx=()):
        """Цена — только на вопрос о цене. Одна модель и обе даты в вопросе — одна дверь, как раньше; модели или дат
        нет (или моделей несколько) — варианты «модель + срок» из вопроса и переписки `ctx` (сообщения до вопроса, новые
        первыми; `price_pairs`, WAPRICECTX0410), каждый — свой `K.quote`. → (исход | None, слова)."""
        if not _PRICE_ASK.search(ask):
            return None, "о цене не спрашивают"
        dates = find_dates(ask, today)
        if len(dates) < 2 and not ctx:
            return None, "о цене спрашивают без дат — дверь не звана"
        if self.fleet is None or self.door is None:
            return None, "двери цены нет"
        try:
            bikes = fleet_bikes(self.fleet())
        except Exception as e:                                       # noqa: BLE001
            bikes = None
            self.log("парк не прочитан: %s" % type(e).__name__)
        if bikes is None:
            if len(dates) < 2:                                       # моделей переписки не найти — как без дат
                return None, "о цене спрашивают без дат, парк не прочитан — дверь не звана"
            return K.quote("?", dates[0], dates[1], self.door, lambda m: None), "парк не прочитан"
        if len(dates) >= 2 and len(find_models(ask, bikes)) <= 1:
            model = B.find_model(ask, bikes)                        # ключ модели — живые имена парка
            if model:
                res = K.quote(model, dates[0], dates[1], self.door, lambda m: units_of(m, bikes),
                              self.no_price_models)
                return res, "цена: %s" % res["outcome"]
        pairs, dropped = price_pairs(ask, ctx, today, bikes)
        if not pairs:
            return None, ("о цене спрашивают без модели из парка — дверь не звана" if len(dates) >= 2 else
                          "о цене спрашивают без дат — дверь не звана")
        got = [self._quote_pair(m, t, bikes) for m, t in pairs]
        n = {o: sum(1 for r in got if r["outcome"] == o) for o in (K.PRICE_NUMBER, K.PRICE_HUMAN, K.PRICE_UNKNOWN)}
        return K.price_set(got, dropped), "цена по переписке: вариантов %d (число %d, человек %d, неизвестно %d)%s" % (
            len(got), n[K.PRICE_NUMBER], n[K.PRICE_HUMAN], n[K.PRICE_UNKNOWN],
            ", сверх предела %d" % dropped if dropped else "")

    def _quote_pair(self, model, term, bikes):
        """Пара «модель + срок» → исход `K.quote` (прежние ворота). Начала срока нет — дверь не зовётся: цена
        неизвестна, агент спрашивает даты."""
        if term["ds"] is None:
            res = K.quote(model, None, None, self.door, lambda m: None)
            res.update(days=term["days"], why="дата начала не названа", line=NO_START_LINE % (model, term["days"]))
            return res
        return K.quote(model, term["ds"], term["de"], self.door, lambda m: units_of(m, bikes), self.no_price_models)

    @staticmethod
    def _context(items, tail):
        """Сообщения диалога ДО вопроса клиента (наши и клиента, без автоприветствия) под маской, новые первыми, не
        больше CTX_MSGS: в них ищутся модель и срок вопроса о цене (WAPRICECTX0410)."""
        skip, out = {id(it) for it in tail}, []
        for it in reversed(items):
            if it.get("auto") or id(it) in skip or not it.get("text"):
                continue
            out.append(K.mask(it["text"])[0])
            if len(out) >= CTX_MSGS:
                break
        return out

    def _book(self, number, ask, today, now):
        """Брони на чтение (WABOOKTOOLS0210) — кодом ДО модели и только на явный вопрос: о свободном байке
        (слово наличия и обе даты) или о конце аренды. → (наличие | None, аренда | None, слова для журнала).
        Не спросили — снимок не читается вовсе."""
        if self.book is None:
            return None, None, "брони выключены"
        asked = B.avail_ask(ask)
        dates = find_dates(ask, today) if asked else []
        want_avail, want_end = len(dates) >= 2, B.rental_end_ask(ask)
        if not want_avail and not want_end:
            return None, None, ("о наличии без двух дат — таблица не звана" if asked else "о бронях не спрашивают")
        rows, bikes, age, why = self.book.get(now)
        now_local = B.local_now(now)
        avail = rental = None
        if want_avail:
            model = B.find_model(ask, bikes) if bikes else None     # ключ модели — живые имена парка
            units = units_of(model, bikes) if model else []
            avail = B.free_bikes(model, units, dates[0], dates[1], rows, age, why, now_local, self.door)
        if want_end:
            rental = B.rental_end(number, rows, age, why, now_local, model_of_name)
        words = "брони: снимок %s, чтений %d" % ("нет" if age is None else "%d мин" % (age // 60), self.book.reads)
        if avail is not None:
            words += " · наличие %s (юнитов %d: свободно %d, занято %d, не проверено %d; дверь %d)" % (
                avail["outcome"], avail["units"], avail["free"], avail["busy"], avail["unchecked"],
                avail["door_calls"])
        if rental is not None:
            words += " · аренда %s (найдено %d, срок истёк %d)" % (rental["outcome"], len(rental["rentals"]),
                                                                  rental["expired"])
        self.log(words)
        return avail, rental, words

    def _now(self, now):
        """Время суждения: заданное вызывающим — как есть; иначе часы адаптера в этот момент (WADRAFTFIX0310)."""
        return self.clock() if now is None else now

    def build(self, number, upto_id, now=None):
        """→ (system, user, сведения) без вызова модели (пробы и тесты меряют то, что уйдёт)."""
        fixed, now = now, self._now(now)
        items, missing = self._history(number, upto_id)
        hist, _ = wa_history.model_view(items)
        hist, n_mask = K.mask(hist)
        cut = 0
        if len(hist) > HISTORY_MAX:
            cut = len(hist) - HISTORY_MAX
            hist = "… (старшая часть истории обрезана: %d симв.)\n" % cut + hist[-HISTORY_MAX:]
        tail = self._tail(items)
        ask_raw = "\n".join(it["text"] or ("[%s]" % it["word"] if it["word"] else "") for it in tail)
        ask, n_mask2 = K.mask(ask_raw[-TAIL_MAX:])
        today = datetime.datetime.fromtimestamp(now + wa_history.PHUKET_OFFSET, datetime.timezone.utc).date()
        terms = client_terms(items, today)              # сутки каждому диапазону дат клиента — кодом (WADAYS0410)
        ctx = self._context(items, tail)                # переписка до вопроса: модель и срок цены (WAPRICECTX0410)
        price, price_words = self._price(ask, today, ctx)
        reasons = K.handoff(ask, price)
        avail, rental, book_words = self._book(number, ask, today, now)
        if avail is not None or rental is not None:
            reasons = B.adjust_reasons(reasons, avail, rental, ask)
        # уроки — SQLite с ожиданием до 5 с: читаются до снятия времени, как и остальное (WATIMEFIX0310)
        lessons = self._lessons()
        # после ожиданий (история, парк и дверь цены, брони, уроки, чтение узлов) время снимается заново
        # (WADRAFTFIX0310): возраст, причина, журнал, блоки знаний и префикс кэша судятся по нему, а не по началу
        # вызова. Дальше до вызова модели блокирующих чтений нет (WATIMEFIX0310)
        nodes = self.knowledge.refresh(self._now(fixed))
        now = self._now(fixed)
        node_list = [nodes[n] for n in K.NODES]
        self.log(knowledge_line(node_list, now))           # на каждый вызов, без текста узлов (WAKNOWFRESH0310)
        # узел старше предела: его текста в промпте нет — черновик пишет человек; причина первой из причин кода
        reasons = K.stale_reasons(node_list, now) + reasons
        parts = K.prompt_parts(price, reasons, node_list, now)
        blocks = ["СЕГОДНЯ: %s (Пхукет)" % today.strftime("%d.%m.%Y")]
        blocks += self._knowledge_blocks(parts, node_list, now)
        lesson_text, n_mask3 = K.mask(lessons_block(lessons))
        if lesson_text:
            blocks.append(lesson_text)
        terms_text = terms_line(terms)
        if terms_text:
            blocks.append(terms_text)
        if "price" in parts:
            blocks.append(parts["price"])
        blocks += [fact["line"] for fact in (avail, rental) if fact is not None]
        if "handoff" in parts:
            blocks.append(parts["handoff"])
        question = ask or "[пусто]"                     # ровно то, что уйдёт последним блоком (WACARDQ0410)
        q_lang = question_lang(question)
        if need_translation(q_lang):
            blocks.append(TR_BLOCK)
        blocks.append("ИСТОРИЯ ПЕРЕПИСКИ (вся, по времени; «мы» — наша сторона):\n" +
                      (hist or "переписки раньше не было") +
                      ("\n⚠️ история неполная: " + "; ".join(missing) if missing else ""))
        blocks.append("КЛИЕНТ СЕЙЧАС (на это и отвечай):\n" + question)
        user = "\n\n".join(blocks)
        system = self._system(SYSTEM_PROMPT if self.book is None else SYSTEM_PROMPT_BOOK, node_list, now)
        info = {"history_items": len(items), "history_chars": len(hist), "history_cut": cut,
                "masked": n_mask + n_mask2 + n_mask3, "lessons": [r[0] for r in lessons], "missing": missing, "price": price, "price_words": price_words,
                "code_reasons": reasons, "nodes": {n: (nodes[n]["read"], nodes[n]["len"]) for n in K.NODES},
                "avail": avail, "rental": rental, "book_words": book_words, "today": today, "terms": terms,
                "user_chars": len(user), "system_chars": system_chars(system), "cache": self.cache,
                "question": question, "q_lang": q_lang,           # карточка сотрудника (WACARDQ0410)
                # время последнего входящего клиента: факт сверки, прочитанный раньше, — устарел (AGENTDEDUP0410)
                "last_in": max((it["ts"] for it in items if it.get("who") == "клиент" and it.get("ts")), default=None)}
        return system, user, info

    def _days_check(self, text, info, words):
        """Сверка суток черновика (WADAYS0410): у диапазона дат число суток не равно разности — причина «нужен
        человек» первой строкой, «Отправить» на версии 1 закрыто (тот же замок, что у денег без опоры). Текст
        не правится; в журнал — только числа."""
        bad = days_claims(text, info.get("today"), [r["days"] for r in info.get("terms") or ()], info.get("price"))
        if not bad:
            return words
        self.log("модель: сутки не по датам %d (названо %s, по датам %s) — причина «нужен человек»"
                 % (len(bad), ",".join(str(n) for _w, n, _r in bad), ",".join(str(r) for _w, _n, r in bad)))
        return K.reason_first(words, K.DAYS_CLAIM_WORDS)

    def draft(self, number, upto_id):
        if self.tools is not None:
            return self._draft_tools(number, upto_id)
        system, user, info = self.build(number, upto_id)
        raw, usage = self.call(system, user)
        self._spend(usage, "черновик:")
        got = parse_reply(raw)
        self.last = {"info": info, "usage": usage, "raw": raw, "parsed": got}
        tok = "токены in=%s out=%s" % ((usage or {}).get("in"), (usage or {}).get("out"))
        if got is None:
            self.log("модель: ответ не JSON или без текста — черновика нет (%s, %d симв.)"
                     % (tok, len(raw or "")))
            return None
        words = [r["words"] for r in info["code_reasons"]]
        if got["lang"] not in ("ru", "en") and K.REASON_WORDS[K.R_LANGUAGE] not in words:
            words.append(K.REASON_WORDS[K.R_LANGUAGE])
        words = K.merge_reasons(words, got["handoff"])      # дедуп по категории (WACARDCOMPACT0310)
        words = self._days_check(got["text"], info, words)   # сутки у дат не по разности — причина (WADAYS0410)
        # деньги в тексте черновика (WAMONEYCHECK0310): процент предоплаты, депозита или скидки и сумма в батах не из
        # блока «ЦЕНА» этого вызова — причина «нужен человек» ПЕРВОЙ строкой (на карточке видна при любом числе
        # причин). Текст ответа не правится. В журнал — только числа: текст черновика туда не идёт.
        claims = K.money_claims(got["text"], info["price"])
        if claims:
            words = K.reason_first(words, K.MONEY_CLAIM_WORDS)   # уже стоящая — вперёд (WADRAFTFIX0310)
            self.log("модель: денежных утверждений без опоры %d (процентов %d, сумм %d) — причина «нужен человек»"
                     % (len(claims), sum(1 for c in claims if c[0] == "процент"),
                        sum(1 for c in claims if c[0] == "сумма")))
        self.log("модель: черновик %d симв., история %d строк / %d симв., маска %d, %s, причин %d (%s)"
                 % (len(got["text"]), info["history_items"], info["history_chars"], info["masked"],
                    info["price_words"], len(words), tok))
        return dict({"text": got["text"], "handoff": words, "lang": got["lang"], "why": got["why"]},
                    **card_fields(info, got))

    # ── черновик со сверкой (AGENTLOOPA0310, Т4а) ─────────────────────────────────────────

    def _tool_doors(self, number, upto_id):
        """Двери адаптера (переписка, аренда, правила) + двери моста из `self.tools`. Все — только чтение."""
        def history():
            items, _missing = self._history(number, upto_id)
            return items

        def rental():
            if self.book is None:
                return {"ok": False, "error": "брони выключены"}
            rows, _bikes, _age, why = self.book.get(self.clock())
            if rows is None:
                return {"ok": False, "error": why or "снимок броней не прочитан"}
            digits = re.sub(r"\D", "", str(number or ""))
            key = digits[-B.KEY_DIGITS:] if len(digits) >= B.KEY_DIGITS else None
            hits = [r for r in rows if key and B.is_active(r) and key in B.phone_keys(r.get("contacts"))]
            return {"ok": True, "rows": hits}

        def rules():
            return self.knowledge.snap.get("business_rules")

        doors = {"history": history, "rental": rental, "rules": rules}
        doors.update({k: v for k, v in (self.tools or {}).items() if k in ("cash", "contract", "contract_pdf")})
        return doors

    def _draft_tools(self, number, upto_id):
        """Сверка: модель вызывает инструменты (≤ T.MAX_CALLS вызовов, ≤ T.MAX_SEC с), код принимает факты, считает
        суммы и судит денежные роли. Предел превышен — обычный черновик одним вызовом без фактов и причина «сверка не
        завершена» первой. Новое входящее посреди сверки — черновика нет (служба повторит позже)."""
        import wa_agent_tools as T
        system, user, info = self.build(number, upto_id)
        with door_budget(T.MAX_SEC - T.FALLBACK_SEC):          # плечо моста не переживёт срок сверки (AGENTDEDUP0410)
            out = T.run(self.call, system, user, self._tool_doors(number, upto_id), number=number, clock=self.clock,
                        fresh=(lambda: self.fresh(number, upto_id)) if self.fresh else None,
                        spend=lambda u: self._spend(u, "сверка:"))
        jr = out["journal"]
        if out["state"] == T.ABORTED:
            for line in jr.lines():
                self.log(line)
            self.log("сверка прервана: новое входящее — черновика нет")
            self.last = {"info": info, "tools": out}
            return None
        reasons, raw, usage = [], out["raw"], out["usage"]
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
        got = parse_reply(raw)
        # процент скидки за срок, названной дверью, — с опорой (WAPRICECTX0410): судья сверки процент судит без
        # исхода цены, поэтому названная дверью скидка снимается из текста до суда; прочее — как было
        said = K.without_known_discount(got["text"], info["price"]) if got else ""
        words_t, figures = T.judge(said, info["price"], out["results"], jr,
                                   since=info.get("last_in"))
        for line in jr.lines():
            self.log(line)
        self.last = {"info": info, "usage": usage, "raw": raw, "parsed": got, "tools": out, "figures": figures}
        if got is None:
            self.log("модель: ответ не JSON или без текста — черновика нет (сверка %s, вызовов %d)"
                     % (out["state"], out["calls"]))
            return None
        words = [r["words"] for r in info["code_reasons"]]
        if got["lang"] not in ("ru", "en") and K.REASON_WORDS[K.R_LANGUAGE] not in words:
            words.append(K.REASON_WORDS[K.R_LANGUAGE])
        words = K.merge_reasons(words, got["handoff"])
        words = self._days_check(got["text"], info, words)      # сутки у дат (WADAYS0410)
        for w in reversed(words_t):                             # причины кода о деньгах — вперёд
            words = K.reason_first(words, w)
        for w in reversed(reasons):                             # «сверка не завершена» — самой первой
            words = K.reason_first(words, w)
        self.log("модель: черновик %d симв. со сверкой (%s, вызовов %d, %.1f с), причин %d"
                 % (len(got["text"]), out["state"], out["calls"], out["sec"], len(words)))
        return dict({"text": got["text"], "handoff": words, "lang": got["lang"], "why": got["why"]},
                    **card_fields(info, got))

    # ── напоминание притихшему (WAFOLLOWUP0210) ───────────────────────────────────────────

    def build_followup(self, number, upto_id, now=None):
        """→ (system, user, сведения) для напоминания без вызова модели: история под маской, узлы знаний,
        действующие уроки. Цены и «нужен человек» не идут — напоминание нового не обещает."""
        fixed, now = now, self._now(now)
        items, missing = self._history(number, upto_id)
        hist, _ = wa_history.model_view(items)
        hist, n_mask = K.mask(hist)                       # маска до модели — как у черновика
        cut = 0
        if len(hist) > HISTORY_MAX:
            cut = len(hist) - HISTORY_MAX
            hist = "… (старшая часть истории обрезана: %d симв.)\n" % cut + hist[-HISTORY_MAX:]
        today = datetime.datetime.fromtimestamp(now + wa_history.PHUKET_OFFSET, datetime.timezone.utc).date()
        lessons = self._lessons()                         # до снятия времени, как у черновика (WATIMEFIX0310)
        nodes = self.knowledge.refresh(self._now(fixed))
        now = self._now(fixed)                            # после уроков и чтения узлов — заново, как у черновика
        node_list = [nodes[n] for n in K.NODES]
        self.log(knowledge_line(node_list, now))
        parts = K.prompt_parts(None, [], node_list, now)
        blocks = ["СЕГОДНЯ: %s (Пхукет)" % today.strftime("%d.%m.%Y")]
        blocks += self._knowledge_blocks(parts, node_list, now)
        lesson_text, n_mask2 = K.mask(lessons_block(lessons))
        if lesson_text:
            blocks.append(lesson_text)
        blocks.append("ИСТОРИЯ ПЕРЕПИСКИ (вся, по времени; «мы» — наша сторона; последнее слово — наше, клиент "
                      "молчит):\n" + (hist or "переписки раньше не было") +
                      ("\n⚠️ история неполная: " + "; ".join(missing) if missing else ""))
        user = "\n\n".join(blocks)
        return self._system(FOLLOW_SYSTEM_PROMPT, node_list, now), user, {
            "history_items": len(items), "history_chars": len(hist), "history_cut": cut,
            "masked": n_mask + n_mask2, "missing": missing, "user_chars": len(user), "cache": self.cache}

    def followup(self, number, upto_id):
        """Напоминание → текст | {skip: True, why} («не нужно») | None (не JSON, нет решения)."""
        system, user, info = self.build_followup(number, upto_id)
        raw, usage = self.call(system, user)
        self._spend(usage, "напоминание:")
        got = parse_followup(raw)
        self.last = {"info": info, "usage": usage, "raw": raw, "parsed": got}
        tok = "токены in=%s out=%s" % ((usage or {}).get("in"), (usage or {}).get("out"))
        if got is None:
            self.log("модель (напоминание): ответ не JSON или без решения — повтор позже (%s, %d симв.)"
                     % (tok, len(raw or "")))
            return None
        if got.get("skip"):
            self.log("модель (напоминание): не нужно (%s)" % tok)
            return got
        self.log("модель (напоминание): %d симв., история %d строк, маска %d (%s)"
                 % (len(got["text"]), info["history_items"], info["masked"], tok))
        return got["text"]


FOLLOW_SYSTEM_PROMPT = """Ты — менеджер проката мотобайков TurboBaby на Пхукете. Клиент в WhatsApp притих: последнее сообщение в переписке — наше, и он молчит уже минут пятнадцать или дольше. Реши, нужно ли ему мягкое напоминание, и если нужно — напиши его ЧЕРНОВИК. Черновик читает сотрудник и сам решает, отправлять ли его.

Напоминание НЕ нужно, если: разговор завершён (клиент поблагодарил, попрощался, сказал «ок», «подумаю», «вернусь позже», «напишу завтра»); мы уже напомнили и клиент так и не ответил; наше последнее сообщение — прощание или «спасибо»; ждём не клиента, а себя (мы обещали уточнить и вернуться); клиент отказался.

Если нужно:
1. ОДНО короткое вежливое сообщение, обычно одно предложение, по сути беседы: о том, на чём остановились (подобрать байк, даты, доставка, документы), без давления и без «вы ещё здесь?».
2. На языке клиента: русский или английский.
3. Ничего нового не обещай и не называй: ни цен, ни наличия, ни брони, ни скидок, ни сроков от имени людей. Не пересказывай историю.
4. Метки «[скрыто: …]» — скрытые данные клиента; не упоминай их.

Ответ — РОВНО один JSON-объект без пояснений и без ``` вокруг:
{"skip": false, "text": "текст напоминания", "lang": "ru" или "en", "why": "одна строка для сотрудника"}
или, если напоминание не нужно:
{"skip": true, "text": "", "why": "одна строка для сотрудника: почему не нужно"}"""


def parse_followup(raw):
    """Ответ модели о напоминании → {skip: True, why} | {text, lang, why} | None (не JSON, нет решения)."""
    s = str(raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        data = json.loads(s)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    why = str(data.get("why") or "").strip()[:300]
    if data.get("skip") is True:
        return {"skip": True, "why": why}
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return {"text": text.strip(), "lang": str(data.get("lang") or "").strip().lower()[:8], "why": why}
