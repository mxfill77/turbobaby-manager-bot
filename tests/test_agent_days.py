# -*- coding: utf-8 -*-
"""WADAYS0410: сутки в черновике = дата возврата минус дата выдачи («с 5 по 7» — двое суток).

Повод — черновик №10 в «Агентах» 04.10: «5–7 октября — 3 суток», «5–8 — 4». Код считает сутки каждому диапазону дат
клиента (блок «СРОКИ» в промпте), правило 10 SYSTEM_PROMPT велит брать число суток только из «СРОКИ» и «ЦЕНА», а
сверка черновика ставит причину «срок: агент посчитал сутки не так — проверьте», если у диапазона дат названо не то
число; «Отправить» на версии 1 закрыто (тот же замок, что у денег без опоры).

Случаи — сквозь живой адаптер и ядро на подделках test_wa_agent_model (модель, мост, Bot API, дверь отправки; сети и
модели нет). Мутанты: правка исходника wa_agent_model.py в памяти, мутант обязан уронить хотя бы один случай."""

import datetime
import json
import os
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
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
DAYS = K.DAYS_CLAIM_WORDS
TODAY = datetime.date(2026, 9, 21)         # «сегодня» мира TM (T0 = 2026-09-21 UTC, Пхукет)


def reply(text):
    return json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "сроки"}, ensure_ascii=False)


def run(M, q, text):
    """Фраза клиента + ответ подделки модели сквозь адаптер M → (промпт user, причины, кнопки карточки)."""
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        w = TM.World(reply=reply(text))
        w.ask(q)
    finally:
        TM.WM = keep
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    user = w.call.calls[0][1]
    return user, hand, TM.buttons(cards[-1])


def days_of(M, text, today=TODAY):
    return [r["days"] for r in M.find_ranges(text, today)]


# ------------------------------- случаи задания (п.4) -------------------------------

def c_5_to_7_october(M):
    """«с 5 по 7 октября» — двое суток: в блоке «СРОКИ» и в счёте кода."""
    assert days_of(M, "с 5 по 7 октября") == [2], days_of(M, "с 5 по 7 октября")
    user, hand, kb = run(M, "Хочу PCX 160 с 5 по 7 октября", "Добрый день! С 5 по 7 октября — двое суток, PCX 160 "
                                                             "уточню у коллег.")
    assert "СРОКИ (" in user and "с 05.10 по 07.10 — 2 сут." in user, user[-400:]
    assert hand == [] and kb[0] == "wa:send:1:1", (hand, kb)


def c_5_8_october(M):
    """«5–8 октября» — трое суток."""
    assert days_of(M, "5–8 октября") == [3], days_of(M, "5–8 октября")
    user, hand, _kb = run(M, "Нужен байк 5–8 октября", "Добрый день! 5–8 октября — это 3 суток.")
    assert "с 05.10 по 08.10 — 3 сут." in user and hand == [], (user[-300:], hand)


def c_from_5_to_7_october_en(M):
    """from 5 to 7 October — two days."""
    assert days_of(M, "from 5 to 7 October") == [2], days_of(M, "from 5 to 7 October")
    user, hand, _kb = run(M, "Hi, need a bike from 5 to 7 October", "Hi! From 5 to 7 October is 2 days.")
    assert "с 05.10 по 07.10 — 2 сут." in user and hand == [], (user[-300:], hand)


def c_30_sep_to_2_oct(M):
    """«с 30 сентября по 2 октября» — двое суток, через границу месяца, при любом «сегодня»."""
    for today in (TODAY, datetime.date(2026, 10, 1), datetime.date(2026, 12, 31)):
        assert days_of(M, "с 30 сентября по 2 октября", today) == [2], (today, days_of(M, "с 30 сентября по 2 "
                                                                                       "октября", today))
    user, hand, _kb = run(M, "Можно с 30 сентября по 2 октября?", "С 30 сентября по 2 октября — 2 суток, уточню.")
    assert "с 30.09 по 02.10 — 2 сут." in user and hand == [], (user[-300:], hand)


def c_3_days_5_to_7_draft_3_caught(M):
    """«на 3 дня с 5 по 7»: блок — 2; черновик с 3 ловится, «Отправить» на версии 1 закрыто."""
    q = "Хочу PCX 160 на 3 дня с 5 по 7"
    user, hand, kb = run(M, q, "Да, на 3 дня с 5 по 7 можно, коллега уточнит цену.")
    assert "с 5 по 7 (месяц не назван) — 2 сут." in user, user[-300:]
    assert hand == [DAYS] and "wa:send:1:1" not in kb, (hand, kb)
    _u, hand2, kb2 = run(M, q, "Аренда на 3 дня — коллега уточнит цену.")          # число без дат рядом
    assert hand2 == [DAYS] and "wa:send:1:1" not in kb2, (hand2, kb2)


def c_3_days_5_to_7_draft_2_clean(M):
    """Близнец: тот же вопрос, черновик с 2 — причин нет, «Отправить» открыто."""
    _u, hand, kb = run(M, "Хочу PCX 160 на 3 дня с 5 по 7", "С 5 по 7 — это двое суток, коллега уточнит цену.")
    assert hand == [] and kb[0] == "wa:send:1:1", (hand, kb)
    _u, hand2, _kb = run(M, "Хочу PCX 160 на 3 дня с 5 по 7 октября",
                         "Вы написали 3 дня, но с 5 по 7 октября — двое суток. Коллега уточнит цену.")
    assert hand2 == [], hand2                                   # мягкая поправка клиента — не причина


def c_no_dates_no_block_no_check(M):
    """Дат нет — ни блока «СРОКИ», ни сверки: число суток без дат не судится."""
    user, hand, kb = run(M, "Хочу PCX 160 на неделю", "Конечно, на 3 дня или неделю — коллега уточнит цену.")
    assert "СРОКИ" not in user and hand == [] and kb[0] == "wa:send:1:1", (user[-300:], hand, kb)
    assert M.days_claims("На 3 дня можно.", TODAY) == [], M.days_claims("На 3 дня можно.", TODAY)


def c_owner_draft_10(M):
    """Живой повод: «5–7 октября — 3 суток, 5–8 — 4» ловится; близнец с 2 и 3 чист."""
    _u, hand, kb = run(M, "Хочу PCX 160 на 5–7 или 5–8 октября",
                       "PCX 160: 5–7 октября — 3 суток, 5–8 октября — 4 суток. Цену уточнит коллега.")
    assert hand == [DAYS] and "wa:send:1:1" not in kb, (hand, kb)
    _u, hand2, _kb = run(M, "Хочу PCX 160 на 5–7 или 5–8 октября",
                         "PCX 160: 5–7 октября — 2 суток, 5–8 октября — 3 суток. Цену уточнит коллега.")
    assert hand2 == [], hand2


def c_prompt_rule_and_card(M):
    """Правило 10 в SYSTEM_PROMPT (и в варианте с бронями); карточка называет действие причины."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert "10. Число суток аренды называй ТОЛЬКО из блоков «СРОКИ» и «ЦЕНА»" in p, p[-600:]
        assert "мягко поправь числом из «СРОКИ»" in p, p[-400:]
    assert K.word_categories(DAYS) == [K.R_DAYS_CLAIM], K.word_categories(DAYS)


CASES = [c_5_to_7_october, c_5_8_october, c_from_5_to_7_october_en, c_30_sep_to_2_oct,
         c_3_days_5_to_7_draft_3_caught, c_3_days_5_to_7_draft_2_clean, c_no_dates_no_block_no_check,
         c_owner_draft_10, c_prompt_rule_and_card]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("счёт включительно (+1)", "    return (de - ds).days\n", "    return (de - ds).days + 1\n"),
    ("сверка выключена", "        if not bad:\n            return words\n", "        if True:\n            return words\n"),
    ("блока нет в промпте", "            blocks.append(terms_text)\n", "            pass\n"),
]


def module(src, name):
    mod = types.ModuleType(name)
    mod.__file__ = MODEL_SRC
    exec(compile(src, name + ".py", "exec"), mod.__dict__)        # noqa: S102 — мутант собственного исходника
    return mod


def run_cases(M):
    fails = []
    for c in CASES:
        try:
            c(M)
        except Exception as e:                                       # noqa: BLE001 — падение мутанта = поимка
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:200])))
    return fails


def mutant_kills():
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        out.append((i, rule, run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i))))
    return out


def main():
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL " + f[0][1]) if f else "PASS", c.__name__)
    print("случаи: %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule, fs in mutant_kills():
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
