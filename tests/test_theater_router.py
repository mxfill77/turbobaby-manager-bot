"""ПК-ТЕАТР кусок 3 «единый пульт» (07.07.2026): авто-роутинг театра исполнения в теме 328.
Самотесты (а)-(е) спеки задачи 122 + маршрут карточек по теме ПОСТАНОВКИ + парсер слоя 2 +
откат THEATER_ROUTER=0; (ж) = полный гейт (этот файл в наборе gate.py). Сети/Telegram/claude
НЕТ — слой 2 замокан (подмена devbot._classify_theater / subprocess.run)."""
import os
import sys
import types

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["THEATER_ROUTER"] = "1"          # роутер ВКЛ детерминированно (не зависим от .env)
os.environ["PC_DEC_LOCAL"] = "0"            # изоляция: тут проверяем СТАРЫЙ путь pc-dec (VPS-дирижёр)
import devbot as DB


class EnqBridge:
    def __init__(s):
        s.calls = []

    def enqueue_task(s, frm, txt, lane=None):
        s.calls.append((frm, txt, lane))
        return {"ok": True, "id": 55}


class _NoLayer2:
    """Контекст: слой 2 ЗАПРЕЩЁН (упадёт assert'ом) — проверка, что слой 1 решил сам."""
    def __init__(s, ret="BOOM"):
        s.ret = ret
        s.calls = []

    def __enter__(s):
        s.old = DB._classify_theater

        def fake(text):
            s.calls.append(text)
            assert s.ret != "BOOM", f"слой 2 НЕ должен зваться, а позвался: {text!r}"
            return s.ret
        DB._classify_theater = fake
        return s

    def __exit__(s, *a):
        DB._classify_theater = s.old
        return False


# (а) явный префикс «пк:»/«pc:» → pc, префикс срезан, карточка с 🎭 pc; слой 2 не зовётся
def test_a_explicit_prefix():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("тз: пк: поправь черновики", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "поправь черновики", "pc"), \
            f"«тз: пк:» → 328-метка + lane=pc, префикс срезан: {b.calls}"
        assert "🎭 pc" in r and "55" in r, f"карточка приёма показывает 🎭 pc: {r}"
        r = DB._try_enqueue("задача: pc: пингани агента", b)
        assert b.calls[-1] == (DB.QUEUE_FROM, "пингани агента", "pc"), f"«pc:» тоже: {b.calls}"
        assert "🎭 pc" in r
        r = DB._try_enqueue("декомпозируй: пк: большое ТЗ", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEC, "большое ТЗ", None), \
            f"дек→pc: родитель Filipp-pc-dec БЕЗ lane (кусок 2): {b.calls}"
        assert "🎭 pc" in r and "театр PC" in r
        assert DB._try_enqueue("тз: пк:", b).startswith("🤖 Пустое ТЗ"), \
            "«тз: пк:» без текста → отказ как пустое"


# (б) keyword-слой: pc-слова → pc без думателя
def test_b_keywords_pc():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("тз: поправь suggest.py в userbot", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "поправь suggest.py в userbot", "pc"), \
            f"keywords userbot/suggest → театр pc: {b.calls}"
        assert "🎎" not in r and "🎭 pc" in r


# (в) keyword-слой: vps-слова → vps, enqueue байт-в-байт как раньше (без lane)
def test_c_keywords_vps():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("тз: прогони гейт", b)
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "прогони гейт", None), \
            f"vps-театр: старая метка, БЕЗ lane: {b.calls}"
        assert "🎭 vps" in r, f"карточка показывает 🎭 vps: {r}"
        assert DB.ROUTER_HINT not in r, "подсказка fail-safe НЕ показывается при решении слоя 1"


# (г) неоднозначный текст → слой 2 думатель → театр по его JSON
def test_d_layer2_decides():
    with _NoLayer2(ret="pc") as m:
        b = EnqBridge()
        r = DB._try_enqueue("тз: сделай что-нибудь полезное", b)
        assert m.calls == ["сделай что-нибудь полезное"], f"слой 2 позван один раз: {m.calls}"
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "сделай что-нибудь полезное", "pc")
        assert "🎭 pc" in r
    with _NoLayer2(ret="vps") as m:
        b = EnqBridge()
        DB._try_enqueue("задача: сделай что-нибудь полезное", b)
        assert m.calls and b.calls[-1] == (DB.QUEUE_FROM, "сделай что-нибудь полезное", None)
    # оба класса keywords совпали → тоже слой 2 (спека: «оба класса совпали или ни один»)
    with _NoLayer2(ret="vps") as m:
        b = EnqBridge()
        DB._try_enqueue("тз: перенеси playbook из userbot в splinter на vps", b)
        assert m.calls, "pc-слова И vps-слова разом → решает слой 2"


# (д) сбой думателя → fail-safe vps + строка-подсказка в карточке
def test_e_failsafe_vps():
    with _NoLayer2(ret=None) as m:
        b = EnqBridge()
        r = DB._try_enqueue("тз: сделай что-нибудь полезное", b)
        assert m.calls, "слой 2 позвался"
        assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "сделай что-нибудь полезное", None), \
            f"fail-safe → vps (прежний enqueue): {b.calls}"
        assert "🎭 vps" in r and DB.ROUTER_HINT in r, f"подсказка «нужен ПК — префикс пк:»: {r}"


# (е) тема 829 (lane='pc') = явный вход БЕЗ роутера — поведение как раньше, слой 2 не зовётся
def test_f_829_explicit_no_router():
    with _NoLayer2():
        b = EnqBridge()
        r = DB._try_enqueue("тз: собери X", b, lane="pc")
        assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEV, "собери X", "pc"), f"829 как раньше: {b.calls}"
        assert "🎭" not in r, f"явный вход — без бейджа роутера: {r}"
        r = DB._try_enqueue("декомпозируй: пк: как текст", b, lane="pc")
        assert b.calls[-1] == (DB.QUEUE_FROM_PC_DEC, "пк: как текст", None), \
            f"829: пк:-префикс НЕ срезается (роутера нет): {b.calls}"


# Откат: THEATER_ROUTER=0 → прежнее поведение байт-в-байт (префикс не срезан, без 🎭, без слоя 2)
def test_router_off_rollback():
    os.environ["THEATER_ROUTER"] = "0"
    try:
        with _NoLayer2():
            b = EnqBridge()
            r = DB._try_enqueue("тз: пк: поправь черновики", b)
            assert b.calls[-1] == (DB.QUEUE_FROM_DEV, "пк: поправь черновики", None), \
                f"роутер выключен: пк: уходит текстом, БЕЗ lane: {b.calls}"
            assert "🎭" not in r, f"без бейджа: {r}"
    finally:
        os.environ["THEATER_ROUTER"] = "1"


# Карточки идут в тему ПОСТАНОВКИ: from=Filipp-328* (даже lane=pc) → 328; from=Filipp-pc* → PC-дев
def test_topic_by_from_label():
    os.environ["PC_DEV_TOPIC_ID"] = "777"
    try:
        assert DB._item_topic({"from": DB.QUEUE_FROM_DEV, "lane": "pc"}) == DB.DEVBOT_TOPIC, \
            "роутнутая на pc задача из 328 отчитывается в 328 (тема постановки)"
        assert DB._item_topic({"from": DB.QUEUE_FROM_PC, "lane": "pc"}) == 777, \
            "задача из 829 отчитывается в 829 (как раньше)"
        assert DB._item_topic({"from": DB.QUEUE_FROM_PC_DEC}) == 777, \
            "цепь pc-декомпозиции — в теме PC-дев (кусок 2 как был)"
        assert DB._item_lane_label({"from": DB.QUEUE_FROM_DEV, "lane": "pc"}) == "pc", \
            "ярлык полосы остаётся по lane: [pc]"
        assert DB._item_lane_label({"from": DB.QUEUE_FROM_DEV}) == "vps"
    finally:
        os.environ.pop("PC_DEV_TOPIC_ID", None)


# Слой 2 (unit): парс CLI-конверта/JSON, exit!=0, мусор, таймаут — всё через подмену subprocess.run
def test_classifier_parsing():
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(
            returncode=0,
            stdout='{"result": "{\\"theater\\":\\"pc\\",\\"reason\\":\\"userbot\\"}"}',
            stderr="")
    old = DB.subprocess.run
    DB.subprocess.run = fake_run
    try:
        assert DB._classify_theater("текст") == "pc", "конверт CLI + строгий JSON → pc"
        cmd = calls[-1]
        assert cmd[-1].endswith("текст") and "--max-turns" in cmd and "haiku" in cmd \
            and "sonnet" in cmd and "--fallback-model" in cmd, \
            f"кондуктор haiku→sonnet, --max-turns 1, prompt последним: {cmd}"
        DB.subprocess.run = lambda *a, **k: types.SimpleNamespace(
            returncode=1, stdout='{"theater":"pc"}', stderr="")
        assert DB._classify_theater("x") is None, "exit!=0 → None (fail-safe)"
        DB.subprocess.run = lambda *a, **k: types.SimpleNamespace(
            returncode=0, stdout="мусор без json", stderr="")
        assert DB._classify_theater("x") is None, "мусор → None"
        DB.subprocess.run = lambda *a, **k: types.SimpleNamespace(
            returncode=0, stdout='{"theater":"луна"}', stderr="")
        assert DB._classify_theater("x") is None, "невалидный театр → None"

        def boom(*a, **k):
            raise OSError("нет бинаря")
        DB.subprocess.run = boom
        assert DB._classify_theater("x") is None, "исключение запуска → None"
    finally:
        DB.subprocess.run = old


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов роутера театра (кусок 3 «единый пульт»)")
