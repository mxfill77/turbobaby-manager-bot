"""УДАЛЕНИЕ СУДИТСЯ ПО ЦЕЛИ, А НЕ ПО ГЛАГОЛУ (класс 30.07.2026, остаток разбора гарда).

Было: слой 2 демона (_HEADLESS_IMPOSSIBLE_RE) держал `os.remove|os.unlink|shutil.rmtree|rm -rf`
как заведомо headless-невозможное красное — где угодно в тексте. Под это попадала уборка СВОЕГО
черновика во временном каталоге: файл, который задача сама создала, сама и убирает — владельцу
решать нечего, а стоило это карточки, «да» и терминальной карты «сделай руками» (владельцу
предлагалось пойти удалить файл в /tmp).

Тот же класс, что сужение 25.07 («имена операций, а не темы») и «данные ≠ команда» в гарде.
Теперь зелёным считается РОВНО один случай: цель названа ЛИТЕРАЛОМ, лежит под корнем временного
каталога (/tmp, /var/tmp, /dev/shm) и является конкретным путём. Всё остальное — как было.
Проверяем ОБА направления: и что шум ушёл, и что настоящее удаление краснеет.
Сети/Telegram/claude нет — только чистые функции модуля.
"""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"          # изоляция от боевого .env (env демона наследуется в headless)
os.environ.setdefault("ORCH_TEST_MODE", "1")

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD

# Имена боевых операций — конкатенацией (правило репо: в текстах их не цитируем дословно).
FLEET_OIL = "set_fleet_" + "oil"

print("(1) уборка СВОЕГО черновика во временном каталоге → НЕ красное (карточки нет):")
for label, text in [
    ("os.remove литералом", "op=other | os.remove('/tmp/tb_scratch/probe_59.py') · убрать свой черновик"),
    ("двойные кавычки", 'op=other | os.remove("/tmp/tb_scratch/dump.json")'),
    ("os.unlink", "op=other | os.unlink('/tmp/claude-abc/scratchpad/fx.py')"),
    ("shutil.rmtree каталога", "op=other | shutil.rmtree('/tmp/tb_scratch')"),
    ("rm -rf по временному пути", "op=other | rm -rf /tmp/tb_scratch/run59"),
    ("/var/tmp", "op=other | os.remove('/var/tmp/report59.txt')"),
    ("/dev/shm", "op=other | os.remove('/dev/shm/probe.bin')"),
    ("несколько своих файлов", "op=other | os.remove('/tmp/a/x.py'); os.remove('/tmp/a/y.py')"),
]:
    res.append(ok(not OD._is_headless_impossible(text), label + " → зелёное"))

print("(2) НАСТОЯЩЕЕ удаление краснеет как раньше (fail-safe во все стороны):")
for label, text in [
    ("файл вне временного каталога", "op=other | os.remove('/root/live.db') · удаление файла"),
    ("файл репо", "op=other | os.remove('/root/turbobaby-manager-bot/memory.db')"),
    ("относительный путь", "op=other | os.remove('memory.db')"),
    ("цель — переменная (не литерал)", "op=other | os.remove(path) · уборка"),
    ("цель через os.path.join", "op=other | os.remove(os.path.join(d, 'x'))"),
    ("маска во временном каталоге", "op=other | rm -rf /tmp/*"),
    ("сам корень /tmp", "op=other | rm -rf /tmp"),
    ("выход из временного каталога через ..", "op=other | os.remove('/tmp/../root/live.db')"),
    ("похожий, но иной корень", "op=other | os.remove('/tmpfoo/x.py')"),
    ("rmtree корня временного каталога", "op=other | shutil.rmtree('/tmp/')"),
    ("смесь: свой черновик + файл репо", "op=other | os.remove('/tmp/a/x.py') и os.remove('/root/x.db')"),
    ("путь только в КОММЕНТАРИИ после глагола", "op=other | os.remove(p)  # см. /tmp/a/x.py"),
]:
    res.append(ok(OD._is_headless_impossible(text), label + " → красное"))

print("(3) прочие ветки слоя 2 не тронуты (список без удаления):")
for label, text in [
    ("clasp/redeploy", "op=other | clasp redeploy Bridge · прод · ping"),
    ("живая таблица", "op=other | записать бронь в Лист1 Байки · confirmed=true"),
    ("деньги", "op=other | add_transaction(-500) в кассу · Money Cashflow"),
    ("CLI-БД", "op=other | sqlite3 memory.db UPDATE trust"),
    ("событие календаря", "op=other | delete_event(id=7) — событие календаря брони"),
    ("парк", "op=other | " + FLEET_OIL + "(bike=12) · живой парк"),
    ("редактор Apps Script", "op=other | запустить setupBrain на script.google.com"),
]:
    res.append(ok(OD._is_headless_impossible(text), label + " → красное (как было)"))
res.append(ok(not OD._is_headless_impossible("op=other | покажи отчёт по деньгам за июль"),
              "тема без имени операции → не красное (сужение 25.07 живо)"))
res.append(ok(not OD._is_headless_impossible(""), "пустой текст → не красное"))

print("(4) _is_tmp_path — границы:")
for p, want in [("/tmp/tb_scratch/x.py", True), ("/tmp/x", True), ("/var/tmp/x", True),
                ("/dev/shm/x", True), ("'/tmp/x'", True), ("/tmp/", False), ("/tmp", False),
                ("/tmp/*", False), ("/tmp/a/?.py", False), ("/tmp/../etc/x", False),
                ("", False), ("x.py", False), ("/root/x", False), ("/tmpfoo/x", False)]:
    res.append(ok(OD._is_tmp_path(p) is want, "%-22r → %s" % (p, want)))

print("(5) план декомпозера: шаг про уборку своего черновика больше не помечается красным:")
steps_green = ["прочитать лог демона", "убрать свой черновик: os.remove('/tmp/tb_scratch/x.py')"]
steps_red = ["правка кода", "удалить рабочую БД: os.remove('/root/turbobaby-manager-bot/wa_queue.db')"]
res.append(ok(OD._dec_red_note(steps_green) == "", "шаг с уборкой /tmp → пометки «🔴 красные шаги» нет"))
res.append(ok("🔴 красные шаги: 2" in OD._dec_red_note(steps_red), "шаг с удалением БД → помечен красным"))

print("(6) преамбула исполнителя: уборка своего черновика объявлена зелёной, красное на месте:")
P = OD.APPROVAL_PREAMBLE
res.append(ok("УБОРКА СВОЕГО ЧЕРНОВИКА" in P and "карточку НЕ объявлять" in P,
              "явное разрешение убирать свой временный файл"))
res.append(ok("/tmp" in P and "ЛИТЕРАЛОМ" in P, "названы каталоги и форма пути (литерал)"))
res.append(ok("удаление событий" in P and "op=other" in P, "настоящее красное в преамбуле не ослаблено"))
res.append(ok("ВНЕ временных каталогов" in P, "формулировка «любое удаление» сужена по цели"))
res.append(ok("прежнее красное с карточкой" in P, "маска//tmp-корень/вне tmp — оговорены явно"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
