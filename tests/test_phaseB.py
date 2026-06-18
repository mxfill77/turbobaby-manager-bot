"""Моки ЧАСТЬ B: трекинг J/K/L при фиксации + прогон на приходе пробега."""
import os, sys, asyncio
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S

CHAT=-1002751134848; TOPIC=73

# bridge с фоллбэк-интервалами (read_doc=False → _service_interval берёт хардкод 4000/10000/20000)
class BR:
    def __init__(self): self.upserts=[]; self.svc_records=[]; self.set_calls=[]
    def _call(self,action,**kw): return {"ok":False}   # read_doc упал → фоллбэк интервалов
    def set_fleet_service(self,number,kind,km,confirmed=False):
        # реальный Bridge возвращает ПОЛНОЕ каноническое имя (с моделью) — здесь не подменяем
        # (без bike_name → _write_service_col классифицирует по входному имени байка, в нём есть модель)
        self.set_calls.append((number,kind,km)); return {"ok":True}
    def service_upsert(self,**kw):
        self.upserts.append(kw)
        iv=kw.get("interval_km"); last=kw.get("last_service_km"); cur=kw.get("current_km")
        nxt=(last+iv) if (last and iv) else (self._stored_next(kw))
        status="ok"
        if nxt and cur:
            if cur>=nxt: status="overdue"
            elif nxt-cur<=300: status="due"
        return {"ok":True,"next_km":nxt,"status":status,"bike":kw.get("bike")}
    def _stored_next(self,kw):  # для прогона на пробеге: next_km из заранее заданной записи
        for r in self.svc_records:
            if r["service_type"]==kw.get("service_type"): return r.get("next_km")
        return ""
    def service_list(self): return {"items":self.svc_records}
    def find_bike(self,b): return {"name":b,"oil_last_km":None}

SENDS=[]; PINS=[]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw): SENDS.append(text)
async def rec_pin(context,bridge,chat_id,topic_id,bike,km,next_km,status,stype="oil",always_notify=False):
    PINS.append((stype,status))
S._send=rec_send; S._pin_overdue_reminder=rec_pin

def reset(): SENDS.clear(); PINS.clear(); S._SVC_INTERVALS_CACHE["data"]=None; S._SVC_INTERVALS_CACHE["ts"]=0.0
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
res=[]; loop=asyncio.new_event_loop()

# B1.1 фиксация abs на скутере NMAX → service_upsert(interval=10000, type=abs)
reset(); br=BR()
loop.run_until_complete(S._write_service_col(None,br,CHAT,TOPIC,"NMAX 7530","abs","40000"))
print("(B1) фиксация ABS:")
res.append(ok(len(br.set_calls)==1, "столбец записан (set_fleet_service)"))
u=[x for x in br.upserts if x.get("service_type")=="abs"]
res.append(ok(len(u)==1 and u[0]["interval_km"]==10000, "service_upsert(abs, interval=10000) вызван"))
res.append(ok(u[0]["last_service_km"]==40000, "цикл сброшен (last_service_km=40000)"))

# B1.2 фиксация gear на скутере → interval=4000
reset(); br=BR()
loop.run_until_complete(S._write_service_col(None,br,CHAT,TOPIC,"NMAX 7530","gear","40000"))
print("(B1) фиксация gear скутер:")
res.append(ok(any(x.get("service_type")=="gear" and x["interval_km"]==4000 for x in br.upserts), "service_upsert(gear, 4000) на скутере"))

# B1.3 фиксация gear на МОТО → НЕ трекаем (iv=None), столбец всё равно записан
reset(); br=BR()
loop.run_until_complete(S._write_service_col(None,br,CHAT,TOPIC,"CB 650R 3503","gear","20000"))
print("(B1) gear на мото:")
res.append(ok(len(br.set_calls)==1, "столбец записан (Фаза 1 поведение цело)"))
res.append(ok(not any(x.get("service_type")=="gear" for x in br.upserts), "service_upsert(gear) НЕ вызван (мото → не трекаем)"))

# B1.4 фиксация возд.фильтра → interval=20000
reset(); br=BR()
loop.run_until_complete(S._write_service_col(None,br,CHAT,TOPIC,"CB 650R 3503","airfilter","20000"))
print("(B1) фиксация возд.фильтр:")
res.append(ok(any(x.get("service_type")=="airfilter" and x["interval_km"]==20000 for x in br.upserts), "service_upsert(airfilter, 20000) — все байки"))

# B2 приход пробега: есть ABS-запись, текущий > next → overdue → напоминание stype=abs
reset(); br=BR()
br.svc_records=[{"service_type":"abs","bike":"NMAX 155 7530","next_km":42000}]
loop.run_until_complete(S._check_other_services(None,br,CHAT,TOPIC,"NMAX 7530","43000"))
print("(B2) пробег 43000, ABS next=42000 → просрочка:")
res.append(ok(("abs","overdue") in PINS, "_pin_overdue_reminder(stype=abs, overdue) вызван"))

# B2.2 ABS в норме (next далеко) → НЕ напоминаем
reset(); br=BR()
br.svc_records=[{"service_type":"abs","bike":"NMAX 155 7530","next_km":50000}]
loop.run_until_complete(S._check_other_services(None,br,CHAT,TOPIC,"NMAX 7530","43000"))
print("(B2) ABS в норме:")
res.append(ok(len(PINS)==0, "напоминания НЕТ (ТО в норме)"))

# B2.3 нет J/K/L записей → ничего (до первой фиксации)
reset(); br=BR()
loop.run_until_complete(S._check_other_services(None,br,CHAT,TOPIC,"NMAX 7530","43000"))
print("(B2) нет записей:")
res.append(ok(len(PINS)==0 and len(br.upserts)==0, "до фиксаций — никаких прогонов"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
