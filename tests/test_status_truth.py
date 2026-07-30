"""ПРАВДА СТАТУСА на серверной полосе — зеркало ПК-фикса 5f2be1c/1597cbe (30.07.2026).

Класс: задача успела закоммитить/записать журнал, упёрлась в таймаут и получила голое
«провалена»; по такому статусу планировали следующий шаг и дважды ошиблись.

Проверяем:
(а) коды причин — РОВНО те же пять, что на ПК, и разбор exec-провала по сырым out/err;
(б) формулировка — «В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА» + оговорка про авторство; слов «работа
    выполнена» в тексте НЕТ (живая проверка ПК: в окно попадают чужие коммиты);
(в) улик нет → честное «следов не найдено», без намёка на сделанное;
(г) ведущий маркер ⏱/✋ остаётся ПЕРВЫМ символом (гейт самопочинки и пропуск куратора целы),
    а где маркера не было — он НЕ появляется;
(д) реестр удачных записей журнала: пишется только после ok, окно фильтрует, битое — мимо;
(е) окно задачи: явный старт → отметка взятия на диске → created;
(ж) коммиты берутся с НАЧАЛА окна (--reverse) — иначе свой коммит выпадает из показанной пятёрки;
(з) fail-safe: git недоступен / реестр битый / сборка упала → прежний голый текст;
(и) точки демона: сирота, сгоревший approve, hard-cap подтверждения, провал исполнения —
    каждая несёт код, и ни одна не теряет прежний диагноз;
(к) cclog: реестр пополняется ТОЛЬКО при успешной записи, под тестом боевой файл не трогается.
Сети/Telegram/claude НЕТ."""
import datetime
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")
os.environ["CURATOR"] = "0"          # изоляция от боевого .env (принудительно, не setdefault)
os.environ["STEP_SELFHEAL"] = "0"    # думатель в этих сценариях не участвует


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []
import status_truth as ST
import orchestrator_daemon as OD

UTC = datetime.timezone.utc
T0 = datetime.datetime(2026, 7, 30, 12, 41, tzinfo=UTC)
T1 = datetime.datetime(2026, 7, 30, 14, 23, tzinfo=UTC)
TMP = tempfile.mkdtemp(prefix="status_truth_")

# ---------------------------------------------------------------- (а) коды причин
print("(а) коды причин — те же, что на ПК:")
res.append(ok(sorted(ST.FAIL_CODES) == sorted([
    "approval_timeout", "heartbeat_timeout", "run_timeout", "model_refusal", "exec_error"]),
    "ровно пять кодов ПК, ни одного своего (%s)" % ",".join(sorted(ST.FAIL_CODES))))
res.append(ok(ST.tag("heartbeat_timeout") == "[причина=heartbeat_timeout · таймаут сердцебиения]",
              "тег причины в формате ПК"))
res.append(ok(ST.code_of("⏱ … [причина=run_timeout · таймаут исполнения]: …") == "run_timeout",
              "код вычитывается из готового текста (FAIL_CODE_RE)"))
res.append(ok(ST.code_of("просто провал без тега") is None, "тега нет → кода нет (не выдумываем)"))
res.append(ok(ST.classify_exec("", "API Error: 529 Overloaded", 1) == "model_refusal",
              "перегрузка API → model_refusal"))
res.append(ok(ST.classify_exec("Failed to authenticate: OAuth session expired", "", 1)
              == "model_refusal", "протухшая сессия модели → model_refusal"))
res.append(ok(ST.classify_exec("", "Traceback: ValueError", 2) == "exec_error",
              "непонятная ошибка → exec_error (в общий код, не в тишину)"))
res.append(ok(ST.classify_exec("", "", 143) == "exec_error", "убит извне → exec_error"))
res.append(ok(ST.log_line(61, "heartbeat_timeout") == "FAIL причина=heartbeat_timeout id=61",
              "строка для лога демона грепается"))

# ---------------------------------------------------------------- (б)(в)(г) формулировка
print("(б) формулировка: окно — не авторство:")
COMMITS = [("a3f75dd", "гард: чтение окружения живого процесса (PEB) зелёное, файл секретов красный"),
           ("fa54ce7", "гард: чтение базы ≠ запись")]
WRITES = ["DONE 2026-07-30 14:13 UTC (local): ARTIFACT статус-не-врёт → docs/artifacts/…"]
txt = ST.fail_result("⏱ ПК-таймаут одиночки: задача провисела без движения.", "heartbeat_timeout",
                     start=T0, end=T1, commits=COMMITS, writes=WRITES)
res.append(ok("В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА" in txt, "заголовок «в окне задачи есть работа»"))
res.append(ok("работа выполнена" not in txt.lower() and "РАБОТА ВЫПОЛНЕНА" not in txt,
              "слов «работа выполнена» НЕТ (опровергнуто живой проверкой ПК)"))
res.append(ok("Окно, а не авторство" in txt, "оговорка про авторство на месте"))
res.append(ok("a3f75dd" in txt and "коммитов 2" in txt, "коммиты названы поимённо и посчитаны"))
res.append(ok("записей журнала 1" in txt, "записи журнала посчитаны"))
res.append(ok("закрой руками" in txt and "НЕ переделывай вслепую" in txt,
              "вывод — сверить и закрыть руками, а не «готово»"))
res.append(ok("[причина=heartbeat_timeout · таймаут сердцебиения]" in txt, "код причины в тексте"))
res.append(ok("ПК-таймаут одиночки: задача провисела без движения." in txt,
              "прежний честный диагноз сохранён дословно"))

print("(в) улик нет → честное «следов не найдено»:")
empty = ST.fail_result("⏱ таймаут задачи 600s — claude -p убит.", "run_timeout",
                       start=T0, end=T1, commits=[], writes=[])
res.append(ok("СЛЕДОВ РАБОТЫ" in empty and "коммитов 0, записей журнала 0" in empty,
              "прямо сказано, что следов нет"))
res.append(ok("ЕСТЬ РАБОТА" not in empty, "без намёка на сделанную работу"))
res.append(ok("[причина=run_timeout" in empty, "код причины есть и здесь"))

print("(г) ведущий маркер:")
res.append(ok(txt.startswith("⏱ "), "⏱ остался ПЕРВЫМ символом (гейт самопочинки цел)"))
res.append(ok(empty.startswith("⏱ "), "⏱ первым и в ветке «следов нет»"))
plain = ST.fail_result("approve истёк (>30 мин), повтори задачу", "approval_timeout",
                       start=T0, end=T1, commits=COMMITS, writes=[])
res.append(ok(not plain.lstrip().startswith("⏱") and "⏱" not in plain,
              "где маркера не было — он НЕ появился (пропуск куратора не сдвинут)"))
res.append(ok(plain.startswith("НЕ ЗАКРЫТА"), "без маркера заголовок идёт первым"))
hand = ST.fail_result("✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ", "exec_error", start=T0, end=T1,
                      commits=[], writes=[])
res.append(ok(hand.startswith("✋ "), "✋ тоже сохраняется первым символом"))

# ---------------------------------------------------------------- (д) реестр записей журнала
print("(д) реестр удачных записей журнала:")
led = os.path.join(TMP, "ledger.jsonl")
res.append(ok(ST.ledger_append("DONE", "DONE 2026-07-30 13:00 UTC (local): раз", label="local",
                               path=led, now=datetime.datetime(2026, 7, 30, 13, 0, tzinfo=UTC)),
              "запись в реестр удалась"))
ST.ledger_append("PLAN", "PLAN 2026-07-30 15:00 UTC (local): вне окна", label="local", path=led,
                 now=datetime.datetime(2026, 7, 30, 15, 0, tzinfo=UTC))
with open(led, "a", encoding="utf-8") as f:
    f.write("{битая строка\n\n")
got = ST.ledger_entries(T0, T1, path=led)
res.append(ok(len(got) == 1 and "раз" in got[0], "в окно попала одна запись, битая строка мимо"))
res.append(ok(ST.ledger_entries(T0, T1, path=os.path.join(TMP, "нет.jsonl")) == [],
              "нет файла реестра → пустой список, без падения"))
rec = json.loads(open(led, encoding="utf-8").readline())
res.append(ok(rec.get("kind") == "DONE" and rec.get("label") == "local" and rec.get("head"),
              "в реестре тип, канал и голова записи"))
res.append(ok(ST.ledger_append("DONE", "x", path=os.path.join(TMP, "нет", "дир", "f.jsonl"))
              is False, "сбой записи реестра проглочен (журнал важнее следа)"))

# ---------------------------------------------------------------- (е) окно задачи
print("(е) окно задачи: явный старт → отметка взятия → created:")
claims = os.path.join(TMP, "claims.jsonl")
with open(claims, "w", encoding="utf-8") as f:
    f.write(json.dumps({"id": 61, "updated": "2026-07-30T12:41:00.000Z"}) + "\n")
    f.write(json.dumps({"id": 62, "updated": "2026-07-30T13:00:00.000Z"}) + "\n")
res.append(ok(ST.claim_started(61, path=claims) == T0, "момент взятия читается по id"))
res.append(ok(ST.claim_started(999, path=claims) is None, "чужого id в журнале нет → None"))
s, e = ST.task_window({"id": 61, "created": "2026-07-30T10:00:00Z"}, claim_path=claims, now=T1)
res.append(ok(s == T0, "отметка взятия бьёт created (задачу закрывает уже другой процесс)"))
s2, _ = ST.task_window({"id": 999, "created": "2026-07-30T10:00:00Z"}, claim_path=claims, now=T1)
res.append(ok(s2 == datetime.datetime(2026, 7, 30, 10, 0, tzinfo=UTC),
              "отметки нет → откат на created"))
s3, _ = ST.task_window({"id": 61, "created": "2026-07-30T10:00:00Z"},
                       started="2026-07-30T11:11:00Z", claim_path=claims, now=T1)
res.append(ok(s3 == datetime.datetime(2026, 7, 30, 11, 11, tzinfo=UTC),
              "явный старт (демон знает точно) бьёт всё"))
res.append(ok(ST.parse_iso("мусор") is None and ST.parse_iso("") is None,
              "битое время → None, окна нет — но и вранья нет"))

# ---------------------------------------------------------------- (ж) коммиты с начала окна
print("(ж) коммиты берутся с НАЧАЛА окна:")
seen = {}


def fake_git(args, **kw):
    seen["args"] = args

    class R:
        returncode = 0
        stdout = "a3f75dd\x1fпервый\nfa54ce7\x1fвторой\n"
    return R()


got_c = ST.commits_in_window(T0, T1, repo=TMP, runner=fake_git)
res.append(ok(got_c == [("a3f75dd", "первый"), ("fa54ce7", "второй")], "коммиты разобраны"))
res.append(ok("--reverse" in seen["args"], "--reverse: свой коммит не выпадает из показанных"))
res.append(ok(any(x.startswith("--since=") for x in seen["args"])
              and any(x.startswith("--until=") for x in seen["args"]), "границы окна переданы"))

# ---------------------------------------------------------------- (з) fail-safe
print("(з) fail-safe:")


def broken_git(args, **kw):
    raise OSError("git не найден")


res.append(ok(ST.commits_in_window(T0, T1, repo=TMP, runner=broken_git) == [],
              "git недоступен → улик нет, без падения"))


class RcFail:
    returncode = 128
    stdout = ""


res.append(ok(ST.commits_in_window(T0, T1, repo=TMP, runner=lambda *a, **k: RcFail()) == [],
              "не репозиторий → пусто"))
_real_fr = ST.fail_result
ST.fail_result = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сломалось"))
safe = OD._truthful_fail(7, "⏱ прежний честный диагноз", "run_timeout")
ST.fail_result = _real_fr
res.append(ok(safe == "⏱ прежний честный диагноз",
              "сборка упала → прежний голый текст байт-в-байт"))

# ---------------------------------------------------------------- (и) точки демона
print("(и) точки демона несут код и не теряют диагноз:")


def iso_ago(sec):
    return (datetime.datetime.now(UTC) - datetime.timedelta(seconds=sec)).isoformat()


class FakeBridge:
    def __init__(s):
        s.rows, s.nid = {}, 200
        s.done = []

    def add(s, status, text, lane=None, age=0, frm="Filipp-328-dev", result=""):
        s.nid += 1
        r = {"id": s.nid, "from": frm, "task_text": text, "status": status, "result": result,
             "updated": iso_ago(age), "created": iso_ago(age + 600)}
        if lane is not None:
            r["lane"] = lane
        s.rows[s.nid] = r
        return s.nid

    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                                      if r["status"] in sts]}

    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        s.done.append((int(tid), status, result))
        return {"ok": True}

    def enqueue_task(s, frm, txt):
        return {"ok": True, "id": s.add("new", txt, frm=frm)}

    def task_heartbeat(s, tid):
        return {"ok": True}

    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        r["status"] = "in_progress"
        return {"ok": True}

    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}


_real_bc = OD.bc
_real_commits, _real_ledger = ST.commits_in_window, ST.ledger_entries
ST.commits_in_window = lambda *a, **k: [("deadbee", "правка в окне")]
ST.ledger_entries = lambda *a, **k: ["DONE 2026-07-30 14:13 UTC (local): строка журнала"]

fb = FakeBridge()
OD.bc = fb
oid = fb.add("in_progress", "ТЗ сироты", age=OD.ORPHAN_TTL + 60)
OD.process_orphans()
orph = fb.rows[oid]["result"]
res.append(ok(orph.startswith("⏱ "), "сирота: ⏱ первым символом"))
res.append(ok("[причина=heartbeat_timeout" in orph, "сирота: код heartbeat_timeout"))
res.append(ok("задача-сирота" in orph and "heartbeat мёртв" in orph, "сирота: прежний диагноз цел"))
res.append(ok("deadbee" in orph and "Окно, а не авторство" in orph, "сирота: следы + оговорка"))

fb2 = FakeBridge()
OD.bc = fb2
aid = fb2.add("approved", "ТЗ одобренное", age=OD.APPROVED_TTL + 60, result="op=other | что-то")
_real_covered = OD._poll_covered      # учёт опросов моста — свой класс со своими тестами (25.07)
OD._poll_covered = lambda w: True
OD.process_approved()
OD._poll_covered = _real_covered
appr = fb2.rows[aid]["result"]
res.append(ok("[причина=approval_timeout" in appr, "сгоревший approve: код approval_timeout"))
res.append(ok("approve истёк (>30 мин)" in appr, "сгоревший approve: прежний диагноз цел"))
res.append(ok("⏱" not in appr, "сгоревший approve: ⏱ не появился (пропуск куратора не сдвинут)"))

fb3 = FakeBridge()
OD.bc = fb3
nid = fb3.add("needs_approval", "ТЗ ждёт да", age=OD.NA_LIFETIME + 60)
OD.process_na_reminders()
na = fb3.rows[nid]["result"]
res.append(ok("[причина=approval_timeout" in na, "hard-cap 24ч: код approval_timeout"))
res.append(ok("подтверждение не получено за 24ч" in na, "hard-cap 24ч: прежний диагноз цел"))

# провал исполнения: код кладёт участок, который видел out/err (не разбор готовой карточки)
fb4 = FakeBridge()
OD.bc = fb4
tid4 = fb4.add("new", "обычное ТЗ")
_real_run_impl = OD._run_task_impl


def fake_impl(task_id, task_text, task_timeout, preamble=None, _mctx=None):
    # мокаем ИМПЛ, а не run_task: канал кода причины (_LAST_RUN) заполняет именно обёртка —
    # проверяем живой путь целиком, а не свою же подмену
    OD._set_fail_code(_mctx, ST.classify_exec("", "API Error: 529 Overloaded", 1))
    return "failed", "claude -p упал (exit=1): API Error: 529 Overloaded"


OD._run_task_impl = fake_impl
OD.process_new()
OD._run_task_impl = _real_run_impl
exe = fb4.rows[tid4]["result"]
res.append(ok("[причина=model_refusal" in exe, "провал исполнения: код model_refusal из out/err"))
res.append(ok("claude -p упал (exit=1)" in exe, "провал исполнения: прежняя карточка цела"))
res.append(ok("В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА" in exe, "провал исполнения: следы названы"))

# без кода (guard-блок ✋ / ручная карта) обрамления НЕТ — такой статус и так честен
fb5 = FakeBridge()
OD.bc = fb5
tid5 = fb5.add("new", "ТЗ с жёстким блоком")


def fake_impl_noc(task_id, task_text, task_timeout, preamble=None, _mctx=None):
    return "failed", "✋ ЖЁСТКИЙ БЛОК: запись в живые таблицы"


OD._run_task_impl = fake_impl_noc
OD.process_new()
OD._run_task_impl = _real_run_impl
res.append(ok(fb5.rows[tid5]["result"] == "✋ ЖЁСТКИЙ БЛОК: запись в живые таблицы",
              "провал без кода причины не обрамляется (ручная карта честна и так)"))

# мок ЦЕЛИКОМ подменённого run_task (так делают шесть соседних сьютов) — канал не заполнен →
# обрамления нет, поведение под моком байт-в-байт прежнее: расширение сигнатуры их бы сломало
fb6 = FakeBridge()
OD.bc = fb6
tid6 = fb6.add("new", "ТЗ под мокнутым run_task")
_real_run_task = OD.run_task
OD.run_task = lambda tid, txt, task_timeout=None: ("failed", "мок: провал")
OD.process_new()
OD.run_task = _real_run_task
res.append(ok(fb6.rows[tid6]["result"] == "мок: провал",
              "run_task мокнут лямбдой прежней формы → работает как раньше"))

# терминал САМОГО думателя (halt) — живой случай задачи 59: коммит и запись журнала были,
# а статус говорил только «упала»
print("(и-2) терминал думателя самопочинки:")
fb7 = FakeBridge()
OD.bc = fb7
tid7 = fb7.add("new", "ТЗ, которое думатель признает безнадёжным")
os.environ["STEP_SELFHEAL"] = "1"
_real_consult = OD._task_selfheal_consult
OD._task_selfheal_consult = lambda text, fail: {"verdict": "halt", "fixed_task": "",
                                                "reason": "exit=143 — процесс убит извне"}


def fake_impl_exec(task_id, task_text, task_timeout, preamble=None, _mctx=None):
    OD._set_fail_code(_mctx, ST.classify_exec("", "boom", 143))
    return "failed", "claude -p упал (exit=143): exit=143"


OD._run_task_impl = fake_impl_exec
OD.process_new()
OD._run_task_impl = _real_run_impl
OD._task_selfheal_consult = _real_consult
os.environ["STEP_SELFHEAL"] = "0"
halt = fb7.rows[tid7]["result"]
res.append(ok("думатель: halt" in halt, "halt-диагноз думателя сохранён"))
res.append(ok("[причина=exec_error" in halt, "halt думателя тоже несёт код причины"))
res.append(ok("В ОКНЕ ЗАДАЧИ ЕСТЬ РАБОТА" in halt and "deadbee" in halt,
              "halt думателя называет следы работы (живой случай задачи 59)"))

ST.commits_in_window, ST.ledger_entries = _real_commits, _real_ledger
OD.bc = _real_bc

# ---------------------------------------------------------------- (к) cclog
print("(к) cclog: реестр только на успехе, боевой файл под тестом не трогаем:")
import cclog

live_before = os.path.exists(ST.LEDGER_PATH) and os.path.getsize(ST.LEDGER_PATH)


class BR:
    def __init__(s, write_ok=True, read_ok=True):
        s.write_ok, s.read_ok = write_ok, read_ok

    def _call(s, action, **kw):
        return {"ok": s.read_ok, "text": "шапка\n═══\n\nстарая запись\n"}

    def write_doc(s, text=None, name=None, id=None):
        return {"ok": s.write_ok}


calls = []
_real_note = cclog._note_written
cclog._note_written = lambda kind, entry, label="": calls.append((kind, entry))
res.append(ok(cclog.write_cclog("DONE", "успешная строка", bridge=BR()) is True, "запись прошла"))
res.append(ok(len(calls) == 1 and calls[0][0] == "DONE", "успех → ровно одна отметка в реестре"))
calls.clear()
res.append(ok(cclog.write_cclog("DONE", "провал записи", bridge=BR(write_ok=False)) is False,
              "мост отказал → False"))
res.append(ok(calls == [], "провал записи → В РЕЕСТР НЕ ПИШЕМ (реестр обещаний, не намерений)"))
calls.clear()
cclog.write_cclog("DONE", "чтение упало", bridge=BR(read_ok=False))
res.append(ok(calls == [], "read fail → в реестр не пишем"))
cclog._note_written = _real_note
cclog._note_written("DONE", "строка тест-прогона — в боевой реестр попасть НЕ должна")
live_after = os.path.exists(ST.LEDGER_PATH) and os.path.getsize(ST.LEDGER_PATH)
res.append(ok(live_before == live_after, "под тест-прогоном боевой реестр не изменился"))

shutil.rmtree(TMP, ignore_errors=True)
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
