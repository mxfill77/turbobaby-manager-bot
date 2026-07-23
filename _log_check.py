import os, sys
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
sys.argv = [
    "cclog.py",
    "DONE 2026-07-17 02:26 UTC (headless read-only): почитал логи. splinter active 17h, ошибок нет. orchestrator-daemon active 1h, 40 tasks, RAM 905M/peak 1006M (близко к OOM). Инциденты: Bad Gateway 21:32 UTC 16.07 (кратко, 3 ошибки), Bridge timeout 01:28 UTC 17.07 (get_pending, backoff 2/3). devbot.banner «not modified» — штатные. Всё работает.",
    "--pulse",
    "2026-07-17 02:26 | 🟢 | логи прочитаны, сервисы OK | ничего не жду | детали→cc_log «почитай логи 17.07»",
]
import cclog  # noqa: runs main
