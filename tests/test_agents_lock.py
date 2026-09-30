# -*- coding: utf-8 -*-
"""ЗАМОК ГОЛОСОВЫХ + ПАССИВНЫЙ РЕЖИМ «agents» (0076-75s.3009, AGENTGROUP3009 §6 шаги 0–1).

До правки голосовое из ЛЮБОЙ группы шло в полный мозг HQ (Whisper → SYSTEM_PROMPT → claude.ask с
пишущими инструментами), карту групп голосовой путь не смотрел вовсе (bot.py:986–1075 на 0772f84).
Отрицательные («−»): голос из группы вне карты не доходит до скачивания, Whisper и мозга; в группе
«TurboBaby · Агенты» текст, голос и фото не будят мозг и не отвечают, строка приёма несёт user id.
Положительные («+»): HQ, личка и группа карты идут прежним путём.
Всё на моках: сети, Telegram, memory.db и моста нет; файлов не пишет.
"""
import asyncio
import contextlib
import io
import logging
import os
import sys
import types
from unittest.mock import AsyncMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
HQ = -1001000000001                       # синтетический id HQ для этого процесса
os.environ["GROUP_CHAT_ID"] = str(HQ)

AGENTS = -1003999596406
FOREIGN = -1009999999999                  # группа вне карты
SERVICING = -1002751134848                # группа карты (режим servicing)
PRIVATE = 5550001                         # личка — положительный id
UID = 777000111
NICK = "probe_user"


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class _StubMem:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}


class _StubAuditor:
    audit_groups = []
    def __init__(self, *a, **k): pass
    def set_audit_config(self, *a, **k): pass


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: object(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=lambda *a, **k: object())
_stub("memory", Memory=_StubMem)
_stub("auditor", Auditor=_StubAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

CALLS = []


class _FakeTranscriptions:
    def create(self, **kw):
        CALLS.append("whisper")
        return types.SimpleNamespace(text="расшифровка пробы")


class _FakeOpenAI:
    def __init__(self, *a, **k):
        CALLS.append("openai_client")
        self.audio = types.SimpleNamespace(transcriptions=_FakeTranscriptions())


_stub("openai", OpenAI=_FakeOpenAI)

import bot          # noqa: E402
import splinter     # noqa: E402


class FakeMemory:
    def save_message(self, *a, **k): CALLS.append("memory.save_message")
    def get_context_for_claude(self, *a, **k):
        CALLS.append("memory.context")
        return {"history": [{"role": "user", "content": "x"}], "rules": []}


class FakeClaude:
    def ask(self, **kw):
        CALLS.append("claude.ask")
        return "ответ мозга"


def _fake_open(path, mode="r", *a, **k):
    CALLS.append("open_audio")
    return io.BytesIO(b"ogg")


bot.memory = FakeMemory()
bot.claude = FakeClaude()
bot.open = _fake_open          # глобал модуля перекрывает builtins.open: аудио не пишется на диск


class FakeUser:
    def __init__(self, uid=UID, username=NICK, first_name="Probe"):
        self.id = uid
        self.username = username
        self.first_name = first_name


class FakeFile:
    async def download_to_drive(self, path):
        CALLS.append("download")


class FakeVoice:
    duration = 7
    async def get_file(self):
        CALLS.append("get_file")
        return FakeFile()


class FakeMsg:
    def __init__(self, chat_id, chat_type="supergroup", text=None, voice=False, photo=False,
                 caption=None, user=None, with_chat=True):
        self.chat_id = chat_id
        if with_chat:
            self.chat = types.SimpleNamespace(id=chat_id, type=chat_type)
        self.message_thread_id = None
        self.message_id = 4242
        self.text = text
        self.caption = caption
        self.voice = FakeVoice() if voice else None
        self.photo = [object()] if photo else []
        self.media_group_id = None
        self.from_user = user if user is not None else FakeUser()
        self.replies = []

    async def reply_text(self, text, **kw):
        CALLS.append("reply_text")
        self.replies.append(text)


class FakeBot:
    username = "splinter_probe_bot"
    async def send_chat_action(self, **kw):
        CALLS.append("send_chat_action")
    async def send_message(self, **kw):
        CALLS.append("send_message")


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []
    def emit(self, record):
        self.lines.append(record.getMessage())


@contextlib.contextmanager
def _logs():
    h = _Capture()
    loggers = [logging.getLogger("turbobaby"), logging.getLogger("splinter")]
    levels = [lg.level for lg in loggers]
    for lg in loggers:
        lg.setLevel(logging.INFO)
        lg.addHandler(h)
    try:
        yield h.lines
    finally:
        for lg, lv in zip(loggers, levels):
            lg.removeHandler(h)
            lg.setLevel(lv)


def _run(coro):
    CALLS.clear()
    asyncio.run(coro)
    return list(CALLS)


def _update(msg):
    return types.SimpleNamespace(message=msg)


_BRAIN = {"get_file", "download", "openai_client", "whisper", "open_audio", "claude.ask",
          "memory.save_message", "memory.context"}


# ─── − замок голосовых: группа вне карты ───────────────────────────────────────────────────

def test_neg_voice_foreign_group_never_reaches_whisper_or_brain():
    msg = FakeMsg(FOREIGN, voice=True)
    with _logs() as lines:
        calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    assert not (_BRAIN & set(calls)), f"голос чужой группы дошёл до скачивания/Whisper/мозга: {calls}"
    assert "reply_text" not in calls and "send_chat_action" not in calls, calls
    lock = [l for l in lines if "ЗАМОК ГОЛОСОВЫХ" in l]
    assert len(lock) == 1 and str(FOREIGN) in lock[0], lines


def test_neg_voice_foreign_group_without_chat_type_fails_closed():
    """Нет типа чата, id отрицательный → считается группой (сомнение → замок)."""
    msg = FakeMsg(FOREIGN, voice=True, with_chat=False)
    calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    assert not (_BRAIN & set(calls)), calls


# ─── − пассивный режим agents ──────────────────────────────────────────────────────────────

def test_map_has_agents_group():
    assert splinter.GROUPS.get(AGENTS) == "agents"
    assert splinter.GROUP_NAMES.get(AGENTS) == "TurboBaby · Агенты"
    assert splinter.is_agents_group(AGENTS) and not splinter.is_agents_group(SERVICING)


def _intake_line(lines, kind):
    got = [l for l in lines if "[agents] приём" in l]
    assert len(got) == 1, f"строк приёма {len(got)}: {lines}"
    line = got[0]
    assert f"uid={UID}" in line and f"@{NICK}" in line and f"вид={kind}" in line, line
    return line


def test_neg_voice_agents_passive_with_user_id():
    msg = FakeMsg(AGENTS, voice=True)
    with _logs() as lines:
        calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    assert not (_BRAIN & set(calls)), f"голос в «Агентах» разбудил мозг: {calls}"
    assert "reply_text" not in calls and "send_chat_action" not in calls and not msg.replies, calls
    _intake_line(lines, "голос")


def test_neg_text_agents_owner_tag_passive_with_user_id():
    """Даже владелец с тегом бота: ни мозга, ни леджера, ни splinter.handle, ни ответа."""
    owner = sorted(splinter.OWNER_USERNAMES)[0] if getattr(splinter, "OWNER_USERNAMES", None) else NICK
    msg = FakeMsg(AGENTS, text="@splinter_probe_bot секретный текст пробы",
                  user=FakeUser(username=owner))
    with patch.object(bot, "manager_reply", new_callable=AsyncMock) as mr, \
            patch.object(bot, "_maybe_api_ledger_cmd", new_callable=AsyncMock) as led, \
            patch.object(bot.splinter, "handle", new_callable=AsyncMock) as sh, _logs() as lines:
        calls = _run(bot.handle_text(_update(msg), FakeContext()))
    assert not mr.await_count and not led.await_count and not sh.await_count, (mr, led, sh)
    assert "claude.ask" not in calls and "reply_text" not in calls and not msg.replies, calls
    got = [l for l in lines if "[agents] приём" in l]
    assert len(got) == 1 and f"uid={UID}" in got[0] and f"@{owner}" in got[0] and "вид=текст" in got[0], lines
    assert not any("секретный текст" in l for l in lines), "текст сообщения попал в журнал"


def test_neg_splinter_handle_agents_passive():
    msg = FakeMsg(AGENTS, text="любой текст")
    with _logs() as lines:
        calls = _run(splinter.handle(_update(msg), FakeContext(), None, None))
    assert calls == [], f"handle в «Агентах» сделал что-то кроме строки: {calls}"
    _intake_line(lines, "текст")


def test_neg_photo_agents_caption_tag_passive():
    owner = sorted(splinter.OWNER_USERNAMES)[0] if getattr(splinter, "OWNER_USERNAMES", None) else NICK
    msg = FakeMsg(AGENTS, photo=True, caption="@splinter_probe_bot проверь фото",
                  user=FakeUser(username=owner))
    with patch.object(bot, "manager_reply", new_callable=AsyncMock) as mr, \
            patch.object(bot, "_route_photos", new_callable=AsyncMock) as rp, _logs() as lines:
        calls = _run(bot.handle_photo(_update(msg), FakeContext()))
    assert not mr.await_count and not rp.await_count, (mr, rp)
    assert "reply_text" not in calls, calls
    assert any("[agents] приём" in l and "вид=фото" in l and f"uid={UID}" in l for l in lines), lines


# ─── + прежний путь: HQ, личка, группа карты ───────────────────────────────────────────────

def _assert_full_path(calls, msg):
    for step in ("get_file", "download", "whisper", "claude.ask", "memory.save_message"):
        assert step in calls, f"прежний путь потерял шаг {step}: {calls}"
    assert "ответ мозга" in msg.replies, msg.replies


def test_pos_voice_hq_prior_path():
    msg = FakeMsg(HQ, voice=True)
    calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    _assert_full_path(calls, msg)


def test_pos_voice_private_prior_path():
    msg = FakeMsg(PRIVATE, chat_type="private", voice=True)
    calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    _assert_full_path(calls, msg)


def test_pos_voice_map_group_prior_path():
    """Группа карты (servicing) замком не задета — голос идёт прежним путём (ответ на п.4)."""
    msg = FakeMsg(SERVICING, voice=True)
    calls = _run(bot.handle_voice(_update(msg), FakeContext()))
    _assert_full_path(calls, msg)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = []
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except Exception as e:
            failed.append(fn.__name__)
            print(f"  ✗ {fn.__name__}: {type(e).__name__}: {str(e)[:300]}")
    print(f"ИТОГ: {len(fns) - len(failed)}/{len(fns)} зелёных, упало {len(failed)}")
    sys.exit(1 if failed else 0)
