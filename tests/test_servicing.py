"""Моки _handle_servicing: проверка фикса «молчание на текст-пояснение работ».
Сценарии a–e из PLAN. Никаких сетевых вызовов — bridge/claude/_send замоканы."""
import os, sys, json, asyncio, datetime, types
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
# Предмет этого сьюта — поведение веток ДО замка повторов (22.08.2026): сценарии гоняют ОДИН и
# тот же байк с ОДНИМ и тем же состоянием подряд, и живой замок законно счёл бы их повторами.
# Изоляция принудительная (не setdefault): иначе флаг приезжает из боевого .env процесса.
# Тот же приём, что у CURATOR / PLAN_ADAPT / CARD_DUTY / ASK_DEDUP.
os.environ["HINTS_DEDUP"] = "0"
import splinter as S

CHAT = -1002751134848
TOPIC = 77

class Msg:
    def __init__(self, text):
        self.text = text; self.caption = None; self.photo = None
        self.chat_id = CHAT; self.message_thread_id = TOPIC
        self.date = datetime.datetime(2026, 6, 9, 17, 50, 58, tzinfo=datetime.timezone.utc)
        self.message_id = 8857

class FakeClaude:
    def __init__(self, parsed): self._parsed = parsed
    def quick(self, system, text, max_tokens=300, **kw): return json.dumps(self._parsed)
    def vision(self, *a, **k): return "{}"

class FakeBridge:
    def __init__(self): self.events = []
    def add_event(self, **kw): self.events.append(kw); return {"ok": True}

# ---- перехват исходящих ----
SENDS = []; SVC_COL = []; AFTER_MIL = []; ASK_CONF = []
async def rec_send(context, *, chat_id, text, message_thread_id=None, **kw): SENDS.append(text)
async def rec_svc_col(context, chat_id, topic_id, bike, kind, km, **kw): SVC_COL.append((kind, km))
async def rec_after(context, bridge, chat_id, topic_id, bike, mileage, oil_hint=False): AFTER_MIL.append(mileage)
async def rec_conf(context, chat_id, topic_id, bike, km, oil_hint=False): ASK_CONF.append(km)
async def rec_dl(pm): return None
S._send = rec_send; S._ask_service_col = rec_svc_col
S._after_mileage = rec_after; S._ask_mileage_confirm = rec_conf
S._download_photo = rec_dl

def reset(clear_cooldown=True):
    SENDS.clear(); SVC_COL.clear(); AFTER_MIL.clear(); ASK_CONF.clear()
    S._RECENT_PHOTOS.clear(); S._PENDING_WORKS.clear()
    if clear_cooldown:
        S._ODOMETER_ASK_TS.clear()

def seed_high_buffer():
    """Доработочный замер сверки: high-пробег 37823 в буфере (как в реальном кейсе)."""
    S._RECENT_PHOTOS[(CHAT, TOPIC)] = [{
        "ts": S._time.time(), "msg_id": 1,
        "vis": {"mileage": "37823", "mileage_confidence": "high"},
    }]

async def run(text, parsed):
    bridge = FakeBridge()
    await S._handle_servicing(Msg(text), context=None, bridge=bridge, claude=FakeClaude(parsed))
    return bridge

def has_receipt(): return any("Принял работы" in s for s in SENDS)
# просьба пробега теперь ВНУТРИ квитанции («пришли пробег»/«ส่งเลขไมล์») — отдельного msg_ask_odometer в инфо-ветке больше нет
def has_odo():     return any("ODO" in s or "одометр" in s.lower() or "пробег" in s.lower() or "เลขไมล์" in s for s in SENDS)

def ok(cond, label):
    print(("  PASS " if cond else "  FAIL ") + label)
    return cond

results = []
loop = asyncio.new_event_loop()

# ---- (a) масло+колодки+цепь текстом, high-буфер → событие repair + квитанция + переспрос пробега, НЕ молчание ----
reset(); seed_high_buffer()
parsed_a = {"type":"event","event_type":"repair","bike":"NINJA 400 6334","fuel":None,"mileage":None,
            "works":["замена моторного масла","масляный фильтр","задние колодки","регулировка цепи"],
            "notes":"работы по обслуживанию"}
b = loop.run_until_complete(run("выполнены работы: замена моторного масла, масляного фильтра, задние колодки, регулировка цепи", parsed_a))
print("(a) масло+колодки+цепь, high-буфер в теме:")
results.append(ok(len(b.events)==0 and (CHAT,TOPIC) in S._PENDING_WORKS, "инфо-работы ОТЛОЖЕНЫ в буфер (нет км в сообщении) — пишутся при приходе пробега"))
results.append(ok(has_receipt(), "квитанция «Принял работы» отправлена"))
results.append(ok(has_odo(), "переспрос пробега отправлен (high-буфер ОБОЙДЁН — force)"))
results.append(ok(len(SENDS)>=1, "НЕ молчание (есть исходящие)"))
results.append(ok(len(SVC_COL)==0, "(d) группа B НЕ тронута без пробега (нет записи в столбец)"))

# ---- (b) info-only (колодки/цепь) → событие+квитанция, переспроса НЕТ ----
reset()
parsed_b = {"type":"event","event_type":"repair","bike":"NINJA 400 6334","fuel":None,"mileage":None,
            "works":["задние колодки","регулировка цепи"],"notes":"работы"}
b = loop.run_until_complete(run("поменяли задние колодки и отрегулировали цепь", parsed_b))
print("(b) info-only (колодки/цепь):")
results.append(ok(len(b.events)==0 and (CHAT,TOPIC) in S._PENDING_WORKS, "инфо-работы отложены в буфер (нет км)"))
results.append(ok(has_receipt(), "квитанция отправлена"))
results.append(ok(has_odo(), "переспрос пробега ЕСТЬ (инфо-работы тоже ждут км для истории)"))
results.append(ok(len(SVC_COL)==0, "группа B не тронута"))

# ---- (c) текст без работ → как раньше (молчание, без события) ----
reset()
parsed_c = {"type":"none","event_type":"other","bike":None,"fuel":None,"mileage":None,"works":[],"notes":""}
b = loop.run_until_complete(run("когда вернётся в офис — посмотрим", parsed_c))
print("(c) текст без работ (болтовня):")
results.append(ok(len(b.events)==0, "событие НЕ записано (ранний return)"))
results.append(ok(len(SENDS)==0, "молчание (как раньше)"))

# ---- (d) сторож B/trust не затронуты: works+gear+ПРОБЕГ текстом → группа B вызвана (путь записи цел) ----
reset()
parsed_d = {"type":"event","event_type":"repair","bike":"NINJA 400 6334","fuel":None,"mileage":"37900",
            "works":["масло редуктора"],"notes":"gear oil"}
b = loop.run_until_complete(run("заменили масло редуктора, пробег 37900", parsed_d))
print("(d) works(gear)+пробег текстом — путь группы B цел:")
results.append(ok(any(k=="gear" for k,_ in SVC_COL), "_ask_service_col(gear) вызван (запись группы B доступна)"))
results.append(ok(not has_receipt(), "квитанция-без-пробега НЕ перехватила (mileage есть → обычный флоу)"))

# ---- (e) НЕ ЗАДВАИВАНИЕ: инфо-работы без км → РОВНО ОДНО исходящее (квитанция), без дубля-«масло» ----
reset(); seed_high_buffer()
loop.run_until_complete(run("выполнены работы: задние колодки, регулировка цепи", parsed_b))
print("(e) фикс задвоения: одно сообщение, без хардкод-«масло»:")
results.append(ok(len(SENDS) == 1, f"ровно ОДНО исходящее (квитанция), дубля msg_ask_odometer нет — а {len(SENDS)}"))
results.append(ok(has_receipt() and has_odo(), "квитанция называет работы И просит пробег (в одном сообщении)"))
results.append(ok(not any("Вижу замену масла" in s for s in SENDS), "НЕТ ложного «Вижу замену масла» (масла в работах нет)"))

loop.close()
print("\nИТОГ:", "ВСЕ PASS" if all(results) else f"ЕСТЬ FAIL ({sum(results)}/{len(results)})")
sys.exit(0 if all(results) else 1)
