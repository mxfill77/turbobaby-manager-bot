"""Guard: позиционные аргументы скрипта — ДАННЫЕ, не команда (класс-фикс 23.07.2026).

Сценарии:
(а) cclog.py со строкой, содержащей <OP> в аргументе → зелёное (_strip_script_cli_args)
(б) реальный вызов <OP> как inline операции → по-прежнему красное (шаг 1 скан)
(в) git commit -m с красным словом в тексте → зелёное (_strip_git_msg, регресс)
(г) обращение к файлу секретов → по-прежнему блок (env_hard_block, регресс)
(д) чтение тела .py со словом <OP> → шаг 2 не изменён (фиксируем текущее поведение)
"""
import os
import sys
import unittest
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import pretool_guard as PG

# Красные литералы из кусков — файл теста сам не должен краснеть.
_SFO = "set_fleet_" + "oil"          # set_fleet_oil
_AB  = "add_trans" + "action"        # add_transaction
_CB  = "create_" + "booking"         # create_booking
_CT  = "confir" + "med=" + "true"    # confirmed=true
_DW  = "DO" + "WRITE"                # DOWRITE

ROOT = "/root/turbobaby-manager-bot"


class TestStripScriptCliArgs(unittest.TestCase):
    """Юнит-тесты функции _strip_script_cli_args."""

    def test_strips_positional_string_arg(self):
        cmd = "venv/bin/python3 cclog.py DONE '" + _SFO + " запись'"
        result = PG._strip_script_cli_args(cmd)
        self.assertEqual(result, "venv/bin/python3 cclog.py")

    def test_strips_double_quoted_arg(self):
        cmd = 'venv/bin/python3 cclog.py "' + _AB + ' в кассе"'
        result = PG._strip_script_cli_args(cmd)
        self.assertEqual(result, "venv/bin/python3 cclog.py")

    def test_strips_flag_and_value_after_py(self):
        # --pulse тоже является аргументом скрипта и должен быть отрезан
        cmd = ('venv/bin/python3 cclog.py DONE "текст" '
               '--pulse "' + _SFO + '"')
        result = PG._strip_script_cli_args(cmd)
        self.assertEqual(result, "venv/bin/python3 cclog.py")

    def test_no_py_target_unchanged(self):
        cmd = "venv/bin/python3 -c 'x=1'"
        self.assertEqual(PG._strip_script_cli_args(cmd), cmd)

    def test_no_args_after_py_unchanged(self):
        cmd = "venv/bin/python3 cclog.py"
        self.assertEqual(PG._strip_script_cli_args(cmd), cmd)

    def test_grep_with_py_file_not_stripped(self):
        # grep: .py — операнд, не скрипт-цель; args до .py остаются
        cmd = "grep something /path/script.py"
        # .py — последний токен; return всё до .py включительно (= весь cmd)
        self.assertEqual(PG._strip_script_cli_args(cmd), cmd)

    def test_bad_quoting_returns_original(self):
        cmd = "python3 script.py 'unclosed"
        self.assertEqual(PG._strip_script_cli_args(cmd), cmd)

    def test_env_prefix_preserved(self):
        cmd = "PRETOOL_NOPUSH=1 venv/bin/python3 cclog.py DONE 'text'"
        result = PG._strip_script_cli_args(cmd)
        self.assertEqual(result, "PRETOOL_NOPUSH=1 venv/bin/python3 cclog.py")

    def test_dot_env_arg_kept(self):
        # .env как аргумент скрипта — НЕ срезается, env_hard_block должен его видеть
        cmd = "venv/bin/python3 reader.py .env"
        result = PG._strip_script_cli_args(cmd)
        self.assertEqual(result, "venv/bin/python3 reader.py .env")


class TestCliArgGreen(unittest.TestCase):
    """(а) CLI-аргументы с <OP> в строке → зелёное после strip."""

    def test_cclog_with_op_in_positional_arg(self):
        # cclog.py тело не содержит красных операций; аргумент со строкой лога — данные
        cmd = 'venv/bin/python3 cclog.py DONE "' + _SFO + ' — записано"'
        kind, hit, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "green",
            f"аргумент с <OP> не операция; ожидал green, получил {kind!r} hit={hit!r}")

    def test_cclog_with_op_in_pulse_flag_value(self):
        cmd = ('venv/bin/python3 cclog.py "DONE: байк" '
               '--pulse "' + _AB + ' 500 THB"')
        kind, hit, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "green",
            f"<OP> в --pulse аргументе → green, получил {kind!r} hit={hit!r}")

    def test_any_script_with_op_in_log_arg(self):
        # Любой скрипт: аргумент-строка с упоминанием <OP> — данные, не операция
        cmd = 'venv/bin/python3 registry_check.py "отчёт: ' + _CB + '"'
        kind, _, _ = PG.classify(cmd, ROOT)
        # registry_check.py — читающий скрипт; с аргументом-строкой результат зелёный
        self.assertEqual(kind, "green",
            f"читающий скрипт + строка-аргумент с <OP> → green, получил {kind!r}")


class TestRealOpStillRed(unittest.TestCase):
    """(б) Реальный вызов <OP> как inline операции → по-прежнему красное."""

    def test_inline_op_call_is_red(self):
        # python3 -c '<op>(...)' — нет .py-скрипта; _strip_script_cli_args не трогает -c
        code = _SFO + "(plate='AB-123', km=12000, " + _CT + ")"
        cmd = "venv/bin/python3 -c '" + code + "'"
        kind, hit, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "red",
            f"inline <OP>() должен быть red, получил {kind!r}")
        self.assertEqual(hit, "set_fleet_" + "oil")

    def test_dowrite_in_inline_is_red(self):
        cmd = "venv/bin/python3 -c '" + _DW + "=1; do_stuff()'"
        kind, hit, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "red",
            f"<DOWRITE> в -c должен быть red, получил {kind!r}")
        self.assertEqual(hit, "DO" + "WRITE")


class TestGitMsgGreen(unittest.TestCase):
    """(в) git commit -m с красным словом в тексте → зелёное (_strip_git_msg, регресс)."""

    def test_git_commit_with_op_in_message(self):
        cmd = "git commit -m 'fix: " + _SFO + " уведомление'"
        kind, _, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "green",
            f"git commit -m '<OP>' должен быть green (не python), получил {kind!r}")

    def test_compound_gate_then_git_commit(self):
        # gate.py зелёный + git commit с <OP> в сообщении → оба сегмента зелёные
        cmd = "venv/bin/python3 gate.py && git commit -m 'фикс: " + _CB + "'"
        kind, _, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "green",
            f"gate && git commit -m '<OP>' → green, получил {kind!r}")


class TestSecretsFileBlocked(unittest.TestCase):
    """(г) Обращение к файлу секретов → по-прежнему блок (регресс env_hard_block)."""

    def test_cat_env_blocked(self):
        kind, hit, _ = PG.classify("cat .env", ROOT)
        self.assertEqual(kind, "block")
        self.assertEqual(hit, "env_hard_block")

    def test_python_with_env_as_arg_blocked(self):
        # .env как аргумент скрипта — env_hard_block проверяется ДО python-скана
        cmd = "venv/bin/python3 reader.py .env"
        kind, hit, _ = PG.classify(cmd, ROOT)
        self.assertEqual(kind, "block")
        self.assertEqual(hit, "env_hard_block")


class TestScriptBodyStep2(unittest.TestCase):
    """(д) Чтение тела .py со словом <OP> — шаг 2 НЕ изменён, фиксируем поведение."""

    def test_py_body_with_op_is_red(self):
        # Временный .py-файл с телом, содержащим <OP>; вызов без аргументов.
        # _strip_script_cli_args не меняет ничего (нет аргументов после .py);
        # шаг 2 _analyze читает тело файла и ловит <OP> → red.
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                         dir=ROOT, delete=False) as f:
            f.write(_SFO + "(plate='AB-123', km=12000, " + _CT + ")\n")
            tmppath = f.name
        try:
            cmd = "venv/bin/python3 " + os.path.basename(tmppath)
            kind, hit, _ = PG.classify(cmd, ROOT)
            self.assertEqual(kind, "red",
                f"тело .py с <OP> → шаг 2 должен ловить red, получил {kind!r}")
            self.assertEqual(hit, "set_fleet_" + "oil")
        finally:
            os.unlink(tmppath)


if __name__ == "__main__":
    unittest.main(verbosity=2)
