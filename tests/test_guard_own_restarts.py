"""Тест: guard не даёт красное на restart/start собственных сервисов (15.07.2026).

Два аспекта:
1. pretool_guard.py ДЕФЕРИТ non-python команды (systemctl → _is_python() = False → exit 0,
   пустой stdout). Guard работает только на python-командах, systemctl обходит его
   и идёт прямо к allow/ask rules — красная карточка НЕ выдаётся.

2. settings.json (или _restarts_new_settings.json, пока не применено из Termux) классифицирует
   собственные рестарты как allow:
     - systemctl restart/start splinter         → allow
     - systemctl restart/start orchestrator-daemon → allow
     - systemctl restart/start wa-webhook*      → allow
     - systemctl daemon-reload                  → allow (после применения _restarts_new_settings.json)
     - systemd-run deferred wa-webhook          → allow (после применения)
   А systemctl stop/sudo остаются ask.
"""
import json
import os
import re
import subprocess
import sys
from fnmatch import fnmatchcase

ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
PREPARED = os.path.join(ROOT, "_restarts_new_settings.json")
GUARD = os.path.join(ROOT, "pretool_guard.py")
PY = os.path.join(ROOT, "venv", "bin", "python3")

# Все новые паттерны (живые + будущие из prepared)
NEW_ALLOW = [
    "Bash(systemctl start splinter)",
    "Bash(systemctl start orchestrator-daemon)",
    "Bash(systemctl daemon-reload)",
    "Bash(systemd-run --on-active=* systemctl restart wa-webhook*)",
]

# Уже существующие в live settings (проверяем что не сломаны)
EXISTING_ALLOW_OWN = [
    "Bash(systemctl restart splinter)",
    "Bash(systemctl restart orchestrator-daemon)",
    "Bash(systemctl restart wa-webhook*)",
    "Bash(systemctl start wa-webhook*)",
    "Bash(systemd-run --on-active=* systemctl restart orchestrator-daemon)",
    "Bash(systemd-run --on-active=* systemctl restart splinter)",
]

# Конкретные команды → должны быть allow (в live или prepared)
OWN_RESTART_CMDS = [
    "systemctl restart splinter",
    "systemctl start splinter",
    "systemctl restart orchestrator-daemon",
    "systemctl start orchestrator-daemon",
    "systemctl restart wa-webhook",
    "systemctl restart wa-webhook.service",
    "systemctl start wa-webhook",
    "systemctl daemon-reload",
    "systemd-run --on-active=10s systemctl restart wa-webhook",
    "systemd-run --on-active=10s systemctl restart wa-webhook.service",
]

# Должны остаться ask (не открываем через новые паттерны)
STILL_ASK = [
    "systemctl stop splinter",
    "systemctl stop orchestrator-daemon",
    "systemctl stop wa-webhook",
    "sudo systemctl restart splinter",
    "sudo systemctl restart nginx",
]


def inner(rule):
    return rule[5:-1] if rule.startswith("Bash(") and rule.endswith(")") else None


def matches(cmd, rules):
    return [r for r in rules if inner(r) is not None and fnmatchcase(cmd, inner(r))]


def classify(cmd, perms):
    for zone in ("deny", "ask", "allow"):
        if matches(cmd, perms.get(zone, [])):
            return zone
    return "default"


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


live = json.load(open(SETTINGS))["permissions"]
prepared = json.load(open(PREPARED))["permissions"]
new_applied = all(p in live["allow"] for p in NEW_ALLOW)
perms = live if new_applied else prepared

if new_applied:
    print("Все новые паттерны ПРИМЕНЕНЫ в live settings.json")
else:
    missing = [p for p in NEW_ALLOW if p not in live["allow"]]
    print(f"WARN: {len(missing)} новых паттернов ещё НЕ в live settings.json — "
          "применить из Termux:\n  cp _restarts_new_settings.json .claude/settings.json\n"
          "  (+ рестарт сессии claude)\n"
          f"Отсутствуют: {missing}\nПроверяю подготовленный файл.")

res = []

print("\n1. Guard ДЕФИРУЕТ системные команды (не python → red-карточка НЕ выдаётся):")
# Проверяем что pretool_guard._is_python() возвращает False для systemctl
# Делаем это через subprocess с PRETOOL_NOPUSH=1 и JSON-вводом
env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
for cmd in ["systemctl restart splinter", "systemctl daemon-reload",
            "systemctl start orchestrator-daemon"]:
    inp = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    p = subprocess.run([PY, GUARD], input=inp, capture_output=True, text=True, env=env)
    # Defer = exit 0, пустой stdout (не JSON-решение ask)
    is_defer = p.returncode == 0 and p.stdout.strip() == ""
    res.append(ok(is_defer, f"guard деферит '{cmd}' (exit={p.returncode}, stdout='{p.stdout.strip()[:50]}')"))

print("\n2. Существующие own-рестарты в live settings.json (не сломаны):")
for rule in EXISTING_ALLOW_OWN:
    res.append(ok(rule in live["allow"], f"live allow содержит {rule}"))

print("\n3. Все own-команды → allow (live или prepared):")
for cmd in OWN_RESTART_CMDS:
    z = classify(cmd, perms)
    res.append(ok(z == "allow", f"'{cmd}' → allow (классифицировано как '{z}')"))

print("\n4. systemctl stop/sudo — остаются ask (не открыты новыми паттернами):")
for cmd in STILL_ASK:
    z_live = classify(cmd, live)
    z_prep = classify(cmd, prepared)
    res.append(ok(z_live == "ask" and z_prep == "ask",
                  f"'{cmd}' → ask (live={z_live}, prepared={z_prep})"))

print("\n5. Новые паттерны в prepared файле на месте:")
for rule in NEW_ALLOW:
    res.append(ok(rule in prepared["allow"], f"prepared allow содержит {rule}"))

print("\n6. Prepared байт-в-байт = live + новые паттерны (ничего лишнего не добавлено):")
extra_allow = [r for r in prepared["allow"] if r not in live["allow"] and r not in NEW_ALLOW]
res.append(ok(not extra_allow, f"лишних allow в prepared: {extra_allow}"))
res.append(ok(prepared["ask"] == live["ask"], "prepared ask идентичен live"))
res.append(ok(prepared["deny"] == live["deny"], "prepared deny идентичен live"))

print(f"\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
