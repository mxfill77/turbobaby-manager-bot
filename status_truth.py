#!/usr/bin/env python3
"""ПРАВДА СТАТУСА — зеркало класса «статус врёт» на СЕРВЕРНОЙ полосе (30.07.2026).

Класс закрыт сначала на ПК (коммиты 5f2be1c, 1597cbe): за сутки дважды задача делала работу
(коммит + запись журнала), упиралась в таймаут и получала голое «провалена». По таким статусам
планируется следующий шаг — владелец и дирижёр дважды строили план на неверной строке.

Здесь ТА ЖЕ механика для VPS-полосы, БЕЗ своих выдумок:

1. КОД ПРИЧИНЫ. Пять кодов, дословно те же, что на ПК:
   approval_timeout · heartbeat_timeout · run_timeout · model_refusal · exec_error.
   Код едет в тексте итога тегом `[причина=<код> · <по-русски>]`, в лог демона — строкой
   `FAIL причина=<код>`, наружу грепается через FAIL_CODE_RE.

2. СЛЕДЫ РАБОТЫ В ОКНЕ. Коммиты (git log --reverse от начала окна) и УСПЕШНЫЕ записи журнала
   (реестр, см. §3) за время жизни задачи называются поимённо.
   ⚠️ ФОРМУЛИРОВКА — «В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА», а НЕ «работа выполнена». Живая проверка на ПК
   опровергла первую формулировку фактом: в окно задачи 61 попали 8 коммитов, её собственный —
   один, остальные от параллельных сессий. ОКНО — НЕ АВТОРСТВО, и текст обязан это сказать вслух.
   Поэтому же вывод — «сверь следы с заданием и закрой руками», а не «всё готово».

3. РЕЕСТР УСПЕШНЫХ ЗАПИСЕЙ ЖУРНАЛА. До этого следа «журнал записан» не существовало вовсе:
   cclog писал в мозг и молчал. Теперь каждая УДАЧНАЯ запись оставляет строку в
   `cc_log_ledger.jsonl` (рантайм-состояние, в git не хранится, ротируется).
   Пишется ТОЛЬКО после ok от моста — реестр обещаний, а не намерений.

ГРАНИЦЫ (сознательно):
- Первый символ текста провала НЕ меняется: ⏱/✋ остаются первыми — на них смотрят гейт
  самопочинки (`_maybe_selfheal`) и пропуск куратора (`_CURATOR_SKIP_MARKS`). Тег причины
  встаёт ПОСЛЕ маркера, новых маркеров модуль не добавляет.
- Служебных строк дирижёра в cc_log нет (демон пишет в свой лог и в очередь, не в журнал мозга),
  поэтому фильтр «исключить служебные NOTE», нужный на ПК, здесь не заводится: нечего исключать.
  Появятся — фильтровать тут, в `ledger_entries`.

Модуль ЧИСТО stdlib (импортируется и демоном, и cclog, и замером) и НИЧЕГО не мутирует, кроме
собственного файла-реестра.
"""
import datetime
import json
import os
import re
import subprocess

REPO = os.path.dirname(os.path.abspath(__file__))

# --- §1 коды причин -------------------------------------------------------------------------
# Порядок = порядок разбора «от частного к общему». Значения — человеческая расшифровка в теге.
FAIL_CODES = {
    "approval_timeout": "таймаут подтверждения",
    "heartbeat_timeout": "таймаут сердцебиения",
    "run_timeout": "таймаут исполнения",
    "model_refusal": "отказ модели",
    "exec_error": "ошибка выполнения",
}
UNKNOWN_CODE = "exec_error"          # неопознанное честно падает в самый общий код, не в тишину

FAIL_CODE_RE = re.compile(r"\[причина=([a-z_]+)\s*·\s*([^\]]*)\]")

# Маркеры, которые ОБЯЗАНЫ остаться первым символом (гейты самопочинки/куратора смотрят на них).
LEAD_MARKS = ("⏱", "✋", "⛔", "🛑", "🔁", "🔄", "⏭", "🩹")

# Признаки отказа со стороны модели/её API. Здесь подстрока — это НЕ догадка о намерении
# (класс 25.07 «судим по действию»), а ДОСЛОВНЫЙ текст ошибки самого CLI: другого источника
# правды о причине выхода у нас нет. Всё неопознанное остаётся exec_error, а не додумывается.
_MODEL_NEEDLES = (
    "api error", "overloaded", "oauth", "authenticate", "authentication",
    "rate limit", "usage limit", "credit balance", "server error",
    "model refused", "cannot assist", "не могу выполнить",
)


def code_label(code):
    """Человеческая расшифровка кода; неизвестный код отдаётся как есть (не глотаем)."""
    return FAIL_CODES.get(str(code or ""), str(code or ""))


def tag(code):
    """Тег причины для текста итога: `[причина=heartbeat_timeout · таймаут сердцебиения]`."""
    return "[причина=%s · %s]" % (code, code_label(code))


def code_of(text):
    """Код причины из готового текста итога (или None). Обратная операция к tag()."""
    m = FAIL_CODE_RE.search(str(text or ""))
    return m.group(1) if m else None


def classify_exec(out="", err="", rc=None):
    """Провал ИСПОЛНЕНИЯ (claude -p завершился с ненулевым кодом) → model_refusal | exec_error.

    Таймауты сюда НЕ попадают: у них свои коды и свои точки (run_timeout — убитый по лимиту
    подпроцесс, heartbeat_timeout — реапер сирот, approval_timeout — сгоревшее подтверждение).
    """
    blob = ((str(out or "") + "\n" + str(err or "")).lower())
    if any(n in blob for n in _MODEL_NEEDLES):
        return "model_refusal"
    return UNKNOWN_CODE


# --- время ----------------------------------------------------------------------------------
def parse_iso(value):
    """ISO-строка очереди/реестра → aware datetime UTC. Не разобралось → None (fail-safe:
    без окна модуль просто не назовёт следов, но НИКОГДА не соврёт о них)."""
    if isinstance(value, datetime.datetime):
        return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
    s = str(value or "").strip()
    if not s:
        return None
    try:
        t = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def fmt_window(start, end):
    """«30.07 12:41–14:23 UTC» — компактная подпись окна для карточки."""
    if start is None or end is None:
        return "окно не определено"
    return "%s %s–%s UTC" % (start.strftime("%d.%m"), start.strftime("%H:%M"), end.strftime("%H:%M"))


# --- §3 реестр успешных записей журнала -------------------------------------------------------
LEDGER_PATH = os.path.join(REPO, "cc_log_ledger.jsonl")
LEDGER_MAX_BYTES = 200_000        # ~1000 записей; сверх — оставляем хвост
LEDGER_KEEP_LINES = 300
LEDGER_HEAD_MAX = 200             # сколько символов записи храним для улики


def ledger_append(kind, entry, label="", path=None, now=None):
    """Отметить УСПЕШНУЮ запись в cc_log. Зовётся ТОЛЬКО после ok от моста.

    FAIL-SAFE ПОЛНЫЙ: любой сбой реестра проглатывается — запись в журнал мозга уже состоялась,
    и потеря следа не смеет её отменить или сломать вызывающего. Возврат True/False — для тестов.
    """
    path = path or LEDGER_PATH
    try:
        rec = {
            "ts": (now or _now()).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "kind": str(kind or ""),
            "label": str(label or ""),
            "head": str(entry or "")[:LEDGER_HEAD_MAX],
        }
        try:                                   # ротация: реестр не растёт бесконечно
            if os.path.getsize(path) > LEDGER_MAX_BYTES:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    tail = f.readlines()[-LEDGER_KEEP_LINES:]
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(tail)
        except OSError:
            pass                               # реестра ещё нет — просто дописываем
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def ledger_entries(start, end, path=None):
    """Успешные записи журнала в окне [start, end] → список строк-улик (порядок хронологический).
    Нет файла / битая строка / сбой чтения → пропускаем молча: отсутствие улики НЕ доказательство
    отсутствия работы, поэтому текст карточки говорит «следов не найдено», а не «работы не было»."""
    path = path or LEDGER_PATH
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        t = parse_iso(rec.get("ts"))
        if t is None:
            continue
        if start is not None and t < start:
            continue
        if end is not None and t > end:
            continue
        head = str(rec.get("head") or "").strip()
        if head:
            out.append(head)
    return out


# --- §2 коммиты в окне ------------------------------------------------------------------------
_GIT_SEP = "\x1f"


def commits_in_window(start, end, repo=None, runner=None):
    """Коммиты репозитория в окне → [(хеш, тема), …] С НАЧАЛА окна (--reverse).

    `--reverse` — не косметика: на ПК без него собственный коммит задачи выпадал из показанной
    пятёрки, потому что параллельные сессии добивали окно сверху.
    Git недоступен / не репозиторий / любой сбой → [] (улик нет — так и скажем)."""
    if start is None:
        return []
    repo = repo or REPO
    runner = runner or subprocess.run
    args = ["git", "log", "--reverse", "--no-merges",
            "--since=" + start.isoformat(),
            "--format=%h" + _GIT_SEP + "%s"]
    if end is not None:
        args.insert(4, "--until=" + end.isoformat())
    try:
        p = runner(args, cwd=repo, capture_output=True, text=True, timeout=20)
    except Exception:
        return []
    if getattr(p, "returncode", 1) != 0:
        return []
    res = []
    for ln in (getattr(p, "stdout", "") or "").splitlines():
        if _GIT_SEP not in ln:
            continue
        h, _, subj = ln.partition(_GIT_SEP)
        h = h.strip()
        if h:
            res.append((h, subj.strip()))
    return res


# --- окно задачи ------------------------------------------------------------------------------
CLAIM_LOG_PATH = os.path.join(REPO, "orchestrator_claims.jsonl")


def claim_started(task_id, path=None):
    """Момент взятия задачи в работу из журнала взятий демона (последняя запись по id) → datetime
    | None. Задачу часто закрывает УЖЕ ДРУГОЙ процесс демона (рестарт, реапер) — у него нет
    оперативной памяти о старте, и отметка на диске остаётся единственной опорой окна."""
    path = path or CLAIM_LOG_PATH
    tid = str(task_id)
    found = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if str(rec.get("id")) != tid:
            continue
        t = parse_iso(rec.get("updated"))
        if t is not None:
            found = t
    return found


def task_window(task, task_id=None, started=None, claim_path=None, now=None):
    """Окно задачи → (start, end). Приоритет начала: явный `started` (демон знает точный момент
    запуска claude) → отметка взятия на диске → поле created очереди. Конец — сейчас."""
    end = now or _now()
    if started is not None:
        st = parse_iso(started)
        if st is not None:
            return st, end
    tid = task_id if task_id is not None else (task or {}).get("id")
    if tid is not None:
        st = claim_started(tid, path=claim_path)
        if st is not None:
            return st, end
    st = parse_iso((task or {}).get("created"))
    return st, end


# --- §2 сборка текста итога -------------------------------------------------------------------
MAX_COMMITS_SHOWN = 5
MAX_WRITES_SHOWN = 3
SUBJ_MAX = 60
HEAD_MAX = 90

_HEADLINE = "НЕ ЗАКРЫТА, но В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА"
_CAVEAT = "(Окно, а не авторство: в него попадают и параллельные сессии.)"


def _split_lead(text):
    """Отделить ведущий маркер (⏱/✋/…) от тела — он обязан остаться ПЕРВЫМ символом итога."""
    s = str(text or "").lstrip()
    for m in LEAD_MARKS:
        if s.startswith(m):
            return m, s[len(m):].lstrip()
    return "", s


def _trim(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n] + " …обрезано"


def fail_result(base, code, start=None, end=None, commits=None, writes=None,
                max_len=4500, repo=None, ledger=None, runner=None, task=None,
                task_id=None, started=None, claim_path=None, now=None):
    """Текст провала, который НЕ врёт: маркер · тег причины · исходный диагноз · следы в окне.

    base    — прежний честный диагноз (его смысл не трогаем, только обрамляем);
    code    — один из FAIL_CODES;
    commits/writes — улики; None → соберём сами по окну (тесты передают явно).

    Первый символ и смысл base сохраняются байт-в-байт — гейты, которые на них смотрят,
    продолжают работать. Если улик нет — так и пишем, без намёка на выполненную работу.
    """
    if start is None and end is None:
        start, end = task_window(task, task_id=task_id, started=started,
                                 claim_path=claim_path, now=now)
    if end is None:
        end = now or _now()
    if commits is None:
        commits = commits_in_window(start, end, repo=repo, runner=runner)
    if writes is None:
        writes = ledger_entries(start, end, path=ledger)

    mark, body = _split_lead(base)
    lead = (mark + " ") if mark else ""
    window = fmt_window(start, end)
    n_c, n_w = len(commits), len(writes)

    if not n_c and not n_w:
        head = "%s%s: %s" % (lead, tag(code), body)
        tail = ("СЛЕДОВ РАБОТЫ в окне %s не найдено (коммитов 0, записей журнала 0) — "
                "судя по уликам, работа не начиналась либо оборвалась до первого следа." % window)
        return _cap(head + " " + tail, max_len)

    parts = []
    if n_c:
        shown = "; ".join("%s «%s»" % (h, _trim(s, SUBJ_MAX)) for h, s in commits[:MAX_COMMITS_SHOWN])
        parts.append("коммитов %d (%s)" % (n_c, shown))
    if n_w:
        shown = "; ".join("«%s»" % _trim(w, HEAD_MAX) for w in writes[:MAX_WRITES_SHOWN])
        parts.append("записей журнала %d (%s)" % (n_w, shown))

    head = "%s%s %s: %s" % (lead, _HEADLINE, tag(code), body)
    tail = ("СЛЕДЫ в окне %s: %s. Формальное закрытие не состоялось — НЕ переделывай вслепую: "
            "сверь эти следы с заданием и закрой руками. %s" % (window, ", ".join(parts), _CAVEAT))
    return _cap(head + " " + tail, max_len)


def _cap(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[:max(0, n - 12)] + " …обрезано"


def log_line(task_id, code, extra=""):
    """Строка для лога демона: `FAIL причина=<код> id=<id> …` — грепается наравне с тегом."""
    base = "FAIL причина=%s id=%s" % (code, task_id)
    return (base + " " + str(extra)).strip() if extra else base
