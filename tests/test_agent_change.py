# -*- coding: utf-8 -*-
"""WASDACHA0510: агент называет итог точно и предлагает сдачу (запись 05.10.2026-2), проверка денег её не ломает.

Повод — №16 v1 (05.10 12:32): итог 39 352 ฿, в ответе 40 000 ฿, сдачи нет; владелец 12:35 — «он должен был предложить
сдачу». Верный ответ со сдачей 648 ฿ получал «деньги без опоры»: 40 000 и 648 в блоке «ЦЕНА» не стоят. Теперь:
(1) `K.change_backed` — в предложении со словом сдачи сумма M с опорой, если черновик называет сумму с опорой T и сумму
N, где N − M = T и N > T; тогда и N с опорой (оба пути черновика: `K.money_claims` и `T.money_claims`); (2) клиент в окне
назвал сумму N больше итога T — строка блока «ЦЕНА» «клиент назвал N ฿: итог T ฿, сдача M ฿ (05.10.2026-2); отдаётся в
конце аренды с залогом (03.10.2026-1 п. 2)»; (3) в `draft()` — та же проверка роли о сдаче, что у `_draft_tools`;
(4) правило 15 инструкции.

Случаи — сквозь живой адаптер, ядро и руки Telegram на подделках test_wa_agent_model (модель, мост, дверь цены, Bot API,
дверь отправки; сети и модели нет). №16 — синтетикой: клиент спросил цену PCX 160 на 8 суток (дверь: итог 39 352 ฿) и
написал «Дам 40 000 наличными». Мутанты: правка исходника wa_agent_model.py или wa_agent_knowledge.py в памяти, мутант
обязан уронить хотя бы один случай. WA_AGENT_SRC=<каталог> подменяет модули."""

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

import wa_agent_knowledge as K_REAL        # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tools as T                 # noqa: E402
import wa_agent_tg as G                    # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(os.path.dirname(os.path.abspath(M_REAL.__file__)), "wa_agent_model.py")
KNOW_SRC = os.path.join(os.path.dirname(os.path.abspath(K_REAL.__file__)), "wa_agent_knowledge.py")
# литералами: на базе констант нет — случай падает своей проверкой, а не импортом всего набора
MONEY = "денежное утверждение без опоры"
ROLE = "денежная роль не сходится с кассой"
LINE_16 = ("клиент назвал 40 000 ฿: итог 39 352 ฿, сдача 648 ฿ (05.10.2026-2); отдаётся в конце аренды с залогом "
           "(03.10.2026-1 п. 2)")
PRICE_16 = ("ЦЕНА: 2026-11-05, 2026-11-13 — PCX 160: 8 сут., 4 919 ฿ в сутки, итого 39 352 ฿ за срок; скидка за срок 0%; "
            "депозит 3 000 ฿.")
LOG_ROLE = "модель: сдача без «в конце, с возвратом залога» 1 — причина «нужен человек»"
RULE15 = ("15. Строка блока «ЦЕНА» «клиент назвал N ฿: итог T ฿, сдача M ฿» — итог называй точно, числом T, без "
          "округления до суммы клиента; сдачу называй числом M из этой строки и словами строки: отдаётся в конце аренды "
          "с залогом. Строки нет — сдачу не считай и не называй.")

# №16 синтетикой (выдумано, форма живого входа): вопрос о цене и следом сумма наличными, нашей реплики между ними нет
ASK_PRICE = "Сколько стоит PCX 160 с 5 по 13 ноября?"
ASK_CASH = "Дам 40 000 наличными"
GOOD = "итог 39 352 ฿, с 40 000 ฿ сдача 648 ฿, вернём в конце аренды с залогом"
ONE_SUM = "Итого 40 000 ฿."
CHANGE_650 = "итог 39 352 ฿, с 40 000 ฿ сдача 650 ฿, вернём в конце аренды с залогом"
NO_END = "итог 39 352 ฿, с 40 000 ฿ сдача 648 ฿"
TOTAL_ONLY = "итог 39 352 ฿ за 8 суток, скидка за срок 0%, депозит 3 000 ฿"


def door_16(unit, ds, de):
    """Дверь цены №16 (живой формат QuotePrice.js): PCX 160 на 8 суток, итог 39 352 ฿."""
    return {"ok": True, "days": 8, "day_price": 4919, "total": 39352, "deposit": 3000,
            "season": {"label": "P3"}, "model": "PCX 160",
            "text": "PCX 160 | дней: 8, стоимость: 39352 (скидка за срок 0%, 4919 в день), депозит: 3000 бат"}


def reply(text):
    return json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "итог из блока «ЦЕНА»"}, ensure_ascii=False)


def run(M, answer, before=(ASK_PRICE,), q=ASK_CASH, conv=(), tools=False):
    """Переписка conv (клиент «in» и наши «echo» по минуте), реплики клиента before и q без нашей между ними + ответ
    подделки модели сквозь адаптер M → (блок «ЦЕНА», причины, кнопки карточки, текст карточки, журнал)."""
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        w = TM.World(reply=reply(answer))
    finally:
        TM.WM = keep
    w.adapter.door = door_16
    if tools:
        w.adapter.tools = {}               # путь со сверкой (AGENTLOOPA0310): T.run, итог — обычный JSON
    if conv:
        for i, (kind, t) in enumerate(conv):
            w.put(TM.T0 - 3000 + i * 60, t, kind=kind)
        w.core.tick(TM.T0 - 100)           # эхо ставит паузу — снимаем её «Продолжить»
        w.core.resume(TM.NUM, 1, "тест")
    for i, t in enumerate(before):
        w.put(TM.T0 - 30 + i, t)
    w.ask(q)
    d = w.drafts()
    assert len(d) == 1, d
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    user = w.call.calls[0][1]
    blk = user.split("ЦЕНА: ", 1)[1].split("\n\n", 1)[0] if "ЦЕНА: " in user else ""
    return "ЦЕНА: " + blk if blk else "", hand, TM.buttons(cards[-1]), cards[-1]["text"], w.lines


def both(M, answer, **kw):
    """Оба пути черновика: без сверки и со сверкой → [(путь, блок, причины, кнопки, карточка, журнал)]."""
    return [(tools,) + run(M, answer, tools=tools, **kw) for tools in (False, True)]


# ------------------------------- случаи задания (п.5) -------------------------------

def c_16_change_line(M):
    """№16: итог 39 352, клиент «дам 40 000 наличными» — строка сдачи 648 в блоке «ЦЕНА» после строки цены, в обоих
    путях; строка цены прежняя, 40 000 и 648 в неё не идут. Сумма клиента до нашей реплики (окно `ctx`) — та же строка."""
    for tools, blk, _h, _kb, _c, _l in both(M, GOOD):
        assert blk == PRICE_16 + "\n" + LINE_16, (tools, blk)
    blk, _h, _kb, _c, _l = run(M, GOOD, before=(), q=ASK_PRICE,
                               conv=[("in", "Дам 40 000 наличными, если что"), ("echo", "Хорошо, посчитаю.")])
    assert blk == PRICE_16 + "\n" + LINE_16, blk


def c_16_good_answer_clean(M):
    """«итог 39 352 ฿, с 40 000 ฿ сдача 648 ฿, вернём в конце аренды с залогом» — без причин в обоих путях; «Отправить»
    первой кнопкой, текст ответа на карточке прежний."""
    for tools, blk, hand, kb, card, lines in both(M, GOOD):
        assert LINE_16 in blk, (tools, blk)
        assert hand == [], (tools, hand)
        assert kb[0] == "wa:send:1:1", (tools, kb)
        assert GOOD in card, (tools, card[:400])
        assert LOG_ROLE not in lines, (tools, lines)


def c_16_one_sum_caught(M):
    """«Итого 40 000 ฿.» одной суммой (живой №16 v1) при той же строке сдачи — причина «деньги без опоры» в обоих путях:
    сумма клиента опорой сама не становится."""
    for tools, blk, hand, kb, _c, _l in both(M, ONE_SUM):
        assert LINE_16 in blk, (tools, blk)
        assert MONEY in hand, (tools, hand)
        assert kb[0] == "wa:send:1:1", (tools, kb)


def c_16_change_650_caught(M):
    """Сдача 650 вместо 648 (неверная разность) — причина «деньги без опоры» в обоих путях; роль сдачи верна — её
    причины нет."""
    for tools, blk, hand, _kb, _c, _l in both(M, CHANGE_650):
        assert LINE_16 in blk, (tools, blk)
        assert MONEY in hand, (tools, hand)
        assert ROLE not in hand, (tools, hand)


def c_16_change_no_end_caught(M):
    """Сдача без «в конце» — причина роли в обоих путях (в `draft()` — та же проверка, что у `_draft_tools`); деньги с
    опорой — их причины нет; в журнале пути без сверки — только число."""
    for tools, blk, hand, kb, _c, lines in both(M, NO_END):
        assert LINE_16 in blk, (tools, blk)
        assert ROLE in hand, (tools, hand)
        assert MONEY not in hand, (tools, hand)
        assert kb[0] == "wa:send:1:1", (tools, kb)
        if not tools:
            assert hand[0] == ROLE, hand
            assert [x for x in lines if x.startswith("модель: сдача")] == [LOG_ROLE], lines


def c_no_client_sum_no_line(M):
    """Клиент суммы не называл — строки нет; суммы меньше итога и наша сумма — строки нет; близнец с суммой
    клиента — строка есть. Ответ одним итогом — без причин."""
    blk, hand, kb, _c, _l = run(M, TOTAL_ONLY, before=(), q=ASK_PRICE)
    assert blk == PRICE_16, blk
    assert hand == [] and kb[0] == "wa:send:1:1", (hand, kb)
    blk, _h, _kb, _c, _l = run(M, TOTAL_ONLY, q="Дам 30 000 наличными")
    assert blk == PRICE_16, blk
    blk, _h, _kb, _c, _l = run(M, TOTAL_ONLY, before=(), q=ASK_PRICE,
                               conv=[("in", "Здравствуйте"), ("echo", "Можно наличными, 40 000 ฿ разменяем.")])
    assert blk == PRICE_16, blk
    blk, _h, _kb, _c, _l = run(M, TOTAL_ONLY)
    assert blk == PRICE_16 + "\n" + LINE_16, blk


def c_send_not_locked(M):
    """«Отправить» не заперто: при причине роли сдачи кнопка отправки версии 1 стоит первой в обоих путях."""
    for tools, _b, hand, kb, card, _l in both(M, NO_END):
        assert ROLE in hand, (tools, hand)
        assert kb == ["wa:send:1:1", "wa:fix:1:1", "wa:no:1:1"], (tools, kb)
        assert "• " + ROLE in card.split(G.W_HAND, 1)[1], (tools, card[-600:])


def c_rule15_both_prompts(M):
    """Правило 15 одной строкой в обоих вариантах инструкции, сразу за 14 и перед пустой строкой."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        lines = p.splitlines()
        i = next(k for k, x in enumerate(lines) if x.startswith("14. "))
        assert lines[i + 1] == RULE15, lines[i + 1]
        assert lines[i + 2] == "", lines[i + 2]
        assert p.count("15. ") == 1, p.count("15. ")


def c_unit_change_backed(M):
    """Разбор: N − M = T и N > T — опора у M и N; неверная разность, N без M, M без T, «сдача байка» — пусто; оба
    пути судят одинаково (бат и число без валюты у сверки)."""
    K = M.K
    cb = K.change_backed
    assert cb(GOOD, {39352}) == {648, 40000}
    assert cb(CHANGE_650, {39352}) == set()
    assert cb("итог 39 352 ฿, с 40 000 ฿", {39352}) == set()                      # N без M
    assert cb("с 40 000 ฿ сдача 648 ฿, вернём в конце аренды", {39352}) == set()   # M без T
    assert cb(GOOD, set()) == set()                                                 # T без опоры
    assert cb("Total 39,352 baht. From 40,000 baht your change is 648 baht.", {39352}) == {648, 40000}
    assert cb("итог 39 352 ฿, 40 000 ฿ и 648 ฿ при сдаче байка", {39352}) == set()
    price = {"line": PRICE_16[len("ЦЕНА: "):]}
    assert K.money_claims(GOOD, price) == [], K.money_claims(GOOD, price)
    assert K.money_claims(CHANGE_650, price) == [("сумма", 40000), ("сумма", 650)], K.money_claims(CHANGE_650, price)
    assert K.money_claims(ONE_SUM, price) == [("сумма", 40000)]
    assert T.money_claims(GOOD, price, {39352}) == []
    assert T.money_claims("итог 39 352, с 40 000 сдача 648, в конце аренды", price, {39352}) == []
    assert T.money_claims("итог 39 352, с 40 000 сдача 650", price, {39352}) == [("число", 40000), ("число", 650)]
    assert T.change_role(NO_END) and not T.change_role(GOOD)


def c_unit_cash_change(M):
    """Сумма клиента: в батах — везде, без валюты — со словом оплаты наличными; первая больше итога, новые первыми;
    вариантов несколько, числа нет, суммы больше итога нет — строки нет."""
    q = {"outcome": "number", "total": 39352, "line": "x"}
    got = M.cash_change(q, ["Дам 40 000 наличными"])
    assert got == {"client": 40000, "total": 39352, "change": 648, "line": LINE_16}, got
    assert M.cash_change(q, ["Возьму, 40 000 ฿ хватит?"])["change"] == 648
    assert M.cash_change(q, ["Дам 45 000 наличными", "Дам 40 000 наличными"])["client"] == 45000
    assert M.cash_change(q, ["Дам 30 000 наличными"]) is None
    assert M.cash_change(q, ["40000"]) is None                                     # без валюты и без слова оплаты
    assert M.cash_change(q, ["Дам за PCX 160 наличными"]) is None
    assert M.cash_change(None, ["Дам 40 000 наличными"]) is None
    assert M.cash_change({"outcome": "human", "total": None, "line": "x"}, ["Дам 40 000 наличными"]) is None
    two = {"outcome": "number", "total": 39352, "quotes": [q, dict(q, total=20000)], "line": "x"}
    assert M.cash_change(two, ["Дам 40 000 наличными"]) is None
    assert M.client_sums("Дам 40 000 наличными") == [40000]
    assert M.client_sums("I can pay 40,000 cash") == [40000]


CASES = [c_16_change_line, c_16_good_answer_clean, c_16_one_sum_caught, c_16_change_650_caught,
         c_16_change_no_end_caught, c_no_client_sum_no_line, c_send_not_locked, c_rule15_both_prompts,
         c_unit_change_backed, c_unit_cash_change]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("разность не проверяется", "knowledge", "if n > t and n - m == t:", "if n > t:"),
    ("строка не строится", "model",
     'blocks.append(parts["price"] + ("\\n" + change["line"] if change else ""))', 'blocks.append(parts["price"])'),
    ("проверка роли в draft() выключена", "model",
     '        words = self._change_check(got["text"], words)          # роль сдачи, как у _draft_tools (WASDACHA0510)\n',
     ""),
]


def module(msrc, name, ksrc=None):
    """Модуль адаптера из исходника; ksrc — мутант знаний: адаптер импортирует его вместо настоящего."""
    saved = sys.modules.get("wa_agent_knowledge")
    try:
        if ksrc is not None:
            kmod = types.ModuleType("wa_agent_knowledge")
            kmod.__file__ = KNOW_SRC
            exec(compile(ksrc, name + "_k.py", "exec"), kmod.__dict__)       # noqa: S102 — мутант исходника
            sys.modules["wa_agent_knowledge"] = kmod
        mod = types.ModuleType(name)
        mod.__file__ = MODEL_SRC
        exec(compile(msrc, name + ".py", "exec"), mod.__dict__)              # noqa: S102 — мутант исходника
        return mod
    finally:
        sys.modules["wa_agent_knowledge"] = saved


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
        msrc = fh.read()
    with open(KNOW_SRC, encoding="utf-8") as fh:
        ksrc = fh.read()
    out = []
    for i, (rule, where, old, new) in enumerate(MUTANTS, 1):
        src = ksrc if where == "knowledge" else msrc
        if src.count(old) != 1:                                      # база: правки нет — мутант не применим
            out.append((i, rule, None))
            continue
        name = "wa_agent_model_mut%d" % i
        if where == "knowledge":
            mod = module(msrc, name, ksrc.replace(old, new))
        else:
            mod = module(msrc.replace(old, new), name)
        out.append((i, rule, run_cases(mod)))
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
