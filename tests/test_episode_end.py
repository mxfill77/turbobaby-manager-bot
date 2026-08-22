#!/usr/bin/env python3
"""КОГДА ЭПИЗОД ОЖИДАНИЯ ПЕРЕСТАЁТ БЫТЬ ЭПИЗОДОМ (22.08.2026). Регресс.

ПОВОД ИЗМЕРЕН, А НЕ ПОЧУВСТВОВАН. Живое состояние рук `/tmp/cc_expect_seen/state.json` на
22.08.2026 09:24 UTC: открыто ДВА эпизода, и ни один не может кончиться.
  · `o7l|1787118120` — 63 ч, наблюдений 123, владельцу не сказано ни разу (вес лёгкий);
  · `o3|7e348d4`     — 283 ч (11.8 суток), заведён прежней редакцией 10.08, вышел из окна
                       судейства 12.08 и с тех пор не судится и не закрывается.
Журнал мозга за всё наблюдение знает 27 ЗАКРЫТЫХ эпизодов, самый долгий прожил 19 ч 28 мин.

ФИКСТУРЫ ДОСЛОВНЫЕ. Записи эпизодов — из живого state.json; строка о детях — из живого
`read_doc name=cowork_log` (26 публикаций 18.08 12:22 → 19.08 05:42, потом ни одной); пороги —
живой `expectations.config()` прода.

ОБА ОТРИЦАТЕЛЬНЫХ ТЕСТА ПУНКТА 6 — секции (4) и (5), и оба обязательны.

(1)  ГРАНИЦА УСТРОЙСТВОМ: импортов НОЛЬ, спросить мир и что-то сделать нечем
(2)  ВЕТКА А на ЖИВОЙ записи: `o3|7e348d4` снимается как НЕИЗВЕСТНО, и это арифметика
(3)  АРИФМЕТИКА, А НЕ ДЛИТЕЛЬНОСТЬ: граница окна проверена с обеих сторон
(4)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): признак правильный, наблюдаемого НЕТ → прибор ОТКАЗЫВАЕТ
(5)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): СВЕЖИЙ СЛЕД ПОКОЙНИКА — «работает» ≠ «умер, а след остался»
(6)  ВЕТКА Б на ЖИВОМ эпизоде: `o7l` поднимается до владельца, и в числе — периоды
(7)  ПОРОГ ОТ ПЕРИОДА ПРОИЗВОДИТЕЛЯ, а не наш: период не назван → не судим
(8)  ЗАМКИ: снятие только у выпавшего из вердикта, подъём только у стоящего в нём
(9)  СЛОВА: снятие говорит «неизвестно» и никогда «доставлен»; подъём — «не опоздание»
(10) РУКИ СКВОЗЬ run(): эпизоды снимаются и поднимаются, журнал и владелец получают своё
(11) ОТКАТ: выключатель гасит ОБЕ ветки, множитель 0 — только ветку Б
(12) СОСЕДИ НЕ ЗАДЕТЫ: вердикт и закрытие по выздоровлению не изменены ни одним полем
(13) ЦЕНА ПО ИСТОРИИ: на 27 закрытых эпизодах правило не сработало бы НИ РАЗУ
"""
import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import episode_end as EE  # noqa: E402
import expectations as E  # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
NOW = 1787390000.0                                  # 2026-08-22 09:33:20 UTC
HOUR = 3600.0

# ── ЖИВЫЕ ПОРОГИ ПРОДА (expectations.config() на 22.08.2026) ───────────────────────────────
CFG = {"deliver": 4 * HOUR, "deliver_window": 48 * HOUR, "pc_child": 12 * HOUR,
       "pc_fresh": 15 * 60.0}

# ── ДОСЛОВНЫЕ ЗАПИСИ ЭПИЗОДОВ ИЗ ЖИВОГО state.json ─────────────────────────────────────────
REC_O3 = {"first": 1786369652.447892, "noted": 1786369652.447892, "task": 0,
          "kind": "o3_unknown",
          "proof": "/root/turbobaby-manager-bot/reports/2026-08-10/expect-o3-7e348d4.md"}
KEY_O3 = "o3|7e348d4"
REC_O7 = {"first": 1787163006.236023, "last": 1787387406.2242126, "ticks": 122,
          "kind": "o7_pulse_lost", "heavy": False, "noted": 0, "task": 0, "held_j": 1,
          "why": "предмет — отсутствие сведений о детях, а не факт о них: решать нечего",
          "num": "строки о детях нет 12 ч 28 мин при пороге 12 ч 0 мин",
          "v": {"kind": "o7_pulse_lost", "key": "o7l|1787118120", "limit": 43200.0}}
KEY_O7 = "o7l|1787118120"
TS_CHILD = 1787118120.0                             # 2026-08-19 05:42:00 UTC — ПОСЛЕДНЯЯ публикация
LAST_LANE = 1787383140.0                            # 2026-08-22 07:19:00 UTC — полоса ПИШЕТ

# ДОСЛОВНАЯ последняя строка о детях. Её собственные слова говорят «0 с назад» — и в этом вся
# соль секции (5): слова свежи, а самой строке 75 часов.
LIVE_SAID = "делает работу (свой продукт 0 с назад)"


def pc_facts(ts=TS_CHILD, last=LAST_LANE, fetched=None, period=360.0, ok_=True,
             children=None, span_to=None):
    return {"pc": {"ok": ok_, "fetched": NOW - 60.0 if fetched is None else fetched,
                   "last": last, "n": 1569,
                   "children": {"ts": ts, "period": period, "span_to": span_to or last,
                                "line": "NOTE 2026-08-19 05:42 UTC: ПУЛЬС · ПК · дети контура:",
                                "children": children if children is not None else [
                                    {"name": "pc_agent", "said": LIVE_SAID, "state": E.CH_ALIVE},
                                    {"name": "userbot", "said": LIVE_SAID, "state": E.CH_ALIVE},
                                    {"name": "moderation_bot", "said": "неизвестно (нет прибора)",
                                     "state": E.CH_UNKNOWN}]}}}


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══
print("\n(1) граница устройством: импортов ноль, спросить мир нечем")
SRC = open(os.path.join(REPO, "episode_end.py"), encoding="utf-8").read()
TREE = ast.parse(SRC)
imports = [n for n in ast.walk(TREE) if isinstance(n, (ast.Import, ast.ImportFrom))]
res.append(ok(len(imports) == 0,
              "(1) импортов НОЛЬ (нашлось %d) — второму определению завестись негде"
              % len(imports)))
NAMES = {n.id for n in ast.walk(TREE) if isinstance(n, ast.Name)} | {
    n.attr for n in ast.walk(TREE) if isinstance(n, ast.Attribute)}
FORBIDDEN = ("open", "exec", "eval", "__import__", "run", "Popen", "system", "urlopen",
             "post", "write_doc", "enqueue_task", "complete_task", "send_message", "time")
hit = sorted(n for n in FORBIDDEN if n in NAMES)
res.append(ok(not hit, "(1) ни одного имени мира/действия в коде (нашлось: %s)" % (hit or "—")))
res.append(ok(EE.GOING != EE.RAISE != EE.DROP and len({EE.GOING, EE.RAISE, EE.DROP}) == 3,
              "(1) исходов ровно три и они различимы: %r · %r · %r"
              % (EE.GOING, EE.RAISE, EE.DROP)))

# ═══ (2) ВЕТКА А НА ЖИВОЙ ЗАПИСИ ═══
print("\n(2) ветка А: живой o3|7e348d4 снимается как НЕИЗВЕСТНО")
gone, why = EE.unreachable(KEY_O3, REC_O3, CFG, NOW)
res.append(ok(gone, "(2) живой эпизод 283 ч признан невозможным к закрытию"))
res.append(ok("вне окна судейства" in why, "(2) причина названа окном судейства: %s" % why[:70]))
o, w, n = EE.state(KEY_O3, REC_O3, {}, CFG, NOW, in_live=False)
res.append(ok(o == EE.DROP, "(2) общий вход даёт СНЯТЬ"))
res.append(ok(n == "", "(2) числа замера у снятия нет — его и не было"))

# ═══ (3) АРИФМЕТИКА, А НЕ ДЛИТЕЛЬНОСТЬ ═══
print("\n(3) арифметика: граница окна проверена с обеих сторон")
edge = NOW - (CFG["deliver_window"] - CFG["deliver"])        # floor == window РОВНО
res.append(ok(not EE.unreachable(KEY_O3, {"first": edge}, CFG, NOW)[0],
              "(3) нижняя оценка РОВНО равна окну → НЕ снимаем (доказано «точно вне», а не «около»)"))
res.append(ok(EE.unreachable(KEY_O3, {"first": edge - 1}, CFG, NOW)[0],
              "(3) на секунду дальше → снимаем"))
res.append(ok(not EE.unreachable(KEY_O3, {"first": NOW - HOUR}, CFG, NOW)[0],
              "(3) молодой эпизод (1 ч) не снимается"))
res.append(ok(not EE.unreachable(KEY_O3, {"first": 0}, CFG, NOW)[0],
              "(3) начала в записи нет → не снимаем: арифметике не на что опереться"))
res.append(ok(not EE.unreachable("o7l|1", REC_O7, CFG, NOW)[0]
              and not EE.unreachable("o2d|1|2", {"first": 1.0}, CFG, NOW)[0],
              "(3) вид без окна судейства («o7l», «o2d») → не судим, эпизод остаётся"))
res.append(ok(not EE.unreachable(KEY_O3, REC_O3, dict(CFG, deliver_window=0), NOW)[0],
              "(3) окно выключено → ветка А мертва"))

# ═══ (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): ПРИЗНАК ПРАВИЛЬНЫЙ, НАБЛЮДАЕМОГО НЕТ ═══
print("\n(4) отрицательный (а): признак выглядит правильным, наблюдаемого нет → ОТКАЗ")
# Состояние: git МОЛЧИТ. Коммита в выборке нет — ровно та же картинка, что у ушедшего из окна.
DEAD_GIT = {"delivery": {"ok": False, "commits": []}}
FULL_GIT = {"delivery": {"ok": True, "commits": [
    {"sha": "7e348d4", "ct": NOW - 200 * HOUR, "subject": "x"}]}}
young = {"first": NOW - HOUR}
res.append(ok(EE.state(KEY_O3, young, DEAD_GIT, CFG, NOW, False)[0] == EE.GOING,
              "(4) git молчит, коммита в выборке НЕТ → эпизод НЕ снят (молчание ≠ уход предмета)"))
res.append(ok(EE.state(KEY_O3, young, DEAD_GIT, CFG, NOW, False)
              == EE.state(KEY_O3, young, FULL_GIT, CFG, NOW, False),
              "(4) ответ ОДИН И ТОТ ЖЕ при мёртвом и при живом git — источник решение не двигает"))
res.append(ok(EE.state(KEY_O3, REC_O3, DEAD_GIT, CFG, NOW, False)
              == EE.state(KEY_O3, REC_O3, FULL_GIT, CFG, NOW, False),
              "(4) и на ЖИВОЙ записи ответ от источника не зависит — замок ветки А"))
# Та же ловушка со стороны ветки Б: журнал НЕ прочитан, предмета в фактах нет.
res.append(ok(EE.lost_instrument(KEY_O7, {"pc": {"ok": False, "err": "мост молчит"}},
                                 CFG, NOW)[0] is False,
              "(4) журнал не прочитан → ветка Б ОТКАЗЫВАЕТ, а не объявляет потерю прибора"))
res.append(ok("не прочитан" in EE.lost_instrument(
    KEY_O7, {"pc": {"ok": False}}, CFG, NOW)[1],
    "(4) и называет причину отказа, а не молчит"))
res.append(ok(EE.lost_instrument(KEY_O7, {}, CFG, NOW)[0] is False
              and EE.lost_instrument(KEY_O7, pc_facts(ts=None), CFG, NOW)[0] is False,
              "(4) фактов нет вовсе / публикации в снимке нет → отказ обеими дорогами"))

# ═══ (5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): СВЕЖИЙ СЛЕД ПОКОЙНИКА ═══
print("\n(5) отрицательный (б): свежий след покойника — «работает» ≠ «умер, а след остался»")
# ФОРМА 1. Слова строки говорят «свой продукт 0 с назад», но самой строке 75 часов.
st_live, info_live = E.children_state(pc_facts(), CFG, NOW)
res.append(ok(st_live != E.CH_ALIVE,
              "(5) строка ГОВОРИТ «делает работу, 0 с назад», но ей 75 ч → НЕ «жив» (дали %r)"
              % st_live))
res.append(ok(info_live.get("lost") is True,
              "(5) прибор называет это просрочкой публикации, а не жизнью детей"))
res.append(ok(E.child_state(LIVE_SAID) == E.CH_ALIVE,
              "(5) при этом САМИ СЛОВА читаются как «жив» — значит отличает возраст, а не текст"))
# ФОРМА 2. Снимок КЭШИРОВАН: источник ВЫГЛЯДИТ живым, потому что показывает старые записи.
stale = pc_facts(fetched=NOW - CFG["pc_fresh"] - 1)
res.append(ok(E.children_state(stale, CFG, NOW)[0] == E.CH_UNKNOWN,
              "(5) срез устарел → состояние «проверить не удалось», а не картинка из кэша"))
gotB, whyB, _ = EE.lost_instrument(KEY_O7, stale, CFG, NOW)
res.append(ok(gotB is False and "устарел" in whyB,
              "(5) и ветка Б ОТКАЗЫВАЕТ поднимать тревогу по кэшу: %s" % whyB[:60]))
# ФОРМА 3. Полоса замолчала ЦЕЛИКОМ: записей после пропавшей публикации нет.
silent = pc_facts(last=TS_CHILD - 60.0, span_to=TS_CHILD - 60.0)
gotС, whyС, _ = EE.lost_instrument(KEY_O7, silent, CFG, NOW)
res.append(ok(gotС is False and "не доказан живым" in whyС,
              "(5) источник не пишет ПОСЛЕ предмета → это молчание полосы (предмет О4), не потеря"))
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(last=TS_CHILD), CFG, NOW)[0] is False,
              "(5) последняя запись РОВНО в момент публикации → живым источник не доказан"))

# ═══ (6) ВЕТКА Б НА ЖИВОМ ЭПИЗОДЕ ═══
print("\n(6) ветка Б: живой o7l поднимается до владельца")
got, why6, num6 = EE.lost_instrument(KEY_O7, pc_facts(), CFG, NOW)
res.append(ok(got, "(6) 75 ч при 4 объявленных периодах по 360 мин → потеря прибора"))
res.append(ok("ЖИВ и пишет" in why6, "(6) причина называет ПОЛОЖИТЕЛЬНЫЙ факт: %s" % why6[:60]))
res.append(ok("периодов" in num6 and "полоса при этом пишет" in num6,
              "(6) число называет и периоды, и живость источника: %s" % num6[:90]))
res.append(ok(EE.state(KEY_O7, REC_O7, pc_facts(), CFG, NOW, in_live=True)[0] == EE.RAISE,
              "(6) общий вход даёт ПОДНЯТЬ"))

# ═══ (7) ПОРОГ ОТ ПЕРИОДА ПРОИЗВОДИТЕЛЯ ═══
print("\n(7) порог берётся из ОБЪЯВЛЕННОГО периода, а не из нашей секунды")
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(period=0), CFG, NOW)[0] is False,
              "(7) период не объявлен → НЕ СУДИМ (своего числа вместо его не ставим)"))
need = 4 * 360 * 60.0
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(ts=NOW - need), CFG, NOW)[0] is False,
              "(7) ровно 4 периода → ещё опоздание"))
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(ts=NOW - need - 1), CFG, NOW)[0] is True,
              "(7) на секунду дальше → потеря"))
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(), CFG, NOW, mult=0)[0] is False,
              "(7) множитель 0 → ветка Б мертва"))
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(period=60.0), CFG, NOW)[0] is True
              and EE.lost_instrument(KEY_O7, pc_facts(ts=NOW - 3 * HOUR, period=60.0),
                                     CFG, NOW)[0] is False,
              "(7) сменил производитель период — сдвинулся и порог: 60 мин → 4 ч"))
res.append(ok(EE.LOST_PERIODS == 4.0,
              "(7) множитель по умолчанию 4 (замер: самый долгий закрытый эпизод = 3.24 периода)"))

# ═══ (8) ЗАМКИ ═══
print("\n(8) замки: снятие — выпавшему, подъём — стоящему в вердикте")
res.append(ok(EE.state(KEY_O3, REC_O3, pc_facts(), CFG, NOW, in_live=True)[0] == EE.GOING,
              "(8) эпизод В ВЕРДИКТЕ не снимается НИКОГДА"))
res.append(ok(EE.state(KEY_O7, REC_O7, pc_facts(), CFG, NOW, in_live=False)[0] == EE.GOING,
              "(8) эпизод ВНЕ вердикта не поднимается НИКОГДА"))
res.append(ok(EE.lost_instrument(KEY_O3, pc_facts(), CFG, NOW)[0] is False,
              "(8) вид без объявленного периода веткой Б не судится"))
res.append(ok(all(EE.state(k, r, f, CFG, NOW, lv)[0] in (EE.GOING, EE.RAISE, EE.DROP)
                  for k in (KEY_O3, KEY_O7, "o1|9|1", "o5s|1", "zzz|1")
                  for r in (REC_O3, REC_O7, {}, {"first": None})
                  for f in ({}, pc_facts(), DEAD_GIT)
                  for lv in (True, False)),
              "(8) на 120 сочетаниях мусора и живых фактов исход всегда один из трёх, без падений"))

# ═══ (9) СЛОВА ═══
print("\n(9) слова: снятие говорит «неизвестно», подъём — «не опоздание»")
dt = EE.drop_text(KEY_O3, REC_O3, why, "VPS", NOW)
res.append(ok("НЕИЗВЕСТНО" in dt, "(9) снятие называет себя НЕИЗВЕСТНЫМ"))
res.append(ok("доставлен" not in dt.lower().replace("не доставлен", ""),
              "(9) слова «доставлен» в снятии нет ни при каком исходе"))
res.append(ok("выздоровление НЕ доказано" in dt, "(9) и прямо говорит, что выздоровления не было"))
res.append(ok("11 сут" in dt or "сут" in dt, "(9) называет прожитый срок: %s" % dt[-120:-60]))
rt = EE.raise_text(KEY_O7, why6, num6, "VPS")
res.append(ok("не опоздание" in rt, "(9) подъём прямо отличает потерю от опоздания"))
res.append(ok("НАБЛЮДЕНИЕ ПОТЕРЯНО" in rt, "(9) и называет НОВЫЙ смысл, а не старое число"))
res.append(ok("рестарта и правок не делаю" in rt,
              "(9) граница слоя в тексте цела: прибор говорит, а не чинит"))
res.append(ok("да" not in rt.split() and "✅" not in rt and "❌" not in rt,
              "(9) ни кнопки, ни номера, ни слова «да» — это не карточка"))

# ═══ (10) РУКИ СКВОЗЬ run() ═══
print("\n(10) руки: сквозной прогон run() — снимает, поднимает, пишет в журнал")
import expectations_run as R  # noqa: E402

SAVED = {}
JOURNAL, NOTES = [], []


def harness(open_eps, facts, env=None, verdicts=None):
    """Полный run() на подменённом мире. Ни сети, ни диска, ни очереди."""
    del JOURNAL[:], NOTES[:]
    st = {"open": dict(open_eps), "tasks": [], "quiet": {"n": 0, "last": []}}
    old = (R.snapshot, R.load_state, R.save_state, R.write_journal, R.send_note,
           R.queue_state_step, R.update_waits, R.remember_bridge, R._to_brain,
           R.write_proof, E.verdict, E.closures)
    R.snapshot = lambda *a, **k: facts
    R.load_state = lambda *a, **k: st
    R.save_state = lambda s: SAVED.update({"st": s})
    R.write_journal = lambda t: (JOURNAL.append(t), True)[1]
    R.send_note = lambda t: (NOTES.append(t), True)[1]
    R.queue_state_step = lambda *a, **k: {"write": False}
    R.update_waits = lambda *a, **k: None
    R.remember_bridge = lambda *a, **k: None
    R._to_brain = lambda: True
    R.write_proof = lambda *a, **k: "proof.md"
    E.verdict = lambda f, c=None: list(verdicts or [])
    E.closures = lambda f, c, keys: []
    keep = {k: os.environ.get(k) for k in (R.EPISODE_END_ENV, R.LOST_PERIODS_ENV)}
    for k, val in (env or {}).items():
        os.environ[k] = val
    try:
        return R.run(now=NOW)
    finally:
        (R.snapshot, R.load_state, R.save_state, R.write_journal, R.send_note,
         R.queue_state_step, R.update_waits, R.remember_bridge, R._to_brain,
         R.write_proof, E.verdict, E.closures) = old
        for k, val in keep.items():
            os.environ.pop(k, None) if val is None else os.environ.__setitem__(k, val)


V_O7 = {"kind": "o7_pulse_lost", "key": KEY_O7, "age": NOW - TS_CHILD, "limit": 43200.0,
        "can_task": False, "ts": TS_CHILD, "period": 360.0}
FACTS = dict(pc_facts(), now=NOW, delivery={"ok": True, "commits": []},
             queue={"rows": []}, splinter={}, daemon={})

r10 = harness({KEY_O3: dict(REC_O3), KEY_O7: dict(REC_O7)}, FACTS, verdicts=[V_O7])
res.append(ok(r10["dropped"] == [KEY_O3],
              "(10) o3|7e348d4 СНЯТ (получено %s)" % r10["dropped"]))
res.append(ok(r10["raised"] == [KEY_O7],
              "(10) o7l ПОДНЯТ до владельца (получено %s)" % r10["raised"]))
res.append(ok(KEY_O3 not in (SAVED.get("st") or {}).get("open", {}),
              "(10) снятый эпизод ушёл из состояния — вечным он больше не будет"))
res.append(ok(any("СНЯТ КАК НЕИЗВЕСТНО" in t for t in JOURNAL),
              "(10) в мозг ушла строка о снятии"))
res.append(ok(any("НАБЛЮДЕНИЕ ПОТЕРЯНО" in t for t in JOURNAL),
              "(10) и строка о подъёме"))
res.append(ok(sum(1 for t in NOTES if "НАБЛЮДЕНИЕ ПОТЕРЯНО" in t) == 1,
              "(10) владельцу о подъёме сказано РОВНО один раз"))
res.append(ok(sum(1 for t in NOTES if "снят как НЕИЗВЕСТНО" in t) == 1,
              "(10) и о снятии — тоже один раз (эпизод был ему объявлен 10.08)"))
r10b = harness({KEY_O3: dict(REC_O3, noted=0), KEY_O7: dict(REC_O7)}, FACTS, verdicts=[V_O7])
res.append(ok(sum(1 for t in NOTES if "снят как НЕИЗВЕСТНО" in t) == 0
              and r10b["dropped"] == [KEY_O3],
              "(10) эпизод, о котором владельцу не говорили, снимается МОЛЧА — но в мозг идёт"))
r10c = harness({KEY_O7: dict(REC_O7, raised=NOW - 10)}, FACTS, verdicts=[V_O7])
res.append(ok(r10c["raised"] == [] and not any("ПОТЕРЯНО" in t for t in NOTES),
              "(10) уже поднятый эпизод второй раз владельца не будит"))

# ═══ (11) ОТКАТ ═══
print("\n(11) откат: выключатель гасит обе ветки, множитель 0 — только ветку Б")
r11 = harness({KEY_O3: dict(REC_O3), KEY_O7: dict(REC_O7)}, FACTS, verdicts=[V_O7],
              env={R.EPISODE_END_ENV: "0"})
res.append(ok(r11["dropped"] == [] and r11["raised"] == [],
              "(11) выключатель: ни снятий, ни подъёмов"))
res.append(ok(KEY_O3 in (SAVED.get("st") or {}).get("open", {}),
              "(11) и эпизод остаётся открытым — поведение байт-в-байт прежнее"))
res.append(ok(not any("ПОТЕРЯНО" in t or "СНЯТ" in t for t in JOURNAL + NOTES),
              "(11) ни одной новой строки ни в мозг, ни владельцу"))
r11b = harness({KEY_O3: dict(REC_O3), KEY_O7: dict(REC_O7)}, FACTS, verdicts=[V_O7],
               env={R.LOST_PERIODS_ENV: "0"})
res.append(ok(r11b["raised"] == [] and r11b["dropped"] == [KEY_O3],
              "(11) множитель 0: ветка Б мертва, ветка А работает — ручки независимы"))

# ═══ (12) СОСЕДИ НЕ ЗАДЕТЫ ═══
print("\n(12) соседи: вердикт и закрытие по выздоровлению не изменены")
res.append(ok(len(E.KINDS) == 12, "(12) видов ожиданий по-прежнему 12"))
FRESH = dict(pc_facts(ts=NOW - HOUR), now=NOW)
res.append(ok(E.children_state(FRESH, CFG, NOW)[0] == E.CH_UNKNOWN,
              "(12) children_state отвечает как отвечал (третий исход при неизвестном ребёнке)"))
ALIVE = dict(pc_facts(ts=NOW - HOUR, children=[
    {"name": "userbot", "said": LIVE_SAID, "state": E.CH_ALIVE}]), now=NOW)
res.append(ok(E.children_state(ALIVE, CFG, NOW)[0] == E.CH_ALIVE,
              "(12) и «жив» по-прежнему возвращается ровно одним путём"))
res.append(ok(E.closures(dict(FACTS, now=NOW), E.config({}), [KEY_O7]) == [],
              "(12) закрытие по выздоровлению эпизод o7l НЕ закрывает — как и раньше"))
src_run = open(os.path.join(REPO, "expectations_run.py"), encoding="utf-8").read()
res.append(ok(src_run.count("episode_end.") > 0 and "episode_end" not in
              open(os.path.join(REPO, "expectations.py"), encoding="utf-8").read(),
              "(12) решение вердиктов о правиле окончания не знает НИ ОДНИМ именем"))

# ═══ (13) ЦЕНА ПО ИСТОРИИ ═══
print("\n(13) цена: на истории закрытых эпизодов правило не сработало бы ни разу")
# Дословный замер по журналу мозга (27 уникальных закрытых эпизодов, 47 строк «закрыт»):
# длительности в секундах, самая долгая — 70080 с = 19 ч 28 мин.
CLOSED_MAX = 70080.0
res.append(ok(CLOSED_MAX < 4 * 360 * 60.0,
              "(13) самый долгий ЗАКРЫВШИЙСЯ эпизод (19 ч 28 мин) короче 4 периодов (24 ч)"))
res.append(ok(EE.lost_instrument(KEY_O7, pc_facts(ts=NOW - CLOSED_MAX), CFG, NOW)[0] is False,
              "(13) на его длительности ветка Б МОЛЧИТ — ноль лишних сообщений за всё наблюдение"))
res.append(ok(CLOSED_MAX / (360 * 60.0) < 4.0,
              "(13) 3.24 периода < 4 — множитель стоит ВЫШЕ всего, что заканчивалось само"))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
