"""BLOCKED в cc_log (ПОД врезкой) + KB_PULSE той же операцией — боевой set_caps ждёт «да».
Зелёная зона (журнальные строки). Сам set_caps НЕ вызываем — красное, ждём approve."""
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
with open("/tmp/cc_log_backup_caps_boevoy_20260705.txt", "w", encoding="utf-8") as f:
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
"BLOCKED " + ts + ": [капы — боевой set_caps, тз 328] Bridge @63 задеплоен (set_caps/toggle_cap в проде). "
"Задача: записать блок капов 12 моделей в лист «Календарь бронирования» через set_caps (флаг confirmed) "
"(payload = SET_CAPS_PAYLOAD из tests/test_set_caps.py: NMAX 5000·XMAX OLD 8900·XMAX NEW 9900·ADV350 10900·"
"Forza300 7900·XSR155 7490·CB300R 9900·MT-03 10990·Ninja400 11900·CB650R/CBR650R 18900·Vulcan 18900·XADV750 33900, "
"все «да»). Запись в ЖИВОЙ Календарь = 🔴 красное (там параллельно работают люди) → headless САМ не пишет, "
"выведена карточка approve в 328 (NEEDS_APPROVAL op=other). ПОСЛЕ «да» и записи: живой quote_price NMAX 4255 на 30 дней — "
"показать cap_price/cap_active + текст оффера; затем обновить пульс на 🟢. "
"ХВОСТ: боевой set_caps ждёт «да» Филиппа · quote_price NMAX после записи · подмена цены на userbot — отдельно."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🔴 | капы боевые: Bridge @63 в проде, готов вызвать set_caps (12 моделей, флаг confirmed) в живой "
"«Календарь бронирования» — карточка approve выведена в 328 | жду «да» Филиппа на запись; после записи → живой "
"quote_price NMAX 4255/30дн (cap_price/cap_active) + пульс на 🟢 | детали→cc_log запись BLOCKED " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
