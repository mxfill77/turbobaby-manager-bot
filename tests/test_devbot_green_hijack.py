"""Фикс класса роутера devbot (инцидент 23:49 11.07.2026): длинное структурированное сообщение
с префиксом («пк:»/«декомпозируй:»/«тз:»/«задача:») угонялось зелёной однословной командой
allowlist, если её ключевое слово встретилось В ТЕЛЕ ТЗ («пк: декомпозируй: <крупное ТЗ>» →
простыня журнала вместо постановки родителя).

ПРАВИЛО: структурированные префиксы матчатся ПЕРВЫМИ по началу сообщения (абсолютный приоритет,
вкл. лидирующий «пк:» ПЕРЕД командным префиксом — канонизация «пк: тз: X» → «тз: пк: X»);
зелёные однословные команды срабатывают ТОЛЬКО когда сообщение и есть команда (короткое после
трима), а не содержит слово в теле. Сети/Telegram/claude НЕТ — слой 2 замокан."""
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["THEATER_ROUTER"] = "1"          # роутер ВКЛ детерминированно (не зависим от .env)
import devbot as DB


# Крупное ТЗ дословно по классу инцидента: в теле — слова зелёных команд (cclog / статус /
# гейт / health / мозг / ошибки) — раньше любое из них угоняло сообщение в allowlist.
INCIDENT_TZ = ("собери сводный отчёт: прочитай cclog и cc_log, сверь статус и пульс, прогони "
               "гейт, проверь health и мозг, разбери ошибки splinter.log и приложи журнал "
               "боевой записи — всё это часть ТЗ, а не зелёные команды")


class EnqBridge:
    def __init__(s):
        s.calls = []

    def enqueue_task(s, frm, txt, lane=None):
        s.calls.append((frm, txt, lane))
        return {"ok": True, "id": 77}


class _NoLayer2:
    """Слой 2 ЗАПРЕЩЁН (упадёт assert'ом) — лидирующий пк: должен решать театр детерминированно."""
    def __enter__(s):
        s.old = DB._classify_theater

        def fake(text):
            raise AssertionError(f"слой 2 НЕ должен зваться: {text!r}")
        DB._classify_theater = fake
        return s

    def __exit__(s, *a):
        DB._classify_theater = s.old
        return False


# (1) ЖИВОЙ ИНЦИДЕНТ: «пк: декомпозируй: <крупное ТЗ со словами зелёных команд>» →
#     ставится РОДИТЕЛЬ pc-декомпозиции (Filipp-pc-dec, БЕЗ lane), зелёная команда молчит.
def test_incident_pc_decompose_parent():
    with _NoLayer2():
        b = EnqBridge()
        msg = f"пк: декомпозируй: {INCIDENT_TZ}"
        r = DB._try_enqueue(msg, b)
        assert r is not None and "77" in r, f"родитель ДОЛЖЕН встать в очередь: {r!r}"
        frm, txt, lane = b.calls[-1]
        assert frm == DB.QUEUE_FROM_PC_DEC and lane is None, \
            f"пк:-декомпозиция → родитель Filipp-pc-dec БЕЗ lane (план строит VPS): {b.calls}"
        assert txt == INCIDENT_TZ, f"пк:-префикс срезан, ТЗ дословно: {txt!r}"
        assert "🎭 pc" in r, f"карточка приёма показывает театр pc: {r}"
        # зелёный allowlist на этом сообщении МОЛЧИТ (и до, и после enqueue-слоя)
        assert DB._match(msg) is None, "зелёная команда НЕ должна матчить структурированное ТЗ"
        assert DB._match(INCIDENT_TZ) is None, "и голое длинное ТЗ со словами команд — тоже нет"


# (2) Лидирующий пк:/pc: перед «тз:»/«задача:» → канон «команда первой», одиночные на lane=pc.
def test_leading_pc_prefix_single_tasks():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("пк: тз: поправь черновики приветствий", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "поправь черновики приветствий", "pc"), \
            f"«пк: тз:» ≡ «тз: пк:» — 328-метка + lane=pc: {b.calls}"
        assert "🎭 pc" in r
        r = DB._try_enqueue("pc: задача: пингани агента", b)
        assert b.calls[-1] == (DB.QUEUE_FROM, "пингани агента", "pc"), f"«pc: задача:» тоже: {b.calls}"
        assert "🎭 pc" in r
        # пустое ТЗ после канонизации → честный отказ, не постановка мусора
        assert DB._try_enqueue("пк: тз:", b).startswith("🤖 Пустое ТЗ"), \
            "«пк: тз:» без текста → отказ как пустое"
        assert DB._try_enqueue("пк: декомпозируй:", b).startswith("🤖 Пустое ТЗ")


# (3) «пк:» БЕЗ командного префикса дальше — НЕ команда очереди и НЕ зелёная команда.
def test_pc_prefix_without_command():
    b = EnqBridge()
    assert DB._try_enqueue("пк: health", b) is None, "пк: без команды → не очередь"
    assert b.calls == [], "enqueue не звался"
    assert DB._match("пк: health") is None, "и не зелёная команда (префикс = приоритет очереди)"


# (4) Зелёные короткие — как раньше: однословные и короткие фразы матчатся.
def test_green_short_commands_intact():
    for word in ("health", "здоровье", "аудит", "cclog", "cc лог", "ошибки", "мозг",
                 "просрочки", "статус", "пульс", "сверься", "гейт", "помощь",
                 "покажи статус", "splinter.log", "лог сплинтер", "write log"):
        assert DB._match(word) is not None, f"короткая зелёная «{word}» должна матчиться как раньше"
    # разные команды не слиплись (регресс test_devbot_registry в миниатюре)
    assert DB._match("статус") is not DB._match("сверься")
    assert DB._match("мозг") is not DB._match("сверься")


# (5) Длинное сообщение БЕЗ префикса со словом команды в теле — НЕ команда (это вопрос/ТЗ).
def test_green_ignores_keyword_in_body():
    long_msg = ("посмотри пожалуйста внимательно что там с ботом творится: гейт вроде зелёный, "
                "но статус в пульсе странный и в cclog какая-то каша")
    assert DB._match(long_msg) is None, "слово команды в ТЕЛЕ длинного текста ≠ команда"
    assert DB._match("тз: гейт") is None, "структурированный префикс → в зелёное не идём вообще"
    assert DB._match("задача: статус") is None
    assert DB._match("") is None and DB._match(None) is None


# (6) Регресс канонизации: THEATER_ROUTER=0 → «пк: тз: X» ведёт себя ровно как «тз: пк: X»
#     при выключенном роутере (пк: уходит текстом, БЕЗ lane) — прежняя точка отката цела.
def test_router_off_canon_matches_legacy():
    os.environ["THEATER_ROUTER"] = "0"
    try:
        with _NoLayer2():
            b = EnqBridge()
            r = DB._try_enqueue("пк: тз: поправь черновики", b)
            assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "пк: поправь черновики", None), \
                f"роутер выключен: как у «тз: пк: …» — пк: текстом, БЕЗ lane: {b.calls}"
            assert "🎭" not in r
    finally:
        os.environ["THEATER_ROUTER"] = "1"


# (7) Полоса pc (тема 829, явный вход БЕЗ роутера): «пк: тз: X» ≡ «тз: пк: X» — как раньше
#     в 829 пк:-префикс НЕ срезается (роутера нет), уходит текстом на lane=pc.
def test_lane_pc_canon_matches_legacy():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("пк: тз: собери X", b, lane="pc")
        assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEV, "пк: собери X", "pc"), \
            f"829: канон = прежнее поведение «тз: пк: …» (префикс текстом): {b.calls}"
        assert "🎭" not in r, f"явный вход — без бейджа роутера: {r}"


# (8) Регресс: обычные структурированные без пк: — байт-в-байт как раньше (vps-театр слоем 1).
def test_plain_prefixes_intact():
    with _NoLayer2():
        b = EnqBridge()
        DB._try_enqueue("тз: прогони гейт", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "прогони гейт", None), \
            f"vps-театр: старая метка, БЕЗ lane: {b.calls}"
        DB._try_enqueue(f"декомпозируй: {INCIDENT_TZ}", b)
        frm, txt, lane = b.calls[-1]
        assert frm == DB.QUEUE_FROM_DEC and lane is None and txt == INCIDENT_TZ, \
            f"декомпозиция без пк: → vps-родитель, ТЗ дословно: {b.calls}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов фикса угона роутера зелёной командой (инцидент 23:49 11.07)")
