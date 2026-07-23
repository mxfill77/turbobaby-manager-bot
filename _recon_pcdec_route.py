# -*- coding: utf-8 -*-
"""Read-only разведка очереди Bridge: задачи за последние 2 часа (обе полосы, все статусы).
Ищем судьбу ТЗ «локальный дирижёр-декомпозер» (пк: декомпозируй: ... 17:08/17:11 UTC 11.07)."""
import json
from datetime import datetime, timedelta, timezone

from bridge_client import BridgeClient

b = BridgeClient()
now = datetime.now(timezone.utc)
cutoff = now - timedelta(hours=2, minutes=30)

statuses = ["new", "in_progress", "needs_approval", "approved", "done", "failed"]
r = b.get_pending_multi(statuses, lane="all")
tasks = r.get("items") or []
print(f"ok={r.get('ok')} err={r.get('error')} total fetched: {len(tasks)}; "
      f"keys sample: {list(tasks[0].keys()) if tasks else '-'}")


def parse_ts(t):
    for k in ("updated", "created", "ts"):
        v = t.get(k)
        if not v:
            continue
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(str(v), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


recent = []
for t in tasks:
    ts = parse_ts(t)
    if ts is None or ts >= cutoff:
        recent.append((ts, t))

recent.sort(key=lambda x: (x[0] or now))
print(f"recent (>= {cutoff:%H:%M} UTC): {len(recent)}")
print("=" * 100)
for ts, t in recent:
    txt = str(t.get("task") or t.get("task_text") or "").replace("\n", " ⏎ ")
    print(f"id={t.get('id')} | from={t.get('from')} | lane={t.get('lane') or '-'} | "
          f"status={t.get('status')} | upd={t.get('updated') or t.get('created')}")
    print(f"  text[:160]: {txt[:160]}")
    if "дирижёр" in txt or "декомпоз" in txt.lower() or "pc_orchestrator" in txt:
        res = str(t.get("result") or "").replace("\n", " ⏎ ")
        print(f"  >>> КАНДИДАТ. result[:400]: {res[:400]}")
    print("-" * 100)
