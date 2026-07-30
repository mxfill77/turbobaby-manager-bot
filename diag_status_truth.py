#!/usr/bin/env python3
"""ЗАМЕР ПРАВДЫ СТАТУСА — сколько серверных задач помечены провалом, но несут работу.

Read-only: очередь читается GET-ом (get_pending), cc_log — read_doc. НИЧЕГО не мутирует,
чужие статусы не трогает. Зеркало ПК-замера (diag_status_truth на ПК-полосе, 30.07.2026).

Запуск:  venv/bin/python3 diag_status_truth.py [--hours 48] [--lane vps]

Окно каждой задачи = created → updated (терминальный момент). Улики:
  • коммиты репозитория в окне (git log --reverse);
  • записи журнала мозга в окне.
Источник записей для ИСТОРИИ — сам cc_log (разбор строк «KIND ДАТА ВРЕМЯ UTC (канал): …»):
реестр cc_log_ledger.jsonl заведён 30.07.2026 и прошлое не восстанавливает — честно считаем
историю по журналу, а живой демон опирается на реестр (сеть на каждом провале не дёргаем).

⚠️ ОКНО — НЕ АВТОРСТВО. В окно задачи попадают и параллельные сессии; замер отвечает на вопрос
«есть ли в окне следы работы», а не «эта ли задача их оставила».
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
import status_truth
from bridge_client import BridgeClient

STATUSES = ("new", "in_progress", "needs_approval", "approved", "done", "failed")
CCLOG_RE = re.compile(
    r"^(DONE|PLAN|NOTE|BLOCKED|WAITING|SKIPPED) (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC "
    r"\(([^)]*)\): (.*)$")


def cclog_entries(text):
    """Строки cc_log → [(datetime, строка)] (только разобравшиеся; остальное молча мимо)."""
    out = []
    for ln in str(text or "").splitlines():
        m = CCLOG_RE.match(ln.strip())
        if not m:
            continue
        try:
            t = datetime.datetime.strptime(m.group(2) + " " + m.group(3), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        out.append((t.replace(tzinfo=datetime.timezone.utc), ln.strip()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--lane", default="vps")
    a = ap.parse_args(argv)

    now = datetime.datetime.now(datetime.timezone.utc)
    since = now - datetime.timedelta(hours=a.hours)
    bc = BridgeClient()

    rows = {}
    for st in STATUSES:
        r = bc.get_pending(st, lane=a.lane)
        if not r.get("ok"):
            print("ОШИБКА чтения очереди (%s): %s" % (st, r.get("error")))
            continue
        for it in r.get("items", []):
            if isinstance(it, dict):
                it.setdefault("status", st)
                rows[str(it.get("id"))] = it

    doc = bc._call("read_doc", name="cc_log")
    journal = cclog_entries(doc.get("text", "")) if doc.get("ok") else []
    if not doc.get("ok"):
        print("ВНИМАНИЕ: cc_log не прочитан (%s) — записи журнала в замер не войдут"
              % doc.get("error"))

    in_window = []
    for it in rows.values():
        t = status_truth.parse_iso(it.get("updated")) or status_truth.parse_iso(it.get("created"))
        if t is not None and t >= since:
            in_window.append(it)
    in_window.sort(key=lambda x: int(x.get("id") or 0))
    failed = [x for x in in_window if str(x.get("status")) == "failed"]

    all_commits = status_truth.commits_in_window(since, now)
    print("ОКНО ЗАМЕРА: %s → %s UTC (%d ч), полоса %s"
          % (since.strftime("%Y-%m-%d %H:%M"), now.strftime("%Y-%m-%d %H:%M"), a.hours, a.lane))
    print("задач в окне: %d | провалов: %d | коммитов репо в окне: %d | строк журнала в окне: %d"
          % (len(in_window), len(failed), len(all_commits),
             len([1 for t, _ in journal if t >= since])))
    print("")

    carriers = []
    for it in failed:
        tid = it.get("id")
        start = (status_truth.claim_started(tid)
                 or status_truth.parse_iso(it.get("created")))
        end = status_truth.parse_iso(it.get("updated")) or now
        commits = status_truth.commits_in_window(start, end) if start else []
        writes = [ln for t, ln in journal if start and start <= t <= end]
        code = status_truth.code_of(it.get("result")) or "—"
        dur = int(((end - start).total_seconds() // 60)) if start else -1
        carry = bool(commits or writes)
        if carry:
            carriers.append(tid)
        print("#%-4s %s  окно %s→%s UTC (%s мин)  причина: %s"
              % (tid, "НЕСЁТ РАБОТУ" if carry else "пусто     ",
                 start.strftime("%m-%d %H:%M") if start else "?",
                 end.strftime("%H:%M"), dur if dur >= 0 else "?", code))
        print("      коммитов %d%s | записей журнала %d%s"
              % (len(commits),
                 (" (" + "; ".join(h for h, _ in commits[:5]) + ")") if commits else "",
                 len(writes),
                 (" (" + "; ".join(w[:60] for w in writes[:2]) + ")") if writes else ""))
        print("      итог: %s" % str(it.get("result") or "")[:150].replace("\n", " "))
    print("")
    print("ИТОГ: из %d провалов полосы %s за %d ч работу в своём окне несут %d (id %s)"
          % (len(failed), a.lane, a.hours, len(carriers),
             ", ".join(str(x) for x in carriers) or "—"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
