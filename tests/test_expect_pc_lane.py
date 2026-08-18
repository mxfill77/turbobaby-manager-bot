#!/usr/bin/env python3
"""О6 — «полоса ПК не движется по взятой задаче» (18.08.2026).

ПОВОД, ЖИВОЙ ФАКТ: 17.08 в 20:56 UTC полоса ПК взяла задачу #43, демона убила перезагрузка
Windows, и задача пролежала 10 ч 17 м. Сервер работал всё это время и не знал НИЧЕГО.

КОНТРАКТ НАБЛЮДЕНИЯ, все четыре части проверяются здесь:
  1. ОЖИДАЕМЫЙ РЕЗУЛЬТАТ — у взятой полосой ПК задачи появляется запись об исходе  (2, 4, 5)
  2. ИСТОЧНИК ИСТИНЫ  — общий журнал полосы ПК на Диске, ПО ИМЕНИ через реестр моста  (15)
  3. СПОСОБ          — судится ПОЯВЛЕНИЕ записи; не живость процесса, не тишина журнала,
                       не код ответа моста                                          (3, 9, 16)
  4. ОТРИЦАТЕЛЬНЫЕ ТЕСТЫ, оба обязательны:
       (а) журнал молчит, но взятой задачи нет  → тревоги НЕТ                        (3)
       (б) задача взята, записи нет дольше порога → тревога ЕСТЬ,
           воспроизведено на ЖИВОЙ хронологии 17–18.08                               (4)

ФИКСТУРЫ СНЯТЫ С ПРОДА, А НЕ ВЫДУМАНЫ: дословные строки `read_doc name=cowork_log`, снимок
18.08.2026 08:10 UTC (1230 строк, 428 968 знаков, окно 28.07 15:11 → 18.08 08:07; 220 взятий,
227 исходов: done 150 · failed 39 · needs_approval 38).

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение О6 живёт в том же доказанно безруком модуле
(2)  ЖИВЫЕ ФОРМЫ ЗАПИСЕЙ: взятие, исход, живые скобки «(сирота…)», «(approved)», «(одиночка)»
(3)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): журнал молчит, взятой задачи нет → тревоги НЕТ
(4)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): ЖИВАЯ хронология 17–18.08, задача #43 → тревога ЕСТЬ
(5)  ПОРОГ 210 мин одной ручкой: живые 39 мин и законные 103 мин молчат
(6)  НОМЕРА ПОВТОРЯЮТСЯ: ответ засчитывается ТОЛЬКО вперёд от взятия
(7)  ДВИЖЕНИЕ ДАЛЬШЕ закрывает эпизод: потерянная запись не становится вечной тревогой
(8)  ТРИ ИСХОДА: «проверить не удалось» — свой ответ, а не вежливое «движется»
(9)  ЗАМОК: канал не доказан живым в этом же прогоне → о полосе не говорим НИЧЕГО
(10) ФОРМА ЗАМЕТКИ: без кнопок, без номера, без «да»; причина не выдумывается
(11) ЗАДАЧИ У О6 НЕ БЫВАЕТ НИКОГДА; прибор ничего не чинит и не поднимает
(12) ОТКАТ: EXPECT_PC_TASK_MIN=0 → ветка мертва ДО разбора; обе ветки 0 → мост не зовётся
(13) ЗАКРЫТИЕ ЭПИЗОДА: только доказанным свежим чтением
(14) ГРОМКОСТЬ ОТДЕЛЕНА ОТ ВЕРДИКТА: адрес и отсрочка не трогают вердикт ни одним полем
(15) РУКИ: журнал открывается ПО ИМЕНИ, О6 не платит мосту своего вызова
(16) ЭТО НЕ ВТОРОЙ О4: на живом случае О4 молчит по устройству, О6 говорит
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
MIN = 60.0
HOUR = 3600.0

# ══════════════ ДОСЛОВНАЯ ЖИВАЯ ХРОНОЛОГИЯ 17–18.08.2026 (снимок 18.08 08:10 UTC) ═══════════
# Записи лежат новыми СВЕРХУ — ровно так, как их отдаёт мост.
LIVE_1718 = (
    "NOTE 2026-08-18 08:07 UTC: Orchestrator: взял задачу #47 (in_progress)  \n"
    "NOTE 2026-08-18 07:39 UTC: Orchestrator: вотчдог поднял moderation_bot (смерть 1/3, "
    "лежал 12 ч 10 м, PID 15760): moderation_bot запущен (PID 15760).  \n"
    "NOTE 2026-08-18 07:38 UTC: Orchestrator: задача #44 → done · Штамп занятости О2 переведён "
    "с поля `at` на mtime реестра — тот же предмет, что у верно отвечающего соседа.  \n"
    "DONE 2026-08-18 07:24 UTC: ARTIFACT задача 43 полосы ПК висела 10ч15м → "
    "docs/artifacts/2026-08-18-task43-stuck-diagnosis.md: демона PID 5540 убила двойная "
    "перезагрузка Windows на обновления 04:01/04:02 местного  \n"
    "NOTE 2026-08-18 07:13 UTC: Orchestrator: взял задачу #44 (in_progress)  \n"
    "NOTE 2026-08-18 07:13 UTC: Orchestrator: watchdog: поднял демон через schtasks "
    "(лежал 10 ч 19 м, подъём №1 за сутки, PID 21256)  \n"
    "NOTE 2026-08-18 07:13 UTC: Orchestrator: задача #43 (сирота, исполнителя нет) → failed "
    "через 36997с · ⏱ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=heartbeat_timeout]  \n"
    "NOTE 2026-08-17 20:56 UTC: Orchestrator: взял задачу #43 (in_progress)  \n"
    "NOTE 2026-08-17 20:27 UTC: Orchestrator: задача #41 → done · Committed as `a9599a3`. "
    "Прибор О2 крикнул «демон не даёт оборота», пока демон штатно исполнял задачу 40  \n"
    "NOTE 2026-08-17 20:06 UTC: Orchestrator: взял задачу #41 (in_progress)  \n"
    "NOTE 2026-08-17 19:37 UTC: Orchestrator: задача #40 → done · Сторож свежести записанного "
    "правила цены построен и закрыт полным гейтом  \n"
    "NOTE 2026-08-17 18:58 UTC: Orchestrator: взял задачу #40 (in_progress)  \n"
)
TOOK_43 = E.parse_iso("2026-08-17T20:56:00Z")      # взятие задачи #43
FAILED_43 = E.parse_iso("2026-08-18T07:13:00Z")    # реапер снял сироту
TOOK_47 = E.parse_iso("2026-08-18T08:07:00Z")

# Хвост той же хронологии ДО взятия #43 — им проверяется отрицательный тест (а).
LIVE_BEFORE_43 = LIVE_1718[LIVE_1718.index("NOTE 2026-08-17 20:27"):]


def cfg(**kw):
    c = E.config({})
    c.update(kw)
    return c


C = cfg()


def facts(text, now, fetched=None, bridge_dt=2.1, ok_read=True, **kw):
    """Снимок фактов ровно той формы, что собирают руки (`expectations_run.snapshot`)."""
    lane = E.pc_lane_facts(text, now) if text is not None else None
    open_ep = (lane or {}).get("open") or {}
    pc = {"ok": ok_read, "fetched": (now if fetched is None else fetched),
          "last": open_ep.get("since") if lane else None,
          "line": "", "n": 0, "lane": lane}
    pc.update(kw.pop("pc", {}))
    f = {"now": now, "pc": pc,
         "bridge": {"ok": True, "dt": bridge_dt, "last_ok": now, "last_fast": now}}
    f.update(kw)
    return f


def o6(text, now, **kw):
    """Только вердикты О6 — соседей отбрасываем, чтобы судить свой предмет."""
    return [v for v in E.verdict(facts(text, now, **kw), kw.get("cfg") or C)
            if v.get("kind") == "o6_pc_task"]


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══
print("\n(1) граница устройством: решение О6 живёт в безруком модуле")
import ast

src = open(os.path.join(REPO, "expectations.py")).read()
tree = ast.parse(src)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(a.name.split(".")[0] for a in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module.split(".")[0])
res.append(ok(imports == {"datetime", "re"},
              "(1) импортов по-прежнему ровно два (%s) — ни сети, ни файлов, ни моста"
              % ", ".join(sorted(imports))))
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
res.append(ok(not ({"open", "exec", "eval", "compile"} & names),
              "(1) в модуле нет ни open, ни exec — прочитать журнал он не может сам"))
res.append(ok("o6_pc_task" in E.KINDS and E._o6 in (E._o6,),
              "(1) вид объявлен в KINDS — журнал и адрес узнают его по имени"))

# ═══ (2) ЖИВЫЕ ФОРМЫ ЗАПИСЕЙ ═══
print("\n(2) живые формы: взятие, исход, живые скобки")
lane = E.pc_lane_facts(LIVE_1718, TOOK_47 + 60)
res.append(ok(lane["takes"] == 5,
              "(2) взятий в живой хронологии 5: #40, #41, #43, #44, #47"))
res.append(ok(lane["open"] and lane["open"]["num"] == 47,
              "(2) открытой числится последняя взятая — #47"))
res.append(ok(lane["answers"] == 4,
              "(2) ответов засчитано 4 (#40, #41, #43-сирота, #44)"))
# Живые скобки между номером и стрелкой — все три вида из корпуса.
for brack, num, word in (("(сирота, исполнителя нет) ", 43, "failed"),
                         ("(approved) ", 55, "done"),
                         ("(одиночка) ", 61, "failed"),
                         ("", 70, "needs_approval")):
    line = ("NOTE 2026-08-17 10:00 UTC: Orchestrator: взял задачу #%d (in_progress)\n"
            "NOTE 2026-08-17 10:30 UTC: Orchestrator: задача #%d %s→ %s · хвост\n"
            % (num, num, brack, word))
    l2 = E.pc_lane_facts(line, E.parse_iso("2026-08-17T11:00:00Z"))
    res.append(ok(l2["open"] is None and l2["answers"] == 1,
                  "(2) исход «%s→ %s» прочитан как ответ полосы" % (brack or "без скобки ", word)))
res.append(ok(E.PC_ANSWERS == ("done", "failed", "needs_approval"),
              "(2) три слова корпуса названы; незнакомое слово тоже засчитывается ответом"))
weird = E.pc_lane_facts(
    "NOTE 2026-08-17 10:00 UTC: Orchestrator: взял задачу #9 (in_progress)\n"
    "NOTE 2026-08-17 10:30 UTC: Orchestrator: задача #9 → отозвана · владелец снял\n",
    E.parse_iso("2026-08-17T20:00:00Z"))
res.append(ok(weird["open"] is None,
              "(2) незнакомое слово исхода — ответ (fail-safe слоя в сторону МОЛЧАНИЯ)"))

# ═══ (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а) ═══
print("\n(3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): журнал молчит, взятой задачи нет → тревоги НЕТ")
# Живой хвост: последняя запись — ответ по #41, взятой задачи нет. Молчим сутки, трое, неделю.
for wait_h in (1, 6, 12, 24, 72, 168):
    now = E.parse_iso("2026-08-17T20:27:00Z") + wait_h * HOUR
    v = o6(LIVE_BEFORE_43, now)
    res.append(ok(not v, "(3) полоса молчит %d ч без взятой задачи → тревоги нет" % wait_h))
st, info = E.pc_task_state(facts(LIVE_BEFORE_43, E.parse_iso("2026-08-24T20:27:00Z")), C,
                           E.parse_iso("2026-08-24T20:27:00Z"))
res.append(ok(st == E.PCT_MOVING and "не давали работы" in info.get("why", ""),
              "(3) состояние названо прямо: «ни одной взятой задачи — полосе не давали работы»"))
empty = o6("NOTE 2026-08-17 10:00 UTC: Orchestrator: ревизор: 0 окон с активностью\n",
           E.parse_iso("2026-08-19T10:00:00Z"))
res.append(ok(not empty, "(3) журнал без единого взятия за двое суток тревоги не даёт"))

# ═══ (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б) — ЖИВАЯ ХРОНОЛОГИЯ ═══
print("\n(4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): живой случай #43 17–18.08 → тревога ЕСТЬ")
# Журнал в тот момент обрывался взятием #43: всё, что ниже, ещё не написано.
STUCK_TEXT = LIVE_1718[LIVE_1718.index("NOTE 2026-08-17 20:56"):]
at_thr = TOOK_43 + C["pc_task"]
res.append(ok(not o6(STUCK_TEXT, at_thr - 60),
              "(4) за минуту ДО порога прибор молчит"))
v4 = o6(STUCK_TEXT, at_thr + 60)
res.append(ok(len(v4) == 1, "(4) через минуту ПОСЛЕ порога прибор говорит"))
if v4:
    v = v4[0]
    res.append(ok(v["pc_task_id"] == 43, "(4) названа именно задача #43"))
    res.append(ok(v["key"] == "o6|43|%d" % int(TOOK_43),
                  "(4) эпизод ключуется ВЗЯТИЕМ — перевзятие даст другой ключ"))
    res.append(ok(abs(v["age"] - (C["pc_task"] + 60)) < 1.5,
                  "(4) возраст считается от НАСТОЯЩЕГО взятия, а не от момента, когда узнали"))
# Живая точка гибели: 10 ч 17 м молчания
dead = o6(STUCK_TEXT, FAILED_43)
res.append(ok(len(dead) == 1 and abs(dead[0]["age"] - 37020) < 120,
              "(4) на живой точке 18.08 07:13 нарушение идёт 10 ч 17 м"))
res.append(ok(dead and dead[0]["age"] > 10 * HOUR,
              "(4) прибор объявил бы это за 6 ч 47 м ДО вотчдога (порог 3 ч 30 мин)"))
# И тем же живым текстом — эпизод ЗАКРЫВАЕТСЯ, когда реапер написал свой исход.
after = o6(LIVE_1718, FAILED_43 + 60)
res.append(ok(not [x for x in after if x["pc_task_id"] == 43],
              "(4) запись «#43 (сирота…) → failed» нарушение снимает"))

# ═══ (5) ПОРОГ ═══
print("\n(5) порог 210 мин одной ручкой; живые 39 мин и законные 103 мин молчат")
res.append(ok(E.PC_TASK_DEFAULT == 210.0 and E.PC_TASK_ENV == "EXPECT_PC_TASK_MIN",
              "(5) ручка одна: EXPECT_PC_TASK_MIN, дефолт 210 мин"))
res.append(ok(C["pc_task"] == 210 * MIN, "(5) config отдаёт порог в секундах"))
res.append(ok(E.PC_TASK_DEFAULT >= 90.0, "(5) пол владельца «не меньше 90 минут» соблюдён"))
# Живая законная работа: #40 шла 39 минут (17.08 18:58 → 19:37).
took40 = E.parse_iso("2026-08-17T18:58:00Z")
t40 = LIVE_1718[LIVE_1718.index("NOTE 2026-08-17 19:37"):]
res.append(ok(not o6(t40, took40 + 39 * MIN + 1),
              "(5) живая законная работа 39 мин (#40) тревоги не даёт"))
# Самая длинная ЗАКОННАЯ занятость корпуса: 103 мин, закрытая СВОИМ предохранителем ПК.
long_ok = ("NOTE 2026-07-30 14:24 UTC: Orchestrator: задача #61 (одиночка) → failed по "
           "ПК-таймауту (6169с) · ⏱ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА\n"
           "NOTE 2026-07-30 12:41 UTC: Orchestrator: взял задачу #61 (in_progress)\n")
took61 = E.parse_iso("2026-07-30T12:41:00Z")
res.append(ok(not o6(long_ok[long_ok.index("NOTE 2026-07-30 12:41"):], took61 + 103 * MIN),
              "(5) 103 мин — ПК ещё успевает закрыть задачу САМ, прибор молчит"))
res.append(ok(bool(o6(long_ok[long_ok.index("NOTE 2026-07-30 12:41"):], took61 + 211 * MIN)),
              "(5) а на 211-й минуте уже говорит"))
c90 = cfg(pc_task=90 * MIN)
res.append(ok(bool([v for v in E.verdict(facts(long_ok[long_ok.index("NOTE 2026-07-30 12:41"):],
                                               took61 + 103 * MIN), c90)
                    if v["kind"] == "o6_pc_task"]),
              "(5) ПОЧЕМУ НЕ 90: задача, которую ПК закрывает СВОИМ таймаутом на 103-й минуте, "
              "при пороге 90 успела бы стать тревогой — порог обгонял бы предохранитель ПК"))
res.append(ok(E.limit_env("EXPECT_PC_TASK_MIN", 210.0, {"EXPECT_PC_TASK_MIN": "45"}) == 45 * MIN,
              "(5) ручка читается из окружения"))

# ═══ (6) НОМЕРА ПОВТОРЯЮТСЯ ═══
print("\n(6) номера повторяются: ответ засчитывается ТОЛЬКО вперёд от взятия")
# Живой случай: #43 закрывалась 15.08 за 16 минут, и это НЕ ответ взятию 17.08.
reuse = ("NOTE 2026-08-17 20:56 UTC: Orchestrator: взял задачу #43 (in_progress)\n"
         "NOTE 2026-08-15 18:24 UTC: Orchestrator: задача #43 → done · Опись выполнена\n"
         "NOTE 2026-08-15 18:08 UTC: Orchestrator: взял задачу #43 (in_progress)\n")
v6 = o6(reuse, TOOK_43 + 4 * HOUR)
res.append(ok(len(v6) == 1 and v6[0]["pc_task_id"] == 43,
              "(6) прошлый ответ по тому же номеру нарушения НЕ снимает"))
lane6 = E.pc_lane_facts(reuse, TOOK_43 + 4 * HOUR)
res.append(ok(lane6["takes"] == 2 and lane6["answers"] == 1,
              "(6) взятий 2, ответ засчитан РОВНО одному — раннему"))
# Обратная ловушка: наивная сверка «по номеру» дала бы 18 суток из воздуха (живой #44).
naive = ("NOTE 2026-08-18 07:38 UTC: Orchestrator: задача #44 → done · хвост\n"
         "NOTE 2026-08-18 07:13 UTC: Orchestrator: взял задачу #44 (in_progress)\n"
         "NOTE 2026-07-29 18:24 UTC: Orchestrator: взял задачу #44 (in_progress)\n")
lane6b = E.pc_lane_facts(naive, E.parse_iso("2026-08-18T08:00:00Z"))
res.append(ok(lane6b["open"] is None and lane6b["lost"] == 1,
              "(6) взятие 29.07 закрыто ПЕРЕвзятием, а не ответом 18 суток спустя"))

# ═══ (7) ДВИЖЕНИЕ ДАЛЬШЕ ═══
print("\n(7) полоса ушла дальше → эпизод закрыт, потерянная запись становится числом")
# Живые #3 и #22 (17.08): записи об исходе нет вовсе, но полоса взяла следом два десятка задач.
lost_case = ("NOTE 2026-08-17 08:22 UTC: Orchestrator: взял задачу #6 (in_progress)\n"
             "NOTE 2026-08-17 07:20 UTC: Orchestrator: взял задачу #3 (in_progress)\n")
v7 = o6(lost_case, E.parse_iso("2026-08-18T08:00:00Z"))
res.append(ok([x["pc_task_id"] for x in v7] == [6],
              "(7) про #3 не говорим — полоса доказанно ушла дальше; открыт только #6"))
lane7 = E.pc_lane_facts(lost_case, E.parse_iso("2026-08-18T08:00:00Z"))
res.append(ok(lane7["lost"] == 1, "(7) пропавшая запись названа числом lost=1, а не тревогой"))
res.append(ok(lane7["closed"] and lane7["closed"][-1].get("moved_to") == 6,
              "(7) закрытие помнит, ЧЕМ закрылось — взятием #6"))
big = E.pc_lane_facts(LIVE_1718 * 30, TOOK_47 + 60)
res.append(ok(len(big["closed"]) <= E.CLOSED_KEEP,
              "(7) память о закрытых ограничена (%d) — состояние не станет копией журнала"
              % E.CLOSED_KEEP))
# Но если полоса ушла дальше НЕ БЫСТРО, эпизод всё равно был нарушением, пока длился.
slow_move = ("NOTE 2026-08-06 12:50 UTC: Orchestrator: взял задачу #377 (in_progress)\n"
             "NOTE 2026-08-05 17:00 UTC: Orchestrator: взял задачу #353 (in_progress)\n")
took353 = E.parse_iso("2026-08-05T17:00:00Z")
mid = o6(slow_move[slow_move.index("NOTE 2026-08-05 17:00"):], took353 + 6 * HOUR)
res.append(ok(len(mid) == 1 and mid[0]["pc_task_id"] == 353,
              "(7) живой случай 05.08: прибор кричал бы за 18 ч ДО вотчдога («лежал 19 ч 45 м»)"))

# ═══ (8) ТРИ ИСХОДА ═══
print("\n(8) три исхода: «проверить не удалось» — свой ответ, а не вежливое «движется»")
NOW8 = TOOK_43 + 5 * HOUR
bad = dict(facts(STUCK_TEXT, NOW8))
bad["pc"] = {"ok": False, "err": "HTTP 302", "fetched": 0, "lane": None}
st8, i8 = E.pc_task_state(bad, C, NOW8)
res.append(ok(st8 == E.PCT_UNKNOWN and "не прочитан" in i8["why"],
              "(8) журнал не прочитан → НЕИЗВЕСТНО"))
res.append(ok(not [v for v in E.verdict(bad, C) if v["kind"] == "o6_pc_task"],
              "(8) и молчание: «не знаю» тревогой не становится"))
stale = facts(STUCK_TEXT, NOW8, fetched=NOW8 - 40 * MIN)
st8b, i8b = E.pc_task_state(stale, C, NOW8)
res.append(ok(st8b == E.PCT_UNKNOWN and "устарел" in i8b["why"],
              "(8) срез старше EXPECT_PC_FRESH_MIN → НЕИЗВЕСТНО (полоса могла ответить после)"))
noparse = facts(None, NOW8)
st8c, i8c = E.pc_task_state(noparse, C, NOW8)
res.append(ok(st8c == E.PCT_UNKNOWN and "не разобран" in i8c["why"],
              "(8) журнал не разобран → НЕИЗВЕСТНО"))
res.append(ok({E.PCT_MOVING, E.PCT_STUCK, E.PCT_UNKNOWN}
              == {"движется", "не движется", "проверить не удалось"},
              "(8) исходы названы СЛОВАМИ владельца, а не булевым флагом"))

# ═══ (9) ЗАМОК КАНАЛА ═══
print("\n(9) канал не доказан живым в этом же прогоне → о полосе не говорим НИЧЕГО")
blind = facts(STUCK_TEXT, NOW8)
blind["bridge"] = {"ok": False, "err": "timeout", "last_ok": NOW8 - 90 * MIN, "probed": True}
res.append(ok(not [v for v in E.verdict(blind, C) if v["kind"] == "o6_pc_task"],
              "(9) мост не ответил → О6 молчит (о самом канале скажет О5)"))
res.append(ok(bool([v for v in E.verdict(blind, C) if v["kind"] == "o5_bridge_down"]),
              "(9) слепота наблюдателя сама становится событием, а не пустотой"))

# ═══ (10) ФОРМА ЗАМЕТКИ ═══
print("\n(10) форма заметки: без кнопок, без номера карточки, без «да»")
note = E.render(dead[0], "VPS") if dead else ""
res.append(ok("#43" in note and "3 ч 30 мин" in note,
              "(10) заметка называет задачу и порог"))
for banned in ("✅", "❌", "подтверд", "нажми", "кнопк", "approve"):
    res.append(ok(banned not in note.lower(), "(10) в заметке нет «%s»" % banned))
res.append(ok("не гадаю" in note and "не буду" in note,
              "(10) причина НЕ выдумывается: «выключен/завис/без интернета» отсюда неразличимы"))
res.append(ok(E.TAIL in note, "(10) граница владельца названа в самом сообщении"))
res.append(ok("умер" not in note.lower(), "(10) слова «ПК умер» нет — с сервера это недоказуемо"))
close_txt = E.render_close("o6|43|%d" % int(TOOK_43), "VPS", "полоса о ней говорит так: «…»")
res.append(ok("#43" in close_txt, "(10) закрытие называет ту же задачу номером"))

# ═══ (11) ЗАДАЧИ НЕ БЫВАЕТ ═══
print("\n(11) задачи у О6 не бывает никогда; прибор ничего не чинит")
res.append(ok(all(v.get("can_task") is False for v in (dead + v4 + mid)),
              "(11) can_task=False во всех ветках"))
o6_src = src[src.index("def _o6("):src.index("def _o5(")]
for banned in ("restart", "systemctl", "enqueue", "kill", "start"):
    res.append(ok(banned not in o6_src,
                  "(11) в решении О6 нет слова «%s» — оно меняет только информационное "
                  "состояние" % banned))

# ═══ (12) ОТКАТ ═══
print("\n(12) откат: EXPECT_PC_TASK_MIN=0 → ветка мертва ДО разбора")
c0 = cfg(pc_task=0.0)
res.append(ok(not [v for v in E.verdict(facts(STUCK_TEXT, NOW8), c0) if v["kind"] == "o6_pc_task"],
              "(12) при пороге 0 вердикта нет"))
st12, i12 = E.pc_task_state(facts(STUCK_TEXT, NOW8), c0, NOW8)
res.append(ok(st12 == E.PCT_UNKNOWN and "выключен" in i12["why"],
              "(12) выключенная ветка говорит «выключена», а не «движется»"))
res.append(ok(E.config({"EXPECT_PC_TASK_MIN": "0"})["pc_task"] == 0.0,
              "(12) ноль в окружении значим — им ветка и выключается"))
# Соседей откат не задевает: О4 при том же снимке живёт своей жизнью.
long_silence = facts(STUCK_TEXT, TOOK_43 + 20 * HOUR)
long_silence["pc"]["last"] = TOOK_43
res.append(ok(bool([v for v in E.verdict(long_silence, c0) if v["kind"] == "o4_pc_silent"]),
              "(12) откат О6 не гасит О4"))

# ═══ (13) ЗАКРЫТИЕ ЭПИЗОДА ═══
print("\n(13) закрытие эпизода — только доказанным свежим чтением")
key43 = "o6|43|%d" % int(TOOK_43)
res.append(ok(key43 in E.closures(facts(LIVE_1718, FAILED_43 + 60), C, [key43]),
              "(13) ответ полосы прочитан → эпизод закрыт"))
res.append(ok(key43 not in E.closures(bad, C, [key43]),
              "(13) журнал не прочитан → эпизод НЕ закрывается: молчание источника не выздоровление"))
res.append(ok(key43 not in E.closures(stale, C, [key43]),
              "(13) устаревший срез эпизода тоже не закрывает"))
res.append(ok(key43 not in E.closures(facts(STUCK_TEXT, TOOK_43 + 9 * HOUR), C, [key43]),
              "(13) пока задача стоит, закрывать нечего"))

# ═══ (14) ГРОМКОСТЬ ОТДЕЛЕНА ОТ ВЕРДИКТА ═══
print("\n(14) громкость отделена от вердикта")
import expect_journal as J

v14 = dead[0]
loud = J.address(v14, facts(STUCK_TEXT, FAILED_43), held=10 * HOUR, defer=HOUR,
                 frozen_client=False)
quiet = J.address(v14, facts(STUCK_TEXT, FAILED_43), held=5 * MIN, defer=HOUR,
                  frozen_client=False)
res.append(ok(loud[0] == J.BRAIN_AND_OWNER, "(14) переживший отсрочку тяжёлый — владельцу"))
res.append(ok(quiet[0] == J.BRAIN and "отсрочку ещё не пережило" in quiet[1],
              "(14) погасший быстрее отсрочки владельцу не показывается…"))
res.append(ok(J.line(v14, "VPS", TOOK_43, FAILED_43, "закрыт", 62, "", num="").count("О6") == 1,
              "(14) …но в счёт входит: строка эпизода уходит в мозг ВСЕГДА"))
jline = J.line(v14, "VPS", TOOK_43, FAILED_43, "закрыт", 62, "",
               num=J.number(v14))
res.append(ok("#43" in jline and "10 ч 17 мин" in jline,
              "(14) число замера называет задачу и длительность: %s" % jline[:90]))
frozen_addr = J.address(v14, None, held=10 * HOUR, defer=HOUR, frozen_client=True)
res.append(ok(frozen_addr[0] == J.BRAIN and "ЗАМОРОЖЕН" in frozen_addr[1],
              "(14) при замороженном контуре — в мозг, тем же правилом, что у О4"))
before = dict(v14)
J.address(v14, facts(STUCK_TEXT, FAILED_43), held=0, defer=HOUR, frozen_client=True)
res.append(ok(before == v14, "(14) выбор адреса не тронул вердикт НИ ОДНИМ полем"))

# ═══ (15) РУКИ ═══
print("\n(15) руки: журнал открывается ПО ИМЕНИ, О6 не платит мосту своего вызова")
try:
    import types

    import expectations_run as ER

    calls = []

    class _FakeBC:
        def __init__(self, timeout=None):
            pass

        def _call(self, action, **kw):
            calls.append((action, kw))
            return {"ok": True, "text": STUCK_TEXT}

    fake = types.ModuleType("bridge_client")
    fake.BridgeClient = _FakeBC
    real = sys.modules.get("bridge_client")
    sys.modules["bridge_client"] = fake
    try:
        st = {}
        p = ER.pc_facts(st, TOOK_43 + 30 * MIN, C)
        res.append(ok(len(calls) == 1 and calls[0][0] == "read_doc"
                      and calls[0][1] == {"name": "cowork_log"},
                      "(15) журнал открыт ПО ИМЕНИ через реестр моста, id не хардкодится"))
        res.append(ok(p["lane"]["open"]["num"] == 43 and p["last"] is not None,
                      "(15) ОДНО чтение кормит оба ожидания: и О4, и О6"))
        # Кэш: пока задача далеко от порога — мосту не платится ничего.
        st["pc"] = {k: p.get(k) for k in ("ok", "fetched", "last", "line", "n", "lane")}
        calls[:] = []
        ER.pc_facts(st, TOOK_43 + 40 * MIN, C)
        res.append(ok(not calls, "(15) вдали от порога — ноль обращений к мосту"))
        # У порога — читаем каждый прогон, чтобы заявление стояло на свежем чтении.
        ER.pc_facts(st, TOOK_43 + 200 * MIN, C)
        res.append(ok(len(calls) == 1, "(15) у порога (limit − fresh) читаем досрочно"))
        # Ветки выключены → журнал не читается вовсе. ЧИТАТЕЛЕЙ У НЕГО СТАЛО ТРИ (18.08.2026:
        # О7 о детях контура читает ТОТ ЖЕ текст ТЕМ ЖЕ вызовом), поэтому молчание мосту
        # покупает только их ОБЩИЙ откат — предмет проверки прежний, знаменатель честный.
        calls[:] = []
        ER.pc_facts({}, TOOK_43, cfg(pc=0.0, pc_task=0.0, pc_child=0.0))
        res.append(ok(not calls, "(15) все три порога 0 → мост не зовётся"))
        # Только О6 → журнал ВСЁ РАВНО читается (иначе откат О4 молча убил бы О6).
        calls[:] = []
        ER.pc_facts({}, TOOK_43, cfg(pc=0.0))
        res.append(ok(len(calls) == 1, "(15) при выключенном О4 журнал читает О6"))
        # Чем закрытие объясняет себя — словами самой полосы.
        # ЗАКРЫТИЕ ОБЪЯСНЯЕТ СЕБЯ СЛОВАМИ СВОЕЙ ЗАДАЧИ, А НЕ СОСЕДНЕЙ. В живом тексте последним
        # ответом лежит #44 от 07:38 — им объяснять закрытие #43 нельзя (это чужой диагноз).
        f15 = facts(LIVE_1718, FAILED_43 + 60)
        d = ER.close_detail(key43, f15)
        res.append(ok("сирота" in d and "#44" not in d,
                      "(15) закрытие цитирует СВОЮ задачу: %s" % d[:70]))
        took3 = E.parse_iso("2026-08-17T07:20:00Z")
        d2 = ER.close_detail("o6|3|%d" % int(took3),
                             facts(lost_case, E.parse_iso("2026-08-18T08:00:00Z")))
        res.append(ok("ушла дальше" in d2 and "#6" in d2,
                      "(15) а при потерянной записи честно говорит, чем именно закрылось"))
        res.append(ok(ER.close_detail("o6|999|1", f15) == "",
                      "(15) своих слов нет → молчим, чужих не подставляем"))
    finally:
        if real is not None:
            sys.modules["bridge_client"] = real
        else:
            sys.modules.pop("bridge_client", None)
except Exception as e:                                               # noqa: BLE001
    res.append(ok(False, "(15) руки: исключение %s" % e))

# ═══ (16) ЭТО НЕ ВТОРОЙ О4 ═══
print("\n(16) это не второй О4: на живом случае О4 молчит ПО УСТРОЙСТВУ")
f16 = facts(STUCK_TEXT, FAILED_43)
f16["pc"]["last"] = TOOK_43                       # последний след — само взятие #43
kinds = {v["kind"] for v in E.verdict(f16, C)}
res.append(ok("o6_pc_task" in kinds, "(16) О6 говорит: задача взята и не отвечена 10 ч 17 м"))
res.append(ok("o4_pc_silent" not in kinds,
              "(16) О4 молчит: 10 ч 17 м молчания против его порога 16 ч"))
res.append(ok(C["pc"] / HOUR == 16.0 and C["pc_task"] / HOUR < 4.0,
              "(16) пороги разные, потому что предметы разные: жизнь контура ≠ обязательство"))

print("\nИТОГО: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
