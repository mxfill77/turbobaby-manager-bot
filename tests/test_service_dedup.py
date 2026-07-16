"""Класс E дедуп: повтор (bike, service_type, km) в окне SERVICE_DEDUP_WIN_SEC не пишет вторую строку в Лист1.
Гейт «да» Пыма НЕ ослаблен (дедуп внутри _sp_write_done, после trust-check).
Fail-safe: стор сбоит → прежнее поведение."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 308
BIKE = "XMAX 300CC NEW BLUE-3 PHUKET 4724"
PLATE = "4724"

class FakeBridge:
    def __init__(self):
        self.oil_calls = []; self.svc_calls = []; self.upserts = []; self.events = []
        self.closed = False
    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed)); return {"ok": True}
    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed)); return {"ok": True}
    def service_upsert(self, **kw): self.upserts.append(kw); return {"ok": True, "next_km": 24316, "status": "ok"}
    def add_event(self, **kw): self.events.append(kw); return {"ok": True}
    def service_pending_close(self, **kw): self.closed = True; return {"ok": True}
    def find_bike(self, q): return {"name": BIKE}

def run(c): return asyncio.run(c)

def reset():
    S._SVC_WRITE_DEDUP.clear()

# ============ A) повтор В окне — вторая запись НЕ идёт в Лист1 ============
def test_dedup_within_window_skips_second_write():
    reset()
    import time as _t
    b1 = FakeBridge()
    run(S._sp_write_done(None, b1, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
    assert len(b1.oil_calls) == 1, "первая запись должна пройти"

    # Второй вызов с той же тройкой — стор свежий, окно не истекло
    b2 = FakeBridge()
    run(S._sp_write_done(None, b2, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
    assert len(b2.oil_calls) == 0, f"дедуп: вторая запись масла пропущена, oil_calls={b2.oil_calls}"
    assert b2.closed is True, "service_pending_close всё равно зовётся"

# ============ B) тройка ВНЕ окна — пишет ============
def test_dedup_outside_window_writes_again():
    reset()
    b1 = FakeBridge()
    run(S._sp_write_done(None, b1, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
    assert len(b1.oil_calls) == 1

    # Протухаем стор — симулируем истечение окна
    key = (PLATE, "oil", 20316)
    S._SVC_WRITE_DEDUP[key] = S._SVC_WRITE_DEDUP[key] - S._SVC_DEDUP_WIN_SEC - 1

    b2 = FakeBridge()
    run(S._sp_write_done(None, b2, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
    assert len(b2.oil_calls) == 1, f"после истечения окна запись должна пройти, oil_calls={b2.oil_calls}"

# ============ C) дедуп только по точной тройке: другой km — пишет ============
def test_dedup_different_km_writes():
    reset()
    b1 = FakeBridge()
    run(S._sp_write_done(None, b1, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
    assert len(b1.oil_calls) == 1

    b2 = FakeBridge()
    run(S._sp_write_done(None, b2, CHAT, TOPIC, BIKE, ["oil"], "20999", confirmed_by="@Pleummmm"))
    assert len(b2.oil_calls) == 1, f"другой km → дедуп не срабатывает, oil_calls={b2.oil_calls}"

# ============ D) дедуп для gear (set_fleet_service) ============
def test_dedup_gear_within_window():
    reset()
    b1 = FakeBridge()
    run(S._sp_write_done(None, b1, CHAT, TOPIC, BIKE, ["gear"], "20316", confirmed_by="@Pleummmm"))
    assert len(b1.svc_calls) == 1

    b2 = FakeBridge()
    run(S._sp_write_done(None, b2, CHAT, TOPIC, BIKE, ["gear"], "20316", confirmed_by="@Pleummmm"))
    assert len(b2.svc_calls) == 0, f"дедуп gear: вторая запись пропущена, svc_calls={b2.svc_calls}"

# ============ E) fail-safe: стор сбоит → прежнее поведение ============
def test_dedup_failsafe_store_exception():
    """Если _SVC_WRITE_DEDUP.get() бросит — запись идёт как обычно (fail-safe)."""
    reset()
    # Подменяем стор на объект, чей .get бросает
    class BrokenDict(dict):
        def get(self, key, default=None):
            raise RuntimeError("стор сломан")
    orig = S._SVC_WRITE_DEDUP
    S._SVC_WRITE_DEDUP = BrokenDict()
    try:
        b = FakeBridge()
        run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE, ["oil"], "20316", confirmed_by="@Pleummmm"))
        assert len(b.oil_calls) == 1, f"fail-safe: при сбое стора запись должна пройти, oil_calls={b.oil_calls}"
    finally:
        S._SVC_WRITE_DEDUP = orig

# ============ F) events (non-col kinds) не дедуплируются стором — у них msg_id идемпотентность ============
def test_dedup_does_not_affect_events():
    reset()
    b1 = FakeBridge()
    run(S._sp_write_done(None, b1, CHAT, TOPIC, BIKE, ["pads"], "20316", confirmed_by="@Pleummmm"))
    assert len(b1.events) == 1

    b2 = FakeBridge()
    run(S._sp_write_done(None, b2, CHAT, TOPIC, BIKE, ["pads"], "20316", confirmed_by="@Pleummmm"))
    assert len(b2.events) == 1, "события (pads) не через стор дедупа — пишутся как обычно"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов дедупа записи ТО")
