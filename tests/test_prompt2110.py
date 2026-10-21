#!/usr/bin/env python3
"""PROMPT2110 (пакет 1, слово владельца 21.10; проверка по TB-REVIEW-2110-CLIENT-NEXT п.1): черновик на «какие
варианты на даты» без модели — кодом, без модели и сети.

Живой провал 21.10 14:04Z (черновик 100): клиент назвал даты 25–30 октября без модели и спросил о вариантах; черновик
пересказал клиенту свою проверку срока («5 суток, по сроку подходит … минимум»), цен и наличия не дал и сослался на
«коллегу». Дословной фразы клиента в этом наборе нет (она в базе очереди, базу не открываем) — фраза ниже взята из
вопроса владельцу в разборе («какие варианты на 25–30 октября?») и дополнена парафразами RU/EN и контрпримером.

Что судится (сквозь живой `build` на подделках test_wa_agent_model; модель не зовётся):
  1. инструкция в обоих вариантах: правило 2 — «проверяй молча», правило 7 — «тип и модель», «коллега» только в
     отрицательных примерах (ровно 3 вхождения);
  2. строки блоков кода (цена «считает человек»/«неизвестна», скидка неизвестна, наличие/аренда НЕИЗВЕСТНО, «срок
     истёк», подсказки offer) — без «коллеги» и «менеджера»;
  3. исходная фраза и парафразы: блоки ЦЕНА и НАЛИЧИЕ не строятся (слова цены/наличия нет — детекторы прежние),
     строка журнала «вход модели: цена — о цене не спрашивают · …» ровно одна на вызов, «коллеги» в сообщении нет;
     сутки — из СРОКИ («5 сут.»);
  4. контрпример со словом цены — исход цены уже НЕ «о цене не спрашивают» (детектор цены не ослаблен).
ЧЕСТНЫЙ ПРЕДЕЛ: что ответит сама модель — тестом не проверяется (модели нет)."""

import inspect
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
import wa_agent_model as M                 # noqa: E402
import wa_book_read as B                   # noqa: E402
import wa_offer_tool as O                  # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

LOG = "вход модели: цена — "
NO_ASK = "о цене не спрашивают"
ASK_LIVE = "Здравствуйте! Какие варианты на 25–30 октября?"
PARAPHRASES = ["Хочу арендовать байк с 25 по 30 октября, что у вас есть?",
               "нужен скутер с 1 по 6 ноября, что есть?",
               "Hi, we need a bike from October 25 to 30, what options do you have?",
               "need a scooter Nov 1-6, what do you have?"]
PRICE_ASK = "Сколько стоит аренда с 25 по 30 октября?"


def built(text):
    """Живой `build` (модель не зовётся) → (system, user, строки журнала этого вызова)."""
    w = TM.World(reply=TM.OK_JSON)
    rid = w.put(TM.T0, text)
    n0 = len(w.lines)
    system, user, _info = w.adapter.build(TM.NUM, rid, now=TM.T0 + 100)
    return system, user, w.lines[n0:]


def rule(p, n):
    return next((x for x in p.splitlines() if x.startswith("%d. " % n)), "")


def c_prompt_rules():
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert "проверяй молча" in rule(p, 2) and "«это 5 суток»" in rule(p, 2), rule(p, 2)
        assert "скутер или мотоцикл и какая модель" in rule(p, 7), rule(p, 7)
        assert p.count("коллег") == 3, p.count("коллег")          # 6: «коллега позвонит», «коллегу»; 7: «коллега уточнит»
        assert "уточнишь у менеджера" not in p and "передам коллеге" not in p


def c_block_lines_voice():
    for fn in (K._human, K._unknown, K.quote, K.node_block, M.node_stable, B._avail_unknown, B._rental_unknown,
               B.free_bikes):
        src = inspect.getsource(fn)
        assert "коллег" not in src and "у менеджера" not in src, fn.__name__
    for s in (B.EXPIRED_WORDS, O.ADV_HUMAN, O.ADV_LATER, O.ADV_LIMIT):
        assert "коллег" not in s and "менеджер" not in s, s


def c_live_phrase_and_paraphrases():
    for text in [ASK_LIVE] + PARAPHRASES:
        _system, user, lines = built(text)
        got = [x for x in lines if x.startswith(LOG)]
        assert len(got) == 1 and got[0].startswith(LOG + NO_ASK + " · брони — "), (text, got)
        assert "коллег" not in user, (text, user[-600:])
        assert "\nЦЕНА" not in user and "НАЛИЧИЕ" not in user, (text, user[-600:])
    _s, user, _l = built(ASK_LIVE)
    assert "— 5 сут." in user, user[-600:]


def c_price_word_counterexample():
    _system, user, lines = built(PRICE_ASK)
    got = [x for x in lines if x.startswith(LOG)]
    assert len(got) == 1 and not got[0].startswith(LOG + NO_ASK), got


CASES = [c_prompt_rules, c_block_lines_voice, c_live_phrase_and_paraphrases, c_price_word_counterexample]


def main():
    bad = 0
    for c in CASES:
        try:
            c()
            print("PASS", c.__name__)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", c.__name__, "—", type(e).__name__, str(e)[:400])
    print("ИТОГ %d/%d" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
