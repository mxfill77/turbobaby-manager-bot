# -*- coding: utf-8 -*-
"""SQL-ЗАПИСЬ СУДИТСЯ ПО ЦЕЛИ ОТКРЫТИЯ, А НЕ ПО СЛОВУ В ТЕКСТЕ (класс «корень А», 02.08.2026).

Остаток серверной полосы, зеркало ПК-фикса `abd2917` («гард судит SQL-запись по оператору, имя
базы в тексте решения больше не принимает»). На ПК послабление сняли ЦЕЛИКОМ — там у имени
`memory.db` нет живого референта. На сервере референт ЕСТЬ: своя БД бота, и доктрина 02.07
«своя таблица через код = зелёное» держится именно на ней. Поэтому здесь снимается не
послабление, а СПОСОБ РЕШЕНИЯ.

БЫЛО (pretool_guard._analyze, две строки — по команде и по телу скрипта):

    if _SQLITE_WRITE.search(blob) and ".db" in blob and "memory.db" not in blob:
        return "red", "sqlite", blob

Читался текст, который гарду никто не обещал: команда, сочинённая моделью, и ИСХОДНИК скрипта
вместе с комментариями и докстрингами. Достаточно было, чтобы слово `memory.db` встретилось в
тексте ХОТЬ РАЗ — и красное снималось со ВСЕХ SQL-записей этого скрипта, включая запись в чужую
БД. Комментарий «мы не трогаем memory.db» отбеливал запись в очередь, в клиентов, куда угодно.

СТАЛО: решает РАЗОБРАННАЯ ЦЕЛЬ ОТКРЫТИЯ — литерал в `connect(...)` либо файловый аргумент
`sqlite3 <файл>.db`. Своя БД у цели → доктрина 02.07 цела; чужая → красное. Цель не разобралась
(открытия в тексте нет) → fail-closed: судим по всем `.db`-именам, как и раньше, но упоминание
своей БД чужую больше не отбеливает.

Тот же класс и тот же принцип, что `tests/test_delete_scope.py` («судим по ЦЕЛИ, а не по глаголу»).

ТЕСТ НИЧЕГО НЕ ИСПОЛНЯЕТ: только импорт модуля и чистая `classify()`. Ни одна строка не уходит
в shell, ни один процесс не трогается, сети нет.
"""
import os
import shutil
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["PRETOOL_NOPUSH"] = "1"      # страховка: ни одна карточка не уйдёт в Telegram

# pretool_guard тянет fcntl (POSIX-локи дедупа); классификация от него не зависит — см. hardblock.
if "fcntl" not in sys.modules:
    try:
        import fcntl  # noqa: F401
    except ImportError:
        _fake = types.ModuleType("fcntl")
        _fake.flock = lambda *a, **k: None
        _fake.LOCK_EX = 2
        sys.modules["fcntl"] = _fake

import pretool_guard as PG


def ok(c, label):
    print(("  PASS " if c else "  FAIL ") + label)
    return bool(c)


def cls(cmd):
    return PG.classify(cmd, ROOT)


def is_red_sqlite(cmd):
    kind, hit, _ = cls(cmd)
    return kind == "red" and hit == "sqlite"


def not_red(cmd):
    """Красного НЕТ (defer/зелёное) — доктрина 02.07 «своя БД через код» цела."""
    kind, _hit, _ = cls(cmd)
    return kind != "red"


res = []
OWN = "memory.db"
FOREIGN = "/root/x/tasks.db"

# ── (1) КЛАСС: упоминание своей БД больше НЕ отбеливает запись в чужую ────────────────────────
print("(1) слово «своя БД» в тексте не снимает красное с записи в ЧУЖУЮ БД:")
WHITEWASH = [
    ("комментарий рядом с открытием",
     "python3 - <<PYEOF\nimport sqlite3\n# " + OWN + " не трогаем, работаем с очередью\n"
     "con = sqlite3.connect('" + FOREIGN + "')\ncon.execute('UPDATE tasks SET s=1')\nPYEOF"),
    ("докстринг скрипта",
     "python3 - <<PYEOF\n'''чистка очереди; " + OWN + " не затрагивается'''\nimport sqlite3\n"
     "sqlite3.connect('" + FOREIGN + "').execute('DELETE FROM tasks')\nPYEOF"),
    ("имя своей БД в соседней строке",
     "python3 -c \"import sqlite3; bak='" + OWN + "'; "
     "sqlite3.connect('" + FOREIGN + "').execute('INSERT INTO tasks VALUES (1)')\""),
    ("печать имени своей БД в отчёте",
     "python3 - <<PYEOF\nimport sqlite3\nprint('бэкап ' + '" + OWN + "' + ' снят')\n"
     "sqlite3.connect('" + FOREIGN + "').execute('DROP TABLE tasks')\nPYEOF"),
]
for label, cmd in WHITEWASH:
    res.append(ok(is_red_sqlite(cmd), label + " → красное (sqlite)"))

# Открытия в тексте нет вовсе (цель не разобралась) → fail-closed по именам, отбеливание не работает.
res.append(ok(is_red_sqlite("python3 - <<PYEOF\n# правим " + FOREIGN + ", резерв в " + OWN + "\n"
                            "run('UPDATE tasks SET s=1')\nPYEOF"),
              "цель открытия не разобралась + чужое имя рядом со своим → fail-closed красное"))

# ── (2) ДОКТРИНА 02.07 ЦЕЛА: своя БД бота через python-код красной не становится ──────────────
print("(2) своя БД через код — по-прежнему НЕ красное (доктрина 02.07 не тронута):")
res.append(ok(not_red("python3 - <<PYEOF\nimport sqlite3\ncon = sqlite3.connect('" + OWN + "')\n"
                      "con.execute('UPDATE tasks SET s=1')\nPYEOF"),
              "connect('" + OWN + "') + UPDATE → красного нет"))
res.append(ok(not_red("python3 - <<PYEOF\nimport sqlite3\n"
                      "con = sqlite3.connect('" + ROOT + "/" + OWN + "')\n"
                      "con.execute('DELETE FROM trust WHERE id=1')\nPYEOF"),
              "абсолютный путь к своей БД → красного нет"))
# Своя БД открыта, чужое имя лишь УПОМЯНУТО в комментарии → цель разобрана, ложного красного нет.
res.append(ok(not_red("python3 - <<PYEOF\nimport sqlite3\n# не путать с " + FOREIGN + "\n"
                      "con = sqlite3.connect('" + OWN + "')\ncon.execute('UPDATE trust SET v=1')\nPYEOF"),
              "чужое имя в комментарии при открытии своей БД → ложного красного НЕТ"))

# ── (3) ПРЕЖНЕЕ КРАСНОЕ НА МЕСТЕ (голдены hardblock не сдвинуты) ──────────────────────────────
print("(3) запись в чужую БД без всяких упоминаний своей — красное, как и было:")
res.append(ok(is_red_sqlite("python3 - <<PYEOF\nimport sqlite3\ncon = sqlite3.connect('" + FOREIGN + "')\n"
                            "con.execute('UPDATE tasks SET s=1')\nPYEOF"),
              "голден hardblock (13б): чужая .db + UPDATE → красное"))
res.append(ok(not_red("python3 - <<PYEOF\nimport sqlite3\ncon = sqlite3.connect('" + FOREIGN + "')\n"
                      "print(con.execute('SELECT 1').fetchone())\nPYEOF"),
              "ЧТЕНИЕ чужой БД (SELECT) красным не делается"))

# ── (4) ТЕЛО СКРИПТА С ДИСКА: тот же класс на второй строке _analyze ──────────────────────────
print("(4) то же для ТЕЛА скрипта, прочитанного с диска (вторая строка _analyze):")
tmp = tempfile.mkdtemp(prefix="sqltgt_").replace(os.sep, "/")
try:
    ww = tmp + "/_fx_whitewash.py"
    with open(ww, "w", encoding="utf-8") as f:
        f.write("# фикстура: " + OWN + " не трогаем\nimport sqlite3\n"
                "sqlite3.connect('" + FOREIGN + "').execute('UPDATE tasks SET s=1')\n")
    res.append(ok(is_red_sqlite("python3 " + ww),
                  "тело скрипта: своё имя в комментарии + запись в чужую БД → красное"))

    own = tmp + "/_fx_own.py"
    with open(own, "w", encoding="utf-8") as f:
        f.write("import sqlite3\nsqlite3.connect('" + OWN + "').execute('UPDATE trust SET v=1')\n")
    res.append(ok(not_red("python3 " + own), "тело скрипта: запись в СВОЮ БД → красного нет"))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ── (5) ЕДИНИЦА: разбор цели ──────────────────────────────────────────────────────────────────
print("(5) единица — _sql_write_is_foreign судит по цели открытия:")
UNIT = [
    ("connect чужой при упоминании своей",
     "# " + OWN + "\nsqlite3.connect('" + FOREIGN + "')", True),
    ("connect своей при упоминании чужой",
     "# " + FOREIGN + "\nsqlite3.connect('" + OWN + "')", False),
    ("connect своей по абсолютному пути", "connect('/root/turbobaby-manager-bot/" + OWN + "')", False),
    ("CLI своей БД", "sqlite3 " + OWN + " 'UPDATE trust SET v=1'", False),
    ("CLI чужой БД", "sqlite3 " + FOREIGN + " 'UPDATE tasks SET s=1'", True),
    ("открытия нет, имён нет", "run('UPDATE tasks SET s=1')", False),
    ("открытия нет, чужое имя есть", "правим " + FOREIGN, True),
    ("открытия нет, только своё имя", "правим " + OWN, False),
    ("две цели: своя и чужая", "connect('" + OWN + "')\nconnect('" + FOREIGN + "')", True),
]
for label, text, want in UNIT:
    res.append(ok(PG._sql_write_is_foreign(text) is want, "%-42s → %s" % (label, want)))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else "ЕСТЬ FAIL (%d/%d)" % (sum(res), len(res)))
sys.exit(0 if all(res) else 1)
