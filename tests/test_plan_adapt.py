"""АДАПТАЦИЯ ПЛАНА декомпозера (мета-дирижёр кусок 2, KB_MASTER §4, 07.07.2026).
После КАЖДОГО done-шага при PLAN_ADAPT=1 думатель (кондуктор, --max-turns 1, строгий JSON)
сверяет результаты с целью: keep (ноль изменений) / adjust (заменить оставшиеся, маркер
«[коррекция плана K]», максимум 2 на цепь, третий = halt «план дрейфует») / finish (закрыть
оставшиеся досрочно, сводка «завершено досрочно»). «skipped» = done+⏭/♻️-карта (Bridge
принимает только done|failed), сводка эти карты исключает. Fail-safe везде = keep.
Сети/Telegram/claude нет — всё мокнуто (FakeBridge в памяти, subprocess.run подменён).
Самотесты обкатки: (А) шаг 1 делает шаг 3 лишним → adjust; (Б) цель достигнута после шага
2 из 4 → finish; (В) нормальная цепь → keep, ноль изменений; (Г) третий adjust → halt
«план дрейфует»; (Д) PLAN_ADAPT=0 → думатель не зовётся, байт-в-байт прежнее;
(Е) сбой думателя (мусор/таймаут/пустой adjust) → keep, цепь не встала.
Плюс: совместимость с STEP_SELFHEAL (провал → самопочинка; done → адаптация)."""
import os, sys, json as _json, datetime, subprocess as _sp
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # база; каждый блок выставляет флаг сам через fresh()
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
        # как боевой Bridge completeTask_: ТОЛЬКО done|failed, иначе bad_status
        if status not in ("done", "failed"):
            return {"ok": False, "error": "bad_status"}
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
    def steps(s, pid):
        return [r for r in s.rows.values() if r["task_text"].startswith("[шаг ")
                and f"родитель {pid}]" in r["task_text"].split("]")[0] + "]"]
    def summaries(s, pid):
        return [r for r in s.rows.values() if r["task_text"].startswith(f"[сводка родитель {pid}]")]
    def adapt_cards(s, pid):
        return [r for r in s.rows.values()
                if r["task_text"].startswith(f"[коррекция плана родитель {pid}]")]
    def corrected(s):
        return [r for r in s.rows.values() if "[коррекция плана" in r["task_text"]
                and not r["task_text"].startswith("[коррекция плана родитель")]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


_real_run = OD.subprocess.run
def fake_run(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN:
        prompt = args[-1]
        if prompt.startswith(OD.ADAPT_PREAMBLE):
            fake_run.adapt_calls += 1
            fake_run.adapt_prompts.append(prompt)
            fake_run.adapt_cmds.append(list(args))
            if fake_run.adapt_exc:
                raise fake_run.adapt_exc
            if fake_run.adapt_queue:
                return FakeProc(fake_run.adapt_queue.pop(0))
            return FakeProc('{"verdict":"keep","adjusted_steps":[],"reason":"план верен"}')
        if prompt.startswith(OD.THINKER_PREAMBLE):
            fake_run.heal_calls += 1
            return FakeProc(fake_run.heal_out)
        if prompt.startswith(OD.PLANNER_PREAMBLE):
            return FakeProc(fake_run.plan_out)
        if fake_run.step_queue:
            out, rc = fake_run.step_queue.pop(0)
            return FakeProc(out, rc)
        return FakeProc("сводка: шаг сделан")
    return FakeProc("ok")
OD.subprocess.run = fake_run


def fresh(adapt="1", selfheal="1", plan="1. шаг один\n2. шаг два\n3. шаг три"):
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    OD._adapt_finish.clear()
    os.environ["PLAN_ADAPT"] = adapt
    os.environ["STEP_SELFHEAL"] = selfheal
    fake_run.plan_out = plan
    fake_run.step_queue = []
    fake_run.adapt_calls = 0
    fake_run.adapt_prompts = []
    fake_run.adapt_cmds = []
    fake_run.adapt_queue = []
    fake_run.adapt_exc = None
    fake_run.heal_calls = 0
    fake_run.heal_out = '{"verdict":"halt","fixed_step":"","reason":"дефолт мока"}'
    return fb


ADJ = lambda steps, reason: _json.dumps(
    {"verdict": "adjust", "adjusted_steps": steps, "reason": reason}, ensure_ascii=False)
FIN = lambda reason: _json.dumps(
    {"verdict": "finish", "adjusted_steps": [], "reason": reason}, ensure_ascii=False)

# (0) юнит: парсер вердикта адаптации
print("(0) парсер вердикта адаптации:")
res.append(ok(OD._parse_adapt_json('{"verdict":"keep","adjusted_steps":[],"reason":"ок"}')["verdict"] == "keep",
              "чистый keep"))
v = OD._parse_adapt_json("```json\n" + ADJ(["новый шаг"], "лишний хвост") + "\n```")
res.append(ok(v and v["verdict"] == "adjust" and v["adjusted_steps"] == ["новый шаг"],
              "adjust в markdown-обёртке — терпим"))
res.append(ok(OD._parse_adapt_json(FIN("готово"))["verdict"] == "finish", "finish"))
res.append(ok(OD._parse_adapt_json('{"verdict":"maybe","adjusted_steps":[],"reason":"x"}') is None,
              "verdict вне keep|adjust|finish → None"))
res.append(ok(OD._parse_adapt_json(ADJ([], "пустой")) is None,
              "adjust с пустым adjusted_steps → None (= keep)"))
res.append(ok(OD._parse_adapt_json('{"verdict":"adjust","adjusted_steps":["  ","\t"],"reason":"x"}') is None,
              "adjust из одних пробелов → None (= keep)"))
res.append(ok(OD._parse_adapt_json("мусор не json") is None, "мусор → None"))
res.append(ok(OD._parse_adapt_json("") is None, "пусто → None"))

# (А) САМОТЕСТ А: шаг 1 сделал шаг 3 лишним → adjust, оставшиеся заменены, цепь дошла
print("(А) adjust: шаг 1 делает шаг 3 лишним:")
fb = fresh(plan="1. первый\n2. второй\n3. третий (лишний после первого)")
pid = fb.enqueue_task("Filipp-328-dec", "цель: собрать фичу X без дублей")["id"]
OD.process_new()                                     # план → 3 шага
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.adapt_queue = [ADJ(["второй шаг, уже без третьего: доделать X и проверить"],
                            "шаг 1 уже покрыл работу шага 3")]
OD.process_new()                                     # шаг 1 done → думатель adjust
corr = fb.corrected()
res.append(ok(fake_run.adapt_calls == 1, "думатель адаптации позван после done шага 1"))
res.append(ok(len(corr) == 1 and corr[0]["status"] == "new"
              and corr[0]["task_text"].startswith(f"[шаг 2/2 родитель {pid}] [коррекция плана 1]")
              and "без третьего" in corr[0]["task_text"],
              "оставшиеся заменены ОДНИМ новым шагом с маркером [коррекция плана 1], нумерация 2/2"))
res.append(ok(corr[0]["from"] == "Filipp-328-dec", "коррекция в полосе dec"))
res.append(ok(fb.rows[s2]["status"] == "done" and fb.rows[s2]["result"].startswith(OD.ADAPT_REPLACED_MARK)
              and fb.rows[s3]["status"] == "done" and fb.rows[s3]["result"].startswith(OD.ADAPT_REPLACED_MARK),
              "старые шаги 2 и 3 закрыты ♻️-картой (не failed — цепь не глушится)"))
res.append(ok(fb.rows[s1]["status"] == "done" and fb.rows[s1]["result"] == "сводка: шаг сделан",
              "сделанный шаг 1 НЕ тронут"))
cards = fb.adapt_cards(pid)
res.append(ok(len(cards) == 1 and cards[0]["status"] == "done"
              and "после шага 1 думатель скорректировал план" in cards[0]["result"]
              and "шаг 1 уже покрыл работу шага 3" in cards[0]["result"],
              "карточка в 328: «после шага i думатель скорректировал план: reason»"))
p = fake_run.adapt_prompts[0]
res.append(ok("цель: собрать фичу X без дублей" in p and "1. первый" in p
              and "РЕЗУЛЬТАТЫ СДЕЛАННЫХ ШАГОВ" in p and "сводка: шаг сделан" in p
              and "ОСТАВШИЕСЯ ШАГИ ПЛАНА" in p and "третий (лишний после первого)" in p,
              "промпт: цель дословно + исходный план + результаты сделанных + оставшиеся"))
cmd0 = fake_run.adapt_cmds[0]
res.append(ok("--max-turns" in cmd0 and cmd0[cmd0.index("--max-turns") + 1] == "1"
              and "--model" in cmd0 and "--fallback-model" in cmd0,
              "думатель: чистый генератор (--max-turns 1) через кондуктор"))
OD.process_new()                                     # скорректированный шаг 2/2 → done → сводка
sums = fb.summaries(pid)
res.append(ok(fb.rows[corr[0]["id"]]["status"] == "done" and len(sums) == 1,
              "цепь дошла: скорректированный шаг исполнен, сводка одна"))
res.append(ok("2/2 шагов done" in sums[0]["result"] and OD.ADAPT_REPLACED_MARK not in sums[0]["result"]
              and "есть упавшие" not in sums[0]["result"],
              "сводка: 2/2 done по НОВОМУ итогу плана, ♻️-карты исключены, упавших нет"))
res.append(ok(fake_run.adapt_calls == 1, "после ПОСЛЕДНЕГО шага думатель не зовётся (экономия)"))
print("  САМОТЕСТ А:", "PASS" if all(res[-11:]) else "FAIL")

# (Б) САМОТЕСТ Б: цель достигнута после шага 2 из 4 → finish, 3-4 закрыты, сводка «досрочно»
print("(Б) finish: цель достигнута после шага 2 из 4:")
fb = fresh(plan="1. раз\n2. два\n3. три\n4. четыре")
pid = fb.enqueue_task("Filipp-328-dec", "цель: починить баг Y")["id"]
OD.process_new()                                     # план → 4 шага
s1, s2, s3, s4 = sorted(r["id"] for r in fb.by_status("new"))
OD.process_new()                                     # шаг 1 done → keep (дефолт мока)
fake_run.adapt_queue = [FIN("баг Y уже исправлен результатом шага 2")]
OD.process_new()                                     # шаг 2 done → finish
res.append(ok(fake_run.adapt_calls == 2, "думатель позван после шага 1 (keep) и шага 2 (finish)"))
res.append(ok(fb.rows[s3]["status"] == "done" and fb.rows[s3]["result"].startswith(OD.ADAPT_FINISH_MARK)
              and fb.rows[s4]["status"] == "done" and fb.rows[s4]["result"].startswith(OD.ADAPT_FINISH_MARK)
              and "достигнута" in fb.rows[s3]["result"],
              "шаги 3-4 закрыты ⏭-картой «цель достигнута досрочно»"))
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and sums[0]["status"] == "done"
              and "завершено досрочно: баг Y уже исправлен результатом шага 2" in sums[0]["result"],
              "сводка по родителю с пометкой «завершено досрочно: <reason>»"))
res.append(ok("2/4 шагов done" in sums[0]["result"] and OD.ADAPT_FINISH_MARK not in sums[0]["result"]
              and "есть упавшие" not in sums[0]["result"],
              "в сводке 2/4 done, ⏭-карты исключены, «упавших» нет"))
res.append(ok(not fb.corrected() and fb.rows[s1]["status"] == "done" and fb.rows[s2]["status"] == "done",
              "сделанные шаги не тронуты, лишних задач не рождено"))
print("  САМОТЕСТ Б:", "PASS" if all(res[-5:]) else "FAIL")

# (В) САМОТЕСТ В: нормальная цепь → keep на каждом стыке, ноль изменений
print("(В) keep: нормальная цепь без изменений:")
fb = fresh(plan="1. раз\n2. два\n3. три")
pid = fb.enqueue_task("Filipp-328-dec", "гладкое ТЗ")["id"]
OD.process_new()
snap_texts = sorted(r["task_text"] for r in fb.by_status("new"))
OD.process_new(); OD.process_new(); OD.process_new()   # три шага → done
sums = fb.summaries(pid)
res.append(ok(fake_run.adapt_calls == 2, "думатель позван РОВНО 2 раза (после шагов 1 и 2, не после 3-го)"))
res.append(ok(len(sums) == 1 and "3/3 шагов done" in sums[0]["result"],
              "сводка 3/3 done — как раньше"))
res.append(ok(not fb.corrected() and not fb.adapt_cards(pid)
              and sorted(r["task_text"] for r in fb.rows.values()
                         if r["task_text"].startswith("[шаг ")) == snap_texts,
              "ноль изменений: ни коррекций, ни карточек, тексты шагов нетронуты"))
print("  САМОТЕСТ В:", "PASS" if all(res[-3:]) else "FAIL")

# (Г) САМОТЕСТ Г: третий adjust → терминальный halt «план дрейфует»
print("(Г) третий adjust → halt «план дрейфует»:")
fb = fresh(plan="1. раз\n2. два\n3. три")
pid = fb.enqueue_task("Filipp-328-dec", "дрейфующее ТЗ")["id"]
OD.process_new()
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
# мок: в цепи УЖЕ было 2 коррекции (маркер K=2 на оставшемся шаге) → следующий adjust = третий
fb.rows[s2]["task_text"] = f"[шаг 2/3 родитель {pid}] [коррекция плана 2] два (после 2-й коррекции)"
fake_run.adapt_queue = [ADJ(["ещё раз переделать всё"], "план снова не сходится")]
OD.process_new()                                     # шаг 1 done → adjust №3 → halt
res.append(ok(fb.rows[s2]["status"] == "failed" and "план дрейфует" in fb.rows[s2]["result"]
              and "нужен владелец" in fb.rows[s2]["result"]
              and "план снова не сходится" in fb.rows[s2]["result"],
              "оставшиеся шаги → терминальный failed «план дрейфует, нужен владелец» с диагнозом"))
res.append(ok(fb.rows[s3]["status"] == "failed", "весь хвост цепи остановлен"))
res.append(ok(not fb.corrected() or all("[коррекция плана 3]" not in r["task_text"] for r in fb.rows.values()),
              "ТРЕТЬЯ коррекция НЕ рождена (лимит 2 на цепь)"))
res.append(ok(fb.rows[s1]["status"] == "done", "сделанный шаг 1 не тронут"))
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "❌" in sums[0]["result"], "сводка пришла, дрейф виден ❌"))
print("  САМОТЕСТ Г:", "PASS" if all(res[-5:]) else "FAIL")

# (Д) САМОТЕСТ Д: PLAN_ADAPT=0 → думатель на done не зовётся вовсе, байт-в-байт прежнее
print("(Д) PLAN_ADAPT=0 → прежнее поведение:")
fb = fresh(adapt="0", plan="1. раз\n2. два\n3. три")
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ при выключенном флаге")["id"]
OD.process_new(); OD.process_new(); OD.process_new(); OD.process_new()
sums = fb.summaries(pid)
res.append(ok(fake_run.adapt_calls == 0, "думатель адаптации НЕ позван ни разу (флаг 0)"))
res.append(ok(len(sums) == 1 and "3/3 шагов done" in sums[0]["result"]
              and not fb.corrected() and not fb.adapt_cards(pid)
              and all("♻️" not in r["result"] and "⏭" not in r["result"] and "🧭" not in r["result"]
                      for r in fb.rows.values()),
              "байт-в-байт прежнее: 3/3 done, ноль следов адаптации"))
print("  САМОТЕСТ Д:", "PASS" if all(res[-2:]) else "FAIL")

# (Е) САМОТЕСТ Е: сбой думателя (мусор/таймаут/пустой adjust/потолок) → keep, цепь не встала
print("(Е) fail-safe думателя → keep, цепь идёт:")
for label, setup in [
    ("мусор-JSON", lambda: fake_run.adapt_queue.append("я не json")),
    ("таймаут", lambda: setattr(fake_run, "adapt_exc", _sp.TimeoutExpired(cmd="claude", timeout=180))),
    ("adjust без шагов", lambda: fake_run.adapt_queue.append('{"verdict":"adjust","adjusted_steps":[],"reason":"пусто"}')),
    ("adjust > потолка", lambda: fake_run.adapt_queue.append(
        ADJ([f"шаг {i}" for i in range(1, 10)], "распухло"))),
]:
    fb = fresh(plan="1. раз\n2. два")
    pid = fb.enqueue_task("Filipp-328-dec", f"ТЗ ({label})")["id"]
    OD.process_new()
    setup()
    OD.process_new(); OD.process_new()
    sums = fb.summaries(pid)
    res.append(ok(len(sums) == 1 and "2/2 шагов done" in sums[0]["result"] and not fb.corrected(),
                  f"{label} → keep: цепь дошла 2/2, коррекций нет"))
print("  САМОТЕСТ Е:", "PASS" if all(res[-4:]) else "FAIL")

# (Ж) совместимость слоёв: провал шага → самопочинка; done шага → адаптация; после 🩹-done
#     исходного шага адаптация НЕ зовётся (реборн того же номера ждёт)
print("(Ж) совместимость с STEP_SELFHEAL:")
fb = fresh(plan="1. раз\n2. два\n3. три")
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ с провалом шага 2")["id"]
OD.process_new()
s1, s2, s3 = sorted(r["id"] for r in fb.by_status("new"))
OD.process_new()                                     # шаг 1 done → адаптация keep
calls_after_1 = fake_run.adapt_calls
fake_run.step_queue = [("", 1)]                      # шаг 2 упадёт
fake_run.heal_out = ('{"verdict":"retry","fixed_step":"шаг два с верным путём","reason":"кривой путь"}')
OD.process_new()                                     # шаг 2 fail → самопочинка → 🩹-done + реборн
res.append(ok(fake_run.heal_calls == 1, "провал шага → думатель самопочинки (слой 1 жив)"))
res.append(ok(fake_run.adapt_calls == calls_after_1,
              "после 🩹-done упавшего шага адаптация НЕ позвана (реборн того же номера ждёт)"))
OD.process_new()                                     # реборн шага 2 → done → адаптация зовётся
res.append(ok(fake_run.adapt_calls == calls_after_1 + 1,
              "после НАСТОЯЩЕГО done реборна адаптация позвана"))
OD.process_new()                                     # шаг 3 → done → сводка
sums = fb.summaries(pid)
res.append(ok(len(sums) == 1 and "3/3 шагов done" in sums[0]["result"],
              "оба слоя вместе: цепь дошла, сводка 3/3"))
print("  СОВМЕСТИМОСТЬ:", "PASS" if all(res[-4:]) else "FAIL")

# (З) осиротевшая карточка адаптации НЕ уходит планировщику как «родитель»
print("(З) осиротевшая карточка:")
fb = fresh()
cid = fb.enqueue_task("Filipp-328-dec", "[коррекция плана родитель 555] карточка адаптации плана")["id"]
OD.process_new()
res.append(ok(fb.rows[cid]["status"] == "done" and "осиротела" in fb.rows[cid]["result"]
              and not fb.by_status("new"),
              "карточка доведена done, план-фанаут по ней НЕ запущен"))

# (И) красное не ослаблено: скорректированный шаг с NEEDS_APPROVAL → кнопка как раньше
print("(И) красное не ослаблено:")
fb = fresh(plan="1. раз\n2. два")
pid = fb.enqueue_task("Filipp-328-dec", "ТЗ с красной коррекцией")["id"]
OD.process_new()
s1, s2 = sorted(r["id"] for r in fb.by_status("new"))
fake_run.adapt_queue = [ADJ(["скорректированный шаг с git push"], "нужен другой финал")]
OD.process_new()                                     # шаг 1 done → adjust
corr = fb.corrected()
fake_run.step_queue = [("NEEDS_APPROVAL: op=git_push | нужен push", 0)]
OD.process_new()                                     # скорректированный шаг → красное
res.append(ok(len(corr) == 1 and fb.rows[corr[0]["id"]]["status"] == "needs_approval",
              "скорректированный шаг с красным → needs_approval-кнопка как раньше"))

os.environ["PLAN_ADAPT"] = "0"
os.environ.pop("STEP_SELFHEAL", None)
OD.subprocess.run = _real_run

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
