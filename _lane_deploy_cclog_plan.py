"""PLAN в cc_log + пульс: конверт одобренной заявки 10 — clasp push + redeploy Bridge (lane)."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

note = (
"PLAN " + ts + " UTC: конверт одобренной заявки 10 («да» Филиппа) — деплой Bridge с колонкой lane. "
"Шаги: gate.py → фиксация текущей версии прод-деплоя (откат) → clasp push → clasp redeploy "
"прод-deploymentId (AKfycbxNC9…) → проверка: ping alive + enqueue тестовой lane=pc + get_pending "
"БЕЗ lane её НЕ видит / lane=pc видит → тест-задачу нейтрализую (claim+complete) → DONE.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
wl = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", wl.get("ok"), "| insert_at_line:", ins)

pulse = (ts + " | 🟡 | конверт заявки 10: деплой Bridge lane — гейт→push→redeploy→проверка, выполняю | "
         "ничего не жду («да» получено) | детали→cc_log запись «PLAN конверт заявки 10 " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
