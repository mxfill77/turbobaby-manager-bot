"""Решатель темы обслуживания в тени (01.10.2026, задание Штаба 0094-76k, SPLDECIDER0110).

ЖИВОЙ СЛУЧАЙ (splinter.log, UTC; тексты людей сюда не переносим — только числа, время, id):
  30.09 11:19:54  альбом 9 фото приборки в теме NMAX 155 BLACK 8952; 11:20:55 разбор mileage=38872 conf=high
  30.09 11:23:01  вопрос «Вижу пробег 38872 км … Верно?» (подсказка L)
  30.09 18:23:43  splinter перезапущен — память процесса стёрта
  01.10 06:08:08  ответ Пыма «38972» реплаем через ~19 ч → мозг переспросил (АУДИТ logic_error 06:08:20).

ЧТО ПРОВЕРЯЕМ (модель — заглушка: «что вернула бы модель», правила и проводка — настоящие):
  + P1. случай 8952 через ПЕРЕЗАПУСК: решение «записать 38972», основание — mid ответа, дверь
        `_odo_confirmed`; модель, решившая переспросить, получает отказ кодом (вопрос уже открыт);
  + P2. сотрудник шлёт фото с пробегом → «записать» только через кнопку Пыма; решатель моста не пишет;
  − N1. модель предлагает пробег ниже записанного → «позвать»; выше потолка → «позвать»; без mid → отказ;
  − N2. второй вопрос того же вида → отказ (а в теме без открытого вопроса — проходит);
  − N3. флаг выключен → путь прежний байт в байт (против кода БЕЗ решателя в отдельном процессе,
        если дан `TOPIC_DECIDER_BASE_SRC`); флаг включён → действия те же, добавлен только вызов модели;
  − N4. ответ не JSON → «ничего: не понял».

Чат, бот и сообщения выдуманные (чат −1009990001234); Telegram, мост и модель — заглушки; каталоги
ленты и состояния — временные. Ничего не удаляется: у каждой проверки своя тема.
"""
import os, sys, re, json, time, types, asyncio, datetime, tempfile, subprocess, contextlib
from unittest.mock import AsyncMock, patch

REPO = "/root/turbobaby-manager-bot"
_CHILD_SRC = os.environ.get("_TD_CHILD_SRC")          # дочерний процесс «база»: код без решателя
sys.path.insert(0, _CHILD_SRC or REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ["HINTS_DEDUP"] = "0"                      # замок повторов подсказок здесь не предмет
_TMP = tempfile.gettempdir()
os.environ.setdefault("TOPIC_FEED_DIR", os.path.join(_TMP, f"topic_feed_td_{os.getpid()}"))
os.environ.setdefault("MILEAGE_Q_STATE", os.path.join(_TMP, f"mileage_q_td_{os.getpid()}.json"))
os.environ.setdefault("SVC_TOKENS_STATE", os.path.join(_TMP, f"svc_tokens_td_{os.getpid()}.json"))
os.environ.setdefault("WORKS_PERSIST_STATE", os.path.join(_TMP, f"works_td_{os.getpid()}.json"))
os.environ.setdefault("HINT_DEDUP_STATE", os.path.join(_TMP, f"hint_td_{os.getpid()}.json"))
os.environ.pop("ODO_CEILING_KM", None)               # потолок — по умолчанию модуля (30000)
FLAG = "TOPIC_DECIDER_SHADOW"


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
    """Заявки ТО нет; всё прочее — отказ без записи. Ведёт список вызванных методов."""
    def __init__(s): s.calls = []
    def service_pending_get(s, *a, **k):
        s.calls.append("service_pending_get"); return {"ok": False, "error": "not_found"}
    def __getattr__(s, name):
        if name.startswith("__"):
            raise AttributeError(name)
        def f(*a, **k):
            s.calls.append(name); return {"ok": False, "items": []}
        return f


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
MECH = "mech_fixture"            # выдуманный механик
BOT_ID = 777000
T_N, T_P2, T_L, T_Q1, T_Q2, T_X, T_TR = 201, 202, 203, 204, 205, 206, 207
for _t in (T_N, T_P2, T_L, T_Q1, T_Q2, T_X, T_TR):
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
TRACE = {"sent": [], "replies": []}


def _next_mid():
    _MID[0] += 1
    return _MID[0]


class Msg:
    def __init__(s, text, uname=PYM, topic=T_N, reply_to=None, mid=None, ts=None, photo=False, album=None):
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
        TRACE["replies"].append(t)
        return Sent(_next_mid())


class TgBot:
    username = "turbobaby_manager_bot"; id = BOT_ID

    async def send_message(s, **kw):
        TRACE["sent"].append([kw.get("text"), kw.get("message_thread_id")])
        return Sent(_next_mid())

    def __getattr__(s, name):
        if name.startswith("__"):
            raise AttributeError(name)
        async def f(*a, **k):
            TRACE["sent"].append([name, k.get("message_thread_id")])
            return Sent(_next_mid())
        return f


class Ctx:
    bot = TgBot()


class Upd:
    def __init__(s, msg=None, cq=None):
        s.message = msg; s.callback_query = cq
        s.effective_chat = Chat(CHAT)


class Model:
    """Заглушка модели: `fn(вход) -> сырой ответ`; ведёт вызовы."""
    def __init__(s, fn): s.fn = fn; s.calls = []
    def quick(s, system, user, max_tokens=600, raise_on_upstream=False, model=None, tag="",
              escalate_to=None, expect_json=False):
        s.calls.append({"tag": tag, "user": user, "system": system})
        return s.fn(user)


def J(**d): return json.dumps(d, ensure_ascii=False)


def mid_in(user):
    return int(re.search(r"сообщение #(\d+)", user).group(1))


@contextlib.contextmanager
def flag(on):
    old = os.environ.get(FLAG)
    os.environ[FLAG] = "1" if on else "0"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = old


def run(c): return asyncio.run(c)


def decide(msg, model, kind="text", bridge=None):
    """Тень на одном сообщении: решение и итог правил (флаг включён на время вызова)."""
    async def go():
        t = S.decider_shadow(msg, bridge=bridge, claude=model, kind=kind)
        assert t is not None, "флаг включён, а тень не запустилась"
        return await t
    with flag(True):
        return run(go())


def _child(mode, *args, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, os.path.abspath(__file__), mode, *map(str, args)],
                       env=env, capture_output=True, text=True, timeout=120)
    for line in (r.stdout or "").splitlines():
        if line.startswith("CHILD_RESULT "):
            return json.loads(line[len("CHILD_RESULT "):])
    raise AssertionError(f"дочерний процесс без итога rc={r.returncode}: {(r.stderr or '')[-800:]}")


def _patches(capture):
    """Перехваты — заглушки «не моё» (здесь предмет — тень, а не они); мозг — захват note."""
    async def cap_reply(msg, context, context_note="", **k):
        capture.append(context_note)
    return [patch.object(bot, "manager_reply", cap_reply),
            patch.object(S, "ensure_info_pin", new_callable=AsyncMock),
            patch.object(S, "expire_stale_mileage_question", new_callable=AsyncMock),
            patch.object(S, "handle_service_result", AsyncMock(return_value=False)),
            patch.object(S, "handle_mileage_confirm", AsyncMock(return_value=False)),
            patch.object(S, "handle_oil_backdated_service", AsyncMock(return_value=False)),
            patch.object(S, "handle_mileage_correction", AsyncMock(return_value=False)),
            patch.object(S, "handle_post_close_ack", AsyncMock(return_value=False)),
            patch.object(S, "handle", new_callable=AsyncMock)]


# ── + P1: случай 8952 через перезапуск ──────────────────────────────────────────

def test_p1_case_8952_reply_after_restart_records_without_reask():
    t = T_N
    t0 = time.time() - 240
    photos = [Msg("", uname=MECH, topic=t, photo=True, album="alb_fixture", ts=t0 + i) for i in range(9)]
    for p in photos:
        S.feed_incoming(p, "photo")
    S.feed_vision(CHAT, t, photos, {"mileage": "38872", "mileage_confidence": "high", "kind": "dashboard"}, 9)
    run(S._ask_mileage_confirm(Ctx(), CHAT, t, BIKE, "38872"))
    q = _MID[0]
    res = _child("--child-8952", q)
    assert res["pending_before"] is False, "в новом процессе память обязана быть пустой"
    u = res["user"]
    for need in (f"вопрос бота #{q}", f"РЕПЛАЙ на #{q}", "Вижу 38872 км. Верно?", "пробег 38872 (уверенность high)",
                 f"сообщение #{res['mid']}", "автор pym (доверенный: да)", f"пробег #{q}"):
        assert need in u, f"во входе решателя нет «{need}»:\n{u}"
    v = res["v"]
    it = v["итог"]
    assert it["действие"] == "записать" and it["км"] == 38972 and it["источник"] == res["mid"], f"итог: {v}"
    assert v["дверь"] == S._tdec.DOOR_ODO and v["правило"] == "", f"дверь/правило: {v}"
    assert res["decision_events"] == 1, f"событий decision в ленте {res['decision_events']} ≠ 1"
    assert res["ctx_has_decision"] is False, "событие тени попало в контекст мозга"
    assert res["brain_calls"] == 1 and res["model_calls"] == 1, f"прежний путь/модель: {res}"
    r2 = res["v_reask"]
    assert r2["итог"]["действие"] == "ничего" and r2["правило"] == "второй_вопрос", f"переспрос не отклонён: {r2}"
    print(f"    · 8952: записать 38972 ← #{res['mid']} (дверь {v['дверь']}); переспрос → отказ; вход {len(u)} симв.")


def _child_8952(q):
    pend_before = bool(S._PENDING_MILEAGE)
    later = time.time() + H19
    reply = Msg("38972", uname=PYM, topic=T_N, reply_to=Ref(int(q)), ts=later)
    seen = {}

    def fn(user):
        seen["user"] = user
        return J(действие="записать", что="пробег", км=38972, источник=mid_in(user))
    model = Model(fn)
    notes = []

    async def go():
        with contextlib.ExitStack() as st:
            for p in _patches(notes):
                st.enter_context(p)
            st.enter_context(patch.object(bot, "claude", model))
            st.enter_context(patch.object(bot, "bridge", FakeBridge()))
            await bot.handle_text(Upd(reply), Ctx())
            await asyncio.gather(*list(S._DECIDER_TASKS))
    with flag(True):
        run(go())
    evs = [e for e in S._tfeed.read(CHAT, T_N, days=30, limit=0, now=later + 60, shadow=True)
           if e.get("kind") == "decision" and e.get("on") == reply.message_id]
    ctx = S.topic_context(CHAT, T_N, now=later + 60)
    v2 = decide(reply, Model(lambda u: J(действие="спросить", вопрос="Сколько км?", ждём_что="пробег", от_кого="Пым")))
    out = {"pending_before": pend_before, "user": seen.get("user", ""), "mid": reply.message_id,
           # пустые поля лента не хранит (`topic_feed.append`): нет `rule` = правило не сработало
           "v": ({"итог": evs[-1]["final"], "дверь": evs[-1].get("door", ""), "правило": evs[-1].get("rule", "")}
                 if evs else {}),
           "decision_events": len(evs), "ctx_has_decision": ("decision" in ctx or "🧠" in ctx),
           "brain_calls": len(notes), "model_calls": len(model.calls), "v_reask": v2}
    print("CHILD_RESULT " + json.dumps(out, ensure_ascii=False))


# ── + P2: фото сотрудника с пробегом → кнопка Пыма ──────────────────────────────

def test_p2_staff_photo_mileage_goes_via_pym_button():
    t = T_P2
    ph = Msg("", uname=MECH, topic=t, photo=True)
    S.feed_incoming(ph, "photo")
    S.feed_vision(CHAT, t, [ph], {"mileage": "41000", "mileage_confidence": "high", "kind": "dashboard"}, 1)
    br = FakeBridge()
    v = decide(ph, Model(lambda u: J(действие="записать", что="пробег", км=41000, источник=mid_in(u))),
               kind="photo", bridge=br)
    assert v["итог"]["действие"] == "записать" and v["дверь"] == S._tdec.DOOR_PYM and v["правило"] == "доверие", (
        f"фото сотрудника: {v}")
    writes = [c for c in br.calls if not re.match(r"(service_pending_get|service_list|find_bike|get_|list_|cell)", c)]
    assert not writes, f"решатель тронул мост не чтением: {br.calls}"
    # число текстом от сотрудника — тоже только кнопкой; от Пыма — дверь подтверждения пробега
    m_st = Msg("41000", uname=MECH, topic=t); S.feed_incoming(m_st, "text")
    v_st = decide(m_st, Model(lambda u: J(действие="записать", что="пробег", км=41000, источник=mid_in(u))))
    assert v_st["дверь"] == S._tdec.DOOR_PYM, f"число сотрудника: {v_st}"
    m_py = Msg("41000", uname=PYM, topic=t); S.feed_incoming(m_py, "text")
    v_py = decide(m_py, Model(lambda u: J(действие="записать", что="пробег", км=41000, источник=mid_in(u))))
    assert v_py["дверь"] == S._tdec.DOOR_ODO, f"число Пыма (контроль): {v_py}"
    # «да» сотрудника на число из фото сотрудника — основание чужое, но тоже не доверенное → кнопка
    m_da = Msg("да", uname=MECH, topic=t); S.feed_incoming(m_da, "text")
    v_da = decide(m_da, Model(lambda u: J(действие="записать", что="пробег", км=41000, источник=ph.message_id)))
    assert v_da["дверь"] == S._tdec.DOOR_PYM, f"«да» сотрудника: {v_da}"
    # место вызова: разбор фото → тень, ПОСЛЕ события разбора
    import ast
    src = open(os.path.join(REPO, "splinter.py"), encoding="utf-8").read()
    fn = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_handle_servicing"][0]
    seg = ast.get_source_segment(src, fn)
    assert 0 <= seg.find("feed_vision(") < seg.find("decider_shadow("), "тень фото обязана стоять после разбора"
    bsrc = open(os.path.join(REPO, "bot.py"), encoding="utf-8").read()
    i_feed = bsrc.find('splinter.feed_incoming(msg, "text")')
    i_dec = bsrc.find("splinter.decider_shadow(msg, bridge=bridge, claude=claude)")
    i_rv = bsrc.find("splinter.revive_mileage_question_by_reply(")
    assert 0 <= i_feed < i_dec < i_rv, "тень текста обязана стоять сразу за лентой, ДО перехватов"


# ── − N1: убывание, потолок, без основания ──────────────────────────────────────

def test_n1_lower_or_above_ceiling_calls_not_records():
    t = T_L
    S.feed_record(CHAT, t, "пробег", km="40000", source="fixture")
    m = Msg("39000", uname=PYM, topic=t); S.feed_incoming(m, "text")
    v = decide(m, Model(lambda u: J(действие="записать", что="пробег", км=39000, источник=mid_in(u))))
    assert v["итог"]["действие"] == "позвать" and v["правило"] == "убывание", f"убывание: {v}"
    m2 = Msg("75000", uname=PYM, topic=t); S.feed_incoming(m2, "text")
    v2 = decide(m2, Model(lambda u: J(действие="записать", что="пробег", км=75000, источник=mid_in(u))))
    assert v2["итог"]["действие"] == "позвать" and v2["правило"] == "потолок", f"потолок: {v2}"
    m3 = Msg("40500", uname=PYM, topic=t); S.feed_incoming(m3, "text")
    v3 = decide(m3, Model(lambda u: J(действие="записать", что="пробег", км=40500, источник=999999)))
    assert v3["итог"]["действие"] == "ничего" and v3["правило"] == "без_mid", f"без mid: {v3}"
    v4 = decide(m3, Model(lambda u: J(действие="записать", что="пробег", км=40500)))
    assert v4["правило"] == "без_mid", f"mid не назван: {v4}"
    v5 = decide(m3, Model(lambda u: J(действие="записать", что="пробег", км=40500, источник=mid_in(u))))
    assert v5["итог"]["действие"] == "записать" and v5["дверь"] == S._tdec.DOOR_ODO, f"контроль 40500: {v5}"


# ── − N2: второй вопрос того же вида ────────────────────────────────────────────

def test_n2_second_question_same_kind_refused():
    run(S._ask_mileage_confirm(Ctx(), CHAT, T_Q1, BIKE, "50000"))
    q = _MID[0]
    m = Msg("ok", uname=MECH, topic=T_Q1); S.feed_incoming(m, "text")
    ask = Model(lambda u: J(действие="спросить", вопрос="Какой пробег?", ждём_что="пробег", от_кого="сотрудник"))
    v = decide(m, ask)
    assert v["итог"]["действие"] == "ничего" and v["правило"] == "второй_вопрос" and f"#{q}" in v["итог"]["почему"], (
        f"второй вопрос не отклонён: {v}")
    m2 = Msg("ok", uname=MECH, topic=T_Q2); S.feed_incoming(m2, "text")
    v2 = decide(m2, ask)
    assert v2["итог"]["действие"] == "спросить" and v2["правило"] == "", f"контроль (вопроса нет): {v2}"


# ── − N3: флаг выключен → путь прежний байт в байт ──────────────────────────────

def test_n3_flag_off_path_byte_for_byte():
    base = os.environ.get("TOPIC_DECIDER_BASE_SRC")
    td = tempfile.mkdtemp(prefix="dec_trace_", dir=_TMP)

    def env_for(tag, extra):
        e = {"TOPIC_FEED_DIR": os.path.join(td, f"{tag}_feed"),
             "MILEAGE_Q_STATE": os.path.join(td, f"{tag}_mq.json"),
             "SVC_TOKENS_STATE": os.path.join(td, f"{tag}_svc.json"),
             "WORKS_PERSIST_STATE": os.path.join(td, f"{tag}_works.json"),
             "HINT_DEDUP_STATE": os.path.join(td, f"{tag}_hint.json")}
        e.update(extra)
        return e
    off = _child("--child-trace", extra_env=env_for("off", {FLAG: "0"}))
    on = _child("--child-trace", extra_env=env_for("on", {FLAG: "1"}))
    assert off["n_steps"] >= 5 and (off["sent"] or off["replies"]) and off["bridge"], f"сценарий пуст: {off}"
    assert not [c for c in off["claude"] if c[1] == "decider"], "флаг выключен, а модель решателя звалась"
    assert [c for c in on["claude"] if c[1] == "decider"], "положительный контроль: при флаге решатель звался"
    for k in ("sent", "replies", "notes"):
        assert on[k] == off[k], f"тень изменила действие ({k}): {on[k]} ≠ {off[k]}"
    assert on["feed"] == off["feed"], "тень изменила ленту темы (без событий decision)"
    if base and os.path.exists(os.path.join(base, "bot.py")):
        b = _child("--child-trace", extra_env=env_for("base", {"_TD_CHILD_SRC": base, FLAG: "0"}))
        for k in ("sent", "replies", "notes", "bridge", "claude", "feed", "errors"):
            assert b[k] == off[k], f"флаг выключен: {k} ≠ код без решателя\nбаза: {b[k]}\nветка: {off[k]}"
        print(f"    · сверено с кодом без решателя ({base}): отправок {len(off['sent'])}, ответов "
              f"{len(off['replies'])}, мозг {len(off['notes'])}, мост {len(off['bridge'])}, модель "
              f"{len(off['claude'])}, лента {len(off['feed'])} — равны")
    else:
        print("    · каталог базы не дан — сверка с кодом без решателя пропущена (только выкл/вкл)")
    # прямой вызов в ЖИВОМ цикле событий (вне цикла тень молчала бы и при сломанном выключателе)
    m, mdl = Msg("x", topic=T_X), Model(lambda u: "")

    async def call():
        return S.decider_shadow(m, bridge=FakeBridge(), claude=mdl)
    with flag(False):
        assert run(call()) is None and not mdl.calls, "флаг 0: тень обязана вернуть None и не звать модель"
    os.environ.pop(FLAG, None)
    assert run(call()) is None and not mdl.calls, "флага нет: тень обязана быть выключена"
    assert S._tdec.enabled() is False, "по умолчанию тень обязана быть выключена"


def _norm(x):
    s = json.dumps(x, ensure_ascii=False, default=repr, sort_keys=True)
    s = re.sub(r"\d{9,}(\.\d+)?", "<ts>", s)
    return re.sub(r"\b\d{1,2}:\d{2}\b", "<hh:mm>", s)


def _child_trace():
    tr = {"bridge": [], "claude": [], "notes": [], "errors": []}

    class RecBridge:
        def service_pending_get(s, *a, **k):
            tr["bridge"].append(["service_pending_get", _norm([a, k])]); return {"ok": False, "error": "not_found"}
        def __getattr__(s, name):
            if name.startswith("__"):
                raise AttributeError(name)
            def f(*a, **k):
                tr["bridge"].append([name, _norm([a, k])]); return {"ok": False, "items": []}
            return f

    class RecClaude:
        def quick(s, system, user, *a, **k):
            tr["claude"].append(["quick", k.get("tag", "")]); return ""
        def __getattr__(s, name):
            if name.startswith("__"):
                raise AttributeError(name)
            def f(*a, **k):
                tr["claude"].append([name, k.get("tag", "")]); return ""
            return f

    async def cap_reply(msg, context, context_note="", **k):
        tr["notes"].append(_norm(context_note))
    t = T_TR
    steps = []

    async def go():
        ctx = Ctx()
        with patch.object(bot, "bridge", RecBridge()), patch.object(bot, "claude", RecClaude()), \
             patch.object(bot, "manager_reply", cap_reply), \
             patch.object(S, "ensure_info_pin", new_callable=AsyncMock):
            for step in ("mech", "ask", "pym_reply", "pym_brain", "mech_da"):
                try:
                    if step == "mech":
                        await bot.handle_text(Upd(Msg("готово масло фильтр", uname=MECH, topic=t)), ctx)
                    elif step == "ask":
                        await S._ask_mileage_confirm(ctx, CHAT, t, BIKE, "38872")
                    elif step == "pym_reply":
                        await bot.handle_text(Upd(Msg("38972", uname=PYM, topic=t, reply_to=Ref(_MID[0]))), ctx)
                    elif step == "pym_brain":
                        await bot.handle_text(Upd(Msg("сколько км?", uname=PYM, topic=t, reply_to=Ref(5555))), ctx)
                    elif step == "mech_da":
                        await bot.handle_text(Upd(Msg("да", uname=MECH, topic=t)), ctx)
                except Exception as e:
                    tr["errors"].append([step, type(e).__name__])
                steps.append(step)
                pend = list(getattr(S, "_DECIDER_TASKS", ()) or ())
                if pend:
                    await asyncio.gather(*pend)
    run(go())
    p = os.path.join(os.environ["TOPIC_FEED_DIR"], f"{CHAT}_{t}.jsonl")
    feed = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                ev = json.loads(line)
                if ev.get("kind") == "decision":
                    continue
                ev.pop("ts", None)
                feed.append(_norm(ev))
    out = {"n_steps": len(steps), "sent": [_norm(x) for x in TRACE["sent"]],
           "replies": [_norm(x) for x in TRACE["replies"]], "notes": tr["notes"],
           "bridge": tr["bridge"], "claude": tr["claude"], "feed": feed, "errors": tr["errors"]}
    print("CHILD_RESULT " + json.dumps(out, ensure_ascii=False))


# ── − N4: ответ не JSON → «ничего: не понял» ────────────────────────────────────

def test_n4_not_json_is_nothing():
    P = S._tdec.parse
    nu = S._tdec.NOT_UNDERSTOOD
    for raw in (None, "", "Думаю, надо записать 38972", '{"действие": "записать"', "[1, 2]",
                '{"действие": "удалить", "что": "всё"}', '{"действие": "записать", "км": 38972}',
                '{"действие": "позвать", "кого": "механик", "зачем": "x"}',
                '{"действие": "ничего"} {"действие": "ответить", "текст": "x"}',
                'Ответ: {"действие": "ответить", "текст": "ок"}'):
        assert P(raw) == nu, f"не JSON/не по схеме принят за решение: {raw!r} → {P(raw)}"
    assert P('```json\n{"действие": "ответить", "текст": "ок"}\n```') == {"действие": "ответить", "текст": "ок"}
    m = Msg("что-то", uname=MECH, topic=T_X); S.feed_incoming(m, "text")
    v = decide(m, Model(lambda u: "Думаю, надо записать 38972"))
    assert v["итог"] == {"действие": "ничего", "почему": "не понял"} and v["модель"] == "ничего", f"проза: {v}"
    ev = [e for e in S._tfeed.read(CHAT, T_X, shadow=True) if e.get("kind") == "decision" and e.get("on") == m.message_id]
    assert ev and ev[-1]["parsed"] is False, f"событие тени не отметило непарсимый ответ: {ev}"
    def boom(u):
        raise RuntimeError("модель недоступна")
    v2 = decide(m, Model(boom))
    assert v2["итог"]["действие"] == "ничего", f"сбой модели: {v2}"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child-8952":
        _child_8952(sys.argv[2]); sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--child-trace":
        _child_trace(); sys.exit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} — решатель темы в тени (FAIL {bad})")
    sys.exit(1 if bad else 0)
