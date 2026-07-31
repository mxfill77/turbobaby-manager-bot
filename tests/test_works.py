"""Моки: разбор перечня работ по адресам (вариант A) + отложенная привязка пробега. Сценарии a–e."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S

CHAT=-1002751134848; TOPIC=77

class Msg:
    def __init__(self, text=None, photo=False, mid=100):
        self.text=text; self.caption=None; self.photo=[1] if photo else None
        self.chat_id=CHAT; self.message_thread_id=TOPIC
        self.date=datetime.datetime(2026,6,9,21,0,0,tzinfo=datetime.timezone.utc)
        self.message_id=mid; self.from_user=None

class FakeClaude:
    def __init__(self, parsed=None, vis=None): self._p=parsed or {}; self._v=vis or {}
    def quick(self,system,text,max_tokens=300, **kw): return json.dumps(self._p)
    def vision(self,system,img,max_tokens=400, **kw): return json.dumps(self._v)

class FakeBridge:
    def __init__(self): self.events=[]
    def add_event(self,**kw): self.events.append(kw); return {"ok":True,"saved":True}

SENDS=[]; SVC_COL=[]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw): SENDS.append(text)
async def rec_svc(context,chat_id,topic_id,bike,kind,km): SVC_COL.append((kind,km))
async def rec_after(context,bridge,chat_id,topic_id,bike,mileage,oil_hint=False): pass
async def rec_conf(context,chat_id,topic_id,bike,km,oil_hint=False): pass
async def rec_dl(pm): return b"img"
S._send=rec_send; S._ask_service_col=rec_svc; S._after_mileage=rec_after
S._ask_mileage_confirm=rec_conf; S._download_photo=rec_dl

def reset():
    SENDS.clear(); SVC_COL.clear(); S._RECENT_PHOTOS.clear()
    S._PENDING_WORKS.clear(); S._ODOMETER_ASK_TS.clear()

async def run(msg, parsed=None, vis=None):
    br=FakeBridge()
    pm=[msg] if msg.photo else None
    await S._handle_servicing(msg, context=None, bridge=br,
                              claude=FakeClaude(parsed,vis), photo_msgs=pm)
    return br

def info_rows(br): return [e for e in br.events if str(e.get("msg_id","")).startswith("info:")]
def lumped(br):    return [e for e in br.events if str(e.get("notes","")).startswith("работы:")]
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c

res=[]; loop=asyncio.new_event_loop()

# (a) масло+колодки+цепь + ПРОБЕГ текстом → инфо-работы разнесены с км, без лумпа
reset()
pa={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":"37900",
    "works":["замена моторного масла","задние колодки","регулировка цепи"]}
br=loop.run_until_complete(run(Msg("масло, колодки, цепь, пробег 37900", mid=201), pa))
ir=info_rows(br)
print("(a) работы+пробег в одном сообщении:")
res.append(ok(len(ir)==2, "2 инфо-строки (колодки+цепь), по строке на работу"))
res.append(ok(all("37900" in e["notes"] for e in ir), "у каждой привязан пробег 37900"))
# СМЕНА КОНТРАКТА (класс-фикс 4957, корень 3, 31.07.2026): ключ = стем + уточнитель места,
# поэтому «задние колодки» → «колодки/зад». Голый стем схлопывал переднее и заднее в одну строку.
res.append(ok({e["msg_id"] for e in ir}=={"info:6334:колодки/зад:37900","info:6334:цепь:37900"}, "msg_id по КОНТЕНТУ (info:plate:ключ:км) — идемпотентно"))
res.append(ok(len(lumped(br))==0, "лумп-строки «работы: …» НЕТ"))
res.append(ok(any("колодки" in e["notes"] for e in ir) and any("цеп" in e["notes"] for e in ir), "колодки и цепь — отдельно"))

# (b) масло+колодки+цепь БЕЗ км → буфер+переспрос; затем фото км → flush с км, без задвоения
reset()
pb={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":None,
    "works":["замена моторного масла","задние колодки","регулировка цепи"]}
br1=loop.run_until_complete(run(Msg("масло, колодки, цепь", mid=202), pb))
print("(b) работы без км → буфер, затем фото км → flush:")
res.append(ok(len(br1.events)==0, "b1: НЕ записано сразу (инфо-работы отложены)"))
res.append(ok((CHAT,TOPIC) in S._PENDING_WORKS, "b1: перечень в буфере _PENDING_WORKS"))
res.append(ok(any("Принял работы" in s for s in SENDS), "b1: квитанция (смягчённая) отправлена"))
res.append(ok(any("ODO" in s or "одометр" in s.lower() or "пробег" in s.lower() for s in SENDS), "b1: переспрос пробега отправлен"))
SENDS.clear()
# КОНТРАКТ ИЗМЕНЁН 31.07.2026 (класс-фикс одометра, корень 1, инцидент NMAX 155 GREEN-B 4957):
# раньше здесь ожидалось, что СЫРОЙ OCR с фото сам дописывает отложенные работы — именно так в прод
# и легла строка «замена передних тормозных колодок — 38982 км» при живом одометре 36982.
# Теперь фото только СПРАШИВАЕТ число, буфер ждёт; дозапись — на ПОДТВЕРЖДЕНИИ, единой точкой
# _odo_confirmed (её же зовут кнопки svc:mok/svc:sodo). Работы при этом не теряются — см. b3.
vb={"mileage":"37823","mileage_confidence":"high","fuel":"empty"}
br2=loop.run_until_complete(run(Msg(photo=True, mid=203), parsed={"type":"None","works":[]}, vis=vb))
ir2=info_rows(br2)
res.append(ok(len(ir2)==0, "b2: сырой OCR с фото инфо-работы НЕ пишет (число не подтверждено)"))
res.append(ok((CHAT,TOPIC) in S._PENDING_WORKS, "b2: буфер ЖДЁТ подтверждения (работы не потеряны)"))
br2b=FakeBridge()
S._odo_confirmed(br2b, CHAT, TOPIC, "NINJA 400 6334", "37823", questioned_km="37823", source="тест")
ir2b=info_rows(br2b)
res.append(ok(len(ir2b)==2, "b3: подтверждённый км → дозапись 2 инфо-строк"))
res.append(ok(all("37823" in e["notes"] for e in ir2b), "b3: у обеих привязан ПОДТВЕРЖДЁННЫЙ км 37823"))
res.append(ok((CHAT,TOPIC) not in S._PENDING_WORKS, "b3: буфер очищен (pop)"))

# (e) повторное фото км той же темы → НЕТ повторного flush (буфер пуст)
vb2={"mileage":"37825","mileage_confidence":"high"}
br3=loop.run_until_complete(run(Msg(photo=True, mid=204), parsed={"type":"None","works":[]}, vis=vb2))
print("(e) повторный км → без задвоения:")
res.append(ok(len(info_rows(br3))==0, "e: второй км не дописал инфо-работы (буфер уже пуст)"))

# (c) только инфо-работы (колодки/цепь), без столбцовых, без км → буфер + переспрос
reset()
pc={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":None,
    "works":["задние колодки","регулировка цепи"]}
br=loop.run_until_complete(run(Msg("поменял колодки и цепь", mid=205), pc))
print("(c) только инфо-работы без км:")
res.append(ok(len(br.events)==0 and (CHAT,TOPIC) in S._PENDING_WORKS, "буфер выставлен, сразу не пишем"))
res.append(ok(any("ODO" in s or "одометр" in s.lower() or "пробег" in s.lower() for s in SENDS), "переспрос пробега ЕСТЬ (инфо-работы тоже ждут км)"))

# (d) gear+пробег → группа B (сторож/trust путь цел), инфо-строк нет
reset()
pd={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":"37900",
    "works":["замена масла редуктора"]}
br=loop.run_until_complete(run(Msg("масло редуктора, пробег 37900", mid=206), pd))
print("(d) gear+пробег — группа B цела:")
res.append(ok(any(k=="gear" for k,_ in SVC_COL), "_ask_service_col(gear) вызван (запись группы B доступна)"))
res.append(ok(len(info_rows(br))==0, "инфо-строк нет (gear — колоночная, не история)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
