# -*- coding: utf-8 -*-
"""СВОЙ ВРЕМЕННЫЙ КАТАЛОГ НА ПРОГОН ГЕЙТА (25.10.2026, GATETMP2510).

ЖИВОЙ СЛУЧАЙ: /tmp сервера — tmpfs на 3871 МБ — 25.10 17:15 встал на 100%. Тесты кладут свои
mkdtemp-каталоги в /tmp и не убирают: один полный прогон гейта оставлял +589 МБ, за день — 11 454
записи на 2.2 ГБ. Гейт краснел на случайных файлах (6/414, затем 14/414 — другие), живой wa_agent
писал «состояние не сохранено ([Errno 28] No space left on device)».

Проверяется договор `gate._child_env()`: подпроцессы получают TMPDIR = каталог прогона, всё созданное
через tempfile ложится туда, а каталог уходит по выходу процесса гейта. Каждая зелёная проверка
стоит рядом с контролем на ПРЕЖНЕЙ строке env (без TMPDIR) — пустышка-фикс дал бы тот же зелёный.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # прогон вне гейта не будит владельца

import gate

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


SYS_TMP = os.path.realpath(tempfile.gettempdir())
PROBE = ("import tempfile, sys\n"
         "d = tempfile.mkdtemp(prefix='probe_')\n"
         "sys.stdout.write(d)\n")


def child_tmp(env):
    """Где подпроцесс с этим env создаёт свой mkdtemp-каталог."""
    r = subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True,
                       timeout=60)
    return os.path.realpath((r.stdout or "").strip())


def under(path, base):
    path, base = os.path.realpath(path), os.path.realpath(base)
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


# ── (1) env подпроцессов несёт TMPDIR = каталог прогона под системным temp ──────────────────
print("(1) TMPDIR каталога прогона:")
e1 = gate._child_env()
run_dir = e1.get("TMPDIR") or ""
ok(bool(run_dir) and os.path.isdir(run_dir), "TMPDIR задан и каталог существует: %r" % run_dir)
ok(under(run_dir, SYS_TMP) and run_dir != SYS_TMP,
   "каталог прогона ВНУТРИ системного temp, а не сам temp (проверки «временный корень» целы)")
ok(os.path.basename(run_dir).startswith("gate_run_"), "имя каталога узнаваемо: gate_run_*")
e2 = gate._child_env()
ok(e2.get("TMPDIR") == run_dir, "второй вызов — тот же каталог (один на процесс гейта)")
ok(e1.get("PRETOOL_NOPUSH") == "1" and e1.get("ORCH_TEST_MODE") == "1",
   "прежние признаки тест-прогона на месте")

# ── (2) тестовый подпроцесс создаёт свой temp ВНУТРИ каталога прогона ───────────────────────
print("(2) mkdtemp подпроцесса:")
got = child_tmp(e1)
ok(under(got, run_dir), "mkdtemp подпроцесса лёг в каталог прогона: %r" % got)
old_env = {k: v for k, v in e1.items() if k != "TMPDIR"}
old_env.pop("TMP", None)
old_env.pop("TEMP", None)
if os.name != "nt":
    old_got = child_tmp(old_env)
    ok(not under(old_got, run_dir),
       "контроль: на прежней строке env (без TMPDIR) каталог лёг МИМО каталога прогона")
    try:
        os.rmdir(old_got)                     # пустой каталог контроля — свой, только что создан
    except OSError:
        pass

# ── (3) уборка: каталог прогона уходит целиком, вместе с содержимым ──────────────────────────
print("(3) уборка каталога прогона:")
with open(os.path.join(got, "leftover.bin"), "wb") as f:
    f.write(b"x" * 4096)
gate._run_tmp_drop()
ok(not os.path.exists(run_dir), "после _run_tmp_drop каталога прогона нет (с содержимым)")
ok(gate._RUN_TMP is None, "состояние сброшено — следующий вызов создаст новый каталог")
e3 = gate._child_env()
ok(e3.get("TMPDIR") and e3["TMPDIR"] != run_dir and os.path.isdir(e3["TMPDIR"]),
   "после уборки — свежий каталог")
gate._run_tmp_drop()

# ── (4) уборка по ВЫХОДУ процесса (atexit) — путь gate_blame и обычного прогона ─────────────
print("(4) уборка по выходу процесса:")
script = ("import sys; sys.path.insert(0, %r)\n"
          "import gate\n"
          "d = gate._child_env()['TMPDIR']\n"
          "open(d + '/x.txt', 'w').write('x')\n"
          "sys.stdout.write(d)\n") % ROOT
r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60,
                   env=dict(os.environ, PRETOOL_NOPUSH="1"))
d = (r.stdout or "").strip()
ok(r.returncode == 0 and d and not os.path.exists(d),
   "процесс вышел — его каталог прогона убран: %r (rc=%s)" % (d, r.returncode))

# ── (5) каталог не создался (нет места) → прежнее поведение, гейт не падает ─────────────────
print("(5) нет места под каталог прогона:")
_real = tempfile.mkdtemp


def _no_space(*a, **k):
    raise OSError(28, "No space left on device")


tempfile.mkdtemp = _no_space
try:
    gate._RUN_TMP = None
    e5 = gate._child_env()
    ok("TMPDIR" not in e5 or e5.get("TMPDIR") == os.environ.get("TMPDIR"),
       "TMPDIR не подменён — env прежний, исключения нет")
finally:
    tempfile.mkdtemp = _real
    gate._RUN_TMP = None

n_ok = sum(res)
print("%d/%d" % (n_ok, len(res)))
sys.exit(0 if all(res) else 1)
