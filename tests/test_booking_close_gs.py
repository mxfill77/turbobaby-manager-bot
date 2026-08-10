"""O3-3b фаза I: closeBooking в Booking.js (зеркало прода = bridge_prod/Booking.js).
Тот же node-vm харнесс tests/booking_gs_harness.js (реальный Booking.js + мок-SpreadsheetApp),
что и O3-2a. Покрытие: штатное закрытие (A=Завершена, N=km_end, K=paid_total), not_active
(Бронь — сначала выдача), not_found, ambiguous (две "В аренде" без date_start) + уточнение
по date_start, odometer_back (km_end < Q; == Q ок), bad_km_end, K опционален (без paid_total
не тронут), F и формульные G/I/J/W целы. Фикс дыры fail-closed (инцидент row705): km_end
ОБЯЗАТЕЛЕН (нет → km_required), Q пуст/нечисловой → odo_unverifiable «сверь и закрой руками»
(молчаливого пропуска гейта одометра больше нет; force-флага нет намеренно).
Фикс №2 (маятник row705→1268): Q в живом листе — СТРОКА «<число> Km, <дата>» → bookingParseOdo_
извлекает число (моки Q — живым форматом листа); не извлекли → odo_unverifiable как раньше.
Плюс: роутинг close_booking в Bridge.js под REDZONE_LOCK 4.2; bridge_client.close_booking
шлёт опциональные поля только при наличии."""
import json
import os
import re
import subprocess
import sys
from unittest import mock

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

# .js берём из ЗЕРКАЛА ПРОДА `bridge_prod/` (задеплоенная версия, паспорт MIRROR.json), а не из
# рабочей папки выкладки: она обезврежена 10.08.2026 и отстаёт от прода.
GS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bridge_prod")
BOOKING_JS = os.path.join(GS_DIR, "Booking.js")
BRIDGE_JS = os.path.join(GS_DIR, "Bridge.js")
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "booking_gs_harness.js")

_harness_cache = {}


def run_harness():
    if "res" not in _harness_cache:
        proc = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=60)
        _harness_cache["res"] = (proc.returncode, proc.stdout, proc.stderr)
    return _harness_cache["res"]


def test_close_harness_all_green():
    code, out, err = run_harness()
    assert code == 0, f"харнесс красный: {err or out}"
    data = json.loads(out)
    failed = [c for c in data["cases"] if not c["pass"]]
    assert not failed, f"провалы: {failed}"


def test_close_harness_covers_required_scenarios():
    """ТЗ O3-3b: закрытие / not_active / not_found / ambiguous / odometer_back / K-опц. / формулы целы."""
    _, out, _ = run_harness()
    names = {c["name"] for c in json.loads(out)["cases"]}
    required = {
        "close.ok", "close.km-written", "close.paid-written", "close.f-intact",
        "close.formulas-intact", "close.k-optional", "close.not-active", "close.not-found",
        "close.ambiguous", "close.by-date", "close.odometer-back", "close.odometer-equal-ok",
        "close.bad-km-end",
        # фикс row705 fail-closed: km_end обязателен; Q пуст/нечисловой → err, не пропуск
        "close.km-required", "close.odo-empty-unverifiable", "close.odo-nonnumeric-unverifiable",
        # фикс №2 (маятник row705→1268): Q живёт строкой «<число> Km, <дата>» — парсер + гейты
        "parseOdo.live-format", "parseOdo.empty-null", "parseOdo.garbage-null",
        "parseOdo.bare-date-null", "parseOdo.split-number-null",
        "close.odo-live-format-back", "close.odo-live-format-ok",
        "close.odo-date-only-unverifiable",
    }
    missing = required - names
    assert not missing, f"в харнессе нет кейсов: {missing}"


def test_close_booking_js_structure():
    """Структурные маркеры closeBooking в реальном Booking.js."""
    src = open(BOOKING_JS, encoding="utf-8").read()
    for marker in (
        "function closeBooking", "not_active", "not_found", "ambiguous",
        "odometer_back", "bad_km_end", "BOOKING.COL.ODO",
        "km_required", "odo_unverifiable",  # фикс row705 fail-closed
        "function bookingParseOdo_",  # фикс №2: Q «<число> Km, <дата>» → число
    ):
        assert marker in src, f"нет маркера {marker}"
    # запись строго точечная: A/N/K; формульные не копируются, F не пишется
    close_body = src.split("function closeBooking")[1].split("\nfunction ")[0]
    assert "setValue('Завершена')" in close_body
    assert "BOOKING.COL.KM" in close_body and "BOOKING.COL.INITIAL_PAY" in close_body
    assert "DATE_END" not in close_body, "closeBooking не должен трогать F (дату возврата)"
    assert "copyTo" not in close_body, "closeBooking не должен копировать формулы"
    # фикс row705: обхода гейта одометра быть не должно — никакого force-флага в body
    assert not re.search(r"[pb]\w*\.force|\bforce\s*[:=]", close_body), "force-флаг запрещён (fail-closed)"


def test_bridge_js_routing():
    """close_booking в Bridge.js: под REDZONE_LOCK 4.2 + case-роутинг + список actions."""
    src = open(BRIDGE_JS, encoding="utf-8").read()
    lock = re.search(r"var REDZONE_LOCK = \{[\s\S]*?\};", src)
    assert lock and "close_booking: 1" in lock.group(0), "close_booking не под REDZONE_LOCK 4.2"
    assert re.search(r"case 'close_booking':\s*\n\s*return jsonResponse\(Object\.assign\(\{ action \}, closeBooking\(body\)\)\)", src)
    assert "'close_booking'," in src  # список actions в ответе unknown_action


def test_bridge_client_close_booking_optional_fields():
    """close_booking: опциональные поля шлются только при наличии; в _REDZONE_ACTIONS."""
    from bridge_client import BridgeClient

    assert "close_booking" in BridgeClient._REDZONE_ACTIONS
    c = BridgeClient(url="http://x", token="x", timeout=1)
    with mock.patch.object(c, "_post", return_value={"ok": True}) as post:
        c.close_booking("4957", "Пётр")
    assert post.call_args == mock.call("close_booking", bike="4957", name="Пётр")
    with mock.patch.object(c, "_post", return_value={"ok": True}) as post:
        c.close_booking("4957", "Пётр", date_start="20.07.2026", km_end=12500, paid_total=9000)
    assert post.call_args == mock.call(
        "close_booking", bike="4957", name="Пётр",
        date_start="20.07.2026", km_end=12500, paid_total=9000)


if __name__ == "__main__":
    test_close_harness_all_green()
    print("OK: харнесс — реальный Booking.js, close-кейсы зелёные")
    test_close_harness_covers_required_scenarios()
    print("OK: покрытие ТЗ (закрытие/not_active/not_found/ambiguous/odometer_back/K-опц./формулы)")
    test_close_booking_js_structure()
    print("OK: структурные маркеры closeBooking")
    test_bridge_js_routing()
    print("OK: роутинг Bridge.js под REDZONE_LOCK 4.2")
    test_bridge_client_close_booking_optional_fields()
    print("ВСЕ ТЕСТЫ booking_close_gs ПРОШЛИ")
