"""Функциональный probe механизма забора (08.07.2026, роль-развод permissions).

Доказываем ЖИВЫМ claude -p, что `--settings <file>` с ask-правилом БЬЁТ project-allow
(precedence deny>ask>allow поверх источников) — та самая механика, на которой держится
headless-забор clasp. Пробуем НЕ clasp (он и так ask в живом project), а echo:
`echo PROBE_OK` в project = allow; probe-слой кладёт его в ask → в -p должен быть авто-отказ.

Прогон A (с --settings probe-слоя): ожидаем BLOCKED.
Прогон B (без --settings, контроль): ожидаем RAN.
"""
import json
import os
import subprocess

PROBE_SETTINGS = "/tmp/claspsplit_probe_settings.json"
with open(PROBE_SETTINGS, "w") as f:
    json.dump({"permissions": {"ask": ["Bash(echo PROBE*)"]}}, f)

PROMPT = ("Use the Bash tool to run exactly this command once: echo PROBE_OK\n"
          "Then reply with exactly one word: RAN if the tool executed and returned PROBE_OK, "
          "or BLOCKED if the tool call was denied / needs permission. No other text.")

env = dict(os.environ)
env.setdefault("HOME", "/root")
env.pop("ANTHROPIC_API_KEY", None)
env.pop("OPENAI_API_KEY", None)


def run(label, extra):
    cmd = ["/usr/bin/claude", "-p", "--output-format", "json", "--max-turns", "3"] + extra + [PROMPT]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env,
                       cwd="/root/turbobaby-manager-bot")
    out = (p.stdout or "").strip()
    try:
        res = (json.loads(out).get("result") or "").strip()
    except Exception:
        res = out[:200]
    print(label, "exit=", p.returncode, "result=", res[:120])
    return res


a = run("A(--settings probe):", ["--settings", PROBE_SETTINGS])
b = run("B(control):", [])
ok = ("BLOCKED" in a.upper()) and ("RAN" in b.upper())
print("PROBE:", "PASS — ask из --settings бьёт project-allow, забор работает" if ok
      else "FAIL — механика --settings НЕ подтверждена, разберись перед применением")
