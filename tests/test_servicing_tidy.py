"""ПАКЕТ 2 ПРИБОРКИ ОБСЛУЖИВАНИЯ (25.10.2026, ветка servicing-tidy-2510).

Живой случай: тема NINJA 400 6334, 25.10 14:01. Решатель записал пробег 41973 с фото приборки
(`_odo_confirmed`) и не сказал ни слова — у двери не было хвоста `_after_mileage`; пол ответа, не
услышав речи, сказал «числа на нём разобрать не смог», хотя число было прочитано уверенно.

Что держит сьют:
  (A)  пол знает ЧИСЛО, прочитанное разбором фото (`_PHOTO_KM`, conf=high, 3–6 цифр), и говорит
       «читаю N км, но сам записывать не стал», а не «разобрать не смог»; число прошлого снимка
       в следующее сообщение не доезжает (`handle` его сбрасывает);
  (A2) дверь решателя `DOOR_ODO` после `_odo_confirmed` зовёт хвост `_after_mileage` (ТО-трекер,
       квитанция) — ровно раз, с тем км; сбой хвоста дверь не роняет;
  (B)  эскалация и напоминание висяка называют работы и тогда, когда заявленного нет
       (было «Заявка на ТО (—) висит 7ч»); замок повторов судит по-прежнему по заявленному;
  (C)  ответ мозга уходит без разметки: парные `**` и строки-линии `---` сняты, прочее цело.
У каждого случая — близнец «то же, но поведения быть не должно».

Мост, Telegram, модель и алерт владельцу — заглушки; имена боевых операций собраны из кусков.
Байк выдуман, числа — живые (41973 / 41928). Файлы состояния — во временном каталоге.
"""
import ast
import asyncio
import contextlib
import datetime
import importlib.util
import json
import os
import sys
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
_TMP = tempfile.gettempdir()
os.environ.setdefault("DECIDER_LIVE_STATE", os.path.join(_TMP, f"dlive_tidy_{os.getpid()}.json"))
os.environ.setdefault("MILEAGE_Q_STATE", os.path.join(_TMP, f"mileage_q_tidy_{os.getpid()}.json"))
os.environ.setdefault("HINT_DEDUP_STATE", os.path.join(_TMP, f"hint_tidy_{os.getpid()}.json"))
os.environ.setdefault("TOPIC_FEED_DIR", os.path.join(_TMP, f"topic_feed_tidy_{os.getpid()}"))
os.environ.setdefault("SVC_TOKENS_STATE", os.path.join(_TMP, f"svc_tokens_tidy_{os.getpid()}.json"))
os.environ.setdefault("WORKS_PERSIST_STATE", os.path.join(_TMP, f"works_tidy_{os.getpid()}.json"))
os.environ["NEVER_SILENT"] = "1"        # боевые дефолты ЯВНО: сьют не зависит от .env машины
os.environ["FLOOR_QUIET"] = "1"
os.environ["SERVICE_DEBT"] = "1"
os.environ["HINTS_DEDUP"] = "0"         # замок повторов включаем точечно там, где он предмет
os.environ["ACT_GATE"] = "0"            # ворота действия здесь не предмет (их судит test_act_gate)

import splinter as S          # noqa: E402
import reply_floor as F       # noqa: E402
import notify as N            # noqa: E402

TOPIC = 8813
BIKE = "TESTBIKE NINJA 400 9998"
KM, OIL_LAST = 41973, 41928             # живые числа случая 25.10 14:01

OP_FIND = "find" + "_bike"
OP_TRACKER = "service" + "_upsert"
OP_SP_GET = "service_pending" + "_get"
OP_SP_LIST = "service_pending" + "_list"
OP_SP_UPSERT = "service_pending" + "_upsert"
OP_SVC_LIST = "service" + "_list"

# Прежний текст пола на приборку без числа — БАЙТ-В-БАЙТ (reply_floor.fallback, ветка (1)).
OLD_DASH_RU = ("🤔 Фото вижу, а числа на нём разобрать не смог. "
               "Что делать: пришли пробег цифрами в ответ или переснимите приборку "
               "покрупнее и без бликов.")
OLD_DASH_TH = ("🤔 เห็นรูป แล้วครับ แต่อ่านเลขไม่ออก "
               "ช่วยพิมพ์เลขไมล์เป็นตัวเลข หรือถ่ายหน้าปัดใหม่ให้ใกล้และไม่สะท้อนแสง")
NEW_DASH_RU = "📟 На фото читаю 41973 км, но сам записывать не стал. Что делать: пришли пробег цифрами в ответ — запишу."


def _chat_of(mode):
    """Живой реестр групп: адрес контура берём у кода, а не хардкодим числом."""
    for cid, m in S.GROUPS.items():
        if m == mode:
            return cid
    raise AssertionError(f"в GROUPS нет контура {mode}")


CHAT = _chat_of("servicing")


class _Calls(list):
    def of(self, name):
        return [c for c in self if c[0] == name]


class _FakeBridge:
    """Мост-заглушка: ловит ЛЮБОЙ вызов по имени, ничего не делает, ничего не пишет."""

    def __init__(self, answers=None):
        self.calls = _Calls()
        self._answers = answers or {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)

        def _catch(*a, **kw):
            self.calls.append((name, a, kw))
            ans = self._answers.get(name, {"ok": True})
            return ans(*a, **kw) if callable(ans) else ans
        return _catch


def _bridge(**extra):
    ans = {OP_FIND: {"name": BIKE, "oil_last_km": OIL_LAST},
           OP_TRACKER: {"ok": True, "status": "ok", "next_km": 44928, "km_left": 2955},
           OP_SP_GET: {"ok": False, "error": "not_found"},
           OP_SVC_LIST: {"ok": True, "items": []}}
    ans.update(extra)
    return _FakeBridge(ans)


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 900 + len(self.sent)})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self, username="testmech"):
        self.id, self.username, self.is_bot = 99044, username, False
        self.first_name = "Test"


class _Msg:
    def __init__(self, text="", topic=TOPIC, photo=None, mid=555, chat=CHAT):
        self.chat_id, self.text, self.message_thread_id = chat, text, topic
        self.caption, self.photo = None, photo or []
        self.from_user, self.message_id, self.date = _User(), mid, None
        self.reply_to_message = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


class _Claude:
    """Модель-заглушка: разбор фото возвращает ровно `vis`, текстовый разбор не нужен."""

    def __init__(self, vis):
        self.vis = vis

    def vision(self, *a, **k):
        return json.dumps(self.vis)

    def quick(self, *a, **k):
        return "{}"


def _run(coro):
    """Свой цикл на каждый прогон: свидетели пола — ContextVar, чужой цикл дал бы чужой контекст."""
    return asyncio.run(coro)


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


_T = [TOPIC]


def _topic():
    """Своя тема на каждый прогон: накопители сводки и вопросы о пробеге не перетекают."""
    _T[0] += 1
    return _T[0]


VIS_HIGH = {"mileage": KM, "mileage_confidence": "high", "kind": "dashboard"}


@contextlib.contextmanager
def _photo_path(decider=None, took=None):
    """Настоящие `handle` → `_handle_servicing` → пол; глушим скачивание, ленту и тень, а решатель
    в бою «берёт» фото (как на живом случае) и делает то, что дано в `decider` (по умолчанию —
    ничего: решил не писать)."""
    async def _img(pm):
        return b"fixture-image"

    async def _dl(msg, context, bridge, claude, kind="text"):
        if took is not None:
            took.append(kind)
        if decider is not None:
            await decider(msg, context, bridge)
        return True
    with _patch(S, _download_photo=_img, decider_live_on=lambda: True, decider_live=_dl,
                decider_shadow=lambda *a, **k: None, feed_vision=lambda *a, **k: True):
        yield


def _photo_drive(vis, decider=None):
    t = _topic()
    ctx, br, took = _Ctx(), _bridge(), []
    with _photo_path(decider, took):
        _run(S.handle(_Upd(_Msg(topic=t, photo=[object()])), ctx, br, _Claude(vis)))
    return ctx.bot.sent, br, took, t


def _ru(m):
    return m["text"]


# ============================================================================================
#  (A) ПОЛ ОТВЕТА ЗНАЕТ ПРОЧИТАННОЕ ЧИСЛО — ЧИСТАЯ ФУНКЦИЯ
# ============================================================================================
def test_fallback_dashboard_with_number_names_it():
    say = F.fallback({"photo": True, "photo_kind": F.DASHBOARD, "photo_km": "41973"})
    assert say["ru"] == NEW_DASH_RU, say["ru"]
    assert "разобрать не смог" not in say["ru"], say["ru"]
    assert "41973" in say["th"] and say["state"] == F.UNCLEAR, say
    with_bike = F.fallback({"photo": True, "photo_kind": F.DASHBOARD, "photo_km": "41973", "bike": "X 1"})
    assert with_bike["ru"].startswith("📟 На фото по X 1 читаю 41973 км"), with_bike["ru"]


def test_fallback_twin_without_number_is_old_text_byte_for_byte():
    """БЛИЗНЕЦ: числа нет (поле не передано / пусто / None) — прежний текст байт-в-байт."""
    for facts in ({"photo": True, "photo_kind": F.DASHBOARD},
                  {"photo": True, "photo_kind": F.DASHBOARD, "photo_km": ""},
                  {"photo": True, "photo_kind": F.DASHBOARD, "photo_km": None}):
        say = F.fallback(facts)
        assert say["ru"] == OLD_DASH_RU, (facts, say["ru"])
        assert say["th"] == OLD_DASH_TH, (facts, say["th"])


def test_fallback_twin_number_not_digits_is_old_text():
    """БЛИЗНЕЦ: «число» не цифрами — прежний текст, ничего не выдумываем."""
    for km in ("41 973", "41973.5", "41,973", "abc", "  ", "~41973", "-41973"):
        say = F.fallback({"photo": True, "photo_kind": F.DASHBOARD, "photo_km": km})
        assert say["ru"] == OLD_DASH_RU, (km, say["ru"])


def test_fallback_twin_number_but_not_dashboard_or_crash():
    """БЛИЗНЕЦ: число есть, но снимок не приборка / вид не узнан / заход упал — прежние ветки."""
    seen_kind = sorted(F._PHOTO_SEEN)[0]
    for facts in ({"photo": True, "photo_kind": seen_kind, "photo_km": "41973"},
                  {"photo": True, "photo_kind": "", "photo_km": "41973"},
                  {"photo": True, "photo_kind": F.DASHBOARD, "photo_km": "41973", "crashed": True},
                  {"photo": False, "photo_kind": F.DASHBOARD, "photo_km": "41973"}):
        say = F.fallback(facts)
        assert "читаю" not in say["ru"] and "41973" not in say["ru"], (facts, say["ru"])


# ============================================================================================
#  (A) ЖИВОЙ ПУТЬ: свидетель `_PHOTO_KM` доезжает до пола
# ============================================================================================
def test_floor_hands_pass_photo_km_from_contextvar():
    """Руки пола (`_reply_floor_speak`) кладут в факты `photo_km` из ContextVar, а не пустоту."""
    seen = []
    orig = F.fallback

    def spy(facts=None):
        seen.append(dict(facts or {}))
        return orig(facts)

    async def go():
        S._PHOTO_KIND.set(F.DASHBOARD)
        S._PHOTO_KM.set("41973")
        ctx = _Ctx()
        spoke = await S._reply_floor_speak(ctx, _Msg(topic=_topic(), photo=[object()]),
                                           spoke_before=S._SPOKE.get())
        return spoke, ctx.bot.sent
    with _patch(F, fallback=spy):
        spoke, sent = _run(go())
    assert seen and seen[-1].get("photo_km") == "41973", seen
    assert spoke is True and len(sent) == 1 and NEW_DASH_RU in _ru(sent[0]), sent


def test_photo_high_confidence_floor_names_number():
    """ГЛАВНЫЙ СЛУЧАЙ (живой путь): фото приборки, разбор уверенно прочитал 41973, решатель взял
    фото и промолчал → пол говорит, ЧТО прочитано, а не «разобрать не смог»."""
    sent, br, took, _t = _photo_drive(VIS_HIGH)
    assert took == ["photo"], f"фото не дошло до решателя: {took}"
    assert len(sent) == 1, sent
    body = _ru(sent[0])
    assert NEW_DASH_RU in body, body
    assert "разобрать не смог" not in body, body


def test_photo_number_with_spaces_is_normalised():
    """Разбор отдал «41 973» — свидетель кладёт 41973 (пробелы и запятые снимаются)."""
    for raw in ("41 973", "41,973"):
        sent, _br, _took, _t = _photo_drive({"mileage": raw, "mileage_confidence": "HIGH", "kind": "dashboard"})
        assert len(sent) == 1 and NEW_DASH_RU in _ru(sent[0]), (raw, sent)


def test_photo_twin_low_confidence_keeps_old_text():
    """БЛИЗНЕЦ: уверенность не high — числу не верим, прежний текст байт-в-байт."""
    for conf in ("low", "medium", ""):
        sent, _br, took, _t = _photo_drive({"mileage": KM, "mileage_confidence": conf, "kind": "dashboard"})
        assert took == ["photo"] and len(sent) == 1, (conf, sent)
        assert OLD_DASH_RU in _ru(sent[0]) and "читаю" not in _ru(sent[0]), (conf, _ru(sent[0]))


def test_photo_twin_implausible_shape_keeps_old_text():
    """БЛИЗНЕЦ: число не той формы (7 цифр, 2 цифры, с точкой, словами) — прежний текст."""
    for raw in ("1234567", "41", "41.973", "41973km", "сорок тысяч"):
        sent, _br, _took, _t = _photo_drive({"mileage": raw, "mileage_confidence": "high", "kind": "dashboard"})
        assert len(sent) == 1 and OLD_DASH_RU in _ru(sent[0]), (raw, _ru(sent[0]))


def test_handle_resets_photo_km_between_messages():
    """Число прошлого снимка не доезжает до следующего сообщения той же задачи: второе фото,
    по которому разбора не было, не получает «читаю 41973»."""
    t = _topic()
    ctx, br = _Ctx(), _bridge()

    async def silent(*a, **k):
        return None

    async def both():
        with _photo_path():
            await S.handle(_Upd(_Msg(topic=t, photo=[object()])), ctx, br, _Claude(VIS_HIGH))
            with _patch(S, _handle_servicing=silent):
                await S.handle(_Upd(_Msg(topic=t, photo=[object()], mid=556)), ctx, br, _Claude(VIS_HIGH))
        return ctx.bot.sent
    sent = _run(both())
    assert len(sent) == 2, sent
    assert NEW_DASH_RU in _ru(sent[0]), _ru(sent[0])
    assert "41973" not in _ru(sent[1]) and "читаю" not in _ru(sent[1]), _ru(sent[1])


def test_handle_resets_photo_km_before_the_handler():
    """Тот же замок изнутри: заход видит пустой свидетель, что бы ни лежало в нём до `handle`."""
    seen = []

    async def peek(*a, **k):
        seen.append(S._PHOTO_KM.get())

    async def go():
        S._PHOTO_KM.set("41973")
        with _patch(S, _handle_servicing=peek):
            await S.handle(_Upd(_Msg(topic=_topic(), text="текст")), _Ctx(), _bridge(), _Claude({}))
    _run(go())
    assert seen == [""], seen


# ============================================================================================
#  (A2) ДВЕРЬ РЕШАТЕЛЯ «ЗАПИСАТЬ ПРОБЕГ» ЗОВЁТ ХВОСТ `_after_mileage`
# ============================================================================================
def _snap(t=TOPIC):
    return {"chat": CHAT, "topic": t, "bike": BIKE, "facts": {"role": "Пым", "mid": 4242}}


def _v(what="пробег", km=KM, door=None):
    return {"итог": {"действие": "записать", "что": what, "км": km, "источник": 4242},
            "дверь": S._tdec.DOOR_ODO if door is None else door}


class _Doors:
    """Двери решателя — шпионы, с общим журналом порядка."""

    def __init__(self, after_raises=False):
        self.after_raises = after_raises
        self.order, self.after, self.odo, self.sp, self.ask = [], [], [], [], []

    def __enter__(self):
        async def _after(*a, **k):
            self.order.append("_after_mileage")
            self.after.append(a)
            if self.after_raises:
                raise RuntimeError("проба: хвост двери упал")

        def _odo(*a, **k):
            self.order.append("_odo_confirmed")
            self.odo.append((a, k))

        async def _sp(*a, **k):
            self.sp.append(a)

        async def _ask(*a, **k):
            self.ask.append(a)
        self._p = _patch(S, _after_mileage=_after, _odo_confirmed=_odo,
                         sp_confirm_from_brain=_sp, _ask_mileage_confirm=_ask)
        self._p.__enter__()
        return self

    def __exit__(self, *a):
        return self._p.__exit__(*a)


def test_decider_odo_door_calls_after_mileage_once_with_km():
    t = _topic()
    ctx, br = _Ctx(), _bridge()
    with _Doors() as d:
        door = _run(S._decider_execute(_Msg(topic=t), ctx, br, _snap(t), _v()))
    assert door == S._tdec.DOOR_ODO, door
    assert len(d.odo) == 1 and d.odo[0][0][4] == KM, d.odo
    assert d.after == [(ctx, br, CHAT, t, BIKE, "41973", False)], d.after
    assert d.order == ["_odo_confirmed", "_after_mileage"], d.order   # хвост — ПОСЛЕ записи
    assert d.sp == [] and d.ask == [], (d.sp, d.ask)


def test_decider_odo_door_survives_tail_failure():
    """Сбой хвоста (ТО-трекер/квитанция) запись не отменяет и дверь не роняет."""
    t = _topic()
    S._PENDING_MILEAGE[(CHAT, t)] = ("41973", BIKE, None, False)
    with _Doors(after_raises=True) as d:
        door = _run(S._decider_execute(_Msg(topic=t), _Ctx(), _bridge(), _snap(t), _v()))
    assert door == S._tdec.DOOR_ODO, door
    assert len(d.after) == 1, f"хвост не звался: {d.after}"
    assert len(d.odo) == 1, d.odo
    assert (CHAT, t) not in S._PENDING_MILEAGE, "вопрос о пробеге не снят"


def test_decider_odo_door_tail_failure_still_says_recorded():
    """Хвост упал, а пробег уже лёг: человек слышит «записан», а не «сам записывать не стал»."""
    t = _topic()
    ctx = _Ctx()
    with _Doors(after_raises=True):
        _run(S._decider_execute(_Msg(topic=t), ctx, _bridge(), _snap(t), _v()))
    texts = [m.get("text", "") for m in ctx.bot.sent]
    assert any("41973" in x and "записан" in x for x in texts), texts
    assert not any("не стал" in x or "разобрать не смог" in x for x in texts), texts


def test_decider_odo_door_passes_oil_hint_of_open_question():
    """Признак «был маркер замены» из открытого вопроса о пробеге доезжает до хвоста, как у
    прочих дверей; без вопроса — False."""
    t = _topic()
    S._PENDING_MILEAGE[(CHAT, t)] = ("41973", BIKE, None, True)
    with _Doors() as d:
        _run(S._decider_execute(_Msg(topic=t), _Ctx(), _bridge(), _snap(t), _v()))
    assert d.after and d.after[0][-1] is True, d.after
    t2 = _topic()
    with _Doors() as d2:
        _run(S._decider_execute(_Msg(topic=t2), _Ctx(), _bridge(), _snap(t2), _v()))
    assert d2.after and d2.after[0][-1] is False, d2.after


def test_decider_twin_service_work_goes_to_brain_button():
    """БЛИЗНЕЦ: работа ТО (не пробег) — кнопка Пыма через `sp_confirm_from_brain`, хвоста нет."""
    t = _topic()
    with _Doors() as d:
        door = _run(S._decider_execute(_Msg(topic=t), _Ctx(), _bridge(), _snap(t),
                                       _v(what="масло", km=None, door=S._tdec.DOOR_PYM)))
    assert door == "кнопка Пыма (ТО-заявка)", door
    assert len(d.sp) == 1 and d.sp[0][2:] == (CHAT, t, BIKE, "масло", None), d.sp
    assert d.after == [] and d.odo == [], (d.after, d.odo)


def test_decider_twin_staff_mileage_asks_pym_no_tail():
    """БЛИЗНЕЦ: пробег не доверенного — вопрос L кнопкой Пыма; ни записи, ни хвоста."""
    t = _topic()
    with _Doors() as d:
        door = _run(S._decider_execute(_Msg(topic=t), _Ctx(), _bridge(), _snap(t),
                                       _v(door=S._tdec.DOOR_PYM)))
    assert door == "кнопка Пыма (вопрос L)", door
    assert len(d.ask) == 1 and str(d.ask[0][4]) == "41973", d.ask
    assert d.after == [] and d.odo == [], (d.after, d.odo)


def test_live_case_1401_decider_record_speaks_and_floor_is_quiet():
    """ЖИВОЙ СЛУЧАЙ 25.10 14:01 целиком: фото → разбор 41973 high → решатель пишет пробег дверью
    `DOOR_ODO` → настоящий хвост `_after_mileage` (ТО-трекер + сводка) говорит сам → пол молчит.
    Прежде: пробег ложился молча, а пол говорил «числа разобрать не смог»."""
    odo, doors = [], []

    async def decide(msg, context, bridge):
        snap = {"chat": msg.chat_id, "topic": msg.message_thread_id, "bike": BIKE,
                "facts": {"role": "Пым", "mid": msg.message_id}}
        doors.append(await S._decider_execute(msg, context, bridge, snap, _v()))
    with _patch(S, _odo_confirmed=lambda *a, **k: odo.append(a), _service_interval=lambda *a, **k: 3000):
        sent, br, took, t = _photo_drive(VIS_HIGH, decider=decide)
    texts = [_ru(m) for m in sent]
    assert doors == [S._tdec.DOOR_ODO] and len(odo) == 1, (doors, odo)
    tr = br.calls.of(OP_TRACKER)
    assert len(tr) == 1 and tr[0][2].get("current_km") == KM, br.calls
    assert len(sent) == 1 and "текущий пробег 41973 км" in texts[0], texts
    assert not any("разобрать не смог" in x for x in texts), texts
    assert not any("читаю" in x for x in texts), "пол заговорил поверх квитанции"


# ============================================================================================
#  (B) ВИСЯК НАЗЫВАЕТ РАБОТЫ И БЕЗ ЗАЯВЛЕННОГО; ЗАМОК ПОВТОРОВ — ПО ЗАЯВЛЕННОМУ
# ============================================================================================
class _Loud:
    """Глушим алерт владельцу и дверь подсказки, перехватывая аргументы."""

    def __init__(self, skip=False):
        self.notes, self.hints, self.skip = [], [], skip

    def __enter__(self):
        async def _hint(context, **kw):
            self.hints.append(kw)
            return S.HINT_SKIPPED if self.skip else type("M", (), {"message_id": 1})()
        self._n = _patch(N, notify=lambda text, *a, **k: (self.notes.append(text), True)[1])
        self._h = _patch(S, _hint_send=_hint)
        self._n.__enter__()
        self._h.__enter__()
        return self

    def __exit__(self, *a):
        self._h.__exit__(*a)
        return self._n.__exit__(*a)


def _escalate_text(th_lbl, ru_lbl, age_th="7 ชม.", age_ru="7ч"):
    """Текст эскалации в теме — формат прежней функции, подпись подставляется."""
    return (f"🐀 Splinter · 📌 {BIKE}\n"
            f"🇹🇭 ⚠️ งานเซอร์วิส ({th_lbl}) ค้างนาน {age_th} ยังไม่ปิด — {S.PYM_HANDLE} ช่วยปิด/ยืนยันหน่อยครับ 🙏\n"
            f"{S._SEP}\n"
            f"🇷🇺 ⚠️ Заявка на ТО ({ru_lbl}) висит {age_ru} без закрытия — {S.PYM_HANDLE}, закрой/подтверди вручную 🙏")


def test_escalate_without_declared_names_done_work():
    t = _topic()
    br = _bridge()
    with _Loud() as L:
        _run(S._sp_escalate_stuck(_Ctx(), br, CHAT, t, BIKE, [], 7.0, "", label_kinds=["other"]))
    assert len(L.notes) == 1 and len(L.hints) == 1, (L.notes, L.hints)
    assert "(—)" not in L.notes[0] and "(прочие работы)" in L.notes[0], L.notes[0]
    h = L.hints[0]
    assert h["text"] == _escalate_text("งานอื่น ๆ", "прочие работы"), h["text"]
    assert h["state"] == ("sp_escalate", []), f"замок повторов сменил ключ: {h['state']}"
    up = br.calls.of(OP_SP_UPSERT)
    assert len(up) == 1 and up[0][2].get("note") == "escalated", up


def test_escalate_twin_declared_without_label_is_old_text():
    """БЛИЗНЕЦ: заявленное есть, подпись не передана — прежний текст и прежний ключ замка."""
    with _Loud() as L:
        _run(S._sp_escalate_stuck(_Ctx(), _bridge(), CHAT, _topic(), BIKE, ["oil"], 7.0, ""))
    assert L.hints[0]["text"] == _escalate_text("น้ำมันเครื่อง", "моторное масло"), L.hints[0]["text"]
    assert L.hints[0]["state"] == ("sp_escalate", ["oil"]), L.hints[0]["state"]
    assert "(моторное масло)" in L.notes[0], L.notes[0]


def test_escalate_label_does_not_enter_repeat_lock():
    """Подпись — только слова: ключ замка повторов = заявленное, подпись в него не входит."""
    with _Loud() as L:
        _run(S._sp_escalate_stuck(_Ctx(), _bridge(), CHAT, _topic(), BIKE, ["oil"], 7.0, "",
                                  label_kinds=["oil", "other"]))
    assert L.hints[0]["state"] == ("sp_escalate", ["oil"]), L.hints[0]["state"]
    assert "(моторное масло, прочие работы)" in L.hints[0]["text"], L.hints[0]["text"]


def test_escalate_real_lock_ignores_label():
    """Настоящий замок (`hint_dedup`): та же заявка с другой подписью — повтор, второго сообщения
    нет; другая заявка (другое заявленное) — сообщение уходит."""
    t = _topic()
    ctx = _Ctx()
    old = os.environ.get("HINTS_DEDUP")
    os.environ["HINTS_DEDUP"] = "1"
    S._HINT_SEEN = {}
    try:
        with _patch(N, notify=lambda *a, **k: True):
            _run(S._sp_escalate_stuck(ctx, _bridge(), CHAT, t, BIKE, [], 7.0, "", label_kinds=["other"]))
            _run(S._sp_escalate_stuck(ctx, _bridge(), CHAT, t, BIKE, [], 8.0, "", label_kinds=["oil"]))
            n_same = len(ctx.bot.sent)
            _run(S._sp_escalate_stuck(ctx, _bridge(), CHAT, t, BIKE, ["gear"], 9.0, ""))
    finally:
        os.environ["HINTS_DEDUP"] = old if old is not None else "0"
        S._HINT_SEEN = {}
    assert n_same == 1, f"подпись открыла замок: {[m['text'] for m in ctx.bot.sent]}"
    assert len(ctx.bot.sent) == 2, "другая заявка подавлена"
    assert "(прочие работы)" in ctx.bot.sent[0]["text"], ctx.bot.sent[0]["text"]


def _iso_ago(hours):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()


def _item(declared="", done="other", hours=7.0, status="ждёт_факт", note="", t=TOPIC):
    return {"status": status, "declared": declared, "done": done, "created_at": _iso_ago(hours),
            "note": note, "bike": BIKE, "chat_id": CHAT, "topic_id": t}


def _tick(item, **stubs):
    br = _bridge(**{OP_SP_LIST: {"ok": True, "items": [item]}})
    S._SP_LAST_SENT.clear()
    with _Loud() as L, _patch(S, **stubs):
        _run(S.scheduled_service_pending_reminder(_Ctx(), br))
    return L, br


def test_reminder_without_declared_names_done_work():
    it = _item()
    L, br = _tick(it)
    assert len(L.hints) == 1, L.hints
    h = L.hints[0]
    assert "на ТО (прочие работы), результат не отписан" in h["text"], h["text"]
    assert "(งานอื่น ๆ)" in h["text"] and "(—)" not in h["text"], h["text"]
    assert h["state"] == ("sp_stuck", it["created_at"], "ждёт_факт", []), f"ключ замка: {h['state']}"


def test_reminder_twin_declared_wins_old_text():
    """БЛИЗНЕЦ: заявленное есть — называется оно (а не сделанное), текст прежний байт-в-байт."""
    it = _item(declared="oil", done="other")
    L, br = _tick(it)
    want = (f"🐀 Splinter · 📌 {BIKE}\n"
            f"🇹🇭 ⏳ {BIKE} แจ้งเข้าเซอร์วิส (น้ำมันเครื่อง) แต่ยังไม่แจ้งผล — เสร็จหรือยังครับ?\n"
            f"{S._SEP}\n"
            f"🇷🇺 ⏳ {BIKE} на ТО (моторное масло), результат не отписан — закончили?")
    assert L.hints[0]["text"] == want, L.hints[0]["text"]
    assert L.hints[0]["state"] == ("sp_stuck", it["created_at"], "ждёт_факт", ["oil"]), L.hints[0]["state"]


def test_reminder_escalation_without_declared_names_done_work():
    it = _item(hours=50.0)
    L, br = _tick(it)
    assert len(L.hints) == 1 and len(L.notes) == 1, (L.hints, L.notes)
    assert "Заявка на ТО (прочие работы) висит 50ч" in L.hints[0]["text"], L.hints[0]["text"]
    assert L.hints[0]["state"] == ("sp_escalate", []), L.hints[0]["state"]


def test_reminder_twin_already_escalated_is_silent():
    """БЛИЗНЕЦ: эскалация уже была — ни алерта, ни сообщения в тему."""
    L, br = _tick(_item(hours=50.0, note="escalated"))
    assert L.hints == [] and L.notes == [], (L.hints, L.notes)


def test_debt_escalation_without_declared_names_done_work():
    """Ветка долга (`ждёт_подтверждения`): эскалация называет сделанное."""
    it = _item(status="ждёт_подтверждения", hours=50.0)
    L, br = _tick(it, _sp_debt_close=lambda *a, **k: None, _sp_debt_cell=lambda *a, **k: None)
    assert len(L.hints) == 1, L.hints
    assert "Заявка на ТО (прочие работы) висит 50ч" in L.hints[0]["text"], L.hints[0]["text"]
    assert "(—)" not in L.notes[0], L.notes[0]
    assert L.hints[0]["state"] == ("sp_escalate", []), L.hints[0]["state"]


def test_debt_twin_declared_equals_done_old_text():
    """БЛИЗНЕЦ: заявлено и сделано одно и то же — текст прежний байт-в-байт."""
    it = _item(status="ждёт_подтверждения", declared="oil", done="oil", hours=50.0)
    L, br = _tick(it, _sp_debt_close=lambda *a, **k: None, _sp_debt_cell=lambda *a, **k: None)
    assert L.hints[0]["text"] == _escalate_text("น้ำมันเครื่อง", "моторное масло", "50 ชม.", "50ч"), L.hints[0]["text"]
    assert L.hints[0]["state"] == ("sp_escalate", ["oil"]), L.hints[0]["state"]


# ============================================================================================
#  (C) ОТВЕТ МОЗГА БЕЗ РАЗМЕТКИ — `bot.plain_answer`
#  bot.py не импортируется (он тянет Telegram и мост): функция и её две регулярки берутся из
#  исходника того bot.py, который нашёл бы импорт, и исполняются отдельно.
# ============================================================================================
def _bot_src():
    spec = importlib.util.find_spec("bot")
    assert spec and spec.origin, "bot.py не найден на пути импорта"
    with open(spec.origin, encoding="utf-8") as f:
        return f.read()


def _plain_answer():
    src = _bot_src()
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name == "plain_answer")
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("_MD_BOLD", "_MD_RULE")
                                                  for t in n.targets))]
    assert any(isinstance(n, ast.FunctionDef) for n in keep), "в bot.py нет plain_answer"
    ns = {"re": __import__("re")}
    exec(compile(ast.Module(body=keep, type_ignores=[]), "bot.py:plain_answer", "exec"), ns)
    return ns["plain_answer"]


LIVE_ANSWER = "✅ Принял: - Текущий пробег: **41973 км** - Пробег замены масла: **41928 км**"


def test_plain_answer_strips_bold_and_rules():
    pa = _plain_answer()
    assert pa("**41973 км**") == "41973 км"
    assert pa(LIVE_ANSWER) == "✅ Принял: - Текущий пробег: 41973 км - Пробег замены масла: 41928 км", pa(LIVE_ANSWER)
    multi = "✅ Принял:\n- Текущий пробег: **41973 км**\n---\n- Пробег замены масла: **41928 км**\n  -----  \nГотово"
    assert pa(multi) == "✅ Принял:\n- Текущий пробег: 41973 км\n- Пробег замены масла: 41928 км\nГотово", pa(multi)
    assert pa("итог\n---") == "итог\n", repr(pa("итог\n---"))


def test_plain_answer_twin_leaves_everything_else():
    """БЛИЗНЕЦ: одиночная звёздочка, «-» в списке, «--» в строке, текст без разметки — как есть."""
    pa = _plain_answer()
    for s in ("5 * 3 = 15", "*курсив*", "- Текущий пробег: 41973 км\n- Масло: 41928 км",
              "итог -- 41973", "41973 км", "", "🐀 Splinter\n🇹🇭 ok\n🇷🇺 ok"):
        assert pa(s) == s, (s, pa(s))
    for x in (None, 41973, b"**41973**", ["**x**"]):
        assert pa(x) is x, x


def test_plain_answer_rule_is_a_whole_line_only():
    """Строка-линия — строка ИЗ ОДНИХ дефисов (докстринг: «строка-линия `---`»). Текст после
    «---» в той же строке линией не является, и его начало съедаться не должно."""
    pa = _plain_answer()
    for s in ("--- текст в строке с линией", "---> стрелка", "--- Итог ---", "-----41973 км",
              "Сводка:\n--- масло: 41928 км"):
        assert pa(s) == s, (s, pa(s))


def test_plain_answer_is_applied_to_brain_reply_before_chunking():
    """Руки: в `manager_reply` ответ мозга режется на куски уже очищенным — `chunk_text(plain_answer(answer), …)`."""
    tree = ast.parse(_bot_src())
    fn = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "manager_reply"]
    assert len(fn) == 1, "manager_reply не найден"
    hits = []
    for node in ast.walk(fn[0]):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "chunk_text" and node.args:
            a0 = node.args[0]
            hits.append(isinstance(a0, ast.Call) and getattr(a0.func, "id", "") == "plain_answer"
                        and [getattr(x, "id", "") for x in a0.args] == ["answer"])
    assert hits == [True], f"chunk_text в manager_reply: {hits}"


# ============================================================================================
#  (D) СЛОВА РАБОТЫ ОТ РЕШАТЕЛЯ → ВИД, А НЕ «ПРОЧИЕ РАБОТЫ» (тема 13072, 21.10: «Замена масла на
#  1200» → карточка «Сделано: прочие работы»). Мозг кладёт ключ («oil»), решатель — слова.
# ============================================================================================
def _brain_card(kind, km=KM):
    seen = []

    async def _adv(context, bridge, chat_id, topic_id, bike, declared, done, odo):
        seen.append((list(declared), list(done), odo))
    t = _topic()
    with _patch(S, _sp_advance_to_confirm=_adv, _sp_open=lambda *a, **k: {}):
        _run(S.sp_confirm_from_brain(_Ctx(), _bridge(), CHAT, t, BIKE, kind, km))
    return seen


def test_decider_words_become_the_work_kind():
    seen = _brain_card("замена масла")
    assert seen and seen[0][1] == ["oil"], seen


def test_decider_words_twin_key_and_unknown():
    """БЛИЗНЕЦЫ: ключ мозга — как был; непонятные слова — «прочие», как было."""
    assert _brain_card("oil")[0][1] == ["oil"]
    assert _brain_card("помыли и протёрли")[0][1] == ["other"]


# ============================================================================================
#  (E) ЖУРНАЛ ПРИНЯТЫХ РАБОТ ЗАКРЫВАЕТСЯ ЛЮБОЙ НАСТОЯЩЕЙ ЗАПИСЬЮ (ERROR «потеряны 9» с 15.10)
# ============================================================================================
def _info_write(chat_id, answer):
    settled = []
    br = _bridge(**{"add_" + "event": answer})
    with _patch(S, _wl_settle=lambda c, t, w, km: settled.append((c, t, list(w), km)),
                _km_event_journal=lambda *a, **k: None, _summary_note_failed=lambda *a, **k: None):
        written = S._write_info_works(br, "обслуживание", TOPIC, BIKE, ["замена передней резины"],
                                      "26542", "", chat_id=chat_id)
    return written, settled


def test_info_write_settles_the_works_journal():
    written, settled = _info_write(CHAT, {"ok": True, "saved": True})
    assert written == ["замена передней резины"], written
    assert settled == [(CHAT, TOPIC, ["замена передней резины"], "26542")], settled


def test_info_write_twin_failed_write_settles_nothing():
    """БЛИЗНЕЦ: работа не легла — снимать с ожидания нечего (список пуст, `_wl_settle` его отсечёт)."""
    written, settled = _info_write(CHAT, {"ok": False, "error": "write_failed"})
    assert written == [], written
    assert all(not s[2] for s in settled), settled


# ============================================================================================
#  (F) ПРАВДОПОДОБИЕ ПРОБЕГА СО СНИМКА — живые ошибки разбора приборки (октябрь: 15 из 52)
# ============================================================================================
_DAY = 86400.0
_NOW = 1792911700.0


def test_photo_doubt_catches_live_misreads():
    D = S._tdec.photo_km_doubt
    for misread in (14932, 14968, 11973):                       # NINJA 400 6334, 25.10
        assert D(misread, 41958, _NOW - 3600, _NOW), misread
    assert "знаков" in D(3565, 35654, _NOW - 5 * _DAY, _NOW)    # CB 650R 3503, 08.10: потеряна цифра
    assert D(38892, 36032, _NOW - 7 * _DAY, _NOW)               # CB 650R 3503, 15.10: +2860 за 7 сут
    assert D(6488, 64887, None, _NOW)                           # CBR 650R 4505, 08.10


def test_photo_doubt_twin_true_readings_pass():
    D = S._tdec.photo_km_doubt
    assert D(41973, 41958, _NOW - 3600, _NOW) == ""             # NINJA 25.10 14:01 — верное чтение
    assert D(16774, 16605, _NOW - 8 * _DAY, _NOW) == ""         # XMAX 8969: верное число Пыма
    assert D(45220, 45203, _NOW - 0.1 * _DAY, _NOW) == ""
    assert D(41900, None) == "" and D(41900, 0) == ""           # опоры нет — судят прежние правила


def _rules_facts(src_is_photo, last=41958, trusted=True):
    return {"mid": 4242, "role": "pym", "trusted": trusted, "known": {}, "last_km": last,
            "last_km_ts": _NOW - 3600, "now": _NOW, "cur_km": None, "ceiling": 30000,
            "open_kinds": {}, "photo_mids": [4242] if src_is_photo else []}


def test_rules_photo_misread_of_trusted_is_not_recorded():
    dec = {"действие": "записать", "что": "пробег", "км": 14932, "источник": 4242}
    v = S._tdec.rules(dec, _rules_facts(True))
    assert v["правило"] == "правдоподобие" and v["итог"]["действие"] == "ничего", v
    assert v["итог"]["опора"] == 41958 and v["дверь"] == "", v


def test_rules_twin_typed_number_and_plausible_photo():
    """БЛИЗНЕЦЫ: число, набранное человеком, правилом снимка не судится; верное чтение снимка
    доверенного пишется, как раньше (`DOOR_ODO`)."""
    typed = S._tdec.rules({"действие": "записать", "что": "пробег", "км": 41973, "источник": 4242},
                          _rules_facts(False))
    assert typed["правило"] != "правдоподобие" and typed["дверь"] == S._tdec.DOOR_ODO, typed
    low_typed = S._tdec.rules({"действие": "записать", "что": "пробег", "км": 14932, "источник": 4242},
                              _rules_facts(False))
    assert low_typed["правило"] == "убывание", low_typed            # прежнее правило — для слова человека
    ok_photo = S._tdec.rules({"действие": "записать", "что": "пробег", "км": 41973, "источник": 4242},
                             _rules_facts(True))
    assert ok_photo["правило"] == "" and ok_photo["дверь"] == S._tdec.DOOR_ODO, ok_photo


def test_floor_names_both_numbers_when_reading_did_not_match():
    say = F.fallback({"bike": "", "photo": True, "photo_kind": "dashboard",
                      "photo_km": "14932", "photo_ref_km": "41958"})
    assert "читаю 14932 км, а записано 41958 км" in say["ru"] and "разобрать не смог" not in say["ru"], say
    twin = F.fallback({"bike": "", "photo": True, "photo_kind": "dashboard", "photo_km": "41973"})
    assert twin["ru"] == NEW_DASH_RU, twin


def test_live_decider_misread_then_floor_says_both_numbers():
    """Живой путь: решатель в бою отвергает чтение 14932 (опора 41958) → пол в той же задаче
    говорит оба числа; в учёт не ушло ничего."""
    t = _topic()
    ctx, br = _Ctx(), _bridge()
    msg = _Msg(topic=t, photo=[object()], mid=4242)
    snap = {"chat": CHAT, "topic": t, "bike": BIKE, "kind": "photo", "user": "",
            "facts": _rules_facts(True)}
    dec = {"действие": "записать", "что": "пробег", "км": 14932, "источник": 4242}
    odo = []

    async def _decide(s, b, c):
        return dec, ""

    async def _go():
        S._PHOTO_KIND.set("dashboard")
        S._PHOTO_KM.set("14932")
        S._PHOTO_REF_KM.set("")
        before = S._SPOKE.get()
        took = await S.decider_live(msg, ctx, br, object(), kind="photo")
        await S._reply_floor_speak(ctx, msg, crashed=False, spoke_before=before)
        return took

    with _patch(S, decider_snapshot=lambda m, k="text": snap, _decider_live_decide=_decide,
                decider_paused=lambda *a, **k: None, _odo_confirmed=lambda *a, **k: odo.append(a)), \
            _patch(S._tdec, live_enabled=lambda: True):
        took = _run(_go())
    assert took is True, took
    assert odo == [], f"неправдоподобное чтение легло в учёт: {odo}"
    texts = [m.get("text", "") for m in ctx.bot.sent]
    assert any("читаю 14932 км, а записано 41958 км" in x for x in texts), texts


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
