#!/usr/bin/env python3
"""Карточка черновика по решениям владельца 05.10 12:35 и 12:39 (WACARDUI0510): «✅ Отправить» на КАЖДОЙ версии
(пометка «нужен человек» видна первой), внизу — как считал агент (why версии модели) и проверка чисел кодом.
Всё на подделках (Bot API, дверь, модель) — мир карточки берётся готовым у `test_wa_card_compact`, сети нет.
Фразы клиентов и суммы выдуманы; №16 — синтетика по числам живого случая (итог 39 352, в тексте 40 000).
USEFUL1310 A5 (решение интегратора К3): штамп «🔎 сверено кодом: число — опора» печатается только при установленной
опоре (чисел нет — штампа нет; об оплате ни слова); оплата кодом не подтверждена, а черновик говорит о деньгах — строка
сверки человеком с предложениями дословно, «Отправить» остаётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон на базе и мутантов)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import test_wa_card_compact as C  # noqa: E402  — мир карточки на подделках

WHY = "клиент спросил цену PCX на 7 суток; 2 800 — из блока «ЦЕНА»; наличие не знаю"
PRICE16 = {"line": "PCX 160: 7 суток, итого 39 352 ฿"}
TEXT16 = "Здравствуйте! За неделю выйдет 40 000 бат, коллега подтвердит наличие."


class ClaimsModel(C.FakeModel):
    """Подделка адаптера с проверкой чисел кодом: claims — как у живого адаптера (`K.money_claims`); checked
    (USEFUL1310 A5) — что о деньгах установлено кодом (`wa_agent_tools.money_check`), если задано."""

    def __init__(self, claims=None, checked=None):
        super().__init__()
        self.claims, self.checked = claims, checked

    def draft(self, number, upto_id):
        out = super().draft(number, upto_id)
        if self.claims is not None:
            out["claims"] = [list(c) for c in self.claims]
        if self.checked is not None:
            out["checked"] = self.checked
        return out


def world(door_open=True, claims=(), checked=None):
    w = C.World(door_open=door_open)
    w.model = ClaimsModel(list(claims) if claims is not None else None, checked)
    w.core.model = w.model
    return w


def kb(p):
    return [b["callback_data"] for row in p["reply_markup"]["inline_keyboard"] for b in row]


# ═══ п.1: «Отправить» на каждой версии ═══════════════════════════════════════════════════

def test_v1_money_reason_has_send_and_mark_first():
    w = world()
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS]))
    t = c1["text"]
    assert "wa:send:1:1" in kb(c1), kb(c1)
    assert kb(c1)[0] == "wa:send:1:1", kb(c1)
    notes = t.split("\n\n")[2]
    assert notes.split("\n")[0] == G.W_HAND, notes                  # пометка — первой строкой под ответом
    assert "«Отправить» открыто — сначала проверьте пометку выше" in t, t


def test_v1_press_reaches_door_and_logs_count():
    w = world()
    w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS])
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, TEXT16)], w.door.sends
    hand = w.core.handoff(1)
    line = [ln for ln in w.lines if "при причинах «нужен человек»" in ln]
    assert len(line) == 1 and (": %d — " % len(hand)) in line[0], (hand, w.lines[-6:])


def test_door_closed_does_not_send():
    w = world(door_open=False)
    c1 = C.card(w.draft("Какой депозит?", extra=[K.MONEY_CLAIM_WORDS]))
    assert "wa:send:1:1" in kb(c1) and G.W_DOOR_CLOSED in c1["text"], (kb(c1), c1["text"])
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [] and w.state()[0] == A.PENDING, (w.door.sends, w.state())


# ═══ п.2: как считал агент и проверка кодом ═════════════════════════════════════════════

def test_why_on_v1_not_on_human_version():
    w = world()
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", why=WHY))
    assert ("💭 Как считал агент: " + WHY) in c1["text"], c1["text"]
    t = c1["text"]
    assert t.index(G.W_HINT) < t.index("💭 Как считал агент"), t           # после ответа и пометок
    w.feed(w.reply(101, "Готовый текст человека."))
    c2 = C.card(w.http.of("sendMessage")[1:])
    assert "версия 2" in c2["text"] and "💭" not in c2["text"], c2["text"]
    assert kb(c2)[0] == "wa:send:1:2", kb(c2)


def test_empty_why_named():
    w = world()
    t = C.card(w.draft("Привет"))["text"]
    assert "💭 агент не объяснил" in t, t


def test_check_ok_line():
    """USEFUL1310 A5, ожидание изменено ПОИМЁННО (было: «🔎 числа сверены с блоком «ЦЕНА»» при пустых claims): ответ
    без чисел («Добрый день! Подскажу.»), опоры не установлено ни одной — штампа нет вовсе, прежней надписи нет."""
    w = world(claims=[])
    t = C.card(w.draft("Сколько стоит PCX на неделю?"))["text"]
    assert "🔎" not in t and "числа сверены" not in t, t
    w = world(claims=[], checked={"nums": [], "pay": False, "said": [], "more": 0})
    t = C.card(w.draft("Сколько стоит PCX на неделю?"))["text"]
    assert "🔎" not in t and G.W_PAY_SAID not in t, t


def test_draft16_synthetic_40000_in_check():
    claims = K.money_claims(TEXT16, PRICE16)
    assert claims == [("сумма", 40000)], claims
    w = world(claims=claims)
    c1 = C.card(w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, extra=[K.MONEY_CLAIM_WORDS],
                        why="итог из блока «ЦЕНА» 39 352, округлил до 40 000"))
    check = [ln for ln in c1["text"].split("\n") if ln.startswith("🔎")]
    assert len(check) == 1 and "сумма 40 000" in check[0], check
    assert "wa:send:1:1" in kb(c1)


def test_client_gets_only_text():
    w = world(claims=[("сумма", 40000)])
    w.draft("Сколько стоит PCX на неделю?", answer=TEXT16, why="СЛУЖЕБНОЕ-ОБЪЯСНЕНИЕ")
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, TEXT16)], w.door.sends
    assert not any("СЛУЖЕБНОЕ" in s[1] or "🔎" in s[1] for s in w.door.sends)


def test_core_extra_by_version():
    w = world(claims=[])
    w.draft("Привет", why=WHY)
    e1 = w.core.card_extra(1, 1, C.ANSWER)
    assert e1 and e1["agent"] and e1["why"] == WHY and e1["claims"] == [], e1
    assert e1["checked"] is None, e1                       # USEFUL1310 A5: адаптер checked не дал — записи нет
    e2 = w.core.card_extra(1, 2, "текст человека")
    assert not (e2 or {}).get("agent"), e2


# ═══ USEFUL1310 A5: штамп — только установленное кодом; сверка человеком при неподтверждённой оплате ═════════════════

TEXT_DUE = "Получили ваше сообщение. Деньги — тоже. К оплате 7790 бат."     # V1 проверяющего X3, m_link дословно
# USEFUL1310 A6 (F4): подтверждение без денег («Получили ваше сообщение.») адаптер больше не цитирует — запись та, что
# адаптер даёт на этот текст (ожидание изменено поимённо: было ещё «Получили ваше сообщение.»)
# USEFUL1310 A7 (W1, решение К3): подтверждение с объектом адаптер снова цитирует, как на A5 — запись та, что адаптер
# даёт на этот текст (ожидание изменено поимённо обратно)
CHK_DUE = {"nums": [[7790, ["итог аренды кода"]], [2800, ["блок «ЦЕНА»"]]], "pay": False,
           "said": ["Получили ваше сообщение.", "Деньги — тоже."], "more": 0}


def _check_lines(t):
    return [ln for ln in t.split("\n") if ln.startswith("🔎") or ln.startswith("⚠️ черновик")]


def test_a5_stamp_names_numbers_and_backing_not_payment():
    """Штамп называет, КАКИЕ числа и С КАКОЙ опорой (итог аренды кода, блок «ЦЕНА»); об оплате — ни слова."""
    w = world(claims=[], checked=dict(CHK_DUE, said=[]))
    t = C.card(w.draft("Сколько в целом?", answer=TEXT_DUE))["text"]
    stamp = [ln for ln in t.split("\n") if ln.startswith("🔎")]
    assert stamp == ["🔎 сверено кодом: 7 790 — итог аренды кода; 2 800 — блок «ЦЕНА»"], stamp
    assert "оплат" not in stamp[0].lower() and "paid" not in stamp[0].lower(), stamp
    assert G.W_PAY_SAID not in t, t


def test_a5_unpaid_money_said_line_send_kept():
    """Оплата кодом не подтверждена, черновик говорит о деньгах — строка сверки и сами предложения дословно; кнопка
    «Отправить» на месте и шлёт ответ дословно (строка — сверка человеком, не отказ)."""
    w = world(claims=[], checked=CHK_DUE)
    c1 = C.card(w.draft("Сколько в целом?", answer=TEXT_DUE))
    lines = _check_lines(c1["text"])
    assert lines[0] == G.W_PAY_SAID + " «Получили ваше сообщение.» · «Деньги — тоже.»", lines
    assert lines[1].startswith("🔎 сверено кодом: 7 790"), lines
    assert kb(c1)[0] == "wa:send:1:1", kb(c1)
    w.feed(w.press("wa:send:1:1", 101))
    assert w.door.sends == [(C.NUM, TEXT_DUE)], w.door.sends
    assert not any("⚠️" in s[1] or "🔎" in s[1] for s in w.door.sends)
    e1 = w.core.card_extra(1, 1, TEXT_DUE)
    assert e1["checked"] == CHK_DUE, e1                    # запись ядра — та, что дал адаптер


def test_a5_paid_or_no_money_no_said_line():
    """Оплата подтверждена кодом — строки сверки нет (даже если предложения о деньгах есть); предложений нет — нет."""
    for chk in (dict(CHK_DUE, pay=True), dict(CHK_DUE, said=[])):
        w = world(claims=[], checked=chk)
        t = C.card(w.draft("Сколько в целом?", answer=TEXT_DUE))["text"]
        assert G.W_PAY_SAID not in t, (chk, t)


def test_a5_more_said_counted_and_bad_kept():
    """Предложений больше двух — названо число скрытых; число без опоры — строка «без опоры» рядом (USEFUL1310 A6, F5:
    ожидание изменено ПОИМЁННО — было «…без опоры в блоке «ЦЕНА»»)."""
    chk = dict(CHK_DUE, nums=[], more=3)
    line = G.card_check([["сумма", 40000]], chk)
    assert line.split("\n")[0].endswith(G.W_PAY_MORE % 3), line
    assert line.split("\n")[1] == "🔎 проверка кодом — без опоры: сумма 40 000", line
    assert G.card_check(None, None) == G.W_CHECK_NONE                     # код не проверял — как было
    assert G.card_check([], None) == ""                                   # записи нет (черновик старше) — штампа нет


# ═══ USEFUL1310 A6: одна формулировка опоры (F5); версия по пояснению — строка сверки и штамп её текста (F3) ═══════

def test_a6_f5_one_backing_wording():
    """F5: штамп и строка «без опоры» говорят одной формулировкой — «сверено кодом: число — опора» и «без опоры: число»;
    «в блоке «ЦЕНА»» (опора пути сверки шире блока) нет ни в одной строке."""
    line = G.card_check([["сумма", 3000]], {"nums": [[7790, ["итог аренды кода"]]], "pay": False, "said": [],
                                           "more": 0})
    assert line == "🔎 сверено кодом: 7 790 — итог аренды кода\n🔎 проверка кодом — без опоры: сумма 3 000", line
    assert "в блоке «ЦЕНА»" not in G.W_CHECK_BAD and "без опоры" in G.W_CHECK_BAD, G.W_CHECK_BAD


HINT_MONEY = "Получили вашу бронь и депозит, ждём вас завтра."   # V1 проверяющего X3 (m_noun) — в версии по пояснению


def test_a6_f3_hint_version_gets_said_line():
    """F3: версия по пояснению сотрудника (модель переписала черновик, ver 2, пути без сверки) — на её карточке строка
    сверки с её предложениями дословно (оплата кодом не подтверждена: сверки нет); строки «💭» нет; запись ядра — то,
    что дал адаптер на ЕЁ текст. Версия человека (правка полным текстом) низа не получает, как было."""
    import json
    import test_wa_hint_rule as H

    class MoneyHint(H.HintCall):
        def __call__(self, system, user):
            if H.ASK_MARK in user:
                self.calls.append((system, user))
                return (json.dumps({"text": HINT_MONEY, "lang": "ru", "handoff": [], "why": "пояснение"},
                                   ensure_ascii=False), {"model": "fake", "in": 10, "out": 5})
            return super().__call__(system, user)
    w = H.started()
    money = MoneyHint()
    money.calls = w.call.calls
    w.adapter.call = w.call = money
    w.explain()
    card2 = w.card_text(2)
    assert HINT_MONEY in card2 and (G.W_PAY_SAID + " «" + HINT_MONEY + "»") in card2, card2
    assert "💭" not in card2, card2
    e2 = w.core.card_extra(1, 2, HINT_MONEY)
    assert e2["hint_check"] and not e2["agent"] and e2["claims"] == [], e2
    assert e2["checked"] == {"nums": [], "pay": False, "said": [HINT_MONEY], "more": 0}, e2
    assert G.card_agent(e2) == (None, G.W_PAY_SAID + " «" + HINT_MONEY + "»"), G.card_agent(e2)
    # без денег в тексте версии — сказать нечего: низа нет (карточка версии 2 — как до A6)
    assert G.card_agent(dict(e2, checked={"nums": [], "pay": False, "said": [], "more": 0})) is None
    w2 = world()
    w2.draft("Привет", why=WHY)
    assert not (w2.core.card_extra(1, 2, "текст человека") or {}).get("hint_check")


# ═══ п.3: правило why и предел ══════════════════════════════════════════════════════════

def test_prompt_rule_and_parse_limit():
    import json
    import wa_agent_model as M
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert "13. Поле \"why\"" in p and "блок «ЦЕНА», наши прежние слова" in p, p[-600:]
    got = M.parse_reply(json.dumps({"text": "ok", "lang": "ru", "handoff": [], "why": "w" * 900}))
    assert len(got["why"]) == 600, len(got["why"])


# ═══ п.4: окно ══════════════════════════════════════════════════════════════════════════

def test_block_fits_and_cut_announced():
    why, check = "Ж" * 600, G.W_CHECK_OK
    texts = G.card_texts("T", "Ответ.", "N" * 3300, "D" * 50, agent=(why, check))
    last = texts[-1]
    assert len(last) <= G.CARD_ROOM and all(len(x) <= G.TG_TEXT_MAX for x in texts), [len(x) for x in texts]
    assert "Ответ." in "".join(texts) and check in last and "…обрезано " in last, last[-200:]
    n = int(last.split("…обрезано ")[1].split(" ")[0])
    assert last.count("Ж") + n == len(why), (last.count("Ж"), n)
    # короткий why — целиком, без пометки обрезки
    ok = G.card_texts("T", "Ответ.", "N" * 100, "", agent=("коротко", check))
    assert "💭 Как считал агент: коротко" in ok[-1] and "обрезано" not in ok[-1], ok


def test_long_answer_not_cut_with_block():
    answer = "Ответ клиенту без сокращений. " * 128 + "КОНЕЦ"
    texts = G.card_texts("T", answer, "N" * 100, "", agent=("w" * 600, G.W_CHECK_OK))
    assert answer in "".join(texts[:-1]).replace("T" + G.W_ANSWER_LEAD, "", 1), [len(x) for x in texts]
    assert "💭 Как считал агент: " + "w" * 600 in texts[-1], texts[-1][-200:]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL %s %s: %s" % (name, type(e).__name__, str(e)[:300]))
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
