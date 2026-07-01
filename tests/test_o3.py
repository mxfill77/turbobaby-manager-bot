"""Моки O3 ступень 1: park-scan просрочек → o3_task CRUD → конструктор наряда (pick→vid→from→when→send) →
наряд RU+TH → board refresh → back-отмена. Боевых тайцев/Telegram/Лист1 нет — всё мокнуто."""
import os, sys, asyncio, tempfile
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
import splinter as S
import memory as M

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []; loop = asyncio.new_event_loop()

# --- mock bridge для скана: knowledge_base fail → фоллбэк-интервалы (oil ск4000/мо5000, gear ск4000/мо None, abs 10000, air 20000)
class BR:
    def _call(s, a, **k): return {"ok": False}
    def fleet(s): return {"data": {"bikes": [
        {"name": "NMAX 155CC PHUKET 4255", "status": "ДОМА", "mileage": 3000,
         "oil_last_km": 24000, "gear_last_km": 27000, "abs_last_km": 0, "airfilter_last_km": 5000},
        {"name": "NINJA 400CC PHUKET 6334", "status": "ДОМА", "mileage": 40000,
         "oil_last_km": 38000, "gear_last_km": 0, "abs_last_km": 25000, "airfilter_last_km": 10000},
        {"name": "PCX 160CC PHUKET 1111", "status": "ДОМА", "mileage": 5000,
         "oil_last_km": 4000, "gear_last_km": 4000, "abs_last_km": 0, "airfilter_last_km": 0},
    ]}}
    def service_list(s): return {"items": [
        {"bike": "NMAX 155CC PHUKET 4255", "current_km": 30000},   # выше colH(3000) → max=30000 (тест max)
    ]}

# (1) скан просрочек
scan = S._o3_overdue_scan(BR()); ov = scan["overdue"]; nb = scan["nobase"]
print("(1) _o3_overdue_scan:")
res.append(ok(len(ov) == 2, f"2 байка с просрочками (NINJA+NMAX) — {len(ov)}"))
res.append(ok("NINJA" in ov[0]["bike"] and ov[0]["items"][0]["kind"] == "airfilter" and ov[0]["items"][0]["over_km"] == 10000,
              "худший сверху: NINJA airfilter over 10000"))
res.append(ok("NMAX" in ov[1]["bike"] and ov[1]["current_km"] == 30000, "NMAX второй; текущий=max(colH,service_list)=30000"))
nm = [o for o in ov if "NMAX" in o["bike"]][0]; kinds_nm = [it["kind"] for it in nm["items"]]
res.append(ok(set(kinds_nm) == {"oil", "airfilter"} and "gear" not in kinds_nm, "NMAX: oil+airfilter просрочены, gear НЕ (rem>0)"))
ninja = [o for o in ov if "NINJA" in o["bike"]][0]
res.append(ok("gear" not in [it["kind"] for it in ninja["items"]], "NINJA мото: gear пропущен (interval None)"))
res.append(ok(any("PCX" in x["bike"] for x in nb) and any("NMAX" in x["bike"] for x in nb), "nobase: PCX (abs+air) и NMAX (abs)"))
res.append(ok(not any("NINJA" in x["bike"] for x in nb), "NINJA не в nobase (база есть)"))

# (2) o3_task CRUD round-trip
print("(2) o3_task CRUD:")
mem = M.Memory(db_path=tempfile.mktemp(suffix=".db"))
tid = mem.o3_task_create(bike="NMAX 4255", plate="4255", kinds="oil,airfilter", from_where="office",
                         when_slot="now", status="sent", delivery_msg_id=555)
g = mem.o3_task_get(tid)
res.append(ok(g and g["bike"] == "NMAX 4255" and g["kinds"] == "oil,airfilter" and g["status"] == "sent"
              and g["delivery_msg_id"] == 555, "create+get round-trip"))
mem.o3_task_update(tid, status="new")
res.append(ok(mem.o3_task_get(tid)["status"] == "new", "update меняет status"))
mem.o3_task_create(bike="X", plate="9", kinds="abs", status="sent")
act = mem.o3_tasks_active()
res.append(ok(len(act) == 1 and act[0]["plate"] == "9", "o3_tasks_active вернул только sent (tid→new исключён)"))

# --- фейки Telegram для конструктора ---
SENDS = []; EDITS = []; _MID = [7000]
class FakeSent:
    def __init__(s, m): s.message_id = m
class FakeBot:
    async def send_message(s, **kw): _MID[0] += 1; SENDS.append(kw); return FakeSent(_MID[0])
    async def edit_message_text(s, **kw): EDITS.append(kw)
class FakeCtx:
    def __init__(s): s.bot = FakeBot()
class FakeChat:
    def __init__(s, c): s.id = c
class FakeMsg:
    def __init__(s, c, t): s.chat = FakeChat(c); s.message_thread_id = t
class FakeQ:
    def __init__(s, data, c=-100, t=None):
        s.data = data; s.message = FakeMsg(c, t); s.answers = []; s.edits = []
        s.from_user = type("U", (), {"username": "mech", "first_name": "M"})()
    async def answer(s, txt=None): s.answers.append(txt)
    async def edit_message_text(s, text=None, reply_markup=None, **kw): s.edits.append({"text": text, "kb": reply_markup})
class FakeUpd:
    def __init__(s, q): s.callback_query = q
async def rec_send(context, *, chat_id, text, message_thread_id=None, bilingual=True, reply_markup=None, **kw):
    _MID[0] += 1; SENDS.append({"chat": chat_id, "topic": message_thread_id, "text": text, "kb": reply_markup})
    return FakeSent(_MID[0])
S._send = rec_send
S._MEMORY = mem

# (3) конструктор: pick → vid тоггл → from → when → send
print("(3) конструктор наряда:")
tok = S._o3_put({"bike": "NMAX 155CC PHUKET 4255", "plate": "4255", "current_km": 30000,
                 "overdue_kinds": ["oil", "airfilter"], "kinds": ["oil", "airfilter"], "from_where": None, "when": None})
ctx = FakeCtx()
q = FakeQ(f"o3:pick:{tok}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q), ctx, BR()))
res.append(ok(any("Выбери виды" in s["text"] for s in SENDS), "pick → конструктор (выбор видов) новым сообщением"))
q2 = FakeQ(f"o3:vid:{tok}:oil")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q2), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["kinds"] == ["airfilter"], "vid тоггл снял oil (осталось airfilter)"))
q3 = FakeQ(f"o3:step:{tok}:from")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q3), ctx, BR()))
res.append(ok(any("Откуда" in e["text"] for e in q3.edits), "step:from → шаг «откуда»"))
q4 = FakeQ(f"o3:from:{tok}:office")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q4), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["from_where"] == "office" and any("Когда" in e["text"] for e in q4.edits), "from=office → шаг «когда»"))
q5 = FakeQ(f"o3:when:{tok}:now")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q5), ctx, BR()))
res.append(ok(S._O3_TOKENS[tok]["when"] == "now" and any("Проверь наряд" in e["text"] for e in q5.edits), "when=now → предпросмотр наряда"))

# (4) send → наряд в доставки RU+TH + o3_task + подтверждение
print("(4) отправка наряда:")
SENDS.clear()
q6 = FakeQ(f"o3:send:{tok}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(q6), ctx, BR()))
naryad = [s for s in SENDS if "Наряд на ТО" in s["text"]]
res.append(ok(len(naryad) == 1, "send → наряд запощен в доставки (1 сообщение)"))
res.append(ok("работы: Возд. фильтр" in naryad[0]["text"] and "забрать: в офисе" in naryad[0]["text"]
              and "когда: сейчас" in naryad[0]["text"], "текст наряда RU: работы/откуда/когда"))
res.append(ok("งาน: ไส้กรองอากาศ" in naryad[0]["text"] and "รับรถ: ที่ออฟฟิศ" in naryad[0]["text"] and "เมื่อไร: ตอนนี้" in naryad[0]["text"], "текст наряда TH: тайскими"))
res.append(ok(any("Наряд отправлен" in e["text"] for e in q6.edits), "конструктор → подтверждение (нестираемый след)"))
res.append(ok(any(t["plate"] == "4255" and t["kinds"] == "airfilter" for t in mem.o3_tasks_active()),
              "o3_task(sent) записан с выбранными видами (airfilter)"))

# (5) board refresh (editMessageText) — байк с активным нарядом помечается
print("(5) board refresh:")
S._O3_BOARD["chat"] = -100; S._O3_BOARD["msg"] = 999
EDITS.clear()
loop.run_until_complete(S._o3_refresh_board(ctx, BR()))
res.append(ok(any(e.get("message_id") == 999 and "Наряды" in e.get("text", "") for e in EDITS), "refresh → editMessageText board (просрочки)"))

# (6) back → чистая отмена, ничего не отправлено
print("(6) back-отмена:")
tok2 = S._o3_put({"bike": "X 1", "plate": "1", "overdue_kinds": ["oil"], "kinds": ["oil"], "from_where": None, "when": None})
SENDS.clear()
qb = FakeQ(f"o3:back:{tok2}")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qb), ctx, BR()))
res.append(ok(not any("Наряд на ТО" in s.get("text", "") for s in SENDS) and any("отменён" in e["text"] for e in qb.edits),
              "back → отменено, ничего не отправлено"))

# (7) устойчивость: неизвестный токен / rescan без board — не падает
print("(7) устойчивость префикса o3:")
qg = FakeQ("o3:bogus:999999")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qg), ctx, BR()))
res.append(ok(qg.answers and any("устарел" in e["text"] for e in qg.edits), "неизвестный токен → «устарел», не падает"))
S._O3_BOARD["chat"] = None; S._O3_BOARD["msg"] = None
qr = FakeQ("o3:rescan")
loop.run_until_complete(S.handle_o3_button(FakeUpd(qr), ctx, BR()))
res.append(ok(qr.answers == ["🔄"], "rescan без board → q.answer, no-op не падает"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
