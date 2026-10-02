"""Вопрос сотрудникам офиса и снимок правил владельца (02.10.2026, задание Штаба 0119-77t, SPLDELIVERYASK0210).

  + A1 вопрос о байке → ОДИН пост в теме байка (тайский + русский, @username из THAI_HANDLES, без имён) и
       короткая просьба в Delivery со ссылкой; в «Агенты» — ничего. Через решатель (`_decider_execute`) — то же
  + A2 срочный → в Delivery пометка «клиент сейчас интересуется» (и по-тайски); обычный — «для ясности»
  + A3 реплай на вопрос → строка в мозг с источником (кто, id, когда, где, на что, ответ); повтор — без второй;
       реплай на просьбу в Delivery — тоже; бот и чужой реплай — ничего; исходник bot.py: хук стоит
  − A4 выключено → ни одного поста, ни записи, ни файла состояния; системный текст решателя байт в байт прежний;
       решатель идёт прежним путём (реплай в теме)
  − A5 нет ответа к сроку → ОДИН вопрос в «Агенты»; второй такт — ничего; отвеченный — не уточняется;
       цена/бронь → сразу «Агенты»; без тайского — ни поста; тот же вопрос — второго поста нет
  + A6 снимок правил в промпте решателя и мозга: время и возраст; неудача чтения не затирает прежний;
       выжимка берёт правила о Splinter/сотрудниках и не берёт чужие

Telegram, мост и модель — заглушки; чаты, ники и фразы выдуманные; состояние — во временном каталоге.
"""
import os, sys, json, time, types, asyncio, datetime, tempfile, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
_TMP = tempfile.mkdtemp(prefix="staff_ask_t_")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("BOT_TOKEN", "x")
os.environ["SPLINTER_ASK_STAFF_STATE"] = os.path.join(_TMP, "staff_ask_state.json")
os.environ["SPLINTER_RULES_SNAP"] = os.path.join(_TMP, "rules_snap.json")
os.environ["TOPIC_FEED_DIR"] = os.path.join(_TMP, "topic_feed")
os.environ["DECIDER_LIVE_STATE"] = os.path.join(_TMP, "dlive.json")
for _k, _f in (("MILEAGE_Q_STATE", "mileage_q.json"), ("SVC_TOKENS_STATE", "svc_tokens.json"),
               ("WORKS_PERSIST_STATE", "works.json"), ("HINT_DEDUP_STATE", "hint.json")):
    os.environ[_k] = os.path.join(_TMP, _f)
os.environ["HINTS_DEDUP"] = "0"
for k in ("SPLINTER_ASK_STAFF", "SPLINTER_RULES_FEED", "SPLINTER_ASK_STAFF_WAIT_S"):
    os.environ.pop(k, None)


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
    def __getattr__(s, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: {"ok": False}


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

import bot                       # noqa: E402
S = bot.splinter
import staff_ask                 # noqa: E402
import rules_snap                # noqa: E402
import topic_decider             # noqa: E402

SVC = S.SERVICING_CHAT
DLV = S.DELIVERY_CHAT_ID
AG = S.AGENTS_CHAT
BIKE = "PCX 160 WHITE 4711"      # выдуманный байк
TOPIC = 501
S._TOPIC_NAMES[(SVC, TOPIC)] = BIKE
Q_RU, Q_TH = "Байк готов к выдаче завтра утром?", "รถพร้อมส่งพรุ่งนี้เช้าไหมครับ"
RESULTS = []
_MID = [9000]


def mid():
    _MID[0] += 1
    return _MID[0]


class Sent:
    def __init__(s, m): s.message_id = m


class TgBot:
    username = "turbobaby_manager_bot"; id = 777000
    def __init__(s): s.sent = []

    async def send_message(s, **kw):
        m = mid()
        s.sent.append(dict(kw, mid=m))
        return Sent(m)


class Ctx:
    def __init__(s): s.bot = TgBot()


class U:
    def __init__(s, uname, uid, is_bot=False): s.username = uname; s.id = uid; s.is_bot = is_bot


class Ref:
    def __init__(s, m): s.message_id = m


class Msg:
    def __init__(s, chat, text, reply_to=None, uname="staff_fixture", uid=4242, is_bot=False, ts=None, topic=None):
        s.chat_id = chat; s.text = text; s.caption = None; s.message_id = mid()
        s.reply_to_message = Ref(reply_to) if reply_to is not None else None
        s.from_user = U(uname, uid, is_bot); s.message_thread_id = topic
        s.date = datetime.datetime.fromtimestamp(ts or time.time(), datetime.timezone.utc)
        s.replies = []

    async def reply_text(s, t, **k):
        s.replies.append(t)
        return Sent(mid())


class BrainBridge:
    """Узел мозга в памяти: read_doc / write_doc; ведёт записи."""
    def __init__(s, text="ОТВЕТЫ СОТРУДНИКОВ ОФИСА (узел-заглушка)"):
        s.doc, s.writes, s.reads = text, [], 0

    def _call(s, action, **k):
        s.reads += 1
        return {"ok": True, "text": s.doc}

    def write_doc(s, text, name=None, id=None):
        s.writes.append((name, text)); s.doc = text
        return {"ok": True}


def run(c): return asyncio.run(c)


@contextlib.contextmanager
def env(**kv):
    old = {k: os.environ.get(k) for k in kv}
    os.environ.update({k: str(v) for k, v in kv.items()})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def fresh_state():
    for p in (os.environ["SPLINTER_ASK_STAFF_STATE"],):
        if os.path.exists(p):
            os.replace(p, p + f".old{mid()}")      # не удаляем: откладываем в сторону


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))


def to(ctx, chat):
    return [s for s in ctx.bot.sent if s["chat_id"] == chat]


# ---------------------------------------------------------------------------------------------- A1 / A2
def test_a1_bike_question_topic_and_delivery():
    fresh_state()
    ctx = Ctx()
    with env(SPLINTER_ASK_STAFF="1"):
        r = run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH, urgency="для ясности"))
    t, d, a = to(ctx, SVC), to(ctx, DLV), to(ctx, AG)
    check("A1 итог: тема байка + Delivery", r.get("posted") == [staff_ask.PLACE_TOPIC, staff_ask.PLACE_DELIVERY], r)
    check("A1 в теме ровно один пост, тема — байка", len(t) == 1 and t[0].get("message_thread_id") == TOPIC, t)
    txt = t[0]["text"] if t else ""
    check("A1 пост: тайский и русский, вопрос на обоих", "🇹🇭" in txt and "🇷🇺" in txt and Q_TH in txt and Q_RU in txt
          and txt.index("🇹🇭") < txt.index("🇷🇺"), txt)
    th_part, ru_part = (txt.split("🇷🇺", 1) + [""])[:2]
    check("A1 пост: обращение @username из THAI_HANDLES в обеих половинах, имени нет",
          all(h in th_part and h in ru_part for h in S.THAI_HANDLES.values())
          and "Пым" not in txt and "тайц" not in txt.lower(), txt)
    check("A1 пост: вежливо, без давления (ครับ / «когда будет минутка»)",
          "ครับ" in txt and "когда будет минутка" in txt and "срочно!" not in txt.lower(), txt)
    check("A1 Delivery: одна просьба, без вопроса целиком, со ссылкой на пост темы",
          len(d) == 1 and Q_RU not in d[0]["text"] and
          f"https://t.me/c/{str(SVC)[4:]}/{TOPIC}/{t[0]['mid'] if t else '?'}" in d[0]["text"], d)
    check("A1 Delivery: срочность одной строкой «для ясности»",
          d and "для ясности" in d[0]["text"] and "клиент сейчас интересуется" not in d[0]["text"], d)
    check("A1 в «Агенты» ничего", not a, a)
    # через решатель: поля модели доезжают до двери
    raw = json.dumps({"действие": "спросить", "вопрос": "Масло меняли?", "ждём_что": "работы", "вид": "байк",
                      "вопрос_th": "เปลี่ยนน้ำมันเครื่องแล้วหรือยังครับ", "срочность": "клиент интересуется"},
                     ensure_ascii=False)
    dec, why = topic_decider.parse_checked(raw)
    check("A1 разбор решателя переносит поля вопроса сотрудникам",
          not why and dec.get("вопрос_th") and dec.get("срочность") == "клиент интересуется" and dec.get("вид") == "байк",
          dec)
    fresh_state()
    ctx2, m = Ctx(), Msg(SVC, "в теме что-то про байк", topic=TOPIC)
    v = topic_decider.rules(dec, {"open_kinds": {}})
    snap = {"chat": SVC, "topic": TOPIC, "bike": BIKE, "facts": {"mid": m.message_id}}
    with env(SPLINTER_ASK_STAFF="1"):
        door = run(S._decider_execute(m, ctx2, None, snap, v))
    check("A1 решатель: дверь вопроса сотрудникам, реплая прежнего пути нет",
          door.startswith("вопрос сотрудникам") and not m.replies and len(to(ctx2, SVC)) == 1
          and len(to(ctx2, DLV)) == 1, (door, m.replies, ctx2.bot.sent))
    dtxt = to(ctx2, DLV)[0]["text"] if to(ctx2, DLV) else ""
    check("A2 срочный → «клиент сейчас интересуется» (и по-тайски)",
          "клиент сейчас интересуется" in dtxt and "ลูกค้ากำลังสนใจ" in dtxt and "для ясности" not in dtxt, dtxt)


# ---------------------------------------------------------------------------------------------- A3
def test_a3_reply_to_brain_with_source():
    fresh_state()
    ctx, br = Ctx(), BrainBridge()
    with env(SPLINTER_ASK_STAFF="1"):
        run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH, urgency="для ясности"))
        qmid, dmid = to(ctx, SVC)[0]["mid"], to(ctx, DLV)[0]["mid"]
        ts = 1790900000.0
        m = Msg(SVC, "да, готов, бак полный", reply_to=qmid, ts=ts, topic=TOPIC)
        ok = run(S.staff_ask_reply(m, br))
        line = br.writes[-1][1].splitlines()[-1] if br.writes else ""
        check("A3 реплай → одна запись в узел мозга ответов", ok and len(br.writes) == 1
              and br.writes[0][0] == staff_ask.DOC_DEFAULT, br.writes)
        check("A3 источник: кто (@ник и id), когда (UTC и Пхукет), где, на какой пост",
              "@staff_fixture (id 4242)" in line and "UTC" in line and "Пхукет" in line
              and staff_ask.PLACE_TOPIC in line and f"#{m.message_id} ↩ на #{qmid}" in line, line)
        check("A3 на что: вопрос и байк; сам ответ", f"«{Q_RU}»" in line and BIKE in line
              and "«да, готов, бак полный»" in line, line)
        check("A3 прежнее содержимое узла сохранено", br.doc.startswith("ОТВЕТЫ СОТРУДНИКОВ ОФИСА"), br.doc[:60])
        run(S.staff_ask_reply(m, br))
        check("A3 повтор того же реплая — второй записи нет", len(br.writes) == 1, len(br.writes))
        calls = []
        r2 = staff_ask.on_reply(lambda line: (calls.append(line), (True, ""))[1], chat=SVC, reply_to=qmid,
                                mid=m.message_id, user_id=4242, username="staff_fixture", is_bot=False,
                                text="да, готов, бак полный", ts=ts)
        check("A3 повтор реплая — модуль не зовёт мозг вовсе (не только узел отказал)",
              not calls and not r2["recorded"] and "уже записан" in r2["why"], (calls, r2))
        m2 = Msg(DLV, "посмотрю после обеда", reply_to=dmid, uname="staff_two", uid=5151)
        run(S.staff_ask_reply(m2, br))
        check("A3 реплай на просьбу в Delivery → запись с местом Delivery",
              len(br.writes) == 2 and staff_ask.PLACE_DELIVERY in br.doc.splitlines()[-1]
              and "@staff_two (id 5151)" in br.doc.splitlines()[-1], br.doc.splitlines()[-1:])
        run(S.staff_ask_reply(Msg(SVC, "это бот", reply_to=qmid, is_bot=True), br))
        run(S.staff_ask_reply(Msg(SVC, "чужой реплай", reply_to=123), br))
        run(S.staff_ask_reply(Msg(SVC, "без реплая"), br))
        check("A3 бот / чужой реплай / без реплая — записей нет", len(br.writes) == 2, len(br.writes))
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    i_grp = src.find("if splinter.is_splinter_group(chat_id):")
    i_hook = src.find("await splinter.staff_ask_reply(msg, bridge)", i_grp)
    i_dec = src.find("splinter.decider_live_on()", i_grp)
    i_ag = src.find('splinter.agents_passive_intake(msg, "текст")')
    i_ag_hook = src.find("await splinter.staff_ask_reply(msg, bridge)", i_ag)
    check("A3 bot.py: хук ответа — первым в операционных группах и в «Агентах» до выхода",
          0 < i_grp < i_hook < i_dec and 0 < i_ag < i_ag_hook < src.find("return", i_ag_hook) and i_ag_hook < i_grp,
          (i_grp, i_hook, i_dec, i_ag, i_ag_hook))
    check("A3 bot.py: такты вопроса и снимка поставлены",
          "functools.partial(splinter.staff_ask_job, bridge=bridge)" in src
          and "functools.partial(splinter.rules_snap_job, bridge=bridge)" in src, "")


# ---------------------------------------------------------------------------------------------- A4
def test_a4_off_no_posts():
    fresh_state()
    ctx, br = Ctx(), BrainBridge()
    st = os.environ["SPLINTER_ASK_STAFF_STATE"]
    r = run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH, urgency="клиент интересуется"))
    r2 = run(S.staff_ask_post(ctx, kind="цена", bike=BIKE, q_ru="Сколько за месяц?"))
    ok = run(S.staff_ask_reply(Msg(SVC, "ответ", reply_to=1), br))
    run(S.staff_ask_job(ctx))
    check("A4 выкл.: постов 0, записей в мозг 0, чтений моста 0",
          not ctx.bot.sent and not br.writes and br.reads == 0 and not ok and not r["posted"] and not r2["posted"],
          (ctx.bot.sent, br.writes))
    check("A4 выкл.: файл состояния не создан", not os.path.exists(st), st)
    check("A4 выкл.: системный текст решателя байт в байт прежний", S._decider_live_system() == topic_decider.LIVE_SYSTEM)
    raw = json.dumps({"действие": "спросить", "вопрос": "Масло меняли?", "ждём_что": "работы", "вид": "байк",
                      "вопрос_th": "เปลี่ยนน้ำมันเครื่องแล้วหรือยังครับ"}, ensure_ascii=False)
    dec, _ = topic_decider.parse_checked(raw)
    v = topic_decider.rules(dec, {"open_kinds": {}})
    m = Msg(SVC, "в теме что-то", topic=TOPIC)
    door = run(S._decider_execute(m, ctx, None, {"chat": SVC, "topic": TOPIC, "bike": BIKE,
                                                 "facts": {"mid": m.message_id}}, v))
    check("A4 выкл.: решатель — прежний путь (реплай в теме), постов 0",
          door == "вопрос реплаем" and len(m.replies) == 1 and not ctx.bot.sent, (door, ctx.bot.sent))
    fb = BrainBridge()
    run(S.rules_snap_job(ctx, bridge=fb))
    check("A4 выкл. снимка: узел не читается", fb.reads == 0 and S.rules_prompt() is None, fb.reads)


# ---------------------------------------------------------------------------------------------- A5
def test_a5_no_answer_one_agents_question():
    fresh_state()
    ctx = Ctx()
    with env(SPLINTER_ASK_STAFF="1"):
        run(staff_ask.ask(S._sask_sender(ctx), kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH,
                          handles=["@Pleummmm"], servicing_chat=SVC, topic_id=TOPIC, delivery_chat=DLV,
                          agents_chat=AG, now=time.time() - 3600))
        run(S.staff_ask_job(ctx))
        check("A5 до срока (1 ч из 3) — в «Агенты» ничего", not to(ctx, AG), to(ctx, AG))
        fresh_state()
        ctx = Ctx()
        run(staff_ask.ask(S._sask_sender(ctx), kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH,
                          handles=["@Pleummmm"], servicing_chat=SVC, topic_id=TOPIC, delivery_chat=DLV,
                          agents_chat=AG, now=time.time() - 3 * 3600 - 5))
        qmid = to(ctx, SVC)[0]["mid"]
        run(S.staff_ask_job(ctx))
        ag = to(ctx, AG)
        check("A5 срок вышел → ровно один вопрос в «Агенты»", len(ag) == 1, ag)
        atxt = ag[0]["text"] if ag else ""
        check("A5 вопрос в «Агентах»: вопрос, байк, срок, ссылка на тему, ответ реплаем",
              Q_RU in atxt and BIKE in atxt and "не ответили за 3 ч" in atxt
              and f"/{TOPIC}/{qmid}" in atxt and "реплаем" in atxt and "🇹🇭" not in atxt, atxt)
        run(S.staff_ask_job(ctx))
        check("A5 второй такт — второго вопроса нет", len(to(ctx, AG)) == 1, to(ctx, AG))
        br = BrainBridge()
        run(S.staff_ask_reply(Msg(AG, "готов, проверили", reply_to=ag[0]["mid"], uname="manager_fx", uid=6161), br))
        check("A5 реплай в «Агентах» → запись с местом «Агенты»",
              len(br.writes) == 1 and staff_ask.PLACE_AGENTS in br.doc.splitlines()[-1], br.writes)
        # отвеченный до срока — не уточняется
        fresh_state()
        ctx, br = Ctx(), BrainBridge()
        run(staff_ask.ask(S._sask_sender(ctx), kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH,
                          handles=["@Pleummmm"], servicing_chat=SVC, topic_id=TOPIC, delivery_chat=DLV,
                          agents_chat=AG, now=time.time() - 4 * 3600))
        run(S.staff_ask_reply(Msg(SVC, "да", reply_to=to(ctx, SVC)[0]["mid"]), br))
        run(S.staff_ask_job(ctx))
        check("A5 отвеченный вопрос в «Агенты» не уходит", not to(ctx, AG), to(ctx, AG))
        # цена → сразу «Агенты»
        fresh_state()
        ctx = Ctx()
        r = run(S.staff_ask_post(ctx, kind="цена", bike=BIKE, q_ru="Какая цена на месяц для клиента?"))
        check("A5 цена → один пост в «Агенты», сотрудникам офиса ничего",
              r["posted"] == [staff_ask.PLACE_AGENTS] and len(to(ctx, AG)) == 1 and not to(ctx, SVC)
              and not to(ctx, DLV), ctx.bot.sent)
        run(S.staff_ask_job(ctx))
        check("A5 вопрос менеджерам такт не повторяет", len(to(ctx, AG)) == 1, to(ctx, AG))
        fresh_state()
        ctx = Ctx()
        r = run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=""))
        check("A5 без тайского текста — сотрудникам не пишем", not ctx.bot.sent and "тайск" in r["why"], r)
        run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH))
        run(S.staff_ask_post(ctx, kind="байк", bike=BIKE, q_ru=Q_RU, q_th=Q_TH))
        check("A5 тот же вопрос дважды — один пост в теме", len(to(ctx, SVC)) == 1, to(ctx, SVC))
        r = run(S.staff_ask_post(ctx, kind="байк", bike="НЕТ ТАКОГО 0000", q_ru="Где он?", q_th="อยู่ไหนครับ"))
        check("A5 темы байка нет — не пишем никуда", len(ctx.bot.sent) == 2 and "не найдена" in r["why"], r)


# ---------------------------------------------------------------------------------------------- A6
RULES = """ШАПКА УЗЛА
РЕШЕНИЕ ВЛАДЕЛЬЦА 30.09.2026 №4 — ВОПРОСЫ СОТРУДНИКАМ: ВОПРОС В ТЕМЕ БАЙКА
- НОМЕР: 30.09.2026-4. АВТОР: владелец.
- ПРАВИЛО:
  1) ГДЕ ВОПРОС: вопрос о байке Splinter задаёт в теме этого байка.
  2) ЧТО В DELIVERY: короткая просьба со срочностью.
- ОТКАТ: новой записью.

РЕШЕНИЕ ВЛАДЕЛЬЦА 29.09.2026 №9 — ЦВЕТ КАСКИ
- ПРАВИЛО:
  1) каски выдаём чёрные.
"""


def test_a6_rules_snapshot_in_prompts():
    p = os.environ["SPLINTER_RULES_SNAP"]
    br = BrainBridge(RULES)
    with env(SPLINTER_RULES_FEED="1"):
        run(S.rules_snap_job(Ctx(), bridge=br))
        d = rules_snap.load(p) or {}
        check("A6 снимок лёг: текст, время, длина", d.get("text") == RULES and d.get("read_ts") and d.get("len") == len(RULES), d)
        t0 = d.get("read_ts") or time.time()
        blk = rules_snap.prompt_block(now=t0 + 2 * 3600 + 5 * 60)
        check("A6 выжимка: возраст и время снимка в шапке", blk and "возраст 2 ч 5 мин" in blk and "снимок" in blk, blk)
        check("A6 выжимка: правило о Splinter есть, чужого (каски) нет",
              "вопрос о байке Splinter задаёт в теме этого байка" in blk and "каски" not in blk
              and "ОТКАТ" not in blk, blk)
        sysx = S._decider_live_system()
        check("A6 системный текст решателя = прежний + выжимка правил",
              sysx.startswith(topic_decider.LIVE_SYSTEM) and "## ПРАВИЛА ВЛАДЕЛЬЦА" in sysx
              and "Splinter задаёт в теме этого байка" in sysx, sysx[-300:])

        class Model:
            def __init__(s): s.calls = []
            def quick(s, system, user, **k):
                s.calls.append(system)
                return json.dumps({"действие": "ничего", "почему": "тест"}, ensure_ascii=False)
        mdl = Model()
        run(S._decider_live_decide({"facts": {}, "user": "u", "bike": None, "chat": SVC, "topic": TOPIC}, None, mdl))
        check("A6 модель решателя получила правила в системном тексте",
              mdl.calls and "## ПРАВИЛА ВЛАДЕЛЬЦА" in mdl.calls[0], mdl.calls[:1])
        with env(TOPIC_FEED_CONTEXT="1"):
            ctx_txt = S.topic_context(SVC, TOPIC)
        check("A6 контекст мозга темы несёт выжимку правил", ctx_txt and "## ПРАВИЛА ВЛАДЕЛЬЦА" in ctx_txt,
              (ctx_txt or "")[-200:])

        class Down:
            reads = 0
            def _call(s, *a, **k):
                s.reads += 1
                return {"ok": False, "error": "timeout"}
        run(S.rules_snap_job(Ctx(), bridge=Down()))
        d2 = rules_snap.load(p) or {}
        check("A6 неудача чтения не затирает прежний снимок", d2.get("text") == RULES and d2.get("read_ts") == t0
              and d2.get("fail_why"), d2)
        blk2 = rules_snap.prompt_block()
        check("A6 после неудачи — прежний снимок с пометкой", blk2 and "показан прежний снимок" in blk2
              and "Splinter задаёт" in blk2, blk2)
        check("A6 вопрос сотрудникам выкл. → добавки о сотрудниках в системном тексте нет",
              topic_decider.LIVE_STAFF_ADD not in S._decider_live_system(), "")
        with env(SPLINTER_ASK_STAFF="1"):
            check("A6 вопрос сотрудникам вкл. → добавка о полях есть", topic_decider.LIVE_STAFF_ADD in S._decider_live_system(), "")


if __name__ == "__main__":
    for fn in (test_a1_bike_question_topic_and_delivery, test_a3_reply_to_brain_with_source, test_a4_off_no_posts,
               test_a5_no_answer_one_agents_question, test_a6_rules_snapshot_in_prompts):
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            check(fn.__name__ + " (исключение)", False, repr(e))
    bad = [n for n, ok in RESULTS if not ok]
    print(f"ИТОГ {len(RESULTS) - len(bad)}/{len(RESULTS)}")
    sys.exit(1 if bad else 0)
