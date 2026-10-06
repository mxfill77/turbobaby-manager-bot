"""Внутренние беседы решателя — на двух языках (06.10.2026, задание Штаба 012b7-7eb.0510, SPLLANGA0610).

Повод: 06.10 01:30 Splinter позвал Пыма в теме байка только по-русски. Слово владельца 06.10: 01:50 «Когда идет
обращение к персоналу всегда надо делать внутри сообщение на двух языках так сотрудники тайцы»; 01:52 «Всегда
давать дауязычные сообщения в таких случаях внутренних бесед».

  + Z1 «позвать»: ОДНО сообщение, шапка «🐀 Splinter», 🇹🇭 с тайскими буквами, 🇷🇺 равен прежнему тексту
  + Z2 «спросить» (мимо `staff_ask_post`): то же; вопрос открыт прежним видом (дедуп вопросов прежний)
  − Z3 сбой перевода (модель упала · пусто · без тайских букв · модели нет) → оба блока, тайский указатель
  − Z4 окно зова прежнее: второй зов в окне — ни сообщения, ни перевода
  − Z5 вопрос сотрудникам через `staff_ask_post` не тронут: перевода нет, реплая нет
  + Z6 решатель в бою передаёт модель двери; перевод идёт в потоке, а не в цикле событий

Страховки выпуска «только A» (06.10.2026, задание Штаба 012bf-7f3.0610, SPLRELA0610):
  − Z7 перевод не дольше таймаута решателя: модель спит дольше — указатель за доли секунды, строка журнала
       с секундами, решатель идёт дальше (зов и вопрос ушли, окно и вопрос отмечены)
  − Z8 запасной текст без модели: указатель без вызова модели и без строки исключения (модели нет · таймаут ·
       сборка упала); форма та же, что у `bilingual_from_ru` при сбое перевода
  − Z9 `_no_car` целым словом: «машинное масло», «машинка» и производные целы; «машина», «автомобиль» и их
       падежи → «байк»; тайская замена и пустой вход — как были

Запуск: `python tests/test_spl_lang.py [--src <каталог со splinter.py>]` — без `--src` судится splinter.py
этого дерева; с `--src` — названный файл (база origin/main, мутант), прочие модули — из этого дерева.
Telegram и модель — заглушки; чат, тема, байк и фразы выдуманные; состояние — во временном каталоге.
"""
import os, sys, re, json, types, asyncio, tempfile, threading, importlib.util, ast, logging, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
SRC = ROOT
if "--src" in sys.argv:
    SRC = os.path.abspath(sys.argv[sys.argv.index("--src") + 1])
_TMP = tempfile.mkdtemp(prefix="spl_lang_t_")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["DECIDER_LIVE_STATE"] = os.path.join(_TMP, "dlive.json")
os.environ["TOPIC_FEED_DIR"] = os.path.join(_TMP, "topic_feed")
os.environ["SPLINTER_ASK_STAFF_STATE"] = os.path.join(_TMP, "staff_ask_state.json")
os.environ["HINTS_DEDUP"] = "0"
for _k in ("SPLINTER_ASK_STAFF", "SPLINTER_RULES_FEED"):
    os.environ.pop(_k, None)
try:
    import fcntl  # noqa: F401  (Linux; на ПК его нет — заглушка только для импорта splinter)
except ImportError:
    _f = types.ModuleType("fcntl")
    _f.LOCK_SH, _f.LOCK_EX, _f.LOCK_NB, _f.LOCK_UN = 1, 2, 4, 8
    _f.flock = lambda *a, **k: None
    sys.modules["fcntl"] = _f

_spec = importlib.util.spec_from_file_location("splinter", os.path.join(SRC, "splinter.py"))
S = importlib.util.module_from_spec(_spec)
sys.modules["splinter"] = S
_spec.loader.exec_module(S)
import topic_decider  # noqa: E402

CHAT, BIKE = -1009990006100, "PCX 160 WHITE 0610"
POINTER = "ดูรายละเอียดในข้อความภาษารัสเซียด้านล่างครับ"
THAI = re.compile("[฀-๿]")
RESULTS = []
_MID = [61000]
_T = [600]


def check(name, ok, info=""):
    RESULTS.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  ← {str(info)[:300]}"))


def mid():
    _MID[0] += 1
    return _MID[0]


def topic():
    _T[0] += 1
    return _T[0]


class Sent:
    def __init__(s, m): s.message_id = m


class Msg:
    def __init__(s, t):
        s.chat_id, s.message_thread_id, s.message_id, s.replies = CHAT, t, mid(), []

    async def reply_text(s, text, **k):
        s.replies.append(text)
        return Sent(mid())


class TgBot:
    def __init__(s): s.sent = []

    async def send_message(s, **kw):
        m = mid()
        s.sent.append(dict(kw, mid=m))
        return Sent(m)


class Ctx:
    def __init__(s): s.bot = TgBot()


class Thai:
    """Переводчик-заглушка: тайский текст с числами и латиницей оригинала; ведёт вызовы и поток вызова."""
    def __init__(s): s.calls, s.threads = [], []

    def quick(s, system, user, **kw):
        s.calls.append({"system": system, "user": user, "tag": kw.get("tag")})
        s.threads.append(threading.current_thread() is threading.main_thread())
        nums = " ".join(re.findall(r"\d+", user))
        lat = " ".join(re.findall(r"@?[A-Za-z]{2,}", user))
        return f"แจ้งเตือน {nums} {lat} ครับ".strip()


class Boom:
    calls = []
    def quick(s, *a, **k): raise RuntimeError("модель недоступна")


class Empty:
    def quick(s, *a, **k): return ""


class Latin:
    def quick(s, *a, **k): return "translated text without thai"


class Slow:
    """Переводчик, который спит дольше таймаута решателя: держится на защёлке до HOLD с, потом отвечает по-тайски.
    Тест отпускает защёлку после замера, чтобы поток не держал прогон."""
    HOLD = 2.0

    def __init__(s): s.calls, s.gate = [], threading.Event()

    def quick(s, system, user, **kw):
        s.calls.append({"system": system, "user": user})
        s.gate.wait(s.HOLD)
        return "แจ้งเตือน ครับ"


class Rec(logging.Handler):
    """Журнал splinter в руки теста: сообщение, уровень и есть ли трасса исключения."""
    def __init__(s):
        super().__init__(0)
        s.rows = []

    def emit(s, r):
        s.rows.append((r.levelno, r.getMessage(), bool(r.exc_info)))


def run_logged(model, v, tmo=None, t=None):
    """Дверь решателя одним циклом событий: время до возврата двери (внутри цикла, без закрытия пула потоков),
    журнал splinter и таймаут решателя через его ручку `TOPIC_DECIDER_TIMEOUT_S`."""
    t = t if t is not None else topic()
    m, ctx = Msg(t), Ctx()
    snap = {"chat": CHAT, "topic": t, "bike": BIKE, "facts": {"mid": m.message_id}}
    out, rec = {}, Rec()

    async def go():
        t0 = time.monotonic()
        try:
            out["door"] = await S._decider_execute(m, ctx, None, snap, v, claude=model)
        except Exception as e:
            out["door"] = f"{type(e).__name__}: {e}"
        out["dt"] = time.monotonic() - t0
        gate = getattr(model, "gate", None)
        if gate is not None:
            gate.set()

    old_tmo, old_lvl = os.environ.get("TOPIC_DECIDER_TIMEOUT_S"), S.log.level
    if tmo is not None:
        os.environ["TOPIC_DECIDER_TIMEOUT_S"] = str(tmo)
    S.log.addHandler(rec)
    S.log.setLevel(logging.INFO)
    try:
        asyncio.run(go())
    finally:
        S.log.removeHandler(rec)
        S.log.setLevel(old_lvl)
        if old_tmo is None:
            os.environ.pop("TOPIC_DECIDER_TIMEOUT_S", None)
        else:
            os.environ["TOPIC_DECIDER_TIMEOUT_S"] = old_tmo
    return out.get("door"), out.get("dt"), m, ctx, t, rec.rows


def no_trace(rows):
    """Нет строки исключения: ни трассы, ни записи уровня ERROR и выше."""
    return not any(tr or lvl >= logging.ERROR for lvl, _, tr in rows)


def run(c):
    return asyncio.run(c)


def blocks(text):
    """(шапка, тайский, русский) или (шапка, None, None), если двух блоков в одном сообщении нет."""
    head, _, rest = str(text).partition("\n")
    sep = "\n" + S._SEP + "\n🇷🇺 "
    if not rest.startswith("🇹🇭 ") or sep not in rest:
        return head, None, None
    th, ru = rest[len("🇹🇭 "):].split(sep, 1)
    return head, th, ru


def call_v(why):
    return {"итог": {"действие": "позвать", "кого": "Пым", "зачем": why}, "правило": "убывание", "дверь": ""}


def ask_v(q, wait="пробег"):
    return {"итог": {"действие": "спросить", "вопрос": q, "ждём_что": wait, "от_кого": "Пым"},
            "правило": "", "дверь": ""}


def execute(model, v, t=None, use_kw=True):
    t = t if t is not None else topic()
    m, ctx = Msg(t), Ctx()
    snap = {"chat": CHAT, "topic": t, "bike": BIKE, "facts": {"mid": m.message_id}}
    try:
        if use_kw:
            door = run(S._decider_execute(m, ctx, None, snap, v, claude=model))
        else:
            door = run(S._decider_execute(m, ctx, None, snap, v))
    except TypeError as e:            # база: у двери нет параметра модели
        door = f"TypeError: {e}"
    return door, m, ctx, t


# ---------------------------------------------------------------------------------------------- Z1
def test_z1_call_bilingual():
    why = "пробег 39000 ниже записанного 40000"
    old = f"🐀 Splinter\n🙋 {S.PYM_HANDLE}: {why}"
    mdl = Thai()
    door, m, ctx, t = execute(mdl, call_v(why))
    check("Z1 позвать: дверь «зов Пыма», ровно одно сообщение реплаем, мимо send_message",
          door == "зов Пыма" and len(m.replies) == 1 and not ctx.bot.sent, (door, m.replies, ctx.bot.sent))
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z1 позвать: в одном сообщении оба блока, 🇹🇭 первым", th is not None and ru is not None,
          m.replies)
    check("Z1 позвать: шапка прежняя «🐀 Splinter»", head == "🐀 Splinter", head)
    check("Z1 позвать: в тайском блоке тайские буквы, кириллицы нет",
          th is not None and THAI.search(th) and not re.search("[А-Яа-яЁё]", th), th)
    check("Z1 позвать: русский блок равен прежнему тексту (без шапки) — с @-хэндлом Пыма",
          ru == old.split("\n", 1)[1] and S.PYM_HANDLE in (ru or ""), (ru, old))
    check("Z1 позвать: перевод — один вызов TRANSLATE_RU_TH с прежним русским текстом",
          len(mdl.calls) == 1 and mdl.calls[0]["system"] == S.TRANSLATE_RU_TH
          and mdl.calls[0]["user"] == old.split("\n", 1)[1], mdl.calls)
    check("Z1 позвать: окно зова отмечено mid отправленного сообщения (прежняя память)",
          (S._DLIVE["calls"].get(S._dkey(CHAT, t)) or {}).get("mid") is not None, S._DLIVE["calls"])


# ---------------------------------------------------------------------------------------------- Z2
def test_z2_ask_bilingual():
    q = "Сколько км на одометре?"
    old = f"🐀 Splinter\n{q}"
    mdl = Thai()
    door, m, ctx, t = execute(mdl, ask_v(q))
    check("Z2 спросить: дверь «вопрос реплаем», ровно одно сообщение, мимо send_message",
          door == "вопрос реплаем" and len(m.replies) == 1 and not ctx.bot.sent, (door, m.replies))
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z2 спросить: в одном сообщении оба блока", th is not None and ru is not None, m.replies)
    check("Z2 спросить: шапка прежняя", head == "🐀 Splinter", head)
    check("Z2 спросить: в тайском блоке тайские буквы", th is not None and THAI.search(th), th)
    check("Z2 спросить: русский блок равен прежнему тексту", ru == old.split("\n", 1)[1], (ru, old))
    check("Z2 спросить: перевод — один вызов с вопросом", len(mdl.calls) == 1 and mdl.calls[0]["user"] == q,
          mdl.calls)
    asks = S._dlive_asks(CHAT, t)
    check("Z2 спросить: вопрос открыт прежним видом (второй того же вида правила не пустят)",
          asks.get("пробег") is not None and asks["пробег"] in S._dlive_mids(CHAT, t)
          and topic_decider.rules({"действие": "спросить", "вопрос": q, "ждём_что": "пробег"},
                                  {"open_kinds": asks})["правило"] == "второй_вопрос", asks)


# ---------------------------------------------------------------------------------------------- Z3
def test_z3_translation_failure_both_blocks():
    why, q = "пробег 75000 выше потолка", "Какие работы сделаны?"
    for name, mdl in (("модель упала", Boom()), ("пустой ответ", Empty()), ("без тайских букв", Latin()),
                      ("модели нет", None)):
        door, m, _, _ = execute(mdl, call_v(why))
        head, th, ru = blocks(m.replies[0] if m.replies else "")
        check(f"Z3 позвать, {name}: оба блока, 🇹🇭 — тайский указатель, 🇷🇺 — прежний текст",
              door == "зов Пыма" and len(m.replies) == 1 and th == POINTER
              and ru == f"🙋 {S.PYM_HANDLE}: {why}", (door, m.replies))
        door, m, _, _ = execute(mdl, ask_v(q, "работы"))
        head, th, ru = blocks(m.replies[0] if m.replies else "")
        check(f"Z3 спросить, {name}: оба блока, 🇹🇭 — тайский указатель, 🇷🇺 — прежний текст",
              door == "вопрос реплаем" and len(m.replies) == 1 and th == POINTER and ru == q, (door, m.replies))


# ---------------------------------------------------------------------------------------------- Z4
def test_z4_call_window_unchanged():
    t = topic()
    mdl = Thai()
    d1, m1, _, _ = execute(mdl, call_v("пробег ниже"), t=t)
    d2, m2, _, _ = execute(mdl, call_v("пробег ниже"), t=t)
    check("Z4 окно зова: второй зов в окне — ни сообщения, ни перевода",
          d1 == "зов Пыма" and len(m1.replies) == 1 and d2.startswith("зов (уже был в окне")
          and not m2.replies and len(mdl.calls) == 1, (d1, d2, m2.replies, len(mdl.calls)))
    check("Z4 окно зова прежнее (call_window модуля решателя)",
          topic_decider.call_allowed(None, 0, topic_decider.call_window()) is True, topic_decider.call_window())


# ---------------------------------------------------------------------------------------------- Z5
def test_z5_staff_ask_post_untouched():
    t = topic()
    S._TOPIC_NAMES[(CHAT, t)] = BIKE
    dec = {"действие": "спросить", "вопрос": "Масло меняли?", "ждём_что": "работы", "вид": "байк",
           "вопрос_th": "เปลี่ยนน้ำมันเครื่องแล้วหรือยังครับ"}
    v = topic_decider.rules(dec, {"open_kinds": {}})
    mdl = Thai()
    os.environ["SPLINTER_ASK_STAFF"] = "1"
    try:
        door, m, ctx, _ = execute(mdl, v, t=t)
    finally:
        os.environ.pop("SPLINTER_ASK_STAFF", None)
    check("Z5 вопрос сотрудникам через staff_ask_post: пост дверью, реплая нет, перевода нет",
          str(door).startswith("вопрос сотрудникам") and not m.replies and not mdl.calls and ctx.bot.sent,
          (door, m.replies, mdl.calls, ctx.bot.sent))


# ---------------------------------------------------------------------------------------------- Z6
def test_z6_model_reaches_door_and_thread():
    src = open(os.path.join(SRC, "splinter.py"), encoding="utf-8").read()
    fns = {n.name: n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.AsyncFunctionDef)}
    live = fns.get("decider_live")
    kw = [k.arg for c in ast.walk(live) if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_decider_execute"
          for k in c.keywords] if live else []
    check("Z6 решатель в бою передаёт модель двери (claude=…)", "claude" in kw, kw)
    mdl = Thai()
    execute(mdl, call_v("проверка потока"))
    check("Z6 перевод идёт в потоке, а не в цикле событий", mdl.threads and not any(mdl.threads), mdl.threads)


# ---------------------------------------------------------------------------------------------- Z7
def test_z7_translation_bounded_by_decider_timeout():
    why = "пробег 39500 ниже записанного 40000"
    mdl = Slow()
    door, dt, m, ctx, t, rows = run_logged(mdl, call_v(why), tmo=0.3)
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    print(f"  · Z7 замер: позвать — дверь вернулась через {'нет замера' if dt is None else '%.3f' % dt} с"
          f" (модель держит {Slow.HOLD:g} с, таймаут 0,3 с)")
    check("Z7 позвать, модель спит дольше таймаута: указатель за доли секунды (< 1 с при модели 2 с, таймаут 0,3 с)",
          dt is not None and dt < 1.0, dt)
    check("Z7 позвать: решатель идёт дальше — дверь «зов Пыма», одно сообщение, окно зова отмечено",
          door == "зов Пыма" and len(m.replies) == 1 and not ctx.bot.sent
          and (S._DLIVE["calls"].get(S._dkey(CHAT, t)) or {}).get("mid") is not None, (door, m.replies))
    check("Z7 позвать: оба блока, 🇹🇭 — тайский указатель, 🇷🇺 — прежний текст",
          th == POINTER and ru == f"🙋 {S.PYM_HANDLE}: {why}", (th, ru))
    check("Z7 позвать: строка журнала называет таймаут в секундах",
          any(re.search(r"не уложился в 0\.3 с", msg) for _, msg, _ in rows), rows)
    q = "Сколько км на одометре сейчас?"
    mdl = Slow()
    door, dt, m, ctx, t, rows = run_logged(mdl, ask_v(q), tmo=0.3)
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    asks = S._dlive_asks(CHAT, t)
    print(f"  · Z7 замер: спросить — дверь вернулась через {'нет замера' if dt is None else '%.3f' % dt} с")
    check("Z7 спросить, модель спит дольше таймаута: указатель за доли секунды, вопрос ушёл и открыт",
          dt is not None and dt < 1.0 and door == "вопрос реплаем" and len(m.replies) == 1
          and th == POINTER and ru == q and asks.get("пробег") is not None, (dt, door, m.replies, asks))
    check("Z7 спросить: строка журнала называет таймаут в секундах",
          any(re.search(r"не уложился в 0\.3 с", msg) for _, msg, _ in rows), rows)
    mdl = Thai()
    door, dt, m, _, _, rows = run_logged(mdl, call_v(why), tmo=0.3)
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z7 граница: быстрый перевод внутри таймаута — тайский перевод, не указатель, строки о таймауте нет",
          door == "зов Пыма" and th is not None and th != POINTER and THAI.search(th)
          and not any("не уложился" in msg for _, msg, _ in rows), (th, rows))


# ---------------------------------------------------------------------------------------------- Z8
def test_z8_fallback_without_model():
    why, q = "пробег 75500 выше потолка", "Какие работы сделаны сегодня?"
    door, dt, m, _, _, rows = run_logged(None, call_v(why))
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z8 модели нет, позвать: указатель, оба блока, прежний русский текст",
          door == "зов Пыма" and th == POINTER and ru == f"🙋 {S.PYM_HANDLE}: {why}", (door, m.replies))
    check("Z8 модели нет, позвать: без строки исключения в журнале", no_trace(rows), rows)
    door, dt, m, _, _, rows = run_logged(None, ask_v(q, "работы"))
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z8 модели нет, спросить: указатель и без строки исключения",
          door == "вопрос реплаем" and th == POINTER and ru == q and no_trace(rows), (door, m.replies, rows))
    mdl = Slow()
    door, dt, m, _, _, rows = run_logged(mdl, call_v(why), tmo=0.3)
    check("Z8 таймаут: запасной текст модель не зовёт (вызов один — тот, что не уложился), строки исключения нет",
          len(mdl.calls) == 1 and no_trace(rows), (len(mdl.calls), rows))
    real = S.bilingual_from_ru

    def broken(*a, **k):
        raise RuntimeError("сборка двуязычного текста упала")
    mdl = Thai()
    S.bilingual_from_ru = broken
    try:
        door, dt, m, _, _, rows = run_logged(mdl, call_v(why))
    finally:
        S.bilingual_from_ru = real
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z8 сборка упала: указатель, зов ушёл, модель не звана, строки исключения нет",
          door == "зов Пыма" and th == POINTER and ru == f"🙋 {S.PYM_HANDLE}: {why}" and not mdl.calls
          and no_trace(rows), (door, m.replies, mdl.calls, rows))
    text = f"🙋 {S.PYM_HANDLE}: замени машину на сервисе"
    door, dt, m, _, _, rows = run_logged(None, call_v("замени машину на сервисе"))
    expect = S.bilingual_from_ru(Empty(), text)
    check("Z8 форма запасного = форма bilingual_from_ru при сбое перевода (шапка, указатель, разделитель, _no_car)",
          bool(m.replies) and m.replies[0] == expect, (m.replies, expect))


# ---------------------------------------------------------------------------------------------- Z9
def test_z9_no_car_whole_word():
    nc = S._no_car
    s = "Залей машинное масло 10W-40"
    check("Z9 «машинное масло» цело", nc(s) == s, nc(s))
    s = "машинка для мойки на складе"
    check("Z9 «машинка» цела", nc(s) == s, nc(s))
    s = "машинист и автомобильный насос, автомобилист"
    check("Z9 производные слова целы (машинист, автомобильный, автомобилист)", nc(s) == s, nc(s))
    check("Z9 «машина» и «автомобиль» целым словом → «байк»",
          nc("машина") == "байк" and nc("автомобиль") == "байк" and nc("Машина клиента") == "байк клиента",
          (nc("машина"), nc("автомобиль"), nc("Машина клиента")))
    pairs = [("проверь машину", "проверь байк"), ("за машиной", "за байк"), ("две машины", "две байк"),
             ("нет машин", "нет байк"), ("у автомобиля", "у байк"), ("автомобили на парковке", "байк на парковке"),
             ("с автомобилем", "с байк")]
    check("Z9 падежи «машины» и «автомобиля» → «байк»", all(nc(a) == b for a, b in pairs),
          [(a, nc(a)) for a, _ in pairs])
    check("Z9 прочее как было: รถยนต์ → รถมอเตอร์ไซค์, пусто → пусто",
          nc("รถยนต์ คันนี้") == "รถมอเตอร์ไซค์ คันนี้" and nc(None) == "" and nc("") == "", nc("รถยนต์ คันนี้"))
    why = "замени машинное масло, машина клиента ждёт"
    mdl = Thai()
    door, m, _, _ = execute(mdl, call_v(why))
    head, th, ru = blocks(m.replies[0] if m.replies else "")
    check("Z9 через решатель: в 🇷🇺 «машинное масло» цело, «машина» → «байк»; перевод получил тот же текст",
          ru == f"🙋 {S.PYM_HANDLE}: замени машинное масло, байк клиента ждёт"
          and bool(mdl.calls) and mdl.calls[0]["user"] == ru, (ru, mdl.calls))


if __name__ == "__main__":
    print(f"splinter.py ← {SRC}")
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        try:
            fn()
        except Exception as e:
            check(f"{fn.__name__} упал: {type(e).__name__}", False, e)
    ok = sum(1 for _, r in RESULTS if r)
    print(f"ИТОГ {ok}/{len(RESULTS)}")
    sys.exit(0 if ok == len(RESULTS) else 1)
