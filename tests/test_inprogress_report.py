"""Мок выноса heartbeat/зависания в 328 (шаг D, devbot.report_results): «🔄 в работе» один раз,
«⚠️ зависла» один раз при now-updated>STALL_SEC, без спама на повторных проходах. Сеть/бот замоканы."""
import sys, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB

SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text=""):
        SENDS.append(text)

class Ctx:
    bot = FakeBot()

def _iso(age_sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_sec)
    return t.isoformat().replace("+00:00", "Z")

class FakeBridge:
    """get_pending: done/failed/needs_approval пустые; in_progress = заданный список."""
    def __init__(s, inprogress):
        s.inprogress = inprogress
    def get_pending(s, status="new"):
        if status == "in_progress":
            return {"ok": True, "items": list(s.inprogress)}
        return {"ok": True, "items": []}

def _reset(inprogress):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._report_seeded = True            # пропустить seed-on-start
    DB.BRIDGE = FakeBridge(inprogress)

def run():
    asyncio.run(DB.report_results(Ctx()))


# D1: задача in_progress (свежий updated) → «в работе» РОВНО один раз, «зависла» НЕ шлём
def test_inprogress_announced_once():
    task = {"id": 7, "from": DB.QUEUE_FROM, "task_text": "почини X", "status": "in_progress", "updated": _iso(10)}
    _reset([task])
    run()
    work = [s for s in SENDS if "в работе" in s]
    assert len(work) == 1, f"анонс «в работе» должен быть один раз: {SENDS}"
    assert not any("зависла" in s for s in SENDS), f"свежая задача НЕ зависла: {SENDS}"
    # второй проход — НЕ дублируем
    SENDS.clear()
    run()
    assert SENDS == [], f"повторный проход не должен спамить: {SENDS}"


# D2: чужая тема (from != Filipp-328) → игнор
def test_inprogress_other_source_ignored():
    task = {"id": 8, "from": "pc_agent-205", "task_text": "не наше", "status": "in_progress", "updated": _iso(10)}
    _reset([task])
    run()
    assert SENDS == [], f"задача чужого источника не выносится: {SENDS}"


# D3: in_progress с протухшим updated (>STALL_SEC) → «зависла» РОВНО один раз
def test_stalled_warned_once():
    old = DB.STALL_SEC + 120
    task = {"id": 9, "from": DB.QUEUE_FROM, "task_text": "долгая", "status": "in_progress", "updated": _iso(old)}
    _reset([task])
    run()
    stalled = [s for s in SENDS if "зависла" in s]
    assert len(stalled) == 1, f"предупреждение о зависании один раз: {SENDS}"
    # повторный проход — не дублируем зависание
    SENDS.clear()
    run()
    assert not any("зависла" in s for s in SENDS), f"зависание не должно дублироваться: {SENDS}"


# D4: ровно ниже порога (updated свежее STALL_SEC) → НЕ «зависла»
def test_below_threshold_not_stalled():
    task = {"id": 10, "from": DB.QUEUE_FROM, "task_text": "норм", "status": "in_progress", "updated": _iso(DB.STALL_SEC - 60)}
    _reset([task])
    run()
    assert not any("зависла" in s for s in SENDS), f"ниже порога — не зависла: {SENDS}"


# D5: битый updated → зависание НЕ объявляем (ложняка нет)
def test_bad_updated_no_stall():
    task = {"id": 11, "from": DB.QUEUE_FROM, "task_text": "x", "status": "in_progress", "updated": "не-дата"}
    _reset([task])
    run()
    assert not any("зависла" in s for s in SENDS), f"битая дата → без тревоги: {SENDS}"
    assert any("в работе" in s for s in SENDS), "но анонс «в работе» всё равно идёт"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов выноса in_progress в 328 (шаг D)")
