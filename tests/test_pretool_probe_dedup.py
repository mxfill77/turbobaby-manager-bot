"""UX-фикс стража красной зоны headless (08.07.2026, спам-инцидент задачи 163: 4 одинаковых
конверта «не распознал операцию» за 13:24–13:28).

Три слоя фикса:
(1) ambiguous-карточка НЕСЁТ саму команду в теле (строка «Команда: …», первые ~200 симв.) —
    владелец решает из уведомления, а не «глянь выше вручную» (в headless «выше» некуда);
(2) ДЕДУП: одинаковая нераспознанная команда в рамках одной сессии(=задачи) = ОДНА карточка,
    повторы копятся счётчиком «Повтор: ×N» правкой ТОЙ ЖЕ карточки (edit), не новыми сообщениями;
(3) классификатор знает читающие probe-паттерны репо: env-префикс + инфо-флаг → зелёное
    (корень инцидента 163: `PRETOOL_NOPUSH=1 venv/bin/python3 --version` падал в ambiguous),
    env-префикс + tests/* → зелёное; node --check / node tests/*harness* / cat / grep / diff —
    не-python → defer ещё до анализа (probe «может писать» не считается).
Ask-философия НЕ ослаблена: настоящая неопределённость (stdin, нечитаемый .py, неизвестный -m,
red-токены) — по-прежнему конверт. Пуши в тесте — только мок-счётчик NOTIFY_COUNT_FILE (сети нет).
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

ROOT = "/root/turbobaby-manager-bot"
PY = os.path.join(ROOT, "venv", "bin", "python3")
PRETOOL = os.path.join(ROOT, "pretool_guard.py")

TMP = tempfile.mkdtemp(prefix="pt_pd_")
DEDUP = os.path.join(TMP, "dedup")


def run(cmd, session="s-default", count_file=None, nopush=True):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                          "cwd": ROOT, "session_id": session})
    env = dict(os.environ)
    env["PRETOOL_DEDUP_DIR"] = DEDUP
    env.pop("PRETOOL_NOPUSH", None)
    env.pop("NOTIFY_COUNT_FILE", None)
    if nopush:
        env["PRETOOL_NOPUSH"] = "1"
    if count_file:
        env["NOTIFY_COUNT_FILE"] = count_file   # мок-счётчик: попытка пуша = строка, сети НЕТ
    return subprocess.run([PY, PRETOOL], input=payload, capture_output=True, text=True,
                          timeout=60, env=env)


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


def lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [ln for ln in f.read().splitlines() if ln.strip()]
    except Exception:
        return []


res = []

print("(1) probe-паттерны репо → БЕЗ конверта (green/defer, ask нет):")
for cmd in [
    "PRETOOL_NOPUSH=1 " + PY + " --version",              # корень инцидента 163
    "PRETOOL_NOPUSH=1 venv/bin/python3 -V",
    "PRETOOL_NOPUSH=1 " + PY + " " + os.path.join(ROOT, "tests", "test_fmt.py"),
    "PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_fmt.py",
    PY + " --version",                                     # регресс без префикса
    "node --check tests/booking_gs_harness.js",
    "node tests/booking_gs_harness.js",
    "cat " + os.path.join(ROOT, "splinter.log"),
    "grep -n def " + os.path.join(ROOT, "bot.py"),
    "diff " + os.path.join(ROOT, "gate.py") + " " + os.path.join(ROOT, "gate.py"),
]:
    r = run(cmd, session="s-probe")
    res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout, cmd[:80] + " → без конверта"))

print("(2) неизвестный скрипт с записью → конверт С КОМАНДОЙ в теле:")
missing = os.path.join(TMP, "fx_writer_probe.py")   # нет на диске → нечитаем → ambiguous
cmd_m = PY + " " + missing
r = run(cmd_m, session="s-card")
res.append(ok(r.returncode == 0 and '"ask"' in r.stdout, "нечитаемый скрипт → ask (конверт)"))
res.append(ok("Команда:" in r.stdout and missing in r.stdout, "команда включена в тело карточки"))
res.append(ok("глянь команду выше" not in r.stdout, "«глянь выше вручную» из карточки убран"))
r = run(PY + " -", session="s-card")
res.append(ok('"ask"' in r.stdout and "Команда:" in r.stdout, "stdin '-' → конверт с командой в теле"))
long_cmd = PY + " -m unknown_mod_" + "x" * 300
r = run(long_cmd, session="s-card")
res.append(ok('"ask"' in r.stdout and "…" in r.stdout, "длинная команда обрезана ~200 симв. (…)"))

print("(3) ДЕДУП: повтор той же команды = счётчик ×N, не новое сообщение:")
cnt = os.path.join(TMP, "cnt_dedup.txt")
r1 = run(cmd_m, session="s-dedup", count_file=cnt, nopush=False)
res.append(ok('"ask"' in r1.stdout and "Повтор:" not in r1.stdout, "1-й раз: карточка без счётчика"))
res.append(ok(len(lines(cnt)) == 1 and not lines(cnt)[0].startswith("EDIT "),
              "1-й раз: ровно ОДНА отправка (новое сообщение)"))
r2 = run(cmd_m, session="s-dedup", count_file=cnt, nopush=False)
res.append(ok('"ask"' in r2.stdout and "×2" in r2.stdout, "2-й раз: ask остался, счётчик ×2 в карточке"))
r3 = run(cmd_m, session="s-dedup", count_file=cnt, nopush=False)
res.append(ok("×3" in r3.stdout, "3-й раз: счётчик ×3"))
tail = lines(cnt)[1:]
res.append(ok(len(tail) == 2 and all(t.startswith("EDIT ") for t in tail),
              "повторы = ПРАВКА той же карточки (EDIT), новых сообщений НОЛЬ"))
res.append(ok(any("×3" in t for t in tail), "счётчик ×3 дошёл до правки карточки"))

print("(4) границы дедупа:")
r = run(cmd_m, session="s-other", count_file=os.path.join(TMP, "cnt_o.txt"), nopush=False)
res.append(ok("Повтор:" not in r.stdout, "другая сессия → свой счёт (карточка без ×N)"))
r = run(PY + " " + os.path.join(TMP, "fx_writer_probe2.py"), session="s-dedup")
res.append(ok('"ask"' in r.stdout and "Повтор:" not in r.stdout, "другая команда в той же сессии → без ×N"))
cnt_red = os.path.join(TMP, "cnt_red.txt")
red = os.path.join(TMP, "fx_red_live.py")
with open(red, "w", encoding="utf-8") as f:
    f.write("# фикстура регресса\nprint('set_fleet_oil')\n")
for _ in range(2):
    r = run(PY + " " + red, session="s-red", count_file=cnt_red, nopush=False)
res.append(ok('"ask"' in r.stdout and "Повтор:" not in r.stdout and len(lines(cnt_red)) == 2,
              "red НЕ дедупится (конкретная операция: каждая карточка пушится, как раньше)"))

print("(5) fail-safe и ask-философия целы:")
env_bad = run(cmd_m, session="s-fs")
# сломанный стор: PRETOOL_DEDUP_DIR указывает в файл → makedirs падает → (1, None), ask стоит
payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd_m},
                      "cwd": ROOT, "session_id": "s-fs2"})
env = dict(os.environ, PRETOOL_NOPUSH="1", PRETOOL_DEDUP_DIR=os.path.join(red, "x"))
rb = subprocess.run([PY, PRETOOL], input=payload, capture_output=True, text=True, timeout=60, env=env)
res.append(ok('"ask"' in env_bad.stdout and '"ask"' in rb.stdout,
              "сломанный дедуп-стор → ask как раньше (fail-safe)"))
for cmd in [PY + " -", PY + " -m some_unknown_module",
            "PRETOOL_NOPUSH=1 " + PY + " --version --frobnicate"]:
    r = run(cmd, session="s-ask")
    res.append(ok('"ask"' in r.stdout, cmd[:70] + " → по-прежнему конверт (ask не ослаблен)"))

shutil.rmtree(TMP, ignore_errors=True)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
