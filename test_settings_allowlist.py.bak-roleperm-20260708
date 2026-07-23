"""Регресс расширения allow-листа .claude/settings.json (заведено 06.07.2026).

Цель правки: частые БЕЗОПАСНЫЕ команды (read-only утилиты, git-читалки, python --version,
tmux capture) перестают падать в дефолт-prompt → уходят в allow. КРАСНОЕ (sqlite3 CLI, clasp
push/redeploy/deploy/run, systemctl stop, sudo systemctl) остаётся ask; deny остаётся deny.

ГЛАВНАЯ проверка регресса: НИ ОДИН новый allow-паттерн не задел красное — для каждой красной
команды classify() всё ещё возвращает ask/deny, и ни одно allow-правило её не матчит.

Headless не может писать в .claude/settings.json (гейт движка) → правка внесётся разовым
`cp _allow_new_settings.json .claude/settings.json` из Termux. Пока не внесена — тест проверяет
подготовленный _allow_new_settings.json и печатает WARN (как test_settings_deferred_restart).
"""
import json
import os
import sys
from fnmatch import fnmatchcase

ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
PREPARED = os.path.join(ROOT, "_allow_new_settings.json")

# Представительный маркер применённости (одна из НОВЫХ зелёных строк).
MARKER = "Bash(jq *)"

# Новые (или уже бывшие) ЗЕЛЁНЫЕ — должны классифицироваться allow.
GREEN = [
    "echo hello",
    "printf '%s' x",
    "jq '.a' /tmp/x.json",
    "rg TODO splinter.py",
    "tr a b",
    "comm -12 a b",
    "column -t x",
    "file splinter.py",
    "basename /a/b",
    "dirname /a/b",
    "realpath .",
    "readlink -f splinter.py",
    "which python3",
    "command -v git",
    "printenv PATH",
    "env",
    "md5sum splinter.py",
    "sha256sum splinter.py",
    "du -sh .",
    "df -h",
    "ps aux",
    "free -m",
    "uptime",
    "whoami",
    "journalctl -u splinter -n 50",
    "git ls-files",
    "git grep TODO",
    "git blame splinter.py",
    "git shortlog -sn",
    "git describe --tags",
    "git reflog",
    "git tag",
    "git tag -l 'v*'",
    "python3 --version",
    "python3 -V",
    "python3 -m py_compile splinter.py",
    "tmux capture-pane -p",
    # прежние зелёные — не должны сломаться
    "grep -n X splinter.py",
    "systemctl restart splinter",
    "git push",
    "venv/bin/python3 gate.py",
]

# КРАСНОЕ — должно остаться ask (и НИ ОДИН allow-паттерн его не матчит).
RED_ASK = [
    "sqlite3 memory.db .tables",
    "sqlite3 memory.db 'UPDATE x SET a=1'",
    "clasp push",
    "clasp redeploy AKfycb...",
    "clasp deploy",
    "clasp run setupBrain",
    "systemctl stop splinter",
    "systemctl stop orchestrator-daemon",
    "sudo systemctl restart nginx",
]

# DENY — остаётся deny.
RED_DENY = [
    "git push --no-verify",
    "git push --force",
    "git push -f origin main",
    "rm -rf /",
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
applied = MARKER in live["allow"]
if applied:
    perms = live
    print("settings.json: расширенный allow ВНЕСЁН — проверяю живой файл")
else:
    perms = json.load(open(PREPARED))["permissions"]
    print("WARN: расширенный allow ЕЩЁ НЕ в .claude/settings.json (гейт headless) — "
          "проверяю подготовленный _allow_new_settings.json; применение = "
          "cp _allow_new_settings.json .claude/settings.json из Termux + рестарт сессии claude")

res = []

print("Зелёные команды → allow (без prompt):")
for cmd in GREEN:
    res.append(ok(classify(cmd, perms) == "allow", cmd + " → allow"))

print("Красные → ask И ни одно allow-правило не матчит (регресс: расширение не задело красное):")
for cmd in RED_ASK:
    z = classify(cmd, perms)
    hit_allow = matches(cmd, perms.get("allow", []))
    res.append(ok(z == "ask" and not hit_allow,
                  cmd + " → ask, allow-матчей нет" + ("" if not hit_allow else " !!!" + str(hit_allow))))

print("Deny остаётся deny:")
for cmd in RED_DENY:
    res.append(ok(classify(cmd, perms) == "deny", cmd + " → deny"))

print("Тройная защита красного не ослаблена (ask-лист = §7 красное, целиком на месте):")
ASK_MUST = ["Bash(sqlite3 *)", "Bash(clasp push*)", "Bash(clasp redeploy*)", "Bash(clasp deploy*)",
            "Bash(clasp run*)", "Bash(systemctl stop*)", "Bash(sudo systemctl *)"]
for a in ASK_MUST:
    res.append(ok(a in perms["ask"], "ask содержит " + a))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
