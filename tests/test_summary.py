"""Моки: единое итоговое сообщение ТО-цикла (накопитель + сводка в терминале)."""
import os, sys, json, asyncio, re
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S

CHAT=-1002751134848; TOPIC=73
class BR:
    def __init__(self): self.events=[]
    def _call(self,a,**k): return {"ok":False}            # read_doc → фоллбэк интервалов
    def find_bike(self,b): return {"name":b,"oil_last_km":37823}
    def service_upsert(self,**kw): return {"status":"ok","next_km":42823,"km_left":5000,"service_type":kw.get("service_type","oil")}
    def service_list(self): return {"items":[]}
    def set_fleet_service(self,number,kind,km,confirmed=False): return {"ok":True}
SENDS=[]
class FakeSent:
    def __init__(s,m): s.message_id=m
_MID=[7000]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw): SENDS.append(text); _MID[0]+=1; return FakeSent(_MID[0])
S._send=rec_send
def reset(): SENDS.clear(); S._SVC_SUMMARY.clear(); S._SVC_CYCLE_MSGS.clear(); S._SVC_INTERVALS_CACHE["data"]=None; S._SVC_INTERVALS_CACHE["ts"]=0.0
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
def last(): return SENDS[-1] if SENDS else ""
res=[]; loop=asyncio.new_event_loop()

# 1) макет + 🇹🇭 чистота
acc={'current_km':'37823','works':['масляный фильтр','колодки','цепь'],'works_km':'37823',
     'oil':{'km':37823,'next':42823,'status':'ok'},'cols':[{'kind':'gear','km':40000,'next':44000}]}
m=S.msg_service_summary('NINJA 400 6334',acc)
print("(1) макет сводки:")
res.append(ok("в норме, следующее 42823" in m and "редуктор (gear): 40000" in m and "— масляный фильтр" in m and "— колодки" in m and "— цепь" in m, "RU: масло+столбец+история ПО ПУНКТАМ (буллеты)"))
res.append(ok("เปลี่ยนน้ำมันเครื่อง" in m and "น้ำมันเกียร์" in m and "ไส้กรองน้ำมันเครื่อง" in m and "ผ้าเบรก" in m and "โซ่" in m, "TH: работы ПО ПУНКТАМ тайскими названиями"))
inth=False; cyr=[]
for l in m.split("\n"):
    if l.lstrip().startswith("🇷🇺"): inth=False
    if l.lstrip().startswith("🇹🇭"): inth=True
    if inth and re.search(r"[А-Яа-яЁё]",l): cyr.append(l)
res.append(ok(not cyr, "🇹🇭-блок без кириллицы"))

# 2) _emit_summary: накопитель → одна сводка, очистка
reset()
a=S._summary_acc(CHAT,TOPIC); a["works"]=["колодки"]; a["works_km"]="37823"; a["oil"]={"km":37823,"next":42823,"status":"ok"}
sent=loop.run_until_complete(S._emit_summary(None,CHAT,TOPIC,"NINJA 6334"))
print("(2) _emit_summary:")
res.append(ok(sent and "Готово" in last() and "колодки" in last(), "одна сводка отправлена"))
res.append(ok((CHAT,TOPIC) not in S._SVC_SUMMARY, "накопитель очищен"))
res.append(ok(not loop.run_until_complete(S._emit_summary(None,CHAT,TOPIC,"x")), "пустой накопитель → ничего"))

# 3) _after_mileage норма с работами в накопителе → ОДНА сводка (масло+история), без msg_mileage_ok
reset()
a=S._summary_acc(CHAT,TOPIC); a["works"]=["масляный фильтр","колодки","цепь"]; a["works_km"]="37823"
loop.run_until_complete(S._after_mileage(None,BR(),CHAT,TOPIC,"NINJA 400 6334","37823"))
print("(3) [Да] норма с работами в накопителе:")
res.append(ok(len(SENDS)==1, "РОВНО ОДНА реплика (не 2)"))
res.append(ok("Готово" in last() and "следующее 42823" in last() and "В историю" in last() and "цепь" in last(), "сводка = пробег+ТО Oil+история"))
res.append(ok("Пробег 37823 км принят" not in last(), "отдельного msg_mileage_ok НЕТ"))

# 4) только пробег без работ → сводка = пробег+ТО
reset()
loop.run_until_complete(S._after_mileage(None,BR(),CHAT,TOPIC,"NINJA 400 6334","37823"))
print("(4) только пробег без работ:")
res.append(ok(len(SENDS)==1 and "ТО Oil: в норме" in last() and "В историю" not in last(), "сводка = пробег+ТО, без истории"))

# 5) _write_service_col → сводка со строкой столбца (без отдельного «Записано»)
reset()
loop.run_until_complete(S._write_service_col(None,BR(),CHAT,TOPIC,"NMAX 7530","abs","40000"))
print("(5) фиксация столбца ABS:")
res.append(ok(len(SENDS)==1 and "ABS: 40000" in last(), "сводка со строкой ABS"))
res.append(ok("Записано «ABS»" not in last(), "отдельного «Записано» НЕТ"))

# 6) масло+столбец 2 кнопками → 2 сводки, работы в ПЕРВОЙ, без дублей
reset()
a=S._summary_acc(CHAT,TOPIC); a["works"]=["колодки","цепь"]; a["works_km"]="37823"
loop.run_until_complete(S._write_service_col(None,BR(),CHAT,TOPIC,"NMAX 7530","gear","37823"))  # терминал 1: столбец+работы
first=last()
loop.run_until_complete(S._after_mileage(None,BR(),CHAT,TOPIC,"NMAX 7530","37823"))            # терминал 2: масло
second=last()
print("(6) масло+столбец разными кнопками:")
res.append(ok("В историю" in first and ("колодки" in first), "работы — в ПЕРВОЙ сводке (столбец)"))
res.append(ok("В историю" not in second, "во ВТОРОЙ сводке (масло) работ НЕТ (без дублей)"))


# 7) П.3: закреп итога после замены масла (_write_oil → pin_chat_message сводки)
class BotPin:
    def __init__(s): s.pinned=[]; s.unpin_all=0
    async def unpin_all_forum_topic_messages(s,chat_id,message_thread_id=None): s.unpin_all+=1
    async def unpin_chat_message(s,chat_id,message_id=None): pass
    async def delete_message(s,chat_id,message_id): pass
    async def pin_chat_message(s,chat_id,message_id,disable_notification=False): s.pinned.append(message_id)
class CtxPin:
    def __init__(s): s.bot=BotPin()
class BRoil(BR):
    def set_fleet_oil(s,number,oil_km,confirmed=False): return {"ok":True,"bike_name":f"NMAX 155 {number}"}
    def service_set_pin(s,**kw): return {"ok":True}
reset()
a=S._summary_acc(CHAT,TOPIC); a["works"]=["колодки","цепь"]; a["works_km"]="37823"   # работы накоплены
ctx=CtxPin()
loop.run_until_complete(S._write_oil(ctx,BRoil(),CHAT,TOPIC,"NMAX 7530","37823"))
print("(7) закреп итога после масла:")
res.append(ok(len(ctx.bot.pinned)==1, "сводка-итог ЗАКРЕПЛЕНА (pin_chat_message 1 раз)"))
res.append(ok(ctx.bot.unpin_all==1, "старые пины сняты ПЕРЕД новым (unpin_all)"))
res.append(ok(len(SENDS)==1 and "Готово" in last() and "— колодки" in last(), "одна сводка (масло+история), буллеты"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
