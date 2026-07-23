"""Враппер cclog для headless-режима: снимает ORCH_TEST_MODE-запрет сети."""
import os, sys
os.environ["BRIDGE_ALLOW_NETWORK"] = "1"
# Добавляем репо в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cclog
sys.exit(cclog.main(sys.argv[1:]))
