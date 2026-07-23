"""Wrapper: set BRIDGE_ALLOW_NETWORK and call cclog.main for headless test-1 entry."""
import os
import sys

os.environ["BRIDGE_ALLOW_NETWORK"] = "1"

# Ensure working directory is repo root for .env loading
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Now import and call cclog
sys.argv = [
    "cclog.py",
    "тест 1 — headless-контур отвечает, задача исполнена штатно",
    "--pulse",
    "2026-07-17 | 🟢 | тест 1 выполнен, headless работает | ничего не жду | детали→cc_log запись тест-1",
]

import cclog
sys.exit(cclog.main(sys.argv[1:]))
