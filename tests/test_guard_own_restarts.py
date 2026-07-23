"""Тест: guard не даёт красное на restart/start собственных сервисов (15.07.2026).

Два аспекта:
1. ПЕРЕСМОТРЕНО 23.07.2026 (чёрный список процессов): guard больше НЕ деферит systemctl вслепую —
   он смотрит на ГЛАГОЛ и ЮНИТ:
     - `systemctl kill|stop` по боевому процессу контура (splinter, orchestrator-daemon, userbot,
       moderation_bot, pc_agent) → ЖЁСТКИЙ БЛОК: deny, карточки НЕТ, approve НЕВОЗМОЖЕН;
     - `systemctl restart|start|…` по тем же сервисам → красное с карточкой (решает владелец);
     - чужие юниты (nginx, wa-webhook) и рутина (daemon-reload) → как раньше, defer к allow/ask rules.
   Прежний инвариант «guard деферит ЛЮБОЙ systemctl» отменён владельцем сознательно: собственный
   рестарт боевого сервиса теперь идёт через «да», а остановка — не идёт вообще.

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

print("\n1. Guard по системным командам (пересмотр 23.07.2026 — чёрный список процессов):")
# Через subprocess с PRETOOL_NOPUSH=1 (ноль карточек в Telegram) и JSON-вводом.
# PRETOOL_GUARD_LOG уводим в /tmp, чтобы тест не писал в боевой журнал блоков.
env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
env["PRETOOL_GUARD_LOG"] = "/tmp/cc_pretool_guard_test_own_restarts.log"


def guard(cmd):
    inp = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    p = subprocess.run([PY, GUARD], input=inp, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip()


for cmd in ["systemctl daemon-reload", "systemctl restart wa-webhook", "systemctl restart nginx"]:
    rc, out = guard(cmd)
    res.append(ok(rc == 0 and out == "", f"guard деферит '{cmd}' (exit={rc}, stdout='{out[:50]}')"))

for cmd in ["systemctl restart splinter", "systemctl start orchestrator-daemon"]:
    rc, out = guard(cmd)
    res.append(ok(rc == 0 and '"ask"' in out and "🔴" in out,
                  f"свой рестарт '{cmd}' → красное с карточкой (ask)"))

for cmd in ["systemctl stop splinter", "systemctl kill orchestrator-daemon"]:
    rc, out = guard(cmd)
    res.append(ok(rc == 0 and '"deny"' in out and "🔴 КРАСНОЕ" not in out,
                  f"остановка боевого '{cmd}' → жёсткий блок (deny, карточки нет)"))

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
