#!/usr/bin/env python3
"""ВЫНОС ЗНАЧЕНИЯ СЕКРЕТА НАРУЖУ — чистая функция «факты → вердикт». Импорт ровно один: `re`.

КЛАСС (11.08.2026). Гард охранял НАПИСАНИЕ ИМЕНИ ФАЙЛА секретов, а не ЗНАЧЕНИЕ. Место, где
решается класс операции по секретам, названо строкой кода: `pretool_guard.classify()` —
`m = _ENV_FILE.search(scan)` → `return "block", "env_hard_block", …`. Секреты при этом живут не
только в файле: демон делает `load_dotenv` и отдаёт задаче КОПИЮ своего окружения
(`orchestrator_daemon._run_task_impl`: `child_env = dict(os.environ)`), поэтому значение
достаётся ЗЕЛЁНОЙ командой — `printenv`, `env`, `os.environ` гардом не судятся вовсе.

ЧТО СУДИТСЯ. Опасно не ЧТЕНИЕ, а ВЫНОС. На чтении окружения работает всё, что ходит к мосту, и
запрет чтения остановил бы контур; поэтому чтение остаётся зелёным, а карточку рождает ПАРА
фактов: специфичное значение (или ИМЯ такой переменной) И КАНАЛ, которым его увидят — файл вне
временных каталогов, журнал, сообщение владельцу, сеть. Один факт без другого — зелёное.

СПЕЦИФИЧНОСТЬ — ЧИСЛОМ, А НЕ НА ГЛАЗ (замер 64 переменных ЖИВОГО окружения задачи, 11.08.2026).
Сравнивать всё подряд нельзя: значения `1`, `claude-opus-…`, `/root/turbobaby-manager-bot`
стоят в командах постоянно и рядом с любым каналом дали бы карточку на пустом месте. Признак —
ДЛИННЕЙШАЯ НЕПРЕРЫВНАЯ цепочка [A-Za-z0-9] в значении и число КЛАССОВ СИМВОЛОВ в ней: имя
модели, путь, локаль и chat-id собраны из СЛОВАРНЫХ кусков, разделённых `-` `/` `.` `_`, а токен —
длинная неразрывная цепочка со смешанным алфавитом. Замер (цепь ≥ R и классов в ней ≥ 2):

    R=10 → 10 · R=12 → 10 · R=14 → 9 · R=16 → 9 · R=18 → 7 · R=20 → 6

Между 12 и 16 промежуток ПУСТ, и обе его границы названы: 12 — `CLAUDE_CODE_SESSION_ID`, он же
ИМЯ ФАЙЛА транскрипта (проверено: файл с этим именем существует), то есть его значение стоит в
КАЖДОЙ команде, читающей свой транскрипт; 16 — `BOT_TOKEN` и `CC_GUARD_TOKEN`, самые короткие из
настоящих ключей. Порог взят В СЕРЕДИНЕ пустого промежутка — `RUN_MIN = 14`, устойчив к ±2.
Ниже него остаются имена моделей (цепь 6), PATH (5), PWD (9), chat-id (13, один класс);
выше 16 терялись бы настоящие ключи. Одноклассовая цепь (только буквы/только цифры) порогом НЕ
берётся ни при какой длине: на живом окружении таких ≥16 ровно НОЛЬ, то есть ветка купила бы
только риск.

НАПРАВЛЕНИЕ СОМНЕНИЯ — В ЗЕЛЁНОЕ, и это названо прямо. Карточка здесь не защищает от намеренного
противника (значение можно переписать по частям или закодировать — тот же честный предел, что у
маркера гарда), она закрывает ВИДИМЫЙ вынос: значение, доехавшее до файла, журнала, сообщения или
сети. Поэтому там, где канал не назван (цель редиректа — переменная, путь вычисляется), вердикта
нет: цена ложного красного в headless — убитая задача, а цена пропуска здесь — то же состояние,
что было до правки.

ЗНАЧЕНИЕ НЕ ВОЗВРАЩАЕТСЯ НИКОГДА: вердикт несёт ИМЯ переменной, вид улики и ярлык канала;
`mask()` отдаёт текст, из которого значения вычищены. Модулю нечем ни прочитать файл, ни
отправить, ни исполнить — импорт ровно один.
"""
import re

# ── ПОРОГ СПЕЦИФИЧНОСТИ ────────────────────────────────────────────────────────────────────────
RUN_MIN = 14          # длиннейшая непрерывная цепочка [A-Za-z0-9] в значении
CLASSES_MIN = 2       # классов символов (строчные · ПРОПИСНЫЕ · цифры) внутри этой цепочки
HIDDEN = "⟨значение скрыто⟩"

_RUN = re.compile(r"[A-Za-z0-9]+")
_ENV_ASSIGN = re.compile(r"^\w+=")
_NAME_OK = re.compile(r"^[A-Za-z_]\w*$")

# Каналы, у которых цель называть нечем — они САМИ и есть «наружу».
_NET = frozenset(("curl", "wget", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp",
                  "rsync", "ftp", "socat", "http", "https", "httpie", "xh"))
# Свои однокомандные каналы репозитория: журнал мозга и пуш владельцу.
_JOURNAL_SCRIPTS = ("cclog.py", "brain_sync.py")
_MSG_SCRIPTS = ("notify.py",)
_GIT_WRITE_SUB = frozenset(("commit", "tag", "notes"))
_SINK_NULL = frozenset(("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"))
_REDIR = re.compile(r"^\d*(?:&)?>{1,2}(.*)$")

# Каналы, видимые в ТЕЛЕ python-скрипта (разбор тела гардом уже сделан, сюда приходит текст).
_CODE_NET = re.compile(r"\brequests\s*\.\s*(?:post|get|put|patch|delete|request)\s*\(|\burlopen\s*\("
                       r"|\bhttp\.client\b|\bsocket\s*\.\s*socket\s*\(|\bsmtplib\b|\bhttpx\s*\.")
_CODE_MSG = re.compile(r"\bnotify\s*\(|\bsend_card\s*\(|\bsend_inbox\s*\(|\bsend_feed\s*\("
                       r"|\bsendMessage\b|\bsend_message\s*\(")
_CODE_JOURNAL = re.compile(r"\bwrite_doc\s*\(|\bwrite_cclog\s*\(|\bcclog\s*\(|\bguard_log\s*\("
                           r"|\blog\s*\.\s*(?:info|warning|error|exception|debug)\s*\(")
_CODE_WRITE = re.compile(r"""\bopen\s*\(\s*['"]([^'"]{1,300})['"]\s*,\s*['"][wax]"""
                         r"""|\bwrite_text\s*\(""")

_TMP_ROOTS = ("/tmp/", "/var/tmp/", "/dev/shm/")


def _is_tmp_default(p):
    """Зеркало `pretool_guard._is_tmp_target` для прогонов вне гарда. В бою гард передаёт СВОЙ
    предикат (`is_tmp=`), чтобы правило временного каталога жило в одном месте."""
    p = (p or "").strip().strip("'\"").strip()
    if not p or "*" in p or "?" in p:
        return False
    for root in _TMP_ROOTS:
        if p.startswith(root):
            tail = p[len(root):].strip("/")
            return bool(tail) and ".." not in tail.split("/")
    return False


def _base(t):
    t = (t or "").strip().strip("'\"")
    return t.rsplit("/", 1)[-1]


# ── (1) СПЕЦИФИЧНОСТЬ ЗНАЧЕНИЯ ─────────────────────────────────────────────────────────────────
def run_facts(value):
    """→ (длина длиннейшей цепочки [A-Za-z0-9], сколько классов символов в ней)."""
    best, best_cls = 0, 0
    for m in _RUN.finditer(value or ""):
        s = m.group(0)
        cls = ((1 if any("a" <= c <= "z" for c in s) else 0)
               + (1 if any("A" <= c <= "Z" for c in s) else 0)
               + (1 if any("0" <= c <= "9" for c in s) else 0))
        if len(s) > best:
            best, best_cls = len(s), cls
    return best, best_cls


def specific(value):
    """Значение достаточно специфично, чтобы его совпадение что-то значило? (см. замер в шапке)"""
    run, cls = run_facts(value or "")
    return run >= RUN_MIN and cls >= CLASSES_MIN


def passing(env):
    """Имена переменных со СПЕЦИФИЧНЫМ значением (порядок стабилен — по имени)."""
    out = []
    for name in sorted(env or ()):
        if not _NAME_OK.match(name or ""):
            continue
        if specific((env or {}).get(name) or ""):
            out.append(name)
    return out


def mask(text, env):
    """Текст, из которого вычищены ЗНАЧЕНИЯ специфичных переменных. Ничего больше не трогает."""
    out = text or ""
    if not out:
        return out
    for name in passing(env):
        v = (env or {}).get(name) or ""
        if v and v in out:
            out = out.replace(v, HIDDEN)
    return out


# ── (2) КАНАЛ НАРУЖУ ───────────────────────────────────────────────────────────────────────────
def _redirect_targets(toks):
    """Цели редиректа сегмента: формы `> f`, `>>f`, `2> f`, `&> f`. Пусто — редиректа нет."""
    out, i = [], 0
    while i < len(toks):
        m = _REDIR.match(toks[i] or "")
        if m:
            tail = (m.group(1) or "").strip().strip("'\"")
            if tail:
                out.append(tail)
            elif i + 1 < len(toks):
                out.append((toks[i + 1] or "").strip().strip("'\""))
        i += 1
    return out


def _file_channel(paths, is_tmp):
    """Названный путь ВНЕ временных каталогов → канал «файл». Цель не названа (переменная,
    подстановка, пусто) → канала НЕТ: см. «направление сомнения» в шапке."""
    for p in paths:
        p = (p or "").strip().strip("'\"")
        if not p or p in _SINK_NULL:
            continue
        if "$" in p or "`" in p:
            continue
        if not is_tmp(p):
            return True
    return False


def channel(segments, code="", is_tmp=None):
    """→ ярлык канала наружу ('' — канала нет).

    segments: [{'name': голова сегмента (гард уже снял обёртки), 'toks': сырые токены}].
    code:     текст тел python-скриптов/инлайн-кода, разобранных гардом.
    is_tmp:   предикат «путь во временном каталоге» — в бою СВОЙ у гарда, здесь только фолбэк."""
    tmp = is_tmp or _is_tmp_default
    for seg in segments or ():
        toks = list(seg.get("toks") or ())
        name = _base(seg.get("name") or "")
        args = [t for t in toks if t and not _ENV_ASSIGN.match(t)]
        if name in _NET or (args and _base(args[0]) in _NET):
            return "сеть"
        for t in toks:
            b = _base(t)
            if b in _MSG_SCRIPTS:
                return "сообщение владельцу"
            if b in _JOURNAL_SCRIPTS:
                return "журнал"
        if name == "logger":
            return "журнал"
        if name == "git":
            pos = [t for t in toks[1:] if t and not t.startswith("-")]
            if pos[:1] and pos[0] in _GIT_WRITE_SUB:
                return "файл репозитория"
        if name == "tee":
            if _file_channel([t for t in toks[1:] if t and not t.startswith("-")], tmp):
                return "файл"
        if _file_channel(_redirect_targets(toks), tmp):
            return "файл"
    src = code or ""
    if src:
        if _CODE_NET.search(src):
            return "сеть"
        if _CODE_MSG.search(src):
            return "сообщение владельцу"
        if _CODE_JOURNAL.search(src):
            return "журнал"
        paths = [m.group(1) for m in _CODE_WRITE.finditer(src) if m.group(1)]
        if _file_channel(paths, tmp):
            return "файл"
    return ""


# ── (3) УЛИКА: ЧТО ИМЕННО НЕСЁТ КОМАНДА ────────────────────────────────────────────────────────
def _name_re(name):
    return re.compile(r"\$\{?%s\b"
                      r"|environ(?:\.get)?\s*[\[(]\s*['\"]%s['\"]"
                      r"|getenv\s*\(\s*['\"]%s['\"]"
                      r"|printenv\s+%s\b" % (name, name, name, name))


def _dump_form(segments):
    """`printenv` / `env` БЕЗ аргументов — снимок ВСЕГО окружения: несёт каждое значение сразу."""
    for seg in segments or ():
        toks = [t for t in (seg.get("toks") or ()) if t and not _ENV_ASSIGN.match(t)]
        if not toks:
            continue
        if _base(toks[0]) in ("printenv", "env"):
            rest = [t for t in toks[1:] if not t.startswith("-") and not _REDIR.match(t)]
            rest = [t for t in rest if t not in _redirect_targets(toks)]
            if not rest:
                return True
    return False


def _supplied(segments):
    """Значения в позиции ПОДАЧИ — `NAME=значение` ПЕРЕД словом-командой сегмента.

    Шелл такой формой ЗАДАЁТ переменную дочернего процесса, а не отправляет её содержимое: это
    ровно то же правило позиции, которым закрыты классы литерала и заявления. ЗАМЕР это и поймал —
    из 12 команд корпуса, попавших под правило, ДВЕ были `BRIDGE_URL=<значение> … cclog.py …`,
    где в журнал уезжает текст записи, а значение достаётся процессу и наружу не идёт."""
    out = []
    for seg in segments or ():
        for t in (seg.get("toks") or ()):
            if _ENV_ASSIGN.match(t or ""):
                out.append((t or "").split("=", 1)[1].strip().strip("'\""))
                continue
            if _base(t) in ("env", "sudo", "nohup", "nice", "ionice", "stdbuf"):
                continue
            break
    return out


def carried(text, env, segments=None):
    """→ (имя переменной, вид улики) | None. Виды: 'значение' · 'имя' · 'снимок окружения'.
    ЗНАЧЕНИЕ не возвращается ни в каком виде."""
    names = passing(env)
    src = text or ""
    supply = _supplied(segments)
    for name in names:
        v = (env or {}).get(name) or ""
        if v and src.count(v) > supply.count(v):
            return name, "значение"
    for name in names:
        if _name_re(name).search(src):
            return name, "имя"
    if names and _dump_form(segments):
        return "*", "снимок окружения"
    return None


def verdict(text, env, segments=None, code="", is_tmp=None):
    """ЕДИНЫЙ ВХОД → {'var','how','channel'} | None. Обе половины обязательны: без канала —
    чтение (зелёное), без улики — обычная команда."""
    try:
        segs = list(segments or ())
        # `text` — ЕДИНСТВЕННЫЙ источник улики (гард кладёт туда и команду, и прочитанные тела);
        # `code` идёт только в судейство канала. Складывать их нельзя: удвоенный текст удваивает
        # и счёт вхождений, а на нём стоит снятие ПОДАЧИ (`VAR=значение команда`).
        found = carried(text, env, segs)
        if not found:
            return None
        ch = channel(segs, code, is_tmp)
        if not ch:
            return None
        return {"var": found[0], "how": found[1], "channel": ch}
    except Exception:
        return None
