"""Нюанс bd5d516 (фикс 12.07.2026): слово-интерпретатор ВНУТРИ текста git commit -m больше не
даёт ambiguous-карточку.

Было: `git commit -m "фикс python скрипта"` → «python» в тексте ловился сканом _is_python →
git шёл в _analyze → ветка -m видела «не-зелёный модуль» → ложный конверт «не распознал операцию».
Фикс: для СКАНА интерпретатора payload'ы -m/-am/--message git-команды вырезаются (_strip_git_msg);
классификация самого git не меняется (git → не-python → defer к штатным allow/ask rules).
Настоящие python-команды: red/green как раньше; ambiguous с в3 (23.07.2026) — defer БЕЗ конверта
(сам по себе не красный, решают слои settings). Пуши замучены PRETOOL_NOPUSH.
"""
import os, sys, json, shutil, tempfile, subprocess

ROOT = "/root/turbobaby-manager-bot"
PY = os.path.join(ROOT, "venv", "bin", "python3")
PRETOOL = os.path.join(ROOT, "pretool_guard.py")

TMP = tempfile.mkdtemp(prefix="pt_cm_")


def run(cmd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                          "cwd": ROOT, "session_id": "s-commitmsg"})
    env = dict(os.environ)
    env["PRETOOL_NOPUSH"] = "1"
    env["PRETOOL_DEDUP_DIR"] = os.path.join(TMP, "dedup")
    env.pop("NOTIFY_COUNT_FILE", None)
    return subprocess.run([PY, PRETOOL], input=payload, capture_output=True, text=True,
                          timeout=60, env=env)


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


res = []

print("(1) слово-интерпретатор в тексте git commit -m → БЕЗ карточки (defer):")
for cmd in [
    'git commit -m "фикс python скрипта"',                       # корень нюанса bd5d516
    'git commit -m "фикс python-скрипта"',                        # формулировка ТЗ
    'git commit -am "прогнал venv/bin/python3 gate.py — зелёный"',
    'git commit --message "python3 больше не нужен тут"',
    'git commit --message="рефактор python обвязки"',
    'git commit -m"фикс python скрипта приклеенным -m"',
    'git -C /root/turbobaby-bridge-gs commit -m "python правка"',  # git с -C до commit
    'git commit -m "часть 1 python" -m "часть 2 python3"',         # несколько -m
]:
    r = run(cmd)
    res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout, cmd[:74] + " → defer"))

print("(2) настоящие python-команды — классификация КАК РАНЬШЕ:")
red = os.path.join(TMP, "fx_red_live.py")
# ЖИВОЙ вызов Bridge с ОБЪЕКТОМ и ЧИСЛОМ: с 28.07.2026 красная карточка без них не собирается
# вовсе (минимум карточки, tests/test_guard_card_min.py) — безобъектная фикстура давала card_skipped,
# и «red-конверт» проверялся на несуществующей карточке. Литерал операции — конкатенацией
# (иначе гард краснеет на самом файле теста).
FLEET_OIL = "set_fleet_" + "oil"
with open(red, "w", encoding="utf-8") as f:
    f.write("# фикстура регресса\nbridge." + FLEET_OIL + "(number='6789', oil_km=27000)\n")
r = run(PY + " " + red)
res.append(ok('"ask"' in r.stdout and "Лист1" in r.stdout, "python с red-токеном → red-конверт"))
missing = os.path.join(TMP, "fx_absent.py")
r = run(PY + " " + missing)
res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout,
              "нечитаемый .py → defer (в3: ambiguous сам по себе не красный)"))
r = run("PRETOOL_NOPUSH=1 " + PY + " --version")
res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout, "инфо-флаг → зелёное (регресс 163)"))
r = run(PY + " " + os.path.join(ROOT, "tests", "test_fmt.py"))
res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout, "tests/* → зелёное (регресс 02.07)"))

print("(3) интерпретатор ВНЕ -m в git-команде по-прежнему сканится (страж не ослаблен):")
r = run(f'git commit -m "правка" && {PY} {red}')
res.append(ok('"ask"' in r.stdout, "компаунд git…&&python red-скрипт → конверт остался"))
r = run(f'git commit -m "правка" && {PY} {missing}')
res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout,
              "компаунд git…&&python нечитаемый → defer (в3, red в компаунде ловится — выше)"))

print("(4) _strip_git_msg: границы и fail-safe:")
sys.path.insert(0, ROOT)
import pretool_guard as PG
res.append(ok(PG._strip_git_msg(PY + " tests/test_fmt.py") == PY + " tests/test_fmt.py",
              "не-git команда возвращается КАК ЕСТЬ"))
res.append(ok("python" not in PG._strip_git_msg('git commit -m "фикс python скрипта"'),
              "payload -m вырезан из скан-представления"))
res.append(ok("python" not in PG._strip_git_msg('VAR=1 git commit -m "python внутри"'),
              "env-префикс перед git учтён"))
broken = 'git commit -m "незакрытая кавычка'
res.append(ok(PG._strip_git_msg(broken) == broken, "кривое квотирование → команда как есть (fail-safe)"))
kept = PG._strip_git_msg(f'git commit -m "msg" && {PY} x.py')
res.append(ok("python3" in kept, "интерпретатор вне -m в скан-представлении СОХРАНЁН"))

print("(5) RED_TOKEN в тексте git commit -m компаунд-команды → НЕ red (класс 23.07.2026):")
# false-red #281: `python gate.py && git commit -m "fixed set_fleet_oil"` → step-1 ловил
# «set_fleet_oil» в сыром cmd, хотя python сам его не читает — только commit-сообщение.
# Фикс: _units (per-segment _strip_git_msg) убирает -m payload'ы из компаундов перед step-1 сканом.
for compound in [
    f'{PY} gate.py && git commit -m "fixed set_fleet_oil"',
    f'{PY} gate.py && git commit -m "add confirmed=true validation"',
    f'{PY} gate.py && git commit -m "fix DOWRITE pattern"',
    f'{PY} gate.py && git commit -am "remove add_transaction stub"',
    f'{PY} gate.py && git commit --message "refactor delete_event guard"',
]:
    r = run(compound)
    label = compound.split("&&")[1].strip()[:70]
    res.append(ok(r.returncode == 0 and '"ask"' not in r.stdout,
                  f"компаунд python+git -m RED_TOKEN → defer (не red): {label}"))

shutil.rmtree(TMP, ignore_errors=True)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
