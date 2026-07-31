"""mem_probe: проба памяти живого процесса (доказательство выкатки байтами процесса).

Проверяем на ЖИВОМ процессе, а не на моке: поднимаем дочерний python, который держит в памяти
маркер MARK_PRESENT и НЕ держит MARK_ABSENT, и читаем его память пробой.
  (1) зонд, который процесс держит → найден;
  (2) зонд, которого у процесса нет → 0 вхождений (иначе проба доказывала бы что угодно);
  (3) статистика читаемости заполнена (регионы найдены, что-то прочитано);
  (4) CLI отдаёт 0 и печатает обе строки; несуществующий pid → не 0, без трейсбека;
  (5) кириллический зонд отбит понятной ошибкой (в памяти CPython он не UCS1 — проба соврала бы
      «не найден» на живом коде).
MARK_ABSENT в дочерний процесс НЕ передаётся ни аргументом, ни через env — иначе он оказался бы
в его стеке и тест (2) стал бы пустышкой."""
import os
import subprocess
import sys
import time

sys.path.insert(0, "/root/turbobaby-manager-bot")

import mem_probe

PY = "/root/turbobaby-manager-bot/venv/bin/python3"
MARK_PRESENT = "MEMPROBE_MARKER_PRESENT_7391"
MARK_ABSENT = "MEMPROBE_MARKER_ABSENT_4477"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

# Дочерний процесс: держит MARK_PRESENT в живой переменной и спит.
child_code = (
    "keep = ['%s'] * 32\n"
    "import sys, time\n"
    "sys.stdout.write('ready\\n'); sys.stdout.flush()\n"
    "time.sleep(60)\n" % MARK_PRESENT
)
child = subprocess.Popen([PY, "-c", child_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True)
try:
    line = child.stdout.readline()          # ждём «ready»: память уже наполнена
    started = ok(line.strip() == "ready", f"дочерний процесс поднялся (pid={child.pid})")
    res.append(started)

    print("(1)-(3) проба живого процесса:")
    hits, st = mem_probe.probe(child.pid, [MARK_PRESENT, MARK_ABSENT])
    res.append(ok(hits[MARK_PRESENT] > 0,
                  f"зонд, который процесс держит → найден ({hits[MARK_PRESENT]} вхожд.)"))
    res.append(ok(hits[MARK_ABSENT] == 0,
                  f"зонд, которого у процесса нет → 0 (получено {hits[MARK_ABSENT]})"))
    res.append(ok(st["regions"] > 0 and st["scanned_bytes"] > 0,
                  f"статистика: регионов={st['regions']}, прочитано={st['scanned_bytes']}"))

    print("(4) CLI:")
    p = subprocess.run([PY, "/root/turbobaby-manager-bot/mem_probe.py", str(child.pid),
                        MARK_PRESENT, MARK_ABSENT], capture_output=True, text=True, timeout=120)
    out = p.stdout
    res.append(ok(p.returncode == 0, f"CLI rc=0 (получено {p.returncode})"))
    res.append(ok(MARK_PRESENT in out and "НАЙДЕН" in out, "CLI печатает найденный зонд"))
    res.append(ok(MARK_ABSENT in out and "не найден" in out, "CLI печатает ненайденный зонд"))
finally:
    child.kill()
    child.wait(timeout=30)

print("(4б) несуществующий pid:")
free_pid = 4194300                            # выше /proc/sys/kernel/pid_max по умолчанию
while os.path.exists(f"/proc/{free_pid}"):
    free_pid -= 1
p = subprocess.run([PY, "/root/turbobaby-manager-bot/mem_probe.py", str(free_pid), "anything"],
                   capture_output=True, text=True, timeout=60)
res.append(ok(p.returncode != 0 and "Traceback" not in p.stderr,
              f"мёртвый pid → честный код {p.returncode} без трейсбека"))

print("(5) кириллический зонд:")
p = subprocess.run([PY, "/root/turbobaby-manager-bot/mem_probe.py", str(os.getpid()), "проба"],
                   capture_output=True, text=True, timeout=60)
res.append(ok(p.returncode == 2 and "ASCII" in p.stdout,
              "кириллица → понятная ошибка, а не тихое «не найдено»"))

print()
bad = len([x for x in res if not x])
print(f"ИТОГО: {len(res) - bad}/{len(res)} PASS")
sys.exit(1 if bad else 0)
