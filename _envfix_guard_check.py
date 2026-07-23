"""Локальная проверка вердикта pretool_guard для probe-команд (без сети, PRETOOL_NOPUSH=1)."""
import json
import os
import subprocess

CMDS = [
    "venv/bin/python3 --version",
    "PRETOOL_NOPUSH=1 venv/bin/python3 --version",
    "PRETOOL_NOPUSH=1 venv/bin/python3 tests/test_cclog.py",
    "PROBE_UX2=1 echo PROBE_OK",
]
env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
for cmd in CMDS:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                          "cwd": "/root/turbobaby-manager-bot"})
    p = subprocess.run(["/root/turbobaby-manager-bot/venv/bin/python3",
                        "/root/turbobaby-manager-bot/pretool_guard.py"],
                       input=payload, capture_output=True, text=True, env=env, timeout=60)
    verdict = "defer(exit0)" if p.returncode == 0 and not p.stdout.strip() else (
        "out=" + p.stdout.strip()[:120] + " exit=" + str(p.returncode))
    print(repr(cmd), "->", verdict)
