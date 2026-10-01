"""Вопрос о пробеге на диске + ответ РЕПЛАЕМ (01.10.2026, задание Штаба 0088-76e, SPLODOREPLY0110).

ЖИВОЙ СЛУЧАЙ (splinter.log, UTC; тексты людей сюда не переносим — только числа, время, id):
  30.09 11:19:54  фото приборки в теме байка; 11:20:55 vision: mileage=38872 conf=high
  30.09 11:23:01  вопрос «Вижу пробег 38872 км … Верно?» (подсказка L)
  30.09 18:23:43  splinter перезапущен — `_PENDING_MILEAGE` (память процесса) стёрт
  01.10 06:08:08  ответ Пыма «38972» реплаем → 06:08:11 «→ мозг»: перехват не взял (вопроса в
                  памяти нет, да и срок 3 ч вышел); переспрос, лишняя карточка.

ЧТО ПРОВЕРЯЕМ:
  + A. реплай-число на вопрос через 19 ч засчитан как ПРАВКА (38972 вместо 38872);
  + B. реплай «да» без числа через 19 ч засчитан как «да» (подтверждено 38872);
  + C. после ПЕРЕЗАПУСКА (отдельный процесс, память пуста) реплай засчитан;
  + D. живой случай целиком: перезапуск + 19 ч;
  − E. НЕ реплай после срока — по-старому (вопрос снят как протухший, ответ не засчитан);
  − F. реплай с тем же id сообщения из ЧУЖОЙ темы — не засчитан, вопрос своей темы не тронут;
  − G. реплай на ДРУГОЕ сообщение бота в той же теме после срока — не засчитан;
  − H. доверие прежнее: «да» реплаем от не доверенного не подтверждает (вопрос висит);
  − I. отвеченный вопрос второй раз реплаем не засчитывается (нет двойной записи);
  − J. новый вопрос в теме заменяет прежний: реплай на старый не засчитан;
  + K. без реплая в пределах срока — путь прежний;
  + L. роутер bot.py: оживление стоит ДО снятия протухшего и ДО фазы 2 ТО.

Чат, бот и сообщения выдуманные; сеть/LLM/_send замоканы; живых таблиц и Telegram тест не касается.
"""
import os, sys, json, asyncio, datetime, subprocess, tempfile
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["HINTS_DEDUP"] = "0"          # замок повторов подсказок здесь не предмет
_TMP = tempfile.gettempdir()
os.environ.setdefault("MILEAGE_Q_STATE", os.path.join(_TMP, f"mileage_q_reply_test_{os.getpid()}.json"))
os.environ.setdefault("SVC_TOKENS_STATE", os.path.join(_TMP, f"svc_tokens_reply_test_{os.getpid()}.json"))
os.environ.setdefault("WORKS_PERSIST_STATE", os.path.join(_TMP, f"works_reply_test_{os.getpid()}.json"))
import splinter as S

CHAT = -1009990001234          # выдуманный чат
TOPIC = 74
TOPIC2 = 75
BIKE = "NMAX 155 BLACK 8952"
OCR_KM = "38872"               # прочитано с фото
REAL_KM = "38972"              # на одометре; ответ реплаем
H19 = 19 * 3600
PYM = sorted(S.PYM_USERNAMES)[0]
MECH = "mech_fixture"          # выдуманный механик, не доверенный
BOT_ID = 777000


class U:
    def __init__(s, uname, uid=111, is_bot=False):
        s.username = uname; s.id = uid; s.is_bot = is_bot


class Chat:
    def __init__(s, cid): s.id = cid


class Ref:
    """Сообщение, на которое отвечают (reply_to_message)."""
    def __init__(s, mid, chat=CHAT, topic_created=False):
        s.message_id = mid; s.chat = Chat(chat); s.from_user = U("turbobaby_manager_bot", BOT_ID, True)
        s.forum_topic_created = (object() if topic_created else None)


class Msg:
    def __init__(s, text, uname=PYM, topic=TOPIC, reply_to=None, mid=20001):
        s.text = text; s.caption = None; s.photo = None
        s.chat_id = CHAT; s.message_thread_id = topic; s.message_id = mid
        s.date = datetime.datetime(2026, 10, 1, 6, 8, tzinfo=datetime.timezone.utc)
        s.from_user = U(uname)
        # Telegram кладёт служебное «тема создана» в reply_to_message каждому сообщению темы
        s.reply_to_message = reply_to if reply_to is not None else Ref(topic, topic_created=True)
        s.entities = None; s.caption_entities = None


class Ctx:
    class B:
        username = "turbobaby_manager_bot"; id = BOT_ID
    bot = B()


class FakeClaude:
    def quick(s, *a, **k): return json.dumps({"type": None, "event_type": None, "mileage": None, "works": []})
    def vision(s, *a, **k): return "{}"


class FakeBridge:
    """Заявки ТО нет; всё прочее — отказ без записи."""
    def service_pending_get(s, *a, **k): return {"ok": False, "error": "not_found"}
    def __getattr__(s, name): return lambda *a, **k: {"ok": False, "items": []}


SENDS = []
_MID = [12400]


async def rec_send(context, *, chat_id, text, message_thread_id=None, **k):
    _MID[0] += 1
    SENDS.append((chat_id, message_thread_id, _MID[0]))

    class _M:
        message_id = _MID[0]
    return _M()


CONFIRMED = []
AFTER = []


def spy_odo_confirmed(bridge, chat_id, topic_id, bike, num, questioned_km=None, **k):
    CONFIRMED.append((chat_id, topic_id, str(num), str(questioned_km)))


async def spy_after(context, bridge, chat_id, topic_id, bike, mileage, oil_hint=False):
    AFTER.append(str(mileage))


S._send = rec_send
S._send_retry = rec_send
S._odo_confirmed = spy_odo_confirmed
S._after_mileage = spy_after
S.set_topic_bike(CHAT, TOPIC, BIKE)
S.set_topic_bike(CHAT, TOPIC2, "NMAX 155 GREY 0000")


def reset():
    SENDS.clear(); CONFIRMED.clear(); AFTER.clear()
    S._PENDING_MILEAGE.clear(); S._SOFT_ODO_PENDING.clear(); S._AWAITING_REPLY.clear()
    S._PENDING_CORRECTION.clear(); S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear()
    S._SVC_TOKENS.clear()
    S._MILEAGE_Q.clear(); S._mileage_q_save()


def run(c): return asyncio.run(c)


def ask(topic=TOPIC, km=OCR_KM):
    """Вопрос «Вижу пробег N км … Верно?» — возвращает id отправленного сообщения-вопроса."""
    run(S._ask_mileage_confirm(Ctx(), CHAT, topic, BIKE, km))
    return SENDS[-1][2]


def age(topic=TOPIC, sec=H19):
    """Состарить вопрос: в памяти (то, что судит срок) и на диске (метка для журнала)."""
    k = (CHAT, topic)
    p = S._PENDING_MILEAGE.get(k)
    if p:
        S._PENDING_MILEAGE[k] = tuple(p[:4]) + (p[4] - sec,)
    q = S._MILEAGE_Q.get(S._mileage_q_key(CHAT, topic))
    if q:
        q["ts"] = float(q["ts"]) - sec
        S._mileage_q_save()


def on_disk():
    try:
        with open(S._mileage_q_path(), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def route(msg, bridge=None, claude=None):
    """ЗЕРКАЛО РОУТЕРА bot.py (handle_text, servicing-ветка), порядок дословно как в проде:
       0'') revive_mileage_question_by_reply → 0') expire_stale_mileage_question →
       0) handle_service_result → 1) correction → 2) handle_mileage_confirm. Дальше — «дальше»."""
    bridge = bridge or FakeBridge(); claude = claude or FakeClaude()
    tid = msg.message_thread_id

    async def _go():
        S.revive_mileage_question_by_reply(msg)
        await S.expire_stale_mileage_question(Ctx(), msg.chat_id, tid, msg.text)
        if await S.handle_service_result(msg, Ctx(), bridge, claude, msg.text):
            return "service_result"
        if S.pending_correction_for(msg.chat_id, tid):
            if await S.handle_correction_confirm(msg, Ctx(), bridge, msg.text):
                return "correction"
        if (S.pending_mileage_for(msg.chat_id, tid) or S.pending_odo_lower_for(msg.chat_id, tid)
                or S.pending_batch_odo_for(msg.chat_id, tid)):
            if await S.handle_mileage_confirm(msg, Ctx(), bridge, msg.text):
                return "mileage_confirm"
        return "дальше"
    return run(_go())


# ── + засчитывается ──────────────────────────────────────────────────────────

def test_a_reply_number_after_19h_counts_as_correction():
    reset(); q = ask()
    assert on_disk().get(S._mileage_q_key(CHAT, TOPIC), {}).get("msg_id") == q, "вопрос обязан лечь на диск с id"
    age()
    who = route(Msg(REAL_KM, reply_to=Ref(q)))
    assert who == "mileage_confirm", f"реплай-число через 19 ч ушёл в «{who}»"
    assert CONFIRMED == [(CHAT, TOPIC, REAL_KM, OCR_KM)], f"правка {REAL_KM} не засчитана: {CONFIRMED}"
    assert AFTER == [REAL_KM], f"ТО-трекер не получил {REAL_KM}: {AFTER}"


def test_b_reply_yes_after_19h_counts_as_yes():
    reset(); q = ask(); age()
    who = route(Msg("да", reply_to=Ref(q)))
    assert who == "mileage_confirm" and CONFIRMED == [(CHAT, TOPIC, OCR_KM, OCR_KM)], (
        f"«да» реплаем через 19 ч: {who} {CONFIRMED}")


def _child_route(q, text=REAL_KM):
    """Новый процесс = перезапуск: память пуста, есть только диск."""
    env = dict(os.environ)
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--child", str(q), text],
                       env=env, capture_output=True, text=True, timeout=120)
    for line in (r.stdout or "").splitlines():
        if line.startswith("CHILD_RESULT "):
            return json.loads(line[len("CHILD_RESULT "):])
    raise AssertionError(f"дочерний процесс без итога rc={r.returncode}: {(r.stderr or '')[-400:]}")


def test_c_reply_after_restart_counts():
    reset(); q = ask()
    res = _child_route(q)
    assert res["pending_before"] is False, "в новом процессе память обязана быть пустой"
    assert res["who"] == "mileage_confirm" and res["confirmed"] == [[CHAT, TOPIC, REAL_KM, OCR_KM]], (
        f"после перезапуска реплай не засчитан: {res}")
    assert res["left_on_disk"] is False, f"отвеченный вопрос обязан сняться с диска: {res}"


def test_d_live_case_restart_and_19h():
    reset(); q = ask(); age()
    res = _child_route(q)
    assert res["who"] == "mileage_confirm" and res["confirmed"] == [[CHAT, TOPIC, REAL_KM, OCR_KM]], (
        f"живой случай (перезапуск + 19 ч) не засчитан: {res}")


# ── − не засчитывается / по-старому ───────────────────────────────────────────

def test_e_no_reply_after_ttl_old_path():
    reset(); ask(); age()
    who = route(Msg(REAL_KM))                       # без реплая (только служебное «тема создана»)
    assert who != "mileage_confirm" and not CONFIRMED, f"НЕ реплай после срока засчитан: {who} {CONFIRMED}"
    assert not S.pending_mileage_for(CHAT, TOPIC), "протухший вопрос обязан быть снят, как раньше"


def test_f_reply_from_other_topic_not_counted():
    reset(); q = ask(); age()
    who = route(Msg(REAL_KM, topic=TOPIC2, reply_to=Ref(q)))
    assert who != "mileage_confirm" and not CONFIRMED, f"реплай из чужой темы засчитан: {who} {CONFIRMED}"
    assert not S.pending_mileage_for(CHAT, TOPIC), "вопрос своей темы оживать не должен"
    assert S._mileage_q_key(CHAT, TOPIC) in on_disk(), "вопрос своей темы обязан остаться на диске"


def test_g_reply_to_other_message_not_counted():
    reset(); q = ask(); age()
    who = route(Msg(REAL_KM, reply_to=Ref(q - 5)))
    assert who != "mileage_confirm" and not CONFIRMED, f"реплай на другое сообщение засчитан: {who} {CONFIRMED}"


def test_h_untrusted_yes_reply_trust_unchanged():
    reset(); q = ask(); age()
    route(Msg("да", uname=MECH, reply_to=Ref(q)))
    assert not CONFIRMED, f"«да» не доверенного подтвердило пробег: {CONFIRMED}"
    assert S._mileage_q_key(CHAT, TOPIC) in on_disk(), "вопрос обязан остаться открытым"


def test_i_answered_question_not_counted_twice():
    reset(); q = ask(); age()
    route(Msg(REAL_KM, reply_to=Ref(q)))
    CONFIRMED.clear()
    who = route(Msg(REAL_KM, reply_to=Ref(q), mid=20002))
    assert who != "mileage_confirm" and not CONFIRMED, f"второй реплай на отвеченный вопрос засчитан: {CONFIRMED}"


def test_j_new_question_replaces_old():
    reset(); q1 = ask(); q2 = ask(km="38990"); age()
    assert q1 != q2
    who = route(Msg(REAL_KM, reply_to=Ref(q1)))
    assert who != "mileage_confirm" and not CONFIRMED, f"реплай на заменённый вопрос засчитан: {CONFIRMED}"


def test_k_fresh_no_reply_unchanged():
    reset(); ask()
    who = route(Msg(REAL_KM))
    assert who == "mileage_confirm" and CONFIRMED == [(CHAT, TOPIC, REAL_KM, OCR_KM)], (
        f"путь без реплая в пределах срока сломан: {who} {CONFIRMED}")


def test_l_router_order_in_bot_py():
    src = open("/root/turbobaby-manager-bot/bot.py", encoding="utf-8").read()
    i_rv = src.index("splinter.revive_mileage_question_by_reply(")
    i_ex = src.index("splinter.expire_stale_mileage_question(")
    i_sr = src.index("splinter.handle_service_result(")
    i_mc = src.index("splinter.handle_mileage_confirm(")
    assert i_rv < i_ex < i_sr < i_mc, "порядок роутера: оживление → снятие протухшего → фаза 2 → перехват"


def _child_main(q, text):
    async def _noop(*a, **k): return None
    pend_before = bool(S._PENDING_MILEAGE)
    who = route(Msg(text, reply_to=Ref(int(q))))
    print("CHILD_RESULT " + json.dumps({
        "pending_before": pend_before, "who": who, "confirmed": [list(c) for c in CONFIRMED],
        "left_on_disk": S._mileage_q_key(CHAT, TOPIC) in on_disk()}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        _child_main(sys.argv[2], sys.argv[3]); sys.exit(0)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    bad = 0
    for fn in fns:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            bad += 1; print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{len(fns) - bad}/{len(fns)} — вопрос о пробеге: диск + ответ реплаем (FAIL {bad})")
    sys.exit(1 if bad else 0)
