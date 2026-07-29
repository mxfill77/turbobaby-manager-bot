"""ТЕЧЬ GUARD-МАРКЕРОВ (цель 36, шаг 3, 29.07.2026) — уборка по возрасту.

Разбор жизненного цикла: маркер /tmp/cc_guard_block/{tid}.json пишет pretool_guard при красном
блоке внутри headless-задачи; удаляется он РОВНО в одном месте — _guard_marker_clear перед
запуском задачи ТОГО ЖЕ id. После обработки файл остаётся в боевом каталоге навсегда → в живом
каталоге цель 36 нашла инертные 12, 27, 399. Течь реальна (кейс 1 воспроизводит её живьём),
детонации «повтор номера» при этом НЕТ (кейс 8: clear снимает старый маркер до старта claude).

Самотесты:
(1) ТЕЧЬ ЖИВЬЁМ: guard-block → needs_approval, маркер остался на диске; sweep его убирает.
(2) Уборка по возрасту: старый убран, свежий (возраст < TTL) жив, не-.json не тронут.
(3) Рубильник GUARD_MARKER_TTL=0 → уборка выключена целиком (откат = как было).
(4) FAIL-SAFE: каталога нет / listdir падает / remove падает / getmtime падает → 0, без исключения.
(5) Тест-прогон боевой каталог НЕ трогает (ORCH_TEST_MODE=1 + дефолтный каталог → no-op);
    явно переданный каталог убирается всегда.
(6) cycle() зовёт уборку.
(7) ИНВАРИАНТ БЕЗОПАСНОСТИ: дефолт TTL заведомо больше TASK_TIMEOUT_DEV → маркер ЖИВОЙ задачи
    состариться до порога физически не может (плюс одно-воркерность: cycle не крутится в run_task).
(8) РЕГРЕСС МИНЫ «повтор номера»: старый маркер id=N + запуск задачи N → clear снял его,
    задача идёт штатно (done), ЧУЖУЮ карточку не ловит.
Сети/claude/Telegram нет: subprocess.Popen (_POPEN) подменён FakePopen, Bridge — FakeBridge."""
import os, sys, json, time, tempfile, shutil, threading
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")     # изоляция от боевого .env
os.environ["CURATOR"] = "0"                  # принудительно: env демона несёт боевые флаги
os.environ["STEP_SELFHEAL"] = "0"            # думатель в этих кейсах не нужен

import orchestrator_daemon as OD

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []


class FakePopen:
    """Мок claude -p: возвращает готовый вывод, terminate() прерывает ожидание."""
    def __init__(self, out="", rc=0, sleep_s=0.0, on_communicate=None):
        self._out, self._rc, self._sleep = out, rc, sleep_s
        self._on_communicate = on_communicate
        self.returncode = None
        self._killed = threading.Event()
    def communicate(self, timeout=None):
        if self._on_communicate:
            self._on_communicate()
        if self._sleep:
            self._killed.wait(self._sleep)
        if self.returncode is None:
            self.returncode = self._rc
        return self._out, ""
    def terminate(self): self.returncode = -15; self._killed.set()
    def kill(self): self.returncode = -9; self._killed.set()
    def poll(self): return self.returncode


class FakeBridge:
    def __init__(s): s.rows = {}
    def task_heartbeat(s, tid): return {"ok": True}
    def complete_task(s, tid, status, result=""):
        s.rows[int(tid)] = {"status": status, "result": result}; return {"ok": True}
    def set_needs_approval(s, tid, what):
        s.rows[int(tid)] = {"status": "needs_approval", "result": what}; return {"ok": True}


def aged(path, seconds):
    """Состарить файл: mtime = сейчас минус seconds."""
    t = time.time() - seconds
    os.utime(path, (t, t))


def marker(d, name, data=None):
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data or {"task_id": name, "hit": "add_transaction", "card": "карточка"}, f)
    return path


_real_POPEN = OD._POPEN
_real_run = OD.subprocess.run
_real_bc = OD.bc
_real_dir = OD.GUARD_BLOCK_DIR
_real_ttl = OD.GUARD_MARKER_TTL
OD.subprocess.run = lambda *a, **kw: type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()


# ── (1) течь живьём: после guard-block маркер остаётся; уборка его снимает ────
print("(1) течь живьём: маркер переживает свою задачу, sweep убирает:")
d1 = tempfile.mkdtemp(prefix="gm_ttl1_")
OD.GUARD_BLOCK_DIR = d1
OD.bc = FakeBridge()

def _plant(*a, **kw):
    marker(d1, "501.json", {"task_id": "501", "hit": "set_fleet_oil", "card": "масло байк 6789"})

OD._POPEN = lambda *a, **kw: FakePopen("вывод без маркера", rc=0, on_communicate=_plant)
st, txt = OD.run_task(501, "тест-течь", task_timeout=10)
res.append(ok(st == "needs_approval", f"guard-block отработал: статус {st!r}"))
res.append(ok(os.path.exists(os.path.join(d1, "501.json")),
              "ТЕЧЬ: после завершения задачи маркер ОСТАЛСЯ на диске (корень цели 36)"))
aged(os.path.join(d1, "501.json"), 7 * 3600)
OD.GUARD_MARKER_TTL = 6 * 3600
res.append(ok(OD._guard_markers_sweep(d1) == 1, "уборка сняла осиротевший маркер (1 шт)"))
res.append(ok(not os.path.exists(os.path.join(d1, "501.json")), "файла больше нет"))
shutil.rmtree(d1, ignore_errors=True)


# ── (2) уборка строго по возрасту ────────────────────────────────────────────
print("(2) уборка по возрасту:")
d2 = tempfile.mkdtemp(prefix="gm_ttl2_")
OD.GUARD_MARKER_TTL = 3600
old1, old2 = marker(d2, "12.json"), marker(d2, "399.json")
fresh = marker(d2, "777.json")
other = os.path.join(d2, "notes.txt")
with open(other, "w") as f:
    f.write("не наш файл")
aged(old1, 7200); aged(old2, 100000); aged(fresh, 300); aged(other, 100000)
n = OD._guard_markers_sweep(d2)
res.append(ok(n == 2, f"убрано ровно 2 старых (получили {n})"))
res.append(ok(not os.path.exists(old1) and not os.path.exists(old2), "инертные 12 и 399 сняты"))
res.append(ok(os.path.exists(fresh), "свежий маркер (300с < TTL) НЕ тронут — может быть живой задачи"))
res.append(ok(os.path.exists(other), "не-.json файл в каталоге не тронут"))
res.append(ok(OD._guard_markers_sweep(d2) == 0, "повторный проход — идемпотентен (убирать нечего)"))
shutil.rmtree(d2, ignore_errors=True)


# ── (3) рубильник TTL=0 ──────────────────────────────────────────────────────
print("(3) рубильник GUARD_MARKER_TTL=0:")
d3 = tempfile.mkdtemp(prefix="gm_ttl3_")
p3 = marker(d3, "27.json"); aged(p3, 999999)
OD.GUARD_MARKER_TTL = 0
res.append(ok(OD._guard_markers_sweep(d3) == 0, "TTL=0 → уборка не работает"))
res.append(ok(os.path.exists(p3), "TTL=0 → файл на месте (откат байт-в-байт к прежнему поведению)"))
OD.GUARD_MARKER_TTL = 3600
shutil.rmtree(d3, ignore_errors=True)


# ── (4) fail-safe ────────────────────────────────────────────────────────────
print("(4) fail-safe (уборка не роняет цикл):")
res.append(ok(OD._guard_markers_sweep("/tmp/нет-такого-каталога-guard-ttl") == 0,
              "каталога нет → 0, без исключения"))
d4 = tempfile.mkdtemp(prefix="gm_ttl4_")
p4 = marker(d4, "55.json"); aged(p4, 99999)
_real_remove, _real_getmtime = os.remove, os.path.getmtime

def _boom_remove(p): raise OSError("permission denied")
os.remove = _boom_remove
try:
    n4 = OD._guard_markers_sweep(d4)
finally:
    os.remove = _real_remove
res.append(ok(n4 == 0 and os.path.exists(p4), "remove падает → 0, файл на месте, исключения нет"))

def _boom_getmtime(p): raise OSError("stat failed")
os.path.getmtime = _boom_getmtime
try:
    n4b = OD._guard_markers_sweep(d4)
finally:
    os.path.getmtime = _real_getmtime
res.append(ok(n4b == 0 and os.path.exists(p4), "stat падает → файл пропущен, без исключения"))
res.append(ok(OD._guard_markers_sweep(d4) == 1, "после снятия поломок уборка работает"))
shutil.rmtree(d4, ignore_errors=True)


# ── (5) тест-прогон боевой каталог не трогает ────────────────────────────────
print("(5) тест-прогон не убирает БОЕВОЙ каталог (симметрия фикса 28.07):")
d5 = tempfile.mkdtemp(prefix="gm_ttl5_")
p5 = marker(d5, "88.json"); aged(p5, 99999)
OD.GUARD_BLOCK_DIR = d5                      # играет роль «боевого» дефолта
_prev_tm = os.environ.get("ORCH_TEST_MODE")
os.environ["ORCH_TEST_MODE"] = "1"
try:
    res.append(ok(OD._guard_markers_sweep() == 0 and os.path.exists(p5),
                  "ORCH_TEST_MODE=1 + дефолтный каталог → no-op, боевой файл цел"))
    res.append(ok(OD._guard_markers_sweep(d5) == 1,
                  "явно переданный каталог убирается и в тест-прогоне (осознанный вызов)"))
    p5b = marker(d5, "89.json"); aged(p5b, 99999)
    os.environ.pop("ORCH_TEST_MODE", None)
    res.append(ok(OD._guard_markers_sweep() == 1 and not os.path.exists(p5b),
                  "в бою (без ORCH_TEST_MODE) дефолтный каталог убирается"))
finally:
    if _prev_tm is None:
        os.environ.pop("ORCH_TEST_MODE", None)
    else:
        os.environ["ORCH_TEST_MODE"] = _prev_tm
    OD.GUARD_BLOCK_DIR = _real_dir
    shutil.rmtree(d5, ignore_errors=True)


# ── (6) cycle() зовёт уборку ─────────────────────────────────────────────────
print("(6) уборка встроена в цикл демона:")
_calls = []
_saved = {k: getattr(OD, k) for k in ("_guard_markers_sweep", "_prune_chain_cache", "_fixture_reap_open",
                                      "process_orphans", "process_na_reminders", "process_approved",
                                      "process_dec_tails", "process_pc_chains", "process_new")}
OD._guard_markers_sweep = lambda *a, **kw: _calls.append("sweep") or 0
for _name in ("_prune_chain_cache", "_fixture_reap_open", "process_orphans", "process_na_reminders",
              "process_approved", "process_dec_tails", "process_pc_chains", "process_new"):
    setattr(OD, _name, (lambda n: (lambda *a, **kw: _calls.append(n)))(_name))
try:
    OD.cycle()
finally:
    for k, v in _saved.items():
        setattr(OD, k, v)
res.append(ok("sweep" in _calls, f"cycle() зовёт _guard_markers_sweep (порядок: {_calls})"))
res.append(ok(_calls.index("sweep") < _calls.index("process_new"),
              "уборка идёт ДО взятия новой задачи (локальная ФС раньше сети)"))


# ── (7) инвариант безопасности дефолта ───────────────────────────────────────
print("(7) инвариант: дефолт TTL заведомо переживает самую длинную задачу:")
OD.GUARD_MARKER_TTL = _real_ttl
res.append(ok(isinstance(OD.GUARD_MARKER_TTL, int), f"константа собрана (TTL={OD.GUARD_MARKER_TTL}s)"))
res.append(ok(OD.GUARD_MARKER_TTL == 0 or OD.GUARD_MARKER_TTL > OD.TASK_TIMEOUT_DEV,
              f"TTL({OD.GUARD_MARKER_TTL}s) > TASK_TIMEOUT_DEV({OD.TASK_TIMEOUT_DEV}s) — "
              "маркер живой задачи не успевает состариться"))
src = open("/root/turbobaby-manager-bot/orchestrator_daemon.py", encoding="utf-8").read()
res.append(ok('_env_int("GUARD_MARKER_TTL"' in src, "TTL берётся из .env (настраиваемо без правки кода)"))


# ── (8) регресс мины «повтор номера» ─────────────────────────────────────────
print("(8) регресс: старый маркер того же id НЕ детонирует (clear перед стартом):")
d8 = tempfile.mkdtemp(prefix="gm_ttl8_")
OD.GUARD_BLOCK_DIR = d8
OD.bc = FakeBridge()
stale = marker(d8, "12.json", {"task_id": "12", "hit": "delete_event", "card": "ЧУЖАЯ карточка"})
aged(stale, 99999)
OD._POPEN = lambda *a, **kw: FakePopen("сводка: работа сделана", rc=0)
st8, txt8 = OD.run_task(12, "новая задача с номером 12", task_timeout=10)
res.append(ok(st8 == "done", f"задача id=12 прошла штатно, статус {st8!r}"))
res.append(ok("ЧУЖАЯ карточка" not in (txt8 or ""), "чужая карточка старого маркера не подхвачена"))
res.append(ok(not os.path.exists(stale), "старый маркер снят _guard_marker_clear до старта claude"))
OD.GUARD_BLOCK_DIR = _real_dir
shutil.rmtree(d8, ignore_errors=True)


OD._POPEN = _real_POPEN
OD.subprocess.run = _real_run
OD.bc = _real_bc
OD.GUARD_BLOCK_DIR = _real_dir
OD.GUARD_MARKER_TTL = _real_ttl

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
