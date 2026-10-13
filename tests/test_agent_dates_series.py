# -*- coding: utf-8 -*-
"""USEFULDATES1310 (часть A): даты клиента как ПЕРИОД — серия сообщений и начало словом.

Повод — 5 живых эпизодов стенда (вердикт judge2: смысл 5/5 «часть»). Класс один: код не видел срок, который клиент
назвал, и блоки СРОКИ / НАЛИЧИЕ / ЦЕНА молчали или врали:
  E05 «Два мотоцикла нужны с 7 по 14» + следующим сообщением «Марта» — блок СРОКИ «с 7 по 14 (месяц не назван)»: серия
      разбиралась по одному сообщению, месяц следующего к числам предыдущего не относился;
  E01 «Даты, сегодня до 16 апреля вечер.» + «Что есть в наличии?» — ни СРОКИ, ни НАЛИЧИЯ: ни один вид диапазона не знал
      начала словом, а `find_ranges` не знал дня сообщения вовсе.
Теперь (`wa_agent_model`):
  п.1 `find_ranges(text, today, day)` — виды «начало словом + разделитель + дата» (сегодня/завтра/послезавтра,
      сегодняшнего/завтрашнего дня, today/tomorrow/day after tomorrow); начало — от дня сообщения; без дня поиск прежний;
  п.2 `client_terms` разбирает СЕРИЮ клиента (`client_series`: реплики подряд, склейка "\\n", как вопрос; рвёт наша
      реплика, автоприветствие — нет; день — общий день серии);
  п.3 `_book`: двух дат нет, а период есть — даты из первого полного диапазона (день вопроса — ask_day);
  п.4 `_terms` (пары цены) — с днём сообщения;
  п.5 `find_dates`: число диапазона «5-7 октября» больше не затирает день сообщения — «завтра» рядом с таким диапазоном
      давало TypeError, черновика не было («модель упала»; найдено прогоном по обезличенной базе диалогов).
Фразы — ФОРМА живого входа (E01/E05 дословно, прочие — парафразы RU/EN), плюс контрпримеры. Сквозь живой адаптер и ядро
на подделках test_wa_agent_model (сети и модели нет). Сегодня мира — 21.09.2026 (Пхукет), «завтра» — 22.09.
Мутанты: правка исходника wa_agent_model.py в памяти; мутант обязан уронить хотя бы один случай."""

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
TODAY = datetime.date(2026, 9, 21)         # «сегодня» мира TM (T0 = 2026-09-21 UTC, Пхукет)
D = datetime.date
UNITS = ["NMAX 155CC BLACK PHUKET 9006", "CB 650R BLACK PHUKET 9003", "PCX 160CC WHITE PHUKET 9007"]
BASE = {"NMAX 155CC": 500, "CB 650R": 1700, "PCX 160CC": 400}
E05_1 = "Опыт 6 лет , права категории а . Два мотоцикла нужны  с 7 по 14"     # живой E05 р2, дословно
E01_2 = "Уже брал у вас в 2024. Все устроило.\nДаты, сегодня до 16 апреля вечер."   # живой E01 р2, дословно
E01_3 = "Что есть в наличии?\nКак происходит оплата и сколько доставка?"           # живой E01 р3, дословно


def spans(M, text, day):
    return [(r["ds"], r["de"], r["days"]) for r in M.find_ranges(text, TODAY, day)]


def it(who, text, ts=None, auto=False, word=None):
    return {"who": who, "text": text, "ts": ts, "auto": auto, "word": word}


def terms(M, items):
    return [(r["label"], r["days"]) for r in M.client_terms(items, TODAY)]


class Bridge:
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


class Book:
    """Снимок броней на подделке: строк нет (таблица прочитана, пустая), парк — UNITS; считает чтения."""

    def __init__(self):
        self.reads = 0

    def get(self, now):
        self.reads += 1
        return [], [{"name": n} for n in UNITS], 0, ""


def world(M, series, book=None):
    """Серия клиента [(сдвиг от T0, текст)] — последняя реплика задаёт вопрос; сквозь адаптер модуля M → мир."""
    keep = TM.WM
    TM.WM = M
    try:
        w = TM.World(reply=json.dumps({"text": "Уточню и вернусь.", "lang": "ru", "handoff": [], "why": "даты"},
                                      ensure_ascii=False))
        br = Bridge()
        w.adapter.fleet, w.adapter.door = br.fleet, br.door
        if book is not None:
            w.adapter.book = book
        for dt, text in series[:-1]:
            w.put(TM.T0 + dt, text)
        w.ask(series[-1][1], ts=TM.T0 + series[-1][0])
    finally:
        TM.WM = keep
    assert len(w.call.calls) == 1, len(w.call.calls)
    return {"br": br, "user": w.call.calls[0][1], "info": w.adapter.last["info"]}


def block(user, head):
    return [b for b in user.split("\n\n") if b.startswith(head)]


# ------------------------------- п.1: начало словом -------------------------------

REL_CASES = [                              # (текст, день сообщения, выдача, возврат)
    ("Даты, сегодня до 16 апреля вечер.", TODAY, D(2026, 9, 21), D(2027, 4, 16)),      # E01 дословно
    ("с завтра по 30 сентября", TODAY, D(2026, 9, 22), D(2026, 9, 30)),
    ("послезавтра - 3 октября", TODAY, D(2026, 9, 23), D(2026, 10, 3)),
    ("Нужен с сегодняшнего дня до 5 октября", TODAY, D(2026, 9, 21), D(2026, 10, 5)),
    ("с завтрашнего дня по 1 октября", TODAY, D(2026, 9, 22), D(2026, 10, 1)),
    ("from today till April 16", TODAY, D(2026, 9, 21), D(2027, 4, 16)),
    ("tomorrow to 5th of October please", TODAY, D(2026, 9, 22), D(2026, 10, 5)),
    ("day after tomorrow - Oct 3", TODAY, D(2026, 9, 23), D(2026, 10, 3)),
    ("Today until Sep 28", TODAY, D(2026, 9, 21), D(2026, 9, 28)),
    ("завтра до 25 сентября", D(2026, 9, 19), D(2026, 9, 20), D(2026, 9, 25)),         # день сообщения ≠ сегодня
]


def c_rel_start_with_day(M):
    """Начало словом + разделитель + дата — один диапазон от дня СООБЩЕНИЯ; сутки — разность дат."""
    for text, day, ds, de in REL_CASES:
        got = spans(M, text, day)
        assert got == [(ds, de, (de - ds).days)], (text, got)
    r = M.find_ranges("Даты, сегодня до 16 апреля вечер.", TODAY, TODAY)[0]
    assert r["label"] == "с 21.09 по 16.04" and r["days"] == 207, r


def c_rel_start_needs_day(M):
    """День сообщения неизвестен — начала нет: поиск как был (те же фразы — ни одного диапазона)."""
    for text, _day, _ds, _de in REL_CASES:
        assert M.find_ranges(text, TODAY) == [] and M.find_ranges(text, TODAY, None) == [], text


def c_rel_counterexamples(M):
    """Не период: без разделителя, время, без начала, прилагательное, конец не позже начала, два начала."""
    for text in ("сегодня 16 апреля", "сегодня до 17:00", "до 16 апреля", "сегодняшний курс до 16 апреля",
                 "сегодня до 21 сентября", "today 5 people, till 10", "сегодня-завтра до 5 октября",
                 "сегодня до 8 вечера", "tomorrow until 5 pm"):
        assert spans(M, text, TODAY) == [], (text, spans(M, text, TODAY))
    # прежние виды с днём — те же, что без дня: место за ними
    for text in ("с 5 по 7 октября", "5–8 октября", "from 5 to 7 October", "30 сентября - 2 октября"):
        assert M.find_ranges(text, TODAY, TODAY) == M.find_ranges(text, TODAY), text


# ------------------------------- п.2: серия клиента -------------------------------

def c_series_month_in_next_message(M):
    """Месяц следующей реплики серии — к числам предыдущей (E05 дословно и парафразы RU/EN)."""
    assert terms(M, [it("клиент", E05_1), it("клиент", "Марта")]) == [("с 07.03 по 14.03", 7)], \
        terms(M, [it("клиент", E05_1), it("клиент", "Марта")])
    for a, b, want in (("need 2 bikes from 3 to 8", "of May", ("с 03.05 по 08.05", 5)),
                       ("Нужен байк 5-9", "октября", ("с 05.10 по 09.10", 4)),
                       ("с 10 по 12", "ноября пожалуйста", ("с 10.11 по 12.11", 2))):
        assert terms(M, [it("клиент", a), it("клиент", b)]) == [want], (a, b, terms(M, [it("клиент", a),
                                                                                      it("клиент", b)]))


def c_series_boundaries(M):
    """Серию рвёт наша реплика (наши слова — не слова клиента); автоприветствие и реплика без текста — не рвут; два
    диапазона двух реплик — два; число и месяц без диапазона — не срок."""
    bare = [("с 7 по 14 (месяц не назван)", 7)]
    assert terms(M, [it("клиент", "с 7 по 14"), it("мы", "Марта?"), it("клиент", "да")]) == bare, \
        terms(M, [it("клиент", "с 7 по 14"), it("мы", "Марта?"), it("клиент", "да")])
    assert terms(M, [it("клиент", "с 7 по 14"), it("мы", "Здравствуйте!", auto=True), it("клиент", "марта")]) == \
        [("с 07.03 по 14.03", 7)]
    assert terms(M, [it("клиент", "с 7 по 14"), it("клиент", "", word="фото"), it("клиент", "марта")]) == \
        [("с 07.03 по 14.03", 7)]
    assert terms(M, [it("клиент", "с 5 по 7 октября"), it("клиент", "или с 10 по 12 октября")]) == \
        [("с 05.10 по 07.10", 2), ("с 10.10 по 12.10", 2)]
    assert terms(M, [it("клиент", "Нас 2 человека"), it("клиент", "приедем в марте")]) == []


def c_series_day(M):
    """День серии — общий день её реплик: «сегодня до 16 апреля» — от него; дни разные или неизвестны — не дата."""
    one = [it("клиент", "Здравствуйте, необходим мопед", TM.T0 - 120), it("клиент", E01_2, TM.T0 - 60)]
    assert terms(M, one) == [("с 21.09 по 16.04", 207)], terms(M, one)
    two = [it("клиент", "Здравствуйте, необходим мопед", TM.T0 - 86400), it("клиент", E01_2, TM.T0)]
    assert terms(M, two) == [], terms(M, two)
    assert terms(M, [it("клиент", E01_2)]) == [], terms(M, [it("клиент", E01_2)])


def c_e05_prompt(M):
    """E05 сквозь адаптер: блок СРОКИ — «с 07.03 по 14.03 — 7 сут.», «месяц не назван» нет."""
    r = world(M, [(-120, E05_1), (0, "Марта")])
    blk = block(r["user"], "СРОКИ (")
    assert blk and blk[0].endswith("с 07.03 по 14.03 — 7 сут.") and "месяц не назван" not in r["user"], blk


def c_e01_prompt_terms_and_avail(M):
    """E01 сквозь адаптер: СРОКИ «с 21.09 по 16.04 — 207 сут.»; вопрос о наличии со сроком из серии — таблица броней
    читается, НАЛИЧИЕ на эти даты (модель не названа — честное «неизвестно»), «без двух дат» нет."""
    book = Book()
    r = world(M, [(-180, "Здравствуйте, необходим мопед"), (-120, E01_2), (-60, E01_3),
                  (0, "Есть права АБ + международные")], book=book)
    blk = block(r["user"], "СРОКИ (")
    assert blk and blk[0].endswith("с 21.09 по 16.04 — 207 сут."), blk
    av = r["info"]["avail"]
    assert av and (av["date_start"], av["date_end"]) == ("2026-09-21", "2027-04-16"), (av, r["info"]["book_words"])
    assert av["outcome"] == B.UNKNOWN and "модель не названа" in av["line"] and book.reads == 1, (av, book.reads)
    assert "без двух дат" not in r["info"]["book_words"], r["info"]["book_words"]


# ------------------------------- п.3: наличие по периоду -------------------------------

def book_of(M, ask, ask_day):
    book = Book()
    ad = M.ModelAdapter("", None, book=book)
    avail, _rental, words = ad._book(TM.NUM, ask, TODAY, TM.T0, ask_day)
    return avail, words, book.reads


def c_book_period(M):
    """Слово наличия + период (начало словом от дня вопроса; «5 октября - 7»; «October 5-7») — даты диапазона."""
    for ask, day, want in (("Что есть в наличии? сегодня до 16 апреля", TODAY, ("2026-09-21", "2027-04-16")),
                           ("PCX 160 свободен 5 октября - 7?", None, ("2026-10-05", "2026-10-07")),
                           ("Is NMAX available October 5-7?", None, ("2026-10-05", "2026-10-07")),
                           ("any bike from tomorrow till Oct 1?", TODAY, ("2026-09-22", "2026-10-01"))):
        av, words, reads = book_of(M, ask, day)
        assert av and (av["date_start"], av["date_end"]) == want and reads == 1, (ask, av, words)


def c_book_counterexamples(M):
    """Нет периода — как было: таблица не звана; без дня вопроса «сегодня» не дата; без слова наличия — не спрашивают."""
    for ask, day, words_want in (("Что есть в наличии?", TODAY, "о наличии без двух дат — таблица не звана"),
                                 ("Что есть в наличии? сегодня до 16 апреля", None,
                                  "о наличии без двух дат — таблица не звана"),
                                 ("сегодня до 16 апреля", TODAY, "о бронях не спрашивают")):
        av, words, reads = book_of(M, ask, day)
        assert av is None and words == words_want and reads == 0, (ask, av, words, reads)
    av, _w, _r = book_of(M, "Свободен PCX 160 с 5 по 7 октября?", TODAY)      # две даты — как было
    assert (av["date_start"], av["date_end"]) == ("2026-10-05", "2026-10-07"), av


# ------------------------------- п.4: пары цены -------------------------------

def c_price_term_from_word_start(M):
    """Вопрос о цене со сроком «с завтра до …» — дверь на срок клиента, а не на минимум от «завтра»."""
    r = world(M, [(0, "Сколько стоит NMAX с завтра до 30 сентября?")])
    assert r["br"].doors == [("NMAX 155CC", "2026-09-22", "2026-09-30")], r["br"].doors
    r = world(M, [(0, "How much is CB 650R from tomorrow till September 29?")])     # в пределах сезона
    assert r["br"].doors == [("CB 650R", "2026-09-22", "2026-09-29")], r["br"].doors
    t = M._terms(M._said("с завтра до 30 сентября", TODAY), TODAY)
    assert [(x["ds"], x["de"], x["days"]) for x in t] == [(D(2026, 9, 22), D(2026, 9, 30), 8)], t
    assert M._terms("с завтра до 30 сентября", TODAY) == [], M._terms("с завтра до 30 сентября", TODAY)


def c_range_with_relative_word(M):
    """Диапазон «5-7 октября» и слово «завтра» в одном тексте: даты, а не TypeError (прежде имя числа диапазона затирало
    день сообщения, разбор падал, и черновика не было — «модель упала»)."""
    for text in ("Нужен завтра, с 5 по 7 октября", "tomorrow or 5-7 October"):
        assert M.find_dates(text, TODAY) == [D(2026, 10, 5), D(2026, 10, 7)], (text, M.find_dates(text, TODAY))
        assert M.find_dates(text, TODAY, TODAY) == [D(2026, 9, 22), D(2026, 10, 5), D(2026, 10, 7)], text
    r = world(M, [(0, "Сколько стоит NMAX завтра или с 5 по 7 октября?")])       # черновик есть (модель звана)
    assert r["info"]["price_words"].startswith("цена"), r["info"]["price_words"]


CASES = [c_rel_start_with_day, c_rel_start_needs_day, c_rel_counterexamples, c_series_month_in_next_message,
         c_series_boundaries, c_series_day, c_e05_prompt, c_e01_prompt_terms_and_avail, c_book_period,
         c_book_counterexamples, c_price_term_from_word_start, c_range_with_relative_word]


# ------------------------------- мутанты: одно правило — одна правка -------------------------------

MUTANTS = [
    ("п.1 начало словом без дня", "    kinds = _RANGES if day is None else _RANGES + _REL_RANGES\n",
     "    kinds = _RANGES + _REL_RANGES\n"),
    ("п.1 «завтра» — сегодня", 'else 1 if w.startswith(("завтра", "tomorrow")) else 0',
     'else 0 if w.startswith(("завтра", "tomorrow")) else 0'),
    ("п.2 серия по одному сообщению", "    for text, day in client_series(items):\n",
     '    for text, day in [(i["text"], None) for i in items or ()\n'
     '                      if i.get("who") == "клиент" and i.get("text")]:\n'),
    ("п.2 наша реплика в серии клиента", '        if it.get("who") == "клиент":\n',
     '        if it.get("who") in ("клиент", "мы"):\n'),
    ("п.2 автоприветствие рвёт серию", '        if it.get("auto"):\n            continue\n',
     '        if False:\n            continue\n'),
    ("п.2 день серии при разных днях", "days.pop() if len(days) == 1 else None", "days.pop()"),
    ("п.3 наличие без периода", "        if asked and len(dates) < 2:\n", "        if False:\n"),
    ("п.3 день вопроса не передан", "self._book(number, ask, today, now, ask_day)",
     "self._book(number, ask, today, now)"),
    ("п.4 пары цены без дня", '    rs = find_ranges(text, today, getattr(text, "day", None))\n',
     "    rs = find_ranges(text, today)\n"),
    ("п.5 число диапазона затирает день", "        for pos, num in ((m.start(1), m.group(1)), (m.start(2), m.group(2))):\n"
     "            d = _mk(today, num, mo)\n",
     "        for pos, day in ((m.start(1), m.group(1)), (m.start(2), m.group(2))):\n"
     "            d = _mk(today, day, mo)\n"),
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
    fails = run_cases(M_REAL)
    for c in CASES:
        f = [x for x in fails if x[0] == c.__name__]
        print(("FAIL %s %s" % (c.__name__, f[0][1])) if f else "PASS %s" % c.__name__)
    print("ИТОГ %d/%d" % (len(CASES) - len(fails), len(CASES)))
    with open(MODEL_SRC, encoding="utf-8") as fh:
        src = fh.read()
    if not hasattr(M_REAL, "client_series"):                         # дерево до правки: мутировать нечего
        print("мутанты: исходник до правки — не применяются")
        return 1 if fails else 0
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
