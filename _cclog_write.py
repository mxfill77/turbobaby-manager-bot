import os, sys
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
sys.argv = [
    "cclog.py",
    "тест 1 — headless задача принята и выполнена (read-only проверка контура 328)",
    "--pulse",
    "2026-07-17 02:35 UTC | 🟢 | тест 1 выполнен | ничего не жду | детали→cc_log «тест 1»"
]
exec(open("/root/turbobaby-manager-bot/cclog.py").read())
