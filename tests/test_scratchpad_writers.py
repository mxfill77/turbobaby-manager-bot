"""Тесты инварианта SCRATCHPAD_WRITERS (invariants_check.py).

Инвариант сканирует _*.py в корне репо на прямые вызовы write_doc
(в обход канонического пути write_cclog() / cclog.py).
Все тесты используют temp-каталоги через _SCRATCHPAD_ROOT — сети нет.
"""
import os
import sys
import tempfile
import shutil
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import invariants_check as ic
from invariants_check import (
    FakeWorld, CheckRun, run_all, check_scratchpad_writers,
)


# ─── Вспомогательные фикстуры ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmpdir():
    """Временный каталог; после теста удаляется."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_scratchpad_root(tmpdir):
    """Каждый тест видит свой tmpdir как _SCRATCHPAD_ROOT; сброс после теста."""
    old = ic._SCRATCHPAD_ROOT
    ic._SCRATCHPAD_ROOT = tmpdir
    yield tmpdir
    ic._SCRATCHPAD_ROOT = old


def _world():
    """Минимальный FakeWorld — SCRATCHPAD_WRITERS его не использует."""
    return FakeWorld(bikes=[], clients=[], queue_ip=[])


def _run(root=None):
    """Запустить ТОЛЬКО SCRATCHPAD_WRITERS с заданным root (или текущим _SCRATCHPAD_ROOT)."""
    if root is not None:
        ic._SCRATCHPAD_ROOT = root
    r = CheckRun("SCRATCHPAD_WRITERS")
    check_scratchpad_writers(_world(), r)
    return r


def _write(d, name, content):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ─── Тесты ────────────────────────────────────────────────────────────────────────────────────

class TestScratchpadWritersClean:
    """Инвариант НЕ флагует допустимые случаи."""

    def test_empty_dir(self, tmpdir):
        """Пустой каталог → 0 находок."""
        r = _run(tmpdir)
        assert r.findings == []

    def test_no_underscore_py_files(self, tmpdir):
        """Файлы без _ или без .py — не сканируются."""
        _write(tmpdir, "not_scratch.py", "bc.write_doc(text='x')\n")
        _write(tmpdir, "_readme.txt", "bc.write_doc(text='x')\n")
        r = _run(tmpdir)
        assert r.findings == []

    def test_canonical_cclog_import(self, tmpdir):
        """Файл с import cclog / write_cclog — канонический путь, не флаг."""
        _write(tmpdir, "_ok_cclog.py",
               "import cclog\nwrite_cclog('DONE', 'test')\n")
        r = _run(tmpdir)
        assert r.findings == []

    def test_comment_only(self, tmpdir):
        """Строка с write_doc в комментарии НЕ освобождает от флага (паттерн grep-style).

        Реальный guard срабатывает на ЛЮБОЕ вхождение паттерна в строке, включая комментарии.
        Этот тест документирует текущее поведение: комментарий с .write_doc( → флаг.
        """
        _write(tmpdir, "_comment.py", "# do not call bc.write_doc()\n")
        r = _run(tmpdir)
        # Паттерн найден в комментарии → флаг (намеренно консервативно)
        assert len(r.findings) == 1

    def test_no_write_doc_in_file(self, tmpdir):
        """Файл _*.py без write_doc → нет флага."""
        _write(tmpdir, "_helper.py", "import os\nprint('hello')\n")
        r = _run(tmpdir)
        assert r.findings == []


class TestScratchpadWritersDirect:
    """Инвариант ФЛАГУЕТ прямые вызовы write_doc."""

    def test_method_call_text(self, tmpdir):
        """bc.write_doc(text=...) → флаг."""
        _write(tmpdir, "_writer.py", "bc.write_doc(text='x', name='cc_log')\n")
        r = _run(tmpdir)
        assert len(r.findings) == 1
        assert "scratchpad/_writer.py:1" in r.findings[0][0]

    def test_method_call_content(self, tmpdir):
        """bc.write_doc(content=...) — любая форма write_doc( → флаг."""
        _write(tmpdir, "_w2.py", "bridge.write_doc(name='pulse', content='ok')\n")
        r = _run(tmpdir)
        assert len(r.findings) == 1

    def test_call_action_double_quote(self, tmpdir):
        """bc._call("write_doc", ...) → флаг."""
        _write(tmpdir, "_w3.py", 'bc._call("write_doc", name="cc_log", text="x")\n')
        r = _run(tmpdir)
        assert len(r.findings) == 1

    def test_call_action_single_quote(self, tmpdir):
        """bc._call('write_doc', ...) → флаг."""
        _write(tmpdir, "_w4.py", "bc._call('write_doc', name='pulse', text='y')\n")
        r = _run(tmpdir)
        assert len(r.findings) == 1

    def test_multiple_lines_in_file(self, tmpdir):
        """Файл с несколькими вызовами write_doc → флаг на каждую строку."""
        _write(tmpdir, "_multi.py",
               "c.write_doc(text='a', name='cc_log')\n"
               "c.write_doc(text='b', name='pulse')\n")
        r = _run(tmpdir)
        assert len(r.findings) == 2
        assert "scratchpad/_multi.py:1" in r.findings[0][0]
        assert "scratchpad/_multi.py:2" in r.findings[1][0]

    def test_multiple_files(self, tmpdir):
        """Несколько _*.py с write_doc → флаг в каждом."""
        _write(tmpdir, "_a.py", "bc.write_doc(text='x')\n")
        _write(tmpdir, "_b.py", "# only import\nimport os\n")
        _write(tmpdir, "_c.py", "c.write_doc(text='y')\n")
        r = _run(tmpdir)
        files = {f[0].split(":")[0] for f in r.findings}
        assert "scratchpad/_a.py" in files
        assert "scratchpad/_c.py" in files
        assert "scratchpad/_b.py" not in files

    def test_finding_message_canonical_hint(self, tmpdir):
        """Сообщение о нарушении содержит подсказку о каноническом пути."""
        _write(tmpdir, "_x.py", "bc.write_doc(name='cc_log')\n")
        r = _run(tmpdir)
        assert len(r.findings) == 1
        _, reality = r.findings[0]
        assert "write_cclog" in reality or "cclog.py" in reality


class TestScratchpadWritersDegradation:
    """Деградация (недоступный каталог) → note, не флаг."""

    def test_nonexistent_dir(self):
        """Несуществующий каталог → note, 0 находок."""
        r = _run("/nonexistent/path/that/does/not/exist")
        assert r.findings == []
        assert len(r.notes) == 1

    def test_run_all_degraded_world(self, tmpdir):
        """run_all с пустым tmpdir и FakeWorld(bikes=None) → 0 находок в SCRATCHPAD_WRITERS."""
        w = FakeWorld(bikes=None, clients=None, queue_ip=None)
        all_runs = run_all(w)
        by_name = {r.name: r for r in all_runs}
        sw = by_name.get("SCRATCHPAD_WRITERS")
        assert sw is not None
        assert sw.findings == []


class TestScratchpadWritersIntegration:
    """Интеграция: инвариант зарегистрирован в CHECKS и вызывается через run_all."""

    def test_registered_in_checks(self):
        """SCRATCHPAD_WRITERS присутствует в реестре CHECKS."""
        from invariants_check import CHECKS
        names = [n for n, _ in CHECKS]
        assert "SCRATCHPAD_WRITERS" in names

    def test_run_all_includes_scratchpad(self, tmpdir):
        """run_all всегда включает SCRATCHPAD_WRITERS."""
        all_runs = run_all(_world())
        names = [r.name for r in all_runs]
        assert "SCRATCHPAD_WRITERS" in names

    def test_run_all_clean_temp(self, tmpdir):
        """run_all с пустым tmpdir → SCRATCHPAD_WRITERS = 0 находок."""
        all_runs = run_all(_world())
        by_name = {r.name: r for r in all_runs}
        assert by_name["SCRATCHPAD_WRITERS"].findings == []

    def test_run_all_dirty_temp(self, tmpdir):
        """run_all с _bad_writer.py в tmpdir → SCRATCHPAD_WRITERS ≥ 1 находки."""
        _write(tmpdir, "_bad.py", "bc.write_doc(name='cc_log')\n")
        all_runs = run_all(_world())
        by_name = {r.name: r for r in all_runs}
        assert len(by_name["SCRATCHPAD_WRITERS"].findings) >= 1
