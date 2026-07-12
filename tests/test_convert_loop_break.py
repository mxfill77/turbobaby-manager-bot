"""КОРНЕВОЙ РАЗРЫВ ПЕТЕЛЬ КОНВЕРТОВ op=other (O4, ст3, 06.07.2026). Три слоя:
  СЛОЙ 1 (ядро): конверт-задача (текст с маркером «[конверт одобренной заявки N]»), снова
    эскалировавшая NEEDS_APPROVAL, → НЕ approvable needs_approval (ре-конверт = петля), а
    терминальный failed с ручной картой (без approve-кнопки) → петля рвётся после 1 перерождения.
  СЛОЙ 2: известное headless-НЕВОЗМОЖНОЕ красное (clasp/живая таблица/деньги/sqlite3/удаление)
    по keyword → НЕ конвертируем вовсе → сразу терминальная карта = ноль перерождений.
  СЛОЙ 3: fingerprint-дедуп /inbox (devbot) — здесь не проверяем, он не в orchestrator_daemon.
Сети/Telegram/claude нет — всё мокнуто."""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ.setdefault("PLAN_ADAPT", "0")  # изоляция от боевого .env (адаптация плана, кусок 2)
os.environ["CURATOR"] = "0"  # изоляция от боевого .env (куратор целей, родитель 231; принудительно — env демона)

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь оркестратора в памяти. na_calls считает set_needs_approval — так проверяем,
    что слой 1/2 НЕ ставит approvable needs_approval (нет approve-кнопки)."""
    def __init__(s):
        s.rows, s.nid = {}, 100
        s.enqueue_fail = False
        s.na_calls = 0
    def enqueue_task(s, frm, txt):
        if s.enqueue_fail:
            return {"ok": False, "error": "bridge_down"}
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": txt, "status": "new",
                         "result": "", "updated": now_iso()}
        return {"ok": True, "id": s.nid}
    def get_pending(s, status="new"):
        sts = [x.strip() for x in str(status).split(",")]
        items = [dict(r) for r in sorted(s.rows.values(), key=lambda x: -x["id"])
                 if r["status"] in sts]
        return {"ok": True, "items": items}
    def claim_task(s, tid):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        if r["status"] != "new": return {"ok": False, "error": "already_claimed", "status": r["status"]}
        r["status"] = "in_progress"; r["updated"] = now_iso()
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"], r["updated"] = status, result, now_iso()
        return {"ok": True}
    def set_needs_approval(s, tid, what):
        s.na_calls += 1
        r = s.rows.get(int(tid))
        r["status"], r["result"], r["updated"] = "needs_approval", what, now_iso()
        return {"ok": True}
    def approve(s, tid):                       # тестовый шорткат «да N»
        r = s.rows.get(int(tid)); r["status"] = "approved"; r["updated"] = now_iso()
    def task_heartbeat(s, tid): return {"ok": True}
    def issue_write_ticket(s): return {"ok": True, "ticket": "t-test"}
    def consume_write_ticket(s, tk): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}
    def by_status(s, status):
        return [r for r in s.rows.values() if r["status"] == status]


class FakeProc:
    def __init__(s, out, rc=0): s.stdout, s.stderr, s.returncode = out, "", rc


_real_run = OD.subprocess.run
def fake_run(args, **kw):
    fake_run.calls.append(args)
    if args and args[0] == OD.CLAUDE_BIN:
        return FakeProc(fake_run.out)
    return FakeProc("ok")
fake_run.calls = []
fake_run.out = "сводка: сделано"
OD.subprocess.run = fake_run


def fresh():
    fb = FakeBridge()
    OD.bc = fb
    OD._summarized.clear()
    return fb


def is_manual(text):
    return "ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ" in text and "это не сбой" in text


CONV_PREFIX = "[конверт одобренной заявки 999] Филипп нажал «да» на заявку: сделать нечто\nИсходная задача: X"


# (1) конверт-задача снова упирается в красное → failed с ручной картой, НЕ needs_approval, БЕЗ кнопки
print("(1) СЛОЙ 1: конверт → NEEDS_APPROVAL → терминальный failed, без approve:")
fb = fresh()
cid = fb.enqueue_task("Filipp-328-dev", CONV_PREFIX)["id"]
fake_run.out = "NEEDS_APPROVAL: op=other | записать в CRM бронь Ивана · CRM/Байки · смотреть строку"
OD.process_new()
row = fb.rows[cid]
res.append(ok(row["status"] == "failed", "конверт → failed (НЕ needs_approval)"))
res.append(ok(fb.na_calls == 0, "set_needs_approval НЕ звался → approve-кнопки нет (ре-конверт невозможен)"))
res.append(ok(is_manual(row["result"]), "тело = «✋ ТРЕБУЕТСЯ РУЧНОЕ ДЕЙСТВИЕ (это не сбой)» + инструкция"))
res.append(ok("записать в CRM" in row["result"], "карточка красного действия сохранена в теле"))
res.append(ok(len(fb.by_status("new")) == 0, "новых конвертов не создано (петля не продолжается)"))


# (2) слой 2: известное headless-невозможное красное → терминальная карта сразу, ноль конвертов
print("(2) СЛОЙ 2: keyword-классификатор ловит красное → терминал сразу, ноль конвертов:")
cases = [
    ("op=other | clasp redeploy Bridge · прод · ping", "clasp/redeploy"),
    ("op=other | записать бронь в Лист1 Байки · confirmed=true", "живая таблица Лист1"),
    ("op=other | провести транзакцию: деньги в кассу · Money Cashflow", "деньги/транзакция"),
    ("op=other | sqlite3 memory.db UPDATE trust", "sqlite3 CLI"),
    ("op=other | удалить событие календаря брони", "удаление события"),
]
for desc, label in cases:
    fb = fresh()
    tid = fb.enqueue_task("Filipp-328-dev", "какая-то дев-задача")["id"]
    fb.rows[tid]["status"] = "needs_approval"; fb.rows[tid]["result"] = desc
    fb.approve(tid)
    OD.process_approved()
    r = fb.rows[tid]
    conv_created = len(fb.by_status("new")) > 0 or any(x["from"] == "Filipp-328-dev" and x["id"] != tid
                                                       for x in fb.rows.values())
    res.append(ok(r["status"] == "failed" and is_manual(r["result"]) and not conv_created,
                  f"{label}: терминальная карта сразу, конвертов 0"))


# (3) неизвестное (не-keyword) op=other → конверт 1 раз; при ре-эскалации слой 1 рвёт
print("(3) неизвестное op=other → конверт 1 раз → слой 1 обрывает на ре-эскалации:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "разберись и примени внутреннюю правку логгера")["id"]
fb.rows[tid]["status"] = "needs_approval"
fb.rows[tid]["result"] = "op=other | нужно твоё решение: включить флаг X · внутренний конфиг · смотреть diff"
fb.approve(tid)
OD.process_approved()
res.append(ok(fb.rows[tid]["status"] == "done" and "конвертировано" in fb.rows[tid]["result"],
              "неизвестное op=other → конверт создан (1 перерождение разрешено)"))
convs = fb.by_status("new")
res.append(ok(len(convs) == 1 and convs[0]["task_text"].startswith("[конверт одобренной заявки"),
              "ровно 1 конверт-задача с маркером"))
conv_id = convs[0]["id"]
# конверт снова упирается в красное → слой 1
fake_run.out = "NEEDS_APPROVAL: op=other | внезапно требуется запись в Лист1 · Байки"
OD.process_new()
res.append(ok(fb.rows[conv_id]["status"] == "failed" and is_manual(fb.rows[conv_id]["result"]),
              "конверт ре-эскалировал → слой 1: терминальный failed"))
res.append(ok(fb.na_calls == 0 and len(fb.by_status("new")) == 0,
              "второго конверта нет, approve-кнопки нет → петля оборвана"))


# (4) обычные op не задеты: git_push (AUTO_OPS) хардкод; headless-доступное op=other → конверт → done
print("(4) обычные op НЕ задеты:")
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "задача с push")["id"]
fb.rows[tid]["status"] = "needs_approval"; fb.rows[tid]["result"] = "op=git_push | нужен push"
fb.approve(tid)
fake_run.calls = []
OD.process_approved()
res.append(ok(fb.rows[tid]["status"] == "done" and any(a and a[0] == "git" for a in fake_run.calls)
              and not is_manual(fb.rows[tid]["result"]),
              "op=git_push → хардкод git push (не терминальная карта)"))
# headless-доступное op=other: конверт → исполнился без маркера → done
fb = fresh()
tid = fb.enqueue_task("Filipp-328-dev", "поправь текст сообщения")["id"]
fb.rows[tid]["status"] = "needs_approval"
fb.rows[tid]["result"] = "op=other | нужно решение: заменить формулировку приветствия · prompts.py"
fb.approve(tid)
OD.process_approved()
conv = fb.by_status("new")[0]
res.append(ok(conv["task_text"].startswith("[конверт"), "headless-доступное op=other → конверт создан"))
fake_run.out = "сводка: правка применена, гейт зелёный"
OD.process_new()
res.append(ok(fb.rows[conv["id"]]["status"] == "done" and not is_manual(fb.rows[conv["id"]]["result"]),
              "конверт исполнился headless → done (петля не рвётся зря)"))


# (5) симуляция старой петли 56→57→58 → обрывается на первом перерождении
print("(5) симуляция старой петли 56→57→58 → обрыв на первом:")
fb = fresh()
# 56: исходная неизвестная op=other-заявка
t56 = fb.enqueue_task("Filipp-328-dev", "исходная задача про внутреннюю правку")["id"]
fb.rows[t56]["status"] = "needs_approval"
fb.rows[t56]["result"] = "op=other | нужно решение по внутренней правке · смотреть diff"
fb.approve(t56)
OD.process_approved()                              # 56 → конверт 57
c57 = fb.by_status("new")[0]["id"]
fake_run.out = "NEEDS_APPROVAL: op=other | снова красное · Лист1"
OD.process_new()                                   # 57 → слой 1 → failed (НЕТ 58)
convert_marker_rows = [r for r in fb.rows.values()
                       if str(r["task_text"]).startswith("[конверт одобренной заявки")]
res.append(ok(len(convert_marker_rows) == 1, "создан РОВНО 1 конверт (57), задачи 58 нет"))
res.append(ok(fb.rows[c57]["status"] == "failed" and is_manual(fb.rows[c57]["result"]),
              "57 = терминальный failed с ручной картой"))
res.append(ok(fb.na_calls == 0, "ни одного approvable needs_approval на конверте → петля мертва"))


OD.subprocess.run = _real_run
print("\nИТОГ:", "ВСЕ PASS" if all(res) else f"ЕСТЬ FAIL ({sum(res)}/{len(res)})")
sys.exit(0 if all(res) else 1)
