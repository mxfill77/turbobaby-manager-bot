import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

client = BridgeClient(os.environ['BRIDGE_URL'])

# Read current cc_log
r = client._call('read_doc', name='cc_log')
if not r.get('ok'):
    print(f"ERROR reading cc_log: {r}")
    sys.exit(1)

old = r.get('content', '') or r.get('text', '') or str(r)
print(f"cc_log read ok, length={len(old)}")

entry = "DONE 2026-07-15 18:53 UTC (headless): [куратор цели 104, шаг 1] READ-ONLY разбор ТО XADV 750 GREY 2478 15.07 11:05-11:25 UTC. (а) Лист1 col I oil_last_km=24997 (НЕВЕРНО, д.б. 24500), next_km=29997 (д.б. 29500), байк в аренде до 17.07 18:00. (б) memory.db: topic_bike→тема 83; 2 service_pending закрытых odo=24997, written @turbophuket1. (в) splinter.log: 11:15:35 «коррекция пробега ПРИМЕНЕНА обход сторожа B 24997→24500» БЕЗ явного да владельца; ТО oil записано ДВАЖДЫ (11:17:51 и 11:21:29) на км 24997, хотя замена масла на 24500. Баг: set_service брал km из vision-фото (24997), а не km замены (24500). Нужна ручная правка Лист1 col I: 24997→24500."

# Insert under vrezka
lines = old.split("\n")
idx = None
for i, ln in enumerate(lines[:15]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        idx = i
        break

if idx is None:
    new_content = entry + "\n\n" + old
else:
    head = "\n".join(lines[:idx + 1])
    rest = "\n".join(lines[idx + 1:]).lstrip("\n")
    new_content = head + "\n\n" + entry + "\n\n" + rest

r2 = client.write_doc(text=new_content, name='cc_log')
print(f"cc_log write: ok={r2.get('ok')} action={r2.get('action')}")

# Update pulse
pulse = "2026-07-15 18:53 | 🟡 | [куратор 104 шаг 1] done: oil_last XADV 2478 = 24997 в Лист1 (д.б. 24500), баг set_service, нужна ручная правка | жду шаг 2/2 | детали→cc_log «куратор цели 104, шаг 1»"
r3 = client.write_doc(text=pulse, name='pulse')
print(f"pulse write: ok={r3.get('ok')} action={r3.get('action')}")
