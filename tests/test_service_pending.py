"""Моки двухфазного сервисного потока ТО (заявка→факт→«да» доверенного).
Сеть/Bridge/claude/_send замоканы. Покрывает: declared-парсер, фаза1 intake, фаза2 резолвер
(переспрос/готово), запись по «да» (диспетчер kind→экшен), trust-гейт кнопки. trust НЕ ослаблен."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 308
BIKE = "XMAX 300CC NEW BLUE-3 PHUKET 4724"

class Msg:
    def __init__(self, text, uname="extthiwxer"):
        self.text = text; self.caption = None; self.photo = None
        self.chat_id = CHAT; self.message_thread_id = TOPIC
        self.date = datetime.datetime(2026, 6, 20, 7, 52, tzinfo=datetime.timezone.utc)
        self.message_id = 9594
        self.from_user = type("U", (), {"username": uname})()

class FakeClaude:
    def __init__(self, parsed): self._parsed = parsed
    def quick(self, system, text, max_tokens=300): return json.dumps(self._parsed)
    def vision(self, *a, **k): return "{}"

class FakeBridge:
    """Эмулирует «то_заявки» (один слот) + set_fleet_* / service_upsert / add_event / find_bike."""
    def __init__(self):
        self.sp = None; self.closed = False
        self.oil_calls = []; self.svc_calls = []; self.upserts = []; self.events = []
    # --- то_заявки ---
    def service_pending_get(self, chat_id, topic_id, bike):
        if self.sp and not self.closed:
            return {"ok": True, "item": dict(self.sp)}
        return {"ok": False, "error": "not_found"}
    def service_pending_upsert(self, **kw):
        if self.sp is None: self.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": ""}
        for k, v in kw.items():
            if v not in (None, ""): self.sp[k] = v
        return {"ok": True, "status": self.sp.get("status")}
    def service_pending_close(self, **kw):
        self.closed = True; return {"ok": True}
    def service_pending_list(self, **kw):
        return {"ok": True, "items": ([self.sp] if (self.sp and not self.closed) else [])}
    # --- запись ---
    def set_fleet_oil(self, number, oil_km, confirmed=False):
        self.oil_calls.append((number, oil_km, confirmed)); return {"ok": True, "new_oil": oil_km}
    def set_fleet_service(self, number, kind, km, confirmed=False):
        self.svc_calls.append((number, kind, km, confirmed)); return {"ok": True, "new_km": km}
    def service_upsert(self, **kw): self.upserts.append(kw); return {"ok": True, "next_km": 24316, "status": "ok"}
    def add_event(self, **kw): self.events.append(kw); return {"ok": True, "saved": True}
    def find_bike(self, q): return {"name": BIKE}

SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **kw): SENDS.append(text)
async def rec_dl(pm): return None
S._send = rec_send; S._download_photo = rec_dl

def reset():
    SENDS.clear(); S._SVC_TOKENS.clear(); S._AWAITING_REPLY.clear()
    S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear(); S._ODOMETER_ASK_TS.clear()
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE

def run(coro): return asyncio.run(coro)

# ============ A) declared-парсер ============
def test_declared_from_works():
    got = S._declared_kinds("", ["замена моторного масла", "масло в редукторе", "масляный фильтр"], {})
    assert set(got) == {"oil", "gear", "filter"}, got
    assert got[0] == "oil"

def test_declared_from_text():
    got = S._declared_kinds("привёз на масло, фильтр и редуктор", [], {})
    assert set(got) == {"oil", "gear", "filter"}, got

def test_declared_gear_only_text_adds_oil_marker():
    # «масло в редукторе» → gear + oil-кандидат (declared информативен)
    got = S._declared_kinds("масло в редукторе", [], {})
    assert "gear" in got and "oil" in got, got

# ============ B) ФАЗА 1: intake создаёт заявку, в Лист1 ничего ============
def test_phase1_intake_creates_pending():
    reset()
    b = FakeBridge()
    parsed = {"type": "event", "event_type": "intake", "bike": BIKE,
              "works": ["замена моторного масла", "масло в редукторе", "масляный фильтр"]}
    run(S._handle_servicing(Msg("Я привёз байк на замену масла, фильтра и редуктора"),
                            context=None, bridge=b, claude=FakeClaude(parsed)))
    assert b.sp is not None and b.sp["status"] == "заявлено", b.sp
    assert "oil" in S._sp_split(b.sp["declared"]) and "gear" in S._sp_split(b.sp["declared"])
    assert not b.oil_calls and not b.svc_calls, "фаза1 НЕ должна писать в Лист1"
    assert any("Принял заявку" in s or "รับเรื่อง" in s for s in SENDS), SENDS

# ============ C) ФАЗА 2: резолвер ============
def test_phase2_no_done_asks():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear", "done": "", "status": "заявлено", "odometer": ""}
    handled = run(S.handle_service_result(Msg("ещё не закончил"), context=None, bridge=b,
                                          claude=FakeClaude({"works": [], "mileage": ""}), text="ещё не закончил"))
    assert handled is True
    assert b.sp["status"] == "ждёт_факт", b.sp
    assert any("что сделал" in s or "ทำอะไร" in s for s in SENDS), SENDS

def test_phase2_done_with_odo_requests_pym():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear,filter", "done": "", "status": "ждёт_факт", "odometer": ""}
    parsed = {"works": ["поменял моторное масло", "масло в редукторе"], "mileage": "20316"}
    handled = run(S.handle_service_result(Msg("готово, масло и редуктор, 20316"), context=None,
                                          bridge=b, claude=FakeClaude(parsed), text="готово, масло и редуктор, 20316"))
    assert handled is True
    assert b.sp["status"] == "ждёт_подтверждения", b.sp
    toks = [d for d in S._SVC_TOKENS.values() if d.get("kind") == "sp_done"]
    assert toks and set(toks[0]["done"]) >= {"oil", "gear"} and toks[0]["odo"] == "20316", toks
    assert any("@Pleummmm" in s for s in SENDS), SENDS

# ============ D) запись по факту: диспетчер kind→экшен ============
def test_sp_write_done_dispatch():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear,filter", "done": "oil,gear,filter",
                              "status": "ждёт_подтверждения", "odometer": "20316"}
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE, ["oil", "gear", "filter"], "20316", confirmed_by="@Pleummmm"))
    assert set(written) == {"oil", "gear", "filter"}, (written, failed)
    assert len(b.oil_calls) == 1 and b.oil_calls[0][1] == 20316 and b.oil_calls[0][2] is True
    assert len(b.svc_calls) == 1 and b.svc_calls[0][1] == "gear" and b.svc_calls[0][3] is True
    # фильтр → событие (регистра нет), oil+gear → синк обслуживания
    assert any(e.get("notes", "").startswith("масляный фильтр") for e in b.events), b.events
    assert {u["service_type"] for u in b.upserts} == {"oil", "gear"}, b.upserts
    assert b.closed is True

# ============ E) TRUST-ГЕЙТ кнопки (Earth сам нажать НЕ может) ============
class FakeQ:
    def __init__(self, data, uname):
        self.data = data; self.from_user = type("U", (), {"username": uname})()
        self.answered = []
    async def answer(self, *a, **k): self.answered.append(a)
    async def edit_message_reply_markup(self, **k): pass
    async def edit_message_text(self, *a, **k): pass

def _mk_update(q): return type("Upd", (), {"callback_query": q})()

def test_done_button_blocks_non_trusted():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear", "done": "oil,gear",
                              "status": "ждёт_подтверждения", "odometer": "20316"}
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE, "done": ["oil", "gear"], "odo": "20316", "kind": "sp_done"})
    run(S.handle_service_button(_mk_update(FakeQ(f"svc:done:{tok}", "extthiwxer")), context=None, bridge=b))
    assert not b.oil_calls and not b.svc_calls, "механик не доверенный — записи быть НЕ должно"
    assert tok in S._SVC_TOKENS, "токен должен жить (Пым нажмёт позже)"

def test_done_button_trusted_writes():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear", "done": "oil,gear",
                              "status": "ждёт_подтверждения", "odometer": "20316"}
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE, "done": ["oil", "gear"], "odo": "20316", "kind": "sp_done"})
    run(S.handle_service_button(_mk_update(FakeQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    assert len(b.oil_calls) == 1 and len(b.svc_calls) == 1, (b.oil_calls, b.svc_calls)
    assert b.closed is True
    assert tok not in S._SVC_TOKENS

# ============ F) ФИКСЫ B1-B6 (закрытие доходит до конца) ============
def _iso_ago(hours):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")

# B2: лексикон завершения (естественные слова) + защита от негатива
def test_b2_done_lexicon_and_negation():
    for w in ("готово", "закончили", "сделал", "поменял", "да", "เสร็จแล้ว", "เรียบร้อย", "ok"):
        assert S._is_done_marker(w), f"{w!r} — должно быть маркером завершения"
    for w in ("ещё не закончил", "пока не готово", "ยังไม่เสร็จ", "not done", "когда привезли", "сдал позже"):
        assert not S._is_done_marker(w), f"{w!r} — НЕ маркер (негатив/ложное срабатывание)"

# B3: declared не теряем, доп.работу добавляем («Закончили да и подшипник» при заявке pads)
def test_b3_declared_kept_plus_extra():
    reset()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "", "status": "ждёт_факт", "odometer": ""}
    msg = Msg("Закончили да и подшипник переднего колеса")
    handled = run(S.handle_service_result(msg, context=None, bridge=b,
                                          claude=FakeClaude({"works": ["подшипник переднего колеса"]}), text=msg.text))
    assert handled is True
    done = S._sp_split(b.sp["done"])
    assert "pads" in done and "other" in done, f"заявленное pads + доп. other, а {done}"
    assert not b.oil_calls and not b.svc_calls and not b.events, "до «да» Пыма в Лист1/события не пишем"

# B3: «готово» без перечня → заявленное считаем сделанным
def test_b3_bare_done_means_declared():
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil", "done": "", "status": "ждёт_факт", "odometer": ""}
    run(S.handle_service_result(Msg("готово"), context=None, bridge=b, claude=FakeClaude({}), text="готово"))
    assert "oil" in S._sp_split(b.sp["done"]), f"«готово» → заявленное (oil) сделано, а {b.sp['done']!r}"

# B1: подтверждённый ФОТО-одометр доводит заявку до подтверждения Пыму (запись — по гейту)
def test_b1_photo_odometer_advances():
    reset(); S._SP_LAST_SENT.clear(); S._PENDING_MILEAGE.clear()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "pads,other", "status": "ждёт_факт", "odometer": "", "bike": BIKE}
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = ("24302", BIKE, None, False)
    handled = run(S.handle_mileage_confirm(Msg("да"), context=None, bridge=b, text="да"))
    assert handled is True
    assert b.sp["status"] == "ждёт_подтверждения" and b.sp["odometer"] == "24302", b.sp
    toks = [d for d in S._SVC_TOKENS.values() if d.get("kind") == "sp_done"]
    assert toks and toks[0]["odo"] == "24302", toks
    assert not b.oil_calls and not b.svc_calls and not b.closed, "запись/закрытие — ТОЛЬКО по «да» Пыма (гейт сохранён)"

# B4: TTL → ОДНА эскалация владельцу/Пыму, тайцам стоп
def test_b4_ttl_escalates_once():
    reset(); S._SP_LAST_SENT.clear()
    import notify
    _orig = notify.notify; cnt = {"n": 0}
    notify.notify = lambda *a, **k: (cnt.__setitem__("n", cnt["n"] + 1), True)[1]
    try:
        b = FakeBridge()
        b.sp = {"created_at": _iso_ago(100), "updated_at": _iso_ago(7), "chat_id": CHAT, "topic_id": TOPIC,
                "bike": BIKE, "declared": "pads", "status": "ждёт_факт", "last_reminded_at": "", "note": ""}
        run(S.scheduled_service_pending_reminder(None, b))
        assert cnt["n"] == 1, "эскалация владельцу ровно ОДИН раз"
        assert "escalated" in str(b.sp.get("note", "")), f"note помечен escalated, а {b.sp.get('note')!r}"
        assert not any("результат не отписан" in s for s in SENDS), "обычное напоминание тайцам после TTL НЕ шлём"
        run(S.scheduled_service_pending_reminder(None, b))     # повтор — уже escalated
        assert cnt["n"] == 1, "повторно НЕ эскалируем (тишина после первого раза)"
    finally:
        notify.notify = _orig

# B5: два близких тика в одном процессе → одно напоминание
def test_b5_inmemory_antidup():
    reset(); S._SP_LAST_SENT.clear()
    b = FakeBridge()
    b.sp = {"created_at": _iso_ago(8), "updated_at": _iso_ago(7), "chat_id": CHAT, "topic_id": TOPIC,
            "bike": BIKE, "declared": "pads", "status": "ждёт_факт", "last_reminded_at": _iso_ago(7), "note": ""}
    run(S.scheduled_service_pending_reminder(None, b))
    run(S.scheduled_service_pending_reminder(None, b))
    reminders = [s for s in SENDS if "результат не отписан" in s]
    assert len(reminders) == 1, f"два тика → одно напоминание, а {len(reminders)}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов двухфазного ТО")
