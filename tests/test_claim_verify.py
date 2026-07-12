"""ФИКС КОРНЯ повторных сирот (138 вчера / 146 сегодня, 08.07.2026) — claim-verify.
Инцидент 146: claim долетел сервер-сайд, но echo-слой вернул unauthorized → auth-resend
получил already_claimed от СВОЕГО ЖЕ claim'а → демон пропустил цикл → сирота in_progress
до реапера. Фикс: _claim_task_verified — после клиентского сбоя claim немедленный
verify-GET in_progress своей полосы (vps одно-воркерная = доказательство владения).
Самотесты ТЗ: (а) «claim долетел, ответ потерян» → verify находит мой in_progress →
исполнение, сироты НЕТ; (б) «claim реально не долетел» → verify пуст → штатный пропуск;
(в) регресс: семантические отказы verify не дёргают, сбой verify = пропуск (fail-safe),
чистый claim работает как раньше. Сети/Telegram/claude НЕТ."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")   # изоляция от боевого .env
os.environ.setdefault("STEP_SELFHEAL", "0")
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def iso_ago(sec):
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=sec)
    return t.isoformat()


class FakeBridge:
    """Мост, у которого claim может «сбоить клиентски», реально исполнив claim сервер-сайд."""
    def __init__(s, claim_reply=None, claim_lands=True):
        s.rows, s.nid = {}, 100
        s.claim_reply = claim_reply        # None = честный claim; dict = вернуть это вместо ok
        s.claim_lands = claim_lands        # True = claim исполняется сервер-сайд несмотря на сбой
        s.verify_calls = 0                 # сколько раз читали in_progress (verify-GET)
        s.completed = {}
    def add(s, status, text, age=0, frm="Filipp-328"):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": "", "updated": iso_ago(age)}
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        if "in_progress" in sts and "new" not in sts:
            s.verify_calls += 1
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if s.claim_reply is not None:
            if s.claim_lands and r and r["status"] == "new":
                r["status"] = "in_progress"    # долетел сервер-сайд, ответ потерян/битый
            return dict(s.claim_reply)
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        s.completed[int(tid)] = status
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}


_real_bc, _real_run_task, _real_restart_pending = OD.bc, OD.run_task, OD._restart_pending
OD._restart_pending = lambda: False
ran = []
OD.run_task = lambda tid, text, task_timeout=600, preamble=None: (ran.append(int(tid)) or ("done", "выполнено"))

# (а) claim долетел, ответ потерян (инцидент 146: already_claimed от своего же claim)
print("(а) claim долетел, ответ потерян → verify → исполнение, сироты НЕТ:")
fb = FakeBridge(claim_reply={"ok": False, "error": "already_claimed", "status": "in_progress"},
                claim_lands=True)
OD.bc = fb; ran.clear()
t1 = fb.add("new", "read-only разведка как задача 146")
OD.process_new()
res.append(ok(ran == [t1], f"задача исполнена штатно (run_task зван: {ran})"))
res.append(ok(fb.verify_calls == 1, f"verify-GET in_progress дёрнут ровно 1 раз ({fb.verify_calls})"))
res.append(ok(fb.rows[t1]["status"] == "done", f"итог done, сироты in_progress нет ({fb.rows[t1]['status']})"))

# тот же класс: чистый request_failed (ответ вообще потерян), claim долетел
fb = FakeBridge(claim_reply={"ok": False, "error": "request_failed"}, claim_lands=True)
OD.bc = fb; ran.clear()
t2 = fb.add("new", "задача при потерянном ответе claim")
OD.process_new()
res.append(ok(ran == [t2] and fb.rows[t2]["status"] == "done",
              "request_failed при долетевшем claim → verify → исполнено, done"))

# (б) claim реально НЕ долетел → verify пуст → штатный пропуск цикла
print("(б) claim не долетел → verify пуст → пропуск, задача ждёт в new:")
fb = FakeBridge(claim_reply={"ok": False, "error": "request_failed"}, claim_lands=False)
OD.bc = fb; ran.clear()
t3 = fb.add("new", "задача при реально упавшем claim")
OD.process_new()
res.append(ok(ran == [], "исполнение НЕ стартовало"))
res.append(ok(fb.verify_calls == 1 and fb.rows[t3]["status"] == "new",
              f"verify дёрнут, задача осталась new (возьмётся следующим циклом)"))

# чужой/иной статус: verify видит не-in_progress → пропуск
fb = FakeBridge(claim_reply={"ok": False, "error": "already_claimed", "status": "done"},
                claim_lands=False)
OD.bc = fb; ran.clear()
t4 = fb.add("new", "задача, закрытая мимо демона")
fb.rows[t4]["status"] = "done"   # финализирована кем-то другим (кнопка «нет» и т.п.)
OD._claim_task_verified(t4)
res.append(ok(ran == [] and fb.rows[t4]["status"] == "done",
              "статус иной (done) → claim не присвоен, задача не тронута"))

# (в) регресс-грани
print("(в) регресс:")
# семантический отказ → verify НЕ дёргается
fb = FakeBridge(claim_reply={"ok": False, "error": "not_found"}, claim_lands=False)
OD.bc = fb
r = OD._claim_task_verified(999)
res.append(ok(not r.get("ok") and fb.verify_calls == 0,
              "not_found → verify не дёргается, отказ как раньше"))
# сбой самого verify → fail-safe пропуск, без исключения
class VerifyDead(FakeBridge):
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        if "in_progress" in sts and "new" not in sts:
            s.verify_calls += 1
            raise RuntimeError("bridge down")
        return FakeBridge.get_pending(s, status, lane)
fb = VerifyDead(claim_reply={"ok": False, "error": "request_failed"}, claim_lands=True)
OD.bc = fb
t5 = fb.add("new", "verify сам сбоит")
try:
    r = OD._claim_task_verified(t5)
    res.append(ok(not r.get("ok"), "verify упал → прежний отказ claim (fail-safe), исключение поймано"))
except Exception as e:
    res.append(ok(False, f"сбой verify не должен ронять цикл: {e}"))
# verify вернул ok=false → тоже пропуск
fb = FakeBridge(claim_reply={"ok": False, "error": "request_failed"}, claim_lands=True)
_orig_gp = fb.get_pending
fb.get_pending = lambda status="new", lane=None: {"ok": False, "error": "request_failed"}
OD.bc = fb
t6 = fb.add("new", "verify вернул ошибку")
r = OD._claim_task_verified(t6)
res.append(ok(not r.get("ok"), "verify ok=false → прежний отказ claim (fail-safe)"))
# чистый claim без сбоев — работает как раньше, verify не дёргается
fb = FakeBridge()
OD.bc = fb; ran.clear()
t7 = fb.add("new", "обычная задача")
OD.process_new()
res.append(ok(ran == [t7] and fb.rows[t7]["status"] == "done" and fb.verify_calls == 0,
              "чистый claim → исполнение как раньше, verify не дёргается"))
# claim НЕ внесён в _IDEMPOTENT_POST_ACTIONS (не идемпотентен — только verify)
from bridge_client import BridgeClient
res.append(ok("claim_task" not in BridgeClient._IDEMPOTENT_POST_ACTIONS,
              "claim_task НЕ в _IDEMPOTENT_POST_ACTIONS (слепой re-POST запрещён)"))

OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_restart_pending

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
