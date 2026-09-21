"""ОДИН ОБЪЕКТ — ОДИН ВОПРОС: ДЕДУП МЕЖДУ ДВЕРЬМИ ОДОБРЕНИЯ (22.08.2026).

ПОВОД, ИЗМЕРЕННЫЙ ЖИВЫМ ЧТЕНИЕМ ЖУРНАЛА ДЕМОНА. У владельца две двери, через которые приходит
вопрос «перезапустить прод ради этого коммита?»: сводная карточка куратора и карточка доставки
пути C. Они не знают друг о друге ничем, и 14.08 это стоило владельцу двух лишних карточек:

    18:02:16  curator-state: пункт цели 559 … (не состоялось: прибор: в проде не живёт b5478ce)
    22:09:13  ДОСТАВКА: коммит b5478ce не доехал до splinter → карточка 565 владельцу
    18:25:44  curator-state: пункт цели 562 … (не состоялось: прибор: в проде не живёт baf5d30)
    22:24:35  ДОСТАВКА: коммит baf5d30 не доехал до splinter → карточка 566 владельцу

Δ = 4.12 ч и 3.98 ч, порядок ОБА раза «куратор → доставка». Пар за окно замера (10.08 19:30 —
21.08 20:38) РОВНО ДВЕ и других нет: коммитов у двери доставки 9, у двери куратора 3, пересечение
— ровно эти два. Все четыре карточки обогнал ОДИН ручной перезапуск splinter 15.08 03:14:40.

КАНОН МЕТРИКИ ЗДЕСЬ НЕ СУДИТСЯ И НЕ ТРОГАЕТСЯ: сорт вмешательства по-прежнему считает
`chain_series.sort_card` ПО ОПЕРАЦИИ (решение владельца 22.08). Меняется не то, КАК считают
карточки, а то, СКОЛЬКО их рождается.

Проверки:
 (1) КЛЮЧ УСТОЙЧИВ: тот же объект через сутки, через рестарт и через пересоздание очереди даёт
     ТОТ ЖЕ ключ; неназванное (пустая операция, `service:?`, пустой предмет) ключа не даёт вовсе;
 (2) ЧИСТОЕ РЕШЕНИЕ: импортов НОЛЬ, рук нет, страж ASK_LEDGER_PURE краснеет на грязном модуле;
 (3) П.4-А ОТРИЦАТЕЛЬНЫЙ: две карточки по РАЗНЫМ объектам — доходят ОБЕ (прогон дословно);
 (4) П.4-Б ОТРИЦАТЕЛЬНЫЙ: две по ОДНОМУ — вторая до владельца НЕ доходит, счётчик дедупа растёт
     (прогон дословно);
 (5) П.5 ТОТ ЖЕ ОБЪЕКТ, ДРУГАЯ ОПЕРАЦИЯ — вопрос НЕ проглатывается;
 (6) ЖИВОЙ СЛУЧАЙ 14.08 в обе стороны: куратор→доставка и доставка→куратор;
 (7) ОТВЕТ УЖЕ ПОЛУЧЕН: терминал карточки кладёт ответ в реестр, вторая дверь называет его словом
     и номером — и НЕ исполняет ничего;
 (8) FAIL-SAFE В СТОРОНУ ВОПРОСА: реестр не прочитан · запись старше окна · покрыта лишь ЧАСТЬ
     ключей · карточка без операции · карточка без коммита → спрашиваем, как спрашивали;
 (9) ГРАНИЦЫ: ASK_DEDUP=0 — байт-в-байт прежнее; файл счёта серии не тронут ни на байт; словари
     `curator_ops`/`chain_series` не изменены; сам дедуп не делает НИ ОДНОГО обращения к мосту.
"""
import ast
import datetime
import hashlib
import json
import os
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"     # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CURATOR_STATE"] = "0"     # сверка с прибором — предмет соседнего сьюта, здесь не она
os.environ["DELIVER_CARD"] = "1"
os.environ["ASK_DEDUP"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"
LEDGER = "/tmp/cc_ask_ledger_selftest.json"
DELIVER_DIR = "/tmp/cc_ask_dedup_deliver_state"
os.environ["CC_ASK_LEDGER_FILE"] = LEDGER
os.environ["CC_DELIVER_DIR"] = DELIVER_DIR

REPO = "/root/turbobaby-manager-bot"


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return c


res = []

import ask_ledger                       # noqa: E402
import chain_cards                      # noqa: E402
import curator_ops                      # noqa: E402
import curator_state                    # noqa: E402
import scan_result                      # noqa: E402
import invariants_check                 # noqa: E402
import orchestrator_daemon as OD        # noqa: E402

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# ДОСЛОВНЫЕ тексты пунктов живого вида (форма пункта 559/562: операция + коммит в одной строке).
ITEM_SPLINTER_B = ("Нужно твоё «да» на перезапуск splinter (`systemctl restart splinter`): "
                   "коммит b5478ce лежит в origin/main, но в проде не живёт — код держится в "
                   "памяти процесса.")
ITEM_SPLINTER_BAF = ("Нужно твоё «да» на перезапуск splinter (`systemctl restart splinter`): "
                     "коммит baf5d30 лежит в origin/main, но в проде не живёт.")
ITEM_DAEMON_B = ("Нужно твоё «да» на отложенный рестарт orchestrator-daemon (`systemd-run "
                 "--on-active=10s systemctl restart orchestrator-daemon`) ради коммита b5478ce.")
ITEM_DECISION = ("Нужно твоё решение: какую единицу метрики считать за вмешательство — карточку "
                 "или цепочку. Коммит 5feebf9 это не меняет.")


# ═══════════════════════════ ОБЩИЙ СТЕНД ═══════════════════════════════════════════════════
def reset(led=None):
    """Реестр в исходное. НИЧЕГО НЕ УДАЛЯЕМ — перезаписываем (запрет захода на удаление)."""
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(led if led is not None else ask_ledger.empty(), f, ensure_ascii=False)
    os.makedirs(DELIVER_DIR, exist_ok=True)
    with open(os.path.join(DELIVER_DIR, "asked.json"), "w", encoding="utf-8") as f:
        json.dump({"asked": {}}, f)
    OD._deliver_next = 0.0
    OD._CARD_ENDED.clear()


def ledger():
    with open(LEDGER, encoding="utf-8") as f:
        return json.load(f)


class FakeBridge:
    """Очередь в памяти + счётчик ЛЮБОГО обращения (образец test_deliver_card.FakeBridge)."""

    def __init__(s, rows=None):
        s.rows, s.nid, s.calls = dict(rows or {}), 900, []

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
        if int(tid) in s.rows:
            s.rows[int(tid)]["status"] = status
        return {"ok": True}

    def cards(s):
        """Что владелец РЕАЛЬНО увидит: строки, доведённые до needs_approval."""
        return [r["id"] for r in s.rows.values() if r["status"] == "needs_approval"]


class Facts:
    """Факты доставки ТОЙ ЖЕ ФОРМЫ, что собирает рука наблюдателя (образец test_deliver_card)."""

    def __init__(s, sha, unit="splinter", files=("splinter.py",)):
        s.sha, s.unit, s.files = sha, unit, list(files)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        s.ct = now - 5 * 3600.0
        mts = [os.stat(os.path.join(REPO, f)).st_mtime
               for f in s.files if os.path.exists(os.path.join(REPO, f))]
        s.started = min([s.ct] + mts) - 60.0        # процесс СТАРШЕ коммита → «не доставлен»

    def commits_since(s, ts, repo=None):
        return [{"sha": s.sha, "ct": int(s.ct), "subject": "фикстура доставки", "files": s.files}]

    def closure(s, entry, repo=None):
        return set([entry] + s.files) if entry == _entry_of(s.unit) else {entry}

    def live(s, unit, entry, proc=None, repo=None):
        return {"pid": 1234, "started": s.started}

    def dirty_files(s):
        return scan_result.ScanResult(scanned=0, parsed=0,
                                      subject="файлов расхождения с origin/main", payload=[])


def _entry_of(unit):
    for u, e in OD.prod_drift.WATCHED:
        if u == unit:
            return e
    return "orchestrator_daemon.py"


def deliver(sha, unit="splinter", files=("splinter.py",), bridge=None):
    """Один прогон ЖИВОЙ двери доставки → (id карточек, мост)."""
    f = Facts(sha, unit, files)
    fb = bridge or FakeBridge()
    keepb, keep = OD.bc, (OD.prod_drift.commits_since, OD.prod_drift.closure,
                          OD.prod_drift.live, OD._curator_state_dirty)
    OD.bc = fb
    OD.prod_drift.commits_since = f.commits_since
    OD.prod_drift.closure = f.closure
    OD.prod_drift.live = f.live
    OD._curator_state_dirty = f.dirty_files
    try:
        OD._deliver_next = 0.0
        said = OD._maybe_deliver_ask()
    finally:
        OD.bc = keepb
        (OD.prod_drift.commits_since, OD.prod_drift.closure, OD.prod_drift.live,
         OD._curator_state_dirty) = keep
    return said, fb


def curator(root, item, bridge=None):
    """Один прогон ЖИВОЙ двери куратора → (результат _curator_human_place, мост)."""
    fb = bridge or FakeBridge()
    keep = OD.bc
    OD.bc = fb
    try:
        out = OD._curator_human_place(root, item)
    finally:
        OD.bc = keep
    return out, fb


# ═══════════════ (1) КЛЮЧ УСТОЙЧИВ, И СРАВНИВАТЬ МОЖНО ТОЛЬКО НАЗВАННОЕ ═══════════════════
print("\n(1) КЛЮЧ УСТОЙЧИВ И НАЗВАН")
k1 = ask_ledger.key("service:splinter", "b5478ce")
k2 = ask_ledger.key("service:splinter", "b5478ce6f1a2c3d4e5f60718293a4b5c6d7e8f90")
res.append(ok(k1 == "service:splinter|b5478ce", "ключ = семья|предмет: %r" % k1))
res.append(ok(k1 == k2, "длинный и короткий хеш дают ОДИН ключ (обе двери зовут коммит 7 знаками)"))
res.append(ok(ask_ledger.key("service:splinter", "B5478CE") == k1, "регистр предмета не меняет ключ"))
res.append(ok(ask_ledger.key("service:splinter", " b5478ce ") == k1, "пробелы не меняют ключ"))
# «ЧЕРЕЗ СУТКИ ТОТ ЖЕ КЛЮЧ» — доказываем устройством, а не сном: ключ строится РОВНО из двух
# аргументов, а времени, номера карточки, номера цели и полосы в нём нет ни одним именем.
res.append(ok(ask_ledger.key("service:splinter", "b5478ce")
              == ask_ledger.key("service:splinter", "b5478ce"),
              "ключ детерминирован: два зова — один результат"))
res.append(ok("561" not in k1 and "559" not in k1 and "vps" not in k1,
              "в ключе нет ни номера карточки, ни номера цели, ни полосы: %r" % k1))
led_day = ask_ledger.remember(ask_ledger.empty(), [k1], "куратор", 561, 1000.0)
v_day = ask_ledger.verdict([ask_ledger.key("service:splinter", "b5478ce")], led_day,
                           1000.0 + 86400.0, 48 * 3600.0)
res.append(ok(v_day["state"] == ask_ledger.STANDING,
              "ТОТ ЖЕ объект через СУТКИ — тот же ключ, запись находится: %s" % v_day["state"]))
res.append(ok(ask_ledger.key("service:?", "b5478ce") is None,
              "семья без имени юнита (`service:?`) ключа НЕ даёт — сравнивать нечего"))
res.append(ok(ask_ledger.key("", "b5478ce") is None and ask_ledger.key("service:splinter", "") is None,
              "пустая операция и пустой предмет ключа НЕ дают"))
res.append(ok(ask_ledger.card_keys([], ["b5478ce"]) == [] and ask_ledger.card_keys(["x"], []) == [],
              "карточка без операции ИЛИ без предмета ключей не даёт вовсе"))

# ═══════════════════════ (2) ЧИСТОЕ РЕШЕНИЕ ═══════════════════════════════════════════════
print("\n(2) ЧИСТОЕ РЕШЕНИЕ: рук нет ФИЗИЧЕСКИ")
src = open(os.path.join(REPO, "ask_ledger.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
res.append(ok(len(imports) == 0, "импортов в ask_ledger.py: %d (ждём 0)" % len(imports)))
names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
res.append(ok(not ({"open", "exec", "eval", "__import__"} & names),
              "ни open, ни exec, ни eval — реестр читают РУКИ, не решение"))


class _Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


r = _Run()
invariants_check.check_ask_ledger_pure(None, r)
res.append(ok(not r.flags, "страж ASK_LEDGER_PURE на боевом файле: нарушений %d" % len(r.flags)))
DIRTY = "/tmp/cc_ask_ledger_dirty_probe.py"
with open(DIRTY, "w", encoding="utf-8") as f:
    f.write("import os\n\n\ndef key(a, b):\n    return os.getcwd()\n")
keep_path = invariants_check._ASK_LEDGER_PATH
invariants_check._ASK_LEDGER_PATH = DIRTY
r2 = _Run()
invariants_check.check_ask_ledger_pure(None, r2)
invariants_check._ASK_LEDGER_PATH = keep_path
res.append(ok(bool(r2.flags), "страж КРАСНЕЕТ на модуле с импортом: нарушений %d" % len(r2.flags)))

# ═════════════ (3) П.4-А ОТРИЦАТЕЛЬНЫЙ: РАЗНЫЕ ОБЪЕКТЫ — ДОХОДЯТ ОБЕ ══════════════════════
print("\n(3) П.4-А ОТРИЦАТЕЛЬНЫЙ ТЕСТ — ДВЕ КАРТОЧКИ ПО РАЗНЫМ ОБЪЕКТАМ (прогон ДОСЛОВНО)")
# ЕДИНИЦА ВОПРОСА — ОПЕРАЦИЯ (22.09.2026, склейка карточки доставки). «Разные объекты» с этого
# дня значит РАЗНЫЕ ОПЕРАЦИИ: два коммита, не доехавшие до ОДНОГО splinter, лечит один рестарт,
# и второй вопрос о нём глушит уже сама дверь (`_deliver_open_units`) — это и есть предмет
# задания 0012-70n.2209. Предмет ЭТОЙ проверки не изменён и здесь только усилен: дедуп МЕЖДУ
# дверьми не смеет съесть вопрос о ДРУГОЙ операции, и ниже это доказано на двух разных юнитах.
reset()
fb_a = FakeBridge()
s1, _ = deliver("b5478ce", bridge=fb_a)
s2, _ = deliver("baf5d30", unit="orchestrator-daemon", files=("orchestrator_daemon.py",),
                bridge=fb_a)
led_a = ledger()
print("   прогон 1: коммит b5478ce (splinter) → карточки владельцу %s" % s1)
print("   прогон 2: коммит baf5d30 (orchestrator-daemon) → карточки владельцу %s" % s2)
print("   строки, доведённые до needs_approval: %s" % fb_a.cards())
print("   реестр: %s" % sorted(led_a["asks"]))
print("   счётчик дедупа: %s" % led_a["skipped"])
res.append(ok(len(s1) == 1 and len(s2) == 1, "по РАЗНЫМ объектам дошли ОБЕ карточки"))
res.append(ok(len(fb_a.cards()) == 2, "владелец видит РОВНО две строки needs_approval: %s"
              % fb_a.cards()))
res.append(ok(led_a["skipped"] == 0, "счётчик дедупа НЕ рос — глушить было нечего: %s"
              % led_a["skipped"]))
res.append(ok(sorted(led_a["asks"]) == ["service:orchestrator-daemon|baf5d30",
                                        "service:splinter|b5478ce"],
              "в реестре ровно два разных объекта (операция × коммит)"))

# ═════════════ (4) П.4-Б ОТРИЦАТЕЛЬНЫЙ: ОДИН ОБЪЕКТ — ВТОРАЯ НЕ ДОХОДИТ ═══════════════════
print("\n(4) П.4-Б ОТРИЦАТЕЛЬНЫЙ ТЕСТ — ДВЕ КАРТОЧКИ ПО ОДНОМУ ОБЪЕКТУ (прогон ДОСЛОВНО)")
reset()
fb_b = FakeBridge()
c1, _ = curator(559, ITEM_SPLINTER_B, bridge=fb_b)
before = ledger()
d1, _ = deliver("b5478ce", bridge=fb_b)
after = ledger()
print("   дверь КУРАТОРА (цель 559, пункт про splinter + b5478ce) → %r" % (c1,))
print("   реестр после неё: %s" % sorted(before["asks"]))
print("   дверь ДОСТАВКИ (тот же коммит b5478ce, тот же splinter) → карточки владельцу %s" % d1)
print("   строки, доведённые до needs_approval: %s" % fb_b.cards())
print("   счётчик дедупа: было %s, стало %s" % (before["skipped"], after["skipped"]))
res.append(ok(c1 is not None and c1[0] is not None, "первая дверь карточку ПОСТАВИЛА: %s" % (c1,)))
res.append(ok(d1 == [], "вторая дверь до владельца НЕ дошла: %r" % (d1,)))
res.append(ok(len(fb_b.cards()) == 1, "у владельца РОВНО одна строка, а не две: %s" % fb_b.cards()))
res.append(ok(after["skipped"] == before["skipped"] + 1,
              "счётчик дедупа ВЫРОС: %s → %s" % (before["skipped"], after["skipped"])))

print("\n   … и в ОБРАТНОМ порядке (доставка первой, куратор вторым):")
reset()
fb_b2 = FakeBridge()
d2, _ = deliver("baf5d30", bridge=fb_b2)
bef2 = ledger()
c2, _ = curator(562, ITEM_SPLINTER_BAF, bridge=fb_b2)
aft2 = ledger()
print("   дверь ДОСТАВКИ → карточки %s ; дверь КУРАТОРА → %r" % (d2, c2))
print("   строки needs_approval: %s ; счётчик дедупа %s → %s"
      % (fb_b2.cards(), bef2["skipped"], aft2["skipped"]))
res.append(ok(len(d2) == 1, "первая дверь (доставка) карточку поставила"))
res.append(ok(c2 is not None and c2[0] is None and c2[1] == "asked",
              "вторая дверь (куратор) карточку НЕ поставила: %r" % (c2,)))
res.append(ok(len(fb_b2.cards()) == 1, "у владельца РОВНО одна строка: %s" % fb_b2.cards()))
res.append(ok(aft2["skipped"] == bef2["skipped"] + 1, "счётчик дедупа вырос"))
res.append(ok("уже спрашивает" in (c2[2] or ""), "причина названа владельцу: %r" % (c2[2],)))

# ═════════ (5) П.5 ТОТ ЖЕ ОБЪЕКТ, ДРУГАЯ ОПЕРАЦИЯ — НЕ ПРОГЛАТЫВАЕТСЯ ═════════════════════
print("\n(5) П.5 ТОТ ЖЕ ОБЪЕКТ, ДРУГАЯ ОПЕРАЦИЯ — ВОПРОС НЕ ПРОГЛАТЫВАЕТСЯ")
reset()
fb_c = FakeBridge()
c3, _ = curator(559, ITEM_SPLINTER_B, bridge=fb_c)          # splinter × b5478ce
led_c = ledger()
d3, _ = deliver("b5478ce", unit="orchestrator-daemon",
                files=("orchestrator_daemon.py",), bridge=fb_c)   # ДРУГАЯ операция, тот же коммит
aft_c = ledger()
print("   реестр после куратора: %s" % sorted(led_c["asks"]))
print("   дверь доставки о ТОМ ЖЕ коммите, но о orchestrator-daemon → карточки %s" % d3)
print("   строки needs_approval: %s ; счётчик дедупа %s → %s"
      % (fb_c.cards(), led_c["skipped"], aft_c["skipped"]))
res.append(ok(len(d3) == 1, "ДРУГАЯ операция того же объекта ДОШЛА до владельца: %s" % d3))
res.append(ok(len(fb_c.cards()) == 2, "у владельца ДВЕ строки — по одной на операцию: %s"
              % fb_c.cards()))
res.append(ok(aft_c["skipped"] == 0, "счётчик дедупа НЕ рос: %s" % aft_c["skipped"]))
res.append(ok(sorted(aft_c["asks"]) == ["service:orchestrator-daemon|b5478ce",
                                        "service:splinter|b5478ce"],
              "в реестре ДВА разных ключа на один коммит: %s" % sorted(aft_c["asks"])))
# и симметрично на чистом решении: пункт про демона не гасится записью про splinter
res.append(ok(ask_ledger.verdict(ask_ledger.card_keys(["service:orchestrator-daemon"], ["b5478ce"]),
                                 led_c, 0.0, 0.0)["state"] == ask_ledger.ASK,
              "решение само: другая семья → СПРОСИТЬ"))

# ═════════════ (6) ЖИВОЙ СЛУЧАЙ 14.08 — ОБЕ ПАРЫ ПО ДОСЛОВНЫМ ДАННЫМ ══════════════════════
print("\n(6) ЖИВОЙ СЛУЧАЙ 14.08: пары 561/565 (b5478ce) и 564/566 (baf5d30)")
for goal, item, sha in ((559, ITEM_SPLINTER_B, "b5478ce"), (562, ITEM_SPLINTER_BAF, "baf5d30")):
    reset()
    fb = FakeBridge()
    cur_out, _ = curator(goal, item, bridge=fb)
    del_out, _ = deliver(sha, bridge=fb)
    res.append(ok(cur_out and cur_out[0] is not None and del_out == [] and len(fb.cards()) == 1,
                  "цель %s / коммит %s: владельцу ОДНА карточка вместо двух (было 2)"
                  % (goal, sha)))

# ═════════════ (7) ОТВЕТ УЖЕ ПОЛУЧЕН — ВТОРАЯ ДВЕРЬ БЕРЁТ ГОТОВЫЙ ОТВЕТ ═══════════════════
print("\n(7) ОТВЕТ УЖЕ ПОЛУЧЕН: вторая дверь называет его словом и номером")
for outcome in (chain_cards.REJECTED, chain_cards.APPROVED, chain_cards.EXPIRED,
                chain_cards.CLOSED):
    reset()
    fb = FakeBridge()
    cur_out, _ = curator(559, ITEM_SPLINTER_B, bridge=fb)
    card_id = cur_out[0]
    OD._card_end_note(card_id, outcome)                     # ЖИВАЯ ветка терминала карточки
    led = ledger()
    rec = led["asks"].get("service:splinter|b5478ce") or {}
    v = ask_ledger.verdict(["service:splinter|b5478ce"], led, 0.0, 0.0)
    d, _ = deliver("b5478ce", bridge=fb)
    res.append(ok(rec.get("answer") == outcome and v["state"] == ask_ledger.ANSWERED
                  and d == [] and str(card_id) in v["why"],
                  "исход «%s» лёг в реестр, вторая дверь молчит и называет карточку %s: %s"
                  % (outcome, card_id, v["why"][:88])))
# ГРАНИЦА: «берёт готовый ответ» — про СЛОВА, не про действие. Ветка доставки не умеет
# перезапускать: у неё нет ни одной команды операции (проверено соседним сьютом), а здесь —
# что ответ чужой карточки не породил НИ ОДНОЙ задачи.
reset()
fb7 = FakeBridge()
cur7, _ = curator(559, ITEM_SPLINTER_B, bridge=fb7)
OD._card_end_note(cur7[0], chain_cards.APPROVED)
n_before = len(fb7.rows)
deliver("b5478ce", bridge=fb7)
res.append(ok(len(fb7.rows) == n_before,
              "«да» чужой карточке НЕ породило у второй двери ни строки очереди (%d → %d)"
              % (n_before, len(fb7.rows))))

# ═════════════════ (8) FAIL-SAFE — ВСЕГДА В СТОРОНУ ВОПРОСА ═══════════════════════════════
print("\n(8) FAIL-SAFE: сомнение решается в сторону ВОПРОСА, а не тишины")
res.append(ok(ask_ledger.verdict(["service:splinter|b5478ce"], None, 0.0, 0.0)["state"]
              == ask_ledger.ASK, "реестр НЕ ПРОЧИТАН (None) → спросить"))
res.append(ok(ask_ledger.skipped(None) is None, "у непрочитанного реестра счётчик None, а не 0"))
led_old = ask_ledger.remember(ask_ledger.empty(), ["service:splinter|b5478ce"], "куратор", 561, 100.0)
res.append(ok(ask_ledger.verdict(["service:splinter|b5478ce"], led_old,
                                 100.0 + 49 * 3600.0, 48 * 3600.0)["state"] == ask_ledger.ASK,
              "запись СТАРШЕ окна → спросить заново"))
res.append(ok(ask_ledger.verdict(["service:splinter|b5478ce"], led_old,
                                 100.0 + 47 * 3600.0, 48 * 3600.0)["state"] == ask_ledger.STANDING,
              "запись внутри окна → молчим"))
# ЧАСТИЧНОЕ ПОКРЫТИЕ: покрыт один ключ из двух → вопрос уходит ЦЕЛИКОМ (класс _HUMAN_MISSING)
led_half = ask_ledger.remember(ask_ledger.empty(), ["service:splinter|7f147a0"], "куратор", 1, 0.0)
res.append(ok(ask_ledger.verdict(["service:splinter|7f147a0", "service:orchestrator-daemon|7f147a0"],
                                 led_half, 0.0, 0.0)["state"] == ask_ledger.ASK,
              "покрыт 1 ключ из 2 → СПРОСИТЬ: половину вопроса дедуп не съедает"))
reset()
fb8 = FakeBridge()
d8, _ = deliver("7f147a0", unit="splinter", files=("splinter.py",), bridge=fb8)
led8 = ledger()
c8, _ = curator(700, "Нужно «да» на перезапуск splinter и на рестарт orchestrator-daemon "
                     "ради коммита 7f147a0.", bridge=fb8)
res.append(ok(c8 is not None and c8[1] != "asked",
              "живьём: доставка спросила про splinter, пункт про ОБЕ операции всё равно дошёл: %r"
              % (c8[1],)))
# Карточка, просящая РЕШЕНИЕ (операции нет вовсе) — дедупом не задета НИ ОДНОЙ
reset(ask_ledger.remember(ask_ledger.empty(), ["service:splinter|5feebf9"], "доставка", 1, 0.0))
fb8b = FakeBridge()
c8b, _ = curator(701, ITEM_DECISION, bridge=fb8b)
res.append(ok(c8b is not None and c8b[1] != "asked" and len(fb8b.cards()) == 1,
              "пункт «просит РЕШЕНИЕ» (операции нет) дошёл, как доходил: %r" % (c8b[1],)))

# ═══════════════════════════ (9) ГРАНИЦЫ ══════════════════════════════════════════════════
print("\n(9) ГРАНИЦЫ: откат, канон метрики, цена")
series_file = OD._series_file() if hasattr(OD, "_series_file") else None


def sha_of(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except OSError:
        return "нет файла"


before_series = sha_of(os.path.join(REPO, "chain_series.json"))
before_ops = sha_of(os.path.join(REPO, "curator_ops.py"))
before_cs = sha_of(os.path.join(REPO, "chain_series.py"))

# ОТКАТ: ASK_DEDUP=0 → ветка мертва ДО чтения реестра; обе двери спрашивают, как спрашивали
reset()
fb9 = FakeBridge()
curator(559, ITEM_SPLINTER_B, bridge=fb9)
os.environ["ASK_DEDUP"] = "0"
d9, _ = deliver("b5478ce", bridge=fb9)
os.environ["ASK_DEDUP"] = "1"
res.append(ok(len(d9) == 1 and len(fb9.cards()) == 2,
              "ASK_DEDUP=0 → ОБЕ карточки у владельца, как до правки: %s" % fb9.cards()))
res.append(ok(OD._ask_dedup_check("доставка", ["service:splinter"], ["b5478ce"]) is not None,
              "…а при ASK_DEDUP=1 тот же объект глушится (ручка действительно правит поведение)"))
os.environ["ASK_DEDUP"] = "0"
res.append(ok(OD._ask_dedup_check("доставка", ["service:splinter"], ["b5478ce"]) is None,
              "ASK_DEDUP=0: проверка молчит ДО чтения реестра"))
os.environ["ASK_DEDUP"] = "1"

res.append(ok(sha_of(os.path.join(REPO, "chain_series.json")) == before_series,
              "файл счёта серии НЕ ТРОНУТ ни на байт: %s" % before_series))
res.append(ok(sha_of(os.path.join(REPO, "curator_ops.py")) == before_ops
              and sha_of(os.path.join(REPO, "chain_series.py")) == before_cs,
              "канон метрики не изменён: curator_ops.py и chain_series.py те же"))
# Судим КОД, а не прозу: имя в докстринге кодом не является (то же правило позиции, что у
# `5ca761d`/`40c8425`). В докстринге `chain_series.sort_card` НАЗВАН намеренно — там сказано, что
# канон метрики этот модуль не трогает; важно, чтобы в КОДЕ этого имени не было ни одним узлом.
_code_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
_code_names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
res.append(ok(not ({"chain_series", "sort_card", "chain_cards", "curator_ops"} & _code_names),
              "в КОДЕ решения нет ни счёта серии, ни словаря операций: %s"
              % sorted({"chain_series", "sort_card", "chain_cards", "curator_ops"} & _code_names)))
res.append(ok("chain_series.sort_card" in src,
              "…и при этом докстринг ПРЯМО говорит, что канон метрики не трогается"))

# ЦЕНА: сам дедуп не делает НИ ОДНОГО обращения к мосту
reset(ask_ledger.remember(ask_ledger.empty(), ["service:splinter|b5478ce"], "куратор", 561, 0.0))
probe = FakeBridge()
keepb = OD.bc
OD.bc = probe
try:
    OD._ask_dedup_check("доставка", ["service:splinter"], ["b5478ce"])
    OD._ask_dedup_note("доставка", ["service:splinter"], ["deadbee"], 5)
    OD._ask_dedup_answer(561, chain_cards.REJECTED)
finally:
    OD.bc = keepb
res.append(ok(probe.calls == [], "дедуп не обращается к мосту НИ РАЗУ: %s" % (probe.calls,)))

# ГАРД не тронут этим заходом
guard_src = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("ask_ledger" not in guard_src and "ask_dedup" not in guard_src,
              "pretool_guard.py о дедупе не знает ничего — он не изменён"))

print("\n%s / total %d" % ("ALL PASS ✅" if all(res) else "‼️ ЕСТЬ ПАДЕНИЯ", len(res)))
sys.exit(0 if all(res) else 1)
