#!/usr/bin/env python3
"""О4 (ПК) и О5 (МОСТ) — регресс (10.08.2026).

Владелец назвал ТРИ проверки, и все три здесь на ДОСЛОВНЫХ живых фактах:
    ПК не подал признака жизни за отведённое время → ЗВУЧИТ                (секции 3, 4)
    мост не ответил / ответил дольше бюджета       → ЗВУЧИТ                (секции 7, 8)
    проверить состояние невозможно                 → говорит «НЕ ЗНАЮ»,
                                                     и это НЕ «жив»       (секции 5, 6)

ФИКСТУРЫ СНЯТЫ С ПРОДА, А НЕ ВЫДУМАНЫ:
  • строки журнала ПК-контура — дословный снимок `read_doc name=cowork_log` 10.08.2026 09:48 UTC
    (886 строк, 855 со временем, 28.07 15:09 → 09.08 18:16). В нём есть ловушка живого формата:
    у записи 18:09 В ТЕЛЕ стоит ЧУЖОЕ время «Dispatch 2026-08-10 01:09» — местное время ПК,
    на семь часов вперёд. Разбор, берущий максимум по строке, уехал бы в будущее;
  • паузы и пороги — замер того же снимка (шапка expectations.py);
  • длительности моста — 137 прогонов `splinter-health.service` за 21 сутки (515 успешных
    чтений: медиана 2.1 · p95 5.7 · p99 45 · max 207 с) и 12 собственных проб наблюдателя
    10.08 (медиана 2.13, max 2.96 с); потолок 798 с — замер клиента 08–09.08.

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение О4/О5 живёт в том же доказанно безруком модуле
(2)  ЖИВОЙ ФОРМАТ ЖУРНАЛА ПК: время берётся ПЕРВОЕ в строке, а не самое большое
(3)  ЖИВОЙ СЛУЧАЙ 09.08 18:16: ПК молчит, мост отвечает → ЗВУЧИТ
(4)  ПОРОГ 16 ч: законная ночь 13.0 ч молчит, поломка 19.7 ч звучит
(5)  ЗАМОК, НАПРАВЛЕНИЕ 1: канал не доказан живым → о ПК не говорится НИЧЕГО
(6)  ЗАМОК, НАПРАВЛЕНИЕ 2: «неизвестно» — свой ответ, а не вежливое «жив»
(7)  О5 «НЕТ УСПЕХА»: порог 30 мин; отказ без истории → «неизвестно», а не «не отвечает»
(8)  О5 «ДОЛЬШЕ БЮДЖЕТА»: 207 с и 798 с звучат, 66 с и 2.9 с — нет
(9)  ФОРМА ЗАМЕТКИ: без кнопок, без номера, без «да»; «ПК умер» не говорится НИКОГДА
(10) ЗАДАЧИ У О4 И О5 НЕ БЫВАЕТ НИКОГДА
(11) ОТКАТ: порог 0 → ветка мертва ДО чтения фактов, лишнего вызова моста нет
(12) ЗАКРЫТИЕ: только доказанным фактом; молчание источника выздоровлением не считается
(13) РУКИ: составной факт, история переживает прогон, журнал читается у порога досрочно
(14) ЖИВОЙ ФОРМАТ ЗАПУСКА: точка входа таймера, ни один PID не сменился, в канал ноль
"""
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import expectations as E


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
HOUR = 3600.0
NOW = E.parse_iso("2026-08-10T09:48:00Z")          # момент живого замера

# ── ДОСЛОВНЫЕ СТРОКИ ЖУРНАЛА ПК (снимок 10.08.2026) ────────────────────────────────────────
PC_HEAD = (
    "NOTE 2026-08-09 18:16 UTC: Orchestrator: self-update: 8ef0a95→e265f98 — dispatch_notify.py "
    "(гейт пройден, управляемый рестарт демона)  \n"
    "NOTE 2026-08-09 18:15 UTC: Orchestrator: задача #423 → done · Инбокс разведён с потоком "
    "итогов: адрес выбирает один признак «ждёт ли сообщение ответа»  \n"
    "DONE 2026-08-09 18:09 UTC: Dispatch 2026-08-10 01:09: инбокс 1160 разведён с потоком "
    "итогов — адрес выбирает ОДИН признак «ждёт ли сообщение ответа»  \n"
    "DONE 2026-08-09 18:08 UTC: ARTIFACT маршрут инбокса 1160 → "
    "docs/artifacts/2026-08-10-inbox-awaits-reply-route.md: один признак «ждёт ли ответа»  \n"
    "NOTE 2026-08-09 17:42 UTC: Orchestrator: взял задачу #423 (in_progress)  \n"
)
# Живая строка возвращения ПК: он САМ называет причину молчания (проект §5.3).
PC_BACK = ("NOTE 2026-08-06 12:43 UTC: Orchestrator: watchdog: поднял демон через schtasks "
           "(лежал 19 ч 45 м, машина была выключена)  \n")
LAST_TRACE = E.parse_iso("2026-08-09T18:16:00Z")


def cfg(**kw):
    c = E.config({})
    c.update(kw)
    return c


def facts(now=NOW, pc=None, bridge=None, **extra):
    f = {"now": now, "queue": {"ok": True, "rows": []}, "daemon": {}, "splinter": {},
         "delivery": {"ok": False}}
    if pc is not None:
        f["pc"] = pc
    if bridge is not None:
        f["bridge"] = bridge
    f.update(extra)
    return f


def pc_fact(last=LAST_TRACE, fetched=None, ok_=True, err="", line="", n=855):
    return {"ok": ok_, "err": err, "fetched": NOW if fetched is None else fetched,
            "last": last, "line": line, "n": n}


def br_fact(ok_=True, dt=2.13, last_ok=None, last_fast=None, err=""):
    return {"ok": ok_, "dt": dt, "err": err, "last_ok": last_ok, "last_fast": last_fast}


def kinds(vs):
    return sorted(v["kind"] for v in vs)


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══
print("\n(1) решение О4/О5 живёт в модуле, у которого доказанно нет рук")
try:
    import invariants_check as IC

    src = open(os.path.join(REPO, "expectations.py"), encoding="utf-8").read()
    findings = IC._expect_ast_findings(src)
    res.append(ok(findings == [], "(1) EXPECTATIONS_PURE молчит на живом файле: %s" % findings))
    res.append(ok("o4_pc_silent" in E.KINDS and "o5_bridge_down" in E.KINDS
                  and "o5_bridge_slow" in E.KINDS, "(1) оба ожидания объявлены в KINDS"))
    res.append(ok(all(w not in src.replace('"""', "", 2).lower()
                      for w in ("systemctl ", "pkill ")),
                  "(1) слов, которыми перезапускают процессы, в модуле нет"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(1) граница")] * 3

# ЭТОТ ЖЕ ФАЙЛ ГОНЯЕТСЯ НА ДЕРЕВЕ «ДО ПРАВКИ» (git worktree) — там О4/О5 в модуле нет вовсе, и
# без этой заставки прогон падал бы исключением, не давая числа. Падение по AttributeError и
# «проверка не прошла» — разные вещи только для отладчика; для замера это одинаковое красное.
TOTAL_CHECKS = 98                      # сверяется в конце: разошлось — поправить и здесь
if not all(hasattr(E, a) for a in ("cowork_facts", "pc_state", "bridge_state", "PC_UNKNOWN")):
    print("\nСЛОЯ О4/О5 В ЭТОМ ДЕРЕВЕ НЕТ ВОВСЕ — остальные проверки красные по построению")
    while len(res) < TOTAL_CHECKS:
        res.append(ok(False, "проверка %d: ожидания О4/О5 в модуле отсутствуют" % (len(res) + 1)))
    print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
    sys.exit(1)

# ═══ (2) ЖИВОЙ ФОРМАТ ЖУРНАЛА ═══
print("\n(2) разбор журнала ПК на ДОСЛОВНОМ снимке: ловушка чужого времени в теле")
f = E.cowork_facts(PC_HEAD, NOW)
res.append(ok(f["last"] == LAST_TRACE,
              "(2) последний след = 09.08 18:16 (первое время строки), а не 10.08 01:09 из тела"))
res.append(ok(f["n"] == 5, "(2) сосчитаны все 5 строк со временем: %s" % f["n"]))
res.append(ok("self-update" in (f["line"] or ""),
              "(2) строка последнего следа взята дословно: «%s…»" % (f["line"] or "")[:40]))
res.append(ok(E.cowork_facts("", NOW)["last"] is None,
              "(2) пустой журнал → следа нет (None), а не ноль-эпоха"))
res.append(ok(E.cowork_facts("строка без времени вовсе", NOW)["last"] is None,
              "(2) строк со временем нет → None"))
future = "NOTE 2027-01-01 00:00 UTC: из будущего\n" + PC_HEAD
res.append(ok(E.cowork_facts(future, NOW)["last"] == LAST_TRACE,
              "(2) время из будущего следом не считается (запас COWORK_SKEW)"))
res.append(ok(E.cowork_facts(PC_HEAD, None)["last"] == LAST_TRACE,
              "(2) от чужого времени В ТЕЛЕ защищает сам разбор (первое время строки), "
              "а не запас по «сейчас» — эти два замка независимы"))
res.append(ok(E.cowork_facts(future, None)["last"] != LAST_TRACE,
              "(2) а вот от времени В НАЧАЛЕ чужой строки спасает только «сейчас» — "
              "значит руки ОБЯЗАНЫ его передавать, и snapshot передаёт"))

# ═══ (3) ЖИВОЙ СЛУЧАЙ ═══
print("\n(3) живой случай: ПК молчит с 09.08 18:16, мост в том же прогоне отвечает")
fx = facts(pc=pc_fact(line="NOTE 2026-08-09 18:16 UTC: Orchestrator: self-update"),
           bridge=br_fact(dt=2.78))
st, info = E.pc_state(fx, cfg(pc=15.5 * HOUR), NOW)
res.append(ok(st == E.PC_SILENT, "(3) при пороге 15.5 ч состояние = «молчит» (%s)" % st))
v = E.verdict(fx, cfg(pc=15.5 * HOUR))
res.append(ok(kinds(v) == ["o4_pc_silent"], "(3) вердикт ровно один: %s" % kinds(v)))
note = E.render(v[0], "VPS")
print("      ЗАМЕТКА: %s" % note)
res.append(ok("15 ч" in note and "молчит сторона ПК" in note,
              "(3) заметка называет возраст молчания и сторону"))
res.append(ok("2.8 с" in note, "(3) заметка называет, что мост ответил и за сколько"))
res.append(ok(E.pc_state(fx, cfg(pc=16 * HOUR), NOW)[0] == E.PC_ALIVE,
              "(3) при боевом пороге 16 ч то же молчание ещё НЕ нарушение (15.5 < 16)"))

# ═══ (4) ПОРОГ 16 ЧАСОВ ═══
print("\n(4) порог 16 ч на живых паузах: ночь 13.0 ч молчит, поломка 19.7 ч звучит")
C = cfg()
res.append(ok(C["pc"] == 16 * HOUR, "(4) боевой порог = 16 ч (%s с)" % C["pc"]))
for hours, want, why in ((9.6, E.PC_ALIVE, "прежний максимум проекта"),
                         (13.03, E.PC_ALIVE, "законная ночь 08–09.08"),
                         (16.01, E.PC_SILENT, "чуть выше порога"),
                         (19.72, E.PC_SILENT, "смерть машины 06.08")):
    got = E.pc_state(facts(pc=pc_fact(last=NOW - hours * HOUR), bridge=br_fact()), C, NOW)[0]
    res.append(ok(got == want, "(4) пауза %5.2f ч (%s) → %s" % (hours, why, got)))

# ═══ (5) ЗАМОК, НАПРАВЛЕНИЕ 1 ═══
print("\n(5) проверить невозможно → о ПК не говорится НИЧЕГО (четыре дороги)")
DEAD_PC = pc_fact(last=NOW - 20 * HOUR)                 # молчание заведомо выше порога
for name, fx2 in (
    ("мост не ответил в этом прогоне",
     facts(pc=DEAD_PC, bridge=br_fact(ok_=False, last_ok=NOW - 40 * 60, err="timeout"))),
    ("пробу моста не удалось поставить",
     facts(pc=DEAD_PC, bridge=br_fact(ok_=None, dt=None, err="клиент моста не собрался"))),
    ("журнал ПК не прочитан",
     facts(pc=pc_fact(ok_=False, err="request_failed"), bridge=br_fact())),
    ("срез журнала ПК устарел",
     facts(pc=pc_fact(last=NOW - 20 * HOUR, fetched=NOW - 40 * 60), bridge=br_fact())),
    ("в журнале нет строк со временем",
     facts(pc=pc_fact(last=None), bridge=br_fact())),
    ("факта о ПК нет вовсе", facts(bridge=br_fact())),
):
    v2 = [x for x in E.verdict(fx2, C) if x["kind"] == "o4_pc_silent"]
    res.append(ok(v2 == [], "(5) %s → об О4 ни слова" % name))
s5 = E.pc_state(facts(pc=pc_fact(ok_=False, err="request_failed"), bridge=br_fact()), C, NOW)
res.append(ok(s5[0] == E.PC_UNKNOWN and "не прочитан" in s5[1]["why"],
              "(5) состояние названо «неизвестно» и причина названа: %s" % s5[1]["why"]))

# ═══ (6) ЗАМОК, НАПРАВЛЕНИЕ 2 ═══
print("\n(6) «неизвестно» — свой ответ, а не вежливое «жив»")
res.append(ok(E.PC_UNKNOWN != E.PC_ALIVE and E.BRIDGE_UNKNOWN != E.BRIDGE_OK,
              "(6) у незнания своё слово, отличное от благополучия"))
unk = facts(pc=pc_fact(ok_=False, err="request_failed"), bridge=br_fact(ok_=False,
                                                                       last_ok=NOW - 10 * 60))
res.append(ok(E.bridge_state(unk, C, NOW)[0] == E.BRIDGE_UNKNOWN,
              "(6) мост сбоит, но порог не перейдён → «неизвестно», а НЕ «отвечает»"))
res.append(ok(E.closures(unk, C, ["o4|%d" % LAST_TRACE]) == [],
              "(6) незнание НЕ закрывает эпизод ПК (молчание источника ≠ выздоровление)"))
res.append(ok(E.closures(unk, C, ["o5|%d" % int(NOW - 10 * 60)]) == [],
              "(6) незнание НЕ закрывает эпизод моста"))
alive = facts(pc=pc_fact(last=NOW - 60), bridge=br_fact())
res.append(ok(E.closures(alive, C, ["o4|%d" % LAST_TRACE]) == ["o4|%d" % LAST_TRACE],
              "(6) а ДОКАЗАННЫЙ свежий след — закрывает"))

# ═══ (7) О5 «НЕТ УСПЕХА» ═══
print("\n(7) мост не отвечает: порог 60 мин, отказ без истории → «неизвестно»")
res.append(ok(C["bridge"] == 60 * 60, "(7) боевой порог = 60 мин (проект 08.08 давал 30 — при "
                                      "пробе раз в 10 мин это 4 ложных за неделю)"))
for mins, want in ((23.3, E.BRIDGE_UNKNOWN),      # самый долгий НАСТОЯЩИЙ отказ корпуса
                   (50.0, E.BRIDGE_UNKNOWN),      # худшая пробная цепочка 04.08
                   (61.0, E.BRIDGE_DOWN)):
    got = E.bridge_state(facts(bridge=br_fact(ok_=False, last_ok=NOW - mins * 60,
                                              err="HTTP 302")), C, NOW)[0]
    res.append(ok(got == want, "(7) нет успеха %4.1f мин → %s" % (mins, got)))
nohist = E.bridge_state(facts(bridge=br_fact(ok_=False, last_ok=None, err="timeout")), C, NOW)
res.append(ok(nohist[0] == E.BRIDGE_UNKNOWN and "истории успехов нет" in nohist[1]["why"],
              "(7) отказ без истории → «неизвестно», а не выдуманный возраст"))
noprobe = E.bridge_state(facts(bridge=br_fact(ok_=None, dt=None,
                                              err="клиент моста не собрался")), C, NOW)
res.append(ok(noprobe[0] == E.BRIDGE_UNKNOWN,
              "(7) пробы не было вовсе → «неизвестно», в возраст отказа не копится"))
down = E.verdict(facts(bridge=br_fact(ok_=False, last_ok=NOW - 70 * 60, err="HTTP 302")), C)
res.append(ok(kinds(down) == ["o5_bridge_down"], "(7) вердикт: %s" % kinds(down)))
dnote = E.render(down[0], "VPS")
print("      ЗАМЕТКА: %s" % dnote)
res.append(ok("о ПК за это время не знаю ничего" in dnote,
              "(7) заметка о мосте прямо говорит, что о ПК не знает ничего"))
res.append(ok(down[0]["key"] == "o5|%d" % int(NOW - 70 * 60),
              "(7) ключ эпизода — последний успех: пока отказ длится, заметка одна"))

# ═══ (8) О5 «ДОЛЬШЕ БЮДЖЕТА» ═══
# ПОРОГ ПЕРЕСНЯТ 13.08.2026: прежние 120 с брались с корпуса `splinter-health` (137 прогонов),
# а health.py зовёт `read_doc` — это ЧТЕНИЕ МОЗГА, и его max 207 с это cc_log 07.08. Наблюдатель
# же меряет ОПРОС ОЧЕРЕДИ (`get_pending_multi`), у которого свой корпус: 787 прогонов, медиана
# 3.2 · p95 46.3 · p99 228.5 · max 417 с. Голдены ниже переведены на ЭТОТ корпус: 207 с внутри
# его тела (тихо), а первое значение за пустым промежутком 229→251 звучит. Смысл ветки не
# изменился — она по-прежнему ловит класс «две лестницы без общего дедлайна» (798 с звучат).
print("\n(8) мост ответил, но дольше отведённого: 251 с и 798 с звучат, 207 с и 2.9 с — нет")
res.append(ok(C["bridge_slow"] == 240.0, "(8) боевой бюджет одного вызова = 240 с (замер 13.08)"))
for dt, want, why in ((2.13, [], "медиана собственной пробы"),
                      (2.96, [], "max собственной пробы 10.08"),
                      (45.0, [], "p99 корпуса чтения мозга"),
                      (174.0, [], "живой случай 13.08 — внутри тела опроса очереди"),
                      (207.0, [], "max корпуса ЧТЕНИЯ МОЗГА — опросу очереди он не порог"),
                      (229.0, [], "p99 опроса очереди, нижний край пустого промежутка"),
                      (251.0, ["o5_bridge_slow"], "первое значение ЗА пустым промежутком"),
                      (798.0, ["o5_bridge_slow"], "потолок двух лестниц при бюджете 14 с")):
    v8 = E.verdict(facts(bridge=br_fact(dt=dt, last_fast=NOW - 600)), C)
    res.append(ok(kinds(v8) == want, "(8) вызов %6.1f с (%s) → %s" % (dt, why, kinds(v8) or "тихо")))
slow = E.verdict(facts(bridge=br_fact(dt=251.0, last_fast=NOW - 600)), C)[0]
snote = E.render(slow, "VPS")
print("      ЗАМЕТКА: %s" % snote)
res.append(ok("251 с" in snote and "240 с" in snote,
              "(8) заметка называет и потраченное, и отведённое"))
res.append(ok("лестницы повторов" in snote,
              "(8) заметка называет причину класса, а не только число"))
res.append(ok(slow["key"] == "o5s|%d" % int(NOW - 600),
              "(8) ключ — последний уложившийся вызов: эпизод один, а не заметка на каждый прогон"))
fast_again = facts(bridge=br_fact(dt=2.1, last_fast=NOW - 600))
res.append(ok(E.closures(fast_again, C, [slow["key"]]) == [slow["key"]],
              "(8) первый ответ В БЮДЖЕТЕ закрывает эпизод"))
still_slow = facts(bridge=br_fact(dt=300.0, last_fast=NOW - 600))
res.append(ok(E.closures(still_slow, C, [slow["key"]]) == [],
              "(8) «мост ответил» сам по себе эпизод медленных ответов НЕ закрывает"))

# ═══ (9) ФОРМА ЗАМЕТКИ ═══
print("\n(9) форма: без кнопок, без номера, без «да»; «ПК умер» не говорится никогда")
notes = [note, dnote, snote,
         E.render_close("o4|%d" % LAST_TRACE, "VPS", "ПК о себе говорит так: «watchdog…»"),
         E.render_close("o5|1", "VPS"), E.render_close("o5s|1", "VPS")]
for t in notes:
    res.append(ok(all(w not in t.lower() for w in ("подтверд", "кнопк", "approve", " да ", "✅", "❌")),
                  "(9) отвечать не на что: «%s…»" % t[:52]))
for t in (note, dnote, snote):
    res.append(ok(t.endswith(E.TAIL), "(9) граница владельца названа последней строкой"))
res.append(ok("умер" not in note and "мёртв" not in note,
              "(9) О4 не объявляет ПК мёртвым — с сервера это неотличимо от «спит»"))
res.append(ok("различается" in note and "не гадаю" in note,
              "(9) предел канала назван в САМОЙ заметке, а не только в документации"))
res.append(ok(E.NOTE_HEAD["o5_bridge_slow"] != E.NOTE_HEAD["o5_bridge_down"],
              "(9) два разных отказа моста звучат разными заголовками"))

# ═══ (10) ЗАДАЧИ НЕ БЫВАЕТ ═══
print("\n(10) задачи у О4 и О5 не бывает НИКОГДА")
for v10 in (v[0], down[0], slow):
    res.append(ok(v10.get("can_task") is False, "(10) can_task=False у %s" % v10["kind"]))
    res.append(ok(E.task_text(v10) == "", "(10) текста задачи нет у %s" % v10["kind"]))

# ═══ (11) ОТКАТ ═══
print("\n(11) откат: порог 0 → ветка мертва ДО чтения фактов")
res.append(ok(E.verdict(facts(pc=pc_fact(last=NOW - 40 * HOUR), bridge=br_fact()),
                        cfg(pc=0)) == [], "(11) EXPECT_PC_MIN=0 → О4 молчит на явном нарушении"))
res.append(ok(E.pc_state(facts(pc=pc_fact(last=NOW - 40 * HOUR)), cfg(pc=0), NOW)[0]
              == E.PC_UNKNOWN, "(11) выключенная ветка не заявляет «жив»"))
res.append(ok([x for x in E.verdict(facts(bridge=br_fact(ok_=False, last_ok=NOW - 5 * HOUR)),
                                    cfg(bridge=0)) if x["kind"].startswith("o5")] == [],
              "(11) EXPECT_BRIDGE_MIN=0 → ветка «нет успеха» мертва"))
res.append(ok([x for x in E.verdict(facts(bridge=br_fact(dt=798.0)), cfg(bridge_slow=0))
               if x["kind"] == "o5_bridge_slow"] == [],
              "(11) EXPECT_BRIDGE_SLOW_SEC=0 → ветка «дольше бюджета» мертва"))
res.append(ok(E.limit_env("EXPECT_PC_MIN", 960.0, {"EXPECT_PC_MIN": "0"}) == 0.0,
              "(11) ноль в окружении читается как ноль, а не как дефолт"))
res.append(ok(E.limit_env("EXPECT_BRIDGE_SLOW_SEC", 120.0, {}, scale=1.0) == 120.0,
              "(11) бюджет вызова живёт в СЕКУНДАХ (scale=1), а не в минутах"))

# ═══ (12) ЗАКРЫТИЕ ═══
print("\n(12) закрытие: только доказанным фактом, и оно цитирует ПК дословно")
back = facts(pc=pc_fact(last=NOW - 60, line=PC_BACK.strip()), bridge=br_fact())
res.append(ok(E.closures(back, C, ["o4|%d" % LAST_TRACE]) == ["o4|%d" % LAST_TRACE],
              "(12) свежий след закрывает эпизод ПК"))
ct = E.render_close("o4|%d" % LAST_TRACE, "VPS", "ПК о себе говорит так: «%s»" % PC_BACK.strip())
print("      ЗАКРЫТИЕ: %s" % ct[:150])
res.append(ok("лежал 19 ч 45 м" in ct,
              "(12) диагноз ПК уезжает ДОСЛОВНО, а не пересказом"))
res.append(ok(E.closures(facts(pc=pc_fact(last=NOW - 20 * HOUR), bridge=br_fact()), C,
                         ["o4|%d" % LAST_TRACE]) == [],
              "(12) пока молчание длится, закрывать нечего"))

# ═══ (13) РУКИ ═══
print("\n(13) руки: составной факт, история переживает прогон, журнал читается у порога досрочно")
try:
    import types

    import expectations_run as ER

    calls = []

    class _FakeBC:
        def __init__(self, timeout=None):
            pass

        def _call(self, action, **kw):
            calls.append((action, kw))
            return {"ok": True, "text": PC_HEAD}

    fake = types.ModuleType("bridge_client")
    fake.BridgeClient = _FakeBC
    real = sys.modules.get("bridge_client")
    sys.modules["bridge_client"] = fake
    try:
        # проба удалась → last_ok/last_fast запоминаются; проба провалилась → история цела
        st13 = {}
        f13 = ER.bridge_facts({"ok": True, "dt": 2.1, "probed": True}, st13, NOW)
        res.append(ok(f13["ok"] is True and f13["last_ok"] is None,
                      "(13) первый прогон: успех есть, истории ещё нет"))
        ER.remember_bridge(st13, {"bridge": f13}, NOW, C)
        res.append(ok(st13["bridge"]["last_ok"] == NOW and st13["bridge"]["last_fast"] == NOW,
                      "(13) успех в бюджете двигает ОБА следа"))
        ER.remember_bridge(st13, {"bridge": {"ok": True, "dt": 300.0}}, NOW + 60, C)
        res.append(ok(st13["bridge"]["last_ok"] == NOW + 60 and st13["bridge"]["last_fast"] == NOW,
                      "(13) медленный успех двигает last_ok, но НЕ last_fast"))
        f13b = ER.bridge_facts({"ok": False, "dt": 45.0, "probed": True, "err": "HTTP 302"},
                               st13, NOW + 120)
        res.append(ok(f13b["ok"] is False and f13b["last_ok"] == NOW + 60,
                      "(13) отказ истории не стирает — по ней и считается возраст"))
        f13c = ER.bridge_facts({"ok": False, "probed": False, "err": "клиент не собрался"},
                               st13, NOW + 120)
        res.append(ok(f13c["ok"] is None,
                      "(13) «пробы не было» отличается от «проба провалилась» в самом факте"))

        # журнал ПК: кэш держит час, но у порога читается КАЖДЫЙ прогон
        calls[:] = []
        st13["pc"] = {"ok": True, "fetched": NOW - 300, "last": NOW - 3 * HOUR, "line": "x"}
        p1 = ER.pc_facts(st13, NOW, C)
        res.append(ok(p1.get("cached") is True and calls == [],
                      "(13) свежий кэш вдали от порога — моста не тревожим"))
        st13["pc"] = {"ok": True, "fetched": NOW - 300, "last": NOW - 15.9 * HOUR, "line": "x"}
        p2 = ER.pc_facts(st13, NOW, C)
        res.append(ok(p2.get("cached") is False and calls == [("read_doc", {"name": "cowork_log"})],
                      "(13) у порога журнал перечитывается досрочно: %s" % calls))
        res.append(ok(p2.get("last") == LAST_TRACE and p2.get("fetched") == NOW,
                      "(13) прочитанный факт несёт и след, и время своего чтения"))
        calls[:] = []
        st13["pc"] = {"ok": False, "fetched": 0, "last": None}
        ER.pc_facts(st13, NOW, C)
        res.append(ok(len(calls) == 1, "(13) прошлое чтение провалилось → пробуем сразу, не через час"))
        # ОТКАТ ГАСИТ ЧТЕНИЕ, КОГДА ВЫКЛЮЧЕНЫ ВСЕ ПОТРЕБИТЕЛИ ЖУРНАЛА. С 18.08.2026 их двое:
        # О4 (следа нет вовсе) и О6 (взятая задача без записи об исходе) — одно чтение кормит оба.
        # Поэтому EXPECT_PC_MIN=0 в одиночку чтение НЕ гасит: иначе откат О4 молча убил бы О6.
        # Предмет проверки прежний — откат не платит мосту НИ ОДНОГО вызова.
        calls[:] = []
        ER.pc_facts({}, NOW, cfg(pc=0, pc_task=0))
        res.append(ok(calls == [], "(13) ОТКАТ: при EXPECT_PC_MIN=0 И EXPECT_PC_TASK_MIN=0 "
                                   "моста не зовём вовсе"))
        calls[:] = []
        ER.pc_facts({}, NOW, cfg(pc=0))
        res.append(ok(len(calls) == 1, "(13) а при выключенном ТОЛЬКО О4 журнал читает О6"))
    finally:
        if real is not None:
            sys.modules["bridge_client"] = real
        else:
            sys.modules.pop("bridge_client", None)
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(13) руки")] * 10

# ═══ (14) ЖИВОЙ ФОРМАТ ЗАПУСКА ═══
print("\n(14) живой формат запуска: точка входа таймера, ничего не тронуто и не отправлено")
try:
    import expectations_run as ER

    os.environ["CC_EXPECT_DIR"] = "/tmp/cc_expect_test_pcbridge"

    def pids():
        out = {}
        for unit, entry in (("orchestrator-daemon", "orchestrator_daemon.py"),
                            ("splinter", "bot.py")):
            p = ER._proc(unit, entry)
            out[unit] = (p or {}).get("pid")
        return out

    before = pids()
    sent = []
    _n, _e, _q = ER.send_note, ER.enqueue_escalation, ER.queue_facts
    ER.send_note = lambda t: (sent.append(t), True)[1]
    ER.enqueue_escalation = lambda v: sent.append(("task", v)) or 0
    # Сеть в гейте не дёргаем: проба «не поставлена» — она же законный третий исход.
    ER.queue_facts = lambda: {"ok": False, "rows": [], "dt": None, "probed": False,
                              "err": "тест: моста не спрашиваем"}
    try:
        out14 = ER.run(dry=True)
        sn = ER.snapshot(NOW, {}, C)
    finally:
        ER.send_note, ER.enqueue_escalation, ER.queue_facts = _n, _e, _q
    after = pids()
    # ЖИВОЙ ФОРМАТ — не «похожий вызов», а ТОТ САМЫЙ: что запускает таймер владельца.
    unit = open(os.path.join(REPO, "deploy", "expectations.service"), encoding="utf-8").read()
    res.append(ok("expectations_run.py" in unit and "--dry" not in unit,
                  "(14) таймер запускает именно этот файл и БЕЗ --dry (боевой прогон говорит)"))
    res.append(ok(before == after and any(before.values()),
                  "(14) PID живых процессов не сменились: %s" % before))
    res.append(ok(sent == [], "(14) в канал не ушло ничего"))
    res.append(ok(out14.get("tasks") == [], "(14) задач не поставлено"))
    res.append(ok(not [k for k in out14.get("notes", []) if str(k).startswith(("o4|", "o5"))],
                  "(14) при непоставленной пробе об О4/О5 не заявлено ничего"))
    res.append(ok(isinstance(sn.get("bridge"), dict) and isinstance(sn.get("pc"), dict),
                  "(14) снимок несёт оба новых факта"))
    res.append(ok(sn["pc"].get("ok") is False and "мост не ответил" in str(sn["pc"].get("err")),
                  "(14) мост молчит → журнал ПК не читается вовсе, и это сказано"))
except Exception as e:                                                   # noqa: BLE001
    print("   ОШИБКА: %r" % e)
    res += [ok(False, "(14) живой прогон")] * 7

if len(res) != TOTAL_CHECKS:
    print("\nЗАМЕТКА: проверок стало %d вместо %d — поправь TOTAL_CHECKS, иначе прогон «до»"
          " и «после» будут считать разными знаменателями" % (len(res), TOTAL_CHECKS))
print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
