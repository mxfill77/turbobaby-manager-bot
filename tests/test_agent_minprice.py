# -*- coding: utf-8 -*-
"""WAMINPRICE0510: на вопрос о цене агент не переспрашивает срок — дверь цены на минимальный срок класса модели.

Повод — №21 (05.10): v1 16:50 спросил срок, v2 16:56 назвал ставку без опоры; владелец 16:53 — «скорректировать клиента
что от 5 дней и дать цены сразу», 17:08 — лишних вопросов не задавать, сразу цена на 5 суток со скидкой за срок.
Теперь (`wa_agent_model`, раздел «минимальный срок аренды»):
  п.1 «сегодня», «завтра», «послезавтра» в словах клиента — дата от дня ЭТОГО сообщения; день неизвестен — не дата;
  п.2 класс модели — копия раздела 20.08 узла business_rules; минимум по записи 05.10.2026-1: скутер 5 суток, мотоцикл
      3, скутер вместе с мотоциклом 3 (слово клиента «вместе», «оба», together, both); начало известно, срок не назван
      или короче — дверь на минимум; X-ADV 750, модель вне списка, два скутера вместе, даты нет — как было;
  п.3 строка «ЦЕНА» такой пары — «минимум N сут. (05.10.2026-1)», клиент назвал короче — ещё «клиент назвал M сут.»;
  п.4 правило 14 SYSTEM_PROMPT: срок не спрашивай, «аренда от N суток» и цена сразу.

Синтетика №21 — ФОРМА живого входа (модель, «на завтра», срока нет), слова выдуманы: переписка в репозиторий не
кладётся. Случаи — сквозь живой адаптер и ядро на подделках test_wa_agent_model (сети и модели нет); парк — имена
моделей живого формата, дверь цены — подделка. Сегодня мира — 21.09.2026 (Пхукет), «завтра» — 22.09.
Мутанты: правка исходника wa_agent_model.py в памяти; мутант обязан уронить хотя бы один случай.
Прогон на чужом исходнике (база): python tests/test_agent_minprice.py --src <путь к wa_agent_model.py>."""

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

import wa_agent_model as M_REAL            # noqa: E402
import wa_book_read as B                   # noqa: E402
import test_wa_agent_model as TM           # noqa: E402  — мир на подделках

MODEL_SRC = os.path.join(ROOT, "wa_agent_model.py")
UNITS = ["NMAX 155CC BLACK PHUKET 9006", "CB 650R BLACK PHUKET 9003", "XADV 750CC GREY BKK 9005",
         "ADV 350CC BLACK PHUKET 9001", "PCX 160CC WHITE PHUKET 9007"]
BASE = {"NMAX 155CC": 500, "CB 650R": 1700, "XADV 750CC": 2500, "ADV 350CC": 1400, "PCX 160CC": 400}
DAY = 86400
RULE14 = "14. Строка блока «ЦЕНА» с «минимум N сут.» — клиент срок не назвал или назвал короче минимума: срок НЕ спрашивай"
HI = [("клиент", "Здравствуйте"), ("мы", "Здравствуйте! Чем помочь?")]


class MinBridge:
    """Парк живого формата имён и дверь цены, которая считает и записывает вызов."""

    def __init__(self):
        self.doors = []

    def fleet(self):
        return {"ok": True, "bikes": [{"name": n} for n in UNITS]}

    def door(self, unit, ds, de):
        model = B.model_key(unit)
        self.doors.append((model, ds, de))
        days = (datetime.date.fromisoformat(de) - datetime.date.fromisoformat(ds)).days
        return {"ok": True, "days": days, "day_price": BASE[model], "total": BASE[model] * days, "deposit": 3000,
                "model": model, "season": {"label": "low"},
                "text": "%s | дней: %d (скидка за срок 0%%, %d в день)" % (model, days, BASE[model])}


def run(M, history, q, text="Уточню и вернусь с ответом."):
    """Переписка [(кто, текст[, сдвиг времени, с])] + вопрос клиента сквозь адаптер модуля M → мост и сообщение модели.
    Без сдвига реплики идут за 50 мин до вопроса (тот же день), со сдвигом — в T0 + сдвиг."""
    keep = TM.WM
    TM.WM = M
    try:
        w = TM.World(reply=json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "цена"}, ensure_ascii=False))
        br = MinBridge()
        w.adapter.fleet, w.adapter.door = br.fleet, br.door
        if history:                        # последнее сообщение переписки — наше: прежние вопросы отвечены
            for i, h in enumerate(history):
                ts = TM.T0 + h[2] if len(h) > 2 else TM.T0 - 3000 + i * 60
                w.put(ts, h[1], kind="echo" if h[0] == "мы" else "in")
            w.core.tick(TM.T0 - 100)
            w.core.resume(TM.NUM, 1, "тест")
        w.ask(q)
    finally:
        TM.WM = keep
    assert len(w.call.calls) == 1, len(w.call.calls)
    _system, user = w.call.calls[0]
    return {"br": br, "user": user, "info": w.adapter.last["info"]}


def price_block(user):
    return [b for b in user.split("\n\n") if b.startswith("ЦЕНА: ")]


# ------------------------------- синтетика №21 и сроки клиента -------------------------------

IN21 = HI + [("клиент", "Хочу взять скутер"), ("мы", "Какую модель смотрите?")]
Q21 = "Сколько стоит NMAX на завтра?"


def c_input21_min_5_from_tomorrow(M):
    """№21: цена NMAX «на завтра», срока нет — дверь NMAX 155 на 5 суток с завтра (22.09–27.09), строка минимума;
    «клиент назвал» нет — он срока не называл."""
    r = run(M, IN21, Q21)
    assert r["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-27")], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "2026-09-22, 2026-09-27 — NMAX 155CC: 5 сут., 500 ฿ в сутки, итого 2 500 ฿ за срок; скидка за " \
        "срок 0%; депозит 3 000 ฿." in blk[0] and "минимум 5 сут. (05.10.2026-1)" in blk[0], blk
    assert "клиент назвал" not in blk[0], blk


def c_named_1_or_2_to_5(M):
    """Назвал 1 или 2 суток — дверь на 5 и «клиент назвал …»."""
    for n, word in ((2, "2 дня"), (1, "1 день")):
        r = run(M, IN21, "Сколько стоит NMAX на завтра на %s?" % word)
        assert r["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-27")], (n, r["br"].doors)
        blk = price_block(r["user"])
        assert blk and "минимум 5 сут. (05.10.2026-1); клиент назвал %d сут." % n in blk[0], blk
        assert "сут.." not in blk[0], blk                     # одна точка после «сут» (WAMINPRICEB0510)


def c_named_7_kept(M):
    """Назвал 7 — дверь на 7 с завтра, строки минимума нет."""
    r = run(M, IN21, "Сколько стоит NMAX на завтра на 7 дней?")
    assert r["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-29")], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "NMAX 155CC: 7 сут." in blk[0] and "минимум" not in blk[0], blk


def c_moto_1_to_3(M):
    """Мотоцикл на 1 сутки — дверь на 3."""
    r = run(M, HI, "Сколько CB 650R на завтра на 1 день?")
    assert r["br"].doors == [("CB 650R", "2026-09-22", "2026-09-25")], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "минимум 3 сут. (05.10.2026-1); клиент назвал 1 сут." in blk[0], blk


def c_scooter_moto_together_2_to_3(M):
    """Скутер и мотоцикл ВМЕСТЕ на 2 — обе двери на 3; без слова «вместе» — каждому свой минимум (5 и 3)."""
    r = run(M, HI, "Сколько будет NMAX и CB 650R вместе на 2 дня с завтра?")
    assert r["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-25"), ("CB 650R", "2026-09-22", "2026-09-25")], \
        r["br"].doors
    blk = price_block(r["user"])
    assert blk and blk[0].count("минимум 3 сут. (05.10.2026-1); клиент назвал 2 сут.") == 2, blk
    r2 = run(M, HI, "Сколько будет NMAX или CB 650R на 2 дня с завтра?")
    assert r2["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-27"), ("CB 650R", "2026-09-22", "2026-09-25")], \
        r2["br"].doors


def c_xadv_short_no_door(M):
    """X-ADV 750 на 2 с завтра — минимум тяжёлых НЕИЗВЕСТЕН: двери нет, как было (цена неизвестна, строки минимума
    нет)."""
    r = run(M, HI, "Сколько X-ADV на завтра на 2 дня?")
    assert r["br"].doors == [], r["br"].doors
    assert not [b for b in price_block(r["user"]) if "минимум" in b], price_block(r["user"])


def c_no_date_no_door(M):
    """Даты нет — двери нет, строки цены нет (как было)."""
    r = run(M, HI, "Сколько стоит NMAX?")
    assert r["br"].doors == [] and not price_block(r["user"]), (r["br"].doors, price_block(r["user"]))


def c_tomorrow_said_yesterday_is_today(M):
    """«Завтра» во вчерашнем сообщении клиента — сегодня (21.09), а не 22.09: дверь NMAX 21.09–26.09."""
    hist = [("клиент", "Хочу NMAX на завтра", -DAY), ("мы", "Хорошо, посмотрю", -DAY + 60)]
    r = run(M, hist, "Сколько стоит?")
    assert r["br"].doors == [("NMAX 155CC", "2026-09-21", "2026-09-26")], r["br"].doors


def c_our_minimum_not_client_term(M):
    """Наши «от 5 суток» и «от 7 суток» срока клиента не дают: CB 650R — на свой минимум 3, NMAX — на 5 (не 7);
    «клиент назвал» нет."""
    hist = [("клиент", "Здравствуйте"), ("мы", "Скутеры у нас от 5 суток, NMAX можно от 7 суток, мотоциклы от 3")]
    r = run(M, hist, "Сколько CB 650R на завтра?")
    assert r["br"].doors == [("CB 650R", "2026-09-22", "2026-09-25")], r["br"].doors
    r2 = run(M, hist, "Сколько NMAX на завтра?")
    assert r2["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-27")], r2["br"].doors
    for x in (r, r2):
        assert "клиент назвал" not in price_block(x["user"])[0], price_block(x["user"])


def c_classes_and_rule14(M):
    """Класс — по копии раздела 20.08 на живых ключах парка; правило 14 — в SYSTEM_PROMPT и в варианте с бронями."""
    got = {k: M.model_class(k) for k in ("NMAX 155CC", "ADV 350CC", "XMAX 300CC", "CB 300CC", "MT-03", "VULCAN 650",
                                         "CB 650R", "XADV 750CC", "PCX 160CC", "FORZA 350")}
    assert got == {"NMAX 155CC": M.SCOOTER, "ADV 350CC": M.SCOOTER, "XMAX 300CC": M.SCOOTER, "CB 300CC": M.MOTO,
                   "MT-03": M.MOTO, "VULCAN 650": M.MOTO, "CB 650R": M.MOTO, "XADV 750CC": M.HEAVY,
                   "PCX 160CC": None, "FORZA 350": None}, got
    for p in (M.SYSTEM_PROMPT, M.SYSTEM_PROMPT_BOOK):
        assert RULE14 in p, p[-700:]


CASES = [c_input21_min_5_from_tomorrow, c_named_1_or_2_to_5, c_named_7_kept, c_moto_1_to_3,
         c_scooter_moto_together_2_to_3, c_xadv_short_no_door, c_no_date_no_door, c_tomorrow_said_yesterday_is_today,
         c_our_minimum_not_client_term, c_classes_and_rule14]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("минимума нет", "MIN_DAYS = {SCOOTER: 5, MOTO: 3}\n", "MIN_DAYS = {}\n"),
    ("«завтра» не дата", "    if day is not None:\n        rel = []\n", "    if False:\n        rel = []\n"),
    ("строки минимума нет", 'MIN_NOTE = " Аренда от %d сут.: минимум %d сут. (%s)"\n', 'MIN_NOTE = "%.0s%.0s%.0s"\n'),
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
            fails.append((c.__name__, "%s: %s" % (type(e).__name__, str(e)[:300])))
    return fails


def main():
    src_path = sys.argv[sys.argv.index("--src") + 1] if "--src" in sys.argv else None
    if src_path:                                                     # чужой исходник (база): только случаи
        with open(src_path, encoding="utf-8") as fh:
            M = module(fh.read(), "wa_agent_model_src", MODEL_SRC)
    else:
        M = M_REAL
    try:
        r = run(M, IN21, Q21)
        print("ЦЕНА №21: %s" % (price_block(r["user"]) or ["(блока нет)"])[0])
        print("двери №21: %s" % r["br"].doors)
    except Exception as e:                                           # noqa: BLE001
        print("ЦЕНА №21: прогон упал — %s: %s" % (type(e).__name__, str(e)[:200]))
    fails = run_cases(M)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL %s %s" % (c.__name__, f[0][1])) if f else "PASS %s" % c.__name__)
    print("ИТОГ %d/%d" % (len(CASES) - len(fails), len(CASES)))
    if src_path:
        return 1 if fails else 0
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    killed = 0
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        fs = run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i, MODEL_SRC))
        killed += bool(fs)
        print("мутант %d «%s»: упало %d из %d%s — %s" % (i, rule, len(fs), len(CASES), "" if fs else "  ← ВЫЖИЛ",
                                                       ", ".join(n for n, _ in fs)))
    print("мутантов %d — поймано %d" % (len(MUTANTS), killed))
    return 1 if fails or killed < len(MUTANTS) else 0


if __name__ == "__main__":
    sys.exit(main())
