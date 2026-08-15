"""Фикс заморозки event loop (разбор таймаутов get_pending 02.07): опрос очереди в
devbot.report_results идёт через asyncio.to_thread + короткий timeout + склейка статусов.
Проверяем: (N1-N2) loop НЕ встаёт и бот отвечает во время долгого Bridge-вызова;
(N3) poll-клиент = своё плечо (45с с 15.08.2026); (N4-N6) get_pending_multi: 1 CSV-вызов / фоллбэк / без добивания
при таймауте; (N7) регресс — done-рапорт через новый путь. Сеть/бот замоканы."""
import sys, asyncio, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB
import bridge_client

SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append(text)

class Ctx:
    bot = FakeBot()

class SlowBridge:
    """get_pending спит СИНХРОННО (имитация тупящего Apps Script /exec). Без url/token →
    _get_poll_bridge опрашивает его как есть; без get_pending_multi → по-статусный фоллбэк."""
    def __init__(s, delay):
        s.delay = delay
        s.calls = 0
    def get_pending(s, status="new", lane=None):
        s.calls += 1
        time.sleep(s.delay)
        return {"ok": True, "items": []}

def _reset(bridge):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._report_seeded = True            # пропустить seed-on-start
    DB.BRIDGE = bridge


# N1: event loop НЕ встаёт: пока report_results висит в Bridge (4×0.15с в потоке),
# параллельная корутина продолжает тикать. При старом (синхронном) коде тиков было бы 0.
def test_loop_not_blocked_during_slow_bridge():
    _reset(SlowBridge(0.15))

    async def scenario():
        report = asyncio.create_task(DB.report_results(Ctx()))
        ticks = 0
        while not report.done():
            await asyncio.sleep(0.01)
            ticks += 1
        await report
        return ticks

    ticks = asyncio.run(scenario())
    assert ticks >= 10, f"loop заморожен: за ~0.6с Bridge-опроса корутина тикнула лишь {ticks} раз"


# N2: «бот отвечает во время долгого Bridge-вызова»: await asyncio.sleep(0.05) параллельно
# опросу возвращается за ~0.05с, а не после всего опроса (при заморозке было бы ~1.6с+).
def test_bot_responds_while_bridge_hangs():
    _reset(SlowBridge(0.4))

    async def scenario():
        t0 = time.monotonic()
        report = asyncio.create_task(DB.report_results(Ctx()))
        await asyncio.sleep(0.05)               # «входящее сообщение» обрабатывается параллельно
        dt = time.monotonic() - t0
        await report
        return dt

    dt = asyncio.run(scenario())
    assert dt < 0.3, f"бот должен ответить за ~0.05с во время Bridge-вызова, ждал {dt:.2f}с"


# N3: poll-клиент опроса очереди — отдельный BridgeClient со СВОИМ плечом (не 60 главного),
# тот же url/token. Число плеча 15.08.2026 поднято 15→45 по замеру распределения (см.
# tests/test_poll_leg.py и docs/artifacts/2026-08-15-poll-leg-not-cutting-live-answers.md):
# предмет теста — «у опроса ОТДЕЛЬНЫЙ клиент со своим, более коротким плечом», а не сама цифра.
def test_poll_bridge_short_timeout():
    real = bridge_client.BridgeClient(url="http://x", token="x")    # основной клиент (timeout=60)
    _reset(real)
    pb = DB._get_poll_bridge()
    assert pb is not real, "для опроса должен создаваться ОТДЕЛЬНЫЙ клиент"
    assert pb.timeout == DB.POLL_TIMEOUT == 45
    assert DB.POLL_TIMEOUT < real.timeout, "плечо опроса короче плеча главного клиента"
    assert (pb.url, pb.token) == (real.url, real.token)
    assert DB._get_poll_bridge() is pb, "клиент кэшируется, не плодится на каждый тик"


# N4: новый Bridge (понимает CSV, отдаёт statuses) → РОВНО один вызов на 4 статуса
def test_multi_one_call_on_new_bridge():
    c = bridge_client.BridgeClient(url="http://x", token="x")
    calls = []
    def fake_call(action, **params):
        calls.append(params.get("status"))
        return {"ok": True, "statuses": params["status"].split(","),
                "items": [{"id": 1, "status": "done", "from": "F"}]}
    c._call = fake_call
    r = c.get_pending_multi(("done", "failed", "needs_approval", "in_progress"))
    assert r["ok"] and len(r["items"]) == 1
    assert calls == ["done,failed,needs_approval,in_progress"]


# N5: старый Bridge (CSV не матчит, поля statuses нет) → фоллбэк по-статусно, статус дописан;
# feature-detect кэшируется — вторая склейка идёт сразу по-статусно, без CSV-пробы
def test_multi_fallback_on_old_bridge():
    c = bridge_client.BridgeClient(url="http://x", token="x")
    calls = []
    def fake_call(action, **params):
        st = params.get("status")
        calls.append(st)
        if "," in st:
            return {"ok": True, "items": []}        # старый getPending_: CSV никого не матчит
        data = {"done": [{"id": 1, "from": "F"}]}
        return {"ok": True, "items": list(data.get(st, []))}
    c._call = fake_call
    r = c.get_pending_multi(("done", "failed"))
    assert r["ok"] and [it["status"] for it in r["items"]] == ["done"]
    assert calls == ["done,failed", "done", "failed"]
    calls.clear()
    r2 = c.get_pending_multi(("done", "failed"))
    assert r2["ok"] and calls == ["done", "failed"], "CSV-проба должна кэшироваться"


# N6: таймаут склеенного вызова → вернуть ошибку КАК ЕСТЬ, Bridge фоллбэком не добивать
def test_multi_timeout_no_fallback_hammer():
    c = bridge_client.BridgeClient(url="http://x", token="x")
    calls = []
    def fake_call(action, **params):
        calls.append(params.get("status"))
        return {"ok": False, "error": "timeout"}
    c._call = fake_call
    r = c.get_pending_multi(("done", "failed"))
    assert not r["ok"] and r["error"] == "timeout"
    assert len(calls) == 1, "в окно деградации Bridge не добиваем по-статусными вызовами"


# N7: регресс — done-задача рапортуется в 328 через новый путь (bridge с get_pending_multi)
def test_report_done_via_multi():
    class MultiBridge:
        def __init__(s, items): s.items = items
        def get_pending_multi(s, statuses, lane=None):
            return {"ok": True, "items": list(s.items)}
    b = MultiBridge([{"id": 5, "from": DB.QUEUE_FROM, "status": "done", "result": "готово: всё ок"}])
    _reset(b)
    asyncio.run(DB.report_results(Ctx()))
    assert any("Задача 5" in s and "done" in s for s in SENDS), f"done-рапорт не пришёл: {SENDS}"
    SENDS.clear()
    asyncio.run(DB.report_results(Ctx()))
    assert SENDS == [], f"повторный тик не должен дублировать рапорт: {SENDS}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов фикса заморозки event loop (to_thread + своё плечо опроса + склейка)")
