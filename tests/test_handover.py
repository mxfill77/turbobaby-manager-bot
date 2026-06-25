"""Моки дешёвого HANDOVER-гейта (выдача клиенту): гасит советы ухода/стоянки + нудёж «нет фото»,
handover НЕ путается с возвратом. Сеть/LLM/_send замоканы."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848; TOPIC = 4242; BIKE = "CB 300CC R 9011"

class U:
    def __init__(s, uname="extthiwxer"): s.username = uname; s.is_bot = False
class Msg:
    def __init__(s, text, photo=False):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = CHAT; s.message_thread_id = TOPIC
        s.date = datetime.datetime(2026, 6, 25, 8, 0, tzinfo=datetime.timezone.utc)
        s.message_id = 777; s.from_user = U(); s.reply_to_message = None
class Ctx:
    class B: username = "turbobaby_manager_bot"
    bot = B()
class FakeClaude:
    def __init__(s, parsed, vis=None): s._p = parsed; s._v = vis or {}
    def quick(s, system, text, max_tokens=300):
        if system == S.TRANSLATE_RU_TH: return "ครับ"
        return json.dumps(s._p)
    def vision(s, *a, **k): return json.dumps(s._v)
class FakeBridge:
    def __init__(s, status=""): s.status = status; s.closing = []; s.events = []; s.pend = []
    def find_bike(s, q): return {"name": BIKE, "status": s.status, "oil_last_km": 30500}
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def service_pending_upsert(s, **k): s.pend.append(k); return {"ok": True, "status": k.get("status")}
    def service_list(s, *a, **k): return {"items": []}
    def add_event(s, **k): s.events.append(k); return {"ok": True, "saved": True}
    def closing_upsert(s, **k): s.closing.append(k); return {"ok": True, "total_due": 0}
    def service_upsert(s, **k): return {"ok": True, "next_km": 0, "status": "ok", "km_left": 0}

SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append(text)
async def rec_card(*a, **k): pass
async def rec_after(*a, **k): pass
async def rec_askmil(*a, **k): pass
async def rec_col(*a, **k): pass
async def rec_dl(pm): return b"x"
S._send = rec_send; S._send_bike_card = rec_card; S._after_mileage = rec_after
S._ask_mileage_confirm = rec_askmil; S._ask_service_col = rec_col; S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)

def reset(): SENDS.clear(); S._CARD_LAST.clear(); S._ODOMETER_ASK_TS.clear(); S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear()
def run(c): return asyncio.run(c)

# ---- unit: _is_handover_context ----
def test_handover_ctx_unit():
    assert S._is_handover_context({"event_type": "handover"}, "") is True
    assert S._is_handover_context({}, "выдаю байк клиенту") is True
    assert S._is_handover_context({}, "повезу клиенту в Патонг") is True
    assert S._is_handover_context({}, "клиент вернул байк") is False   # это возврат, не выдача
    assert S._is_handover_context({}, "просто болтают") is False

# ---- handover гасит совет про грязь ----
def test_handover_suppresses_dirt():
    reset(); b = FakeBridge(status="ДОМА")
    run(S._handle_servicing(Msg("выдаю клиенту, повёз", photo=True), Ctx(), b,
                            FakeClaude({"type": "none"}, vis={"dirt": True})))
    assert not any("помыть" in s or "чехл" in s for s in SENDS), f"на выдаче совет ухода должен молчать: {SENDS}"

def test_dirt_fires_without_handover():
    reset(); b = FakeBridge(status="ДОМА")
    run(S._handle_servicing(Msg("стоит на парковке", photo=True), Ctx(), b,
                            FakeClaude({"type": "none"}, vis={"dirt": True})))
    assert any("помыть" in s or "чехл" in s for s in SENDS), "вне выдачи грязь-совет должен сработать"

# ---- handover НЕ возврат (не запускает closing-приёмку) ----
def test_handover_not_return():
    reset(); b = FakeBridge(status="В аренде")
    run(S._handle_servicing(Msg("выдаю клиенту, бензин полный, пробег 33797"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "handover", "bike": BIKE,
                                        "fuel": "полный", "mileage": "33797", "works": []})))
    assert b.closing == [], f"выдача НЕ должна заводить лист закрытия: {b.closing}"

def test_return_still_creates_closing():
    reset(); b = FakeBridge(status="В аренде")
    run(S._handle_servicing(Msg("вернулся, бензин полный, пробег 33797"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "return", "bike": BIKE,
                                        "fuel": "полный", "mileage": "33797", "works": []})))
    assert len(b.closing) == 1, "возврат по-прежнему → лист закрытия (регрессии нет)"

# ---- photo-reminder подавлен на handover и при свежем пробеге в буфере ----
def test_photo_reminder_suppressed_on_handover():
    reset(); b = FakeBridge(status="В аренде")
    run(S._handle_servicing(Msg("выдаю клиенту"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "handover", "bike": BIKE,
                                        "fuel": "", "mileage": "", "works": []})))
    assert not any("не хватает фото" in s for s in SENDS), "на выдаче нудёж про фото гасим"

def test_photo_reminder_suppressed_when_buffer_has_mileage():
    reset(); b = FakeBridge(status="В аренде")
    # в буфере темы уже есть свежий пробег
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [{"ts": S._time.time(), "sender": "@x",
                                        "vis": {"mileage": "33797", "mileage_confidence": "high"}}]
    run(S._handle_servicing(Msg("вернулся"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "return", "bike": BIKE,
                                        "fuel": "", "mileage": "", "works": []})))
    assert not any("не хватает фото" in s for s in SENDS), "если пробег темы уже виден — не нудим"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов handover-гейта")
