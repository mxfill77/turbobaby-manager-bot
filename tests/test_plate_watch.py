"""НОМЕР НА БАЙКЕ ↔ ИМЯ ТЕМЫ ↔ ЗЕЛЁНАЯ КНИГА (25.10.2026, PLATEWATCH2510).

Правило владельца 25.10: имя темы обслуживания идёт за номером, ФИЗИЧЕСКИ стоящим на байке;
расхождение с зелёной книгой — предупреждение. Повод — переход 24.10 на номера из зелёных книг,
а снимки показывают старые таблички: 83 — 2478 при книге 9286, 1190 — 9315 при 8676.

Предмет — четыре вещи:
  1  РЕШЕНИЕ `plate_watch` (чистое, импортов ноль): какое чтение годится, номер темы, предложение
     имени, два чтения из РАЗНЫХ отправок за 14 суток, альбом = одна отправка, расхождение поровну,
     висящая карточка, «Оставить», предупреждение раз в 7 суток;
  2  ПРОМПТ снимка: поле `plate` — только табличка на САМОМ байке, `legible`, не угадывать;
  3  ЖИВОЙ `splinter.handle` + кнопки `svc:plren` / `svc:plkeep`: 83 — карточка с предупреждением,
     82 — ничего, 1190 — карточка с предупреждением, одно чтение и байк на фоне — ничего, в тему
     байка от этой ветки не уходит НИ ОДНОГО сообщения, карточка переживает перезапуск, нажимает
     только владелец (Пым — доверенный, но не владелец — получает отказ), «Переименовать» зовёт
     `edit_forum_topic` и правит кэш и memory.db как событие переименования, PLATE_WATCH=0 — тишина;
  4  ДРЕЙФ ИМЕНИ ТЕМЫ: обычное сообщение (reply на сообщение создания) больше не возвращает теме
     ПЕРВОЕ имя — живой случай 82, 21.10 09:23:30 UTC «5104» → «3902» через 0.8 с после фото.

Сеть, Telegram, мост, модель и memory.db — заглушки; зелёная книга — настоящий
`greenbook_plates.json` из корня дерева. Память — во временном каталоге.
"""
import ast
import asyncio
import json
import os
import sys
import tempfile
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # дерево, которое судим
sys.path.insert(0, ROOT)
os.environ["ACT_GATE"] = "0"            # предмет сьюта — номер темы; ворота судит tests/test_act_gate.py
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLATE_WATCH"] = "1"
_TMP = tempfile.mkdtemp(prefix="tb_plate_watch_")
os.environ["PLATE_WATCH_STATE"] = os.path.join(_TMP, "plate.json")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import notify                # noqa: E402
import plate_watch as PW     # noqa: E402
import splinter as S         # noqa: E402

DAY = 86400.0
NOW = 1792915200.0           # 25.10.2026 00:00 UTC
SERV = S.SERVICING_CHAT
OWNER = ("turbophuket1", 6879003264)          # бизнес-аккаунт владельца (OWNER_IDS)
PYM = ("pleummmm", 99001)                     # доверенный, но НЕ владелец
with open(os.path.join(ROOT, "greenbook_plates.json"), encoding="utf-8") as _f:
    BOOK = json.load(_f)


def _book(topic):
    return PW.book_entry(BOOK, topic)


def _plate(d, legible=True, series=None):
    return {"kind": "bike", "dirt": False, "damage": None, "fuel": None, "mileage": None, "notes": "байк",
            "plate": {"digits": d, "series": series, "province": "Phuket", "legible": legible}}


def _st(topic, *reads):
    """Память с чтениями: reads = (цифры, mid[, отправка[, возраст в сутках]])."""
    st = PW.clean(None)
    for r in reads:
        d, mid = r[0], r[1]
        grp = r[2] if len(r) > 2 else None
        age = r[3] if len(r) > 3 else 0.0
        st = PW.add_reading(st, topic, {"d": d}, mid, grp, NOW - age * DAY)
    return st


# ============================================================================================
#  (1) РЕШЕНИЕ — чистое
# ============================================================================================
def test_module_is_pure():
    src = open(os.path.join(ROOT, "plate_watch.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], [ast.dump(n) for n in imports]
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not used & {"open", "eval", "exec", "__import__", "input"}, used


def test_reading_only_legible_digits():
    assert PW.reading(_plate("2478", series="2กจ")) == {"d": "2478", "series": "2กจ", "province": "Phuket"}
    assert PW.reading(_plate("2478", legible=False)) is None          # байк на фоне / смазано
    assert PW.reading(_plate("2478", legible="true")) is None         # только булево «да»
    assert PW.reading(_plate("24 78"))["d"] == "2478"
    assert PW.reading(_plate("๒๔๗๘"))["d"] == "2478"                  # тайские цифры
    assert PW.reading(_plate(461))["d"] == "461"
    # две цифры — не номер для моста: строку Лист1 он ищет по числу от трёх цифр (plateFromName_)
    for bad in ("24781", "47", "0047", "", "2กจ", None, "24?8", True):
        assert PW.reading(_plate(bad)) is None, bad
    for bad in (None, {}, {"plate": None}, {"plate": "2478"}, "мусор"):
        assert PW.reading(bad) is None, bad


def test_topic_plate_is_the_last_word():
    assert PW.topic_plate("XADV 750CC GREY 9286") == "9286"
    assert PW.topic_plate("CB 300CC R 461") == "461"
    assert PW.topic_plate("XADV 750 BLACK") is None                    # «750» — объём, не номер
    assert PW.topic_plate("5104") is None and PW.topic_plate(None) is None
    assert PW.topic_plate("NMAX 155CC 12") is None                      # две цифры мост не узнает
    # номер темы совпадает с тем, что мост берёт из имени (зеркало plateFromName_) — на всём парке книги
    for b in BOOK["bikes"]:
        assert PW.topic_plate(b["name"]) == S._plate_from_name(b["name"]) == b["plate_digits"], b["name"]
    assert PW.propose("XADV 750CC GREY 9286", "2478") == "XADV 750CC GREY 2478"
    assert PW.propose("XADV 750 BLACK", "2478") is None


def test_greenbook_file_names_live_topics():
    assert _book(83)["d"] == "9286" and _book(83)["series"] == "2กจ"
    assert _book(1190)["d"] == "8676" and _book(82)["d"] == "5104"
    assert _book(62)["d"] == "5662" and _book(66)["d"] == "461"
    assert _book(999999) is None and PW.book_entry(None, 83) is None


def test_live_83_two_readings_rename_with_warning():
    st = _st(83, ("2478", 4411), ("2478", 4520))
    v = PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)
    assert v["kind"] == PW.KIND_RENAME and v["why"] == PW.RENAME, v
    assert v["d"] == "2478" and v["g"] == "9286" and v["mids"] == [4411, 4520], v
    assert v["proposed"] == "XADV 750CC GREY 2478"
    text = PW.card_text(v, SERV)
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (9286)" in text, text
    assert "«XADV 750CC GREY 2478»" in text and "4411" in text and "4520" in text
    assert "https://t.me/c/2751134848/83/4411" in text


def test_live_82_same_everywhere_nothing():
    st = _st(82, ("5104", 900), ("5104", 901))
    v = PW.verdict(st, 82, "XADV 750CC BLACK 5104", _book(82), NOW)
    assert v["kind"] is None and v["why"] == PW.SAME, v


def test_live_1190_rename_with_warning():
    st = _st(1190, ("9315", 70), ("9315", 75))
    v = PW.verdict(st, 1190, "XMAX 300CC NEW BROWN 8676", _book(1190), NOW)
    assert v["kind"] == PW.KIND_RENAME and v["proposed"] == "XMAX 300CC NEW BROWN 9315", v
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (8676)" in PW.card_text(v, SERV)


def test_bike_equals_book_says_so():
    # тема 62 зовётся старым номером 5849, а на байке уже новый 5662 = книга
    st = _st(62, ("5662", 10), ("5662", 11))
    v = PW.verdict(st, 62, "ADV 350CC BLACK 5849", _book(62), NOW)
    text = PW.card_text(v, SERV)
    assert v["kind"] == PW.KIND_RENAME and "✅ Номер на байке совпадает с зелёной книгой (5662)" in text, text
    assert "не совпадает с зелёной книгой" not in text


def test_single_reading_album_and_old_readings_are_few():
    assert PW.verdict(_st(83, ("2478", 1)), 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.FEW
    album = _st(83, ("2478", 1, "alb"), ("2478", 2, "alb"), ("2478", 3, "alb"))
    assert PW.verdict(album, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.FEW
    old = _st(83, ("2478", 1, None, 15), ("2478", 2))
    assert PW.verdict(old, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.FEW
    same_msg = PW.add_reading(_st(83, ("2478", 7)), 83, {"d": "2478"}, 7, None, NOW)   # повтор по «да»
    assert PW.verdict(same_msg, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.FEW


def test_split_readings_are_not_guessed():
    st = _st(83, ("2478", 1), ("2478", 2), ("2473", 3), ("2473", 4))
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.SPLIT
    st = PW.add_reading(st, 83, {"d": "2478"}, 5, None, NOW)            # перевес — уже не догадка
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)["d"] == "2478"


def test_no_plate_in_topic_name_nothing():
    st = _st(83, ("2478", 1), ("2478", 2))
    assert PW.verdict(st, 83, "XADV 750 GREY", _book(83), NOW)["why"] == PW.NO_TOPIC_PLATE


def test_pending_card_and_ttl():
    st = _st(83, ("2478", 1), ("2478", 2))
    v = PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW, chat_id=SERV)
    assert PW.find_card(st, n)[1]["proposed"] == "XADV 750CC GREY 2478"
    st = PW.add_reading(st, 83, {"d": "2478"}, 3, None, NOW + 60)
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW + 60)["why"] == PW.PENDING
    later = NOW + PW.CARD_TTL_S + 60
    st = PW.add_reading(PW.add_reading(st, 83, {"d": "2478"}, 8, None, later), 83, {"d": "2478"}, 9, None, later)
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), later)["kind"] == PW.KIND_RENAME


def test_declined_holds_until_name_or_digits_change():
    st = _st(83, ("2478", 1), ("2478", 2))
    v = PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)
    st, n = PW.next_seq(st)
    st = PW.with_card(st, v, n, NOW)
    st = PW.with_declined(st, PW.find_card(st, n)[1], NOW)
    assert PW.find_card(st, n) == (None, None)
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.DECLINED
    assert PW.verdict(st, 83, "XADV 750CC GREY2 9286", _book(83), NOW)["kind"] == PW.KIND_RENAME


def test_warn_only_once_per_seven_days():
    # после переименования 83 зовётся по табличке 2478 — книга по-прежнему 9286
    st = _st(83, ("2478", 1), ("2478", 2))
    v = PW.verdict(st, 83, "XADV 750CC GREY 2478", _book(83), NOW)
    assert v["kind"] == PW.KIND_WARN and v["why"] == PW.WARN, v
    text = PW.card_text(v, SERV)
    assert text.startswith("⚠️ Номер на байке не совпадает с зелёной книгой (9286)"), text
    assert "Предлагаю" not in text
    st = PW.with_warned(st, 83, NOW)
    assert PW.verdict(st, 83, "XADV 750CC GREY 2478", _book(83), NOW + 6 * DAY)["why"] == PW.WARN_RECENT
    st = PW.add_reading(PW.add_reading(st, 83, {"d": "2478"}, 5, None, NOW + 8 * DAY), 83, {"d": "2478"}, 6,
                        None, NOW + 8 * DAY)
    assert PW.verdict(st, 83, "XADV 750CC GREY 2478", _book(83), NOW + 8 * DAY)["kind"] == PW.KIND_WARN


def test_off_and_broken_memory():
    st = _st(83, ("2478", 1), ("2478", 2))
    assert PW.verdict(st, 83, "XADV 750CC GREY 9286", _book(83), NOW, on=False)["why"] == PW.OFF
    for bad in (None, "мусор", {"readings": "x", "cards": [1]}, {"readings": {"83": [None, {"d": "abc"}]}}):
        assert PW.verdict(bad, 83, "XADV 750CC GREY 9286", _book(83), NOW)["why"] == PW.FEW, bad


# ============================================================================================
#  (2) ПРОМПТ снимка
# ============================================================================================
def test_prompt_asks_plate_of_the_photographed_bike_only():
    p = S.VISION_BIKE_SYSTEM
    assert "plate:" in p and "legible" in p and "digits" in p, p
    assert "на фоне" in p and "НЕ угадывай" in p
    assert "plate:" in S.VISION_BIKE_SYSTEM_POS
    # промпт положения байка по-прежнему дописывает «разобран» сразу перед notes
    extra = S.VISION_BIKE_SYSTEM_POS.replace(S.VISION_BIKE_SYSTEM.split("  notes:")[0], "", 1)
    assert extra.startswith("  disassembled:"), extra[:80]


# ============================================================================================
#  Заглушки мира для живого `splinter.handle` и кнопок
# ============================================================================================
class _Bot:
    username = "tb_plate_test_bot"

    def __init__(self):
        self.sent, self.renamed = [], []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return types.SimpleNamespace(message_id=100 + len(self.sent))

    async def edit_forum_topic(self, **kw):
        self.renamed.append(kw)
        return True

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self, username="testmech", uid=99005):
        self.id, self.username, self.is_bot, self.first_name = uid, username, False, "T"


class _Msg:
    def __init__(self, topic, mid, photo=True, text=None, group=None, reply_name=None, user=None):
        self.chat_id = SERV
        self.text = text
        self.caption = None
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic
        self.date = None
        self.from_user = user or _User()
        self.media_group_id = group
        self.forum_topic_created = None
        self.forum_topic_edited = None
        self.reply_to_message = (types.SimpleNamespace(forum_topic_created=types.SimpleNamespace(name=reply_name))
                                 if reply_name else None)


class _World:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append((name, kw))
            return {"ok": True, "items": [], "saved": True}
        return _any

    def find_bike(self, q):
        return {}

    def service_pending_get(self, *a, **kw):
        return {"ok": False, "error": "not_found"}


class _Claude:
    def __init__(self, vision):
        self.vision_q = list(vision)

    def quick(self, *a, **kw):
        return ""

    def vision(self, system, *a, **kw):
        return json.dumps(self.vision_q.pop(0) if self.vision_q else {})


class _Mem:
    """memory.db-заглушка: та же форма вызовов, что у `memory.Memory`, без файла базы."""

    def __init__(self, names=None):
        self.names, self.calls = dict(names or {}), []

    def set_topic_bike(self, chat_id, topic_id, name, source="auto"):
        self.calls.append((chat_id, topic_id, name, source))
        self.names[(chat_id, topic_id)] = name

    def get_topic_bike(self, chat_id, topic_id):
        return self.names.get((chat_id, topic_id), "")

    def all_topic_bikes(self):
        return dict(self.names)


CARDS = []


def _fake_send_card(text, buttons=None):
    CARDS.append({"text": text, "buttons": buttons})
    return 7000 + len(CARDS), notify.HQ_CHAT_ID


notify.send_card = _fake_send_card          # сеть не дёргаем ни при каких условиях


def _fresh(names=None, mem=None):
    """Чистая память номеров, подсказок и тем; memory.db — заглушка либо нет вовсе."""
    os.environ["PLATE_WATCH_STATE"] = tempfile.mktemp(prefix="plate_", suffix=".json", dir=_TMP)
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None
    S._PLATE_STATE = None
    S._TOPIC_NAMES.clear()
    S._TOPIC_NAMES.update({(SERV, t): n for t, n in (names or {}).items()})
    S.set_memory(mem)
    CARDS.clear()


def _photo(topic, mid, vision, ctx=None, group=None, reply_name=None, knob="1"):
    prev = os.environ.get("PLATE_WATCH")
    os.environ["PLATE_WATCH"] = knob
    ctx = ctx or _Ctx()
    saved = S._download_photo

    async def _dl(pm):
        return b"\xff\xd8 test"
    S._download_photo = _dl
    try:
        asyncio.run(S.handle(types.SimpleNamespace(message=_Msg(topic, mid, group=group, reply_name=reply_name)),
                             ctx, _World(), _Claude([vision])))
    finally:
        S._download_photo = saved
        os.environ["PLATE_WATCH"] = prev if prev is not None else "1"
    return ctx


class _Q:
    def __init__(self, data, user, text="карточка"):
        self.data, self.from_user = data, _User(*user)
        self.message = types.SimpleNamespace(chat_id=notify.HQ_CHAT_ID, message_thread_id=1160, message_id=7001,
                                             text=text, chat=types.SimpleNamespace(id=notify.HQ_CHAT_ID))
        self.answers, self.edits = [], []

    async def answer(self, txt=None, **kw):
        self.answers.append((txt, kw))

    async def edit_message_text(self, text=None, **kw):
        self.edits.append(text)

    async def edit_message_reply_markup(self, **kw):
        self.edits.append(("markup", kw))


def _press(data, user, ctx=None):
    ctx = ctx or _Ctx()
    q = _Q(data, user)
    asyncio.run(S.handle_service_button(types.SimpleNamespace(callback_query=q), ctx, _World()))
    return q, ctx


def _plate_texts(ctx):
    """Сообщения в тему байка, похожие на эту ветку: их быть не должно НИ ОДНОГО."""
    marks = ("Номер на байке", "🔢", "зелёной книг", "Переименовать", "svc:pl")
    return [kw for kw in ctx.bot.sent if any(m in str(kw) for m in marks)]


# ============================================================================================
#  (3) ЖИВОЙ `splinter.handle` + кнопки
# ============================================================================================
def test_live_83_card_to_owner_only_and_nothing_into_topic():
    _fresh({83: "XADV 750CC GREY 9286"})
    c1 = _photo(83, 4411, _plate("2478", series="2กจ"))
    assert CARDS == [], "одно чтение — ничего"
    c2 = _photo(83, 4520, _plate("2478"))
    assert len(CARDS) == 1, CARDS
    card = CARDS[0]
    assert "⚠️ Номер на байке не совпадает с зелёной книгой (9286)" in card["text"], card["text"]
    assert "«XADV 750CC GREY 2478»" in card["text"] and "4411" in card["text"] and "4520" in card["text"]
    labels = [b[0] for row in card["buttons"] for b in row]
    datas = [b[1] for row in card["buttons"] for b in row]
    assert labels == ["Переименовать тему", "Оставить"], labels
    assert datas[0].startswith("svc:plren:") and datas[1].startswith("svc:plkeep:"), datas
    for c in (c1, c2):
        assert _plate_texts(c) == [], _plate_texts(c)
        assert not c.bot.renamed
    # третье чтение того же номера — висящая карточка, второй нет
    _photo(83, 4600, _plate("2478"))
    assert len(CARDS) == 1, CARDS


def test_feature_hands_never_write_into_the_topic():
    """Код-уровень: руки ветки (`splinter._plate_*`) не зовут ни одной отправки в группу. Наружу —
    только карточка владельцу (`notify.send_card`) и переименование темы по его нажатию."""
    tree = ast.parse(open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read())
    hands = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith("_plate")]
    assert len(hands) >= 5, [h.name for h in hands]
    outward = {"send_message", "_send", "_send_retry", "_hint_send", "reply_text", "send_photo",
               "_send_bilingual", "copy_message", "forward_message", "pin_chat_message"}
    for h in hands:
        used = {n.attr for n in ast.walk(h) if isinstance(n, ast.Attribute)} |                {n.id for n in ast.walk(h) if isinstance(n, ast.Name)}
        assert not used & outward, (h.name, used & outward)


def test_rename_survives_restart_owner_press_renames_topic():
    mem = _Mem({(SERV, 83): "XADV 750CC GREY 9286"})
    _fresh({83: "XADV 750CC GREY 9286"}, mem=mem)
    _photo(83, 4411, _plate("2478"))
    _photo(83, 4520, _plate("2478"))
    ren = CARDS[0]["buttons"][0][0][1]
    S._PLATE_STATE = None                     # перезапуск: память номеров — только с диска
    q, ctx = _press(ren, OWNER)
    assert ctx.bot.renamed == [{"chat_id": SERV, "message_thread_id": 83, "name": "XADV 750CC GREY 2478"}], \
        ctx.bot.renamed
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 2478"
    assert mem.calls[-1] == (SERV, 83, "XADV 750CC GREY 2478", "forum_created"), mem.calls
    assert S.bike_from_topic(SERV, 83) == "XADV 750CC GREY 2478"
    assert any("Переименовано" in str(e) for e in q.edits), q.edits
    assert not ctx.bot.sent, "в тему байка ничего"
    # повтор нажатия — карточки уже нет
    q2, ctx2 = _press(ren, OWNER)
    assert not ctx2.bot.renamed and q2.answers and q2.answers[0][1].get("show_alert"), q2.answers
    # теперь тема = табличка 2478, книга 9286: предупреждение не раньше 7 суток (карточка его уже несла)
    _photo(83, 4700, _plate("2478"))
    assert len(CARDS) == 1, CARDS


def test_non_owner_press_refused():
    _fresh({83: "XADV 750CC GREY 9286"})
    _photo(83, 4411, _plate("2478"))
    _photo(83, 4520, _plate("2478"))
    ren = CARDS[0]["buttons"][0][0][1]
    for who in (PYM, ("testmech", 99005)):
        q, ctx = _press(ren, who)
        assert not ctx.bot.renamed, who
        assert q.answers and q.answers[0][1].get("show_alert") and "владел" in q.answers[0][0], q.answers
        assert not q.edits, q.edits
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 9286"
    q, ctx = _press(ren, OWNER)                # карточка жива и после чужих нажатий
    assert ctx.bot.renamed, "владелец переименовал"


def test_keep_press_silences_this_digits_for_this_name():
    _fresh({83: "XADV 750CC GREY 9286"})
    _photo(83, 4411, _plate("2478"))
    _photo(83, 4520, _plate("2478"))
    keep = CARDS[0]["buttons"][0][1][1]
    q, ctx = _press(keep, OWNER)
    assert not ctx.bot.renamed and any("Оставлено" in str(e) for e in q.edits), q.edits
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 9286"
    _photo(83, 4800, _plate("2478"))
    _photo(83, 4801, _plate("2478"))
    assert len(CARDS) == 1, CARDS


def test_rename_refused_when_topic_renamed_meanwhile():
    _fresh({83: "XADV 750CC GREY 9286"})
    _photo(83, 4411, _plate("2478"))
    _photo(83, 4520, _plate("2478"))
    ren = CARDS[0]["buttons"][0][0][1]
    S._TOPIC_NAMES[(SERV, 83)] = "XADV 750CC GREY 7777"     # кто-то переименовал руками
    q, ctx = _press(ren, OWNER)
    assert not ctx.bot.renamed and q.answers[0][1].get("show_alert"), q.answers
    assert S._TOPIC_NAMES[(SERV, 83)] == "XADV 750CC GREY 7777"


def test_live_82_nothing():
    _fresh({82: "XADV 750CC BLACK 5104"})
    _photo(82, 900, _plate("5104"))
    _photo(82, 901, _plate("5104"))
    assert CARDS == []


def test_live_1190_card_with_warning():
    _fresh({1190: "XMAX 300CC NEW BROWN 8676"})
    _photo(1190, 70, _plate("9315"))
    _photo(1190, 75, _plate("9315"))
    assert len(CARDS) == 1 and "⚠️ Номер на байке не совпадает с зелёной книгой (8676)" in CARDS[0]["text"], CARDS
    assert "«XMAX 300CC NEW BROWN 9315»" in CARDS[0]["text"]


def test_background_bike_and_album_are_nothing():
    _fresh({83: "XADV 750CC GREY 9286"})
    _photo(83, 4411, _plate("5104", legible=False))          # чужой байк на фоне
    _photo(83, 4412, _plate("5104", legible=False))
    assert CARDS == []
    _photo(83, 4413, _plate("2478"), group="alb1")           # альбом — одна отправка
    _photo(83, 4414, _plate("2478"), group="alb1")
    assert CARDS == []


def test_kill_switch_records_nothing():
    _fresh({83: "XADV 750CC GREY 9286"})
    _photo(83, 4411, _plate("2478"), knob="0")
    _photo(83, 4520, _plate("2478"), knob="0")
    assert CARDS == [] and PW.clean(S._PLATE_STATE)["readings"] == {}
    _photo(83, 4600, _plate("2478"))                         # включили — прошлые не считались
    assert CARDS == []


# ============================================================================================
#  (4) ДРЕЙФ ИМЕНИ ТЕМЫ
# ============================================================================================
def test_drift_ordinary_reply_to_creation_does_not_overwrite():
    """Живой случай 82: 16.06 переименована в «XADV 750 BLACK 5104», 21.10 09:23:30 UTC обычное фото
    @Pleummmm (reply на сообщение создания с ПЕРВЫМ именем) вернуло имя бота к «…3902»."""
    mem = _Mem({(SERV, 82): "XADV 750 BLACK 5104"})
    _fresh({82: "XADV 750 BLACK 5104"}, mem=mem)
    msg = _Msg(82, 13000, reply_name="XADV 750 BLACK 3902", user=_User("pleummmm", 99001))
    assert S._remember_topic_name(SERV, 82, msg) == "XADV 750 BLACK 5104"
    assert S._TOPIC_NAMES[(SERV, 82)] == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls
    # и через живой путь фото (так и было 21.10)
    _photo(82, 13001, {"kind": "bike", "dirt": False}, reply_name="XADV 750 BLACK 3902")
    assert S.bike_from_topic(SERV, 82) == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls
    # кэш пуст (до засева), имя знает только memory.db — тоже не переписываем
    S._TOPIC_NAMES.clear()
    S._remember_topic_name(SERV, 82, msg)
    assert S.bike_from_topic(SERV, 82) == "XADV 750 BLACK 5104" and mem.calls == [], mem.calls


def test_drift_missing_name_is_filled_and_events_stay_authoritative():
    # номера тем — вне живого форума: на сервере рядом лежит topics_map.json, и тема 82 в нём известна
    t, t2 = 990082, 990084
    mem = _Mem()
    _fresh({}, mem=mem)
    msg = _Msg(t, 13002, reply_name="XADV 750 BLACK 3902")
    assert S._remember_topic_name(SERV, t, msg) == "XADV 750 BLACK 3902"      # пусто → заполнить
    assert mem.calls == [(SERV, t, "XADV 750 BLACK 3902", "forum_created")], mem.calls
    ren = _Msg(t, 13003, photo=False)
    ren.forum_topic_edited = types.SimpleNamespace(name="XADV 750 BLACK 5104")
    assert S._remember_topic_name(SERV, t, ren) == "XADV 750 BLACK 5104"      # переименование пишет всегда
    assert mem.calls[-1] == (SERV, t, "XADV 750 BLACK 5104", "forum_created"), mem.calls
    created = _Msg(t2, 13004, photo=False)
    created.forum_topic_created = types.SimpleNamespace(name="NEW BIKE 1234")
    S._TOPIC_NAMES[(SERV, t2)] = "OLD 1"
    assert S._remember_topic_name(SERV, t2, created) == "NEW BIKE 1234"       # создание — тоже
    icon_only = _Msg(t, 13005, photo=False, reply_name="XADV 750 BLACK 3902")
    icon_only.forum_topic_edited = types.SimpleNamespace(name=None)          # сменили только значок
    assert S._remember_topic_name(SERV, t, icon_only) == "XADV 750 BLACK 5104"
    S.set_memory(None)


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
    S.set_memory(None)
    print(f"{ok}/{ok + fail}")
    sys.exit(1 if fail else 0)
