"""Гейт-алерты владельцу — только на ФИНАЛЬНОМ прогоне (хвост §7, 12.07.2026).

Промежуточные красные прогоны gate.py ВНУТРИ headless-задачи (демон ставит claude -p окружение
GATE_ALERT_FINAL_ONLY=1) — штатный red-fix-green цикл: exit 1 / боевой_лог остаются, Telegram-пуш
подавлен. Финальный прогон (pre-push hook зовёт gate.py --final) алертит ВСЕГДА, даже внутри
headless. FAIL-SAFE: env нет / значение не «1» / сбой чтения → алерт как раньше.
Всё in-process с моками (run_tests/_log/_push) — ни сети, ни реальных тестов, ни пушей."""
import io
import os
import sys
import json
import contextlib

ROOT = "/root/turbobaby-manager-bot"
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")     # изоляция от боевого .env
os.environ.setdefault("STEP_SELFHEAL", "0")
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

res = []
def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c

import gate

pushes, logs = [], []
gate._push = lambda text: pushes.append(text)
gate._log = lambda result, args_str: logs.append((result, args_str))

def run_gate(argv, env_flag=None, red=True):
    """Прогнать gate.main() с мокнутым результатом тестов. Вернуть (exit_code, stdout)."""
    pushes.clear(); logs.clear()
    gate.run_tests = (lambda: (["test_fake_red.py"], 3, 0.1)) if red else (lambda: ([], 3, 0.1))
    # Мокаем run_selective_tests — при GATE_STEP_SELECTIVE=1 (headless-контекст) gate.main()
    # идёт в selective-ветку; без мока вызывается реальный прогон тестов → таймаут.
    gate.run_selective_tests = (lambda *_: (["test_fake_red.py"], 3, 0.1, "селективный (мок)")) if red else (lambda *_: ([], 3, 0.1, "селективный (мок)"))
    old_argv, old_env = sys.argv, os.environ.get("GATE_ALERT_FINAL_ONLY")
    sys.argv = ["gate.py"] + argv
    if env_flag is None:
        os.environ.pop("GATE_ALERT_FINAL_ONLY", None)
    else:
        os.environ["GATE_ALERT_FINAL_ONLY"] = env_flag
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = gate.main()
    finally:
        sys.argv = old_argv
        if old_env is None:
            os.environ.pop("GATE_ALERT_FINAL_ONLY", None)
        else:
            os.environ["GATE_ALERT_FINAL_ONLY"] = old_env
    return code, buf.getvalue()

# (1) FAIL-SAFE дефолт: контекста нет (Termux/cron/девбот) → красный алертит КАК РАНЬШЕ
print("(1) красный без контекста → алерт как раньше:")
code, out = run_gate([])
ok(code == 1 and len(pushes) == 1 and "ТЕСТЫ КРАСНЫЕ" in pushes[0], "exit 1 + пуш ушёл (поведение не изменилось)")
ok(logs and logs[0][0] == "blocked_by_tests" and "подавлен" not in logs[0][1], "боевой_лог blocked_by_tests без пометки подавления")

# (2) промежуточный headless-прогон: env=1, БЕЗ --final → тихо (блок/лог целы, пуша НЕТ)
print("(2) промежуточный headless-прогон → тихо:")
code, out = run_gate(["--for", "push"], env_flag="1")
ok(code == 1, "решение гейта НЕ ослаблено: exit 1 (деплой блокирован)")
ok(pushes == [], "Telegram-пуш ПОДАВЛЕН (ноль исходящих)")
ok(logs and logs[0][0] == "blocked_by_tests" and "подавлен" in logs[0][1], "боевой_лог записан + пометка подавления")
ok("подавлен" in out and "КРАСНЫЕ ТЕСТЫ" in out, "терминал честно показывает красный и факт подавления")

# (3) ФИНАЛЬНЫЙ прогон внутри headless: env=1 + --final (pre-push) → алерт живой
print("(3) финальный прогон (pre-push --final) внутри headless → алерт живой:")
code, out = run_gate(["--for", "push", "--final"], env_flag="1")
ok(code == 1 and len(pushes) == 1 and "ЗАБЛОКИРОВАН" in pushes[0], "--final бьёт подавление: пуш ушёл")

# (4) FAIL-SAFE на мусор в env: только строгое «1» глушит
print("(4) мусор в env → алерт (fail-safe):")
for junk in ("0", "true", "", " да "):
    code, _ = run_gate([], env_flag=junk)
    ok(code == 1 and len(pushes) == 1, f"env={junk!r} → алерт как раньше")

# (5) зелёный прогон под env → exit 0, пуша нет (регресс)
print("(5) зелёный прогон не тронут:")
code, out = run_gate([], env_flag="1", red=False)
ok(code == 0 and pushes == [] and "разрешена" in out, "зелёный: exit 0, без пуша, как раньше")

# (6) fail-safe _alert_allowed при сбое чтения окружения → True (алертить)
print("(6) сбой чтения env → алертить:")
class _BoomEnv:
    def get(self, *a, **kw):
        raise RuntimeError("boom")
_old_environ = gate.os.environ
gate.os.environ = _BoomEnv()
try:
    allowed = gate._alert_allowed(False)
finally:
    gate.os.environ = _old_environ
ok(allowed is True, "исключение при чтении env → алерт (в сторону шума, не тишины)")

# (7) демон даёт claude -p окружение GATE_ALERT_FINAL_ONLY=1 (детерминизм контекста)
print("(7) run_task демона несёт флаг подавления в child_env:")
import orchestrator_daemon as OD
class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

CAP = {}
_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0
_fake_good_out = json.dumps({"result": "готово", "is_error": False, "modelUsage": {}})

def fake_popen(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return FakePopen(out=_fake_good_out)

OD.subprocess.run = lambda args, **kw: type("P", (), {"stdout": "", "stderr": "", "returncode": 0})()
OD._POPEN = fake_popen
try:
    st, _r = OD.run_task(1, "проверь X", task_timeout=60)
finally:
    OD.subprocess.run = _real_run
    OD._POPEN = _real_POPEN
    OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS
ok(st == "done", "мок-задача прошла (run_task жив)")
ok((CAP.get("env") or {}).get("GATE_ALERT_FINAL_ONLY") == "1", "child_env claude -p несёт GATE_ALERT_FINAL_ONLY=1")

# (8) pre-push hook зовёт gate.py с --final (финальность деплой-прогона детерминированна)
print("(8) pre-push hook несёт --final:")
with open(os.path.join(ROOT, "deploy", "hooks", "pre-push"), encoding="utf-8") as f:
    hook = f.read()
ok("gate.py --for push --final" in hook, "pre-push: gate.py --for push --final")

# (9) --override путь не тронут (по «да» Филиппа)
print("(9) override-регресс:")
code, out = run_gate(["--override", "ложный красный"], env_flag="1")
ok(code == 0 and pushes == [] and logs and logs[0][0] == "test_override", "override: exit 0, лог test_override")

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
