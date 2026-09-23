"""АЛЬБОМ ИЗ N ФОТО — ОДИН ПРОГОН, А НЕ N (24.09.2026, задание Штаба 0027-72f).

Telegram шлёт альбом N отдельными обновлениями с общим `media_group_id`; `bot.handle_photo` копит
их и через окно `ALBUM_WINDOW` отдаёт в `_route_photos` ОДНОЙ пачкой. Замка на это в сьюте не было,
а жалоба «коммент на каждое фото альбома» упирается ровно сюда: сломайся склейка — ответов стало
бы N. Живьём склейка работала (журнал 22.09: «склеил 9 фото»); этот файл держит её тестом.

Близнецы: два РАЗНЫХ альбома → два прогона (склейка не сливает чужое); одиночные фото → по прогону
на каждое (одиночное не ждёт окна). Сеть, мост, мозг и память заглушены (приём
`test_photo_servicing_log`); `_route_photos` подменён счётчиком — в Splinter ничего не уходит.
"""
import asyncio
import contextlib
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class _Mem:
    def all_topic_bikes(self):
        return {}

    def all_info_pins(self):
        return {}


class _Any:
    audit_groups = []

    def __init__(self, *a, **k):
        pass

    def set_audit_config(self, *a, **k):
        pass


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: _Any(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=_Any)
_stub("memory", Memory=_Mem)
_stub("auditor", Auditor=_Any)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import bot  # noqa: E402

CHAT = next(cid for cid, m in bot.splinter.GROUPS.items() if m == "servicing")
TOPIC = 7314


class _Msg:
    def __init__(self, mid, mgid=None):
        self.chat_id, self.message_thread_id, self.message_id = CHAT, TOPIC, mid
        self.photo, self.caption, self.text = [object()], None, None
        self.media_group_id = mgid
        self.from_user = type("U", (), {"username": "testmech", "id": 1})()


class _Upd:
    def __init__(self, msg):
        self.message = msg


def _drive(batches):
    """Прогнать `bot.handle_photo` по списку обновлений и вернуть, какими пачками ушло."""
    passes = []

    async def _count(context, updates):
        passes.append([u.message.message_id for u in updates])

    saved = (bot._route_photos, bot.ALBUM_WINDOW)
    bot._route_photos, bot.ALBUM_WINDOW = _count, 0.05

    async def _go():
        for upd in batches:
            await bot.handle_photo(upd, None)
        await asyncio.sleep(0.4)

    try:
        asyncio.run(_go())
    finally:
        bot._route_photos, bot.ALBUM_WINDOW = saved
    return passes


def test_album_of_nine_is_one_pass():
    passes = _drive([_Upd(_Msg(100 + i, mgid="g1")) for i in range(9)])
    assert len(passes) == 1, passes
    assert sorted(passes[0]) == [100 + i for i in range(9)], passes


def test_two_albums_are_two_passes():
    ups = [_Upd(_Msg(200 + i, mgid="gA")) for i in range(4)]
    ups += [_Upd(_Msg(300 + i, mgid="gB")) for i in range(5)]
    passes = _drive(ups)
    assert sorted(len(p) for p in passes) == [4, 5], passes


def test_single_photos_are_one_pass_each():
    passes = _drive([_Upd(_Msg(400 + i)) for i in range(3)])
    assert passes == [[400], [401], [402]], passes


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
