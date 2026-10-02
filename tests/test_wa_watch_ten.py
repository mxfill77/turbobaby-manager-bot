#!/usr/bin/env python3
"""Сторож «клиент без ответа»: порог и тихие часы — настройки (WAWATCHTEN0210). Повод — владелец 02.10 12:58:
«35 минут долго минут 10».

(1) Порог — WA_AGENT_WATCH_SEC, по умолчанию 600 с; битое значение — умолчание и строка журнала.
(2) Тихие часы — WA_AGENT_WATCH_QUIET «ЧЧ-ЧЧ» по Пхукету, по умолчанию выключены; тревога, выпавшая на
    тихие часы, приходит в их конце одной сводкой.
(3) Текст тревоги называет порог в минутах из настройки.
На каждое правило — плюс и минус. Подделки — из test_wa_watch (поддельный Bot API, временные очередь, база
показа и база агента, поддельные часы). Сети нет, модель не зовётся.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_watch as W  # noqa: E402
from test_wa_watch import LINK, NUM, ON, T0, FakeHttp, World  # noqa: E402

NUM2 = "66887654321"
QUIET = dict(ON, WA_AGENT_WATCH_QUIET="00-08")


def at(h, m=0, day=1):
    """Пхукет ЧЧ:ММ через `day` суток от суток T0 (T0 — 21:13:20 по Пхукету)."""
    return T0 - (T0 + A.PHUKET_OFFSET) % 86400 + day * 86400 + h * 3600 + m * 60


def _world(environ, t):
    return World(dict(environ), t=t).start(t - 5000)


def _jump(w, t, serve=120):
    w.clock.t = float(t)
    w.serve(serve)


def _summaries(w):
    return [a for a in w.alarms() if a["text"].startswith("⏰ Сводка")]


def _single(w):
    return [a for a in w.alarms() if a["text"].startswith("⏰ Клиент ждёт")]


# ═══ (1) порог — настройка WA_AGENT_WATCH_SEC ════════════════════════════════════════════

def test_threshold_default_600():
    """+ настройки нет — порог 600 с: 650 с тишины — тревога; − 570 с — тишина."""
    assert W.WATCH_SEC == 600 and W.threshold_of(None)[:1] == (600,) and W.threshold_of("")[2] is False
    w = World(dict(ON)).start()
    assert w.core.watch.threshold == 600, w.core.watch.threshold
    w.row(T0 - 650)
    w.serve(20)
    assert len(_single(w)) == 1, w.alarms()
    w2 = World(dict(ON)).start()
    w2.row(T0 - 570)
    w2.serve(20)
    assert w2.alarms() == [], w2.alarms()


def test_threshold_from_setting():
    """+ WA_AGENT_WATCH_SEC=900: 850 с — тишина, 910 с — тревога; − то же сообщение при умолчании звенит сразу."""
    w = World(dict(ON, WA_AGENT_WATCH_SEC="900")).start()
    assert w.core.watch.threshold == 900, w.core.watch.threshold
    w.row(T0 - 850)
    w.serve(20)
    assert w.alarms() == [], w.alarms()
    w.serve(120)
    assert len(_single(w)) == 1, w.alarms()
    assert W.threshold_of("60")[0] == 60 and W.threshold_of("86399")[0] == 86399


def test_threshold_bad_default_and_log_line():
    """+ битое значение — порог 600 и строка журнала «битая»; − годное значение строки «битая» не даёт."""
    for raw in ("abc", "0", "59", "86400", "10m", "-5", "6 00", "600.0", "１２０", "9999999"):
        sec, words, bad = W.threshold_of(raw)
        assert sec == 600 and bad and "битая" in words and W.F_SEC in words, (raw, sec, words)
    w = World(dict(ON, WA_AGENT_WATCH_SEC="abc")).start()
    assert w.core.watch.threshold == 600
    assert any("битая" in ln and "WA_AGENT_WATCH_SEC" in ln for ln in w.lines), w.lines
    w2 = World(dict(ON, WA_AGENT_WATCH_SEC="900")).start()
    assert not any("битая" in ln for ln in w2.lines), w2.lines


# ═══ (2) тихие часы — WA_AGENT_WATCH_QUIET ═══════════════════════════════════════════════

def test_quiet_hours_unit():
    """+ 00-08: 00:00 и 07:59 — тихо; − 08:00 и 23:59 — нет. Через полночь 22-07: 22:00 и 06:59 — тихо, 07:00 нет."""
    q = W.quiet_of("00-08")[0]
    assert q == (0, 8), q
    assert W.in_quiet(at(0), q) and W.in_quiet(at(7, 59), q), "ночь"
    assert not W.in_quiet(at(8), q) and not W.in_quiet(at(23, 59), q) and not W.in_quiet(at(12), q), "день"
    q2 = W.quiet_of("22-07")[0]
    assert W.in_quiet(at(22), q2) and W.in_quiet(at(6, 59), q2) and W.in_quiet(at(0, 30), q2)
    assert not W.in_quiet(at(7), q2) and not W.in_quiet(at(21, 59), q2) and not W.in_quiet(at(12), q2)
    assert W.quiet_of("22-24")[0] == (22, 0) and W.quiet_of(" 0 - 8 ")[0] == (0, 8)
    assert not W.in_quiet(at(2), None)


def test_quiet_alarm_held_then_one_summary():
    """+ двое клиентов без ответа в 02:00 — Telegram молчит; в 08:00 — ОДНА сводка на обоих."""
    w = _world(QUIET, at(2))
    w.row(at(2) - 700)
    w.row(at(2) - 690, number=NUM2)
    w.serve(600)
    assert w.alarms() == [] and w.core.watch.counts() == {W.QUIET: 2}, (w.alarms(), w.core.watch.counts())
    _jump(w, at(7, 50))
    assert w.alarms() == [], w.alarms()
    _jump(w, at(8, 0, ) + 30, serve=600)
    al = w.alarms()
    assert len(al) == 1 and al == _summaries(w), al
    t = al[0]["text"]
    assert "00–08 (Пхукет)" in t and "ждут 2" in t and "Анна" in t and LINK in t and NUM2 in t, t
    assert "Порог — 10 мин (WA_AGENT_WATCH_SEC)" in t, t
    assert w.core.watch.counts() == {W.SENT: 2}, w.core.watch.counts()
    w.serve(600)
    assert len(w.alarms()) == 1, w.alarms()


def test_quiet_off_night_alarm_immediate():
    """− тихих часов нет (умолчание) — в 02:00 тревога сразу, по одной на клиента."""
    w = _world(ON, at(2))
    w.row(at(2) - 700)
    w.row(at(2) - 690, number=NUM2)
    w.serve(120)
    assert len(_single(w)) == 2 and _summaries(w) == [], w.alarms()


def test_quiet_daytime_alarm_immediate():
    """− тихие часы 00-08, а тревога в 09:00 — сразу, отдельной тревогой."""
    w = _world(QUIET, at(9))
    w.row(at(9) - 700)
    w.serve(120)
    assert len(_single(w)) == 1 and _summaries(w) == [], w.alarms()


def test_quiet_answered_before_end_dropped():
    """− ответили с телефона в 07:00 — сводки нет, отложенная строка снята."""
    w = _world(QUIET, at(2))
    w.row(at(2) - 700)
    w.serve(120)
    w.row(at(7), echo=1, text="ответ человека")
    _jump(w, at(8) + 30)
    assert w.alarms() == [] and w.core.watch.counts() == {W.DROPPED: 1}, (w.alarms(), w.core.watch.counts())


def test_quiet_client_wrote_again_one_entry():
    """+ клиент написал ещё раз ночью — в сводке он один, на последнее сообщение."""
    w = _world(QUIET, at(2))
    w.row(at(2) - 700)
    w.serve(120)
    w.row(at(3))
    _jump(w, at(4))
    assert w.core.watch.counts() == {W.QUIET: 2}, w.core.watch.counts()
    _jump(w, at(8) + 30)
    al = _summaries(w)
    assert len(w.alarms()) == 1 and len(al) == 1 and "ждут 1" in al[0]["text"], w.alarms()
    assert "последнее сообщение — %s (Пхукет)" % A.hm_phuket(at(3)) in al[0]["text"], al[0]["text"]
    assert w.core.watch.counts() == {W.DROPPED: 1, W.SENT: 1}, w.core.watch.counts()


def test_quiet_over_midnight():
    """+ 22-07: тревога в 23:30 ждёт, в 06:50–06:52 ещё ждёт, в 07:00 — сводка."""
    w = _world(dict(ON, WA_AGENT_WATCH_QUIET="22-07"), at(23, 30, day=0))
    w.row(at(23, 30, day=0) - 700)
    w.serve(120)
    _jump(w, at(6, 50))
    assert w.alarms() == [] and w.core.watch.counts() == {W.QUIET: 1}, w.core.watch.counts()
    _jump(w, at(7) + 30)
    al = w.alarms()
    assert len(al) == 1 and "22–07 (Пхукет)" in al[0]["text"], al


def test_quiet_restart_keeps_held():
    """+ рестарт службы ночью — отложенное не теряется и не уходит раньше утра; утром одна сводка."""
    w = _world(QUIET, at(2))
    w.row(at(2) - 700)
    w.serve(120)
    w.build(w.environ)
    w.serve(600)
    assert w.alarms() == [] and w.core.watch.counts() == {W.QUIET: 1}, (w.alarms(), w.core.watch.counts())
    _jump(w, at(8) + 30)
    assert len(_summaries(w)) == 1 and len(w.alarms()) == 1, w.alarms()


def test_quiet_summary_retry_on_code():
    """+ Telegram ответил кодом — сводка ещё раз на следующем обороте; − молчание сети — второй раз не шлём."""
    class Http(FakeHttp):
        fail = 1

        def __call__(self, method, url, headers=None, data=None, timeout=30):
            if url.endswith("/sendMessage") and self.fail:
                self.fail -= 1
                self.calls.append(("sendMessage", json.loads(data.decode("utf-8"))))
                return 500, b'{"ok": false, "description": "x"}'
            return FakeHttp.__call__(self, method, url, headers, data, timeout)

    w = World(dict(QUIET), t=at(2))
    w.http = Http(w.clock)
    w.build(w.environ).start(at(2) - 5000)
    w.row(at(2) - 700)
    w.serve(120)
    _jump(w, at(8) + 30, serve=300)
    assert len(_summaries(w)) == 2 and w.core.watch.counts() == {W.SENT: 1}, (w.alarms(), w.core.watch.counts())

    class Silent(FakeHttp):
        def __call__(self, method, url, headers=None, data=None, timeout=30):
            if url.endswith("/sendMessage"):
                self.calls.append(("sendMessage", json.loads(data.decode("utf-8"))))
                return None, b"TimeoutError"
            return FakeHttp.__call__(self, method, url, headers, data, timeout)

    w2 = World(dict(QUIET), t=at(2))
    w2.http = Silent(w2.clock)
    w2.build(w2.environ).start(at(2) - 5000)
    w2.row(at(2) - 700)
    w2.serve(120)
    _jump(w2, at(8) + 30, serve=300)
    assert len(_summaries(w2)) == 1 and w2.core.watch.counts() == {W.UNSURE: 1}, w2.core.watch.counts()


def test_quiet_summary_list_max():
    """+ 22 клиента — поимённо 20, остальные числом; сообщение одно."""
    w = _world(QUIET, at(2))
    for k in range(22):
        w.row(at(2) - 700, number="668000000%02d" % k)
    w.serve(120)
    _jump(w, at(8) + 30)
    al = w.alarms()
    assert len(al) == 1, al
    t = al[0]["text"]
    assert "ждут 22" in t and "\n20) " in t and "\n21) " not in t and "и ещё 2" in t, t


def test_quiet_bad_setting_off_and_log_line():
    """+ битая настройка — тихих часов нет и строка журнала «битая»; − годная — без «битая»."""
    for raw in ("25-08", "8", "00-00", "08-08", "0-24", "abc", "00:08", "-1-8", "00-25", "00-08-10"):
        q, words, bad = W.quiet_of(raw)
        assert q is None and bad and "битая" in words and W.F_QUIET in words, (raw, q, words)
    assert W.quiet_of(None)[0] is None and W.quiet_of("")[2] is False
    w = _world(dict(ON, WA_AGENT_WATCH_QUIET="25-08"), at(2))
    assert w.core.watch.quiet is None
    assert any("битая" in ln and "WA_AGENT_WATCH_QUIET" in ln for ln in w.lines), w.lines
    w.row(at(2) - 700)
    w.serve(120)
    assert len(_single(w)) == 1, w.alarms()                             # ночью — сразу
    w2 = _world(QUIET, at(2))
    assert w2.core.watch.quiet == (0, 8) and not any("битая" in ln for ln in w2.lines), w2.lines


# ═══ (3) текст тревоги называет порог из настройки ════════════════════════════════════════

def test_alarm_text_names_threshold_minutes():
    """+ 900 → «Порог — 15 мин», умолчание → «10 мин», 2130 → «35 мин 30 с»; − прежней фразы про «1 из 10» нет."""
    for raw, words in (("900", "15 мин"), ("", "10 мин"), ("2130", "35 мин 30 с")):
        w = World(dict(ON, WA_AGENT_WATCH_SEC=raw)).start()
        w.row(T0 - 2200)
        w.serve(120)
        al = _single(w)
        assert len(al) == 1 and "Порог — %s (WA_AGENT_WATCH_SEC)." % words in al[0]["text"], (raw, al)
        assert "1 беседе из 10" not in al[0]["text"], al[0]["text"]
    assert W.min_words(600) == "10 мин" and W.min_words(2130) == "35 мин 30 с" and W.min_words(60) == "1 мин"


def test_service_start_line_names_settings():
    """+ строка старта службы называет порог и тихие часы словами; − выключатель выключен — объекта нет."""
    w = World(dict(ON, WA_AGENT_WATCH_SEC="900", WA_AGENT_WATCH_QUIET="00-08")).start()
    ln = [x for x in w.lines if x.startswith("ожидание: порог")]
    assert len(ln) == 1 and "15 мин" in ln[0] and "00–08 по Пхукету" in ln[0], w.lines
    w2 = World({"WA_AGENT_WATCH_SEC": "900", "WA_AGENT_WATCH_QUIET": "00-08"}).start()
    assert w2.core.watch is None and w2.table() is None


def test_log_numbers_only_summary():
    """− в журнале сводки тихих часов нет ни номера, ни текста клиента."""
    w = _world(QUIET, at(2))
    w.row(at(2) - 700, text="секретный текст")
    w.serve(120)
    _jump(w, at(8) + 30)
    log = "\n".join(w.lines)
    assert "сводка тихих часов · клиентов 1" in log and NUM not in log and "секретный" not in log, log


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    bad = 0
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:                                       # noqa: BLE001
            bad += 1
            print("FAIL", name, "—", type(e).__name__, str(e)[:200])
    print("ИТОГ %d/%d" % (len(tests) - bad, len(tests)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
