"""DONE в cc_log (обёртка quote_price() в bridge_client.py, зелёный хвост из 328) + пульс — ОДНА операция.
Врезка сохраняется: вставка ПОД шапкой (после последней ═-only строки в начале дока)."""
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
"DONE " + ts + " UTC: обёртка quote_price() в bridge_client.py СОБРАНА, тесты+гейт зелёные, запушено "
"(зелёный хвост из cc_log «конверт 2 деплоя Bridge», headless-задача из 328). Commit af6d2d7.\n"
"а) BridgeClient.quote_price(bike, date_start, date_end) — read-only GET-вызов экшена quote_price "
"(QuotePrice.gs на проде). ok → возвращает dict Bridge целиком (day_price, total, deposit, available, "
"conflicts, season, text + bike/model/days); ЛЮБАЯ ошибка (не-ok, таймаут, кривой JSON, неожиданный "
"Exception) → None — вызывающий код не падает. Размещена в секции read-only методов после daily_pulse.\n"
"б) Тесты: tests/test_quote_price.py — 5 мок-кейсов (requests.get подменён, живой Bridge НЕ дёргался): "
"ok → dict со всеми 7 ключами + сверка GET-параметров; bike_not_resolved → None; таймаут → None; "
"кривой JSON → None; RuntimeError в _call → None. Файл в tests/ — гейт цепляет автоматически.\n"
"в) Гейт: 34/34 зелёные (был 33 + новый). py_compile чисто. Push через pre-push hook (гейт прошёл "
"повторно): 03c3b58..af6d2d7 main.\n"
"г) Прод-Bridge НЕ тронут (только клиентская обёртка). Бэкап = bridge_client.py.bak-quoteprice-20260703 "
"(в репо) + git; откат = git revert af6d2d7.\n"
"Статус: технически готово (тесты на моках); функционально против живого прода обёртку не гонял "
"(сам экшен quote_price на проде уже проверен живьём ранее — запись «проверка деплоя» 03.07).\n"
"ХВОСТОВ НЕТ: зелёный хвост «обёртка quote_price() в bridge_client.py» из записи «конверт 2 деплоя "
"Bridge» — ЗАКРЫТ. Подключение обёртки к мозгу/сплинтеру (tool для claude_client) — отдельной задачей, "
"если понадобится.\n"
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

pulse = (ts + " | 🟢 | обёртка quote_price() в bridge_client.py готова: ok→dict/ошибка→None, 5 мок-тестов, "
         "гейт 34/34, push af6d2d7; прод не тронут | ничего не жду | детали→cc_log запись «обёртка "
         "quote_price " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
