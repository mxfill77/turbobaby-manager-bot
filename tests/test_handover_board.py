"""Моки ТАБЛО ВЫДАЧИ (Delivery, слой 1 O3) — упрощённый флоу БЕЗ переспроса.
ОДНА бронь = ОТДЕЛЬНАЯ КАРТОЧКА (отдельный пост) с данными брони + её 2 кнопки: «✅ Выдан» и «🔁 Другой».
Проверяет: N броней → N карточек + шапка дня, «Выдан»→state_set 1 раз+разъём 💵 (без переспроса, новым сообщением),
«Другой»→список байков дома кнопками→pick→замена байка+state, pay не пишет, устаревший токен, тест-режим/префикс."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S


class FakeBridge:
    def __init__(self): self.state_calls = []
    def _call(self, action, **kw):
        if action == "clients":
            t = S._hb_phuket("%Y-%m-%d")
            return {"ok": True, "data": {"clients": [
                {"status": "Бронь", "bike": "NMAX 4957", "name": "Ivan",
                 "date_start": t + " 12:00", "date_end": "2026-07-05 13:00", "booking_id": "B1"},
                {"status": "Бронь", "bike": "PCX 1122", "name": "Anna",
                 "date_start": t + " 09:00", "date_end": "2026-07-03 10:00", "booking_id": "B2"},
                {"status": "В аренде", "bike": "XMAX 7777", "name": "Old",
                 "date_start": t + " 08:00", "date_end": "2026-07-01", "booking_id": "B3"},   # не бронь → фильтр
                {"status": "Бронь", "bike": "ADV 3030", "name": "Late",
                 "date_start": "2026-06-01 10:00", "date_end": "x", "booking_id": "B4"},        # не сегодня → фильтр
            ]}}
        return {"ok": True, "data": {}}
    def fleet(self):
        return {"ok": True, "data": {"bikes": [
            {"name": "CB 300CC R 9011", "status": "ДОМА"},
            {"name": "FORZA 350 5050", "status": "ДОМА"},
            {"name": "NINJA 400 8080", "status": "В аренде"},   # не дома → не кандидат
        ]}}
    def find_bike(self, q): return {"name": str(q) + " CANON"}
    def state_set(self, **kw): self.state_calls.append(kw); return {"ok": True}


class SentMsg:
    def __init__(s, mid): s.message_id = mid
class FakeBot:
    def __init__(s): s.sent = []
    async def send_message(s, **kw): s.sent.append(kw); return SentMsg(1000 + len(s.sent))
class FakeCtx:
    def __init__(s): s.bot = FakeBot()
class FakeUser:
    def __init__(s, uname="extthiwxer"): s.username = uname; s.first_name = "Taec"
class FakeMsg:
    def __init__(s, text=""): s.text = text; s.message_id = 555
class FakeQuery:
    def __init__(s, data, text="🛵 карточка"):
        s.data = data; s.from_user = FakeUser(); s.message = FakeMsg(text)
        s.answers = []; s.edits = []
    async def answer(s, text=None): s.answers.append(text)
    async def edit_message_text(s, text=None, reply_markup=None):
        s.message.text = text; s.edits.append((text, reply_markup))
    async def edit_message_reply_markup(s, reply_markup=None): s.edits.append((None, reply_markup))
class FakeUpdate:
    def __init__(s, q): s.callback_query = q


def _cbs(markup):
    if markup is None: return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]

def _reset():
    S._HB_TOKENS.clear(); S._HB_SEQ[0] = 0
    S.HB_TEST_MODE = False   # 6 тестов ниже — БОЕВОЙ путь (clients/fleet/find_bike)

def _cards(ctx):
    """Карточки = сообщения С кнопками (шапка дня — без кнопок, не карточка)."""
    return [m for m in ctx.bot.sent if m.get("reply_markup") is not None]

def _post_board(br, ctx):
    asyncio.run(S.hb_post_board(ctx, br))
    return _cards(ctx)

def _hand_tok(markup):
    # карточка одной брони = [✅ Выдан (hand)], [🔁 Другой (other)] → берём hand-токен
    return int([c for c in _cbs(markup) if c.startswith("delivery:hand:")][0].split(":")[2])

def _first_tok(cards):
    return _hand_tok(cards[0]["reply_markup"])


def test_board_separate_cards():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    cards = _post_board(br, ctx)
    assert len(cards) == 2, f"2 брони = 2 ОТДЕЛЬНЫЕ карточки, а {len(cards)}"   # XMAX/ADV отсеяны
    for m in cards:
        cbs = _cbs(m["reply_markup"])
        assert len(cbs) == 2, f"под карточкой ровно 2 кнопки (✅ + 🔁), а {len(cbs)}"
        assert sum(c.startswith("delivery:hand:") for c in cbs) == 1, cbs
        assert sum(c.startswith("delivery:other:") for c in cbs) == 1, cbs
        kb = m["reply_markup"].inline_keyboard
        assert kb[0][0].text.startswith("✅ "), "кнопка выдачи = эмодзи+данные её байка"
        assert kb[1][0].text == "🔁", "под ней голая 🔁 (подмена ЭТОГО байка)"
        assert "Выдача" in m["text"] and "Оплата" not in m["text"], m["text"]
    # шапка дня — ПЕРВЫМ сообщением, БЕЗ кнопок, с числом выдач
    header = ctx.bot.sent[0]
    assert header.get("reply_markup") is None, "шапка дня без кнопок"
    assert "Выдачи на сегодня" in header["text"] and "(2)" in header["text"], header["text"]

def test_hand_direct_state_once_money_no_reask():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    n_before = len(ctx.bot.sent)
    q = FakeQuery(f"delivery:hand:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(q), ctx, br))
    assert len(br.state_calls) == 1, f"state_set ровно 1 раз (без переспроса), а {len(br.state_calls)}"
    c = br.state_calls[0]
    assert c["status"] == "в аренде" and c["bike"] == "NMAX 4957 CANON" and c["client"] == "Ivan" and c["booking_id"] == "B1", c
    assert len(ctx.bot.sent) == n_before + 1, "подтверждение — НОВЫМ сообщением (доску не редактируем)"
    conf = ctx.bot.sent[-1]
    assert "выдал клиенту" in conf["text"] and "Пхукет" in conf["text"], conf["text"]
    assert _cbs(conf["reply_markup"]) == [f"delivery:pay:{tok}"], "разъём 💵 после выдачи"
    # переспроса «он/другой» НЕТ:
    assert "или другой?" not in conf["text"], conf["text"]

def test_other_then_pick_replaces_bike():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    qo = FakeQuery(f"delivery:other:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qo), ctx, br))
    lst = ctx.bot.sent[-1]                      # список замены — НОВЫМ сообщением
    pick_cbs = _cbs(lst["reply_markup"])
    assert pick_cbs == [f"delivery:pick:{tok}:0", f"delivery:pick:{tok}:1", f"delivery:back:{tok}"], pick_cbs  # 2 байка ДОМА + Назад
    assert all(c for c in [lst["reply_markup"].inline_keyboard[0][0].text]), "кнопка замены не пустая"
    assert lst["reply_markup"].inline_keyboard[0][0].text.startswith("✅ "), "кнопка замены = ✅ + данные"
    assert br.state_calls == [], "до выбора байка state_set не вызывается"
    qp = FakeQuery(f"delivery:pick:{tok}:1")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qp), ctx, br))
    assert len(br.state_calls) == 1, br.state_calls
    c = br.state_calls[0]
    assert c["bike"] == "FORZA 350 5050 CANON", c       # выбран кандидат idx1
    assert c["client"] == "Ivan" and c["booking_id"] == "B1", "бронь та же, сменился только байк"
    assert _cbs(qp.edits[-1][1]) == [f"delivery:pay:{tok}"], "разъём 💵 после выдачи (правка списка-сообщения)"

def test_back_cancels_no_write():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:other:{tok}")), ctx, br))  # открыли список замены
    assert any(c == f"delivery:back:{tok}" for c in _cbs(ctx.bot.sent[-1]["reply_markup"])), "на списке есть ◀️ Назад"
    qb = FakeQuery(f"delivery:back:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qb), ctx, br))
    assert br.state_calls == [], "Назад до выдачи — чистая отмена, ничего не пишет"
    last_text, last_kb = qb.edits[-1]
    assert last_kb is None, "кнопки убраны после Назад"
    assert "Замена отменена" in (last_text or ""), last_text

def test_pay_inactive_no_write():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:hand:{tok}")), ctx, br))
    n = len(br.state_calls)
    qp = FakeQuery(f"delivery:pay:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qp), ctx, br))
    assert len(br.state_calls) == n, "денежный разъём НЕ активен — ничего не пишет"
    assert any("следующий слой" in (a or "").lower() for a in qp.answers), qp.answers

def test_stale_token_graceful():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    q = FakeQuery("delivery:hand:999999")
    asyncio.run(S.handle_delivery_button(FakeUpdate(q), ctx, br))
    assert br.state_calls == [], "устаревший токен ничего не пишет"
    assert any("устарела" in (t or "") for t, _ in q.edits), q.edits

def test_zz_test_mode_hq_mock_prefix():
    _reset(); S.HB_TEST_MODE = True
    br = FakeBridge(); ctx = FakeCtx()
    try:
        cards = _post_board(br, ctx)
        assert len(cards) == 3, f"3 выдуманные брони = 3 ОТДЕЛЬНЫЕ карточки, а {len(cards)}"
        for m in cards:
            assert m["chat_id"] == S.HB_TEST_CHAT_ID, "тест-карточки в HQ"
            assert "ТЕСТ" in m["text"]
            assert len(_cbs(m["reply_markup"])) == 2, "под каждой карточкой 2 кнопки (✅ + 🔁)"
        assert ctx.bot.sent[0]["chat_id"] == S.HB_TEST_CHAT_ID, "шапка дня тоже в HQ"
        tok = _first_tok(cards)
        asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:hand:{tok}")), ctx, br))
        assert len(br.state_calls) == 1, br.state_calls
        assert br.state_calls[0]["bike"].startswith("🧪ТЕСТ "), br.state_calls[0]
        assert _cbs(ctx.bot.sent[-1]["reply_markup"]) == [f"delivery:pay:{tok}"]
    finally:
        S.HB_TEST_MODE = False


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов табло выдачи (слой 1 O3, упрощённый флоу)")
