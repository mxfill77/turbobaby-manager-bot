# -*- coding: utf-8 -*-
"""УДАЛЕНИЕ ИЗ ТЕЛА PYTHON — ТА ЖЕ ДОКТРИНА, ЧТО У КОМАНДЫ ОБОЛОЧКИ (03.08.2026).

ЧТО ЗДЕСЬ ЗАКРЫТО. Остаток артефакта `docs/artifacts/2026-08-03-delete-outside-tmp.md` §6.2:
класс удаления закрыли на ОБОЛОЧКЕ, а `os.remove("<файл репо>")` в теле НЕотслеживаемого скрипта
по-прежнему уходил в defer — то есть решал allow-слой, где на уборку черновиков стоит
`Bash(rm -f …/_*.py)`. Доктрина (CLAUDE.md, редакция Б) относит ЛЮБОЕ удаление данных и файлов вне
временных каталогов к КРАСНОМУ высшего вида, и поверхность, на которой стоит глагол, доктрину не
меняет: правило одно — судим ПО ЦЕЛИ.

  • цель — КОНКРЕТНЫЙ путь под /tmp, /var/tmp, /dev/shm → уборка своего черновика, ЗЕЛЁНОЕ;
  • цель вне временных каталогов                        → КРАСНОЕ, объект карточки — путь;
  • цель НЕВЫЧИСЛИМА (переменная извне, f-строка, join с переменной, glob, os.environ) → КРАСНОЕ
    fail-closed: объекта нет → карточки нет (общий гейт card_gate не тронут), решение ask
    остаётся, команда НЕ ПРОХОДИТ.

ПОЧЕМУ РАЗБОРОМ (ast), А НЕ ПОДСТРОКОЙ: иначе вернулся бы класс 02.08 с другой стороны — слово
`os.remove` в комментарии-шапке или в строке-шаблоне разведки командой не является, а карточка за
ним пришла бы и в headless убила бы задачу (ask = отказ). Красное рождает РАЗОБРАННЫЙ ВЫЗОВ.

ЗАМЕР 168 ч (2026-07-27 → 08-03, транскрипты): 3075 живых Bash-команд и 460 питонных тел; 21 живой
вызов удаления, у 14 цель — ПЕРЕМЕННАЯ. Прямое «переменная → красное» убило бы законную уборку
своего черновика (риск назван в §6.2), поэтому цель резолвится по связкам ТЕЛА (присваивание, цикл
по литеральному списку, `with … as`, `tempfile.*`). Итог замера: решений изменилось РОВНО ОДНО —
`_drop_markers.py` с `os.path.join(DIR, переменная)`; это НАЗВАННАЯ цена fail-closed, голден (1.5).

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ И НИЧЕГО НЕ УДАЛЯЕТ: тела-фикстуры кладутся во временный каталог, зовутся
чистые функции + main() в ЭТОМ процессе (stdin/stdout/_push подменены). Красные литералы собраны
конкатенацией (образец — test_delete_outside_tmp): иначе гард краснеет на САМОМ файле теста.
"""
import ast
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

TMP = tempfile.mkdtemp(prefix="pt_pydel_").replace(os.sep, "/")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

REPO = "/root/turbobaby-manager-bot"
PY = "venv/bin/python3"
HIT = "delete_" + "file"
SFO = "set_fleet_" + "oil"
CONF = "confirmed" + "=True"
ENVF = "." + "env"
RM = "r" + "m"

res = []
_seq = [0]


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def cmd_of(body, name=""):
    """Тело → команда запуска чернового скрипта (имя с «_» → тело ЧИТАЕТСЯ, как у черновика)."""
    _seq[0] += 1
    path = TMP + "/" + (name or "_case%03d.py" % _seq[0])
    with open(path, "w", encoding="utf-8") as f:
        f.write("# фикстура\n" + body + "\n")
    return PY + " " + path


def verdict(body):
    """Тело → (kind, hit, объект карточки)."""
    kind, hit, blob = PG.classify(cmd_of(body), ROOT)
    return kind, hit, PG.card_min(hit, blob)[0]


def red(body, label, obj_sub=None):
    kind, hit, obj = verdict(body)
    good = kind == "red" and hit == HIT
    if obj_sub is not None:
        good = good and obj_sub in obj
    return ok(good, "%s → kind=%s hit=%s объект=«%s»" % (label, kind, hit, obj))


def green(body, label):
    kind, hit, _o = verdict(body)
    return ok(kind == "green", "%s → kind=%s hit=%s" % (label, kind, hit or "—"))


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


# ── ГОЛДЕНЫ ЖИВОГО ЗАМЕРА: тела ДОСЛОВНО из транскриптов окна 168 ч ───────────────────────────
LIVE_LOOP = ("import os\n"
             "for p in ('/tmp/tb_scratch/_w.txt', '/tmp/tb_scratch/old_od.py',"
             " '/tmp/tb_scratch/head_od.py'):\n"
             "    os.remove(p)\n")
LIVE_RMTREE = "import shutil\nshutil.rmtree('/tmp/tb_scratch')\n"
LIVE_RMDIR = "import os\nos.rmdir('/tmp/tb_scratch')\n"
LIVE_MKDTEMP = ("import shutil, tempfile\n"
                "d = tempfile.mkdtemp(prefix='guard_replay_st_')\n"
                "shutil.rmtree(d, ignore_errors=True)\n")
LIVE_JOINVAR = ("import os\n"
                "DIR = '/tmp/cc_guard_block'\n"
                "for n in os.listdir(DIR):\n"
                "    os.remove(os.path.join(DIR, n))\n")

print("(1) ГОЛДЕНЫ ЗАМЕРА 168 ч — дословные живые тела:")
res.append(green(LIVE_LOOP, "1.1 цикл по литеральному кортежу /tmp (живой инлайн) — уборка своя"))
res.append(green(LIVE_RMTREE, "1.2 shutil.rmtree('/tmp/tb_scratch') — свой каталог"))
res.append(green(LIVE_RMDIR, "1.3 os.rmdir('/tmp/tb_scratch') — свой каталог"))
res.append(green(LIVE_MKDTEMP, "1.4 mkdtemp → rmtree (12 из 20 живых связок цели)"))
res.append(red(LIVE_JOINVAR, "1.5 join(литерал, ПЕРЕМЕННАЯ) — единственное изменившееся решение замера"))
_k, _h, _o = verdict(LIVE_JOINVAR)
res.append(ok(_o == "", "1.5 у него объекта НЕТ → карточки нет, но ask остаётся (fail-closed)"))

print("(2) ДОКТРИНА ЦЕЛИ: судим по ЦЕЛИ, а не по глаголу:")
res.append(red("import os\nos.remove('" + REPO + "/bot.py')\n",
               "2.1 файл репо", "bot.py"))
res.append(red("import os\nos.remove('" + REPO + "/_envfix_probe.py')\n",
               "2.2 отслеживаемый git черновик (тот самый файл из §2 артефакта)", "_envfix_probe.py"))
res.append(green("import os\nos.remove('/var/tmp/x.txt')\n", "2.3 /var/tmp — временный каталог"))
res.append(green("import os\nos.remove('/dev/shm/x.txt')\n", "2.4 /dev/shm — временный каталог"))
res.append(red("import shutil\nshutil.rmtree('/tmp')\n", "2.5 САМ корень /tmp — не уборка черновика"))
res.append(red("import shutil\nshutil.rmtree('/tmp/')\n", "2.6 корень /tmp со слешем"))
res.append(red("import os\nos.remove('/tmp/../root/x.py')\n", "2.7 «..» уводит из временного"))
res.append(red("import os\nos.remove('/tmp/*.json')\n", "2.8 маска в литерале (как у оболочки)"))
res.append(red("import os\nos.remove('x.py')\n", "2.9 относительное имя (cwd = репо, не /tmp)", "x.py"))
res.append(red("import os\nfor p in ('/tmp/a.txt', '" + REPO + "/_x.py'):\n    os.remove(p)\n",
               "2.10 в цикле ОДИН путь вне /tmp → красное по нему", "_x.py"))
res.append(red("import os\np = '/tmp/a.txt'\np = '" + REPO + "/_x.py'\nos.remove(p)\n",
               "2.11 имя связано дважды, вторая связка наружу → красное"))

print("(3) FAIL-CLOSED: цель невычислима → красное БЕЗ объекта (ask остаётся):")
for body, label in (
        ("import os\nJ = f'/tmp/claim_{os.getpid()}.jsonl'\nos.remove(J)\n", "3.1 f-строка"),
        ("import os\np = os.environ['X']\nos.remove(p)\n", "3.2 os.environ"),
        ("import os, sys\nos.remove(sys.argv[1])\n", "3.3 sys.argv"),
        ("import os, glob\nfor p in glob.glob('/tmp/x/*.py'):\n    os.remove(p)\n", "3.4 glob"),
        ("import os, tempfile\nd = tempfile.mkdtemp()\nos.remove(d.replace('a', 'b'))\n",
         "3.5 произвольный метод поверх временного пути"),
        ("import shutil\ndef f(p):\n    shutil.rmtree(p)\n", "3.6 аргумент функции")):
    kind, hit, obj = verdict(body)
    res.append(ok(kind == "red" and hit == HIT and obj == "",
                  "%s → красное, объект пуст (kind=%s объект=«%s»)" % (label, kind, obj)))
res.append(ok(PG.card_gate(HIT, "") is False,
              "3.7 общий объектный гейт: без объекта карточки нет (журнал, не владелец)"))

print("(4) РАЗБОР, А НЕ ПОДСТРОКА (класс 02.08 не возвращается с другой стороны):")
res.append(green("# os.remove('" + REPO + "/bot.py') — так делать нельзя\nprint('ok')\n",
                 "4.1 имя удаления в КОММЕНТАРИИ действием не является"))
res.append(green('"""os.remove(' + REPO + '/bot.py)"""\nprint(1)\n',
                 "4.2 имя удаления в ДОКСТРИНГЕ"))
res.append(green("pat = 'os.remove'\nprint([l for l in open('/tmp/x.log') if pat in l])\n",
                 "4.3 имя удаления в строке-ШАБЛОНЕ разведки"))
res.append(green("VERBS = ['os.remove', 'shutil.rmtree']\nprint(len(VERBS))\n",
                 "4.4 имя удаления в СПИСКЕ СЛОВ (дословный корень карточки 117)"))
res.append(green("xs = ['a', 'b']\nxs.remove('a')\nprint(xs)\n",
                 "4.5 list.remove — приёмник не os, файловой операции нет"))
res.append(green("class Q:\n    def remove(self, k):\n        return k\nQ().remove('" + REPO + "/bot.py')\n",
                 "4.6 чужой метод remove у своего класса"))
res.append(green("import re\nprint(re.sub('rmtree', '', 'x'))\n", "4.7 глагол как аргумент-строка"))

print("(5) ФОРМЫ ВЫЗОВА (разбор, а не список написаний):")
res.append(red("import os\nos.unlink('" + REPO + "/_a.py')\n", "5.1 os.unlink", "_a.py"))
res.append(red("import os\nos.removedirs('" + REPO + "/docs')\n", "5.2 os.removedirs", "docs"))
res.append(red("import os as o\no.remove('" + REPO + "/_a.py')\n", "5.3 import os as o", "_a.py"))
res.append(red("from os import remove as rmf\nrmf('" + REPO + "/_a.py')\n",
               "5.4 from os import remove as rmf", "_a.py"))
res.append(red("from shutil import rmtree\nrmtree('" + REPO + "/tests')\n",
               "5.5 from shutil import rmtree", "tests"))
res.append(red("from pathlib import Path\nPath('" + REPO + "/_a.py').unlink()\n",
               "5.6 Path(литерал).unlink() — цель это САМ приёмник", "_a.py"))
res.append(green("from pathlib import Path\nPath('/tmp/tb_scratch/a.txt').unlink(missing_ok=True)\n",
                 "5.7 Path('/tmp/…').unlink(missing_ok=True) — свой черновик"))
res.append(green("import tempfile\nfrom pathlib import Path\nd = tempfile.mkdtemp()\n"
                 "(Path(d) / 'a.txt').unlink()\n", "5.8 Path(mkdtemp) / 'имя'"))
res.append(green("import os, tempfile\nd = tempfile.mkdtemp()\nos.unlink(os.path.join(d, 'a.txt'))\n",
                 "5.9 join(mkdtemp, литерал)"))
res.append(green("import shutil, tempfile\nwith tempfile.TemporaryDirectory() as d:\n"
                 "    shutil.rmtree(d)\n", "5.10 with TemporaryDirectory() as d"))
res.append(red("import os, tempfile\nd = tempfile.mkdtemp()\n"
               "os.remove(os.path.join(d, '..', '..', 'root', 'x.py'))\n",
               "5.11 join(mkdtemp, '..') — побег из временного каталога виден"))
res.append(red("import os\nos.remove(path='" + REPO + "/_a.py')\n",
               "5.12 цель именованным аргументом path=", "_a.py"))
res.append(green("import os\nos.remove(os.path.join('/tmp/tb_scratch', 'a.txt'))\n",
                 "5.13 join(литерал /tmp, литерал)"))

print("(6) ВСТРОЕННАЯ ОБОЛОЧКА: одно правило на обе поверхности:")
res.append(red("import subprocess\nsubprocess.run(['" + RM + "', '-f', '" + REPO + "/_a.py'])\n",
               "6.1 subprocess argv вне /tmp", "_a.py"))
res.append(green("import subprocess\nsubprocess.run(['" + RM + "', '-f', '/tmp/tb_scratch/a.txt'])\n",
                 "6.2 subprocess argv в /tmp — уборка своя"))
res.append(red("import os\nos.system('" + RM + " -rf " + REPO + "/docs')\n",
               "6.3 os.system строкой", "docs"))
res.append(green("import subprocess\nsubprocess.run(['echo', 'a; " + RM + " -f " + REPO + "/x.py'])\n",
                 "6.4 глагол ВНУТРИ литерала-аргумента echo — данные, не команда"))
kind6, hit6, obj6 = verdict("import subprocess, sys\nsubprocess.run(['" + RM + "', '-f', sys.argv[1]])\n")
res.append(ok(kind6 == "red" and hit6 == HIT and obj6 == "",
              "6.5 argv с невычислимым элементом → красное без объекта (kind=%s)" % kind6))
res.append(green("import subprocess\nsubprocess.run(['git', 'status', '--short'])\n",
                 "6.6 обычный subprocess без удаления не краснеет"))

print("(7) ПОРЯДОК КЛАССОВ: запись дороже уборки (владелец видит карточку про ЗАПИСЬ):")
kind7, hit7, _o7 = verdict("import bridge_client, os\n"
                           "bridge_client." + SFO + "(number='1234', oil_km=27000, " + CONF + ")\n"
                           "os.remove('" + REPO + "/_a.py')\n")
res.append(ok(kind7 == "red" and hit7 != HIT,
              "7.1 запись в Лист1 + уборка файла → карточка про запись (hit=%s)" % hit7))
kind8, hit8, _o8 = verdict("import sqlite3, os\n"
                           "c = sqlite3.connect('/root/other.db')\n"
                           "c.execute('UPDATE t SET a=1')\n"
                           "os.remove('" + REPO + "/_a.py')\n")
res.append(ok(kind8 == "red" and hit8 == "sqlite",
              "7.2 SQL в чужую БД + уборка файла → карточка про SQL (hit=%s)" % hit8))
out_b, _p, _e = run_main("cat " + REPO + "/" + ENVF + " ; " + PY + " " + TMP + "/_case001.py")
res.append(ok("block" in out_b or "deny" in out_b,
              "7.3 жёсткий блок секретов не ослаблен соседством питонного тела"))

print("(8) ПРЕЖНЕЕ НЕ ОСЛАБЛЕНО:")
res.append(ok(PG.classify(RM + " -f " + REPO + "/_a.py", ROOT)[:2] == ("red", HIT),
              "8.1 класс оболочки (03.08) на месте"))
res.append(ok(PG.classify(RM + " /tmp/cc_guard_block/12.json", ROOT)[0] == "green",
              "8.2 уборка маркеров в /tmp оболочкой — зелёная, как была"))
res.append(green("import json\nprint(json.dumps({'a': 1}))\n", "8.3 обычное тело без удаления"))
_amb = PG.classify(PY + " " + TMP + "/_нет_такого.py", ROOT)[0]
res.append(ok(_amb == "ambiguous", "8.4 нечитаемое тело → ambiguous (слой слеп, как и был): " + _amb))
res.append(ok(PG._py_del_class(None) is None, "8.5 view=None → падения нет"))
res.append(ok(PG._py_del_class({"text": "", "calls": {}}) is None,
              "8.6 вид без ключа dels (легаси) → падения нет"))
res.append(ok(PG._py_dels(ast.parse("import os\nos.remove('/tmp/a')\n")) != [],
              "8.7 _py_dels видит вызов"))
res.append(ok(PG._py_dels(ast.parse("print(1)\n")) == [], "8.8 без вызова — пусто"))

# Доверенные тела tests/ в бою НЕ читаются вовсе (ранний defer в _analyze) — проверяем на ЖИВОМ
# файле репо, у которого удаление есть и цель невычислима: он обязан остаться зелёным.
_trusted = ""
for _n in sorted(os.listdir(os.path.join(ROOT, "tests"))):
    if not _n.startswith("test_") or not _n.endswith(".py"):
        continue
    try:
        with open(os.path.join(ROOT, "tests", _n), encoding="utf-8") as _f:
            _tree = ast.parse(_f.read())
    except Exception:
        continue
    if PG._py_del_class({"dels": PG._py_dels(_tree)}):
        _trusted = _n
        break
if _trusted:
    res.append(ok(PG.classify(PY + " tests/" + _trusted, ROOT)[0] == "green",
                  "8.9 доверенное тело tests/ (%s) читается НЕ будет → зелёное" % _trusted))
else:
    print("  SKIP  8.9 в tests/ сейчас нет тела с некрасным-неразрешимым удалением")

print("(9) main(): решение ask, маркер, путь в решении:")
out1, pushed1, ev1 = run_main(cmd_of("import os\nos.remove('" + REPO + "/_a.py')\n"), task_id="801")
res.append(ok('"ask"' in out1, "9.1 красное удаление из тела → ask (команда не проходит)"))
res.append(ok(os.path.exists(TMP + "/test-801.json"), "9.2 маркер уведён в ТЕСТ-канал (изоляция проб)"))
# Канал 1 (пуш) мьютится ВНУТРИ notify по PRETOOL_NOPUSH — здесь он подменён стабом, поэтому
# проверяем то, что этот харнесс доказать МОЖЕТ: канал 2 уведён в тест-имя, а карточка, которая
# собиралась уйти, говорит про УДАЛЕНИЕ и называет путь. Утечку пушей ловит test_no_push_leak.
res.append(ok(PG.marker_name("801").startswith("test-"),
              "9.3 канал 2 уведён в тест-имя маркера (изоляция проб не тронута)"))
res.append(ok(bool(pushed1) and "_a.py" in pushed1[0] and "далени" in pushed1[0].lower(),
              "9.3б карточка называет удаление и путь"))
res.append(ok("_a.py" in out1, "9.4 путь удаляемого виден в решении гарда"))
out2, _p2, _e2 = run_main(cmd_of(LIVE_LOOP), task_id="802")
res.append(ok(out2.strip() == "", "9.5 уборка своего черновика в /tmp → хук молчит (defer, exit 0)"))
res.append(ok(not os.path.exists(TMP + "/test-802.json"), "9.6 зелёная уборка маркера не пишет"))
out3, _p3, ev3 = run_main(cmd_of("import os\nos.remove(os.environ['X'])\n"), task_id="803")
res.append(ok('"ask"' in out3, "9.7 невычислимая цель → ask"))
res.append(ok("card_skipped" in ev3, "9.8 невычислимая цель → card_skipped в журнале гарда"))

print("(10) КАРТОЧКА: объект — ПУТЬ, число — сколько файлов:")
_k, _h, blob10 = PG.classify(cmd_of("import os\nfor p in ('" + REPO + "/_a.py', '" + REPO
                                    + "/_b.py', '" + REPO + "/_c.py'):\n    os.remove(p)\n"), ROOT)
obj10, num10 = PG.card_min(_h, blob10)
res.append(ok("_a.py" in obj10, "10.1 объект называет путь: " + obj10))
res.append(ok(num10 == "файлов 3", "10.2 число = сколько файлов названо: " + num10))
card = PG._card(_h, blob10)
for label in ("Что: ", "Объект: ", "Число: ", "Откат: "):
    res.append(ok(label in card, "10.3 карточка несёт строку «" + label.strip() + "»"))
res.append(ok("далени" in card.split("Объект:")[0].lower(),
              "10.4 строка «Что» называет УДАЛЕНИЕ, а не безликое «не распознал операцию»"))

print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
