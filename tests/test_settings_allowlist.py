"""Страж permissions: allow-лист + РОЛЬ-РАЗВОД интерактив/headless (обновлено 08.07.2026).

История: 06.07 расширен allow (read-only утилиты); 08.07 permissions разведены ПО РОЛЯМ:
  - ИНТЕРАКТИВ владельца (Termux): clasp push/redeploy/deployments/version(s)/create-version
    в allow через .claude/settings.local.json (гит его игнорит глобально) — ноль промптов
    при исполнении одобренных конвертов. clasp deploy (создаёт НОВЫЙ деплой, ломает URL) и
    clasp run — остаются ask ВЕЗДЕ.
  - HEADLESS (orchestrator_daemon → claude -p): демон передаёт `--settings headless_settings.json`
    (git-истина, корень репо) — ask на ВСЮ clasp-запись. Precedence deny>ask>allow действует
    поверх всех источников → headless-ask бьёт allow из local владельца: забор цел, даже если
    local загружен. В -p режиме ask = авто-отказ → NEEDS_APPROVAL, как раньше.

ГЛАВНАЯ проверка: строгость ИМЕННО headless-пути = git-истина (project settings) + headless-конфиг;
live-файл владельца .claude/settings.local.json headless-проверка НЕ читает (его содержимое не
влияет на вердикт — забор доказывается симуляцией «local разрешил clasp» поверх headless-слоя).

Headless не может писать в .claude/ (гейт движка) → сплит применяется разово из Termux:
  cp _claspsplit_new_settings.json .claude/settings.json
  cp _claspsplit_new_settings.local.json .claude/settings.local.json
Пока не применён — тест проверяет подготовленные файлы и печатает WARN (как test_settings_deferred_restart).

UX-фикс №2 (08.07.2026, вердикт диагностики 13:09): env-префикс перед интерпретатором ломает
allow-матч движка — `PRETOOL_NOPUSH=1 venv/bin/python3 x` НЕ матчится `Bash(venv/bin/python3 *)`.
Лечение: в local — литеральные env-ДУБЛИ интерпретаторных правил. Форма подтверждена живым probe
(_envfix_probe.py, как в de36412): ctrl2 BLOCKED (баг есть) / litecho+pytest_dup RAN (дубль матчится).
Внимание конфаунду probe: hook pretool_guard сам ask'ает `… venv/bin/python3 --version` с префиксом
(hook бьёт allow) — probe-команды брать guard-deferred (echo / tests/*.py). Ask-список by design
не тронут: env-дубли покрывают ТОЛЬКО интерпретаторы, clasp/sqlite3/stop/sudo остаются ask/prompt.
"""
import json
import os
import subprocess
import sys
from fnmatch import fnmatchcase

ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
LOCAL = os.path.join(ROOT, ".claude", "settings.local.json")
HEADLESS = os.path.join(ROOT, "headless_settings.json")
PREPARED_PROJ = os.path.join(ROOT, "_claspsplit_new_settings.json")
PREPARED_LOCAL = os.path.join(ROOT, "_claspsplit_new_settings.local.json")
DAEMON_SRC = os.path.join(ROOT, "orchestrator_daemon.py")

# Зелёные — классифицируются allow (набор 06.07, не должен сломаться сплитом).
GREEN = [
    "echo hello", "printf '%s' x", "jq '.a' /tmp/x.json", "rg TODO splinter.py",
    "tr a b", "comm -12 a b", "column -t x", "file splinter.py", "basename /a/b",
    "dirname /a/b", "realpath .", "readlink -f splinter.py", "which python3",
    "command -v git", "printenv PATH", "env", "md5sum splinter.py", "sha256sum splinter.py",
    "du -sh .", "df -h", "ps aux", "free -m", "uptime", "whoami",
    "journalctl -u splinter -n 50", "git ls-files", "git grep TODO", "git blame splinter.py",
    "git shortlog -sn", "git describe --tags", "git reflog", "git tag", "git tag -l 'v*'",
    "python3 --version", "python3 -V", "python3 -m py_compile splinter.py",
    "tmux capture-pane -p",
    "grep -n X splinter.py", "systemctl restart splinter", "git push", "venv/bin/python3 gate.py",
]

# clasp-ЗАПИСЬ: в headless — строго ask (авто-отказ в -p), НИ ОДИН allow headless-источников не матчит.
CLASP_WRITE = [
    "clasp push",
    "clasp push --force",
    "clasp redeploy AKfycb...",
    "clasp deploy",
    "clasp deploy AKfycb...",
    "clasp run setupBrain",
    "clasp version 66",
    "clasp create-version",
    "clasp deployments",
]

# Владельцу в ИНТЕРАКТИВЕ — allow (одобренные конверты без промптов).
OWNER_ALLOW = [
    "clasp push",
    "clasp push --force",
    "clasp redeploy AKfycb...",
    "clasp deployments",
    "clasp version 66",
    "clasp versions",
    "clasp create-version",
]

# Пары «правило + env-дубль» (UX-фикс №2): base — в объединённом интерактив-allow,
# дубль — в local-allow; форма дубля = литеральный префикс, probe-подтверждена.
ENV_DUPS = [
    ("Bash(venv/bin/python3 *)", "Bash(PRETOOL_NOPUSH=1 venv/bin/python3 *)"),
    ("Bash(venv/bin/python *)", "Bash(PRETOOL_NOPUSH=1 venv/bin/python *)"),
    ("Bash(/root/turbobaby-manager-bot/venv/bin/python3 *)",
     "Bash(PRETOOL_NOPUSH=1 /root/turbobaby-manager-bot/venv/bin/python3 *)"),
    ("Bash(node *)", "Bash(PRETOOL_NOPUSH=1 node *)"),
    ("Bash(/root/turbobaby-manager-bot/venv/bin/python3 *)",
     "Bash(DOWRITE=1 /root/turbobaby-manager-bot/venv/bin/python3 *)"),
    ("Bash(venv/bin/python3 *)", "Bash(DOWRITE=1 venv/bin/python3 *)"),
]

# Env-префиксные команды владельца — после дублей ДОЛЖНЫ быть allow (интерактив).
ENV_GREEN = [
    "PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_cclog.py",
    "PRETOOL_NOPUSH=1 venv/bin/python3 gate.py",
    "PRETOOL_NOPUSH=1 /root/turbobaby-manager-bot/venv/bin/python3 /root/turbobaby-manager-bot/_recon.py",
    "PRETOOL_NOPUSH=1 node --check /root/turbobaby-bridge-gs/Bridge.js",
]

# Env-префикс НЕ должен открывать красное/ask-зону НИ в одной роли (дубли только на интерпретаторы).
ENV_NO_ALLOW = [
    "PRETOOL_NOPUSH=1 clasp push",
    "PRETOOL_NOPUSH=1 clasp deploy",
    "DOWRITE=1 sqlite3 memory.db .tables",
    "FOO=1 systemctl stop splinter",
    "PRETOOL_NOPUSH=1 sudo systemctl restart nginx",
]

# Опасное для ВСЕХ ролей: ask даже у владельца.
OWNER_STILL_ASK = [
    "clasp deploy",            # создаёт НОВЫЙ деплой → смена URL → Splinter отвалится
    "clasp deploy AKfycb...",
    "clasp run setupBrain",
    "sqlite3 memory.db .tables",
    "systemctl stop splinter",
    "sudo systemctl restart nginx",
]

RED_DENY = ["git push --no-verify", "git push --force", "git push -f origin main", "rm -rf /"]


def inner(rule):
    return rule[5:-1] if rule.startswith("Bash(") and rule.endswith(")") else None


def matches(cmd, rules):
    return [r for r in rules if inner(r) is not None and fnmatchcase(cmd, inner(r))]


def merge(*perms_list):
    """Слить permissions нескольких источников (модель движка: зоны объединяются)."""
    out = {"deny": [], "ask": [], "allow": []}
    for p in perms_list:
        for z in out:
            out[z] = out[z] + list(p.get(z, []))
    return out


def classify(cmd, perms):
    for zone in ("deny", "ask", "allow"):
        if matches(cmd, perms.get(zone, [])):
            return zone
    return "default"


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


live_proj = json.load(open(SETTINGS))["permissions"]
live_local = json.load(open(LOCAL))["permissions"]
applied_proj = "Bash(clasp push*)" not in live_proj.get("ask", [])
applied_local = ("Bash(clasp push*)" in live_local.get("allow", [])
                 and all(dup in live_local.get("allow", []) for _, dup in ENV_DUPS))
proj = live_proj if applied_proj else json.load(open(PREPARED_PROJ))["permissions"]
local = live_local if applied_local else json.load(open(PREPARED_LOCAL))["permissions"]
if applied_proj and applied_local:
    print("settings: сплит ПРИМЕНЁН — проверяю живые project+local файлы")
else:
    print("WARN: роль-сплит/env-дубли применены не полностью (project: %s, local: %s — local "
          "должен нести и clasp-allow, и env-дубли UX-фикса №2; headless в .claude/ не пишет) — "
          "недостающее проверяю по подготовленным _claspsplit_new_settings*.json; "
          "применение из Termux:\n"
          "  cp _claspsplit_new_settings.json .claude/settings.json\n"
          "  cp _claspsplit_new_settings.local.json .claude/settings.local.json\n"
          "  (+ рестарт сессии claude)"
          % ("да" if applied_proj else "нет", "да" if applied_local else "нет"))

headless_layer = json.load(open(HEADLESS))["permissions"]
res = []

print("HEADLESS-путь (git-истина project + headless_settings.json, БЕЗ local):")
hl = merge(proj, headless_layer)
for cmd in CLASP_WRITE:
    z = classify(cmd, hl)
    hit_allow = matches(cmd, hl["allow"])
    res.append(ok(z == "ask" and not hit_allow, "headless: " + cmd + " → ask, allow-матчей нет"))
for cmd in GREEN:
    res.append(ok(classify(cmd, hl) == "allow", "headless: " + cmd + " → allow"))
for cmd in RED_DENY:
    res.append(ok(classify(cmd, hl) == "deny", "headless: " + cmd + " → deny"))

print("ЗАБОР: даже если local владельца разрешил clasp — headless-ask бьёт его allow:")
owner_sim = {"allow": ["Bash(clasp push*)", "Bash(clasp redeploy*)", "Bash(clasp deployments*)",
                       "Bash(clasp version*)", "Bash(clasp create-version*)"]}
hl_leaky = merge(proj, headless_layer, owner_sim, local)
for cmd in CLASP_WRITE:
    res.append(ok(classify(cmd, hl_leaky) == "ask", "забор: " + cmd + " → ask при загруженном local"))

print("ИНТЕРАКТИВ владельца (project + local): конверты без промптов, опасное — ask:")
ia = merge(proj, local)
for cmd in OWNER_ALLOW:
    res.append(ok(classify(cmd, ia) == "allow", "интерактив: " + cmd + " → allow"))
for cmd in OWNER_STILL_ASK:
    res.append(ok(classify(cmd, ia) == "ask", "интерактив: " + cmd + " → ask"))
for cmd in RED_DENY:
    res.append(ok(classify(cmd, ia) == "deny", "интерактив: " + cmd + " → deny"))
for cmd in GREEN:
    res.append(ok(classify(cmd, ia) == "allow", "интерактив: " + cmd + " → allow"))

print("ENV-ДУБЛИ (UX-фикс №2): пара «правило + env-дубль», зелёный env-префикс allow, красное не открыто:")
for base, dup in ENV_DUPS:
    res.append(ok(base in ia["allow"], "env-пара: базовое правило на месте: " + base))
    res.append(ok(dup in local.get("allow", []), "env-пара: дубль в local: " + dup))
for cmd in ENV_GREEN:
    res.append(ok(classify(cmd, ia) == "allow", "интерактив env: " + cmd + " → allow"))
for cmd in ENV_NO_ALLOW:
    res.append(ok(not matches(cmd, ia["allow"]),
                  "интерактив env: " + cmd + " → allow-матчей НЕТ (prompt/ask)"))
    res.append(ok(not matches(cmd, merge(proj, headless_layer, local)["allow"]),
                  "headless env (даже с local): " + cmd + " → allow-матчей НЕТ"))
res.append(ok(all(inner(dup) is not None and "clasp" not in dup and "sqlite3" not in dup
                  and "systemctl" not in dup and "sudo" not in dup for _, dup in ENV_DUPS),
              "env-дубли покрывают только интерпретаторы (нет clasp/sqlite3/systemctl/sudo)"))

print("Headless-конфиг: только ask-забор, БЕЗ allow/deny-правок; демон передаёт его через --settings:")
res.append(ok(not headless_layer.get("allow") and not headless_layer.get("deny"),
              "headless_settings.json не добавляет allow/deny (только ask-забор)"))
for must in ["Bash(clasp push*)", "Bash(clasp redeploy*)", "Bash(clasp deploy*)", "Bash(clasp run*)"]:
    res.append(ok(must in headless_layer.get("ask", []), "headless ask содержит " + must))
src = open(DAEMON_SRC, encoding="utf-8").read()
res.append(ok('HEADLESS_SETTINGS = os.path.join(REPO, "headless_settings.json")' in src,
              "демон: HEADLESS_SETTINGS указывает на headless_settings.json"))
res.append(ok(src.count('"--settings", HEADLESS_SETTINGS') >= 2,
              "демон: --settings HEADLESS_SETTINGS в обоих claude-вызовах (исполнитель+думатель)"))

print("git-забор: local игнорится (не попадёт в git-истину), headless-конфиг — НЕ игнорится:")
ign_local = subprocess.run(["git", "check-ignore", "-q", ".claude/settings.local.json"],
                           cwd=ROOT).returncode == 0
ign_hl = subprocess.run(["git", "check-ignore", "-q", "headless_settings.json"],
                        cwd=ROOT).returncode == 0
res.append(ok(ign_local, ".claude/settings.local.json игнорится git"))
res.append(ok(not ign_hl, "headless_settings.json НЕ игнорится (git-истина)"))

print("Прежний ask-костяк project (кроме clasp push/redeploy) на месте:")
for a in ["Bash(sqlite3 *)", "Bash(clasp run*)", "Bash(systemctl stop*)", "Bash(sudo systemctl *)"]:
    res.append(ok(a in proj.get("ask", []), "project ask содержит " + a))

if not applied_proj:
    print("Подготовленный project = живой settings минус clasp push*/redeploy*, deploy* сужен (остальное байт-в-байт):")
    res.append(ok(proj["allow"] == live_proj["allow"] and proj["deny"] == live_proj["deny"],
                  "prepared project: allow/deny идентичны живому"))
    gone = {"Bash(clasp push*)", "Bash(clasp redeploy*)", "Bash(clasp deploy*)"}
    narrowed = {"Bash(clasp deploy)", "Bash(clasp deploy *)"}
    exp_ask = [r for r in live_proj["ask"] if r not in gone]
    got_ask = [r for r in proj["ask"] if r not in narrowed]
    res.append(ok(got_ask == exp_ask and narrowed <= set(proj["ask"]),
                  "prepared project: ask-diff = ровно clasp-сплит"))
if not applied_local:
    res.append(ok(all(r in local.get("allow", []) for r in live_local.get("allow", [])),
                  "prepared local: прежние локальные allow-записи сохранены"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
