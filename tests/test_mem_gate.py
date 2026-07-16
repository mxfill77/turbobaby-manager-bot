"""Гейт памяти (OOM-инцидент 16.07.2026): MemAvailable < MEM_MIN_MB → задача ждёт в new.
Юнит-тесты мокают _mem_available_mb через monkey-patch на OD.
Все тесты изолированы от боевого .env — флаги выставляются принудительно ДО импорта OD."""
import os, sys, time
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "0"
os.environ["STEP_SELFHEAL"] = "0"
os.environ["GATE_SINGLE_SELECTIVE"] = "0"
os.environ["MEM_MIN_MB"] = "700"
os.environ["MEM_RETRY_SEC"] = "120"
os.environ["PRETOOL_NOPUSH"] = "1"

def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c

res = []

import orchestrator_daemon as OD


class FakeBridge:
    """Минимальная очередь в памяти для process_new."""
    def __init__(s):
        s.rows, s.nid, s.claimed = {}, 100, []

    def enqueue_task(s, frm, txt):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt,
                         "status": "new", "result": "", "updated": "x"}
        return {"ok": True, "id": s.nid}

    def get_pending(s, status="new"):
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] == status]
        return {"ok": True, "items": items}

    def claim_task(s, tid):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        if r["status"] != "new":
            return {"ok": False, "error": "already_claimed"}
        r["status"] = "in_progress"
        s.claimed.append(int(tid))
        return {"ok": True, "task": dict(r)}

    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if r:
            r["status"] = status
            r["result"] = result
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        return {"ok": True}

    def task_heartbeat(s, tid):
        return {"ok": True}

    def get_in_progress(s, lane="vps"):
        return {"ok": True, "items": []}

    def issue_write_ticket(s):
        return {"ok": True, "ticket": "t-test"}

    def consume_write_ticket(s, tk):
        return {"ok": True}

    def log_write(s, **kw):
        return {"ok": True}


def _fake_run_done(args, **kw):
    """Имитирует успешный claude -p exit=0 с минимальным JSON-выводом."""
    return type("P", (), {
        "stdout": '{"type":"result","result":"сводка done","subtype":"success"}',
        "stderr": "", "returncode": 0
    })()


def fresh(mem_mb=900):
    """Сбросить состояние модуля, вернуть FakeBridge с нужным уровнем памяти."""
    fb = FakeBridge()
    OD.bc = fb
    OD._mem_wait_until = 0.0       # сброс cooldown
    OD._mem_deny_count = 0         # сброс счётчика отказов
    OD.MEM_MIN_MB = 700            # стандартный порог
    OD.MEM_DENY_ALERT = 3          # стандартный порог алерта
    OD._mem_available_mb = lambda: mem_mb
    return fb


# T1: память выше порога → задача берётся
def t1():
    fb = fresh(mem_mb=900)          # 900 >= 700
    fb.enqueue_task("Filipp-328", "задача: тест 1")
    _old = OD.subprocess.run
    OD.subprocess.run = _fake_run_done
    try:
        OD.process_new()
    finally:
        OD.subprocess.run = _old
    res.append(ok(len(fb.claimed) == 1, "T1: память ОК → задача взята"))


# T2: память ниже порога → задача НЕ берётся, остаётся в new
def t2():
    fb = fresh(mem_mb=500)          # 500 < 700
    fb.enqueue_task("Filipp-328", "задача: тест 2")
    OD.process_new()
    res.append(ok(len(fb.claimed) == 0, "T2: память LOW → claim не было"))
    res.append(ok(list(fb.rows.values())[0]["status"] == "new",
                  "T2: задача осталась в статусе new"))


# T3: cooldown блокирует следующий цикл даже при высокой памяти
def t3():
    fb = fresh(mem_mb=400)          # low → выставит cooldown
    fb.enqueue_task("Filipp-328", "задача: тест 3")
    OD.process_new()                # ← cooldown взводится здесь
    assert len(fb.claimed) == 0
    # память «восстановилась», но cooldown ещё не истёк
    OD._mem_available_mb = lambda: 1200
    OD.process_new()
    res.append(ok(len(fb.claimed) == 0,
                  "T3: cooldown держит блок даже при высокой памяти"))


# T4: fail-safe — _mem_available_mb возвращает None → гейт пропускается, задача берётся
def t4():
    fb = fresh()
    fb.enqueue_task("Filipp-328", "задача: тест 4")
    OD._mem_available_mb = lambda: None   # /proc/meminfo «нечитаем»
    _old = OD.subprocess.run
    OD.subprocess.run = _fake_run_done
    try:
        OD.process_new()
    finally:
        OD.subprocess.run = _old
    res.append(ok(len(fb.claimed) == 1,
                  "T4: fail-safe (None) → гейт пропущен, задача взята"))


# T5: MEM_MIN_MB=0 полностью выключает гейт (даже при 50МБ)
def t5():
    fb = fresh(mem_mb=50)
    fb.enqueue_task("Filipp-328", "задача: тест 5")
    OD.MEM_MIN_MB = 0               # gate off
    _old = OD.subprocess.run
    OD.subprocess.run = _fake_run_done
    try:
        OD.process_new()
    finally:
        OD.subprocess.run = _old
    res.append(ok(len(fb.claimed) == 1,
                  "T5: MEM_MIN_MB=0 → гейт выключен, задача берётся"))


# T6: cooldown истекает → следующий вызов (при высокой памяти) берёт задачу
def t6():
    fb = fresh(mem_mb=400)          # low → cooldown
    fb.enqueue_task("Filipp-328", "задача: тест 6")
    OD.process_new()
    assert len(fb.claimed) == 0
    # симулируем истечение cooldown
    OD._mem_wait_until = time.monotonic() - 1.0
    OD._mem_available_mb = lambda: 900    # теперь ОК
    _old = OD.subprocess.run
    OD.subprocess.run = _fake_run_done
    try:
        OD.process_new()
    finally:
        OD.subprocess.run = _old
    res.append(ok(len(fb.claimed) == 1,
                  "T6: cooldown истёк + память ОК → задача взята"))


# T7: _mem_gate_check сам по себе (прямой юнит-тест функции)
def t7():
    OD._mem_wait_until = 0.0
    OD.MEM_MIN_MB = 700
    OD._mem_available_mb = lambda: 1000
    res.append(ok(not OD._mem_gate_check(), "T7a: 1000МБ >= 700 → gate=False"))
    OD._mem_wait_until = 0.0
    OD._mem_available_mb = lambda: 300
    res.append(ok(OD._mem_gate_check(), "T7b: 300МБ < 700 → gate=True"))
    # cooldown теперь взведён; сбросим для следующих тестов
    OD._mem_wait_until = 0.0


# T8: 3 последовательных «настоящих» отказа → synthetic-карточка в 328 (enqueue→claim→done)
def t8():
    fb = fresh(mem_mb=300)        # ниже порога
    # первые два отказа — карточки ещё нет
    for _ in range(2):
        OD._mem_wait_until = 0.0  # сброс cooldown, чтобы каждый проход был «настоящим» чеком
        OD._mem_gate_check()
    done_before = [r for r in fb.rows.values() if r["status"] == "done"]
    res.append(ok(len(done_before) == 0, "T8a: 2 отказа — карточки ещё нет"))
    # третий отказ → карточка
    OD._mem_wait_until = 0.0
    OD._mem_gate_check()
    done_after = [r for r in fb.rows.values() if r["status"] == "done"]
    res.append(ok(len(done_after) == 1, "T8b: 3-й отказ → synthetic done в 328"))
    card_result = done_after[0].get("result", "") if done_after else ""
    res.append(ok("памят" in card_result.lower() or "oom" in card_result.lower(),
                  "T8c: текст карточки упоминает память/OOM"))
    # счётчик сброшен после алерта → следующий отказ начинает отсчёт заново
    res.append(ok(OD._mem_deny_count == 0, "T8d: счётчик сброшен после алерта"))


# T9: успех сбрасывает счётчик — цикл не нарастает через recovery
def t9():
    fb = fresh(mem_mb=300)
    # два отказа
    for _ in range(2):
        OD._mem_wait_until = 0.0
        OD._mem_gate_check()
    # память восстановилась
    OD._mem_wait_until = 0.0
    OD._mem_available_mb = lambda: 1200
    OD._mem_gate_check()
    res.append(ok(OD._mem_deny_count == 0, "T9a: успех после 2 отказов → счётчик=0"))
    # следующий отказ — снова с нуля, карточек нет
    OD._mem_wait_until = 0.0
    OD._mem_available_mb = lambda: 300
    OD._mem_gate_check()
    done = [r for r in fb.rows.values() if r["status"] == "done"]
    res.append(ok(len(done) == 0 and OD._mem_deny_count == 1,
                  "T9b: отказ после recovery — счётчик=1, карточек нет"))


# run all
t1(); t2(); t3(); t4(); t5(); t6(); t7(); t8(); t9()

fails = sum(0 if r else 1 for r in res)
print(f"\n{'OK' if not fails else 'FAIL'} — {fails}/{len(res)} тестов провалились")
raise SystemExit(0 if not fails else 1)
