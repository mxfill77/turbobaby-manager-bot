#!/usr/bin/env python3
"""Два малых дефекта цепочки агента WhatsApp (WADRAFTFIX0210, задание 0123-78f.0210).

1. Путь цены находит модель по живым именам парка: модель — `wa_book_read.find_model` (ключ «слова до первого с
   цифрой»), как у броней. Имена ниже — ИМЕНА МОДЕЛЕЙ живого парка (один GET fleet 02.10: 38 юнитов, 13 моделей),
   номерные знаки заменены выдуманными. Дверь цены — только на явный вопрос с моделью и обеими датами, не больше
   одного раза на вопрос.
2. Время в словах, которые видят сотрудники (карточки, ответы на нажатия, сторож, напоминания, уроки) — «ЧЧ:ММ» по
   Пхукету одной функцией `wa_agent.hm_phuket`; UTC в этих словах нет.

Всё на подделках из соседних тестов: временные очередь и база агента, поддельные модель, мост, Bot API и дверь
отправки. Сети нет, модели нет. WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import ast
import datetime
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import test_wa_agent_model as TM  # noqa: E402
import wa_agent as A  # noqa: E402
import wa_agent_model as WM  # noqa: E402
import wa_agent_tg as G  # noqa: E402
import wa_book_read as B  # noqa: E402
import wa_history  # noqa: E402
import wa_watch as W  # noqa: E402

T0 = TM.T0                                    # 2026-09-21 14:13:20 UTC = 21:13 по Пхукету

# Имена моделей живого парка (имя юнита без номерного знака; GET fleet 02.10.2026). У двух живых имён в конце
# трёхзначное число вместо знака — формат сохранён, число выдуманное. «СС» в MT-03, NINJA и XSR — кириллица, как
# в живых именах.
LIVE_MODEL_NAMES = (
    "ADV 350CC BLACK GOLD PHUKET 100", "ADV 350CC BLACK PHUKET", "ADV 350CC DARK GREY BANGKOK",
    "ADV 350CC GREY BKK 200", "ADV 350CC LIGHT GREY HKT", "ADV 350CC RED BKK", "CB 300CC R",
    "CB 650R BLACK PHUKET", "CBR 650R PHUKET", "CLICK 125CC PHUKET", "FORZA 300CC WHITE PHUKET",
    "MT-03 300СС BLUE PHUKET", "NINJA 400СС PHUKET", "NMAX 155CC BLACK GOLD PHUKET", "NMAX 155CC BLACK GOLD-2 PHUKET",
    "NMAX 155CC BLACK GOLD-3 PHUKET", "NMAX 155CC BLACK GREEN PHUKET", "NMAX 155CC BLACK PHUKET",
    "NMAX 155CC GREEN-B PHUKET", "NMAX 155CC GREY GOLD PHUKET", "NMAX 155CC GREY PHUKET", "NMAX 155CC RACE PHUKET",
    "NMAX 155CC RED WHITE PHUKET", "VULCAN 650CC S PHUKET", "XADV 750CC BLACK BKK", "XADV 750CC GREY BKK",
    "XMAX 300CC BLUE PHUKET", "XMAX 300CC GREEN PHUKET", "XMAX 300CC GREY PHUKET", "XMAX 300CC NEW BLACK PHUKET",
    "XMAX 300CC NEW BLUE PHUKET", "XMAX 300CC NEW BLUE-2 PHUKET", "XMAX 300CC NEW BLUE-3 PHUKET",
    "XMAX 300CC NEW BROWN BANGKOK", "XMAX 300CC NEW RED GLOSS 2 PHUKET", "XMAX 300CC NEW RED GLOSS BKK",
    "XSR 155СС BLACK PHUKET", "XSR 155СС GREEN")
LIVE_UNITS = [n if n.split()[-1].isdigit() else "%s %d" % (n, 9000 + i) for i, n in enumerate(LIVE_MODEL_NAMES)]
LIVE_KEYS = {"ADV 350CC": 6, "CB 300CC": 1, "CB 650R": 1, "CBR 650R": 1, "CLICK 125CC": 1, "FORZA 300CC": 1,
             "MT-03": 1, "NINJA 400СС": 1, "NMAX 155CC": 10, "VULCAN 650CC": 1, "XADV 750CC": 2, "XMAX 300CC": 10,
             "XSR 155СС": 2}
# как клиент пишет модель → ключ модели парка
ASKS = (("ADV 350", "ADV 350CC"), ("adv350", "ADV 350CC"), ("XADV 750", "XADV 750CC"), ("X-ADV 750", "XADV 750CC"),
        ("CB 300R", "CB 300CC"), ("CB 650R", "CB 650R"), ("CBR 650R", "CBR 650R"), ("Click 125", "CLICK 125CC"),
        ("Forza 300", "FORZA 300CC"), ("MT-03", "MT-03"), ("Ninja 400", "NINJA 400СС"), ("NMAX 155", "NMAX 155CC"),
        ("Vulcan 650", "VULCAN 650CC"), ("XMAX 300", "XMAX 300CC"), ("xmax 300cc", "XMAX 300CC"),
        ("XSR 155", "XSR 155СС"))
DATES = "с 5 по 12 ноября"


class LiveBridge(TM.FakeBridge):
    """Мост с парком живого формата имён; дверь цены считает вызовы и модель не подставляет (итог — ключ)."""

    def __init__(self, units=LIVE_UNITS, available=True):
        super().__init__()
        self.units, self.available = list(units), available

    def fleet(self):
        self.fleets += 1
        return {"ok": True, "data": {"bikes": [{"name": n} for n in self.units]}}

    def door(self, unit, ds, de):
        self.doors.append((unit, ds, de))
        return {"ok": True, "days": 7, "day_price": 400, "total": 2800, "deposit": 3000,
                "season": {"label": "P3"}, "available": self.available, "conflicts": 0}


def live_world():
    w = TM.World()
    br = LiveBridge()
    w.bridge = br
    w.adapter.fleet, w.adapter.door = br.fleet, br.door
    return w, br


def built(w, text, now=T0):
    rid = w.put(now, text)
    return w.adapter.build(TM.NUM, rid, now=now)


def asked(text, book=False):
    """Один вопрос клиента в СВЕЖЕМ мире (хвост «клиент сейчас» копит все реплики после нашей последней) →
    (мост, сообщение модели, сведения). book — снимок броней включён (WA_AGENT_BOOK_READ=1)."""
    w, br = live_world()
    if book:
        other = {"row": 2, "status": "Завершена", "auto_cancel": "OFF", "bike": LIVE_UNITS[0], "name": "x",
                 "date_start": "2026-08-01 10:00", "date_end": "2026-08-05 10:00", "contacts": ""}
        w.adapter.book = B.Snapshot(lambda: {"ok": True, "data": {"clients": [other]}}, br.fleet)
    _s, user, info = built(w, text)
    return br, user, info


def phuket(ts):
    """Ожидаемое «ЧЧ:ММ» по Пхукету — независимо от кода агента."""
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts + 7 * 3600)).strftime("%H:%M")


def utc(ts):
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=ts)).strftime("%H:%M")


# ═══ 1. путь цены на живых именах парка ═══════════════════════════════════════════════════

def test_live_names_keys_13():
    """Живой формат: 38 юнитов → 13 моделей по ключу; юниты модели — все её цвета и города, без чужих."""
    bikes = [{"name": n} for n in LIVE_UNITS]
    keys = {}
    for n in LIVE_UNITS:
        keys[B.model_key(n)] = keys.get(B.model_key(n), 0) + 1
    assert keys == LIVE_KEYS, keys
    for k, n in LIVE_KEYS.items():
        assert len(WM.units_of(k, bikes)) == n, (k, WM.units_of(k, bikes))
    # прежний ключ пути цены (имя без знака) — цвет и город: 38 «моделей» на 38 юнитов
    assert len({WM.model_of_name(n) for n in LIVE_UNITS}) == 38


def test_price_found_on_live_names_one_door():
    """+ вопрос о цене с моделью живого парка и обеими датами → модель найдена, ОДНА дверь цены на юнит этой
    модели, ОДНО чтение парка; блок «ЦЕНА» с числом. Все 13 моделей, 16 написаний."""
    seen = set()
    for words, key in ASKS:
        br, user, info = asked("Сколько стоит %s %s?" % (words, DATES))
        doors = br.doors
        assert len(doors) == 1 and br.fleets == 1, (words, doors, br.fleets)
        assert B.model_key(doors[0][0]) == key and doors[0][1:] == ("2026-11-05", "2026-11-12"), (words, doors)
        p = info["price"]
        assert p["outcome"] == "number" and p["model"] == key and p["door_calls"] == 1, (words, p)
        assert "ЦЕНА: 2026-11-05, 2026-11-12 — %s: 7 сут., 400 ฿ в сутки, итого 2 800 ฿" % key in user, user[-400:]
        seen.add(key)
    assert seen == set(LIVE_KEYS), set(LIVE_KEYS) - seen


def test_price_en_question_live_names():
    """+ вопрос по-английски: «how much is XMAX 300 from Nov 5 to Nov 12» → цена XMAX, одна дверь."""
    br, _u, info = asked("how much is XMAX 300 from Nov 5 to Nov 12?")
    assert info["price"]["model"] == "XMAX 300CC" and len(br.doors) == 1, (info["price"], br.doors)


def test_price_no_cross_model():
    """− чужая модель не цепляется: XADV ≠ ADV, CB 650R ≠ CBR 650R; модели нет в парке (PCX) или названо только
    семейство без кубатуры (NMAX) → дверь не звана, «без модели из парка»."""
    br, _u, info = asked("Сколько стоит XADV 750 %s?" % DATES)
    assert info["price"]["model"] == "XADV 750CC" and B.model_key(br.doors[-1][0]) == "XADV 750CC", br.doors
    br, _u, info = asked("Сколько стоит CB 650R %s?" % DATES)
    assert info["price"]["model"] == "CB 650R" and B.model_key(br.doors[-1][0]) == "CB 650R", br.doors
    for words in ("PCX 160", "NMAX", "скутер"):
        br, user, info = asked("Сколько стоит %s %s?" % (words, DATES))
        assert info["price"] is None and "без модели из парка" in info["price_words"], (words, info["price_words"])
        assert "ЦЕНА:" not in user and br.doors == [], (words, br.doors)


def test_price_gate_question_model_both_dates():
    """− дверь цены только на явный вопрос о цене с моделью и обеими датами: без слова цены, с одной датой, без
    дат — ни двери, ни чтения парка."""
    for text, words in (("Нужен XMAX 300 %s, доставка есть?" % DATES, "о цене не спрашивают"),
                        ("Сколько стоит XMAX 300 с 5 ноября?", "без дат"),
                        ("Сколько стоит XMAX 300 в сутки?", "без дат")):
        br, user, info = asked(text)
        assert info["price"] is None and words in info["price_words"], (text, info["price_words"])
        assert "ЦЕНА:" not in user and br.doors == [] and br.fleets == 0, (text, br.doors, br.fleets)


def test_old_fixture_case_unchanged():
    """+ прежний случай (тестовый парк «PCX 160 1234»): модель «PCX 160», дверь на первый юнит — как раньше."""
    w = TM.World()
    w.ask("Сколько стоит PCX 160 с 5 по 12 ноября?")
    assert w.bridge.doors == [("PCX 160 1234", "2026-11-05", "2026-11-12")], w.bridge.doors
    assert w.adapter.last["info"]["price"]["model"] == "PCX 160"


def test_doors_per_question_with_book():
    """Сколько дверей цены даёт один вопрос: только цена — 1; цена И наличие при включённых бронях
    (WA_AGENT_BOOK_READ) — 2: одна у цены, одна сверка «свободен» у броней. Модель у обоих путей одна."""
    br, _u, info = asked("Сколько стоит и свободен ли XMAX 300 %s?" % DATES, book=True)
    assert info["price"]["model"] == "XMAX 300CC" and info["avail"]["outcome"] == B.FREE, (info["price"], info["avail"])
    assert len(br.doors) == 2 and all(B.model_key(d[0]) == "XMAX 300CC" for d in br.doors), br.doors
    br, _u, info = asked("Сколько стоит XMAX 300 %s?" % DATES, book=True)
    assert len(br.doors) == 1 and info["avail"] is None, br.doors


# ═══ 2. время по Пхукету ══════════════════════════════════════════════════════════════════

def test_hm_phuket_unit():
    """+ «ЧЧ:ММ» по Пхукету (UTC+7), переход суток; пусто — «—»; смещение то же, что у показа переписки."""
    assert A.hm_phuket(T0) == "21:13" == phuket(T0), A.hm_phuket(T0)
    late = 1_790_022_600                                     # 20:30 UTC → 03:30 следующего дня по Пхукету
    assert utc(late) == "20:30" and A.hm_phuket(late) == "03:30", A.hm_phuket(late)
    assert A.hm_phuket(0) == "—" and A.hm_phuket(None) == "—"
    assert A.PHUKET_OFFSET == wa_history.PHUKET_OFFSET == B.PHUKET_OFFSET == 7 * 3600
    assert "UTC" not in A.hm_phuket(T0)


_TIME_CALLS = {"strftime", "gmtime", "localtime", "ctime", "asctime", "fromtimestamp", "utcfromtimestamp"}
SITES = {"wa_agent": 15, "wa_agent_tg": 2, "wa_watch": 1}


def _scan(mod):
    """Исходник модуля → (вызовов hm_phuket, времени словами вне hm_phuket, строк кода с «UTC» вне докстрок)."""
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    inside, docs = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "hm_phuket":
            inside = {id(n) for n in ast.walk(node)}
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body \
                and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
            docs.add(id(node.body[0].value))
    calls, other, utc_lits = 0, [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name == "hm_phuket":
                calls += 1
            elif name in _TIME_CALLS and id(node) not in inside:
                other.append("%s:%d" % (name, node.lineno))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "UTC" in node.value \
                and id(node) not in docs:
            utc_lits.append(node.lineno)
    return calls, other, utc_lits


def test_one_time_function_for_staff_words():
    """Перечень мест: 18 мест времени в словах сотрудникам — все через ОДНУ `wa_agent.hm_phuket` (ядро 15:
    карточки, ответы на нажатия, напоминания, уроки; руки Telegram 2: урок и «продолжено»; сторож 1). Иного
    времени словами в трёх модулях нет, «UTC» в строках кода нет."""
    for mod in (A, G, W):
        name = os.path.splitext(os.path.basename(mod.__file__))[0]
        calls, other, utc_lits = _scan(mod)
        assert calls == SITES[name], (name, calls)
        assert other == [] and utc_lits == [], (name, other, utc_lits)
    assert not hasattr(A, "_hm") and not hasattr(W, "_local_hm")


def test_card_and_answers_phuket():
    """+ карточка после «Отправить» и ответ на повторное нажатие — время нажатия по Пхукету (21:21), не UTC."""
    w = TM.World()
    w.ask("Спасибо!")
    w.press("wa:send:1:1", 101)
    assert w.door.sends, w.door.sends
    edits = [p["text"] for p in w.http.of("editMessageText")]
    assert edits and phuket(T0 + 500) in edits[-1] and utc(T0 + 500) not in edits[-1], edits[-1:]
    assert "UTC" not in edits[-1]
    w.press("wa:send:1:1", 101)                                       # повтор — «уже решено: …, 21:21 — …»
    assert phuket(T0 + 500) in w.answers()[-1] and "UTC" not in w.answers()[-1], w.answers()[-1]


def test_card_no_need_phuket():
    """+ «не нужно» — то же время по Пхукету."""
    w = TM.World()
    w.ask("Спасибо!")
    w.press("wa:no:1:1", 101)
    edits = [p["text"] for p in w.http.of("editMessageText")]
    assert edits and "не нужно" in edits[-1] and phuket(T0 + 500) in edits[-1], edits[-1:]
    assert utc(T0 + 500) not in edits[-1] and "UTC" not in edits[-1]


def test_lesson_card_phuket():
    """+ урок: «исправил: Дарья, 21:21» и «✅ действующее правило — Филипп, 21:21» — по Пхукету."""
    import test_wa_lesson as TL
    w, _rid = TL.started()
    w.fix()
    lesson = w.http.of("sendMessage")[2]["text"]
    assert "Дарья (id 501), %s" % phuket(T0 + 500) in lesson and "UTC" not in lesson, lesson
    w.press("wa:rule:1:0")
    ed = TL.edits_of(w, TL.LESSON_MSG)[-1]["text"]
    assert "Филипп (id 504608015), %s" % phuket(T0 + 500) in ed and "UTC" not in ed, ed


def test_watch_alarm_phuket():
    """+ сторож: «последнее сообщение клиента — ЧЧ:ММ (Пхукет)» — та же функция, время входящего по Пхукету."""
    import test_wa_watch as TW
    w = TW._w()
    in_ts = TW.T0 - 2200
    w.row(in_ts)
    w.serve(600)
    al = w.alarms()
    assert len(al) == 1 and "— %s (Пхукет)" % phuket(in_ts) in al[0]["text"], al
    assert "%s (Пхукет)" % utc(in_ts) not in al[0]["text"] and "UTC" not in al[0]["text"], al[0]["text"]


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:300])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
