"""САМОПОЧИНКА ШАГА декомпозера (мета-дирижёр кусок 1, KB_MASTER §4, 06.07.2026).
Провал шага при STEP_SELFHEAL=1 → думатель (кондуктор, JSON-вердикт) → РОВНО 1 перерождение
с маркером «[самопочинка шага N, попытка 1]»; повторный провал → терминальный halt.
Fail-safe: любой сбой думателя (halt/мусор/таймаут/enqueue-fail) = прежний halt-on-fail.
Сети/Telegram/claude нет — всё мокнуто (FakeBridge в памяти, subprocess.run подменён).
Самотесты обкатки: (А) починимый шаг → retry → цепь дошла; (Б) непочинимый → 1 попытка →
терминальный halt, третьего перерождения НЕТ; (В) цепь без провалов → думатель НЕ зовётся;
(Г) STEP_SELFHEAL=0 → провал = мгновенный halt как раньше."""
import os, sys, datetime, subprocess as _sp
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
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
    def issue_write_ticket(s): return {"ok": True, "ticket": "t"}
    def consume_write_ticket(s, tk): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}
    def by_status(s, status):
        return [r for r in s.rows.values() if r["status"] == status]
    def summaries(s, pid):
        return [r for r in s.rows.values() if r["task_text"].startswith(f"[сводка родитель {pid}]")]
    def heals(s):
        return [r for r in s.rows.values() if "[самопочинка шага" in r["task_text"]]


class FakePopen:
    """Мок _POPEN для claude -p в run_task (планировщик + шаг; НЕ думатель)."""
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode

class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


_real_run = OD.subprocess.run
_real_POPEN = OD._POPEN
_real_MAX_CLAUDE_PROCS = OD.MAX_CLAUDE_PROCS
OD.MAX_CLAUDE_PROCS = 0  # отключить proc-gate в тестах (нет живых claude)

def fake_popen(args, **kw):
    """Мок claude -p через _POPEN: планировщик (plan) + шаги (step_queue)."""
    prompt = args[-1] if args else ""
    if prompt.startswith(OD.PLANNER_PREAMBLE):
        return FakePopen(fake_run.plan_out, 0)
    if fake_run.step_queue:
        out, rc = fake_run.step_queue.pop(0)
        return FakePopen(out, rc)
    return FakePopen("сводка: шаг сделан", 0)

def fake_run(args, **kw):
    """Мок думателя через subprocess.run (думатель идёт через _thinker_exec → subprocess.run)."""
    if args and args[0] == OD.CLAUDE_BIN:
        prompt = args[-1]
        if prompt.startswith(OD.THINKER_PREAMBLE) or prompt.startswith(OD.TASK_THINKER_PREAMBLE):
            fake_run.thinker_calls += 1
            fake_run.thinker_prompts.append(prompt)
            fake_run.thinker_cmds.append(list(args))
            if fake_run.thinker_exc:
                raise fake_run.thinker_exc
            return FakeProc(fake_run.thinker_out)
    return FakeProc("ok")
OD.subprocess.run = fake_run
OD._POPEN = fake_popen


def fresh(selfheal="1", plan="1. шаг один\n2. шаг два"):
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    os.environ["STEP_SELFHEAL"] = selfheal
    fake_run.plan_out = plan
    fake_run.step_queue = []
    fake_run.thinker_calls = 0
    fake_run.thinker_prompts = []
    fake_run.thinker_cmds = []
    fake_run.thinker_out = '{"verdict":"halt","fixed_step":"","reason":"дефолт мока"}'
    fake_run.thinker_exc = None
    return fb


RETRY_JSON = ('{"verdict":"retry","fixed_step":"шаг два: взять ВЕРНЫЙ путь '
              '/root/turbobaby-manager-bot/bot.py и проверить py_compile","reason":"в шаге был неверный путь файла"}')

# (0) юнит: парсер вердикта думателя
print("(0) парсер вердикта:")
res.append(ok(OD._parse_thinker_json(RETRY_JSON)["verdict"] == "retry", "чистый JSON retry"))
res.append(ok(OD._parse_thinker_json("```json\n" + RETRY_JSON + "\n```")["verdict"] == "retry",
              "JSON в markdown-обёртке — терпим"))
res.append(ok(OD._parse_thinker_json('{"verdict":"maybe","fixed_step":"x","reason":"y"}') is None,
              "verdict вне retry|halt → None"))
res.append(ok(OD._parse_thinker_json("не json вовсе") is None, "мусор → None"))
res.append(ok(OD._parse_thinker_json("") is None, "пусто → None"))

# (А) САМОТЕСТ А: починимый провал → думатель retry → перерождение → цепь дошла до конца
print("(А) починимый шаг → retry → цепь дошла:")
fb = fresh(plan="1. первый\n2. второй с кривым путём\n3. третий")
pid = fb.enqueue_task("Filipp-328-dec", "крупное ТЗ: перепиши модуль")["id"]
OD.process_new()                                     # план → 3 шага
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
OD.process_new()                                     # шаг 1 → done
fake_run.step_queue = [("", 1)]                      # шаг 2 упадёт (exit=1, известная починимая причина)
fake_run.thinker_out = RETRY_JSON
OD.process_new()                                     # шаг 2 fail → думатель retry → перерождение
heals = fb.heals()
res.append(ok(fake_run.thinker_calls == 1, "думатель позван ровно 1 раз"))
res.append(ok(len(heals) == 1 and heals[0]["status"] == "new"
              and heals[0]["task_text"].startswith(f"[шаг 2/3 родитель {pid}] [самопочинка шага 2, попытка 1]")
              and "ВЕРНЫЙ путь" in heals[0]["task_text"],
              "перерождение: новая задача с паттерном шага + маркером самопочинки + fixed_step"))
res.append(ok(heals[0]["from"] == "Filipp-328-dec", "перерождение в полосе dec (45 мин таймаут)"))
r2 = fb.rows[s2]
res.append(ok(r2["status"] == "done" and r2["result"].startswith("🩹 шаг 2/3 упал → думатель: retry")
              and "правка:" in r2["result"] and "причина: в шаге был неверный путь файла" in r2["result"],
              "карточка в 328: «шаг N упал → думатель: retry, правка, причина» (done-рапорт devbot)"))
p = fake_run.thinker_prompts[0]
res.append(ok("крупное ТЗ: перепиши модуль" in p and "второй с кривым путём" in p
              and "СУТЬ ПРОВАЛА" in p and "1. первый" in p,
              "промпт думателя: цель родителя дословно + план + упавший шаг + суть провала"))
cmd0 = fake_run.thinker_cmds[0]
res.append(ok("--max-turns" in cmd0 and cmd0[cmd0.index("--max-turns") + 1] == "1"
              and "--model" in cmd0 and "--fallback-model" in cmd0,
              "думатель: чистый генератор (--max-turns 1) через кондуктор --model/--fallback-model"))
OD.process_new()                                     # порядок: перерождённый шаг 2 (не шаг 3!)
res.append(ok(fb.rows[heals[0]["id"]]["status"] == "done" and fb.rows[s3]["status"] == "new",
              "guard порядка: перерождённый шаг 2 исполнен РАНЬШЕ шага 3 (по номеру, не по id)"))
OD.process_new()                                     # шаг 3 → последний → сводка
sums = fb.summaries(pid)
res.append(ok(fb.rows[s3]["status"] == "done" and len(sums) == 1 and "3/3 шагов done" in sums[0]["result"],
              "цепь дошла до конца: сводка 3/3 done (перерождение засчитано, дубля шага 2 нет)"))
res.append(ok(sums[0]["result"].count("шаг 2/3") == 1, "в сводке одна строка на шаг 2 (дедуп)"))
print("  САМОТЕСТ А:", "PASS" if all(res[-8:]) else "FAIL")

# (Б) САМОТЕСТ Б: непочинимый шаг → 1 попытка → терминальный halt, ТРЕТЬЕГО перерождения нет
print("(Б) непочинимый шаг → терминальный halt после 1 попытки:")
fb = fresh(plan="1. первый\n2. второй")
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ с непочинимым шагом")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1), ("", 1)]             # шаг 1 упадёт, перерождение тоже упадёт
fake_run.thinker_out = RETRY_JSON
OD.process_new()                                     # шаг 1 fail → retry → перерождение
heals = fb.heals()
res.append(ok(len(heals) == 1, "перерождение создано (попытка 1)"))
OD.process_new()                                     # перерождение упало ПОВТОРНО → терминальный halt
hid = heals[0]["id"]
res.append(ok(fb.rows[hid]["status"] == "failed"
              and "самопочинка не помогла (попытка 1 исчерпана)" in fb.rows[hid]["result"],
              "повторный провал → терминальный halt с диагнозом"))
res.append(ok(len(fb.heals()) == 1, "ТРЕТЬЕГО перерождения НЕТ (петля невозможна)"))
res.append(ok(fake_run.thinker_calls == 1, "думатель НЕ зовётся на маркированный шаг"))
res.append(ok(fb.rows[s2]["status"] == "failed" and "пропущен" in fb.rows[s2]["result"],
              "хвост цепочки заглушен (halt-on-fail)"))
res.append(ok(len(fb.summaries(pid)) == 1 and "❌" in fb.summaries(pid)[0]["result"],
              "сводка пришла, упавший шаг с ❌"))
print("  САМОТЕСТ Б:", "PASS" if all(res[-6:]) else "FAIL")

# (В) САМОТЕСТ В: цепь без провалов → думатель НЕ зовётся, поведение прежнее
print("(В) цепь без провалов:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "гладкое ТЗ")["id"]
OD.process_new(); OD.process_new(); OD.process_new()
res.append(ok(fake_run.thinker_calls == 0, "думатель не позван ни разу"))
res.append(ok(len(fb.summaries(pid)) == 1 and "2/2 шагов done" in fb.summaries(pid)[0]["result"]
              and not fb.heals(), "цепь как раньше: 2/2 done, перерождений нет"))
print("  САМОТЕСТ В:", "PASS" if all(res[-2:]) else "FAIL")

# (Г) САМОТЕСТ Г: STEP_SELFHEAL=0 → провал = мгновенный halt как раньше (регресса нет)
print("(Г) флаг выключен → прежний halt-on-fail:")
fb = fresh(selfheal="0", plan="1. первый\n2. второй\n3. третий")
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ при выключенном флаге")["id"]
OD.process_new()
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
OD.process_new()                                     # шаг 1 fail → мгновенный halt
res.append(ok(fake_run.thinker_calls == 0, "думатель НЕ позван (флаг 0)"))
res.append(ok(fb.rows[s1]["status"] == "failed" and "🩹" not in fb.rows[s1]["result"]
              and "думатель" not in fb.rows[s1]["result"],
              "шаг 1 failed с прежней карточкой провала (без следов самопочинки)"))
res.append(ok(fb.rows[s2]["status"] == "failed" and fb.rows[s3]["status"] == "failed"
              and not fb.heals() and len(fb.summaries(pid)) == 1
              and "0/3 шагов done" in fb.summaries(pid)[0]["result"],
              "цепочка остановлена и сводка 0/3 — байт-в-байт прежнее поведение"))
print("  САМОТЕСТ Г:", "PASS" if all(res[-3:]) else "FAIL")

# (5) думатель: verdict=halt → терминальный halt С ДИАГНОЗОМ в карточке
print("(5) думатель говорит halt:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = '{"verdict":"halt","fixed_step":"","reason":"нужен доступ, переформулировка не поможет"}'
OD.process_new()
res.append(ok(fb.rows[s1]["status"] == "failed"
              and "думатель: halt, причина: нужен доступ" in fb.rows[s1]["result"]
              and not fb.heals(), "halt-вердикт → терминальный halt, диагноз в карточке, перерождения нет"))
res.append(ok(fb.rows[s2]["status"] == "failed", "хвост цепочки заглушен"))

# (6) fail-safe: мусор-JSON / таймаут думателя / retry без fixed_step / enqueue-fail
print("(6) fail-safe думателя:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = "я не буду отвечать json"
OD.process_new()
res.append(ok(fb.rows[s1]["status"] == "failed" and "думатель" not in fb.rows[s1]["result"]
              and not fb.heals(), "мусор-JSON → прежний halt-on-fail (не хуже текущего)"))

fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_exc = _sp.TimeoutExpired(cmd="claude", timeout=180)
OD.process_new()
res.append(ok(fb.rows[s1]["status"] == "failed" and not fb.heals(),
              "таймаут думателя → прежний halt-on-fail"))

fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = '{"verdict":"retry","fixed_step":"","reason":"retry без правки"}'
OD.process_new()
res.append(ok(fb.rows[s1]["status"] == "failed" and "думатель: halt" in fb.rows[s1]["result"]
              and not fb.heals(), "retry с пустым fixed_step → трактуем как halt"))

fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = RETRY_JSON
_real_enq = FakeBridge.enqueue_task
FakeBridge.enqueue_task = lambda s, frm, txt: {"ok": False, "error": "queue_down"}
OD.process_new()
FakeBridge.enqueue_task = _real_enq
res.append(ok(fb.rows[s1]["status"] == "failed" and not fb.heals(),
              "enqueue перерождения не встал → fail-safe прежний halt"))

# (7) конверт CLI --output-format json вокруг вердикта — распаковывается
print("(7) CLI-конверт:")
import json as _json
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = _json.dumps({"result": RETRY_JSON, "modelUsage": {"fable": {}}})
OD.process_new()
res.append(ok(len(fb.heals()) == 1 and fb.rows[s1]["status"] == "done",
              "вердикт внутри CLI-json-конверта распакован → retry сработал"))

# (8) одиночные «тз:»/«задача:» — ТОЖЕ под самопочинкой (расширение ст4, 07.07.2026);
# детальные сценарии одиночной ветки — tests/test_task_selfheal.py, тут смоук-маршрутизация
print("(8) одиночная задача маршрутизируется в думателя задачи:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "почини рендер")["id"]
fake_run.step_queue = [("", 1)]
fake_run.thinker_out = ('{"verdict":"retry","fixed_task":"почини рендер: верный путь '
                        '/root/turbobaby-manager-bot/bot.py","reason":"кривой путь"}')
OD.process_new()
_reborn8 = [r for r in fb.rows.values() if r["task_text"].startswith("[самопочинка задачи")]
res.append(ok(fake_run.thinker_calls == 1 and fb.rows[tid]["status"] == "done"
              and len(_reborn8) == 1 and _reborn8[0]["status"] == "new",
              "провал «тз:» → думатель задачи → перерождение (расширение ст4)"))

# (9) красный шаг НЕ ослаблен: NEEDS_APPROVAL идёт кнопкой, самопочинка не вмешивается
print("(9) красное не ослаблено:")
fb = fresh()
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ с красным шагом")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.step_queue = [("NEEDS_APPROVAL: op=git_push | нужен push", 0)]
OD.process_new()
res.append(ok(fb.rows[s1]["status"] == "needs_approval" and fake_run.thinker_calls == 0,
              "красный шаг → needs_approval-кнопка как раньше, думатель не зовётся"))

os.environ.pop("STEP_SELFHEAL", None)
OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
