"""tests/test_settings_failopen.py: deny Write/Edit вне whitelist-путей (failopen, шаг 1/6 родитель 185).

Whitelist (записывать можно): /root/turbobaby-manager-bot, /root/turbobaby-bridge-gs, /tmp.
Вне whitelist (deny):
  - Headless: //root/.claude/** (весь .claude), /etc/**, /usr/**, /var/**, /boot/**
  - Интерактив (_failopen): //root/.claude/settings.json + settings.local.json (точечно,
    чтобы не заблокировать memory), + те же системные dirs.

WARN если _failopen_new_settings.json не применён в .claude/settings.json.
headless_settings.json: deny применён напрямую (движок блокирует Write к своему --settings файлу
из текущей сессии — в тесте проверяем через прямой парсинг файла).

Применение интерактива владельцем:
  cp _failopen_new_settings.json .claude/settings.json
  (+ рестарт сессии claude)
"""
import json
import os
import sys
from fnmatch import fnmatchcase

ROOT = "/root/turbobaby-manager-bot"
SETTINGS = os.path.join(ROOT, ".claude", "settings.json")
HEADLESS = os.path.join(ROOT, "headless_settings.json")
PREPARED = os.path.join(ROOT, "_failopen_new_settings.json")

# Deny-правила headless: широкий блок .claude + системные dirs
HEADLESS_DENY = [
    "Write(//root/.claude/**)",
    "Edit(//root/.claude/**)",
    "Write(//etc/**)",
    "Edit(//etc/**)",
    "Write(//usr/**)",
    "Edit(//usr/**)",
    "Write(//var/**)",
    "Edit(//var/**)",
    "Write(//boot/**)",
    "Edit(//boot/**)",
]

# Deny-правила интерактива: точечная защита settings (не блокирует memory) + системные dirs
PREPARED_DENY = [
    "Write(//root/.claude/settings.json)",
    "Write(//root/.claude/settings.local.json)",
    "Edit(//root/.claude/settings.json)",
    "Edit(//root/.claude/settings.local.json)",
    "Write(//etc/**)",
    "Edit(//etc/**)",
    "Write(//usr/**)",
    "Edit(//usr/**)",
    "Write(//var/**)",
    "Edit(//var/**)",
    "Write(//boot/**)",
    "Edit(//boot/**)",
]

# Общая часть (в обоих наборах)
COMMON_DENY = [r for r in HEADLESS_DENY if r in PREPARED_DENY]

# Whitelist-пути: запись должна быть НЕ заблокирована
WHITELIST_PATHS = [
    "//root/turbobaby-manager-bot/bot.py",
    "//root/turbobaby-manager-bot/tests/test_foo.py",
    "//root/turbobaby-bridge-gs/Bridge.js",
    "//tmp/test_file.txt",
]

# Memory-путь: запись должна быть НЕ заблокирована в интерактиве (_failopen)
MEMORY_PATH = "//root/.claude/projects/-root-turbobaby-manager-bot/memory/user_role.md"

# Вне-whitelist пути: запись должна быть заблокирована headless-deny
OUTSIDE_PATHS_HEADLESS = [
    ("Write", "//root/.claude/settings.json"),
    ("Edit", "//root/.claude/settings.json"),
    ("Write", "//etc/passwd"),
    ("Edit", "//etc/hosts"),
    ("Write", "//usr/local/bin/evil"),
    ("Write", "//var/log/syslog"),
    ("Write", "//boot/grub.cfg"),
]

# Вне-whitelist пути: запись должна быть заблокирована prepared-deny
OUTSIDE_PATHS_PREPARED = [
    ("Write", "//root/.claude/settings.json"),
    ("Write", "//root/.claude/settings.local.json"),
    ("Edit", "//root/.claude/settings.json"),
    ("Write", "//etc/passwd"),
    ("Write", "//usr/local/bin/evil"),
    ("Write", "//var/log/syslog"),
    ("Write", "//boot/grub.cfg"),
]


def _pat(rule):
    """Извлечь путь-паттерн из 'Write(pat)' / 'Edit(pat)' → 'pat'. Иначе None."""
    for prefix in ("Write(", "Edit("):
        if rule.startswith(prefix) and rule.endswith(")"):
            return rule[len(prefix):-1]
    return None


def _is_denied(op, path, deny_rules):
    """True если (op, path) соответствует хотя бы одному deny-правилу (с учётом операции)."""
    for rule in deny_rules:
        if not rule.startswith(op + "("):
            continue
        pat = _pat(rule)
        if pat and fnmatchcase(path, pat):
            return True
    return False


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return c


res = []

# ── 1. HEADLESS ─────────────────────────────────────────────────────────────
print("Headless deny (headless_settings.json — применён напрямую):")
headless = json.load(open(HEADLESS))["permissions"]
headless_deny = headless.get("deny", [])
for rule in HEADLESS_DENY:
    res.append(ok(rule in headless_deny, f"headless deny содержит {rule}"))

print("Headless: whitelist-пути НЕ заблокированы (Write):")
for path in WHITELIST_PATHS:
    res.append(ok(not _is_denied("Write", path, headless_deny),
                  f"headless NOT deny Write {path}"))

print("Headless: вне-whitelist пути ЗАБЛОКИРОВАНЫ:")
for op, path in OUTSIDE_PATHS_HEADLESS:
    res.append(ok(_is_denied(op, path, headless_deny),
                  f"headless deny {op} {path}"))

# ── 2. PREPARED (_failopen_new_settings.json) ────────────────────────────────
print("Подготовленный _failopen_new_settings.json:")
if not os.path.exists(PREPARED):
    print("  FAIL _failopen_new_settings.json не существует!")
    res.append(False)
else:
    prep = json.load(open(PREPARED))["permissions"]
    prep_deny = prep.get("deny", [])
    for rule in PREPARED_DENY:
        res.append(ok(rule in prep_deny, f"prepared deny содержит {rule}"))

    print("Prepared: whitelist-пути НЕ заблокированы (Write):")
    for path in WHITELIST_PATHS:
        res.append(ok(not _is_denied("Write", path, prep_deny),
                      f"prepared NOT deny Write {path}"))

    print("Prepared: memory-путь НЕ заблокирован (headless строже):")
    res.append(ok(not _is_denied("Write", MEMORY_PATH, prep_deny),
                  f"prepared NOT deny Write {MEMORY_PATH}"))

    print("Prepared: вне-whitelist пути ЗАБЛОКИРОВАНЫ:")
    for op, path in OUTSIDE_PATHS_PREPARED:
        res.append(ok(_is_denied(op, path, prep_deny),
                      f"prepared deny {op} {path}"))

    print("Prepared: Bash-паттерны (cp deploy/*.service и др.) не тронуты:")
    bash_allow = prep.get("allow", [])
    res.append(ok("Bash(cp *)" in bash_allow, "prepared allow содержит Bash(cp *)"))
    res.append(ok("Bash(git push)" in bash_allow, "prepared allow содержит Bash(git push)"))

# ── 3. LIVE settings.json — WARN если не применено ───────────────────────────
live = json.load(open(SETTINGS))["permissions"]
live_deny = live.get("deny", [])
applied_common = all(r in live_deny for r in COMMON_DENY)
applied_settings_protect = ("Write(//root/.claude/settings.json)" in live_deny and
                            "Edit(//root/.claude/settings.json)" in live_deny)
applied = applied_common and applied_settings_protect
if applied:
    print("settings.json: failopen deny ПРИМЕНЁН")
else:
    print("WARN: failopen deny НЕ применён в .claude/settings.json (headless в .claude/ не пишет);\n"
          "  применить (владелец, интерактивная сессия):\n"
          "    cp _failopen_new_settings.json .claude/settings.json\n"
          "  (+ рестарт сессии claude)")

# ── 4. СТРУКТУРНЫЕ ПРОВЕРКИ ──────────────────────────────────────────────────
print("Headless-конфиг: НЕТ allow-правил (только ask/deny-забор):")
res.append(ok(not headless.get("allow"),
              "headless_settings.json не добавляет allow"))
res.append(ok(bool(headless.get("ask")), "headless ask-список непуст"))

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else f'ЕСТЬ FAIL ({sum(r for r in res if r)}/{len(res)})'}")
sys.exit(0 if all(res) else 1)
