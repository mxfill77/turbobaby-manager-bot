"""Снять висящую заявку set_caps id=45 (needs_approval → failed). Обновление ОЧЕРЕДИ Bridge
(Bot Data — своя таблица бота), в рабочие листы НЕ пишем. То же, что кнопка «нет N» в devbot."""
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
REASON = ("снято штабом: адрес капов переезжает на лист памятки — цель K3 Календаря "
          "больше не актуальна, заявка невалидна (тз 328)")

# 1) снять 45
r = c.complete_task(45, "failed", REASON)
print("cancel 45:", r.get("ok"), r.get("error") or "")

# 2) страховка — если вдруг есть клоны set_caps→K3 в needs_approval/new/approved, показать
STATUSES = ["new", "needs_approval", "approved", "in_progress"]
q = c.get_pending_multi(STATUSES, lane="all")
caps_open = []
for it in q.get("items", []):
    if not isinstance(it, dict):
        continue
    if it.get("id") == 47:   # текущая задача-обёртка
        continue
    blob = (str(it.get("task_text", "")) + " " + str(it.get("result", ""))).lower()
    if ("set_caps" in blob or "toggle_cap" in blob) and ("k3" in blob or "календар" in blob or "кап" in blob):
        caps_open.append((it.get("id"), it.get("status")))
print("ОТКРЫТЫЕ set_caps→K3 после снятия (кроме тек. задачи):", caps_open if caps_open else "ПУСТО")
