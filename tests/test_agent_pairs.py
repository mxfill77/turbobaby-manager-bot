# -*- coding: utf-8 -*-
"""WAPAIRS0410: пары «модель + срок» для двери цены не бывают чужими.

Повод — WACTXLIST0410 §4: вершина WAPRICECTX на входе №11 дала CB 650R 07.10–12.10 и 07.10–10.10 — срок «5» из нашей
фразы о минимумах ушёл к CB 650R; диапазон «5 - 7 of October» прочитан двумя датами (начало 07.10 вместо 05.10);
«CB» и «ADV» без кубатуры (№14) — не ключи парка. Теперь (`wa_agent_model.price_pairs`, шапка раздела):
  п.2 пара — только из слов клиента: модель и срок в одном его сообщении или его перечень «X или Y, N или M суток»
      (каждая модель с каждым сроком); наши сроки, даты и модели пар не дают; срок сообщения о другой модели к модели
      вопроса не идёт;
  п.3 «5 - 7 of October» — один диапазон; начало срока — дата клиента; нет начала — двери нет («спроси даты»);
  п.4 сокращение модели — ключ парка, только если в парке одна такая модель; иначе модель НЕИЗВЕСТНА, двери нет.

Входы №11 и №14 здесь — ФОРМА живых входов (порядок реплик, кто пишет, числа, «of», сокращения), слова выдуманы:
переписка в репозиторий не кладётся. Живые входы прогоняются на сервере (артефакт WAPAIRS0410). Случаи — сквозь живой
адаптер и ядро на подделках test_wa_agent_model (сети и модели нет); парк — имена моделей живого формата, дверь цены —
подделка. Мутанты: правка исходника wa_agent_model.py в памяти; мутант обязан уронить хотя бы один случай."""

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
UNITS = ["ADV 350CC BLACK PHUKET 9001", "CB 300CC R 9002", "CB 650R BLACK PHUKET 9003", "CBR 650R PHUKET 9004",
         "XADV 750CC GREY BKK 9005", "NMAX 155CC BLACK PHUKET 9006"]
BASE = {"ADV 350CC": 1400, "CB 300CC": 1200, "CB 650R": 1700, "CBR 650R": 1800, "XADV 750CC": 2500, "NMAX 155CC": 500}


class PairsBridge:
    """Парк живого формата имён и дверь цены, которая только считает и записывает вызов."""

    def __init__(self):
        self.doors, self.fleets = [], 0

    def fleet(self):
        self.fleets += 1
        return {"ok": True, "bikes": [{"name": n} for n in UNITS]}

    def door(self, unit, ds, de):
        self.doors.append((B.model_key(unit), ds, de))
        model = B.model_key(unit)
        days = (datetime.date.fromisoformat(de) - datetime.date.fromisoformat(ds)).days
        return {"ok": True, "days": days, "day_price": BASE[model], "total": BASE[model] * days, "deposit": 3000,
                "model": model, "season": {"label": "low"},
                "text": "%s | дней: %d (скидка за срок 0%%, %d в день)" % (model, days, BASE[model])}


def run(M, history, q, text="Уточню и вернусь с ответом."):
    """Переписка [(кто, текст)] + вопрос клиента сквозь адаптер модуля M → мост, сообщение модели, сведения."""
    keep = TM.WM
    TM.WM = M
    try:
        w = TM.World(reply=json.dumps({"text": text, "lang": "ru", "handoff": [], "why": "цена"}, ensure_ascii=False))
        br = PairsBridge()
        w.adapter.fleet, w.adapter.door = br.fleet, br.door
        if history:                        # последнее сообщение переписки — наше: прежние вопросы отвечены
            for i, (who, t) in enumerate(history):
                w.put(TM.T0 - 3000 + i * 60, t, kind="echo" if who == "мы" else "in")
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


def terms_block(user):
    return [b for b in user.split("\n\n") if b.startswith("СРОКИ ")]


# ------------------------------- п.5: форма входов №11 и №14 -------------------------------

IN11 = [("клиент", "Hi, 5 - 7 of October or 5 - 8 of October. ADV350 or CB650R, two of us, 3 or 4 days"),
        ("клиент", "ok"),
        ("мы", "Hello! Adv can be booked for 5 days, CB650R for 3 days")]


def c_input11_client_pairs(M):
    """№11: вопрос о CB 650R; клиент связал ADV 350 или CB 650R с «5 - 7 of October or 5 - 8 of October» — двери CB
    650R 05.10–07.10 и 05.10–08.10. Не CB 650R × 5 и не начало 07.10: наши «5 days / 3 days» пар не дают; блок
    «СРОКИ» видит оба диапазона клиента (2 и 3 сут.)."""
    r = run(M, IN11, "How much CB650R? How much?")
    assert r["br"].doors == [("CB 650R", "2026-10-05", "2026-10-07"), ("CB 650R", "2026-10-05", "2026-10-08")], \
        r["br"].doors
    assert not [d for d in r["br"].doors if d[1] == "2026-10-07" or d[2] == "2026-10-10" or d[0] != "CB 650R"], \
        r["br"].doors
    tb = terms_block(r["user"])
    assert tb and "с 05.10 по 07.10 — 2 сут." in tb[0] and "с 05.10 по 08.10 — 3 сут." in tb[0], tb
    blk = price_block(r["user"])
    assert blk and "(1) 2026-10-05, 2026-10-07 — CB 650R: 2 сут." in blk[0] and \
        "(2) 2026-10-05, 2026-10-08 — CB 650R: 3 сут." in blk[0], blk


IN14 = [("мы", "Hello! Adv can be booked for 5 days, CB650R for 3 days"),
        ("клиент", "How much CB650R?"),
        ("мы", "ADV 350 days: 5 cost: 7 000. CB 650R: 3 days — 5 100, 4 days — 6 800"),
        ("клиент", "Can I 3 days CB and 2 days ADV?"),
        ("клиент", "Or the other one?"),
        ("мы", "ADV 350 minimum rent is 5 days, 2 days is not possible. CB 650R minimum 3 days."),
        ("клиент", "Is it possible?"),
        ("мы", "Sorry, we can rent CB and ADV to you for 3 days together")]


def c_input14_unknown_no_door(M):
    """№14: «2 days CB 1 day ADV. Or 2 days CB 2 days ADV» — каждой модели свой срок перед ней; «CB» подходит к
    CB 300CC и CB 650R — модель НЕИЗВЕСТНА; «ADV» — один ADV 350CC, но начала срока в словах клиента нет — цена
    НЕИЗВЕСТНА, спросить даты. Дверей нет; наши «3 days together» и «5 days» в пары не идут."""
    r = run(M, IN14, "How much: 2 days CB 1 day ADV. Or 2 days CB 2 days ADV")
    assert r["br"].doors == [], r["br"].doors
    blk = price_block(r["user"])
    assert blk, r["user"][-600:]
    assert "«CB» на 2 сут.: цена НЕИЗВЕСТНА — модель не определена" in blk[0] and "CB 300CC / CB 650R" in blk[0], blk
    assert "ADV 350CC на 1 сут.: цена НЕИЗВЕСТНА — дата начала" in blk[0], blk
    assert "ADV 350CC на 2 сут.: цена НЕИЗВЕСТНА — дата начала" in blk[0], blk
    assert "на 3 сут." not in blk[0] and "на 5 сут." not in blk[0], blk


# ------------------------------- п.2: только слова клиента -------------------------------

def c_our_minimum_not_client_term(M):
    """Наш минимум «CB 650R — 3 дня» срок клиента не даёт: клиент назвал модели и дату начала, но срока нет — пары
    нет, двери нет (вершина WAPRICECTX дала бы CB 650R 07.10–10.10)."""
    hist = [("клиент", "ADV 350 или CB 650R с 7 октября?"), ("мы", "ADV — минимум 5 дней, CB 650R — 3 дня")]
    r = run(M, hist, "Сколько стоит CB 650R?")
    assert r["br"].doors == [] and not price_block(r["user"]), (r["br"].doors, price_block(r["user"]))


def c_term_of_other_model(M):
    """Срок, который клиент связал с ADV 350, к CB 650R из вопроса не идёт; к ADV 350 — идёт (близнец)."""
    hist = [("клиент", "ADV 350 на 5 дней с 10 октября"), ("мы", "ADV 350 свободен")]
    r = run(M, hist, "А CB 650R сколько?")
    assert r["br"].doors == [] and not price_block(r["user"]), (r["br"].doors, price_block(r["user"]))
    r2 = run(M, hist, "А ADV 350 сколько?")
    assert r2["br"].doors == [("ADV 350CC", "2026-10-10", "2026-10-15")], r2["br"].doors


def c_client_list_each_with_each(M):
    """Перечень клиента «ADV 350 или CB 650R, 3 или 4 дня» — каждая модель с каждым сроком (обе цифры, не одна 4);
    начало — его «с 10 октября»; четвёртая пара — сверх предела, названа числом."""
    hist = [("клиент", "ADV 350 или CB 650R, 3 или 4 дня, с 10 октября"), ("мы", "Хорошо")]
    r = run(M, hist, "сколько?")
    assert r["br"].doors == [("ADV 350CC", "2026-10-10", "2026-10-13"), ("ADV 350CC", "2026-10-10", "2026-10-14"),
                             ("CB 650R", "2026-10-10", "2026-10-13")], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "Ещё вариантов из переписки: 1" in blk[0], blk


def c_each_model_own_term(M):
    """Вперемешку — каждой модели свой срок: «ADV 350 на 3 дня, CB 650R на 5 дней» (срок после модели) и «2 days CB
    650R, 1 day ADV 350» (срок перед моделью); чужой срок модели не достаётся. Переписка до вопроса есть (без неё
    вопрос без двух дат двери не зовёт — прежний путь `_price`)."""
    hi = [("клиент", "Здравствуйте"), ("мы", "Здравствуйте! Чем помочь?")]
    r = run(M, hi, "Сколько стоит ADV 350 на 3 дня и CB 650R на 5 дней с 10 октября?")
    assert r["br"].doors == [("ADV 350CC", "2026-10-10", "2026-10-13"), ("CB 650R", "2026-10-10", "2026-10-15")], \
        r["br"].doors
    r2 = run(M, hi, "How much: 2 days CB 650R, 1 day ADV 350, from 10 October?")
    assert r2["br"].doors == [("CB 650R", "2026-10-10", "2026-10-12"), ("ADV 350CC", "2026-10-10", "2026-10-11")], \
        r2["br"].doors


# ------------------------------- п.3: диапазон с «of» и начало клиента -------------------------------

def c_of_range_one_range(M):
    """«5 - 7 of October» — один диапазон 05.10–07.10 (2 сут.): одна дверь, как у «с 5 по 7 октября»."""
    r = run(M, [], "How much is CB 650R 5 - 7 of October?")
    assert r["br"].doors == [("CB 650R", "2026-10-05", "2026-10-07")], r["br"].doors
    assert price_block(r["user"]) == ["ЦЕНА: 2026-10-05, 2026-10-07 — CB 650R: 2 сут., 1 700 ฿ в сутки, итого 3 400 ฿ "
                                      "за срок; скидка за срок 0%; депозит 3 000 ฿."], price_block(r["user"])
    assert M.find_dates("5 - 8 of October", datetime.date(2026, 9, 21)) == [datetime.date(2026, 10, 5),
                                                                          datetime.date(2026, 10, 8)]


def c_start_from_client_only(M):
    """Начало срока — только дата клиента: наше «свободен с 12 октября» начало не даёт — цена НЕИЗВЕСТНА, спроси
    даты; дверь не звана."""
    hist = [("клиент", "ADV 350 на 3 дня"), ("мы", "ADV 350 свободен с 12 октября")]
    r = run(M, hist, "сколько?")
    assert r["br"].doors == [], r["br"].doors
    blk = price_block(r["user"])
    assert blk and "ADV 350CC на 3 сут.: цена НЕИЗВЕСТНА — дата начала аренды в переписке не названа" in blk[0], blk


# ------------------------------- п.4: сокращение модели -------------------------------

def c_alias_one_match_only(M):
    """«ADV» — в парке одна модель (ADV 350CC): дверь; «X-ADV» — XADV 750CC, не ADV; «CB» — CB 300CC и CB 650R:
    модель НЕИЗВЕСТНА, двери нет; «CB 500» — модели нет в парке: ни двери, ни строки."""
    r = run(M, [], "How much ADV 10 - 15 of October?")
    assert r["br"].doors == [("ADV 350CC", "2026-10-10", "2026-10-15")], r["br"].doors
    r = run(M, [], "How much X-ADV 10 - 15 of October?")
    assert r["br"].doors == [("XADV 750CC", "2026-10-10", "2026-10-15")], r["br"].doors
    r = run(M, [], "How much CB 10 - 15 of October?")
    blk = price_block(r["user"])
    assert r["br"].doors == [] and blk and "модель не определена" in blk[0] and "CB 300CC / CB 650R" in blk[0], \
        (r["br"].doors, blk)
    r = run(M, [], "How much CB 500 10 - 15 of October?")
    assert r["br"].doors == [] and not price_block(r["user"]), (r["br"].doors, price_block(r["user"]))


CASES = [c_input11_client_pairs, c_input14_unknown_no_door, c_our_minimum_not_client_term, c_term_of_other_model,
         c_client_list_each_with_each, c_each_model_own_term, c_of_range_one_range, c_start_from_client_only,
         c_alias_one_match_only]


# ------------------------------- мутанты на пп. 2–4: одно правило — одна правка -------------------------------

MUTANTS = [
    ("п.2 наши строки — как слова клиента",
     "    mine = [t for who, t in msgs if who == WHO_CLIENT]           # слова клиента, новые первыми; [0] — вопрос\n",
     "    mine = [t for who, t in msgs]\n"),
    ("п.2 срок сообщения о другой модели — к модели вопроса",
     "[p for p in _link(hs, ts) if _ident(p[0]) == _ident(h)]", "[(h, t) for t in ts]"),
    ("п.2 перечень «3 или 4 дня» — одно число", "    for m in _RX_COUNT_LIST.finditer(s):\n",
     "    for m in _RX_COUNT_LIST.finditer(\"\"):\n"),
    ("п.3 «of» — не диапазон", r"(\d{1,2})\s+(?:of\s+)?" + '" + _MON)', r"(\d{1,2})\s+" + '" + _MON)'),
    ("п.3 начало — и из наших строк", "    start = context_start(mine, today)\n",
     "    start = context_start([t for _w, t in msgs], today)\n"),
    ("п.4 сокращение — первая из моделей", "ms[0] if len(ms) == 1 else None", "ms[0]"),
    ("п.4 сокращений нет", "        if a not in alias or any(", "        if True or any("),
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


def mutant_kills():
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    out = []
    for i, (rule, old, new) in enumerate(MUTANTS, 1):
        assert src.count(old) == 1, "мутант %d не применился (%s): %r" % (i, rule, old)
        out.append((i, rule, run_cases(module(src.replace(old, new), "wa_agent_model_mut%d" % i, MODEL_SRC))))
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
