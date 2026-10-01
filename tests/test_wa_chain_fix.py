#!/usr/bin/env python3
"""Малые дефекты цепочки агента WhatsApp до выкатки (WACHAINFIX0210).

(1) Соединения с очередью в модулях службы агента закрываются ЯВНО. Блок `with` у sqlite3 фиксирует
    транзакцию, но соединение не закрывает (проба WAGREETECHO0210: 1 328 открытий подряд → «unable to
    open database file» при пределе 1 024 дескрипторов). Замер — 2 000 оборотов каждого места на
    подделке: число открытых дескрипторов процесса (/proc/self/fd) не растёт, и ни одно соединение,
    открытое местом, не осталось открытым. Сборщик мусора на время замера выключен: закрытие не должно
    зависеть от него. Нет /proc (не Linux) — проверяется только второе.
(2) Ожидание `wa_watch` берёт отпечаток приветствия из той же настройки WA_AGENT_GREET_SHA256 и тем же
    правилом, что ядро (`wa_agent.greet_fps` → `wa_agent.greet_hit`); константы в коде нет; правило
    времени остаётся; нет настройки — автоответ ловит одно время.
(3) Дверь своего дерева — в tests/test_wa_send.py (корень от файла теста), доказательство — мутантом.

Подделки — из test_wa_agent и test_wa_watch: временная очередь схемой wa_webhook, временная база
агента, поддельные Telegram, модель и дверь. Сети нет, модель не зовётся, живых баз нет.

WA_AGENT_SRC=<каталог> подменяет модули (прогон мутантов)."""
import gc
import hashlib
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
if os.environ.get("WA_AGENT_SRC"):
    sys.path.insert(0, os.environ["WA_AGENT_SRC"])

import wa_agent as A  # noqa: E402
import wa_send  # noqa: E402
import wa_watch as W  # noqa: E402
import test_wa_agent as T  # noqa: E402
import test_wa_watch as TW  # noqa: E402

N = 2000
FD_DIR = "/proc/self/fd"
GREET = "ВЫДУМАННОЕ автоприветствие: скутеры 125–160, макси 300–400, менеджер ответит."
FP = hashlib.sha256(GREET.encode("utf-8")).hexdigest()
OTHER_FP = hashlib.sha256("другой текст приветствия".encode("utf-8")).hexdigest()


# ═══ (1) соединения закрываются явно ═══════════════════════════════════════════════════════

def _fds():
    return len(os.listdir(FD_DIR)) if os.path.isdir(FD_DIR) else None


class _Track:
    """sqlite3.connect на время замера: каждое открытое соединение под учётом (ссылка держится —
    незакрытое не соберёт и сборщик мусора)."""

    def __init__(self):
        self.conns, self.real = [], sqlite3.connect

    def __enter__(self):
        def connect(*a, **kw):
            c = self.real(*a, **kw)
            self.conns.append(c)
            return c
        sqlite3.connect = connect
        return self

    def __exit__(self, *exc):
        sqlite3.connect = self.real

    def left_open(self):
        n = 0
        for c in self.conns:
            try:
                c.execute("SELECT 1")
                n += 1
            except sqlite3.ProgrammingError:                       # закрыто
                pass
        return n


def measure(fn, n=N):
    """fn(i) n раз → (прирост дескрипторов | None без /proc, соединений открыто, осталось открытыми)."""
    fn(-1)                                                       # прогрев: первая запись базы агента и пр.
    gc.collect()
    was = gc.isenabled()
    gc.disable()
    tr = _Track()
    try:
        before = _fds()
        with tr:
            for i in range(n):
                fn(i)
        after = _fds()
        left = tr.left_open()
    finally:
        for c in tr.conns:
            c.close()
        if was:
            gc.enable()
    return (None if before is None else after - before), len(tr.conns), left


def check(place, res, n=N):
    grew, opened, left = res
    print("  замер %s: оборотов %d, соединений открыто %d, осталось открытыми %d, дескрипторов %s"
          % (place, n, opened, left, "нет /proc" if grew is None else "%+d" % grew))
    assert opened >= n, (place, "место не открывало очередь — замер пустой", res)
    assert left == 0, (place, "соединения не закрыты", res)
    assert grew is None or grew <= 0, (place, "дескрипторы растут", res)


def _world():
    w = T.World()
    w.put(T.T0 - 900)                                            # входящее клиента
    w.put(T.T0 - 890, kind="echo", wamid="wamid.E1")             # эхо с телефона — пауза
    return w


def test_scan_2000_fds_flat():
    w = _world()
    check("Core.scan", measure(lambda i: w.core.scan(T.T0 + i)))


def test_follow_2000_fds_flat():
    w = _world()
    w.core.drafts = False                                        # WA_AGENT_DRAFTS выключен → follow
    check("Core.follow", measure(lambda i: w.core.tick(T.T0 + i)))


def test_fresh_2000_fds_flat():
    w = _world()
    check("Core._fresh", measure(lambda i: w.core._fresh(T.NUM, 0)))


def test_after_first_2000_fds_flat():
    w = _world()
    rid = w.put(T.T0 - 897, kind="echo")
    check("Core._after_first", measure(lambda i: w.core._after_first(T.NUM, rid, T.T0 - 897)))


def test_tick_drafts_on_2000_fds_flat():
    """Такт ядра с черновиками: скан + черновик (`_fresh`) — как в цикле службы."""
    w = T.World()
    w.put(T.T0 - 900)
    check("Core.tick", measure(lambda i: w.core.tick(T.T0 + i)))


def test_watch_tick_2000_fds_flat():
    w = _world()
    sent = []
    watch = W.Watch(w.core.db, w.qpath, lambda number, text: sent.append(number) or (True, 1), every=0)
    watch.tick(T.T0 - 1000)                                      # первый старт: курсор
    w.put(T.T0 - 2300)                                           # «первое» входящее — без ответа
    w.put(T.T0 - 2297, kind="echo")                              # 3 с — автоответ по времени
    check("Watch.tick", measure(lambda i: watch.tick(T.T0 + i)))
    assert sent == [T.NUM], sent                                 # оборот шёл всем путём: тревога одна


def test_send_door_2000_fds_flat():
    w = _world()
    check("wa_send.last_inbound_ts", measure(lambda i: wa_send.last_inbound_ts(T.NUM, db_path=w.qpath)))


# ═══ (2) wa_watch — на настройке ядра ═══════════════════════════════════════════════════════

def _greet_case(environ, delay):
    """Клиент написал, через delay с эхо текстом приветствия, дольше порога ничего. → (тревог, мир)."""
    w = TW._w(dict(TW.ON, **environ))
    w.row(TW.T0 - 2300)
    w.row(TW.T0 - 2300 + delay, echo=1, text=GREET)
    w.serve(120)
    return len(w.alarms()), w


def test_watch_setting_changes_outcome():
    """Эхо приветствия через 100 с (по времени не автоответ): исход решает настройка."""
    for setting, want in ((FP[:10], 1),              # отпечаток совпал — автоответ, ответа нет → тревога
                          (FP, 1),                   # полный sha256 — то же правило, что у ядра
                          (FP[:16].upper(), 1),      # начало от 10 знаков, регистр не важен
                          (OTHER_FP[:10], 0),        # другой отпечаток — эхо человека → ответ
                          ("не-отпечаток", 0),       # битая — признака нет
                          (None, 0)):                # нет настройки — признака нет
        environ = {} if setting is None else {"WA_AGENT_GREET_SHA256": setting}
        got, w = _greet_case(environ, 100)
        assert got == want, (setting, got, w.lines[-5:])
        assert w.core.watch.greet == w.core.greet, (setting, w.core.watch.greet, w.core.greet)


def test_watch_no_setting_time_rule():
    """Нет настройки — автоответ ловит одно время: эхо через 3 с после «первого» входящего — не ответ."""
    got, w = _greet_case({}, 3)
    assert w.core.watch.greet == () and got == 1, (w.core.watch.greet, got)
    got, w = _greet_case({"WA_AGENT_GREET_SHA256": OTHER_FP[:10]}, 3)
    assert got == 1, got                                         # с настройкой время тоже остаётся


def test_watch_no_fingerprint_in_code():
    """Отпечатка в коде нет: Watch без настройки — пусто, константы GREET_FP нет."""
    w = T.World()
    watch = W.Watch(w.core.db, w.qpath, lambda number, text: (True, 1))
    assert watch.greet == () and not hasattr(W, "GREET_FP"), (watch.greet, getattr(W, "GREET_FP", None))


def test_greet_hit_one_rule():
    assert A.greet_hit(GREET, (FP,)) and A.greet_hit(GREET, (FP[:10],))
    assert not A.greet_hit(GREET, ()) and not A.greet_hit(GREET, (OTHER_FP[:10],))
    assert not A.greet_hit("", (FP[:10],)) and not A.greet_hit(None, (FP[:10],))


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
