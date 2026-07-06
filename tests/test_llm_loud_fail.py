"""§12: молчаливых потерь LLM БОЛЬШЕ НЕТ (Фаза 2 — громкий провал API-пути).
Проверяет:
- money upstream-down → громкий пуш «впиши руками» + ответ в чат (проводка НЕ теряется тихо);
- ЧЕСТНЫЙ type:none (модель ответила) → тихо, как раньше (пуша НЕТ);
- vision-чек-с-суммой (деньги) → пуш; vision-фото-байк (не деньги) → лог+счётчик, БЕЗ пуша;
- дедуп (Поправка А): N потерь за окно → 1 громкий + схлопка «ещё N»;
- quick()/vision() raise_on_upstream: upstream-down → SplinterLLMError; деф off → '' (контракт цел).
Реальных сетевых/денежных вызовов НЕТ — notify/_send/claude замоканы."""
import os, sys, json, asyncio, datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.pop("SPLINTER_LLM_VIA_CLI", None)
os.environ["PRETOOL_NOPUSH"] = "1"     # страховка: даже если что-то прорвётся к боевому notify

import anthropic
import claude_client as CC
import splinter as S
import notify as N

MONEY_CHAT = -1003873906891   # Money Cashflow

# ---- перехват исходящих ----
PUSHES = []       # тексты громких пушей владельцу
SENDS = []        # тексты ответов в чат


def _fake_notify(text, *a, **k):
    PUSHES.append(text)
    return True


async def _rec_send(context, *, chat_id, text, message_thread_id=None, **kw):
    SENDS.append(text)


N.notify = _fake_notify
S._send = _rec_send


def reset():
    PUSHES.clear()
    SENDS.clear()
    S._llm_loss.update({"loud_ts": 0.0, "collapsed": 0, "quiet": 0})
    S._PENDING_CURRENCY.clear()


class Msg:
    def __init__(self, text, username="pleummmm"):
        self.text = text
        self.caption = None
        self.photo = None
        self.chat_id = MONEY_CHAT
        self.message_thread_id = None
        self.date = datetime.datetime(2026, 7, 6, 10, 0, 0, tzinfo=datetime.timezone.utc)
        self.message_id = 555
        self.from_user = type("U", (), {"username": username, "id": 111})()


class FakeBridge:
    def get_balance(self, **kw): return {"balance": {}}
    def add_transaction(self, **kw): return {"ok": True}


class ClaudeUpstreamDown:
    """quick() при кассовом разборе бросает upstream-down (как платный API с кредит=0 / CLI-обвал)."""
    def quick(self, system, text, max_tokens=400, raise_on_upstream=False):
        if raise_on_upstream:
            raise CC.SplinterLLMError("quick upstream down: BadRequestError")
        return ""
    def vision(self, *a, **k): return ""


class ClaudeTypeNone:
    """quick() честно отвечает type:none (модель жива, просто болтовня) — это НЕ потеря."""
    def quick(self, system, text, max_tokens=400, raise_on_upstream=False):
        return '{"type":"none"}'
    def vision(self, *a, **k): return ""


loop = asyncio.new_event_loop()
results = []


def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    results.append(cond)


# ---- (1) money upstream-down → громкий пуш + ответ в чат, НЕ тихо ----
reset()
loop.run_until_complete(S._handle_money(Msg("-500 бензин"), None, FakeBridge(), ClaudeUpstreamDown()))
ok(len(PUSHES) == 1, "(1) money upstream-down → РОВНО один громкий пуш владельцу")
ok(PUSHES and "впиши руками" in PUSHES[0].lower(), "(1) пуш содержит «впиши руками»")
ok(PUSHES and "-500 бензин" in PUSHES[0], "(1) пуш несёт исходный текст операции (для ручного ввода)")
ok(len(SENDS) == 1, "(1) ответ в чат отправлен (Пым видит, что не обработали)")
ok(S._llm_loss["collapsed"] == 0, "(1) первый в окне — не схлопнут")

# ---- (2) честный type:none → тихо (как раньше), пуша НЕТ ----
reset()
loop.run_until_complete(S._handle_money(Msg("есть работа сегодня?"), None, FakeBridge(), ClaudeTypeNone()))
ok(len(PUSHES) == 0, "(2) честный type:none → НИ одного пуша (тихо, как раньше)")
ok(len(SENDS) == 0, "(2) type:none от Пыма → молчим (не owner-mention)")

# ---- (3) vision-чек-с-суммой (ДЕНЬГИ) → пуш ----
reset()
pushed = S._note_llm_loss(money=True, wallet="Money Cashflow", lost_text="чек 4900", kind="чек-с-суммой")
ok(pushed and len(PUSHES) == 1, "(3) vision-чек-с-суммой (деньги) → громкий пуш")

# ---- (4) vision-фото-байк (НЕ деньги) → лог + тихий счётчик, БЕЗ пуша ----
reset()
pushed = S._note_llm_loss(money=False, kind="фото-байк(ТО)", detail="upstream down")
ok(not pushed and len(PUSHES) == 0, "(4) vision-фото-байк (не деньги) → БЕЗ пуша")
ok(S._llm_loss["quiet"] == 1, "(4) тихий счётчик не-денежных потерь увеличился")

# ---- (5) дедуп: N потерь за окно → 1 громкий + схлопка «ещё N» ----
reset()
for i in range(5):
    S._note_llm_loss(money=True, wallet="Money Cashflow", lost_text=f"оп{i}", kind="money")
ok(len(PUSHES) == 1, "(5) 5 потерь в окне → РОВНО 1 громкий пуш (владельца не спамим)")
ok(S._llm_loss["collapsed"] == 4, "(5) остальные 4 схлопнуты в счётчик окна")
# окно истекло → следующий пуш громкий и упоминает схлопнутые
S._llm_loss["loud_ts"] = S._time.time() - (S._LLM_LOSS_WINDOW + 100)
S._note_llm_loss(money=True, wallet="Money Cashflow", lost_text="оп-след", kind="money")
ok(len(PUSHES) == 2, "(5) после истечения окна → новый громкий пуш")
ok("ещё 4" in PUSHES[1], "(5) новый пуш несёт хвост схлопки «ещё 4»")
ok(S._llm_loss["collapsed"] == 0, "(5) счётчик схлопки сброшен после выката хвоста")

# ---- (6) claude_client.quick/vision raise_on_upstream ----
class _RaisingMsgs:
    def create(self, **kw):
        raise anthropic.AnthropicError("Your credit balance is too low")
class _RaisingClient:
    def __init__(self): self.messages = _RaisingMsgs()

c = CC.ClaudeClient()
c.client = _RaisingClient()
# default (деф off) → graceful '' (контракт как раньше — happy-path/некритичные callers целы)
ok(c.quick("SYS", "txt") == "", "(6) quick() деф off → '' на upstream-down (контракт цел)")
ok(c.vision("SYS", b"img") == "", "(6) vision() деф off → '' на upstream-down (контракт цел)")
# opt-in → типизированный SplinterLLMError (кассовый/денежный путь)
_raised = False
try:
    c.quick("SYS", "txt", raise_on_upstream=True)
except CC.SplinterLLMError:
    _raised = True
ok(_raised, "(6) quick(raise_on_upstream=True) → SplinterLLMError на upstream-down")
_raised = False
try:
    c.vision("SYS", b"img", raise_on_upstream=True)
except CC.SplinterLLMError:
    _raised = True
ok(_raised, "(6) vision(raise_on_upstream=True) → SplinterLLMError на upstream-down")


if __name__ == "__main__":
    print(f"OK — {sum(results)}/{len(results)} проверок test_llm_loud_fail")
    sys.exit(0 if all(results) else 1)
