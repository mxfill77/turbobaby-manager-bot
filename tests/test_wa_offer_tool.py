#!/usr/bin/env python3
"""OFFER1910 (отрезок inquiry-to-booking): инструмент offer сверки Т4а — приёмка `wa_offer_tool` и флага службы
WA_AGENT_OFFER.

Клиент: «PCX 160 с 10 по 15 ноября сколько?» → «а свободен?» — модель сама зовёт offer {PCX 160, 2026-11-10, 2026-11-15}:
наличие и цена одним вызовом двери цены, факт с источником и подтверждённым юнитом (юнит — только журналу). Занято —
модель проверяет альтернативу; черновик назвал свободным занятое или непроверенное — «агент их не видит» не снимается и
причина «не совпадает с проверкой»; ворота, снимок, дверь, модель и даты — не факт и причина человеку; предел 3 вызова; флаг
выкл — модуля в процессе нет, класс и блок инструментов прежние; модель offer не звала — черновик и журнал равны
родительским. Каждый случай — с близнецом.

r3: причина «агент их не видит» снимается, только если текст сверен с фактами ЦЕЛИКОМ (каждая модель парка где угодно в
тексте и каждый диапазон дат; «We have NMAX 155», «можем предложить», «…, but X is», другие даты — не снимают); слова брони
в черновике — «бронь оформляет человек» при любом входящем; «занято» по снимку старше последнего входящего — не факт;
слово двери «model», похожее на юнит, в строку цены не идёт; служба выключает offer КОДОМ (OFFER-OFFPIN1910) — окружение
WA_AGENT_OFFER=1 ничего не включает.

Стенд: адаптер `wa_agent_model.ModelAdapter` со сборкой-подменой (как у `test_wa_agent_tools`), поддельные снимок броней,
дверь цены (живой формат QuotePrice.js: available, days, day_price, total, deposit, скидка словами в text) и модель по
сценарию; служба — мир `test_wa_agent_model.World`. «Сегодня» — 21.09.2026 по Пхукету, номер выдуманный. Сети нет, модели
нет, боевых баз нет."""
import ast
import datetime
import json
import os
import subprocess
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

try:                                       # spend_ledger импортирует fcntl (только Linux): на ПК без заглушки — подмена цены
    import fcntl  # noqa: F401
except ImportError:
    sys.modules.setdefault("spend_ledger", types.SimpleNamespace(cost_usd=lambda model, i, o: 0.0,
                                                                 meter=lambda *a, **k: None))

PROBE_ARG = "--probe-offer-off"
PROBE_MARK = "OFFER_PROBE "
NEW_MODULE = "wa_offer_tool"


# окружение процесса пробы (OFFER-OFFPIN1910): offer ВКЛ вместе со сверкой, бронями и ценой через ход — служба читает его
# сама (`build(environ=None)` → os.environ), прочих WA_AGENT_* в процессе нет
PROBE_ENV = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_TOOLS": "1", "WA_AGENT_OFFER": "1",
             "WA_AGENT_PRICE_CARRY": "1"}


def _probe():
    """Отдельный процесс: служба БЕЗ засчитанного offer — модуля выпуска в процессе нет, класс адаптера прежний (ни
    примеси offer, ни цены через ход), блок инструментов сверки без строки offer, строки старта об offer нет. Прогоны:
    флаг не запрошен; «0»; 1 без сверки; и ВКЛ окружением (OFFER-OFFPIN1910) — картой прогона (1, true + цена через ход) и
    самим окружением процесса (`PROBE_ENV`): выкл кодом, строки старта те же, что без флага. Адаптер — свой на прогон."""
    import test_wa_agent_model as TM
    import test_wa_book_read as TB
    import wa_agent_svc as S
    import wa_agent_tools as T
    w = TM.World()
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}
    seen = []

    def make():
        br = TB.Bridge([])
        br.tx_find, br.contract_find, br.contract_pdf = (lambda **k: {}), (lambda **k: {}), (lambda **k: {})
        return S.make_model(env, bridge=br, call=lambda s, u: (seen.append(u) or json.dumps(
            {"text": "Здравствуйте!", "lang": "ru", "handoff": [], "why": "x"}), {}), book=True, tools=True)[0]
    base = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_TOOLS": "1"}
    runs, model = [], None
    for i, environ in enumerate((base, dict(base, WA_AGENT_OFFER="0"),
                                 {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_OFFER": "1"},
                                 dict(base, WA_AGENT_OFFER="1"),
                                 dict(base, WA_AGENT_OFFER="true", WA_AGENT_PRICE_CARRY="1"),
                                 None)):
        model, lines, db = make(), [], w.dbpath + str(i)
        S.build(dict(env, agent_db=db), environ=environ, model=model, line=lines.append)
        runs.append({"offer": [ln for ln in lines if "WA_AGENT_OFFER" in ln or ln.startswith("наличие и цена по запросу")],
                     "type": type(model).__name__, "n": len(lines), "lines": [ln.replace(db, "<db>") for ln in lines],
                     "env": None if environ is not None else {k: os.environ.get(k) for k in sorted(PROBE_ENV)}})
    rid = w.put(TM.T0, "а свободен?")
    model.draft(TM.NUM, rid)                        # адаптер последнего прогона — включённого окружением процесса
    print(PROBE_MARK + json.dumps({"runs": runs, "mods": sorted(m for m in sys.modules if m == NEW_MODULE),
                                   "offer_in_block": any("offer {" in u for u in seen),
                                   "block_head": all(u.startswith(T.TOOLS_BLOCK % T.MAX_CALLS + "\n\nСЕГОДНЯ")
                                                     for u in seen), "calls": len(seen)}, ensure_ascii=False))


if __name__ == "__main__" and PROBE_ARG in sys.argv:
    _probe()
    sys.exit(0)

import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_tools as T  # noqa: E402
import wa_book_read as B  # noqa: E402
import wa_offer_tool as O  # noqa: E402

T0 = 1_790_000_000.0                         # 21.09.2026 21:13 по Пхукету (= test_wa_agent_model.T0)
TODAY = datetime.date(2026, 9, 21)
NUMBER = "10000000009"                       # выдуманный номер
BIKES = [{"name": n} for n in ("PCX 160 1234", "PCX 160 5678", "NMAX 155 7001", "CB 300 9011", "CB 650R 9012",
                               "XMAX 300 4321")]
AVAIL_WORDS = K.REASON_WORDS[K.R_AVAILABILITY]
Q = "а свободен?"
PCX = {"model": "PCX 160", "date_from": "2026-11-10", "date_to": "2026-11-15"}
NMAX = {"model": "NMAX 155", "date_from": "2026-11-10", "date_to": "2026-11-15"}
# даты — отдельным предложением: число без валюты в предложении с денежным словом судья сверки судит как сумму (прежнее
# правило `wa_agent_tools.money_claims`, не этого выпуска)
FREE_TEXT = ("PCX 160 с 10 по 15 ноября свободен. Цена: 400 ฿ в сутки, итого 2 000 ฿ за 5 суток, скидка за срок 0%, "
             "депозит 3 000 ฿.")
LOG = []


# ══ стенд ══════════════════════════════════════════════════════════════════════════════════════════════════════

class Clock:
    def __init__(self, t=T0, step=0.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


class Script:
    """Модель по сценарию: ответы по порядку, последний повторяется; `seen` — запросы (user) каждого хода."""

    def __init__(self, *answers):
        self.answers, self.seen = list(answers), []

    def __call__(self, system, user):
        self.seen.append(user)
        a = self.answers[min(len(self.seen) - 1, len(self.answers) - 1)]
        return (a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)), {"in": 10, "out": 5}


def final(text, handoff=()):
    return {"text": text, "handoff": list(handoff), "lang": "ru", "why": "тест"}


def offer(args):
    return {"tool": "offer", "args": dict(args)}


class Book:
    """Снимок броней: (строки, парк, возраст, почему); rows=None — не служит."""

    def __init__(self, rows=(), bikes=BIKES, age=60.0, why=""):
        self.rows, self.bikes, self.age, self.why, self.reads = list(rows) if rows is not None else None, bikes, age, \
            why, 0

    def get(self, now):
        self.reads += 1
        if self.rows is None:
            return None, None, None, self.why or "дверь clients не дала строк"
        return self.rows, self.bikes, self.age, ""


class Door:
    """Дверь цены живого формата: available, days, ставка 400/сут, депозит 3000, скидка за срок словами в text; name —
    слово поля «model» ответа (по умолчанию ключ модели юнита)."""

    def __init__(self, available=True, discount=0, fail=None, ok=True, name=None):
        self.available, self.discount, self.fail, self.ok, self.calls = available, discount, fail, ok, []
        self.name = name

    def __call__(self, unit, ds, de):
        self.calls.append((unit, ds, de))
        if self.fail is not None:
            raise self.fail
        days = (datetime.date.fromisoformat(de) - datetime.date.fromisoformat(ds)).days
        model = self.name or B.model_key(unit)
        disc = "" if self.discount is None else "скидка за срок %d%%, " % self.discount
        return {"ok": self.ok, "available": self.available, "days": days, "day_price": 400, "total": 400 * days,
                "deposit": 3000, "season": {"label": "P3"}, "model": model,
                "text": "%s | дней: %d, стоимость: %d (%s400 в день), депозит: 3000 бат" % (model, days, 400 * days,
                                                                                         disc)}


def row(bike, status, ds, de):
    return {"row": 2, "status": status, "auto_cancel": "OFF", "bike": bike, "date_start": ds, "date_end": de,
            "contacts": ""}


BUSY_PCX = [row("PCX 160 1234", "Бронь", "2026-11-09 10:00", "2026-11-16 10:00"),
            row("PCX 160 5678", "Бронь", "2026-11-12 10:00", "2026-11-13 10:00")]


def adapter(script, rows=(), book=True, door=None, question=Q, price=None, reasons=None, last_in=None, mixin=True,
            clock=None, tools=None, avail=None, terms=(), conv=None, **book_kw):
    """Адаптер со сверкой (WA_AGENT_TOOLS) и бронями (WA_AGENT_BOOK_READ): сборка — подмена со сведениями вызова
    (вопрос, «сегодня», причины кода как у `K.handoff`); mixin — примесь offer надета."""
    door = Door() if door is None else door
    lines = []
    a = M.ModelAdapter(":memory:-не-открывается", script, read_doc=None, clock=clock or Clock(), log=lines.append,
                       book=Book(rows, **book_kw) if book else None, tools=tools if tools is not None else {},
                       door=door or None, fleet=lambda: {"ok": True, "bikes": BIKES})
    info = {"price": price, "code_reasons": reasons if reasons is not None else K.handoff(question, price),
            "price_words": "о цене не спрашивают", "history_items": 1, "history_chars": 10, "masked": 0,
            "question": question, "today": TODAY, "last_in": last_in, "terms": list(terms), "avail": avail,
            "conv": conv}
    a.build = lambda number, upto_id, now=None, hint=None: ("SYSTEM", "USER", info)
    a._history = lambda number, upto_id: ([{"who": "клиент", "text": question}], [])
    a.knowledge.snap["business_rules"] = {"name": "business_rules", "read": True,
                                          "text": "… 03.10.2026-1 Решения владельца …", "len": 40}
    if mixin:
        a.__class__ = O.with_offer(type(a))
    a.lines = lines
    return a, door


def offers(a):
    return a.last["tools"]["offers"]


def offer_block(user):
    """Блок ответов offer из запроса модели ("" — нет)."""
    i = user.find(O.HEAD.split(" (")[0])
    return user[i:] if i >= 0 else ""


# ══ О1: свободно — один вызов двери, факт, цена — опора ════════════════════════════════════════════════════════

def test_o1_free_one_door_fact_and_price():
    """(а) «а свободен?» → модель зовёт offer по паре из переписки: FACT «свободно», ровно один quote_price (и наличие,
    и цена), юнит — в факте и журнале, но НЕ в запросе модели; числа ответа — с опорой; «агент их не видит» снята."""
    s = Script(offer(PCX), final(FREE_TEXT))
    a, door = adapter(s)
    out = a.draft(NUMBER, 5)
    assert door.calls == [("PCX 160 1234", "2026-11-10", "2026-11-15")], door.calls
    r = offers(a)[0]
    assert r["outcome"] == T.FACT and r["tool"] == "offer" and r["source"] == O.SOURCE, r
    f = r["facts"][0]
    assert (f["kind"], f["model"], f["date_start"], f["date_end"], f["avail"], f["unit"], f["units"], f["free"]) == \
        ("offer", "PCX 160", "2026-11-10", "2026-11-15", B.FREE, "PCX 160 1234", 2, 2), f
    assert (f["day_price"], f["total"], f["deposit"], f["discount"], f["age"]) == (400, 2000, 3000, 0, 60.0), f
    assert r["read_at"] == T0 - 60.0 and f["read_at"] == T0 - 60.0 and r["at"] == T0, (r["read_at"], r["at"])
    block = offer_block(s.seen[1])
    assert "НАЛИЧИЕ (таблица броней, снимок 1 мин назад; свободный юнит сверен дверью цены): PCX 160, 2026-11-10 — " \
           "2026-11-15: свободно 2 из 2." in block, block
    assert ("ЦЕНА: 2026-11-10, 2026-11-15 — PCX 160: 5 сут., 400 ฿ в сутки, итого 2 000 ฿ за срок; скидка за срок 0%; "
            "депозит 3 000 ฿.") in block, block
    assert "1234" not in s.seen[1] and "5678" not in s.seen[1], "юнит в запрос модели не идёт"
    assert O.FACT_NOTE in block and (O.HEAD % 2) in block, block
    hand = out["handoff"]
    assert K.MONEY_CLAIM_WORDS not in hand and AVAIL_WORDS not in hand, hand
    assert B.W_AVAIL_UNKNOWN not in hand and K.DAYS_CLAIM_WORDS not in hand, hand
    assert out["claims"] == [], out["claims"]
    assert [ln for ln in a.lines if ln.startswith(O.LOG_HEAD)] == [
        O.LOG_HEAD + "вызовов 1: факт 1 (свободно 1, занято 0), не факт 0 (предел 0), дверь цены 1, кеш 0"], a.lines
    fact_lines = [ln for ln in a.lines if "offer факт" in ln]
    assert len(fact_lines) == 1 and '"unit": "PCX 160 1234"' in fact_lines[0], fact_lines
    assert not [ln for ln in a.lines if NUMBER in ln], "номера клиента в журнале нет"
    # близнец: без примеси — «offer» неизвестный инструмент, фактов нет, «агент их не видит» на месте, деньги без опоры
    s0 = Script(offer(PCX), final(FREE_TEXT))
    a0, door0 = adapter(s0, mixin=False)
    out0 = a0.draft(NUMBER, 5)
    assert door0.calls == [] and "offers" not in a0.last["tools"], door0.calls
    assert a0.last["tools"]["results"][0]["reason"] == "неизвестный инструмент"
    assert AVAIL_WORDS in out0["handoff"] and K.MONEY_CLAIM_WORDS in out0["handoff"], out0["handoff"]
    assert "offer {" not in s0.seen[0] and O.OFFER_BLOCK in s.seen[0], "строка инструмента — только с примесью"


def test_o1_tools_block_line_only_addition():
    """Модель offer не звала: запрос первого хода — родительский плюс ровно строка инструмента после блока инструментов."""
    s, s0 = Script(final("Здравствуйте!")), Script(final("Здравствуйте!"))
    adapter(s)[0].draft(NUMBER, 5)
    adapter(s0, mixin=False)[0].draft(NUMBER, 5)
    head = T.TOOLS_BLOCK % T.MAX_CALLS
    assert s.seen[0] == s0.seen[0].replace(head, head + "\n" + O.OFFER_BLOCK, 1), (s.seen[0][:300], s0.seen[0][:300])


def test_o1_door_model_like_unit_not_echoed():
    """r3 (юнит — сотруднику, клиенту — модель): слово двери «model», похожее на юнит (имя юнита, его номер, «… PHUKET
    3011»), в строку цены модели не идёт — вместо него модель парка; близнец — имя модели прайса («HONDA PCX 160», так
    по копии моста в дереве) — как было. Юнит — по-прежнему в журнале."""
    for name in ("PCX 160 1234", "PCX 160CC WHITE PHUKET 3011", "Honda PCX 160 1234"):
        s = Script(offer(PCX), final(FREE_TEXT))
        a, _d = adapter(s, door=Door(name=name))
        a.draft(NUMBER, 5)
        block = offer_block(s.seen[1])
        assert "ЦЕНА: 2026-11-10, 2026-11-15 — PCX 160: 5 сут." in block, (name, block)
        assert "1234" not in s.seen[1] and "3011" not in s.seen[1] and "PHUKET" not in s.seen[1], (name, block)
        assert [ln for ln in a.lines if "offer факт" in ln and '"unit": "PCX 160 1234"' in ln], a.lines
    s0 = Script(offer(PCX), final(FREE_TEXT))
    adapter(s0, door=Door(name="HONDA PCX 160"))[0].draft(NUMBER, 5)
    assert "ЦЕНА: 2026-11-10, 2026-11-15 — HONDA PCX 160: 5 сут." in offer_block(s0.seen[1]), offer_block(s0.seen[1])
    units = ["PCX 160 1234", "PCX 160 5678"]
    for name, want in (("PCX 160 1234", True), ("pcx 160 5678", True), ("PCX 160CC WHITE PHUKET 3011", True),
                       ("HONDA PCX 160", False), ("PCX 160", False), ("YAMAHA XMAX300 2020-2022", False),
                       ("YAMAHA XMAX 300 NEW 2023-", False), ("", False), (None, False)):
        assert O.unit_like(name, units) is want, (name, want)


# ══ О2: занято → альтернатива ═════════════════════════════════════════════════════════════════════════════════

def test_o2_busy_then_alternative():
    """(б) PCX 160 занят на все юниты → FACT «занято» без двери, строка разрешает проверить альтернативу; модель зовёт
    offer NMAX на те же даты → свободно, дверь одна; текст с ценой альтернативы — с опорой; занятое свободным не названо —
    это проверяет код (`avail_mismatch`), а не сценарий модели: близнец, назвавший PCX 160 свободным, причину не снимает."""
    text = "PCX 160 на 10–15 ноября занят. Свободен NMAX 155: 400 ฿ в сутки, итого 2 000 ฿, депозит 3 000 ฿."
    s = Script(offer(PCX), offer(NMAX), final(text))
    a, door = adapter(s, rows=BUSY_PCX)
    out = a.draft(NUMBER, 5)
    got = offers(a)
    assert [r["outcome"] for r in got] == [T.FACT, T.FACT], [(r["outcome"], r["reason"]) for r in got]
    assert got[0]["facts"][0]["avail"] == B.BUSY and got[0]["facts"][0]["unit"] is None, got[0]["facts"]
    assert got[0]["offer"]["quote"] is None and got[0]["offer"]["door_calls"] == 0, got[0]["offer"]
    assert got[1]["facts"][0]["avail"] == B.FREE and got[1]["facts"][0]["unit"] == "NMAX 155 7001", got[1]["facts"]
    assert door.calls == [("NMAX 155 7001", "2026-11-10", "2026-11-15")], door.calls
    block1 = offer_block(s.seen[1])
    want = ("НАЛИЧИЕ (таблица броней, снимок 1 мин назад; прочитаны все юниты модели): PCX 160, 2026-11-10 — 2026-11-15: "
            "заняты все 2. Можно сказать, что на эти даты этой модели нет. Другую модель или другие даты можно "
            "проверить вызовом offer")
    assert want in block1 and "ЦЕНА: " not in block1 and "฿" not in block1 and "коллега подберёт" not in block1, block1
    assert "NMAX 155, 2026-11-10 — 2026-11-15: свободно 1 из 1" in offer_block(s.seen[2]), offer_block(s.seen[2])
    assert K.MONEY_CLAIM_WORDS not in out["handoff"] and AVAIL_WORDS not in out["handoff"], out["handoff"]
    assert O.W_AVAIL_MISMATCH not in out["handoff"] and not [ln for ln in a.lines if "не совпадает" in ln], a.lines
    # близнец: сумма не из факта (2 800) — «денежное утверждение без опоры»
    s2 = Script(offer(PCX), offer(NMAX), final(text.replace("2 000", "2 800")))
    out2 = adapter(s2, rows=BUSY_PCX)[0].draft(NUMBER, 5)
    assert K.MONEY_CLAIM_WORDS in out2["handoff"], out2["handoff"]
    # близнец (приёмка): тот же ход, но занятый PCX 160 назван свободным — «агент их не видит» не снята, расхождение
    s3 = Script(offer(PCX), offer(NMAX), final(text.replace("занят", "свободен")))
    a3, _d3 = adapter(s3, rows=BUSY_PCX)
    out3 = a3.draft(NUMBER, 5)
    assert AVAIL_WORDS in out3["handoff"] and O.W_AVAIL_MISMATCH in out3["handoff"], out3["handoff"]
    assert O.LOG_HEAD + O.L_MISMATCH % (O.M_BUSY % "PCX 160") in a3.lines, a3.lines


def test_o2_busy_called_free_keeps_reason():
    """Приёмка (замечание major): offer сказал «занято», а черновик назвал ту же модель свободной («PCX 160 на эти даты
    свободен») → причины как без флага («агент их не видит» на месте) плюс «наличие в тексте не совпадает с проверкой»,
    строка журнала с моделью. Близнецы: флаг выкл — «агент их не видит»; «занят» — снята, расхождения нет."""
    text = "PCX 160 на эти даты свободен."
    a, door = adapter(Script(offer(PCX), final(text)), rows=BUSY_PCX)
    out = a.draft(NUMBER, 5)
    assert offers(a)[0]["facts"][0]["avail"] == B.BUSY and door.calls == [], offers(a)[0]
    assert [ln for ln in a.lines if "не совпадает" in ln] == [O.LOG_HEAD + O.L_MISMATCH % (O.M_BUSY % "PCX 160")], a.lines
    out0 = adapter(Script(offer(PCX), final(text)), rows=BUSY_PCX, mixin=False)[0].draft(NUMBER, 5)
    assert AVAIL_WORDS in out0["handoff"], out0["handoff"]
    assert out["handoff"] == out0["handoff"] + [O.W_AVAIL_MISMATCH], (out["handoff"], out0["handoff"])
    a1, _d1 = adapter(Script(offer(PCX), final("PCX 160 на эти даты занят.")), rows=BUSY_PCX)
    out1 = a1.draft(NUMBER, 5)
    assert AVAIL_WORDS not in out1["handoff"] and O.W_AVAIL_MISMATCH not in out1["handoff"], out1["handoff"]
    assert not [ln for ln in a1.lines if "не совпадает" in ln], a1.lines
    # клиент о наличии не спрашивал (причины кода «агент их не видит» нет) — расхождение всё равно причина
    out2 = adapter(Script(offer(PCX), final(text)), rows=BUSY_PCX, reasons=[])[0].draft(NUMBER, 5)
    assert O.W_AVAIL_MISMATCH in out2["handoff"], out2["handoff"]
    # «свободен» без модели при занятом — тоже расхождение; при одном свободном факте — нет
    out3 = adapter(Script(offer(PCX), final("Да, свободен!")), rows=BUSY_PCX)[0].draft(NUMBER, 5)
    assert AVAIL_WORDS in out3["handoff"] and O.W_AVAIL_MISMATCH in out3["handoff"], out3["handoff"]
    out4 = adapter(Script(offer(PCX), final("Да, свободен!")))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out4["handoff"] and O.W_AVAIL_MISMATCH not in out4["handoff"], out4["handoff"]


def test_o2_unchecked_model_called_free_keeps_reason():
    """Свободной названа модель, которую offer не проверял (XMAX 300 при факте PCX 160 «свободно»), — причина не
    снимается; пересказ модели «агент их не видит» тоже остаётся; близнец — только проверенная модель."""
    out = adapter(Script(offer(PCX), final("PCX 160 свободен, XMAX 300 тоже.", [AVAIL_WORDS])))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS in out["handoff"] and O.W_AVAIL_MISMATCH in out["handoff"], out["handoff"]
    out0 = adapter(Script(offer(PCX), final("PCX 160 свободен.", [AVAIL_WORDS])))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out0["handoff"] and O.W_AVAIL_MISMATCH not in out0["handoff"], out0["handoff"]


R3_FREE_TEXTS = ("We have NMAX 155 for these dates.", "Также можем предложить NMAX 155.", "NMAX 155 ждёт вас.",
                 "PCX 160 isn't available, but NMAX 155 is.", "PCX 160 занят, а NMAX 155 — да.")


def test_r3_free_claim_without_free_word_keeps_reason():
    """r3 (замечание major, закрыто наглухо): «свободно» без слова «свободно» — «We have NMAX 155», «можем предложить»,
    «ждёт вас», «…, but NMAX 155 is.», «…, а NMAX 155 — да.» — рядом с принятым фактом PCX 160: NMAX 155 не проверен —
    «агент их не видит» на месте и «не совпадает с проверкой» (r2 причину снимал). Близнец: NMAX 155 проверен свободным —
    снята, расхождения нет."""
    for text in R3_FREE_TEXTS:
        a, _d = adapter(Script(offer(PCX), final(text)), rows=BUSY_PCX)
        out = a.draft(NUMBER, 5)
        assert offers(a)[0]["facts"][0]["avail"] == B.BUSY, (text, offers(a)[0]["reason"])
        assert AVAIL_WORDS in out["handoff"] and O.W_AVAIL_MISMATCH in out["handoff"], (text, out["handoff"])
        assert O.LOG_HEAD + O.L_MISMATCH % (O.M_UNCHECKED % "NMAX 155") in a.lines, (text, a.lines)
        out2 = adapter(Script(offer(PCX), offer(NMAX), final(text)), rows=BUSY_PCX)[0].draft(NUMBER, 5)
        assert AVAIL_WORDS not in out2["handoff"] and O.W_AVAIL_MISMATCH not in out2["handoff"], (text, out2["handoff"])


def test_r3_other_dates_keep_reason():
    """r3: та же модель на ДРУГИЕ даты — проверено 10–15 ноября, в тексте «с 18 по 22 ноября» — причина на месте и
    расхождение «на 18–22 не проверен»; даты без модели в соседнем предложении — тоже; близнец — даты проверки."""
    for text, why in (("PCX 160 свободен с 18 по 22 ноября.", O.M_DATES % ("PCX 160", "с 18.11 по 22.11")),
                      ("PCX 160 свободен. Аренда с 18 по 22 ноября — 2 000 ฿.", O.M_DATES_ANY % "с 18.11 по 22.11")):
        a, _d = adapter(Script(offer(PCX), final(text)))
        out = a.draft(NUMBER, 5)
        assert AVAIL_WORDS in out["handoff"] and O.W_AVAIL_MISMATCH in out["handoff"], (text, out["handoff"])
        assert O.LOG_HEAD + O.L_MISMATCH % why in a.lines, (text, a.lines)
    out0 = adapter(Script(offer(PCX), final("PCX 160 свободен с 10 по 15 ноября.")))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out0["handoff"] and O.W_AVAIL_MISMATCH not in out0["handoff"], out0["handoff"]


def test_r3_book_words_in_draft_keep_reason():
    """r3: в тексте ЧЕРНОВИКА слова брони («забронировал», «оформим бронь», I've booked … for you) при входящем БЕЗ просьбы
    о брони — «агент их не видит» не снята, «бронь оформляет человек» добавлена, строка журнала; близнец без слов брони —
    снята, «бронь оформляет человек» нет. Модель offer не звала — как родитель (О6)."""
    assert not B.book_intent(Q)
    for text in ("PCX 160 свободен, забронировал его для вас.", "PCX 160 свободен — оформим бронь?",
                 "PCX 160 is available, I've booked it for you."):
        a, _d = adapter(Script(offer(PCX), final(text)))
        out = a.draft(NUMBER, 5)
        assert AVAIL_WORDS in out["handoff"] and B.W_BOOKING in out["handoff"], (text, out["handoff"])
        assert O.W_AVAIL_MISMATCH not in out["handoff"] and O.LOG_HEAD + O.L_BOOK_SAID in a.lines, (text, a.lines)
    out0 = adapter(Script(offer(PCX), final("PCX 160 свободен.")))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out0["handoff"] and B.W_BOOKING not in out0["handoff"], out0["handoff"]


def test_r3_unsure_keeps_reason_without_words():
    """r3: о модели в тексте нет слова наличия (и нигде больше) — «не сверено»: «агент их не видит» на месте, слов
    расхождения нет, строка журнала «не сверено»; близнец — о той же модели сказано «свободен» в другом предложении."""
    text = "PCX 160 свободен. Цена NMAX 155 — 400 ฿ в сутки."
    a, _d = adapter(Script(offer(PCX), offer(NMAX), final(text)))
    out = a.draft(NUMBER, 5)
    assert AVAIL_WORDS in out["handoff"] and O.W_AVAIL_MISMATCH not in out["handoff"], out["handoff"]
    assert O.LOG_HEAD + O.L_UNSURE % (O.U_STANCE % "NMAX 155") in a.lines, a.lines
    out0 = adapter(Script(offer(PCX), offer(NMAX), final(text + " NMAX 155 тоже свободен.")))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out0["handoff"] and O.W_AVAIL_MISMATCH not in out0["handoff"], out0["handoff"]


def test_o2_busy_numbers_are_not_support():
    """Занятая пара цены не даёт: её числа опорой не служат (дверь не звана), сумма в тексте — без опоры."""
    s = Script(offer(PCX), final("PCX 160 занят; обычно 400 ฿ в сутки."))
    a, door = adapter(s, rows=BUSY_PCX)
    out = a.draft(NUMBER, 5)
    assert door.calls == [] and offers(a)[0]["facts"][0]["avail"] == B.BUSY
    assert K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]


# ══ О3: ворота и отсевы — не факт, числа нет, причина человеку ══════════════════════════════════════════════════

def _not_fact(args, want_reason, want_words, rows=(), door=None, outcome=T.UNKNOWN, **kw):
    s = Script(offer(args), final("Коллега проверит наличие и вернётся."))
    a, d = adapter(s, rows=rows, door=door, **kw)
    out = a.draft(NUMBER, 5)
    r = offers(a)[0]
    assert r["outcome"] == outcome and r["facts"] == [] and want_reason in r["reason"], (r["outcome"], r["reason"])
    block = offer_block(s.seen[1])
    assert "свободно" not in block and "итого" not in block and "฿" not in block, block
    assert want_words in out["handoff"], (want_words, out["handoff"])
    assert AVAIL_WORDS in out["handoff"], "факта нет — «агент их не видит» на месте"
    return a, d, r, block


def test_o3_long_term_human_no_door():
    """≥30 суток → «считает человек» (ворота `K.quote`), двери нет; причина «срок от месяца и дольше»."""
    a, d, r, block = _not_fact({"model": "PCX 160", "date_from": "2027-06-01", "date_to": "2027-07-05"},
                               "считает человек: срок от месяца", K.REASON_WORDS[K.R_LONG_TERM])
    assert d.calls == [] and r["offer"]["gate"] == K.R_LONG_TERM and "Эту цену считает человек" in block, block
    # близнец: 29 суток того же сезона — дверь звана, факт
    s = Script(offer({"model": "PCX 160", "date_from": "2027-06-01", "date_to": "2027-06-30"}), final("ok"))
    a2, d2 = adapter(s)
    a2.draft(NUMBER, 5)
    assert offers(a2)[0]["outcome"] == T.FACT and len(d2.calls) == 1, offers(a2)[0]["reason"]


def test_o3_season_cross_human_no_door():
    """Стык сезонов (28.11 → 03.12: P3 → P4) → «считает человек», двери нет; близнец внутри P3 — факт."""
    a, d, r, _b = _not_fact({"model": "PCX 160", "date_from": "2026-11-28", "date_to": "2026-12-03"},
                            "через границу сезонов", K.REASON_WORDS[K.R_SEASON_CROSS])
    assert d.calls == [] and r["offer"]["gate"] == K.R_SEASON_CROSS
    s = Script(offer({"model": "PCX 160", "date_from": "2026-11-25", "date_to": "2026-11-30"}), final("ok"))
    a2, d2 = adapter(s)
    a2.draft(NUMBER, 5)
    assert offers(a2)[0]["outcome"] == T.FACT and len(d2.calls) == 1


def test_o3_no_snapshot_unknown():
    """Снимок не служит → «неизвестно», двери нет; причина «наличие не проверено — решает человек»."""
    a, d, r, _b = _not_fact(PCX, "таблица броней не прочитана", B.W_AVAIL_UNKNOWN, rows=None)
    assert d.calls == [] and r["offer"]["code"] == "snapshot"


def test_o3_no_door_unknown():
    """Двери цены нет → «неизвестно», снимок не читается."""
    s = Script(offer(PCX), final("Коллега проверит."))
    a, _d = adapter(s, door=False)
    out = a.draft(NUMBER, 5)
    r = offers(a)[0]
    assert r["outcome"] == T.UNKNOWN and r["reason"] == O.W_NO_DOOR and a.book.reads == 0, (r["reason"], a.book.reads)
    assert B.W_AVAIL_UNKNOWN in out["handoff"]


def test_o3_door_falls_or_disagrees():
    """Дверь упала (таймаут) или не подтвердила свободный юнит → «неизвестно», числа нет; близнец — факт."""
    _not_fact(PCX, "дверь цены упала (TimeoutError)", B.W_AVAIL_UNKNOWN, door=Door(fail=TimeoutError()))
    _not_fact(PCX, "таблица и дверь разошлись", B.W_AVAIL_UNKNOWN, door=Door(available=False))
    _not_fact(PCX, "дверь цены не ответила", B.W_AVAIL_UNKNOWN, door=Door(ok=False))


def test_o3_model_checks():
    """Модель не из парка, кубатура не из парка, неоднозначное сокращение, две модели, пусто — двери нет; близнецы."""
    _not_fact(dict(PCX, model="Vespa 150"), "нет в парке", B.W_AVAIL_UNKNOWN)
    _not_fact(dict(PCX, model="PCX 150"), "нет в парке", B.W_AVAIL_UNKNOWN)
    _not_fact(dict(PCX, model="PCX 160 или Vespa 150"), "«Vespa 150» нет в парке", B.W_AVAIL_UNKNOWN)
    a, d, r, block = _not_fact(dict(PCX, model="CB"), "подходит к моделям парка CB 300 / CB 650R", B.W_AVAIL_UNKNOWN,
                               outcome=T.AMBIGUOUS)
    assert d.calls == [] and O.ADV_MODEL in block, block
    _not_fact(dict(PCX, model="PCX 160 и NMAX 155"), "несколько моделей", B.W_AVAIL_UNKNOWN, outcome=T.AMBIGUOUS)
    _not_fact(dict(PCX, model=""), O.W_NO_MODEL, B.W_AVAIL_UNKNOWN)
    for m, key in (("CB 650R", "CB 650R"), ("pcx160", "PCX 160"), ("PCX 160CC WHITE", "PCX 160"), ("nmax", "NMAX 155")):
        assert O.model_of(m, BIKES)[0] == key, (m, O.model_of(m, BIKES))


def test_o3_dates_checks():
    """Даты не ISO, конец не позже начала, срок начался или прошёл → отказ до снимка; начало сегодня — можно."""
    for args, want in ((dict(PCX, date_from="10.11.2026"), O.W_DATES), (dict(PCX, date_to="2026-11-31"), O.W_DATES),
                       (dict(PCX, date_to="2026-11-10"), O.W_ORDER), (dict(PCX, date_to="2026-11-09"), O.W_ORDER),
                       (dict(PCX, date_from="2026-09-20", date_to="2026-09-25"), "срок уже начался или прошёл")):
        a, d, r, block = _not_fact(args, want, B.W_AVAIL_UNKNOWN, outcome=T.REFUSED)
        assert a.book.reads == 0 and d.calls == [] and O.ADV_DATES in block, (args, a.book.reads)
    s = Script(offer(dict(PCX, date_from="2026-09-21", date_to="2026-09-26")), final("ok"))
    a, d = adapter(s)
    a.draft(NUMBER, 5)
    assert offers(a)[0]["outcome"] == T.FACT, offers(a)[0]["reason"]


def test_o3_minimum_term_of_class():
    """NMAX на 2 суток — короче минимума скутера (5): наличие и цена на 5 суток одной дверью, строка «минимум 5 сут.»,
    в факте — сутки клиента."""
    s = Script(offer({"model": "NMAX 155", "date_from": "2026-11-10", "date_to": "2026-11-12"}), final("ok"))
    a, door = adapter(s)
    a.draft(NUMBER, 5)
    f = offers(a)[0]["facts"][0]
    assert door.calls == [("NMAX 155 7001", "2026-11-10", "2026-11-15")], door.calls
    assert (f["date_end"], f["days"], f["min_days"], f["client_days"], f["total"]) == ("2026-11-15", 5, 5, 2, 2000), f
    assert "минимум 5 сут." in offer_block(s.seen[1]) and "клиент назвал 2 сут" in offer_block(s.seen[1])


# ══ О4: предел, кеш, свежесть ═════════════════════════════════════════════════════════════════════════════════

def test_o4_fourth_call_refused_limit():
    """(е) 4-й offer в сверке → отказ «предел», ни снимка, ни двери; первые три — по двери на пару."""
    pairs = [dict(PCX, date_from="2026-11-%02d" % d, date_to="2026-11-%02d" % (d + 3)) for d in (10, 14, 18, 22)]
    s = Script(*[offer(p) for p in pairs] + [final("ok")])
    a, door = adapter(s)
    a.draft(NUMBER, 5)
    got = offers(a)
    assert [r["outcome"] for r in got] == [T.FACT, T.FACT, T.FACT, T.REFUSED], [r["reason"] for r in got]
    assert got[3]["reason"] == O.W_LIMIT and len(door.calls) == 3 and a.book.reads == 3, (door.calls, a.book.reads)
    assert O.ADV_LIMIT in offer_block(s.seen[4]) and (O.HEAD % 0) in offer_block(s.seen[4])
    assert O.LOG_HEAD + "вызовов 4: факт 3 (свободно 3, занято 0), не факт 1 (предел 1), дверь цены 3, кеш 0" in a.lines


def test_o4_same_pair_cached_one_door():
    """Повтор той же пары — ответ из кеша сверки, двери нет; принят один раз."""
    s = Script(offer(PCX), offer(dict(PCX, model="pcx 160")), final(FREE_TEXT))
    a, door = adapter(s)
    out = a.draft(NUMBER, 5)
    got = offers(a)
    assert len(door.calls) == 1 and got[1]["offer"]["cached"] and O.W_CACHED in got[1]["reason"], got[1]
    assert len(O.accepted(got)) == 1 and K.MONEY_CLAIM_WORDS not in out["handoff"]


def test_o4_stale_fact_not_support():
    """(в) вызов offer раньше последнего входящего клиента — не опора: сумма без опоры, «агент их не видит» на месте
    (порядок искусственный: новое входящее обрывает сверку, `fresh`; живой порядок — `test_o4_old_snapshot_*`)."""
    s = Script(offer(PCX), final(FREE_TEXT))
    a, _d = adapter(s, last_in=T0 + 5)
    out = a.draft(NUMBER, 5)
    assert offers(a)[0]["outcome"] == T.FACT and O.accepted(offers(a), T0 + 5) == []
    assert K.MONEY_CLAIM_WORDS in out["handoff"] and AVAIL_WORDS in out["handoff"], out["handoff"]
    s2 = Script(offer(PCX), final(FREE_TEXT))
    out2 = adapter(s2, last_in=T0 - 90)[0].draft(NUMBER, 5)
    assert K.MONEY_CLAIM_WORDS not in out2["handoff"] and AVAIL_WORDS not in out2["handoff"], out2["handoff"]


def test_o4_old_snapshot_busy_not_fact():
    """r3, живой порядок: снимок таблицы прочитан в T0−60, клиент написал в T0−5, offer зван в T0. «Занято» — только по
    снимку (дверь не зовётся), а он старше входящего — не факт: «неизвестно» со словами о снимке, модели нет строки «на
    эти даты этой модели нет», «агент их не видит» на месте и «наличие не проверено». Близнец: входящее в T0−90 (до
    снимка) — факт «занято», причина снята."""
    text = "PCX 160 на эти даты занят."
    s = Script(offer(PCX), final(text))
    a, door = adapter(s, rows=BUSY_PCX, last_in=T0 - 5)
    out = a.draft(NUMBER, 5)
    r = offers(a)[0]
    assert (r["outcome"], r["offer"]["code"], r["reason"], r["facts"]) == (T.UNKNOWN, "old_busy", O.W_OLD_BUSY % 1, []), r
    assert door.calls == [] and r["read_at"] == T0 - 60.0 and r["at"] == T0, (door.calls, r["read_at"])
    block = offer_block(s.seen[1])
    assert O.NOT_LINE % (O.W_OLD_BUSY % 1, O.ADV_LATER) in block and "заняты все" not in block, block
    assert AVAIL_WORDS in out["handoff"] and B.W_AVAIL_UNKNOWN in out["handoff"], out["handoff"]
    assert not [ln for ln in a.lines if "offer факт" in ln], a.lines
    a0, _d0 = adapter(Script(offer(PCX), final(text)), rows=BUSY_PCX, last_in=T0 - 90)
    out0 = a0.draft(NUMBER, 5)
    assert offers(a0)[0]["outcome"] == T.FACT and offers(a0)[0]["facts"][0]["avail"] == B.BUSY
    assert AVAIL_WORDS not in out0["handoff"] and B.W_AVAIL_UNKNOWN not in out0["handoff"], out0["handoff"]


def test_o4_old_snapshot_free_is_fact_without_counts():
    """r3: «свободно» сверено дверью цены В МОМЕНТ ВЫЗОВА — при снимке старше входящего это факт (причина снята, цена —
    опора), но число свободных из старого снимка модели не называется; в журнале — «снимок старше». Близнец: снимок
    после входящего — строка с числом «свободно 2 из 2»."""
    s = Script(offer(PCX), final(FREE_TEXT))
    a, door = adapter(s, last_in=T0 - 5)
    out = a.draft(NUMBER, 5)
    r = offers(a)[0]
    assert r["outcome"] == T.FACT and r["facts"][0]["snap_old"] is True and len(door.calls) == 1, r
    block = offer_block(s.seen[1])
    assert O.FREE_OLD_LINE % (1, "PCX 160", "2026-11-10", "2026-11-15") in block, block
    assert "свободно 2 из 2" not in block and "ЦЕНА: 2026-11-10, 2026-11-15 — PCX 160" in block, block
    assert AVAIL_WORDS not in out["handoff"] and K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]
    assert [ln for ln in a.lines if "offer факт" in ln and '"snapshot_old": true' in ln], a.lines
    s0 = Script(offer(PCX), final(FREE_TEXT))
    adapter(s0, last_in=T0 - 90)[0].draft(NUMBER, 5)
    assert "свободно 2 из 2" in offer_block(s0.seen[1]), offer_block(s0.seen[1])


def test_o4_accepted_busy_on_snapshot_time_pure():
    """`accepted`: «занято» — по времени СНИМКА (`read_at`) против последнего входящего; «свободно» — по времени вызова
    (ответ двери); времени снимка нет — «занято» не принято; входящего нет — не судим (как `T.stale`)."""
    busy = {"outcome": T.FACT, "at": T0, "read_at": T0 - 60, "offer": {"model": "PCX 160", "avail": B.BUSY,
                                                                      "date_from": "2026-11-10", "date_to": "2026-11-15"}}
    free = dict(busy, offer=dict(busy["offer"], avail=B.FREE))
    blind = dict(busy, read_at=None)
    assert O.accepted([busy], T0 - 5) == [] and O.accepted([busy], T0 - 90) == [busy] and O.accepted([busy]) == [busy]
    assert O.accepted([free], T0 - 5) == [free] and O.accepted([free], T0 + 5) == []
    assert O.accepted([blind], T0 - 5) == [] and O.accepted([blind]) == [blind]
    assert O.snap_fresh(T0, T0) and not O.snap_fresh(T0 - 1, T0) and not O.snap_fresh(None, T0)
    assert not O.snap_fresh(True, 0) and O.snap_fresh(None, None)


def test_o4_over_limit_fallback_drops_offers():
    """Предел вызовов модели — запасной вызов без фактов: факты offer тоже не опора, «сверка не завершена» первой."""
    s = Script(offer(PCX), offer(NMAX), final(FREE_TEXT))
    a, _d = adapter(s)
    got = O.run(s, "SYSTEM", "USER", {}, O.Offers(a, TODAY), clock=Clock(), max_calls=2)
    assert got["state"] == T.OVER and len(got["offers"]) == 2 and got["results"] == [], got["state"]
    # путь адаптера: offer на каждом ходе до предела вызовов модели — запасной вызов, факты offer не опора
    s2 = Script(*([offer(PCX)] * T.MAX_CALLS + [final(FREE_TEXT)]))
    a2, _d2 = adapter(s2)
    out = a2.draft(NUMBER, 5)
    assert len(s2.seen) == T.MAX_CALLS + 1 and a2.last["tools"]["state"] == T.OVER, len(s2.seen)
    assert out["handoff"][0] == T.INCOMPLETE_WORDS and K.MONEY_CLAIM_WORDS in out["handoff"], out["handoff"]
    assert AVAIL_WORDS in out["handoff"], out["handoff"]


# ══ О5: суд — деньги, скидка, бронь, пересказ модели ═════════════════════════════════════════════════════════════

def test_o5_discount_percent_from_fact():
    """(д) процент скидки за срок из факта offer — с опорой (снят `without_known_discount` тем же путём); другой — нет."""
    s = Script(offer(PCX), final("PCX 160 свободен, скидка за срок 0%."))
    out = adapter(s)[0].draft(NUMBER, 5)
    assert K.MONEY_CLAIM_WORDS not in out["handoff"], out["handoff"]
    s2 = Script(offer(PCX), final("PCX 160 свободен, скидка за срок 10%."))
    out2 = adapter(s2)[0].draft(NUMBER, 5)
    assert K.MONEY_CLAIM_WORDS in out2["handoff"], out2["handoff"]


def test_o5_discount_unknown_reason():
    """Дверь не назвала скидку за срок → причина «скидка за срок неизвестна» (как у цены, `K.handoff`)."""
    s = Script(offer(PCX), final("PCX 160 свободен."))
    out = adapter(s, door=Door(discount=None))[0].draft(NUMBER, 5)
    assert K.DISCOUNT_UNKNOWN_WORDS in out["handoff"], out["handoff"]
    out2 = adapter(Script(offer(PCX), final("PCX 160 свободен.")))[0].draft(NUMBER, 5)
    assert K.DISCOUNT_UNKNOWN_WORDS not in out2["handoff"], out2["handoff"]


def test_o5_booking_words_stay():
    """Просьба о брони: факт снимает «агент их не видит», «бронь оформляет человек» остаётся."""
    q = "а свободен? хочу забронировать"
    out = adapter(Script(offer(PCX), final("PCX 160 свободен.")), question=q)[0].draft(NUMBER, 5)
    assert B.W_BOOKING in out["handoff"] and AVAIL_WORDS not in out["handoff"], out["handoff"]


def test_o5_model_echo_dropped_only_with_fact():
    """Пересказ моделью «наличие и брони — агент их не видит» снимается только при принятом факте."""
    out = adapter(Script(offer(PCX), final("PCX 160 свободен.", [AVAIL_WORDS])))[0].draft(NUMBER, 5)
    assert AVAIL_WORDS not in out["handoff"], out["handoff"]
    out2 = adapter(Script(offer(PCX), final("Коллега проверит.", [AVAIL_WORDS])), rows=None)[0].draft(NUMBER, 5)
    assert AVAIL_WORDS in out2["handoff"], out2["handoff"]


def test_o5_code_unknown_block_is_senior():
    """Старшинство при двух источниках (наличие по переписке / хвост и offer): «неизвестно» блока кода offer НЕ снимает
    — «наличие не проверено — решает человек» остаётся; снимается только «агент их не видит»."""
    unknown = B._avail_unknown(B._avail_base("PCX 160", None, None, [], None), "пары переписки разошлись")
    reasons = B.adjust_reasons(K.handoff(Q, None), unknown, None, Q) + [
        {"reason": K.R_AVAILABILITY, "words": AVAIL_WORDS, "why": "слово"}]
    out = adapter(Script(offer(PCX), final("PCX 160 свободен.")), reasons=reasons, avail=unknown)[0].draft(NUMBER, 5)
    assert B.W_AVAIL_UNKNOWN in out["handoff"] and AVAIL_WORDS not in out["handoff"], out["handoff"]


def test_o5_offer_is_not_rental_payment_or_due():
    """(ж) факт offer не даёт аренды, оплаты и итога «к оплате»: в results и опоре сверки его нет."""
    s = Script(offer(PCX), final("PCX 160 свободен."))
    a, _d = adapter(s)
    a.draft(NUMBER, 5)
    tools = a.last["tools"]
    assert not [r for r in tools["results"] if r["tool"] == "offer"], tools["results"]
    assert not [f for f in tools["journal"].facts if f.get("kind") == "offer"]
    assert T.rental_of(tools["journal"].facts) is None and not T.pay_verdict(tools["journal"].facts)[0]
    assert T.due_block(tools["results"]) == "" and a.last["figures"]["sums"] == {}
    assert "К ОПЛАТЕ" not in s.seen[1].upper().replace("НЕ К ОПЛАТЕ", ""), s.seen[1][-400:]


OTHER_TERM = [{"ds": datetime.date(2026, 11, 1), "de": datetime.date(2026, 11, 4), "days": 3}]   # «СРОКИ»: 3 сут.


def test_o5_days_and_dates_supported_by_fact():
    """Сутки и день черновика — с опорой на срок факта offer: «за 5 суток» при «СРОКАХ» клиента в 3 суток и «доставим 10
    ноября» причин не дают; близнецы — факт устарел (прочитан раньше последнего входящего): обе причины на месте."""
    text = "PCX 160 свободен. Цена: 400 ฿ в сутки, итого 2 000 ฿ за 5 суток. Доставим 10 ноября."
    out = adapter(Script(offer(PCX), final(text)), terms=OTHER_TERM)[0].draft(NUMBER, 5)
    assert K.DAYS_CLAIM_WORDS not in out["handoff"] and K.ARRIVAL_CLAIM_WORDS not in out["handoff"], out["handoff"]
    out2 = adapter(Script(offer(PCX), final(text)), terms=OTHER_TERM, last_in=T0 + 5)[0].draft(NUMBER, 5)
    assert K.DAYS_CLAIM_WORDS in out2["handoff"] and K.ARRIVAL_CLAIM_WORDS in out2["handoff"], out2["handoff"]
    out3 = adapter(Script(offer(PCX), final(text.replace("за 5 суток", "за 6 суток"))),
                   terms=OTHER_TERM)[0].draft(NUMBER, 5)
    assert K.DAYS_CLAIM_WORDS in out3["handoff"], out3["handoff"]


# ══ О6: флаг выкл и модель без offer — как родитель ═══════════════════════════════════════════════════════════

def _strip(last):
    """`self.last` для сравнения: журнал — строками, ответов offer нет (у родителя их нет)."""
    out = dict(last)
    if "tools" in out:
        t = dict(out["tools"])
        t.pop("offers", None)
        t["journal"] = t["journal"].lines()
        out["tools"] = t
    return out


def test_o6_no_offer_call_equals_parent():
    """Модель offer не звала → черновик, `last` (без ответов offer), журнал и двери равны родителю — сценарии: итог сразу,
    касса + итог, предел вызовов (запасной вызов), новое входящее (обрыв), ответ не JSON."""
    cash = lambda **kw: {"ok": True, "checked": {"span_from": "2026-09-01", "span_to": "2026-10-03",  # noqa: E731
                                                 "rows_scanned": 3, "complete": True}, "items": []}
    pay = "оплатил 4900 бат за аренду"
    cases = [
        (lambda: Script(final("Здравствуйте! 2 800 бат.")), {}),
        (lambda: Script({"tool": "cash", "args": {"bike": "PCX 160 1234"}}, final("Оплата получена.")), {}),
        (lambda: Script({"tool": "cash", "args": {}}, final("Да, 4900 получили, спасибо!")), {"question": pay}),
        (lambda: Script({"tool": "history", "args": {}}), {}),
        (lambda: Script(final("x")), {"fresh": True}),
        (lambda: Script("не JSON"), {}),
        (lambda: Script(final("Аренда с 5 по 7 октября — 3 суток, доставим завтра в 15:00, скидка 10%.",
                              [AVAIL_WORDS, "нужна скидка"])), {"terms": OTHER_TERM}),
        (lambda: Script({"text": "Hello", "handoff": [], "lang": "th", "why": "x"}), {"hint": True}),
        (lambda: Script(final("Здравствуйте, подскажу.")), {"conv": ("en", 3, 3)}),
        (lambda: Script(final("Забронировал PCX 160 для вас, свободен.")), {}),   # r3: слова брони без offer
        (lambda: Script(final("Свободен, скидка за срок 0%, 2 800 бат.")), {"price": {
            "line": "2026-11-10, 2026-11-17 — PCX 160: 7 сут., 400 ฿ в сутки, итого 2 800 ฿ за срок; скидка за срок 0%.",
            "outcome": "number", "discount": 0, "days": 7, "date_start": "2026-11-10", "date_end": "2026-11-17"}}),
    ]
    for make, opt in cases:
        got = []
        for mixin in (True, False):
            s = make()
            a, door = adapter(s, mixin=mixin, tools={"cash": cash}, question=opt.get("question", Q),
                              terms=opt.get("terms", ()), conv=opt.get("conv"),
                              price=opt.get("price", {"line": "ЦЕНА: 2 800 ฿", "outcome": "number"}))
            if opt.get("fresh"):
                a.fresh = lambda number, upto_id: True
            res = a.redraft_checked(NUMBER, 5, "прежний", "пояснение") if opt.get("hint") else a.draft(NUMBER, 5)
            got.append((res, _strip(a.last), list(a.lines), door.calls, len(s.seen)))
        assert got[0] == got[1], (opt, [x for x, y in zip(got[0], got[1]) if x != y])
        assert got[0][0] is None or got[0][0]["handoff"] or opt.get("hint"), got[0][0]


def test_o6_flag_off_service_probe():
    """(з) + OFFER-OFFPIN1910: отдельный процесс, окружение которого САМО просит offer (WA_AGENT_OFFER=1 вместе с
    WA_AGENT_TOOLS, WA_AGENT_BOOK_READ и WA_AGENT_PRICE_CARRY). Флаг не запрошен, «0», 1 без сверки, 1 и true картой
    прогона, 1 окружением процесса — модуля выпуска в процессе нет ни в одном прогоне, класс адаптера прежний (ни
    примеси offer, ни цены через ход), строки старта об offer нет (и «не засчитан» тоже: окружение не читается), строки
    старта включённых прогонов те же, что у невключённого; блок инструментов сверки без строки offer."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("WA_AGENT_")}
    env.update(PROBE_ENV, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], capture_output=True, timeout=300,
                       env=env, cwd=ROOT)
    out = p.stdout.decode("utf-8", "replace")
    line = next((ln for ln in out.splitlines() if ln.startswith(PROBE_MARK)), None)
    assert p.returncode == 0 and line, (p.returncode, out[-800:], p.stderr.decode("utf-8", "replace")[-800:])
    got = json.loads(line[len(PROBE_MARK):])
    assert got["mods"] == [], got["mods"]
    runs = got["runs"]
    assert [r["type"] for r in runs] == ["ModelAdapter"] * 6, [r["type"] for r in runs]
    assert [r["offer"] for r in runs] == [[]] * 6, [r["offer"] for r in runs]
    assert runs[5]["env"] == PROBE_ENV, runs[5]["env"]                        # окружение процесса и правда просило ВКЛ
    assert runs[1]["lines"] == runs[0]["lines"] and runs[0]["n"] > 0, (runs[0]["lines"], runs[1]["lines"])
    for r in runs[3:]:
        assert r["lines"] == runs[0]["lines"], [x for x in r["lines"] if x not in runs[0]["lines"]]
    assert got["calls"] >= 1 and not got["offer_in_block"] and got["block_head"], got


# ══ О7: служба ════════════════════════════════════════════════════════════════════════════════════════════════

def _svc_model(tools=True, book=True):
    import wa_agent_svc as S
    br = types.SimpleNamespace(tx_find=lambda **k: {}, contract_find=lambda **k: {}, contract_pdf=lambda **k: {},
                               fleet=lambda: {"ok": True, "bikes": BIKES}, quote_price=Door(),
                               _call=lambda *a, **k: {}, clients=lambda **k: {"ok": True, "data": {"clients": []}})
    model, _ = S.make_model({"queue_db": ":memory:"}, bridge=br, call=Script(final("x")), tools=tools, book=book)
    return S, model


def test_o7_offer_of_counted_only_with_tools_book_door():
    S, model = _svc_model()
    on = {"WA_AGENT_OFFER": "1", "WA_AGENT_TOOLS": "1", "WA_AGENT_BOOK_READ": "1"}
    assert S.offer_of({}, model) == (None, None) and S.offer_of({"WA_AGENT_OFFER": "0"}, model) == (None, None)
    ok, words = S.offer_of(dict(on, WA_AGENT_TOOLS="0"), model)
    assert ok is False and "сверки Т4а нет" in words and type(model) is M.ModelAdapter, words
    ok, words = S.offer_of(dict(on, WA_AGENT_BOOK_READ="0"), model)
    assert ok is False and "брони (WA_AGENT_BOOK_READ) выключены" in words and type(model) is M.ModelAdapter, words
    _S, bare = _svc_model(tools=False)
    assert S.offer_of(on, bare)[0] is False and type(bare) is M.ModelAdapter
    ok, words = S.offer_of(on, model)
    assert ok is True and words.startswith("вкл — в сверке Т4а модель сама зовёт offer") and "не больше 3" in words
    assert type(model).__name__ == "OfferModelAdapter" and isinstance(model, O.OfferMixin), type(model)
    assert S.offer_of(on, model)[0] is True and type(model).__name__ == "OfferModelAdapter", "повтор — тот же класс"
    assert S.F_OFFER == "WA_AGENT_OFFER" and S.F_OFFER not in S.FLAGS


def test_o7_parent_drift_refuses():
    """Копия не сверена (исходник родителя изменился) или у класса свой `_draft_tools` → «не засчитан», класс прежний."""
    S, model = _svc_model()
    on = {"WA_AGENT_OFFER": "1", "WA_AGENT_TOOLS": "1", "WA_AGENT_BOOK_READ": "1"}
    was = dict(O.PARENT_SHA)
    try:
        O.PARENT_SHA["wa_agent_tools.run"] = "0" * 64
        ok, words = S.offer_of(on, model)
        assert ok is False and type(model) is M.ModelAdapter, (ok, words)
        assert words == "не засчитан — копия сверки Т4а не сверена (исходник родителя изменился: wa_agent_tools.run) " \
                        "— адаптер прежний", words
    finally:
        O.PARENT_SHA.clear()
        O.PARENT_SHA.update(was)
    own = type("Own", (M.ModelAdapter,), {"_draft_tools": lambda self, n, u, hint=None: None})
    try:
        O.with_offer(own)
        raise AssertionError("свой _draft_tools — примесь не надевается")
    except O.ParentDrift as e:
        assert "свой _draft_tools" in str(e), e
    assert O.drift() == [], O.drift()


def _svc_world():
    import test_wa_agent_model as TM
    import test_wa_book_read as TB
    import wa_agent_svc as S
    w = TM.World()
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}

    def make():
        br = TB.Bridge([])
        br.tx_find, br.contract_find, br.contract_pdf = (lambda **k: {}), (lambda **k: {}), (lambda **k: {})
        return S.make_model(env, bridge=br, call=lambda s, u: ("", {}), book=True, tools=True)[0]
    return S, w, env, make


def test_o7_build_env_on_pinned_off():
    """OFFER-OFFPIN1910: окружение просит ВКЛ («1», «true»; с наличием по переписке и ценой через ход и без) — `build()`
    даёт `offer_of` свою карту «0»: `import wa_offer_tool` не исполнялся ни разу (подмена `__import__`), примеси нет,
    строки старта об offer нет, строки старта те же, что без флага."""
    import builtins
    S, w, env, make = _svc_world()
    on = {"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_TOOLS": "1"}
    real_import, asked = builtins.__import__, []

    def spy(name, *a, **k):
        if name.split(".")[0] == NEW_MODULE:
            asked.append(name)
        return real_import(name, *a, **k)
    got = {}
    for key, extra in (("off", {}), ("1", {S.F_OFFER: "1"}), ("true", {S.F_OFFER: "true"}),
                       ("ctx", {S.F_BOOK_CTX: "1"}), ("ctx1", {S.F_BOOK_CTX: "1", S.F_OFFER: "1",
                                                               S.F_PRICE_CARRY: "1"})):
        model, lines = make(), []
        builtins.__import__ = spy
        try:
            S.build(dict(env, agent_db=w.dbpath + key), environ=dict(on, **extra), model=model, line=lines.append)
        finally:
            builtins.__import__ = real_import
        assert not any(c is O.OfferMixin for c in type(model).__mro__), (key, type(model).__mro__)
        assert type(model).__name__ == ("BookCtxModelAdapter" if S.F_BOOK_CTX in extra else "ModelAdapter"), key
        assert [ln for ln in lines if S.F_OFFER in ln or ln.startswith("наличие и цена по запросу")] == [], key
        got[key] = lines
    assert asked == [], asked
    assert got["1"] == got["off"] and got["true"] == got["off"] and got["ctx1"] == got["ctx"], got


def test_o7_build_line_and_order_explicit_on():
    """Включение — только ЯВНОЙ подменой карты (как PRICECARRY-OFFPIN1810): `S.offer_of` на время `build` заменён
    обёрткой, которая записывает карту службы (обязана быть ровно {флаг: «0»}) и зовёт ту же функцию с картой «1» (со
    сверкой и бронями). Тогда строка старта «вкл» — после строки наличия по переписке, примесь надета ПОСЛЕ наличия по
    переписке — класс «offer + bookctx + адаптер»."""
    S, w, env, make = _svc_world()
    model, lines, pins = make(), [], []
    real = S.offer_of

    def offer_on(pin, model):
        pins.append(dict(pin))
        return real({S.F_OFFER: "1", S.F_TOOLS: "1", S.F_BOOK: "1"}, model)
    S.offer_of = offer_on
    try:
        S.build(env, environ={"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1", "WA_AGENT_TOOLS": "1",
                              "WA_AGENT_BOOK_CTX": "1", "WA_AGENT_OFFER": "1"}, model=model, line=lines.append)
    finally:
        S.offer_of = real
    assert pins == [{S.F_OFFER: "0"}], pins
    assert type(model).__name__ == "OfferBookCtxModelAdapter", type(model).__mro__
    got = [ln for ln in lines if "WA_AGENT_OFFER" in ln]
    assert len(got) == 1 and got[0].startswith("наличие и цена по запросу модели (WA_AGENT_OFFER): вкл — "), got
    i_ctx = next(i for i, ln in enumerate(lines) if ln.startswith("наличие по переписке"))
    assert i_ctx < lines.index(got[0]), lines


# ══ О8: чистые функции и замки ════════════════════════════════════════════════════════════════════════════════

def test_o8_day_arg_goldens():
    d = datetime.date
    assert O.day_arg("2026-11-10") == d(2026, 11, 10) and O.day_arg(" 2026-11-10 ") == d(2026, 11, 10)
    for bad in ("10.11.2026", "2026-11-31", "2026/11/10", "20261110", "", None, "2026-11-10T10:00", "завтра"):
        assert O.day_arg(bad) is None, bad


def test_o8_offer_reasons_pure():
    """Причины кода: принятый факт снимает ключ «наличие и брони» (не только слова); ворота человека — свои слова, без
    «наличие не проверено»; не факт — «наличие не проверено» один раз; порядок прежних — прежний."""
    s = Script(offer(PCX), offer(dict(PCX, model="Vespa 150")),
               offer({"model": "PCX 160", "date_from": "2027-06-01", "date_to": "2027-07-05"}), final("ok"))
    a, _d = adapter(s)
    a.draft(NUMBER, 5)
    got = offers(a)
    assert [r["outcome"] for r in got] == [T.FACT, T.UNKNOWN, T.UNKNOWN], [r["reason"] for r in got]
    base = K.handoff("а свободен? и есть ли скидка", None)
    assert [r["reason"] for r in base] == [K.R_AVAILABILITY, K.R_DISCOUNT], base
    out = O.offer_reasons(base, got, O.accepted(got), Q)
    assert [r["reason"] for r in out] == [K.R_DISCOUNT, K.R_LONG_TERM, B.R_AVAIL_UNKNOWN], out
    assert out[-1]["why"] == "offer: не факт 1", out[-1]
    assert [r["reason"] for r in O.offer_reasons(base, got[1:], [], Q)] == [K.R_AVAILABILITY, K.R_DISCOUNT,
                                                                           K.R_LONG_TERM, B.R_AVAIL_UNKNOWN]
    assert O.offer_reasons(base, [], [], Q) == base


def test_o8_offer_reasons_mismatch_pure():
    """Расхождение текста с фактом: «наличие и брони» не снята (порядок прежний), «бронь оформляет человек» не
    добавлена (её покрывает прежняя), «не совпадает» — в конце с причиной; пересказ модели остаётся."""
    got = [{"outcome": T.FACT, "offer": {"model": "PCX 160", "avail": B.BUSY, "quote": None, "gate": None}}]
    base = K.handoff("а свободен? хочу забронировать", None)
    out = O.offer_reasons(base, got, got, "хочу забронировать", ["PCX 160 — по проверке занят"])
    assert [r["reason"] for r in out] == [r["reason"] for r in base] + [O.R_AVAIL_MISMATCH], out
    assert out[-1] == {"reason": O.R_AVAIL_MISMATCH, "words": O.W_AVAIL_MISMATCH,
                       "why": "offer: PCX 160 — по проверке занят"}, out[-1]
    assert [r["reason"] for r in O.offer_reasons(base, got, got, "хочу забронировать")] == [B.R_BOOKING], base
    assert O.without_avail_words([AVAIL_WORDS, "x"], got, ["m"]) == [AVAIL_WORDS, "x"]
    assert O.without_avail_words([AVAIL_WORDS, "x"], got) == ["x"]


def _f(model, avail, ds="2026-11-10", de="2026-11-15", asked=None):
    """Принятый факт offer для голденов: модель, исход, даты (по умолчанию пара PCX), конец клиента до минимума."""
    return {"outcome": T.FACT, "offer": {"model": model, "avail": avail, "date_from": ds, "date_to": de,
                                         "asked_to": asked or de}}


PB, PF, NF, NB = _f("PCX 160", B.BUSY), _f("PCX 160", B.FREE), _f("NMAX 155", B.FREE), _f("NMAX 155", B.BUSY)
PB18, PF18 = _f("PCX 160", B.BUSY, "2026-11-18", "2026-11-22"), _f("PCX 160", B.FREE, "2026-11-18", "2026-11-22")
NF_MIN = _f("NMAX 155", B.FREE, asked="2026-11-12")     # клиент 10–12, проверен минимум класса 10–15
NB_MIN = _f("NMAX 155", B.BUSY, asked="2026-11-12")
BARE = [O.M_BARE]
P, N = "PCX 160", "NMAX 155"
# (текст, принятые факты, расхождение, не сверено) — `avail_check`; r2-голдены с датами фактов, поменялись два — помечены
MISMATCH_GOLDENS = [
    # занятое названо свободным — RU, EN, слабое слово, «не занят», сокращение без кубатуры
    ("PCX 160 на эти даты свободен.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 на 10–15 ноября свободен. Свободен NMAX 155: 400 ฿ в сутки.", [PB, NF], [O.M_BUSY % P], []),
    ("PCX 160 и NMAX 155 свободны.", [PB, NF], [O.M_BUSY % P], []),
    ("PCX 160 свободен. Да, PCX 160 свободен!", [PB], [O.M_BUSY % P], []),          # одно расхождение — один раз
    ("PCX 160 не занят.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 на эти даты не забронирован.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 is not booked.", [PB], [O.M_BUSY % P], []),
    ("Нет занятых — PCX 160 ждёт вас.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 is available for these dates.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 есть на эти даты.", [PB], [O.M_BUSY % P], []),
    ("PCX 160 в наличии.", [PB], [O.M_BUSY % P], []),
    ("pcx свободен", [PB], [O.M_BUSY % P], []),
    # r3 (было M_BOTH при фактах без дат): у каждого окна текста свой факт — «свободен с 10 по 15» и «на 18–22 нет»
    # совпали; без дат в тексте при «свободно» на одни даты и «занято» на другие — по-прежнему расхождение
    ("PCX 160 свободен с 10 по 15, на 18–22 нет.", [PF, PB18], [], []),
    ("PCX 160 свободен.", [PF, PB18], [O.M_BOTH % P], []),
    # не проверена, не из парка, не определена
    ("PCX 160 свободен, XMAX 300 тоже.", [PF], [O.M_UNCHECKED % "XMAX 300"], []),
    ("Vespa 150 свободна.", [PF], [O.M_FOREIGN % "Vespa 150"], []),
    ("CB свободен.", [PF], [O.M_ALIAS % "CB"], []),
    # «свободно» без модели при занятом
    ("Да, свободен!", [PB], BARE, []),
    ("Да, есть!", [PB], BARE, []),
    ("Да, на эти даты есть.", [PB], BARE, []),
    ("Yes, it's free.", [PB], BARE, []),
    ("PCX 160 занят, но есть другие варианты.", [PB], BARE, []),
    # r3 (было BARE): «с 10 по 15 свободен» в части без модели — о PCX 160 своего предложения, а он на 10–15 занят
    ("PCX 160 занят до 9 ноября, а с 10 по 15 свободен.", [PB], [O.M_BUSY % P], []),
    # совпало: занятое названо занятым, альтернатива проверена, «свободно» без модели при одном свободном
    ("PCX 160 на эти даты занят.", [PB], [], []),
    ("PCX 160 на 10–15 ноября занят. Свободен NMAX 155: 400 ฿ в сутки, итого 2 000 ฿.", [PB, NF], [], []),
    ("PCX 160 занят, но свободен NMAX 155.", [PB, NF], [], []),
    ("PCX 160: занят, NMAX 155: свободен.", [PB, NF], [], []),
    ("PCX 160 занят, есть другой вариант — NMAX 155.", [PB, NF], [], []),
    ("PCX 160 isn't available, but NMAX 155 is free.", [PB, NF], [], []),
    ("PCX 160 unavailable, NMAX 155 available.", [PB, NF], [], []),
    ("PCX 160 не свободен на эти даты.", [PB], [], []),
    ("Свободных PCX 160 на эти даты нет.", [PB], [], []),
    ("PCX 160 нет в наличии.", [PB], [], []),
    ("PCX 160 недоступен.", [PB], [], []),
    ("PCX 160 is not available for these dates.", [PB], [], []),
    ("PCX 160 занят, доставка есть.", [PB], [], []),
    ("Free delivery. PCX 160 is booked.", [PB], [], []),
    ("Коллега проверит наличие и вернётся.", [PB], [], []),
    ("Да, свободен!", [PF], [], []),
    ("THB 400 в сутки, PCX 160 свободен.", [PF], [], []),
    (FREE_TEXT, [PF], [], []),
    ("PCX 160 свободен.", [], [], []),                               # фактов нет — снимать нечего
    # ── r3: «свободно» без слова «свободно» (r2 пропускал): we have, можем предложить, ждёт вас, «…, but X is», «а X — да»
    ("We have NMAX 155 for these dates.", [PF], [O.M_UNCHECKED % N], []),
    ("We have NMAX 155 for these dates.", [PF, NB], [O.M_BUSY % N], []),
    ("We have NMAX 155 for these dates.", [PF, NF], [], []),
    ("Также можем предложить NMAX 155.", [PF], [O.M_UNCHECKED % N], []),
    ("Также можем предложить NMAX 155.", [PB, NB], [O.M_BUSY % N], []),
    ("Также можем предложить NMAX 155.", [PB, NF], [], []),
    ("NMAX 155 ждёт вас.", [PF], [O.M_UNCHECKED % N], []),
    ("NMAX 155 ждёт вас.", [NB], [O.M_BUSY % N], []),
    ("NMAX 155 ждёт вас.", [NF], [], []),
    ("PCX 160 isn't available, but NMAX 155 is.", [PB], [O.M_UNCHECKED % N], []),
    ("PCX 160 isn't available, but NMAX 155 is.", [PB, NB], [O.M_BUSY % N], []),
    ("PCX 160 isn't available, but NMAX 155 is.", [PB, NF], [], []),
    ("PCX 160 занят, а NMAX 155 — да.", [PB], [O.M_UNCHECKED % N], []),
    ("PCX 160 занят, а NMAX 155 — да.", [PB, NB], [O.M_BUSY % N], []),
    ("PCX 160 занят, а NMAX 155 — да.", [PB, NF], [], []),
    ("PCX 160 свободен, а NMAX 155 — нет.", [PF, NF], [O.M_FREE % N], []),
    ("PCX 160 свободен, а NMAX 155 — нет.", [PF, NB], [], []),
    ("PCX 160 is booked, but we can offer NMAX 155.", [PB], [O.M_UNCHECKED % N], []),
    ("PCX 160 is booked, but we can offer NMAX 155.", [PB, NF], [], []),
    ("PCX 160 занят, NMAX 155 — свободен.", [PB, NF], [], []),        # слово в следующей части без модели — о NMAX
    ("PCX 160 занят и NMAX 155 свободен.", [PB, NF], [], []),         # «и» делит части: у каждой модели своё слово
    ("PCX 160 is available, daily 400 THB.", [PF], [], []),           # за числом валюта — сумма, не модель
    # ── r3: обратное — проверено «свободно», а названо занятым
    ("PCX 160 на эти даты занят.", [PF], [O.M_FREE % P], []),
    ("PCX 160 на 10–15 ноября занят.", [PF], [O.M_FREE % P], []),
    ("PCX 160 занят.", [PF, PB18], [O.M_FREE_SOME % P], []),
    # ── r3: та же модель на ДРУГИЕ даты; даты без модели — у любого факта; без месяца — по числам дней
    ("PCX 160 свободен с 18 по 22 ноября.", [PF], [O.M_DATES % (P, "с 18.11 по 22.11")], []),
    ("PCX 160 is available from 18 to 22 November.", [PF], [O.M_DATES % (P, "с 18.11 по 22.11")], []),
    ("PCX 160 свободен с 18 по 22.", [PF], [O.M_DATES % (P, "с 18 по 22 (месяц не назван)")], []),
    ("PCX 160 свободен на 18–22.", [PF], [O.M_DATES % (P, "18–22 (месяц не назван)")], []),
    ("PCX 160 свободен. С 18 по 22 ноября — 2 000 ฿.", [PF], [O.M_DATES_ANY % "с 18.11 по 22.11"], []),
    ("PCX 160 свободен. С 18 по 22 ноября свободно.", [PF, _f(N, B.BUSY, "2026-11-18", "2026-11-22")],
     [O.M_DATES_DIFF % "с 18.11 по 22.11"], []),
    ("PCX 160 свободен с 10 по 15 ноября.", [PF], [], []),
    ("PCX 160 свободен на 10–15.", [PF], [], []),
    ("PCX 160 свободен на 10 - 15 ноября.", [PF], [], []),         # тире с пробелами внутри диапазона части не делит
    ("PCX 160 свободен. С 10 по 15 ноября — 2 000 ฿.", [PF], [], []),
    ("PCX 160 свободен с 18 по 22 ноября.", [PF, PF18], [], []),
    ("PCX 160 на 10–15 ноября занят, свободен с 18 по 22 ноября.", [PB, PF18], [], []),
    ("PCX 160 на 10–15 ноября занят, свободен с 18 по 22 ноября.", [PB, PB18], [O.M_BUSY % P], []),
    ("PCX 160 на 1-2 дня свободен.", [PF], [], []),                  # «на 1-2 дня» — счёт суток, а не даты
    # даты в части без модели и без слова наличия — о модели предложения: её «свободен» судится на эти даты
    ("PCX 160 свободен, аренда с 18 по 22 ноября.", [PF, PB18], [O.M_BUSY % P], []),
    ("PCX 160 свободен, аренда с 18 по 22 ноября.", [PB, PF18], [], []),
    # ── r3: срок на минимум класса — «свободно» минимума покрывает короткий срок клиента, «занято» минимума — нет
    ("NMAX 155 свободен с 10 по 12 ноября.", [NF_MIN], [], []),
    ("NMAX 155 на 10–12 ноября занят.", [NB_MIN], [O.M_DATES % (N, "с 10.11 по 12.11")], []),
    # ── r3: не сверено — о модели нет слова наличия (и нигде больше), сокращение без слова, «we have no»
    ("Цена NMAX 155 — 400 ฿ в сутки.", [PF], [], [O.U_UNCHECKED % N]),
    ("Цена NMAX 155 — 400 ฿ в сутки.", [PF, NF], [], [O.U_STANCE % N]),
    ("PCX 160 свободен. PCX 160 стоит 400 ฿ в сутки.", [PF], [], []),
    ("Про CB уточню.", [PF], [], [O.U_ALIAS % "CB"]),
    ("We have no PCX 160 for these dates.", [PB], [], [O.U_STANCE % P]),
    ("PCX 160 is available, the price is 400 THB per day.", [PF], [], []),     # «is 400 THB» — сумма, не модель
]


def test_o8_avail_check_goldens():
    """`avail_check` (r3): каждая модель парка в тексте и каждый диапазон дат — с принятым фактом и тем же исходом;
    расхождение и «не сверено» — раздельно."""
    bad = [(t, want, got) for t, facts, *want in MISMATCH_GOLDENS
           for got in [list(O.avail_check(t, facts, BIKES, TODAY))] if got != want]
    assert not bad, bad
    assert O.avail_check("PCX 160 свободен.", [PF], None, TODAY) == ([O.M_FOREIGN % P], []), "парка нет — не сверено"
    # «сегодня» не передано — по часам Пхукета, а не «дат нет»: другие даты по-прежнему расхождение
    assert O.avail_check("PCX 160 свободен с 18 по 22 ноября.", [PF], BIKES)[0] == [O.M_DATES % (P, "с 18.11 по 22.11")]


BOOK_SAID = [("Забронировал PCX 160 для вас.", True), ("PCX 160 забронирован на эти даты.", True),
             ("Оформим бронь на PCX 160.", True), ("Ваша бронь подтверждена.", True), ("Бронирую PCX 160.", True),
             ("PCX 160 reserved for you.", True), ("I've booked PCX 160 for you.", True),
             ("We can book it for you.", True), ("Your booking is confirmed.", True), ("PCX 160 is reserved.", True),
             ("I'll reserve it.", True),
             ("PCX 160 свободен.", False), ("PCX 160 is booked.", False), ("Free delivery.", False),
             ("Коллега проверит наличие и вернётся.", False), (FREE_TEXT, False), ("", False), (None, False)]


def test_r3_book_said_goldens():
    """Слова брони в тексте черновика (r3): заброн*/бронир*/оформ*/бронь, reserved, booked for you, I/we book."""
    bad = [(t, want) for t, want in BOOK_SAID if O.book_said(t) is not want]
    assert not bad, bad


def test_r3_offer_reasons_unsure_and_promise_pure():
    """`offer_reasons`: «не сверено» — «агент их не видит» не снята, новых слов нет; слова брони в тексте — не снята и
    «бронь оформляет человек» (один раз, и при просьбе клиента о брони); ответов offer нет — причины прежние."""
    got = [{"outcome": T.FACT, "offer": {"model": "PCX 160", "avail": B.FREE, "quote": None, "gate": None}}]
    base = K.handoff(Q, None)
    out = O.offer_reasons(base, got, got, Q, [], ["NMAX 155 — не разобрано, свободен или занят"])
    assert out == base, out
    out = O.offer_reasons(base, got, got, Q, promise=True)
    assert [r["reason"] for r in out] == [r["reason"] for r in base] + [B.R_BOOKING], out
    assert out[-1] == {"reason": B.R_BOOKING, "words": B.W_BOOKING, "why": "offer: слова брони в тексте черновика"}
    ask = "а свободен? хочу забронировать"
    out = O.offer_reasons(K.handoff(ask, None), got, got, ask, promise=True)
    assert [r["reason"] for r in out].count(B.R_BOOKING) == 1 and K.R_AVAILABILITY in [r["reason"] for r in out], out
    assert O.offer_reasons(base, [], [], Q, promise=True) == base
    assert O.without_avail_words([AVAIL_WORDS], got, True) == [AVAIL_WORDS]


def test_o8_judged_price_same_object_without_facts():
    p = {"line": "x", "outcome": "number"}
    assert O.judged_price(p, []) is p and O.judged_price(None, []) is None
    info = {"price": p, "terms": []}
    assert O.judged_info(info, p, []) is info
    assert O.offer_reasons([{"reason": "a", "words": "b"}], [], [], Q) == [{"reason": "a", "words": "b"}]
    assert O.without_avail_words([AVAIL_WORDS], []) == [AVAIL_WORDS]


def _tree():
    return ast.parse(open(os.path.join(ROOT, "wa_offer_tool.py"), encoding="utf-8").read())


def _module_level_imports(tree):
    out, todo = set(), list(tree.body)
    while todo:
        node = todo.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add((node.module or "").split(".")[0])
        todo.extend(ast.iter_child_nodes(node))
    return out


def test_o8_module_locks():
    """Импорты — ровно разрешённые; ни файлов, ни сети, ни базы, ни записи броней; в примеси — только `_draft_tools`;
    модуль не импортируется на уровне модуля нигде в корне (только лениво в `wa_agent_svc.offer_of`)."""
    tree = _tree()
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            imps.add((n.module or "").split(".")[0])
    assert imps == {"datetime", "hashlib", "inspect", "json", "re", "time", "wa_agent_knowledge", "wa_agent_model",
                    "wa_agent_tools", "wa_book_read"}, imps
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
        {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    bad = {"open", "sqlite3", "subprocess", "socket", "os", "sys", "bridge_client", "create_booking", "_post", "write"}
    assert not names & bad, names & bad
    own = {k for k in vars(O.OfferMixin) if not (k.startswith("__") and k.endswith("__"))}
    assert own == {"_draft_tools"}, own
    for name in sorted(os.listdir(ROOT)):
        if name.endswith(".py") and name != "wa_offer_tool.py":
            try:
                t = ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            assert NEW_MODULE not in _module_level_imports(t), name


def test_o8_copies_reconciled_with_parents():
    """Копии `run` и `_draft_tools` сверены с родителями этого дерева (sha256 исходника); класс с примесью — один на cls."""
    assert O.drift() == [], O.drift()
    a = O.with_offer(M.ModelAdapter)
    assert a is O.with_offer(M.ModelAdapter) and O.with_offer(a) is a and a.__mro__[1] is O.OfferMixin
    assert a.__name__ == "OfferModelAdapter" and a.__module__ == "wa_offer_tool"
    assert O.OFFER_MAX == 3 and O.OFFER_TOOL not in T.TOOLS


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
