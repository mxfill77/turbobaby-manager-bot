# cc_log DONE + pulse одной операцией (зелёная зона, журнальные строки)
import sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
from dotenv import load_dotenv
load_dotenv("/root/turbobaby-manager-bot/.env")
from bridge_client import BridgeClient

b = BridgeClient(timeout=90)

ENTRY = """DONE 2026-07-03 15:02 UTC: [задача 328] проверка деплоя Bridge — quote_price и склейка статусов ПОДТВЕРЖДЕНЫ на проде (read-only, прод не трогал).
- ping ok v1.0.0. quote_price живой: bike=4957 (NMAX 155CC GREEN-B, ДОМА) 04.07–11.07 → ok=true, 7 дней, 317/день, total=2217, депозит=3000, available=true, conflicts=0, season=low (global_discount=0.25).
- Запрошенный в задаче PCX 160: в парке НЕТ такой модели (38 байков: NMAX/XMAX/ADV/CLICK/CB/FORZA/...) → quote_price вернул корректный bike_not_resolved (НЕ unknown_action) — роутинг действия на проде есть.
- Склейка статусов: get_pending status="done,failed" → ok=true, statuses=["done","failed"], items=6 (НЕ unknown_action).
- Хвостов нет. Хелперы: _qp_check_prod/_qp_fleet_struct/_qp_names/_qp_live/_qp_cclog_done.py (read-only).
"""

doc = b._call("read_doc", name="cc_log")
if not doc.get("ok"):
    print("READ FAILED, не пишу:", doc)
    sys.exit(1)
text = doc.get("text") or doc.get("content") or ""
lines = text.split("\n")
# врезка: найти ПОСЛЕДНЮЮ строку шапки — закрывающую ═-only линию стартового блока
insert_at = 0
eq_lines = [i for i, ln in enumerate(lines[:80]) if ln.strip() and set(ln.strip()) == {"═"}]
if len(eq_lines) >= 2:
    insert_at = eq_lines[1] + 1  # под закрывающей линией врезки
elif len(eq_lines) == 1:
    insert_at = eq_lines[0] + 1
new_text = "\n".join(lines[:insert_at] + ["", ENTRY] + lines[insert_at:])
w = b.write_doc(new_text, name="cc_log")
print("cc_log write:", {k: w.get(k) for k in ("ok", "error", "id", "name")})

PULSE = ("2026-07-03 15:02 | 🟢 | деплой Bridge подтверждён: quote_price live (NMAX 4957, 7дн=2217бат, "
         "available=true; PCX 160 в парке нет → bike_not_resolved) + склейка get_pending CSV→statuses ok | "
         "ничего не жду | детали→cc_log запись «03.07 проверка деплоя Bridge»")
p = b.write_doc(PULSE, name="pulse")
print("pulse write:", {k: p.get(k) for k in ("ok", "error", "id", "name")})
