"""Запись DONE в cc_log + пульс одной операцией (headless-задача «проверь X»)."""
from datetime import datetime, timezone

from bridge_client import BridgeClient
from cclog import _insert_under_vrezka

now = datetime.now(timezone.utc)
ts = now.strftime("%Y-%m-%d %H:%M")

entry = (
    f"DONE {ts} UTC (headless): задача «проверь X» — текст без конкретики (похоже на след "
    f"утечки тест-фикстур 16.07, ср. конверт 999 «нечто/X»); исполнено как read-only health-чек. "
    f"Итог: splinter active (планировщики ок, свежих ошибок нет — только Bridge-таймауты 12:51/13:45 "
    f"и telegram-исключения 21:32), orchestrator-daemon active — но в 21:50 UTC был убит OOM "
    f"(пик 1.6G RAM + 1.7G swap, restart counter 2), авто-рестарт 21:51 чистый (mem_gate on, avail 1562MB); "
    f"из-за OOM цепь родителя 185 остановлена на шаге 2/6 (exit -9), шаги 3-6 пропущены, сводка → задача 192. "
    f"Bridge ping ok (v1.0.0). Память сейчас: avail ~327MB, swap 278MB/2048MB — тесно, но живо. "
    f"Сейчас исполняется задача 193 (фикс класса утечки фикстур, dev 45 мин) — не трогал. "
    f"Никаких записей в рабочие таблицы, чисто чтение. Хвост: OOM-риск демона при claude-подпроцессах — "
    f"память впритык, follow-up у задачи 193/владельца."
)

pulse = (
    f"{ts} | \U0001F7E2 | «проверь X» исполнена read-only health-чеком: сервисы active, Bridge ok; "
    f"OOM-kill демона 21:50 закрыт авто-рестартом, цепь 185 halt (сводка 192), задача 193 в работе "
    f"| ничего не жду | детали→cc_log запись 17.07 «проверь X»"
)

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    raise SystemExit(f"READ FAIL — не пишу: {r}")
new = _insert_under_vrezka(r.get("text", ""), entry)
w = c.write_doc(text=new, name="cc_log")
print("cc_log:", "OK" if w.get("ok") else w)
wp = c.write_doc(text=pulse, name="pulse")
print("pulse:", "OK" if wp.get("ok") else wp)
