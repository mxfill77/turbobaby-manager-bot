"""ЗАМЕНА МАСЛА ЗАДНИМ ЧИСЛОМ НИЖЕ КОЛ.I — ОДНА ПРОВЕРКА, НАСТОЯЩИЙ ВОПРОС (25.10.2026).

Живой случай: тема NINJA 400 6334, 13:28. Мозг вызвал set_service с `oil_last_km=41928`, вход
`sp_confirm_from_brain(backdated=True)` сразу выдал Пыму кнопку «подтвердить запись в ТО (кол.I)?»
— без сверки, которую делает прямой перехват. В кол.I уже было 41958; кнопку нажали, мост отказал
`oil_decreasing`, и вторая дверь масла (`_write_oil_backdated`) напечатала «понизить можно:
выбери причину и напиши пояснение» — а выбирать было не из чего: вопрос не открывался.

Что держит сьют:
  (1) вход через мозг сверяет число с кол.I так же, как перехват: ниже — вопрос, а не кнопка;
  (2) отказ второй двери открывает тот же вопрос, что у первой (`_oil_refusal`);
  (3) у вопроса задним числом понижается ТОЛЬКО кол.I — одометр, вопрос о пробеге, счётчик
      убываний и строки «событий» не трогаются;
  (3а) причину и пояснение даёт только Пым или владелец — гейт E2b не ослабел от замены кнопки
      вопросом (мост пускает понижение до 500 км без доверенного);
  (4) «Старая замена — оставить» не пишет ничего и говорит это вслух;
  у каждого случая — близнец «то же, но вопроса быть не должно».

Мост — заглушка, имена боевых операций собраны из кусков (урок 14.08, см. test_odo_lower_path).
Байк выдуман, числа — живые (41958 / 41928 / 30).
"""
import asyncio
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PRETOOL_NOPUSH", "1")
os.environ["ODO_LOWER"] = "1"           # боевой дефолт ЯВНО: сьют не зависит от .env машины
os.environ["NEVER_SILENT"] = "1"

import splinter as S          # noqa: E402
import odo_lower as L         # noqa: E402

CHAT = -1009000000043
TOPIC = 8812
BIKE = "TESTBIKE NINJA 400 9999"
RECORDED, SENT = 41958, 41928           # живые числа случая 25.10 13:28
WHO = "@testmech"                       # механик — НЕ доверенный
PYM = "Pleummmm"                        # доверенный (PYM_USERNAMES): только он исправляет кол.I

OP_REGISTER = "set_fleet" + "_oil"
OP_EVENT = "add_" + "event"
OP_TRACKER = "service" + "_upsert"


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
            return self._answers.get(name, {"ok": True})
        return _catch


def _bridge(oil_last=RECORDED, register=None):
    ans = {"find_bike": {"name": BIKE, "oil_last_km": oil_last}}
    if register is not None:
        ans[OP_REGISTER] = register
    return _FakeBridge(ans)


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 800 + len(self.sent)})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self, username=WHO.lstrip("@")):
        self.id, self.username, self.is_bot = 99043, username, False
        self.first_name = "Test"


class _Msg:
    def __init__(self, text="", username=WHO.lstrip("@")):
        self.chat_id, self.text, self.message_thread_id = CHAT, text, TOPIC
        self.caption, self.photo = None, []
        self.from_user, self.message_id, self.date = _User(username), 778, None
        self.reply_to_message = None


class _Query:
    def __init__(self, data, username=WHO.lstrip("@")):
        self.data, self.from_user, self.message = data, _User(username), _Msg()
        self.answered = []

    async def answer(self, text="", show_alert=False):
        self.answered.append(text)

    async def edit_message_reply_markup(self, **kw):
        return True

    async def edit_message_text(self, *a, **kw):
        return True


class _Upd:
    def __init__(self, q):
        self.callback_query = q


def _run(coro):
    return asyncio.run(coro)


def _clean():
    S._ODO_LOWER_PENDING.pop((CHAT, TOPIC), None)
    S._SOFT_ODO_PENDING.pop((CHAT, TOPIC), None)
    S._PENDING_MILEAGE.pop((CHAT, TOPIC), None)
    S._SVC_TOKENS.clear()
    S._ODO_DROP_CONSEC.pop(BIKE, None)


class _Stubs:
    """Соседние двери глушим и СЧИТАЕМ: предмет сьюта — что одометр не трогается."""

    def __init__(self, cur_km=41990):
        self.cur_km = cur_km
        self.odo_calls = []

    def __enter__(self):
        self.saved = {n: getattr(S, n) for n in (
            "last_mileage_in_topic", "_after_mileage", "_odo_confirmed", "_service_interval",
            "_close_service_reminder", "_emit_summary", "_clear_cycle_msgs", "_repin_info",
            "_sp_debt_close")}
        cur = self.cur_km
        S.last_mileage_in_topic = lambda c, t=None, exclude_km=None: ((cur, "high") if cur else None)

        async def _after(*a, **k):
            self.odo_calls.append(("_after_mileage", a))

        def _conf(*a, **k):
            self.odo_calls.append(("_odo_confirmed", a))

        async def _anoop(*a, **k):
            return None
        S._after_mileage = _after
        S._odo_confirmed = _conf
        S._service_interval = lambda *a, **k: 1500
        S._close_service_reminder = _anoop
        S._emit_summary = _anoop
        S._clear_cycle_msgs = _anoop
        S._repin_info = _anoop
        S._sp_debt_close = lambda *a, **k: None
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(S, k, v)
        return False


def _labels(m):
    kb = m.get("reply_markup")
    return [b.text for row in kb.inline_keyboard for b in row] if kb else []


def _callbacks(m):
    kb = m.get("reply_markup")
    return [b.callback_data for row in kb.inline_keyboard for b in row] if kb else []


def _brain(oil_last=RECORDED, km=SENT, cur_km=41990):
    """Вход через мозг — ровно как его зовёт bot.py после блока E2b."""
    _clean()
    br, ctx = _bridge(oil_last), _Ctx()
    with _Stubs(cur_km):
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", km, True))
    return ctx.bot.sent, br


# ============================================================================================
#  (1) ВХОД ЧЕРЕЗ МОЗГ СВЕРЯЕТ ЧИСЛО С КОЛ.I — ГЛАВНЫЙ СЛУЧАЙ 25.10
# ============================================================================================
def test_brain_path_below_column_asks_instead_of_doomed_card():
    sent, br = _brain()
    assert len(sent) == 1, sent
    body = sent[0]["text"]
    # (а) обречённой кнопки «подтвердить запись в кол.I» больше нет
    assert "подтвердить запись в ТО" not in body, body
    assert not any(c.startswith("svc:oilbk:") for c in _callbacks(sent[0])), _callbacks(sent[0])
    # (б) расхождение названо всеми тремя числами, и это вопрос про замену задним числом
    for n in ("41958", "41928", "30"):
        assert n in body, (n, body)
    assert "задним числом" in body and "текущий пробег байка не трогаю" in body, body
    assert "Причину выбирает и пояснение пишет @Pleummmm или владелец" in body, body
    # (в) выбор ПРЕДЛОЖЕН: три причины + «старая замена»
    labels = _labels(sent[0])
    assert len(labels) == 4, labels
    assert any("Старая замена" in x and "41958" in x for x in labels), labels
    # (г) вопрос открыт, метит в кол.I и помнит «одометр не трогать»
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["register"] == "oil" and low["odo_keep"] is True, low
    assert (low["recorded"], low["sent"]) == (RECORDED, SENT), low
    # (д) в живую таблицу не ушло ничего
    assert br.calls.of(OP_REGISTER) == [], br.calls


def test_brain_path_repeat_points_to_the_open_question():
    """Живой круг 6334 (06:20 → 06:22 → 06:28 UTC): на ответ Пыма «ยืนยัน» мозг снова звал
    set_service. Теперь второго такого же вопроса нет — короткая ссылка на открытый, его кнопки
    и состояние те же."""
    _clean()
    br, ctx = _bridge(), _Ctx()
    with _Stubs():
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        first = dict(S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) or {})
        toks = set(S._SVC_TOKENS)
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
    sent = ctx.bot.sent
    assert len(sent) == 2, sent
    assert _callbacks(sent[0]) and not _callbacks(sent[1]), [m.get("reply_markup") for m in sent]
    assert "уже открыт" in sent[1]["text"] and "41958" in sent[1]["text"], sent[1]["text"]
    assert set(S._SVC_TOKENS) == toks, "второй круг выпустил новые метки"
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) == first, "второй круг переписал вопрос"


def test_brain_path_repeat_twin_other_number_asks_anew():
    """БЛИЗНЕЦ: другое число — это другой вопрос, его задаём заново."""
    _clean()
    br, ctx = _bridge(), _Ctx()
    with _Stubs():
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", 41900, True))
    sent = ctx.bot.sent
    assert len(sent) == 2 and _callbacks(sent[1]), sent
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC))["sent"] == 41900


def test_brain_path_twin_above_column_keeps_the_card():
    """БЛИЗНЕЦ: число ВЫШЕ кол.I — прежняя кнопка Пыму, вопроса нет."""
    sent, br = _brain(oil_last=41000)
    assert len(sent) == 1 and any(c.startswith("svc:oilbk:") for c in _callbacks(sent[0])), sent
    assert "подтвердить запись в ТО" in sent[0]["text"], sent[0]["text"]
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


def test_brain_path_twin_unreadable_column_keeps_the_card():
    """БЛИЗНЕЦ: кол.I не прочиталась (0/пусто) — сверять нечем, кнопка прежняя."""
    sent, br = _brain(oil_last=0)
    assert len(sent) == 1 and any(c.startswith("svc:oilbk:") for c in _callbacks(sent[0])), sent
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


def test_brain_path_equal_to_column_says_already_recorded():
    sent, br = _brain(oil_last=SENT)
    assert len(sent) == 1 and not _callbacks(sent[0]), sent
    assert "уже записана" in sent[0]["text"], sent[0]["text"]
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


def test_brain_path_above_odometer_is_a_wrong_number():
    """Замена «в будущем» (выше текущего одометра темы) — ошибка числа, без кнопок."""
    sent, br = _brain(oil_last=41000, km=42500, cur_km=41990)
    assert len(sent) == 1 and not _callbacks(sent[0]), sent
    assert "не прошёл проверку" in sent[0]["text"] and "41990" in sent[0]["text"], sent[0]["text"]


# ============================================================================================
#  (2) ОТКАЗ ВТОРОЙ ДВЕРИ ОТКРЫВАЕТ ВОПРОС, А НЕ ОБЕЩАЕТ ЕГО
# ============================================================================================
OIL_LOWER_RES = {"ok": False, "error": "oil_decreasing", "old_oil": RECORDED, "new_oil": SENT}
HOLLOW = "понизить можно: выбери причину и напиши пояснение своими словами"


def _door(res, lower_on=True):
    _clean()
    br, ctx = _bridge(register=res), _Ctx()
    old = os.environ.get("ODO_LOWER", "1")
    os.environ["ODO_LOWER"] = "1" if lower_on else "0"
    try:
        with _Stubs():
            _run(S._write_oil_backdated(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
    finally:
        os.environ["ODO_LOWER"] = old
    return ctx.bot.sent, br


def test_backdated_door_refusal_opens_the_question():
    sent, br = _door(OIL_LOWER_RES)
    assert sent, "дверь промолчала — это запрещено правилом 1"
    last = sent[-1]
    # (а) пустого обещания больше нет — вместо него выбор кнопками
    assert HOLLOW not in last["text"], last["text"]
    assert len(_labels(last)) == 4, _labels(last)
    for n in ("41958", "41928", "30"):
        assert n in last["text"], (n, last["text"])
    # (б) вопрос открыт и знает, что одометр трогать нельзя
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["register"] == "oil" and low["odo_keep"] is True, low


def test_backdated_door_twin_other_refusal_keeps_words():
    """БЛИЗНЕЦ: отказ НЕ про понижение — прежние слова, вопроса нет."""
    sent, br = _door({"ok": False, "error": "write_failed"})
    assert sent and not _callbacks(sent[-1]), sent
    assert "строка не записалась" in sent[-1]["text"], sent[-1]["text"]
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


def test_backdated_door_twin_rollback_knob_keeps_words():
    """ОТКАТ: `ODO_LOWER=0` — прежний путь байт-в-байт (слова без вопроса)."""
    sent, br = _door(OIL_LOWER_RES, lower_on=False)
    assert sent and not _callbacks(sent[-1]), sent
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


def test_first_door_question_has_no_keep_button():
    """БЛИЗНЕЦ: у первой двери (`_write_oil`, масло на текущем пробеге) «старой замены» нет —
    там число и есть одометр, и смысла «более старая замена» у него нет."""
    _clean()
    br, ctx = _bridge(register=OIL_LOWER_RES), _Ctx()
    with _Stubs():
        _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
    last = ctx.bot.sent[-1]
    assert len(_labels(last)) == 3, _labels(last)
    assert not any(c.startswith("svc:lowk:") for c in _callbacks(last)), _callbacks(last)
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["odo_keep"] is False, low


# ============================================================================================
#  (3) ПУТЬ ЦЕЛИКОМ: ПОНИЖАЕТСЯ ТОЛЬКО КОЛ.I
# ============================================================================================
def _walk(reason, words):
    """Вопрос через мозг → Пым жмёт причину → Пым пишет пояснение. Вопрос о пробеге темы висит."""
    _clean()
    br, ctx = _bridge(), _Ctx()
    S._PENDING_MILEAGE[(CHAT, TOPIC)] = ("41990", BIKE, None, False)
    with _Stubs() as st:
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == reason)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}", username=PYM)), ctx, br))
        _run(S.handle_mileage_confirm(_Msg(words, username=PYM), ctx, br, words))
    return ctx.bot.sent, br, st


def test_full_path_lowers_only_the_column():
    words = "в прошлый раз записали пробег с приборки, а меняли на 41928"
    sent, br, st = _walk(L.OLD_WRONG, words)
    try:
        # (а) кол.I понижена веткой исправления: число, причина со словами, автор
        reg = br.calls.of(OP_REGISTER)
        assert len(reg) == 1, br.calls
        kw = reg[0][2]
        assert kw.get("oil_km") == SENT and kw.get("confirmed") is True, kw
        assert words in kw.get("fix_reason", "") and kw.get("fixed_by") == "@" + PYM, kw
        # (б) ТО-трекер узнал только пробег замены — текущий одометр не передан
        tr = br.calls.of(OP_TRACKER)
        assert len(tr) == 1, br.calls
        assert tr[0][2].get("last_service_km") == SENT and "current_km" not in tr[0][2], tr
        # (в) одометр не тронут НИ ОДНИМ следом
        assert st.odo_calls == [], st.odo_calls
        assert br.calls.of(OP_EVENT) == [], br.calls.of(OP_EVENT)
        assert S._PENDING_MILEAGE.get((CHAT, TOPIC)) is not None, "вопрос о пробеге темы сняли"
        assert BIKE not in S._ODO_DROP_CONSEC, "счётчик убываний одометра вырос"
        # (г) квитанция говорит правду: кол.I исправлена, пробег не тронут, слова дословно
        rec = sent[-1]["text"]
        assert "исправлено задним числом" in rec and "не трогал" in rec, rec
        assert "41958" in rec and "41928" in rec and words in rec, rec
        assert "43428" in rec, rec               # следующее ТО = 41928 + 1500
        assert "Пробег" not in rec and "понижен" not in rec, rec   # не «пробег понижен»
        assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None
    finally:
        S._PENDING_MILEAGE.pop((CHAT, TOPIC), None)


def test_full_path_odometer_replaced_writes_no_odometer_event():
    """Причина «одометр заменён» задним числом: строка «одометр заменён на N» соврала бы числом
    (N здесь — пробег прошлой замены масла), поэтому её нет; причина уезжает в ветку исправления."""
    sent, br, st = _walk(L.ODO_REPLACED, "поставили новый одометр, масло меняли уже на нём")
    try:
        assert br.calls.of(OP_EVENT) == [], br.calls.of(OP_EVENT)
        reg = br.calls.of(OP_REGISTER)
        assert len(reg) == 1 and "одометр заменён" in reg[0][2].get("fix_reason", ""), reg
        assert st.odo_calls == [], st.odo_calls
    finally:
        S._PENDING_MILEAGE.pop((CHAT, TOPIC), None)


def test_full_path_bridge_refusal_still_speaks():
    """Мост отказал и ветке исправления — человек слышит слова, пояснение названо сохранённым."""
    _clean()
    br = _bridge(register={"ok": False, "error": "oil_drop_needs_trusted", "drop": 30,
                           "threshold": 20, "old_oil": RECORDED})
    ctx = _Ctx()
    with _Stubs() as st:
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.OLD_WRONG)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}", username=PYM)), ctx, br))
        words = "записали с приборки, а меняли раньше"
        _run(S.handle_mileage_confirm(_Msg(words, username=PYM), ctx, br, words))
    last = ctx.bot.sent[-1]["text"]
    assert "Пояснение я сохранил" in last and words in last, last
    assert br.calls.of(OP_TRACKER) == [] and st.odo_calls == [], (br.calls, st.odo_calls)


# ============================================================================================
#  (3а) ДОВЕРИЕ НЕ ОСЛАБЕЛО: кол.I задним числом исправляет только Пым или владелец
#  Прежде вход через мозг писал кол.I только кнопкой Пыма (гейт E2b). Мост пускает понижение до
#  500 км без доверенного — значит, без замка вопрос сделал бы ПОНИЖЕНИЕ проще, чем повышение.
# ============================================================================================
def test_untrusted_cannot_pick_the_reason_on_backdated_question():
    _clean()
    br, ctx = _bridge(), _Ctx()
    with _Stubs():
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.OLD_WRONG)
        q = _Query(f"svc:lowr:{tok}")                      # механик
        _run(S.handle_service_button(_Upd(q), ctx, br))
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["reason"] == "", f"механик выбрал причину: {low}"
    assert any("Выбирает" in a for a in q.answered), q.answered
    assert tok in S._SVC_TOKENS, "кнопка обязана жить — Пым нажмёт сам"
    assert br.calls.of(OP_REGISTER) == [], br.calls


def test_untrusted_text_is_not_taken_as_explanation():
    """Пым выбрал причину, а следом пишет механик: его текст НЕ пояснение и НЕ съедается."""
    _clean()
    br, ctx = _bridge(), _Ctx()
    with _Stubs() as st:
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.OLD_WRONG)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}", username=PYM)), ctx, br))
        words = "да меняли на 41928, точно помню"
        took = _run(S.handle_mileage_confirm(_Msg(words), ctx, br, words))   # механик
    assert took is False, "чужой текст съеден дверью понижения"
    assert br.calls.of(OP_REGISTER) == [] and st.odo_calls == [], br.calls
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["reason"] == L.OLD_WRONG, "вопрос обязан остаться открытым для Пыма"


def test_untrusted_twin_plain_lowering_unchanged():
    """БЛИЗНЕЦ: у ОБЫЧНОГО понижения (первая дверь) правило 23.08 прежнее — причину выбирает
    тот, кто прислал число; замок задним числом туда не протёк."""
    _clean()
    br, ctx = _bridge(register=OIL_LOWER_RES), _Ctx()
    with _Stubs():
        _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.OLD_WRONG)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))   # механик
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["reason"] == L.OLD_WRONG, low


# ============================================================================================
#  (4) «СТАРАЯ ЗАМЕНА — ОСТАВИТЬ» НЕ ПИШЕТ НИЧЕГО
# ============================================================================================
def test_keep_button_writes_nothing_and_says_so():
    _clean()
    br, ctx = _bridge(), _Ctx()
    with _Stubs() as st:
        _run(S.sp_confirm_from_brain(ctx, br, CHAT, TOPIC, BIKE, "oil", SENT, True))
        before = len(br.calls)
        tok = next(t for t, d in S._SVC_TOKENS.items() if d.get("kind") == "odo_lower_keep")
        q = _Query(f"svc:lowk:{tok}")
        _run(S.handle_service_button(_Upd(q), ctx, br))
    assert len(br.calls) == before, br.calls[before:]
    assert st.odo_calls == [], st.odo_calls
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "вопрос не закрыт"
    rec = ctx.bot.sent[-1]["text"]
    assert "Оставил как есть" in rec and "41958" in rec and "41928" in rec, rec


def test_keep_button_twin_on_plain_question_is_refused():
    """БЛИЗНЕЦ: метка «оставить» на вопросе ОБЫЧНОГО понижения не исполняется — вопрос живёт."""
    _clean()
    br, ctx = _bridge(register=OIL_LOWER_RES), _Ctx()
    with _Stubs():
        _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
        tok = S._svc_put({"kind": "odo_lower_keep", "chat": CHAT, "topic": TOPIC, "bike": BIKE})
        q = _Query(f"svc:lowk:{tok}")
        _run(S.handle_service_button(_Upd(q), ctx, br))
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is not None, "обычный вопрос закрыт чужой меткой"
    assert any("закрыт" in a for a in q.answered), q.answered


# ============================================================================================
#  (5) РЕШЕНИЕ — ЧИСТЫЕ СЛОВА `odo_lower`
# ============================================================================================
def test_odo_lower_backdated_words():
    say = L.ask("X", RECORDED, SENT, backdated=True)
    assert say["drop"] == 30 and "Старая замена" in say["ru"] and "кол.I" in say["ru"], say
    assert L.ask("X", RECORDED, RECORDED + 5, backdated=True) is None
    rec = L.receipt("X", RECORDED, SENT, L.OLD_WRONG, "слова", backdated=True, next_km=43428)
    assert "не трогал" in rec["ru"] and "43428" in rec["ru"] and "Пробег" not in rec["ru"], rec
    plain = L.receipt("X", RECORDED, SENT, L.OLD_WRONG, "слова")
    assert "Пробег" in plain["ru"] and "понижен" in plain["ru"], plain   # прежняя квитанция цела
    keep = L.keep_receipt("X", RECORDED, SENT)
    assert "не пишу" in keep["ru"] and "41958" in keep["ru"], keep


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
