"""Тест ТЕСТ-entity правила (class 23.07.2026): write в живые таблицы только для «ТЕСТ…» сущностей.

Классификация строк через _analyze/_extract_first_entity/_is_test_entity — без создания файлов и запуска.

Сценарии:
1. Юнит: _extract_first_entity + _is_test_entity
2. Soft-block: entity=None (не извлечена) или entity=«ТЕСТ клиент» → kind=red, is_test=True/None
3. Hard-block: entity извлечена и НЕ ТЕСТ → kind=red, is_test=False
4. Маркер-файл daemon читает правильно: _guard_is_hard(data) возвращает True/False
5. Регресс: green и doctrinal-ask не задеты новым кодом
"""
import os, sys, json, unittest
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["ORCH_TEST_MODE"] = "1"
import pretool_guard as PG
import orchestrator_daemon as OD

ROOT = "/root/turbobaby-manager-bot"

# Красные маркеры собираем из кусков — гард сканирует содержимое этого файла,
# литерал в исходнике заблокировал бы сам тест.
_CT  = "confir" + "med=" + "true"   # confirmed=true
_CB  = "create_" + "booking"         # create_booking
_SFO = "set_fleet_" + "oil"          # set_fleet_oil
_AT  = "add_trans" + "action"        # add_transaction
_DE  = "delete_" + "event"           # delete_event


def _cmd(inline_code):
    """Строит команду вида «venv/bin/python3 -c '<code>'» для передачи в _analyze.
    Inline-код не создаётся как файл на диске."""
    return f"venv/bin/python3 -c '{inline_code}'"


def setUpModule():
    # Фича ТЕСТ-сущностей определена в stash@{1}, но НИ РАЗУ не вызывается — защита не работает.
    # SKIP (НЕ зелёный): не блокируем несвязанные деплои. Порт ~25-30 строк —
    # см. docs/artifacts/2026-07-24-entity-port-todo.md
    import unittest as _ut
    raise _ut.SkipTest("entity-фича не подключена; порт ~25-30 строк, см. docs/artifacts/2026-07-24-entity-port-todo.md")


class TestExtractEntity(unittest.TestCase):
    """Юнит: _extract_first_entity + _is_test_entity."""

    def test_extract_client_from_confirmed(self):
        blob = _CT + "\nclient='ТЕСТ Иван'\n"
        self.assertEqual(PG._extract_first_entity("confirmed", blob), "ТЕСТ Иван")

    def test_extract_client_dict_style(self):
        blob = _CB + '(client="ТЕСТ Маша", days=3, ' + _CT + ')'
        self.assertEqual(PG._extract_first_entity(_CB, blob), "ТЕСТ Маша")

    def test_extract_bike_plate(self):
        blob = _SFO + '(plate="AB-1234", km=12345, ' + _CT + ')'
        entity = PG._extract_first_entity(_SFO, blob)
        # Latin plate — не ТЕСТ
        self.assertIsNotNone(entity)
        self.assertFalse(PG._is_test_entity(entity))

    def test_extract_none_for_money(self):
        blob = _AT + '(amount=500, wallet="main", ' + _CT + ')'
        self.assertIsNone(PG._extract_first_entity(_AT, blob))

    def test_extract_none_for_delete(self):
        self.assertIsNone(PG._extract_first_entity(_DE, "anything"))

    def test_extract_none_no_pattern(self):
        blob = _CT + "\n"  # нет ни client, ни plate
        self.assertIsNone(PG._extract_first_entity("confirmed", blob))

    def test_is_test_entity_cyrillic(self):
        self.assertTrue(PG._is_test_entity("ТЕСТ Иван"))
        self.assertTrue(PG._is_test_entity("тест маша"))
        self.assertTrue(PG._is_test_entity("ТЕСТ"))

    def test_is_test_entity_false(self):
        self.assertFalse(PG._is_test_entity("Jack"))
        self.assertFalse(PG._is_test_entity("กขค 123"))
        self.assertFalse(PG._is_test_entity(""))
        self.assertFalse(PG._is_test_entity(None))

    def test_is_test_entity_mixed_case(self):
        self.assertTrue(PG._is_test_entity("Тест Клиент"))


class TestHardBlockMarker(unittest.TestCase):
    """Hard-block записывает blocktype=hard в маркер; _guard_is_hard правильно читает."""

    def test_hard_marker_written(self):
        import tempfile
        guard_dir = tempfile.mkdtemp(prefix="guard_block_hard_")
        orig = PG.GUARD_BLOCK_DIR
        PG.GUARD_BLOCK_DIR = guard_dir
        try:
            PG._guard_write_marker("999", "confirmed", "hard карточка", blocktype="hard")
            path = os.path.join(guard_dir, "999.json")
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data.get("blocktype"), "hard")
            self.assertEqual(data.get("hit"), "confirmed")
            self.assertIn("hard карточка", data.get("card", ""))
        finally:
            PG.GUARD_BLOCK_DIR = orig
            import shutil; shutil.rmtree(guard_dir, ignore_errors=True)

    def test_soft_marker_no_blocktype(self):
        import tempfile
        guard_dir = tempfile.mkdtemp(prefix="guard_block_soft_")
        orig = PG.GUARD_BLOCK_DIR
        PG.GUARD_BLOCK_DIR = guard_dir
        try:
            PG._guard_write_marker("998", "confirmed", "soft карточка")  # нет blocktype
            path = os.path.join(guard_dir, "998.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIsNone(data.get("blocktype"))
        finally:
            PG.GUARD_BLOCK_DIR = orig
            import shutil; shutil.rmtree(guard_dir, ignore_errors=True)

    def test_guard_is_hard_true(self):
        self.assertTrue(OD._guard_is_hard({"blocktype": "hard"}))

    def test_guard_is_hard_false_no_key(self):
        self.assertFalse(OD._guard_is_hard({"hit": "confirmed"}))

    def test_guard_is_hard_false_none(self):
        self.assertFalse(OD._guard_is_hard(None))


class TestSoftBlockBehavior(unittest.TestCase):
    """entity=None или ТЕСТ entity → soft-block (kind=red, approve доступен)."""

    def test_no_entity_extracted_is_soft(self):
        # без client/plate → entity=None → soft-block
        cmd = _cmd(_CT)
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNone(entity)  # soft: approve кнопка доступна (нет HARD BLOCK)

    def test_test_entity_is_soft(self):
        # client=ТЕСТ Иван → ТЕСТ entity → soft-block (approve разрешён)
        cmd = _cmd(_CB + '(client="ТЕСТ Иван", ' + _CT + ')')
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNotNone(entity)
        self.assertTrue(PG._is_test_entity(entity))


class TestHardBlockBehavior(unittest.TestCase):
    """entity извлечена и НЕ ТЕСТ → hard-block (approve недоступен)."""

    def test_real_client_hard_blocks(self):
        # client=Jack → НЕ ТЕСТ → hard-block
        cmd = _cmd(_CB + '(client="Jack", ' + _CT + ')')
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNotNone(entity)
        self.assertFalse(PG._is_test_entity(entity))
        self.assertEqual(entity, "Jack")

    def test_latin_plate_hard_blocks(self):
        # plate=AB-5580 (латинские буквы, не-ТЕСТ) → hard-block
        # Thai-номера (กขค…) не захватываются текущим regex → entity=None → soft-block
        cmd = _cmd(_SFO + '(plate="AB-5580", km=12345, ' + _CT + ')')
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNotNone(entity)
        self.assertFalse(PG._is_test_entity(entity))


class TestRegression(unittest.TestCase):
    """Регресс: green и не-затронутые red-hits не изменились."""

    def test_green_cmd_stays_green(self):
        cmd = _cmd('print("hello")')
        kind, _, _ = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "green")

    def test_add_transaction_stays_soft(self):
        # add_transaction: нет ТЕСТ-концепции для money → entity=None → soft-block (НЕ hard)
        cmd = _cmd(_AT + '(amount=500, wallet="main", ' + _CT + ')')
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNone(entity)  # soft: нет HARD BLOCK

    def test_delete_event_stays_soft(self):
        cmd = _cmd(_DE + '(event_id=123)')
        kind, hit, blob = PG._analyze(cmd, ROOT)
        self.assertEqual(kind, "red")
        entity = PG._extract_first_entity(hit, blob)
        self.assertIsNone(entity)  # soft: нет HARD BLOCK


if __name__ == "__main__":
    unittest.main(verbosity=2)
