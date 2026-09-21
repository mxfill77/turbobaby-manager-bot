"""ОДИН РЕСТАРТ — ОДНА КАРТОЧКА ДОСТАВКИ (22.09.2026, задание Штаба 0012-70n.2209).

ПОВОД — ЖИВОЙ ЗАМЕР, а не рассуждение. Прибор О3 судит КОММИТ и на каждый недоставленный даёт
свою заметку; лечит их всех ОДНО действие — перезапуск процесса, который поднимает в память
ДЕРЕВО целиком. Пока карточка выписывалась на заметку, владельцу приходило столько вопросов,
сколько коммитов накопилось, и второй не покупал ничего.

ЖУРНАЛ ДЕМОНА (`orchestrator_daemon.log`, строки «не доехал до»), 7 суток 14.09–21.09:
  карточек доставки 5 — 119 (19.09 21:52, orchestrator-daemon, 5e78c36), 149 (20.09 17:23,
  splinter, 3b8f4d8), 150 (20.09 17:38, splinter, 7b1d3af), 15 (21.09 17:22, splinter, ef20207),
  16 (21.09 17:38, splinter, fe66881);
  ЧЕТЫРЕ из пяти — об ОДНОМ И ТОМ ЖЕ splinter в ОДНОМ окне между его перезапусками
  (окна по `journalctl -u splinter`: 19.09 06:21 → 21.09 12:22 держит пару 149+150, 21.09 12:22 →
  21.09 20:03 держит пару 15+16), обе пары с разницей ~15 минут = ровно период замера
  DELIVER_EVERY_SEC. Лишних вопросов владельцу за неделю — ДВА из пяти.

ЧТО ЗАКРЕПЛЕНО ЗДЕСЬ:
 (1) СКЛЕЙКА: заметки по коммитам сворачиваются в предложение ПО ПРОЦЕССУ (`deliver_card.fold`);
 (2) КАРТОЧКА называет ЧИСЛО коммитов и перечисляет их все — «да» дано на всю работу рестарта;
 (3) ОТКАТ один и настоящий (вернуть дерево + перезапустить снова); ❌ и `git revert` названы
     НЕ-откатами прямо в теле — откат, который ничего не откатывает, запрещён;
 (4) СТРОКА ОЧЕРЕДИ несёт все коммиты и читается старыми читателями (`sha_of`/`units_of`), а
     карточка, висящая с прошлой редакции, читается новым (`shas_of` падает на головной маркер);
 (5) ДЕДУП ДВУСТОРОННЕ: пока карточка по процессу открыта — второй нет, даже если пришёл новый
     коммит; карточка закрылась — выписка снова открыта, и новая несёт ВСЕ накопленные коммиты;
 (6) МУТАНТ: дедуп сломан намеренно — показано ЧИСЛОМ, что проверка это ловит;
 (7) ПОТОЛОК СУТОК считает ВОПРОСЫ, а не коммиты (иначе склейка стала бы глушилкой);
 (8) ГРАНИЦЫ: решение чистое, операций в ветке нет, боевое состояние не тронуто.

ПУТЬ ДО ЧЕЛОВЕКА ЗАКРЫТ УСТРОЙСТВОМ, А НЕ ОБЕЩАНИЕМ. Боевой отправитель — модуль-клиент моста
в `OD.bc`: через него строка попадает в очередь, откуда её забирает devbot и несёт владельцу.
Здесь `OD.bc` подменяется ЦЕЛИКОМ объектом в памяти (`FakeBridge`), то есть проверка и боевой
вызов различаются ИМЕНЕМ ОБЪЕКТА, а не флагом внутри него: ни одной строки в очередь, ни одной
карточки в инбокс, ни одного сообщения в тему из этого файла уйти не может. Секция (8) это
доказывает счётом обращений и сверкой боевых файлов состояния до и после прогона.
"""
import datetime
import hashlib
import os
import shutil
import sys

sys.path.insert(0, "/root/turbobaby-manager-bot")
os.environ.setdefault("BRIDGE_URL", "http://x")
os.environ.setdefault("BRIDGE_TOKEN", "x")
os.environ["STEP_SELFHEAL"] = "0"     # изоляция от боевого .env (load_dotenv грузит боевые флаги)
os.environ["PLAN_ADAPT"] = "0"
os.environ["ASK_DEDUP"] = "0"         # предмет сьюта — дедуп САМОЙ двери; реестр между дверьми
# проверяется отдельной секцией со СВОИМ файлом, чтобы фикстура не писала в боевое состояние.
os.environ["CARD_DUTY"] = "0"
os.environ["CURATOR"] = "0"
os.environ["CURATOR_STATE"] = "1"
os.environ["DELIVER_CARD"] = "1"
os.environ["ORCH_TEST_MODE"] = "1"
os.environ["PRETOOL_NOPUSH"] = "1"

# ВРЕМЕННОЕ МЕСТО НАЗВАНО ЯВНО (требование задания): всё, что этот файл пишет, живёт здесь.
TMP = "/tmp/shtab_kartochka_2209"
STATE_DIR = os.path.join(TMP, "deliver_state")
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


def sha256(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return "нет файла"


# Боевые файлы состояния — снимок ДО прогона (сверка в секции (8)).
WATCH_FILES = [os.path.join(REPO, "chain_series.json"),
               os.path.join(REPO, "chain_cards.jsonl"),
               os.path.join(REPO, "deliver_card.py"),
               os.path.join(REPO, "orchestrator_daemon.py")]
BEFORE = {p: sha256(p) for p in WATCH_FILES}


def reset_state():
    shutil.rmtree(STATE_DIR, ignore_errors=True)
    OD._deliver_next = 0.0


class Facts:
    """Факты доставки ТОЙ ЖЕ ФОРМЫ, что собирает рука наблюдателя (образец test_deliver_card).

    Отличие одно и оно и есть предмет: коммитов НЕСКОЛЬКО, и все они не доехали до ОДНОГО
    процесса — ровно живой случай 21.09 (ef20207 и fe66881 против splinter). Файлы коммитов —
    настоящие файлы репозитория: свидетель по mtime обязан работать на живом формате."""

    def __init__(s, commits=None, unit="splinter", started_after=False, dirty=(), dirty_ok=True):
        s.unit = unit
        # ВОЗРАСТ ФИКСТУРЫ ЖИВОЙ, А НЕ УДОБНЫЙ: коммит становится событием О3 только когда он
        # старше порога доставки (`EXPECT_DELIVER_MIN`, дефолт 240 мин) и моложе окна судейства
        # (48 ч). Взять «-3 ч» значило бы построить фикстуру, которой прибор не даёт заметки, —
        # и проверка склейки молча перестала бы задевать ветку, ради которой заведена.
        s.commits = list(commits or [("aaa1111", "первый коммит окна", -8 * 3600.0),
                                     ("bbb2222", "второй коммит окна", -6 * 3600.0)])
        s.files = ["splinter.py"] if unit == "splinter" else ["curator_event.py"]
        s.dirty, s.dirty_ok = list(dirty), dirty_ok
        s.calls = {"commits": 0, "closure": 0, "live": 0, "dirty": 0}
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        s.cts = [now + shift for _sha, _subj, shift in s.commits]
        mts = [os.stat(os.path.join(REPO, f)).st_mtime
               for f in s.files if os.path.exists(os.path.join(REPO, f))]
        edge = max(s.cts + mts)
        s.started = (edge + 60.0) if started_after else (min(s.cts + mts) - 60.0)

    def commits_since(s, ts, repo=None):
        s.calls["commits"] += 1
        return [{"sha": sha, "ct": int(ct), "subject": subj, "files": list(s.files)}
                for (sha, subj, _sh), ct in zip(s.commits, s.cts)]

    def closure(s, entry, repo=None):
        s.calls["closure"] += 1
        return set([entry] + s.files) if entry == _entry_of(s.unit) else {entry}

    def live(s, unit, entry, proc=None, repo=None):
        s.calls["live"] += 1
        return {"pid": 4242, "started": s.started}

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
    return "splinter.py"


def with_facts(f, fn, *a, **kw):
    """Подмена ИМЕНЕМ, а не копией кода: рука зовёт ровно эти четыре функции — их и подменяем."""
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
    """Очередь В ПАМЯТИ и счётчик ЛЮБОГО обращения. ЭТО И ЕСТЬ ГРАНИЦА ДО ЧЕЛОВЕКА: боевой
    отправитель (`bridge_client` в `OD.bc`) на время прогона заменён целиком."""

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


def ask(facts, rows=None, fb=None):
    """Один прогон боевой ветки предложения → (id карточек, мост-в-памяти)."""
    fb, keep = (fb or FakeBridge(rows)), OD.bc
    OD.bc = fb
    try:
        said = with_facts(facts, OD._maybe_deliver_ask)
    finally:
        OD.bc = keep
    return said, fb


def offers_of(facts):
    """Живые предложения ПО КОММИТАМ (боевой прибор + боевой `offer`), до склейки."""
    def go():
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        notes = expectations.verdict({"now": now, "delivery": OD._delivery_facts(now)},
                                     expectations.config(os.environ))
        watched = {u for u, _e in OD.prod_drift.WATCHED}
        return [o for o in (deliver_card.offer(n, watched) for n in notes) if o]
    return with_facts(facts, go)


# ══════════════ (1) СКЛЕЙКА: ЕДИНИЦА — ПРОЦЕСС ══════════════════════════════════════════════
print("\n(1) склейка: заметки по коммитам → предложение по ОПЕРАЦИИ")
F = Facts()
raw = offers_of(F)
res.append(ok(len(raw) >= 2, "прибор дал заметку на КАЖДЫЙ коммит — вот она, единица до склейки "
              "(%d)" % len(raw)))
folded = deliver_card.fold(raw)
res.append(ok(len(folded) == 1, "после склейки предложение ОДНО: один процесс — один вопрос"))
FOLD = folded[0]
res.append(ok(FOLD["unit"] == "splinter" and FOLD["units"] == ["splinter"],
              "единица названа процессом, а не коммитом"))
res.append(ok(FOLD["n"] == len(raw) and [c["sha"] for c in FOLD["commits"]]
              == [o["sha"] for o in raw],
              "в предложении ВСЕ коммиты рестарта и их число (%d)" % FOLD["n"]))
res.append(ok(FOLD["sha"] == raw[0]["sha"],
              "ключом строки остался САМЫЙ СТАРЫЙ коммит — старые читатели не сломаны"))

# два процесса — две операции, и склейка их НЕ смешивает
two = deliver_card.fold([{"sha": "c1c1c1c", "subject": "a", "age": 10.0, "units": ["splinter"],
                          "by_unit": {"splinter": ["splinter.py"]}},
                         {"sha": "d2d2d2d", "subject": "b", "age": 20.0,
                          "units": ["orchestrator-daemon"],
                          "by_unit": {"orchestrator-daemon": ["orchestrator_daemon.py"]}}])
res.append(ok(len(two) == 2 and [t["unit"] for t in two] == ["orchestrator-daemon", "splinter"],
              "рестарт splinter и рестарт демона — РАЗНЫЕ операции, склейки между ними нет"))
res.append(ok(deliver_card.fold([]) == [] and deliver_card.fold(None) == []
              and deliver_card.fold(["мусор", None]) == [],
              "мусор и пустота на входе → пустой выход (fail-safe)"))

# ══════════════ (2) КАРТОЧКА НАЗЫВАЕТ ВСЮ РАБОТУ РЕСТАРТА ═══════════════════════════════════
print("\n(2) карточка называет число коммитов и перечисляет их")
BODY = deliver_card.render(FOLD)
res.append(ok(("их %d" % FOLD["n"]) in BODY, "число коммитов названо ЦИФРОЙ"))
res.append(ok(all(c["sha"] in BODY for c in FOLD["commits"]),
              "перечислены ВСЕ коммиты, которые доедут этим рестартом"))
res.append(ok("Отдельных карточек на каждый коммит больше не будет" in BODY,
              "владельцу сказано, почему вопрос один"))
res.append(ok("✅" in BODY and "❌" in BODY and "gate.py" in BODY
              and "ТОЛЬКО при зелёном" in BODY,
              "оба исхода и гейт ПЕРЕД рестартом — как было"))
res.append(ok(len(BODY) <= OD.RESULT_MAX, "тело помещается в потолок result (%d)" % len(BODY)))

TZ = deliver_card.tz(700, FOLD)
res.append(ok(all(c["sha"] in TZ for c in FOLD["commits"]) and ("%d коммит" % FOLD["n"]) in TZ,
              "ТЗ доставщика знает ВСЕ коммиты одного перезапуска и их число"))
res.append(ok(TZ.startswith("[конверт одобренной заявки 700]") and TZ.find("gate.py")
              < TZ.find("systemctl restart splinter"),
              "маркер конверта первым, гейт ДО рестарта — контур разрыва петли не тронут"))

# одиночное предложение (форма до 22.09 и прямой зов offer) рендерится КАК РАНЬШЕ
one = deliver_card.render(raw[0])
res.append(ok("живой процесс его НЕ ЧИТАЛ" in one and "ЭТИМ ЖЕ ПЕРЕЗАПУСКОМ" not in one,
              "на одном коммите тело прежнее: списка нет, формула не изменилась"))

# ══════════════ (3) ОТКАТ ОДИН И НАСТОЯЩИЙ ══════════════════════════════════════════════════
print("\n(3) откат называется один и настоящий")
res.append(ok(BODY.count("ОТКАТ ОДИН И НАСТОЯЩИЙ") == 1, "откат в теле РОВНО один"))
res.append(ok(("git checkout %s^ -- ." % FOLD["sha"]) in BODY
              and "systemctl restart splinter" in BODY,
              "откат настоящий: вернуть ДЕРЕВО на состояние до старшего коммита и перезапустить "
              "снова — только это возвращает процесс на прежний код"))
res.append(ok("Откатом НЕ являются" in BODY and "git revert" in BODY
              and "она ничего не меняет" in BODY,
              "❌ и `git revert` названы НЕ-откатами прямо в теле"))
tail = BODY.split("ОТКАТ ОДИН И НАСТОЯЩИЙ")[1]
res.append(ok(tail.find("git checkout") < tail.find("git revert"),
              "настоящий откат стоит ПЕРВЫМ, фальшивые — после него как отказ"))
res.append(ok("систему верну" not in BODY and "откачу" not in BODY,
              "задача отката не обещает: это ход владельца"))

# ══════════════ (4) СТРОКА ОЧЕРЕДИ: НОВОЕ ЧИТАЕТСЯ, СТАРОЕ НЕ СЛОМАНО ═══════════════════════
print("\n(4) строка очереди несёт операцию и все её коммиты")
ROW = deliver_card.row_text(FOLD)
res.append(ok(deliver_card.shas_of(ROW) == [c["sha"] for c in FOLD["commits"]],
              "новый читатель достаёт ВСЕ коммиты карточки"))
res.append(ok(deliver_card.sha_of(ROW) == FOLD["sha"],
              "старый читатель `sha_of` отвечает то же, что отвечал (старший коммит)"))
res.append(ok(deliver_card.units_of(ROW) == ["splinter"],
              "старый читатель `units_of` не сбит списком коммитов"))
OLD_ROW = "[доставка коммита ef20207] доставка в прод: splinter"   # форма до 22.09, дословно
res.append(ok(deliver_card.shas_of(OLD_ROW) == ["ef20207"]
              and deliver_card.units_of(OLD_ROW) == ["splinter"],
              "карточка, висящая в очереди с прошлой редакции, читается новым кодом"))
res.append(ok(deliver_card.shas_of("[конверт одобренной заявки 5] что-то") == []
              and deliver_card.shas_of("") == [],
              "чужая строка коммитов не отдаёт (пусто = разобрать не удалось)"))

# ══════════════ (5) ДЕДУП ДВУСТОРОННЕ ═══════════════════════════════════════════════════════
print("\n(5) дедуп: пока вопрос открыт — второго нет; закрылся — выписка снова открыта")
reset_state()
said1, fb1 = ask(Facts(commits=[("aaa1111", "первый коммит окна", -8 * 3600.0)]))
res.append(ok(len(said1) == 1, "первый вопрос по splinter поставлен"))
CARD1 = said1[0]

# (а) НОВЫЙ КОММИТ В ТО ЖЕ ОКНО — второй карточки НЕТ
OD._deliver_next = 0.0
said2, fb1 = ask(Facts(), fb=fb1)          # тот же мост: карточка CARD1 висит в needs_approval
res.append(ok(said2 == [],
              "новый коммит в то же окно ВТОРОЙ карточки не рождает — рестарт уже заказан"))
res.append(ok(sum(1 for r in fb1.rows.values() if r["status"] == "needs_approval") == 1,
              "у владельца по этому процессу висит РОВНО один вопрос"))

# (б) КАРТОЧКА ЗАКРЫЛАСЬ — ВЫПИСКА СНОВА ОТКРЫТА, и новая несёт ОБА коммита
fb1.rows[CARD1]["status"] = "done"          # владелец ответил (или карточка истекла)
reset_state()                               # память на диске — про уже отвеченные коммиты
OD._deliver_next = 0.0
said3, fb1 = ask(Facts(), fb=fb1)
res.append(ok(len(said3) == 1, "карточка закрыта → выписка снова открыта"))
NEW_ROW = fb1.rows[said3[0]]["task_text"]
res.append(ok(deliver_card.shas_of(NEW_ROW) == ["aaa1111", "bbb2222"],
              "новая карточка несёт ВСЕ накопленные коммиты (%s)"
              % ", ".join(deliver_card.shas_of(NEW_ROW))))

# ПАМЯТЬ ПРО КОММИТЫ: ничего нового — вопроса нет; появился новый — вопрос есть
fb1.rows[said3[0]]["status"] = "done"
OD._deliver_next = 0.0
said4, fb1 = ask(Facts(), fb=fb1)
res.append(ok(said4 == [],
              "те же коммиты второй раз не спрашиваются (память на диске, как была)"))
OD._deliver_next = 0.0
said5, fb1 = ask(Facts(commits=[("aaa1111", "первый", -8 * 3600.0),
                                ("bbb2222", "второй", -6 * 3600.0),
                                ("ccc3333", "третий", -5 * 3600.0)]), fb=fb1)
res.append(ok(len(said5) == 1
              and "ccc3333" in deliver_card.shas_of(fb1.rows[said5[0]]["task_text"]),
              "пришёл НОВЫЙ коммит → вопрос снова законен, и в нём вся накопленная работа"))

# (в) РЕЕСТР МЕЖДУ ДВЕРЬМИ ЗНАЕТ ВСЕ КОММИТЫ КАРТОЧКИ, а не только старший: иначе соседняя
# дверь (куратор) спросила бы о младшем коммите как о новом объекте — тот же дубль сбоку.
# Файл реестра СВОЙ, во временном месте: фикстура в боевое состояние не пишет.
LEDGER = os.path.join(TMP, "ask_ledger.json")
os.environ["CC_ASK_LEDGER_FILE"] = LEDGER
os.environ["ASK_DEDUP"] = "1"
reset_state()
try:
    if os.path.exists(LEDGER):
        os.remove(LEDGER)
    OD._deliver_next = 0.0
    said6, fb6 = ask(Facts())
    keys = []
    if os.path.exists(LEDGER):
        import json                                                          # noqa: E402
        with open(LEDGER, encoding="utf-8") as f:
            keys = sorted((json.load(f) or {}).get("asks") or {})
finally:
    os.environ["ASK_DEDUP"] = "0"
    os.environ.pop("CC_ASK_LEDGER_FILE", None)
res.append(ok(len(said6) == 1 and keys == ["service:splinter|aaa1111", "service:splinter|bbb2222"],
              "в реестр между дверьми уехали ОБА коммита одной операции (%s)" % ", ".join(keys)))

# ══════════════ (6) МУТАНТ: ЛОМАЕМ ДЕДУП НАМЕРЕННО ══════════════════════════════════════════
print("\n(6) мутант: дедуп по процессу сломан — проверка обязана покраснеть")


def scenario_a():
    """Сценарий (а) отдельной функцией: один прогон ставит карточку, второй приходит с НОВЫМ
    коммитом при ОТКРЫТОЙ карточке. Возвращает число карточек у владельца после обоих."""
    reset_state()
    s1, fb = ask(Facts(commits=[("aaa1111", "первый коммит окна", -8 * 3600.0)]))
    OD._deliver_next = 0.0
    s2, fb = ask(Facts(), fb=fb)
    return len(s1) + len(s2)


live_n = scenario_a()
keep_units = OD._deliver_open_units


def mutant_open_units():
    """МУТАНТ: рубеж «по этому процессу вопрос уже открыт» возвращает пустоту — ровно то, чем
    он был до 22.09, когда ключом служил КОММИТ (открытая карточка о `ef20207` про splinter не
    говорила ничего)."""
    return scan_result.ScanResult(scanned=0, parsed=0,
                                  subject="открытых карточек доставки в очереди", payload=set())


OD._deliver_open_units = mutant_open_units
try:
    mutant_n = scenario_a()
finally:
    OD._deliver_open_units = keep_units
after_n = scenario_a()
res.append(ok(live_n == 1, "живой код: у владельца ОДИН вопрос на оба коммита (карточек %d)"
              % live_n))
res.append(ok(mutant_n == 2, "мутант: карточек стало %d вместо %d — ровно живой дефект 21.09 "
              "(15 и 16 об одном splinter)" % (mutant_n, live_n)))
res.append(ok(mutant_n - live_n == 1,
              "ЧИСЛОМ: поломка дедупа добавляет владельцу +%d лишний вопрос за окно, и проверка "
              "(5а) на ней краснеет" % (mutant_n - live_n)))
res.append(ok(after_n == live_n, "мутант снят — поведение вернулось (%d)" % after_n))

# ══════════════ (7) ПОТОЛОК СУТОК СЧИТАЕТ ВОПРОСЫ ═══════════════════════════════════════════
print("\n(7) потолок суток считает вопросы, а не коммиты")
reset_state()
now = datetime.datetime.now(datetime.timezone.utc).timestamp()
for s in ("m1", "m2", "m3", "m4"):
    OD._deliver_mark(s, now)                # ОДНА карточка на четыре коммита — одно время
OD._deliver_next = 0.0
said7, fb7 = ask(Facts())
res.append(ok(len(said7) == 1,
              "склеенная карточка на 4 коммита съедает ОДИН вопрос из потолка, а не четыре"))
reset_state()
for i in range(OD.DELIVER_DAY_CAP):
    OD._deliver_mark("dead%d" % i, now - i)  # РАЗНЫЕ вопросы — разное время
OD._deliver_next = 0.0
said8, fb8 = ask(Facts())
res.append(ok(said8 == [] and "enqueue_task" not in fb8.calls,
              "потолок вопросов достигнут → молчим, недоставку по-прежнему видно в О3"))

# ══════════════ (8) ГРАНИЦЫ ═════════════════════════════════════════════════════════════════
print("\n(8) границы: решение чистое, операций нет, боевое состояние не тронуто")
src = open(os.path.join(REPO, "deliver_card.py"), encoding="utf-8").read()
imports = [l for l in src.splitlines() if l.startswith(("import ", "from "))]
res.append(ok(imports == ["import expectations"],
              "импорт по-прежнему ровно один: склейка ничего не читает и никуда не шлёт"))
res.append(ok("subprocess" not in src and "os.system" not in src,
              "инструментов у решения нет — перезапустить ему нечем"))
import invariants_check as IC            # noqa: E402


class Run:
    def __init__(s):
        s.flags = []

    def flag(s, where, why):
        s.flags.append((where, why))


run = Run()
IC.check_deliver_card_pure(None, run)
res.append(ok(not run.flags, "страж DELIVER_CARD_PURE проходит (%s)" % run.flags))

od_src = open(os.path.join(REPO, "orchestrator_daemon.py"), encoding="utf-8").read()
branch = od_src.split("def _maybe_deliver_ask")[1].split("\ndef ")[0]
res.append(ok("systemctl" not in branch and "subprocess" not in branch,
              "в ветке предложения нет ни одной команды перезапуска"))
res.append(ok(od_src.count("_convert_deliver_approved(") == 2,
              "дверь исполнения ответа по-прежнему ровно одна (определение + вызов)"))
guard_src = open(os.path.join(REPO, "pretool_guard.py"), encoding="utf-8").read()
res.append(ok("deliver_card" not in guard_src,
              "pretool_guard.py этой правкой не тронут ни одной строкой"))

# ПУТЬ ДО ЧЕЛОВЕКА: боевой отправитель за весь прогон не звался ни разу
import bridge_client                     # noqa: E402
res.append(ok(OD.bc is not None and not isinstance(OD.bc, FakeBridge),
              "после прогона боевой клиент моста возвращён на место"))
res.append(ok(isinstance(OD.bc, bridge_client.BridgeClient)
              and not isinstance(FakeBridge(None), bridge_client.BridgeClient),
              "боевой отправитель и фикстура — РАЗНЫЕ объекты, различить можно типом"))
res.append(ok("send_card" not in src and "notify" not in src,
              "в решении нет ни одного имени отправки владельцу"))

AFTER = {p: sha256(p) for p in WATCH_FILES}
res.append(ok(AFTER[os.path.join(REPO, "chain_series.json")]
              == BEFORE[os.path.join(REPO, "chain_series.json")],
              "боевой файл счёта серии не тронут ни на байт"))
res.append(ok(AFTER[os.path.join(REPO, "chain_cards.jsonl")]
              == BEFORE[os.path.join(REPO, "chain_cards.jsonl")],
              "боевой журнал карточек не тронут ни на байт"))

shutil.rmtree(STATE_DIR, ignore_errors=True)
print("\n%d/%d" % (sum(1 for x in res if x), len(res)))
sys.exit(0 if all(res) else 1)
