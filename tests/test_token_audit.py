"""tests/test_token_audit.py — тесты tools/token_audit.py на фиктивных токенах.

Боевые токены (RED_TOKENS / _RED_PY_TOKENS) НЕ встречаются в этом файле:
  - _load_tokens() патчится через unittest.mock → возвращает _FAKE_TOKENS
  - _scan_file() и _mask() тестируются напрямую с _FAKE_TOKENS

Цель: проверить механику (маскирование, сканирование, зоны), не боевой список.
PRETOOL_NOPUSH=1 обеспечивает gate.py (нет пушей в личку из тестов).
"""
import os
import sys
import tempfile
import unittest.mock

os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("PRETOOL_NOPUSH", "1")

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

import importlib.util as _ilu

_TOOL_PATH = os.path.join(PROJECT, "tools", "token_audit.py")
_spec = _ilu.spec_from_file_location("token_audit", _TOOL_PATH)
ta = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(ta)

# Фиктивные токены для тестов (не совпадают с реальными RED_TOKENS/_RED_PY_TOKENS)
_FAKE_TOKENS = ("MOCK_REDTOKEN_ALPHA", "MOCK_BETA_TOKEN_XYZ")


# ─── _mask() ────────────────────────────────────────────────────────────────────

def test_mask_first4_chars():
    """Первые 4 символа сохраняются, остальное — звёздочки."""
    result = ta._mask("ABCDEFGHIJ")
    assert result[:4] == "ABCD"
    assert all(c == "*" for c in result[4:])


def test_mask_preserves_length():
    """Длина маски == длина оригинального токена."""
    tok = "XYZABCDE"
    assert len(ta._mask(tok)) == len(tok)


def test_mask_all_stars_after_4():
    """Позиции [4:] целиком из звёздочек."""
    tok = "LONGTOKEN123"
    m = ta._mask(tok)
    assert set(m[4:]) == {"*"}


def test_mask_short_token():
    """Короткий токен (< 6 символов) → хотя бы 1 символ виден, остальное звёздочки."""
    tok = "ABC"
    m = ta._mask(tok)
    assert len(m) == len(tok)
    assert "*" in m
    assert m[0] == "A"


def test_mask_fake_tokens_safe():
    """Маска фиктивных токенов начинается с 'MOCK' — первые 4 символа."""
    m = ta._mask(_FAKE_TOKENS[0])
    assert m.startswith("MOCK")
    assert "*" in m


# ─── _scan_file() ───────────────────────────────────────────────────────────────

def test_scan_file_finds_single_hit():
    """Строка с фиктивным токеном → (lineno, masked, preview) в результате."""
    content = "normal line\nline with MOCK_REDTOKEN_ALPHA here\nend\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(content)
        path = f.name
    try:
        hits = ta._scan_file(path, _FAKE_TOKENS)
        assert len(hits) == 1
        lineno, masked, preview = hits[0]
        assert lineno == 2
        assert masked.startswith("MOCK")
        assert "*" in masked
        assert "MOCK_REDTOKEN_ALPHA" not in masked  # маска работает
    finally:
        os.unlink(path)


def test_scan_file_no_hit():
    """Файл без токенов → пустой список."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("safe line 1\nsafe line 2\n")
        path = f.name
    try:
        hits = ta._scan_file(path, _FAKE_TOKENS)
        assert hits == []
    finally:
        os.unlink(path)


def test_scan_file_two_different_lines():
    """По одному хиту на каждую строку (два разных токена на разных строках)."""
    content = "MOCK_REDTOKEN_ALPHA here\nnormal\nMOCK_BETA_TOKEN_XYZ there\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(content)
        path = f.name
    try:
        hits = ta._scan_file(path, _FAKE_TOKENS)
        assert len(hits) == 2
        assert hits[0][0] == 1
        assert hits[1][0] == 3
    finally:
        os.unlink(path)


def test_scan_file_one_hit_per_line():
    """Строка с двумя токенами сразу → только один хит (первый совпавший)."""
    content = "MOCK_REDTOKEN_ALPHA and MOCK_BETA_TOKEN_XYZ on same line\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(content)
        path = f.name
    try:
        hits = ta._scan_file(path, _FAKE_TOKENS)
        assert len(hits) == 1  # только первый совпавший токен на строке
    finally:
        os.unlink(path)


def test_scan_file_missing_path():
    """Несуществующий путь → пустой список (без исключений)."""
    hits = ta._scan_file("/nonexistent/path/file.py", _FAKE_TOKENS)
    assert hits == []


# ─── _zone_files() ───────────────────────────────────────────────────────────────

def test_zone_files_configs_exist():
    """Зона configs возвращает реально существующие файлы."""
    files = ta._zone_files("configs")
    for f in files:
        assert os.path.isfile(f), f"{f} не существует"


def test_zone_files_preambles_exist():
    """Зона preambles включает orchestrator_daemon.py (файл есть)."""
    files = ta._zone_files("preambles")
    names = [os.path.basename(f) for f in files]
    assert "orchestrator_daemon.py" in names


def test_zone_files_tests_nonempty():
    """Зона tests возвращает хотя бы один test_*.py файл."""
    files = ta._zone_files("tests")
    assert any(os.path.basename(f).startswith("test_") for f in files)


def test_zone_files_custom_project():
    """С кастомным project-каталогом зона configs смотрит в него же."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # создаём config-файл с нужным именем
        cfg = os.path.join(tmpdir, "headless_settings.json")
        with open(cfg, "w") as fh:
            fh.write("{}\n")
        files = ta._zone_files("configs", project=tmpdir)
        assert cfg in files


def test_zone_files_scratchpad_pattern():
    """Зона scratchpad возвращает только _*.py файлы (не другие)."""
    files = ta._zone_files("scratchpad")
    for f in files:
        base = os.path.basename(f)
        assert base.startswith("_") and base.endswith(".py"), f"некорректный scratchpad: {base}"


# ─── run_audit() с патченным _load_tokens ────────────────────────────────────────

def test_run_audit_report_has_header():
    """run_audit() возвращает отчёт с заголовком «АУДИТ ТОКЕНОВ»."""
    with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
        report, hits, files = ta.run_audit("configs")
    assert "АУДИТ ТОКЕНОВ" in report
    assert isinstance(hits, int)
    assert isinstance(files, int)


def test_run_audit_clean_tempdir():
    """Пустая configs-зона без фиктивных токенов → 0 хитов, ✅ в отчёте."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = os.path.join(tmpdir, "headless_settings.json")
        with open(cfg, "w") as fh:
            fh.write('{"version": 1}\n')
        with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
            report, hits, files = ta.run_audit("configs", project=tmpdir)
    assert hits == 0
    assert "✅" in report


def test_run_audit_finds_hit():
    """Файл с фиктивным токеном → хит в отчёте, файл:строка присутствует."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = os.path.join(tmpdir, "headless_settings.json")
        with open(cfg, "w") as fh:
            fh.write(f"MOCK_REDTOKEN_ALPHA appears here\n")
        with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
            report, hits, files = ta.run_audit("configs", project=tmpdir)
    assert hits >= 1
    assert "headless_settings.json" in report
    assert "MOCK_REDTOKEN_ALPHA" not in report  # маска сработала
    assert "MOCK" in report  # первые 4 символа видны


def test_run_audit_masked_output():
    """В отчёте токены маскированы: открытой строки токена нет, маска есть."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg = os.path.join(tmpdir, "headless_settings.json")
        with open(cfg, "w") as fh:
            fh.write("MOCK_BETA_TOKEN_XYZ is here\n")
        with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
            report, hits, _files = ta.run_audit("configs", project=tmpdir)
    assert hits >= 1
    assert "MOCK_BETA_TOKEN_XYZ" not in report  # открытый токен отсутствует
    assert "MOCK" in report                      # первые 4 символа присутствуют
    assert "*" in report                          # звёздочки присутствуют


def test_run_audit_empty_token_list():
    """_load_tokens вернул [] → сообщение «нет токенов», 0 хитов."""
    with unittest.mock.patch.object(ta, "_load_tokens", return_value=[]):
        report, hits, _files = ta.run_audit("configs")
    assert hits == 0
    assert "нет токенов" in report


# ─── main() ──────────────────────────────────────────────────────────────────────

def test_main_returns_zero():
    """main() с патченным _load_tokens завершается с кодом 0."""
    with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
        rc = ta.main(["--zone", "configs"])
    assert rc == 0


def test_main_all_zone_ok():
    """main() с зоной all не падает (read-only сканирование реального проекта)."""
    with unittest.mock.patch.object(ta, "_load_tokens", return_value=list(_FAKE_TOKENS)):
        rc = ta.main(["--zone", "all"])
    assert rc == 0


if __name__ == "__main__":
    import traceback
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = fail = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
            ok += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            fail += 1
    print(f"\n{'ALL PASS ✅' if fail == 0 else f'FAIL {fail}'} / total {ok + fail}")
    raise SystemExit(0 if fail == 0 else 1)
