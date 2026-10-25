"""ЧЕК И СТОИМОСТЬ ОБСЛУЖИВАНИЯ В ИСТОРИИ БАЙКА (25.10.2026, SVCRECEIPT2510).

Живые случаи группы «Обслуживание»:
  * 01.10.2026 11:19, XADV 750 GREY 2478 — фото чека PRASUTBIGBIKE CO.,LTD: «Pirelli Diablo Rosso Scoo…»
    5,600.00, тайская строка болтов 2 × 25.00 = 50.00, GRAND TOTAL 5,650.00, дата «01/10/2569». Разбор снимка
    назвал вид `receipt` — и всё: в истории байка ни суммы, ни магазина, бот молчит;
  * 15.10.2026 VULCAN — FM204 250, грипсы Daytona GGD-Duel 790, работа 300 = 1,340;
  * 19.10.2026 — FM204 250, регулировка цепи 0, работа 200 = 450;
  * цена текстом («Передняя шина — 980 бат», фикстура `tests/works_batch_harness.py`) терялась, а висящий
    вопрос о пробеге взял бы «Total 2,290 bath» одометром 2290.

Что держит сьют:
  (A) чистое решение `service_cost`: позиции и итог чека, буддийский год, строка истории ≤ 200 и без «—»
      (шаблон карточки `_SVC_HIST_RE` её работой не прочтёт), стоимость текстом и её отрицания;
  (B) снимок чека в теме → ОДНА строка «событий» вида «чек» + ответ RU/TH; тот же снимок второй раз — строки
      нет; сомнение — ничего не пишем и просим итог цифрами; ответ цифрами на эту просьбу — строка;
  (C) стоимость текстом → та же строка; смешанное сообщение идёт дальше прежним путём;
  (D) число с «бат» пробегом не становится: вопрос о пробеге, фаза 2, разбор сообщения, масло задним числом;
  (E) просьба о чеке — ОДНА строка к подтверждению записанной работы, раз на тему за день, и не тогда, когда
      стоимость визита уже известна;
  (F) карточка байка строку «чек» работой не показывает; bot.py зовёт дверь стоимости раньше решателя и фазы 2;
  (G) `SVC_RECEIPT=0` — путь прежний.
Мост, Telegram и модель — заглушки (платных вызовов нет); имена боевых операций склеены из кусков; байки
выдуманы и помечены TESTBIKE, числа чеков — живые. Файлы состояния — во временном каталоге.
"""
import ast
import asyncio
import contextlib
import datetime
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
_TMP = tempfile.gettempdir()
os.environ.setdefault("DECIDER_LIVE_STATE", os.path.join(_TMP, f"dlive_rcpt_{os.getpid()}.json"))
os.environ.setdefault("MILEAGE_Q_STATE", os.path.join(_TMP, f"mileage_q_rcpt_{os.getpid()}.json"))
os.environ.setdefault("HINT_DEDUP_STATE", os.path.join(_TMP, f"hint_rcpt_{os.getpid()}.json"))
os.environ.setdefault("TOPIC_FEED_DIR", os.path.join(_TMP, f"topic_feed_rcpt_{os.getpid()}"))
os.environ.setdefault("SVC_TOKENS_STATE", os.path.join(_TMP, f"svc_tokens_rcpt_{os.getpid()}.json"))
os.environ.setdefault("WORKS_PERSIST_STATE", os.path.join(_TMP, f"works_rcpt_{os.getpid()}.json"))
os.environ["NEVER_SILENT"] = "1"        # боевые дефолты ЯВНО: сьют не зависит от файла настроек машины
os.environ["FLOOR_QUIET"] = "1"
os.environ["HINTS_DEDUP"] = "0"         # замок повторов здесь не предмет
os.environ["ACT_GATE"] = "0"            # ворота действия здесь не предмет (их судит test_act_gate)
os.environ["TOPIC_DECIDER_LIVE"] = "0"
os.environ["SVC_RECEIPT"] = "1"

import splinter as S          # noqa: E402
try:
    import service_cost as C  # noqa: E402
except ImportError:           # дерево ДО правки: модуля нет — краснеет каждый случай сам, а не весь файл
    C = None

OP_EVENT = "add" + "_event"
OP_FIND = "find" + "_bike"
OP_TRACKER = "service" + "_upsert"
OP_SP_GET = "service_pending" + "_get"
OP_SVC_LIST = "service" + "_list"

BIKE_X = "TESTBIKE XADV 750 9991"
BIKE_V = "TESTBIKE VULCAN 650 9992"
RU_ASK = "🧾 Пришлите фото чека или стоимость работ"


def _chat_of(mode):
    for cid, m in S.GROUPS.items():
        if m == mode:
            return cid
    raise AssertionError(f"в GROUPS нет контура {mode}")


CHAT = _chat_of("servicing")
_T = [9400]


def _topic(bike=BIKE_X):
    """Своя тема на каждый случай: память визита, накопители и вопросы не перетекают."""
    _T[0] += 1
    S._TOPIC_BIKE_OVERRIDE[(CHAT, _T[0])] = bike
    return _T[0]


# ── фикстуры: разборы снимков чеков, какими их отдаёт модель (числа живые) ──────────────────────────────
RC_XADV = {"shop": "PRASUTBIGBIKE CO.,LTD", "date": "01/10/2569 11:19",
           "items": [{"name": "Pirelli Diablo Rosso Scooter", "name_orig": "Pirelli Diablo Rosso Scoo…",
                      "qty": 1, "unit_price": 5600, "price": 5600},
                     {"name": "болты", "name_orig": "น็อต", "qty": 2, "unit_price": 25, "price": 50}],
           "total": "5,650.00", "currency": "THB", "confidence": "high"}
RC_V1510 = {"shop": None, "date": "15/10/2569",
            "items": [{"name": "FM204", "name_orig": "FM204", "qty": 1, "unit_price": 250, "price": 250},
                      {"name": "грипсы Daytona GGD-Duel", "name_orig": "Daytona GGD-Duel", "qty": 1,
                       "unit_price": 790, "price": 790},
                      {"name": "работа", "name_orig": "Service", "qty": 1, "unit_price": 300, "price": 300}],
            "total": "1,340.00", "currency": "THB", "confidence": "high"}
RC_V1910 = {"shop": None, "date": "19/10/2569",
            "items": [{"name": "FM204", "name_orig": "FM204", "qty": 1, "price": 250},
                      {"name": "регулировка цепи", "name_orig": "chain adjust", "qty": 1, "price": 0},
                      {"name": "работа", "name_orig": "Service", "qty": 1, "price": 200}],
            "total": 450, "currency": "THB", "confidence": "high"}

NOTE_XADV = "чек PRASUTBIGBIKE 01.10.2026: Pirelli Diablo Rosso Scooter 5600 ฿; болты 2×25 ฿; итого 5650 ฿"
NOTE_V1510 = "чек 15.10.2026: FM204 250 ฿; грипсы Daytona GGD-Duel 790 ฿; работа 300 ฿; итого 1340 ฿"
NOTE_V1910 = "чек 19.10.2026: FM204 250 ฿; регулировка цепи 0 ฿; работа 200 ฿; итого 450 ฿"


# ── заглушки ─────────────────────────────────────────────────────────────────────────────────────────────
class _Bridge:
    """Мост-заглушка: лист «события» — словарь в памяти с дедупом по ключу, как у моста (`botMsgExists_`)."""

    def __init__(self, answers=None):
        self.calls, self.rows = [], {}
        self._answers = answers or {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _catch(*a, **kw):
            self.calls.append((name, a, kw))
            if name == OP_EVENT:
                mid = kw.get("msg_id") or ""
                if mid and mid in self.rows:
                    return {"ok": True, "duplicate": True, "msg_id": mid}
                self.rows[mid] = dict(kw)
                return {"ok": True, "saved": True}
            ans = self._answers.get(name, {"ok": True})
            return ans(*a, **kw) if callable(ans) else ans
        return _catch

    def events(self, et=None):
        return [kw for n, a, kw in self.calls if n == OP_EVENT and (et is None or kw.get("event_type") == et)]


def _bridge(**extra):
    ans = {OP_FIND: {"name": BIKE_X}, OP_SP_GET: {"ok": False, "error": "not_found"},
           OP_TRACKER: {"ok": True, "status": "ok", "next_km": 48000, "km_left": 2797},
           OP_SVC_LIST: {"ok": True, "items": []}}
    ans.update(extra)
    return _Bridge(ans)


class _Claude:
    """Модель-заглушка: разбор снимка байка → `bike`, разбор чека → `receipt`, разбор текста → `parse[text]`."""

    def __init__(self, bike=None, receipt=None, parse=None):
        self.bike, self.receipt, self.parse = bike or {}, receipt or {}, parse or {}
        self.systems = []

    def vision(self, system, img, *a, **k):
        self.systems.append(system)
        if system == getattr(S, "VISION_SERVICE_RECEIPT", "\x00"):
            return json.dumps(self.receipt)
        return json.dumps(self.bike)

    def quick(self, system, text, *a, **k):
        if system == S.SERVICING_SYSTEM:
            return json.dumps(self.parse.get(str(text or "").strip(), {}))
        return "ครับ"


class _Bot:
    id, username = 777000, "turbobaby_manager_bot"

    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 900 + len(self.sent), "text": kw.get("text")})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self, username="testmech", is_bot=False):
        self.id, self.username, self.is_bot, self.first_name = 99045, username, is_bot, "T"


class _Photo:
    def __init__(self, uid):
        self.file_unique_id, self.file_id = uid, uid


class _Msg:
    def __init__(self, text=None, topic=None, photo_uid=None, caption=None, mid=7001, reply_to=None,
                 user="testmech", day=(2026, 10, 1)):
        self.chat_id, self.message_thread_id = CHAT, topic
        self.text, self.caption = text, caption
        self.photo = [_Photo(photo_uid)] if photo_uid else []
        self.message_id, self.from_user, self.reply_to_message = mid, _User(user), reply_to
        self.date = datetime.datetime(*day, 4, 19, tzinfo=datetime.timezone.utc)
        self.media_group_id = None


class _BotMsg:
    def __init__(self, text):
        self.text, self.caption, self.from_user, self.message_id = text, None, _User("turbobaby_manager_bot", True), 950


class _Upd:
    def __init__(self, msg):
        self.message = msg


@contextlib.contextmanager
def _patch(mod, **repl):
    saved = {k: getattr(mod, k) for k in repl}
    for k, v in repl.items():
        setattr(mod, k, v)
    try:
        yield
    finally:
        for k, v in saved.items():
            setattr(mod, k, v)


@contextlib.contextmanager
def _env(**kv):
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


async def _img(pm):
    return b"fixture-image"


def _photo(msg, claude, bridge=None, album=None):
    """Настоящие `handle` → `_handle_servicing` → пол; скачивание, лента и тень решателя заглушены."""
    ctx, br = _Ctx(), bridge or _bridge()
    with _patch(S, _download_photo=_img, decider_live_on=lambda: False,
                decider_shadow=lambda *a, **k: None, feed_vision=lambda *a, **k: True):
        asyncio.run(S.handle(_Upd(msg), ctx, br, claude, album_msgs=album))
    return ctx.bot.sent, br


def _cost(msg, bridge=None):
    ctx, br = _Ctx(), bridge or _bridge()
    took = asyncio.run(S.handle_service_cost(msg, ctx, br))
    return took, ctx.bot.sent, br


def _texts(sent):
    return [m.get("text") or "" for m in sent]


# ============================================================================================================
#  (A) ЧИСТОЕ РЕШЕНИЕ
# ============================================================================================================
def test_xadv_receipt_buddhist_year_items_and_note():
    rc = C.normalize_receipt(RC_XADV, ref_date=datetime.date(2026, 10, 1))
    assert rc["ok"], rc["why"]
    assert rc["date"] == datetime.date(2026, 10, 1), rc["date"]          # 2569 → 2026, дд/мм
    assert rc["total"] == 5650 and [i["price"] for i in rc["items"]] == [5600, 50], rc
    assert rc["items"][1]["qty"] == 2 and rc["items"][1]["unit"] == 25, rc["items"][1]
    assert C.receipt_note(rc) == NOTE_XADV, C.receipt_note(rc)


def test_vulcan_receipts_15_and_19_october():
    r1 = C.normalize_receipt(RC_V1510, ref_date=datetime.date(2026, 10, 15))
    r2 = C.normalize_receipt(RC_V1910, ref_date=datetime.date(2026, 10, 19))
    assert r1["ok"] and r2["ok"], (r1["why"], r2["why"])
    assert C.receipt_note(r1) == NOTE_V1510, C.receipt_note(r1)
    assert C.receipt_note(r2) == NOTE_V1910, C.receipt_note(r2)          # позиция за 0 ฿ — честный ноль


def test_note_never_reads_as_work_on_mileage_and_fits_cap():
    """Карточка разбирает историю шаблоном «<работа> — <км> км»: строка чека им не читается никогда."""
    import re
    long = dict(RC_XADV, items=[{"name": f"позиция — номер {i} — 45 км", "price": 10} for i in range(40)],
                total=400)
    for rc in (C.normalize_receipt(RC_XADV), C.normalize_receipt(long)):
        note = C.receipt_note(rc)
        assert len(note) <= C.NOTE_CAP == S.work_name.NOTE_CAP, len(note)
        assert "—" not in note and not re.match(S._SVC_HIST_RE, note, re.IGNORECASE), note
        assert note.endswith(f"итого {C.fmt(rc['total'])} ฿"), note             # итог не режется никогда
    assert "…" in C.receipt_note(C.normalize_receipt(long))


def test_uncertain_receipt_is_not_ok():
    low = dict(RC_XADV, confidence="low")
    no_total = dict(RC_XADV, total=None, confidence="low")
    mismatch = dict(RC_XADV, total=5950)                                    # цифра итога прочитана не та
    for v in (low, no_total, mismatch, {}):
        assert C.normalize_receipt(v)["ok"] is False, v
    assert "не сходятся" in C.normalize_receipt(mismatch)["why"]
    vat = dict(RC_V1510, total=round(1340 * 1.07, 2))                       # итог = позиции + НДС 7 %
    assert C.normalize_receipt(vat)["ok"], C.normalize_receipt(vat)["why"]


def test_receipt_date_out_of_window_is_dropped_not_guessed():
    rc = C.normalize_receipt(dict(RC_XADV, date="01/10/2559"), ref_date=datetime.date(2026, 10, 1))
    assert rc["ok"] and rc["date"] is None and "вне окна" in rc["date_note"], rc
    assert C.be_date("15/10/69") == datetime.date(2026, 10, 15) and C.be_date("2026-10-19") == datetime.date(2026, 10, 19)


def test_typed_costs_parsed_into_items_and_total():
    a = C.parse_cost_text("Передняя шина — 980 бат")
    assert [(i["name"], i["price"]) for i in a["items"]] == [("Передняя шина", 980)] and a["total"] == 980, a
    b = C.parse_cost_text("работа 300, фильтр 250")
    assert [(i["name"], i["price"]) for i in b["items"]] == [("работа", 300), ("фильтр", 250)], b
    assert b["total"] == 550 and not b["marked"], b
    c = C.parse_cost_text("итого 1340 бат")
    assert c["items"] == [] and c["total"] == 1340 and c["total_explicit"], c
    d = C.parse_cost_text("Total 2,290 bath")
    assert d["total"] == 2290, d
    e = C.parse_cost_text("ค่าแรง 300 บาท")
    assert e["total"] == 300, e
    assert C.receipt_note(a, typed=True) == "стоимость: Передняя шина 980 ฿; итого 980 ฿"


def test_typed_cost_negatives_km_and_questions():
    for t in ("45203 км", "пробег 45203", "Эти работы на 37480", "45203", "заменил колодки",
              "будет стоить 3000 бат?", "сколько стоит шина", "first service 1000", "колодки 45203"):
        assert C.parse_cost_text(t) is None, t
    assert C.parse_cost_text("45203", asked="cost+km") is None          # голое число на просьбу с пробегом — пробег
    # r2: голое число на просьбу о чеке — стоимость ТОЛЬКО при известном пробеге и вне окна одометра
    assert C.parse_cost_text("800", asked="cost", odo_km=45203)["total"] == 800
    assert C.parse_cost_text("800", asked="cost") is None                # пробег не известен — fail-closed


def test_money_number_is_never_km():
    assert C.is_money_km("Total 2,290 bath", "2290") and C.is_money_km("итого 1340 бат", 1340)
    assert C.is_money_km("Передняя шина — 980 бат", "980")
    assert not C.is_money_km("пробег 45203", "45203") and not C.is_money_km("45203 км", 45203)
    assert not C.is_money_km("масло 1200 бат, пробег 45203", "45203")


def test_ask_line_attach_keeps_halves():
    out = C.attach("🐀 Splinter\n🇹🇭 รับงาน\n🇷🇺 Принял работы", *C.ASK)
    lines = out.split("\n")
    assert lines[2] == C.ASK[0] and lines[-1] == RU_ASK == C.ASK[1], out
    sep = S._SEP
    out2 = C.attach(f"🐀 X\n🇹🇭 a\n{sep}\n🇷🇺 b", *C.ASK)
    assert out2.split("\n") == ["🐀 X", "🇹🇭 a", C.ASK[0], sep, "🇷🇺 b", RU_ASK], out2
    assert C.attach("t", "", "") == "t"


def test_service_cost_module_is_pure():
    src = open(C.__file__, encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            mods |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module or "")
    assert mods <= {"re", "datetime"}, mods


# ============================================================================================================
#  (B) СНИМОК ЧЕКА В ТЕМЕ
# ============================================================================================================
def test_receipt_photo_writes_one_row_and_answers():
    t = _topic()
    S._LAST_RECORDED_KM[(CHAT, t)] = (45203, time.time())                 # последний пробег темы
    cl = _Claude(bike={"kind": "receipt"}, receipt=RC_XADV)
    sent, br = _photo(_Msg(topic=t, photo_uid="AgADrcpt2478a"), cl)
    rows = br.events()
    assert len(rows) == 1, rows                                            # ОДНА строка, строки «photo» нет
    r = rows[0]
    assert r["event_type"] == "чек" and r["notes"] == NOTE_XADV, r
    assert r["mileage"] == "45203" and r["bike"] == BIKE_X and r["msg_id"].startswith("rcpt:"), r
    assert cl.systems.count(S.VISION_SERVICE_RECEIPT) == 1, cl.systems
    assert len(sent) == 1, _texts(sent)
    body = sent[0]["text"]
    assert "🇷🇺 🧾 Чек PRASUTBIGBIKE 01.10.2026" in body and "итого 5650 ฿ — записал в историю" in body, body
    assert "🇹🇭 🧾 ใบเสร็จ PRASUTBIGBIKE 01.10.2026" in body and "รวม 5650 ฿" in body, body
    assert "болты 2 × 25 = 50 ฿" in body and "น็อต 2 × 25 = 50 ฿" in body, body


def test_same_photo_twice_is_not_written_twice():
    t = _topic()
    br = _bridge()
    cl = _Claude(bike={"kind": "receipt"}, receipt=RC_XADV)
    _photo(_Msg(topic=t, photo_uid="AgADsame", mid=7101), cl, br)
    sent, _ = _photo(_Msg(topic=t, photo_uid="AgADsame", mid=7102), cl, br)   # тот же снимок, другое сообщение
    assert len(br.rows) == 1 and len(br.events()) == 2, br.rows            # мост схлопнул по ключу
    assert "уже был в истории" in sent[-1]["text"], sent[-1]["text"]


def test_receipt_row_without_known_km_has_empty_mileage():
    t = _topic(BIKE_V)
    S._LAST_RECORDED_KM.pop((CHAT, t), None)
    _sent, br = _photo(_Msg(topic=t, photo_uid="AgADv1510", day=(2026, 10, 15)),
                       _Claude(bike={"kind": "receipt"}, receipt=RC_V1510))
    assert [r["notes"] for r in br.events()] == [NOTE_V1510], br.events()
    assert br.events()[0]["mileage"] == "", br.events()[0]                 # сырого зрения в строке нет


def test_caption_says_receipt_even_if_photo_kind_other():
    t = _topic(BIKE_V)
    _sent, br = _photo(_Msg(topic=t, photo_uid="AgADv1910", caption="чек", day=(2026, 10, 19)),
                       _Claude(bike={"kind": "other"}, receipt=RC_V1910))
    assert [r["notes"] for r in br.events("чек")] == [NOTE_V1910], br.events()


def test_unsure_receipt_writes_nothing_then_digits_reply_writes_cost():
    t = _topic()
    br = _bridge()
    sent, _ = _photo(_Msg(topic=t, photo_uid="AgADblur"), _Claude(bike={"kind": "receipt"},
                                                                  receipt=dict(RC_XADV, confidence="low")), br)
    assert br.events() == [], br.events()
    body = sent[-1]["text"]
    assert "Чек прочитал неуверенно" in body and "цифрами" in body and "PRASUTBIGBIKE" in body, body
    # r2: пробег темы не известен — голое «1340» стоимостью не становится (fail-closed), строки нет
    S._LAST_RECORDED_KM.pop((CHAT, t), None)
    took0, sent0, _ = _cost(_Msg(text="1340", topic=t, reply_to=_BotMsg(body), mid=7011), br)
    assert took0 is False and sent0 == [] and br.events() == [], br.events()
    took, sent2, _ = _cost(_Msg(text="итого 1340", topic=t, reply_to=_BotMsg(body), mid=7012), br)
    assert took is True and [r["notes"] for r in br.events()] == ["стоимость: итого 1340 ฿"], br.events()
    assert "Записал стоимость" in sent2[-1]["text"], _texts(sent2)


#: Подтверждение со строкой просьбы, которое пробега НЕ просит (сводка цикла): ответ на него — вид "cost".
ASK_SUMMARY = "🐀 Splinter · 📌 TESTBIKE ADV160 9993\n🇹🇭 ✅ บันทึกครบแล้วครับ\n🇷🇺 ✅ Готово — текущий пробег 1631 км."


def _reply_cost(text, odo=None, odo_row=None, mid=7401):
    """Ответ реплаем на просьбу о чеке; `odo` — записанный пробег темы, `odo_row` — свой одометр в мосте."""
    t = _topic("TESTBIKE ADV160 9993")
    S._LAST_RECORDED_KM.pop((CHAT, t), None)
    if odo is not None:
        S._LAST_RECORDED_KM[(CHAT, t)] = (odo, time.time())
    items = [odo_row] if odo_row else []
    br = _bridge(**{OP_SVC_LIST: {"ok": True, "items": items}})
    ask = _BotMsg(C.attach(ASK_SUMMARY, *C.ASK))
    assert C.ask_kind(ask.text) == "cost"
    took, sent, _ = _cost(_Msg(text=text, topic=t, reply_to=ask, mid=mid), br)
    return took, sent, br


def test_r2_bare_reply_is_cost_only_outside_odometer_window():
    """r2, живой довод: ADV160 6470 стоит на 1631 км, замена масла 21.10 на 1200 км — «1650» в ответ на
    просьбу о чеке есть пробег, а не «итого 1650 ฿». Окно одометра [пробег − 150, пробег + 3000]."""
    took, sent, br = _reply_cost("1650", odo=1631)
    assert took is False and sent == [] and br.events() == [], br.events()   # пробег — прежнему пути, без вопроса
    took, sent, br = _reply_cost("450", odo=1631)
    assert took is True and [r["notes"] for r in br.events()] == ["стоимость: итого 450 ฿"], br.events()
    took, sent, br = _reply_cost("450")                                       # пробег не известен — fail-closed
    assert took is False and sent == [] and br.events() == [], br.events()
    took, sent, br = _reply_cost("29870", odo=29859)                          # близнец: и > 9999, и в окне
    assert took is False and br.events() == [], br.events()
    took, sent, br = _reply_cost("1650 бат", odo=1631)                        # признак денег — стоимость всегда
    assert took is True and [r["notes"] for r in br.events()] == ["стоимость: итого 1650 ฿"], br.events()
    took, sent, br = _reply_cost("итого 1650", odo=1631)                      # слово итога — тоже
    assert took is True and br.events()[0]["notes"] == "стоимость: итого 1650 ฿", br.events()


def test_r2_window_uses_own_odometer_and_edges():
    """Источник пробега — тот же, что у строки чека: запись темы за сутки, иначе свой одометр байка не
    старше суток. Края окна включительно; позиция с именем без слова цены в окне — тоже не стоимость."""
    fresh = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    row = {"bike": "TESTBIKE ADV160 9993", "current_km": 1631, "updated_at": fresh}
    took, _s, br = _reply_cost("1650", odo_row=row)
    assert took is False and br.events() == [], br.events()
    stale = dict(row, updated_at="2026-01-01T00:00:00.000Z")                 # одометр старше суток = не известен
    took, _s, br = _reply_cost("450", odo_row=stale)
    assert took is False and br.events() == [], br.events()
    for n, inside in ((1481, True), (1480, False), (4631, True), (4632, False)):
        assert bool(C.could_be_odometer(n, 1631)) is inside, n
    assert C.could_be_odometer(1650, None) is None
    assert C.parse_cost_text("колодки 1650", asked="cost", odo_km=1631) is None
    assert C.parse_cost_text("колодки 450", asked="cost", odo_km=1631)["total"] == 450
    assert C.parse_cost_text("работа 1650", asked="cost", odo_km=1631)["total"] == 1650   # слово цены
    two =C.parse_cost_text("1. работа 300\n2. фильтр 250", asked="cost", odo_km=40000)
    assert two["total"] == 550, two                                                         # «1.»/«2.» — не деньги


def test_album_receipt_plus_dashboard_keeps_old_path_for_dashboard():
    t = _topic()
    asked = []

    async def _ask(context, chat_id, topic_id, bike, km, **k):
        asked.append(km)
    album = [_Msg(topic=t, photo_uid="AgADalb1", mid=7201), _Msg(topic=t, photo_uid="AgADalb2", mid=7202)]
    vis = iter([{"kind": "receipt"}, {"kind": "dashboard", "mileage": "45203", "mileage_confidence": "high"}])

    class _Cl(_Claude):
        def vision(self, system, img, *a, **k):
            self.systems.append(system)
            return json.dumps(self.receipt if system == S.VISION_SERVICE_RECEIPT else next(vis))
    with _patch(S, _ask_mileage_confirm=_ask):
        _sent, br = _photo(album[0], _Cl(receipt=RC_XADV), album=album)
    assert [r["notes"] for r in br.events("чек")] == [NOTE_XADV], br.events()
    assert asked == ["45203"], asked                                       # приборку судит прежний путь


# ============================================================================================================
#  (C) СТОИМОСТЬ ТЕКСТОМ
# ============================================================================================================
def test_typed_total_is_a_cost_row_not_km():
    t = _topic()
    took, sent, br = _cost(_Msg(text="Total 2,290 bath", topic=t))
    assert took is True, "чистая стоимость — дверь стоимости берёт сообщение"
    rows = br.events()
    assert len(rows) == 1 and rows[0]["notes"] == "стоимость: итого 2290 ฿" and rows[0]["mileage"] == "", rows
    assert rows[0]["event_type"] == "чек" and rows[0]["msg_id"] == f"cost:{CHAT}:7001", rows
    assert "итого 2290 ฿" in sent[-1]["text"] and "รวม 2290 ฿" in sent[-1]["text"], _texts(sent)


def test_typed_items_without_currency_with_cost_word():
    t = _topic()
    took, _sent, br = _cost(_Msg(text="работа 300, фильтр 250", topic=t))
    assert took is True and [r["notes"] for r in br.events()] == \
        ["стоимость: работа 300 ฿; фильтр 250 ฿; итого 550 ฿"], br.events()


def test_typed_cost_with_work_is_mixed_goes_on_and_is_acked_later():
    """«Передняя шина — 980 бат» само по себе — отчёт о работе С ценой: строка стоимости пишется, сообщение
    идёт дальше прежним путём (дверь работ его не теряет), «записал стоимость» едет подтверждением работ."""
    t = _topic()
    took, sent, br = _cost(_Msg(text="Передняя шина — 980 бат", topic=t))
    assert took is False and sent == [], _texts(sent)
    assert [r["notes"] for r in br.events()] == ["стоимость: Передняя шина 980 ฿; итого 980 ฿"], br.events()
    acc = S._summary_acc(CHAT, t)
    acc["works"] = ["замена передней шины"]
    ctx = _Ctx()
    asyncio.run(S._emit_summary(ctx, CHAT, t, BIKE_X))
    body = ctx.bot.sent[-1]["text"]
    assert "🧾 Записал стоимость: итого 980 ฿" in body and RU_ASK not in body, body


def test_typed_cost_as_reply_to_ask_is_pure():
    t = _topic()
    ask_msg = _BotMsg(C.attach(S.msg_work_receipt(BIKE_X, ["замена передней шины"]), *C.ASK))
    took, sent, br = _cost(_Msg(text="Передняя шина — 980 бат", topic=t, reply_to=ask_msg))
    assert took is True and len(br.events()) == 1 and "Записал стоимость" in sent[-1]["text"], _texts(sent)
    took2, _s, br2 = _cost(_Msg(text="45203", topic=_topic(), reply_to=ask_msg))
    assert took2 is False and br2.events() == []                           # голое число там — пробег


def test_typed_total_equal_to_receipt_is_not_a_second_row():
    t = _topic()
    br = _bridge()
    _photo(_Msg(topic=t, photo_uid="AgADeq"), _Claude(bike={"kind": "receipt"}, receipt=RC_XADV), br)
    took, sent, _ = _cost(_Msg(text="итого 5650 бат", topic=t, mid=7301), br)
    assert took is True and len(br.events()) == 1, br.events()
    assert "уже записан по чеку" in sent[-1]["text"], _texts(sent)


def test_plain_km_message_is_not_a_cost():
    t = _topic()
    for text in ("45203 км", "пробег 45203", "45203", "заменил колодки, пробег 45203"):
        took, sent, br = _cost(_Msg(text=text, topic=t))
        assert took is False and br.events() == [] and sent == [], text


# ============================================================================================================
#  (D) ЧИСЛО С «БАТ» — НЕ ПРОБЕГ
# ============================================================================================================
def _doors(rec):
    def _odo(*a, **k):
        rec.append(("odo", str(a[4])))

    async def _after(*a, **k):
        rec.append(("after", str(a[5])))
    return dict(_odo_confirmed=_odo, _after_mileage=_after, _sp_open=lambda *a, **k: None,
                _mileage_q_forget=lambda *a, **k: None)


def test_pending_mileage_question_does_not_take_money():
    for text, want in (("Total 2,290 bath", None), ("итого 1340 бат", None), ("45203", "45203"),
                       ("итого 1340 бат, пробег 45203", "45203")):
        t = _topic()
        rec = []
        S._PENDING_MILEAGE[(CHAT, t)] = ("41973", BIKE_X, None, False, time.time())
        with _patch(S, **_doors(rec)):
            took = asyncio.run(S.handle_mileage_confirm(_Msg(text=text, topic=t), _Ctx(), _bridge(), text))
        S._PENDING_MILEAGE.pop((CHAT, t), None)
        if want is None:
            assert took is False and rec == [], (text, rec)
        else:
            assert took is True and ("odo", want) in rec, (text, rec)


def test_phase2_does_not_take_money_as_odometer():
    for text, parse, want in (("Замена масла — 1200 бат", {"works": ["замена масла"], "mileage": "1200"}, None),
                              ("Замена масла 1200 бат", {"works": ["замена масла"]}, None),
                              ("Замена масла, пробег 45203", {"works": ["замена масла"], "mileage": "45203"}, "45203")):
        t = _topic()
        adv = []

        async def _adv(context, bridge, chat_id, topic_id, bike, declared, done, odo, **kw):
            adv.append(str(odo))
        sp = {"status": "ждёт_факт", "declared": "oil", "done": "", "note": ""}
        with _patch(S, _sp_open=lambda *a, **k: sp, _sp_advance_to_confirm=_adv,
                    _odo_known_fresh=lambda *a, **k: {"use": False, "why": "тест"}):
            asyncio.run(S.handle_service_result(_Msg(text=text, topic=t), _Ctx(), _bridge(),
                                                _Claude(parse={text: parse}), text))
        assert adv == ([] if want is None else [want]), (text, adv)


def test_message_parse_mileage_next_to_baht_is_dropped():
    t = _topic()
    rec = []
    parse = {"Total 2,290 bath": {"type": "event", "event_type": "other", "mileage": "2290", "works": []},
             "пробег 45203": {"type": "event", "event_type": "other", "mileage": "45203", "works": []}}
    with _patch(S, _after_mileage=_doors(rec)["_after_mileage"], _km_door=lambda *a, **k: ([], None)):
        _sent, br = _photo(_Msg(text="Total 2,290 bath", topic=t), _Claude(parse=parse))
        _sent2, br2 = _photo(_Msg(text="пробег 45203", topic=_topic()), _Claude(parse=parse))
    assert ("after", "2290") not in rec and all(r.get("mileage") != "2290" for r in br.events()), (rec, br.events())
    assert ("after", "45203") in rec, rec                                    # близнец: настоящий пробег идёт


def test_oil_backdated_and_correction_ignore_money():
    assert S.detect_oil_backdated_km("Замена масла была на 1200 бат") is None
    assert S.detect_oil_backdated_km("Замена масла была на 24500") == 24500
    assert S.detect_mileage_correction("нет, не 980, а 1200 бат") is None


# ============================================================================================================
#  (E) ПРОСЬБА О ЧЕКЕ — ОДНА СТРОКА, РАЗ НА ВИЗИТ
# ============================================================================================================
def _summary(t, **acc_fields):
    acc = S._summary_acc(CHAT, t)
    acc.update(acc_fields)
    ctx = _Ctx()
    asyncio.run(S._emit_summary(ctx, CHAT, t, BIKE_X))
    return ctx.bot.sent[-1]["text"] if ctx.bot.sent else ""


def test_written_work_summary_asks_once_per_topic_day():
    t = _topic()
    first = _summary(t, works=["замена колодок"], works_km="45203")
    assert first.count(RU_ASK) == 1 and first.count(C.ASK[0]) == 1, first
    assert first.index(C.ASK[0]) < first.index("🇷🇺"), first               # тайская строка — в тайском блоке
    second = _summary(t, works=["регулировка цепи"], works_km="45210")
    assert RU_ASK not in second and C.ASK[0] not in second, second          # партия того же визита — молча
    other = _summary(_topic(), works=["замена колодок"])
    assert RU_ASK in other, other                                           # другая тема — свой визит


def test_mileage_only_summary_does_not_ask_and_known_cost_does_not_ask():
    t = _topic()
    only_km = _summary(t, current_km="45203", oil={"km": 45203, "next": 48000, "status": "ok"})
    assert only_km and RU_ASK not in only_km, only_km
    assert RU_ASK in _summary(t, works=["замена колодок"]), "просьба не потрачена сводкой пробега"
    t2 = _topic()
    S._svc_rcpt_known(CHAT, t2, 1340)
    assert RU_ASK not in _summary(t2, works=["замена колодок"])
    t3 = _topic()
    assert RU_ASK in _summary(t3, oil={"km": 45203, "next": 48000, "status": "ok"}, oil_written=True)


def test_work_receipt_without_km_carries_ask():
    t = _topic()
    text = "заменил передние колодки"
    cl = _Claude(parse={text: {"type": "event", "event_type": "repair", "mileage": None,
                               "works": ["замена передних колодок"]}})
    with _patch(S, _odo_known_fresh=lambda *a, **k: {"use": False, "why": "тест"}):
        sent, _br = _photo(_Msg(text=text, topic=t), cl)
    body = [x for x in _texts(sent) if "Принял работы" in x]
    assert body and body[0].rstrip().endswith(RU_ASK) and C.ASK[0] in body[0], _texts(sent)


def test_phase2_receipt_written_carries_ask():
    t = _topic()

    async def _done(*a, **k):
        return (["pads"], [])
    sp = {"status": "ждёт_подтверждения", "done": "pads", "note": ""}
    ctx = _Ctx()
    with _patch(S, _sp_open=lambda *a, **k: sp, _sp_write_done=_done):
        took = asyncio.run(S.handle_service_result(_Msg(text="45203", topic=t, user="Pleummmm"), ctx,
                                                   _bridge(), _Claude(), "45203"))
    assert took is True and ctx.bot.sent, "доверенное число вместо кнопки — квитанция"
    body = ctx.bot.sent[-1]["text"]
    assert "✅ Записано" in body and body.rstrip().endswith(RU_ASK), body


# ============================================================================================================
#  (F) ЧИТАТЕЛИ И ПРОВОДКА
# ============================================================================================================
def test_card_history_skips_receipt_rows():
    items = [{"event_type": "чек", "notes": "чек X 01.10.2026: шина — 5600 км"},   # даже если бы форма совпала
             {"event_type": "repair", "notes": "замена колодок — 45203 км"}]
    assert S._parse_service_items(items) == [{"work": "замена колодок", "km": "45203"}]
    import bike_position
    assert bike_position.events_from_items([{"event_type": "чек", "notes": NOTE_XADV,
                                             "recorded_at": "2026-10-01T04:19:00Z"}]) == []


def test_bot_calls_cost_door_before_decider_and_phase2():
    src = open(os.path.join(os.path.dirname(os.path.abspath(S.__file__)), "bot.py"), encoding="utf-8").read()
    i = src.find("splinter.handle_service_cost(msg, context, bridge)")
    j = src.find("await splinter.decider_live(msg, context, bridge, claude)")
    k = src.find("splinter.handle_service_result(msg, context, bridge, claude, msg.text)")
    assert 0 < i < j < k, (i, j, k)


# ============================================================================================================
#  (G) РУЧКА ОТКАТА
# ============================================================================================================
def test_flag_off_is_old_path():
    with _env(SVC_RECEIPT="0"):
        t = _topic()
        cl = _Claude(bike={"kind": "receipt"}, receipt=RC_XADV)
        _sent, br = _photo(_Msg(topic=t, photo_uid="AgADoff"), cl)
        assert S.VISION_SERVICE_RECEIPT not in cl.systems and br.events("чек") == [], br.events()
        took, _s, br2 = _cost(_Msg(text="итого 1340 бат", topic=t))
        assert took is False and br2.events() == []
        assert RU_ASK not in _summary(_topic(), works=["замена колодок"])
        rec = []
        S._PENDING_MILEAGE[(CHAT, t)] = ("41973", BIKE_X, None, False, time.time())
        with _patch(S, **_doors(rec)):
            asyncio.run(S.handle_mileage_confirm(_Msg(text="Total 2,290 bath", topic=t), _Ctx(), _bridge(),
                                                 "Total 2,290 bath"))
        S._PENDING_MILEAGE.pop((CHAT, t), None)
        assert ("odo", "2290") in rec, rec          # прежнее поведение (ровно тот класс, что снимает ручка вкл.)


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
