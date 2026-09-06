#!/usr/bin/env python3
"""ДЕТЕКТОР ДРЕЙФА ПРОДА — живой процесс отстал от origin/main (06.08.2026).

ОСНОВАНИЕ (разбор выкатки, цель 355): автоматики выкатки нет вовсе — демон 49 % недели шёл
позади git, splinter 39 %, самый длинный разрыв 34,4 часа закрылся ПОСТОРОННИМ апгрейдом
пакетов, а не решением человека. Класс «фикс в git ≠ фикс в проде» ловится в этом репозитории
четвёртый раз (карточка 110 умерла старым кодом через 16 минут после фикса; дважды подряд
оговорка о рестарте писалась по привычке — один раз с завышением готовности, один раз с
занижением, коммиты e6fb0b5 и 7672e98). Общего у всех случаев одно: РАЗРЫВ НИКТО НЕ ВИДЕЛ.

РЕШЕНИЕ ВЛАДЕЛЬЦА: «детектор без рестарта». Система замечает разрыв и ГОВОРИТ о нём — заметкой
в ленту 829, без кнопок, без номера, без слова «да». Автоматики рестарта живых процессов нет
ни в каком виде, и это здесь не обещание, а устройство: см. «ЧЕГО ЭТОТ МОДУЛЬ НЕ УМЕЕТ».

────────────────────────────────────────────────────────────────────────────────────────────
ЧТО СЧИТАЕТСЯ ОТСТАВАНИЕМ — ФАКТ В ПАМЯТИ ПРОЦЕССА, А НЕ ВОЗРАСТ ПРОЦЕССА

Наивное определение («процесс стартовал раньше, чем лёг коммит → он позади») ЛОЖНО, и ложно
ровно в рабочем цикле этого репозитория: правку сначала кладут на диск, потом перезапускают
сервис, чтобы её проверить, и только потом коммитят. Коммит при этом моложе старта, а код в
памяти — уже новый. Наивный детектор кричал бы на КАЖДЫЙ такой заход.

Поэтому отставание требует ДВУХ независимых свидетелей, и первый из них — о памяти:

  W1 — СВИДЕТЕЛЬ ПАМЯТИ: `mtime(F) > старт процесса`. Файл на диске переписан ПОСЛЕ того, как
       процесс его прочитал, — значит байты, лежащие сейчас на диске, процесс не читал.
       Это факт об идентичности содержимого, а не о возрасте: строгий порядок двух событий
       («процесс прочитал» ↔ «файл записан»), а не длина отрезка между ними.

  W2 — СВИДЕТЕЛЬ СОДЕРЖИМОГО: в origin/main есть коммит, который ИЗМЕНИЛ F и доехал ПОСЛЕ
       старта. Он убивает вторую половину ложных срабатываний — `touch`, checkout того же
       содержимого, любую перезапись байт-в-байт (W1 их не отличает, git отличает).

Оба вместе: процесс держит в памяти НЕ ту версию F, что лежит в origin/main. Возраст разрыва
считается от ПЕРВОГО неподхваченного коммита, а не от старта процесса, — «сколько времени прод
живёт с непринятой правкой».

КАКИЕ ФАЙЛЫ ВООБЩЕ МОГУТ ДРЕЙФОВАТЬ. Только те, что процесс держит В ПАМЯТИ, — замыкание
импортов от точки входа (ast, первая сторона; сторонние и стандартные модули не наши). Отсюда
даром получается граница класса, которую в CLAUDE.md пришлось выписывать словами дважды:
`pretool_guard.py` и `posttool_feed.py` — ХУКИ, отдельный подпроцесс на каждый вызов; ни демон,
ни splinter их не импортируют, значит в замыкание они не попадают и дрейфовать не могут по
устройству. Правка CLAUDE.md, docs/, tests/ — тоже не код в памяти: молчим. Ровно это и просил
владелец словами «по факту в памяти процесса, а не по времени старта».

ЧЕСТНЫЙ ПРЕДЕЛ ЗАМЫКАНИЯ: оно СТАТИЧЕСКОЕ. Модуль, импортируемый лениво (внутри функции) и ещё
ни разу не тронутый, будет назван позади, хотя в памяти его пока нет; направление ошибки —
лишняя строка в заметке, не молчание. Обратная сторона: коммит из ОТДЕЛЬНОГО рабочего дерева
(`git worktree`, приём «прогон ДО правки») origin/main двигает, а mtime в живой копии не трогает
— W1 промолчит, и разрыв мы не назовём. Это молчание, а не ложь: оно названо здесь.

────────────────────────────────────────────────────────────────────────────────────────────
ПОРОГ — DRIFT_HOURS (.env), дефолт DEFAULT_HOURS часов; владелец: «разрыв в минуты — шум, в
часы — сигнал». ЗАМЕР на живой истории (журнал systemd = когда сервис стартовал, origin/main =
когда доехал коммит и что он изменил, замыкание считал ЭТОТ модуль; окно 7 суток 30.07–06.08,
62 коммита). Замер ВОСПРОИЗВЁЛ ОСНОВАНИЕ независимо: демон 81.9 ч позади из 168 (49 %),
splinter 65.4 ч (39 %) — те же числа, что в разборе цели 355. Эпизодов (жизнь экземпляра, в
которую доехал неподхваченный коммит) — 24: у демона 17, у splinter 7. Сколько заметок:
    порог 0.5 ч → 12 за 7 суток (1.71/сут)      порог  4 ч → 7 (1.00/сут)
    порог   1 ч → 11 (1.57/сут)                 порог  6 ч → 7 (1.00/сут)
    порог   2 ч →  8 (1.14/сут)                 порог 12 ч → 4 (0.57/сут)
    порог   3 ч →  7 (1.00/сут)                 порог 24 ч → 3 (0.43/сут)
Потолок владельца — 10 заметок в сутки; мы на порядок ниже ПРИ ЛЮБОМ пороге, включая
получасовой. Значит порог выбран НЕ по потолку шума, а по смыслу и по форме распределения:
длительности эпизодов идут 1 ч 44 м · 1 ч 53 м · 1 ч 53 м · 2 ч 30 м — ПУСТО — 6 ч 09 м ·
6 ч 46 м · 8 ч 03 м · 21 ч 06 м · 24 ч 00 м · 34 ч · 35 ч. Между 2 ч 30 м и 6 ч 09 м нет ни
одного эпизода, поэтому ЛЮБОЙ порог из этого промежутка даёт ровно 7 заметок; 4 часа стоит в
его середине — выбор устойчив к ±1,5 ч в обе стороны. Смысл того же числа: 4 часа дольше
любого рабочего захода (TASK_TIMEOUT_DEV = 45 мин) и дольше цепи декомпозера, то есть это
«правку положили и забыли», а не «правку кладут прямо сейчас». Всё, что порог отрезает
(≤ 2 ч 30 м), закрылось само следующим рестартом.

ОДНА ЗАМЕТКА НА ЭПИЗОД. Ключ дедупа — (юнит · старт процесса · первый неподхваченный коммит).
Новые коммиты поверх уже названного разрыва первого коммита не меняют → второй заметки нет.
Рестарт меняет старт → новый эпизод. Повторов-напоминаний НЕТ намеренно: канал информационный,
а «то же самое каждые N часов» — ровно тот шум, за который 05.08 отозвали класс push.

────────────────────────────────────────────────────────────────────────────────────────────
ЧЕГО ЭТОТ МОДУЛЬ НЕ УМЕЕТ — И ЭТО УСТРОЙСТВО, А НЕ ОБЕЩАНИЕ

  • он не может ничего ЗАПУСТИТЬ и ничего ПЕРЕЗАПУСТИТЬ: единственная внешняя команда —
    `git`, и только читающая подкоманда из словаря GIT_READ (сверяется в _git, а не в
    комментарии). Слов, которыми в этой системе перезапускают процессы, в его коде нет вовсе;
  • он не может ничего ЗАПИСАТЬ: файлы открываются только на чтение, каталогов не создаёт,
    состояние дедупа держат РУКИ (orchestrator_daemon), а не он;
  • он не может ничего ОТПРАВИТЬ: ни моста, ни сети, ни notify — текст заметки он возвращает
    строкой, отдаёт её в канал демон.
Стережёт это инвариант PROD_DRIFT_READONLY в invariants_check.py (ast-разбор, в гейте), тем же
приёмом, что CARD_DUTY_PURE и CURATOR_EVENT_PURE. Честный предел названного словаря: `git` с
ПРОИЗВОЛЬНЫМИ аргументами исполнить чужое теоретически может (алиасы, `-c`), поэтому аргументы
здесь — литералы модуля, а подкоманда сверяется словарём на каждом вызове.

FAIL-SAFE ВЕЗДЕ — В СТОРОНУ МОЛЧАНИЯ: нет процесса, нет /proc, git недоступен, ref origin/main
отсутствует, файл не читается, замыкание не разобралось, любое исключение → пустой вердикт,
то есть поведение системы байт-в-байт как без детектора. Заметка не даёт прав и ничего не
меняет, поэтому её отсутствие не может ничего сломать; её ошибочное появление стоит одной
лишней строки в ленте.

ОТКАТ: `DRIFT_HOURS=0` в .env + рестарт демона → ветка мертва целиком (вердикт пуст ДО сбора
фактов, git не зовётся ни разу). Парсер порога намеренно СВОЙ, а не `_env_int` демона: тот
возвращает дефолт на любом значении ≤ 0, то есть выключить им ветку нельзя.
"""
import ast
import os
import subprocess
import time

REPO = os.path.dirname(os.path.abspath(__file__))

# НАБЛЮДАЕМЫЕ: (юнит systemd, точка входа). Двое названы разбором цели 355; третий, `wa-webhook`,
# внесён 06.09.2026 РЕШЕНИЕМ ВЛАДЕЛЬЦА (ТЗ WA-возврата: «добавить wa-webhook в наблюдаемые юниты»).
#
# ПРЕЖНЯЯ СТРОКА «`wa-webhook` сюда НЕ входит намеренно: список без реакции владельца растёт в
# шум» УСТАРЕЛА — и устарела она по своей же логике, а не вопреки ей: условием стояла РЕАКЦИЯ,
# и в тот же день она заведена (`health.build_report` вносит отказ вебхука в `problems`, отчего
# сводка краснеет и уходит пуш; до 06.09.2026 отказ печатался в тело отчёта и не будил никого).
#
# ЧТО ИМЕННО ЭТО ДОБАВЛЯЕТ, а что нет: список читают ДВОЕ — сам детектор дрейфа и факты О3
# (`expectations_run.delivery_facts`). Оба судят ОДИН вопрос: «живой процесс читал байты этого
# коммита?» — то есть класс «фикс в git ≠ фикс в проде», ровно тот, которому wa_webhook.py
# подвержен (код живёт в памяти процесса, доставка = перезапуск юнита). ЖИВОСТЬ вебхука здесь
# по-прежнему НЕ судится: её мерит `health.check_wa_webhook` настоящим рукопожатием и чинит
# вотчдогом, и второго механизма на тот же факт мы не заводим — это прямой запрет рамки.
#
# ЦЕНА ШУМА УЗКАЯ ПО ПОСТРОЕНИЮ: замыкание импортов `wa_webhook.py` — стандартная библиотека и
# ничего из репозитория, поэтому сигнал рождается РОВНО когда правят сам этот файл и не
# перезапускают юнит.
WATCHED = (("orchestrator-daemon", "orchestrator_daemon.py"),
           ("splinter", "bot.py"),
           ("wa-webhook", "wa_webhook.py"))

# СЛОВАРЬ GIT: только читающие подкоманды. Сверяется на КАЖДОМ вызове (_git), а не в докстринге.
GIT_READ = frozenset(("log", "rev-parse"))
GIT_TIMEOUT = 20

PROC = "/proc"                  # подменяется тестом (фальшивое дерево процессов)
HOURS_ENV = "DRIFT_HOURS"
DEFAULT_HOURS = 4.0             # обоснование числом — в шапке (ЗАМЕР)

_REC = "\x1e"                   # разделитель записей git log
_FLD = "\x1f"                   # разделитель полей внутри записи


def hours_env(env=None):
    """Порог в часах. Пусто/мусор → DEFAULT_HOURS; 0 → ветка мертва (откат); < 0 → дефолт.
    НОЛЬ ЗДЕСЬ ЗНАЧИМ, поэтому парсер свой: `_env_int` демона на «0» отдаёт дефолт, и объявленный
    таким способом откат не работал бы вовсе (проверено на EVENT_WINDOW — см. остатки артефакта)."""
    raw = str(((env if env is not None else os.environ).get(HOURS_ENV) or "")).strip()
    if not raw:
        return DEFAULT_HOURS
    try:
        v = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return DEFAULT_HOURS
    return v if v >= 0 else DEFAULT_HOURS


# ═══════════════════════════ ЧТЕНИЕ МИРА (и ничего кроме чтения) ═══════════════════════════
def _read(path):
    """Текст файла или None. Единственная форма работы с ФС в этом модуле — чтение."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _git(args, cwd=None):
    """Читающий git → stdout | None. Подкоманда вне GIT_READ не исполняется ВООБЩЕ."""
    if not args or args[0] not in GIT_READ:
        return None
    try:
        p = subprocess.run(["git"] + list(args), cwd=cwd or REPO,
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except Exception:
        return None
    return p.stdout if p.returncode == 0 else None


def _imports(path):
    """Имена модулей первого уровня, импортируемые файлом. ast, а не подстрока: слово в
    комментарии и в строке импортом не является (то же правило исполняющей позиции, что у гарда).
    Нечитаемый/несобирающийся файл → пусто (fail-safe в сторону молчания)."""
    src = _read(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out.extend(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            if not n.level:                      # относительные импорты: пакетов у нас нет
                out.append((n.module or "").split(".")[0])
    return [m for m in out if m]


def closure(entry, repo=None):
    """Файлы репозитория, которые процесс держит В ПАМЯТИ: точка входа + транзитивные импорты
    первой стороны. Обход берёт импорты ЛЮБОГО уровня вложенности (демон импортирует notify
    внутри функции — в памяти он окажется так же прочно, как импортированный сверху).
    Не наш модуль (стандартный/сторонний) в репозитории не лежит и в замыкание не попадает."""
    repo = repo or REPO
    start = os.path.basename(str(entry or ""))
    if not start or not os.path.isfile(os.path.join(repo, start)):
        return set()
    seen, queue = set(), [start]
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        for mod in _imports(os.path.join(repo, rel)):
            cand = mod + ".py"
            if cand not in seen and os.path.isfile(os.path.join(repo, cand)):
                queue.append(cand)
    return seen


def _boot(proc=None):
    """Момент загрузки машины (эпоха) из /proc/stat — нужен, чтобы перевести тики старта
    процесса в абсолютное время. Нет строки btime → None."""
    txt = _read(os.path.join(proc or PROC, "stat"))
    for line in (txt or "").splitlines():
        if line.startswith("btime "):
            try:
                return float(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def started_at(pid, proc=None, boot=None):
    """Момент старта процесса (эпоха) по /proc/<pid>/stat, поле 22 (тики от загрузки).
    Имя команды в поле 2 может содержать пробелы и скобки — поэтому режем по ПОСЛЕДНЕЙ «)»,
    а не по split() всей строки. Не разобрали → None (процесс просто не будет наблюдаться)."""
    txt = _read(os.path.join(proc or PROC, str(pid), "stat"))
    if not txt or ")" not in txt:
        return None
    tail = txt[txt.rindex(")") + 1:].split()
    if len(tail) < 20:
        return None
    b = _boot(proc) if boot is None else boot
    if not b:
        return None
    try:
        hz = float(os.sysconf("SC_CLK_TCK")) or 100.0
        return b + int(tail[19]) / hz
    except (ValueError, OSError):
        return None


def live(unit, entry, proc=None, repo=None):
    """Живой процесс юнита → {"unit","entry","pid","started"} | None.

    ЮНИТ БЕРЁТСЯ ИЗ /proc/<pid>/cgroup, а не из вывода systemctl: это ЧТЕНИЕ ФАЙЛА, и оно
    авторитетно (ядро, а не команда управления). Точка входа сверяется как ПУТЬ, целиком:
    длинный аргумент, внутри которого лишь УПОМЯНУТО имя файла (текст ТЗ у claude-подпроцесса
    в той же cgroup!), путём не является — та же мысль, что «цитата маркера — не заявление»."""
    proc, repo = proc or PROC, repo or REPO
    base = os.path.basename(str(entry or ""))
    target = os.path.normpath(os.path.join(repo, base))
    boot = _boot(proc)
    try:
        pids = sorted((n for n in os.listdir(proc) if n.isdigit()), key=int)
    except OSError:
        return None
    for pid in pids:
        cg = _read(os.path.join(proc, pid, "cgroup")) or ""
        if (unit + ".service") not in cg:
            continue
        raw = _read(os.path.join(proc, pid, "cmdline")) or ""
        for a in raw.split("\x00"):
            a = a.strip()
            if not a or os.path.basename(a) != base:
                continue
            path = a if os.path.isabs(a) else os.path.join(repo, a)
            if os.path.normpath(path) != target:
                continue
            st = started_at(pid, proc, boot)
            if st is None:
                continue
            return {"unit": unit, "entry": base, "pid": int(pid), "started": st}
    return None


def commits_since(ts, repo=None):
    """Коммиты origin/main, доехавшие ПОСЛЕ ts, каждый со списком ИЗМЕНЁННЫХ им файлов.
    Ref нет / git недоступен / любой сбой → пусто, то есть W2 не подтверждён и мы молчим."""
    since = time.strftime("%Y-%m-%d %H:%M:%S +0000", time.gmtime(max(0.0, float(ts))))
    out = _git(["log", "origin/main", "--since=" + since, "--name-only",
                "--format=" + _REC + "%H" + _FLD + "%ct" + _FLD + "%s"], cwd=repo)
    if not out:
        return []
    recs = []
    for chunk in out.split(_REC):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        head, _, rest = chunk.partition("\n")
        parts = head.split(_FLD)
        if len(parts) < 3:
            continue
        try:
            ct = int(parts[1])
        except ValueError:
            continue
        recs.append({"sha": parts[0][:7], "ct": ct, "subject": parts[2],
                     "files": [ln.strip() for ln in rest.split("\n") if ln.strip()]})
    return recs


def snapshot(now=None, proc=None, repo=None, watched=None):
    """ФАКТЫ и ни одного решения: кто живой, когда стартовал, что лежит в его замыкании, какие
    коммиты доехали после старта. Порога здесь нет — его применяет verdict()."""
    repo = repo or REPO
    procs = []
    for unit, entry in (watched or WATCHED):
        try:
            p = live(unit, entry, proc=proc, repo=repo)
        except Exception:
            p = None
        if not p:
            continue                    # процесса нет — о мёртвом сервисе говорит health, не мы
        files = {}
        try:
            for rel in sorted(closure(entry, repo)):
                try:
                    files[rel] = os.stat(os.path.join(repo, rel)).st_mtime
                except OSError:
                    continue
        except Exception:
            files = {}
        p["files"] = files
        try:
            p["commits"] = commits_since(p["started"], repo)
        except Exception:
            p["commits"] = []
        procs.append(p)
    return {"now": float(now if now is not None else time.time()), "procs": procs}


# ═══════════════════════════ РЕШЕНИЕ: ЧИСТАЯ ФУНКЦИЯ ФАКТОВ ═══════════════════════════════
def verdict(facts, hours):
    """ФАКТЫ → список заметок. Ни одного обращения к миру: ни ФС, ни git, ни времени — всё
    приходит в `facts`. Поэтому решение проверяемо мокнутыми фактами, а не живой машиной.

    hours ≤ 0 → пусто (откат). Порядок проверки: W1 (память) → W2 (содержимое) → порог."""
    out = []
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return out
    if hours <= 0 or not isinstance(facts, dict):
        return out
    now = float(facts.get("now") or 0.0)
    for p in (facts.get("procs") or []):
        started = float(p.get("started") or 0.0)
        if started <= 0:
            continue
        # W1 — СВИДЕТЕЛЬ ПАМЯТИ: эти файлы переписаны на диске после того, как процесс их прочитал.
        rewritten = {rel for rel, mt in (p.get("files") or {}).items()
                     if mt and float(mt) > started}
        if not rewritten:
            continue
        # W2 — СВИДЕТЕЛЬ СОДЕРЖИМОГО: изменение доехало до origin/main коммитом после старта.
        behind, first = set(), None
        for c in (p.get("commits") or []):
            ct = float(c.get("ct") or 0.0)
            if ct <= started:
                continue
            hit = [f for f in (c.get("files") or []) if f in rewritten]
            if not hit:
                continue
            behind.update(hit)
            if first is None or ct < float(first.get("ct") or 0.0):
                first = c
        if not behind or first is None:
            continue
        age = now - float(first.get("ct") or 0.0)
        if age < hours * 3600.0:
            continue                     # разрыв в минуты — шум; порог обоснован в шапке
        out.append({
            "unit": p.get("unit") or "?",
            "pid": p.get("pid") or 0,
            "started": started,
            "age": age,
            "files": sorted(behind),
            "sha": str(first.get("sha") or ""),
            "subject": str(first.get("subject") or ""),
            "ct": float(first.get("ct") or 0.0),
            "key": "%s|%d|%s" % (p.get("unit") or "?", int(started), first.get("sha") or ""),
        })
    return out


# ═══════════════════════════ ФОРМА ЗАМЕТКИ ════════════════════════════════════════════════
# Одна строка ленты: кнопок нет, номера карточки нет, слова «да» нет — отвечать не на что и
# нечем. Первый токен «🔔» — общий с лентой фазы 1, чтобы в теме 829 заметки читались одним
# семейством; сам класс назван словами, а не op-кодом (op-код — язык карточек, не ленты).
NOTE_HEAD = "🔔 прод отстал от origin/main"
MAX_FILES = 3
MAX_SUBJECT = 44


def human_age(sec):
    """«48 мин» / «5 ч 12 мин» / «1 сут 10 ч». Ноль дробей: заметку читают с телефона."""
    s = max(0, int(sec or 0))
    d, rest = divmod(s, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return "%d сут %d ч" % (d, h)
    if h:
        return "%d ч %d мин" % (h, m)
    return "%d мин" % m


def _stamp(ts):
    return time.strftime("%d.%m %H:%M UTC", time.gmtime(float(ts or 0.0)))


def render(note, lane="VPS"):
    """Текст заметки. Отправляет её ДЕМОН — этот модуль в канал не ходит (см. шапку)."""
    files = list(note.get("files") or [])
    shown = ", ".join(files[:MAX_FILES])
    if len(files) > MAX_FILES:
        shown += " (+%d)" % (len(files) - MAX_FILES)
    subj = str(note.get("subject") or "")
    if len(subj) > MAX_SUBJECT:
        subj = subj[:MAX_SUBJECT - 1] + "…"
    return " · ".join([
        NOTE_HEAD,
        str(lane or "VPS"),
        "%s (PID %s, старт %s)" % (note.get("unit"), note.get("pid"), _stamp(note.get("started"))),
        "в памяти код старше на %s" % human_age(note.get("age")),
        "позади %d файл(ов): %s" % (len(files), shown),
        "с коммита %s «%s»" % (note.get("sha"), subj),
        "рестарта не делаю — это решение владельца",
    ])
