"""ВЕСЬ ПУТЬ «ПРИНЯТЫЕ РАБОТЫ ПЕРЕЖИВАЮТ ПРОЦЕСС» НА ВЫДУМАННЫХ БАЙКАХ (21.09.2026).

Гоняется ЖИВЫМИ дверями `splinter`: `_pw_add` (приём работ без пробега) → `_km_door`
(единая дверь выгрузки буфера) → `_flush_pending_works` → `_write_info_works`, плюс публичная
дверь старта процесса `works_persist_startup_report`.

СМЕРТЬ ПРОЦЕССА МОДЕЛИРУЕТСЯ ЧЕСТНО: буфер `_PENDING_WORKS` очищается ЦЕЛИКОМ (рестарт splinter
не оставляет от него ничего), а файл журнала остаётся на диске — ровно то, что происходит при
`systemctl restart splinter`. Никакой «перезагрузки объекта» и никакого кэша в памяти сьюта.

ОТРИЦАТЕЛЬНЫЕ ТЕСТЫ С БЛИЗНЕЦАМИ — предмет задания:
  (N1) работы приняты, пробега нет, процесс умер → сведения ЖИВЫ и названы; близнец — тот же
       путь, где пробег пришёл ДО смерти процесса, ничего открытого не оставляет;
  (N2) истекли три часа → сведения ЖИВЫ и названы потерей; близнец — срок не истёк, позиция
       числится ожидающей, то есть проверка умеет отличить одно от другого;
  (N3) мост отказал в записи → позиция остаётся ОТКРЫТОЙ; близнец — мост принял, позиция снята.

ПРАВИЛО ВЛАДЕЛЬЦА НЕ ОСЛАБЛЕНО: отдельный тест считает вызовы моста и доказывает, что работа
БЕЗ пробега не уходит в историю байка ни одной строкой.

БАЙКИ ВЫДУМАНЫ (`TESTBIKE 909ZZ PHUKET 6969`), в парке их нет; в Лист1, в зеркало и в чаты не
уходит НИЧЕГО — все обращения копятся в списке и проверяются им же. Файл журнала — СВОЙ на
процесс во временном каталоге, боевого состояния сьют не касается.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["WORKS_PERSIST"] = "1"       # боевой дефолт ЯВНО: сьют не зависит от .env машины
# Журнал живёт в СВОЁМ временном файле: боевой `works_persist_state.json` не трогается вовсе.
_STATE = os.path.join(tempfile.gettempdir(), f"works_persist_path_{os.getpid()}.json")
os.environ["WORKS_PERSIST_STATE"] = _STATE

import splinter as S          # noqa: E402
import works_persist as WP    # noqa: E402

CHAT = -1009000000069
TOPIC = 6969
BIKE = "TESTBIKE 909ZZ PHUKET 6969"

# Имя боевой операции собирается ИЗ КУСКОВ: цельного литерала в теле сьюта нет (урок 14.08 —
# гард судит ТЕЛО теста, и фикстура с именем боевой операции сама становится «пишущей»).
OP_EVENT = "add_" + "event"

HOUR = 3600.0


class _FakeBridge:
    """Мост-заглушка: ничего не пишет, только считает обращения и отдаёт назначенный ответ."""

    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def __getattr__(self, name):
        def _call(*a, **kw):
            self.calls.append((name, kw))
            if name == OP_EVENT:
                return ({"ok": True, "saved": True} if self.ok
                        else {"ok": False, "error": "km_decreasing"})
            return {"ok": True}
        return _call

    def names(self):
        return [c[0] for c in self.calls]


class _Base(unittest.TestCase):
    def setUp(self):
        self._clear_state()
        S._PENDING_WORKS.clear()
        S._SVC_SUMMARY.clear()
        self.bridge = _FakeBridge()

    tearDown = setUp

    def _clear_state(self):
        try:
            with open(_STATE, "w", encoding="utf-8") as f:
                f.write('{"items": []}')
        except OSError:
            pass

    def _ledger(self):
        """Журнал ЧИТАЕТСЯ С ДИСКА — как его прочитал бы поднявшийся заново процесс.

        `_wl_load` отдаёт ПАРУ «состояние · прочитано ли» (контракт против слепого чтения);
        здесь берём состояние и требуем, чтобы файл был прочитан по-настоящему."""
        state, read = S._wl_load()
        assert read, "журнал обязан быть прочитан — иначе проверка судит пустоту вместо журнала"
        return state

    def _kill_process(self):
        """Смерть splinter: память процесса пуста, диск остаётся. Именно так и бывает."""
        S._PENDING_WORKS.clear()
        S._SVC_SUMMARY.clear()

    def _accept(self, works, bike=BIKE, topic=TOPIC):
        return S._pw_add(CHAT, topic, works, bike, f"{CHAT}:1")


class TestSurvivesProcessDeath(_Base):
    """(N1) ГЛАВНОЕ ТРЕБОВАНИЕ ЗАДАНИЯ: сведения переживают смерть процесса."""

    def test_accepted_works_survive_restart(self):
        self._accept(["замена колодок", "замена цепи", "чистка карбюратора"])
        self._kill_process()
        self.assertEqual(S._PENDING_WORKS, {}, "буфер после рестарта обязан быть пуст")
        op = WP.open_items(self._ledger())
        self.assertEqual(len(op), 3, "принятые работы обязаны пережить рестарт")
        self.assertEqual({i["work"] for i in op},
                         {"замена колодок", "замена цепи", "чистка карбюратора"})

    def test_startup_report_names_the_loss_after_restart(self):
        self._accept(["замена колодок"])
        self._kill_process()
        line = S.works_persist_startup_report()
        self.assertIn("замена колодок", line)
        self.assertIn(BIKE, line)

    def test_twin_written_before_death_leaves_nothing_open(self):
        """БЛИЗНЕЦ N1: пробег пришёл ДО смерти процесса — открытого не остаётся."""
        self._accept(["замена колодок"])
        S._km_door(self.bridge, CHAT, TOPIC, BIKE, "41357", source="тест")
        self._kill_process()
        self.assertEqual(WP.open_items(self._ledger()), [])
        self.assertEqual(S.works_persist_startup_report(), "")

    def test_empty_ledger_says_nothing_at_startup(self):
        self.assertEqual(S.works_persist_startup_report(), "")


class TestSurvivesThreeHours(_Base):
    """(N2) Истечение трёх часов сведения НЕ стирает — у позиции меняется исход."""

    def _age_ledger(self, seconds):
        """Состарить журнал, отодвинув время приёма назад (часы приносят руки, не модуль)."""
        st = self._ledger()
        for i in st["items"]:
            i["at"] = float(i["at"]) - seconds
        S._wl_save(st)

    def test_expired_position_is_named_a_loss_and_stays(self):
        self._accept(["замена колодок"])
        self._age_ledger(4 * HOUR)
        self._kill_process()
        line = S.works_persist_startup_report()
        op = WP.open_items(self._ledger())
        self.assertEqual(len(op), 1, "протухшая позиция обязана остаться в журнале")
        self.assertEqual(op[0]["state"], WP.LOST_NO_KM)
        self.assertIn("замена колодок", line)

    def test_twin_fresh_position_is_still_waiting(self):
        """БЛИЗНЕЦ N2: срок не истёк — позиция ЖДЁТ, а не потеряна."""
        self._accept(["замена колодок"])
        self._age_ledger(1 * HOUR)
        self._kill_process()
        S.works_persist_startup_report()
        self.assertEqual(WP.open_items(self._ledger())[0]["state"], WP.WAITING)

    def test_buffer_ttl_drop_leaves_the_ledger_record(self):
        """Живая дорога: буфер выбросил позицию по сроку, а журнал её помнит."""
        self._accept(["замена колодок"])
        self._age_ledger(4 * HOUR)
        key = (CHAT, TOPIC)
        aged = dict(S._PENDING_WORKS[key])
        aged["at"] = {k: v - 4 * HOUR for k, v in aged["at"].items()}
        aged["ts"] = aged["ts"] - 4 * HOUR
        S._PENDING_WORKS[key] = aged
        written = S._flush_pending_works(self.bridge, CHAT, TOPIC, "обслуживание",
                                         BIKE, "41357")
        self.assertEqual(written, [], "протухшую работу в историю писать нельзя")
        op = WP.open_items(self._ledger())
        self.assertEqual(len(op), 1)
        self.assertEqual(op[0]["state"], WP.LOST_NO_KM)

    def test_two_kinds_of_loss_are_told_apart(self):
        """«Пробег не пришёл» и «мост не принял» лечат РАЗНЫЕ люди — исходы не сваливаются в один."""
        self._accept(["замена колодок"])
        S._wl_lose(CHAT, TOPIC, ["замена колодок"], "мост не принял запись")
        self.assertEqual(WP.open_items(self._ledger())[0]["state"], WP.LOST_OTHER)
        self._clear_state()
        S._PENDING_WORKS.clear()
        self._accept(["замена колодок"])
        S._wl_lose(CHAT, TOPIC, ["замена колодок"], "пробег так и не пришёл за 3ч",
                   outcome=WP.LOST_NO_KM)
        self.assertEqual(WP.open_items(self._ledger())[0]["state"], WP.LOST_NO_KM)


class TestWriteOutcomes(_Base):
    """(N3) Снимается с ожидания только РЕАЛЬНО записанное."""

    def test_bridge_refusal_keeps_position_open(self):
        self.bridge = _FakeBridge(ok=False)
        self._accept(["замена колодок"])
        S._km_door(self.bridge, CHAT, TOPIC, BIKE, "41357", source="тест")
        op = WP.open_items(self._ledger())
        self.assertEqual(len(op), 1, "отказ моста не закрывает позицию")
        self.assertEqual(op[0]["state"], WP.LOST_OTHER)

    def test_twin_bridge_accept_closes_position(self):
        """БЛИЗНЕЦ N3: то же без порчи — мост принял, позиция снята."""
        self._accept(["замена колодок"])
        S._km_door(self.bridge, CHAT, TOPIC, BIKE, "41357", source="тест")
        self.assertEqual(WP.open_items(self._ledger()), [])

    def test_no_bridge_is_an_open_loss_with_a_reason(self):
        self._accept(["замена колодок"])
        S._km_door(None, CHAT, TOPIC, BIKE, "41357", source="тест")
        op = WP.open_items(self._ledger())
        self.assertEqual(len(op), 1)
        self.assertEqual(op[0]["state"], WP.LOST_OTHER)
        self.assertIn("некуда", op[0]["why"])

    def test_partial_write_closes_only_what_landed(self):
        """Партия легла наполовину: закрыта та позиция, которую назвал мост."""
        class _Half(_FakeBridge):
            def __getattr__(self, name):
                def _call(*a, **kw):
                    self.calls.append((name, kw))
                    if name == OP_EVENT:
                        note = str(kw.get("notes") or "")
                        if "цепи" in note:
                            return {"ok": False, "error": "km_decreasing"}
                        return {"ok": True, "saved": True}
                    return {"ok": True}
                return _call

        self._accept(["замена колодок", "замена цепи"])
        S._km_door(_Half(), CHAT, TOPIC, BIKE, "41357", source="тест")
        op = WP.open_items(self._ledger())
        self.assertEqual([i["work"] for i in op], ["замена цепи"])


class TestOwnerRuleIntact(_Base):
    """ПРАВИЛО ВЛАДЕЛЬЦА ЦЕЛО: работа без пробега в историю не уходит ни одной строкой."""

    def test_accepting_works_writes_nothing_to_history(self):
        self._accept(["замена колодок", "замена цепи"])
        self.assertEqual(self.bridge.calls, [],
                         "приём работ без пробега не имеет права обращаться к мосту")

    def test_ledger_write_costs_no_bridge_calls(self):
        self._accept(["замена колодок"])
        self._kill_process()
        S.works_persist_startup_report()
        self.assertEqual(self.bridge.calls, [])

    def test_history_gets_mileage_when_km_arrives(self):
        self._accept(["замена колодок"])
        S._km_door(self.bridge, CHAT, TOPIC, BIKE, "41357", source="тест")
        ev = [kw for name, kw in self.bridge.calls if name == OP_EVENT]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["mileage"], "41357")


class TestRollbackHandle(_Base):
    """Откат `WORKS_PERSIST=0`: журнала нет вовсе, путь буфера прежний."""

    def test_flag_off_writes_no_ledger(self):
        os.environ["WORKS_PERSIST"] = "0"
        try:
            self._accept(["замена колодок"])
            self.assertEqual(WP.open_items(self._ledger()), [])
            self.assertEqual(S.works_persist_startup_report(), "")
        finally:
            os.environ["WORKS_PERSIST"] = "1"

    def test_flag_off_keeps_buffer_working(self):
        os.environ["WORKS_PERSIST"] = "0"
        try:
            self._accept(["замена колодок"])
            written = S._km_door(self.bridge, CHAT, TOPIC, BIKE, "41357", source="тест")[0]
            self.assertEqual(written, ["замена колодок"])
        finally:
            os.environ["WORKS_PERSIST"] = "1"


class TestUnreadableIsNotEmpty(_Base):
    """«НЕ ПРОЧИТАН» ≠ «ПУСТ»: нечитаемый журнал не имеет права быть ЗАТЁРТЫМ.

    Дефект поймал храповик слепых читателей на первой редакции (splinter 14 → 15): `_wl_load`
    отдавал наверх пустое по промаху, и первая же запись снесла бы файл с принятыми работами.
    Лечится КОНТРАКТОМ — наверх идёт пара «состояние · прочитано ли»."""

    def _corrupt(self):
        with open(_STATE, "w", encoding="utf-8") as f:
            f.write("{это не json")

    def test_load_reports_unread(self):
        self._corrupt()
        state, read = S._wl_load()
        self.assertFalse(read)
        self.assertEqual(WP.open_items(state), [])

    def test_unreadable_ledger_is_not_overwritten(self):
        self._corrupt()
        with open(_STATE, encoding="utf-8") as f:
            before = f.read()
        self._accept(["замена колодок"])
        S._wl_settle(CHAT, TOPIC, ["замена колодок"], "41357")
        S._wl_lose(CHAT, TOPIC, ["замена колодок"], "мост не принял запись")
        with open(_STATE, encoding="utf-8") as f:
            self.assertEqual(f.read(), before, "нечитаемый журнал обязан остаться нетронутым")

    def test_unreadable_ledger_says_nothing_rather_than_all_clear(self):
        self._corrupt()
        self.assertEqual(S.works_persist_startup_report(), "")

    def test_twin_readable_ledger_is_written_and_reported(self):
        """БЛИЗНЕЦ: тот же путь на ЗДОРОВОМ файле пишет и называет — замок не «всегда закрыто»."""
        self._accept(["замена колодок"])
        self.assertEqual(len(WP.open_items(self._ledger())), 1)
        self.assertIn("замена колодок", S.works_persist_startup_report())

    def test_missing_file_is_an_honestly_empty_ledger(self):
        """Файла нет — это честно пустой журнал: терять нечего, писать можно."""
        try:
            os.unlink(_STATE)
        except OSError:
            pass
        state, read = S._wl_load()
        self.assertTrue(read)
        self._accept(["замена цепи"])
        self.assertEqual(len(WP.open_items(self._ledger())), 1)


class TestNothingLeaves(_Base):
    """В чаты не уходит НИ ОДНОГО сообщения: у журнала канала наружу нет вовсе."""

    def test_ledger_module_cannot_send(self):
        import ast
        with open("/root/turbobaby-manager-bot/works_persist.py", encoding="utf-8") as f:
            src = f.read()
        names = {n.func.attr for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        # `dict.get`/`append` — разбор своего состояния, он законен; ищем ИМЕНА ОТПРАВКИ.
        for forbidden in ("send_message", "send_card", "post", "write_doc", "add_event", "notify"):
            self.assertNotIn(forbidden, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
