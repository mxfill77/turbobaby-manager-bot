#!/usr/bin/env python3
"""О8 — ПОЛОСА НЕ МОЖЕТ ВЫПОЛНИТЬ НИ ОДНОГО ЗАХОДА (18.08.2026). Регресс.

ПОВОД ДОСЛОВНЫЙ: 18.08 между 16:26 и 17:25 UTC заходы полосы падали внешним отказом, система
каждый раз честно говорила «нужна пауза до восстановления API» — и ждала бы вечно, потому что у
владельца был отключён способ оплаты. Ни одно действующее ожидание этого не видит: О4 молчит
(полоса ПИШЕТ в журнал), О6 молчит (заходы закрываются за 4–6 минут), О7 про детей.

ПРЕМИСА ПОВОДА ПРОВЕРЕНА ЖИВЫМ ЧТЕНИЕМ И ПОДТВЕРДИЛАСЬ НАПОЛОВИНУ. Снимок `read_doc
name=cowork_log` 18.08.2026 18:24 UTC (452 900 знаков, 1298 строк, окно 28.07 15:11 → 18.08
18:15 = 21.1 суток, 238 заходов с записью об исходе): в окне повода заходов ПЯТЬ, внешним
отказом упали ТРИ (#5, #9, #10), и ПОДРЯД они не шли — между ними полоса выполнила #7
(needs_approval) и #8 (done). «Четыре подряд» корпус не подтверждает, «один — обычная жизнь»
подтверждает прямо: все четыре одиночных отказа корпуса (29.07 ×2, 04.08, 05.08) полоса
пережила сама. Отсюда порог ДВА: при трёх не ловится ничего, включая сам повод.

ФИКСТУРЫ СНЯТЫ С ПРОДА, А НЕ ВЫДУМАНЫ — строки ниже дословны, включая формы отказа обеих
редакций производителя («Code-сессия завершена: API Error: …» и «claude exit=1: API Error: …»).

ОБА ОТРИЦАТЕЛЬНЫХ ТЕСТА КОНТРАКТА — секции (4) и (5), и оба обязательны.

(1)  ГРАНИЦА УСТРОЙСТВОМ: решение О8 живёт в том же доказанно безруком модуле
(2)  ЖИВАЯ ФОРМА: обе редакции отказа разбираются, текст берётся ДОСЛОВНО
(3)  ПОЗИЦИЯ: пересказ думателя о том же 529 отказом НЕ является
(4)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): заходы идут либо падают по РАЗНЫМ причинам → тревоги НЕТ
(5)  ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): N подряд с внешним отказом → тревога ЕСТЬ
(6)  ТРИ ИСХОДА: «проверить не удалось» не сливается ни со вторым, ни с первым
(7)  ПОРОГ ЧИСЛОМ: 2 ловит повод, 3 не ловит ничего; успех череду обрывает
(8)  ОКНО СВЕЖЕСТИ: старая череда нарушения НЕ рождает — историю не выкрикиваем
(9)  ДОСЛОВНЫЙ ТЕКСТ В ТЕЛЕ ТРЕВОГИ — обязателен, и своего суждения о причине в ней нет
(10) ГРАНИЦА: прибор не чинит и не ретраит — задачи не бывает НИКОГДА
(11) ЗАКРЫТИЕ: только ДОКАЗАННЫМ исполнением; молчание источника выздоровлением не считается
(12) ОТКАТ: EXPECT_LANE_RUN=0 → ветка мертва ДО чтения фактов
(13) ГРОМКОСТЬ ОТДЕЛЕНА ОТ ВЕРДИКТА: вес, адрес и число журнальной строки
(14) РУКИ: журнал читается ОДИН раз и кормит ЧЕТЫРЕ ожидания; своего вызова у О8 нет
(15) СОСЕДИ НЕ ЗАДЕТЫ: О4, О6 и О7 на тех же фактах отвечают как отвечали
"""
import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"

import expectations as E  # noqa: E402
import expect_journal as J  # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
HOUR = 3600.0
NOW = E.parse_iso("2026-08-18T17:30:00Z")            # семь минут после второго отказа подряд

# ── ДОСЛОВНЫЕ ЖИВЫЕ СТРОКИ (снимок 18.08.2026 18:24 UTC) ───────────────────────────────────
ERR529 = ("API Error: 529 Overloaded. This is a server-side issue, usually temporary — try "
          "again in a moment. If it persists, check https://status.claude.com.")
LIVE = "\n".join([
    "NOTE 2026-08-18 17:25 UTC: Orchestrator: задача #10 → failed (думатель: halt) · Причина "
    "провала — транзиентный серверный 529 Overloaded, а не дефект ТЗ (путь/имя/команда верны): "
    "переформулировка не лечит перегруз",
    "DONE 2026-08-18 17:23 UTC: ✅ Code-сессия завершена: " + ERR529,
    "NOTE 2026-08-18 17:20 UTC: Orchestrator: взял задачу #10 (in_progress)",
    "NOTE 2026-08-18 17:18 UTC: Orchestrator: задача #9 → failed (думатель: halt) · Провал — "
    "внешний серверный сбой claude 529 Overloaded, а не дефект формулировки ТЗ; переформулировкой "
    "не чинится, к тому же второй внешний провал подряд",
    "DONE 2026-08-18 17:15 UTC: ✅ Code-сессия завершена: " + ERR529,
    "NOTE 2026-08-18 17:12 UTC: Orchestrator: взял задачу #9 (in_progress)",
    "NOTE 2026-08-18 17:11 UTC: Orchestrator: терминал карточки #7: отказано · открыта 16:51 UTC, "
    "закрыта 17:11 UTC (20 мин) · объект: <секретный объект скрыт> · классы: env",
    "NOTE 2026-08-18 17:09 UTC: Orchestrator: задача #8 → done · Разведка read-only: тренажёр "
    "глазами менеджера. Артефакт создан, 8 пунктов отвечены фактами.",
    "NOTE 2026-08-18 16:53 UTC: Orchestrator: взял задачу #8 (in_progress)",
    "NOTE 2026-08-18 16:51 UTC: Orchestrator: задача #7 → needs_approval (красное, жду «да»)",
    "NOTE 2026-08-18 16:32 UTC: Orchestrator: взял задачу #7 (in_progress)",
    "NOTE 2026-08-18 16:30 UTC: Orchestrator: задача #5 → failed (думатель: halt) · Провал не от "
    "формулировки: claude exit=1 по API 529 Overloaded (серверная перегрузка Anthropic) — "
    "переформулировка ТЗ этого не чинит",
    "NOTE 2026-08-18 16:26 UTC: Orchestrator: взял задачу #5 (in_progress)",
])
# Историческая редакция: отказ лежит В САМОЙ строке исхода, строки «взял» в снимке нет вовсе.
OLD = "\n".join([
    "NOTE 2026-07-29 20:41 UTC: Orchestrator: задача #52 → failed · claude exit=1: " + ERR529,
    "NOTE 2026-07-29 19:58 UTC: Orchestrator: задача #51 → done · Разведка класса «ревизор ставит "
    "цепи, правящие клиентский контур» завершена — только чтение, ничего не менял.",
    "NOTE 2026-07-29 19:46 UTC: Orchestrator: задача #50 → failed · claude exit=1: API Error: "
    "Server error mid-response. The response above may be incomplete.",
])
# Падения по РАЗНЫМ причинам — внешнего отказа нет ни в одном (отрицательный тест контракта).
MIXED = "\n".join([
    "NOTE 2026-08-17 13:12 UTC: Orchestrator: задача #16 → failed · ⏱ провал [причина=run_timeout "
    "· таймаут прогона]: таймаут 2700s — headless прерван, задача не завершилась.",
    "NOTE 2026-08-17 12:20 UTC: Orchestrator: взял задачу #16 (in_progress)",
    "NOTE 2026-08-17 07:05 UTC: Orchestrator: задача #2 → failed (думатель: halt) · Ни одна пара "
    "не прогнана — исполнитель закрыл ход после подготовки; 0 коммитов и 0 записей журнала.",
    "NOTE 2026-08-17 06:31 UTC: Orchestrator: взял задачу #2 (in_progress)",
    "NOTE 2026-08-16 20:57 UTC: Orchestrator: задача #36 → failed · ⏱ НЕ ЗАКРЫТА, но В ОКНЕ "
    "ЗАДАЧИ ЕСТЬ РАБОТА [причина=approval_timeout · таймаут подтверждения]: подтверждение не "
    "получено за 46 мин — задача закрыта без «да».",
])
# Полоса работает штатно — так выглядит обычный день.
GOOD = "\n".join([
    "NOTE 2026-08-18 16:10 UTC: Orchestrator: задача #1 → done · Разведка read-only завершена.",
    "NOTE 2026-08-18 15:53 UTC: Orchestrator: взял задачу #1 (in_progress)",
    "NOTE 2026-08-18 15:51 UTC: Orchestrator: задача #76 → done · Прибор о детях научен судить.",
    "NOTE 2026-08-18 15:11 UTC: Orchestrator: взял задачу #76 (in_progress)",
])


def facts(text, now=NOW, fetched=None, bridge_ok=True, runs=True):
    """Факты в том виде, в каком их собирают руки (`expectations_run.pc_facts`)."""
    pc = {"ok": True, "fetched": now if fetched is None else fetched, "dt": 3.0,
          "last": now, "line": "", "n": 10,
          "lane": E.pc_lane_facts(text, now), "children": E.pc_children_facts(text, now)}
    if runs:
        pc["runs"] = E.pc_runs_facts(text, now)
    return {"now": now, "pc": pc,
            "bridge": {"ok": bridge_ok, "dt": 3.0, "err": "" if bridge_ok else "HTTP 302",
                       "last_ok": now if bridge_ok else now - 4 * HOUR,
                       "last_fast": now if bridge_ok else now - 4 * HOUR}}


C = E.config({})
C3 = dict(C, lane_run=3.0)                           # тот же корпус при пороге 3


def o8(f, cfg=None):
    return [v for v in E.verdict(f, cfg or C) if v.get("kind") == "o8_lane_dead"]


# ═══ (1) ГРАНИЦА УСТРОЙСТВОМ ═══════════════════════════════════════════════════════════════
print("\n(1) ГРАНИЦА: решение О8 не умеет ни ходить в мир, ни чинить")
src = open(os.path.join(REPO, "expectations.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = sorted({n.names[0].name.split(".")[0] for n in ast.walk(tree)
                  if isinstance(n, (ast.Import, ast.ImportFrom))
                  and isinstance(n, ast.Import)}
                 | {n.module.split(".")[0] for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom) and n.module})
res.append(ok(imports == ["datetime", "re"],
              "(1) импортов в модуле по-прежнему ровно два: %s" % imports))
fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
mine = ("lane_err", "pc_runs_facts", "lane_runs_state", "_o8")
called = set()
for name in mine:
    for n in ast.walk(fns[name]):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            called.add(n.func.id)
banned = {"open", "exec", "eval", "__import__", "compile", "input"}
res.append(ok(not (called & banned),
              "(1) ни open/exec/eval внутри веток О8 (зовётся: %d имён)" % len(called)))
res.append(ok(all(not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(fns[m]))
                  for m in mine),
              "(1) и ни одного импорта внутри них — мира эти функции не касаются"))

# ═══ (2) ЖИВАЯ ФОРМА ═══════════════════════════════════════════════════════════════════════
print("\n(2) ЖИВАЯ ФОРМА: обе редакции отказа, текст ДОСЛОВНО")
r = E.pc_runs_facts(LIVE, NOW)
res.append(ok(r["run"] == 2 and r["nums"] == [9, 10],
              "(2) редакция «Code-сессия завершена»: череда 2, задачи #9 и #10"))
res.append(ok(r["err"].startswith("529 Overloaded.") and "status.claude.com" in r["err"],
              "(2) текст отказа взят ДОСЛОВНО и целиком: «%s…»" % r["err"][:40]))
ro = E.pc_runs_facts(OLD, E.parse_iso("2026-07-29T21:00:00Z"))
res.append(ok(ro["total"] == 3 and ro["run"] == 1 and ro["nums"] == [52],
              "(2) историческая редакция «claude exit=1:» — отказ в САМОЙ строке исхода"))
res.append(ok([x["ext"] for x in ro["runs"]] == [True, False, True],
              "(2) и заход между ними (#51 → done) отказом не считается"))
res.append(ok(E.lane_err("DONE …: ✅ Code-сессия завершена: " + ERR529).startswith("529 Over")
              and E.lane_err("… → failed · claude exit=1: API Error: Server error mid-response.")
              == "Server error mid-response.",
              "(2) оба машинных зачина узнаются, хвост отдаётся без маркера"))

# ═══ (3) ПОЗИЦИЯ ═══════════════════════════════════════════════════════════════════════════
print("\n(3) ПОЗИЦИЯ: пересказ отказом не является")
res.append(ok(E.lane_err("NOTE …: Orchestrator: задача #5 → failed (думатель: halt) · Провал не "
                         "от формулировки: claude exit=1 по API 529 Overloaded") == "",
              "(3) слова думателя о том же 529 — пересказ, а не ответ системы"))
res.append(ok(E.lane_err("NOTE …: в журнале лежит строка «API Error: 529 Overloaded» — так "
                         "выглядит внешний отказ") == "",
              "(3) цитата формы в прозе отчёта отказом не становится"))
res.append(ok([x["num"] for x in r["runs"] if x["ext"]] == [9, 10],
              "(3) поэтому #5 (о нём говорит только думатель) в череду НЕ попал"))

# ═══ (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а) ════════════════════════════════════════════════════════════
print("\n(4) ОТРИЦАТЕЛЬНЫЙ (а): заходы идут либо падают по РАЗНЫМ причинам → тревоги НЕТ")
fg = facts(GOOD, E.parse_iso("2026-08-18T16:15:00Z"))
res.append(ok(E.lane_runs_state(fg, C, fg["now"])[0] == E.RUNS_OK and not o8(fg),
              "(4) полоса работает штатно → «идут», вердиктов О8 ноль"))
fm = facts(MIXED, E.parse_iso("2026-08-17T13:20:00Z"))
st, info = E.lane_runs_state(fm, C, fm["now"])
res.append(ok(st == E.RUNS_OK and info.get("run") == 0 and not o8(fm),
              "(4) три подряд провала РАЗНЫХ причин (таймаут прогона, halt, таймаут «да») → тишина"))
one = "\n".join(LIVE.splitlines()[3:])               # снимок на 17:19: отказ ровно один
f1 = facts(one, E.parse_iso("2026-08-18T17:19:00Z"))
st1, i1 = E.lane_runs_state(f1, C, f1["now"])
res.append(ok(st1 == E.RUNS_OK and i1.get("run") == 1 and not o8(f1),
              "(4) ОДИН внешний отказ — обычная жизнь: череда 1 при пороге 2, тревоги нет"))
ro_f = facts(OLD, E.parse_iso("2026-07-29T21:00:00Z"))
res.append(ok(not o8(ro_f),
              "(4) и в корпусе 29.07 (два отказа через успешный заход) тревоги нет"))

# ═══ (5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б) ════════════════════════════════════════════════════════════
print("\n(5) ОТРИЦАТЕЛЬНЫЙ (б): N подряд с внешним отказом → тревога ЕСТЬ")
f = facts(LIVE)
st, info = E.lane_runs_state(f, C, NOW)
vs = o8(f)
res.append(ok(st == E.RUNS_DEAD and len(vs) == 1, "(5) состояние «не идут», вердикт ровно один"))
v = vs[0] if vs else {}
res.append(ok(v.get("run") == 2 and v.get("nums") == [9, 10],
              "(5) в вердикте длина череды и номера упавших заходов"))
res.append(ok(str(v.get("key")) == "o8|%d" % int(E.parse_iso("2026-08-18T17:15:00Z")),
              "(5) ключ — ПЕРВЫЙ отказ череды: второй отказ второго эпизода не заводит"))
grown = "NOTE 2026-08-18 17:29 UTC: Orchestrator: задача #14 → failed · claude exit=1: " + ERR529 \
        + "\nNOTE 2026-08-18 17:27 UTC: Orchestrator: взял задачу #14 (in_progress)\n" + LIVE
fgr = facts(grown)
vgr = o8(fgr)
res.append(ok(len(vgr) == 1 and vgr[0]["run"] == 3 and vgr[0]["key"] == v.get("key"),
              "(5) третий отказ той же череды — тот же эпизод, длина 3"))

# ═══ (6) ТРИ ИСХОДА ════════════════════════════════════════════════════════════════════════
print("\n(6) ТРИ ИСХОДА: «проверить не удалось» — своё слово, а не вежливое «идут»")
res.append(ok(len({E.RUNS_OK, E.RUNS_DEAD, E.RUNS_UNKNOWN}) == 3,
              "(6) исходов ровно три и они различимы: %s / %s / %s"
              % (E.RUNS_OK, E.RUNS_DEAD, E.RUNS_UNKNOWN)))
bad = dict(facts(LIVE))
bad["pc"] = {"ok": False, "err": "мост ответил без ok"}
res.append(ok(E.lane_runs_state(bad, C, NOW)[0] == E.RUNS_UNKNOWN and not o8(bad),
              "(6) журнал не прочитан → «проверить не удалось», не «идут»"))
stale = facts(LIVE, fetched=NOW - 3600)
res.append(ok(E.lane_runs_state(stale, C, NOW)[0] == E.RUNS_UNKNOWN and not o8(stale),
              "(6) срез устарел (час) → тот же третий исход: полоса могла ответить после"))
legacy = facts(LIVE, runs=False)
res.append(ok(E.lane_runs_state(legacy, C, NOW)[0] == E.RUNS_UNKNOWN and not o8(legacy),
              "(6) записи прежней редакции (разбора нет) → третий исход, а не падение"))
empty = facts("NOTE 2026-08-18 17:00 UTC: ПУЛЬС · ПК · контур жив")
res.append(ok(E.lane_runs_state(empty, C, NOW)[0] == E.RUNS_UNKNOWN,
              "(6) ни одного захода в снимке → судить не на чем (полосе могли не давать работы)"))

# ═══ (7) ПОРОГ ЧИСЛОМ ══════════════════════════════════════════════════════════════════════
print("\n(7) ПОРОГ: 2 ловит повод, 3 не ловит ничего")
res.append(ok(C["lane_run"] == 2.0, "(7) дефолт порога — 2 захода подряд"))
res.append(ok(not o8(f, C3) and E.lane_runs_state(f, C3, NOW)[0] == E.RUNS_OK,
              "(7) при пороге 3 повод 18.08 НЕ ловится вовсе — потому и взято 2"))
res.append(ok(o8(fgr, C3) and o8(fgr, C3)[0]["run"] == 3,
              "(7) а череда из трёх ловится и порогом 3 — правило считает подряд, а не «всего»"))
broken = ("NOTE 2026-08-18 17:26 UTC: Orchestrator: задача #11 → done · работа сделана\n"
          "NOTE 2026-08-18 17:26 UTC: Orchestrator: взял задачу #11 (in_progress)\n") + LIVE
res.append(ok(not o8(facts(broken, E.parse_iso("2026-08-18T17:40:00Z"))),
              "(7) успешный заход ПОСЛЕ отказов обрывает череду — тревоги нет"))

# ═══ (8) ОКНО СВЕЖЕСТИ ═════════════════════════════════════════════════════════════════════
print("\n(8) ОКНО: старая череда нарушения не рождает — историю не выкрикиваем")
late = E.parse_iso("2026-08-19T01:00:00Z")           # +7 ч 37 мин от последнего отказа
fl = facts(LIVE, now=late)
st, info = E.lane_runs_state(fl, C, late)
res.append(ok(st == E.RUNS_UNKNOWN and not o8(fl) and "окна судейства" in (info.get("why") or ""),
              "(8) череда старше 6 ч → третий исход с названной причиной, а не тревога"))
near = E.parse_iso("2026-08-18T22:00:00Z")           # +4 ч 37 мин — ещё внутри окна
res.append(ok(o8(facts(LIVE, now=near)),
              "(8) внутри окна нарушение живо: молчание полосы его не отменяет"))
res.append(ok(C["lane_fresh"] == 6 * HOUR, "(8) окно — 6 ч (p90 пауз между заходами, 318 мин)"))

# ═══ (9) ДОСЛОВНЫЙ ТЕКСТ В ТЕЛЕ ════════════════════════════════════════════════════════════
print("\n(9) ТЕЛО ТРЕВОГИ: дословный ответ обязателен, своего суждения о причине нет")
note = E.render(v, "VPS")
res.append(ok(ERR529.split("API Error: ")[-1][:60] in note,
              "(9) дословный текст последней ошибки стоит в заметке"))
res.append(ok("status.claude.com" in note, "(9) и не обрезан на полуслове"))
res.append(ok("НЕ РАЗЛИЧИТЬ" in note and "не гадаю" in note,
              "(9) прибор прямо говорит, что перегрузку от денег не различает"))
res.append(ok("#9" in note and "#10" in note, "(9) названы номера упавших заходов"))
res.append(ok("2026-08-18 17:23:00 UTC" in note,
              "(9) время ответа АБСОЛЮТНОЕ — заметку читают позже её прогона"))
# СУДИМ СВОЙСТВО, А НЕ ПОДСТРОКУ: первая редакция этой проверки искала слово «да» и краснела на
# «захо-ДА» — ровно тот класс («решение по слову, а не по существу»), против которого заведены
# правила позиции. Заметка не ждёт ответа, если в ней нет ни маркера красного, ни кнопок, ни
# ссылки на номер карточки.
res.append(ok(E.NOTE_HEAD["o8_lane_dead"].startswith("🔔")
              and not any(t in note for t in ("NEEDS_APPROVAL", "✅", "❌", "карточк", "нажми",
                                              "подтверди")),
              "(9) заметка ленты: ни кнопок, ни номера карточки, ни просьбы подтвердить"))
res.append(ok(note.endswith(E.TAIL) and "не ретраю" in note,
              "(9) и заканчивается границей владельца"))

# ═══ (10) ГРАНИЦА: НИЧЕГО НЕ ЧИНИТ ═════════════════════════════════════════════════════════
print("\n(10) ГРАНИЦА: прибор не чинит и не ретраит")
res.append(ok(v.get("can_task") is False, "(10) can_task=False — задачи не бывает НИКОГДА"))
res.append(ok(not E.task_text(dict(v, can_task=True)),
              "(10) и текста задачи нет даже при подделанном флаге"))
res.append(ok("o8" not in str(E.TASK_HEAD % ("", "")) and "o8_lane_dead" not in E.TASK_BODY,
              "(10) вида О8 нет в шаблоне задачи-эскалации вовсе"))

# ═══ (11) ЗАКРЫТИЕ ═════════════════════════════════════════════════════════════════════════
print("\n(11) ЗАКРЫТИЕ: только ДОКАЗАННЫМ исполнением")
key = v.get("key")
res.append(ok(E.closures(f, C, [key]) == [],
              "(11) пока череда идёт — эпизод не закрывается"))
fixed = facts(broken, E.parse_iso("2026-08-18T17:40:00Z"))
res.append(ok(E.closures(fixed, C, [key]) == [key],
              "(11) полоса выполнила заход → закрыт (доказано свежим чтением журнала)"))
res.append(ok(E.closures(stale, C, [key]) == [] and E.closures(bad, C, [key]) == [],
              "(11) устаревший срез и непрочитанный журнал эпизода НЕ закрывают"))
res.append(ok(E.closures(fl, C, [key]) == [],
              "(11) и уход череды из окна — тоже: это незнание, а не выздоровление"))

# ═══ (12) ОТКАТ ════════════════════════════════════════════════════════════════════════════
print("\n(12) ОТКАТ: EXPECT_LANE_RUN=0 → ветка мертва ДО чтения фактов")
C0 = E.config({"EXPECT_LANE_RUN": "0"})
res.append(ok(C0["lane_run"] == 0.0, "(12) ноль читается как ноль (парсер limit_env)"))
res.append(ok(E.lane_runs_state(f, C0, NOW)[0] == E.RUNS_UNKNOWN and not o8(f, C0),
              "(12) на ТЕХ ЖЕ фактах повода — ни одного вердикта О8"))
res.append(ok(E.closures(fixed, C0, [key]) == [],
              "(12) и закрытий тоже нет — ветка не живёт наполовину"))
others_on = sorted(x["kind"] for x in E.verdict(f, C0))
others_off = sorted(x["kind"] for x in E.verdict(f, C))
res.append(ok([k for k in others_off if k != "o8_lane_dead"] == others_on,
              "(12) прочие ожидания при откате отвечают БАЙТ-В-БАЙТ так же"))

# ═══ (13) ГРОМКОСТЬ ════════════════════════════════════════════════════════════════════════
print("\n(13) ГРОМКОСТЬ: вес, адрес и число журнальной строки")
heavy, why = J.heavy(v, f, frozen_client=True)
res.append(ok(heavy, "(13) вес ТЯЖЁЛЫЙ даже при замороженном контуре: %s" % why))
res.append(ok(J.address(v, f, held=2 * HOUR, defer=HOUR)[0] == J.BRAIN_AND_OWNER,
              "(13) переживший отсрочку идёт мозг+владелец"))
res.append(ok(J.address(v, f, held=5 * 60, defer=HOUR)[0] == J.BRAIN,
              "(13) а мгновенный (транзиент) — только в мозг: отсрочка и есть различитель"))
num = J.number(v)
res.append(ok("2" in num and "529 Overloaded" in num,
              "(13) число строки журнала несёт и длину череды, и ДОСЛОВНЫЙ ответ"))
res.append(ok(J.number({"kind": "o8_lane_dead"}) == J.NO_NUMBER,
              "(13) а без фактов честно говорит «число не записано», а не «0»"))
line = J.line(v, "VPS", first=NOW - HOUR, now=NOW, phase="закрыт")
res.append(ok(line.startswith("ОЖИДАНИЕ О8") and "529 Overloaded" in line,
              "(13) строка ищется по «ОЖИДАНИЕ О8» и несёт ответ системы"))

# ═══ (14) РУКИ ═════════════════════════════════════════════════════════════════════════════
print("\n(14) РУКИ: журнал читается ОДИН раз и кормит ЧЕТЫРЕ ожидания")
import expectations_run as R  # noqa: E402

calls = {"n": 0}


class _FakeBridge(object):
    def __init__(self, *a, **kw):
        pass

    def _call(self, action, **kw):
        calls["n"] += 1
        return {"ok": True, "text": LIVE}


import bridge_client  # noqa: E402
real = bridge_client.BridgeClient
bridge_client.BridgeClient = _FakeBridge
try:
    got = R.pc_facts({}, NOW, C)
    res.append(ok(calls["n"] == 1, "(14) на все четыре ожидания — РОВНО один вызов моста"))
    res.append(ok(isinstance(got.get("runs"), dict) and got["runs"]["run"] == 2,
                  "(14) разбор заходов приезжает тем же чтением"))
    res.append(ok(isinstance(got.get("children"), dict) and isinstance(got.get("lane"), dict),
                  "(14) и соседи (О6, О7) своих фактов не потеряли"))
    calls["n"] = 0
    off = dict(C, pc=0.0, pc_task=0.0, pc_child=0.0, lane_run=0.0)
    R.pc_facts({}, NOW, off)
    res.append(ok(calls["n"] == 0,
                  "(14) все четыре выключены → журнал не читается вовсе, мосту ноль вызовов"))
    calls["n"] = 0
    only8 = dict(C, pc=0.0, pc_task=0.0, pc_child=0.0)
    r8 = R.pc_facts({}, NOW, only8)
    res.append(ok(calls["n"] == 1 and (r8.get("runs") or {}).get("run") == 2,
                  "(14) один только О8 включён → журнал ЧИТАЕТСЯ (иначе он ослеп бы молча)"))
finally:
    bridge_client.BridgeClient = real
res.append(ok("run" in R._KEEP_V and "err" in R._KEEP_V,
              "(14) длина череды и текст ответа доезжают до строки журнала через _KEEP_V"))
res.append(ok("полоса снова выполнила заход" in R.close_detail(key, fixed),
              "(14) закрытие объясняется СОБСТВЕННОЙ строкой полосы: %s"
              % R.close_detail(key, fixed)[:70]))

# ═══ (15) СОСЕДИ НЕ ЗАДЕТЫ ═════════════════════════════════════════════════════════════════
print("\n(15) СОСЕДИ: О4, О6 и О7 на тех же фактах отвечают как отвечали")
res.append(ok(E.pc_task_state(f, C, NOW)[0] == E.PCT_MOVING,
              "(15) О6 «движется» — заходы закрывались за 4–6 минут, он и не мог увидеть беду"))
res.append(ok(E.children_state(f, C, NOW)[0] in (E.CH_ALIVE, E.CH_UNKNOWN),
              "(15) О7 занят детьми и о заходах не говорит"))
res.append(ok(E.pc_state(f, C, NOW)[0] == E.PC_ALIVE,
              "(15) О4 «подаёт признак жизни» — полоса ПИШЕТ, и это верно"))
res.append(ok(sorted(x["kind"] for x in E.verdict(f, C)) == ["o8_lane_dead"],
              "(15) беду видит РОВНО О8 — дыра закрыта, дубля нет"))
res.append(ok(len(E.KINDS) == 12 and "o8_lane_dead" in E.KINDS,
              "(15) видов стало 12, новый назван поимённо"))
res.append(ok(all(k in E.NOTE_HEAD for k in E.KINDS)
              and all(k in J.SHORT and k in J.WHAT for k in E.KINDS),
              "(15) у каждого вида есть заголовок заметки и имя в журнале мозга"))

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
