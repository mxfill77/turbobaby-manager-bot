"""DONE конверта заявки 31 в cc_log (ПОД врезкой) + KB_PULSE той же операцией. Зелёная зона."""
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
with open("/tmp/cc_log_backup_env31_20260705.txt", "w", encoding="utf-8") as f:
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
"DONE " + ts + ": КОНВЕРТ ЗАЯВКИ 31 (капы low season, «да» Филиппа) — оба одобренных шага РУЧНЫЕ, "
"headless их исполнить не может (запись в живой Календарь = красное руками; clasp из headless блокирован). "
"Сделал read-only проверку готовности: зеркало /root/turbobaby-bridge-gs/QuotePrice.js содержит капы-код, "
"бэкап QuotePrice.js.bak-caps-20260705 на месте, node --check ok, tests/test_quote_caps.py 11/11 зелёные. "
"Живой Bridge: quote_price(NMAX 155CC BLACK GOLD PHUKET 4255, 06.07–05.08) отвечает (day_price=219, total=6572), "
"но cap-ключей в JSON НЕТ → прод-Bridge СТАРЫЙ, шаг 2 (clasp push + redeploy) НЕ выполнен; шаг 1 (блок капов "
"K3:M15 в «Календаре бронирования») до деплоя проверить нельзя. Повторно выдал карточку NEEDS_APPROVAL с обоими "
"шагами (порядок: 1 Календарь руками, 2 Termux: cd /root/turbobaby-bridge-gs && clasp push && clasp redeploy "
"AKfycbxNC9gCM7-…; clasp pull ПЕРЕД push НЕ делать — затрёт QuotePrice.js). "
"Проверка после: quote_price по NMAX должен вернуть cap_price=5000, cap_active=true (перезапущу проверку по запросу). "
"ХВОСТЫ: шаги 1+2 за Филиппом; после деплоя — функциональная сверка cap-полей; логика подмены цены — на userbot (отдельная задача)."
)

new_lines = lines[: sep + 1] + ["", entry] + lines[sep + 1 :]
new = "\n".join(new_lines)
w = c.write_doc(text=new, name="cc_log")
print("cc_log WRITE:", w.get("ok"), "| old:", len(old), "new:", len(new))
if not w.get("ok"):
    raise SystemExit(1)

pulse = (ts + " | 🟡 | конверт заявки 31: зеркало+тесты капов готовы (11/11), прод-Bridge СТАРЫЙ (cap-ключей нет) | "
"жду от Филиппа 2 ручных шага: капы в Календарь руками + clasp push/redeploy из Termux (pull НЕ делать) | "
"детали→cc_log запись DONE " + ts)
p = c.write_doc(text=pulse, name="pulse")
print("pulse WRITE:", p.get("ok"))
