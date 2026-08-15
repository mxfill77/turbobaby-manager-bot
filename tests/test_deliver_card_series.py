"""КАРТОЧКА ДОСТАВКИ — ТОЖЕ ВМЕШАТЕЛЬСТВО, И ЖИВОЙ СЧЁТ СЕРИИ ОБЯЗАН ЕГО ВИДЕТЬ (15.08.2026).

ПОВОД — ДОСЛОВНЫЙ. 14.08 дверь `_maybe_deliver_ask` выдала владельцу две карточки:
  565 — `[доставка коммита b5478ce] доставка в прод: splinter` (22:09:13),
  566 — `[доставка коммита baf5d30] доставка в прод: splinter` (22:24:35),
а 15.08 в 03:14:40 splinter перезапустили РУКАМИ — обе просьбы к моменту ответа «купили ничего».
По рамке §8г это ШУМ, то есть обрыв серии. В `chain_series.json` не оказалось НИ ОДНОЙ из двух
карточек и ни строки в `chain_cards.jsonl`: дверь доставки не звала `_series_note_card` вовсе —
единственная дверь карточек владельцу, которая счёт не трогала (у красных карточек `process_new`
вызов стоит с 10.08).

ПОЧЕМУ НЕ ХВАТИЛО ПРОСТО ПОЗВАТЬ ОБРАЗЕЦ. Строка очереди карточки доставки маркера родителя не
несёт, поэтому `_series_root` вернул бы ЕЁ СОБСТВЕННЫЙ номер, а цепочка из одной карточки без
единой записи не закрывается НИКОГДА (`chain_series.chain_closed` требует хотя бы один терминал)
— она вечно «открыта» и в серию не входит. То есть наивный вызов записал бы вмешательство в
файл и всё равно не дал бы ему ни удлинить серию, ни оборвать. Корень берётся у ЦЕПОЧКИ КОММИТА:
коммит уже приписан ей окном исполнения — тем же свидетелем, которым считается её вес.

Проверки:
 (1) ДОСЛОВНОСТЬ: строка очереди карточки доставки байт-в-байт равна живым строкам 565/566;
 (2) дверь зовёт счёт: карточка есть и в состоянии, и в журнале рождения, тело — то же, что у
     владельца; корень = цепочка КОММИТА (559 для b5478ce, 562 для baf5d30), а не номер карточки;
 (3) операции карточки = `service:splinter` — тем же словарём; отрицание («выкладки моста задача
     делать не будет») операцией не становится;
 (4) СОРТ ПО РАМКЕ: перезапуск состоялся ДО ответа → ШУМ → цепочка стала ОБРЫВОМ; не состоялся →
     ВОЛЯ, цепочка чистая (ответ владельца в решении не участвует ни в одну сторону);
 (5) БЕЗ ПРАВКИ вмешательство выпадало: цепочка своего номера не закрывается, серия её не видит;
 (6) коммита нет ни в одной цепочке → журнал пишем, состояние НЕ трогаем (фантомной цепочки не
     заводим), сама карточка владельцу выдаётся как выдавалась;
 (7) ГРАНИЦЫ: `CHAIN_SERIES=0` → ни состояния, ни журнала (карточка всё равно встаёт); красные
     карточки `process_new` пишутся ПРЕЖНИМ корнем; у моста ни одного лишнего обращения;
     `deliver_card.py` и `chain_series.py` не тронуты (импорты те же), `pretool_guard.py` — ни строкой.
"""
import datetime
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"    # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CURATOR_STATE"] = "0"
os.environ["DELIVER_CARD"] = "1"
os.environ["CHAIN_SERIES"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"

TMP = tempfile.mkdtemp(prefix="cc_deliver_series_")
os.environ["CC_DELIVER_DIR"] = os.path.join(TMP, "asked")
os.environ["CC_SERIES_FILE"] = os.path.join(TMP, "chain_series.json")
os.environ["CC_CARDS_FILE"] = os.path.join(TMP, "chain_cards.jsonl")


def ok(c, l):
    print(("  PASS " if c else "  FAIL ") + l)
    return bool(c)


res = []

import chain_cards as CC                # noqa: E402
import chain_series as CS               # noqa: E402
import curator_ops                      # noqa: E402
import deliver_card                     # noqa: E402
import scan_result                      # noqa: E402
import orchestrator_daemon as OD        # noqa: E402

NOW_ISO = datetime.datetime.now(datetime.timezone.utc).isoformat()

# ── ДОСЛОВНЫЕ строки очереди 565/566 (снимок живого состояния наблюдателя, 15.08.2026) ───────
ROW_565 = "[доставка коммита b5478ce] доставка в прод: splinter"
ROW_566 = "[доставка коммита baf5d30] доставка в прод: splinter"
# Заголовки коммитов — живые (`git log -1 --format=%s`), обрезка как у боевого предложения.
SUBJ_565 = "кнопка отмены достроена в дверь масла: расписка та же, лишних обращений ноль, за"
SUBJ_566 = "в историю обслуживания идёт названная работа, а не ярлык: слова механика — челов"
# Перезапуск splinter, случившийся РУКАМИ 15.08 (тот самый, из-за которого обе просьбы — шум).
RESTART_AT = "2026-08-15T03:14:40"
BORN_565 = "2026-08-14T22:09:13"


class Facts:
    """Факты доставки ТОЙ ЖЕ ФОРМЫ, что собирает рука наблюдателя (образец test_deliver_card).

    Замыкания и живые процессы подменяются целиком — иначе тест мерил бы состояние ЭТОЙ машины.
    Файл коммита настоящий (`splinter.py`): свидетель по mtime обязан работать на живом формате.
    Заголовок коммита — живой, ради дословности тела карточки."""

    def __init__(s, sha, subject, files=("splinter.py",), unit="splinter"):
        s.sha, s.subject, s.files, s.unit = sha, subject, list(files), unit
        s.calls = {"commits": 0, "closure": 0, "live": 0, "dirty": 0}
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        s.ct = now - 5 * 3600.0
        mts = [os.stat(os.path.join(REPO, f)).st_mtime
               for f in s.files if os.path.exists(os.path.join(REPO, f))]
        s.started = min([s.ct] + mts) - 60.0        # процесс поднят ДО коммита → не доставлен

    def commits_since(s, ts, repo=None):
        s.calls["commits"] += 1
        return [{"sha": s.sha, "ct": int(s.ct), "subject": s.subject, "files": s.files}]

    def closure(s, entry, repo=None):
        s.calls["closure"] += 1
        return set([entry] + s.files) if entry == _entry_of(s.unit) else {entry}

    def live(s, unit, entry, proc=None, repo=None):
        s.calls["live"] += 1
        return {"pid": 1234, "started": s.started}

    def dirty_files(s):
        s.calls["dirty"] += 1
        return scan_result.ScanResult(scanned=0, parsed=0,
                                      subject="файлов расхождения с origin/main", payload=[])


def _entry_of(unit):
    for u, e in OD.prod_drift.WATCHED:
        if u == unit:
            return e
    return "bot.py"


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
    """Очередь в памяти + счётчик ЛЮБОГО обращения (образец test_deliver_card.FakeBridge)."""

    def __init__(s, first_id=564):
        s.rows, s.nid, s.calls = {}, int(first_id), []

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
        return {"ok": True}


def seed_state(commits_by_root, changes=()):
    """Состояние счёта: закрытые цепочки со своим весом. Форма — та же, что у боевого файла
    (снята с `chain_series.json` прода: цепочки 559 и 562 несут b5478ce и baf5d30)."""
    chains = {}
    for root, shas in commits_by_root.items():
        chains[str(root)] = {
            "root": int(root), "lane": "vps", "created": "2026-08-14T17:38:49",
            "closed_at": "2026-08-14T18:01:17", "statuses": {str(root): "done"},
            "cards": [], "refusals": [],
            "weight": {"commits": list(shas), "restarts": 0, "known": True},
        }
    state = {"started_counting": "2026-08-10T19:30:55", "chains": chains, "windows": [],
             "derived": {}, "changes": [dict(c) for c in changes], "units": {}}
    with open(os.environ["CC_SERIES_FILE"], "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    return state


def read_state():
    with open(os.environ["CC_SERIES_FILE"], encoding="utf-8") as f:
        return json.load(f)


def reset(commits_by_root, changes=()):
    shutil.rmtree(os.environ["CC_DELIVER_DIR"], ignore_errors=True)
    for p in (os.environ["CC_SERIES_FILE"], os.environ["CC_CARDS_FILE"]):
        if os.path.exists(p):
            os.remove(p)
    OD._deliver_next = 0.0
    OD._SERIES_LOST.clear()
    return seed_state(commits_by_root, changes)


def ask(facts, first_id=564):
    """Один прогон боевой двери предложения → (id карточек, мост)."""
    fb, keep = FakeBridge(first_id), OD.bc
    OD.bc = fb
    try:
        said = with_facts(facts, OD._maybe_deliver_ask)
    finally:
        OD.bc = keep
    return said, fb


def card_of(state, root, tid):
    for c in ((state.get("chains") or {}).get(str(root)) or {}).get("cards") or []:
        if c.get("id") == tid:
            return c
    return None


F565 = Facts("b5478ce", SUBJ_565)
F566 = Facts("baf5d30", SUBJ_566)
LIVE_ROOTS = {559: ["b5478ce"], 562: ["baf5d30"]}

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(1) ДОСЛОВНОСТЬ СТРОКИ ОЧЕРЕДИ 565/566")
off565 = {"sha": "b5478ce", "subject": SUBJ_565, "age": 5 * 3600.0, "units": ["splinter"],
          "by_unit": {"splinter": ["splinter.py"]}, "files": ["splinter.py"], "unknown": []}
off566 = dict(off565, sha="baf5d30", subject=SUBJ_566)
res.append(ok(deliver_card.row_text(off565) == ROW_565,
              "(1a) строка 565 байт-в-байт живая: %r" % deliver_card.row_text(off565)))
res.append(ok(deliver_card.row_text(off566) == ROW_566,
              "(1b) строка 566 байт-в-байт живая: %r" % deliver_card.row_text(off566)))
res.append(ok(deliver_card.sha_of(ROW_565) == "b5478ce" and deliver_card.sha_of(ROW_566) == "baf5d30",
              "(1c) коммит читается обратно из дословной строки"))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(2) ДВЕРЬ ДОСТАВКИ ЗОВЁТ СЧЁТ: карточка в состоянии и в журнале, корень = цепочка коммита")
st = reset(LIVE_ROOTS)
said, fb = ask(F565, first_id=564)
state = read_state()
c = card_of(state, 559, 565)
res.append(ok(said == [565], "(2a) карточка выдана владельцу (id=%s)" % said))
res.append(ok(c is not None, "(2b) карточка 565 записана в ЖИВОЙ СЧЁТ (прежде не попадала вовсе)"))
res.append(ok(card_of(state, 565, 565) is None and "565" not in (state.get("chains") or {}),
              "(2c) СВОЕЙ цепочки 565 не заведено — корень взят у цепочки коммита 559"))
res.append(ok(bool(c) and c.get("open") is True, "(2d) карточка записана ОТКРЫТОЙ (сорт — при закрытии)"))
j = (CC.load(os.environ["CC_CARDS_FILE"]) or {}).get("cards") or {}
res.append(ok(565 in j, "(2e) карточка 565 записана в журнал рождения (замер)"))
body_owner = fb.rows[565]["result"]
res.append(ok(bool(j) and str(j[565]["head"])[:60] == body_owner[:60],
              "(2f) в журнал ушло ТО ЖЕ тело, что видит владелец"))
res.append(ok(bool(c) and c.get("journal") is True, "(2g) успех журнала назван в самой карточке"))

st = reset(LIVE_ROOTS)
said2, fb2 = ask(F566, first_id=565)
state2 = read_state()
res.append(ok(said2 == [566] and card_of(state2, 562, 566) is not None,
              "(2h) 566 (`baf5d30`) → цепочка 562, тем же фактом окна исполнения"))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(3) ОПЕРАЦИИ КАРТОЧКИ — ТЕМ ЖЕ СЛОВАРЁМ")
ops = curator_ops.operations(body_owner)
keys = [o["key"] for o in ops]
res.append(ok(keys == ["service:splinter"], "(3a) операция карточки ровно одна: %s" % keys))
res.append(ok(card_of(read_state(), 562, 566)["ops"] == ["service:splinter"],
              "(3b) те же ключи легли в состояние"))
res.append(ok("выкладки моста" in body_owner and "bridge_deploy" not in keys,
              "(3c) отрицание в теле («выкладки моста … не будет») операцией НЕ становится"))
res.append(ok("systemctl restart splinter" in body_owner,
              "(3d) тело называет форму доставки дословно (голден живого рендера)"))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(4) СОРТ ПО РАМКЕ §8г: ответ владельца не участвует, решает ОПЕРАЦИЯ")
v_noise = CS.sort_card(["service:splinter"],
                       [{"family": "service:splinter", "at": RESTART_AT}],
                       BORN_565, "2026-08-15T04:00:00")
res.append(ok(v_noise["sort"] == CS.NOISE and RESTART_AT in v_noise["why"],
              "(4a) перезапуск 15.08 03:14:40 внутри жизни карточки → ШУМ: %s" % v_noise["why"][:70]))
ch_noise = {"root": 559, "lane": "vps", "created": "", "closed_at": "x",
            "statuses": {"559": "done"},
            "cards": [{"id": 565, "open": False, "sort": v_noise["sort"], "why": v_noise["why"]}],
            "refusals": [], "weight": {"commits": ["b5478ce"], "restarts": 0, "known": True}}
vd = CS.chain_verdict(ch_noise)
res.append(ok(vd["break"] and vd["cause"] == CS.NOISE,
              "(4b) цепочка 559 с этой карточкой = ОБРЫВ (шум), а прежде шла чистой"))
v_will = CS.sort_card(["service:splinter"], [], BORN_565, "2026-08-15T04:00:00")
ch_will = dict(ch_noise, cards=[{"id": 565, "open": False, "sort": v_will["sort"],
                                 "why": v_will["why"]}])
res.append(ok(v_will["sort"] == CS.WILL and not CS.chain_verdict(ch_will)["break"],
              "(4c) перезапуска не было → ВОЛЯ, цепочка НЕ рвётся (граница не сдвинута)"))
# Живой тик закрытия: карточка ушла из needs_approval → сорт ставится здесь. Часы пришпилены
# к ДОСЛОВНЫМ меткам живого случая (рождение 14.08 22:09:13, перезапуск 15.08 03:14:40) —
# иначе тест мерил бы момент своего запуска, а не воспроизводил бы 565.
st = reset(LIVE_ROOTS, changes=[{"family": "service:splinter", "at": RESTART_AT}])
said3, fb3 = ask(F565, first_id=564)
_s = read_state()
card_of(_s, 559, 565)["born"] = BORN_565
with open(os.environ["CC_SERIES_FILE"], "w", encoding="utf-8") as _f:
    json.dump(_s, _f, ensure_ascii=False)
keep_units, OD._series_units_now = OD._series_units_now, lambda: {}
try:
    OD._series_cards_tick(set())          # карточки в needs_approval больше нет
finally:
    OD._series_units_now = keep_units
closed = card_of(read_state(), 559, 565)
res.append(ok(bool(closed) and closed.get("open") is False and closed.get("sort") == CS.NOISE,
              "(4d) живой тик закрыл карточку 565 сортом ШУМ: %s" % (closed or {}).get("why", "")[:60]))
d = read_state().get("derived") or {}
res.append(ok(any(b.get("root") == 559 and b.get("cause") == CS.NOISE
                  for b in (d.get("breaks") or [])),
              "(4e) обрыв цепочки 559 назван в состоянии счёта (%s)" % (d.get("breaks") or [])[-1:]))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(5) БЕЗ ПРИПИСКИ ПО КОММИТУ ВМЕШАТЕЛЬСТВО ВЫПАДАЛО БЫ И ЗАПИСАННЫМ")
res.append(ok(CS.chain_closed({}) is False and CS.chain_closed([]) is False,
              "(5a) цепочка без единой записи НЕ закрыта — своим номером карточка не считалась бы"))
own = {"root": 565, "lane": "vps", "created": "", "closed_at": "", "statuses": {},
       "cards": [{"id": 565, "open": False, "sort": CS.NOISE, "why": "шум"}], "refusals": [],
       "weight": {"commits": [], "restarts": 0, "known": True}}
res.append(ok(CS.chain_verdict(own)["closed"] is False,
              "(5b) вердикт такой цепочки: НЕ ЗАКРЫТА → серия её пропускает навсегда"))
ser_own = CS.series([CS.chain_verdict(own)])
res.append(ok(ser_own["current"] == 0 and not ser_own["breaks"],
              "(5c) серия от неё не растёт и не рвётся — ровно та немота, что была у 565/566"))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(6) КОММИТА НЕТ НИ В ОДНОЙ ЦЕПОЧКЕ → журнал есть, фантомной цепочки нет")
st = reset({559: ["ffffff0"]})                       # b5478ce не принадлежит ни одному окну
said4, fb4 = ask(F565, first_id=564)
state4 = read_state()
res.append(ok(said4 == [565], "(6a) карточка владельцу выдана как выдавалась"))
res.append(ok(set(state4.get("chains") or {}) == {"559"},
              "(6b) новых цепочек не заведено (фантома 565 нет): %s" % sorted(state4.get("chains") or {})))
res.append(ok(card_of(state4, 559, 565) is None, "(6c) чужой цепочке карточку не вешаем"))
res.append(ok(565 in ((CC.load(os.environ["CC_CARDS_FILE"]) or {}).get("cards") or {}),
              "(6d) в журнал рождения запись всё равно легла — замер сорт восстановит"))
res.append(ok(OD._series_commit_root(state4, "b5478ce") is None
              and OD._series_commit_root(st, "ffffff0") == 559,
              "(6e) приписка по коммиту: есть в окне → корень, нет → None (не догадка)"))

# ────────────────────────────────────────────────────────────────────────────────────────────
print("(7) ГРАНИЦЫ")
st = reset(LIVE_ROOTS)
os.environ["CHAIN_SERIES"] = "0"
said5, fb5 = ask(F565, first_id=564)
os.environ["CHAIN_SERIES"] = "1"
res.append(ok(said5 == [565], "(7a) CHAIN_SERIES=0: карточка владельцу всё равно встаёт"))
res.append(ok(card_of(read_state(), 559, 565) is None
              and not os.path.exists(os.environ["CC_CARDS_FILE"]),
              "(7b) CHAIN_SERIES=0: ни состояния, ни журнала — откат байт-в-байт"))

st = reset(LIVE_ROOTS)
said6, fb6 = ask(F565, first_id=564)
res.append(ok(fb6.calls == ["get_pending", "enqueue_task", "claim_task", "set_needs_approval"],
              "(7c) у моста ни одного лишнего обращения: %s" % fb6.calls))

# Образец process_new не тронут: карточка БЕЗ коммита пишется прежним корнем (по маркеру родителя).
st = reset({300: []})
OD._series_note_card(301, {"id": 301, "lane": "vps",
                           "task_text": "[шаг 2/3 родитель 300] правка"}, "🔴 КРАСНОЕ")
res.append(ok(card_of(read_state(), 300, 301) is not None,
              "(7d) красная карточка process_new по-прежнему идёт корнем из маркера родителя"))
st = reset({300: []})
OD._series_note_card(302, {"id": 302, "lane": "vps", "task_text": "одиночная"}, "🔴 КРАСНОЕ")
res.append(ok(card_of(read_state(), 302, 302) is not None,
              "(7e) карточка без родителя — по-прежнему своим корнем (образец не изменён)"))

src = open(os.path.join(REPO, "deliver_card.py"), encoding="utf-8").read()
res.append(ok(sum(1 for ln in src.splitlines() if ln.startswith("import ")) == 1
              and "chain_series" not in src,
              "(7f) deliver_card.py остался чистым решением: импорт ровно один"))
cs_src = open(os.path.join(REPO, "chain_series.py"), encoding="utf-8").read()
res.append(ok(sum(1 for ln in cs_src.splitlines() if ln.startswith("import ")) == 1,
              "(7g) chain_series.py не тронут: импорт ровно один"))
guard = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("deliver_card" not in guard and "_series_note_card" not in guard,
              "(7h) pretool_guard.py этой правкой не тронут ни одной строкой"))
od = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
deliver_branch = od.split("def _maybe_deliver_ask")[1].split("\ndef ")[0]
res.append(ok("systemctl" not in deliver_branch,
              "(7i) в ветке предложения по-прежнему нет ни одной команды перезапуска"))
res.append(ok(deliver_branch.count("_series_note_card(") == 1,
              "(7j) счёт зовётся ровно один раз — после доведения карточки до needs_approval"))

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
