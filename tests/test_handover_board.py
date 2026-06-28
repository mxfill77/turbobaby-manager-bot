"""Моки ТАБЛО ВЫДАЧИ (Delivery, слой 1 O3) — упрощённый флоу БЕЗ переспроса.
Доска: под каждой бронью 2 кнопки в ряд — «✅ Выдан» (выдать плановый СРАЗУ) и «🔁 Другой» (подмена).
Проверяет: доска 2 кнопки/бронь, «Выдан»→state_set 1 раз+разъём 💵 (без переспроса, новым сообщением),
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

def _post_board(br, ctx):
    asyncio.run(S.hb_post_board(ctx, br))
    return ctx.bot.sent[-1]["reply_markup"]

def _hand_tok(markup):
    # первая строка доски = [✅ Выдан (hand), 🔁 Другой (other)] → берём hand-токен
    return int([c for c in _cbs(markup) if c.startswith("delivery:hand:")][0].split(":")[2])


def test_board_two_buttons_per_booking():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    mk = _post_board(br, ctx)
    cbs = _cbs(mk)
    assert len(cbs) == 4, f"2 брони × 2 кнопки = 4, а {len(cbs)}"   # XMAX/ADV отсеяны
    assert sum(c.startswith("delivery:hand:") for c in cbs) == 2, cbs
    assert sum(c.startswith("delivery:other:") for c in cbs) == 2, cbs
    body = ctx.bot.sent[-1]["text"]
    assert "Выдачи на сегодня" in body and "Другой байк" in body   # легенда: ✅ и 🔁 (без 💵)
    assert "Оплата" not in body, "на доске 💵 в легенде быть НЕ должно"

def test_hand_direct_state_once_money_no_reask():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _hand_tok(_post_board(br, ctx))
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
    tok = _hand_tok(_post_board(br, ctx))
    qo = FakeQuery(f"delivery:other:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qo), ctx, br))
    lst = ctx.bot.sent[-1]                      # список замены — НОВЫМ сообщением
    pick_cbs = _cbs(lst["reply_markup"])
    assert pick_cbs == [f"delivery:pick:{tok}:0", f"delivery:pick:{tok}:1"], pick_cbs  # 2 байка ДОМА
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

def test_pay_inactive_no_write():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _hand_tok(_post_board(br, ctx))
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
        asyncio.run(S.hb_post_board(ctx, br))
        sent = ctx.bot.sent[-1]
        assert sent["chat_id"] == S.HB_TEST_CHAT_ID, "тест-доска в HQ"
        assert "ТЕСТ" in sent["text"]
        cbs = _cbs(sent["reply_markup"])
        assert len(cbs) == 6, f"3 выдуманные брони × 2 кнопки = 6, а {len(cbs)}"
        tok = _hand_tok(sent["reply_markup"])
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
