"""Ускорение цепей ч.2 (13.07.2026): селективный гейт промежуточных шагов декомпозиции.

Промежуточные шаги [шаг i/N родитель id] с i < N → GATE_STEP_SELECTIVE=1 в child_env claude -p;
gate.py на этом флаге + без --final → run_selective_tests (smoke + тесты затронутых модулей).
Последний шаг (i == N), одиночки, планировщик — полный сьют. --final всегда бьёт флаг.
Fail-safe: не удалось определить затронутое → полный сьют (label «полный (fail-safe…)»).
Всё in-process с моками (subprocess.run, файловая система) — ни сети, ни реальных тестов."""
import io, os, sys, json, glob, contextlib, tempfile, shutil

ROOT = "/root/turbobaby-manager-bot"
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"  # изоляция от боевого .env

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


# ── gate.py ──────────────────────────────────────────────────────────────────
import gate

pushes, logs = [], []
gate._push = lambda text: pushes.append(text)
gate._log = lambda result, args_str: logs.append((result, args_str))


def run_gate(argv, env_overrides=None, run_tests_ret=None, run_selective_ret=None):
    """Прогнать gate.main() in-process с мокнутыми run_tests/run_selective_tests."""
    pushes.clear(); logs.clear()
    env_overrides = env_overrides or {}
    old_run_tests = gate.run_tests
    old_run_selective = gate.run_selective_tests
    old_changed_py_files = gate._changed_py_files
    gate.run_tests = lambda: (run_tests_ret if run_tests_ret is not None else ([], 10, 0.1))
    gate.run_selective_tests = lambda changed: (
        run_selective_ret if run_selective_ret is not None
        else ([], 3, 0.1, "селективный (3 тестов)")
    )
    gate._changed_py_files = lambda: []   # не вызываем реальный git в тестах
    old_argv = sys.argv
    saved_env = {}
    for k in ("GATE_STEP_SELECTIVE", "GATE_ALERT_FINAL_ONLY"):
        saved_env[k] = os.environ.get(k)
        if k in env_overrides:
            os.environ[k] = env_overrides[k]
        else:
            os.environ.pop(k, None)
    sys.argv = ["gate.py"] + argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = gate.main()
    finally:
        sys.argv = old_argv
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        gate.run_tests = old_run_tests
        gate.run_selective_tests = old_run_selective
        gate._changed_py_files = old_changed_py_files
    return code, buf.getvalue()


# ── (1–3) _step_selective() ──────────────────────────────────────────────────
print("(1–3) gate._step_selective():")
os.environ["GATE_STEP_SELECTIVE"] = "1"
ok(gate._step_selective() is True, "GATE_STEP_SELECTIVE=1 → True")
os.environ.pop("GATE_STEP_SELECTIVE")
ok(gate._step_selective() is False, "нет переменной → False")
for junk in ("0", "true", "yes", ""):
    os.environ["GATE_STEP_SELECTIVE"] = junk
    ok(gate._step_selective() is False, f"GATE_STEP_SELECTIVE={junk!r} → False (строгое «1»)")
    os.environ.pop("GATE_STEP_SELECTIVE")

# ── (4) без флага → полный сьют ──────────────────────────────────────────────
print("\n(4) main() без GATE_STEP_SELECTIVE → полный:")
code, out = run_gate([], run_tests_ret=([], 7, 0.1))
ok(code == 0 and "полный" in out and "7" in out, "без флага → run_tests (полный), вывод «полный»")

# ── (5) GATE_STEP_SELECTIVE=1 без --final → selective ────────────────────────
print("\n(5) GATE_STEP_SELECTIVE=1 → selective:")
code, out = run_gate([], env_overrides={"GATE_STEP_SELECTIVE": "1"},
                     run_selective_ret=([], 4, 0.1, "селективный (4 тестов)"))
ok(code == 0 and "селективный" in out and "4" in out, "флаг → run_selective_tests, вывод «селективный»")

# ── (6) --final бьёт GATE_STEP_SELECTIVE=1 → полный ─────────────────────────
print("\n(6) --final бьёт selective → полный:")
code, out = run_gate(["--final"], env_overrides={"GATE_STEP_SELECTIVE": "1"},
                     run_tests_ret=([], 9, 0.2))
ok(code == 0 and "полный" in out and "9" in out, "--final + флаг → run_tests (полный сьют)")
ok("selective" not in out.lower() or "fail" not in out.lower(),
   "--final: вывод не несёт «селективный» (полный)")

# ── (7) selective красный → exit 1 (блок не ослаблен) ───────────────────────
print("\n(7) selective красный → exit 1:")
code, out = run_gate([], env_overrides={"GATE_STEP_SELECTIVE": "1", "GATE_ALERT_FINAL_ONLY": "1"},
                     run_selective_ret=(["test_foo.py"], 4, 0.1, "селективный (4 тестов)"))
ok(code == 1, "selective красный → exit 1 (решение гейта не ослаблено)")
ok("КРАСНЫЕ" in out and "ЗАБЛОКИРОВАН" in out, "selective красный → печатает блок")
ok("test_foo.py" in out, "selective красный → упавший тест назван")

# ── (8) fail-safe label в выводе ─────────────────────────────────────────────
print("\n(8) fail-safe label в выводе:")
code, out = run_gate([], env_overrides={"GATE_STEP_SELECTIVE": "1"},
                     run_selective_ret=([], 10, 0.5, "полный (fail-safe: 10 тестов)"))
ok(code == 0, "fail-safe → exit 0 (зелёный)")
ok("fail-safe" in out, "fail-safe: label «fail-safe» виден в выводе")

# ── (9) override не тронут ────────────────────────────────────────────────────
print("\n(9) --override регресс:")
code, out = run_gate(["--override", "ложный красный"],
                     env_overrides={"GATE_STEP_SELECTIVE": "1"})
ok(code == 0 and logs and logs[0][0] == "test_override", "override: exit 0, лог test_override")

# ── (10–13) _affected_test_files() с temp-директорией ───────────────────────
print("\n(10–13) gate._affected_test_files():")
tmp = tempfile.mkdtemp()
try:
    # тест, ссылающийся на orchestrator_daemon
    with open(os.path.join(tmp, "test_orch_check.py"), "w") as f:
        f.write("import orchestrator_daemon\n# tests for orchestrator_daemon\n")
    # тест, ссылающийся на gate
    with open(os.path.join(tmp, "test_gate_stuff.py"), "w") as f:
        f.write("from gate import run_tests\nimport gate\n")
    # несвязанный тест
    with open(os.path.join(tmp, "test_unrelated.py"), "w") as f:
        f.write("# unrelated test, no special imports\n")

    old_TESTS_DIR = gate.TESTS_DIR
    gate.TESTS_DIR = tmp

    # (10) orchestrator_daemon.py → нашли test_orch_check.py, не нашли test_unrelated.py
    affected = gate._affected_test_files(["orchestrator_daemon.py"])
    names = [os.path.basename(p) for p in affected]
    ok("test_orch_check.py" in names,
       "orchestrator_daemon.py → test_orch_check.py найден (ссылается на модуль)")
    ok("test_unrelated.py" not in names,
       "test_unrelated.py НЕ включён (не ссылается на orchestrator_daemon)")

    # (11) gate.py → нашли test_gate_stuff.py
    affected2 = gate._affected_test_files(["gate.py"])
    names2 = [os.path.basename(p) for p in affected2]
    ok("test_gate_stuff.py" in names2, "gate.py → test_gate_stuff.py найден")

    # (12) пустой список → [] (не запускаем полный)
    ok(gate._affected_test_files([]) == [], "пустые changed_files → [] (не вызываем полный)")

    # (13) файл без .py → модуль = пустая строка, ничего не матчит
    ok(gate._affected_test_files(["README.md"]) == [],
       "README.md → [] (не py, ни один тест не ссылается на «README»)")

finally:
    gate.TESTS_DIR = old_TESTS_DIR
    shutil.rmtree(tmp)

# ── (14–16) _changed_py_files() ─────────────────────────────────────────────
print("\n(14–16) gate._changed_py_files():")

class FakeGitResult:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout; self.returncode = returncode; self.stderr = ""

_real_subprocess_run = gate.subprocess.run

# (14) git возвращает .py и не-.py файлы → только .py базовые имена
gate.subprocess.run = lambda args, **kw: FakeGitResult(
    "src/foo.py\nbar.py\nREADME.md\nbaz.py\n")
result = gate._changed_py_files()
ok("foo.py" in result and "bar.py" in result and "baz.py" in result,
   "_changed_py_files: .py файлы извлечены")
ok("README.md" not in result, "не-.py файлы не включаются")

# (15) git возвращает ошибку → [] (fail-safe)
gate.subprocess.run = lambda args, **kw: FakeGitResult("", returncode=1)
ok(gate._changed_py_files() == [], "git error (rc=1) → [] (fail-safe полного сьюта)")

# (16) исключение при вызове subprocess → [] (fail-safe)
def boom(*a, **kw): raise OSError("git not found")
gate.subprocess.run = boom
ok(gate._changed_py_files() == [], "исключение subprocess → [] (fail-safe)")

gate.subprocess.run = _real_subprocess_run

# ── (17–24) orchestrator_daemon: GATE_STEP_SELECTIVE в child_env ─────────────
print("\n(17–24) orchestrator_daemon.run_task: GATE_STEP_SELECTIVE в child_env:")
import orchestrator_daemon as OD

_good_out = json.dumps({"result": "готово", "is_error": False,
                         "modelUsage": {"claude-fable-5": {}}})
_plan_out = json.dumps({"result": "1. шаг один\n2. шаг два", "is_error": False,
                         "modelUsage": {"claude-fable-5": {}}})

CAP = {}
_real_od_run = OD.subprocess.run


def cap_run(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return type("P", (), {
        "stdout": _good_out, "stderr": "", "returncode": 0
    })()

OD.subprocess.run = cap_run

# (17) промежуточный шаг 2/5 → GATE_STEP_SELECTIVE=1
OD.run_task(1, "[шаг 2/5 родитель 10] сделай X", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") == "1",
   "шаг 2/5 (промежуточный) → GATE_STEP_SELECTIVE=1 в child_env")

# (18) шаг 1/3 → тоже intermediate
OD.run_task(2, "[шаг 1/3 родитель 10] первый шаг", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") == "1", "шаг 1/3 → GATE_STEP_SELECTIVE=1")

# (19) шаг 1/1 → единственный (последний) → нет флага
OD.run_task(3, "[шаг 1/1 родитель 10] единственный", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1",
   "шаг 1/1 (единственный/последний) → нет GATE_STEP_SELECTIVE")

# (20) шаг 5/5 → последний → нет флага
OD.run_task(4, "[шаг 5/5 родитель 10] последний шаг", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1",
   "шаг 5/5 (последний) → нет GATE_STEP_SELECTIVE (полный сьют)")

# (21) шаг 2/2 → последний из двух → нет флага
OD.run_task(5, "[шаг 2/2 родитель 10] последний из двух", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1", "шаг 2/2 → нет флага")

# (22) одиночная задача (нет [шаг i/N]) → нет флага
OD.run_task(6, "обычная одиночная задача без маркера", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1",
   "одиночная задача → нет GATE_STEP_SELECTIVE")

# (23) планировщик (preamble != None) → нет флага, даже если текст похож на шаг
def cap_run_plan(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return type("P", (), {"stdout": _plan_out, "stderr": "", "returncode": 0})()

OD.subprocess.run = cap_run_plan
OD.run_task(7, "[шаг 2/5 родитель 10] планировщик-тест", task_timeout=60,
            preamble=OD.PLANNER_PREAMBLE)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1",
   "планировщик (preamble != None) → нет GATE_STEP_SELECTIVE")

# (24) GATE_ALERT_FINAL_ONLY=1 по-прежнему выставляется (регресс)
OD.subprocess.run = cap_run
OD.run_task(8, "[шаг 3/7 родитель 10] шаг для регресса", task_timeout=60)
ok(CAP["env"].get("GATE_ALERT_FINAL_ONLY") == "1",
   "GATE_ALERT_FINAL_ONLY=1 цел (регресс: оба флага вместе в child_env)")
ok(CAP["env"].get("GATE_STEP_SELECTIVE") == "1",
   "GATE_STEP_SELECTIVE=1 и GATE_ALERT_FINAL_ONLY=1 стоят вместе (промежуточный шаг 3/7)")

OD.subprocess.run = _real_od_run

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else 'ЕСТЬ FAIL (%d/%d)' % (sum(res), len(res))}")
sys.exit(0 if all(res) else 1)
