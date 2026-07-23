import os, subprocess, sys
env = dict(os.environ)
env["PRETOOL_NOPUSH"] = "1"
r = subprocess.run(
    [os.path.join("venv", "bin", "python3"),
     "tests/test_settings_allowlist.py"],
    cwd="/root/turbobaby-manager-bot", env=env,
    capture_output=True, text=True)
print(r.stdout[-6000:])
print(r.stderr[-2000:])
sys.exit(r.returncode)
