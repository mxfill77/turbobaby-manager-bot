# Постановка read-only верификационной задачи после включения куратора (CURATOR=1, 12.07.2026).
# Задача исполнится СВЕЖИМ демоном (после отложенного рестарта) и подтвердит в cc_log,
# что флаг живёт в env живого процесса (curator=1 в старт-баннере). Ничего не пишет в таблицы.
from bridge_client import BridgeClient

TEXT = (
    "Read-only верификация включения куратора после рестарта orchestrator-daemon "
    "(12.07.2026, CURATOR=1). Ничего не менять, только проверить и залогировать: "
    "(1) systemctl is-active orchestrator-daemon — должен быть active; "
    "(2) в /root/turbobaby-manager-bot/orchestrator_daemon.log найти ПОСЛЕДНЮЮ строку "
    "'=== ДЕМОН СТАРТ' — в ней должно быть curator=1 (а также selfheal=1, plan_adapt=1 — "
    "остальные ветки не тронуты); это и есть доказательство: баннер печатается живым процессом "
    "из его os.environ после load_dotenv; "
    "(3) после этой строки в логе нет Traceback/ошибок старта; "
    "(4) итог одной строкой DONE в cc_log через write_doc name=cc_log (под врезкой) + пульс "
    "write_doc name=pulse ТОЙ ЖЕ операцией: «куратор функционально подтверждён: демон active, "
    "curator=1 в баннере живого процесса, selfheal/plan_adapt не тронуты, старт чистый» "
    "(или честный BLOCKED с фактами, если что-то не так)."
)

r = BridgeClient(timeout=90).enqueue_task("Filipp-328", TEXT)
print(r)
