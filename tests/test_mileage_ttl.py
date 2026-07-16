"""Тесты TTL на last_mileage_in_topic (MILEAGE_TTL_DAYS, класс C).
Проверяет: свежая запись → возвращается; старая запись > TTL → None;
нет ts → возвращается (fail-safe); несколько записей — свежая побеждает."""
import os, sys
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
sys.path.insert(0, "/root/turbobaby-manager-bot")

import time
import splinter as S

CHAT = -100111
TOPIC = 99

def ok(cond, msg):
    assert cond, msg

def _make_entry(km, conf="high", ts_offset=0):
    """ts_offset < 0 = в прошлом."""
    return {
        "ts": time.time() + ts_offset,
        "vis": {"mileage": str(km), "mileage_confidence": conf},
        "sender": "test",
    }

def setup():
    S._RECENT_PHOTOS.pop((CHAT, TOPIC), None)

# ── A. Свежая запись (ts только что) → возвращается ──────────────────
def test_fresh_entry_returned():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "7"
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [_make_entry(50000, "high", ts_offset=0)]
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is not None, "A: свежая запись должна возвращаться")
    ok(result[0] == 50000, f"A: km=50000, получили {result[0]}")

# ── B. Запись старше TTL → None ───────────────────────────────────────
def test_old_entry_returns_none():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "1"   # 1 день
    old_ts = time.time() - 2 * 86400       # 2 дня назад
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [{
        "ts": old_ts,
        "vis": {"mileage": "40000", "mileage_confidence": "high"},
        "sender": "test",
    }]
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is None, f"B: запись старше TTL должна давать None, получили {result}")

# ── C. Запись без поля ts → возвращается (fail-safe) ─────────────────
def test_no_ts_fallback():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "0.001"   # ничтожный TTL
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [{
        "vis": {"mileage": "31000", "mileage_confidence": "high"},
        "sender": "test",
        # нет "ts"
    }]
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is not None, "C: запись без ts должна проходить (fail-safe)")
    ok(result[0] == 31000, f"C: km=31000, получили {result[0]}")

# ── D. Несколько записей: старая + свежая → свежая ───────────────────
def test_fresh_wins_over_old():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "3"
    old_ts = time.time() - 4 * 86400   # 4 дня назад (> 3d TTL)
    fresh_ts = time.time() - 3600      # 1 час назад (< 3d TTL)
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [
        {"ts": old_ts,   "vis": {"mileage": "10000", "mileage_confidence": "high"}, "sender": "t"},
        {"ts": fresh_ts, "vis": {"mileage": "20000", "mileage_confidence": "high"}, "sender": "t"},
    ]
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is not None, "D: должна быть свежая запись")
    ok(result[0] == 20000, f"D: km=20000 (свежая), получили {result[0]}")

# ── E. Невалидный MILEAGE_TTL_DAYS → fail-safe 7d → свежая запись возвращается ──
def test_invalid_env_fallback():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "not_a_number"
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [_make_entry(77777, "high", ts_offset=-3600)]
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is not None, "E: при невалидном env должен быть fallback 7d → запись возвращается")

# ── F. Без буфера → None (базовый случай) ────────────────────────────
def test_empty_buffer():
    setup()
    os.environ["MILEAGE_TTL_DAYS"] = "7"
    result = S.last_mileage_in_topic(CHAT, TOPIC)
    ok(result is None, "F: пустой буфер → None")

# ── Запуск ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("A fresh_entry_returned",   test_fresh_entry_returned),
        ("B old_entry_returns_none", test_old_entry_returns_none),
        ("C no_ts_fallback",         test_no_ts_fallback),
        ("D fresh_wins_over_old",    test_fresh_wins_over_old),
        ("E invalid_env_fallback",   test_invalid_env_fallback),
        ("F empty_buffer",           test_empty_buffer),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
        finally:
            os.environ.pop("MILEAGE_TTL_DAYS", None)
    print(f"\n{passed}/{len(tests)} passed")
    if passed < len(tests):
        sys.exit(1)
