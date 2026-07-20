"""Стейл-кнопка конверта (шаг 1/6 родитель 230): _cb_approve/_cb_reject перед действием
проверяют текущий статус через _find_task. Если статус ≠ needs_approval — действие
не применяется, кнопки снимаются («⏱ карточка устарела»), если есть другой открытый
needs_approval — отправляется его свежая карточка с _kb_approval(N). Всё замокано."""
import sys, asyncio, os
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB

res = []

def ok(cond, label):
    print(("PASS" if cond else "FAIL"), "-", label)
    return bool(cond)


class FakeUser:
    def __init__(s, uid): s.id = uid

class FakeMsg:
    def __init__(s):
        s.text = "NEEDS_APPROVAL: op=restart_splinter | перезапустить splinter"
        s.message_thread_id = DB.DEVBOT_TOPIC

class FakeQuery:
    def __init__(s, data, uid=DB.DEVBOT_USER):
        s.data = data
        s.from_user = FakeUser(uid)
        s.message = FakeMsg()
        s.answers, s.edits = [], []
    async def answer(s, txt=None, **kw): s.answers.append(txt)
    async def edit_message_text(s, text=None, **kw): s.edits.append(text)
    async def edit_message_reply_markup(s, **kw): pass

SENDS = []
class FakeBot:
    async def send_message(s, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append({"text": text, "markup": reply_markup})
class Ctx:
    bot = FakeBot()

class FakeBridge:
    def __init__(s, approve=None, complete=None, items=None):
        s._approve, s._complete = approve or {}, complete or {}
        s._items = items or []
        s.approve_calls, s.complete_calls = [], []
    def approve_task(s, qid, who):
        s.approve_calls.append(qid); return s._approve
    def complete_task(s, qid, status, note):
        s.complete_calls.append(qid); return s._complete
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [i for i in s._items if i.get("_st") == status]}

class Upd:
    def __init__(s, q): s.callback_query = q

loop = asyncio.new_event_loop()
run = loop.run_until_complete

# ─── S1: approve на задачу со статусом done → стейл, approve_task НЕ вызван ───
SENDS.clear()
br = FakeBridge(approve={"ok": True}, items=[{"_st": "done", "id": 7}])
q = FakeQuery("approve:7")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S1) approve на done-задачу (стейл):")
res.append(ok(br.approve_calls == [], "approve_task НЕ вызван"))
res.append(ok(len(q.edits) == 1 and "устарела" in q.edits[0] and "статус: done" in q.edits[0],
             "кнопки сняты с пометкой «устарела (статус: done)»"))
res.append(ok("карточка устарела" in (q.answers[0] or ""), "тост «карточка устарела»"))
res.append(ok(len(SENDS) == 0, "нет followup-карточки (нет других needs_approval)"))

# ─── S2: reject на задачу со статусом done → стейл, complete_task НЕ вызван ───
SENDS.clear()
br = FakeBridge(complete={"ok": True}, items=[{"_st": "done", "id": 5}])
q = FakeQuery("reject:5")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S2) reject на done-задачу (стейл):")
res.append(ok(br.complete_calls == [], "complete_task НЕ вызван"))
res.append(ok(len(q.edits) == 1 and "устарела" in q.edits[0], "кнопки сняты с пометкой «устарела»"))

# ─── S3: approve на задачу со статусом needs_approval → гейт пропускает, approve выполняется ───
SENDS.clear()
br = FakeBridge(approve={"ok": True}, items=[{"_st": "needs_approval", "id": 10}])
q = FakeQuery("approve:10")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S3) approve на needs_approval-задачу (нормальный путь):")
res.append(ok(br.approve_calls == [10], "approve_task вызван"))
res.append(ok(len(q.edits) == 1 and "✅ одобрено" in q.edits[0], "кнопки сняты с «✅ одобрено»"))

# ─── S4: стейл + есть другой needs_approval → followup-карточка с кнопками ───
SENDS.clear()
OTHER_CARD = "NEEDS_APPROVAL: op=other | сделать что-то важное"
br = FakeBridge(items=[
    {"_st": "done", "id": 7},
    {"_st": "needs_approval", "id": 42, "result": OTHER_CARD},
])
q = FakeQuery("approve:7")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S4) стейл + другой needs_approval:")
res.append(ok(len(q.edits) == 1 and "актуальный конверт №42 ниже" in q.edits[0],
             "пометка «актуальный конверт №42 ниже»"))
res.append(ok(len(SENDS) == 1, "followup-карточка отправлена"))
res.append(ok(len(SENDS) == 1 and SENDS[0]["text"] == OTHER_CARD,
             "текст followup = result другой задачи"))
# Проверяем кнопки: должны быть _kb_approval(42) — callback_data должен содержать «approve:42»
markup = SENDS[0]["markup"] if SENDS else None
btn_data = [btn.callback_data for row in (markup.inline_keyboard if markup else []) for btn in row]
res.append(ok(any("approve:42" in d for d in btn_data), "кнопки followup: approve:42"))
res.append(ok(any("reject:42" in d for d in btn_data), "кнопки followup: reject:42"))

# ─── S5: стейл (задача не найдена вовсе) + нет других needs_approval → нет followup ───
SENDS.clear()
br = FakeBridge(items=[])  # пустая очередь
q = FakeQuery("reject:99")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S5) стейл (не найдена) + нет других needs_approval:")
res.append(ok(len(q.edits) == 1 and "устарела" in q.edits[0] and "не найдена" in q.edits[0],
             "пометка «устарела (задача не найдена)»"))
res.append(ok(len(SENDS) == 0, "нет followup-карточки"))

# ─── S6: reject на needs_approval → гейт пропускает, complete_task вызван ───
SENDS.clear()
br = FakeBridge(complete={"ok": True}, items=[{"_st": "needs_approval", "id": 20}])
q = FakeQuery("reject:20")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(S6) reject на needs_approval-задачу (нормальный путь):")
res.append(ok(br.complete_calls == [20], "complete_task вызван"))
res.append(ok(len(q.edits) == 1 and "❌ отклонено" in q.edits[0], "кнопки сняты с «❌ отклонено»"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
