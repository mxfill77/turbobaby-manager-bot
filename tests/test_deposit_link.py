"""O3-3c часть Б: привязка deposit-прихода Money к брони по байку (splinter).
Покрытие:
- РОВНО один матч в CRM (Бронь/В аренде по номеру байка, booking_id col Y) →
  booking_id уходит в add_transaction deposit-движения + «привязано к брони строка N»;
- ноль матчей / несколько матчей → booking_id пуст, запись как раньше + «уточни бронь»;
- intake-окно: 30 мин после «✅ Бронь записана» по тому же байку — приоритет над CRM
  (CRM не читается вовсе), просроченное окно → обычный CRM-резолв;
- регресс Money цел: движение БЕЗ депозита → ни линка, ни подсказки, CRM не читается;
  возврат депозита (минус) → не трогаем.
Реальных сетевых вызовов НЕТ — bridge/_send замоканы (схема test_llm_loud_fail)."""
import os
import sys
import asyncio
import datetime
import tempfile
import time

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
# §касса, 13.08.2026: кэш баланса — БОЕВОЕ состояние в корне репо. Без этой строки прогон писал в
# него фикстурное «Money Cashflow: 1000» (так оно там и оказалось), и при больном мосте касса
# подставила бы группе выдуманное тестом число. Сьют держит своё состояние в своём каталоге.
os.environ["WALLET_CACHE_FILE"] = os.path.join(
    tempfile.mkdtemp(prefix="tb_deposit_link_"), "wallet_cache.json")

import splinter as S

MONEY_CHAT = -1003873906891   # Money Cashflow

SENDS = []


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


S._send = _rec_send
S._send_retry = _rec_send


class Msg:
    def __init__(self, text, msg_id=555):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = MONEY_CHAT
        self.message_thread_id = None
        self.date = datetime.datetime(2026, 7, 8, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.message_id = msg_id
        self.from_user = type("U", (), {"username": "pleummmm", "id": 111})()


class FakeBridge:
    """clients → подсунутые CRM-строки; add_transaction → захват kwargs."""
    def __init__(self, clients_rows):
        self.rows = clients_rows
        self.tx = []
        self.clients_calls = 0

    def _call(self, action, **kw):
        assert action == "clients"
        self.clients_calls += 1
        return {"ok": True, "data": {"clients": self.rows}}

    def add_transaction(self, **kw):
        self.tx.append(kw)
        return {"ok": True, "saved": True}

    def get_balance(self, **kw):
        # ЖИВОЙ ФОРМАТ ответа моста: `ok` есть ВСЕГДА (Bridge.js:284-285 → BotData.getBalance).
        # Без него касса законно считает мост молчащим — а этот сьют про здоровый путь.
        return {"ok": True, "balance": {"THB": 1000}}


def crm(row, status, bike, booking_id):
    return {"row": row, "status": status, "bike": bike, "booking_id": booking_id,
            "name": "Client", "date_start": "01.07.2026", "date_end": "15.07.2026"}


DEPOSIT_PARSED = {
    "type": "transaction",
    "moves": [
        {"amount": 4900, "currency": "THB", "category": "rental", "bike": "ADV 8004", "deposit": "passport"},
        {"amount": 1, "currency": "PASSPORT", "category": "other", "bike": None, "deposit": None},
    ],
    "transfer_to_pettycash": False,
}


def run_tx(bridge, parsed, text="ADV 8004 +4,900 Bath 1 passport"):
    SENDS.clear()
    S._RECENT_BOOKINGS_snapshot = None
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            S._record_transaction(None, bridge, None, Msg(text), parsed, "Money Cashflow"))
    finally:
        loop.close()


def setup_function(_fn):
    S._RECENT_BOOKINGS.clear()
    S._entry_counts.clear()


# ── один матч → линк ──
def test_one_match_links():
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC BLACK 8004", "uuid-A"),
                    crm(650, "Завершена", "HONDA ADV 350CC BLACK 8004", "uuid-OLD"),
                    crm(690, "Бронь", "NMAX 155CC GREEN 4957", "uuid-B")])
    run_tx(b, DEPOSIT_PARSED)
    assert b.tx[0]["booking_id"] == "uuid-A"          # deposit-движение привязано
    assert b.tx[1]["booking_id"] == ""                # паспорт-движение — нет
    blob = "\n".join(SENDS)
    assert "привязано к брони строка 700" in blob
    assert "уточни бронь" not in blob


# ── ноль матчей → как раньше + подсказка ──
def test_zero_match_hint():
    b = FakeBridge([crm(690, "Бронь", "NMAX 155CC GREEN 4957", "uuid-B")])
    run_tx(b, DEPOSIT_PARSED)
    assert all(t["booking_id"] == "" for t in b.tx)
    blob = "\n".join(SENDS)
    assert "уточни бронь" in blob
    assert "привязано" not in blob


# ── несколько матчей → как раньше + подсказка ──
def test_two_matches_hint():
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC 8004", "uuid-A"),
                    crm(710, "В аренде", "HONDA ADV 350CC 8004", "uuid-C")])
    run_tx(b, DEPOSIT_PARSED)
    assert all(t["booking_id"] == "" for t in b.tx)
    assert "уточни бронь" in "\n".join(SENDS)


# ── матч без uuid (старая строка CRM) → честная подсказка, не пустой линк ──
def test_match_without_uuid_hint():
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC 8004", "")])
    run_tx(b, DEPOSIT_PARSED)
    assert all(t["booking_id"] == "" for t in b.tx)
    assert "уточни бронь" in "\n".join(SENDS)


# ── intake-окно: приоритет над CRM, CRM не читается ──
def test_intake_window_priority():
    S._RECENT_BOOKINGS["8004"] = {"booking_id": "uuid-FRESH", "row": 720, "ts": time.time()}
    # в CRM нарочно ДВА матча — окно должно победить без чтения CRM
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC 8004", "uuid-A"),
                    crm(710, "В аренде", "HONDA ADV 350CC 8004", "uuid-C")])
    run_tx(b, DEPOSIT_PARSED)
    assert b.tx[0]["booking_id"] == "uuid-FRESH"
    assert b.clients_calls == 0
    assert "привязано к брони строка 720" in "\n".join(SENDS)


# ── просроченное окно (>30 мин) → обычный CRM-резолв ──
def test_intake_window_expired():
    S._RECENT_BOOKINGS["8004"] = {"booking_id": "uuid-STALE", "row": 720,
                                  "ts": time.time() - S._DEPOSIT_LINK_WINDOW - 60}
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC 8004", "uuid-A")])
    run_tx(b, DEPOSIT_PARSED)
    assert b.tx[0]["booking_id"] == "uuid-A"
    assert b.clients_calls == 1
    assert "привязано к брони строка 700" in "\n".join(SENDS)


# ── регресс Money: движение без депозита → ни линка, ни подсказки, CRM не дёргаем ──
def test_regular_move_untouched():
    b = FakeBridge([crm(700, "Бронь", "HONDA ADV 350CC 8004", "uuid-A")])
    run_tx(b, {"type": "transaction", "transfer_to_pettycash": False,
               "moves": [{"amount": -500, "currency": "THB", "category": "other",
                          "bike": None, "deposit": None}]},
           text="-500 бензин")
    assert b.tx[0]["booking_id"] == ""
    assert b.clients_calls == 0
    blob = "\n".join(SENDS)
    assert "уточни бронь" not in blob and "привязано" not in blob
    assert len(SENDS) >= 1        # подтверждение записи ушло как раньше


# ── регресс: возврат депозита (минус) не трогаем — без линка и без подсказки ──
def test_deposit_refund_untouched():
    b = FakeBridge([crm(700, "Завершена", "HONDA ADV 350CC 8004", "uuid-A")])
    run_tx(b, {"type": "transaction", "transfer_to_pettycash": False,
               "moves": [{"amount": -8000, "currency": "THB", "category": "other",
                          "bike": "ADV 8004", "deposit": "cash"}]},
           text="ADV 8004 -8000 депозит вернул")
    assert b.tx[0]["booking_id"] == ""
    assert b.clients_calls == 0
    blob = "\n".join(SENDS)
    assert "уточни бронь" not in blob and "привязано" not in blob


# ── юнит резолвера: сбой Bridge → None (запись не падает) ──
def test_resolver_bridge_down():
    class DownBridge:
        def _call(self, *a, **k):
            raise RuntimeError("bridge down")
    assert S._deposit_resolve_booking(DownBridge(), "ADV 8004") is None
    assert S._deposit_resolve_booking(FakeBridge([]), None) is None   # байка нет вовсе


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        setup_function(fn)
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов привязки депозита к брони (O3-3c часть Б)")
