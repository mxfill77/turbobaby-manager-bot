# -*- coding: utf-8 -*-
"""WAPRICECTX0410: вопрос о цене без модели или дат — варианты из переписки; скидка за срок — в строке цены всегда.

Повод — владелец 05.10, черновик №11: агент не учёл контекст — «сколько будет стоить» относилось и к ADV 350 на 5 дней
из нашего ответа (клиент готов рассмотреть 5 дней); скидка за срок прописывается всегда, даже 0. Код до правки
(26c0b565 … c682ec66): `_price` брал модель и даты только из блока «КЛИЕНТ СЕЙЧАС», строка quote скидки не несла.

Теперь: вопрос о цене без модели или двух дат дополняется парами «модель + срок» из последних сообщений диалога (наших
и клиента), до трёх, каждая — своя дверь цены с прежними воротами; срок числом суток — от начала из переписки, начала
нет — числа нет, агент спрашивает даты. Строка цены несёт скидку за срок из ответа двери (поле text, QuotePrice.js),
0% тоже; её нет — «скидка неизвестна» и причина человеку. Правило 11 SYSTEM_PROMPT: в ответе о цене скидка за срок
называется всегда. Процент скидки, названной дверью, — с опорой; «5% off» без неё ловится.

WAPAIRS0410 сузил пары до слов клиента (наши сроки, даты и модели пар не дают): в пяти случаях, где пара шла из
нашего ответа, слова перенесены в реплику клиента, а прежняя форма осталась близнецом «пары нет»; c_owner_adv350_5_days
теперь даёт одну дверь — по паре клиента (поимённо — артефакт WAPAIRS0410).

Случаи — сквозь живой адаптер и ядро на подделках test_wa_agent_model (модель, мост, Bot API, дверь отправки; сети и
модели нет). Дверь цены — подделка с кривой скидки самоката из QuotePrice.js (`quoteDurationDiscount_`). Мутанты:
правка исходника wa_agent_model.py или wa_agent_knowledge.py в памяти; мутант обязан уронить хотя бы один случай."""

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

import wa_agent_knowledge as K_REAL        # noqa: E402
import wa_agent_model as M_REAL            # noqa: E402
import wa_agent_tools as T                 # noqa: E402
import wa_book_read as B                   # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

K = K_REAL
MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
KNOW_SRC = os.path.join(ROOT, "wa_agent_knowledge.py")
UNITS = ["ADV 350 1111", "PCX 160 1234", "XMAX 300 4321", "NMAX 155 7777"]
BASE = {"ADV 350": 1000, "PCX 160": 400, "XMAX 300": 800, "NMAX 155": 500}
SEND = "wa:send:1:1"
RULE11 = "11. В ответе о цене скидку за срок называй ВСЕГДА — числом из блока «ЦЕНА», и когда она 0%"


def scooter_discount(d):
    """Кривая «scooter» QuotePrice.js `quoteDurationDiscount_` (ADV/PCX/XMAX/NMAX — самокаты)."""
    if d <= 5:
        return 0.0
    if d == 6:
        return 0.05
    if d <= 13:
        return 0.06 + (d - 7) * 0.01
    if d <= 30:
        return 0.18 + (d - 14) * 0.010625
    return 0.35


class PriceBridge:
    """Парк и дверь цены живого формата: text со «скидка за срок N%» (with_text=False — ответ без text)."""

    def __init__(self, with_text=True):
        self.doors, self.fleets, self.with_text = [], 0, with_text

    def fleet(self):
        self.fleets += 1
        return {"ok": True, "bikes": [{"name": n} for n in UNITS]}

    def door(self, unit, ds, de):
        self.doors.append((unit, ds, de))
        model = B.model_key(unit)
        days = (datetime.date.fromisoformat(de) - datetime.date.fromisoformat(ds)).days
        disc = scooter_discount(days)
        day, total = int(round(BASE[model] * (1 - disc))), int(round(BASE[model] * days * (1 - disc)))
        q = {"ok": True, "days": days, "day_price": day, "total": total, "deposit": 3000, "model": model,
             "season": {"label": "low", "global_discount": 0.15}}
        if self.with_text:
            q["text"] = "%s | дней: %d, стоимость: %d (скидка за срок %d%%, %d в день), депозит: 3000 бат" % (
                model, days, total, int(round(disc * 100)), day)
        return q


def reply(text, lang="ru"):
    return json.dumps({"text": text, "lang": lang, "handoff": [], "why": "цена"}, ensure_ascii=False)


def run(M, history, q, text, lang="ru", with_text=True):
    """Переписка [(кто, текст)] + вопрос клиента + ответ подделки модели сквозь адаптер M → мир и разбор."""
    keep = TM.WM
    TM.WM = M                              # мир строит адаптер из модуля под случаем (настоящий или мутант)
    try:
        w = TM.World(reply=reply(text, lang))
        br = PriceBridge(with_text)
        w.adapter.fleet, w.adapter.door = br.fleet, br.door
        if history:                        # последнее сообщение переписки — наше: прежние вопросы отвечены
            for i, (who, t) in enumerate(history):
                w.put(TM.T0 - 3000 + i * 60, t, kind="echo" if who == "мы" else "in")
            w.core.tick(TM.T0 - 100)
            w.core.resume(TM.NUM, 1, "тест")
        w.ask(q)
    finally:
        TM.WM = keep
    d = w.drafts()
    assert len(d) == 1 and len(w.call.calls) == 1, (d, len(w.call.calls))
    hand = json.loads(d[0][4]) if d[0][4] else []
    cards = [p for p in w.http.of("sendMessage") if "reply_markup" in p]
    assert cards, w.http.of("sendMessage")
    system, user = w.call.calls[0]
    return {"w": w, "br": br, "user": user, "system": system, "hand": hand, "kb": TM.buttons(cards[-1]),
            "info": w.adapter.last["info"]}


def price_block(user):
    return [b for b in user.split("\n\n") if b.startswith("ЦЕНА: ")]


def sys_text(system):
    return system if isinstance(system, str) else " ".join(b.get("text") or "" for b in system)


# ------------------------------- случаи задания (п.4) -------------------------------

OWNER = [("клиент", "Хочу ADV 350 с 10 по 17 октября"),
         ("мы", "ADV 350 на эти даты занят, могу предложить ADV 350 на 5 дней")]


def c_owner_adv350_5_days(M):
    """Наш ответ — ADV 350 на 5 дней, клиент «сколько будет стоить?». WAPAIRS0410: «5 дней» — НАШ срок, клиентским он
    не становится; дверь одна — по паре, которую связал клиент (ADV 350 с 10 по 17 октября, 7 сут., скидка 6%).
    До WAPAIRS0410 первой шла дверь 10.10–15.10 из нашего ответа, второй — эта."""
    r = run(M, OWNER, "Сколько будет стоить?", "ADV 350 с 10 по 17 октября — 6 580 ฿, скидка за срок 6%.")
    assert r["br"].doors == [("ADV 350 1111", "2026-10-10", "2026-10-17")], r["br"].doors
    blk = price_block(r["user"])
    assert blk == ["ЦЕНА: 2026-10-10, 2026-10-17 — ADV 350: 7 сут., 940 ฿ в сутки, итого 6 580 ฿ за срок; "
                   "скидка за срок 6%; депозит 3 000 ฿."], blk
    assert r["hand"] == [] and r["kb"][0] == SEND, (r["hand"], r["kb"])
    assert RULE11 in sys_text(r["system"]), sys_text(r["system"])[-900:]


def c_owner_ready_for_5_days(M):
    """Клиент «можно и на 5 дней — сколько?»: срок из вопроса, модель из нашего ответа — ровно одна дверь, 0%."""
    r = run(M, OWNER, "Можно и на 5 дней. Сколько будет стоить?", "ADV 350 на 5 дней — 5 000 ฿, скидка за срок 0%.")
    assert r["br"].doors == [("ADV 350 1111", "2026-10-10", "2026-10-15")], r["br"].doors
    blk = price_block(r["user"])
    assert blk == ["ЦЕНА: 2026-10-10, 2026-10-15 — ADV 350: 5 сут., 1 000 ฿ в сутки, итого 5 000 ฿ за срок; "
                   "скидка за срок 0%; депозит 3 000 ฿."], blk
    assert r["hand"] == [] and r["kb"][0] == SEND, (r["hand"], r["kb"])


def c_two_models_two_lines(M):
    """Две модели в словах клиента — две двери, две строки, у каждой скидка за срок. WAPAIRS0410: модели перенесены из
    нашего ответа в слова клиента — модели, названные только нами, пар не дают (близнец ниже: дверей нет)."""
    hist = [("клиент", "Нужен ADV 350 или PCX 160 с 10 по 15 октября"), ("мы", "Оба свободны на эти даты")]
    r = run(M, hist, "сколько стоит?", "ADV 350 — 5 000 ฿, PCX 160 — 2 000 ฿ за 5 дней, скидка за срок 0%.")
    assert r["br"].doors == [("ADV 350 1111", "2026-10-10", "2026-10-15"),
                             ("PCX 160 1234", "2026-10-10", "2026-10-15")], r["br"].doors
    blk = price_block(r["user"])
    assert len(blk) == 1 and "по вариантам из переписки (2)" in blk[0], blk
    assert "(1) 2026-10-10, 2026-10-15 — ADV 350: 5 сут." in blk[0] and "(2) 2026-10-10, 2026-10-15 — PCX 160: " \
        "5 сут." in blk[0] and blk[0].count("скидка за срок 0%") == 2, blk
    assert r["hand"] == [] and r["kb"][0] == SEND, (r["hand"], r["kb"])
    ours = [("клиент", "Нужен скутер с 10 по 15 октября"), ("мы", "Есть ADV 350 и PCX 160 с 10 по 15 октября")]
    r2 = run(M, ours, "сколько стоит?", "Подскажите, какую модель считать?")
    assert r2["br"].doors == [] and not price_block(r2["user"]), (r2["br"].doors, price_block(r2["user"]))


def c_discount_5_in_line_and_answer(M):
    """Скидка 5% (6 суток самоката) — в строке и в ответе; процент с опорой — причин нет. Близнец: 10% — ловится.
    Сверка `wa_agent_tools` судит процент без исхода цены — названная дверью скидка снимается до суда."""
    q = "Сколько стоит PCX 160 с 10 по 16 октября?"
    r = run(M, [], q, "PCX 160 с 10 по 16 октября — 2 280 ฿, скидка за срок 5%.")
    assert r["br"].doors == [("PCX 160 1234", "2026-10-10", "2026-10-16")], r["br"].doors
    assert price_block(r["user"]) == ["ЦЕНА: 2026-10-10, 2026-10-16 — PCX 160: 6 сут., 380 ฿ в сутки, итого 2 280 ฿ "
                                      "за срок; скидка за срок 5%; депозит 3 000 ฿."], price_block(r["user"])
    assert r["hand"] == [] and r["kb"][0] == SEND, (r["hand"], r["kb"])
    r2 = run(M, [], q, "PCX 160 с 10 по 16 октября — 2 280 ฿, скидка за срок 10%.")
    assert r2["hand"] == [K.MONEY_CLAIM_WORDS] and SEND in r2["kb"], (r2["hand"], r2["kb"])   # WACARDUI0510
    price, text = r["info"]["price"], "PCX 160 с 10 по 16 октября — 2 280 ฿, скидка за срок 5%."
    known = set(K.thb_amounts(price["line"]))
    assert ("процент", "5%") in T.money_claims(text, price, known), T.money_claims(text, price, known)
    said = M.K.without_known_discount(text, price)
    assert not [c for c in T.money_claims(said, price, known) if c[0] == "процент"], said


def c_5pct_off_without_line_caught(M):
    """«5% off» без строки цены — ловится; при скидке 0% в строке — тоже; «discount for the term 0%» — чисто."""
    r = run(M, [], "Hi! Do you deliver to Kata?", "Yes, we deliver, and we can give you 5% off.", lang="en")
    assert r["hand"] == [K.MONEY_CLAIM_WORDS] and SEND in r["kb"], (r["hand"], r["kb"])   # WACARDUI0510
    q = "How much is PCX 160 from 10 to 15 October?"
    r2 = run(M, [], q, "PCX 160 from 10 to 15 October is 2 000 ฿, and 5% off for you.", lang="en")
    assert "скидка за срок 0%" in price_block(r2["user"])[0], price_block(r2["user"])
    assert r2["hand"] == [K.MONEY_CLAIM_WORDS] and SEND in r2["kb"], (r2["hand"], r2["kb"])   # WACARDUI0510
    r3 = run(M, [], q, "PCX 160 from 10 to 15 October is 2 000 ฿, discount for the term 0%.", lang="en")
    assert r3["hand"] == [] and r3["kb"][0] == SEND, (r3["hand"], r3["kb"])


def c_season_cross_human(M):
    """Пара из переписки через границу сезонов — «считает человек»: дверь не звана, причина на карточке. WAPAIRS0410:
    даты перенесены из нашего ответа в слова клиента — наши даты срок клиента не дают (близнец ниже: пары нет)."""
    hist = [("клиент", "Нужен ADV 350 с 28 октября по 3 ноября"), ("мы", "ADV 350 свободен на эти даты")]
    r = run(M, hist, "Сколько будет стоить?", "Цену на эти даты уточнит коллега и вернётся с точной суммой.")
    assert r["br"].doors == [] and r["br"].fleets >= 1, (r["br"].doors, r["br"].fleets)
    blk = price_block(r["user"])
    assert blk and "Эту цену считает человек: срок через границу сезонов" in blk[0], blk
    assert K.REASON_WORDS[K.R_SEASON_CROSS] in r["hand"] and SEND in r["kb"], (r["hand"], r["kb"])
    ours = [("клиент", "Нужен ADV 350"), ("мы", "ADV 350 свободен с 28 октября по 3 ноября")]
    r2 = run(M, ours, "Сколько будет стоить?", "Подскажите даты, пожалуйста.")
    assert r2["br"].doors == [] and not price_block(r2["user"]), (r2["br"].doors, price_block(r2["user"]))


def c_more_than_three_pairs_three(M):
    """Пар больше трёх — три двери (новые и первые по месту), остаток назван числом. WAPAIRS0410: перечень моделей
    перенесён из нашего ответа в слова клиента — модели, названные только нами, пар не дают."""
    hist = [("клиент", "Нужен ADV 350, PCX 160, XMAX 300 или NMAX 155 с 10 по 15 октября"),
            ("мы", "Все свободны на эти даты")]
    r = run(M, hist, "сколько стоит?", "Подскажу цены, коллега уточнит детали.")
    assert [u for u, _ds, _de in r["br"].doors] == ["ADV 350 1111", "PCX 160 1234", "XMAX 300 4321"], r["br"].doors
    blk = price_block(r["user"])
    assert "по вариантам из переписки (3)" in blk[0] and "Ещё вариантов из переписки: 1" in blk[0], blk
    assert "сверх предела 1" in r["info"]["price_words"], r["info"]["price_words"]


def c_no_start_asks_dates(M):
    """Срок без дат и без начала в переписке — числа нет, дверь не звана, агент спрашивает даты. WAPAIRS0410: срок
    перенесён из нашего ответа в слова клиента — наш срок пары не даёт (близнец ниже: строки цены нет)."""
    hist = [("клиент", "Нужен ADV 350 на 5 дней"), ("мы", "Хорошо, ADV 350 есть")]
    r = run(M, hist, "А сколько?", "Подскажите, пожалуйста, даты — с какого по какое число?")
    assert r["br"].doors == [], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "ADV 350 на 5 сут.: цена НЕИЗВЕСТНА — дата начала аренды в переписке не названа" in blk[0] \
        and "спроси у клиента даты" in blk[0], blk
    assert not [c for c in "0123456789" if c in blk[0].split("НЕИЗВЕСТНА", 1)[1]], blk
    ours = [("клиент", "Нужен ADV 350"), ("мы", "ADV 350 можно взять на 5 дней")]
    r2 = run(M, ours, "А сколько?", "Подскажите, пожалуйста, даты — с какого по какое число?")
    assert r2["br"].doors == [] and not price_block(r2["user"]), (r2["br"].doors, price_block(r2["user"]))


def c_discount_unknown_reason(M):
    """Дверь без скидки в ответе — «скидка за срок неизвестна» в строке и причина человеку; «Отправить» есть — решает человек (WACARDUI0510)."""
    r = run(M, [], "Сколько стоит PCX 160 с 10 по 15 октября?",
            "PCX 160 с 10 по 15 октября — 2 000 ฿, скидку за срок уточнит коллега.", with_text=False)
    blk = price_block(r["user"])
    assert blk and "скидка за срок неизвестна" in blk[0] and "%" not in blk[0], blk
    assert r["hand"] == [K.DISCOUNT_UNKNOWN_WORDS] and SEND in r["kb"], (r["hand"], r["kb"])   # WACARDUI0510


def c_old_paths_kept(M):
    """Прежние пути: модель и даты в вопросе — одна дверь, одна строка; без дат и без переписки — двери нет;
    не о цене — двери нет и при парах в переписке."""
    r = run(M, [], "Сколько стоит PCX 160 с 10 по 15 октября?", "PCX 160 — 2 000 ฿, скидка за срок 0%.")
    assert r["br"].doors == [("PCX 160 1234", "2026-10-10", "2026-10-15")], r["br"].doors
    assert price_block(r["user"]) == ["ЦЕНА: 2026-10-10, 2026-10-15 — PCX 160: 5 сут., 400 ฿ в сутки, итого 2 000 ฿ "
                                      "за срок; скидка за срок 0%; депозит 3 000 ฿."], price_block(r["user"])
    r2 = run(M, [], "Сколько стоит PCX 160?", "Подскажите даты, пожалуйста.")
    assert r2["br"].doors == [] and r2["br"].fleets == 0 and not price_block(r2["user"]), (r2["br"].doors,)
    r3 = run(M, OWNER, "А шлем дадите?", "Да, шлем входит.")
    assert r3["br"].doors == [] and not price_block(r3["user"]), r3["br"].doors


def c_prompt_rule_and_card(M):
    """Правило 11 в SYSTEM_PROMPT и в варианте с бронями; причина «скидка неизвестна» — своя категория."""
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert RULE11 in p and "скидку за срок уточнит коллега" in p, p[-900:]
    assert K.word_categories(K.DISCOUNT_UNKNOWN_WORDS) == [K.R_DISCOUNT_UNKNOWN], \
        K.word_categories(K.DISCOUNT_UNKNOWN_WORDS)


CASES = [c_owner_adv350_5_days, c_owner_ready_for_5_days, c_two_models_two_lines, c_discount_5_in_line_and_answer,
         c_5pct_off_without_line_caught, c_season_cross_human, c_more_than_three_pairs_three, c_no_start_asks_dates,
         c_discount_unknown_reason, c_old_paths_kept, c_prompt_rule_and_card]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------
# (файл, правило, было, стало); «было» с префиксом LINE: — вся строка исходника, что начинается так.

MUTANTS = [
    (MODEL_SRC, "контекст выключен", "        price, price_words = self._price(ask, today, ctx, ask_day)\n",
     "        price, price_words = self._price(ask, today, (), ask_day)\n"),    # ask_day — WAMINPRICE0510
    (KNOW_SRC, "скидка выпала из строки",
     '    res["line"] = "%s, %s — %s: %d сут., %s ฿ в сутки, итого %s ฿ за срок; %s; %s." % (\n',
     '    res["line"] = "%s, %s — %s: %d сут., %s ฿ в сутки, итого %s ฿ за срок; %.0s%s." % (\n'),
    (MODEL_SRC, "правило скидки снято", "LINE:11. В ответе о цене скидку за срок называй ВСЕГДА", ""),
]


def module(src, name, path):
    mod = types.ModuleType(name)
    mod.__file__ = path
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


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def mutant_kills():
    srcs ={MODEL_SRC: _read(MODEL_SRC), KNOW_SRC: _read(KNOW_SRC)}
    out = []
    for i, (path, rule, old, new) in enumerate(MUTANTS, 1):
        src = srcs[path]
        if old.startswith("LINE:"):
            old = next(x for x in src.splitlines(True) if x.startswith(old[5:]))
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        if path == MODEL_SRC:
            fs = run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i, MODEL_SRC))
        else:                              # мутант знаний: адаптер собирается поверх него, потом всё возвращается
            kmut = module(src.replace(old, new), "wa_agent_knowledge", KNOW_SRC)
            sys.modules["wa_agent_knowledge"] = kmut
            try:
                fs = run_cases(module(srcs[MODEL_SRC], "wa_agent_model_mut%d" % i, MODEL_SRC))
            finally:
                sys.modules["wa_agent_knowledge"] = K_REAL
        out.append((i, rule, fs))
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
