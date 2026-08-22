# -*- coding: utf-8 -*-
"""ЗАМОК ПОВТОРНЫХ ПОДСКАЗОК В ТЕМАХ БАЙКОВ (22.08.2026).

Предмет — правило «та же подсказка по тому же байку не уходит второй раз, пока не изменилось
состояние, её породившее», и ГРАНИЦЫ этого правила.

Байки в фикстурах ВЫДУМАНЫ и помечены ТЕСТ — в парке TurboBaby таких нет; ни одна проверка
не касается ни рабочих таблиц, ни зеркала обслуживания, ни моста.

Секции:
  (1) первая подсказка проходит ВСЕГДА;
  (2) повтор того же состояния в окне — подавлен;
  (3) ОТРИЦАТЕЛЬНАЯ, без неё задача не закрыта: состояние ИЗМЕНИЛОСЬ → подсказка обязана
      уйти снова. Проверяется для КАЖДОГО из 14 видов на ЕГО форме состояния;
  (4) право на повтор при долго держащемся состоянии (порог 24 ч) и его обоснование числом;
  (5) fail-safe: любая дырка → ОТПРАВКА, как было до замка;
  (6) живые серии висяка из журнала 60 суток;
  (7) руки: все 14 видов заведены, чужих дверей `_send` на местах подсказок не осталось,
      откат ручкой возвращает прежний путь;
  (8) чистота решения (импортов ноль) — зеркало инварианта HINT_DEDUP_PURE.
"""
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import hint_dedup

CHAT = -1002751134848
TOPIC = 4242
BIKE = "ТЕСТ ЕДИНОРОГ 0001"          # выдуманный байк, в парке такого нет
BIKE2 = "ТЕСТ ЕДИНОРОГ 0002"
HOUR = 3600.0
T0 = 1_700_000_000.0


def v(state, prev=None, now=T0, kind="F", bike=BIKE, topic=TOPIC, **kw):
    return hint_dedup.verdict(kind, bike, state, prev, now, chat_id=CHAT, topic_id=topic, **kw)


def rec(state, ts=T0):
    return {"fp": hint_dedup.state_fingerprint(state), "ts": ts}


# ---------------------------------------------------------------- (1) первая проходит всегда
class FirstAlwaysGoes(unittest.TestCase):
    def test_no_memory_at_all(self):
        r = v(("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"]), prev=None)
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.FIRST)

    def test_first_for_every_kind(self):
        for kind in hint_dedup.KINDS:
            r = v(("что-то", kind), prev=None, kind=kind)
            self.assertTrue(r["send"], f"{kind}: первая подсказка обязана пройти")

    def test_other_bike_is_another_key(self):
        state = ("dirt", True)
        r = v(state, prev=None, kind="C", bike=BIKE2)
        self.assertTrue(r["send"])
        self.assertNotEqual(hint_dedup.key(CHAT, TOPIC, BIKE, "C"),
                            hint_dedup.key(CHAT, TOPIC, BIKE2, "C"))

    def test_other_kind_is_another_key(self):
        self.assertNotEqual(hint_dedup.key(CHAT, TOPIC, BIKE, "C"),
                            hint_dedup.key(CHAT, TOPIC, BIKE, "J"))


# ------------------------------------------------------------------- (2) повтор — подавлен
class SameStateSuppressed(unittest.TestCase):
    def test_same_state_one_hour_later(self):
        st = ("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"])
        r = v(st, prev=rec(st), now=T0 + HOUR)
        self.assertFalse(r["send"])
        self.assertEqual(r["why"], hint_dedup.REPEAT)

    def test_same_state_just_under_threshold(self):
        st = ("dirt", True)
        r = v(st, prev=rec(st), now=T0 + 23.9 * HOUR, kind="C")
        self.assertFalse(r["send"])

    def test_works_order_is_not_a_change(self):
        """['oil','gear'] и ['gear','oil'] — ОДНО состояние: порядок перечня значением не является."""
        a = ("works", ["oil", "gear"])
        b = ("works", ["gear", "oil"])
        self.assertEqual(hint_dedup.state_fingerprint(a), hint_dedup.state_fingerprint(b))
        self.assertFalse(v(b, prev=rec(a), now=T0 + HOUR, kind="I")["send"])

    def test_case_and_spaces_are_not_a_change(self):
        a = ("damage", "Треснут нижний обтекатель")
        b = ("damage", "  треснут   нижний обтекатель ")
        self.assertEqual(hint_dedup.state_fingerprint(a), hint_dedup.state_fingerprint(b))
        self.assertFalse(v(b, prev=rec(a), now=T0 + HOUR, kind="J")["send"])


# ============================================================================================
#  (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ — БЕЗ НЕГО ЗАДАЧА НЕ ЗАКРЫТА
#  Замок, который молчит ВСЕГДА, защитой не является. Состояние изменилось — подсказка
#  ОБЯЗАНА уйти снова, и это проверяется для КАЖДОГО из 14 видов на ЕГО форме состояния.
# ============================================================================================
CHANGED_PAIRS = {
    # вид: (состояние ДО, состояние ПОСЛЕ, что именно изменилось в мире)
    "A1": (("ask_odo", "oil"), ("ask_odo", "gear"), "просят одометр под другую работу"),
    "A2": (("sp_ask_odo", ["oil"], "ждёт_факт"), ("sp_ask_odo", ["oil", "gear"], "ждёт_факт"),
           "механик доназвал редуктор"),
    "A3": (("e2b_ask_odo", ["oil"]), ("e2b_ask_odo", ["abs"]), "другая работа из мозга"),
    "B": (("sp_ask_done", ["oil"], "ждёт_факт"), ("sp_ask_done", ["oil", "pads"], "ждёт_факт"),
          "в заявку добавились колодки"),
    "C": (("dirt", True), ("dirt", "сильная грязь после дождя"), "вердикт vision о грязи стал другим"),
    "D": (("no_photo", "return", False, False), ("no_photo", "return", True, False),
          "топливо прислали, пробега всё ещё нет"),
    "E": (("service_due", "oil", "overdue", 36200), ("service_due", "oil", "overdue", 40200),
          "масло заменили — следующий порог прыгнул"),
    "E2": (("service_due", "gear", "due", 22000), ("service_due", "gear", "overdue", 22000),
           "было due, стало overdue"),
    "F": (("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"]),
          ("sp_stuck", "2026-07-30T09:10", "ждёт_факт", ["oil"]),
          "заявку закрыли и открыли НОВУЮ (живой случай NMAX 9548 14.08)"),
    "G": (("sp_escalate", ["oil"]), ("sp_escalate", ["oil", "gear", "abs"]), "перечень висящего вырос"),
    "H": (("oil_or_km", "overdue", 36200), ("oil_or_km", "ok", 40200), "ТО сделали"),
    "I": (("works", ["замена масла"]), ("works", ["замена масла", "замена колодок"]),
          "механик сдал ещё одну работу"),
    "J": (("damage", "Скол пластика под сиденьем"), ("damage", "Треснут нижний обтекатель"),
          "повреждение ДРУГОЕ"),
    "L": (("mileage_confirm", "41346"), ("mileage_confirm", "41890"), "с фото прочли другое число"),
}


class StateChangedMustSendAgain(unittest.TestCase):
    def test_every_kind_covered(self):
        self.assertEqual(sorted(CHANGED_PAIRS), sorted(hint_dedup.KINDS),
                         "у КАЖДОГО вида обязана быть отрицательная пара «состояние изменилось»")

    def test_changed_state_sends_again_now(self):
        """Сразу же, через минуту после первой отправки — и всё равно ОБЯЗАНА уйти."""
        for kind, (before, after, why) in CHANGED_PAIRS.items():
            r = v(after, prev=rec(before), now=T0 + 60, kind=kind)
            self.assertTrue(r["send"], f"{kind}: {why} — подсказка обязана уйти снова")
            self.assertEqual(r["why"], hint_dedup.CHANGED, f"{kind}: исход обязан называться сменой состояния")

    def test_changed_state_is_a_different_fingerprint(self):
        for kind, (before, after, _why) in CHANGED_PAIRS.items():
            self.assertNotEqual(hint_dedup.state_fingerprint(before),
                                hint_dedup.state_fingerprint(after),
                                f"{kind}: разные состояния обязаны давать разные отпечатки")

    def test_lock_is_not_a_mute(self):
        """Сводно: замок, который молчит всегда, — не защита. На 14 сменах состояния 14 отправок."""
        sent = sum(1 for k, (b, a, _) in CHANGED_PAIRS.items()
                   if v(a, prev=rec(b), now=T0 + 60, kind=k)["send"])
        self.assertEqual(sent, len(hint_dedup.KINDS))

    def test_and_the_same_state_is_still_held(self):
        """Зеркало отрицательного: те же 14 видов при НЕизменном состоянии молчат все 14."""
        held = sum(1 for k, (b, _a, _) in CHANGED_PAIRS.items()
                   if not v(b, prev=rec(b), now=T0 + 60, kind=k)["send"])
        self.assertEqual(held, len(hint_dedup.KINDS))


# ------------------------------------------------- (4) право на повтор при долгом состоянии
class RightToRepeat(unittest.TestCase):
    def test_default_is_twenty_four_hours(self):
        self.assertEqual(hint_dedup.REPEAT_H_DEFAULT, 24.0)

    def test_after_threshold_repeat_allowed(self):
        st = ("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"])
        r = v(st, prev=rec(st), now=T0 + 24 * HOUR)
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.DUE)

    def test_before_threshold_denied(self):
        st = ("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"])
        self.assertFalse(v(st, prev=rec(st), now=T0 + 23 * HOUR)["send"])

    def test_threshold_is_stable_plus_minus_six_hours(self):
        """Замер: T = 18 · 20 · 24 · 27 · 30 ч дают ОДИН результат на живых сериях висяка."""
        series_h = [0.0, 7.0, 14.0, 21.0, 28.0, 35.0]      # CB 650R BLACK 3503, ×6 за 35 ч
        st = ("sp_stuck", "2026-07-29T03:47", "ждёт_факт", ["oil"])
        counts = set()
        for T in (18.0, 20.0, 24.0, 27.0, 30.0):
            kept, last = 0, None
            for h in series_h:
                r = v(st, prev=(None if last is None else rec(st, last)), now=T0 + h * HOUR, repeat_h=T)
                if r["send"]:
                    kept += 1
                    last = T0 + h * HOUR
            counts.add(kept)
        self.assertEqual(counts, {2}, "порог устойчив к ±6 ч: тот же результат")

    def test_threshold_exceeds_longest_working_shift(self):
        """Снизу порог обязан быть длиннее рабочей смены (03…19 UTC = 17 ч по корпусу),
        иначе повтор читают ТЕ ЖЕ люди; сверху — короче 26 ч (за ней в распределении пауз
        пустой промежуток 26…34 ч, то есть уже пропущенные сутки)."""
        self.assertGreater(hint_dedup.REPEAT_H_DEFAULT, 17.0)
        self.assertLess(hint_dedup.REPEAT_H_DEFAULT, 26.0)
        self.assertEqual(hint_dedup.REPEAT_H_DEFAULT % 24.0, 0.0, "кратность суткам держит ФАЗУ")


# ------------------------------------------------------------------------- (5) fail-safe
class FailSafeSends(unittest.TestCase):
    def test_disabled_sends(self):
        st = ("dirt", True)
        r = v(st, prev=rec(st), now=T0 + HOUR, kind="C", enabled=False)
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.OFF)

    def test_zero_threshold_sends(self):
        st = ("dirt", True)
        self.assertTrue(v(st, prev=rec(st), now=T0 + HOUR, kind="C", repeat_h=0)["send"])

    def test_no_address_sends(self):
        st = ("dirt", True)
        r = hint_dedup.verdict("C", "", st, rec(st), T0 + HOUR, chat_id=CHAT, topic_id=None)
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.NO_ADDR)
        self.assertEqual(r["key"], "")

    def test_no_state_sends(self):
        r = v(None, prev=rec(("dirt", True)), now=T0 + HOUR, kind="C")
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.NO_STATE)

    def test_empty_state_parts_send(self):
        self.assertTrue(v(("", None, False), prev=None, kind="C")["send"])

    def test_broken_prev_sends(self):
        st = ("dirt", True)
        for bad in ("мусор", 17, [], {"fp": hint_dedup.state_fingerprint(st), "ts": "вчера"},
                    {"fp": hint_dedup.state_fingerprint(st)}):
            r = v(st, prev=bad, now=T0 + HOUR, kind="C")
            self.assertTrue(r["send"], f"битая запись {bad!r} обязана давать отправку")

    def test_clock_went_backwards_sends(self):
        st = ("dirt", True)
        r = v(st, prev=rec(st, T0 + 5 * HOUR), now=T0, kind="C")
        self.assertTrue(r["send"])
        self.assertEqual(r["why"], hint_dedup.BACKWARD)

    def test_unknown_kind_still_judged(self):
        """Опечатка в виде не открывает дверь настежь — ключ всё равно строится."""
        st = ("dirt", True)
        self.assertFalse(hint_dedup.verdict("СЮРПРИЗ", BIKE, st, rec(st), T0 + HOUR,
                                            chat_id=CHAT, topic_id=TOPIC)["send"])

    def test_prune_keeps_fresh_drops_stale_and_survives_garbage(self):
        seen = {"a": rec(("x",), T0), "b": rec(("y",), T0 - 8 * 24 * HOUR), "c": "мусор"}
        out = hint_dedup.prune(seen, T0)
        self.assertEqual(sorted(out), ["a"])
        self.assertEqual(hint_dedup.prune("не словарь", T0), {})
        self.assertEqual(sorted(hint_dedup.prune(seen, "не число")), sorted(seen))


# --------------------------------------------------------------- (6) живые серии из журнала
class LiveSeries(unittest.TestCase):
    #: три серии переписи 22.08.2026: часы от первой отправки серии (журнал splinter.log)
    SERIES = {
        "CB 650R BLACK 3503": ([0.0, 7.0, 14.0, 21.0, 28.0, 35.0], 1),
        "XADV 750 BLACK 3902": ([0.0, 7.0, 14.0, 20.0, 26.4, 32.7], 1),
        # у NMAX 9548 на 4-й отправке возраст сбросился 23.0 → 6.4 ч: это ВТОРАЯ заявка
        "NMAX RED WHITE 9548": ([0.0, 8.8, 16.6, 32.0, 39.0], 2),
    }

    def _replay(self, hours, births):
        """Прогон серии сквозь ЖИВОЕ решение: сколько отправок осталось бы."""
        kept, last = 0, {}
        for i, h in enumerate(hours):
            born = "заявка-2" if (births == 2 and i >= 3) else "заявка-1"
            st = ("sp_stuck", born, "ждёт_факт", ["oil"])
            k = hint_dedup.key(CHAT, TOPIC, BIKE, "F")
            r = hint_dedup.verdict("F", BIKE, st, last.get(k), T0 + h * HOUR,
                                   chat_id=CHAT, topic_id=TOPIC)
            if r["send"]:
                kept += 1
                last[k] = {"fp": r["fp"], "ts": T0 + h * HOUR}
        return kept

    def test_each_series_collapses(self):
        for bike, (hours, births) in self.SERIES.items():
            kept = self._replay(hours, births)
            self.assertLess(kept, len(hours), f"{bike}: серия обязана схлопнуться")

    def test_second_request_is_not_a_repeat(self):
        """НЕ схлопнуть в одну: у NMAX 9548 второй повод — ДРУГАЯ заявка, она имеет право."""
        hours, births = self.SERIES["NMAX RED WHITE 9548"]
        self.assertGreaterEqual(self._replay(hours, births), 2)

    def test_total_over_three_series(self):
        """19 отправок F за 60 суток, из них в трёх сериях 17; остальные 2 — одиночные."""
        total = sum(self._replay(h, b) for h, b in self.SERIES.values())
        self.assertEqual(sum(len(h) for h, _ in self.SERIES.values()), 17)
        self.assertEqual(total, 6, "17 отправок трёх серий сжимаются в 6")


# ------------------------------------------------------------------------------ (7) руки
SPL = os.path.join(REPO, "splinter.py")


class HandsInSplinter(unittest.TestCase):
    def setUp(self):
        with open(SPL, encoding="utf-8") as f:
            self.src = f.read()

    def test_all_fourteen_kinds_wired(self):
        wired = set()
        for m in ast.walk(ast.parse(self.src)):
            if isinstance(m, ast.Call) and getattr(m.func, "id", "") == "_hint_send":
                for kw in m.keywords:
                    if kw.arg == "kind":
                        if isinstance(kw.value, ast.Constant):
                            wired.add(kw.value.value)
                        elif isinstance(kw.value, ast.IfExp):      # E / E2 одной дверью
                            for br in (kw.value.body, kw.value.orelse):
                                if isinstance(br, ast.Constant):
                                    wired.add(br.value)
        self.assertEqual(sorted(wired), sorted(hint_dedup.KINDS),
                         "замок обязан стоять на ВСЕХ 14 видах переписи")

    def test_one_door_not_fourteen_patches(self):
        """Решение зовётся из ОДНОГО места splinter.py — из рук `_hint_send`, а не из мест отправки."""
        callers = set()
        tree = ast.parse(self.src)
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and getattr(node.func.value, "id", "") == "hint_dedup"
                            and node.func.attr == "verdict"):
                        callers.add(fn.name)
        self.assertEqual(callers, {"_hint_send"})

    def test_suppressed_send_is_handled_by_callers(self):
        """Подавлено = сообщения НЕТ. Каждое место, которое БЕРЁТ результат в переменную,
        обязано сверить его с `HINT_SKIPPED` ДО того, как им воспользуется.

        Сверять на None НЕЛЬЗЯ, и это не вкус: `_send` вправе вернуть None (так делает любой
        мок), и тогда подавлением считалась бы любая отправка, ничего не вернувшая. Живой
        случай: у висяка после такого «подавления» не ставилась отметка `_SP_LAST_SENT` —
        замок МОЛЧА ломал прежний троттл 6 ч и давал ДВА напоминания вместо одного. Поймал
        tests/test_service_pending.py; этот замок держит границу впредь."""
        tree = ast.parse(self.src)
        taken, guarded = 0, 0
        for fn in ast.walk(tree):
            body = getattr(fn, "body", None)
            if not isinstance(body, list):
                continue
            for i, node in enumerate(body):
                if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Await)):
                    continue
                call = node.value.value
                if not (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "_hint_send"):
                    continue
                taken += 1
                nxt = body[i + 1] if i + 1 < len(body) else None
                ok = (isinstance(nxt, ast.If) and isinstance(nxt.test, ast.Compare)
                      and isinstance(nxt.test.ops[0], (ast.Is, ast.IsNot))
                      and getattr(nxt.test.comparators[0], "id", "") == "HINT_SKIPPED")
                if ok:
                    guarded += 1
        self.assertGreaterEqual(taken, 3, "места, берущие результат в переменную, обязаны быть")
        self.assertEqual(taken, guarded, "каждое обязано сверять результат с HINT_SKIPPED")

    def test_none_is_never_used_as_the_suppression_signal(self):
        """Зеркало того же: сравнения результата двери с None в splinter.py быть не должно."""
        self.assertNotIn("_hint_send(...) is None", self.src)
        tree = ast.parse(self.src)
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == "_hint_send":
                returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
                bare_none = [r for r in returns
                             if isinstance(r.value, ast.Constant) and r.value.value is None]
                self.assertEqual(bare_none, [], "дверь не смеет возвращать голый None как «подавлено»")

    def test_rollback_handle_named(self):
        self.assertIn("HINTS_DEDUP", self.src)
        self.assertIn("HINT_REPEAT_H", self.src)

    def test_button_answer_bypasses_the_lock(self):
        """Ответ на КНОПКУ человека (always_notify) — не повтор бота: замок туда не лезет."""
        self.assertIn("if always_notify:", self.src)

    def test_hands_write_nothing_to_bridge(self):
        """Руки замка не завели НИ ОДНОГО обращения к мосту: ни в живые таблицы, ни в зеркало
        «обслуживание». Всё, что они делают, — свой файл и `_send`."""
        tree = ast.parse(self.src)
        hands = [fn for fn in ast.walk(tree)
                 if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and fn.name in ("_hint_send", "_hint_load", "_hint_save",
                                 "_hint_enabled", "_hint_repeat_h")]
        self.assertEqual(len(hands), 5, "руки замка — ровно пять функций")
        for fn in hands:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    owner = getattr(node.func.value, "id", "")
                    self.assertNotEqual(owner, "bridge", f"{fn.name}: моста у рук замка быть не должно")
                    self.assertNotIn(node.func.attr,
                                     ("service_pending_upsert", "service_upsert", "service_set_pin",
                                      "set_fleet_oil", "set_fleet_service", "add_transaction"),
                                     f"{fn.name}: пишущих операций у рук замка быть не должно")

    def test_state_file_is_ours_not_a_sheet(self):
        self.assertIn("hint_dedup_state.json", self.src)


# ============================================================================================
#  (9) СКВОЗНОЙ ПРОГОН РУК — не только решения.
#  Изоляция легаси-сьютов (`HINTS_DEDUP=0`) отняла бы у замка всякую живую проверку дверей,
#  поэтому дверь `splinter._hint_send` гоняется здесь целиком: с поддельным контекстом, на
#  ВРЕМЕННОМ файле памяти. Боевого состояния не касаемся — класс «фикстура в живом состоянии»
#  этому репозиторию известен (боевой wallet_cache.json с фикстурой test_deposit_link).
# ============================================================================================
class HandsEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import asyncio, tempfile
        cls.asyncio = asyncio
        cls.tmp = tempfile.mkdtemp(prefix="hint_dedup_test_")
        cls.state = os.path.join(cls.tmp, "state.json")
        os.environ["BRIDGE_URL"] = os.environ.get("BRIDGE_URL", "http://x")
        os.environ["BRIDGE_TOKEN"] = os.environ.get("BRIDGE_TOKEN", "x")
        os.environ["HINTS_DEDUP"] = "1"
        os.environ["HINT_DEDUP_STATE"] = cls.state
        import splinter
        cls.S = splinter
        # путь считается на КАЖДОМ зове, поэтому подмены env довольно

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree("/tmp/" + os.path.basename(cls.tmp), ignore_errors=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.pop("HINT_DEDUP_STATE", None)

    def setUp(self):
        self.sent = []
        self.S._HINT_SEEN = None
        try:
            os.remove(self.state)
        except OSError:
            pass

        outer = self

        class FakeBot:
            async def send_message(self, **kw):
                outer.sent.append(kw)
                return type("M", (), {"message_id": 100 + len(outer.sent)})()

        self.ctx = type("Ctx", (), {"bot": FakeBot()})()

    def door(self, kind, state, bike=BIKE):
        return self.asyncio.run(
            self.S._hint_send(self.ctx, kind=kind, bike=bike, state=state,
                              chat_id=CHAT, topic_id=TOPIC, text="текст подсказки"))

    def test_first_goes_repeat_is_silent_change_goes_again(self):
        st = ("sp_stuck", "заявка-1", "ждёт_факт", ["oil"])
        self.assertIsNot(self.door("F", st), self.S.HINT_SKIPPED, "первая обязана уйти")
        self.assertIs(self.door("F", st), self.S.HINT_SKIPPED, "тот же повод второй раз — молчим")
        self.assertIs(self.door("F", st), self.S.HINT_SKIPPED, "и третий")
        self.assertEqual(len(self.sent), 1, "в чат ушло РОВНО одно сообщение")
        # ОТРИЦАТЕЛЬНАЯ половина сквозь ЖИВЫЕ руки: состояние изменилось → обязана уйти
        self.assertIsNot(self.door("F", ("sp_stuck", "заявка-2", "ждёт_факт", ["oil"])),
                          self.S.HINT_SKIPPED, "состояние изменилось — обязана уйти")
        self.assertEqual(len(self.sent), 2)

    def test_other_bike_is_not_a_repeat(self):
        st = ("dirt", True)
        self.assertIsNot(self.door("C", st, bike=BIKE), self.S.HINT_SKIPPED)
        self.assertIsNot(self.door("C", st, bike=BIKE2), self.S.HINT_SKIPPED, "другой байк — свой повод")
        self.assertEqual(len(self.sent), 2)

    def test_memory_survives_process_restart(self):
        """splinter за окно переписи перезапускался 126 раз — память обязана пережить рестарт."""
        st = ("dirt", True)
        self.assertIsNot(self.door("C", st), self.S.HINT_SKIPPED)
        self.S._HINT_SEEN = None                 # как будто процесс поднялся заново
        self.assertIs(self.door("C", st), self.S.HINT_SKIPPED, "после рестарта повтор всё равно повтор")
        self.assertTrue(os.path.exists(self.state))

    def test_rollback_handle_restores_previous_path(self):
        st = ("dirt", True)
        os.environ["HINTS_DEDUP"] = "0"
        try:
            self.assertIsNot(self.door("C", st), self.S.HINT_SKIPPED)
            self.assertIsNot(self.door("C", st), self.S.HINT_SKIPPED, "с выключенным замком обе уходят, как до него")
            self.assertEqual(len(self.sent), 2)
            self.assertFalse(os.path.exists(self.state),
                             "выключенный замок не читает и не пишет память вовсе")
        finally:
            os.environ["HINTS_DEDUP"] = "1"

    def test_failed_send_does_not_spend_the_hint(self):
        """Упавшая отправка подсказку не тратит: факт запоминается ПОСЛЕ `_send`, не до."""
        class Boom:
            async def send_message(self, **kw):
                raise RuntimeError("сеть легла")
        good, self.ctx.bot = self.ctx.bot, Boom()
        st = ("dirt", True)
        with self.assertRaises(RuntimeError):
            self.door("C", st)
        self.ctx.bot = good
        self.assertIsNot(self.door("C", st), self.S.HINT_SKIPPED, "после падения подсказка обязана уйти")

    def test_test_run_marker_alone_diverts_the_path(self):
        """Даже БЕЗ явной подмены пути прогон тестов в боевой файл не пишет: путь судит признак
        прогона теми же четырьмя именами, что и гард. Изоляция сьютов по одному была бы игрой
        в догонялки — новый сьют открыл бы дыру снова (так и случилось на первом полном гейте:
        в боевом файле оказались РЕАЛЬНЫЕ байки 4957/4248/4724/6334 из легаси-фикстур)."""
        live = os.path.abspath(os.path.join(REPO, "hint_dedup_state.json"))
        saved = os.environ.pop("HINT_DEDUP_STATE", None)
        try:
            for mark in self.S._HINT_TEST_MARKS:
                had = os.environ.get(mark)
                os.environ[mark] = "1"
                try:
                    got = os.path.abspath(self.S._hint_state_path())
                    self.assertNotEqual(got, live,
                                        f"признака {mark} довольно, чтобы увести память из боевого файла")
                    self.assertIn(str(os.getpid()), got,
                                  "файл прогона — СВОЙ НА ПРОЦЕСС: общее имя течёт между прогонами гейта")
                finally:
                    if had is None:
                        os.environ.pop(mark, None)
                    else:
                        os.environ[mark] = had
        finally:
            if saved is not None:
                os.environ["HINT_DEDUP_STATE"] = saved

    def test_never_touches_the_live_state_file(self):
        live = os.path.join(REPO, "hint_dedup_state.json")
        before = os.path.getmtime(live) if os.path.exists(live) else None
        self.door("C", ("dirt", True))
        after = os.path.getmtime(live) if os.path.exists(live) else None
        self.assertEqual(before, after, "прогон теста НЕ смеет писать в боевое состояние")
        self.assertNotEqual(os.path.abspath(self.S._hint_state_path()), os.path.abspath(live))


# --------------------------------------------------------------------------- (8) чистота
class Purity(unittest.TestCase):
    def test_zero_imports(self):
        with open(os.path.join(REPO, "hint_dedup.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(imports, [], "у решения импортов НОЛЬ — ни времени, ни диска, ни сети")

    def test_no_open_no_exec(self):
        with open(os.path.join(REPO, "hint_dedup.py"), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for banned in ("open", "exec", "eval", "__import__", "compile"):
            self.assertNotIn(banned, names)

    def test_invariant_registered(self):
        import invariants_check
        self.assertIn("HINT_DEDUP_PURE", [n for n, _fn in invariants_check.CHECKS])


if __name__ == "__main__":
    unittest.main(verbosity=2)
