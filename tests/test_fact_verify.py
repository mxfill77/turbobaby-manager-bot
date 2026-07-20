"""FACT-ВЕРИФИКАЦИЯ (класс R11–R15, 19.07.2026).
Цель: «done = живой факт» — задача ОБЯЗАНА верифицировать эффект и включить блок «FACT:».
Демон помечает dev-задачи без FACT: как ⚠️ unverified и форсирует куратора (bypass CURATOR_SCOPE).

Проверки:
  (0) _result_has_fact: True при «FACT:» / «FACT :» / «fact:»; False без него;
  (1) APPROVAL_PREAMBLE содержит «FACT:» — требование в v3-преамбуле;
  (2) PLANNER_PREAMBLE содержит «FACT:» — напоминание в шагах декомпозера;
  (3) CURATOR_PREAMBLE содержит «FACT:» — куратор знает о верификации;
  (4) THINKER_PREAMBLE содержит «FACT:» — selfheal знает (думательный слой);
  (5) TASK_THINKER_PREAMBLE содержит «FACT:» — selfheal одиночки знает;
  (6) process_new: dev done С FACT: → нет пометки ⚠️, куратор без force_consult;
  (7) process_new: dev done БЕЗ FACT: → ⚠️ unverified в result, force_consult куратору;
  (8) process_new: Filipp-328 (не dev) done БЕЗ FACT: → нет пометки (только dev);
  (9) force_consult=True обходит CURATOR_SCOPE=1 (done без commit)."""
import os, sys
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "1"
os.environ["CURATOR_SCOPE"] = "0"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


# --- spy на _curator_consult ---
_real_consult = OD._curator_consult
consults = []
force_flags = []

def spy_consult(goal, result):
    consults.append((goal, result))
    return {"verdict": "closed", "tasks": [], "human": "", "reason": "spy-closed"}
OD._curator_consult = spy_consult


class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 400
    def add(s, status, text, frm="Filipp-328-dev", result=""):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": "2026-07-19T00:00:00+00:00"}
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed"}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, text, lane=None):
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}


_real_bc = OD.bc
_real_run_task = OD.run_task
_real_rp = OD._restart_pending
OD._restart_pending = lambda: False
OD.MAX_CLAUDE_PROCS = 0; OD.MEM_MIN_MB = 0; OD.CLAUDE_RSS_TOTAL_MB = 0


def setup(run_ret, frm="Filipp-328-dev", text="тз: починить gate"):
    fb = FakeBridge()
    OD.bc = fb
    OD.run_task = lambda tid, t, task_timeout=600, preamble=None: run_ret
    OD._curated.clear()
    consults.clear(); force_flags.clear()
    return fb, fb.add("new", text, frm=frm)


# (0) _result_has_fact
print("(0) _result_has_fact:")
res.append(ok(OD._result_has_fact("FACT: commit abc1234 в git log origin/main") is True,
              "FACT: (заглавные) → True"))
res.append(ok(OD._result_has_fact("fact: read-only") is True,
              "fact: (строчные) → True"))
res.append(ok(OD._result_has_fact("FACT : PID=12345") is True,
              "FACT : (пробел перед двоеточием) → True"))
res.append(ok(OD._result_has_fact("Fact: read back: первые 200 символов") is True,
              "Fact: (смешанный регистр) → True"))
res.append(ok(OD._result_has_fact("гейт зелёный, push выполнен, коммит abc1234") is False,
              "нет FACT: → False"))
res.append(ok(OD._result_has_fact("") is False, "пустая строка → False"))
res.append(ok(OD._result_has_fact(None) is False, "None → False, не падает"))
# «FACTUAL» не должно срабатывать (word boundary \b перед FACT)
res.append(ok(OD._result_has_fact("FACTUAL analysis completed") is False,
              "FACTUAL (не FACT:) → False"))
res.append(ok(OD._result_has_fact("PREFACT: some note") is False,
              "PREFACT: (нет \\b перед FACT) → False"))

# (1)-(5) Пресамбулы содержат «FACT:»
print("(1)-(5) Пресамбулы содержат «FACT:»:")
res.append(ok("FACT:" in OD.APPROVAL_PREAMBLE,
              "(1) APPROVAL_PREAMBLE (v3) содержит FACT:"))
res.append(ok("FACT:" in OD.PLANNER_PREAMBLE,
              "(2) PLANNER_PREAMBLE (декомпозер) содержит FACT:"))
res.append(ok("FACT:" in OD.CURATOR_PREAMBLE,
              "(3) CURATOR_PREAMBLE (куратор) содержит FACT:"))
res.append(ok("FACT:" in OD.THINKER_PREAMBLE,
              "(4) THINKER_PREAMBLE (selfheal шаг) содержит FACT:"))
res.append(ok("FACT:" in OD.TASK_THINKER_PREAMBLE,
              "(5) TASK_THINKER_PREAMBLE (selfheal одиночка) содержит FACT:"))

# (6) dev done С FACT: → нет пометки, куратор вызван БЕЗ force_consult (обычно)
print("(6) dev done С FACT: → нет ⚠️, куратор обычно:")
fb, tid = setup(("done", "Сводка фикса.\nFACT: commit abc1234 в git log origin/main"))
OD.process_new()
r = fb.rows[tid]
res.append(ok("⚠️ unverified" not in r["result"],
              "result без ⚠️ (FACT: присутствует)"))
res.append(ok(r["status"] == "done", "статус done"))
res.append(ok(len(consults) == 1, "куратор вызван"))
# curator получил original result (без ⚠️-преамбулы)
res.append(ok("⚠️ unverified" not in consults[0][1],
              "куратор видит result без ⚠️ (FACT: был, нет пометки)"))

# (7) dev done БЕЗ FACT: → result НЕ мутируется (байт-в-байт) и куратор НЕ форсируется (мягкое
# 229, 20.07.2026). Видимость ⚠️ unverified даёт devbot в тексте карточки 328 — см.
# tests/test_devbot_fact_card.py (helper _unverified_card_prefix).
print("(7) dev done БЕЗ FACT: → result цел (байт-в-байт), без форса куратора:")
os.environ["CURATOR_SCOPE"] = "1"  # scope-фильтр включён
_orig7 = "Сводка: проверил тесты, всё зелено, хвостов нет"   # read-only, без commit-ключа
fb, tid = setup(("done", _orig7), text="тз: добавь тест")
OD.process_new()
r = fb.rows[tid]
res.append(ok(r["result"] == _orig7,
              "result БАЙТ-В-БАЙТ (нет ⚠️-мутации — инвариант финал-байт-в-байт сохранён)"))
res.append(ok(r["status"] == "done", "статус остался done"))
res.append(ok(len(consults) == 0,
              "куратор НЕ форсируется: scope=1 + нет commit → пропуск (мягкое 229)"))
os.environ["CURATOR_SCOPE"] = "0"

# (8) Filipp-328 (не dev) done БЕЗ FACT: → нет пометки (только dev помечается)
print("(8) Filipp-328 (не dev) без FACT: → нет ⚠️:")
fb, tid = setup(("done", "Проверил DNS, всё ОК, хвостов нет"),
                frm="Filipp-328", text="задача: проверь DNS")
OD.process_new()
r = fb.rows[tid]
res.append(ok("⚠️ unverified" not in r["result"],
              "Filipp-328 без FACT: → нет пометки ⚠️"))
res.append(ok(r["status"] == "done", "статус done"))

# (9) force_consult=True обходит CURATOR_SCOPE=1 (done без commit в result)
print("(9) force_consult обходит CURATOR_SCOPE:")
os.environ["CURATOR_SCOPE"] = "1"
consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328-dev", 999, "тз: что-то",
                          "⚠️ unverified (нет блока FACT:)\nрезультат без коммита",
                          status="done", force_consult=True)
res.append(ok(len(consults) == 1,
              "force_consult=True: куратор вызван несмотря на CURATOR_SCOPE=1"))

consults.clear(); OD._curated.clear()
OD._maybe_curator_single("Filipp-328-dev", 998, "тз: что-то",
                          "результат без коммита и без FACT:",
                          status="done", force_consult=False)
res.append(ok(consults == [],
              "force_consult=False + CURATOR_SCOPE=1: куратор НЕ вызван (scope-фильтр)"))
os.environ["CURATOR_SCOPE"] = "0"

# cleanup
OD.bc = _real_bc
OD.run_task = _real_run_task
OD._restart_pending = _real_rp
OD._curator_consult = _real_consult
OD._curated.clear()

print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
