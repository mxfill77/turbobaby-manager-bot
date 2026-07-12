"""Пометка «(повтор)» на клон-карточках (микрофикс §7 12.07.2026, класс 7ff92fb / инцидент 156).

Клон возврата из-под чужого рестарта (_requeue_foreign_restart) ставился в очередь ДОСЛОВНО —
владелец видел в 328 «задвоение карточки»: карточка клона неотличима от новой задачи. Фикс:
демон дописывает маркер «[повтор задачи N]» в КОНЕЦ текста клона (стартовые маркеры [шаг i/N]
и [конверт…] не сдвигаются), devbot по маркеру ставит «(повтор)» в заголовок карточек
(done/failed-рапорт и анонс «в работе»). Сеть/бот/Bridge замоканы, пушей нет.
"""
import os, sys, asyncio, datetime

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"       # изоляция от боевого .env
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)
os.environ.setdefault("PRETOOL_NOPUSH", "1")

import orchestrator_daemon as OD
import devbot as DB


def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    def __init__(s):
        s.rows, s.nid, s.enqueue_fail = {}, 200, False
        s.enqueued = []                      # (frm, text) в порядке постановки
    def enqueue_task(s, frm, txt, lane=None):
        if s.enqueue_fail:
            return {"ok": False, "error": "queue_down"}
        s.nid += 1
        s.enqueued.append((frm, txt))
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def complete_task(s, tid, status, result=""):
        s.rows.setdefault(int(tid), {"id": int(tid)})
        s.rows[int(tid)].update({"status": status, "result": result, "updated": now_iso()})
        return {"ok": True}


# ===== (1) демон: рождение клона несёт маркер повтора В КОНЦЕ =====
print("(1) _requeue_foreign_restart: маркер повтора в конце текста клона:")
fb = FakeBridge(); OD.bc = fb
PLAIN = "тз: поправь опечатку в prompts.py и прогони тесты"
OD._requeue_foreign_restart(41, "Filipp-328-dev", PLAIN, "🔄 чужой рестарт")
frm, clone = fb.enqueued[0]
res.append(ok(clone.startswith(PLAIN), "текст клона начинается с исходного ДОСЛОВНО"))
res.append(ok(clone.endswith(f"{OD.REPEAT_MARK} 41]"), "маркер «[повтор задачи 41]» в КОНЦЕ"))
res.append(ok(frm == "Filipp-328-dev", "полоса from сохранена"))
orig = fb.rows.get(41, {})
res.append(ok(orig.get("status") == "done" and "Возвращена в очередь" in orig.get("result", ""),
              "исходная закрыта done с маркер-картой возврата (как раньше)"))

# шаг декомпозера: стартовый маркер [шаг i/N родитель id] НЕ сдвинут — _STEP_RE его видит
fb = FakeBridge(); OD.bc = fb
STEP = "[шаг 2/4 родитель 150] сделай кусок 2"
OD._requeue_foreign_restart(152, "Filipp-328-dec", STEP, "🔄 чужой рестарт")
_, clone2 = fb.enqueued[0]
m = OD._STEP_RE.match(clone2)
res.append(ok(m is not None and m.group(1) == "2" and m.group(3) == "150",
              "клон шага: [шаг i/N родитель id] остался ПЕРВЫМ (_STEP_RE.match жив)"))
res.append(ok(clone2.endswith(f"{OD.REPEAT_MARK} 152]"), "и маркер повтора — в конце"))

# клон клона: маркер НЕ дублируется
fb = FakeBridge(); OD.bc = fb
OD._requeue_foreign_restart(43, "Filipp-328", clone, "🔄 чужой рестарт снова")
_, clone3 = fb.enqueued[0]
res.append(ok(clone3 == clone, "повторный возврат клона: второй маркер НЕ дописан (текст тот же)"))
res.append(ok(clone3.count(OD.REPEAT_MARK) == 1, "маркер в тексте ровно один"))

# enqueue-fail: прежний честный failed, без потери задачи
fb = FakeBridge(); fb.enqueue_fail = True; OD.bc = fb
OD._requeue_foreign_restart(44, "Filipp-328", PLAIN, "🔄")
r44 = fb.rows.get(44, {})
res.append(ok(r44.get("status") == "failed" and "не встал" in r44.get("result", ""),
              "клон не встал → честный failed (регресс цел)"))


# ===== (2) devbot: «(повтор)» в заголовке карточек =====
print("(2) devbot: заголовки карточек клона:")
SENDS = []

class FakeBot:
    async def send_message(self, **kw):
        SENDS.append(kw.get("text") or "")

class Ctx:
    bot = FakeBot()

class ReportBridge:
    """get_pending по статусам (без multi — фоллбэк devbot по-статусно)."""
    def __init__(s, items_by_status):
        s.by = items_by_status
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": list(s.by.get(status, []))}

def _reset(by):
    SENDS.clear()
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._report_seeded = True
    DB.BRIDGE = ReportBridge(by)

def run():
    asyncio.run(DB.report_results(Ctx()))

CLONE_TEXT = f"тз: поправь опечатку\n{DB.REPEAT_MARK} 41]"

# done-рапорт клона → «(повтор)» в заголовке
_reset({"done": [{"id": 45, "from": DB.QUEUE_FROM_DEV, "task_text": CLONE_TEXT,
                  "status": "done", "result": "сделано", "updated": now_iso()}]})
run()
res.append(ok(any(s.startswith("✅ Задача 45 (повтор) — done") for s in SENDS),
              "done-карточка клона: «✅ Задача 45 (повтор) — done»"))

# failed-рапорт клона → тоже с пометкой
_reset({"failed": [{"id": 46, "from": DB.QUEUE_FROM, "task_text": CLONE_TEXT,
                    "status": "failed", "result": "упало", "updated": now_iso()}]})
run()
res.append(ok(any(s.startswith("❌ Задача 46 (повтор) — failed") for s in SENDS),
              "failed-карточка клона: «❌ Задача 46 (повтор) — failed»"))

# анонс «в работе» клона → с пометкой
_reset({"in_progress": [{"id": 47, "from": DB.QUEUE_FROM_DEV, "task_text": CLONE_TEXT,
                         "status": "in_progress", "updated": now_iso()}]})
run()
res.append(ok(any(s.startswith("🔄 Задача 47 (повтор) в работе") for s in SENDS),
              "анонс in_progress клона: «🔄 Задача 47 (повтор) в работе…»"))

# ОБЫЧНАЯ задача (без маркера) → заголовки байт-в-байт прежние, «(повтор)» нигде нет
_reset({"done": [{"id": 48, "from": DB.QUEUE_FROM, "task_text": "тз: новая задача",
                  "status": "done", "result": "сделано", "updated": now_iso()}],
        "in_progress": [{"id": 49, "from": DB.QUEUE_FROM, "task_text": "тз: ещё одна",
                         "status": "in_progress", "updated": now_iso()}]})
run()
res.append(ok(any(s.startswith("✅ Задача 48 — done") for s in SENDS),
              "обычный done: заголовок прежний, без пометки"))
res.append(ok(any(s.startswith("🔄 Задача 49 в работе") for s in SENDS),
              "обычный in_progress: заголовок прежний, без пометки"))
res.append(ok(not any("(повтор)" in s for s in SENDS), "«(повтор)» на обычных задачах НЕ появился"))

# константы демона и devbot не разъехались
res.append(ok(OD.REPEAT_MARK == DB.REPEAT_MARK, "REPEAT_MARK демона == REPEAT_MARK devbot"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
