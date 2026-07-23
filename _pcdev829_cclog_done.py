"""DONE «тема PC-дев = 829» в cc_log (ПОД врезкой, после ═-only строки) + пульс той же операцией."""
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
"DONE " + ts + " UTC: тема «PC-дев» ПОДКЛЮЧЕНА — боевой id 829 прописан (хвосты 2+3 записи «lane=pc "
"2026-07-04», headless-задача из 328). Commit 2460065, push 2460065, гейт 35/35 ×3 (до push, pre-push, "
"до restart), restart splinter — старт чистый (active, Bridge ✅ alive v1.0.0, 0 ошибок после старта 10:13).\n"
"а) .env: + PC_DEV_TOPIC_ID=829 (бэкап .env.bak-pcdev-20260704; .env вне git). Код НЕ менялся — "
"devbot/splinter читают id лениво из env (0bb38df), после restart полоса в теме 829 активна: "
"«тз:»/«задача:» только от Филиппа → enqueue lane=pc, карточки статусов/needs_approval/итогов lane=pc "
"→ тема 829 (кнопки как в 328), splinter тему 829 игнорит.\n"
"б) Тесты маршрутизации: tests/test_lane_pc.py 8→10. L9 боевой id 829: «тз:»/«задача:» в 829 → enqueue "
"lane=pc + карточка в 829, не-Филипп — игнор, splinter.is_ignored_thread(829)=true, guard конфиг-дрейфа "
"(.env содержит PC_DEV_TOPIC_ID=829). L10 VPS-демон: process_new опрашивает get_pending БЕЗ lane → "
"на новом Bridge дефолт vps, pc-задачи не берёт.\n"
"⚠️ ЧЕСТНО: «VPS-демон не берёт» подтверждено НА МОКАХ и заработает в проде ТОЛЬКО после clasp redeploy "
"Bridge (хвост 1, КРАСНОЕ, всё ещё ждёт «да»). ПРОД-Bridge СЕЙЧАС без колонки lane: enqueue из 829 "
"пройдёт (lane-параметр /exec игнорит), но get_pending(new) вернёт задачу ВСЕМ → VPS-демон её ВОЗЬМЁТ "
"и исполнит на VPS. До redeploy «тз:» в 829 НЕ писать (карточки при этом уже маршрутизируются в 829 "
"по метке from — это работает). Живой enqueue-тест НЕ гонял сознательно (загрязнил бы очередь + "
"VPS-демон бы забрал).\n"
"Откат: git revert 2460065; строку PC_DEV_TOPIC_ID убрать из .env (бэкап .env.bak-pcdev-20260704) + restart.\n"
"ХВОСТЫ (включение полосы pc): 1) clasp push + redeploy прод-Bridge (КРАСНОЕ, ждёт «да»; после — живая "
"проверка: enqueue lane=pc тестовой, get_pending без lane НЕ видит / lane=pc видит, complete сразу); "
"2) [СДЕЛАНО этой задачей] id 829 в .env + restart; 3) ПК-агент-исполнитель полосы pc — отдельная задача.\n"
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

pulse = (ts + " | 🟡 | тема PC-дев=829 подключена: .env PC_DEV_TOPIC_ID=829, +2 теста (гейт 35/35), "
         "push 2460065, restart splinter чистый | жду «да» на clasp redeploy Bridge (без него VPS-демон "
         "заберёт pc-задачи — «тз:» в 829 пока не писать) | детали→cc_log запись «PC-дев 829 " + ts[:10] + "»")
p = c.write_doc(text=pulse, name="pulse")
print("WRITE pulse:", p.get("ok"))
