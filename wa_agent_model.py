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
    НЕИЗВЕСТНО словами, а не пусто;
  • цена — `wa_agent_knowledge.quote` ТОЛЬКО когда клиент сейчас спрашивает о цене И в его словах есть
    модель из парка И обе даты. Без дат или модели дверь цены не зовётся. Модель ищется по ключу живых имён
    парка (`wa_book_read.find_model`, WADRAFTFIX0210), дверь цены на вопрос — не больше одного раза;
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

ПЛАТЕЛЬЩИК — платный ключ API тем же путём, что у Splinter (`claude_client.ClaudeClient`:
ANTHROPIC_API_KEY из .env корня дерева, учёт трат `spend_ledger.meter`). Значение ключа не печатается.

ЖУРНАЛ — только номер черновика у ядра, объёмы, токены, причины словами. Текстов, номеров и имён
клиентов в журнале нет.

КЭШ ПРОМПТА (WAAGENTCACHE0210) — выключатель службы WA_AGENT_CACHE: «1h»/«5m» — срок, 1/true/yes/on — 1h,
прочее и пусто — выключен (запрос байт-в-байт прежний). Включён — неизменная часть идёт ВПЕРЕДИ одним
системным префиксом: инструкция, затем снимки `faq` и `business_rules` БЕЗ возраста (меняются только со
сменой узла) с отметкой `cache_control` на последнем блоке; возраст узлов, уроки, цена, факты, история и
вопрос — после, в сообщении. Цена каждого вызова считается по usage (вход, запись в кэш 5 мин/1 ч, чтение
из кэша, выход) — строкой журнала и итогом в сводку службы (`spend`). Множители — по документации Anthropic
«Prompt caching»: запись 5 мин 1.25× цены входа, запись 1 ч 2×, чтение 0.1×.
"""

import datetime
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
MAX_TOKENS = 700
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
    return {"text": text.strip(), "lang": str(data.get("lang") or "").strip().lower()[:8],
            "handoff": hand[:8], "why": str(data.get("why") or "").strip()[:300]}


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
    return "УЗЕЛ %s (%d симв.):\n%s" % (node["name"], node["len"], node["text"])


def knowledge_stable(nodes, now=None):
    """Неизменная часть знаний — одним блоком: шапка и узлы по имени."""
    return "\n\n".join([KNOW_HEAD] + [node_stable(n, now) for n in _by_name(nodes)])


def ages_block(nodes, now=None):
    """Переменная часть знаний — возраст снимков и причина непрочтения, в сообщение (после префикса)."""
    out = []
    for n in _by_name(nodes):
        age = K.node_age(n, now)
        out.append("%s — %s" % (n.get("name"), "снят %d мин назад" % int(age // 60) if age is not None else
                                "НЕИЗВЕСТНО: не прочитан (%s)" % (n.get("why") or "причина не названа")))
    return "ВОЗРАСТ ЗНАНИЙ: " + "; ".join(out)


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


# ── адаптер ────────────────────────────────────────────────────────────────────────────

class ModelAdapter(wa_agent.Model):
    """draft(number, upto_id) → {text, handoff[слова], lang, why} | None.

    call(system, user) → (текст, usage) — модель; read_doc(name) → ответ моста; fleet() → ответ моста
    `fleet`; door(unit, ds, de) → ответ двери цены. Все — снаружи (в тестах подделки)."""

    def __init__(self, queue_db, call, read_doc=None, fleet=None, door=None, archive_db="",
                 manifest="", media_dir="", no_price_models=(), clock=time.time, log=None, agent_db="",
                 lessons_db="", book=None, cache=None):
        self.queue_db, self.call = queue_db, call
        self.cache = cache if cache in CACHE_TTLS else None   # срок кэша промпта (WAAGENTCACHE0210); None — выкл
        self.spend = {"calls": 0, "in": 0, "cw": 0, "cr": 0, "out": 0, "usd": 0.0, "usd_nocache": 0.0}
        self.book = book                                  # снимок броней `wa_book_read.Snapshot`; None — выкл
        self.agent_db = agent_db                          # outbox: ушедшее через API (WARELAYTEXT0210)
        self.lessons_db = lessons_db                      # уроки людей (WAAGENTLESSON0210); пусто — выкл
        self.fleet, self.door = fleet, door
        self.archive_db, self.manifest, self.media_dir = archive_db, manifest, media_dir
        self.no_price_models = tuple(no_price_models)
        self.knowledge = K.Knowledge(read_doc or (lambda n: {"ok": False, "error": "моста нет"}))
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

    def _price(self, ask, today):
        """Цена — только на вопрос о цене с моделью и обеими датами. → (исход quote | None, слова)."""
        if not _PRICE_ASK.search(ask):
            return None, "о цене не спрашивают"
        dates = find_dates(ask, today)
        if len(dates) < 2:
            return None, "о цене спрашивают без дат — дверь не звана"
        if self.fleet is None or self.door is None:
            return None, "двери цены нет"
        try:
            bikes = fleet_bikes(self.fleet())
        except Exception as e:                                       # noqa: BLE001
            bikes = None
            self.log("парк не прочитан: %s" % type(e).__name__)
        if bikes is None:
            return K.quote("?", dates[0], dates[1], self.door, lambda m: None), "парк не прочитан"
        model = B.find_model(ask, bikes)                            # ключ модели — живые имена парка
        if not model:
            return None, "о цене спрашивают без модели из парка — дверь не звана"
        res = K.quote(model, dates[0], dates[1], self.door, lambda m: units_of(m, bikes),
                      self.no_price_models)
        return res, "цена: %s" % res["outcome"]

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

    def build(self, number, upto_id, now=None):
        """→ (system, user, сведения) без вызова модели (пробы и тесты меряют то, что уйдёт)."""
        now = self.clock() if now is None else now
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
        price, price_words = self._price(ask, today)
        reasons = K.handoff(ask, price)
        avail, rental, book_words = self._book(number, ask, today, now)
        if avail is not None or rental is not None:
            reasons = B.adjust_reasons(reasons, avail, rental, ask)
        nodes = self.knowledge.refresh(now)
        node_list = [nodes[n] for n in K.NODES]
        parts = K.prompt_parts(price, reasons, node_list, now)
        blocks = ["СЕГОДНЯ: %s (Пхукет)" % today.strftime("%d.%m.%Y")]
        blocks += self._knowledge_blocks(parts, node_list, now)
        lessons = self._lessons()
        lesson_text, n_mask3 = K.mask(lessons_block(lessons))
        if lesson_text:
            blocks.append(lesson_text)
        if "price" in parts:
            blocks.append(parts["price"])
        blocks += [fact["line"] for fact in (avail, rental) if fact is not None]
        if "handoff" in parts:
            blocks.append(parts["handoff"])
        blocks.append("ИСТОРИЯ ПЕРЕПИСКИ (вся, по времени; «мы» — наша сторона):\n" +
                      (hist or "переписки раньше не было") +
                      ("\n⚠️ история неполная: " + "; ".join(missing) if missing else ""))
        blocks.append("КЛИЕНТ СЕЙЧАС (на это и отвечай):\n" + (ask or "[пусто]"))
        user = "\n\n".join(blocks)
        system = self._system(SYSTEM_PROMPT if self.book is None else SYSTEM_PROMPT_BOOK, node_list, now)
        info = {"history_items": len(items), "history_chars": len(hist), "history_cut": cut,
                "masked": n_mask + n_mask2 + n_mask3, "lessons": [r[0] for r in lessons], "missing": missing, "price": price, "price_words": price_words,
                "code_reasons": reasons, "nodes": {n: (nodes[n]["read"], nodes[n]["len"]) for n in K.NODES},
                "avail": avail, "rental": rental, "book_words": book_words,
                "user_chars": len(user), "system_chars": system_chars(system), "cache": self.cache}
        return system, user, info

    def draft(self, number, upto_id):
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
        self.log("модель: черновик %d симв., история %d строк / %d симв., маска %d, %s, причин %d (%s)"
                 % (len(got["text"]), info["history_items"], info["history_chars"], info["masked"],
                    info["price_words"], len(words), tok))
        return {"text": got["text"], "handoff": words, "lang": got["lang"], "why": got["why"]}

    # ── напоминание притихшему (WAFOLLOWUP0210) ───────────────────────────────────────────

    def build_followup(self, number, upto_id, now=None):
        """→ (system, user, сведения) для напоминания без вызова модели: история под маской, узлы знаний,
        действующие уроки. Цены и «нужен человек» не идут — напоминание нового не обещает."""
        now = self.clock() if now is None else now
        items, missing = self._history(number, upto_id)
        hist, _ = wa_history.model_view(items)
        hist, n_mask = K.mask(hist)                       # маска до модели — как у черновика
        cut = 0
        if len(hist) > HISTORY_MAX:
            cut = len(hist) - HISTORY_MAX
            hist = "… (старшая часть истории обрезана: %d симв.)\n" % cut + hist[-HISTORY_MAX:]
        today = datetime.datetime.fromtimestamp(now + wa_history.PHUKET_OFFSET, datetime.timezone.utc).date()
        nodes = self.knowledge.refresh(now)
        node_list = [nodes[n] for n in K.NODES]
        parts = K.prompt_parts(None, [], node_list, now)
        blocks = ["СЕГОДНЯ: %s (Пхукет)" % today.strftime("%d.%m.%Y")]
        blocks += self._knowledge_blocks(parts, node_list, now)
        lesson_text, n_mask2 = K.mask(lessons_block(self._lessons()))
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
