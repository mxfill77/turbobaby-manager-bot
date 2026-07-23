import sys
from datetime import datetime, timezone

sys.path.insert(0, "/root/turbobaby-manager-bot")
from bridge_client import BridgeClient
from cclog import _insert_under_vrezka

utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

entry = (
    f"DONE {utc} UTC (headless, задача «проверь X»): read-only проверка систем. "
    "Сервисы splinter/orchestrator-daemon/wa-webhook — все active; Bridge ping ok v1.0.0; splinter.log чист (только штатные job'ы). "
    "НАЙДЕНО: 16.07 21:49–21:51 UTC OOM-kill orchestrator-daemon (systemd restart counter=2, память peak 1.6G+swap 1.7G) — "
    "погиб во время шага 2/6 родителя 185 (id 187, exit=-9); selfheal-думатель КОРРЕКТНО дал halt (SIGKILL не чинится переформулировкой), "
    "шаги 3–6 пропущены, сводка родителя ушла задачей 192; демон перезапущен 21:51:14, mem_gate on (min=700MB). "
    "Сейчас в работе id=193 (класс «тест-фикстуры утекают в живую очередь», старт 23:36, dev-таймаут 45м). "
    "Память сейчас: 1.4/1.9GB used, swap 278MB/2GB, available ~457MB — НИЖЕ порога mem_gate 700MB, новые задачи могут придерживаться до освобождения. "
    "NB: сама задача «проверь X» без конкретики — похожа на тот же класс утёкших фикстур, что разбирает 193; выполнена как общий чек по протоколу «ПРОВЕРЬ». "
    "Хвосты: шаги 2–6 родителя 185 (fail-open deny) не сделаны — ждут перепостановки после 193; следить за памятью демона."
)

pulse = (
    f"{utc} | 🟢 | проверь X: сервисы active, Bridge ok; OOM демона 21:49 разобран — halt 185 корректный, id=193 в работе | "
    "ничего не жду | детали→cc_log запись 17.07 «проверь X»"
)

c = BridgeClient()
r = c._call("read_doc", name="cc_log")
if not r.get("ok"):
    print("READ FAIL — не пишу:", r)
    sys.exit(1)
new = _insert_under_vrezka(r.get("text", ""), entry)
w = c.write_doc(text=new, name="cc_log")
print("cc_log:", "OK" if w.get("ok") else w)
wp = c.write_doc(text=pulse, name="pulse")
print("pulse:", "OK" if wp.get("ok") else wp)
