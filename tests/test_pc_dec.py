"""ПК-ТЕАТР кусок 2 (07.07.2026): декомпозер на полосу pc — «один дирижёр, два театра».
Мозг (планировщик/думатели) ТОЛЬКО на VPS-демоне; ПК-агент (мокнут) — второй театр исполнения.
Шаги релизятся ПО ОДНОМУ (sequential release: у ПК-агента нет guard'а последовательности),
состояние цепи restart-proof из очереди. Сети/Telegram/claude нет — всё мокнуто.
Самотесты ТЗ: (А) цепь с pc-шагами: план → шаги lane=pc → мок-исполнение → сводка;
(Б) провал pc-шага → думатель retry → перерождение lane=pc; повторный провал → терминальный halt;
(В) done pc-шага → PLAN_ADAPT (adjust: карточка коррекции + скорректированный релиз; finish; лимит);
(Г) красный pc-шаг → needs_approval нетронут (карточку в инбокс несёт devbot), отказ «нет» → halt;
(Д) ПК молчит → таймаут-failed с диагнозом «ПК-театр не отвечает», думатель НЕ зовётся;
(Е) обычная vps-декомпозиция — ноль изменений; одиночные pc-задачи не трогаются."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("STEP_SELFHEAL", "1")
os.environ.setdefault("PLAN_ADAPT", "1")
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso(ago_sec=0):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=ago_sec)).isoformat()


class FakeBridge:
    """Очередь в памяти С ПОЛОСАМИ: enqueue/get_pending понимают lane (как новый Bridge)."""
    def __init__(s):
        s.rows, s.nid = {}, 100
    def enqueue_task(s, frm, txt, lane=None):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso(), "lane": lane or "vps"}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        ln = lane or "vps"
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts and (ln == "all" or r["lane"] == ln)]
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
    # хелперы ассертов
    def pc_steps(s, status=None):
        return [r for r in sorted(s.rows.values(), key=lambda x: x["id"])
                if r["lane"] == "pc" and (status is None or r["status"] == status)]
    def summaries(s, pid):
        return [r for r in s.rows.values()
                if r["task_text"].startswith(f"[сводка родитель {pid}]")]
    def cards(s, pid):
        return [r for r in sorted(s.rows.values(), key=lambda x: x["id"])
                if r["task_text"].startswith(f"[карточка родитель {pid}]")]
    def adapt_cards(s, pid):
        return [r for r in sorted(s.rows.values(), key=lambda x: x["id"])
                if r["task_text"].startswith(f"[коррекция плана родитель {pid}]")]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


def fake_run(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN:
        prompt = args[-1]
        if prompt.startswith(OD.PLANNER_PREAMBLE):
            fake_run.planner_prompts.append(prompt)
            return FakeProc(fake_run.plan_out)
        if prompt.startswith(OD.ADAPT_PREAMBLE):
            fake_run.adapt_calls += 1
            if fake_run.adapt_queue:
                return FakeProc(fake_run.adapt_queue.pop(0))
            return FakeProc(fake_run.adapt_out)
        if prompt.startswith(OD.THINKER_PREAMBLE) or prompt.startswith(OD.TASK_THINKER_PREAMBLE):
            fake_run.thinker_calls += 1
            return FakeProc(fake_run.thinker_out)
        if fake_run.step_queue:                     # vps-шаги (театр Е) исполняет claude-мок
            out, rc = fake_run.step_queue.pop(0)
            return FakeProc(out, rc)
        return FakeProc("сводка: шаг сделан")
    return FakeProc("ok")
OD.subprocess.run = fake_run


def fresh(plan="1. шаг один\n2. шаг два", selfheal="1", adapt="1"):
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    OD._pc_adapted.clear()
    OD._adapt_finish.clear()
    os.environ["STEP_SELFHEAL"] = selfheal
    os.environ["PLAN_ADAPT"] = adapt
    fake_run.plan_out = plan
    fake_run.planner_prompts = []
    fake_run.step_queue = []
    fake_run.adapt_calls = 0
    fake_run.adapt_queue = []
    fake_run.adapt_out = '{"verdict":"keep","adjusted_steps":[],"reason":"план верен"}'
    fake_run.thinker_calls = 0
    fake_run.thinker_out = '{"verdict":"halt","fixed_step":"","reason":"дефолт мока"}'
    return fb


def pc_exec(fb, status="done", result="шаг сделан ПК-агентом"):
    """Мок ПК-исполнителя: берёт ЕДИНСТВЕННЫЙ new-шаг полосы pc (claim → complete/needs_approval)."""
    steps = fb.pc_steps("new")
    assert len(steps) == 1, f"на полосе pc должен ждать ровно 1 шаг (sequential release): {steps}"
    r = steps[0]
    r["status"] = "in_progress"
    if status == "needs_approval":
        r["status"], r["result"] = "needs_approval", result
    else:
        r["status"], r["result"] = status, result
    r["updated"] = now_iso()
    return r


PARENT_FROM = OD.PC_DEC_FROM      # Filipp-pc-dec (родитель на полосе vps — кладёт devbot)


def new_parent(fb, text="крупное ТЗ для ПК"):
    return fb.enqueue_task(PARENT_FROM, text)["id"]     # БЕЗ lane → vps → возьмёт VPS-демон


# (0) юниты: восстановление плана из очереди (restart-proof)
print("(0) юниты плана:")
res.append(ok(OD._parse_numbered("шапка\n1. раз\n2) два\nхвост 3 не шаг") == {1: "раз", 2: "два"},
              "_parse_numbered: нумерованные строки → {N: текст}"))
fb = fresh()
pid = new_parent(fb)
fb.rows[pid]["status"], fb.rows[pid]["result"] = "done", "🧩 план:\n1. альфа\n2. бета\n3. гамма"
plan, k, base = OD._pc_current_plan(pid)
res.append(ok(plan == {1: ("альфа", 0), 2: ("бета", 0), 3: ("гамма", 0)} and k == 0 and base is None,
              "план из result родителя, коррекций нет"))
cid = fb.enqueue_task(PARENT_FROM, f"[коррекция плана родитель {pid}] после шага 2 (K=1)")["id"]
fb.rows[cid]["status"] = "done"
fb.rows[cid]["result"] = "🧭 коррекция: причина\nНОВЫЙ ОСТАВШИЙСЯ ПЛАН:\n3. дельта\n4. эпсилон"
plan, k, base = OD._pc_current_plan(pid)
res.append(ok(plan == {1: ("альфа", 0), 2: ("бета", 0), 3: ("дельта", 1), 4: ("эпсилон", 1)}
              and k == 1 and base == 2,
              "коррекция поверх: остаток заменён, база=2, K=1"))

# (А) цепь с pc-шагами: план → шаги lane=pc ПО ОДНОМУ → мок-исполнение → сводка
print("(А) цепь ПК-театра до сводки:")
fb = fresh(plan="1. первый\n2. второй\n3. третий")
pid = new_parent(fb)
OD.process_new()                                     # родитель → план → релиз шага 1 lane=pc
parent = fb.rows[pid]
res.append(ok(parent["status"] == "done" and "театр PC" in parent["result"]
              and "1. первый" in parent["result"], "родитель done, план в result (театр PC)"))
res.append(ok(fake_run.planner_prompts and OD.PLANNER_PC_NOTE in fake_run.planner_prompts[0],
              "планировщику дописана особенность ПК-театра"))
s1 = fb.pc_steps()
res.append(ok(len(s1) == 1 and s1[0]["task_text"].startswith(f"[шаг 1/3 родитель {pid}]")
              and s1[0]["from"] == PARENT_FROM and s1[0]["lane"] == "pc",
              "релизнут ТОЛЬКО шаг 1 (lane=pc, from=Filipp-pc-dec)"))
OD.process_pc_chains()                               # шаг 1 ещё new (ПК не взял) → ждём, без действий
res.append(ok(len(fb.pc_steps()) == 1 and fake_run.thinker_calls == 0 and fake_run.adapt_calls == 0,
              "шаг ждёт ПК — демон не дёргает думателей и не плодит шагов"))
pc_exec(fb, "done", "первый готов")
OD.process_pc_chains()                               # done → адаптация (keep) → релиз шага 2
res.append(ok(fake_run.adapt_calls == 1, "после done шага 1 позван думатель адаптации (keep)"))
s = fb.pc_steps("new")
res.append(ok(len(s) == 1 and s[0]["task_text"].startswith(f"[шаг 2/3 родитель {pid}]"),
              "keep → релизнут шаг 2/3"))
pc_exec(fb, "done", "второй готов")
OD.process_pc_chains()                               # → шаг 3
pc_exec(fb, "done", "третий готов")
OD.process_pc_chains()                               # последний done → сводка (адаптация не зовётся)
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and sums[0]["status"] == "done" and sums[0]["from"] == PARENT_FROM,
              "сводка одна, done, from=Filipp-pc-dec (devbot принесёт в 829)"))
res.append(ok("3/3 шагов done" in sums[0]["result"] and "театр PC" in sums[0]["result"]
              and sums[0]["result"].count("✅") == 3, f"текст сводки: {sums[0]['result'][:120]}"))
res.append(ok(fake_run.adapt_calls == 2, "на последнем шаге думатель адаптации НЕ зовётся (экономия)"))
OD.process_pc_chains()                               # идемпотентность
res.append(ok(len(fb.summaries(pid)) == 1, "повторный цикл — дубля сводки нет"))
# restart-proof: рестарт демона (потеря памяти) — закрытая цепь не трогается
OD._summarized.clear(); OD._pc_adapted.clear()
n_rows = len(fb.rows)
OD.process_pc_chains()
res.append(ok(len(fb.rows) == n_rows and fake_run.thinker_calls == 0,
              "после «рестарта» закрытая цепь узнана по сводке в очереди — ноль действий"))

# (Б) провал pc-шага → думатель retry → перерождение lane=pc; повторный провал → терминальный halt
print("(Б) самопочинка pc-шага:")
fb = fresh(plan="1. первый\n2. второй")
pid = new_parent(fb)
OD.process_new()
pc_exec(fb, "done", "первый готов")
OD.process_pc_chains()                               # релиз шага 2
pc_exec(fb, "failed", "claude -p упал (exit=1): кривой путь")
fake_run.thinker_out = ('{"verdict":"retry","fixed_step":"шаг два: взять верный путь и повторить",'
                        '"reason":"в шаге был неверный путь"}')
OD.process_pc_chains()                               # провал → думатель retry → перерождение
res.append(ok(fake_run.thinker_calls == 1, "думатель самопочинки позван один раз"))
reborn = fb.pc_steps("new")
res.append(ok(len(reborn) == 1 and "[самопочинка шага 2, попытка 1]" in reborn[0]["task_text"]
              and reborn[0]["task_text"].startswith(f"[шаг 2/2 родитель {pid}]")
              and reborn[0]["lane"] == "pc",
              "перерождение шага 2 на полосе pc с маркером самопочинки"))
crd = fb.cards(pid)
res.append(ok(len(crd) == 1 and crd[0]["result"].startswith("🩹"), "карточка 🩹 retry в тему PC-дев"))
res.append(ok(not fb.summaries(pid), "цепь жива — сводки ещё нет"))
pc_exec(fb, "failed", "снова упал")
OD.process_pc_chains()                               # повторный провал → терминальный halt
res.append(ok(fake_run.thinker_calls == 1, "повторный провал — думатель НЕ зовётся (петля невозможна)"))
crd = fb.cards(pid)
res.append(ok(len(crd) == 2 and crd[1]["result"].startswith("🛑"), "терминальная карточка 🛑"))
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "1/2" in sums[0]["result"] and "❌" in sums[0]["result"],
              "сводка halt-цепи: 1/2 done, провал виден"))
res.append(ok(len(fb.pc_steps("new")) == 0, "третьего перерождения/шагов после halt НЕТ"))

# (Б-2) думатель halt на первом провале → цепь останавливается без перерождения
fb = fresh(plan="1. первый\n2. второй")
pid = new_parent(fb)
OD.process_new(); pc_exec(fb, "failed", "исполнительский провал")
fake_run.thinker_out = '{"verdict":"halt","fixed_step":"","reason":"нужен человек"}'
OD.process_pc_chains()
res.append(ok(fake_run.thinker_calls == 1 and not fb.pc_steps("new")
              and len(fb.summaries(pid)) == 1 and fb.cards(pid)
              and "halt" in fb.cards(pid)[0]["result"],
              "думатель halt → карточка диагноза + сводка, перерождения нет"))

# (Б-3) STEP_SELFHEAL=0 → провал = мгновенный halt без думателя
fb = fresh(plan="1. первый\n2. второй", selfheal="0")
pid = new_parent(fb)
OD.process_new(); pc_exec(fb, "failed", "провал")
OD.process_pc_chains()
res.append(ok(fake_run.thinker_calls == 0 and len(fb.summaries(pid)) == 1,
              "SELFHEAL=0: думатель не зовётся, сразу сводка halt-цепи"))

# (В) done pc-шага → PLAN_ADAPT: adjust → карточка коррекции + скорректированный релиз
print("(В) адаптация плана ПК-цепи:")
fb = fresh(plan="1. первый\n2. второй\n3. третий")
pid = new_parent(fb)
OD.process_new()
pc_exec(fb, "done", "первый готов")
fake_run.adapt_queue = ['{"verdict":"adjust","adjusted_steps":["новый второй","новый третий"],'
                        '"reason":"результат шага 1 изменил остаток"}']
OD.process_pc_chains()
ac = fb.adapt_cards(pid)
res.append(ok(len(ac) == 1 and "после шага 1" in ac[0]["task_text"] and ac[0]["status"] == "done"
              and "2. новый второй" in ac[0]["result"] and "3. новый третий" in ac[0]["result"],
              "карточка коррекции done, restart-proof план в result"))
s = fb.pc_steps("new")
res.append(ok(len(s) == 1 and s[0]["task_text"].startswith(f"[шаг 2/3 родитель {pid}]")
              and "[коррекция плана 1]" in s[0]["task_text"] and "новый второй" in s[0]["task_text"],
              "релизнут скорректированный шаг 2/3 с маркером коррекции"))
# рестарт демона между шагами коррекции: план продолжается ИЗ КАРТОЧКИ (не из памяти)
OD._pc_adapted.clear(); OD._summarized.clear()
pc_exec(fb, "done", "новый второй готов")
fake_run.adapt_calls = 0
OD.process_pc_chains()
s = fb.pc_steps("new")
res.append(ok(len(s) == 1 and "новый третий" in s[0]["task_text"] and fake_run.adapt_calls == 1,
              "после «рестарта» шаг 3 взят из карточки коррекции"))
pc_exec(fb, "done", "новый третий готов")
OD.process_pc_chains()
res.append(ok(len(fb.summaries(pid)) == 1 and "3/3" in fb.summaries(pid)[0]["result"],
              "цепь с коррекцией дошла до сводки 3/3"))

# (В-2) finish → оставшиеся не релизятся, сводка «завершено досрочно»
fb = fresh(plan="1. первый\n2. второй\n3. третий")
pid = new_parent(fb)
OD.process_new(); pc_exec(fb, "done", "первый готов")
fake_run.adapt_queue = ['{"verdict":"finish","adjusted_steps":[],"reason":"цель уже достигнута"}']
OD.process_pc_chains()
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "завершено досрочно" in sums[0]["result"]
              and not fb.pc_steps("new"), "finish: шаги 2-3 не релизнуты, сводка 🏁"))

# (В-3) лимит коррекций: третий adjust → терминальный halt «план дрейфует»
fb = fresh(plan="1. а\n2. б\n3. в\n4. г")
pid = new_parent(fb)
OD.process_new()
adj = '{"verdict":"adjust","adjusted_steps":["з1","з2","з3"],"reason":"дрейф %d"}'
pc_exec(fb, "done", "ок")
fake_run.adapt_queue = [adj % 1]
OD.process_pc_chains()                               # коррекция 1
pc_exec(fb, "done", "ок")
fake_run.adapt_queue = [adj % 2]
OD.process_pc_chains()                               # коррекция 2
pc_exec(fb, "done", "ок")
fake_run.adapt_queue = [adj % 3]
OD.process_pc_chains()                               # коррекция 3 → лимит → halt
res.append(ok(len(fb.adapt_cards(pid)) == 2, "встали только 2 карточки коррекции (лимит)"))
halt_cards = [c for c in fb.cards(pid) if "план дрейфует" in c["result"]]
res.append(ok(len(halt_cards) == 1 and len(fb.summaries(pid)) == 1 and not fb.pc_steps("new"),
              "третий adjust → halt «план дрейфует» + сводка, релиза нет"))

# (В-4) PLAN_ADAPT=0 → думатель адаптации не зовётся, релиз по исходному плану
fb = fresh(plan="1. первый\n2. второй", adapt="0")
pid = new_parent(fb)
OD.process_new(); pc_exec(fb, "done", "ок")
OD.process_pc_chains()
res.append(ok(fake_run.adapt_calls == 0 and len(fb.pc_steps("new")) == 1,
              "PLAN_ADAPT=0: без думателя, шаг 2 релизнут по исходному плану"))

# (Г) красный pc-шаг → needs_approval висит нетронутым (карточку в инбокс несёт devbot);
#     отказ Филиппа («нет N») → halt без думателя
print("(Г) красный pc-шаг:")
fb = fresh(plan="1. первый\n2. второй")
pid = new_parent(fb)
OD.process_new()
step = pc_exec(fb, "needs_approval", "op=other | запись в Лист1: строка байка")
n_rows = len(fb.rows)
OD.process_pc_chains(); OD.process_pc_chains()
res.append(ok(fb.rows[step["id"]]["status"] == "needs_approval" and len(fb.rows) == n_rows
              and fake_run.thinker_calls == 0,
              "needs_approval нетронут: демон ждёт Филиппа, ничего не плодит"))
fb.complete_task(step["id"], "failed", "отклонено Филиппом (кнопка)")   # «нет N» от devbot
OD.process_pc_chains()
res.append(ok(fake_run.thinker_calls == 0 and len(fb.summaries(pid)) == 1
              and not fb.pc_steps("new"),
              "отказ Филиппа → halt цепи без думателя, сводка есть"))

# (Д) ПК молчит → таймаут-failed с диагнозом, думатель НЕ зовётся, цепь не висит вечно
print("(Д) таймаут ПК-театра:")
fb = fresh(plan="1. первый\n2. второй")
pid = new_parent(fb)
OD.process_new()
step = fb.pc_steps("new")[0]
step["updated"] = now_iso(ago_sec=OD.PC_STEP_TIMEOUT + 60)     # ПК так и не взял шаг
OD.process_pc_chains()
row = fb.rows[step["id"]]
res.append(ok(row["status"] == "failed" and OD.PC_SILENT_MARK in row["result"],
              f"шаг failed с диагнозом «ПК-театр не отвечает»: {row['result'][:100]}"))
res.append(ok(fake_run.thinker_calls == 0, "молчание ПК думатель НЕ чинит (halt)"))
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "0/2" in sums[0]["result"], "сводка halt-цепи по таймауту"))
OD.process_pc_chains()
res.append(ok(len(fb.summaries(pid)) == 1 and fake_run.thinker_calls == 0,
              "после таймаута цепь закрыта: повторных действий нет"))
# (Д-2) зависший in_progress (heartbeat умер) — тот же честный таймаут
fb = fresh(plan="1. первый\n2. второй")
pid = new_parent(fb)
OD.process_new()
step = fb.pc_steps("new")[0]
step["status"] = "in_progress"
step["updated"] = now_iso(ago_sec=OD.PC_STEP_TIMEOUT + 60)
OD.process_pc_chains()
res.append(ok(fb.rows[step["id"]]["status"] == "failed"
              and OD.PC_SILENT_MARK in fb.rows[step["id"]]["result"]
              and len(fb.summaries(pid)) == 1,
              "in_progress без heartbeat дольше лимита → таймаут-failed + сводка"))

# (Е) обычная vps-декомпозиция — ноль изменений (веерный fan-out, guard, сводка);
#     process_pc_chains между циклами ей не мешает; одиночные pc-задачи не трогаются
print("(Е) vps-полоса байт-в-байт + изоляция:")
fb = fresh(plan="1. первый\n2. второй")
vps_pid = fb.enqueue_task("Filipp-328-dec", "крупное ТЗ на VPS")["id"]
lone_pc = fb.enqueue_task("Filipp-pc", "одиночная задача ПК", lane="pc")["id"]
OD.process_pc_chains()
res.append(ok(fb.rows[lone_pc]["status"] == "new", "одиночную pc-задачу демон НЕ трогает"))
OD.process_new()                                     # план → веерный fan-out ОБОИХ шагов сразу
vps_steps = [r for r in fb.rows.values() if r["from"] == "Filipp-328-dec"
             and r["task_text"].startswith("[шаг ")]
res.append(ok(len(vps_steps) == 2 and all(r["lane"] == "vps" for r in vps_steps)
              and all(r["status"] == "new" for r in vps_steps),
              "vps: оба шага в очереди сразу (веер, БЕЗ sequential release), lane=vps"))
OD.process_pc_chains()                               # не мешает vps-цепи
fake_run.step_queue = [("первый готов", 0), ("второй готов", 0)]
OD.process_new(); OD.process_pc_chains(); OD.process_new()
sums = fb.summaries(vps_pid)
res.append(ok(len(sums) == 1 and "театр PC" not in sums[0]["result"]
              and "2/2" in sums[0]["result"], "vps-цепь дошла до обычной сводки 2/2"))
res.append(ok(fb.rows[lone_pc]["status"] == "new" and fake_run.thinker_calls == 0,
              "одиночная pc-задача так и нетронута; лишних думателей не было"))

print()
if all(res):
    print(f"OK — {len(res)} проверок ПК-театра (декомпозер на полосу pc) зелёные")
    sys.exit(0)
print(f"FAILED — {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
