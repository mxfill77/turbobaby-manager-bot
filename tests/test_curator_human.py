"""КУРАТОР ЦЕЛИ — ветка human: сводная карточка владельцу (шаг 4/7 родитель 231, 12.07.2026).
Вердикт human задач НЕ ставит: пункт «что нужно от владельца» уходит в ЕДИНУЮ сводную карточку
[куратор владельцу цель G] — synthetic-задачу в статусе needs_approval (devbot несёт такие
карточки в инбокс INBOX_TOPIC_ID, прод 1160). Первая = создание (образец _dec_post_summary:
enqueue → claim → финал, здесь финал = set_needs_approval); новые пункты ТОЙ ЖЕ цели —
правкой result существующей открытой карточки; тот же текст пункта повторно → счётчик ×N
на той же строке, НЕ дубль (дедуп-образец bd5d516). ✅ владельца на карточке = закрыть done
БЕЗ конверта op=other (пункты по определению владельческие); сирота new (демон упал между
enqueue и set_needs_approval) доводится в needs_approval БЕЗ потери пункта (пункт в task_text).
Преамбула куратора ЖЕЛЕЗНО шлёт красные/смок-шаги ТОЛЬКО в human, НИКОГДА в tasks.
Сети/claude нет — bridge и консультация подменены.
Проверки: (1) рендер/парс пунктов + regex-гварды; (2) upsert: создание; (3) дозапись пункта;
(4) дедуп ×N; (5) fail-safe всех сбоев → None; (6) полный цикл human через _maybe_curator
(карточка-отчёт + сводная, продолжения НЕ ставятся, продолжение корня копит в ту же карточку);
(7) сбой upsert → пункт в карточке-отчёте (откат на шаг 2/7); (8) преамбула;
(9) process_approved: ✅ закрывает done без конверта (и до проверки таймаута approved);
(10) сирота new доводится в needs_approval с пунктом; (11) CURATOR=0 → ветка мертва."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"   # принудительная изоляция (load_dotenv грузит боевые значения)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR_SCOPE"] = "0"  # новый флаг (15.07.2026): консультация на всех done/failed

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


class FakeBridge:
    """Мост-очередь в памяти (как в test_curator) + set_needs_approval, тумблеры сбоев
    и журнал enqueue-вызовов."""
    def __init__(s):
        s.rows, s.nid = {}, 200
        s.fail_get = s.fail_enqueue = s.fail_sna = False
        s.enq_calls = []
    def add(s, status, text, frm="Filipp-328", result="", updated="2026-07-12T00:00:00+00:00"):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": updated}
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
        if s.fail_enqueue:
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        if s.fail_sna:
            return {"ok": False, "error": "request_failed"}
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def cards(s, mark="[куратор владельцу цель"):
        return [dict(r) for r in s.rows.values() if str(r["task_text"]).startswith(mark)]
    def spawned(s):
        return [dict(r) for r in s.rows.values() if r["from"] == OD.CURATOR_FROM]


_real_bc, _real_run_task, _real_rp = OD.bc, OD.run_task, OD._restart_pending
_real_consult = OD._curator_consult
OD._restart_pending = lambda: False
OD.MAX_CLAUDE_PROCS = 0; OD.MEM_MIN_MB = 0; OD.CLAUDE_RSS_TOTAL_MB = 0
os.environ["CURATOR"] = "1"

consults = []
def spy_consult(goal, result):
    consults.append((goal, result))
    return spy_consult.verdict
OD._curator_consult = spy_consult

HUMAN = {"verdict": "human", "tasks": [], "human": "нужно «да» на clasp redeploy",
         "reason": "красная зона"}

def setup(verdict=None):
    fb = FakeBridge()
    OD.bc = fb
    OD._curated.clear(); OD._summarized.clear(); consults.clear()
    spy_consult.verdict = dict(verdict or HUMAN)
    return fb


# (1) рендер/парс пунктов + regex-гварды
print("(1) рендер/парс/regex:")
body = OD._curator_human_render(42, [("сделай да на clasp", 1), ("смок на тест-строке", 3)])
res.append(ok(body.startswith("🧑 нужно от владельца (цель 42)"), "заголовок: 🧑 + цель G"))
res.append(ok("1. сделай да на clasp" in body and "2. смок на тест-строке (×3)" in body
              and "(×1)" not in body,
              "пункты нумерованы, ×N только при счётчике >1"))
res.append(ok("✅" in body and "❌" in body and "НЕ ставит" in body,
              "подсказка владельцу: ✅/❌ + «задач не ставит»"))
res.append(ok(OD._curator_human_items(body) == [("сделай да на clasp", 1), ("смок на тест-строке", 3)],
              "round-trip: парс пунктов из рендера (заголовок/подсказка не мешают)"))
res.append(ok(OD._curator_human_items("") == [] and OD._curator_human_items(None) == [],
              "пусто/None → ноль пунктов, не падает"))
m = OD._CURATOR_HUMAN_RE.match("[куратор владельцу цель 77] сделай X")
res.append(ok(m is not None and m.group(1) == "77", "маркер карточки владельцу матчится, G извлекается"))
res.append(ok(OD._CURATOR_CARD_RE.match("[куратор владельцу цель 77] х") is None
              and OD._CURATOR_GOAL_RE.match("[куратор владельцу цель 77] х") is None,
              "маркер владельцу НЕ матчится карточным/бюджетным regex (не путает шаги 2–3/7)"))
res.append(ok(OD._CURATOR_HUMAN_RE.match("[куратор задача 77] вердикт") is None
              and OD._CURATOR_HUMAN_RE.match("[куратор цели 77, шаг 1] х") is None,
              "обратно: чужие маркеры куратора НЕ матчятся human-regex'ом"))

# (2) upsert: создание первой карточки
print("(2) upsert — создание:")
fb = setup()
r = OD._curator_human_upsert(42, "нужно «да» на clasp redeploy")
cards = fb.cards()
res.append(ok(r is not None and r[1] == "created" and len(cards) == 1 and r[0] == cards[0]["id"],
              "нет открытой карточки → создана, возврат (id, created)"))
res.append(ok(cards[0]["status"] == "needs_approval",
              "карточка в needs_approval (devbot унесёт её в инбокс INBOX_TOPIC_ID)"))
res.append(ok(cards[0]["task_text"] == "[куратор владельцу цель 42] нужно «да» на clasp redeploy",
              "task_text = маркер + пункт (сирота доводится без потери пункта)"))
res.append(ok(cards[0]["from"] == "Filipp-328-dec",
              "from=-dec: synthetic-задача демона (образец _dec_post_summary)"))
res.append(ok("1. нужно «да» на clasp redeploy" in cards[0]["result"]
              and "цель 42" in cards[0]["result"],
              "тело: заголовок с целью + пункт №1"))
long_item = "x" * 900
fb = setup()
r = OD._curator_human_upsert(7, long_item)
res.append(ok(r is not None and ("x" * OD.CURATOR_TASK_MAX) + "\n" in fb.cards()[0]["result"] + "\n"
              and ("x" * (OD.CURATOR_TASK_MAX + 1)) not in fb.cards()[0]["result"],
              "пункт длиннее 400 режется до CURATOR_TASK_MAX"))
fb = setup()
r = OD._curator_human_upsert(7, "  ")
res.append(ok(r is not None and "(куратор не уточнил)" in fb.cards()[0]["result"],
              "пустой пункт → заглушка «(куратор не уточнил)»"))

# (3) дозапись пункта в существующую открытую карточку
print("(3) upsert — дозапись:")
fb = setup()
r1 = OD._curator_human_upsert(42, "пункт первый")
r2 = OD._curator_human_upsert(42, "пункт второй")
cards = fb.cards()
res.append(ok(len(cards) == 1 and r2 == (r1[0], "edited"),
              "второй пункт той же цели → ТА ЖЕ карточка (edited), новой задачи нет"))
res.append(ok("1. пункт первый" in cards[0]["result"] and "2. пункт второй" in cards[0]["result"],
              "оба пункта в теле, нумерация сквозная"))
res.append(ok(len(fb.enq_calls) == 1, "enqueue звался один раз (правка — без новой задачи)"))
fb.rows[r1[0]]["status"] = "done"   # владелец закрыл карточку
r3 = OD._curator_human_upsert(42, "пункт третий")
res.append(ok(r3 is not None and r3[1] == "created" and len(fb.cards()) == 2,
              "закрытая (done) карточка не редактируется → новый пункт = НОВАЯ карточка"))

# (4) дедуп: тот же текст пункта → ×N, не дубль
print("(4) дедуп пунктов (образец bd5d516):")
fb = setup()
r1 = OD._curator_human_upsert(42, "нужно «да» на clasp")
r2 = OD._curator_human_upsert(42, "нужно «да» на clasp")
cards = fb.cards()
res.append(ok(r2 == (r1[0], "dedup") and len(cards) == 1,
              "повтор пункта → возврат dedup, карточка та же"))
res.append(ok("1. нужно «да» на clasp (×2)" in cards[0]["result"]
              and "2." not in cards[0]["result"],
              "строка одна со счётчиком ×2, дубль-строки нет"))
OD._curator_human_upsert(42, "нужно «да» на clasp")
res.append(ok("(×3)" in fb.cards()[0]["result"], "третий повтор → ×3 (счётчик растёт правкой)"))
OD._curator_human_upsert(42, "другой пункт")
b = fb.cards()[0]["result"]
res.append(ok("1. нужно «да» на clasp (×3)" in b and "2. другой пункт" in b,
              "после дедупа новый ДРУГОЙ пункт дописывается отдельной строкой"))

# (5) fail-safe: любой сбой → None, без падения
print("(5) fail-safe upsert:")
fb = setup(); fb.fail_get = True
res.append(ok(OD._curator_human_upsert(42, "пункт") is None and fb.cards() == [],
              "get_pending падает → None, карточка не создаётся"))
fb = setup(); fb.fail_enqueue = True
res.append(ok(OD._curator_human_upsert(42, "пункт") is None,
              "enqueue-fail → None"))
fb = setup(); fb.fail_sna = True
r = OD._curator_human_upsert(42, "пункт")
res.append(ok(r is None and len(fb.cards()) == 1 and fb.cards()[0]["status"] == "in_progress",
              "set_needs_approval-fail на создании → None (остов доведёт реапер/сирота-хендлер)"))
class Broken:                         # моста нет вовсе (AttributeError внутри)
    def get_pending(s, status="new", lane=None): raise RuntimeError("boom")
OD.bc = Broken()
res.append(ok(OD._curator_human_upsert(42, "пункт") is None,
              "исключение моста → None (try/except, не падает)"))

# (6) полный цикл human через _maybe_curator
print("(6) _maybe_curator, вердикт human:")
fb = setup()
t = fb.add("done", "тз: цель с красным хвостом")
OD._maybe_curator("задача", t, "тз: цель с красным хвостом", "итог")
rep = fb.cards("[куратор задача")
hum = fb.cards()
res.append(ok(fb.spawned() == [] , "human → НОЛЬ followup-задач (from=Filipp-curator нет)"))
res.append(ok(len(hum) == 1 and hum[0]["status"] == "needs_approval"
              and hum[0]["task_text"].startswith(f"[куратор владельцу цель {t}]")
              and "нужно «да» на clasp redeploy" in hum[0]["result"],
              "пункт human ушёл в сводную карточку владельцу (цель = корень терминала)"))
res.append(ok(len(rep) == 1 and rep[0]["status"] == "done"
              and "требует владельца" in rep[0]["result"]
              and f"задача {hum[0]['id']}" in rep[0]["result"]
              and "создана сводная карточка" in rep[0]["result"],
              "карточка-отчёт в 328: done, ссылка на id сводной карточки"))
spy_consult.verdict = {"verdict": "human", "tasks": [], "human": "проверь живую бронь руками",
                       "reason": "смок"}
f2 = fb.add("done", f"[куратор цели {t}, шаг 1] дожать хвост", frm=OD.CURATOR_FROM)
OD._maybe_curator("задача", f2, f"[куратор цели {t}, шаг 1] дожать хвост", "итог продолжения")
hum = fb.cards()
res.append(ok(len(hum) == 1 and "1. нужно «да» на clasp redeploy" in hum[0]["result"]
              and "2. проверь живую бронь руками" in hum[0]["result"],
              "human на ПРОДОЛЖЕНИИ корня → пункт в ТУ ЖЕ карточку (корень из маркера цели)"))

# (7) сбой upsert внутри _maybe_curator → откат на карточку-полотно (шаг 2/7)
print("(7) откат при сбое upsert:")
fb = setup()
t = fb.add("done", "тз: цель")
_orig_get = fb.get_pending
def flaky_get(status="new", lane=None):
    # роняем ТОЛЬКО опрос needs_approval (upsert); сканы дедупа (done,new,in_progress) живут
    if "needs_approval" in str(status):
        return {"ok": False, "error": "request_failed"}
    return _orig_get(status, lane)
fb.get_pending = flaky_get
OD._maybe_curator("задача", t, "тз: цель", "итог")
rep = fb.cards("[куратор задача")
res.append(ok(fb.cards() == [] and len(rep) == 1 and rep[0]["status"] == "done"
              and "НЕ встала" in rep[0]["result"]
              and "нужно «да» на clasp redeploy" in rep[0]["result"],
              "upsert None → пункт остаётся в карточке-отчёте, цикл не падает"))

# (8) преамбула: красные/смок-шаги ТОЛЬКО в human
print("(8) преамбула куратора:")
res.append(ok("ТОЛЬКО в human" in OD.CURATOR_PREAMBLE and "НИКОГДА в tasks" in OD.CURATOR_PREAMBLE,
              "ЖЕЛЕЗНО закреплено: красное — только в human, никогда в tasks"))
res.append(ok("смок" in OD.CURATOR_PREAMBLE and "clasp" in OD.CURATOR_PREAMBLE,
              "смок-шаги и clasp названы явно"))

# (9) process_approved: ✅ владельца = РАЗРЕШЕНИЕ → задача на исполнение пунктов
# ПЕРЕПИСАНО 31.07.2026 (класс карточек 95/100): прежний контракт «✅ → done без исполнения»
# и был дефектом — «да» на операцию молча не рождало работы. Живой регресс на дословных
# карточках 95/100 — tests/test_curator_human_exec.py.
print("(9) ✅ на сводной карточке:")
fb = setup()
cid = fb.add("approved", "[куратор владельцу цель 42] нужно да",
             frm="Filipp-328-dec", result="🧑 нужно от владельца (цель 42)…\n1. нужно да")
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done" and "задача id" in fb.rows[cid]["result"],
              "✅ (approved) → карточка done со ссылкой на задачу-исполнителя"))
res.append(ok(len(fb.enq_calls) == 1 and OD._is_convert(fb.enq_calls[0][1])
              and "нужно да" in fb.enq_calls[0][1],
              "задача поставлена, текст — конверт с пунктом (разрыв петли готовым контуром)"))
fb = setup()
cid = fb.add("approved", "[куратор владельцу цель 42] нужно да", frm="Filipp-328-dec",
             result="🧑 …", updated="2026-01-01T00:00:00+00:00")
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done" and "истёк" not in fb.rows[cid]["result"]
              and len(fb.enq_calls) == 1,
              "гвард ДО таймаута approved: старая карточка не гибнет «approve истёк»"))

# (10) сирота new (демон упал между enqueue и set_needs_approval) → доводится с пунктом
print("(10) сирота-хендлер:")
fb = setup()
ran = []
OD.run_task = lambda tid, txt, task_timeout=600, preamble=None: (ran.append(int(tid)) or ("done", "x"))
oid = fb.add("new", "[куратор владельцу цель 42] нужно «да» на clasp", frm="Filipp-328-dec")
OD.process_new()
res.append(ok(fb.rows[oid]["status"] == "needs_approval"
              and "1. нужно «да» на clasp" in fb.rows[oid]["result"]
              and "цель 42" in fb.rows[oid]["result"],
              "сирота доведена в needs_approval, пункт из task_text не потерян"))
res.append(ok(ran == [] and not any("[шаг" in str(r["task_text"]) for r in fb.rows.values()),
              "claude не зовётся, планировщику сирота не уходит"))
OD.run_task = _real_run_task

# (11) CURATOR=0 → ветка мертва целиком
print("(11) CURATOR=0:")
os.environ["CURATOR"] = "0"
fb = setup()
t = fb.add("done", "тз: цель")
OD._maybe_curator("задача", t, "тз: цель", "итог")
res.append(ok(consults == [] and fb.cards() == [] and fb.cards("[куратор") == [],
              "CURATOR=0 → ни консультаций, ни карточек (в т.ч. владельцу)"))
os.environ["CURATOR"] = "1"

OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_rp
OD._curator_consult = _real_consult
OD._curated.clear(); OD._summarized.clear()
os.environ.pop("CURATOR", None)

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
