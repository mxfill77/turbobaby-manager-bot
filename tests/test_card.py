"""Моки ЗАХОД 2: распознавание запроса + карточка байка."""
import os, sys, json, asyncio, re, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S
CHAT=-1002751134848; TOPIC=73

class Msg:
    def __init__(s,text): s.text=text; s.caption=None; s.photo=None; s.chat_id=CHAT
    s_=None
    def __getattr__(s,n): return None
class Msg2:
    def __init__(s,text):
        s.text=text; s.caption=None; s.photo=None; s.chat_id=CHAT
        s.message_thread_id=TOPIC; s.from_user=None
        s.date=datetime.datetime(2026,6,10,5,0,0,tzinfo=datetime.timezone.utc); s.message_id=400
class FakeClaude:
    def quick(s,*a,**k): return "{}"
    def vision(s,*a,**k): return "{}"
class BR:
    def __init__(s): s.events=[]
    def _call(s,a,**k): return {"ok":False}
    def add_event(s,**kw): s.events.append(kw); return {"ok":True}
    def find_bike(s,b): return {"name":"NINJA 400СС PHUKET 6334","status":"В аренде","oil_last_km":37823,
                                "current_rental":{"client":"Jack"}}
    def service_list(s): return {"items":[
        {"bike":"NINJA 400СС PHUKET 6334","service_type":"oil","current_km":37823,"next_km":42823,"status":"ok"},
        {"bike":"NINJA 400СС PHUKET 6334","service_type":"gear","current_km":40000,"next_km":44000,"status":"ok"},
    ]}
SENDS=[]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw): SENDS.append(text); return None
S._send=rec_send
S.bike_from_topic=lambda c,t: "NINJA 400 6334"   # тема → байк
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
def th_clean(m):
    inth=False
    for l in m.split("\n"):
        if l.lstrip().startswith("🇷🇺"): inth=False
        if l.lstrip().startswith("🇹🇭"): inth=True
        if inth and re.search(r"[А-Яа-яЁё]",l): return False
    return True
res=[]; loop=asyncio.new_event_loop()

# 1) распознавание
print("(1) распознавание запроса:")
res.append(ok(S._is_status_request("дай инфу по байку"), "«дай инфу по байку» → да"))
res.append(ok(S._is_status_request("статус"), "«статус» → да"))
res.append(ok(S._is_status_request("что по байку"), "«что по байку» → да"))
res.append(ok(S._is_status_request("карточка"), "«карточка» → да"))
res.append(ok(not S._is_status_request("заменил масло, колодки, цепь, пробег 37823 фото приложил позже"), "длинное сообщение о работах → НЕТ"))

# 2) карточка: содержимое + 🇹🇭 чистота
m=S.msg_bike_card("NINJA 400 6334","37823",{"km":"37823","next":42823,"status":"ok"},
   [{"kind":"gear","next":44000,"status":"ok","km":40000}],{"state":"В аренде","client":"Jack"})
print("(2) карточка:")
res.append(ok("пробег 37823" in m and "ТО Oil: в норме, следующее 42823" in m and "редуктор (gear): следующее 44000" in m and "аренда: у клиента Jack" in m, "RU: пробег+ТО Oil+gear+аренда"))
res.append(ok("เปลี่ยนน้ำมันเครื่อง" in m and "น้ำมันเกียร์" in m and "ให้เช่าอยู่" in m, "TH: масло+gear+аренда тайскими"))
res.append(ok(th_clean(m), "🇹🇭 без кириллицы"))

# 3) _send_bike_card собирает из bridge
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BR(),CHAT,TOPIC,"NINJA 6334"))
print("(3) _send_bike_card:")
res.append(ok(len(SENDS)==1 and "ТО Oil: в норме, следующее 42823" in SENDS[0] and "редуктор" in SENDS[0], "карточка собрана из find_bike+service_list"))

# 4) _handle_servicing: запрос статуса → карточка, НИЧЕГО не пишет, parse не как событие
SENDS.clear()
br=BR()
# Пакет Б: карточка теперь под гейтом — явный статус-запрос (начинается со статус-слова) ИЛИ обращение к боту.
loop.run_until_complete(S._handle_servicing(Msg2("статус по байку"),context=None,bridge=br,claude=FakeClaude(),photo_msgs=[]))
print("(4) хук в _handle_servicing:")
res.append(ok(len(SENDS)==1 and "Статус байка" in SENDS[0], "на ЯВНЫЙ запрос → карточка отправлена"))
res.append(ok(len(br.events)==0, "ничего НЕ записано (только чтение)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
