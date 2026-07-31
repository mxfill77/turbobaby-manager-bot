"""САМОПОЧИНКА ОДИНОЧНОЙ ЗАДАЧИ «тз:»/«задача:» (мета-дирижёр, расширение ст4, 07.07.2026).
Провал одиночной задачи при STEP_SELFHEAL=1 → думатель (тот же кондуктор, строгий JSON
retry/halt + fixed_task + reason; контекст: текст задачи дословно + суть провала) → РОВНО 1
перерождение с маркером «[самопочинка задачи N, попытка 1]»; повторный провал маркированной =
терминальный failed с диагнозом. Fail-safe: любой сбой думателя = прежний голый failed.
Сети/Telegram/claude нет — всё мокнуто (FakeBridge в памяти, subprocess.run подменён).
Самотесты ТЗ: (а) починимый провал → retry → перерождение done; (б) непочинимый → 1 попытка →
терминальный failed с диагнозом, третьего перерождения НЕТ; (в) плановый рестарт самомод-задачи →
done с пометкой, думатель НЕ звался; (г) STEP_SELFHEAL=0 → голый failed как раньше."""
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
    def heals(s):
        return [r for r in s.rows.values() if r["task_text"].startswith("[самопочинка задачи")]


class FakePopen:
    """Мок _POPEN для claude -p в run_task (исполнитель задачи, НЕ думатель)."""
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
    """Мок claude -p через _POPEN: исполнитель задачи (run_task). task_queue на fake_run."""
    if fake_run.task_queue:
        out, rc = fake_run.task_queue.pop(0)
        return FakePopen(out, rc)
    return FakePopen("сделано", 0)

def fake_run(args, **kw):
    """Мок systemctl + думатель через subprocess.run (думатель идёт через subprocess.run, НЕ _POPEN)."""
    if args and args[0] == "systemctl":
        return FakeProc(fake_run.systemd_units)
    if args and args[0] == OD.CLAUDE_BIN:
        prompt = args[-1]
        if prompt.startswith(OD.TASK_THINKER_PREAMBLE) or prompt.startswith(OD.THINKER_PREAMBLE):
            fake_run.thinker_calls += 1
            fake_run.thinker_prompts.append(prompt)
            fake_run.thinker_cmds.append(list(args))
            if fake_run.thinker_exc:
                raise fake_run.thinker_exc
            return FakeProc(fake_run.thinker_out)
    return FakeProc("ok")
OD.subprocess.run = fake_run
OD._POPEN = fake_popen


def fresh(selfheal="1"):
    fb = FakeBridge()
    OD.bc = fb
    os.environ["STEP_SELFHEAL"] = selfheal
    fake_run.task_queue = []
    fake_run.thinker_calls = 0
    fake_run.thinker_prompts = []
    fake_run.thinker_cmds = []
    fake_run.thinker_out = '{"verdict":"halt","fixed_task":"","reason":"дефолт мока"}'
    fake_run.thinker_exc = None
    fake_run.systemd_units = ""
    return fb


RETRY_JSON = ('{"verdict":"retry","fixed_task":"почини рендер: взять ВЕРНЫЙ путь '
              '/root/turbobaby-manager-bot/bot.py и проверить py_compile","reason":"в ТЗ был неверный путь файла"}')

# (0) юнит: парсер вердикта с ключом fixed_task
print("(0) парсер вердикта (fix_key=fixed_task):")
v = OD._parse_thinker_json(RETRY_JSON, fix_key="fixed_task")
res.append(ok(v["verdict"] == "retry" and "ВЕРНЫЙ путь" in v["fixed_task"], "чистый JSON retry + fixed_task"))
res.append(ok(OD._parse_thinker_json('{"verdict":"maybe","fixed_task":"x","reason":"y"}',
                                     fix_key="fixed_task") is None, "verdict вне retry|halt → None"))
res.append(ok(OD._parse_thinker_json(RETRY_JSON)["verdict"] == "retry",
              "дефолтный fix_key=fixed_step не сломан (обратная совместимость)"))

# (а) САМОТЕСТ а: починимый провал → думатель retry → перерождение → перерождение done
print("(а) починимая одиночная → retry → перерождение done:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: почини рендер карточки байка")["id"]
fake_run.task_queue = [("", 1)]                      # исходная задача упадёт (exit=1)
fake_run.thinker_out = RETRY_JSON
OD.process_new()                                     # провал → думатель retry → перерождение
heals = fb.heals()
res.append(ok(fake_run.thinker_calls == 1, "думатель позван ровно 1 раз"))
res.append(ok(len(heals) == 1 and heals[0]["status"] == "new"
              and heals[0]["task_text"].startswith(f"[самопочинка задачи {tid}, попытка 1]")
              and "ВЕРНЫЙ путь" in heals[0]["task_text"],
              "перерождение: новая задача с маркером [самопочинка задачи N, попытка 1] + fixed_task"))
res.append(ok(heals[0]["from"] == "Filipp-328-dev", "перерождение в ТОЙ ЖЕ полосе from (таймаут сохранён)"))
r0 = fb.rows[tid]
res.append(ok(r0["status"] == "done" and r0["result"].startswith("🩹 задача упала → думатель: retry")
              and "правка:" in r0["result"] and "причина: в ТЗ был неверный путь файла" in r0["result"]
              and "повторный провал = терминальный failed" in r0["result"],
              "карточка решения в 328: done-рапорт исходной с retry/правкой/причиной"))
p = fake_run.thinker_prompts[0]
res.append(ok(p.startswith(OD.TASK_THINKER_PREAMBLE) and "тз: почини рендер карточки байка" in p
              and "СУТЬ ПРОВАЛА" in p and "УПАВШАЯ ЗАДАЧА" in p,
              "промпт думателя: своя преамбула + текст задачи дословно + суть провала"))
cmd0 = fake_run.thinker_cmds[0]
res.append(ok("--max-turns" in cmd0 and cmd0[cmd0.index("--max-turns") + 1] == "1"
              and "--model" in cmd0 and "--fallback-model" in cmd0,
              "думатель: чистый генератор (--max-turns 1) через кондуктор --model/--fallback-model"))
OD.process_new()                                     # перерождение исполняется штатно → done
res.append(ok(fb.rows[heals[0]["id"]]["status"] == "done", "перерождённая задача исполнена → done"))
print("  САМОТЕСТ а:", "PASS" if all(res[-7:]) else "FAIL")

# (б) САМОТЕСТ б: непочинимая → 1 попытка → терминальный failed с диагнозом, ТРЕТЬЕГО нет
print("(б) непочинимая → терминальный failed после 1 попытки:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: непочинимое")["id"]
fake_run.task_queue = [("", 1), ("", 1)]             # исходная упадёт, перерождение тоже упадёт
fake_run.thinker_out = RETRY_JSON
OD.process_new()                                     # провал → retry → перерождение
heals = fb.heals()
res.append(ok(len(heals) == 1, "перерождение создано (попытка 1)"))
OD.process_new()                                     # перерождение упало ПОВТОРНО → терминальный failed
hid = heals[0]["id"]
res.append(ok(fb.rows[hid]["status"] == "failed"
              and "самопочинка не помогла (попытка 1 исчерпана)" in fb.rows[hid]["result"]
              and str(tid) in fb.rows[hid]["result"],
              "повторный провал маркированной → терминальный failed с диагнозом"))
res.append(ok(len(fb.heals()) == 1, "ТРЕТЬЕГО перерождения НЕТ (петля невозможна)"))
res.append(ok(fake_run.thinker_calls == 1, "думатель НЕ зовётся на маркированную задачу"))
print("  САМОТЕСТ б:", "PASS" if all(res[-4:]) else "FAIL")

# (в) САМОТЕСТ в: плановый рестарт самомод-задачи → done с пометкой, думатель НЕ звался
print("(в) плановый рестарт самомод-задачи → done, думатель молчит:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: поправь orchestrator_daemon.py и перезапусти демон")["id"]
fake_run.task_queue = [("", 143)]                    # claude убит SIGTERM (плановый рестарт)
fake_run.systemd_units = "run-r1.service loaded active running systemctl restart orchestrator-daemon"
_run_flag = OD._running
OD._running = False                                  # демон сам в остановке (признак планового)
OD.process_new()
OD._running = _run_flag
res.append(ok(fb.rows[tid]["status"] == "done" and "плановым рестартом" in fb.rows[tid]["result"],
              "самомод-задача завершена done с пометкой планового рестарта (фикс 48d9c64 главнее)"))
res.append(ok(fake_run.thinker_calls == 0 and not fb.heals(),
              "думатель НЕ звался, перерождения нет (плановый рестарт ≠ провал)"))
print("  САМОТЕСТ в:", "PASS" if all(res[-2:]) else "FAIL")

# (г) САМОТЕСТ г: STEP_SELFHEAL=0 → голый failed как раньше (байт-в-байт прежнее поведение)
print("(г) флаг выключен → голый failed:")
fb = fresh(selfheal="0")
tid = fb.enqueue_task("Filipp-328-dev", "тз: упадёт при выключенном флаге")["id"]
fake_run.task_queue = [("", 1)]
OD.process_new()
res.append(ok(fake_run.thinker_calls == 0, "думатель НЕ позван (флаг 0)"))
res.append(ok(fb.rows[tid]["status"] == "failed" and "🩹" not in fb.rows[tid]["result"]
              and "думатель" not in fb.rows[tid]["result"] and not fb.heals(),
              "голый failed без следов самопочинки — прежнее поведение"))
print("  САМОТЕСТ г:", "PASS" if all(res[-2:]) else "FAIL")

# (5) думатель: verdict=halt → терминальный failed С ДИАГНОЗОМ (перерождения нет)
print("(5) думатель говорит halt:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328", "задача: сложное")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_out = '{"verdict":"halt","fixed_task":"","reason":"нужен доступ, переформулировка не поможет"}'
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "failed"
              and "думатель: halt, причина: нужен доступ" in fb.rows[tid]["result"]
              and not fb.heals(), "halt-вердикт → терминальный failed, диагноз в карточке"))

# (6) fail-safe: мусор-JSON / таймаут / retry без fixed_task / enqueue-fail → голый failed
print("(6) fail-safe думателя:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: A")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_out = "я не буду отвечать json"
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "failed" and "думатель" not in fb.rows[tid]["result"]
              and not fb.heals(), "мусор-JSON → прежний голый failed (не хуже)"))

fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: B")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_exc = _sp.TimeoutExpired(cmd="claude", timeout=180)
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "failed" and not fb.heals(),
              "таймаут думателя → прежний голый failed"))

fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: C")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_out = '{"verdict":"retry","fixed_task":"","reason":"retry без правки"}'
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "failed" and "думатель: halt" in fb.rows[tid]["result"]
              and not fb.heals(), "retry с пустым fixed_task → трактуем как halt"))

fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: D")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_out = RETRY_JSON
_real_enq = FakeBridge.enqueue_task
FakeBridge.enqueue_task = lambda s, frm, txt: {"ok": False, "error": "queue_down"}
OD.process_new()
FakeBridge.enqueue_task = _real_enq
res.append(ok(fb.rows[tid]["status"] == "failed" and not fb.heals(),
              "enqueue перерождения не встал → fail-safe голый failed"))

# (7) красное НЕ ослаблено: NEEDS_APPROVAL одиночной → кнопка, думатель молчит;
#     перерождённая задача с красным → тоже кнопка (обычный цикл)
print("(7) красное не ослаблено:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: с красным")["id"]
fake_run.task_queue = [("NEEDS_APPROVAL: op=other | запись в Лист1", 0)]
OD.process_new()
res.append(ok(fb.rows[tid]["status"] == "needs_approval" and fake_run.thinker_calls == 0,
              "красная одиночная → needs_approval-кнопка как раньше, думатель не зовётся"))
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "тз: упадёт, а перерождение упрётся в красное")["id"]
# живой формат самодекларации (31.07.2026): op=other — исполнимый класс в заявке исполнителя
# карточки не рождает (замок происхождения, tests/test_card_origin.py)
fake_run.task_queue = [("", 1), ("NEEDS_APPROVAL: op=other | запись в CRM · строка 12", 0)]
fake_run.thinker_out = RETRY_JSON
OD.process_new()                                     # провал → перерождение
OD.process_new()                                     # перерождение упёрлось в красное → кнопка
hid = fb.heals()[0]["id"]
res.append(ok(fb.rows[hid]["status"] == "needs_approval",
              "перерождённая задача идёт обычным циклом: красное → кнопка"))

# (8) конверт одобренной заявки НЕ трогаем (маркер [конверт…] обязан оставаться первым)
print("(8) конверт мимо самопочинки задачи:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev",
                      "[конверт одобренной заявки 55] Филипп нажал «да» на заявку: сделай X")["id"]
fake_run.task_queue = [("", 1)]
OD.process_new()
res.append(ok(fake_run.thinker_calls == 0 and fb.rows[tid]["status"] == "failed" and not fb.heals(),
              "провал конверта → прежний голый failed, думатель не позван"))

# (9) шаги декомпозера НЕ задеты: провал шага идёт в ШАГОВУЮ ветку (промпт с преамбулой шага)
print("(9) шаговая ветка не задета:")
fb = fresh()
sid = fb.enqueue_task("Filipp-328-dec", "[шаг 1/2 родитель 7] сделать первый шаг")["id"]
fake_run.task_queue = [("", 1)]
fake_run.thinker_out = '{"verdict":"halt","fixed_step":"","reason":"диагноз шага"}'
OD.process_new()
res.append(ok(fake_run.thinker_calls == 1
              and fake_run.thinker_prompts[0].startswith(OD.THINKER_PREAMBLE)
              and "УПАВШИЙ ШАГ 1/2" in fake_run.thinker_prompts[0]
              and not fb.heals(),
              "провал шага → думатель ШАГА (своя преамбула), маркер задачи не рождается"))

os.environ.pop("STEP_SELFHEAL", None)
OD.subprocess.run = _real_run
OD._POPEN = _real_POPEN
OD.MAX_CLAUDE_PROCS = _real_MAX_CLAUDE_PROCS

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
