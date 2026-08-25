# -*- coding: utf-8 -*-
"""СЛОВАРЬ ОБЪЕКТОВ КЛАССА `confirmed` ЗНАЛ ПОЛЯ ДВУХ ДВЕРЕЙ ИЗ ШЕСТИ (26.08.2026).

Ключ `confirmed=true` жёстко требуют ШЕСТЬ дверей моста (зеркало `bridge_prod/`, @83; счёт снят
заново — `confirmed !== true` встречается ровно шесть раз):

    set_fleet_oil  ReadFleet:266   · set_fleet_service ReadFleet:423  — объект `number`
    edit_event     BotData:631     — `msg_id`
    service_undo   ServiceUndo:243 — `act`
    set_caps       QuotePrice:316  — `caps`
    toggle_cap     QuotePrice:376  — `model` + `on`

Имя первых двух стоит в RED_TOKEN_HIT, поэтому у них СВОЙ хит и своя ветка объекта. У остальных
имени в словаре нет — хит схлопывается в общий `confirmed`, а его словарь объектов читал РОВНО
байк и клиента. Объект выходил ПУСТЫМ, `card_gate` гасил карточку (правило верное, НЕ тронуто),
и в этой ветке `_guard_write_marker` и `_push` НЕДОСТИЖИМЫ — красное умирало молча, строкой в
журнал, которого не читает ни один механизм. Живой случай: заход 25.08 упёрся в дверь отмены
записи ТО и не смог ни исполнить, ни СПРОСИТЬ (разбор: docs/artifacts/2026-08-26-guard-deadlock.md).

ЧТО ИМЕННО ЧИНИТСЯ: извлечение объекта (`_detail_parts`), а не правило карточки. Расширение
ОДНОСТОРОННЕЕ — имена только добавляются и приписываются ПОСЛЕ прежних, поэтому прежний объект
остаётся НАЧАЛОМ нового (секция 3), карточек может стать больше и не может стать меньше.

ГЛАВНАЯ ЛОВУШКА, из-за которой этого мало (секция 4). `_entity_blocktype` судит ТЕМ ЖЕ извлечением,
но там «объект есть» означает НЕ карточку, а deny без кнопки (задача failed). Пусти новые имена и
туда — команда, которая сегодня молча уходит в журнал с решением `ask`, стала бы ЖЁСТКИМ БЛОКОМ:
карточек не прибавилось бы, прибавилось бы отказов, то есть ровно наоборот замыслу. Поэтому забор
судит прежним объектом (`doors=False`) и его решения побайтно прежние.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ: чистые функции + main() в ЭТОМ процессе (stdin/stdout/_push подменены).
Красные литералы собраны КОНКАТЕНАЦИЕЙ (образец — test_guard_card_min): иначе гард краснеет на
САМОМ файле теста и правка файла становится невозможной.
"""
import atexit
import io
import json
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"       # страховка: ни одна карточка не уйдёт в Telegram

if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG  # noqa: E402

# ── красные литералы по кускам ────────────────────────────────────────────────
CONF = "confirmed" + "=" + "True"
CONF_K = '"' + "confirmed" + '": True'
SFO = "set_fleet_" + "oil"
SFS = "set_fleet_" + "service"
EE = "edit_" + "event"
CB = "create_" + "booking"

TMP = tempfile.mkdtemp(prefix="pt_doors_").replace(os.sep, "/")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)
PY = "venv/bin/python3"

# ЖИВЫЕ формы вызова дверей. Тела сняты с сигнатур зеркала `bridge_prod/` дословно:
#   ServiceUndo.js:232  body: { act:String, by:String, confirmed:Bool }
#   QuotePrice.js:309   body: { confirmed: true, caps: [{model, cap, active}, ...] }
#   QuotePrice.js:371   body: { confirmed: true, model: String, on: Bool|'on'|'off'|'да'|'нет' }
ACT = "mt93f8k91a7ea"                    # ключ акта из живого случая 25.08 (байк 5960)
BODY_UNDO = "c._post('service_undo', act='" + ACT + "', by='Filipp', " + CONF + ")"
BODY_CAPS = ("c._post('set_caps', caps=[{'model': 'NMAX 155', 'cap': 3}], " + CONF + ")")
BODY_TOGGLE = "c._post('toggle_cap', model='NMAX 155', on='off', " + CONF + ")"
# Сырое тело запроса — вторая живая форма той же двери (именованных аргументов нет вовсе).
BODY_UNDO_RAW = ("c.post(url, json={'action': 'service_undo', '" + "act" + "': '" + ACT
                 + "', " + CONF_K + "})")


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def cmd_of(body):
    return PY + ' -c "' + body + '"'


def seen(body):
    """→ (kind, hit, объект, число) для ЖИВОЙ формы команды."""
    kind, hit, blob = PG.classify(cmd_of(body))
    o, n = PG.card_min(hit, blob)
    return kind, hit, o, n


def fixture(name, body):
    path = TMP + "/" + name
    with open(path, "w", encoding="utf-8") as f:
        f.write("# фикстура\n" + body + "\n")
    return path


res = []


def run_main(cmd, task_id=""):
    """main() В ЭТОМ процессе → (решение-JSON, [карточки в пуше], [события журнала])."""
    logp = TMP + "/guard_%d.log" % len(res)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    pushed, out = [], io.StringIO()
    saved = (sys.stdin, sys.stdout, PG._push, os.environ.get("CC_TASK_ID"))
    sys.stdin, sys.stdout, PG._push = io.StringIO(payload), out, pushed.append
    os.environ["PRETOOL_GUARD_LOG"] = logp
    os.environ["PRETOOL_BLOCK_DIR"] = TMP
    os.environ["CC_TASK_ID"] = task_id
    try:
        PG.main()
    except SystemExit:
        pass
    finally:
        sys.stdin, sys.stdout, PG._push = saved[0], saved[1], saved[2]
        os.environ.pop("PRETOOL_GUARD_LOG", None)
        os.environ.pop("PRETOOL_BLOCK_DIR", None)
        if saved[3] is None:
            os.environ.pop("CC_TASK_ID", None)
        else:
            os.environ["CC_TASK_ID"] = saved[3]
    events = []
    try:
        with open(logp, encoding="utf-8") as f:
            events = [json.loads(ln)["event"] for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        pass
    return out.getvalue(), pushed, events


print("(1) ДВЕРИ, ПАДАЮЩИЕ В ОБЩИЙ КЛАСС `confirmed`: объект НАЗЫВАЕТСЯ, карточка рождается:")
for label, body, want in (("отмена записи ТО (act)", BODY_UNDO, "акт " + ACT),
                          ("отмена, сырое тело запроса", BODY_UNDO_RAW, "акт " + ACT),
                          ("блок капов (caps)", BODY_CAPS, "блок капов"),
                          ("переключение капа (model)", BODY_TOGGLE, "модель NMAX 155")):
    kind, hit, o, n = seen(body)
    res.append(ok(kind == "red" and hit == "confirmed",
                  label + ": красное, общий класс (kind=%s hit=%s)" % (kind, hit)))
    res.append(ok(want in o, label + ": ОБЪЕКТ назван — %r" % o))
    res.append(ok(PG.card_gate(hit, o, n) is True, label + ": КАРТОЧКА выписана (была бы журналом)"))
    res.append(ok(PG.marker_has_object(hit, PG._card(hit, PG.classify(cmd_of(body))[2])) is True,
                  label + ": маркер демону УХОДИТ (вторая линия пропускает)"))

_k, _h, _o, _n = seen(BODY_TOGGLE)
res.append(ok("состояние off" in _n, "переключение капа: ЧИСЛО — то, чем значение станет: %r" % _n))

print("(2) ОТРИЦАТЕЛЬНЫЕ БЛИЗНЕЦЫ: СЛОВО в тексте объекта НЕ даёт (карточки по-прежнему нет):")
# Ровно те формы, которыми правило объекта живёт с 29.07: имя поля лежит ДАННЫМИ в читающей
# разведке. Если бы новые имена красили по подстроке, эти четыре стали бы карточками владельцу.
NEG = (
    ("имя поля в списке слов", "keys = ['" + "act" + "', 'model', 'caps']; print(keys)"),
    ("имя поля в докстринге", '"""разбор поля act и model двери отмены"""' + "; print(1)"),
    ("имя поля в шаблоне поиска", "re.search(r'\\\\bact=', open(p).read())"),
    ("сравнение строк отчёта", "print('дверь отмены несёт act и by')"),
)
for label, body in NEG:
    kind, hit, blob = PG.classify(cmd_of(body))
    o, n = PG.card_min(hit, blob)
    res.append(ok(o == "", label + ": объекта нет — %r (kind=%s)" % (o, kind)))

# Тот же текст, но С ключом подтверждения: красное есть, а объекта всё равно нет — значит слово
# само по себе объектом не становится ни при каком классе.
kind, hit, blob = PG.classify(cmd_of("w = ['" + "act" + "', 'caps']; d = {" + CONF_K + "}"))
o, n = PG.card_min(hit, blob)
res.append(ok(hit == "confirmed" and o == "",
              "красное + имена полей ДАННЫМИ → объекта нет, карточки нет (%r)" % o))

print("(3) РАСШИРЕНИЕ, А НЕ ПОДМЕНА: прежние объекты целы и остаются НАЧАЛОМ новых:")
OLD = (
    ("байк", "c._post('service_undo', number='6789', " + CONF + ")", "байк 6789"),
    ("клиент", "c._post('x', client='Jack', " + CONF + ")", "клиент Jack"),
)
for label, body, want in OLD:
    kind, hit, o, n = seen(body)
    res.append(ok(o.startswith(want), label + ": прежнее извлечение цело — %r" % o))
# Прежний объект — ПРЕФИКС нового: байк назван первым, акт приписан следом.
kind, hit, o, n = seen("c._post('service_undo', number='6789', act='" + ACT + "', " + CONF + ")")
res.append(ok(o.startswith("байк 6789") and ("акт " + ACT) in o,
              "оба поля: прежнее ПЕРВЫМ, новое следом — %r" % o))
# Голая красная команда без единого поля объекта — как была, журналом.
kind, hit, o, n = seen("d = {" + CONF_K + "}; print(d)")
res.append(ok(o == "" and PG.card_gate(hit, o, n) is False,
              "красное без единого названного поля → журнал, как было (%r)" % o))

print("(4) ЗАБОР ЖИВОЙ СУЩНОСТИ НЕ ТРОНУТ — и контрфакт, зачем `doors=False`:")
for label, body in (("отмена записи ТО", BODY_UNDO), ("блок капов", BODY_CAPS),
                    ("переключение капа", BODY_TOGGLE)):
    kind, hit, blob = PG.classify(cmd_of(body))
    res.append(ok(PG._entity_blocktype(hit, blob) is None,
                  label + ": НЕ жёсткий блок — владелец получает карточку с кнопкой"))
    # КОНТРФАКТ: то же решение, но забором с расширенным объектом (наивная правка).
    naive = (PG._extract_first_entity(hit, blob) is None
             and hit in PG._ENTITY_HITS_LIVE
             and not PG._blob_has_test_entity(blob)
             and bool(", ".join(PG._detail_parts(hit, blob, doors=True)[0]).strip()))
    res.append(ok(naive is True,
                  label + ": наивное расширение дало бы deny без кнопки — потому забор и узок"))

# Живая сущность по-прежнему жёсткая: доктрина 23.07 не ослаблена ни на символ.
kind, hit, blob = PG.classify(cmd_of("c." + CB + "(client='Jack', bike='6789', " + CONF + ")"))
res.append(ok(PG._entity_blocktype(hit, blob) == "hard",
              "живой клиент без пометки ТЕСТ → hard, как было"))
kind, hit, blob = PG.classify(cmd_of("c." + SFO + "(number='6789', oil_km=27000, " + CONF + ")"))
res.append(ok(PG._entity_blocktype(hit, blob) == "hard",
              "живой байк без пометки ТЕСТ → hard, как было"))
kind, hit, blob = PG.classify(cmd_of("c." + SFO + "(number='ТЕСТ-6789', oil_km=27000, " + CONF + ")"))
res.append(ok(PG._entity_blocktype(hit, blob) is None, "ТЕСТ-сущность → мягко, как было"))
# Забор читает РОВНО прежний объект: для класса `confirmed` — байк и клиента, и ничего сверх.
res.append(ok(PG._detail_parts("confirmed", "act='" + ACT + "'", doors=False)[0] == [],
              "забор новые имена НЕ видит (doors=False)"))
res.append(ok(PG._detail_parts("confirmed", "act='" + ACT + "'")[0] == ["акт " + ACT],
              "карточка новые имена видит (doors по умолчанию ИСТИНА)"))
# У прочих хитов флаг не читается ни одной веткой → их объект одинаков при любом значении.
for hit_, blob_ in ((SFO, "number='6789', oil_km=27000"), (CB, "bike='6334', name='Jack'"),
                    (EE, "msg_id='-100:456'"), ("delete_file", "rm_target=/root/x.py")):
    res.append(ok(PG._detail_parts(hit_, blob_, doors=True) == PG._detail_parts(hit_, blob_, doors=False),
                  "прочий класс %s: флаг на объект не влияет" % hit_))

print("(5) СКВОЗНОЙ ПРОГОН main(): дверь отмены доходит до ВЛАДЕЛЬЦА, а не в журнал:")
out, pushed, events = run_main(cmd_of(BODY_UNDO), task_id="900001")
res.append(ok('"ask"' in out, "решение ask (без «да» команда не идёт)"))
res.append(ok(len(pushed) == 1, "ровно один пуш владельцу (получили %d)" % len(pushed)))
res.append(ok(bool(pushed) and ("Объект: акт " + ACT) in pushed[0],
              "в карточке подписан ОБЪЕКТ: акт " + ACT))
res.append(ok("card_skipped" not in events, "строки card_skipped НЕТ (было — только она): %r" % events))
marker = os.path.join(TMP, PG.marker_name("900001"))
res.append(ok(os.path.exists(marker), "маркер демону записан — карточка дойдёт до 328/1160"))
if os.path.exists(marker):
    with open(marker, encoding="utf-8") as f:
        m = json.load(f)
    res.append(ok(m.get("blocktype") != "hard", "маркер НЕ hard: у карточки есть кнопка «да»"))
    res.append(ok(("акт " + ACT) in (m.get("card") or ""), "объект доехал в маркере"))

print("(6) КОНТРАКТ `card_min(hit, blob)` цел — третьего параметра он не получил:")
res.append(ok(PG.card_min("confirmed", "act='" + ACT + "'") == ("акт " + ACT, ""),
              "двухаргументный вызов работает и отдаёт пару строк"))
try:
    import inspect as _i
    sig = list(_i.signature(PG.card_min).parameters)
    res.append(ok(sig == ["hit", "blob"], "сигнатура card_min: %r" % sig))
except Exception as e:                                   # noqa: BLE001
    res.append(ok(False, "сигнатуру card_min прочитать не удалось: %r" % e))

print("(7) ГРАНИЦЫ: правило карточки и соседние классы не тронуты:")
res.append(ok(PG.card_gate("confirmed", "акт " + ACT, "") is True, "объект без числа → карточка"))
res.append(ok(PG.card_gate("confirmed", "", "состояние off") is False,
              "ЧИСЛО БЕЗ ОБЪЕКТА карточку по-прежнему НЕ рождает"))
res.append(ok(PG.card_gate("confirmed", "", "") is False, "пусто → журнал, правило bool(obj) цело"))
kind, hit, blob = PG.classify(cmd_of("c." + SFO + "(number='6789', oil_km=27000, " + CONF + ")"))
o, n = PG.card_min(hit, blob)
res.append(ok(hit == SFO and o == "байк 6789" and n == "пробег 27000",
              "своя ветка ТО масла не изменилась: %r / %r" % (o, n)))
kind, hit, blob = PG.classify(cmd_of("c." + EE + "(msg_id='-100:456', " + CONF + ")"))
res.append(ok(hit == EE, "edit_event по-прежнему идёт СВОИМ хитом, а не общим классом"))
res.append(ok(PG.classify("grep -n def " + ROOT.replace(os.sep, "/") + "/bot.py")[0] == "green",
              "зелёная рутина осталась зелёной"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
