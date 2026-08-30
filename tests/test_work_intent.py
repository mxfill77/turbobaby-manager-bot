"""ПРИЁМ РАБОТ РАЗЛИЧАЕТ НАМЕРЕНИЕ: вопрос — не заявка, деталь — не приборка (30.08.2026).

Предмет — три вещи, и все три судятся ЖИВЫМ кодом:
  1  НАМЕРЕНИЕ (`work_intent`) — вопрос о работе, отписка о работе, честное сомнение;
  2  ДВЕРЬ ЗАЯВКИ (`splinter._handle_servicing`) — заводится ли строка на самом деле;
  3  ВИД СНИМКА (`reply_floor.fallback`) — приборка против всего остального.

КАЖДЫЙ ОТРИЦАТЕЛЬНЫЙ СЛУЧАЙ ИДЁТ С БЛИЗНЕЦОМ, иначе «заявки нет» неотличимо от «заявок не
бывает вовсе», а «фото распознано» — от «на любое фото один ответ»:
  вопрос      → заявки НЕТ   ‖  отписка теми же словами о работе → заявка ЕСТЬ;
  сомнение    → переспрос    ‖  чистая отписка                   → молча заводим, как заводили;
  деталь      → свои слова   ‖  приборка                         → текст БАЙТ-В-БАЙТ прежний;
  вид неизвестен → не врём   ‖  вид назван                       → называем увиденное;
  ручка вкл   → гейт держит  ‖  `WORK_INTENT=0`                  → путь прежний, байт-в-байт.

ГОЛДЕНЫ — НА ДОСЛОВНЫХ СТРОКАХ ЖУРНАЛА (`splinter.log`, окно замера 31.07–30.08.2026):
  «@Pleummmm в редукторе тоже меняли масло?»            22.08 07:12:04, ADV 350 372 → заявка ['gear']
  «@extthiwxer была произведена замена жидкости абс?»   01.08 08:03:41, NMAX 155 GREY 5960 → ['abs']
  «Я уже заменил переднюю шину, моторное масло, …»      23.08 14:10:59 — настоящая отписка

ЗАПРЕТЫ ЗАХОДА СОБЛЮДЕНЫ: сеть/Telegram/мост замоканы, байки ВЫДУМАНЫ (в парке таких нет),
в живые таблицы и в зеркало не пишется ничего, память замка подсказок уведена во временный файл.
Фейковый мост отвечает ПО СОСТАВУ АРГУМЕНТОВ, а не по имени — имён боевых операций записи в
этом файле нет ни одного (тот же приём, что в `tests/works_batch_harness.py`).
"""
import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["WORK_INTENT"] = "1"          # боевой дефолт ЯВНО: сьют не зависит от .env машины
os.environ["NEVER_SILENT"] = "1"
# Память замка подсказок — во ВРЕМЕННЫЙ файл: боевое состояние прогоном не трогается.
os.environ["HINT_DEDUP_STATE"] = os.path.join(tempfile.mkdtemp(prefix="tb_intent_"), "seen.json")

import work_intent as W      # noqa: E402
import reply_floor as F      # noqa: E402
import splinter as S         # noqa: E402
import invariants_check      # noqa: E402

TOPIC = 7312
BIKE = "TESTBIKE 000ZZ PHUKET 4242"      # такого байка в парке нет

#: Дословные строки журнала — предмет захода.
Q_LIVE = "@Pleummmm в редукторе тоже меняли масло?"
U_LIVE = "@extthiwxer была произведена замена жидкости абс?"
C_LIVE = ("Я уже заменил переднюю шину, моторное масло, масло в редукторе, "
          "передние и задние тормозные колодки")


# ============================================================================================
#  (1) НАМЕРЕНИЕ: вопрос ‖ отписка ‖ сомнение
# ============================================================================================
def test_live_question_is_a_question():
    """ГЛАВНЫЙ СЛУЧАЙ, дословно из журнала: вопрос о редукторе — не заявка."""
    v = W.verdict(Q_LIVE, ["замена масла в редукторе"])
    assert v["state"] == W.QUESTION, v
    assert "?" in v["clause"], "решившая клауза должна быть названа человеку и журналу"


def test_twin_live_claim_stays_a_claim():
    """БЛИЗНЕЦ: настоящая отписка теми же работами — по-прежнему заявка, путь прежний."""
    assert W.verdict(C_LIVE)["state"] == W.CLAIM


def test_live_ambiguous_is_its_own_outcome():
    """Живой 01.08: и «замена», и знак вопроса в ОДНОЙ клаузе — честное сомнение, не догадка."""
    assert W.verdict(U_LIVE)["state"] == W.UNCLEAR


def test_greeting_does_not_immunise_a_question():
    """Клауза без признака (`SILENT`) — не отписка. Иначе «Доброе утро» спасало бы любой вопрос."""
    assert W.verdict("Доброе утро. В редукторе тоже меняли масло?")["state"] == W.QUESTION


def test_claim_beside_a_question_wins():
    """Порядок силы: сказанное ПРЯМО сильнее спрошенного рядом — работу не теряем."""
    assert W.verdict("Я заменил масло, а колодки тоже надо?")["state"] == W.CLAIM


def test_thai_question_without_a_question_mark():
    """Тайский вопрос знака не несёт — весь признак в частице; молча пройти он не должен."""
    assert W.verdict("เปลี่ยนน้ำมันเฟืองท้ายไหม")["state"] in (W.QUESTION, W.UNCLEAR)


def test_thai_claim_is_not_demoted():
    """БЛИЗНЕЦ: тайская отписка без частицы — заявка, как была."""
    assert W.verdict("เปลี่ยนน้ำมันเครื่องแล้วครับ")["state"] == W.CLAIM


def test_particle_is_read_as_a_whole_word_only():
    """«заЛИл»/«доЛИли» не содержат вопроса. Подстрочный поиск «ли» съел бы любую отписку."""
    for t in ("залил масло", "долили тормозную жидкость", "поставил новые колодки"):
        assert W.verdict(t)["state"] == W.CLAIM, t


def test_empty_text_keeps_the_previous_path():
    """Признака нет — демотировать нечем. Модуль умеет СНЯТЬ заявку и не умеет её родить."""
    for t in ("", None, "   "):
        assert W.verdict(t)["state"] == W.CLAIM, repr(t)


def test_works_are_never_judged():
    """`works` в решение не входит: предмет назвал разборщик, намерение живёт в словах человека."""
    a = W.verdict(Q_LIVE, ["замена масла в редукторе"])
    b = W.verdict(Q_LIVE, [])
    c = W.verdict(Q_LIVE, ["выдуманная работа", "и ещё одна"])
    assert a["state"] == b["state"] == c["state"] == W.QUESTION


def test_clause_split_keeps_the_question_mark():
    """Знак — признак; потеряв его при разрезе, правило ослепло бы на главный случай."""
    cs = W.clauses("Поменял масло. А редуктор тоже?")
    assert any(c.endswith("?") for c in cs), cs


# ============================================================================================
#  (2) ДВЕРЬ ЗАЯВКИ: живой `_handle_servicing` — строка заводится или нет
# ============================================================================================
class _Bot:
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


class _Msg:
    def __init__(self, chat_id, text):
        self.chat_id = chat_id
        self.text = text
        self.caption = None
        self.photo = None
        self.message_id = 555
        self.message_thread_id = TOPIC
        self.date = None
        self.from_user = type("U", (), {"username": "tester", "id": 1})()
        self.reply_to_message = None


class _Bridge:
    """Мост-заглушка. Отвечает НА ЛЮБОЕ имя одинаково и копит СОСТАВ АРГУМЕНТОВ вызова —
    имён боевых операций записи в этом файле нет ни одного (запрет захода)."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _any(*a, **kw):
            self.calls.append(dict(kw))
            return {"ok": True, "items": [], "saved": True}
        return _any

    def staged(self):
        """Вызовы, ПОХОЖИЕ НА ЗАВЕДЕНИЕ ЗАЯВКИ — по составу аргументов, а не по имени:
        строка заявки — единственная, что несёт И перечень работ, И её статус."""
        return [c for c in self.calls if "declared" in c and "status" in c]


class _Claude:
    """Разборщик-заглушка: отдаёт РОВНО тот разбор, что дал живой LLM в журнале."""

    def __init__(self, works):
        self.works = works

    def quick(self, *a, **kw):
        return json.dumps({"type": "event", "event_type": "repair",
                           "mileage": None, "works": self.works, "bike": BIKE})

    def vision(self, *a, **kw):
        return "{}"


def _chat_servicing():
    for cid, m in S.GROUPS.items():
        if m == "servicing":
            return cid
    raise AssertionError("в GROUPS нет контура servicing")


def _door(text, works, *, intent="1"):
    """Прогнать ЖИВУЮ дверь приёма работ. Возвращает (заведённые строки, отправленное)."""
    prev = os.environ.get("WORK_INTENT")
    os.environ["WORK_INTENT"] = intent
    br, ctx = _Bridge(), _Ctx()
    saved = S.bike_from_topic
    S.bike_from_topic = lambda *a, **k: BIKE      # тема = байк, без обращения к миру
    try:
        asyncio.run(S._handle_servicing(_Msg(_chat_servicing(), text), ctx, br, _Claude(works)))
    finally:
        S.bike_from_topic = saved
        if prev is None:
            os.environ.pop("WORK_INTENT", None)
        else:
            os.environ["WORK_INTENT"] = prev
    return br.staged(), ctx.bot.sent


def test_door_question_creates_nothing():
    """ГЛАВНЫЙ ОТРИЦАТЕЛЬНЫЙ: вопрос дошёл до живой двери и НЕ завёл заявку."""
    staged, sent = _door(Q_LIVE, ["замена масла в редукторе"])
    assert staged == [], f"вопрос завёл заявку: {staged}"
    assert len(sent) >= 1, "бот промолчал — правило «никогда не молчать» нарушено"
    body = "\n".join(s["text"] for s in sent)
    assert "НЕ открыл" in body and "не записал" in body, body
    assert "Принял работы" not in body, "переспрос не смеет читаться как приём работы"


def test_door_twin_claim_creates_the_row():
    """БЛИЗНЕЦ: отписка о ТЕХ ЖЕ работах — заявка заводится, как заводилась."""
    staged, _ = _door(C_LIVE, ["замена масла в редукторе"])
    assert staged, "отписка перестала заводить заявку — гейт съел живой поток"


def test_door_ambiguous_asks_instead_of_creating():
    """Сомнение переспрашивает, а не заводит и не молчит."""
    staged, sent = _door(U_LIVE, ["замена жидкости АБС"])
    assert staged == [], f"сомнительный случай завёл заявку: {staged}"
    body = "\n".join(s["text"] for s in sent)
    assert "Не понял" in body, body


def test_door_rollback_switch_restores_the_old_path():
    """ОТКАТ ДОКАЗАН: `WORK_INTENT=0` → тот же вопрос снова заводит заявку, как до 30.08."""
    staged, _ = _door(Q_LIVE, ["замена масла в редукторе"], intent="0")
    assert staged, "ручка отката не вернула прежний путь"


def test_door_never_writes_to_the_fleet():
    """ГРАНИЦА: ни одна ветка приёма не трогает живые регистры — подтверждено составом аргументов."""
    for text, works in ((Q_LIVE, ["замена масла в редукторе"]), (U_LIVE, ["замена жидкости АБС"])):
        br, ctx = _Bridge(), _Ctx()
        saved = S.bike_from_topic
        S.bike_from_topic = lambda *a, **k: BIKE
        try:
            asyncio.run(S._handle_servicing(_Msg(_chat_servicing(), text), ctx, br, _Claude(works)))
        finally:
            S.bike_from_topic = saved
        for c in br.calls:
            assert not (c.get("confirmed") is True), f"подтверждённая запись из ветки вопроса: {c}"


# ============================================================================================
#  (3) ВИД СНИМКА: приборка ‖ всё остальное ‖ вид неизвестен
# ============================================================================================
_RETAKE = "переснимите приборку"


def test_dashboard_text_is_byte_for_byte_the_old_one():
    """БЛИЗНЕЦ-ЗАБОР: на приборке просьба переснять верна по существу и обязана остаться прежней."""
    r = F.fallback({"bike": BIKE, "photo": True, "photo_kind": F.DASHBOARD})
    assert _RETAKE in r["ru"], r["ru"]
    assert "числа на нём разобрать не смог" in r["ru"], r["ru"]


def test_detail_photo_does_not_ask_to_retake_the_dashboard():
    """ГЛАВНЫЙ ОТРИЦАТЕЛЬНЫЙ: снятая деталь (повод 29.08) — приборку переснимать не просим."""
    r = F.fallback({"bike": BIKE, "photo": True, "photo_kind": "other"})
    assert _RETAKE not in r["ru"], r["ru"]
    assert "приборки на нём нет" in r["ru"], r["ru"]
    assert "к чему это относится" in r["ru"], r["ru"]


def test_every_named_kind_gets_its_own_words():
    """Вид назван — говорим, ЧТО видно; ни один известный вид не просит переснять приборку."""
    for k in ("wheel", "bike", "receipt", "other"):
        r = F.fallback({"bike": BIKE, "photo": True, "photo_kind": k})
        assert _RETAKE not in r["ru"], (k, r["ru"])
        assert r["th"].strip() and r["ru"].strip(), k


def test_unknown_kind_claims_neither():
    """ТРЕТИЙ ИСХОД: вид не назван — не утверждаем ни приборку, ни деталь, но и не молчим.
    Именно сюда падают ВСЕ пять живых случаев окна: разбор снимка не назвал ничего."""
    for k in ("", None, "неведомое"):
        r = F.fallback({"bike": BIKE, "photo": True, "photo_kind": k})
        assert _RETAKE not in r["ru"], (k, r["ru"])
        assert "не узнал" in r["ru"], (k, r["ru"])
        assert any(w in r["ru"] for w in ("напиши", "пришли")), (k, r["ru"])


def test_photo_kind_absent_behaves_like_unknown():
    """Старый вызов без нового факта не падает и не врёт: он попадает в «не узнал»."""
    r = F.fallback({"bike": BIKE, "photo": True})
    assert _RETAKE not in r["ru"] and "не узнал" in r["ru"], r["ru"]


def test_album_keeps_the_dashboard_kind():
    """Альбом: приборка в пачке ЕСТЬ, если она есть хоть на одном снимке (оттуда же и пробег)."""
    agg = S._aggregate_album_vis([{"kind": "other"}, {"kind": "dashboard", "mileage": "12345"}])
    assert agg.get("kind") == F.DASHBOARD, agg


def test_album_without_a_dashboard_keeps_the_first_named_kind():
    """БЛИЗНЕЦ: приборки в пачке нет — вид не выдумывается, берётся первый названный."""
    agg = S._aggregate_album_vis([{"kind": "wheel"}, {"kind": "other"}])
    assert agg.get("kind") == "wheel", agg


def test_witness_is_per_task_not_global():
    """ContextVar, а не глобаль: вид снимка соседнего сообщения в чужой ответ не течёт."""
    async def _one(val):
        S._PHOTO_KIND.set(val)
        return S._PHOTO_KIND.get()
    assert asyncio.run(_one("wheel")) == "wheel"
    assert asyncio.run(_one("")) == "", "вид снимка пережил чужую задачу"


# ============================================================================================
#  (4) ЧИСТОТА РЕШЕНИЯ: страж зарегистрирован и краснеет на близнеце
# ============================================================================================
def test_purity_guard_is_registered_and_red_on_a_twin():
    """Страж `WORK_INTENT_PURE` в гейте; на подделке с сетью/записью он обязан покраснеть."""
    IC = invariants_check
    assert "WORK_INTENT_PURE" in [n for n, _ in IC.CHECKS], "страж в гейте"
    live = open("/root/turbobaby-manager-bot/work_intent.py", encoding="utf-8").read()
    assert IC._duty_ast_findings(live, allowed=frozenset(("re",))) == [], "живой модуль чист"
    twin = ("import re\nimport bridge_client\n\n"
            "def verdict(t):\n    return open('/tmp/x').read()\n")
    assert IC._duty_ast_findings(twin, allowed=frozenset(("re",))), \
        "тот же страж на модуле, который умеет в мир, обязан краснеть"


def test_only_one_import_in_the_decision():
    """ГРАНИЦА УСТРОЙСТВОМ: импорт РОВНО ОДИН. Второй — повод перечитать, зачем он решению."""
    import ast
    src = open("/root/turbobaby-manager-bot/work_intent.py", encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    assert mods == {"re"}, mods


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
