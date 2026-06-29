"""Моки кнопки «ℹ️ Инфо по байку» (pinned-inline токен-free). Боевых тайцев/Telegram нет.
Сценарии a-h из плана: тап→карточка, ленивый пин+дедуп, пере-пин после unpin, резолв из темы,
обход тротла, персист round-trip (рестарт), debounce, /pin_info_all владельцем."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = S.SERVICING_CHAT
TOPIC = 4255
BIKE = "NMAX 155 BLACK GOLD 4255"

class FakeSent:
    def __init__(self, mid): self.message_id = mid
class FakeBot:
    def __init__(self): self.pinned = []
    async def pin_chat_message(self, chat_id, message_id, disable_notification=None):
        self.pinned.append(message_id)
class FakeCtx:
    def __init__(self): self.bot = FakeBot()
class FakeChat:
    def __init__(self, cid): self.id = cid
class FakeMsg:
    def __init__(self, cid, tid): self.chat = FakeChat(cid); self.message_thread_id = tid
class FakeQuery:
    def __init__(self, data, cid, tid):
        self.data = data; self.message = FakeMsg(cid, tid); self.answers = []
    async def answer(self, text=None): self.answers.append(text)
class FakeUpdate:
    def __init__(self, q): self.callback_query = q
class FakeMemory:
    def __init__(self): self.pins = {}
    def set_info_pin(self, c, t, m): self.pins[(int(c), int(t))] = int(m)
    def get_info_pin(self, c, t): return self.pins.get((int(c), int(t)))
    def all_info_pins(self): return dict(self.pins)

# --- перехваты ---
SENDS = []; CARDS = []; _MID = [9000]
async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, group="", reply_markup=None):
    SENDS.append({"chat": chat_id, "topic": message_thread_id, "text": text, "kb": reply_markup})
    _MID[0] += 1
    return FakeSent(_MID[0])
async def rec_card(context, bridge, chat_id, topic_id, bike):
    CARDS.append({"chat": chat_id, "topic": topic_id, "bike": bike})
S._send = rec_send
S._send_bike_card = rec_card

def reset():
    SENDS.clear(); CARDS.clear()
    S._INFO_PINNED.clear(); S._INFO_TAP_TS.clear(); S._CARD_LAST.clear()
    S._TOPIC_NAMES.clear(); S._TOPIC_BIKE_OVERRIDE.clear()
    S._MEMORY = FakeMemory()
    S._TOPIC_NAMES[(CHAT, TOPIC)] = BIKE

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []; loop = asyncio.new_event_loop()

# (a) тап info:card → карточка по байку темы
reset()
q = FakeQuery("info:card", CHAT, TOPIC)
loop.run_until_complete(S.handle_info_button(FakeUpdate(q), FakeCtx(), bridge=None))
print("(a) тап → карточка:")
res.append(ok(len(CARDS) == 1 and CARDS[0]["bike"] == BIKE and CARDS[0]["topic"] == TOPIC, "_send_bike_card по байку темы"))
res.append(ok(q.answers and q.answers[0] is None, "q.answer() вызван (спиннер снят)"))

# (d) резолв байка из темы — через override
reset()
S._TOPIC_BIKE_OVERRIDE[(CHAT, TOPIC)] = "XMAX 300 5773"
q = FakeQuery("info:card", CHAT, TOPIC)
loop.run_until_complete(S.handle_info_button(FakeUpdate(q), FakeCtx(), bridge=None))
print("(d) резолв из темы (override):")
res.append(ok(len(CARDS) == 1 and CARDS[0]["bike"] == "XMAX 300 5773", "карточка по override-байку темы"))

# (a') тема без байка → дружелюбный ответ, карточки нет
reset(); S._TOPIC_NAMES.clear()
q = FakeQuery("info:card", CHAT, 9999)
loop.run_until_complete(S.handle_info_button(FakeUpdate(q), FakeCtx(), bridge=None))
print("(a') тема без байка:")
res.append(ok(len(CARDS) == 0 and any("не привязана" in s["text"] for s in SENDS), "карточки нет, сказано «тема не привязана»"))

# (e) обход тротла _card_allowed: кулдаун стоит, тап всё равно даёт карточку
reset()
S._CARD_LAST[(CHAT, TOPIC)] = S._time.time()   # как будто карточку только что слали (тротл бы заблокировал)
q = FakeQuery("info:card", CHAT, TOPIC)
loop.run_until_complete(S.handle_info_button(FakeUpdate(q), FakeCtx(), bridge=None))
print("(e) обход тротла:")
res.append(ok(len(CARDS) == 1, "явный тап ответил картой ДАЖЕ в кулдаун _card_allowed"))

# (g) debounce 5с: два быстрых тапа → одна карточка
reset()
upd = FakeUpdate(FakeQuery("info:card", CHAT, TOPIC))
loop.run_until_complete(S.handle_info_button(upd, FakeCtx(), bridge=None))
loop.run_until_complete(S.handle_info_button(FakeUpdate(FakeQuery("info:card", CHAT, TOPIC)), FakeCtx(), bridge=None))
print("(g) debounce 5с:")
res.append(ok(len(CARDS) == 1, "два тапа за 5с → ОДНА карточка"))

# (b) ensure_info_pin: пусто → send+pin+persist+set; повтор → no-op
reset()
ctx = FakeCtx()
loop.run_until_complete(S.ensure_info_pin(ctx, CHAT, TOPIC))
print("(b) ленивый пин + дедуп:")
res.append(ok(len(SENDS) == 1 and SENDS[0]["kb"] is not None, "сообщение-кнопка отправлено (с клавиатурой)"))
res.append(ok(len(ctx.bot.pinned) == 1, "сообщение закреплено (pin_chat_message)"))
res.append(ok(S._MEMORY.get_info_pin(CHAT, TOPIC) == ctx.bot.pinned[0], "msg_id персистнут в memory.db"))
res.append(ok((CHAT, TOPIC) in S._INFO_PINNED, "ключ в _INFO_PINNED"))
loop.run_until_complete(S.ensure_info_pin(ctx, CHAT, TOPIC))
res.append(ok(len(SENDS) == 1, "повторный вызов → НЕ шлёт второй раз (дедуп)"))

# (b') тема без байка → пин не ставится
reset(); S._TOPIC_NAMES.clear()
ctx = FakeCtx()
loop.run_until_complete(S.ensure_info_pin(ctx, CHAT, 7777))
print("(b') тема без байка → skip:")
res.append(ok(len(SENDS) == 0 and len(ctx.bot.pinned) == 0, "ни сообщения, ни пина (кнопке нечего показывать)"))

# (f) персист round-trip: имитация рестарта (clear set, seed из DB) → ensure НЕ перепинивает
reset()
ctx = FakeCtx()
loop.run_until_complete(S.ensure_info_pin(ctx, CHAT, TOPIC))   # создали пин, в DB
S._INFO_PINNED.clear()                                          # «рестарт»: память процесса сброшена
n = S.seed_info_pins()                                          # seed из memory.db (FakeMemory)
print("(f) персист переживает рестарт:")
res.append(ok((CHAT, TOPIC) in S._INFO_PINNED and n >= 1, "seed_info_pins вернул ключ из DB"))
SENDS.clear()
loop.run_until_complete(S.ensure_info_pin(ctx, CHAT, TOPIC))
res.append(ok(len(SENDS) == 0, "после seed повторного пина НЕТ (рестарт не плодит дубли)"))

# (c) _repin_info после unpin → pin_chat_message со СОХРАНЁННЫМ msg_id
reset()
S._MEMORY.set_info_pin(CHAT, TOPIC, 5151)   # как будто пин был создан ранее
ctx = FakeCtx()
loop.run_until_complete(S._repin_info(ctx, CHAT, TOPIC))
print("(c) пере-пин после unpin ТО:")
res.append(ok(ctx.bot.pinned == [5151], "pin_chat_message вызван со СОХРАНЁННЫМ msg_id=5151"))
# нет записи в DB → пере-пин ничего не делает
reset(); ctx = FakeCtx()
loop.run_until_complete(S._repin_info(ctx, CHAT, TOPIC))
res.append(ok(ctx.bot.pinned == [], "без сохранённого msg_id — пере-пин no-op"))

# (h) pin_info_all владельцем → пинит servicing-темы с байком, скип чужой чат
reset()
S._TOPIC_NAMES[(CHAT, 111)] = "PCX 160 1111"
S._TOPIC_NAMES[(CHAT, 222)] = "ADV 350 2222"
S._TOPIC_NAMES[(-999, 333)] = "не-обслуживание"   # другой чат → скип
ctx = FakeCtx()
n = loop.run_until_complete(S.pin_info_all(ctx))
print("(h) /pin_info_all засев:")
res.append(ok(n == 3, f"засеяно 3 servicing-темы (4255/111/222), чужой чат скип — n={n}"))
res.append(ok((-999, 333) not in S._INFO_PINNED, "тема чужого чата НЕ пиннута"))
res.append(ok(len(ctx.bot.pinned) == 3, "ровно 3 пина (по servicing-темам)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
