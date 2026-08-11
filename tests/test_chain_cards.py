"""ЖУРНАЛ РОЖДЕНИЯ КАРТОЧЕК — то, чего не хватает при РАЗБОРЕ, сохраняется при РОЖДЕНИИ
(11.08.2026, цель «снизить долю цепочек с неразобранным сортом»).

ОСНОВАНИЕ ЧИСЛОМ (снимок очереди 11.08.2026, 489 записей, 304 закрытых цепочки): неразобранных
цепочек 64, и разложены они так — **тело карточки затёрто 58 · семья не наблюдается 6**; ни
одного случая «сорт не читается» и ни одной висящей карточки в корпусе нет. Затёртое тело делится
по тому, КТО мог его сохранить: 41 карточка полосы pc (VPS видит их только пока они висят в
needs_approval), 17 — красные карточки process_new полосы vps. Семья, которая не наблюдается,
не лечится ничем и остаётся «неизвестно» честно.

Голдены — ДОСЛОВНЫЕ карточки живой очереди, те же, что у сьюта серии: 437 (рестарт splinter
СЛУЧИЛСЯ внутри жизни карточки → ШУМ) и 425 (случился ПОСЛЕ ответа → ВОЛЯ). Здесь они проходят
не через уцелевшее тело, а через журнал — и обязаны дать ТОТ ЖЕ сорт.

Секции:
(1) формат журнала: запись/чтение, «не прочитан» ≠ «пуст», битые строки считаются, дедуп, урезка
(2) ЗАМОК замера: тело затёрто и журнала нет → цепочка НЕ РАЗОБРАНА, серию не удлиняет
(3) журнал даёт сорт: дословные 437/425 через журнал = тот же вердикт; чужой номер не течёт
(4) руки демона: карточка пишется и в состояние, и в журнал; pc-карточка — при первом виде
(5) ЗАМОК демона: запись не удалась → цепочка помечена «не разобрана», серия не выросла
(6) изоляция: боевые пути не тронуты ни одним слоем
(7) границы: CHAIN_SERIES=0 → журнала нет; пороги не тронуты; без журнала разбор байт-в-байт
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
import chain_cards as CC                                               # noqa: E402
import chain_series as CS                                             # noqa: E402
import chain_series_report as REP                                     # noqa: E402
import curator_ops                                                    # noqa: E402

# ── ДОСЛОВНЫЕ карточки живой очереди ────────────────────────────────────────────────────────
C437 = ("Нужно твоё «да» на рестарт splinter: фикс скана просрочек (коммит 6e525d6) лежит в "
        "origin/main и гейт зелёный, но живой процесс держит старый код и считает по-старому — "
        "исходное ТЗ рестарт запрещало намеренно, поэтому сам не делаю.")
# ДОСЛОВНАЯ карточка 429 (отклонена владельцем): выкладка моста — семья, которую с этой машины
# не наблюдают вовсе. Журнал её тело сохранит, а сорт всё равно останется НЕИЗВЕСТНЫМ.
C429 = ("Нужно твоё «да» на выкат моста (`clasp push` + `clasp redeploy` прод-деплоя): правки "
        "живут только в папке — прод-мост о них не знает")
OPS437 = [o["key"] for o in curator_ops.operations(C437)]
OPS429 = [o["key"] for o in curator_ops.operations(C429)]

tmp = tempfile.mkdtemp(prefix="cc_cards_test_")
J = os.path.join(tmp, "chain_cards.jsonl")

print("(1) ФОРМАТ ЖУРНАЛА")
res.append(ok(CC.load(os.path.join(tmp, "нет-такого.jsonl")) is None,
              "(1) журнала нет → None («НЕ ПРОЧИТАН»), а не пустой словарь"))
CC.note(J, 437, "2026-08-10T08:59:03", "vps", CC.BORN, OPS437, C437)
j = CC.load(J)
res.append(ok(j is not None and set(j["cards"]) == {437} and j["broken"] == 0,
              "(1) запись читается обратно по своему номеру"))
res.append(ok(j["cards"][437]["ops"] == OPS437 == ["service:splinter"],
              "(1) операции сохранены тем же словарём, каким машина зовёт их сама (%s)" % OPS437))
res.append(ok(j["cards"][437]["head"] == C437[:CC.HEAD] and len(j["cards"][437]["head"]) <= 200,
              "(1) тело хранится головой (200 симв.) — журнал не вторая копия очереди"))
CC.note(J, 437, "2026-08-10T09:00:00", "vps", CC.BORN, [], "другое тело")
j = CC.load(J)
res.append(ok(j["lines"] == 1 and j["cards"][437]["ops"] == OPS437,
              "(1) повтор по тому же номеру не плодит строк и не переписывает первую запись"))
with open(J, "a", encoding="utf-8") as f:
    f.write("{битая строка\n")
j = CC.load(J)
res.append(ok(j["broken"] == 1 and set(j["cards"]) == {437},
              "(1) битая строка НЕ молчит — она посчитана, а не пропущена молча"))
empty = os.path.join(tmp, "empty.jsonl")
open(empty, "w", encoding="utf-8").close()
res.append(ok(CC.load(empty) == {"cards": {}, "lines": 0, "broken": 0},
              "(1) пустой журнал — это {} и прочитан; «не прочитан» отвечает None"))
# урезка: журнал не растёт вечно, режется СТАРОЕ
big = os.path.join(tmp, "big.jsonl")
with open(big, "w", encoding="utf-8") as f:
    for i in range(1, CC.KEEP + 1):
        f.write(json.dumps(CC.entry(i, "2026-08-01T00:00:00", "vps", CC.BORN, [], "x")) + "\n")
CC.note(big, 999999, "2026-08-11T00:00:00", "vps", CC.BORN, ["service:splinter"], "новая")
jb = CC.load(big)
res.append(ok(jb["lines"] == CC.KEEP and 999999 in jb["cards"] and 1 not in jb["cards"],
              "(1) урезка держит потолок %d строк и режет СТАРОЕ (новое дороже)" % CC.KEEP))

print("(2) ЗАМОК ЗАМЕРА — тела нет и в журнале его нет → цепочка НЕ РАЗОБРАНА")
# Дословная форма живого корпуса: карточка дошла до владельца, он ответил, и очередь ЗАТЁРЛА её
# тело своим вердиктом. Так выглядят 58 из 64 неразобранных цепочек замера 11.08.
CARD_ROW = {"id": 500, "lane": "vps", "from": "Filipp-328-dev", "status": "failed",
            "task_text": "ultrathink ЦЕЛЬ: проба замка", "created": "2026-08-10T08:59:03.000Z",
            "updated": "2026-08-10T09:20:35.000Z", "result": "отклонено Филиппом"}
NEXT_ROW = {"id": 501, "lane": "vps", "from": "Filipp-328-dev", "status": "done",
            "task_text": "ultrathink ЦЕЛЬ: соседняя", "created": "2026-08-10T09:30:00.000Z",
            "updated": "2026-08-10T09:40:00.000Z", "result": "готово"}
STARTS_IN = [{"family": "service:splinter", "at": "2026-08-10T09:09:45", "unit": "splinter"}]
STARTS_AFTER = [{"family": "service:splinter", "at": "2026-08-10T19:24:34", "unit": "splinter"}]


def run(journal, starts=STARTS_IN, rows=(CARD_ROW, NEXT_ROW)):
    # windows=None — «окон исполнения нет, ремонт руками не обвиняем»: старт юнита здесь ФАКТ
    # для сорта карточки, а не улика против цепочки; иначе фикстура мерила бы приписку, а не
    # предмет сьюта (ровно тот же довод, по которому build не судит ремонт без окон METRICS).
    v, ch, order, _r = REP.build(list(rows), starts, None, None, journal)
    return v, CS.series(v), ch


v0, s0, _c0 = run(None)
res.append(ok(v0[0]["unresolved"] and not v0[0]["break"],
              "(2) тело затёрто, журнала нет → цепочка не разобрана и не обрыв"))
res.append(ok(s0["current"] == 1 and s0["unresolved"] == 1 and s0["current_unresolved"] == 1,
              "(2) серию она НЕ удлиняет: длина 1 (соседняя цепочка), перешагнула 1"))
res.append(ok(s0["clean"] == 1 and s0["chains"] == 2,
              "(2) в чистые она не попала — «не знаю» больше не значит «ничего не было»"))
v_empty, s_empty, _ = run({})
res.append(ok(v_empty[0]["unresolved"] and s_empty["unresolved"] == 1,
              "(2) журнал ЕСТЬ, но этой карточки в нём нет → тот же замок (задним числом не гадаем)"))

print("(3) ЖУРНАЛ ДАЁТ СОРТ — дословные карточки через журнал дают ТОТ ЖЕ вердикт")
JN = {500: CC.entry(500, "2026-08-10T08:59:03", "vps", CC.BORN, OPS437, C437)}
v1, s1, c1 = run(JN, STARTS_IN)
res.append(ok(v1[0]["break"] and v1[0]["cause"] == CS.NOISE and not v1[0]["unresolved"],
              "(3) 437 через журнал: рестарт 09:09:45 внутри жизни карточки → ШУМ, обрыв"))
res.append(ok("журнал рождения" in str(c1[500]["cards"][0]["why"]),
              "(3) вердикт прямо называет, откуда взято тело"))
v2, s2, _ = run(JN, STARTS_AFTER)
res.append(ok(not v2[0]["break"] and not v2[0]["unresolved"] and s2["current"] == 2,
              "(3) 425-подобный случай: операция ПОСЛЕ ответа → ВОЛЯ, цепочка чистая, серия 2"))
JU = {500: CC.entry(500, "2026-08-10T08:59:03", "vps", CC.BORN, OPS429, C429)}
v3, s3, _ = run(JU, STARTS_IN)
res.append(ok(v3[0]["unresolved"] and not v3[0]["break"] and OPS429 == ["bridge_deploy"],
              "(3) семья, которую отсюда не наблюдают, остаётся НЕИЗВЕСТНОЙ и с журналом (%s)"
              % OPS429))
JX = {777: CC.entry(777, "2026-08-10T08:59:03", "vps", CC.BORN, OPS437, C437)}
v4, _s4, _ = run(JX)
res.append(ok(v4[0]["unresolved"],
              "(3) запись ЧУЖОГО номера в сорт не течёт — сортируется только своя карточка"))
# запись журнала = ДОКАЗАТЕЛЬСТВО, что карточка дошла до владельца
SILENT = dict(CARD_ROW, result="готово", status="done")
v5, _s5, c5 = run({500: CC.entry(500, "2026-08-10T08:59:03", "vps", CC.BORN, OPS437, C437)},
                  STARTS_IN, (SILENT, NEXT_ROW))
res.append(ok(len(c5[500]["cards"]) == 1 and v5[0]["break"],
              "(3) запись в журнале доказывает, что карточка висела: вмешательство не потеряно, "
              "даже когда в очереди не осталось ни следа ответа"))

print("(4) РУКИ ДЕМОНА — тело пишется и в состояние, и в журнал")
import orchestrator_daemon as OD                                      # noqa: E402
OD._series_commits = lambda result, since: []          # git в тесте не зовём
OD._series_units_now = lambda: {"splinter": "2026-08-10T09:09:45"}
os.environ["CHAIN_SERIES"] = "1"
d1 = tempfile.mkdtemp(prefix="cc_cards_daemon_")
os.environ["CC_SERIES_FILE"] = os.path.join(d1, "chain_series.json")
os.environ["CC_CARDS_FILE"] = os.path.join(d1, "chain_cards.jsonl")
TASK435 = {"id": 435, "lane": "vps", "created": "2026-08-10T08:20:00.000Z",
           "task_text": "ultrathink ЦЕЛЬ: скан просрочек"}
TASK437 = {"id": 437, "lane": "vps", "created": "2026-08-10T08:59:03.083Z",
           "task_text": "[куратор владельцу цель 435] " + C437}
OD._series_note_terminal(TASK435, "done", "готово")
OD._series_note_card(437, TASK437, C437)
jd = CC.load(os.environ["CC_CARDS_FILE"])
st = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
res.append(ok(jd is not None and jd["cards"].get(437, {}).get("ops") == ["service:splinter"],
              "(4) карточка 437 легла в журнал с операцией — замер её сорт восстановит"))
res.append(ok(jd["cards"][437]["src"] == CC.BORN and jd["cards"][437]["lane"] == "vps",
              "(4) журнал говорит, ОТКУДА знание: рождение, полоса vps"))
res.append(ok((st["chains"]["435"]["cards"][0] or {}).get("journal") is True,
              "(4) состояние живого счёта помнит, что журнал принял карточку"))
# pc-карточка: VPS видит её только пока она висит
PC_ROWS = [{"id": 601, "lane": "pc", "status": "needs_approval",
            "task_text": "[шаг 2/3 родитель 600] правка", "result": "NEEDS_APPROVAL: op=other | "
            + C437},
           {"id": 602, "lane": "pc", "status": "done", "task_text": "[шаг 3/3 родитель 600] x",
            "result": "готово"}]
OD._pc_carded.clear()
OD._series_note_pc_cards(PC_ROWS)
jd = CC.load(os.environ["CC_CARDS_FILE"])
res.append(ok(601 in jd["cards"] and 602 not in jd["cards"],
              "(4) pc: записана ТОЛЬКО висящая карточка — у остальных тела нет и вопроса нет"))
res.append(ok(jd["cards"][601]["src"] == CC.SEEN and jd["cards"][601]["lane"] == "pc",
              "(4) pc: источник назван честно — «первый вид», раньше VPS увидеть не мог"))
lines_before = CC.load(os.environ["CC_CARDS_FILE"])["lines"]
OD._pc_carded.clear()
OD._series_note_pc_cards(PC_ROWS)
res.append(ok(CC.load(os.environ["CC_CARDS_FILE"])["lines"] == lines_before,
              "(4) pc: каждый оборот демона видит ту же карточку — дублей в журнале нет"))
res.append(ok("601" not in json.dumps(json.load(open(os.environ["CC_SERIES_FILE"],
                                                     encoding="utf-8")), ensure_ascii=False),
              "(4) pc-карточка в состояние ЖИВОГО счёта не идёт: терминалов полосы pc демон не "
              "видит, такая цепочка не закрылась бы никогда"))

print("(5) ЗАМОК ДЕМОНА — сохранить не удалось → цепочка «не разобрана»")
OD._SERIES_LOST.clear()
os.environ["CC_SERIES_FILE"] = os.path.join(d1, "нет-каталога", "chain_series.json")
crashed = False
try:
    OD._series_note_card(438, dict(TASK437, id=438), C437)
except Exception:                                                     # noqa: BLE001
    crashed = True
res.append(ok(not crashed and 438 in OD._SERIES_LOST,
              "(5) провал записи не бросает наверх и НЕ забывается — карточка взята на карандаш"))
os.environ["CC_SERIES_FILE"] = os.path.join(d1, "chain_series.json")
OD._series_cards_tick(set())
st = json.load(open(os.environ["CC_SERIES_FILE"], encoding="utf-8"))
lost = [c for ch in st["chains"].values() for c in ch["cards"] if c.get("id") == 438]
res.append(ok(lost and lost[0].get("sort") == "" and "не удалось" in lost[0]["why"],
              "(5) первым же тиком она выложена пометкой «сорт не читается»"))
ch438 = [ch for ch in st["chains"].values() if any(c.get("id") == 438 for c in ch["cards"])][0]
vv = CS.chain_verdict(dict(ch438, statuses=list((ch438.get("statuses") or {}).values()),
                           cards=list(ch438.get("cards") or [])))
res.append(ok(vv["unresolved"] and not vv["break"] and vv["unreadable"] >= 1,
              "(5) вердикт такой цепочки — НЕ РАЗОБРАНА: серию не удлиняет и не рвёт"))
res.append(ok(not OD._SERIES_LOST,
              "(5) выложенная карточка снята с карандаша — второй раз не запишется"))

print("(6) ИЗОЛЯЦИЯ — боевые пути не тронуты ни одним слоем")
prod_j = os.path.join(REPO, "chain_cards.jsonl")
sha_before = (hashlib.sha256(open(prod_j, "rb").read()).hexdigest()
              if os.path.exists(prod_j) else "нет файла")
res.append(ok(OD.CHAIN_CARDS_FILE == os.path.join(OD.REPO, "chain_cards.jsonl"),
              "(6) боевой путь журнала по умолчанию: %s" % OD.CHAIN_CARDS_FILE))
res.append(ok(OD._cards_file() != OD.CHAIN_CARDS_FILE,
              "(6) подстановка сьюта (CC_CARDS_FILE) уводит запись из боевого журнала"))
os.environ.pop("CC_CARDS_FILE", None)
res.append(ok(OD._cards_file() == OD.CHAIN_CARDS_TEST_FILE,
              "(6) забыли подставить — второй слой (ORCH_TEST_MODE) держит"))
was_test_mode = os.environ.pop("ORCH_TEST_MODE", None)
res.append(ok(not OD._IS_DAEMON and OD._cards_file() != OD.CHAIN_CARDS_FILE,
              "(6) сняты ОБА признака — третий слой (личность пишущего) не пускает в боевой"))
os.environ["ORCH_TEST_MODE"] = was_test_mode or "1"
sha_after = (hashlib.sha256(open(prod_j, "rb").read()).hexdigest()
             if os.path.exists(prod_j) else "нет файла")
res.append(ok(sha_before == sha_after,
              "(6) боевой журнал за прогон не изменился ни на байт"))

print("(7) ГРАНИЦЫ")
os.environ["CC_CARDS_FILE"] = os.path.join(d1, "off", "chain_cards.jsonl")
os.environ["CC_SERIES_FILE"] = os.path.join(d1, "off", "chain_series.json")
os.environ["CHAIN_SERIES"] = "0"
OD._series_note_card(439, dict(TASK437, id=439), C437)
OD._series_note_pc_cards(PC_ROWS)
res.append(ok(not os.path.exists(os.environ["CC_CARDS_FILE"]),
              "(7) CHAIN_SERIES=0 → журнала нет вовсе: ветка мертва ДО сбора фактов"))
os.environ["CHAIN_SERIES"] = "1"
res.append(ok(CS.WEIGHT_MIN_SHARE == 0.25 and CS.SERIES_TARGET == 30,
              "(7) порог веса и критерий выхода из фазы не тронуты (0.25 / 30)"))
src_cs = open(os.path.join(REPO, "chain_series.py"), encoding="utf-8").read()
res.append(ok(src_cs.count("\nimport ") == 1 and "\nimport re" in src_cs,
              "(7) решение осталось чистым: импорт по-прежнему ровно один"))
v_old, s_old, _ = run(None)
v_bare, _ch, _o, _r = REP.build(list((CARD_ROW, NEXT_ROW)), STARTS_IN, None, None)
res.append(ok(v_bare == v_old and v_old[0]["unresolved"] and s_old["current"] == 1,
              "(7) без журнала разбор БАЙТ-В-БАЙТ прежний: то же «не разобрана», та же длина"))
src_rep = open(os.path.join(REPO, "chain_series_report.py"), encoding="utf-8").read()
res.append(ok("journal=None" in src_rep,
              "(7) журнал у замера — необязательный аргумент: прежний зов работает как работал"))

shutil.rmtree(tmp, ignore_errors=True)
shutil.rmtree(d1, ignore_errors=True)
for k in ("CC_SERIES_FILE", "CC_CARDS_FILE"):
    os.environ.pop(k, None)
print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
