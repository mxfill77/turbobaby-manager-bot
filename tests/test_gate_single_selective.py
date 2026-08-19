"""Селективный гейт для одиночных задач (15.07.2026).

GATE_SINGLE_SELECTIVE=1 в .env → одиночные «тз:»/«задача:» тоже идут в gate.py
с GATE_STEP_SELECTIVE=1 (smoke + тесты затронутых модулей).
Дефолт 0 = текущее поведение (полный гейт), fail-safe gate.py: не смог определить
затронутые → полный сьют автоматически (без действий на нашей стороне).
Полный гейт: pre-push --final, последний шаг цепи (i == N), планировщик — без изменений."""
import io, os, sys, json, contextlib

ROOT = "/root/turbobaby-manager-bot"
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"
os.environ["GATE_SINGLE_SELECTIVE"] = "0"   # изоляция: боевой .env может иметь =0/=1
# Изоляция от МЕТКИ ДОСТАВКИ (`prod_gate.ENV_MARK` = CC_PROD_DELIVERY): её ставит демон задаче
# доставки, окружение наследуют все дети, и на ней gate.main() поднимает селективный набор до
# полного — smoke (12) краснел бы, пока снаружи идёт конверт доставки. Саму доставку судит
# tests/test_prod_gate.py.
os.environ["CC_PROD_DELIVERY"] = "0"

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


import orchestrator_daemon as OD

_good_out = json.dumps({"result": "готово", "is_error": False,
                         "modelUsage": {"claude-fable-5": {}}})

class _FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

CAP = {}
_real_od_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0


def cap_run(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return type("P", (), {"stdout": _good_out, "stderr": "", "returncode": 0})()


def cap_popen(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return _FakePopen(out=_good_out)


def with_flag(value, fn):
    """Запустить fn() с GATE_SINGLE_SELECTIVE=value, восстановить после."""
    saved = os.environ.get("GATE_SINGLE_SELECTIVE")
    os.environ["GATE_SINGLE_SELECTIVE"] = str(value)
    try:
        return fn()
    finally:
        if saved is None:
            os.environ.pop("GATE_SINGLE_SELECTIVE", None)
        else:
            os.environ["GATE_SINGLE_SELECTIVE"] = saved


OD.subprocess.run = cap_run
OD._POPEN = cap_popen


# ── (1–4) Дефолт (GATE_SINGLE_SELECTIVE=0/не задан) = текущее поведение ──────
print("(1–4) GATE_SINGLE_SELECTIVE=0/не задан → обратная совместимость:")

# (1) GATE_SINGLE_SELECTIVE=0 → одиночная задача → нет GATE_STEP_SELECTIVE
def _t1():
    OD.run_task(1, "обычная одиночная задача", task_timeout=60)
    return CAP["env"].get("GATE_STEP_SELECTIVE")

val = with_flag("0", _t1)
ok(val != "1", "флаг=0 → одиночная → нет GATE_STEP_SELECTIVE (полный гейт)")

# (2) GATE_SINGLE_SELECTIVE не задан → одиночная → нет GATE_STEP_SELECTIVE
saved = os.environ.pop("GATE_SINGLE_SELECTIVE", None)
OD.run_task(2, "одиночная без флага в env", task_timeout=60)
ok(CAP["env"].get("GATE_STEP_SELECTIVE") != "1",
   "флаг не задан → одиночная → нет GATE_STEP_SELECTIVE")
if saved is not None:
    os.environ["GATE_SINGLE_SELECTIVE"] = saved
else:
    os.environ["GATE_SINGLE_SELECTIVE"] = "0"   # вернуть изоляцию

# (3) мусорные значения → нет флага
for junk in ("yes", "true", "0", ""):
    def _tj(v=junk):
        OD.run_task(3, "задача мусор", task_timeout=60)
        return CAP["env"].get("GATE_STEP_SELECTIVE")
    val = with_flag(junk, _tj)
    ok(val != "1", f"GATE_SINGLE_SELECTIVE={junk!r} → нет GATE_STEP_SELECTIVE (строгое «1»)")

# (4) промежуточный шаг цепи при флаге=0 → GATE_STEP_SELECTIVE=1 (регресс: цепи не затронуты)
def _t4():
    OD.run_task(4, "[шаг 2/5 родитель 10] шаг при флаге=0", task_timeout=60)
    return CAP["env"].get("GATE_STEP_SELECTIVE")

val = with_flag("0", _t4)
ok(val == "1", "флаг=0, промежуточный шаг → GATE_STEP_SELECTIVE=1 (цепи не затронуты)")


# ── (5–9) GATE_SINGLE_SELECTIVE=1 ─────────────────────────────────────────────
print("\n(5–9) GATE_SINGLE_SELECTIVE=1:")


def _run(task_text, preamble=None, tid=99):
    def _inner():
        OD.run_task(tid, task_text, task_timeout=60, preamble=preamble)
        return CAP["env"].get("GATE_STEP_SELECTIVE")
    return with_flag("1", _inner)


# (5) одиночная задача → GATE_STEP_SELECTIVE=1
ok(_run("сделай рефактор gate.py") == "1",
   "флаг=1 → одиночная → GATE_STEP_SELECTIVE=1")

# (6) задача с тз: префиксом (типичный паттерн)
ok(_run("исправь баг в splinter.py") == "1",
   "флаг=1 → одиночная (исправь баг) → GATE_STEP_SELECTIVE=1")

# (7) промежуточный шаг цепи [шаг 2/5] → GATE_STEP_SELECTIVE=1 (независимо от флага)
ok(_run("[шаг 2/5 родитель 10] промежуточный шаг") == "1",
   "флаг=1 + промежуточный шаг → GATE_STEP_SELECTIVE=1 (цепной механизм не затронут)")

# (8) последний шаг цепи [шаг 5/5] → НЕТ GATE_STEP_SELECTIVE (полный гейт)
ok(_run("[шаг 5/5 родитель 10] последний шаг") != "1",
   "флаг=1 + последний шаг [5/5] → нет GATE_STEP_SELECTIVE (полный гейт)")

# (9) единственный шаг [шаг 1/1] → нет флага (он же последний)
ok(_run("[шаг 1/1 родитель 10] единственный") != "1",
   "флаг=1 + [шаг 1/1] (единственный/последний) → нет GATE_STEP_SELECTIVE")


# ── (10) планировщик: никогда не получает GATE_STEP_SELECTIVE ─────────────────
print("\n(10) планировщик + флаг=1 → нет GATE_STEP_SELECTIVE:")

_plan_out = json.dumps({"result": "1. шаг один\n2. шаг два", "is_error": False,
                         "modelUsage": {"claude-fable-5": {}}})


def cap_popen_plan(args, **kw):
    CAP.update({"args": list(args), "env": dict(kw.get("env") or {})})
    return _FakePopen(out=_plan_out)


OD._POPEN = cap_popen_plan
ok(_run("[шаг 2/5 родитель 10] планировщик", preamble=OD.PLANNER_PREAMBLE, tid=10) != "1",
   "планировщик + флаг=1 → нет GATE_STEP_SELECTIVE (планировщик всегда полный)")
OD._POPEN = cap_popen


# ── (11) GATE_ALERT_FINAL_ONLY=1 цел при флаге=1 (регресс) ───────────────────
print("\n(11) GATE_ALERT_FINAL_ONLY регресс при флаге=1:")


def _t11():
    OD.run_task(11, "одиночная регресс", task_timeout=60)
    return CAP["env"]

env11 = with_flag("1", _t11)
ok(env11.get("GATE_ALERT_FINAL_ONLY") == "1",
   "GATE_ALERT_FINAL_ONLY=1 цел (регресс: оба флага вместе у одиночной)")
ok(env11.get("GATE_STEP_SELECTIVE") == "1",
   "GATE_STEP_SELECTIVE=1 и GATE_ALERT_FINAL_ONLY=1 стоят вместе (одиночная + флаг)")


# ── (12) gate.py интеграция: GATE_STEP_SELECTIVE=1 → selective mode ────────────
# (gate.py сторона покрыта test_gate_selective; smoke-чек, что флаг достигает gate)
print("\n(12) gate.py smoke: GATE_STEP_SELECTIVE=1 (из одиночной) → selective branch:")
import gate

pushes_g, logs_g = [], []
gate._push = lambda text: pushes_g.append(text)
gate._log = lambda result, args_str: logs_g.append((result, args_str))

old_run_tests = gate.run_tests
old_run_selective = gate.run_selective_tests
old_changed = gate._changed_py_files
gate.run_tests = lambda: ([], 10, 0.1)
gate.run_selective_tests = lambda changed: ([], 3, 0.1, "селективный (3 тестов)")
gate._changed_py_files = lambda: []

old_argv = sys.argv
sys.argv = ["gate.py"]
os.environ["GATE_STEP_SELECTIVE"] = "1"
os.environ.pop("GATE_ALERT_FINAL_ONLY", None)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    code = gate.main()
sys.argv = old_argv
os.environ.pop("GATE_STEP_SELECTIVE", None)
out = buf.getvalue()

gate.run_tests = old_run_tests
gate.run_selective_tests = old_run_selective
gate._changed_py_files = old_changed

ok(code == 0 and "селективный" in out and "3" in out,
   "GATE_STEP_SELECTIVE=1 → gate.py идёт в selective branch (end-to-end)")

OD.subprocess.run = _real_od_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else 'ЕСТЬ FAIL (%d/%d)' % (sum(res), len(res))}")
sys.exit(0 if all(res) else 1)
