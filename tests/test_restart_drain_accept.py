# -*- coding: utf-8 -*-
"""НЕЗАВИСИМАЯ ПРИЁМКА RESTARTDRAIN1610 (Splinter): дренаж альбомов при штатной остановке + передача ждущих карточек.

Пишется приёмщиком по СПЕЦИФИКАЦИИ задания, не по авторскому тесту (его этот файл не читал). Каждая проверка —
утверждение спецификации; где уместно — отрицательный близнец. Красная проверка = расхождение продукта со
спецификацией (дефект), а не «тест сломан».

Изоляция: всё состояние — во временном каталоге tempfile.mkdtemp() (файл передачи через RESTART_HANDOFF_STATE, пути
состояния splinter — через их env); мост, мозг, память, LLM заглушены; `_route_photos` подменён счётчиком — в Splinter
ничего не уходит, сети нет. «Новый процесс» = сброс словарей карточек, альбомов, метки сигнала и `_HANDOFF_SEEN`.
Прогон: venv/Scripts/python.exe tests/test_restart_drain_accept.py → итог «N/M».
"""
import asyncio
import collections
import contextlib
import copy
import glob
import hashlib
import inspect
import json
import logging
import os
import sys
import tempfile
import time
import types

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="restart_drain_accept_")
os.environ["BRIDGE_URL"] = "http://x"
os.environ["BRIDGE_TOKEN"] = "x"
os.environ["BOT_TOKEN"] = "x"
os.environ.pop("SHUTDOWN_BUDGET_SEC", None)          # проверяем умолчание 90
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json"),
                  ("SPEND_LEDGER_FILE", "spend_ledger.json")):
    os.environ[_k] = os.path.join(TMP, _name)
os.makedirs(os.path.join(TMP, "_default"), exist_ok=True)
os.environ["RESTART_HANDOFF_STATE"] = os.path.join(TMP, "_default", "restart_handoff.json")


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


try:
    import fcntl  # noqa: F401
except ImportError:                                   # Windows: модули с flock импортируются, но не зовутся здесь
    _stub("fcntl", flock=lambda *a, **k: None, LOCK_EX=2, LOCK_UN=8, LOCK_SH=1, LOCK_NB=4)


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


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: _Any(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=_Any)
_stub("memory", Memory=_Mem)
_stub("auditor", Auditor=_Any)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")


class _Cap(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:  # noqa: BLE001
            self.lines.append(str(record.msg))


CAP = _Cap()

import bot  # noqa: E402

logging.getLogger().addHandler(CAP)
for _h in list(logging.getLogger().handlers):
    if _h is not CAP:
        _h.setLevel(logging.CRITICAL + 1)            # консоль молчит; журнал ловит CAP

S = bot.splinter
RH = sys.modules["restart_handoff"]
assert S._rh is RH

CHAT = next(cid for cid, m in S.GROUPS.items() if m == "servicing")
TOPIC = 7314
CTX = object()
NOW = time.time()

C1, C2, C3 = -100111, -100112, -100113               # три группы с черновиками брони
H1, H2 = S.INTAKE_CHAT, -100222                      # выдача: ждёт / уже исполнена
R1, R2 = S.INTAKE_CHAT, -100333                      # закрытие: ждёт / уже закрыто
PASSPORT_NO, OCR_NAME, EXTRA = "PSP-77441199", "OCRNAME SECRETOV", "NOT_WHITELISTED_7731"


# ---------- помощники ----------

@contextlib.contextmanager
def _patched(obj, **kw):
    saved = {k: getattr(obj, k) for k in kw}
    for k, v in kw.items():
        setattr(obj, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(obj, k, v)


def _new_process(path):
    """Состояние свежего процесса: пустые словари карточек и альбомов, без метки сигнала, без прежних решений."""
    os.environ["RESTART_HANDOFF_STATE"] = path
    for d in (S._INTAKE_DRAFTS, S._HANDOVER_ACTIVATIONS, S._RETURN_CLOSES):
        d.clear()
    # К3 16.10 (правка обвязки, названа в коммите): после исправления C6 у рук появился ключ «carry» — страж полного
    # сброса состояния процесса сохранён, сброс дополнен.
    assert set(S._HANDOFF_SEEN) == {"applied_sha", "unapplied", "carry"}, S._HANDOFF_SEEN
    S._HANDOFF_SEEN.update(applied_sha=None, unapplied=False, carry=[])
    bot._ALBUM_BUF.clear()
    bot._ALBUM_TIMERS.clear()
    bot._ALBUM_PROCESSING.clear()
    bot._ALBUM_INFLIGHT.clear()
    bot._SHUTDOWN_T0 = None


def _scene(name):
    d = os.path.join(TMP, name)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "restart_handoff.json")
    _new_process(p)
    CAP.lines.clear()
    return d, p


def _intake(status, **kw):
    d = dict(model="Honda PCX 160", client="Test Client", contacts="@tclient +66 80 000 0000",
             date_start="20.10", date_end="27.10", date_start_iso="2026-10-20", date_end_iso="2026-10-27",
             term="7 дней", experience="5 лет", deposit_type="деньги", delivery_name="Раваи",
             delivery_url="https://maps.example/x", helmets="2",
             status=status, ts=NOW - 60.25, ic_msg_ids=[501, 502], ic_edit_asked=False,
             passport_photo=True, rc_exp_id="exp-1", rc_card_ref="card-1",
             passport_ocr={"file_id": "F1", "ocr_status": "ok", "ts": NOW - 70,
                           "fields": {"full_name": OCR_NAME, "passport_no": PASSPORT_NO,
                                      "country": "RU", "expire_date": "2031-01-01"}},
             secret_extra=EXTRA)
    d.update(kw)
    return d


def _ho(status, **kw):
    d = {"bike": "PCX 4957", "name": "Test Client", "date_start": "20.10", "row": 77, "ts": NOW - 600.5,
         "status": status, "extra_x": EXTRA}
    d.update(kw)
    return d


def _cl(status, **kw):
    d = {"bike": "ADV 2478", "name": "Close Client", "date_start": "01.10", "row": 88, "km": "35200",
         "paid_total": 4900, "ts": NOW - 900.75, "status": status, "extra_x": EXTRA}
    d.update(kw)
    return d


def _stop():
    asyncio.run(bot.on_stop(None))


def _stop_lines():
    return [ln for ln in CAP.lines if "🛑 дренаж остановки:" in ln]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _raw(path):
    with open(path, "rb") as f:
        return f.read()


def _write_raw(path, data):
    with open(path, "wb") as f:
        f.write(data)


def _write_json(path, obj):
    _write_raw(path, json.dumps(obj, ensure_ascii=False).encode("utf-8"))


def _reply(mid):
    return types.SimpleNamespace(reply_to_message=types.SimpleNamespace(message_id=mid, forum_topic_created=None))


class _Msg:
    def __init__(self, mid, mgid=None):
        self.chat_id, self.message_thread_id, self.message_id = CHAT, TOPIC, mid
        self.photo, self.caption, self.text = [object()], None, None
        self.media_group_id = mgid
        self.from_user = type("U", (), {"username": "testmech", "id": 1})()


def _upd(mid, mgid):
    return types.SimpleNamespace(message=_Msg(mid, mgid))


class _Route:
    """Подмена `_route_photos`: какие пачки ушли, какие ДОВЕДЕНЫ до конца; задержка по альбому; побочный эффект."""
    def __init__(self, delay=None, on_call=None):
        self.batches, self.finished, self.delay, self.on_call = [], [], dict(delay or {}), on_call

    async def __call__(self, context, updates):
        ids = [u.message.message_id for u in updates]
        mg = updates[0].message.media_group_id
        self.batches.append(ids)
        if self.on_call:
            self.on_call(ids)
        if self.delay.get(mg):
            await asyncio.sleep(self.delay[mg])
        self.finished.append(ids)


async def _feed(ids, mgid):
    for i in ids:
        await bot.handle_photo(_upd(i, mgid), CTX)


def _unapplied(d):
    return sorted(glob.glob(os.path.join(d, "restart_handoff.unapplied-*.json")))


# =====================================================================================================================
# 1. ШТАТНАЯ ОСТАНОВКА: сигнал, бюджет, строка журнала, проводка
# =====================================================================================================================

def test_signal_sets_mark_once_and_raises_systemexit():
    """SIGTERM/SIGINT-обработчик: метка времени (одна, первая) и SystemExit — и из цикла событий он выходит наружу."""
    saved = bot._SHUTDOWN_T0
    try:
        bot._SHUTDOWN_T0 = None
        raised = 0
        for _ in range(2):
            try:
                bot._on_stop_signal()
            except SystemExit:
                raised += 1
            if _ == 0:
                first = bot._SHUTDOWN_T0
                time.sleep(0.02)
        assert raised == 2, raised
        assert isinstance(first, float) and abs(first - bot._mono()) < 5, first
        assert bot._SHUTDOWN_T0 == first, "вторая метка сдвинула первую"
        loop = asyncio.new_event_loop()
        got = False
        try:
            loop.call_soon(bot._on_stop_signal)
            loop.run_forever()
        except SystemExit:
            got = True
        finally:
            loop.close()
        assert got, "SystemExit из обработчика сигнала не вышел из цикла событий (PTB его бы не увидел)"
    finally:
        bot._SHUTDOWN_T0 = saved


def test_budget_constants_and_deadline_from_signal():
    """Бюджет — ВСЯ остановка от сигнала: дедлайн дренажа = метка + 90 − 15; без метки — вход в хук + 30."""
    assert (bot.SHUTDOWN_BUDGET_SEC, bot.SHUTDOWN_RESERVE_SEC, bot.SHUTDOWN_FALLBACK_SEC) == (90.0, 15.0, 30.0)
    seen = []

    async def fake_drain(deadline):
        seen.append(deadline)
        return {"timers": 0, "inflight": 0, "buffered": 0, "done": 0, "late": 0, "left_in_buffer": 0}

    _scene("budget_calc")
    with _patched(bot, _album_drain=fake_drain, _mono=lambda: 1000.0):
        bot._SHUTDOWN_T0 = 990.0
        _stop()
        bot._SHUTDOWN_T0 = None
        _stop()                                                       # близнец: метки нет
    assert seen == [1065.0, 1030.0], seen
    ls = _stop_lines()
    assert len(ls) == 2 and "от сигнала 10.0 с из 90" in ls[0] and "от сигнала неизвестно с из 90" in ls[1], ls


def test_budget_real_cut_from_signal():
    """Сигнал был 74.6 с назад → дренажу осталось ~0.4 с: прогон в работе НЕ дожидается сверх срока, НЕ отменяется,
    назван числом «не успели»."""
    _scene("budget_real")
    r = _Route(delay={"gT": 3.0})

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=0.01):
            await _feed([11, 12], "gT")
            await asyncio.sleep(0.15)
            task = bot._ALBUM_INFLIGHT.get("gT")
            bot._SHUTDOWN_T0 = bot._mono() - (90 - 15 - 0.4)
            t = time.monotonic()
            await bot.on_stop(None)
            return time.monotonic() - t, task, task.done(), task.cancelled()

    dt, task, done, cancelled = asyncio.run(go())
    assert task is not None
    assert 0.2 <= dt < 1.5, f"on_stop шёл {dt:.2f} с при остатке бюджета 0.4 с"
    assert not done and not cancelled, "прогон в работе отменён/завершён к выходу из on_stop"
    ls = _stop_lines()
    assert ls and "не успели 1;" in ls[-1] and "от сигнала 74.6 с" in ls[-1], ls


def test_budget_fallback_without_signal_mark():
    """Метки нет (сигнал не наш) → бюджет от входа в хук (подменён на 0.4 с вместо 30), сверх него не ждём."""
    _scene("budget_fallback")
    r = _Route(delay={"gF": 3.0})

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=0.01, SHUTDOWN_FALLBACK_SEC=0.4):
            await _feed([21], "gF")
            await asyncio.sleep(0.15)
            t = time.monotonic()
            await bot.on_stop(None)
            return time.monotonic() - t

    dt = asyncio.run(go())
    assert 0.2 <= dt < 1.5, dt
    ls = _stop_lines()
    assert ls and "от сигнала неизвестно" in ls[-1] and "не успели 1;" in ls[-1], ls


def test_on_startup_restores_before_signals_and_bridge():
    """post_init: восстановление передачи — ПЕРВЫМ, затем обработчики SIGTERM+SIGINT = _on_stop_signal, затем мост."""
    order = []

    class _Halt(Exception):
        pass

    class _Br:
        def ping(self):
            order.append("ping")
            raise _Halt()

    def fake_restore():
        order.append("restore")
        return "передачи нет"

    class _RecLoop(asyncio.SelectorEventLoop):
        def add_signal_handler(self, sig, cb, *a):
            order.append(("sig", int(sig), cb))

    loop = _RecLoop()
    with _patched(bot, bridge=_Br()), _patched(S, handoff_restore=fake_restore):
        try:
            loop.run_until_complete(bot.on_startup(None))
        except _Halt:
            pass
        finally:
            loop.close()
    sigs = [x for x in order if isinstance(x, tuple)]
    assert order[0] == "restore" and order[-1] == "ping", order
    assert {s for _, s, _ in sigs} == {int(bot.signal.SIGTERM), int(bot.signal.SIGINT)}, sigs
    assert all(cb is bot._on_stop_signal for _, _, cb in sigs), sigs
    # близнец: цикл без add_signal_handler (Windows) — старт не падает, мост всё равно проверяется
    order.clear()
    CAP.lines.clear()
    loop = asyncio.new_event_loop()
    with _patched(bot, bridge=_Br()), _patched(S, handoff_restore=fake_restore):
        try:
            loop.run_until_complete(bot.on_startup(None))
        except _Halt:
            pass
        finally:
            loop.close()
    assert order == ["restore", "ping"], order
    if sys.platform == "win32":
        assert any("метка начала недоступна" in ln for ln in CAP.lines), CAP.lines[-5:]


def test_main_wires_post_init_and_post_stop():
    src = inspect.getsource(bot.main)
    assert ".post_init(on_startup)" in src and ".post_stop(on_stop)" in src, "post_stop не подключён в main()"
    assert inspect.iscoroutinefunction(bot.on_stop)


# =====================================================================================================================
# 2. АЛЬБОМЫ (B): «альбом принят, handle не вызван»
# =====================================================================================================================

def test_B1_sleeping_timer_cancelled_album_run_once_whole():
    _scene("B1")
    r = _Route()

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=100.0):
            await _feed(range(101, 106), "gB1")
            await asyncio.sleep(0.05)
            before = [list(b) for b in r.batches]
            timer = bot._ALBUM_TIMERS["gB1"]
            await bot.on_stop(None)
            return before, timer

    before, timer = asyncio.run(go())
    assert before == [], f"до остановки альбом уже ушёл: {before} (таймер не спал — тест не о том)"
    assert r.batches == [[101, 102, 103, 104, 105]], r.batches
    assert r.finished == r.batches, "on_stop вернулся раньше, чем прогон доведён"
    assert timer.done(), "спящий таймер не дождан"
    assert not bot._ALBUM_BUF and not bot._ALBUM_PROCESSING and not bot._ALBUM_INFLIGHT and not bot._ALBUM_TIMERS
    ls = _stop_lines()
    assert ls and "таймеров 1, в обработке 0, из буфера 1 → доведено 1, не успели 0" in ls[-1], ls


def test_B1_twin_without_stop_timer_still_sleeping():
    """Отрицательный близнец B1: без on_stop альбом с большим окном НЕ прогоняется (дренаж — единственная причина)."""
    _scene("B1twin")
    r = _Route()

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=100.0):
            await _feed(range(111, 114), "gB1t")
            await asyncio.sleep(0.2)
            return [list(b) for b in r.batches], dict(bot._ALBUM_BUF)

    batches, buf = asyncio.run(go())
    assert batches == [] and "gB1t" in buf, (batches, buf)


def test_B2_album_in_processing_waited_not_rerun():
    _scene("B2")
    r = _Route(delay={"gB2": 0.5})

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=0.01):
            await _feed([201, 202, 203], "gB2")
            await asyncio.sleep(0.15)
            mid = ("gB2" in bot._ALBUM_INFLIGHT, [list(b) for b in r.batches], list(r.finished))
            await bot.on_stop(None)
            return mid

    (inflight, batches, finished) = asyncio.run(go())
    assert inflight and batches == [[201, 202, 203]] and finished == [], (inflight, batches, finished)
    assert r.batches == [[201, 202, 203]], f"прогон в работе запущен повторно: {r.batches}"
    assert r.finished == [[201, 202, 203]], "on_stop не дождался прогона в работе"
    ls = _stop_lines()
    assert ls and "таймеров 0, в обработке 1, из буфера 0 → доведено 1, не успели 0" in ls[-1], ls


def test_B3_photo_sent_during_processing_exactly_once():
    _scene("B3")
    r = _Route(delay={"gB3": 0.4})

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=0.01):
            await _feed([301, 302, 303], "gB3")
            await asyncio.sleep(0.1)
            assert "gB3" in bot._ALBUM_INFLIGHT
            bot.ALBUM_WINDOW = 100.0
            await _feed([304, 305], "gB3")                 # досланное во время обработки — спящий таймер
            await asyncio.sleep(0.05)
            assert "gB3" in bot._ALBUM_BUF and "gB3" in bot._ALBUM_PROCESSING
            await bot.on_stop(None)

    asyncio.run(go())
    cnt = collections.Counter(i for b in r.batches for i in b)
    assert sorted(cnt) == [301, 302, 303, 304, 305] and set(cnt.values()) == {1}, r.batches
    assert r.batches == [[301, 302, 303], [304, 305]], r.batches
    assert r.finished == r.batches
    ls = _stop_lines()
    assert ls and "таймеров 1, в обработке 1, из буфера 1 → доведено 2, не успели 0" in ls[-1], ls


def test_B4_album_take_single_owner():
    _scene("B4")
    entry = {"updates": [_upd(401, "gB4")], "context": CTX}
    bot._ALBUM_BUF["gB4"] = entry
    got = bot._album_take("gB4")
    assert got is entry and "gB4" in bot._ALBUM_PROCESSING and "gB4" not in bot._ALBUM_BUF
    assert bot._album_take("gB4") is None, "второй захват того же альбома"
    bot._ALBUM_BUF["gB4"] = {"updates": [_upd(402, "gB4")], "context": CTX}
    assert bot._album_take("gB4") is None and "gB4" in bot._ALBUM_BUF, "захват при прогоне в работе / буфер тронут"
    bot._ALBUM_PROCESSING.discard("gB4")
    bot._ALBUM_BUF["gB4x"] = {"updates": [], "context": CTX}
    assert bot._album_take("gB4x") is None and "gB4x" not in bot._ALBUM_PROCESSING


def test_B5_over_budget_counted_not_cancelled_not_rerun():
    _scene("B5")
    r = _Route(delay={"gB5": 3.0})

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=0.01):
            await _feed([501, 502], "gB5")
            await asyncio.sleep(0.1)
            bot.ALBUM_WINDOW = 100.0
            await _feed([503], "gB5")
            await asyncio.sleep(0.05)
            task = bot._ALBUM_INFLIGHT["gB5"]
            bot._SHUTDOWN_T0 = bot._mono() - (90 - 15 - 0.4)
            t = time.monotonic()
            await bot.on_stop(None)
            dt = time.monotonic() - t
            buf = [u.message.message_id for u in bot._ALBUM_BUF.get("gB5", {}).get("updates", [])]
            return dt, task.done(), task.cancelled(), buf

    dt, done, cancelled, buf = asyncio.run(go())
    assert dt < 1.5, dt
    assert not done and not cancelled, "не успевший прогон отменён"
    assert buf == [503], f"досланное сверх срока: буфер {buf} (ожидалось остаться в буфере, не прогоняться)"
    assert r.batches == [[501, 502]], r.batches
    ls = _stop_lines()
    assert ls and "не успели 2;" in ls[-1] and "передача карточек: записана" in ls[-1], ls


def test_B6_double_on_stop_no_second_run():
    d, p = _scene("B6")
    r = _Route()
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=100.0):
            await _feed([601, 602], "gB6")
            await asyncio.sleep(0.02)
            await bot.on_stop(None)
            first = _read(p)
            await bot.on_stop(None)
            return first, _read(p)

    first, second = asyncio.run(go())
    assert r.batches == [[601, 602]], r.batches
    ls = _stop_lines()
    assert len(ls) == 2 and "таймеров 0, в обработке 0, из буфера 0 → доведено 0, не успели 0" in ls[1], ls
    # К3 16.10 (правка ожидания, названа в коммите): после исправления C7 каждая запись — новый sha (время/pid в теле);
    # содержимое передачи то же, второго прогона нет.
    assert first["entries"] == second["entries"] and len(second["entries"]) == 1
    assert first["sha256"] != second["sha256"]


def test_B7_drain_failure_still_writes_handoff():
    d, p = _scene("B7")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    bot._ALBUM_TIMERS["bogus"] = object()                # не задача — дренаж падает
    _stop()
    bot._ALBUM_TIMERS.pop("bogus", None)
    ls = _stop_lines()
    assert ls and "альбомы: СБОЙ" in ls[-1] and "передача карточек: записана 1" in ls[-1], ls
    assert [e["chat_id"] for e in _read(p)["entries"]] == [C1]


def test_B8_card_born_during_drain_is_handed_over():
    """«Вход между снимком и остановкой»: прогон альбома в дренаже родил карточку брони → она в передаче
    (снимок берётся ПОСЛЕ дренажа)."""
    d, p = _scene("B8")

    def on_call(ids):
        S._INTAKE_DRAFTS[C2] = _intake("awaiting_approval", ic_msg_ids=list(ids))

    r = _Route(on_call=on_call)

    async def go():
        with _patched(bot, _route_photos=r, ALBUM_WINDOW=100.0):
            await _feed([801, 802], "gB8")
            await asyncio.sleep(0.02)
            await bot.on_stop(None)

    asyncio.run(go())
    ents = _read(p)["entries"]
    assert [(e["kind"], e["chat_id"]) for e in ents] == [("intake", C2)], ents
    assert ents[0]["data"]["ic_msg_ids"] == [801, 802]


# =====================================================================================================================
# 3. ПЕРЕДАЧА (A): «вход между снимком и остановкой», белый список, формат
# =====================================================================================================================

def _old_process_cards():
    S._INTAKE_DRAFTS.update({C1: _intake("awaiting_approval"),
                             C2: _intake("approved", ic_msg_ids=[601]),
                             C3: _intake("write_unknown", ic_msg_ids=[701])})
    S._HANDOVER_ACTIVATIONS.update({H1: _ho("awaiting"), H2: _ho("activated")})
    S._RETURN_CLOSES.update({R1: _cl("awaiting"), R2: _cl("closed")})


def test_A1_booking_card_survives_restart_and_binds_reply():
    d, p = _scene("A1")
    _old_process_cards()
    want_fields = S._intake_booking_fields(copy.deepcopy(S._INTAKE_DRAFTS[C1]))
    ho_ts, cl_ts = S._HANDOVER_ACTIVATIONS[H1]["ts"], S._RETURN_CLOSES[R1]["ts"]
    _stop()
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("применена") and "брони 1 · выдачи 1 · закрытия 1 · занятых мест 0" in res, res
    dr = S._INTAKE_DRAFTS.get(C1)
    assert dr is not None and dr["status"] == "awaiting_approval", dr
    assert S._intake_booking_fields(dr) == want_fields, (S._intake_booking_fields(dr), want_fields)
    assert S._ic_reply_binding(_reply(502), dr) == "card"
    assert S._ic_reply_binding(_reply(501), dr) == "card"
    assert S._ic_reply_binding(_reply(601), dr) == "other", "реплай на карточку другого черновика привязался"
    assert S._ic_reply_binding(_reply(999), dr) == "other"
    assert S._ic_reply_binding(types.SimpleNamespace(reply_to_message=None), dr) == "none"
    assert C2 not in S._INTAKE_DRAFTS and C3 not in S._INTAKE_DRAFTS, "approved/write_unknown доехали"
    assert H2 not in S._HANDOVER_ACTIVATIONS and R2 not in S._RETURN_CLOSES
    assert S._HANDOVER_ACTIVATIONS[H1]["ts"] == ho_ts and S._RETURN_CLOSES[R1]["ts"] == cl_ts
    assert "passport_ocr" not in dr and "secret_extra" not in dr


def test_A1_twin_no_handoff_no_binding():
    """Близнец A1: без передачи (новый процесс, файла нет) — карточки нет, «да» реплаем привязать не к чему."""
    d, p = _scene("A1twin")
    res = S.handoff_restore()
    assert res == "передачи нет" and C1 not in S._INTAKE_DRAFTS, res


def test_A2_no_passport_no_extra_fields_in_file():
    d, p = _scene("A2")
    _old_process_cards()
    _stop()
    raw = _raw(p).decode("utf-8")
    for bad in (PASSPORT_NO, OCR_NAME, "passport_ocr", EXTRA, "extra_x", "secret_extra"):
        assert bad not in raw, f"в файле передачи «{bad}»"
    src = {("intake", C1): _intake("awaiting_approval"), ("handover", H1): _ho("awaiting"), ("close", R1): _cl("awaiting")}
    ents = _read(p)["entries"]
    assert {(e["kind"], e["chat_id"]) for e in ents} == set(src), ents
    for e in ents:
        assert set(e["data"]) <= set(src[(e["kind"], e["chat_id"])]), e["data"]
        assert "status" in e["data"] and "ts" in e["data"]


def test_A3_file_format_version_sha_atomic():
    d, p = _scene("A3")
    _old_process_cards()
    _write_raw(p, b'{"old": true}')                       # прежний файл — должен быть ЗАМЕНЁН целиком
    _stop()
    obj = _read(p)
    ents = obj["entries"]
    # К3 16.10 (правка ожидания, названа в коммите): после исправления C7 sha считается по ВСЕМУ телу (версия, время,
    # pid, число, записи) — иначе повторная запись того же содержимого давала тот же sha и карточка терялась.
    canon = json.dumps({k: obj[k] for k in ("version", "written_at", "pid", "count", "entries")},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert obj["version"] == 1 and obj["count"] == len(ents) == 3, obj
    assert obj["sha256"] == hashlib.sha256(canon.encode("utf-8")).hexdigest()
    assert not os.path.exists(p + ".tmp"), "временный файл остался"
    ls = _stop_lines()
    assert ls and f"записана 3 (sha {obj['sha256'][:8]})" in ls[-1], ls
    # атомарность: запись сорвалась (на месте временного файла — каталог) → прежний файл байт-в-байт цел
    d2, p2 = _scene("A3atomic")
    _old_process_cards()
    _write_raw(p2, b'{"prev": "intact"}')
    os.mkdir(p2 + ".tmp")
    h, n, sha = S.handoff_write()
    assert h.startswith("НЕ записана") and n is None, (h, n)
    assert _raw(p2) == b'{"prev": "intact"}'


def test_A4_status_matrix_only_waiting_travel():
    d, p = _scene("A4")
    yes = set()
    for i, st in enumerate(("awaiting_approval", "approved", "write_unknown", "write_failed", "booked",
                            "rejected", "error", "new", "awaiting")):
        S._INTAKE_DRAFTS[-200000 - i] = _intake(st)
        if st == "awaiting_approval":
            yes.add(("intake", -200000 - i))
    for i, st in enumerate(("awaiting", "activated", "rejected", "error", "awaiting_approval")):
        S._HANDOVER_ACTIVATIONS[-300000 - i] = _ho(st)
        if st == "awaiting":
            yes.add(("handover", -300000 - i))
    for i, st in enumerate(("awaiting", "closed", "rejected", "error", "awaiting_approval")):
        S._RETURN_CLOSES[-400000 - i] = _cl(st)
        if st == "awaiting":
            yes.add(("close", -400000 - i))
    _stop()
    got = {(e["kind"], e["chat_id"]) for e in _read(p)["entries"]}
    assert got == yes, (sorted(got - yes), sorted(yes - got))
    _new_process(p)
    S.handoff_restore()
    have = ({("intake", k) for k in S._INTAKE_DRAFTS} | {("handover", k) for k in S._HANDOVER_ACTIVATIONS}
            | {("close", k) for k in S._RETURN_CLOSES})
    assert have == yes, have


def test_A5_marker_written_before_memory():
    d, p = _scene("A5")
    _old_process_cards()
    _stop()
    sha = _read(p)["sha256"]
    _new_process(p)
    seen = []
    orig = RH.apply

    def spy(todo):
        m = _read(p + ".applied") if os.path.exists(p + ".applied") else None
        seen.append((m and m.get("sha256") == sha, len(S._INTAKE_DRAFTS) + len(S._HANDOVER_ACTIVATIONS)
                     + len(S._RETURN_CLOSES)))
        return orig(todo)

    with _patched(RH, apply=spy):
        res = S.handoff_restore()
    assert res.startswith("применена"), res
    assert seen == [(True, 0)], f"метка к моменту вписывания: {seen}"


def test_A6_restore_sends_nothing_does_nothing():
    d, p = _scene("A6")
    _old_process_cards()
    _stop()
    _new_process(p)
    calls = []

    async def no_send(*a, **k):
        calls.append(("send", a, k))

    def no_write(*a, **k):
        calls.append(("agent_write", a, k))
        raise AssertionError("бизнес-запись при восстановлении")

    class _NoBridge:
        def __getattr__(self, name):
            calls.append(("bridge", name))
            raise AssertionError("мост при восстановлении: " + name)

    before_pp = dict(S._INTAKE_PASSPORT)
    with _patched(S, _send=no_send), _patched(S.bridge_client, agent_write=no_write), _patched(bot, bridge=_NoBridge()):
        res = S.handoff_restore()
    assert not inspect.iscoroutine(res) and res.startswith("применена"), res
    assert calls == [], calls
    assert S._INTAKE_PASSPORT == before_pp


def test_A7_only_empty_places():
    d, p = _scene("A7")
    _old_process_cards()
    _stop()
    _new_process(p)
    mine = {"status": "new", "model": "OTHER", "ts": 1.0}
    S._INTAKE_DRAFTS[C1] = mine
    res = S.handoff_restore()
    assert S._INTAKE_DRAFTS[C1] is mine and S._INTAKE_DRAFTS[C1]["model"] == "OTHER", "занятое место перезаписано"
    assert "занятых мест 1" in res and "выдачи 1" in res and H1 in S._HANDOVER_ACTIVATIONS, res


def test_A8_no_cards_file_written_empty_harmless():
    """По заявке файл пишется всегда (в т.ч. пустой). Проверяем, что он пустой и его восстановление ничего не вписывает."""
    d, p = _scene("A8")
    S._INTAKE_DRAFTS[C2] = _intake("approved")
    _stop()
    obj = _read(p)
    assert obj["count"] == 0 and obj["entries"] == [], obj
    _new_process(p)
    res = S.handoff_restore()
    assert "брони 0 · выдачи 0 · закрытия 0" in res and not S._INTAKE_DRAFTS, res


# =====================================================================================================================
# 4. СБОЙ ВОССТАНОВЛЕНИЯ И ПОВТОРНЫЙ СТАРТ (C)
# =====================================================================================================================

def test_C1_restart_with_same_handoff_does_not_revive_finished():
    d, p = _scene("C1")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    _new_process(p)                                                   # процесс B
    assert S.handoff_restore().startswith("применена")
    S._INTAKE_DRAFTS[C1]["status"] = "booked"                         # B закрыл карточку и упал без остановки
    assert S.handoff_restore().startswith("повторно не применяю")     # тот же процесс — повтора нет
    _new_process(p)                                                   # процесс C
    res = S.handoff_restore()
    assert res.startswith("повторно не применяю") and C1 not in S._INTAKE_DRAFTS, res
    # близнец: метка от ДРУГОЙ передачи — применяется
    d2, p2 = _scene("C1twin")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    _new_process(p2)
    _write_json(p2 + ".applied", {"sha256": "0" * 64, "pid": 1})
    assert S.handoff_restore().startswith("применена") and C1 in S._INTAKE_DRAFTS


def test_C2_marker_write_failure_nothing_applied_file_intact_next_start_applies():
    d, p = _scene("C2")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    raw = _raw(p)
    _new_process(p)
    blocker = p + ".applied.tmp"
    os.mkdir(blocker)                                                 # метку записать нельзя
    res = S.handoff_restore()
    assert res.startswith("НЕ применена"), res
    assert not S._INTAKE_DRAFTS and not S._HANDOVER_ACTIVATIONS and not S._RETURN_CLOSES
    assert _raw(p) == raw and not os.path.exists(p + ".applied")
    _new_process(p)                                                   # следующий старт (прежний процесс убит)
    os.rename(blocker, blocker + ".moved")
    res = S.handoff_restore()
    assert res.startswith("применена") and C1 in S._INTAKE_DRAFTS, res


def test_C3_verify_failure_nothing_applied_next_start_applies():
    d, p = _scene("C3")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    raw = _raw(p)
    for bad in (lambda obj: 1 / 0, lambda obj: (None, "подмена проверки")):
        _new_process(p)
        with _patched(RH, verify=bad):
            res = S.handoff_restore()
        assert res.startswith("НЕ применена"), res
        assert not S._INTAKE_DRAFTS and _raw(p) == raw and not os.path.exists(p + ".applied"), res
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("применена") and C1 in S._INTAKE_DRAFTS, res


def test_C4_unreadable_marker_no_risk():
    d, p = _scene("C4")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    raw = _raw(p)
    _new_process(p)
    _write_raw(p + ".applied", b"{garbage")
    res = S.handoff_restore()
    assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS and _raw(p) == raw, res


def test_C5_corrupt_file_not_applied_and_kept_aside_on_next_stop():
    for name, body in (("C5bad", b"{not json"), ("C5sum", None)):
        d, p = _scene(name)
        if body is None:                                              # валидный JSON, но сумма не сошлась
            S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
            _stop()
            obj = _read(p)
            obj["entries"][0]["data"]["client"] = "Tampered"
            _write_json(p, obj)
            body = _raw(p)
        else:
            _write_raw(p, body)
        _new_process(p)
        res = S.handoff_restore()
        assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS, res
        S._INTAKE_DRAFTS[C3] = _intake("awaiting_approval", client="New One")
        _stop()
        aside = _unapplied(d)
        assert len(aside) == 1 and _raw(aside[0]) == body, (name, aside)
        assert [e["chat_id"] for e in _read(p)["entries"]] == [C3]


def test_C6_marker_failure_then_graceful_stop_next_start_still_gets_card():
    """Реальная последовательность к заявке «сбой метки — файл цел, следующий старт применит»: процесс B не смог
    записать метку, ПОРАБОТАЛ и был остановлен ШТАТНО (как при любом рестарте), процесс C стартует нормально.
    Ожидание по заявке «не теряется оставшееся»: карточка X из передачи A доезжает до C."""
    d, p = _scene("C6")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()                                                           # A
    _new_process(p)                                                   # B
    blocker = p + ".applied.tmp"
    os.mkdir(blocker)
    r_b = S.handoff_restore()
    assert r_b.startswith("НЕ применена"), r_b
    _stop()                                                           # B штатно остановлен
    _new_process(p)                                                   # C
    os.rename(blocker, blocker + ".moved")
    r_c = S.handoff_restore()
    assert C1 in S._INTAKE_DRAFTS, (f"карточка X потеряна: B={r_b!r}; C={r_c!r}; файл C: "
                                    f"{_read(p)['count']} записей; рядом: {[os.path.basename(x) for x in _unapplied(d)]}")


def test_C7_card_waiting_across_two_restarts():
    """Карточка X ждёт «да» дольше одного рестарта: A → (рестарт) → B восстановил, владелец ещё не ответил →
    (рестарт) → C. Ожидание по заявке «не теряется оставшееся»: X есть и в C."""
    d, p = _scene("C7")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()                                                           # A
    sha_a = _read(p)["sha256"]
    _new_process(p)                                                   # B
    assert S.handoff_restore().startswith("применена")
    _stop()                                                           # B (X всё ещё ждёт)
    sha_b, marker = _read(p)["sha256"], _read(p + ".applied")
    _new_process(p)                                                   # C
    r_c = S.handoff_restore()
    assert C1 in S._INTAKE_DRAFTS, (f"карточка X потеряна на втором рестарте: C={r_c!r}; sha A={sha_a[:8]} "
                                    f"B={sha_b[:8]} метка={marker.get('sha256', '')[:8]}")


def test_C7_twin_changed_card_survives_second_restart():
    """Близнец C7: если в B карточка ИЗМЕНИЛАСЬ (просили правки), второй рестарт её переносит."""
    d, p = _scene("C7twin")
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    _stop()
    _new_process(p)
    assert S.handoff_restore().startswith("применена")
    S._INTAKE_DRAFTS[C1]["ic_edit_asked"] = True
    _stop()
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("применена") and C1 in S._INTAKE_DRAFTS, res


# =====================================================================================================================
# 5. ПОПЫТКИ СЛОМАТЬ (D)
# =====================================================================================================================

def _forged(p, mutate):
    S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
    S._HANDOVER_ACTIVATIONS[H1] = _ho("awaiting")
    _stop()
    obj = _read(p)
    mutate(obj)
    obj["count"] = len(obj["entries"])
    obj["sha256"] = RH.digest(obj["entries"])                       # сумма подделана честно — ловить должен контракт
    _write_json(p, obj)


def test_D1_forged_not_waiting_status_rejected():
    d, p = _scene("D1")
    _forged(p, lambda o: o["entries"][0]["data"].__setitem__("status", "approved"))
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS and not S._HANDOVER_ACTIVATIONS, res


def test_D2_two_entries_one_place_rejected():
    d, p = _scene("D2")

    def dup(o):
        e = copy.deepcopy(o["entries"][0])
        e["data"]["client"] = "Second"
        o["entries"].append(e)

    _forged(p, dup)
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS, res


def test_D3_passport_field_injected_rejected():
    d, p = _scene("D3")
    _forged(p, lambda o: o["entries"][0]["data"].__setitem__("passport_ocr", PASSPORT_NO))
    _new_process(p)
    res = S.handoff_restore()
    assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS, res


def test_D4_wrong_version_count_shape_rejected():
    cases = {"ver": lambda o: o.__setitem__("version", 2), "cnt": lambda o: o.__setitem__("count", 99)}
    for name, mut in cases.items():
        d, p = _scene("D4" + name)
        S._INTAKE_DRAFTS[C1] = _intake("awaiting_approval")
        _stop()
        obj = _read(p)
        mut(obj)
        _write_json(p, obj)
        _new_process(p)
        res = S.handoff_restore()
        assert res.startswith("НЕ применена") and not S._INTAKE_DRAFTS, (name, res)
    d, p = _scene("D4list")
    _write_json(p, [])
    res = S.handoff_restore()
    assert res.startswith("НЕ применена"), res


def test_D5_ttl_clock_not_reset_by_restore():
    d, p = _scene("D5")
    S._HANDOVER_ACTIVATIONS[H1] = _ho("awaiting", ts=NOW - 1700.125)       # почти истекла (TTL 1800)
    S._RETURN_CLOSES[R1] = _cl("awaiting", ts=NOW - 1900.5)               # уже истекла
    _stop()
    _new_process(p)
    S.handoff_restore()
    assert S._HANDOVER_ACTIVATIONS[H1]["ts"] == NOW - 1700.125
    assert S._RETURN_CLOSES[R1]["ts"] == NOW - 1900.5
    assert time.time() - S._RETURN_CLOSES[R1]["ts"] > S._RET_CLOSE_TTL, "истёкшая карточка закрытия ожила по сроку"


def test_D6_gitignore_covers_handoff_files():
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        gi = f.read().split("\n")
    for pat in ("restart_handoff.json", "restart_handoff.json.tmp", "restart_handoff.json.applied",
                "restart_handoff.json.applied.tmp", "restart_handoff.unapplied-*.json"):
        assert pat in gi, pat


# =====================================================================================================================

TESTS = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    ok = 0
    print(f"временный каталог: {TMP}")
    for fn in TESTS:
        try:
            fn()
            ok += 1
            print(f"✓ {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            print(f"✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{ok}/{len(TESTS)}")
    sys.exit(0 if ok == len(TESTS) else 1)
