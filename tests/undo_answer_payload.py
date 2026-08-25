# -*- coding: utf-8 -*-
"""ПОМОЩНИК ХАРНЕССА (не тест, гейт его не собирает — имя не `test_*`).

Проходит ПУТЬ ОТВЕТА ВЛАДЕЛЬЦА целиком и ничего не отправляет:

    расписка записи регистра  →  undo_last.position (читает ключ акта)
                              →  undo_last.act      (журнал акта темы)
                              →  undo_last.request  (ответ владельца → тела вызовов)
                              →  bridge_client.service_undo (транспорт ПОДМЕНЁН — тело
                                 перехватывается, сеть не трогается вовсе)

Печатает JSON: тело «да», тело без подтверждения и названные отказы. Тело потом скармливается
ЖИВОМУ коду двери в node (tests/guard_unlock_harness.js) — так проверяется, что ответ владельца
доходит до двери и она срабатывает.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("ORCH_TEST_MODE", "1")     # сетевой запрет bridge_client — вторая линия

import bridge_client  # noqa: E402
import undo_last  # noqa: E402


def body_of(client, call):
    """Тело POST, которое клиент отдал бы мосту (транспорт подменён, сокет не открывается)."""
    seen = {}

    def _capture(method, action, params=None, body=None, **kw):
        seen["method"] = method
        seen["action"] = action
        seen["body"] = dict(body or {})
        return {"ok": True, "captured": True}

    saved = client._durable_request
    client._durable_request = _capture
    try:
        client.service_undo(**call)
    finally:
        client._durable_request = saved
    return seen


def main():
    receipt = json.load(open(sys.argv[1], encoding="utf-8"))
    out_path = sys.argv[2]

    # Руки, как в splinter: расписка → позиция → журнал акта темы. Букву колонки приносят руки
    # (`fleet_cell.FIELD_COL`) — мост отдаёт номер, а человек читает букву.
    letter = {"oil": "I", "gear": "J", "abs": "K", "airfilter": "L"}
    pos, why = undo_last.position(receipt.get("kind") or "oil",
                                  letter.get(receipt.get("kind") or "oil", "I"),
                                  receipt,
                                  want_km=receipt.get("new_km") or receipt.get("new_oil"))
    entry = undo_last.act(tok=7, ts=1.0, chat=-100, topic=83,
                          bike=receipt.get("bike_name") or "", plate=receipt.get("number") or "",
                          by="@pym", odo=str(receipt.get("new_km") or ""),
                          positions=[pos] if pos else [], blind=0 if pos else 1)

    yes_calls, yes_refusals = undo_last.request(entry, by="@filipp", confirmed=True)
    no_calls, no_refusals = undo_last.request(entry, by="@filipp")

    client = bridge_client.BridgeClient(url="https://example.invalid/exec", token="ТЕСТ-ТОКЕН")
    payload = {
        "position_why": why,
        "position": pos,
        "yes_refusals": yes_refusals,
        "no_refusals": no_refusals,
        "yes": [body_of(client, c) for c in yes_calls],
        "no": [body_of(client, c) for c in no_calls],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(json.dumps({"ok": True, "calls": len(yes_calls)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
