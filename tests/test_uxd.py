"""Моки: UX-квитанции (по факту записи) + ЧАСТЬ D (чистка промежуточных)."""
import os, sys, json, asyncio, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL","http://x"); os.environ.setdefault("BRIDGE_TOKEN","x")
import splinter as S

CHAT=-1002751134848; TOPIC=73
class FakeSent:
    def __init__(self, mid): self.message_id=mid
_MID=[1000]
class Msg:
    def __init__(self, text=None, photo=False, mid=300):
        self.text=text; self.caption=None; self.photo=[1] if photo else None
        self.chat_id=CHAT; self.message_thread_id=TOPIC; self.from_user=None
        self.date=datetime.datetime(2026,6,9,23,0,0,tzinfo=datetime.timezone.utc); self.message_id=mid
class FakeClaude:
    def __init__(self,p=None,v=None): self._p=p or {}; self._v=v or {}
    def quick(self,*a,**k): return json.dumps(self._p)
    def vision(self,*a,**k): return json.dumps(self._v)
class FakeBridge:
    def __init__(self): self.events=[]
    def add_event(self,**kw): self.events.append(kw); return {"ok":True,"saved":True}
class FakeBot:
    def __init__(self): self.deleted=[]; self.fail=False
    async def delete_message(self,chat_id,message_id):
        if self.fail: raise RuntimeError("no rights")
        self.deleted.append(message_id)
class FakeCtx:
    def __init__(self): self.bot=FakeBot()

SENDS=[]
async def rec_send(context,*,chat_id,text,message_thread_id=None,**kw):
    SENDS.append(text); _MID[0]+=1; return FakeSent(_MID[0])
async def rec_after(context,bridge,chat_id,topic_id,bike,mileage,oil_hint=False): pass
async def rec_conf(context,chat_id,topic_id,bike,km,oil_hint=False): pass
async def rec_dl(pm): return b"img"
S._send=rec_send; S._after_mileage=rec_after; S._ask_mileage_confirm=rec_conf; S._download_photo=rec_dl

def reset(): SENDS.clear(); S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear(); S._SVC_CYCLE_MSGS.clear(); S._SVC_SUMMARY.clear(); S._ODOMETER_ASK_TS.clear()
def ok(c,l): print(("  PASS " if c else "  FAIL ")+l); return c
res=[]; loop=asyncio.new_event_loop()

# 1) текст работ БЕЗ км → СМЯГЧЁННАЯ квитанция «Принял работы» (не «Записал»); записи НЕТ; вопрос одометра в буфере
reset()
pa={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":None,
    "works":["замена моторного масла","задние колодки","регулировка цепи"]}
async def run(msg,p=None,v=None):
    br=FakeBridge(); pm=[msg] if msg.photo else None
    await S._handle_servicing(msg,context=None,bridge=br,claude=FakeClaude(p,v),photo_msgs=pm); return br
b1=loop.run_until_complete(run(Msg("масло, колодки, цепь", mid=301), pa))
print("(1) текст работ без км:")
res.append(ok(any("Принял работы" in s for s in SENDS), "квитанция СМЯГЧЕНА: «Принял работы … пришли пробег»"))
res.append(ok(not any("Записал работы" in s for s in SENDS), "НЕТ преждевременного «Записал работы»"))
res.append(ok(len(b1.events)==0 and (CHAT,TOPIC) in S._PENDING_WORKS, "работы НЕ записаны (в буфере)"))
res.append(ok(any("пробег" in s.lower() for s in SENDS) and (CHAT,TOPIC) not in S._SVC_CYCLE_MSGS,
              "пробег спрошен В КВИТАНЦИИ (одно сообщение); отдельный transient вопрос-одометр убран (фикс задвоения)"))

# 2) затем фото км 37823 → ПОДТВЕРЖДЕНИЕ → работы КОПЯТСЯ в накопитель сводки (НЕ шлются сразу — терминал мокнут)
# КОНТРАКТ ИЗМЕНЁН 31.07.2026 (класс-фикс одометра, корень 1, инцидент NMAX 155 GREEN-B 4957):
# сырой OCR с фото больше не дописывает отложенные работы — фото только спрашивает число.
# Накопитель сводки наполняет ЕДИНАЯ точка подтверждения _odo_confirmed (текст «да»/число и кнопки).
SENDS.clear()
vb={"mileage":"37823","mileage_confidence":"high"}
b2=loop.run_until_complete(run(Msg(photo=True, mid=302), p={"type":"None","works":[]}, v=vb))
print("(2) фото км → работы в накопитель сводки (единое сообщение):")
acc_raw=S._SVC_SUMMARY.get((CHAT,TOPIC),{})
res.append(ok(len(acc_raw.get("works",[]))==0, "сырой OCR сам работы НЕ проводит (число не подтверждено)"))
S._odo_confirmed(FakeBridge(), CHAT, TOPIC, "NINJA 400 6334", "37823", questioned_km="37823", source="тест")
acc2=S._SVC_SUMMARY.get((CHAT,TOPIC),{})
res.append(ok(len(acc2.get("works",[]))==2 and acc2.get("works_km")=="37823", "работы (колодки/цепь) накоплены для итоговой сводки после подтверждения (км 37823)"))
res.append(ok(not any("Записал работы на пробеге" in s for s in SENDS), "немедленной отдельной квитанции НЕТ (уйдёт в сводке на терминале)"))

# 3) работы+км в ОДНОМ сообщении → запись + накопление (сводка на терминале)
reset()
pc={"type":"event","event_type":"repair","bike":"NINJA 400 6334","mileage":"37900",
    "works":["задние колодки","регулировка цепи"]}
b3=loop.run_until_complete(run(Msg("колодки, цепь, пробег 37900", mid=303), pc))
print("(3) работы+км сразу:")
acc3=S._SVC_SUMMARY.get((CHAT,TOPIC),{})
res.append(ok(len(acc3.get("works",[]))==2 and acc3.get("works_km")=="37900", "работы накоплены (км 37900)"))

# 4) ЧАСТЬ D: _clear_cycle_msgs удаляет накопленные вопросы, буфер пуст
reset()
S._remember_cycle_msg(CHAT,TOPIC,FakeSent(501)); S._remember_cycle_msg(CHAT,TOPIC,FakeSent(502)); S._remember_cycle_msg(CHAT,TOPIC,FakeSent(503))
ctx=FakeCtx()
loop.run_until_complete(S._clear_cycle_msgs(ctx,CHAT,TOPIC))
print("(4) чистка на финале:")
res.append(ok(ctx.bot.deleted==[501,502,503], "delete_message по всем 3 вопросам"))
res.append(ok((CHAT,TOPIC) not in S._SVC_CYCLE_MSGS, "буфер очищен"))

# 5) delete_message падает → флоу не падает, буфер всё равно очищен
reset()
S._remember_cycle_msg(CHAT,TOPIC,FakeSent(601))
ctx=FakeCtx(); ctx.bot.fail=True
loop.run_until_complete(S._clear_cycle_msgs(ctx,CHAT,TOPIC))
print("(5) delete падает (нет прав):")
res.append(ok((CHAT,TOPIC) not in S._SVC_CYCLE_MSGS, "исключение проглочено, буфер очищен (best-effort)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
