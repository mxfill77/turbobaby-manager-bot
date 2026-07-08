"""O3-3a ВЫДАЧА: активация брони (Бронь→В аренде) на handover-контексте.
Моки: handover в «Обслуживании» → карточка подтверждения в INTAKE_CHAT → «да» авторизатора →
activate_booking под билетом 4.2 (с date_start) → ✅; «нет» → ничего не записано; брони нет →
⚠️ без падения; не-авторизатор → игнор. Сеть/LLM/_send замоканы."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

SERV_CHAT = -1002751134848; TOPIC = 4242; BIKE = "CB 300CC R 9011"
INTAKE = S.INTAKE_CHAT
DATE_START = "2026-07-08 10:00"

class U:
    def __init__(s, uname="extthiwxer"): s.username = uname; s.is_bot = False
class Msg:
    def __init__(s, text, chat_id=SERV_CHAT, uname="extthiwxer", photo=False):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = chat_id; s.message_thread_id = (TOPIC if chat_id == SERV_CHAT else None)
        s.date = datetime.datetime(2026, 7, 8, 8, 0, tzinfo=datetime.timezone.utc)
        s.message_id = 777; s.from_user = U(uname); s.reply_to_message = None
class Ctx:
    class B: username = "turbobaby_manager_bot"
    bot = B()
class FakeClaude:
    def __init__(s, parsed): s._p = parsed
    def quick(s, system, text, max_tokens=300):
        if system == S.TRANSLATE_RU_TH: return "ครับ"
        return json.dumps(s._p)
    def vision(s, *a, **k): return "{}"

class FakeBridge:
    def __init__(s, clients=None):
        s.clients = clients if clients is not None else []
        s.activated = []; s.states = []; s.events = []; s.tickets = 0
    def _call(s, action, **k):
        assert action == "clients"
        return {"ok": True, "data": {"clients": s.clients}}
    def find_bike(s, q): return {"name": BIKE, "status": "ДОМА", "oil_last_km": 30500}
    def state_set(s, **k): s.states.append(k); return {"ok": True}
    def add_event(s, **k): s.events.append(k); return {"ok": True, "saved": True}
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def service_list(s, *a, **k): return {"items": []}
    def closing_upsert(s, **k): return {"ok": True, "total_due": 0}
    def issue_write_ticket(s): s.tickets += 1; return {"ok": True, "ticket": "t-42"}
    def activate_booking(s, bike, name, date_start=None):
        s.activated.append({"bike": bike, "name": name, "date_start": date_start})
        return {"ok": True, "activated": True, "row": 17, "bike": bike, "name": name}

BOOKING_ROW = {"row": 17, "status": "Бронь", "bike": BIKE, "name": "Иван Тест",
               "date_start": DATE_START, "date_end": "2026-07-15 10:00", "booking_id": "b-1"}

SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append((chat_id, text))
async def rec_pass(*a, **k): pass
async def rec_dl(pm): return b"x"
S._send = rec_send; S._send_bike_card = rec_pass; S._after_mileage = rec_pass
S._ask_mileage_confirm = rec_pass; S._ask_service_col = rec_pass; S._download_photo = rec_dl
S.set_topic_bike(SERV_CHAT, TOPIC, BIKE)

HO_PARSE = {"type": "event", "event_type": "handover", "bike": BIKE,
            "fuel": "", "mileage": "", "works": []}

def reset():
    SENDS.clear(); S._HANDOVER_ACTIVATIONS.clear(); S._HO_ACT_WARN_TS.clear()
    S._INTAKE_DRAFTS.clear(); S._CARD_LAST.clear(); S._PENDING_WORKS.clear()
def run(c): return asyncio.run(c)
def intake_sends(): return [t for c, t in SENDS if c == INTAKE]
def do_handover(b):
    run(S._handle_servicing(Msg("выдаю клиенту, повёз"), Ctx(), b, FakeClaude(HO_PARSE)))

# ---- (а) handover с бронью → карточка → «да» авторизатора → activate с date_start → ✅ ----
def test_happy_path_yes():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b)
    cards = [t for t in intake_sends() if "ВЫДАЧА" in t and "Активирую" in t]
    assert len(cards) == 1, f"ждал одну карточку активации во Входящих: {SENDS}"
    assert "Иван Тест" in cards[0] and "строка 17" in cards[0]
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["status"] == "awaiting"
    assert b.states, "state-путь Bot Data должен отработать как раньше (дополнение, не замена)"
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.activated == [{"bike": BIKE, "name": "Иван Тест", "date_start": DATE_START}], \
        f"activate должен уйти с date_start: {b.activated}"
    assert b.tickets == 1, "красный шаг — строго под билетом 4.2"
    assert any("✅ В аренде" in t and "строка 17" in t for t in intake_sends()), f"{SENDS}"
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["status"] == "activated"

# ---- (б) «нет» → ничего не записано ----
def test_no_cancels():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b)
    run(S._handle_intake(Msg("нет", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.activated == [], "на «нет» записи в CRM быть не должно"
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["status"] == "rejected"
    assert any("отменил" in t.lower() for t in intake_sends()), f"{SENDS}"

# ---- (в) брони нет → ⚠️ без падения, handover-путь жив ----
def test_no_booking_warns():
    reset(); b = FakeBridge(clients=[])
    do_handover(b)   # не должно упасть
    warns = [t for t in intake_sends() if "⚠️" in t and "не нашёл" in t]
    assert len(warns) == 1, f"ждал ⚠️ «брони не нашёл»: {SENDS}"
    assert "руками" in warns[0]
    assert INTAKE not in S._HANDOVER_ACTIVATIONS, "без брони pending-активации не заводим"
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.activated == [], "без pending «да» ничего активировать не должно"

# ---- (г) не-авторизатор говорит «да» → игнор ----
def test_non_approver_ignored():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="pym_thai"), Ctx(), b, None))
    assert b.activated == [], "Пым/тайцы не авторизуют — «да» не-аппрувера игнорируется (§9)"
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["status"] == "awaiting", "запрос остаётся ждать аппрувера"

# ---- уже «В аренде» → карточку не шлём, активировать нечего ----
def test_already_active_silent():
    reset(); b = FakeBridge(clients=[dict(BOOKING_ROW, status="В аренде")])
    do_handover(b)
    assert not any("Активирую" in t for t in intake_sends()), f"уже активна — карточка не нужна: {SENDS}"
    assert INTAKE not in S._HANDOVER_ACTIVATIONS

# ---- повторная handover-фраза той же брони → карточка не дублируется ----
def test_card_not_duplicated():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b); do_handover(b)
    cards = [t for t in intake_sends() if "Активирую" in t]
    assert len(cards) == 1, f"повтор handover не должен дублировать карточку: {len(cards)}"

# ---- просроченный запрос (TTL) → «да» уже не активирует ----
def test_ttl_expired():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b)
    S._HANDOVER_ACTIVATIONS[INTAKE]["ts"] -= (S._HO_ACT_TTL + 60)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.activated == [], "просроченный запрос активации исполняться не должен"

# ---- err от Bridge → честная ошибка, статус error ----
def test_bridge_error_honest():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    def bad_activate(bike, name, date_start=None):
        return {"ok": False, "error": "booking_not_found", "message": "не найдена"}
    b.activate_booking = bad_activate
    do_handover(b)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert any("❌ Активация не прошла" in t and "booking_not_found" in t for t in intake_sends()), f"{SENDS}"
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["status"] == "error"

# ---- intake-draft awaiting_approval выигрывает «да» (существующий путь не сломан) ----
def test_intake_draft_priority():
    reset(); b = FakeBridge(clients=[BOOKING_ROW])
    do_handover(b)
    S._INTAKE_DRAFTS[INTAKE] = {"status": "awaiting_approval", "ts": S._time.time(),
                                "model": BIKE, "client": "Иван Тест", "deposit_type": "паспорт",
                                "date_start": "08-07-2026", "date_end": "15-07-2026"}
    class BR2(FakeBridge):
        def create_booking(s, **k): s.booked = k; return {"ok": True, "row": 33}
    b2 = BR2(clients=[BOOKING_ROW]); b2.activated = b.activated
    S._HANDOVER_ACTIVATIONS[INTAKE] = dict(S._HANDOVER_ACTIVATIONS[INTAKE])
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b2, None))
    assert getattr(b2, "booked", None), "«да» при живой карточке брони по-прежнему ставит бронь"
    assert b2.activated == [], "активация НЕ перехватывает «да» у карточки брони"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов активации выдачи (O3-3a)")
