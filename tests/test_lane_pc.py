"""Вторая полоса дев-контура O4: lane=pc (тема PC-дев, 04.07.2026). Маршрутизация lane:
(L1-L4) bridge_client шлёт lane ТОЛЬКО если передан (старый Bridge не ломается);
(L5) _try_enqueue: pc-полоса → метки Filipp-pc[-dev] + lane='pc', декомпозиция на pc не поддержана,
328 — как раньше БЕЗ lane; (L6) handle_command: тема PC-дев только от Филиппа, выключена без env;
(L7) report_results разносит карточки по полосам (pc → тема PC-дев, vps → 328);
(L8) splinter.is_ignored_thread игнорит тему PC-дев из env;
(L9) боевой id темы = 829 (прописан в .env 04.07.2026): сообщение в 829 → очередь lane=pc,
splinter тему 829 игнорит, .env реально содержит PC_DEV_TOPIC_ID=829;
(L10) VPS-демон pc-задачи НЕ берёт: его опрос идёт БЕЗ lane → Bridge дефолтит vps. Сеть/бот замоканы."""
import sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB
import bridge_client

PC_TOPIC = 777  # тестовый id темы PC-дев (боевой Филипп даст после создания темы)


def _set_pc(on=True):
    if on:
        os.environ["PC_DEV_TOPIC_ID"] = str(PC_TOPIC)
    else:
        os.environ.pop("PC_DEV_TOPIC_ID", None)


def _client_with_capture():
    c = bridge_client.BridgeClient(url="http://x", token="x")
    calls = []
    def fake(action, **params):
        calls.append((action, params))
        return {"ok": True, "id": 1, "items": [], "statuses": ["done", "failed"], "task": {}}
    c._post = fake
    c._call = fake
    return c, calls


# L1: enqueue_task — lane уходит в payload ТОЛЬКО если передан
def test_enqueue_lane_param():
    c, calls = _client_with_capture()
    c.enqueue_task("Filipp-328-dev", "x")
    assert calls[-1] == ("enqueue_task", {"from": "Filipp-328-dev", "task_text": "x"}), \
        f"без lane параметр НЕ шлётся (совместимость со старым Bridge): {calls[-1]}"
    c.enqueue_task("Filipp-pc-dev", "y", lane="pc")
    assert calls[-1][1].get("lane") == "pc", f"lane='pc' должен уйти в payload: {calls[-1]}"


# L2: get_pending — lane опционален
def test_get_pending_lane_param():
    c, calls = _client_with_capture()
    c.get_pending("new")
    assert "lane" not in calls[-1][1], f"без lane параметр НЕ шлётся: {calls[-1]}"
    c.get_pending("new", lane="all")
    assert calls[-1][1].get("lane") == "all", f"lane='all' должен уйти: {calls[-1]}"


# L3: get_pending_multi — lane пробрасывается и в CSV-вызов, и в по-статусный фоллбэк
def test_get_pending_multi_lane_param():
    c = bridge_client.BridgeClient(url="http://x", token="x")
    calls = []
    def fake_new(action, **params):
        calls.append(params)
        return {"ok": True, "statuses": params["status"].split(","), "items": []}
    c._call = fake_new
    c.get_pending_multi(("done", "failed"), lane="all")
    assert calls == [{"status": "done,failed", "lane": "all"}], f"CSV-вызов без lane: {calls}"
    c2 = bridge_client.BridgeClient(url="http://x", token="x")
    calls2 = []
    def fake_old(action, **params):
        calls2.append(params)
        return {"ok": True, "items": []}          # старый Bridge: без поля statuses → фоллбэк
    c2._call = fake_old
    c2.get_pending_multi(("done", "failed"), lane="all")
    assert all(p.get("lane") == "all" for p in calls2), f"фоллбэк потерял lane: {calls2}"


# L4: claim_task — опциональный lane-guard
def test_claim_lane_param():
    c, calls = _client_with_capture()
    c.claim_task(5)
    assert calls[-1] == ("claim_task", {"id": 5}), f"без lane параметр НЕ шлётся: {calls[-1]}"
    c.claim_task(5, lane="pc")
    assert calls[-1][1].get("lane") == "pc", f"lane-guard должен уйти: {calls[-1]}"


class EnqBridge:
    def __init__(s):
        s.calls = []
    def enqueue_task(s, frm, txt, lane=None):
        s.calls.append((frm, txt, lane))
        return {"ok": True, "id": 42}


# L5: _try_enqueue — маршрутизация меток/lane по полосам
def test_try_enqueue_lanes():
    b = EnqBridge()
    r = DB._try_enqueue("тз: почини Y", b, lane="pc")
    assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEV, "почини Y", "pc"), f"pc-ТЗ: {b.calls}"
    assert "PC" in r and "42" in r
    DB._try_enqueue("задача: проверь Z", b, lane="pc")
    assert b.calls[-1] == (DB.QUEUE_FROM_PC, "проверь Z", "pc"), f"pc-задача: {b.calls}"
    n = len(b.calls)
    r = DB._try_enqueue("декомпозируй: большое ТЗ", b, lane="pc")
    assert len(b.calls) == n and "не поддержан" in r, "декомпозиция на pc-полосе НЕ ставится в очередь"
    DB._try_enqueue("тз: как раньше", b)                     # 328 (vps) — регресс
    assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "как раньше", None), \
        f"полоса vps: старая метка и БЕЗ lane: {b.calls}"
    assert DB._try_enqueue("просто текст", b, lane="pc") is None, "не-префикс → None (мимо очереди)"


SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append((message_thread_id, text, reply_markup))

class Ctx:
    bot = FakeBot()

class FakeUser:
    def __init__(s, uid): s.id = uid

class FakeMsg:
    def __init__(s, text, topic, uid=DB.DEVBOT_USER):
        s.text = text
        s.message_thread_id = topic
        s.from_user = FakeUser(uid)
        s.chat_id = DB.HQ_CHAT_ID


# L6: handle_command — тема PC-дев: только Филипп, только с env; не-префикс → подсказка
def test_handle_command_pc_topic():
    _set_pc(True)
    try:
        b = EnqBridge()
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("тз: собери X", PC_TOPIC), Ctx(), b))
        assert b.calls == [(DB.QUEUE_FROM_PC_DEV, "собери X", "pc")], f"enqueue lane=pc: {b.calls}"
        assert SENDS and SENDS[0][0] == PC_TOPIC, f"ответ в тему PC-дев: {SENDS}"
        b2 = EnqBridge()
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("тз: чужой", PC_TOPIC, uid=111), Ctx(), b2))
        assert b2.calls == [] and SENDS == [], "чужой юзер в теме PC-дев — полный игнор"
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("health", PC_TOPIC), Ctx(), EnqBridge()))
        assert len(SENDS) == 1 and "PC-дев" in SENDS[0][1], \
            f"не-префикс в PC-дев → подсказка, зелёный allowlist НЕ гоняем: {SENDS}"
    finally:
        _set_pc(False)
    b3 = EnqBridge()
    SENDS.clear()
    asyncio.run(DB.handle_command(FakeMsg("тз: без env", PC_TOPIC), Ctx(), b3))
    assert b3.calls == [] and SENDS == [], "env не задан → полоса pc выключена, тема чужая"


class MultiBridge:
    def __init__(s, items): s.items = items
    def get_pending_multi(s, statuses, lane=None):
        s.lane = lane
        return {"ok": True, "items": list(s.items)}


def _reset_report(bridge):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._report_seeded = True
    DB.BRIDGE = bridge


# L7: report_results — карточки pc-задач идут в тему PC-дев, vps — в 328; опрос с lane='all'
def test_report_routing_by_lane():
    _set_pc(True)
    # L7 проверяет маршрут по ПОЛОСАМ (pc→PC_TOPIC, vps→328). Единый инбокс (INBOX_TOPIC_ID, ст3)
    # перекрывает маршрут approve-карточек на тему-инбокс — его поведение покрыто отдельно в
    # test_inbox.py (I4/I5). Здесь инбокс детерминированно ВЫКЛючаем, чтобы не течь ambient .env
    # (INBOX_TOPIC_ID=1160) и тестировать именно полосовую маршрутизацию.
    _inbox_saved = os.environ.pop("INBOX_TOPIC_ID", None)
    try:
        b = MultiBridge([
            {"id": 1, "from": DB.QUEUE_FROM_PC_DEV, "lane": "pc", "status": "done", "result": "готово pc"},
            {"id": 2, "from": DB.QUEUE_FROM, "lane": "vps", "status": "done", "result": "готово vps"},
            {"id": 3, "from": DB.QUEUE_FROM_PC, "lane": "pc", "status": "needs_approval", "result": "clasp push"},
        ])
        _reset_report(b)
        asyncio.run(DB.report_results(Ctx()))
        assert b.lane == "all", f"опрос очереди должен идти с lane='all': {b.lane}"
        topics = {}
        for tid, text, kb in SENDS:
            for qid in ("1", "2", "3"):
                if f"адача {qid}" in text:
                    topics[qid] = (tid, kb)
        assert topics["1"][0] == PC_TOPIC, f"done pc → тема PC-дев: {SENDS}"
        assert topics["2"][0] == DB.DEVBOT_TOPIC, f"done vps → 328: {SENDS}"
        assert topics["3"][0] == PC_TOPIC and topics["3"][1] is not None, \
            f"needs_approval pc → тема PC-дев С КНОПКАМИ: {SENDS}"
        # старый Bridge (без поля lane) → полоса pc узнаётся по метке from
        b2 = MultiBridge([{"id": 4, "from": DB.QUEUE_FROM_PC, "status": "done", "result": "ok"}])
        _reset_report(b2)
        asyncio.run(DB.report_results(Ctx()))
        assert SENDS and SENDS[0][0] == PC_TOPIC, f"без поля lane маршрут по from: {SENDS}"
    finally:
        _set_pc(False)
        if _inbox_saved is not None:
            os.environ["INBOX_TOPIC_ID"] = _inbox_saved
        DB.BRIDGE = None


# L8: splinter.is_ignored_thread — тема PC-дев игнорится (лениво из env)
def test_splinter_ignores_pc_topic():
    import splinter
    _set_pc(True)
    try:
        assert splinter.is_ignored_thread(splinter.HQ_CHAT_ID, PC_TOPIC), "тема PC-дев — игнор Splinter"
        assert splinter.is_ignored_thread(splinter.HQ_CHAT_ID, 328), "328 игнорится как раньше"
        assert not splinter.is_ignored_thread(splinter.HQ_CHAT_ID, 999), "прочие темы HQ — не игнор"
        assert not splinter.is_ignored_thread(-1, PC_TOPIC), "чужой чат — не игнор"
    finally:
        _set_pc(False)
    assert not splinter.is_ignored_thread(splinter.HQ_CHAT_ID, PC_TOPIC), \
        "env не задан → тема не игнорится (полоса выключена)"


# L9: боевой id темы PC-дев = 829 — маршрутизация в проде (env как в .env)
def test_pc_topic_829_live_id():
    env_path = "/root/turbobaby-manager-bot/.env"
    if os.path.exists(env_path):                       # конфиг-дрейф: строка должна быть в .env
        with open(env_path, encoding="utf-8") as f:
            assert "PC_DEV_TOPIC_ID=829" in f.read(), ".env потерял PC_DEV_TOPIC_ID=829"
    os.environ["PC_DEV_TOPIC_ID"] = "829"
    try:
        b = EnqBridge()
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("тз: проверь полосу", 829), Ctx(), b))
        assert b.calls == [(DB.QUEUE_FROM_PC_DEV, "проверь полосу", "pc")], \
            f"«тз:» в теме 829 → enqueue lane=pc: {b.calls}"
        assert SENDS and SENDS[0][0] == 829, f"ответ-карточка в тему 829: {SENDS}"
        b2 = EnqBridge()
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("задача: пингани ПК", 829), Ctx(), b2))
        assert b2.calls == [(DB.QUEUE_FROM_PC, "пингани ПК", "pc")], \
            f"«задача:» в теме 829 → enqueue lane=pc: {b2.calls}"
        b3 = EnqBridge()
        SENDS.clear()
        asyncio.run(DB.handle_command(FakeMsg("тз: чужой", 829, uid=111), Ctx(), b3))
        assert b3.calls == [] and SENDS == [], "тема 829: не-Филипп — полный игнор"
        import splinter
        assert splinter.is_ignored_thread(splinter.HQ_CHAT_ID, 829), "splinter игнорит тему 829"
    finally:
        os.environ.pop("PC_DEV_TOPIC_ID", None)


# L10: VPS-демон pc-задачи НЕ берёт — process_new опрашивает БЕЗ lane (Bridge дефолтит vps)
def test_vps_daemon_polls_without_lane():
    import orchestrator_daemon as OD
    calls = []
    class PollBridge:
        def get_pending(s, status, **kw):
            calls.append((status, dict(kw)))
            return {"ok": True, "items": []}
    old = OD.bc
    OD.bc = PollBridge()
    try:
        OD.process_new()
    finally:
        OD.bc = old
    assert calls == [("new", {})], \
        f"опрос VPS-демона должен идти БЕЗ lane (Bridge дефолтит vps → pc-задачи невидимы): {calls}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов второй полосы lane=pc (Bridge-клиент / devbot / splinter)")
