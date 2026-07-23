import os, sys
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
sys.argv = [
    "cclog.py",
    "задача: тест 5 — связь подтверждена, задача выполнена.",
    "--pulse",
    "2026-07-17 | 🟢 | тест 5 выполнен | ничего не жду | детали→cc_log",
]
exec(open("/root/turbobaby-manager-bot/cclog.py").read())
