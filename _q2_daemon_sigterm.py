"""Мягкая перезагрузка orchestrator-daemon для подхвата преамбулы v3 (Q2, 03.07).
НЕ systemctl restart: он убил бы cgroup вместе с текущим claude -p (эта задача — его ребёнок).
SIGTERM → штатный _stop демона: _running=False, демон ДОРАБОТАЕТ текущую итерацию (эту задачу),
отчитается в Bridge и выйдет; systemd (Restart=always, 15с) поднимет его с новым кодом.
Read-only по данным; сигнал процессу — обратимый (Restart=always). Зона 🟠."""
import os
import signal
import subprocess

p = subprocess.run(["systemctl", "show", "-p", "MainPID", "orchestrator-daemon"],
                   capture_output=True, text=True)
pid = int(p.stdout.strip().split("=", 1)[1])
if pid <= 1:
    print("FAIL: MainPID не найден:", p.stdout.strip())
    raise SystemExit(1)
os.kill(pid, signal.SIGTERM)
print(f"SIGTERM отправлен orchestrator-daemon (pid={pid}) — мягкий выход после текущей итерации, "
      f"systemd поднимет с преамбулой v3.")
