# -*- coding: utf-8 -*-
# smoke шага 7/7 родителя 185: вложенный headless claude -p с VPS (как _thinker_exec ПК-демона).
# Read-only: один генеративный вызов, ничего не исполняет (--allowed-tools '').
import json
import os
import subprocess
import tempfile

env = dict(os.environ)
env.pop("ANTHROPIC_API_KEY", None)
env.pop("OPENAI_API_KEY", None)
env.pop("CLAUDECODE", None)
env.pop("CLAUDE_CODE_ENTRYPOINT", None)
env["PYTHONIOENCODING"] = "utf-8"

cmd = ["claude", "-p", "ответь одним словом: ок", "--model", "fable",
       "--output-format", "json", "--max-turns", "1", "--allowed-tools", ""]
p = subprocess.run(cmd, cwd=tempfile.gettempdir(), capture_output=True,
                   encoding="utf-8", errors="replace", timeout=180, env=env)
print("rc:", p.returncode)
out = (p.stdout or "").strip()
try:
    j = json.loads(out)
    print("result:", (j.get("result") or "")[:200])
except Exception:
    print("stdout tail:", out[-300:])
    print("stderr tail:", (p.stderr or "")[-300:])
