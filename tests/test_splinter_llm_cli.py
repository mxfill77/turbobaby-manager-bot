"""Фаза 1: quick()/judge() уходят на ПОДПИСКУ (claude -p/Max) при SPLINTER_LLM_VIA_CLI=1.
Мок CLI-seam (_run_claude_cli) + мок Anthropic — реальных сетевых/CLI/денежных вызовов НЕТ.
Проверяет инварианты: флаг on → CLI; env БЕЗ ANTHROPIC_API_KEY; нейтральный tempdir-cwd;
модель сохранена (quick→sonnet, judge→haiku); флаг off → старый API-путь (fallback);
timeout/rc!=0 → понятная SplinterLLMError (не сырой 400) + graceful ''/{}; формат ответа
(снятие ```-обрамления) сохранён — money-JSON парсится как раньше."""
import os, sys, json

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")   # ClaudeClient.__init__ требует ключ (для fallback-клиента)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.pop("SPLINTER_LLM_VIA_CLI", None)      # старт с ВЫКЛЮЧЕННОГО флага (как в проде)

import claude_client as CC


def _client():
    return CC.ClaudeClient()   # реальный клиент; Anthropic('x') конструируется без сети


class _Recorder:
    """Фейковый CLI-seam: ловит (cmd, env, cwd, timeout, stdin), отдаёт stdout или бросает."""
    def __init__(self, out="", exc=None):
        self.out, self.exc, self.calls = out, exc, []

    def __call__(self, cmd, env, cwd, timeout, stdin=None):
        self.calls.append({"cmd": cmd, "env": env, "cwd": cwd, "timeout": timeout, "stdin": stdin})
        if self.exc:
            raise self.exc
        return self.out


# --- фейковый Anthropic-ответ (для проверки fallback при флаге off) ---
class _Blk:
    def __init__(self, t): self.type, self.text = "text", t
class _Resp:
    def __init__(self, t): self.content = [_Blk(t)]
class _FakeMessages:
    def __init__(self, t): self._t, self.calls = t, 0
    def create(self, **kw):
        self.calls += 1
        return _Resp(self._t)
class _FakeAnthropic:
    def __init__(self, t): self.messages = _FakeMessages(t)


def _on():  os.environ["SPLINTER_LLM_VIA_CLI"] = "1"
def _off(): os.environ.pop("SPLINTER_LLM_VIA_CLI", None)


def test_quick_via_cli_when_flag_on():
    c = _client()
    rec = _Recorder(out='```json\n{"type":"transaction","amount":1000}\n```')
    c._run_claude_cli = rec
    _on()
    try:
        out = c.quick("SYS money", "อัดนี้ 1000 บาท")   # тайский money «запиши»
    finally:
        _off()
    assert len(rec.calls) == 1, "quick при флаге on должен идти по CLI-seam"
    call = rec.calls[0]
    assert "ANTHROPIC_API_KEY" not in call["env"], "env дочернего claude -p не несёт платный ключ"
    assert "OPENAI_API_KEY" not in call["env"]
    assert call["cmd"][0] == CC.CLAUDE_CLI_BIN and "-p" in call["cmd"]
    assert "--model" in call["cmd"] and "claude-sonnet-4-5" in call["cmd"], "quick → sonnet сохранён"
    assert "splinter_llm_" in call["cwd"], "нейтральный tempdir-cwd (не репо)"
    # формат: ```-обрамление снято → контракт как на API-пути, money-JSON парсится
    assert out == '{"type":"transaction","amount":1000}', f"fence-strip сохраняет контракт: {out!r}"
    assert json.loads(out)["amount"] == 1000


def test_prompt_goes_via_stdin_not_argv():
    """Боевой баг 06.07: money-расход '-100' (ведущий '-') нельзя класть позиционным argv —
    claude-CLI (commander) парсит его как неизвестную опцию → rc=1, money не разбирается.
    Промпт ОБЯЗАН идти через stdin; в argv его быть НЕ должно."""
    c = _client()
    rec = _Recorder(out='{"type":"transaction","moves":[{"amount":-100,"currency":"THB"}]}')
    c._run_claude_cli = rec
    _on()
    try:
        out = c.quick("MONEY_SYS", "-100")     # кассовый расход, ведущий '-'
    finally:
        _off()
    call = rec.calls[0]
    assert call["stdin"] == "-100", "user-промпт передан через stdin"
    assert "-100" not in call["cmd"], "user-промпт НЕ должен быть позиционным argv (иначе '-' = опция)"
    assert json.loads(out)["moves"][0]["amount"] == -100, "money-расход парсится"


def test_judge_via_cli_uses_haiku():
    c = _client()
    rec = _Recorder(out='вердикт: {"ok": true, "score": 5}')   # judge извлекает {...} из текста
    c._run_claude_cli = rec
    _on()
    try:
        d = c.judge("SYS", "user")
    finally:
        _off()
    assert len(rec.calls) == 1
    assert "claude-haiku-4-5" in rec.calls[0]["cmd"], "judge сохраняет модель Haiku (не self.model)"
    assert d == {"ok": True, "score": 5}, "judge парсит JSON из ответа CLI"


def test_flag_off_uses_api_fallback():
    c = _client()
    c.client = _FakeAnthropic("ПЛОСКИЙ_ОТВЕТ_API")   # подменяем платный клиент
    rec = _Recorder(out="CLI_НЕ_ДОЛЖЕН_ЗВАТЬСЯ")
    c._run_claude_cli = rec
    _off()   # флаг выключен
    out = c.quick("SYS", "txt")
    assert out == "ПЛОСКИЙ_ОТВЕТ_API", "флаг off → старый API-путь (fallback цел)"
    assert len(rec.calls) == 0, "CLI-seam НЕ зовётся при флаге off"
    assert c.client.messages.calls == 1, "вызван именно платный клиент"


def test_cli_failure_is_clear_error_not_400():
    c = _client()
    c._run_claude_cli = _Recorder(exc=CC.SplinterLLMError("claude -p rc=1: subscription unreachable"))
    _on()
    try:
        q = c.quick("SYS", "txt")     # graceful
        j = c.judge("SYS", "txt")
        err = None
        try:
            c._cli_generate("SYS", "txt", "claude-sonnet-4-5")
        except CC.SplinterLLMError as e:
            err = str(e)
    finally:
        _off()
    assert q == "" and j == {}, "недоступность CLI → graceful ''/{} (не падение потока)"
    assert err is not None, "_cli_generate бросает типизированный SplinterLLMError"
    assert "credit balance" not in err.lower() and "400" not in err, "ошибка понятная, не сырой anthropic-400"


def test_cli_timeout_raises_clear():
    import subprocess as _sp
    c = _client()
    def fake_run(*a, **k):
        raise _sp.TimeoutExpired(cmd="claude", timeout=k.get("timeout", 1))
    orig = CC.subprocess.run
    CC.subprocess.run = fake_run
    try:
        err = None
        try:
            c._run_claude_cli(["claude", "-p", "x"], {"HOME": "/root"}, "/tmp", 1)
        except CC.SplinterLLMError as e:
            err = str(e)
    finally:
        CC.subprocess.run = orig
    assert err is not None, "timeout → SplinterLLMError"
    assert "credit balance" not in err.lower() and "400" not in err, "понятный timeout, не 400"


def test_env_strips_key_even_when_present():
    """_cli_generate вырезает ANTHROPIC_API_KEY из env дочернего процесса, даже если он в окружении."""
    c = _client()
    prev = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "paid-key-должен-исчезнуть"
    rec = _Recorder(out="ok")
    c._run_claude_cli = rec
    _on()
    try:
        c._cli_generate("SYS", "txt", "claude-sonnet-4-5")
    finally:
        _off()
        if prev is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = prev
    assert "ANTHROPIC_API_KEY" not in rec.calls[0]["env"], "ключ вырезан из env claude -p"
    assert rec.calls[0]["env"].get("HOME") == "/root", "HOME сохранён (иначе Max-auth не найдётся)"


def test_strip_code_fences_helper():
    assert CC._strip_code_fences('```json\n{"a":1}\n```') == '{"a":1}'
    assert CC._strip_code_fences('{"a":1}') == '{"a":1}', "чистый JSON не трогаем"
    assert CC._strip_code_fences('สวัสดี ครับ') == 'สวัสดี ครับ', "перевод (не-JSON) остаётся как есть"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"OK — {len(fns)} тестов splinter_llm_cli")
