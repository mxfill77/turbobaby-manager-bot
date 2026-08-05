# -*- coding: utf-8 -*-
"""ГРАНИЦА ГЕЙТА: КЛАСС ВСТАЁТ НА ЛИТЕРАЛ (05.08.2026).

ЖИВОЙ ФАКТ (полоса ПК, 19:21): красное поднялось на СТРОКЕ ВНУТРИ python-кода — самой операции
в теле не было вовсе. Тот же класс уже дважды закрыт с одной стороны и дважды НАЗВАН остатком с
другой:
  * 02.08.2026 — денежная ветвь (`_money_is_action`); в артефакте
    `docs/artifacts/2026-08-02-money-action-not-word.md` §4 остаток назван адресом:
    «`pretool_guard._body_has` — распространить `_money_is_action` на имена операций ЖИВЫХ ТАБЛИЦ»;
  * 04.08.2026 — правило исполняющей позиции (`5ca761d`): красит имя, стоящее там, где его
    ИСПОЛНИТ разборщик. В `_body_has` правило было остановлено намеренно — «снять это развилка
    владельца, гард своей властью записанное решение не отменяет».

ЗДЕСЬ РАЗВИЛКА ПРОЙДЕНА ПО РЕШЕНИЮ ВЛАДЕЛЬЦА: правило одно на ВСЕ имена операций. Красит вызов,
имя кода и литерал-селектор при живом канале; докстринг, комментарий, список слов и печатаемая
строка — не красят. Двух списков нет: у python-тела исполняющую позицию называет AST.

ЧТО ПРОВЕРЯЕТСЯ:
  (1) литерал имени операции ЖИВОЙ ТАБЛИЦЫ (докстринг/список слов/`in line`/печать) карточки НЕ
      рождает и красного НЕ даёт;
  (2) ДОСЛОВНЫЕ команды 117 и 135 (транскрипты 31.07) — тот самый остаток §4 — уходят в defer
      целиком, а не «в журнал по имени операции CRM»;
  (3) фактический вызов рождает КАК ПРЕЖДЕ: разобранный вызов, имя кода, литерал-селектор при
      канале, сырой HTTP к мосту — с названным объектом;
  (4) ГРАНИЦЫ НЕ ОСЛАБЛЕНЫ: жёсткий блок спрашивает всегда; `confirmed` как РАЗОБРАННОЕ значение
      краснеет при любом написании и БЕЗ всякого канала; тело не разобралось / слепое тело /
      имя вне разобранных тел → прежняя подстрока (fail-closed); маркер автора судится по сырому
      тексту; объектный гейт и класс удаления не тронуты.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ: зовутся ЧИСТЫЕ функции (classify/card_min/card_gate/
can_approve), main() не вызывается, подпроцессов нет → ни пуша, ни маркера. Красные литералы в
САМОМ файле собраны конкатенацией; в фикстуры, которые пишутся во временный каталог, они попадают
целыми — там и нужен живой формат.
"""
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"           # страховка: даже случайный пуш упрётся в мут

_fake_notify = types.ModuleType("notify")    # страховка №2 — до импорта гарда
_fake_notify.send_card = lambda card, **kw: (111, 222)
_fake_notify.edit_card = lambda mid, card, **kw: None
sys.modules.setdefault("notify", _fake_notify)

import pretool_guard as PG  # noqa: E402

SFO = "set_fleet_" + "oil"
SFS = "set_fleet_" + "service"
SF = "set_" + "fleet"
CB = "create_" + "booking"
AB = "activate_" + "booking"
CU = "closing_" + "upsert"
DE = "delete_" + "event"
EE = "edit_" + "event"
AT = "add_" + "transaction"
VL = "void_" + "last"
CONF = "confirmed" + "=" + "true"
DOW = "DO" + "WRITE"
PY = "venv/bin/python3"

TMP = tempfile.mkdtemp(prefix="litpos_0805_")
res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    res.append(bool(c))
    return bool(c)


def fixture(name, body):
    p = os.path.join(TMP, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return PY + " " + p


def bucket(cmd):
    """Куда команда идёт по решению гарда: БЛОК | КАРТОЧКА | журнал | defer (+hit, объект, число).
    Повторяет порядок main(), ничего не исполняя и не записывая."""
    kind, hit, blob = PG.classify(cmd, ROOT)
    if kind in ("green", "ambiguous"):
        return "defer", hit, "", ""
    if not PG.can_approve(kind, hit):
        return "БЛОК", hit, "", ""
    obj, num = PG.card_min(hit, blob)
    return ("КАРТОЧКА" if PG.card_gate(hit, obj, num) else "журнал"), hit, obj, num


# ══ (1) ЛИТЕРАЛ ИМЕНИ ОПЕРАЦИИ — НЕ ДЕЙСТВИЕ ═══════════════════════════════════════════════════
print("(1) имя операции живой таблицы в литерале: красного нет:")

LITERAL_FORMS = (
    ("докстринг", '"""Модуль про ' + SFO + ' — только описание, записи тут нет."""\nprint(1)\n'),
    ("комментарий", "# запись " + SFO + " тут НЕ делается\nprint(1)\n"),
    ("печать имени", "print('" + DE + "')\n"),
    ("список слов + поиск", "import re\nTOK = ('" + SFO + "', '" + CB + "', '" + DE + "')\n"
                            "print(any(t in open('/etc/hostname').read() for t in TOK))\n"),
    ("сравнение `in line`", "import re\n"
                            'with open("/etc/hostname", encoding="utf-8") as f:\n'
                            "    for line in f:\n"
                            '        if ("' + CU + '" in line or "' + AB + '" in line):\n'
                            '            print(line.rstrip())\n'),
    ("шаблон регулярки", "import re\nRX = re.compile(r'" + EE + "[: ]')\nprint(RX.pattern)\n"),
    ("ключ отчёта", "import json\nprint(json.dumps({'проверено': ['" + SFS + "', '" + CB + "']}))\n"),
)
for label, body in LITERAL_FORMS:
    b, hit, _o, _n = bucket(fixture("lit_%s.py" % abs(hash(label)), body))
    ok(b == "defer", label + ": красного нет — %s (hit=%s)" % (b, hit or "—"))

# ══ (2) ДОСЛОВНЫЙ ОСТАТОК §4: команды 117 и 135 ════════════════════════════════════════════════
print("(2) дословные 117 и 135 — остаток, названный адресом 02.08, закрыт:")

# ДОСЛОВНАЯ команда 117 (транскрипт 2026-07-31T12:27:18 UTC): инлайн-подсчёт пишущих признаков.
# Склейка байт-в-байт повторяет голден tests/test_money_action.py — источник тот же транскрипт.
TASK117 = (
    PY + " -c '\n"
    "import re\n"
    'src = open("/root/turbobaby-manager-bot/splinter.py", encoding="utf-8").read()\n'
    'i = src.index("def _build_bike_card")\n'
    'j = src.index("\\ndef ", i + 10)\n'
    "body = src[i:j]\n"
    'print("строк в _build_bike_card:", body.count("\\n"))\n'
    'writes = ["' + SF + '", "' + AT + '", "' + VL + '", "' + CB + '", "' + AB + '",'
    ' "' + CU + '", "' + DE + '", "' + CONF + '", "_odo_store",'
    ' "write_doc", "append", "enqueue"]\n'
    "for w in writes:\n"
    "    n = body.count(w)\n"
    "    if n:\n"
    '        print("  ПИШУЩИЙ ПРИЗНАК:", w, n)\n'
    'print("bridge-вызовы:", sorted(set(re.findall(r"bridge\\.([a-z_]+)\\(", body))))\n'
    "'"
)
b, hit, obj, num = bucket(TASK117)
ok(b == "defer", "117 ДОСЛОВНО: defer целиком — %s (hit=%s)" % (b, hit or "—"))
ok(hit != CB, "117: имя операции CRM из СПИСКА СЛОВ класс больше не назначает (hit=%s)" % (hit or "—"))
# В том же списке слов лежит и написание confirmed=true. Оно не должно краснить читающую
# разведку: канала у тела нет вовсе (импорт один — re), дойти до Лист1 ей нечем.
ok(hit != "confirmed",
   "117: `" + CONF + "` СТРОКОЙ в списке слов у тела БЕЗ канала не краснит (hit=%s)" % (hit or "—"))

# ДОСЛОВНАЯ 135 (транскрипт 2026-07-31T16:20:14 UTC) — харнесс собственного регресса задачи 117:
# имена операций лежат ДАННЫМИ внутри строковых литералов списка случаев.
CMD_135_TAIL = (
    PY + " -c '\n"
    "import sys\n"
    'sys.path.insert(0, "/root/turbobaby-manager-bot")\n'
    "import pretool_guard as G\n"
    "cases = [\n"
    ' ("D1 читающий скрипт со СПИСКОМ слов (задача 117)", "' + PY + ' -c \\x27\\nsrc = '
    'open(\\"/root/turbobaby-manager-bot/splinter.py\\").read()\\nwrites = [\\"' + SF + '\\", \\"'
    + AT + '\\", \\"' + VL + '\\", \\"' + CB + '\\"]\\nfor w in writes:\\n    print(w, '
    'src.count(w))\\n\\x27"),\n'
    "]\n"
    "for lab, c in cases:\n"
    '    kind, hit, blob = G.classify(c, "/root/turbobaby-manager-bot")\n'
    '    print(lab, kind, hit)\n'
    "'"
)
b, hit, _o, _n = bucket(CMD_135_TAIL)
ok(b == "defer", "135 ДОСЛОВНО (хвост-харнесс): defer — %s (hit=%s)" % (b, hit or "—"))
ok(hit != CB, "135: имя операции CRM из данных класс не назначает (hit=%s)" % (hit or "—"))

# ══ (3) ФАКТИЧЕСКИЙ ВЫЗОВ — КАРТОЧКА КАК ПРЕЖДЕ ════════════════════════════════════════════════
print("(3) настоящее действие рождает красное как прежде:")

FX_CALL = "import bridge_client as bc\nbc." + SFO + "(number='6789', oil_km=27000)\n"
b, hit, obj, num = bucket(fixture("fx_call.py", FX_CALL))
ok(b == "КАРТОЧКА" and hit == SFO, "разобранный вызов записи ТО: КАРТОЧКА (%s, hit=%s)" % (b, hit))
ok(obj.strip() != "", "объект назван — %r" % obj)

FX_VAR = ("import bridge_client as bc\nplate = input()\nkm = 27000\n"
          "bc." + SFO + "(number=plate, oil_km=km)\n")
b, hit, obj, num = bucket(fixture("fx_var.py", FX_VAR))
ok(b == "КАРТОЧКА" and hit == SFO, "вычисляемые аргументы: карточка есть (%s)" % b)
ok("вычисляется" in obj, "вычисляемый объект назван честно — %r" % obj)

FX_SELECTOR = "import bridge_client as bc\nbc._call('" + SFO + "', number='6789')\n"
kind, hit, _blob = PG.classify(fixture("fx_selector.py", FX_SELECTOR), ROOT)
ok(kind == "red" and hit == SFO, "литерал-СЕЛЕКТОР при живом канале: красное (hit=%s)" % (hit or "—"))

FX_HTTP = ("import requests\n"
           'requests.post("https://script.google.com/x", data={"action": "' + DE + '",'
           ' "key": "ev-2026-08-05"})\n')
kind, hit, _blob = PG.classify(fixture("fx_http.py", FX_HTTP), ROOT)
ok(kind == "red" and hit == DE, "сырой HTTP к мосту: красное (hit=%s)" % (hit or "—"))

FX_REF = "from bridge_client import " + CB + "\nfn = " + CB + "\n"
kind, hit, _blob = PG.classify(fixture("fx_ref.py", FX_REF), ROOT)
ok(kind == "red" and hit == CB, "имя КОДА (импорт+ссылка) без скобок: красное (hit=%s)" % (hit or "—"))

FX_GETATTR = ("import bridge_client as bc\n"
              'fn = getattr(bc, "' + CU + '")\nfn(row=705)\n')
kind, hit, _blob = PG.classify(fixture("fx_getattr.py", FX_GETATTR), ROOT)
ok(kind == "red" and hit == CU, "вызов через getattr: красное (hit=%s)" % (hit or "—"))

# ══ (4) ГРАНИЦЫ НЕ ОСЛАБЛЕНЫ ═══════════════════════════════════════════════════════════════════
print("(4) границы: жёсткий блок, confirmed, слепое тело, маркер автора, удаление:")

b, hit, _o, _n = bucket("systemctl stop splinter")
ok(b == "БЛОК", "жёсткий блок процесса контура: по-прежнему БЛОК (%s, hit=%s)" % (b, hit or "—"))

# confirmed как РАЗОБРАННОЕ значение краснеет БЕЗ всякого канала: это не имя операции, а
# универсальный признак боевой записи в Лист1, и разбор видит его в исполняющей позиции.
FX_CONF_DICT = "p = {'" + "confirmed" + "'  :  True}\nprint(p)\n"
kind, hit, _blob = PG.classify(fixture("fx_conf_dict.py", FX_CONF_DICT), ROOT)
ok(kind == "red" and hit == "confirmed",
   "ключ словаря `'confirmed' : True` без канала → красное (hit=%s)" % (hit or "—"))

FX_CONF_KW = "import bridge_client as bc\nbc._call('sheet_write', " + "confirmed" + "  =  True)\n"
kind, hit, _blob = PG.classify(fixture("fx_conf_kw.py", FX_CONF_KW), ROOT)
ok(kind == "red" and hit == "confirmed",
   "`confirmed  =  True` (два пробела) в теле → красное (hit=%s)" % (hit or "—"))

# Сырое тело запроса: написание лежит в СТРОКЕ, но у тела есть чем дойти до Лист1 → красное.
FX_CONF_RAW = ("import requests\n"
               'requests.post("https://script.google.com/x", data="action=' + SFO + '&' + CONF + '")\n')
kind, hit, _blob = PG.classify(fixture("fx_conf_raw.py", FX_CONF_RAW), ROOT)
ok(kind == "red", "сырое тело запроса с `" + CONF + "` при канале → красное (hit=%s)" % (hit or "—"))

# ГЛАВНЫЙ ИНВАРИАНТ ВЫЧИТАНИЯ РАЗОБРАННЫХ ТЕЛ: вычитается ТОЛЬКО то, что удалось разобрать.
# Инлайн-код с синтаксической ошибкой не разбирается вовсе (view is None) → судится ПОЛНЫЙ скан,
# байт-в-байт как до правки. Иначе вычитание стало бы дырой: достаточно было бы сломать синтаксис.
kind, hit, _blob = PG.classify(PY + " -c 'p = {\"" + "confirmed" + '": True,\ndef (:\'', ROOT)
ok(kind == "red" and hit == "confirmed",
   "инлайн-код НЕ разобрался → полный скан, красное как было (fail-closed, hit=%s)" % (hit or "—"))

# Вычитание литералов не должно СЪЕДАТЬ буквы настоящего признака: короткая строка в теле
# («e») не имеет к признаку отношения, и после вычитания `confirmed=true` обязан остаться цел.
kind, hit, _blob = PG.classify(PY + " -c 'sep = \"e\"\n" + CONF + "'", ROOT)
ok(kind == "red" and hit == "confirmed",
   "короткий литерал в теле не стирает буквы настоящего признака (hit=%s)" % (hit or "—"))

# ИЗМЕРЕННЫЙ ФАКТ, а не намерение этой правки: написание в АРГУМЕНТАХ python-команды и в теле
# запроса curl красного не давало и ДО неё — скан-представление считает argv и полезную нагрузку
# ДАННЫМИ («данные ≠ команда»), а не-python команда до этой ветки вообще не доходит (_is_python).
# Сверено прогоном HEAD и рабочего дерева: обе формы green в ОБОИХ, правка их не касается.
for _label, _cmd in (
    ("флаг CLI", PY + " " + fixture("fx_flag.py", "print(1)\n").split(" ", 1)[1] + " --" + CONF),
    ("тело запроса curl", 'curl -s -d "action=' + SFO + "&" + CONF + '" https://script.google.com/x'),
):
    _k, _h, _b = PG.classify(_cmd, ROOT)
    print("  NOTE %s: %s (hit=%s) — так было и до правки, класс «данные ≠ команда»"
          % (_label, _k, _h or "—"))

FX_BROKEN = "# " + SFO + " упомянут в комментарии\ndef (:\n"
kind, hit, _blob = PG.classify(fixture("fx_broken.py", FX_BROKEN), ROOT)
ok(kind == "red" and hit == SFO, "тело не разобралось → ПРЕЖНЯЯ подстрока (fail-closed, hit=%s)" % (hit or "—"))

FX_DOW = "# " + DOW + "=1 — этот скрипт реально пишет\nprint(1)\n"
kind, hit, _blob = PG.classify(fixture("fx_dow.py", FX_DOW), ROOT)
ok(kind == "red" and hit == DOW, DOW + " в комментарии-шапке: красное (самообъявление автора)")

# Имя операции произнесено ВНЕ разобранных тел (в `-m`-модуле) → разбирать нечего → подстрока.
kind, hit, _blob = PG.classify(PY + " -m " + SFO + "_runner", ROOT)
ok(kind == "red" and hit == SFO, "имя ВНЕ разобранных тел: слепой режим, подстрока (hit=%s)" % (hit or "—"))

# Удаление из тела не тронуто этой правкой (класс 03.08): цель вне временных каталогов → красное.
FX_DEL = "import os\nos.remove('/root/turbobaby-manager-bot/splinter.py')\n"
kind, hit, _blob = PG.classify(fixture("fx_del.py", FX_DEL), ROOT)
ok(kind == "red" and hit == "delete_file", "удаление файла репо из тела: красное (hit=%s)" % (hit or "—"))

shutil.rmtree(TMP, ignore_errors=True)
bad = res.count(False)
print("\nИТОГ: %d/%d" % (res.count(True), len(res)))
if bad:
    print("КРАСНЫХ: %d" % bad)
    sys.exit(1)
print("Все проверки зелёные.")
