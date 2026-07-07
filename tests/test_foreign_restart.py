"""ФИКС ДЫРЫ класса 48d9c64 (урок задачи 122, 07.07.2026): признаки планового рестарта не
отличали СВОЙ рестарт от ЧУЖОГО — задача, взятая в окно чужого отложенного рестарта демона,
гибла на СТАРТЕ и ложно закрывалась done+🔁 («фантомный done», работа терялась). Два слоя:
(1) ПРОФИЛАКТИКА: process_new не берёт new-задачи, пока systemd-run-единица рестарта ЖИВА
    (ActiveState active/activating) — «пауза приёма»; мёртвый/failed остов паузы НЕ даёт.
(2) ДЕТЕКТ: run_task сравнивает monotonic-время создания единицы со стартом claude задачи:
    создана ДО старта = ЧУЖОЙ → возврат в new (клон дословно, исходная done+🔄, думатель не
    дёргается); ПОСЛЕ старта / времени не видно = прежний путь 48d9c64 (done+🔁 / failed).
Сети/Telegram/claude нет — всё мокнуто."""
import os, sys, time, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"       # изоляция от боевого .env
os.environ["STEP_SELFHEAL"] = "0"    # думатель в этих тестах не участвует вовсе
os.environ.setdefault("PRETOOL_NOPUSH", "1")   # ноль пушей и при ручном прогоне вне гейта

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    def __init__(s):
        s.rows, s.nid, s.enqueue_fail = {}, 100, False
    def enqueue_task(s, frm, txt, lane=None):
        if s.enqueue_fail:
            return {"ok": False, "error": "queue_down"}
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed"}
        r["status"] = "in_progress"; r["updated"] = now_iso()
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def by_status(s, status):
        return [r for r in s.rows.values() if r["status"] == status]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


def _show_block(unit, state, enter_usec, exit_usec=0):
    return (f"Id={unit}\n"
            f"Description=/usr/bin/systemctl restart orchestrator-daemon\n"
            f"ActiveState={state}\n"
            f"ActiveEnterTimestampMonotonic={enter_usec}\n"
            f"InactiveExitTimestampMonotonic={exit_usec}\n")


# единица создана «давно» (1-я секунда после boot) — заведомо ДО любого старта claude в тесте
SHOW_PAST = (_show_block("run-r1.timer", "active", 1_000_000, 1_000_000) + "\n" +
             _show_block("run-r1.service", "inactive", 0, 0))
# мёртвый failed-остов старой единицы: виден, но НЕ жив (паузу давать не должен)
SHOW_DEAD = _show_block("run-r0.service", "failed", 1_000_000, 1_000_000)
# легаси-формат list-units (старый мок 48d9c64): виден, времени/состояния нет
LEGACY_LINE = ("run-r4242.service loaded active running "
               "/usr/bin/systemctl restart orchestrator-daemon")

def show_future():
    """Единица создана в «будущем» (после текущего момента) = ПОСЛЕ старта claude = СВОЙ рестарт."""
    fut = int((time.monotonic() + 3600) * 1e6)
    return _show_block("run-r2.timer", "active", fut, fut)


SELFMOD_TEXT = ("тз: фикс класса — правка orchestrator_daemon.py, в конце отложенный "
                "systemd-run restart демона")
PLAIN_TEXT = "тз: поправь опечатку в prompts.py и прогони тесты"

_real_run = OD.subprocess.run
def fake_run(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN:
        fake_run.claude_calls += 1
        if fake_run.claude_queue:
            out, rc = fake_run.claude_queue.pop(0)
            return FakeProc(out, rc)
        return FakeProc("сводка: сделано")
    if args and args[0] == "systemctl":
        fake_run.probe_calls += 1
        if fake_run.probe_exc:
            raise fake_run.probe_exc
        if fake_run.probe_queue:
            return FakeProc(fake_run.probe_queue.pop(0))
        return FakeProc(fake_run.probe_out)
    return FakeProc("ok")
OD.subprocess.run = fake_run

_prev_running = OD._running


def fresh(probe_out="", running=False):
    fb = FakeBridge()
    OD.bc = fb
    OD._running = running
    fake_run.claude_queue, fake_run.claude_calls = [], 0
    fake_run.probe_out, fake_run.probe_queue = probe_out, []
    fake_run.probe_exc, fake_run.probe_calls = None, 0
    return fb


# (1) юнит: проба _restart_probe (visible/pending/earliest)
print("(1) проба _restart_probe:")
fresh(probe_out=SHOW_PAST)
v, p, e = OD._restart_probe()
res.append(ok(v and p and e == 1.0, "живой таймер → visible+pending, earliest=создание (1.0с)"))
fresh(probe_out=SHOW_DEAD)
v, p, e = OD._restart_probe()
res.append(ok(v and not p and e == 1.0, "failed-остов → visible, но НЕ pending (пауза не залипнет)"))
fresh(probe_out=LEGACY_LINE)
v, p, e = OD._restart_probe()
res.append(ok(v and not p and e is None, "легаси-строка list-units → visible, времени/паузы нет"))
fresh(probe_out="")
res.append(ok(OD._restart_probe() == (False, False, None), "пусто → (False, False, None)"))
fresh()
fake_run.probe_exc = OSError("systemctl недоступен")
res.append(ok(OD._restart_probe() == (False, False, None), "сбой пробы → (False, False, None), fail-safe"))

def killed():
    """claude задачи убит SIGTERM (exit=143) — гибель под рестартом."""
    fake_run.claude_queue = [("", 143)]


# (2) ДЕТЕКТ ЧУЖОГО (слой 2): единица старше старта claude → requeue, даже с самомод-ТЗ
print("(2) чужой рестарт → requeue (возврат в new):")
fresh(probe_out=SHOW_PAST); killed()
st, out = OD.run_task(1, PLAIN_TEXT)
res.append(ok(st == "requeue" and "ЧУЖОГО" in out and "НЕ выполнялась" in out,
              "обычная задача, убитая чужим рестартом → requeue (не failed: думатель не нужен)"))
fresh(probe_out=SHOW_PAST); killed()
st, out = OD.run_task(1, SELFMOD_TEXT)
res.append(ok(st == "requeue" and "ЧУЖОГО" in out,
              "самомод-ТЗ под ЧУЖИМ рестартом → requeue, НЕ ложный done+🔁 (сама дыра 122)"))

# (3) СВОЙ рестарт (единица создана ПОСЛЕ старта claude) → done+🔁 как в 48d9c64
print("(3) свой рестарт → done+🔁:")
fresh(probe_out=show_future()); killed()
st, out = OD.run_task(2, SELFMOD_TEXT)
res.append(ok(st == "done" and "плановым рестартом" in out,
              "единица моложе старта + самомод-ТЗ → done+🔁 (регресс 48d9c64 цел)"))
fresh(probe_out=show_future()); killed()
st, out = OD.run_task(2, PLAIN_TEXT)
res.append(ok(st == "failed", "единица моложе старта, но ТЗ без самомод-признака → честный failed"))

# (4) fail-safe времени: метки не видны → прежнее поведение 48d9c64 байт-в-байт
print("(4) сомнение во времени → прежнее поведение:")
fresh(probe_out=LEGACY_LINE); killed()
st, out = OD.run_task(3, SELFMOD_TEXT)
res.append(ok(st == "done" and "плановым рестартом" in out, "времени нет + самомод-ТЗ → done+🔁"))
fresh(probe_out=LEGACY_LINE); killed()
st, out = OD.run_task(3, PLAIN_TEXT)
res.append(ok(st == "failed", "времени нет + обычное ТЗ → честный failed"))

# (5) e2e САМОТЕСТ б: чужой рестарт на старте → задача вернулась в new и исполнилась после рестарта
print("(5) e2e: возврат в new + исполнение после рестарта:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", PLAIN_TEXT)["id"]
fake_run.probe_queue = ["", SHOW_PAST]      # пауза-проба единицу ещё не видит (гонка), детект — видит
fake_run.claude_queue = [("", 143)]         # claude убит SIGTERM чужим рестартом на старте
OD.process_new()
clones = [r for r in fb.by_status("new")]
orig = fb.rows[tid]
res.append(ok(orig["status"] == "done" and "ЧУЖОГО" in orig["result"] and "Возвращена в очередь" in orig["result"],
              "исходная закрыта done с маркер-картой 🔄 (не failed, не фантомный 🔁)"))
res.append(ok(len(clones) == 1 and clones[0]["task_text"] == PLAIN_TEXT
              and clones[0]["from"] == "Filipp-328-dev",
              "клон в new: текст ДОСЛОВНО, полоса from та же"))
# «после рестарта»: демон свежий, единицы нет → клон исполняется штатно
OD._running = False
fake_run.probe_out, fake_run.probe_queue = "", []
fake_run.claude_queue = [('{"result":"сводка: сделано после рестарта","modelUsage":{"m":{}}}', 0)]
OD.process_new()
cl = fb.rows[clones[0]["id"]]
res.append(ok(cl["status"] == "done" and cl["result"] == "сводка: сделано после рестарта",
              "клон исполнился после рестарта → работа НЕ потеряна"))

# (6) e2e САМОТЕСТ в: pending-единица → пауза приёма; единица ушла → очередь пошла
print("(6) пауза приёма при живой единице рестарта:")
fb = fresh(probe_out=SHOW_PAST)
tid = fb.enqueue_task("Filipp-328", "задача: проверь логи")["id"]
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "new" and fake_run.claude_calls == 0,
              "живая единица → задача НЕ взята (ждёт в new), claude не звался"))
fake_run.probe_out = ""                     # «после рестарта»: единицы больше нет
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "done" and fake_run.claude_calls == 1,
              "единица ушла → очередь пошла, задача исполнена"))
fb = fresh(probe_out=SHOW_DEAD)             # мёртвый остов паузу НЕ даёт
tid = fb.enqueue_task("Filipp-328", "задача: проверь логи")["id"]
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "done", "failed-остов единицы → приём НЕ заморожен"))

# (7) чужой рестарт на шаге декомпозера: клон сохраняет маркер [шаг i/N], цепь не глушится
print("(7) дек-шаг под чужим рестартом:")
fb = fresh()
step_text = "[шаг 1/2 родитель 42] сделай раз"
tid = fb.enqueue_task("Filipp-328-dec", step_text)["id"]
fake_run.probe_queue = ["", SHOW_PAST]
fake_run.claude_queue = [("", 143)]
OD.process_new()
clones = fb.by_status("new")
res.append(ok(fb.rows[tid]["status"] == "done" and len(clones) == 1
              and clones[0]["task_text"] == step_text and clones[0]["from"] == "Filipp-328-dec",
              "шаг вернулся в new дословно (маркер цепи цел), исходный done+🔄 — думатель не звался"))

# (8) fail-safe возврата: клон не встал в очередь → честный failed (задача не теряется молча)
print("(8) клон не встал → честный failed:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", PLAIN_TEXT)["id"]
fake_run.probe_queue = ["", SHOW_PAST]
fake_run.claude_queue = [("", 143)]
fb.enqueue_fail = True
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "failed" and "повтори задачу" in fb.rows[tid]["result"],
              "очередь не приняла клон → failed с диагнозом (не молчаливая потеря)"))

OD._running = _prev_running
OD.subprocess.run = _real_run

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
