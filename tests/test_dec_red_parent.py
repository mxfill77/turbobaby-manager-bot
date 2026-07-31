"""Фикс UX декомпозера (урок задачи 166): red-маркеры в тексте РОДИТЕЛЯ не валят декомпозицию
на этапе планирования — план строится всегда; красная классификация применяется к ОТДЕЛЬНЫМ
шагам (красный шаг → кнопка при исполнении, существующая механика); фейл-сейф: ВЕСЬ смысл
родителя = одно красное действие → прежний честный отказ. Сети/Telegram/claude нет — всё
мокнуто (FakeBridge = очередь в памяти, subprocess.run подменён)."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"      # изоляция от боевого .env (адаптация плана после done-шагов)
os.environ["STEP_SELFHEAL"] = "0"   # изоляция от думателя самопочинки
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
os.environ["THEATER_ROUTER"] = "0"  # изоляция от роутера театра: легаси-поведение 328

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь оркестратора в памяти — контракт как у Bridge (BotData.js)."""
    def __init__(s):
        s.rows, s.nid = {}, 100
    def enqueue_task(s, frm, txt):
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
    def task_heartbeat(s, tid): return {"ok": True}
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


_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0  # отключить proc-gate в тестах (real /proc видит claude)
def fake_run(args, **kw):
    return FakeProc("ok")   # git / systemctl (claude идёт через _POPEN)
def fake_popen(args, **kw):
    prompt = args[-1] if args else ""
    if prompt.startswith(OD.PLANNER_PREAMBLE):
        return FakePopen(fake_run.plan_out)
    return FakePopen(fake_run.step_out)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen
fake_run.step_out = "сводка: шаг сделан"


def fresh():
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    return fb


# (1) урок 166 в лоб: родитель со clasp-словом в одной из частей — план строится,
# красный шаг помечен в карточке, текст шагов в очереди чист (без 🔴)
print("(1) родитель с red-маркером в части → план построен, красный шаг помечен:")
fb = fresh()
fake_run.plan_out = ("1. поправить splinter.py карточку приёма\n"
                     "2. тесты и гейт\n"
                     "3. clasp redeploy Bridge (прод-деплой)")
pid = fb.enqueue_task("Filipp-328-dec", "O3-xx: часть А код, часть Б clasp redeploy Bridge")["id"]
OD.process_new()
parent = fb.rows[pid]
res.append(ok(parent["status"] == "done" and "🧩 Декомпозиция: 3 шагов" in parent["result"],
              "родитель done, план построен (red-маркер в ТЗ не валит планирование)"))
res.append(ok("🔴 красные шаги: 3" in parent["result"],
              "красный шаг 3 помечен в карточке плана"))
news = sorted(fb.by_status("new"), key=lambda r: r["id"])
res.append(ok(len(news) == 3 and news[2]["task_text"] == f"[шаг 3/3 родитель {pid}] clasp redeploy Bridge (прод-деплой)"
              and all("🔴" not in r["task_text"] for r in news),
              "3 шага в очереди, текст шагов чист (пометка только в дисплее плана)"))

# (2) планировщик самодекларировал NEEDS_APPROVAL, но план всё же дал → план побеждает
print("(2) NA-маркер в выводе планировщика РЯДОМ с планом → план побеждает:")
fb = fresh()
fake_run.plan_out = ("NEEDS_APPROVAL: op=clasp_redeploy (деплой Bridge владельцем)\n"
                     "1. править код\n2. деплой Bridge")
pid = fb.enqueue_task("Filipp-328-dec", "правки + деплой")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "done" and "🧩 Декомпозиция: 2 шагов" in fb.rows[pid]["result"],
              "NA-строка не глушит распарсенный план"))

# (3) фоллбэк-фраза («требует подтверждения») в тексте шага плана не валит декомпозицию
print("(3) фоллбэк-фраза NA в тексте шага → план построен:")
fb = fresh()
fake_run.plan_out = "1. править код\n2. деплой Bridge — требует подтверждения Филиппа кнопкой"
pid = fb.enqueue_task("Filipp-328-dec", "правки + деплой")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "done" and "🧩 Декомпозиция: 2 шагов" in fb.rows[pid]["result"],
              "фоллбэк-фраза в шаге не превращает план в needs_approval"))

# (4) фейл-сейф: чисто-красный родитель (планировщик дал ТОЛЬКО NA-строку) → отказ как раньше
print("(4) чисто-красный родитель → прежний честный отказ:")
fb = fresh()
fake_run.plan_out = "NEEDS_APPROVAL: op=other | задеплой прод — одно красное действие, разбивать нечего"
pid = fb.enqueue_task("Filipp-328-dec", "задеплой прод")["id"]
OD.process_new()
parent = fb.rows[pid]
res.append(ok(parent["status"] == "failed" and "планировщик needs_approval" in parent["result"]
              and "задеплой прод" in parent["result"],
              "плана нет + NA-маркер → failed «планировщик needs_approval» (как раньше)"))
res.append(ok(not fb.by_status("new"), "шаги в очередь не встали"))

# (5) регресс: NA-детект ЖИВ вне планировщика — красный ШАГ при исполнении даёт кнопку
print("(5) регресс: красный шаг при исполнении → needs_approval (кнопка):")
fb = fresh()
fake_run.plan_out = "1. код\n2. деплой"
pid = fb.enqueue_task("Filipp-328-dec", "код + деплой")["id"]
OD.process_new()                                   # план → 2 шага
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
# живой формат самодекларации (31.07.2026): исполнитель выводит ТОЛЬКО «op=other» (git push и
# рестарт своих сервисов — оранжевый цикл, маркер запрещён преамбулой). Заявка с ИСПОЛНИМЫМ
# классом карточки не рождает — замок происхождения, tests/test_card_origin.py.
fake_run.step_out = "NEEDS_APPROVAL: op=other | запись в CRM · строка 12 · смотреть лист"
OD.process_new()                                   # шаг 1 красный
res.append(ok(fb.rows[s1]["status"] == "needs_approval",
              "красный шаг → needs_approval (существующая механика кнопки цела)"))
fake_run.step_out = "сводка: шаг сделан"
OD.process_new()
res.append(ok(fb.rows[s2]["status"] == "new", "guard последовательности цел (шаг 2 ждёт)"))

# (6) регресс: план без красных шагов → пометки 🔴 нет; мусор без списка → прежний failed
print("(6) регресс чистого плана и мусора:")
fb = fresh()
fake_run.plan_out = "1. шаг один\n2. шаг два"
pid = fb.enqueue_task("Filipp-328-dec", "обычное ТЗ")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "done" and "🔴" not in fb.rows[pid]["result"],
              "нет красных шагов → нет пометки 🔴"))
fb = fresh()
fake_run.plan_out = "не могу, нет списка"
pid = fb.enqueue_task("Filipp-328-dec", "мутное ТЗ")["id"]
OD.process_new()
res.append(ok(fb.rows[pid]["status"] == "failed" and "не вернул нумерованный список" in fb.rows[pid]["result"],
              "мусор без списка и без NA → прежний failed"))

# (7) хелпер и преамбула
print("(7) хелпер пометки и преамбула планировщика:")
# СУЖЕНО 25.07.2026: пометка идёт по ИМЕНИ ОПЕРАЦИИ, «запись в CRM» — тема, а не операция.
res.append(ok(OD._dec_red_note(["код", "clasp redeploy", "тесты", "delete_event(id) в календаре"]).startswith("🔴 красные шаги: 2, 4"),
              "_dec_red_note: находит красные шаги по номерам"))
res.append(ok(OD._dec_red_note(["код", "тесты"]) == "", "_dec_red_note: чистый план → пустая строка"))
res.append(ok(all(OD._PLAN_LINE_RE.match(ln) is None
                  for ln in OD._dec_red_note(["clasp redeploy"]).splitlines()),
              "пометка не матчит _PLAN_LINE_RE (restart-proof парс плана из result цел)"))
res.append(ok("НЕ ПОВОД ОТКАЗЫВАТЬСЯ" in OD.PLANNER_PREAMBLE and "ОТДЕЛЬНЫМ шагом" in OD.PLANNER_PREAMBLE
              and OD.PLANNER_PREAMBLE.rstrip().endswith("КРУПНОЕ ТЗ:"),
              "преамбула: запрет отказа + красное отдельным шагом; «КРУПНОЕ ТЗ:» осталось хвостом"))

OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS
n_fail = sum(1 for r in res if not r)
print(f"\nИтог: {len(res) - n_fail}/{len(res)} PASS")
sys.exit(1 if n_fail else 0)
