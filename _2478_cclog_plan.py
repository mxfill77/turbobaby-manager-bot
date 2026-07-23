import sys, os
sys.path.insert(0, '/root/turbobaby-manager-bot')
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

client = BridgeClient(os.environ['BRIDGE_URL'])

r = client._call('read_doc', name='cc_log')
if not r.get('ok'):
    print(f"ERROR reading cc_log: {r}")
    sys.exit(1)

old = r.get('content', '') or r.get('text', '') or str(r)

entry = (
    "PLAN 2026-07-15 12:20 UTC (headless): Правка ТО XADV 750 GREY 2478 по слову владельца. "
    "ФАКТЫ: (1) Лист1 col I oil_last_km=24997 НЕВЕРНО (д.б. 24500) — баг: bot брал km из vision-фото вместо km замены. "
    "(2) Текущий odo=24997 подтверждён в conversations ID 387 (11:20:46); след коррекции 24997→24500 не сохранился. "
    "(3) service_pending rows 2+3 (updated 11:17:49 и 11:21:28): odo=24997, закрыто — API правки закрытых нет, только ручная Sheets. "
    "(4) После фикса Лист1: oil=24500 next=29500 left=4503. "
    "КОНВЕРТ: ручная правка Лист1 col I + инструкция по service_pending. "
    "Ничего сверх 2478 не трогается."
)

pulse = (
    "2026-07-15 12:20 | 🟡 | [2478 ТО] PLAN выдан: Лист1 col I 24997→24500 ждёт да Филиппа | "
    "конверт в 328 | детали→cc_log PLAN 2026-07-15 12:20"
)

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
print(f"cc_log: ok={r2.get('ok')} action={r2.get('action')}")

r3 = client.write_doc(text=pulse, name='pulse')
print(f"pulse: ok={r3.get('ok')}")
