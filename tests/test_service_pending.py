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
    S._SP_ASK_TS.clear(); S._SP_LAST_SENT.clear()   # E4/B5 in-memory троттлы — чистим между тестами
    S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = BIKE
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE

def run(coro): return asyncio.run(coro)

# ============ A) declared-парсер ============
def test_declared_from_works():
    # E3(a): «масляный фильтр» больше НЕ kind (невалиден) → только oil+gear
    got = S._declared_kinds("", ["замена моторного масла", "масло в редукторе", "масляный фильтр"], {})
    assert set(got) == {"oil", "gear"}, got
    assert got[0] == "oil"

def test_declared_from_text():
    # «фильтр» без «воздушн» больше не даёт filter-kind (масляного фильтра нет)
    got = S._declared_kinds("привёз на масло, фильтр и редуктор", [], {})
    assert set(got) == {"oil", "gear"}, got

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

def test_done_button_stale_answer_still_writes():
    # фикс 02.07 (паттерн _o3_answer из 749cf46): протухший q.answer (BadRequest «Query is too old»)
    # НЕ валит хендлер — запись по «да» доверенного всё равно проходит.
    reset()
    b = FakeBridge(); b.sp = {"declared": "oil,gear", "done": "oil,gear",
                              "status": "ждёт_подтверждения", "odometer": "20316"}
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE, "done": ["oil", "gear"], "odo": "20316", "kind": "sp_done"})
    class DeadQ(FakeQ):
        async def answer(self, *a, **k):
            raise Exception("Query is too old and response timeout expired or query id is invalid")
    run(S.handle_service_button(_mk_update(DeadQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    assert len(b.oil_calls) == 1 and len(b.svc_calls) == 1, (b.oil_calls, b.svc_calls)
    assert tok not in S._SVC_TOKENS, "токен снят — запись прошла до конца"

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


# G) ОБРАЩЕНИЕ К ТАЙЦАМ — ТОЛЬКО @username, без имени (правило 28.06)
def test_thai_handle_only_no_name():
    # единая точка
    assert S.PYM_HANDLE == "@Pleummmm" and S.THAI_HANDLES["pym"] == "@Pleummmm"
    # ключевые исходящие, адресующие/называющие тайца → @username, БЕЗ имени
    msgs = [
        S.msg_sp_confirm_pym("NMAX 4255", ["pads"], [], "24302"),
        S.msg_oil_need_trusted("NMAX 4255", "24302"),
        S.msg_topup_pettycash(500, {}),
        S.msg_reconcile("Самоорганизация", {}),
        S._SP_STATUS_RU["ждёт_подтверждения"],
        S._SP_STATUS_TH["ждёт_подтверждения"],
    ]
    for m in msgs:
        assert "@Pleummmm" in m, f"таец адресован через @username: {m[:70]!r}"
        for bad in ("Пым", "Earth", "พี่ Pleum"):
            assert bad not in m, f"имя тайца «{bad}» в исходящем тексте: {m!r}"


# ============ H) ФИКС КЛАССА B (E1-E4) ============
def test_e1_svc_done_confirm_survives_timeout():
    # E1: подтверждение svc:done через _send_retry — ConnectTimeout не теряет его, запись 1 раз.
    from telegram.error import TimedOut
    import asyncio as _a
    reset()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "pads", "status": "ждёт_подтверждения", "odometer": "24302"}
    tok = S._svc_put({"chat": CHAT, "topic": TOPIC, "bike": BIKE, "done": ["pads"], "odo": "24302", "kind": "sp_done"})
    calls = {"n": 0}; orig = S._send
    async def flaky(context, *, chat_id, text, message_thread_id=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimedOut("сетевой блип")
        SENDS.append(text)
    S._send = flaky
    orig_sleep = _a.sleep
    async def _nos(*a, **k): return None
    _a.sleep = _nos
    try:
        run(S.handle_service_button(_mk_update(FakeQ(f"svc:done:{tok}", "Pleummmm")), context=None, bridge=b))
    finally:
        S._send = orig; _a.sleep = orig_sleep
    assert calls["n"] >= 2, f"подтверждение переотправлено после TimedOut, попыток={calls['n']}"
    assert len(b.events) == 1 and b.closed, "_sp_write_done отработал РОВНО раз (pads→событие + close)"
    assert not b.oil_calls, "set_fleet_oil не зван (pads — событие)"

def test_e2b_brain_set_service_gated_in_servicing():
    # E2b: в servicing-теме (_force_bike) мозг НЕ пишет ТО — set_service возвращает advisory, не пишет.
    import claude_client
    b = FakeBridge()
    cc = claude_client.ClaudeClient(api_key="test", bridge=b, memory=None)
    cc._force_bike = BIKE
    out = cc._execute_tool("set_service", {"bike": BIKE, "service_type": "oil", "current_km": 24302, "confirmed": True})
    assert ("service_gate" in out or "blocked" in out), f"set_service должен быть заблокирован: {out[:80]}"
    assert b.upserts == [], "service_upsert НЕ должен быть вызван (мозг не пишет ТО в servicing)"

def test_e3_kind_validation():
    # E3(a): масляный фильтр невалиден; (e) воздушный→airfilter; подшипник→other.
    assert "filter" not in S._declared_kinds("заменил масляный фильтр", [], {}, strict_oil=True), "масляный фильтр — НЕ kind"
    assert "oil" not in S._declared_kinds("заменил масляный фильтр", [], {}, strict_oil=True), "масляный фильтр НЕ даёт oil"
    assert "airfilter" in S._declared_kinds("воздушный фильтр", [], {}), "воздушный фильтр → airfilter"
    assert S._service_kind("подшипник переднего колеса") == "other", "подшипник → other (не теряем)"
    # E3(b) ФАКТ (strict_oil): oil ТОЛЬКО при явной замене
    assert S._declared_kinds("колодки заменил", [], {}, strict_oil=True) == ["pads"], "колодки → только pads (без oil)"
    assert "oil" not in S._declared_kinds("масло в норме, ничего не трогал", [], {}, strict_oil=True), "мягкое масло ≠ oil (факт)"
    assert "oil" in S._declared_kinds("заменил моторное масло", [], {}, strict_oil=True), "явная замена масла → oil"
    # intake (нестрого): «привёз на масло» — oil как намерение сохраняется
    assert "oil" in S._declared_kinds("привёз на масло", [], {}), "intake: oil-намерение от явного слова масла"

def test_e3_write_done_no_false_oil():
    # E3(d): done=[pads,other] → 2 события, set_fleet_oil НЕ зван (в кол I не пишем не-регламент).
    reset()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "pads,other", "status": "ждёт_подтверждения", "odometer": "24302"}
    written, failed = run(S._sp_write_done(None, b, CHAT, TOPIC, BIKE, ["pads", "other"], "24302", confirmed_by="@Pleummmm"))
    assert len(b.events) == 2, f"pads+other → 2 события, а {len(b.events)}"
    assert not b.oil_calls and not b.svc_calls, "set_fleet_* НЕ зван (только события)"
    assert b.closed is True

def test_e4_ask_throttle():
    # E4(a): два сообщения подряд на ждёт_факт без факта → один переспрос (троттл), не плодим.
    reset(); S._SP_ASK_TS.clear()
    b = FakeBridge(); b.sp = {"declared": "oil,gear", "done": "", "status": "ждёт_факт", "odometer": ""}
    c = FakeClaude({"works": [], "mileage": ""})
    run(S.handle_service_result(Msg("ещё вожусь"), context=None, bridge=b, claude=c, text="ещё вожусь"))
    run(S.handle_service_result(Msg("почти"), context=None, bridge=b, claude=c, text="почти"))
    asks = [s for s in SENDS if "что сделал" in s or "ทำอะไร" in s]
    assert len(asks) == 1, f"два сообщения → один переспрос (троттл E4), а {len(asks)}"


# ============ I) ФИКС ЗАДВОЕНИЯ ИНФО-РАБОТ (msg_ask_odometer динамический) ============
def _th_no_cyrillic(m):
    import re as _re
    inth = False
    for ln in m.split("\n"):
        s = ln.lstrip()
        if s.startswith("🇷🇺"): inth = False
        if s.startswith("🇹🇭"): inth = True
        if inth and _re.search(r"[А-Яа-яЁё]", ln):
            return False
    return True

def test_ask_odometer_dynamic_text():
    # (b) текст ПО ФАКТУ работ, без хардкод-«масло»; 🇹🇭 без кириллицы
    m = S.msg_ask_odometer("NMAX 4255", ["pads"])
    assert "тормозные колодки" in m and "масл" not in m.lower(), m
    assert "Вижу замену масла" not in m, m
    assert _th_no_cyrillic(m), "🇹🇭 без кириллицы (работы тайскими лейблами)"
    m2 = S.msg_ask_odometer("NMAX 4255")   # без kinds → нейтрально
    assert "масл" not in m2.lower() and ("ODO" in m2 or "пробег" in m2.lower()), m2
    m3 = S.msg_ask_odometer("NMAX 4255", ["oil"])   # oil-контекст корректен
    assert "моторное масло" in m3, m3

def test_ask_odometer_in_phase2_names_works_not_oil():
    # НЕ регресс: двухфазный переспрос одометра по работам заявки (колодки) → НЕ «масло»
    reset()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "", "status": "ждёт_факт", "odometer": ""}
    run(S.handle_service_result(Msg("колодки заменил"), context=None, bridge=b,
                                claude=FakeClaude({"works": ["замена колодок"], "mileage": ""}), text="колодки заменил"))
    asks = [s for s in SENDS if "пробег" in s.lower() or "ODO" in s]
    assert asks, "переспрос одометра отправлен"
    assert "тормозные колодки" in asks[-1] and "Вижу замену масла" not in asks[-1], asks[-1]


# ============ J) КЛАСС-ФИКС кнопочных подтверждений (ConnectTimeout) ============
def test_emit_summary_retry_survives_timeout():
    # (1) сводка-квитанция после кнопки переживает TimedOut (_send_retry) — не тишина
    from telegram.error import TimedOut
    import asyncio as _a
    reset()
    S._SVC_SUMMARY[(CHAT, TOPIC)] = {"works": ["замена колодок", "замена переднего подшипника"], "current_km": "24302"}
    calls = {"n": 0}; orig = S._send
    async def flaky(context, *, chat_id, text, message_thread_id=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimedOut("сетевой блип")
        SENDS.append(text)
        return type("M", (), {"message_id": 1})()
    S._send = flaky
    orig_sleep = _a.sleep
    async def _nos(*a, **k): return None
    _a.sleep = _nos
    try:
        res = run(S._emit_summary(None, CHAT, TOPIC, BIKE))
    finally:
        S._send = orig; _a.sleep = orig_sleep
    assert calls["n"] >= 2, f"сводка переотправлена после TimedOut, попыток={calls['n']}"
    assert res is not None and any("24302" in s for s in SENDS), "квитанция доставлена (не тишина)"

def test_svc_mok_button_advances_open_request():
    # (2) B1-хук в КНОПОЧНОМ svc:mok: открытая ждёт_факт заявка → доведена до кнопки Пыма, БЕЗ записи в Лист1
    reset()
    b = FakeBridge(); b.sp = {"declared": "pads", "done": "", "status": "ждёт_факт", "odometer": ""}
    tok = S._svc_put({"kind": "mileconf", "chat": CHAT, "topic": TOPIC, "bike": BIKE,
                      "mileage": "24302", "floor": None, "oil_hint": False})
    run(S.handle_service_button(_mk_update(FakeQ(f"svc:mok:{tok}", "earthmechanic")), context=None, bridge=b))
    assert b.sp["status"] == "ждёт_подтверждения" and str(b.sp.get("odometer")) == "24302", b.sp
    assert any(d.get("kind") == "sp_done" for d in S._SVC_TOKENS.values()), "кнопка Пыму (svc:done) создана"
    assert not b.oil_calls and not b.svc_calls, "в Лист1 НЕ пишем (гейт Пыма сохранён)"

def test_summary_names_works_or_neutral():
    # (3) квитанция называет записанные работы; без работ — нейтральная (пробег)
    m = S.msg_service_summary(BIKE, {"works": ["замена колодок", "замена переднего подшипника"], "current_km": "24302"})
    assert "колод" in m.lower() and "подшип" in m.lower() and "24302" in m, m
    m2 = S.msg_service_summary(BIKE, {"current_km": "24302", "oil": {"km": "24302", "next": 28094, "status": "ok"}})
    assert "24302" in m2 and "колод" not in m2.lower(), m2


# ============ K) ФИКС A — дедуп ТО-событий (идемпотентность + рендер) ============
def test_a_work_stem_stable():
    assert S._work_stem("замена колодок") == S._work_stem("колодки") == S._work_stem("тормозные колодки") == "колодки"
    assert S._work_stem("замена переднего подшипника") == S._work_stem("подшипник") == "подшипник"
    assert S._work_stem("регулировка цепи") == "цепь"

def test_a1_write_idempotent_content_msgid():
    # A1: msg_id по контенту info:plate:стем:км → повторный прогон (др.формулировка) = тот же ключ
    reset()
    b = FakeBridge()
    S._write_info_works(b, "обслуживание", TOPIC, "NMAX 4255", ["замена колодок", "замена переднего подшипника"], "24302", "base:1")
    mids1 = [e["msg_id"] for e in b.events]
    assert mids1 == ["info:4255:колодки:24302", "info:4255:подшипник:24302"], mids1
    n = len(b.events)
    S._write_info_works(b, "обслуживание", TOPIC, "NMAX 4255", ["колодки", "подшипник переднего колеса"], "24302", "base:2")
    assert [e["msg_id"] for e in b.events[n:]] == mids1, "повторный прогон → ТЕ ЖЕ ключи (Bridge задедупит)"
    S._write_info_works(b, "обслуживание", TOPIC, "NMAX 4255", ["замена колодок"], "30000", "b3")
    assert b.events[-1]["msg_id"] == "info:4255:колодки:30000", "разный км → разный ключ"
    S._write_info_works(b, "обслуживание", TOPIC, "PCX 1122", ["замена колодок"], "24302", "b4")
    assert b.events[-1]["msg_id"] == "info:1122:колодки:24302", "разный plate → разный ключ"

def test_a2_render_dedup_by_work_km():
    # A2: дедуп карточки по (стем-работы, км) — точный повтор один раз; разные км — обе
    items = [{"notes": "замена колодок — 24302 км"}, {"notes": "замена переднего подшипника — 24302 км"},
             {"notes": "замена колодок — 24302 км"}, {"notes": "замена переднего подшипника — 24302 км"}]
    out = S._parse_service_items(items, limit=6)
    assert len(out) == 2 and {o["work"] for o in out} == {"замена колодок", "замена переднего подшипника"}, out
    out2 = S._parse_service_items([{"notes": "замена колодок — 24302 км"}, {"notes": "замена колодок — 30000 км"}], limit=6)
    assert len(out2) == 2, "та же работа на РАЗНЫХ км → обе (реальная история)"


# ============ L) ФИКС C — тайский словарь работ (подшипник + родительный колодок) ============
def test_c_work_th_bearing_and_pads():
    import re as _re
    # подшипник больше не «งานอื่น ๆ»
    assert S._work_th("замена переднего подшипника") == "ลูกปืนล้อหน้า", S._work_th("замена переднего подшипника")
    assert S._work_th("подшипник переднего колеса") == "ลูกปืนล้อหน้า"
    assert S._work_th("замена заднего подшипника") == "ลูกปืนล้อหลัง"
    assert S._work_th("подшипник") == "ลูกปืน"
    # колодки (вкл. родительный «колодок») → ผ้าเบรก, не «งานอื่น ๆ»
    assert S._work_th("замена колодок") == "ผ้าเบรก", S._work_th("замена колодок")
    assert S._work_th("тормозные колодки") == "ผ้าเบรก"
    assert S._work_th("регулировка цепи") == "ปรับโซ่"
    # 🇹🇭 без кириллицы во всех ответах
    for w in ("замена переднего подшипника", "замена колодок", "подшипник", "งานอื่น"):
        assert not _re.search(r"[А-Яа-яЁё]", S._work_th(w)), f"кириллица в TH-лейбле для {w!r}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов двухфазного ТО")
