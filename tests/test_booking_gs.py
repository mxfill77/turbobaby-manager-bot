"""O3-2a: докрутка Booking.js (Apps Script, зеркало = /root/turbobaby-bridge-gs/Booking.js).
Apps Script локально не исполнить КАК СЕРВИС — но Booking.js зовёт SpreadsheetApp только внутри
функций, поэтому реальный код гоняется node-харнессом tests/booking_gs_harness.js с мок-листом
(схема репо: node --check на синтаксис + исполнение/парс реального .js, ср. test_set_caps.py).
Покрытие харнесса: парс дат листа (дд.мм.гггг / 'дд.мм.гггг , Ч:мм' / ISO / Date-ячейка),
booking_conflict (пересечение / касание границ НЕ конфликт / другой байк / «Завершена» не блокирует /
открытая аренда блокирует), bad_dates, нормализация в формат листа, passthrough нераспознанных дат
(совместимость INTAKE), прежний duplicate, activateBooking с уточнением по date_start.
Плюс: bridge_client.activate_booking шлёт date_start только при наличии (обратная совместимость)."""
import json
import os
import re
import subprocess
import sys
from unittest import mock

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

BOOKING_JS = "/root/turbobaby-bridge-gs/Booking.js"
HARNESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "booking_gs_harness.js")

_harness_cache = {}


def run_harness():
    if "res" not in _harness_cache:
        proc = subprocess.run(["node", HARNESS], capture_output=True, text=True, timeout=60)
        _harness_cache["res"] = (proc.returncode, proc.stdout, proc.stderr)
    return _harness_cache["res"]


def test_booking_js_syntax():
    proc = subprocess.run(["node", "--check", BOOKING_JS], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_harness_all_green():
    code, out, err = run_harness()
    assert code == 0, f"харнесс красный: {err or out}"
    data = json.loads(out)
    failed = [c for c in data["cases"] if not c["pass"]]
    assert not failed, f"провалы: {failed}"
    assert data["total"] >= 38  # полный набор кейсов O3-2a на месте


def _case_names():
    _, out, _ = run_harness()
    return {c["name"] for c in json.loads(out)["cases"]}


def test_harness_covers_required_scenarios():
    """ТЗ O3-2a: конфликт / касание / разные байки / Завершена / bad_dates / нормализация / активация."""
    names = _case_names()
    required = {
        "create.conflict-overlap", "create.conflict-date-cells", "create.touch-ok",
        "create.other-bike-ok", "create.completed-not-blocking", "create.open-ended-conflict",
        "create.bad-dates-reversed", "create.bad-dates-equal", "create.normalize-iso",
        "create.unparseable-passthrough", "create.duplicate-exact",
        "activate.by-date", "activate.no-date-legacy", "activate.date-mismatch-not-found",
    }
    missing = required - names
    assert not missing, f"в харнессе нет кейсов: {missing}"


def test_booking_js_structure():
    """Структурные маркеры в реальном Booking.js: новые err-коды и точки врезки на месте."""
    src = open(BOOKING_JS, encoding="utf-8").read()
    for marker in (
        "booking_conflict", "bad_dates", "bookingParseDate_", "bookingFmtDate_",
        "bookingOverlap_", "bookingDateEq_",
    ):
        assert marker in src, f"нет маркера {marker}"
    # скан дубль/конфликт расширен до F (A..F), не прежний A..E
    assert re.search(r"getRange\(2, 1, lastRow - 1, BOOKING\.COL\.DATE_END\)", src), "скан не A..F"
    # даты в лист идут нормализованными
    assert "put(BOOKING.COL.DATE_START,  writeStart)" in src
    assert "put(BOOKING.COL.DATE_END,    writeEnd)" in src
    # активация читает E и фильтрует по p.date_start
    assert re.search(r"function activateBooking[\s\S]*?BOOKING\.COL\.DATE_START\).getValues", src)
    assert re.search(r"function activateBooking[\s\S]*?p\.date_start", src)


def test_bridge_client_activate_booking_optional_date():
    """activate_booking: без date_start POST-поля прежние (совместимость), с date_start — добавляется."""
    from bridge_client import BridgeClient

    c = BridgeClient(url="http://x", token="x", timeout=1)
    with mock.patch.object(c, "_post", return_value={"ok": True}) as post:
        c.activate_booking("4957", "Пётр")
    assert post.call_args == mock.call("activate_booking", bike="4957", name="Пётр")
    with mock.patch.object(c, "_post", return_value={"ok": True}) as post:
        c.activate_booking("4957", "Пётр", date_start="20.07.2026")
    assert post.call_args == mock.call(
        "activate_booking", bike="4957", name="Пётр", date_start="20.07.2026")
    print("OK: activate_booking — date_start опционален, без него поля прежние")


if __name__ == "__main__":
    test_booking_js_syntax()
    print("OK: node --check Booking.js")
    test_harness_all_green()
    print("OK: харнесс — реальный Booking.js, все кейсы зелёные")
    test_harness_covers_required_scenarios()
    print("OK: покрытие ТЗ (конфликт/касание/байки/Завершена/bad_dates/нормализация/активация)")
    test_booking_js_structure()
    print("OK: структурные маркеры Booking.js")
    test_bridge_client_activate_booking_optional_date()
    print("ВСЕ ТЕСТЫ booking_gs ПРОШЛИ")
