"""Моки конверта op=other (O4, 03.07.2026): заявка NEEDS_APPROVAL op=other → «да» Филиппа →
демон НЕ валит failed-отпиской «требуется решение владельца», а конвертирует заявку в обычную headless-задачу
(текст заявки = ТЗ, from=Filipp-328-dev, дев-таймаут) → та исполняется claude -p → done-рапорт.
Исключения: шаг декомпозиции (конверт сломал бы guard цепочки → прежний failed) и сбой enqueue
(честный failed-фоллбэк). Сети/Telegram/claude нет — всё мокнуто."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
os.environ["CARD_DUTY"] = "0"  # изоляция от боевого .env (дежурный по карточкам, фаза 1; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь оркестратора в памяти — контракт как у Bridge (BotData.js)."""
    def __init__(s):
        s.rows, s.nid = {}, 100
        s.enqueue_fail = False
    def enqueue_task(s, frm, txt):
        if s.enqueue_fail:
            return {"ok": False, "error": "bridge_down"}
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new"):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}
    def claim_task(s, tid):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
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
    def approve(s, tid):                       # тестовый шорткат «да N»
        r = s.rows.get(int(tid)); r["status"] = "approved"; r["updated"] = now_iso()
    def task_heartbeat(s, tid): return {"ok": True}
    def issue_write_ticket(s): return {"ok": True, "ticket": "t-test"}
    def consume_write_ticket(s, tk): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}
    def by_status(s, status):
        return [r for r in s.rows.values() if r["status"] == status]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode


_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0  # отключить proc-gate в тестах
_real_run = OD.subprocess.run
def fake_run(args, **kw):
    fake_run.calls.append(args)
    return FakeProc("ok")
fake_run.calls = []
fake_run.out = "сводка: сделано"
def fake_popen(args, **kw):
    fake_run.calls.append(args)
    return FakePopen(fake_run.out)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen


def fresh():
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    return fb


# (1) полный путь: НЕИЗВЕСТНОЕ (не-keyword) op=other → approve → конверт → исполнилась headless → отчёт
#     (headless-невозможное красное — clasp/Лист1/деньги — теперь перехватывает слой 2, см. test_convert_loop_break)
print("(1) op=other (headless-доступное) → approve → конверт → headless done:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "уточни и примени рефакторинг helper в claude_client")["id"]
fake_run.out = "NEEDS_APPROVAL: op=other | нужно решение: применить рефакторинг helper _foo · claude_client.py · смотреть git diff"
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "needs_approval"
              and fb.rows[tid]["result"].startswith("op=other"),
              "красная заявка → needs_approval с дескриптором op=other"))
fb.approve(tid)
OD.process_approved()
orig = fb.rows[tid]
res.append(ok(orig["status"] == "done" and "конвертировано в headless-задачу" in orig["result"],
              "approve → заявка done «конвертировано», НЕ failed-отписка владельцу"))
news = fb.by_status("new")
res.append(ok(len(news) == 1 and news[0]["from"] == "Filipp-328-dev",
              "конверт в очереди, from=Filipp-328-dev (дев-таймаут 45 мин)"))
conv = news[0]
res.append(ok("применить рефакторинг helper" in conv["task_text"]
              and "уточни и примени рефакторинг helper" in conv["task_text"]
              and not conv["task_text"].startswith("op=") and "op=other |" not in conv["task_text"],
              "ТЗ конверта = карточка заявки + исходная задача, префикс op= срезан"))
res.append(ok("NEEDS_APPROVAL" in conv["task_text"] and "обход" in conv["task_text"],
              "ТЗ конверта: красная классификация внутри задачи остаётся (обхода гейта нет)"))
res.append(ok(str(conv["id"]) in orig["result"], "рапорт заявки указывает id конверта"))
res.append(ok(OD._task_timeout(conv) == 2700, "таймаут конверта = 2700с (дев)"))
fake_run.out = "сводка: одобренное выполнено, гейт зелёный"
OD.process_new()
res.append(ok(fb.rows[conv["id"]]["status"] == "done"
              and "одобренное выполнено" in fb.rows[conv["id"]]["result"],
              "конверт исполнился headless → done-отчёт (devbot принесёт в 328)"))

# (2) билет 4.2 на конверт НЕ жжётся (демон красное сам не исполняет)
# read-only проба `systemctl show run-*` (пауза приёма, фикс дыры 48d9c64/122) — НЕ хардкод,
# из запрета исключена; хардкод-исполнители (git push / systemctl restart|is-active) — под запретом.
# ЧИТАЮЩИЙ git исключён ПО ТОЙ ЖЕ ПРИЧИНЕ и по чужому словарю, а не по своему: с 11.08.2026 живой
# счёт серии спрашивает `git log origin/main` о весе цепочки (вес считается по ОПЕРАЦИИ, а не по
# хешу в отчёте). Список читающих подкоманд берётся у `prod_drift.GIT_READ` — того самого места,
# где он и стережётся; писать здесь второй список значит завести расхождение.
print("(2) конверт без билета/хардкода:")
import prod_drift as _PD                                              # noqa: E402
_ro = [a for a in fake_run.calls if a and a[0] == "git" and list(a[1:2]) and a[1] in _PD.GIT_READ]
res.append(ok(not any(a and ((a[0] == "git" and (not list(a[1:2]) or a[1] not in _PD.GIT_READ))
                             or (a[0] == "systemctl" and list(a[1:2]) != ["show"]))
                      for a in fake_run.calls),
              "хардкод-команды (git push / systemctl restart) при конверте не звались "
              "(читающих git-проб веса: %d)" % len(_ro)))

# (3) шаг декомпозиции: конверт запрещён (guard цепочки) → прежний failed + halt
print("(3) шаг декомпозиции op=other → прежний failed:")
fb = fresh()
p = 55
s1 = fb.enqueue_task("Filipp-328-dec", f"[шаг 1/2 родитель {p}] красный шаг")["id"]
s2 = fb.enqueue_task("Filipp-328-dec", f"[шаг 2/2 родитель {p}] обычный шаг")["id"]
fb.rows[s1]["status"] = "needs_approval"; fb.rows[s1]["result"] = "op=other | записать в Лист1"
fb.approve(s1)
OD.process_approved()
res.append(ok(fb.rows[s1]["status"] == "failed" and "решение владельца" in fb.rows[s1]["result"]
              and "328" in fb.rows[s1]["result"],
              "шаг декомпозиции op=other → failed (конверта нет, формулировка «решение владельца»)"))
res.append(ok(fb.rows[s2]["status"] == "failed" and "пропущен" in fb.rows[s2]["result"],
              "halt-on-fail: сиблинг пропущен, цепочка остановлена"))
res.append(ok(all(r["from"] != "Filipp-328-dev" for r in fb.rows.values()),
              "конверт-задача для шага НЕ создана"))

# (4) enqueue упал → честный failed-фоллбэк (заявка не теряется молча)
print("(4) сбой enqueue при конверте:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328", "быстрая задача")["id"]
fb.rows[tid]["status"] = "needs_approval"; fb.rows[tid]["result"] = "op=other | что-то красное"
fb.approve(tid)
fb.enqueue_fail = True
OD.process_approved()
res.append(ok(fb.rows[tid]["status"] == "failed" and "не встал в очередь" in fb.rows[tid]["result"]
              and "решение владельца" in fb.rows[tid]["result"],
              "enqueue не прошёл → failed с фоллбэком «требуется решение владельца»"))

# (5) AUTO_OPS-путь не задет: op=git_push после approve по-прежнему хардкод.
# ЗАМОК ПРОИСХОЖДЕНИЯ (31.07.2026): исполнимый класс признаётся ТОЛЬКО у карточки, рождённой
# сверенным маркером гарда, поэтому фикстура несёт гардовый штамп — так её и рождает демон.
# Заявка исполнителя с тем же op=git_push (и легаси-строка без штампа) хардкод НЕ запускает —
# это проверяет tests/test_card_origin.py секция (4).
print("(5) op∈AUTO_OPS без изменений:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "задача с push")["id"]
fb.rows[tid]["status"] = "needs_approval"
fb.rows[tid]["result"] = f"op=git_push | нужен push\n{OD.ORIGIN_GUARD_TOKEN} — перехвачена команда"
fb.approve(tid)
fake_run.calls = []
OD.process_approved()
res.append(ok(fb.rows[tid]["status"] == "done" and any(a and a[0] == "git" for a in fake_run.calls),
              "op=git_push (гардовая карточка) → хардкод git push, конверт не вмешался"))
res.append(ok(OD.AUTO_OPS == ("git_push", "restart_splinter"), "AUTO_OPS не расширены"))

OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
