"""Кондуктор модели VPS-оркестратора (06.07.2026, догнан 25.07.2026): headless-исполнитель на
ORCH_MODEL с авто-фолбэком на ORCH_MODEL_FALLBACK силами CLI (--fallback-model), модель из env,
не хардкод, --output-format json → достаём текст (result) и какая модель реально отработала
(modelUsage). Всё мокнуто (subprocess.run), сети/claude нет.

СОСТОЯНИЕ НАСТРОЕК на 25.07.2026: основная claude-opus-5, запасная claude-fable-5. Прежняя
редакция описывала обратную раскладку (основная Fable 5, запасная Opus 4.8 1M) — она устарела
06→25.07 и вводила в заблуждение. Моки modelUsage ниже НЕ хардкодят имена: они берут
OD.ORCH_MODEL / OD.ORCH_MODEL_FALLBACK, поэтому смена модели в .env их больше не красит."""
import os, sys, json
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
# изоляция от боевого .env (ускорение цепей ч.1): пустая строка = дефолт EXECUTOR_MODEL=ORCH_MODEL,
# load_dotenv(override=False) существующее значение не перебьёт — тест доказывает дефолт байт-в-байт
os.environ["EXECUTOR_MODEL"] = ""

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD

# (1) модель вынесена в env: основная claude-opus-5 → фолбэк claude-fable-5 (состояние 25.07.2026)
print("(1) конфиг модели из env:")
# NB: два литерала ниже ЗЕРКАЛЯТ боевой .env (ORCH_MODEL / ORCH_MODEL_FALLBACK); при смене
# модели правятся вместе с конфигом — иначе гейт краснеет и отгрузка встаёт ВСЕМУ репозиторию.
# Так и вышло 24→25.07.2026: правку .env не догнали гейтом в том же заходе, push стоял 13 часов.
# Поэтому ниже к литералу добавлена проверка СВОЙСТВА (полный идентификатор ≠ короткий алиас):
# она переживает смену модели, а литерал остаётся якорем «конфиг и тест сверены глазами».
res.append(ok(OD.ORCH_MODEL == "claude-opus-5", "ORCH_MODEL из .env = claude-opus-5"))
# ЗЕРКАЛО .env: 25.07.2026 фолбэк переведён с алиаса «fable» на полный идентификатор —
# короткий алиас API не принимает (404 not_found_error), CLI-фолбэк был мёртв.
res.append(ok(OD.ORCH_MODEL_FALLBACK == "claude-fable-5",
              "ORCH_MODEL_FALLBACK = claude-fable-5"))
res.append(ok(OD.ORCH_MODEL_FALLBACK.startswith("claude-"),
              "фолбэк — ПОЛНЫЙ идентификатор модели (короткий алиас даёт 404)"))
res.append(ok(OD.ORCH_MODEL != OD.ORCH_MODEL_FALLBACK, "основная и фолбэк — разные модели"))

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
fake_run.out = ""; fake_run.rc = 0
def fake_popen(args, **kw):
    CAP["args"] = list(args); CAP["kw"] = kw
    return FakePopen(fake_run.out, fake_run.rc)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen
OD.bc = _MinFakeBC()

# (2) кондуктор в argv: --model основная + --fallback-model прежняя + json, prompt последним
print("(2) argv кондуктора:")
fake_run.out = json.dumps({"result": "готово", "is_error": False,
                           "modelUsage": {OD.ORCH_MODEL: {"inputTokens": 1}}})
st, r = OD.run_task(1, "проверь X", task_timeout=600)
a = CAP["args"]
res.append(ok(a[0] == OD.CLAUDE_BIN and a[1] == "-p", "вызов claude -p"))
res.append(ok("--model" in a and a[a.index("--model") + 1] == OD.ORCH_MODEL,
              "--model = ORCH_MODEL (claude-opus-5)"))
res.append(ok("--fallback-model" in a and a[a.index("--fallback-model") + 1] == OD.ORCH_MODEL_FALLBACK,
              "--fallback-model = ORCH_MODEL_FALLBACK (кондуктор, не хардкод)"))
res.append(ok("--output-format" in a and a[a.index("--output-format") + 1] == "json",
              "--output-format json (для парса модели/текста)"))
res.append(ok(a[-1].endswith("проверь X"), "prompt — последним позиционным аргументом"))

# (3) из json достаём result (текст), а не сырой json
print("(3) парс json result:")
res.append(ok(st == "done" and r == "готово", "result из json → чистый текст ответа"))

# (4) фолбэк реально отработал (основная недоступна → CLI взял запасную): задача НЕ упала
print("(4) фолбэк подхватил, задача жива:")
fake_run.out = json.dumps({"result": "сделано на фолбэке", "is_error": False,
                           "modelUsage": {OD.ORCH_MODEL_FALLBACK: {"inputTokens": 1}}})
fake_run.rc = 0
st4, r4 = OD.run_task(4, "поправь Y")
res.append(ok(st4 == "done" and r4 == "сделано на фолбэке",
              "modelUsage=фолбэк (основная недоступна) → done, задача НЕ упала"))
# Страховка ветки: если фолбэк совпадёт с основной, мок перестанет её задевать и проверка
# выше станет пустой — ловим это здесь, а не через полгода на живом отказе модели.
res.append(ok(OD.ORCH_MODEL not in json.loads(fake_run.out)["modelUsage"],
              "мок фолбэка не содержит основную модель → ветка «отработал фолбэк» задета"))

# (5) обе модели недоступны (invalid/лимит) → exit 1, is_error, modelUsage пуст → failed (не крэш)
print("(5) обе недоступны → аккуратный failed:")
fake_run.out = json.dumps({"result": "There's an issue with the selected model", "is_error": True,
                           "api_error_status": 404, "modelUsage": {}})
fake_run.rc = 1
st5, r5 = OD.run_task(5, "z")
res.append(ok(st5 == "failed" and "model" in r5.lower(), "обе модели down → failed с внятной причиной"))

# (6) деградация: не-json stdout (текст-режим/старый мок) → сырой текст, не крэш парсера
print("(6) не-json вывод — деградация:")
fake_run.out = "просто текст без json"; fake_run.rc = 0
st6, r6 = OD.run_task(6, "w")
res.append(ok(st6 == "done" and r6 == "просто текст без json", "не-json → сырой stdout (обратная совместимость)"))

# (7) NEEDS_APPROVAL детект работает на извлечённом из json result
print("(7) красная зона через json.result:")
fake_run.out = json.dumps({"result": "анализ\nNEEDS_APPROVAL: op=other | запись в Лист1 · Байки · смотреть diff",
                           "is_error": False, "modelUsage": {OD.ORCH_MODEL: {}}})
fake_run.rc = 0
st7, r7 = OD.run_task(7, "v")
res.append(ok(st7 == "needs_approval" and r7.startswith("op=other"),
              "маркер внутри json.result → needs_approval (гейт красной зоны жив)"))

OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
