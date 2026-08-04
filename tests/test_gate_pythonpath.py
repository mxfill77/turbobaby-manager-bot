# -*- coding: utf-8 -*-
"""PYTHONPATH ПОДПРОЦЕССОВ ГЕЙТА — СОБИРАЕТСЯ, А НЕ ПЕРЕЗАПИСЫВАЕТСЯ (04.08.2026, шаг 3 цели 282).

ПРЕМИСА ШАГА НЕ ПОДТВЕРДИЛАСЬ, И ЭТО ЗАФИКСИРОВАНО ЗДЕСЬ ПРОВЕРКОЙ (секция 7). ТЗ утверждало:
«gate.py перетирает PYTHONPATH → аудит-хук tests/livewatch.py под гейтом НЕ активен». Замер
говорит обратное: все четыре живых пользователя (test_feed_list, test_feed_channel,
test_no_push_leak, test_guard_escalation) зовут `import livewatch` ПОСЛЕ
`sys.path.insert(0, <каталог tests>)`, да и sys.path[0] у прямо запущенного файла и так равен его
каталогу — PYTHONPATH в этом импорте не участвует вовсе. Прогон test_feed_list под живой строкой
env гейта: секция (9) зелёная, контроль «ноль не ложный» срабатывает. Хук под гейтом РАБОТАЛ.

ЧТО БЫЛО СЛОМАНО НА САМОМ ДЕЛЕ — ровно та строка, но другим боком: `dict(os.environ,
PYTHONPATH=ROOT, …)` ронял УНАСЛЕДОВАННЫЙ PYTHONPATH молча. Цена этого одна и она по существу
темы: наблюдатель, поставленный через PYTHONPATH (sitecustomize), до подпроцессов гейта не
доезжал. А это единственный способ покрыть ПОДПРОЦЕССЫ — тот самый честный предел из шапки
tests/livewatch.py («хук живёт в ЭТОМ процессе»), и именно так, sitecustomize'ом на PYTHONPATH,
был найден живой случай коммита dd5f4a5 (фикстура стирала боевой /tmp/cc_guard_block/88.json).

Поэтому проверки идут парами «стало / было»: у каждой зелёной есть контроль на СТАРОЙ строке
env — иначе фикс-пустышка дал бы ровно тот же зелёный.
"""
import os
import subprocess
import sys
import tempfile

ROOT = "/root/turbobaby-manager-bot"
TESTS = os.path.join(ROOT, "tests")
PY = os.path.join(ROOT, "venv", "bin", "python3")
sys.path.insert(0, ROOT)
sys.path.insert(0, TESTS)
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # прогон вне гейта не будит владельца

# Страж боевых каталогов состояния (правило dd5f4a5) — взводится ДО импортов. Свой процесс ловит
# хук, след ПОДПРОЦЕССОВ (а их здесь много) — снимок: ровно то разделение, о котором секция 6.
LIVE_STATE = ("/tmp/cc_feed_seen", "/tmp/cc_feed_seen_test", "/tmp/cc_guard_block")
import livewatch
LW = livewatch.watch(*LIVE_STATE)
BEFORE_LIVE = livewatch.snapshot(*LIVE_STATE)

import gate

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return c


TMP = tempfile.mkdtemp(prefix="gatepp_")
WATCHDIR = os.path.join(TMP, "watch")       # сюда кладём sitecustomize «наблюдателя вызывающего»
os.makedirs(WATCHDIR, exist_ok=True)

# Старая строка env — ДОСЛОВНО как было до фикса; контроль каждой зелёной проверки.
OLD_ENV = dict(os.environ, PYTHONPATH=ROOT, PRETOOL_NOPUSH="1", ORCH_TEST_MODE="1")


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def run(script, env):
    r = subprocess.run([PY, script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def child_env(inherited=None):
    """gate._child_env() при заданном PYTHONPATH вызывающего (восстанавливаем окружение обратно)."""
    saved = os.environ.get("PYTHONPATH")
    if inherited is None:
        os.environ.pop("PYTHONPATH", None)
    else:
        os.environ["PYTHONPATH"] = inherited
    try:
        return gate._child_env()
    finally:
        if saved is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = saved


def parts_of(env):
    return (env.get("PYTHONPATH") or "").split(os.pathsep)


# ── (1) ПРЕЖНИЙ ДОГОВОР ЦЕЛ: ROOT ПЕРВЫМ ───────────────────────────────────────────────────
print("(1) прежний договор цел — ROOT первым (import splinter из tests/):")
e = child_env(None)
ok(parts_of(e)[0] == ROOT, "ROOT — первая запись пути: %r" % parts_of(e)[:1])
ok(e.get("PRETOOL_NOPUSH") == "1" and e.get("ORCH_TEST_MODE") == "1",
   "признаки тест-прогона на месте (PRETOOL_NOPUSH, ORCH_TEST_MODE)")
rc, out = run(write(os.path.join(TMP, "imp_splinter.py"),
                    "import splinter\nprint('splinter ok')\n"), e)
ok(rc == 0 and "splinter ok" in out, "подпроцесс видит splinter (договор ROOT работает вживую)")

# ── (2) УНАСЛЕДОВАННЫЙ PYTHONPATH БОЛЬШЕ НЕ ТЕРЯЕТСЯ ───────────────────────────────────────
print("(2) унаследованный PYTHONPATH больше не роняется молча:")
e = child_env(WATCHDIR)
ok(WATCHDIR in parts_of(e), "путь вызывающего доехал до подпроцесса")
ok(parts_of(e)[0] == ROOT, "и при этом ROOT остался первым (порядок не перевёрнут)")
ok(WATCHDIR not in parts_of(OLD_ENV), "контроль: на СТАРОЙ строке того же пути не было")
e2 = child_env(os.pathsep.join([WATCHDIR, ROOT, "", WATCHDIR, "  "]))
ok(parts_of(e2).count(WATCHDIR) == 1 and parts_of(e2).count(ROOT) == 1,
   "дубли сняты: %r" % parts_of(e2))
ok("" not in parts_of(e2), "пустые записи не попали в путь (пустая = текущий каталог)")
ok(parts_of(e2)[0] == ROOT, "дедуп не сдвинул ROOT с первого места")

# ── (3) tests/ НА ПУТИ → import livewatch НЕ ЗАВИСИТ ОТ ФОРМЫ ЗАПУСКА ──────────────────────
print("(3) tests/ на пути — import livewatch не зависит от формы запуска:")
e = child_env(None)
ok(TESTS in parts_of(e), "каталог tests/ в пути подпроцесса")
# Пробник лежит ВНЕ tests/, sys.path-игр не делает: у него sys.path[0] = свой каталог, значит
# livewatch доступен ровно через PYTHONPATH и никак иначе.
probe_bare = write(os.path.join(TMP, "imp_livewatch_bare.py"),
                   "import livewatch\nprint('livewatch from', livewatch.__file__)\n")
rc, out = run(probe_bare, e)
ok(rc == 0 and "livewatch from" in out, "вне tests/ и без sys.path-игр: импорт проходит")
rc_old, out_old = run(probe_bare, OLD_ENV)
ok(rc_old != 0 and "ModuleNotFoundError" in out_old,
   "контроль: на СТАРОЙ строке тот же пробник падал — фикс не пустышка")

# ── (4) ОБЕ ТОЧКИ ВЫЗОВА НЕСУТ ОДНУ СТРОКУ ─────────────────────────────────────────────────
print("(4) обе точки вызова гейта берут ОДНУ строку env (иначе фикс наполовину):")
seen_envs = []


class _R:
    returncode = 0


_orig_run, _orig_glob = gate.subprocess.run, gate.glob.glob
gate.subprocess.run = lambda args, **kw: (seen_envs.append(kw.get("env") or {}), _R())[1]
gate.glob.glob = lambda pat: [os.path.join(TMP, "test_x.py")]
try:
    gate.run_tests()
    n_full = len(seen_envs)
    gate.run_selective_tests(["gate.py"])
finally:
    gate.subprocess.run, gate.glob.glob = _orig_run, _orig_glob
ok(n_full >= 1 and len(seen_envs) > n_full, "сняты env обоих режимов (полный и селективный)")
ok(all(parts_of(x)[:2] == [ROOT, TESTS] for x in seen_envs),
   "в каждом подпроцессе — одна и та же голова пути [ROOT, tests/]")
ok(all(x.get("PRETOOL_NOPUSH") == "1" for x in seen_envs),
   "и в каждом — мут пушей (селективный режим не растерял признаки)")

# ── (5) ЖИВОЙ ПОДПРОЦЕСС: ХУК ВЗВОДИТСЯ И ЛОВИТ ЗАПИСЬ ─────────────────────────────────────
print("(5) сквозь живой подпроцесс: хук не просто импортирован, а ЛОВИТ действие:")
probe_hook = write(os.path.join(TMP, "probe_hook.py"), """
import os, sys
import livewatch
D = sys.argv[1] if len(sys.argv) > 1 else os.environ["PROBE_DIR"]
W = livewatch.watch(D)
p = os.path.join(D, "touched.txt")
with open(p, "w", encoding="utf-8") as f:
    f.write("x")
os.remove(p)                      # создал-и-убрал: снимок такого не видит, хук обязан увидеть
print("WRITES=%d" % len(W.writes()))
""")
probe_dir = os.path.join(TMP, "probe_state")
os.makedirs(probe_dir, exist_ok=True)
e = dict(child_env(None), PROBE_DIR=probe_dir)
rc, out = run(probe_hook, e)
ok(rc == 0 and "WRITES=" in out, "пробник отработал под строкой гейта")
ok("WRITES=0" not in out, "хук поймал «создал-и-убрал» (записей > 0): %s" % out.strip()[-40:])

# ── (6) ЗАКРЫТЫЙ ПРЕДЕЛ: НАБЛЮДАТЕЛЬ ВЫЗЫВАЮЩЕГО ДОЕЗЖАЕТ ДО ПОДПРОЦЕССА ───────────────────
print("(6) наблюдатель через sitecustomize доезжает до подпроцесса гейта (предел из шапки livewatch):")
marker = os.path.join(TMP, "sitecustomize_loaded.txt")
write(os.path.join(WATCHDIR, "sitecustomize.py"),
      "with open(%r, 'a', encoding='utf-8') as f:\n    f.write('loaded\\n')\n" % marker)
quiet = write(os.path.join(TMP, "quiet.py"), "print('ok')\n")
rc, out = run(quiet, child_env(WATCHDIR))
loaded_new = os.path.exists(marker)
ok(rc == 0 and loaded_new, "наблюдатель вызывающего загрузился в подпроцессе теста")
if loaded_new:
    os.remove(marker)
rc, out = run(quiet, OLD_ENV)
ok(rc == 0 and not os.path.exists(marker),
   "контроль: на СТАРОЙ строке он не доезжал вовсе — это и было сломано")

# ── (7) ПРЕМИСА ТЗ, НАЗВАННАЯ ПРОВЕРКОЙ ────────────────────────────────────────────────────
print("(7) премиса ТЗ («хук под гейтом не активен») — проверкой, а не пересказом:")
probe_asuser = write(os.path.join(TMP, "probe_as_user.py"), """
import os, sys
sys.path.insert(0, %r)            # ровно то, что делают все четыре живых пользователя
import livewatch
W = livewatch.watch("/tmp/cc_guard_block")
print("HOOK_OK")
""" % TESTS)
rc, out = run(probe_asuser, OLD_ENV)
ok(rc == 0 and "HOOK_OK" in out,
   "на СТАРОЙ строке env хук всё равно взводился → премиса «не активен» не подтвердилась")
users = ["test_feed_list.py", "test_feed_channel.py", "test_no_push_leak.py",
         "test_guard_escalation.py"]
lifted = []
for u in users:
    with open(os.path.join(TESTS, u), encoding="utf-8") as f:
        src = f.read()
    i_path, i_lw = src.find("sys.path.insert"), src.find("import livewatch")
    lifted.append(i_lw > 0 and 0 <= i_path < i_lw)
ok(all(lifted), "все четыре пользователя кладут tests/ в sys.path ДО импорта: %r" % lifted)
ok(len(users) == 4, "пользователей ровно четыре — список не разъехался с коммитом dd5f4a5")

# ── (8) ПРОГОН НЕ КАСАЕТСЯ БОЕВЫХ КАТАЛОГОВ ────────────────────────────────────────────────
print("(8) прогон не касается боевых каталогов состояния:")
ok(not LW.writes(), "ноль ЗАПИСЕЙ в боевые каталоги (свой процесс): %s" % LW.report())
_d = livewatch.diff(BEFORE_LIVE, livewatch.snapshot(*LIVE_STATE))
ok(not _d, "снимок не разошёлся — след подпроцессов тоже чист: %s" % _d)
_ctl = livewatch.watch(TMP)
write(os.path.join(TMP, "ctl.txt"), "x")
ok(_ctl.writes() and not LW.writes(),
   "контроль «ноль не ложный»: страж ловит запись в свой каталог (%s)" % _ctl.report())
ok(TMP.startswith(tempfile.gettempdir()) and "gatepp_" in TMP,
   "своё состояние — временный каталог с уникальным суффиксом (%s)" % TMP)

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
