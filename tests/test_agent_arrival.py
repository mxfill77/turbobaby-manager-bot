# -*- coding: utf-8 -*-
"""WATIMECLAIMB0510: агент не обещает срок и приезд без опоры (№18 v1 05.10).

Повод — черновик №18 v1 (12:43) пообещал приезд сотрудника с байком «в течение часа-двух»: это продолжение НАШЕЙ строки
с телефона 12:22, а не факт; «завтра» в окне — 0 из 97 строк, блоков дат нет, проверка денег класс не ловит, правило 12
(«наши прежние слова обязывают») ошибку усиливало. Теперь: (1) проверка кодом — день или время приезда, доставки, выдачи
или прихода сотрудника не из дат блоков этого вызова — причина `K.ARRIVAL_CLAIM_WORDS` первой строкой, в обоих путях
черновика; «Отправить» не запирается (решение владельца 05.10 12:39); (2) оговорка в правиле 12: относительный срок
нашей прежней строки отсчитывался от её ЧЧ:ММ.

Случаи — сквозь живой адаптер, ядро и руки Telegram на подделках test_wa_agent_model (модель, мост, Bot API, дверь
отправки; сети и модели нет). №18 — синтетикой: наша строка за 21 мин до черновика с «час-два», черновик с тем же
сроком. Мутанты: правка исходника wa_agent_model.py в памяти, мутант обязан уронить хотя бы один случай.
WA_AGENT_SRC=<каталог> подменяет модули (прогон на базе)."""

import datetime
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

import wa_agent_knowledge as K             # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tg as G                    # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(os.path.dirname(os.path.abspath(M_REAL.__file__)), "wa_agent_model.py")
# литералом: на базе константы нет — случай падает своей проверкой, а не импортом всего набора
ARR = "срок или приезд без опоры на даты — проверьте день и время"
MONEY = K.MONEY_CLAIM_WORDS
TODAY = datetime.date(2026, 9, 21)         # «сегодня» мира TM (T0 = 2026-09-21 21:13 по Пхукету)
CLAUSE = ("Относительный срок из нашей прежней строки («через час», «час-два», «сегодня») отсчитывался от её ЧЧ:ММ — "
          "как новый не повторяй. День и время приезда, доставки или выдачи называй только из фактов этого вызова или "
          "наших последних слов о том же; иначе скажи, что уточнишь у сотрудника.")
OUR_1222 = "Сотрудник подъедет к вам с байком в течение часа-двух, удобно?"     # форма №18 #88 — выдумана
DRAFT_18 = "Отлично! Сотрудник подъедет к вам с байком в течение часа-двух."      # форма №18 v1 — выдумана
HAND_M = ["клиент ждёт байк"]              # причина модели: «в конец» мутанта отличается от «первой»


def reply(text, lang="ru", handoff=None):
    return json.dumps({"text": text, "lang": lang, "handoff": list(handoff or []), "why": "срок"},
                      ensure_ascii=False)


def run(M, q, text, lang="ru", handoff=None, ours=None, tools=False):
    """Наша строка с телефона (если есть) за 21 мин, фраза клиента + ответ подделки модели сквозь адаптер M →
    (промпт user, причины, кнопки карточки, текст карточки, журнал)."""
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        w = TM.World(reply=reply(text, lang, handoff))
    finally:
        TM.WM = keep
    if tools:
        w.adapter.tools = {}               # путь со сверкой (AGENTLOOPA0310): T.run, итог — обычный JSON
    if ours:
        w.put(TM.T0 - 21 * 60, ours, kind="echo")      # эхо с телефона — «мы»; ставит паузу, снимаем её
        w.core.tick(TM.T0 - 100)
        w.core.resume(TM.NUM, 1, "тест")
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    user = w.call.calls[0][1]
    return user, hand, TM.buttons(cards[-1]), cards[-1]["text"], w.lines


# ------------------------------- случаи задания (п.3) -------------------------------

def c_18_synthetic_caught(M):
    """№18: наша строка 12:22 с «час-два», черновик через 21 мин с тем же сроком — причина первой; «Отправить» есть;
    на карточке пометка первым пунктом; в журнале — только числа."""
    user, hand, kb, card, lines = run(M, "ок", DRAFT_18, handoff=HAND_M, ours=OUR_1222)
    assert OUR_1222 in user and "СРОКИ" not in user, user[-500:]          # наша строка видна модели, дат нет
    assert hand[:1] == [ARR] and HAND_M[0] in hand, hand
    assert "wa:send:1:1" in kb, kb                                        # не запирается (решение 12:39)
    notes = card.split(G.W_HAND, 1)[1]
    assert notes.lstrip("\n").startswith("• " + ARR), notes[:200]
    log = [x for x in lines if "срок или приезд без опоры" in x]
    assert len(log) == 1 and "часа-двух" not in log[0] and "Сотрудник" not in log[0], log


def c_18_tools_path_caught(M):
    """Тот же №18 путём со сверкой (`_draft_tools`): причина первой."""
    _u, hand, kb, _c, _l = run(M, "ок", DRAFT_18, handoff=HAND_M, ours=OUR_1222, tools=True)
    assert hand[:1] == [ARR], hand
    assert "wa:send:1:1" in kb, kb


def c_no_term_clean(M):
    """Без срока — причины нет: «сотрудник уточнит» сроком не является."""
    _u, hand, kb, _c, lines = run(M, "ок", "Хорошо, передам сотруднику — он уточнит и напишет вам.", ours=OUR_1222)
    assert ARR not in hand and hand == [], hand
    assert kb[0] == "wa:send:1:1", kb
    assert not [x for x in lines if "срок или приезд без опоры" in x], lines
    for text in ("Доставка по Пхукету бесплатно от 3 суток.", "Доставки и заборы — до 17:30.",
                 "Коллега вернётся к вам с ответом.", "My colleague will come back to you within an hour."):
        assert M.arrival_claims(text, TODAY) == [], (text, M.arrival_claims(text, TODAY))


def c_term_with_dates_block_clean(M):
    """Срок с опорой на блок дат — причины нет: клиент назвал 21–23 сентября (блок «СРОКИ»), «сегодня» = 21.09."""
    q = "Хочу PCX 160 с 21 по 23 сентября, привезёте сегодня?"
    user, hand, kb, _c, _l = run(M, q, "Да, сегодня привезём PCX 160, точное время уточнит сотрудник.")
    assert "с 21.09 по 23.09" in user, user[-400:]
    assert ARR not in hand, hand
    _u, hand2, _kb, _c2, _l2 = run(M, q, "Да, 21 сентября привезём PCX 160.")
    assert ARR not in hand2, hand2
    # блок есть, но день не его (№18 на 2ce75b54: «СРОКИ» без сегодня и завтра) — причина
    _u, hand3, kb3, _c3, _l3 = run(M, "Хочу PCX 160 с 25 по 27 сентября", "Привезём сегодня, через час.",
                                   handoff=HAND_M)
    assert hand3[:1] == [ARR] and "wa:send:1:1" in kb3, hand3


def c_english_caught(M):
    """По-английски — причина: within an hour, tomorrow at 10 am."""
    _u, hand, kb, _c, _l = run(M, "Hi, can you bring the bike?", "Sure! Our staff will bring the bike within an hour.",
                               lang="en", handoff=HAND_M)
    assert hand[:1] == [ARR] and "wa:send:1:1" in kb, hand
    _u, hand2, _kb, _c2, _l2 = run(M, "Hi, can you bring the bike?", "We will deliver it tomorrow at 10 am.",
                                   lang="en")
    assert hand2[:1] == [ARR], hand2


def c_rule12_clause(M):
    """Оговорка в правиле 12 обоих вариантов инструкции — в той же строке, после прежнего текста правила."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        line = next((x for x in p.splitlines() if x.startswith("12. НАШИ ПРЕЖНИЕ СЛОВА ОБЯЗЫВАЮТ.")), "")
        assert line.endswith("нового числа из него не выводи. " + CLAUSE), line[-400:]


def c_money_first_then_arrival(M):
    """Деньги и срок вместе (форма №17): деньги — первой, срок — второй строкой; обе видны на карточке."""
    _u, hand, _kb, card, _l = run(M, "ок", "Сотрудник подъедет с байком в течение часа-двух, депозит 5 000 бат.",
                                  ours=OUR_1222)
    assert hand[:2] == [MONEY, ARR], hand
    assert ARR in card.split(G.W_HAND, 1)[1], card


def c_unit_marks(M):
    """Разбор меток: позитивы RU/EN и опора дня."""
    for text in ("Через час привезём байк.", "Курьер будет у вас час-два.", "Сегодня привезём.",
                 "Our driver will arrive in 30 minutes.", "Сотрудник приедет в 15:00.", "Привезём в пятницу."):
        assert M.arrival_claims(text, TODAY), text
    assert M.arrival_claims("Сегодня привезём.", TODAY, {TODAY}) == [], "день с опорой"
    assert M.arrival_claims("Привезём завтра.", TODAY, {TODAY}) == [("завтра", "2026-09-22")]
    assert M.call_dates({"terms": [{"ds": TODAY, "de": TODAY + datetime.timedelta(days=2)}]}) == {
        TODAY, TODAY + datetime.timedelta(days=2)}


CASES = [c_18_synthetic_caught, c_18_tools_path_caught, c_no_term_clean, c_term_with_dates_block_clean,
         c_english_caught, c_rule12_clause, c_money_first_then_arrival, c_unit_marks]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("проверка выключена",
     "        if bad:\n            self.log(\"модель: срок или приезд",
     "        if False:\n            self.log(\"модель: срок или приезд"),
    ("reason_first → в конец",
     "            words = K.reason_first(words, K.ARRIVAL_CLAIM_WORDS)\n",
     "            words = list(words) + [K.ARRIVAL_CLAIM_WORDS]\n"),
    ("оговорка удалена", " " + CLAUSE, ""),
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
        if src.count(old) != 1:                                      # база: правки нет — мутант не применим
            out.append((i, rule, None))
            continue
        out.append((i, rule, run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i))))
    return out


def main():
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL %s %s" % (c.__name__, f[0][1])) if f else ("PASS " + c.__name__))
    print("ИТОГ %d/%d" % (len(CASES) - len(fails), len(CASES)))
    killed = 0
    for i, rule, fs in mutant_kills():
        if fs is None:
            print("мутант %d «%s»: не применим (правки в исходнике нет)" % (i, rule))
            continue
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
