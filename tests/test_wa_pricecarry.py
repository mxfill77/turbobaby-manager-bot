#!/usr/bin/env python3
"""PRICECARRY1610 (отрезок P1 «цена»): цена через ход — приёмка примеси `wa_price_carry` и флага WA_AGENT_PRICE_CARRY.

Клиент: «Сколько стоит PCX 160?» → мы: «на какие даты?» → «с 10 по 15 октября» — прежде цены не было (в хвосте нет слова
цены, `ModelAdapter._price` дверь не звал), теперь — цена на ЭТИ даты той же модели, теми же воротами двери. Каждый случай —
с близнецом без примеси. Стенд: мир `test_wa_agent_model.World` (временные очередь и база в TMP) и мост
`test_wa_book_read.Bridge` с дверью цены, считающей срок по датам. T0 = 21.09.2026 по Пхукету, номер TM.NUM — всё
выдуманное. Сети нет, модели нет, боевых баз нет. Набор и как unittest (`python -m unittest`), и как файл гейта."""
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

PROBE_ARG = "--probe-price-carry-off"
PROBE_MARK = "PRICECARRY_PROBE "
NEW_MODULE = "wa_price_carry"


def _probe():
    """Отдельный процесс: служба с флагом не запрошенным, «0», «» и при включённом наличии по переписке — модуля выпуска
    в процессе нет, класс адаптера прежний, строки старта о цене через ход нет. PRICECARRY-OFFPIN1810: то же при «1» и
    «true» — выкл держит код `build()`, а не окружение."""
    import wa_agent_svc as S
    import test_wa_agent_model as TM
    import test_wa_book_read as TB
    w, br = TM.World(), TB.Bridge([])
    env = {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}
    runs = []
    for i, extra in enumerate(({}, {"WA_AGENT_PRICE_CARRY": "0"}, {"WA_AGENT_PRICE_CARRY": ""},
                               {"WA_AGENT_BOOK_CTX": "1"}, {"WA_AGENT_PRICE_CARRY": "off", "WA_AGENT_BOOK_CTX": "1"},
                               {"WA_AGENT_PRICE_CARRY": "1"}, {"WA_AGENT_PRICE_CARRY": "true", "WA_AGENT_BOOK_CTX": "1"})):
        model, _ = S.make_model(env, bridge=br, call=lambda s, u: ("", {}), book=True)
        lines = []
        S.build(dict(env, agent_db=w.dbpath + str(i)), environ=dict({"WA_AGENT_DRAFTS": "1", "WA_AGENT_BOOK_READ": "1"},
                                                                    **extra), model=model, line=lines.append)
        runs.append({"carry": [ln for ln in lines if "PRICE_CARRY" in ln or ln.startswith("цена через ход")],
                     "type": type(model).__name__, "lines": lines})
    print(PROBE_MARK + json.dumps({"runs": runs, "mods": sorted(m for m in sys.modules if m == NEW_MODULE)},
                                  ensure_ascii=False))


if __name__ == "__main__" and PROBE_ARG in sys.argv:
    _probe()
    sys.exit(0)

import ast  # noqa: E402
import datetime  # noqa: E402
import hashlib  # noqa: E402
import inspect  # noqa: E402
import unittest  # noqa: E402

import test_wa_agent_model as TM  # noqa: E402
import test_wa_book_read as TB  # noqa: E402
import wa_agent_knowledge as K  # noqa: E402
import wa_agent_model as M  # noqa: E402
import wa_agent_svc as S  # noqa: E402
import wa_book_read as B  # noqa: E402
import wa_book_ctx as BC  # noqa: E402
import wa_price_carry as PC  # noqa: E402

T0, NUM = TM.T0, TM.NUM                        # 21.09.2026 по Пхукету; выдуманный номер
TODAY = datetime.date(2026, 9, 21)
C1 = "Сколько стоит PCX 160?"                   # вопрос о цене без дат
U1 = "Подскажите, на какие даты планируете аренду?"   # наш встречный вопрос о датах
A1 = "с 10 по 15 октября"                       # ответ датами, слова цены нет
LINE = ("2026-10-10, 2026-10-15 — PCX 160: 5 сут., 400 ฿ в сутки, итого 2 000 ฿ за срок; скидка за срок 0%; "
        "депозит 3 000 ฿.")
DOOR = [("PCX 160 1234", "2026-10-10", "2026-10-15")]
BIKES = [{"name": n} for n in ("PCX 160 1234", "PCX 160 5678", "NMAX 155 6001", "XMAX 300 4321", "CB 300CC R 9011",
                               "CB 650R RED PHUKET 9012")]
L_DONE = PC.LOG_HEAD + "вопрос о цене обменом раньше, наш вопрос о датах, ответ датами — расчёт: %s, дверь %d"
W_ON = ("вкл — клиент спросил цену, мы спросили даты, он ответил датами: цена считается с датами его ответа и той же "
        "моделью, ворота двери цены прежние, дверь — не больше раза; даты противоречат, срок неполный, модель "
        "сменилась — расчёт не вызван, число не называется; клиенту — только по «Отправить»")
W_NO_MODEL = "не засчитан — флаг 1, но у модели нет двери цены (WA_AGENT_DRAFTS выкл или адаптер не собран)"
W_NO_MOD = "не засчитан — модуль цены через ход не собран (ImportError) — адаптер прежний"
# блобы закреплённых файлов на 13b4188 (git rev-parse 13b4188:<файл>): родитель примеси тот же, что в базе
PINS = {"wa_agent.py": "70695c7dc669f2b4d14ff7c000763b915e6121e8",
        "wa_agent_model.py": "29fcf2350bbcc7a574bc6a44be67b8a71e1ddc2b",  # RCFIX2010: было 868b0c4b (free_bikes с парком снимка) · PROMPT2110: было 7c58cca9 · WAFIX2210: было b95d3a86
        "wa_agent_knowledge.py": "34fcc7858c39f9f1c705d79f617916cbf636dda6",  # PROMPT2110: было d338a3c2
        "wa_agent_tools.py": "fb70716d09b8b2812c08d40f2b0d66ff18ead9e3",
        "wa_book_read.py": "ba866980d22c75c005e40510b1271453aac74a25",  # RCFIX2010: было 7329698d (ремонт по парку не «свободно») · PROMPT2110: было 5a90fddc
        "wa_book_ctx.py": "4db150f276359b1cb07d5816041fc25db03912e0",  # RCFIX2010: было 3a507747 (free_bikes с парком снимка)
        "wa_agent_cstate.py": "86d46669854237a1d258e970227eccd8d7e775d7",
        "wa_history.py": "0ed8f882d026045089fb4a8227a46c839fe29460"}


# ══ стенд ══════════════════════════════════════════════════════════════════════════════════════════════════════

class Bridge(TB.Bridge):
    """Мост стенда: парк BIKES (или отказ), дверь цены живого формата со сроком по датам запроса (или отказ)."""

    def __init__(self, rows=(), door_mode=None, fleet_mode=None):
        super().__init__(rows)
        self.door_mode, self.fleet_mode = door_mode, fleet_mode

    def fleet(self):
        self.fleets += 1
        if self.fleet_mode == "raise":
            raise TimeoutError("парк")
        if self.fleet_mode == "fail":
            return {"ok": False, "error": "timeout"}
        return {"ok": True, "bikes": list(BIKES)}

    def door(self, unit, ds, de):
        self.doors.append((unit, ds, de))
        if self.door_mode == "raise":
            raise TimeoutError("дверь")
        if self.door_mode == "refuse":
            return {"ok": False, "error": "quote_failed"}
        if self.door_mode == "none":
            return None
        days = (datetime.date.fromisoformat(de) - datetime.date.fromisoformat(ds)).days
        model = B.model_key(unit)
        return {"ok": True, "days": days, "day_price": 400, "total": 400 * days, "deposit": 3000,
                "season": {"label": "P2"}, "model": model, "available": True, "conflicts": 0,
                "text": "%s | дней: %d, стоимость: %d (скидка за срок 0%%, 400 в день), депозит: 3000 бат"
                        % (model, days, 400 * days)}


def world(mixin=True, book_ctx=False, csa=False, **kw):
    """Мир адаптера на мосту стенда; mixin — примесь цены через ход надета; book_ctx — и примесь наличия; csa — адаптер
    состояния договора (как CASESTATE в проде)."""
    w = TM.World()
    br = Bridge(**kw)
    w.bridge = br
    if csa:
        import wa_agent_cstate as C
        w.adapter = C.ContractStateAdapter(w.qpath, w.call, read_doc=br.read_doc, fleet=br.fleet, door=br.door,
                                           archive_db=w.apath, clock=lambda: T0, log=w.lines.append,
                                           agent_db=w.dbpath)
    w.adapter.knowledge = K.Knowledge(br.read_doc)
    w.adapter.fleet, w.adapter.door = br.fleet, br.door
    w.adapter.book = B.Snapshot(lambda: br.clients(filter="all"), br.fleet)
    if book_ctx:
        w.adapter.__class__ = BC.with_book_ctx(type(w.adapter))
    if mixin:
        w.adapter.__class__ = PC.with_price_carry(type(w.adapter))
    return w, br


def scene(w, msgs):
    """[(кто, текст)] по порядку, «мы» — эхо нашей стороны; раз в 10 минут, последняя — в T0 → номер последней строки."""
    rid, n = None, len(msgs)
    for i, (who, text) in enumerate(msgs):
        rid = w.put(T0 - (n - 1 - i) * 600, text, kind="echo" if who == "мы" else "in")
    return rid


def three(c1=C1, u1=U1, a1=A1):
    return [("клиент", c1), ("мы", u1), ("клиент", a1)]


def built(w, rid):
    n = len(w.lines)
    system, user, info = w.adapter.build(NUM, rid, now=T0)
    return system, user, info, w.lines[n:]


def pair(msgs, **kw):
    """Сцена с примесью и близнец без неё → ((s, u, i, журнал), мост, (s0, u0, i0, журнал0), мост0)."""
    w, br = world(**kw)
    w0, br0 = world(mixin=False, **kw)
    return built(w, scene(w, msgs)), br, built(w0, scene(w0, msgs)), br0


def carry_lines(lines):
    return [ln for ln in lines if ln.startswith(PC.LOG_HEAD)]


def price_block(user):
    return [b for b in user.split("\n\n") if b.startswith("ЦЕНА: ")]


def no_pii(test, lines):
    for bad in (NUM, "PCX", "NMAX", "2026-10", "10.10", "15.10", "октябр"):
        test.assertFalse([ln for ln in lines if bad in ln], (bad, [ln for ln in lines if bad in ln]))


# ══ позитив ════════════════════════════════════════════════════════════════════════════════════════════════════

class Positive(unittest.TestCase):

    def test_p1_price_for_answered_dates(self):
        """П1: вопрос о цене → наш вопрос о датах → ответ датами → «ЦЕНА» на эти даты той же модели, дверь один раз;
        близнец без примеси — цены нет, дверь не звана (это и есть разрыв)."""
        (s, user, info, lines), br, (s0, u0, i0, l0), br0 = pair(three())
        self.assertEqual(price_block(user), ["ЦЕНА: " + LINE], user[-1500:])
        self.assertEqual(info["price"]["outcome"], K.PRICE_NUMBER)
        self.assertEqual((info["price"]["date_start"], info["price"]["date_end"], info["price"]["days"]),
                         ("2026-10-10", "2026-10-15", 5))
        self.assertEqual(br.doors, DOOR)
        self.assertEqual(br.fleets, 1)
        self.assertEqual(info["price_words"], PC.LOG_HEAD + "цена: number")
        self.assertEqual(carry_lines(lines), [L_DONE % ("number", 1)])
        no_pii(self, lines)
        # близнец: разрыв M:1527 — расчёт не вызван
        self.assertEqual(price_block(u0), [])
        self.assertIsNone(i0["price"])
        self.assertEqual(i0["price_words"], PC.NO_ASK)
        self.assertEqual(br0.doors, [])
        self.assertEqual(s, s0, "инструкция прежняя")

    def test_p2_english(self):
        """П2: то же по-английски: «How much is PCX 160?» → «What dates?» → «10 to 15 October»."""
        (_s, user, info, _l), br, (_s0, u0, _i0, _l0), _b0 = pair(
            three("How much is PCX 160?", "What dates are you planning?", "10 to 15 October"))
        self.assertEqual(price_block(user), ["ЦЕНА: " + LINE], user[-900:])
        self.assertEqual(br.doors, DOOR)
        self.assertEqual(price_block(u0), [])

    def test_p3_model_named_in_answer(self):
        """П3: в вопросе модели нет («сколько в сутки?»), мы спросили модель и даты, ответ «PCX 160 с 10 по 15 октября»."""
        (_s, user, _i, _l), br, _b, _b0 = pair(three("Сколько в сутки?", "Какую модель и на какие даты?",
                                                     "PCX 160 с 10 по 15 октября"))
        self.assertEqual(price_block(user), ["ЦЕНА: " + LINE])
        self.assertEqual(br.doors, DOOR)

    def test_p4_model_from_earlier_client_message(self):
        """П4: модель названа раньше вопроса о цене — тот же байк из переписки клиента."""
        msgs = [("клиент", "Хочу PCX 160"), ("мы", "Отличный выбор!"), ("клиент", "Сколько стоит?"),
                ("мы", "На какие даты?"), ("клиент", A1)]
        (_s, user, _i, _l), br, _b, _b0 = pair(msgs)
        self.assertEqual(price_block(user), ["ЦЕНА: " + LINE])
        self.assertEqual(br.doors, DOOR)

    def test_p5_same_gates_as_parent_minimum(self):
        """П5: ворота родителя: NMAX 155 на 3 сут. (минимум скутера 5) — та же дверь и тот же исход, что у родителя на
        вопрос «Сколько стоит NMAX 155 с 10 по 13 октября?» одним сообщением."""
        w, br = world()
        _s, user, info, _l = built(w, scene(w, three("Сколько стоит NMAX 155?", U1, "с 10 по 13 октября")))
        w0, br0 = world(mixin=False)
        _s, u0, i0, _l = built(w0, scene(w0, [("клиент", "Сколько стоит NMAX 155 с 10 по 13 октября?")]))
        self.assertEqual(br.doors, br0.doors)
        self.assertEqual(br.doors, [("NMAX 155 6001", "2026-10-10", "2026-10-15")])
        self.assertEqual(info["price"], i0["price"])
        self.assertEqual(price_block(user), price_block(u0))
        self.assertIn("минимум 5 сут.", info["price"]["line"])

    def test_p6_discount_and_money_support(self):
        """П6: перенесённая цена — опора проверки денег: сумма из «ЦЕНА» в черновике причины «денежное утверждение без
        опоры» не даёт (у близнеца без примеси — даёт)."""
        reply = json.dumps({"text": "PCX 160 с 10 по 15 октября — 2 000 ฿ за 5 суток, скидка за срок 0%.", "lang": "ru",
                            "handoff": [], "why": "цена из блока"}, ensure_ascii=False)
        got = {}
        for mixin in (True, False):
            w, _br = world(mixin=mixin)
            w.call.reply = reply
            res = w.adapter.draft(NUM, scene(w, three()))
            got[mixin] = res["handoff"]
        self.assertNotIn(K.MONEY_CLAIM_WORDS, got[True])
        self.assertIn(K.MONEY_CLAIM_WORDS, got[False])


# ══ матрица адаптеров (критик п.5): {ModelAdapter, ContractStateAdapter} × {draft, сверка Т4а} × BOOKCTX ═══════════

TOOLS = {"cash": lambda **k: {"ok": False}, "contract": lambda **k: {"ok": False},
         "contract_pdf": lambda *a, **k: {"ok": False}}


class Matrix(unittest.TestCase):

    def test_matrix_all_eight(self):
        for csa in (False, True):
            for book_ctx in (False, True):
                for tools in (False, True):
                    for mixin in (True, False):
                        w, br = world(mixin=mixin, book_ctx=book_ctx, csa=csa)
                        if tools:
                            w.adapter.tools = dict(TOOLS)
                        w.adapter.draft(NUM, scene(w, three()))
                        key = (csa, book_ctx, tools, mixin)
                        self.assertTrue(w.call.calls, key)
                        user = w.call.calls[0][1]
                        self.assertEqual(("ЦЕНА: " + LINE) in user, mixin, (key, user[-600:]))
                        self.assertEqual(br.doors, DOOR if mixin else [], key)
                        mro = type(w.adapter).__mro__
                        if mixin:
                            self.assertIs(mro[1], PC.PriceCarryMixin, key)
                        self.assertEqual(any(c is BC.BookCtxMixin for c in mro), book_ctx, key)
                        if csa:
                            import wa_agent_cstate as C
                            self.assertIsInstance(w.adapter, C.ContractStateAdapter)


# ══ контрпримеры ══════════════════════════════════════════════════════════════════════════════════════════════

class SourceUnavailable(unittest.TestCase):
    """Источник недоступен — числа нет: исход тех же ворот «Цена НЕИЗВЕСТНА» (а не «расчёт не вызван»)."""

    def _unknown(self, **kw):
        (_s, user, info, lines), br, _b, _b0 = pair(three(), **kw)
        self.assertEqual(info["price"]["outcome"], K.PRICE_UNKNOWN, info["price"])
        block = price_block(user)
        self.assertEqual(len(block), 1)
        self.assertIn("Цена НЕИЗВЕСТНА", block[0])
        for num in ("400", "2 000", "3 000", "2000"):
            self.assertNotIn(num, block[0])
        self.assertEqual(carry_lines(lines)[-1], L_DONE % ("unknown", len(br.doors)))
        no_pii(self, lines)
        return info, br, lines

    def test_door_raises(self):
        info, br, _l = self._unknown(door_mode="raise")
        self.assertEqual(br.doors, DOOR)
        self.assertIn("дверь цены упала", info["price"]["why"])

    def test_door_refuses(self):
        info, br, _l = self._unknown(door_mode="refuse")
        self.assertEqual(br.doors, DOOR)
        self.assertIn("отказом", info["price"]["why"])

    def test_door_silent(self):
        info, br, _l = self._unknown(door_mode="none")
        self.assertIn("не ответила", info["price"]["why"])

    def test_fleet_unreadable(self):
        info, br, lines = self._unknown(fleet_mode="raise")
        self.assertEqual(br.doors, [], "парк не прочитан — дверь не звана")
        self.assertIn("парк не прочитан", info["price"]["why"])
        self.assertIn(PC.LOG_HEAD + "парк не прочитан: TimeoutError", lines)

    def test_fleet_refuses(self):
        info, br, _l = self._unknown(fleet_mode="fail")
        self.assertEqual(br.doors, [])


class NotCalled(unittest.TestCase):
    """Расчёт не вызывается: запрос модели побайтно равен близнецу без примеси, двери и парк не званы, число не
    выдумано; в журнале — причина (это исход «расчёт не вызван», а не «цена неизвестна»)."""

    def _stop(self, msgs, why, **kw):
        (s, user, info, lines), br, (s0, u0, i0, l0), br0 = pair(msgs, **kw)
        self.assertEqual((s, user), (s0, u0))
        self.assertEqual(price_block(user), [])
        self.assertIsNone(info["price"])
        self.assertEqual(br.doors, [])
        self.assertEqual(info["price_words"], PC.LOG_HEAD + PC.L_STOP % why)
        self.assertEqual(carry_lines(lines), [PC.LOG_HEAD + PC.L_STOP % why])
        self.assertEqual({k: v for k, v in info.items() if k != "price_words"},
                         {k: v for k, v in i0.items() if k != "price_words"})
        no_pii(self, lines)
        return br

    # ── даты противоречат ──
    def test_dates_two_ranges(self):
        br = self._stop(three(a1="с 10 по 15 октября или с 12 по 17 октября"), PC.W_MANY)
        self.assertEqual(br.fleets, 0, "даты судятся до моста")

    def test_dates_range_vs_count(self):
        self._stop(three(a1="с 10 по 15 октября, 7 дней"), PC.W_MANY)

    def test_dates_question_named_other_dates(self):
        self._stop(three("Сколько стоит PCX 160 с 1 по 5 ноября?", "Уточните, пожалуйста, даты?", A1), PC.W_PREV)

    def test_dates_question_named_other_days(self):
        self._stop(three("Сколько стоит PCX 160 на 3 дня?", "С какого числа?", A1), PC.W_PREV)

    def test_dates_descending(self):
        self._stop(three(a1="15.10 и 10.10"), PC.W_MANY)

    # ── срок неполный / прошёл ──
    def test_term_without_month(self):
        self._stop(three(a1="с 10 по 15"), PC.W_LOOSE)

    def test_term_only_days(self):
        self._stop(three(a1="на 5 дней"), PC.W_LOOSE)

    def test_term_started(self):
        self._stop(three(a1="с 20 по 25 сентября"), PC.W_PAST)

    # ── смена модели ──
    def test_model_changed(self):
        self._stop(three(a1="лучше NMAX 155 с 10 по 15 октября"), PC.W_CHANGED)

    def test_model_two_in_answer(self):
        self._stop(three(a1="PCX 160 или NMAX 155, с 10 по 15 октября"), PC.W_CHANGED)

    def test_model_not_in_fleet(self):
        self._stop(three(a1="Vespa 150 с 10 по 15 октября"), PC.W_MODEL_TAIL)

    def test_model_alias_ambiguous(self):
        self._stop(three("Сколько стоит CB 650R?", U1, "CB с 10 по 15 октября"), PC.W_ALIAS)

    def test_model_unknown(self):
        self._stop(three("Сколько стоит?", U1, A1), PC.W_NO_MODEL)

    # ── смена периода: прежний срок не тащится ──
    def test_period_changed_in_answer(self):
        msgs = three() + [("клиент", "ой, лучше с 20 по 25 октября")]
        br = self._stop(msgs, PC.W_MANY)
        self.assertFalse([d for d in br.doors if "2026-10-10" in d])


class Untouched(unittest.TestCase):
    """Перенос не нужен — выход и журнал побайтно равны близнецу без примеси, двери и парк — как у близнеца."""

    def _same(self, msgs, **kw):
        (s, user, info, lines), br, (s0, u0, i0, l0), br0 = pair(msgs, **kw)
        self.assertEqual((s, user, info), (s0, u0, i0))
        self.assertEqual(lines, l0)
        self.assertEqual((br.doors, br.fleets, br.client_calls), (br0.doors, br0.fleets, br0.client_calls))
        self.assertFalse(carry_lines(lines))
        return info, br

    def test_no_price_question(self):
        """О цене не спрашивал: «Хочу PCX 160» → «на какие даты?» → даты — цены нет, как было."""
        info, br = self._same(three("Хочу PCX 160", U1, A1))
        self.assertIsNone(info["price"])
        self.assertEqual(br.doors, [])

    def test_our_answer_not_about_dates(self):
        self._same(three(C1, "Добрый день! Коллега подскажет.", A1))

    def test_our_answer_already_named_amount(self):
        """Наш вопрос о датах уже нёс сумму («400 бат в сутки. На какие даты?») — наши слова обязывают (правило 12),
        переноса нет."""
        self._same(three(C1, "PCX 160 — 400 бат в сутки. На какие даты?", A1))

    def test_thanks_after_our_question(self):
        """К1: «спасибо» после нашего вопроса о датах — срока нет, цены нет."""
        self._same(three(a1="спасибо"))

    def test_normal_path_price_word_in_tail(self):
        """Обычный путь: слово цены в хвосте — ответ родителя как есть (одна дверь у обоих)."""
        info, br = self._same(three(a1="с 10 по 15 октября, сколько будет?"))
        self.assertEqual(br.doors, DOOR)
        self.assertEqual(info["price"]["outcome"], K.PRICE_NUMBER)

    def test_period_changed_after_priced_answer(self):
        """Смена периода после нашего ответа С ЧИСЛОМ: «а с 20 по 25 октября?» — переноса нет, старая цена не
        тащится, дверь не звана."""
        msgs = three() + [("мы", "PCX 160 с 10 по 15 октября — 2 000 бат за 5 суток, скидка за срок 0%."),
                          ("клиент", "а с 20 по 25 октября?")]
        info, br = self._same(msgs)
        self.assertIsNone(info["price"])
        self.assertEqual(br.doors, [])


class Repeat(unittest.TestCase):
    """Повтор того же сообщения — без второго расчёта."""

    def test_same_message_twice_one_door(self):
        msgs = three() + [("клиент", A1)]
        (_s, user, info, lines), br, _b, _b0 = pair(msgs)
        self.assertEqual(br.doors, DOOR, "один срок — одна дверь")
        self.assertEqual(price_block(user), ["ЦЕНА: " + LINE])
        self.assertEqual(carry_lines(lines), [L_DONE % ("number", 1)])

    def test_repeat_after_priced_answer_no_second_calc(self):
        msgs = three() + [("мы", "PCX 160 с 10 по 15 октября — 2 000 бат, скидка за срок 0%."), ("клиент", A1)]
        (_s, user, info, lines), br, (_s0, u0, i0, l0), _b0 = pair(msgs)
        self.assertEqual(br.doors, [])
        self.assertEqual((user, info, lines), (u0, i0, l0))


class Robust(unittest.TestCase):

    def test_exception_parent_answer(self):
        """Сбой внутри примеси — ответ родителя и строка журнала с именем ошибки."""
        w, br = world()
        orig = PC.tail_term
        PC.tail_term = lambda *a, **k: (_ for _ in ()).throw(ValueError("x"))
        try:
            _s, user, info, lines = built(w, scene(w, three()))
        finally:
            PC.tail_term = orig
        self.assertIsNone(info["price"])
        self.assertEqual(info["price_words"], PC.NO_ASK)
        self.assertIn(PC.LOG_HEAD + PC.L_FAIL % "ValueError", lines)

    def test_history_of_other_call(self):
        """История не того вызова (вызов `_price` мимо `build`) — ответ родителя."""
        w, br = world()
        scene(w, three())
        got = w.adapter._price(A1, TODAY, [], None)
        self.assertEqual(got, (None, PC.NO_ASK))
        self.assertEqual(br.doors, [])

    def test_no_ask_words_equal_parent(self):
        w, _br = world(mixin=False)
        self.assertEqual(w.adapter._price("с 10 по 15 октября", TODAY), (None, PC.NO_ASK))


# ══ служба: флаг ═══════════════════════════════════════════════════════════════════════════════════════════════

def _env():
    w = TM.World()
    return w, {"queue_db": w.qpath, "agent_db": w.dbpath, "mirror_db": "", "tg_token": "", "show_chat": ""}


def _model(env, **kw):
    model, why = S.make_model(env, bridge=TB.Bridge([]), call=lambda s, u: ("", {}), **kw)
    assert model is not None, why
    return model


class Service(unittest.TestCase):

    def test_flag_off_subprocess(self):
        """Флаг не запрошен / «0» / «» / «off» (и при включённом наличии по переписке) — в процессе нет модуля выпуска,
        класс адаптера прежний, строк старта о цене через ход нет, строки старта одинаковы. PRICECARRY-OFFPIN1810: то же
        при «1» и «true» (выкл держит код `build()`)."""
        p = subprocess.run([sys.executable, os.path.abspath(__file__), PROBE_ARG], cwd=ROOT, capture_output=True,
                           timeout=300, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        text = p.stdout.decode("utf-8", "replace")
        got = [ln for ln in text.splitlines() if ln.startswith(PROBE_MARK)]
        self.assertTrue(p.returncode == 0 and got, (p.returncode, text[-800:], p.stderr.decode("utf-8", "replace")))
        r = json.loads(got[-1][len(PROBE_MARK):])
        self.assertEqual(r["mods"], [])
        runs = r["runs"]
        self.assertEqual([x["type"] for x in runs], ["ModelAdapter"] * 3 + ["BookCtxModelAdapter"] * 2 +
                         ["ModelAdapter", "BookCtxModelAdapter"])
        self.assertEqual([x["carry"] for x in runs], [[]] * 7)
        self.assertEqual(runs[0]["lines"], runs[1]["lines"])
        self.assertEqual(runs[0]["lines"], runs[2]["lines"])
        self.assertEqual(runs[3]["lines"], runs[4]["lines"])
        self.assertEqual(runs[0]["lines"], runs[5]["lines"])
        self.assertEqual(runs[3]["lines"], runs[6]["lines"])

    def test_flag_on_env_pinned_off(self):
        """PRICECARRY-OFFPIN1810: окружение просит ВКЛ («1», «true»; с наличием по переписке и без) — `build()` даёт
        `price_carry_of` свою карту «0»: `import wa_price_carry` не исполнялся ни разу (подмена `__import__`), примеси
        нет, строки старта о цене через ход нет, строки старта те же, что без флага."""
        import builtins
        w, env = _env()
        real_import, asked = builtins.__import__, []

        def spy(name, *a, **k):
            if name.split(".")[0] == NEW_MODULE:
                asked.append(name)
            return real_import(name, *a, **k)
        got = {}
        for key, extra in (("off", {}), ("1", {S.F_PRICE_CARRY: "1"}), ("true", {S.F_PRICE_CARRY: "true"}),
                           ("ctx", {S.F_BOOK_CTX: "1"}), ("ctx1", {S.F_BOOK_CTX: "1", S.F_PRICE_CARRY: "1"})):
            m, lines = _model(env, book=True), []
            builtins.__import__ = spy
            try:
                S.build(dict(env, agent_db=w.dbpath + key), environ=dict({"WA_AGENT_DRAFTS": "1", S.F_BOOK: "1"},
                                                                        **extra), model=m, line=lines.append)
            finally:
                builtins.__import__ = real_import
            self.assertFalse(any(c is PC.PriceCarryMixin for c in type(m).__mro__), key)
            self.assertEqual([ln for ln in lines if S.F_PRICE_CARRY in ln or ln.startswith("цена через ход")], [], key)
            got[key] = lines
        self.assertEqual(asked, [])
        self.assertEqual(got["1"], got["off"])
        self.assertEqual(got["true"], got["off"])
        self.assertEqual(got["ctx1"], got["ctx"])

    def test_flag_off_in_process(self):
        w, env = _env()
        model = _model(env, book=True)
        self.assertEqual(S.price_carry_of({}, model), (None, None))
        self.assertIs(type(model), M.ModelAdapter)
        self.assertEqual(S.F_PRICE_CARRY, "WA_AGENT_PRICE_CARRY")
        self.assertNotIn(S.F_PRICE_CARRY, S.FLAGS)

    def test_flag_on_mixin_and_line_position(self):
        """Флаг 1 → (True, «вкл — …»), класс «примесь + прежний» (и поверх примеси наличия); второй вызов класс не
        меняет; строка старта — сразу после строки наличия по переписке, а без неё — сразу после строки броней.
        PRICECARRY-OFFPIN1810: `build()` даёт функции свою карту «0», поэтому ВКЛ по пути службы — только ЯВНОЙ подменой
        карты в тесте: `S.price_carry_of` на время `build` заменён обёрткой, которая записывает карту службы (обязана быть
        ровно {флаг: «0»}) и зовёт ту же функцию с картой «1»."""
        import wa_agent_cstate as C
        w, env = _env()
        model = _model(env, book=True)
        self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: "1"}, model), (True, W_ON))
        cls = type(model)
        self.assertIs(cls.__mro__[1], PC.PriceCarryMixin)
        self.assertIs(cls.__mro__[2], M.ModelAdapter)
        self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: "1"}, model), (True, W_ON))
        self.assertIs(type(model), cls)
        csa = _model(env, book=True, cstate=True)
        self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: "1"}, csa), (True, W_ON))
        self.assertIsInstance(csa, C.ContractStateAdapter)
        for extra, after in (({}, "брони (WA_AGENT_BOOK_READ): "),
                             ({S.F_BOOK_CTX: "1"}, "наличие по переписке (WA_AGENT_BOOK_CTX): ")):
            m2 = _model(env, book=True)
            lines, pins = [], []
            real = S.price_carry_of

            def carry_on(pin, model, real=real, pins=pins):
                pins.append(dict(pin))
                return real({S.F_PRICE_CARRY: "1"}, model)
            S.price_carry_of = carry_on
            try:
                S.build(dict(env, agent_db=w.dbpath + str(len(extra))),
                        environ=dict({"WA_AGENT_DRAFTS": "1", S.F_BOOK: "1", S.F_PRICE_CARRY: "1"}, **extra), model=m2,
                        line=lines.append)
            finally:
                S.price_carry_of = real
            self.assertEqual(pins, [{S.F_PRICE_CARRY: "0"}])
            i = [k for k, ln in enumerate(lines) if ln.startswith(after)]
            self.assertEqual(len(i), 1, lines)
            self.assertEqual(lines[i[0] + 1], "цена через ход (WA_AGENT_PRICE_CARRY): " + W_ON)
            self.assertIs(type(m2).__mro__[1], PC.PriceCarryMixin)
            self.assertEqual(any(c is BC.BookCtxMixin for c in type(m2).__mro__), bool(extra))

    def test_flag_without_model(self):
        self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: "1"}, None), (False, W_NO_MODEL))

    def test_module_not_built(self):
        w, env = _env()
        model = _model(env, book=True)
        saved = sys.modules.get(NEW_MODULE)
        sys.modules[NEW_MODULE] = None
        try:
            got = S.price_carry_of({S.F_PRICE_CARRY: "1"}, model)
        finally:
            sys.modules[NEW_MODULE] = saved
        self.assertEqual(got, (False, W_NO_MOD))
        self.assertIs(type(model), M.ModelAdapter)

    def test_flag_values(self):
        w, env = _env()
        for v in ("1", "true", "YES", " on "):
            model = _model(env, book=True)
            self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: v}, model), (True, W_ON), v)
        for v in ("0", "да", "", "off", "2"):
            model = _model(env, book=True)
            self.assertEqual(S.price_carry_of({S.F_PRICE_CARRY: v}, model), (None, None), v)
            self.assertIs(type(model), M.ModelAdapter)

    def test_with_price_carry_cached_and_idempotent(self):
        a = PC.with_price_carry(M.ModelAdapter)
        self.assertIs(a, PC.with_price_carry(M.ModelAdapter))
        self.assertIs(PC.with_price_carry(a), a)
        self.assertEqual((a.__name__, a.__module__), ("PriceCarryModelAdapter", "wa_price_carry"))


# ══ закрепление ════════════════════════════════════════════════════════════════════════════════════════════════

def _blob(path):
    data = open(path, "rb").read()
    shas = {hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()}
    lf = data.replace(b"\r\n", b"\n")
    shas.add(hashlib.sha1(b"blob %d\0" % len(lf) + lf).hexdigest())
    return shas


def _tree(name):
    return ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())


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


class Locks(unittest.TestCase):

    def test_pins(self):
        """Родитель примеси тот же, что на 13b4188: закреплённые файлы не тронуты."""
        for name, sha in PINS.items():
            self.assertIn(sha, _blob(os.path.join(ROOT, name)), name)

    def test_module_locks(self):
        tree = _tree("wa_price_carry.py")
        imps = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imps |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                imps.add((n.module or "").split(".")[0])
        self.assertLessEqual(imps, {"datetime", "re", "wa_agent_model", "wa_agent_knowledge"})
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        bad = {"open", "sqlite3", "subprocess", "socket", "os", "sys", "bridge_client", "create_booking", "_post",
               "wa_book_ctx", "BC"}
        self.assertFalse(names & bad, names & bad)
        own = {k for k in vars(PC.PriceCarryMixin) if not (k.startswith("__") and k.endswith("__"))}
        self.assertLessEqual(own, {"_history", "_price"} | {k for k in own if k.startswith("_pcarry")})
        for fn in ("__init__", "build", "draft", "build_followup", "_book", "_draft_tools"):
            self.assertNotIn(fn, vars(PC.PriceCarryMixin), fn)
        for name in sorted(os.listdir(ROOT)):
            if name.endswith(".py") and name != "wa_price_carry.py":
                try:
                    t = ast.parse(open(os.path.join(ROOT, name), encoding="utf-8").read())
                except (SyntaxError, UnicodeDecodeError):
                    continue
                self.assertNotIn(NEW_MODULE, _module_level_imports(t), name)

    def test_one_price_word_list(self):
        """Слово цены — то же выражение, что у родителя (`M._PRICE_ASK`), своего списка нет; «похоже на модель» — как у
        наличия по переписке."""
        src = open(os.path.join(ROOT, "wa_price_carry.py"), encoding="utf-8").read()
        self.assertIn("M._PRICE_ASK.search(prev)", src)
        self.assertNotIn("_PRICE_ASK =", src)
        self.assertEqual(PC._RX_MODEL_LIKE.pattern, BC._RX_MODEL_LIKE.pattern)

    def test_signatures(self):
        def params(fn):
            return list(inspect.signature(fn).parameters)
        self.assertEqual(params(M.ModelAdapter._price), ["self", "ask", "today", "ctx", "ask_day"])
        self.assertEqual(params(PC.PriceCarryMixin._price), ["self", "ask", "today", "ctx", "ask_day"])
        self.assertEqual(params(S.price_carry_of), ["environ", "model"])
        src = inspect.getsource(S.make_model) + inspect.getsource(S.models_of) + inspect.getsource(S.main)
        self.assertNotIn(NEW_MODULE, src)
        self.assertNotIn("price_carry", src)


# ══ чистые функции: голдены ═══════════════════════════════════════════════════════════════════════════════════

class Goldens(unittest.TestCase):

    def test_date_question(self):
        for t in ("На какие даты?", "Подскажите даты аренды?", "С какого по какое число?", "Когда вам нужен байк?",
                  "На сколько дней планируете?", "Уточните срок?", "What dates are you planning?", "When do you need it?",
                  "For how many days?", "Отличный выбор! А какой датой начнём?"):
            self.assertTrue(PC.date_question(t), t)
        for t in ("Добрый день! Коллега подскажет.", "На какие даты — уточню у коллег.", "Кандидат?", "Передать коллеге?",
                  "Какой цвет?", "Нужен шлем?", ""):
            self.assertFalse(PC.date_question(t), t)

    def test_has_amount(self):
        for t in ("2 000 бат", "2000 ฿", "฿ 400", "400 baht", "1,200 THB"):
            self.assertTrue(PC.has_amount(t), t)
        for t in ("на 5 дней", "PCX 160", "с 10 по 15 октября", ""):
            self.assertFalse(PC.has_amount(t), t)

    def test_tail_term(self):
        D = datetime.date
        self.assertEqual(PC.tail_term("с 10 по 15 октября", TODAY), (D(2026, 10, 10), D(2026, 10, 15), None))
        self.assertEqual(PC.tail_term("10.10 - 15.10", TODAY), (D(2026, 10, 10), D(2026, 10, 15), None))
        self.assertEqual(PC.tail_term("10 октября на 5 дней", TODAY), (D(2026, 10, 10), D(2026, 10, 15), None))
        self.assertEqual(PC.tail_term("с 10 по 15 октября, 5 суток", TODAY), (D(2026, 10, 10), D(2026, 10, 15), None))
        self.assertEqual(PC.tail_term("с 10 по 15 октября\nс 10 по 15 октября", TODAY),
                         (D(2026, 10, 10), D(2026, 10, 15), None))
        for t in ("с 10 по 15 октября или с 12 по 17 октября", "с 10 по 15 октября, 7 дней", "15.10 и 10.10",
                  "с 10 по 15 октября и ещё 20 октября", "2026-10-10 - 2026-10-15 или 2027-10-10 - 2027-10-15"):
            self.assertEqual(PC.tail_term(t, TODAY)[2], PC.MANY, t)
        for t in ("с 10 по 15", "на 5 дней", "10 октября", "завтра"):
            self.assertEqual(PC.tail_term(t, TODAY)[2], PC.LOOSE, t)

    def test_term_sign(self):
        for t in ("с 10 по 15", "на 5 дней", "10 октября", "завтра", "с 10 по 15 октября"):
            self.assertTrue(PC.term_sign(t, TODAY), t)
        for t in ("спасибо", "ок", "PCX 160", "а шлем есть?"):
            self.assertFalse(PC.term_sign(t, TODAY), t)


if __name__ == "__main__":
    unittest.main()
