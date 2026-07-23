# -*- coding: utf-8 -*-
"""Раннер сьюта ПК-порта (шаги родителя 185): chdir в _pcport185 (лог-путь модуля относительный,
Windows-стиль) и unittest test_pc_orchestrator. Опц. аргументы = конкретные тесты."""
import os
import sys
import unittest

os.environ.setdefault("PRETOOL_NOPUSH", "1")
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pcport185")
os.chdir(BASE)
sys.path.insert(0, BASE)

names = sys.argv[1:] or ["test_pc_orchestrator"]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
res = unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(0 if res.wasSuccessful() else 1)
