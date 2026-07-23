"""DONE в cc_log + пульс: повторный селфтест полосы pc 8/8.
cc_log: вставка ПОД шапкой (после последней ═-only строки); пульс — той же операцией."""
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()
from bridge_client import BridgeClient

c = BridgeClient()

r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ cc_log FAIL — НЕ пишу:", r)
    raise SystemExit(1)
old = r.get("text", "")
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

note = (
"DONE " + ts + " UTC: повторный селфтест полосы pc — 8/8 ALL PASS (headless-задача из 328; "
"_lane_pc_selftest.py, тестовая задача id=18, метка selftest-lane-pc — карточек в TG нет). "
"Ключевое: get_pending БЕЗ lane тестовую НЕ видит (lane=vps, ids=[]), get_pending lane=pc — ВИДИТ; "
"claim lane=vps → wrong_lane (guard), claim lane=pc → ok; complete done; в new (lane=all) пусто. "
"Прод-Bridge с колонкой lane работает функционально ПОДТВЕРЖДЁННО (живой /exec). Код не менялся, "
"read-only для прода (запись только в Bridge-очередь Bot Data). "
"ХВОСТЫ включения полосы pc: 1) id темы PC-дев в .env — СДЕЛАНО (829, commit 2460065); "
"2) ПК-агент-исполнитель полосы pc (опрос get_pending lane=pc + claim lane=pc) — отдельная задача, на VPS его нет.\n"
)

lines = old.split("\n")
ins = 0
for i, ln in enumerate(lines[:80]):
    s = ln.strip()
    if s and set(s) == {"═"}:
        ins = i + 1
new = "\n".join(lines[:ins]) + ("\n" if ins else "") + note + "\n" + "\n".join(lines[ins:])
wl = c.write_doc(text=new, name="cc_log")
print("WRITE cc_log:", wl.get("ok"), "| old_len:", len(old), "new_len:", len(new), "| insert_at_line:", ins)

pulse = (ts + " | 🟢 | селфтест полосы pc повторно 8/8 ALL PASS: Bridge-очередь фильтрует по lane "
         "(без lane pc-задачу не видно, lane=pc видно, guard wrong_lane работает), тестовая задача закрыта | "
         "ничего не жду; хвост — ПК-агент-исполнитель полосы pc | детали→cc_log запись «селфтест pc " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
