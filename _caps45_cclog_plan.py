"""PLAN в cc_log (ПОД врезкой) + KB_PULSE той же операцией. Зелёная зона."""
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
with open("/tmp/cc_log_backup_caps45_20260705.txt", "w", encoding="utf-8") as f:
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
"PLAN " + ts + ": [капы — доделка без рук владельца, тз 328] "
"(1) KB knowledge_base: раздел «Правила цен v2»+памятка+«нет в парке»+правило Bot Data уже в git (d1edd28) — "
"добавлю уточнение «J-текст дословно КРОМЕ кап-случая» и синкну Brain write_doc(name=knowledge_base). "
"(2) Зеркало Bridge (/root/turbobaby-bridge-gs): новые POST-экшены set_caps (создать/обновить блок K3:M15 "
"«Модель|Кап|Активен» по списку, confirmed-гейт) и toggle_cap (model, on/off, confirmed-гейт) в QuotePrice.js + "
"роутинг в Bridge.js + оба в REDZONE_LOCK; cap-поля quote_price не трогаю. Бэкапы .bak-setcaps-20260705. "
"(3) Тесты tests/test_set_caps.py (зеркало логики + node --check + роутинг/гейты), гейт, commit+push. "
"(4) Карточка с командами clasp push/redeploy для Termux. Вызов set_caps на прод — ПОСЛЕ «деплой сделан» "
"(отдельная задача, красная карточка)."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟢 | тз 328 «капы-доделка»: начал — KB-уточнение+синк, set_caps/toggle_cap в зеркале Bridge, тесты | "
"ничего не жду, работаю | детали→cc_log запись PLAN " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
