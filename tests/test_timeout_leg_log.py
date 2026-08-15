"""ЖУРНАЛ ТАЙМАУТА НАЗЫВАЕТ ВЫДАННОЕ ПЛЕЧО, А НЕ НАСТРОЕННОЕ — замок (15.08.2026).

КЛАСС. Строка `Bridge timeout (>Ns) for action=…` печатала `self.timeout` — НАСТРОЕННОЕ плечо, —
тогда как запросу выдавался `_leg_timeout()`, урезанный остатком общего бюджета захода. В журнале
стояло «>45s» там, где плечо реально прождало ~14 с: замер по splinter.log читал НАСТРОЙКУ вместо
ФАКТА и завышал время ожидания (повод — куратор цели 19, шаг 1; остаток артефакта
`docs/artifacts/2026-08-15-poll-leg-not-cutting-live-answers.md`). Родня класса — «нуль по
неразбору» (`scan_result`) и «баланс из кэша молча» (`balance_fact`): число печатается, а откуда
оно взялось — умалчивается.

ЗАМОК СТОИТ НА ФАКТЕ, А НЕ НА ФОРМУЛЕ: число из строки журнала сверяется с тем, что ПОЛУЧИЛА
сессия (`timeout=` живого вызова), — не с пересчётом той же арифметики. Поэтому тест краснеет и
на возврат прежней подстановки, и на любую новую, которая разойдётся с выданным.

КОНТРОЛЬНЫЕ ВЕТКИ («как было до правки») зелёные в ОБОИХ прогонах: они доказывают, что тест видит
разницу, а не зелен всегда.

ГРАНИЦЫ, КОТОРЫЕ ЗАХОД НЕ ТРОГАЕТ (секция 6): величины плеч, дедлайны и число опросов те же;
голова строки `Bridge timeout (>Ns) for action=…` не изменена — по ней ходят разборщики журнала,
пометка урезки клеится ХВОСТОМ; форма без урезки БАЙТ-В-БАЙТ прежняя.

ВРЕМЯ ВИРТУАЛЬНОЕ (приём tests/test_poll_leg.py): часы `bridge_client` подменяются, иначе остаток
бюджета зависел бы от нагрузки машины и гейт давал бы ложный красный.
"""
import os
import sys
import threading
import time as _real_time

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")

import requests
import card_deadline as CD
import bridge_client as BC

res = []


def ok(cond, label):
    print(("  PASS  " if cond else "  FAIL  ") + label)
    res.append(bool(cond))
    return bool(cond)


# ============================ ВИРТУАЛЬНЫЕ ЧАСЫ + ЛЕЖАЩИЙ МОСТ ============================
class Clock:
    def __init__(self, now=1000.0):
        self.now = float(now)

    def monotonic(self):
        return self.now

    def time(self):
        return _real_time.time()

    def sleep(self, sec):
        self.now += float(sec)


class DeadBridge:
    """Мост, который не отвечает вовсе: каждое плечо честно висит ВЕСЬ выданный ему бюджет и
    падает Timeout'ом — так ведёт себя requests, и так рождается разбираемая строка журнала.
    `issued` — то, что сессия РЕАЛЬНО получила: с этим и сверяется журнал."""

    def __init__(self, clock):
        self.clock = clock
        self.issued = []

    def _leg(self, timeout):
        self.issued.append(float(timeout))
        self.clock.now += float(timeout)
        raise requests.exceptions.Timeout("плечо истекло")

    def get(self, url, **kw):
        self._leg(kw.get("timeout"))

    def post(self, url, **kw):
        self._leg(kw.get("timeout"))

    def close(self):
        pass


class Rec:
    """Перехват журнала: копим строки уровня error/warning, ничего не печатая в лог."""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg, *a):
        self.errors.append(msg % a if a else msg)

    def warning(self, msg, *a):
        self.warnings.append(msg % a if a else msg)

    info = debug = warning


def run(leg, budget=None, spent_before=0.0, label="опроса очереди", attempts=1):
    """Один заход к лежащему мосту. → (строки журнала, ответ, выданные плечи).

    `spent_before` — сколько бюджета уже сгорело до обмена (так и рождается урезанное плечо:
    первая попытка съела своё, второй достаётся остаток)."""
    clock = Clock()
    rec = Rec()
    old_time, old_log = BC.time, BC.log
    BC.time, BC.log = clock, rec
    try:
        c = BC.BridgeClient(url="http://x", token="t", timeout=leg)
        c.retry_attempts = attempts
        c.retry_base = 0.0
        c.retry_jitter = 0.0
        sess = DeadBridge(clock)
        c._session = sess
        c._new_session = lambda: None
        if budget is None:
            out = c._one_exchange("GET", "get_pending", params={})
        else:
            with BC.card_budget(budget, label=label):
                clock.now += float(spent_before)
                out = c._one_exchange("GET", "get_pending", params={})
        return rec, out, sess.issued
    finally:
        BC.time, BC.log = old_time, old_log


def said_number(line):
    """Число из головы строки журнала — ровно так его читает разборщик замера."""
    head = line.split("(>", 1)[1].split("s)", 1)[0]
    return float(head)


# ============================ (1) БЕЗ БЮДЖЕТА — СТРОКА БАЙТ-В-БАЙТ ПРЕЖНЯЯ ============================
print("(1) бюджет не открыт: плечо выдано настроенное, строка не меняется ни на символ")

rec, out, issued = run(leg=45)
ok(rec.errors == ["Bridge timeout (>45s) for action=get_pending"],
   f"голова строки прежняя: «{rec.errors[0] if rec.errors else '—'}»")
ok(out == {"ok": False, "error": "timeout", "message": "Timeout >45s"},
   "контракт ответа прежний (error=timeout, message без хвоста) — читатели не тронуты")
ok(issued == [45.0], f"сессии выдано настроенное плечо {issued}")

rec1, out1, _ = run(leg=1)
ok(out1.get("message") == "Timeout >1s",
   "голден соседнего сьюта (timeout=1 → «Timeout >1s») цел: число печатается без хвоста «.0»")

# ============================ (2) БЮДЖЕТ УРЕЗАЛ ПЛЕЧО — В ЖУРНАЛЕ ВЫДАННОЕ ============================
print("\n(2) общий бюджет 60 с, до обмена сгорело 46 с → плечу остаётся 14 с")

rec, out, issued = run(leg=45, budget=60, spent_before=46.0)
line = rec.errors[0] if rec.errors else ""
ok(issued == [14.0], f"сессия РЕАЛЬНО получила {issued[0] if issued else '—'} с (остаток бюджета)")
ok(bool(line) and abs(said_number(line) - issued[0]) < 0.01,
   f"журнал назвал ВЫДАННОЕ число: «{line}»")
ok("45" not in line.split("action=")[0],
   "в голове строки НЕТ настроенных 45 с — ради этого заход и сделан")
ok(BC.BridgeClient._LEG_CUT_NOTE in line and "настроено 45s" in line,
   "урезка ПОМЕЧЕНА и настроенное плечо названо рядом — из строки видно и факт, и настройка")
ok("опроса очереди" in line,
   "назван ЧЕЙ бюджет урезал плечо (метка захода, а не общее слово «карточка»)")
ok(out.get("error") == "timeout" and out.get("message", "").startswith("Timeout >14s"),
   f"ответ несёт то же число: «{out.get('message')}»")

# КОНТРОЛЬ: прежняя формула на ТЕХ ЖЕ фактах напечатала бы настройку — тест видит разницу
ok(f"Bridge timeout (>{45}s) for action=get_pending" != line,
   "КОНТРОЛЬ: прежняя строка (>45s) и новая — РАЗНЫЕ (иначе замок был бы пустым)")
ok(abs(45.0 - issued[0]) > 30,
   f"КОНТРОЛЬ: прежнее число завышало ожидание в {45.0 / issued[0]:.1f} раза — это и есть враньё замера")

# ============================ (3) ЧИСЛО ЖУРНАЛА = ЧИСЛО СЕССИИ, НА ЛЮБОМ ОСТАТКЕ ============================
print("\n(3) сверка по факту, а не по формуле: журнал против выданного сессии")

for spent in (0.0, 10.0, 30.5, 44.0, 46.0, 55.0, 58.0, 59.0):
    rec, out, issued = run(leg=45, budget=60, spent_before=spent)
    line = rec.errors[0] if rec.errors else ""
    ok(bool(issued) and bool(line) and abs(said_number(line) - issued[0]) < 0.06,
       f"сгорело {spent:g} с → выдано {issued[0]:g} с, в журнале {said_number(line) if line else '—'}")

rec, out, issued = run(leg=45, budget=60, spent_before=59.0)
ok(issued and abs(issued[0] - CD.LEG_MIN) < 0.01,
   f"дно плеча: остаток 1 с, выдано {issued[0]:g} с (LEG_MIN) — журнал назвал его же")

# Ниже дна обмен не начинается ВОВСЕ (`_card_room`), и это не таймаут, а третий исход: строка
# журнала о плече тут не рождается и родиться не должна — плеча не было.
rec, out, issued = run(leg=45, budget=60, spent_before=59.5)
ok(issued == [] and out.get("error") == BC.CARD_DEADLINE_ERROR,
   "остаток 0.5 с → плечо не начато вовсе (третий исход), строки о таймауте нет — врать не о чем")

# ============================ (4) ХВОСТ ПОЯВЛЯЕТСЯ ТОЛЬКО ПРИ РАСХОЖДЕНИИ ЧИСЕЛ ============================
print("\n(4) пометка объясняет, почему число не равно настроенному — и молчит, когда равно")

rec, out, issued = run(leg=45, budget=60, spent_before=0.0)
line = rec.errors[0] if rec.errors else ""
ok(issued == [45.0], "остатка хватает на полное плечо — выдано настроенное")
ok(line == "Bridge timeout (>45s) for action=get_pending",
   f"бюджет ОТКРЫТ, но урезки не было → строка прежняя: «{line}»")
ok(BC.BridgeClient._LEG_CUT_NOTE not in line,
   "пометки нет: объяснять нечего, а пометка без расхождения врала бы в другую сторону")

rec, out, issued = run(leg=45, budget=0, spent_before=0.0)
ok(rec.errors and rec.errors[0] == "Bridge timeout (>45s) for action=get_pending",
   "откат (бюджет 0 = дедлайна нет) — строка прежняя")

# ============================ (5) ЧУЖОЙ ПОТОК НЕ ПОДСОВЫВАЕТ СВОЁ ЧИСЛО ============================
print("\n(5) выданное плечо принадлежит ОДНОМУ обмену: потоки не смешиваются")

out_lines = {}


def worker(name, leg, budget, spent):
    rec, _, issued = run(leg=leg, budget=budget, spent_before=spent)
    out_lines[name] = (rec.errors[0] if rec.errors else "", issued)


t1 = threading.Thread(target=worker, args=("узкий", 45, 60, 46.0))
t2 = threading.Thread(target=worker, args=("широкий", 45, None, 0.0))
t1.start(); t1.join()
t2.start(); t2.join()
ok(out_lines["узкий"][1] == [14.0] and abs(said_number(out_lines["узкий"][0]) - 14.0) < 0.01,
   "поток с урезанным бюджетом назвал СВОИ 14 с")
ok(out_lines["широкий"][0] == "Bridge timeout (>45s) for action=get_pending",
   "поток без бюджета назвал СВОИ 45 с — чужое число не протекло (ContextVar, не поле клиента)")

# плечо не записано вовсе (сессию подменили мимо `_leg_timeout`) → прежнее поведение
clock, rec = Clock(), Rec()
old_time, old_log = BC.time, BC.log
BC.time, BC.log = clock, rec
try:
    c = BC.BridgeClient(url="http://x", token="t", timeout=45)
    c.retry_attempts = 1
    c._session = type("S", (), {"get": lambda *a, **k: (_ for _ in ()).throw(
        requests.exceptions.Timeout("x")), "close": lambda *a: None})()
    BC._LAST_LEG.set(None)
    bare = c._one_exchange("GET", "get_pending", params={})
finally:
    BC.time, BC.log = old_time, old_log
ok(rec.errors == ["Bridge timeout (>45s) for action=get_pending"] and bare.get("error") == "timeout",
   "FAIL-SAFE: плечо не записано → печатаем настройку, как печаталось (байт-в-байт прежнее)")

# ============================ (6) ГРАНИЦЫ: ЗАХОД НИЧЕГО НЕ ПЕРЕНАСТРОИЛ ============================
print("\n(6) границы: величины и форма головы строки не тронуты")

import devbot as D  # noqa: E402

ok(D.POLL_TIMEOUT == 45 and D.POLL_BUDGET == 60,
   f"плечо и бюджет опроса те же ({D.POLL_TIMEOUT} с / {D.POLL_BUDGET} с)")
ok(abs(CD.BUDGET_DEFAULT - 60.0) < 1e-9 and abs(CD.LEG_MIN - 1.0) < 1e-9,
   f"дедлайн карточки {CD.BUDGET_DEFAULT:g} с и пол плеча {CD.LEG_MIN:g} с не изменены")

clock = Clock()
old_time = BC.time
BC.time = clock
try:
    c = BC.BridgeClient(url="http://x", token="t", timeout=45)
    plain = c._leg_timeout()
    with BC.card_budget(60, label="опроса очереди"):
        clock.now += 46.0
        cut = c._leg_timeout()
finally:
    BC.time = old_time
ok(plain == 45 and abs(cut - 14.0) < 1e-9,
   f"`_leg_timeout` считает ТО ЖЕ, что и до правки ({plain} / {cut:g}) — изменилась только память о выданном")

src = open("/root/turbobaby-manager-bot/bridge_client.py", encoding="utf-8").read()
ok(src.count('log.error(f"Bridge timeout (>') == 1
   and '(>{said}s) for action={action}{cut}' in src,
   "печатающее место ОДНО, голова строки прежняя, пометка клеится ХВОСТОМ — разборщики целы")
ok("_LAST_LEG.set(" in src and src.count("_LAST_LEG.set(") == 1,
   "выданное плечо записывается РОВНО в одном месте — двум записям разойтись негде")

print("\n" + "=" * 70)
print(f"ИТОГО: {sum(res)}/{len(res)}")
if not all(res):
    sys.exit(1)
