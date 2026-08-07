"""ОТРИЦАНИЕ ПРОЧИТАНО КАК ЗАЯВКА (класс карточек 349, 357, 358; 06.08.2026).

ЖИВОЙ ФАКТ, с которого снят регресс (не выдуманный). Read-only снимок очереди Bridge 06.08.2026
(241 задача, все статусы) даёт ЧЕТЫРЕ операционные карточки — всё, что развод пункта на операции
выписал владельцу за свою жизнь:
    348  цель 344  service:orchestrator-daemon  → done   (одобрена, конверт 350 отработал)
    349  цель 344  service:splinter             → failed «отклонено Филиппом (кнопка)»
    357  цель 355  service:splinter             → failed «отклонено Филиппом (кнопка)»
    358  цель 355  service:orchestrator-daemon  → failed «отклонено Филиппом (кнопка)»
Три из четырёх — фантомы. Пункт цели 344 говорил ДОСЛОВНО «…рестарт демона `systemd-run …
systemctl restart orchestrator-daemon` (правило самомодификации, splinter НЕ ТРОГАЕМ)…» — развод
вытащил имя из отрицания. Пункт цели 355 называл оба имени в ОПИСАНИИ ВАРИАНТОВ выбора («какой
вариант … — любой автоматический рестарт splinter/orchestrator-daemon … это красное и без твоего
«да» НЕ ЗАВОДИТСЯ»). Класс тот же, что закрыт для литерала в теле скрипта (40c8425), для имени
секрета в аргументе (05c110b) и правилом исполняющей позиции (5ca761d): решение по совпадению
слова, а не по позиции.

ЗАМЕР (тот же снимок, реплей ЖИВЫМ классификатором `curator_ops` по дословным пунктам ветки
human): за 7 суток 25 пунктов, названо 27 операций, из них ТРИ стоят под отрицанием или в описании
вариантов (splinter в 344; splinter и orchestrator-daemon в 355). Карточек владельцу 33 → 31,
разводов 6 → 4. Ложных демотировок на живом корпусе НОЛЬ.

ЧТО ЗАКРЕПЛЕНО:
  имя под отрицанием действия, под словом запрета или в описании вариантов выбора заявкой НЕ
  является; любая демотировка отменяет РАЗВОД целиком (пункт едет владельцу одной карточкой, как
  до 05.08) и НАЗЫВАЕТСЯ в самой карточке; настоящий пункт с двумя операциями разводится как
  прежде.

ЖИВОЙ ФОРМАТ (класс row705→1268): тексты пунктов — ДОСЛОВНО из снимка очереди (цели 344, 355 и
границы 195, 379, 303 + дословные 251/254/257/95/32 из разведки 05.08); карточки собирает тот же
`_curator_human_place`, что и в проде; конверт — тот же `process_approved`. Сети/claude нет.

Проверки:
 (1) ПРАВИЛО ПОЗИЦИИ на дословных 344/355: имя под отрицанием и в описании вариантов — не заявка;
 (2) ГРАНИЦЫ ПРАВИЛА: настоящие просьбы (в т.ч. «splinter НЕ перезапущен» — состояние, а не отказ)
     остаются заявкой; краткое причастие не путается с личной формой;
 (3) КАРТОЧКИ по дословной 344: карточки на splinter НЕТ, пункт целиком одной карточкой;
 (4) КАРТОЧКИ по дословной 355: две карточки → одна;
 (5) ГРАНИЦА (зелено В ОБОИХ прогонах): настоящий пункт с 2+ операциями разводится КАК ПРЕЖДЕ;
 (6) ГРАНИЦА (зелено В ОБОИХ): одна операция и ноль операций — прежний путь;
 (7) ПОМЕТКА: демотированное имя названо в карточке, переживает повтор и доезжает до ТЗ конверта,
     токенов объекта не несёт, подпись 3a95df7 цела;
 (8) FAIL-SAFE (зелено В ОБОИХ): сбой правила / сбой очереди → прежний путь;
 (9) ОТЧЁТ в 328 называет, что заявкой не сочтено;
 (10) ЧИСТОТА: правило умеет только читать текст (инвариант CURATOR_CLAIM_PURE, ast).
"""
import os, sys, datetime
# Корень берётся ОТ СЕБЯ, а не хардкодом: замер «красный ДО / зелёный ПОСЛЕ» гоняется этим же
# файлом на дереве через `git worktree`, и хардкод пути тянул бы туда боевые модули.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _HERE)
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
# ЛОВУШКА МЕТОДА (названа в артефакте детектора дрейфа, 06.08) — и она СРАБОТАЛА здесь живьём.
# Демон держит REPO ЗАХАРДКОЖЕННЫМ и кладёт его ПЕРВЫМ в sys.path при импорте. Мало вернуть своё
# дерево в начало пути: модуля, которого в дереве НЕТ, интерпретатор не найдёт у себя и спокойно
# возьмёт его из боевого корня ниже по списку — прогон «ДО правки» позеленел бы на коде, которого
# в проверяемом дереве нет вовсе. Поэтому чужой корень УБИРАЕТСЯ, а не оттесняется.
_LIVE = getattr(OD, "REPO", "")
if _LIVE and os.path.abspath(_LIVE) != os.path.abspath(_HERE):
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.abspath(_LIVE)]
sys.path.insert(0, _HERE)

# МОСТ К КОДУ БЕЗ ПРАВКИ: тест обязан быть годен для замера «красный ДО / зелёный ПОСЛЕ», а
# ImportError замером не является (он говорит «модуля нет», а не «поведение другое»). Поэтому
# отсутствие модуля превращается в ЧЕСТНО КРАСНЫЕ проверки, а границы судятся через демона,
# который есть в обоих деревьях.
try:
    import curator_claim
except ImportError:
    curator_claim = None

PLACE = getattr(OD, "_curator_human_place", None) or OD._curator_human_upsert
SIGN = getattr(OD, "_HUMAN_SIGN", "· подписи в коде нет")
NOTCLAIM = getattr(OD, "_HUMAN_NOTCLAIM", "⚠️ пометки «не сочтено заявкой» в коде нет")

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# --- ЖИВОЙ ФОРМАТ: пункты ДОСЛОВНО из снимка очереди 06.08.2026 -------------------------------
# цель 344 (вердикт 347 → карточки 348 ✅ и 349 ❌): имя splinter стоит ПОД ОТРИЦАНИЕМ
GOAL344 = (
    'Шаг 1 цели 344 вернул отчёт без факта — ни MainPID, ни ActiveEnterTimestamp, ни имени '
    'единицы: живёт ли в проде фикс 4a7ef75 (curator_event.py), неизвестно, а повторную проверку '
    'по смыслу дублирует уже отработавшая задача 346; нужно твоё «да» на отложенный рестарт '
    'демона `systemd-run --on-active=10s systemctl restart orchestrator-daemon` (правило '
    'самомодификации, splinter не трогаем), после которого исполнитель назовёт единицу, PID и '
    'время старта и запишет строку в cc_log.')
# цель 355 (вердикт 356 → карточки 357 ❌ и 358 ❌): оба имени в ОПИСАНИИ ВАРИАНТОВ выбора
GOAL355 = (
    'Разбор выкатки закрыт (автоматики нет вовсе; демон 49% недели позади git, splinter 39%; '
    'самый долгий разрыв 34.4 ч закрыт посторонним апгрейдом пакетов). Дальше нужен твой выбор: '
    'какой вариант из предложения ставить в работу — любой автоматический рестарт '
    'splinter/orchestrator-daemon на живых процессах это красное и без твоего «да» не заводится; '
    'вариант «read-only детектор дрейфа без рестарта» тоже требует твоего решения, ставить его '
    'или оставить как есть.')
# ГРАНИЦЫ — настоящие просьбы, у которых отрицание/запрет стоит РЯДОМ (цели 195, 379, 303)
GOAL195 = (
    'Нужны два твоих решения: (1) выкат фикса в прод — коммит d78d5fa (гейт 152 зелёных) лежит в '
    'origin/main, но splinter не перезапущен, рестарт запрещало само ТЗ, значит разрешение на '
    'выкат только твоё; (2) что делать с 6 почти достоверными дублями в живых данных (касса −800 '
    'и −159 THB, 2 задачи очереди, 2 строки «события») — исполнитель их назвал и не чинил, как ты '
    'и велел, плюс 2 случая с неизвестным исходом.')
GOAL379 = (
    'Маршрут находок лежит в git (commit 9f84f3e), но devbot работает внутри процесса bot.py — до '
    'рестарта splinter в проде маршрута НЕТ (ТЗ рестарт прямо запретило, клиентский контур '
    'заморожен): нужно твоё решение — перезапускать splinter, чтобы правка стала живой, или '
    'сознательно оставить её неприменённой до разморозки.')
GOAL303 = (
    'Разделение каналов собрано в коде, но в проде не действует: девбот живёт внутри процесса '
    'splinter, а клиентский контур заморожен — нужно твоё решение, перезапускать ли splinter '
    'сейчас, чтобы сокращение отчётов в 328 и сигнал «очередь пуста» реально заработали (иначе '
    'класс «фикс в git ≠ фикс в проде»).')
# честные пункты с несколькими операциями (разведка 05.08, дословно) — граница «как прежде»
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
    """Очередь в памяти (образец test_curator_split.FakeBridge)."""
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
    pref = f"[куратор владельцу цель {root}"
    return [r for r in sorted(fb.rows.values(), key=lambda x: x["id"])
            if str(r["task_text"]).startswith(pref) and r["status"] == "needs_approval"]


def op_cards(fb, root):
    """Операционные карточки (те, что развод выписывает по одной на операцию)."""
    return [r for r in cards_of(fb, root) if ", операция " in str(r["task_text"])]


def claims(text):
    """Ключи операций, оставшихся ЗАЯВКОЙ, и демотированные семьи. Модуля нет → всё заявка."""
    occs = curator_ops.occurrences(text) if hasattr(curator_ops, "occurrences") else []
    if curator_claim is None or not hasattr(curator_ops, "dedup"):
        return [o["key"] for o in curator_ops.operations(text)], []
    kept, dem = curator_claim.filter_claims(text, occs)
    return [o["key"] for o in curator_ops.dedup(kept)], dem


# =============================== (1) правило позиции ==========================================
print("(1) ПРАВИЛО ПОЗИЦИИ на ДОСЛОВНЫХ пунктах целей 344 и 355:")
k344, d344 = claims(GOAL344)
res.append(ok("service:splinter" not in k344,
              f"344: «splinter не трогаем» заявкой НЕ считается (осталось: {k344})"))
res.append(ok("service:orchestrator-daemon" in k344,
              "344: настоящая просьба про orchestrator-daemon УЦЕЛЕЛА"))
res.append(ok(any(d["key"] == "service:splinter" and "отрицан" in str(d["why"]) for d in d344),
              f"344: причина названа — под отрицанием ({[d.get('why') for d in d344]})"))
k355, d355 = claims(GOAL355)
res.append(ok(k355 == [], f"355: НИ ОДНО имя из описания вариантов не заявка (осталось: {k355})"))
res.append(ok(len(d355) == 2, f"355: демотированы обе семьи (было {len(d355)})"))

# описание вариантов — САМОСТОЯТЕЛЬНЫЙ признак, а не побочный эффект отрицания рядом:
# в 355 сработали оба, поэтому проверяем ветку выбора на том же тексте БЕЗ слов отрицания.
CHOICE_ONLY = GOAL355.replace("и без твоего «да» не заводится", "и решается только тобой")
kc, dc = claims(CHOICE_ONLY)
res.append(ok(kc == [], f"описание вариантов БЕЗ отрицания — тоже не заявка (осталось: {kc})"))
res.append(ok(bool(dc) and all("вариант" in str(d.get("why")) or "выбор" in str(d.get("why"))
                               for d in dc),
              f"причина названа — описание вариантов выбора ({[d.get('why') for d in dc]})"))

# =============================== (2) границы правила ==========================================
print("(2) ГРАНИЦЫ: настоящая просьба остаётся заявкой, даже если отрицание рядом:")
for name, txt, key in (("195 «splinter НЕ перезапущен» (состояние, не отказ)", GOAL195,
                        "service:splinter"),
                       ("379 «ТЗ рестарт прямо запретило» в соседнем обороте", GOAL379,
                        "service:splinter"),
                       ("303 «клиентский контур заморожен» рядом", GOAL303, "service:splinter"),
                       ("95 «в ТЗ рестарт был прямо запрещён»", CARD95, "service:splinter"),
                       ("251 деплой моста", CARD251, "bridge_deploy"),
                       ("254 правка живой ячейки", CARD254, "sheet:I16"),
                       ("257 правка строки события", CARD257, "edit_event")):
    kk, dd = claims(txt)
    res.append(ok(key in kk and not dd, f"{name}: заявка цела (осталось {kk})"))

if curator_claim is not None:
    print("  форма слова после «не» решает, отказ это или состояние:")
    for phrase, expect in (("splinter не трогаем", True),
                           ("splinter не перезапущен", False),
                           ("splinter не заводится", True),
                           ("splinter не перезапускаем", True),
                           ("splinter не тронут", False),
                           ("рестарт splinter нельзя", True)):
        got = curator_claim._negated(phrase)
        res.append(ok(got is expect, f"«{phrase}» → отрицание действия: {got} (ждали {expect})"))
else:
    res.append(ok(False, "правила позиции заявки в коде нет — форму слова судить нечем"))

# =============================== (3) карточки по цели 344 =====================================
print("(3) КАРТОЧКИ ВЛАДЕЛЬЦУ по ДОСЛОВНОМУ пункту цели 344 (было: 348 ✅ и 349 ❌):")
fb = setup()
hum344 = PLACE(344, GOAL344)
c344, o344 = cards_of(fb, 344), op_cards(fb, 344)
res.append(ok(len(o344) == 0, f"операционных карточек НЕТ (было {len(o344)})"))
res.append(ok(len(c344) == 1, f"владельцу ОДНА карточка на весь пункт (было {len(c344)})"))
body344 = str(c344[0]["result"]) if c344 else ""
res.append(ok(not any(", операция service:splinter]" in str(r["task_text"])
                      for r in fb.rows.values()),
              "карточка «перезапуск splinter» не родилась ВООБЩЕ (класс 349)"))
res.append(ok(NOTCLAIM in body344, "карточка НАЗЫВАЕТ, что заявкой не сочтено"))
res.append(ok("splinter" in body344.split(NOTCLAIM)[-1].splitlines()[0] if NOTCLAIM in body344
              else False, "в пометке названо ИМЕННО демотированное имя"))
res.append(ok(GOAL344[:150] in body344, "сам пункт в карточке ДОСЛОВНО — ничего не потеряно"))
res.append(ok(SIGN in body344, "подпись 3a95df7 (что будет после ✅) на месте"))

# =============================== (4) карточки по цели 355 =====================================
print("(4) КАРТОЧКИ ВЛАДЕЛЬЦУ по ДОСЛОВНОМУ пункту цели 355 (было: 357 ❌ и 358 ❌):")
fb = setup()
PLACE(355, GOAL355)
c355, o355 = cards_of(fb, 355), op_cards(fb, 355)
res.append(ok(len(o355) == 0, f"операционных карточек НЕТ (было {len(o355)})"))
res.append(ok(len(c355) == 1, f"владельцу ОДНА карточка (было {len(c355)})"))
b355 = str(c355[0]["result"]) if c355 else ""
res.append(ok(NOTCLAIM in b355 and "splinter" in b355 and "orchestrator-daemon" in b355,
              "оба имени названы пометкой, а не карточками"))

# =============================== (5) ГРАНИЦА: развод как прежде ===============================
print("(5) ГРАНИЦА (зелено В ОБОИХ прогонах): настоящий пункт с 2+ операциями разводится КАК ПРЕЖДЕ:")
fb = setup(); h251 = PLACE(247, CARD251)
res.append(ok(len(op_cards(fb, 247)) == 3, f"251 → 3 операционные карточки "
                                           f"(стало {len(op_cards(fb, 247))})"))
res.append(ok(h251 is not None and h251[1] == "split", f"режим развода (получено {h251 and h251[1]})"))
fb = setup(); PLACE(248, CARD254)
res.append(ok(len(op_cards(fb, 248)) == 3, f"254 → 3 (стало {len(op_cards(fb, 248))})"))
fb = setup(); PLACE(255, CARD257)
res.append(ok(len(op_cards(fb, 255)) == 2, f"257 → 2 (стало {len(op_cards(fb, 255))})"))
fb = setup(); PLACE(262, CARD251)
bodies = [str(r["result"]) for r in op_cards(fb, 262)]
res.append(ok(all(NOTCLAIM not in b for b in bodies),
              "у честного развода пометки «не сочтено» НЕТ — путь байт-в-байт прежний"))

# =============================== (6) ГРАНИЦА: одна и ноль операций ============================
print("(6) ГРАНИЦА (зелено В ОБОИХ): одна операция и ноль операций — прежний путь:")
fb = setup(); h95 = PLACE(93, CARD95)
c95 = cards_of(fb, 93)
res.append(ok(len(c95) == 1 and not op_cards(fb, 93), "95 — одна общая карточка, как раньше"))
res.append(ok(str(c95[0]["result"]) == OD._curator_human_render(93, [(CARD95, 1)]),
              "тело БАЙТ-В-БАЙТ равно прежнему рендеру (пометки нет)"))
fb = setup(); PLACE(30, CARD32)
c32 = cards_of(fb, 30)
res.append(ok(len(c32) == 1, "пункт без операций — общая карточка, как раньше"))
res.append(ok(str(c32[0]["result"]) == OD._curator_human_render(30, [(CARD32, 1)]),
              "тело чистого решения не изменилось ни на символ"))

# =============================== (7) пометка: повтор, конверт, объекты ========================
print("(7) ПОМЕТКА живёт при повторе, доезжает до ТЗ и не подсовывает объект:")
fb = setup()
PLACE(344, GOAL344)
PLACE(344, GOAL344)
c = cards_of(fb, 344)
res.append(ok(len(c) == 1, f"второй карточки нет (карточек {len(c)})"))
items = OD._curator_human_items(str(c[0]["result"])) if c else []
res.append(ok(len(items) == 1 and items[0][1] == 2,
              f"тот же пункт → ×2 на том же пункте (получено {[(t[:20], n) for t, n in items]})"))
res.append(ok(str(c[0]["result"]).count(NOTCLAIM) == 1,
              "пометка не размножилась при повторе"))
res.append(ok(NOTCLAIM in items[0][0] if items else False,
              "пометка склеена С ПУНКТОМ (переживает пересборку тела карточки)"))

try:
    import devbot
    objs = devbot._card_objects(str(c[0]["result"]))
    bad = [o for o in objs if "splinter" in str(o).lower() and "systemctl" not in str(o).lower()]
    res.append(ok(not bad, f"пометка не подсунула devbot объект сверки: {objs}"))
except Exception as e:
    res.append(ok(False, f"devbot._card_objects не проверен ({e})"))

fb = setup()
PLACE(344, GOAL344)
tgt = cards_of(fb, 344)[0]
fb.rows[tgt["id"]]["status"] = "approved"
fb.enq_calls.clear()
OD.process_approved()
convs = [t for _f, t, _l in fb.enq_calls if t.startswith("[конверт одобренной заявки")]
res.append(ok(len(convs) == 1, f"✅ → РОВНО один конверт (было {len(convs)})"))
tz = convs[0] if convs else ""
res.append(ok("splinter не трогаем" in tz, "пункт доехал до ТЗ ДОСЛОВНО, вместе с отрицанием"))
res.append(ok(NOTCLAIM in tz, "исполнитель видит, что имя заявкой не сочтено"))
res.append(ok("NEEDS_APPROVAL" in tz, "красный гейт в ТЗ не ослаблен"))

# =============================== (8) fail-safe ================================================
print("(8) FAIL-SAFE (зелено В ОБОИХ): сбой правила и сбой очереди → прежний путь:")
if curator_claim is not None:
    saved = curator_claim.filter_claims
    curator_claim.filter_claims = lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("бум"))
    try:
        fb = setup()
        h = PLACE(247, CARD251)
        res.append(ok(h is not None and len(cards_of(fb, 247)) >= 1,
                      "правило упало → карточка владельцу всё равно встала"))
    finally:
        curator_claim.filter_claims = saved
else:
    res.append(ok(True, "правила нет — падать нечему, путь прежний"))
fb = setup(); fb.fail_pending = True
res.append(ok(PLACE(344, GOAL344) is None, "очередь не опрашивается → None (прежний исход)"))
fb = setup(); fb.fail_enqueue = True
res.append(ok(PLACE(344, GOAL344) is None, "enqueue не встаёт → None, карточек не плодим"))

# =============================== (9) отчёт в 328 ==============================================
print("(9) ОТЧЁТ в 328 называет, что заявкой не сочтено:")
fb = setup()
h = PLACE(344, GOAL344)
note = h[2] if (h and len(h) > 2) else ""
res.append(ok(bool(note) and "splinter" in str(note),
              f"отчёт называет демотированное имя: {str(note)[:80]}"))
card = OD._curator_card_text("задача", 346,
                             {"verdict": "human", "human": GOAL344, "reason": "тест"}, None, h)
res.append(ok("⚠️" in card and "splinter" in card,
              "карточка-сигнал 328 несёт заметку (devbot отдаст её отдельным сообщением)"))

# =============================== (10) чистота правила =========================================
print("(10) ЧИСТОТА: правило умеет ТОЛЬКО читать текст:")
try:
    import invariants_check as IC
    names = [n for n, _f in IC.CHECKS] if hasattr(IC, "CHECKS") else list(IC.REGISTRY)
    res.append(ok("CURATOR_CLAIM_PURE" in names, f"инвариант в реестре: {'CURATOR_CLAIM_PURE' in names}"))
    run = IC.CheckRun("CURATOR_CLAIM_PURE")
    IC.check_curator_claim_pure({}, run)
    res.append(ok(not run.findings, f"боевой curator_claim.py чист: {run.findings[:2]}"))
    # Страж обязан КРАСНЕТЬ на руках, иначе он декорация: подсовываем модуль, который лезет в мир.
    # Путь — ЛИТЕРАЛ под /tmp: уборка своего черновика по названному литералу зелёная, а
    # tempfile-имя через атрибут гард разрешить не может и честно краснеет (класс 03.08).
    dirty = "/tmp/tb_curator_claim_dirty_fixture.py"
    with open(dirty, "w", encoding="utf-8") as f:
        f.write("import os\ndef claims(t):\n    os.remove('/tmp/x')\n    return t\n")
    IC._CURATOR_CLAIM_PATH = dirty
    run2 = IC.CheckRun("CURATOR_CLAIM_PURE")
    IC.check_curator_claim_pure({}, run2)
    IC._CURATOR_CLAIM_PATH = None
    os.remove("/tmp/tb_curator_claim_dirty_fixture.py")
    res.append(ok(bool(run2.findings), f"страж краснеет, если у правила появились руки: "
                                       f"{run2.findings[:2]}"))
except Exception as e:
    res.append(ok(False, f"инвариант чистоты не проверен ({e})"))

print(f"\nИТОГ: {sum(res)}/{len(res)}")
sys.exit(0 if all(res) else 1)
