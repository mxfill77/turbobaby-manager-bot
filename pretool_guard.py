#!/usr/bin/env python3
"""PreToolUse hook Claude Code — закрывает СЛЕПОЕ ПЯТНО записи в Лист1/CRM/деньги.

Контекст: `venv/bin/python3 *` в allow → ЛЮБОЙ мой python-скрипт (вкл. ПИШУЩИЙ в рабочие таблицы через Bridge)
исполнялся БЫ без сигнала. Этот hook перехватывает python-команды и, если скрипт содержит WRITE-признак
(запись в Лист1/CRM, деньги, удаление), форсит permissionDecision="ask" + пушит человеческую КРАСНУЮ КАРТОЧКУ
в Telegram владельцу. Читающий python (recon/gate/tests/reports через write_doc в журналы) — не трогает (defer).

ПОЗИЦИЯ БЕЗОПАСНОСТИ: hook ТОЛЬКО ДОБАВЛЯЕТ подтверждения (никогда не выдаёт новых разрешений).
- red python → "ask" (+карточка); жёсткие классы (процессы/секреты) → "deny".
- зелёный python, ambiguous (в3, ниже) и всё прочее → exit 0 (defer к штатным allow/ask/deny
  rules; venv python уже в allow, доктринальное красное держит ask/deny-слой settings).
- FAIL-SAFE РАЗБОРА: сбой разбора цепи → скан по СЫРОЙ команде, т.е. КРАСНЕЕ (см. _scan);
  доктринальные проверки (red-токены, sqlite, процессы, секреты) идут ДО любого ambiguous-выхода.
ПЕРЕКЛАССИФИКАЦИЯ 02.07 (меньше шума, ask только где «да» реально решает):
- tests/*.py и gate.py → ранний defer БЕЗ чтения содержимого (моки по определению);
- memory.db через python-код → defer (своя БД бота; sqlite3 CLI остаётся ask в settings);
  SQL-write в ИНУЮ .db → ask;
- git push / systemctl restart splinter → авто на уровне settings (restart идёт только по «да»
  владельца в ТЗ — терминальный prompt был двойным вопросом); systemctl stop остался ask.
ТРИ КЛАССА ПОВЕРХ python-скана (23.07.2026) — python-скан при этом НЕ ослаблен:
(а) ЧЁРНЫЙ СПИСОК ПРОЦЕССОВ: kill/pkill/`systemctl kill|stop` по боевым процессам контура
    (splinter, orchestrator-daemon, userbot, moderation_bot, pc_agent) и `kill` по PID 1 →
    HARD-BLOCK: permissionDecision="deny", карточка владельцу НЕ шлётся, approve НЕВОЗМОЖЕН,
    строка `proc_hard_block` в GUARD_LOG. Отложенный `systemd-run … systemctl stop|kill` —
    тот же HARD-BLOCK (обёртки раскрываются). systemctl restart|start СВОИХ сервисов —
    ЗЕЛЁНОЕ (defer к allow-правилам settings): это штатный поток (подъём после гейта /
    self-update / упавшего сервиса), его гейтит оркестратор ДО команды; ask здесь ломал
    headless — красное не исполнялось даже после «да» владельца (тупик задач 339/340).
    Остальные глаголы по своим (mask/disable/reload…) — обычное красное с карточкой.
(б) ДАННЫЕ ≠ КОМАНДА: красное слово внутри ПОИСКОВОГО ШАБЛОНА grep/rg/sed/awk (аргумент
    -n/-e/-E либо первый позиционный) — это ДАННЫЕ, они НЕ краснят команду. Шаблон вырезается
    ТОЛЬКО из скан-представления и ТОЛЬКО в СВОЁМ сегменте цепи; ОПЕРАНДЫ (файлы!) остаются под
    сканом, а токен с признаками ИСПОЛНЕНИЯ ($(…)/`…`/system("…")) не вырезается и раскрывается
    отдельным сегментом. Итог: `grep -n ".env" f.py` — зелёное, `grep -n foo .env` — блок.
    Тот же класс с 24.07.2026 — ARGV .py-СКРИПТА (_strip_script_cli_args): всё ПОСЛЕ имени
    скрипта вырезается из скан-представления (журнальный `cclog.py "DONE …"` краснел по ТЕКСТУ
    строки), но ТЕЛО .py читается как прежде, а операнды-улики (файл секретов, .db/SQL-write,
    $(…)/`…`) из argv НЕ вырезаются — жёсткие блоки не слабеют.
    Тот же класс с 30.07.2026 — ТЕКСТ СВОЕГО КОММИТА В ЛЮБОЙ ФОРМЕ ПЕРЕДАЧИ: payload -m/-am/
    --message держал _strip_git_msg, а многострочная форма `git commit -F - <<'MSG' … MSG` шла
    под скан целиком — и 29.07.2026 боевой commit получил env_hard_block за СЛОВА в сообщении.
    _strip_git_msg_heredoc вырезает тело ТОЛЬКО у ЗАКАВЫЧЕННОГО heredoc (шелл в нём ничего не
    подставляет) и ТОЛЬКО когда сообщение читает git commit из stdin; голый <<MSG, тело
    `bash <<'EOF'` и всё после терминатора остаются под сканом.
(в) HARD-BLOCK .env: обращение к файлу секретов в ЛЮБОЙ позиции цепи (после &&/;/|, внутри
    `bash -c`, $(…), `…`) → deny БЕЗ карточки, лог `env_hard_block`, approve НЕВОЗМОЖЕН.
    Сканируется ТОЛЬКО ТЕКСТ КОМАНДЫ: содержимое .py-целей НЕ проверяется (иначе любой боевой
    скрипт с load_env() встал бы намертво).
в3 (23.07.2026, доктрина «шквал подтверждений»): AMBIGUOUS САМ ПО СЕБЕ НЕ КРАСНЫЙ. Незнакомая
команда, python без внятной цели (stdin/heredoc `python3 - <<EOF`, неизвестный -m, нечитаемый
.py, кривое квотирование) → defer к слоям settings (allow/ask/deny). Красное гарда — ТОЛЬКО
доктринальный список: живые таблицы/CRM/деньги (RED_TOKENS), файл секретов, SQL-write вне
memory.db (с в3 ловится и в heredoc/stdin — проверка поднята ДО ambiguous-выходов), kill/stop
боевых процессов, PID 1. clasp/массовые удаления/git-force держит ask/deny-слой settings —
гард их не дублирует. Конверт «не распознал операцию» упразднён вместе с ambiguous-ask
(хелперы дедупа карточек оставлены: их контракт держит test_guard_inbox).
Единая точка классификации — classify(cmd, cwd) → (kind, hit, blob), kind ∈ block/red/ambiguous/
green; can_approve(kind, hit) и decision(kind, hit, reason) — чистые (их зовут тесты, ничего не
исполняя). Направление fail-safe разбора прежнее: сбой разбора → скан по СЫРОЙ команде (краснее).

МИНИМУМ КАРТОЧКИ (28.07.2026): красная карточка обязана читаться за ТРИ СЕКУНДЫ и нести ЧЕТЫРЕ
вещи — ЧТО меняется, у какого ОБЪЕКТА, какое ЧИСЛО, одну строку ОТКАТА. Нет ОБЪЕКТА или ЧИСЛА →
карточки НЕТ ВОВСЕ: вместо неё строка `card_skipped` в GUARD_LOG (ни пуша владельцу, ни
маркер-конверта демону). Решение хука это НЕ ослабляет — ask/deny остаются, т.е. без «да» команда
не исполняется; молчим только в каналах владельца. Жёсткий блок — ИСКЛЮЧЕНИЕ: он приходит всегда.
Объект и число берутся ИЗ ИЗВЛЕЧЕНИЯ по ЖИВЫМ именам полей Bridge (_detail_parts/card_min), а не из
текста шаблона действия: прежняя проверка искала цифру в готовой карточке и «Лист1» делал объект
найденным ВСЕГДА, тогда как сами шаблоны (plate=/client=/\bkm=) живым подписям Bridge
(number=/name=/oil_km=) не соответствовали и не срабатывали НИ РАЗУ.

НЕ трогает реальный гейт записи confirmed=true в Bridge (ReadFleet.js) — тот независим (третий слой защиты).
Зона 🟢 (конфиг агента; прод Splinter/таблицы не трогает). НИЧЕГО не печатает в stdout, кроме JSON-решения.
"""
import sys, os, json, re, shlex, time, fcntl, hashlib
import ast
import subprocess

PROJECT = "/root/turbobaby-manager-bot"

# WRITE-признаки рабочих таблиц/денег/удаления. confirmed=true — УНИВЕРСАЛЬНЫЙ (Bridge требует его на КАЖДУЮ
# запись в Лист1 → любая боевая запись его содержит). write_doc/state_set/add_event/service_upsert/o3_task_*/
# set_info_pin — ЗЕЛЁНЫЕ (Brain-журналы / Bot Data / свои таблицы), их здесь НЕТ намеренно.
# Порядок ВАЖЕН: конкретные действия ПЕРВЫМИ, обобщённые (DOWRITE/confirmed) — ПОСЛЕДНИМИ, чтобы скрипт с
# set_fleet_oil+confirmed=true распознался как set_fleet_oil (конкретно), а не как безликое confirmed.
RED_TOKEN_HIT = {
    "set_fleet_oil": "set_fleet_oil", "set_fleet_service": "set_fleet_service",
    "add_transaction": "add_transaction", "void_last": "void_last",
    "create_booking": "create_booking", "activate_booking": "activate_booking",
    "closing_upsert": "closing_upsert", "delete_event": "delete_event",
    "DOWRITE": "DOWRITE",
    "confirmed=true": "confirmed", "confirmed=True": "confirmed", "confirmed = true": "confirmed",
    '"confirmed": true': "confirmed", '"confirmed":true': "confirmed",
}
RED_TOKENS = tuple(RED_TOKEN_HIT.keys())
_GREEN_MODULES = {"py_compile", "json.tool", "pytest", "unittest", "pip", "venv", "http.server",
                  "platform", "sysconfig", "site"}
# Инфо-флаги интерпретатора: НИЧЕГО не исполняют (печатают версию/справку) → зелёное, даже без .py-цели.
# Убирает ложный ambiguous-ask на `venv/bin/python3 --version` (нет target → раньше падало в ask, хотя
# venv python в allow). Сужение неоднозначности (06.07.2026) — red-список НЕ трогает.
_INFO_FLAGS = {"--version", "-V", "-VV", "--help", "-h"}
_ENV_ASSIGN = re.compile(r"^\w+=")   # env-префикс VAR=val перед интерпретатором (PRETOOL_NOPUSH=1 …)
_SQLITE_WRITE = re.compile(r"\b(UPDATE|DELETE\s+FROM|INSERT\s+INTO|DROP\s+TABLE)\b", re.IGNORECASE)

# ── ЦЕЛЬ SQL-ЗАПИСИ (класс «корень А», 02.08.2026; зеркало ПК-фикса abd2917) ──────────────────
# Своя БД бота — исключение доктрины 02.07 («своя таблица через код = зелёное»). Проверялось оно
# СЛОВОМ: `".db" in blob and "memory.db" not in blob`. Текст при этом гарду никто не обещал —
# это команда, сочинённая моделью, плюс ИСХОДНИК скрипта с комментариями и докстрингами. Хватало
# одного упоминания своей БД где угодно в тексте, чтобы красное снялось со ВСЕХ SQL-записей
# скрипта: комментарий «memory.db не трогаем» отбеливал запись в чужую БД.
#
# Теперь решает РАЗОБРАННАЯ ЦЕЛЬ ОТКРЫТИЯ, а не совпадение слова: литерал в `connect(...)` либо
# файловый аргумент `sqlite3 <файл>.db`. Цель не разобралась — fail-closed: судим по всем
# `.db`-именам (прежний охват), но упоминание своей БД чужую больше не отбеливает.
_OWN_DB = "memory.db"
_DB_TOKEN_RE = re.compile(r"[\w./\\+-]*\.db\b")
_SQLITE_OPEN_RE = re.compile(r"\bconnect\s*\(\s*(['\"])(.*?)\1", re.S)
# Файловый аргумент CLI. Пробел/табуляция, а НЕ \s: `import sqlite3\n` + следующая строка
# `sqlite3.connect('memory.db')` иначе склеиваются в одну «цель» через перевод строки.
_SQLITE_CLI_RE = re.compile(r"\bsqlite3[ \t]+(?:-\S+[ \t]+)*([^\s'\"()]+?\.db)\b")


def _db_basename(tok):
    return (tok or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _sql_write_is_foreign(text):
    """Цель SQL-записи — ЧУЖАЯ БД? Судим по РАЗОБРАННОЙ цели открытия, а не по слову в тексте.

    → True (чужая, красное), если названа хоть одна `.db`-цель с именем, отличным от своей БД.
    Разобранные открытия имеют приоритет над упоминаниями: скрипт, открывающий СВОЮ БД и лишь
    называющий чужую в комментарии, ложного красного не получает."""
    text = text or ""
    opened = [m.group(2) for m in _SQLITE_OPEN_RE.finditer(text)]
    opened += [m.group(1) for m in _SQLITE_CLI_RE.finditer(text)]
    opened = [t for t in opened if t and _db_basename(t).endswith(".db")]
    if opened:                                  # цель названа явно — по ней и судим
        return any(_db_basename(t) != _OWN_DB for t in opened)
    # открытия в тексте нет → прежний охват по именам, но БЕЗ отбеливания своим именем
    return any(_db_basename(t) != _OWN_DB for t in _DB_TOKEN_RE.findall(text))


# ── РАЗБОР ТЕЛА СКРИПТА: где КОД, а где ПРОЗА (класс «корень А», 02.08.2026; тот же ход, что
#    ПК-фикс f7cfb25 «судить по разобранному вызову») ──────────────────────────────────────────
# Красное решалось ПОДСТРОКОЙ по всему телу — тексту, который гарду никто не обещал: это исходник,
# сочинённый моделью, вместе с комментариями и докстрингами. Обе стороны били:
#   ЛОЖНОЕ КРАСНОЕ И ЛОЖНЫЙ КЛАСС — `# проводку add_transaction тут НЕ делаем` краснело наравне с
#     вызовом, и владельцу уходила карточка «проводка ДЕНЕГ в кассу» об операции, которой в
#     скрипте нет;
#   СЛЕПОТА — `confirmed=true` проверялся ПЯТЬЮ написаниями списком, и `confirmed  =  True`
#     (два пробела) не совпадал ни с одним из пяти: БОЕВАЯ запись в Лист1 проходила молча.
# Оба конца — один класс: судили по НАПИСАНИЮ, а не по разобранному коду.
#
# Тело скрипта — формальная грамматика, у неё есть канонический разбор. _py_code_view строит
# дерево (ast) и отдаёт ТРИ факта:
#   text  — всё, что видно как КОД: идентификаторы, имена атрибутов/аргументов/импортов и
#           СТРОКОВЫЕ ЛИТЕРАЛЫ. Комментариев там нет ПО ПОСТРОЕНИЮ. Докстринг и строка остаются
#           намеренно: имя операции в строке МОЖЕТ быть действием (`_call("add_transaction")`) —
#           сомнение решаем в сторону красного;
#   conf  — есть ли `confirmed` со значением ИСТИНА как РАЗОБРАННЫЙ именованный аргумент, ключ
#           словаря или присваивание: сколько бы пробелов, кавычек и регистра ни стояло;
#   calls — {имя вызванной функции: {имя именованного аргумента: литерал | None}} — видно не
#           только ЧТО вызвано, но и ЧЕМ: аргумент есть, а значение вычисляется (переменная).
# Разбор не удался (не python, обрывок, чужой синтаксис) → None, и вызывающий остаётся на прежнем
# подстрочном скане БАЙТ-В-БАЙТ. Направление сомнения прежнее — краснее.
_CONFIRMED_RE = re.compile(r"""\bconfirmed\b["']?\s*[:=]\s*["']?\s*true\b""", re.I)
# Пять исторических написаний из RED_TOKEN_HIT: для них решает разбор, а не буквальное совпадение.
_CONFIRMED_TOKENS = ("confirmed=true", "confirmed=True", "confirmed = true",
                     '"confirmed": true', '"confirmed":true')


def _node_truthy(node):
    """Значение узла — ИСТИНА? True / 1 / 'true' в любом регистре. Иначе (в т.ч. переменная) — нет."""
    if not isinstance(node, ast.Constant):
        return False
    v = node.value
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return v is True or v == 1


def _node_literal(node):
    """Литерал узла → строкой; вычисляемое значение (переменная, вызов, f-строка) → None.
    Именно это различение и невозможно текстом: `number=plate` регулярке неотличимо от `number='6789'`."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else repr(node.value)
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)):
        return "-" + repr(node.operand.value)
    return None


# Чисто-разборные модули: ими нельзя ни записать в кассу, ни выполнить чужой код — только читать и
# считать. Список БЕЛЫЙ намеренно: неизвестный модуль = канал = краснее. Сюда НЕ входят и не должны
# входить subprocess/socket/http/urllib/requests/bridge_client — это и есть каналы.
_INERT_MODULES = frozenset((
    "re", "json", "os", "sys", "glob", "time", "datetime", "calendar", "math", "csv", "statistics",
    "collections", "itertools", "functools", "operator", "pathlib", "textwrap", "string", "difflib",
    "hashlib", "random", "unicodedata", "ast", "shlex", "io", "typing", "pprint", "argparse",
    "traceback", "base64", "binascii", "codecs", "uuid", "tempfile", "shutil", "fnmatch", "logging",
    "warnings", "copy", "heapq", "bisect", "decimal", "fractions", "struct", "zlib", "gzip",
    "tarfile", "zipfile", "sqlite3", "unittest", "types", "enum", "dataclasses", "abc", "inspect",
    "platform", "locale", "getpass", "signal", "atexit", "gc", "keyword", "token", "tokenize",
))
# Имена, которыми тело ИСПОЛНЯЕТ чужое или ходит в сеть: их наличие = канал, даже если все импорты
# инертны (`os.system("curl …")`, `getattr(bridge, имя)()`).
_EXEC_CALLS = frozenset((
    "system", "popen", "run", "Popen", "call", "check_call", "check_output", "spawn", "spawnl",
    "execv", "execl", "exec", "eval", "compile_command", "urlopen", "request", "post", "put",
    "patch", "send", "sendall", "getattr", "__import__", "import_module", "connect",
))


def _str_consts(node, depth=3):
    """Строковые литералы, отданные ВЫЗОВУ: сам аргумент либо элемент списка/кортежа/словаря внутри
    него. Глубина ограничена и контейнеры перечислены НАРОЧНО: ищется СЕЛЕКТОР действия
    (`_post("add_transaction", …)`), а не всякая строка, случайно оказавшаяся в дереве аргумента —
    иначе `any(t in line for t in (…))` из разведки снова читалось бы как операция."""
    out = []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        out.append(node.value)
    elif depth > 0 and isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for e in node.elts:
            out += _str_consts(e, depth - 1)
    elif depth > 0 and isinstance(node, ast.Dict):
        for e in list(node.keys) + list(node.values):
            if e is not None:
                out += _str_consts(e, depth - 1)
    return out


def _py_code_view(src):
    """Разбор ОДНОГО python-тела → {'text','conf','calls','names','lit_args','channel'} либо None.

    Три факта добавлены 02.08.2026 ради ДЕНЕЖНОГО класса (см. _money_is_action ниже):
      names    — ИМЕНА КОДА без строк: идентификатор/атрибут/импорт/аргумент/def. Именно этим
                 `bridge.add_transaction(…)` отличается от `"add_transaction" in line`;
      lit_args — строковые литералы, отданные ВЫЗОВУ (сам аргумент либо элемент списка/кортежа/
                 словаря внутри него): так выглядит имя операции, работающее СЕЛЕКТОРОМ действия
                 (`_post("add_transaction", …)`, `data={"action": "add_transaction"}`);
      channel  — есть ли у тела чем ДОЙТИ до кассы: импорт вне списка чисто-разборных модулей либо
                 вызов исполняющего/сетевого имени. Список инертных модулей БЕЛЫЙ намеренно —
                 неизвестный модуль считается каналом, то есть сомнение решается краснее."""
    try:
        tree = ast.parse(src or "")
    except Exception:
        return None
    words, names, conf, calls = [], [], False, {}
    lit_args, mods = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            words.append(node.id)
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            words.append(node.attr)
            names.append(node.attr)
        elif isinstance(node, ast.arg):
            words.append(node.arg)
            names.append(node.arg)
        elif isinstance(node, ast.alias):
            words.append(node.name)
            words.append(node.asname or "")
            names.append(node.name)
            names.append(node.asname or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            words.append(node.name)
            names.append(node.name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            words.append(node.value)
        elif isinstance(node, ast.Import):
            mods += [(a.name or "").split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods.append((node.module or "").split(".")[0])
        elif isinstance(node, ast.keyword):
            words.append(node.arg or "")
            if node.arg == "confirmed" and _node_truthy(node.value):
                conf = True
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and k.value.strip().lower() == "confirmed" and _node_truthy(v)):
                    conf = True
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "confirmed" and _node_truthy(node.value):
                    conf = True
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if name:
                kw = calls.setdefault(name, {})
                for k in node.keywords:
                    if k.arg:
                        kw.setdefault(k.arg, _node_literal(k.value))
            for a in list(node.args) + [k.value for k in node.keywords]:
                lit_args += _str_consts(a)
    channel = (any(m and m not in _INERT_MODULES for m in mods)
               or any(c in _EXEC_CALLS for c in calls))
    return {"text": "\n".join(w for w in words if w), "conf": conf, "calls": calls,
            "names": [n for n in names if n], "lit_args": lit_args, "channel": channel}


def _code_view_parts(parts):
    """Слить разборы ВСЕХ python-тел команды (файлы + инлайн `-c`). Хоть одно не разобралось →
    None: тогда вся команда судится по-старому, подстрокой (fail-closed, не хуже прежнего)."""
    if not parts:
        return None
    text, conf, calls = [], False, {}
    names, lit_args, channel = [], [], False
    for src in parts:
        v = _py_code_view(src)
        if v is None:
            return None
        text.append(v["text"])
        conf = conf or v["conf"]
        names += v["names"]
        lit_args += v["lit_args"]
        channel = channel or v["channel"]      # канал ОДНОГО тела красит команду целиком
        for fn, kw in v["calls"].items():
            calls.setdefault(fn, {}).update(kw)
    return {"text": "\n".join(text), "conf": conf, "calls": calls,
            "names": names, "lit_args": lit_args, "channel": channel}


def _body_has(tok, raw, view):
    """Есть ли красный признак в ТЕЛЕ скрипта. Разбор недоступен → прежняя подстрока.

    DOWRITE судится по СЫРОМУ тексту ВСЕГДА и намеренно: это не операция, а САМООБЪЯВЛЕНИЕ автора
    («этот скрипт реально пишет»), и оно законно живёт в комментарии-шапке — прятать его разбором
    значило бы обесценить пометку, которую CLAUDE.md требует ставить руками."""
    if view is None or tok == "DOWRITE":
        return tok in raw
    if tok in _CONFIRMED_TOKENS:
        # разобранный аргумент/ключ/присваивание ЛИБО написание внутри строкового литерала
        # (`data="confirmed=true&…"` — тоже боевая запись, только через сырой запрос)
        return view["conf"] or bool(_CONFIRMED_RE.search(view["text"]))
    return tok in view["text"]


# ── ДЕНЕЖНЫЙ КЛАСС: КРАСНОЕ РОЖДАЕТ ДЕЙСТВИЕ, А НЕ УПОМИНАНИЕ (02.08.2026) ────────────────────
# Пять карточек за трое суток (117, 135, 140, 181, 208) пришли владельцу как «проводка ДЕНЕГ в
# кассу», и НИ ЗА ОДНОЙ не стояло проводки. Дословный корень 208 — тело разведки, читающей
# splinter.log: `if ("add_event" in line or … or "add_transaction" in line):`. Дословный корень
# 117 — инлайн-подсчёт пишущих признаков СПИСКОМ СЛОВ: `writes = ["set_fleet", "add_transaction",
# …]`. Оба раза красное дал СТРОКОВЫЙ ЛИТЕРАЛ: у прочих операций сомнение решается краснее и это
# терпимо (карточка гаснет объектным гейтом), а деньги обходили гейт через _ALWAYS_CARD — и
# упоминание доезжало до владельца карточкой из одних прочерков.
#
# Асимметрия с остальными токенами намеренная: у денег цена ЛОЖНОЙ карточки выше, чем у прочих
# классов, — она не просто шумит, она УБИВАЕТ задачу (в headless `ask` = отказ), и она приучает
# владельца жать «да» на карточку, за которой ничего нет. Поэтому здесь красное требует признака
# ДЕЙСТВИЯ, а не совпадения слова:
#   1) РАЗОБРАННЫЙ ВЫЗОВ         — `bridge.add_transaction(…)`, `add_transaction(…)`;
#   2) ИМЯ КОДА                  — ссылка/импорт/атрибут без скобок (`fn = bridge.void_last`,
#                                  `from bridge_client import add_transaction`);
#   3) ЛИТЕРАЛ-СЕЛЕКТОР + КАНАЛ  — строка отдана вызову (`_post("add_transaction", …)`,
#                                  `data={"action": …}`) И у тела есть чем дойти до кассы.
# Слепое тело (stdin/heredoc, неизвестный `-m`, нечитаемый .py) и несостоявшийся разбор → прежняя
# подстрока БАЙТ-В-БАЙТ: судить по разобранному нечего, направление сомнения — краснее.
_MONEY_HITS = ("add_transaction", "void_last")


def _money_is_action(tok, raw, view, blind=False):
    """Денежное имя ДЕЙСТВУЕТ (красное) или лишь УПОМЯНУТО (не красное)? См. разбор выше."""
    if view is None or blind:
        return tok in (raw or "")
    if tok in (view.get("calls") or {}) or tok in (view.get("names") or ()):
        return True
    return bool(view.get("channel")) and any(tok in s for s in (view.get("lit_args") or ()))


# Разбор тела последней команды — латч на прогон хука. ПОЧЕМУ ЛАТЧ, А НЕ ПАРАМЕТР: та же причина,
# что у _PROBE_LATCH ниже. Разбор рождается в _analyze, а нужен он ещё и в _detail_parts, который
# зовётся из main() и из _entity_blocktype через контракт card_min(hit, blob) — на этот контракт
# опираются тесты ОБЕИХ полос, и протаскивать сквозь него третий параметр ради одного факта значит
# сломать его всем. Хук — процесс на ОДНУ команду, поэтому глобальное состояние здесь честно.
_CODE_VIEW = None


def set_code_view(view):
    """Взвести разбор тела на прогон (зовёт _analyze; тесты — напрямую)."""
    global _CODE_VIEW
    _CODE_VIEW = view


# Дедуп ambiguous-карточек (UX-фикс 08.07.2026, спам-инцидент задачи 163). в3 (23.07.2026):
# ambiguous → defer, путь ambiguous-карточек из main() удалён — дедуп в бою НЕ зовётся. Хелперы
# (_dedup_bump/_dedup_save_mid/_edit) оставлены как движок повторных карточек: их контракт держит
# test_guard_inbox (5), формат стора /tmp на сессию с TTL прежний.
_DEDUP_DIR = os.environ.get("PRETOOL_DEDUP_DIR") or "/tmp/cc_pretool_dedup"
_DEDUP_TTL = 4 * 3600

# Guard-маркер для headless-задач (шаг 2/6 родитель 185): когда CC_TASK_ID задан в env,
# красный блок пишет маркер-файл → демон видит → гасит claude-подпроцесс → needs_approval.
#
# МИНА 28.07.2026 (задача 12, воспроизведена прогоном). Гейт внутри headless-задачи отдаёт
# тест-процессам КОПИЮ окружения (gate.py:86 — dict(os.environ, …)), вместе с ней наследуется
# CC_TASK_ID=12. Гард-тесты запускают хук ПОДПРОЦЕССОМ с красной фикстурой, а каталог был
# КОНСТАНТОЙ без подмены через env — патч константы в памяти на подпроцесс не действует по
# определению. Итог: фикстура записала БОЕВОЙ /tmp/cc_guard_block/12.json, монитор демона увидел
# его и прервал ЖИВУЮ задачу. Виновники найдены прогоном всего набора с унаследованным
# CC_TASK_ID: test_no_push_leak, test_pretool_commit_msg, test_pretool_infoflags,
# test_pretool_probe_dedup — каждый спавнит хук с red-фикстурой.
GUARD_BLOCK_DIR = "/tmp/cc_guard_block"        # БОЕВОЙ каталог; путь берётся В МОМЕНТ ЗАПИСИ
TEST_BLOCK_DIR = "/tmp/cc_guard_block_test"    # безопасное умолчание ТЕСТ-прогона
BLOCK_DIR_ENV = "PRETOOL_BLOCK_DIR"            # явная подмена каталога тестом
TEST_MARKER_PREFIX = "test-"                   # монитор открывает ровно «<tid>.json» → префикс ему невидим

# Признак ТЕСТ-ПРОГОНА, видимый САМОМУ ХУКУ — в том числе когда его запустили ПОДПРОЦЕССОМ.
# Почему подпроцесс это увидит: тесты строят окружение как dict(os.environ) и отдают его в
# subprocess.run(env=…) — переменные наследуются ВНИЗ по дереву процессов, в отличие от патча
# константы в памяти теста. Почему это НЕ спутать с боем: ORCH_TEST_MODE=1 и PRETOOL_NOPUSH=1
# гейт ставит ВСЕМ тест-процессам (gate.py:86 и :164), а демон ОБЕ снимает с окружения боевого
# claude -p (orchestrator_daemon.py:903-904, child_env.pop) — в живой headless-задаче их нет
# ФИЗИЧЕСКИ. Направление ошибки безопасное: лишний «тест» уводит маркер в сторону, но САМ БЛОК
# команды остаётся — хук всё равно возвращает deny/ask.
_TEST_RUN_ENVS = ("PRETOOL_TEST_RUN", "ORCH_TEST_MODE", "PRETOOL_NOPUSH", "PYTEST_CURRENT_TEST")


def is_test_run(env=None):
    """Идёт ли ТЕСТ-прогон с точки зрения ХУКА (см. _TEST_RUN_ENVS выше)."""
    e = os.environ if env is None else env
    return any((e.get(k) or "").strip() for k in _TEST_RUN_ENVS)


# ─────────── ЕДИНЫЙ ПРЕДИКАТ ПРОБЫ (класс «проба рождает боевую карточку», 01.08.2026) ───────────
# ПОЧЕМУ КЛАСС, А НЕ ЧАСТНОСТЬ. К владельцу ведут ДВА канала, и до сих пор у каждого был СВОЙ,
# НЕСОВПАДАЮЩИЙ признак пробы — поэтому каждый признак закрывал ровно то, что другой оставлял
# открытым, и ни один не закрывал оба:
#   канал 1 «прямой пуш» (_push → notify.send_card → инбокс 1160 / личка) слушал ТОЛЬКО
#           PRETOOL_NOPUSH=1 и _is_test_script(cmd);
#   канал 2 «маркер → демон → devbot» (_guard_write_marker → needs_approval → карточка с кнопками,
#           плюс напоминание в личку через 3 ч с force=True, которое мут вообще не глушит)
#           не слушал НИ ОДНОГО признака — маркер писался безусловно.
# Отсюда две зеркальные течи: проба, объявившая себя через ORCH_TEST_MODE/PRETOOL_TEST_RUN,
# уводила маркер в тест-каталог, но БОЕВОЙ ПУШ всё равно летел владельцу; проба, опознанная как
# тест-скрипт, пуш не слала, но писала БОЕВОЙ МАРКЕР — и владелец получал ту же карточку вторым
# путём. Пять заходов подряд (117, 135, 140, 142, 143) умерли на этом: задача, чинившая изоляцию,
# сама рождала владельцу боевую карточку из собственной пробы, и дефект блокировал свой же фикс.
# Теперь признак ОДИН и его слушают ОБА канала — «наполовину изолированной» пробы больше нет.
#
# ТРЕТИЙ ИСТОЧНИК ПРИЗНАКА — САМА КОМАНДА. Внутри живой headless-задачи демон СНИМАЕТ тест-флаги
# с окружения (orchestrator_daemon: child_env.pop ORCH_TEST_MODE/PRETOOL_NOPUSH) — это правильно и
# намеренно, иначе боевая задача притворилась бы тестом. Но следствие: у пробы, запускаемой ВНУТРИ
# такой задачи, не было НИ ОДНОГО способа сказать «я проба» — env ей не принадлежит, а требование
# «работай в тест-режиме» в тексте ТЗ ручкой не является (замер 24.07: слово в задании ничего не
# переключает). Круг замыкался. Разрывает его env-ПРЕФИКС В ТЕКСТЕ КОМАНДЫ: `PRETOOL_TEST_RUN=1
# venv/bin/python3 fx.py` — хук видит СТРОКУ команды всегда, даже когда его собственное окружение
# боевое. Заодно снят known-класс «префикс перед своей командой не работает»: раньше он молча не
# работал (живой хук наследует env сессии, а не команды), теперь работает ровно как написано.
#
# НАПРАВЛЕНИЕ ОШИБКИ БЕЗОПАСНОЕ и это главное свойство: пометка «проба» НЕ ДАЁТ НИКАКИХ ПРАВ.
# Решение хука (deny/ask) не меняется ни на йоту, жёсткий блок остаётся жёстким, секреты остаются
# секретами, команда без «да» не исполняется. Пометка глушит ТОЛЬКО каналы владельца и уводит
# маркер в тест-каталог. Худшее, что делает ложная «проба», — владелец не увидит карточку о
# команде, которая всё равно не выполнилась; факт при этом остаётся в журнале гарда и в тексте,
# который получает исполнитель. Честный предел назван прямо: агент с bash на этой машине может
# написать префикс сам — это граница против ШУМА (проба ≠ бой), а не против намеренного противника
# с тем же uid; от подделки прав защищает замок происхождения, и он здесь не тронут.
_PROBE_PREFIX_ENVS = _TEST_RUN_ENVS      # те же имена, что в окружении: одна ручка, два способа задать
_PROBE_LATCH = False                     # взводится в main() ОДИН раз, до любой записи маркера


def _cmd_declares_probe(cmd):
    """Объявила ли САМА КОМАНДА, что она проба: ведущий env-префикс `VAR=1 …` с одним из
    _PROBE_PREFIX_ENVS. Читаем ровно ведущие присваивания (до первого не-`VAR=val` токена) —
    имя переменной в середине строки (в тексте, в аргументе, в кавычках) объявлением НЕ является,
    иначе пометкой стал бы любой пересказ. Сбой разбора → False (в сторону боя, не тише)."""
    try:
        for t in shlex.split(cmd or ""):
            if not _ENV_ASSIGN.match(t):
                return False              # ведущие присваивания кончились — дальше уже команда
            name, _, val = t.partition("=")
            if name in _PROBE_PREFIX_ENVS and val.strip():
                return True
    except Exception:
        return False
    return False


def is_probe(cmd="", env=None):
    """ЕДИНЫЙ признак пробы для ОБОИХ каналов владельца. Три источника, любой достаточен:
      • окружение хука (_TEST_RUN_ENVS) — работает для гейта и тест-подпроцессов;
      • env-префикс в самой команде — единственный, доступный пробе внутри живой задачи;
      • тест-скрипт по имени/пути (_is_test_script) — прежняя эвристика, теперь гасит ОБА канала."""
    return is_test_run(env) or _cmd_declares_probe(cmd) or _is_test_script(cmd)


def set_probe(on):
    """Взвести латч пробы на весь прогон хука. ПОЧЕМУ ЛАТЧ, А НЕ ПАРАМЕТР: маркер пишется из ДВУХ
    веток main() (жёсткая по живой сущности и обычная карточка), а пуш — из третьего места;
    параметр пришлось бы протаскивать в каждую, и СЛЕДУЮЩАЯ добавленная ветка про него забыла бы —
    ровно так и появилась течь, которую мы чиним. Латч закрывает ветки ПО ПОСТРОЕНИЮ."""
    global _PROBE_LATCH
    _PROBE_LATCH = bool(on)


def isolated(env=None):
    """Идёт ли изоляция каналов владельца: тест-прогон по окружению ИЛИ взведённый латч пробы.
    Единственный источник правды для block_dir/marker_name/_push/_edit."""
    return is_test_run(env) or _PROBE_LATCH


def block_dir(env=None):
    """Каталог маркеров: явная подмена (env) → тест-умолчание → боевой. Читается В МОМЕНТ ЗАПИСИ
    (как PRETOOL_GUARD_LOG ниже) — поэтому подмена работает и для хука-подпроцесса."""
    e = os.environ if env is None else env
    explicit = (e.get(BLOCK_DIR_ENV) or "").strip()
    if explicit:
        return explicit
    return TEST_BLOCK_DIR if isolated(e) else GUARD_BLOCK_DIR


def marker_name(task_id, env=None):
    """Имя файла маркера. В тест-прогоне номер ЖИВОЙ задачи в имя НЕ попадает: префикс делает
    файл невидимым для монитора демона даже если каталог почему-то остался боевым."""
    return "%s%s.json" % (TEST_MARKER_PREFIX if isolated(env) else "", task_id)


# ДЕНЬГИ БОЛЬШЕ НЕ ИСКЛЮЧЕНИЕ ИЗ ПРАВИЛА ОБЪЕКТА (02.08.2026, класс пяти пустых карточек).
# Было: `_ALWAYS_CARD = ("void_last", "add_transaction")` — деньги спрашивали ВСЕГДА, даже когда
# объекта нет. Основанием служила природа `void_last()` («сними последнюю» зовётся без аргументов).
# Основание оказалось ложным дважды: цель у такого вызова ЕСТЬ — это САМ РАЗОБРАННЫЙ ВЫЗОВ, и он
# теперь называется объектом («вызов void_last()»); а прикрытие исключением получала не природа
# операции, а СОВПАДЕНИЕ СЛОВА — карточка «проводка ДЕНЕГ в кассу · Объект: — · Число: —» об
# операции, которой в скрипте нет. Правило стало ОДНО для всех классов: нет названной цели —
# карточки нет, есть строка в журнале. Деньги остаются высшим видом ДРУГИМ способом: у настоящего
# вызова цель есть всегда (кошелёк, сумма или сам вызов), поэтому настоящая проводка спрашивает
# как прежде. Жёсткий блок (процессы/секреты/живая сущность) правила объекта не касался и не
# касается — он приходит владельцу всегда, мимо card_gate.

# Строка «Объект:» готовой карточки, У КОТОРОЙ ЕСТЬ ЗНАЧЕНИЕ (прочерк «—» значением не считаем).
_MARKER_OBJECT_RE = re.compile(r"(?m)^Объект:[ \t]*(?!—[ \t]*$)\S")


def marker_has_object(hit, card):
    """Есть ли у маркера ОБЪЕКТ операции. Вторая линия: карточка без объекта бессмысленна,
    подтверждать в ней нечего. Блок команды это НЕ ослабляет — хук всё равно вернёт deny/ask;
    маркер лишь канал «скажи демону», и пустую карточку демону показывать незачем.

    29.07.2026 — БЛИЗОРУКОСТЬ СНЯТА, и это НЕ косметика. Проверкой была `\\d` по тексту всей
    карточки, то есть «есть хоть одна цифра». Она резала ровно наоборот доктрине: шаблон операций
    с парком несёт «Лист1» — цифра там есть ВСЕГДА (ложное «объект есть»), а `pkill ngrok`,
    `systemctl stop nginx` и `DELETE FROM sessions` цифры не несут вовсе — маркер демону НЕ
    уходил, даже когда объект честно извлечён. Теперь смотрим ту же величину, что и card_gate:
    подписанную строку «Объект:» со значением. 02.08.2026: денежного исключения здесь больше нет —
    обе линии говорят ОДНО И ТО ЖЕ (см. блок над этой функцией и card_gate)."""
    return bool(_MARKER_OBJECT_RE.search(card or ""))

# ── HARD-BLOCK: журнал жёстких блоков (JSONL). Путь берётся В МОМЕНТ ЗАПИСИ (тесты подменяют
# PRETOOL_GUARD_LOG). Пишется ТОЛЬКО факт блока: событие + сама команда; значений секретов в
# команде нет (файл секретов не читается — он как раз заблокирован).
GUARD_LOG = "/tmp/cc_pretool_guard.log"
HARD_BLOCK_HITS = ("proc_hard_block", "env_hard_block")

# Боевые процессы контура: остановка = обрыв живых задач/очередей → агенту НЕЛЬЗЯ вообще.
# Сверка по НОРМАЛИЗОВАННОМУ токену (нижний регистр, «-» и «.» → «_»), т.е. splinter.service,
# orchestrator-daemon, /root/…/moderation_bot.py — одно и то же имя.
_PROTECTED_PROCS = ("splinter", "orchestrator_daemon", "userbot", "moderation_bot", "pc_agent")
_KILL_CMDS = {"kill", "pkill"}
_HARD_VERBS = {"kill", "stop"}                    # systemctl kill|stop → жёстко
_GREEN_VERBS = {"restart", "start"}               # свои сервисы: штатный поток → defer (в2, 339/340)
_SVC_VERBS = {"kill", "stop", "restart", "start", "reload", "try-restart",
              "force-reload", "enable", "disable", "mask", "unmask"}
# Поисковые утилиты: их ШАБЛОН — данные (класс «данные ≠ команда»).
_SEARCH_CMDS = {"grep", "egrep", "fgrep", "zgrep", "rg", "ag", "ack", "sed", "awk", "gawk", "mawk"}
_PATTERN_FLAGS = {"-e", "-E", "-n", "--regexp", "--expression"}
# Обёртки: команда-цель идёт ПОСЛЕ них (иначе `sudo systemctl stop splinter` проскочил бы).
_WRAPPERS = {"sudo", "doas", "env", "nohup", "nice", "ionice", "time", "timeout",
             "stdbuf", "xargs", "systemd-run"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_ENV_FILE = re.compile(r"(?:^|[^\w.\-])\.env[\w.\-]*")          # .env, .env.local, /root/app/.env
# Признаки ИСПОЛНЕНИЯ внутри «шаблона»: такой токен шаблоном не считаем (дыра
# `awk 'BEGIN{system("…")}'` / `grep -e "$(…)"` закрыта) — он и остаётся под сканом, и раскрывается.
_EXEC_IN_PATTERN = re.compile(r"\$\(|`|\bsystem\s*\(|\bpopen\s*\(|\|\s*['\"]?\s*(?:sh|bash|zsh|xargs)\b")
_SUBST = re.compile(r"\$\(([^()]{1,400})\)|`([^`]{1,400})`"
                    r"|(?:system|popen)\s*\(\s*['\"]([^'\"]{1,400})['\"]")

_BLOCK_TEXT = {
    "proc_hard_block": "⛔ ЖЁСТКИЙ БЛОК (proc_hard_block): остановка боевого процесса контура%s. "
                       "Карточка владельцу НЕ шлётся, approve НЕВОЗМОЖЕН — агент боевые процессы "
                       "не гасит НИКОГДА (обрыв живых задач и очередей). Нужна остановка — "
                       "требуется решение владельца: переставь задачу в 328 после его ответа.",
    "env_hard_block": "⛔ ЖЁСТКИЙ БЛОК (env_hard_block): обращение к файлу секретов%s. "
                      "Карточка владельцу НЕ шлётся, approve НЕВОЗМОЖЕН — секреты агенту не "
                      "показываются ни в каком виде. Нужно значение ключа — владелец передаёт его сам.",
}


def _guard_log(event, cmd, why=""):
    """Строка JSONL о жёстком блоке. Best-effort: сбой журнала НЕ отменяет блок (решение важнее)."""
    try:
        line = json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event,
                           "cmd": " ".join((cmd or "").split())[:400], "why": why},
                          ensure_ascii=False)
        with open(os.environ.get("PRETOOL_GUARD_LOG") or GUARD_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _guard_write_marker(task_id, hit, card, blocktype=None):
    """Записать маркер красного блока для демона-наблюдателя. blocktype='hard' → демон закроет
    задачу failed БЕЗ кнопки approve (живая сущность); None → прежнее поведение (needs_approval)."""
    if not task_id:
        return
    # Вторая линия (28.07): маркер без объекта операции демону не отдаём — подтверждать в такой
    # карточке нечего. hard-блок исключение: это не карточка на «да», а закрытие задачи failed.
    if blocktype != "hard" and not marker_has_object(hit, card):
        return
    try:
        d = block_dir()
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, marker_name(task_id))
        tmp = path + ".tmp"
        payload = {"task_id": task_id, "hit": hit, "card": card}
        # ЗАМОК ПРОИСХОЖДЕНИЯ КАРТОЧКИ (31.07.2026): одноразовый токен прогона, который демон
        # положил в env запускаемой задачи. Демон сверяет его и по нему отличает маркер, писанный
        # ХУКОМ этого прогона, от протухшего/чужого. Токена в env нет (ручной прогон, старый
        # демон) → поле не пишем: демон покажет карточку как несверенную, но НЕ потеряет её.
        tok = (os.environ.get("CC_GUARD_TOKEN") or "").strip()
        if tok:
            payload["token"] = tok
        if blocktype:
            payload["blocktype"] = blocktype
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def _defer():
    sys.exit(0)   # ничего не печатаем → штатный permission-flow (allow/ask rules)


def can_approve(kind, hit=""):
    """False = ЖЁСТКИЙ БЛОК: ни карточки владельцу, ни «да» — обойти нельзя (deny хука).
    Единственный источник правды: по нему же main() решает, слать ли карточку/конверт."""
    return not (kind == "block" or hit in HARD_BLOCK_HITS)


def decision(kind, hit, reason):
    """Чистая функция «классификация → решение хука» (её зовут тесты, ничего не исполняя):
    block → deny (approve НЕВОЗМОЖЕН), red → ask, ambiguous/green → None (defer). в3 23.07.2026:
    ambiguous сам по себе не красный — решают слои settings (доктринальное красное там ask/deny)."""
    if kind in ("green", "ambiguous"):
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask" if can_approve(kind, hit) else "deny",
        "permissionDecisionReason": reason}}


def _emit(d):
    if d:
        print(json.dumps(d, ensure_ascii=False))
    sys.exit(0)


def _ask(reason):
    _emit(decision("red", "", reason))


# per-действие: (Что — таблица/операция, Проверь, ОТКАТ одной строкой). ОБЪЕКТ и ЧИСЛО в карточку
# кладутся ОТДЕЛЬНЫМИ подписанными строками из _detail_parts() — их отсутствие карточку не
# «обедняет», а ГАСИТ (см. card_min). Строка «Последствия» убрана 28.07.2026: карточка обязана
# читаться за ТРИ СЕКУНДЫ, а стоимость ошибки честнее показывает ОТКАТ, чем абзац про учёт.
_ACTIONS = {
    "confirmed": ("БОЕВАЯ запись в Лист1/CRM (confirmed=true)",
                  "та ли строка и значение",
                  "только ручная правка той же строки — затёртый чужой ввод не вернётся"),
    "set_fleet_oil": ("запись «ТО масло» в Лист1 Байки (колонка I)",
                      "тот ли байк и пробег",
                      "вписать прежний пробег в колонку I руками"),
    "set_fleet_service": ("запись планового ТО в Лист1 (редуктор/ABS/возд.фильтр)",
                          "тот ли байк и вид ТО",
                          "вписать прежний пробег в ту же колонку руками"),
    "add_transaction": ("проводка ДЕНЕГ в кассу (Money/Cashflow)",
                        "та ли сумма, знак (+/−) и кошелёк",
                        "ручной сторно — обратная проводка на ту же сумму"),
    "void_last": ("отмена последней денежной проводки (Money)",
                  "точно ли ПОСЛЕДНЯЯ проводка — та",
                  "провести снятую проводку заново руками"),
    "create_booking": ("создание брони в CRM «клиенты»",
                       "тот ли клиент, байк и даты",
                       "удалить заведённую строку брони руками"),
    "activate_booking": ("активация брони → «В аренде» (CRM)",
                         "тот ли байк и клиент",
                         "вернуть строке прежний статус «Бронь» руками"),
    "closing_upsert": ("запись закрытия аренды (CRM)",
                       "тот ли клиент и суммы закрытия",
                       "переписать строку закрытия прежними суммами руками"),
    "delete_event": ("УДАЛЕНИЕ события из истории",
                     "то ли событие",
                     "ОТКАТА НЕТ — строка стирается безвозвратно"),
    "DOWRITE": ("скрипт помечен DOWRITE=1 — реальная запись (не dry-run)",
                "что именно пишет скрипт",
                "зависит от скрипта — прочитай его ДО «да»"),
    "proc_ctl": ("остановка/перезапуск процесса или systemd-сервиса",
                 "тот ли процесс и переживёт ли контур паузу",
                 "поднять обратно (start) — но оборванные задачи не вернутся"),
    "sqlite": ("SQL-запись в БД вне memory.db (UPDATE/DELETE/INSERT/DROP)",
               "та ли БД и таблица",
               "обратный SQL руками — бэкапа БД гард не делает"),
}
# в3 23.07.2026: штатно НЕдостижимо (ambiguous → defer, main() до карточки не доходит);
# оставлено фолбэком _card на случай red-hit вне _ACTIONS (карточка не падает, а страшнеет).
_AMBIGUOUS = ("не распознал операцию — скрипт может писать в рабочие данные",
              "команда в карточке — подтверждай, только если понимаешь, что она делает",
              "неизвестен — операция не разобрана")


def _find(patterns, blob):
    for p in patterns:
        m = re.search(p, blob, re.IGNORECASE)
        if m:
            g = (m.group(1) or "").strip().strip('\'"').strip()
            if g:
                return g
    return ""


# ══ ОБЪЕКТ и ЧИСЛО карточки ═══════════════════════════════════════════════════════════════════
# Имена полей — ЖИВЫЕ, снятые с bridge_client (тот же класс, что «мок обязан копировать живой
# формат прода», CLAUDE.md). Подписи Bridge:
#   set_fleet_oil(number=…, oil_km=…)             set_fleet_service(number=…, kind=…, km=…)
#   add_transaction(group=…, amount=…, bike=…)    void_last(group=…)
#   create_booking(bike=…, name=…, date_start=…)  activate_booking(bike=…, name=…)
#   closing_upsert(booking_id=…, bike=…, name=…)  delete_event(msg_id=…, group=…)
# ДО 28.07.2026 шаблоны искали plate=/client=/wallet=/\bkm= — таких имён у Bridge НЕТ ни одного
# («\bkm» вдобавок физически не совпадает внутри «oil_km»: подчёркивание — словесный символ).
# Итог был двойной: объект не извлекался НИКОГДА, а «объект есть?» решала цифра в ТЕКСТЕ шаблона
# действия — «Лист1» → \d — то есть для операций с парком объект считался найденным ВСЕГДА.
_P_BIKE = [r"\b(?:number|plate)\s*[=:]\s*['\"]?([A-Za-z0-9][A-Za-z0-9\- ]{1,11})",
           r"\bbike(?:_id|_no|_num|_number)?\s*[=:]\s*['\"]?([A-Za-z0-9][A-Za-z0-9\- ]{1,11})",
           r"['\"](?:number|plate|bike)['\"]\s*:\s*['\"]?([A-Za-z0-9][A-Za-z0-9\- ]{1,11})"]
_P_CLIENT = [r"\b(?:name|client)\s*[=:]\s*['\"]([^\"']{2,30})",
             r"['\"](?:name|client)['\"]\s*:\s*['\"]([^\"']{2,30})"]
_P_CLIENT_STRICT = [r"\bclient\s*[=:]\s*['\"]([^\"']{2,30})",      # generic-hit: «name» слишком
                    r"['\"]client['\"]\s*:\s*['\"]([^\"']{2,30})"]  # общее слово, чтобы им врать
_P_KM = [r"\b(?:oil_km|km|mileage|odo|пробег)\s*[=:]\s*['\"]?(\d{2,7})",
         r"['\"](?:oil_km|km|mileage)['\"]\s*:\s*['\"]?(\d{2,7})"]
_P_KIND = [r"\bkind\s*[=:]\s*['\"]?(\w{2,12})", r"['\"]kind['\"]\s*:\s*['\"](\w{2,12})"]
_P_AMOUNT = [r"\bamount\s*[=:]\s*['\"]?(-?\d[\d ]{0,9})",
             r"['\"]amount['\"]\s*:\s*['\"]?(-?\d+)",
             r"\bsum\s*[=:]\s*['\"]?(-?\d[\d ]{0,9})"]
_P_WALLET = [r"\b(?:group|wallet|account)\s*[=:]\s*['\"]?([\w\- ]{2,20})",
             r"['\"](?:group|wallet|account)['\"]\s*:\s*['\"]([\w\- ]{2,20})"]
_P_DATE = [r"\b(?:date_start|date_end|date_return)\s*[=:]\s*['\"]?(\d[\d.\-/]{5,9})",
           r"['\"](?:date_start|date_end|date_return)['\"]\s*:\s*['\"](\d[\d.\-/]{5,9})"]
_P_SUM_FIELD = [r"\b(?:deposit|initial_pay|total_due|surcharge_days|surcharge_fuel)"
                r"\s*[=:]\s*['\"]?(-?\d[\d ]{0,9})"]
_P_MSGID = [r"\bmsg_id\s*[=:]\s*['\"]?([\w:.\-]{2,40})",
            r"['\"]msg_id['\"]\s*:\s*['\"]([\w:.\-]{2,40})"]
_P_TABLE = [r"UPDATE\s+['\"`]?(\w+)", r"INSERT\s+INTO\s+['\"`]?(\w+)", r"DELETE\s+FROM\s+['\"`]?(\w+)",
            # DROP TABLE входит в _SQLITE_WRITE, но в объект НЕ извлекался: снос таблицы оставался
            # без объекта, а значит (правило 29.07) и без карточки. Самая дорогая форма — теперь тоже.
            r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?['\"`]?(\w+)"]
# Файл БД: у «SQL в чужую БД» объект — это ИМЕННО БАЗА, а не только таблица (`users` есть везде).
_P_DBFILE = [r"([\w./\\-]{1,60}\.db)\b"]
_P_DOC = [r"write_doc\s*\(\s*(?:name|id)\s*=\s*['\"]?([\w\-]+)"]
_P_DIGIT = re.compile(r"\d")

_HITS_FLEET = ("set_fleet_oil", "set_fleet_service")
_HITS_CRM = ("create_booking", "activate_booking", "closing_upsert")


def _bike_bit(blob):
    """Байк как ОБЪЕКТ: у Bridge он резолвится ПО НОМЕРУ (last 3-4 цифры), поэтому значение без
    единой цифры байком не считаем — иначе `number=str(number)` из чужого тела станет «объектом»."""
    b = _find(_P_BIKE, blob)
    return "байк " + b if b and _P_DIGIT.search(b) else ""


# ── ОБЪЕКТ, КОТОРЫЙ ВЫЗОВ НЕСЁТ, НО ЧЬЁ ЗНАЧЕНИЕ ВЫЧИСЛЯЕТСЯ (класс «корень А», 02.08.2026) ──
# Извлечение объекта шло регуляркой `ключ=значение` и умело видеть ТОЛЬКО ЛИТЕРАЛ. Живой скрипт
# пишет `set_fleet_oil(number=plate, oil_km=km)` — объект не извлекался, card_gate гасил карточку,
# и владелец о НАСТОЯЩЕЙ записи в Лист1 не узнавал вовсе. Гард при этом не слабел (ask оставался,
# без «да» команда не шла) — но и спросить «да» было не у кого: операция молча упиралась в стену.
# Разобранный вызов различает то, чего текст различить не может: аргумента НЕТ (голое упоминание,
# `print('set_fleet_oil')`) и аргумент ЕСТЬ, а значение станет известно только при запуске.
# ДЕНЬГИ ПОДКЛЮЧЕНЫ 02.08.2026 (кошелёк): пока их карточка не гасилась никогда, извлекать объект
# было незачем; теперь правило объекта одно для всех, и вычисляемый `group=wallet` обязан называться
# — иначе НАСТОЯЩАЯ проводка молча ушла бы в журнал.
_ARG_OBJ = {"bike": ("number", "plate", "bike"), "client": ("name", "client"),
            "wallet": ("group", "wallet", "account"), "amount": ("amount", "sum")}
_ARG_LABEL = {"bike": "байк", "client": "клиент", "wallet": "кошелёк", "amount": "сумма"}


def _call_args(hit):
    """Именованные аргументы РАЗОБРАННОГО вызова операции → {имя: литерал|None} либо None, если
    вызова в разборе нет вовсе (слепое тело, чужой синтаксис, голое упоминание)."""
    view = _CODE_VIEW
    if not view:
        return None
    return (view.get("calls") or {}).get(hit)


def _call_arg_literal(hit, kind):
    """ЛИТЕРАЛЬНОЕ значение аргумента разобранного вызова (или ""). Разобранный вызов ВАЖНЕЕ текста:
    регулярка `ключ=значение` читает ВЕСЬ blob и на теле `wallet = input()` + `add_transaction(
    group=wallet, …)` выдавала «кошелёк input» — имя ПЕРЕМЕННОЙ вместо цели. Вызов знает точно."""
    kw = _call_args(hit) or {}
    for a in _ARG_OBJ.get(kind, ()):
        v = kw.get(a)
        if v:
            return str(v).strip()
    return ""


def _carried_bit(hit, kind):
    """→ подпись объекта, который РАЗОБРАННЫЙ вызов операции несёт вычисляемым значением, иначе "".
    Разбора нет / вызова нет / аргумент литеральный (его берёт обычное извлечение) → ""."""
    view = _CODE_VIEW
    if not view:
        return ""
    kw = (view.get("calls") or {}).get(hit)
    if not kw:
        return ""
    for a in _ARG_OBJ.get(kind, ()):
        if a in kw and kw[a] is None:
            return "%s — значение вычисляется (аргумент %s)" % (_ARG_LABEL[kind], a)
    return ""


def _money_call_seen(hit, blob):
    """Денежная операция ВЫЗВАНА (а не упомянута)? Разобранный вызов — точный ответ; имя вплотную
    к скобке в тексте — фолбэк для слепых тел (heredoc), где разбора нет вовсе.

    Зачем это объект: `void_last()` по своей природе зовётся БЕЗ аргументов («сними последнюю»), и
    ровно этим раньше оправдывалось исключение _ALWAYS_CARD. Цель у такого вызова всё-таки есть —
    ЭТО САМ ВЫЗОВ; назвав его, мы получаем карточку у настоящей отмены и не получаем её у слова
    в списке (`writes = ["void_last", …]` скобки не несёт)."""
    view = _CODE_VIEW
    if view is not None and _money_is_action(hit, blob, view):
        return True
    return bool(re.search(r"\b" + re.escape(hit) + r"\s*\(", blob or ""))


def _detail_parts(hit, blob):
    """ОБЪЕКТ операции и её ЧИСЛО, извлечённые ИЗ КОМАНДЫ/ТЕЛА → (obj_bits, num_bits).
    Пустой список = НЕ извлеклось. Текст шаблона действия сюда не попадает НИКОГДА — именно этим
    новое извлечение отличается от близорукой проверки по готовой карточке (marker_has_object)."""
    obj, num = [], []
    if hit in _HITS_FLEET:
        b = _bike_bit(blob) or _carried_bit(hit, "bike")
        if b:
            obj.append(b)
        if hit == "set_fleet_service":
            k = _find(_P_KIND, blob)
            if k:
                obj.append("вид ТО " + k)
        v = _find(_P_KM, blob)
        if v:
            num.append("пробег " + v)
    elif hit in _MONEY_HITS:
        # Порядок источников ЖЁСТКИЙ: разобранный вызов → «значение вычисляется» → текст. Текст
        # берётся ТОЛЬКО когда вызова в разборе нет (слепое тело): иначе регулярка тянет цель из
        # чужой строки скрипта и врёт в самом дорогом классе.
        seen = _call_args(hit) is not None
        w = _call_arg_literal(hit, "wallet")
        if w:
            obj.append("кошелёк " + w)
        else:
            cw = _carried_bit(hit, "wallet")
            if cw:
                obj.append(cw)
            elif not seen:
                w2 = _find(_P_WALLET, blob)
                if w2:
                    obj.append("кошелёк " + w2.strip())
        if seen:
            bl = _call_arg_literal(hit, "bike")
            b = ("байк " + bl) if (bl and _P_DIGIT.search(bl)) else _carried_bit(hit, "bike")
        else:
            b = _bike_bit(blob)
        if b:
            obj.append(b)
        a = _call_arg_literal(hit, "amount") or ("" if seen else _find(_P_AMOUNT, blob))
        if a:
            num.append("сумма " + a.strip())
        if not obj and _money_call_seen(hit, blob):
            obj.append("вызов %s()" % hit)      # аргументов нет по природе — цель это сам вызов
    elif hit in _HITS_CRM:
        b = _bike_bit(blob) or _carried_bit(hit, "bike")
        if b:
            obj.append(b)
        c = _find(_P_CLIENT, blob)
        if c:
            obj.append("клиент " + c)
        else:
            cc = _carried_bit(hit, "client")
            if cc:
                obj.append(cc)
        d = _find(_P_DATE, blob)
        if d:
            num.append("дата " + d)
        s = _find(_P_SUM_FIELD, blob)
        if s:
            num.append("сумма " + s.strip())
    elif hit == "confirmed":
        b = _bike_bit(blob)
        if b:
            obj.append(b)
        c = _find(_P_CLIENT_STRICT, blob)
        if c:
            obj.append("клиент " + c)
        for pats, lab in ((_P_KM, "пробег "), (_P_AMOUNT, "сумма ")):
            v = _find(pats, blob)
            if v:
                num.append(lab + v.strip())
    elif hit == "delete_event":
        e = _find(_P_MSGID, blob)
        if e:
            obj.append("событие " + e)
            if _P_DIGIT.search(e):
                num.append("ключ " + e)        # у удаления «число» — сам ключ стираемой строки
        g = _find(_P_WALLET, blob)
        if g:
            obj.append("группа " + g.strip())
    elif hit == "sqlite":
        d = _find(_P_DBFILE, blob)
        if d:
            obj.append("БД " + d)
        t = _find(_P_TABLE, blob)
        if t:
            obj.append("таблица " + t)
    elif hit == "DOWRITE":
        d = _find(_P_DOC, blob)
        if d:
            obj.append("док " + d)
    elif hit == "proc_ctl":
        tgt = _find([r"proc_target=([^\n]{1,60})"], blob)   # маркер кладёт classify()
        if tgt:
            obj.append("цель " + tgt)
            pid = _find([r"\b(\d{2,7})\s*$"], tgt)          # kill по PID: число операции — сам PID
            if pid:
                num.append("PID " + pid)
    return obj, num


def card_min(hit, blob=""):
    """ОБЯЗАТЕЛЬНЫЙ МИНИМУМ карточки → (ОБЪЕКТ, ЧИСЛО) строками; пусто = не извлеклось.
    Доктрина: карточка красной зоны говорит ЧТО меняется, у какого ОБЪЕКТА, какое ЧИСЛО и как
    ОТКАТИТЬ. Родится ли карточка — решает card_gate(), а не эта функция: здесь только извлечение."""
    obj, num = _detail_parts(hit, blob)
    return ", ".join(obj), ", ".join(num)


def card_gate(hit, obj, num=""):
    """ЕДИНОЕ ПРАВИЛО КАРТОЧКИ, общее с полосой ПК (29.07.2026) → True = карточка, False = журнал.

        • ОБЪЕКТ обязателен ВСЕГДА. Нет объекта — признак сработал на ПОДСТРОКЕ, а не на действии
          (`print('set_fleet_oil')`): показывать владельцу нечего, идёт строка в журнал.
        • ЧИСЛО карточку НЕ гейтит НИКОГДА. Оно есть там, где операция несёт его ПО СВОЕЙ ПРИРОДЕ
          (сумма, пробег, дата, ключ, PID), и честно пусто там, где не несёт. Поле остаётся, в нём
          прочерк.
        • Жёсткий блок и секреты спрашивают всегда — как и было (они сюда не заходят вовсе).
        • ДЕНЬГИ С 02.08.2026 — НЕ ИСКЛЮЧЕНИЕ: у настоящего вызова цель есть всегда (кошелёк,
          сумма либо сам разобранный вызов), а безобъектная карточка «проводка ДЕНЕГ» пять раз
          за трое суток означала не проводку, а совпадение слова. См. блок над marker_has_object.

    ЧТО ЭТИМ ЧИНИТСЯ. Правило было «нет объекта ИЛИ числа → карточки нет», и числа по природе не
    несут ЧЕТЫРЕ операции — отмена последней проводки (деньги!), стоп сервиса по имени, pkill по
    имени, SQL в чужую БД. Все четыре молча уходили в журнал: гард не слабел (ask оставался), но
    владелец о них не узнавал. Полоса ПК тем временем гасила карточку только когда пусто И объект,
    И число — то есть безобъектная команда с любой цифрой карточку РОЖДАЛА. Обе полосы сведены
    сюда: одна функция, одно правило, одинаковое имя в обоих репозиториях."""
    return bool((obj or "").strip())


# ТЕСТ-СУЩНОСТИ (класс 23.07.2026, порт из stash@{1} 26.07.2026). Доктрина: боевую запись в живые
# таблицы (Лист1/CRM) можно одобрять «да» ТОЛЬКО для ТЕСТ-сущностей write-смока; живая сущность —
# решение владельца вне агента. Функции лежали в стэше и НИ РАЗУ не вызывались — защита не работала.
# ЖИВЫЕ ИМЕНА ПОЛЕЙ, а не идеализированные (класс «мок ≠ живой формат», тот же, что закрыт 28.07 в
# _P_BIKE — но ВТОРУЮ копию регулярок тогда не догнали, и правило 23.07 полтора месяца не срабатывало
# по байкам ВООБЩЕ). Живая подпись Bridge — `set_fleet_oil(number=…)`, `create_booking(bike=…, name=…)`,
# `activate_booking(bike, name)`: полей `plate=`/`client=` у моста НЕТ НИ ОДНОГО. Именно поэтому проба
# `set_fleet_oil(number='6789', oil_km=27000)` отдавала entity=None → «мягко» → карточка владельцу.
_ENTITY_CLIENT_RE = re.compile(r"""\b(?:client|name)\s*[=:]\s*['"](.*?)['"]""")
_ENTITY_BIKE_RE   = re.compile(r"""\b(?:number|plate|bike)\s*[=:]\s*['"](.*?)['"]""")
_ENTITY_ANY_RE    = re.compile(r"""\b(?:client|name|bike|number|plate)\s*[=:]\s*['"](.*?)['"]""")

_ENTITY_HITS_CLIENT = frozenset(("confirmed", "create_booking", "activate_booking", "closing_upsert"))
_ENTITY_HITS_PLATE  = frozenset(("set_fleet_oil", "set_fleet_service"))
# ЖИВЫЕ ТАБЛИЦЫ (Лист1 Байки / CRM): у этих операций сущность есть ПО ПРИРОДЕ — клиент или байк.
# Деньги (add_transaction/void_last) и удаление события сюда НЕ входят намеренно: они сущности не
# несут вовсе, и ужесточать их — значит остановить владельца там, где разрешать нечего.
_ENTITY_HITS_LIVE = _ENTITY_HITS_CLIENT | _ENTITY_HITS_PLATE


def _extract_first_entity(hit, blob):
    """Извлечь сущность (клиент/байк) из blob для ТЕСТ-entity классификации hard/soft.
    Возвращает строку-сущность или None (не извлечено / хит не поддерживает сущность).
    У клиентских операций сначала ищем ЧЕЛОВЕКА (client/name), затем байк — карточка про клиента
    информативнее; у операций парка сущность одна."""
    if hit in _ENTITY_HITS_CLIENT:
        m = _ENTITY_CLIENT_RE.search(blob or "") or _ENTITY_BIKE_RE.search(blob or "")
        return m.group(1).strip() if m else None
    if hit in _ENTITY_HITS_PLATE:
        m = _ENTITY_BIKE_RE.search(blob or "")
        return m.group(1).strip() if m else None
    return None


def _is_test_entity(entity):
    """True если entity — «ТЕСТ…» сущность (approve разрешён в write-смоках)."""
    return bool(entity) and str(entity).strip().lower().startswith("тест")


def _blob_has_test_entity(blob):
    """Есть ли в теле команды ХОТЬ ОДНА явно ТЕСТОВАЯ сущность — в любом из опознаваемых полей.
    Предохранитель для write-смока, который называет ТЕСТ-сущность в поле, которого ветка этого
    хита не читает (например `set_fleet_oil` рядом с `name='ТЕСТ Иван'`): смок остаётся живым."""
    return any(_is_test_entity(v) for v in _ENTITY_ANY_RE.findall(blob or ""))


def _entity_blocktype(hit, blob):
    """ЧИСТЫЙ решатель (его зовут main и тесты): → 'hard' | None.
      живая сущность извлечена и НЕ ТЕСТ → 'hard'  — approve недоступен физически;
      ТЕСТ-сущность                      → None    — мягко, кнопка «да» как раньше;
      сущность НЕ извлечена, но операция пишет в ЖИВЫЕ ТАБЛИЦЫ И НЕСЁТ ОБЪЕКТ → 'hard' (01.08.2026);
      сущность НЕ извлечена, объекта тоже нет → None: судим по ДЕЙСТВИЮ, а не по подстроке;
      сущность НЕ извлечена, операция сущности не несёт (деньги/удаление) → None, как было.

    ЧТО ИЗМЕНЕНО И ПОЧЕМУ. Прежнее правило гласило «сущность не извлечена → мягко: молчание не
    повод ужесточать» — и на нём в живые таблицы уезжала любая запись, чьё поле не совпало с
    регуляркой: гард молчаливо считал, что раз он не понял ОБЪЕКТ, то и решать нечего. Наоборот:
    для операции, которая по природе пишет в Лист1/CRM, «объект не опознан» — это худший случай, а
    не безобидный. Доктрина 23.07 требует пометки ТЕСТ у любой сущности, которую пишем в живые
    таблицы; значит отсутствие пометки — отказ, а не смягчение. Теперь: НЕТ пометки ТЕСТ → в живые
    таблицы не пишем ВОВСЕ (deny, кнопки нет). Деньги и удаление не тронуты — там сущности нет по
    природе, и ложный hard отнял бы у владельца право разрешить."""
    entity = _extract_first_entity(hit, blob)
    if entity:
        return None if _is_test_entity(entity) else "hard"
    if hit in _ENTITY_HITS_LIVE and not _blob_has_test_entity(blob):
        # ГРАНИЦА УЖЕСТОЧЕНИЯ — ОБЪЕКТ ОПЕРАЦИИ, а не само красное слово. Жёстко закрываем только
        # то, что похоже на НАСТОЯЩУЮ запись: объект в команде есть, а пометки ТЕСТ у него нет —
        # тогда молчание о сущности и правда означает отказ. Если объекта нет вовсе (голое
        # упоминание имени операции в тексте, `print('set_fleet_oil')`), решать нечего: там нет
        # ни записи, ни того, что владелец мог бы подтвердить, — работает прежнее правило
        # МИНИМУМА КАРТОЧКИ (строка в журнал, ask). Иначе гард начал бы отказывать ПО ПОДСТРОКЕ,
        # ровно против правила «судить по ДЕЙСТВИЮ, а не по слову в команде».
        obj, _num = card_min(hit, blob)
        if (obj or "").strip():
            return "hard"
    return None


def _is_test_script(cmd):
    """Тестовый прогон: запускаемый .py лежит в scratchpad (/tmp/claude-*/…/scratchpad/) или несёт
    _dryrun/_test в имени. Влияние: 🧪-пометка первой строкой карточки И пуш в Telegram НЕ шлётся
    (фикс утечек 01–05.07: тестовые красные карточки летели Филиппу в личку; терминальная карточка
    и решение ask ОСТАЮТСЯ — классификацию red/ambiguous/green это НЕ меняет). Боевые скрипты из
    репо — без пометки, с пушем."""
    try:
        toks = shlex.split(cmd)
    except Exception:
        toks = cmd.split()
    for t in toks:
        if not t.endswith(".py"):
            continue
        if "/tmp/claude-" in t and "/scratchpad/" in t:
            return True
        # Каталог разведки из правила R17 (29.07.2026): «разведочные/одноразовые скрипты пишутся во
        # ВРЕМЕННЫЙ каталог /tmp/tb_scratch и запускаются оттуда». Раз правило объявляет содержимое
        # каталога одноразовой разведкой, то запуск ОТТУДА — проба по определению, и владельцу о ней
        # знать незачем. ЧЕСТНЫЙ ПРЕДЕЛ: настоящая разовая операция, запущенная из этого каталога,
        # карточки владельцу тоже не даст — она при этом НЕ исполнится (решение остаётся ask/deny),
        # а исполнитель увидит перехват с полным текстом и повторит вызов из нормального места.
        if "/tmp/tb_scratch/" in t:
            return True
        base = os.path.basename(t)
        if "_dryrun" in base or "_test" in base:
            return True
    return False


def _card(hit, blob="", test=False, cmd="", count=1):
    """Карточка красной зоны: ЧТО меняется → у какого ОБЪЕКТА → какое ЧИСЛО → одна строка ОТКАТА.
    Четыре подписанные строки читаются за три секунды, объект и число ищутся глазом мгновенно.
    Прочерк в «Объект»/«Число» — знак, что минимум НЕ собран: в бою такая карточка не рождается
    вовсе (card_min в main()), прочерк виден только при прямом вызове (тесты, фолбэк вне _ACTIONS)."""
    ambiguous = hit == "ambiguous" or hit not in _ACTIONS
    what, check, back = _AMBIGUOUS if ambiguous else _ACTIONS[hit]
    obj, num = card_min(hit, blob)
    head = "🧪 ТЕСТ (dry-run, не реальная операция)\n" if test else ""
    # UX-фикс 08.07 (инцидент 163): ambiguous-карточка НЕСЁТ саму команду — владелец решает прямо из
    # уведомления («глянь выше вручную» в headless некуда). Повтор той же команды в задаче → счётчик ×N.
    cmd_line = ""
    if ambiguous:
        c = " ".join((cmd or "").split())
        if c:
            cmd_line = "Команда: " + (c[:200] + "…" if len(c) > 200 else c) + "\n"
    rep = ("Повтор: ×%d — та же команда в этой задаче (карточка обновлена, новых не шлю)\n" % count) \
        if count > 1 else ""
    return (head +
            "🔴 КРАСНОЕ\n" + rep +
            "Что: " + what + "\n" + cmd_line +
            "Объект: " + (obj or "—") + "\n"
            "Число: " + (num or "—") + "\n"
            "Откат: " + back + "\n"
            "Проверь: " + check + " — жду твоё «да».")


def _probe_intercept(card, tid=""):
    """ПЕРЕХВАТ НА ГРАНИЦЕ: владельцу не ушло ничего, а исполнитель видит ДОСЛОВНО то, что
    собиралось уйти, и каким каналом. Без этого изоляция была бы неотличима от поломки: проба
    молча «ничего не делает», и автор пробы не знает, сработал ли гард вообще — а именно ради
    ответа на этот вопрос пробу и запускают. Текст идёт в решение хука (его читает исполнитель
    задачи), НЕ в канал владельца."""
    where = os.path.join(block_dir(), marker_name(tid)) if tid else "не пишется (CC_TASK_ID пуст)"
    return ("🧪 ПРОБА — ПЕРЕХВАЧЕНО НА ГРАНИЦЕ. Владельцу НЕ ушло ничего ни одним каналом.\n"
            "  канал 1 (прямой пуш в тему-инбокс / личку): подавлен;\n"
            "  канал 2 (маркер → демон → карточка с кнопками, плюс напоминание через 3 ч): "
            "маркер уведён в тест-канал → %s.\n"
            "Решение гарда НЕ ослаблено: без «да» команда не исполнится, жёсткий блок остаётся "
            "жёстким, секреты остаются секретами.\n"
            "─── ниже ДОСЛОВНО карточка, которая СОБИРАЛАСЬ уйти владельцу ───\n%s" % (where, card))


def _dedup_path(session):
    sid = re.sub(r"[^\w\-]", "_", str(session or "nosession"))[:64]
    return os.path.join(_DEDUP_DIR, sid + ".json")


def _dedup_bump(session, cmd):
    """Счётчик одинаковой ambiguous-команды в рамках сессии (= headless-задачи). → (count, mid|None):
    count — какой это раз (1 = первая карточка), mid — message_id уже висящей Telegram-карточки.
    FAIL-SAFE: любой сбой стора → (1, None) = прежнее поведение (новая карточка), не хуже."""
    try:
        os.makedirs(_DEDUP_DIR, exist_ok=True)
        path = _dedup_path(session)
        key = hashlib.sha1(cmd.encode("utf-8", "ignore")).hexdigest()[:16]
        with open(path + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
            ent = data.get(key) if isinstance(data, dict) else None
            now = time.time()
            if not isinstance(ent, dict) or now - float(ent.get("ts", 0)) > _DEDUP_TTL:
                ent = {"count": 0, "mid": None}
            ent["count"] = int(ent.get("count", 0)) + 1
            ent["ts"] = now
            data[key] = ent
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        return ent["count"], ent.get("mid")
    except Exception:
        return 1, None


def _dedup_save_mid(session, cmd, mid):
    """Запомнить (message_id, chat_id) первой карточки (под тем же lock; tuple → JSON-список) —
    повтор будет править ЕЁ в том же чате (инбокс/личка). Best-effort."""
    try:
        path = _dedup_path(session)
        key = hashlib.sha1(cmd.encode("utf-8", "ignore")).hexdigest()[:16]
        with open(path + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data.get(key), dict):
                data[key]["mid"] = mid
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                os.replace(tmp, path)
    except Exception:
        pass


def _push(card):
    """Отправить карточку. → (message_id, chat_id)|None (нужно дедупу: повтор правит ЭТУ карточку
    В ТОМ ЖЕ чате). Маршрут 13.07.2026 — внутри notify.send_card: тема-инбокс HQ 1160, личка-фолбэк."""
    if isolated():
        return None   # проба/тест-прогон: не спамить Telegram красными карточками (единый признак —
                      # прежде здесь стоял ТОЛЬКО PRETOOL_NOPUSH, и проба с иным флагом пушила в бой)
    try:
        sys.path.insert(0, PROJECT)
        from notify import send_card
        return send_card(card)
    except Exception:
        return None   # пуш — вторичный канал; не роняем решение из-за сети/ошибки


def _edit(mid, card):
    """Повтор той же команды → правка УЖЕ висящей карточки (счётчик ×N). mid из стора: [message_id,
    chat_id] (карточки 13.07+ несут чат: инбокс 1160 или личка-фолбэк) либо голый id (легаси-записи
    до маршрута инбокса → личка). Сбой → молча (спама нет)."""
    if isolated() or not mid:
        return
    chat = None
    if isinstance(mid, (list, tuple)):
        chat = mid[1] if len(mid) > 1 else None
        mid = mid[0] if mid else None
    if not mid:
        return
    try:
        sys.path.insert(0, PROJECT)
        from notify import edit_card
        edit_card(mid, card, chat_id=chat)
    except Exception:
        pass


def _is_python(cmd):
    return re.search(r"(^|\s|/)(python3?|venv/bin/python3?)(\s|$)", cmd) is not None


def _strip_git_msg(cmd):
    """Нюанс bd5d516 (фикс 12.07.2026): слово-интерпретатор ВНУТРИ текста git commit -m
    («фикс python скрипта») попадало в скан _is_python → git-команда шла в _analyze → ветка -m
    видела «не-зелёный модуль» → ложная ambiguous-карточка. Для СКАНА интерпретатора из git-команды
    вырезаются payload'ы -m/-am/--message (формы: -m <txt>, -am <txt>, --message <txt>,
    --message=<txt>, приклеенное -m<txt>); классификация самого git НЕ меняется — git без
    интерпретатора вне -m остаётся не-python → defer к штатным allow/ask rules, как и был.
    Не git (учитывая env-префикс) / сбой разбора → команда КАК ЕСТЬ (fail-safe: скан полный,
    интерпретатор в компаунде `git … && python3 evil.py` по-прежнему ловится)."""
    try:
        toks = shlex.split(cmd)
    except Exception:
        return cmd
    i0 = 0
    while i0 < len(toks) and _ENV_ASSIGN.match(toks[i0]):
        i0 += 1
    if i0 >= len(toks) or toks[i0] != "git":
        return cmd
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t in ("-m", "-am", "--message"):
            out.append(t)
            i += 2
            continue
        if t.startswith("--message="):
            out.append("--message")
            i += 1
            continue
        if re.match(r"^-a?m.", t):        # приклеенный payload: -mтекст / -amтекст
            out.append("-m")
            i += 1
            continue
        out.append(t)
        i += 1
    return " ".join(out)


# Сообщение коммита, поданное ЧЕРЕЗ STDIN закавыченным heredoc (`git commit -F - <<'MSG' … MSG`),
# — те же ДАННЫЕ, что payload -m (_strip_git_msg выше), только форма другая; текст сообщения НЕ
# исполняет ничего. Течь была ровно та же, что у -m до bd5d516, и стоила боевого коммита: 29.07.2026
# в 08:51:35 живая команда
#   git -C … commit -q -F /dev/stdin <<'MSG'   (тело описывало фикс и упоминало файл секретов)
# получила env_hard_block — deny на СЛОВА В СООБЩЕНИИ, задача переформулировала текст, чтобы
# закоммитить (реплей боевого лога: guard_replay.py --hours 48).
# СУДИМ ПО ДЕЙСТВИЮ, и сужено жёстко — иначе это дыра, а не фикс:
#   • разделитель ОБЯЗАН быть в кавычках (<<'MSG' / <<"MSG"): тогда шелл в теле не делает НИКАКИХ
#     подстановок и тело физически не может ничего сделать. Голый <<MSG шелл РАСКРЫВАЕТ ($(cat .env)
#     утёк бы в историю git) → такую форму НЕ трогаем вовсе, прежний полный скан;
#   • строка-открыватель обязана быть командой git с подкомандой commit, читающей сообщение ИЗ
#     STDIN (-F -, -F /dev/stdin, --file=…). Тело `bash <<'EOF'` под сканом остаётся — его читает
#     ИНТЕРПРЕТАТОР, а не git;
#   • нужен терминатор; сама строка-открыватель и всё ПОСЛЕ терминатора остаются ДОСЛОВНО
#     (`… MSG` + `&& pkill splinter` скану по-прежнему виден).
# Нет совпадения / сбой разбора → команда КАК ЕСТЬ (fail-safe: скан полный, краснит охотнее).
_HEREDOC_QUOTED_RE = re.compile(r"<<-?\s*(['\"])([A-Za-z_]\w{0,30})\1")
_GIT_MSG_STDIN = ("-", "/dev/stdin")


def _git_commit_reads_stdin(line):
    """Строка — это `git … commit …`, берущий СООБЩЕНИЕ из stdin? Разбор СТРУКТУРНЫЙ (слово-команда
    сегмента + флаг источника сообщения), а не по подстроке: `echo git commit -F -` сюда не попадёт."""
    toks = _tokens(line)
    i = 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    if i >= len(toks) or _base(toks[i]) != "git":
        return False
    rest = toks[i + 1:]
    if "commit" not in rest:
        return False
    for k, t in enumerate(rest):
        if t in ("-F", "--file") and k + 1 < len(rest) and rest[k + 1] in _GIT_MSG_STDIN:
            return True
        if t.startswith("--file=") and t.split("=", 1)[1] in _GIT_MSG_STDIN:
            return True
        if t.startswith("-F") and t != "-F" and t[2:] in _GIT_MSG_STDIN:
            return True
    return False


def _strip_git_msg_heredoc(cmd):
    """Тело закавыченного heredoc, которое `git commit` читает КАК СООБЩЕНИЕ, → вон из скана.
    Зовётся ДО сегментации (_units): переводы строк — шелл-разделители, поэтому тело сообщения
    иначе разъезжается по сегментам и никакой пер-сегментный вырез его уже не соберёт."""
    s = cmd or ""
    if "<<" not in s or "commit" not in s:
        return s
    try:
        lines = s.split("\n")
        out, i, changed = [], 0, False
        while i < len(lines):
            line = lines[i]
            out.append(line)
            m = _HEREDOC_QUOTED_RE.search(line)
            if m and _git_commit_reads_stdin(line):
                word = m.group(2)
                j = i + 1
                while j < len(lines) and lines[j].strip() != word:
                    j += 1
                if j < len(lines):          # терминатор есть → ТЕЛО (только оно) выбрасываем
                    out.append(lines[j])
                    i = j + 1
                    changed = True
                    continue
            i += 1
        return "\n".join(out) if changed else s
    except Exception:
        return s


def _strip_script_cli_args(cmd):
    """Аргументы ПОСЛЕ имени .py-скрипта — ДАННЫЕ скрипта, а не операция команды. Тот же класс,
    что текст git -m (_strip_git_msg): журнальные/логовые скрипты несут боевые слова В ТЕКСТЕ
    строки — `venv/bin/python3 cclog.py "DONE …: закрыл …"` краснел на шаге 1 _analyze по argv,
    хотя пишет он в журнал, а не в Лист1/CRM. Вырезается ТОЛЬКО из СКАН-представления; ТЕЛО .py
    по-прежнему читается и сканируется (_analyze шаг 2 токенизирует СЫРУЮ команду) — операция,
    которую скрипт РЕАЛЬНО делает, ловится там, как и раньше.
    Интерпретатор и его СОБСТВЕННЫЕ флаги (всё ДО имени скрипта: -u, -X, -m …) — ОСТАЮТСЯ.
    ОПЕРАНДЫ-УЛИКИ НЕ вырезаются (та же линия, что у _strip_search_pattern с файлами): токен с
    файлом секретов, с .db/SQL-write или с признаком исполнения ($(…)/`…`/system(…)) остаётся под
    сканом — иначе `python3 dump.py /root/app/.env` перестал бы жёстко блокироваться, а
    `python3 run.py "UPDATE x SET y" other.db` — краснеть.
    Нет .py-токена / сбой разбора → команда КАК ЕСТЬ (fail-safe: скан полный, краснит охотнее)."""
    try:
        toks = shlex.split(cmd)
    except Exception:
        return cmd
    for i, t in enumerate(toks):
        if not t.endswith(".py"):
            continue
        tail = toks[i + 1:]
        if not tail:
            return cmd                 # аргументов нет — не трогаем (лишняя переклейка кавычек)
        keep = [a for a in tail if _ENV_FILE.search(a) or ".db" in a
                or _SQLITE_WRITE.search(a) or _EXEC_IN_PATTERN.search(a)]
        return " ".join(toks[:i + 1] + keep)
    return cmd


def _args_after_interp(toks):
    """Аргументы ПОСЛЕ интерпретатора: срезает ведущие VAR=val (env-префикс) и сам python-токен.
    Фикс инцидента 163 (08.07.2026): `PRETOOL_NOPUSH=1 venv/bin/python3 --version` считал интерпретатор
    обычным аргументом → инфо-флаг не распознавался → ложный ambiguous → конверт-спам. Probe-паттерны
    без python (node --check / node tests/*harness* / cat / grep / diff) сюда НЕ доходят вовсе —
    main() дефёрит не-python до анализа (они «может писать» не считаются by construction)."""
    i = 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    if i < len(toks) and re.search(r"(^|/)python3?$", toks[i]):
        return toks[i + 1:]
    return toks[1:]   # интерпретатор не опознан токеном → прежнее поведение (fail-safe)


def _py_targets(cmd, cwd):
    """Все .py-цели команды → list существующих абсолютных путей (realpath). Непрочитавшиеся пути пропускаются."""
    try:
        toks = shlex.split(cmd)
    except Exception:
        return []
    out = []
    for t in toks:
        if not t.endswith(".py"):
            continue
        for cand in (t, os.path.join(cwd or PROJECT, t), os.path.join(PROJECT, t)):
            if os.path.isfile(cand):
                out.append(os.path.realpath(cand))
                break
    return out


def _is_trusted_test(cmd, cwd):
    """Ранний defer БЕЗ чтения содержимого (переклассификация 02.07): запуск тестов/гейта = зелёная рутина
    по определению (tests/* — моки, gate.py их прогоняет). True ТОЛЬКО если есть ≥1 .py-цель и ВСЕ цели
    лежат в PROJECT/tests/ или равны PROJECT/gate.py. Скрипт вне tests/ рядом в команде → НЕ доверяем."""
    targets = _py_targets(cmd, cwd)
    if not targets:
        return False
    tests_dir = os.path.join(PROJECT, "tests") + os.sep
    gate = os.path.join(PROJECT, "gate.py")
    return all(p.startswith(tests_dir) or p == gate for p in targets)


def _repo_tracked(path, cwd):
    """True if path is a file TRACKED by git in THIS repo (PROJECT). Trust-by-origin (24.07.2026):
    repo sources not body-scanned (own reviewed/tested code); _-prefixed drafts, scratchpad and
    out-of-repo files are body-scanned as before. Fail-safe: git missing / outside repo / _-prefixed
    -> False (body IS scanned, redder)."""
    try:
        if os.path.basename(path).startswith("_"):
            return False
        for cand in (path, os.path.join(cwd or PROJECT, path), os.path.join(PROJECT, path)):
            if os.path.isfile(cand):
                r = subprocess.run(["git", "-C", PROJECT, "ls-files", "--error-unmatch",
                                    os.path.realpath(cand)],
                                   capture_output=True, timeout=5)
                return r.returncode == 0
        return False
    except Exception:
        return False


def _read_file(path, cwd):
    for cand in (path, os.path.join(cwd or PROJECT, path), os.path.join(PROJECT, path)):
        try:
            if os.path.isfile(cand):
                with open(cand, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(400000)
        except Exception:
            continue
    return None


# ══ РАЗБОР ЦЕПОЧКИ: сегменты, слово-команда, поисковый шаблон = ДАННЫЕ ══════════════════════
def _base(t):
    """Имя команды без пути и кавычек, нижним регистром (/usr/bin/systemctl → systemctl)."""
    return os.path.basename((t or "").strip("'\"")).lower()


def _tokens(seg):
    try:
        return shlex.split(seg)
    except Exception:
        return seg.split()          # кривое квотирование → грубые токены (скан всё равно полный)


def _split_segments(cmd):
    """Цепочку → сегменты по шелл-разделителям (&&, ||, ;, |, &, перевод строки) ВНЕ КАВЫЧЕК.
    Кавычки уважаются намеренно: в `grep -n "a|b" f` труба — часть ШАБЛОНА, а не разделитель;
    зато `grep -e x&&pkill …` разъедется на два сегмента, и второй под сканом останется."""
    segs, buf, q, i, n = [], [], None, 0, len(cmd or "")
    while i < n:
        ch = cmd[i]
        if q:
            buf.append(ch)
            if ch == "\\" and q == '"' and i + 1 < n:
                buf.append(cmd[i + 1]); i += 2; continue
            if ch == q:
                q = None
            i += 1; continue
        if ch in "'\"":
            q = ch; buf.append(ch); i += 1; continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch); buf.append(cmd[i + 1]); i += 2; continue
        if cmd[i:i + 2] in ("&&", "||"):
            segs.append("".join(buf)); buf = []; i += 2; continue
        if ch in ";|&\n":
            segs.append("".join(buf)); buf = []; i += 1; continue
        buf.append(ch); i += 1
    segs.append("".join(buf))
    return [s for s in segs if s.strip()]


def _cmd_index(toks):
    """Индекс слова-КОМАНДЫ сегмента: пропускает env-префикс (VAR=val) и обёртки
    (sudo/env/nohup/timeout N/xargs/systemd-run…). None — команды в сегменте нет.
    Разбор СТРУКТУРНЫЙ, а не по подстроке: `cat splinter.log` командой-убийцей не станет."""
    i, hops = 0, 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    while i < len(toks) and hops < 4:
        name = _base(toks[i])
        if name not in _WRAPPERS:
            return i
        i += 1
        while i < len(toks) and toks[i].startswith("-"):
            i += 1
        if name in ("timeout", "nice", "ionice") and i < len(toks) and re.match(r"^[\d.]+[smhd]?$", toks[i]):
            i += 1
        while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
            i += 1
        hops += 1
    return i if i < len(toks) else None


def _strip_search_pattern(toks, idx):
    """→ (токены БЕЗ поискового шаблона, список вырезанных). Шаблон = аргумент -n/-e/-E либо
    ПЕРВЫЙ позиционный у grep/rg/sed/awk. Операнды-ФАЙЛЫ и прочие токены не трогаем — иначе
    `grep -n foo .env` перестал бы блокироваться. Токен с признаком исполнения не вырезается."""
    if idx is None or _base(toks[idx]) not in _SEARCH_CMDS:
        return toks, []
    drop, pat_seen, i = set(), False, idx + 1
    while i < len(toks):
        t = toks[i]
        if t in _PATTERN_FLAGS and i + 1 < len(toks):
            drop.add(i + 1); pat_seen = True; i += 2; continue
        if t.startswith("-") and t != "-":
            i += 1; continue
        if not pat_seen:
            drop.add(i); pat_seen = True
        i += 1
    keep, dropped = [], []
    for k, t in enumerate(toks):
        if k in drop and not _EXEC_IN_PATTERN.search(t):
            dropped.append(t)
        else:
            keep.append(t)
    return keep, dropped


def _mask(seg, dropped):
    """Убрать шаблоны из ТЕКСТА сегмента (в кавычках или без), сохранив всё прочее ДОСЛОВНО —
    red-скан не должен слабеть от переклейки токенов. Не нашли форму → текст как есть (краснее)."""
    out = seg
    for d in dropped:
        for form in ('"' + d + '"', "'" + d + "'", d):
            if d and form in out:
                out = out.replace(form, " ", 1)
                break
    return out


def _subst_inners(seg):
    """Тела подстановок $(…) / `…` / system("…") / popen("…") — это ИСПОЛНЯЕМОЕ, а не данные."""
    out = []
    for m in _SUBST.finditer(seg or ""):
        for g in m.groups():
            if g and g.strip():
                out.append(g)
    return out[:8]


def _units(cmd, depth=0):
    """Цепочка → список пар (токены сегмента, текст сегмента) с ВЫРЕЗАННЫМИ поисковыми шаблонами.
    Тела подстановок и `sh -c "…"` добавляются ОТДЕЛЬНЫМИ парами (иначе прятались бы от скана)."""
    out = []
    if depth > 2 or not (cmd or "").strip():
        return out
    cmd = _strip_git_msg_heredoc(cmd)    # текст своего коммита — данные; вырез ДО сегментации
    for seg in _split_segments(cmd):
        for inner in _subst_inners(seg):
            out.extend(_units(inner, depth + 1))
        clean = _strip_git_msg(seg)          # текст git -m — ДАННЫЕ (нюанс bd5d516)
        clean = _strip_script_cli_args(clean)   # argv .py-скрипта — ДАННЫЕ (тот же класс)
        toks = _tokens(clean)
        i = _cmd_index(toks)
        if i is not None and _base(toks[i]) in _SHELLS:
            for j in range(i + 1, len(toks) - 1):
                if toks[j] == "-c":
                    out.extend(_units(toks[j + 1], depth + 1))
                    break
        keep, dropped = _strip_search_pattern(toks, i)
        out.append((keep, _mask(clean, dropped)))
        if len(out) > 60:
            break
    return out


def _scan(cmd):
    """→ (units, скан-текст). Сбой разбора → СЫРАЯ команда (fail-safe: скан полнее, краснит охотнее)."""
    try:
        units = _units(cmd)
        text = " ".join(t for _, t in units)
        return units, (text if text.strip()
                       else _strip_script_cli_args(_strip_git_msg(_strip_git_msg_heredoc(cmd))))
    except Exception:
        return [(_tokens(cmd), cmd)], _strip_script_cli_args(_strip_git_msg(cmd))


# ══ (а) ЧЁРНЫЙ СПИСОК ПРОЦЕССОВ ════════════════════════════════════════════════════════════
def _norm(t):
    return re.sub(r"[^a-z0-9_]", "", (t or "").lower().replace("-", "_").replace(".", "_"))


def _protected_in(args):
    """Первый аргумент, называющий боевой процесс контура ('' — таких нет)."""
    for a in args:
        v = a
        if v.startswith("-"):
            if "=" not in v:              # --signal=SIGKILL: цель может прятаться в значении флага
                continue
            v = v.split("=", 1)[1]
        n = _norm(v)
        for p in _PROTECTED_PROCS:
            if p in n:
                return a
    return ""


def _pid1_in(args):
    """PID 1 (init/systemd) среди целей `kill`. Аргументы сигналов (-s TERM, -n 9) пропускаются."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-s", "--signal", "-n", "-q", "--queue"):
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        if a.strip() == "1":
            return True
        i += 1
    return False


def _systemctl_parts(args):
    """→ (глагол, [юниты]). Флаги и их аргументы (-H/-M) отбрасываются."""
    verb, names, i = "", [], 0
    while i < len(args):
        a = args[i]
        if a in ("-H", "--host", "-M", "--machine"):
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        if not verb:
            verb = a.lower()
        else:
            names.append(a)
        i += 1
    return verb, names


def _proc_class(units):
    """→ ('block', цель) | ('red', цель) | None. Блок ищем во ВСЕЙ цепи (красное первого сегмента
    не должно заслонять жёсткое во втором: `systemctl restart nginx && pkill -9 splinter`)."""
    red = None
    for toks, _text in units:
        i = _cmd_index(toks)
        if i is None:
            continue
        name, args = _base(toks[i]), toks[i + 1:]
        if name in _KILL_CMDS:
            tgt = _protected_in(args)
            if tgt:
                return "block", name + " " + tgt
            if name == "kill" and _pid1_in(args):
                return "block", "kill PID 1 (init/systemd)"
            red = red or ("red", " ".join([name] + args[:3]))
        elif name == "systemctl":
            verb, names = _systemctl_parts(args)
            tgt = _protected_in(names)
            if verb in _HARD_VERBS and tgt:
                return "block", "systemctl " + verb + " " + tgt
            # restart|start своих → ЗЕЛЁНОЕ (в2): штатный поток, гейт живёт выше (оркестратор+settings)
            if verb in _HARD_VERBS or (verb in _SVC_VERBS and tgt and verb not in _GREEN_VERBS):
                red = red or ("red", ("systemctl " + verb + " " + (tgt or " ".join(names[:2]))).strip())
    return red


def classify(cmd, cwd=None):
    """ЕДИНАЯ точка классификации (её зовут main() и тесты — исполнять ничего не требуется).
    → (kind, hit, blob): kind ∈ {'block','red','ambiguous','green'}; hit — ключ действия и,
    для жёстких блоков, имя события в журнале; blob — текст для _detail()/причины.
    Порядок: жёсткое (процессы → секреты) ПЕРЕД всем остальным — иначе `cat .env && python gate.py`
    ушёл бы в зелёное на раннем defer доверенных тестов/гейта."""
    cmd = cmd or ""
    units, scan = _scan(cmd)
    proc = _proc_class(units)
    if proc and proc[0] == "block":
        return "block", "proc_hard_block", cmd + "\nproc_target=" + proc[1]
    m = _ENV_FILE.search(scan)
    if m:
        return "block", "env_hard_block", cmd + "\nenv_target=" + m.group(0).strip()
    if proc:
        return "red", "proc_ctl", cmd + "\nproc_target=" + proc[1]
    if not _is_python(scan):
        return "green", "", cmd          # не-python и не процесс/секрет → штатные allow/ask rules
    return _analyze(cmd, cwd or PROJECT, scan)


def _block_reason(hit, blob=""):
    tgt = _find([r"proc_target=([^\n]{1,60})", r"env_target=([^\n]{1,60})"], blob)
    return _BLOCK_TEXT[hit] % ((" — " + tgt) if tgt else "")


def _analyze(cmd, cwd, scan=None):
    """→ (kind, hit, blob): kind ∈ {'red','ambiguous','green'}; hit — ключ действия; blob — текст для _detail()."""
    scan = cmd if scan is None else scan
    # 0) тесты/гейт → зелёное СРАЗУ, до сканирования содержимого (моки по определению; шум ask убран 02.07)
    if _is_trusted_test(cmd, cwd):
        return "green", "", cmd
    # 1) быстрый греп по САМОЙ команде (инлайн -c, env DOWRITE, argv) — по СКАН-представлению:
    #    красное слово в поисковом шаблоне это данные, а не операция (класс «данные ≠ команда»)
    #    ДЕНЬГИ ЗДЕСЬ ПРОПУСКАЮТСЯ (02.08.2026): их решает _money_is_action ПОСЛЕ разбора тел —
    #    инлайн `-c` попадает в parts и судится разобранным, а всё, что разбору не досталось
    #    (heredoc/stdin/нечитаемое), возвращается сюда же подстрокой через blind ниже.
    for tok in RED_TOKENS:
        if tok in scan and tok not in _MONEY_HITS:
            return "red", RED_TOKEN_HIT[tok], cmd
    # 1а) confirmed=ИСТИНА в САМОЙ команде — по разобранному присваиванию, а не по написанию
    #     (02.08.2026): список из пяти литералов не совпадал с `confirmed  =  True`, и боевая
    #     запись в Лист1 проходила молча. Обобщённый признак стоит ПОСЛЕ конкретных операций —
    #     порядок RED_TOKEN_HIT («конкретные первыми») этим сохранён.
    if _CONFIRMED_RE.search(scan):
        return "red", "confirmed", cmd
    # 1б) SQL-write в тексте команды (heredoc/stdin/инлайн) — в3: раньше такие формы прятались за
    #     ambiguous-ask, теперь ambiguous defer'ится → доктринальный sqlite проверяется ДО любого
    #     ambiguous-выхода. memory.db — своя БД (зелёная доктрина 02.07), скан-представление
    #     чтит «данные ≠ команда» (UPDATE в шаблоне grep не краснит). 02.08.2026: своя БД
    #     опознаётся по РАЗОБРАННОЙ ЦЕЛИ открытия, а не по слову в тексте (см. _sql_write_is_foreign).
    if _SQLITE_WRITE.search(scan) and _sql_write_is_foreign(scan):
        return "red", "sqlite", cmd
    # 2) разобрать команду на токены
    try:
        toks = shlex.split(cmd)
    except Exception:
        # Кривое квотирование → ambiguous (в3: defer). ДЕНЬГИ ЗДЕСЬ ДОБИРАЮТСЯ ПОДСТРОКОЙ: разбора
        # тел не будет вовсе, а пропуск денег на шаге 1 рассчитан именно на разбор — без этой
        # ветки команда с незакрытой кавычкой стала бы тише, чем была до правки 02.08.2026.
        for tok in _MONEY_HITS:
            if tok in scan:
                return "red", RED_TOKEN_HIT[tok], cmd
        return "ambiguous", "ambiguous", cmd
    content = ""
    parts = []          # те же тела ПООТДЕЛЬНОСТИ — для канонического разбора (_code_view_parts)
    i = 0
    saw_target = False
    amb = False        # в3: ambiguous КОПИТСЯ, а не выходит сразу — красное в ЧИТАЕМОЙ части команды
    while i < len(toks):                     # важнее (иначе `python3 red.py && python3 нет_такого.py`
        t = toks[i]                          # ушёл бы в defer, не отсканировав red.py)
        if t == "-c":                                  # инлайн-код в следующем токене
            inline = toks[i + 1] if i + 1 < len(toks) else ""
            content += inline
            parts.append(inline)
            saw_target = True
            i += 2; continue
        if t == "-":                                   # stdin: тело heredoc уже отсканировано по scan (шаг 1)
            amb = True
            i += 1; continue
        if t == "-m":                                  # модуль (py_compile/pytest/json.tool — ОБРАБАТЫВАЮТ файлы-
            mod = toks[i + 1] if i + 1 < len(toks) else ""   # аргументы, НЕ исполняют их write-логику → не читаем
            if mod in _GREEN_MODULES:                  # арг-файлы: иначе `-m py_compile splinter.py` ложно ловит
                return "green", "", cmd                # токены из ИСХОДНИКА splinter.py (он их определяет)
            amb = True
            i += 2; continue
        if t.endswith(".py"):
            if _repo_tracked(t, cwd):
                saw_target = True                      # trust-by-origin: git-tracked repo source not body-scanned
            else:
                body = _read_file(t, cwd)              # _-prefixed / out-of-repo / untracked -> body as before
                if body is None:
                    amb = True
                else:
                    content += body
                    parts.append(body)
                    saw_target = True
        i += 1
    blob = cmd + "\n" + content
    # 02.08.2026: тело судится по КАНОНИЧЕСКОМУ РАЗБОРУ, а не по подстроке — имя операции в
    # комментарии больше не рождает карточку чужого класса, а `confirmed` с любыми пробелами и
    # кавычками больше не проходит молча. Разбор не удался → _body_has возвращает прежнюю
    # подстроку, байт-в-байт. Взвод латча — ДО первого return: его читает _detail_parts.
    view = _code_view_parts(parts)
    set_code_view(view)
    for tok in RED_TOKENS:
        if tok in _MONEY_HITS:
            # Подстрока берётся по СКАН-представлению (argv скрипта и шаблон поиска — данные, класс
            # «данные ≠ команда» цел), а слепым считается не только несобранный разбор (amb), но и
            # имя, произнесённое ВНЕ разобранных тел: до имени скрипта, в `-m`-модуле, в heredoc.
            # Там разбирать нечего, и молчать нельзя — это и есть регресс `<OP> перед .py`.
            outside = tok in scan and tok not in content
            if _money_is_action(tok, scan + "\n" + content, view, blind=amb or outside):
                return "red", RED_TOKEN_HIT[tok], blob
            continue
        if _body_has(tok, content, view):
            return "red", RED_TOKEN_HIT[tok], blob
    # memory.db через python-код = 🟢 (своя БД бота, доктрина «своя таблица через код = зелёное»,
    # переклассификация 02.07; прямой sqlite3 CLI остаётся ask в settings). SQL-write в ИНУЮ БД → ask.
    # 02.08.2026: «своя» определяется целью открытия, а не упоминанием имени в комментарии/докстринге.
    if _SQLITE_WRITE.search(blob) and _sql_write_is_foreign(blob):
        return "red", "sqlite", blob
    if amb:
        return "ambiguous", "ambiguous", blob          # доктринального красного нет → в3: defer
    if not saw_target:
        # Инфо-флаги (--version/-V/--help) НИЧЕГО не исполняют → зелёное (сужение ambiguous 06.07):
        # все не-интерпретаторные, не-`VAR=val` токены ∈ _INFO_FLAGS и хотя бы один есть.
        # Интерпретатор ищется С УЧЁТОМ env-префикса (фикс 163, 08.07) — см. _args_after_interp.
        rest = [t for t in _args_after_interp(toks) if not _ENV_ASSIGN.match(t)]
        if rest and all(t in _INFO_FLAGS for t in rest):
            return "green", "", blob
        return "ambiguous", "ambiguous", blob          # python без внятной цели (REPL/heredoc) → в3: defer
    return "green", "", blob


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        _defer()                                       # не распарсили вход → отдать штатным rules
    if (data.get("tool_name") or "") != "Bash":
        _defer()
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    cwd = data.get("cwd") or PROJECT
    if not cmd:
        _defer()
    try:
        kind, hit, blob = classify(cmd, cwd)
    except Exception:
        kind, hit, blob = "ambiguous", "ambiguous", cmd  # сбой анализа → в3: defer (красное держат settings)
    if kind in ("green", "ambiguous"):
        _defer()                  # читающий python / не-python / ambiguous (в3) → штатные allow/ask/deny
    if not can_approve(kind, hit):
        why = _block_reason(hit, blob)                 # ЖЁСТКИЙ БЛОК: deny + журнал. Ниже по коду —
        _guard_log(hit, cmd, why)                      # карточка, пуш и маркер-конверт: сюда НЕ доходим,
        _emit(decision(kind, hit, why))                # т.е. approve по этой команде невозможен физически
    # ЕДИНЫЙ ПРИЗНАК ПРОБЫ — считается ОДИН раз и ДО первой записи маркера, латч взводится сразу:
    # ниже маркер пишется из ДВУХ веток, и обе обязаны быть изолированы, не сговариваясь.
    probe = is_probe(cmd)                              # дальше ТОЛЬКО red: конкретная операция
    set_probe(probe)
    card = _card(hit, blob, probe, cmd=cmd)
    tid = os.environ.get("CC_TASK_ID", "").strip()
    # ТЕСТ-СУЩНОСТИ: запись в живые таблицы по ЖИВОЙ сущности — approve недоступен физически
    # (deny хука + маркер blocktype=hard, по которому демон закрывает задачу failed без кнопки).
    # ТЕСТ-сущность и неизвлечённая сущность идут прежним мягким путём — карточка с «да».
    # Жёсткая ветка стоит ДО минимума карточки НАРОЧНО: hard-блок — ИСКЛЮЧЕНИЕ, он приходит всегда.
    blocktype = _entity_blocktype(hit, blob)
    if blocktype == "hard":
        _guard_write_marker(tid, hit, card, blocktype="hard")
        why = ("Сущность «%s» без пометки ТЕСТ: в живые таблицы не пишем ВОВСЕ — "
               "решение владельца вне агента" % (_extract_first_entity(hit, blob) or "не опознана"))
        _guard_log(hit, cmd, why)
        if probe:
            why += "\n" + _probe_intercept(card, tid)
        _emit(decision("block", hit, why))              # block → deny: кнопки «да» здесь нет
    # МИНИМУМ КАРТОЧКИ (29.07.2026, единое правило обеих полос — см. card_gate): нет ОБЪЕКТА —
    # показывать владельцу нечего. Вместо карточки — СТРОКА В ЖУРНАЛ (факт не теряется).
    # Гард при этом НЕ слабеет: решение остаётся ask, т.е. без «да» команда не исполнится; молчим
    # только в каналах владельца (Telegram-пуш и маркер-конверт демону). ЧИСЛО здесь не гейт:
    # операции без числа по природе (стоп сервиса, pkill по имени, SQL, отмена проводки) карточку
    # получают, и в поле «Число» у них честный прочерк.
    obj, num = card_min(hit, blob)
    if not card_gate(hit, obj, num):
        why = "объект=%s, число=%s" % (obj or "—", num or "—")
        _guard_log("card_skipped", cmd, hit + ": " + why)
        _ask("🔴 КРАСНОЕ (%s) — карточки нет: %s. Владельцу не отправлена, факт записан в журнал "
             "гарда; решай по самой команде." % (hit, why))
    _guard_write_marker(tid, hit, card, blocktype=blocktype)
    # Вызов _push остаётся БЕЗУСЛОВНЫМ, а глушение живёт ВНУТРИ него (там же, где мут PRETOOL_NOPUSH
    # и мок-счётчик notify). Так «гард решил отправить карточку» и «карточка ушла» остаются РАЗНЫМИ
    # событиями: первое видно тесту, второе физически не происходит. Прежняя развилка `if not test`
    # на месте вызова означала, что в тест-прогоне отправитель не звался вовсе — и любой регресс
    # «боевая операция карточку рождает» проверить было нечем: он одинаково молчал и когда всё
    # хорошо, и когда канал сломан.
    _push(card)
    _ask(_probe_intercept(card, tid) if probe else card)


if __name__ == "__main__":
    main()
