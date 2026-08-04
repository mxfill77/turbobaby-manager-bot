"""КУРАТОРСКАЯ КНОПКА ОБЯЗАНА ПОРОЖДАТЬ РАБОТУ — ВТОРАЯ РЕВИЗИЯ КЛАССА (04.08.2026).

ЖИВЫЕ ФАКТЫ, с которых снят регресс (снимок очереди Bridge + orchestrator_daemon.log, 04.08):
  • карточки 95 и 100 (31.07): ✅ владельца → «сводная карточка N закрыта владельцем», result
    «пункты приняты/сделаны владельцем», задачи НЕТ. Ветка до fc07efa. Тем же старым кодом
    съедены 32, 106 и 110 — причём 110 (11:41) уже ПОСЛЕ коммита фикса (11:25): демон крутил
    старый код до рестарта ~11:45.
  • карточка 264 (04.08 12:01:45): ✅ → задача 265 РОДИЛАСЬ (журнал: «карточка 264 одобрена
    (✅) → задача 265», result карточки называет её id). Работы всё равно не случилось: пункт
    просил включить дежурного строкой в файле секретов — агенту она закрыта жёстким блоком
    гарда; конверт закрылся done, ничего не сделав, а подпись карточки ДО нажатия обещала
    «пункт-разрешение будет выполнен».
  • замер 7 суток (28.07–04.08): 16 сводных карточек, 9 подтверждено владельцем, задачу
    породили 4, работу довела до конца 1 (116 — рестарт splinter, FACT PID=270986).

ЧТО ЗАКРЕПЛЕНО ЗДЕСЬ (каждая проверка — на дословном живом тексте):
 (1) карточки 95, 100, 264 ДОСЛОВНО: ✅ → РОВНО одна задача, пункт в ТЗ дословно;
 (2) подпись «что будет после ✅» переживает потолок result: тело режется ПОД подпись
     (до правки: 12 пунктов → тело ровно RESULT_MAX и подписи нет ВООБЩЕ);
 (3) многострочный пункт доезжает в ТЗ ЦЕЛИКОМ (до правки: только первая строка);
 (4) постановка не встала → карточка FAILED, а не done (done читался как успех при
     отсутствующей задаче — тот же класс с другой стороны), пункты в result дословно;
 (5) ответ моста потерян, а конверт долетел → берём его id, ДУБЛЯ НЕТ (класс 138/146);
 (6) разовый сбой постановки → ровно один повтор → задача всё-таки есть;
 (7) пункт «принял к сведению» работы не рождает: тип НЕ угадываем (задача ставится всегда),
     но ТЗ прямо запрещает её выдумывать — исход для владельца прежний;
 (8) подпись называет ОБА исхода и НЕ подсовывает devbot объект сверки «да <объект>»;
 (9) границы целы: op=other идёт своим конвертом, петли конверта по-прежнему разорваны.
"""
import datetime
import os
import re
import sys

REPO = "/root/turbobaby-manager-bot"
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
# ИЗОЛЯЦИЯ ОТ БОЕВОГО .env: демон делает load_dotenv на импорте и тянет боевые флаги в тест
# (урок e9a07b0 — при включении CARD_DUTY семь легаси-сьютов покраснели). setdefault НЕ хватает.
for _k in ("STEP_SELFHEAL", "PLAN_ADAPT", "CARD_DUTY"):
    os.environ[_k] = "0"
os.environ["CURATOR"] = "1"

import orchestrator_daemon as OD  # noqa: E402


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

# --- ДОСЛОВНЫЕ ПУНКТЫ БОЕВЫХ КАРТОЧЕК (снимок очереди Bridge 04.08.2026) ---
ITEM95 = ("Нужно явное «да» владельца на `systemctl restart splinter`: фикс одометра (корни 1 и 2, "
          "commit bbbe458) уже в origin/main и зелёный по гейту (142 теста) и по живому регрессу "
          "4957 (6/9 красных → 9/9 зелёных), но в проде НЕ действует, пока сервис работает на "
          "старом коде — в ТЗ рестарт был прямо запрещён до отдельного разрешения с названным "
          "объектом.")
ITEM100 = ("Правка приёмника лежит в origin/main (e4f3999), но splinter крутит старый код: нужно "
           "твоё решение на рестарт splinter (в задаче он был запрещён) и живая проверка — "
           "ответить «да systemctl restart splinter» на реальную карточку в теме 1160 и "
           "подтвердить, что ответ принят, а не отбит справкой.")
ITEM264 = ("Дежурный собран и в гейте, но в бою выключен: флаг CARD_DUTY по умолчанию 0 (ветка "
           "мертва, карточки идут владельцу как раньше). Нужно твоё решение — включать ли "
           "дежурного: поставить CARD_DUTY=1 в .env и перезапустить демон оркестратора (откат тот "
           "же: вернуть 0 + рестарт). Это решение про то, что машина будет снимать твои карточки, "
           "поэтому за тобой. Отдельным остатком висит зеркало на ПК-полосе — о")
# пункт «просто принял к сведению» — дословная форма из карточки 32 (цель 30)
ITEM_FYI = ("Реши, чья реализация минимума красной карточки живёт: ПК-коммит или VPS-коммит — "
            "обе в main, расходятся только формулировкой строки.")

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()


class FakeBridge:
    """Очередь в памяти + управляемые сбои постановки (образец test_curator_human_exec)."""

    def __init__(s):
        s.rows, s.nid = {}, 700
        s.enq_calls = []
        s.fail_enqueue = False      # сбой ОБЕИХ попыток
        s.fail_first = False        # сбой только первой (повтор проходит)
        s.lost_answer = False       # задача ВСТАЁТ, а ответ теряется (класс 138/146)
        s.fail_verify = False       # verify-чтение очереди не отвечает

    def add(s, status, text, frm="Filipp-328-dec", result="", updated=NOW_ISO):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": updated}
        return s.nid

    def get_pending(s, status="new", lane=None):
        if s.fail_verify and status == "new":
            return {"ok": False, "error": "request_failed"}
        sts = [x.strip() for x in str(status).split(",")]
        return {"ok": True, "items": [dict(r) for r in sorted(s.rows.values(), key=lambda x: x["id"])
                                      if r["status"] in sts]}

    def complete_task(s, tid, status, result=""):
        r = s.rows.get(int(tid))
        if not r:
            return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = status, result
        return {"ok": True}

    def enqueue_task(s, frm, text, lane=None):
        s.enq_calls.append((frm, text, lane))
        n = len(s.enq_calls)
        if s.lost_answer and n == 1:
            s.add("new", text, frm=frm)          # долетело сервер-сайд, ответ потерян
            return {"ok": False, "error": "request_failed"}
        if s.fail_enqueue or (s.fail_first and n == 1):
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}

    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}

    def claim_task(s, tid, lane=None):
        return {"ok": True, "task": dict(s.rows[int(tid)])}

    def task_heartbeat(s, tid):
        return {"ok": True}

    def issue_write_ticket(s):
        return {"ok": True, "ticket": "T"}

    def consume_write_ticket(s, t):
        return {"ok": True}

    def log_write(s, **kw):
        return {"ok": True}


_real_bc = OD.bc
OD._restart_pending = lambda: False
consults = []
OD._curator_consult = lambda goal, result: (consults.append((goal, result)) or
                                            {"verdict": "closed", "tasks": [], "human": "",
                                             "reason": "x"})


def setup():
    fb = FakeBridge()
    OD.bc = fb
    OD._curated.clear()
    consults.clear()
    return fb


def card(fb, root, items, updated=NOW_ISO):
    """Живая сводная карточка в approved: task_text = маркер + первый пункт (как в проде),
    result = тело, собранное БОЕВЫМ рендером."""
    body = OD._curator_human_render(root, [(t, 1) for t in items])
    return fb.add("approved", f"[куратор владельцу цель {root}] {items[0]}",
                  frm="Filipp-328-dec", result=body, updated=updated)


def convert_of(fb):
    """Текст конверта, реально вставшего в очередь (не просто попытки постановки)."""
    return [r["task_text"] for r in fb.rows.values() if OD._is_convert(r["task_text"])]


# --- (1) три дословные карточки: ✅ → РОВНО одна задача с пунктом дословно ---
print("(1) дословные карточки 95, 100, 264 → задача:")
for num, root, item in ((95, 93, ITEM95), (100, 97, ITEM100), (264, 262, ITEM264)):
    fb = setup()
    cid = card(fb, root, [item])
    OD.process_approved()
    convs = convert_of(fb)
    res.append(ok(fb.rows[cid]["status"] == "done" and len(convs) == 1,
                  f"карточка {num}: закрыта done, поставлена РОВНО одна задача"))
    res.append(ok(len(convs) == 1 and item in convs[0],
                  f"карточка {num}: пункт уехал в ТЗ ДОСЛОВНО"))
    res.append(ok(str(fb.rows[cid]["result"]).find("приняты/сделаны владельцем") < 0,
                  f"карточка {num}: прежнего тихого «пункты приняты» нет"))
    nid = next((r["id"] for r in fb.rows.values() if OD._is_convert(r["task_text"])), None)
    res.append(ok(nid is not None and str(nid) in fb.rows[cid]["result"],
                  f"карточка {num}: result называет id поставленной задачи ({nid})"))

# --- (2) подпись переживает потолок result (до правки её срезало) ---
print("(2) подпись «что будет после ✅» не срезается потолком:")
for n in (1, 4, 8, 12, 20, 40):
    body = OD._curator_human_render(262, [(f"пункт {i}: " + ITEM264, 1) for i in range(n)])
    res.append(ok("ПОСТАВЛЮ ЗАДАЧУ" in body and len(body) <= OD.RESULT_MAX,
                  f"пунктов {n}: подпись на месте, тело {len(body)} ≤ {OD.RESULT_MAX}"))
big = OD._curator_human_render(262, [(f"пункт {i}: " + ITEM264, 1) for i in range(20)])
res.append(ok(OD._HUMAN_OVERFLOW in big,
              "не поместившиеся пункты названы ЧИСЛОМ (молча ничего не исчезает)"))
res.append(ok(len(OD._curator_human_items(big)) >= 1,
              "уцелевшие пункты по-прежнему разбираются"))

print("(2б) хвост урезки доезжает до исполнителя (список не выдаётся за полный):")
fb = setup()
many = [f"пункт {i}: " + ITEM264 for i in range(20)]
cid = card(fb, 262, many)
OD.process_approved()
convs = convert_of(fb)
res.append(ok(len(convs) == 1 and OD._HUMAN_OVERFLOW in convs[0],
              "ТЗ конверта честно говорит, что пунктов было больше"))

# --- (3) многострочный пункт доезжает целиком ---
print("(3) многострочный пункт (до правки терял всё после первой строки):")
MULTI = ("Нужны два твоих решения:\n"
         "(1) выкат фикса в прод — коммит d78d уже зелёный по гейту;\n"
         "(2) деплой моста — папка позади прода, push стёр бы ротацию.")
fb = setup()
cid = card(fb, 195, [MULTI])
OD.process_approved()
convs = convert_of(fb)
res.append(ok(len(convs) == 1 and MULTI in convs[0],
              "пункт из трёх строк уехал в ТЗ ДОСЛОВНО, целиком"))
back = OD._curator_human_items(OD._curator_human_render(195, [(MULTI, 1)]))
res.append(ok(len(back) == 1 and back[0][0] == MULTI,
              "круг рендер→разбор возвращает пункт байт-в-байт"))
back2 = OD._curator_human_items(OD._curator_human_render(195, [(MULTI, 3), ("второй", 1)]))
res.append(ok(len(back2) == 2 and back2[0] == (MULTI, 3) and back2[1] == ("второй", 1),
              "счётчик ×N и соседний пункт при этом не путаются"))

# --- (4) постановка не встала → FAILED, а не done ---
print("(4) задача не встала → карточка failed (done читался как успех):")
fb = setup()
fb.fail_enqueue = True
cid = card(fb, 93, [ITEM95])
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "failed",
              "карточка закрыта FAILED — «да» видно как незакрытое дело"))
res.append(ok(ITEM95 in fb.rows[cid]["result"],
              "«да» не потеряно: пункт в result ДОСЛОВНО"))
res.append(ok(len(fb.enq_calls) == 2, f"попыток постановки было 2 (было {len(fb.enq_calls)})"))
res.append(ok(not convert_of(fb), "фантомной задачи в очереди не появилось"))

print("(4б) verify не читается → к повтору, поведение не хуже:")
fb = setup()
fb.fail_enqueue = True
fb.fail_verify = True
cid = card(fb, 93, [ITEM95])
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "failed" and len(fb.enq_calls) == 2,
              "сбой verify не съедает повтор и не вешает карточку"))

# --- (5) ответ потерян, конверт долетел → без дубля ---
print("(5) ответ моста потерян, а конверт долетел (класс 138/146):")
fb = setup()
fb.lost_answer = True
cid = card(fb, 262, [ITEM264])
OD.process_approved()
convs = convert_of(fb)
res.append(ok(len(convs) == 1, f"конверт в очереди РОВНО один (было {len(convs)}) — дубля нет"))
res.append(ok(len(fb.enq_calls) == 1, "второй постановки не было (verify нашёл долетевшую)"))
_nid = next((r["id"] for r in fb.rows.values() if OD._is_convert(r["task_text"])), None)
res.append(ok(fb.rows[cid]["status"] == "done" and _nid is not None
              and str(_nid) in fb.rows[cid]["result"],
              f"карточка done и НАЗЫВАЕТ id долетевшей задачи ({_nid}) — не «дожми руками»"))

# --- (6) разовый сбой → один повтор ---
print("(6) разовый сбой постановки → ровно один повтор:")
fb = setup()
fb.fail_first = True
cid = card(fb, 97, [ITEM100])
OD.process_approved()
convs = convert_of(fb)
res.append(ok(len(convs) == 1 and len(fb.enq_calls) == 2,
              "две попытки, одна задача — работа за «да» всё-таки есть"))
res.append(ok(fb.rows[cid]["status"] == "done", "карточка done"))

# --- (7) пункт «принял к сведению» ---
print("(7) пункт «просто принял к сведению»:")
fb = setup()
cid = card(fb, 30, [ITEM_FYI])
OD.process_approved()
convs = convert_of(fb)
res.append(ok(len(convs) == 1 and ITEM_FYI in convs[0],
              "задача ставится (тип пункта НЕ угадываем) с пунктом дословно"))
res.append(ok(len(convs) == 1 and "работу НЕ выдумывай" in convs[0],
              "ТЗ прямо запрещает выдумывать работу → пункт «к сведению» её не рождает"))
res.append(ok(len(convs) == 1 and "исполнять нечего" in convs[0],
              "исполнителю названа форма честного отчёта «исполнять нечего»"))

# --- (8) подпись: оба исхода названы, объект сверки не подсунут ---
print("(8) подпись говорит ДО нажатия и не подсовывает объект:")
body = OD._curator_human_render(93, [(ITEM95, 1)])
res.append(ok("ПОСТАВЛЮ ЗАДАЧУ" in body, "исход ✅ назван: поставлю задачу"))
res.append(ok("вернёт его тебе ручной картой" in body,
              "назван и ВТОРОЙ исход: красный пункт вернётся владельцу (живой факт 258/265)"))
res.append(ok("гейт красной зоны НЕ открывает" in body,
              "сказано прямо: «да» на карточке красную зону не открывает"))
res.append(ok("карточка закроется" not in body, "прежнего «карточка закроется» нет"))
SIGN = OD._HUMAN_SIGN
res.append(ok("`" not in SIGN, "в подписи нет обратных кавычек (объект сверки берётся из ТЕЛА)"))
res.append(ok(not re.search(r"systemctl|clasp\s+\w|git\s+push|sqlite3\s", SIGN),
              "в подписи нет токенов объекта (systemctl/clasp/git push/sqlite3)"))
res.append(ok(len(OD._curator_human_items(body)) == 1,
              "служебные строки подписи не читаются как пункты"))
try:
    sys.path.insert(0, REPO)
    import devbot                                     # noqa: E402
    res.append(ok(devbot._card_objects(SIGN) == [],
                  "devbot._card_objects: в подписи объектов НЕТ (сверка «да <объект>» цела)"))
    res.append(ok(devbot._card_objects(body) == ["systemctl restart splinter"],
                  "объект сверки берётся из ПУНКТА владельца, а не из служебного текста"))
except Exception as e:                                # noqa: BLE001
    res.append(ok(False, f"devbot не импортировался: {e}"))

# --- (9) границы ---
print("(9) границы не сдвинуты:")
fb = setup()
oid = fb.add("approved", "почини X", frm="Filipp-328-dev",
             result="op=other | нужно доразрешение на правку X")
OD.process_approved()
res.append(ok(fb.rows[oid]["status"] == "done" and len(fb.enq_calls) == 1
              and OD._is_convert(fb.enq_calls[0][1]),
              "op=other по-прежнему уходит своим конвертом"))
fb = setup()
cid = card(fb, 93, [ITEM95])
OD.process_approved()
tz = convert_of(fb)[0]
res.append(ok(OD._maybe_selfheal(999, tz, "провал", frm="Filipp-328-dev") is False,
              "самопочинка конверт НЕ трогает (петля перерождений невозможна)"))
OD._maybe_curator_single("Filipp-328-dev", 999, tz, "итог")
res.append(ok(consults == [], "куратор на терминале конверта не консультируется"))
fb = setup()
cid = card(fb, 93, [ITEM95], updated="2026-01-01T00:00:00+00:00")
OD.process_approved()
res.append(ok(fb.rows[cid]["status"] == "done" and "истёк" not in fb.rows[cid]["result"]
              and len(convert_of(fb)) == 1,
              "гвард ДО таймаута approved цел: старое «да» не сгорает и рождает задачу"))

OD.bc = _real_bc
print(f"\nИТОГО: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
