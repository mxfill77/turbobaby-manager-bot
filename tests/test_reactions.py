"""Моки ПАКЕТ Б — анти-спам карточки + RETURN-контекст (приёмка vs ремонт).
Сеть/LLM/_send замоканы. Проверяет: карточка только при обращении/явном запросе + троттл;
возврат гасит phase-1 intake и repair-наряд, ведёт closing_upsert."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 8358
BIKE = "XMAX 300CC NEW BLUE-3 PHUKET 8358"

class U:
    def __init__(self, uname="extthiwxer", is_bot=False): self.username = uname; self.is_bot = is_bot

class Msg:
    def __init__(self, text, uname="extthiwxer", reply_to=None):
        self.text = text; self.caption = None; self.photo = None
        self.chat_id = CHAT; self.message_thread_id = TOPIC
        self.date = datetime.datetime(2026, 6, 24, 8, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 555; self.from_user = U(uname); self.reply_to_message = reply_to

class Ctx:
    class _B:
        username = "turbobaby_manager_bot"
    bot = _B()

class FakeClaude:
    def __init__(self, parsed): self._p = parsed
    def quick(self, system, text, max_tokens=300):
        if system == S.TRANSLATE_RU_TH: return "รับเรื่องแล้วครับ"
        return json.dumps(self._p)
    def vision(self, *a, **k): return "{}"

class FakeBridge:
    def __init__(self, status=""):
        self.status = status
        self.sp = None; self.closing = []; self.events = []; self.pending_ups = []
    def find_bike(self, q): return {"name": BIKE, "status": self.status, "oil_last_km": 20000}
    def service_pending_get(self, *a, **k): return {"ok": False, "error": "not_found"}
    def service_pending_upsert(self, **kw): self.pending_ups.append(kw); self.sp = kw; return {"ok": True, "status": kw.get("status")}
    def service_list(self, *a, **k): return {"items": []}
    def add_event(self, **kw): self.events.append(kw); return {"ok": True, "saved": True}
    def closing_upsert(self, **kw): self.closing.append(kw); return {"ok": True, "total_due": 0}
    def service_upsert(self, **kw): return {"ok": True, "next_km": 0, "status": "ok", "km_left": 0}

CARDS, SENDS, SVC_COL = [], [], []
async def rec_card(context, bridge, chat_id, topic_id, bike): CARDS.append(bike)
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append(text)
async def rec_svc_col(context, chat_id, topic_id, bike, kind, km): SVC_COL.append(kind)
async def rec_dl(pm): return None
S._send_bike_card = rec_card; S._send = rec_send; S._ask_service_col = rec_svc_col; S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)

def reset():
    CARDS.clear(); SENDS.clear(); SVC_COL.clear()
    S._CARD_LAST.clear(); S._ODOMETER_ASK_TS.clear(); S._PENDING_WORKS.clear()

def run(coro): return asyncio.run(coro)

# ============ БАГ1: анти-спам карточки ============
def test_card_helpers():
    assert S._is_explicit_status_query("статус") is True
    assert S._is_explicit_status_query("инфо по байку") is True
    assert S._is_explicit_status_query("ребята когда вернётся не помню какой там статус слесаря") is False  # >30, не запрос
    # «инф» убрано: «конференция» не должна цеплять статус (нет «инфо» в начале)
    assert S._is_status_request("конференция завтра") is False

def test_card_not_on_untargeted_chatter():
    reset()
    # короткая реплика со статус-словом, НО к боту не обращаются и это не явный запрос (в середине)
    run(S._handle_servicing(Msg("да там статус норм вроде"), Ctx(), FakeBridge(), FakeClaude({"type": "none"})))
    assert CARDS == [], "карточка НЕ должна слаться на нетаргетный трёп"

def test_card_on_addressed_and_throttle():
    reset()
    # обращение к боту (тег) + статус → карточка ОДИН раз
    run(S._handle_servicing(Msg("@turbobaby_manager_bot статус"), Ctx(), FakeBridge(), FakeClaude({"type": "none"})))
    assert CARDS == [BIKE], CARDS
    # второй раз в окне троттла → подавлено
    run(S._handle_servicing(Msg("@turbobaby_manager_bot статус"), Ctx(), FakeBridge(), FakeClaude({"type": "none"})))
    assert CARDS == [BIKE], "троттл должен подавить вторую карточку"

def test_card_on_reply_to_bot():
    reset()
    run(S._handle_servicing(Msg("статус", reply_to=Msg("", uname="turbobaby_manager_bot")), Ctx(), FakeBridge(), FakeClaude({"type": "none"})))
    assert CARDS == [BIKE], "реплай на бота = обращение"

# ============ БАГ2: RETURN-контекст ============
def test_return_context_detection():
    b_rented = FakeBridge(status="В аренде")
    b_home = FakeBridge(status="ДОМА")
    assert S._is_return_context({"event_type": "return"}, "", {}, b_home, BIKE) is True
    assert S._is_return_context({"event_type": "other"}, "клиент вернул байк", {}, b_home, BIKE) is True
    # intake + damage + В аренде → возврат (CRM-сигнал)
    assert S._is_return_context({"event_type": "intake"}, "привезли", {"damage": "скол"}, b_rented, BIKE) is True
    # intake на масло, байк НЕ в аренде → НЕ возврат
    assert S._is_return_context({"event_type": "intake"}, "привёз на масло", {}, b_home, BIKE) is False

def test_return_suppresses_phase1_and_does_closing():
    reset()
    b = FakeBridge(status="В аренде")
    # возврат: event_type=return, есть топливо+пробег
    run(S._handle_servicing(Msg("8358 вернулся, бензин полный, пробег 57186"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "return", "bike": BIKE,
                                        "fuel": "полный", "mileage": "57186", "works": []})))
    assert b.pending_ups == [], "phase-1 заявка НЕ должна создаваться на возврате"
    assert len(b.closing) == 1, "должна быть запись в лист закрытия (приёмка)"
    assert any("Pleummmm" in s or "возврат" in s.lower() for s in SENDS), "пинг приёмки Пыму"

def test_intake_oil_still_creates_phase1():
    reset()
    b = FakeBridge(status="ДОМА")
    run(S._handle_servicing(Msg("привёз байк на замену масла и редуктора"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "intake", "bike": BIKE,
                                        "works": ["замена масла", "масло в редукторе"]})))
    assert len(b.pending_ups) >= 1 and b.pending_ups[0].get("status") == "заявлено", b.pending_ups
    assert b.closing == [], "плановый intake НЕ должен трогать лист закрытия"

def test_return_suppresses_repair_order():
    reset()
    b = FakeBridge(status="В аренде")
    # возврат с упоминанием работ + пробег → repair-наряд (кнопки группы B) НЕ должен сработать
    run(S._handle_servicing(Msg("клиент вернул байк, на пробеге 57186, надо колодки и цепь глянуть"), Ctx(), b,
                            FakeClaude({"type": "event", "event_type": "other", "bike": BIKE,
                                        "mileage": "57186", "works": ["задние колодки", "регулировка цепи"]})))
    assert SVC_COL == [], "на возврате repair-наряд (фиксация группы B) гасится"
    assert len(b.closing) == 1, "возврат → лист закрытия"

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов реакций (пакет Б)")
