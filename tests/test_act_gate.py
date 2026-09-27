"""ОДНО МЕСТО ПЕРЕД ДЕЙСТВИЕМ В ТЕМЕ БАЙКА (27.09.2026, правило владельца, задание Штаба 0055-74x).

Правило владельца 27.09: сверить сообщение с тем, что идёт в теме; адресовано человеку или неясно —
одним сообщением RU+TH сказать, что видно, спросить, верно ли понято и кто берёт; действовать после
«да». Прямое поручение Splinter и ясный факт работы — как сейчас. Разговор без задач — молчание.

Предмет — ЖИВОЙ `splinter.handle` (харнесс `tests/test_molch_vetka.py`) и чистое `act_gate`:
  (1) четыре живых случая 27.09 (04:38, 04:59, 05:21, 05:57 UTC) — ОТРИЦАТЕЛЬНЫЕ: двери не
      действуют по одному сообщению; мутант `ACT_GATE=0` (путь 09587d9) валит КАЖДЫЙ;
  (2) восемь тестов разведки #92 (T1–T8) — T1–T3 суть случаи (1), T4–T8 положительные: прямое
      поручение Splinter, правдоподобная приборка, явное «пробег N» доверенного, «готово»
      механика с перечнем — посимвольно как при `ACT_GATE=0`; повреждение на приёме — тревога
      есть, но без зашитого адресата; разговор без задач — молчание (регрессия 0041-74j);
  (3) чистые решения: форма числа, вероятное число, поручение в ленте, сбой → вопрос, импорты.

Фразы ВЫДУМАНЫ (того же вида: тег, порог, фото детали, чек как приборка), имён людей нет. Сеть,
Telegram и мост замоканы; память замков и журналов — во временном каталоге.
"""
import ast
import asyncio
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # дерево, которое судим
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NEVER_SILENT"] = "1"
os.environ["FLOOR_QUIET"] = "1"
os.environ["WORK_INTENT"] = "1"
os.environ["BIKE_POSITION"] = "1"
os.environ["TALK_STAGE"] = "1"
os.environ["ACT_GATE"] = "1"
_TMP = tempfile.mkdtemp(prefix="tb_actgate_")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import act_gate as G         # noqa: E402
import splinter as S         # noqa: E402

BIKE = "TESTBIKE 000ZZ PHUKET 4243"      # такого байка в парке нет
BOT = "tb_actgate_test_bot"
OWNER = sorted(S.OWNER_USERNAMES)[0]
PYM = sorted(S.PYM_USERNAMES)[0]
MECH = "testmech"
_TOPIC = [9300]
WRITES = {"add_event", "service_upsert", "service_pending_upsert", "set_fleet_oil",
          "set_fleet_service", "closing_upsert", "state_set"}

ON = {"ACT_GATE": "1"}
OFF = {"ACT_GATE": "0"}            # мутант: правка выключена = путь 09587d9


def _topic():
    _TOPIC[0] += 1
    return _TOPIC[0]


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


class _Bot:
    username = BOT
    id = 77002

    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 100 + len(self.sent)})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self, username=MECH, is_bot=False, uid=99003):
        self.id, self.username, self.is_bot, self.first_name = uid, username, is_bot, "T"


def _bot_msg():
    return type("R", (), {"from_user": _User(BOT, is_bot=True, uid=77002)})()


class _Msg:
    def __init__(self, text="", photo=False, reply_to=None, user=MECH, mid=555, topic=None):
        self.chat_id = _chat_servicing()
        self.text = text or None
        self.caption = None
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic or _topic()
        self.date = None
        self.from_user = _User(user)
        self.reply_to_message = reply_to
        self.media_group_id = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _Bridge:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append((name, dict(kw)))
            return {"ok": True, "items": [], "saved": True}
        return _any


class _Claude:
    def __init__(self, parse=None, vision=None):
        self.parse, self.vision_q = parse, list(vision or [])

    def quick(self, system, *a, **kw):
        if system is S.SERVICING_SYSTEM:
            if self.parse is None:
                return ""
            return self.parse if isinstance(self.parse, str) else json.dumps(self.parse)
        return ""

    def vision(self, *a, **kw):
        v = self.vision_q.pop(0) if self.vision_q else {}
        return v if isinstance(v, str) else json.dumps(v)


def _fresh():
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    os.environ["WORKS_PERSIST_STATE"] = tempfile.mktemp(prefix="works_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None


class _Env:
    def __init__(self, env):
        self.env = dict(env or {})

    def __enter__(self):
        self.prev = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.saved = (S.bike_from_topic, S._download_photo)
        S.bike_from_topic = lambda *a, **k: BIKE

        async def _dl(pm):
            return b"\xff\xd8 test"
        S._download_photo = _dl
        return self

    def __exit__(self, *a):
        S.bike_from_topic, S._download_photo = self.saved
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _run(msg, claude, *, env=None, ctx=None, br=None):
    """ЖИВОЙ `splinter.handle` под ручками. Возврат (тексты, вызовы моста, ctx, мост)."""
    ctx, br = ctx or _Ctx(), br or _Bridge()
    with _Env(env):
        _fresh()
        asyncio.run(S.handle(_Upd(msg), ctx, br, claude))
    return [s.get("text", "") for s in ctx.bot.sent], br.calls, ctx, br


def _writes(calls):
    return [n for n, _ in calls if n in WRITES]


# ============================================================================================
#  (1) ЧЕТЫРЕ ЖИВЫХ СЛУЧАЯ 27.09 — ОТРИЦАТЕЛЬНЫЕ (они же T1–T3 разведки #92 и случай #91)
# ============================================================================================
ASSIGN = {"type": "event", "event_type": "repair", "mileage": None,
          "works": ["замена масла", "колодки"]}


def _case_0438_assignment_to_human(env, topic=None):
    """04:38 (T1): владелец ответом на карточку бота отмечает механика и поручает работы →
    вопрос «кто берёт», ни заявки, ни «принял работы», ни строки событий."""
    m = _Msg("@mech_test сделай замену масла и колодок", reply_to=_bot_msg(), user=OWNER, topic=topic)
    texts, calls, _, _ = _run(m, _Claude(ASSIGN), env=env)
    ok = (len(texts) == 1 and "Кто берёт" in texts[0] and not _writes(calls)
          and not any("Принял" in t or "пришли пробег" in t for t in texts))
    return ok, (texts, _writes(calls))


def _case_0459_threshold_number(env):
    """04:59 (T2): порог «после 20 000» в тексте владельца → число не пишется пробегом."""
    parse = {"type": "event", "event_type": "repair", "mileage": 20000, "works": ["подшипники"]}
    texts, calls, _, _ = _run(_Msg("подшипники проверить после 20 000", user=OWNER),
                              _Claude(parse), env=env)
    wrote_km = [(n, kw) for n, kw in calls if n in WRITES and "20000" in json.dumps(kw)]
    ok = len(texts) == 1 and "20000" in texts[0] and "пробег" in texts[0] and not _writes(calls)
    return ok, (texts, wrote_km)


def _case_0521_removed_part_photo(env):
    """05:21 (T3): фото снятой детали от механика, которому поручены работы; зрение назвало
    «повреждение» → нет тревоги J и зашитого тега, нет «повреждения:» в строке, есть вопрос."""
    t = _topic()
    _case_0438_assignment_to_human(env, topic=t)
    vis = [{"kind": "other", "disassembled": True, "dirt": True,
            "damage": "изношенная щётка стартера"}]
    texts, calls, _, _ = _run(_Msg(photo=True, user="mech_test", topic=t, mid=556),
                              _Claude(vision=vis), env=env)
    dmg_rows = [kw for n, kw in calls if n == "add_event" and "повреждения" in str(kw.get("notes"))]
    ok = (len(texts) == 1 and "деталь" in texts[0] and "поручено" in texts[0]
          and S.PYM_HANDLE not in texts[0]
          and "повреждения:" not in texts[0] and not dmg_rows)
    return ok, (texts, dmg_rows)


def _case_0557_implausible_dashboard(env):
    """05:57 (#91): приборка 198864 при последнем 19800 → названо расхождение и вероятное число,
    вопроса «верно?» с кнопкой на 198864 нет."""
    t = _topic()
    v1 = [{"kind": "dashboard", "mileage": 19800, "mileage_confidence": "high"}]
    _run(_Msg(photo=True, topic=t, mid=560), _Claude(vision=v1), env=env)
    v2 = [{"kind": "dashboard", "mileage": 198864, "mileage_confidence": "high"}]
    texts, calls, ctx, _ = _run(_Msg(photo=True, topic=t, mid=561), _Claude(vision=v2), env=env)
    ok = (len(texts) == 1 and "неправдоподобна" in texts[0] and "19864" in texts[0]
          and not any("reply_markup" in s for s in ctx.bot.sent))
    return ok, texts


def _case_yes_from_untrusted(env):
    """#91: «да» на вопрос о пробеге от НЕ доверенного не принимается — вопрос висит."""
    t = _topic()
    chat = _chat_servicing()
    S._PENDING_MILEAGE[(chat, t)] = ("19864", BIKE, None, False, __import__("time").time())
    ctx, br = _Ctx(), _Bridge()
    with _Env(env):
        _fresh()
        asyncio.run(S.handle_mileage_confirm(_Msg("да", topic=t, user=MECH), ctx, br, "да"))
    still = (chat, t) in S._PENDING_MILEAGE
    S._PENDING_MILEAGE.pop((chat, t), None)
    texts = [s.get("text", "") for s in ctx.bot.sent]
    return (still and not _writes(br.calls) and any("Пым или владелец" in x for x in texts)), \
        (still, texts, _writes(br.calls))


NEGATIVE = [
    ("04:38 поручение человеку", _case_0438_assignment_to_human),
    ("04:59 порог в тексте", _case_0459_threshold_number),
    ("05:21 фото снятой детали", _case_0521_removed_part_photo),
    ("05:57 неправдоподобная приборка", _case_0557_implausible_dashboard),
    ("05:57 «да» не доверенного", _case_yes_from_untrusted),
]


def test_four_live_cases_of_27_09_do_not_act_on_one_message():
    bad = []
    for name, case in NEGATIVE:
        ok, detail = case(ON)
        if not ok:
            bad.append((name, detail))
    assert not bad, bad


def test_mutant_each_negative_case_turns_red_with_the_gate_off():
    alive = []
    for name, case in NEGATIVE:
        ok, detail = case(OFF)
        if ok:
            alive.append((name, detail))
    assert not alive, f"мутант выжил — случай ничего не проверяет: {alive}"


def test_yes_button_on_gate_question_runs_the_door():
    """«Верно» доверенного на вопрос о числе → дверь действует тем же путём (число — пробег)."""
    parse = {"type": "event", "event_type": "repair", "mileage": 20000, "works": ["подшипники"]}
    ctx, br = _Ctx(), _Bridge()
    texts, calls, ctx, br = _run(_Msg("подшипники проверить после 20 000", user=OWNER),
                                 _Claude(parse), env=ON, ctx=ctx, br=br)
    assert not _writes(calls), calls
    n = max(S._ACT_GATE_PENDING)

    class _Q:
        data = f"svc:agy:{n}"
        from_user = _User(MECH)
        message = None

        async def answer(self, *a, **k):
            return True

        async def edit_message_reply_markup(self, **k):
            return True

    class _U:
        callback_query = _Q()
    with _Env(ON):
        asyncio.run(S.handle_service_button(_U(), ctx, br))
    assert n in S._ACT_GATE_PENDING and not _writes(br.calls), "не доверенный не подтверждает число"
    _Q.from_user = _User(OWNER)
    with _Env(ON):
        asyncio.run(S.handle_service_button(_U(), ctx, br))
    assert n not in S._ACT_GATE_PENDING
    assert any("20000" in json.dumps(kw) for nm, kw in br.calls if nm in WRITES), br.calls


def _press(data, user, ctx, br, env):
    class _Q:
        from_user = _User(user)
        message = None

        async def answer(self, *a, **k):
            return True

        async def edit_message_reply_markup(self, **k):
            return True
    q = _Q()
    q.data = data

    class _U:
        callback_query = q
    with _Env(env):
        asyncio.run(S.handle_service_button(_U(), ctx, br))


def test_yes_button_on_mileage_only_from_trusted():
    """#91: кнопка «Да» на «Вижу N км, верно?» от НЕ доверенного не пишет; мутант — пишет."""
    out = {}
    for name, env in (("on", ON), ("off", OFF)):
        t = _topic()
        chat = _chat_servicing()
        tok = S._svc_put({"kind": "mileconf", "chat": chat, "topic": t, "bike": BIKE,
                          "mileage": "19864", "floor": None, "oil_hint": False})
        S._PENDING_MILEAGE[(chat, t)] = ("19864", BIKE, None, False, __import__("time").time())
        ctx, br = _Ctx(), _Bridge()
        _press(f"svc:mok:{tok}", MECH, ctx, br, env)
        out[name] = ((chat, t) in S._PENDING_MILEAGE, [n for n, _ in br.calls if n in WRITES])
        S._PENDING_MILEAGE.pop((chat, t), None)
    assert out["on"][0] and not out["on"][1], out
    assert (not out["off"][0]) or out["off"][1], f"мутант выжил: {out}"


# ============================================================================================
#  (2) ПОЛОЖИТЕЛЬНЫЕ (T4–T8 разведки #92)
# ============================================================================================
def _twins(fn):
    """Близнецы: ручка вкл и выкл → посимвольно одни тексты и одни ЗАПИСИ моста (чтения не
    сравниваются: сверка показания вверх читает свой одометр)."""
    fn(ON)                                                  # прогрев кэшей живого кода
    a, b = fn(ON), fn(OFF)
    return (a[0], [n for n, _ in a[1] if n in WRITES]), (b[0], [n for n, _ in b[1] if n in WRITES])


def test_t4_direct_instruction_to_splinter_as_before():
    parse = {"type": "event", "event_type": "repair", "mileage": 12345, "works": ["замена масла"]}
    a, b = _twins(lambda env: _run(_Msg(f"@{BOT} замена масла, пробег 12345"), _Claude(parse),
                                   env=env)[:2])
    assert a == b and not any("Кто берёт" in t for t in a[0]), (a, b)


def test_t5_plausible_dashboard_as_before():
    def one(env):
        t = _topic()
        _run(_Msg(photo=True, topic=t, mid=570),
             _Claude(vision=[{"kind": "dashboard", "mileage": 19800, "mileage_confidence": "high"}]),
             env=env)
        return _run(_Msg(photo=True, topic=t, mid=571),
                    _Claude(vision=[{"kind": "dashboard", "mileage": 19900,
                                     "mileage_confidence": "high"}]), env=env)[:2]
    a, b = _twins(one)
    assert a == b and any("19900" in t and "Верно" in t for t in a[0]), (a, b)


def test_t6_explicit_mileage_from_trusted_as_before():
    parse = {"type": "event", "event_type": "other", "mileage": 19130, "works": []}
    a, b = _twins(lambda env: _run(_Msg("пробег 19130", user=OWNER), _Claude(parse), env=env)[:2])
    assert a == b and not any("Кто берёт" in t for t in a[0]), (a, b)


def test_t7_done_with_list_from_mechanic_as_before():
    parse = {"type": "event", "event_type": "repair", "mileage": 12345,
             "works": ["замена масла", "колодки"]}
    a, b = _twins(lambda env: _run(_Msg("готово: поменял масло и колодки, 12345 км"),
                                   _Claude(parse), env=env)[:2])
    assert a == b and not any("Кто берёт" in t for t in a[0]), (a, b)


def test_t7b_done_without_km_still_gets_works_receipt():
    parse = {"type": "event", "event_type": "repair", "mileage": None,
             "works": ["замена масла", "колодки"]}
    a, b = _twins(lambda env: _run(_Msg("поменял масло и колодки"), _Claude(parse), env=env)[:2])
    assert a == b and len(a[0]) == 1 and "Кто берёт" not in a[0][0], (a, b)


def test_damage_on_intake_alarm_without_hardwired_addressee():
    """Повреждение при приёме (не ремонт, не снятая деталь) → тревога есть, адресат не зашит."""
    vis = [{"kind": "bike", "damage": "скол на пластике", "disassembled": False}]
    on = _run(_Msg(photo=True), _Claude(vision=list(vis)), env=ON)[0]
    off = _run(_Msg(photo=True), _Claude(vision=list(vis)), env=OFF)[0]
    assert any("скол" in t and "Кто глянет" in t and S.PYM_HANDLE not in t for t in on), on
    assert any(S.PYM_HANDLE in t for t in off), off         # мутант: тег зашит


def test_damage_photo_of_assigned_author_asks_even_without_repair_mark():
    """Лента: механику поручены работы; его фото с «повреждением» (не снятая деталь) — вопрос."""
    t = _topic()
    chat = _chat_servicing()
    S._TOPIC_FEED[(chat, t)] = [{"ts": __import__("time").time() - 600, "author": OWNER,
                                 "tags": [PYM], "works": ["колодк"]}]
    vis = [{"kind": "wheel", "damage": "износ колодки", "disassembled": False}]
    texts = _run(_Msg(photo=True, user=PYM, topic=t), _Claude(vision=vis), env=ON)[0]
    assert len(texts) == 1 and "поручено: колодк" in texts[0] and S.PYM_HANDLE not in texts[0], texts


def test_t8_talk_without_tasks_stays_silent():
    """Регрессия 0041-74j: разговор людей без задач — ни сообщения, ни записи."""
    chat = {"type": "none", "event_type": None, "mileage": None, "works": []}
    texts, calls, _, _ = _run(_Msg("@owner_test завтра заберу после обеда", user=MECH),
                              _Claude(chat), env=ON)
    assert texts == [] and not _writes(calls), (texts, calls)


# ============================================================================================
#  (3) ЧИСТЫЕ РЕШЕНИЯ
# ============================================================================================
def test_mileage_form():
    f = G.mileage_form
    assert f("подшипники проверить после 20 000", 20000) == "threshold"
    assert f("через 20 000 км масло", "20000") == "threshold"
    assert f("пробег 19130", 19130) == "explicit"
    assert f("одометр: 19 130", 19130) == "explicit"
    assert f("12345 км", 12345) == "explicit"
    assert f("ไมล์ 19130", 19130) == "explicit"
    assert f("масло 12345", 12345) == "bare"
    assert f("масло поменяли", 12345) == "absent"
    assert f("", None) == "absent"


def test_verdict_text_km():
    v = G.verdict
    d = G.DOOR_TEXT_KM
    assert v({"door": d, "text": "пробег 19130", "km": 19130, "trusted": True})["act"] == G.DO
    assert v({"door": d, "text": "пробег 19130", "km": 19130, "trusted": False})["act"] == G.ASK
    assert v({"door": d, "text": "после 20 000", "km": 20000, "trusted": True})["act"] == G.ASK
    assert v({"door": d, "text": "поменял масло 12345", "km": 12345})["act"] == G.DO
    assert v({"door": d, "text": "@x пробег 19130", "km": 19130, "trusted": True,
              "to_human": "тег человека @x"})["act"] == G.ASK
    assert v({"door": d, "text": "после 20 000", "km": 20000, "to_bot": True})["act"] == G.DO


def test_verdict_damage_and_works():
    v = G.verdict
    assert v({"door": G.DOOR_DAMAGE, "service": True})["act"] == G.ASK
    assert v({"door": G.DOOR_DAMAGE, "disassembled": True})["act"] == G.ASK
    assert v({"door": G.DOOR_DAMAGE, "assignment": {"works": ["колодк"]}})["act"] == G.ASK
    assert v({"door": G.DOOR_DAMAGE})["act"] == G.DO
    assert v({"door": G.DOOR_WORKS, "works": ["масло"], "to_human": "тег человека @x"})["act"] == G.ASK
    assert v({"door": G.DOOR_WORKS, "works": ["масло"]})["act"] == G.DO


def test_verdict_failure_is_a_question_not_an_action():
    class Bad(dict):
        def get(self, *a, **k):
            raise RuntimeError("проба")
    assert G.verdict(Bad())["act"] == G.ASK


def test_odo_candidate():
    assert G.odo_candidate(198864, 19800, 30000) == 19864
    assert G.odo_candidate(367474, 36400, 30000) == 36474
    assert G.odo_candidate(900000, 19800, 30000) is None


def test_assignment_for():
    now = 10000.0
    feed = [{"ts": now - 60, "author": "o", "tags": ["m"], "works": ["масл"]}]
    assert G.assignment_for(feed, "m", now, 3600)["works"] == ["масл"]
    assert G.assignment_for(feed, "z", now, 3600) == {}
    assert G.assignment_for(feed, "m", now, 30) == {}


def test_act_gate_imports_only_re_and_work_intent():
    tree = ast.parse(open(os.path.join(ROOT, "act_gate.py"), encoding="utf-8").read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"re", "work_intent"}, mods


if __name__ == "__main__":
    ok = fail = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ok += 1
            except Exception as e:
                fail += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
