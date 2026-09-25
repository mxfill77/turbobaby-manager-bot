"""ПОДПИСЬ К ФОТО: КОРОТКОЕ УКАЗАНИЕ — ЗАЯВКА (24.09.2026, задание Штаба 0031-73d).

Живой случай 24.09 07:09 UTC, тема XADV 750 GREY 2478 (артефакт ПК XADVZHIVOYSLUCHAY2409):
msg 12105 — фото колеса с подписью «Need to change»; разборщик не дал вердикта (`type=None`),
строка событий легла как `photo` без подписи, заявки нет, подсказка C посоветовала помыть байк.
msg 12106 — фото без подписи с повреждением; тревога J — верно, её не трогаем.

Предмет — четыре вещи, все судятся ЖИВЫМ кодом (`splinter.handle` → `_handle_servicing`):
  1  РЕШЕНИЕ `caption_intent` — указание / отчёт о сделанном / ни то ни другое (EN/RU/TH);
  2  УКАЗАНИЕ → ЗАЯВКА на байк темы существующей дверью и ОДНА строка подтверждения, без C;
  3  ПРЕЖНЕЕ ЦЕЛО — отчёт о сделанном идёт записью работ, болтовня молчит, J и C без подписи —
     как были, альбом — один прогон и одна заявка;
  4  РУЧКА `CAPTION_INTAKE=0` — прежний путь: C на 12105, подписи в строке событий нет.

Фразы подписей — названные заданием и их парафразы, переписка наружу не выводится. Сеть, Telegram,
мост и модель замоканы; мост-заглушка копит СОСТАВ аргументов — имён боевых операций записи в файле
нет (приём `test_floor_quiet`). Память замков и журналов уведена во временный каталог.
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
os.environ["CAPTION_INTAKE"] = "1"
_TMP = tempfile.mkdtemp(prefix="tb_caption_zayavka_")
os.environ["HINT_DEDUP_STATE"] = os.path.join(_TMP, "hint.json")
os.environ["WORKS_PERSIST_STATE"] = os.path.join(_TMP, "works.json")
os.environ["SVC_TOKENS_STATE"] = os.path.join(_TMP, "svc_tokens.json")

import splinter as S         # noqa: E402

BIKE = "TESTBIKE 000ZZ PHUKET 4244"      # такого байка в парке нет
_TOPIC = [7400]


def _topic():
    """Своя тема на каждый прогон: память переспросов и буферов по теме между случаями не течёт."""
    _TOPIC[0] += 1
    return _TOPIC[0]


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


# ============================================================================================
#  Заглушки мира
# ============================================================================================
class _Bot:
    username = "tb_caption_test_bot"

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
        self.id, self.username, self.is_bot, self.first_name = 99003, username, is_bot, "T"


class _Msg:
    def __init__(self, text="", photo=False, caption=None, mid=12105, topic=None):
        self.chat_id = _chat_servicing()
        self.text = text or None
        self.caption = caption
        self.photo = [object()] if photo else []
        self.message_id = mid
        self.message_thread_id = topic if topic is not None else _topic()
        self.date = None
        self.from_user = _User()
        self.reply_to_message = None
        self.media_group_id = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _Bridge:
    """Отвечает на ЛЮБОЕ имя одинаково; копит (имя, состав аргументов). `open_item` — открытая
    заявка по байку (чтение); `refuse` — мост не принимает заявку (ответ без `ok`)."""

    def __init__(self, open_item=None, refuse=False):
        self.calls, self.open_item, self.refuse = [], open_item, refuse

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def _any(*a, **kw):
            self.calls.append((name, dict(kw)))
            if name == "service_pending_get":
                return {"ok": True, "item": self.open_item} if self.open_item else {"ok": False}
            if self.refuse and "declared" in kw:
                return {"ok": False, "error": "test_refused"}
            return {"ok": True, "items": [], "saved": True}
        return _any


class _Claude:
    """Разборщик: текст → заданный вердикт; снимки → заданные разборы по очереди.
    `parse=None` — разбор не дал ничего (как живой ответ по 12105); строка — отдаётся как есть."""

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


def _run(msg, claude, *, album=None, knob="1", bridge=None, bike=BIKE, position="1"):
    """Прогнать ЖИВОЙ `splinter.handle`. Возврат (отправленное, вызовы моста, разборщик).
    `position` — ручка `BIKE_POSITION` (25.09.2026): случаи, чей предмет — прежнее правило «совет C
    по картинке», гоняются с `position="0"`; новое правило судит `tests/test_bike_position.py`."""
    prev = os.environ.get("CAPTION_INTAKE")
    prev_pos = os.environ.get("BIKE_POSITION")
    os.environ["CAPTION_INTAKE"] = knob
    os.environ["BIKE_POSITION"] = position
    ctx, br = _Ctx(), (bridge or _Bridge())
    saved = (S.bike_from_topic, S._download_photo)
    S.bike_from_topic = lambda *a, **k: bike          # тема = байк, без обращения к миру

    async def _dl(pm):
        return b"\xff\xd8 test"
    S._download_photo = _dl
    _fresh_hints()
    try:
        asyncio.run(S.handle(_Upd(msg), ctx, br, claude, album_msgs=album))
    finally:
        S.bike_from_topic, S._download_photo = saved
        os.environ["CAPTION_INTAKE"] = prev if prev is not None else "1"
        os.environ["BIKE_POSITION"] = prev_pos if prev_pos is not None else "1"
    return ctx.bot.sent, br.calls, claude


def _texts(sent):
    return [s.get("text", "") for s in sent]


def _fresh_hints():
    """Замок подсказок — СВОЙ файл на прогон: близнецы не должны делить память повтора."""
    os.environ["HINT_DEDUP_STATE"] = tempfile.mktemp(prefix="hint_", suffix=".json", dir=_TMP)
    S._HINT_SEEN = None


def _zayavki(calls):
    """Вызовы-заявки: по СОСТАВУ аргументов (перечень видов), без имени операции."""
    return [kw for _, kw in calls if "declared" in kw and "bike" in kw]


def _intake_rows(calls):
    return [kw for _, kw in calls if kw.get("event_type") == "intake"]


def _event_rows(calls):
    return [kw for _, kw in calls if "event_type" in kw and "notes" in kw]


CHAT = {"type": "none", "event_type": None, "mileage": None, "works": []}
V12105 = {"kind": "wheel", "tire": {"position": None, "condition": "worn", "note": "шина"},
          "damage": None, "dirt": True, "fuel": None, "mileage": None, "notes": "колесо"}
V12106 = {"kind": "other", "damage": "трещина на пластике", "dirt": False,
          "fuel": None, "mileage": None, "notes": "деталь"}
LINE_RU = f"📝 заявка: {BIKE} — замена (колесо)"
LINE_TH = f"📝 รับเรื่อง: {BIKE} — เปลี่ยน (ล้อ)"


# ============================================================================================
#  (1) РЕШЕНИЕ — чистое, EN/RU/TH
# ============================================================================================
def test_directive_captions_are_directives():
    import caption_intent as C
    for cap in ("Need to change", "need to change", "change", "replace", "broken",
                "заменить", "поменять", "сломано", "เปลี่ยน", "เสีย", "ชำรุด",
                "change tire", "Need to replace front tyre", "заменить колодки", "надо менять",
                "не работает", "เปลี่ยนยาง", "ต้องเปลี่ยน", "@pym_mech need to change"):
        v = C.verdict(cap)
        assert v["state"] == C.DIRECTIVE, (cap, v)


def test_done_reports_are_not_directives():
    import caption_intent as C
    for cap in ("changed", "changed tire", "поменял масло", "заменил колодки", "เปลี่ยนแล้ว",
                "replaced", "done", "ซ่อมเสร็จ", "поменяли шину"):
        v = C.verdict(cap)
        assert v["state"] == C.DONE, (cap, v)


def test_chatter_questions_negations_and_long_text_are_none():
    import caption_intent as C
    for cap in ("ok", "ок", "👍", "@someone_else", "nice weather", "you ok", "",
                "need to change?", "เปลี่ยนไหม", "не надо менять", "no need to change",
                "ไม่ต้องเปลี่ยน", "เสียงดัง", "https://example.org/x",
                "we will think whether to change the tire later"):
        v = C.verdict(cap)
        assert v["state"] == C.NONE, (cap, v)


def test_decision_never_raises():
    import caption_intent as C
    for bad in (None, 12345, object(), "   ", "\n\n"):
        assert C.verdict(bad)["state"] in (C.NONE, C.DIRECTIVE, C.DONE)


def test_object_from_caption_then_photo_then_honest_unknown():
    import caption_intent as C
    assert C.object_of("Need to change", {"kind": "wheel"}) == ("колесо", "ล้อ")
    assert C.object_of("change tire", {"kind": "bike"}) == ("шина", "ยาง")
    assert C.object_of("заменить колодки", {}) == ("тормозные колодки", "ผ้าเบรก")
    assert C.object_of("เปลี่ยนยาง", None) == ("шина", "ยาง")
    assert C.object_of("broken", {"kind": "other"})[0] == "что — по фото"


def test_confirm_line_is_one_message_th_and_ru_with_notebook_and_no_cyrillic_in_th():
    import caption_intent as C
    t = C.confirm_text("XADV 750 GREY 2478", C.ACT_CHANGE, ("колесо", "ล้อ"))
    lines = t.split("\n")
    assert "📝 заявка: XADV 750 GREY 2478 — замена (колесо)" in lines, t
    th = [ln for ln in lines if ln.startswith("📝 รับเรื่อง")]
    assert len(th) == 1 and not any("а" <= ch.lower() <= "я" for ch in th[0]), t
    assert lines[0] == "🐀 Splinter" and len(lines) == 3, t


def test_caption_goes_first_into_notes_and_fits_the_field():
    import caption_intent as C
    n = C.note_with_caption("колесо | грязный", "Need to change")
    assert n == "подпись: «Need to change» | колесо | грязный", n
    assert len(C.note_with_caption("x" * 400, "y" * 400)) == 200
    assert C.note_with_caption("колесо", "") == "колесо"


def test_decision_imports_only_re_and_work_intent():
    src = open(os.path.join(ROOT, "caption_intent.py"), encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"re", "work_intent"}, mods


# ============================================================================================
#  (2) УКАЗАНИЕ → ЗАЯВКА — на живом `_handle_servicing`
# ============================================================================================
def test_replay_12105_gives_one_zayavka_and_one_line_without_c():
    """Реплей: подпись «Need to change», снимок колеса с грязью, разборщик не дал ничего."""
    sent, calls, cl = _run(_Msg(photo=True, caption="Need to change"),
                           _Claude(None, vision=[V12105]))
    assert len(sent) == 1, _texts(sent)
    text = sent[0]["text"]
    assert LINE_RU in text and LINE_TH in text, text
    assert "🧽" not in text, "совет помыть на указании"
    z = _zayavki(calls)
    assert len(z) == 1 and z[0]["status"] == "заявлено" and z[0]["bike"] == BIKE, z
    assert "WORKS:{замена (колесо)}" in z[0]["note"], z
    rows = _intake_rows(calls)
    assert len(rows) == 1 and rows[0]["notes"].startswith("подпись: «Need to change»"), rows
    assert len(_event_rows(calls)) == 1, "строка события ровно одна (intake), без второй photo"
    assert cl.vision_calls == 1


def test_replay_12105_does_not_depend_on_what_the_parser_said():
    """Модель недетерминирована: JSON без type, «болтовня», ремонт с работами — исход один."""
    for parse in ('{"notes": "нужна замена"}', CHAT, "не json",
                  {"type": "event", "event_type": "repair", "mileage": None,
                   "works": ["замена колеса"], "notes": "замена колеса"}):
        sent, calls, _ = _run(_Msg(photo=True, caption="Need to change"),
                              _Claude(parse, vision=[V12105]))
        assert len(sent) == 1 and LINE_RU in sent[0]["text"], (parse, _texts(sent))
        assert len(_zayavki(calls)) == 1, (parse, calls)


def test_th_and_ru_directives_become_zayavki_with_object_from_caption():
    for cap, obj in (("เปลี่ยนยาง", "шина"), ("заменить колодки", "тормозные колодки"),
                     ("сломано", "колесо"), ("เสีย", "колесо")):
        sent, calls, _ = _run(_Msg(photo=True, caption=cap),
                              _Claude(None, vision=[{"kind": "wheel", "dirt": True}]))
        assert len(sent) == 1 and "📝 заявка" in sent[0]["text"], (cap, _texts(sent))
        assert f"({obj})" in sent[0]["text"], (cap, sent[0]["text"])
        assert len(_zayavki(calls)) == 1, cap


def test_open_zayavka_gets_the_work_added_and_keeps_its_status():
    br = _Bridge(open_item={"declared": "oil", "status": "ждёт_факт", "note": "WORKS:{замена масла}"})
    sent, calls, _ = _run(_Msg(photo=True, caption="Need to change"),
                          _Claude(None, vision=[V12105]), bridge=br)
    z = _zayavki(calls)
    assert len(z) == 1 and "status" not in z[0], z
    assert z[0]["declared"] == "oil,other", z
    assert z[0]["note"] == "WORKS:{замена масла; замена (колесо)}", z
    assert len(sent) == 1 and LINE_RU in sent[0]["text"], _texts(sent)


def test_bridge_refusal_is_not_a_false_confirmation():
    """Мост заявку не принял → «заявка есть» не говорим; пол скажет, что заход упал."""
    sent, calls, _ = _run(_Msg(photo=True, caption="Need to change"),
                          _Claude(None, vision=[V12105]), bridge=_Bridge(refuse=True))
    assert not any("📝 заявка" in t for t in _texts(sent)), _texts(sent)
    assert len(sent) == 1, "пол ответа говорит о сбое"


def test_album_with_one_caption_gives_one_zayavka():
    album = [_Msg(photo=True, caption="Need to change" if i == 0 else None, mid=13000 + i)
             for i in range(3)]
    for m in album[1:]:
        m.message_thread_id = album[0].message_thread_id
    vis = [dict(V12105), {"kind": "bike", "dirt": True}, {"kind": "bike"}]
    sent, calls, cl = _run(album[0], _Claude(None, vision=vis), album=album)
    assert cl.vision_calls == 3, "каждый снимок альбома разобран"
    assert len(sent) == 1 and LINE_RU in sent[0]["text"], _texts(sent)
    assert len(_zayavki(calls)) == 1 and len(_intake_rows(calls)) == 1, calls


# ============================================================================================
#  (3) ПРЕЖНЕЕ ЦЕЛО
# ============================================================================================
def test_replay_12106_damage_alarm_j_as_before():
    """Второе фото живого случая: без подписи, повреждение — тревога J, байт-в-байт с ручкой выкл."""
    on, c_on, _ = _run(_Msg(photo=True, mid=12106), _Claude(None, vision=[V12106]))
    off, c_off, _ = _run(_Msg(photo=True, mid=12106), _Claude(None, vision=[V12106]), knob="0")
    assert len(on) == 1 and "⚠️" in on[0]["text"] and "трещина на пластике" in on[0]["text"], _texts(on)
    assert _texts(on) == _texts(off)
    assert not _zayavki(c_on)
    strip = lambda cs: [(n, {k: v for k, v in kw.items() if k not in ("group", "msg_id", "topic_id")})
                        for n, kw in cs]         # тема у близнецов своя — адрес, а не смысл
    assert strip(c_on) == strip(c_off), "вызовы моста те же (без подписи ручке нечего менять)"


def test_done_captions_go_to_works_record_not_zayavka():
    cases = (
        ("changed tire", {"type": "event", "event_type": "repair", "mileage": None,
                          "works": ["замена шины"], "notes": "заменили шину"}, {"kind": "wheel"}),
        ("поменял масло", {"type": "event", "event_type": "repair", "mileage": None,
                           "works": ["замена масла"], "notes": "замена масла"}, {"kind": "other"}),
    )
    for cap, parse, v in cases:
        on, c_on, _ = _run(_Msg(photo=True, caption=cap), _Claude(parse, vision=[v]))
        off, c_off, _ = _run(_Msg(photo=True, caption=cap), _Claude(parse, vision=[v]), knob="0")
        assert not any("📝 заявка" in t for t in _texts(on)), (cap, _texts(on))
        assert not [z for z in _zayavki(c_on) if z.get("status") == "заявлено"], (cap, c_on)
        assert _texts(on) == _texts(off), (cap, _texts(on), _texts(off))
        assert on, f"{cap}: запись работ отвечает, как отвечала"


def test_chatter_ok_emoji_and_tag_are_not_zayavka_and_floor_is_silent():
    for cap in ("nice weather today", "ok", "👍", "@someone_else"):
        sent, calls, _ = _run(_Msg(photo=True, caption=cap), _Claude(CHAT, vision=[{"kind": "wheel"}]))
        assert sent == [], (cap, _texts(sent))
        assert not _zayavki(calls), cap


def test_directive_as_plain_text_without_photo_is_not_this_path():
    """Предмет — подпись к ФОТО. Текст без снимка судит разборщик, как судил."""
    sent, calls, _ = _run(_Msg("Need to change"), _Claude(CHAT))
    assert not _zayavki(calls) and not any("📝 заявка" in t for t in _texts(sent)), _texts(sent)


def test_dirty_photo_without_caption_still_gets_c():
    # Предмет — прежнее правило C (по картинке): ручка положения выключена. С 25.09 при включённой
    # совет зависит от положения байка — близнец в `tests/test_bike_position.py`.
    on, _, _ = _run(_Msg(photo=True), _Claude(None, vision=[{"kind": "bike", "dirt": True}]), position="0")
    off, _, _ = _run(_Msg(photo=True), _Claude(None, vision=[{"kind": "bike", "dirt": True}]), knob="0",
                     position="0")
    assert len(on) == 1 and "🧽" in on[0]["text"], _texts(on)
    assert _texts(on) == _texts(off)


def test_dirty_photo_with_neutral_caption_still_gets_c():
    """Подпись без сервисного смысла — не сервис-контекст: совет про мойку и чехол на стоянке
    по делу (близнец `test_handover.test_dirt_fires_without_handover`). Предмет — прежнее правило
    C, ручка положения выключена; на возврате то же проверяет `tests/test_bike_position.py`."""
    for cap in ("ok", "👍", "@someone_else", "стоит на парковке", "nice weather today"):
        sent, _, _ = _run(_Msg(photo=True, caption=cap),
                          _Claude(CHAT, vision=[{"kind": "bike", "dirt": True}]), position="0")
        assert len(sent) == 1 and "🧽" in sent[0]["text"], (cap, _texts(sent))


def test_dirty_photo_with_service_caption_gets_no_c():
    """Отчёт о сделанном при немом разборщике и указание там, где заявку завести нельзя (байк
    темы неизвестен), — сервис-контекст: совета «помыть» нет."""
    for cap, bike in (("changed tire", BIKE), ("Need to change", "")):
        sent, calls, _ = _run(_Msg(photo=True, caption=cap),
                              _Claude(None, vision=[{"kind": "wheel", "dirt": True}]), bike=bike)
        assert not any("🧽" in t for t in _texts(sent)), (cap, _texts(sent))
        assert not [z for z in _zayavki(calls) if z.get("status") == "заявлено"], (cap, calls)


def test_directive_on_dashboard_with_mileage_keeps_its_own_path():
    """Снимок приборки с числом — своя ветка записи пробега; заявку по подписи сюда не ведём."""
    v = {"kind": "dashboard", "mileage": "12345", "mileage_confidence": "high"}
    sent, calls, _ = _run(_Msg(photo=True, caption="need to change"), _Claude(None, vision=[v]))
    assert not any("📝 заявка" in t for t in _texts(sent)), _texts(sent)
    assert not [z for z in _zayavki(calls) if z.get("status") == "заявлено"], calls


# ============================================================================================
#  (4) РУЧКА ОТКАТА
# ============================================================================================
def test_knob_off_returns_the_old_path_on_12105():
    """`CAPTION_INTAKE=0` → как было 24.09 07:09: совет C, заявки нет, подписи в строке нет.
    «Как было 24.09» — это и без положения байка (25.09): обе ручки выключены."""
    sent, calls, _ = _run(_Msg(photo=True, caption="Need to change"),
                          _Claude(None, vision=[V12105]), knob="0", position="0")
    assert _texts(sent) == [S.msg_dirty_care(BIKE)], _texts(sent)
    assert not _zayavki(calls)
    rows = _event_rows(calls)
    assert len(rows) == 1 and rows[0]["event_type"] == "photo", rows
    assert "подпись" not in rows[0]["notes"], rows


def test_knob_reads_like_its_neighbours():
    for off in ("0", "", "нет", "no", "off", " 0 "):
        os.environ["CAPTION_INTAKE"] = off
        assert S._caption_intake_on() is False, repr(off)
    for on in ("1", "yes", "да"):
        os.environ["CAPTION_INTAKE"] = on
        assert S._caption_intake_on() is True, repr(on)
    os.environ["CAPTION_INTAKE"] = "1"


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
