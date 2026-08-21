"""ДОСЛОВНАЯ СТРОКА ВНЕШНЕГО ОТКАЗА ДОХОДИТ ДО СУДЬИ И ДО ВЛАДЕЛЬЦА (19.08.2026).

ПОВОД (разведка 18.08, коммит 2dfd4fd): дословный ответ внешней системы СОХРАНЯЕТСЯ — он лежит
в поле `result` упавшей строки очереди, и наблюдатель яруса 2 читает это поле ОБЕИХ полос одним
GET, за который уже заплачено. А до владельца он не доезжает: тело режется `[:400]` при чтении,
слепок берёт из него ПЕРВУЮ строку и режет её до 160 символов.

ЗАМЕР ЭТОГО ЗАХОДА (живой корпус артефактов отчётов, 24 упавших тела):
    внешним отказом упало 5, нашей причиной 19;
    дословная строка стоит на символах 406 · 463 · 530 · 534 · 641 — ЗА срезом 400 во всех пяти;
    первой строкой тела она не стоит НИ РАЗУ (5 из 5 машинных строк лежат третьими, первой идёт
    пересказ думателя) — то есть сегодня владельцу достаётся ПЕРЕСКАЗ, обрезанный на полуслове.

ГОЛДЕНЫ — ДОСЛОВНЫЕ ТЕЛА ЖИВЫХ УПАВШИХ ЗАДАЧ:
    #4  (18.08, vps) — «claude -p упал (exit=1): API Error: Server error mid-response…»,
        и В ТОМ ЖЕ ТЕЛЕ пересказ думателя «(API Error: … при exit=1)» на символе 105;
    #5  (18.08, pc)  — «claude exit=1: API Error: 529 Overloaded…» + наш хвост следов работы;
    #316 (05.08, vps) — машинный зачин ЕСТЬ («claude -p упал (exit=143):»), маркера НЕТ: SIGTERM,
        причина НАША;
    #469 (10.08) — таймаут прогона; #391 (07.08) — заявка на красное без карточки гарда.

Что доказывается:
    (1) КОРПУС — числа замера воспроизводятся живым решением на дословных телах;
    (2) ЗАМОК НА ЖИВЫХ ПРОИЗВОДИТЕЛЕЙ — зачин и хвост сверяются не с формулой, а с тем, что
        ПРЯМО СЕЙЧАС печатают `orchestrator_daemon._fail_card` и `status_truth.fail_result`;
    (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а) — внешний отказ: текст доехал ЦЕЛИКОМ и не обрезан;
    (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б) — наша причина: текст тоже доехал и внешним НЕ назвался;
    (5) ПОЗИЦИЯ, А НЕ ПОДСТРОКА — пересказ в прозе заявлением отказа не становится;
    (6) ЗАБОР ЧЕСТЕРТОНА — срез 400 стоит на месте, мимо него идёт ОДНА названная строка;
    (7) СЛЕПОК — строка печатается рядом с «почему», а не вместо неё;
    (8) СУДЬЯ — факт доезжает до `expectations.verdict` и честно говорит своё «не спрашивали»;
    (9) ГРАНИЦЫ — О8 не тронут ни одним условием, новых ожиданий нет, `lane_err` прежний;
   (10) ЦЕНА — ни одного нового обращения к мосту;
   (11) ЧИСТОТА — у решения ровно один импорт, ни рук, ни собственных часов (ast).
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

import failure_text as F                                              # noqa: E402
import expectations as E                                              # noqa: E402
import queue_state as Q                                               # noqa: E402
import expectations_run as R                                          # noqa: E402
import status_truth                                                   # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
NOW = 1787140000.0

# ═══════════ ДОСЛОВНЫЕ ТЕЛА (артефакты отчётов = поле `result` очереди, §1 разведки) ═════════
# #4 — полоса VPS, 18.08.2026 16:40 UTC. Тело целиком, все три строки.
B4 = (
    "[причина=model_refusal · отказ модели]: задача упала → думатель: halt, причина: Провал "
    "инфраструктурный (API Error: Server error mid-response при exit=1), а не дефект формулировки "
    "— переформулировкой не чинится; вдобавок текст ТЗ обрезан на блоке «ЗАПРЕТЫ: в боевы…», и "
    "сжатие 8 пунктов разведки с живым замером в ≤400 символов потеряло бы именно запрет писать в "
    "боевые узлы мозга — цена ошибки затёртые бизнес-правила, поэтому решает владелец.\n"
    "Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
    "claude -p упал (exit=1): API Error: Server error mid-response. The response above may be "
    "incomplete. СЛЕДОВ РАБОТЫ в окне 18.08 16:24–16:40 UTC не найдено (коммитов 0, записей "
    "журнала 0) — судя по уликам, работа не начиналась либо оборвалась до первого следа."
)
# #5 — полоса ПК, 18.08.2026 16:30 UTC. Перечень 52 коммитов ВНУТРИ нашего хвоста укорочен: до
# него цитата не доходит ни в одном случае, а всё, что ДО хвоста, стоит дословно.
B5 = (
    "задача упала → думатель: halt, причина: Провал не от формулировки: claude exit=1 по API 529 "
    "Overloaded (серверная перегрузка Anthropic) — переформулировка ТЗ этого не чинит, а само "
    "задание объёмно и рискует не влезть в таймаут даже при живом API; нужен человек.\n"
    "Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
    "НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=exec_error · ошибка выполнения]: claude "
    "exit=1: API Error: 529 Overloaded. This is a server-side issue, usually temporary — try again "
    "in a moment. If it persists, check https://status.claude.com.. СЛЕДЫ в окне 17.08 "
    "07:56–16:29 UTC: коммитов 52 (69a6c9f «откуда бот берёт цену: источник ЕСТЬ и рабочий»)."
)
EXT4 = "API Error: Server error mid-response. The response above may be incomplete."
EXT5 = ("API Error: 529 Overloaded. This is a server-side issue, usually temporary — try again "
        "in a moment. If it persists, check https://status.claude.com..")
# #23 — ЖИВАЯ строка полосы ПК (снята из очереди 19.08.2026, дословно). Ради неё правило и стало
# судить не по одному выученному маркеру: внешняя система отказала СОВСЕМ ДРУГИМИ словами, и это
# ровно ИСТЁКШАЯ СЕССИЯ — один из трёх случаев, ради которых заход делается.
B23 = (
    "НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=exec_error · ошибка выполнения]: claude "
    "exit=1: Failed to authenticate: OAuth session expired and could not be refreshed. СЛЕДЫ в "
    "окне 16.08 16:49–04:12 UTC: коммитов 69 (da4c065 «тень ЦЕПОЧКИ на полосе ПК»)."
)
EXT23 = "Failed to authenticate: OAuth session expired and could not be refreshed."

# #316 — НАША причина при ЖИВОМ машинном зачине: SIGTERM по таймауту/рестарту, маркера нет.
B316 = (
    "[причина=exec_error · ошибка выполнения]: задача упала → думатель: halt, причина: exit=143 — "
    "SIGTERM (убит по таймауту/рестарту), а не чинимая формулировка: ТЗ несёт 4 независимых фикса "
    "гарда + замер до/после на суточном корпусе — нужен владелец и «декомпозируй:».\n"
    "Перерождение не поможет (диагноз думателя выше), нужен человек.\n"
    "claude -p упал (exit=143): exit=143 СЛЕДОВ РАБОТЫ в окне 05.08 06:46–06:53 UTC не найдено "
    "(коммитов 0, записей журнала 0) — судя по уликам, работа не начиналась либо оборвалась до "
    "первого следа."
)
B469 = (
    "⏱ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=run_timeout · таймаут прогона]: таймаут "
    "2700s — headless прерван, задача не завершилась. СЛЕДЫ в окне 10.08 21:44–22:29 UTC: "
    "коммитов 1 (341ca33 «слой ожиданий на полосе ПК»)."
)
B391 = (
    "✋ НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА [причина=unbacked_red · заявка на красное без "
    "карточки гарда]: исполнитель напечатал заявку на красное, но ГАРД карточки не выписывал — "
    "значит красной операции он не видел и подтверждать нечего."
)
OURS_BODIES = [("#316 SIGTERM при живом машинном зачине", B316),
               ("#469 таймаут прогона", B469),
               ("#391 заявка на красное без карточки", B391)]

print("── (1) КОРПУС: числа замера воспроизводятся живым решением")
res.append(ok(F.verdict(B4)["kind"] == F.EXTERNAL and F.verdict(B5)["kind"] == F.EXTERNAL,
              "оба живых внешних отказа (vps и pc) опознаны внешними"))
res.append(ok(F.verdict(B23)["kind"] == F.EXTERNAL and F.verdict(B23)["text"] == EXT23,
              "ИСТЁКШАЯ СЕССИЯ (#23, живая очередь 19.08) — внешний отказ, слова её собственные"))
res.append(ok("API Error" not in B23,
              "и сказана она БЕЗ выученного маркера — потому вокабуляр и берётся готовым"))
res.append(ok(all(F.verdict(b)["kind"] == F.OURS for _, b in OURS_BODIES),
              "все три живых тела нашей причины опознаны нашими"))
res.append(ok(F.verdict(B4)["at"] > 400 and F.verdict(B5)["at"] > 400,
              "обе дословные строки стоят ЗА срезом 400 (в живых телах — 534 и 641)"))
res.append(ok(F.verdict(B4)["at"] == B4.rfind("API Error:"),
              "и это ПОСЛЕДНЕЕ вхождение маркера, а не первое"))
res.append(ok(Q.head(B4).startswith("[причина=model_refusal") and "claude -p упал" not in Q.head(B4),
              "первой строкой тела идёт ПЕРЕСКАЗ, машинной строки в ней нет"))

print("── (2) ЗАМОК: зачин и хвост сверены с ЖИВЫМИ производителями, а не с формулой")
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["MEM_MIN_MB"] = "0"
import datetime                                                       # noqa: E402
import orchestrator_daemon as D                                       # noqa: E402
live_card = D._fail_card("", "API Error: 529 Overloaded. Живой хвост.", 1)
res.append(ok(F.verdict(live_card)["kind"] == F.EXTERNAL,
              "карточка провала ЖИВОГО `_fail_card` читается как внешний отказ"))
res.append(ok(F.verdict(live_card)["text"] == "API Error: 529 Overloaded. Живой хвост.",
              "и цитата из неё — ровно то, что напечатал инструмент"))
res.append(ok(F.verdict(D._fail_card("", "exit=143", 143))["kind"] == F.OURS,
              "та же живая карточка с SIGTERM внешним отказом НЕ становится (rc=143)"))
# СВОДКА ЗАДАЧИ НЕ ВЫДАЁТСЯ ЗА ЧУЖИЕ СЛОВА: карточка склеивает stdout и хвост stderr СВОИМ
# разделителем, и цитируется ровно хвост. На живом корпусе таких тел 0 из 6 (stdout был пуст),
# но форма — живая, её печатает тот же `_fail_card`.
noisy = D._fail_card("сводка задачи, написанная исполнителем", "API Error: 529 Overloaded.", 1)
res.append(ok(F.verdict(noisy)["kind"] == F.EXTERNAL
              and F.verdict(noisy)["text"] == "API Error: 529 Overloaded.",
              "сводка задачи отрезана, в цитате только хвост инструмента"))
res.append(ok("сводка задачи" in noisy and "сводка" not in F.verdict(noisy)["text"],
              "наши слова в цитату не попали, хотя в карточке они есть"))
T0 = datetime.datetime(2026, 8, 18, 16, 24, tzinfo=datetime.timezone.utc)
T1 = datetime.datetime(2026, 8, 18, 16, 40, tzinfo=datetime.timezone.utc)
live_tail_none = status_truth.fail_result("claude -p упал (exit=1): API Error: 529 Overloaded.",
                                          "model_refusal", start=T0, end=T1,
                                          commits=[], writes=[])
res.append(ok(F.verdict(live_tail_none)["text"] == "API Error: 529 Overloaded.",
              "хвост ЖИВОГО `fail_result` (следов нет) в цитату не попал"))
live_tail_some = status_truth.fail_result("claude -p упал (exit=1): API Error: 529 Overloaded.",
                                          "model_refusal", start=T0, end=T1,
                                          commits=[("abc1234", "тема")], writes=[])
res.append(ok(F.verdict(live_tail_some)["text"] == "API Error: 529 Overloaded.",
              "хвост ЖИВОГО `fail_result` (следы есть) в цитату тоже не попал"))
res.append(ok(F.NEEDLES is status_truth._MODEL_NEEDLES,
              "вокабуляр отказа взят у `status_truth` ГОТОВЫМ — второго списка нет"))
res.append(ok("СЛЕДОВ РАБОТЫ в окне " in live_tail_none and "СЛЕДЫ в окне " in live_tail_some,
              "оба наших хвоста производитель печатает ровно теми словами, что мы режем"))

print("── (3) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (а): внешний отказ — текст доехал ЦЕЛИКОМ")
v4, v5 = F.verdict(B4), F.verdict(B5)
res.append(ok(v4["text"] == EXT4, "#4: цитата дословна и полна (%d симв.)" % len(v4["text"])))
res.append(ok(v5["text"] == EXT5, "#5: цитата дословна и полна (%d симв.)" % len(v5["text"])))
res.append(ok(not v4["text"].endswith("…") and not v5["text"].endswith("…"),
              "ни одна цитата не обрезана многоточием"))
res.append(ok(max(len(v4["text"]), len(v5["text"])) < F.TEXT_MAX,
              "обе короче потолка %d — потолок на живом корпусе не режет ничего" % F.TEXT_MAX))
res.append(ok("СЛЕДОВ РАБОТЫ" not in v4["text"] and "СЛЕДЫ в окне" not in v5["text"],
              "наш разбор следов работы в чужую цитату НЕ попал"))
res.append(ok(v4["cut"] == "наш разбор следов работы" and v5["cut"] == "наш разбор следов работы",
              "и обрезано это названо прямо, а не молча"))
res.append(ok("529 Overloaded" in v5["text"] and "credit" not in v5["text"].lower(),
              "перегрузка названа её собственными словами — судить о причине решение не берётся"))

print("── (4) ОТРИЦАТЕЛЬНЫЙ ТЕСТ (б): наша причина — текст доехал и внешним НЕ назвался")
for label, b in OURS_BODIES:
    v = F.verdict(b)
    res.append(ok(v["kind"] == F.OURS and v["text"] == "",
                  "%s: внешним отказом НЕ назван, цитаты нет" % label))
    rec = Q._with_ext({"why": Q.head(b)[:Q.WHY_MAX]}, R._failed_row({"result": b}))
    res.append(ok("ext" not in rec, "%s: поля внешнего ответа в записи НЕТ" % label))
    res.append(ok(rec["why"] == Q.head(b)[:Q.WHY_MAX] and len(rec["why"]) > 40,
                  "%s: текст причины доехал прежней дверью (%d симв.)" % (label, len(rec["why"]))))
res.append(ok(F.verdict(B316)["at"] is not None and F.verdict(B316)["kind"] == F.OURS
              and "причина наша" in F.verdict(B316)["why"],
              "#316: машинный зачин НАЙДЕН, отказа в нём нет — одной позиции мало, и это сказано"))
res.append(ok(F.verdict("")["kind"] == F.NOTHING and F.verdict(None)["kind"] == F.NOTHING,
              "пустое тело — третий исход «тела нет», а не «наша причина» наугад"))
res.append(ok(F.verdict("claude -p упал (exit=1):    ")["kind"] == F.OURS,
              "зачин есть, слов за ним нет — цитировать нечего, внешним не зовём"))
res.append(ok(F.verdict("claude exit=1: timeout after 2700s")["kind"] == F.OURS,
              "наш таймаут после машинного зачина внешним отказом не становится"))

print("── (5) ПОЗИЦИЯ, А НЕ ПОДСТРОКА")
res.append(ok(F.verdict(B4)["quoted"] is True,
              "#4: пересказ думателя рядом с заявлением ОПОЗНАН как цитата"))
only_quote = B4.split("\n")[0]
qv = F.verdict(only_quote)
res.append(ok(qv["kind"] == F.OURS and qv["quoted"] is True,
              "то же тело БЕЗ машинной строки → «наша причина», хотя маркер в нём есть"))
res.append(ok("пересказ" in qv["why"], "и причина отказа названа словом «пересказ»"))
for bad in ("см. в логе API Error: 529 Overloaded",
            "`API Error: 529` в кавычках",
            "| API Error: 529 в ячейке таблицы",
            "> API Error: 529 в цитате"):
    res.append(ok(F.verdict(bad)["kind"] == F.OURS, "вне позиции: %s" % bad[:34]))
res.append(ok(F.verdict("Code-сессия завершена: API Error: 529 Overloaded.")["text"]
              == "API Error: 529 Overloaded.",
              "журнальный зачин (готовый у lane_err) работает и здесь"))
# РЕГРЕСС ЖИВОГО ДЕФЕКТА (19.08, тела #5 и #9): наш хвост ЦИТИРУЕТ строки журнала, а в них живут
# те же машинные зачины. Пока хвост не снимали ПЕРВЫМ, «последним зачином в теле» оказывался
# зачин из НАШЕЙ ЖЕ цитаты, и ответом внешней системы становился обрывок нашего отчёта.
selfbite = ("НЕ ЗАКРЫТА [причина=exec_error]: claude exit=1: API Error: 529 Overloaded. "
            "СЛЕДЫ в окне 17.08: записей журнала 82 («DONE 2026-08-17 08:15 UTC: "
            "✅ Code-сессия завершена: Источник цены у бота есть и рабочий …обрезано»).")
sb = F.verdict(selfbite)
res.append(ok(sb["kind"] == F.EXTERNAL and sb["text"] == "API Error: 529 Overloaded.",
              "зачин ВНУТРИ нашей цитаты не перебивает настоящий — хвост снимается первым"))
res.append(ok("Источник цены" not in sb["text"] and "DONE" not in sb["text"],
              "и обрывок нашего отчёта ответом внешней системы не становится"))
two = ("claude exit=1: API Error: первый отказ.\nпотом\n"
       "claude -p упал (exit=1): API Error: последний отказ.")
res.append(ok(F.verdict(two)["text"] == "API Error: последний отказ.",
              "заявлений два → судится ПОСЛЕДНЕЕ (машинная строка ложится последней)"))

print("── (6) ЗАБОР ЧЕСТЕРТОНА: срез 400 на месте, мимо него идёт ОДНА названная строка")
res.append(ok(F.verdict(B4[:400])["kind"] == F.OURS and F.verdict(B5[:400])["kind"] == F.OURS,
              "из УРЕЗАННОГО тела оба внешних отказа читаются как «наша причина» — снимать "
              "цитату после среза бессмысленно"))
row = R._failed_row({"id": "4", "lane": "vps", "task_text": "ultrathink", "result": B4,
                     "updated": "2026-08-18T16:40:02Z"})
res.append(ok(len(row["result"]) == 400, "срез тела 400 символов СОХРАНЁН байт-в-байт"))
res.append(ok(row["ext"] == EXT4, "а дословная строка снята ДО среза и доехала целой"))
res.append(ok(len(row["ext"]) <= F.TEXT_MAX, "у неё свой потолок — тело мимо среза не едет"))
res.append(ok(sum(len(str(v)) for v in row.values()) < 900,
              "вся запись строки осталась короткой (%d симв.) — второй копией очереди "
              "состояние не становится" % sum(len(str(v)) for v in row.values())))
res.append(ok("ext" not in R._failed_row({"id": "316", "result": B316, "updated": None}),
              "у нашей причины поля внешнего ответа нет вовсе"))

print("── (7) СЛЕПОК: строка стоит РЯДОМ с «почему», а не вместо неё")
F4 = {"id": "4", "lane": "vps", "task_text": "ultrathink РАЗВЕДКА", "result": B4[:400],
      "ext": EXT4, "at": NOW - 600}
F316 = {"id": "316", "lane": "vps", "task_text": "ultrathink ЦЕЛЬ", "result": B316[:400],
        "at": NOW - 600}
was = {"4": {"lane": "vps", "head": "ultrathink РАЗВЕДКА"},
       "316": {"lane": "vps", "head": "ultrathink ЦЕЛЬ"}}
g = Q.ledger([], was, [], [F4, F316], NOW)
rec4 = [r for r in g if r["id"] == "4"][0]
rec316 = [r for r in g if r["id"] == "316"][0]
res.append(ok(rec4["ext"] == EXT4, "запись реестра несёт дословный ответ"))
res.append(ok(rec4["why"] == Q.head(B4[:400])[:Q.WHY_MAX],
              "и строка «почему» при этом БАЙТ-В-БАЙТ прежняя"))
res.append(ok("ext" not in rec316, "у нашей причины поля нет — запись прежняя целиком"))
body = Q.body([], g, NOW, NOW, since=NOW - 86400)
res.append(ok("ОТВЕТ ВНЕШНЕЙ СИСТЕМЫ, дословно: «%s»" % EXT4 in body,
              "в слепке цитата напечатана ЦЕЛИКОМ и в кавычках"))
res.append(ok(body.count("ОТВЕТ ВНЕШНЕЙ СИСТЕМЫ") == 1,
              "ровно одна такая строка — у нашей причины её нет"))
res.append(ok("почему: " in body, "строка «почему» осталась на месте"))
res.append(ok(body.index("почему") < body.index("ОТВЕТ ВНЕШНЕЙ"),
              "наш разбор идёт первым, чужие слова — следом"))
plain = Q.body([], [dict(rec4, ext=None), rec316], NOW, NOW, since=NOW - 86400)
res.append(ok("ОТВЕТ ВНЕШНЕЙ СИСТЕМЫ" not in plain,
              "без поля слепок БАЙТ-В-БАЙТ прежний"))
# Предмет проверки — «форма ПОДНЯТА относительно той, при которой строки внешнего ответа не было»
# (это была «2»). Литерал «3» сюда вписан 19.08 и протух 22.08, когда форма ушла до «4» ради
# разреза «отказ владельца ≠ падение»: голден, прибитый к одному числу, судил бы соседний заход,
# а не свой предмет.
try:
    _form = int(Q.FORM)
except (TypeError, ValueError):
    _form = -1
res.append(ok(_form >= 3, "форма слепка поднята (сейчас «%s»; при «2» строки внешнего ответа в "
                          "документе не было) — иначе документ остался бы с прежним текстом" % Q.FORM))
res.append(ok(Q.fingerprint([]) != "v2|", "отпечаток несёт новую форму"))

print("── (8) СУДЬЯ: факт доезжает до expectations.verdict")
st = {}
res.append(ok(R.failed_fact(st, NOW)["ok"] is False,
              "не спрашивали ни разу → честное «не знаю», а не «отказов нет»"))
R.remember_failed(st, [F4, F316], NOW)
f = R.failed_fact(st, NOW + 60)
res.append(ok(f["ok"] and f["ext"] == 1 and f["n"] == 2, "после ответа моста факт есть и считан"))
res.append(ok(f["last"]["text"] == EXT4, "судье доступна ДОСЛОВНАЯ строка последнего отказа"))
res.append(ok(f["last"]["id"] == "4" and f["last"]["lane"] == "vps",
              "с номером задачи и полосой — обе полосы одним фактом"))
res.append(ok(f["age"] == 60.0 and f["fetched"] == NOW,
              "факт СОСТАВНОЙ и несёт свой возраст — врать свежестью ему нечем"))
res.append(ok(all("result" not in r for r in f["rows"]),
              "в состояние уехала только названная строка, тела там нет"))
R.remember_failed(st, [dict(F4, id=str(i), ext="отказ %d" % i) for i in range(20)], NOW)
res.append(ok(len(st["failed"]["rows"]) == R.FAILED_KEEP,
              "память ограничена %d последними" % R.FAILED_KEEP))
# СУДЬЯ ВИДИТ ФАКТ РОВНО В ТОМ ЖЕ СЛОВАРЕ, что и все прочие: ключ приходит из `snapshot`.
# Сегодня его не читает ни одно ожидание — О8 не тронут, новых ожиданий заход не заводит; это
# плата за прямой запрет ТЗ, и потому здесь доказывается ровно две вещи: факт ДОЕЗЖАЕТ и вердикт
# от него НЕ МЕНЯЕТСЯ ни одним полем.
base = {"now": NOW, "queue": {"ok": False}, "daemon": {}, "splinter": {}, "delivery": {},
        "bridge": {}, "pc": {"ok": False}}
res.append(ok(E.verdict(dict(base), E.config({}))
              == E.verdict(dict(base, failed=f), E.config({})),
              "вердикт с фактом и без него совпадает поле в поле — О8 и соседи не задеты"))
snap_src = open(os.path.join(ROOT, "expectations_run.py"), encoding="utf-8").read()
res.append(ok('"failed": failed_fact(st, now)' in snap_src,
              "ключ `failed` стоит в снимке фактов, который и уходит судье"))

print("── (9) ГРАНИЦЫ: О8 не тронут, новых ожиданий нет")
res.append(ok(E.LANE_ERR_HEADS == ("Code-сессия завершена: ", "claude exit=1: "),
              "журнальные зачины О8 не изменены ни одним элементом"))
res.append(ok(E.lane_err("claude exit=1: API Error: 529 Overloaded.") == "529 Overloaded.",
              "`lane_err` отвечает ровно как прежде"))
res.append(ok(E.lane_err("claude -p упал (exit=1): API Error: 529.") == "",
              "и НЕ выучил зачин чужой поверхности — О8 судит ровно то, что судил"))
res.append(ok(len(E.KINDS) == 12 and "o8_lane_dead" in E.KINDS,
              "видов ожиданий по-прежнему 12 — новых заход не завёл"))
res.append(ok((E.LANE_RUN_ENV, E.LANE_RUN_DEFAULT) == ("EXPECT_LANE_RUN", 2.0),
              "порог О8 и его ручка прежние"))
src_ft = open(os.path.join(ROOT, "failure_text.py"), encoding="utf-8").read()
res.append(ok("lane_runs_state" not in src_ft and "_o8" not in src_ft,
              "решение не знает об О8 ни одним именем"))

print("── (10) ЦЕНА: ни одного нового обращения к мосту")
calls = []


class _BC:
    def __init__(self, timeout=None):
        pass

    def get_pending(self, status, lane=None):
        calls.append((status, lane))
        return {"ok": True, "items": [{"id": "4", "lane": "vps", "task_text": "t",
                                       "result": B4, "updated": "2026-08-18T16:40:02Z"}]}


import bridge_client                                                  # noqa: E402
bridge_client.BridgeClient = _BC
rows = R.failed_facts()
res.append(ok(calls == [("failed", "all")], "тот же ОДИН GET, что и до правки"))
res.append(ok(rows[0]["ext"] == EXT4, "и он же принёс дословную строку"))
st2 = {}
R.remember_failed(st2, rows, NOW)
res.append(ok(len(calls) == 1, "запоминание факта мост не трогает вовсе"))
res.append(ok(R.failed_fact(st2, NOW)["last"]["text"] == EXT4 and len(calls) == 1,
              "и выдача факта судье — тоже"))

print("── (11) ЧИСТОТА: у решения ровно один импорт, ни рук, ни часов")
tree = ast.parse(src_ft)
imports = sorted({a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                  for a in n.names}
                 | {(n.module or "").split(".")[0] for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom)})
res.append(ok(imports == ["expectations", "status_truth"],
              "импортов РОВНО ДВА, и оба — готовый вокабуляр: %s" % imports))
calls_st = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "status_truth"]
res.append(ok(calls_st == [], "вокабуляр ЧИТАЕТСЯ, а не зовётся (у status_truth есть subprocess)"))
bad = {"open", "exec", "eval", "compile", "__import__", "input"}
hits = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id in bad]
res.append(ok(hits == [], "ни одного вызова записи/исполнения: %s" % hits))
import invariants_check                                               # noqa: E402
run = invariants_check.CheckRun("FAILURE_TEXT_PURE")
invariants_check.check_failure_text_pure(None, run)
res.append(ok(not run.findings, "живой страж чистоты говорит «чисто»: %s" % run.findings[:1]))
dirty = invariants_check.CheckRun("FAILURE_TEXT_PURE")
invariants_check._FAILURE_TEXT_PATH = os.path.join(ROOT, "expectations_run.py")
invariants_check.check_failure_text_pure(None, dirty)
invariants_check._FAILURE_TEXT_PATH = None
res.append(ok(bool(dirty.findings), "и у стража есть зубы: модуль с руками он краснит"))
inv_src = open(os.path.join(ROOT, "invariants_check.py"), encoding="utf-8").read()
res.append(ok('@register("FAILURE_TEXT_PURE")' in inv_src, "страж зарегистрирован — значит в гейте"))

bad_n = len(res) - sum(res)
print("\n%s: %d/%d проверок дословной строки внешнего отказа"
      % ("OK" if bad_n == 0 else "ПРОВАЛ", sum(res), len(res)))
sys.exit(1 if bad_n else 0)
