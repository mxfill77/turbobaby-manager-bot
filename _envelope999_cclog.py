"""cc_log DONE + KB_PULSE для конверта 999 (placeholder-задача, ТЗ=X).
Запись ПОД врезкой (матч ═-only строки), write только если read ok. Зона 🟢."""
from dotenv import load_dotenv
load_dotenv(override=True)
from bridge_client import BridgeClient

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — НЕ пишу:", r)
    raise SystemExit(1)

old = r.get("text", "")
entry = "DONE 2026-07-17 00:46 UTC: конверт 999 — задача-заполнитель (исходная задача = «X», нет реального ТЗ), ничего не выполнено\n"

lines = old.splitlines(keepends=True)
ins = 0
for i, ln in enumerate(lines[:10]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
        break
new = "".join(lines[:ins]) + entry + "\n" + "".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| вставка после строки", ins, "| old:", len(old), "new:", len(new))

pulse = "2026-07-17 00:46 UTC | 🟢 | конверт 999: placeholder-задача, ТЗ пусто (X) — ничего не сделано | ничего не жду | детали→cc_log запись 2026-07-17"
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
