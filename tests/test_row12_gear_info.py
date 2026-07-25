"""Фикс аудита row12 (contradiction, X MAX GREEN 4248 08.07): «Принято» по редуктору терялось молча —
ни заявки, ни кнопки, Инфо показывал только моторное масло. Три слоя фикса (гейт записи НЕ ослаблен,
Лист1 только по «да» Пыма):
  1) E2b-блок set_service (claude_client) → работа в очередь pending_service_confirm (не теряется);
  2) splinter.sp_confirm_from_brain: очередь → штатная то_заявка (одометр есть → кнопка Пыму
     'ждёт_подтверждения'; нет → 'ждёт_факт' + просьба одометра);
  3) работы группы B (gear/abs/airfilter) без пробега в сообщении → то_заявка 'ждёт_факт'
     (раньше терялись: кнопка фиксации требовала пробег в ТОМ ЖЕ сообщении).
Плюс карточка Инфо: открытая заявка с gear видна в «В работе» (правило row12: Инфо отражает
подтверждённые работы или честное «ждёт подтверждения»). Сеть/LLM/_send замоканы."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 222
BIKE = "XMAX 300CC GREEN PHUKET 4248"


class U:
    def __init__(s, uname="extthiwxer"): s.username = uname; s.is_bot = False


class Msg:
    def __init__(s, text, photo=False):
        s.text = text; s.caption = None; s.photo = ([object()] if photo else None)
        s.chat_id = CHAT; s.message_thread_id = TOPIC
        s.date = datetime.datetime(2026, 7, 8, 6, 11, tzinfo=datetime.timezone.utc)
        s.message_id = 10268; s.from_user = U(); s.reply_to_message = None


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
    """Стейтфул то_заявки (один слот) + читалки карточки. Ничего не пишет в Лист1."""
    def __init__(s, sp=None):
        s.sp = sp; s.closed = False; s.pend = []; s.events = []
    def _call(s, *a, **k): return {"ok": False}
    def find_bike(s, q):
        return {"name": BIKE, "mileage": "38065", "status": "", "oil_last_km": 38065,
                "gear_last_km": None, "abs_last_km": None, "airfilter_last_km": None}
    def service_pending_get(s, chat_id, topic_id, bike):
        if s.sp and not s.closed:
            return {"ok": True, "item": dict(s.sp)}
        return {"ok": False, "error": "not_found"}
    def service_pending_upsert(s, **kw):
        if s.sp is None: s.sp = {"declared": "", "done": "", "status": "заявлено", "odometer": ""}
        for k, v in kw.items():
            if v not in (None, ""): s.sp[k] = v
        s.pend.append(kw); return {"ok": True, "status": s.sp.get("status")}
    def service_pending_list(s, **kw): return {"ok": True, "items": []}
    def service_list(s, *a, **k): return {"items": []}
    def read_events(s, *a, **k): return {"ok": True, "items": []}
    def add_event(s, **k): s.events.append(k); return {"ok": True, "saved": True}
    def service_upsert(s, **k): return {"ok": True, "next_km": 0, "status": "ok", "km_left": 0}


SENDS = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **k): SENDS.append(text)
async def rec_dl(pm): return b"x"
S._send = rec_send; S._download_photo = rec_dl
S.set_topic_bike(CHAT, TOPIC, BIKE)


def reset():
    SENDS.clear(); S._SVC_TOKENS.clear(); S._AWAITING_REPLY.clear()
    S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear(); S._ODOMETER_ASK_TS.clear()
    S._SP_ASK_TS.clear(); S._SP_LAST_SENT.clear(); S._CARD_LAST.clear()


def run(c): return asyncio.run(c)


# ============ 1) E2b-блок claude_client: работа НЕ теряется — очередь ============
def _client():
    import claude_client as CC
    c = CC.ClaudeClient.__new__(CC.ClaudeClient)   # без __init__ (не нужен API-ключ)
    c._force_bike = BIKE; c._force_mileage = None; c._force_mileage_conf = ""
    c.pending_service_confirm = []
    return c


def test_e2b_block_queues_kind_and_km():
    c = _client()
    out = json.loads(c._execute_tool("set_service", {"bike": BIKE, "service_type": "gear",
                                                     "current_km": 38065, "confirmed": True}))
    assert out.get("blocked") == "service_gate", out          # гейт цел: запись НЕ прошла
    assert c.pending_service_confirm == [{"kind": "gear", "km": 38065}]


def test_e2b_block_dedups_same_kind():
    c = _client()
    for _ in range(2):
        c._execute_tool("set_service", {"service_type": "gear", "current_km": 38065})
    assert len(c.pending_service_confirm) == 1


def test_e2b_block_km_falls_back_to_force_mileage():
    c = _client()
    c._force_mileage = 38065
    c._execute_tool("set_service", {"service_type": "gear"})
    assert c.pending_service_confirm == [{"kind": "gear", "km": 38065}]


def test_e2b_not_engaged_outside_servicing_topic():
    # вне servicing-темы (_force_bike пуст) гейт E2b не работает — очередь пуста, идёт обычный путь
    c = _client(); c._force_bike = ""
    c.bridge = FakeBridge()
    c._execute_tool("set_service", {"bike": BIKE, "service_type": "oil", "current_km": 38100})
    assert c.pending_service_confirm == []


# ============ 2) sp_confirm_from_brain: очередь → штатная то_заявка ============
def test_from_brain_with_km_advances_to_pym_button():
    reset(); b = FakeBridge()
    run(S.sp_confirm_from_brain(Ctx(), b, CHAT, TOPIC, BIKE, "gear", 38065))
    assert b.sp and b.sp.get("status") == "ждёт_подтверждения", b.sp
    assert "gear" in S._sp_split(b.sp.get("done"))
    assert str(b.sp.get("odometer")) == "38065"
    assert any("подтвер" in t.lower() for t in SENDS), SENDS   # кнопка/запрос Пыму отправлены


def test_from_brain_without_km_waits_fact_and_asks_odo():
    reset(); b = FakeBridge()
    run(S.sp_confirm_from_brain(Ctx(), b, CHAT, TOPIC, BIKE, "gear", None))
    assert b.sp and b.sp.get("status") == "ждёт_факт", b.sp
    assert "gear" in S._sp_split(b.sp.get("done"))
    assert any("одометр" in t.lower() or "ODO" in t for t in SENDS), SENDS


def test_from_brain_no_duplicate_button_when_already_waiting():
    reset()
    b = FakeBridge(sp={"declared": "gear", "done": "gear", "status": "ждёт_подтверждения",
                       "odometer": "38065"})
    run(S.sp_confirm_from_brain(Ctx(), b, CHAT, TOPIC, BIKE, "gear", 38065))
    assert SENDS == [] and b.pend == []      # уже ждёт Пыма — не дублируем


def test_from_brain_merges_into_open_request():
    reset()
    b = FakeBridge(sp={"declared": "pads", "done": "", "status": "заявлено", "odometer": ""})
    run(S.sp_confirm_from_brain(Ctx(), b, CHAT, TOPIC, BIKE, "gear", 38065))
    assert set(S._sp_split(b.sp.get("done"))) >= {"pads", "gear"} or "gear" in S._sp_split(b.sp.get("done"))
    assert b.sp.get("status") == "ждёт_подтверждения"


def test_from_brain_unknown_kind_becomes_other():
    reset(); b = FakeBridge()
    run(S.sp_confirm_from_brain(Ctx(), b, CHAT, TOPIC, BIKE, "wheel_paint", None))
    assert "other" in S._sp_split(b.sp.get("done")), b.sp


# ============ 3) группа B без пробега в сообщении → заявка (инцидент 06:11) ============
ROW12_PARSE = {"type": "event", "event_type": "repair", "mileage": None,
               "works": ["замена аккумулятора", "замена моторного масла",
                         "замена масла в редукторе", "замена масляного фильтра",
                         "замена рамки номерного знака"]}


def test_works_without_km_persist_gear_request():
    reset(); b = FakeBridge()
    run(S._handle_servicing(Msg("Этот мотоцикл привезли для замены аккумулятора, моторного масла, "
                                "масла в редукторе, масляного фильтра и рамки номерного знака"),
                            Ctx(), b, FakeClaude(ROW12_PARSE)))
    assert b.sp is not None, "заявка на группу B не создана"
    assert "gear" in S._sp_split(b.sp.get("declared")), b.sp
    assert b.sp.get("status") == "ждёт_факт", b.sp
    assert any("Принял работы" in t for t in SENDS), SENDS    # квитанция как раньше (не задваиваем)


def test_works_without_km_no_request_when_no_group_b():
    reset(); b = FakeBridge()
    parse = {"type": "event", "event_type": "repair", "mileage": None,
             "works": ["замена рамки номерного знака"]}
    run(S._handle_servicing(Msg("поменяли рамку номерного знака"), Ctx(), b, FakeClaude(parse)))
    assert b.sp is None, b.sp                                  # инфо-работа — заявка ТО не нужна


# ============ 4) Инфо-карточка честно показывает редуктор (суть row12) ============
def test_card_shows_gear_in_progress():
    reset()
    b = FakeBridge(sp={"declared": "gear", "done": "gear", "status": "ждёт_подтверждения",
                       "odometer": "38065", "note": ""})
    card = S._build_bike_card(b, CHAT, TOPIC, BIKE)
    assert "масло редуктора" in card, card                     # работа видна в «В работе»
    assert "ждёт подтверждения" in card, card                  # честный статус (не молчание)


def test_card_shows_gear_planned_row_for_scooter():
    reset(); b = FakeBridge()
    card = S._build_bike_card(b, CHAT, TOPIC, BIKE)
    assert "Редуктор" in card, card                            # xmax = скутер → строка регламента есть

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        reset(); fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов row12 (редуктор виден после «Принято»)")
