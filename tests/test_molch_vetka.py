"""SPLINTER МОЛЧИТ, КОГДА ЛЮДИ ГОВОРЯТ МЕЖДУ СОБОЙ (26.09.2026, задание Штаба 0041-74j).

Правило Штаба: в теме байка Splinter говорит, только когда к нему обратились прямо или пришёл
факт для его работы — пробег, сделанная работа, повреждение на фото; разговор людей он читает
молча; совет и запись — по стадии дела. Разведка 0040-74i (SPLINTERRAZGOVOR2609, ПК-репо) нашла
семь ответов 26.09 в одной теме и четыре двери: пол ответа (4), совет C до сервиса (1), A1 по
подстроке масла (1), I — согласие как факт работ (1).

Предмет — ЖИВОЙ `splinter.handle` (тот же харнесс, что `tests/test_floor_quiet.py`):
  (1) семь ответов 26.09 — отрицательными случаями: бот молчит или не пишет ложного;
  (2) МУТАНТ у каждого: правка выключена (`TALK_STAGE=0`, у двери C — `BIKE_POSITION=0`) →
      случай ОБЯЗАН покраснеть, иначе тест ничего не проверяет;
  (3) положительные близнецы: прямой вопрос Splinter получает ответ; моторное масло без пробега
      просит одометр; работа с пробегом, «готово» с перечнем, приборка и повреждение — посимвольно
      как при выключенной ручке;
  (4) чистые решения: `work_intent` (исход AGREE только по просьбе), `addressee.other`.

Фразы ВЫДУМАНЫ (того же вида: тег, вопрос, цена, согласие, диагноз), имён людей нет. Сеть,
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
_TMP = tempfile.mkdtemp(prefix="tb_molch_")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import addressee as A        # noqa: E402
import reply_floor as F      # noqa: E402
import splinter as S         # noqa: E402
import work_intent as W      # noqa: E402

BIKE = "TESTBIKE 000ZZ PHUKET 4243"      # такого байка в парке нет
BOT = "tb_molch_test_bot"
_TOPIC = [9100]


def _topic():
    """Своя тема на случай: кулдаун вопроса об одометре и память сервиса темы не текут."""
    _TOPIC[0] += 1
    return _TOPIC[0]


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


class _Bot:
    username = BOT
    id = 77001

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
    def __init__(self, username="testmech", is_bot=False, uid=99002):
        self.id, self.username, self.is_bot, self.first_name = uid, username, is_bot, "T"


def _bot_msg():
    """Сообщение Splinter, на которое отвечают."""
    return type("R", (), {"from_user": _User(BOT, is_bot=True, uid=77001)})()


def _topic_anchor():
    """Служебное сообщение создания темы, автор — бот: Telegram кладёт его в reply_to."""
    return type("R", (), {"from_user": _User(BOT, is_bot=True, uid=77001),
                          "forum_topic_created": object()})()


class _Msg:
    def __init__(self, text="", photo=False, reply_to=None, caption=None, mid=555, topic=None):
        self.chat_id = _chat_servicing()
        self.text = text or None
        self.caption = caption
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic or _topic()
        self.date = None
        self.from_user = _User()
        self.reply_to_message = reply_to
        self.media_group_id = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _Bridge:
    """Отвечает на ЛЮБОЕ имя одинаково; копит (имя, состав аргументов)."""

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
        self.parse, self.vision_q, self.vision_calls = parse, list(vision or []), 0

    def quick(self, system, *a, **kw):
        if system is S.SERVICING_SYSTEM:
            if self.parse is None:
                return ""
            return self.parse if isinstance(self.parse, str) else json.dumps(self.parse)
        return ""

    def vision(self, *a, **kw):
        self.vision_calls += 1
        v = self.vision_q.pop(0) if self.vision_q else {}
        return v if isinstance(v, str) else json.dumps(v)


def _fresh():
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    os.environ["WORKS_PERSIST_STATE"] = tempfile.mktemp(prefix="works_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None


def _run(msg, claude, *, album=None, env=None):
    """ЖИВОЙ `splinter.handle` под заданными ручками. Возврат (тексты, вызовы моста)."""
    env = dict(env or {})
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    ctx, br = _Ctx(), _Bridge()
    saved = (S.bike_from_topic, S._download_photo)
    S.bike_from_topic = lambda *a, **k: BIKE

    async def _dl(pm):
        return b"\xff\xd8 test"
    S._download_photo = _dl
    try:
        _fresh()
        asyncio.run(S.handle(_Upd(msg), ctx, br, claude, album_msgs=album))
    finally:
        S.bike_from_topic, S._download_photo = saved
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return [s.get("text", "") for s in ctx.bot.sent], br.calls


ON = {"TALK_STAGE": "1"}
OFF = {"TALK_STAGE": "0"}          # мутант: правка выключена = путь 744619b

CHAT = {"type": "none", "event_type": None, "mileage": None, "works": []}
REMARK = {"type": "event", "event_type": "repair", "mileage": None, "works": [],
          "notes": "подшипник колеса гудит"}
OIL_DIAG = {"type": "event", "event_type": "repair", "mileage": None, "works": [],
            "notes": "течёт масло из вилки"}
AGREE = {"type": "event", "event_type": "repair", "mileage": None, "works": ["подшипники"]}


# ============================================================================================
#  (1) СЕМЬ ОТВЕТОВ 26.09 — ОТРИЦАТЕЛЬНЫЕ СЛУЧАИ. Каждый: (правило соблюдено?, подробность).
#      Второй аргумент — ручки; мутант зовёт тот же случай с выключенной правкой.
# ============================================================================================
def _case_c_album_before_service(env):
    """№1 (12138): альбом 2 фото с грязью, сервиса в теме ещё нет, положение неизвестно → нет C."""
    t = _topic()
    album = [_Msg(photo=True, mid=610, topic=t), _Msg(photo=True, mid=611, topic=t)]
    vis = [{"kind": "wheel", "dirt": True}, {"kind": "wheel", "dirt": True}]
    texts, _ = _run(album[0], _Claude(vision=vis), album=album, env=env)
    return (not any("🧽" in x for x in texts)), texts


def _case_a1_fork_oil(env):
    """№2 (12141): диагноз мастера со словом масла не о моторном, works=[] → событие легло, нет A1."""
    texts, calls = _run(_Msg("мастер смотрел: течёт масло из вилки, сальник менять"),
                        _Claude(OIL_DIAG), env=env)
    ev = [kw for _, kw in calls if kw.get("event_type") == "repair" and "notes" in kw]
    return (texts == [] and bool(ev)), (texts, len(ev))


def _case_floor_only_tag(env):
    """№3 (12143): один тег владельца ответом на сообщение бота → тишина."""
    texts, _ = _run(_Msg("@owner_test", reply_to=_bot_msg()), _Claude(None), env=env)
    return texts == [], texts


def _case_floor_repeat_diag_tagged(env):
    """№4 (12145) с другим адресатом: повтор диагноза ответом на «не понял», тег человека → тишина."""
    texts, calls = _run(_Msg("@owner_test повторяю: подшипник колеса гудит, надо менять",
                             reply_to=_bot_msg()), _Claude(REMARK), env=env)
    return texts == [], texts


def _case_floor_repeat_diag_direct(env):
    """№4 (12145) без другого адресата: прямое обращение → ответ есть, но БЕЗ лжи «ничего не
    записал» и без «не понял»: разборщик назвал событие."""
    texts, _ = _run(_Msg("повторяю: подшипник колеса гудит", reply_to=_bot_msg()),
                    _Claude(REMARK), env=env)
    ok = (len(texts) == 1 and "ничего не записал" not in texts[0]
          and "не понял" not in texts[0] and "замечание" in texts[0])
    return ok, texts


def _case_floor_workshop_price(env):
    """№5 (12147): цена мастерской ответом на сообщение бота → тишина."""
    texts, _ = _run(_Msg("в мастерской сказали 1200 бат за оба подшипника", reply_to=_bot_msg()),
                    _Claude(CHAT), env=env)
    return texts == [], texts


def _case_i_agree(env):
    """№6 (12150): согласие владельца на цену → ни «принял работы», ни просьбы пробега, ни записи."""
    wp = None
    texts, calls = _run(_Msg("ок, давай сделаем подшипники"), _Claude(AGREE), env=env)
    wp = os.environ.get("WORKS_PERSIST_STATE")
    journal = open(wp, encoding="utf-8").read() if wp and os.path.exists(wp) else ""
    wrote = [kw for _, kw in calls if any("подшипник" in str(v) for v in kw.values())]
    ok = texts == [] and "подшипник" not in journal and not wrote
    return ok, (texts, bool(journal), wrote)


def _case_floor_owner_tags_mech(env):
    """№7 (12152): ответ владельца на сообщение бота с тегом механика и пояснением → тишина."""
    texts, _ = _run(_Msg("@mech_test завтра отвезёшь в мастерскую, они ждут", reply_to=_bot_msg()),
                    _Claude(CHAT), env=env)
    return texts == [], texts


def _case_topic_anchor(env):
    """reply_to = служебное создание темы от бота → это не обращение к боту."""
    texts, _ = _run(_Msg("ну что там по байку", reply_to=_topic_anchor()), _Claude(CHAT), env=env)
    return texts == [], texts


NEGATIVE = (
    ("C_12138", _case_c_album_before_service, {"BIKE_POSITION": "0"}),
    ("A1_12141", _case_a1_fork_oil, OFF),
    ("floor_12143", _case_floor_only_tag, OFF),
    ("floor_12145_tag", _case_floor_repeat_diag_tagged, OFF),
    ("floor_12145_direct", _case_floor_repeat_diag_direct, OFF),
    ("floor_12147", _case_floor_workshop_price, OFF),
    ("I_12150", _case_i_agree, OFF),
    ("floor_12152", _case_floor_owner_tags_mech, OFF),
    ("floor_anchor", _case_topic_anchor, OFF),
)


def test_seven_answers_of_26_09_are_silent_or_true():
    bad = []
    for name, case, _ in NEGATIVE:
        ok, detail = case(ON)
        if not ok:
            bad.append((name, detail))
    assert not bad, bad


def test_mutant_each_negative_case_turns_red_with_the_fix_off():
    """МУТАНТ: выключенная правка валит КАЖДЫЙ отрицательный случай. Не валит — тест пуст."""
    alive = []
    for name, case, mut in NEGATIVE:
        ok, detail = case(mut)
        if ok:
            alive.append((name, detail))
    assert not alive, f"мутант выжил — случай ничего не проверяет: {alive}"


# ============================================================================================
#  (2) ПОЛОЖИТЕЛЬНЫЕ — речь по делу осталась
# ============================================================================================
def test_direct_question_to_splinter_by_reply_gets_an_answer():
    texts, _ = _run(_Msg("а ты что записал?", reply_to=_bot_msg()), _Claude(CHAT), env=ON)
    assert len(texts) == 1, texts


def test_direct_tag_of_splinter_with_a_human_tag_still_gets_an_answer():
    texts, _ = _run(_Msg(f"@{BOT} @mech_test сколько стоит?"), _Claude(CHAT), env=ON)
    assert len(texts) == 1, texts


def test_motor_oil_without_km_still_asks_for_the_odometer():
    diag = dict(OIL_DIAG, notes="моторное масло тёмное")
    texts, _ = _run(_Msg("моторное масло тёмное, пора менять"), _Claude(diag), env=ON)
    assert len(texts) == 1, texts


def _same_on_off(make_msg, make_claude):
    """Близнецы: ручка вкл и выкл → посимвольно одни тексты и одни вызовы моста."""
    _run(make_msg(), make_claude(), env=ON)                       # прогрев кэшей живого кода
    t = _topic()
    a = _run(make_msg(t), make_claude(), env=ON)
    b = _run(make_msg(t), make_claude(), env=OFF)
    return a, b


def test_real_oil_change_with_km_is_written_as_before():
    parse = {"type": "event", "event_type": "repair", "mileage": "30120",
             "works": ["замена моторного масла"]}
    a, b = _same_on_off(lambda t=None: _Msg("заменил моторное масло, пробег 30120", topic=t),
                        lambda: _Claude(parse))
    assert a == b, (a, b)
    assert a[0], "ответа нет — запись масла не пошла"


def test_done_with_list_and_km_goes_as_before():
    parse = {"type": "event", "event_type": "repair", "mileage": "30150",
             "works": ["замена подшипников переднего колеса", "замена задних колодок"]}
    a, b = _same_on_off(lambda t=None: _Msg("готово: подшипники и задние колодки, пробег 30150",
                                            topic=t),
                        lambda: _Claude(parse))
    assert a == b, (a, b)
    assert W.verdict("готово: подшипники и задние колодки", plan=True)["state"] == W.CLAIM


def test_done_without_km_still_gets_works_receipt():
    parse = {"type": "event", "event_type": "repair", "mileage": None,
             "works": ["замена подшипников переднего колеса"]}
    texts, _ = _run(_Msg("заменил подшипники переднего колеса"), _Claude(parse), env=ON)
    assert len(texts) == 1 and "Принял работы" in texts[0], texts


def test_dashboard_and_damage_photos_as_before():
    dash = {"kind": "dashboard", "mileage": "25908", "mileage_confidence": "high"}
    a, b = _same_on_off(lambda t=None: _Msg(photo=True, topic=t), lambda: _Claude(vision=[dash]))
    assert a == b and a[0] and "25908" in a[0][0], (a, b)
    dmg = {"kind": "bike", "damage": "царапина на крыле"}
    a, b = _same_on_off(lambda t=None: _Msg(photo=True, topic=t), lambda: _Claude(vision=[dmg]))
    assert a == b and a[0], (a, b)


# ============================================================================================
#  (3) ЧИСТЫЕ РЕШЕНИЯ
# ============================================================================================
def test_agree_only_on_request_and_only_without_done_verb():
    for p in ("ок, давай сделаем", "давайте меняем подшипники", "согласен, делаем",
              "ok go ahead", "let's do it", "ตกลง จัดไป", "จะเปลี่ยนพรุ่งนี้",
              "Сколько? Давай делаем"):
        assert W.verdict(p, plan=True)["state"] == W.AGREE, p
        assert W.verdict(p)["state"] != W.AGREE, p            # без просьбы исходов три, как было
    for p in ("заменил подшипники", "готово, давай следующий", "сделали, давай пробег",
              "เปลี่ยนแล้ว", "replaced bearings, let's check"):
        assert W.verdict(p, plan=True)["state"] != W.AGREE, p


def test_addressee_other():
    assert A.other("@mech_test глянь", bot_names=(BOT,)).startswith("тег человека")
    assert A.other(f"@{BOT} глянь", bot_names=(BOT,)) == ""
    assert A.other("за оба 1200 бат") == "цена для людей"
    assert A.other("какая цена?") == "цена для людей"
    assert A.other("когда заберёшь?") == "вопрос людям"
    assert A.other("а ты что записал?") == ""
    assert A.other("повторяю: подшипник гудит") == ""
    assert A.other("пробег 30120") == ""                       # число без валюты — не цена
    assert A.other("x", mentions_human=True) == "упоминание человека"


def test_non_motor_oil_is_not_oil_kind():
    for w in ("замена масла в амортизаторах", "тормозное масло", "น้ำมันเบรก", "fork oil"):
        assert S._classify_work(w) == "info", w
    assert S._classify_work("замена моторного масла") == "oil"
    assert S._classify_work("замена масла") == "oil"          # голое «масло» в РАБОТЕ — как было
    assert S._oil_non_motor("течёт масло из вилки")
    assert not S._oil_non_motor("колодки тормозные и масло")   # соседство, а не слово где-то
    assert not S._oil_motor_explicit("масло подтекает", {})
    assert S._oil_motor_explicit("น้ำมันเครื่องดำ", {})


def test_addressee_keeps_its_single_import():
    src = open(os.path.join(ROOT, "addressee.py"), encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"work_intent"}, mods


def test_floor_decision_keeps_its_single_import():
    src = open(os.path.join(ROOT, "reply_floor.py"), encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"write_fact"}, mods


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
