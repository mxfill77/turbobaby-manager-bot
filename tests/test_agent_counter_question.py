# -*- coding: utf-8 -*-
"""USEFULQ1310: черновик вправе задать клиенту ОДИН встречный вопрос о недостающем — правило 7 SYSTEM_PROMPT.

Повод — §12.8, пять живых эпизодов на стенде (judge2/VERDICT_EP.md, 13.10.2026): смысл 5/5 «ЧАСТЬ», встречный вопрос
у менеджера в 2 эпизодах из 5 (E01 — куда доставить, E03 — на какой срок), у черновика — в 0 из 5. Код вопрос не
запрещает: ни одна сверка (деньги, сутки, приезд, язык; судья сверки `wa_agent_tools.judge`) вопросительную фразу не
судит. Не разрешал промпт: правила 4–7 знают только «коллега уточнит / уточню у коллег», а указание спросить живёт
лишь внутри блока «ЦЕНА» (его нет без вопроса о цене с моделью). Ремонт — одно предложение в КОНЦЕ правила 7
(15-го правила нет: test_wa_our_words держит пункты 1..14), вариант с бронями наследует его заменой правил 4/7.

Класс, а не эпизод: «ответ упирается в то, что знает только клиент и чего он ещё не назвал» — даты или срок, куда
доставить, какая модель, сколько байков. Границы — в той же фразе: вопрос ОДИН, названное не переспрашивается,
правила 8 («ок» — без новых вопросов) и 14 (строка «минимум N сут.» — срок не спрашивать) сильнее, handoff прежний.
USEFUL1310 fix (находка n2 судьи по смыслу): вопрос — В ДОПОЛНЕНИЕ к тому, что можно сказать по блокам и знаниям, а не
вместо него (словами фразы; мутант «вопрос вместо ответа»).

Случаи — сквозь живой адаптер и ядро на подделках test_wa_agent_model (модель, мост, Bot API, дверь отправки; сети
и модели нет): фраза доходит до модели в обоих вариантах инструкции и с кэшем; сообщение пользователя байт-в-байт
прежнее (правка — только инструкция); черновик с вопросом не получает НИ ОДНОЙ лишней причины против близнеца без
вопроса (RU/EN); замки не ослаблены — выдуманная сумма, приезд без опоры, неверные сутки и «оплату получили» внутри
вопросительного черновика ловятся по-прежнему. ЧЕСТНЫЙ ПРЕДЕЛ: спросит ли модель — тестом не проверяется (модели
нет); это стенд E01–E05 с реальной моделью. Мутанты — правка исходника wa_agent_model.py в памяти."""

import datetime
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent_knowledge as K             # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tools as T                 # noqa: E402
import wa_book_read as B                   # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
T0 = TM.T0                                 # 21.09.2026 по Пхукету — «сейчас» мира TM
TODAY = datetime.date(2026, 9, 21)
QUESTION = ("Если ответ упирается в то, что знает только клиент и чего он в переписке ещё не назвал (даты или срок, "
            "куда доставить, какая модель, сколько байков), — это спроси у него сам, а не «коллега уточнит»: в "
            "черновике ОДИН короткий встречный вопрос о самом нужном; что можно сказать по блокам и знаниям — скажи, "
            "вопрос — в дополнение, а не вместо; названное клиентом не переспрашивай (правила 8 и 14 сильнее), "
            "handoff — как выше.")
RULE7_HEAD = "Причины из блока «НУЖЕН ЧЕЛОВЕК» перенеси в handoff обязательно."
MONEY, DAYS, ARR = K.MONEY_CLAIM_WORDS, K.DAYS_CLAIM_WORDS, K.ARRIVAL_CLAIM_WORDS

# Клиент не назвал то, что знает только он (RU/EN): место доставки, конец срока, модель, число байков, даты.
ASKS = ["Здравствуйте, нужен мопед. Сколько стоит доставка?", "есть байки в наличии? нужен уже сейчас",
        "Хочу арендовать байк, что посоветуете?", "Нам нужно несколько байков на компанию",
        "Hi, how much is delivery?", "Need a scooter from tomorrow", "What bikes do you have?"]
# Встречные вопросы черновика (RU/EN) — по одному о недостающем.
QS = ["Куда привезти байк?", "На сколько дней нужен байк?", "Какой байк вам ближе — скутер или мотоцикл?",
      "Сколько байков нужно?", "На какие даты нужен байк?", "Where should we bring the bike?",
      "Until what date do you need it?", "Which dates do you need the bike for?", "How many bikes do you need?",
      "Подскажите, в какой район доставить байк?"]
# (вопрос клиента, черновик без вопроса, встречный вопрос, язык) — близнецы для сверки причин.
PAIRS = [(ASKS[0], "Здравствуйте! Доставляем по Пхукету, стоимость доставки уточнит коллега.", "Куда привезти байк?",
          "ru"),
         (ASKS[1], "Здравствуйте! Наличие уточню у коллег.", "На сколько дней нужен байк?", "ru"),
         (ASKS[2], "Добрый день! Подберём байк.", "Какой вам ближе — скутер или мотоцикл?", "ru"),
         (ASKS[3], "Добрый день! Подберём байки, наличие уточнит коллега.", "Сколько байков нужно?", "ru"),
         (ASKS[4], "Hi! We deliver within Phuket, a colleague will confirm the cost.", "Where should we bring the bike?",
          "en"),
         (ASKS[5], "Hi! A colleague will check what is free.", "Until what date do you need it?", "en"),
         (ASKS[6], "Hi! A colleague will check what is free.", "Which dates do you need the bike for?", "en")]


def reply(text, lang="ru"):
    return json.dumps({"text": text, "lang": lang, "handoff": [], "why": "встречный вопрос"}, ensure_ascii=False)


def world(M, text=None, lang="ru"):
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        return TM.World(reply=reply(text, lang) if text is not None else TM.OK_JSON)
    finally:
        TM.WM = keep


def run(M, q, text, lang="ru"):
    """Фраза клиента + ответ подделки модели сквозь адаптер M → (system, user, причины, кнопки карточки)."""
    w = world(M, text, lang)
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    system, user = w.call.calls[0]
    return system, user, hand, TM.buttons(cards[-1])


def system_text(system):
    return system if isinstance(system, str) else system[0]["text"]


def rule(p, n):
    return next((x for x in p.splitlines() if x.startswith("%d. " % n)), "")


def built(M, text, cache=None, book=False):
    """Живой `build` модуля M (модель не зовётся) → (system, user, info)."""
    w = world(M)
    ad = w.adapter
    if cache:
        ad = M.ModelAdapter(w.qpath, w.call, read_doc=w.bridge.read_doc, fleet=w.bridge.fleet, door=w.bridge.door,
                            archive_db=w.apath, clock=lambda: T0, log=w.lines.append, cache=cache)
    if book:
        ad.book = B.Snapshot(lambda: {"ok": True, "data": {"clients": [], "summary": {"count": 0}}}, w.bridge.fleet)
    rid = w.put(T0, text)
    return ad.build(TM.NUM, rid, now=T0 + 100)


# ------------------------------- инструкция -------------------------------

def c_rule7_ends_with_question(M):
    """Фраза — последним предложением правила 7, после прежнего текста правила, в обоих вариантах инструкции; ровно раз."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        r7 = rule(p, 7)
        assert r7.endswith(RULE7_HEAD + " " + QUESTION), r7[-500:]
        assert p.count(QUESTION) == 1 and r7.count("встречный вопрос") == 1, p.count(QUESTION)
        assert "перечисли причины в handoff" in r7, r7[:400]


def c_rules_still_1_to_14(M):
    """15-го правила нет, после 14 — пустая строка; замены варианта с бронями — ровно по разу; «НАЛИЧИЕ» — только там."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        nums = [int(x) for x in re.findall(r"^(\d{1,2})\. ", p.split("Ответ — РОВНО")[0], re.M)]
        assert nums == list(range(1, 15)), nums
        lines = p.splitlines()
        i = lines.index(rule(p, 14))
        assert lines[i + 1] == "" and lines[i + 2].startswith("Ответ — РОВНО"), lines[i:i + 3]
        assert rule(p, 13).startswith("13. Поле \"why\""), rule(p, 13)[:60]
    s = M.SYSTEM_PROMPT
    assert s.count(M._RULE4_OLD) == 1 and s.count(M._RULE7_OLD) == 1, (s.count(M._RULE4_OLD), s.count(M._RULE7_OLD))
    assert M.SYSTEM_PROMPT_BOOK == s.replace(M._RULE4_OLD, M._RULE4_BOOK).replace(M._RULE7_OLD, M._RULE7_BOOK)
    assert "НАЛИЧИЕ" not in s and "«НАЛИЧИЕ»" in M.SYSTEM_PROMPT_BOOK


def c_question_scope(M):
    """Граница класса — словами самой фразы: только то, что знает клиент; вопрос один; названное не переспрашивается;
    правила 8 и 14 сильнее (и они на месте); handoff не отменён. Решения человека (наличие, цена, оплата) — не вопрос."""
    r7 = rule(M.SYSTEM_PROMPT, 7)
    tail = r7.split(RULE7_HEAD, 1)[1] if RULE7_HEAD in r7 else ""
    assert tail.strip(), r7[-300:]
    items = re.search(r"\(([^()]*)\)", tail)
    assert items and [x.strip() for x in items.group(1).split(",")] == [
        "даты или срок", "куда доставить", "какая модель", "сколько байков"], tail
    low = items.group(1).lower()
    assert not any(w in low for w in ("налич", "цен", "оплат", "скидк", "депозит", "брон")), low
    assert "только клиент" in tail and "ещё не назвал" in tail, tail
    assert "ОДИН короткий встречный вопрос" in tail and "о самом нужном" in tail, tail
    assert "не переспрашивай" in tail and "(правила 8 и 14 сильнее)" in tail, tail
    assert "handoff — как выше" in tail, tail
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):             # ссылки фразы указывают на живые правила
        assert rule(p, 8).startswith("8. На «спасибо», «ок» и подобное — короткий вежливый ответ без новых вопросов"), \
            rule(p, 8)
        assert "срок НЕ спрашивай" in rule(p, 14) and "не переспрашивай" in rule(p, 14), rule(p, 14)[-200:]


def c_follow_prompt_untouched(M):
    """Напоминание притихшему клиенту — свой контур: фразы там нет."""
    assert QUESTION not in M.FOLLOW_SYSTEM_PROMPT and "встречный вопрос" not in M.FOLLOW_SYSTEM_PROMPT


# ------------------------------- до модели -------------------------------

def c_reaches_model_ru_en(M):
    """Каждая формулировка RU/EN без недостающего: инструкция с фразой — в system живого вызова, ровно как SYSTEM_PROMPT."""
    for q in ASKS:
        system, _user, _hand, _kb = run(M, q, "Добрый день!")
        assert system_text(system) == M.SYSTEM_PROMPT and QUESTION in system_text(system), (q, system_text(system)[-300:])


def c_reaches_model_cache_and_book(M):
    """С кэшем фраза — в первом блоке (префикс кэша, отметка на последнем); с бронями — в SYSTEM_PROMPT_BOOK."""
    system, _u, _i = built(M, ASKS[0], cache="1h")
    assert isinstance(system, list) and system[0]["text"] == M.SYSTEM_PROMPT and "cache_control" not in system[0]
    assert system[-1]["cache_control"]["ttl"] == "1h" and QUESTION in system[0]["text"], system[-1].keys()
    s_book, _u2, _i2 = built(M, ASKS[4], book=True)
    assert s_book == M.SYSTEM_PROMPT_BOOK and QUESTION in s_book, s_book[-300:]


def c_only_instruction_changed(M):
    """Правка — только инструкция: сообщение пользователя и разбор кода байт-в-байт как у модуля без фразы; system
    длиннее ровно на фразу. Значит блоков, причин «НУЖЕН ЧЕЛОВЕК» и цены правка не трогает."""
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    assert src.count(" " + QUESTION) == 1, src.count(" " + QUESTION)
    base = module(src.replace(" " + QUESTION, ""), "wa_agent_model_noq")
    for q in ASKS:
        s1, u1, i1 = built(M, q)
        s0, u0, i0 = built(base, q)
        assert u1 == u0, (q, u1[-300:], u0[-300:])
        assert {k: v for k, v in i1.items() if k != "system_chars"} == {k: v for k, v in i0.items()
                                                                         if k != "system_chars"}, q
        assert s1 == s0.replace(RULE7_HEAD, RULE7_HEAD + " " + QUESTION, 1) and s0 != s1, q


# ------------------------------- код вопрос не наказывает -------------------------------

def c_question_not_punished_twins(M):
    """Черновик с встречным вопросом — ни одной лишней причины против близнеца без вопроса; «Отправить» на месте."""
    for q, base, qq, lang in PAIRS:
        _s, _u, hand0, kb0 = run(M, q, base, lang)
        _s, _u, hand1, kb1 = run(M, q, base + " " + qq, lang)
        assert hand1 == hand0 and kb1 == kb0 and kb1[0] == "wa:send:1:1", (q, hand0, hand1, kb0, kb1)


def c_question_checks_pure(M):
    """Сверки кода по самой фразе (RU/EN): деньги, приезд, сутки и судья сверки (с вопросом клиента об оплате и без)
    — пусто."""
    for t in QS:
        assert K.money_claims(t, None) == [] and T.money_claims(t, None, set()) == [], t
        assert M.arrival_claims(t, TODAY) == [] and M.days_claims(t, TODAY) == [], t
        assert T.judge(t, None, [], T.Journal())[0] == [], t
        assert T.judge(t, None, [], T.Journal(), asked=True, incoming="Как оплатить?")[0] == [], t


# ------------------------------- контрпримеры: замки не ослаблены -------------------------------

def c_locks_hold_inside_question(M):
    """Вопросительный черновик не прячет вымысла: сумма без опоры, приезд без опоры, неверные сутки — причина;
    судья сверки ловит выдуманную сумму и «оплату получили» рядом с вопросом."""
    _s, _u, hand, kb = run(M, "Сколько стоит доставка?", "Куда привезти байк? Доставка будет 300 бат.")
    assert MONEY in hand and "wa:send:1:1" in kb, hand
    _s, _u, hand, _kb = run(M, "Сколько стоит доставка?", "Привезём завтра в 10:00 — куда доставить?")
    assert ARR in hand, hand
    _s, _u, hand, _kb = run(M, "Хочу PCX 160 с 5 по 7 октября", "С 5 по 7 октября — это 3 суток, верно? Куда привезти?")
    assert DAYS in hand, hand
    assert MONEY in T.judge("Where should we bring it? Delivery is 300 baht.", None, [], T.Journal())[0]
    assert T.PAY_WORDS in T.judge("Оплату получили, куда привезти байк?", None, [], T.Journal())[0]


# Порядок — от дешёвых к дорогим: мутант останавливается на первом упавшем случае (поимка), настоящий модуль — все.
CASES = [c_rule7_ends_with_question, c_rules_still_1_to_14, c_question_scope, c_follow_prompt_untouched,
         c_question_checks_pure, c_locks_hold_inside_question, c_reaches_model_cache_and_book,
         c_reaches_model_ru_en, c_only_instruction_changed, c_question_not_punished_twins]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

END14 = "Что клиент уже назвал в переписке (модель, даты, срок), не переспрашивай.\n\nОтвет — РОВНО"
MUTANTS = [
    ("фразы нет", [(" " + QUESTION, "")]),
    ("фраза 15-м правилом", [(" " + QUESTION, ""),
                             (END14, END14.replace("\n\nОтвет", "\n15. " + QUESTION + "\n\nОтвет"))]),
    ("правила 8 и 14 не сильнее", [(" (правила 8 и 14 сильнее)", "")]),
    ("вопросов без счёта", [("ОДИН короткий встречный вопрос о самом нужном",
                             "короткие встречные вопросы обо всём недостающем")]),
    ("вопрос вместо handoff", [("handoff — как выше.", "handoff тогда не нужен.")]),
    ("вопрос вместо ответа",
     [("; что можно сказать по блокам и знаниям — скажи, вопрос — в дополнение, а не вместо", "")]),
    ("наличие — вопросом клиенту", [("(даты или срок, куда доставить,", "(наличие, даты или срок, куда доставить,")]),
    ("деньги без проверки",
     [("            words = K.reason_first(words, K.MONEY_CLAIM_WORDS)   # уже стоящая — вперёд (WADRAFTFIX0310)\n",
       "            pass\n")]),
    ("приезд без проверки", [("            words = K.reason_first(words, K.ARRIVAL_CLAIM_WORDS)\n", "            pass\n")]),
    ("сутки без проверки", [("        return K.reason_first(words, K.DAYS_CLAIM_WORDS)\n", "        return words\n")]),
]


def module(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = MODEL_SRC
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(M, first=False):
    """Случаи на модуле M → [(имя, ошибка)]; first=True — до первого упавшего (мутанту хватает одной поимки)."""
    fails = []
    for c in CASES:
        try:
            c(M)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
            if first:
                break
    return fails


def mutant_kills():
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule_name, edits) in enumerate(MUTANTS, 1):
        mut = src
        for old, new in edits:
            assert mut.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule_name, old[:80])
            mut = mut.replace(old, new)
        out.append((i, rule_name, run_cases(module(mut, "wa_agent_model_mut%d" % i), first=True)))
    return out


def main():
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL " + c.__name__ + " " + f[0][1]) if f else "PASS " + c.__name__)
    print("случаи: %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule_name, fs in mutant_kills():
        killed += bool(fs)
        print("мутант %d «%s»: %s" % (i, rule_name, ("пойман случаем " + fs[0][0]) if fs else "← ВЫЖИЛ"))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
