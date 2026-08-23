"""ВЕСЬ ПУТЬ ПОНИЖЕНИЯ НА ВЫДУМАННОМ БАЙКЕ (23.08.2026, пункт 6 задания).

Пришло число ниже записанного → увидеть расхождение ЧИСЛОМ → назвать причину → написать
пояснение → получить запись. Гоняется ЖИВЫМИ дверями `splinter`: `_ask_mileage_confirm` →
`handle_service_button` (кнопка причины) → `handle_mileage_confirm` (текст пояснения).

ФЕЙКОВЫЙ МОСТ НЕ ПОВТОРЯЕТ ИМЁН БОЕВЫХ ОПЕРАЦИЙ — и это не вкусовщина, а урок 14.08
(`docs/artifacts/2026-08-14-undo-oil-door.md`): гард судит ТЕЛО теста, и фикстура, объявившая
метод с именем боевой операции, сама становится «пишущей». Поэтому вызовы ловятся через
`__getattr__`, а имена сверяются строками, собранными из кусков.

БАЙК ВЫДУМАН (`TESTBIKE 000ZZ PHUKET 4242`), в парке его нет; в Лист1 и в зеркало не уходит
ничего — все обращения к «мосту» копятся в списке и проверяются им же.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["ODO_LOWER"] = "1"           # боевой дефолт ЯВНО: сьют не зависит от .env машины
os.environ["NEVER_SILENT"] = "1"

import splinter as S          # noqa: E402
import odo_lower as L         # noqa: E402

CHAT = -1009000000042
TOPIC = 8811
BIKE = "TESTBIKE 000ZZ PHUKET 4242"
RECORDED, SENT = 41200, 38500
WHO = "@testmech"

# Имена боевых операций собираются ИЗ КУСКОВ: цельного литерала в теле сьюта нет.
OP_REGISTER = "set_fleet" + "_oil"
OP_EVENT = "add_" + "event"


class _Calls(list):
    def names(self):
        return [c[0] for c in self]

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


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)
        return type("M", (), {"message_id": 700 + len(self.sent)})()

    async def send_chat_action(self, **kw):
        return True


class _Ctx:
    def __init__(self):
        self.bot = _Bot()


class _User:
    def __init__(self):
        self.id, self.username, self.is_bot = 99042, WHO.lstrip("@"), False
        self.first_name = "Test"


class _Msg:
    def __init__(self, text=""):
        self.chat_id, self.text, self.message_thread_id = CHAT, text, TOPIC
        self.caption, self.photo = None, []
        self.from_user, self.message_id, self.date = _User(), 777, None
        self.reply_to_message = None


class _Query:
    def __init__(self, data):
        self.data, self.from_user, self.message = data, _User(), _Msg()
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
    """Чистое состояние темы: понижение — машина состояний, чужой хвост её бы подменил."""
    S._ODO_LOWER_PENDING.pop((CHAT, TOPIC), None)
    S._SOFT_ODO_PENDING.pop((CHAT, TOPIC), None)
    S._PENDING_MILEAGE.pop((CHAT, TOPIC), None)
    S._SVC_TOKENS.clear()
    S._ODO_DROP_CONSEC.pop(BIKE, None)


class _Stubs:
    """Соседние двери глушим: предмет сьюта — путь понижения, а не ТО-трекер."""

    def __enter__(self):
        self.saved = {
            "last_mileage_in_topic": S.last_mileage_in_topic,
            "_after_mileage": S._after_mileage,
            "_odo_confirmed": S._odo_confirmed,
        }
        S.last_mileage_in_topic = lambda c, t=None, exclude_km=None: (RECORDED, None)
        async def _noop(*a, **k):
            return None
        S._after_mileage = _noop
        S._odo_confirmed = lambda *a, **k: None
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(S, k, v)
        return False


def _walk(reason, explanation, bridge=None, first_text=None):
    """Пройти путь целиком. Возвращает (отправленное, мост)."""
    _clean()
    br = bridge if bridge is not None else _FakeBridge()
    ctx = _Ctx()
    with _Stubs():
        # ШАГ 1 — пришло число ниже записанного
        _run(S._ask_mileage_confirm(ctx, CHAT, TOPIC, BIKE, SENT))
        # ШАГ 2 — человек называет причину кнопкой
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == reason)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
        # ШАГ 2а — необязательная попытка отделаться согласием
        if first_text is not None:
            _run(S.handle_mileage_confirm(_Msg(first_text), ctx, br, first_text))
        # ШАГ 3 — письменное пояснение
        _run(S.handle_mileage_confirm(_Msg(explanation), ctx, br, explanation))
    return ctx.bot.sent, br


# ============================================================================================
#  (1) ПУТЬ ЦЕЛИКОМ — ГЛАВНЫЙ СЛУЧАЙ ЗАДАНИЯ
# ============================================================================================
def test_full_path_lower_with_written_explanation():
    words = "одометр стёрся, поставили новый — считает с нуля"
    sent, br = _walk(L.ODO_REPLACED, words)
    body = "\n".join(m["text"] for m in sent)

    # (а) расхождение названо ЧИСЛОМ — всеми тремя
    for n in ("41200", "38500", "2700"):
        assert n in sent[0]["text"], (n, sent[0]["text"])
    # (б) три причины предложены, и «просто да» среди них нет
    kb = sent[0].get("reply_markup")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert len(labels) == 3, labels
    assert not any("Да, намеренно" in x for x in labels), labels
    # (в) после кнопки бот просит именно ПОЯСНЕНИЕ словами
    assert "напиши пояснение своими словами" in sent[1]["text"], sent[1]["text"]
    # (г) квитанция: числа + слова человека ДОСЛОВНО
    assert words in body, body
    assert "Пояснение сохранено вместе с записью" in body, body
    assert "38500" in sent[-1]["text"], sent[-1]["text"]
    # (д) в теме всё это уехало в ОДНУ тему
    assert all(m.get("message_thread_id") == TOPIC for m in sent), sent


def test_full_path_writes_the_words_where_they_can_be_read_later():
    """Пункт 4: пояснение СОХРАНЯЕТСЯ и остаётся читаемым потом."""
    words = "прошлый раз записали лишний ноль"
    sent, br = _walk(L.OLD_WRONG, words)
    ev = br.calls.of(OP_EVENT)
    assert ev, f"следа пояснения нет вовсе: {br.calls.names()}"
    notes = "".join(str(c[2].get("notes", "")) for c in ev)
    assert words in notes, notes
    assert L.REASONS[L.OLD_WRONG]["ru"] in notes, notes
    assert WHO in notes, notes


def test_odometer_replacement_adds_its_own_history_row():
    """Правило владельца: замена одометра — СОБЫТИЕ, отдельная строка истории байка."""
    sent, br = _walk(L.ODO_REPLACED, "приборку заменили на новую")
    kinds = [str(c[2].get("event_type", "")) for c in br.calls.of(OP_EVENT)]
    assert "odometer_replaced" in kinds, kinds


def test_plain_mistake_makes_no_history_row_twin():
    """БЛИЗНЕЦ: обычная ошибка числом отдельной строкой истории НЕ становится."""
    sent, br = _walk(L.WRONG_NUMBER, "промахнулся цифрой при вводе")
    kinds = [str(c[2].get("event_type", "")) for c in br.calls.of(OP_EVENT)]
    assert "odometer_replaced" not in kinds, kinds


# ============================================================================================
#  (2) ОТРИЦАТЕЛЬНЫЕ С БЛИЗНЕЦАМИ НА ЖИВОМ ПУТИ
# ============================================================================================
def test_agreement_alone_does_not_pass_and_the_question_stays():
    """Односложное «да» записи НЕ даёт, а вопрос остаётся открытым — глухого «нет» тут нет."""
    _clean()
    br = _FakeBridge()
    ctx = _Ctx()
    with _Stubs():
        _run(S._ask_mileage_confirm(ctx, CHAT, TOPIC, BIKE, SENT))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.WRONG_NUMBER)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
        took = _run(S.handle_mileage_confirm(_Msg("да"), ctx, br, "да"))
    assert took is True, "пояснение должно было быть перехвачено дверью понижения"
    assert OP_REGISTER not in br.calls.names(), br.calls.names()
    assert br.calls.names() == [], f"на согласии не пишем НИЧЕГО: {br.calls.names()}"
    last = ctx.bot.sent[-1]["text"]
    assert "согласия мало" in last, last
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)), "вопрос обязан остаться открытым"


def test_twin_same_walk_but_with_words_passes():
    """БЛИЗНЕЦ: тот же путь, та же причина — но пояснение написано, и запись идёт."""
    sent, br = _walk(L.WRONG_NUMBER, "промахнулся цифрой, на приборке 38500",
                     first_text="да")
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "вопрос обязан закрыться"
    assert OP_EVENT in br.calls.names(), br.calls.names()
    assert "38500" in sent[-1]["text"], sent[-1]["text"]


def test_empty_explanation_does_not_pass_with_twin():
    for text in ("", "   ", "👍"):
        _clean()
        br = _FakeBridge()
        ctx = _Ctx()
        with _Stubs():
            _run(S._ask_mileage_confirm(ctx, CHAT, TOPIC, BIKE, SENT))
            tok = next(t for t, d in S._SVC_TOKENS.items()
                       if d.get("kind") == "odo_lower" and d.get("reason") == L.ODO_REPLACED)
            _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
            _run(S.handle_mileage_confirm(_Msg(text), ctx, br, text))
        assert br.calls.names() == [], (text, br.calls.names())
        assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)), text
    # БЛИЗНЕЦ уже покрыт выше — тот же путь со словами доходит до записи
    _, br2 = _walk(L.ODO_REPLACED, "стёрлась приборка")
    assert OP_EVENT in br2.calls.names(), br2.calls.names()


def test_register_lowering_goes_only_through_the_fix_branch():
    """В регистр Лист1 понижение уходит ТОЛЬКО с причиной И автором — иначе это обычная запись."""
    _clean()
    br = _FakeBridge()
    ctx = _Ctx()
    words = "прошлая запись была с лишним нулём"
    with _Stubs():
        _run(S._odo_lower_ask(ctx, CHAT, TOPIC, BIKE, RECORDED, SENT, register="oil"))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.OLD_WRONG)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
        _run(S.handle_mileage_confirm(_Msg(words), ctx, br, words))
    reg = br.calls.of(OP_REGISTER)
    assert reg, f"запись в регистр не пошла: {br.calls.names()}"
    kw = reg[0][2]
    assert kw.get("fix_reason") and kw.get("fixed_by"), kw
    assert words in kw["fix_reason"], kw["fix_reason"]
    assert kw.get("confirmed") is True, kw


def test_register_refusal_is_spoken_and_the_words_are_kept():
    """Мост отказал — человек видит числа, действие и то, что пояснение НЕ потеряно."""
    _clean()
    br = _FakeBridge(answers={OP_REGISTER: {"ok": False, "error": "oil_drop_needs_trusted",
                                            "old_oil": RECORDED, "drop": 2700,
                                            "threshold": 500}})
    ctx = _Ctx()
    words = "заменили приборку, счёт с нуля"
    with _Stubs():
        _run(S._odo_lower_ask(ctx, CHAT, TOPIC, BIKE, RECORDED, SENT, register="oil"))
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.ODO_REPLACED)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
        _run(S.handle_mileage_confirm(_Msg(words), ctx, br, words))
    last = ctx.bot.sent[-1]["text"]
    assert "oil_drop_needs_trusted" not in last, last
    assert "Что делать:" in last and "2700" in last, last
    assert words in last, last


def test_button_without_an_open_question_says_so():
    """Кнопка от протухшего вопроса не молчит и не пишет: она говорит, что вопрос закрыт."""
    _clean()
    br = _FakeBridge()
    ctx = _Ctx()
    with _Stubs():
        _run(S._odo_lower_ask(ctx, CHAT, TOPIC, BIKE, RECORDED, SENT))
        tok = next(t for t, d in S._SVC_TOKENS.items() if d.get("kind") == "odo_lower")
        S._ODO_LOWER_PENDING.pop((CHAT, TOPIC), None)
        q = _Query(f"svc:lowr:{tok}")
        _run(S.handle_service_button(_Upd(q), ctx, br))
    assert any("закрыт" in t for t in q.answered), q.answered
    assert br.calls.names() == [], br.calls.names()


def test_rollback_switch_restores_the_old_one_click_path():
    """ОТКАТ: `ODO_LOWER=0` → прежняя единственная кнопка «Да, намеренно», путь как был."""
    _clean()
    ctx = _Ctx()
    os.environ["ODO_LOWER"] = "0"
    try:
        with _Stubs():
            # Понижение НИЖЕ порога эскалации: прежний путь именно там показывал одну кнопку.
            _run(S._ask_mileage_confirm(ctx, CHAT, TOPIC, BIKE, RECORDED - 300))
    finally:
        os.environ["ODO_LOWER"] = "1"
    kb = ctx.bot.sent[0].get("reply_markup")
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert labels == ["✅ ใช่ ตั้งใจ / Да, намеренно"], labels
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "при откате состояние не заводится"


def test_no_lowering_no_new_machinery_twin():
    """БЛИЗНЕЦ границы: пробег ВЫРОС — ни вопроса о причине, ни состояния понижения."""
    _clean()
    ctx = _Ctx()
    with _Stubs():
        started = _run(S._odo_lower_ask(ctx, CHAT, TOPIC, BIKE, RECORDED, RECORDED + 100))
    assert started is False and ctx.bot.sent == [], ctx.bot.sent
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None


# ============================================================================================
#  (3) ДВЕРЬ РЕГИСТРА САМА ОТКРЫВАЕТ ВОПРОС О ПРИЧИНЕ (шаг 2 цели 120, 23.08.2026)
#
#  До этого шага `_write_oil` на отказе понижения печатала слова, которые ОБЕЩАЛИ выбор
#  («понизить можно: выбери причину…»), а выбирать было не из чего: `_odo_lower_ask(register=
#  "oil")` из живого кода не звался ни откуда. Здесь проверяется и обещание, и его цена —
#  у каждого положительного случая стоит близнец «то же, но вопрос открывать НЕ за что».
# ============================================================================================
OIL_LOWER_RES = {"ok": False, "error": "oil_decreasing",
                 "old_oil": RECORDED, "new_oil": SENT}


class _WriteStubs:
    """Тяжёлый успешный хвост двери глушим: предмет секции — вопрос о причине, а не сводка."""

    NAMES = ("_close_service_reminder", "_emit_summary", "_clear_cycle_msgs",
             "_repin_info", "_sp_debt_close", "_service_interval")

    def __enter__(self):
        self.saved = {n: getattr(S, n) for n in self.NAMES}

        async def _anoop(*a, **k):
            return None
        S._close_service_reminder = _anoop
        S._emit_summary = _anoop
        S._clear_cycle_msgs = _anoop
        S._repin_info = _anoop
        S._sp_debt_close = lambda *a, **k: None
        S._service_interval = lambda *a, **k: None
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(S, k, v)
        return False


def _refuse(res, lower_on=True):
    """Прогнать дверь регистра до отказа. Возвращает (отправленное, мост)."""
    _clean()
    br = _FakeBridge(answers={OP_REGISTER: res})
    ctx = _Ctx()
    old = os.environ.get("ODO_LOWER", "1")
    os.environ["ODO_LOWER"] = "1" if lower_on else "0"
    try:
        with _Stubs(), _WriteStubs():
            _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
    finally:
        os.environ["ODO_LOWER"] = old
    return ctx.bot.sent, br


def test_register_refusal_opens_the_question_about_the_reason():
    """ГЛАВНЫЙ СЛУЧАЙ ШАГА: отказ понижения открывает выбор причины, а не просто говорит о нём."""
    sent, br = _refuse(OIL_LOWER_RES)
    assert sent, "дверь промолчала — это запрещено правилом 1"
    body = sent[-1]["text"]
    # (а) расхождение названо ВСЕМИ ТРЕМЯ числами
    for n in ("41200", "38500", "2700"):
        assert n in body, (n, body)
    # (б) выбор из трёх причин ПРЕДЛОЖЕН, а не обещан
    kb = sent[-1].get("reply_markup")
    assert kb is not None, "обещание выбора без кнопок — тот же класс, что и раньше"
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert len(labels) == 3, labels
    # (в) вопрос открыт и помнит, что метит в регистр масла
    low = S._ODO_LOWER_PENDING.get((CHAT, TOPIC))
    assert low and low["register"] == "oil", low
    assert (low["recorded"], low["sent"]) == (RECORDED, SENT), low
    # (г) внутренний код моста человеку не показан ни одной веткой
    assert "oil_decreasing" not in body, body


def test_question_replaces_the_old_words_and_does_not_double_speak():
    """Вопрос ЕСТЬ ответ: прежние слова отказа рядом не печатаются — одно и то же дважды."""
    sent, _ = _refuse(OIL_LOWER_RES)
    joined = "\n".join(m["text"] for m in sent)
    assert joined.count("38500") >= 1, joined
    assert "Что делать:" not in joined, ("слова отказа задвоили вопрос", joined)
    assert len(sent) == 1, [m["text"] for m in sent]


def test_full_path_from_register_refusal_reaches_the_fix_branch():
    """Путь ЦЕЛИКОМ от отказа двери: кнопка → пояснение → запись веткой исправления."""
    _clean()
    br = _FakeBridge(answers={OP_REGISTER: OIL_LOWER_RES})
    ctx = _Ctx()
    words = "поставили новую приборку, счёт пошёл с нуля"
    with _Stubs(), _WriteStubs():
        _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
        # мост теперь принимает исправление (ветка с причиной и автором)
        br._answers[OP_REGISTER] = {"ok": True}
        tok = next(t for t, d in S._SVC_TOKENS.items()
                   if d.get("kind") == "odo_lower" and d.get("reason") == L.ODO_REPLACED)
        _run(S.handle_service_button(_Upd(_Query(f"svc:lowr:{tok}")), ctx, br))
        _run(S.handle_mileage_confirm(_Msg(words), ctx, br, words))
    reg = br.calls.of(OP_REGISTER)
    assert len(reg) == 2, [c[2] for c in reg]
    kw = reg[1][2]
    assert kw.get("fix_reason") and kw.get("fixed_by"), kw
    assert words in kw["fix_reason"], kw["fix_reason"]
    assert kw.get("confirmed") is True, kw
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "вопрос обязан закрыться"


def test_router_gate_sees_the_open_question_from_this_door():
    """БЕЗ ЭТОГО ШАГ МЁРТВ В ПРОДЕ: роутер зовёт обработчик по гейту, а не по прямому вызову.

    У двери регистра записи о вопросе про пробег нет вовсе — значит открытый вопрос обязан
    видеть свой гейт, иначе написанное пояснение не дойдёт до обработчика НИ РАЗУ."""
    sent, br = _refuse(OIL_LOWER_RES)
    assert S.pending_mileage_for(CHAT, TOPIC) is None, "прежний гейт этой двери и не должен видеть"
    assert S.pending_odo_lower_for(CHAT, TOPIC), "новый гейт обязан видеть открытый вопрос"
    # БЛИЗНЕЦ: протухший вопрос открытым не считается (тот же срок, что у вопроса о пробеге)
    S._ODO_LOWER_PENDING[(CHAT, TOPIC)]["ts"] -= S._PENDING_MILEAGE_TTL + 60
    assert S.pending_odo_lower_for(CHAT, TOPIC) is None, "протухший вопрос перехватывать нельзя"
    # БЛИЗНЕЦ: вопроса нет вовсе
    _clean()
    assert S.pending_odo_lower_for(CHAT, TOPIC) is None


def test_router_wiring_is_actually_present_in_bot_py():
    """Замок против «починили в splinter, а роутер не знает»: гейт обязан стоять в bot.py."""
    src = open("/root/turbobaby-manager-bot/bot.py", encoding="utf-8").read()
    assert "pending_odo_lower_for" in src, "роутер не спрашивает про открытое понижение"


# ── БЛИЗНЕЦЫ: «то же, но вопрос открывать НЕ за что» ────────────────────────────────────────
def _expected_old_words(res):
    """Эталон прежних слов. Собирается ЖИВЫМИ функциями — `_refuse_words` (что сказать) и
    `_with_separator` (как транспорт единообразно разводит 🇹🇭/🇷🇺). Переписывать их руками
    нельзя: тогда эталон проверял бы мою копию, а не дверь."""
    ru, th = S._refuse_words(res, plate="4242", sent=SENT)
    return S._with_separator(f"🐀 Splinter\n🇹🇭 ⚠️ {th}\n🇷🇺 ⚠️ {ru}")


def test_rollback_switch_keeps_the_old_refusal_byte_for_byte():
    """ОТКАТ `ODO_LOWER=0`: прежние слова БАЙТ-В-БАЙТ и ни следа новой машинерии."""
    sent, br = _refuse(OIL_LOWER_RES, lower_on=False)
    assert len(sent) == 1, [m["text"] for m in sent]
    assert sent[0]["text"] == _expected_old_words(OIL_LOWER_RES), sent[0]["text"]
    assert sent[0].get("reply_markup") is None, sent[0]
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "при откате состояние не заводится"


def test_trusted_threshold_refusal_does_not_reopen_the_question():
    """БЛИЗНЕЦ: причина УЖЕ названа (ветка исправления) — переспрашивать её нельзя, это петля."""
    res = {"ok": False, "error": "oil_drop_needs_trusted", "old_oil": RECORDED,
           "drop": 2700, "threshold": 500}
    sent, br = _refuse(res)
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "второй раз причину не спрашиваем"
    assert sent[0]["text"] == _expected_old_words(res), sent[0]["text"]
    assert "oil_drop_needs_trusted" not in sent[0]["text"], sent[0]["text"]


def test_refusal_without_the_recorded_number_falls_back_to_words():
    """БЛИЗНЕЦ: расписка не назвала записанного числа — расхождения нет, вопрос не открываем."""
    res = {"ok": False, "error": "oil_decreasing"}
    sent, br = _refuse(res)
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "без числа вопрос не строится"
    assert sent[0]["text"] == _expected_old_words(res), sent[0]["text"]


def test_contradictory_receipt_does_not_open_the_question():
    """БЛИЗНЕЦ: код говорит «ниже», а числа — «выше». Верим ЧИСЛАМ, вопрос не открываем."""
    res = {"ok": False, "error": "oil_decreasing", "old_oil": SENT - 100, "new_oil": SENT}
    sent, br = _refuse(res)
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, res
    assert sent[0]["text"] == _expected_old_words(res), sent[0]["text"]


def test_unknown_refusal_code_keeps_the_old_path():
    """БЛИЗНЕЦ: чужой код — прежний путь, и код человеку по-прежнему не показан."""
    for err in ("verify_failed", "write_failed", "not_found", "receipt_unknown", ""):
        res = {"ok": False, "error": err, "old_oil": RECORDED}
        sent, br = _refuse(res)
        assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, err
        assert sent[0]["text"] == _expected_old_words(res), (err, sent[0]["text"])
        if err:
            assert err not in sent[0]["text"], (err, sent[0]["text"])


def test_broken_question_still_speaks_the_old_words():
    """FAIL-SAFE: вопрос сорвался → человек всё равно слышит слова. Молчание запрещено правилом 1."""
    _clean()
    br = _FakeBridge(answers={OP_REGISTER: OIL_LOWER_RES})
    ctx = _Ctx()
    saved = S._odo_lower_ask

    async def _boom(*a, **k):
        S._ODO_LOWER_PENDING[(CHAT, TOPIC)] = {"bike": BIKE, "ts": 0}   # успел наследить
        raise RuntimeError("телеграм лежит")
    S._odo_lower_ask = _boom
    try:
        with _Stubs(), _WriteStubs():
            _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
    finally:
        S._odo_lower_ask = saved
    assert ctx.bot.sent, "дверь промолчала — это запрещено правилом 1"
    assert ctx.bot.sent[-1]["text"] == _expected_old_words(OIL_LOWER_RES), ctx.bot.sent[-1]["text"]
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, \
        "недооткрытый вопрос обязан быть убран: иначе он съест следующий текст темы"


def test_successful_write_opens_nothing():
    """БЛИЗНЕЦ границы: запись прошла — ни вопроса, ни состояния понижения."""
    _clean()
    br = _FakeBridge(answers={OP_REGISTER: {"ok": True, "bike_name": BIKE}})
    ctx = _Ctx()
    with _Stubs(), _WriteStubs():
        _run(S._write_oil(ctx, br, CHAT, TOPIC, BIKE, SENT, confirmed_by=WHO))
    assert S._ODO_LOWER_PENDING.get((CHAT, TOPIC)) is None, "на успехе вопросов не задаём"


def test_asking_costs_no_extra_bridge_call():
    """ЦЕНА: записанное число берётся ИЗ ТОЙ ЖЕ расписки — у моста ни одного лишнего раза."""
    sent, br = _refuse(OIL_LOWER_RES)
    assert br.calls.names() == [OP_REGISTER], br.calls.names()
    # БЛИЗНЕЦ: при откате цена та же, счёт не меняется от ручки
    _, br2 = _refuse(OIL_LOWER_RES, lower_on=False)
    assert br2.calls.names() == [OP_REGISTER], br2.calls.names()


def test_nothing_was_written_to_live_tables_across_the_suite():
    """ЗАМОК ГИГИЕНЫ: за весь путь боевой мост не звался ни разу — все вызовы поймала заглушка."""
    sent, br = _walk(L.WRONG_NUMBER, "ошибся на одну цифру")
    for name, _a, _kw in br.calls:
        assert name in (OP_EVENT, OP_REGISTER, "service_upsert"), name
    assert all(isinstance(c[2], dict) for c in br.calls)


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
