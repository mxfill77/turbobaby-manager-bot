"""Моки ЗАХОД 3: read_events парсинг + секция сервис-на-пробеге в карточке."""
import os, sys, asyncio, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S
CHAT=-1002751134848; TOPIC=73
EV=[
 {"notes":"напоминание проверять износ грипсов","mileage":"","event_type":"repair"},
 {"notes":"Приборная панель ... пробег 37823 км ...","mileage":"37823","event_type":"photo"},
 {"notes":"регулировка цепи — 37823 км","mileage":"37823","event_type":"repair"},
 {"notes":"замена задних тормозных колодок — 37823 км","mileage":"37823","event_type":"repair"},
 {"notes":"замена масляного фильтра — 37823 км","mileage":"37823","event_type":"repair"},
]
class BR:
    def __init__(s,ev=EV): s._ev=ev
    def _call(s,a,**k): return {"ok":False}
    def find_bike(s,b): return {"name":"NINJA 400СС PHUKET 6334","status":"ДОМА","oil_last_km":37823}
    def service_list(s): return {"items":[{"bike":"NINJA 400СС PHUKET 6334","service_type":"oil","current_km":37823,"next_km":42823,"status":"ok"}]}
    def read_events(s,bike,limit=8): return {"ok":True,"bike":bike,"items":s._ev}
SENDS=[]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw): SENDS.append(text); return None
S._send=rec_send
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
def th_clean(m):
    inth=False
    for l in m.split("\n"):
        if l.lstrip().startswith("🇷🇺"): inth=False
        if l.lstrip().startswith("🇹🇭"): inth=True
        if inth and re.search(r"[А-Яа-яЁё]",l): return False
    return True
res=[]; loop=asyncio.new_event_loop()

# 1) парсер: шум отсеян, инфо-работы оставлены (newest-first)
sv=S._parse_service_items(EV,limit=6)
print("(1) парсер read_events:")
res.append(ok(len(sv)==3, "оставлены 3 инфо-работы (фото-описание/напоминание отсеяны)"))
res.append(ok(sv[0]["work"]=="регулировка цепи" and sv[0]["km"]=="37823", "newest-first + км распознан"))

# 2) лимит
res.append(ok(len(S._parse_service_items(EV,limit=2))==2, "лимит работает (2)"))

# 3) карточка с секцией сервиса RU+TH
loop.run_until_complete(S._send_bike_card(None,BR(),CHAT,TOPIC,"NINJA 6334"))
m=SENDS[-1]
print("(3) карточка с сервисом:")
res.append(ok("Обслужено дополнительно на пробегах:" in m and "37823 км (на текущем пробеге)" in m
              and "регулировка цепи" in m and "замена масляного фильтра" in m, "RU: блок «обслужено доп.» + «км назад» точно"))
res.append(ok("ตามไมล์:" in m and "37823 กม. (ไมล์ปัจจุบัน)" in m and "ปรับโซ่" in m and "ไส้กรองน้ำมันเครื่อง" in m, "TH: блочно тайскими названиями"))
res.append(ok(th_clean(m), "🇹🇭 без кириллицы"))

# 4) нет записей → секции нет
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BR(ev=[]),CHAT,TOPIC,"NINJA 6334"))
print("(4) нет истории:")
res.append(ok("Обслужено дополнительно" not in SENDS[-1] and "🇷🇺" in SENDS[-1], "карточка без секции доп-работ (нет событий)"))

# 5) read_events упал → карточка всё равно (без секции), не падает
class BRfail(BR):
    def read_events(s,bike,limit=8): raise RuntimeError("bridge down")
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BRfail(),CHAT,TOPIC,"NINJA 6334"))
res.append(ok(len(SENDS)==1 and "Обслужено дополнительно" not in SENDS[-1], "read_events упал → карточка без секции, не падает"))

# 6) П2: пробег в шапке = max(colH, service_list, км работ-событий). Кейс 5849: colH 3500 / замер 20229 /
#    работы 20829 → шапка ДОЛЖНА быть 20829 (одометр не падает; иначе занижена и работа «выше текущего»).
class BR5849(BR):
    def find_bike(s,b): return {"name":"ADV 350CC BLACK PHUKET 5849","status":"ДОМА","mileage":3500,"oil_last_km":18302}
    def service_list(s): return {"items":[{"bike":"ADV 350CC BLACK PHUKET 5849","service_type":"oil","current_km":20229,"next_km":24229,"status":"ok"}]}
    def read_events(s,bike,limit=8): return {"ok":True,"items":[
        {"notes":"замена задних тормозных колодок — 20829 км","mileage":"20829","event_type":"repair"},
        {"notes":"почистили вариатор (CVT) — 20829 км","mileage":"20829","event_type":"repair"}]}
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BR5849(),CHAT,TOPIC,"ADV 5849"))
m6=SENDS[-1]
print("(6) П2 пробег=max с событиями (5849):")
res.append(ok("<b>пробег 20829 км</b>" in m6, "шапка=20829 (max colH3500/замер20229/работы20829)"))
res.append(ok("20829 км (на текущем пробеге)" in m6 and "тормозных колодок" in m6, "работа 20829 на текущем (20829−20829=0), блочно"))
res.append(ok(th_clean(m6), "🇹🇭 без кириллицы"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
