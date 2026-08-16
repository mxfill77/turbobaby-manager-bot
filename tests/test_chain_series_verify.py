"""СВЕРКА ЖИВОГО СЧЁТА С РЕПЛЕЕМ (10.08.2026, рамка §8г, цель «состояние серии — в файле демона»).

Живой счёт демона — единственный источник числа серии, а число без сверки есть ощущение с
точностью до знака. Прежняя `--verify` печатала обе пары чисел и ВСЕГДА возвращала 0: расхождение
было неотличимо от совпадения ни кодом, ни словом. Здесь оно становится КРАСНЫМ — и красным
остаётся, потому что чинить его файлом запрещено: молча подогнанный счётчик перестаёт быть
свидетелем, и следующий раз соврёт уже без свидетелей.

ГЛАВНАЯ АСИММЕТРИЯ, которую сьют пиннит с обеих сторон: реплей структурно СЛЕП там, где очередь
затёрла тело карточки её же вердиктом (замер 10.08 — тело восстановимо у 46 вмешательств из 106),
и ровно поэтому файл вообще заведён. Значит «файл видит обрыв, слепой реплей молчит» — не
расхождение, а счётное число; «реплей доказывает обрыв, файл его не знает» — расхождение ВСЕГДА:
это направление, в котором счёт надувает серию.

Секции:
(1) страж читателя: прибор сверки не умеет писать — ни файла состояния, ни любого другого (ast)
(2) сходится: одинаковые картины → 0
(3) расхождение (красное): реплей доказал обрыв · разные сорта · файл против себя · чужая цепочка
(4) слепота реплея — НЕ расхождение, а число
(5) не сверено: нет файла · пуст · факты мира не прочитаны · общая почва пуста
(6) сверка НИЧЕГО не пишет: байты файла состояния до и после КРАСНОГО прогона совпали
(7) зеркало демона: вердикты файла в приборе и в `_series_derive` демона — одни и те же
(8) файл отвечает на вопросы рамки: серия · рекорд (не уменьшается при урезке) · последний обрыв
(9) личность пишущего: боевой файл состояния пишет только боевой процесс
"""
import ast
import hashlib
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
# ПРЕДМЕТ ЭТОГО СЬЮТА — ПРЕЖНЕЕ ОПРЕДЕЛЕНИЕ ЧИСТОТЫ (сходимость файла и реплея, память рекорда).
# Правило зелёного (16.08.2026, RULE_ON_COUNT) считает по-другому и судится своим сьютом
# `tests/test_rule_on_count.py`; здесь оно принудительно выключено — тот же приём изоляции
# легаси-сьютов, что у CURATOR/PLAN_ADAPT/CARD_DUTY (setdefault не хватает: флаг доезжает из
# боевого .env через load_dotenv демона).
os.environ["RULE_ON_COUNT"] = "0"
# Признак тест-прогона ставим САМИ (ручной запуск идёт и без гейта): пушей в личку и боевых
# файлов состояния у этого сьюта быть не должно ни при каком способе запуска.
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []
import chain_series as CS                                              # noqa: E402
import chain_series_report as CSR                                      # noqa: E402

BLIND = ("тело карточки затёрто вердиктом очереди — операция из снимка не восстановима")
WHY_NOISE = ("операция service:splinter случилась 2026-08-10T09:09:45 — ДО ответа владельца: "
             "карточка просила разрешения на то, что уже произошло")
WHY_MANUAL = "перезапуск splinter в 2026-08-10T15:00:00 не попадает ни в одно окно исполнения"


def fchain(root, cards=(), statuses=None, refusals=()):
    """Цепочка в ФОРМЕ ФАЙЛА демона: статусы — словарь id→статус, карточки уже закрыты."""
    return {"root": root, "lane": "vps", "created": "2026-08-10T08:00:00",
            "closed_at": "2026-08-10T10:00:00",
            "statuses": statuses or {str(root): "done"}, "cards": list(cards),
            "refusals": list(refusals), "weight": {"commits": [], "restarts": 0, "known": True}}


def rchain(root, cards=(), statuses=("done",), refusals=()):
    """Та же цепочка в ФОРМЕ РЕПЛЕЯ: статусы — список (так их складывает `build`)."""
    return {"root": root, "lane": "vps", "created": "2026-08-10T08:00:00",
            "closed_at": "2026-08-10T10:00:00", "ids": [root], "statuses": list(statuses),
            "cards": list(cards), "refusals": list(refusals),
            "weight": {"commits": [], "restarts": 0, "known": True}}


CARD_NOISE = {"id": 437, "open": False, "sort": CS.NOISE, "why": WHY_NOISE, "at": "2026-08-10T09:20:35"}
CARD_WILL = {"id": 425, "open": False, "sort": CS.WILL, "why": "операция позже ответа",
             "at": "2026-08-09T18:58:48"}
CARD_MANUAL = {"id": None, "open": False, "sort": CS.MANUAL, "why": WHY_MANUAL,
               "at": "2026-08-10T15:00:00"}
CARD_BLIND = {"id": 437, "sort": CS.UNKNOWN, "why": BLIND, "at": "2026-08-10T09:20:35"}

def merge(base, extra):
    """Слияние с ЧИСЛОВЫМИ ключами: `dict(x, **{449: …})` питон не берёт (ключи-кваргсы — строки)."""
    out = dict(base)
    out.update(extra)
    return out


# Файл: 435 оборвана ШУМОМ, 449 и 420 чисты. Числа `derived` проставлены РУКАМИ (голден), а не
# посчитаны прибором, — иначе слой «файл сам себе» проверял бы сам себя. Порядок счёта — по
# НОМЕРУ корня (420 → 435 → 449), поэтому обрыв стоит в середине: серия 1, рекорд 1.
FILE_OK = {"chains": {"435": fchain(435, [CARD_NOISE]), "449": fchain(449), "420": fchain(420)},
           "derived": {"current": 1, "best": 1, "chains": 3, "best_ever": 1,
                       "last_break": {"root": 435, "cause": CS.NOISE, "at": "2026-08-10T09:20:35",
                                      "why": WHY_NOISE},
                       "line": "серия цепочек: идёт 2"}}
REPLAY_OK = {435: rchain(435, [dict(CARD_NOISE)]), 449: rchain(449), 420: rchain(420)}

print("(1) СТРАЖ ЧИТАТЕЛЯ — прибор сверки не умеет писать")
src = open(os.path.join(REPO, "chain_series_report.py"), encoding="utf-8").read()
tree = ast.parse(src)
writes = []
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        mod = getattr(getattr(f, "value", None), "id", "")
        if name in ("dump", "write", "writelines", "replace", "remove", "unlink", "rename",
                    "rmtree", "mkdir", "makedirs", "truncate", "copy", "copy2"):
            writes.append(name)
        if name == "open":
            mode = ""
            for a in list(n.args[1:2]) + [k.value for k in n.keywords if k.arg == "mode"]:
                mode = getattr(a, "value", "") or ""
            if any(ch in str(mode) for ch in "wax+"):
                writes.append("open(%s)" % mode)
        if mod == "shutil":
            writes.append("shutil." + name)
res.append(ok(not writes, "(1) ни одного пишущего вызова во всём модуле сверки (%s)" % writes))
руки = [n.func.attr for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and getattr(n.func.value, "id", "") == "cs"]
res.append(ok("series" in руки and "chain_verdict" in руки,
              "(1) судит ТЕМИ ЖЕ чистыми функциями, что и демон (chain_verdict/series)"))

print("(2) СХОДИТСЯ")
code, lines = CSR.verify(FILE_OK, REPLAY_OK)
res.append(ok(code == 0, "(2) одинаковые картины → код 0 (получено %s)" % code))
res.append(ok(any("СХОДИТСЯ на 3 цепочках" in x for x in lines),
              "(2) названо, НА СКОЛЬКИХ цепочках сошлось — почва не подразумевается"))
res.append(ok(any("последний обрыв: 2026-08-10T09:20 · шум · цепочка 435" in x for x in lines),
              "(2) дата последнего обрыва и его сорт названы (рамка §8г)"))

print("(3) РАСХОЖДЕНИЕ — красное")
# (а) САМОЕ ОПАСНОЕ НАПРАВЛЕНИЕ: реплей доказал обрыв (тело уцелело), файл его не знает.
replay_break = merge(REPLAY_OK, {449: rchain(449, [dict(CARD_NOISE, id=451)])})
code, lines = CSR.verify(FILE_OK, replay_break)
res.append(ok(code == 1, "(3) реплей доказал обрыв, файл его не знает → код 1 (%s)" % code))
res.append(ok(any("цепочка 449" in x and "РАСХОЖДЕНИЕ" in x for x in lines),
              "(3) расхождение названо ПОИМЁННО — цепочкой, а не общим числом"))
res.append(ok(any("Файл НЕ правим" in x for x in lines),
              "(3) итог прямо говорит, что файл не правится"))
# (б) оба разобрали ОДНУ И ТУ ЖЕ запись 437, но сорта разные (ручная карта у реплея несёт номер —
# в отличие от приписанного перезапуска, у которого номера нет вовсе; тот случай в (4б))
code, _ = CSR.verify(FILE_OK, merge(REPLAY_OK, {435: rchain(435, [dict(CARD_MANUAL, id=437)])}))
res.append(ok(code == 1, "(3) файл «шум» против реплея «ремонт» по ОДНОЙ записи → код 1 (%s)"
              % code))
# (в) файл сам себе: `derived` не выводится из его же цепочек (правка руками)
code, lines = CSR.verify(dict(FILE_OK, derived=dict(FILE_OK["derived"], current=9)), REPLAY_OK)
res.append(ok(code == 1 and any("сам себе противоречит" in x for x in lines),
              "(3) подправленный derived → код 1: тихая правка файла ловится (%s)" % code))


def with_chain(root):
    """Файл + ещё одна цепочка. `derived` НАМЕРЕННО без чисел: этот случай судит про снимок, а не
    про самосогласованность файла — один случай проверяет одно."""
    return {"chains": merge(FILE_OK["chains"], {str(root): fchain(root)})}


# (г) цепочка, которой в снимке нет вовсе (внутри охвата снимка)
code, lines = CSR.verify(with_chain(440), REPLAY_OK)
res.append(ok(code == 1 and any("в снимке очереди её НЕТ" in x for x in lines),
              "(3) файл знает цепочку 440, снимок — нет → код 1 (%s)" % code))
# ГРАНИЦА той же ветки: цепочка НОВЕЕ снимка обвинением не является и сверки НЕ отменяет —
# иначе живая сверка была бы вечно «не сверено»: файл всегда знает то, что закрылось после снимка.
code, lines = CSR.verify(with_chain(500), REPLAY_OK)
res.append(ok(code == 0 and any("новее снимка" in x for x in lines),
              "(3) цепочка новее снимка — не расхождение, а оговорка (%s)" % code))

# (д) ФОРМА: цепочка, которую демон написать не мог — след пробы в боевом файле (живой случай
# 10.08.2026: синтетическая 101 по ИСХОДУ сошлась с настоящей и дала зелёное).
junk = {"chains": {"101": dict(fchain(101), created="")}}
code, lines = CSR.verify(junk, {101: rchain(101)})
res.append(ok(code == 1 and any("БЕЗ ДАТЫ РОЖДЕНИЯ" in x for x in lines),
              "(3) цепочка без даты рождения → код 1, хотя ИСХОД сошёлся (%s)" % code))
res.append(ok(CSR.verify({"chains": {"101": fchain(101)}}, {101: rchain(101)})[0] == 0,
              "(3) та же цепочка С датой рождения — зелёное: судится форма, не подозрение"))

print("(4) СЛЕПОТА РЕПЛЕЯ — не расхождение, а число")
blind = merge(REPLAY_OK, {435: rchain(435, [dict(CARD_BLIND)])})
code, lines = CSR.verify(FILE_OK, blind)
res.append(ok(code == 0, "(4) файл видит обрыв, слепой реплей молчит → код 0 (%s)" % code))
res.append(ok(any("слепота реплея 1" in x for x in lines),
              "(4) слепота посчитана отдельным числом, а не спрятана"))
# И ОБРАТНОЕ: слепота НЕ покрывает опасное направление — обрыв реплея красный и при ней
code, _ = CSR.verify(FILE_OK, merge(blind, {449: rchain(449, [dict(CARD_NOISE, id=451)])}))
res.append(ok(code == 1, "(4) слепота не оправдывает пропущенный файлом обрыв (%s)" % code))
# и числа при слепоте расходиться ВПРАВЕ — за это красного нет
code, lines = CSR.verify(FILE_OK, blind)
res.append(ok(not any("числа на общей почве разошлись" in x for x in lines),
              "(4) разошедшиеся при слепоте числа расхождением не объявляются"))
# ВТОРАЯ ФОРМА СЛЕПОТЫ: реплей не разобрал запись КАК ВМЕШАТЕЛЬСТВО вовсе (карточки нет — ответ
# владельца затёрт вместе со следом). Тела он не видел так же, как в первой форме.
code, lines = CSR.verify(FILE_OK, merge(REPLAY_OK, {435: rchain(435)}))
res.append(ok(code == 0 and any("слепота реплея 1" in x for x in lines),
              "(4) реплей не увидел вмешательства вовсе — тоже слепота, а не спор (%s)" % code))
# А ВОТ ЕСЛИ РАЗОБРАЛ ТУ ЖЕ ЗАПИСЬ И СУДИЛ ИНАЧЕ — это спор по существу, красное
code, lines = CSR.verify(FILE_OK, merge(REPLAY_OK, {435: rchain(435, [dict(CARD_WILL, id=437)])}))
res.append(ok(code == 1 and any("реплей разобрал сам" in x for x in lines),
              "(4) ту же запись 437 реплей разобрал в ВОЛЮ → расхождение по существу (%s)" % code))

print("(4б) ПРИПИСАННЫЙ РЕМОНТ — хозяин условен у обеих сторон, сверяется ЧИСЛО")
f_man = {"chains": {"435": fchain(435, [dict(CARD_MANUAL)]), "449": fchain(449)}}
r_man = {435: rchain(435), 449: rchain(449, [dict(CARD_MANUAL)])}
code, lines = CSR.verify(f_man, r_man)
res.append(ok(code == 0, "(4б) перезапуск без номера записи повешен на РАЗНЫЕ цепочки → не "
                         "расхождение (%s)" % code))
res.append(ok(any("ремонт руками на общей почве: файл 1 · реплей 1" in x for x in lines),
              "(4б) вместо хозяина сверено число ремонтов — и оно сошлось"))

print("(5) НЕ СВЕРЕНО — третий исход")
res.append(ok(CSR.verify(None, REPLAY_OK)[0] == 2, "(5) файла нет → код 2, а не 0"))
res.append(ok(CSR.verify({"chains": {}}, REPLAY_OK)[0] == 2,
              "(5) файл пуст (счёт ещё не считал) → код 2: пустое пересечение не «сходится»"))
res.append(ok(CSR.verify(FILE_OK, REPLAY_OK, unread=["splinter"])[0] == 2,
              "(5) журнал юнита не прочитан → код 2 (реплей не судит ремонт руками)"))
res.append(ok(CSR.verify(FILE_OK, REPLAY_OK, windows_read=False)[0] == 2,
              "(5) окна исполнения не прочитаны → код 2"))
code, lines = CSR.verify({"chains": {"500": fchain(500)}}, REPLAY_OK)
res.append(ok(code == 2 and any("общая почва пуста" in x for x in lines),
              "(5) общая почва пуста → код 2 (%s)" % code))

print("(6) СВЕРКА НИЧЕГО НЕ ПИШЕТ — живой прогон")
tmp = tempfile.mkdtemp(prefix="cc_series_verify_")
state_path = os.path.join(tmp, "chain_series.json")
with open(state_path, "w", encoding="utf-8") as f:
    json.dump(FILE_OK, f, ensure_ascii=False)
before = hashlib.sha256(open(state_path, "rb").read()).hexdigest()
snap_path = os.path.join(tmp, "snap.json")
with open(snap_path, "w", encoding="utf-8") as f:
    json.dump([{"id": 435, "status": "done", "lane": "vps", "created": "2026-08-10T08:00:00Z",
                "updated": "2026-08-10T10:00:00Z", "task_text": "ЦЕЛЬ: раз", "result": "готово"},
               {"id": 449, "status": "done", "lane": "vps", "created": "2026-08-10T08:10:00Z",
                "updated": "2026-08-10T10:10:00Z", "task_text": "ЦЕЛЬ: два", "result": "готово"}],
              f, ensure_ascii=False)
CSR.unit_starts = lambda since: ([], [])          # журнал systemd в тесте не зовём
CSR.origin_commits = lambda: {}
CSR.metrics_windows = lambda: {}
rc = CSR.main(["--snapshot", snap_path, "--verify", "--state", state_path])
after = hashlib.sha256(open(state_path, "rb").read()).hexdigest()
res.append(ok(before == after,
              "(6) байты файла состояния после сверки НЕ изменились (код сверки %s)" % rc))
res.append(ok(rc == 1, "(6) живой прогон красный: файл знает 420, снимок — нет, и это видно (%s)"
              % rc))

print("(7) ЗЕРКАЛО ДЕМОНА — вердикты файла считаются одинаково там и тут")
import orchestrator_daemon as OD                                       # noqa: E402
mirror = {"chains": {k: dict(v) for k, v in FILE_OK["chains"].items()}}
d = OD._series_derive(mirror)
own = CS.series([CSR._file_verdicts(FILE_OK)[r] for r in sorted(CSR._file_verdicts(FILE_OK))])
res.append(ok(d["current"] == own["current"] and d["best"] == own["best"]
              and d["chains"] == own["chains"],
              "(7) демон и прибор выводят из ОДНОГО состояния одно (current %s/%s)"
              % (d["current"], own["current"])))
res.append(ok(d["current"] == 1 and d["best"] == 1 and d["chains"] == 3,
              "(7) голден-числа фикстуры: 3 цепочки, обрыв 435 в середине → серия 1 (%s/%s)"
              % (d["current"], d["chains"])))

print("(8) ФАЙЛ ОТВЕЧАЕТ НА ВОПРОСЫ РАМКИ")
res.append(ok(CS.series([])["last_break"] is None,
              "(8) обрывов не было → last_break пуст, а не выдуман"))
lb = d.get("last_break") or {}
res.append(ok(lb.get("cause") == CS.NOISE and lb.get("root") == 435 and lb.get("at"),
              "(8) последний обрыв: дата и СОРТ лежат в файле отдельным полем (%s)" % lb))
res.append(ok(d.get("best_ever") == d.get("best"),
              "(8) рекорд серии записан рядом с текущей (%s)" % d.get("best_ever")))
# УРЕЗКА: цепочки забылись — рекорд обязан выстоять, последний обрыв остаться
short = {"derived": dict(d), "chains": {"600": fchain(600)}}
d2 = OD._series_derive(short)
res.append(ok(d2["best_ever"] == d["best_ever"] and d2["best"] == 1,
              "(8) после урезки окно даёт best=%s, а рекорд НЕ уменьшился (%s)"
              % (d2["best"], d2["best_ever"])))
res.append(ok((d2.get("last_break") or {}).get("root") == 435,
              "(8) дата последнего обрыва пережила забывание старых цепочек"))

print("(9) ЛИЧНОСТЬ ПИШУЩЕГО — боевой файл пишет только боевой процесс")
os.environ.pop("CC_SERIES_FILE", None)
os.environ.pop("ORCH_TEST_MODE", None)
res.append(ok(OD._series_file() == OD.CHAIN_SERIES_TEST_FILE and not OD._IS_DAEMON,
              "(9) импорт со стороны (харнесс, сьют) в боевой файл НЕ пишет: %s"
              % os.path.basename(OD._series_file())))
was = OD._IS_DAEMON
OD._IS_DAEMON = True
res.append(ok(OD._series_file() == OD.CHAIN_SERIES_FILE,
              "(9) боевой процесс пишет боевой путь — счёт не переезжает во временный"))
os.environ["CC_SERIES_FILE"] = os.path.join(tmp, "явный.json")
res.append(ok(OD._series_file().endswith("явный.json"),
              "(9) явная подмена CC_SERIES_FILE сильнее всего — свой сьют управляем"))
OD._IS_DAEMON = was
os.environ["ORCH_TEST_MODE"] = "1"
dsrc = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
mainf = next(n for n in ast.walk(ast.parse(dsrc))
             if isinstance(n, ast.FunctionDef) and n.name == "main")
sets = [t.id for n in ast.walk(mainf) if isinstance(n, ast.Assign)
        for t in n.targets if isinstance(t, ast.Name) and t.id == "_IS_DAEMON"]
res.append(ok(sets == ["_IS_DAEMON"],
              "(9) флаг ставит РОВНО main() демона — не импорт и не окружение"))
shutil.rmtree(tmp, ignore_errors=True)

print("\nИтог: %d/%d PASS" % (sum(res), len(res)))
fails = sum(1 for r in res if not r)
if fails:
    print("FAIL: %d тест(а/ов) не прошли" % fails)
    sys.exit(1)
