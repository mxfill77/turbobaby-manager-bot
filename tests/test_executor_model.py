"""Ускорение цепей ч.1 (13.07.2026): модель ИСПОЛНИТЕЛЯ headless-задач — флаг EXECUTOR_MODEL (.env).
Дефолт (нет/пусто) = ORCH_MODEL байт-в-байт (поведение до правки); флаг подхватывается реимпортом;
короткие алиасы нормализуются в полные model id (класс 404, урок ПК b18ad08); думанье
(планировщик декомпозиции / думатель самопочинки-адаптации-куратора) остаётся на ORCH_MODEL.
Всё мокнуто (subprocess.run), сети/claude нет."""
import os, sys, json, importlib
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (принудительно — env демона с боевыми флагами)
# старт с ПУСТОЙ EXECUTOR_MODEL = дефолт-ветка; load_dotenv(override=False) её не перебьёт
os.environ["EXECUTOR_MODEL"] = ""

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD

# (1) дефолт байт-в-байт: переменной нет/пустая → EXECUTOR_MODEL == ORCH_MODEL (поведение до правки)
print("(1) дефолт байт-в-байт:")
res.append(ok(OD.EXECUTOR_MODEL == OD.ORCH_MODEL, "EXECUTOR_MODEL по умолчанию == ORCH_MODEL"))

class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc

class _MinFakeBC:
    def task_heartbeat(s, tid): return {"ok": True}

_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
CAP = {}
def fake_run(args, **kw):
    CAP["args"] = list(args); CAP["kw"] = kw
    return FakeProc(fake_run.out, fake_run.rc)
fake_run.out = json.dumps({"result": "готово", "is_error": False,
                           "modelUsage": {"claude-fable-5": {"inputTokens": 1}}})
fake_run.rc = 0
def fake_popen(args, **kw):
    CAP["args"] = list(args); CAP["kw"] = kw
    return FakePopen(fake_run.out, fake_run.rc)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen
OD.bc = _MinFakeBC()

def argv_model(a):
    return a[a.index("--model") + 1] if "--model" in a else None

# (2) argv исполнителя на дефолте: --model == ORCH_MODEL дословно (как до правки)
print("(2) argv исполнителя на дефолте:")
st, r = OD.run_task(1, "проверь X", task_timeout=600)
res.append(ok(st == "done" and argv_model(CAP["args"]) == OD.ORCH_MODEL,
              "--model = ORCH_MODEL при пустом флаге (байт-в-байт)"))

# (3) нормализация алиасов (класс 404 b18ad08): полные id как есть, алиасы → полные, [1m] цел
print("(3) нормализация алиасов:")
res.append(ok(OD._normalize_model("claude-sonnet-4-6") == "claude-sonnet-4-6", "полный id — как есть"))
res.append(ok(OD._normalize_model("sonnet-4-6") == "claude-sonnet-4-6", "sonnet-4-6 → claude-sonnet-4-6"))
res.append(ok(OD._normalize_model(" sonnet ") == "claude-sonnet-4-6", "голый sonnet (+пробелы) → полный id"))
res.append(ok(OD._normalize_model("opus-4-8[1m]") == "claude-opus-4-8[1m]", "суффикс [1m] сохраняется"))
res.append(ok(OD._normalize_model("fable") == "claude-fable-5", "fable → claude-fable-5"))
res.append(ok(OD._normalize_model("haiku") == "claude-haiku-4-5-20251001", "haiku → полный id с датой"))
res.append(ok(OD._normalize_model("my-custom-model") == "my-custom-model",
              "незнакомое значение не трогаем (фолбэк-кондуктор подстрахует)"))

# (4) флаг подхватывается: EXECUTOR_MODEL=sonnet-4-6 в env → реимпорт → исполнитель на полном id
print("(4) флаг подхватывается (реимпорт с EXECUTOR_MODEL=sonnet-4-6):")
os.environ["EXECUTOR_MODEL"] = "sonnet-4-6"
importlib.reload(OD)  # patch subprocess.run живёт на общем модуле subprocess — переживает reload
OD._POPEN = fake_popen   # _POPEN сбрасывается reload'ом — восстанавливаем
OD.bc = _MinFakeBC()     # bc сбрасывается reload'ом — восстанавливаем
res.append(ok(OD.EXECUTOR_MODEL == "claude-sonnet-4-6",
              "флаг из env подхвачен + алиас нормализован в полный id"))
# NB: литерал ниже ЗЕРКАЛИТ боевой .env (ORCH_MODEL); при смене модели правится вместе с конфигом.
res.append(ok(OD.ORCH_MODEL == "claude-opus-5", "ORCH_MODEL (думатель/планировщик) флагом НЕ тронут"))
st4, r4 = OD.run_task(4, "поправь Y", task_timeout=600)
a4 = CAP["args"]
res.append(ok(argv_model(a4) == "claude-sonnet-4-6", "argv исполнителя: --model = claude-sonnet-4-6"))
res.append(ok("--fallback-model" in a4 and a4[a4.index("--fallback-model") + 1] == OD.ORCH_MODEL_FALLBACK,
              "фолбэк-кондуктор исполнителя цел (ORCH_MODEL_FALLBACK)"))
res.append(ok(st4 == "done" and r4 == "готово", "результат парсится как раньше"))

# (5) планировщик декомпозиции = ДУМАНЬЕ → ORCH_MODEL, даже при включённом EXECUTOR_MODEL
print("(5) планировщик остаётся на ORCH_MODEL:")
fake_run.out = json.dumps({"result": "1. шаг\n2. шаг", "is_error": False,
                           "modelUsage": {"claude-fable-5": {}}})
st5, r5 = OD.run_task(5, "родитель: крупное ТЗ", task_timeout=600, preamble=OD.PLANNER_PREAMBLE)
res.append(ok(argv_model(CAP["args"]) == OD.ORCH_MODEL,
              "preamble планировщика → --model = ORCH_MODEL (план не ускоряем)"))

# (6) думатель (самопочинка/адаптация/куратор) → ORCH_MODEL, флаг его не трогает
print("(6) думатель остаётся на ORCH_MODEL:")
fake_run.out = json.dumps({"result": "{\"verdict\": \"retry\"}", "is_error": False,
                           "modelUsage": {"claude-fable-5": {}}})
out6 = OD._thinker_exec("вопрос", 60, "тест")
res.append(ok(argv_model(CAP["args"]) == OD.ORCH_MODEL, "думатель: --model = ORCH_MODEL"))
res.append(ok(out6 is not None, "думатель отработал (мок жив)"))

# (7) NEEDS_APPROVAL-гейт исполнителя жив и на sonnet-модели (красное не ослаблено)
print("(7) красный гейт цел на исполнителе:")
fake_run.out = json.dumps({"result": "NEEDS_APPROVAL: op=other | запись в Лист1 · Байки · смотреть diff",
                           "is_error": False, "modelUsage": {"claude-sonnet-4-6": {}}})
st7, r7 = OD.run_task(7, "v", task_timeout=600)
res.append(ok(st7 == "needs_approval" and r7.startswith("op=other"),
              "маркер в выводе sonnet-исполнителя → needs_approval как раньше"))

OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
