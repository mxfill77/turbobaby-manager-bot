"""ЖУРНАЛ ПРИНЯТЫХ РАБОТ — РЕШЕНИЕ (works_persist.py, 21.09.2026).

Предмет: сведения о ПРИНЯТЫХ работах переживают смерть процесса и истечение трёх часов, при этом
правило владельца «нет пробега — работа НЕ записывается» не ослаблено ни одной веткой.

У каждого отрицательного случая есть близнец «то же без порчи», иначе замок мог бы оказаться
«всегда закрыто». Часов у модуля нет: «сейчас» во всех проверках подставляется числом.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import works_persist as wp

T0 = 1_700_000_000.0
HOUR = 3600.0


def _accept(state, works, *, chat=-100, topic=7, bike="ТЕСТ BIKE 0001", now=T0):
    return wp.accept(state, chat_id=chat, topic_id=topic, bike=bike,
                     pairs=[(w, w.strip().lower()) for w in works], now=now)


class TestAccept(unittest.TestCase):
    def test_accepted_work_lands_in_ledger(self):
        st, added = _accept(wp.empty(), ["замена колодок"])
        self.assertEqual(added, 1)
        self.assertEqual(len(wp.open_items(st)), 1)
        self.assertEqual(wp.open_items(st)[0]["state"], wp.WAITING)

    def test_position_carries_bike_topic_and_time(self):
        st, _ = _accept(wp.empty(), ["замена цепи"], bike="ТЕСТ BIKE 0002", topic=42, now=T0)
        it = wp.open_items(st)[0]
        self.assertEqual(it["bike"], "ТЕСТ BIKE 0002")
        self.assertEqual(it["topic"], 42)
        self.assertEqual(it["at"], T0)
        self.assertEqual(it["work"], "замена цепи")

    def test_batch_of_three_gives_three_positions(self):
        """Единица журнала — ПОЗИЦИЯ: живой случай 21.09 принял три работы одним сообщением."""
        st, added = _accept(wp.empty(), ["колодки", "цепь", "шина"])
        self.assertEqual(added, 3)
        self.assertEqual(len(wp.open_items(st)), 3)

    def test_same_words_while_open_do_not_duplicate(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, added = _accept(st, ["колодки"], now=T0 + 60)
        self.assertEqual(added, 0)
        self.assertEqual(len(wp.open_items(st)), 1)

    def test_same_words_after_close_are_allowed_again(self):
        """Близнец предыдущего: ту же работу законно делают второй раз на другом пробеге."""
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"], km="41000", now=T0 + 10)
        st, added = _accept(st, ["колодки"], now=T0 + 20)
        self.assertEqual(added, 1)

    def test_other_topic_is_a_different_position(self):
        st, _ = _accept(wp.empty(), ["колодки"], topic=7)
        st, added = _accept(st, ["колодки"], topic=8)
        self.assertEqual(added, 1)
        self.assertEqual(len(wp.open_items(st)), 2)

    def test_empty_slot_is_not_a_position(self):
        st, added = wp.accept(wp.empty(), chat_id=-100, topic_id=7, bike="ТЕСТ",
                              pairs=[("колодки", "")], now=T0)
        self.assertEqual(added, 0)

    def test_no_works_changes_nothing(self):
        st, added = wp.accept(wp.empty(), chat_id=-100, topic_id=7, bike="ТЕСТ",
                              pairs=[], now=T0)
        self.assertEqual(added, 0)
        self.assertEqual(wp.open_items(st), [])


class TestSurvivesThreeHours(unittest.TestCase):
    """ГЛАВНОЕ ТРЕБОВАНИЕ ЗАДАНИЯ: истечение трёх часов сведения НЕ стирает."""

    def test_expired_position_stays_in_ledger(self):
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        st, hit = wp.expire(st, now=T0 + 4 * HOUR, ttl=3 * HOUR)
        self.assertEqual(hit, 1)
        op = wp.open_items(st)
        self.assertEqual(len(op), 1, "протухшая позиция обязана ОСТАТЬСЯ в журнале")
        self.assertEqual(op[0]["state"], wp.LOST_NO_KM)
        self.assertIn("пробег", op[0]["why"])

    def test_fresh_position_is_not_expired(self):
        """Близнец: то же без истечения срока — позиция всё ещё просто ждёт."""
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        st, hit = wp.expire(st, now=T0 + 2 * HOUR, ttl=3 * HOUR)
        self.assertEqual(hit, 0)
        self.assertEqual(wp.open_items(st)[0]["state"], wp.WAITING)

    def test_expire_is_idempotent(self):
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        st, _ = wp.expire(st, now=T0 + 4 * HOUR, ttl=3 * HOUR)
        st, hit = wp.expire(st, now=T0 + 5 * HOUR, ttl=3 * HOUR)
        self.assertEqual(hit, 0, "второй проход не обязан пересчитывать уже потерянное")
        self.assertEqual(len(wp.open_items(st)), 1)

    def test_ttl_zero_does_not_judge(self):
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        st, hit = wp.expire(st, now=T0 + 100 * HOUR, ttl=0)
        self.assertEqual(hit, 0)
        self.assertEqual(wp.open_items(st)[0]["state"], wp.WAITING)

    def test_age_is_named_in_report(self):
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        line = wp.report(st, now=T0 + 5 * HOUR)
        self.assertIn("5.0 ч", line, "время без возраста читается как «только что»")


class TestSettleLock(unittest.TestCase):
    """ЗАМОК ПРОТИВ ЛОЖНОГО ЗЕЛЁНОГО: снято ровно то, что названо записанным."""

    def test_written_position_closes(self):
        st, _ = _accept(wp.empty(), ["колодки", "цепь"])
        st, done = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"],
                             km="41000", now=T0 + 60)
        self.assertEqual(done, 1)
        left = [i["work"] for i in wp.open_items(st)]
        self.assertEqual(left, ["цепь"])

    def test_unnamed_position_stays_open(self):
        """Мост промолчал об одной из двух — она остаётся НАШЕЙ."""
        st, _ = _accept(wp.empty(), ["колодки", "цепь"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"], km="41000", now=T0)
        self.assertEqual(wp.counts(st)[wp.WAITING], 1)

    def test_empty_written_list_closes_nothing(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, done = wp.settle(st, chat_id=-100, topic_id=7, slots=[], km="41000", now=T0)
        self.assertEqual(done, 0)
        self.assertEqual(wp.counts(st)[wp.WAITING], 1)

    def test_settle_does_not_reach_other_topic(self):
        st, _ = _accept(wp.empty(), ["колодки"], topic=7)
        st, _ = _accept(st, ["колодки"], topic=8)
        st, done = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"],
                             km="41000", now=T0)
        self.assertEqual(done, 1)
        self.assertEqual(wp.counts(st)[wp.WAITING], 1)

    def test_late_km_closes_an_already_lost_position(self):
        """Исход следует за МИРОМ: пробег пришёл после срока, работа легла — позиция закрыта."""
        st, _ = _accept(wp.empty(), ["колодки"], now=T0)
        st, _ = wp.expire(st, now=T0 + 4 * HOUR, ttl=3 * HOUR)
        st, done = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"],
                             km="41357", now=T0 + 5 * HOUR)
        self.assertEqual(done, 1)
        self.assertEqual(wp.open_items(st), [])

    def test_km_is_remembered_on_close(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"],
                          km="41357", now=T0 + 60)
        self.assertEqual(st["items"][0]["km"], "41357")


class TestLose(unittest.TestCase):
    def test_write_failure_is_an_open_loss(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, hit = wp.lose(st, chat_id=-100, topic_id=7, slots=["колодки"],
                          why="мост не принял запись", now=T0 + 60)
        self.assertEqual(hit, 1)
        it = wp.open_items(st)[0]
        self.assertEqual(it["state"], wp.LOST_OTHER)
        self.assertIn("мост", it["why"])

    def test_lost_position_can_still_close_later(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.lose(st, chat_id=-100, topic_id=7, slots=["колодки"],
                        why="писать было некуда", now=T0)
        st, done = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"],
                             km="41357", now=T0 + HOUR)
        self.assertEqual(done, 1)

    def test_closed_position_is_not_reopened_by_lose(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"], km="41000", now=T0)
        st, hit = wp.lose(st, chat_id=-100, topic_id=7, slots=["колодки"],
                          why="поздний отказ", now=T0 + HOUR)
        self.assertEqual(hit, 0)
        self.assertEqual(wp.counts(st)[wp.WRITTEN], 1)


class TestPruneKeepsLosses(unittest.TestCase):
    """ВЛАСТЬ СТРОГО ДОБАВЛЯЮЩАЯ: потолок файла не имеет права съесть открытую потерю."""

    def test_open_losses_are_never_pruned(self):
        st = wp.empty()
        for n in range(50):
            st, _ = _accept(st, [f"работа {n}"], topic=n, now=T0 + n)
        st, _ = wp.expire(st, now=T0 + 100 * HOUR, ttl=3 * HOUR)
        pruned = wp.prune(st, keep=0)
        self.assertEqual(len(wp.open_items(pruned)), 50)

    def test_closed_positions_are_pruned_oldest_first(self):
        st = wp.empty()
        for n in range(10):
            st, _ = _accept(st, [f"работа {n}"], topic=n, now=T0 + n)
            st, _ = wp.settle(st, chat_id=-100, topic_id=n, slots=[f"работа {n}"],
                              km="1", now=T0 + 100 + n)
        pruned = wp.prune(st, keep=3)
        self.assertEqual(wp.counts(pruned)[wp.WRITTEN], 3)
        left = sorted(i["work"] for i in pruned["items"])
        self.assertEqual(left, ["работа 7", "работа 8", "работа 9"])

    def test_prune_below_cap_changes_nothing(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"], km="1", now=T0)
        self.assertEqual(len(wp.prune(st, keep=300)["items"]), 1)

    def test_mixed_ledger_keeps_all_open_and_caps_closed(self):
        st = wp.empty()
        for n in range(5):
            st, _ = _accept(st, [f"открытая {n}"], topic=100 + n, now=T0 + n)
        for n in range(5):
            st, _ = _accept(st, [f"закрытая {n}"], topic=200 + n, now=T0 + n)
            st, _ = wp.settle(st, chat_id=-100, topic_id=200 + n, slots=[f"закрытая {n}"],
                              km="1", now=T0 + 50 + n)
        pruned = wp.prune(st, keep=1)
        self.assertEqual(len(wp.open_items(pruned)), 5)
        self.assertEqual(wp.counts(pruned)[wp.WRITTEN], 1)


class TestReportAndCounts(unittest.TestCase):
    def test_empty_ledger_says_nothing(self):
        self.assertEqual(wp.report(wp.empty(), now=T0), "")

    def test_report_names_bike_and_work(self):
        st, _ = _accept(wp.empty(), ["замена колодок"], bike="ТЕСТ BIKE 0007")
        line = wp.report(st, now=T0 + HOUR)
        self.assertIn("замена колодок", line)
        self.assertIn("ТЕСТ BIKE 0007", line)

    def test_report_counts_waiting_and_lost_apart(self):
        st, _ = _accept(wp.empty(), ["колодки"], topic=7, now=T0)
        st, _ = _accept(st, ["цепь"], topic=8, now=T0 + 10 * HOUR)
        st, _ = wp.expire(st, now=T0 + 10 * HOUR, ttl=3 * HOUR)
        line = wp.report(st, now=T0 + 10 * HOUR)
        self.assertIn("ждут 1", line)
        self.assertIn("потеряны 1", line)

    def test_report_names_the_tail_by_number(self):
        st = wp.empty()
        for n in range(15):
            st, _ = _accept(st, [f"работа {n}"], topic=n, now=T0 + n)
        line = wp.report(st, now=T0 + HOUR, limit=10)
        self.assertIn("и ещё 5", line)

    def test_closed_positions_are_not_in_report(self):
        st, _ = _accept(wp.empty(), ["колодки"])
        st, _ = wp.settle(st, chat_id=-100, topic_id=7, slots=["колодки"], km="1", now=T0)
        self.assertEqual(wp.report(st, now=T0 + HOUR), "")


class TestGarbageIn(unittest.TestCase):
    """Чужой/битый файл не роняет читателя и не выдумывает позиций."""

    def test_not_a_dict(self):
        self.assertEqual(wp.open_items("мусор"), [])
        self.assertEqual(wp.report(None, now=T0), "")

    def test_items_not_a_list(self):
        self.assertEqual(wp.open_items({"items": "нет"}), [])

    def test_non_dict_items_are_skipped(self):
        self.assertEqual(wp.open_items({"items": [1, "два", None]}), [])

    def test_broken_time_does_not_crash_expire(self):
        st = {"items": [{"key": "-100:7", "chat": -100, "topic": 7, "bike": "ТЕСТ",
                         "work": "колодки", "slot": "колодки", "at": "не число",
                         "state": wp.WAITING, "km": "", "why": "", "closed_at": 0.0}]}
        st2, hit = wp.expire(st, now=T0, ttl=3 * HOUR)
        self.assertEqual(hit, 1)
        self.assertEqual(len(wp.open_items(st2)), 1)


class TestPurity(unittest.TestCase):
    """ГРАНИЦА УСТРОЙСТВОМ: импортов ноль — ни файла, ни сети, ни часов."""

    def test_module_imports_nothing(self):
        import ast
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "works_persist.py"), encoding="utf-8") as f:
            src = f.read()
        bad = [n for n in ast.walk(ast.parse(src))
               if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertEqual(bad, [], "у журнала принятых работ импортов быть не должно")

    def test_module_has_no_open_or_time_calls(self):
        import ast
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "works_persist.py"), encoding="utf-8") as f:
            src = f.read()
        names = {n.func.id for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        for forbidden in ("open", "eval", "exec", "__import__"):
            self.assertNotIn(forbidden, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
