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
  (G) шаблон скрипта рестарта `srv_splinter_restart.sh` (дословная копия ниже) принимает ровно STRICT=ВКЛ и GEN=ВЫКЛ.
Сеть, мост и CRM не трогаются; окружение восстанавливается после каждой проверки.
"""
import ast
import os
import re
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)                 # корень СВОЕГО дерева — первым (ловушка метода: чужой корень не берём)

STRICT, GEN = "INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN"
for _f in ("RENTAL_CASE", "RENTAL_CASE_PICK", "RENTAL_CASE_APPROVALS", "RENTAL_CASE_DB", GEN, STRICT):
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

# (G) Шаблон из srv_splinter_restart.sh — ДОСЛОВНО (ERE grep). Разошлись — тест обязан покраснеть вместе со скриптом.
RESTART_OK_RE = r"🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ \((не )?задан\) · CONTRACT_REF_GEN=ВЫКЛ \((не )?задан\)$"


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
        with _Env(**{STRICT: None, GEN: None}):
            self.assertEqual(S.release_flags_line(),
                             "🧩 флаги выпуска: INTAKE_CONFIRM_STRICT=ВКЛ (не задан) · CONTRACT_REF_GEN=ВЫКЛ (не задан)")
            self.assertTrue(S._intake_confirm_strict_on())
            self.assertFalse(S._rc_on(GEN))


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
        for name, v in ((STRICT, "maybe"), (STRICT, "2"), (STRICT, "вкл"), (GEN, "да"), (GEN, "enabled"), (GEN, "2")):
            with _Env(**{name: v}):
                self.assertEqual(_word(S.release_flags_line(), name), "НЕИЗВЕСТНО (задан)", "%s=%r" % (name, v))

    def test_twins_inside_dictionary_are_decided(self):
        for name, v, want in ((STRICT, "да", "ВКЛ (задан)"), (STRICT, "нет", "ВЫКЛ (задан)"),
                              (GEN, "yes", "ВКЛ (задан)"), (GEN, "нет", "ВЫКЛ (задан)")):
            with _Env(**{name: v}):
                self.assertEqual(_word(S.release_flags_line(), name), want, "%s=%r" % (name, v))


class E_NoValue(unittest.TestCase):
    def test_value_never_printed(self):
        bait = "Zq9-bait-VALUE-7731"
        for name in (STRICT, GEN):
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
            with _Env(**{STRICT: sv, GEN: gv}):
                line = S.release_flags_line()
                self.assertEqual(bool(rx.search(line)), want, "STRICT=%r GEN=%r → %s" % (sv, gv, line))
        self.assertIsNone(rx.search("🧩 флаги выпуска: НЕ ПРОЧИТАНЫ (KeyError)"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
