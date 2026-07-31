"""СВОДНАЯ КАРТОЧКА ВЛАДЕЛЬЦУ: ✅ = РАЗРЕШЕНИЕ НА ОПЕРАЦИЮ, а не «принял к сведению»
(класс карточек 95 и 100, инцидент 31.07.2026).

ЖИВОЙ ФАКТ, с которого снят регресс (не выдуманный):
  31.07.2026 задачи 93 и 97 закончились вердиктом куратора human → карточки-сигналы 94 и 99,
  сводные карточки владельцу 95 и 100 (`[куратор владельцу цель 93]` / `[… цель 97]`). ОБА
  пункта просили ровно одно: разрешение на `systemctl restart splinter`. Владелец подтвердил
  обе — orchestrator_daemon.log 09:29:04 и 10:44:10 «curator-human: сводная карточка N закрыта
  владельцем (✅)», result обеих: «🧑 сводная карточка владельцу закрыта (ok): пункты приняты/
  сделаны владельцем». Рестарта не случилось НИ РАЗУ: ветка `_CURATOR_HUMAN_RE` в
  process_approved гасила approved сразу в done — без конверта и без исполнения. Два зелёных
  коммита (bbbe458, e4f3999) простояли на диске полдня, вскрылось только ручной перекличкой
  (задача 96) и отдельными задачами 101/102 на рестарт.

КОРЕНЬ КЛАССА: одна кнопка означала то «принял к сведению», то «разрешаю действие», и владелец
их различить не мог. Карточка, просящая РАЗРЕШЕНИЕ на операцию, обязана рождать работу.

ЧТО ЗАКРЕПЛЕНО (тип пункта НЕ угадывается — признака «разрешение vs к сведению» нет):
  ✅ ВСЕГДА ставит задачу на исполнение пунктов, а карточка говорит об этом ДО нажатия;
  разбор «исполнять / нечего исполнять» уходит исполнителю, который видит пункт целиком.

ЖИВОЙ ФОРМАТ (класс row705→1268): тексты пунктов — ДОСЛОВНО task_text боевых карточек 95 и 100
(read-only разведка очереди Bridge 31.07.2026 ~11:15 UTC), тело карточки собирается тем же
`_curator_human_render`, что и в проде. Сети/claude нет — мост подменён.

Проверки:
 (1) карточка 95 (живой текст): ✅ → карточка done И РОВНО одна новая задача с пунктом ДОСЛОВНО;
 (2) задача встаёт в vps-полосу от Filipp-328-dev (дев-таймаут), текст = конверт;
 (3) разрыв петель: маркер конверта → самопочинка и куратор задачу пропускают;
 (4) result закрытой карточки НАЗЫВАЕТ id поставленной задачи (владелец может проследить);
 (5) карточка 100 (живой текст) — то же самое, второй дословный формат;
 (6) карточка ГОВОРИТ ДО НАЖАТИЯ, что ✅ поставит задачу (а не «закроется»);
 (7) несколько пунктов в одной карточке → все дословно уезжают в ТЗ;
 (8) FAIL-SAFE: enqueue не встал → карточка всё равно done, пункты в result ДОСЛОВНО («да»
     владельца не теряется), петли нет;
 (9) гвард ДО таймаута approved сохранён: старая карточка не гибнет «approve истёк» и всё
     равно рождает задачу;
 (10) регресс соседней ветки: обычный approved op=other по-прежнему идёт конвертом,
      кураторская ветка его не перехватывает.
"""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"   # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CURATOR"] = "1"
os.environ["CURATOR_SCOPE"] = "0"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import orchestrator_daemon as OD

# --- ЖИВОЙ ФОРМАТ: пункты боевых карточек 95 и 100 ДОСЛОВНО (разведка очереди 31.07.2026) ---
CARD95_ITEM = (
    "Нужно явное «да» владельца на `systemctl restart splinter`: фикс одометра (корни 1 и 2, "
    "commit bbbe458) уже в origin/main и зелёный по гейту (142 теста) и по живому регрессу 4957 "
    "(6/9 красных → 9/9 зелёных), но в проде НЕ действует, пока сервис работает на старом коде — "
    "в ТЗ рестарт был прямо запрещён до отдельного разрешения с названным объектом.")
CARD100_ITEM = (
    "Правка приёмника лежит в origin/main (e4f3999), но splinter крутит старый код: нужно твоё "
    "решение на рестарт splinter (в задаче он был запрещён) и живая проверка — ответить "
    "«да systemctl restart splinter» на реальную карточку в теме 1160 и подтвердить, что ответ "
    "принят, а не отбит справкой.")


# «Свежая» метка updated считается от ТЕКУЩЕГО момента, а не хардкодится: иначе тест протухает
# ровно через APPROVED_TTL после написания и ветка таймаута начинает съедать чужие проверки.
NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь в памяти (образец test_curator_human.FakeBridge) + журнал enqueue-вызовов."""
    def __init__(s):
        s.rows, s.nid = {}, 300
        s.fail_enqueue = False
        s.enq_calls = []
    def add(s, status, text, frm="Filipp-328-dec", result="", updated=NOW_ISO):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": updated}
        return s.nid
    def get_pending(s, status="new", lane=None):
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: x["id"])
                                      if r["status"] in sts]}
    def claim_task(s, tid, lane=None):
        r = s.rows.get(int(tid))
        if not r or r["status"] != "new":
            return {"ok": False, "error": "not_found"}
        r["status"] = "in_progress"
        return {"ok": True, "task": dict(r)}
    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}
    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text, lane))
        if s.fail_enqueue:
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def issue_write_ticket(s): return {"ok": True, "ticket": "T"}
    def consume_write_ticket(s, t): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}


_real_bc = OD.bc
OD._restart_pending = lambda: False
consults = []
OD._curator_consult = lambda goal, result: (consults.append((goal, result)) or
                                            {"verdict": "closed", "tasks": [], "human": "",
                                             "reason": "x"})


def setup():
    fb = FakeBridge()
    OD.bc = fb
    OD._curated.clear(); consults.clear()
    return fb


def card(fb, root, items, updated=NOW_ISO):
    """Живая сводная карточка в approved: task_text = маркер + первый пункт (как в проде),
    result = тело, собранное боевым рендером."""
    body = OD._curator_human_render(root, [(t, 1) for t in items])
    return fb.add("approved", f"[куратор владельцу цель {root}] {items[0]}",
                  frm="Filipp-328-dec", result=body, updated=updated)


# --- (1)(2)(4) карточка 95 дословно ---
print("(1) карточка 95 (живой текст): ✅ → задача на исполнение:")
fb = setup()
cid = card(fb, 93, [CARD95_ITEM])
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done", "карточка закрыта done"))
res.append(ok(len(fb.enq_calls) == 1, f"поставлена РОВНО одна задача (было {len(fb.enq_calls)})"))
tz95 = fb.enq_calls[0][1] if fb.enq_calls else ""
res.append(ok(CARD95_ITEM in tz95, "пункт карточки 95 уехал в ТЗ ДОСЛОВНО"))

print("(2) полоса и форма задачи:")
res.append(ok(bool(fb.enq_calls) and fb.enq_calls[0][0] == "Filipp-328" + OD.DEV_FROM_SUFFIX,
              "from=Filipp-328-dev (vps-полоса, дев-таймаут 45 мин)"))
res.append(ok(bool(fb.enq_calls) and fb.enq_calls[0][2] is None, "lane не задан → полоса vps"))
res.append(ok(OD._is_convert(tz95), "текст задачи — конверт ([конверт одобренной заявки N] первым)"))

print("(3) разрыв петель (маркер конверта):")
res.append(ok(bool(tz95) and OD._maybe_selfheal(999, tz95, "провал", frm="Filipp-328-dev") is False,
              "самопочинка конверт НЕ трогает (петля перерождений невозможна)"))
if tz95:
    OD._maybe_curator_single("Filipp-328-dev", 999, tz95, "итог")
res.append(ok(bool(tz95) and consults == [],
              "куратор на терминале конверта НЕ консультируется (ре-карточки нет)"))

print("(4) прослеживаемость:")
nid95 = next((r["id"] for r in fb.rows.values() if r["task_text"] == tz95 and tz95), None)
res.append(ok(nid95 is not None and str(nid95) in fb.rows[cid]["result"],
              f"result закрытой карточки называет id поставленной задачи ({nid95})"))
res.append(ok("приняты/сделаны владельцем" not in fb.rows[cid]["result"],
              "прежней формулировки «пункты приняты/сделаны владельцем» больше нет"))

# --- (5) карточка 100 дословно ---
print("(5) карточка 100 (живой текст):")
fb = setup()
cid = card(fb, 97, [CARD100_ITEM])
OD.process_approved()
tz100 = fb.enq_calls[0][1] if fb.enq_calls else ""
res.append(ok(fb.rows[cid]["status"] == "done" and len(fb.enq_calls) == 1,
              "карточка done + РОВНО одна задача"))
res.append(ok(CARD100_ITEM in tz100 and OD._is_convert(tz100),
              "пункт 100 дословно в ТЗ, текст — конверт"))

# --- (6) владелец видит ДО нажатия, что будет после «да» ---
print("(6) карточка говорит ДО нажатия:")
body = OD._curator_human_render(93, [(CARD95_ITEM, 1)])
res.append(ok("✅" in body and "❌" in body, "кнопки названы"))
res.append(ok("ЗАДАЧУ" in body.upper() and "ПОСТАВЛ" in body.upper(),
              "подпись прямо говорит: ✅ поставит задачу на исполнение"))
res.append(ok("карточка закроется" not in body,
              "прежнего обещания «карточка закроется» (и только) больше нет"))
res.append(ok(1 == len(OD._curator_human_items(body)),
              "служебные строки подписи не читаются как пункты (парсер цел)"))

# --- (7) несколько пунктов ---
print("(7) несколько пунктов в одной карточке:")
fb = setup()
cid = card(fb, 93, [CARD95_ITEM, CARD100_ITEM])
OD.process_approved()
tz = fb.enq_calls[0][1] if fb.enq_calls else ""
res.append(ok(CARD95_ITEM in tz and CARD100_ITEM in tz, "оба пункта дословно в одном ТЗ"))
res.append(ok(len(fb.enq_calls) == 1, "одна задача на карточку, не по задаче на пункт"))

# --- (8) fail-safe: enqueue не встал ---
print("(8) fail-safe enqueue:")
fb = setup()
fb.fail_enqueue = True
cid = card(fb, 93, [CARD95_ITEM])
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done", "карточка всё равно закрыта done (не зависает)"))
res.append(ok(CARD95_ITEM in fb.rows[cid]["result"],
              "«да» не потеряно: пункт лежит в result ДОСЛОВНО, дожать «тз:» руками"))

# --- (9) гвард ДО таймаута approved ---
print("(9) гвард ДО таймаута approved:")
fb = setup()
cid = card(fb, 93, [CARD95_ITEM], updated="2026-01-01T00:00:00+00:00")
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done" and "истёк" not in fb.rows[cid]["result"],
              "старая карточка не гибнет «approve истёк»"))
res.append(ok(len(fb.enq_calls) == 1, "и всё равно рождает задачу"))

# --- (10) соседняя ветка не задета ---
print("(10) регресс: обычный approved op=other:")
fb = setup()
oid = fb.add("approved", "почини X", frm="Filipp-328-dev",
             result="op=other | нужно доразрешение на правку X")
OD.process_approved()
res.append(ok(fb.rows[oid]["status"] == "done" and len(fb.enq_calls) == 1
              and OD._is_convert(fb.enq_calls[0][1]),
              "op=other по-прежнему уходит конвертом (кураторская ветка его не перехватила)"))

OD.bc = _real_bc
print(f"\nИТОГО: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
