"""DONE в cc_log (проверка деплоя Bridge: quote_price + склейка, задача из 328) + пульс — ОДНА операция.
Зелёная зона. Врезка сохраняется: вставка ПОД шапкой (после последней ═-only строки в начале дока)."""
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
"DONE " + ts + " UTC: ПРОВЕРКА деплоя Bridge (задача из 328, headless, read-only) — quote_price и "
"склейка статусов на прод ЕЩЁ НЕ ВЫКАЧЕНЫ, зеркало готово и проверено.\n"
"а) Прод (BRIDGE_URL, живой GET): ping ok v1.0.0 alive; quote_price → unknown_action; get_pending "
"status=done,failed → ok, но БЕЗ поля statuses (маркер CSV-склейки) → прод старше 02.07 22:08, "
"clasp push+redeploy после сборки не выполнялись (ожидаемо: clasp login протух, ждёт владельца — "
"см. DONE «quote_price 2026-07-03» ниже).\n"
"б) Зеркало /root/turbobaby-bridge-gs: QuotePrice.js (03.07 12:44) + роутинг в Bridge.js + склейка "
"getPending_ CSV в BotData.js (02.07 22:08) — всё на месте. Локальный функциональный тест "
"_quote_local_test.js перепрогнан: 27/27 PASS (эталоны = живая J-колонка Календаря).\n"
"в) Склейка: демон НЕ деградирует — get_pending_multi в bridge_client.py тихо фоллбэчит на "
"по-статусные вызовы, пока прод без CSV (просто 4 вызова вместо 1).\n"
"г) Пример ответа quote_price (ЛОКАЛЬНАЯ эмуляция _quote_example.js на живом снимке цен 03.07, "
"НЕ с прода): bike=4957, 08.07–15.07 → {ok:true, bike:'NMAX 155CC GREEN-B PHUKET 4957', model:"
"'YAMAHA NMAX 155', days:7, day_price:317, total:2217, deposit:3000, available:true, conflicts:0, "
"season:{label:'low', global_discount:0.25}, text:'YAMAHA NMAX 155 | дней: 7, стоимость: 2217 "
"(скидка за срок 6%, 317 в день), депозит: 3000 бат'}.\n"
"Статус честно: технически готово в зеркале + функционально сверено ЛОКАЛЬНО; на проде НЕ работает "
"до деплоя. ХВОСТЫ (без изменений): 1) владелец: clasp login → clasp push → clasp redeploy "
"<прод-deploymentId>; 2) после деплоя — ping + quote_price live + CSV-проба get_pending; "
"3) обёртка quote_price() в bridge_client.py — после деплоя.\n"
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

pulse = (ts + " | 🟡 | проверка деплоя Bridge: прод БЕЗ quote_price и БЕЗ склейки (unknown_action / "
         "нет statuses), зеркало готово, локальный тест 27/27, пример ответа получен локально | жду: "
         "clasp login+push+redeploy руками владельца (кнопка в 328) | детали→cc_log запись "
         "«ПРОВЕРКА деплоя " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
