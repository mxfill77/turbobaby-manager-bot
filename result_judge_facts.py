"""РУКИ СУДЬИ АДРЕСА — читают мир по названному адресу и НИЧЕГО НЕ РЕШАЮТ (16.08.2026).

Разделение взято у прибора О3 дословно: `expectations.py` судит — `expectations_run.py` читает;
здесь `result_judge.py` судит — этот модуль читает. Смысл разделения в том, что решение остаётся
доказуемо безруким (страж `RESULT_JUDGE_PURE`), а всё, что умеет трогать мир, собрано в одном
месте и умеет трогать его ТОЛЬКО НА ЧТЕНИЕ:

  • git — белый список из ОДНОЙ подкоманды `log`, аргументы литеральные, `shell` нигде;
  • диск — `os.stat`, ни одного `open` на запись;
  • база — открывается URI-режимом `mode=ro`, условие уезжает ПАРАМЕТРАМИ (адрес приходит из
    живого текста очереди, и пускать его в текст запроса нельзя);
  • systemd — `systemctl show`, свойства только читающие;
  • мозг — `read_doc` через мост; импорт моста ЛЕНИВЫЙ, внутри функции: модуль обязан
    импортироваться и на машине, где моста нет вовсе.

НИКЕМ НЕ ЗОВОМ, как и сам судья: ни одна живая точка входа его не импортирует (доказано
замыканием импортов в `tests/test_result_judge.py`). Читатели сегодня двое — тест и замер захода.

ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО: «сейчас», окна и порога. Руки приносят величины, названные адресом
(старт юнита, время коммита), а сравнивает их судья — и только между собой. Ни одна функция
модуля не принимает время и не спрашивает его у системы, кроме перевода метки systemd в секунды.

«НЕ ПРОЧИТАНО» — ОТДЕЛЬНЫЙ ОТВЕТ, А НЕ ПУСТОЙ. Каждая функция возвращает `read`: False со
СЛОВАМИ причины. Пустой список вместо отказа читался бы как честный ноль — тот самый класс
«нуль по неразбору», против которого стоят `scan_result` и касса.
"""
import calendar
import os
import sqlite3
import subprocess

import result_judge

REPO = os.path.dirname(os.path.abspath(__file__))

GIT_READ = frozenset(("log",))      # белый список ЧИТАЮЩИХ подкоманд, сверяется на каждом вызове
GIT_TIMEOUT = 30
SYSTEMCTL_TIMEOUT = 15
# Свойства systemd только читающие; `show` ничего не меняет ни при каком наборе свойств.
UNIT_PROPS = ("ActiveState", "ExecMainStartTimestamp")
DB_TIMEOUT = 10


def _git(args):
    """Читающий git → stdout | None. Подкоманда вне белого списка не исполняется ВООБЩЕ."""
    if not args or args[0] not in GIT_READ:
        return None
    try:
        p = subprocess.run(["git"] + [str(a) for a in args], cwd=REPO,
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def commits_fact(ref="origin/main"):
    """Все коммиты ветки → {"read","shas":[полные],"at":{хеш: секунды}}.

    ОКНА ЗДЕСЬ НЕТ НАМЕРЕННО: вопрос судьи — «есть ли этот хеш в origin/main», а не «есть ли он
    за последние N часов». Ограничь список временем — и сдвиг окна начал бы менять вердикты,
    то есть судья стал бы судить совпадение во времени (замок C захода)."""
    out = _git(["log", str(ref), "--format=%H %ct"])
    if out is None:
        return {"read": False, "shas": [], "at": {}, "why": "git не прочитан"}
    shas, at = [], {}
    for line in out.splitlines():
        sha, _, ts = line.strip().partition(" ")
        if not sha:
            continue
        shas.append(sha.lower())
        try:
            at[sha.lower()] = float(ts)
        except ValueError:
            continue
    return {"read": True, "shas": shas, "at": at}


def file_fact(path):
    """Файл на диске → {"read","exists","size"}. Пути судья не выдумывает: берётся как назван."""
    p = path if os.path.isabs(path) else os.path.join(REPO, path)
    try:
        st = os.stat(p)
    except FileNotFoundError:
        return {"read": True, "exists": False, "size": 0}
    except OSError as e:
        return {"read": False, "exists": False, "size": 0, "why": "stat не удался (%s)" % e.errno}
    return {"read": True, "exists": True, "size": int(st.st_size)}


def row_fact(db, table, conds):
    """Строка в базе → {"read","count"}. База ТОЛЬКО НА ЧТЕНИЕ: URI `mode=ro`.

    Значения условия уезжают параметрами; имя таблицы параметром не бывает, поэтому оно сверяется
    со списком таблиц базы, а в запрос попадает в кавычках."""
    p = db if os.path.isabs(db) else os.path.join(REPO, db)
    if not os.path.exists(p):
        return {"read": False, "count": 0, "why": "базы «%s» нет" % db}
    con = None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=DB_TIMEOUT)
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if table not in names:
            return {"read": False, "count": 0,
                    "why": "таблицы «%s» в базе нет — спрошено не то место" % table}
        where = " AND ".join('"%s" = ?' % c for c, _ in conds)
        cur = con.execute('SELECT COUNT(*) FROM "%s" WHERE %s' % (table, where),
                          [v for _, v in conds])
        return {"read": True, "count": int(cur.fetchone()[0])}
    except sqlite3.Error as e:
        return {"read": False, "count": 0, "why": "база не отвечает (%s)" % type(e).__name__}
    finally:
        if con is not None:
            con.close()


def unit_fact(unit):
    """Юнит systemd → {"read","started": секунды | None}. `show` — команда чтения."""
    if not unit or any(ch.isspace() for ch in unit):
        return {"read": False, "started": None, "why": "имя юнита не похоже на имя"}
    # Голова argv — ЛИТЕРАЛ, и это не стиль: она сверяется разбором в тесте. Команда, собранная
    # из переменной целиком, читалась бы как «что угодно» — то же правило исполняющей позиции,
    # которым живёт гард.
    props = [x for prop in UNIT_PROPS for x in ("--property", prop)]
    try:
        p = subprocess.run(["systemctl", "show", unit] + props,
                           capture_output=True, text=True, timeout=SYSTEMCTL_TIMEOUT)
    except Exception:
        return {"read": False, "started": None, "why": "systemctl не отвечает"}
    if p.returncode != 0:
        return {"read": False, "started": None, "why": "systemctl вернул %d" % p.returncode}
    vals = dict(ln.split("=", 1) for ln in p.stdout.splitlines() if "=" in ln)
    stamp = (vals.get("ExecMainStartTimestamp") or "").strip()
    started = _stamp_secs(stamp)
    if started is None:
        return {"read": False, "started": None,
                "why": "юнит не запущен либо метка старта пуста (ActiveState=%s)"
                       % (vals.get("ActiveState") or "?")}
    return {"read": True, "started": started, "active": vals.get("ActiveState")}


def _stamp_secs(stamp):
    """«Mon 2026-08-10 21:39:15 UTC» → секунды эпохи. Не UTC либо мусор → None (не догадываемся).

    Машина живёт в UTC (это же допущение стоит у соседних приборов); метка в другой зоне
    честнее остаться непрочитанной, чем быть сдвинутой на догадку."""
    parts = str(stamp or "").split()
    if len(parts) < 4 or parts[3].upper() not in ("UTC", "GMT"):
        return None
    try:
        y, mo, d = (int(x) for x in parts[1].split("-"))
        h, mi, s = (int(x) for x in parts[2].split(":"))
        return float(calendar.timegm((y, mo, d, h, mi, s, 0, 0, 0)))
    except (ValueError, IndexError):
        return None


def brain_fact(key, before=None):
    """Узел мозга → {"read","text","len","len_before"}. Мост импортируется ЛЕНИВО.

    `before` — длина узла ДО шага; сегодня её не записывает никто, поэтому по умолчанию None, и
    судья на таком факте отвечает НЕИЗВЕСТНО, а не зелёным. Это не дыра, а честное состояние
    записей: пока длина при создании шага не сохраняется, «содержит» от «уже содержало»
    неотличимо."""
    try:
        import bridge_client
        reply = bridge_client.BridgeClient().read_doc(name=key)
    except Exception as e:                       # noqa: BLE001 — мост может отсутствовать вовсе
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": "мост не отвечает (%s)" % type(e).__name__}
    if not isinstance(reply, dict) or not reply.get("ok"):
        why = (reply or {}).get("error") if isinstance(reply, dict) else "ответ не разобран"
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": "узел не прочитан (%s)" % (why or "без причины")}
    text = str(reply.get("text") or reply.get("content") or "")
    return {"read": True, "text": text, "len": len(text), "len_before": before}


def gather(refs, before=None, brain=True):
    """Список адресов → факты РОВНО под них (каждый источник спрашивается один раз).

    `brain=False` — не ходить к мосту вовсе: тогда узлы останутся непрочитанными и судья скажет
    по ним НЕИЗВЕСТНО. Это законный режим замера, а не тихое зелёное."""
    facts = {"commits": None, "files": {}, "rows": {}, "brain": {}, "units": {}}
    need_commits = False
    for ref in refs or ():
        p = result_judge.plan(ref)
        if not p["ok"]:
            continue
        kind, parts = p["kind"], p["parts"]
        if kind == "commit":
            need_commits = True
        elif kind == "file":
            facts["files"].setdefault(parts["path"], None)
        elif kind == "row":
            facts["rows"].setdefault(p["pointer"], parts)
        elif kind == "brain":
            facts["brain"].setdefault(parts["key"], None)
        elif kind == "service_start":
            need_commits = True
            facts["units"].setdefault(parts["unit"], None)
    facts["commits"] = commits_fact() if need_commits else {
        "read": False, "shas": [], "at": {}, "why": "коммиты не спрашивались"}
    facts["files"] = {p: file_fact(p) for p in facts["files"]}
    facts["rows"] = {k: row_fact(v["db"], v["table"], v["conds"]) for k, v in facts["rows"].items()}
    facts["units"] = {u: unit_fact(u) for u in facts["units"]}
    facts["brain"] = {
        k: (brain_fact(k, (before or {}).get(k)) if brain else
            {"read": False, "text": "", "len": 0, "len_before": None,
             "why": "к мосту не ходили"})
        for k in facts["brain"]}
    return facts
