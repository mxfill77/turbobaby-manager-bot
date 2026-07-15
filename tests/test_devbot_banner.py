"""Плашка продолжения в done/failed-карточках devbot (задача N):
_build_banner: fail-safe / активные / куратор / конверт / завершено;
report_results: баннер дописан последней строкой каждой карточки;
_check_curator_pending: редактирует «оценивает» после вердикта / таймаута.
Сеть / Telegram / время не нужны — всё мокнуто."""
import asyncio, os, sys, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["CURATOR"] = "0"   # куратор выключен по умолчанию

import devbot as DB

ok_c, fail_c = [0], [0]

def ok(cond, label):
    if cond:
        ok_c[0] += 1; print(f"  PASS {label}")
    else:
        fail_c[0] += 1; print(f"  FAIL {label}")
    return cond


def _mk_by(**kwargs):
    by = {st: [] for st in DB._REPORT_STATUSES}
    for st, items in kwargs.items():
        by[st] = list(items)
    return by


def _item(id, frm, st="done", lane=None, text="", result="ok"):
    it = {"id": id, "from": frm, "status": st, "task_text": text, "result": result}
    if lane:
        it["lane"] = lane
    return it


def _reset():
    DB._reported.clear(); DB._asked.clear()
    DB._inprogress_seen.clear(); DB._stalled.clear()
    DB._curator_pending.clear(); DB._report_seeded = True


# ── B1. fail-safe: by=None → «недоступно» (НЕ «завершено») ──────────────────
print("B1. fail-safe (by=None):")
b = DB._build_banner(1, "", "Filipp-328", None)
ok("недоступно" in b and "статус" in b, "by=None → недоступно, не завершено")
ok("ЗАВЕРШЕНО" not in b, "by=None: «завершено» запрещено без данных")

# ── B2. активная vps-задача ───────────────────────────────────────────────────
print("B2. активная vps-задача:")
by = _mk_by(new=[_item(9, DB.QUEUE_FROM, "new")])
b = DB._build_banner(1, "", "Filipp-328", by)
ok("Работа продолжается" in b, "active vps → «Работа продолжается»")
ok("vps 1" in b, "счётчик vps=1")
ok("(9)" in b, "id задачи 9 в плашке (≤3)")

# ── B3. активная pc-задача ────────────────────────────────────────────────────
print("B3. активная pc-задача:")
by = _mk_by(in_progress=[_item(7, DB.QUEUE_FROM, "in_progress", lane="pc")])
b = DB._build_banner(1, "", "Filipp-328", by)
ok("Работа продолжается: 1" in b, "active pc → «Работа продолжается: 1»")
ok("🎭" in b and "pc 1" in b, "🎭 pc 1 в плашке")
ok("vps" not in b, "vps-счётчика нет (vps пуст)")

# ── B4. конверт NEEDS_APPROVAL ────────────────────────────────────────────────
print("B4. конверт needs_approval:")
by = _mk_by(needs_approval=[_item(3, DB.QUEUE_FROM, "needs_approval")])
b = DB._build_banner(1, "", "Filipp-328", by)
ok("Ждёт тебя" in b and "1 конвертов" in b, "needs_approval → «Ждёт тебя: 1 конвертов»")

# ── B5. пустая очередь без куратора → ЗАВЕРШЕНО ──────────────────────────────
print("B5. пустая очередь → ЗАВЕРШЕНО:")
by = _mk_by()
b = DB._build_banner(1, "", "Filipp-328", by)
ok("ВСЁ ЗАВЕРШЕНО" in b, "пустая очередь + куратор off → «ВСЁ ЗАВЕРШЕНО»")
ok("последняя задача" in b, "правильная фраза о последней задаче")

# ── B6. куратор включён, вердикта нет → «оценивает» ─────────────────────────
print("B6. куратор думает:")
os.environ["CURATOR"] = "1"
by = _mk_by()   # нет куратор-карточки в done
b = DB._build_banner(10, "просто задача", "Filipp-328", by)
ok("оценивает итог" in b, "куратор вкл, вердикта нет → «Куратор оценивает»")
ok("ЗАВЕРШЕНО" not in b, "не показывать «завершено» пока куратор думает")
os.environ["CURATOR"] = "0"

# ── B7. куратор дал вердикт closed → ЗАВЕРШЕНО ───────────────────────────────
print("B7. куратор: closed (карточка есть, followup нет):")
os.environ["CURATOR"] = "1"
curator_card = _item(99, DB.QUEUE_FROM_DEC, "done", text="[куратор задача 10] вердикт куратора")
by = _mk_by(done=[curator_card])
b = DB._build_banner(10, "просто задача", "Filipp-328", by)
ok("ВСЁ ЗАВЕРШЕНО" in b, "curator closed + пустая очередь → ЗАВЕРШЕНО")
os.environ["CURATOR"] = "0"

# ── B8. _curator_verdict_exists ───────────────────────────────────────────────
print("B8. _curator_verdict_exists:")
by_v = _mk_by(done=[
    _item(11, DB.QUEUE_FROM_DEC, "done", text="[куратор задача 5] вердикт"),
    _item(12, DB.QUEUE_FROM_DEC, "done", text="[куратор родитель 7] вердикт"),
])
ok(DB._curator_verdict_exists(5, "обычная", "Filipp-328", by_v),
   "задача 5 → карточка [куратор задача 5] найдена")
ok(DB._curator_verdict_exists(7, "[сводка родитель 7] шаги", "Filipp-328-dec", by_v),
   "цепная сводка родитель 7 → карточка [куратор родитель 7] найдена")
ok(not DB._curator_verdict_exists(9, "обычная", "Filipp-328", by_v),
   "задача 9 → карточки нет → False")
ok(not DB._curator_verdict_exists(7, "обычная", "Filipp-328", by_v),
   "задача 7 (не dec) → ищет [куратор задача 7], не [куратор родитель 7] → False")

# ── B9. _curator_followup_id ─────────────────────────────────────────────────
print("B9. _curator_followup_id:")
fu = _item(55, DB.QUEUE_FROM_CURATOR, "new", text="[куратор цели 5, шаг 1] допиши тесты")
by_fu = _mk_by(new=[fu])
ok(DB._curator_followup_id(5, by_fu) == 55, "followup для цели 5 → id 55")
ok(DB._curator_followup_id(9, by_fu) is None, "цель 9 → followup нет → None")

# ── B10. report_results: плашка в карточке ────────────────────────────────────
print("B10. report_results с плашкой:")
SENDS = []
class FakeBot10:
    async def send_message(self, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append(text)
        class M:
            message_id = 100
        return M()
class Ctx10:
    bot = FakeBot10()
class MB10:
    def get_pending_multi(self, statuses, lane=None):
        return {"ok": True, "items": [
            {"id": 20, "from": DB.QUEUE_FROM, "status": "done",
             "result": "готово", "task_text": "сделай что-то"},
        ]}
_reset(); DB.BRIDGE = MB10()
asyncio.run(DB.report_results(Ctx10()))
done_texts = [s for s in SENDS if "Задача 20" in s]
ok(len(done_texts) >= 1, "done-карточка отправлена")
ok(any("ВСЁ ЗАВЕРШЕНО" in t or "Работа продолжается" in t
       or "недоступно" in t or "Ждёт тебя" in t
       for t in done_texts), "плашка присутствует в тексте карточки")

# ── B11. _check_curator_pending: followup ─────────────────────────────────────
print("B11. _check_curator_pending: followup:")
os.environ["CURATOR"] = "1"
EDITS = []
class FakeBot11:
    async def edit_message_text(self, **kw):
        EDITS.append(kw)
class Ctx11:
    bot = FakeBot11()
curator_done = _item(200, DB.QUEUE_FROM_DEC, "done", text="[куратор задача 30] вердикт")
followup_new = _item(201, DB.QUEUE_FROM_CURATOR, "new", text="[куратор цели 30, шаг 1] доделай")
by_check = _mk_by(done=[curator_done], new=[followup_new])
DB._curator_pending[30] = (
    DB.HQ_CHAT_ID, DB.DEVBOT_TOPIC, 999,
    "✅ Задача 30 — done\n\nрезультат", "исходная задача", "Filipp-328", "done",
    time.monotonic() - 20,
)
asyncio.run(DB._check_curator_pending(Ctx11(), by_check))
ok(30 not in DB._curator_pending, "задача 30 убрана из pending после вердикта")
ok(any("поставил продолжение" in str(e.get("text", "")) for e in EDITS),
   "editMessageText содержит «поставил продолжение»")
ok(any("201" in str(e.get("text", "")) for e in EDITS),
   "id followup-задачи 201 в тексте edit")
os.environ["CURATOR"] = "0"

# ── B12. _check_curator_pending: таймаут → перерасчёт ─────────────────────────
print("B12. _check_curator_pending: таймаут:")
EDITS.clear()
by_empty = _mk_by()
DB._curator_pending[40] = (
    DB.HQ_CHAT_ID, DB.DEVBOT_TOPIC, 888,
    "❌ Задача 40 — failed\n\nрезультат", "задача", "Filipp-328", "failed",
    time.monotonic() - DB._CURATOR_WAIT_MAX - 10,
)
asyncio.run(DB._check_curator_pending(Ctx11(), by_empty))
ok(40 not in DB._curator_pending, "задача 40 убрана из pending после таймаута")
ok(any("ЗАВЕРШЕНО" in str(e.get("text", "")) for e in EDITS),
   "edit после таймаута + пустая очередь → ЗАВЕРШЕНО")

# ── B13. fallback (по-статусный путь): new и approved в by ────────────────────
print("B13. fallback path (нет get_pending_multi):")
class FallBridge:
    def __init__(self): self.calls = []
    def get_pending(self, st, lane=None):
        self.calls.append(st)
        if st == "in_progress":
            return {"ok": True, "items": [
                {"id": 77, "from": DB.QUEUE_FROM, "status": "in_progress", "task_text": "жду"},
            ]}
        return {"ok": True, "items": []}
fb = FallBridge()
by_fb = DB._poll_queue_sync(fb)
ok(by_fb is not None, "fallback path вернул by (не None)")
ok("new" in by_fb and "approved" in by_fb,
   "by содержит 'new' и 'approved' (расширенный _REPORT_STATUSES)")
ok("new" in fb.calls and "approved" in fb.calls,
   "get_pending вызван для 'new' и 'approved'")
b_fb = DB._build_banner(1, "", "Filipp-328", by_fb)
ok("Работа продолжается: 1" in b_fb, "fallback: in_progress задача 77 → продолжается")
ok("vps 1" in b_fb, "fallback: lane=vps")

# ── B14. curators из не-eligible from → не «оценивает» ───────────────────────
print("B14. куратор off для pc-dec/pcloc-dec:")
os.environ["CURATOR"] = "1"
# Filipp-pc-dec и Filipp-pcloc-dec НЕ вызывают куратора (_pc_post_summary без _maybe_curator_chain)
by_empty2 = _mk_by()
b_pcdec = DB._build_banner(99, "[сводка родитель 88] шаги", "Filipp-pc-dec", by_empty2)
ok("оценивает" not in b_pcdec, "Filipp-pc-dec: куратор не зовётся → не «оценивает»")
ok("ЗАВЕРШЕНО" in b_pcdec, "Filipp-pc-dec + пустая очередь → ЗАВЕРШЕНО")
b_pcloc = DB._build_banner(99, "задача", "Filipp-pcloc-dec", by_empty2)
ok("оценивает" not in b_pcloc, "Filipp-pcloc-dec: куратор не зовётся → не «оценивает»")
os.environ["CURATOR"] = "0"

print()
total = ok_c[0] + fail_c[0]
if fail_c[0] == 0:
    print(f"OK: {total}/{total} проверок плашки продолжения")
    sys.exit(0)
print(f"FAIL: {fail_c[0]} из {total} красные")
sys.exit(1)
