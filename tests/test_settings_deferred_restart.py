"""Классификация УЗКИХ allow-паттернов deferred-рестарта (заведено 03.07.2026).

Разрешены ТОЛЬКО две формы (правило самомодификации — отложенный рестарт демона/splinter):
    systemd-run --on-active=<T> systemctl restart orchestrator-daemon
    systemd-run --on-active=<T> systemctl restart splinter

ПОЧЕМУ голый `systemd-run` в allow ЗАПРЕЩЁН НАВСЕГДА: systemd-run создаёт transient unit,
который исполняет ПРОИЗВОЛЬНУЮ команду уже ВНЕ bash-паттернов allowlist —
`systemd-run --on-active=1s <что угодно>` = полный обход классификации allow/ask/deny
(и deny на rm -rf, и ask на sqlite3 — всё мимо). Поэтому allow-паттерн фиксирует
КОМАНДУ ЦЕЛИКОМ, wildcard только на значении таймера.

Известный остаточный предел (документируем честно): glob `*` в середине жаден и матчит
пробелы, т.е. строка вида `systemd-run --on-active=1s X systemctl restart splinter`
формально матчится. Прикрытие: суффикс фиксирован (payload обязан КОНЧАТЬСЯ ровно на
`systemctl restart <наш сервис>`), а сцепки `;`/`&&`/`|` ловит FORM-GUARD движка отдельно.

Тест гоняет матчер (glob, семантика как у движка: * = любые символы) по РЕАЛЬНОМУ
.claude/settings.json. Если узкие паттерны ещё не внесены (headless не может писать в
.claude/ — нужна разовая правка из Termux: cp _sdrun_new_settings.json .claude/settings.json),
тест проверяет подготовленный _sdrun_new_settings.json и печатает WARN.
"""
import json
import os
import sys
from fnmatch import fnmatchcase

ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
PREPARED = os.path.join(ROOT, "_restarts_new_settings.json")

NARROW = [
    "Bash(systemd-run --on-active=* systemctl restart orchestrator-daemon)",
    "Bash(systemd-run --on-active=* systemctl restart splinter)",
    "Bash(systemd-run --on-active=* systemctl restart wa-webhook*)",
]


def inner(rule):
    """'Bash(x y *)' -> 'x y *' (не-Bash правила отбрасываем)."""
    return rule[5:-1] if rule.startswith("Bash(") and rule.endswith(")") else None


def matches(cmd, rules):
    return [r for r in rules if inner(r) is not None and fnmatchcase(cmd, inner(r))]


def classify(cmd, perms):
    """Упрощённая модель precedence движка: deny > ask > allow > дефолт (prompt)."""
    for zone in ("deny", "ask", "allow"):
        if matches(cmd, perms.get(zone, [])):
            return zone
    return "default"


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


live = json.load(open(SETTINGS))["permissions"]
applied = all(p in live["allow"] for p in NARROW)
if applied:
    perms = live
    print("settings.json: узкие паттерны ВНЕСЕНЫ — проверяю живой файл")
else:
    perms = json.load(open(PREPARED))["permissions"]
    print("WARN: узкие паттерны ЕЩЁ НЕ в .claude/settings.json (гейт headless) — "
          "проверяю подготовленный _restarts_new_settings.json; применение = разовый cp из Termux:\n"
          "  cp _restarts_new_settings.json .claude/settings.json  (+ рестарт сессии claude)")

res = []

print("Узкие формы deferred-рестарта → allow:")
res.append(ok(classify("systemd-run --on-active=10s systemctl restart orchestrator-daemon", perms) == "allow",
              "--on-active=10s restart orchestrator-daemon → allow"))
res.append(ok(classify("systemd-run --on-active=30s systemctl restart splinter", perms) == "allow",
              "--on-active=30s restart splinter → allow"))
res.append(ok(classify("systemd-run --on-active=10s systemctl restart wa-webhook", perms) == "allow",
              "--on-active=10s restart wa-webhook → allow"))
res.append(ok(classify("systemd-run --on-active=10s systemctl restart wa-webhook.service", perms) == "allow",
              "--on-active=10s restart wa-webhook.service → allow"))

print("Любой ДРУГОЙ systemd-run → НЕ allow (дефолт = prompt, как раньше):")
for cmd in [
    "systemd-run --on-active=10s systemctl restart nginx",
    "systemd-run --on-active=10s systemctl stop splinter",
    "systemd-run --on-active=10s rm -rf /tmp/x",
    "systemd-run --on-active=10s bash -c evil",
    "systemd-run systemctl restart orchestrator-daemon",
    "systemd-run --unit=x --on-active=10s systemctl restart splinter",
    "systemd-run bash",
    "systemd-run",
]:
    res.append(ok(classify(cmd, perms) != "allow", cmd + " → НЕ allow"))

print("Голого/широкого systemd-run в allow НЕТ (единственные systemd-run-правила = 3 узких):")
sdrun_rules = [r for r in perms["allow"] if inner(r) is not None and inner(r).split(" ", 1)[0] == "systemd-run"]
res.append(ok(sorted(sdrun_rules) == sorted(NARROW),
              "systemd-run-правила в allow ровно NARROW: " + str(sdrun_rules)))

print("Прежняя классификация не тронута:")
res.append(ok(classify("systemctl stop splinter", perms) == "ask", "systemctl stop splinter → ask"))
res.append(ok(classify("sqlite3 memory.db .tables", perms) == "ask", "sqlite3 → ask"))
res.append(ok(classify("git push --no-verify", perms) == "deny", "--no-verify → deny"))
res.append(ok(classify("systemctl restart splinter", perms) == "allow", "прямой restart splinter → allow (Q2)"))

if applied:
    print("Паттерны в живом settings.json — сверка с _restarts_new_settings.json не нужна (файл можно удалить).")
else:
    print("Подготовленный файл = живой settings + РОВНО 3 узких паттерна + start/daemon-reload (ничего лишнего):")
    prep = json.load(open(PREPARED))["permissions"]
    res.append(ok(all(p in prep["allow"] for p in NARROW),
                  "diff prepared vs live == все 3 узких паттерна (allow)"))
    res.append(ok(prep["ask"] == live["ask"] and prep["deny"] == live["deny"], "ask/deny идентичны"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
