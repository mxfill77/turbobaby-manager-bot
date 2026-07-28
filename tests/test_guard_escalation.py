"""Guard escalation (шаг 2/6 родитель 185): красный блок pretool_guard внутри headless-задачи
→ маркер-файл /tmp/cc_guard_block/{tid}.json → демон-монитор terminate claude → needs_approval.

Самотесты:
(1) _guard_write_marker пишет JSON с hit/card при CC_TASK_ID; молчит без task_id.
(2) run_task: маркер-файл ДО execute → needs_approval (пост-проверка ловит мгновенный случай).
(3) run_task: монитор срабатывает в ходе execute (задержка) → needs_approval.
(4) Формат what: op=other | [{hit}] {card}\n[guard-block задача {tid}].
(5) Без маркера: обычный done/failed/needs_approval от NA_MARKER работает как раньше (регресс).
(6) _guard_what без данных/пустые данные → fail-safe строка.
(7) guard_marker_clear + guard_marker_read.
(8) CC_TASK_ID выставляется в child_env перед запуском.
Сети/claude нет — subprocess.Popen (_POPEN) подменён FakePopen."""
import os, sys, json, tempfile, shutil, threading
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"   # изоляция: не хотим think-loop в guard-тестах
import subprocess as _sp

import pretool_guard as PG
import orchestrator_daemon as OD

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

# FakePopen: имитирует subprocess.Popen + communicate() для _POPEN-мока.
# terminate() прерывает sleep в communicate() через Event — иначе async-монитор не работает.
class FakePopen:
    def __init__(self, out="", rc=0, sleep_s=0.0, exc=None, on_communicate=None):
        self._out = out; self._rc = rc; self._sleep = sleep_s
        self._exc = exc; self._on_communicate = on_communicate
        self.returncode = None
        self._killed = threading.Event()
        self.sleeping = threading.Event()    # set when communicate() enters its wait
    def communicate(self, timeout=None):
        if self._on_communicate:
            self._on_communicate()
        if self._sleep:
            self.sleeping.set()              # signal: now entering interruptible sleep
            self._killed.wait(self._sleep)   # прерывается terminate()/kill()
        else:
            self.sleeping.set()
        if self._exc:
            e = self._exc; self._exc = None; raise e
        if self.returncode is None:          # не перезаписываем rc от terminate()
            self.returncode = self._rc
        return self._out, ""
    def terminate(self): self.returncode = -15; self._killed.set()
    def kill(self): self._exc = None; self.returncode = -9; self._killed.set()
    def poll(self): return self.returncode


class FakeBridge:
    def __init__(s):
        s.rows = {}; s.nid = 100
    def task_heartbeat(s, tid): return {"ok": True}
    def complete_task(s, tid, status, result=""):
        s.rows[int(tid)] = {"status": status, "result": result}
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        s.rows[int(tid)] = {"status": "needs_approval", "result": what}
        return {"ok": True}

_real_POPEN = OD._POPEN
_real_run = OD.subprocess.run
OD.subprocess.run = lambda *a, **kw: type("P",(),{"stdout":"ok","stderr":"","returncode":0})()


# ── (1) pretool_guard._guard_write_marker ────────────────────────────────────
print("(1) _guard_write_marker:")
tmp_guard = tempfile.mkdtemp(prefix="guard_esc_")
_orig_env = os.environ.get(PG.BLOCK_DIR_ENV)
os.environ[PG.BLOCK_DIR_ENV] = tmp_guard      # каталог из env, читается В МОМЕНТ ЗАПИСИ
_CARD42 = "нужно да: масло, байк 6789"        # у карточки есть объект операции (вторая линия)
try:
    # записывает при наличии task_id
    PG._guard_write_marker("42", "set_fleet_oil", _CARD42)
    _name = PG.marker_name("42")
    path = os.path.join(tmp_guard, _name)
    res.append(ok(os.path.exists(path), f"маркер-файл создан ({_name})"))
    with open(path) as f:
        d = json.load(f)
    res.append(ok(d == {"task_id": "42", "hit": "set_fleet_oil", "card": _CARD42},
                  f"содержимое маркера корректно: {d}"))
    # молчит без task_id
    PG._guard_write_marker("", "set_fleet_oil", "карточка 1")
    res.append(ok(not os.path.exists(os.path.join(tmp_guard, ".json")),
                  "пустой task_id → файл не создаётся"))
    PG._guard_write_marker(None, "hit", "card")
    res.append(ok(True, "None task_id не роняет (fail-safe)"))
finally:
    if _orig_env is None:
        os.environ.pop(PG.BLOCK_DIR_ENV, None)
    else:
        os.environ[PG.BLOCK_DIR_ENV] = _orig_env
    shutil.rmtree(tmp_guard, ignore_errors=True)


# ── (1б) МИНА 28.07: гард-тесты внутри headless-задачи не смеют писать БОЕВОЙ маркер ─────────
print("(1б) изоляция маркера тест-прогона (мина 28.07, задача 12):")
_ON = {"ORCH_TEST_MODE": "1"}
_OFF = {}
_tmp_dir = tempfile.mkdtemp(prefix="guard_blockdir_")
res.append(ok(PG.block_dir({PG.BLOCK_DIR_ENV: _tmp_dir}) == _tmp_dir,
              "замок 1: PRETOOL_BLOCK_DIR уводит каталог"))
res.append(ok(PG.is_test_run(_ON) and not PG.is_test_run(_OFF),
              "замок 2: ORCH_TEST_MODE=1 → тест-прогон; пустое окружение → бой"))
res.append(ok(PG.is_test_run({"PRETOOL_NOPUSH": "1"}) and PG.is_test_run({"PYTEST_CURRENT_TEST": "x"}),
              "замок 2: PRETOOL_NOPUSH и PYTEST_CURRENT_TEST — тоже признак теста"))
res.append(ok(PG.block_dir(_ON) == PG.TEST_BLOCK_DIR != PG.GUARD_BLOCK_DIR,
              f"замок 2: умолчание тест-прогона {PG.TEST_BLOCK_DIR} ≠ боевого"))
res.append(ok(PG.block_dir(_OFF) == PG.GUARD_BLOCK_DIR,
              "замок 2: в бою умолчание прежнее (регресс)"))
res.append(ok(PG.marker_name("12", _ON) == "test-12.json" and PG.marker_name("12", _OFF) == "12.json",
              "замок 3: тест-маркер с префиксом, боевой — прежнее имя"))
_tmp2 = tempfile.mkdtemp(prefix="guard_obj_")
_prev = os.environ.get(PG.BLOCK_DIR_ENV)
os.environ[PG.BLOCK_DIR_ENV] = _tmp2
try:
    res.append(ok(PG.marker_has_object("add_transaction", "сумма 500")
                  and not PG.marker_has_object("op", "подтверди операцию"),
                  "вторая линия: объект операции распознаётся по номеру/величине"))
    PG._guard_write_marker("77", "op", "подтверди операцию")
    res.append(ok(not os.path.exists(os.path.join(_tmp2, PG.marker_name("77"))),
                  "вторая линия: карточка без объекта → маркера НЕТ"))
    PG._guard_write_marker("78", "op", "подтверди операцию", blocktype="hard")
    res.append(ok(os.path.exists(os.path.join(_tmp2, PG.marker_name("78"))),
                  "вторая линия: hard-блок пишется всегда (это не карточка на «да»)"))
finally:
    if _prev is None:
        os.environ.pop(PG.BLOCK_DIR_ENV, None)
    else:
        os.environ[PG.BLOCK_DIR_ENV] = _prev
    shutil.rmtree(_tmp2, ignore_errors=True)
    shutil.rmtree(_tmp_dir, ignore_errors=True)

# СКВОЗНОЙ РЕГРЕСС: гоняем НАСТОЯЩИЙ гард-тест ровно как гейт (gate.py:86), но с унаследованным
# CC_TASK_ID — именно эта связка убила задачу 12. Зовём _real_run: строкой выше в этом файле
# subprocess.run подменён моком для _POPEN-сценариев, и обычный вызов не запустил бы процесс.
_ROOT = "/root/turbobaby-manager-bot"
_PY = os.path.join(_ROOT, "venv", "bin", "python3")
_FAKE = "999012"
_live_plain = os.path.join(PG.GUARD_BLOCK_DIR, _FAKE + ".json")
_live_pref = os.path.join(PG.GUARD_BLOCK_DIR, "test-" + _FAKE + ".json")
_test_marker = os.path.join(PG.TEST_BLOCK_DIR, "test-" + _FAKE + ".json")
for _p in (_live_plain, _live_pref, _test_marker):
    try:
        os.remove(_p)
    except OSError:
        pass
_env = dict(os.environ, PYTHONPATH=_ROOT, PRETOOL_NOPUSH="1", ORCH_TEST_MODE="1", CC_TASK_ID=_FAKE)
_env.pop(PG.BLOCK_DIR_ENV, None)               # НАРОЧНО без подмены: проверяем УМОЛЧАНИЕ
_real_run([_PY, os.path.join(_ROOT, "tests", "test_pretool_probe_dedup.py")],
          cwd=_ROOT, env=_env, capture_output=True, text=True, timeout=180)
res.append(ok(not os.path.exists(_live_plain) and not os.path.exists(_live_pref),
              f"СКВОЗНОЙ: гард-тест с CC_TASK_ID={_FAKE} не создал НИЧЕГО в боевом каталоге"))
res.append(ok(os.path.exists(_test_marker),
              "СКВОЗНОЙ: маркер ушёл в тест-каталог под именем без номера живой задачи"))
try:
    os.remove(_test_marker)
except OSError:
    pass


# ── (2) run_task: маркер уже есть ДО execute (пост-проверка) ─────────────────
print("(2) run_task: пост-проверка маркера (синхронный гард):")
tmp_guard2 = tempfile.mkdtemp(prefix="guard_esc2_")
_orig_od_dir = OD.GUARD_BLOCK_DIR
OD.GUARD_BLOCK_DIR = tmp_guard2
OD._POPEN = lambda *a, **kw: FakePopen("нет никаких NEEDS_APPROVAL", rc=0)

def _plant_marker(*a, **kw):
    """FakePopen: записать маркер перед возвратом из communicate()."""
    path = os.path.join(tmp_guard2, "99.json")
    with open(path, "w") as f:
        json.dump({"task_id": "99", "hit": "add_transaction", "card": "добавить транзакцию"}, f)

OD._POPEN = lambda *a, **kw: FakePopen("вывод без маркера", rc=0, on_communicate=_plant_marker)
fb = FakeBridge(); OD.bc = fb
st, res_text = OD.run_task(99, "тест-guard-пост", task_timeout=10)
res.append(ok(st == "needs_approval", f"пост-проверка: статус needs_approval (получили: {st!r})"))
res.append(ok("add_transaction" in res_text and "guard-block" in res_text,
              f"needs_approval несёт hit + guard-block: {res_text[:120]!r}"))
res.append(ok("op=other" in res_text, f"op=other в карточке: {res_text[:80]!r}"))
OD.GUARD_BLOCK_DIR = _orig_od_dir
shutil.rmtree(tmp_guard2, ignore_errors=True)


# ── (3) run_task: монитор срабатывает ВО ВРЕМЯ execute (задержка) ────────────
print("(3) run_task: guard-монитор (асинхронный):")
tmp_guard3 = tempfile.mkdtemp(prefix="guard_esc3_")
OD.GUARD_BLOCK_DIR = tmp_guard3

# Детерминизация: вместо time.sleep(0.1) ждём Event, который communicate() выставляет
# перед входом в _killed.wait() — гарантирует запись маркера ПОКА proc ещё «работает»,
# без зависимости от CPU-нагрузки или реального планировщика ОС.
_popen_ref_3 = [None]

def _plant_when_sleeping():
    """Записать маркер ровно когда communicate() вошёл в ожидание — без fixed sleep."""
    proc = _popen_ref_3[0]
    if proc is not None:
        proc.sleeping.wait(timeout=5.0)   # Event, выставляемый FakePopen.communicate()
    path = os.path.join(tmp_guard3, "77.json")
    with open(path, "w") as f:
        json.dump({"task_id": "77", "hit": "closing_upsert", "card": "закрыть booking"}, f)

def _on_start_3():
    threading.Thread(target=_plant_when_sleeping, daemon=True).start()

def _make_popen_3(*a, **kw):
    p = FakePopen("нет маркера", rc=0, sleep_s=0.5, on_communicate=_on_start_3)
    _popen_ref_3[0] = p
    return p

OD._POPEN = _make_popen_3
fb = FakeBridge(); OD.bc = fb

# Уменьшим монитор-интервал до 0.05с для быстрого теста (подменяем функцию)
_orig_monitor = OD._guard_monitor_loop
def _fast_monitor(tid, proc, stop_ev, kill_ev, holder):
    path = OD._guard_marker_path(tid)
    while not stop_ev.wait(0.05):
        if os.path.exists(path):
            data = OD._guard_marker_read(tid)
            holder.append(data or {})
            try: proc.terminate()
            except Exception: pass
            kill_ev.set(); return
OD._guard_monitor_loop = _fast_monitor

st, res_text = OD.run_task(77, "тест-async-guard", task_timeout=10)
OD._guard_monitor_loop = _orig_monitor

res.append(ok(st == "needs_approval", f"async-монитор: needs_approval (получили {st!r})"))
res.append(ok("closing_upsert" in res_text, f"hit в карточке: {res_text[:80]!r}"))
OD.GUARD_BLOCK_DIR = _orig_od_dir
shutil.rmtree(tmp_guard3, ignore_errors=True)


# ── (4) _guard_what: формат карточки ─────────────────────────────────────────
print("(4) _guard_what формат:")
data = {"task_id": "5", "hit": "set_fleet_oil", "card": "масло для байка"}
what = OD._guard_what("5", data)
res.append(ok(what.startswith("op=other | [set_fleet_oil]"), f"op=other | [hit]: {what[:60]!r}"))
res.append(ok("[guard-block задача 5]" in what, f"суффикс guard-block: {what[-40:]!r}"))
res.append(ok("масло для байка" in what, f"card в тексте: {what[:80]!r}"))


# ── (5) регресс: обычные пути не сломаны ─────────────────────────────────────
print("(5) регресс: done/NA_MARKER без маркер-файла:")
tmp_guard5 = tempfile.mkdtemp(prefix="guard_esc5_")
OD.GUARD_BLOCK_DIR = tmp_guard5
# done-задача
OD._POPEN = lambda *a, **kw: FakePopen("сделано без маркера", rc=0)
fb = FakeBridge(); OD.bc = fb
st, r = OD.run_task(50, "обычная задача", task_timeout=10)
res.append(ok(st == "done" and "сделано" in r, f"done: {st!r} / {r[:40]!r}"))

# NA_MARKER (самодекларация) — без guard-маркера
OD._POPEN = lambda *a, **kw: FakePopen(
    f"NEEDS_APPROVAL: op=git_push | нужен push в ветку main", rc=0)
fb = FakeBridge(); OD.bc = fb
st, r = OD.run_task(51, "задача с push", task_timeout=10)
res.append(ok(st == "needs_approval" and "git_push" in r,
              f"NA_MARKER регресс: {st!r} / {r[:60]!r}"))

# failed (exit 1, нет маркера)
OD._POPEN = lambda *a, **kw: FakePopen("падение", rc=1)
fb = FakeBridge(); OD.bc = fb
st, r = OD.run_task(52, "задача что падает", task_timeout=10)
res.append(ok(st == "failed", f"failed-регресс: {st!r} / {r[:40]!r}"))
OD.GUARD_BLOCK_DIR = _orig_od_dir
shutil.rmtree(tmp_guard5, ignore_errors=True)


# ── (6) _guard_what без данных ────────────────────────────────────────────────
print("(6) _guard_what fail-safe (None/пустые данные):")
w1 = OD._guard_what("3", None)
res.append(ok("op=other" in w1 and "[guard-block задача 3]" in w1,
              f"None data → fail-safe строка: {w1[:80]!r}"))
w2 = OD._guard_what("4", {})
res.append(ok("op=other" in w2 and "guard_block" in w2, f"пустые данные → fail-safe: {w2[:80]!r}"))


# ── (7) _guard_marker_clear + _guard_marker_read ──────────────────────────────
print("(7) _guard_marker_clear/_guard_marker_read:")
tmp_guard7 = tempfile.mkdtemp(prefix="guard_esc7_")
OD.GUARD_BLOCK_DIR = tmp_guard7
path7 = OD._guard_marker_path("7")
with open(path7, "w") as f:
    json.dump({"task_id": "7", "hit": "DOWRITE", "card": "тест"}, f)
d7 = OD._guard_marker_read("7")
res.append(ok(d7 == {"task_id": "7", "hit": "DOWRITE", "card": "тест"}, f"read: {d7}"))
OD._guard_marker_clear("7")
res.append(ok(not os.path.exists(path7), "clear удалил файл"))
res.append(ok(OD._guard_marker_read("7") is None, "read несуществующего → None"))
OD._guard_marker_clear("нет такого")   # не роняет
res.append(ok(True, "clear несуществующего → не падает"))
OD.GUARD_BLOCK_DIR = _orig_od_dir
shutil.rmtree(tmp_guard7, ignore_errors=True)


# ── (8) CC_TASK_ID выставлен в child_env ─────────────────────────────────────
print("(8) CC_TASK_ID в child_env:")
CAP = {}
def cap_popen(*a, **kw):
    CAP["env"] = dict(kw.get("env") or {})
    return FakePopen("ок", 0)
OD._POPEN = cap_popen
fb = FakeBridge(); OD.bc = fb
OD.run_task(88, "тест CC_TASK_ID", task_timeout=10)
res.append(ok(CAP.get("env", {}).get("CC_TASK_ID") == "88",
              f"CC_TASK_ID=88 в child_env: {CAP.get('env',{}).get('CC_TASK_ID')!r}"))


# ── финал ─────────────────────────────────────────────────────────────────────
OD._POPEN = _real_POPEN
OD.subprocess.run = _real_run

print(f"\nИТОГ: {'ВСЕ PASS' if all(res) else 'ЕСТЬ FAIL (%d/%d)' % (sum(res), len(res))}")
sys.exit(0 if all(res) else 1)
