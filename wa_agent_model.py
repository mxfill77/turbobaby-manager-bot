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
    модель из парка И обе даты. Без дат или модели дверь цены не зовётся;
  • причины «нужен человек» кодом — `wa_agent_knowledge.handoff` по тому, что клиент спрашивает сейчас.

ОТВЕТ МОДЕЛИ — JSON {text, lang, handoff[], why}. Не JSON, нет текста — черновика нет, строка журнала
(ядро повторит не раньше MODEL_RETRY_SEC). lang не ru/en — причина «язык». Итог `draft` — словарь
{text, handoff[слова], lang, why} (ядро принимает и прежнюю строку); причины — кода и модели вместе.

ПЛАТЕЛЬЩИК — платный ключ API тем же путём, что у Splinter (`claude_client.ClaudeClient`:
ANTHROPIC_API_KEY из .env корня дерева, учёт трат `spend_ledger.meter`). Значение ключа не печатается.

ЖУРНАЛ — только номер черновика у ядра, объёмы, токены, причины словами. Текстов, номеров и имён
клиентов в журнале нет.
"""

import datetime
import json
import os
import re
import time

import wa_agent
import wa_agent_knowledge as K
import wa_history

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = "claude-sonnet-4-5"          # как CLAUDE_MODEL Splinter по умолчанию (claude_client)
MAX_TOKENS = 700
HISTORY_MAX = 60000                           # символов истории; старше — обрезается с головы, словами
TAIL_MAX = 4000

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


def find_model(text, bikes):
    """Модель из парка, названная в словах клиента (самое длинное совпадение) | None."""
    t1, t2 = _alnum(text), _nocc(text)
    best = None
    for b in bikes or ():
        m = model_of_name((b or {}).get("name"))
        k1, k2 = _alnum(m), _nocc(m)
        if len(k2) < 3:
            continue
        if (k1 and k1 in t1) or (k2 and k2 in t2):
            if best is None or len(k1) > len(_alnum(best)):
                best = m
    return best


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


# ── платный вызов (как у Splinter) ─────────────────────────────────────────────────────

def paid_call(model_name=None, env_file=None):
    """→ call(system, user) → (текст, usage-словарь). Ключ — ANTHROPIC_API_KEY из .env дерева тем же
    путём, что у Splinter; учёт трат — `spend_ledger.meter`. Значение ключа нигде не печатается."""
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
        try:
            import spend_ledger
            spend_ledger.meter(name, getattr(resp, "usage", None))
        except Exception:                                            # noqa: BLE001
            pass
        u = getattr(resp, "usage", None)
        text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text, {"model": getattr(resp, "model", name),
                      "in": getattr(u, "input_tokens", None), "out": getattr(u, "output_tokens", None)}
    return call


# ── адаптер ────────────────────────────────────────────────────────────────────────────

class ModelAdapter(wa_agent.Model):
    """draft(number, upto_id) → {text, handoff[слова], lang, why} | None.

    call(system, user) → (текст, usage) — модель; read_doc(name) → ответ моста; fleet() → ответ моста
    `fleet`; door(unit, ds, de) → ответ двери цены. Все — снаружи (в тестах подделки)."""

    def __init__(self, queue_db, call, read_doc=None, fleet=None, door=None, archive_db="",
                 manifest="", media_dir="", no_price_models=(), clock=time.time, log=None, agent_db=""):
        self.queue_db, self.call = queue_db, call
        self.agent_db = agent_db                          # outbox: ушедшее через API (WARELAYTEXT0210)
        self.fleet, self.door = fleet, door
        self.archive_db, self.manifest, self.media_dir = archive_db, manifest, media_dir
        self.no_price_models = tuple(no_price_models)
        self.knowledge = K.Knowledge(read_doc or (lambda n: {"ok": False, "error": "моста нет"}))
        self.clock = clock
        self.log = log or (lambda line: None)
        self.last = None                                  # разбор последнего вызова (для проб и тестов)

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
        model = find_model(ask, bikes)
        if not model:
            return None, "о цене спрашивают без модели из парка — дверь не звана"
        res = K.quote(model, dates[0], dates[1], self.door, lambda m: units_of(m, bikes),
                      self.no_price_models)
        return res, "цена: %s" % res["outcome"]

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
        nodes = self.knowledge.refresh(now)
        parts = K.prompt_parts(price, reasons, [nodes[n] for n in K.NODES], now)
        blocks = ["СЕГОДНЯ: %s (Пхукет)" % today.strftime("%d.%m.%Y")]
        blocks += [parts[k] for k in sorted(parts) if k.startswith("node:")]
        if "price" in parts:
            blocks.append(parts["price"])
        if "handoff" in parts:
            blocks.append(parts["handoff"])
        blocks.append("ИСТОРИЯ ПЕРЕПИСКИ (вся, по времени; «мы» — наша сторона):\n" +
                      (hist or "переписки раньше не было") +
                      ("\n⚠️ история неполная: " + "; ".join(missing) if missing else ""))
        blocks.append("КЛИЕНТ СЕЙЧАС (на это и отвечай):\n" + (ask or "[пусто]"))
        user = "\n\n".join(blocks)
        info = {"history_items": len(items), "history_chars": len(hist), "history_cut": cut,
                "masked": n_mask + n_mask2, "missing": missing, "price": price, "price_words": price_words,
                "code_reasons": reasons, "nodes": {n: (nodes[n]["read"], nodes[n]["len"]) for n in K.NODES},
                "user_chars": len(user), "system_chars": len(SYSTEM_PROMPT)}
        return SYSTEM_PROMPT, user, info

    def draft(self, number, upto_id):
        system, user, info = self.build(number, upto_id)
        raw, usage = self.call(system, user)
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
        for h in got["handoff"]:
            if h not in words:
                words.append(h)
        self.log("модель: черновик %d симв., история %d строк / %d симв., маска %d, %s, причин %d (%s)"
                 % (len(got["text"]), info["history_items"], info["history_chars"], info["masked"],
                    info["price_words"], len(words), tok))
        return {"text": got["text"], "handoff": words, "lang": got["lang"], "why": got["why"]}
