# -*- coding: utf-8 -*-
"""Штатная остановка Splinter: дренаж альбомов и передача ждущих карточек (Codex TB-CHECK-1610-0742).

Повод — Codex TB-REL-B0392DF-STOP-1610-0459: рестарт не должен терять уже принятое. PTB 22.7 при SIGTERM сам прекращает
приём (новые входы остаются в Telegram) и дорабатывает очередь, но таймеры альбомов — обычные задачи (их PTB не ждёт),
а карточки «ждут да» живут в памяти. Здесь проверено новое:
  (A) restart_handoff — чистые решения: только ждущие статусы, белый список полей (паспортных данных нет), версия и
      контрольная сумма, «уже применена» по метке, вписывание только в пустые места;
  (B) руки splinter: атомарная запись; восстановление пишет метку ДО вписывания; повторный старт с той же передачей не
      оживляет завершённое; сбой метки/проверки — ничего не вписано и файл цел (следующий старт применит — без потерь);
      испорченный/нечитаемый файл не применяется и не затирается следующей остановкой;
  (C) граница «вход между снимком и остановкой»: карточка, принятая старым процессом перед остановкой, доезжает до
      нового с той же привязкой реплая и теми же полями брони; незавершённые записи (approved/write_unknown) — нет;
  (D) граница «альбом принят до handle»: буфер доводится один раз; прогон в работе дожидается, второго нет; не успели
      к сроку — названо числом, передача всё равно пишется; досланные во время прогона фото — отдельной пачкой ровно раз;
  (E) подключение: post_stop зарегистрирован, восстановление стоит в post_init до проверки моста, захват альбома один.
Сеть, мост и CRM не трогаются (заглушки); файлы — только во временном каталоге прогона.
"""
import ast
import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
_TMP = tempfile.mkdtemp(prefix="restart_drain_t_")
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json")):
    os.environ[_k] = os.path.join(_TMP, _name)


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class _Mem:
    def all_topic_bikes(self):
        return {}

    def all_info_pins(self):
        return {}


class _Any:
    audit_groups = []

    def __init__(self, *a, **k):
        pass

    def set_audit_config(self, *a, **k):
        pass


try:
    import fcntl  # noqa: F401
except ImportError:
    _stub("fcntl", LOCK_SH=1, LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=lambda *a, **k: None, lockf=lambda *a, **k: None)
_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: _Any(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=_Any)
_stub("memory", Memory=_Mem)
_stub("auditor", Auditor=_Any)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import bot  # noqa: E402
import restart_handoff as RH  # noqa: E402

S = bot.splinter
CHAT = next(cid for cid, m in S.GROUPS.items() if m == "servicing")
TOPIC = 7314
LOGS = []


class _Cap(logging.Handler):
    def emit(self, rec):
        LOGS.append(rec.getMessage())


logging.getLogger("turbobaby").addHandler(_Cap())
_N = [0]


def _fresh():
    """Новый «процесс»: пустая память карточек и альбомов, свой файл передачи во временном каталоге."""
    for st in (S._INTAKE_DRAFTS, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES, bot._ALBUM_BUF, bot._ALBUM_TIMERS,
               bot._ALBUM_INFLIGHT):
        st.clear()
    bot._ALBUM_PROCESSING.clear()
    S._HANDOFF_SEEN.update(applied_sha=None, unapplied=False)
    bot._SHUTDOWN_T0 = None
    LOGS.clear()


def _new_path():
    _N[0] += 1
    d = os.path.join(_TMP, "h%02d" % _N[0])
    os.makedirs(d)
    p = os.path.join(d, "restart_handoff.json")
    os.environ["RESTART_HANDOFF_STATE"] = p
    return p


def _restart_same_path():
    """Тот же файл, новый процесс: память пуста, флаги рук сброшены."""
    for st in (S._INTAKE_DRAFTS, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES):
        st.clear()
    S._HANDOFF_SEEN.update(applied_sha=None, unapplied=False)


def _draft(status="awaiting_approval"):
    return {"model": "CB 300CC R 9011", "client": "Мария Тест", "contacts": "+66 80 000 0000",
            "date_start": "15-11-2026", "date_end": "20-11-2026", "deposit_type": "паспорт", "helmets": 2,
            "term": "5 дней", "experience": "да", "delivery_name": "Раваи", "delivery_url": "https://maps.app.goo.gl/x",
            "status": status, "ts": 1792100000.5, "passport_photo": True,
            "passport_ocr": {"file_id": "F", "fields": {"passport_no": "AB123456"}, "ocr_status": "ok", "ts": 1},
            "ic_msg_ids": [5001, 5002], "ic_edit_asked": False}


HO = {"bike": "XADV 750 GREY 2478", "name": "Ivan T", "date_start": "16-10-2026", "row": 41, "ts": 1792100100.0,
      "status": "awaiting"}
CL = {"bike": "NMAX 155 GREY 5960", "name": "Olga T", "date_start": "10-10-2026", "row": 37, "km": "41357",
      "paid_total": 3500.0, "ts": 1792100200.0, "status": "awaiting"}
INTAKE = S.INTAKE_CHAT


def _bytes(p):
    with open(p, "rb") as f:
        return f.read()


# ---------------- (A) чистые решения ----------------

def test_a1_only_waiting_statuses_selected():
    drafts = {1: _draft(), 2: _draft("approved"), 3: _draft("write_unknown"), 4: _draft("booked"),
              5: _draft("rejected"), 6: _draft("incomplete"), 7: _draft("write_failed")}
    ho = {10: dict(HO), 11: dict(HO, status="activated"), 12: dict(HO, status="error")}
    cl = {20: dict(CL), 21: dict(CL, status="closed")}
    got = RH.select(drafts, ho, cl)
    assert [(e["kind"], e["chat_id"]) for e in got] == [("intake", 1), ("handover", 10), ("close", 20)], got


def test_a2_whitelist_no_passport_data_no_objects():
    d = _draft()
    d["raw_card_text"], d["obj"] = "полный текст карточки", object()
    e = RH.select({1: d}, {}, {})[0]
    assert "passport_ocr" not in e["data"] and "raw_card_text" not in e["data"] and "obj" not in e["data"], e
    assert set(e["data"]) <= set(RH.INTAKE_KEYS)
    assert "AB123456" not in json.dumps(e, ensure_ascii=False)


def test_a3_pack_verify_and_tamper():
    entries = RH.select({1: _draft()}, {10: dict(HO)}, {20: dict(CL)})
    obj = RH.pack(entries, written_at=1.0, pid=7)
    assert RH.verify(obj)[0] == entries
    bad = json.loads(json.dumps(obj))
    bad["entries"][0]["data"]["client"] = "Другой"
    assert RH.verify(bad)[0] is None and "сумма" in RH.verify(bad)[1]
    assert RH.verify(dict(obj, version=2))[0] is None
    assert RH.verify(dict(obj, count=5))[0] is None
    sneaky = json.loads(json.dumps(entries))
    sneaky[0]["data"]["passport_ocr"] = {"x": 1}
    assert RH.verify(RH.pack(sneaky, written_at=1.0, pid=7))[0] is None          # вне белого списка
    stale = json.loads(json.dumps(entries))
    stale[0]["data"]["status"] = "approved"
    assert RH.verify(RH.pack(stale, written_at=1.0, pid=7))[0] is None           # незавершённое не принимается
    dup = json.loads(json.dumps(entries)) + [json.loads(json.dumps(entries[0]))]
    assert RH.verify(RH.pack(dup, written_at=1.0, pid=7))[0] is None             # два на одно место
    assert RH.verify("строка")[0] is None


def test_a4_decide_by_marker():
    assert RH.decide("abc", None) == (True, "ok")
    assert RH.decide("abc", {"sha256": "zzz"})[0] is True
    assert RH.decide("abc", {"sha256": "abc", "pid": 9})[0] is False


def test_a5_plan_never_overwrites_and_keeps_ts():
    entries = RH.select({1: _draft()}, {10: dict(HO)}, {})
    occupied = {1: {"status": "awaiting_approval", "model": "живой"}}
    todo, counts = RH.plan(entries, occupied, {}, {})
    assert counts["conflict"] == 1 and counts["intake"] == 0 and counts["handover"] == 1
    ho = {}
    todo, _ = RH.plan(entries, {}, ho, {})
    RH.apply(todo)
    assert ho[10]["ts"] == HO["ts"] and ho[10] is not HO


# ---------------- (B) руки splinter ----------------

def test_b1_write_atomic_and_private():
    _fresh()
    p = _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    h, n, sha = S.handoff_write(now=5.0)
    assert h == "записана" and n == 1 and len(sha) == 8
    assert os.path.exists(p) and not os.path.exists(p + ".tmp")
    if os.name == "posix":
        assert (os.stat(p).st_mode & 0o777) == 0o600
    obj = json.loads(_bytes(p))
    assert RH.verify(obj)[0] is not None and "AB123456" not in _bytes(p).decode("utf-8")


def test_b2_restore_applies_after_marker():
    _fresh()
    p = _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S._HANDOVER_ACTIVATIONS[INTAKE] = dict(HO)
    S.handoff_write()
    _restart_same_path()
    msg = S.handoff_restore(now=9.0)
    assert msg.startswith("применена") and "брони 1" in msg and "выдачи 1" in msg, msg
    mk = json.loads(_bytes(p + ".applied"))
    assert mk["sha256"] == json.loads(_bytes(p))["sha256"]
    assert S._INTAKE_DRAFTS[INTAKE]["ic_msg_ids"] == [5001, 5002]
    assert "passport_ocr" not in S._INTAKE_DRAFTS[INTAKE]


def test_b3_second_start_same_handoff_does_not_revive():
    """Процесс А восстановил карточку, закрыл её (booked) и упал без новой передачи → процесс Б её не оживляет."""
    _fresh()
    _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S.handoff_write()
    _restart_same_path()
    assert S.handoff_restore().startswith("применена")
    S._INTAKE_DRAFTS[INTAKE]["status"] = "booked"          # А довёл бронь…
    _restart_same_path()                                   # …и упал (SIGKILL): новой передачи нет
    msg = S.handoff_restore()
    assert msg.startswith("повторно не применяю"), msg
    assert S._INTAKE_DRAFTS == {}


def test_b4_marker_failure_applies_nothing_and_loses_nothing():
    _fresh()
    p = _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S.handoff_write()
    before = _bytes(p)
    _restart_same_path()
    os.makedirs(p + ".applied.tmp")                        # метку не записать
    msg = S.handoff_restore()
    assert msg.startswith("НЕ применена") and S._INTAKE_DRAFTS == {}, msg
    assert _bytes(p) == before and not os.path.exists(p + ".applied")
    # следующий старт (метку записать можно) — та же передача применяется: потерь нет
    p2 = _new_path()
    with open(p2, "wb") as f:
        f.write(before)
    _restart_same_path()
    assert S.handoff_restore().startswith("применена") and S._INTAKE_DRAFTS[INTAKE]["status"] == "awaiting_approval"


def test_b5_corrupt_not_applied_and_preserved_on_next_stop():
    _fresh()
    p = _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S.handoff_write()
    obj = json.loads(_bytes(p))
    obj["entries"][0]["data"]["client"] = "подмена"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    bad = _bytes(p)
    _restart_same_path()
    msg = S.handoff_restore()
    assert msg.startswith("НЕ применена") and "сумма" in msg and S._INTAKE_DRAFTS == {}, msg
    assert _bytes(p) == bad and not os.path.exists(p + ".applied")
    S.handoff_write()                                      # штатная остановка этого процесса
    kept = [f for f in os.listdir(os.path.dirname(p)) if f.startswith("restart_handoff.unapplied-")]
    assert len(kept) == 1 and _bytes(os.path.join(os.path.dirname(p), kept[0])) == bad, kept
    assert RH.verify(json.loads(_bytes(p)))[0] == []       # новый файл — состояние этого процесса (пусто)


def test_b6_unreadable_and_exception_keep_file():
    _fresh()
    p = _new_path()
    with open(p, "w", encoding="utf-8") as f:
        f.write("{не json")
    assert S.handoff_restore().startswith("НЕ применена") and _bytes(p) == "{не json".encode("utf-8")
    _fresh()
    p = _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S.handoff_write()
    before = _bytes(p)
    _restart_same_path()
    saved = RH.verify
    RH.verify = lambda obj: (_ for _ in ()).throw(RuntimeError("сбой"))
    try:
        msg = S.handoff_restore()
    finally:
        RH.verify = saved
    assert msg.startswith("НЕ применена: сбой") and S._INTAKE_DRAFTS == {} and _bytes(p) == before


def test_b7_restore_sends_nothing():
    _fresh()
    _new_path()
    S._INTAKE_DRAFTS[INTAKE] = _draft()
    S.handoff_write()
    _restart_same_path()
    sent = []

    async def _no_send(*a, **k):
        sent.append(1)
    saved = S._send
    S._send = _no_send
    try:
        S.handoff_restore()
    finally:
        S._send = saved
    assert sent == []
    assert "bridge" not in S.handoff_restore.__code__.co_varnames


def test_b8_no_file_is_honest_empty():
    _fresh()
    _new_path()
    assert S.handoff_restore() == "передачи нет" and S._INTAKE_DRAFTS == {}


# ---------------- (C) вход между снимком и остановкой ----------------

class _Reply:
    def __init__(self, mid):
        self.message_id = mid
        self.from_user = type("U", (), {"is_bot": False, "id": 2, "username": "x"})()
        self.forum_topic_created = None


class _AnsMsg:
    def __init__(self, reply_mid):
        self.chat_id, self.message_thread_id, self.message_id = INTAKE, None, 9999
        self.reply_to_message = _Reply(reply_mid)
        self.text, self.caption = "да", None
        self.from_user = type("U", (), {"username": "deramor", "id": 3, "is_bot": False})()


def test_c1_card_accepted_before_stop_reaches_new_process():
    _fresh()
    _new_path()
    old = _draft()
    S._INTAKE_DRAFTS[INTAKE] = old                            # старый процесс принял карточку перед остановкой
    S._HANDOVER_ACTIVATIONS[INTAKE] = dict(HO)
    S._RETURN_CLOSES[-100777] = dict(CL)
    S._INTAKE_DRAFTS[-100555] = _draft("write_unknown")       # исход записи неизвестен — не передаётся
    S._INTAKE_DRAFTS[-100556] = _draft("approved")            # запись в пути — не передаётся
    fields_before = S._intake_booking_fields(old)
    asyncio.run(bot.on_stop(None))
    assert any("🛑 дренаж остановки" in m and "передача карточек: записана 3" in m for m in LOGS), LOGS
    _restart_same_path()                                      # новый процесс
    assert S.handoff_restore().startswith("применена")
    d = S._INTAKE_DRAFTS[INTAKE]
    assert S._intake_booking_fields(d) == fields_before
    assert S._ic_reply_binding(_AnsMsg(5001), d) == "card"
    assert S._ic_reply_binding(_AnsMsg(4242), d) != "card"
    assert -100555 not in S._INTAKE_DRAFTS and -100556 not in S._INTAKE_DRAFTS
    assert S._HANDOVER_ACTIVATIONS[INTAKE]["ts"] == HO["ts"] and S._RETURN_CLOSES[-100777]["km"] == "41357"


# ---------------- (D) альбом принят до handle ----------------

class _Msg:
    def __init__(self, mid, mgid=None):
        self.chat_id, self.message_thread_id, self.message_id = CHAT, TOPIC, mid
        self.photo, self.caption, self.text = [object()], None, None
        self.media_group_id = mgid
        self.from_user = type("U", (), {"username": "testmech", "id": 1})()


class _Upd:
    def __init__(self, msg):
        self.message = msg


def _run_album(scenario, route_sleep=0.0, window=10.0):
    """Прогнать сценарий с подменой _route_photos; → (пачки, строка дренажа)."""
    passes = []

    async def _route(context, updates):
        passes.append([u.message.message_id for u in updates])
        if route_sleep:
            await asyncio.sleep(route_sleep)

    saved = (bot._route_photos, bot.ALBUM_WINDOW)
    bot._route_photos, bot.ALBUM_WINDOW = _route, window
    try:
        asyncio.run(scenario())
    finally:
        bot._route_photos, bot.ALBUM_WINDOW = saved
    line = next((m for m in LOGS if "🛑 дренаж остановки" in m), "")
    return passes, line


def test_d1_buffered_album_flushed_once_on_stop():
    _fresh()
    _new_path()

    async def sc():
        for i in range(3):
            await bot.handle_photo(_Upd(_Msg(100 + i, mgid="g1")), None)
        timer = bot._ALBUM_TIMERS["g1"]
        bot._SHUTDOWN_T0 = bot._mono()
        await bot.on_stop(None)
        assert timer.done() and bot._ALBUM_BUF == {} and bot._ALBUM_PROCESSING == set()
    passes, line = _run_album(sc)
    assert passes == [[100, 101, 102]], passes
    assert "таймеров 1, в обработке 0, из буфера 1 → доведено 1, не успели 0" in line, line


def test_d2_album_in_processing_awaited_not_rerouted():
    _fresh()
    _new_path()

    async def sc():
        for i in range(2):
            await bot.handle_photo(_Upd(_Msg(200 + i, mgid="g2")), None)
        await asyncio.sleep(0.15)                              # таймер сработал, прогон идёт
        assert "g2" in bot._ALBUM_INFLIGHT
        bot._SHUTDOWN_T0 = bot._mono()
        await bot.on_stop(None)
        assert bot._ALBUM_INFLIGHT == {}
    passes, line = _run_album(sc, route_sleep=0.3, window=0.05)
    assert passes == [[200, 201]], passes
    assert "в обработке 1, из буфера 0 → доведено 1, не успели 0" in line, line


def test_d3_over_budget_named_and_handoff_still_written():
    _fresh()
    p = _new_path()

    async def sc():
        await bot.handle_photo(_Upd(_Msg(300, mgid="g3")), None)
        await asyncio.sleep(0.15)
        bot._SHUTDOWN_T0 = bot._mono() + 0.2 - (bot.SHUTDOWN_BUDGET_SEC - bot.SHUTDOWN_RESERVE_SEC)
        await bot.on_stop(None)
        assert os.path.exists(p)
        task = bot._ALBUM_INFLIGHT.get("g3")
        assert task is not None and not task.cancelled()     # не отменён — PTB закроет цикл сам
        await task
    passes, line = _run_album(sc, route_sleep=1.0, window=0.05)
    assert passes == [[300]], passes
    assert "не успели 1" in line and "передача карточек: записана 0" in line, line


def test_d4_photos_arriving_during_processing_go_once_separately():
    _fresh()
    _new_path()

    async def sc():
        await bot.handle_photo(_Upd(_Msg(400, mgid="g4")), None)
        await asyncio.sleep(0.15)                              # первая пачка в прогоне
        bot.ALBUM_WINDOW = 10.0
        await bot.handle_photo(_Upd(_Msg(401, mgid="g4")), None)   # досланное фото того же альбома
        bot._SHUTDOWN_T0 = bot._mono()
        await bot.on_stop(None)
    passes, line = _run_album(sc, route_sleep=0.3, window=0.05)
    flat = sorted(i for p_ in passes for i in p_)
    assert flat == [400, 401] and len(passes) == 2, passes
    assert "не успели 0" in line, line


def test_d5_signal_marks_start_once_and_exits():
    _fresh()
    try:
        bot._on_stop_signal()
        raise AssertionError("нет SystemExit")
    except SystemExit:
        pass
    t0 = bot._SHUTDOWN_T0
    try:
        bot._on_stop_signal()
    except SystemExit:
        pass
    assert t0 is not None and bot._SHUTDOWN_T0 == t0


def test_d6_unknown_start_uses_fallback_budget():
    _fresh()
    _new_path()

    async def sc():
        await bot.on_stop(None)
    _, line = _run_album(sc)
    assert "от сигнала неизвестно с из 90" in line, line


# ---------------- (E) подключение ----------------

def _bot_tree():
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        return ast.parse(f.read())


def _func(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)


def test_e1_post_stop_registered_and_restore_before_bridge():
    tree = _bot_tree()
    src = ast.dump(_func(tree, "main"))
    assert "'post_stop'" in src and "'on_stop'" in src
    st = _func(tree, "on_startup")
    calls = [n for n in ast.walk(st) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    restore = min(c.lineno for c in calls if c.func.attr == "handoff_restore")
    ping = min(c.lineno for c in calls if c.func.attr == "ping")
    sig = min(c.lineno for c in calls if c.func.attr == "add_signal_handler")
    assert restore < ping and sig < ping


def _called(fn_node):
    """Имена ВЫЗЫВАЕМЫХ функций (по разбору, не по тексту: докстринг словами вызовом не считается)."""
    return {n.func.id for n in ast.walk(fn_node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def test_e2_single_album_capture():
    tree = _bot_tree()
    for fn in ("_album_flush", "_album_drain"):
        called = _called(_func(tree, fn))
        assert "_album_take" in called and "_route_photos" not in called, (fn, called)
    assert "_route_photos" in _called(_func(tree, "_album_run"))
    assert "_route_photos" not in _called(_func(tree, "_album_take"))


def test_e3_budget_arithmetic():
    assert bot.SHUTDOWN_BUDGET_SEC == 90.0 and bot.SHUTDOWN_RESERVE_SEC == 15.0


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
                print("  ✓", name)
            except Exception as e:                                   # noqa: BLE001
                fail += 1
                print("  ✗", name, ":", type(e).__name__, e)
    print("%d/%d — дренаж и передача при штатной остановке" % (ok, ok + fail))
    sys.exit(1 if fail else 0)
