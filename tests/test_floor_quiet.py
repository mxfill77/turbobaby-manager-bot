"""ПОЛ ОТВЕТА ГОВОРИТ ПО ДЕЛУ, А НЕ НА ВСЁ (24.09.2026, задание Штаба 0027-72f).

Слово владельца: «чтобы не было спама после фото, всё по делу». Замер живого журнала 21–23.09:
пол ответа (`splinter._reply_floor_speak`) заговорил 15 раз — 6 на болтовню, 9 на снимок без
приборки, — и НИ РАЗУ не по делу. Альбом при этом уже склеивался в ОДИН прогон (`bot.py`,
окно 1.8 с): лишним был не «ответ на каждый снимок альбома», а ответ на каждое фото/альбом.

Предмет — четыре вещи, все судятся ЖИВЫМ кодом (`splinter.handle` → `_handle_servicing`):
  1  РЕШЕНИЕ `reply_floor.should_speak` — одностороннее: молчит только при знании «не запись»;
  2  ШУМ МОЛЧИТ — болтовня, тег человека, замечание-событие, снимок без приборки, альбом;
  3  РЕЧЬ ПО ДЕЛУ ОСТАЛАСЬ — не разобрали, упали, приборка без чисел, к боту обратились прямо;
  4  ЗАПИСЬ ЦЕЛА — «принял работы», запись работ с пробегом, вопрос о пробеге с фото приборки,
     альбом с приборкой: ответы и вызовы моста ПОСИМВОЛЬНО равны при ручке вкл и выкл.

Фразы — ПЕРЕСКАЗ живых классов, а не цитаты переписки (переписку наружу не выводим). Сеть,
Telegram и мост замоканы; мост-заглушка отвечает на любое имя и копит СОСТАВ аргументов — имён
боевых операций записи в файле нет. Память замков и журналов уведена во временный каталог.
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
os.environ["NEVER_SILENT"] = "1"        # боевые дефолты ЯВНО: сьют не зависит от файла настроек
os.environ["FLOOR_QUIET"] = "1"
os.environ["WORK_INTENT"] = "1"
_TMP = tempfile.mkdtemp(prefix="tb_floor_quiet_")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import reply_floor as F      # noqa: E402
import splinter as S         # noqa: E402

TOPIC = 7313
BIKE = "TESTBIKE 000ZZ PHUKET 4243"      # такого байка в парке нет


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


# ============================================================================================
#  Заглушки мира
# ============================================================================================
class _Bot:
    username = "tb_floor_test_bot"

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
        self.id, self.username, self.is_bot, self.first_name = 99002, username, is_bot, "T"


class _Msg:
    def __init__(self, text="", photo=False, reply_to=None, caption=None, mid=555, topic=TOPIC):
        self.chat_id = _chat_servicing()
        self.text = text or None
        self.caption = caption
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic
        self.date = None
        self.from_user = _User()
        self.reply_to_message = reply_to
        self.media_group_id = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _Bridge:
    """Отвечает на ЛЮБОЕ имя одинаково; копит (имя, состав аргументов). Имена боевых операций
    записи здесь не пишутся — судим по составу аргументов (приём `test_work_intent`)."""

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
    """Разборщик: текст → заданный вердикт; снимки → заданные разборы по очереди.
    `parse=None` — разбор не дал ничего (как упавшая модель); строка — отдаётся как есть."""

    def __init__(self, parse=None, vision=None):
        self.parse, self.vision_q, self.vision_calls = parse, list(vision or []), 0

    def quick(self, system, *a, **kw):
        if system is S.SERVICING_SYSTEM:
            if self.parse is None:
                return ""
            return self.parse if isinstance(self.parse, str) else json.dumps(self.parse)
        return ""                      # перевод и прочее — «модель молчит», штатный fail-safe

    def vision(self, *a, **kw):
        self.vision_calls += 1
        v = self.vision_q.pop(0) if self.vision_q else {}
        return v if isinstance(v, str) else json.dumps(v)


def _run(msg, claude, *, album=None, quiet="1", download=None):
    """Прогнать ЖИВОЙ `splinter.handle`. Возврат (отправленное, вызовы моста, разборщик)."""
    prev = os.environ.get("FLOOR_QUIET")
    os.environ["FLOOR_QUIET"] = quiet
    ctx, br = _Ctx(), _Bridge()
    saved = (S.bike_from_topic, S._download_photo)
    S.bike_from_topic = lambda *a, **k: BIKE          # тема = байк, без обращения к миру

    async def _dl(pm):
        if download is not None:
            return download(pm)
        return b"\xff\xd8 test"
    S._download_photo = _dl
    try:
        asyncio.run(S.handle(_Upd(msg), ctx, br, claude, album_msgs=album))
    finally:
        S.bike_from_topic, S._download_photo = saved
        os.environ["FLOOR_QUIET"] = prev if prev is not None else "1"
    return ctx.bot.sent, br.calls, claude


def _texts(sent):
    return [s.get("text", "") for s in sent]


def _fresh_hints():
    """Замок подсказок — СВОЙ файл на случай: близнецы не должны делить память повтора."""
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None           # кэш замка: None = «ещё не читали», поднимется с нового файла


CHAT = {"type": "none", "event_type": None, "mileage": None, "works": []}
REMARK = {"type": "event", "event_type": "repair", "mileage": None, "works": [],
          "notes": "замечание о шланге"}


# ============================================================================================
#  (1) РЕШЕНИЕ: одностороннее, чистое
# ============================================================================================
def test_parse_seen_maps_only_two_verdicts():
    assert F.parse_seen({"type": "event"}) == F.PARSE_EVENT
    assert F.parse_seen({"type": "none"}) == F.PARSE_CHATTER
    assert F.parse_seen({"type": "NONE"}) == F.PARSE_CHATTER
    for bad in ({}, None, {"type": None}, {"type": "question"}, "мусор", {"type": 7}):
        assert F.parse_seen(bad) == F.PARSE_FAILED, bad


def test_has_content_ignores_tags_links_and_signs():
    assert not F.has_content("@someone_else")
    assert not F.has_content("@a @b   ")
    assert not F.has_content("🙏 !!! ...")
    assert not F.has_content("https://example.org/x")
    assert F.has_content("@someone ok")
    assert F.has_content("ใช่")                     # тайская буква — буква
    assert F.has_content("25906")


def test_quiet_classes_are_silent():
    quiet = [
        {"parse": F.PARSE_CHATTER, "text": "you ok?"},
        {"parse": F.PARSE_EVENT, "text": "говорят, это шланг"},
        {"parse": F.PARSE_STATUS, "text": "статус"},
        {"parse": F.PARSE_FAILED, "text": "@someone_else"},
        {"parse": F.PARSE_UNKNOWN, "text": "@someone_else"},
    ] + [{"photo": True, "photo_kind": k} for k in ("wheel", "bike", "receipt", "other", "WHEEL")]
    for f in quiet:
        r = F.should_speak(f)
        assert r["speak"] is False, (f, r)
        assert r["why"], f


def test_our_failures_still_speak():
    loud = [
        {"crashed": True, "parse": F.PARSE_CHATTER, "text": "you ok?"},
        {"crashed": True, "photo": True, "photo_kind": "wheel"},
        {"addressed": True, "parse": F.PARSE_CHATTER, "text": "you ok?"},
        {"photo": True, "photo_kind": F.DASHBOARD},
        {"photo": True, "photo_kind": ""},
        {"photo": True, "photo_kind": None},
        {"photo": True, "photo_kind": "неведомое"},
        {"photo": True, "photo_kind": "wheel", "parse": F.PARSE_FAILED, "text": "что это такое"},
        {"parse": F.PARSE_FAILED, "text": "что-то невнятное"},
        {"parse": F.PARSE_UNKNOWN, "text": "что-то невнятное"},
        {"text": "что-то невнятное"},
    ]
    for f in loud:
        assert F.should_speak(f)["speak"] is True, f


def test_decision_never_raises_and_doubt_is_speech():
    for f in (None, {}, {"parse": object()}, {"photo": True, "photo_kind": 5},
              {"text": None}, {"text": 12345}):
        r = F.should_speak(f)
        assert isinstance(r, dict) and "speak" in r, (f, r)


def test_live_window_replay_all_fifteen_are_quiet():
    """ЗАМЕР: 15 срабатываний пола 21–23.09 (журнал splinter, ФАКТЫ без текста переписки).
    До правки говорил каждый — 15 из 15; после — 0 из 15."""
    live = (
        # (снимок, вид снимка, вердикт разбора, есть ли слова)
        (True, "other", "", False), (False, "", "chatter", False), (True, "bike", "", False),
        (True, "other", "", False), (False, "", "event", True), (True, "other", "", False),
        (False, "", "failed", False), (False, "", "chatter", True), (False, "", "chatter", True),
        (True, "bike", "", False), (True, "other", "", False), (False, "", "chatter", True),
        (True, "bike", "", False), (True, "bike", "", False), (True, "wheel", "", False),
    )
    assert len(live) == 15
    photos = sum(1 for x in live if x[0])
    assert photos == 9 and len(live) - photos == 6, "раскладка замера: 9 снимков, 6 текстов"
    spoke = 0
    for photo, kind, parse, words in live:
        f = {"photo": photo, "photo_kind": kind, "parse": parse,
             "text": "слово" if words else "@someone_else"}
        spoke += F.should_speak(f)["speak"]
    assert spoke == 0, f"после правки заговорил бы {spoke} раз из 15"


# ============================================================================================
#  (2) ШУМ МОЛЧИТ — на живом `_handle_servicing`
# ============================================================================================
def test_chatter_gets_no_word():
    for phrase in ("you ok?", "ok", "работаю над темами, скоро станет лучше"):
        sent, _, _ = _run(_Msg(phrase), _Claude(CHAT))
        assert sent == [], (phrase, _texts(sent))


def test_tag_of_a_human_gets_no_word_even_if_parse_failed():
    sent, _, _ = _run(_Msg("@someone_else"), _Claude(None))
    assert sent == [], _texts(sent)


def test_remark_is_written_as_event_and_not_answered():
    """Замечание-событие: строка событий ЛЕГЛА (состав аргументов), а ответа нет. До правки
    бот писал «ничего не записал» — это была неправда."""
    sent, calls, _ = _run(_Msg("говорят, это шланг, откуда — не ясно"), _Claude(REMARK))
    assert sent == [], _texts(sent)
    rows = [kw for _, kw in calls if kw.get("event_type") == "repair" and "notes" in kw]
    assert rows, f"событие не записано: {calls}"


def test_named_photo_gets_no_word():
    for kind in ("wheel", "bike", "other", "receipt"):
        _fresh_hints()
        sent, _, cl = _run(_Msg(photo=True), _Claude(vision=[{"kind": kind}]))
        assert sent == [], (kind, _texts(sent))
        assert cl.vision_calls == 1, kind


def test_album_without_dashboard_gets_no_word_and_every_photo_is_read():
    _fresh_hints()
    album = [_Msg(photo=True, mid=600 + i) for i in range(9)]
    vis = [{"kind": "wheel" if i % 2 else "bike"} for i in range(9)]
    sent, _, cl = _run(album[0], _Claude(vision=vis), album=album)
    assert sent == [], _texts(sent)
    assert cl.vision_calls == 9, "каждый снимок альбома разобран — ничего не потеряно"


def test_album_before_the_fix_was_one_word_not_nine():
    """ЧЕСТНОСТЬ ПРЕМИСЫ: альбом и до правки давал ОДИН ответ, а не девять."""
    _fresh_hints()
    album = [_Msg(photo=True, mid=700 + i) for i in range(9)]
    vis = [{"kind": "wheel"} for _ in range(9)]
    sent, _, _ = _run(album[0], _Claude(vision=vis), album=album, quiet="0")
    assert len(sent) == 1, _texts(sent)


def test_dirty_advice_repeat_does_not_turn_into_a_floor_word():
    """Живой случай 23.09: совет «помыть» подавлен замком повторов → пол говорил «вижу байк
    целиком, напиши о чём». Теперь: совет один раз, повтор — тишина."""
    _fresh_hints()
    v = {"kind": "bike", "dirt": True}
    own = TOPIC + 101        # своя тема: открытый вопрос о пробеге соседнего случая глушит совет
    first, _, _ = _run(_Msg(photo=True, mid=801, topic=own), _Claude(vision=[v]))
    second, _, _ = _run(_Msg(photo=True, mid=802, topic=own), _Claude(vision=[v]))
    assert len(first) == 1 and "🧽" in first[0]["text"], _texts(first)
    assert second == [], _texts(second)


# ============================================================================================
#  (3) РЕЧЬ ПО ДЕЛУ ОСТАЛАСЬ — близнецы
# ============================================================================================
def test_unparsed_words_still_get_an_answer():
    sent, _, _ = _run(_Msg("что-то невнятное про байк"), _Claude("не json"))
    assert len(sent) == 1 and "не понял" in sent[0]["text"], _texts(sent)


def test_chatter_addressed_to_the_bot_still_gets_an_answer():
    bot_msg = type("R", (), {"from_user": _User("tb_floor_test_bot", is_bot=True)})()
    sent, _, _ = _run(_Msg("you ok?", reply_to=bot_msg), _Claude(CHAT))
    assert len(sent) == 1, _texts(sent)


def test_dashboard_without_numbers_still_asks():
    _fresh_hints()
    sent, _, _ = _run(_Msg(photo=True), _Claude(vision=[{"kind": "dashboard"}]))
    assert len(sent) == 1, _texts(sent)
    assert "числа на нём разобрать не смог" in sent[0]["text"], sent[0]["text"]


def test_unreadable_photo_still_says_so():
    _fresh_hints()
    sent, _, _ = _run(_Msg(photo=True), _Claude(vision=[""]))
    assert len(sent) == 1 and "не узнал" in sent[0]["text"], _texts(sent)


def test_crash_still_says_nothing_was_written():
    def boom(pm):
        raise RuntimeError("проба падения")
    sent, _, _ = _run(_Msg(photo=True), _Claude(vision=[{"kind": "wheel"}]), download=boom)
    assert len(sent) == 1 and "НЕ делал" in sent[0]["text"], _texts(sent)


def test_rollback_switch_restores_the_old_floor():
    sent, _, _ = _run(_Msg("you ok?"), _Claude(CHAT), quiet="0")
    assert len(sent) == 1 and "не понял" in sent[0]["text"], _texts(sent)
    _fresh_hints()
    sent2, _, _ = _run(_Msg(photo=True), _Claude(vision=[{"kind": "wheel"}]), quiet="0")
    assert len(sent2) == 1 and "приборки на нём нет" in sent2[0]["text"], _texts(sent2)


def test_witness_of_a_previous_message_does_not_leak():
    """Одна задача, два обновления подряд (так PTB и работает без параллели): вердикт
    «болтовня» первого не имеет права заглушить второе, неразобранное."""
    async def both():
        ctx = _Ctx()
        saved = S.bike_from_topic
        S.bike_from_topic = lambda *a, **k: BIKE
        try:
            await S.handle(_Upd(_Msg("you ok?")), ctx, _Bridge(), _Claude(CHAT))
            await S.handle(_Upd(_Msg("что-то невнятное про байк")), ctx, _Bridge(),
                           _Claude("не json"))
        finally:
            S.bike_from_topic = saved
        return ctx.bot.sent
    sent = asyncio.run(both())
    assert len(sent) == 1 and "не понял" in sent[0]["text"], _texts(sent)


# ============================================================================================
#  (4) ЗАПИСЬ ЦЕЛА — главная функция; ручка вкл и выкл дают ПОСИМВОЛЬНО одно и то же
# ============================================================================================
WORKS_NO_KM = {"type": "event", "event_type": "repair", "mileage": None,
               "works": ["передние тормозные колодки", "задние тормозные колодки"]}
WORKS_KM = {"type": "event", "event_type": "repair", "mileage": "27537",
            "works": ["замена передних тормозных колодок"]}
DASH = {"kind": "dashboard", "mileage": "25908", "mileage_confidence": "high"}


def _both(make_msg, make_claude, album=None):
    """Один и тот же случай при ручке вкл и выкл. ПРОГРЕВ первым прогоном обязателен: живой код
    один раз за процесс подтягивает кэш базы знаний (чтение моста), и без прогрева близнецы
    разошлись бы на этом чтении, а не на ручке (поймано первым прогоном сьюта)."""
    _fresh_hints()
    wm = make_msg()
    _run(wm, make_claude(), album=(album(wm) if album else None), quiet="1")
    out = {}
    for q in ("1", "0"):
        _fresh_hints()
        msg = make_msg()
        alb = album(msg) if album else None
        sent, calls, cl = _run(msg, make_claude(), album=alb, quiet=q)
        out[q] = (_texts(sent), calls, cl.vision_calls)
    return out


def test_works_without_km_are_still_received():
    out = _both(lambda: _Msg("поменяли передние и задние колодки"),
                lambda: _Claude(WORKS_NO_KM))
    texts = out["1"][0]
    assert len(texts) == 1 and "Принял работы" in texts[0], texts
    assert out["1"] == out["0"], "ручка задела приём работ"


def test_works_with_km_are_still_written():
    out = _both(lambda: _Msg("замена передних колодок, пробег 27537"),
                lambda: _Claude(WORKS_KM))
    calls = out["1"][1]
    rows = [kw for _, kw in calls
            if any("27537" in str(v) for v in kw.values())
            and any("колод" in str(v) for v in kw.values())]
    assert rows, f"работа с пробегом не записана: {calls}"
    assert out["1"] == out["0"], "ручка задела запись работ"


def test_dashboard_photo_still_asks_to_confirm_the_number():
    out = _both(lambda: _Msg(photo=True), lambda: _Claude(vision=[DASH]))
    texts = out["1"][0]
    assert len(texts) == 1 and "25908" in texts[0], texts
    assert out["1"] == out["0"], "ручка задела вопрос о пробеге"


def test_album_with_dashboard_answers_once_not_nine():
    vis = [{"kind": "wheel"}] * 4 + [DASH] + [{"kind": "bike"}] * 4
    out = _both(lambda: _Msg(photo=True, mid=900),
                lambda: _Claude(vision=list(vis)),
                album=lambda m: [m] + [_Msg(photo=True, mid=901 + i) for i in range(8)])
    texts, _, vcalls = out["1"]
    assert vcalls == 9, vcalls
    assert len(texts) == 1 and "25908" in texts[0], texts
    assert out["1"] == out["0"], "ручка задела альбом с приборкой"


def test_witness_is_read_only_by_the_floor():
    """ГРАНИЦА УСТРОЙСТВОМ: свидетель разбора читается РОВНО в `_reply_floor_speak` — ни одна
    ветка записи не зависит от нового знания (ast по живому исходнику)."""
    src = open(os.path.join(ROOT, "splinter.py"), encoding="utf-8").read()
    readers = set()
    for fn in ast.walk(ast.parse(src)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if (isinstance(node, ast.Attribute) and node.attr == "get"
                        and isinstance(node.value, ast.Name) and node.value.id == "_PARSE_SEEN"):
                    readers.add(fn.name)
    assert readers == {"_reply_floor_speak"}, readers


# ============================================================================================
#  (5) ЧИСТОТА РЕШЕНИЯ — прежний страж, прежний единственный импорт
# ============================================================================================
def test_decision_keeps_its_single_import():
    src = open(os.path.join(ROOT, "reply_floor.py"), encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"write_fact"}, mods


def test_purity_guard_still_green_on_the_live_module():
    import invariants_check as IC
    assert "REPLY_FLOOR_PURE" in [n for n, _ in IC.CHECKS], "страж в гейте"
    live = open(os.path.join(ROOT, "reply_floor.py"), encoding="utf-8").read()
    assert IC._duty_ast_findings(live, allowed=frozenset(("write_fact",))) == [], "модуль чист"


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
