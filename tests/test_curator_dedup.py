"""Дедуп followup-проверок куратора (15.07.2026, наблюдение: цели 82/83 — wa-webhook ×2, 73 — DNS ×2).

Куратор без памяти соседних терминалов ставил одинаковые read-only проверки с интервалом в минуты.
Фикс: два слоя — (1) промпт-инъекция списка недавних done-задач; (2) программный фильтр в
_maybe_curator (_followup_dedup): если нормализованный ключ предложенной задачи совпадает с ключом
done-задачи в окне DEDUP_WINDOW → refused + note «проверка уже выполнена задачей N».
Deploy-контекст (терминал — изменение/деплой/рестарт) → дедуп пропускается (проверки свежие нужны).
Все фолбэки fail-safe: задачи проходят без фильтра при ошибке или _VF_DISABLED.

Проверки:
(1) _is_deploy_context: deploy/restart/коммит → True; обычная задача → False
(2) _followup_dedup: нет свежих done → (tasks, []); совпадение → refused; нет совпадения → remaining
(3) _followup_dedup: deploy-контекст → пропуск дедупа (все задачи в remaining)
(4) _maybe_curator followup→closed: все предложенные задачи в recent done → тишина (нет карточки)
(5) _maybe_curator followup→частичный дедуп: часть задач в recent done → remaining задачи ставятся,
    дедуплицированные попадают в refused карточки
(6) _maybe_curator followup→живёт: deploy-контекст → followup не блокируется несмотря на recent done
(7) Регресс: CURATOR=0 → ноль вызовов (как test_curator п.10)
(8) Fail-safe: ошибка bridge.get_pending → _followup_dedup возвращает (tasks, []) без краша
(9) Регресс бюджетов: followup с дедупом не обнуляет счётчики per_root/today
"""
import datetime
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "1"

def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c

res = []

import tempfile
import shutil

_TMP = tempfile.mkdtemp()

import orchestrator_daemon as OD

# Снимаем _VF_DISABLED и перенаправляем VF-файл на tmpdir — как в test_verified_facts.py.
# Без перенаправления тест пишет в боевой verified_facts.json → следующий запуск гейта
# видит fresh-записи → задачи refused → красные тесты.
OD.VERIFIED_FACTS_FILE = os.path.join(_TMP, "vf.json")
OD.VERIFIED_FACTS_LOCK = os.path.join(_TMP, "vf.lock")
OD._VF_DISABLED = False

_NOW = datetime.datetime.now(datetime.timezone.utc)
_NOW_ISO = _NOW.strftime("%Y-%m-%dT%H:%M:%S+00:00")
_OLD_ISO = (_NOW - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")  # за пределами окна


class FakeBridge:
    """Мок bridge: задачи в памяти, статус updated задаётся явно."""
    def __init__(s):
        s.rows, s.nid = {}, 400
        s.enq_calls = []
        s.fail_get_done = False

    def add(s, status, text, frm="Filipp-328", result="", updated=None):
        s.nid += 1
        s.rows[s.nid] = {
            "id": s.nid, "from": frm, "task_text": text, "status": status,
            "result": result or "",
            "created": _NOW_ISO,
            "updated": updated or _NOW_ISO,
        }
        return s.nid

    def get_pending(s, status="new", lane=None):
        if status == "done" and s.fail_get_done:
            return {"ok": False, "error": "request_failed"}
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True,
                "items": [dict(r) for r in s.rows.values() if r["status"] in sts]}

    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text))
        return {"ok": True, "id": s.add("new", text, frm=frm)}

    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}

    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False}
        r["status"], r["result"] = status, result
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if r: r["status"], r["result"] = "needs_approval", what
        return {"ok": True}


# ── (1) _is_deploy_context ────────────────────────────────────────────────────
print("(1) _is_deploy_context:")

res.append(ok(OD._is_deploy_context("тз: задеплоить новую версию", "задеплоил успешно"),
              "деплой в goal+result → True"))
res.append(ok(OD._is_deploy_context("тз: git push в main", "push OK"),
              "git push → True"))
res.append(ok(OD._is_deploy_context("тз: рестарт splinter", "splinter перезапущен"),
              "рестарт splinter → True"))
res.append(ok(OD._is_deploy_context("тз: clasp redeploy bridge", ""),
              "clasp redeploy → True"))
res.append(ok(not OD._is_deploy_context("тз: проверить wa-webhook статус", "wa-webhook 200 OK"),
              "read-only проверка → False"))
res.append(ok(not OD._is_deploy_context("", ""),
              "пустые строки → False (fail-safe)"))


# ── (2) _followup_dedup — основная логика ─────────────────────────────────────
print("(2) _followup_dedup базовые случаи:")

fb = FakeBridge()
old_bc = OD.bc
OD.bc = fb

# Нет свежих done → всё в remaining, refused пуст
res.append(ok(OD._followup_dedup(["проверить wa-webhook"]) == (["проверить wa-webhook"], []),
              "нет done-задач → (tasks, [])"))

# Добавляем свежую done-задачу с тем же нормализованным ключом
wa_key = OD._vf_normalize("проверить wa-webhook")
fb.add("done", "проверить wa-webhook", updated=_NOW_ISO)  # свежая
remaining, refused = OD._followup_dedup(["проверить wa-webhook"])
res.append(ok(len(remaining) == 0, "точное совпадение → remaining пуст"))
res.append(ok(len(refused) == 1 and "уже выполнена задачей" in refused[0][1],
              "refused содержит note с id задачи"))

# Старая done-задача (за пределами окна) → не в refused
fb2 = FakeBridge()
fb2.add("done", "проверить wa-webhook", updated=_OLD_ISO)  # старая
OD.bc = fb2
remaining2, refused2 = OD._followup_dedup(["проверить wa-webhook"])
res.append(ok(len(remaining2) == 1 and len(refused2) == 0,
              "done-задача за пределами окна → не дедупируется"))
OD.bc = fb


# ── (3) _followup_dedup — deploy-контекст пропускает дедуп ───────────────────
print("(3) _followup_dedup deploy-контекст:")

remaining3, refused3 = OD._followup_dedup(
    ["проверить wa-webhook"],
    goal="тз: задеплоить новую версию и проверить",
    result="задеплоил, рестарт прошёл чисто")
res.append(ok(len(remaining3) == 1 and len(refused3) == 0,
              "deploy-контекст → все задачи в remaining (дедуп пропущен)"))

remaining4, refused4 = OD._followup_dedup(
    ["проверить wa-webhook"],
    goal="тз: git push в main",
    result="push OK, 3 коммита")
res.append(ok(len(remaining4) == 1 and len(refused4) == 0,
              "git push-контекст → дедуп пропущен"))


# ── (4) _maybe_curator: все задачи дедуплицированы → closed (тишина) ──────────
print("(4) _maybe_curator followup→closed (все деdup):")

fb4 = FakeBridge()
OD.bc = fb4
OD._curated.clear()

# Добавляем задачу в recent done (нормализованный ключ совпадёт)
dns_task = "DNS-разведка turbophuket.com"
dns_key = OD._vf_normalize(dns_task)
fb4.add("done", dns_task, updated=_NOW_ISO)

# Мокируем куратор-тинкер чтобы вернул followup с задачей dns_task
import subprocess as _sp
_real_run = OD.subprocess.run
def fake_run_followup(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN and args[-1].startswith(OD.CURATOR_PREAMBLE):
        return type("P", (), {"stdout": '{"verdict":"followup","tasks":["' + dns_task + '"],"human":"","reason":"надо проверить"}', "stderr": "", "returncode": 0})()
    return type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()
OD.subprocess.run = fake_run_followup

before_enq = len(fb4.enq_calls)
OD._maybe_curator("задача", 999, "тз: сделать X", "X сделано")
enq_after = [c for c in fb4.enq_calls[before_enq:] if "куратор задача" in c[1]]
res.append(ok(len(enq_after) == 0,
              "все followup дедуплицированы → карточка куратора НЕ создаётся (closed-тишина)"))

OD.subprocess.run = _real_run


# ── (5) _maybe_curator: частичный дедуп → remaining задачи ставятся ───────────
print("(5) _maybe_curator частичный дедуп:")

fb5 = FakeBridge()
OD.bc = fb5
OD._curated.clear()

# Одна из двух предложенных задач уже в recent done
fb5.add("done", dns_task, updated=_NOW_ISO)  # dns_task в recent done
new_task = "проверить ping turbophuket.com"   # этого нет в done

def fake_run_two_tasks(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN and args[-1].startswith(OD.CURATOR_PREAMBLE):
        return type("P", (), {
            "stdout": '{"verdict":"followup","tasks":["' + dns_task + '","' + new_task + '"],"human":"","reason":"два хвоста"}',
            "stderr": "", "returncode": 0})()
    return type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()
OD.subprocess.run = fake_run_two_tasks

before5 = len(fb5.enq_calls)
OD._maybe_curator("задача", 998, "тз: сделать Y", "Y сделано")
enq5 = fb5.enq_calls[before5:]
curator_cards5 = [c for c in enq5 if "куратор задача" in c[1]]
followup5 = [c for c in enq5 if "куратор цели" in c[1]]

res.append(ok(len(curator_cards5) >= 1, "частичный дедуп → карточка куратора создана"))
res.append(ok(any(new_task in t for _, t in followup5),
              "не-дедуплицированная задача поставлена в очередь"))
res.append(ok(not any(dns_task in t for _, t in followup5),
              "дедуплицированная задача НЕ поставлена в очередь"))

# Проверяем что деdup-задача видна в refused карточки
card5_result = ""
for row in fb5.rows.values():
    if row["status"] == "done" and row.get("task_text", "").startswith("[куратор задача 998]"):
        card5_result = row.get("result", "")
        break
res.append(ok("уже выполнена" in card5_result or "отказано" in card5_result,
              "refused с дедуп-тегом виден в тексте карточки куратора"))

OD.subprocess.run = _real_run


# ── (6) _maybe_curator: deploy-контекст → followup живёт ──────────────────────
print("(6) _maybe_curator followup живёт при deploy-контексте:")

fb6 = FakeBridge()
OD.bc = fb6
OD._curated.clear()

# recent done содержит ту же задачу — но мы в deploy-контексте
fb6.add("done", dns_task, updated=_NOW_ISO)

def fake_run_deploy(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN and args[-1].startswith(OD.CURATOR_PREAMBLE):
        return type("P", (), {
            "stdout": '{"verdict":"followup","tasks":["' + dns_task + '"],"human":"","reason":"свежая проверка после деплоя"}',
            "stderr": "", "returncode": 0})()
    return type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()
OD.subprocess.run = fake_run_deploy

before6 = len(fb6.enq_calls)
OD._maybe_curator("задача", 997,
                  "тз: clasp redeploy bridge и проверить",
                  "задеплоил bridge, нужна проверка")
followup6 = [c for c in fb6.enq_calls[before6:] if "куратор цели" in c[1]]
res.append(ok(len(followup6) >= 1,
              "deploy-контекст → followup задача поставлена несмотря на recent done"))

OD.subprocess.run = _real_run


# ── (7) Регресс: CURATOR=0 → ноль вызовов ────────────────────────────────────
print("(7) CURATOR=0 регресс:")

fb7 = FakeBridge()
OD.bc = fb7
OD._curated.clear()
os.environ["CURATOR"] = "0"

spawn_calls7 = []
_orig_spawn = OD._curator_spawn
def spy_spawn(*a, **kw):
    spawn_calls7.append(a)
    return _orig_spawn(*a, **kw)
OD._curator_spawn = spy_spawn

OD._maybe_curator("задача", 1, "тз: dns", "dns готово")
res.append(ok(len(spawn_calls7) == 0, "CURATOR=0 → _curator_spawn не вызывается"))
res.append(ok(len(fb7.enq_calls) == 0, "CURATOR=0 → ноль enqueue-вызовов"))

os.environ["CURATOR"] = "1"
OD._curator_spawn = _orig_spawn


# ── (8) Fail-safe: ошибка bridge.get_pending → (tasks, []) без краша ──────────
print("(8) Fail-safe: get_pending падает:")

fb8 = FakeBridge()
fb8.fail_get_done = True
OD.bc = fb8

remaining8, refused8 = OD._followup_dedup(["проверить что-то важное"])
res.append(ok(len(remaining8) == 1 and len(refused8) == 0,
              "get_pending падает → fail-safe (tasks, []), нет краша"))


# ── (9) Регресс бюджетов: дедуп не ломает счётчики per_root/today ────────────
print("(9) Регресс бюджетов при дедупе:")

fb9 = FakeBridge()
OD.bc = fb9
OD._curated.clear()

# Добавляем 2 done-задачи: одна в recent done (будет деdup), одна уникальная
fb9.add("done", dns_task, updated=_NOW_ISO)   # деdup
unique_task = "уникальная-задача-x9-дедуп-тест"

def fake_run_budget(args, **kw):
    if args and args[0] == OD.CLAUDE_BIN and args[-1].startswith(OD.CURATOR_PREAMBLE):
        return type("P", (), {
            "stdout": '{"verdict":"followup","tasks":["' + dns_task + '","' + unique_task + '"],"human":"","reason":"два хвоста"}',
            "stderr": "", "returncode": 0})()
    return type("P", (), {"stdout": "ok", "stderr": "", "returncode": 0})()
OD.subprocess.run = fake_run_budget

before9 = len(fb9.enq_calls)
OD._maybe_curator("задача", 996, "тз: сделать Z", "Z сделано")
enq9 = fb9.enq_calls[before9:]
followup9 = [c for c in enq9 if "куратор цели" in c[1]]

# Только unique_task должна быть поставлена (dns_task деdup-отсеяна)
res.append(ok(len(followup9) == 1 and unique_task in followup9[0][1],
              "только уникальная задача поставлена, dns_task деdup-отсеяна"))
# Бюджет: per_root считает ПОСТАВЛЕННЫЕ задачи (у куратора через маркер [куратор цели G, шаг m])
placed_mark = [c for c in followup9 if "куратор цели 996" in c[1]]
res.append(ok(len(placed_mark) == 1,
              "маркер [куратор цели G, шаг m] стоит ровно на поставленной задаче"))

OD.subprocess.run = _real_run

# Восстановить bc
OD.bc = old_bc
OD._VF_DISABLED = OD._UNDER_TEST  # вернуть флаг

# ── Итог ─────────────────────────────────────────────────────────────────────
shutil.rmtree(_TMP, ignore_errors=True)

print(f"\nИтог: {sum(res)}/{len(res)} PASS")
fails = sum(1 for r in res if not r)
if fails:
    print(f"FAIL: {fails} тест(а/ов) не прошли")
    sys.exit(1)
