"""Команда «сверься»/«реестр» в теме 328 (реестр знания, запуск с телефона, 06.07.2026).
Зелёная read-only: девбот-allowlist → registry_check.py → сжатый отчёт в 328. Проверяем:
(R1) «сверься»/«реестр» роутятся на _g_registry, не шадовятся ранними ключами;
(R2) существующие ключи (статус/гейт) НЕ перехвачены новым префиксом;
(R3) _g_registry зовёт registry_check.py подпроцессом (read-only, таймаут ≥60с);
(R4) чужой (не Филипп) — игнор.
Запуск standalone (как весь gate): python3 tests/test_devbot_registry.py."""
import sys, os, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB


def test_registry_keywords_route_to_registry():
    orig = DB._g_registry
    DB._g_registry = lambda: "SENTINEL_REG"          # без сети/подпроцесса
    try:
        for word in ("сверься", "Сверься", "реестр", "РЕЕСТР", "сверка", "сверить", "registry"):
            fn = DB._match(word)
            assert fn is not None, f"«{word}» не поймана allowlist"
            assert fn(None) == "SENTINEL_REG", f"«{word}» ушла не в реестр"
    finally:
        DB._g_registry = orig


def test_registry_does_not_shadow_existing():
    orig_r, orig_g = DB._g_registry, DB._g_gate
    DB._g_registry = lambda: "SENTINEL_REG"
    DB._g_gate = lambda: "SENTINEL_GATE"
    try:
        reg_fn = DB._match("сверься")
        assert reg_fn(None) == "SENTINEL_REG"                   # реестр ловится
        assert DB._match("статус") is not reg_fn                # пульс — другая функция, не перехвачен
        assert DB._match("мозг") is not reg_fn                  # «свеж»/мозг не путается со «сверься»
        assert DB._match("гейт")(None) == "SENTINEL_GATE"       # гейт цел
        assert DB._match("здоровье") is not None                # health цел
    finally:
        DB._g_registry, DB._g_gate = orig_r, orig_g


def test_registry_calls_subprocess_readonly():
    calls = {}
    class R:
        returncode = 0
        stdout = "🧭 РЕЕСТР ЗНАНИЯ\n✅ СХОДИТСЯ — 3 проверки, 0 расхождений"
        stderr = ""
    def fake_run(argv, cwd=None, capture_output=None, text=None, timeout=None):
        calls["argv"] = list(argv); calls["timeout"] = timeout
        return R()
    orig = DB.subprocess.run
    DB.subprocess.run = fake_run
    try:
        out = DB._g_registry()
    finally:
        DB.subprocess.run = orig
    assert calls["argv"][-1].endswith("registry_check.py"), calls["argv"]
    assert "--self-test" not in calls["argv"] and "--json" not in calls["argv"]  # живой отчёт
    assert calls["timeout"] and calls["timeout"] >= 60
    assert "СХОДИТСЯ" in out


class _Bot:
    def __init__(s): s.sends = []
    async def send_message(s, chat_id, message_thread_id=None, text="", reply_markup=None):
        s.sends.append(text)


class _Ctx:
    def __init__(s): s.bot = _Bot()


class _User:
    def __init__(s, uid): s.id = uid


class _Msg:
    def __init__(s, uid, text):
        s.from_user = _User(uid); s.text = text
        s.message_thread_id = DB.DEVBOT_TOPIC; s.chat_id = DB.HQ_CHAT_ID


def test_registry_ignores_non_philipp():
    ctx = _Ctx()
    msg = _Msg(999999, "сверься")                    # не Филипп
    asyncio.run(DB.handle_command(msg, ctx, bridge=None))
    assert ctx.bot.sends == [], f"чужому не должны ничего слать: {ctx.bot.sends}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов команды «сверься»/«реестр» (реестр знания с телефона)")
