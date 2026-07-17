# -*- coding: utf-8 -*-
"""Стражи класса 193 «тест-фикстуры утекают в живую очередь» (17.07.2026).

Два рубежа:
  РУБЕЖ 1 (клиент): BridgeClient.enqueue_task с каноническим фикстур-текстом («проверь X»,
    «сделай X», «task», «конверт 999 …сделать нечто», TEST-…) → {ok:False, fixture_guard:True}
    БЕЗ сети. Обход BRIDGE_ALLOW_FIXTURES=1 — транспорт уходит как раньше.
  РУБЕЖ 2 (демон): фикстура дошла до живой очереди (чужой клиент/обход) → process_new даёт
    мгновенный failed с ⛔-меткой БЕЗ claude -p. ORCH_TEST_MODE=1 (его ставит gate.py всем
    тестам) фильтр выключает — прочие голдены гоняют фикстуры через мок свободно.
Живые задачи под гард НЕ попадают: реальный конверт 999 без «сделать нечто», длинные тексты,
«проверь X у клиента» — проходят.

УРОК ЭТОГО ЖЕ КЛАССА (17.07, первый прогон этого файла): мокался только OD.subprocess.run,
а run_task спавнит claude через OD._POPEN — недомоканный тест сам запустил ЖИВОЙ
`claude -p … "проверь X"` (вектор инцидента 16.07 дословно). Мокаем ОБЕ точки спавна.
Сети/Telegram/claude нет — всё мокнуто."""
import os, sys, json, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"; os.environ["CURATOR"] = "0"
os.environ.pop("BRIDGE_ALLOW_FIXTURES", None)   # чистый старт (гейт мог унаследовать)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import bridge_client
from bridge_client import BridgeClient

FIXTURES = [
    "проверь X", " сделай X ", "task", "тест", "нечто", "проверь x.",
    "TEST-любой текст задачи",
    "[конверт одобренной заявки 999] Филипп нажал «да» на заявку: сделать нечто\nИсходная задача: X",
    "[шаг 2/6 родитель 10] сделай X",
]
LIVE = [
    "проверь X у клиента 66812345678 в wa_queue.db",          # не голая заглушка
    "[конверт одобренной заявки 999] Филипп нажал «да» на заявку: рестарт splinter",  # живой 999
    "[шаг 2/6 родитель 10] правь suggest.py по трассе #51",   # живой шаг родителя 10
    "read-only: проверь wa_queue.db на VPS",
    "тестируй новую ветку резолвера",                          # «тест» лишь префикс слова
]

print("(1) РУБЕЖ 1: enqueue_task блокирует фикстуры БЕЗ сети:")
c = BridgeClient(url="http://x", token="x", timeout=1)
calls = []
c._post = lambda action, **kw: (calls.append(kw), {"ok": True, "id": 1})[1]
for t in FIXTURES:
    r = c.enqueue_task("Filipp-328", t)
    res.append(ok(r.get("ok") is False and r.get("fixture_guard") is True and not calls,
                  f"фикстура блокирована до сети: {t[:45]!r}"))
    calls.clear()

print("(2) РУБЕЖ 1: живые тексты проходят как раньше:")
for t in LIVE:
    r = c.enqueue_task("Filipp-328", t)
    res.append(ok(r.get("ok") is True and len(calls) == 1, f"живой текст прошёл: {t[:45]!r}"))
    calls.clear()

print("(3) РУБЕЖ 1: BRIDGE_ALLOW_FIXTURES=1 — осознанный обход (транспорт-тесты):")
os.environ["BRIDGE_ALLOW_FIXTURES"] = "1"
r = c.enqueue_task("Filipp-328", "тест")
res.append(ok(r.get("ok") is True and len(calls) == 1, "обход работает: «тест» ушёл в транспорт"))
calls.clear()
os.environ.pop("BRIDGE_ALLOW_FIXTURES", None)

# ---- РУБЕЖ 2: демон (ОБЕ точки спавна мокнуты: subprocess.run И _POPEN — урок 17.07) ----
import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 100
    def enqueue_task(s, frm, txt, lane=None):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid):
        r = s.rows.get(int(tid))
        if not r or r["status"] != "new":
            return {"ok": False, "error": "not_found_or_claimed"}
        r["status"] = "in_progress"; r["updated"] = now_iso()
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


class FakePopen:
    def __init__(s, out="", rc=0):
        s.returncode = None; s._out = out; s._rc = rc
    def communicate(s, timeout=None):
        if s.returncode is None: s.returncode = s._rc
        return s._out, ""
    def terminate(s): s.returncode = -15
    def kill(s): s.returncode = -9
    def poll(s): return s.returncode


CLAUDE_OUT = json.dumps({"result": "готово", "is_error": False,
                         "modelUsage": {"claude-fable-5": {"inputTokens": 1}}})
SPAWNS = []
def fake_run(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN:
        SPAWNS.append(list(args))
        return FakeProc(CLAUDE_OUT)
    return FakeProc("ok")
def fake_popen(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN:
        SPAWNS.append(list(args))
    return FakePopen(CLAUDE_OUT)
OD.subprocess.run = fake_run
OD._POPEN = fake_popen           # БЕЗ этого первый прогон спавнил ЖИВОЙ claude (урок класса!)
OD.MAX_CLAUDE_PROCS = 0; OD.MEM_MIN_MB = 0; OD.CLAUDE_RSS_TOTAL_MB = 0

print("(4) РУБЕЖ 2: фикстура в живой очереди → мгновенный failed, claude -p не звался:")
os.environ.pop("ORCH_TEST_MODE", None)   # боевой режим (гейт наследует ORCH_TEST_MODE=1 — снимаем)
fb = FakeBridge(); OD.bc = fb
tid = fb.enqueue_task("Filipp-328", "проверь X")["id"]
SPAWNS.clear()
OD.process_new()
row = fb.rows[tid]
res.append(ok(row["status"] == "failed", "фикстура → failed"))
res.append(ok("⛔" in row["result"] and "класс 193" in row["result"], "тело = ⛔-метка класса 193"))
res.append(ok(not SPAWNS, "claude -p НЕ вызывался (нулевая стоимость)"))

print("(5) РУБЕЖ 2: ORCH_TEST_MODE=1 — фильтр выключен, фикстура идёт штатным (МОКНУТЫМ) путём:")
os.environ["ORCH_TEST_MODE"] = "1"
fb = FakeBridge(); OD.bc = fb
tid = fb.enqueue_task("Filipp-328", "проверь X")["id"]
SPAWNS.clear()
OD.process_new()
res.append(ok(fb.rows[tid]["status"] != "new" and "⛔" not in str(fb.rows[tid]["result"]),
              "в тест-режиме фикстура обработана штатным путём (без ⛔)"))
res.append(ok(len(SPAWNS) >= 1, "спавн claude состоялся, но через МОК (обе точки перехвачены)"))
os.environ.pop("ORCH_TEST_MODE", None)

print("(6) РУБЕЖ 2: живая задача при боевом фильтре идёт в исполнение:")
fb = FakeBridge(); OD.bc = fb
tid = fb.enqueue_task("Filipp-328", "read-only: проверь wa_queue.db на VPS")["id"]
SPAWNS.clear()
OD.process_new()
res.append(ok("⛔" not in str(fb.rows[tid]["result"]), "живой текст фильтром не тронут"))

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
