"""DONE в cc_log (проверка деплоя quote_price + склейки, задача из 328) + пульс — ОДНА операция.
Зелёная зона (read-only проверки + журнал). Врезка сохраняется: вставка ПОД шапкой."""
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
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

note = (
"DONE " + ts + " UTC: ДЕПЛОЙ Bridge ПРОВЕРЕН ЖИВЬЁМ (задача из 328, headless, read-only) — "
"quote_price И склейка статусов НА ПРОДЕ, работают.\n"
"1) ping: ok, v1.0.0, alive (первый вызов дал транзиентный 404 на googleusercontent-redirect, "
"повтор чистый — известный флап GAS, не признак поломки).\n"
"2) quote_price ЖИВОЙ: bike=4957 → NMAX 155CC GREEN-B PHUKET 4957, ближайшее свободное окно "
"04.07–11.07.2026 (свободно сразу с завтра, conflicts=0, available=true): 7 дней, 317/день, "
"total 2217, депозит 3000, сезон low (глоб.скидка скутеров 25%). СВЕРКА С ЭТАЛОНОМ: цифры "
"совпадают 1-в-1 с J-колонкой Календаря (CSV-экспорт 03.07: «дней: 7 стоимость: 2217, скидка 6%, "
"317 в день, депозит 3 000») — функционально ПОДТВЕРЖДЕНО.\n"
"3) ПРО PCX 160 (пример из ТЗ): в прайсе 'цены альт' модель ЕСТЬ (QUOTE_MODELS row 24), но в ПАРКЕ "
"(fleet, 38 байков) ни одного PCX нет вообще → quote_price честно вернул bike_not_resolved "
"(«не найден однозначно в 'список мото'») — корректное поведение, не баг. Живой прогон сделан "
"на реальном байке 4957.\n"
"4) Склейка статусов ЖИВАЯ: get_pending status='done,failed' → ok=true, statuses=['done','failed'] "
"(маркер поддержки CSV на месте), items=5 одним вызовом — feature-detect для "
"bridge_client.get_pending_multi работает.\n"
"Хелперы проверки: _quote_prod_check2/3/4.py (read-only). Прод не менялся, записи никуда не было.\n"
"ХВОСТ (прежний, остаётся): обёртка quote_price() в bridge_client.py — отдельной зелёной задачей.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
w = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", w.get("ok"), "| old_len:", len(old), "new_len:", len(new), "| insert_at_line:", ins)

pulse = (ts + " | 🟢 | деплой Bridge проверен живьём: quote_price работает (NMAX 4957, 04-11.07, "
         "2217/317/деп.3000 = эталон Календаря 1-в-1) + склейка статусов CSV ok (items=5 одним вызовом); "
         "PCX 160 в парке нет — bike_not_resolved корректен | ничего не жду | детали→cc_log запись "
         "«проверка деплоя " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
