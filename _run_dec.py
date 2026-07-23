import subprocess, os
env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
env["ORCH_TEST_MODE"] = "1"
r = subprocess.run(
    ["venv/bin/python3", "tests/test_orchestrator_dec.py"],
    capture_output=True, text=True, timeout=90, env=env
)
print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
if r.stderr:
    print("STDERR:", r.stderr[-1000:])
print("EXIT:", r.returncode)
