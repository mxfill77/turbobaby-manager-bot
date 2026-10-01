#!/usr/bin/env python3
"""О9 — РУКИ ВНЕШНЕГО ПРИБОРА ЗА ПОКАЗОМ WhatsApp В TELEGRAM (01.10.2026, задание 0090-76g).

ПОЧЕМУ ВНЕ СЛУЖБЫ. Своя тревога wa-tg-mirror (`watch_step`) ходит только при включённом и готовом
показе, тем же ботом в ту же группу: «показ стоит», зависание и смерть службы она не видит по
построению — наблюдатель не живёт на том, за чем следит. Этот прибор живёт в слое ожиданий
(`expectations.timer`, раз в 10 минут), судит РЕЗУЛЬТАТ и кричит каналом демона (лента), а не
ботом показа.

КОНТРАКТ (судья — `expectations.wa_mirror_state`, чистая функция): каждая живая строка wa_inbox
после точки включения показа показана в своей теме не позже 10 минут.

ЗДЕСЬ ТОЛЬКО СБОР ФАКТОВ, и каждый — чтением:
  юнит   — `systemctl show` (ActiveState, SubState, MainPID, ActiveEnterTimestamp);
  флаг   — ПОРЯДКОМ СЛУЖБЫ: окружение процесса (/proc/<MainPID>/environ) сильнее файла ключей —
           служба зовёт load_dotenv БЕЗ перезаписи заданного. Из обоих источников берётся ТОЛЬКО
           флаг; толкует значение функция службы `wa_tg_mirror._flag_on`;
  точка включения — kv.show_start_id в wa_tg_mirror.db (mode=ro);
  живые строки — wa_inbox (mode=ro) после точки; живость и ключ — функциями службы
           `_is_live` / `_row_key`; «показано» — строка shown с ключом «msg:<ключ>» в ЛЮБОМ
           состоянии, как у самой службы (`_is_shown`: «в отправке» и «без ответа» повтора не ждут);
  пояснение — последние «сводка: показ=…» и «показ: СТОИТ — …» хвоста wa_tg_mirror.log. Это
           пояснение к тревоге, а не решение: решает только wa_inbox против таблицы показанного.
Ничего не пишет, никуда не шлёт, код службы не меняет — берёт у неё только чистые функции
импортом. В факты не попадают тексты, номера и имена — только id строк, время и числа.

Usage: venv/bin/python3 expect_wa_mirror.py [--root <дерево>] [--probe]
  один прогон без отправки: вердикт и числа. --probe — счёт строк очереди и при выключенном флаге.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

import wa_tg_mirror as M                # только чистые функции и константы; main() не зовётся

UNIT = "wa-tg-mirror"
LOG_TAIL = 65536
_LOG_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_SUMMARY = "сводка: показ="
_STOIT = "показ: СТОИТ — "


def paths(root=None):
    """Пути службы — те же умолчания, что у `wa_tg_mirror._env` (база показанного рядом с очередью)."""
    root = root or M.ROOT
    queue = os.path.join(root, "wa_queue.db")
    return {"queue_db": queue,
            "state_db": os.path.join(os.path.dirname(queue), "wa_tg_mirror.db"),
            "log": os.path.join(root, "wa_tg_mirror.log"),
            "keys": os.path.join(root, ".env")}


# ─────────────────────────────── юнит ─────────────────────────────────────────────────────
def unit_facts(run=None):
    """→ {"active": bool|None, "state", "pid", "since", "addr"[, "err"]}. None = не прочитано."""
    run = run or subprocess.run
    addr = "systemctl show %s" % UNIT
    try:
        p = run(["systemctl", "show", UNIT, "--timestamp=unix", "-p", "ActiveState", "-p",
                 "SubState", "-p", "MainPID", "-p", "ActiveEnterTimestamp"],
                capture_output=True, text=True, timeout=20)
    except Exception as e:                                           # noqa: BLE001
        return {"active": None, "err": type(e).__name__, "addr": addr}
    kv = {}
    for line in (p.stdout or "").splitlines():
        k, sep, v = line.partition("=")
        if sep:
            kv[k.strip()] = v.strip()
    state = kv.get("ActiveState") or ""
    if p.returncode != 0 or not state:
        return {"active": None, "err": "код %s, ActiveState пуст" % p.returncode, "addr": addr}
    raw = (kv.get("ActiveEnterTimestamp") or "").lstrip("@")
    try:
        since = float(raw) if raw else None
    except ValueError:
        since = None
    try:
        pid = int(kv.get("MainPID") or 0)
    except ValueError:
        pid = 0
    return {"active": state == "active", "state": "%s/%s" % (state, kv.get("SubState") or "?"),
            "pid": pid, "since": since, "addr": addr}


# ─────────────────────────────── флаг — порядком службы ───────────────────────────────────
def proc_flag(pid, proc="/proc"):
    """Окружение процесса → {флаг: значение} | {} (флага нет) | None (не прочитано). Прочее не берётся."""
    if not pid:
        return None
    try:
        with open(os.path.join(proc, str(pid), "environ"), "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    head = (M.FLAG_NAME + "=").encode()
    for item in raw.split(b"\0"):
        if item.startswith(head):
            return {M.FLAG_NAME: item[len(head):].decode("utf-8", "replace")}
    return {}


def file_flag(path):
    """Файл ключей → {флаг: значение} | {} | None (не прочитан). Читает та же библиотека, что у
    службы; файла нет — как у службы, флага нет. Прочие ключи не берутся."""
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(path) if os.path.exists(path) else {}
    except Exception:                                                # noqa: BLE001
        return None
    return {M.FLAG_NAME: vals.get(M.FLAG_NAME)} if M.FLAG_NAME in vals else {}


def flag_of(proc_vals, file_vals, keys_addr="файл ключей"):
    """Порядок службы: окружение процесса сильнее файла (load_dotenv без перезаписи)."""
    if proc_vals is None:
        return {"on": None, "err": "окружение процесса не прочитано", "addr": "/proc/<MainPID>/environ"}
    if M.FLAG_NAME in proc_vals:
        return {"on": M._flag_on(proc_vals[M.FLAG_NAME]), "src": "окружение юнита"}
    if file_vals is None:
        return {"on": None, "err": "файл ключей не прочитан", "addr": keys_addr}
    if M.FLAG_NAME in file_vals:
        return {"on": M._flag_on(file_vals[M.FLAG_NAME]), "src": "файл ключей"}
    return {"on": False, "src": "не задан — по умолчанию выключен"}


# ─────────────────────────────── базы: только mode=ro ─────────────────────────────────────
def _ro(path):
    if not os.path.exists(path):
        raise sqlite3.OperationalError("файла нет")
    return sqlite3.connect("file:%s?mode=ro" % os.path.abspath(path).replace("\\", "/"),
                           uri=True, timeout=10)


def _err(e):
    return "%s: %s" % (type(e).__name__, str(e)[:80])


def state_facts(path):
    """→ (факты, ключи показанного «msg:%» | None)."""
    try:
        c = _ro(path)
        try:
            r = c.execute("SELECT v FROM kv WHERE k='show_start_id'").fetchone()
            shown = {k for (k,) in c.execute("SELECT key FROM shown WHERE key LIKE 'msg:%'")}
        finally:
            c.close()
        start = int(r[0]) if r and str(r[0]).strip() != "" else None
    except (sqlite3.Error, ValueError, TypeError) as e:
        return {"err": _err(e), "addr": path}, None
    return {"start_id": start, "shown": len(shown), "addr": path}, shown


def queue_facts(start, shown, path):
    """Живые строки после точки включения: сколько, и какие ещё не показаны → [[id, ts_queued]]."""
    try:
        c = _ro(path)
        c.row_factory = sqlite3.Row
        try:
            rows = c.execute("SELECT id, ts_queued, msg_type, echo, history, wamid FROM wa_inbox "
                             "WHERE id > ? ORDER BY id", (int(start),)).fetchall()
        finally:
            c.close()
        live, pending = 0, []
        for r in rows:
            if not M._is_live(r):
                continue
            live += 1
            if ("msg:" + M._row_key(r)) not in shown:
                pending.append([int(r["id"]), float(r["ts_queued"] or 0)])
    except (sqlite3.Error, ValueError, TypeError, IndexError) as e:
        return {"err": _err(e), "addr": path}
    return {"live": live, "pending": pending, "addr": path}


# ─────────────────────────────── пояснение из журнала службы ──────────────────────────────
def log_hint(text):
    """Последние «сводка: показ=…» и «показ: СТОИТ — …» → {"show","ts","stoit","stoit_ts"}."""
    out = {}
    for line in (text or "").splitlines():
        m = _LOG_TS.match(line)
        ts = m.group(1) if m else ""
        i = line.find(_SUMMARY)
        if i >= 0:
            out["show"] = line[i + len(_SUMMARY):].split(" ", 1)[0]
            out["ts"] = ts
        j = line.find(_STOIT)
        if j >= 0:
            out["stoit"] = line[j + len(_STOIT):].strip()[:120]
            out["stoit_ts"] = ts
    return out


def _tail(path, nbytes=LOG_TAIL):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


# ─────────────────────────────── сбор ─────────────────────────────────────────────────────
def facts(now=None, root=None, run=None, proc="/proc", probe=False):
    """Факты О9. Не активен или не прочитан юнит — флаг и базы не нужны: судья решит без них."""
    p = paths(root)
    u = unit_facts(run)
    out = {"unit": u, "hint": log_hint(_tail(p["log"]))}
    if not u.get("active") and not probe:
        return out
    pv = proc_flag(u.get("pid"), proc)
    fv = file_flag(p["keys"]) if (pv is not None and M.FLAG_NAME not in pv) else None
    out["flag"] = flag_of(pv, fv, p["keys"])
    if not out["flag"].get("on") and not probe:
        return out
    st, shown = state_facts(p["state_db"])
    out["state"] = st
    if st.get("err"):
        return out
    if st.get("start_id") is None and not probe:
        return out
    out["queue"] = queue_facts(st.get("start_id") or 0, shown or set(), p["queue_db"])
    return out


def main(argv=None):
    import expectations
    argv = list(sys.argv[1:] if argv is None else argv)
    root = argv[argv.index("--root") + 1] if "--root" in argv else None
    probe = "--probe" in argv
    now = time.time()
    cfg = expectations.config(os.environ)
    f = facts(now, root=root, probe=probe)
    st, info = expectations.wa_mirror_state({"now": now, "wa_mirror": f}, cfg, now)
    print(expectations.wa_mirror_line(st, info))
    q = f.get("queue") or {}
    brief = {"unit": {k: f["unit"].get(k) for k in ("active", "state", "pid", "since")},
             "flag": {k: (f.get("flag") or {}).get(k) for k in ("on", "src")},
             "state": {k: (f.get("state") or {}).get(k) for k in ("start_id", "shown", "err")},
             "queue": {"live": q.get("live"), "pending": len(q.get("pending") or []),
                       "err": q.get("err"),
                       "late_ids": [i for i, t in (q.get("pending") or [])
                                    if now - t > float(cfg.get("wa_mirror") or 0)][:20]},
             "hint": f.get("hint"), "limit_sec": cfg.get("wa_mirror"), "now": round(now, 1),
             "probe": probe}
    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
