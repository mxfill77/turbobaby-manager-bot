"""БОТ НИКОГДА НЕ МОЛЧИТ И НИКОГДА НЕ ОТКАЗЫВАЕТ ГЛУХО (23.08.2026, правила владельца 1 и 2).

Предмет — две вещи, и обе судятся ЖИВЫМ кодом `splinter`:
  1  ПОЛ ОТВЕТА — заход отработал и не сказал ни слова → бот говорит сам (`_reply_floor_speak`
     в `splinter.handle`); молчание запрещено как ИСХОД;
  2  СЛОВА ОТКАЗА — вместо «мост не принял запись» и внутреннего кода человеку уезжает
     «что случилось · какие числа · что делать» (`_refuse_words` → `reply_floor.refusal`).

КАЖДЫЙ ОТРИЦАТЕЛЬНЫЙ СЛУЧАЙ ИДЁТ С БЛИЗНЕЦОМ, иначе «бот заговорил» неотличимо от «бот говорит
всегда и на всё»:
  промолчали  → ответ есть   ‖  уже ответили      → второго ответа НЕТ;
  заход упал  → ответ есть   ‖  заход отработал   → ответа-добавки НЕТ;
  своя тема   → ответ есть   ‖  клиентский контур → НЕ ТРОГАЕМ ВОВСЕ;
  ручка вкл   → ответ есть   ‖  `NEVER_SILENT=0`  → молчание прежнее, байт-в-байт.

Сеть/Telegram/Bridge замоканы, байки выдуманные, в Лист1 не пишется ничего.
"""
import asyncio
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["NEVER_SILENT"] = "1"        # боевой дефолт ЯВНО: сьют не зависит от .env машины

import splinter as S          # noqa: E402
import reply_floor as F       # noqa: E402

CHAT_SERVICING = None         # берётся из живого реестра групп ниже
TOPIC = 7311
BIKE = "TESTBIKE 000ZZ PHUKET 4242"     # такого байка в парке нет


def _chat_of(mode):
    """Живой реестр групп: адрес контура берём у кода, а не хардкодим числом."""
    for cid, m in S.GROUPS.items():
        if m == mode:
            return cid
    raise AssertionError(f"в GROUPS нет контура {mode}")


class _Bot:
    """Телеграм-заглушка. Копит отправленное; сеть не трогается вовсе."""

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
    def __init__(self, uid=99001, username="testmech"):
        self.id, self.username, self.is_bot = uid, username, False
        self.first_name = "Test"


class _Msg:
    def __init__(self, chat_id, text="", topic=TOPIC, photo=None):
        self.chat_id, self.text, self.message_thread_id = chat_id, text, topic
        self.caption, self.photo = None, photo or []
        self.from_user, self.message_id, self.date = _User(), 555, None
        self.reply_to_message = None


class _Upd:
    def __init__(self, msg):
        self.message = msg


def _run(coro):
    """Свой цикл на каждый прогон: свидетель речи — ContextVar, и чужой цикл дал бы чужой контекст."""
    return asyncio.run(coro)


def _drive(handler, *, mode="servicing", text="что-то невнятное", photo=None):
    """Прогнать `splinter.handle` с подменённым разбором. Возвращает (ctx, отправленное)."""
    chat = _chat_of(mode)
    ctx = _Ctx()
    saved = {}
    names = {"servicing": "_handle_servicing", "intake": "_handle_intake"}
    name = names[mode]
    saved[name] = getattr(S, name)
    setattr(S, name, handler)
    try:
        _run(S.handle(_Upd(_Msg(chat, text, photo=photo)), ctx, None, None))
    finally:
        setattr(S, name, saved[name])
    return ctx, ctx.bot.sent


# ============================================================================================
#  (1) ПОЛ ОТВЕТА: промолчали — говорим. Близнец: сказали — молчим.
# ============================================================================================
def test_silent_handler_still_answers_the_human():
    """ГЛАВНЫЙ СЛУЧАЙ: сообщение, которое бот не понял, всё равно получает ответ."""
    async def silent(*a, **k):
        return None
    _, sent = _drive(silent)
    assert len(sent) == 1, f"молчание осталось исходом: отправлено {len(sent)}"
    body = sent[0]["text"]
    assert sent[0]["message_thread_id"] == TOPIC, "ответ ушёл не в ту тему"
    assert "не понял" in body, body
    # «не понял» без «что прислать» — половина ответа; правило требует обе
    assert any(w in body for w in ("пришли", "напиши")), body


def test_twin_handler_that_answered_gets_no_second_word():
    """БЛИЗНЕЦ: заход ответил сам — пол молчит, шума нет."""
    async def talky(msg, context, *a, **k):
        await S._send(context, chat_id=msg.chat_id, text="🐀 Splinter\nответил сам",
                      message_thread_id=TOPIC)
    _, sent = _drive(talky)
    assert len(sent) == 1, f"пол добавил лишнее слово: {sent}"
    assert "ответил сам" in sent[0]["text"], sent


def test_crashed_handler_says_what_it_could_not_do():
    """Заход упал — человек узнаёт, ЧЕГО именно бот не смог, и что записи не было."""
    async def boom(*a, **k):
        raise RuntimeError("проба падения, наружу не уходит")
    _, sent = _drive(boom)
    assert len(sent) == 1, sent
    body = sent[0]["text"]
    assert "не смог" in body and "НЕ делал" in body, body
    assert "RuntimeError" not in body and "проба падения" not in body, "внутренности наружу"


def test_crash_after_an_answer_does_not_add_a_second_word():
    """БЛИЗНЕЦ падения: успели ответить и упали — ответ уже есть, второго не будет."""
    async def talk_then_boom(msg, context, *a, **k):
        await S._send(context, chat_id=msg.chat_id, text="🐀 Splinter\nуспел сказать",
                      message_thread_id=TOPIC)
        raise RuntimeError("падение после ответа")
    _, sent = _drive(talk_then_boom)
    assert len(sent) == 1 and "успел сказать" in sent[0]["text"], sent


def test_photo_without_numbers_gets_its_own_words():
    """Фото есть, числа не разобрали — говорим именно об этом, а не общее «не понял»."""
    async def silent(*a, **k):
        return None
    _, sent = _drive(silent, text="", photo=[object()])
    assert len(sent) == 1, sent
    assert "Фото" in sent[0]["text"] and "цифрами" in sent[0]["text"], sent[0]["text"]


# ============================================================================================
#  (2) ГРАНИЦЫ: клиентский контур не трогаем; ручка отката возвращает молчание
# ============================================================================================
def test_client_contour_is_not_touched_at_all():
    """ПРЯМОЙ ЗАПРЕТ ЗАДАНИЯ: у клиента разговор ведёт менеджер — лишней реплики быть не должно."""
    async def silent(*a, **k):
        return None
    _, sent = _drive(silent, mode="intake")
    assert sent == [], f"пол заговорил в клиентском контуре: {sent}"


def test_rollback_switch_restores_previous_silence():
    """ОТКАТ: `NEVER_SILENT=0` → путь прежний, молчание вернулось байт-в-байт."""
    async def silent(*a, **k):
        return None
    os.environ["NEVER_SILENT"] = "0"
    try:
        _, sent = _drive(silent)
        assert sent == [], f"ручка отката не гасит ветку: {sent}"
    finally:
        os.environ["NEVER_SILENT"] = "1"
    _, sent2 = _drive(silent)
    assert len(sent2) == 1, "ручка вернулась — ответ обязан вернуться"


def test_witness_is_per_task_not_global():
    """Свидетель речи — ContextVar: ответ СОСЕДНЕГО сообщения не имеет права сойти за наш."""
    async def talky(msg, context, *a, **k):
        await S._send(context, chat_id=msg.chat_id, text="🐀 Splinter\nсосед",
                      message_thread_id=TOPIC)

    async def silent(*a, **k):
        return None

    chat = _chat_of("servicing")

    async def both():
        ctx = _Ctx()
        S._handle_servicing = talky
        await S.handle(_Upd(_Msg(chat, "первое")), ctx, None, None)
        S._handle_servicing = silent
        await S.handle(_Upd(_Msg(chat, "второе")), ctx, None, None)
        return ctx.bot.sent

    saved = S._handle_servicing
    try:
        sent = _run(both())
    finally:
        S._handle_servicing = saved
    assert len(sent) == 2, f"второе сообщение осталось без ответа: {sent}"
    assert "не понял" in sent[1]["text"], sent[1]["text"]


def test_floor_never_raises_even_if_sending_dies():
    """Пол — последний в цепи: он не имеет права стать новой причиной падения."""
    class _DeadBot(_Bot):
        async def send_message(self, **kw):
            raise RuntimeError("телеграм лежит")

    async def silent(*a, **k):
        return None

    ctx = _Ctx()
    ctx.bot = _DeadBot()
    saved = S._handle_servicing
    S._handle_servicing = silent
    try:
        _run(S.handle(_Upd(_Msg(_chat_of("servicing"), "текст")), ctx, None, None))
    finally:
        S._handle_servicing = saved


# ============================================================================================
#  (3) ОТКАЗ ОБЯЗАН ГОВОРИТЬ, ЧТО ДЕЛАТЬ — и НЕ показывать внутренний код
# ============================================================================================
ALL_CODES = sorted(set(list(F._SAY) + [
    "receipt_unknown", "request_failed", "timeout", "лютый_незнакомый_код", "",
    "km_decreasing", "oil_drop_needs_trusted", "audit_failed",
])) + [None]        # None отдельно: он не сравним со строкой, а проверить его надо


def test_every_refusal_names_an_action():
    for code in ALL_CODES:
        say = F.refusal(code, {"recorded": 41200, "sent": 38500, "drop": 2700,
                               "plate": "4242", "threshold": 500, "who": "@pleummmm"})
        assert say["ru"] and say["th"], code
        assert "Что делать:" in say["ru"], (code, say["ru"])
        assert say["state"] in (F.NAMED, F.UNSETTLED, F.UNNAMED), (code, say)


def test_no_internal_code_ever_reaches_the_human():
    """ЗАМОК: код уходит в журнал отдельным полем и в тексте человеку не появляется НИ РАЗУ."""
    for code in ALL_CODES:
        say = F.refusal(code, {"recorded": 1, "sent": 2, "drop": 3})
        if not code:
            continue
        assert code not in say["ru"], (code, say["ru"])
        assert code not in say["th"], (code, say["th"])
        assert say["log"] == code, (code, say)
    banned = ("мост не принял", "bridge", "error", "Exception", "traceback")
    for code in ALL_CODES:
        say = F.refusal(code, {})
        for b in banned:
            assert b.lower() not in say["ru"].lower(), (code, b, say["ru"])


def test_transport_silence_is_its_own_outcome():
    """ТРЕТИЙ ИСХОД: расписки нет → «не знаю, легло ли», а не «не записал»."""
    for code in ("receipt_unknown", "request_failed", "timeout"):
        say = F.refusal(code)
        assert say["state"] == F.UNSETTLED, (code, say)
        assert "не знаю" in say["ru"], say["ru"]
        assert "перед тем как слать ещё раз" in say["ru"], say["ru"]


def test_settled_refusal_is_not_confused_with_silence():
    """БЛИЗНЕЦ третьего исхода: мост вынес отказ САМ — говорим определённо, без «не знаю»."""
    for code in ("not_found", "ambiguous", "oil_decreasing", "write_failed"):
        say = F.refusal(code, {"plate": "4242", "recorded": 5, "sent": 4, "drop": 1})
        assert say["state"] == F.NAMED, (code, say)
        assert "не знаю" not in say["ru"], (code, say["ru"])


def test_lowering_refusal_carries_all_three_numbers():
    say = F.refusal("oil_decreasing", {"recorded": 41200, "sent": 38500, "drop": 2700})
    for n in ("41200", "38500", "2700"):
        assert n in say["ru"], (n, say["ru"])
        assert n in say["th"], (n, say["th"])


def test_missing_number_becomes_a_question_mark_not_a_hole():
    """Дырка в фактах не имеет права стать пустым местом: «?» видно, пустоту — нет."""
    say = F.refusal("oil_decreasing", {})
    assert "?" in say["ru"], say["ru"]
    assert "  " not in say["ru"], say["ru"]


def test_hands_door_hides_the_code_and_logs_it():
    """ЖИВЫЕ РУКИ: `_refuse_words` — единая дверь слов отказа обеих дверей записи."""
    ru, th = S._refuse_words({"ok": False, "error": "oil_decreasing", "old_oil": 41200},
                             plate="4242", sent=38500)
    assert "oil_decreasing" not in ru and "oil_decreasing" not in th, (ru, th)
    for n in ("41200", "38500", "2700"):
        assert n in ru, (n, ru)
    assert "Что делать:" in ru, ru


def test_hands_door_survives_garbage_from_the_bridge():
    """FAIL-SAFE: мост ответил мусором — слова всё равно есть, и в них есть действие."""
    for res in (None, {}, "строка вместо словаря", {"error": None}, {"error": "неведомое"}):
        ru, th = S._refuse_words(res, plate="4242", sent=38500)
        assert ru and th and "Что делать:" in ru, (res, ru)


def test_purity_guard_is_registered_and_red_on_a_twin():
    import invariants_check as IC
    assert "REPLY_FLOOR_PURE" in [n for n, _ in IC.CHECKS], "страж в гейте"
    live = open("/root/turbobaby-manager-bot/reply_floor.py", encoding="utf-8").read()
    assert IC._duty_ast_findings(live, allowed=frozenset(("write_fact",))) == [], "живой модуль чист"
    twin = ("from write_fact import SETTLED_ERRORS\nimport requests\n\n"
            "def refusal(a):\n    return open('/tmp/x').read()\n")
    assert IC._duty_ast_findings(twin, allowed=frozenset(("write_fact",))), \
        "тот же страж на модуле, который умеет в мир, обязан краснеть"


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
