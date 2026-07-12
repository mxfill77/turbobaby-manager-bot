"""КУРАТОР ЦЕЛИ — ветка followup: постановка продолжений + бюджеты (шаг 3/7 родитель 231).
Каждое ТЗ вердикта followup → задача from=Filipp-curator ТОЙ ЖЕ полосы (vps, дефолт enqueue)
с маркером [куратор цели G, шаг m] (G = id корневой задачи/родителя цепи, m — сквозной номер
по корню); вторая глубина несёт тег [глубина 2]. Бюджеты restart-proof ИЗ МАРКЕРОВ очереди
(один CSV-опрос get_pending): ≤3 продолжений на корень, глубина ≤2, ≤10 куратор-задач/сутки
(UTC); превышение / сбой опроса / enqueue-fail → ТЗ в карточку владельцу (НЕ поставлено),
без падения и без петли. Терминал followup-задачи снова курируется (даёт глубину 2);
таймаут Filipp-curator = дев (45 мин). Сети/claude нет — bridge и консультация подменены.
Проверки: (1) постановка+маркер+from+полоса+карточка; (2) сквозная нумерация шага по корню;
(3) наследование корня + тег глубины 2; (4) запрет глубины 3; (5) лимит корня (вкл. частичную
постановку); (6) суточный лимит (вчерашние не в счёт, нечитаемый created — консервативно в
счёт); (7) enqueue-fail → refused, остальные ставятся; (8) сбой опроса очереди → ноль
постановок, карточка объясняет; (9) human/closed → ноль постановок; (10) терминал
Filipp-curator курируется, сама задача исполняется штатно (не карточка/не dec);
(11) таймаут; (12) regex-гварды (match/search, карточный regex не путается с маркером цели)."""
import datetime
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("STEP_SELFHEAL", "0")  # изоляция от боевого .env
os.environ.setdefault("PLAN_ADAPT", "0")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD

_TODAY = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT03:00:00Z")
_YESTERDAY = (datetime.datetime.now(datetime.timezone.utc) -
              datetime.timedelta(days=1)).strftime("%Y-%m-%dT03:00:00Z")


class FakeBridge:
    """Мост-очередь в памяти (как в test_curator) + created у строк, тумблеры сбоев enqueue/get
    и журнал enqueue-вызовов (from/text/lane)."""
    def __init__(s):
        s.rows, s.nid = {}, 200
        s.fail_enqueue, s.fail_get, s.enq_calls = 0, False, []
    def add(s, status, text, frm="Filipp-328", result="", created=None):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "created": created or _TODAY,
                         "updated": "2026-07-12T00:00:00+00:00"}
        return s.nid
    def get_pending(s, status="new", lane=None):
        if s.fail_get:
            return {"ok": False, "error": "request_failed"}
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text, lane))
        if s.fail_enqueue > 0:
            s.fail_enqueue -= 1
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def task_heartbeat(s, tid): return {"ok": True}
    def cards(s, mark="[куратор задача"):
        return [dict(r) for r in s.rows.values() if str(r["task_text"]).startswith(mark)]
    def spawned(s):
        return sorted((dict(r) for r in s.rows.values()
                       if r["from"] == OD.CURATOR_FROM), key=lambda x: x["id"])


_real_bc, _real_run_task, _real_rp = OD.bc, OD.run_task, OD._restart_pending
_real_consult = OD._curator_consult
OD._restart_pending = lambda: False
os.environ["CURATOR"] = "1"

consults = []
def spy_consult(goal, result):
    consults.append((goal, result))
    return spy_consult.verdict
OD._curator_consult = spy_consult


def setup(verdict=None):
    fb = FakeBridge()
    OD.bc = fb
    OD._curated.clear(); OD._summarized.clear(); consults.clear()
    spy_consult.verdict = verdict or {"verdict": "followup", "tasks": ["дожать хвост А"],
                                      "human": "", "reason": "хвост"}
    return fb


# (1) постановка followup: маркер, from, полоса, карточка-отчёт
print("(1) постановка продолжений:")
fb = setup(verdict={"verdict": "followup", "tasks": ["дожать хвост А", "дожать хвост Б"],
                    "human": "", "reason": "два хвоста"})
t = fb.add("done", "тз: почини рендер")
OD._maybe_curator("задача", t, "тз: почини рендер", "итог с хвостами")
sp = fb.spawned()
res.append(ok(len(sp) == 2
              and sp[0]["task_text"] == f"[куратор цели {t}, шаг 1] дожать хвост А"
              and sp[1]["task_text"] == f"[куратор цели {t}, шаг 2] дожать хвост Б",
              "два ТЗ → две задачи с маркером [куратор цели G, шаг m], сквозная нумерация"))
res.append(ok(all(x["from"] == "Filipp-curator" and x["status"] == "new" for x in sp),
              "from=Filipp-curator, задачи в new (демон исполнит штатно)"))
res.append(ok(all(c[2] is None for c in fb.enq_calls),
              "enqueue без lane-kwarg → полоса vps (та же, что у терминала)"))
res.append(ok("[глубина 2]" not in sp[0]["task_text"] and "[глубина 2]" not in sp[1]["task_text"],
              "первая глубина — без тега [глубина 2]"))
cards = fb.cards()
res.append(ok(len(cards) == 1 and cards[0]["status"] == "done"
              and f"задача id {sp[0]['id']}: дожать хвост А" in cards[0]["result"]
              and f"задача id {sp[1]['id']}: дожать хвост Б" in cards[0]["result"]
              and "поставлены продолжения" in cards[0]["result"],
              "карточка-отчёт: id и текст каждого поставленного продолжения"))
res.append(ok("НЕ поставлено" not in cards[0]["result"],
              "всё встало → секции «НЕ поставлено» в карточке нет"))
fb = setup()
pid = fb.add("done", "декомпозируй: собери фичу", frm="Filipp-328-dec")
OD._maybe_curator("родитель", pid, "декомпозируй: собери фичу", "сводка")
sp = fb.spawned()
res.append(ok(len(sp) == 1 and sp[0]["task_text"] == f"[куратор цели {pid}, шаг 1] дожать хвост А",
              "терминал-родитель цепи: корень = id родителя"))

# (2) сквозная нумерация шага по корню — restart-proof из маркеров
print("(2) нумерация шага из маркеров очереди:")
fb = setup()
t = fb.add("done", "тз: цель")
fb.add("done", f"[куратор цели {t}, шаг 1] старое продолжение", frm="Filipp-curator")
OD._maybe_curator("задача", t, "тз: цель", "итог")
sp = [x for x in fb.spawned() if "старое" not in x["task_text"]]
res.append(ok(len(sp) == 1 and sp[0]["task_text"].startswith(f"[куратор цели {t}, шаг 2]"),
              "в очереди шаг 1 → новое продолжение получает шаг 2 (память не нужна)"))

# (3) терминал-продолжение: корень наследуется, вторая глубина с тегом
print("(3) наследование корня, глубина 2:")
fb = setup(verdict={"verdict": "followup", "tasks": ["ещё дожим"], "human": "", "reason": "r"})
x = fb.add("done", "[куратор цели 500, шаг 1] дожать хвост", frm="Filipp-curator")
OD._maybe_curator("задача", x, "[куратор цели 500, шаг 1] дожать хвост", "итог")
sp = [r for r in fb.spawned() if r["id"] != x]
res.append(ok(len(sp) == 1 and sp[0]["task_text"] == "[куратор цели 500, шаг 2][глубина 2] ещё дожим",
              "корень 500 (не id терминала), шаг max+1, тег [глубина 2]"))
res.append(ok(OD._curator_root_depth("задача", x, "[куратор цели 500, шаг 1] дожать") == (500, 2),
              "_curator_root_depth: продолжение → (корень, глубина 2)"))

# (4) глубина 3 запрещена
print("(4) запрет глубины 3:")
fb = setup(verdict={"verdict": "followup", "tasks": ["третья волна"], "human": "", "reason": "r"})
x = fb.add("done", "[куратор цели 500, шаг 2][глубина 2] дожим дожима", frm="Filipp-curator")
OD._maybe_curator("задача", x, "[куратор цели 500, шаг 2][глубина 2] дожим дожима", "итог")
res.append(ok([r for r in fb.spawned() if r["id"] != x] == [],
              "терминал глубины 2 → продолжений НЕТ"))
cards = fb.cards()
res.append(ok(len(cards) == 1 and "глубина" in cards[0]["result"]
              and "третья волна" in cards[0]["result"] and "НЕ поставлено" in cards[0]["result"],
              "карточка владельцу: ТЗ в списке «НЕ поставлено», причина — глубина"))

# (5) лимит корня ≤3 (вкл. частичную постановку)
print("(5) лимит корня:")
fb = setup(verdict={"verdict": "followup", "tasks": ["четвёртое"], "human": "", "reason": "r"})
t = fb.add("done", "тз: цель")
for i in (1, 2, 3):
    fb.add("done", f"[куратор цели {t}, шаг {i}] старое {i}", frm="Filipp-curator")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(len(fb.spawned()) == 3, "3 продолжения уже были → новое НЕ ставится"))
cards = fb.cards()
res.append(ok(len(cards) == 1 and "лимит корня" in cards[0]["result"]
              and "четвёртое" in cards[0]["result"],
              "карточка: причина «лимит корня», ТЗ не потеряно"))
fb = setup(verdict={"verdict": "followup", "tasks": ["всё-таки А", "лишнее Б"],
                    "human": "", "reason": "r"})
t = fb.add("done", "тз: цель")
for i in (1, 2):
    fb.add("failed", f"[куратор цели {t}, шаг {i}] старое {i}", frm="Filipp-curator")
OD._maybe_curator("задача", t, "тз: цель", "итог")
sp = [x for x in fb.spawned() if "старое" not in x["task_text"]]
res.append(ok(len(sp) == 1 and sp[0]["task_text"] == f"[куратор цели {t}, шаг 3] всё-таки А",
              "2 из 3 потрачено (счёт по ЛЮБОМУ статусу, failed тоже) → встаёт ровно одно"))
res.append(ok("лишнее Б" in fb.cards()[0]["result"] and "НЕ поставлено" in fb.cards()[0]["result"],
              "второе ТЗ — в карточку (частичная постановка честно отчитана)"))

# (6) суточный лимит ≤10 (UTC), вчерашние не в счёт, нечитаемый created — в счёт
print("(6) суточный лимит:")
fb = setup()
t = fb.add("done", "тз: цель")
for i in range(10):
    fb.add("done", f"[куратор цели {900 + i}, шаг 1] чужое {i}", frm="Filipp-curator")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(len(fb.spawned()) == 10 and "суточный лимит" in fb.cards()[0]["result"],
              "10 куратор-задач за сегодня (все корни) → новое НЕ ставится, карточка"))
fb = setup()
t = fb.add("done", "тз: цель")
for i in range(10):
    fb.add("done", f"[куратор цели {900 + i}, шаг 1] чужое {i}", frm="Filipp-curator",
           created=_YESTERDAY)
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(len([x for x in fb.spawned() if "чужое" not in x["task_text"]]) == 1,
              "те же 10, но вчерашние → сегодняшний бюджет свободен, продолжение встаёт"))
fb = setup()
t = fb.add("done", "тз: цель")
for i in range(10):
    fb.add("done", f"[куратор цели {900 + i}, шаг 1] чужое {i}", frm="Filipp-curator",
           created="мусор-не-дата")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(len(fb.spawned()) == 10,
              "created нечитаем → консервативно «сегодня» (в сторону лимита, не спама)"))

# (7) enqueue-fail → ТЗ в refused, остальные ставятся, без падения
print("(7) enqueue-fail:")
fb = setup(verdict={"verdict": "followup", "tasks": ["первое", "второе"],
                    "human": "", "reason": "r"})
t = fb.add("done", "тз: цель")
fb.fail_enqueue = 2               # 1-й сбой съест карточку… нет: карточка ставится ДО spawn —
fb.fail_enqueue = 0               # …поэтому сбой имитируем точечно на первом продолжении
_orig_enq = fb.enqueue_task
def flaky_enq(frm, text, lane=None):
    if frm == OD.CURATOR_FROM and "первое" in text:
        fb.enq_calls.append((frm, text, lane))
        return {"ok": False, "error": "request_failed"}
    return _orig_enq(frm, text, lane=lane)
fb.enqueue_task = flaky_enq
OD._maybe_curator("задача", t, "тз: цель", "итог")
sp = fb.spawned()
res.append(ok(len(sp) == 1 and sp[0]["task_text"] == f"[куратор цели {t}, шаг 1] второе",
              "сбой enqueue первого → второе ставится, номер шага не дырявится"))
res.append(ok("первое — enqueue не прошёл" in fb.cards()[0]["result"],
              "упавшее ТЗ — в карточке с причиной enqueue-fail"))

# (8) сбой опроса очереди → бюджет не доказан → ноль постановок, карточка объясняет
print("(8) сбой опроса очереди:")
fb = setup()
t = fb.add("done", "тз: цель")
fb.fail_get = True
OD._maybe_curator("задача", t, "тз: цель", "итог")
fb.fail_get = False
res.append(ok(fb.spawned() == [] and len(fb.cards()) == 1
              and "бюджет не доказать" in fb.cards()[0]["result"],
              "get_pending падает → ничего не ставим (fail-safe), ТЗ в карточке"))

# (9) human/closed → ноль постановок
print("(9) human/closed без постановки:")
fb = setup(verdict={"verdict": "human", "tasks": [], "human": "нужно да", "reason": "красное"})
t = fb.add("done", "тз: цель")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(fb.spawned() == [] and "требует владельца" in fb.cards()[0]["result"],
              "human → карточка без задач"))
fb = setup(verdict={"verdict": "closed", "tasks": [], "human": "", "reason": "ок"})
t = fb.add("done", "тз: цель")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(fb.spawned() == [] and fb.cards() == [], "closed → тишина, ноль задач"))
os.environ["CURATOR"] = "0"
fb = setup()
t = fb.add("done", "тз: цель")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(consults == [] and fb.spawned() == [] and fb.cards() == [],
              "CURATOR=0 → ветка мертва целиком"))
os.environ["CURATOR"] = "1"

# (10) followup-задача в очереди: исполняется штатно, её терминал снова курируется
print("(10) жизненный цикл followup-задачи:")
fb = setup(verdict={"verdict": "closed", "tasks": [], "human": "", "reason": "ок"})
ran = []
OD.run_task = lambda tid, txt, task_timeout=600, preamble=None: (
    ran.append((int(tid), txt, task_timeout)) or ("done", "дожал"))
q = fb.add("new", "[куратор цели 500, шаг 1] дожать хвост", frm="Filipp-curator")
OD.process_new()
res.append(ok(ran and ran[0][0] == q and fb.rows[q]["status"] == "done",
              "followup-задача НЕ карточка/НЕ dec: claim → run_task → done штатно"))
res.append(ok(ran[0][2] == OD.TASK_TIMEOUT_DEV,
              "…с дев-таймаутом (45 мин): куратор ставит дев-ТЗ"))
res.append(ok(len(consults) == 1 and consults[0][0] == "[куратор цели 500, шаг 1] дожать хвост",
              "терминал followup-задачи курируется (вторая глубина возможна)"))

# (11) таймаут по метке from
print("(11) _task_timeout:")
res.append(ok(OD._task_timeout({"from": "Filipp-curator"}) == OD.TASK_TIMEOUT_DEV,
              "Filipp-curator → TASK_TIMEOUT_DEV"))
res.append(ok(OD._task_timeout({"from": "Filipp-328"}) == OD.TASK_TIMEOUT,
              "Filipp-328 → быстрый таймаут (не задет)"))

# (12) regex-гварды
print("(12) regex-гварды:")
reborn = "[самопочинка задачи 9, попытка 1] [куратор цели 5, шаг 1] дожать"
res.append(ok(OD._CURATOR_GOAL_RE.match(reborn) is None,
              "перерождение самопочинки НЕ считается в бюджет (match от начала)"))
res.append(ok(OD._curator_root_depth("задача", 9, reborn) == (5, 2),
              "…но корень/глубина из перерождения трассируются (search)"))
res.append(ok(OD._CURATOR_CARD_RE.match("[куратор цели 5, шаг 1] х") is None,
              "маркер цели НЕ матчится карточным regex (сирот-хендлер её не съест)"))
res.append(ok(OD._curator_root_depth("задача", 7, "тз: обычная задача") == (7, 1),
              "терминал без маркера → корень = сам терминал, глубина 1"))
res.append(ok(OD._curator_root_depth("родитель", 44, "[куратор цели 5, шаг 1] х") == (44, 1),
              "родитель цепи — всегда корень (маркер в его тексте игнорируется)"))

OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_rp
OD._curator_consult = _real_consult
OD._curated.clear(); OD._summarized.clear()
os.environ.pop("CURATOR", None)

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
