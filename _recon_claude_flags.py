"""Read-only разведка: какие флаги настроек поддерживает установленный claude CLI."""
import subprocess

p = subprocess.run(["/usr/bin/claude", "--help"], capture_output=True, text=True, timeout=60)
txt = p.stdout + p.stderr
print("exit:", p.returncode)
for line in txt.splitlines():
    low = line.lower()
    if "settings" in low or "permission" in low or "setting-sources" in low or "--version" in low:
        print(line)
