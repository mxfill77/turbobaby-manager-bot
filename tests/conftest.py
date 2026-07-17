# -*- coding: utf-8 -*-
"""Pytest conftest — общий стражник тест-сьюта (класс 193, 17.07.2026).

Для script-based тестов (gate.py запускает python3 tests/test_*.py напрямую)
сетевой бан уже установлен в bridge_client._install_test_network_ban() при импорте
с ORCH_TEST_MODE=1. conftest.py дублирует его как autouse-фикстуру для случаев,
когда тесты прогоняются через pytest вручную без ORCH_TEST_MODE=1 в окружении.
"""
import os

import pytest

os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

_LOCALHOST_PREFIXES = ("http://127.", "https://127.", "http://[::1]",
                       "https://[::1]", "http://localhost", "https://localhost")


@pytest.fixture(autouse=True)
def ban_external_network(monkeypatch):
    """Блокирует requests к нелокальным URL в любом pytest-прогоне.
    BRIDGE_ALLOW_NETWORK=1 — обход для транспорт-тестов."""
    try:
        import requests
        _orig = requests.Session.send

        def _banned(self_sess, request, **kw):
            if os.getenv("BRIDGE_ALLOW_NETWORK") == "1":
                return _orig(self_sess, request, **kw)
            url = str(getattr(request, "url", "") or "")
            if not any(url.startswith(p) for p in _LOCALHOST_PREFIXES):
                raise RuntimeError(
                    f"🚫 ТЕСТ ДЁРНУЛ СЕТЬ [{url[:80]}] "
                    "(conftest ban) — замокай _post/_session или поставь BRIDGE_ALLOW_NETWORK=1"
                )
            return _orig(self_sess, request, **kw)

        monkeypatch.setattr(requests.Session, "send", _banned)
    except ImportError:
        pass
