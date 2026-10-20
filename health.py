#!/usr/bin/env python3
"""ЗДОРОВЬЕ СИСТЕМЫ TurboBaby — одна read-only проверка: всё живо или где проблема.

Пункт 2 «лестницы фундамента» (docs/project_state.md → «ФУНДАМЕНТ ПЕРЕД АВТОНОМИЕЙ»).
Ничего НЕ пишет, НЕ рестартит, НЕ деплоит. Запуск одной командой:
    venv/bin/python3 health.py                 # печать сводки в терминал
    venv/bin/python3 health.py --push          # + пуш Филиппу, ТОЛЬКО если проблема (❌)
    venv/bin/python3 health.py --push-always   # + пуш всегда (даже «всё ок») — для теста/расписания

Проверяет:
  • Splinter   — systemctl active/running + uptime + счётчик рестартов;
  • Bridge     — ping-экшен (alive + версия), живой запрос;
  • Аудитор    — маркеры старт-лога (Auditor ✅ + Auditor LLM ✅);
  • Polling    — ТЕКУЩИЙ запуск юнита (MainPID + ExecMainStartTimestamp, два чтения вокруг чтения
                 журнала): его строка «🚦 вход выпуска» (OK release|truth_off) и РОВНО ОДНА его строка
                 «Bot polling started». Строка прошлого запуска не доказательство; простой (вход
                 MISMATCH/UNKNOWN), нет polling текущего запуска, граница не прочитана / сменилась —
                 ❌ (RCFIX2010 C, Codex TB-QA-2110-0006-PARKSEEN, вариант B). Запуск моложе 300 с — ❌
                 НЕИЗВЕСТНО и со строкой polling: bot.py печатает её ДО app.run_polling (:1778–1779),
                 и цикл падений после неё (NRestarts растёт) иначе давал «✅ ВСЁ ОК». Цена: прогон в
                 первые 300 с после любого рестарта — ❌ с пушем (таймер после загрузки — OnBootSec=10min);
  • Лог        — свежесть последней строки (инфо: бот event-driven, тишина ≠ смерть)
                 + ошибки/Traceback ПОСЛЕ старта сервиса;
  • Прод       — последний коммит (что сейчас в проде).

Exit 0 = ок/предупреждение, 1 = есть проблема (лежит компонент, простой Splinter или запуск не
доказан — НЕИЗВЕСТНО). Пуш идёт через notify.py (личка Филиппа), ОДИН вызов за прогон, без повтора:
«отправлен» печатается только при ответе Telegram ok, иначе — «доставка не подтверждена». Предупреждение
(⚠️ ошибки в логе) пушем НЕ дёргает — только реальный ❌. Авто-проверка по расписанию (systemd timer,
такт 4 ч) зовёт `health.py --push`.
"""
import os
import re
import subprocess
import datetime
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "splinter.log")
OK, BAD, INFO, WARN = "✅", "❌", "ℹ️ ", "⚠️ "

# === RCFIX2010 C · PARKSEEN (Codex TB-QA-2110-0006-PARKSEEN, вариант B): polling ТЕКУЩЕГО запуска ==============
# Прежде «Bot polling started» искался последним совпадением по ВСЕМУ неротированному splinter.log: строка прошлого
# запуска проходила, а простой текущего (bot.main: вход выпуска MISMATCH/UNKNOWN → одна строка [ERROR] и
# _park_until_stop) давал «⚠️ РАБОТАЕТ, но 1 ошибок», code 0 и ни одного пуша. Теперь polling судится в границе
# запуска: MainPID + ExecMainStartTimestamp юнита (два чтения вокруг чтения журнала), строка входа выпуска ЭТОГО запуска
# и его polling. health splinter НЕ импортирует: копии ниже сверяет с splinter тест (tests/test_rcfix2010_health.py).
_UNIT = "splinter"
_ENTRY_HEAD = "🚦 вход выпуска: "                       # = splinter._ENTRY_HEAD (splinter.py:287)
_ENTRY_STATES = ("release", "truth_off")                # = имена splinter.RELEASE_ENTRY_STATES (splinter.py:283–286)
_ENTRY_KEYS = ("INTAKE_CONFIRM_STRICT", "CONTRACT_REF_GEN", "CLOSE_TRUTH", "CLOSE_ACCRUAL", "HANDOVER_FACTS")
#                                                       # = splinter.RELEASE_FLAG_KEYS (splinter.py:279)
_ENTRY_PARK_TAIL = "обработчики не зарегистрированы, опрос не начат — процесс ждёт остановки"
_START_SKEW_S = 300     # вход и polling — не позже старта + 300 с (= SC_START_SKEW библиотеки рестарта RC2010)
_FUTURE_SKEW_S = 120    # метка журнала впереди часов больше чем на 120 с → пояс журнала не UTC, НЕИЗВЕСТНО
_RUN_PROPS = ("MainPID", "ExecMainStartTimestamp", "NRestarts", "ActiveState", "SubState")
# Строгие шаблоны на ВСЮ строку журнала (формат bot.py:71–74 «%(asctime)s [%(levelname)s] %(name)s: %(message)s»,
# логгер «turbobaby» bot.py:79): якорь на префикс логгера отсекает цитаты внутри чужих сообщений и продолжения
# без метки.
_LOG_TS = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}"
_POLL_RE = re.compile(r"^" + _LOG_TS + r" \[INFO\] turbobaby: Bot polling started\. Press Ctrl\+C to stop\.$")
_ENTRY_RE = re.compile(r"^" + _LOG_TS + r" \[([A-Z]+)\] turbobaby:   " + re.escape(_ENTRY_HEAD) + r"(.*)$")
_ENTRY_OK_RE = re.compile(r"^OK — состояние (" + "|".join(_ENTRY_STATES) + r") · "
                          + " · ".join(re.escape(k) + " OK" for k in _ENTRY_KEYS) + r"$")
_ENTRY_PARK_RE = re.compile(r"^(MISMATCH|UNKNOWN) — .*; " + re.escape(_ENTRY_PARK_TAIL) + r"$")
_ENTRY_BAD_KEY_RE = re.compile(r"(" + "|".join(re.escape(k) for k in _ENTRY_KEYS) + r") (MISMATCH|UNKNOWN)")

# Ранний детектор деградации Brain-доков (износ Google-Doc → рост latency чтения).
# ПЕР-ДОКОВЫЙ порог: журналы (cc_log/review) должны читаться ~1с → порог 10с ловит ранний износ;
# base-доки (project_state/knowledge_base) законно большие (норм. 17-35с, синк из git, не изнашиваются)
# → порог высокий, тревога только при реальном выходе за норму (иначе ложный ⚠️ каждые 4ч).
# Формат: (label, read_doc-kwargs, порог_сек). Зонд читает с таймаутом порог+margin.
# Резолв по name= через манифест (НЕ хардкод id) — переживает миграции (cc_log/review на plain-text).
_BRAIN_DOCS = [
    ("cc_log",         {"name": "cc_log"}, 10),
    ("review",         {"name": "review"}, 10),
    ("project_state",  {"name": "project_state"}, 45),
    ("knowledge_base", {"name": "knowledge_base"}, 40),
]
_BRAIN_PROBE_MARGIN = 4   # сек сверх порога: «дочитал, но медленно» vs «не дочитал (timeout)»


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _run(cmd):
    """Запуск read-only команды, вернуть stdout (или '' при ошибке)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def _fmt_age(delta):
    s = int(delta.total_seconds())
    if s < 0:
        s = 0
    h, m = s // 3600, (s % 3600) // 60
    if h:
        return str(h) + "ч" + str(m) + "м"
    if m:
        return str(m) + "м"
    return str(s) + "с"


def check_service():
    state = _run(["systemctl", "is-active", "splinter"])
    props = {}
    raw = _run(["systemctl", "show", "splinter",
                "--property=SubState,NRestarts,ExecMainStartTimestamp"])
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    start_dt = None
    ts = props.get("ExecMainStartTimestamp", "")
    parts = ts.split()
    if len(parts) >= 3:
        try:
            start_dt = datetime.datetime.strptime(parts[1] + " " + parts[2],
                                                  "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except Exception:
            start_dt = None
    nrestarts = props.get("NRestarts", "?")
    up = _fmt_age(_utcnow() - start_dt) if start_dt else "?"
    ok = (state == "active")
    detail = state + "/" + props.get("SubState", "?") + ", uptime " + up + ", рестартов " + nrestarts
    return ok, detail, start_dt, nrestarts


def _read_run():
    """RCFIX2010 C: граница ТЕКУЩЕГО запуска юнита одним `systemctl show` → {pid, start, start_raw, nrestarts, active,
    sub} или None, когда её нельзя доказать: systemctl не запустился / код ≠ 0 / нет любого из ключей / MainPID не
    число > 0 / метка не вида «Ddd YYYY-MM-DD HH:MM:SS UTC» (пояс ≠ UTC прежде молча считался UTC) / NRestarts не
    число. Ключи разбираются по имени, а не по порядку строк: systemd печатает их в своём порядке. Промах — только
    None, а не пустое: «границы нет» не должно читаться как «граница пустая»."""
    try:
        r = subprocess.run(["systemctl", "show", _UNIT, "--property=" + ",".join(_RUN_PROPS)],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    props = {}
    for line in (r.stdout or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    if any(k not in props for k in _RUN_PROPS):
        return None
    pid, raw, nr = props["MainPID"], props["ExecMainStartTimestamp"], props["NRestarts"]
    parts = raw.split()
    if not (pid.isdigit() and int(pid) > 0 and nr.isdigit() and len(parts) == 4 and parts[3] == "UTC"):
        return None
    try:
        start = datetime.datetime.strptime(parts[1] + " " + parts[2], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    return {"pid": int(pid), "start": start, "start_raw": raw, "nrestarts": int(nr),
            "active": props["ActiveState"], "sub": props["SubState"]}


def _run_key(run):
    return (run["pid"], run["start_raw"], run["nrestarts"], run["active"], run["sub"])


def _run_word(run):
    return ("PID " + str(run["pid"]) + ", старт " + run["start"].strftime("%Y-%m-%d %H:%M:%S") + " UTC, рестартов "
            + str(run["nrestarts"]))


def check_bridge(attempts=3):
    """Ping Bridge. Bridge временами флапает (таймауты) — ретраим до `attempts` раз,
    чтобы авто-проверка по расписанию НЕ будила Филиппа ложным «Bridge не отвечает»."""
    last = "?"
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        from bridge_client import BridgeClient
        bc = BridgeClient()
        for i in range(attempts):
            try:
                r = bc.ping()
                if r.get("ok"):
                    suffix = "" if i == 0 else " (со " + str(i + 1) + "-й попытки)"
                    return True, "alive v" + str(r.get("version", "?")) + suffix
                last = "ответ без ok: " + str(r.get("error", r))
            except Exception as e:
                last = type(e).__name__ + " " + str(e)
        return False, last + " (после " + str(attempts) + " попыток)"
    except Exception as e:
        return False, type(e).__name__ + " " + str(e)


def _read_log_lines():
    try:
        with open(LOG, encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except Exception:
        return []


def _last_match(lines, needle):
    for ln in reversed(lines):
        if needle in ln:
            return ln.rstrip()
    return None


def _parse_log_ts(line):
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})", line)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None


def check_auditor(lines):
    a = _last_match(lines, "Auditor: ")
    a_llm = _last_match(lines, "Auditor LLM: ")
    ok = bool(a and "✅" in a) and bool(a_llm and "✅" in a_llm)
    if ok:
        return True, "подключён + LLM-надзор (старт-лог)"
    miss = []
    if not (a and "✅" in a):
        miss.append("Auditor")
    if not (a_llm and "✅" in a_llm):
        miss.append("Auditor LLM")
    return False, "нет ✅ в старт-логе: " + ", ".join(miss)


def _run_verdict(lines, run0, run1, now):
    """RCFIX2010 C: вердикт ТЕКУЩЕГО запуска → (OK | PARKED | NO_POLL | UNKNOWN, слова). Чистая: только строки журнала,
    два чтения границы (до и после чтения журнала) и «сейчас».
    Сегмент запуска — строки, чья действующая метка ≥ старта юнита (продолжения без своей метки наследуют метку
    родителя, как в check_log_health). В нём ровно одна строка «🚦 вход выпуска» не позже старт + 300 с:
      · [INFO] «OK — состояние release|truth_off · <пять ручек OK>» и после неё РОВНО ОДНА строка polling не позже
        старт + 300 с, и запуску не меньше 300 с → OK (строка polling печатается ДО app.run_polling, bot.py:1778–1779:
        падение initialize/get_me/post_init приходит после неё, поэтому молодой запуск с polling — не доказательство);
      · [ERROR] «MISMATCH|UNKNOWN — …; <хвост простоя>» и polling в запуске нет → PARKED (простой);
      · нет строки входа (и polling) при запуске старше 300 с, либо вход OK без polling → NO_POLL.
    Всё прочее — UNKNOWN: граница не прочитана или сменилась, запуск моложе 300 с, метки впереди часов или за окном
    (пояс журнала не UTC?), два входа / два polling, polling раньше входа или при простое, polling без строки входа,
    строка входа не по грамматике или уровень не сходится с вердиктом. Старый журнал UNKNOWN не спасает никогда."""
    if run0 is None or run1 is None:
        return "UNKNOWN", "граница запуска не прочитана (systemctl show: нет MainPID / старта в UTC)"
    if _run_key(run0) != _run_key(run1):
        return "UNKNOWN", ("граница запуска сменилась во время чтения журнала (" + _run_word(run0) + " → "
                           + _run_word(run1) + ")")
    who = _run_word(run1)
    if run1["active"] != "active":
        return "UNKNOWN", "юнит " + run1["active"] + "/" + run1["sub"] + " — текущий запуск не доказан (" + who + ")"
    start = run1["start"]
    skew = datetime.timedelta(seconds=_START_SKEW_S)
    ahead = now + datetime.timedelta(seconds=_FUTURE_SKEW_S)
    if start > ahead:
        return "UNKNOWN", "старт юнита впереди часов (" + who + ")"
    young = (now - start) < skew
    entries, polls = [], []
    cur = None
    for raw in lines:
        ln = raw.rstrip("\r\n")
        ts = _parse_log_ts(ln)
        if ts is not None:
            cur = ts
        if cur is None or cur < start:
            continue
        if cur > ahead:
            return "UNKNOWN", ("метка журнала " + cur.strftime("%Y-%m-%d %H:%M:%S") + " впереди часов — пояс журнала "
                               "не UTC? (" + who + ")")
        if ts is None:
            continue                       # продолжение без своей метки: ни входом, ни polling оно не бывает
        m = _ENTRY_RE.match(ln)
        if m:
            entries.append((ts, m.group(1), m.group(2)))
        elif _POLL_RE.match(ln):
            polls.append((ts, len(entries)))
    if len(entries) > 1:
        return "UNKNOWN", ("граница неоднозначна: строк «вход выпуска» в текущем запуске " + str(len(entries))
                           + " (" + who + ")")
    if not entries:
        if polls:
            return "UNKNOWN", ("polling текущего запуска без строки «вход выпуска» — кортеж выпуска не доказан (код "
                               "процесса старше выпуска?) (" + who + ")")
        if young:
            return "UNKNOWN", "запуск моложе 300 с — строки «вход выпуска» ещё нет (" + who + ")"
        return "NO_POLL", "нет строки «вход выпуска» и polling текущего запуска (" + who + ")"
    ets, lvl, rest = entries[0]
    if ets > start + skew:
        return "UNKNOWN", ("строка «вход выпуска» позже старта больше чем на 300 с — пояс журнала не UTC или долгий "
                           "импорт (" + who + ")")
    mo = _ENTRY_OK_RE.match(rest)
    mp = _ENTRY_PARK_RE.match(rest)
    if mp and lvl == "ERROR":
        if polls:
            return "UNKNOWN", ("противоречие: вход выпуска " + mp.group(1) + ", а polling в том же запуске есть ("
                               + who + ")")
        bad = ["%s %s" % kv for kv in _ENTRY_BAD_KEY_RE.findall(rest)]
        return "PARKED", ("ПРОСТОЙ Splinter: вход выпуска " + mp.group(1) + " текущего запуска (" + who + ")"
                          + ((": " + ", ".join(bad)) if bad else "") + " — обработчиков и опроса нет, бот молчит")
    if not (mo and lvl == "INFO"):
        return "UNKNOWN", ("строка «вход выпуска» не по грамматике или уровень " + lvl + " не сходится с вердиктом ("
                           + who + ")")
    if any(n_before == 0 for _t, n_before in polls):
        return "UNKNOWN", "противоречие: polling раньше строки «вход выпуска» того же запуска (" + who + ")"
    if len(polls) > 1:
        return "UNKNOWN", "граница неоднозначна: polling в текущем запуске " + str(len(polls)) + " (" + who + ")"
    if not polls:
        if young:
            return "UNKNOWN", "запуск моложе 300 с — polling ещё нет (" + who + ")"
        return "NO_POLL", "вход выпуска OK (" + mo.group(1) + "), но нет polling текущего запуска (" + who + ")"
    if polls[0][0] > start + skew:
        return "UNKNOWN", "polling позже старта больше чем на 300 с — пояс журнала не UTC? (" + who + ")"
    if young:   # verify3 x1/x1b/x5: цикл падений после строки polling и строки чужого процесса той же секунды
        return "UNKNOWN", "запуск моложе 300 с — устойчивость запуска не доказана (" + who + ")"
    return "OK", "вход выпуска OK (" + mo.group(1) + ") · Bot polling started · " + who


def check_polling(lines, run0=None, run1=None, now=None):
    """Polling ТЕКУЩЕГО запуска (RCFIX2010 C) → (ok, слова), форма прежняя. Без границы запуска — НЕИЗВЕСТНО:
    строка «Bot polling started» прошлого запуска больше не доказательство."""
    status, why = _run_verdict(lines, run0, run1, now if now is not None else _utcnow())
    if status == "OK":
        return True, why
    if status == "UNKNOWN":
        return False, "запуск не доказан — НЕИЗВЕСТНО: " + why
    return False, why


def check_log_health(lines, start_dt):
    if not lines:
        return False, "лог пуст/недоступен", 0
    last_ts = None
    for ln in reversed(lines):
        last_ts = _parse_log_ts(ln)
        if last_ts:
            break
    age = _fmt_age(_utcnow() - last_ts) if last_ts else "?"
    # Лог копит записи всех прошлых запусков (не ротируется). Считаем ошибки ТОЛЬКО
    # текущего запуска: ведём «текущий timestamp» — строки-продолжения трейсбэка без
    # своей даты наследуют время родительской строки, поэтому датируются корректно.
    errors = 0
    cur_ts = None
    for ln in lines:
        ts = _parse_log_ts(ln)
        if ts:
            cur_ts = ts
        if start_dt and (cur_ts is None or cur_ts < start_dt):
            continue
        if "[ERROR]" in ln or "[CRITICAL]" in ln or "Traceback (most recent" in ln:
            errors += 1
    return True, "посл. строка " + age + " назад; ошибок с старта: " + str(errors), errors


def check_commit():
    out = _run(["git", "-C", ROOT, "log", "-1", "--format=%h %ci %s"])
    return (bool(out), out or "git недоступен")


# ─── WA-0 watchdog helpers ────────────────────────────────────────────────────
# State file tracking consecutive probe failures for the watchdog.
# Reset on successful probe; on N consecutive failures → auto-restart.
_WA_PROBE_FAIL_FILE = os.path.join(ROOT, ".wa_watchdog_fails")
_WA_WATCHDOG_THRESHOLD = 2   # consecutive probe failures that trigger auto-restart


def _wa_probe(port: int, verify_token: str, timeout: float = 6.0):
    """Real HTTP GET handshake: GET /wa-webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=probe42.
    Returns (ok:bool, detail:str).  Port-probe alone is unreliable (incident 15.07: TCP open, HTTP hung)."""
    challenge = "probe42"
    url = ("http://127.0.0.1:" + str(port)
           + "/wa-webhook?hub.mode=subscribe&hub.verify_token=" + verify_token
           + "&hub.challenge=" + challenge)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(256).decode("utf-8", errors="replace")
            if resp.status == 200 and challenge in body:
                return True, "handshake " + str(resp.status) + "/" + challenge
            return False, "bad resp " + str(resp.status) + " " + repr(body[:40])
    except urllib.error.HTTPError as e:
        return False, "HTTP " + str(e.code)
    except Exception as e:
        return False, type(e).__name__


def _wa_watchdog_count():
    """Return consecutive probe-failure count from state file (0 if missing/unreadable)."""
    try:
        with open(_WA_PROBE_FAIL_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _wa_watchdog_set(n: int):
    try:
        with open(_WA_PROBE_FAIL_FILE, "w", encoding="utf-8") as f:
            f.write(str(n))
    except Exception:
        pass


def _wa_watchdog_reset():
    try:
        os.remove(_WA_PROBE_FAIL_FILE)
    except Exception:
        pass


def _wa_restart_unit():
    """systemctl restart wa-webhook. Returns True on success (returncode==0)."""
    try:
        r = subprocess.run(["systemctl", "restart", "wa-webhook"],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def check_wa_webhook():
    """WA-0 health check: service state + real HTTP handshake probe + watchdog.

    Skipped (returns None, info-string) when WA_VERIFY_TOKEN is not set in .env.

    Port-level liveness check is insufficient — the incident of 15.07 proved that
    TCP accepted connections while the HTTP layer was completely hung.  This probe
    does a real GET handshake and, on _WA_WATCHDOG_THRESHOLD consecutive failures,
    auto-restarts the unit (logged in the health report).
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    if not os.environ.get("WA_VERIFY_TOKEN"):
        return None, "не настроен (WA_VERIFY_TOKEN не задан)"

    state = _run(["systemctl", "is-active", "wa-webhook"])
    svc_ok = (state == "active")

    q_info = ""
    try:
        import sqlite3 as _sq
        db_path = os.environ.get("WA_QUEUE_DB") or os.path.join(ROOT, "wa_queue.db")
        if os.path.exists(db_path):
            with _sq.connect(db_path, timeout=2) as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM wa_inbox WHERE status='new'"
                ).fetchone()[0]
            q_info = ", очередь new=" + str(n)
        else:
            q_info = ", db отсутствует"
    except Exception as e:
        q_info = ", db err=" + type(e).__name__

    if not svc_ok:
        _wa_watchdog_reset()
        return False, state + q_info

    # Real HTTP handshake probe (port-probe lied: TCP open ≠ HTTP responds, incident 15.07)
    port = int(os.environ.get("WA_WEBHOOK_PORT", "8765"))
    verify_token = os.environ.get("WA_VERIFY_TOKEN", "")
    probe_ok, probe_detail = _wa_probe(port, verify_token)

    # Watchdog: track consecutive failures; restart on threshold
    watchdog_note = ""
    if probe_ok:
        _wa_watchdog_reset()
    else:
        fails = _wa_watchdog_count() + 1
        _wa_watchdog_set(fails)
        if fails >= _WA_WATCHDOG_THRESHOLD:
            restarted = _wa_restart_unit()
            if restarted:
                _wa_watchdog_reset()
                watchdog_note = " — ⚠️ wa-webhook перезапущен вотчдогом"
            else:
                watchdog_note = " — ⚠️ вотчдог: рестарт не удался"

    if probe_ok:
        detail = state + ", " + probe_detail + q_info
    else:
        detail = state + ", PROBE FAIL: " + probe_detail + watchdog_note + q_info
    return probe_ok, detail


def check_brain_latency():
    """Замер latency чтения Brain-доков (ранний детектор износа). Вернуть (warn:bool, detail:str).
    warn=True если док читается > СВОЕГО порога ИЛИ не прочитался — сигнал деградации.
    Порог пер-доковый (журналы 10с, base-доки большие → высокий), чтобы не ложно тревожить."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        from bridge_client import BridgeClient
    except Exception as e:
        return True, "зонд не запустился: " + type(e).__name__
    parts = []
    warn = False
    for label, kw, thr in _BRAIN_DOCS:
        try:
            bc = BridgeClient(timeout=thr + _BRAIN_PROBE_MARGIN)
        except Exception as e:
            return True, "зонд не запустился: " + type(e).__name__
        t0 = time.time()
        try:
            r = bc._call("read_doc", **kw)
            dt = time.time() - t0
            if not r.get("ok"):
                warn = True
                parts.append(label + " ✗(" + str(r.get("error", "?")) + ")")
            elif dt > thr:
                warn = True
                parts.append(label + " " + ("%.0f" % dt) + "с⚠️(>" + str(thr) + ")")
            else:
                parts.append(label + " " + ("%.1f" % dt) + "с")
        except Exception:
            warn = True
            parts.append(label + " ✗(timeout>" + str(thr) + "с)")
    return warn, "; ".join(parts)


# === §12: ранний детектор «кредит платного ключа на нуле» — ОДИН пуш ДО обвала money/vision ====
# Плановая 1-токенная синт-проба ANTHROPIC_API_KEY. Как check_brain_latency ловит латентность —
# эта ловит исчерпание кредита/отзыв ключа ЗАРАНЕЕ (400 credit-too-low / 401), пока обвал ещё не
# начался. Дедуп (Поправка А штаба): ОДИН warning на эпизод (файл-маркер), не повторяем пока не
# восстановится.
_CREDIT_EPISODE_FILE = os.path.join(ROOT, ".api_credit_episode")


def _classify_credit_error(exc):
    """Классификация ошибки синт-пробы → (warn:bool, detail:str). Чистая/тестируемая подставными
    исключениями: смотрим имя типа + текст, реальные anthropic-ошибки НЕ конструируем."""
    name = type(exc).__name__
    msg = str(exc).lower()
    if name == "AuthenticationError" or "invalid x-api-key" in msg or "authentication" in msg:
        return True, "❗платный ключ невалиден/отозван (" + name + ")"
    if ("credit balance is too low" in msg or "credit" in msg
            or "billing" in msg or "too low" in msg):
        return True, "❗кредит платного ключа на нуле (" + name + ")"
    # прочее (сеть/таймаут/5xx) — НЕ про кредит, ранний детектор не паникует
    return False, "проба не про кредит (" + name + ")"


def check_api_credit(_probe=None):
    """1-токенная синт-проба платного ключа → (warn:bool, detail:str). warn=True на кредит-на-нуле /
    отзыв ключа. _probe: инъекция для тестов — callable(), бросает/возвращает как messages.create."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
    except Exception:
        pass
    if os.environ.get("ANTHROPIC_API_KEY") in (None, ""):
        return False, "нет ANTHROPIC_API_KEY (проба пропущена)"
    probe = _probe
    if probe is None:
        try:
            import anthropic
            cl = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                     timeout=15, max_retries=0)

            def probe():
                return cl.messages.create(model="claude-haiku-4-5", max_tokens=1,
                                          messages=[{"role": "user", "content": "ping"}])
        except Exception as e:
            return False, "зонд не собрался (" + type(e).__name__ + ")"
    try:
        probe()
        return False, "кредит ок (1-токенная проба прошла)"
    except Exception as e:
        return _classify_credit_error(e)


def _credit_episode_should_push(warn):
    """Дедуп кредит-warning (Поправка А): ОДИН пуш на эпизод. warn и эпизод НЕ открыт → открыть+True;
    warn и уже открыт → тихо (False); НЕ warn → закрыть эпизод (восстановилось), пуша нет (False)."""
    active = os.path.exists(_CREDIT_EPISODE_FILE)
    if warn:
        if active:
            return False
        try:
            with open(_CREDIT_EPISODE_FILE, "w", encoding="utf-8") as f:
                f.write(_utcnow().isoformat())
        except Exception:
            pass
        return True
    if active:
        try:
            os.remove(_CREDIT_EPISODE_FILE)
        except Exception:
            pass
    return False


def build_report():
    """Собрать отчёт здоровья. Вернуть (report, summary, code, brain_warn, credit_warn).
    code: 0 = ок/предупреждение, 1 = реальная проблема (лежит компонент, простой Splinter, текущий запуск не доказан).
    brain_warn: ранняя деградация чтения Brain-дока (>10с/ошибка) — повод для пуша.
    credit_warn: ранний детектор «кредит платного ключа на нуле / ключ отозван» — повод для пуша."""
    # RCFIX2010 C: граница запуска читается ДО и ПОСЛЕ журнала — смена процесса за время чтения даёт НЕИЗВЕСТНО.
    run0 = _read_run()
    lines = _read_log_lines()
    run1 = _read_run()
    svc_ok, svc_d, start_dt, _ = check_service()
    br_ok, br_d = check_bridge()
    au_ok, au_d = check_auditor(lines)
    pl_ok, pl_d = check_polling(lines, run0, run1)
    log_ok, log_d, errors = check_log_health(lines, start_dt)
    brain_warn, brain_d = check_brain_latency()
    credit_warn, credit_d = check_api_credit()
    _, commit_d = check_commit()
    wa_ok, wa_d = check_wa_webhook()

    rows = [
        (svc_ok, "Splinter сервис", svc_d),
        (br_ok, "Bridge        ", br_d),
        (au_ok, "Аудитор       ", au_d),
        (pl_ok, "Polling       ", pl_d),
    ]
    out = ["🩺 TurboBaby — здоровье системы (" + _utcnow().strftime("%Y-%m-%d %H:%M UTC") + ")",
           "─" * 46]
    for ok, name, detail in rows:
        out.append((OK if ok else BAD) + " " + name + "  " + detail)
    # лог — мягкий сигнал: свежесть инфо, ошибки — предупреждение
    out.append((WARN if errors else INFO) + "Лог            " + log_d)
    # Brain-латентность — ранний детектор износа доков (порог 10с)
    out.append((WARN if brain_warn else OK) + " Brain read     " + brain_d)
    # Кредит платного ключа — ранний детектор обвала money/vision (кредит-на-нуле / отзыв ключа)
    out.append((WARN if credit_warn else OK) + " Кредит API     " + credit_d)
    # WA-0 webhook — только если настроен (WA_VERIFY_TOKEN задан)
    if wa_ok is not None:
        out.append((OK if wa_ok else BAD) + " WA webhook     " + wa_d)
    elif wa_d and "не настроен" not in wa_d:
        out.append(INFO + "WA webhook     " + wa_d)
    out.append(INFO + "Прод           " + commit_d)
    out.append("─" * 46)

    # ❌ ПРОБЛЕМА — только реально лежащие компоненты (бот не работает / недоступен).
    problems = []
    if not svc_ok:
        problems.append("Splinter не active")
    if not br_ok:
        problems.append("Bridge не отвечает")
    if not au_ok:
        problems.append("аудитор не подтверждён")
    if not pl_ok:
        # RCFIX2010 C: слова вердикта текущего запуска (простой / нет polling / НЕИЗВЕСТНО), а не прежнее «нет polling».
        problems.append(pl_d)
    # WA-0 — 06.09.2026. Наблюдение за вебхуком было ЗДЕСЬ И РАНЬШЕ (проба рукопожатия +
    # вотчдог), а вот РЕАКЦИИ не было: строка «❌ WA webhook» печаталась в тело отчёта, но в
    # `problems` не попадала, поэтому сводка оставалась «✅ ВСЁ ОК», code=0 и пуш не уходил —
    # мёртвый вебхук был виден отчёту и невидим владельцу. Классу дал имя разбор KB_WA_PLAN
    # («юнит не наблюдает никто»); премиса оказалась ВЕРНА наполовину — смотрели, но молчали.
    #
    # РАЗЛИЧАЕМ False И None. `check_wa_webhook()` отдаёт None, когда WA не настроен вовсе
    # (WA_VERIFY_TOKEN пуст) — это не поломка, а «канала нет». Проблемой считается РОВНО
    # измеренный отказ: `wa_ok is False`. Наивное `if not wa_ok` записало бы в проблемы и
    # ненастроенный канал, то есть подняло бы тревогу на каждой машине без WA.
    if wa_ok is False:
        problems.append("WA webhook не отвечает")

    if problems:
        summary = BAD + " ПРОБЛЕМА: " + "; ".join(problems)
        code = 1
    elif credit_warn:
        # Кредит платного ключа на нуле / ключ отозван — обвал money/vision близко, ранний пуш.
        summary = WARN + "Кредит платного ключа на нуле/ключ отозван — money/vision под угрозой (см. Кредит API)"
        code = 0
    elif brain_warn:
        # Деградация чтения Brain-дока (>10с / ошибка) — ранний симптом износа, пушим Филиппу.
        summary = WARN + "Brain-док читается медленно/с ошибкой — ранний симптом, глянь (см. Brain read)"
        code = 0
    elif errors:
        # Ошибки в логе текущего запуска — мягкий сигнал: бот жив, но стоит глянуть.
        summary = WARN + "РАБОТАЕТ, но " + str(errors) + " ошибок в логе с старта — стоит глянуть"
        code = 0
    else:
        summary = OK + " ВСЁ ОК"
        code = 0
    out.append(summary)
    return "\n".join(out), summary, code, brain_warn, credit_warn


def main(argv):
    push = "--push" in argv            # пуш Филиппу при проблеме (❌) или деградации Brain (ранний детектор)
    push_always = "--push-always" in argv  # пуш всегда, даже когда всё ✅
    report, summary, code, brain_warn, credit_warn = build_report()
    print(report)
    # Дедуп кредит-warning (Поправка А): ОДИН пуш на эпизод, не повторяем пока не восстановится.
    credit_first = _credit_episode_should_push(credit_warn)
    if push_always or (push and (code != 0 or brain_warn or credit_first)):
        # RCFIX2010 C: ОДИН вызов за прогон, повтора нет. notify сводит «точно не отправлено» и «ответ потерян»
        # (таймаут, сеть) в один False (notify.py:140–146), поэтому «отправлен» — только при True (Telegram ok); иначе
        # доставка НЕИЗВЕСТНА, а не достоверный отказ: слепой повтор дал бы дубль. Следующая попытка — следующий прогон
        # таймера.
        try:
            from notify import notify
            ok = notify(report, force=True)   # боевой health-алерт — тест-мут не глушит
        except Exception as e:
            print("[push] доставка не подтверждена (НЕ отправлен или ответ потерян — неизвестно): ошибка "
                  + type(e).__name__ + " " + str(e) + " — повтора нет")
        else:
            if ok is True:
                print("[push] отправлен (Telegram ok)")
            else:
                print("[push] доставка не подтверждена (НЕ отправлен или ответ потерян — неизвестно) — повтора нет")
    return code


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
