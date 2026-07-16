"""Класс H — сторож Б (единый гейт снижения одометра).

Golden test: кейс 15.07 11:15:35 «ПРИМЕНЕНА в обход сторожа Б» — БЛОКИРУЕТСЯ.
Стандартный путь: authorize → check → разрешено.
Fail-safe: исключение в guard → allow.
Owner check: только владелец подтверждает снижение (text + кнопка).
"""
import os, sys, asyncio, logging, time
from unittest.mock import patch, AsyncMock
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 83   # топик 83 — тема кейса 15.07
BIKE = "XADV 750 GREY 2478"
OLD_KM = 24997
NEW_KM = 24500


def run(coro):
    return asyncio.run(coro)


def _clear_guard():
    S._ODOGUARD_CONFIRMED.clear()
    S._PENDING_CORRECTION.clear()
    S._SVC_TOKENS.clear()


# ── helper: fake message from user ────────────────────────────────────────────

class _FakeUser:
    def __init__(self, username=None, uid=None):
        self.username = username
        self.id = uid or 0


class _FakeMsg:
    def __init__(self, username=None, uid=None):
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.from_user = _FakeUser(username=username, uid=uid)


# ── golden test: кейс 15.07 — обход без авторизации → БЛОК ───────────────────

def test_golden_case_15jul_bypass_blocked():
    """Прямой вызов _apply_correction без _odoguard_authorize → блок.
    Воспроизводит кейс 15.07 11:15:35 «ПРИМЕНЕНА в обход сторожа Б»."""
    _clear_guard()
    called = []

    async def fake_service_tracker(*a, **k):
        called.append("tracker")
        return None

    async def fake_send(*a, **k):
        called.append("send")

    with patch.object(S, "_run_service_tracker", side_effect=fake_service_tracker), \
         patch.object(S, "_send_retry", side_effect=fake_send):
        run(S._apply_correction(None, None, CHAT, TOPIC, BIKE, OLD_KM, NEW_KM))

    assert "tracker" not in called, (
        f"сторож Б: _run_service_tracker должен был быть ЗАБЛОКИРОВАН, но был вызван. called={called}"
    )
    assert "send" not in called, (
        f"сторож Б: _send_retry не должен был вызываться при блоке. called={called}"
    )


# ── стандартный путь: authorize → apply → разрешено ──────────────────────────

def test_authorized_correction_allowed():
    """После _odoguard_authorize _apply_correction проходит."""
    _clear_guard()
    called = []

    def fake_tracker(*a, **k):
        called.append("tracker")
        return None

    async def fake_send(*a, **k):
        called.append("send")

    S._odoguard_authorize(CHAT, TOPIC, NEW_KM, source="test")
    with patch.object(S, "_run_service_tracker", side_effect=fake_tracker), \
         patch.object(S, "_send_retry", side_effect=fake_send):
        run(S._apply_correction(None, None, CHAT, TOPIC, BIKE, OLD_KM, NEW_KM))

    assert "tracker" in called, f"После авторизации _run_service_tracker должен был вызваться"
    # токен потреблён
    assert S._ODOGUARD_CONFIRMED.get((CHAT, TOPIC)) is None, "Токен должен быть потреблён"


# ── токен устарел → блок ──────────────────────────────────────────────────────

def test_expired_token_blocked():
    """Устаревший токен (> _ODOGUARD_TTL) → блок."""
    _clear_guard()
    S._ODOGUARD_CONFIRMED[(CHAT, TOPIC)] = {
        "new_km": NEW_KM, "ts": time.time() - S._ODOGUARD_TTL - 10, "source": "old"
    }
    called = []

    def fake_tracker(*a, **k):
        called.append("tracker")

    with patch.object(S, "_run_service_tracker", side_effect=fake_tracker):
        run(S._apply_correction(None, None, CHAT, TOPIC, BIKE, OLD_KM, NEW_KM))

    assert "tracker" not in called, "Устаревший токен должен блокировать"
    assert S._ODOGUARD_CONFIRMED.get((CHAT, TOPIC)) is None, "Устаревший токен должен быть удалён"


# ── несовпадение km → блок ────────────────────────────────────────────────────

def test_km_mismatch_blocked():
    """Токен есть, но new_km не совпадает → блок."""
    _clear_guard()
    S._odoguard_authorize(CHAT, TOPIC, NEW_KM + 100, source="wrong_km")
    called = []

    def fake_tracker(*a, **k):
        called.append("tracker")

    with patch.object(S, "_run_service_tracker", side_effect=fake_tracker):
        run(S._apply_correction(None, None, CHAT, TOPIC, BIKE, OLD_KM, NEW_KM))

    assert "tracker" not in called, "km-несовпадение должно блокировать"


# ── fail-safe: исключение в guard → allow ─────────────────────────────────────

def test_guard_exception_failsafe_allows():
    """Исключение ВНУТРИ _odoguard_check (bad dict value) → except → True (allow).
    Fail-safe: сбой сторожа → прежнее поведение."""
    _clear_guard()
    # Записываем токен с некорректным ts (не число) → внутри guard сравнение ts упадёт
    S._ODOGUARD_CONFIRMED[(CHAT, TOPIC)] = {
        "new_km": NEW_KM, "ts": "not-a-number", "source": "failsafe_test"
    }
    result = S._odoguard_check(CHAT, TOPIC, NEW_KM, caller="failsafe_test")
    assert result is True, f"Fail-safe: guard должен вернуть True при внутреннем исключении, вернул {result}"


# ── handle_correction_confirm: только владелец ────────────────────────────────

def test_correction_confirm_owner_only():
    """Текстовое «да» от НЕ-владельца → pending сохранён, apply не вызван."""
    _clear_guard()
    S._PENDING_CORRECTION[(CHAT, TOPIC)] = (OLD_KM, NEW_KM, BIKE, time.time())

    apply_called = []

    async def fake_apply(*a, **k):
        apply_called.append(1)

    msg_pym = _FakeMsg(username="Pleummmm")  # Pym, не владелец

    with patch.object(S, "_apply_correction", side_effect=fake_apply):
        result = run(S.handle_correction_confirm(msg_pym, None, None, "да"))

    assert result is False, f"Не-владелец должен вернуть False, вернул {result}"
    assert (CHAT, TOPIC) in S._PENDING_CORRECTION, "Pending должен сохраниться после non-owner"
    assert not apply_called, "_apply_correction не должен вызываться от non-owner"


def test_correction_confirm_owner_allowed():
    """Текстовое «да» от владельца → authorize + apply вызван."""
    _clear_guard()
    S._PENDING_CORRECTION[(CHAT, TOPIC)] = (OLD_KM, NEW_KM, BIKE, time.time())

    apply_called = []

    async def fake_apply(*a, **k):
        apply_called.append(1)

    def fake_clear(*a, **k):
        pass

    msg_owner = _FakeMsg(uid=504608015)  # OWNER_IDS

    with patch.object(S, "_apply_correction", side_effect=fake_apply), \
         patch.object(S, "clear_awaiting", side_effect=fake_clear):
        result = run(S.handle_correction_confirm(msg_owner, None, None, "да"))

    assert result is True, f"Владелец должен вернуть True, вернул {result}"
    assert apply_called, "_apply_correction должен быть вызван от владельца"
    assert (CHAT, TOPIC) not in S._PENDING_CORRECTION, "Pending должен быть очищен"


# ── handle_service_button fix: только владелец ───────────────────────────────

def test_fix_button_non_owner_blocked():
    """Кнопка fix от Пыма → блок, pending и токен живут."""
    _clear_guard()
    tok = S._svc_put({
        "kind": "correction", "chat": CHAT, "topic": TOPIC,
        "bike": BIKE, "old_km": OLD_KM, "new_km": NEW_KM,
    })
    S._PENDING_CORRECTION[(CHAT, TOPIC)] = (OLD_KM, NEW_KM, BIKE, time.time())

    apply_called = []

    class FakeQ:
        data = f"svc:fix:{tok}"
        from_user = _FakeUser(username="Pleummmm")  # Pym
        async def answer(self, text="", show_alert=False, **k): pass
        async def edit_message_reply_markup(self, **k): pass

    class FakeUpdate:
        callback_query = FakeQ()

    async def fake_apply(*a, **k):
        apply_called.append(1)

    with patch.object(S, "_apply_correction", side_effect=fake_apply):
        run(S.handle_service_button(FakeUpdate(), context=None, bridge=None))

    assert not apply_called, "Пым не должен авторизовать снижение одометра"
    assert tok in S._SVC_TOKENS, "Токен кнопки должен оставаться (кнопка живёт)"
    assert (CHAT, TOPIC) in S._PENDING_CORRECTION, "Pending должен оставаться"


def test_fix_button_owner_allowed():
    """Кнопка fix от владельца → authorize + apply."""
    _clear_guard()
    tok = S._svc_put({
        "kind": "correction", "chat": CHAT, "topic": TOPIC,
        "bike": BIKE, "old_km": OLD_KM, "new_km": NEW_KM,
    })
    S._PENDING_CORRECTION[(CHAT, TOPIC)] = (OLD_KM, NEW_KM, BIKE, time.time())

    apply_called = []

    class FakeQ:
        data = f"svc:fix:{tok}"
        from_user = _FakeUser(uid=504608015)  # owner
        async def answer(self, text="", show_alert=False, **k): pass
        async def edit_message_reply_markup(self, **k): pass

    class FakeUpdate:
        callback_query = FakeQ()

    async def fake_apply(*a, **k):
        apply_called.append(1)

    def fake_clear(*a, **k):
        pass

    with patch.object(S, "_apply_correction", side_effect=fake_apply), \
         patch.object(S, "clear_awaiting", side_effect=fake_clear):
        run(S.handle_service_button(FakeUpdate(), context=None, bridge=None))

    assert apply_called, "Владелец должен авторизовать снижение (apply вызван)"


# ── guard log: блок пишет warning ─────────────────────────────────────────────

def test_guard_block_logs_warning():
    """Блок guard → warning в log."""
    _clear_guard()
    warnings = []

    class Capture(logging.Handler):
        def emit(self, r):
            if "сторож Б БЛОК" in r.getMessage():
                warnings.append(r.getMessage())

    logger = logging.getLogger("splinter")
    h = Capture(); logger.addHandler(h)
    try:
        S._odoguard_check(CHAT, TOPIC, NEW_KM, caller="test_warn")
    finally:
        logger.removeHandler(h)

    assert warnings, "Блок guard должен писать warning"
    assert "_apply_correction" in warnings[0] or "test_warn" in warnings[0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов class_h_guard")
