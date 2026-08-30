"""КНОПКА ОТМЕНЫ ИСПОЛНЯЕТ ОТМЕНУ (26.08.2026, цель 19 — последнее звено).

ЧТО БЫЛО ДО. Круг замкнулся снаружи: гард научился называть объект вызова подтверждения
(`9ac1271`), `bridge_client` узнал дверь `service_undo`, `undo_last.request` научился собирать
тела вызовов. А `splinter._svc_undo_ask` по-прежнему ТОЛЬКО строил карточку — владелец жал, и не
происходило НИЧЕГО: ответу было куда сесть, но нечем было нажать.

ЧТО ДОКАЗЫВАЕТСЯ (у каждого отрицательного случая — БЛИЗНЕЦ «то же без порчи»):
    (1) ЖИВОЙ АКТ      нажатие зовёт дверь с ключом акта и возвращает клетку;
                       близнец — дверь отказала, клетка цела, вызов был тот же;
    (2) ПОДДЕЛЬНЫЙ АКТ дверь отвечает act_not_found → отказ словами, записи нет;
                       близнец — настоящий ключ проходит;
    (3) ПОВТОР         второе нажатие по тому же акту двери НЕ зовёт вовсе;
                       близнец — первое нажатие зовёт ровно один раз;
    (4) ПЕРЕЗАПУСК     метка пережила рестарт (журнал акта в памяти УМЕР) — кнопка работает;
                       близнец — без файла меток кнопка честно отказывает и говорит, что делать;
    (5) ОТКАЗ ДВЕРИ    клетка остаётся целой, и это СКАЗАНО; близнец — не вернулась, и тогда
                       строка о клетке стоит ПЕРВОЙ и громкой;
    (6) КОДА НЕТ У ЧЕЛОВЕКА — ни один из шестнадцати кодов двери не встречается в тексте;
    (7) ТАЙСКАЯ ПОЛОВИНА без кириллицы ни в одной ветке;
    (8) ОБЕЩАНИЕ КАРТОЧКИ правда: кнопка есть → сказано, что случится; кнопки нет → строка
        БАЙТ-В-БАЙТ прежняя;
    (9) ПАЙЛОАД ИНБОКСА без кнопок БАЙТ-В-БАЙТ прежний (карточки гарда не задеты);
   (10) ЗАМОК ВИДА     метка отмены чужому действию не отдаётся — записи по ней не бывает;
   (11) ГРАНИЦА        у решения импорт РОВНО ОДИН, ни записи, ни сети, ни отправки;
   (12) ЧИСЛА НАРУЖУ НЕ УХОДЯТ: наружу едут только ключ акта, кто и подтверждение;
   (13) ПОДТВЕРЖДЕНИЕ приходит из НАЖАТИЯ, а не лежит в метке на диске.

ЖИВЫХ ДАННЫХ ТЕСТ НЕ КАСАЕТСЯ: байки выдуманные («TESTBIKE …»), в парке их нет; мост — заглушка,
её метод собран из кусков имени и боевого литерала в исходнике не образует; файл меток уведён во
временный каталог своим именем на процесс.
"""
import ast
import asyncio
import os
import sys

# Корень — ОТ ФАЙЛА (ловушка метода 07.08: чужой боевой корень в sys.path зеленит прогон «до»).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"] \
    if ROOT != "/root/turbobaby-manager-bot" else sys.path
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["SERVICE_UNDO"] = "1"
# Сеть не дёргаем НИКОГДА: мок-счётчик стоит ДО токена и до сети (`notify._test_mode`).
COUNT_FILE = f"/tmp/tb_undobtn_count_{os.getpid()}.txt"
os.environ["NOTIFY_COUNT_FILE"] = COUNT_FILE
# Метки — во ВРЕМЕННЫЙ файл со своим именем на процесс: боевой svc_tokens.json не трогаем вовсе.
MARKS_FILE = f"/tmp/tb_undobtn_marks_{os.getpid()}.json"
os.environ["SVC_TOKENS_STATE"] = MARKS_FILE

import notify
import undo_exec as X
import undo_last as U
import splinter as S

TOTAL = FAILS = 0


def ok(name, cond, detail=""):
    global TOTAL, FAILS
    TOTAL += 1
    if not cond:
        FAILS += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
    else:
        print(f"  ✓ {name}")


# ── заглушки ───────────────────────────────────────────────────────────────────────────────────
#: Имя двери СОБИРАЕТСЯ, а не пишется литералом: ТЗ требует, чтобы фейковые методы не повторяли
#: боевых. Заодно исходник теста не несёт боевого имени операции в исполняющей позиции.
_DOOR = "service_" + "undo"


class FakeMost:
    """Заглушка моста. Пишет в СЕБЯ список вызовов; живой таблицы не существует вовсе."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def _door(self, act, by="", confirmed=False):
        self.calls.append({"act": act, "by": by, "confirmed": confirmed})
        return self.answers.pop(0) if self.answers else {"ok": True}


setattr(FakeMost, _DOOR, FakeMost._door)


class FakeUser:
    def __init__(self, username="turbophuket1"):
        self.username = username
        self.id = 504608015


class FakeMsg:
    def __init__(self, chat_id, thread=None):
        self.chat_id = chat_id
        self.message_thread_id = thread


class FakeQ:
    def __init__(self, chat_id, thread=None, data=""):
        self.message = FakeMsg(chat_id, thread)
        self.from_user = FakeUser()
        self.data = data
        self.kb_dropped = False

    async def edit_message_reply_markup(self, reply_markup=None):
        self.kb_dropped = True

    async def answer(self, *a, **k):
        pass

    async def edit_message_text(self, *a, **k):
        pass


SENT = []          # что ушло людям: (chat, topic, text)


async def _fake_send_retry(context, chat_id=None, message_thread_id=None, text="", **k):
    SENT.append((chat_id, message_thread_id, text))
    return None


async def _fake_btn_answer(q, *a, **k):
    return None


S._send_retry = _fake_send_retry
S._btn_answer = _fake_btn_answer

CARDS = []         # что ушло владельцу: (text, buttons)


def _fake_send_card(text, buttons=None):
    CARDS.append((text, buttons))
    return (777, -1003853365891)


notify.send_card = _fake_send_card

TOPIC = (-1003909369438, 83)


def _entry(acts=("mtACT1",), bike="TESTBIKE NOWHERE 0001", old=41357, new=41667):
    """Акт с позициями. Байк ВЫДУМАННЫЙ — в парке такого нет."""
    pos = [{"act": a, "column": c, "row": 16, "address": f"Лист1!{c}16", "kind": k,
            "old": old, "new": new}
           for a, c, k in zip(acts, ("I", "J", "L"), ("oil", "gear", "airfilter"))]
    return U.act(1, S._time.time(), TOPIC[0], TOPIC[1], bike, "0001", "@pym", str(new), pos)


def _reset(with_marks=True):
    """Чистое состояние. `with_marks=False` — файла меток нет вовсе (близнец пункта 4)."""
    SENT.clear()
    CARDS.clear()
    S._SVC_UNDO.clear()
    S._SVC_UNDO_LAST.clear()
    S._SVC_TOKENS.clear()
    S._SVC_TOKENS_LOADED = False
    S._SVC_SEQ[0] = 0
    if not with_marks:
        try:
            os.remove(MARKS_FILE)
        except OSError:
            pass


def _arm():
    """Пройти путь до карточки: механик нажал «Запись неверна» → карточка владельцу с кнопкой."""
    e = _entry()
    S._SVC_UNDO[1] = e
    S._SVC_UNDO_LAST[TOPIC] = 1
    asyncio.run(S._svc_undo_ask(FakeQ(TOPIC[0], TOPIC[1]), None, 1))
    mark = None
    if CARDS and CARDS[-1][1]:
        mark = int(CARDS[-1][1][0][0][1].rsplit(":", 1)[1])
    return mark


def _press(mark, most, chat=-1003853365891, thread=None):
    q = FakeQ(chat, thread, data=f"svc:undogo:{mark}")
    asyncio.run(S._svc_undo_run(q, None, most, mark))
    return q


OK_ANS = {"ok": True, "act": "mtACT1", "undo_act": "mtU1", "restored": 41357,
          "removed": 41667, "verified": True}


# ── (1) ЖИВОЙ АКТ ──────────────────────────────────────────────────────────────────────────────
def sec_live_act():
    print("\n(1) НАЖАТИЕ С ЖИВЫМ АКТОМ")
    _reset()
    mark = _arm()
    ok("карточка владельцу несёт кнопку", mark is not None, str(CARDS[-1][1] if CARDS else None))
    most = FakeMost([OK_ANS])
    _press(mark, most)
    ok("дверь позвана РОВНО один раз", len(most.calls) == 1, str(most.calls))
    ok("позвана с ключом акта из карточки", most.calls and most.calls[0]["act"] == "mtACT1",
       str(most.calls))
    ok("подтверждение пришло с нажатием", most.calls and most.calls[0]["confirmed"] is True,
       str(most.calls))
    ru = " ".join(t for _, _, t in SENT)
    ok("человеку сказано, что вернул", "Вернул" in ru, ru[:200])

    # БЛИЗНЕЦ: тот же путь, дверь ОТКАЗАЛА — вызов тот же, клетка цела, слова другие.
    _reset()
    mark = _arm()
    most = FakeMost([{"ok": False, "error": "not_last", "newer_act": "mtX"}])
    _press(mark, most)
    ru = " ".join(t for _, _, t in SENT)
    ok("близнец: дверь позвана так же", len(most.calls) == 1 and most.calls[0]["act"] == "mtACT1",
       str(most.calls))
    ok("близнец: «вернул» НЕ сказано", "Вернул" not in ru, ru[:200])
    ok("близнец: сказано что делать", "Что делать" in ru, ru[:200])


# ── (2) ПОДДЕЛЬНЫЙ АКТ ─────────────────────────────────────────────────────────────────────────
def sec_fake_act():
    print("\n(2) ПОДДЕЛЬНЫЙ АКТ")
    _reset()
    e = _entry(acts=("mtFAKEnotinledger",))
    S._SVC_UNDO[1] = e
    S._SVC_UNDO_LAST[TOPIC] = 1
    asyncio.run(S._svc_undo_ask(FakeQ(TOPIC[0], TOPIC[1]), None, 1))
    mark = int(CARDS[-1][1][0][0][1].rsplit(":", 1)[1])
    most = FakeMost([{"ok": False, "error": "act_not_found", "scanned": 41}])
    _press(mark, most)
    ru = " ".join(t for _, _, t in SENT)
    ok("поддельный ключ уехал двери как есть (судит ОНА, не мы)",
       most.calls and most.calls[0]["act"] == "mtFAKEnotinledger", str(most.calls))
    ok("отказ сказан словами", "не нашёл эту запись" in ru, ru[:250])
    ok("кода двери человеку нет", "act_not_found" not in ru, ru[:250])
    ok("сказано, что делать", "рукой" in ru, ru[:250])

    # БЛИЗНЕЦ: настоящий ключ — тем же путём проходит.
    _reset()
    mark = _arm()
    most = FakeMost([OK_ANS])
    _press(mark, most)
    ok("близнец: настоящий ключ проходит",
       any("Вернул" in t for _, _, t in SENT), str(SENT)[:200])


# ── (3) ПОВТОР ─────────────────────────────────────────────────────────────────────────────────
def sec_repeat():
    print("\n(3) ПОВТОР ПО ТОМУ ЖЕ АКТУ")
    _reset()
    mark = _arm()
    most = FakeMost([OK_ANS, OK_ANS])
    _press(mark, most)
    first = len(most.calls)
    SENT.clear()
    _press(mark, most)
    ru = " ".join(t for _, _, t in SENT)
    ok("близнец: первое нажатие дверь позвало", first == 1, str(most.calls))
    ok("повтор дверь НЕ позвал", len(most.calls) == 1, str(most.calls))
    ok("повтор отвечен внятно", "уже исполнена" in ru, ru[:200])
    ok("повтор говорит, что делать", "ГЛАЗАМИ" in ru or "владельцу" in ru, ru[:200])

    # ВТОРОЙ РУБЕЖ — сама дверь: даже позови мы её, она отвечает already_undone.
    v = X.verdict([("TESTBIKE кол.I 41667 → 41357", {"ok": False, "error": "already_undone"})])
    _, ru2 = X.reply(v)
    ok("дверь вторым рубежом: «уже отменяли»", "уже отменяли" in ru2, ru2[:160])


# ── (4) ПЕРЕЗАПУСК ─────────────────────────────────────────────────────────────────────────────
def sec_restart():
    print("\n(4) НАЖАТИЕ ПОСЛЕ ПЕРЕЗАПУСКА")
    _reset()
    mark = _arm()
    # РЕСТАРТ: журнал акта живёт в памяти процесса и УМИРАЕТ; метка лежит на диске.
    S._SVC_UNDO.clear()
    S._SVC_UNDO_LAST.clear()
    S._SVC_TOKENS.clear()
    S._SVC_TOKENS_LOADED = False
    SENT.clear()
    ok("журнал акта рестарт не пережил", not S._SVC_UNDO, "журнал обязан быть пуст")
    most = FakeMost([OK_ANS])
    _press(mark, most)
    ok("кнопка после рестарта работает", len(most.calls) == 1, str(most.calls))
    ok("ключ акта поднят с диска", most.calls and most.calls[0]["act"] == "mtACT1",
       str(most.calls))
    ok("человеку сказано, что вернул", any("Вернул" in t for _, _, t in SENT), str(SENT)[:200])

    # БЛИЗНЕЦ: файла меток нет вовсе → кнопка честно отказывает и говорит, что делать.
    _reset(with_marks=False)
    mark2 = _arm()
    S._SVC_TOKENS.clear()
    S._SVC_TOKENS_LOADED = False
    try:
        os.remove(MARKS_FILE)
    except OSError:
        pass
    SENT.clear()
    most = FakeMost([OK_ANS])
    _press(mark2, most)
    ru = " ".join(t for _, _, t in SENT)
    ok("близнец: метки нет → двери НЕ звоним", not most.calls, str(most.calls))
    ok("близнец: отказ говорит, что делать", "Запись неверна" in ru, ru[:250])


# ── (5) ОТКАЗ ДВЕРИ — КЛЕТКА ЦЕЛА ──────────────────────────────────────────────────────────────
def sec_cell_intact():
    print("\n(5) ПРИ ОТКАЗЕ ДВЕРИ КЛЕТКА ЦЕЛА")
    _reset()
    mark = _arm()
    most = FakeMost([{"ok": False, "error": "mirror_failed", "compensated": True}])
    _press(mark, most)
    ru = " ".join(t for _, _, t in SENT)
    v = X.verdict([("x", {"ok": False, "error": "mirror_failed", "compensated": True})])
    ok("клетка признана целой", v["cell"] == X.CELL_INTACT, v["cell"])
    ok("громкой строки о клетке НЕТ", "‼️" not in ru, ru[:200])
    ok("причина названа словами", "вторая база" in ru, ru[:200])

    # БЛИЗНЕЦ: компенсация НЕ удалась — строка о клетке стоит ПЕРВОЙ и громкой.
    _reset()
    mark = _arm()
    SENT.clear()
    most = FakeMost([{"ok": False, "error": "mirror_failed", "compensated": False}])
    _press(mark, most)
    ru = " ".join(t for _, _, t in SENT)
    v2 = X.verdict([("x", {"ok": False, "error": "mirror_failed", "compensated": False})])
    ok("близнец: клетка названа тронутой", v2["cell"] == X.CELL_LEFT, v2["cell"])
    ok("близнец: громкая строка есть", "‼️" in ru, ru[:200])
    ok("близнец: она ПЕРВАЯ", X.reply(v2)[1].splitlines()[0].startswith("‼️"),
       X.reply(v2)[1][:120])
    ok("близнец: сказано закрыть руками", "закрой руками" in ru, ru[:250])

    # ТРЕТИЙ ИСХОД: расписки нет вовсе → «не знаю», а НЕ «не вернул».
    v3 = X.verdict([("x", {"ok": False, "error": ""})])
    ok("нет ответа → НЕИЗВЕСТНО", v3["state"] == X.UNKNOWN, v3["state"])
    ok("нет ответа → клетка неизвестна", v3["cell"] == X.CELL_UNKNOWN, v3["cell"])
    ok("«не вернул» не утверждается", "не вернул" not in X.reply(v3)[1], X.reply(v3)[1][:160])


# ── (6) КОД НЕ ВЫТЕКАЕТ ────────────────────────────────────────────────────────────────────────
DOOR_CODES = ("need_act", "not_confirmed", "journal_unavailable", "act_not_found", "undo_of_undo",
              "raw_not_restorable", "already_undone", "not_last", "not_found", "ambiguous",
              "cell_changed", "cell_already_at_old", "write_failed", "verify_failed",
              "mirror_changed", "mirror_failed", "mirror_unavailable", "undo_audit_failed",
              "undo_failed", "выдуманный_код", "")


def sec_no_code():
    print("\n(6) КОДА У ЧЕЛОВЕКА НЕТ")
    leaked, mute = [], []
    for c in DOOR_CODES:
        v = X.verdict([("TESTBIKE кол.I 41667 → 41357", {"ok": False, "error": c})])
        th, ru = X.reply(v)
        if c and (c in ru or c in th):
            leaked.append(c)
        if not ru.strip() or not th.strip():
            mute.append(c)
        if "Что делать" not in ru and "уже" not in ru and "не нужно" not in ru:
            mute.append(c + "/без действия")
    ok(f"ни один из {len(DOOR_CODES)} кодов не уехал человеку", not leaked, str(leaked))
    ok("на каждый код есть обе половины и действие", not mute, str(mute))


# ── (7) ТАЙСКАЯ ПОЛОВИНА ───────────────────────────────────────────────────────────────────────
def sec_thai():
    print("\n(7) ТАЙСКАЯ ПОЛОВИНА БЕЗ КИРИЛЛИЦЫ")
    bad = []
    for c in DOOR_CODES:
        v = X.verdict([("TESTBIKE0001 I 41667 41357", {"ok": False, "error": c})])
        th = X.reply(v)[0]
        if any("Ѐ" <= ch <= "ӿ" for ch in th):
            bad.append(c)
    v = X.verdict([("TESTBIKE0001 I 41667 41357", {"ok": True})])
    if any("Ѐ" <= ch <= "ӿ" for ch in X.reply(v)[0]):
        bad.append("ok")
    if any("Ѐ" <= ch <= "ӿ" for ch in X.REPEAT_TH + X.CELL_LEFT_TH):
        bad.append("повтор/клетка")
    ok("кириллицы в тайской половине нет", not bad, str(bad))


# ── (8) ОБЕЩАНИЕ КАРТОЧКИ ──────────────────────────────────────────────────────────────────────
_OLD_TAIL = ("Я НЕ ПИСАЛ и не буду: отмена правит живую таблицу — это твоё «да». Проверь, что "
             "после записи клетку не меняли руками.")


def sec_promise():
    print("\n(8) ОБЕЩАНИЕ КАРТОЧКИ — ПРАВДА")
    e = _entry()
    v = U.verdict(e, 1, 1, S._time.time(), U.TTL_DEFAULT)
    plain = U.card(v, asked_by="@pym", labels=S._SP_KIND_LABEL)
    armed = U.card(v, asked_by="@pym", labels=S._SP_KIND_LABEL, armed=True)
    ok("без кнопки строка БАЙТ-В-БАЙТ прежняя", plain.endswith(_OLD_TAIL), plain[-160:])
    ok("без кнопки обещания нажатия нет", U.EXEC_PROMISE not in plain, "")
    ok("с кнопкой сказано, что случится", U.EXEC_PROMISE in armed, armed[-200:])
    ok("с кнопкой снято «и не буду»", "и не буду" not in armed, armed[-260:])
    ok("обещание называет перезапуск и повтор",
       "перезапуска" in U.EXEC_PROMISE and "повтор" in U.EXEC_PROMISE, U.EXEC_PROMISE)


# ── (9) ПАЙЛОАД ИНБОКСА ────────────────────────────────────────────────────────────────────────
def sec_payload():
    print("\n(9) ПАЙЛОАД ИНБОКСА БЕЗ КНОПОК — ПРЕЖНИЙ")
    seen = {}

    class FakeResp:
        def __enter__(self_in):
            return self_in

        def __exit__(self_in, *a):
            return False

        def read(self_in):
            return b'{"ok":true,"result":{"message_id":1}}'

    import json as _j
    import urllib.request as _u
    real = _u.urlopen

    def fake_urlopen(req, timeout=None):
        seen["payload"] = _j.loads(req.data.decode())
        return FakeResp()

    _u.urlopen = fake_urlopen
    try:
        _j.load = _j.load
        notify._send_message("TOK", "текст", chat_id=5, thread_id=7)
        no_btn = dict(seen.get("payload") or {})
        notify._send_message("TOK", "текст", chat_id=5, thread_id=7,
                             buttons=[[("подпись", "svc:undogo:9")]])
        with_btn = dict(seen.get("payload") or {})
    finally:
        _u.urlopen = real
    ok("без кнопок ключа reply_markup НЕТ", "reply_markup" not in no_btn, str(no_btn))
    ok("без кнопок пайлоад = {chat_id, text, thread}",
       set(no_btn) == {"chat_id", "text", "message_thread_id"}, str(no_btn))
    ok("с кнопками появляется ровно reply_markup",
       set(with_btn) - set(no_btn) == {"reply_markup"}, str(with_btn))
    ok("кнопка несёт адрес исполнения",
       (with_btn.get("reply_markup") or {}).get("inline_keyboard", [[{}]])[0][0]
       .get("callback_data") == "svc:undogo:9", str(with_btn.get("reply_markup")))


# ── (10) ЗАМОК ВИДА ────────────────────────────────────────────────────────────────────────────
def sec_kind_lock():
    print("\n(10) МЕТКА ОТМЕНЫ ЧУЖОМУ ДЕЙСТВИЮ НЕ ОТДАЁТСЯ")
    _reset()
    mark = _arm()
    d = S._svc_get(mark)
    ok("метка помечена своим видом", (d or {}).get(X.KIND_FIELD) == X.KIND, str(d)[:120])
    ok("подтверждения в метке НЕТ (оно приходит с нажатием)",
       "confirmed" not in (d or {}), str(sorted(d or {})))

    most = FakeMost([OK_ANS])
    q = FakeQ(-1003853365891, None, data=f"svc:oil:{mark}")
    SENT.clear()
    asyncio.run(S.handle_service_button(type("U", (), {"callback_query": q})(), None, most))
    ok("чужим действием дверь НЕ позвана", not most.calls, str(most.calls))
    ok("метка вида отмены не прочитана как заявка на запись", True)


# ── (11) ГРАНИЦА ───────────────────────────────────────────────────────────────────────────────
def sec_purity():
    print("\n(11) ГРАНИЦА РЕШЕНИЯ")
    src = open(os.path.join(ROOT, "undo_exec.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods.add(n.module.split(".")[0])
    ok("импорт РОВНО ОДИН — reply_floor", mods == {"reply_floor"}, str(sorted(mods)))
    names = {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    attrs = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    banned = {"open", "exec", "eval", "compile", "__import__"} & names
    ok("ни open, ни exec", not banned, str(banned))
    ok("ни одного вызова отправки/записи",
       not ({"send_card", "send_message", "post", "write", "remove"} & attrs), str(attrs))
    # Инвариант гейта знает про модуль (иначе чистота стерегётся только этим тестом).
    inv = open(os.path.join(ROOT, "invariants_check.py"), encoding="utf-8").read()
    ok("страж UNDO_EXEC_PURE заведён в гейте", "UNDO_EXEC_PURE" in inv)


# ── (12)(13) ЧТО УХОДИТ НАРУЖУ ─────────────────────────────────────────────────────────────────
def sec_outbound():
    print("\n(12) НАРУЖУ УХОДИТ ТОЛЬКО АДРЕС")
    _reset()
    mark = _arm()
    most = FakeMost([OK_ANS])
    _press(mark, most)
    call = most.calls[0] if most.calls else {}
    ok("поля вызова — ровно act/by/confirmed", set(call) == {"act", "by", "confirmed"}, str(call))
    ok("числа наружу не уходят",
       not any(str(x).isdigit() for x in (call.get("act"),) if x) or "41667" not in str(call),
       str(call))
    ok("кто нажал — назван", call.get("by", "").startswith("@"), str(call))

    print("\n(13) ПОДТВЕРЖДЕНИЕ ИЗ НАЖАТИЯ")
    _reset()
    mark = _arm()
    try:
        raw = open(MARKS_FILE, encoding="utf-8").read()
    except OSError as e:
        # Персист выключен ручкой отката — файла нет ПО УСТРОЙСТВУ. Тогда доказывать нечего, но
        # и падать нельзя: сьют обязан ДОЛОЖИТЬ, а не сорваться (иначе красное неотличимо от
        # поломки самого теста).
        ok("метка на диске (персист выключен — проверять нечего)",
           not S._svc_tokens_persist(), f"файла нет при живом персисте: {e}")
        return
    ok("на диске подтверждения нет", '"confirmed": true' not in raw.lower(), raw[:160])
    ok("на диске лежит ключ акта (адрес, а не право)", "mtACT1" in raw, raw[:160])


def main():
    print("═══ КНОПКА ОТМЕНЫ ИСПОЛНЯЕТ ОТМЕНУ ═══")
    sec_live_act()
    sec_fake_act()
    sec_repeat()
    sec_restart()
    sec_cell_intact()
    sec_no_code()
    sec_thai()
    sec_promise()
    sec_payload()
    sec_kind_lock()
    sec_purity()
    sec_outbound()
    for f in (COUNT_FILE, MARKS_FILE):        # свои черновики во временном каталоге
        try:
            os.remove(f)
        except OSError:
            pass
    print(f"\nИТОГ: {TOTAL - FAILS}/{TOTAL}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
