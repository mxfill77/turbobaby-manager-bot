#!/usr/bin/env python3
"""Деньги в черновике модели без опоры → причина «нужен человек» (WAMONEYCHECK0310). После parse_reply текст
черновика проверяется кодом: процент рядом со словом предоплаты, депозита или скидки и сумма в батах, которой нет в
блоке «ЦЕНА» этого вызова, дают причину «денежное утверждение без опоры»; на версии 1 «Отправить» нет. Число, равное
сумме двери из «ЦЕНА», — не причина; ответ без денег — как раньше. Текст ответа не правится.
Всё на подделках: модель, мост (узлы, парк, дверь цены), Bot API и дверь отправки — из test_wa_agent_model; сети нет,
модели нет. Фразы клиентов и ответы модели выдуманы.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent_knowledge as K  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — адаптер модели на подделках

CLAIM = "денежное утверждение без опоры"
ACT_CLAIM = "деньги в ответе: агент назвал процент или сумму без опоры — проверьте и исправьте"
# дверь подделки: 7 сут., 400 ฿ в сутки, итого 2 800 ฿, депозит 3 000 ฿ (TM.FakeBridge.door)
PRICE_Q = "Сколько стоит PCX 160 с 5 по 12 ноября?"
PLAIN_Q = "Здравствуйте, хочу взять PCX 160 на неделю"      # кода «нужен человек» нет, блока «ЦЕНА» нет
MANY_Q = "Свободен ли байк? Скидку дадите? Какой депозит? Оплатил переводом. Был штраф."


def reply(text, handoff=(), lang="ru"):
    return json.dumps({"text": text, "lang": lang, "handoff": list(handoff), "why": "вопрос"}, ensure_ascii=False)


def run(q, text, lang="ru"):
    """Фраза клиента + ответ подделки модели → (мир, строка черновика, причины, карточка с кнопками)."""
    w = TM.World(reply=reply(text, lang=lang))
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    return w, d[0], hand, cards[-1]


def actions(text):
    return [ln[2:] for ln in text.split("\n") if ln.startswith("• ")]


def price_of(q=PRICE_Q):
    """Исход цены этого вызова — тот, что адаптер положил в блок «ЦЕНА»."""
    w = TM.World()
    w.ask(q)
    return w.adapter.last["info"]["price"]


def kinds(claims):
    return sorted(k for k, _ in claims)


# ═══ проверки Штаба (п.4) ════════════════════════════════════════════════════════════════

def test_prepay_30_without_client_question():
    assert K.handoff(PLAIN_Q) == [], K.handoff(PLAIN_Q)                 # клиент о деньгах не спрашивал
    text = "Добрый день! Для брони нужна предоплата 30%, остальное — при получении."
    w, d, hand, card = run(PLAIN_Q, text)
    assert hand == [CLAIM], hand
    assert d[3] == text, d[3]                                             # текст ответа не тронут
    assert TM.buttons(card) == ["wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)   # «Отправить» на версии 1 нет
    assert actions(card["text"]) == [ACT_CLAIM], card["text"]
    w.press("wa:send:1:1", 101)                                           # старая/подделанная кнопка
    assert w.door.sends == [] and w.drafts()[0][1] == TM.A.PENDING, w.door.sends
    # английский ответ — то же
    _w, _d, hand_en, _c = run("Hi, I want a PCX 160 for a week", "Sure! To book it we need a 30% deposit.",
                              lang="en")
    assert hand_en == [CLAIM], hand_en


def test_prepay_100():
    _w, d, hand, card = run(PLAIN_Q, "Бронь — только при 100% предоплате.")
    assert hand == [CLAIM] and "wa:send:1:1" not in TM.buttons(card), (hand, TM.buttons(card))
    for t in ("Бронь — только при 100% предоплате.", "100% предоплата обязательна.",
              "We take 100% prepayment upfront.", "Нужна предоплата: 100 процентов.", "скидка 10%",
              "10% off for a month", "Залог — 50% от стоимости."):
        assert kinds(K.money_claims(t)) == ["процент"], (t, K.money_claims(t))


def test_sum_equals_door_total_no_reason():
    text = "PCX 160 с 5 по 12 ноября — 2 800 ฿ за 7 суток."
    w, d, hand, card = run(PRICE_Q, text)
    assert "ЦЕНА: " in w.call.calls[0][1] and "итого 2 800 ฿" in w.call.calls[0][1]
    assert hand == [] and d[4] is None, d
    assert TM.buttons(card) == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)
    price = price_of()
    for t in ("Итого 2800 бат за неделю.", "Total THB 2,800 for 7 days.", "За неделю 2.8k baht.",
              "400 ฿ в сутки, за неделю 2 800 ฿.", "Депозит 3 000 бат.", "депозит 3k ฿", "депозит 3 тыс. бат",
              "Итого 2" + chr(0xA0) + "800 ฿.", "Итого 2" + chr(0x202F) + "800 THB."):
        assert K.money_claims(t, price) == [], (t, K.money_claims(t, price))


def test_sum_not_from_price_block():
    _w, _d, hand, card = run(PRICE_Q, "PCX 160 на эти даты — 3 500 ฿.")
    assert hand == [CLAIM] and "wa:send:1:1" not in TM.buttons(card), (hand, TM.buttons(card))
    _w, _d, hand2, _c = run(PLAIN_Q, "Депозит за PCX 160 — 5 000 бат.")         # блока «ЦЕНА» нет вовсе
    assert hand2 == [CLAIM], hand2
    price = price_of()
    for t, want in (("Total THB 3,500.", [3500]), ("от 1 500 до 2 800 ฿", [1500]), ("1 500–2 800 бат", [1500]),
                    ("за две недели 5 600 ฿", [5600]), ("скидка 500 бат", [500])):
        got = [v for k, v in K.money_claims(t, price) if k == "сумма"]
        assert got == want, (t, got)


def test_no_money_no_reason():
    for text in ("Добрый день! Подскажите, на какие даты нужен байк?",
                 "Депозит и предоплату уточнит коллега и вернётся с точной суммой."):
        _w, d, hand, card = run(PLAIN_Q, text)
        assert hand == [] and d[4] is None, (text, d)
        assert TM.buttons(card)[0] == "wa:send:1:1" and "НУЖЕН" not in card["text"], card["text"]


# ═══ ветки правки ════════════════════════════════════════════════════════════════════════

def test_pct_other_sentence_not_claim():
    for t in ("Скидки сейчас нет. Шлем выдаём в 100% случаев.", "Доставка 100% бесплатно.",
              "PCX 160, 2026 года выпуска, на 7 суток.", "Drop-off is free, the bike is 100% insured.",
              "Номер брони 7 400, шлем в подарок."):
        assert K.money_claims(t) == [], (t, K.money_claims(t))


def test_claim_first_visible_with_many_reasons():
    _w, _d, hand, card = run(MANY_Q, "Скидка 10% на месяц, остальное уточнит коллега.")
    assert hand[0] == CLAIM and len(hand) == 6, hand
    acts = actions(card["text"])
    assert acts[0] == ACT_CLAIM and acts[-1] == "ещё 3 — в подробностях", acts


def test_journal_numbers_only():
    text = "Для брони нужна предоплата 30%, депозит 5 000 ฿."
    w, _d, hand, _c = run(PLAIN_Q, text)
    assert hand == [CLAIM], hand
    got = [ln for ln in w.lines if "без опоры" in ln]
    assert got == ["модель: денежных утверждений без опоры 2 (процентов 1, сумм 1) — причина «нужен человек»"], got
    assert not any("30%" in ln or "5 000" in ln or text in ln for ln in w.lines), w.lines


def test_fix_v2_opens_send():
    w, _d, _hand, _card = run(PLAIN_Q, "Для брони нужна предоплата 30%.")
    w.reply(101, "Коллега уточнит условия брони и напишет.")
    card2 = w.http.of("sendMessage")[-1]
    assert TM.buttons(card2) == ["wa:send:1:2", "wa:fix:1:2", "wa:no:1:2"], TM.buttons(card2)
    w.press("wa:send:1:2", 102)
    assert w.door.sends == [(TM.NUM, "Коллега уточнит условия брони и напишет.")], w.door.sends


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
