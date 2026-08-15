"""log.info '→ photo servicing' появляется ДО _servicing_caption_to_brain в _route_photos (класс G)."""
import sys, os, asyncio, logging, types, contextlib
from unittest.mock import AsyncMock, patch
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class FakeMem:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}


class FakeClaude:
    def __init__(self, *a, **k): pass


class FakeBridge:
    pass


class FakeAuditor:
    audit_groups = []
    def __init__(self, *a, **k): pass
    def set_audit_config(self, *a, **k): pass


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: FakeBridge(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())   # общий бюджет опроса (15.08.2026)
_stub("claude_client", ClaudeClient=FakeClaude)
_stub("memory", Memory=FakeMem)
_stub("auditor", Auditor=FakeAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import bot

CHAT = -1002751134848   # servicing в GROUPS
TOPIC = 77


class FakeUser:
    username = "Pleummmm"


class FakeMsg:
    def __init__(self, cap=""):
        self.chat_id = CHAT
        self.message_thread_id = TOPIC
        self.caption = cap
        self.photo = [object()]
        self.text = None
        self.from_user = FakeUser()
        self.message_id = 1


class FakeUpdate:
    def __init__(self, msg):
        self.message = msg


def test_photo_servicing_log_before_caption_to_brain():
    """'photo servicing' log.info должен появиться ДО вызова _servicing_caption_to_brain."""
    events = []

    class LogHandler(logging.Handler):
        def emit(self, record):
            if "photo servicing" in record.getMessage():
                events.append("log")

    logger = logging.getLogger("turbobaby")
    orig_level = logger.level
    logger.setLevel(logging.INFO)
    handler = LogHandler()
    logger.addHandler(handler)

    orig_fn = bot._servicing_caption_to_brain

    def fake_caption_to_brain(*a, **k):
        events.append("process")
        return False

    bot._servicing_caption_to_brain = fake_caption_to_brain
    try:
        msg = FakeMsg(cap="@SplinterBot проверь резину")
        update = FakeUpdate(msg)
        with patch.object(bot.splinter, "ensure_info_pin", new_callable=AsyncMock):
            with patch.object(bot.splinter, "handle", new_callable=AsyncMock):
                asyncio.run(bot._route_photos(None, [update]))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)
        bot._servicing_caption_to_brain = orig_fn

    assert "log" in events, f"'photo servicing' log не появился; events={events}"
    assert "process" in events, f"_servicing_caption_to_brain не вызвана; events={events}"
    assert events.index("log") < events.index("process"), (
        f"log должен быть ДО caption_to_brain, но events={events}"
    )


def test_photo_servicing_log_contains_username_and_cap():
    """Лог содержит username и начало caption."""
    captured = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            if "photo servicing" in record.getMessage():
                captured.append(record.getMessage())

    logger = logging.getLogger("turbobaby")
    orig_level = logger.level
    logger.setLevel(logging.INFO)
    handler = CaptureHandler()
    logger.addHandler(handler)

    orig_fn = bot._servicing_caption_to_brain
    bot._servicing_caption_to_brain = lambda *a, **k: False
    try:
        msg = FakeMsg(cap="проверь резину")
        update = FakeUpdate(msg)
        with patch.object(bot.splinter, "ensure_info_pin", new_callable=AsyncMock):
            with patch.object(bot.splinter, "handle", new_callable=AsyncMock):
                asyncio.run(bot._route_photos(None, [update]))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(orig_level)
        bot._servicing_caption_to_brain = orig_fn

    assert captured, "Лог 'photo servicing' не выведен"
    msg_text = captured[0]
    assert "pleummmm" in msg_text, f"username не в логе: {msg_text}"
    assert "резину" in msg_text, f"caption не в логе: {msg_text}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов photo servicing log")
