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
                                "gear_last_km":0,"abs_last_km":0,"airfilter_last_km":0,"mileage":0,
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

# 2) карточка: содержимое + 🇹🇭 чистота (скутер → масло+редуктор оба видны)
m=S.msg_bike_card("NMAX 155 4255","27000",
   [{"kind":"oil","last":24094,"interval":4000},{"kind":"gear","last":20000,"interval":4000}],
   {"state":"В аренде","client":"Jack"})
print("(2) карточка:")
res.append(ok("пробег <b>27000</b>" in m and "Масло —" in m and "Редуктор —" in m and "аренда: у клиента Jack" in m, "RU: пробег+масло+редуктор+аренда"))
res.append(ok("น้ำมันเครื่อง" in m and "น้ำมันเกียร์" in m and "ให้เช่าอยู่" in m, "TH: масло+редуктор+аренда тайскими"))
res.append(ok(th_clean(m), "🇹🇭 без кириллицы"))

# 3) _send_bike_card собирает из bridge (NINJA=мото: масло считается, gear скрыт, abs/фильтр «не делалось»)
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BR(),CHAT,TOPIC,"NINJA 6334"))
print("(3) _send_bike_card:")
res.append(ok(len(SENDS)==1 and "Масло — ✅ ещё <b>2823</b> км" in SENDS[0] and "Плановое ТО" in SENDS[0], "карточка собрана из find_bike(Лист1)+service_list (пробег=max)"))

# 4) _handle_servicing: запрос статуса → карточка, НИЧЕГО не пишет, parse не как событие
SENDS.clear()
br=BR()
# Пакет Б: карточка теперь под гейтом — явный статус-запрос (начинается со статус-слова) ИЛИ обращение к боту.
loop.run_until_complete(S._handle_servicing(Msg2("статус по байку"),context=None,bridge=br,claude=FakeClaude(),photo_msgs=[]))
print("(4) хук в _handle_servicing:")
res.append(ok(len(SENDS)==1 and "Статус байка" in SENDS[0], "на ЯВНЫЙ запрос → карточка отправлена"))
res.append(ok(len(br.events)==0, "ничего НЕ записано (только чтение)"))

# 5) НОВЫЕ секции: в работе (Z1+Z4 дословно) / последний сервис / устаревшая аренда (Z3) / пусто
print("(5) то_заявки секции + Z3/Z4:")
m2=S.msg_bike_card("NMAX 4255","24302",[],
   {"state":"В аренде","client":"Gamza","expired":True,"end":"17.06.2026"},
   sp_open={"kinds":["pads"],"works":["подшипник переднего колеса"],"odo":"24302","status":"ждёт_факт"},
   sp_last={"done":["oil"],"odo":"24094","date":"2026-06-07"})
res.append(ok("В работе:" in m2 and "подшипник переднего колеса" in m2, "Z4: дословная работа в RU «В работе»"))
res.append(ok("ждёт результат" in m2 and "одометр 24302" in m2, "статус заявки читаемый + одометр"))
res.append(ok("Последний сервис:" in m2 and "24094" in m2, "секция «Последний сервис» из закрытой заявки"))
res.append(ok("аренда истекла 17.06.2026" in m2, "Z3: флаг устаревшей аренды"))
res.append(ok(th_clean(m2), "🇹🇭 чистый (дословная кириллица только в RU)"))
res.append(ok("กำลังทำ: <b>ผ้าเบรก" in m2, "TH «в работе» тайскими лейблами (без дословной кириллицы)"))

m3=S.msg_bike_card("X","100",[],{"state":"дома","client":""})
res.append(ok("В работе" not in m3 and "Последний сервис" not in m3, "нет заявок → секции опущены"))

# не устаревшая аренда (дата в будущем) → без флага
m4=S.msg_bike_card("Y","1",[],{"state":"В аренде","client":"Z","expired":False,"end":"01.01.2099"})
res.append(ok("истекла" not in m4 and "у клиента Z" in m4, "аренда в силе → без флага «истекла»"))

# _send_bike_card подтягивает то_заявки из bridge (открытая дословная + закрытая)
class BR2(BR):
    def read_events(s,b,limit=8): return {"items":[]}
    def service_pending_get(s,c,t,b): return {"ok":True,"item":{"status":"ждёт_факт","declared":"pads",
        "done":"","odometer":"24302","note":"WORKS:{подшипник переднего колеса} | escalated"}}
    # E3(e): закрытая заявка с done='pads,oil,filter' (как улика 4255) — карточка валидирует:
    # показывает ТОЛЬКО колодки (oil/gear/abs/airfilter — в своих секциях; масляный фильтр невалиден).
    def service_pending_list(s,**k): return {"items":[{"bike":"NINJA 400СС PHUKET 6334","status":"закрыто",
        "done":"pads,oil,filter","odometer":"37000","updated_at":"2026-06-01T00:00:00Z"}]}
SENDS.clear()
loop.run_until_complete(S._send_bike_card(None,BR2(),CHAT,TOPIC,"NINJA 6334"))
res.append(ok(len(SENDS)==1 and "В работе:" in SENDS[0] and "подшипник переднего колеса" in SENDS[0],
              "_send_bike_card подтянул открытую заявку с дословной работой (note WORKS:)"))
res.append(ok("Последний сервис: тормозные колодки" in SENDS[0]
              and "Последний сервис: тормозные колодки, моторное масло" not in SENDS[0],
              "E3(e): «Последний сервис» из done='pads,oil,filter' → ТОЛЬКО колодки (без масла/масляного фильтра)"))

# Z4 хелперы note: запись/чтение/слияние без потери прочего текста
n1=S._sp_note_set_works("", ["колодки","подшипник"])
res.append(ok(S._sp_works_from_note(n1)==["колодки","подшипник"], "Z4 note: запись+чтение работ"))
n2=S._sp_note_set_works("WORKS:{колодки} | escalated", ["подшипник"])
res.append(ok(S._sp_works_from_note(n2)==["колодки","подшипник"] and "escalated" in n2, "Z4 note: слияние + прочий текст сохранён"))
res.append(ok(S._rental_expired("В аренде","17.06.2026 , 14:00") and not S._rental_expired("дома","17.06.2026"), "Z3 _rental_expired логика"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
