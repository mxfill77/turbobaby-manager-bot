# одиночный прогон порт-модуля шага 6/7 (Linux: REPO демона = D:\ → пре-инит логгера до импорта)
import logging
import sys
import unittest

logging.basicConfig(level=logging.CRITICAL)
sys.path.insert(0, "/root/_pcport_userbot_185")

unittest.main(module="test_pc_local_dec", verbosity=2, argv=["runner"])
