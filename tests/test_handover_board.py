"""Моки ТАБЛО ВЫДАЧИ (Delivery, слой 1 площадки O3). Сеть/LLM/_send-бот замоканы.
Проверяет: доска броней дня (фильтр бронь+сегодня), кнопка «Выдан»→переспрос байка,
«он»→выдача, «другой»→список дома→pick→замена байка, state_set РОВНО 1 раз на подтверждении
с каноничным именем, денежный РАЗЪЁМ появляется ТОЛЬКО после выдачи (гейт), pay не пишет, устаревший токен."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

TODAY = S._hb_phuket("%Y-%m-%d")


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
    def find_bike(self, q): return {"name": str(q) + " CANON"}   # каноничное имя (проверяем, что идёт в state_set)
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

def _post_board(br, ctx):
    asyncio.run(S.hb_post_board(ctx, br))
    return ctx.bot.sent[-1]["reply_markup"]

def _first_tok(markup):
    return int(_cbs(markup)[0].split(":")[2])


def test_board_filters_today_bron():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    mk = _post_board(br, ctx)
    cbs = _cbs(mk)
    assert len(cbs) == 2, f"должно быть 2 брони (бронь+сегодня), а не {len(cbs)}"   # XMAX(в аренде), ADV(не сегодня) отсеяны
    assert all(c.startswith("delivery:hand:") for c in cbs), cbs
    body = ctx.bot.sent[-1]["text"]
    assert "Выдачи на сегодня" in body

def test_hand_opens_reask_no_money_no_state():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    q = FakeQuery(f"delivery:hand:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(q), ctx, br))
    card = ctx.bot.sent[-1]
    assert "он, или другой" in card["text"], card["text"]
    cbs = _cbs(card["reply_markup"])
    assert any(c == f"delivery:ok:{tok}" for c in cbs) and any(c == f"delivery:other:{tok}" for c in cbs), cbs
    assert not any("delivery:pay" in c for c in cbs), "ГЕЙТ: денег НЕ должно быть до подтверждения выдачи"
    assert br.state_calls == [], "state_set НЕ должен вызываться на переспросе"

def test_ok_state_once_and_money_socket():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:hand:{tok}")), ctx, br))
    q = FakeQuery(f"delivery:ok:{tok}", text="🛵 Выдача\nбайк NMAX 4957")
    asyncio.run(S.handle_delivery_button(FakeUpdate(q), ctx, br))
    assert len(br.state_calls) == 1, f"state_set ровно 1 раз, а {len(br.state_calls)}"
    c = br.state_calls[0]
    assert c["status"] == "в аренде", c
    assert c["bike"] == "NMAX 4957 CANON", c           # каноничное имя из find_bike
    assert c["client"] == "Ivan" and c["booking_id"] == "B1", c
    last_markup = q.edits[-1][1]
    paycbs = _cbs(last_markup)
    assert paycbs == [f"delivery:pay:{tok}"], f"денежный разъём появляется ТОЛЬКО после выдачи: {paycbs}"
    assert "выдал клиенту" in q.message.text and "Пхукет" in q.message.text, q.message.text

def test_other_pick_replaces_bike():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:hand:{tok}")), ctx, br))
    qo = FakeQuery(f"delivery:other:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qo), ctx, br))
    pick_cbs = _cbs(qo.edits[-1][1])
    assert pick_cbs == [f"delivery:pick:{tok}:0", f"delivery:pick:{tok}:1"], pick_cbs  # 2 байка ДОМА
    assert br.state_calls == [], "до выбора байка state_set не вызывается"
    qp = FakeQuery(f"delivery:pick:{tok}:1")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qp), ctx, br))
    assert len(br.state_calls) == 1, br.state_calls
    c = br.state_calls[0]
    assert c["bike"] == "FORZA 350 5050 CANON", c        # выбран кандидат idx1, каноничное имя
    assert c["client"] == "Ivan" and c["booking_id"] == "B1", "бронь та же, сменился только байк"
    assert _cbs(qp.edits[-1][1]) == [f"delivery:pay:{tok}"], "денежный разъём после выдачи"

def test_pay_inactive_no_write():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    tok = _first_tok(_post_board(br, ctx))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:hand:{tok}")), ctx, br))
    asyncio.run(S.handle_delivery_button(FakeUpdate(FakeQuery(f"delivery:ok:{tok}")), ctx, br))
    n = len(br.state_calls)
    qp = FakeQuery(f"delivery:pay:{tok}")
    asyncio.run(S.handle_delivery_button(FakeUpdate(qp), ctx, br))
    assert len(br.state_calls) == n, "денежный разъём НЕ активен — ничего не пишет"
    assert any("следующий слой" in (a or "").lower() or "не активна" in (a or "").lower() for a in qp.answers), qp.answers

def test_stale_token_graceful():
    _reset(); br = FakeBridge(); ctx = FakeCtx()
    q = FakeQuery("delivery:ok:999999")
    asyncio.run(S.handle_delivery_button(FakeUpdate(q), ctx, br))
    assert br.state_calls == [], "устаревший токен ничего не пишет"
    assert any("устарела" in (t or "") for t, _ in q.edits), q.edits


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов табло выдачи (слой 1 O3)")
