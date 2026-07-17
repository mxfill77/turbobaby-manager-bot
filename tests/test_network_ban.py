# -*- coding: utf-8 -*-
"""Страж класса 193 — сетевой запрет в ORCH_TEST_MODE=1 (рубеж 3).

Проверяет, что bridge_client._install_test_network_ban() патчит requests.Session.send:
  (1) попытка к нелокальному URL → RuntimeError ДО открытия сокета;
  (2) localhost всегда разрешён;
  (3) BRIDGE_ALLOW_NETWORK=1 снимает ban (обход транспорт-тестов);
  (4) BridgeClient с замоканным _post сеть не трогает;
  (5) BridgeClient с заменённым _session=FakeSession не дёргает requests.Session.send.
Сети нет — всё мокнуто или перехвачено до TCP."""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ORCH_TEST_MODE", "1")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

# import bridge_client ПЕРВЫМ — это устанавливает ban если ORCH_TEST_MODE=1
import bridge_client  # noqa: F401 (side-effect: installs ban)
import requests


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

# ── (1) ban активен для нелокального URL ──────────────────────────────────────
print("(1) ban ловит нелокальный URL:")
sess = requests.Session()
prep = requests.Request("GET", "https://script.google.com/macros/s/ABC/exec").prepare()
try:
    sess.send(prep, timeout=0.001)
    res.append(ok(False, "ban НЕ сработал — вызов к внешнему URL не заблокирован"))
except RuntimeError as e:
    res.append(ok("ТЕСТ ДЁРНУЛ СЕТЬ" in str(e), f"ban сработал: {str(e)[:70]}"))
except Exception as e:
    res.append(ok(False, f"ожидался RuntimeError, получили {type(e).__name__}: {e}"))

# ── (2) localhost разрешён ─────────────────────────────────────────────────────
print("(2) localhost разрешён:")
prep_local = requests.Request("GET", "http://127.0.0.1:19999/").prepare()
try:
    sess.send(prep_local, timeout=0.001)
    res.append(ok(True, "localhost пропущен баном"))
except RuntimeError as e:
    res.append(ok(False, f"localhost НЕ должен блокироваться баном: {e}"))
except Exception:
    # Ожидаем: ConnectionError/Timeout (порт закрыт) — не RuntimeError, значит бан не сработал
    res.append(ok(True, "localhost пропущен баном (соединение отклонено портом — не RuntimeError)"))

# ── (3) BRIDGE_ALLOW_NETWORK=1 снимает ban ────────────────────────────────────
print("(3) BRIDGE_ALLOW_NETWORK=1 снимает ban:")
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
try:
    sess.send(prep, timeout=0.0001)
    res.append(ok(True, "BRIDGE_ALLOW_NETWORK=1: не RuntimeError"))
except RuntimeError as e:
    res.append(ok(False, f"BRIDGE_ALLOW_NETWORK=1 должен снимать ban: {e}"))
except Exception:
    # ConnectionError/Timeout — сеть недоступна, но НЕ RuntimeError ban
    res.append(ok(True, "BRIDGE_ALLOW_NETWORK=1: RuntimeError не поднят (сеть недоступна — ok)"))
finally:
    os.environ.pop("BRIDGE_ALLOW_NETWORK", None)

# ── (4) BridgeClient с мок-_post не дёргает Session.send ─────────────────────
print("(4) BridgeClient._post=мок не касается Session.send:")
from bridge_client import BridgeClient

c = BridgeClient(url="http://x", token="x", timeout=1)
mock_calls = []
c._post = lambda action, **kw: (mock_calls.append(action), {"ok": True, "id": 1})[1]
try:
    c.enqueue_task("Filipp-328", "read-only: проверь wa_queue.db на VPS")
    res.append(ok(len(mock_calls) == 1, "мок _post вызван, Session.send не трогался"))
except RuntimeError as e:
    res.append(ok(False, f"мок _post не должен дёргать ban: {e}"))

# ── (5) BridgeClient с _session=FakeSession не дёргает requests.Session.send ──
print("(5) _session=FakeSession не дёргает requests.Session.send:")


class FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def json(self):
        return {"ok": True, "action": "ping", "status": "alive"}


class FakeSess:
    def __init__(self):
        self.calls = []

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        return FakeResponse()

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        return FakeResponse()

    def close(self):
        pass


c2 = BridgeClient(url="http://x", token="x", timeout=1)
fake_s = FakeSess()
c2._session = fake_s
try:
    c2.ping()
    res.append(ok(len(fake_s.calls) >= 1, "FakeSess.get вызван, requests.Session.send не трогался"))
except RuntimeError as e:
    res.append(ok(False, f"FakeSess не должна дёргать ban: {e}"))

# ── итог ───────────────────────────────────────────────────────────────────────
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
