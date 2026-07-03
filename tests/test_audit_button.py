"""Кнопки карточки аудита (bot.py on_audit_button) при протухшем ack (хвост ревизии §7,
паттерн _o3_answer / _btn_answer): раньше сырой q.answer() первой строкой валил хендлер при
BadRequest «Query is too old» — 👍/✏️/👎 выглядели «мёртвыми», правило НЕ записывалось.
Проверяем: (A1) 👍 при мёртвом ack — правило уходит в memory.add_rule, карточка помечена;
(A2) устаревший токен при мёртвом ack — честное «карточка устарела»; (A3) 👎 при мёртвом ack;
(A4) живой ack — регресс. Тяжёлые зависимости bot.py (Bridge/Claude/Memory/Auditor) застаблены
ДО импорта — тест НЕ трогает живую memory.db и не требует ключей."""
import sys, types, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")

RULES = []

class FakeMemory:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}
    def add_rule(self, text, context=None, source=None):
        RULES.append(text); return len(RULES)

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


class FakeQuery:
    def __init__(s, data):
        s.data = data
        s.answers, s.edits = [], []
    async def answer(s, txt=None, **kw): s.answers.append(txt)
    async def edit_message_text(s, text=None, **kw):
        s.edits.append(text if text is not None else kw.get("text"))

class DeadAnswerQuery(FakeQuery):
    """Протухший колбэк: q.answer всегда кидает (BadRequest «Query is too old»)."""
    async def answer(s, txt=None, **kw):
        raise Exception("Query is too old and response timeout expired or query id is invalid")

class Upd:
    def __init__(s, q): s.callback_query = q

loop = asyncio.new_event_loop()
run = loop.run_until_complete

# A1: 👍 (audit:ok) при мёртвом ack — правило записано, карточка помечена «Принято»
RULES.clear(); B._audit_cards.clear()
B._audit_cards[1] = {"fix": "тестовое правило из аудита"}
q = DeadAnswerQuery("audit:ok:1")
run(B.on_audit_button(Upd(q), None))
print("(A1) 👍 при протухшем ack:")
res.append(ok(RULES == ["тестовое правило из аудита"], "правило записано в memory.add_rule несмотря на мёртвый ack"))
res.append(ok(len(q.edits) == 1 and "Принято" in q.edits[0], "карточка помечена «Принято»"))

# A2: устаревший токен (нет в _audit_cards) при мёртвом ack — честная пометка, не крэш
B._audit_cards.clear()
q = DeadAnswerQuery("audit:ok:99")
run(B.on_audit_button(Upd(q), None))
print("(A2) устаревший токен при протухшем ack:")
res.append(ok(len(q.edits) == 1 and "устарела" in q.edits[0], "ответ «карточка устарела» ушёл"))

# A3: 👎 (audit:no) при мёртвом ack — отклонение проходит
B._audit_cards[2] = {"fix": "не нужно"}
RULES.clear()
q = DeadAnswerQuery("audit:no:2")
run(B.on_audit_button(Upd(q), None))
print("(A3) 👎 при протухшем ack:")
res.append(ok(RULES == [] and len(q.edits) == 1 and "Отклонено" in q.edits[0], "отклонено без записи правила"))

# A4: регресс — живой ack работает как раньше
RULES.clear(); B._audit_cards[3] = {"fix": "живое правило"}
q = FakeQuery("audit:ok:3")
run(B.on_audit_button(Upd(q), None))
print("(A4) живой ack (регресс):")
res.append(ok(len(q.answers) == 1 and RULES == ["живое правило"], "ack прошёл, правило записано"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
