# -*- coding: utf-8 -*-
"""УДАЛЕНИЕ ФАЙЛОВ ВНЕ ВРЕМЕННЫХ КАТАЛОГОВ — КРАСНОЕ, А НЕ defer (03.08.2026).

ДЫРА, которая здесь закрыта. Доктрина (CLAUDE.md, редакция Б) относит «любое удаление данных и
файлов ВНЕ временных каталогов» к КРАСНОМУ высшего вида — тому, что без «да» владельца не идёт.
Гард же не-python команду не разбирал ВООБЩЕ (`classify`: `if not _is_python(scan): return green`)
→ вердикт defer → решали слои settings, а там на удаление своих черновиков стоит allow-паттерн.
Замер 168 ч (2026-07-27 04:31 → 08-03 04:31 UTC, транскрипты сессий): ЧЕТЫРЕ команды удаления
прошли молча, 38 файлов, все — в корне репозитория. Среди них `_envfix_probe.py`, файл
ОТСЛЕЖИВАЕМЫЙ git (добавлен коммитом fcff713) — в той же сессии его пришлось возвращать
`git checkout`. То есть дыра доставала не только до черновиков.

ЧТО ИМЕННО ЧИНИТСЯ: судим ПО ЦЕЛИ, а не по глаголу — та же доктрина и тот же текст правила, что
у демона (`_delete_is_red`/`_is_tmp_path`, orchestrator_daemon.py, 30.07.2026). Уборка СВОЕГО
черновика во временном каталоге (конкретный путь под /tmp, /var/tmp, /dev/shm) остаётся ЗЕЛЁНОЙ;
маска, сам корень, «..», любая цель вне временных каталогов и НЕИЗВЛЁКШАЯСЯ цель → красное.
Объект карточки — ПУТЬ того, что удаляют; объекта нет → карточки нет (общий гейт `card_gate`
не тронут), но решение ask остаётся, т.е. команда НЕ ПРОХОДИТ.

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ: чистые функции + main() в ЭТОМ процессе (stdin/stdout/_push подменены).
Ни одна строка отсюда не уходит в shell. Красные литералы собраны конкатенацией (образец —
test_pretool_hardblock): иначе гард краснеет на САМОМ файле теста.
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

TMP = tempfile.mkdtemp(prefix="pt_del_").replace(os.sep, "/")
atexit.register(shutil.rmtree, TMP, ignore_errors=True)

REPO = "/root/turbobaby-manager-bot"
PY = "venv/bin/python3"
SFO = "set_fleet_" + "oil"
CONF = "confirmed" + "=" + "True"
ENVF = "." + "env"
SPL = "spl" + "inter"
HIT = "delete_" + "file"

# ── ГОЛДЕНЫ ЖИВОГО ЗАМЕРА: команды ДОСЛОВНО из транскриптов окна 168 ч ────────────────────────
G1 = "rm -f " + REPO + "/_recon_vis.py"
G2 = ("rm -f " + REPO + "/_recon_task12.py " + REPO + "/_recon_tr12.py "
      + REPO + "/_recon_tr12b.py " + REPO + "/_recon_cls.py")
G3 = ("rm " + REPO + "/_artifact_dump.py " + REPO + "/_card_check_29.py "
      + REPO + "/_claspsplit_build.py " + REPO + "/_envfix_probe.py "
      + REPO + "/_guard_suite_29.py " + REPO + "/_live_check_c.py "
      + REPO + "/_live_check_visibility.py " + REPO + "/_live_hook_27.py "
      + REPO + "/_marker_probe.py " + REPO + "/_pg_old_card.py "
      + REPO + "/_probe_fail_line.py " + REPO + "/_probe_guard_ask.py "
      + REPO + "/_probe_two_tests.py " + REPO + "/_readback.py "
      + REPO + "/_readback_29.py " + REPO + "/_recon_cclog_check.py")
G4 = ("rm " + REPO + "/_recon_inprogress.py " + REPO + "/_recon_money_01.py "
      + REPO + "/_recon_money_02.py " + REPO + "/_recon_money_03.py "
      + REPO + "/_recon_money_04.py " + REPO + "/_recon_money_05.py "
      + REPO + "/_recon_money_06.py " + REPO + "/_recon_money_07.py "
      + REPO + "/_recon_money_08.py " + REPO + "/_recon_opus5.py "
      + REPO + "/_recon_queue.py " + REPO + "/_recon_readback.py "
      + REPO + "/_recon_tail_cmds.py " + REPO + "/_recon_task27_classify.py "
      + REPO + "/_recon_task27_tools.py " + REPO + "/_recon_vrezka.py "
      + REPO + "/_verify_reset.py")
# Пятая команда окна — уборка МАРКЕРОВ гарда, цели конкретные и временные → зелёная (см. §2).
G5 = "rm /tmp/cc_guard_block/12.json /tmp/cc_guard_block/27.json /tmp/cc_guard_block/399.json"


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def fixture(name, body):
    path = TMP + "/" + name
    with open(path, "w", encoding="utf-8") as f:
        f.write("# фикстура\n" + body + "\n")
    return path


res = []


def kind_of(cmd):
    return PG.classify(cmd, ROOT)[0]


def hit_of(cmd):
    return PG.classify(cmd, ROOT)[1]


def obj_of(cmd):
    kind, hit, blob = PG.classify(cmd, ROOT)
    return PG.card_min(hit, blob)[0]


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


print("(1) ГОЛДЕНЫ ЗАМЕРА 168 ч — четыре команды, прошедшие молча, больше не проходят:")
for label, cmd, want_obj, want_cnt in (
        ("одиночный файл репо", G1, "_recon_vis.py", 1),
        ("четыре файла разом", G2, "_recon_task12.py", 4),
        ("16 файлов, среди них отслеживаемый git", G3, "_artifact_dump.py", 16),
        ("17 файлов разведки", G4, "_recon_inprogress.py", 17)):
    kind, hit, blob = PG.classify(cmd, ROOT)
    res.append(ok(kind == "red" and hit == HIT, "%s: kind=%s hit=%s" % (label, kind, hit)))
    d = PG.decision(kind, hit, "x")
    res.append(ok(d and d["hookSpecificOutput"]["permissionDecision"] == "ask",
                  "%s: решение хука = ask (без «да» не исполнится)" % label))
    o, n = PG.card_min(hit, blob)
    res.append(ok(want_obj in o, "%s: ОБЪЕКТ — путь удаляемого (%r)" % (label, o[:70])))
    # ЧИСЛО — ФАКТ, а не оценка: общий разбор режет всё после первого «.py» (argv скрипта —
    # данные), и на этих же голденах карточка сказала бы «файлов 1» вместо 4/16/17.
    res.append(ok(n == "файлов %d" % want_cnt,
                  "%s: ЧИСЛО = столько, сколько удаляется (%r)" % (label, n)))
    res.append(ok(PG.card_gate(hit, o, n), "%s: карточка рождается (объект есть)" % label))

print("(2) УБОРКА СВОЕГО ЧЕРНОВИКА ВО ВРЕМЕННОМ КАТАЛОГЕ ОСТАЁТСЯ ЗЕЛЁНОЙ (правило 30.07):")
for label, cmd in (
        ("голден замера: маркеры гарда", G5),
        ("конкретный файл в /tmp", "rm -f /tmp/tb_scratch/probe.json"),
        ("каталог прогона в /tmp", "rm -rf /tmp/tb_scratch/run59"),
        ("/var/tmp", "rm /var/tmp/dump_0803.txt"),
        ("/dev/shm", "rm -f /dev/shm/lock_0803"),
        ("rmdir временного каталога", "rmdir /tmp/tb_scratch/run59"),
        ("unlink временного файла", "unlink /tmp/tb_scratch/x.json"),
        ("несколько временных целей разом", "rm -f /tmp/a.json /var/tmp/b.json /dev/shm/c"),
        ("уборка в цепочке после чтения", "cat /tmp/tb_scratch/x.log ; rm /tmp/tb_scratch/x.log"),
        ("find -delete в пределах временного каталога",
         "find /tmp/tb_scratch -name '*.pyc' -delete")):
    res.append(ok(kind_of(cmd) == "green", "%s → green (defer, как было)" % label))

print("(3) ДОКТРИНА ЦЕЛИ — та же, что у демона (маска, корень, «..» временем не считаются):")
for label, cmd in (("маска /tmp/*", "rm -rf /tmp/*"),
                   ("сам корень /tmp", "rm -rf /tmp"),
                   ("корень со слэшем", "rm -rf /tmp/"),
                   ("выход вверх из /tmp", "rm -rf /tmp/../root/x"),
                   ("вопросительная маска", "rm -f /tmp/tb_scratch/?.json"),
                   ("файл репо", "rm " + REPO + "/docs/artifacts/2026-07-24-entity-port-todo.md"),
                   ("относительный путь", "rm docs/knowledge_base.md"),
                   ("каталог тестов", "rm -rf " + REPO + "/tests"),
                   ("чужой каталог", "rm -rf /root/turbobaby-bridge-gs/Bridge.js")):
    res.append(ok(kind_of(cmd) == "red" and hit_of(cmd) == HIT, "%s → красное" % label))

print("(4) FAIL-CLOSED: цель не определяется — команда НЕ ПРОХОДИТ (карточки при этом нет):")
for label, cmd in (("цели приходят из stdin", "find " + REPO + " -name '_*.py' | xargs rm -f"),
                   ("цель в подстановке", "rm -f $(cat /tmp/list.txt)"),
                   ("глагол без аргументов", "rm -rf"),
                   ("переменная вместо пути", "rm -f $TARGET")):
    kind, hit, blob = PG.classify(cmd, ROOT)
    res.append(ok(kind == "red" and hit == HIT, "%s → красное (fail-closed)" % label))
    o, n = PG.card_min(hit, blob)
    res.append(ok(not PG.card_gate(hit, o, n),
                  "%s: объекта нет → карточки нет, но ask остаётся" % label))

print("(5) ДАННЫЕ ≠ КОМАНДА: слово об удалении карточку НЕ рождает:")
for label, cmd in (
        ("шаблон grep", "grep -n \"rm -rf /root/x\" " + REPO + "/CLAUDE.md"),
        ("шаблон rg", "rg -n 'rm -f /root/turbobaby' " + REPO + "/docs"),
        ("текст своего коммита",
         "git commit -m \"убрал rm -rf /root/x из скрипта уборки\""),
        ("эхо строки", "echo rm -rf /root/x"),
        ("имя файла похоже на глагол", "cat " + REPO + "/rm.txt"),
        ("чтение журнала", "tail -50 " + REPO + "/splinter.log")):
    res.append(ok(kind_of(cmd) == "green", "%s → green" % label))

print("(6) ФОРМЫ ЗАПУСКА: обёртки, вложенный шелл, цепочки, find, git:")
for label, cmd, want in (
        ("sudo", "sudo rm -f " + REPO + "/bot.py", "red"),
        ("вложенный шелл", "sh -c \"rm -f " + REPO + "/bot.py\"", "red"),
        ("цепочка через &&", "git status && rm -f " + REPO + "/bot.py", "red"),
        ("цепочка через ;", "echo start ; rm -f " + REPO + "/bot.py", "red"),
        ("timeout-обёртка", "timeout 5 rm -rf " + REPO + "/docs", "red"),
        ("find -delete вне /tmp", "find " + REPO + " -name '_*.py' -delete", "red"),
        ("find -exec rm", "find " + REPO + " -name '*.bak' -exec rm {} ;", "red"),
        ("find только читает", "find " + REPO + " -name '*.py' -newer /tmp/x", "green"),
        ("find -exec grep", "find " + REPO + " -name '*.py' -exec grep -l DONE {} ;", "green"),
        ("shred файла репо", "shred -u " + REPO + "/memory.db", "red"),
        ("git rm", "git rm docs/faq.md", "red"),
        ("git rm --cached", "git rm --cached " + REPO + "/_envfix_probe.py", "red")):
    res.append(ok(kind_of(cmd) == want, "%s → %s" % (label, want)))

print("(7) СУЩЕСТВУЮЩИЕ КРАСНЫЕ И БЛОКИ НЕ ОСЛАБЛЕНЫ:")
FX_LIVE = fixture("fx_fleet_live.py",
                  "bridge." + SFO + "(number='6789', oil_km=27000, " + CONF + ")")
FX_TMPCLEAN = fixture("fx_tmp_clean.py", "import os\nos.remove('/tmp/tb_scratch/x.json')")
checks = [
    ("файл секретов остаётся жёстким блоком", "cat " + REPO + "/" + ENVF, "block"),
    ("секреты в цепочке с удалением",
     "rm -f /tmp/x ; cat " + REPO + "/" + ENVF, "block"),
    ("стоп боевого процесса остаётся жёстким", "p" + "kill -9 " + SPL, "block"),
    ("запись в Лист1 не подменяется удалением файла",
     PY + " " + FX_LIVE + " && rm -f " + REPO + "/_tmpX.py", "red"),
    # sqlite3-CLI держит ask-слой settings, а гард по нему деферит — так было и так остаётся:
    # новый класс не должен ни красить, ни отбеливать чужие классы.
    ("sqlite3-CLI по-прежнему defer гарда (красное держит settings)",
     "sqlite3 /root/other.db \"UPDATE t SET a=1\"", "green"),
]
for label, cmd, want in checks:
    res.append(ok(kind_of(cmd) == want, "%s → %s" % (label, want)))
res.append(ok(hit_of(PY + " " + FX_LIVE + " && rm -f " + REPO + "/_tmpX.py") == SFO,
              "красное живой таблицы ИМЕНУЕТСЯ верно (hit=%s, а не удаление)"
              % hit_of(PY + " " + FX_LIVE + " && rm -f " + REPO + "/_tmpX.py")))
res.append(ok(kind_of(PY + " " + FX_TMPCLEAN) == "green",
              "уборка своего черновика ИЗ python-кода — по-прежнему green"))

print("(8) main() ЦЕЛИКОМ: удаление вне /tmp = ask + карточка; уборка в /tmp = ноль вывода:")
out, pushed, events = run_main(G1, task_id="777")
res.append(ok('"permissionDecision": "ask"' in out or '"permissionDecision":"ask"' in out,
              "решение хука на удаление файла репо — ask"))
res.append(ok("_recon_vis.py" in out, "в тексте решения назван ПУТЬ удаляемого"))
res.append(ok(os.path.exists(TMP + "/test-777.json"),
              "маркер конверта записан (владелец увидит карточку в 328/1160)"))
out2, pushed2, _ev2 = run_main(G5, task_id="778")
res.append(ok(out2.strip() == "", "уборка маркеров в /tmp: хук молчит (defer, exit 0)"))
res.append(ok(not os.path.exists(TMP + "/test-778.json"), "уборка в /tmp маркера не пишет"))
out3, _p3, ev3 = run_main("rm -rf", task_id="779")
res.append(ok('"ask"' in out3, "цель не определена → ask (не проходит)"))
res.append(ok("card_skipped" in ev3, "цель не определена → строка card_skipped в журнале гарда"))

print("(9) ОБЩИЙ ОБЪЕКТНЫЙ ГЕЙТ НЕ ТРОНУТ (то же правило, что у прочих классов):")
res.append(ok(PG.card_gate(HIT, "") is False, "нет объекта → карточки нет"))
res.append(ok(PG.card_gate(HIT, "путь " + REPO + "/bot.py") is True, "объект есть → карточка"))
card = PG._card(HIT, "cmd\ndel_target=" + REPO + "/bot.py\ndel_count=1")
for label in ("Что: ", "Объект: ", "Число: ", "Откат: "):
    res.append(ok(label in card, "карточка удаления несёт строку «" + label.strip() + "»"))
res.append(ok("далени" in card.split("Объект:")[0].lower(),
              "строка «Что» называет УДАЛЕНИЕ, а не безликое «не распознал операцию»"))
res.append(ok("bot.py" in card, "в карточке виден путь удаляемого"))
res.append(ok("`" not in card, "в карточке нет обратных кавычек (объект сверки берётся из тела)"))

print("(10) ЧЕСТНЫЙ ПРЕДЕЛ (документирован, не лечится здесь): имя удаляемого файла с «_test»")
print("     читается как признак ПРОБЫ — пуш владельцу гасится, но решение ask остаётся:")
res.append(ok(PG.is_probe("rm -f " + REPO + "/_probe_two_tests.py"),
              "команда с «_test» в имени цели опознана как проба (прежняя эвристика)"))
kind_p, hit_p, _b = PG.classify("rm -f " + REPO + "/_probe_two_tests.py", ROOT)
res.append(ok(kind_p == "red" and hit_p == HIT,
              "но КЛАССИФИКАЦИЯ не ослаблена: удаление остаётся красным"))

print("\nИТОГ: %d/%d" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
