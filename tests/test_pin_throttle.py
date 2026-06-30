"""Флуд-троттл /pin_info_all: ровный темп + RetryAfter-ретрай (через единый _send_retry) → ВСЕ темы запинены,
тему не теряем; повторный засев → 0 повторных отправок (дедуп). Боевого Telegram нет — _send/pin замоканы."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S
from telegram.error import RetryAfter

# не спим по-настоящему (троттл-паузы и RetryAfter-ожидания) — мгновенный тест
async def _noop_sleep(*a, **k): return None
asyncio.sleep = _noop_sleep

CHAT = S.SERVICING_CHAT
TOPICS = [101, 102, 103, 104, 105, 106, 107, 108]   # 8 тем обслуживания
FLOOD_TOPICS = {102, 105}                            # эти флудят ОДИН раз, потом проходят (эмуляция RetryAfter)

class FakeSent:
    def __init__(self, mid): self.message_id = mid
class FakeBot:
    def __init__(self): self.pinned = []
    async def pin_chat_message(self, chat_id, message_id, disable_notification=None):
        self.pinned.append(message_id)
class FakeCtx:
    def __init__(self): self.bot = FakeBot()
class FakeMemory:
    def __init__(self): self.pins = {}
    def set_info_pin(self, c, t, m): self.pins[(int(c), int(t))] = int(m)
    def get_info_pin(self, c, t): return self.pins.get((int(c), int(t)))
    def all_info_pins(self): return dict(self.pins)

SEND_CALLS = []; _MID = [7000]; _flooded = set()
async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, group="", reply_markup=None):
    SEND_CALLS.append(message_thread_id)
    if message_thread_id in FLOOD_TOPICS and message_thread_id not in _flooded:
        _flooded.add(message_thread_id)
        raise RetryAfter(2)          # первый раз по теме — флуд-контроль; _send_retry должен переждать и повторить
    _MID[0] += 1
    return FakeSent(_MID[0])
S._send = rec_send                   # МОКАЕМ только нижний _send; _send_retry — НАСТОЯЩИЙ (его и тестируем)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []; loop = asyncio.new_event_loop()

# подготовка: 8 servicing-тем + 1 чужой чат (должна скипнуться фильтром)
S._INFO_PINNED.clear(); S._TOPIC_NAMES.clear(); S._TOPIC_BIKE_OVERRIDE.clear()
S._MEMORY = FakeMemory()
for t in TOPICS:
    S._TOPIC_NAMES[(CHAT, t)] = f"BIKE-{t}"
S._TOPIC_NAMES[(-999, 555)] = "не-обслуживание"

ctx = FakeCtx()
st = loop.run_until_complete(S.pin_info_all(ctx))
print("итог:", st)
print("(1) троттл + RetryAfter-ретрай:")
res.append(ok(st["total"] == 8, "обойдено 8 servicing-тем (чужой чат скипнут фильтром)"))
res.append(ok(st["pinned"] == 8 and st["fail"] == 0, "ВСЕ 8 запинены, 0 потерь (RetryAfter пережит)"))
res.append(ok(all((CHAT, t) in S._INFO_PINNED for t in TOPICS), "все 8 в _INFO_PINNED"))
res.append(ok(len(ctx.bot.pinned) == 8, "8 реальных пинов (pin_chat_message)"))
# флудовые темы шлются ДВАЖДЫ (флуд + повтор), остальные — по разу
res.append(ok(SEND_CALLS.count(102) == 2 and SEND_CALLS.count(105) == 2, "флудовые темы (102,105) отправлены 2× (был ретрай)"))
res.append(ok(SEND_CALLS.count(101) == 1 and SEND_CALLS.count(108) == 1, "не-флудовые — по 1 отправке"))
# порядок первых попыток = порядок тем (не потерян)
first_attempts = []
for t in SEND_CALLS:
    if t not in first_attempts: first_attempts.append(t)
res.append(ok(first_attempts == TOPICS, f"порядок тем сохранён: {first_attempts}"))
res.append(ok(S._MEMORY.all_info_pins() and len(S._MEMORY.all_info_pins()) == 8, "8 закрепов персистнуты в memory.db"))

# (2) повторный засев → дедуп: 0 новых отправок
SEND_CALLS.clear()
st2 = loop.run_until_complete(S.pin_info_all(ctx))
print("(2) повторный засев (дедуп):")
res.append(ok(st2["already"] == 8 and st2["pinned"] == 0, "повтор: все 8 «уже было», 0 новых пинов"))
res.append(ok(len(SEND_CALLS) == 0, "НИ ОДНОЙ повторной отправки (повторный /pin_info_all не флудит)"))

# (3) имитация рестарта: seed из memory.db → дедуп держится
S._INFO_PINNED.clear(); SEND_CALLS.clear()
n = S.seed_info_pins()
st3 = loop.run_until_complete(S.pin_info_all(ctx))
print("(3) рестарт (seed) → дедуп:")
res.append(ok(n == 8, "seed_info_pins поднял 8 закрепов из memory.db"))
res.append(ok(st3["already"] == 8 and len(SEND_CALLS) == 0, "после рестарта повтор не шлёт (дедуп через персист)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
