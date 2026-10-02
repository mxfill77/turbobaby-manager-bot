#!/usr/bin/env python3
"""Пять остатков черновика WA (WADRAFTFIX0310).
2 — после ожиданий (история, цена, брони, чтение узлов) время снимается заново: возраст, причина, журнал, блоки и
    префикс кэша судятся по нему — в черновике и напоминании.
3 — узел без снимка, когда чтение пробовали и оно не удалось, — причина «знания устарели»; без настроенного чтения —
    как было.
4 — документ под отрицанием («чека нет», «нет чека», «без чека», no receipt) фактом оплаты не считается.
5 — возврат рядом с другими деньгами (аренда, предоплата, «деньги за», rent) остаётся возвратом рядом с депозитом.
6 — денежная причина первой всегда: уже стоящая переносится вперёд.
Всё на подделках: модель, мост (узлы, парк, дверь цены), часы, Bot API и дверь отправки — из test_wa_agent_model;
сети нет, модели нет. Тексты узлов и фразы клиентов выдуманы.

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
import wa_agent_model as WM  # noqa: E402
import test_wa_agent_model as TM  # noqa: E402  — адаптер модели на подделках
import test_wa_know_fresh as F  # noqa: E402  — узлы, мост, хелперы знаний
import test_wa_card_money as CM  # noqa: E402  — карточка и денежные ярлыки

T0 = TM.T0
STALE, ACT_STALE = F.STALE, F.ACT_STALE
CLAIM = "денежное утверждение без опоры"
ACT_CLAIM = "деньги в ответе: агент назвал процент или сумму без опоры — проверьте и исправьте"
PAY_FACT = K.MONEY_WORDS[K.MONEY_PAYMENT]


class SlowBridge(F.Bridge):
    """Мост, который отвечает отказом через `wait` секунд: каждый отказ двигает часы вперёд."""

    def __init__(self, clk, wait=60):
        super().__init__()
        self.clk, self.wait = clk, wait

    def read_doc(self, name):
        if self.down:
            self.reads.append(name)
            self.clk[0] += self.wait
            raise TimeoutError()
        return super().read_doc(name)


def slow_world(cache=None, reply=F.REPLY):
    """Снимок взят в t0; часы на t0+1790; мост лёг, каждый отказ — 60 с. → (мир, часы, мост)."""
    clk = [T0]
    br = SlowBridge(clk)
    kn = K.Knowledge(br.read_doc)
    kn.refresh(T0)
    br.down, br.reads = True, []
    clk[0] = T0 + 1790
    w = TM.World(reply=reply)
    w.adapter.knowledge, w.adapter.clock, w.adapter.cache = kn, (lambda: clk[0]), cache
    return w, clk, br


def drafted(w, q=F.Q):
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    system, user = w.call.calls[-1]
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    return (system if isinstance(system, str) else "\n".join(b["text"] for b in system)) + "\n" + user, hand, cards[-1]


def line_1910(w):
    got = F.know_lines(w)
    assert len(got) == 1, got
    for n in K.NODES:
        assert ("%s — не прочитан (мост не отвечает (TimeoutError)), снимок %d симв., sha16 %s, возраст 1910 с > "
                "предела 1800 с — НЕИЗВЕСТНО, текста в промпте нет" % (n, len(F.TEXT[n]), F.SHA[n])) in got[0], got
    return got[0]


# ═══ п.2 — время после ожиданий: снимок 1790 с, два отказа по 60 с → 1910 с ═══════════════════════

def test_clock_after_waits_draft_no_cache():
    w, clk, br = slow_world()
    prompt, hand, card = drafted(w)
    assert br.reads == ["faq", "business_rules"] and clk[0] == T0 + 1910, (br.reads, clk)
    F.no_node_text(prompt, "промпт")
    for n in K.NODES:
        assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" % n) in prompt, n
    assert "НУЖЕН ЧЕЛОВЕК: " + STALE in prompt and hand == [STALE], hand
    assert TM.buttons(card) == ["wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)      # «Отправить» на версии 1 нет
    assert F.actions(card["text"]) == [ACT_STALE], card["text"]
    line_1910(w)


def test_clock_after_waits_cache_on():
    w, clk, _br = slow_world(cache="1h")
    system, user, info = w.adapter.build(TM.NUM, 0)
    pre = system[1]["text"]
    F.no_node_text(system[0]["text"] + pre + user, "кэш")
    for n in K.NODES:
        assert ("УЗЕЛ %s: НЕИЗВЕСТНО: снимок старше 30 мин" % n) in pre, pre[:400]
        assert ("%s — НЕИЗВЕСТНО: снимок старше 30 мин, мост не отвечает (TimeoutError)" % n) in user, user[:500]
    assert "TimeoutError" not in pre, pre[:400]                                     # причина — не в префиксе
    assert [r["words"] for r in info["code_reasons"]][:1] == [STALE], info["code_reasons"]
    line_1910(w)
    assert clk[0] == T0 + 1910, clk


def test_clock_after_waits_followup():
    for cache in (None, "1h"):
        w, clk, _br = slow_world(cache=cache)
        system, user, _info = w.adapter.build_followup(TM.NUM, 0)
        text = (system if isinstance(system, str) else "\n".join(b["text"] for b in system)) + "\n" + user
        F.no_node_text(text, "напоминание")
        assert "УЗЕЛ faq: НЕИЗВЕСТНО: снимок старше 30 мин" in text, (cache, text[-600:])
        line_1910(w)


def test_fixed_now_kept():
    # время, заданное вызывающим (пробы и тесты), — как есть: часы адаптера не зовутся вместо него
    w, clk, _br = slow_world()
    _s, user, info = w.adapter.build(TM.NUM, 0, now=T0 + 1790)
    assert "снят 29 мин назад" in user and info["code_reasons"] == [], info["code_reasons"]
    assert "возраст 1790 с" in F.know_lines(w)[0], F.know_lines(w)


# ═══ п.3 — узел без снимка: чтение пробовали и оно не удалось → причина ═════════════════════════

def test_unread_failed_gets_reason():
    br = F.Bridge()
    br.down = True
    w, prompt, hand, card = F.draft_at(K.Knowledge(br.read_doc), T0)
    assert "УЗЕЛ faq: НЕИЗВЕСТНО — не прочитан (мост не отвечает (TimeoutError))" in prompt, prompt[-600:]
    assert "НУЖЕН ЧЕЛОВЕК: " + STALE in prompt and hand == [STALE], hand
    assert TM.buttons(card) == ["wa:fix:1:1", "wa:no:1:1"], TM.buttons(card)
    assert F.actions(card["text"]) == [ACT_STALE], card["text"]
    got = K.stale_reasons([K.Knowledge(br.read_doc).refresh(T0)[n] for n in K.NODES], T0)
    assert [r["words"] for r in got] == [STALE] and "снимка нет, чтение не удалось: faq, business_rules" in got[0]["why"]
    # один узел прочитан, другой нет — та же причина, одна
    one = K.Knowledge(lambda n: {"ok": True, "text": F.TEXT[n]} if n == "faq" else {"ok": False, "error": "x"})
    got = K.stale_reasons(list(one.refresh(T0).values()), T0)
    assert len(got) == 1 and got[0]["why"] == "снимка нет, чтение не удалось: business_rules", got


def test_unread_not_configured_as_before():
    ad = WM.ModelAdapter(TM.World().qpath, None, clock=lambda: T0)                  # read_doc не задан
    assert getattr(ad.knowledge, "configured", False) is False
    snap = ad.knowledge.refresh(T0)
    assert snap["faq"]["why"] == "мост ответил отказом (моста нет)", snap["faq"]      # слова те же, что раньше
    assert K.stale_reasons(list(snap.values()), T0) == []
    ad2 = WM.ModelAdapter(TM.World().qpath, None, clock=lambda: T0)
    w, prompt, hand, card = F.draft_at(ad2.knowledge, T0)
    assert "УЗЕЛ faq: НЕИЗВЕСТНО — не прочитан (мост ответил отказом (моста нет))" in prompt and hand == [], hand
    assert TM.buttons(card)[0] == "wa:send:1:1", TM.buttons(card)
    # узлы не из Knowledge (простые словари) — без причины, как раньше
    assert K.stale_reasons([{"name": "faq", "read": False, "call": K.CALL_FAILED}], T0) == []


# ═══ п.4 — документ под отрицанием фактом не считается ════════════════════════════════════════

def test_receipt_neg_after():
    q = "Я ещё не оплатил, чека нет"
    assert CM.words(q) == ["оплата"], CM.words(q)
    t = CM.card_of(q)
    assert CM.C.actions(t) == [CM.ACT_UNCLEAR] and CM.no_fact(t), t
    assert CM.words("оплата будет завтра, чека пока нет") == ["оплата"]


def test_receipt_neg_before():
    for q in ("оплата будет завтра, нет чека", "оплачу наличными, без чека", "payment tomorrow, no receipt yet",
              "I will pay tomorrow, without receipt"):
        assert CM.words(q) == ["оплата"], (q, CM.words(q))
        assert CM.no_fact(CM.card_of(q)), q


def test_receipt_fact_kept():
    for q in ("вот чек", "скинул чек", "оплатил, вот чек", "перевёл 5000, вот чек", "here is the payment receipt"):
        assert CM.words(q) == [PAY_FACT], (q, CM.words(q))
    assert CM.C.actions(CM.card_of("вот чек")) == [CM.ACT_DONE]


# ═══ п.5 — возврат рядом с другими деньгами ═════════════════════════════════════════════════

def test_refund_with_other_money():
    q = "Верните депозит и деньги за аренду"
    assert CM.words(q) == ["депозит", "возврат денег"], CM.words(q)
    assert CM.C.actions(CM.card_of(q)) == [CM.ACT_DEPOSIT, CM.ACT_REFUND], CM.card_of(q)
    for q in ("верните депозит и аренду за 3 дня", "верните депозит и деньги за неиспользованные дни",
              "refund the deposit and the rent", "верните депозит и аванс", "refund deposit and prepaid days"):
        assert CM.words(q) == ["депозит", "возврат денег"], (q, CM.words(q))


def test_refund_deposit_only_kept():
    for q in ("верните депозит", "верните залог", "refund my deposit", "когда вернёте депозит? верните депозит"):
        assert CM.words(q) == ["депозит"], (q, CM.words(q))
    assert CM.C.actions(CM.card_of("верните депозит")) == [CM.ACT_DEPOSIT]


# ═══ п.6 — денежная причина первой всегда ═════════════════════════════════════════════════

MANY_Q = "Свободен ли байк? Скидку дадите? Какой депозит? Был штраф."
PREPAY = "Добрый день! Для брони нужна предоплата 30%."


def money_run(handoff, q=MANY_Q):
    w = TM.World(reply=json.dumps({"text": PREPAY, "lang": "ru", "handoff": list(handoff), "why": "вопрос"},
                                  ensure_ascii=False))
    _p, hand, card = drafted(w, q)
    return hand, card


def test_money_reason_moved_first():
    hand, card = money_run([CLAIM])                                               # модель уже назвала её
    assert hand[0] == CLAIM and hand.count(CLAIM) == 1 and len(hand) >= 4, hand
    assert F.actions(card["text"])[0] == ACT_CLAIM, card["text"]
    hand2, _c = money_run([])                                                    # не назвала — как раньше
    assert hand2[0] == CLAIM and hand2[1:] == hand[1:], (hand, hand2)
    assert K.reason_first(["a", CLAIM, "b"], CLAIM) == [CLAIM, "a", "b"]


def test_money_reason_norm_dedup():
    hand, _card = money_run(["Денежное утверждение без опоры."])
    assert hand[0] == CLAIM and sum(1 for h in hand if "утверждение без опоры" in h.lower()) == 1, hand
    # денег в тексте нет — причину модели код вперёд не двигает
    w = TM.World(reply=json.dumps({"text": "Добрый день!", "lang": "ru", "handoff": [CLAIM], "why": "вопрос"},
                                  ensure_ascii=False))
    _p, hand3, _c = drafted(w, MANY_Q)
    assert hand3[-1] == CLAIM and hand3[0] != CLAIM, hand3


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
