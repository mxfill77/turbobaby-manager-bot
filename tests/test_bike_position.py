"""ПОЛОЖЕНИЕ БАЙКА: СОВЕТ «ПОМЫТЬ» ТОЛЬКО ПОСЛЕ ВОЗВРАТА (25.09.2026, задание Штаба 0033-74b.2509).

Слово владельца 25.09: совет C («помыть, воск, чехол») звучит только когда байк на базе после
возврата и ещё не помыт; в аренде, в ремонте, перед выдачей и при неизвестном положении — молчит.
Фраза тревоги J «если это возврат — посмотри по депозиту» — тоже только на возврате.

Предмет — пять вещей:
  1  РЕШЕНИЕ `bike_position.position` — порядок силы, цикл возврата, мойка после цикла, три исхода
     там, где источник не прочитан; чистота (импорты ровно `re` и `work_intent`);
  2  СЛОВА — мойка («помыл», «washed», «ล้างแล้ว») против просьбы («помыть»), вопроса и отрицания;
  3  РЕПЛЕЙ ЗАМЕРА — 11 советов C окна 11.09–25.09 по журнальным ногам: ни один не ВОЗВРАТ;
  4  ЖИВОЙ `splinter.handle` — VULCAN 21.09 (работы приняты, байк разобран) без C и без депозита
     в J; аренда — без C; возврат — C один раз, повтор молчит (и через 30 ч тоже); «помыл» — C нет
     до следующего возврата; выдача сегодня — без C; неизвестно — без C и без слова пола;
  5  РУЧКА `BIKE_POSITION=0` — прежний путь: прежний промпт снимка, C по картинке, фраза о депозите,
     ни одного чтения положения, ни строки мойки, ни сегмента «положение» в строке событий.

Сеть, Telegram, мост и модель — заглушки. Мост-заглушка ПОМНИТ свои строки «событий» и отдаёт их
чтением (`read_events`), как живой лист, — иначе история возврата/мойки не судилась бы вовсе.
Фразы — пересказ классов, не цитаты переписки. Память замков и журналов — во временном каталоге.
"""
import ast
import asyncio
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # дерево, которое судим
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NEVER_SILENT"] = "1"        # боевые дефолты ЯВНО: сьют не зависит от файла настроек
os.environ["FLOOR_QUIET"] = "1"
os.environ["WORK_INTENT"] = "1"
os.environ["CAPTION_INTAKE"] = "1"
os.environ["BIKE_POSITION"] = "1"
os.environ.pop("POS_SERVICE_H", None)
_TMP = tempfile.mkdtemp(prefix="tb_bike_position_")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import bike_position as P    # noqa: E402
import splinter as S         # noqa: E402

H = 3600.0
BIKE = "VULCAN 650 S 5065"          # байк живого случая 21.09 (имя байка — не переписка)
_TOPIC = [9100]


def _topic():
    _TOPIC[0] += 1
    return _TOPIC[0]


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


def _loc(epoch):
    """Секунды эпохи → строка CRM 'YYYY-MM-DD HH:MM' в поясе таблицы (+7)."""
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(epoch + P.TZ_H * 3600))


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(epoch))


# ============================================================================================
#  (1) РЕШЕНИЕ — чистое
# ============================================================================================
NOW = 1790318669.0      # 25.09.2026 06:44:29 UTC — совет C по 5065 из замера


def _f(**kw):
    base = {"now": NOW, "service_h": 10, "svc_marks": [], "events": [], "rentals": [],
            "open_request": False, "fleet_status": "ДОМА"}
    base.update(kw)
    return base


def test_module_is_pure():
    src = open(os.path.join(ROOT, "bike_position.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    assert names == {"re", "work_intent"}, names
    for bad in ("open(", "requests", "subprocess", "bridge", "time.time", "os.getenv"):
        assert bad not in src.replace("bridge_client", ""), bad


def test_states_are_six_and_named():
    assert P.STATES == ("возврат", "в аренде", "ремонт", "выдача", "помыт", "неизвестно")


def test_unknown_when_sources_are_silent_and_names_unread():
    p = P.position(_f(events=None, rentals=None, open_request=None, fleet_status=None))
    assert p["state"] == P.UNKNOWN and "CRM" in p["why"] and "события" in p["why"], p
    assert not P.may_advise_wash(p) and not P.deposit_phrase(p)


def test_decision_never_raises():
    for bad in (None, {}, {"now": "x"}, {"now": NOW, "rentals": "мусор", "events": [None, 5]},
                {"now": NOW, "service_h": "abc", "svc_marks": ["x"]}):
        p = P.position(bad)
        assert p["state"] in P.STATES, (bad, p)


def test_message_order_wash_return_handover_service():
    assert P.position(_f(msg_wash=True, msg_return=True))["state"] == P.WASHED
    assert P.position(_f(msg_return=True, msg_handover=True, msg_service=True))["state"] == P.RETURN
    assert P.position(_f(msg_handover=True, msg_service=True))["state"] == P.ISSUE
    assert P.position(_f(msg_service=True))["state"] == P.REPAIR
    assert P.position(_f(msg_disassembled=True))["state"] == P.REPAIR


def test_service_window_n_from_measurement():
    assert P.SERVICE_H_DEFAULT == 10.0
    assert P.position(_f(svc_marks=[NOW - 1.4 * H]))["state"] == P.REPAIR       # VULCAN 21.09: 82 мин
    assert P.position(_f(svc_marks=[NOW - 9.9 * H]))["state"] == P.REPAIR
    assert P.position(_f(svc_marks=[NOW - 15.3 * H]))["state"] != P.REPAIR     # следующая сессия
    assert P.position(_f(svc_marks=[NOW - 96.4 * H]))["state"] == P.UNKNOWN    # VULCAN 25.09
    # своя строка работ из «событий» — тот же сигнал, что память (переживает рестарт)
    assert P.position(_f(events=[{"type": "service", "at": NOW - 2 * H}]))["state"] == P.REPAIR
    assert P.position(_f(open_request=True))["state"] == P.REPAIR
    assert P.position(_f(fleet_status="В ремонте"))["state"] == P.REPAIR


def test_rent_and_crm_lag_after_own_return():
    rent = [{"status": "в аренде", "start": NOW - 72 * H, "end": NOW + 48 * H, "id": "b-1"}]
    assert P.position(_f(rentals=rent))["state"] == P.RENT
    assert P.position(_f(rentals=[], fleet_status="В аренде"))["state"] == P.RENT
    # CRM ещё «В аренде», а свой след возврата новее её начала — CRM запаздывает за людьми
    ev = [{"type": "return", "at": NOW - 1 * H}]
    p = P.position(_f(rentals=rent, events=ev))
    assert p["state"] == P.RETURN and p["cycle"] == "аренда b-1", p


def test_issue_today_or_tomorrow():
    for dh in (1, 20):
        b = [{"status": "бронь", "start": NOW + dh * H, "end": NOW + 100 * H, "id": "b-9"}]
        assert P.position(_f(rentals=b))["state"] == P.ISSUE, dh
    far = [{"status": "бронь", "start": NOW + 80 * H, "end": NOW + 100 * H, "id": "b-9"}]
    assert P.position(_f(rentals=far))["state"] == P.UNKNOWN
    assert P.position(_f(events=[{"type": "handover", "at": NOW - 2 * H}]))["state"] == P.ISSUE


def test_history_return_today_or_yesterday_only():
    done = lambda end: [{"status": "завершена", "start": end - 96 * H, "end": end, "id": "b-2"}]
    assert P.position(_f(rentals=done(NOW - 3 * H)))["state"] == P.RETURN
    assert P.position(_f(rentals=done(NOW - 60 * H)))["state"] == P.UNKNOWN     # не сегодня/вчера
    assert P.position(_f(events=[{"type": "return", "at": NOW - 5 * H}]))["state"] == P.RETURN
    assert P.position(_f(events=[{"type": "return", "at": NOW - 80 * H}]))["state"] == P.UNKNOWN


def test_one_cycle_for_word_and_crm_of_the_same_return():
    rent = [{"status": "в аренде", "start": NOW - 72 * H, "end": NOW, "id": "b-3"}]
    by_word = P.position(_f(rentals=rent, msg_return=True))
    closed = [dict(rent[0], status="завершена")]
    by_crm = P.position(_f(rentals=closed, now=NOW + 2 * H))
    assert by_word["state"] == by_crm["state"] == P.RETURN
    assert by_word["cycle"] == by_crm["cycle"] == "аренда b-3", (by_word, by_crm)
    assert P.hint_state(by_word) == P.hint_state(by_crm)


def test_wash_after_cycle_start_means_washed_until_next_return():
    rent = [{"status": "завершена", "start": NOW - 72 * H, "end": NOW - 4 * H, "id": "b-4"}]
    washed = [{"type": "wash", "at": NOW - 1 * H}]
    assert P.position(_f(rentals=rent, events=washed))["state"] == P.WASHED
    assert P.position(_f(rentals=rent, events=washed, msg_return=True))["state"] == P.WASHED
    nxt = rent + [{"status": "в аренде", "start": NOW - 0.5 * H, "end": NOW, "id": "b-5"}]
    p = P.position(_f(rentals=nxt, events=washed, msg_return=True))
    assert p["state"] == P.RETURN and p["cycle"] == "аренда b-5", p


def test_cycle_without_crm_is_the_local_day():
    p = P.position(_f(rentals=None, msg_return=True))
    assert p["state"] == P.RETURN and p["cycle"] == "день 2026-09-25", p


def test_times_from_living_formats():
    assert P.when("2026-09-25T06:44:41.524Z") == 1790318681
    assert P.when("2026-09-25 13:44") == 1790318640               # CRM, пояс таблицы +7
    assert P.when("25.09.2026 , 13:44") == 1790318640
    assert P.when("25.09.2026") == P.when("2026-09-25")
    assert P.when("Fri Sep 25 2026 13:44:41 GMT+0700 (Indochina Time)") == 1790318681
    assert P.when("") is None and P.when("мусор") is None and P.when(None) is None
    assert P.day_label(NOW) == "2026-09-25" and P.day_label(P.when("2026-12-31 23:59")) == "2026-12-31"


def test_events_mapping_and_own_return_mark():
    items = [{"event_type": "wash", "notes": "мойка: «…»", "recorded_at": "2026-09-25T06:00:00Z"},
             {"event_type": "photo", "notes": "x | " + P.RETURN_MARK, "recorded_at": "2026-09-25T05:00:00Z"},
             {"event_type": "photo", "notes": "положение: возврат (CRM)", "recorded_at": "2026-09-25T04:00:00Z"},
             {"event_type": "repair", "notes": "колодки", "recorded_at": "2026-09-25T03:00:00Z"},
             {"event_type": "handover", "notes": "", "msg_date": "2026-09-24"},
             {"event_type": "photo", "notes": "грязный", "recorded_at": "2026-09-25T02:00:00Z"},
             {"event_type": "return", "notes": "", "recorded_at": ""}]
    got = [e["type"] for e in P.events_from_items(items)]
    assert got == ["wash", "return", "service", "handover"], got   # производный возврат — не след
    assert P.note({"state": P.RETURN, "src": P.SRC_MSG}) == P.RETURN_MARK


def test_rentals_from_crm_rows():
    rows = [{"status": "В аренде", "date_start": "2026-09-22 10:00", "date_end": "2026-09-25 17:30",
             "booking_id": "uuid-1", "row": 700},
            {"status": "Отмена", "date_start": "2026-09-01 10:00"},
            {"status": "Завершена", "date_start": "01.09.2026 10:00", "date_end": "05.09.2026", "row": 650}]
    r = P.rentals_from_rows(rows)
    assert [x["status"] for x in r] == ["в аренде", "завершена"], r
    assert r[0]["id"] == "uuid-1" and r[1]["id"] == "строка 650", r


# ============================================================================================
#  (2) СЛОВА
# ============================================================================================
def test_wash_words():
    for yes in ("помыл", "Помыли байк", "помыта", "вымыл", "washed", "washing done",
                "ล้างแล้ว", "ล้างรถแล้วครับ", "мойка сделана", "помыл и поменял масло"):
        assert P.wash_said(yes), yes
    for no in ("помыть", "надо помыть", "не помыл", "ещё не помыт", "помыл?", "not washed yet",
               "ยังไม่ล้าง", "ต้องล้าง", "", None, "ล้างกระบอกสูบ", "мыло"):
        assert not P.wash_said(no), no


def test_service_words_and_fuel_is_not_service():
    for yes in ("замена колодок", "разобрал вилку", "поменял масло", "не работает поворотник",
                "repair", "changed tire", "ซ่อม", "เปลี่ยนยาง", "ถอดล้อ", "เสีย"):
        assert P.service_said(yes), yes
    for no in ("น้ำมันเต็ม", "бак полный", "стоит на парковке", "ok", "", None, "เสียงดัง"):
        assert not P.service_said(no), no


# ============================================================================================
#  (3) РЕПЛЕЙ ЗАМЕРА — 11 советов C окна 11.09 13:25 → 25.09 13:25 UTC (журнальные ноги)
# ============================================================================================
#: (UTC, байк, отправлен?, сервис в теме до, ч; сервис в самом сообщении). Снято скриптом замера
#: `tmp/pomyt_sost_2509/zamer.py` по живому splinter.log; CRM на момент совета не восстановим.
_MEASURED = [
    ("12.09 06:07", "4685", True, None, False),
    ("12.09 07:56", "4957", True, 1.43, False),
    ("15.09 09:15", "7530", True, None, False),
    ("21.09 06:16", "5065", True, 1.365, False),
    ("21.09 06:17", "5065", False, 1.384, False),
    ("23.09 07:24", "4255", True, 2052.4, False),
    ("23.09 07:28", "4255", False, 2052.5, False),
    ("23.09 07:39", "4255", False, 2052.7, False),
    ("23.09 08:46", "4255", False, 2053.8, False),
    ("24.09 07:09", "2478", True, None, True),     # подпись-указание 12105 («Need to change»)
    ("25.09 06:44", "5065", True, 96.394, False),
]


def test_replay_of_the_measurement_keeps_no_advice():
    got = {}
    for at, plate, sent, svc_h, msg_svc in _MEASURED:
        marks = [NOW - svc_h * H] if svc_h is not None else []
        p = P.position(_f(svc_marks=marks, msg_service=msg_svc, events=None, rentals=None,
                          open_request=None, fleet_status=None))
        got.setdefault(p["state"], 0)
        got[p["state"]] += 1
        assert not P.may_advise_wash(p), (at, plate, p)
    assert got == {P.REPAIR: 4, P.UNKNOWN: 7}, got


# ============================================================================================
#  Заглушки мира для живого `splinter.handle`
# ============================================================================================
class _Bot:
    username = "tb_position_test_bot"

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
    def __init__(self, username="testmech", is_bot=False):
        self.id, self.username, self.is_bot, self.first_name = 99005, username, is_bot, "T"


class _Msg:
    def __init__(self, text="", photo=False, caption=None, mid=20000, topic=None):
        self.chat_id = _chat_servicing()
        self.text = text or None
        self.caption = caption
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic
        self.date = None
        self.from_user = _User()
        self.reply_to_message = None
        self.media_group_id = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _World:
    """Мост-заглушка с памятью: строки «событий» пишутся `add_event` и читаются `read_events`
    (newest-first, как живой лист). CRM — `rows`, парк — `fleet`, заявка — `open_req`.
    `shift` — сдвиг времени записи новых строк (секунды): так строится «мойка два часа назад»."""

    def __init__(self, rows=None, fleet=None, open_req=None):
        self.rows, self.fleet, self.open_req = list(rows or []), fleet, open_req
        self.events, self.calls, self.shift = [], [], 0.0

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append((name, dict(kw), a))
            return {"ok": True, "items": [], "saved": True}
        return _any

    def add_event(self, **kw):
        self.calls.append(("add_event", dict(kw), ()))
        if any(e["msg_id"] == kw.get("msg_id") for e in self.events):
            return {"ok": True, "duplicate": True}
        self.events.append({"event_type": kw.get("event_type", ""), "notes": kw.get("notes", ""),
                            "mileage": kw.get("mileage", ""), "msg_id": kw.get("msg_id", ""),
                            "recorded_at": _iso(time.time() + self.shift), "msg_date": ""})
        return {"ok": True, "saved": True}

    def read_events(self, bike, limit=8):
        self.calls.append(("read_events", {"bike": bike, "limit": limit}, ()))
        return {"ok": True, "bike": bike, "items": list(reversed(self.events))[:limit]}

    def _call(self, action, **kw):
        self.calls.append(("_call", dict(kw, action=action), ()))
        if action == "clients":
            return {"ok": True, "data": {"clients": list(self.rows)}}
        return {"ok": True, "data": {}}

    def find_bike(self, q):
        self.calls.append(("find_bike", {"q": q}, ()))
        return {"name": BIKE, "status": self.fleet} if self.fleet is not None else {}

    def service_pending_get(self, *a, **kw):
        self.calls.append(("service_pending_get", dict(kw), a))
        if self.open_req:
            return {"ok": True, "item": {"status": "ждёт_факт", "declared": "other"}}
        return {"ok": False, "error": "not_found"}


class _Claude:
    def __init__(self, parse=None, vision=None):
        self.parse, self.vision_q, self.systems = parse, list(vision or []), []

    def quick(self, system, *a, **kw):
        if system is S.SERVICING_SYSTEM:
            if self.parse is None:
                return ""
            return self.parse if isinstance(self.parse, str) else json.dumps(self.parse)
        return ""

    def vision(self, system, *a, **kw):
        self.systems.append(system)
        v = self.vision_q.pop(0) if self.vision_q else {}
        return v if isinstance(v, str) else json.dumps(v)


CHAT = {"type": "none", "event_type": None, "mileage": None, "works": []}
DIRTY = {"kind": "bike", "dirt": True, "damage": None, "fuel": None, "mileage": None, "notes": "байк"}


def _fresh_hints():
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None


def _run(msg, claude, world, knob="1"):
    prev = os.environ.get("BIKE_POSITION")
    os.environ["BIKE_POSITION"] = knob
    ctx = _Ctx()
    saved = (S.bike_from_topic, S._download_photo)
    S.bike_from_topic = lambda *a, **k: BIKE

    async def _dl(pm):
        return b"\xff\xd8 test"
    S._download_photo = _dl
    try:
        asyncio.run(S.handle(_Upd(msg), ctx, world, claude))
    finally:
        S.bike_from_topic, S._download_photo = saved
        os.environ["BIKE_POSITION"] = prev if prev is not None else "1"
    return [s.get("text", "") for s in ctx.bot.sent]


def _c(texts):
    return [t for t in texts if "🧽" in t]


def _rows(world, et=None):
    return [kw for n, kw, _ in world.calls if n == "add_event" and (et is None or kw.get("event_type") == et)]


def _reads(world):
    return [n for n, _, _ in world.calls if n in ("read_events", "_call", "find_bike", "service_pending_get")]


# ============================================================================================
#  (4) ЖИВОЙ `splinter.handle`
# ============================================================================================
def test_vulcan_21_09_replay_works_accepted_bike_disassembled_no_c_no_deposit():
    """21.09: 04:54 бот принял работы → 05:04 J про депозит на колодки → 06:16 C «помой и накрой»
    по снимку разобранного байка. Теперь: J без депозита, C нет, пол молчит."""
    _fresh_hints()
    t, w = _topic(), _World(fleet="ДОМА")
    works = {"type": "event", "event_type": "repair", "bike": BIKE, "mileage": None,
             "works": ["замена передних тормозных колодок", "замена поворотников"]}
    first = _run(_Msg("поменял передние колодки и поворотники", mid=11980, topic=t), _Claude(works), w)
    assert any("Принял" in x or "รับ" in x for x in first), first        # работы приняты, как было
    key = (_chat_servicing(), t)
    assert S._POS_SVC_MARKS.get(key), "сервис темы записан в память"
    S._POS_SVC_MARKS[key] = [x - 10 * 60 for x in S._POS_SVC_MARKS[key]]     # +10 мин: 05:04
    j = _run(_Msg(photo=True, mid=11985, topic=t),
             _Claude(None, vision=[{"kind": "other", "damage": "изношенные колодки", "dirt": False}]), w)
    assert len(j) == 1 and "повреждения" in j[0] and "депозит" not in j[0], j
    S._POS_SVC_MARKS[key] = [x - 72 * 60 for x in S._POS_SVC_MARKS[key]]     # +82 мин: 06:16
    for i, v in enumerate(({"kind": "bike", "dirt": True, "disassembled": True},
                           {"kind": "bike", "dirt": True},
                           {"kind": "other", "dirt": True})):
        sent = _run(_Msg(photo=True, mid=11994 + i, topic=t), _Claude(None, vision=[v]), w)
        assert _c(sent) == [] and sent == [], (i, sent)                     # ни совета, ни пола
    photo_rows = [r for r in _rows(w) if r.get("event_type") == "photo"]
    assert photo_rows and all("положение: ремонт" in r["notes"] for r in photo_rows), photo_rows
    assert all("грязный" in r["notes"] for r in photo_rows if "повреждения" not in r["notes"])


def test_vulcan_after_restart_repair_row_in_events_still_silences():
    """Память процесса стёрта рестартом — решает своя строка работ в «событиях»."""
    _fresh_hints()
    t, w = _topic(), _World(fleet="ДОМА")
    w.events.append({"event_type": "repair", "notes": "колодки — 36474 км", "msg_id": "x:1",
                     "recorded_at": _iso(time.time() - 3 * H), "msg_date": ""})
    sent = _run(_Msg(photo=True, mid=12001, topic=t), _Claude(None, vision=[dict(DIRTY)]), w)
    assert _c(sent) == [], sent
    assert "положение: ремонт" in _rows(w, "photo")[-1]["notes"]


def test_bike_in_rent_gets_no_c():
    _fresh_hints()
    now = time.time()
    w = _World(rows=[{"status": "В аренде", "bike": BIKE, "date_start": _loc(now - 48 * H),
                      "date_end": _loc(now + 72 * H), "booking_id": "b-rent", "row": 700}], fleet="В аренде")
    sent = _run(_Msg(photo=True, mid=12010, topic=_topic()), _Claude(None, vision=[dict(DIRTY)]), w)
    assert _c(sent) == [], sent
    assert "положение: в аренде" in _rows(w, "photo")[-1]["notes"]


def _return_world():
    now = time.time()
    return _World(rows=[{"status": "В аренде", "bike": BIKE, "date_start": _loc(now - 72 * H),
                         "date_end": _loc(now), "booking_id": "b-1", "row": 701}], fleet="В аренде")


def test_return_with_dirt_gives_c_once_and_repeat_is_silent_even_after_30h():
    _fresh_hints()
    t, w = _topic(), _return_world()
    first = _run(_Msg(photo=True, caption="клиент вернул байк", mid=12020, topic=t),
                 _Claude(CHAT, vision=[dict(DIRTY)]), w)
    assert len(_c(first)) == 1, first
    assert S.bike_position.RETURN_MARK in _rows(w, "photo")[-1]["notes"]
    second = _run(_Msg(photo=True, mid=12021, topic=t), _Claude(None, vision=[dict(DIRTY)]), w)
    assert _c(second) == [], second                     # тот же цикл аренды b-1 — повтор
    for rec in (S._HINT_SEEN or {}).values():           # «прошло 30 ч» — права на повтор нет
        rec["ts"] = rec["ts"] - 30 * H
    third = _run(_Msg(photo=True, caption="вернул", mid=12022, topic=t),
                 _Claude(CHAT, vision=[dict(DIRTY)]), w)
    assert _c(third) == [], third


def test_after_washed_no_c_until_next_return():
    _fresh_hints()
    t, w = _topic(), _return_world()
    assert len(_c(_run(_Msg(photo=True, caption="клиент вернул байк", mid=12030, topic=t),
                       _Claude(CHAT, vision=[dict(DIRTY)]), w))) == 1
    w.shift = -2 * H                                   # мойка два часа назад
    said = _run(_Msg("помыл", mid=12031, topic=t), _Claude(CHAT), w)
    w.shift = 0.0
    assert said == [], said                            # строка мойки легла, пол молчит
    wash = _rows(w, "wash")
    assert len(wash) == 1 and wash[0]["msg_id"].endswith(":wash"), wash
    for cap in (None, "вернул"):
        sent = _run(_Msg(photo=True, caption=cap, mid=12032 if cap is None else 12033, topic=t),
                    _Claude(CHAT if cap else None, vision=[dict(DIRTY)]), w)
        assert _c(sent) == [], (cap, sent)             # помыт после начала цикла — молчим
    now = time.time()
    w.rows = [dict(w.rows[0], status="Завершена"),
              {"status": "В аренде", "bike": BIKE, "date_start": _loc(now - 1 * H),
               "date_end": _loc(now), "booking_id": "b-2", "row": 702}]
    nxt = _run(_Msg(photo=True, caption="клиент вернул байк", mid=12034, topic=t),
               _Claude(CHAT, vision=[dict(DIRTY)]), w)
    assert len(_c(nxt)) == 1, nxt                      # следующий возврат — новый цикл


def test_wash_caption_on_photo_is_washed_not_advice():
    _fresh_hints()
    t, w = _topic(), _return_world()
    sent = _run(_Msg(photo=True, caption="washed", mid=12040, topic=t), _Claude(CHAT, vision=[dict(DIRTY)]), w)
    assert _c(sent) == [] and len(_rows(w, "wash")) == 1, sent


def test_issue_today_gets_no_c():
    _fresh_hints()
    now = time.time()
    w = _World(rows=[{"status": "Бронь", "bike": BIKE, "date_start": _loc(now + 2 * H),
                      "date_end": _loc(now + 50 * H), "booking_id": "b-issue", "row": 703}], fleet="ДОМА")
    sent = _run(_Msg(photo=True, mid=12050, topic=_topic()), _Claude(None, vision=[dict(DIRTY)]), w)
    assert _c(sent) == [], sent
    assert "положение: выдача" in _rows(w, "photo")[-1]["notes"]


def test_unknown_gets_no_c_and_no_floor_word():
    _fresh_hints()
    w = _World(fleet="ДОМА")
    sent = _run(_Msg(photo=True, mid=12060, topic=_topic()), _Claude(None, vision=[dict(DIRTY)]), w)
    assert sent == [], sent
    assert "положение: неизвестно" in _rows(w, "photo")[-1]["notes"]


def test_neutral_captions_on_return_still_get_c():
    """Близнец прежнего `test_dirty_photo_with_neutral_caption_still_gets_c` — на возврате."""
    for cap in ("ok", "👍", "@someone_else", "стоит на парковке", "nice weather today"):
        _fresh_hints()
        t, w = _topic(), _return_world()
        w.events.append({"event_type": "photo", "notes": S.bike_position.RETURN_MARK, "msg_id": "y:1",
                         "recorded_at": _iso(time.time() - 60), "msg_date": ""})
        sent = _run(_Msg(photo=True, caption=cap, mid=12070, topic=t), _Claude(CHAT, vision=[dict(DIRTY)]), w)
        assert len(_c(sent)) == 1, (cap, sent)


def test_alarm_j_on_return_keeps_the_deposit_phrase():
    _fresh_hints()
    t, w = _topic(), _return_world()
    sent = _run(_Msg(photo=True, caption="клиент вернул байк", mid=12080, topic=t),
                _Claude(CHAT, vision=[{"kind": "other", "damage": "трещина на пластике", "dirt": True}]), w)
    j = [x for x in sent if "повреждения" in x]
    assert len(j) == 1 and "Если это возврат — посмотри по депозиту" in j[0], sent
    assert _c(sent) == [], "повреждение идёт тревогой J, совет C не добавляется"


def test_position_is_not_read_when_nothing_depends_on_it():
    _fresh_hints()
    w = _World(fleet="ДОМА")
    _run(_Msg(photo=True, mid=12090, topic=_topic()), _Claude(None, vision=[{"kind": "wheel", "dirt": False}]), w)
    assert _reads(w) == [], w.calls


# ============================================================================================
#  (5) РУЧКА `BIKE_POSITION=0` — прежний путь
# ============================================================================================
def test_knob_reads_like_its_neighbours():
    for off in ("0", "", "нет", "no", "off", " 0 "):
        os.environ["BIKE_POSITION"] = off
        assert S._bike_position_on() is False, repr(off)
    for on in ("1", "yes", "да"):
        os.environ["BIKE_POSITION"] = on
        assert S._bike_position_on() is True, repr(on)
    os.environ["BIKE_POSITION"] = "1"


def test_prompt_with_disassembled_only_when_knob_on():
    assert "disassembled" in S.VISION_BIKE_SYSTEM_POS and "disassembled" not in S.VISION_BIKE_SYSTEM
    assert S.VISION_BIKE_SYSTEM_POS.startswith(S.VISION_BIKE_SYSTEM.split("  disassembled")[0][:200])
    extra = S.VISION_BIKE_SYSTEM_POS.replace(S.VISION_BIKE_SYSTEM.split("  notes:")[0], "", 1)
    assert extra.startswith("  disassembled:"), extra[:80]
    _fresh_hints()
    on, off = _Claude(None, vision=[dict(DIRTY)]), _Claude(None, vision=[dict(DIRTY)])
    _run(_Msg(photo=True, mid=12100, topic=_topic()), on, _World(fleet="ДОМА"))
    _run(_Msg(photo=True, mid=12101, topic=_topic()), off, _World(fleet="ДОМА"), knob="0")
    assert on.systems == [S.VISION_BIKE_SYSTEM_POS] and off.systems == [S.VISION_BIKE_SYSTEM]


def test_knob_off_is_the_old_path():
    """Выкл: C по картинке, фраза о депозите в ремонте, ни чтения положения, ни строки мойки,
    ни сегмента «положение», память темы не пишется."""
    _fresh_hints()
    t, w = _topic(), _World(fleet="ДОМА")
    sent = _run(_Msg(photo=True, mid=12110, topic=t), _Claude(None, vision=[dict(DIRTY)]), w, knob="0")
    assert sent == [S.msg_dirty_care(BIKE)], sent
    works = {"type": "event", "event_type": "repair", "bike": BIKE, "mileage": None,
             "works": ["замена передних тормозных колодок"]}
    _run(_Msg("поменял колодки", mid=12111, topic=t), _Claude(works), w, knob="0")
    j = _run(_Msg(photo=True, mid=12112, topic=t),
             _Claude(None, vision=[{"kind": "other", "damage": "скол", "dirt": False}]), w, knob="0")
    assert len(j) == 1 and "Если это возврат — посмотри по депозиту" in j[0], j
    _run(_Msg("помыл", mid=12113, topic=t), _Claude(CHAT), w, knob="0")
    # чтений ПОЛОЖЕНИЯ нет (свои события и CRM прежний путь в этих случаях не читает вовсе);
    # побайтное равенство с родителем 48ee30a — отдельной сверкой двух деревьев
    assert not [n for n, kw, _ in w.calls if n == "read_events" or (n == "_call" and kw.get("action") == "clients")], w.calls
    assert _rows(w, "wash") == []
    assert not any("положение" in r.get("notes", "") for r in _rows(w))
    assert (_chat_servicing(), t) not in S._POS_SVC_MARKS
    seen = S._hint_load()
    assert any(r.get("fp") == S.hint_dedup.state_fingerprint(("dirt", True)) for r in seen.values()), seen


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
