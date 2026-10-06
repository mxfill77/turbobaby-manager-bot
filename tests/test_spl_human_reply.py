"""Ответ человеку — не к Splinter (06.10.2026, задание Штаба 012bfa-7f5.0610, SPLRELB0610) поверх SPLRELA0610: правило
SPLLANGC0610 без переводчика, слово владельца 06.10 19:43.

  + H1 `splinter.reply_to_other_human`: реплай на сообщение человека — да; бот, сам себе, «тема создана», не реплай,
       без автора — нет; не бросает
  − H2 01:30 — реплай владельца на альбом сотрудника: «позвать»/«спросить» самой модели → «ничего» по правилу
       «ответ_человеку», в Telegram ничего, «было» в журнале и в ленте; то же целиком через `bot.handle_text` в окне
       ожидания — мозг не зван, в Telegram ничего
  + H3 «записать» на ответе человеку исполняется, как сейчас
  + H4 «позвать» по правилу («убывание», «потолок») исполняется, двуязычно
  + H5 «ответить» → прежний путь (False)
  + H6 не реплай, реплай боту, себе, на «тема создана», ответ человеку с тегом Splinter → зов модели, как раньше
  + H7 `bot._addresses_bot`: касса (ожидание `_ask_currency`), Delivery и «Обслуживание» без решателя — как раньше;
       «Обслуживание» с решателем — ответ человеку не к Splinter; тег, ответ Splinter, без реплая, себе — обращение

Запуск: `python tests/test_spl_human_reply.py [--src <каталог со splinter.py и bot.py>]` — без `--src` судятся файлы
этого дерева; с `--src` — названные (снимок, мутант), прочие модули — из этого дерева. Telegram, мост и модель —
заглушки (подделка `claude.quick`); чаты, тема, байк, ники и фразы выдуманные; состояние — во временном каталоге.
"""
import os, sys, re, json, time, types, asyncio, datetime, tempfile, contextlib, logging
from unittest.mock import AsyncMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
SRC = ROOT
if "--src" in sys.argv:
    SRC = os.path.abspath(sys.argv[sys.argv.index("--src") + 1])
_TMP = tempfile.mkdtemp(prefix="spl_human_t_")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
for _k, _f in (("DECIDER_LIVE_STATE", "dlive.json"), ("TOPIC_FEED_DIR", "topic_feed"),
               ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
               ("MILEAGE_Q_STATE", "mq.json"), ("SVC_TOKENS_STATE", "svc.json"),
               ("WORKS_PERSIST_STATE", "works.json"), ("HINT_DEDUP_STATE", "hint.json")):
    os.environ[_k] = os.path.join(_TMP, _f)
os.environ["HINTS_DEDUP"] = "0"
os.environ["TOPIC_DECIDER_LIVE"] = "1"
for _k in ("SPLINTER_ASK_STAFF", "SPLINTER_RULES_FEED", "SPLINTER_TRANSLATE", "TOPIC_DECIDER_TIMEOUT_S",
           "TOPIC_DECIDER_SHADOW", "ODO_CEILING_KM", "TOPIC_DECIDER_CALL_WINDOW_S"):
    os.environ.pop(_k, None)
try:
    import fcntl  # noqa: F401  (Linux; на ПК его нет — заглушка только для импорта splinter)
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    sys.modules["fcntl"] = _fc


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m


class FakeMem:
    def all_topic_bikes(self): return {}
    def all_info_pins(self): return {}
    def set_topic_bike(self, *a, **k): return None


class FakeBridge:
    """Мост: всё — отказ без записи (заявки ТО нет, пробега из таблицы нет)."""
    def __getattr__(s, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: {"ok": False, "error": "not_found", "items": []}


class FakeAuditor:
    audit_groups = []
    def __init__(self, *a, **k): pass
    def set_audit_config(self, *a, **k): pass


_stub("dotenv", load_dotenv=lambda *a, **k: None)
_stub("bridge_client", BridgeClient=lambda *a, **k: FakeBridge(), agent_write=lambda *a, **k: None,
      card_budget=lambda *a, **k: contextlib.nullcontext())
_stub("claude_client", ClaudeClient=lambda *a, **k: None)
_stub("memory", Memory=FakeMem)
_stub("auditor", Auditor=FakeAuditor)
_stub("prompts", SYSTEM_PROMPT="", daily_pulse_prompt=lambda *a, **k: "")

import importlib.util  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SRC, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("splinter")
B = _load("bot")

CHAT, KASSA, DELIV, BIKE = -1009990006301, -1009990006302, -1009990006303, "NMAX 155 BLUE 0610"
S.GROUPS[CHAT] = "servicing"
S.GROUPS[KASSA] = "money"
S.GROUPS[DELIV] = "delivery"
OWNER, PYM, MECH = sorted(S.OWNER_USERNAMES)[0], sorted(S.PYM_USERNAMES)[0], "mech_fixture"
UID = {OWNER: 501, PYM: 502, MECH: 503}
BOT_ID = 777000
OWNER_TEXT = "Поменяй масло на этом байке и проверь задние колодки"
RESULTS = []
_MID = [64000]
_T = [900]
LOG = []


class _Cap(logging.Handler):
    def emit(self, rec):
        LOG.append(rec.getMessage())


S.log.addHandler(_Cap())


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  ← {str(info)[:300]}"))


def nmid():
    _MID[0] += 1
    return _MID[0]


def topic():
    _T[0] += 1
    S._TOPIC_NAMES[(CHAT, _T[0])] = BIKE
    return _T[0]


class U:
    def __init__(s, uname, is_bot=False):
        s.username, s.is_bot = uname, is_bot
        s.id = BOT_ID if is_bot else UID.get(uname, 599)


def BOT():
    return U("turbobaby_manager_bot", is_bot=True)


class Chat:
    def __init__(s, cid): s.id, s.type = cid, "supergroup"


class Ref:
    """Сообщение, на которое отвечают: человек (в т.ч. фото альбома), бот или служебное «тема создана»."""
    def __init__(s, author, mid=None, topic_created=False, album=False, chat=CHAT):
        s.message_id = mid if mid is not None else nmid()
        s.from_user = author
        s.forum_topic_created = object() if topic_created else None
        s.photo = [object()] if album else None
        s.media_group_id = "album-0130" if album else None
        s.chat = Chat(chat)


class Broken:
    """Сообщение, на чтении реплая которого всё падает — функция обязана не бросать."""
    from_user = U(OWNER)

    @property
    def reply_to_message(s):
        raise RuntimeError("сломанный объект")


class Sent:
    def __init__(s, m): s.message_id = m


class Msg:
    def __init__(s, text, uname, t, reply_to, chat=CHAT):
        s.text, s.caption, s.photo = text, None, None
        s.chat_id, s.chat, s.message_thread_id, s.message_id = chat, Chat(chat), t, nmid()
        s.date = datetime.datetime.fromtimestamp(time.time(), datetime.timezone.utc)
        s.from_user = U(uname) if uname is not None else None
        s.reply_to_message = reply_to
        s.entities = s.caption_entities = s.media_group_id = None
        s.replies, s.sent_mids = [], []

    async def reply_text(s, text, **k):
        s.replies.append(text)
        m = nmid()
        s.sent_mids.append(m)
        return Sent(m)


class TgBot:
    username, id = "turbobaby_manager_bot", BOT_ID

    def __init__(s): s.sent = []

    async def send_message(s, **kw):
        s.sent.append(kw)
        return Sent(nmid())

    def __getattr__(s, name):
        if name.startswith("__"):
            raise AttributeError(name)

        async def f(*a, **k):
            s.sent.append({"method": name})
            return Sent(nmid())
        return f


class Ctx:
    def __init__(s): s.bot = TgBot()


class Upd:
    def __init__(s, msg): s.message, s.callback_query, s.effective_chat = msg, None, Chat(msg.chat_id)


def J(**d):
    return json.dumps(d, ensure_ascii=False)


def mid_in(user):
    m = re.search(r"сообщение #(\d+)", user)
    return int(m.group(1)) if m else None


def call_pym(user):
    return J(действие="позвать", кого="Пым", зачем="владелец просит поменять масло")


def ask_km(user):
    return J(действие="спросить", вопрос="Какой сейчас пробег?", ждём_что="пробег", от_кого="Пым")


def answer(user):
    return J(действие="ответить", текст="Принял, передам механику")


def write_km(km):
    return lambda user: J(действие="записать", что="пробег", км=km, источник=mid_in(user))


def write_work(user):
    return J(действие="записать", что="замена масла", км=40500, источник=mid_in(user))


def to_thai(user):
    return "แปลแล้ว " + " ".join(re.findall(r"\d+", user)) + " ครับ"


class Model:
    """Подделка `claude.quick`: перевод RU→TH по системному тексту, иначе — решение решателя. Ведёт вызовы."""
    def __init__(s, decide, ru_th=to_thai):
        s.decide, s.ru_th, s.calls = decide, ru_th, []

    def quick(s, system, user, **kw):
        kind = "ru_th" if system == S.TRANSLATE_RU_TH else "decide"
        s.calls.append({"kind": kind, "user": user, "tag": kw.get("tag")})
        return {"ru_th": s.ru_th, "decide": s.decide}[kind](user)

    def n(s, kind):
        return sum(1 for c in s.calls if c["kind"] == kind)


def live(m, model, ctx=None):
    return asyncio.run(S.decider_live(m, ctx or Ctx(), FakeBridge(), model))


def blocks(text):
    """(шапка, тайский, русский) или (шапка, None, None), если двух блоков в одном сообщении нет."""
    head, _, rest = str(text).partition("\n")
    sep = "\n" + S._SEP + "\n🇷🇺 "
    if not rest.startswith("🇹🇭 ") or sep not in rest:
        return head, None, None
    th, ru = rest[len("🇹🇭 "):].split(sep, 1)
    return head, th, ru


def pym_called(m):
    return any(S.PYM_HANDLE in str(r) for r in m.replies)


def last_decision(t, mid, chat=CHAT):
    evs = [e for e in S._tfeed.read(chat, t, days=30, limit=0, shadow=True)
           if e.get("kind") == "decision" and e.get("live") and e.get("on") == mid]
    return evs[-1] if evs else {}


def rtoh(m):
    f = getattr(S, "reply_to_other_human", None)
    return f(m) if f is not None else "нет функции reply_to_other_human"


def addressed(m):
    return B._owner_addresses_bot(m, Ctx())


def via_bot(m, model):
    """Сообщение целиком через `bot.handle_text`: перехваты — заглушки «не моё», мозг — захват вызова."""
    brain = []

    async def cap_reply(msg, context, context_note="", **k):
        brain.append(context_note)
    ctx = Ctx()
    with contextlib.ExitStack() as st:
        for p in (patch.object(B, "manager_reply", cap_reply), patch.object(B, "claude", model),
                  patch.object(B, "bridge", FakeBridge()),
                  patch.object(S, "ensure_info_pin", new_callable=AsyncMock),
                  patch.object(S, "expire_stale_mileage_question", new_callable=AsyncMock),
                  patch.object(S, "handle_service_result", AsyncMock(return_value=False)),
                  patch.object(S, "handle_mileage_confirm", AsyncMock(return_value=False)),
                  patch.object(S, "handle_oil_backdated_service", AsyncMock(return_value=False)),
                  patch.object(S, "handle_mileage_correction", AsyncMock(return_value=False)),
                  patch.object(S, "handle_post_close_ack", AsyncMock(return_value=False)),
                  patch.object(S, "handle", new_callable=AsyncMock)):
            st.enter_context(p)
        asyncio.run(B.handle_text(Upd(m), ctx))
    return brain, ctx


# ---------------------------------------------------------------------------------------------- H1
def test_h1_reply_to_other_human():
    t = topic()
    for name, m, want in (
            ("реплай на сообщение человека", Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH))), True),
            ("реплай на фото альбома человека", Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), album=True)), True),
            ("реплай боту", Msg(OWNER_TEXT, OWNER, t, Ref(BOT())), False),
            ("реплай самому себе", Msg(OWNER_TEXT, OWNER, t, Ref(U(OWNER))), False),
            ("реплай на «тема создана»", Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), mid=t, topic_created=True)), False),
            ("не реплай", Msg(OWNER_TEXT, OWNER, t, None), False),
            ("без автора сообщения", Msg(OWNER_TEXT, None, t, Ref(U(MECH))), False),
            ("сломанный объект — не бросает", Broken(), False)):
        try:
            got = rtoh(m)
        except Exception as e:
            got = f"бросила {type(e).__name__}"
        check(f"H1 reply_to_other_human, {name} → {want}", got is want, got)


# ---------------------------------------------------------------------------------------------- H2
def test_h2_owner_reply_to_staff_album_quenched():
    for name, fn, want in (("позвать", call_pym, "позвать (Пым)"), ("спросить", ask_km, "спросить (ждём пробег)")):
        t = topic()
        m = Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), album=True))     # 01:30: владелец отвечает на альбом сотрудника
        ctx = Ctx()
        n0 = len(LOG)
        took = live(m, Model(fn), ctx)
        ev = last_decision(t, m.message_id)
        check(f"H2 01:30 «{name}» модели на ответ владельца сотруднику → «ничего» по правилу «ответ_человеку»",
              took is True and ev.get("rule") == "ответ_человеку"
              and (ev.get("final") or {}).get("действие") == "ничего", (took, ev))
        check(f"H2 01:30 «{name}»: в Telegram ничего (ни реплая, ни сообщения)",
              not m.replies and not ctx.bot.sent, (m.replies, ctx.bot.sent))
        lines = [ln for ln in LOG[n0:] if "решатель (бой)" in ln and f"#{m.message_id} " in ln]
        check(f"H2 01:30 «{name}»: строка журнала несёт «было {want}»",
              any(f"было {want}" in ln for ln in lines), lines)
        check(f"H2 01:30 «{name}»: прежний итог в ленте полем «было»",
              (ev.get("было") or {}).get("действие") == name, ev)
    t = topic()
    S.mark_awaiting(CHAT, t)
    m = Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), album=True))
    mdl = Model(call_pym)
    brain, ctx = via_bot(m, mdl)
    check("H2 через bot.handle_text в окне ожидания: решатель спрошен, мозг не зван, в Telegram ничего",
          mdl.n("decide") == 1 and not brain and not m.replies and not ctx.bot.sent,
          (mdl.n("decide"), len(brain), m.replies, ctx.bot.sent))


# ---------------------------------------------------------------------------------------------- H3
def test_h3_write_executed():
    t = topic()
    m = Msg("Масло поменяли на 40500", OWNER, t, Ref(U(MECH)))
    took = live(m, Model(write_work))
    ev = last_decision(t, m.message_id)
    check("H3 «записать» на ответе человеку исполняется, как сейчас (итог «записать», дверь названа, «было» нет)",
          took is True and (ev.get("final") or {}).get("действие") == "записать" and ev.get("door")
          and ev.get("rule") != "ответ_человеку" and not ev.get("было"), (took, ev))


# ---------------------------------------------------------------------------------------------- H4
def test_h4_rule_call_executed_bilingual():
    for name, km in (("убывание", 39000), ("потолок", 90000)):
        t = topic()
        S.feed_record(CHAT, t, "пробег подтверждён", km="40000", source="fixture", bike=BIKE)
        m = Msg(f"Пробег сейчас {km}", OWNER, t, Ref(U(MECH)))
        took = live(m, Model(write_km(km)))
        ev = last_decision(t, m.message_id)
        calls = [r for r in m.replies if S.PYM_HANDLE in str(r)]
        check(f"H4 правило «{name}» на ответе человеку: зов Пыма исполнен",
              took is True and ev.get("rule") == name and len(calls) == 1, (took, ev, m.replies))
        _, th, ru = blocks(calls[0] if calls else "")
        check(f"H4 правило «{name}»: зов двуязычный — 🇹🇭 тайский ответ подделки, 🇷🇺 русский зов",
              th is not None and th.startswith("แปลแล้ว") and ru is not None and S.PYM_HANDLE in ru, calls)


# ---------------------------------------------------------------------------------------------- H5
def test_h5_answer_old_path():
    t = topic()
    m = Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH)))
    took = live(m, Model(answer))
    check("H5 «ответить» на ответе человеку: прежний путь (False), сообщений решателя нет, итог не записан",
          took is False and not m.replies and not last_decision(t, m.message_id),
          (took, m.replies, last_decision(t, m.message_id)))


# ---------------------------------------------------------------------------------------------- H6
def test_h6_not_human_reply_as_before():
    for name, mk in (("не реплай", lambda t: Msg(OWNER_TEXT, OWNER, t, None)),
                     ("реплай боту", lambda t: Msg(OWNER_TEXT, OWNER, t, Ref(BOT()))),
                     ("реплай себе", lambda t: Msg(OWNER_TEXT, OWNER, t, Ref(U(OWNER)))),
                     ("реплай на «тема создана»",
                      lambda t: Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), mid=t, topic_created=True))),
                     ("ответ человеку с тегом Splinter",
                      lambda t: Msg(OWNER_TEXT + " @turbobaby_manager_bot", MECH, t, Ref(U(OWNER))))):
        t = topic()
        m = mk(t)
        took = live(m, Model(call_pym))
        ev = last_decision(t, m.message_id)
        check(f"H6 {name}: зов модели исполнен, как раньше (без правила «ответ_человеку»)",
              took is True and pym_called(m) and ev.get("rule") != "ответ_человеку" and not ev.get("было"),
              (took, m.replies, ev))


# ---------------------------------------------------------------------------------------------- H7
def test_h7_addresses_bot():
    try:
        os.environ["TOPIC_DECIDER_LIVE"] = "1"
        m0 = Msg("-500 бензин", OWNER, None, None, chat=KASSA)
        asyncio.run(S._ask_currency(Ctx(), FakeBridge(), None, m0,
                                    {"moves": [{"amount": -500, "currency": "?"}]}, "Наличка"))
        m = Msg("Это за бензин вчера", OWNER, None, Ref(U(MECH), chat=KASSA), chat=KASSA)
        check("H7 касса, ожидание _ask_currency открыто, решатель в бою: ответ человеку — обращение, как раньше",
              S.is_awaiting(KASSA, None) and addressed(m) is True, (S.is_awaiting(KASSA, None), addressed(m)))
        S.mark_awaiting(DELIV, 5)
        m = Msg("Завтра к 10", OWNER, 5, Ref(U(MECH), chat=DELIV), chat=DELIV)
        check("H7 Delivery, ожидание, решатель в бою: ответ человеку — обращение, как раньше", addressed(m) is True,
              addressed(m))
        t = topic()
        os.environ["TOPIC_DECIDER_LIVE"] = "0"
        S.mark_awaiting(CHAT, t)
        m = Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH)))
        check("H7 «Обслуживание» без решателя, ожидание: ответ человеку — обращение, как раньше", addressed(m) is True,
              addressed(m))
        os.environ["TOPIC_DECIDER_LIVE"] = "1"
        S.mark_awaiting(CHAT, t)
        m = Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), album=True))
        check("H7 «Обслуживание» с решателем, ожидание: ответ владельца сотруднику — не к Splinter",
              addressed(m) is False, addressed(m))
        for name, mm in (("тег Splinter", Msg(OWNER_TEXT + " @turbobaby_manager_bot", OWNER, t, Ref(U(MECH)))),
                         ("ответ самому Splinter", Msg(OWNER_TEXT, OWNER, t, Ref(BOT()))),
                         ("без реплая", Msg(OWNER_TEXT, OWNER, t, Ref(U(MECH), mid=t, topic_created=True))),
                         ("ответ себе", Msg(OWNER_TEXT, OWNER, t, Ref(U(OWNER))))):
            S.mark_awaiting(CHAT, t)
            check(f"H7 «Обслуживание» с решателем, ожидание, {name}: обращение к Splinter, как раньше",
                  addressed(mm) is True, addressed(mm))
    finally:
        os.environ["TOPIC_DECIDER_LIVE"] = "1"


if __name__ == "__main__":
    print(f"splinter.py, bot.py ← {SRC}")
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} упал: {type(e).__name__}", False, e)
    ok = sum(1 for _, r in RESULTS if r)
    print(f"ИТОГ {ok}/{len(RESULTS)}")
    sys.exit(0 if ok == len(RESULTS) else 1)
