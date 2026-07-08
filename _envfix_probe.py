"""Живой probe UX-фикса №2 (08.07.2026): env-префикс перед интерпретатором vs allow-матч.

Механика как в _claspsplit_probe.py (de36412): claude -p + --settings слой, смотрим
RAN/BLOCKED. Три прогона (вариант — первым аргументом):

  control: `PRETOOL_NOPUSH=1 venv/bin/python3 --version` БЕЗ доп. слоя.
           Ожидаем BLOCKED — подтверждение бага: project-allow `Bash(venv/bin/python3 *)`
           НЕ матчит команду с env-префиксом.
  dup:     тот же cmd + --settings слой `Bash(PRETOOL_NOPUSH=1 venv/bin/python3 *)`.
           Ожидаем RAN — литеральный env-дубль матчится движком → форма правильная.
  wildval: `PROBE_UX2=abc echo PROBE_OK` + слой `Bash(PROBE_UX2=* echo PROBE*)`.
           Информативно: работает ли wildcard в ЗНАЧЕНИИ переменной.
"""
import json
import os
import subprocess
import sys

VARIANTS = {
    "control": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 --version",
        "settings": None,
    },
    "dup": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 --version",
        "settings": {"permissions": {"allow": ["Bash(PRETOOL_NOPUSH=1 venv/bin/python3 *)"]}},
    },
    "wildval": {
        "cmd": "PROBE_UX2=abc echo PROBE_OK",
        "settings": {"permissions": {"allow": ["Bash(PROBE_UX2=* echo PROBE*)"]}},
    },
    # ЧИСТЫЕ пробы (guard гарантированно defer'ит: echo — не python; tests/*.py — ранний defer).
    # Урок проб 1-й волны: --version-команды резал pretool_guard (hook ask бьёт allow) — конфаунд.
    "ctrl2": {
        "cmd": "PROBE_UX2=1 echo PROBE_OK",
        "settings": None,   # project allow `Bash(echo *)`; BLOCKED = матчер ломается на env-префиксе
    },
    "litecho": {
        "cmd": "PROBE_UX2=1 echo PROBE_OK",
        "settings": {"permissions": {"allow": ["Bash(PROBE_UX2=1 echo PROBE*)"]}},
    },
    "pytest_ctrl": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_cclog.py",
        "settings": None,
    },
    "pytest_dup": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_cclog.py",
        "settings": {"permissions": {"allow": ["Bash(PRETOOL_NOPUSH=1 venv/bin/python3 *)"]}},
    },
    # sanity: работает ли allow через --settings вообще (без env-префикса)
    "sanity": {
        "cmd": "sleep 2",
        "settings": {"permissions": {"allow": ["Bash(sleep *)"]}},
    },
    # широкий префикс: матчится ли хоть что-то с env-префиксом
    "broad": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 --version",
        "settings": {"permissions": {"allow": ["Bash(PRETOOL_NOPUSH=1 *)"]}},
    },
    # ведущая звёздочка: матч по хвосту команды
    "star": {
        "cmd": "PRETOOL_NOPUSH=1 venv/bin/python3 --version",
        "settings": {"permissions": {"allow": ["Bash(*venv/bin/python3 *)"]}},
    },
}

variant = sys.argv[1]
spec = VARIANTS[variant]

extra = []
if spec["settings"] is not None:
    path = "/tmp/envfix_probe_settings_%s.json" % variant
    with open(path, "w") as f:
        json.dump(spec["settings"], f)
    extra = ["--settings", path]

PROMPT = ("Use the Bash tool to run exactly this command once: " + spec["cmd"] + "\n"
          "Then reply with exactly one word: RAN if the tool executed successfully, "
          "or BLOCKED if the tool call was denied / needs permission. No other text.")

env = dict(os.environ)
env.setdefault("HOME", "/root")
env.pop("ANTHROPIC_API_KEY", None)
env.pop("OPENAI_API_KEY", None)

cmd = ["/usr/bin/claude", "-p", "--output-format", "json", "--max-turns", "3"] + extra + [PROMPT]
p = subprocess.run(cmd, capture_output=True, text=True, timeout=280, env=env,
                   cwd="/root/turbobaby-manager-bot")
out = (p.stdout or "").strip()
try:
    res = (json.loads(out).get("result") or "").strip()
except Exception:
    res = out[:200]
print("variant=%s exit=%s result=%s" % (variant, p.returncode, res[:120]))
