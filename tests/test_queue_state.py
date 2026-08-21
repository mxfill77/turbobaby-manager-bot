"""СЛЕПОК СОСТОЯНИЯ ОЧЕРЕДИ В МОЗГЕ (14.08.2026).

ПОВОД (решение владельца 14.08): Штаб читает мозг сам, но состояния очереди там нет — в журнал
попадает только ИТОГ, а между «взял» и «сдал» пустота, из которой за трое суток родились четыре
дубля. Слепок закрывает пустоту, и главный риск у него ОДИН: соврать свежестью. Документ,
который выглядит снимком «сейчас», а показывает вчерашнее, хуже отсутствующего — по нему решают
«свободно/занято».

ГОЛДЕНЫ СТОЯТ НА ДОСЛОВНОМ ЖИВОМ СНИМКЕ очереди (14.08.2026 11:0x UTC, `get_pending` lane=all):
    #541 approved  Filipp-328-dec «[куратор владельцу цель 538] Разбор целей 538 (read-only)…»
    #536 in_progress «ultrathink ЦЕЛЬ: …»
и на дословной упавшей строке журнала демона (#519, сбой расписки claim 13.08).

Что доказывается:
    (1) ЗАМОК СВЕЖЕСТИ — исходов ТРИ, и ни один не сворачивается в другой: сверено · не сверено
        при живой памяти · не сверено без памяти. В последнем НЕ печатается ни одной строки
        состояния (пустой список читался бы как «очередь пуста»);
    (2) ПАМЯТЬ О ВЕРНОМ СНИМКЕ отказ НЕ стирает: время последнего верного и его тело остаются;
    (3) ВРЕМЕНА В ШАПКЕ АБСОЛЮТНЫЕ — замороженный в документе относительный возраст сам стал бы
        ложью о свежести;
    (4) ЗАПИСЬ ПО СМЕНЕ СОСТОЯНИЯ, а не по такту: то же состояние → write=False; взял · сдал ·
        ждёт владельца · встал в очередь → write=True; отказ подряд → одна запись на весь отказ;
    (5) РЕЕСТР ЗАКРЫТЫХ узнаёт исход БЕЗ дорогого вопроса и честно говорит «не сверен», когда
        списка упавших нет; падение, не виденное открытым, попадает в реестр из самого списка;
    (6) ЦЕНА — дорогой вопрос задаётся ТОЛЬКО по факту (ушла строка · реестра нет · старше часа);
    (7) ОТКАТ `QUEUE_STATE=0` — ветка мертва ДО единого обращения к мосту;
    (8) ИЗОЛЯЦИЯ — под гейтом/тестом в боевой мозг не пишется ничего;
    (9) ЖИВАЯ ДВЕРЬ — шаг целиком: пишет один раз, помнит отпечаток, при ПРОВАЛЕ записи отпечаток
        НЕ помечает (скажет на следующем прогоне);
   (10) ЧИСТОТА — у решения ровно один импорт, ни рук, ни собственных часов (ast).
"""
import ast
import os
import sys

# Корень берётся ОТ ФАЙЛА, а чужой боевой корень вычищается из пути: иначе прогон «до правки»
# через `git worktree` тянул бы модуль из БОЕВОГО дерева и зеленел бы на коде, которого в
# проверяемом дереве нет (ловушка метода, пойманная живьём 07.08).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT != "/root/turbobaby-manager-bot":
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != "/root/turbobaby-manager-bot"]
sys.path.insert(0, ROOT)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"

import queue_state as Q                                               # noqa: E402
import expectations_run as R                                          # noqa: E402


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


res = []
NOW = 1786705200.0                       # 14.08.2026 11:00:00 UTC — момент живого снимка

# ── ДОСЛОВНЫЕ живые строки очереди (снимок 14.08.2026, lane=all) ──────────────────────────
R541 = {"id": "541", "status": "approved", "lane": "vps", "from": "Filipp-328-dec",
        "since": NOW - 14400,
        "text": "[куратор владельцу цель 538] Разбор целей 538 (read-only) выбрал путь C — "
                "доставка проверенного"}
R536 = {"id": "536", "status": "in_progress", "lane": "vps", "from": "Filipp-328-dev",
        "since": NOW - 1020, "text": "ultrathink\n\nЦЕЛЬ: состояние очереди читается из мозга."}
R520_PC = {"id": "520", "status": "new", "lane": "pc", "from": "Filipp-pc-dec",
           "since": NOW - 600, "text": "[шаг 2/4 родитель 511] сверить зеркало гарда"}
LIVE = [R541, R536]
QOK = {"ok": True, "rows": LIVE, "err": ""}
QBAD = {"ok": False, "rows": [], "err": "HTTP 302"}

# ДОСЛОВНАЯ упавшая строка (журнал демона 13.08 14:03, отказ расписки claim)
F519 = {"id": "519", "lane": "vps", "task_text": "ultrathink\nЦЕЛЬ: разбор класса.",
        "result": "⏱ задача не уложилась: отказ расписки на write-POST (claim) — исход неизвестен",
        "at": NOW - 3600}

print("── (1) ЗАМОК СВЕЖЕСТИ: три исхода, и ни один не сворачивается в другой")
v_ok = Q.verdict({}, QOK, [], NOW)
res.append(ok(v_ok["verified"] and "снято: 2026-08-14 11:00:00 UTC" in v_ok["text"],
              "сверено: в шапке стоит ВРЕМЯ СНЯТИЯ"))
res.append(ok("НЕ СВЕРЕНО" not in v_ok["text"], "сверено: пометки «не сверено» в нём нет"))

v_bad = Q.verdict({"fp": "v2|x", "at": NOW - 7200, "text": "СТАРОЕ ТЕЛО СЛЕПКА"}, QBAD, [], NOW)
t = v_bad["text"]
res.append(ok(not v_bad["verified"] and "⚠️ НЕ СВЕРЕНО" in t, "не сверено: сказано ПЕРВОЙ строкой"))
res.append(ok("HTTP 302" in t, "не сверено: названа ПРИЧИНА, а не «что-то пошло не так»"))
res.append(ok("2026-08-14 09:00:00 UTC" in t,
              "не сверено: время последнего ВЕРНОГО снимка — абсолютное"))
res.append(ok("СТАРОЕ ТЕЛО СЛЕПКА" in t, "не сверено: прошлый слепок показан ЦЕЛИКОМ"))
res.append(ok("НЕЛЬЗЯ решать" in t, "не сверено: прямо сказано, что по нему не решать"))

v_never = Q.verdict({"fp": "v2|x"}, QBAD, [], NOW)
tn = v_never["text"]
res.append(ok("НИ РАЗУ" in tn and "НЕИЗВЕСТНО" in tn, "нет памяти: сказано, что верного не было"))
res.append(ok("В РАБОТЕ (" not in tn and "ЖДЁТ ВЛАДЕЛЬЦА (" not in tn
              and "очередь пуста" not in tn,
              "нет памяти: НИ ОДНОЙ строки состояния — пустой список читался бы как «пусто»"))

print("── (2) ПАМЯТЬ О ВЕРНОМ СНИМКЕ отказом не стирается (живая дверь шага)")
st = {"qstate": {"fp": Q.fingerprint(LIVE), "at": NOW - 600, "text": "ВЕРНОЕ ТЕЛО",
                 "open": Q.open_map(LIVE), "gone": [], "closed_at": NOW - 600}}
calls = []
R.write_queue_state = lambda text: (calls.append(text), True)[1]
R.failed_facts = lambda: []
out = R.queue_state_step(st, {"queue": QBAD}, NOW)
res.append(ok(out["wrote"] and st["qstate"]["at"] == NOW - 600,
              "после отказа время последнего верного НЕ сдвинуто на «сейчас»"))
res.append(ok(st["qstate"]["text"] == "ВЕРНОЕ ТЕЛО", "тело последнего верного сохранено"))
res.append(ok(st["qstate"]["open"] == Q.open_map(LIVE),
              "память об открытых строках отказом не обнулена"))
res.append(ok(st["qstate"]["fp"] == Q.UNVERIFIED_FP, "отпечаток отказа — один на весь отказ"))
out2 = R.queue_state_step(st, {"queue": QBAD}, NOW + 600)
res.append(ok(not out2["write"], "отказ ПОДРЯД второй записи не рождает"))

print("── (3) ВРЕМЕНА В ШАПКЕ АБСОЛЮТНЫЕ (замороженный «N назад» — та же ложь)")
head_ok = v_ok["text"].split("В РАБОТЕ")[0]
head_bad = t.split("────────────")[0]
res.append(ok("назад" not in head_ok, "верная шапка: относительного возраста в ней нет"))
res.append(ok("назад" not in head_bad, "шапка отказа: относительного возраста в ней нет"))
res.append(ok("на момент снятия" in v_ok["text"],
              "возраст строк внутри разделов подписан «на момент снятия»"))

print("── (4) ЗАПИСЬ ПО СМЕНЕ СОСТОЯНИЯ, а не по такту")
prev = {"fp": Q.fingerprint(LIVE)}
res.append(ok(not Q.verdict(prev, QOK, [], NOW)["write"], "то же состояние → НЕ пишем"))
res.append(ok(Q.verdict({}, QOK, [], NOW)["write"], "публикации не было → пишем"))
claimed = [R541, dict(R536, status="in_progress"), dict(R520_PC, status="in_progress")]
res.append(ok(Q.verdict(prev, {"ok": True, "rows": claimed}, [], NOW)["write"],
              "ВЗЯЛ (новая строка в работе) → пишем"))
res.append(ok(Q.verdict(prev, {"ok": True, "rows": [R541]}, [], NOW)["write"],
              "СДАЛ (строка ушла из открытых) → пишем"))
res.append(ok(Q.verdict(prev, {"ok": True, "rows": [R541, dict(R536, status="needs_approval")]},
                        [], NOW)["write"], "ЖДЁТ ВЛАДЕЛЬЦА (сменился статус) → пишем"))
res.append(ok(Q.verdict(prev, {"ok": True, "rows": LIVE + [R520_PC]}, [], NOW)["write"],
              "ВСТАЛА В ОЧЕРЕДЬ новая строка → пишем"))
res.append(ok(not Q.verdict(prev, {"ok": True, "rows": [R536, R541]}, [], NOW)["write"],
              "переставленные ответом строки сменой состояния НЕ являются"))
# Отпечаток сторожит и ТЕКСТ: реестр стал полным — карта строк та же, а фраза о полноте другая.
res.append(ok(Q.verdict(prev, QOK, [], NOW, NOW, "VPS", NOW - 86400)["write"],
              "реестр закрытых стал полным → документ переписывается ОДИН раз"))
res.append(ok(Q.fingerprint(LIVE) != Q.fingerprint(LIVE, True),
              "полнота реестра различима в отпечатке"))
res.append(ok(Q.verdict({"fp": Q.UNVERIFIED_FP, "at": NOW - 60, "text": "СТАРОЕ"},
                        QOK, [], NOW)["write"], "мост ожил → пишем сверенный слепок"))

print("── (5) РЕЕСТР ЗАКРЫТЫХ: исход узнаётся без дорогого вопроса, незнание названо")
was = Q.open_map([R541, R536])
g_fell = Q.ledger([], was, [R541], [F519 | {"id": "536"}], NOW)
res.append(ok(len(g_fell) == 1 and g_fell[0]["outcome"] == "упала", "ушла и есть среди упавших → «упала»"))
res.append(ok("отказ расписки" in g_fell[0]["why"], "причина падения взята из result задачи"))
g_done = Q.ledger([], was, [R541], [], NOW)
res.append(ok(g_done[0]["outcome"] == "сдана", "ушла, среди упавших нет → «сдана» (без вопроса про done)"))
g_unsure = Q.ledger([], was, [R541], None, NOW)
res.append(ok(g_unsure[0]["outcome"] == "не сверен",
              "списка упавших нет → исход «не сверен», а не «сдана»"))
res.append(ok("536" in Q.body([R541], g_unsure, NOW, NOW)
              and "ИСХОД НЕ СВЕРЕН" in Q.body([R541], g_unsure, NOW, NOW),
              "несверенный исход НАЗВАН в теле, а не спрятан среди сданных"))
g_unseen = Q.ledger([], {}, [R541], [F519], NOW)
res.append(ok(len(g_unseen) == 1 and g_unseen[0]["id"] == "519",
              "падение, которого не видели открытым, попадает в реестр из списка упавших"))
old = [{"id": "1", "at": NOW - 3 * 86400, "outcome": "сдана", "head": "древняя", "lane": "vps"}]
res.append(ok(Q.ledger(old, {}, [R541], [], NOW) == [], "запись старше 48 ч из реестра уходит"))
body24 = Q.body([R541], [{"id": "2", "at": NOW - 2 * 86400, "outcome": "сдана", "head": "x",
                          "lane": "vps"}], NOW, NOW)
res.append(ok("#2" not in body24, "в разделе суток чужого дня нет"))

print("── (5а) ЛОЖНЫЙ НУЛЬ: пустой реестр ≠ «ничего не закрылось» (живой случай 14.08 11:24)")
# Первый боевой прогон напечатал «за сутки не закрылось ничего», когда закрылось 26: реестр
# строится из наблюдения, а наблюдение началось минуту назад. Тот же род, что «тиков не было»
# против «не разобрал» (205c00b) и «баланс не сверен» против нуля.
young = Q.body([R541], [], NOW, NOW, since=NOW - 600)
res.append(ok("СПИСОК НЕ ПОЛОН" in young, "наблюдение моложе суток → список назван НЕПОЛНЫМ"))
res.append(ok("за сутки не закрылось ничего" not in young,
              "и фраза «не закрылось ничего» НЕ печатается вовсе"))
grown = Q.body([R541], [], NOW, NOW, since=NOW - 86400)
res.append(ok("СПИСОК НЕ ПОЛОН" not in grown and "за сутки не закрылось ничего" in grown,
              "наблюдение покрыло сутки → список полон и говорит это прямо"))
never = Q.body([R541], [], NOW, NOW, since=None)
res.append(ok("ещё не начато" in never, "наблюдения не было вовсе → сказано отдельно"))
res.append(ok("ПОЛНА" in grown, "половина упавших названа полной — её читают из очереди"))
res.append(ok("НЕ сверены" in Q.body([R541], [], NOW, None, since=NOW - 86400),
              "упавших не спрашивали → сказано, что исход может быть неточен"))
res.append(ok(Q.needs_seed(None) and not Q.needs_seed(NOW), "засев нужен ровно один раз"))
seeded = Q.seed([{"id": "538", "lane": "vps", "status": "done", "task_text": "ultrathink",
                  "result": "готово", "at": NOW - 3600},
                 {"id": "519", "lane": "vps", "status": "failed", "task_text": "ultrathink",
                  "result": "⏱ отказ расписки", "at": NOW - 7200},
                 {"id": "1", "lane": "vps", "status": "done", "task_text": "древняя",
                  "result": "", "at": NOW - 3 * 86400}], NOW)
res.append(ok([r["id"] for r in seeded] == ["538", "519"], "засев берёт ровно окно суток"))
res.append(ok(seeded[0]["outcome"] == "сдана" and seeded[1]["outcome"] == "упала",
              "исход засева берётся из СТАТУСА строки, а не угадывается"))
res.append(ok(seeded[1]["why"] == "⏱ отказ расписки", "причина падения переносится в засев"))

print("── (6) ЦЕНА: дорогой вопрос задаётся ТОЛЬКО по факту")
res.append(ok(Q.needs_closed(was, LIVE, None, NOW), "реестра нет → спрашиваем"))
res.append(ok(Q.needs_closed(was, [R541], NOW, NOW), "строка ушла из открытых → спрашиваем"))
res.append(ok(not Q.needs_closed(was, LIVE, NOW, NOW + 600),
              "ничего не ушло, реестр свежий → НЕ спрашиваем"))
res.append(ok(Q.needs_closed(was, LIVE, NOW, NOW + 3601), "реестр старше часа → спрашиваем"))
res.append(ok(not Q.needs_closed({}, LIVE, NOW, NOW + 60),
              "первый прогон с готовым реестром лишнего вопроса не платит"))

print("── (7) ОТКАТ QUEUE_STATE=0: ветка мертва ДО обращения к мосту")
touched = []
R.failed_facts = lambda: touched.append("failed")
R.write_queue_state = lambda text: touched.append("write") or True
os.environ["QUEUE_STATE"] = "0"
st_off = {}
off = R.queue_state_step(st_off, {"queue": QOK}, NOW)
res.append(ok(not off["write"] and not off["wrote"], "выключено → ни решения, ни записи"))
res.append(ok(touched == [], "выключено → мост не тронут НИ ОДНИМ вызовом"))
res.append(ok(st_off == {}, "выключено → состояние не заведено"))
os.environ.pop("QUEUE_STATE", None)

print("── (8) ИЗОЛЯЦИЯ: под гейтом в боевой мозг не пишется ничего")
import importlib                                                      # noqa: E402
R2 = importlib.reload(R)
sent = []
R2.__dict__["_bridge_used"] = sent
res.append(ok(R2._is_test_run(), "прогон опознан как тестовый (ORCH_TEST_MODE)"))
res.append(ok(R2.write_queue_state("тело фикстуры") is True,
              "запись под тестом возвращает успех, не трогая мост"))

print("── (9) ЖИВАЯ ДВЕРЬ: шаг целиком")
R2.failed_facts = lambda: []
seed_calls = []
R2.closed_facts = lambda: (seed_calls.append(1), [
    {"id": "538", "lane": "vps", "status": "done", "task_text": "ultrathink",
     "result": "готово", "at": NOW - 3600}])[1]
wrote = []
R2.write_queue_state = lambda text: (wrote.append(text), True)[1]
st2 = {}
s1 = R2.queue_state_step(st2, {"queue": QOK}, NOW)
res.append(ok(s1["wrote"] and len(wrote) == 1, "первый прогон: слепок записан один раз"))
res.append(ok("#541" in wrote[0] and "#536" in wrote[0], "в слепке НОМЕРА живых задач"))
res.append(ok("[куратор владельцу цель 538]" in wrote[0], "и ПЕРВАЯ СТРОКА цели каждой из них"))
res.append(ok("ЖДЁТ ВЛАДЕЛЬЦА (1)" in wrote[0], "approved стоит в разделе «ждёт владельца»"))
res.append(ok("В РАБОТЕ (1)" in wrote[0], "in_progress стоит в разделе «в работе»"))
res.append(ok(st2["qstate"]["fp"] == Q.fingerprint(LIVE, True),
              "отпечаток опубликованного запомнен (с меткой полного реестра)"))
res.append(ok(len(seed_calls) == 1 and "#538" in wrote[0],
              "реестр засеян с первого прогона — раздел суток не пуст при живых закрытиях"))
s2 = R2.queue_state_step(st2, {"queue": QOK}, NOW + 600)
res.append(ok(not s2["write"] and len(wrote) == 1, "второй прогон без смен: НЕ пишем"))
res.append(ok(len(seed_calls) == 1, "дорогой засев ВТОРОЙ раз не платится"))
s3 = R2.queue_state_step(st2, {"queue": {"ok": True, "rows": [R541]}}, NOW + 1200)
res.append(ok(s3["wrote"] and len(wrote) == 2, "задача закрылась → пишем"))
res.append(ok("сдано: #536" in wrote[1], "закрытая названа сданной в разделе суток"))

fp_before = st2["qstate"]["fp"]
R2.write_queue_state = lambda text: False                # мост отказал на записи
s4 = R2.queue_state_step(st2, {"queue": {"ok": True, "rows": []}}, NOW + 1800)
res.append(ok(s4["write"] and not s4["wrote"], "запись не прошла → честно сказано «не записано»"))
res.append(ok(st2["qstate"]["fp"] == fp_before,
              "провал записи отпечаток НЕ помечает — скажем на следующем прогоне"))

# ЗА ЧТО ЗАПЛАЧЕНО — ТО ЗАПОМНЕНО, даже когда писать было нечего: иначе тихая очередь платила
# бы дорогой засев каждые десять минут заново (дефект, пойманный на живом прогоне 14.08).
seed2 = []
R2.closed_facts = lambda: (seed2.append(1), [])[1]
R2.write_queue_state = lambda text: True
st3 = {}
R2.queue_state_step(st3, {"queue": QOK}, NOW)
R2.queue_state_step(st3, {"queue": QOK}, NOW + 600)          # состояние не менялось → не пишем
R2.queue_state_step(st3, {"queue": QOK}, NOW + 1200)
res.append(ok(len(seed2) == 1, "тихая очередь дорогой засев ПОВТОРНО не платит"))
res.append(ok(st3["qstate"].get("since") is not None,
              "начало наблюдения запомнено, хотя записи в док не было"))

print("── (10) ЧИСТОТА решения (ast): ни рук, ни собственных часов")
src = open(os.path.join(ROOT, "queue_state.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
imports |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
# 22.08.2026: импортов стало ДВА. Второй — `owner_refusal`, ВОКАБУЛЯР исходов закрытой задачи
# (у него самого импортов НОЛЬ, страж OWNER_REFUSAL_PURE), взятый ГОТОВЫМ вместо второго
# определения «чей это исход» рядом со слепком. Предмет проверки не изменился: рук и часов у
# слепка по-прежнему нет — это доказывают две строки ниже.
res.append(ok(imports == {"datetime", "owner_refusal"},
              f"импортов РОВНО ДВА — datetime и вокабуляр исходов (нашлось: {sorted(imports)})"))
_or_src = open(os.path.join(ROOT, "owner_refusal.py"), encoding="utf-8").read()
res.append(ok(not [n for n in ast.walk(ast.parse(_or_src))
                   if isinstance(n, (ast.Import, ast.ImportFrom))],
              "и у самого вокабуляра импортов НОЛЬ — рук через него не втечёт"))
banned = {"open", "exec", "eval", "compile", "__import__", "input", "print"}
hands = [n.func.id for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in banned]
res.append(ok(not hands, f"ни одной руки в теле решения (нашлось: {hands})"))
clock = [a.attr for n in ast.walk(tree) if isinstance(n, ast.Call) for a in [n.func]
         if isinstance(a, ast.Attribute) and a.attr in ("now", "utcnow", "today")]
res.append(ok(not clock, f"своих часов НЕТ — «сейчас» приносят руки (нашлось: {clock})"))

print("── формат времени и возраста (телефонная строка не должна разъезжаться)")
for sec, want in ((0, "0 мин"), (59, "0 мин"), (60, "1 мин"), (3599, "59 мин"),
                  (3600, "1 ч 00 мин"), (3660, "1 ч 01 мин"), (86400, "1 сут 0 ч"),
                  (90000, "1 сут 1 ч")):
    res.append(ok(Q.age(sec) == want, f"{sec} с → «{want}»"))
res.append(ok(Q.utc(None) == "время неизвестно", "нечитаемое время названо, а не подставлено"))
res.append(ok(Q.head("") == "(цель пуста)", "пустая цель названа, а не показана пустотой"))
res.append(ok(Q.head("  \n\nвторая строка") == "вторая строка", "первая СОДЕРЖАТЕЛЬНАЯ строка"))

print()
if all(res):
    print(f"OK: {len(res)}/{len(res)} проверок слепка состояния очереди")
    sys.exit(0)
print(f"FAIL: {sum(1 for r in res if not r)} из {len(res)} проверок красные")
sys.exit(1)
