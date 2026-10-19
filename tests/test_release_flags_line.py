# -*- coding: utf-8 -*-
"""INTAKECONFIRM1610 (16.10.2026): строка «🧩 флаги выпуска» в логе старта Splinter.

Повод — Codex TB-REL-CDA1AD9-STOP-1610-0431, причина 1: скрипт рестарта видел только имена окружения юнита, а обе ручки
выпуска (`INTAKE_CONFIRM_STRICT`, `CONTRACT_REF_GEN`) читаются лениво через os.getenv ПОСЛЕ load_dotenv в bot.py, то есть
их эффективные значения из юнита не следуют. Теперь процесс сам говорит их словами при старте, а скрипт рестарта требует
ровно одну строку «STRICT=ВКЛ · GEN=ВЫКЛ»; всё прочее (ВЫКЛ, НЕИЗВЕСТНО, НЕ ПРОЧИТАНЫ, нет строки) — стоп.

Разделы:
  (A) ручки не заданы — точная строка по умолчанию;
  (B) INTAKE_CONFIRM_STRICT: на КАЖДОМ слове словаря (и в другом регистре, с пробелами) слово строки = решение
      `_intake_confirm_strict_on()`;
  (C) CONTRACT_REF_GEN: то же против `_rc_on`;
  (D) значение вне словаря читателя — НЕИЗВЕСТНО (задан); близнец — то же значение из словаря даёт ВКЛ/ВЫКЛ;
  (E) само значение в строку не попадает никогда (приманка);
  (F) bot.py: вызов строки стоит ПОСЛЕ load_dotenv() и настройки журнала, в try с «НЕ ПРОЧИТАНЫ» (ast, по исходнику);
  (G) шаблоны скрипта рестарта: прежний SC_FLAGS_RE (дословная копия srv_splinter_checks.sh выпуска 947953e) на строке
      RC2010 не сходится НИ ПРИ КАКИХ ручках — стоп (exit 7), а не «доказано» без трёх новых; новый шаблон RC2010
      (его обязан взять скрипт рестарта, правка вне репозитория) принимает ровно умолчания выпуска.
RC2010 (20.10.2026): в строку добавлены ручки отрезков 19.10 — CLOSE_TRUTH, CLOSE_ACCRUAL, HANDOVER_FACTS — словом
ДЕЙСТВУЮЩЕГО решения; значение вне словаря читателя — НЕИЗВЕСТНО и рядом то, что действует (читатель CLOSE_TRUTH и
STRICT такое слово молча решает как ВКЛ, `_rc_on` — как ВЫКЛ):
  (H) CLOSE_TRUTH: на каждом слове словаря слово строки = `_close_truth_on()`; не задан — ВКЛ;
  (I) CLOSE_ACCRUAL: слово строки = `_close_accrual_on()` при каждом CLOSE_TRUTH; вкл-слово при CLOSE_TRUTH ВЫКЛ —
      «ВЫКЛ (задан; только поверх CLOSE_TRUTH)»;
  (J) HANDOVER_FACTS: слово строки = `_handover_facts_on()`; ВКЛ, а rental_case_rules не загрузился — «ВЫКЛ (задан;
      rental_case_rules не загрузился)», как и действует;
  (K) разделители: в словах нет « · » и «=», каждый ключ — ровно раз (читатели вне процесса режут строку по ним).
Сеть, мост и CRM не трогаются; окружение восстанавливается после каждой проверки.
"""
import ast
import os
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)                 # корень СВОЕГО дерева — первым (ловушка метода: чужой корень не берём)

STRICT, GEN = "INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN"
TRUTH, ACCR, HOF = "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS"      # RC2010
ALL = (STRICT, GEN, TRUTH, ACCR, HOF)
for _f in ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", GEN, STRICT, TRUTH, ACCR, HOF):
    os.environ.pop(_f, None)

_TMP = tempfile.mkdtemp(prefix="release_flags_t_")
for _k, _name in (("HINT_DEDUP_STATE", "hint_dedup_state.json"), ("DECIDER_LIVE_STATE", "decider_live_state.json"),
                  ("WORKS_PERSIST_STATE", "works_persist_state.json"), ("MILEAGE_Q_STATE", "mileage_q.json"),
                  ("SVC_TOKENS_STATE", "svc_tokens.json"), ("TOPIC_FEED_DIR", "topic_feed"),
                  ("SPLINTER_ASK_STAFF_STATE", "staff_ask_state.json"), ("SPLINTER_RULES_SNAP", "rules_snap.json"),
                  ("WALLET_CACHE_FILE", "wallet_cache.json"), ("ENQUEUE_DEDUP_FILE", "enqueue_dedup.json")):
    os.environ[_k] = os.path.join(_TMP, _name)

try:
    import fcntl  # noqa: F401  (Linux; на ПК — заглушка только для импорта splinter)
except ImportError:
    _fc = types.ModuleType("fcntl")
    _fc.LOCK_SH, _fc.LOCK_EX, _fc.LOCK_NB, _fc.LOCK_UN = 1, 2, 4, 8
    _fc.flock = lambda *a, **k: None
    _fc.lockf = lambda *a, **k: None
    sys.modules["fcntl"] = _fc

import splinter as S  # noqa: E402

# (G) Прежний шаблон: SC_FLAGS_RE srv_splinter_checks.sh (выпуск 947953e, скрипт srv_splinter_restart5_r3.sh) — ДОСЛОВНО
# (ERE grep). Строку 947953e (откат) он принимает по-прежнему; строку RC2010 — никогда.
RESTART_OK_RE_947 = r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)$"
LINE_947_DEFAULT = "🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · CONTRACT_REF_GEN=ВЫКЛ (не задан)"
# (G) Шаблон RC2010 — его обязан взять SC_FLAGS_RE скрипта рестарта выпуска RC2010 (правка вне репозитория, открытый
# пункт К3): умолчания выпуска STRICT=ВКЛ · GEN=ВЫКЛ · CLOSE_TRUTH=ВКЛ · CLOSE_ACCRUAL=ВЫКЛ · HANDOVER_FACTS=ВЫКЛ.
RESTART_OK_RE = (r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)"
                 r" · CLOSE_TRUTH=ВКЛ \((не )?задан\) · CLOSE_ACCRUAL=ВЫКЛ \((не )?задан\)"
                 r" · HANDOVER_FACTS=ВЫКЛ \((не )?задан\)$")
DEFAULT_LINE = ("🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · CONTRACT_REF_GEN=ВЫКЛ (не задан)"
                " · CLOSE_TRUTH=ВКЛ (не задан) · CLOSE_ACCRUAL=ВЫКЛ (не задан) · HANDOVER_FACTS=ВЫКЛ (не задан)")


class _Env:
    """Ручки на время проверки; прежнее окружение возвращается всегда."""

    def __init__(self, **kv):
        self.kv, self.old = kv, {}

    def __enter__(self):
        for k, v in self.kv.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _word(line, name):
    m = re.search(re.escape(name) + r"=([^·]+?)(?: ·|$)", line)
    return m.group(1).strip() if m else None


class A_Default(unittest.TestCase):
    def test_unset_exact_line(self):
        with _Env(**{k: None for k in ALL}):
            self.assertEqual(S.release_flags_line(), DEFAULT_LINE)
            self.assertTrue(S._intake_confirm_strict_on())
            self.assertFalse(S._rc_on(GEN))
            self.assertTrue(S._close_truth_on())          # RC2010: умолчание выпуска — защитная правка ВКЛ
            self.assertFalse(S._close_accrual_on())
            self.assertFalse(S._handover_facts_on())


class B_Strict(unittest.TestCase):
    def test_every_dictionary_word_agrees_with_reader(self):
        n = 0
        for w in S._FLAG_WORDS_STRICT:
            for v in (w, w.upper(), " %s " % w.capitalize()):
                with _Env(**{STRICT: v, GEN: None}):
                    on = S._intake_confirm_strict_on()
                    self.assertEqual(_word(S.release_flags_line(), STRICT), ("ВКЛ" if on else "ВЫКЛ") + " (задан)",
                                     "значение %r" % v)
                    n += 1
        self.assertGreaterEqual(n, 33)

    def test_off_words_are_off(self):
        for v in ("0", "no", "OFF", "False", "НЕТ", ""):
            with _Env(**{STRICT: v}):
                self.assertTrue(_word(S.release_flags_line(), STRICT).startswith("ВЫКЛ"), v)


class C_Gen(unittest.TestCase):
    def test_every_dictionary_word_agrees_with_reader(self):
        n = 0
        for w in S._FLAG_WORDS_RC:
            for v in (w, w.upper(), " %s " % w.capitalize()):
                with _Env(**{GEN: v, STRICT: None}):
                    on = S._rc_on(GEN)
                    self.assertEqual(_word(S.release_flags_line(), GEN), ("ВКЛ" if on else "ВЫКЛ") + " (задан)",
                                     "значение %r" % v)
                    n += 1
        self.assertGreaterEqual(n, 30)

    def test_on_words_are_on(self):
        for v in ("1", "true", "YES", "On"):
            with _Env(**{GEN: v}):
                self.assertTrue(_word(S.release_flags_line(), GEN).startswith("ВКЛ"), v)


class D_Unknown(unittest.TestCase):
    def test_outside_dictionary_is_unknown(self):
        # RC2010: рядом с НЕИЗВЕСТНО — то, что ДЕЙСТВУЕТ: читатель STRICT такое слово решает ВКЛ, `_rc_on` — ВЫКЛ
        for name, v, eff in ((STRICT, "maybe", "ВКЛ"), (STRICT, "2", "ВКЛ"), (STRICT, "вкл", "ВКЛ"),
                             (GEN, "да", "ВЫКЛ"), (GEN, "enabled", "ВЫКЛ"), (GEN, "2", "ВЫКЛ")):
            with _Env(**{name: v}):
                self.assertEqual(_word(S.release_flags_line(), name), "НЕИЗВЕСТНО (задан; действует %s)" % eff,
                                 "%s=%r" % (name, v))
                self.assertEqual(S._intake_confirm_strict_on() if name == STRICT else S._rc_on(GEN), eff == "ВКЛ")

    def test_twins_inside_dictionary_are_decided(self):
        for name, v, want in ((STRICT, "да", "ВКЛ (задан)"), (STRICT, "нет", "ВЫКЛ (задан)"),
                              (GEN, "yes", "ВКЛ (задан)"), (GEN, "нет", "ВЫКЛ (задан)")):
            with _Env(**{name: v}):
                self.assertEqual(_word(S.release_flags_line(), name), want, "%s=%r" % (name, v))


class E_NoValue(unittest.TestCase):
    def test_value_never_printed(self):
        bait = "Zq9-bait-VALUE-7731"
        for name in ALL:
            with _Env(**{name: bait}):
                line = S.release_flags_line()
                self.assertNotIn(bait, line)
                self.assertNotIn(bait.lower(), line.lower())
                self.assertIn("НЕИЗВЕСТНО", line)


class F_BotOrder(unittest.TestCase):
    def test_line_after_load_dotenv_and_logging_in_try(self):
        with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        dotenv = logcfg = call = None
        for node in tree.body:
            src = ast.dump(node)
            if dotenv is None and "load_dotenv" in src and isinstance(node, ast.Expr):
                dotenv = node.lineno
            if logcfg is None and "basicConfig" in src:
                logcfg = node.lineno
            if call is None and "release_flags_line" in src:
                call = node
        self.assertIsNotNone(dotenv)
        self.assertIsNotNone(logcfg)
        self.assertIsNotNone(call, "bot.py не печатает строку флагов выпуска")
        self.assertIsInstance(call, ast.Try, "строка флагов обязана стоять в try (сбой → «НЕ ПРОЧИТАНЫ»)")
        self.assertGreater(call.lineno, dotenv)
        self.assertGreater(call.lineno, logcfg)
        handler = ast.dump(call.handlers[0]) if call.handlers else ""
        self.assertIn("НЕ ПРОЧИТАНЫ", handler)


class G_RestartPattern(unittest.TestCase):
    def test_only_strict_on_gen_off_passes(self):
        rx = re.compile(RESTART_OK_RE)
        cases = {(None, None): True, ("1", None): True, ("да", "0"): True, (None, "нет"): True,
                 ("0", None): False, (None, "1"): False, ("maybe", None): False, (None, "да"): False,
                 ("off", "on"): False}
        for (sv, gv), want in cases.items():
            with _Env(**{STRICT: sv, GEN: gv, TRUTH: None, ACCR: None, HOF: None}):
                line = S.release_flags_line()
                self.assertEqual(bool(rx.search(line)), want, "STRICT=%r GEN=%r → %s" % (sv, gv, line))
        self.assertIsNone(rx.search("🧩 флаги выпуска: НЕ ПРОЧИТАНЫ (KeyError)"))

    def test_rc2010_only_release_defaults_pass(self):
        """RC2010: новые ручки — ровно умолчания выпуска (ВКЛ / ВЫКЛ / ВЫКЛ), заданы они или нет; иначе — стоп."""
        rx = re.compile(RESTART_OK_RE)
        cases = {(None, None, None): True, ("1", "0", "0"): True, ("да", None, "нет"): True, (None, "off", "false"): True,
                 ("0", None, None): False, ("maybe", None, None): False, (None, "1", None): False,
                 (None, "maybe", None): False, (None, None, "1"): False, (None, None, "да"): False,
                 ("0", "1", None): False}
        for (tv, av, hv), want in cases.items():
            with _Env(**{STRICT: None, GEN: None, TRUTH: tv, ACCR: av, HOF: hv}):
                line = S.release_flags_line()
                self.assertEqual(bool(rx.search(line)), want, "TRUTH=%r ACCR=%r HOF=%r → %s" % (tv, av, hv, line))

    def test_old_pattern_stops_on_rc2010_line(self):
        """Прежний SC_FLAGS_RE (якорь `$` после CONTRACT_REF_GEN) строку RC2010 не принимает ни при каких ручках — скрипт
        рестарта 947953e на кандидате останавливается (exit 7), а не доказывает выпуск без трёх новых ручек; строку
        947953e (откат) он принимает, как принимал."""
        old = re.compile(RESTART_OK_RE_947)
        self.assertIsNotNone(old.search(LINE_947_DEFAULT))
        for sv in (None, "1", "0"):
            for tv in (None, "1", "0"):
                for av in (None, "0", "1"):
                    for hv in (None, "0", "1"):
                        with _Env(**{STRICT: sv, GEN: None, TRUTH: tv, ACCR: av, HOF: hv}):
                            line = S.release_flags_line()
                            self.assertIsNone(old.search(line), line)


class H_CloseTruth(unittest.TestCase):
    def test_every_dictionary_word_agrees_with_reader(self):
        n = 0
        for w in S._FLAG_WORDS_TRUTH:
            for v in (w, w.upper(), " %s " % w.capitalize()):
                with _Env(**{TRUTH: v, ACCR: None}):
                    on = S._close_truth_on()
                    self.assertEqual(_word(S.release_flags_line(), TRUTH), ("ВКЛ" if on else "ВЫКЛ") + " (задан)",
                                     "значение %r" % v)
                    n += 1
        self.assertGreaterEqual(n, 33)

    def test_unset_is_on_and_off_words_are_off(self):
        with _Env(**{TRUTH: None}):
            self.assertEqual(_word(S.release_flags_line(), TRUTH), "ВКЛ (не задан)")
        for v in ("0", "no", "OFF", "False", "НЕТ", ""):
            with _Env(**{TRUTH: v}):
                self.assertEqual(_word(S.release_flags_line(), TRUTH), "ВЫКЛ (задан)", v)
                self.assertFalse(S._close_truth_on(), v)

    def test_unknown_word_says_effective_on(self):
        """Читатель CLOSE_TRUTH слово вне выкл-списка решает ВКЛ — строка обязана сказать именно это."""
        for v in ("maybe", "2", "вкл", "выкл", "disabled"):
            with _Env(**{TRUTH: v}):
                self.assertTrue(S._close_truth_on(), v)
                self.assertEqual(_word(S.release_flags_line(), TRUTH), "НЕИЗВЕСТНО (задан; действует ВКЛ)", v)


class I_CloseAccrual(unittest.TestCase):
    def test_word_agrees_with_reader_under_every_truth(self):
        n = 0
        for tv in (None, "1", "0", "maybe"):
            for w in S._FLAG_WORDS_TRUTH:
                for v in (w, w.upper(), " %s " % w.capitalize()):
                    with _Env(**{TRUTH: tv, ACCR: v}):
                        on = S._close_accrual_on()
                        got = _word(S.release_flags_line(), ACCR)
                        if on:
                            self.assertEqual(got, "ВКЛ (задан)", "TRUTH=%r ACCR=%r" % (tv, v))
                        else:
                            self.assertTrue(got.startswith("ВЫКЛ (задан"), "TRUTH=%r ACCR=%r → %s" % (tv, v, got))
                        n += 1
        self.assertGreaterEqual(n, 132)

    def test_on_word_under_truth_off_names_the_reason(self):
        for v in ("1", "yes", "да", "ON"):
            with _Env(**{TRUTH: "0", ACCR: v}):
                self.assertFalse(S._close_accrual_on(), v)
                self.assertEqual(_word(S.release_flags_line(), ACCR), "ВЫКЛ (задан; только поверх CLOSE_TRUTH)", v)
            with _Env(**{TRUTH: None, ACCR: v}):
                self.assertTrue(S._close_accrual_on(), v)
                self.assertEqual(_word(S.release_flags_line(), ACCR), "ВКЛ (задан)", v)

    def test_unknown_word_says_effective(self):
        for tv, eff in ((None, "ВКЛ"), ("1", "ВКЛ"), ("0", "ВЫКЛ")):
            with _Env(**{TRUTH: tv, ACCR: "maybe"}):
                self.assertEqual(S._close_accrual_on(), eff == "ВКЛ")
                self.assertEqual(_word(S.release_flags_line(), ACCR), "НЕИЗВЕСТНО (задан; действует %s)" % eff, tv)

    def test_unset_is_off(self):
        for tv in (None, "1", "0"):
            with _Env(**{TRUTH: tv, ACCR: None}):
                self.assertEqual(_word(S.release_flags_line(), ACCR), "ВЫКЛ (не задан)", tv)


class J_HandoverFacts(unittest.TestCase):
    def test_every_dictionary_word_agrees_with_reader(self):
        n = 0
        for w in S._FLAG_WORDS_RC:
            for v in (w, w.upper(), " %s " % w.capitalize()):
                with _Env(**{HOF: v}):
                    on = S._handover_facts_on()
                    self.assertEqual(on, S._rc_on(HOF), "значение %r" % v)     # rental_case_rules грузится
                    self.assertEqual(_word(S.release_flags_line(), HOF), ("ВКЛ" if on else "ВЫКЛ") + " (задан)",
                                     "значение %r" % v)
                    n += 1
        self.assertGreaterEqual(n, 30)

    def test_unknown_word_says_effective_off(self):
        for v in ("да", "enabled", "2"):
            with _Env(**{HOF: v}):
                self.assertFalse(S._handover_facts_on(), v)
                self.assertEqual(_word(S.release_flags_line(), HOF), "НЕИЗВЕСТНО (задан; действует ВЫКЛ)", v)

    def test_rules_not_loaded_is_off_with_reason(self):
        """HOFACTS v3 (2): ВКЛ, а rental_case_rules не загружается — действует ВЫКЛ; строка так и говорит."""
        def _boom():
            raise ImportError("стенд: rental_case_rules не грузится")
        with _Env(**{HOF: "1"}), mock.patch.object(S, "_rc_rules", _boom):
            self.assertFalse(S._handover_facts_on())
            self.assertEqual(_word(S.release_flags_line(), HOF), "ВЫКЛ (задан; rental_case_rules не загрузился)")
        with _Env(**{HOF: "0"}), mock.patch.object(S, "_rc_rules", _boom):
            self.assertEqual(_word(S.release_flags_line(), HOF), "ВЫКЛ (задан)")


class K_Separators(unittest.TestCase):
    def test_words_never_carry_separators(self):
        """Читатели вне процесса (FLAGREAD k4: ключ ровно раз, слово до « · ») режут строку по « · » и «=»."""
        words = ("1", "0", "maybe", "да", None, "")
        for sv in words:
            for tv in words:
                for av in words:
                    for hv in ("1", "0", "да", None):
                        with _Env(**{STRICT: sv, GEN: sv, TRUTH: tv, ACCR: av, HOF: hv}):
                            line = S.release_flags_line()
                            self.assertEqual(line.count(" · "), 4, line)
                            self.assertEqual(line.count("="), 5, line)
                            for name in ALL:
                                self.assertEqual(line.count(name + "="), 1, line)
                                self.assertIsNotNone(_word(line, name), line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
