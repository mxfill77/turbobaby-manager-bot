"""ЕДИНЫЙ ИНБОКС ПОДТВЕРЖДЕНИЙ (ст3 оркестратора O4, KB_MASTER §7 Вариант Б, 06.07.2026).
Тема-инбокс = env INBOX_TOPIC_ID (боевой 1160). Проверяем 4 части плана + гейты:
(I1) build_inbox — cross-lane список: needs_approval ОБЕИХ полос (vps+pc) в одном /inbox, опрос lane='all';
(I2) build_inbox — дедуп В СПИСКЕ по отпечатку конверта (одинаковые op+текст → одна строка ×N + список id);
(I3) build_inbox — пустой инбокс → человеческая строка «пуст»;
(I4) report_results ФОЛЛБЭК-БЕЗ-РЕГРЕССА: INBOX не задан → approve-карточки по СТАРЫМ полосам (vps→328, pc→829);
(I5) report_results: INBOX задан → approve ОБЕИХ полос сходятся в тему-инбокс; done/failed ОСТАЮТСЯ по полосам;
(I6) splinter.is_ignored_thread игнорит тему-инбокс из env (+ боевой id 1160 в .env);
(I7) /inbox (bot.cmd_inbox) — ТОЛЬКО Филипп (504608015); чужой → игнор, build_inbox НЕ зван.
Тяжёлые зависимости bot.py (Bridge/Claude/Memory/Auditor) застаблены ДО импорта — сеть/ключи/бот не трогаем."""
import sys, types, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ.pop("INBOX_TOPIC_ID", None)   # чистый старт: инбокс по умолчанию выключен


# --- стабы тяжёлых модулей bot.py (паттерн test_audit_button) ---
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
import devbot as DB
import splinter

PC_TOPIC = 777        # тестовый id темы PC-дев
INBOX = 1160          # боевой id темы-инбокса


def _set_pc(on=True):
    if on:
        os.environ["PC_DEV_TOPIC_ID"] = str(PC_TOPIC)
    else:
        os.environ.pop("PC_DEV_TOPIC_ID", None)


def _set_inbox(on=True):
    if on:
        os.environ["INBOX_TOPIC_ID"] = str(INBOX)
    else:
        os.environ.pop("INBOX_TOPIC_ID", None)


# ===================== build_inbox (части в+г) =====================
class InboxBridge:
    def __init__(s, items): s.items = items; s.calls = []
    def get_pending(s, status, lane=None):
        s.calls.append((status, lane))
        return {"ok": True, "items": list(s.items)}


# I1: cross-lane — vps+pc в ОДНОМ списке, опрос идёт lane='all'
def test_build_inbox_cross_lane():
    b = InboxBridge([
        {"id": 10, "lane": "vps", "from": DB.QUEUE_FROM_DEV, "result": "op=git_push | запушить фикс X"},
        {"id": 11, "lane": "pc", "from": DB.QUEUE_FROM_PC_DEV, "result": "op=other | clasp redeploy Bridge"},
    ])
    txt = DB.build_inbox(b)
    assert b.calls == [("needs_approval", "all")], f"опрос ОБЕИХ полос lane='all': {b.calls}"
    assert "10" in txt and "11" in txt, f"обе задачи в списке: {txt}"
    assert "vps" in txt and "pc" in txt, f"обе полосы помечены: {txt}"
    assert "открыто 2" in txt, f"счётчик открытых: {txt}"


# I2: дедуп В СПИСКЕ по отпечатку (одинаковые op+текст → одна строка ×N + оба id); разный op — отдельно
def test_build_inbox_dedup():
    b = InboxBridge([
        {"id": 20, "lane": "vps", "from": DB.QUEUE_FROM_DEV, "result": "op=other | одинаковый конверт"},
        {"id": 21, "lane": "vps", "from": DB.QUEUE_FROM_DEV, "result": "op=other | одинаковый конверт"},
        {"id": 22, "lane": "vps", "from": DB.QUEUE_FROM_DEV, "result": "op=git_push | другой конверт"},
    ])
    txt = DB.build_inbox(b)
    assert "открыто 3" in txt, f"всего 3 открытых (дедуп — про строки, не про счётчик): {txt}"
    assert "×2" in txt, f"одинаковые конверты схлопнуты в ×2: {txt}"
    lines = [l for l in txt.splitlines() if "×2" in l]
    assert lines and "20" in lines[0] and "21" in lines[0], f"строка ×2 несёт оба id: {lines}"
    assert "22" in txt, f"конверт с другим op — отдельной строкой: {txt}"
    # дедуп по ОТПЕЧАТКУ, а не по id — три записи, но групп-строк (•) ровно 2
    bullets = [l for l in txt.splitlines() if l.strip().startswith("•")]
    assert len(bullets) == 2, f"две группы (одинаковые + другой), а не три: {bullets}"


# I3: пустой инбокс
def test_build_inbox_empty():
    txt = DB.build_inbox(InboxBridge([]))
    assert "пуст" in txt.lower(), f"пустой инбокс → человеческая строка: {txt}"


# I3b: очередь недоступна → не падаем, честная строка
def test_build_inbox_error():
    class BadBridge:
        def get_pending(s, status, lane=None): return {"ok": False, "error": "timeout"}
    txt = DB.build_inbox(BadBridge())
    assert "недоступна" in txt or "timeout" in txt, f"ошибка очереди → честная строка: {txt}"


# ===================== report_results (части а+б) =====================
SENDS = []

class FakeBot:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append((message_thread_id, text, reply_markup))

class Ctx:
    bot = FakeBot()

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


def _topic_of(qid):
    for tid, text, kb in SENDS:
        if f"адача {qid}" in text:
            return tid, kb
    return None, None


# I4: ФОЛЛБЭК-БЕЗ-РЕГРЕССА — INBOX не задан → approve-карточки по СТАРЫМ полосам (vps→328, pc→829)
def test_report_fallback_no_inbox():
    _set_inbox(False)
    _set_pc(True)
    try:
        b = MultiBridge([
            {"id": 1, "from": DB.QUEUE_FROM, "lane": "vps", "status": "needs_approval", "result": "op=git_push | x"},
            {"id": 2, "from": DB.QUEUE_FROM_PC, "lane": "pc", "status": "needs_approval", "result": "op=other | y"},
        ])
        _reset_report(b)
        asyncio.run(DB.report_results(Ctx()))
        t1, kb1 = _topic_of(1)
        t2, kb2 = _topic_of(2)
        assert t1 == DB.DEVBOT_TOPIC and kb1 is not None, f"vps approve → 328 с кнопками (регресс): {SENDS}"
        assert t2 == PC_TOPIC and kb2 is not None, f"pc approve → тема PC-дев с кнопками (регресс): {SENDS}"
    finally:
        _set_pc(False)


# I5: INBOX задан → approve ОБЕИХ полос → тема-инбокс; done/failed ОСТАЮТСЯ по полосам (не в инбокс)
def test_report_inbox_collects_both():
    _set_inbox(True)
    _set_pc(True)
    try:
        b = MultiBridge([
            {"id": 1, "from": DB.QUEUE_FROM, "lane": "vps", "status": "needs_approval", "result": "op=git_push | x"},
            {"id": 2, "from": DB.QUEUE_FROM_PC, "lane": "pc", "status": "needs_approval", "result": "op=other | y"},
            {"id": 3, "from": DB.QUEUE_FROM, "lane": "vps", "status": "done", "result": "готово vps"},
            {"id": 4, "from": DB.QUEUE_FROM_PC, "lane": "pc", "status": "done", "result": "готово pc"},
        ])
        _reset_report(b)
        asyncio.run(DB.report_results(Ctx()))
        assert b.lane == "all", f"опрос lane='all': {b.lane}"
        t1, kb1 = _topic_of(1)
        t2, kb2 = _topic_of(2)
        assert t1 == INBOX and t2 == INBOX, f"approve ОБЕИХ полос → тема-инбокс {INBOX}: {SENDS}"
        assert kb1 is not None and kb2 is not None, "кнопки approve/reject сохранены в инбоксе"
        # done ОСТАЮТСЯ по полосам, в инбокс НЕ сводятся
        t3, _ = _topic_of(3)
        t4, _ = _topic_of(4)
        assert t3 == DB.DEVBOT_TOPIC, f"done vps остаётся в 328, не в инбоксе: {SENDS}"
        assert t4 == PC_TOPIC, f"done pc остаётся в теме PC-дев, не в инбоксе: {SENDS}"
    finally:
        _set_inbox(False)
        _set_pc(False)
        DB.BRIDGE = None


# ===================== splinter молчит в теме-инбоксе (часть а) =====================
def test_splinter_ignores_inbox_topic():
    _set_inbox(True)
    try:
        assert splinter.is_ignored_thread(splinter.HQ_CHAT_ID, INBOX), "тема-инбокс — игнор Splinter"
        assert splinter.is_ignored_thread(splinter.HQ_CHAT_ID, 328), "328 игнорится как раньше"
        assert not splinter.is_ignored_thread(splinter.HQ_CHAT_ID, 999), "прочие темы HQ — не игнор"
        assert not splinter.is_ignored_thread(-1, INBOX), "чужой чат — не игнор"
    finally:
        _set_inbox(False)
    assert not splinter.is_ignored_thread(splinter.HQ_CHAT_ID, INBOX), \
        "env не задан → тема-инбокс не игнорится (инбокс выключен)"


# I6b: боевой id темы-инбокса = 1160 прописан в .env (конфиг-дрейф)
def test_inbox_topic_1160_in_env():
    env_path = "/root/turbobaby-manager-bot/.env"
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            assert "INBOX_TOPIC_ID=1160" in f.read(), ".env потерял INBOX_TOPIC_ID=1160"


# ===================== /inbox — только Филипп (часть в) =====================
_BUILD_CALLS = {"n": 0}

def _stub_build(bridge):
    _BUILD_CALLS["n"] += 1
    return "СПИСОК-ЗАГЛУШКА"

class RUser:
    def __init__(s, uid): s.id = uid

class RMsg:
    def __init__(s): s.replies = []
    async def reply_text(s, txt): s.replies.append(txt)

class RUpd:
    def __init__(s, uid):
        s.effective_user = RUser(uid)
        s.effective_message = RMsg()


def test_inbox_command_owner_only():
    orig = B.devbot.build_inbox
    B.devbot.build_inbox = _stub_build
    try:
        _BUILD_CALLS["n"] = 0
        u = RUpd(999)                                  # чужой
        asyncio.run(B.cmd_inbox(u, None))
        assert _BUILD_CALLS["n"] == 0 and u.effective_message.replies == [], \
            "чужой → полный игнор, build_inbox НЕ зван"
        u2 = RUpd(B.devbot.DEVBOT_USER)                # Филипп (504608015)
        asyncio.run(B.cmd_inbox(u2, None))
        assert _BUILD_CALLS["n"] == 1, "Филипп → build_inbox зван ровно раз"
        assert any("ЗАГЛУШКА" in r for r in u2.effective_message.replies), \
            f"Филиппу уходит список: {u2.effective_message.replies}"
    finally:
        B.devbot.build_inbox = orig
    assert B.devbot.DEVBOT_USER == 504608015, "владелец инбокса — строго Филипп 504608015"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов единого инбокса подтверждений (ст3 O4)")
