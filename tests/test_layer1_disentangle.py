"""Слой 1: РАЗВЯЗКА handover↔return (ВОЗВРАТ ВЫИГРЫВАЕТ). Жёсткие регресс-тесты closing —
доказать, что НАСТОЯЩИЙ возврат ВСЕГДА заводит closing-приёмку, а инверсия приоритета не теряет его.
Мок-уровень, counter на closing_upsert."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848; TOPIC = 5151; BIKE = "ADV 350CC RED BKK 9890"

class U:
    def __init__(s): s.username = "extthiwxer"; s.is_bot = False
class Msg:
    def __init__(s, text, photo=False):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = CHAT; s.message_thread_id = TOPIC
        s.date = datetime.datetime(2026, 6, 25, 9, 0, tzinfo=datetime.timezone.utc)
        s.message_id = 9; s.from_user = U(); s.reply_to_message = None
class Ctx:
    class B: username = "turbobaby_manager_bot"
    bot = B()
class FakeClaude:
    def __init__(s, parsed, vis=None): s._p = parsed; s._v = vis or {}
    def quick(s, system, text, max_tokens=300, **kw):
        if system == S.TRANSLATE_RU_TH: return "ครับ"
        return json.dumps(s._p)
    def vision(s, *a, **k): return json.dumps(s._v)
class FakeBridge:
    def __init__(s, status=""): s.status = status; s.closing = []; s.pend = []; s.events = []
    def find_bike(s, q): return {"name": BIKE, "status": s.status, "oil_last_km": 12000}
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def service_pending_upsert(s, **k): s.pend.append(k); return {"ok": True, "status": k.get("status")}
    def service_list(s, *a, **k): return {"items": []}
    def add_event(s, **k): s.events.append(k); return {"ok": True, "saved": True}
    def closing_upsert(s, **k): s.closing.append(k); return {"ok": True, "total_due": 0}
    def service_upsert(s, **k): return {"ok": True, "next_km": 0, "status": "ok", "km_left": 0}

SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append(text)
async def noop(*a, **k): pass
async def rec_dl(pm): return b"x"
S._send = rec_send; S._send_bike_card = noop; S._after_mileage = noop
S._ask_mileage_confirm = noop; S._ask_service_col = noop; S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)

def reset(): SENDS.clear(); S._CARD_LAST.clear(); S._ODOMETER_ASK_TS.clear(); S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear()
def run(c): return asyncio.run(c)

def go(text, parsed, status="ДОМА", vis=None, photo=False):
    reset(); b = FakeBridge(status=status)
    run(S._handle_servicing(Msg(text, photo=photo), Ctx(), b, FakeClaude(parsed, vis=vis)))
    return b

# R1: event_type==return + топливо+пробег → closing вызван
def test_R1_return_event_closing():
    b = go("вернулся, бензин полный, пробег 19200",
           {"type": "event", "event_type": "return", "bike": BIKE, "fuel": "полный", "mileage": "19200", "works": []},
           status="В аренде")
    assert len(b.closing) == 1, b.closing

# R2: только слово возврата (без event_type) → closing вызван
def test_R2_return_word_closing():
    b = go("клиент вернул байк",
           {"type": "event", "event_type": "other", "bike": BIKE, "works": []}, status="В аренде")
    assert len(b.closing) == 1, b.closing

# R3: CRM-возврат (нет слов, топливо+пробег, «В аренде») → closing вызван
def test_R3_crm_return_closing():
    b = go("бензин полный пробег 19200",
           {"type": "event", "event_type": "other", "bike": BIKE, "fuel": "полный", "mileage": "19200", "works": []},
           status="В аренде")
    assert len(b.closing) == 1, b.closing

# R4: ЧИСТАЯ выдача (handover, байк ДОМА, без handback) → closing НЕ вызван
def test_R4_clean_handover_no_closing():
    b = go("выдаю клиенту, повезу",
           {"type": "event", "event_type": "handover", "bike": BIKE, "fuel": "", "mileage": "", "works": []},
           status="ДОМА")
    assert b.closing == [], b.closing

# R4b: ЭДЖ (по дизайну «возврат выигрывает») — handover + handback + «В аренде» → closing ВЫЗВАН (лишний closing лучше потери)
def test_R4b_ambiguous_handover_with_handback_leans_return():
    b = go("выдаю клиенту, бензин полный, пробег 19200",
           {"type": "event", "event_type": "handover", "bike": BIKE, "fuel": "полный", "mileage": "19200", "works": []},
           status="В аренде")
    assert len(b.closing) == 1, "спорный handover+handback+В аренде → возврат (closing), по принципу штаба"

# R5 (КОНФЛИКТ, главный): возврат + handover-слово в одном → ВОЗВРАТ ВЫИГРЫВАЕТ → closing вызван
def test_R5_conflict_return_wins():
    b = go("клиент вернул байк, потом выдам другому",
           {"type": "event", "event_type": "other", "bike": BIKE, "fuel": "полный", "mileage": "19200", "works": []},
           status="В аренде")
    assert len(b.closing) == 1, "конфликт: возврат должен выиграть, closing вызван"

# R6 (неоднозначность): топливо+пробег + «В аренде» без слов выдачи → возврат → closing вызван
def test_R6_ambiguous_leans_return():
    b = go("бензин 3/4, пробег 19250",
           {"type": "event", "event_type": "other", "bike": BIKE, "fuel": "3/4", "mileage": "19250", "works": []},
           status="В аренде")
    assert len(b.closing) == 1, b.closing

# R8 (регрессия пакета Б): intake «на масло» (не в аренде) → closing НЕ вызван, phase-1 заявка создана
def test_R8_intake_no_closing_phase1():
    b = go("привёз байк на замену масла и редуктора",
           {"type": "event", "event_type": "intake", "bike": BIKE, "works": ["замена масла", "масло в редукторе"]},
           status="ДОМА")
    assert b.closing == [], "intake не заводит closing"
    assert any(p.get("status") == "заявлено" for p in b.pend), "phase-1 заявка должна создаться"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} регресс-тестов развязки (Слой 1)")
