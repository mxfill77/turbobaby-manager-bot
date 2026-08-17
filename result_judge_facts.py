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
  • мозг — `_call("read_doc", name=…)` через мост, ТА ЖЕ дверь, которой ходят все живые
    читатели узлов; импорт моста ЛЕНИВЫЙ, внутри функции: модуль обязан импортироваться и на
    машине, где моста нет вовсе.

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

# ── УЗЕЛ МОЗГА: ОДНА ЖИВАЯ ДВЕРЬ И ЧЕСТНАЯ ПРИЧИНА ОТКАЗА (17.08.2026) ────────────────────────
# Дверь чтения мозга в этом репозитории ОДНА и называется `_call("read_doc", name=…)`: так ходят
# `brain_sync.py`, `cclog.py`, `health.py`, `expectations_run.py`, `devbot.py`, и `brain_sync`
# прямо оговаривает — «своего метода-обёртки нет». Прежний код звал у клиента метод `read_doc`,
# которого НЕТ ВОВСЕ, и `AttributeError` попадал в широкий `except`, выходя наружу словами «мост
# не отвечает». Так НАША поломка представлялась молчанием мира: вид `brain` не мог дать ДОКАЗАН
# ни при каком состоянии моста, а причина в отчёте называла невиновного (разбор 17.08, §3).
BRAIN_ACTION = "read_doc"
BRAIN_ENTRY = "_call"
BRAIN_BUDGET_LABEL = "адрес результата"
BROKEN = "РУКИ СЛОМАНЫ"       # слова НАШЕЙ поломки — их нельзя спутать с молчанием моста

# ОБЩИЙ БЮДЖЕТ НА ОДНО ЧТЕНИЕ УЗЛА — 120 с, и число НЕ ВЫДУМАНО. Это порог О5 для ЧТЕНИЯ МОЗГА,
# выведенный из корпуса 515 живых `read_doc` (137 прогонов `splinter-health` за 21 сутки):
# медиана 2.1 · p95 5.7 · p99 45 · хвост 45·49·51·55·66 — и сразу 207, между 66 и 207 ПУСТО.
# Любое число из пустого промежутка режет РОВНО патологию и не режет ни одного честного чтения;
# 120 стоит внутри него и устойчиво к ±50 с. Из О5 этот порог ушёл только потому, что О5 мерит
# ДРУГОЕ действие (опрос очереди, свой корпус, 240 с) — для своего корпуса он остался верным.
# Живая проба 17.08: `pulse` (218 знаков) 3.05 с · `business_rules` (14 588 знаков) 2.25 с —
# цена здесь круговая, а не размерная. Откат: BRAIN_REF_BUDGET_SEC=0 → дедлайна нет, путь как был.
BRAIN_BUDGET_DEFAULT = 120


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


def _brain_budget():
    """Бюджет одного чтения узла: BRAIN_REF_BUDGET_SEC либо 120 с. Мусор → дефолт, «0» → без
    дедлайна (законный откат: путь становится прежним, а не выключается)."""
    try:
        return float(os.environ.get("BRAIN_REF_BUDGET_SEC") or BRAIN_BUDGET_DEFAULT)
    except (TypeError, ValueError):
        return float(BRAIN_BUDGET_DEFAULT)


def _brain_door():
    """Живая дверь чтения узла → {"door","hold","deadline_err","why","broken"}. Мира НЕ трогает.

    РЕЗОЛВИНГ СТОИТ ОТДЕЛЬНО ОТ ВЫЗОВА, и в этом весь смысл функции. До сети здесь не доходит
    НИЧЕГО, поэтому всё, что падает ЗДЕСЬ, — наша поломка (`broken`), а всё, что упадёт ПОСЛЕ, —
    уже мир. Развести их можно ТОЛЬКО порядком: по типу исключения нельзя (`AttributeError`
    бывает и внутри транспорта), и ровно один широкий `except` вокруг обоих этапов породил класс
    17.08 — несуществующий метод семьдесят дней выдавал себя за молчание моста.

    Отсутствие самого моста поломкой НЕ считается: модуль обязан жить и на машине, где моста нет
    вовсе (о том же говорит шапка). Это «источник недоступен», и вердикт по нему — НЕИЗВЕСТНО."""
    out = {"door": None, "hold": None, "deadline_err": "card_deadline", "why": "", "broken": False}
    try:
        import bridge_client
    except Exception as e:                       # noqa: BLE001 — моста может не быть на машине
        out["why"] = "моста нет на этой машине (%s)" % type(e).__name__
        return out
    door = getattr(bridge_client.BridgeClient, BRAIN_ENTRY, None)
    hold = getattr(bridge_client, "card_budget", None)
    if not callable(door):
        out["why"] = "%s: у клиента моста нет входа «%s» — узел читать нечем" % (BROKEN,
                                                                                BRAIN_ENTRY)
        out["broken"] = True
        return out
    if not callable(hold):
        out["why"] = "%s: у моста нет общего бюджета «card_budget»" % BROKEN
        out["broken"] = True
        return out
    try:
        client = bridge_client.BridgeClient()
    except Exception as e:                       # noqa: BLE001 — настроек моста может не быть
        out["why"] = "клиент моста не собран (%s)" % type(e).__name__
        return out
    out["door"] = getattr(client, BRAIN_ENTRY)
    out["hold"] = hold
    out["deadline_err"] = str(getattr(bridge_client, "CARD_DEADLINE_ERROR", "card_deadline"))
    return out


def brain_fact(key, before=None, budget=None):
    """Узел мозга → {"read","text","len","len_before","why","broken"}. Мост импортируется ЛЕНИВО.

    ЧИТАЕТСЯ ТЕМ ЖЕ ПУТЁМ, ЧТО У ВСЕХ ЖИВЫХ ЧИТАТЕЛЕЙ: `_call("read_doc", name=…)`.

    ПРИЧИН ОТКАЗА ЧЕТЫРЕ, И ОНИ РАЗНЫЕ СЛОВАМИ: наша поломка (`broken=True` — входа нет либо
    ответ не того вида) · моста нет / клиент не собран · мост не отвечает · мост ответил отказом.
    Вердикт у всех один и тот же — НЕИЗВЕСТНО, потому что НЕ ПРОЧИТАНО, — но читателю отчёта они
    говорят РАЗНОЕ, и это вся разница между «чини свой код» и «подожди Google».

    ПОВИСНУТЬ ЗДЕСЬ НЕЛЬЗЯ: чтение идёт под общим бюджетом (`card_budget`, тот же механизм, что у
    карточки «Инфо» и опроса очереди) — исчерпание возвращает ОТВЕТ, а не исключение, и узел
    остаётся честно непрочитанным.

    `before` — длина узла ДО шага; её не пишет никто, и с 17.08.2026 судья её НЕ ТРЕБУЕТ (решение
    Штаба; забор Честертона назван в `result_judge._judge_brain`). Здесь она осталась ДАННЫМИ:
    руки отдают то, что им дали, а судья вправе назвать прирост справкой."""
    d = _brain_door()
    if d["door"] is None:
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": d["why"], "broken": d["broken"]}
    budget = _brain_budget() if budget is None else budget
    try:
        with d["hold"](budget, label=BRAIN_BUDGET_LABEL):
            reply = d["door"](BRAIN_ACTION, name=key)
    except Exception as e:                       # noqa: BLE001 — дальше входа начинается мир
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": "мост не отвечает (%s)" % type(e).__name__, "broken": False}
    if not isinstance(reply, dict):
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": "%s: ответ моста не разобран (%s)" % (BROKEN, type(reply).__name__),
                "broken": True}
    if not reply.get("ok"):
        err = str(reply.get("error") or "")
        why = ("общий бюджет %g с исчерпан — узел не спрошен" % float(budget)
               if err == d["deadline_err"] else
               "мост ответил отказом (%s)" % (err or "без причины"))
        return {"read": False, "text": "", "len": 0, "len_before": before,
                "why": why, "broken": False}
    text = str(reply.get("text") or reply.get("content") or "")
    return {"read": True, "text": text, "len": len(text), "len_before": before, "broken": False}


def gather(refs, before=None, brain=True, budget=None):
    """Список адресов → факты РОВНО под них (каждый источник спрашивается один раз).

    `brain=False` — не ходить к мосту вовсе: тогда узлы останутся непрочитанными и судья скажет
    по ним НЕИЗВЕСТНО. Это законный режим замера, а не тихое зелёное.

    К МОСТУ ХОДИМ ТОЛЬКО ПОД АДРЕС ВИДА `brain`: адрес назвал файл, коммит, строку или юнит —
    словарь узлов пуст, и `brain_fact` не зовётся НИ РАЗУ (цена названа числом в тесте).
    `budget` — потолок ОДНОГО чтения узла в секундах (None → BRAIN_REF_BUDGET_SEC либо 120)."""
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
        k: (brain_fact(k, (before or {}).get(k), budget=budget) if brain else
            {"read": False, "text": "", "len": 0, "len_before": None,
             "why": "к мосту не ходили"})
        for k in facts["brain"]}
    return facts
