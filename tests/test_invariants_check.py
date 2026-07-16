"""Тесты инвариантов данных v1 (invariants_check.py) — по образцу 08.07.2026.

ЖИВОЙ ФОРМАТ МОКОВ (урок инцидента row705→1268, 08.07.2026):
  - oil_last_km / gear_last_km: число (parseNumber; 0 = пусто/нечисловое)
  - date_end: "2026-07-14 14:00" (yyyy-MM-dd HH:mm Bangkok TZ, formatDate Apps Script)
  - deposit_raw: сырая строка из col S — "7000" | "passport" | "" | "7000 passport"
  - bike name: "HONDA CLICK 125 5580" (точное имя из Лист1 Байки col C)
  - queue updated: ISO строка "2026-07-15T08:30:00+00:00" или "...Z"

PRETOOL_NOPUSH=1 обеспечивает gate.py — пуши в личку из тестов исключены (утечка 01–05.07.2026).
"""
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import invariants_check as ic
from invariants_check import (
    FakeWorld, CheckRun, run_all, format_report,
    check_fleet_oil_gear, check_crm_overdue, check_crm_no_booking_id,
    check_crm_deposit, check_fleet_click_125, check_queue_long_ip,
    check_oil_vs_current_odo, check_bot_data_vs_sheet,
    OIL_PHOTO_DELTA, OIL_FRESH_SECS, BOT_DATA_OIL_DELTA,
    CHECKS,
)
from datetime import timezone

# ─── Вспомогательные константы ─────────────────────────────────────────────────────────────
_NOW = datetime.datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
# Метка «старая запись» (30ч до NOW = 2026-07-14T06:00) — релевантна для OIL_VS_CURRENT_ODO
_OLD_TS = "2026-07-14T06:00:00+00:00"
# Метка «свежая запись» (1ч до NOW = 2026-07-15T11:00 < OIL_FRESH_SECS=7200с)
_FRESH_TS = "2026-07-15T11:00:00+00:00"

# Живой формат fleet bike (ReadFleet.js parseNumber → 0 если пусто)
_BIKE_RENTED_OK = {
    "name": "PCX160 4234", "status": "В аренде",
    "oil_last_km": 35200, "gear_last_km": 34000, "mileage": 25000,
}
_BIKE_HOME = {
    "name": "NMAX155 5001", "status": "ДОМА",
    "oil_last_km": 0, "gear_last_km": 0, "mileage": 12000,
}
# CLICK 125 — дома в чистом мире (правило: не сдаём)
_BIKE_CLICK_HOME = {
    "name": "HONDA CLICK 125 5580", "status": "ДОМА",
    "oil_last_km": 10000, "gear_last_km": 9500, "mileage": 8000,
}

# Живой формат clients (ReadClients.js formatDate → "yyyy-MM-dd HH:mm" Bangkok TZ)
# date_end: NOW=2026-07-15 12:00; свежий срок — ещё не истёк
_CLIENT_OK = {
    "row": 5, "status": "В аренде", "bike": "PCX160 4234", "name": "John Smith",
    "date_end": "2026-07-20 14:00",
    "booking_id": "abc-123-uuid",
    "deposit_raw": "7000",
}
_CLIENT_BRON_OK = {
    "row": 6, "status": "Бронь", "bike": "NMAX155 5001", "name": "Jane Doe",
    "date_end": "2026-07-25 10:00",
    "booking_id": "def-456-uuid",
    "deposit_raw": "passport",
}

# Живой формат queue task (test_orphan_timeout.py pattern)
_TASK_FRESH = {
    "id": 1, "from": "Filipp-328", "task_text": "тест",
    "status": "in_progress",
    "updated": (_NOW - datetime.timedelta(seconds=100)).isoformat(),
}
# Bot Data service records — здоровое состояние:
# current_km=36000 (≠ oil_last_km 35200 → нет флага OIL_VS_CURRENT_ODO)
# last_service_km=35200 (= col I → diff=0 ≤ BOT_DATA_OIL_DELTA → нет флага BOT_DATA_VS_SHEET)
_SVC_OIL_OK = {
    "updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "oil",
    "current_km": 36000,       # текущий пробег; diff с col I (35200) = 800 > OIL_PHOTO_DELTA(100)
    "last_service_km": 35200,  # = col I → расхождение 0 ≤ BOT_DATA_OIL_DELTA(200)
    "interval_km": 3000, "next_km": 38200, "status": "ok",
}
_SVC_GEAR_OK = {
    "updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "gear",
    "current_km": 36000,
    "last_service_km": 34000,  # = col J (gear_last_km)
    "interval_km": 10000, "next_km": 44000, "status": "ok",
}


def _make_world(bikes=None, clients=None, queue=None, tt=600, ttd=2700, services=None):
    """Собрать FakeWorld с дефолтами чистого мира.
    services=None (дефолт) → Bridge down для ТО-трекера (note, без флагов).
    services=[] → Bot Data пуст (нет записей для сравнения).
    services=[...] → Bot Data с записями.
    """
    if bikes is None:
        bikes = [dict(_BIKE_RENTED_OK), dict(_BIKE_HOME), dict(_BIKE_CLICK_HOME)]
    if clients is None:
        clients = [dict(_CLIENT_OK), dict(_CLIENT_BRON_OK)]
    if queue is None:
        queue = [dict(_TASK_FRESH)]
    return FakeWorld(bikes=bikes, clients=clients, queue_ip=queue,
                     task_timeout=tt, task_timeout_dev=ttd, now=_NOW, services=services)


def _run(check_fn, world):
    """Прогнать одну проверку. → CheckRun."""
    r = CheckRun(check_fn.__name__)
    check_fn(world, r)
    return r


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 1: FLEET_OIL_GEAR
# ════════════════════════════════════════════════════════════════════════════════
def test_oil_gear_clean():
    """Чистый мир: байк в аренде с ненулевым oil/gear → 0 нарушений."""
    r = _run(check_fleet_oil_gear, _make_world())
    assert len(r.findings) == 0, f"ожидали 0, поймали: {r.findings}"


def test_oil_empty_rented():
    """oil_last_km=0 у «В аренде» → флаг (пусто = 0 из parseNumber)."""
    bikes = [dict(_BIKE_RENTED_OK)]
    bikes[0]["oil_last_km"] = 0     # parseNumber вернул 0 = пусто/нечисловое
    r = _run(check_fleet_oil_gear, _make_world(bikes=bikes))
    assert len(r.findings) >= 1
    assert "oil_last_km = 0" in r.findings[0][0]


def test_gear_empty_rented():
    """gear_last_km=0 у «В аренде» → флаг."""
    bikes = [dict(_BIKE_RENTED_OK)]
    bikes[0]["gear_last_km"] = 0
    r = _run(check_fleet_oil_gear, _make_world(bikes=bikes))
    assert any("gear_last_km = 0" in f[0] for f in r.findings)


def test_oil_hard_max():
    """oil_last_km > HARD_MAX_KM → флаг нереального пробега."""
    bikes = [dict(_BIKE_RENTED_OK)]
    bikes[0]["oil_last_km"] = 999_999   # нереально для тайского проката
    r = _run(check_fleet_oil_gear, _make_world(bikes=bikes))
    assert any("нереальный" in f[1] for f in r.findings), r.findings


def test_oil_at_hard_max_boundary():
    """oil_last_km == HARD_MAX_KM (300_000) → не флаг (граница не включена)."""
    bikes = [dict(_BIKE_RENTED_OK)]
    bikes[0]["oil_last_km"] = ic.HARD_MAX_KM   # ровно на границе
    r = _run(check_fleet_oil_gear, _make_world(bikes=bikes))
    assert not any("нереальный" in f[1] for f in r.findings), r.findings


def test_oil_home_not_checked():
    """Байк ДОМА с oil=0 → не флаг (не В аренде)."""
    # В _BIKE_HOME oil=0 уже есть
    r = _run(check_fleet_oil_gear, _make_world())
    assert len(r.findings) == 0, r.findings


def test_oil_bridge_down():
    """fleet() вернул None (Bridge недоступен) → note, 0 нарушений (деградация, не ложный флаг)."""
    w = FakeWorld(bikes=None, clients=[], queue_ip=[], now=_NOW)
    r = _run(check_fleet_oil_gear, w)
    assert len(r.findings) == 0
    assert r.notes


def test_oil_no_rented_bikes():
    """Нет байков «В аренде» (нулевая выборка) → note, 0 нарушений."""
    bikes = [dict(_BIKE_HOME), dict(_BIKE_CLICK_HOME)]
    r = _run(check_fleet_oil_gear, _make_world(bikes=bikes))
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 2: CRM_OVERDUE
# ════════════════════════════════════════════════════════════════════════════════
def test_overdue_clean():
    """date_end в будущем → 0 нарушений."""
    r = _run(check_crm_overdue, _make_world())
    assert len(r.findings) == 0, r.findings


def test_overdue_5_days():
    """date_end 5 дней назад → флаг просрочки.
    Живой формат: 'yyyy-MM-dd HH:mm' (Bangkok TZ, Apps Script formatDate).
    NOW=2026-07-15 12:00; date_end=2026-07-10 14:00 → ≈4.9 дней просрочки."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["date_end"] = "2026-07-10 14:00"    # живой формат Bangkok TZ
    r = _run(check_crm_overdue, _make_world(clients=clients))
    assert len(r.findings) >= 1, r.findings
    assert "просрочка" in r.findings[0][1]


def test_overdue_1_day_not_flagged():
    """date_end 1 день назад (< 2 дней порог) → НЕ флаг.
    date_end=2026-07-14 14:00 → ≈0.9 дней."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["date_end"] = "2026-07-14 14:00"
    r = _run(check_crm_overdue, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_overdue_exactly_2_days_boundary():
    """date_end ровно 2 дня назад — граница; по условию >2 дней → НЕ флаг.
    date_end=2026-07-13 12:00 → ровно 48ч → not > OVERDUE_DAYS*86400."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["date_end"] = "2026-07-13 12:00"
    r = _run(check_crm_overdue, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_overdue_no_date_end():
    """date_end пустая/None → пропуск (не флаг; не все статусы имеют дату)."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["date_end"] = None
    r = _run(check_crm_overdue, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_overdue_non_active_status_not_flagged():
    """«Завершена» с просроченной датой → НЕ флаг (проверяем только «В аренде»)."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["status"] = "Завершена"
    clients[0]["date_end"] = "2026-07-10 14:00"
    r = _run(check_crm_overdue, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_overdue_bridge_down():
    """clients() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[], clients=None, queue_ip=[], now=_NOW)
    r = _run(check_crm_overdue, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 3: CRM_NO_BOOKING_ID
# ════════════════════════════════════════════════════════════════════════════════
def test_booking_id_clean():
    """booking_id заполнен у В аренде/Бронь → 0 нарушений."""
    r = _run(check_crm_no_booking_id, _make_world())
    assert len(r.findings) == 0, r.findings


def test_booking_id_missing_rented():
    """booking_id пуст у «В аренде» → флаг."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["booking_id"] = ""    # пусто = UUID ещё не присвоен
    r = _run(check_crm_no_booking_id, _make_world(clients=clients))
    assert len(r.findings) >= 1, r.findings
    assert "booking_id" in r.findings[0][0]


def test_booking_id_missing_bron():
    """booking_id пуст у «Бронь» → флаг."""
    clients = [dict(_CLIENT_BRON_OK)]
    clients[0]["booking_id"] = ""
    r = _run(check_crm_no_booking_id, _make_world(clients=clients))
    assert len(r.findings) >= 1, r.findings


def test_booking_id_completed_not_flagged():
    """Завершена без booking_id → НЕ флаг (статус не в _ACTIVE_ST)."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["status"] = "Завершена"
    clients[0]["booking_id"] = ""
    r = _run(check_crm_no_booking_id, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_booking_id_bridge_down():
    """clients() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[], clients=None, queue_ip=[], now=_NOW)
    r = _run(check_crm_no_booking_id, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 4: CRM_DEPOSIT
# ════════════════════════════════════════════════════════════════════════════════
def test_deposit_clean_money():
    """Только цифровой депозит — чисто."""
    r = _run(check_crm_deposit, _make_world())
    assert len(r.findings) == 0, r.findings


def test_deposit_clean_passport():
    """Только «passport» — чисто."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["deposit_raw"] = "passport"
    r = _run(check_crm_deposit, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_deposit_both_flagged():
    """Сумма + «passport» в одной строке → флаг (обе формы одновременно).
    Живой формат col S: строка «7000 passport»."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["deposit_raw"] = "7000 passport"   # как оператор ввёл оба
    r = _run(check_crm_deposit, _make_world(clients=clients))
    assert len(r.findings) >= 1, r.findings
    assert "И сумму И" in r.findings[0][1]


def test_deposit_passport_uppercase():
    """«Passport 5000» (регистр не важен) → флаг."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["deposit_raw"] = "Passport 5000"
    r = _run(check_crm_deposit, _make_world(clients=clients))
    assert len(r.findings) >= 1, r.findings


def test_deposit_empty_not_flagged():
    """Пустой deposit_raw → НЕ флаг (нет данных = нет нарушения)."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["deposit_raw"] = ""
    r = _run(check_crm_deposit, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_deposit_non_active_not_flagged():
    """Завершена с «7000 passport» → НЕ флаг (не активный статус)."""
    clients = [dict(_CLIENT_OK)]
    clients[0]["status"] = "Завершена"
    clients[0]["deposit_raw"] = "7000 passport"
    r = _run(check_crm_deposit, _make_world(clients=clients))
    assert len(r.findings) == 0, r.findings


def test_deposit_bridge_down():
    """clients() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[], clients=None, queue_ip=[], now=_NOW)
    r = _run(check_crm_deposit, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 5: FLEET_CLICK_125
# ════════════════════════════════════════════════════════════════════════════════
def test_click_125_home_ok():
    """CLICK 125 дома → нет нарушений (правило: не сдаём = не должен быть «В аренде»)."""
    r = _run(check_fleet_click_125, _make_world())
    assert len(r.findings) == 0, r.findings


def test_click_125_rented_flagged():
    """HONDA CLICK 125 в статусе «В аренде» → флаг.
    Живой формат имени: «HONDA CLICK 125 5580» (точное из Лист1 col C)."""
    bikes = [dict(_BIKE_CLICK_HOME)]
    bikes[0]["status"] = "В аренде"   # нарушение бизнес-правила
    r = _run(check_fleet_click_125, _make_world(bikes=bikes))
    assert len(r.findings) >= 1, r.findings
    assert "CLICK 125" in r.findings[0][1]


def test_click_125_case_insensitive():
    """«honda click 125» (нижний регистр) → флаг (регистронезависимый поиск)."""
    bikes = [{"name": "honda click 125 9999", "status": "В аренде",
              "oil_last_km": 5000, "gear_last_km": 4000, "mileage": 3000}]
    r = _run(check_fleet_click_125, _make_world(bikes=bikes))
    assert len(r.findings) >= 1, r.findings


def test_click_125_pcx_not_flagged():
    """PCX160 в аренде → НЕ флаг (не CLICK 125)."""
    r = _run(check_fleet_click_125, _make_world())
    assert len(r.findings) == 0, r.findings


def test_click_125_bridge_down():
    """fleet() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=None, clients=[], queue_ip=[], now=_NOW)
    r = _run(check_fleet_click_125, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 6: QUEUE_LONG_IP
# ════════════════════════════════════════════════════════════════════════════════
def test_queue_fresh_ok():
    """Свежая in_progress задача (100с) → 0 нарушений."""
    r = _run(check_queue_long_ip, _make_world())
    assert len(r.findings) == 0, r.findings


def test_queue_normal_task_overtime():
    """Нормальная задача висит 2×TASK_TIMEOUT+1s → флаг.
    Живой формат updated: ISO строка с +00:00."""
    old = (_NOW - datetime.timedelta(seconds=601 * 2)).isoformat()   # 2×600+2 = 1202с
    task = {"id": 99, "from": "Filipp-328", "task_text": "т",
            "status": "in_progress", "updated": old}
    w = _make_world(queue=[task], tt=600, ttd=2700)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) >= 1, r.findings
    assert "реапер" in r.findings[0][1]


def test_queue_dev_task_short_not_flagged():
    """Dev-задача висит 1000с (< 2×2700=5400) → НЕ флаг."""
    young = (_NOW - datetime.timedelta(seconds=1000)).isoformat()
    task = {"id": 88, "from": "Filipp-328-dev", "task_text": "дев",
            "status": "in_progress", "updated": young}
    w = _make_world(queue=[task], tt=600, ttd=2700)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) == 0, r.findings


def test_queue_dev_task_overtime():
    """Dev-задача висит 2×2700+1s → флаг (использует TASK_TIMEOUT_DEV)."""
    old = (_NOW - datetime.timedelta(seconds=2701 * 2)).isoformat()   # 5402с > 2×2700
    task = {"id": 77, "from": "Filipp-328-dev", "task_text": "дев",
            "status": "in_progress", "updated": old}
    w = _make_world(queue=[task], tt=600, ttd=2700)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) >= 1, r.findings


def test_queue_dec_task_uses_dev_timeout():
    """Dec-задача (from=Filipp-328-dec) → тот же порог 2×TASK_TIMEOUT_DEV."""
    young_ok = (_NOW - datetime.timedelta(seconds=1000)).isoformat()   # < 5400 → нет флага
    task = {"id": 66, "from": "Filipp-328-dec", "task_text": "дек",
            "status": "in_progress", "updated": young_ok}
    w = _make_world(queue=[task], tt=600, ttd=2700)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) == 0, r.findings


def test_queue_z_iso_format():
    """updated с суффиксом Z ('2026-07-15T08:30:00Z') → корректный парс."""
    old = "2026-07-15T08:00:00Z"   # 4 часа назад от _NOW
    task = {"id": 55, "from": "Filipp-328", "task_text": "т",
            "status": "in_progress", "updated": old}
    w = _make_world(queue=[task], tt=600, ttd=2700)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) >= 1, r.findings   # 4h = 14400s > 2×600


def test_queue_no_updated_skipped():
    """updated пустая строка → пропуск (не флаг, не падение)."""
    task = {"id": 44, "from": "Filipp-328", "task_text": "т",
            "status": "in_progress", "updated": ""}
    r = _run(check_queue_long_ip, _make_world(queue=[task]))
    assert len(r.findings) == 0, r.findings


def test_queue_bridge_down():
    """get_pending() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[], clients=[], queue_ip=None, now=_NOW)
    r = _run(check_queue_long_ip, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 7: OIL_VS_CURRENT_ODO
# ════════════════════════════════════════════════════════════════════════════════
def test_oil_vs_current_odo_clean():
    """Нормальная ситуация: oil_last_km ≠ current_km (байк проехал после замены) → 0 нарушений."""
    bikes = [dict(_BIKE_RENTED_OK)]   # oil_last_km=35200
    svcs = [dict(_SVC_OIL_OK)]        # current_km=36000, diff=800 > OIL_PHOTO_DELTA(100) → нет флага
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) == 0, r.findings


def test_oil_vs_current_odo_golden_2478():
    """ГОЛДЕН инцидент 2478: col I = current_km = 24997, запись старая (>2ч) → флаг.
    Сценарий: vision прочитала одометр (24997) и записала его в col I как «пробег замены»,
    хотя реальная замена была на 22000. Bot Data current_km=24997 (то же фото), запись старая."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 24997, "gear_last_km": 34000, "mileage": 20000}]
    # Bot Data: current_km=24997 (= col I → diff=0 ≤ 100), старая запись (30ч > 7200с)
    svcs = [{"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "oil",
             "current_km": 24997, "last_service_km": 22000,
             "interval_km": 3000, "next_km": 25000, "status": "overdue"}]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) >= 1, r.findings
    assert "24997" in r.findings[0][0], r.findings
    assert "2478" in r.findings[0][1], r.findings


def test_oil_vs_current_odo_fresh_no_flag():
    """ТО записано < 2ч назад: oil_last_km = current_km — НОРМАЛЬНО (только что заменили),
    не флагуем по маркеру свежести OIL_FRESH_SECS."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 24997, "gear_last_km": 34000, "mileage": 20000}]
    # Свежая запись: NOW=2026-07-15 12:00, fresh=11:00 → age=3600с < OIL_FRESH_SECS(7200с)
    svcs = [{"updated_at": _FRESH_TS, "bike": "PCX160 4234", "service_type": "oil",
             "current_km": 24997, "last_service_km": 22000,
             "interval_km": 3000, "next_km": 25000, "status": "ok"}]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) == 0, r.findings


def test_oil_vs_current_odo_small_diff_within_delta():
    """oil_last_km и current_km отличаются на 50 < OIL_PHOTO_DELTA(100) → подозрительно, флаг."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 24997, "gear_last_km": 34000, "mileage": 20000}]
    svcs = [{"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "oil",
             "current_km": 24950,  # |24997 - 24950| = 47 ≤ 100 → флаг
             "last_service_km": 22000, "interval_km": 3000, "next_km": 25000, "status": "ok"}]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) >= 1, r.findings


def test_oil_vs_current_odo_over_delta_no_flag():
    """|oil_last_km - current_km| > OIL_PHOTO_DELTA(100) → нет флага (нормальный разрыв)."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 24500, "gear_last_km": 34000, "mileage": 20000}]
    svcs = [{"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "oil",
             "current_km": 24997,  # |24500 - 24997| = 497 > 100 → нет флага
             "last_service_km": 22000, "interval_km": 3000, "next_km": 25000, "status": "ok"}]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) == 0, r.findings


def test_oil_vs_current_odo_no_oil_record():
    """Нет Bot Data oil-записи для байка → пропуск (note «нет oil-записей»), 0 нарушений."""
    bikes = [dict(_BIKE_RENTED_OK)]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=[]))
    assert len(r.findings) == 0, r.findings
    assert r.notes  # note «не содержит oil-записей»


def test_oil_vs_current_odo_no_plate_skipped():
    """Байк без 4-значного номера в имени → пропуск, нет флага."""
    bikes = [{"name": "XSR 155 GREEN", "status": "В аренде",
              "oil_last_km": 15000, "gear_last_km": 14000, "mileage": 10000}]
    svcs = [{"updated_at": _OLD_TS, "bike": "XSR 155 GREEN", "service_type": "oil",
             "current_km": 15000, "last_service_km": 12000,
             "interval_km": 3000, "next_km": 15000, "status": "due"}]
    r = _run(check_oil_vs_current_odo, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) == 0, r.findings


def test_oil_vs_current_odo_fleet_none():
    """fleet() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=None, clients=[], queue_ip=[], services=[], now=_NOW)
    r = _run(check_oil_vs_current_odo, w)
    assert len(r.findings) == 0
    assert r.notes


def test_oil_vs_current_odo_service_none():
    """service_list() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[dict(_BIKE_RENTED_OK)], clients=[], queue_ip=[], services=None, now=_NOW)
    r = _run(check_oil_vs_current_odo, w)
    assert len(r.findings) == 0
    assert r.notes


# ════════════════════════════════════════════════════════════════════════════════
#  ИНВАРИАНТ 8: BOT_DATA_VS_SHEET
# ════════════════════════════════════════════════════════════════════════════════
def test_bot_data_vs_sheet_clean():
    """last_service_km (Bot Data) совпадает с col I → 0 нарушений."""
    bikes = [dict(_BIKE_RENTED_OK)]   # oil_last_km=35200, gear_last_km=34000
    svcs = [dict(_SVC_OIL_OK), dict(_SVC_GEAR_OK)]
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) == 0, r.findings


def test_bot_data_vs_sheet_oil_diverge():
    """Bot Data last_service_km ↔ col I расходятся > BOT_DATA_OIL_DELTA(200 km) → флаг.
    Сценарий 2478-вариант: vision записала в col I 24997, но Bot Data помнит старое значение 22000."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 24997, "gear_last_km": 34000, "mileage": 20000}]
    svcs = [{"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "oil",
             "current_km": 24997, "last_service_km": 22000,  # diff = 2997 > 200
             "interval_km": 3000, "next_km": 25000, "status": "overdue"}]
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) >= 1, r.findings
    text = r.findings[0][0] + r.findings[0][1]
    assert "2997" in text, r.findings  # diff упомянут в репорте


def test_bot_data_vs_sheet_gear_diverge():
    """Bot Data last_service_km gear ↔ col J расходятся > 200 км → флаг."""
    bikes = [{"name": "PCX160 4234", "status": "В аренде",
              "oil_last_km": 35200, "gear_last_km": 34000, "mileage": 20000}]
    svcs = [{"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "gear",
             "current_km": 36000, "last_service_km": 31000,  # diff = 3000 > 200
             "interval_km": 10000, "next_km": 41000, "status": "ok"}]
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=svcs))
    assert len(r.findings) >= 1, r.findings
    assert "gear" in r.findings[0][0].lower() or "J" in r.findings[0][0], r.findings


def test_bot_data_vs_sheet_small_diff_no_flag():
    """Расхождение ≤ BOT_DATA_OIL_DELTA(200 км) → не флаг."""
    bikes = [dict(_BIKE_RENTED_OK)]   # oil_last_km=35200
    svc = dict(_SVC_OIL_OK)
    svc["last_service_km"] = 35100    # diff = 100 ≤ 200 → нет флага
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=[svc]))
    assert len(r.findings) == 0, r.findings


def test_bot_data_vs_sheet_exact_at_delta_boundary():
    """Расхождение ровно = BOT_DATA_OIL_DELTA(200 км) → НЕ флаг (порог строгий >)."""
    bikes = [dict(_BIKE_RENTED_OK)]   # oil_last_km=35200
    svc = dict(_SVC_OIL_OK)
    svc["last_service_km"] = 35000    # diff = 200 = граница → нет флага (строго >)
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=[svc]))
    assert len(r.findings) == 0, r.findings


def test_bot_data_vs_sheet_just_over_delta():
    """Расхождение = BOT_DATA_OIL_DELTA + 1 = 201 → флаг (> порога)."""
    bikes = [dict(_BIKE_RENTED_OK)]   # oil_last_km=35200
    svc = dict(_SVC_OIL_OK)
    svc["last_service_km"] = 34999    # diff = 201 > 200 → флаг
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=[svc]))
    assert len(r.findings) >= 1, r.findings


def test_bot_data_vs_sheet_no_last_service_km():
    """Bot Data last_service_km = 0/пусто → пропуск (нет предыдущего значения), 0 нарушений."""
    bikes = [dict(_BIKE_RENTED_OK)]
    svc = dict(_SVC_OIL_OK)
    svc["last_service_km"] = 0  # нет предыдущего → пропуск
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=[svc]))
    assert len(r.findings) == 0, r.findings


def test_bot_data_vs_sheet_fleet_none():
    """fleet() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=None, clients=[], queue_ip=[],
                  services=[dict(_SVC_OIL_OK)], now=_NOW)
    r = _run(check_bot_data_vs_sheet, w)
    assert len(r.findings) == 0
    assert r.notes


def test_bot_data_vs_sheet_service_none():
    """service_list() вернул None → note, 0 нарушений."""
    w = FakeWorld(bikes=[dict(_BIKE_RENTED_OK)], clients=[], queue_ip=[],
                  services=None, now=_NOW)
    r = _run(check_bot_data_vs_sheet, w)
    assert len(r.findings) == 0
    assert r.notes


def test_bot_data_vs_sheet_unknown_service_type_skipped():
    """service_type = 'abs' или 'airfilter' → пропуск (нет col в fleet endpoint), 0 нарушений."""
    bikes = [dict(_BIKE_RENTED_OK)]
    svc = {"updated_at": _OLD_TS, "bike": "PCX160 4234", "service_type": "abs",
           "current_km": 36000, "last_service_km": 0,
           "interval_km": 20000, "next_km": 56000, "status": "ok"}
    r = _run(check_bot_data_vs_sheet, _make_world(bikes=bikes, services=[svc]))
    assert len(r.findings) == 0, r.findings


# ════════════════════════════════════════════════════════════════════════════════
#  ИНТЕГРАЦИЯ: run_all / format_report / расширяемость
# ════════════════════════════════════════════════════════════════════════════════
def test_run_all_clean_world():
    """Чистый мир: все инварианты → 0 суммарных нарушений."""
    runs = run_all(_make_world())
    total = sum(len(r.findings) for r in runs)
    assert total == 0, [(r.name, r.findings) for r in runs if r.findings]


def test_run_all_returns_all_checks():
    """run_all возвращает запись для каждого зарегистрированного инварианта."""
    runs = run_all(_make_world())
    names = {r.name for r in runs}
    for name, _ in CHECKS:
        assert name in names, f"Инвариант {name!r} не найден в run_all"


def test_format_report_ok_string():
    """format_report на чистом мире содержит '✅ СХОДИТСЯ'."""
    runs = run_all(_make_world())
    rep = format_report(runs, ts="2026-07-15 12:00")
    assert "✅ СХОДИТСЯ" in rep, rep


def test_format_report_shows_violations():
    """format_report при нарушении содержит '⚠️' и адрес нарушения."""
    bikes = [dict(_BIKE_RENTED_OK)]
    bikes[0]["oil_last_km"] = 0
    runs = run_all(_make_world(bikes=bikes))
    rep = format_report(runs, ts="2026-07-15 12:00")
    assert "⚠️" in rep, rep
    assert "oil_last_km" in rep, rep


def test_degraded_world_no_violations():
    """Полная деградация (все источники None) → только notes, 0 нарушений суммарно.
    Деградация ≠ нарушение инварианта: Bridge упал, а не данные испорчены."""
    w = FakeWorld(bikes=None, clients=None, queue_ip=None, now=_NOW)
    runs = run_all(w)
    total = sum(len(r.findings) for r in runs)
    assert total == 0, [(r.name, r.findings) for r in runs if r.findings]
    total_notes = sum(len(r.notes) for r in runs)
    assert total_notes > 0, "ожидали хотя бы одну заметку при деградации"


def test_extensibility_register():
    """@register добавляет новый инвариант и run_all его прогоняет."""
    from invariants_check import CHECKS, CheckRun, run_all, register, FakeWorld
    n_before = len(CHECKS)

    @register("_TEST_EXT_TEMP")
    def _tmp(w, r):
        r.flag("тест-адрес", "тест-суть")

    try:
        runs = run_all(_make_world())
        by_name = {r.name: r for r in runs}
        assert "_TEST_EXT_TEMP" in by_name, "новый инвариант не появился в run_all"
        assert len(by_name["_TEST_EXT_TEMP"].findings) == 1
    finally:
        CHECKS[:] = [c for c in CHECKS if c[0] != "_TEST_EXT_TEMP"]
        assert len(CHECKS) == n_before, "CHECKS не очищен после теста"


def test_exception_in_check_becomes_note():
    """Исключение внутри инварианта → note 'инвариант упал', не аварийное завершение."""
    from invariants_check import CHECKS, CheckRun, run_all, register
    n_before = len(CHECKS)

    @register("_TEST_CRASH_TEMP")
    def _crash(w, r):
        raise RuntimeError("намеренный краш в тесте")

    try:
        runs = run_all(_make_world())
        by_name = {r.name: r for r in runs}
        crash_run = by_name.get("_TEST_CRASH_TEMP")
        assert crash_run is not None
        assert len(crash_run.findings) == 0
        assert any("инвариант упал" in n for n in crash_run.notes), crash_run.notes
    finally:
        CHECKS[:] = [c for c in CHECKS if c[0] != "_TEST_CRASH_TEMP"]
        assert len(CHECKS) == n_before


# ════════════════════════════════════════════════════════════════════════════════
#  SELF-TEST совместимость: __self-test встроен в invariants_check.py
# ════════════════════════════════════════════════════════════════════════════════
def test_self_test_passes():
    """_self_test() в invariants_check.py завершается с кодом 0 (все PASS)."""
    result = ic._self_test()
    assert result == 0, f"_self_test() вернул {result} — есть FAIL"


if __name__ == "__main__":
    # Быстрый прогон без pytest
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = fail = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            ok += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
            fail += 1
    print(f"\n{'ALL PASS ✅' if fail == 0 else f'FAIL {fail}'} / total {ok+fail}")
    raise SystemExit(0 if fail == 0 else 1)
