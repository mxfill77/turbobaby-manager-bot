#!/usr/bin/env python3
import subprocess, os, glob

tests = sorted(glob.glob("tests/test_*.py"))
results = []
for t in tests:
    env = dict(os.environ)
    env["PRETOOL_NOPUSH"] = "1"
    env["ORCH_TEST_MODE"] = "1"
    try:
        r = subprocess.run(
            ["venv/bin/python3", t],
            capture_output=True, text=True, timeout=90, env=env
        )
        last = (r.stdout + r.stderr).strip().split("\n")[-1]
        status = "PASS" if r.returncode == 0 else "FAIL"
    except subprocess.TimeoutExpired:
        last = "(TIMEOUT)"
        status = "FAIL"
    print(f"{status} {t}: {last}")
    if status == "FAIL":
        results.append(t)

print(f"\n{len(results)} failing: {results}")
