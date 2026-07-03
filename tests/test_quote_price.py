"""Обёртка BridgeClient.quote_price() — мок-тесты (Bridge не дёргаем, requests.get подменён).
Проверяет: ok → dict с ключами day_price/total/deposit/available/conflicts/season/text;
не-ok (bike_not_resolved) → None; таймаут → None; кривой JSON → None; неожиданный
Exception внутри _call → None (вызывающий код не падает). Плюс: правильные GET-параметры."""
import os, sys, json
from unittest import mock

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import requests
from bridge_client import BridgeClient

OK_PAYLOAD = {
    "ok": True, "action": "quote_price",
    "bike": "NMAX 155CC GREEN-B PHUKET 4957", "model": "YAMAHA NMAX 155",
    "days": 7, "day_price": 317, "total": 2217, "deposit": 3000,
    "available": True, "conflicts": 0,
    "season": {"label": "low", "global_discount": 0.25,
               "source": "Календарь бронирования H3/I3/J3 (через 'цены альт' B2/B9/B19)"},
    "text": "YAMAHA NMAX 155 | дней: 7, стоимость: 2217 (скидка за срок 7%, 317 в день), депозит: 3000 бат",
}


class FakeResp:
    def __init__(self, payload=None, raw=None):
        self._payload = payload
        self._raw = raw

    def raise_for_status(self):
        pass

    def json(self):
        if self._payload is not None:
            return self._payload
        # кривой JSON от Bridge (HTML-заглушка и т.п.)
        return json.loads(self._raw)


def client():
    return BridgeClient(url="http://x", token="x", timeout=1)


def test_ok_returns_dict_with_expected_keys():
    with mock.patch("bridge_client.requests.get", return_value=FakeResp(OK_PAYLOAD)) as g:
        res = client().quote_price("4957", "08.07.2026", "15.07.2026")
    assert isinstance(res, dict)
    for key in ("day_price", "total", "deposit", "available", "conflicts", "season", "text"):
        assert key in res, f"нет ключа {key}"
    assert res["day_price"] == 317 and res["total"] == 2217 and res["deposit"] == 3000
    assert res["available"] is True and res["conflicts"] == 0
    assert res["season"]["label"] == "low"
    # GET-параметры ушли правильные
    params = g.call_args.kwargs["params"]
    assert params["action"] == "quote_price" and params["bike"] == "4957"
    assert params["date_start"] == "08.07.2026" and params["date_end"] == "15.07.2026"
    print("OK: ok-ответ → dict со всеми ключами, параметры верные")


def test_not_ok_returns_none():
    payload = {"ok": False, "error": "bike_not_resolved",
               "message": 'Байк "PCX" не найден однозначно в "список мото"'}
    with mock.patch("bridge_client.requests.get", return_value=FakeResp(payload)):
        res = client().quote_price("PCX", "08.07.2026", "15.07.2026")
    assert res is None
    print("OK: bike_not_resolved → None")


def test_timeout_returns_none():
    with mock.patch("bridge_client.requests.get",
                    side_effect=requests.exceptions.Timeout("boom")):
        res = client().quote_price("4957", "08.07.2026", "15.07.2026")
    assert res is None
    print("OK: таймаут → None")


def test_bad_json_returns_none():
    with mock.patch("bridge_client.requests.get",
                    return_value=FakeResp(raw="<html>not json</html>")):
        res = client().quote_price("4957", "08.07.2026", "15.07.2026")
    assert res is None
    print("OK: кривой JSON → None")


def test_unexpected_exception_returns_none():
    with mock.patch.object(BridgeClient, "_call", side_effect=RuntimeError("сюрприз")):
        res = client().quote_price("4957", "08.07.2026", "15.07.2026")
    assert res is None
    print("OK: неожиданный Exception в _call → None (не роняем вызывающий код)")


if __name__ == "__main__":
    test_ok_returns_dict_with_expected_keys()
    test_not_ok_returns_none()
    test_timeout_returns_none()
    test_bad_json_returns_none()
    test_unexpected_exception_returns_none()
    print("ВСЕ ТЕСТЫ quote_price ПРОШЛИ")
