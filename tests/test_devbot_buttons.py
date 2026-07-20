"""Кнопки дев-бота (тема 328) при протухшем ack (хвост ревизии §7, паттерн _o3_answer):
колбэк, отлежавшийся за долгим Bridge-вызовом, протухает — q.answer кидает BadRequest
«Query is too old». Раньше это валило хендлер: approve оставался без снятых кнопок,
check/next вообще не отвечали (ack шёл ДО действия). Проверяем: (B1) approve — действие
и снятие кнопок проходят при мёртвом ack; (B2) check — статус уходит в тему при мёртвом
ack ПЕРЕД действием; (B3) reject not_found — идемпотентная пометка проходит; (B4) чужой
юзер с мёртвым ack — тихий выход без исключения; (B5) живой ack как раньше. Всё замокано."""
import sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
import os
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import devbot as DB

res = []

def ok(cond, label):
    print(("PASS" if cond else "FAIL"), "-", label)
    return bool(cond)


class FakeUser:
    def __init__(s, uid): s.id = uid

class FakeMsg:
    def __init__(s):
        s.text = "карточка задачи"
        s.message_thread_id = DB.DEVBOT_TOPIC

class FakeQuery:
    """Живой ack — считает вызовы."""
    def __init__(s, data, uid=DB.DEVBOT_USER):
        s.data = data
        s.from_user = FakeUser(uid)
        s.message = FakeMsg()
        s.answers, s.edits = [], []
    async def answer(s, txt=None, **kw): s.answers.append(txt)
    async def edit_message_text(s, text=None, **kw): s.edits.append(text)
    async def edit_message_reply_markup(s, **kw): pass

class DeadAnswerQuery(FakeQuery):
    """Протухший колбэк: q.answer всегда кидает (BadRequest «Query is too old»)."""
    async def answer(s, txt=None, **kw):
        raise Exception("Query is too old and response timeout expired or query id is invalid")

class FakeBridge:
    def __init__(s, approve=None, complete=None, items=None):
        s._approve, s._complete = approve, complete
        s._items = items or []
        s.approve_calls, s.complete_calls = [], []
    def approve_task(s, qid, who):
        s.approve_calls.append(qid); return s._approve
    def complete_task(s, qid, status, note):
        s.complete_calls.append(qid); return s._complete
    def get_pending(s, status="new", lane=None):
        return {"ok": True, "items": [i for i in s._items if i.get("_st") == status]}

SENDS = []
class FakeBot:
    async def send_message(s, chat_id, message_thread_id=None, text="", reply_markup=None):
        SENDS.append(text)
class Ctx:
    bot = FakeBot()

class Upd:
    def __init__(s, q): s.callback_query = q

loop = asyncio.new_event_loop()
run = loop.run_until_complete

# B1: approve с мёртвым ack — approve_task вызван, кнопки сняты пометкой «одобрено»
br = FakeBridge(approve={"ok": True}, items=[{"_st": "needs_approval", "id": 7}])
q = DeadAnswerQuery("approve:7")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(B1) approve при протухшем ack:")
res.append(ok(br.approve_calls == [7], "approve_task выполнен несмотря на мёртвый ack"))
res.append(ok(len(q.edits) == 1 and "✅ одобрено" in q.edits[0], "кнопки сняты, пометка «одобрено»"))

# B2: check с мёртвым ack (ack идёт ДО действия — раньше валило весь ответ)
SENDS.clear()
br = FakeBridge(items=[{"_st": "done", "id": 9, "result": "готово", "updated": "2026-07-03T10:00:00Z"}])
q = DeadAnswerQuery("check:9")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(B2) check при протухшем ack:")
res.append(ok(len(SENDS) == 1 and "статус done" in SENDS[0], "статус задачи ушёл в тему несмотря на мёртвый ack"))

# B3: reject not_found с мёртвым ack (race: задача была в needs_approval, исчезла до complete)
br = FakeBridge(complete={"ok": False, "error": "not_found"}, items=[{"_st": "needs_approval", "id": 5}])
q = DeadAnswerQuery("reject:5")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(B3) reject not_found при протухшем ack:")
res.append(ok(br.complete_calls == [5] and len(q.edits) == 1 and "нет в очереди" in q.edits[0],
              "complete_task вызван, пометка «нет в очереди» поставлена"))

# B4: чужой юзер + мёртвый ack — тихий выход, никаких действий/исключений
br = FakeBridge(approve={"ok": True})
q = DeadAnswerQuery("approve:7", uid=111)
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(B4) чужой юзер при протухшем ack:")
res.append(ok(br.approve_calls == [] and q.edits == [], "approve НЕ выполнен, хендлер не упал"))

# B5: регресс — живой ack работает как раньше (тост уходит)
br = FakeBridge(approve={"ok": True}, items=[{"_st": "needs_approval", "id": 7}])
q = FakeQuery("approve:7")
run(DB.handle_callback(Upd(q), Ctx(), br))
print("(B5) живой ack (регресс):")
res.append(ok(q.answers == ["✅ одобрено"] and len(q.edits) == 1, "тост и снятие кнопок как раньше"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
