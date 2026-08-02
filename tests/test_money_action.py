# -*- coding: utf-8 -*-
"""ДЕНЕЖНЫЙ КЛАСС: карточку рождает ДЕЙСТВИЕ, а не совпадение слова (02.08.2026).

ЖИВОЙ ФАКТ. Пять карточек за трое суток — 117, 135, 140, 181, 208 — пришли владельцу как
«проводка ДЕНЕГ в кассу». Настоящей проводки не было ни за одной. Два корня, оба дословные:

  208 (02.08 20:04 UTC, `venv/bin/python3 _scratch_evkey_0802a/recon_empty_keys.py`) — тело
      РАЗВЕДКИ splinter.log: в фильтре строк стоит `or "add_transaction" in line`. Красное дал
      СТРОКОВЫЙ ЛИТЕРАЛ; объект извлекать было не из чего, а денежный класс обходил объектный
      гейт через `_ALWAYS_CARD` → владельцу ушли одни прочерки, задача умерла в needs_approval.
  117 (31.07 12:27 UTC) — инлайн-подсчёт пишущих признаков СПИСКОМ СЛОВ: `writes = ["set_fleet",
      "add_transaction", …]`. Задача просила ровно `systemctl restart splinter`; 37000/38982 в
      её задании — ПРОБЕГ, денег там не было вовсе.

ЧТО ПРОВЕРЯЕТСЯ ЗДЕСЬ:
  (1) дословные тела 208 и 117 карточки НЕ рождают;
  (2) настоящий вызов проводки рождает — с НАЗВАННЫМИ кошельком и суммой, включая формы
      «значение вычисляется» и «диспетчер по строке» (`_post("add_transaction", …)`);
  (3) объектный гейт распространён на деньги, а жёсткий блок по-прежнему спрашивает ВСЕГДА;
  (4) слепое тело (heredoc/stdin) судится подстрокой, как раньше — fail-closed;
  (5) соседние классы (парк/CRM/удаление/SQL/процессы/секреты/зелёная рутина) не тронуты.

181 — ОТДЕЛЬНЫЙ КЛАСС, и это показано числами, а не словами: его карточка несла «кошелёк Наличка,
сумма −500» (денежный голден `tests/test_pretool_probe_dedup.py`), то есть НАСТОЯЩИЙ разобранный
вызов. Карточку там рождать и надо — не доехать до владельца она должна была изоляцией пробы
(`a739ee9` + `PRETOOL_BLOCK_DIR` в фикстуре). Дословная команда 181 проверяется в секции (2) как
ПОЛОЖИТЕЛЬНЫЙ голден: после правки она карточку рождает — с кошельком и суммой.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ ШЛЁТ: зовутся ЧИСТЫЕ функции (classify/card_min/card_gate/
_card/marker_has_object), main() не вызывается, подпроцессов нет → ни пуша, ни маркера. Красные
литералы в САМОМ файле собраны конкатенацией (иначе гард краснеет на файле теста); в фикстуры,
которые пишутся во временный каталог, они попадают целыми — там и нужен живой формат.
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

AT = "add_" + "transaction"
VL = "void_" + "last"
SFO = "set_fleet_" + "oil"
CB = "create_" + "booking"
CONF = "confirmed" + "=" + "true"
PY = "venv/bin/python3"

TMP = tempfile.mkdtemp(prefix="money_action_")
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


# ══ (1) ДОСЛОВНЫЕ ТЕЛА, УБИВШИЕ ЗАДАЧИ 208 и 117 ═══════════════════════════════════════════════
print("(1) дословные разведки 208 и 117: имя операции в литерале карточки не рождает:")

# Тело 208 — фрагмент СНЯТ С ЖИВОГО ФАЙЛА `_scratch_evkey_0802a/recon_empty_keys.py` (задача 209
# читала им splinter.log). Важны три вещи разом: имя операции стоит в СРАВНЕНИИ (`in line`),
# импорты чисто-разборные (re, datetime), вызовов-каналов нет.
BODY_208 = (
    '"""Разведка (read-only): сколько записей события с ПУСТЫМ ключом за 7 суток."""\n'
    "import re\n"
    "import datetime\n"
    'LOG = "/root/turbobaby-manager-bot/splinter.log"\n'
    'DIAG = re.compile(r"→ add_event: .*?msg_id=(.*?) info_works=")\n'
    'marks = ["2026-08-01 07:5", "2026-08-02 04:11"]\n'
    'with open(LOG, encoding="utf-8", errors="replace") as f:\n'
    "    for line in f:\n"
    "        if any(line.startswith(mk) for mk in marks):\n"
    '            if ("add_event" in line or "событ" in line.lower() or "ERROR" in line\n'
    '                    or "' + AT + '" in line):\n'
    '                print("  ", line.rstrip()[:190])\n'
)
b, hit, obj, num = bucket(fixture("recon_empty_keys.py", BODY_208))
ok(b == "defer", "208 ДОСЛОВНО: карточки нет и красного нет — %s (hit=%s)" % (b, hit or "—"))
ok(hit != AT, "208: денежный класс к этой разведке больше не относится")

# ДОСЛОВНАЯ команда 117 (транскрипт 2026-07-31T12:27:18 UTC): инлайн-подсчёт пишущих признаков.
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
ok(hit != AT, "117 ДОСЛОВНО: денежное имя из списка слов класс больше не назначает (hit=%s)" % hit)
ok(b != "КАРТОЧКА", "117 ДОСЛОВНО: карточки владельцу НЕТ — %s (объект=%r)" % (b, obj))
# ЧЕСТНО НАЗВАННЫЙ ОСТАТОК: тот же список слов содержит имена операций ЖИВЫХ ТАБЛИЦ, и они
# по-прежнему красят команду (правило «сомнение краснее» для них не менялось). Владельца это уже
# не будит — объекта нет, карточка гаснет, — но команда без «да» не идёт. Класс тот же, ветка иная.
ok(b == "журнал" and hit == CB,
   "117: остаток назван — красит имя операции CRM из того же списка (hit=%s, %s)" % (hit, b))

# Живой файл 208, если он ещё на диске: та же проверка по НАСТОЯЩИМ байтам, а не по копии.
LIVE_208 = os.path.join(ROOT, "_scratch_evkey_0802a", "recon_empty_keys.py")
if os.path.isfile(LIVE_208):
    b, hit, _o, _n = bucket(PY + " " + LIVE_208)
    ok(b == "defer" and hit != AT, "208: ЖИВОЙ файл разведки — %s (hit=%s)" % (b, hit or "—"))
else:
    print("  NOTE живого файла 208 на диске нет — проверено копией фрагмента выше")

print("  имя операции в комментарии, прозе и шаблоне поиска — тоже не действие:")
for label, body in (
    ("комментарий", "# проводку " + AT + " тут НЕ делаем\nprint(1)\n"),
    ("докстринг", '"""Отчёт: разобрал ветку ' + AT + ' и ' + VL + '."""\nprint(1)\n'),
    ("печать имени", "print('" + AT + "')\n"),
    ("список слов + поиск", "import re\nTOK = ('" + AT + "', '" + VL + "')\n"
                            "print(any(t in open('/etc/hostname').read() for t in TOK))\n"),
    # ВНИМАНИЕ на форму: без префикса r у ЭТОГО куска — иначе `\n` уедет в фикстуру буквально,
    # тело перестанет разбираться, и проверка молча уйдёт в ветку слепого тела (fail-closed).
    ("шаблон регулярки", "import re\nRX = re.compile(r'" + AT + "[: ]')\nprint(RX.pattern)\n"),
):
    b, hit, _o, _n = bucket(fixture("m_%s.py" % abs(hash(label)), body))
    ok(b == "defer", label + ": красного нет — %s (hit=%s)" % (b, hit or "—"))

# ══ (2) НАСТОЯЩАЯ ПРОВОДКА — КАК ПРЕЖДЕ, С НАЗВАННОЙ ЦЕЛЬЮ ═════════════════════════════════════
print("(2) настоящий вызов проводки: карточка с кошельком и суммой:")

# ДОСЛОВНЫЙ голден задачи 181 — MONEY_CALL из tests/test_pretool_probe_dedup.py.
LIVE_181 = "bridge." + AT + "(group='Наличка', amount=-500)"
b, hit, obj, num = bucket(fixture("fx_red_live.py", "# фикстура регресса\n" + LIVE_181 + "\n"))
ok(b == "КАРТОЧКА" and hit == AT, "181 ДОСЛОВНО: карточка рождается — %s (hit=%s)" % (b, hit))
ok("кошелёк Наличка" in obj, "181: кошелёк назван — %r" % obj)
ok("сумма -500" in num, "181: сумма названа — %r" % num)

REAL = (
    ("инлайн-проводка", PY + ' -c "' + AT + '(amount=500)"', "вызов " + AT + "()", "сумма 500"),
    ("отмена с кошельком", PY + ' -c "bridge.' + VL + "(group='Наличка')" + '"', "кошелёк Наличка", ""),
    ("отмена БЕЗ аргументов (природа операции)", PY + ' -c "bridge.' + VL + '()"',
     "вызов " + VL + "()", ""),
)
for label, cmd, want_obj, want_num in REAL:
    b, hit, obj, num = bucket(cmd)
    ok(b == "КАРТОЧКА", label + ": КАРТОЧКА владельцу (получили %s)" % b)
    ok(want_obj in obj, label + ": цель названа — %r" % obj)
    if want_num:
        ok(want_num in num, label + ": число — %r" % num)

print("  формы, которые текстом неотличимы от упоминания, а по разбору — действие:")
FX_VAR = ("import bridge_client as bc\nwallet = input()\nsum_ = -500\n"
          "bc." + AT + "(group=wallet, amount=sum_)\n")
b, hit, obj, num = bucket(fixture("fx_money_var.py", FX_VAR))
ok(b == "КАРТОЧКА" and hit == AT, "вычисляемые аргументы: карточка есть (%s)" % b)
ok("вычисляется" in obj, "вычисляемый кошелёк назван честно — %r" % obj)

FX_DISPATCH = ("import bridge_client as bc\nw = input()\n"
               'bc._post("' + AT + '", group=w, amount=-500)\n')
b, hit, obj, num = bucket(fixture("fx_money_post.py", FX_DISPATCH))
ok(b == "КАРТОЧКА" and hit == AT, "диспетчер по строке (_post): красное и карточка (%s)" % b)
ok(obj.strip() != "", "диспетчер: цель названа — %r" % obj)

FX_HTTP = ("import requests\n"
           'requests.post("https://script.google.com/x", data={"action": "' + AT + '",'
           ' "group": "Наличка", "amount": -500})\n')
b, hit, obj, num = bucket(fixture("fx_money_http.py", FX_HTTP))
ok(b == "КАРТОЧКА" and hit == AT, "сырой HTTP-запрос к мосту: красное и карточка (%s)" % b)

FX_GETATTR = ("import bridge_client as bc\n"
              'fn = getattr(bc, "' + AT + '")\nfn(group="Наличка", amount=-500)\n')
b, hit, _o, _n = bucket(fixture("fx_money_getattr.py", FX_GETATTR))
ok(b == "КАРТОЧКА" and hit == AT, "вызов через getattr: красное и карточка (%s)" % b)

FX_REF = "import bridge_client as bc\nfn = bc." + VL + "\n"
b, hit, _o, _n = bucket(fixture("fx_money_ref.py", FX_REF))
ok(hit == VL, "ссылка на функцию без скобок — имя КОДА, красное (hit=%s)" % hit)

# ══ (3) СЛЕПОЕ ТЕЛО: подстрока, как раньше (fail-closed) ═══════════════════════════════════════
print("(3) слепое тело (stdin/heredoc/нечитаемое): судим подстрокой, направление краснее:")
HEREDOC = (PY + " - <<'PYX'\nimport bridge_client as bc\n"
           "bc." + AT + "(group='Наличка', amount=-500)\nPYX")
b, hit, obj, num = bucket(HEREDOC)
ok(hit == AT and b == "КАРТОЧКА", "heredoc с настоящей проводкой: красное + карточка (%s)" % b)
ok("кошелёк Наличка" in obj, "heredoc: кошелёк вынут из текста — %r" % obj)

HEREDOC_MENTION = PY + " - <<'PYX'\nprint('" + AT + "')\nPYX"
b, hit, _o, _n = bucket(HEREDOC_MENTION)
ok(hit == AT, "ПРЕДЕЛ НАЗВАН: в слепом теле даже упоминание красное (hit=%s) — разбора нет" % hit)

BROKEN_PY = PY + " -c 'bridge." + AT + "(group='"          # шелл разбирает, python — нет
b, hit, _o, _n = bucket(BROKEN_PY)
ok(hit == AT, "тело не разобралось: прежняя подстрока (hit=%s)" % hit)

BROKEN_SH = PY + ' -c "bridge.' + AT + "(group='Наличка'"   # незакрытая кавычка — не разбирает шелл
b, hit, _o, _n = bucket(BROKEN_SH)
ok(hit == AT, "команда не разобралась шеллом: тоже подстрока, не тишина (hit=%s)" % hit)

FX_BROKEN_FILE = "import bridge_client as bc\nbc." + AT + "(group='Наличка',\n"   # обрыв файла
b, hit, _o, _n = bucket(fixture("fx_broken.py", FX_BROKEN_FILE))
ok(hit == AT, "оборванный файл: подстрока (hit=%s)" % hit)

# ══ (4) ОБЪЕКТНЫЙ ГЕЙТ РАСПРОСТРАНЁН НА ДЕНЬГИ ════════════════════════════════════════════════
print("(4) правило объекта одно для всех классов; жёсткий блок спрашивает всегда:")
ok(PG.card_gate(AT, "", "") is False, "деньги без цели → журнал (было: карточка всегда)")
ok(PG.card_gate(VL, "", "") is False, "отмена без цели → журнал")
ok(PG.card_gate(AT, "кошелёк Наличка", "") is True, "деньги: кошелёк — цель → карточка")
ok(PG.card_gate(AT, "вызов " + AT + "()", "сумма 500") is True, "деньги: вызов — тоже цель")
ok(PG.card_gate(SFO, "", "пробег 27000") is False,
   "НЕ деньги: число без объекта карточку не рождает (правило 29.07 цело)")
ok(PG.card_gate(SFO, "байк 6789", "") is True, "НЕ деньги: объект без числа → карточка (регресс)")
ok(not hasattr(PG, "_ALWAYS_CARD"), "исключение _ALWAYS_CARD снято, а не переименовано")

bare = PG._card(AT, "print('" + AT + "')")
ok("Объект: —" in bare and PG.marker_has_object(AT, bare) is False,
   "вторая линия: денежная карточка из одних прочерков маркера НЕ пишет")
live_card = PG._card(AT, LIVE_181)
ok(PG.marker_has_object(AT, live_card) is True, "вторая линия: настоящая денежная карточка — маркер")
ok(PG.marker_has_object(VL, PG._card(VL, "bridge." + VL + "()")) is True,
   "вторая линия: вызов без аргументов — цель названа")

for label, cmd in (("гашение боевого процесса", "pkill -9 spl" + "inter"),
                   ("файл секретов", "cat " + ROOT + "/." + "env")):
    b, hit, _o, _n = bucket(cmd)
    ok(b == "БЛОК", label + ": жёсткий блок на месте — %s (hit=%s)" % (b, hit))

# ══ (5) СОСЕДНИЕ КЛАССЫ НЕ ТРОНУТЫ ════════════════════════════════════════════════════════════
print("(5) границы: соседние классы байт-в-байт:")
LIVE_OIL = "import bridge_client as bc\nbc." + SFO + "(number='6789', oil_km=27000, " + CONF + ")\n"
b, hit, obj, num = bucket(fixture("fx_oil.py", LIVE_OIL))
ok(hit == SFO and "байк 6789" in obj and "пробег 27000" in num,
   "парк: класс, объект и число прежние (%s, %r, %r)" % (hit, obj, num))
b, hit, obj, _n = bucket(fixture("fx_oil_bare.py", "print('" + SFO + "')\n"))
ok(hit == SFO and b == "журнал",
   "парк: голое упоминание — красное без карточки, как было (%s, hit=%s)" % (b, hit))
b, hit, _o, _n = bucket(fixture("fx_conf.py", "payload = {'confirmed' : True}\nprint(payload)\n"))
ok(hit == "confirmed", "разбор confirmed (корень А) цел: hit=%s" % hit)
SQL_FOREIGN = ("import sqlite3\ncon = sqlite3.connect('/var/lib/other/app.db')\n"
               "con.execute('DELETE " + "FROM sessions WHERE id=5')\n")
b, hit, obj, _n = bucket(fixture("fx_sql.py", SQL_FOREIGN))
ok(hit == "sqlite" and b == "КАРТОЧКА", "SQL в чужую БД: класс и карточка прежние (%s)" % b)
for label, cmd in (("зелёная рутина", "grep -n def " + ROOT + "/bot.py"),
                   ("гейт", PY + " gate.py"),
                   ("рестарт своего сервиса", "systemctl restart splinter")):
    ok(bucket(cmd)[0] == "defer", label + ": зелёное")

shutil.rmtree(TMP, ignore_errors=True)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
