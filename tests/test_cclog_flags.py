# -*- coding: utf-8 -*-
"""Журнал: флаги отделены от текста; подпись несёт фактический канал.

Живой дефект 28.07.2026: `cclog --help` записал в мозг строку «DONE ...: --help» —
разбора флагов не было вовсе, аргумент уехал в текст. Голдены — дословные
аргументы того провала.
"""
import datetime
import importlib.util
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(ROOT, "cclog.py")):
    ROOT = os.path.dirname(ROOT)
CCLOG = os.path.join(ROOT, "cclog.py")
WROTE = "OK cc_log"          # признак того, что строка реально ушла в журнал
ENVKEYS = ("CCLOG_CHANNEL", "TERMUX_VERSION", "PREFIX",
           "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")


def load():
    spec = importlib.util.spec_from_file_location("cclog_mod", CCLOG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(*args):
    return subprocess.run([sys.executable, CCLOG, *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)


class SpravkaNePishetsya(unittest.TestCase):
    def test_help_pechataet_i_ne_pishet(self):
        for flag in ("--help", "-h"):
            r = run(flag)
            self.assertEqual(r.returncode, 0, flag)
            self.assertIn("cclog", r.stdout)
            self.assertNotIn(WROTE, r.stdout + r.stderr, "справка ушла в журнал: " + flag)

    def test_help_sredi_argumentov(self):
        r = run("DONE", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn(WROTE, r.stdout + r.stderr)


class NeizvestnyjFlagOtklonen(unittest.TestCase):
    def test_otkaz_a_ne_zapis(self):
        r = run("--oops", "текст итога")
        self.assertEqual(r.returncode, 2)
        self.assertIn("неизвестный флаг", r.stderr)
        self.assertNotIn(WROTE, r.stdout + r.stderr)


class TekstSDefisom(unittest.TestCase):
    def test_minus_chislo_ne_flag(self):
        mod = load()
        for t in ("-7000", "-111", "-42.5"):
            self.assertFalse(mod._is_flag(t), t)
        for f in ("--help", "-h", "--pulse"):
            self.assertTrue(mod._is_flag(f), f)


class MetkaKanala(unittest.TestCase):
    def _channel(self, **env):
        mod = load()
        keep = {k: os.environ.get(k) for k in ENVKEYS}
        try:
            for k in ENVKEYS:
                os.environ.pop(k, None)
            os.environ.update({k: v for k, v in env.items() if v is not None})
            return mod._channel()
        finally:
            for k, v in keep.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_ssh(self):
        self.assertEqual(self._channel(SSH_CONNECTION="1.2.3.4 1 5.6.7.8 22"), "ssh")

    def test_termux(self):
        self.assertEqual(self._channel(TERMUX_VERSION="0.118"), "Termux")

    def test_lokalno(self):
        self.assertEqual(self._channel(), "local")

    def test_pereopredelenie(self):
        self.assertEqual(self._channel(CCLOG_CHANNEL="RC", SSH_CONNECTION="x"), "RC")


class ValidatorPrinimaetNovujuMetku(unittest.TestCase):
    """Метка сменилась — ENTRY_RE обязан принимать и новую, и легаси."""

    def test_novye_i_legacy_metki(self):
        mod = load()
        now = datetime.datetime(2026, 7, 28, 8, 30)
        for label in ("ssh", "local", "Termux", "Termux-raw", "ssh-raw", "RC"):
            line = mod._make_entry("DONE", "итог работы", now=now, label=label)
            self.assertIn("(%s):" % label, line)
            self.assertRegex(line, mod.ENTRY_RE, "метка отвергнута ENTRY_RE: " + label)

    def test_bez_payload_ne_matchit(self):
        mod = load()
        self.assertIsNone(mod.ENTRY_RE.match("DONE 2026-07-16 09:00 UTC (ssh):"))


if __name__ == "__main__":
    unittest.main()
