"""
Тесты класса A разбора 2478: нарратив «замена масла была на N» ≠ правка одометра.
Голдены: (а) 15.07 «Замена масла была на 24500» при одометре 24997;
         (б) та же фраза доезжает до Лист1 через кнопку Пыма, не оседает в памяти.
"""
import os
import sys
import asyncio
import json

os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ.setdefault("NOTIFY_COUNT_FILE", "/tmp/_test_oilbk_notify_count")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import splinter as sp

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

results = []

def ok(cond, label):
    results.append(cond)
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}")
    return cond


# ---------------------------------------------------------------------------
# 1. detect_oil_backdated_km — распознаёт нарративы задним числом
# ---------------------------------------------------------------------------
print("=== detect_oil_backdated_km ===")

ok(sp.detect_oil_backdated_km("Замена масла была на 24500") == 24500,
   "голден (а): 'Замена масла была на 24500' → 24500")
ok(sp.detect_oil_backdated_km("масло было на 24500") == 24500,
   "'масло было на 24500' → 24500")
ok(sp.detect_oil_backdated_km("поменял масло на 24500") == 24500,
   "'поменял масло на 24500' → 24500")
ok(sp.detect_oil_backdated_km("заменил масло на 23000") == 23000,
   "'заменил масло на 23000' → 23000")
ok(sp.detect_oil_backdated_km("менял масло на 19000") == 19000,
   "'менял масло на 19000' → 19000")
ok(sp.detect_oil_backdated_km("เปลี่ยนน้ำมันแล้ว ที่ 15000") == 15000,
   "тайский: 'เปลี่ยนน้ำมันแล้ว ที่ 15000' → 15000")
ok(sp.detect_oil_backdated_km("пробег был 24500") is None,
   "нет масляных кв → None")
ok(sp.detect_oil_backdated_km("масло 24500") is None,
   "масло есть, но нет прошедшего глагола → None")
ok(sp.detect_oil_backdated_km("поменял масло на 500") is None,
   "число < 1000 → None")
ok(sp.detect_oil_backdated_km("поменял масло на 1234567") is None,
   "число > 999999 → None")
ok(sp.detect_oil_backdated_km("масло было на 24 500") == 24500,
   "число с пробелом '24 500' → 24500")


# ---------------------------------------------------------------------------
# 2. detect_mileage_correction — масло-нарративы ИСКЛЮЧЕНЫ
# ---------------------------------------------------------------------------
print("\n=== detect_mileage_correction — oil исключён ===")

ok(sp.detect_mileage_correction("Замена масла была на 24500") is None,
   "голден (а): 'Замена масла была на 24500' → correction=None (не правка одометра)")
ok(sp.detect_mileage_correction("масло было на 24500") is None,
   "'масло было на 24500' → correction=None")
ok(sp.detect_mileage_correction("поменял масло на 24500") is None,
   "'поменял масло на 24500' → correction=None")
ok(sp.detect_mileage_correction("не верно 24997, правильно 25100") is not None,
   "реальная правка одометра 'не верно 24997' → correction не None")
ok(sp.detect_mileage_correction("неверно 25000") is not None,
   "'неверно 25000' → correction не None")


# ---------------------------------------------------------------------------
# 3. handle_oil_backdated_service — интеграционные тесты (моки)
# ---------------------------------------------------------------------------
print("\n=== handle_oil_backdated_service ===")


class _FakeMsg:
    def __init__(self, text, trusted=True, chat_id=-100, topic_id=123):
        self.text = text
        self.chat_id = chat_id
        self.message_thread_id = topic_id
        self.from_user = type("U", (), {
            "id": 504608015 if trusted else 999,
            "username": "Pleummmm" if trusted else "x"
        })()


class _FakeBridge:
    def __init__(self, oil_last=None):
        self._oil_last = oil_last

    def find_bike(self, bike):
        return {"name": bike, "oil_last_km": self._oil_last}


class _FakeContext:
    bot = type("B", (), {"send_message": None})()


_sent_messages = []
_sent_markups = []


async def _fake_send(context, **kwargs):
    _sent_messages.append(kwargs.get("text", ""))
    _sent_markups.append(kwargs.get("reply_markup"))
    return type("M", (), {"message_id": 1})()


_orig_send = sp._send
_orig_bike_from_topic = sp.bike_from_topic
_orig_lm = sp.last_mileage_in_topic
_orig_remember = sp._remember_cycle_msg
_orig_mark_aw = sp.mark_awaiting


def _noop(*a, **kw):
    pass


sp._remember_cycle_msg = _noop
sp.mark_awaiting = _noop


def _run_bk(text, trusted=True, oil_last=None, cur_km=24997, bike="PCX160 AAA"):
    _sent_messages.clear()
    _sent_markups.clear()
    sp._send = _fake_send
    sp.bike_from_topic = lambda c, t: bike
    sp.last_mileage_in_topic = lambda c, t: (cur_km, "high") if cur_km else None
    msg = _FakeMsg(text, trusted=trusted)
    bridge = _FakeBridge(oil_last=oil_last)
    result = _loop.run_until_complete(
        sp.handle_oil_backdated_service(msg, _FakeContext(), bridge, msg.text)
    )
    sp._send = _orig_send
    sp.bike_from_topic = _orig_bike_from_topic
    sp.last_mileage_in_topic = _orig_lm
    return result, list(_sent_messages), list(_sent_markups)


# голден (а): km=24500, одометр=24997, oil_last=None → кнопка Пыму
r, msgs, mks = _run_bk("Замена масла была на 24500", cur_km=24997, oil_last=None)
ok(r is True, "голден (а): обработчик вернул True")
ok(len(msgs) == 1, "голден (а): отправлена ровно одна карточка")
ok("24500" in msgs[0], "голден (а): карточка содержит km=24500")
ok(mks[0] is not None, "голден (а): кнопка подтверждения присутствует")

# km > cur_odo → ошибка
r, msgs, mks = _run_bk("масло было на 24500", cur_km=24000, oil_last=None)
ok(r is True, "km > cur_odo: обработчик вернул True")
ok(len(msgs) == 1, "km > cur_odo: отправлено одно сообщение")
ok("24500" in msgs[0], "km > cur_odo: сообщение содержит km")
ok(mks[0] is None, "km > cur_odo: кнопки НЕТ (сообщение об ошибке)")

# km ≤ oil_last → ошибка
r, msgs, mks = _run_bk("масло было на 24500", cur_km=30000, oil_last=25000)
ok(r is True, "km ≤ oil_last: вернул True")
ok(len(msgs) == 1, "km ≤ oil_last: одно сообщение")
ok(mks[0] is None, "km ≤ oil_last: кнопки НЕТ (ошибка)")

# ненадёжный пользователь → False
r, msgs, mks = _run_bk("масло было на 24500", trusted=False)
ok(r is False, "ненадёжный пользователь → False (fail-safe, штатный флоу)")

# байк не известен → False
sp._send = _fake_send
sp.bike_from_topic = lambda c, t: ""
sp.last_mileage_in_topic = lambda c, t: (24997, "high")
msg = _FakeMsg("масло было на 24500")
r2 = _loop.run_until_complete(
    sp.handle_oil_backdated_service(msg, _FakeContext(), _FakeBridge(), msg.text)
)
sp._send = _orig_send
sp.bike_from_topic = _orig_bike_from_topic
sp.last_mileage_in_topic = _orig_lm
ok(r2 is False, "байк не определён → False (fail-safe)")

# обычный текст → False
r, msgs, mks = _run_bk("пробег сейчас 24997")
ok(r is False, "обычный текст (не нарратив) → False")

# восстанавливаем патчи
sp._remember_cycle_msg = _orig_remember
sp.mark_awaiting = _orig_mark_aw


# ---------------------------------------------------------------------------
# 4. E2b-гейт: oil_last_km → backdated=True в pending_service_confirm
# ---------------------------------------------------------------------------
print("\n=== E2b: oil_last_km → backdated ===")

from unittest.mock import MagicMock, AsyncMock
import claude_client as cc


def _make_client(force_mileage=None):
    bridge = MagicMock()
    bridge.find_bike.return_value = {"name": "PCX160 AAA", "oil_last_km": 23000}
    client = cc.ClaudeClient.__new__(cc.ClaudeClient)
    client.bridge = bridge
    client._force_bike = "PCX160 AAA"
    client._force_mileage = force_mileage
    client._force_mileage_conf = "high" if force_mileage else ""
    client.pending_service_confirm = []
    return client


# oil_last_km=24500 → backdated=True, km=24500
client = _make_client(force_mileage=24997)
res_json = client._execute_tool("set_service",
                                {"bike": "PCX160 AAA", "service_type": "oil", "oil_last_km": 24500})
res = json.loads(res_json)
ok(res.get("blocked") == "service_gate", "E2b с oil_last_km → blocked=service_gate")
item = client.pending_service_confirm[0] if client.pending_service_confirm else {}
ok(item.get("backdated") is True, "E2b: backdated=True при oil_last_km")
ok(item.get("km") == 24500, f"E2b: km=24500 (не force_mileage=24997), получили: {item.get('km')}")

# current_km=24997 → backdated=False
client2 = _make_client(force_mileage=None)
client2._execute_tool("set_service",
                      {"bike": "PCX160 AAA", "service_type": "oil", "current_km": 24997})
item2 = client2.pending_service_confirm[0] if client2.pending_service_confirm else {}
ok(not item2.get("backdated"), "E2b: backdated отсутствует/False при current_km")
ok(item2.get("km") == 24997, f"E2b: km=24997 при current_km, получили: {item2.get('km')}")


# ---------------------------------------------------------------------------
# 5. _write_oil_backdated: set_fleet_oil получает oil_km=N, service_upsert без current_km
# ---------------------------------------------------------------------------
print("\n=== _write_oil_backdated: одометр не трогается ===")

from unittest.mock import patch

bridge_m = MagicMock()
bridge_m.find_bike.return_value = {"name": "PCX160 6789", "plate": "6789"}
bridge_m.set_fleet_oil.return_value = {"ok": True, "bike_name": "PCX160 6789"}
bridge_m.service_upsert.return_value = {"ok": True}

context_m = MagicMock()

with patch.object(sp, "_send_retry", new=AsyncMock()), \
     patch.object(sp, "_send", new=AsyncMock()), \
     patch.object(sp, "_plate_from_name", return_value="6789"), \
     patch.object(sp, "_service_interval", return_value=1500), \
     patch.object(sp, "_oil_interval", return_value=1500):
    _loop.run_until_complete(
        sp._write_oil_backdated(context_m, bridge_m, -100, 123, "PCX160 6789", 24500)
    )

ok(bridge_m.set_fleet_oil.call_count == 1, "set_fleet_oil вызван ровно 1 раз")
call_kw = bridge_m.set_fleet_oil.call_args.kwargs if bridge_m.set_fleet_oil.call_args else {}
ok(call_kw.get("oil_km") == 24500, f"set_fleet_oil(oil_km=24500), получили: {call_kw}")

ok(bridge_m.service_upsert.call_count == 1, "service_upsert вызван ровно 1 раз")
su_kw = bridge_m.service_upsert.call_args.kwargs if bridge_m.service_upsert.call_args else {}
ok("current_km" not in su_kw, f"current_km НЕ в service_upsert (одометр не трогаем): {su_kw}")
ok(su_kw.get("last_service_km") == 24500, f"last_service_km=24500 в service_upsert: {su_kw}")


# ---------------------------------------------------------------------------
print(f"\nИТОГ: {'ВСЕ PASS' if all(results) else 'ЕСТЬ FAIL (%d/%d)' % (sum(results), len(results))}")
sys.exit(0 if all(results) else 1)
