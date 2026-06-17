#!/usr/bin/env python3
"""ЗДОРОВЬЕ СИСТЕМЫ TurboBaby — одна read-only проверка: всё живо или где проблема.

Пункт 2 «лестницы фундамента» (docs/project_state.md → «ФУНДАМЕНТ ПЕРЕД АВТОНОМИЕЙ»).
Ничего НЕ пишет, НЕ рестартит, НЕ деплоит. Запуск одной командой:
    venv/bin/python3 health.py

Проверяет:
  • Splinter   — systemctl active/running + uptime + счётчик рестартов;
  • Bridge     — ping-экшен (alive + версия), живой запрос;
  • Аудитор    — маркеры старт-лога (Auditor ✅ + Auditor LLM ✅);
  • Polling    — «Bot polling started» в старт-логе;
  • Лог        — свежесть последней строки (инфо: бот event-driven, тишина ≠ смерть)
                 + ошибки/Traceback ПОСЛЕ старта сервиса;
  • Прод       — последний коммит (что сейчас в проде).

Exit 0 = всё ок, 1 = есть проблема. (--push пока НЕ реализован — предложен отдельным шагом.)
"""
import os
import re
import subprocess
import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, "splinter.log")
OK, BAD, INFO, WARN = "✅", "❌", "ℹ️ ", "⚠️ "


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


def check_bridge():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(ROOT, ".env"))
        from bridge_client import BridgeClient
        r = BridgeClient().ping()
        if r.get("ok"):
            return True, "alive v" + str(r.get("version", "?"))
        return False, "ответ без ok: " + str(r.get("error", r))
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


def check_polling(lines):
    p = _last_match(lines, "Bot polling started")
    return (bool(p), "Bot polling started" if p else "нет «Bot polling started» в логе")


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


def main():
    lines = _read_log_lines()
    svc_ok, svc_d, start_dt, _ = check_service()
    br_ok, br_d = check_bridge()
    au_ok, au_d = check_auditor(lines)
    pl_ok, pl_d = check_polling(lines)
    log_ok, log_d, errors = check_log_health(lines, start_dt)
    _, commit_d = check_commit()

    rows = [
        (svc_ok, "Splinter сервис", svc_d),
        (br_ok, "Bridge        ", br_d),
        (au_ok, "Аудитор       ", au_d),
        (pl_ok, "Polling       ", pl_d),
    ]
    print("🩺 TurboBaby — здоровье системы (" + _utcnow().strftime("%Y-%m-%d %H:%M UTC") + ")")
    print("─" * 46)
    for ok, name, detail in rows:
        print((OK if ok else BAD) + " " + name + "  " + detail)
    # лог — мягкий сигнал: свежесть инфо, ошибки — предупреждение
    print((WARN if errors else INFO) + "Лог            " + log_d)
    print(INFO + "Прод           " + commit_d)
    print("─" * 46)

    # ❌ ПРОБЛЕМА — только реально лежащие компоненты (бот не работает / недоступен).
    problems = []
    if not svc_ok:
        problems.append("Splinter не active")
    if not br_ok:
        problems.append("Bridge не отвечает")
    if not au_ok:
        problems.append("аудитор не подтверждён")
    if not pl_ok:
        problems.append("нет polling")

    if problems:
        summary = BAD + " ПРОБЛЕМА: " + "; ".join(problems)
        print(summary)
        return summary, 1
    # Ошибки в логе текущего запуска — мягкий сигнал: бот жив, но стоит глянуть.
    if errors:
        summary = WARN + "РАБОТАЕТ, но " + str(errors) + " ошибок в логе с старта — стоит глянуть"
        print(summary)
        return summary, 0
    summary = OK + " ВСЁ ОК"
    print(summary)
    return summary, 0


if __name__ == "__main__":
    import sys
    _, code = main()
    sys.exit(code)
