#!/usr/bin/env python3
"""РУКИ СЛОЯ ОЖИДАНИЙ — ярус 2 (07.08.2026). Зовётся `expectations.timer` раз в 10 минут.

Решение живёт в `expectations.py` (чистая функция «факты → вердикт», ни одного обращения к миру).
Здесь — ровно руки: СОБРАТЬ факты, ОТНЕСТИ вердикт в канал, СОХРАНИТЬ доказательство и состояние.

ПОЧЕМУ ОТДЕЛЬНЫЙ ПРОЦЕСС, А НЕ ВЕТКА В ДЕМОНЕ (правило владельца «наблюдатель не живёт на том,
за чем следит»): О1 наблюдает, БЕРЁТ ЛИ РАБОТУ ДЕМОН, а О2 — даёт ли демон оборот. Наблюдатель
внутри демона молчал бы ровно в наблюдаемом случае — так сегодня устроен `_maybe_prod_drift`
(живёт в `cycle()` и слеп, когда демон стоит), и повторять это здесь нельзя.

ШЕСТЬ ИСТОЧНИКОВ ФАКТОВ, КАЖДЫЙ ПЕРЕЖИВАЕТ СМЕРТЬ СВОЕГО ПРЕДМЕТА:
  очередь  — GET моста (одним вызовом, обе полосы);
  оборот   — файл пульса в /tmp, который демон пишет в конце cycle();
  тик      — хвост splinter.log на диске;
  доставка — origin/main (читающий git), замыкание импортов, /proc и mtime файлов репозитория
             (О3: дошёл ли проверенный коммит до прода; три исхода, включая «неизвестно»);
  ПК       — журнал ПК-контура `cowork_log` через мост: его пишет ТОЛЬКО ПК, а читаем его мы,
             значит факт переживает смерть машины, которая его произвела (О4);
  мост     — СОБСТВЕННАЯ проба: тот же GET очереди, но с замером «удался ли» и «сколько занял»
             (О5). Отдельного вызова ради этого не делается — канал судится по следу того, кто
             через него ходит, а не по словам самого канала о себе.
Ни демон, ни splinter отсюда НЕ импортируются. Единственный сосед — `prod_drift`, у которого
берётся read-only разведка /proc (кто жив и когда стартовал): она уже доказана инвариантом
PROD_DRIFT_READONLY и покрыта своими тестами, дубль того же кода был бы второй правдой.

ПОЧЕМУ ЖУРНАЛ ПК ЧИТАЕТСЯ НЕ КАЖДЫЙ ПРОГОН. Он весит ≈310 КБ, и путь его чтения — ровно тот,
у которого замер 08.08 нашёл разброс до 207 с. Порог О4 — часы, значит часовое разрешение
достаточно: журнал читается раз в PC_PROBE_MIN, а рядом с порогом (когда до нарушения остаётся
меньше «свежести» факта) — каждый прогон. Так заявление «следа нет» всегда стоит на чтении не
старше EXPECT_PC_FRESH_MIN, а нагрузка на мост остаётся 24 чтения в сутки вместо 144.

ГРАНИЦА ВЛАДЕЛЬЦА (реакция): заметка в ленту 829 и, если нарушение ДЕРЖИТСЯ, задача в очередь.
Ни одна ветка не перезапускает процессов, не правит данных и не трогает инфраструктуру. Задача
ставится по правилу годности 4.2 — её исполнитель обязан быть доказанно жив (иначе она ляжет в
ту же вставшую очередь и создаст ВИДИМОСТЬ действия), поэтому у нарушения «демон не даёт
оборота» задачи не бывает никогда.

АДРЕС НАБЛЮДЕНИЯ — МОЗГ, А НЕ ВЛАДЕЛЕЦ (13.08.2026, решение владельца). Замер 5.65 суток:
владельцу ушло 67 сообщений слоя, ОТВЕТА ждало НОЛЬ — ни у одной заметки нет ни кнопки, ни
номера, ни слова «да». По §3 рамки карточки идут в инбокс, а наблюдение карточкой не является,
значит его место — журнал мозга. Теперь: наблюдение пишется в `cc_log` (канонический путь
`cclog.write_cclog`, R16), а владельцу уходит ТОЛЬКО то, что пережило отсрочку И задевает
деньги, живые таблицы или клиентский контур (решает чистая функция `expect_journal`).

ОТСРОЧКА ВЗЯТА ЗАМЕРОМ ЖИЗНИ ЭПИЗОДОВ, а не на глаз: из 33 закрытых эпизодов окна 31 прожил
≤42 мин (o5s 6…18 · o2d 10…30 · o3 10…42), а два оставшихся — 642 и 785 мин. Между 42 и 642
ПУСТО, поэтому любое значение из [43, 641] мин гасит РОВНО те же 31; внутри этой полосы взято
число, которое слой уже означает словом «нарушение держится», — `EXPECT_HOLD_MIN` = 60 мин.
Своя ручка `EXPECT_OWNER_DEFER_MIN` (мин) её переопределяет.

ОДНА СТРОКА НА ЭПИЗОД, А НЕ НА ТИК. Длительность растёт в СОСТОЯНИИ (поле `ticks`/`last`), а на
диск идёт одна строка — при закрытии, с началом, концом и длительностью. Эпизод, переживший
отсрочку, получает вторую и последнюю строку «держится»: иначе о самом долгом нарушении в
журнале не было бы ни слова до его конца. На замере это 35 строк на 33 эпизода.

ПРОТИВ read-and-ignore: одно сообщение на эпизод и одно на его закрытие. Повторов-напоминаний
НЕТ намеренно — это ровно тот шум, за который 05.08 отозван класс push из ленты.

FAIL-SAFE: любой сбой сбора → факта нет → вердикта нет (молчание). Заметка не ушла → эпизод НЕ
помечен, скажем на следующем прогоне. Доказательство не записалось → заметка всё равно уходит.

ОТКАТ: остановить и выключить таймер `expectations` (одна команда владельца), либо порог
соответствующей ветки = 0 в .env (EXPECT_NEW_MIN / EXPECT_TURN_MIN / EXPECT_TICK_MIN /
EXPECT_PC_MIN / EXPECT_BRIDGE_MIN / EXPECT_BRIDGE_SLOW_SEC), либо EXPECT_TASK=0 — тогда живут
только заметки, задач не ставится вовсе. У О4 и О5 задачи не бывает НИКОГДА и без этого флага.
ОТКАТ АДРЕСА отдельной ручкой: `EXPECT_TO_BRAIN=0` — в мозг не пишется ничего, все заметки
уходят владельцу в ленту БАЙТ-В-БАЙТ как до 13.08.2026.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"))

import expectations
import expect_journal              # чистая функция «вердикт → адрес и строка журнала»
import queue_state                 # чистая функция «факты очереди → писать ли слепок и чем»
import prod_drift                  # только read-only разведка /proc (live/started_at)

LANE = "VPS"                       # метка полосы в заметке; на зеркале ПК обязана стать «ПК»
# Журнал СВОЕЙ полосы: у VPS это cc_log. Зеркало ПК обязано сменить ключ на свой (cowork_log).
JOURNAL_DOC = "cc_log"
OWNER_DEFER_ENV, OWNER_DEFER_DEFAULT = "EXPECT_OWNER_DEFER_MIN", 60.0   # замер: полоса [43,641]
PULSE_DIR = "/tmp/cc_expect_pulse"          # сюда демон пишет оборот cycle() (см. _expect_pulse)
STATE_DIR = "/tmp/cc_expect_seen"           # открытые эпизоды: о чём уже сказали
SPLINTER_LOG = os.path.join(REPO, "splinter.log")
CLAIMS_LOG = os.path.join(REPO, "orchestrator_claims.jsonl")
REPORTS = os.path.join(REPO, "reports")
TAIL_BYTES = 400_000               # ≈16 часов лога: тик найдётся, даже если splinter давно молчит
TASK_FROM = "Filipp-328-dev"       # метка очереди: отчёт доезжает в 328 без правки devbot
TASK_CAP_DAY = 2                   # потолок задач-эскалаций в сутки (страховка от петли)
STATE_KEEP = 32
QUEUE_TIMEOUT = 45                 # бюджет ОДНОГО обмена пробы моста (её длительность и мерим)
COWORK_DOC = "cowork_log"          # журнал ПК-контура: пишет ТОЛЬКО ПК, читаем мостом (О4)
PC_PROBE_ENV, PC_PROBE_DEFAULT = "EXPECT_PC_PROBE_MIN", 60.0   # как часто ходить за журналом ПК


def _dir(base):
    """Каталог состояния. ORCH_TEST_MODE → тест-каталог (тест НЕ пишет в боевой никогда),
    CC_EXPECT_DIR — явная подмена. Зеркало дисциплины _drift_dir демона."""
    explicit = (os.environ.get("CC_EXPECT_DIR") or "").strip()
    if explicit:
        return os.path.join(explicit, os.path.basename(base))
    if (os.environ.get("ORCH_TEST_MODE") or "").strip():
        return base + "_test"
    return base


# ═════════════════════════════════ СБОР ФАКТОВ (только чтение) ═════════════════════════════
def read_pulse():
    """Пульс демона → {"ts","n","pid","started"} | None. Нет файла/мусор → None, и это МОЛЧАНИЕ:
    «демон держит код без пульса» и «демон мёртв» отсюда неотличимы (см. expectations._o2_daemon)."""
    try:
        with open(os.path.join(_dir(PULSE_DIR), "pulse.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("ts") else None
    except Exception:
        return None


def claims_ts():
    """Когда демон в последний раз ВЗЯЛ работу (журнал претензий). → эпоха | None.
    Берётся mtime файла: он и есть момент записи претензии, а разбор последней строки добавил бы
    разбор ради того же числа."""
    try:
        return os.stat(CLAIMS_LOG).st_mtime
    except OSError:
        return None


def log_tail(path=None, nbytes=TAIL_BYTES):
    """Хвост файла текстом. splinter.log без ротации (39 МБ, 67 суток) — читать целиком нельзя,
    это прямо названо пределом в проекте; читаем хвост."""
    path = path or SPLINTER_LOG
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > nbytes:
                f.seek(size - nbytes)
                f.readline()                       # первая строка после seek обычно обрезана
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def queue_facts():
    """Снимок открытых строк ОБЕИХ полос одним GET → {"ok","rows","dt","err","probed"}.
    Мост молчит → ok=False, то есть фактов нет и О1 молчит (честная зависимость, названа в проекте).

    ЭТОТ ЖЕ ВЫЗОВ — ПРОБА МОСТА ДЛЯ О5, поэтому у него меряется длительность и различаются два
    провала: «пробу не удалось даже поставить» (клиента не собрать — измерять нечего, исход
    «неизвестно») и «проба поставлена и провалилась» (измеренный отказ). Разница не косметическая:
    первое не вправе копиться в возраст отказа, второе обязано."""
    t0 = time.time()
    try:
        from bridge_client import BridgeClient
        bc = BridgeClient(timeout=QUEUE_TIMEOUT)
    except Exception as e:                                           # noqa: BLE001
        return {"ok": False, "rows": [], "dt": None, "probed": False,
                "err": "клиент моста не собрался: %s" % str(e)[:120]}
    try:
        r = bc.get_pending_multi(list(expectations.OPEN_STATUSES), lane="all")
    except Exception as e:                                           # noqa: BLE001
        return {"ok": False, "rows": [], "dt": time.time() - t0, "probed": True,
                "err": str(e)[:120]}
    dt = time.time() - t0
    if not r.get("ok"):
        return {"ok": False, "rows": [], "dt": dt, "probed": True,
                "err": str(r.get("error") or "мост ответил без ok")[:120]}
    rows = []
    for it in (r.get("items") or []):
        if not isinstance(it, dict):
            continue
        # «когда строка вошла в нынешнее состояние»: updated, а при его отсутствии created.
        since = expectations.parse_iso(it.get("updated")) or expectations.parse_iso(it.get("created"))
        rows.append({
            "id": it.get("id"),
            "status": it.get("status"),
            "lane": it.get("lane"),
            "from": it.get("from"),
            "since": since,
            "text": str(it.get("task_text") or "")[:200],
        })
    return {"ok": True, "rows": rows, "dt": dt, "probed": True, "err": ""}


def bridge_facts(q, st, now):
    """Проба моста → факт для О5. Историю успехов держит СОСТОЯНИЕ (пережить прогон иначе нечем):
    last_ok — когда мост в последний раз ответил, last_fast — когда ответил В БЮДЖЕТЕ.

    Истории нет → в фактах None, и решение честно скажет «неизвестно», а не «не отвечает N минут»."""
    prev = (st or {}).get("bridge") if isinstance(st, dict) else None
    prev = prev if isinstance(prev, dict) else {}
    q = q if isinstance(q, dict) else {}
    return {
        # True — ответил · False — измеренный отказ · None — пробы не было вовсе.
        "ok": bool(q.get("ok")) if q.get("probed") else None,
        "dt": q.get("dt"),
        "err": q.get("err") or "",
        "last_ok": prev.get("last_ok"),
        "last_fast": prev.get("last_fast"),
    }


def remember_bridge(st, facts, now, cfg):
    """Запомнить успехи пробы ПОСЛЕ вердикта: иначе сегодняшний успех обнулил бы возраст отказа,
    по которому вердикт и выносится."""
    b = (facts or {}).get("bridge") or {}
    prev = (st.get("bridge") or {}) if isinstance(st.get("bridge"), dict) else {}
    if b.get("ok"):
        prev["last_ok"] = now
        slow = float((cfg or {}).get("bridge_slow") or 0.0)
        try:
            dt = float(b.get("dt") or 0.0)
        except (TypeError, ValueError):
            dt = 0.0
        if slow <= 0 or dt <= slow:
            prev["last_fast"] = now
    st["bridge"] = prev


def pc_facts(st, now, cfg):
    """Свежий срез журнала ПК-контура → факт для О4 (читается мостом, пишется ТОЛЬКО ПК).

    ЧИТАЕМ НЕ КАЖДЫЙ ПРОГОН (см. шапку): раз в PC_PROBE_MIN, но ОБЯЗАТЕЛЬНО каждый прогон, когда
    до порога осталось меньше «свежести» — заявление «следа нет» обязано стоять на свежем чтении.
    Прошлое чтение провалилось → пробуем снова сразу, ждать час незачем.

    Кэш живёт в состоянии и несёт `fetched`; решение само откажется судить по устаревшему срезу."""
    prev = (st or {}).get("pc") if isinstance(st, dict) else None
    prev = prev if isinstance(prev, dict) else {}
    every = expectations.limit_env(PC_PROBE_ENV, PC_PROBE_DEFAULT, os.environ)
    limit = float((cfg or {}).get("pc") or 0.0)
    fresh = float((cfg or {}).get("pc_fresh") or 0.0)
    try:
        fetched = float(prev.get("fetched") or 0.0)
        last = float(prev.get("last") or 0.0)
    except (TypeError, ValueError):
        fetched, last = 0.0, 0.0
    near = bool(limit > 0 and last > 0 and (now - last) >= (limit - fresh))
    if prev.get("ok") and fetched > 0 and (now - fetched) < every and not near:
        out = dict(prev)
        out["cached"] = True
        return out
    if limit <= 0:
        return dict(prev, cached=True) if prev else {"ok": False, "err": "ветка О4 выключена"}
    t0 = time.time()
    try:
        from bridge_client import BridgeClient
        r = BridgeClient(timeout=QUEUE_TIMEOUT)._call("read_doc", name=COWORK_DOC)
    except Exception as e:                                           # noqa: BLE001
        return {"ok": False, "err": "журнал ПК не прочитан: %s" % str(e)[:100],
                "fetched": 0, "last": prev.get("last"), "line": prev.get("line"),
                "dt": time.time() - t0}
    if not r.get("ok"):
        return {"ok": False, "err": str(r.get("error") or "мост ответил без ok")[:100],
                "fetched": 0, "last": prev.get("last"), "line": prev.get("line"),
                "dt": time.time() - t0}
    f = expectations.cowork_facts(r.get("text") or "", now)
    return {"ok": True, "err": "", "fetched": now, "dt": time.time() - t0,
            "last": f.get("last"), "line": f.get("line"), "n": f.get("n"), "cached": False}


def _proc(unit, entry):
    """Живой процесс юнита (read-only /proc, через prod_drift) → {"pid","started"} | None."""
    try:
        p = prod_drift.live(unit, entry)
    except Exception:
        return None
    return {"pid": p["pid"], "started": p["started"]} if p else None


# ═══════════════════ ФАКТЫ О3: ДОШЁЛ ЛИ ПРОВЕРЕННЫЙ КОММИТ ДО ПРОДА ════════════════════════
# Собственный читающий git, а не расширение GIT_READ соседа: `prod_drift` лежит В ПАМЯТИ демона,
# и правка ради чужой нужды сделала бы его самого отставшим. Дисциплина та же — белый список
# подкоманд сверяется на КАЖДОМ вызове, аргументы литеральные.
GIT_READ_RUN = frozenset(("diff", "log", "rev-parse"))
GIT_TIMEOUT = 20


def _git(args):
    """Читающий git → stdout | None. Подкоманда вне белого списка не исполняется ВООБЩЕ."""
    if not args or args[0] not in GIT_READ_RUN:
        return None
    try:
        p = subprocess.run(["git"] + list(args), cwd=REPO,
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def dirty_files():
    """Файлы, которыми рабочее дерево ОТЛИЧАЕТСЯ от origin/main → (список, спросили_ли_успешно).

    Это и есть замок против ложного зелёного: доставка утверждается только тогда, когда байты на
    диске ДОКАЗАННО те же, что в origin/main. Не смогли спросить → False, и каждый файл коммита
    станет «неизвестно», а не «доставлен»."""
    out = _git(["diff", "--name-only", "origin/main", "--"])
    if out is None:
        return [], False
    return [ln.strip() for ln in out.splitlines() if ln.strip()], True


# ═══ ЧЕМ ОТВЕЧАЮТ НА ВОПРОС «А ЧТО ЖЕ ЛЕЖИТ НА ДИСКЕ» (15.08.2026) ════════════════════════════
# Расхождение с origin/main говорит ТОЛЬКО «файл не такой, как в ветке» — этого мало, чтобы
# судить доставку: коммит мог быть перекрыт более новым, а мог и не быть. Поэтому здесь снимаются
# ДВА хеша, и оба — факт: что коммит ОСТАВИЛ в файле (печатает git) и что в файле лежит СЕЙЧАС
# (считается из байтов). Решение по ним принимает `expectations.disk_carries`, здесь решений нет.
_BLOB_MAX = 8 * 1024 * 1024        # больше — не хешируем: «не знаю» дешевле долгого прогона
_ZERO_BLOB = "0" * 40              # git так печатает post-image удалённого файла


def blob_sha1(path):
    """Содержимое файла → хеш В ФОРМЕ БЛОБА git (`sha1("blob <длина>\\0" + байты)`).

    Ровно то же число, что печатает `git hash-object`, — сверено на живом файле. Считаем сами,
    а не зовём git: подкоманды записи в белом списке нет, и заводить её ради чтения незачем."""
    try:
        with open(path, "rb") as fh:
            body = fh.read(_BLOB_MAX + 1)
    except OSError:
        return None
    if len(body) > _BLOB_MAX:
        return None                                        # не судим — честнее, чем судить долго
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


def commit_blobs(since, paths):
    """{путь: {коммит: хеш содержимого ПОСЛЕ него}} — одна команда на весь список путей.

    `--raw` печатает post-image каждого изменения, то есть ровно то, что коммит ОСТАВИЛ в файле.
    Спрашиваем только про пути, разошедшиеся с origin/main в ЭТОМ прогоне: на чистом дереве
    стоимость ровно ноль (команда не зовётся вовсе), а грязных файлов бывает единицы.
    Коммиты ключуются так же, как в `commits_since`, — семью знаками."""
    paths = sorted(paths or ())
    if not paths:
        return {}
    out = _git(["log", "origin/main", "--since=" + since, "--format=%H", "--raw", "--no-abbrev",
                "--"] + paths)
    if not out:
        return {}
    blobs, sha = {}, None
    for ln in out.splitlines():
        ln = ln.rstrip()
        if not ln:
            continue
        if ln.startswith(":"):
            meta, _, rest = ln.partition("\t")
            f = meta.split()
            # У переименования путей два — берём ПОСЛЕДНИЙ, то есть назначение: именно оно лежит
            # на диске и именно его имя стоит в списке файлов коммита.
            rel = expectations.norm_path(rest.split("\t")[-1])
            if len(f) < 5 or not rel or sha is None or f[3] == _ZERO_BLOB:
                continue                                   # удаление: сравнивать нечего с чем
            blobs.setdefault(rel, {})[sha[:7]] = f[3]
            continue
        if len(ln) == 40 and not ln.strip("0123456789abcdef"):
            sha = ln
    return blobs


def delivery_facts(now):
    """Факты О3 и ни одного решения: коммиты окна, замыкания потребителей, живые процессы,
    время последней записи файлов, расхождение диска с origin/main.

    git недоступен / ref origin/main отсутствует → ok=False, то есть выборки нет и О3 молчит
    (о молчании честно сказано в шапке expectations.py: это не «дошло», это отсутствие фактов)."""
    cfg_window = expectations.limit_env(expectations.DELIVER_WINDOW_ENV,
                                        expectations.DELIVER_WINDOW_DEFAULT,
                                        os.environ, scale=3600.0)
    # Берём с запасом: судейское окно применяет решение, а фактов пусть будет чуть больше.
    since_ts = max(0.0, now - max(cfg_window, 3600.0) * 2)
    try:
        commits = prod_drift.commits_since(since_ts, REPO)
    except Exception:
        commits = []
    if not commits and _git(["rev-parse", "--verify", "origin/main"]) is None:
        return {"ok": False, "commits": [], "closures": {}, "units": {}, "mtimes": {},
                "dirty": [], "dirty_ok": False, "blobs": {}, "disk": {}}
    closures, units = {}, {}
    for unit, entry in prod_drift.WATCHED:
        try:
            closures[unit] = sorted(prod_drift.closure(entry, REPO))
        except Exception:
            closures[unit] = []
        p = _proc(unit, entry)
        units[unit] = {"alive": bool(p), "started": (p or {}).get("started"),
                       "pid": (p or {}).get("pid"), "entry": entry}
    mtimes = {}
    for c in commits:
        for rel in (c.get("files") or []):
            rel = expectations.norm_path(rel)
            if rel in mtimes:
                continue
            try:
                mtimes[rel] = os.stat(os.path.join(REPO, rel)).st_mtime
            except OSError:
                continue                       # файла нет (удалён коммитом) — свидетель С1 хватит
    dirty, dirty_ok = dirty_files()
    # ХЕШИ СНИМАЮТСЯ ТОЛЬКО ПРО СПОРНЫЕ ФАЙЛЫ — те, что разошлись с origin/main И тронуты
    # коммитами окна. Чистое дерево (обычный случай) не платит ни одной лишней команды.
    hot = sorted({expectations.norm_path(x) for x in dirty} & set(mtimes))
    since = time.strftime("%Y-%m-%d %H:%M:%S +0000", time.gmtime(since_ts))
    blobs = commit_blobs(since, hot) if (hot and dirty_ok) else {}
    disk = {}
    for rel in (hot if blobs else ()):
        h = blob_sha1(os.path.join(REPO, rel))
        if h:
            disk[rel] = h
    return {"ok": True, "commits": commits, "closures": closures, "units": units,
            "mtimes": mtimes, "dirty": dirty, "dirty_ok": dirty_ok, "blobs": blobs, "disk": disk}


def snapshot(now=None, st=None, cfg=None):
    """ФАКТЫ и ни одного решения. Порогов здесь нет — их применяет expectations.verdict().

    `st` — состояние прошлых прогонов: у моста и ПК факт СОСТАВНОЙ (сегодняшняя проба + история
    успехов / кэш журнала), пережить прогон ему больше нечем. Состояния нет → истории нет, и
    решение честно скажет «неизвестно» вместо выдуманного возраста."""
    now = time.time() if now is None else float(now)
    cfg = cfg if isinstance(cfg, dict) else expectations.config(os.environ)
    st = st if isinstance(st, dict) else {}
    tick = expectations.tick_facts(log_tail())
    q = queue_facts()
    return {
        "now": now,
        "queue": q,
        "daemon": {"pulse": read_pulse(),
                   "proc": _proc("orchestrator-daemon", "orchestrator_daemon.py"),
                   "claims": claims_ts()},
        "splinter": {"tick": tick.get("tick"), "log": tick.get("log"),
                     "proc": _proc("splinter", "bot.py")},
        "delivery": delivery_facts(now),
        "bridge": bridge_facts(q, st, now),
        # Журнал ПК читается ТОЛЬКО когда канал в этом же прогоне ответил: тянуть второй вызов в
        # лежащий мост незачем — исход всё равно «неизвестно», а лишний вызов стоит времени.
        "pc": pc_facts(st, now, cfg) if q.get("ok") else
              dict((st.get("pc") or {}) if isinstance(st.get("pc"), dict) else {},
                   ok=False, err="мост не ответил в этом прогоне — журнал ПК не читался"),
    }


# ═══════════════════════════════ СОСТОЯНИЕ: ОДИН ЭПИЗОД — ОДНО СООБЩЕНИЕ ═══════════════════
def load_state():
    try:
        with open(os.path.join(_dir(STATE_DIR), "state.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_state(st):
    """Best-effort: диск недоступен → худшее, что случится, — повтор заметки на следующем прогоне."""
    d = _dir(STATE_DIR)
    try:
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "state.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(d, "state.json"))
    except Exception as e:                                           # noqa: BLE001
        print("состояние не сохранено (%s) — возможен повтор заметки" % e, file=sys.stderr)


WAIT_STEP_CAP = 1200.0             # сколько максимум засчитывать за ОДНО наблюдение (2 периода)


def update_waits(state, facts, now):
    """Накопить ЧИСТОЕ ожидание каждой строки `new` полосы vps — время, простоянное ИМЕННО ПРИ
    СВОБОДНОЙ полосе. Именно по нему О1 берёт порог (обоснование — шапка expectations.py).

    ПОЧЕМУ СЧЁТЧИК, А НЕ МГНОВЕННЫЙ СНИМОК. Полоса одно-воркерная, и между двумя задачами всегда
    есть щель, в которую снимок видит «свободно». Правило по мгновенному снимку дало на реплее
    7 суток 17 ложных эпизодов (живой образец — задача 330: 69 минут в new, из них при свободной
    полосе 15). Счётчик эти щели складывает и до порога не доводит, а вставшую полосу доводит за
    три наблюдения.

    ЗА ОДНО НАБЛЮДЕНИЕ ЗАСЧИТЫВАЕТСЯ НЕ БОЛЬШЕ WAIT_STEP_CAP: таймер мог не работать час, и о
    занятости полосы в этот час мы не знаем НИЧЕГО — записать его в «свободное» значило бы
    выдумать факт. Первое наблюдение строки не добавляет ничего вовсе (не с чем сравнивать).

    Снимка очереди нет → счётчики не трогаем ВООБЩЕ: молчание моста не есть простой полосы."""
    q = (facts or {}).get("queue") or {}
    if not q.get("ok"):
        return
    rows = [r for r in (q.get("rows") or [])
            if str(r.get("lane") or "vps").lower() == expectations.VPS_LANE]
    busy = any(str(r.get("status") or "").lower() == "in_progress" for r in rows)
    prev = state.get("waits") or {}
    cur = {}
    for r in rows:
        if str(r.get("status") or "").lower() != "new":
            continue
        try:
            since = float(r.get("since") or 0)
        except (TypeError, ValueError):
            continue
        if since <= 0:
            continue
        key = "%s|%d" % (r.get("id"), int(since))          # тот же ключ, что у эпизода О1
        old = prev.get(key) or {}
        free = float(old.get("free") or 0.0)
        last = float(old.get("seen") or 0.0)
        if not busy and last > 0:
            free += max(0.0, min(now - last, WAIT_STEP_CAP))
        cur[key] = {"free": free, "seen": now}
        r["free_wait"] = free
    state["waits"] = cur          # строки, ушедшие из new, выпадают сами — состояние не растёт


def _tasks_today(st, now):
    """Сколько задач-эскалаций поставлено за последние сутки (потолок TASK_CAP_DAY)."""
    out = 0
    for rec in (st.get("tasks") or []):
        try:
            if now - float(rec.get("ts") or 0) < 86400:
                out += 1
        except (TypeError, ValueError):
            continue
    return out


# ═══════════════════════════════ ДОКАЗАТЕЛЬСТВО (улики живут меньше нарушения) ═════════════
def write_proof(v, facts, now):
    """Файл в reports/<дата>/expect-<ключ>.md — сырые факты в момент обнаружения.
    Когда ПК выключен, а мост отказывает, улик потом не будет: журнал перетрётся, тела ответов
    исчезнут. → путь | "" (сбой записи заметку НЕ отменяет)."""
    try:
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        d = os.path.join(REPORTS, day)
        os.makedirs(d, exist_ok=True)
        safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(v.get("key")))
        path = os.path.join(d, "expect-%s.md" % safe[:60])
        body = [
            "# Ожидание нарушено: %s" % v.get("kind"),
            "",
            "- обнаружено: %s UTC" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)),
            "- ключ эпизода: `%s`" % v.get("key"),
            "- возраст нарушения: %s (порог %s)" % (expectations.human_age(v.get("age")),
                                                    expectations.human_age(v.get("limit"))),
            "- реакция: заметка в ленту 829; задача — только если нарушение держится и правило "
            "годности 4.2 выполнено (`can_task=%s`)" % v.get("can_task"),
            "",
            "## Заметка, ушедшая владельцу",
            "",
            "```", expectations.render(v, LANE), "```",
            "",
            "## Сырые факты снимка",
            "",
            "```json",
            json.dumps(facts, ensure_ascii=False, indent=1, default=str)[:12000],
            "```",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
        return path
    except Exception as e:                                           # noqa: BLE001
        print("доказательство не записано (%s)" % e, file=sys.stderr)
        return ""


# ═══════════════════════════════════ МАРШРУТ РЕАКЦИИ ═══════════════════════════════════════
def send_note(text):
    """Заметка в ленту 829. Адреса нет → не уходит НИКУДА (у ленты фолбэка нет намеренно)."""
    try:
        import notify
        return bool(notify.send_feed(text))
    except Exception as e:                                           # noqa: BLE001
        print("заметка не ушла (%s)" % e, file=sys.stderr)
        return False


def _is_test_run():
    """Прогон под тестом/гейтом. Изоляция канала обязательна: строка фикстуры, доехавшая до
    боевого cc_log, портит журнал мозга ровно так же, как её доехавший пуш портил личку
    владельцу (класс «канал 2 изоляции проб»)."""
    for name in ("ORCH_TEST_MODE", "PYTEST_CURRENT_TEST", "PRETOOL_TEST_RUN"):
        if (os.environ.get(name) or "").strip():
            return True
    return False


def write_journal(text):
    """СТРОКА НАБЛЮДЕНИЯ В МОЗГ. Канонический путь — `cclog.write_cclog` (правило R16: прямой
    `write_doc(name="cc_log")` минует length-guard и защиту от затирки).

    Не удалось записать → False, и эпизод НЕ помечается: скажем на следующем прогоне. Терять
    наблюдение молча нельзя — ради этого адрес и менялся."""
    if _is_test_run():
        print("[тест] в мозг НЕ пишем: %s" % str(text)[:160])
        return True
    try:
        import cclog
        return bool(cclog.write_cclog("NOTE", str(text), label="expectations"))
    except Exception as e:                                           # noqa: BLE001
        print("наблюдение не записано в мозг (%s)" % e, file=sys.stderr)
        return False


def _to_brain():
    """Ручка отката адреса: EXPECT_TO_BRAIN=0 → поведение до 13.08.2026 байт-в-байт."""
    return str(os.environ.get("EXPECT_TO_BRAIN") or "1").strip() not in ("0", "no", "off")


# ═══════════════════ СЛЕПОК СОСТОЯНИЯ ОЧЕРЕДИ В МОЗГ (14.08.2026) ═══════════════════════════
# РУКИ чистого решения `queue_state`: спросить упавших (дорого — значит по факту), записать
# слепок в свой документ мозга, запомнить опубликованное. Решает не здесь: здесь только берут
# и кладут.
#
# ПОЧЕМУ СЛЕПОК ЖИВЁТ У НАБЛЮДАТЕЛЯ, А НЕ У ДЕМОНА. Демон исполняет `claude -p` СИНХРОННО
# внутри `cycle()`: живой замер — задача 536 держала оборот 1026 с, рекорд наблюдения 41.6 мин.
# Слепок, который пишет сам демон, публиковал бы «занято» ПОСЛЕ конца работы, то есть ровно
# тогда, когда это перестало быть нужно. Наблюдатель яруса 2 — отдельный процесс с диска, он
# тикает свои 10 минут независимо от того, чем занят демон, и уже берёт снимок открытых строк
# ОБЕИХ полос (`queue_facts`) — открытая половина слепка достаётся даром.
def _qstate_on():
    """Ручка отката: QUEUE_STATE=0 → ветка мертва ДО единого обращения к мосту."""
    return str(os.environ.get("QUEUE_STATE") or "1").strip() not in ("0", "no", "off")


def failed_facts():
    """Упавшие строки ОБЕИХ полос → список | None (мост не ответил — исход честно «не сверен»).

    Дорогой вопрос: 301 КБ ответа (замер 14.08). Поэтому его задаёт РЕШЕНИЕ (`needs_closed`),
    а не таймер: спрашиваем, когда строка ушла из открытых, либо реестр старше часа."""
    try:
        from bridge_client import BridgeClient
        bc = BridgeClient(timeout=QUEUE_TIMEOUT)
        r = bc.get_pending("failed", lane="all")
    except Exception as e:                                           # noqa: BLE001
        print("упавшие не прочитаны (%s) — исход закрытых будет «не сверен»" % str(e)[:120],
              file=sys.stderr)
        return None
    if not r.get("ok"):
        return None
    rows = []
    for it in (r.get("items") or []):
        if not isinstance(it, dict):
            continue
        rows.append({"id": it.get("id"), "lane": it.get("lane"),
                     "task_text": str(it.get("task_text") or "")[:200],
                     "result": str(it.get("result") or "")[:400],
                     "at": expectations.parse_iso(it.get("updated"))})
    return rows


def closed_facts():
    """РАЗОВЫЙ засев реестра: закрытые строки ОБЕИХ полос → список | None.

    Самый дорогой вопрос контура (2745 КБ на замере 14.08) и потому задаётся РОВНО ОДИН РАЗ на
    жизнь состояния: без него первые сутки раздел «закрыто за сутки» был бы пуст при 26 реально
    закрытых — ложный нуль вместо знания."""
    try:
        from bridge_client import BridgeClient
        bc = BridgeClient(timeout=QUEUE_TIMEOUT)
        r = bc.get_pending("done,failed", lane="all")
    except Exception as e:                                           # noqa: BLE001
        print("засев реестра закрытых не удался (%s)" % str(e)[:120], file=sys.stderr)
        return None
    if not r.get("ok"):
        return None
    rows = []
    for it in (r.get("items") or []):
        if not isinstance(it, dict):
            continue
        rows.append({"id": it.get("id"), "lane": it.get("lane"), "status": it.get("status"),
                     "task_text": str(it.get("task_text") or "")[:200],
                     "result": str(it.get("result") or "")[:400],
                     "at": expectations.parse_iso(it.get("updated"))})
    return rows


def write_queue_state(text):
    """Слепок в свой документ мозга ЦЕЛИКОМ (перезапись, не журнал). → True | False.

    Изоляция та же, что у `write_journal`: под тестом/гейтом в боевой мозг не пишем НИКОГДА.
    Не записалось → отпечаток НЕ запоминаем, значит следующий прогон попробует снова."""
    if _is_test_run():
        print("[тест] слепок очереди НЕ пишем: %d симв." % len(str(text)))
        return True
    try:
        from bridge_client import BridgeClient
        bc = BridgeClient(timeout=QUEUE_TIMEOUT)
        r = bc.write_doc(str(text), name=queue_state.DOC_KEY)
    except Exception as e:                                           # noqa: BLE001
        print("слепок очереди не записан (%s)" % str(e)[:120], file=sys.stderr)
        return False
    if not r.get("ok"):
        print("слепок очереди не записан (%s)" % str(r.get("error"))[:120], file=sys.stderr)
        return False
    return True


def queue_state_step(st, facts, now, dry=False):
    """Один шаг слепка. → {"write","why","wrote"} для итога прогона (и для теста).

    FAIL-SAFE ВЕЗДЕ В СТОРОНУ МОЛЧАНИЯ: ручка выключена · решение сказало «не менялось» ·
    запись не прошла → состояние не помечается, документ остаётся прежним со СВОИМ временем
    снятия — то есть врать свежестью ему по-прежнему нечем."""
    if not _qstate_on():
        return {"write": False, "why": "QUEUE_STATE=0 — ветка выключена", "wrote": False}
    prev = st.get("qstate") if isinstance(st.get("qstate"), dict) else {}
    q = facts.get("queue") if isinstance(facts.get("queue"), dict) else {"ok": False}
    rows = q.get("rows") or []
    prev_open = prev.get("open") if isinstance(prev.get("open"), dict) else {}
    gone, closed_at = list(prev.get("gone") or []), prev.get("closed_at")
    since = prev.get("since")
    if q.get("ok"):
        # ЗАСЕВ — один раз на жизнь состояния и ТОЛЬКО при живой очереди: реестр, засеянный
        # вслепую, был бы тем же ложным нулём, только дороже.
        if queue_state.needs_seed(since):
            seeded = closed_facts()
            if seeded is not None:
                gone = queue_state.seed(seeded, now)
                since, closed_at = now - queue_state.SHOW_SEC, now
        failed = None
        if queue_state.needs_closed(prev_open, rows, closed_at, now):
            failed = failed_facts()
            if failed is not None:
                closed_at = now
        gone = queue_state.ledger(gone, prev_open, rows, failed, now)
    v = queue_state.verdict(prev, q, gone, now, closed_at, LANE, since)
    out = {"write": bool(v.get("write")), "why": v.get("why"), "wrote": False}
    if dry:
        return out

    # ДВА РАЗНЫХ СРОКА ГОДНОСТИ, и путать их нельзя. То, за что УЖЕ ЗАПЛАЧЕНО мосту (засев,
    # реестр, наблюдение), кладётся в состояние ВСЕГДА — иначе тихая очередь платила бы дорогой
    # засев каждые десять минут заново. А отпечаток «что опубликовано» ставится ТОЛЬКО по факту
    # удавшейся записи: он утверждает про ДОКУМЕНТ, а не про наши знания.
    new = dict(prev)
    new.update({"gone": gone[:64], "closed_at": closed_at, "since": since})
    if q.get("ok"):
        new["open"] = queue_state.open_map(rows)
    st["qstate"] = new
    if not v.get("write"):
        return out
    if not write_queue_state(v.get("text")):
        return out                       # отпечаток НЕ помечаем: скажем на следующем прогоне
    out["wrote"] = True
    new["fp"] = v.get("fp")
    if v.get("verified"):                          # отказ не стирает память о верном снимке
        new["at"] = now                            # время ПОСЛЕДНЕГО ВЕРНОГО снимка
        new["text"] = v.get("text")
    return out


def _frozen_client():
    """Заморожен ли КЛИЕНТСКИЙ контур. Та же ручка, что у `revizor_route`/devbot: одно решение
    владельца обязано читаться одним способом, иначе у него будет две правды."""
    try:
        import revizor_route
        return "client" in revizor_route.frozen_keys(os.environ.get("CONTOUR_FREEZE", "client"))
    except Exception:                                                # noqa: BLE001
        return True            # не смогли спросить → считаем замороженным (как сегодня в проде)


def _owner_defer():
    """Сколько эпизод обязан прожить, прежде чем тяжёлое дойдёт до владельца (сек)."""
    return expectations.limit_env(OWNER_DEFER_ENV, OWNER_DEFER_DEFAULT, os.environ)


# Поля вердикта, которые переживают эпизод в состоянии: по ним строится ЧИСЛО журнальной строки.
# Числа остаются теми, что были В МОМЕНТ ОБНАРУЖЕНИЯ, — это сказано в самой строке словом
# «начало», и подменять их свежими при закрытии значило бы переписать историю задним числом.
_KEEP_V = ("kind", "key", "id", "sha", "dt", "limit", "free", "age")


def _trim_v(v):
    return {k: (v or {}).get(k) for k in _KEEP_V if (v or {}).get(k) is not None}


def keep_number(rec, v):
    """ЧИСЛО ЗАМЕРА ЗАМОРАЖИВАЕТСЯ ПРИ ОБНАРУЖЕНИИ — ГОТОВОЙ СТРОКОЙ, а не набором полей.

    ПОВОД (живая запись 13.08 13:46, единственная запись слоя в мозге на тот час): «ОЖИДАНИЕ О5 ·
    мост отвечает дольше отведённого времени · опрос очереди 0 с при отведённых 0 с · длилось
    20 мин». Длительность цела, а замер и порог обнулены — при том, что числа БЫЛИ измерены и
    лежат в доказательстве того же эпизода (`reports/2026-08-13/expect-o5s-1786626993.md`:
    «опрос очереди занял 127 с при отведённых 120 с»). Эпизод открылся в 13:26 одной редакцией
    рук, а закрылся в 13:47 другой — и на переносе оба числа исчезли разом.

    ПОЧЕМУ ИМЕННО ГОТОВАЯ СТРОКА. К закрытию вердикта уже нет: эпизод закрылся ровно потому, что
    нарушения в фактах больше нет. Значит число обязано пережить эпизод внутри его записи, а
    единственная дорога туда — `_trim_v`, белый список ИМЁН полей. Список угадывает задним числом:
    запись прежней редакции его не проходила вовсе, а вид, чьё поле в список не внесли (завтрашнее
    О6), не пройдёт и завтра — и оба числа пропадут ОДНОВРЕМЕННО, как пропали здесь. Готовая
    строка снимается там, где вердикт ЦЕЛЫЙ, и списком не режется.

    ЗАМЕР НЕ ПЕРЕПИСЫВАЕТСЯ ПОЗЖЕ: строка журнала говорит «начало», и число принадлежит ему же —
    тому такту, чьи улики легли в доказательство. Числа нет (вид их не несёт / запись легаси) →
    возвращаем "", и `line()` честно скажет «неизвестно», а не ноль: это принятый контракт."""
    have = str((rec or {}).get("num") or "").strip()
    if have:
        return have
    try:
        num = expect_journal.number(v)
    except Exception:                                                # noqa: BLE001
        return ""
    return "" if (not num or num == expect_journal.NO_NUMBER) else num


def close_detail(key, facts):
    """Чем закрытие эпизода объясняет само себя. Для О4 это ДОСЛОВНАЯ первая строка вернувшегося
    ПК: он единственный знает, почему молчал («🛌 ПК СПАЛ 51 м 43 с — весь контур стоял»), и
    пересказывать это своими словами значило бы потерять диагноз (проект §5.3)."""
    try:
        if str(key).startswith("o4|"):
            line = ((facts or {}).get("pc") or {}).get("line")
            return ("ПК о себе говорит так: «%s»" % str(line)[:150]) if line else ""
        if str(key).startswith("o5"):
            dt = ((facts or {}).get("bridge") or {}).get("dt")
            return "проба прошла за %s" % expectations._secs(dt) if dt is not None else ""
    except Exception:                                                # noqa: BLE001
        return ""
    return ""


def enqueue_escalation(v):
    """Вторая реакция: задача в очередь. → id | 0.

    Ставится ТОЛЬКО при can_task (правило 4.2) — проверку дублируем здесь, потому что руки не
    вправе полагаться на то, что вызывающий её сделал."""
    text = expectations.task_text(v)
    if not text:
        return 0
    try:
        from bridge_client import BridgeClient
        r = BridgeClient(timeout=45).enqueue_task(TASK_FROM, text, lane="vps",
                                                  dedup_key="expect:" + str(v.get("key")))
        return int(r.get("id") or 0) if r.get("ok") else 0
    except Exception as e:                                           # noqa: BLE001
        print("задача-эскалация не встала (%s)" % e, file=sys.stderr)
        return 0


def _bump_quiet(st, key):
    """Счётчик эпизодов, которые закрылись сами раньше отсрочки. Владельцу их не показывали —
    тем важнее, чтобы система их не забыла: число живёт в состоянии, имена — последними восемью."""
    q = st.get("quiet") if isinstance(st.get("quiet"), dict) else {}
    q["n"] = int(q.get("n") or 0) + 1
    q["last"] = ([str(key)] + [k for k in (q.get("last") or []) if k != str(key)])[:8]
    return q


def run(dry=False, now=None):
    """Один прогон яруса 2. → словарь итога (для теста, лога и ручной проверки)."""
    now = time.time() if now is None else float(now)
    cfg = expectations.config(os.environ)
    # Состояние читается ДО фактов: у моста и ПК факт составной — сегодняшняя проба плюс история
    # прошлых прогонов (см. snapshot). Без него оба честно скажут «неизвестно».
    st = load_state()
    facts = snapshot(now, st, cfg)
    # Счётчики чистого ожидания копятся ДО вердикта: О1 судит по ним, а не по возрасту строки.
    update_waits(st, facts, now)
    verdicts = expectations.verdict(facts, cfg)
    # Успех пробы запоминается ПОСЛЕ вердикта — иначе он обнулил бы возраст отказа, по которому
    # вердикт и выносится.
    remember_bridge(st, facts, now, cfg)
    pc = facts.get("pc")
    if isinstance(pc, dict) and pc.get("ok"):
        st["pc"] = {k: pc.get(k) for k in ("ok", "fetched", "last", "line", "n")}
    open_eps = dict(st.get("open") or {})
    out = {"verdicts": len(verdicts), "notes": [], "tasks": [], "closed": [],
           # ОТСРОЧЕННЫЕ И ПОГАШЕННЫЕ ОТСРОЧКОЙ — В СЧЁТЕ, А НЕ В НЕБЫТИИ: владельцу их не
           # показывали, но итог прогона уходит в журнал таймера, и там они названы числом.
           "held": [], "quiet": [], "journal": [], "dry": bool(dry)}
    brain = _to_brain()
    frozen = _frozen_client()
    owner_defer = _owner_defer()

    # 1. ЗАКРЫТИЕ ЭПИЗОДОВ — первым: закончившееся обязано быть названо раньше начавшегося.
    for key in expectations.closures(facts, cfg, list(open_eps.keys())):
        rec = open_eps.get(key) or {}
        detail = close_detail(key, facts)
        if dry:
            out["closed"].append(key)
            open_eps.pop(key, None)
            continue
        # 1а. В МОЗГ — ВСЕГДА И ПРО ЛЮБОЙ эпизод, включая тот, о котором владелец не слышал:
        #     «не пошло владельцу» не значит «не было». Это и есть одна строка на эпизод —
        #     с началом, концом и длительностью, которая копилась в состоянии.
        #     ПОМЕТКА СТАВИТСЯ СРАЗУ ПОСЛЕ ЗАПИСИ и переживает прогон: иначе провал СЛЕДУЮЩЕГО
        #     шага (заметка владельцу) вернул бы нас сюда и положил в журнал вторую строку об
        #     одном эпизоде — ровно то, что правило «одна строка на эпизод» и запрещает.
        if brain and not rec.get("closed_j"):
            first = float(rec.get("first") or now)
            v = rec.get("v") or {"kind": rec.get("kind"), "key": key}
            if not write_journal(expect_journal.line(v, LANE, first, now, "закрыт",
                                                     rec.get("ticks"), detail,
                                                     num=rec.get("num"))):
                continue                       # не записалось → эпизод жив, скажем на следующем
            rec["closed_j"] = 1
            open_eps[key] = rec
            out["journal"].append(key)
        elif not brain and not rec.get("noted"):
            # ОТКАТ (EXPECT_TO_BRAIN=0): прежняя тишина о том, чего не объявляли.
            open_eps.pop(key, None)
            out["quiet"].append(key)
            st["quiet"] = _bump_quiet(st, key)
            continue
        # 1б. ВЛАДЕЛЬЦУ — только если ему объявляли начало: закрытие того, о чём он не слышал,
        #     было бы той же заметкой, только задом наперёд.
        if rec.get("noted") and not send_note(expectations.render_close(key, LANE, detail)):
            continue
        if not rec.get("noted"):
            out["quiet"].append(key)
            st["quiet"] = _bump_quiet(st, key)
        else:
            out["closed"].append(key)
        open_eps.pop(key, None)

    # 2. НАРУШЕНИЯ.
    task_on = str(os.environ.get("EXPECT_TASK") or "1").strip() not in ("0", "no", "off")
    for v in verdicts:
        key = str(v.get("key"))
        rec = open_eps.get(key) or {}
        first = float(rec.get("first") or now)
        # ДЛИТЕЛЬНОСТЬ ОБНОВЛЯЕТСЯ КАЖДЫЙ ТИК, А НА ДИСК НЕ ХОДИТ: журнал получит ОДНУ строку с
        # готовым числом при закрытии. Вес считается ОДИН раз — при первом обнаружении, пока
        # факты под рукой (у закрытия их уже не будет: эпизод закрылся именно потому, что
        # нарушения в фактах больше нет).
        if rec:
            is_heavy, why = bool(rec.get("heavy")), str(rec.get("why") or "")
        else:
            is_heavy, why = expect_journal.heavy(v, facts, frozen)
        # ЧИСЛО СНИМАЕТСЯ ЗДЕСЬ, ПОКА ВЕРДИКТ ЦЕЛЫЙ, и дальше не переписывается (см. keep_number).
        # Поля `v` при этом СЛИВАЮТСЯ, а не замещаются: замер, однажды измеренный, не должен
        # пропадать оттого, что следующий такт принёс вердикт беднее прежнего.
        num = keep_number(rec, v)
        rec.update({"first": first, "last": now, "ticks": int(rec.get("ticks") or 0) + 1,
                    "kind": v.get("kind"), "v": dict(rec.get("v") or {}, **_trim_v(v)),
                    "heavy": bool(is_heavy), "why": why})
        if num:
            rec["num"] = num
        rec.setdefault("noted", 0)
        rec.setdefault("task", 0)
        open_eps[key] = rec
        held = max(0.0, now - first)
        # Отсрочка адреса и отсрочка самого О3 (окно правки) складываются по СИЛЬНЕЙШЕЙ: обе
        # говорят «рано», и уступить надо той, что говорит это дольше.
        defer = max(owner_defer if brain else 0.0, float(v.get("defer") or 0.0))
        if not rec.get("noted"):                           # ВЛАДЕЛЬЦУ ЕЩЁ НЕ СКАЗАНО
            if brain:
                addr, addr_why = expect_journal.address(v, facts, held, defer, frozen)
            else:                                          # ОТКАТ: прежний путь байт-в-байт
                addr = (expect_journal.BRAIN_AND_OWNER if held >= defer
                        else expect_journal.BRAIN)
                addr_why = "откат EXPECT_TO_BRAIN=0: адрес не судится"
            # СТРОКА «ДЕРЖИТСЯ» — ПЕРЕЖИВШЕМУ ОТСРОЧКУ, БЕЗ ОГЛЯДКИ НА АДРЕС. Эпизод может не
            # закрыться никогда, и тогда закрывающей строки не будет вовсе: без этой в журнале
            # не осталось бы ни слова о самом долгом нарушении. Пишется РОВНО один раз (`held_j`),
            # и одинаково для тяжёлого и лёгкого — в мозг идёт ВСЁ, а адрес решает только, узнает
            # ли о нём вдобавок владелец.
            if brain and held >= defer and not rec.get("held_j") and not dry:
                if write_journal(expect_journal.line(v, LANE, first, now, "держится",
                                                     rec.get("ticks"), addr_why,
                                                     num=rec.get("num"))):
                    rec["held_j"] = 1
                    out["journal"].append(key)
            if addr == expect_journal.BRAIN_AND_OWNER:
                if dry:
                    out["notes"].append(key)
                    rec["noted"] = now
                else:
                    shown = dict(v)
                    if held > 0:
                        shown["held"] = held               # заметка САМА скажет, сколько её ждали
                    proof = write_proof(shown, facts, now)  # доказательство ДО канала: улики летучи
                    if send_note(expectations.render(shown, LANE)):
                        rec["noted"] = now
                        rec["proof"] = proof
                        out["notes"].append(key)
                    # не ушла → не помечаем, скажем на следующем прогоне
            else:
                # ВЛАДЕЛЬЦУ НЕ ИДЁТ. Эпизод жив, длительность копится; в журнал он попадёт при
                # закрытии одной строкой (а если переживёт отсрочку — строкой «держится» выше).
                out["held"].append(key)
        # ЗАДАЧА-ЭСКАЛАЦИЯ ЖИВЁТ СВОИМ ПРАВИЛОМ И ОТ АДРЕСА ЗАМЕТКИ НЕ ЗАВИСИТ. До правки она
        # стояла за проверкой «владельцу уже сказано», и это было БЕЗ РАЗНИЦЫ (заметка уходила
        # сразу, значит `noted` стоял всегда). Теперь большинство эпизодов владельцу не идёт —
        # оставить её там значило бы молча отнять реакцию, а менялся только АДРЕС.
        if rec.get("task") or not task_on or not v.get("can_task"):
            continue
        if held < float(cfg.get("hold") or 0):
            continue                                       # ещё не «держится»
        if _tasks_today(st, now) + len(out["tasks"]) >= TASK_CAP_DAY:
            continue                                       # потолок суток — страховка от петли
        if dry:
            out["tasks"].append({"key": key, "id": -1})
            continue
        tid = enqueue_escalation(v)
        if not tid:
            continue
        rec["task"] = tid
        open_eps[key] = rec
        st.setdefault("tasks", []).append({"ts": now, "id": tid, "key": key})
        out["tasks"].append({"key": key, "id": tid})
        said = ("🔔 нарушение держится · %s · поставил задачу %s на разбор причины (read-only; "
                "живые процессы и данные не трогаются) · %s"
                % (LANE, tid, expectations.render(v, LANE).split(" · ", 2)[-1]))
        # Владельцу — только если ему объявляли сам эпизод: иначе он получил бы сообщение о
        # задаче по нарушению, о котором не слышал. О самой задаче он и так узнает её отчётом
        # в 328, когда она отработает, — вторая дверь тут лишняя.
        if rec.get("noted"):
            send_note(said)
        elif brain:
            write_journal("%s %s · %s" % (expect_journal.TAG,
                                          expect_journal.SHORT.get(str(v.get("kind")), "?"), said))

    # 3. СЛЕПОК СОСТОЯНИЯ ОЧЕРЕДИ — ПОСЛЕДНИМ и вне вердиктов: он не про нарушения, а про то,
    #    что Штаб обязан видеть ВСЕГДА. Своей ручкой и своим fail-safe; упади он — ожидания
    #    уже отработали.
    try:
        out["qstate"] = queue_state_step(st, facts, now, dry)
    except Exception as e:                                           # noqa: BLE001
        print("слепок очереди не снят (%s) — документ остался прежним" % str(e)[:160],
              file=sys.stderr)
        out["qstate"] = {"write": False, "why": "сбой шага: %s" % str(e)[:80], "wrote": False}

    if not dry:
        st["open"] = dict(list(open_eps.items())[-STATE_KEEP:])
        st["tasks"] = (st.get("tasks") or [])[-STATE_KEEP:]
        save_state(st)
    return out


def main():
    dry = "--dry" in sys.argv[1:]
    try:
        out = run(dry=dry)
    except Exception as e:                                           # noqa: BLE001
        print("прогон не удался (%s) — вердикта нет" % e, file=sys.stderr)
        return 0                                           # молчание не считается сбоем таймера
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
