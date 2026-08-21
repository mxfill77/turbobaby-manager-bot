"""ОТКАЗ ВЛАДЕЛЬЦА — НЕ ПАДЕНИЕ ЗАДАЧИ (22.08.2026).

ПОВОД. В учёте сервера решение человека и сбой машины лежат под ОДНИМ статусом, и «нет» владельца
читается как поломка. Живой замер полосы сервера (снимок очереди 21.08.2026 20:51:44 UTC, обе
полосы, все семь статусов): `rejected` — 0 строк, `declined` — 0, `cancelled` — 0; под `failed` —
5 строк, и ЧЕТЫРЕ из них (#4, #6, #16, #20) закрыты словами «отклонено Филиппом (кнопка)».
То есть 80 % «падений» суток — нажатая кнопка, и слепок очереди в мозге называл их упавшими.

ПРИЗНАК НАЗВАЛА СОСЕДНЯЯ ПОЛОСА, А НЕ МЫ. Журнал `cowork_log` 14.08.2026 17:20 UTC дословно:
«статуса rejected в очереди нет (items=0), отказ лежит в failed с ПРЕФИКСОМ «отклонено Филиппом» —
23 из 55 (41.8 %)». Здесь читается ровно префикс, а не слово где-нибудь в теле.

ГОЛДЕНЫ — ДОСЛОВНЫЕ ТЕЛА ЖИВЫХ СТРОК ОЧЕРЕДИ (снимок 21.08.2026 20:51:44 UTC):
    #4, #16, #20 (pc, failed) — «отклонено Филиппом (кнопка)»: карточка ревизора и два ТЗ;
    #6  (pc, failed) — то же, задача «ПРЕКРАТИТЬ СПРАШИВАТЬ ВЛАДЕЛЬЦА ПРО ВЫКАТКУ…»;
    #21 (pc, failed) — НАСТОЯЩЕЕ падение: «⏱ НЕ ЗАКРЫТА… [причина=run_timeout…]», 1055 символов;
    #5  (pc, DONE)   — отчёт, ЦИТИРУЮЩИЙ маркер на символе 1952 внутри обратных кавычек.

Что доказывается:
    (1) ПРЕМИСА — у очереди статусов шесть, терминальных два, `rejected` мост не принимает вовсе
        (сверяется с ЖИВЫМ исходником задеплоенного моста, а не с пересказом);
    (2) ПРИЗНАК И ПОЗИЦИЯ — маркер судится префиксом первой непустой строки;
    (3) РАЗРЕЗ В УЧЁТЕ — отказ владельца стал отдельным исходом со своим счётчиком и разделом,
        и раздел прямо говорит, что это решение и что переотправке оно не подлежит;
    (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а) — настоящее падение НЕ попало в отклонённые;
    (5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б) — отклонённое НЕ попало в упавшие;
    (6) ЛЕГАСИ — запись реестра, снятая ДО разреза, пересуживается односторонне;
    (7) СЕРИЯ — отказ владельца её не рвёт, падение рвёт, а падение С ЦИТАТОЙ маркера рвёт тоже
        (находка 22.08: прежде цитата в теле отчёта делала сбой «волей владельца»);
    (8) СВЕРКА ДВУХ РЕАЛИЗАЦИЙ — счёт серии и хозяин признака отвечают одинаково на всём корпусе;
    (9) ГРАНИЦЫ — `done` с цитатой маркера остаётся сданной, дословный ответ внешней системы к
        отклонённой не приезжает, очередь не переписывается ничем;
   (10) ЧИСТОТА — у решения импортов НОЛЬ (ast), страж живой и зубастый.
"""
import ast
import os
import sys

# Корень берётся ОТ ФАЙЛА, а чужой боевой корень вычищается из пути: иначе прогон «до правки»
# через `git worktree` тянул бы модуль из БОЕВОГО дерева (ловушка метода, пойманная живьём 07.08).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT != "/root/turbobaby-manager-bot":
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"]
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"

import owner_refusal as OR                                            # noqa: E402
import queue_state as Q                                               # noqa: E402
import chain_series as CS                                             # noqa: E402
import invariants_check                                               # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
NOW = 1787000000.0            # «сейчас» пришпилено: своих часов у решения нет

# ── ДОСЛОВНЫЕ ТЕЛА ЖИВОЙ ОЧЕРЕДИ ─────────────────────────────────────────────────────────────
BTN = "отклонено Филиппом (кнопка)"          # devbot._cb_reject, кнопка ❌
TXT = "отклонено Филиппом"                   # devbot «нет N», текстом
FELL21 = (
    "⏱ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=run_timeout · таймаут прогона]: "
    "таймаут 2700s — headless прерван, задача не завершилась. СЛЕДЫ в окне 15.08 10:29–20:42 "
    "UTC: коммитов 185 (edca94a «выводы 15.08 держались на четырёх годах: те же четыре меры п»; "
    "6806662 «тело журнальной записи о пересчёте базы на коротких окнах (в»)")
QUOTE5 = (
    "**2. Ключевой ответ — отказ не читается никогда.** Реестр есть "
    "(`pc_orchestrator.revizor_verdicts.json`, ключ `класс|окно|предмет`), читается каждым "
    "прогоном (`:8529`), фильтр исправен. Отказ владельца живёт отдельно: `failed` с префиксом "
    "`отклонено Филиппом`; его читают `NO_HEAL_PREFIXES`, `card_terminal_log.py`, "
    "`queue_snapshot_pc.py` — **ревизора среди них нет**.")

print("\n(1) ПРЕМИСА: какие статусы вообще бывают у очереди — по ЖИВОМУ исходнику моста")
_bridge = open(os.path.join(ROOT, "bridge_prod", "BotData.js"), encoding="utf-8").read()
res.append(ok("// status ∈ new/in_progress/needs_approval/approved/done/failed." in _bridge,
              "(1a) очередь знает ШЕСТЬ статусов и `rejected` среди них нет"))
res.append(ok("if (status !== 'done' && status !== 'failed') return { ok: false, "
              "error: 'bad_status' };" in _bridge,
              "(1b) терминалов ДВА: мост принимает у complete_task только done|failed"))
res.append(ok("отклонено Филиппом" in open(os.path.join(ROOT, "devbot.py"), encoding="utf-8").read(),
              "(1c) отказ владельца пишется словами в поле результата — иного места у него нет"))

print("\n(2) ПРИЗНАК И ЕГО ПОЗИЦИЯ")
res.append(ok(OR.said(BTN) and OR.said(TXT), "(2a) обе живые формы отказа — заявление"))
res.append(ok(OR.said("  " + BTN) and OR.said("- " + BTN) and OR.said("**" + TXT),
              "(2b) декорация форматирования перед маркером цитатой не делает"))
res.append(ok(not OR.said(QUOTE5),
              "(2c) ДОСЛОВНАЯ цитата #5 (маркер в обратных кавычках на 1952-м символе) — не заявление"))
res.append(ok(not OR.said(FELL21 + "\n\nхвост: задачи 4, 6, 16 закрыты словами «" + BTN + "»"),
              "(2d) настоящее падение, ЦИТИРУЮЩЕЕ маркер в хвосте отчёта, — не заявление"))
res.append(ok(not OR.said("") and not OR.said(None) and not OR.said("причина=run_timeout"),
              "(2e) пусто · None · чужая причина → заявления нет"))
res.append(ok(OR.said("\n\n   " + BTN), "(2f) пустые строки сверху позиции не сдвигают"))
res.append(ok(not OR.said("> " + BTN) and not OR.said("«" + BTN) and not OR.said("`" + BTN),
              "(2g) знак цитаты, кавычка и обратная кавычка → цитата, а не заявление"))
res.append(ok(OR.outcome("failed", BTN) == OR.REFUSAL and OR.outcome("failed", FELL21) == OR.FAILURE,
              "(2h) исход: отказ владельца ≠ падение"))
res.append(ok(OR.outcome("done", BTN) == "" and OR.outcome("", BTN) == "",
              "(2i) не `failed` → судить нечего, отвечаем пустотой"))
res.append(ok(OR.outcome("failed", "") == OR.FAILURE and OR.outcome("failed", None) == OR.FAILURE,
              "(2j) НАПРАВЛЕНИЕ СОМНЕНИЯ: нет доказательства → «упала», как было"))

print("\n(3) РАЗРЕЗ В СВОЁМ УЧЁТЕ: закрытые за сутки — до и после")
CORPUS = [
    {"id": "4", "lane": "pc", "task_text": "[ревизор-находки] сводная карточка находок ревизора",
     "result": BTN, "status": "failed", "at": NOW - 37000},
    {"id": "6", "lane": "pc", "task_text": "ultrathink ПРЕКРАТИТЬ СПРАШИВАТЬ ВЛАДЕЛЬЦА ПРО ВЫКАТКУ",
     "result": BTN, "status": "failed", "at": NOW - 28000},
    {"id": "16", "lane": "pc", "task_text": "[ревизор-находки] сводная карточка находок ревизора",
     "result": BTN, "status": "failed", "at": NOW - 13000},
    {"id": "20", "lane": "pc", "task_text": "ultrathink", "result": BTN,
     "status": "failed", "at": NOW - 4000},
    {"id": "21", "lane": "pc", "task_text": "ultrathink", "result": FELL21,
     "status": "failed", "at": NOW - 700},
    {"id": "5", "lane": "pc", "task_text": "ultrathink РАЗВЕДКА read-only: почему ревизор трижды",
     "result": QUOTE5, "status": "done", "at": NOW - 36000},
    {"id": "7", "lane": "vps", "task_text": "ultrathink Записать в мозг итог работ 20-21.08",
     "result": "Итог записан в узел карты master", "status": "done", "at": NOW - 30000},
]
gone = Q.seed(CORPUS, NOW)
by = {r["id"]: r for r in gone}
n_done = len([r for r in gone if r["outcome"] == "сдана"])
n_fell = len([r for r in gone if r["outcome"] == OR.FAILURE])
n_turn = len([r for r in gone if r["outcome"] == OR.REFUSAL])
print("      ДО разреза (правило «статус=failed → упала»): сдано 2, упало 5")
print("      ПОСЛЕ: сдано %d, упало %d, отклонено владельцем %d" % (n_done, n_fell, n_turn))
res.append(ok((n_done, n_fell, n_turn) == (2, 1, 4),
              "(3a) 7 закрытых суток: сдано 2, упало 1, отклонено владельцем 4"))
res.append(ok([r["id"] for r in gone if r["outcome"] == OR.REFUSAL] == ["20", "16", "6", "4"],
              "(3b) поимённо отклонены владельцем: #20, #16, #6, #4 (новее — выше)"))
text = Q.body([], gone, NOW, closed_at=NOW, lane="VPS", since=NOW - Q.SHOW_SEC - 1)
res.append(ok("сдано 2, упало 1, отклонено владельцем 4" in text,
              "(3c) шапка раздела считает три исхода врозь"))
res.append(ok("ОТКЛОНЕНО ВЛАДЕЛЬЦЕМ (4)" in text and OR.NOTE in text,
              "(3d) у отказа свой раздел и прямая пометка «решение, а не сбой; не переотправлять»"))
res.append(ok("переотправке не подлежит" in text,
              "(3e) сказано ДОСЛОВНО, что переотправке отклонённое не подлежит"))
res.append(ok(Q.FORM == "4",
              "(3f) форма слепка поднята — иначе документ остался бы с прежним текстом"))

print("\n(4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): настоящее падение НЕ попало в отклонённые")
print("      тело #21 дословно: %s…" % FELL21[:96])
print("      исход: %s | в разделе отклонённых: %s"
      % (by["21"]["outcome"], "ДА" if "#21" in text.split("ОТКЛОНЕНО ВЛАДЕЛЬЦЕМ")[-1] else "нет"))
res.append(ok(by["21"]["outcome"] == OR.FAILURE, "(4a) #21 (run_timeout) — «упала»"))
res.append(ok("УПАЛА · pc · #21" in text, "(4b) #21 стоит в упавших ДОСЛОВНОЙ строкой"))
res.append(ok("#21" not in text.split("ОТКЛОНЕНО ВЛАДЕЛЬЦЕМ")[-1].split("(упавшие")[0],
              "(4c) и его НЕТ в разделе отклонённых"))

print("\n(5) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): отклонённое НЕ попало в упавшие")
print("      тело #6 дословно: «%s»" % BTN)
print("      исход: %s | строк «УПАЛА · pc · #6»: %d"
      % (by["6"]["outcome"], text.count("УПАЛА · pc · #6")))
res.append(ok(by["6"]["outcome"] == OR.REFUSAL, "(5a) #6 — «отклонена владельцем»"))
res.append(ok("УПАЛА · pc · #6" not in text and "УПАЛА · pc · #4" not in text,
              "(5b) в упавших их нет ни одной строкой"))
res.append(ok(text.count("УПАЛА · ") == 1, "(5c) упавшая в разделе ровно одна — #21"))

print("\n(6) ЛЕГАСИ-ЗАПИСЬ РЕЕСТРА, СНЯТАЯ ДО РАЗРЕЗА")
old = [{"id": "16", "lane": "pc", "head": "карточка", "at": NOW - 13000,
        "outcome": "упала", "why": BTN},
       {"id": "21", "lane": "pc", "head": "ultrathink", "at": NOW - 700,
        "outcome": "упала", "why": Q.head(FELL21)[:Q.WHY_MAX]},
       {"id": "9", "lane": "vps", "head": "рамка", "at": NOW - 900, "outcome": "сдана", "why": ""}]
re_led = Q.ledger(old, {}, [], [], NOW)
rb = {r["id"]: r for r in re_led}
res.append(ok(rb["16"]["outcome"] == OR.REFUSAL,
              "(6a) вчерашняя «упала» с маркером в «почему» стала отказом владельца"))
res.append(ok(rb["21"]["outcome"] == OR.FAILURE and rb["9"]["outcome"] == "сдана",
              "(6b) настоящее падение и сданная не тронуты"))
res.append(ok(OR.regrade(OR.REFUSAL, "что угодно") == OR.REFUSAL
              and OR.regrade("сдана", BTN) == "сдана",
              "(6c) пересуд ОДНОСТОРОННИЙ: обратного хода и захвата «сдана» нет"))

print("\n(7) СЧЁТЧИК СЕРИИ СЧИТАЕТ ПОЛОВИНЫ ПО-РАЗНОМУ")
print("      отказ владельца     → refusal=%r" % CS.refusal("failed", BTN))
print("      падение #21         → refusal=%r" % CS.refusal("failed", FELL21))
_quoted = FELL21 + "\n\nхвост отчёта: задачи 4, 6, 16 и 20 закрыты словами «" + BTN + "»."
print("      падение + цитата    → refusal=%r" % CS.refusal("failed", _quoted))
res.append(ok(CS.refusal("failed", BTN) == "" and CS.refusal("failed", TXT) == "",
              "(7a) отказ владельца серию как сбой НЕ рвёт"))
res.append(ok(CS.refusal("failed", FELL21) == "зависание",
              "(7b) настоящее падение рвёт (необъяснённый отказ контура)"))
res.append(ok(CS.refusal("failed", _quoted) == "зависание",
              "(7c) НАХОДКА 22.08 закрыта: падение с ЦИТАТОЙ маркера рвёт серию, как и должно"))
res.append(ok(CS.refusal("failed", "КАРТОЧКА СНЯТА ДЕЖУРНЫМ: объект не назван") == ""
              and CS.refusal("failed", "⏭ пропущен: сиблинг упал") == "",
              "(7d) соседние «не отказы» (дежурный, пропуск сиблинга) не тронуты"))
res.append(ok(CS.refusal("done", FELL21) == "", "(7e) не failed — судить нечего, как было"))
_turned_chain = CS.chain_verdict({"root": 6, "lane": "pc", "created": "2026-08-21T12:40:00",
                                  "closed_at": "2026-08-21T13:00:20", "statuses": {"6": "failed"},
                                  "cards": [], "refusals": [], "weight": {"known": True}})
_fell_chain = CS.chain_verdict({"root": 21, "lane": "pc", "created": "2026-08-21T19:57:00",
                                "closed_at": "2026-08-21T20:42:23", "statuses": {"21": "failed"},
                                "cards": [], "refusals": [{"id": 21, "reason": "зависание"}],
                                "weight": {"known": True}})
print("      цепочка #6 (отказ владельца) → обрыв=%s | цепочка #21 (падение) → обрыв=%s (%s)"
      % (bool(_turned_chain.get("cause")), bool(_fell_chain.get("cause")), _fell_chain.get("cause")))
res.append(ok(not _turned_chain["break"] and not _turned_chain["unresolved"],
              "(7f) ЦЕПОЧКА с отказом владельца остаётся чистой — серия не рвётся"))
res.append(ok(_fell_chain["break"] and _fell_chain["cause"] == "отказ",
              "(7g) ЦЕПОЧКА с настоящим падением рвёт серию"))

print("\n(7з) ЖИВОЙ ПУТЬ НАБЛЮДАТЕЛЯ: реестр строится `ledger`, а не разовым засевом")
_prev_open = {"6": {"lane": "pc", "status": "in_progress", "head": "ultrathink ПРЕКРАТИТЬ"},
              "21": {"lane": "pc", "status": "in_progress", "head": "ultrathink"}}
_failed = [{"id": "6", "lane": "pc", "task_text": "t", "result": BTN, "at": NOW - 28000},
           {"id": "21", "lane": "pc", "task_text": "t", "result": FELL21, "at": NOW - 700}]
_led = {r["id"]: r["outcome"] for r in Q.ledger([], _prev_open, [], _failed, NOW)}
res.append(ok(_led == {"6": OR.REFUSAL, "21": OR.FAILURE},
              "(7и) обе половины разведены и на живом пути: %r" % _led))

print("\n(8) ДВЕ РЕАЛИЗАЦИИ ПРИЗНАКА ОТВЕЧАЮТ ОДИНАКОВО")
SAMPLES = [BTN, TXT, "  " + BTN, "- " + BTN, "**" + TXT, "\n\n   " + BTN, "> " + BTN,
           "«" + BTN, "`" + BTN, QUOTE5, FELL21, _quoted, "", "причина=run_timeout",
           "отчёт: " + BTN, BTN + "\nвторой строкой отчёт", "#1 " + BTN]
diff = [s for s in SAMPLES if OR.said(s) != CS._owner_said(s)]
res.append(ok(not diff, "(8a) хозяин признака и счёт серии сошлись на %d образцах: %r"
              % (len(SAMPLES), diff[:1])))

print("\n(9) ГРАНИЦЫ")
res.append(ok(by["5"]["outcome"] == "сдана" and by["5"]["why"] == "",
              "(9a) `done` с цитатой маркера в теле осталась СДАННОЙ"))
_ext = Q.seed([{"id": "30", "lane": "vps", "task_text": "t", "status": "failed",
                "result": BTN, "at": NOW - 100, "ext": "529 Overloaded"}], NOW)
res.append(ok("ext" not in _ext[0],
              "(9b) дословный ответ внешней системы к отклонённой не приезжает — там ответила кнопка"))
_ext2 = Q.seed([{"id": "31", "lane": "vps", "task_text": "t", "status": "failed",
                 "result": FELL21, "at": NOW - 100, "ext": "529 Overloaded"}], NOW)
res.append(ok(_ext2[0].get("ext") == "529 Overloaded",
              "(9c) у настоящего падения он остался БАЙТ-В-БАЙТ"))
res.append(ok(Q.fingerprint([{"id": "1", "status": "new", "lane": "vps"}]).startswith("v4"),
              "(9d) отпечаток несёт новую форму — прежний документ будет переписан один раз"))
_src_or = open(os.path.join(ROOT, "owner_refusal.py"), encoding="utf-8").read()
# РАЗРЕЗ ДЕЛАЕТСЯ НА ЧТЕНИИ. Строки, которые судили, обязаны остаться БАЙТ-В-БАЙТ теми же:
# ни статуса, ни текста в них не меняется — «rejected» появляется только в НАШЕМ учёте.
import copy                                                          # noqa: E402
_before = copy.deepcopy(CORPUS)
Q.seed(CORPUS, NOW)
Q.ledger([], {}, [], CORPUS, NOW)
res.append(ok(CORPUS == _before,
              "(9e) судимые строки очереди не изменены ни одним полем — это чтение, а не правка"))

print("\n(10) ЧИСТОТА РЕШЕНИЯ")
_tree = ast.parse(_src_or)
_imports = [n for n in ast.walk(_tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
res.append(ok(not _imports, "(10a) импортов РОВНО НОЛЬ (ast), рук у решения нет"))
run = invariants_check.CheckRun("OWNER_REFUSAL_PURE")
invariants_check.check_owner_refusal_pure(None, run)
res.append(ok(not run.findings, "(10b) живой страж чистоты говорит «чисто»: %s" % run.findings[:1]))
dirty = invariants_check.CheckRun("OWNER_REFUSAL_PURE")
invariants_check._OWNER_REFUSAL_PATH = os.path.join(ROOT, "expectations_run.py")
invariants_check.check_owner_refusal_pure(None, dirty)
invariants_check._OWNER_REFUSAL_PATH = None
res.append(ok(bool(dirty.findings), "(10c) и у стража есть зубы: модуль с руками он краснит"))
_inv = open(os.path.join(ROOT, "invariants_check.py"), encoding="utf-8").read()
res.append(ok('@register("OWNER_REFUSAL_PURE")' in _inv, "(10d) страж зарегистрирован — значит в гейте"))
qrun = invariants_check.CheckRun("QUEUE_STATE_PURE")
invariants_check.check_queue_state_pure(None, qrun)
res.append(ok(not qrun.findings,
              "(10e) слепок остался чистым с двумя импортами: %s" % qrun.findings[:1]))

bad = len(res) - sum(res)
print("\n%s: %d/%d проверок разреза «отказ владельца ≠ падение»"
      % ("OK" if bad == 0 else "ПРОВАЛ", sum(res), len(res)))
sys.exit(1 if bad else 0)
