"""Фикс D (задержка после «Да»): кэш интервалов отдаёт то же значение одним read_doc;
квитанция (_emit_summary) шлётся ДО фоновой доп.проверки ТО (_check_other_services)."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S

CHAT = -1002751134848; TOPIC = 73
KB_TEXT = (
    "бла бла\n```json SERVICE_INTERVALS\n"
    '{"oil": {"scooter": 4000, "moto": 5000}, "abs": 10000, "airfilter": 20000,'
    ' "scooter_keywords": ["nmax", "pcx"], "moto_default": 5000}\n```\nещё текст\n'
)

class CountBridge:
    """Считает read_doc — проверяем, что кэш не бьёт в Drive повторно."""
    def __init__(self): self.read_doc_calls = 0
    def _call(self, op, **kw):
        if op == "read_doc":
            self.read_doc_calls += 1
            return {"ok": True, "text": KB_TEXT}
        return {"ok": True}

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# ---- (1) КЭШ ИНТЕРВАЛОВ: prewarm + N вызовов = ОДИН read_doc, значение стабильно ----
S._SVC_INTERVALS_CACHE["data"] = None; S._SVC_INTERVALS_CACHE["ts"] = 0.0   # холодный старт
br = CountBridge()
S.prewarm_service_intervals(br)                       # прогрев на «старте»
v1 = S._service_interval("oil", "nmax 155 black 4255", br)
v2 = S._service_interval("oil", "nmax 155 black 4255", br)
v3 = S._service_interval("abs", "nmax 155 black 4255", br)
print("(1) кэш интервалов:")
res.append(ok(br.read_doc_calls == 1, f"read_doc книги знаний ровно 1 раз на прогрев+3 вызова (а {br.read_doc_calls})"))
res.append(ok(v1 == 4000 and v2 == 4000, "oil(scooter)=4000 стабильно из кэша"))
res.append(ok(v3 == 10000, "abs=10000 из того же кэша"))
res.append(ok(S._SVC_INTERVALS_TTL >= 3600, f"TTL ≥ 1 час (фикс D), сейчас {S._SVC_INTERVALS_TTL}"))

# ---- (2) ПОРЯДОК: квитанция (_emit_summary) ДО _check_other_services ----
ORDER = []
async def fake_emit(context, chat_id, topic_id, bike): ORDER.append("summary")
async def fake_other(context, bridge, chat_id, topic_id, bike, km): ORDER.append("other")
async def fake_clear(context, chat_id, topic_id): ORDER.append("clear")
S._emit_summary = fake_emit
S._check_other_services = fake_other
S._clear_cycle_msgs = fake_clear
S._run_service_tracker = lambda bridge, c, t, b, m: {"km": 24302, "status": "ok", "next_km": 28302, "km_left": 4000, "stype": "oil"}
S._sp_open = lambda bridge, c, t, b: None        # нет открытой заявки → ветка квитанции
S._summary_acc = lambda c, t: {}

loop = asyncio.new_event_loop()
loop.run_until_complete(S._after_mileage(None, br, CHAT, TOPIC, "NMAX 4255", 24302))
loop.close()
print("(2) порядок отправки:")
res.append(ok("summary" in ORDER and "other" in ORDER, "и квитанция, и доп.проверка вызваны"))
res.append(ok(ORDER.index("summary") < ORDER.index("other"),
              f"квитанция РАНЬШЕ доп.проверки ТО (порядок: {ORDER})"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
