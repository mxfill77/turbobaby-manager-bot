#!/usr/bin/env python3
"""ПРАВИЛО ИСПОЛНЯЮЩЕЙ ПОЗИЦИИ (04.08.2026): краснит имя, стоящее там, где его ИСПОЛНИТ разборщик.

Закрыты ДВЕ живые течи: имя операции в ИМЕНИ ФАЙЛА (секция 2) и SQL-глагол в ПЕЧАТАЕМОЙ строке
(секция 4) — до правки обе были КРАСНЫМИ. Фактический вызов краснит как прежде, слепое тело
остаётся красным (секция 1), прежде закрытые классы не ослаблены (секции 3, 5).

ГРАНИЦА, названная честно: строковый литерал НЕ-денежной операции (докстринг, печатаемая строка,
список слов) краснит ПО-ПРЕЖНЕМУ — так РЕШЕНО 02.08.2026, голден назван словом «намеренно»
(tests/test_root_a_vps.py), плюс остатки 117/135 в tests/test_money_action.py. Правило туда не
распространено: это снятие существующего красного в трёх классах, развилка владельца.
"""
import os
import sys
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pretool_guard as g

PY = os.path.join(g.PROJECT, "venv/bin/python3")
CLEAN = "print(1)\n"


class ExecPositionBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="execpos_")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def script(self, name, body):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
        return p

    def verdict(self, cmd):
        kind, hit, _ = g.classify(cmd, g.PROJECT)
        return kind, hit


class TestActualCallStillRed(ExecPositionBase):
    """(1) ФАКТИЧЕСКИЙ ВЫЗОВ РОЖДАЕТ КРАСНОЕ КАК ПРЕЖДЕ — правило ничего не ослабило."""

    def test_parsed_call_is_red(self):
        p = self.script("s1.py", "import bridge_client\nbridge_client.create_booking(7)\n")
        self.assertEqual(self.verdict(PY + " " + p), ("red", "create_booking"))

    def test_money_call_is_red(self):
        p = self.script("s2.py", "import bridge_client\nbridge_client.add_transaction(500)\n")
        self.assertEqual(self.verdict(PY + " " + p), ("red", "add_transaction"))

    def test_sql_given_to_cursor_is_red(self):
        p = self.script("s3.py", "import sqlite3\n"
                                 "c = sqlite3.connect('/tmp/execpos_other.db')\n"
                                 "c.execute('UPDATE rides SET price=1')\n")
        self.assertEqual(self.verdict(PY + " " + p), ("red", "sqlite"))

    def test_dowrite_declaration_is_red(self):
        p = self.script("s4.py", CLEAN)
        self.assertEqual(self.verdict("DOWRITE=1 " + PY + " " + p), ("red", "DOWRITE"))

    def test_blind_body_stays_red(self):
        cmd = PY + " - <<'EOF'\ncreate_booking(7)\nEOF"
        self.assertEqual(self.verdict(cmd)[0], "red")


class TestNameInFileName(ExecPositionBase):
    """(2) ИМЯ ОПЕРАЦИИ В ИМЕНИ ФАЙЛА. До правила: red по шагу 1 (`tok in scan`) при ЧИСТОМ теле."""

    def test_operation_name_in_script_path_is_not_red(self):
        p = self.script("create_booking_report.py", CLEAN)
        self.assertNotEqual(self.verdict(PY + " " + p)[0], "red")

    def test_money_name_in_script_path_is_not_red(self):
        p = self.script("add_transaction_audit.py", CLEAN)
        self.assertNotEqual(self.verdict(PY + " " + p)[0], "red")


class TestNameInProse(ExecPositionBase):
    """(3) ИМЯ В КОММЕНТАРИИ (закрыто 02.08.2026, здесь — регресс неослабления).

    ГРАНИЦА: строковый литерал НЕ-денежной операции (докстринг, печатаемая строка, список слов)
    краснит ПО-ПРЕЖНЕМУ — решение 02.08.2026, голден так и назван: «докстринг остаётся красным
    намеренно (строка = возможное действие)», tests/test_root_a_vps.py. Правило исполняющей позиции
    туда НЕ распространено намеренно: это снятие существующего красного сразу в трёх классах,
    и решать его владельцу. Голдена «печатаемая строка зелёная» здесь поэтому НЕТ."""

    def test_comment_is_not_red(self):
        p = self.script("s7.py", "# create_booking не трогаем\nprint(1)\n")
        self.assertNotEqual(self.verdict(PY + " " + p)[0], "red")


class TestSqlInProse(ExecPositionBase):
    """(4) SQL-ГЛАГОЛ В ПЕЧАТАЕМОЙ СТРОКЕ. До правила: red «sqlite», а ОБЪЕКТ карточки («БД …»)
    тянулся из той же прозы — карточка про запись, за которой нет записи."""

    def test_printed_sql_is_not_red(self):
        p = self.script("s8.py", "import sqlite3\n"
                                 "print('UPDATE rides SET price=1 в /tmp/execpos_other.db')\n")
        self.assertNotEqual(self.verdict(PY + " " + p)[0], "red")

    def test_sql_in_docstring_is_not_red(self):
        p = self.script("s9.py", '"""отчёт: UPDATE rides SET price=1 в /tmp/execpos_other.db"""\n'
                                 "print(1)\n")
        self.assertNotEqual(self.verdict(PY + " " + p)[0], "red")


class TestNotWeakened(ExecPositionBase):
    """(5)(6) НЕОСЛАБЛЕНИЕ: жёсткий блок, SQL-операнд argv и прежде закрытые классы (шаблон
    поиска, argv скрипта) судятся ровно как судились."""

    def test_secrets_file_operand_still_hard_blocked(self):
        p = self.script("s10.py", CLEAN)
        kind, hit = self.verdict(PY + " " + p + " " + os.path.join(g.PROJECT, ".env"))
        self.assertEqual((kind, hit), ("block", "env_hard_block"))

    def test_sql_operand_of_unknown_script_still_red(self):
        cmd = PY + " " + os.path.join(self.dir, "нет_такого.py") + \
            " \"UPDATE rides SET price=1\" /tmp/execpos_other.db"
        self.assertEqual(self.verdict(cmd), ("red", "sqlite"))

    def test_search_pattern_is_data(self):
        p = self.script("s11.py", CLEAN)
        cmd = PY + " " + p + " && grep -n create_booking /tmp/execpos_none.log"
        self.assertNotEqual(self.verdict(cmd)[0], "red")

    def test_script_argv_is_data(self):
        p = self.script("s12.py", CLEAN)
        cmd = PY + " " + p + " \"DONE закрыл create_booking\""
        self.assertNotEqual(self.verdict(cmd)[0], "red")


if __name__ == "__main__":
    unittest.main(verbosity=2)
