"""log.info 'fix-btn' пишется ДО вызова _apply_correction в handle_service_button (action='fix')."""
import os, sys, asyncio, logging
from unittest.mock import patch
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848
TOPIC = 308
BIKE = "XMAX 300CC NEW BLUE-3 PHUKET 4724"


class FakeQ:
    def __init__(self, data, uname="Pleummmm"):
        self.data = data
        self.from_user = type("U", (), {"username": uname})()
    async def answer(self, *a, **k): pass
    async def edit_message_reply_markup(self, **k): pass
    async def edit_message_text(self, *a, **k): pass


def _mk_update(q):
    return type("Upd", (), {"callback_query": q})()


def run(coro):
    return asyncio.run(coro)


def test_fix_btn_log_before_apply_correction():
    """'fix-btn' log.info должен появиться ДО того, как _apply_correction будет вызван."""
    S._SVC_TOKENS.clear()
    S._PENDING_CORRECTION.clear()

    tok = S._svc_put({
        "kind": "correction",
        "chat": CHAT, "topic": TOPIC,
        "bike": BIKE, "old_km": 19500, "new_km": 20000,
    })

    events = []

    class OrderHandler(logging.Handler):
        def emit(self, record):
            if "fix-btn" in record.getMessage():
                events.append("log")

    async def fake_apply(context, bridge, chat_id, topic_id, bike, old_km, new_km):
        events.append("apply")

    logger = logging.getLogger("splinter")
    orig_level = logger.level
    logger.setLevel(logging.INFO)
    handler = OrderHandler()
    logger.addHandler(handler)
    try:
        with patch.object(S, "_apply_correction", fake_apply):
            run(S.handle_service_button(
                _mk_update(FakeQ(f"svc:fix:{tok}")),
                context=None, bridge=None,
            ))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)

    assert "log" in events, f"log.info 'fix-btn' не вызван; events={events}"
    assert "apply" in events, f"_apply_correction не вызван; events={events}"
    assert events.index("log") < events.index("apply"), (
        f"log.info должен быть ДО _apply_correction, но events={events}"
    )


def test_fix_btn_log_contains_bike_and_km():
    """Сообщение лога содержит байк, old_km и new_km."""
    S._SVC_TOKENS.clear()
    S._PENDING_CORRECTION.clear()

    tok = S._svc_put({
        "kind": "correction",
        "chat": CHAT, "topic": TOPIC,
        "bike": BIKE, "old_km": 19500, "new_km": 20000,
    })

    captured = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            if "fix-btn" in record.getMessage():
                captured.append(record.getMessage())

    async def fake_apply(*a, **k):
        pass

    logger = logging.getLogger("splinter")
    orig_level = logger.level
    logger.setLevel(logging.INFO)
    handler = CaptureHandler()
    logger.addHandler(handler)
    try:
        with patch.object(S, "_apply_correction", fake_apply):
            run(S.handle_service_button(
                _mk_update(FakeQ(f"svc:fix:{tok}", uname="Pleummmm")),
                context=None, bridge=None,
            ))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)

    assert captured, "Сообщение 'fix-btn' не найдено в логе"
    msg = captured[0]
    assert str(19500) in msg, f"old_km 19500 не в логе: {msg}"
    assert str(20000) in msg, f"new_km 20000 не в логе: {msg}"
    assert "Pleummmm" in msg, f"uname не в логе: {msg}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов fix-btn log")
