"""DONE в cc_log (ПОД врезкой) + KB_PULSE той же операцией. Зелёная зона."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)

old = r.get("text", "")
with open("/tmp/cc_log_backup_setcaps_cancel_20260705.txt", "w", encoding="utf-8") as f:
    f.write(old)

lines = old.split("\n")
sep = None
for i, ln in enumerate(lines):
    s = ln.strip()
    if s and set(s) == {"═"}:
        sep = i
        break
if sep is None:
    print("ВРЕЗКА НЕ НАЙДЕНА — НЕ пишу")
    raise SystemExit(1)

ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
entry = (
"DONE " + ts + ": [тз 328: снять висящие заявки set_caps→K3] Разведка очереди Bridge (read-only, 47 задач): "
"из «43/44/45» реально висела ОДНА — id=45 needs_approval (конверт одобр. заявки 44 → set_caps «Календарь» K3, "
"адрес капов переезжает на лист памятки → карточка невалидна). id=42/43/44 = цепочка конвертов, уже done; "
"id=41 уже failed (кнопка). Снял id=45 → complete_task(45, failed, «адрес капов переезжает на памятку, K3 не цель»). "
"Обновил ОЧЕРЕДЬ Bridge (Bot Data — своя таблица), в рабочие листы/K3 НЕ писал. Проверка после снятия: открытых "
"set_caps/toggle_cap→K3 в new/needs_approval/approved/in_progress НЕТ (кроме тек. задачи-обёртки 47) — очередь пуста. "
"Хвост: боевой набор капов на K3 (или на лист памятки) — отдельной задачей по новому адресу."
)
new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟢 | тз 328: висящая заявка set_caps→K3 id=45 снята (needs_approval→failed), очередь set_caps→K3 пуста | "
"ничего не жду | детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
