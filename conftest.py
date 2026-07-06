"""§12 корень 2 (06.07.2026): изоляция тест-шума от лички Splinter — pytest-путь.

Зачем: тесты набора tests/ гоняются двумя способами — (1) как отдельные скрипты
(`venv/bin/python3 tests/test_*.py`, так их зовёт gate.py) и (2) через pytest. Для пути (1)
флаг PRETOOL_NOPUSH поднимает сам notify на импорте (см. notify._is_test_entrypoint). Для пути
(2) этот conftest поднимает флаг на СТАРТЕ pytest — ДО импорта тест-модулей, чтобы ни один тест
не мог послать карточку/пуш Филиппу в личку. Мок-счётчик NOTIFY_COUNT_FILE (где выставлен) всё
равно первичен — сеть в тестах не дёргаем никогда.

Модульный setdefault срабатывает при загрузке conftest (до коллекции) — самый ранний момент;
autouse-фикстура session-scope дублирует его как явная страховка внутри сессии pytest."""
import os

# самый ранний момент: до импорта тест-модулей и до любого notify()
os.environ.setdefault("PRETOOL_NOPUSH", "1")

try:
    import pytest

    @pytest.fixture(scope="session", autouse=True)
    def _mute_pushes_in_tests():
        os.environ.setdefault("PRETOOL_NOPUSH", "1")
        yield
except Exception:
    # pytest не установлен / conftest подхвачен вне pytest — модульного setdefault выше достаточно
    pass
