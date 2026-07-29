# -*- coding: utf-8 -*-
"""ARGV .py-скрипта = ДАННЫЕ, а не операция (класс «данные ≠ команда», 24.07.2026).

Было: `venv/bin/python3 cclog.py "DONE …: закрыл <OP> …"` краснел на шаге 1 _analyze — боевое
слово ловилось В ТЕКСТЕ журнальной строки, хотя скрипт пишет в журнал, а не в Лист1/CRM.
Фикс: _strip_script_cli_args() вырезает всё ПОСЛЕ имени .py-скрипта из СКАН-представления
(зовётся в _units до построения скан-текста). Тот же приём, что _strip_git_msg для текста git -m.

СТРАЖ НЕ ОСЛАБЛЕН — это здесь важнее самого фикса:
- ТЕЛО .py читается и сканируется как прежде (_analyze шаг 2 идёт по СЫРОЙ команде);
- операнды-улики в argv (файл секретов, .db/SQL-write, $(…)/`…`) НЕ вырезаются;
- красное в СОСЕДНЕМ сегменте цепи вырезание первого сегмента не заслоняет.

Боевые операции в тексте называем <OP>; литералы собраны КОНКАТЕНАЦИЕЙ — иначе красное слово
попало бы в тело самого тест-файла и гард заблокировал бы его чтение.
Тесты чистые: зовут classify()/_strip_script_cli_args(), НИЧЕГО не исполняя (см. docstring classify).
"""
import atexit
import os
import shutil
import sys
import tempfile
import types

# ROOT берём от файла, а не константой /root/… — тест обязан идти и на VPS, и в клоне.
# shlex (внутри гарда) съедает обратные слэши → путь держим в POSIX-форме.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("ORCH_TEST_MODE", "1")   # без сети
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # без Telegram

# pretool_guard тянет fcntl (POSIX-локи дедупа). Классификация от него не зависит: на ПК
# (Windows-клон репо) подставляем пустышку, на VPS импортируется настоящий модуль. Без этого
# обещание докстринга «идёт и в клоне» не выполнялось — файл падал на импорте.
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG   # noqa: E402


def _p(path):
    return path.replace("\\", "/")


PY = _p(os.path.join(ROOT, "venv", "bin", "python3"))
CCLOG = _p(os.path.join(ROOT, "cclog.py"))
ENVF = _p(os.path.join(ROOT, ".env"))

# Боевые операции — ТОЛЬКО конкатенацией (см. docstring).
OP_CRM = "create" + "_" + "booking"        # <OP> — операция CRM
OP_MONEY = "add" + "_" + "transaction"     # <OP> — операция кассы

TMP = tempfile.mkdtemp(prefix="pt_sa_")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)


def _fixture(name, body):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return _p(path)


# Боевой скрипт: операция живёт в ТЕЛЕ (как настоящий писатель в Лист1/CRM).
FX_OP_BODY = _fixture("fx_op_body.py",
                      "# фикстура регресса\nbridge.call('" + OP_CRM + "', plate='ABC-1')\n")
# Скрипт БЕЗ операции: <OP> приедет только в argv.
FX_PLAIN = _fixture("fx_plain.py", "# фикстура: тело чистое\nprint('ok')\n")

# Живая форма журнальной строки — ровно то, чем стреляет контур (её и чинит фикс).
JOURNAL_LINE = "DONE Dispatch 04:20: закрыл " + OP_CRM + " по байку ABC-1, гейт зелёный"


def _kind(cmd, cwd=ROOT):
    return PG.classify(cmd, cwd)[0]


# ── (а) журнальный скрипт: <OP> в АРГУМЕНТЕ → ЗЕЛЁНОЕ ──────────────────────────
def test_a_journal_arg_is_green():
    assert _kind('%s %s "%s"' % (PY, CCLOG, JOURNAL_LINE)) == "green"


def test_a_journal_arg_green_with_interp_flag():
    # флаг САМОГО интерпретатора до имени скрипта не съеден, argv вырезан
    assert _kind('%s -u %s "%s"' % (PY, CCLOG, JOURNAL_LINE)) == "green"


def test_a_journal_arg_green_second_op():
    assert _kind('%s %s "перевёл %s на 500"' % (PY, CCLOG, OP_MONEY)) == "green"


# ── (б) РЕАЛЬНЫЙ вызов <OP> как операции → КРАСНОЕ ────────────────────────────
def test_b_op_in_script_body_is_red():
    kind, hit, _ = PG.classify("%s %s" % (PY, FX_OP_BODY), ROOT)
    assert (kind, hit) == ("red", OP_CRM)


def test_b_op_inline_c_is_red():
    # инлайн-код не стоит после .py-токена → вырезанию не подлежит
    kind, hit, _ = PG.classify('%s -c "bridge.call(\'%s\')"' % (PY, OP_CRM), ROOT)
    assert (kind, hit) == ("red", OP_CRM)


def test_b_op_before_py_token_is_red():
    # красное ДО имени скрипта (например, в -m-модуле/обёртке) вырезание не трогает
    kind, _hit, _ = PG.classify("%s %s %s" % (PY, OP_MONEY, FX_PLAIN), ROOT)
    assert kind == "red"


# ── (в) git commit -m с красным словом → ЗЕЛЁНОЕ ──────────────────────────────
def test_v_git_commit_msg_is_green():
    assert _kind('git commit -m "фикс разбора %s в отчёте"' % OP_CRM) == "green"


def test_v_git_commit_am_is_green():
    assert _kind('git commit -am "правка %s"' % OP_MONEY) == "green"


# ── (г) файл секретов → БЛОК (жёсткий, approve невозможен) ────────────────────
def test_g_secrets_file_is_block():
    kind, hit, _ = PG.classify("cat %s" % ENVF, ROOT)
    assert (kind, hit) == ("block", "env_hard_block")
    assert PG.can_approve(kind, hit) is False


def test_g_secrets_as_script_arg_still_blocks():
    # ГЛАВНЫЙ пин фикса: операнд-улика в argv НЕ вырезается — дыры в жёстком блоке нет
    kind, hit, _ = PG.classify("%s %s %s" % (PY, FX_PLAIN, ENVF), ROOT)
    assert (kind, hit) == ("block", "env_hard_block")


def test_g_sql_write_as_script_arg_still_red():
    kind, hit, _ = PG.classify(
        '%s %s "UPDATE bikes SET x=1" /root/other.db' % (PY, FX_PLAIN), ROOT)
    assert (kind, hit) == ("red", "sqlite")


# ── (д) чтение ТЕЛА .py, где встречается слово <OP> — поведение НЕ меняем ─────
def test_d_running_py_with_op_in_body_stays_red():
    # тело читается и сканируется как прежде — фикс сканирование тела не ослабил
    assert _kind("%s %s" % (PY, FX_OP_BODY)) == "red"


def test_d_cat_py_with_op_in_body_stays_green():
    # не-python команда: гард сканирует ТЕКСТ команды, тело файла не читает (текущее поведение)
    assert _kind("cat %s" % FX_OP_BODY) == "green"


def test_d_grep_op_in_py_stays_green():
    # красное слово в ПОИСКОВОМ шаблоне — данные (класс «данные ≠ команда», уже был)
    assert _kind('grep -n "%s" %s' % (OP_CRM, FX_OP_BODY)) == "green"


# ── страж не ослаблен: соседний сегмент цепи ─────────────────────────────────
def test_compound_red_segment_not_shielded():
    cmd = '%s %s "%s" && %s %s' % (PY, CCLOG, JOURNAL_LINE, PY, FX_OP_BODY)
    assert _kind(cmd) == "red"


def test_compound_kill_segment_not_shielded():
    cmd = '%s %s "%s" && pkill -9 splinter' % (PY, CCLOG, JOURNAL_LINE)
    kind, hit, _ = PG.classify(cmd, ROOT)
    assert (kind, hit) == ("block", "proc_hard_block")


# ── границы и fail-safe самой _strip_script_cli_args ─────────────────────────
def test_fn_no_py_token_unchanged():
    cmd = "git status --porcelain"
    assert PG._strip_script_cli_args(cmd) == cmd


def test_fn_py_last_token_unchanged():
    cmd = "%s %s" % (PY, CCLOG)
    assert PG._strip_script_cli_args(cmd) == cmd


def test_fn_broken_quoting_unchanged():
    cmd = '%s %s "незакрытая кавычка' % (PY, CCLOG)
    assert PG._strip_script_cli_args(cmd) == cmd      # fail-safe: скан полный, краснее


def test_fn_keeps_interpreter_and_script():
    out = PG._strip_script_cli_args('%s -u %s "%s"' % (PY, CCLOG, JOURNAL_LINE))
    assert out.endswith("cclog.py") and " -u " in out
    assert OP_CRM not in out


def test_fn_drops_quoted_literal():
    out = PG._strip_script_cli_args('%s %s "%s"' % (PY, CCLOG, JOURNAL_LINE))
    assert OP_CRM not in out and "DONE" not in out


def test_fn_keeps_evidence_operands():
    out = PG._strip_script_cli_args("%s %s %s" % (PY, FX_PLAIN, ENVF))
    assert ".env" in out
    out2 = PG._strip_script_cli_args('%s %s "text" /root/other.db' % (PY, FX_PLAIN))
    assert ".db" in out2 and "text" not in out2


def test_fn_keeps_exec_substitution_arg():
    out = PG._strip_script_cli_args('%s %s "$(cat /root/secret)"' % (PY, FX_PLAIN))
    assert "$(" in out


# ── раннер для gate.py (репо гоняет tests/*.py и напрямую, не только pytest) ──
if __name__ == "__main__":
    res = []
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            res.append(True)
            print("  PASS " + name)
        except Exception as exc:
            res.append(False)
            print("  FAIL " + name + " → " + repr(exc))
    print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
    sys.exit(0 if all(res) else 1)
