"""ДОСТАВКА ПРОВЕРЕННОГО КОММИТА В ПРОД — ОДНА КНОПКА ВМЕСТО РУЧНОГО РЕСТАРТА (14.08.2026).

ПОВОД — путь C разбора цели 538 (`reports/2026-08-14/task-538.md`), выбранный владельцем кнопкой
на сводной карточке 541. Числа разбора: за наблюдение 10.08 19:30:55 → 14.08 11:00 было 13
перезапусков, машина сделала 11, руками 2 — и ровно ручные рвали серию цепочек. Класс не в
границе (перезапуск живого процесса операционен и остаётся решением владельца), а в МОЛЧАНИИ:
О3 умел сказать «коммит не доставлен» только в журнал наблюдения, то есть в канал, на который
не отвечают.

ЧТО ЗАКРЕПЛЕНО:
  вердикт О3 «не доставлен» рождает ВОПРОС владельцу (карточка в инбокс через needs_approval),
  «да» ставит задачу «гейт → перезапуск → проверка старта», «нет» не делает НИЧЕГО;
  ни одна ветка не перезапускает ничего сама — ни решение (инструментов нет физически), ни руки
  демона (они умеют ровно enqueue + claim + set_needs_approval).

Проверки:
 (1) чистое решение: импорт ровно один, руки отсутствуют, замки на месте;
 (2) карточка рождается ТОЛЬКО на «не доставлен»: «неизвестно», «доставлен», «вне доставки» — нет;
 (3) чужой юнит / пустой список файлов / отложенное объявление → предложения нет ВОВСЕ;
 (4) тело карточки называет ОБА исхода и правильную форму рестарта (демон — только отложенно);
 (5) живой путь рук: строка очереди с маркером и юнитами → needs_approval, метка from наша;
 (6) дедуп: тот же коммит второй раз не спрашивается (диск + открытая карточка в очереди);
 (7) потолок вопросов в сутки;
 (8) ОТКАТ DELIVER_CARD=0 — ни одного обращения к фактам и к мосту;
 (9) ✅ → задача-доставщик: гейт СТОИТ ДО рестарта, рестарт демона отложенный, карточка done;
 (10) ВТОРОЕ ОКНО: прибор доказал доставку, пока карточка висела → задачи НЕТ (🔍), не done молча;
 (11) строка карточки не разобрана → FAILED (перезапускать наугад не станем, «да» видно);
 (12) ГРАНИЦЫ: страж DELIVER_CARD_PURE, гард не тронут, операций в ветке нет.
"""
import datetime
import os
import shutil
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"    # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CURATOR_STATE"] = "1"
os.environ["DELIVER_CARD"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"
STATE_DIR = "/tmp/cc_deliver_test_state"
os.environ["CC_DELIVER_DIR"] = STATE_DIR

REPO = "/root/turbobaby-manager-bot"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

import deliver_card                     # noqa: E402
import expectations                     # noqa: E402
import scan_result                      # noqa: E402
import orchestrator_daemon as OD        # noqa: E402

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()
SHA = "abc1234"


def reset_state():
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    OD._deliver_next = 0.0


class Facts:
    """Факты доставки ТОЙ ЖЕ ФОРМЫ, что собирает рука наблюдателя (образец test_curator_state).

    Замыкания и живые процессы подменяются целиком — иначе тест мерил бы состояние ЭТОЙ машины.
    Файлы коммита — настоящие файлы репозитория: свидетель по mtime обязан работать на живом
    формате, а не на выдуманном пути."""

    def __init__(s, files=("curator_event.py",), ct_shift=-5 * 3600.0, started_after=False,
                 unit="orchestrator-daemon", dirty=(), dirty_ok=True, alive=True, in_window=True,
                 sha=SHA):
        s.files, s.unit, s.sha = list(files), unit, sha
        s.dirty, s.dirty_ok, s.alive, s.in_window = list(dirty), dirty_ok, alive, in_window
        s.calls = {"commits": 0, "closure": 0, "live": 0, "dirty": 0}
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        s.ct = now + ct_shift
        mts = [os.stat(os.path.join(REPO, f)).st_mtime
               for f in s.files if os.path.exists(os.path.join(REPO, f))]
        edge = max([s.ct] + mts)
        s.started = (edge + 60.0) if started_after else (min([s.ct] + mts) - 60.0)

    def commits_since(s, ts, repo=None):
        s.calls["commits"] += 1
        if not s.in_window:
            return []
        return [{"sha": s.sha, "ct": int(s.ct), "subject": "фикстура доставки", "files": s.files}]

    def closure(s, entry, repo=None):
        s.calls["closure"] += 1
        return set([entry] + s.files) if entry == _entry_of(s.unit) else {entry}

    def live(s, unit, entry, proc=None, repo=None):
        s.calls["live"] += 1
        return None if not s.alive else {"pid": 1234, "started": s.started}

    def dirty_files(s):
        s.calls["dirty"] += 1
        if not s.dirty_ok:
            return scan_result.ScanResult.unreadable("файлов расхождения с origin/main",
                                                     detail="фикстура: git не ответил")
        return scan_result.ScanResult(scanned=len(s.dirty), parsed=len(s.dirty),
                                      subject="файлов расхождения с origin/main",
                                      payload=list(s.dirty))


def _entry_of(unit):
    for u, e in OD.prod_drift.WATCHED:
        if u == unit:
            return e
    return "orchestrator_daemon.py"


def with_facts(f, fn, *a, **kw):
    """Подмена ИМЕНЕМ, а не копией кода: рука зовёт ровно те три функции prod_drift и свой
    читающий git — их и подменяем, всё прочее в пути остаётся боевым."""
    keep = (OD.prod_drift.commits_since, OD.prod_drift.closure, OD.prod_drift.live,
            OD._curator_state_dirty)
    OD.prod_drift.commits_since = f.commits_since
    OD.prod_drift.closure = f.closure
    OD.prod_drift.live = f.live
    OD._curator_state_dirty = f.dirty_files
    try:
        return fn(*a, **kw)
    finally:
        (OD.prod_drift.commits_since, OD.prod_drift.closure, OD.prod_drift.live,
         OD._curator_state_dirty) = keep


class FakeBridge:
    """Очередь в памяти + счётчик ЛЮБОГО обращения (образец test_curator_state.FakeBridge)."""

    def __init__(s, rows=None):
        s.rows, s.nid, s.calls = dict(rows or {}), 900, []
        s.completed = []

    def get_pending(s, status="new", lane=None):
        s.calls.append("get_pending")
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(),
                                                              key=lambda x: x["id"])
                                      if r["status"] in str(status)]}

    def enqueue_task(s, from_, task_text, lane=None, **kw):
        s.calls.append("enqueue_task")
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": from_, "task_text": task_text,
                         "status": "new", "result": "", "updated": NOW_ISO}
        return {"ok": True, "id": s.nid}

    def claim_task(s, tid, lane=None):
        s.calls.append("claim_task")
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        s.calls.append("set_needs_approval")
        s.rows[int(tid)]["status"] = "needs_approval"
        s.rows[int(tid)]["result"] = what
        return {"ok": True}

    def complete_task(s, tid, status, result=""):
        s.calls.append("complete_task")
        s.completed.append((int(tid), status, str(result or "")))
        if int(tid) in s.rows:
            s.rows[int(tid)]["status"] = status
        return {"ok": True}


def ask(facts, rows=None):
    """Один прогон боевой ветки предложения → (id карточек, мост)."""
    fb, keep = FakeBridge(rows), OD.bc
    OD.bc = fb
    try:
        said = with_facts(facts, OD._maybe_deliver_ask)
    finally:
        OD.bc = keep
    return said, fb


def note_of(facts):
    """Живой вердикт О3 на этих фактах (боевой прибор, не выдуманная запись)."""
    def go():
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        return expectations.verdict({"now": now, "delivery": OD._delivery_facts(now)},
                                    expectations.config(os.environ))
    return [n for n in with_facts(facts, go) if str(n.get("kind") or "").startswith("o3")]


# ══════════════ (1) ЧИСТОЕ РЕШЕНИЕ ══════════════════════════════════════════════════════════
print("\n(1) чистое решение: инструментов нет")
src = open(os.path.join(REPO, "deliver_card.py"), encoding="utf-8").read()
imports = [l for l in src.splitlines() if l.startswith(("import ", "from "))]
res.append(ok(imports == ["import expectations"],
              "импорт ровно один (`expectations`): вокабуляр прибора взят готовым, рук нет"))
res.append(ok("subprocess" not in src and "systemctl restart" in src,
              "имя команды рестарта в модуле есть только как ТЕКСТ карточки, запускать нечем"))
res.append(ok(deliver_card.on({"DELIVER_CARD": "0"}) is False
              and deliver_card.on({}) is True,
              "флаг: «0» гасит ветку, по умолчанию вопрос жив"))
res.append(ok(deliver_card.restart_cmd("orchestrator-daemon").startswith("systemd-run"),
              "рестарт демона — ТОЛЬКО отложенной единицей (правило самомодификации)"))
res.append(ok(deliver_card.restart_cmd("splinter") == "systemctl restart splinter",
              "у splinter родства с cgroup задачи нет — обычный рестарт"))
res.append(ok(deliver_card.sha_of("[доставка коммита abc1234] доставка в прод: splinter") == "abc1234"
              and deliver_card.sha_of("[конверт одобренной заявки 5] что-то") is None,
              "маркер строки очереди читается точно, чужая строка — не наша"))

# ══════════════ (2) ТОЛЬКО «НЕ ДОСТАВЛЕН» ═══════════════════════════════════════════════════
print("\n(2) карточка рождается только на «не доставлен»")
UND = note_of(Facts())
res.append(ok(len(UND) == 1 and UND[0]["state"] == expectations.UNDELIVERED,
              "живой прибор на фикстуре даёт «не доставлен» (%s)" % (UND and UND[0]["state"])))
off = deliver_card.offer(UND[0], {"orchestrator-daemon", "splinter"})
res.append(ok(off and off["sha"] == SHA and off["units"] == ["orchestrator-daemon"],
              "предложение названо коммитом и юнитом"))

UNK = note_of(Facts(dirty_ok=False))
res.append(ok(UNK and UNK[0]["state"] == expectations.UNKNOWN
              and deliver_card.offer(UNK[0], {"orchestrator-daemon"}) is None,
              "«неизвестно» карточкой НЕ становится: незнание — не повод перезапускать прод"))
res.append(ok(note_of(Facts(started_after=True)) == [],
              "доставленный коммит вердикта не даёт вовсе"))
res.append(ok(deliver_card.offer({"kind": "o3_undelivered", "state": expectations.DELIVERED,
                                  "sha": SHA, "missing": [("a.py", "splinter")]},
                                 {"splinter"}) is None,
              "вид заметки и состояние сверяются ОБА (двойной замок)"))

# ══════════════ (3) ДЫРКИ → ПРЕДЛОЖЕНИЯ НЕТ ═════════════════════════════════════════════════
print("\n(3) чужой юнит, пустой список, отсрочка")
base = dict(UND[0])
res.append(ok(deliver_card.offer(base, {"splinter"}) is None,
              "юнит вне наблюдаемых отменяет предложение ЦЕЛИКОМ (чужой вид доставки)"))
res.append(ok(deliver_card.offer(dict(base, missing=[]), {"orchestrator-daemon"}) is None,
              "пустой список файлов → предложения нет"))
res.append(ok(deliver_card.offer(dict(base, defer=1800.0), {"orchestrator-daemon"}) is None,
              "объявление отложено прибором → вопрос тем более ждёт"))
res.append(ok(deliver_card.offer(None, {"orchestrator-daemon"}) is None
              and deliver_card.offer(dict(base, sha=""), {"orchestrator-daemon"}) is None,
              "мусор на входе → молчание (fail-safe)"))

# ══════════════ (4) ТЕЛО КАРТОЧКИ ═══════════════════════════════════════════════════════════
print("\n(4) тело карточки называет оба исхода")
body = deliver_card.render(off)
res.append(ok("✅" in body and "❌" in body, "оба исхода названы ДО нажатия"))
res.append(ok("gate.py" in body and "ТОЛЬКО при зелёном" in body,
              "сказано, что гейт стоит ПЕРЕД рестартом и красный гейт его отменяет"))
res.append(ok("systemd-run --on-active=10s systemctl restart orchestrator-daemon" in body,
              "форма рестарта демона в карточке — отложенная"))
res.append(ok("не делаю ничего" in body,
              "❌ обещает бездействие, а не «отложу на потом»"))
res.append(ok("прибор спрашивается второй раз" in body,
              "владелец предупреждён: обогнанная карточка задачи не поставит"))
res.append(ok(len(body) <= OD.RESULT_MAX, "тело помещается в потолок result"))

# ══════════════ (5) ЖИВОЙ ПУТЬ РУК ══════════════════════════════════════════════════════════
print("\n(5) живой путь: карточка встаёт в needs_approval")
reset_state()
said, fb = ask(Facts())
row = fb.rows.get(said[0]) if said else {}
res.append(ok(len(said) == 1, "ровно одна карточка за прогон"))
res.append(ok(row.get("status") == "needs_approval", "карточка доведена до needs_approval"))
res.append(ok(str(row.get("from")) == "Filipp-328" + OD.DEC_FROM_SUFFIX,
              "метка from из QUEUE_FROMS devbot — иначе карточка не доедет до инбокса"))
res.append(ok(deliver_card.sha_of(row.get("task_text")) == SHA
              and deliver_card.units_of(row.get("task_text")) == ["orchestrator-daemon"],
              "строка очереди несёт коммит и юнит (тело затрёт вердикт, строка — нет)"))
res.append(ok("complete_task" not in fb.calls,
              "ветка предложения НИЧЕГО не закрывает и не исполняет"))

# ══════════════ (6) ДЕДУП ═══════════════════════════════════════════════════════════════════
print("\n(6) один коммит — один вопрос")
OD._deliver_next = 0.0
said2, fb2 = ask(Facts())
res.append(ok(said2 == [], "тот же коммит второй раз не спрашивается (память на диске)"))
reset_state()
open_row = {901: {"id": 901, "from": "Filipp-328-dec", "status": "needs_approval",
                  "task_text": deliver_card.row_text(off), "result": "тело",
                  "updated": NOW_ISO}}
said3, fb3 = ask(Facts(), rows=open_row)
res.append(ok(said3 == [], "открытая карточка того же коммита в очереди — второй не будет"))

# ЗНАМЕНАТЕЛЬ У ОБОИХ РУБЕЖЕЙ: «никого не спрашивали» и «память не прочиталась» — разные вещи,
# иначе испорченный файл читался бы как чистая память и владелец получил бы второй вопрос.
reset_state()
os.makedirs(STATE_DIR, exist_ok=True)
open(os.path.join(STATE_DIR, "asked.json"), "w", encoding="utf-8").write("{не json")
OD._deliver_next = 0.0
said6, fb6 = ask(Facts())
res.append(ok(OD._deliver_asked().outcome == scan_result.OUTCOME_UNREADABLE and said6 == [],
              "память испорчена → вопрос НЕ задаём (дубль владельцу хуже задержки)"))
reset_state()
res.append(ok(OD._deliver_asked().outcome == scan_result.OUTCOME_EMPTY,
              "файла нет — это законный ноль первого прогона, а не сбой"))


class DeadBridge(FakeBridge):
    def get_pending(s, status="new", lane=None):
        s.calls.append("get_pending")
        return {"ok": False, "error": "request_failed"}


OD._deliver_next = 0.0
fb7, keep7 = DeadBridge(), OD.bc
OD.bc = fb7
try:
    said7 = with_facts(Facts(), OD._maybe_deliver_ask)
finally:
    OD.bc = keep7
res.append(ok(said7 == [] and "enqueue_task" not in fb7.calls,
              "очередь не прочиталась → карточку не ставим (второй рубеж тоже со знаменателем)"))

# ══════════════ (7) ПОТОЛОК СУТОК ═══════════════════════════════════════════════════════════
print("\n(7) потолок вопросов в сутки")
reset_state()
now = datetime.datetime.now(datetime.timezone.utc).timestamp()
for i in range(OD.DELIVER_DAY_CAP):
    OD._deliver_mark("dead%d" % i, now)
OD._deliver_next = 0.0
said4, fb4 = ask(Facts())
res.append(ok(said4 == [] and "enqueue_task" not in fb4.calls,
              "потолок суток достигнут → молчим, недоставку по-прежнему видно в О3"))

# ══════════════ (8) ОТКАТ ═══════════════════════════════════════════════════════════════════
print("\n(8) откат DELIVER_CARD=0")
reset_state()
os.environ["DELIVER_CARD"] = "0"
f8 = Facts()
said5, fb5 = ask(f8)
os.environ["DELIVER_CARD"] = "1"
res.append(ok(said5 == [] and fb5.calls == [],
              "ветка мертва: ни одного обращения к мосту"))
res.append(ok(f8.calls == {"commits": 0, "closure": 0, "live": 0, "dirty": 0},
              "и ни одного обращения к фактам — гашение ДО сбора (git не зовётся)"))

# ══════════════ (9) ОТВЕТ ВЛАДЕЛЬЦА ═════════════════════════════════════════════════════════
print("\n(9) ✅ → задача-доставщик")


def answer(task_text, facts, tid=800, body="тело карточки"):
    fb, keep = FakeBridge(), OD.bc
    fb.rows[tid] = {"id": tid, "from": "Filipp-328-dec", "status": "approved",
                    "task_text": task_text, "result": body, "updated": NOW_ISO}
    OD.bc = fb
    try:
        with_facts(facts, OD.process_approved)
    finally:
        OD.bc = keep
    return fb


TT = deliver_card.row_text(off)
fb9 = answer(TT, Facts())
tz = next((r["task_text"] for r in fb9.rows.values() if r["id"] != 800), "")
closed = next((c for c in fb9.completed if c[0] == 800), None)
res.append(ok(bool(tz) and tz.startswith("[конверт одобренной заявки 800]"),
              "задача встала и несёт маркер конверта ПЕРВЫМ (контур разрыва петли готов)"))
res.append(ok(tz.find("gate.py") < tz.find("systemd-run"),
              "в ТЗ гейт стоит ДО рестарта, а не после"))
res.append(ok("systemd-run --on-active=10s systemctl restart orchestrator-daemon" in tz,
              "рестарт демона в ТЗ — только отложенный"))
res.append(ok("FACT:" in tz and "is-active" in tz,
              "ТЗ требует доказать эффект живым фактом"))
res.append(ok("не коммить" in tz and "мост не выкладывай" in tz,
              "ТЗ прямо запрещает работу сверх доставки"))
res.append(ok(closed and closed[1] == "done" and str(fb9.rows[901]["id"]) in closed[2],
              "карточка закрыта done со ССЫЛКОЙ на задачу"))

# ══════════════ (10) ВТОРОЕ ОКНО ════════════════════════════════════════════════════════════
print("\n(10) второе окно: коммит доехал, пока карточка висела")
fb10 = answer(TT, Facts(started_after=True), tid=810)
closed10 = next((c for c in fb10.completed if c[0] == 810), None)
res.append(ok("enqueue_task" not in fb10.calls,
              "задача НЕ ставится: второй перезапуск владелец не просил"))
res.append(ok(closed10 and closed10[1] == "done" and "🔍" in closed10[2]
              and "ПО ФАКТУ" in closed10[2],
              "карточка закрыта знаком 🔍 и сказано, что вопрос снят по факту, а не по времени"))
fb10b = answer(TT, Facts(dirty_ok=False), tid=811)
res.append(ok("enqueue_task" in fb10b.calls,
              "прибор не смог подтвердить → «да» исполняется, как исполнялось (замок в ту же "
              "сторону, что у сводной карточки)"))

# ══════════════ (11) СТРОКА НЕ РАЗОБРАНА ════════════════════════════════════════════════════
print("\n(11) строка карточки не разобрана → failed, а не тихий done")
fb11 = answer("[доставка коммита abc1234] без юнитов", Facts(), tid=820)
c11 = next((c for c in fb11.completed if c[0] == 820), None)
res.append(ok("enqueue_task" not in fb11.calls, "перезапускать наугад не станем"))
res.append(ok(c11 and c11[1] == "failed" and "не разобрана" in c11[2],
              "«да» видно как незакрытое дело (done читался бы как успех)"))

# ══════════════ (12) ГРАНИЦЫ ════════════════════════════════════════════════════════════════
print("\n(12) границы")
import invariants_check as IC            # noqa: E402


class Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


run = Run()
IC.check_deliver_card_pure(None, run)
res.append(ok(not run.flags, "боевой deliver_card.py страж проходит (%s)" % run.flags))

bad = "/tmp/cc_deliver_hands_fixture.py"
open(bad, "w", encoding="utf-8").write(
    "import expectations\nimport subprocess\n\n\ndef go():\n"
    "    return subprocess.run(['systemctl', 'restart', 'splinter'])\n")
IC._DELIVER_CARD_PATH = bad
run2 = Run()
IC.check_deliver_card_pure(None, run2)
IC._DELIVER_CARD_PATH = None
res.append(ok(bool(run2.flags), "модуль С РУКАМИ страж краснит (%s)" % (run2.flags[:1] or "нет")))

run3 = Run()
IC._DELIVER_CARD_PATH = "/tmp/cc_deliver_missing_fixture.py"
IC.check_deliver_card_pure(None, run3)
IC._DELIVER_CARD_PATH = None
res.append(ok(bool(run3.flags), "файла нет → ФЛАГ (нечитаемое правило доверия не имеет)"))

guard_src = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("deliver_card" not in guard_src,
              "pretool_guard.py этой правкой не тронут ни одной строкой"))
od_src = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
res.append(ok(od_src.count("_convert_deliver_approved(") == 2,
              "дверь исполнения ответа ровно одна (определение + вызов)"))
res.append(ok("systemctl" not in od_src.split("def _maybe_deliver_ask")[1].split("def ")[0],
              "в ветке предложения нет ни одной команды перезапуска"))

os.remove(bad)
shutil.rmtree(STATE_DIR, ignore_errors=True)

print("\n%d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
