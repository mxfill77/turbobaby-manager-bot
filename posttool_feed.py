#!/usr/bin/env python3
"""ЛЕНТА — канал заметок «третьего состояния». ШАГ 1: провод (03.08). ШАГ 2: СПИСОК (04.08.2026).
СОКРАЩЕНИЕ ШУМА (05.08.2026): класс push ОТОЗВАН владельцем, метка сервиса исправлена — см. ниже.

Основание: docs/artifacts/2026-08-03-third-state-notify-design.md (устройство и список утверждены
владельцем) + docs/artifacts/2026-08-04-feed-list-phase1.md (подключение списка, замер на живом
корпусе, честные пределы) + docs/artifacts/2026-08-05-feed-noise-cut.md (этот заход).

ЗАЧЕМ ВООБЩЕ. У гарда было два состояния: «выполнить молча» и «спросить разрешения». Клетка
«выполнить и СКАЗАТЬ» физически пуста, поэтому значимые изменения мира (рестарт живого сервиса,
отброс рабочего дерева, вынос теста из гейта) проходили молча — доктрина запрещает по ним карточку,
и это верно: разрешения там не нужно. Но из «не спрашивать» система вывела «не говорить».

ПОЧЕМУ ЭТО ЖИВЁТ В PostToolUse, А НЕ В ГАРДЕ. У события `PostToolUse` НЕТ поля `permissionDecision`
вовсе — команда уже выполнена, разрешать нечего. Заметка, живущая в этой фазе, не может выдать
право ФИЗИЧЕСКИ, а не потому что мы аккуратно написали код. Следствия:
  1. `pretool_guard.py` не меняется НИ НА ОДНУ строку — ни один красный класс измениться не может.
     Гард для ленты — БИБЛИОТЕКА РАЗБОРА: мы зовём его чистые ручки (`_del_units`/`_cmd_index`/
     `_base`/`_del_targets`/`is_probe`) и НИ ОДНОЙ его пишущей ветки. Стережёт секция (8) теста
     (ast-разбор этого файла), а не обещание в докстринге.
  2. Заблокированное в ленту не попадает: PostToolUse на невыполненной команде не срабатывает.
     Красное остаётся при своём адресе (инбокс 1160), лента говорит только о случившемся.
  3. Исход известен (`tool_response`) — заметка отличает «сделал» от «упало».
Сверх фазы этот файл держит СОБСТВЕННЫЙ обет: он НЕ ПЕЧАТАЕТ В stdout НИЧЕГО ни при каком входе
(включая мусорный и враждебный) — движок не получает от ленты ни решения, ни контекста, ни текста.

ФОРМА ЗАМЕТКИ: одна строка `🔔 <класс> · <полоса · кто> · <команда ≤120> [· <деталь>] · <исход>`.
Кнопок нет, номера карточки нет, слова «да» нет — отвечать не на что и нечем. МЕТКА ПОЛОСЫ стоит
всегда: в одну тему сходятся обе полосы, а номера задач VPS и ПК идут по РАЗНЫМ счётчикам.

СПИСОК ФАЗЫ 1 — ЧЕТЫРЕ КЛАССА (§3 проекта минус push, редакция владельца 05.08.2026):
  • рестарт/старт/стоп ЖИВОГО БОТА — клиентского (ПК) или внутреннего (splinter): сервис
    работает 24/7, на время рестарта его нет;
  • вынос теста из гейта — защита слабеет молча, а гейт после этого зелёный по МЕНЬШЕМУ набору;
  • отброс рабочего дерева — единственный класс, где НЕзакоммиченная работа исчезает без следа;
  • стирание маркеров гарда — цель в /tmp (по правилу 30.07 это зелёная уборка, и она молчит),
    но стираются СЛЕДЫ красных карточек, которых владелец не закрывал.
НЕ УВЕДОМЛЯЕМ (§4, 35 сообщений в сутки): коммиты, PUSH (см. ниже), записи в мозг, прогоны гейта,
копирование, рестарт ДЕМОНА, уборку своего черновика в /tmp, пробы и красное (адрес красного — 1160).

PUSH ОТОЗВАН ВЛАДЕЛЬЦЕМ 05.08.2026 — и это НЕ отступление, а прописанный ход. §3.3 проекта завёл
условие отзыва класса, §6 — порог «выше 8 заметок в сутки список раздут, режем». Живой факт: за
полчаса три заметки подряд об ОДНОЙ цепочке (задачи 318, 319 дважды), реагировать на них владелец
не может, а коммиты и так видны отчётом в 328. ЗАМЕР (реальный классификатор по транскриптам,
168 ч): 57 заметок, из них push 44 → 8.1 в сутки, из них push 6.3. Без push остаётся 13 (1.9/сут),
то есть ленту режет вчетверо и уводит ниже порога §6. Вместе с классом ушла его деталь
(ветка · коммиты · диапазон · ⚠️ машинерия защиты): она существовала ТОЛЬКО ради push, и её
единственный смысл — «в этом push переписаны предохранители» — теперь виден в отчёте задачи.
Код класса не заморожен, а удалён: живой предикат без канала гниёт молча (история — в git,
разбор — в артефакте 05.08).

ЧТО СУДИМ — ДЕЙСТВИЕ, А НЕ СЛОВО. Разбор идёт по СЕГМЕНТАМ цепи и по ГОЛОВЕ сегмента (тем же
парсером, что у гарда): текст коммита, шаблон поиска и аргумент журнальной команды — один
shlex-токен и головой сегмента не бывают. Поэтому `cclog.py "…нужен systemctl restart wa-webhook…"`
и тело коммита со словами «git reset --hard» заметки не рождают. Голдены — ДОСЛОВНЫЕ команды
транскриптов (tests/test_feed_list.py).

КЛИЕНТСКИЙ БОТ ≠ SPLINTER (поправка метки, 05.08.2026, живой скриншот владельца). Заметка
«рестарт клиентского бота · VPS · systemctl restart splinter» называла внутренний сервис
клиентским. Клиентский контур — `userbot_listen` / `moderation_bot` на ПК; splinter обслуживает
команду и учёт, клиентов он не ведёт. Теперь имя даёт ЦЕЛЬ команды: splinter → «внутреннего
сервиса splinter», ПК-процессы → «клиентского бота». МЕТКОЙ ПОЛОСЫ имя НЕ решается намеренно:
метка отвечает на вопрос «чья задача», а имя класса — «что тронуто», и это разные вопросы. Вывести
имя из полосы было бы к тому же ОПАСНО: у ПК-зеркала `CC_LANE` может быть не выставлен
(`LANE_DEFAULT` = «VPS» — известный остаток ниже), и настоящий клиентский бот назвался бы тогда
внутренним. Цели двух семейств не пересекаются, поэтому имя по цели верно на любой полосе.

ЧЕСТНЫЕ ПРЕДЕЛЫ, названные прямо:
  • ФОРМА ОТВЕТА ИНСТРУМЕНТА ТЕПЕРЬ ИЗМЕРЕНА (шаг 1 писал «проверить нечем»): успех приходит
    словарём {stdout, stderr, interrupted, isImage, noOutputExpected} БЕЗ кода возврата, провал —
    СТРОКОЙ «Error: Exit code N …», отказ движка — строкой «Error: …» без кода. Отсюда: код есть →
    называем код; строка-отказ → заметки НЕТ ВОВСЕ (действия не было, а лента говорит только о
    случившемся); всё прочее → «выполнено» БЕЗ утверждения об успехе.
  • ПК-формы клиентского бота (`userbot_listen` / `moderation_bot` под pc_agent) живым корпусом
    ЭТОЙ полосы не подтверждены — на VPS таких команд нет вовсе; форма взята из карты процессов
    ПК (docs/project_state.md). Ложных срабатываний на VPS они дать не могут (имён нет ни в одной
    команде окна), но и покрытие ПК-полосы этим НЕ доказано — это остаток для зеркала.
  • `wa-webhook` в списке фазы 1 НЕТ намеренно: владелец назвал клиентского бота, транзит WA в
    §3 проекта не входит. Расширять список молча нельзя — у класса без реакции за 14 суток по
    §4 наступает смерть, а не рост.
  • перечень внутренних сервисов — РОВНО `splinter`. Демон и `wa-webhook` в него не входят
    (§4 «не уведомляем»); молча дописывать туда юниты нельзя — это рост списка, а не поправка.
  • копия VPS-репо говорит «VPS» за всякого, кто её запустил; ПК-зеркало обязано сменить
    `LANE_DEFAULT` либо ставить `CC_LANE`, иначе честно соврёт чужой меткой.
"""
import hashlib
import json
import os
import re
import shlex
import sys

PROJECT = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────── КАТАЛОГ СОСТОЯНИЯ (потолок и дедуп) ───────────────────────────
# Зеркало дисциплины гарда (block_dir/PRETOOL_BLOCK_DIR), но каталог ДРУГОЙ — это и есть вторая
# из трёх вещей шага 1. Путь берётся В МОМЕНТ ЗАПИСИ, чтобы подмена работала для хука-подпроцесса.
FEED_SEEN_DIR = "/tmp/cc_feed_seen"            # БОЕВОЙ каталог ленты
FEED_SEEN_TEST_DIR = "/tmp/cc_feed_seen_test"  # безопасное умолчание тест-прогона
SEEN_DIR_ENV = "CC_FEED_SEEN_DIR"              # явная подмена каталога тестом (ставить ВСЕГДА)

CAP = 6            # потолок заметок на задачу; дальше одна строка «молчу» и тишина
SEEN_KEEP = 64     # сколько отпечатков команд держим для дедупа

# ─────────────────────────── МЕТКА ПОЛОСЫ (чья это задача) ───────────────────────────
LANE_ENV = "CC_LANE"       # исполнитель называет полосу сам (демон / pc_orchestrator), если хочет
LANE_DEFAULT = "VPS"       # эта копия файла живёт в репозитории VPS-полосы; ПК-зеркало ставит «ПК»
LANE_MAX = 12              # метка — короткая; длинное значение режем, чтобы не съесть команду


# ═══════════════ РАЗБОР КОМАНДЫ: ГАРД КАК БИБЛИОТЕКА, БЕЗ ЕДИНОЙ ЕГО ПИШУЩЕЙ ВЕТКИ ═════════
def _g():
    """Модуль гарда как БИБЛИОТЕКА разбора. Мы его ЧИТАЕМ и не меняем ни на строку — в этом
    смысл выбора PostToolUse. Зовём ровно чистые ручки; ни `decision`, ни `classify`, ни
    `_guard_write_marker` лента не трогает (те пишут маркер и шлют карточку — заметка не смеет
    ни того, ни другого). Импорт не удался → разбора нет → МОЛЧИМ (см. _units_raw)."""
    try:
        import pretool_guard as g
        return g
    except Exception:
        return None


def _units_raw(cmd):
    """Сегменты цепи в СЫРЫХ токенах (+ тела подстановок и `sh -c`) — ровно тем разбором, что
    судит удаление у гарда. Почему именно он, а не общий `_units`: тот вырезает argv .py-скрипта
    (класс «данные ≠ команда»), и на наших классах это калечило бы разбор самого действия —
    у `mv tests/test_x.py …` пропадали бы цели. Класс «данные ≠ команда» здесь держится иначе и
    не слабее: глагол ищется в ГОЛОВЕ сегмента, а текст коммита и шаблон поиска — один токен."""
    g = _g()
    if g is None:
        return []
    try:
        return g._del_units(cmd)
    except Exception:
        return []


def _heads(cmd):
    """[(имя команды сегмента, её аргументы), …]. Голова ищется структурно (env-префиксы и
    обёртки sudo/timeout/systemd-run пропускаются) — `systemd-run --on-active=10s systemctl
    restart splinter` виден как systemctl, а `cat splinter.log` командой управления не станет."""
    g = _g()
    if g is None:
        return []
    out = []
    for toks in _units_raw(cmd):
        try:
            i = g._cmd_index(toks)
            if i is None:
                continue
            out.append((g._base(toks[i]), list(toks[i + 1:])))
        except Exception:
            continue
    return out


_REDIR = re.compile(r"[<>]")


def _pos(args):
    """Позиционные аргументы: без флагов и без токенов перенаправления (`2>&1`, `2>/dev/null`) —
    иначе у `systemctl restart splinter 2>&1` редирект сошёл бы за второй юнит."""
    return [a for a in args if not a.startswith("-") and not _REDIR.search(a)]


_GIT_VALUE_FLAGS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                    "--config-env", "--super-prefix")


def _git_sub(args):
    """Подкоманда git и её хвост. Флаги СО ЗНАЧЕНИЕМ пропускаются парой — живые формы
    `git -c core.hooksPath=deploy/hooks stash` и `git -C <репо> mv …` иначе читались бы как
    подкоманда «core.hooksPath»/«<репо>» и класс не срабатывал бы вовсе."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in _GIT_VALUE_FLAGS:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a, list(args[i + 1:])
    return "", []


# ═══════════════════════════ КЛАСС 1: РЕСТАРТ ЖИВОГО БОТА ══════════════════════════════════
# Сервис работает 24/7 — на время рестарта его нет. ИМЯ В ЗАМЕТКЕ ДАЁТ ЦЕЛЬ КОМАНДЫ, а не полоса
# (поправка 05.08.2026, см. шапку):
#   • ПК-процессы `userbot_listen` / `moderation_bot` / `moderbot` — КЛИЕНТСКИЙ контур
#     (docs/project_state.md): их рестарт видят клиенты;
#   • сервис `splinter` — ВНУТРЕННИЙ контур: команда и учёт, клиентов он не ведёт.
# Демон, wa-webhook, health и прочие юниты — вне класса вовсе (§4 «не уведомляем»).
_CTL_VERB = {"restart": "рестарт", "start": "старт", "stop": "стоп", "kill": "стоп",
             "reload-or-restart": "рестарт", "try-restart": "рестарт", "force-reload": "рестарт"}
_INTERNAL_UNITS = ("splinter",)                  # внутренний контур VPS (не клиентский!)
_CLIENT_PROCS = ("userbot_listen", "moderation_bot", "moderbot")
_CLIENT_SCRIPTS = ("userbot_listen.py", "moderation_bot.py")
_KILL_HEADS = ("pkill", "killall", "taskkill")
_CLIENT_WHAT = "клиентского бота"
_INTERNAL_WHAT = "внутреннего сервиса"


def _unit_name(u):
    u = (u or "").strip().strip("'\"")
    for suf in (".service", ".socket", ".timer"):
        if u.endswith(suf):
            u = u[:-len(suf)]
    return u.lower()


def _bot_ctl(cmd, cwd=None):
    """Управление живым ботом → «<глагол> клиентского бота» / «<глагол> внутреннего сервиса <юнит>».
    Имя юнита стоит в заметке рядом с глаголом: команда в заметке видна целиком, но класс должен
    читаться и без неё («рестарт внутреннего сервиса splinter» — законченная фраза)."""
    for head, args in _heads(cmd):
        pos = _pos(args)
        if head == "systemctl":
            if not pos or pos[0] not in _CTL_VERB:
                continue                       # show/status/is-active/cat — чтение, не событие
            for u in (_unit_name(x) for x in pos[1:]):
                if u in _CLIENT_PROCS:         # клиентский контур и юнитом называется клиентским
                    return _CTL_VERB[pos[0]] + " " + _CLIENT_WHAT
                if u in _INTERNAL_UNITS:
                    return _CTL_VERB[pos[0]] + " " + _INTERNAL_WHAT + " " + u
            continue
        if head in _KILL_HEADS:
            blob = " ".join(args).lower()
            if any(p in blob for p in _CLIENT_PROCS):
                return "стоп " + _CLIENT_WHAT
            continue
        if head.startswith("python") or head in ("py", "pythonw"):
            for a in pos:
                if os.path.basename(a.strip("'\"")).lower() in _CLIENT_SCRIPTS:
                    return "старт " + _CLIENT_WHAT
    return None


# ═══════════════════════════ КЛАСС 2: СТИРАНИЕ МАРКЕРОВ ГАРДА ══════════════════════════════
# Цель лежит в /tmp → по правилу 30.07 это зелёная уборка, и она проходит молча. Единственное
# оправданное исключение из «в /tmp всё ничьё»: стираются СЛЕДЫ красных карточек, которых владелец
# не закрывал. Судим по ТОМУ, ЧТО стёрто, а не где оно лежало.
def _marker_dirs():
    g = _g()
    out = set()
    if g is None:
        return out
    try:
        out.add(str(g.GUARD_BLOCK_DIR).rstrip("/"))      # боевой каталог маркеров
    except Exception:
        pass
    try:
        out.add(str(g.block_dir()).rstrip("/"))          # и тот, что настроен сейчас
    except Exception:
        pass
    return {d for d in out if d}


def _markers_wiped(cmd, cwd=None):
    g = _g()
    if g is None:
        return None
    dirs = _marker_dirs()
    if not dirs:
        return None
    for toks in _units_raw(cmd):
        try:
            i = g._cmd_index(toks)
            if i is None:
                continue
            tgts = g._del_targets(g._base(toks[i]), list(toks[i + 1:]))
        except Exception:
            continue
        for t in (tgts or []):
            p = str(t).strip().strip("'\"").rstrip("/")
            if any(p == d or p.startswith(d + "/") for d in dirs):
                return "стирание маркеров гарда"
    return None


# ═══════════════════════════ КЛАСС 3: ВЫНОС ТЕСТА ИЗ ГЕЙТА ═════════════════════════════════
# Гейт набирает тесты глобом `tests/test_*.py` (gate.py). Файл выпадает из набора, когда уезжает
# из каталога ИЛИ теряет префикс имени — защита слабеет молча, и следующий «гейт зелёный» уже про
# МЕНЬШИЙ набор. Внос теста В гейт и переименование ВНУТРИ гейта событием не являются.
def _in_gate(path):
    p = (path or "").strip().strip("'\"").rstrip("/")
    if not p:
        return False
    base = os.path.basename(p)
    if base == "tests":                       # каталог целиком
        return True
    return (os.path.basename(os.path.dirname(p)) == "tests"
            and base.startswith("test_") and base.endswith(".py"))


def _dest_path(src, dst, many, cwd=None):
    """Куда файл ЛЯЖЕТ: `mv a b` → b, `mv a b/` или `mv a b c/` → каталог + имя исходного."""
    d = (dst or "").strip().strip("'\"")
    if many or d.endswith("/") or os.path.isdir(os.path.join(cwd or PROJECT, d)):
        return os.path.join(d.rstrip("/"), os.path.basename(src.strip("'\"").rstrip("/")))
    return d


def _test_out_of_gate(cmd, cwd=None):
    for head, args in _heads(cmd):
        if head == "git":
            sub, rest = _git_sub(args)
            if sub != "mv":
                continue
            args = rest
        elif head != "mv":
            continue
        pos = _pos(args)
        if len(pos) < 2:
            continue
        srcs, dst = pos[:-1], pos[-1]
        for s in srcs:
            if _in_gate(s) and not _in_gate(_dest_path(s, dst, len(srcs) > 1, cwd)):
                return "вынос теста из гейта"
    return None


# ═══════════════════════════ КЛАСС 4: ОТБРОС РАБОЧЕГО ДЕРЕВА ═══════════════════════════════
# Единственный класс, где НЕзакоммиченная работа исчезает без следа в git — восстановить нечем.
# `stash list|show` читают, `pop|apply` возвращают работу — они молчат; `drop|clear` уничтожают
# отложенное, поэтому остаются событием. `clean -n` — сухой прогон, `checkout -b`/`checkout main`
# работу не теряют (git на грязном дереве переключение просто отклонит).
_STASH_QUIET = ("list", "show", "pop", "apply", "branch")


def _tree_discard(cmd, cwd=None):
    for head, args in _heads(cmd):
        if head != "git":
            continue
        sub, rest = _git_sub(args)
        pos = _pos(rest)
        if sub == "reset" and "--hard" in rest:
            return "отброс рабочего дерева"
        if sub == "checkout":
            if "--" in rest or pos[:1] == ["."]:
                return "отброс рабочего дерева"
            continue
        if sub == "restore":
            if "--staged" in rest and "--worktree" not in rest:
                continue                      # снятие из индекса работу не теряет
            if pos or "--" in rest:
                return "отброс рабочего дерева"
            continue
        if sub == "stash":
            if pos[:1] and pos[0] in _STASH_QUIET:
                continue
            return "отброс рабочего дерева"
        if sub == "clean":
            short = "".join(a[1:] for a in rest if a.startswith("-") and not a.startswith("--"))
            dry = "n" in short or "--dry-run" in rest
            force = "f" in short or "--force" in rest
            if force and not dry:
                return "отброс рабочего дерева"
    return None


# ═══════════════ КЛАСС 5 (PUSH) — ОТОЗВАН ВЛАДЕЛЬЦЕМ 05.08.2026 ════════════════════════════
# Предикат `_push_out` и деталь `push_detail` (ветка · коммиты · диапазон · ⚠️ машинерия защиты)
# удалены вместе с классом: без канала они были бы мёртвым кодом, а мёртвый код гниёт молча.
# Довод отзыва, замер и цена — в шапке файла и docs/artifacts/2026-08-05-feed-noise-cut.md;
# сам код — в git (последний живой вид: коммит eb33187, файл posttool_feed.py).

# Порядок = порядок проверки; первый совпавший решает. Имя в паре — запасное (предикат обычно
# уточняет его глаголом: «рестарт клиентского бота», «старт внутреннего сервиса splinter»).
_CLASSES = (
    ("управление живым ботом", _bot_ctl),
    ("стирание маркеров гарда", _markers_wiped),
    ("вынос теста из гейта", _test_out_of_gate),
    ("отброс рабочего дерева", _tree_discard),
)

# ПРОБА САМОГО КАНАЛА (шаг 1) — ведущий env-префикс `CC_FEED_PROBE=1 <команда>`. Почему префикс:
# проба идёт ТЕМ ЖЕ путём, что и настоящее событие (разбор → класс → изоляция проб → дедуп →
# потолок → отправка), значит проверяет провод целиком. Имя в СЕРЕДИНЕ строки объявлением НЕ
# является — читаем ровно ведущие присваивания, как pretool_guard._cmd_declares_probe.
PROBE_PREFIX = "CC_FEED_PROBE"
PROBE_CLASS = "проба канала"


def _leading_env(cmd):
    """Ведущие присваивания `VAR=val` до первого не-присваивания. Сбой разбора → пусто."""
    out = {}
    try:
        for t in shlex.split(cmd or ""):
            name, sep, val = t.partition("=")
            if not sep or not name or not name.replace("_", "").isalnum() or name[0].isdigit():
                break
            out[name] = val
    except Exception:
        return {}
    return out


def classify(cmd, cwd=None):
    """Класс события → имя | None. Первый совпавший класс решает."""
    if (_leading_env(cmd).get(PROBE_PREFIX) or "").strip():
        return PROBE_CLASS
    for name, pred in _CLASSES:
        try:
            got = pred(cmd, cwd)
        except Exception:
            continue                          # сбой предиката = молчание, а не мусорная заметка
        if got:
            return got if isinstance(got, str) else name
    return None


def is_probe(cmd):
    """Изоляция проб — ЕДИНЫЙ признак гарда, а не свой собственный. Свой второй признак и породил
    класс «наполовину изолированной пробы» (01.08.2026): у каждого канала владельца был СВОЙ список,
    и каждый закрывал ровно то, что другой оставлял открытым. Лента — третий канал к владельцу,
    поэтому спрашивает ту же ручку: pretool_guard.is_probe (env-имена + env-префикс в команде +
    тест-скрипт по имени/пути). Гард при этом НЕ меняется: мы его ЧИТАЕМ.
    FAIL-SAFE: импорт не удался → считаем пробой, то есть МОЛЧИМ. Направление безопасное: заметка
    не даёт прав, её отсутствие возвращает ровно сегодняшнее поведение."""
    try:
        from pretool_guard import is_probe as _guard_is_probe
        return bool(_guard_is_probe(cmd))
    except Exception:
        return True


def seen_dir(env=None):
    """Каталог состояния ленты: явная подмена → тест-умолчание → боевой."""
    e = os.environ if env is None else env
    explicit = (e.get(SEEN_DIR_ENV) or "").strip()
    if explicit:
        return explicit
    try:
        from pretool_guard import is_test_run
        testing = is_test_run(e)
    except Exception:
        testing = True
    return FEED_SEEN_TEST_DIR if testing else FEED_SEEN_DIR


def state_key(data):
    """Ключ ленты = задача демона (CC_TASK_ID) или сессия Termux (session_id). Не опознали → 'orphan'.
    Ключ живёт в ИМЕНИ ФАЙЛА, поэтому чистим всё, кроме букв/цифр/дефиса."""
    tid = (os.environ.get("CC_TASK_ID") or "").strip()
    raw = tid or str((data or {}).get("session_id") or "").strip() or "orphan"
    safe = "".join(c for c in raw if c.isalnum() or c in "-_")[:64]
    return safe or "orphan"


def lane():
    """Метка полосы: `CC_LANE` исполнителя → константа этой копии. Значение плющим в одну строку
    и режем: метка идёт в текст заметки, и длинный/многострочный мусор из окружения не должен ни
    ломать форму, ни вытеснять команду."""
    v = " ".join((os.environ.get(LANE_ENV) or "").split())[:LANE_MAX]
    return v or LANE_DEFAULT


def who(data):
    """Кто сделал: полоса + задача демона (CC_TASK_ID) либо ручная сессия Termux. Полоса стоит
    ВСЕГДА — номера задач VPS и ПК пересекаются, без метки заметка врёт о принадлежности."""
    tid = (os.environ.get("CC_TASK_ID") or "").strip()
    return lane() + " · " + (("задача " + tid) if tid else "Termux")


def _state_path(key, env=None):
    return os.path.join(seen_dir(env), key + ".json")


def _load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("n", 0)
            data.setdefault("seen", [])
            data.setdefault("capped", False)
            return data
    except Exception:
        pass
    return {"n": 0, "seen": [], "capped": False}


def _save_state(path, st):
    """Best-effort: каталог/диск недоступен → молча пропускаем. Состояние ленты не критично —
    хуже дедупа не бывает ничего страшнее повторной заметки."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, path)
    except Exception:
        pass


def _fingerprint(cls, cmd, detail=""):
    """Отпечаток для дедупа: класс + команда + деталь. ДЕТАЛЬ ВХОДИТ В НЕГО НАМЕРЕННО — одна и та
    же команда, давшая РАЗНЫЕ детали, описывает разные факты мира, и глушить второй нельзя (правило
    заведено под отозванный класс push с его диапазонами). Детали сейчас нет ни у одного класса,
    поэтому отпечаток фактически «класс + команда» — как и был до неё."""
    raw = cls + "\x00" + " ".join((cmd or "").split()) + "\x00" + (detail or "")
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]


def short_cmd(cmd, limit=120):
    flat = " ".join((cmd or "").split())
    return flat if len(flat) <= limit else flat[:limit - 1] + "…"


# ─────────────────────────── ИСХОД: ФОРМА ОТВЕТА ИЗМЕРЕНА ПО ТРАНСКРИПТУ ────────────────────
_EXIT_RE = re.compile(r"exit code\s+(-?\d+)", re.I)
_TIMEOUT_RE = re.compile(r"timed out|timeout", re.I)


def outcome(resp):
    """Исход из `tool_response`. Живая форма (замер 04.08 по транскриптам сессий): успех —
    словарь БЕЗ кода возврата, провал — СТРОКА «Error: Exit code N …», прерывание — флаг.
    Кода не нашли → «выполнено», БЕЗ утверждения об успехе (fail-honest, не выдумываем)."""
    if isinstance(resp, str):
        m = _EXIT_RE.search(resp)
        if m:
            try:
                code = int(m.group(1))
            except Exception:
                return "ошибка"
            return "ok" if code == 0 else ("ошибка (код %d)" % code)
        if _TIMEOUT_RE.search(resp):
            return "прервано таймаутом"
        return "выполнено"
    if not isinstance(resp, dict):
        return "выполнено"
    for k in ("exit_code", "exitCode", "returncode", "returnCode", "code"):
        v = resp.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return "ok" if v == 0 else ("ошибка (код %d)" % v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return "ok" if int(v) == 0 else ("ошибка (код %d)" % int(v))
    if resp.get("interrupted"):
        return "прервано"
    if resp.get("is_error") or resp.get("isError") or resp.get("error"):
        return "ошибка"
    return "выполнено"


def refused(resp):
    """ОТКАЗ ДВИЖКА (команда НЕ исполнялась) — «Error: This command requires approval»,
    «Error: Contains simple_expansion» и подобные. Лента говорит ТОЛЬКО о случившемся, поэтому
    здесь заметки нет вовсе: сказать «push выполнен» о push, которого не было, — худшая из
    возможных ошибок этого канала. Упавшая команда (есть код возврата) и таймаут отказом НЕ
    считаются: они исполнялись, и о них лента говорит честно."""
    if not isinstance(resp, str):
        return False
    s = resp.strip()
    if not s.lower().startswith("error:"):
        return False
    return not (_EXIT_RE.search(s) or _TIMEOUT_RE.search(s))


# ─────────────────────────── ДЕТАЛЬ ЗАМЕТКИ ────────────────────────────────────────────────
# Точка расширения: класс может добавить к строке одну деталь (её видит и дедуп — см. _fingerprint).
# Сейчас деталь не даёт НИ ОДИН класс: единственным её потребителем был push, отозванный 05.08.2026.
# Само поле оставлено — оно ничего не стоит и держит форму заметки неизменной для следующего класса.


def render(cls, subject, cmd, resp, detail=None):
    """Одна строка. Кнопок нет, номера карточки нет, слова «да» нет — отвечать не на что."""
    parts = ["🔔 " + cls, subject, short_cmd(cmd)]
    if detail:
        parts.append(detail)
    parts.append(outcome(resp))
    return " · ".join(parts)


def render_cap(subject):
    return ("🔔 потолок ленты (%d заметки) · %s · дальше по этой задаче молчу — "
            "смотри журнал гарда и cc_log" % (CAP, subject))


def send(text):
    """Отправка в ленту. Мут/мок-счётчик — ОБЩИЕ с боевым пушем (notify._test_mode), поэтому полный
    гейт по-прежнему даёт ноль исходящих. Адреса нет (тема не задана) → False, МОЛЧА:
    фолбэка в личку у ленты нет намеренно (личка — канал алармов)."""
    try:
        from notify import send_feed
        return bool(send_feed(text))
    except Exception:
        return False


def _remember_permission(data, cmd, resp):
    """ФАКТ, А НЕ ПРАВО (05.08.2026, «одна операция спрашивается дважды»).

    Команда ИСПОЛНИЛАСЬ — значит вопрос гарда по ней уже получил «да» владельца: до этого «да»
    решение `ask` её держало. Записываем ровно этот факт в память захода, которую на следующем
    вызове читает гард (PreToolUse), чтобы тот же вопрос не прозвучал второй раз.

    ПОЧЕМУ ЭТО МЕСТО БЕЗОПАСНО, И ЭТО УСТРОЙСТВО, А НЕ ОБЕЩАНИЕ: у события `PostToolUse` нет поля
    `permissionDecision` ВООБЩЕ — отсюда прав не выдать физически, ровно та же причина, по которой
    здесь живёт лента. Гард `pretool_guard` при этом остаётся БИБЛИОТЕКОЙ РАЗБОРА: отсюда зовётся
    только read-only `is_probe` (изоляция каналов, общая ручка — см. ниже), решающих и пишущих его
    веток лента не касается по-прежнему. Сам отпечаток операции считает ГАРД в момент вопроса — лента лишь
    подтверждает, что команда с этим вопросом дошла до исполнения.

    КАТАЛОГ ПАМЯТИ ВЫБИРАЕТСЯ ТЕМ ЖЕ ПРИЗНАКОМ, ЧТО У ГАРДА (фикс 05.08.2026, вторая ревизия того
    же захода). Гард берёт каталог как `isolated()` ПОСЛЕ латча `set_probe(is_probe(cmd))`, то есть
    по признаку, зависящему ОТ КОМАНДЫ; здесь стоял `is_test_run()` — признак, зависящий ТОЛЬКО ОТ
    ОКРУЖЕНИЯ. Для ЛЮБОЙ пробы в живой сессии (env-префикс в тексте команды, `_test`/`_dryrun` в
    имени, запуск из `/tmp/tb_scratch`) стороны расходились: гард клал связку в
    `/tmp/cc_repeat_ask_test`, а подтверждение искалось в `/tmp/cc_repeat_ask` — память не
    накапливалась ВОВСЕ, и повтор спрашивался как прежде. Под гейтом оба признака истинны, поэтому
    расхождение было тестам не видно (замер: 3 расхождения из 5 живых сочетаний).
    Это ТОТ ЖЕ класс «наполовину изолированной пробы» (01.08.2026), ради которого выше заведена
    общая ручка `is_probe` — свой второй признак снова закрыл ровно то, что другой оставил открытым.
    Направление разделения СОХРАНЕНО намеренно: память пробы живёт в тест-каталоге, боевая команда
    читает боевой, поэтому «да», данное на пробе, боевой вопрос НЕ снимает.

    ЧТО ИМЕННО ИСПОЛНИЛОСЬ, сверяет сама память (`repeat_ask.confirm` → `body_signature`): связка
    живёт по ключу ТЕКСТА команды, а текст скрипта не меняется, пока меняется его содержимое.
    Гард для ленты остаётся БИБЛИОТЕКОЙ РАЗБОРА — его `classify` отсюда не зовётся (страж
    секции (8) `tests/test_feed_list.py`), сверка целиком внутри модуля памяти.

    FAIL-SAFE: любое исключение (нет модуля, недоступен /tmp, чужая форма ответа) → молча ничего,
    то есть гард спросит как прежде."""
    try:
        import repeat_ask
        repeat_ask.confirm(repeat_ask.run_key(data), cmd, resp, is_probe(cmd))
    except Exception:
        pass


def handle(data):
    """Ядро без ввода-вывода процесса. → отправленный текст | None (для теста и для читаемости)."""
    if (data.get("tool_name") or "") != "Bash":
        return None
    ti = data.get("tool_input")
    cmd = (ti.get("command") or "") if isinstance(ti, dict) else ""
    if not cmd:
        return None
    resp = data.get("tool_response")
    if refused(resp):
        return None                      # движок отказал — события мира не было, говорить не о чем
    _remember_permission(data, cmd, resp)
    cwd = str(data.get("cwd") or "") or None
    cls = classify(cmd, cwd)
    if not cls:
        return None                      # вне списка фазы 1 — молчим (§4 проекта)
    if is_probe(cmd):
        return None                      # гейт, фикстуры, разведка из /tmp/tb_scratch — не лента
    detail = None                        # деталей сейчас не даёт ни один класс (см. выше)
    key = state_key(data)
    path = _state_path(key)
    st = _load_state(path)
    if st.get("capped"):
        return None
    fp = _fingerprint(cls, cmd, detail)
    if fp in (st.get("seen") or []):
        return None                      # дедуп: тот же класс+команда+деталь в той же задаче
    if int(st.get("n") or 0) >= CAP:
        text = render_cap(who(data))
        if not send(text):
            return None
        st["capped"] = True
        _save_state(path, st)
        return text
    text = render(cls, who(data), cmd, resp, detail)
    if not send(text):
        return None                      # канал не заведён/сеть — состояние не трогаем
    st["n"] = int(st.get("n") or 0) + 1
    st["seen"] = ([fp] + list(st.get("seen") or []))[:SEEN_KEEP]
    _save_state(path, st)
    return text


def main():
    """НИЧЕГО НЕ ПЕЧАТАЕТ. Любой вход, любая ошибка → тихий exit 0: у ленты нет и не может быть
    голоса в диалоге движка (ни решения, ни контекста)."""
    try:
        data = json.load(sys.stdin)
        if isinstance(data, dict):
            handle(data)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
