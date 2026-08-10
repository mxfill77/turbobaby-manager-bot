"""ЖИВОЙ СЧЁТ СЕРИИ ЦЕПОЧЕК (10.08.2026, рамка §8г).

Правило рамки записано 08.08, а счёта не было: единственный замер (задача 399) прогнан руками,
по ПРЕЖНЕЙ редакции («обрыв = любое вмешательство владельца») и умер вместе с задачей.

Голдены — на ДОСЛОВНЫХ текстах живой очереди и ДОСЛОВНЫХ фактах systemd:
  * карточка 437 (10.08 08:59:03 → 09:20:35) просила «да» на рестарт splinter, а splinter
    стартовал 09:09:45 — ВНУТРИ её жизни, за 11 минут ДО нажатия → ШУМ;
  * карточка 425 (09.08 17:49:22 → 18:58:48) просила то же, а старт был 19:24:34, то есть
    ПОСЛЕ ответа → ВОЛЯ ПО КОНСТРУКЦИИ.
Обе одобрены владельцем — значит сортирует именно ОПЕРАЦИЯ, а не кнопка: аргумента «да/нет»
у решения нет вовсе.

Секции:
(1) чистота модуля: импорт ровно один, ни файлов, ни сети, ни подпроцессов (ast)
(2) единица: маркеры родителя, транзитивное разрешение, петля, номер шага ≠ id задачи
(3) сорт карточки ПО ОПЕРАЦИИ: дословные 437/425 + границы (нет операции, ненаблюдаемая семья)
(4) ручная карта: высший вид §7 → воля; своя оранжевая операция → ремонт руками
(5) необъяснённый отказ: дословные формы корпуса; «отклонено Филиппом» и дежурный — НЕ отказ
(6) вердикт цепочки и серия: что рвёт, что не рвёт, открытая цепочка вне счёта
(7) замок против подлога: вес, три состояния веса, порог по замеру
(8) руки демона: тело карточки пишется при РОЖДЕНИИ, сорт ставится при закрытии, ремонт руками
(9) границы: CHAIN_SERIES=0 → ветка мертва; счёт не меняет НИ ОДНОГО вердикта очереди
(10) изоляция состояния: прогон СЬЮТА боевого файла не касается ни одним слоем
"""
import ast
import json
import os
import shutil
import sys
import tempfile

# Путь ОТ ФАЙЛА ТЕСТА, а не константой: тот же файл гоняется по дереву ДО правки (git worktree).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
# Признак тест-прогона ставим САМИ (ручной запуск идёт и без гейта): пушей в личку и боевых
# каталогов у этого сьюта быть не должно ни при каком способе запуска.
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
import chain_series as CS                                              # noqa: E402

# ── ДОСЛОВНЫЕ тексты и факты (снимок очереди 10.08.2026 + журнал systemd) ────────────────────
C437 = ("Нужно твоё «да» на рестарт splinter: фикс скана просрочек (коммит 6e525d6) лежит в "
        "origin/main и гейт зелёный, но живой процесс держит старый код и считает по-старому — "
        "исходное ТЗ рестарт запрещало намеренно, поэтому сам не делаю.")
C425 = ("Нужно твоё «да» на рестарт splinter: замок инбокса лежит в git (commit 1e7c93e, гейт "
        "183 зелёных), но devbot живёт внутри процесса splinter — в проде замка ещё нет; "
        "клиентский контур заморожен твоим решением, поэтому рестарт делаю только по твоей "
        "отмашке.")
# Дословный пункт карточки 429 оборван ПЕРЕД путём к папке выкладки: литерал этого пути внутри
# tests/*.py — находка замка зеркала (tests/test_bridge_prod_mirror.py), а операции он не несёт.
C429 = "Нужно твоё «да» на выкат моста (`clasp push` + `clasp redeploy` прод-деплоя из …)."
C032 = ("Реши, чья реализация минимума красной карточки живёт: ПК-коммит 17221f2 "
        "(`_detail_parts`/`card_min`) или уже стоящий на VPS.")
STARTS = [{"family": "service:splinter", "at": "2026-07-31T10:52:38"},
          {"family": "service:splinter", "at": "2026-08-02T18:00:28"},
          {"family": "service:splinter", "at": "2026-08-09T19:24:34"},
          {"family": "service:splinter", "at": "2026-08-10T09:09:45"},
          {"family": "service:orchestrator-daemon", "at": "2026-08-10T08:08:56"}]
OPS_RESTART = ["service:splinter"]

print("(1) ЧИСТОТА МОДУЛЯ — прибор не умеет писать")
src = open(os.path.join(REPO, "chain_series.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = sorted({(n.names[0].name.split(".")[0] if isinstance(n, ast.Import)
                   else (n.module or "").split(".")[0])
                  for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))})
res.append(ok(imports == ["re"], "(1) импорт ровно один — `re` (нашли %s)" % imports))
bad = [n.func.id for n in ast.walk(tree)
       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
       and n.func.id in ("open", "exec", "eval", "compile", "__import__")]
res.append(ok(not bad, "(1) ни open/exec/eval в исполняющей позиции (нашли %s)" % bad))
attrs = [n.func.value.id for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name)
         and n.func.value.id in ("os", "sys", "subprocess", "bridge_client", "notify", "bc")]
res.append(ok(not attrs, "(1) не трогает мир через os/sys/subprocess/мост (нашли %s)" % attrs))

print("(2) ЕДИНИЦА — корневая запись со своими шагами")
res.append(ok(CS.parent_of("[шаг 2/5 родитель 316] сделай") == ("step", 316),
              "(2) шаг → родитель 316"))
res.append(ok(CS.parent_of("[конверт одобренной заявки 437] Филипп нажал") == ("envelope", 437),
              "(2) конверт → карточка 437"))
res.append(ok(CS.parent_of("[куратор владельцу цель 435] Нужно твоё") == ("owner_card", 435),
              "(2) сводная карточка → цель 435"))
res.append(ok(CS.parent_of("[куратор владельцу цель 344, операция service:orchestrator-daemon] x")
              == ("owner_card", 344), "(2) разведённая по операции карточка → та же цель"))
res.append(ok(CS.parent_of("[куратор цели 319, шаг 1] Хвост") == ("curator_step", 319),
              "(2) продолжение куратора → цель 319"))
res.append(ok(CS.parent_of("[куратор задача 435] вердикт куратора") == ("curator_verdict", 435),
              "(2) карточка вердикта → задача 435"))
res.append(ok(CS.parent_of("ultrathink\n\nЦЕЛЬ: ...") == ("root", None),
              "(2) задача без маркера — сама себе корень"))
# ГЛАВНАЯ ЛОВУШКА: у «самопочинки ШАГА» число — НОМЕР ШАГА, а не id задачи; шаг решает первым.
res.append(ok(CS.parent_of("[шаг 3/7 родитель 210] [самопочинка шага 3, попытка 1] x")
              == ("step", 210),
              "(2) перерождение шага: родитель 210, а НЕ «задача 3» (номер шага ≠ id)"))
res.append(ok(CS.parent_of("[самопочинка задачи 122, попытка 1] x") == ("selfheal", 122),
              "(2) перерождение одиночки → задача 122"))
ENTRIES = [{"id": 435, "text": "ultrathink ЦЕЛЬ: скан просрочек"},
           {"id": 437, "text": "[куратор владельцу цель 435] Нужно твоё «да»"},
           {"id": 441, "text": "[конверт одобренной заявки 437] Филипп нажал «да»"},
           {"id": 436, "text": "[куратор задача 435] вердикт куратора"},
           {"id": 999, "text": "[шаг 1/2 родитель 777] сирота: родителя в снимке нет"}]
r = CS.resolve_roots(ENTRIES)
res.append(ok(r[441][0] == 435 and r[437][0] == 435 and r[436][0] == 435,
              "(2) ТРАНЗИТИВНО: конверт 441 → карточка 437 → цель 435"))
res.append(ok(r[999][0] == 999, "(2) родителя нет в снимке → запись сама себе корень"))
loop = CS.resolve_roots([{"id": 1, "text": "[шаг 1/2 родитель 2] a"},
                         {"id": 2, "text": "[шаг 1/2 родитель 1] b"}])
res.append(ok(loop[1][0] in (1, 2) and loop[2][0] in (1, 2), "(2) петля маркеров не зацикливает"))
res.append(ok(len(CS.resolve_roots(ENTRIES)) == 5, "(2) ни одна запись не потеряна"))
res.append(ok("owner_card" in CS.SERVICE_KINDS and "step" not in CS.SERVICE_KINDS,
              "(2) служебные виды названы, шаг служебным не считается"))

print("(3) СОРТ ПО ОПЕРАЦИИ — дословные 437 и 425")
# Операции берём ИЗ ДОСЛОВНОГО ТЕЛА тем же словарём, которым машина зовёт операции сама, — иначе
# голден проверял бы наш список, а не разбор живого текста.
import curator_ops                                                     # noqa: E402
ops437 = [o["key"] for o in curator_ops.operations(C437)]
ops425 = [o["key"] for o in curator_ops.operations(C425)]
ops429 = [o["key"] for o in curator_ops.operations(C429)]
ops032 = [o["key"] for o in curator_ops.operations(C032)]
res.append(ok(ops437 == OPS_RESTART and ops425 == OPS_RESTART,
              "(3) в дословных 437 и 425 названа операция service:splinter (%s / %s)"
              % (ops437, ops425)))
res.append(ok(ops429 == ["bridge_deploy"], "(3) в дословной 429 названа выкладка моста (%s)"
              % ops429))
res.append(ok(ops032 == [], "(3) в дословной 32 операции нет вовсе — это просьба РЕШИТЬ"))
res.append(ok(CS.sort_card(ops429, STARTS, "2026-08-10T00:00:00",
                           "2026-08-10T12:00:00")["sort"] == CS.UNKNOWN,
              "(3) дословная 429 (выкат моста) → НЕИЗВЕСТНО: состояние отсюда не наблюдается"))
res.append(ok(CS.sort_card(ops032, STARTS, "2026-07-29T10:00:00",
                           "2026-07-29T11:00:00")["sort"] == CS.NOISE,
              "(3) дословная 32 → шум по рамке (операции операционного класса за ней нет)"))
v437 = CS.sort_card(ops437, STARTS, "2026-08-10T08:59:03", "2026-08-10T09:20:35")
res.append(ok(v437["sort"] == CS.NOISE and "09:09:45" in v437["why"],
              "(3) 437: рестарт в 09:09:45 внутри жизни карточки → ШУМ («да» купило ничего)"))
v425 = CS.sort_card(ops425, STARTS, "2026-08-09T17:49:22", "2026-08-09T18:58:48")
res.append(ok(v425["sort"] == CS.WILL,
              "(3) 425: рестарт 19:24:34 ПОСЛЕ ответа → ВОЛЯ ПО КОНСТРУКЦИИ"))
res.append(ok(CS.sort_card(["service:splinter", "bridge_deploy"], STARTS,
                           "2026-08-10T08:00:00", "2026-08-10T09:00:00")["sort"] == CS.WILL,
              "(3) одна операция ещё не сделана → воля (смесь не понижает до неизвестного)"))
res.append(ok(CS.sort_card(["service:wa-webhook"], STARTS, "2026-08-10T08:00:00",
                           "2026-08-10T10:00:00")["sort"] == CS.WILL,
              "(3) наблюдаемая семья без смены состояния → воля"))
# ОТВЕТ ВЛАДЕЛЬЦА В РЕШЕНИЕ НЕ ВХОДИТ: у функции нет такого аргумента вовсе.
sig = [a.arg for a in ast.parse(src).body[0].body[0].args.args] if False else None
fn = next(n for n in ast.walk(ast.parse(src))
          if isinstance(n, ast.FunctionDef) and n.name == "sort_card")
res.append(ok(not any(a.arg in ("answer", "approved", "verdict", "button")
                      for a in fn.args.args),
              "(3) у sort_card нет аргумента ответа — «по операции, а не по кнопке» устройством"))
res.append(ok(CS.sort_card(OPS_RESTART, STARTS, "2026-08-10T08:59:03", "")["sort"] == CS.NOISE,
              "(3) карточка ещё открыта: верхняя граница окна не задана — смена всё равно видна"))
res.append(ok(CS.sort_card(OPS_RESTART, [], "2026-08-10T08:59:03",
                           "2026-08-10T09:20:35")["sort"] == CS.WILL,
              "(3) фактов о стартах нет → воля (без факта в шум не обвиняем)"))

print("(4) РУЧНАЯ КАРТА — высший вид §7 против своей оранжевой операции")
res.append(ok(CS.sort_manual_card(["bridge_deploy"])["sort"] == CS.WILL,
              "(4) деплой моста руками — воля по конструкции (система не вправе сама)"))
res.append(ok(CS.sort_manual_card(["set_fleet_oil"])["sort"] == CS.WILL,
              "(4) запись в Лист1 руками — воля по конструкции"))
res.append(ok(CS.sort_manual_card(["service:splinter"])["sort"] == CS.MANUAL,
              "(4) рестарт своего сервиса руками — РЕМОНТ РУКАМИ (обязана была сама)"))
res.append(ok(CS.sort_manual_card([])["sort"] == CS.MANUAL,
              "(4) операции не названо → ремонт (работа всё равно ушла в руки)"))
res.append(ok(CS.is_manual_card("✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ (это не сбой, а нормальный ручной "
                                "исход) HEAD…"), "(4) дословная форма ручной карты опознана"))
res.append(ok(not CS.is_manual_card("отклонено Филиппом (кнопка)"),
              "(4) отказ владельца ручной картой не является"))

print("(5) НЕОБЪЯСНЁННЫЙ ОТКАЗ — дословные формы корпуса")
for text, want, label in (
        ("⏱ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=heartbeat_timeout · ...]",
         "зависание", "heartbeat_timeout"),
        ("⏱ провал [причина=run_timeout · таймаут прогона]: таймаут 2700с", "зависание",
         "run_timeout"),
        ("⏱ ПК-театр не отвечает: задача взята в исполнение", "зависание", "ПК-театр"),
        ("claude -p упал (exit=1): Failed to authenticate: OAuth session expired", "потеря",
         "OAuth"),
        ("claude exit=1: API Error: 500 Overloaded.", "потеря", "API Error"),
        ("✋ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=model_refusal · отказ]",
         "тихий отказ", "model_refusal"),
        ("[причина=exec_error · ошибка выполнения]: задача упала → думатель: halt, причина: x",
         "халт", "halt думателя")):
    res.append(ok(CS.refusal("failed", text) == want, "(5) %s → %s" % (label, want)))
res.append(ok(CS.refusal("failed", "отклонено Филиппом (кнопка)") == "",
              "(5) «отклонено Филиппом» отказом контура НЕ является (это воля)"))
res.append(ok(CS.refusal("failed", "✋ КАРТОЧКА СНЯТА ДЕЖУРНЫМ (кнопки «да» здесь нет)") == "",
              "(5) карточка, снятая дежурным, до владельца не дошла — не отказ"))
res.append(ok(CS.refusal("failed", "⏭ пропущен: другой шаг родителя 210 упал") == "",
              "(5) пропуск сиблинга — следствие чужого обрыва, не свой"))
res.append(ok(CS.refusal("failed", "гейт красный: 3 теста упали, откатился git revert") == "",
              "(5) честный провал С ДИАГНОЗОМ серию НЕ рвёт — система отработала как задумана"))
res.append(ok(CS.refusal("done", "⏱ причина=run_timeout") == "",
              "(5) не failed → отказа нет вовсе"))


def chain(root, cards=(), refusals=(), statuses=("done",), commits=(), restarts=0, known=True,
          lane="vps"):
    return {"root": root, "lane": lane, "created": "2026-08-01T00:00:00",
            "closed_at": "2026-08-01T01:00:00", "statuses": list(statuses),
            "cards": [dict(c) for c in cards], "refusals": [dict(x) for x in refusals],
            "weight": {"commits": list(commits), "restarts": restarts, "known": known}}


print("(6) ВЕРДИКТ ЦЕПОЧКИ И СЕРИЯ")
res.append(ok(CS.chain_verdict(chain(1, cards=[{"sort": CS.NOISE, "why": "x"}]))["break"],
              "(6) шум рвёт серию"))
res.append(ok(CS.chain_verdict(chain(1, cards=[{"sort": CS.MANUAL, "why": "x"}]))["break"],
              "(6) ремонт руками рвёт серию"))
res.append(ok(not CS.chain_verdict(chain(1, cards=[{"sort": CS.WILL, "why": "x"}]))["break"],
              "(6) ВОЛЯ ПО КОНСТРУКЦИИ серию НЕ рвёт (иначе критерий недостижим)"))
res.append(ok(not CS.chain_verdict(chain(1, cards=[{"sort": CS.UNKNOWN, "why": "x"}]))["break"],
              "(6) неизвестное серию не рвёт — без факта не обвиняем"))
res.append(ok(CS.chain_verdict(chain(1, refusals=[{"id": 1, "reason": "зависание"}]))["cause"]
              == "отказ", "(6) необъяснённый отказ рвёт и называется своей причиной"))
res.append(ok(CS.chain_verdict(chain(1, cards=[{"sort": CS.NOISE, "why": "n"},
                                               {"sort": CS.MANUAL, "why": "m"}]))["cause"]
              == CS.NOISE, "(6) причина обрыва одна и по порядку: шум → ремонт → отказ"))
res.append(ok(not CS.chain_verdict(chain(1, statuses=("done", "new")))["closed"],
              "(6) живая запись в цепочке → цепочка НЕ закрыта"))
seq = [CS.chain_verdict(chain(i, commits=(["abc1234"] if i % 2 else []))) for i in range(1, 8)]
seq[3]["break"], seq[3]["cause"] = True, CS.NOISE
st = CS.series(seq)
res.append(ok(st["best"] == 3 and st["current"] == 3,
              "(6) серия считается подряд и обрывается ровно на цепочке с обрывом"))
res.append(ok(len(st["breaks"]) == 1 and st["breaks"][0]["broke_len"] == 3,
              "(6) обрыв помнит, серию какой длины он оборвал"))
opened = [CS.chain_verdict(chain(1)), CS.chain_verdict(chain(2, statuses=("in_progress",))),
          CS.chain_verdict(chain(3))]
res.append(ok(CS.series(opened)["current"] == 2 and CS.series(opened)["open"] == 1,
              "(6) открытая цепочка в серию не входит ни в одну сторону"))

print("(7) ЗАМОК ПРОТИВ ПОДЛОГА — длина без веса не считается")
res.append(ok(CS.chain_verdict(chain(1, commits=["6e525d6"]))["weight"],
              "(7) доказанный коммит origin/main = вес"))
res.append(ok(CS.chain_verdict(chain(1, restarts=1))["weight"], "(7) свой рестарт сервиса = вес"))
res.append(ok(not CS.chain_verdict(chain(1))["weight"], "(7) чтение без следа веса не даёт"))
pc = CS.chain_verdict(chain(1, commits=["6e525d6"], known=False, lane="pc"))
res.append(ok(pc["weight_known"] is False and pc["weight"] is False,
              "(7) полоса pc: вес НЕ НАБЛЮДАЕМ — это третье состояние, а не нуль"))
long_ok = [CS.chain_verdict(chain(i, commits=(["c%06d" % i] if i % 2 else [])))
           for i in range(1, 41)]
res.append(ok(CS.series(long_ok)["qualified"],
              "(7) 40 цепочек, вес половина — серия ЗАЧЁТНАЯ (порог %.0f%%)"
              % (100 * CS.WEIGHT_MIN_SHARE)))
long_light = [CS.chain_verdict(chain(i)) for i in range(1, 41)]
res.append(ok(not CS.series(long_light)["qualified"],
              "(7) 40 цепочек БЕЗ веса → НЕ зачётная: подлог длиной не проходит"))
blind = [CS.chain_verdict(chain(i, known=False, lane="pc")) for i in range(1, 41)]
res.append(ok(not CS.series(blind)["qualified"],
              "(7) 40 цепочек с ненаблюдаемым весом → не зачётная (слепота ≠ зачёт)"))
res.append(ok(CS.series([CS.chain_verdict(chain(i, commits=["c"])) for i in range(1, 10)])
              ["qualified"] is False, "(7) вес есть, длины нет → не зачётная"))
w = CS.weight_windows([CS.chain_verdict(chain(i, commits=(["c"] if i <= 15 else [])))
                       for i in range(1, 41)], size=10)
res.append(ok(w and w[0] == 0.0 and w[-1] == 1.0,
              "(7) скользящее окно веса даёт форму распределения (min 0, max 1)"))
res.append(ok(CS.SERIES_TARGET == 30, "(7) порог фазы не тронут — 30 цепочек, как в рамке"))

print("(8) РУКИ ДЕМОНА — тело карточки пишется при РОЖДЕНИИ")
import orchestrator_daemon as OD                                       # noqa: E402
tmp = tempfile.mkdtemp(prefix="cc_series_test_")
os.environ["CC_SERIES_FILE"] = os.path.join(tmp, "chain_series.json")
OD._series_commits = lambda result, since: []          # git в тесте не зовём
OD._series_units_now = lambda: {"splinter": "2026-08-10T09:09:45"}
os.environ["CHAIN_SERIES"] = "1"
TASK437 = {"id": 437, "lane": "vps", "created": "2026-08-10T08:59:03.083Z",
           "task_text": "[куратор владельцу цель 435] " + C437}
TASK435 = {"id": 435, "lane": "vps", "created": "2026-08-10T08:20:00.000Z",
           "task_text": "ultrathink ЦЕЛЬ: скан просрочек"}
OD._series_note_terminal(TASK435, "done", "готово")
OD._series_note_card(437, TASK437, C437)
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
card = (state["chains"]["435"]["cards"] or [{}])[0]
res.append(ok(card.get("ops") == ["service:splinter"],
              "(8) операция карточки 437 названа при рождении (%s)" % card.get("ops")))
res.append(ok(card.get("open") is True and "435" in state["chains"],
              "(8) карточка записана в цепочку ЦЕЛИ 435, а не отдельной строкой"))
res.append(ok("437" not in state["chains"],
              "(8) служебная запись цепочки не заводит — плоский счёт запрещён"))
# карточка ушла из needs_approval → сорт ставится ЗДЕСЬ, по операции
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
state["units"] = {"splinter": "2026-08-10T08:00:00"}          # прошлый старт известен
state["chains"]["435"]["cards"][0]["born"] = "2026-08-10T08:59:03"
OD._series_save(state)
OD._series_cards_tick(set())
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
card = state["chains"]["435"]["cards"][0]
res.append(ok(card.get("sort") == CS.NOISE and not card.get("open"),
              "(8) 437 закрыта сортом ШУМ: рестарт 09:09:45 успел ДО ответа (%s)"
              % str(card.get("why"))[:60]))
res.append(ok(state["derived"]["current"] == 0 and state["derived"]["breaks"],
              "(8) серия обнулена этим обрывом, и обрыв записан"))
res.append(ok("отклонено" not in json.dumps(state, ensure_ascii=False)
              and "approved" not in json.dumps(state, ensure_ascii=False),
              "(8) ответа владельца в состоянии нет вовсе — сорт по операции"))
# ремонт руками: рестарт вне окна исполнения (считаем ПРИРОСТ — прошлый тик уже дал свой)
was = len([c for c in state["chains"]["435"]["cards"] if c.get("sort") == CS.MANUAL])
OD._series_units_now = lambda: {"splinter": "2026-08-10T15:00:00"}
OD._series_cards_tick(set())
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
manual = [c for c in state["chains"]["435"]["cards"] if c.get("sort") == CS.MANUAL]
res.append(ok(len(manual) == was + 1 and "15:00:00" in manual[-1]["why"]
              and "руками" in manual[-1]["why"],
              "(8) рестарт вне окна исполнения → РЕМОНТ РУКАМИ (раньше не считался вовсе)"))
# свой рестарт: попал в окно задачи → вес, а не ремонт
OD._LAST_RUN.clear()
OD._LAST_RUN.update({"task": 449, "started": "2026-08-10T16:00:00+00:00"})
OD._series_note_terminal({"id": 449, "lane": "vps", "created": "2026-08-10T15:58:00.000Z",
                          "task_text": "ultrathink ЦЕЛЬ: другая"}, "done", "готово")
OD._series_units_now = lambda: {"splinter": "2026-08-10T16:05:00"}
OD._series_cards_tick(set())
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
res.append(ok(state["chains"]["449"]["weight"]["restarts"] == 1
              and not [c for c in state["chains"]["449"]["cards"] if c.get("sort") == CS.MANUAL],
              "(8) рестарт ВНУТРИ окна исполнения — своя работа (вес), а не ремонт"))
res.append(ok(state["chains"]["435"]["statuses"].get("435") == "done",
              "(8) исход записан в момент терминала, а не пересчитан по очереди"))
# КОНВЕРТ одобренной карточки: терминала у самой карточки в process_new нет, и без поиска среди
# КАРТОЧЕК конверт завёл бы свою цепочку — ровно плоский счёт, запрещённый рамкой.
OD._series_note_terminal({"id": 441, "lane": "vps", "created": "2026-08-10T09:20:31.000Z",
                          "task_text": "[конверт одобренной заявки 437] Филипп нажал «да»"},
                         "done", "исполнять нечего")
state = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
res.append(ok("441" not in state["chains"] and "437" not in state["chains"]
              and state["chains"]["435"]["statuses"].get("441") == "done",
              "(8) конверт 441 → карточка 437 → ЦЕЛЬ 435: своей цепочки не завёл"))

print("(9) ГРАНИЦЫ")
shutil.rmtree(tmp, ignore_errors=True)
tmp2 = tempfile.mkdtemp(prefix="cc_series_test_off_")
os.environ["CC_SERIES_FILE"] = os.path.join(tmp2, "chain_series.json")
os.environ["CHAIN_SERIES"] = "0"
OD._series_note_terminal(TASK435, "done", "готово")
OD._series_note_card(437, TASK437, C437)
OD._series_cards_tick(set())
res.append(ok(not os.path.exists(os.environ["CC_SERIES_FILE"]),
              "(9) CHAIN_SERIES=0 → ветка мертва ДО сбора фактов, файла нет вовсе"))
os.environ["CHAIN_SERIES"] = "1"
# счёт ничего не решает: сбой записи не должен ломать терминал
os.environ["CC_SERIES_FILE"] = os.path.join(tmp2, "нет-такого-каталога", "x.json")
crashed = False
try:
    OD._series_note_terminal(TASK435, "done", "готово")
except Exception:                                                       # noqa: BLE001
    crashed = True
res.append(ok(not crashed, "(9) сбой записи состояния НЕ бросает — счёт не смеет ломать задачу"))
dsrc = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
dtree = ast.parse(dsrc)
series_fns = [n for n in ast.walk(dtree)
              if isinstance(n, ast.FunctionDef) and n.name.startswith("_series_")]
touch = [n.name for f in series_fns for n in ast.walk(f)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name) and n.func.value.id == "bc"]
res.append(ok(not touch, "(9) руки счёта НЕ трогают очередь ни одним вызовом моста (%s)" % touch))
res.append(ok(CS.WEIGHT_MIN_SHARE == 0.25,
              "(9) порог веса — 0.25, поставлен по замеру 10.08 (min окна 23.3 %, медиана 60 %)"))
shutil.rmtree(tmp2, ignore_errors=True)

print("(10) ИЗОЛЯЦИЯ СОСТОЯНИЯ — прогон сьюта боевого файла не касается")
# СУДИМ ПУТЬ, А НЕ ФАЙЛ, и это не вкусовщина. Проверка «mtime боевого файла не изменился за
# прогон» дала бы ЛОЖНОЕ КРАСНОЕ: боевой демон пишет то же состояние на терминале задачи, а гейт
# гоняется РОВНО в такие моменты — сьют штрафовался бы за чужую законную запись. Путь же
# принадлежит этому процессу целиком.
env_was = (os.environ.get("CC_SERIES_FILE"), os.environ.get("ORCH_TEST_MODE"))
res.append(ok(os.path.basename(OD.CHAIN_SERIES_FILE) == "chain_series.json"
              and OD.CHAIN_SERIES_FILE == os.path.join(OD.REPO, "chain_series.json"),
              "(10) боевой путь по умолчанию НЕ тронут: %s" % OD.CHAIN_SERIES_FILE))
res.append(ok(OD._series_file() != OD.CHAIN_SERIES_FILE,
              "(10) подстановка сьюта (CC_SERIES_FILE) уводит запись из боевого файла"))
os.environ.pop("CC_SERIES_FILE", None)
res.append(ok(OD._series_file() == OD.CHAIN_SERIES_TEST_FILE,
              "(10) забыли подставить — второй слой (ORCH_TEST_MODE) держит: %s"
              % os.path.basename(OD._series_file())))
os.environ.pop("ORCH_TEST_MODE", None)
res.append(ok(not OD._IS_DAEMON and OD._series_file() != OD.CHAIN_SERIES_FILE,
              "(10) сняты ОБА признака — третий слой (личность пишущего) не пускает в боевой"))
if env_was[0] is not None:
    os.environ["CC_SERIES_FILE"] = env_was[0]
os.environ["ORCH_TEST_MODE"] = env_was[1] or "1"

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
