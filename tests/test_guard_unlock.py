# -*- coding: utf-8 -*-
"""РАЗОМКНУТЫЙ КРУГ ГАРДА: объект по разобранному вызову (A) + ответу владельца есть куда сесть (D).

КРУГ (разбор docs/artifacts/2026-08-26-guard-deadlock.md). Дверь моста требует подтверждения →
подтверждение краснит гард → красному нужна карточка → карточке нужен ОБЪЕКТ → объект не
извлёкся → `card_gate` гасит карточку → `_guard_write_marker` и `_push` в этой ветке НЕДОСТИЖИМЫ
→ владелец не узнаёт ничего, а исполнитель, попросив сам, получает от дежурного обещание «когда
команду РЕАЛЬНО попробуют, её перехватит гард и пришлёт карточку с объектом» — для двери, чьего
имени гард не знает, обещание неисполнимо.

ХОД A. Шаг 26.08 (`test_confirmed_doors.py`) выучил ПОЛЯ шести известных дверей — это лечит класс
подтверждения, а не класс НЕЗНАКОМЫХ дверей: седьмая дверь с новым именем поля снова уходит в
молчание (из 89 меток роутера моста гард знает по имени 9). Здесь объект называется САМИМ
ДЕЙСТВИЕМ: разобранный вызов, несущий подтверждение, знает имя двери (сам вызов либо
литерал-селектор доставщика) и адрес операции (литеральный аргумент). Ветка зовётся ТОЛЬКО когда
прежнее извлечение дало пусто, поэтому подменить прежний объект она не может механически.

ХОД D. Даже с карточкой «да» садиться было НЕКУДА: `bridge_client` двери отмены не знал вовсе, а
ключ акта, который мост кладёт в расписку КАЖДОЙ записи регистра (`act`/`act_logged`), не читался
ниоткуда. Теперь `undo_last.position` его помнит, `undo_last.request` собирает из ответа владельца
тела вызовов, `bridge_client.service_undo` их отправляет. Сквозной путь до ЖИВОГО кода двери
проверяет node-харнесс (секция 7).

ЧЕГО ЗДЕСЬ НЕТ. Правило карточки `bool(obj)` не тронуто ни символом — секция 2 держит его
отрицательными близнецами (те же формы, которыми правило живёт с 29.07.2026: имя лежит ДАННЫМИ в
читающей разведке). Забор живой сущности судит прежним объектом — секция 4.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИКУДА НЕ ПИШЕТ: чистые функции + main() в ЭТОМ процессе (stdin/stdout/
_push подменены), сеть у клиента подменена перехватом. Красные литералы собраны КОНКАТЕНАЦИЕЙ —
иначе гард краснеет на самом файле теста (образец: test_confirmed_doors.py).
"""
import atexit
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"          # страховка: ни одна карточка не уйдёт в Telegram
os.environ.setdefault("ORCH_TEST_MODE", "1")

if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG  # noqa: E402
import undo_last as UL  # noqa: E402
import bridge_client as BC  # noqa: E402

CONF = "confir" + "med" + "=True"
CONF_K = "'" + "confir" + "med" + "': True"     # ключ в ОДИНАРНЫХ: команда живёт внутри двойных
UNDO = "service_" + "undo"
ACT = "mt93f8k91a7ea"                        # ключ акта живого случая 25.08 (номер байка НЕ берём)
PY = "venv/bin/python3"

TMP = tempfile.mkdtemp(prefix="guard_unlock_").replace(os.sep, "/")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return bool(c)


def cmd_of(body):
    return PY + ' -c "' + body + '"'


def seen(body):
    kind, hit, blob = PG.classify(cmd_of(body))
    o, n = PG.card_min(hit, blob)
    return kind, hit, o, n


def run_main(cmd, task_id=""):
    """main() В ЭТОМ процессе → (решение-JSON, [карточки], [события журнала])."""
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


# ЖИВЫЕ формы обращения к двери. Первые две — НЕЗНАКОМАЯ дверь с полем, которого словарь не знает
# (ровно тот случай, ради которого ход A): словарь полей молчит, называет действие.
B_UNKNOWN = "c._post('service_reopen', ref='zz-77', by='Filipp', " + CONF + ")"
B_UNKNOWN_DICT = "c.post(url, {'action': 'service_reopen', 'ref': 'zz-77', " + CONF_K + "})"
B_BY_NAME = "bridge.set_caps(caps=caps_var, " + CONF + ")"      # значение вычисляется, поля молчат
B_UNDO = "c._post('" + UNDO + "', act='" + ACT + "', by='Filipp', " + CONF + ")"

print("(1) ХОД A: НЕЗНАКОМАЯ дверь получает ОБЪЕКТ и КАРТОЧКУ (прежде — молчание):")
for label, body, want in (("дверь+ключ у доставщика", B_UNKNOWN, "дверь моста service_reopen"),
                          ("тело запроса словарём", B_UNKNOWN_DICT, "дверь моста service_reopen"),
                          ("дверь названа самим вызовом", B_BY_NAME, "дверь моста set_caps")):
    kind, hit, o, n = seen(body)
    ok(kind == "red" and hit == "confirmed", label + ": красное, общий класс (kind=%s hit=%s)" % (kind, hit))
    ok(want in o, label + ": ОБЪЕКТ назван — %r" % o)
    ok(PG.card_gate(hit, o, n) is True, label + ": КАРТОЧКА выписана (была бы журналом)")
    ok(PG.marker_has_object(hit, PG._card(hit, PG.classify(cmd_of(body))[2])) is True,
       label + ": маркер демону УХОДИТ (вторая линия пропускает)")

_k, _h, _o, _n = seen(B_UNKNOWN)
ok("ключ ref=zz-77" in _o, "адрес операции назван ключом вызова: %r" % _o)

print("(1б) НАСТОЯЩАЯ попытка записи через дверь подтверждения: main() спрашивает и ПОКАЗЫВАЕТ:")
out, pushed, events = run_main(cmd_of(B_UNKNOWN), task_id="9001")
dec = json.loads(out or "{}")
ok(dec.get("hookSpecificOutput", {}).get("permissionDecision") == "ask",
   "решение ask (команда не проходит): %r" % dec.get("hookSpecificOutput", {}).get("permissionDecision"))
ok(len(pushed) == 1, "владельцу ушла РОВНО одна карточка: %d" % len(pushed))
ok(pushed and "service_reopen" in pushed[0] and "Объект" in pushed[0],
   "в карточке назван объект: %r" % (pushed[0][:120] if pushed else ""))
ok("card_skipped" not in events, "красное больше НЕ уходит молча в журнал: %r" % events)
ok(os.path.exists(os.path.join(TMP, PG.marker_name("9001"))),
   "маркер демону записан (канал к владельцу открыт): %s" % PG.marker_name("9001"))

print("(2) ОТРИЦАТЕЛЬНЫЕ БЛИЗНЕЦЫ: СРЕЗ НА ПОДСТРОКЕ без действия карточки НЕ рождает:")
NEG = (
    ("имя двери в списке слов",
     "doors = ['" + UNDO + "', 'service_reopen']; print(doors, '" + "confir" + "med')"),
    ("имя двери в шаблоне поиска",
     "import re; print(re.findall(r'" + UNDO + "', open('/tmp/x').read()), '" + "confir" + "med')"),
    ("имя двери в печатаемой строке отчёта",
     "print('дверь " + UNDO + " требует " + "confir" + "med=true и мы её не звали')"),
    ("ключ акта данными в разведке",
     "acts = {'a': '" + ACT + "'}; print(acts, '" + "confir" + "med')"),
)
for label, body in NEG:
    kind, hit, o, n = seen(body)
    ok(not (o or "").strip(), label + ": объект ПУСТ — %r" % o)
    ok(PG.card_gate("confirmed", o, n) is False, label + ": карточки НЕТ (правило объекта живо)")

print("(2б) БЛИЗНЕЦ ТОГО ЖЕ ИМЕНИ: настоящий вызов той же двери — карточка есть:")
_k, _h, _o, _n = seen(B_UNDO)
ok(_k == "red" and PG.card_gate(_h, _o, _n) is True,
   "настоящий вызов двери отмены: карточка (объект %r)" % _o)
ok("акт " + ACT in _o, "объект называет ключ акта — словарём полей, не веткой A: %r" % _o)

print("(3) ЗАЩИТА: РАЗБОРА НЕТ — ОБЪЕКТА НЕТ (нет действия — нет карточки):")
PG.set_code_view(None)
ok(PG._door_bits() == [], "разбора нет → ветка молчит")
PG.set_code_view(PG._code_view_parts(["x = 1"]))
ok(PG._door_bits() == [], "разбор есть, вызова подтверждения нет → ветка молчит")
PG.set_code_view(PG._code_view_parts(["c._post('" + UNDO + "', act='x', " + "confir" + "med=flag)"]))
ok(PG._door_bits() == [], "подтверждение ВЫЧИСЛЯЕТСЯ (не литерал) → ветка молчит")
PG.set_code_view(None)
BLIND = PY + " - <<'PY'\nc._post('" + UNDO + "', act='x', " + CONF + ")\nPY"
_kind, _hit, _blob = PG.classify(BLIND)
_o2, _n2 = PG.card_min(_hit, _blob)
ok(_kind in ("red", "ambiguous"), "слепое тело (heredoc) по-прежнему красное: %s" % _kind)
ok("дверь моста" not in _o2, "слепое тело: ветка A не выдумывает объект — %r" % _o2)

print("(4) ЗАБОР ЖИВОЙ СУЩНОСТИ СУДИТ ПРЕЖНИМ ОБЪЕКТОМ (иначе вместо карточек прибавилось бы deny):")
for label, body in (("незнакомая дверь", B_UNKNOWN), ("дверь отмены", B_UNDO),
                    ("дверь названа вызовом", B_BY_NAME)):
    _kind, _hit, _blob = PG.classify(cmd_of(body))
    o_card, _ = PG._detail_parts(_hit, _blob, doors=True)
    o_fence, _ = PG._detail_parts(_hit, _blob, doors=False)
    ok(o_card and not o_fence, label + ": карточка видит объект, забор — нет (%r / %r)" % (o_card, o_fence))
    ok(PG._entity_blocktype(_hit, _blob) != "hard", label + ": жёсткого блока НЕ прибавилось")
_live = "c._post('set_fleet_" + "oil', number='6789', oil_km=41357, " + CONF + ")"
_kind, _hit, _blob = PG.classify(cmd_of(_live))
ok(PG._entity_blocktype(_hit, _blob) == "hard", "живая сущность парка по-прежнему жёсткий блок")

print("(5) ГРАНИЦЫ: контракты и соседние классы не тронуты:")
import inspect  # noqa: E402
ok(list(inspect.signature(PG.card_min).parameters) == ["hit", "blob"],
   "контракт card_min(hit, blob) третьего параметра не получил")
ok(inspect.getsource(PG.card_gate).count("bool((obj or \"\").strip())") == 1,
   "правило карточки — по-прежнему один только объект")
_money = "c.add_" + "transaction(group=wallet, amount=-500)"
_k, _h, _blob = PG.classify(cmd_of(_money))
ok(_h and "вызов" in PG.card_min(_h, _blob)[0] or "кошелёк" in PG.card_min(_h, _blob)[0],
   "денежный класс отвечает прежним объектом: %r" % (PG.card_min(_h, _blob)[0],))
PG.set_code_view(PG._code_view_parts(["c._post('" + UNDO + "', act='" + ACT + "', token='СЕКРЕТ-XYZ', "
                                      + CONF + ")"]))
ok("СЕКРЕТ" not in ", ".join(PG._door_bits()),
   "значение служебного ключа (token) в объект НЕ уезжает: %r" % PG._door_bits())
PG.set_code_view(None)

print("(6) ХОД D: ответу владельца есть куда сесть:")
ok(hasattr(BC.BridgeClient, UNDO), "мост-клиент знает дверь отмены")
R = {"ok": True, "number": "90808", "bike_name": "ТЕСТ-БАЙК 90808", "row": 3, "kind": "gear",
     "column": 10, "old_km": 41357, "new_km": 41667, "verified": True,
     "full_address": "…|Лист1|J3", "act": ACT, "act_logged": True}
pos, why = UL.position("gear", "J", R, want_km=41667)
ok(pos and pos.get("act") == ACT, "позиция помнит ключ акта: %r (%s)" % (pos and pos.get("act"), why))
entry = UL.act(1, 1.0, -100, 83, R["bike_name"], R["number"], "@pym", "41667", [pos])
calls, refusals = UL.request(entry, by="@filipp", confirmed=True)
ok(len(calls) == 1 and calls[0] == {"act": ACT, "by": "@filipp", "confirmed": True},
   "ответ владельца → тело вызова двери: %r" % calls)
ok(not refusals, "отказов нет: %r" % refusals)
_c2, _r2 = UL.request(entry, by="@filipp")
ok(_c2 and _c2[0]["confirmed"] is False and _r2 and "not_" + "confirmed" in _r2[0][1],
   "без ответа владельца подтверждение НЕ подразумевается и причина названа: %r" % (_r2,))
R_NO_ACT = dict(R, act=None, act_logged=False)
p2, _ = UL.position("gear", "J", R_NO_ACT, want_km=41667)
ok(p2 is not None and p2.get("act") == "", "журнал моста не лёг → позиция есть, ключа нет: %r" % p2)
e2 = UL.act(2, 1.0, -100, 83, R["bike_name"], R["number"], "@pym", "41667", [p2])
c3, r3 = UL.request(e2, by="@filipp", confirmed=True)
ok(not c3 and r3 and "act_logged" in r3[0][1],
   "звать нечем — и это СКАЗАНО, а не пропущено молча: %r" % (r3,))
ok(UL.request(None)[1] and UL.request({})[1], "мусор на входе → названный отказ, не исключение")

print("(7) СКВОЗНОЙ ПУТЬ ДО ЖИВОГО КОДА ДВЕРИ (node-харнесс на bridge_prod/@83):")
p = subprocess.run(["node", os.path.join(HERE, "guard_unlock_harness.js")],
                   capture_output=True, text=True, timeout=180, cwd=ROOT)
try:
    H = json.loads((p.stdout or "").strip().splitlines()[-1])
except (ValueError, IndexError):
    H = {"cases": [], "negatives": 0}
bad = [c for c in H.get("cases", []) if not c.get("pass")]
ok(p.returncode == 0 and not bad,
   "харнесс зелёный: %d проверок, отрицательных %d%s"
   % (len(H.get("cases", [])), H.get("negatives", 0),
      "" if not bad else " | ПРОВАЛЫ: " + "; ".join(c["name"] for c in bad[:4])))
ok(H.get("negatives", 0) >= 3, "отрицательных близнецов у двери не меньше трёх: %d" % H.get("negatives", 0))
names = {c["name"] for c in H.get("cases", [])}
for need in ("door.срабатывает", "neg.поддельный-акт-отвергнут", "neg.без-подтверждения-отказ"):
    ok(need in names, "харнесс проверяет «%s»" % need)

print("\nИТОГ: %d/%d" % (sum(res), len(res)))
if not all(res):
    sys.exit(1)
