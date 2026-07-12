"""ФИКС КЛАССА инцидента 07.07.2026 (задача 138) — сторона ДЕМОНА.
Инцидент: Bridge-сбой (404 на redirect-echo) → claim долетел сервер-сайд при клиентском
request_failed → задача застряла в in_progress навсегда (heartbeat мёртв, исполнителя нет).
Самотесты ТЗ: (а) мок висящего claude → таймаут-failed с ⏱-маркером, heartbeat тикает ВСЁ время
исполнения независимым потоком и глохнет после; (б) думатель ⏱-провалы НЕ чинит (обычные — чинит
как раньше); (в) реапер сирот: старый vps-in_progress → честный failed, свежий/pc/new — нетронуты,
сбой чтения → ничего; сирота-шаг декомпозера дёргает хук цепи; (г) cycle() зовёт реапер ПЕРВЫМ;
(д) таймауты конфигурируемы из .env (_env_int, мусор → дефолт). Сети/Telegram/claude НЕТ."""
import os, sys, time, datetime, threading
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")   # изоляция от боевого .env
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def iso_ago(sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=sec)
    return t.isoformat()


class FakeBridge:
    def __init__(s):
        s.rows, s.nid, s.hb = {}, 100, 0
    def add(s, status, text, lane=None, age=0, frm="Filipp-328-dev"):
        s.nid += 1
        r = {"id": s.nid, "from": frm, "task_text": text, "status": status,
             "result": "", "updated": iso_ago(age)}
        if lane is not None:
            r["lane"] = lane
        s.rows[s.nid] = r
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, txt):
        return {"ok": True, "id": s.add("new", txt, frm=frm)}
    def task_heartbeat(s, tid):
        s.hb += 1
        return {"ok": True}


_real_bc, _real_run, _real_hb = OD.bc, OD.subprocess.run, OD.HEARTBEAT_SEC

# (а) висящий claude → subprocess-таймаут → честный failed с ⏱; heartbeat жив всё время
print("(а) таймаут висящего claude + независимый heartbeat:")
fb = FakeBridge()
OD.bc = fb
OD.HEARTBEAT_SEC = 0.05

def hang_run(args, **kw):
    time.sleep(0.5)                       # «висит» — heartbeat в это время обязан тикать
    raise OD.subprocess.TimeoutExpired(cmd="claude", timeout=kw.get("timeout"))

OD.subprocess.run = hang_run
st, out = OD.run_task(1, "тз которое повисло", task_timeout=1)
hb_at_end = fb.hb
time.sleep(0.2)                           # поток должен быть остановлен → счётчик замер
res.append(ok(st == "failed" and out.startswith(OD.TIMEOUT_MARK) and "таймаут" in out,
              f"таймаут → честный failed с ⏱-маркером ({out[:60]!r})"))
res.append(ok(hb_at_end >= 3, f"heartbeat тикал независимо всё время исполнения ({hb_at_end} тиков)"))
res.append(ok(fb.hb == hb_at_end, "после kill heartbeat-поток остановлен (счётчик замер)"))
res.append(ok(threading.active_count() < 20, "потоки не текут"))
OD.subprocess.run = _real_run
OD.HEARTBEAT_SEC = _real_hb

# (б) думатель ⏱-провалы НЕ чинит; обычный провал — идёт в думатель как раньше
print("(б) гейт ⏱ в самопочинке:")
os.environ["STEP_SELFHEAL"] = "1"
thinker_calls = []
_real_thinker = OD._thinker_exec
OD._thinker_exec = lambda prompt, timeout, tag: thinker_calls.append(tag) or None
fb = FakeBridge(); OD.bc = fb
r1 = OD._maybe_selfheal(5, "обычная одиночная задача", f"{OD.TIMEOUT_MARK} таймаут задачи 600s — claude -p убит",
                        frm="Filipp-328-dev")
res.append(ok(r1 is False and not thinker_calls, "⏱-таймаут → думатель НЕ зван, голый failed"))
r2 = OD._maybe_selfheal(5, "обычная одиночная задача", "claude -p упал (exit=1): сломалось",
                        frm="Filipp-328-dev")
res.append(ok(len(thinker_calls) == 1, "обычный провал → думатель зван как раньше (регресс)"))
OD._thinker_exec = _real_thinker
os.environ.pop("STEP_SELFHEAL", None)

# (в) реапер сирот in_progress
print("(в) process_orphans:")
fb = FakeBridge(); OD.bc = fb
orphan = fb.add("in_progress", "мини-ревизия как задача 138", age=2000)          # сирота vps
fresh = fb.add("in_progress", "только что взятая", age=30)                       # свежая — не трогать
pc = fb.add("in_progress", "[шаг 1/2 родитель 9] шаг ПК", lane="pc", age=9000)   # полоса pc — не трогать
new = fb.add("new", "ждёт очереди", age=9000)                                     # new — не трогать
OD.process_orphans()
r = fb.rows
res.append(ok(r[orphan]["status"] == "failed" and r[orphan]["result"].startswith(OD.TIMEOUT_MARK)
              and "сирота" in r[orphan]["result"],
              f"сирота (updated {2000}с назад) → честный failed с ⏱-диагнозом"))
res.append(ok(r[fresh]["status"] == "in_progress", "свежий in_progress (< ORPHAN_TTL) не тронут"))
res.append(ok(r[pc]["status"] == "in_progress", "полоса pc не тронута (надзор PC_STEP_TIMEOUT)"))
res.append(ok(r[new]["status"] == "new", "new не тронут"))

# сирота-шаг декомпозера → хук цепи (halt-on-fail) дёрнут
dec_calls = []
_real_dec_after = OD._maybe_dec_after
OD._maybe_dec_after = lambda text, status: dec_calls.append((text[:30], status))
fb = FakeBridge(); OD.bc = fb
step = fb.add("in_progress", "[шаг 2/3 родитель 44] застрявший шаг", age=2000, frm="Filipp-328-dec")
OD.process_orphans()
res.append(ok(fb.rows[step]["status"] == "failed" and dec_calls and dec_calls[0][1] == "failed",
              "сирота-шаг декомпозера → failed + хук цепи (halt-on-fail)"))
OD._maybe_dec_after = _real_dec_after

# сбой чтения → реапер молчит (fail-safe)
class DeadBridge:
    def get_pending(s, status="new", lane=None): return {"ok": False, "error": "request_failed"}
OD.bc = DeadBridge()
try:
    OD.process_orphans()
    res.append(ok(True, "сбой get_pending → реапер тихо ждёт следующего цикла"))
except Exception as e:
    res.append(ok(False, f"сбой get_pending не должен ронять цикл: {e}"))

# (г) cycle() зовёт реапер ПЕРВЫМ
print("(г) порядок cycle():")
order = []
_saved = (OD.process_orphans, OD.process_approved, OD.process_dec_tails, OD.process_pc_chains, OD.process_new)
OD.process_orphans = lambda: order.append("orphans")
OD.process_approved = lambda: order.append("approved")
OD.process_dec_tails = lambda: order.append("dec_tails")
OD.process_pc_chains = lambda: order.append("pc_chains")
OD.process_new = lambda: order.append("new")
OD.cycle()
(OD.process_orphans, OD.process_approved, OD.process_dec_tails, OD.process_pc_chains, OD.process_new) = _saved
res.append(ok(order == ["orphans", "approved", "dec_tails", "pc_chains", "new"],
              f"cycle: реапер сирот первым, остальное как было ({order})"))

# (д) таймауты из .env: _env_int (мусор/пусто/отрицательное → дефолт)
print("(д) _env_int:")
os.environ["_T_X"] = "123"
res.append(ok(OD._env_int("_T_X", 5) == 123, "число из env читается"))
os.environ["_T_X"] = "мусор"
res.append(ok(OD._env_int("_T_X", 5) == 5, "мусор → дефолт"))
os.environ["_T_X"] = "-7"
res.append(ok(OD._env_int("_T_X", 5) == 5, "отрицательное → дефолт"))
os.environ.pop("_T_X", None)
res.append(ok(OD._env_int("_T_X", 5) == 5, "нет переменной → дефолт"))
res.append(ok(isinstance(OD.TASK_TIMEOUT, int) and isinstance(OD.TASK_TIMEOUT_DEV, int)
              and isinstance(OD.ORPHAN_TTL, int),
              f"константы собраны (TASK_TIMEOUT={OD.TASK_TIMEOUT}, DEV={OD.TASK_TIMEOUT_DEV}, "
              f"ORPHAN_TTL={OD.ORPHAN_TTL})"))

OD.bc = _real_bc
OD.subprocess.run = _real_run

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
