"""Мок выноса heartbeat/зависания в 328 (шаг D, devbot.report_results): «🔄 в работе» один раз,
«⚠️ зависла» один раз — с порогом PER-ЗАДАЧА (_stall_threshold_sec = штатный потолок + люфт).
Урок задачи 287 (13.07.2026): «долго работает» ≠ «умерла» — долгое «тз:» (до 45 мин) молчит до
потолка; тревога один раз после потолка; done после тревоги → только штатный рапорт, без «отбоя».
Сеть/бот замоканы."""
import sys, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# ПРИНУДИТЕЛЬНАЯ изоляция потолков (урок test_curator: headless-тест наследует env демона с
# боевыми значениями из .env — setdefault НЕ хватает, присваиваем жёстко):
os.environ["TASK_TIMEOUT"] = "600"
os.environ["TASK_TIMEOUT_DEV"] = "2700"
os.environ["PC_STEP_TIMEOUT"] = "3600"
import devbot as DB

SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", **kw):
        SENDS.append(text)

class Ctx:
    bot = FakeBot()

def _iso(age_sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_sec)
    return t.isoformat().replace("+00:00", "Z")

class FakeBridge:
    """get_pending по статусам: in_progress/done — заданные списки, прочее пусто."""
    def __init__(s, inprogress, done=None):
        s.inprogress = inprogress
        s.done = done or []
    def get_pending(s, status="new", lane=None):
        if status == "in_progress":
            return {"ok": True, "items": list(s.inprogress)}
        if status == "done":
            return {"ok": True, "items": list(s.done)}
        return {"ok": True, "items": []}

def _reset(inprogress, done=None):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    # Сигнал «очередь пуста» (05.08.2026) — состояние ПЕРЕХОДА, а не снимка: чистим вместе с
    # дедупами, иначе занятость из соседнего кейса протекает и одиночный снимок рождает сигнал.
    DB._queue_busy = None; DB._closed_since_busy = []
    DB._report_seeded = True            # пропустить seed-on-start
    DB.BRIDGE = FakeBridge(inprogress, done)

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


# D3: быстрая «задача:» с updated старше своего порога (600+120) → «зависла» РОВНО один раз
def test_stalled_warned_once():
    task = {"id": 9, "from": DB.QUEUE_FROM, "task_text": "долгая", "status": "in_progress", "updated": _iso(0)}
    task["updated"] = _iso(DB._stall_threshold_sec(task) + 120)
    _reset([task])
    run()
    stalled = [s for s in SENDS if "зависла" in s]
    assert len(stalled) == 1, f"предупреждение о зависании один раз: {SENDS}"
    # повторный проход — не дублируем зависание (анти-спам: не каждые 12 мин)
    SENDS.clear()
    run()
    assert not any("зависла" in s for s in SENDS), f"зависание не должно дублироваться: {SENDS}"


# D4: ровно ниже порога быстрой задачи → НЕ «зависла»
def test_below_threshold_not_stalled():
    task = {"id": 10, "from": DB.QUEUE_FROM, "task_text": "норм", "status": "in_progress", "updated": _iso(0)}
    task["updated"] = _iso(DB._stall_threshold_sec(task) - 60)
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


# ===== ГОЛДЕНЫ инцидента 287 (13.07.2026): порог per-задача, «долго» ≠ «умерла» =====

# G1: дев-ТЗ «тз:» in_progress 30 мин при потолке 45 → ТИШИНА (ложняк 287 убит)
def test_dev_task_30min_silence():
    task = {"id": 287, "from": DB.QUEUE_FROM_DEV, "task_text": "тз: долгий headless-заход",
            "status": "in_progress", "updated": _iso(1800)}
    _reset([task])
    run()
    assert not any("зависла" in s for s in SENDS), f"30 мин при потолке 45 — не зависла: {SENDS}"
    assert any("в работе" in s for s in SENDS), "анонс «в работе» идёт как раньше"


# G2: дев-ТЗ ЗА потолком (45 мин + люфт) без терминала → РОВНО одно предупреждение, без повтора
def test_dev_task_past_cap_one_warning():
    task = {"id": 12, "from": DB.QUEUE_FROM_DEV, "task_text": "тз: демон умер",
            "status": "in_progress", "updated": _iso(0)}
    thr = DB._stall_threshold_sec(task)
    assert thr == 2700 + DB.STALL_GRACE_SEC, f"потолок дев-ТЗ = TASK_TIMEOUT_DEV+люфт: {thr}"
    task["updated"] = _iso(thr + 60)
    _reset([task])
    run()
    stalled = [s for s in SENDS if "зависла" in s]
    assert len(stalled) == 1, f"одно предупреждение за потолком: {SENDS}"
    assert "потолке" in stalled[0], f"в тревоге виден потолок задачи: {stalled[0]}"
    SENDS.clear()
    run()
    assert not any("зависла" in s for s in SENDS), f"повторов нет: {SENDS}"


# G3: done ПОСЛЕ предупреждения → штатный рапорт done, НИКАКОГО «отбоя» и новых тревог
def test_done_after_warning_silence():
    task = {"id": 13, "from": DB.QUEUE_FROM_DEV, "task_text": "тз: медленная",
            "status": "in_progress", "updated": _iso(0)}
    task["updated"] = _iso(DB._stall_threshold_sec(task) + 60)
    _reset([task])
    run()
    assert any("зависла" in s for s in SENDS), f"сначала предупреждение: {SENDS}"
    # задача завершилась: уходит из in_progress, появляется в done
    done_it = dict(task); done_it["status"] = "done"; done_it["result"] = "готово"
    DB.BRIDGE = FakeBridge([], [done_it])
    SENDS.clear()
    run()
    assert any("done" in s for s in SENDS), f"штатный рапорт done идёт: {SENDS}"
    assert not any("зависла" in s for s in SENDS), f"тревога снята молча: {SENDS}"
    assert not any("отбой" in s.lower() for s in SENDS), f"«отбой» не шлём: {SENDS}"
    # и дальше — полная тишина по этой задаче
    SENDS.clear()
    run()
    assert SENDS == [], f"после done — больше ничего: {SENDS}"


# G4: полоса pc — потолок PC_STEP_TIMEOUT: 50 мин → тишина; за потолком → одна тревога с pc-хинтом
def test_pc_lane_cap():
    task = {"id": 14, "from": DB.QUEUE_FROM_PC_DEV, "lane": "pc", "task_text": "шаг на ПК",
            "status": "in_progress", "updated": _iso(3000)}
    assert DB._stall_threshold_sec(task) == 3600 + DB.STALL_GRACE_SEC
    _reset([task])
    run()
    assert not any("зависла" in s for s in SENDS), f"50 мин при потолке 60 — тишина: {SENDS}"
    task["updated"] = _iso(3600 + DB.STALL_GRACE_SEC + 60)
    _reset([task])
    run()
    stalled = [s for s in SENDS if "зависла" in s]
    assert len(stalled) == 1 and "ПК" in stalled[0], f"за потолком pc — одна тревога с pc-хинтом: {SENDS}"


# G5: классификация потолков — куратор/дек = дев-потолок, быстрая = 600, мусорный env не валит
def test_threshold_classification():
    dev = DB._stall_threshold_sec({"from": DB.QUEUE_FROM_DEV})
    assert DB._stall_threshold_sec({"from": DB.QUEUE_FROM_CURATOR}) == dev, "куратор = дев-потолок (как у демона)"
    assert DB._stall_threshold_sec({"from": DB.QUEUE_FROM_DEC}) == dev, "декомпозер = дев-потолок"
    assert DB._stall_threshold_sec({"from": DB.QUEUE_FROM}) == 600 + DB.STALL_GRACE_SEC
    old = os.environ.get("TASK_TIMEOUT")
    os.environ["TASK_TIMEOUT"] = "мусор"
    try:
        assert DB._stall_threshold_sec({"from": DB.QUEUE_FROM}) == 600 + DB.STALL_GRACE_SEC, \
            "мусорный env → дефолт, порог не падает"
    finally:
        os.environ["TASK_TIMEOUT"] = old if old is not None else "600"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов выноса in_progress в 328 (шаг D + голдены 287)")
