"""РЕШЕНИЕ «РАБОТЫ БЫЛИ НА ДРУГОМ ПРОБЕГЕ» (batch_odo.py, 25.08.2026).

Предмет — ЧИСТАЯ функция: разбор ответа человека («24500 15.07.2026») в пару «пробег + дата»,
три исхода приёмки и замок против ложного зелёного. Мира здесь нет вовсе: «сегодня» приходит
параметром, мост не зовётся, писать нечем.

У КАЖДОГО ОТРИЦАТЕЛЬНОГО СЛУЧАЯ ЕСТЬ БЛИЗНЕЦ «то же без порчи — проходит»: иначе fail-closed
мог бы оказаться «всегда закрыто», и сьют этого не заметил бы.
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, "/root/turbobaby-manager-bot")

import batch_odo as B        # noqa: E402
import odo_lower as L        # noqa: E402

TODAY = datetime.date(2026, 8, 25)


class TestFlag(unittest.TestCase):
    """(1) Ручка отката — разбор тот же, что у соседних ручек."""

    def test_default_alive(self):
        self.assertTrue(B.enabled(None))
        self.assertTrue(B.enabled("1"))

    def test_zero_kills(self):
        for raw in ("0", "", "нет", "no", "off", " 0 ", "OFF"):
            self.assertFalse(B.enabled(raw), raw)

    def test_flag_name(self):
        self.assertEqual(B.FLAG_ENV, "BATCH_ODO")


class TestParseBoth(unittest.TestCase):
    """(2) ЗАМОК: `READY` приходит РОВНО ОДНИМ путём — есть пробег И есть дата."""

    def test_plain_pair(self):
        v = B.verdict("24500 15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.READY)
        self.assertTrue(v["ok"])
        self.assertEqual(v["km"], 24500)
        self.assertEqual(v["date_iso"], "2026-07-15")
        self.assertEqual(v["date_human"], "15.07.2026")

    def test_words_around_numbers(self):
        v = B.verdict("работы были 15.07.2026 на 24500 км", today=TODAY)
        self.assertEqual(v["state"], B.READY)
        self.assertEqual((v["km"], v["date_iso"]), (24500, "2026-07-15"))

    def test_km_with_spaces(self):
        v = B.verdict("24 500 км, 15.07.2026", today=TODAY)
        self.assertEqual(v["km"], 24500)
        self.assertTrue(v["ok"])

    def test_iso_date(self):
        v = B.verdict("2026-07-15 24500", today=TODAY)
        self.assertEqual((v["km"], v["date_iso"]), (24500, "2026-07-15"))

    def test_slash_date(self):
        v = B.verdict("15/07/2026 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-07-15")

    def test_two_digit_year(self):
        v = B.verdict("15.07.26 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-07-15")

    def test_year_not_eaten_as_km(self):
        """ГОД НЕ СТАНОВИТСЯ КИЛОМЕТРАМИ: кусок даты вырезается ДО разбора числа."""
        v = B.verdict("15.07.2026 24500", today=TODAY)
        self.assertEqual(v["km"], 24500)

    def test_day_month_only_uses_this_year(self):
        v = B.verdict("15.07 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-07-15")

    def test_day_month_in_future_falls_back_a_year(self):
        """Декабрь, названный в январе, — это ПРОШЛЫЙ декабрь, а не ещё не наступивший."""
        v = B.verdict("20.12 24500", today=datetime.date(2026, 1, 10))
        self.assertEqual(v["date_iso"], "2025-12-20")

    def test_word_today(self):
        v = B.verdict("сегодня 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-08-25")

    def test_word_yesterday(self):
        v = B.verdict("вчера 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-08-24")

    def test_word_day_before_yesterday_beats_yesterday(self):
        """«позавчера» содержит «вчера» — проверяется ПЕРВЫМ, иначе съест его."""
        v = B.verdict("позавчера 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-08-23")

    def test_thai_yesterday(self):
        v = B.verdict("เมื่อวาน 24500", today=TODAY)
        self.assertEqual(v["date_iso"], "2026-08-24")


class TestMissing(unittest.TestCase):
    """(3) Нет любого из двух — работа НЕ пишется, и человеку сказано, ЧТО прислать."""

    def test_km_only(self):
        v = B.verdict("24500", today=TODAY)
        self.assertEqual(v["state"], B.NEED_DATE)
        self.assertFalse(v["ok"])
        self.assertEqual(v["km"], 24500)
        self.assertIsNone(v["date"])
        self.assertIn("ДАТЫ", v["say_ru"])
        self.assertTrue(v["say_th"].strip())

    def test_date_only(self):
        v = B.verdict("15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.NEED_KM)
        self.assertFalse(v["ok"])
        self.assertIn("ПРОБЕГА", v["say_ru"])
        self.assertTrue(v["say_th"].strip())

    def test_nothing(self):
        v = B.verdict("были работы", today=TODAY)
        self.assertEqual(v["state"], B.NEED_BOTH)
        self.assertFalse(v["ok"])
        self.assertIsNone(v["km"])
        self.assertIsNone(v["date"])

    def test_empty(self):
        for raw in ("", "   ", None):
            v = B.verdict(raw, today=TODAY)
            self.assertFalse(v["ok"], repr(raw))
            self.assertEqual(v["state"], B.NEED_BOTH)

    def test_every_refusal_says_what_to_send(self):
        """Каждый отказ несёт ДЕЙСТВИЕ на ОБОИХ языках — глухого «нет» тут нет по построению."""
        for raw in ("24500", "15.07.2026", "были работы", "", "12 15.07.2026", "31.02.2026 24500"):
            v = B.verdict(raw, today=TODAY)
            self.assertFalse(v["ok"], repr(raw))
            self.assertTrue(v["say_ru"].strip(), repr(raw))
            self.assertTrue(v["say_th"].strip(), repr(raw))


class TestBadValues(unittest.TestCase):
    """(4) Названо, но негодно — отказ называет ЧИСЛО, а не диагноз. У каждого есть близнец."""

    def test_km_too_small(self):
        v = B.verdict("12 15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.BAD_KM)
        self.assertIsNone(v["km"])

    def test_km_too_small_twin_ok(self):
        v = B.verdict("120 15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.READY)
        self.assertEqual(v["km"], 120)

    def test_km_too_big(self):
        v = B.verdict("12345678 15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.BAD_KM)

    def test_km_too_big_twin_ok(self):
        v = B.verdict("999999 15.07.2026", today=TODAY)
        self.assertEqual(v["state"], B.READY)

    def test_date_not_in_calendar(self):
        v = B.verdict("31.02.2026 24500", today=TODAY)
        self.assertEqual(v["state"], B.BAD_DATE)
        self.assertIsNone(v["date"])

    def test_date_not_in_calendar_twin_ok(self):
        v = B.verdict("28.02.2026 24500", today=TODAY)
        self.assertEqual(v["state"], B.READY)

    def test_date_in_future(self):
        v = B.verdict("01.09.2026 24500", today=TODAY)
        self.assertEqual(v["state"], B.BAD_DATE)
        self.assertIsNone(v["date"])

    def test_date_in_future_twin_ok(self):
        v = B.verdict("25.08.2026 24500", today=TODAY)
        self.assertEqual(v["state"], B.READY)

    def test_date_too_old(self):
        v = B.verdict("15.07.2020 24500", today=TODAY)
        self.assertEqual(v["state"], B.BAD_DATE)

    def test_date_too_old_twin_ok(self):
        v = B.verdict("15.07.2026 24500", today=TODAY)
        self.assertEqual(v["state"], B.READY)

    def test_no_today_no_future_check(self):
        """Часов у решения нет: `today` не дали — о будущем не заявляем, разбор идёт как есть."""
        v = B.verdict("01.09.2026 24500", today=None)
        self.assertEqual(v["state"], B.READY)


class TestLowering(unittest.TestCase):
    """(5) Дорога понижения НЕ изобретается второй раз — различитель берётся у `odo_lower`."""

    def test_lower_detected(self):
        low = B.lowering(41200, 24500)
        self.assertTrue(low["known"])
        self.assertTrue(low["lower"])
        self.assertEqual((low["recorded"], low["named"], low["drop"]), (41200, 24500, 16700))

    def test_not_lower(self):
        low = B.lowering(24000, 24500)
        self.assertTrue(low["known"])
        self.assertFalse(low["lower"])

    def test_unknown_recorded(self):
        low = B.lowering("", 24500)
        self.assertFalse(low["known"])
        self.assertFalse(low["lower"])

    def test_mirrors_odo_lower_diff(self):
        """Своего сравнения нет: на одних входах оба ответа совпадают поле в поле."""
        for rec, named in ((41200, 24500), (100, 100), (1, 999999), ("", 5), (7, None)):
            mine, theirs = B.lowering(rec, named), L.diff(rec, named)
            self.assertEqual(mine["known"], theirs["known"])
            self.assertEqual(mine["lower"], theirs["lower"])
            self.assertEqual(mine["drop"], theirs["drop"])

    def test_explanation_is_odo_lower_verbatim(self):
        for raw in ("да", "ใช่", "", "аа", "меняли колодки в другом сервисе месяц назад"):
            self.assertEqual(B.explanation_verdict(raw), L.explanation_verdict(raw), repr(raw))

    def test_agreement_is_not_explanation(self):
        for raw in ("да", "ok", "ใช่", "верно"):
            self.assertFalse(B.explanation_verdict(raw)["ok"], repr(raw))

    def test_real_words_accepted(self):
        v = B.explanation_verdict("работы делали 15 июля, забыли внести вовремя")
        self.assertTrue(v["ok"])
        self.assertTrue(v["text"])

    def test_explanation_ask_shows_numbers(self):
        say = B.explanation_ask("TESTBIKE", B.lowering(41200, 24500))
        for n in ("41200", "24500", "16700"):
            self.assertIn(n, say["ru"])
            self.assertIn(n, say["th"])

    def test_explanation_ask_promises_odometer_untouched(self):
        say = B.explanation_ask("TESTBIKE", B.lowering(41200, 24500))
        self.assertIn("НЕ меняю", say["ru"])


class TestQuestion(unittest.TestCase):
    """(6) Вопрос называет текущее число и обещает его не трогать; суммы не спрашивает."""

    def test_names_current(self):
        say = B.question("TESTBIKE", ["колодки"], 41200)
        self.assertIn("41200", say["ru"])
        self.assertIn("41200", say["th"])

    def test_promises_untouched(self):
        say = B.question("TESTBIKE", ["колодки"], 41200)
        self.assertIn("НЕ трогаю", say["ru"])

    def test_lists_works(self):
        say = B.question("TESTBIKE", ["колодки", "цепь"], 41200)
        self.assertIn("колодки", say["ru"])
        self.assertIn("цепь", say["ru"])

    def test_no_current_no_lie(self):
        say = B.question("TESTBIKE", ["колодки"], "")
        self.assertNotIn("Сейчас на байке записано", say["ru"])

    def test_does_not_ask_for_sum(self):
        """Прямой запрет правила владельца: «сумма НЕ спрашивается отдельным вопросом»."""
        say = B.question("TESTBIKE", ["колодки"], 41200)
        low = (say["ru"] + " " + say["th"]).lower()
        for word in ("сколько стоил", "стоимость", "сумм", "цена", "ราคา"):
            self.assertNotIn(word, low)

    def test_both_halves_present(self):
        say = B.question("", [], None)
        self.assertTrue(say["ru"].strip())
        self.assertTrue(say["th"].strip())


class TestReceipt(unittest.TestCase):
    """(7) ОБЕ ПОЛОВИНЫ ИЗ ОДНОГО ИСХОДА (класс 14.08) и НИ ОДНА потеря не молчит."""

    def test_written(self):
        r = B.receipt("TESTBIKE", ["колодки", "цепь"], [], 24500, "15.07.2026")
        self.assertEqual(r["state"], "written")
        self.assertIn("✅", r["ru"])
        self.assertIn("✅", r["th"])

    def test_partial_names_the_loss_in_both(self):
        r = B.receipt("TESTBIKE", ["колодки"], ["цепь"], 24500, "15.07.2026")
        self.assertEqual(r["state"], "partial")
        self.assertIn("цепь", r["ru"])
        self.assertIn("цепь", r["th"])

    def test_failed(self):
        r = B.receipt("TESTBIKE", [], ["колодки"], 24500, "15.07.2026")
        self.assertEqual(r["state"], "failed")
        self.assertIn("колодки", r["ru"])
        self.assertIn("колодки", r["th"])

    def test_halves_never_disagree(self):
        """Русская говорит «записано» ⟺ тайская говорит «записано» — на всех трёх исходах."""
        for w, l in ((["a"], []), (["a"], ["b"]), ([], ["b"])):
            r = B.receipt("BIKE", w, l, 24500, "15.07.2026")
            self.assertEqual("✅" in r["ru"], "✅" in r["th"], r["state"])
            self.assertEqual("⚠️" in r["ru"], "⚠️" in r["th"], r["state"])

    def test_km_and_date_named_in_both(self):
        r = B.receipt("TESTBIKE", ["колодки"], [], 24500, "15.07.2026")
        for token in ("24500", "15.07.2026"):
            self.assertIn(token, r["ru"])
            self.assertIn(token, r["th"])

    def test_says_odometer_untouched(self):
        r = B.receipt("TESTBIKE", ["колодки"], [], 24500, "15.07.2026", current_km=41200)
        self.assertIn("не тронут", r["ru"])
        self.assertIn("41200", r["ru"])

    def test_registers_named_as_not_shifted(self):
        """Умолчание о регистре читалось бы как «срок ТО обновлён» — это ложное зелёное."""
        r = B.receipt("TESTBIKE", ["масло"], [], 24500, "15.07.2026", registers=["ТО Oil"])
        self.assertIn("Срок следующего ТО не сдвигал", r["ru"])
        self.assertIn("ТО Oil", r["ru"])
        self.assertTrue(r["th"].strip())

    def test_no_registers_no_noise(self):
        r = B.receipt("TESTBIKE", ["колодки"], [], 24500, "15.07.2026", registers=[])
        self.assertNotIn("Срок следующего ТО", r["ru"])

    def test_explanation_quoted(self):
        r = B.receipt("TESTBIKE", ["колодки"], [], 24500, "15.07.2026",
                      explanation="делали в другом сервисе")
        self.assertIn("делали в другом сервисе", r["ru"])
        self.assertIn("делали в другом сервисе", r["th"])


class TestPurity(unittest.TestCase):
    """(8) ГРАНИЦА УСТРОЙСТВОМ, а не докстрингом: разбор ast — тот же, что в гейте."""

    def test_imports_are_exactly_three_named(self):
        import ast
        src = open("/root/turbobaby-manager-bot/batch_odo.py", encoding="utf-8").read()
        roots = set()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Import):
                roots.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                roots.add((node.module or "").split(".")[0])
        self.assertEqual(roots, {"re", "datetime", "odo_lower"})

    def test_no_hands(self):
        import ast
        src = open("/root/turbobaby-manager-bot/batch_odo.py", encoding="utf-8").read()
        bad = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in ("open", "exec", "eval", "compile", "__import__"):
                bad.append(node.func.id)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id in ("os", "subprocess", "socket", "requests", "shutil"):
                bad.append(node.func.value.id)
        self.assertEqual(bad, [])

    def test_guard_registered_in_gate(self):
        src = open("/root/turbobaby-manager-bot/invariants_check.py", encoding="utf-8").read()
        self.assertIn("BATCH_ODO_PURE", src)

    def test_has_no_clock_of_its_own(self):
        """«Сегодня» приносят руки: своих часов у решения нет ни одного ВЫЗОВА.

        Судится ДЕЙСТВИЕ, а не подстрока, и это не педантизм — первая редакция этой проверки
        искала `time.time` текстом и краснела на `datetime.timedelta`, внутри которого такая
        подстрока просто лежит. Ровно тот класс, против которого написан весь гард (`40c8425`)."""
        import ast
        src = open("/root/turbobaby-manager-bot/batch_odo.py", encoding="utf-8").read()
        clocks = {"now", "today", "utcnow", "time", "monotonic", "fromtimestamp"}
        found = []
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in clocks:
                found.append(f"{ast.dump(node.func)[:40]}.{node.func.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in clocks:
                found.append(node.func.id)
        self.assertEqual(found, [], f"решение спросило время само: {found}")

    def test_timedelta_is_not_a_clock(self):
        """Близнец к предыдущему: арифметика над ДАННОЙ датой законна и должна проходить."""
        self.assertEqual(B.verdict("вчера 24500", today=TODAY)["date_iso"], "2026-08-24")


if __name__ == "__main__":
    unittest.main(verbosity=2)
