"""Класс F — эскалация contradiction/high в инбокс 1160.
Проверяем: (B1) contradiction/high → AUDIT_INBOX_TOPIC_ID=1160, не AUDIT_THREAD_ID=161;
(B2) contradiction/med → AUDIT_THREAD_ID=161, не инбокс;
(B3) дедуп: повторная карточка с тем же fingerprint → НЕ отправляется;
(B4) fail-safe: inbox_escalate=True но AUDIT_INBOX_TOPIC_ID=0 → fallback тема 161;
(B5) fail-safe: inbox_escalate=True, отправка в инбокс бросает исключение → fallback тема 161.
Тяжёлые зависимости zastableny ДО импорта — тест не трогает живую DB и не требует ключей."""
import sys, types, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ["AUDIT_CHAT_ID"] = "-1003853365891"
os.environ["AUDIT_THREAD_ID"] = "161"
os.environ["INBOX_TOPIC_ID"] = "1160"

class FakeMemory:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}

class FakeBridge:
    pass

class FakeClaude:
    def __init__(self, *a, **k): pass

class FakeAuditor:
    audit_groups = []
    def __init__(self, *a, **k): pass
    def set_audit_config(self, *a, **k): pass

def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m

_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: FakeBridge(), agent_write=lambda *a, **k: None)
_stub("claude_client", ClaudeClient=FakeClaude)
_stub("memory", Memory=FakeMemory)
_stub("auditor", Auditor=FakeAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import bot as B

res = []

def ok(cond, label):
    print(("PASS" if cond else "FAIL"), "-", label)
    return bool(cond)


# Фиктивный bot: пишет вызовы send_message в список
class FakeBot:
    def __init__(self):
        self.calls = []   # [(chat_id, thread_id_or_None)]
        self.raise_on_thread = None  # если задан — бросить исключение при этом thread_id

    async def send_message(self, **kw):
        tid = kw.get("message_thread_id")
        if self.raise_on_thread is not None and tid == self.raise_on_thread:
            raise Exception(f"fake error sending to thread {tid}")
        self.calls.append((kw.get("chat_id"), tid))

class FakeContext:
    def __init__(self, bot): self.bot = bot

loop = asyncio.new_event_loop()
run = loop.run_until_complete


def reset():
    B._audit_cards.clear()
    B._audit_seq[0] = 0
    B._audit_high_dedup.clear()


# B1: contradiction/high → инбокс 1160
reset()
bot = FakeBot()
card_high = {
    "answer": "ответ бота", "detail": "клиент А сказал Б а бот сказал В", "fix": "fix",
    "verdict": "contradiction", "severity": "high",
    "chat_id": -1003909369438, "topic_id": 42,
    "audit_thread_id": 161, "inbox_escalate": True,
}
run(B.post_audit_card(FakeContext(bot), card_high))
print("(B1) contradiction/high → инбокс 1160:")
res.append(ok(len(bot.calls) == 1, "ровно один вызов send_message"))
res.append(ok(bot.calls and bot.calls[0][1] == 1160, f"message_thread_id=1160, got {bot.calls}"))

# B2: contradiction/med → тема 161 (не инбокс)
reset()
bot = FakeBot()
card_med = {
    "answer": "ответ", "detail": "ошибка логики", "fix": "",
    "verdict": "contradiction", "severity": "med",
    "chat_id": -1003909369438, "topic_id": 42,
    "audit_thread_id": 161, "inbox_escalate": False,
}
run(B.post_audit_card(FakeContext(bot), card_med))
print("(B2) contradiction/med → тема 161:")
res.append(ok(len(bot.calls) == 1, "ровно один вызов send_message"))
res.append(ok(bot.calls and bot.calls[0][1] == 161, f"message_thread_id=161, got {bot.calls}"))

# B3: дедуп — второй вызов с тем же fingerprint → карточка НЕ отправляется
reset()
bot = FakeBot()
card_h2 = dict(card_high, detail="клиент А сказал Б а бот сказал В", inbox_escalate=True)
run(B.post_audit_card(FakeContext(bot), card_h2))
run(B.post_audit_card(FakeContext(bot), card_h2))  # повтор с тем же detail
print("(B3) дедуп contradiction/high:")
res.append(ok(len(bot.calls) == 1, f"второй вызов проигнорирован (calls={bot.calls})"))

# B4: fail-safe — AUDIT_INBOX_TOPIC_ID=0 → fallback тема 161
reset()
old_inbox = B.AUDIT_INBOX_TOPIC_ID
B.AUDIT_INBOX_TOPIC_ID = 0
bot = FakeBot()
run(B.post_audit_card(FakeContext(bot), dict(card_high, inbox_escalate=True)))
B.AUDIT_INBOX_TOPIC_ID = old_inbox
print("(B4) fail-safe инбокс выключен → тема 161:")
res.append(ok(len(bot.calls) == 1, "один вызов"))
res.append(ok(bot.calls and bot.calls[0][1] == 161, f"fallback thread=161, got {bot.calls}"))

# B5: fail-safe — отправка в инбокс бросает → fallback тема 161
reset()
bot = FakeBot()
bot.raise_on_thread = 1160   # инбокс упадёт
run(B.post_audit_card(FakeContext(bot), dict(card_high, inbox_escalate=True)))
print("(B5) fail-safe: ошибка отправки в инбокс → fallback тема 161:")
res.append(ok(len(bot.calls) == 1, f"один вызов (fallback, calls={bot.calls})"))
res.append(ok(bot.calls and bot.calls[0][1] == 161, f"fallback thread=161, got {bot.calls}"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
