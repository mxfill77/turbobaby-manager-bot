"""Лента темы обслуживания + контекст мозгу (01.10.2026, задание Штаба 0091-76h, SPLTOPICFEED0110).

ЖИВОЙ СЛУЧАЙ (splinter.log, UTC; тексты людей сюда не переносим — только числа, время, id):
  30.09 11:19:54  альбом 9 фото приборки в теме NMAX 155 BLACK 8952; 11:20:55 разбор mileage=38872 conf=high
  30.09 11:23:01  вопрос «Вижу пробег 38872 км … Верно?» (подсказка L)
  30.09 18:23:43  splinter перезапущен — память процесса стёрта
  01.10 06:08:08  ответ Пыма «38972» реплаем через ~19 ч → мозг, который не знал ни вопроса, ни фото.

ЧТО ПРОВЕРЯЕМ:
  + A. лента пишет все виды: текст, фото, кнопка, вопрос бота (с id и видом), ответ бота, запись в
       учёт (`_odo_confirmed`), разбор фото; места записи ТО и разбора стоят в своих функциях;
  + B. живой случай NMAX 155 BLACK 8952 через ПЕРЕЗАПУСК (отдельный процесс) и 19 ч: контекст мозга
       содержит вопрос, его id, реплай на него и разбор фото;
  − C. выключатель `TOPIC_FEED_CONTEXT=0`: контекст мозга прежний байт в байт (против кода без ленты
       — в отдельном процессе, если дан каталог базы `TOPIC_FEED_BASE_SRC`; и всегда — против той же
       сборки с пустым контекстом ленты);
  − D. хранилище недоступно: сообщение обработано как раньше, без задержки, строка журнала есть;
  − E. чужая тема в контекст не попадает;
  + F. вход bot.py пишет сообщение ДО перехватов (перехват взял сообщение — событие в ленте есть);
  + G. объём контекста ограничен (символов ≤ TOPIC_CONTEXT_MAX, событий ≤ 30).

Чат, бот и сообщения выдуманные (чат −1009990001234); Telegram, мост и модель — заглушки; каталог
ленты — временный (`TOPIC_FEED_DIR`). Ничего не удаляется: у каждой проверки своя тема.
"""
import os, sys, json, time, types, asyncio, datetime, logging, tempfile, subprocess, contextlib
from unittest.mock import AsyncMock, patch

REPO = "/root/turbobaby-manager-bot"
_CHILD_SRC = os.environ.get("_TF_CHILD_SRC")          # дочерний процесс «база»: код без ленты
sys.path.insert(0, _CHILD_SRC or REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ["HINTS_DEDUP"] = "0"                      # замок повторов подсказок здесь не предмет
_TMP = tempfile.gettempdir()
os.environ.setdefault("TOPIC_FEED_DIR", os.path.join(_TMP, f"topic_feed_t_{os.getpid()}"))
os.environ.setdefault("MILEAGE_Q_STATE", os.path.join(_TMP, f"mileage_q_tf_{os.getpid()}.json"))
os.environ.setdefault("SVC_TOKENS_STATE", os.path.join(_TMP, f"svc_tokens_tf_{os.getpid()}.json"))
os.environ.setdefault("WORKS_PERSIST_STATE", os.path.join(_TMP, f"works_tf_{os.getpid()}.json"))
FEED_DIR = os.environ["TOPIC_FEED_DIR"]


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class FakeMem:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}
    def set_topic_bike(self, *a, **k): return None


class FakeClaudeCls:
    def __init__(self, *a, **k): pass


class FakeBridge:
    """Заявки ТО нет; всё прочее — отказ без записи."""
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def __getattr__(s, name): return lambda *a, **k: {"ok": False, "items": []}


class FakeAuditor:
    audit_groups = []
    def __init__(self, *a, **k): pass
    def set_audit_config(self, *a, **k): pass


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: FakeBridge(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=FakeClaudeCls)
_stub("memory", Memory=FakeMem)
_stub("auditor", Auditor=FakeAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import bot                       # noqa: E402
S = bot.splinter

CHAT = -1009990001234            # выдуманный чат, объявлен группой обслуживания только здесь
S.GROUPS[CHAT] = "servicing"
BIKE = "NMAX 155 BLACK 8952"
PYM = sorted(S.PYM_USERNAMES)[0]
OWNER = sorted(S.OWNER_USERNAMES)[0]
MECH = "mech_fixture"            # выдуманный механик
BOT_ID = 777000
T_A, T_N, T_C, T_D, T_E1, T_E2, T_F, T_G = 101, 74, 103, 104, 105, 106, 107, 108
for _t in (T_A, T_N, T_C, T_D, T_E1, T_E2, T_F, T_G):
    S.set_topic_bike(CHAT, _t, BIKE)
H19 = 19 * 3600


class U:
    def __init__(s, uname, uid=111, is_bot=False):
        s.username = uname; s.id = uid; s.is_bot = is_bot


class Chat:
    def __init__(s, cid): s.id = cid; s.type = "supergroup"


class Ref:
    def __init__(s, mid, chat=CHAT, topic_created=False):
        s.message_id = mid; s.chat = Chat(chat); s.from_user = U("turbobaby_manager_bot", BOT_ID, True)
        s.forum_topic_created = (object() if topic_created else None)


class Sent:
    def __init__(s, mid): s.message_id = mid


_MID = [12400]
REPLIES = []


def _next_mid():
    _MID[0] += 1
    return _MID[0]


class Msg:
    def __init__(s, text, uname=PYM, topic=T_A, reply_to=None, mid=None, ts=None, photo=False, album=None):
        s.text = None if photo else text
        s.caption = text if photo else None
        s.photo = [object()] if photo else None
        s.chat_id = CHAT; s.chat = Chat(CHAT); s.message_thread_id = topic
        s.message_id = mid if mid is not None else _next_mid()
        s.date = datetime.datetime.fromtimestamp(ts if ts is not None else time.time(), datetime.timezone.utc)
        s.from_user = U(uname)
        s.reply_to_message = reply_to if reply_to is not None else Ref(topic, topic_created=True)
        s.entities = None; s.caption_entities = None; s.media_group_id = album

    async def reply_text(s, t, **k):
        REPLIES.append(t)
        return Sent(_next_mid())


class TgBot:
    username = "turbobaby_manager_bot"; id = BOT_ID

    async def send_message(s, **kw):
        return Sent(_next_mid())


class Ctx:
    bot = TgBot()


class Upd:
    def __init__(s, msg=None, cq=None):
        s.message = msg; s.callback_query = cq
        s.effective_chat = Chat(CHAT)


class CQ:
    def __init__(s, data, msg, uname=PYM):
        s.data = data; s.message = msg; s.from_user = U(uname)


def run(c): return asyncio.run(c)


def feed(topic):
    p = os.path.join(FEED_DIR, f"{CHAT}_{topic}.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def brain_note(text, topic, *, intercept=False, env=None):
    """Прогнать сообщение Пыма-реплаем-на-бота через НАСТОЯЩИЙ `bot.handle_text` (перехваты —
    заглушки «не моё»/«моё»), вернуть (context_note мозга или None, сколько звали перехватчик)."""
    seen = {}
    calls = {"n": 0}

    async def cap_reply(msg, context, context_note="", **k):
        seen["note"] = context_note

    async def svc_result(*a, **k):
        calls["n"] += 1
        return intercept

    old = {k: os.environ.get(k) for k in (env or {})}
    os.environ.update(env or {})
    try:
        m = Msg(text, uname=PYM, topic=topic, reply_to=Ref(5555))
        with patch.object(bot, "manager_reply", cap_reply), \
             patch.object(S, "ensure_info_pin", new_callable=AsyncMock), \
             patch.object(S, "expire_stale_mileage_question", new_callable=AsyncMock), \
             patch.object(S, "handle_service_result", svc_result), \
             patch.object(S, "handle_oil_backdated_service", AsyncMock(return_value=False)), \
             patch.object(S, "handle_mileage_correction", AsyncMock(return_value=False)), \
             patch.object(S, "handle_post_close_ack", AsyncMock(return_value=False)), \
             patch.object(S, "handle", new_callable=AsyncMock):
            run(bot.handle_text(Upd(m), Ctx()))
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return seen.get("note"), calls["n"], m.message_id


# ── + лента пишет все виды ──────────────────────────────────────────────────────

def test_a_feed_writes_all_kinds():
    t = T_A
    m_txt = Msg("готово, масло", uname=MECH, topic=t)
    assert S.feed_incoming(m_txt, "text")
    m_ph = Msg("", uname=MECH, topic=t, photo=True)
    assert S.feed_incoming(m_ph, "photo")
    q_msg = Ref(9001); q_msg.chat_id = CHAT; q_msg.message_thread_id = t
    assert S.feed_button(Upd(cq=CQ("svc:mok:54", q_msg)))
    run(S._ask_mileage_confirm(Ctx(), CHAT, t, BIKE, "38872"))            # вопрос бота через _hint_send
    q_mid = _MID[0]
    run(S._send(Ctx(), chat_id=CHAT, text="Записал пробег.", message_thread_id=t))   # ответ бота
    try:
        S._odo_confirmed(FakeBridge(), CHAT, t, BIKE, 38972, questioned_km="38872", sender="@x", source="test")
    except Exception as e:
        raise AssertionError(f"_odo_confirmed упал на заглушке моста: {type(e).__name__}: {e}")
    assert S.feed_vision(CHAT, t, [m_ph], {"mileage": "38872", "mileage_confidence": "high",
                                           "kind": "dashboard"}, 1)
    ev = feed(t)
    kinds = {e["kind"] for e in ev}
    assert kinds == set(S._tfeed.KINDS), f"виды в ленте {sorted(kinds)} ≠ {sorted(S._tfeed.KINDS)}"
    ask = [e for e in ev if e["kind"] == "bot_ask" and e.get("hint") == "L"]
    assert ask and ask[-1]["mid"] == q_mid and ask[-1]["role"] == "bot", f"вопрос L без id: {ask}"
    rec = [e for e in ev if e["kind"] == "record"]
    assert rec and rec[-1]["km"] == "38972" and rec[-1]["questioned_km"] == "38872", f"запись учёта: {rec}"
    roles = {e["kind"]: e["role"] for e in ev}
    assert roles["text"] == "staff" and roles["button"] == "pym" and roles["bot_msg"] == "bot", roles
    btn = [e for e in ev if e["kind"] == "button"][0]
    assert btn["text"] == "svc:mok" and btn["mid"] == 9001, f"кнопка без действия/id: {btn}"
    # места записи ТО и разбора фото — в своих функциях (их живой прогон требует моста и зрения)
    import ast
    src = open(os.path.join(_CHILD_SRC or REPO, "splinter.py"), encoding="utf-8").read()
    calls = {}
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("feed_record", "feed_vision"):
                    calls.setdefault(n.func.id, set()).add(fn.name)
    assert "_sp_write_done" in calls.get("feed_record", set()), f"запись ТО не пишет ленту: {calls}"
    assert "_odo_confirmed" in calls.get("feed_record", set()), f"_odo_confirmed не пишет ленту: {calls}"
    assert "_handle_servicing" in calls.get("feed_vision", set()), f"разбор фото не пишет ленту: {calls}"


# ── + живой случай через перезапуск ─────────────────────────────────────────────

def _child(mode, *args, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, os.path.abspath(__file__), mode, *map(str, args)],
                       env=env, capture_output=True, text=True, timeout=120)
    for line in (r.stdout or "").splitlines():
        if line.startswith("CHILD_RESULT "):
            return json.loads(line[len("CHILD_RESULT "):])
    raise AssertionError(f"дочерний процесс без итога rc={r.returncode}: {(r.stderr or '')[-600:]}")


def test_b_nmax_case_context_after_restart():
    t = T_N
    t0 = time.time() - 240
    photos = [Msg("", uname=MECH, topic=t, photo=True, album="alb_fixture", ts=t0 + i) for i in range(9)]
    for p in photos:
        S.feed_incoming(p, "photo")
    S.feed_vision(CHAT, t, photos, {"mileage": "38872", "mileage_confidence": "high", "kind": "dashboard"}, 9)
    run(S._ask_mileage_confirm(Ctx(), CHAT, t, BIKE, "38872"))
    q = _MID[0]
    res = _child("--child-nmax", q)
    ctx = res["ctx"]
    assert res["pending_before"] is False, "в новом процессе память обязана быть пустой"
    assert "Вижу 38872 км. Верно?" in ctx and f"сообщение бота #{q}" in ctx, (
        f"открытого вопроса с id нет в контексте:\n{ctx}")
    assert f"вопрос бота #{q}" in ctx, f"вопроса #{q} нет в ленте контекста:\n{ctx}"
    assert f"↩#{q}" in ctx and "«38972»" in ctx, f"реплая на вопрос нет:\n{ctx}"
    assert f"РЕПЛАЙ на #{q}" in ctx, f"контекст не сказал, на что это сообщение:\n{ctx}"
    assert "разбор фото" in ctx and "пробег 38872 (уверенность high)" in ctx and "фото 9" in ctx, (
        f"разбора фото нет:\n{ctx}")
    assert "NMAX 155 BLACK 8952" in ctx
    print(f"    · контекст случая 8952: {len(ctx)} символов, событий {res['events']}")


def _child_nmax(q):
    pend_before = bool(S._PENDING_MILEAGE)
    later = time.time() + H19
    reply = Msg("38972", uname=PYM, topic=T_N, reply_to=Ref(int(q)), ts=later)
    S.feed_incoming(reply, "text")
    ctx = S.topic_context(CHAT, T_N, reply_to=int(q), now=later + 5, bridge=FakeBridge())
    print("CHILD_RESULT " + json.dumps({"pending_before": pend_before, "ctx": ctx,
                                        "events": len(feed(T_N))}, ensure_ascii=False))


# ── − выключатель: контекст прежний байт в байт ─────────────────────────────────

def test_c_flag_off_context_byte_for_byte():
    S.feed_incoming(Msg("событие до", uname=MECH, topic=T_C), "text")
    note_on, _, _ = brain_note("сколько км?", T_C)
    assert note_on and "ЛЕНТА ЭТОЙ ТЕМЫ" in note_on, "положительный контроль: при включённом флаге лента есть"
    note_off, _, _ = brain_note("сколько км?", T_C, env={"TOPIC_FEED_CONTEXT": "0"})
    assert "ЛЕНТА ЭТОЙ ТЕМЫ" not in note_off, "флаг выключен, а лента в контексте"
    with patch.object(S, "topic_context", lambda *a, **k: ""):
        note_empty, _, _ = brain_note("сколько км?", T_C)
    assert note_off == note_empty, "флаг выключен: note обязан совпасть с note без ленты байт в байт"
    base = os.environ.get("TOPIC_FEED_BASE_SRC")
    if base and os.path.exists(os.path.join(base, "bot.py")):
        res = _child("--child-note", T_C, extra_env={"_TF_CHILD_SRC": base})
        assert res["note"] == note_off, "флаг выключен: note ≠ note кода БЕЗ ленты (база)"
        print(f"    · сверено с кодом без ленты ({base}): {len(note_off)} символов, равны")
    else:
        print("    · каталог базы не дан — сверка с кодом без ленты пропущена (только сверка внутри)")


def _child_note(topic):
    note, _, _ = brain_note("сколько км?", int(topic))
    print("CHILD_RESULT " + json.dumps({"note": note}, ensure_ascii=False))


# ── − хранилище недоступно ──────────────────────────────────────────────────────

def test_d_store_unavailable_message_processed():
    blocker = os.path.join(_TMP, f"topic_feed_blocker_{os.getpid()}")
    with open(blocker, "w") as f:
        f.write("не каталог")
    warn = []

    class H(logging.Handler):
        def emit(self, r):
            if "лента темы" in r.getMessage():
                warn.append(r.getMessage())
    lg = logging.getLogger("splinter"); h = H(); lg.addHandler(h)
    S._tfeed._SAID["fail"] = 0.0
    try:
        t0 = time.monotonic()
        note, n_int, _ = brain_note("сколько км?", T_D, env={"TOPIC_FEED_DIR": os.path.join(blocker, "feed")})
        dt = time.monotonic() - t0
    finally:
        lg.removeHandler(h)
    assert n_int == 1, "перехват обязан быть вызван, как раньше"
    assert note is not None, "сообщение обязано дойти до мозга, как раньше"
    assert warn, "сбой ленты обязан дать строку журнала"
    assert dt < 2.0, f"сбой ленты задержал обработку: {dt:.2f} с"
    print(f"    · хранилище недоступно: обработано за {dt:.3f} с, строк журнала {len(warn)}")


# ── − чужая тема ────────────────────────────────────────────────────────────────

def test_e_foreign_topic_not_in_context():
    S.feed_incoming(Msg("своё сообщение", uname=MECH, topic=T_E1), "text")
    S.feed_incoming(Msg("ЧУЖАЯ-ТЕМА-МАРКЕР 12345", uname=MECH, topic=T_E2), "text")
    run(S._ask_mileage_confirm(Ctx(), CHAT, T_E2, BIKE, "77777"))
    q2 = _MID[0]
    ctx = S.topic_context(CHAT, T_E1, bridge=FakeBridge())
    assert "своё сообщение" in ctx, "своё событие обязано быть"
    assert "ЧУЖАЯ-ТЕМА-МАРКЕР" not in ctx and "77777" not in ctx and f"#{q2}" not in ctx, (
        f"чужая тема попала в контекст:\n{ctx}")


# ── + вход пишет ДО перехватов ──────────────────────────────────────────────────

def test_f_entry_writes_before_interceptors():
    note, n_int, mid = brain_note("38972", T_F, intercept=True)
    assert n_int == 1 and note is None, "перехват обязан взять сообщение (мозг не зовётся)"
    ev = [e for e in feed(T_F) if e["mid"] == mid]
    assert ev and ev[0]["kind"] == "text" and ev[0]["role"] == "pym", (
        f"сообщение, взятое перехватом, в ленту не попало: {feed(T_F)}")
    src = open(os.path.join(REPO, "bot.py"), encoding="utf-8").read()
    i_feed = src.find('splinter.feed_incoming(msg, "text")')
    i_rv = src.index("splinter.revive_mileage_question_by_reply(")
    i_pin = src.index("await splinter.ensure_info_pin(context, chat_id, _tid_sv)")
    assert 0 <= i_feed < i_pin < i_rv, "вход ленты обязан стоять первым в ветке обслуживания"


# ── + объём ограничен ───────────────────────────────────────────────────────────

def test_g_context_volume_bounded():
    for i in range(45):
        S.feed_incoming(Msg("x" * 280 + f" {i}", uname=MECH, topic=T_G), "text")
    ctx = S.topic_context(CHAT, T_G, bridge=FakeBridge())
    n_ev = ctx.count("[сотрудник]")
    assert n_ev <= 30, f"событий в контексте {n_ev} > 30"
    assert len(ctx) <= 6000, f"контекст {len(ctx)} символов > 6000"
    print(f"    · 45 длинных событий → в контексте {n_ev}, {len(ctx)} символов")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child-nmax":
        _child_nmax(sys.argv[2]); sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--child-note":
        _child_note(sys.argv[2]); sys.exit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} — лента темы + контекст мозгу (FAIL {bad})")
    sys.exit(1 if bad else 0)
