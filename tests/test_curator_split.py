"""ОДНА КАРТОЧКА = ОДНА ОПЕРАЦИЯ И В КУРАТОРСКОЙ СВОДКЕ (класс карточек 251, 254, 257; 05.08.2026).

ЖИВОЙ ФАКТ, с которого снят регресс (не выдуманный). Read-only разведка очереди Bridge 05.08.2026
(снимок всех статусов, 171 задача) дала 19 сводных карточек владельцу за 14 суток. Карточки 251 и
254 просили под ОДНИМ «да» деплой моста ВМЕСТЕ с двумя правками живых данных, 257 — деплой вместе
с пробой правки. Правило «одна карточка = одна операция» у карточек гарда закрыто давно, а здесь
операции разного веса стояли одним списком. Цена: 251 и 254 владелец отклонил кнопкой ЦЕЛИКОМ
(result «отклонено Филиппом (кнопка)»), и вся готовая работа пункта умерла — её собирали заново.

ЗАМЕР (тот же снимок, классификатор — боевой `curator_ops`): больше одной операции несли 4
карточки (251, 254, 257, 264), из них владелец отклонил 2 (251, 254). Ровно одну операцию — 10,
ни одной — 5. Отдельный факт из журнала демона: за те же 14 суток «создана сводная карточка» 17
раз, «пункт добавлен»/«пункт уже был» — НИ РАЗУ, то есть НИ ОДНА карточка не копила больше одного
пункта: склейка операций жила ВНУТРИ текста одного пункта, а не между пунктами. Поэтому делит
правка именно текст пункта.

ЧТО ЗАКРЕПЛЕНО:
  пункт, назвавший ДВЕ и более операции, разводится по карточкам — по одной на операцию;
  пункт с одной операцией и пункт без операций идут прежним путём БАЙТ-В-БАЙТ.

ЖИВОЙ ФОРМАТ (класс row705→1268): тексты пунктов — ДОСЛОВНО task_text боевых карточек 95, 251,
254, 257 и 264 из той разведки; тело карточки собирается тем же `_curator_human_render`, что и в
проде; конверт — тем же `process_approved`. Сети/claude нет — мост подменён.

Проверки:
 (1) классификатор на дословных текстах: 251/254/257 — больше одной операции, 95 — ровно одна,
     чистое решение (32 — ни одной);
 (2) карточка 251 дословно → ТРИ карточки, по одной на операцию, у каждой свой маркер-ключ;
 (3) карточка 254 дословно → ТРИ карточки; 257 дословно → ДВЕ;
 (4) в каждой операционной карточке ОДИН пункт, названа своя операция, соседи названы отдельно,
     а текст куратора приехал контекстом ДОСЛОВНО;
 (5) карточка с ОДНОЙ операцией (95) работает как прежде: одна карточка, прежний маркер,
     тело БАЙТ-В-БАЙТ равно прежнему рендеру;
 (6) дедуп: тот же пункт второй раз → ×N на тех же карточках, а не второй комплект;
 (7) FAIL-SAFE: очередь не опрашивается / enqueue не встаёт → откат на ПРЕЖНИЙ путь (общая
     карточка), «да» владельца не теряется;
 (8) конверт операционной карточки: ✅ → ТЗ несёт ОДНУ операцию, справку-контекст и ПРЯМОЙ
     запрет делать соседние операции;
 (9) ГРАНИЦЫ: подпись 3a95df7 не ослаблена (в теле операционной карточки она целиком), а
     служебные строки развода не несут токенов объекта;
 (10) словарь операций не разойдётся молча: каждое имя write-действия из боевого
      `pretool_guard.RED_TOKEN_HIT` классификатор узнаёт;
 (11) совместимость маркера: старая карточка читается как раньше, а общий upsert НЕ подхватывает
      операционные карточки (иначе пункты «к сведению» приклеились бы к операции);
 (12) дайджест devbot видит операционные карточки как «ждёт владельца».
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

# МОСТ К КОДУ БЕЗ ПРАВКИ. Тест обязан быть годен для замера «красный ДО / зелёный ПОСЛЕ», а
# AttributeError на старом коде замером не является: он говорит «функции нет», а не «поведение
# другое». Поэтому на старом коде тест падает ПРОВЕРКАМИ — прежний путь честно кладёт все
# операции в ОДНУ карточку под одним «да», и это видно числом.
PLACE = getattr(OD, "_curator_human_place", None) or OD._curator_human_upsert
SCOPE = getattr(OD, "_HUMAN_SCOPE", "· строки области «да» в коде нет")
SIBL = getattr(OD, "_HUMAN_SIBL", "· строки соседей в коде нет")
CTX = getattr(OD, "_HUMAN_CTX", "· строки контекста в коде нет")

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# --- ЖИВОЙ ФОРМАТ: пункты боевых карточек ДОСЛОВНО (разведка очереди 05.08.2026) --------------
CARD251 = (
    "Нужен владелец на красное: (1) деплой моста — `clasp push` + `clasp redeploy` "
    "прод-deploymentId (до него edit_event в проде отвечает unknown_action, эффект кода живым "
    "фактом НЕ доказан — FACT-блока в итоге нет); (2) после деплоя на живом случае NMAX 155 "
    "GREEN-B 4957 — правка строки событий 29.07 09:32:15 (38982→36982) и понижение Лист1 I16 "
    "37000→36982 веткой «исправление ошибки», каждое по отдельн")
CARD254 = (
    "Нужен деплой моста и живая проверка: из /root/turbobaby-bridge-gs `clasp push` + "
    "`clasp redeploy` прод-deploymentId (красная зона — только владелец; учесть предупреждение о "
    "`clasp pull`, локальное впереди прода), затем смок на живом случае NMAX 155 GREEN-B 4957 — "
    "правка строки 29.07 09:32:15 (38982→36982) и понижение I16 37000→36982 веткой «исправление "
    "ошибки». До деплоя прод-мост отвечает `unknow")
CARD257 = (
    "Деплой моста НЕ выкачен — папка /root/turbobaby-bridge-gs позади прода @76 (ротация "
    "cowork_log 29.07 есть в проде, в папке нет; push стёр бы её). Нужно «да» владельца на "
    "красный дожим: вытянуть прод в ОТДЕЛЬНУЮ папку, наложить локальный дифф (edit_event + ветка "
    "исправления пробега) и оттуда clasp push + redeploy прод-deploymentId, затем проба "
    "edit_event на ТЕСТ-сущности и обновление пина. Отдельно")
CARD95 = (
    "Нужно явное «да» владельца на `systemctl restart splinter`: фикс одометра (корни 1 и 2, "
    "commit bbbe458) уже в origin/main и зелёный по гейту (142 теста) и по живому регрессу 4957 "
    "(6/9 красных → 9/9 зелёных), но в проде НЕ действует, пока сервис работает на старом коде — "
    "в ТЗ рестарт был прямо запрещён до отдельного разрешения с названным объектом.")
CARD32 = (
    "Реши, чья реализация минимума красной карточки живёт: ПК-коммит 17221f2 "
    "(`_detail_parts`/`card_min`) или уже стоящий на VPS непушнутый e4e6e2b (`_facts`/`card_due`) "
    "— они конфликтуют в живом гарде (merge-tree exit 1), и без твоего решения выкатка "
    "невозможна: pull ломает хук, reset стирает работу сервера.")


class FakeBridge:
    """Очередь в памяти (образец test_curator_human_exec.FakeBridge) + журнал enqueue."""
    def __init__(s):
        s.rows, s.nid = {}, 400
        s.fail_enqueue = False
        s.fail_pending = False
        s.enq_calls = []
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
        if s.fail_enqueue:
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}
    def set_needs_approval(s, tid, what):
        r = s.rows.get(int(tid))
        if not r: return {"ok": False, "error": "not_found"}
        r["status"], r["result"] = "needs_approval", what
        return {"ok": True}
    def task_heartbeat(s, tid): return {"ok": True}
    def log_write(s, **kw): return {"ok": True}


OD._restart_pending = lambda: False


def setup():
    fb = FakeBridge()
    OD.bc = fb
    return fb


def cards_of(fb, root):
    """Открытые карточки владельцу по цели root (любые: общая и операционные)."""
    pref = f"[куратор владельцу цель {root}"
    return [r for r in sorted(fb.rows.values(), key=lambda x: x["id"])
            if str(r["task_text"]).startswith(pref) and r["status"] == "needs_approval"]


# =============================== (1) классификатор ===========================================
print("(1) классификатор на ДОСЛОВНЫХ боевых текстах:")
k251 = [o["key"] for o in curator_ops.operations(CARD251)]
k254 = [o["key"] for o in curator_ops.operations(CARD254)]
k257 = [o["key"] for o in curator_ops.operations(CARD257)]
k95 = [o["key"] for o in curator_ops.operations(CARD95)]
k32 = [o["key"] for o in curator_ops.operations(CARD32)]
res.append(ok(len(k251) >= 2, f"251 несёт больше одной операции: {k251}"))
res.append(ok(len(k254) >= 2, f"254 несёт больше одной операции: {k254}"))
res.append(ok(len(k257) >= 2, f"257 несёт больше одной операции: {k257}"))
res.append(ok("bridge_deploy" in k251 and "bridge_deploy" in k254 and "bridge_deploy" in k257,
              "деплой моста опознан во всех трёх"))
res.append(ok("edit_event" in k251 and "edit_event" in k254 and "edit_event" in k257,
              "правка строки события опознана во всех трёх"))
res.append(ok("sheet:I16" in k251 and "sheet:I16" in k254,
              "живая ячейка I16 опознана в 251 и 254"))
res.append(ok(k95 == ["service:splinter"], f"95 — РОВНО одна операция: {k95}"))
res.append(ok(k32 == [], f"32 (чистое решение) — операций не названо: {k32}"))
res.append(ok(k251.count("bridge_deploy") == 1,
              "`clasp push` + `clasp redeploy` = ОДИН выкат моста, а не два"))
res.append(ok(not any(k.startswith("service") for k in k254),
              "`clasp pull` и слово «прод» сервисом не притворились"))

# =============================== (2)(3)(4) развод ============================================
print("(2) карточка 251 дословно → карточка на КАЖДУЮ операцию:")
fb = setup()
hum = PLACE(247, CARD251)
c251 = cards_of(fb, 247)
res.append(ok(hum is not None and hum[1] == "split", f"режим развода (получено {hum and hum[1]})"))
res.append(ok(len(c251) == 3, f"карточек ровно 3 (было {len(c251)})"))
marks = [str(r["task_text"]).split("]")[0] + "]" for r in c251]
res.append(ok(len(set(marks)) == 3, f"маркеры РАЗНЫЕ: {marks}"))
res.append(ok(all(", операция " in m for m in marks), "каждый маркер несёт ключ операции"))

print("(3) карточки 254 и 257 дословно:")
fb = setup(); PLACE(248, CARD254)
res.append(ok(len(cards_of(fb, 248)) == 3, f"254 → 3 карточки (было {len(cards_of(fb, 248))})"))
fb = setup(); PLACE(255, CARD257)
c257 = cards_of(fb, 255)
res.append(ok(len(c257) == 2, f"257 → 2 карточки (было {len(c257)})"))

print("(4) что владелец видит в операционной карточке:")
fb = setup(); PLACE(247, CARD251)
c251 = cards_of(fb, 247)
bodies = [str(r["result"]) for r in c251]
res.append(ok(all(len(OD._curator_human_items(b)) == 1 for b in bodies),
              "в каждой карточке РОВНО один пункт"))
res.append(ok(all("ОПЕРАЦИЯ " in b and " из 3" in b for b in bodies),
              "заголовок называет номер операции из общего числа"))
res.append(ok(all(SCOPE in b for b in bodies),
              "сказано, что «да» покрывает только эту операцию"))
res.append(ok(all(SIBL in b for b in bodies), "соседние операции названы отдельно"))
res.append(ok(all(CTX in b for b in bodies), "контекст пункта приехал"))
ctx_line = next((ln for ln in bodies[0].splitlines() if ln.startswith(CTX)), "")
res.append(ok(CARD251[:180] in ctx_line, "текст куратора в контексте ДОСЛОВНО"))
labels = [OD._curator_human_items(b)[0][0] for b in bodies]
res.append(ok(len(set(labels)) == 3, f"пункты карточек РАЗНЫЕ (по операции на карточку): {labels}"))
res.append(ok(any("clasp push" in l for l in labels), "литерал куратора виден в пункте"))

# =============================== (5) одна операция — как прежде ==============================
print("(5) карточка с ОДНОЙ операцией (95) — прежний путь байт-в-байт:")
fb = setup()
hum95 = PLACE(93, CARD95)
c95 = cards_of(fb, 93)
res.append(ok(len(c95) == 1, f"карточка ровно одна (было {len(c95)})"))
res.append(ok(hum95[1] == "created", f"режим прежний (получено {hum95[1]})"))
res.append(ok(str(c95[0]["task_text"]).startswith("[куратор владельцу цель 93] "),
              "маркер БЕЗ хвоста операции — как раньше"))
res.append(ok(str(c95[0]["result"]) == OD._curator_human_render(93, [(CARD95, 1)]),
              "тело БАЙТ-В-БАЙТ равно прежнему рендеру"))
fb = setup(); PLACE(30, CARD32)
res.append(ok(len(cards_of(fb, 30)) == 1, "пункт без операций — общая карточка, как раньше"))

# =============================== (6) дедуп ===================================================
print("(6) повтор того же пункта:")
fb = setup()
PLACE(247, CARD251)
PLACE(247, CARD251)
c = cards_of(fb, 247)
res.append(ok(len(c) == 3, f"второго комплекта карточек НЕТ (карточек {len(c)})"))
res.append(ok(all(OD._curator_human_items(str(r["result"]))[0][1] == 2 for r in c),
              "на каждой карточке счётчик ×2, а не дубль пункта"))

# =============================== (7) fail-safe ===============================================
print("(7) FAIL-SAFE — не хуже прежнего:")
fb = setup(); fb.fail_pending = True
h = PLACE(247, CARD251)
res.append(ok(h is None, "очередь не опрашивается → None (прежний исход upsert), карточек не плодим"))
fb = setup(); fb.fail_enqueue = True
h = PLACE(247, CARD251)
res.append(ok(h is None, "enqueue не встаёт → откат на прежний путь, тот же исход что и раньше"))


class HalfBridge(FakeBridge):
    """Первая карточка встаёт, остальные — нет: частичный сбой развода."""
    def enqueue_task(s, frm, text, lane=None, dedup_key=None):
        s.enq_calls.append((frm, text, lane))
        if len(s.enq_calls) > 1:
            return {"ok": False, "error": "request_failed"}
        return {"ok": True, "id": s.add("new", text, frm=frm)}


fb = HalfBridge(); OD.bc = fb
h = PLACE(247, CARD251)
res.append(ok(h is not None and h[1] == "split", "часть карточек встала — развод не откатывается"))
note = h[2] if (h and len(h) > 2) else ""
res.append(ok(bool(note), f"НЕвставшие операции названы в отчёте: {str(note)[:70]}"))

# =============================== (8) конверт =================================================
print("(8) конверт операционной карточки:")
fb = setup()
PLACE(247, CARD251)
c = cards_of(fb, 247)
target = c[0]
fb.rows[target["id"]]["status"] = "approved"
fb.enq_calls.clear()
OD.process_approved()
res.append(ok(fb.rows[target["id"]]["status"] == "done", "карточка закрыта done"))
convs = [t for _f, t, _l in fb.enq_calls if t.startswith("[конверт одобренной заявки")]
res.append(ok(len(convs) == 1, f"РОВНО один конверт (было {len(convs)})"))
tz = convs[0] if convs else ""
res.append(ok("Соседние операции того же пункта сюда НЕ входят" in tz,
              "ТЗ прямо запрещает делать соседние операции"))
res.append(ok("Справка — пункт куратора дословно:" in tz, "контекст приехал справкой"))
res.append(ok(tz.count("clasp push") >= 1, "одобренная операция названа"))
res.append(ok("NEEDS_APPROVAL" in tz, "красный гейт в ТЗ не ослаблен"))

# длинная справка не должна съесть хвост ТЗ (класс «режем справку, а не дисциплину»)
fb = setup()
PLACE(247, CARD251 + (" хвост" * 2000))
c = cards_of(fb, 247)
fb.rows[c[0]["id"]]["status"] = "approved"
fb.enq_calls.clear()
OD.process_approved()
tzl = next((t for _f, t, _l in fb.enq_calls if t.startswith("[конверт")), "")
res.append(ok(len(tzl) <= OD.RESULT_MAX, "длинная справка: ТЗ в потолке"))
res.append(ok("NEEDS_APPROVAL" in tzl, "длинная справка: запрет красного в ТЗ ВЫЖИЛ"))
res.append(ok("Соседние операции того же пункта сюда НЕ входят" in tzl,
              "длинная справка: запрет соседних операций выжил"))

# =============================== (9) границы =================================================
print("(9) границы: фикс 3a95df7 и токены объекта:")
fb = setup(); PLACE(247, CARD251)
bodies = [str(r["result"]) for r in cards_of(fb, 247)]
res.append(ok(all(OD._HUMAN_SIGN in b for b in bodies),
              "подпись 3a95df7 в теле ЦЕЛИКОМ — обещание исхода не ослаблено"))
res.append(ok(all(b.rstrip().endswith(OD._HUMAN_SIGN) for b in bodies),
              "подпись по-прежнему последняя (тело режется под неё)"))
res.append(ok(all(len(b) <= OD.RESULT_MAX for b in bodies), "тело в потолке result"))
TOK = ("`", "systemctl", "clasp", "git push", "sqlite3")
res.append(ok(not any(t in SCOPE or t in SIBL for t in TOK),
              "служебные строки развода не несут токенов объекта"))

# длинный пункт: контекст режется, а пункт и подпись выживают
LONG = CARD251 + (" хвост" * 2000)
fb = setup(); PLACE(247, LONG)
bodies = [str(r["result"]) for r in cards_of(fb, 247)]
res.append(ok(bodies and all(len(b) <= OD.RESULT_MAX for b in bodies), "длинный пункт: потолок цел"))
res.append(ok(all(OD._HUMAN_SIGN in b for b in bodies), "длинный пункт: подпись на месте"))
res.append(ok(all(len(OD._curator_human_items(b)) == 1 for b in bodies),
              "длинный пункт: сам пункт не съеден урезкой контекста"))

# контекст не притворяется пунктом: строка «1. …» внутри текста куратора
TRICK = "Нужен деплой: `clasp push` и рестарт splinter.\n1. поддельный пункт\n2. ещё один"
fb = setup(); PLACE(247, TRICK)
bodies = [str(r["result"]) for r in cards_of(fb, 247)]
res.append(ok(bodies and all(len(OD._curator_human_items(b)) == 1 for b in bodies),
              "нумерованная строка внутри контекста пунктом НЕ становится"))

# =============================== (10) словарь не разойдётся ==================================
print("(10) словарь операций против молчаливого расхождения:")
try:
    import pretool_guard as PG
    names = [k for k, v in PG.RED_TOKEN_HIT.items() if v not in ("DOWRITE", "confirmed")]
    miss = [n for n in names if not curator_ops.operations(f"нужно {n} по байку")]
    res.append(ok(not miss, f"все write-действия гарда узнаются (не узнано: {miss})"))
except Exception as e:
    res.append(ok(False, f"страж словаря не отработал: {e}"))

# =============================== (11) совместимость маркера ==================================
print("(11) совместимость маркера:")
m_old = OD._CURATOR_HUMAN_RE.match("[куратор владельцу цель 93] пункт")
m_new = OD._CURATOR_HUMAN_RE.match("[куратор владельцу цель 93, операция bridge_deploy] пункт")
def _grp(m, i):
    """group(i) без падения: у маркера ДО правки второй группы нет вовсе — это FAIL проверки,
    а не обвал прогона (иначе замер «красный до» превращается в traceback)."""
    try:
        return m.group(i)
    except Exception:
        return None


res.append(ok(bool(m_old) and _grp(m_old, 1) == "93" and not _grp(m_old, 2),
              "старый маркер читается как раньше"))
res.append(ok(bool(m_new) and _grp(m_new, 1) == "93" and _grp(m_new, 2) == "bridge_deploy",
              "новый маркер отдаёт цель и ключ операции"))
fb = setup(); PLACE(247, CARD251)
n_before = len(cards_of(fb, 247))
PLACE(247, "просто прими к сведению: зеркало ПК-полосы не сделано")
after = cards_of(fb, 247)
res.append(ok(len(after) == n_before + 1,
              f"пункт «к сведению» встал СВОЕЙ общей карточкой (было {n_before}, стало {len(after)})"))
gen = [r for r in after if str(r["task_text"]).startswith("[куратор владельцу цель 247] ")]
res.append(ok(len(gen) == 1 and "к сведению" in str(gen[0]["result"]),
              "общий upsert НЕ приклеил пункт к операционной карточке"))

# =============================== (12) дайджест devbot ========================================
print("(12) дайджест devbot видит операционные карточки:")
try:
    import devbot as DB
    mm = DB._CURATOR_HUMAN_RE.match("[куратор владельцу цель 247, операция bridge_deploy] x")
    res.append(ok(bool(mm) and mm.group(1) == "247",
                  "devbot считает операционную карточку ожиданием владельца"))
except Exception as e:
    res.append(ok(False, f"devbot не проверился: {e}"))

OD.bc = None
print("\nИТОГ: %d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
