"""ЧАСТИЧНЫЙ РАЗВОД КУРАТОРСКОГО ПУНКТА ВИДЕН ВЛАДЕЛЬЦУ (класс 05.08.2026).

КЛАСС. Развод пункта куратора по операциям (`_curator_human_split`, класс 251/254/257) ставит
ОДНУ карточку на операцию — и каждая постановка может не встать по отдельности (мост, очередь;
живой прецедент отказов моста — класс 138/146). Тогда часть карточек стоит, часть нет. Демон
называл недостающие операции ТОЛЬКО в отчётной карточке 328 (строка под знаком внимания), а
владелец решает по карточкам ИНБОКСА — и там ему говорили ровно обратное: строка «рядом по этому
же пункту ждут: …» перечисляла ВСЕ соседние операции, включая те, у которых карточки нет и не
будет. Владелец видел полный список ожидающих «да» и не знал, что часть операций требует его воли
БЕЗ единой карточки. Это хуже лишней карточки — это молчание о том, что требует его воли.

ПОЧЕМУ НЕ FAIL-CLOSED «до факта». Отказ постановки обнаруживается ТОЛЬКО попыткой (мост отвечает
на запрос), а поставленную карточку не отозвать честно: `completeTask_` знает лишь done|failed, и
закрытие уже уехавшей в инбокс карточки оставило бы владельцу в Telegram кнопку, за которой мёртвая
строка очереди — та же ложь с другой стороны. Поэтому честная форма одна: карточка САМА называет,
чего не хватает.

ЗАМЕР (снимок очереди 05.08.2026, все статусы, 199 задач; окно 7 суток 29.07–05.08; классификатор
боевой `curator_ops`): пунктов ветки human — 20; из них назвали ДВЕ и более операции 4 (карточки
250, 253, 256, 263 → 3+3+2+2 = 10 карточек развода), ровно одну — 11, ни одной — 5. Разводов,
выполненных живьём, — 0, поэтому ЧАСТИЧНЫХ наблюдалось 0 из 0: код развода лёг в 04:35, демон
поднял его рестартом 06:53, а ни один human-вердикт после этого двух операций не назвал. То есть
класс — не прошлое, а ближайшее будущее: ~4 развода в неделю, 10 отдельных постановок, каждая со
своим шансом не встать.

ЖИВОЙ ФОРМАТ (класс row705→1268): тексты пунктов — ДОСЛОВНО task_text боевых карточек 251 и 95;
тела карточек собирает тот же `_curator_human_render`, отчёт в 328 — тот же `_curator_card_text`,
строку вердикта — тот же `devbot._curator_line`. Сети/claude нет — мост подменён.

Проверки:
 (1) частичный развод: карточка ВЛАДЕЛЬЦА называет операции, оставшиеся без карточки;
 (2) она же не выдаёт их за ожидающие рядом (строка соседей говорит только о том, что есть);
 (3) вторая форма отказа — карточка встала в очередь, но не финализировалась;
 (4) ПОЛНЫЙ развод работает как прежде: ни строки о нехватке, соседи на месте, лишних правок
     карточек нет (счётчик вызовов), одна операция — байт-в-байт прежний рендер;
 (5) служебная строка не притворяется пунктом: конверт «да» несёт ОДНУ операцию и не получает
     недостающие как работу;
 (6) отчёт в 328 говорит и о нехватке, и о том, названа ли она владельцу; при полном провале
     дописи он называет карточки, которые молчат;
 (7) ГРАНИЦЫ: подпись 3a95df7 целиком и последней, потолок result, токенов объекта в служебной
     строке нет, fail-safe «ни одной карточки → прежний путь» цел, а devbot по-прежнему не ужимает
     такую карточку в строку (027e280).
"""
import os, sys, datetime
sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x"); os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"   # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "1"
os.environ["CURATOR_SCOPE"] = "0"

def ok(c, l): print(("  PASS " if c else "  FAIL ") + l); return c
res = []

import curator_ops
import orchestrator_daemon as OD

# МОСТ К КОДУ БЕЗ ПРАВКИ: на дереве ДО фикса имён ещё нет, и тест обязан падать ПРОВЕРКАМИ
# («поведение другое»), а не AttributeError («функции нет») — иначе замер «красный до» не замер.
PLACE = getattr(OD, "_curator_human_place", None) or OD._curator_human_upsert
SIGN = getattr(OD, "_HUMAN_SIGN", "· подписи в коде нет")
SIBL = getattr(OD, "_HUMAN_SIBL", "· строки соседей в коде нет")
SCOPE = getattr(OD, "_HUMAN_SCOPE", "· строки области «да» в коде нет")
MISS = getattr(OD, "_HUMAN_MISSING", "· строки «чего не хватает» в коде НЕТ")
NOTE_TOLD = getattr(OD, "_NOTE_TOLD", "в карточки владельца это вписано")
NOTE_SILENT = getattr(OD, "_NOTE_SILENT", "молчат о недостающих операциях")

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# --- ЖИВОЙ ФОРМАТ: пункты боевых карточек ДОСЛОВНО (разведка очереди 05.08.2026) --------------
CARD251 = (
    "Нужен владелец на красное: (1) деплой моста — `clasp push` + `clasp redeploy` "
    "прод-deploymentId (до него edit_event в проде отвечает unknown_action, эффект кода живым "
    "фактом НЕ доказан — FACT-блока в итоге нет); (2) после деплоя на живом случае NMAX 155 "
    "GREEN-B 4957 — правка строки событий 29.07 09:32:15 (38982→36982) и понижение Лист1 I16 "
    "37000→36982 веткой «исправление ошибки», каждое по отдельн")
CARD95 = (
    "Нужно явное «да» владельца на `systemctl restart splinter`: фикс одометра (корни 1 и 2, "
    "commit bbbe458) уже в origin/main и зелёный по гейту (142 теста) и по живому регрессу 4957 "
    "(6/9 красных → 9/9 зелёных), но в проде НЕ действует, пока сервис работает на старом коде — "
    "в ТЗ рестарт был прямо запрещён до отдельного разрешения с названным объектом.")

OPS251 = curator_ops.operations(CARD251)
LAB251 = [o["label"] for o in OPS251]


class FakeBridge:
    """Очередь в памяти (образец test_curator_split.FakeBridge) + счётчики вызовов."""
    def __init__(s):
        s.rows, s.nid = {}, 400
        s.fail_pending = False
        s.enq_fail_from = None      # с какого по счёту enqueue отвечать отказом
        s.sna_fail_calls = ()       # НОМЕРА вызовов set_needs_approval, которые отвечают отказом
        s.enq_calls, s.sna_calls = [], []
    def add(s, status, text, frm="Filipp-328-dec", result="", updated=NOW_ISO):
        s.nid += 1
        s.rows[s.nid] = {"id": s.nid, "from": frm, "task_text": text, "status": status,
                         "result": result, "updated": updated}
        return s.nid
    def get_pending(s, status="new", lane=None):
        if s.fail_pending:
            return {"ok": False, "error": "request_failed"}
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
    def enqueue_task(s, frm, text, lane=None, dedup_key=None):
        s.enq_calls.append((frm, text, lane))
        if s.enq_fail_from is not None and len(s.enq_calls) >= s.enq_fail_from:
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        s.sna_calls.append((int(tid), what))
        if len(s.sna_calls) in s.sna_fail_calls:
            return {"ok": False, "error": "request_failed"}
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}


OD._restart_pending = lambda: False


def setup(**kw):
    fb = FakeBridge()
    for k, v in kw.items():
        setattr(fb, k, v)
    OD.bc = fb
    return fb


def cards_of(fb, root):
    pref = f"[куратор владельцу цель {root}"
    return [r for r in sorted(fb.rows.values(), key=lambda x: x["id"])
            if str(r["task_text"]).startswith(pref) and r["status"] == "needs_approval"]


def sibl_line(body):
    return next((ln for ln in str(body).splitlines() if ln.startswith(SIBL)), "")


def miss_line(body):
    return next((ln for ln in str(body).splitlines() if ln.startswith(MISS)), "")


print("ЗАМЕР основания: пункт 251 назвал операций:", len(OPS251), [o["key"] for o in OPS251])

# ============ (1)(2) ЧАСТИЧНЫЙ РАЗВОД: встала первая карточка, остальные — нет ================
print("(1) частичный развод — карточка владельца называет, чего не хватает:")
fb = setup(enq_fail_from=2)
hum = PLACE(247, CARD251)
cards = cards_of(fb, 247)
res.append(ok(len(cards) == 1, f"встала РОВНО одна карточка из {len(OPS251)} (стоит {len(cards)})"))
body = str(cards[0]["result"]) if cards else ""
gone = LAB251[1:]                     # операции, которым карточки не досталось
res.append(ok(bool(body) and MISS in body,
              "в теле карточки есть строка «развод не полный» (её раньше не было вовсе)"))
res.append(ok(all(g in miss_line(body) for g in gone),
              f"названы ОБЕ операции без карточки: {gone}"))
res.append(ok("⚠️" in miss_line(body), "строка помечена знаком внимания — владелец её не пролистает"))

print("(2) карточка не выдаёт операции без карточки за ожидающие рядом:")
res.append(ok(not any(g in sibl_line(body) for g in gone),
              f"строка соседей о них МОЛЧИТ (в ней: «{sibl_line(body)[:60]}…»)"))
res.append(ok(SIBL not in body or sibl_line(body).strip() != SIBL.strip(),
              "пустой строки соседей в карточке не осталось"))

print("(3) вторая форма отказа: карточка встала, но не финализировалась:")
fb = setup(sna_fail_calls=(3,))   # третью карточку не финализировать; допись (4-й,5-й) проходит
hum3 = PLACE(247, CARD251)
c3 = cards_of(fb, 247)
res.append(ok(len(c3) == 2, f"финализировались две карточки из трёх (стоит {len(c3)})"))
res.append(ok(all(MISS in str(r["result"]) for r in c3),
              "ОБЕ уцелевшие карточки называют недостающую операцию"))
res.append(ok(all(LAB251[2] in miss_line(str(r["result"])) for r in c3),
              f"названа именно третья операция: {LAB251[2]}"))
res.append(ok(all(LAB251[2] not in sibl_line(str(r["result"])) for r in c3),
              "и она НЕ числится среди ожидающих рядом"))
res.append(ok(all(LAB251[1 - i] in sibl_line(str(c3[i]["result"])) for i in (0, 1)),
              "настоящий сосед в строке соседей остался"))

# ============ (4) ПОЛНЫЙ РАЗВОД — БАЙТ-В-БАЙТ КАК ПРЕЖДЕ (зелёное в ОБОИХ прогонах) ==========
print("(4) полный развод — как прежде:")
fb = setup()
humF = PLACE(247, CARD251)
cF = cards_of(fb, 247)
res.append(ok(len(cF) == len(OPS251), f"карточек ровно {len(OPS251)} (стоит {len(cF)})"))
res.append(ok(humF is not None and humF[1] == "split", "режим развода"))
res.append(ok(not (len(humF) > 2 and humF[2]), f"отчёт без заметки о нехватке: «{humF[2:]}»"))
bodiesF = [str(r["result"]) for r in cF]
res.append(ok(all(MISS not in b for b in bodiesF), "строки о нехватке в карточках НЕТ"))
res.append(ok(all(SIBL in b for b in bodiesF), "соседи названы, как раньше"))
res.append(ok(all(len(sibl_line(b)[len(SIBL):].split(";")) == len(OPS251) - 1 for b in bodiesF),
              "у каждой карточки ровно N-1 соседей"))
res.append(ok(len(fb.sna_calls) == len(OPS251),
              f"лишних правок карточек нет: set_needs_approval вызван {len(fb.sna_calls)} раз"))

fb = setup()
h95 = PLACE(93, CARD95)
c95 = cards_of(fb, 93)
res.append(ok(len(c95) == 1 and h95[1] == "created", "одна операция → прежний путь"))
res.append(ok(str(c95[0]["result"]) == OD._curator_human_render(93, [(CARD95, 1)]),
              "тело БАЙТ-В-БАЙТ равно прежнему рендеру"))

# ============ (5) служебная строка не притворяется пунктом ====================================
print("(5) разбор и конверт:")
fb = setup(enq_fail_from=2)
PLACE(247, CARD251)
c = cards_of(fb, 247)
body = str(c[0]["result"])
res.append(ok(len(OD._curator_human_items(body)) == 1,
              f"в карточке по-прежнему РОВНО один пункт (насчитано {len(OD._curator_human_items(body))})"))
fb.rows[c[0]["id"]]["status"] = "approved"
fb.enq_calls.clear()
OD.process_approved()
conv = next((t for _f, t, _l in fb.enq_calls if t.startswith("[конверт одобренной заявки")), "")
res.append(ok(bool(conv), "конверт поставлен"))
res.append(ok(not any(g in conv.split("Справка")[0] for g in gone),
              "недостающие операции НЕ уехали в ТЗ как работа"))
res.append(ok("NEEDS_APPROVAL" in conv, "красный гейт в ТЗ не ослаблен"))

# ============ (6) отчёт в 328 ================================================================
print("(6) отчёт в 328:")
fb = setup(enq_fail_from=2)
hum6 = PLACE(247, CARD251)
note = hum6[2] if (hum6 and len(hum6) > 2) else ""
res.append(ok("операции БЕЗ карточки" in note, "заметка о нехватке осталась (её читает 328)"))
res.append(ok(NOTE_TOLD in note, f"и сказано, что владельцу это названо: «{note[-90:]}»"))

fb = setup(enq_fail_from=2, sna_fail_calls=(2,))   # карточка встала, а вписать нехватку не вышло
hum7 = PLACE(247, CARD251)
res.append(ok(hum7 is None or hum7[1] == "split", "исход развода не изменился"))
note7 = hum7[2] if (hum7 and len(hum7) > 2) else ""
res.append(ok(NOTE_SILENT in note7,
              f"провал дописи назван громко: «{str(note7)[-110:]}»"))

v = {"verdict": "human", "human": CARD251, "reason": "красное — владельцу", "tasks": []}
card328 = OD._curator_card_text("задача", 300, v, None, hum6)
res.append(ok("⚠️" in card328 and "операции БЕЗ карточки" in card328,
              "тело карточки 328 несёт заметку под знаком внимания"))
try:
    import devbot as DB
    res.append(ok(DB._curator_line(card328) is None,
                  "devbot НЕ ужимает такую карточку в строку (граница 027e280 цела)"))
except Exception as e:
    res.append(ok(False, f"devbot не проверился: {e}"))

# ============ (7) ГРАНИЦЫ ====================================================================
print("(7) границы:")
fb = setup(enq_fail_from=3)
PLACE(247, CARD251)
bodies = [str(r["result"]) for r in cards_of(fb, 247)]
res.append(ok(all(SIGN in b for b in bodies), "подпись 3a95df7 в теле ЦЕЛИКОМ"))
res.append(ok(all(b.rstrip().endswith(SIGN) for b in bodies), "подпись по-прежнему последняя"))
res.append(ok(all(SCOPE in b for b in bodies), "область «да» названа, как раньше"))
res.append(ok(all(len(b) <= OD.RESULT_MAX for b in bodies), "тело в потолке result"))
TOK = ("`", "systemctl", "clasp", "git push", "sqlite3")
res.append(ok(not any(t in MISS for t in TOK), "служебная строка не несёт токенов объекта"))

# длинный пункт: строка о нехватке переживает урезку контекста
fb = setup(enq_fail_from=2)
PLACE(247, CARD251 + (" хвост" * 2000))
bl = [str(r["result"]) for r in cards_of(fb, 247)]
res.append(ok(bl and all(len(b) <= OD.RESULT_MAX for b in bl), "длинный пункт: потолок цел"))
res.append(ok(bl and all(MISS in b for b in bl),
              "длинный пункт: строка о нехватке НЕ срезана (режется справка, а не она)"))
res.append(ok(bl and all(SIGN in b for b in bl), "длинный пункт: подпись на месте"))

# fail-safe прежнего вида: ни одной карточки → прежний путь
fb = setup(enq_fail_from=1)
res.append(ok(PLACE(247, CARD251) is None,
              "ни одна карточка не встала → None, откат на общую карточку (как было)"))
fb = setup(fail_pending=True)
res.append(ok(PLACE(247, CARD251) is None, "очередь не опросить → None (как было)"))

OD.bc = None
print("\nИТОГ: %d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
