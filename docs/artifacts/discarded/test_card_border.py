# -*- coding: utf-8 -*-
"""ГРАНИЦА КАРТОЧЕК (31.07.2026): когда красное действие доходит ДО ВЛАДЕЛЬЦА, а когда — нет.

Три класса, все три с живыми фактами серверной полосы:

(A) ЗАМОК ТЕСТ-ПРОГОНА НЕ ЗАКРЫВАЛ КАНАЛ ВЛАДЕЛЬЦА. Замок 28.07 (задача 12) знает ЧЕТЫРЕ признака
    тест-прогона (_TEST_RUN_ENVS) и по ним уводит маркер в отдельный каталог с префиксом `test-`.
    Пуш владельцу смотрел РОВНО ОДИН признак — PRETOOL_NOPUSH. Проба, запущенная с PRETOOL_TEST_RUN=1
    (маркер безопасно ушёл в тест-каталог), слала владельцу БОЕВУЮ карточку в инбокс. Три захода
    подряд (117, 135, 140) умерли на собственной пробе — этот перекос чинится ПЕРВЫМ, иначе им же
    умирает и регресс. Теперь у канала владельца тот же единственный источник правды: is_test_run().

(B) ДЕНЕЖНОЕ ИСКЛЮЧЕНИЕ РОЖДАЛО ПУСТУЮ КАРТОЧКУ. Задача 117 просила ровно `systemctl restart
    splinter`, а по дороге пересчитывала пишущие признаки в исходнике splinter.py — СПИСКОМ СЛОВ.
    Слово прошло красным грепом, извлекать было нечего, и владельцу ушла карточка «проводка ДЕНЕГ
    в кассу» с прочерками в ОБЪЕКТЕ и ЧИСЛЕ (37000 и 38982 в задании — ПРОБЕГ, никаких денег там
    не было вовсе). Теперь денежное исключение опирается на НАЗВАННУЮ ЦЕЛЬ — литерал: кошелёк,
    сумма либо сам литеральный вызов `void_last(`. Голое ИМЯ функции целью не является.

(C) ФАЙЛ СЕКРЕТОВ СУДИЛСЯ ПО ПОДСТРОКЕ. Слово `.env` в прозе — в строке журнала cclog или в
    отчёте echo — давало ЖЁСТКИЙ БЛОК (deny, approve невозможен): работа вставала на СЛОВЕ, хотя
    секретов такая команда не открывает. Судим по ДЕЙСТВИЮ: путь-операнд и исполняемый текст —
    блок как был; проза — нет.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ. main() зовётся В ЭТОМ процессе (stdin/stdout
подменены), модуль notify подменён ФЕЙКОМ-счётчиком ДО любой проверки — «боевой» путь пуша упирается
в счётчик, а не в Telegram. Маркеры пишутся с ФЕЙКОВЫМ номером задачи в тест-каталог. Красные
литералы собраны КОНКАТЕНАЦИЕЙ (иначе гард краснеет на самом файле теста).
"""
import io
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"          # страховка №1: ни одна карточка не уйдёт в Telegram

# ── ФЕЙК notify (страховка №2, ставится ДО импорта гарда): даже если мут когда-нибудь протечёт,
#    _push упрётся в счётчик. Импорт настоящего notify.py после этого невозможен by construction.
_SENT = []
_fake_notify = types.ModuleType("notify")
_fake_notify.send_card = lambda card, **kw: (_SENT.append(card), (111, 222))[1]
_fake_notify.edit_card = lambda mid, card, **kw: _SENT.append("EDIT:" + str(card))
sys.modules["notify"] = _fake_notify

if "fcntl" not in sys.modules:               # ПК-клон (Windows) — как в соседних гард-тестах
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _f = types.ModuleType("fcntl")
        _f.flock = lambda *a, **k: None
        _f.LOCK_EX = 2
        sys.modules["fcntl"] = _f

import pretool_guard as PG  # noqa: E402

# ── красные литералы по кускам ────────────────────────────────────────────────
AT = "add_" + "transaction"
VL = "void_" + "last"
SFO = "set_fleet_" + "oil"
CB = "create_" + "booking"
CONF = "confirmed" + "=" + "true"
ENVF = "." + "env"
PY = "venv/bin/python3"
FAKE_TID = "990117"                       # НИКОГДА не номер живой задачи: маркер уйдёт под ним

res = []


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def bucket(cmd, cwd=ROOT):
    """Куда команда идёт по решению гарда: БЛОК | КАРТОЧКА | журнал | defer (+hit, объект, число).
    Повторяет порядок main(), ничего не исполняя и не записывая."""
    kind, hit, blob = PG.classify(cmd, cwd)
    if kind in ("green", "ambiguous"):
        return "defer", hit, "", ""
    if not PG.can_approve(kind, hit):
        return "БЛОК", hit, "", ""
    obj, num = PG.card_min(hit, blob)
    return ("КАРТОЧКА" if PG.card_gate(hit, obj, num) else "журнал"), hit, obj, num


def run_main(cmd, task_id="", env_extra=None, block_dir=None):
    """main() В ЭТОМ процессе → (решение-JSON, [карточки, ПЕРЕХВАЧЕННЫЕ на границе], [события лога]).
    Перехват на границе — сам PG._push: он остаётся НАСТОЯЩИМ, а под ним стоит фейк notify."""
    logp = os.path.join(TMPD, "guard_%d.log" % len(res))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": ROOT})
    out = io.StringIO()
    saved_io = (sys.stdin, sys.stdout)
    saved_env = dict(os.environ)
    before = len(_SENT)
    sys.stdin, sys.stdout = io.StringIO(payload), out
    os.environ["PRETOOL_GUARD_LOG"] = logp
    os.environ["CC_TASK_ID"] = task_id
    if block_dir:
        os.environ[PG.BLOCK_DIR_ENV] = block_dir
    else:
        os.environ.pop(PG.BLOCK_DIR_ENV, None)     # НАРОЧНО: проверяем УМОЛЧАНИЕ каталога
    for k in PG._TEST_RUN_ENVS:                    # чистое окружение → флаги ставит только тест
        os.environ.pop(k, None)
    os.environ.update(env_extra or {})
    try:
        PG.main()
    except SystemExit:
        pass
    finally:
        sys.stdin, sys.stdout = saved_io
        os.environ.clear()
        os.environ.update(saved_env)
    events = []
    try:
        with open(logp, encoding="utf-8") as f:
            events = [json.loads(ln)["event"] for ln in f.read().splitlines() if ln.strip()]
    except OSError:
        pass
    return out.getvalue(), _SENT[before:], events


import tempfile  # noqa: E402
TMPD = tempfile.mkdtemp(prefix="card_border_")     # НЕ убираем за собой намеренно: следы пробы

# ══════════════════════════════════════════════════════════════════════════════════════════════
print("(A) ЗАМОК ТЕСТ-ПРОГОНА: канал владельца закрыт ВСЕМИ признаками теста, не одним:")
for flag in PG._TEST_RUN_ENVS:
    res.append(ok(PG.is_test_run({flag: "1"}), "признак теста виден хуку: " + flag))
res.append(ok(not PG.is_test_run({}), "пустое окружение = БОЙ (регресс)"))

for flag in PG._TEST_RUN_ENVS:
    saved = dict(os.environ)
    try:
        for k in PG._TEST_RUN_ENVS:
            os.environ.pop(k, None)
        os.environ[flag] = "1"
        n = len(_SENT)
        PG._push("🔴 КРАСНОЕ\nЧто: проба\nОбъект: —\nЧисло: —")
        PG._edit([111, 222], "🔴 КРАСНОЕ\nЧто: проба-правка")
        res.append(ok(len(_SENT) == n, "при " + flag + " владельцу НЕ уходит ничего (пуш и правка)"))
    finally:
        os.environ.clear()
        os.environ.update(saved)

_saved = dict(os.environ)
try:                                        # боевой путь ЖИВ (мут не съел канал вообще)
    for k in PG._TEST_RUN_ENVS:
        os.environ.pop(k, None)
    n = len(_SENT)
    PG._push("🔴 КРАСНОЕ\nЧто: боевая карточка")
    res.append(ok(len(_SENT) == n + 1, "без признаков теста карточка УХОДИТ (канал не убит)"))
finally:
    os.environ.clear()
    os.environ.update(_saved)

res.append(ok(PG.block_dir({"PRETOOL_TEST_RUN": "1"}) == PG.TEST_BLOCK_DIR != PG.GUARD_BLOCK_DIR,
              "замок 28.07 цел: тест-прогон → отдельный каталог маркеров"))
res.append(ok(PG.marker_name(FAKE_TID, {"PRETOOL_TEST_RUN": "1"}) == "test-" + FAKE_TID + ".json",
              "замок 28.07 цел: имя маркера с префиксом test-"))

# СКВОЗНОЕ: денежная проба в тест-режиме — боевого маркера нет, владельцу нет, а ЧТО СОБИРАЛОСЬ
# уйти — видно глазами (перехват на границе).
LIVE_MONEY = "bridge." + AT + "(group='Наличка', amount=-500, category='fuel')"
_live_plain = os.path.join(PG.GUARD_BLOCK_DIR, FAKE_TID + ".json")
_live_pref = os.path.join(PG.GUARD_BLOCK_DIR, "test-" + FAKE_TID + ".json")
_test_marker = os.path.join(PG.TEST_BLOCK_DIR, "test-" + FAKE_TID + ".json")
out, pushed, events = run_main(PY + ' -c "' + LIVE_MONEY + '"', task_id=FAKE_TID,
                               env_extra={"PRETOOL_TEST_RUN": "1"})
res.append(ok('"ask"' in out, "СКВОЗНОЕ: решение хука ask (гард не ослаблен тест-режимом)"))
res.append(ok(pushed == [], "СКВОЗНОЕ: владельцу не ушло НИЧЕГО (перехват на границе)"))
res.append(ok(not os.path.exists(_live_plain) and not os.path.exists(_live_pref),
              "СКВОЗНОЕ: в БОЕВОМ каталоге маркеров не появилось ничего"))
res.append(ok(os.path.exists(_test_marker), "СКВОЗНОЕ: маркер ушёл в тест-каталог под test-именем"))
print("  ── что СОБИРАЛОСЬ уйти владельцу (перехвачено, не отправлено):")
for ln in (PG._card(AT, LIVE_MONEY) or "").splitlines():
    print("     | " + ln)

# ══════════════════════════════════════════════════════════════════════════════════════════════
print("(B) ДЕНЬГИ: карточка только при НАЗВАННОЙ ЦЕЛИ (литерал), а не на имя функции:")
# ДОСЛОВНАЯ боевая команда задачи 117 (транскрипт 2026-07-31T12:27:18 UTC), имена — кусками.
TASK117 = (
    PY + " -c '\n"
    "import re\n"
    'src = open("/root/turbobaby-manager-bot/splinter.py", encoding="utf-8").read()\n'
    'i = src.index("def _build_bike_card")\n'
    'j = src.index("\\ndef ", i + 10)\n'
    "body = src[i:j]\n"
    'print("строк в _build_bike_card:", body.count("\\n"))\n'
    'writes = ["set_fleet", "' + AT + '", "' + VL + '", "' + CB + '", "activate_' + "booking" + '",'
    ' "closing_' + "upsert" + '", "delete_' + "event" + '", "' + CONF + '", "_odo_store",'
    ' "write_doc", "append", "enqueue"]\n'
    "for w in writes:\n"
    "    n = body.count(w)\n"
    "    if n:\n"
    '        print("  ПИШУЩИЙ ПРИЗНАК:", w, n)\n'
    'print("bridge-вызовы:", sorted(set(re.findall(r"bridge\\.([a-z_]+)\\(", body))))\n'
    "'"
)
b, hit, obj, num = bucket(TASK117)
res.append(ok(hit == AT, "117: красным признаком по-прежнему остаётся денежное имя (hit=%s)" % hit))
res.append(ok(b == "журнал", "117 ДОСЛОВНО: карточки НЕТ, факт в журнал (получили %s)" % b))
res.append(ok(obj == "" and num == "", "117: цели не названо — объект=%r число=%r" % (obj, num)))
out, pushed, events = run_main(TASK117, task_id=FAKE_TID, env_extra={"PRETOOL_TEST_RUN": "1"})
res.append(ok('"ask"' in out, "117: решение ask осталось (без «да» команда не идёт)"))
res.append(ok(pushed == [], "117: владельцу не ушло ничего"))
res.append(ok(events == ["card_skipped"], "117: в журнале ровно card_skipped: %r" % events))

print("  настоящая денежная операция рождает карточку КАК ПРЕЖДЕ:")
REAL = (
    ("проводка с кошельком и суммой", PY + ' -c "' + LIVE_MONEY + '"', "кошелёк Наличка", "сумма -500"),
    ("отмена с кошельком", PY + ' -c "bridge.' + VL + "(group='Наличка')" + '"', "кошелёк Наличка", ""),
    ("отмена БЕЗ аргументов (природа операции)", PY + ' -c "bridge.' + VL + '()"',
     "вызов " + VL + "()", ""),
    ("проводка без кошелька, но с суммой", PY + ' -c "' + AT + '(amount=500)"',
     "вызов " + AT + "()", "сумма 500"),
)
for label, cmd, want_obj, want_num in REAL:
    b, hit, obj, num = bucket(cmd)
    res.append(ok(b == "КАРТОЧКА", label + ": КАРТОЧКА владельцу (получили %s)" % b))
    res.append(ok(want_obj in obj, label + ": цель названа — %r" % obj))
    if want_num:
        res.append(ok(want_num in num, label + ": число — %r" % num))

print("  имя денежной операции БЕЗ действия карточку не рождает:")
MENTIONS = (
    ("имя в списке слов", PY + ' -c "writes = [\'' + AT + "', '" + VL + "']\""),
    ("имя в прозе журнальной строки", PY + " cclog.py \"DONE: разобрал ветку " + AT + " в отчёте\""),
    ("имя через пробел перед скобкой (проза)", PY + ' -c "print(\'' + AT + ' (наша касса)\')"'),
)
for label, cmd in MENTIONS:
    b, hit, obj, num = bucket(cmd)
    res.append(ok(b in ("журнал", "defer"), label + ": карточки нет (получили %s, hit=%s)" % (b, hit)))

print("  правило card_gate и вторая линия (маркер) говорят ОДНО И ТО ЖЕ:")
res.append(ok(PG.card_gate(AT, "", "") is False, "деньги без цели → журнал (было: карточка всегда)"))
res.append(ok(PG.card_gate(VL, "", "") is False, "отмена без цели → журнал"))
res.append(ok(PG.card_gate(AT, "", "сумма 500") is True, "деньги: сумма — тоже названная цель"))
res.append(ok(PG.card_gate(AT, "кошелёк Наличка", "") is True, "деньги: кошелёк — цель"))
res.append(ok(PG.card_gate(SFO, "", "пробег 27000") is False,
              "НЕ деньги: число без объекта карточку не рождает (правило 29.07 цело)"))
res.append(ok(PG.marker_has_object(AT, PG._card(AT, "print('" + AT + "')")) is False,
              "вторая линия: денежная карточка из одних прочерков маркера НЕ пишет"))
res.append(ok(PG.marker_has_object(AT, PG._card(AT, LIVE_MONEY)) is True,
              "вторая линия: настоящая денежная карточка маркер пишет"))
res.append(ok(PG.marker_has_object(VL, PG._card(VL, "bridge." + VL + "()")) is True,
              "вторая линия: литеральный вызов без аргументов — цель названа"))

# ══════════════════════════════════════════════════════════════════════════════════════════════
print("(C) ФАЙЛ СЕКРЕТОВ: судим по ДЕЙСТВИЮ (чтение красное, слово в тексте — нет):")
PROSE = (
    ("строка журнала со словом в тексте",
     PY + ' cclog.py "DONE 12:00 UTC: поправил ' + ENVF + ', добавил флаг"'),
    ("отчёт echo со словом в тексте", 'echo "смотри ' + ENVF + ' — там флаг"'),
    ("текст своего коммита", 'git commit -m "правка ' + ENVF + ' форматом"'),
    ("шаблон поиска (данные)", 'grep -n "' + ENVF + '" ' + ROOT + "/pretool_guard.py"),
)
for label, cmd in PROSE:
    b, hit, _o, _n = bucket(cmd)
    res.append(ok(b == "defer", label + ": блока нет (получили %s)" % b))

READS = (
    ("cat файла секретов", "cat " + ROOT + "/" + ENVF),
    ("grep ПО файлу секретов", "grep -n TOKEN " + ROOT + "/" + ENVF),
    ("копирование файла секретов", "cp " + ROOT + "/" + ENVF + " /tmp/x"),
    ("бэкап-копия файла секретов", "cat " + ROOT + "/" + ENVF + ".bak-20260730"),
    ("python-скрипт с путём секретов в аргументе", PY + " dump.py " + ROOT + "/" + ENVF),
    ("чтение из инлайн-кода", PY + ' -c "load_dotenv(\'' + ROOT + "/" + ENVF + '\')"'),
    ("чтение из инлайн-кода с пробелами", PY + ' -c "p = \'' + ROOT + "/" + ENVF
     + '\'; print(open(p).read())"'),
    ("подстановка команды", 'echo "$(cat ' + ROOT + "/" + ENVF + ')"'),
    ("через шелл в конце цепи", 'echo "cat ' + ROOT + "/" + ENVF + '" | bash'),
    ("шелл с -c", 'bash -c "cat ' + ROOT + "/" + ENVF + '"'),
    ("относительный путь", "cat " + ENVF),
)
for label, cmd in READS:
    b, hit, _o, _n = bucket(cmd)
    res.append(ok(b == "БЛОК" and hit == "env_hard_block", label + ": ЖЁСТКИЙ БЛОК (получили %s)" % b))

# ══════════════════════════════════════════════════════════════════════════════════════════════
print("(D) регресс границ: ничего смежного не ослаблено:")
out, pushed, events = run_main("p" + "kill -9 spl" + "inter", task_id=FAKE_TID,
                               env_extra={"PRETOOL_TEST_RUN": "1"})
res.append(ok('"deny"' in out and pushed == [], "гашение боевого процесса → deny без карточки"))
out, pushed, events = run_main("cat " + ROOT + "/" + ENVF, task_id=FAKE_TID,
                               env_extra={"PRETOOL_TEST_RUN": "1"})
res.append(ok('"deny"' in out and pushed == [], "файл секретов → deny без карточки"))
LIVE_OIL = "bridge." + SFO + "(number='6789', oil_km=27000, " + CONF + ")"
b, hit, obj, num = bucket(PY + ' -c "' + LIVE_OIL + '"')
res.append(ok(b == "КАРТОЧКА" and "байк 6789" in obj and "пробег 27000" in num,
              "объектный гейт парка цел: %s объект=%r число=%r" % (b, obj, num)))
b, hit, obj, num = bucket(PY + ' -c "bridge.' + CB + '(client=\'Jack\', ' + CONF + ')"')
res.append(ok(b in ("КАРТОЧКА", "БЛОК"), "живая сущность CRM по-прежнему не проходит молча: %s" % b))
res.append(ok(PG._entity_blocktype(CB, "bridge." + CB + "(client='Jack')") == "hard",
              "ЖИВАЯ сущность → hard (approve невозможен) — регресс цел"))
res.append(ok(bucket("grep -n def " + ROOT + "/bot.py")[0] == "defer", "зелёная рутина зелёная"))
res.append(ok(bucket(PY + " gate.py")[0] == "defer", "гейт по-прежнему зелёный"))
res.append(ok(bucket("systemctl restart splinter")[0] == "defer",
              "рестарт своего сервиса — штатный поток (не красное)"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
