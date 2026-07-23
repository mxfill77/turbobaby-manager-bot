"""One-shot wrapper: run cclog.main() with BRIDGE_ALLOW_NETWORK=1 (ORCH_TEST_MODE blocks network)."""
import os, sys

os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
os.environ.pop("ORCH_TEST_MODE", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cclog

args = [
    "задача «тест 1» — тест пайплайна оркестратора, выполнено успешно",
    "--pulse",
    "2026-07-17 | \U0001f7e2 | задача тест 1 выполнена | ничего не жду | детали→cc_log тест 1",
]

sys.exit(cclog.main(args))
