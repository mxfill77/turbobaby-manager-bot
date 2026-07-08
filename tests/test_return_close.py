"""O3-3b фаза II ПРИЁМ: карточка закрытия аренды (В аренде→Завершена) на return-контексте.
Моки: возврат в «Обслуживании» → карточка ПРИЁМА в INTAKE_CHAT → «да» авторизатора →
close_booking под билетом 4.2 (с km_end/paid_total) → ✅; «нет» → ничего не записано;
строки «В аренде» нет → ⚠️ без падения; уже «Завершена» → молчание (идемпотентность);
unknown_action (Bridge без деплоя фазы I) → ⏳, карточка жива; не-авторизатор → игнор.
Существующий closing-путь (лист закрытия) НЕ ломается. Сеть/LLM/_send замоканы."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

SERV_CHAT = -1002751134848; TOPIC = 4242; BIKE = "CB 300CC R 9011"
INTAKE = S.INTAKE_CHAT
DATE_START = "2026-07-01 10:00"

class U:
    def __init__(s, uname="extthiwxer"): s.username = uname; s.is_bot = False
class Msg:
    def __init__(s, text, chat_id=SERV_CHAT, uname="extthiwxer", photo=False):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = chat_id; s.message_thread_id = (TOPIC if chat_id == SERV_CHAT else None)
        s.date = datetime.datetime(2026, 7, 8, 8, 0, tzinfo=datetime.timezone.utc)
        s.message_id = 778; s.from_user = U(uname); s.reply_to_message = None
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
    def __init__(s, clients=None, total_due=1500):
        s.clients = clients if clients is not None else []
        s.closed = []; s.states = []; s.events = []; s.tickets = 0
        s.total_due = total_due
    def _call(s, action, **k):
        assert action == "clients"
        return {"ok": True, "data": {"clients": s.clients}}
    def find_bike(s, q): return {"name": BIKE, "status": "в аренде", "oil_last_km": 30500}
    def state_set(s, **k): s.states.append(k); return {"ok": True}
    def add_event(s, **k): s.events.append(k); return {"ok": True, "saved": True}
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def service_list(s, *a, **k): return {"items": []}
    def closing_upsert(s, **k): s.closing = k; return {"ok": True, "row": 5, "total_due": s.total_due}
    def issue_write_ticket(s): s.tickets += 1; return {"ok": True, "ticket": "t-43"}
    def close_booking(s, bike, name, date_start=None, km_end=None, paid_total=None):
        s.closed.append({"bike": bike, "name": name, "date_start": date_start,
                         "km_end": km_end, "paid_total": paid_total})
        return {"ok": True, "closed": True, "row": 21, "bike": bike, "name": name}

RENT_ROW = {"row": 21, "status": "В аренде", "bike": BIKE, "name": "Иван Тест",
            "date_start": DATE_START, "date_end": "2026-07-08 10:00", "booking_id": "b-1"}

SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append((chat_id, text))
async def rec_pass(*a, **k): pass
async def rec_dl(pm): return b"x"
S._send = rec_send; S._send_bike_card = rec_pass; S._after_mileage = rec_pass
S._ask_mileage_confirm = rec_pass; S._ask_service_col = rec_pass; S._download_photo = rec_dl
S.set_topic_bike(SERV_CHAT, TOPIC, BIKE)

RET_PARSE = {"type": "event", "event_type": "return", "bike": BIKE,
             "fuel": "полный", "mileage": "35200", "works": []}

def reset():
    SENDS.clear(); S._RETURN_CLOSES.clear(); S._RET_CLOSE_WARN_TS.clear()
    S._HANDOVER_ACTIVATIONS.clear(); S._HO_ACT_WARN_TS.clear()
    S._INTAKE_DRAFTS.clear(); S._CARD_LAST.clear(); S._PENDING_WORKS.clear()
def run(c): return asyncio.run(c)
def intake_sends(): return [t for c, t in SENDS if c == INTAKE]
def do_return(b, parse=RET_PARSE):
    run(S._handle_servicing(Msg("вернул байк, принял"), Ctx(), b, FakeClaude(parse)))

# ---- (а) return со строкой «В аренде» → карточка → «да» авторизатора → close с km_end/paid → ✅ ----
def test_happy_path_yes():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    cards = [t for t in intake_sends() if "ПРИЁМ" in t and "Завершаю" in t]
    assert len(cards) == 1, f"ждал одну карточку приёма во Входящих: {SENDS}"
    assert "Иван Тест" in cards[0] and "строка 21" in cards[0]
    assert "35200" in cards[0], f"пробег из return-контекста должен быть в карточке: {cards[0]}"
    assert "1 500" in cards[0] or "1500" in cards[0], f"итог закрытия должен быть в карточке: {cards[0]}"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "awaiting"
    assert getattr(b, "closing", None), "closing-путь (лист закрытия) должен отработать как раньше"
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed == [{"bike": BIKE, "name": "Иван Тест", "date_start": DATE_START,
                         "km_end": "35200", "paid_total": 1500.0}], \
        f"close должен уйти с date_start/km_end/paid_total: {b.closed}"
    assert b.tickets == 1, "красный шаг — строго под билетом 4.2"
    assert any("✅ Завершена" in t and "строка 21" in t for t in intake_sends()), f"{SENDS}"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "closed"

# ---- (б) «нет» → ничего не записано ----
def test_no_cancels():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    run(S._handle_intake(Msg("нет", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed == [], "на «нет» записи в CRM быть не должно"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "rejected"
    assert any("отменил" in t.lower() for t in intake_sends()), f"{SENDS}"

# ---- «не завершай» → отказ, НЕ закрытие (yes-слово «заверш» внутри отказа) ----
def test_negation_not_confused():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    run(S._handle_intake(Msg("не завершай", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed == [], "«не завершай» — отказ, закрытия быть не должно"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "rejected"

# ---- (в) строки «В аренде» нет → ⚠️ без падения ----
def test_no_rent_row_warns():
    reset(); b = FakeBridge(clients=[])
    do_return(b)   # не должно упасть
    warns = [t for t in intake_sends() if "⚠️" in t and "не нашёл" in t]
    assert len(warns) == 1, f"ждал ⚠️ «В аренде не нашёл»: {SENDS}"
    assert "руками" in warns[0]
    assert INTAKE not in S._RETURN_CLOSES, "без строки аренды pending-закрытие не заводим"
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed == [], "без pending «да» ничего закрывать не должно"

# ---- (г) не-авторизатор говорит «да» → игнор ----
def test_non_approver_ignored():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="pym_thai"), Ctx(), b, None))
    assert b.closed == [], "Пым/тайцы не авторизуют — «да» не-аппрувера игнорируется (§9)"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "awaiting", "запрос остаётся ждать аппрувера"

# ---- (д) unknown_action (Bridge ещё без деплоя фазы I) → ⏳, карточка ЖИВА, повторное «да» после деплоя закрывает ----
def test_unknown_action_keeps_card():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    good_close = b.close_booking
    def old_bridge(bike, name, date_start=None, km_end=None, paid_total=None):
        return {"ok": False, "error": "unknown_action", "message": "close_booking?"}
    b.close_booking = old_bridge
    do_return(b)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert any("⏳" in t and "не задеплоено" in t for t in intake_sends()), f"{SENDS}"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "awaiting", "карточка должна остаться живой до деплоя"
    b.close_booking = good_close   # «Termux задеплоил Bridge»
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert len(b.closed) == 1, f"после деплоя то же «да» должно закрыть: {b.closed}"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "closed"

# ---- (е) последняя строка уже «Завершена» → молчание (идемпотентность повторного return) ----
def test_already_closed_silent():
    reset(); b = FakeBridge(clients=[dict(RENT_ROW, status="Завершена")])
    do_return(b)
    assert not any("ПРИЁМ" in t for t in intake_sends()), f"уже завершена — ни карточки, ни ⚠️: {SENDS}"
    assert INTAKE not in S._RETURN_CLOSES

# ---- err от Bridge (not_active и т.п.) → честная ошибка, статус error ----
def test_bridge_error_honest():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    def bad_close(bike, name, date_start=None, km_end=None, paid_total=None):
        return {"ok": False, "error": "odometer_back", "message": "km_end меньше одометра"}
    b.close_booking = bad_close
    do_return(b)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert any("❌ Закрытие не прошло" in t and "odometer_back" in t for t in intake_sends()), f"{SENDS}"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "error"

# ---- пробега в контексте нет → карточка просит цифру; «да 35300» → km_end из ответа ----
def test_km_from_reply():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b, parse=dict(RET_PARSE, mileage=""))
    cards = [t for t in intake_sends() if "ПРИЁМ" in t]
    assert len(cards) == 1 and "цифра" in cards[0].lower() or "цифр" in cards[0], \
        f"без пробега карточка должна просить цифру: {cards}"
    run(S._handle_intake(Msg("да 35300", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed and b.closed[0]["km_end"] == "35300", f"km_end должен взяться из ответа: {b.closed}"

# ---- итог закрытия 0/не число → K не пишем (paid_total=None), карточка без «оплачено» ----
def test_zero_due_no_paid():
    reset(); b = FakeBridge(clients=[RENT_ROW], total_due=0)
    do_return(b)
    cards = [t for t in intake_sends() if "ПРИЁМ" in t]
    assert cards and "оплачено" not in cards[0], f"итог 0 → «оплачено» в карточке не показываем: {cards}"
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed and b.closed[0]["paid_total"] is None, f"итог 0 → K не трогаем: {b.closed}"

# ---- повторная return-фраза той же аренды → карточка не дублируется ----
def test_card_not_duplicated():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b); do_return(b)
    cards = [t for t in intake_sends() if "Завершаю" in t]
    assert len(cards) == 1, f"повтор return не должен дублировать карточку: {len(cards)}"

# ---- просроченный запрос (TTL) → «да» уже не закрывает ----
def test_ttl_expired():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    S._RETURN_CLOSES[INTAKE]["ts"] -= (S._RET_CLOSE_TTL + 60)
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.closed == [], "просроченный запрос закрытия исполняться не должен"

# ---- приоритет «да»: intake-draft (бронь) выигрывает у карточки приёма ----
def test_intake_draft_priority():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    S._INTAKE_DRAFTS[INTAKE] = {"status": "awaiting_approval", "ts": S._time.time(),
                                "model": BIKE, "client": "Иван Тест", "deposit_type": "паспорт",
                                "date_start": "08-07-2026", "date_end": "15-07-2026"}
    class BR2(FakeBridge):
        def create_booking(s, **k): s.booked = k; return {"ok": True, "row": 33}
    b2 = BR2(clients=[RENT_ROW]); b2.closed = b.closed
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b2, None))
    assert getattr(b2, "booked", None), "«да» при живой карточке брони по-прежнему ставит бронь"
    assert b2.closed == [], "закрытие НЕ перехватывает «да» у карточки брони"

# ---- приоритет «да»: активация выдачи (4) выигрывает у закрытия (5); карточка приёма остаётся ждать ----
def test_activation_priority_over_close():
    reset(); b = FakeBridge(clients=[RENT_ROW])
    do_return(b)
    b.activated = []
    def fake_activate(bike, name, date_start=None):
        b.activated.append({"bike": bike, "name": name}); return {"ok": True, "row": 17}
    b.activate_booking = fake_activate
    S._HANDOVER_ACTIVATIONS[INTAKE] = {"bike": BIKE, "name": "Пётр", "date_start": "",
                                       "row": 17, "ts": S._time.time(), "status": "awaiting"}
    run(S._handle_intake(Msg("да", chat_id=INTAKE, uname="deramor"), Ctx(), b, None))
    assert b.activated and b.closed == [], "«да» при живой карточке активации идёт активации, не закрытию"
    assert S._RETURN_CLOSES[INTAKE]["status"] == "awaiting", "карточка приёма остаётся ждать своего «да»"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов карточки приёма (O3-3b фаза II)")
