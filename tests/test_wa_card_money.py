#!/usr/bin/env python3
"""Денежные действия компактной карточки не утверждают фактов, которых в сообщении нет (WACARDMONEY0310).
Оплата: заявлена совершённой — «проверьте поступление»; вопрос или упоминание — «вопрос об оплате»; признак неясен —
нейтрально. Возврат денег — свой ярлык; к депозиту — только когда депозит назван. Триггер «нужен человек» тот же:
объединение слов денежных ярлыков равно прежнему. Всё на подделках (Bot API, дверь, модель), сети нет.
Фразы клиентов выдуманы.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent_knowledge as K  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — адаптер модели на подделках
import test_wa_card_compact as C  # noqa: E402  — мир карточки на подделках

ACT_DONE = "оплата: проверьте поступление"
ACT_ASK = "вопрос об оплате: ответьте сами"
ACT_UNCLEAR = "оплата: прочтите сообщение клиента и решите сами"
ACT_DEPOSIT = "депозит: сверьте сумму и условия возврата"
ACT_REFUND = "возврат: уточните, что возвращать — депозит, предоплату или аренду"

# альтернативы выражения R_MONEY на b6abc45 (WACARDCOMPACT0310) — прежнее объединение слов, 40 штук
PREV_UNION = frozenset(
    "поврежд|царап|вмятин|разбил|сломал|авари|\\bдтп|\\bупал|штраф|депозит|залог|верн[иуё]те|"
    "\\bспор(?!т)|оспор|претенз|жалоб|оплат|оплач|переве[лд]|перевёл|перевод(?!чик)|\\bчек\\b|"
    "refund|damage|scratch|\\bdent|crash|accident|\\bbroke|\\bfined\\b|penalt|deposit|dispute|"
    "complain|\\bpaid\\b|payment|\\bpay\\b|transfer|receipt|invoice".split("|"))


def words(q):
    return [r["words"] for r in K.handoff(q)]


def card_of(q, extra=()):
    w = C.World(door_open=False)
    return C.card(w.draft(q, extra=extra))["text"]


def no_fact(t):
    return "поступлен" not in t.lower()


# ═══ проверки Штаба (п.6) ════════════════════════════════════════════════════════════════

def test_pay_question_by_transfer():
    q = "можно оплатить переводом?"
    assert words(q) == ["вопрос об оплате"], words(q)
    t = card_of(q)
    assert C.actions(t) == [ACT_ASK] and no_fact(t), t


def test_pay_thanks_understood():
    q = "спасибо, всё понял об оплате"
    assert words(q) == ["вопрос об оплате"], words(q)
    t = card_of(q)
    assert C.actions(t) == [ACT_ASK] and no_fact(t), t


def test_pay_done_transfer_receipt():
    q = "перевёл 5000, вот чек"
    assert words(q) == [K.MONEY_WORDS[K.MONEY_PAYMENT]], words(q)
    t = card_of(q)
    assert C.actions(t) == [ACT_DONE], t


def test_refund_deposit_named():
    q = "верните депозит"
    assert words(q) == ["депозит"], words(q)
    assert C.actions(card_of(q)) == [ACT_DEPOSIT], card_of(q)


def test_refund_prepayment():
    q = "верните предоплату"
    assert words(q) == ["возврат денег"], words(q)
    t = card_of(q)
    assert C.actions(t) == [ACT_REFUND] and no_fact(t) and ACT_DEPOSIT not in t, t


def test_refund_money():
    for q in ("верните деньги", "refund please"):
        assert words(q) == ["возврат денег"], (q, words(q))
        t = card_of(q)
        assert C.actions(t) == [ACT_REFUND] and ACT_DEPOSIT not in t, t
    assert words("refund my deposit") == ["депозит"]
    assert words("верните залог") == ["депозит"]


# ═══ ветки правки ════════════════════════════════════════════════════════════════════════

def test_pay_negated_is_unclear():
    q = "ещё не оплатил, куда перевести?"
    assert words(q) == ["оплата"], words(q)
    t = card_of(q)
    assert C.actions(t) == [ACT_UNCLEAR] and no_fact(t), t


def test_pay_li_is_unclear():
    q = "аренда оплачена ли?"
    assert words(q) == ["оплата"], words(q)
    assert C.actions(card_of(q)) == [ACT_UNCLEAR]


def test_proof_in_question_is_unclear():
    q = "нужен чек об оплате?"
    assert words(q) == ["оплата"], words(q)
    assert C.actions(card_of(q)) == [ACT_UNCLEAR]
    assert words("скрин оплаты отправил") == [K.MONEY_WORDS[K.MONEY_PAYMENT]]       # документ без вопроса — факт
    assert words("I paid by transfer") == [K.MONEY_WORDS[K.MONEY_PAYMENT]]


def test_model_reason_never_states_payment():
    # кода о деньгах нет, модель пишет «клиент уже оплатил» — пересказ, факт не берётся
    t = card_of("Привет, сколько стоит PCX на неделю?", extra=["клиент уже оплатил аренду"])
    assert C.actions(t) == [ACT_UNCLEAR] and no_fact(t), t
    # код назвал вопрос об оплате — пересказ модели о той же оплате отпадает (одна семья)
    got = K.merge_reasons(["вопрос об оплате"], ["клиент уже оплатил аренду", "клиент спрашивает об оплате"])
    assert got == ["вопрос об оплате"], got


def test_union_equals_previous_by_set():
    trig = dict(K._TEXT_RULES)[K.R_MONEY]
    subs = set()
    for _key, _words, rx in K.MONEY_LABELS:
        subs |= set(rx.pattern.split("|"))
    assert len(PREV_UNION) == 40 and subs == PREV_UNION == set(trig.pattern.split("|")), subs ^ PREV_UNION
    for t in ("можно оплатить переводом?", "спасибо, всё понял об оплате", "перевёл 5000, вот чек", "верните депозит",
              "верните предоплату", "верните деньги", "привет", "хочу спортбайк", "переводчик нужен", "нужен чек?"):
        hit = bool(trig.search(t))
        assert hit == bool(K.money_labels(t)) == bool(K.money_labels(t, trusted=False)), t
        assert hit == (K.R_MONEY in [r["reason"] for r in K.handoff(t)]), t


def test_prompt_words_no_fact():
    want = {"можно оплатить переводом?": "вопрос об оплате", "спасибо, всё понял об оплате": "вопрос об оплате",
            "перевёл 5000, вот чек": "оплата со слов клиента — поступление не проверено",
            "верните депозит": "депозит", "верните предоплату": "возврат денег", "верните деньги": "возврат денег"}
    for q, w in want.items():
        line = K.prompt_parts(None, K.handoff(q), [])["handoff"]
        assert line.startswith("НУЖЕН ЧЕЛОВЕК: %s. " % w), (q, line)
    # настоящий адаптер модели: в user-промпт уходит тот же ярлык
    w = TM.World()
    w.ask("можно оплатить переводом?")
    user = w.call.calls[0][1]
    assert "НУЖЕН ЧЕЛОВЕК: вопрос об оплате." in user and "поступлен" not in user, user[-400:]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
